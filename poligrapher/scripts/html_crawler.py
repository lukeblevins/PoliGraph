#!/usr/bin/env python3
"""Download a web page and export the accessibility tree for parsing."""

import argparse
import base64
import json
import logging
from pathlib import Path
import re
import urllib.parse as urlparse

import bs4
import langdetect
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
import requests
from requests_cache import CachedSession

READABILITY_JS_COMMIT = "8e8ec27cd2013940bc6f3cc609de10e35a1d9d86"
READABILITY_JS_URL = (
    f"https://raw.githubusercontent.com/mozilla/readability/{READABILITY_JS_COMMIT}"
)
REQUESTS_TIMEOUT = 10

# Chromium's accessibility snapshot uses different role names than Firefox (which
# this pipeline was originally built around). Map Chromium roles onto the Firefox
# vocabulary that SegmentExtractor consumes so the exported tree is equivalent
# regardless of browser. Roles not listed here already match or are handled.
_CHROMIUM_ROLE_MAP = {
    "WebArea": "document",
    "RootWebArea": "document",
    "generic": "section",
    "none": "section",
    "main": "section",
    "complementary": "section",
    "LabelText": "label",
    "StaticText": "statictext",
    "image": "img",
    "LineBreak": "whitespace",
    "ListMarker": "list item marker",
}


def normalize_accessibility_tree(node):
    """Rewrite Chromium role names to the Firefox equivalents in place.

    Chromium wraps every text node's runs in empty-named ``InlineTextBox``
    children; the real text lives on the parent ``text`` node's ``name``. We drop
    those children (and remove a now-empty ``children`` key) so the text node
    becomes a leaf whose name SegmentExtractor will read.
    """
    if node is None:
        return node
    role = node.get("role")
    if role in _CHROMIUM_ROLE_MAP:
        node["role"] = _CHROMIUM_ROLE_MAP[role]

    kept = [c for c in node.get("children", []) if c.get("role") != "InlineTextBox"]
    if kept:
        node["children"] = kept
        for child in kept:
            normalize_accessibility_tree(child)
    else:
        node.pop("children", None)
    return node


def get_readability_js():
    session = CachedSession("py_request_cache", backend="filesystem", use_temp=True)
    js_code = []
    res = session.get(f"{READABILITY_JS_URL}/Readability.js", timeout=REQUESTS_TIMEOUT)
    res.raise_for_status()
    js_code.append(res.text)
    res = session.get(
        f"{READABILITY_JS_URL}/Readability-readerable.js", timeout=REQUESTS_TIMEOUT
    )
    res.raise_for_status()
    js_code.append(res.text)
    return "\n".join(js_code)


def url_arg_handler(url):
    parsed_url = urlparse.urlparse(url)

    # Not HTTP(s): interpret as a file path
    if parsed_url.scheme not in ["http", "https"]:
        parsed_path = Path(url).absolute()

        if not parsed_path.is_file():
            raise FileNotFoundError(f"File {url} not found")

        return parsed_path.as_uri()

    # Handle Google Docs URLs
    if (
        parsed_url.hostname == "docs.google.com"
        and not parsed_url.path.endswith("/pub")
        and (
            m := re.match(
                r"/document/d/(1[a-zA-Z0-9_-]{42}[AEIMQUYcgkosw048])", parsed_url.path
            )
        )
    ):
        logging.info("Exporting HTML from Google Docs URL...")

        export_url = f"https://docs.google.com/feeds/download/documents/export/Export?id={m[1]}&exportFormat=html"

        req = requests.get(export_url, timeout=REQUESTS_TIMEOUT)
        req.raise_for_status()

        base64_url = "data:text/html;base64," + base64.b64encode(req.content).decode()
        req.close()
        return base64_url

    # Perform a HEAD preflight to weed out obviously unreachable endpoints before
    # launching the browser (difference #6 retained). We allow auth and method
    # errors (401/403/405/501) to pass through since content might still render.
    try:
        resp = requests.head(url, timeout=REQUESTS_TIMEOUT, allow_redirects=True)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise RuntimeError(f"Preflight HEAD request failed for {url}: {e}") from e
    status = resp.status_code
    if status >= 400 and status not in {401, 403, 405, 501}:
        raise RuntimeError(f"Preflight HEAD request for {url} returned HTTP {status}")
    return url


def main(url, output, no_readability_js=False):
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
    )

    args = argparse.Namespace(
        url=url, output=output, no_readability_js=no_readability_js
    )
    access_url = url_arg_handler(args.url)

    with sync_playwright() as p:
        # Chromium is used for crawling (Firefox fails to launch headless in some
        # environments). Playwright's accessibility snapshot is a normalized,
        # cross-browser tree, so SegmentExtractor consumes it unchanged. CSP is
        # bypassed via the browser context so Readability.js can always be
        # injected, and cert errors are ignored to tolerate deprecated TLS.
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        context = browser.new_context(bypass_csp=True, ignore_https_errors=True)
        context.set_default_timeout(REQUESTS_TIMEOUT * 1000)

        def error_cleanup(msg):
            logging.error(msg)
            try:
                context.close()
                browser.close()
            finally:
                raise RuntimeError(f"html_crawler failure: {msg}")

        page = context.new_page()
        page.set_default_timeout(REQUESTS_TIMEOUT * 1000)
        page.set_viewport_size({"width": 1080, "height": 1920})
        logging.info("Navigating to %r", access_url)

        # Record HTTP status and navigated URLs so we can check errors later
        url_status = dict()
        navigated_urls = []
        page.on("response", lambda r: url_status.update({r.url: r.status}))
        page.on(
            "framenavigated",
            lambda f: f.parent_frame is None and navigated_urls.append(f.url),
        )

        try:
            page.goto(access_url)
            page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            logging.warning("Cannot reach networkidle but will continue")

        # Check HTTP errors
        for url in navigated_urls:
            if (status_code := url_status.get(url, 0)) >= 400:
                error_cleanup(f"Got HTTP error {status_code}")

        page.evaluate("window.stop()")
        if not args.no_readability_js:
            page.add_script_tag(content=get_readability_js())
        readability_info = page.evaluate(
            r"""(no_readability_js) => {
            window.stop();

            const documentClone = document.cloneNode(true);
            const article = new Readability(documentClone).parse();
            if (!article) {
                throw new Error("Readability.js failed to parse the document");
            }
            article.applied = false;

            document.querySelectorAll('[aria-hidden=true]').forEach((x) => x.setAttribute("aria-hidden", false));

            if (isProbablyReaderable(document) && !no_readability_js) {
                documentClone.body.innerHTML = article.content;

                if (documentClone.body.innerText.search(/(data|privacy|cookie)\s*(policy|notice)/) >= 0) {
                    document.body.innerHTML = article.content;
                    article.applied = true;
                }
            }

            for (const elem of document.querySelectorAll('script, link, style, header, footer, nav'))
                elem.remove();

            return article;
        }""",
            [args.no_readability_js],
        )
        cleaned_html = page.content()

        # Check language
        soup = bs4.BeautifulSoup(cleaned_html, "lxml")
        soup_text = soup.body.text if soup.body else ""

        try:
            lang = langdetect.detect(soup_text)
        except langdetect.lang_detect_exception.LangDetectException:
            lang = "UNKNOWN"

        if not lang.lower().startswith("en"):
            error_cleanup(f"Content language {lang} isn't English")

        if re.search(r"(data|privacy)\s*(?:policy|notice)", soup_text, re.I) is None:
            error_cleanup("Not like a privacy policy")

        # obtain the accessibility tree (normalized to the Firefox role vocabulary)
        snapshot = page.accessibility.snapshot(interesting_only=False)
        snapshot = normalize_accessibility_tree(snapshot)

        output_dir = Path(args.output)
        output_dir.mkdir(exist_ok=True)

        with open(
            output_dir / "accessibility_tree.json", "w", encoding="utf-8"
        ) as fout:
            json.dump(snapshot, fout)

        with open(output_dir / "cleaned.html", "w", encoding="utf-8") as fout:
            fout.write(cleaned_html)

        with open(output_dir / "readability.json", "w", encoding="utf-8") as fout:
            json.dump(readability_info, fout)

        logging.info("Saved to %s", output_dir)
        context.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output_dir")
    parser.add_argument(
        "--no-readability-js",
        action="store_true",
        help="Disable Readability.js content extraction",
    )
    cli_args = parser.parse_args()
    main(
        cli_args.url, cli_args.output_dir, no_readability_js=cli_args.no_readability_js
    )

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import threading
import time

import fitz

from poligrapher.scripts import html_crawler


POLICY_HTML = """\
<!doctype html>
<html lang="en">
  <head><title>Privacy Policy</title></head>
  <body>
    <main aria-hidden="true">
      <div>
        <span>Privacy Policy</span>
        <span>We collect personal data to provide our services.</span>
        <span>You may contact us to request access or deletion.</span>
      </div>
    </main>
  </body>
</html>
"""


NULL_READABILITY_JS = """
function Readability(documentClone) {
  this.parse = function () { return null; };
}
function isProbablyReaderable(document) { return false; }
"""


DYNAMICALLY_CLEARED_POLICY_HTML = """\
<!doctype html>
<html lang="en">
  <head><title>Privacy Policy</title></head>
  <body>
    <main>
      <h1>Privacy Policy</h1>
      <p>We collect personal data to provide our services.</p>
      <p>You may contact us to request access or deletion.</p>
    </main>
    <script>document.body.innerHTML = "";</script>
  </body>
</html>
"""


@contextmanager
def _serve_html(html, first_get_delay=0):
    body = html.encode()
    request_state = {"get_count": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()

        def do_GET(self):
            request_state["get_count"] += 1
            if request_state["get_count"] == 1:
                time.sleep(first_get_delay)
            self.do_HEAD()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/privacy-policy"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_crawler_launches_chromium_not_firefox():
    source = inspect.getsource(html_crawler.main)
    assert "p.chromium.launch" in source
    assert "p.firefox.launch" not in source


def _write_policy(tmp_path):
    source = tmp_path / "privacy-policy.html"
    source.write_text(POLICY_HTML)
    return source


def test_null_readability_result_falls_back_to_original_document(tmp_path, monkeypatch):
    source = _write_policy(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(html_crawler, "get_readability_js", lambda: NULL_READABILITY_JS)

    html_crawler.main(str(source), str(output))

    cleaned_html = (output / "cleaned.html").read_text()
    readability = json.loads((output / "readability.json").read_text())
    assert "We collect personal data" in cleaned_html
    assert readability == {"applied": False, "reason": "parse_failed"}


def test_no_readability_mode_does_not_load_or_call_readability(tmp_path, monkeypatch):
    source = _write_policy(tmp_path)
    output = tmp_path / "output"

    def fail_if_loaded():
        raise AssertionError("Readability.js must not load when disabled")

    monkeypatch.setattr(html_crawler, "get_readability_js", fail_if_loaded)

    html_crawler.main(str(source), str(output), no_readability_js=True)

    cleaned_html = (output / "cleaned.html").read_text()
    readability = json.loads((output / "readability.json").read_text())
    assert "We collect personal data" in cleaned_html
    assert readability == {"applied": False, "reason": "disabled"}


def test_empty_rendered_dom_falls_back_to_http_source(tmp_path):
    output = tmp_path / "output"
    pdf_output = tmp_path / "policy.pdf"

    with _serve_html(DYNAMICALLY_CLEARED_POLICY_HTML) as url:
        html_crawler.main(
            url,
            str(output),
            no_readability_js=True,
            pdf_output=pdf_output,
        )

    cleaned_html = (output / "cleaned.html").read_text()
    readability = json.loads((output / "readability.json").read_text())
    with fitz.open(pdf_output) as pdf:
        pdf_text = "".join(page.get_text() for page in pdf)

    assert "We collect personal data" in cleaned_html
    assert "We collect personal data" in pdf_text
    assert readability == {"applied": False, "reason": "http_fallback"}


def test_navigation_timeout_falls_back_without_evaluating_stuck_page(
    tmp_path, monkeypatch
):
    output = tmp_path / "output"
    monkeypatch.setattr(html_crawler, "NAV_TIMEOUT", 0.1)

    with _serve_html(POLICY_HTML, first_get_delay=1) as url:
        html_crawler.main(url, str(output), no_readability_js=True)

    cleaned_html = (output / "cleaned.html").read_text()
    readability = json.loads((output / "readability.json").read_text())
    assert "We collect personal data" in cleaned_html
    assert readability == {"applied": False, "reason": "http_fallback"}

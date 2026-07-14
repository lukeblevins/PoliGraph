import inspect
import json

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

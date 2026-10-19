import re
from pathlib import Path

import bpmn2graphml

VIEWER = Path(bpmn2graphml.__file__).parent / "viewer"
EXTERNAL = ("http://", "https://", "//")


def _refs(html: str) -> list[str]:
    return re.findall(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+)"', html)


def test_viewer_assets_local():
    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    refs = _refs(html)
    assert any(r.endswith("bpmn-navigated-viewer.production.min.js") for r in refs)
    assert {"properties.js", "app.js", "app.css"} <= set(refs)
    for ref in refs:
        if ref.startswith("data:"):
            continue
        assert not ref.startswith(EXTERNAL), ref
        assert (VIEWER / ref).is_file(), ref
        if ref.endswith(".css"):
            css = (VIEWER / ref).read_text(encoding="utf-8")
            for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
                if url.startswith("data:"):
                    continue
                assert not url.startswith(EXTERNAL), url
                assert ((VIEWER / ref).parent / url.split("?")[0].split("#")[0]).is_file(), url


def test_viewer_no_module_scripts():
    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' not in html
    assert "alert(" not in (VIEWER / "app.js").read_text(encoding="utf-8")


def test_hidden_attribute_beats_display_rules():
    # .drop-hint 等元素设了 display:flex，会盖过浏览器默认的 [hidden]{display:none}
    css = (VIEWER / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", css)

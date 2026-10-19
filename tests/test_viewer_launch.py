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


def _attr(html: str, name: str) -> str:
    return re.search(rf'{name}="([^"]*)"', html).group(1)


def test_launch_page_embeds_utf8_bpmn(tmp_path):
    import base64
    import html as htmllib

    from bpmn2graphml.viewer_launch import make_launch_page
    from conftest import FIX
    src = FIX / "科技创新平台策划.bpmn"
    page = make_launch_page(src, tmp_path)
    text = page.read_text(encoding="utf-8")
    assert 'id="b2g-preload"' in text
    assert base64.b64decode(_attr(text, "data-base64")) == src.read_bytes()
    assert htmllib.unescape(_attr(text, "data-filename")) == "科技创新平台策划.bpmn"


def test_launch_page_assets_absolute(tmp_path):
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    from bpmn2graphml.viewer_launch import make_launch_page
    from conftest import FIX
    text = make_launch_page(FIX / "科技创新平台策划.bpmn", tmp_path).read_text(encoding="utf-8")
    refs = [r for r in _refs(text) if not r.startswith("data:")]
    assert len(refs) == 6
    for ref in refs:
        assert ref.startswith("file:///"), ref
        assert Path(url2pathname(urlparse(ref).path)).is_file(), ref


def test_open_viewer_without_file():
    from bpmn2graphml.viewer_launch import VIEWER_DIR, open_viewer
    opened = []
    assert open_viewer(opener=opened.append) == VIEWER_DIR / "index.html"
    assert opened == [(VIEWER_DIR / "index.html").as_uri()]


def test_open_viewer_with_file(tmp_path, monkeypatch):
    import tempfile

    from bpmn2graphml.viewer_launch import open_viewer
    from conftest import FIX
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    opened = []
    page = open_viewer(FIX / "平台建设运行.bpmn", opener=opened.append)
    assert page.name == "view.html" and page.is_file()
    assert opened == [page.as_uri()]

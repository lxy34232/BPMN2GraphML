"""在浏览器中打开可视化查看器（bpmn2graphml/viewer/index.html）。

浏览器从 file:// 打开的页面不能读取任意本地路径，所以带文件打开时，
生成一个临时启动页：资源改为绝对 file:// 地址，BPMN 内容以 base64 嵌入。
"""
from __future__ import annotations

import base64
import html
import re
import tempfile
import webbrowser
from pathlib import Path

VIEWER_DIR = Path(__file__).parent / "viewer"

_REF = re.compile(r'(<(?:script|link)\b[^>]*?\b(?:src|href)=")([^"]+)(")')
_KEEP = ("data:", "http:", "https:", "//", "file:")


def _default_opener(url: str) -> None:
    webbrowser.open(url)


def make_launch_page(bpmn_path: Path, out_dir: Path | None = None) -> Path:
    bpmn_path = Path(bpmn_path)
    page = (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

    def absolutize(m: re.Match) -> str:
        ref = m.group(2)
        if ref.startswith(_KEEP):
            return m.group(0)
        return m.group(1) + (VIEWER_DIR / ref).resolve().as_uri() + m.group(3)

    page = _REF.sub(absolutize, page)
    data = base64.b64encode(bpmn_path.read_bytes()).decode("ascii")
    preload = (f'  <script type="text/plain" id="b2g-preload" '
               f'data-filename="{html.escape(bpmn_path.name, quote=True)}" data-base64="{data}"></script>\n')
    # 必须出现在 app.js 之前，app.js 执行时才能找到它
    page = page.replace("</main>\n", "</main>\n" + preload, 1)
    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="b2g-view-"))
    out = out_dir / "view.html"
    out.write_text(page, encoding="utf-8")
    return out


def open_viewer(bpmn_path: Path | None = None, opener=None) -> Path:
    """用浏览器打开查看器；给出文件时直接打开该文件。返回被打开的页面路径。"""
    opener = opener or _default_opener
    page = make_launch_page(bpmn_path) if bpmn_path else VIEWER_DIR / "index.html"
    opener(page.as_uri())
    return page

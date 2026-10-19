"""共用的 XML 写出：UTF-8，双引号 XML 声明，缩进排版。"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET


def write_xml(root: ET.Element, path: str | os.PathLike) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree)
    with open(path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="UTF-8", xml_declaration=False)

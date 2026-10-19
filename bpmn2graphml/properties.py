"""节点属性的存放格式（查看器与以后的配置表工具共用）：

    <bpmn2:extensionElements>
      <b2g:properties>
        <b2g:property name="负责人" value="张三"/>
      </b2g:properties>
    </bpmn2:extensionElements>

多值时重复写同名 property。本模块作用于 Origin.children_xml（子元素序列化列表）。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .model import BPMN_NS

B2G_NS = "https://github.com/lxy34232/BPMN2GraphML/properties"
SOURCE_PROP = "来源流程"

Prop = tuple[str, str]

_EXT = f"{{{BPMN_NS}}}extensionElements"
_DOC = f"{{{BPMN_NS}}}documentation"
_PROPS = f"{{{B2G_NS}}}properties"
_PROP = f"{{{B2G_NS}}}property"


def read_b2g_properties(children_xml: list[str]) -> list[Prop]:
    props: list[Prop] = []
    for xml in children_xml:
        el = ET.fromstring(xml)
        if el.tag != _EXT:
            continue
        for group in el.findall(_PROPS):
            for p in group.findall(_PROP):
                name, value = (p.get("name") or "").strip(), (p.get("value") or "").strip()
                if name and value:
                    props.append((name, value))
    return props


def with_b2g_properties(children_xml: list[str], props: list[Prop]) -> list[str]:
    """返回新的 children_xml：替换掉已有的 b2g:properties，其它扩展内容原样保留。"""
    ET.register_namespace("b2g", B2G_NS)
    elements = [ET.fromstring(x) for x in children_xml]
    ext = next((e for e in elements if e.tag == _EXT), None)
    if ext is not None:
        for group in ext.findall(_PROPS):
            ext.remove(group)
    if props:
        if ext is None:
            ext = ET.Element(_EXT)
            insert_at = sum(1 for e in elements if e.tag == _DOC)
            elements.insert(insert_at, ext)
        group = ET.SubElement(ext, _PROPS)
        for name, value in props:
            ET.SubElement(group, _PROP, name=name, value=value)
    if ext is not None and len(ext) == 0 and not (ext.text or "").strip():
        elements.remove(ext)
    return [ET.tostring(e, encoding="unicode") for e in elements]

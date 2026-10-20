"""节点属性的存放格式（查看器与以后的配置表工具共用）：

    <bpmn2:extensionElements>
      <b2g:properties>
        <b2g:property name="负责人" value="张三"/>
      </b2g:properties>
    </bpmn2:extensionElements>

多值时重复写同名 property。本模块既可作用于节点元素本身，也可作用于
Origin.children_xml（子元素序列化列表）。
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


TYPE_LABELS = {
    "task": "任务", "manualTask": "人工任务", "userTask": "用户任务", "serviceTask": "服务任务",
    "scriptTask": "脚本任务", "sendTask": "发送任务", "receiveTask": "接收任务",
    "businessRuleTask": "业务规则任务", "subProcess": "子流程", "callActivity": "调用活动",
    "startEvent": "开始事件", "endEvent": "结束事件", "intermediateThrowEvent": "中间抛出事件",
    "intermediateCatchEvent": "中间捕获事件", "boundaryEvent": "边界事件",
    "exclusiveGateway": "排他网关", "parallelGateway": "并行网关", "inclusiveGateway": "包容网关",
    "eventBasedGateway": "事件网关", "complexGateway": "复杂网关",
}


def type_label(bpmn_type: str) -> str:
    """与查看器 properties.js 的 TYPE_LABELS 一致；未知类型返回原标签名。"""
    return TYPE_LABELS.get(bpmn_type, bpmn_type)


def node_b2g_properties(node: ET.Element) -> list[Prop]:
    """读取节点（其直接子元素 extensionElements 下）的 b2g 属性。"""
    props: list[Prop] = []
    for ext in node.findall(_EXT):
        for group in ext.findall(_PROPS):
            for p in group.findall(_PROP):
                name, value = (p.get("name") or "").strip(), (p.get("value") or "").strip()
                if name and value:
                    props.append((name, value))
    return props


def set_node_b2g_properties(node: ET.Element, props: list[Prop]) -> None:
    """就地替换节点的 b2g:properties，extensionElements 中其它内容原样保留。"""
    ext = node.find(_EXT)
    if ext is not None:
        for group in ext.findall(_PROPS):
            ext.remove(group)
    if props:
        if ext is None:
            ext = ET.Element(_EXT)
            insert_at = 0
            while insert_at < len(node) and node[insert_at].tag == _DOC:
                insert_at += 1
            node.insert(insert_at, ext)
        group = ET.SubElement(ext, _PROPS)
        for name, value in props:
            ET.SubElement(group, _PROP, name=name, value=value)
    if ext is not None and len(ext) == 0 and not (ext.text or "").strip():
        node.remove(ext)


def _wrap(children_xml: list[str]) -> ET.Element:
    wrapper = ET.Element("wrapper")
    wrapper.extend(ET.fromstring(x) for x in children_xml)
    return wrapper


def read_b2g_properties(children_xml: list[str]) -> list[Prop]:
    return node_b2g_properties(_wrap(children_xml))


def with_b2g_properties(children_xml: list[str], props: list[Prop]) -> list[str]:
    """返回新的 children_xml：替换掉已有的 b2g:properties，其它扩展内容原样保留。"""
    ET.register_namespace("b2g", B2G_NS)
    wrapper = _wrap(children_xml)
    set_node_b2g_properties(wrapper, props)
    return [ET.tostring(e, encoding="unicode") for e in wrapper]

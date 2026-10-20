import xml.etree.ElementTree as ET

from bpmn2graphml.model import BPMN_NS
from bpmn2graphml.properties import (B2G_NS, TYPE_LABELS, node_b2g_properties,
                                     read_b2g_properties, set_node_b2g_properties,
                                     type_label, with_b2g_properties)

EXT = (f'<bpmn2:extensionElements xmlns:bpmn2="{BPMN_NS}" xmlns:ext="http://example.com/ext">'
       '<ext:info level="1"/></bpmn2:extensionElements>')
DOC = f'<bpmn2:documentation xmlns:bpmn2="{BPMN_NS}">说明</bpmn2:documentation>'


def test_read_b2g_properties_trims():
    xml = (f'<bpmn2:extensionElements xmlns:bpmn2="{BPMN_NS}" xmlns:b2g="{B2G_NS}">'
           '<b2g:properties><b2g:property name=" 负责人 " value=" 张三 "/>'
           '<b2g:property name="系统" value=""/><b2g:property name="" value="x"/>'
           '</b2g:properties></bpmn2:extensionElements>')
    assert read_b2g_properties([xml]) == [("负责人", "张三")]


def test_read_ignores_other_namespaces():
    xml = (f'<bpmn2:extensionElements xmlns:bpmn2="{BPMN_NS}" xmlns:c="http://camunda.org/schema/1.0/bpmn">'
           '<c:properties><c:property name="a" value="1"/></c:properties></bpmn2:extensionElements>')
    assert read_b2g_properties([xml]) == []


def test_write_creates_extension_after_documentation():
    out = with_b2g_properties([DOC, '<timer xmlns="x"/>'], [("负责人", "张三")])
    assert len(out) == 3
    assert "documentation" in out[0]
    assert "extensionElements" in out[1]
    assert "timer" in out[2]
    assert read_b2g_properties(out) == [("负责人", "张三")]


def test_write_keeps_other_extension_content():
    out = with_b2g_properties([EXT], [("a", "1")])
    assert len(out) == 1
    assert "info" in out[0] and B2G_NS in out[0]
    assert read_b2g_properties(out) == [("a", "1")]


def test_write_replaces_existing_b2g():
    once = with_b2g_properties([EXT], [("a", "1")])
    assert read_b2g_properties(with_b2g_properties(once, [("b", "2")])) == [("b", "2")]


def test_write_empty_removes():
    once = with_b2g_properties([EXT], [("a", "1")])
    out = with_b2g_properties(once, [])
    assert read_b2g_properties(out) == []
    assert "info" in out[0]


def test_write_multi_values_in_order():
    out = with_b2g_properties([], [("来源流程", "A"), ("来源流程", "B")])
    assert read_b2g_properties(out) == [("来源流程", "A"), ("来源流程", "B")]


def _node(inner=""):
    return ET.fromstring(f'<bpmn2:task xmlns:bpmn2="{BPMN_NS}" id="t" name="n">{inner}'
                         '<bpmn2:incoming>f1</bpmn2:incoming></bpmn2:task>')


def _tags(node):
    return [c.tag.rsplit("}", 1)[1] for c in node]


def test_type_label():
    assert type_label("manualTask") == "人工任务"
    assert type_label("boundaryEvent") == "边界事件"
    assert type_label("weird") == "weird"
    assert len(TYPE_LABELS) == 20


def test_set_node_creates_after_documentation():
    node = _node(f'<bpmn2:documentation>说明</bpmn2:documentation>')
    set_node_b2g_properties(node, [("负责人", "张三"), ("系统", "OA"), ("系统", "ERP")])
    assert _tags(node) == ["documentation", "extensionElements", "incoming"]
    assert node_b2g_properties(node) == [("负责人", "张三"), ("系统", "OA"), ("系统", "ERP")]


def test_set_node_empty_removes_extension():
    node = _node()
    set_node_b2g_properties(node, [("a", "1")])
    set_node_b2g_properties(node, [])
    assert _tags(node) == ["incoming"]


def test_set_node_keeps_other_extensions():
    camunda = ('<bpmn2:extensionElements xmlns:c="http://camunda.org/schema/1.0/bpmn">'
               '<c:properties><c:property name="x" value="1"/></c:properties>'
               '</bpmn2:extensionElements>')
    node = _node(camunda)
    set_node_b2g_properties(node, [("a", "1")])
    set_node_b2g_properties(node, [])
    ext = node.find(f"{{{BPMN_NS}}}extensionElements")
    assert ext is not None
    assert ext.find("{http://camunda.org/schema/1.0/bpmn}properties") is not None
    assert node_b2g_properties(node) == []

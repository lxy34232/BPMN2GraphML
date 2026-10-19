from bpmn2graphml.model import BPMN_NS
from bpmn2graphml.properties import B2G_NS, read_b2g_properties, with_b2g_properties

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

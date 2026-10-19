import pytest

from bpmn2graphml.bpmn_reader import BpmnReadError, read_bpmn
from bpmn2graphml.model import BPMN_NS
from conftest import FIX

START = "EBPM_21298a9b-4681-18a2-2219-eec70541056e"
GW = "EBPM_2783b857-45a5-40e5-84d6-3b98c770a0b8"
SUB = "EBPM_5cd3a4cf-43f3-49b0-1962-356448c0579c"
TASK = "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e"


@pytest.fixture
def ref():
    return read_bpmn(FIX / "科技创新平台策划.bpmn")


def test_reads_reference_nodes_and_flows(ref):
    assert len(ref.nodes) == 12 and len(ref.edges) == 13
    assert ref.nodes[START].bpmn_type == "startEvent"
    assert ref.nodes[START].name == "接收到外部科技创新平台申报通知"
    assert ref.nodes[GW].name == ""
    e = ref.edges["EBPM_ea9d4cad-60ee-bf38-be14-817d219d55e7"]
    assert (e.source, e.target, e.name) == (
        "EBPM_12354ce6-5b67-fc6c-5e49-52763f5c26a9", GW, "审核不通过")


def test_reads_bounds(ref):
    assert ref.nodes[START].bounds == (312, 162, 56, 56)


def test_subprocess_marked_expandable(ref):
    assert ref.nodes[SUB].expandable is True
    assert ref.nodes[TASK].expandable is False


def test_source_info(ref):
    (s,) = ref.sources
    assert s.file == "科技创新平台策划"
    assert s.process_attrs["id"] == "Process_1"
    assert s.definitions_attrs["id"] == "sample-diagram"
    assert s.namespaces["bpmn2"] == BPMN_NS
    assert (s.diagram_id, s.plane_id) == ("BPMNDiagram_1", "BPMNPlane_1")


def test_origin_single_and_order(ref):
    elements = list(ref.nodes.values()) + list(ref.edges.values())
    for el in elements:
        assert len(el.origins) == 1
        assert el.origins[0].id == el.id
        assert el.origins[0].file == "科技创新平台策划"
    orders = sorted(el.origins[0].order for el in elements)
    assert len(set(orders)) == len(orders)
    # 文档顺序：第一个元素是网关，最后一个是最后一条连线
    assert ref.nodes[GW].origins[0].order == orders[0]
    assert ref.edges["EBPM_7a6586a2-9327-45b5-1efe-1a37c88d8586"].origins[0].order == orders[-1]


def test_flow_origin_has_endpoints(ref):
    o = ref.edges["EBPM_ea9d4cad-60ee-bf38-be14-817d219d55e7"].origins[0]
    assert (o.source_id, o.target_id) == ("EBPM_12354ce6-5b67-fc6c-5e49-52763f5c26a9", GW)
    assert "sourceRef" not in o.attrs and "name" not in o.attrs


def test_default_prefix_and_extensions():
    g = read_bpmn(FIX / "科技创新平台申报.bpmn")
    t = g.nodes["Task_1"]
    assert t.bpmn_type == "userTask"
    assert t.origins[0].attrs["{http://example.com/ext}owner"] == "科技管理部"
    assert len(t.origins[0].children_xml) == 1
    assert "extensionElements" in t.origins[0].children_xml[0]
    assert g.nodes["Gateway_1"].name is None


def test_missing_di():
    g = read_bpmn(FIX / "平台建设运行.bpmn")
    assert len(g.nodes) == 4
    assert all(n.bounds is None for n in g.nodes.values())


def test_invalid_file_raises(tmp_path):
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml", encoding="utf-8")
    with pytest.raises(BpmnReadError, match="bad.bpmn"):
        read_bpmn(bad)
    other = tmp_path / "other.bpmn"
    other.write_text("<root/>", encoding="utf-8")
    with pytest.raises(BpmnReadError, match="other.bpmn"):
        read_bpmn(other)


def test_unsupported_elements_warn(tmp_path):
    p = tmp_path / "x.bpmn"
    p.write_text(
        f'<definitions xmlns="{BPMN_NS}" id="d"><process id="P">'
        '<laneSet id="ls"/><task id="t" name="T"/>'
        '<textAnnotation id="a"/></process></definitions>',
        encoding="utf-8")
    g = read_bpmn(p)
    assert list(g.nodes) == ["t"]
    text = " ".join(g.warnings)
    assert "textAnnotation" in text and "laneSet" in text

import xml.etree.ElementTree as ET

import pytest

from bpmn2graphml.bpmn_reader import read_bpmn
from bpmn2graphml.bpmn_writer import (SPLIT_MARGIN, clip_to_rect, edge_points,
                                      write_merged_bpmn, write_split_bpmn)
from bpmn2graphml.graphml_reader import read_graphml
from bpmn2graphml.graphml_writer import write_graphml
from bpmn2graphml.merger import merge
from bpmn2graphml.model import BPMN_NS, BPMNDI_NS, DC_NS, DI_NS
from conftest import fixture_paths
from yed_sim import add_edge, add_task, delete_node, reconnect_edge, simulate_yed_save

START = "EBPM_21298a9b-4681-18a2-2219-eec70541056e"
DRAFT = "EBPM_873ebcef-da2c-52ff-4318-d7bb3b59cc1b"
STEMS = ["科技创新平台策划", "科技创新平台申报", "平台建设运行"]
B = f"{{{BPMN_NS}}}"


def pipeline(tmp_path, edit=None):
    merged, _ = merge([read_bpmn(p) for p in fixture_paths()])
    a, b = tmp_path / "a.graphml", tmp_path / "b.graphml"
    write_graphml(merged, a)
    simulate_yed_save(a, b, edit)
    return read_graphml(b)


def same_xml(a: str, b: str) -> bool:
    def eq(x, y):
        return (x.tag == y.tag and x.attrib == y.attrib
                and (x.text or "").strip() == (y.text or "").strip()
                and (x.tail or "").strip() == (y.tail or "").strip()
                and len(x) == len(y) and all(eq(c, d) for c, d in zip(x, y)))
    return eq(ET.fromstring(a), ET.fromstring(b))


def _semantic(g):
    nodes = {(n.id, n.bpmn_type, n.name) for n in g.nodes.values()}
    edges = {(e.id, e.source, e.target, e.name) for e in g.edges.values()}
    return nodes, edges


@pytest.fixture
def split(tmp_path):
    def run(edit=None):
        out = tmp_path / "split"
        warnings = write_split_bpmn(pipeline(tmp_path, edit), out)
        return out, warnings
    return run


@pytest.fixture
def merged_out(tmp_path):
    def run(edit=None):
        out = tmp_path / "merged.bpmn"
        warnings = write_merged_bpmn(pipeline(tmp_path, edit), out)
        return out, warnings
    return run


def test_clip_to_rect():
    rect = (0, 0, 100, 50)
    assert clip_to_rect((50, 25), (200, 25), rect) == pytest.approx((100, 25))
    assert clip_to_rect((50, 25), (50, -100), rect) == pytest.approx((50, 0))


def test_edge_points_with_ports():
    pts = edge_points((0, 0, 100, 50), (300, 0, 100, 50), [], (10, 0), (0, 0))
    assert pts[0] == pytest.approx((60, 25))
    assert pts[-1] == pytest.approx((300, 25))
    assert len(pts) == 2


def test_split_roundtrip_exact(split):
    out, _ = split()
    assert sorted(p.stem for p in out.glob("*.bpmn")) == sorted(STEMS)
    for original in fixture_paths():
        before, after = read_bpmn(original), read_bpmn(out / original.name)
        assert _semantic(after) == _semantic(before), original.stem
        for nid, n in before.nodes.items():
            o1, o2 = n.origins[0], after.nodes[nid].origins[0]
            assert o2.attrs == o1.attrs
            assert len(o2.children_xml) == len(o1.children_xml)
            assert all(same_xml(x, y) for x, y in zip(o1.children_xml, o2.children_xml))
    plan = read_bpmn(out / "科技创新平台策划.bpmn")
    assert plan.nodes["EBPM_5cd3a4cf-43f3-49b0-1962-356448c0579c"].bpmn_type == "subProcess"
    assert read_bpmn(out / "科技创新平台申报.bpmn").nodes["StartEvent_1"].bpmn_type == "startEvent"


def test_split_definitions_preserved(split):
    out, _ = split()
    path = out / "科技创新平台策划.bpmn"
    assert "<bpmn2:definitions" in path.read_text(encoding="utf-8")
    s = read_bpmn(path).sources[0]
    assert s.definitions_attrs["id"] == "sample-diagram"
    assert s.definitions_attrs["targetNamespace"] == "http://bpmn.io/schema/bpmn"
    assert s.process_attrs["id"] == "Process_1"
    assert read_bpmn(out / "科技创新平台申报.bpmn").sources[0].process_attrs["id"] == "Process_sb"


def test_split_coordinates_translated(split):
    out, _ = split()
    for p in out.glob("*.bpmn"):
        bounds = list(ET.parse(p).getroot().iter(f"{{{DC_NS}}}Bounds"))
        assert min(float(b.get("x")) for b in bounds) == SPLIT_MARGIN
        assert min(float(b.get("y")) for b in bounds) == SPLIT_MARGIN


def test_merged_output_valid(merged_out):
    out, _ = merged_out()
    g = read_bpmn(out)
    assert len(g.nodes) == 18 and len(g.edges) == 21
    root = ET.parse(out).getroot()
    process = root.find(B + "process")
    flows = {f.get("id"): f for f in process.findall(B + "sequenceFlow")}
    for f in flows.values():
        assert f.get("sourceRef") in g.nodes and f.get("targetRef") in g.nodes
    for el in process:
        if el.tag == B + "sequenceFlow":
            continue
        incoming = {i.text for i in el.findall(B + "incoming")}
        outgoing = {o.text for o in el.findall(B + "outgoing")}
        assert incoming == {k for k, f in flows.items() if f.get("targetRef") == el.get("id")}
        assert outgoing == {k for k, f in flows.items() if f.get("sourceRef") == el.get("id")}
    assert len(list(root.iter(f"{{{BPMNDI_NS}}}BPMNShape"))) == 18
    edges = list(root.iter(f"{{{BPMNDI_NS}}}BPMNEdge"))
    assert len(edges) == 21
    assert all(len(e.findall(f"{{{DI_NS}}}waypoint")) >= 2 for e in edges)
    assert g.nodes["EndEvent_1"].bpmn_type == "intermediateThrowEvent"


def test_merged_renormalizes_after_new_edges(tmp_path):
    edit = lambda t: add_edge(t, "eNew", DRAFT, START)
    g = pipeline(tmp_path, edit)
    write_merged_bpmn(g, tmp_path / "m.bpmn")
    assert read_bpmn(tmp_path / "m.bpmn").nodes[START].bpmn_type == "intermediateThrowEvent"
    write_split_bpmn(g, tmp_path / "s")
    plan = read_bpmn(tmp_path / "s" / "科技创新平台策划.bpmn")
    assert plan.nodes[START].bpmn_type == "startEvent"
    assert any((e.source, e.target) == (DRAFT, START) for e in plan.edges.values())


def test_split_new_node_assignment(split):
    def edit(t):
        add_task(t, "nX", "补充材料", "TASK_TYPE_USER", 0, 0)
        add_edge(t, "e1", "Task_1", "nX")
        add_edge(t, "e2", "nX", "Gateway_1")
    out, _ = split(edit)
    sb = read_bpmn(out / "科技创新平台申报.bpmn")
    (new,) = [n for n in sb.nodes.values() if n.name == "补充材料"]
    assert new.bpmn_type == "userTask"
    assert {(e.source, e.target) for e in sb.edges.values()} >= {("Task_1", new.id), (new.id, "Gateway_1")}
    for stem in ("科技创新平台策划", "平台建设运行"):
        assert all(n.name != "补充材料" for n in read_bpmn(out / f"{stem}.bpmn").nodes.values())


def test_split_cross_file_new_edge_warned(tmp_path):
    g = pipeline(tmp_path, lambda t: add_edge(t, "eX", DRAFT, "Task_1_2"))
    (new,) = [e for e in g.edges.values() if not e.origins and e.exported_source is None]
    warnings = write_split_bpmn(g, tmp_path / "s")
    assert any(new.id in w for w in warnings)
    for stem in STEMS:
        out = read_bpmn(tmp_path / "s" / f"{stem}.bpmn")
        assert new.id not in out.edges


def test_split_reconnected_edge(split):
    flow, new_target = "EBPM_96155149-f4ef-5e3a-7594-53ea337a137d", "EBPM_e68efe62-6af7-7c43-bf10-c0e40f4ef136"
    out, _ = split(lambda t: reconnect_edge(t, flow, new_target))
    assert read_bpmn(out / "科技创新平台策划.bpmn").edges[flow].target == new_target


def test_deleted_node_absent(tmp_path):
    gone = "EBPM_69e928b3-1b43-eb55-f45e-5b884aa5853b"
    g = pipeline(tmp_path, lambda t: delete_node(t, gone))
    write_merged_bpmn(g, tmp_path / "m.bpmn")
    write_split_bpmn(g, tmp_path / "s")
    for p in [tmp_path / "m.bpmn", *(tmp_path / "s").glob("*.bpmn")]:
        out = read_bpmn(p)
        assert gone not in out.nodes
        assert out.warnings == []
        for e in out.edges.values():
            assert e.source in out.nodes and e.target in out.nodes


def test_xml_declaration_double_quoted(split, merged_out):
    decl = b'<?xml version="1.0" encoding="UTF-8"?>'
    out, _ = split()
    m, _ = merged_out()
    for p in [m, *out.glob("*.bpmn")]:
        assert p.read_bytes().startswith(decl), p.name


def _gateway_files():
    from helpers import make_graph

    def mk(file):
        g = make_graph(file, [("Gateway_1", "exclusiveGateway", None), ("Task_1", "task", f"{file}1"),
                              ("Task_2", "task", f"{file}2")],
                       [("Flow_1", "Gateway_1", "Task_1", None), ("Flow_3", "Gateway_1", "Task_2", None)])
        g.nodes["Gateway_1"].origins[0].attrs["default"] = "Flow_3"
        return g
    return merge([mk("A"), mk("B")])[0]


def _defaults(path):
    return {el.get("id"): el.get("default")
            for el in ET.parse(path).getroot().iter(B + "exclusiveGateway")}


def test_merged_default_flow_follows_id_rename(tmp_path):
    write_merged_bpmn(_gateway_files(), tmp_path / "m.bpmn")
    assert _defaults(tmp_path / "m.bpmn") == {"Gateway_1": "Flow_3", "Gateway_1_2": "Flow_3_2"}


def test_deleted_default_flow_dropped(tmp_path):
    g = _gateway_files()
    del g.edges["Flow_3"]
    warnings = write_merged_bpmn(g, tmp_path / "m.bpmn")
    assert _defaults(tmp_path / "m.bpmn")["Gateway_1"] is None
    assert any("Flow_3" in w for w in warnings)
    warnings = write_split_bpmn(g, tmp_path / "s")
    assert _defaults(tmp_path / "s" / "A.bpmn") == {"Gateway_1": None}
    assert _defaults(tmp_path / "s" / "B.bpmn") == {"Gateway_1": "Flow_3"}
    assert any("Flow_3" in w for w in warnings)


def test_split_without_sources_data_keeps_files(tmp_path):
    def edit(tree):
        top = tree.getroot().find("{http://graphml.graphdrawing.org/xmlns}graph")
        for d in top.findall("{http://graphml.graphdrawing.org/xmlns}data"):
            top.remove(d)
    g = pipeline(tmp_path, edit)
    assert any("bpmn_sources" in w for w in g.warnings)
    write_split_bpmn(g, tmp_path / "s")
    assert sorted(p.stem for p in (tmp_path / "s").glob("*.bpmn")) == sorted(STEMS)
    for original in fixture_paths():
        before, after = read_bpmn(original), read_bpmn(tmp_path / "s" / original.name)
        assert _semantic(after) == _semantic(before)


def _b2g(path, node_id):
    from bpmn2graphml.properties import read_b2g_properties
    for el in ET.parse(path).getroot().iter():
        if el.get("id") == node_id:
            return read_b2g_properties([ET.tostring(c, encoding="unicode") for c in el])
    raise KeyError(node_id)


def test_merged_writes_source_property(merged_out):
    out, _ = merged_out()
    assert _b2g(out, "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e") == [
        ("来源流程", "科技创新平台策划"), ("来源流程", "科技创新平台申报")]
    assert _b2g(out, START) == [("来源流程", "科技创新平台策划")]
    assert _b2g(out, "StartEvent_1") == [("来源流程", "科技创新平台申报"), ("来源流程", "科技创新平台策划")]
    task = next(el for el in ET.parse(out).getroot().iter() if el.get("id") == "Task_1")
    ext = task.find(B + "extensionElements")
    assert ext.find("{http://example.com/ext}info") is not None


def test_merged_unions_b2g_from_all_origins(tmp_path):
    from bpmn2graphml.properties import with_b2g_properties
    from helpers import make_graph
    a = make_graph("A", [("a1", "task", "X")])
    b = make_graph("B", [("b1", "task", "X")])
    a.nodes["a1"].origins[0].children_xml = with_b2g_properties([], [("负责人", "张三")])
    b.nodes["b1"].origins[0].children_xml = with_b2g_properties([], [("负责人", "李四"), ("负责人", "张三")])
    merged, _ = merge([a, b])
    write_merged_bpmn(merged, tmp_path / "m.bpmn")
    assert _b2g(tmp_path / "m.bpmn", "a1") == [
        ("来源流程", "A"), ("来源流程", "B"), ("负责人", "张三"), ("负责人", "李四")]


def test_remerge_keeps_original_sources(tmp_path, merged_out):
    out, _ = merged_out()
    again, _ = merge([read_bpmn(out)])
    write_merged_bpmn(again, tmp_path / "again.bpmn")
    assert _b2g(tmp_path / "again.bpmn", "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e") == [
        ("来源流程", "科技创新平台策划"), ("来源流程", "科技创新平台申报")]


def test_new_node_has_no_properties(tmp_path):
    g = pipeline(tmp_path, lambda t: add_task(t, "nX", "新任务", None, 0, 0))
    write_merged_bpmn(g, tmp_path / "m.bpmn")
    (new,) = [n for n in g.nodes.values() if not n.origins]
    assert _b2g(tmp_path / "m.bpmn", new.id) == []


def test_split_output_has_no_b2g(split):
    from bpmn2graphml.properties import B2G_NS
    out, _ = split()
    for p in out.glob("*.bpmn"):
        assert B2G_NS not in p.read_text(encoding="utf-8")

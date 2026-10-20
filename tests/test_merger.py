import pytest

from bpmn2graphml.bpmn_reader import read_bpmn
from bpmn2graphml.merger import FILE_GAP, Expansion, MergeError, expansion_targets, merge
from conftest import fixture_paths
from helpers import make_graph

TASK = "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e"
SUB = "EBPM_5cd3a4cf-43f3-49b0-1962-356448c0579c"


@pytest.fixture
def merged():
    return merge([read_bpmn(p) for p in fixture_paths()])


def _by_name(graph, name):
    return [e for e in graph.edges.values() if e.name == name]


def test_fixtures_merge_counts(merged):
    g, _ = merged
    assert len(g.nodes) == 18
    assert len(g.edges) == 21


def test_same_name_merged_keeps_first_id(merged):
    g, report = merged
    assert [o.file for o in g.nodes[TASK].origins] == ["科技创新平台策划", "科技创新平台申报"]
    assert "Task_2" not in g.nodes
    (e,) = _by_name(g, "通过")
    assert e.target == TASK
    assert any(gr.kept_id == TASK and gr.name == "部门领导审核" for gr in report.groups)


def test_end_start_join_retyped(merged):
    g, report = merged
    n = g.nodes["EndEvent_1"]
    assert n.bpmn_type == "intermediateThrowEvent"
    assert [o.bpmn_type for o in n.origins] == ["endEvent", "startEvent"]
    assert ("EndEvent_1", "endEvent", "intermediateThrowEvent") in report.retyped


def test_subprocess_expanded(merged):
    g, report = merged
    assert SUB not in g.nodes
    start = g.nodes["StartEvent_1"]
    assert any(o.bpmn_type == "subProcess" and o.file == "科技创新平台策划"
               for o in start.origins)
    assert g.edges["EBPM_7a6586a2-9327-45b5-1efe-1a37c88d8586"].target == "StartEvent_1"
    assert start.bpmn_type == "intermediateThrowEvent"
    assert report.expansions == [
        Expansion(SUB, "科技创新平台策划", "科技创新平台申报", "StartEvent_1")]


def test_empty_names_never_merge(merged):
    g, _ = merged
    gateways = [n for n in g.nodes.values() if n.bpmn_type.endswith("Gateway")]
    assert len(gateways) == 5


def test_id_collision_renamed(merged):
    g, report = merged
    o = g.nodes["Task_1_2"].origins[0]
    assert (o.file, o.id) == ("平台建设运行", "Task_1")
    assert len(set(g.nodes)) == len(g.nodes)
    assert all(e.id == k for k, e in g.edges.items())
    assert all(n.id == k for k, n in g.nodes.items())
    assert any("Task_1" in w for w in report.warnings)


def test_edges_point_to_existing_nodes(merged):
    g, _ = merged
    for e in g.edges.values():
        assert e.source in g.nodes and e.target in g.nodes


def test_same_file_same_name_not_merged():
    a = make_graph("A", [("a1", "task", "X"), ("a2", "task", "X")])
    b = make_graph("B", [("b1", "task", "X")])
    g, report = merge([a, b])
    assert [o.id for o in g.nodes["a1"].origins] == ["a1", "b1"]
    assert "a2" in g.nodes and len(g.nodes["a2"].origins) == 1
    assert report.warnings


def test_type_mismatch_warns():
    a = make_graph("A", [("a1", "task", "X")])
    b = make_graph("B", [("b1", "exclusiveGateway", "X")])
    g, report = merge([a, b])
    assert len(g.nodes) == 1 and g.nodes["a1"].bpmn_type == "task"
    assert any("X" in w for w in report.warnings)


def test_expansion_outgoing_from_end_events():
    a = make_graph("A", [("s", "startEvent", "S"), ("sub", "subProcess", "B"), ("t", "task", "T")],
                   [("f1", "s", "sub", None), ("f2", "sub", "t", None)])
    b = make_graph("B", [("bs", "startEvent", "BS"), ("bx", "task", "BX"),
                         ("be1", "endEvent", "E1"), ("be2", "endEvent", "E2")],
                   [("g1", "bs", "bx", None), ("g2", "bx", "be1", None), ("g3", "bx", "be2", None)])
    g, report = merge([a, b])
    assert "sub" not in g.nodes
    assert [o.id for o in g.nodes["bs"].origins] == ["bs", "sub"]
    assert g.edges["f1"].target == "bs"
    assert g.edges["f2"].source == "be1" and g.edges["f2"].target == "t"
    extra = [e for e in g.edges.values() if e.source == "be2" and e.target == "t"]
    assert len(extra) == 1 and extra[0].origins == []
    assert report.expansions == [Expansion("sub", "A", "B", "bs")]


def test_expansion_fallback_without_events():
    a = make_graph("A", [("s", "startEvent", "S"), ("sub", "subProcess", "B"), ("t", "task", "T")],
                   [("f1", "s", "sub", None), ("f2", "sub", "t", None)])
    b = make_graph("B", [("x", "task", "X"), ("y", "task", "Y")], [("g1", "x", "y", None)])
    g, report = merge([a, b])
    assert [o.id for o in g.nodes["x"].origins] == ["x", "sub"]
    assert g.edges["f2"].source == "y"
    assert report.warnings


def test_duplicate_edges_combined():
    a = make_graph("A", [("p", "task", "P"), ("q", "task", "Q")], [("e1", "p", "q", "go")])
    b = make_graph("B", [("p2", "task", "P"), ("q2", "task", "Q")], [("e2", "p2", "q2", "go")])
    g, _ = merge([a, b])
    assert len(g.edges) == 1
    (e,) = g.edges.values()
    assert [o.id for o in e.origins] == ["e1", "e2"]


def test_duplicate_file_stem_raises():
    with pytest.raises(MergeError):
        merge([make_graph("A", [("a", "task", "X")]), make_graph("A", [("b", "task", "Y")])])


def test_report_text(merged):
    _, report = merged
    text = report.to_text()
    assert "部门领导审核" in text
    assert "科技创新平台申报" in text
    assert "EBPM_81ba6f70" in text


def test_positions_offset(merged):
    g, _ = merged
    assert all(n.bounds is not None for n in g.nodes.values())

    def only_from(file):
        return [n for n in g.nodes.values() if len(n.origins) == 1 and n.origins[0].file == file]

    right_1 = max(n.bounds[0] + n.bounds[2] for n in only_from("科技创新平台策划"))
    left_2 = min(n.bounds[0] for n in only_from("科技创新平台申报"))
    assert left_2 >= right_1 + FILE_GAP


def test_expansion_does_not_fold_caller_into_target():
    a = make_graph("A", [("as", "startEvent", "开始"), ("at", "task", "准备"),
                         ("sub", "subProcess", "B"), ("ag", "exclusiveGateway", ""),
                         ("ae", "endEvent", "结束")],
                   [("f1", "as", "at", None), ("f2", "at", "sub", None),
                    ("f3", "sub", "ag", None), ("f4", "ag", "ae", None)])
    b = make_graph("B", [("bs", "startEvent", "开始"), ("bt", "task", "做B"),
                         ("be", "endEvent", "结束")],
                   [("g1", "bs", "bt", None), ("g2", "bt", "be", None)])
    g, report = merge([a, b])
    assert g.nodes["as"].bpmn_type == "startEvent"
    assert g.nodes["ae"].bpmn_type == "endEvent"
    assert (g.edges["f1"].source, g.edges["f1"].target) == ("as", "at")
    assert (g.edges["f2"].target, g.edges["f3"].source, g.edges["f4"].target) == ("bs", "be", "ae")
    assert any("开始" in w for w in report.warnings)
    assert any("结束" in w for w in report.warnings)


def test_expansion_targets_fixtures():
    graphs = [read_bpmn(p) for p in fixture_paths()]
    assert expansion_targets(graphs) == {("科技创新平台策划", SUB): 1}


def test_expansion_targets_needs_target_selected():
    graphs = [read_bpmn(fixture_paths()[0])]
    assert expansion_targets(graphs) == {}

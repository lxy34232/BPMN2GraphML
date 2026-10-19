import re
import xml.etree.ElementTree as ET

import pytest

from bpmn2graphml.bpmn_reader import read_bpmn
from bpmn2graphml.graphml_reader import GraphmlReadError, read_graphml
from bpmn2graphml.graphml_writer import write_graphml
from bpmn2graphml.merger import merge
from conftest import fixture_paths
from yed_sim import (G, Y, add_edge, add_shape_node, add_task, duplicate_node,
                     find_edge, find_node, set_label, simulate_yed_save)

TASK = "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e"
EBPM_RE = r"^EBPM_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


@pytest.fixture(scope="module")
def merged():
    return merge([read_bpmn(p) for p in fixture_paths()])[0]


@pytest.fixture
def roundtrip(merged, tmp_path):
    def run(edit=None):
        a, b = tmp_path / "a.graphml", tmp_path / "b.graphml"
        write_graphml(merged, a)
        simulate_yed_save(a, b, edit)
        return read_graphml(b)
    return run


def _new_nodes(g):
    return [n for n in g.nodes.values() if not n.origins]


def test_roundtrip_identity(merged, roundtrip):
    g = roundtrip()
    assert list(g.nodes) == list(merged.nodes)
    for nid, n in merged.nodes.items():
        r = g.nodes[nid]
        assert (r.bpmn_type, r.name) == (n.bpmn_type, n.name)
        assert [o.to_dict() for o in r.origins] == [o.to_dict() for o in n.origins]
    assert list(g.edges) == list(merged.edges)
    for eid, e in merged.edges.items():
        r = g.edges[eid]
        assert (r.source, r.target, r.name) == (e.source, e.target, e.name)
        assert [o.to_dict() for o in r.origins] == [o.to_dict() for o in e.origins]
        assert (r.exported_source, r.exported_target) == (r.source, r.target)
    assert [s.to_dict() for s in g.sources] == [s.to_dict() for s in merged.sources]
    assert g.warnings == []


def test_geometry_read(roundtrip):
    def edit(tree):
        find_node(tree, TASK).find(f".//{Y}Geometry").set("x", "1000.0")
    assert roundtrip(edit).nodes[TASK].bounds[0] == 1000


def test_rename_applies_to_all_origins(roundtrip):
    g = roundtrip(lambda t: set_label(t, TASK, "部门负责人审核"))
    n = g.nodes[TASK]
    assert n.name == "部门负责人审核"
    assert [o.name for o in n.origins] == ["部门负责人审核", "部门负责人审核"]


def test_unrenamed_none_name_kept(roundtrip):
    assert roundtrip().nodes["Gateway_1"].name is None


def test_new_task_from_palette(roundtrip):
    g = roundtrip(lambda t: add_task(t, "nX", "新任务", "TASK_TYPE_USER", 10, 10))
    (n,) = _new_nodes(g)
    assert n.bpmn_type == "userTask" and n.name == "新任务" and n.origins == []
    assert re.match(EBPM_RE, n.id)
    assert n.bounds == (10, 10, 85, 55)


def test_new_plain_shape_is_task(roundtrip):
    (n,) = _new_nodes(roundtrip(lambda t: add_shape_node(t, "nS", "普通方框")))
    assert n.bpmn_type == "task" and n.name == "普通方框"


def test_new_edge_sequence_flow(roundtrip):
    g = roundtrip(lambda t: add_edge(t, "eX", TASK, "EBPM_873ebcef-da2c-52ff-4318-d7bb3b59cc1b"))
    (e,) = [e for e in g.edges.values() if not e.origins and e.exported_source is None]
    assert re.match(EBPM_RE, e.id)
    assert (e.source, e.target) == (TASK, "EBPM_873ebcef-da2c-52ff-4318-d7bb3b59cc1b")


def test_duplicate_bpmn_id_from_copy_paste(roundtrip):
    g = roundtrip(lambda t: duplicate_node(t, TASK, "copy1"))
    assert len(g.nodes[TASK].origins) == 2
    (n,) = _new_nodes(g)
    assert re.match(EBPM_RE, n.id) and n.name == "部门领导审核"
    assert any("重复" in w for w in g.warnings)


def test_waypoints_and_ports(roundtrip):
    eid = "EBPM_ea9d4cad-60ee-bf38-be14-817d219d55e7"

    def edit(tree):
        path = find_edge(tree, eid).find(f".//{Y}Path")
        path.set("sx", "10.0")
        ET.SubElement(path, Y + "Point", x="1.0", y="2.0")
        ET.SubElement(path, Y + "Point", x="3.0", y="4.0")
    e = roundtrip(edit).edges[eid]
    assert e.source_port == (10, 0)
    assert e.waypoints == [(1, 2), (3, 4)]


def test_group_nodes_ignored(roundtrip):
    def edit(tree):
        top = tree.getroot().find(G + "graph")
        group = ET.SubElement(top, G + "node", {"id": "grp", "yfiles.foldertype": "group"})
        inner = ET.SubElement(group, G + "graph", id="grp:", edgedefault="directed")
        for bid in (TASK, "EBPM_873ebcef-da2c-52ff-4318-d7bb3b59cc1b"):
            n = find_node(tree, bid)
            top.remove(n)
            inner.append(n)
    g = roundtrip(edit)
    assert TASK in g.nodes and "EBPM_873ebcef-da2c-52ff-4318-d7bb3b59cc1b" in g.nodes
    assert len(g.nodes) == 18


def test_invalid_graphml_raises(tmp_path):
    p = tmp_path / "bad.graphml"
    p.write_text("<<<", encoding="utf-8")
    with pytest.raises(GraphmlReadError, match="bad.graphml"):
        read_graphml(p)

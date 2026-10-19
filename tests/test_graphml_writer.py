import json
import xml.etree.ElementTree as ET

import pytest

from bpmn2graphml.bpmn_reader import read_bpmn
from bpmn2graphml.graphml_writer import write_graphml
from bpmn2graphml.merger import merge
from bpmn2graphml.yed_styles import (SUPPORTED_TYPES, bpmn_type_from_yed,
                                     yed_style_for)
from conftest import fixture_paths

G = "{http://graphml.graphdrawing.org/xmlns}"
Y = "{http://www.yworks.com/xml/graphml}"
BPMN_CONFIGS = {"com.yworks.bpmn.Activity.withShadow", "com.yworks.bpmn.Gateway.withShadow",
                "com.yworks.bpmn.Event.withShadow"}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    merged, _ = merge([read_bpmn(p) for p in fixture_paths()])
    path = tmp_path_factory.mktemp("w") / "m.graphml"
    write_graphml(merged, path)
    return ET.parse(path).getroot()


def _keys(root):
    return {(k.get("for"), k.get("attr.name")): k.get("id") for k in root.iter(G + "key")}


def _data(el, key_id):
    for d in el.findall(G + "data"):
        if d.get("key") == key_id:
            return d.text
    return None


def _node_by_bpmn_id(root, bpmn_id):
    kid = _keys(root)[("node", "bpmn_id")]
    return next(n for n in root.iter(G + "node") if _data(n, kid) == bpmn_id)


def _props(el):
    return {p.get("name"): p.get("value") for p in el.iter(Y + "Property")}


def test_style_roundtrip_table():
    for t in SUPPORTED_TYPES:
        if t == "callActivity":
            continue
        s = yed_style_for(t)
        assert bpmn_type_from_yed(s.configuration, {n: v for _, n, v in s.properties}) == t, t


def test_unknown_shape_is_task():
    assert bpmn_type_from_yed("com.yworks.flowchart.process", {}) == "task"
    assert bpmn_type_from_yed("", {}) == "task"


def test_writer_emits_yed_bpmn_nodes(written):
    for n in written.iter(G + "node"):
        gn = n.find(f".//{Y}GenericNode")
        assert gn is not None and gn.get("configuration") in BPMN_CONFIGS
    gw = _node_by_bpmn_id(written, "EBPM_2783b857-45a5-40e5-84d6-3b98c770a0b8")
    assert _props(gw)["com.yworks.bpmn.type"] == "GATEWAY_TYPE_DATA_BASED_EXCLUSIVE"
    task = _node_by_bpmn_id(written, "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e")
    assert _props(task)["com.yworks.bpmn.taskType"] == "TASK_TYPE_MANUAL"
    assert task.find(f".//{Y}NodeLabel").text == "部门领导审核"


def test_writer_custom_keys(written):
    keys = _keys(written)
    for k in [("node", "bpmn_id"), ("node", "bpmn_type"), ("node", "bpmn_origins"),
              ("edge", "bpmn_id"), ("edge", "bpmn_origins"), ("edge", "bpmn_endpoints"),
              ("graph", "bpmn_sources")]:
        assert k in keys, k
    graph = written.find(G + "graph")
    sources = json.loads(_data(graph, keys[("graph", "bpmn_sources")]))
    assert [s["file"] for s in sources] == ["科技创新平台策划", "科技创新平台申报", "平台建设运行"]


def test_task_width_fits_label(written):
    n = _node_by_bpmn_id(written, "EBPM_645ad92f-c58a-1a3e-74c7-49b27bb2ef7c")
    assert float(n.find(f".//{Y}Geometry").get("width")) >= 14 * 13 + 20


def test_edges_sequence_flow(written):
    labels = []
    for e in written.iter(G + "edge"):
        ge = e.find(f".//{Y}GenericEdge")
        assert ge.get("configuration") == "com.yworks.bpmn.Connection"
        assert _props(ge)["com.yworks.bpmn.type"] == "CONNECTION_TYPE_SEQUENCE_FLOW"
        lab = ge.find(Y + "EdgeLabel")
        if lab is not None:
            labels.append(lab.text)
    assert "审核不通过" in labels

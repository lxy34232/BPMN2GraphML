"""测试用：模拟 yEd 中的编辑与保存（保存时 yEd 会把 key/节点/边的 id 改写为 d0/n0/e0）。

编辑在改写 id 之前执行，所以编辑时节点的 yEd id 等于 bpmn id。
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

G = "{http://graphml.graphdrawing.org/xmlns}"
Y = "{http://www.yworks.com/xml/graphml}"


def _register() -> None:
    ET.register_namespace("", G[1:-1])
    ET.register_namespace("y", Y[1:-1])
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")


def _key_id(tree: ET.ElementTree, for_: str, name: str) -> str:
    for k in tree.getroot().iter(G + "key"):
        if k.get("for") == for_ and (k.get("attr.name") == name or k.get("yfiles.type") == name):
            return k.get("id")
    raise KeyError(name)


def _top_graph(tree: ET.ElementTree) -> ET.Element:
    return tree.getroot().find(G + "graph")


def _parent_map(tree: ET.ElementTree) -> dict[ET.Element, ET.Element]:
    return {c: p for p in tree.getroot().iter() for c in p}


def _by_data(tree, tag, for_, bpmn_id) -> ET.Element:
    kid = _key_id(tree, for_, "bpmn_id")
    for el in tree.getroot().iter(G + tag):
        for d in el.findall(G + "data"):
            if d.get("key") == kid and d.text == bpmn_id:
                return el
    raise KeyError(bpmn_id)


def find_node(tree: ET.ElementTree, bpmn_id: str) -> ET.Element:
    return _by_data(tree, "node", "node", bpmn_id)


def find_edge(tree: ET.ElementTree, bpmn_id: str) -> ET.Element:
    return _by_data(tree, "edge", "edge", bpmn_id)


def set_label(tree: ET.ElementTree, bpmn_id: str, text: str) -> None:
    node = find_node(tree, bpmn_id)
    node.find(f".//{Y}NodeLabel").text = text


def delete_node(tree: ET.ElementTree, bpmn_id: str) -> None:
    node = find_node(tree, bpmn_id)
    parents = _parent_map(tree)
    parents[node].remove(node)
    for e in list(tree.getroot().iter(G + "edge")):
        if node.get("id") in (e.get("source"), e.get("target")):
            parents[e].remove(e)


def _graphics(parent: ET.Element, tree: ET.ElementTree, for_: str) -> ET.Element:
    return ET.SubElement(parent, G + "data", key=_key_id(tree, for_, f"{for_}graphics"))


def add_task(tree: ET.ElementTree, yed_id: str, label: str, task_type: str | None,
             x: float, y: float) -> None:
    node = ET.SubElement(_top_graph(tree), G + "node", id=yed_id)
    gn = ET.SubElement(_graphics(node, tree, "node"), Y + "GenericNode",
                       configuration="com.yworks.bpmn.Activity.withShadow")
    ET.SubElement(gn, Y + "Geometry", height="55.0", width="85.0", x=str(x), y=str(y))
    ET.SubElement(gn, Y + "NodeLabel").text = label
    sp = ET.SubElement(gn, Y + "StyleProperties")
    ET.SubElement(sp, Y + "Property", {"class": "com.yworks.yfiles.bpmn.view.BPMNTypeEnum",
                                       "name": "com.yworks.bpmn.type",
                                       "value": "ACTIVITY_TYPE_STATELESS_TASK_PLAIN"})
    if task_type:
        ET.SubElement(sp, Y + "Property", {"class": "com.yworks.yfiles.bpmn.view.TaskTypeEnum",
                                           "name": "com.yworks.bpmn.taskType", "value": task_type})


def add_shape_node(tree: ET.ElementTree, yed_id: str, label: str) -> None:
    node = ET.SubElement(_top_graph(tree), G + "node", id=yed_id)
    sn = ET.SubElement(_graphics(node, tree, "node"), Y + "ShapeNode")
    ET.SubElement(sn, Y + "Geometry", height="30.0", width="80.0", x="0.0", y="0.0")
    ET.SubElement(sn, Y + "NodeLabel").text = label
    ET.SubElement(sn, Y + "Shape", type="rectangle")


def add_edge(tree: ET.ElementTree, yed_id: str, source_yed: str, target_yed: str) -> None:
    edge = ET.SubElement(_top_graph(tree), G + "edge", id=yed_id, source=source_yed,
                         target=target_yed)
    ge = ET.SubElement(_graphics(edge, tree, "edge"), Y + "GenericEdge",
                       configuration="com.yworks.bpmn.Connection")
    ET.SubElement(ge, Y + "Path", sx="0.0", sy="0.0", tx="0.0", ty="0.0")
    sp = ET.SubElement(ge, Y + "StyleProperties")
    ET.SubElement(sp, Y + "Property", {"class": "com.yworks.yfiles.bpmn.view.BPMNTypeEnum",
                                       "name": "com.yworks.bpmn.type",
                                       "value": "CONNECTION_TYPE_SEQUENCE_FLOW"})


def reconnect_edge(tree: ET.ElementTree, edge_bpmn_id: str, new_target_bpmn_id: str) -> None:
    find_edge(tree, edge_bpmn_id).set("target", find_node(tree, new_target_bpmn_id).get("id"))


def duplicate_node(tree: ET.ElementTree, bpmn_id: str, new_yed_id: str) -> None:
    clone = copy.deepcopy(find_node(tree, bpmn_id))
    clone.set("id", new_yed_id)
    _top_graph(tree).append(clone)


def simulate_yed_save(src: Path, dst: Path,
                      edit: Callable[[ET.ElementTree], None] | None = None) -> None:
    _register()
    tree = ET.parse(src)
    if edit:
        edit(tree)
    root = tree.getroot()
    key_map = {k.get("id"): f"d{i}" for i, k in enumerate(root.iter(G + "key"))}
    for k in root.iter(G + "key"):
        k.set("id", key_map[k.get("id")])
    for d in root.iter(G + "data"):
        d.set("key", key_map[d.get("key")])
    node_map = {n.get("id"): f"n{i}" for i, n in enumerate(root.iter(G + "node"))}
    for n in root.iter(G + "node"):
        n.set("id", node_map[n.get("id")])
    for i, e in enumerate(root.iter(G + "edge")):
        e.set("id", f"e{i}")
        e.set("source", node_map[e.get("source")])
        e.set("target", node_map[e.get("target")])
    tree.write(dst, encoding="UTF-8", xml_declaration=True)

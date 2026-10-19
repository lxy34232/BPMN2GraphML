"""BPMN 2.0 XML → Graph（单文件）。按命名空间 URI 解析，与前缀无关。"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import (BPMN_NS, BPMNDI_NS, DC_NS, EXPANDABLE_TYPES,
                    FLOW_NODE_TYPES, Edge, Graph, Node, Origin, SourceInfo)

_SKIP_CHILDREN = {"incoming", "outgoing"}
_NODE_SKIP_ATTRS = {"id", "name"}
_FLOW_SKIP_ATTRS = {"id", "name", "sourceRef", "targetRef"}


class BpmnReadError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ns(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _collect_namespaces(path: Path) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    for _event, (prefix, uri) in ET.iterparse(path, events=("start-ns",)):
        namespaces.setdefault(prefix, uri)
    return namespaces


def _children_xml(el: ET.Element) -> list[str]:
    return [ET.tostring(c, encoding="unicode").strip()
            for c in el if _local(c.tag) not in _SKIP_CHILDREN]


def read_bpmn(path: str | os.PathLike) -> Graph:
    path = Path(path)
    file = path.stem
    try:
        namespaces = _collect_namespaces(path)
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise BpmnReadError(f"{path.name}: 无法解析 XML（{e}）") from e
    if root.tag != f"{{{BPMN_NS}}}definitions":
        raise BpmnReadError(f"{path.name}: 不是 BPMN 2.0 文件（根元素为 {_local(root.tag)}）")

    graph = Graph()
    processes = root.findall(f"{{{BPMN_NS}}}process")
    if not processes:
        raise BpmnReadError(f"{path.name}: 文件中没有 process")
    if len(processes) > 1:
        graph.warnings.append(f"{file}: 含 {len(processes)} 个 process，将合并为一个处理")

    order = 0
    for process in processes:
        for el in process:
            kind = _local(el.tag)
            if _ns(el.tag) != BPMN_NS:
                graph.warnings.append(f"{file}: 忽略非 BPMN 元素 {kind}")
                continue
            el_id = el.get("id", "")
            if kind in FLOW_NODE_TYPES:
                origin = Origin(
                    file=file, id=el_id, bpmn_type=kind, name=el.get("name"),
                    attrs={k: v for k, v in el.attrib.items() if k not in _NODE_SKIP_ATTRS},
                    children_xml=_children_xml(el), order=order)
                expandable = kind in EXPANDABLE_TYPES and not any(
                    _local(c.tag) in FLOW_NODE_TYPES for c in el)
                graph.nodes[el_id] = Node(el_id, kind, origin.name, [origin],
                                          expandable=expandable)
            elif kind == "sequenceFlow":
                origin = Origin(
                    file=file, id=el_id, bpmn_type=kind, name=el.get("name"),
                    attrs={k: v for k, v in el.attrib.items() if k not in _FLOW_SKIP_ATTRS},
                    children_xml=_children_xml(el), order=order,
                    source_id=el.get("sourceRef"), target_id=el.get("targetRef"))
                graph.edges[el_id] = Edge(el_id, origin.source_id or "", origin.target_id or "",
                                          origin.name, [origin])
            else:
                graph.warnings.append(f"{file}: 暂不支持 {kind}（id={el_id}），已忽略")
                continue
            order += 1

    for edge in list(graph.edges.values()):
        if edge.source not in graph.nodes or edge.target not in graph.nodes:
            graph.warnings.append(f"{file}: 连线 {edge.id} 的端点不存在，已忽略")
            del graph.edges[edge.id]

    diagram = root.find(f"{{{BPMNDI_NS}}}BPMNDiagram")
    plane = diagram.find(f"{{{BPMNDI_NS}}}BPMNPlane") if diagram is not None else None
    for shape in root.iter(f"{{{BPMNDI_NS}}}BPMNShape"):
        node = graph.nodes.get(shape.get("bpmnElement", ""))
        b = shape.find(f"{{{DC_NS}}}Bounds")
        if node is not None and b is not None:
            node.bounds = tuple(float(b.get(k, 0)) for k in ("x", "y", "width", "height"))

    graph.sources.append(SourceInfo(
        file=file,
        namespaces=namespaces,
        definitions_attrs=dict(root.attrib),
        process_attrs=dict(processes[0].attrib),
        diagram_id=diagram.get("id", "BPMNDiagram_1") if diagram is not None else "BPMNDiagram_1",
        plane_id=plane.get("id", "BPMNPlane_1") if plane is not None else "BPMNPlane_1",
    ))
    return graph

"""Graph → BPMN 2.0（语义 + BPMNDI）。

合并模式：一个扁平流程，使用合并后的 ID 和类型。
拆分模式：按原文件拆回，原 ID / 类型 / 属性 / 子元素不变，只更新布局。
"""
from __future__ import annotations

import copy
import math
import os
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .merger import normalize_events
from .model import (BPMN_NS, BPMNDI_NS, DC_NS, DI_NS, XSI_NS, Bounds, Graph,
                    Point, SourceInfo)
from .yed_styles import default_size
from .xmlutil import write_xml

SPLIT_MARGIN = 50.0
_FLOW_REF_ATTRS = ("default",)   # 节点上引用连线 ID 的属性
_FIXED_NS = {"bpmn2": BPMN_NS, "bpmndi": BPMNDI_NS, "dc": DC_NS, "di": DI_NS, "xsi": XSI_NS}
_LAST = math.inf


@dataclass
class _NodeEl:
    tag: str
    id: str
    name: str | None
    attrs: dict[str, str]
    children: list[str]
    bounds: Bounds
    order: float = _LAST


@dataclass
class _FlowEl:
    id: str
    source: str
    target: str
    name: str | None
    attrs: dict[str, str]
    children: list[str]
    points: list[Point] = field(default_factory=list)
    order: float = _LAST


def _center(b: Bounds) -> Point:
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def clip_to_rect(center: Point, toward: Point, bounds: Bounds) -> Point:
    """从矩形中心朝 toward 方向，求与矩形边框的交点。"""
    cx, cy = center
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return center
    tx = (bounds[2] / 2) / abs(dx) if dx else math.inf
    ty = (bounds[3] / 2) / abs(dy) if dy else math.inf
    t = min(tx, ty)
    return (cx + dx * t, cy + dy * t)


def edge_points(src_bounds: Bounds, tgt_bounds: Bounds, bends: list[Point],
                source_port: Point, target_port: Point) -> list[Point]:
    sc, tc = _center(src_bounds), _center(tgt_bounds)
    if source_port != (0, 0):
        start = (sc[0] + source_port[0], sc[1] + source_port[1])
    else:
        start = clip_to_rect(sc, bends[0] if bends else tc, src_bounds)
    if target_port != (0, 0):
        end = (tc[0] + target_port[0], tc[1] + target_port[1])
    else:
        end = clip_to_rect(tc, bends[-1] if bends else sc, tgt_bounds)
    return [start, *bends, end]


def _bounds_of(graph: Graph, node_id: str) -> Bounds:
    n = graph.nodes[node_id]
    return n.bounds or (0.0, 0.0, *default_size(n.bpmn_type))


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _register(namespaces: dict[str, str]) -> None:
    for prefix, uri in _FIXED_NS.items():
        ET.register_namespace(prefix, uri)
    fixed_uris = set(_FIXED_NS.values())
    for prefix, uri in namespaces.items():
        if prefix and prefix not in _FIXED_NS and uri not in fixed_uris:
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                pass


def _write(source: SourceInfo, namespaces: dict[str, str], nodes: list[_NodeEl],
           flows: list[_FlowEl], path: str | os.PathLike) -> None:
    _register(namespaces)
    b = f"{{{BPMN_NS}}}"
    root = ET.Element(b + "definitions", source.definitions_attrs)
    process = ET.SubElement(root, b + "process", source.process_attrs)
    process_id = source.process_attrs.get("id", "Process_1")

    for n in nodes:
        el = ET.SubElement(process, b + n.tag, id=n.id)
        if n.name is not None:
            el.set("name", n.name)
        el.attrib.update(n.attrs)
        el.extend(ET.fromstring(x) for x in n.children)
        for f in flows:
            if f.target == n.id:
                ET.SubElement(el, b + "incoming").text = f.id
        for f in flows:
            if f.source == n.id:
                ET.SubElement(el, b + "outgoing").text = f.id
    for f in flows:
        el = ET.SubElement(process, b + "sequenceFlow", id=f.id, sourceRef=f.source,
                           targetRef=f.target)
        if f.name is not None:
            el.set("name", f.name)
        el.attrib.update(f.attrs)
        el.extend(ET.fromstring(x) for x in f.children)

    diagram = ET.SubElement(root, f"{{{BPMNDI_NS}}}BPMNDiagram", id=source.diagram_id)
    plane = ET.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", id=source.plane_id,
                          bpmnElement=process_id)
    for n in nodes:
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape", id=f"{n.id}_di", bpmnElement=n.id)
        x, y, w, h = n.bounds
        ET.SubElement(shape, f"{{{DC_NS}}}Bounds", x=_fmt(x), y=_fmt(y), width=_fmt(w), height=_fmt(h))
    for f in flows:
        edge = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNEdge", id=f"{f.id}_di", bpmnElement=f.id)
        for px, py in f.points:
            ET.SubElement(edge, f"{{{DI_NS}}}waypoint", x=_fmt(px), y=_fmt(py))

    write_xml(root, path)


def _fix_flow_refs(nodes: list[_NodeEl], resolve, warnings: list[str]) -> None:
    """把节点上引用连线的属性映射到实际写出的连线 ID；目标连线不存在时移除该属性。"""
    for n in nodes:
        for attr in _FLOW_REF_ATTRS:
            old = n.attrs.get(attr)
            if old is None:
                continue
            new = resolve(n, old)
            if new is None:
                del n.attrs[attr]
                warnings.append(f"{n.id} 的 {attr} 指向的连线 {old} 已不存在，已移除该属性")
            else:
                n.attrs[attr] = new


def _all_namespaces(graph: Graph) -> dict[str, str]:
    merged: dict[str, str] = {}
    for s in graph.sources:
        for prefix, uri in s.namespaces.items():
            merged.setdefault(prefix, uri)
    return merged


def write_merged_bpmn(graph: Graph, path: str | os.PathLike) -> list[str]:
    g = copy.deepcopy(graph)
    normalize_events(g)
    warnings: list[str] = []
    nodes, node_file = [], {}
    for n in g.nodes.values():
        o = n.origins[0] if n.origins else None
        nodes.append(_NodeEl(n.bpmn_type, n.id, n.name, dict(o.attrs) if o else {},
                             list(o.children_xml) if o else [], _bounds_of(g, n.id)))
        node_file[n.id] = o.file if o else None
    # (文件, 原连线 id) → 合并后的连线 id（ID 冲突改名后引用要跟着改）
    flow_ids = {(o.file, o.id): e.id for e in g.edges.values() for o in e.origins}
    _fix_flow_refs(nodes, lambda n, old: flow_ids.get((node_file[n.id], old)), warnings)
    flows = []
    for e in g.edges.values():
        o = e.origins[0] if e.origins else None
        points = edge_points(_bounds_of(g, e.source), _bounds_of(g, e.target), e.waypoints,
                             e.source_port, e.target_port)
        flows.append(_FlowEl(e.id, e.source, e.target, e.name, dict(o.attrs) if o else {},
                             list(o.children_xml) if o else [], points))
    _write(g.sources[0], _all_namespaces(g), nodes, flows, path)
    return warnings


def _home_files(graph: Graph, files: list[str]) -> dict[str, str]:
    """用户新增节点 → 归属文件：相邻节点所属文件中票数最多者（平局按输入顺序）。"""
    homes: dict[str, str] = {}
    for n in graph.nodes.values():
        if n.origins:
            continue
        votes: Counter[str] = Counter()
        for e in graph.edges.values():
            other = e.target if e.source == n.id else e.source if e.target == n.id else None
            if other is not None:
                votes.update({o.file for o in graph.nodes[other].origins})
        homes[n.id] = (max(files, key=lambda f: (votes[f], -files.index(f)))
                       if votes else files[0])
    return homes


def write_split_bpmn(graph: Graph, out_dir: str | os.PathLike) -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    files = [s.file for s in graph.sources]
    homes = _home_files(graph, files)
    written_new_edges: set[str] = set()

    for source in graph.sources:
        f = source.file
        nodes: list[_NodeEl] = []
        first_in_file: dict[str, str] = {}     # 合并节点 id → 本文件中的原 id
        drawn: dict[str, str] = {}             # 本文件元素 id → 绘制它的合并节点 id
        for n in graph.nodes.values():
            bounds = _bounds_of(graph, n.id)
            for o in n.origins:
                if o.file == f:
                    nodes.append(_NodeEl(o.bpmn_type, o.id, o.name, dict(o.attrs),
                                         list(o.children_xml), bounds, o.order))
                    first_in_file.setdefault(n.id, o.id)
                    drawn[o.id] = n.id
            if not n.origins and homes[n.id] == f:
                nodes.append(_NodeEl(n.bpmn_type, n.id, n.name, {}, [], bounds))
                first_in_file[n.id] = n.id
                drawn[n.id] = n.id

        flows: list[_FlowEl] = []

        def add_flow(fid, src, tgt, name, attrs, children, edge, order=_LAST):
            if src not in drawn or tgt not in drawn:
                warnings.append(f"「{f}」中连线 {fid} 的端点不在该文件中，已跳过")
                return
            exact = drawn[src] == edge.source and drawn[tgt] == edge.target
            points = edge_points(_bounds_of(graph, drawn[src]), _bounds_of(graph, drawn[tgt]),
                                 edge.waypoints if exact else [],
                                 edge.source_port if exact else (0, 0),
                                 edge.target_port if exact else (0, 0))
            flows.append(_FlowEl(fid, src, tgt, name, attrs, children, points, order))

        for e in graph.edges.values():
            if e.origins:
                for o in e.origins:
                    if o.file != f:
                        continue
                    src = o.source_id if e.source == e.exported_source else first_in_file.get(e.source)
                    tgt = o.target_id if e.target == e.exported_target else first_in_file.get(e.target)
                    if src is None or tgt is None:
                        warnings.append(f"连线 {o.id} 在 yEd 中改接到「{f}」以外的节点，拆分时已从「{f}」中跳过")
                        continue
                    add_flow(o.id, src, tgt, o.name, dict(o.attrs), list(o.children_xml), e, o.order)
            elif e.exported_source is None and e.source in first_in_file and e.target in first_in_file:
                add_flow(e.id, first_in_file[e.source], first_in_file[e.target], e.name, {}, [], e)
                written_new_edges.add(e.id)

        written = {fl.id for fl in flows}
        _fix_flow_refs(nodes, lambda n, old: old if old in written else None, warnings)
        if nodes:
            dx = SPLIT_MARGIN - min(n.bounds[0] for n in nodes)
            dy = SPLIT_MARGIN - min(n.bounds[1] for n in nodes)
            for n in nodes:
                x, y, w, h = n.bounds
                n.bounds = (x + dx, y + dy, w, h)
            for fl in flows:
                fl.points = [(px + dx, py + dy) for px, py in fl.points]
        nodes.sort(key=lambda n: n.order)
        flows.sort(key=lambda fl: fl.order)
        _write(source, source.namespaces, nodes, flows, out_dir / f"{f}.bpmn")

    for e in graph.edges.values():
        if not e.origins and e.exported_source is None and e.id not in written_new_edges:
            warnings.append(f"新增连线 {e.id} 跨越不同文件，拆分时未写入任何文件")
    return warnings

"""yEd 保存的 graphml → Graph。

yEd 保存时会改写 key/节点/边的 id，因此 key 按 attr.name / yfiles.type 识别，
元素按 bpmn_id 数据识别。没有 bpmn 数据的元素视为用户在 yEd 中新增的元素。
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from .graphml_writer import GRAPHML_NS, Y_NS
from .merger import new_id
from .model import Edge, Graph, Node, Origin, SourceInfo
from .yed_styles import bpmn_type_from_yed

_G = f"{{{GRAPHML_NS}}}"
_Y = f"{{{Y_NS}}}"


class GraphmlReadError(Exception):
    pass


def _default_source() -> SourceInfo:
    return SourceInfo("merged", {}, {"id": "Definitions_1"}, {"id": "Process_1"},
                      "BPMNDiagram_1", "BPMNPlane_1")


def _label_text(graphics: ET.Element | None, tag: str) -> str:
    if graphics is None:
        return ""
    texts = [(lab.text or "").strip() for lab in graphics.iter(_Y + tag)]
    return "\n".join(t for t in texts if t)


def _apply_name(label: str, origins: list[Origin]) -> str | None:
    """标签与原名称不同即视为改名，写回与原名称相同的 origin；未改名时保留原值（可能为 None）。

    名称不同的 origin（例如被展开吸收的子流程，其名称是目标文件名）不受影响。
    """
    stored = origins[0].name if origins else None
    old = (stored or "").strip()
    if label == old:
        return stored
    for o in origins:
        if (o.name or "").strip() == old:
            o.name = label
    return label if label or origins else None


def read_graphml(path: str | os.PathLike) -> Graph:
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise GraphmlReadError(f"{path.name}: 无法解析 XML（{e}）") from e
    if root.tag != _G + "graphml":
        raise GraphmlReadError(f"{path.name}: 不是 graphml 文件")

    keys: dict[tuple[str, str], str] = {}
    for k in root.iter(_G + "key"):
        name = k.get("attr.name") or k.get("yfiles.type")
        if name:
            keys[(k.get("for", ""), name)] = k.get("id", "")

    def data(el: ET.Element, for_: str, name: str) -> ET.Element | None:
        kid = keys.get((for_, name))
        if kid is None:
            return None
        return next((d for d in el.findall(_G + "data") if d.get("key") == kid), None)

    def text(el: ET.Element, for_: str, name: str) -> str | None:
        d = data(el, for_, name)
        return d.text if d is not None and d.text else None

    graph = Graph()
    top = root.find(_G + "graph")
    if top is None:
        raise GraphmlReadError(f"{path.name}: 文件中没有 graph")
    raw_sources = text(top, "graph", "bpmn_sources")

    used: set[str] = set()
    yed_to_id: dict[str, str] = {}

    def claim(bpmn_id: str | None, what: str) -> tuple[str, bool]:
        """返回 (id, 是否沿用原元素)。缺失或重复的 bpmn_id 分配新 id。"""
        if bpmn_id and bpmn_id not in used:
            used.add(bpmn_id)
            return bpmn_id, True
        if bpmn_id:
            graph.warnings.append(f"{what} {bpmn_id} 重复（可能是 yEd 中复制粘贴产生），副本按新元素处理")
        nid = new_id()
        used.add(nid)
        return nid, False

    for el in root.iter(_G + "node"):
        if el.get("yfiles.foldertype") or el.find(_G + "graph") is not None:
            continue
        gdata = data(el, "node", "nodegraphics")
        graphics = gdata[0] if gdata is not None and len(gdata) else None
        nid, kept = claim(text(el, "node", "bpmn_id"), "节点")
        origins = ([Origin.from_dict(o) for o in json.loads(text(el, "node", "bpmn_origins") or "[]")]
                   if kept else [])
        bpmn_type = text(el, "node", "bpmn_type")
        if not bpmn_type:
            props = {} if graphics is None else {
                p.get("name"): p.get("value") for p in graphics.iter(_Y + "Property")}
            configuration = "" if graphics is None else graphics.get("configuration", "")
            bpmn_type = bpmn_type_from_yed(configuration, props)
        geo = None if graphics is None else graphics.find(_Y + "Geometry")
        bounds = None if geo is None else tuple(
            float(geo.get(k, 0)) for k in ("x", "y", "width", "height"))
        name = _apply_name(_label_text(graphics, "NodeLabel"), origins)
        graph.nodes[nid] = Node(nid, bpmn_type, name, origins, bounds=bounds)
        yed_to_id[el.get("id", "")] = nid

    for el in root.iter(_G + "edge"):
        src, tgt = yed_to_id.get(el.get("source", "")), yed_to_id.get(el.get("target", ""))
        if src is None or tgt is None:
            graph.warnings.append(f"连线 {el.get('id')} 的端点不是流程节点（例如组节点），已忽略")
            continue
        gdata = data(el, "edge", "edgegraphics")
        graphics = gdata[0] if gdata is not None and len(gdata) else None
        eid, kept = claim(text(el, "edge", "bpmn_id"), "连线")
        origins = ([Origin.from_dict(o) for o in json.loads(text(el, "edge", "bpmn_origins") or "[]")]
                   if kept else [])
        endpoints = json.loads(text(el, "edge", "bpmn_endpoints") or "null") if kept else None
        edge = Edge(eid, src, tgt, _apply_name(_label_text(graphics, "EdgeLabel"), origins), origins)
        if endpoints:
            edge.exported_source, edge.exported_target = endpoints
        p = None if graphics is None else graphics.find(_Y + "Path")
        if p is not None:
            edge.source_port = (float(p.get("sx", 0)), float(p.get("sy", 0)))
            edge.target_port = (float(p.get("tx", 0)), float(p.get("ty", 0)))
            edge.waypoints = [(float(pt.get("x", 0)), float(pt.get("y", 0)))
                              for pt in p.findall(_Y + "Point")]
        graph.edges[eid] = edge

    if raw_sources:
        graph.sources = [SourceInfo.from_dict(s) for s in json.loads(raw_sources)]
    else:
        graph.sources = _sources_from_origins(graph)
    return graph


def _sources_from_origins(graph: Graph) -> list[SourceInfo]:
    """bpmn_sources 数据丢失时，按 origin 中出现的文件重建（属性取默认值），保证拆分不丢元素。"""
    files: list[str] = []
    for el in [*graph.nodes.values(), *graph.edges.values()]:
        for o in el.origins:
            if o.file not in files:
                files.append(o.file)
    if not files:
        return [_default_source()]
    graph.warnings.append("graphml 中缺少 bpmn_sources 数据，已按节点来源重建文件信息"
                          "（definitions/process 属性使用默认值）")
    return [SourceInfo(f, {}, {"id": f"Definitions_{i}"}, {"id": f"Process_{i}"},
                       "BPMNDiagram_1", "BPMNPlane_1") for i, f in enumerate(files, 1)]

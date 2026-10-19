"""Graph → yEd graphml（使用 yEd 自带 BPMN 图形，并以自定义数据键携带全部 BPMN 信息）。"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

from .model import Graph
from .yed_styles import CONNECTION, SEQUENCE_FLOW, TYPE_CLASS, TYPE_PROP, yed_style_for

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"
Y_NS = "http://www.yworks.com/xml/graphml"
YED_NS = "http://www.yworks.com/xml/yed/3"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

# (for, attr.name, key id)
CUSTOM_KEYS = (
    ("graph", "bpmn_sources", "g_bpmn_sources"),
    ("node", "bpmn_id", "n_bpmn_id"),
    ("node", "bpmn_type", "n_bpmn_type"),
    ("node", "bpmn_origins", "n_bpmn_origins"),
    ("edge", "bpmn_id", "e_bpmn_id"),
    ("edge", "bpmn_origins", "e_bpmn_origins"),
    ("edge", "bpmn_endpoints", "e_bpmn_endpoints"),
)
NODE_GRAPHICS = "d6"
EDGE_GRAPHICS = "d10"

_LABEL_ATTRS = {
    "alignment": "center", "autoSizePolicy": "content", "fontFamily": "Dialog",
    "fontSize": "12", "fontStyle": "plain", "hasBackgroundColor": "false",
    "hasLineColor": "false", "textColor": "#000000", "visible": "true",
}


def _g(tag: str) -> str:
    return f"{{{GRAPHML_NS}}}{tag}"


def _y(tag: str) -> str:
    return f"{{{Y_NS}}}{tag}"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _data(parent: ET.Element, key: str, text: str | None = None) -> ET.Element:
    d = ET.SubElement(parent, _g("data"), key=key)
    if text is not None:
        d.text = text
    return d


def _num(v: float) -> str:
    return repr(float(v))


def _style_properties(parent: ET.Element, props) -> None:
    sp = ET.SubElement(parent, _y("StyleProperties"))
    for cls, name, value in props:
        ET.SubElement(sp, _y("Property"), {"class": cls, "name": name, "value": value})


def write_graphml(graph: Graph, path: str | os.PathLike) -> None:
    ET.register_namespace("", GRAPHML_NS)
    ET.register_namespace("y", Y_NS)
    ET.register_namespace("yed", YED_NS)
    ET.register_namespace("xsi", XSI)

    root = ET.Element(_g("graphml"), {
        f"{{{XSI}}}schemaLocation":
            f"{GRAPHML_NS} http://www.yworks.com/xml/schema/graphml/1.1/ygraphml.xsd"})
    for for_, name, kid in CUSTOM_KEYS:
        ET.SubElement(root, _g("key"), {"attr.name": name, "attr.type": "string",
                                        "for": for_, "id": kid})
    ET.SubElement(root, _g("key"), {"for": "node", "id": NODE_GRAPHICS, "yfiles.type": "nodegraphics"})
    ET.SubElement(root, _g("key"), {"for": "edge", "id": EDGE_GRAPHICS, "yfiles.type": "edgegraphics"})

    g = ET.SubElement(root, _g("graph"), edgedefault="directed", id="G")
    _data(g, "g_bpmn_sources", _json([s.to_dict() for s in graph.sources]))

    for node in graph.nodes.values():
        style = yed_style_for(node.bpmn_type)
        el = ET.SubElement(g, _g("node"), id=node.id)
        _data(el, "n_bpmn_id", node.id)
        _data(el, "n_bpmn_type", node.bpmn_type)
        _data(el, "n_bpmn_origins", _json([o.to_dict() for o in node.origins]))
        gn = ET.SubElement(_data(el, NODE_GRAPHICS), _y("GenericNode"),
                           configuration=style.configuration)
        x, y, w, h = node.bounds or (0.0, 0.0, *style.default_size)
        name = node.name or ""
        if style.label_inside:
            w = max(w, 14 * len(name) + 20)
        ET.SubElement(gn, _y("Geometry"), height=_num(h), width=_num(w), x=_num(x), y=_num(y))
        ET.SubElement(gn, _y("Fill"), color="#FFFFFFE6", color2="#D4D4D4CC", transparent="false")
        ET.SubElement(gn, _y("BorderStyle"), color=style.border_color, type="line", width="1.0")
        if name:
            placement = ({"modelName": "internal", "modelPosition": "c"} if style.label_inside
                         else {"modelName": "sandwich", "modelPosition": "s"})
            label = ET.SubElement(gn, _y("NodeLabel"), {**_LABEL_ATTRS, **placement})
            label.text = name
        _style_properties(gn, style.properties)

    for edge in graph.edges.values():
        el = ET.SubElement(g, _g("edge"), id=edge.id, source=edge.source, target=edge.target)
        _data(el, "e_bpmn_id", edge.id)
        _data(el, "e_bpmn_origins", _json([o.to_dict() for o in edge.origins]))
        _data(el, "e_bpmn_endpoints", _json([edge.source, edge.target]))
        ge = ET.SubElement(_data(el, EDGE_GRAPHICS), _y("GenericEdge"), configuration=CONNECTION)
        ET.SubElement(ge, _y("Path"), sx="0.0", sy="0.0", tx="0.0", ty="0.0")
        ET.SubElement(ge, _y("LineStyle"), color="#000000", type="line", width="1.0")
        ET.SubElement(ge, _y("Arrows"), source="none", target="delta")
        if edge.name:
            label = ET.SubElement(ge, _y("EdgeLabel"), {
                **_LABEL_ATTRS, "modelName": "centered", "modelPosition": "center",
                "preferredPlacement": "anywhere"})
            label.text = edge.name
        _style_properties(ge, ((TYPE_CLASS, TYPE_PROP, SEQUENCE_FLOW),))

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(path, encoding="UTF-8", xml_declaration=True)

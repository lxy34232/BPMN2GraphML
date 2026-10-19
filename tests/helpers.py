"""测试用：手工构造单文件 Graph。"""
from bpmn2graphml.model import (EXPANDABLE_TYPES, Edge, Graph, Node, Origin,
                                SourceInfo)


def make_graph(file: str,
               nodes: list[tuple[str, str, str | None]],
               edges: list[tuple[str, str, str, str | None]] = ()) -> Graph:
    g = Graph()
    order = 0
    for nid, kind, name in nodes:
        o = Origin(file, nid, kind, name, {}, [], order)
        g.nodes[nid] = Node(nid, kind, name, [o], expandable=kind in EXPANDABLE_TYPES)
        order += 1
    for eid, src, tgt, name in edges:
        o = Origin(file, eid, "sequenceFlow", name, {}, [], order, src, tgt)
        g.edges[eid] = Edge(eid, src, tgt, name, [o])
        order += 1
    g.sources.append(SourceInfo(file, {}, {"id": f"Def_{file}"}, {"id": f"P_{file}"},
                                "BPMNDiagram_1", "BPMNPlane_1"))
    return g

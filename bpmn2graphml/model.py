"""贯穿全程的内部图模型。

每个 Node / Edge 都带着它所代表的全部原始 BPMN 元素（Origin），
因此合并不会丢失信息，拆分模式可以精确还原每个原文件。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

FLOW_NODE_TYPES = frozenset({
    "task", "manualTask", "userTask", "serviceTask", "scriptTask", "sendTask",
    "receiveTask", "businessRuleTask", "subProcess", "callActivity",
    "startEvent", "endEvent", "intermediateThrowEvent", "intermediateCatchEvent",
    "exclusiveGateway", "parallelGateway", "inclusiveGateway",
    "eventBasedGateway", "complexGateway",
})
EXPANDABLE_TYPES = frozenset({"subProcess", "callActivity"})

Bounds = tuple[float, float, float, float]
Point = tuple[float, float]


@dataclass
class Origin:
    """一个原始 BPMN 元素的完整记录。"""
    file: str
    id: str
    bpmn_type: str
    name: str | None
    attrs: dict[str, str]
    children_xml: list[str]
    order: int
    source_id: str | None = None
    target_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Origin":
        return Origin(**d)


@dataclass
class Node:
    id: str
    bpmn_type: str
    name: str | None
    origins: list[Origin]
    bounds: Bounds | None = None
    expandable: bool = False


@dataclass
class Edge:
    id: str
    source: str
    target: str
    name: str | None
    origins: list[Origin]
    waypoints: list[Point] = field(default_factory=list)
    source_port: Point = (0.0, 0.0)
    target_port: Point = (0.0, 0.0)
    exported_source: str | None = None
    exported_target: str | None = None


@dataclass
class SourceInfo:
    file: str
    namespaces: dict[str, str]
    definitions_attrs: dict[str, str]
    process_attrs: dict[str, str]
    diagram_id: str
    plane_id: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SourceInfo":
        return SourceInfo(**d)


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    sources: list[SourceInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

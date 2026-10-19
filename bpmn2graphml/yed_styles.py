"""BPMN 元素类型 ⇄ yEd 自带 BPMN 图形样式（yEd 3.25 经典 graphml 格式）。

取值来自 yEd 自带示例和 yed.jar 中的枚举；改动只需维护此文件。
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIVITY = "com.yworks.bpmn.Activity.withShadow"
GATEWAY = "com.yworks.bpmn.Gateway.withShadow"
EVENT = "com.yworks.bpmn.Event.withShadow"
CONNECTION = "com.yworks.bpmn.Connection"

TYPE_PROP = "com.yworks.bpmn.type"
TASK_TYPE_PROP = "com.yworks.bpmn.taskType"
CHAR_PROP = "com.yworks.bpmn.characteristic"
TYPE_CLASS = "com.yworks.yfiles.bpmn.view.BPMNTypeEnum"
TASK_TYPE_CLASS = "com.yworks.yfiles.bpmn.view.TaskTypeEnum"
CHAR_CLASS = "com.yworks.yfiles.bpmn.view.EventCharEnum"
SEQUENCE_FLOW = "CONNECTION_TYPE_SEQUENCE_FLOW"

_ICON_PROPS = (
    ("java.awt.Color", "com.yworks.bpmn.icon.line.color", "#000000"),
    ("java.awt.Color", "com.yworks.bpmn.icon.fill", "#ffffff"),
    ("java.awt.Color", "com.yworks.bpmn.icon.fill2", "#d4d4d4"),
)

_TASK_TYPES = {
    "task": "TASK_TYPE_ABSTRACT",
    "manualTask": "TASK_TYPE_MANUAL",
    "userTask": "TASK_TYPE_USER",
    "serviceTask": "TASK_TYPE_SERVICE",
    "scriptTask": "TASK_TYPE_SCRIPT",
    "sendTask": "TASK_TYPE_SEND",
    "receiveTask": "TASK_TYPE_RECEIVE",
    "businessRuleTask": "TASK_TYPE_BUSINESS_RULE",
}
_GATEWAY_TYPES = {
    "exclusiveGateway": "GATEWAY_TYPE_DATA_BASED_EXCLUSIVE",
    "parallelGateway": "GATEWAY_TYPE_PARALLEL",
    "inclusiveGateway": "GATEWAY_TYPE_INCLUSIVE",
    "eventBasedGateway": "GATEWAY_TYPE_EVENT_BASED_EXCLUSIVE",
    "complexGateway": "GATEWAY_TYPE_COMPLEX",
}
_EVENT_CHARS = {
    "startEvent": "EVENT_CHARACTERISTIC_START",
    "endEvent": "EVENT_CHARACTERISTIC_END",
    "intermediateThrowEvent": "EVENT_CHARACTERISTIC_INTERMEDIATE_THROWING",
    "intermediateCatchEvent": "EVENT_CHARACTERISTIC_INTERMEDIATE_CATCHING",
}
_EVENT_BORDERS = {
    "startEvent": "#27AE27",
    "endEvent": "#C0392B",
    "intermediateThrowEvent": "#888888",
    "intermediateCatchEvent": "#888888",
}

SUPPORTED_TYPES: tuple[str, ...] = (
    *_TASK_TYPES, "subProcess", "callActivity", *_GATEWAY_TYPES, *_EVENT_CHARS)


@dataclass(frozen=True)
class YedStyle:
    configuration: str
    properties: tuple[tuple[str, str, str], ...]
    default_size: tuple[float, float]
    border_color: str
    label_inside: bool


def yed_style_for(bpmn_type: str) -> YedStyle:
    if bpmn_type in ("subProcess", "callActivity"):
        props = ((TYPE_CLASS, TYPE_PROP, "ACTIVITY_TYPE_SUBPROCESS_PLAIN"),)
        return YedStyle(ACTIVITY, props + _ICON_PROPS, (140.0, 67.0), "#123EA2", True)
    if bpmn_type in _GATEWAY_TYPES:
        props = ((TYPE_CLASS, TYPE_PROP, _GATEWAY_TYPES[bpmn_type]),)
        return YedStyle(GATEWAY, props + _ICON_PROPS, (50.0, 50.0), "#E38B00", False)
    if bpmn_type in _EVENT_CHARS:
        props = ((TYPE_CLASS, TYPE_PROP, "EVENT_TYPE_PLAIN"),
                 (CHAR_CLASS, CHAR_PROP, _EVENT_CHARS[bpmn_type]))
        return YedStyle(EVENT, props + _ICON_PROPS, (36.0, 36.0), _EVENT_BORDERS[bpmn_type], False)
    task_type = _TASK_TYPES.get(bpmn_type, "TASK_TYPE_ABSTRACT")
    props = ((TYPE_CLASS, TYPE_PROP, "ACTIVITY_TYPE_STATELESS_TASK_PLAIN"),
             (TASK_TYPE_CLASS, TASK_TYPE_PROP, task_type))
    return YedStyle(ACTIVITY, props + _ICON_PROPS, (140.0, 67.0), "#123EA2", True)


def default_size(bpmn_type: str) -> tuple[float, float]:
    return yed_style_for(bpmn_type).default_size


def bpmn_type_from_yed(configuration: str, props: dict[str, str]) -> str:
    """根据 yEd 节点的 configuration 和样式属性推断 BPMN 类型；未知图形一律视为 task。"""
    kind = props.get(TYPE_PROP, "")
    if configuration.startswith("com.yworks.bpmn.Activity"):
        if "SUBPROCESS" in kind:
            return "subProcess"
        reverse = {v: k for k, v in _TASK_TYPES.items()}
        return reverse.get(props.get(TASK_TYPE_PROP, ""), "task")
    if configuration.startswith("com.yworks.bpmn.Gateway"):
        reverse = {v: k for k, v in _GATEWAY_TYPES.items()}
        return reverse.get(kind, "exclusiveGateway")
    if configuration.startswith("com.yworks.bpmn.Event"):
        char = props.get(CHAR_PROP, "")
        if char.startswith("EVENT_CHARACTERISTIC_START"):
            return "startEvent"
        if char == "EVENT_CHARACTERISTIC_END":
            return "endEvent"
        if char == "EVENT_CHARACTERISTIC_INTERMEDIATE_CATCHING":
            return "intermediateCatchEvent"
        return "intermediateThrowEvent"
    return "task"

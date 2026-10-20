"""节点属性表：从 BPMN 导出表格，以及把表格导回 BPMN（就地改写）。

表格第一列是节点名称，其后每列一个属性；按名称（去首尾空白）匹配节点。
就地改写时直接修改原文件的 XML，只替换节点的 b2g:properties，其它内容保持不变。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .bpmn_reader import BpmnReadError, read_bpmn
from .merger import expansion_targets
from .model import BPMN_NS, Graph
from .properties import (SOURCE_PROP, TYPE_LABELS, Prop, node_b2g_properties,
                         type_label)
from .table_io import write_table

NAME_HEADER = "节点名称"
FILE_HEADER = "所在文件"
TYPE_HEADER = "元素类型"
READONLY_HEADERS = (FILE_HEADER, TYPE_HEADER, SOURCE_PROP)
SEP = "；"

_CSV_HINT = "提示：CSV 在 Excel 中打开再保存，可能把“001”变成“1”、把“1-2”变成日期；建议使用 .xlsx。"


class PropTableError(Exception):
    pass


@dataclass
class NodeRef:
    file: str
    id: str
    name: str
    bpmn_type: str
    element: ET.Element


@dataclass
class BpmnDoc:
    path: Path
    file: str
    root: ET.Element
    namespaces: list[tuple[str, str]]
    nodes: list[NodeRef]
    graph: Graph = field(repr=False, default=None)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_docs(paths: list[Path]) -> list[BpmnDoc]:
    docs: list[BpmnDoc] = []
    seen: set[str] = set()
    for path in map(Path, paths):
        if path.stem in seen:
            raise PropTableError(f"文件名重复：{path.stem}（每个文件名只能出现一次）")
        seen.add(path.stem)
        try:
            namespaces = [pu for _e, pu in ET.iterparse(path, events=("start-ns",))]
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
            root = ET.parse(path, parser).getroot()
            graph = read_bpmn(path)
        except (ET.ParseError, OSError) as e:
            raise PropTableError(f"{path.name}: 无法解析 XML（{e}）") from e
        except BpmnReadError as e:
            raise PropTableError(str(e)) from e
        nodes = [NodeRef(path.stem, el.get("id", ""), (el.get("name") or "").strip(),
                         _local(el.tag), el)
                 for el in root.iter()
                 if isinstance(el.tag, str) and el.tag.startswith(f"{{{BPMN_NS}}}")
                 and _local(el.tag) in TYPE_LABELS]
        docs.append(BpmnDoc(path, path.stem, root, namespaces, nodes, graph))
    return docs


def group_rows(docs: list[BpmnDoc]) -> tuple[dict[str, list[NodeRef]], list[str]]:
    """行名 → 节点列表（按首次出现顺序）；以及空子流程归并到开始事件的说明。"""
    by_key = {(n.file, n.id): n for d in docs for n in d.nodes}
    fold: dict[tuple[str, str], str] = {}
    folded: list[str] = []
    for (file, node_id), ti in expansion_targets([d.graph for d in docs]).items():
        target = docs[ti]
        start = next((m for m in target.graph.nodes.values() if m.bpmn_type == "startEvent"), None)
        entry = by_key.get((target.file, start.id)) if start else None
        sub = by_key.get((file, node_id))
        if entry is None or not entry.name or sub is None:
            continue
        fold[(file, node_id)] = entry.name
        folded.append(f"「{sub.name}」（{file}）归入「{entry.name}」")
    rows: dict[str, list[NodeRef]] = {}
    for d in docs:
        for n in d.nodes:
            key = fold.get((n.file, n.id), n.name)
            if key:
                rows.setdefault(key, []).append(n)
    return rows, folded


def _unique(values) -> list[str]:
    out: list[str] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _prop_map(props: list[Prop], skip=READONLY_HEADERS) -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {}
    for k, v in props:
        if k not in skip:
            out.setdefault(k, set()).add(v)
    return {k: frozenset(v) for k, v in out.items()}


@dataclass
class ExportSummary:
    path: Path
    rows: int
    columns: list[str]
    conflicts: list[str]
    folded: list[str]

    def to_text(self) -> str:
        lines = [f"已导出：{self.path}",
                 f"共 {self.rows} 行，{len(self.columns)} 个属性列："
                 + ("、".join(self.columns) or "（无）"),
                 "", "== 同名节点取值不一致（导回后会统一为表中的取值）=="]
        lines += self.conflicts or ["（无）"]
        lines += ["", "== 归入开始事件那一行的子流程 =="]
        lines += self.folded or ["（无）"]
        if Path(self.path).suffix.lower() == ".csv":
            lines += ["", _CSV_HINT]
        return "\n".join(lines)


def export_table(bpmn_paths: list[Path], out: Path) -> ExportSummary:
    docs = load_docs(bpmn_paths)
    rows, folded = group_rows(docs)
    in_table = {id(n) for refs in rows.values() for n in refs}
    props = {id(n): node_b2g_properties(n.element) for d in docs for n in d.nodes}

    has_source, columns = False, []
    for d in docs:
        for n in d.nodes:
            if id(n) not in in_table:
                continue
            for k, _v in props[id(n)]:
                if k == SOURCE_PROP:
                    has_source = True
                elif k not in READONLY_HEADERS and k not in columns:
                    columns.append(k)

    header = [NAME_HEADER, FILE_HEADER, TYPE_HEADER] + ([SOURCE_PROP] if has_source else [])
    value_cols = ([SOURCE_PROP] if has_source else []) + columns
    table = [header + columns]
    conflicts: list[str] = []
    for name, refs in rows.items():
        values: dict[str, list[str]] = {}
        for n in refs:
            for k, v in props[id(n)]:
                if v not in values.setdefault(k, []):
                    values[k].append(v)
        table.append([name,
                      SEP.join(_unique(n.file for n in refs)),
                      SEP.join(_unique(type_label(n.bpmn_type) for n in refs))]
                     + [SEP.join(values.get(c, [])) for c in value_cols])
        maps = [_prop_map(props[id(n)]) for n in refs]
        if any(m != maps[0] for m in maps[1:]):
            conflicts.append(name)

    write_table(Path(out), table, frozenset(range(1, len(header))))
    return ExportSummary(Path(out), len(table) - 1, columns, conflicts, folded)

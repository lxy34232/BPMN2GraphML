"""节点属性表：从 BPMN 导出表格，以及把表格导回 BPMN（就地改写）。

表格第一列是节点名称，其后每列一个属性；按名称（去首尾空白）匹配节点。
就地改写时直接修改原文件的 XML，只替换节点的 b2g:properties，其它内容保持不变。
"""
from __future__ import annotations

import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .bpmn_reader import BpmnReadError, read_bpmn
from .merger import expansion_targets
from .model import BPMN_NS, Graph
from .properties import (B2G_NS, SOURCE_PROP, TYPE_LABELS, Prop, node_b2g_properties,
                         set_node_b2g_properties, type_label)
from .table_io import TableError, read_table, write_table
from .xmlutil import write_xml

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


# —— 导入 ——

class _Abort(Exception):
    pass


def import_report_path_for(table: Path) -> Path:
    table = Path(table)
    return table.with_name(table.stem + ".import-report.txt")


@dataclass
class ImportReport:
    table: Path
    ok: bool = False
    error: str | None = None
    changed_files: list[tuple[Path, int]] = field(default_factory=list)
    backups: list[Path] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    untouched: list[str] = field(default_factory=list)
    same_file_dupes: list[str] = field(default_factory=list)
    folded: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"表格：{self.table}"]
        if not self.ok:
            return "\n".join(lines + [f"导入已中止：{self.error}", "未修改任何 BPMN 文件。"])
        lines.append(f"导入成功：修改了 {len(self.changed_files)} 个文件。")

        def section(title: str, items: list[str]) -> None:
            lines.extend(["", f"== {title} =="] + (items or ["（无）"]))

        section("修改的文件", [f"{p}：更新 {n} 个节点（备份：{b}）"
                               for (p, n), b in zip(self.changed_files, self.backups)])
        section("表中找不到对应节点的名称", self.not_found)
        section("表中没有的节点（未改动）", self.untouched)
        section("同一文件中同名、一并写入的节点", self.same_file_dupes)
        section("归入开始事件那一行的子流程", self.folded)
        section("属性变化", self.changes)
        section("被忽略的列（只读参考列）", self.ignored_columns)
        return "\n".join(lines)


def _split(cell: str) -> list[str]:
    return _unique(v.strip() for v in re.split(r"[;；]", cell) if v.strip())


def _parse_table(rows: list[list[str]]):
    """返回（属性列名，[(行名, 每列取值列表)]，被忽略的列）。"""
    if not rows:
        raise _Abort("表格是空的")
    header = [h.strip() for h in rows[0]]
    body = rows[1:]
    cols: list[tuple[int, str]] = []
    ignored: list[str] = []
    for i in range(1, len(header)):
        h = header[i]
        if h in READONLY_HEADERS:
            ignored.append(h)
        elif not h:
            if any(r[i].strip() for r in body):
                raise _Abort(f"第 {i + 1} 列表头为空，但下面有数据")
        elif h in [name for _, name in cols]:
            raise _Abort(f"表头「{h}」重复")
        else:
            cols.append((i, h))
    if not cols:
        raise _Abort("表中没有属性列。按“以表格为准”，导入这张表会清空所有节点的属性，因此已中止；"
                     "如果确实要清空，请保留表头、只把格子清空")
    records: list[tuple[str, list[list[str]]]] = []
    seen: dict[str, int] = {}
    for excel_row, r in enumerate(body, start=2):
        cells = [c.strip() for c in r]
        name = cells[0] if cells else ""
        if not name:
            if any(cells[i] for i, _ in cols):
                raise _Abort(f"第 {excel_row} 行没有节点名称，但填写了属性")
            continue
        if name in seen:
            raise _Abort(f"节点名称「{name}」在表中出现了多行（第 {seen[name]}、{excel_row} 行）")
        seen[name] = excel_row
        records.append((name, [_split(cells[i]) for i, _ in cols]))
    if not records:
        raise _Abort("表中没有数据行")
    return [name for _, name in cols], records, ignored


def _ordered(props: list[Prop]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in props:
        out.setdefault(k, []).append(v)
    return out


def _describe(old: list[Prop], new: list[Prop]) -> str:
    om, nm = _ordered(old), _ordered(new)
    parts = [f"新增 {k}={'、'.join(v)}" for k, v in nm.items() if k not in om]
    parts += [f"修改 {k}：{'、'.join(om[k])} → {'、'.join(v)}"
              for k, v in nm.items() if k in om and set(om[k]) != set(v)]
    parts += [f"删除 {k}" for k in om if k not in nm]
    return "；".join(parts)


def _save(doc: BpmnDoc) -> Path:
    backup = doc.path.with_name(doc.path.name + ".bak")
    shutil.copy2(doc.path, backup)
    for prefix, uri in doc.namespaces:
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
    ET.register_namespace("b2g", B2G_NS)
    tmp = doc.path.with_name(doc.path.name + ".tmp")
    write_xml(doc.root, tmp)
    os.replace(tmp, doc.path)
    return backup


def _apply(table: Path, bpmn_paths: list[Path], report: ImportReport) -> None:
    try:
        rows = read_table(table)
    except TableError as e:
        raise _Abort(str(e)) from e
    columns, records, report.ignored_columns = _parse_table(rows)
    try:
        docs = load_docs(bpmn_paths)
    except PropTableError as e:
        raise _Abort(str(e)) from e
    groups, report.folded = group_rows(docs)

    changed: dict[str, int] = {}
    for name, values in records:
        refs = groups.get(name)
        if not refs:
            report.not_found.append(name)
            continue
        files = [n.file for n in refs]
        report.same_file_dupes += [f"{name}（{f}）" for f in _unique(files) if files.count(f) > 1]
        table_props = [(c, v) for c, vs in zip(columns, values) for v in vs]
        described: list[tuple[str, str]] = []
        for n in refs:
            old = node_b2g_properties(n.element)
            new = [p for p in old if p[0] in READONLY_HEADERS] + table_props
            if _prop_map(new, skip=()) == _prop_map(old, skip=()):
                continue
            set_node_b2g_properties(n.element, new)
            changed[n.file] = changed.get(n.file, 0) + 1
            described.append((n.file, _describe(old, new)))
        if len(described) == len(refs) and len({d for _, d in described}) == 1:
            report.changes.append(f"{name}：{described[0][1]}")
        else:
            report.changes += [f"{name}（{f}）：{d}" for f, d in described]
    table_names = {name for name, _ in records}
    report.untouched = [name for name in groups if name not in table_names]

    for doc in docs:
        if doc.file in changed:
            report.backups.append(_save(doc))
            report.changed_files.append((doc.path, changed[doc.file]))


def import_table(table: Path, bpmn_paths: list[Path]) -> ImportReport:
    """把属性表导回 BPMN（就地改写）。数据问题不抛异常，返回 ok=False 的报告。"""
    table = Path(table)
    report = ImportReport(table)
    try:
        _apply(table, [Path(p) for p in bpmn_paths], report)
        report.ok = True
    except _Abort as e:
        report.error = str(e)
    import_report_path_for(table).write_text(report.to_text(), encoding="utf-8")
    return report

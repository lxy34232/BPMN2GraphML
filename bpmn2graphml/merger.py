"""多个单文件 Graph → 一个合并后的 Graph + 合并报告。

规则（按顺序）：空子流程展开 → 跨文件同名合并 → 折叠并保证 ID 唯一
→ 连线去重 → 事件规范化。任何原始元素都作为 Origin 保留在合并节点上。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .model import Edge, Graph, Node, Origin
from .yed_styles import default_size

FILE_GAP = 200.0

Key = tuple[str, str]  # (file, 原 id)


class MergeError(Exception):
    pass


@dataclass
class MergeGroup:
    name: str
    kept_id: str
    members: list[tuple[str, str]]


@dataclass
class Expansion:
    subprocess_id: str
    file: str
    target_file: str
    entry_id: str


@dataclass
class MergeReport:
    groups: list[MergeGroup] = field(default_factory=list)
    expansions: list[Expansion] = field(default_factory=list)
    retyped: list[tuple[str, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["== 同名节点合并 =="]
        for g in self.groups:
            members = "，".join(f"{f}:{i}" for f, i in g.members)
            lines.append(f"「{g.name}」保留 {g.kept_id} ← {members}")
        if not self.groups:
            lines.append("（无）")
        lines.append("")
        lines.append("== 子流程展开 ==")
        for e in self.expansions:
            lines.append(f"{e.file}:{e.subprocess_id} → 展开为文件「{e.target_file}」，入口 {e.entry_id}")
        if not self.expansions:
            lines.append("（无）")
        lines.append("")
        lines.append("== 类型调整 ==")
        for nid, old, new in self.retyped:
            lines.append(f"{nid}: {old} → {new}")
        if not self.retyped:
            lines.append("（无）")
        lines.append("")
        lines.append("== 警告 ==")
        lines.extend(self.warnings or ["（无）"])
        return "\n".join(lines) + "\n"


def new_id() -> str:
    return f"EBPM_{uuid.uuid4()}"


def _family(bpmn_type: str) -> str:
    return "event" if bpmn_type.endswith("Event") else bpmn_type


def normalize_events(graph: Graph) -> list[tuple[str, str, str]]:
    """开始事件有入线、结束事件有出线 → intermediateThrowEvent。原地修改。"""
    has_in = {e.target for e in graph.edges.values()}
    has_out = {e.source for e in graph.edges.values()}
    changed = []
    for n in graph.nodes.values():
        if (n.bpmn_type == "startEvent" and n.id in has_in) or \
                (n.bpmn_type == "endEvent" and n.id in has_out):
            changed.append((n.id, n.bpmn_type, "intermediateThrowEvent"))
            n.bpmn_type = "intermediateThrowEvent"
    return changed


@dataclass
class _EdgeRec:
    key: Key | None          # None = 合并过程中合成的连线
    src: Key
    tgt: Key
    name: str | None
    origins: list[Origin]


def _unique(base: str, used: set[str], report: MergeReport, what: str) -> str:
    result, n = base, 2
    while result in used:
        result = f"{base}_{n}"
        n += 1
    if result != base:
        report.warnings.append(f"ID 冲突：{what} {base} 在合并结果中改为 {result}")
    used.add(result)
    return result


def _layout_positions(graphs: list[Graph]) -> dict[Key, tuple[float, float, float, float]]:
    """每个文件沿用原坐标，按文件横向错开；没有坐标的节点放进网格。"""
    positions: dict[Key, tuple[float, float, float, float]] = {}
    offset = 0.0
    for g in graphs:
        file = g.sources[0].file
        with_bounds = [n.bounds for n in g.nodes.values() if n.bounds]
        min_x = min((b[0] for b in with_bounds), default=0.0)
        k = 0
        for n in g.nodes.values():
            if n.bounds:
                x, y, w, h = n.bounds
                positions[(file, n.id)] = (x - min_x + offset, y, w, h)
            else:
                w, h = default_size(n.bpmn_type)
                positions[(file, n.id)] = (offset + (k % 5) * 200, (k // 5) * 150, w, h)
                k += 1
        right = max((p[0] + p[2] for key, p in positions.items() if key[0] == file),
                    default=offset)
        offset = right + FILE_GAP
    return positions


def expansion_targets(graphs: list[Graph]) -> dict[Key, int]:
    """会被展开的空子流程：(文件名, 节点 ID) → 目标图在 graphs 中的下标。

    子流程名称等于另一张图的文件名或其 process 名称（文件名优先，先出现者优先）时展开。
    """
    files = [g.sources[0].file for g in graphs]
    by_name: dict[str, int] = {}
    for i, g in enumerate(graphs):
        by_name.setdefault(files[i], i)
        pname = (g.sources[0].process_attrs.get("name") or "").strip()
        if pname:
            by_name.setdefault(pname, i)
    targets: dict[Key, int] = {}
    for i, g in enumerate(graphs):
        for n in g.nodes.values():
            ti = by_name.get((n.name or "").strip()) if n.expandable else None
            if ti is not None and ti != i:
                targets[(files[i], n.id)] = ti
    return targets


def merge(graphs: list[Graph]) -> tuple[Graph, MergeReport]:
    report = MergeReport()
    files = [g.sources[0].file for g in graphs]
    dupes = {f for f in files if files.count(f) > 1}
    if dupes:
        raise MergeError(f"文件名重复：{'、'.join(sorted(dupes))}（每个文件名只能出现一次）")
    for g in graphs:
        report.warnings.extend(g.warnings)

    nodes: dict[Key, Node] = {}
    for f, g in zip(files, graphs):
        for n in g.nodes.values():
            nodes[(f, n.id)] = n
    order = {k: i for i, k in enumerate(nodes)}
    parent: dict[Key, Key] = {k: k for k in nodes}

    def find(k: Key) -> Key:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    # 每个集合已接入哪些文件的流程：同一文件的两个不同元素绝不能并成一个节点，
    # 否则会在该文件内造成环路（例如子流程展开后，调用方与目标流程都有「开始」「结束」）
    wired: dict[Key, set[str]] = {k: {k[0]} for k in nodes}

    def absorb(rep: Key, other: Key) -> bool:
        root_rep, root_other = find(rep), find(other)
        if root_rep == root_other:
            return True
        if wired[root_rep] & wired[root_other]:
            return False
        parent[root_other] = root_rep
        wired[root_rep] |= wired.pop(root_other)
        return True

    edges: list[_EdgeRec] = []
    for f, g in zip(files, graphs):
        for e in g.edges.values():
            edges.append(_EdgeRec((f, e.id), (f, e.source), (f, e.target), e.name, list(e.origins)))

    # 1. 空子流程展开
    file_index = {f: i for i, f in enumerate(files)}
    expanded: set[Key] = set()
    for sub, ti in expansion_targets(graphs).items():
        i, n = file_index[sub[0]], graphs[file_index[sub[0]]].nodes[sub[1]]
        tg, tf = graphs[ti], files[ti]
        t_in = {e.target for e in tg.edges.values()}
        t_out = {e.source for e in tg.edges.values()}
        entries = [m.id for m in tg.nodes.values() if m.bpmn_type == "startEvent"]
        if not entries:
            entries = [m.id for m in tg.nodes.values() if m.id not in t_in]
            report.warnings.append(f"「{tf}」没有开始事件，子流程 {n.id} 的入线接到无入线的节点")
        exits = [m.id for m in tg.nodes.values() if m.bpmn_type == "endEvent"]
        if not exits:
            exits = [m.id for m in tg.nodes.values() if m.id not in t_out]
            report.warnings.append(f"「{tf}」没有结束事件，子流程 {n.id} 的出线从无出线的节点出发")
        if not entries:
            report.warnings.append(f"「{tf}」没有可作为入口的节点，子流程 {n.id} 未展开")
            continue
        if not absorb((tf, entries[0]), sub):
            report.warnings.append(
                f"子流程 {n.id} 的入口 {entries[0]} 已接入「{files[i]}」的流程，子流程未展开")
            continue
        expanded.add(sub)
        for x in entries + exits:
            wired[find((tf, x))].add(files[i])
        report.expansions.append(Expansion(n.id, files[i], tf, entries[0]))
        preds = [r.src for r in edges if r.tgt == sub]
        for extra in entries[1:]:
            report.warnings.append(f"「{tf}」有多个入口，{extra} 也连到子流程 {n.id} 的前驱节点")
            for p in preds:
                edges.append(_EdgeRec(None, p, (tf, extra), None, []))
        for r in [r for r in edges if r.src == sub]:
            if not exits:
                break
            for extra in exits[1:]:
                edges.append(_EdgeRec(None, (tf, extra), r.tgt, r.name, []))
            r.src = (tf, exits[0])

    # 2. 跨文件同名合并
    name_groups: dict[str, dict[str, Key]] = {}
    for key, n in nodes.items():
        name = (n.name or "").strip()
        if not name or key in expanded:
            continue
        per_file = name_groups.setdefault(name, {})
        if key[0] in per_file:
            report.warnings.append(
                f"「{key[0]}」中有多个名为「{name}」的节点，只有 {per_file[key[0]][1]} 参与合并，{key[1]} 保持独立")
            continue
        per_file[key[0]] = key
    groups: list[tuple[str, list[Key]]] = []
    for name, per_file in name_groups.items():
        candidates = list(per_file.values())
        if len(candidates) < 2:
            continue
        members = candidates[:1]
        for m in candidates[1:]:
            if absorb(candidates[0], m):
                members.append(m)
            else:
                report.warnings.append(
                    f"同名节点「{name}」：{m[0]}:{m[1]} 与 {candidates[0][0]}:{candidates[0][1]} "
                    f"合并会把同一文件的不同元素并在一起（通常由子流程展开引起），已保持独立")
        if len(members) < 2:
            continue
        groups.append((name, members))
        kinds = {_family(nodes[m].bpmn_type) for m in members}
        if len(kinds) > 1:
            report.warnings.append(
                f"同名节点「{name}」类型不一致（{'、'.join(sorted(nodes[m].bpmn_type for m in members))}），"
                f"已合并并保留 {nodes[members[0]].bpmn_type}")

    # 3. 折叠
    positions = _layout_positions(graphs)
    used: set[str] = set()
    final_id: dict[Key, str] = {}
    merged = Graph(sources=[s for g in graphs for s in g.sources])
    members_of: dict[Key, list[Key]] = {}
    for key in nodes:
        members_of.setdefault(find(key), []).append(key)
    for root in sorted(members_of, key=order.__getitem__):
        rep = nodes[root]
        nid = _unique(rep.id, used, report, "节点")
        origins = [o for m in [root] + [m for m in members_of[root] if m != root]
                   for o in nodes[m].origins]
        merged.nodes[nid] = Node(nid, rep.bpmn_type, rep.name, origins, bounds=positions[root])
        for m in members_of[root]:
            final_id[m] = nid

    for name, members in groups:
        report.groups.append(MergeGroup(name, final_id[members[0]], list(members)))

    # 4. 连线（去重）
    seen: dict[tuple[str, str, str | None], Edge] = {}
    for r in edges:
        src, tgt = final_id[find(r.src)], final_id[find(r.tgt)]
        dedup = (src, tgt, r.name)
        if dedup in seen:
            seen[dedup].origins.extend(r.origins)
            continue
        eid = _unique(r.key[1], used, report, "连线") if r.key else _unique(new_id(), used, report, "连线")
        edge = Edge(eid, src, tgt, r.name, r.origins)
        seen[dedup] = edge
        merged.edges[eid] = edge

    # 5. 事件规范化
    report.retyped.extend(normalize_events(merged))
    merged.warnings = list(report.warnings)
    return merged, report

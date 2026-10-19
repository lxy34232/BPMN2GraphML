"""命令行与图形界面共用的两个转换流程。"""
from __future__ import annotations

from pathlib import Path

from .bpmn_reader import read_bpmn
from .bpmn_writer import write_merged_bpmn, write_split_bpmn
from .graphml_reader import read_graphml
from .graphml_writer import write_graphml
from .merger import MergeReport, merge


def report_path_for(graphml_path: Path) -> Path:
    graphml_path = Path(graphml_path)
    return graphml_path.with_name(graphml_path.stem + ".merge-report.txt")


def bpmn_to_graphml(inputs: list[Path], output: Path) -> MergeReport:
    """读取并合并多个 BPMN，写出 graphml 和合并报告。"""
    output = Path(output)
    merged, report = merge([read_bpmn(p) for p in inputs])
    output.parent.mkdir(parents=True, exist_ok=True)
    write_graphml(merged, output)
    report_path_for(output).write_text(report.to_text(), encoding="utf-8")
    return report


def graphml_to_bpmn(input: Path, merged: Path | None, split_dir: Path | None) -> list[str]:
    """把 yEd 保存的 graphml 转回 BPMN；返回警告列表。"""
    graph = read_graphml(input)
    warnings = list(graph.warnings)
    if merged:
        Path(merged).parent.mkdir(parents=True, exist_ok=True)
        warnings += write_merged_bpmn(graph, merged)
    if split_dir:
        warnings += write_split_bpmn(graph, split_dir)
    return warnings

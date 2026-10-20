"""命令行入口：merge（BPMN → GraphML）、tobpmn（GraphML → BPMN）、view（查看器）、
props-export / props-import（节点属性表）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bpmn_reader import BpmnReadError
from .graphml_reader import GraphmlReadError
from .merger import MergeError
from .pipeline import bpmn_to_graphml, graphml_to_bpmn, report_path_for
from .prop_table import PropTableError, export_table, import_report_path_for, import_table
from .table_io import TableError
from .viewer_launch import open_viewer


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bpmn2graphml", description="BPMN 与 yEd GraphML 互转")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("merge", help="合并多个 BPMN 文件为一个 yEd graphml")
    m.add_argument("inputs", nargs="+", type=Path, help="BPMN 文件（顺序决定合并时谁是“首个”）")
    m.add_argument("-o", "--output", required=True, type=Path, help="输出 graphml 路径")
    t = sub.add_parser("tobpmn", help="把 yEd 保存的 graphml 转回 BPMN")
    t.add_argument("input", type=Path, help="graphml 文件")
    t.add_argument("--merged", type=Path, help="输出合并后的单个 BPMN 文件")
    t.add_argument("--split", type=Path, help="拆分回原文件，输出到此文件夹")
    v = sub.add_parser("view", help="在浏览器中打开可视化查看器")
    v.add_argument("file", nargs="?", type=Path, help="要打开的 BPMN 文件（可选）")
    pe = sub.add_parser("props-export", help="从 BPMN 导出节点属性表（.xlsx 或 .csv）")
    pe.add_argument("inputs", nargs="+", type=Path, help="BPMN 文件")
    pe.add_argument("-o", "--output", required=True, type=Path, help="输出表格（按扩展名决定格式）")
    pi = sub.add_parser("props-import", help="把属性表导回 BPMN（直接修改文件，修改前备份为 .bak）")
    pi.add_argument("table", type=Path, help="属性表（.xlsx 或 .csv）")
    pi.add_argument("inputs", nargs="+", type=Path, help="要写入的 BPMN 文件")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "tobpmn" and not (args.merged or args.split):
        parser.error("至少需要 --merged 或 --split 之一")
    if args.command == "view":
        if args.file is not None and not args.file.is_file():
            print(f"错误：找不到文件 {args.file}", file=sys.stderr)
            return 1
        page = open_viewer(args.file)
        print(f"已在浏览器中打开查看器：{page}")
        return 0
    if args.command == "props-import":
        report = import_table(args.table, args.inputs)
        print(report.to_text())
        print()
        print(f"导入报告：{import_report_path_for(args.table)}")
        return 0 if report.ok else 1
    try:
        if args.command == "props-export":
            print(export_table(args.inputs, args.output).to_text())
            return 0
        if args.command == "merge":
            report = bpmn_to_graphml(args.inputs, args.output)
            print(f"已写出 {args.output}（{len(report.groups)} 组同名合并，"
                  f"{len(report.expansions)} 个子流程展开）")
            print(f"合并报告：{report_path_for(args.output)}")
            warnings = report.warnings
        else:
            warnings = graphml_to_bpmn(args.input, args.merged, args.split)
            if args.merged:
                print(f"已写出合并文件 {args.merged}")
            if args.split:
                print(f"已拆分到文件夹 {args.split}")
    except (BpmnReadError, GraphmlReadError, MergeError, PropTableError, TableError,
            OSError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"警告：{w}")
    return 0

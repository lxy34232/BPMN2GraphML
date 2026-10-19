"""tkinter 图形界面：两个页签分别对应两个转换方向。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .bpmn_reader import BpmnReadError
from .graphml_reader import GraphmlReadError
from .merger import MergeError
from .pipeline import bpmn_to_graphml, graphml_to_bpmn, report_path_for

_ERRORS = (BpmnReadError, GraphmlReadError, MergeError, OSError)
_BPMN_TYPES = [("BPMN 文件", "*.bpmn *.xml"), ("所有文件", "*.*")]
_GRAPHML_TYPES = [("GraphML 文件", "*.graphml"), ("所有文件", "*.*")]


def _log_box(parent: tk.Widget) -> tk.Text:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(8, 0))
    text = tk.Text(frame, height=12, wrap="word", state="disabled")
    bar = ttk.Scrollbar(frame, command=text.yview)
    text.configure(yscrollcommand=bar.set)
    text.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return text


def _show(text: tk.Text, content: str) -> None:
    text.configure(state="normal")
    text.delete("1.0", "end")
    text.insert("1.0", content)
    text.configure(state="disabled")


def _path_row(parent: tk.Widget, label: str, var: tk.StringVar, browse) -> ttk.Frame:
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=2)
    ttk.Label(row, text=label, width=14).pack(side="left")
    ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="浏览…", command=browse).pack(side="left", padx=(4, 0))
    return row


class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=10)
        self.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self._build_merge_tab()
        self._build_back_tab()

    # —— 页签一：BPMN → GraphML ——
    def _build_merge_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="BPMN → GraphML")
        ttk.Label(tab, text="BPMN 文件（顺序决定合并时谁是“首个”）：").pack(anchor="w")
        body = ttk.Frame(tab)
        body.pack(fill="x")
        self.files = tk.Listbox(body, height=8, selectmode="extended")
        self.files.pack(side="left", fill="both", expand=True)
        buttons = ttk.Frame(body)
        buttons.pack(side="left", fill="y", padx=(6, 0))
        for text, cmd in [("添加…", self._add_files), ("移除", self._remove_files),
                          ("上移", lambda: self._move(-1)), ("下移", lambda: self._move(1))]:
            ttk.Button(buttons, text=text, command=cmd).pack(fill="x", pady=1)
        self.graphml_out = tk.StringVar()
        _path_row(tab, "输出 graphml：", self.graphml_out, self._pick_graphml_out)
        ttk.Button(tab, text="合并并导出", command=self._run_merge).pack(anchor="e", pady=4)
        self.merge_log = _log_box(tab)

    def _add_files(self) -> None:
        for p in filedialog.askopenfilenames(title="选择 BPMN 文件", filetypes=_BPMN_TYPES):
            if p not in self.files.get(0, "end"):
                self.files.insert("end", p)
        if not self.graphml_out.get() and self.files.size():
            self.graphml_out.set(str(Path(self.files.get(0)).with_name("merged.graphml")))

    def _remove_files(self) -> None:
        for i in reversed(self.files.curselection()):
            self.files.delete(i)

    def _move(self, delta: int) -> None:
        sel = self.files.curselection()
        if len(sel) != 1:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < self.files.size():
            item = self.files.get(i)
            self.files.delete(i)
            self.files.insert(j, item)
            self.files.selection_set(j)

    def _pick_graphml_out(self) -> None:
        p = filedialog.asksaveasfilename(title="保存 graphml", defaultextension=".graphml",
                                         filetypes=_GRAPHML_TYPES)
        if p:
            self.graphml_out.set(p)

    def _run_merge(self) -> None:
        inputs = [Path(p) for p in self.files.get(0, "end")]
        if not inputs or not self.graphml_out.get():
            messagebox.showerror("错误", "请先添加 BPMN 文件并选择输出路径")
            return
        output = Path(self.graphml_out.get())
        try:
            report = bpmn_to_graphml(inputs, output)
        except _ERRORS as e:
            messagebox.showerror("错误", str(e))
            return
        _show(self.merge_log, f"已写出：{output}\n合并报告：{report_path_for(output)}\n\n"
                              + report.to_text())

    # —— 页签二：GraphML → BPMN ——
    def _build_back_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="GraphML → BPMN")
        self.graphml_in = tk.StringVar()
        _path_row(tab, "yEd graphml：", self.graphml_in, self._pick_graphml_in)
        self.want_merged = tk.BooleanVar(value=True)
        self.want_split = tk.BooleanVar(value=True)
        self.merged_out = tk.StringVar()
        self.split_dir = tk.StringVar()
        ttk.Checkbutton(tab, text="合并为一个文件", variable=self.want_merged).pack(anchor="w", pady=(8, 0))
        _path_row(tab, "输出 BPMN：", self.merged_out, self._pick_merged_out)
        ttk.Checkbutton(tab, text="拆分回原文件", variable=self.want_split).pack(anchor="w", pady=(8, 0))
        _path_row(tab, "输出文件夹：", self.split_dir, self._pick_split_dir)
        ttk.Button(tab, text="转换", command=self._run_back).pack(anchor="e", pady=4)
        self.back_log = _log_box(tab)

    def _pick_graphml_in(self) -> None:
        p = filedialog.askopenfilename(title="选择 yEd 保存的 graphml", filetypes=_GRAPHML_TYPES)
        if p:
            self.graphml_in.set(p)
            base = Path(p)
            if not self.merged_out.get():
                self.merged_out.set(str(base.with_name(base.stem + ".bpmn")))
            if not self.split_dir.get():
                self.split_dir.set(str(base.with_name(base.stem + "_split")))

    def _pick_merged_out(self) -> None:
        p = filedialog.asksaveasfilename(title="保存 BPMN", defaultextension=".bpmn",
                                         filetypes=_BPMN_TYPES)
        if p:
            self.merged_out.set(p)

    def _pick_split_dir(self) -> None:
        p = filedialog.askdirectory(title="选择拆分输出文件夹")
        if p:
            self.split_dir.set(p)

    def _run_back(self) -> None:
        merged = Path(self.merged_out.get()) if self.want_merged.get() and self.merged_out.get() else None
        split = Path(self.split_dir.get()) if self.want_split.get() and self.split_dir.get() else None
        if not self.graphml_in.get() or not (merged or split):
            messagebox.showerror("错误", "请选择 graphml，并至少勾选一种输出方式且填写路径")
            return
        try:
            warnings = graphml_to_bpmn(Path(self.graphml_in.get()), merged, split)
        except _ERRORS as e:
            messagebox.showerror("错误", str(e))
            return
        lines = []
        if merged:
            lines.append(f"已写出合并文件：{merged}")
        if split:
            lines.append(f"已拆分到文件夹：{split}")
        lines += ["", "== 警告 =="] + (warnings or ["（无）"])
        _show(self.back_log, "\n".join(lines))


def run() -> None:
    root = tk.Tk()
    root.title("BPMN ⇄ yEd GraphML 转换器")
    root.geometry("760x560")
    App(root)
    root.mainloop()

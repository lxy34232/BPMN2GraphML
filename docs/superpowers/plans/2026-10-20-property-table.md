# 节点属性表（导出 / 导入）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 BPMN 导出节点属性表（.xlsx / .csv），用户在 Excel 中编辑后导回，就地改写 BPMN 节点的 `b2g` 属性并生成报告；提供命令行和图形界面入口。

**Architecture:** `table_io.py` 只管表格文件读写（标准库 `zipfile` + `csv`）；`prop_table.py` 负责解析 BPMN（保留注释与前缀）、按名称分组、导出、校验并就地改写、生成报告；`properties.py` 增加以元素为单位的属性读写；`merger.py` 抽出“空子流程展开目标”的判定供两处共用。CLI 与 GUI 只是薄薄一层调用。

**Tech Stack:** Python 3.10+ 标准库（`xml.etree.ElementTree`、`zipfile`、`csv`、`tkinter`），pytest。

**Spec:** `docs/superpowers/specs/2026-10-20-property-table-design.md`

## Global Constraints

- 只用 Python 标准库，不新增任何依赖。
- 属性格式：`extensionElements / b2g:properties / b2g:property(name, value)`，命名空间 `https://github.com/lxy34232/BPMN2GraphML/properties`，前缀 `b2g`。
- 表头固定文字：`节点名称`、`所在文件`、`元素类型`、`来源流程`；后三个是只读参考列。
- 多值分隔：读入时 `；` 与 `;` 都认；导出用 `；`。
- 名称比较：`str.strip()` 后完全相同。
- 备份文件名：`<原文件名>.bak`（如 `a.bpmn.bak`）；报告文件名：`<表格文件名去扩展名>.import-report.txt`，UTF-8。
- 界面文字、报告、错误信息均为中文。
- 导出的 CSV：UTF-8 带 BOM；读入 CSV：先 `utf-8-sig`，失败再 `gb18030`。
- 导入任何中止情况下，一个 BPMN 文件都不写。

## Review Focus

1. 表格文件正在 Excel 中打开时导出 → 给出“请先在 Excel 中关闭该文件”的提示，而不是原始异常。（Task 3 测试 `test_write_locked_file_message`）
2. 同一张表导入两次 → 第二次没有任何变化，不改写文件，也不覆盖第一次留下的 `.bak`。（Task 6 测试 `test_second_import_changes_nothing`）
3. 节点名称或取值里含换行、首尾全角空格 → 导出再导入仍能匹配，取值不变。（Task 5 测试 `test_export_import_roundtrip_unchanged` 的数据里包含这种名称）
4. 节点上已有 Camunda `properties` 或其它扩展内容 → 导入只换 `b2g:properties`，其它原样保留。（Task 1 测试 `test_set_node_keeps_other_extensions`）
5. 只含空白的格子、表头首尾有空格 → 按空格子 / 去空格后的表头处理。（Task 6 测试 `test_whitespace_cells_and_headers`）

---

### Task 1: 节点元素级属性读写 + 元素类型中文名

**Files:**
- Modify: `bpmn2graphml/properties.py`
- Test: `tests/test_properties.py`

**Interfaces:**
- Produces:
  - `TYPE_LABELS: dict[str, str]` —— 与 `bpmn2graphml/viewer/properties.js` 中的 `TYPE_LABELS` 完全相同（20 项，含 `boundaryEvent: "边界事件"`）。
  - `type_label(bpmn_type: str) -> str` —— 查不到时返回原值。
  - `node_b2g_properties(node: ET.Element) -> list[Prop]` —— 读节点直接子元素 `extensionElements` 下的 b2g 属性（规则同现有 `read_b2g_properties`：去首尾空格，名或值为空的丢弃）。
  - `set_node_b2g_properties(node: ET.Element, props: list[Prop]) -> None` —— 就地替换；规则同现有 `with_b2g_properties`（新建 `extensionElements` 插在开头连续的 `documentation` 之后；变空则删除）。
  - 现有 `read_b2g_properties` / `with_b2g_properties` 签名和行为不变，改为把子元素包进一个临时元素后调用上面两个函数实现。

- [ ] **Step 1: 写失败测试**

```python
import xml.etree.ElementTree as ET
from bpmn2graphml.properties import (TYPE_LABELS, type_label, node_b2g_properties,
                                     set_node_b2g_properties)

def _node(inner=""):
    return ET.fromstring(f'<bpmn2:task xmlns:bpmn2="{BPMN_NS}" id="t" name="n">{inner}'
                         '<bpmn2:incoming>f1</bpmn2:incoming></bpmn2:task>')

def test_type_label():
    assert type_label("manualTask") == "人工任务"
    assert type_label("boundaryEvent") == "边界事件"
    assert type_label("weird") == "weird"
    assert len(TYPE_LABELS) == 20

def test_set_node_creates_after_documentation():
    node = _node(DOC)
    set_node_b2g_properties(node, [("负责人", "张三"), ("系统", "OA"), ("系统", "ERP")])
    tags = [c.tag.rsplit("}", 1)[1] for c in node]
    assert tags == ["documentation", "extensionElements", "incoming"]
    assert node_b2g_properties(node) == [("负责人", "张三"), ("系统", "OA"), ("系统", "ERP")]

def test_set_node_empty_removes_extension():
    node = _node()
    set_node_b2g_properties(node, [("a", "1")])
    set_node_b2g_properties(node, [])
    assert [c.tag.rsplit("}", 1)[1] for c in node] == ["incoming"]

def test_set_node_keeps_other_extensions():
    camunda = ('<bpmn2:extensionElements xmlns:c="http://camunda.org/schema/1.0/bpmn">'
               '<c:properties><c:property name="x" value="1"/></c:properties>'
               '</bpmn2:extensionElements>')
    node = _node(camunda)
    set_node_b2g_properties(node, [("a", "1")])
    set_node_b2g_properties(node, [])
    ext = node.find(f"{{{BPMN_NS}}}extensionElements")
    assert ext is not None and ext.find("{http://camunda.org/schema/1.0/bpmn}properties") is not None
    assert node_b2g_properties(node) == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_properties.py -v`
Expected: 新测试 ImportError 失败

- [ ] **Step 3: 在 `bpmn2graphml/properties.py` 实现上述 4 个新名称，并让旧的两个函数委托给它们**

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`
Expected: 全部通过（现有 `test_properties.py`、`test_bpmn_writer.py` 不受影响）

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/properties.py tests/test_properties.py
git commit -m "feat: element-level b2g property helpers and type labels"
```

---

### Task 2: 抽出空子流程展开目标的判定

**Files:**
- Modify: `bpmn2graphml/merger.py:175-189`（第 1 步“空子流程展开”的 `by_name` 与目标查找）
- Test: `tests/test_merger.py`

**Interfaces:**
- Produces: `expansion_targets(graphs: list[Graph]) -> dict[tuple[str, str], int]` —— 键为（文件名, 节点 ID），值为它会展开到的目标图在 `graphs` 中的下标。规则即现有代码：节点 `expandable`，其 `name.strip()` 等于另一张图的文件名或其第一个 process 的 `name`（文件名优先，先出现者优先），且目标不是自己所在的图。按图顺序、图内节点顺序生成。
- `merge()` 改为遍历 `expansion_targets(graphs)` 的结果，行为不变。

- [ ] **Step 1: 写失败测试**

```python
from bpmn2graphml.merger import expansion_targets
from bpmn2graphml.bpmn_reader import read_bpmn

def test_expansion_targets_fixtures():
    graphs = [read_bpmn(p) for p in fixture_paths()]
    assert expansion_targets(graphs) == {("科技创新平台策划", SUB): 1}

def test_expansion_targets_needs_target_selected():
    graphs = [read_bpmn(fixture_paths()[0])]
    assert expansion_targets(graphs) == {}
```

（`SUB` 为 `test_merger.py` 中已有的子流程 ID 常量；`fixture_paths` 从 `conftest` 导入，如该文件尚未导入则补上。）

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_merger.py -v`
Expected: ImportError 失败

- [ ] **Step 3: 在 `merger.py` 中实现 `expansion_targets`，并让 `merge()` 第 1 步使用它**

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/merger.py tests/test_merger.py
git commit -m "refactor: extract expansion_targets from merge"
```

---

### Task 3: 表格读写 —— 写出 xlsx / csv，并能读回

**Files:**
- Create: `bpmn2graphml/table_io.py`
- Test: `tests/test_table_io.py`

**Interfaces:**
- Produces:
  - `class TableError(Exception)` —— 所有表格读写失败都包成它，消息为中文、含文件名。
  - `write_table(path: Path, rows: list[list[str]], readonly_cols: frozenset[int] = frozenset()) -> None` —— 按扩展名（不区分大小写）选 `.xlsx` / `.csv`，其它扩展名抛 `TableError`。`rows[0]` 为表头。
  - `read_table(path: Path) -> list[list[str]]` —— 返回各行（含表头），每行补齐到相同列数；去掉末尾的全空行。格子值不做 strip。

xlsx 写出要求（我已定）：
- 最小部件：`[Content_Types].xml`、`_rels/.rels`、`xl/workbook.xml`（工作表名“属性”）、`xl/_rels/workbook.xml.rels`、`xl/styles.xml`、`xl/worksheets/sheet1.xml`。
- 所有单元格写成 `t="inlineStr"`，`<t xml:space="preserve">`。
- `styles.xml` 的 `cellXfs`：0 默认；1 表头（粗体 + 文本格式 `numFmtId="49"`）；2 普通数据（文本格式 49）；3 只读数据（文本格式 49 + 浅灰底 `FFEDEDED`）。表头一律用 1。
- `<cols>`：每列宽度 = 该列最长内容的显示宽度（非 ASCII 字符算 2）+ 2，限制在 8–60；另外再追加 20 个空列，`style="2"`，宽 12。这样用户在新列里输入的内容也默认是文本格式。
- 冻结首行：`<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>`。
- `PermissionError` → `TableError(f"无法写入 {path.name}：文件可能正在 Excel 中打开，请先关闭该文件")`；读时同理用“无法读取”。

- [ ] **Step 1: 写失败测试**

```python
ROWS = [["节点名称", "所在文件", "负责人"],
        ["部门领导审核", "策划；申报", "张三；李四"],
        ["多行\n名称", "", ""],
        ["　全角空格　", "a", "001"]]

@pytest.mark.parametrize("ext", [".xlsx", ".csv", ".XLSX"])
def test_roundtrip(tmp_path, ext):
    p = tmp_path / f"t{ext}"
    write_table(p, ROWS, frozenset({1}))
    assert read_table(p) == ROWS

def test_csv_has_bom(tmp_path):
    p = tmp_path / "t.csv"
    write_table(p, ROWS)
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")

def test_csv_gbk(tmp_path):
    p = tmp_path / "t.csv"
    p.write_bytes("节点名称,负责人\r\n审核,张三\r\n".encode("gbk"))
    assert read_table(p) == [["节点名称", "负责人"], ["审核", "张三"]]

def test_trailing_empty_rows_dropped_and_padded(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("a,b,c\nx\n,,\n", encoding="utf-8")
    assert read_table(p) == [["a", "b", "c"], ["x", "", ""]]

def test_xlsx_text_styles_and_freeze(tmp_path):
    p = tmp_path / "t.xlsx"
    write_table(p, ROWS, frozenset({1}))
    with zipfile.ZipFile(p) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        styles = z.read("xl/styles.xml").decode()
    assert 'state="frozen"' in sheet and 'numFmtId="49"' in styles

def test_unknown_extension(tmp_path):
    with pytest.raises(TableError):
        write_table(tmp_path / "t.txt", ROWS)

def test_write_locked_file_message(tmp_path, monkeypatch):
    def locked(*a, **k): raise PermissionError(13, "denied")
    monkeypatch.setattr(zipfile, "ZipFile", locked)
    with pytest.raises(TableError, match="请先关闭该文件"):
        write_table(tmp_path / "t.xlsx", ROWS)
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_table_io.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 `bpmn2graphml/table_io.py`**

xlsx 读取在本任务只需能读回自己写出的文件（内联字符串）；Task 4 补全对外部文件的支持。CSV 用 `csv` 模块，`lineterminator="\r\n"`，读时 `io.StringIO(text, newline="")`。

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_table_io.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/table_io.py tests/test_table_io.py
git commit -m "feat: xlsx/csv table read and write"
```

---

### Task 4: 读取 Excel / WPS 保存的 xlsx

**Files:**
- Modify: `bpmn2graphml/table_io.py`
- Test: `tests/test_table_io.py`

**Interfaces:**
- Consumes/Produces: 仍是 `read_table(path) -> list[list[str]]`。

读取规则（我已定）：
- 从 `xl/workbook.xml` 取第一个 `<sheet>` 的 `r:id`，在 `xl/_rels/workbook.xml.rels` 中找到 `Target`；`Target` 以 `/` 开头时视为包内绝对路径，否则相对于 `xl/`。
- `<c r="C5">` 用 `r` 定位列；缺失的格子为 `""`；没有 `r` 时顺延。
- `t="s"`：共享字符串，`<si>` 下所有 `<t>` 拼接，但跳过 `<rPh>`（注音）里的 `<t>`。`t="inlineStr"`：`<is>` 下的 `<t>` 同理。`t="str"`/`"e"`：`<v>` 原文。`t="b"`：`"TRUE"`/`"FALSE"`。
- 数字：若该格样式是日期格式，转为 `YYYY-MM-DD`，时间部分四舍五入到分钟后非零则追加 ` HH:MM`；纪元为 1899-12-30，`workbookPr date1904="1"` 时为 1904-01-01。否则：`float(v).is_integer()` 且绝对值 < 1e15 时输出整数文本，其它输出 `<v>` 原文。
- 日期格式判定：`cellXfs[s].numFmtId` 属于 `{14,15,16,17,22,27,28,29,30,31,36,50,51,52,53,54,55,56,57,58}`；或该 id 在 `<numFmts>` 中自定义，`formatCode` 去掉 `"..."`、`[...]`、`\x` 转义后包含 `y` 或 `d`（不区分大小写）。

- [ ] **Step 1: 写失败测试**

在测试中用 `zipfile` 手工拼一个“外部”xlsx 的辅助函数 `_make_xlsx(path, sheet_xml, shared=None, styles=None, sheet_target="worksheets/sheet7.xml", date1904=False)`，然后：

```python
def test_shared_strings_rich_text_and_phonetic(tmp_path): ...
    # <si><r><t>部门</t></r><r><t>审核</t></r><rPh><t>ブ</t></rPh></si> → "部门审核"

def test_sparse_cells(tmp_path): ...
    # 行 1: A1, C1 有值 → ["a", "", "c"]；行 3 存在、行 2 缺失 → 中间补一个全空行

def test_numbers_and_bools(tmp_path): ...
    # <v>3</v> → "3"; <v>3.0</v> → "3"; <v>0.5</v> → "0.5"; t="b" <v>1</v> → "TRUE"

def test_dates_builtin_and_custom(tmp_path): ...
    # numFmtId 14, v=46315 → "2026-10-20"
    # 自定义 164 "yyyy\"年\"m\"月\"d\"日\"", v=46315.5 → "2026-10-20 12:00"
    # 自定义 165 "0.00%", v=0.5 → "0.5"
    # numFmtId 20 (h:mm), v=0.5 → "0.5"

def test_date1904(tmp_path): ...
    # date1904，numFmtId 14，v=0 → "1904-01-01"

def test_absolute_sheet_target(tmp_path): ...
    # rels Target="/xl/worksheets/sheet7.xml" 也能读到
```

每个测试写出具体的 XML 片段与期望的 `read_table` 返回值。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_table_io.py -v`
Expected: 新测试失败

- [ ] **Step 3: 在 `table_io.py` 中补全 xlsx 读取**

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_table_io.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/table_io.py tests/test_table_io.py
git commit -m "feat: read Excel/WPS xlsx (shared strings, sparse cells, dates)"
```

---

### Task 5: 载入 BPMN、按名称分组、导出属性表

**Files:**
- Create: `bpmn2graphml/prop_table.py`
- Test: `tests/test_prop_table.py`

**Interfaces:**
- Consumes: Task 1 的 `node_b2g_properties`、`type_label`、`TYPE_LABELS`、`SOURCE_PROP`；Task 2 的 `expansion_targets`；Task 3 的 `write_table`、`TableError`；`bpmn_reader.read_bpmn`、`BpmnReadError`。
- Produces（Task 6、7、8 使用）：
  - 常量 `NAME_HEADER = "节点名称"`、`FILE_HEADER = "所在文件"`、`TYPE_HEADER = "元素类型"`、`READONLY_HEADERS = (FILE_HEADER, TYPE_HEADER, SOURCE_PROP)`。
  - `class PropTableError(Exception)`
  - `@dataclass NodeRef(file: str, id: str, name: str, bpmn_type: str, element: ET.Element)`
  - `@dataclass BpmnDoc(path: Path, file: str, root: ET.Element, namespaces: list[tuple[str, str]], nodes: list[NodeRef])` —— `file` 为 `path.stem`。
  - `load_docs(paths: list[Path]) -> list[BpmnDoc]` —— 用 `ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))` 解析以保留注释；用 `ET.iterparse(path, events=("start-ns",))` 收集前缀；节点 = 文件中任意层级、命名空间为 BPMN 且本地名在 `TYPE_LABELS` 中的元素，按文档顺序。`ET.ParseError`、`OSError`、`BpmnReadError`（下一条用到）以及文件名（stem）重复都抛 `PropTableError`，消息含文件名。
  - `group_rows(docs: list[BpmnDoc]) -> tuple[dict[str, list[NodeRef]], list[str]]` —— 返回（行名 → 节点列表，按首次出现顺序；归并说明列表）。名称为空的节点不进任何行。对 `expansion_targets([read_bpmn(d.path) for d in docs])` 中的每个空子流程：目标文件第一个 `startEvent`（按 `read_bpmn` 的节点顺序）存在且名称非空时，这个子流程归入开始事件名称那一行，并记一条说明 `「科技创新平台申报」（科技创新平台策划）归入「启动平台申报」`；否则按普通节点处理。
  - `@dataclass ExportSummary(path: Path, rows: int, columns: list[str], conflicts: list[str], folded: list[str])`，`to_text() -> str`；`path` 后缀为 `.csv` 时，文本末尾附一句：`提示：CSV 在 Excel 中打开再保存，可能把“001”变成“1”、把“1-2”变成日期；建议使用 .xlsx。`
  - `export_table(bpmn_paths: list[Path], out: Path) -> ExportSummary`

导出表结构：
- 表头：`节点名称, 所在文件, 元素类型, [来源流程], 属性列…`。`来源流程` 列仅在任一节点有该属性时出现。属性列 = 除 `READONLY_HEADERS` 外的 b2g 属性名，按跨文件、按文档顺序的首次出现排序。
- 每行：所在文件、元素类型（`type_label`）、各属性的取值，均为组内各节点的去重并集（保持出现顺序），用 `；` 连接。
- 只读列下标传给 `write_table(..., readonly_cols=...)`。
- `conflicts`：组内节点多于一个，且它们（不含只读名）的属性按 `{名称: 取值集合}` 比较不相同的行名。

- [ ] **Step 1: 写失败测试**

```python
def test_group_rows_fixtures_folds_subprocess():
    rows, folded = group_rows(load_docs(fixture_paths()))
    assert "科技创新平台申报" not in rows
    assert {(n.file, n.bpmn_type) for n in rows["启动平台申报"]} == {
        ("科技创新平台策划", "subProcess"), ("科技创新平台申报", "startEvent")}
    assert len(folded) == 1 and "启动平台申报" in folded[0]

def test_group_rows_single_file_keeps_subprocess_row():
    rows, folded = group_rows(load_docs(fixture_paths()[:1]))
    assert "科技创新平台申报" in rows and folded == []

def test_export_columns_and_values(tmp_path):
    # 拷贝两个 fixture 到 tmp，用 set_node_b2g_properties 给同名节点「部门领导审核」
    # 分别写 [("来源流程","策划"),("负责人","张三")] 和 [("负责人","李四"),("系统","OA")]，保存
    s = export_table(paths, tmp_path / "t.xlsx")
    table = read_table(tmp_path / "t.xlsx")
    assert table[0] == ["节点名称", "所在文件", "元素类型", "来源流程", "负责人", "系统"]
    row = next(r for r in table if r[0] == "部门领导审核")
    assert row[4] == "张三；李四" and row[5] == "OA"
    assert s.conflicts == ["部门领导审核"]

def test_export_csv_summary_warns(tmp_path):
    s = export_table(fixture_paths(), tmp_path / "t.csv")
    assert "建议使用 .xlsx" in s.to_text()

def test_load_docs_errors(tmp_path):
    bad = tmp_path / "x.bpmn"; bad.write_text("hello", encoding="utf-8")
    with pytest.raises(PropTableError, match="x.bpmn"):
        load_docs([bad])
    # 两个不同目录下同名文件 → PropTableError，消息含“文件名重复”
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_prop_table.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 实现上面列出的 `prop_table.py` 接口**

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_prop_table.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/prop_table.py tests/test_prop_table.py
git commit -m "feat: export node property table from BPMN"
```

---

### Task 6: 导入属性表、就地改写 BPMN、报告

**Files:**
- Modify: `bpmn2graphml/prop_table.py`
- Modify: `bpmn2graphml/xmlutil.py`（如需要，加原子写）
- Test: `tests/test_prop_table.py`

**Interfaces:**
- Consumes: Task 5 的全部；Task 1 的 `set_node_b2g_properties`；Task 3 的 `read_table`、`TableError`；`xmlutil.write_xml`。
- Produces（Task 7、8 使用）：
  - `import_report_path_for(table: Path) -> Path`
  - `@dataclass ImportReport(table: Path, ok: bool, error: str | None, changed_files: list[tuple[Path, int]], backups: list[Path], not_found: list[str], untouched: list[str], same_file_dupes: list[str], folded: list[str], changes: list[str], ignored_columns: list[str])`，`to_text() -> str`，各段顺序与 spec“报告”一节的 1–7 一致，空段写“（无）”。
  - `import_table(table: Path, bpmn_paths: list[Path]) -> ImportReport` —— 数据问题不抛异常，返回 `ok=False` 的报告；无论成败都把 `to_text()` 写入 `import_report_path_for(table)`。

导入步骤（我已定）：
1. `read_table`；`TableError` → 中止。
2. 解析表：第 1 行为表头；第 1 列为名称列（表头内容不限）。其它列表头 `strip()` 后：在 `READONLY_HEADERS` 中 → 记入 `ignored_columns`；为空且该列有非空白数据 → 中止“第 N 列表头为空，但下面有数据”；为空且无数据 → 跳过；重复 → 中止“表头「X」重复”。属性列为 0 → 中止（消息说明：真想清空请保留表头、清空格子）。格子值 `strip()`；整行全空白 → 跳过；名称为空而属性格子有值 → 中止“第 N 行没有节点名称，但填写了属性”（N 为 Excel 行号，即下标 + 1）；名称重复 → 中止“节点名称「X」在表中出现了多行（第 a、b 行）”；没有数据行 → 中止。取值用 `re.split(r"[;；]", cell)` 拆分、去空白、丢空、按序去重。
3. `load_docs`、`group_rows`；`PropTableError` → 中止。
4. 对表中每一行：行名不在分组中 → `not_found`。否则对组内每个节点：新属性 = 节点原有属性中名称属于 `READONLY_HEADERS` 的那些（原样、原顺序）+ 表中各属性列（按列顺序、每个取值一条）。用 `{名称: 取值集合}` 与原属性比较，相同则不动；不同则 `set_node_b2g_properties`，记录变化。
5. 分组中有、表中没有的行名 → `untouched`；表中行对应的组内同一文件有多个节点 → `same_file_dupes`（写“名称（文件）”）。
6. `changes`：每个有变化的节点生成一行 `名称：新增 X=…；修改 Y：旧 → 新；删除 Z`（多值用 `；` 连接）；组内各节点的这一行文字相同则只记一次，否则在名称后加“（文件）”区分。
7. 全部算完后才写文件：只写有变化的文档。对每个：`shutil.copy2` 到 `<名>.bak`；注册该文档的命名空间前缀（`ET.register_namespace`，`ValueError` 忽略）及 `b2g`；`write_xml` 写到 `<名>.tmp`，再 `os.replace` 到原路径。

- [ ] **Step 1: 写失败测试**

测试辅助：`_copy_fixtures(tmp_path) -> list[Path]`；`_canon(el)` 递归生成（tag 字符串, 排序后的属性, strip 后的 text, 子元素列表），跳过 `b2g:properties` 以及因此变空的 `extensionElements`。

```python
def test_export_import_roundtrip_unchanged(tmp_path):
    # 先给某节点写入名称含换行的属性值、并把一个节点名改成带首尾全角空格的形式后保存
    paths = _copy_fixtures(tmp_path)
    export_table(paths, tmp_path / "t.xlsx")
    before = [p.read_bytes() for p in paths]
    r = import_table(tmp_path / "t.xlsx", paths)
    assert r.ok and r.changed_files == []
    assert [p.read_bytes() for p in paths] == before
    assert not any(p.with_name(p.name + ".bak").exists() for p in paths)

def test_fill_clear_delete_add(tmp_path):
    # 导出后用 read_table/write_table 改表：给「部门领导审核」填 负责人=张三；李四，
    # 清空另一节点已有的 负责人，删掉 系统 列，新增 审批时限 列；导入
    # 断言：节点属性正好等于预期列表；来源流程 保留；.bak 存在且等于原文件

def test_same_name_across_files_all_written(tmp_path): ...
def test_folded_subprocess_gets_start_event_row(tmp_path): ...
    # 「启动平台申报」行的属性同时写进申报的开始事件和策划的空子流程

@pytest.mark.parametrize("rows, msg", [
    ([["节点名称", "负责人"], ["审核", "a"], ["审核", "b"]], "出现了多行"),
    ([["节点名称", "a", "a"], ["审核", "1", "2"]], "重复"),
    ([["节点名称", ""], ["审核", "1"]], "表头为空"),
    ([["节点名称", "所在文件"], ["审核", "x"]], "保留表头"),
    ([["节点名称", "负责人"], ["", "张三"]], "没有节点名称"),
    ([["节点名称", "负责人"]], "没有数据"),
])
def test_abort_writes_nothing(tmp_path, rows, msg):
    paths = _copy_fixtures(tmp_path); before = [p.read_bytes() for p in paths]
    write_table(tmp_path / "t.csv", rows)
    r = import_table(tmp_path / "t.csv", paths)
    assert not r.ok and msg in r.error
    assert [p.read_bytes() for p in paths] == before
    assert import_report_path_for(tmp_path / "t.csv").exists()

def test_rewritten_file_semantically_same(tmp_path):
    # 申报.bpmn（含 ext 扩展元素、bpmn: 前缀）导入后：_canon 相同；
    # 根元素序列化文本以 "<bpmn:definitions" 开头；read_bpmn 能读；
    # 在原文件里预先插入一条 <!-- 注释 -->，导入后仍在

def test_second_import_changes_nothing(tmp_path):
    # 同一张改过的表导入两次：第二次 changed_files == []，.bak 内容仍是最初的原文件

def test_whitespace_cells_and_headers(tmp_path):
    # 表头 " 负责人 "、格子 "  " → 属性名「负责人」，该节点不写这个属性

def test_report_sections(tmp_path):
    # to_text() 含：「找不到对应节点」「表中没有的节点」「被忽略的列」以及 not_found 中的名称
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_prop_table.py -v`
Expected: 新测试失败

- [ ] **Step 3: 实现 `import_table`、`ImportReport`、`import_report_path_for`**

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/prop_table.py bpmn2graphml/xmlutil.py tests/test_prop_table.py
git commit -m "feat: import property table into BPMN in place with report"
```

---

### Task 7: 命令行 `props-export` / `props-import`

**Files:**
- Modify: `bpmn2graphml/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `export_table`、`import_table`、`import_report_path_for`、`PropTableError`、`TableError`。
- `props-export INPUTS... -o OUT`：成功打印 `ExportSummary.to_text()`，返回 0；`PropTableError`/`TableError`/`OSError` → stderr `错误：…`，返回 1。
- `props-import TABLE INPUTS...`：打印 `ImportReport.to_text()` 和报告文件路径；`ok` 为真返回 0，否则 1。
- 更新模块 docstring。

- [ ] **Step 1: 写失败测试**

```python
def test_cli_props_roundtrip(tmp_path, capsys):
    paths = [shutil.copy(p, tmp_path / p.name) for p in fixture_paths()]
    table = tmp_path / "t.xlsx"
    assert main(["props-export", *map(str, paths), "-o", str(table)]) == 0
    assert main(["props-import", str(table), *map(str, paths)]) == 0
    assert "t.import-report.txt" in capsys.readouterr().out

def test_cli_props_import_abort(tmp_path):
    (tmp_path / "t.csv").write_text("节点名称\n审核\n", encoding="utf-8")
    paths = [shutil.copy(p, tmp_path / p.name) for p in fixture_paths()]
    assert main(["props-import", str(tmp_path / "t.csv"), *map(str, paths)]) == 1
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_cli.py -v`
Expected: SystemExit（未知子命令）

- [ ] **Step 3: 在 `cli.py` 中加两个子命令**

- [ ] **Step 4: 运行测试**

Run: `python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/cli.py tests/test_cli.py
git commit -m "feat: props-export and props-import commands"
```

---

### Task 8: 图形界面“属性表”页签 + README

**Files:**
- Modify: `bpmn2graphml/gui.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 5/6 的 `export_table`、`import_table`、`import_report_path_for`、`PropTableError`；`table_io.TableError`。
- 页签 `_build_props_tab()`，标签文字“属性表”，放在两个已有页签之后：
  - 说明标签：`BPMN 文件（导入时会直接修改这些文件，修改前自动备份为 .bak）：`
  - 列表 `self.prop_files`（`selectmode="extended"`），右侧按钮“添加…”“移除”（复用与合并页签相同的添加去重逻辑，抽成接收 Listbox 参数的辅助函数）。
  - 按钮行：“导出表格…”“导入表格…”“在查看器中打开”。
  - 结果区 `self.props_log = _log_box(tab)`。
- 导出：`asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel 工作簿", "*.xlsx"), ("CSV 文件", "*.csv")])`，成功后结果区显示 `ExportSummary.to_text()`。
- 导入：`askopenfilename(filetypes=[("表格文件", "*.xlsx *.csv"), ("所有文件", "*.*")])`，结果区显示 `ImportReport.to_text()` 与报告文件路径；`ok` 为假时另弹 `messagebox.showerror("导入已中止", report.error)`。
- 在查看器中打开：列表选中项中的第一个，否则列表第一个；列表为空时报错提示。
- 列表为空时点导出/导入：`messagebox.showerror("错误", "请先添加 BPMN 文件")`。
- `_ERRORS` 加入 `PropTableError`、`TableError`。
- README：在“可视化查看器”之后新增“属性表”一节：用途、GUI 与命令行用法、表格结构（含只读列）、多值分号、以表格为准的规则、中止条件、备份与报告、空子流程归并、已知限制（只读第一个工作表、不支持 .xls、数字/日期/CSV 的说明）。

- [ ] **Step 1: 实现页签**

- [ ] **Step 2: 冒烟检查**

Run:
```bash
python -c "import tkinter as tk; from bpmn2graphml.gui import App; r=tk.Tk(); r.withdraw(); a=App(r); print([a.notebook.tab(i,'text') for i in a.notebook.tabs()]); r.destroy()"
```
Expected: `['BPMN → GraphML', 'GraphML → BPMN', '属性表']`

- [ ] **Step 3: 写 README 一节**

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add bpmn2graphml/gui.py README.md
git commit -m "feat: property table tab in GUI; document it"
```

---

### Task 9: 端到端验证与示例表

**Files:** 无代码改动（产物放在已被忽略的 `out/` 下）。

- [ ] **Step 1: 生成示例**

把三个 fixture 复制到 `out/props_demo/`；`props-export` 导出 `out/props_demo/属性表示例.xlsx`；用 `table_io` 读入后加两列 `负责人`、`信息系统`，给约一半的行填假数据（含多值 `OA；科研管理系统`），写回同一个 xlsx；`props-import` 导入。

Expected: 返回 0，报告列出 3 个文件被修改、`.bak` 存在。

- [ ] **Step 2: 在查看器中检查**

用 Playwright 打开查看器并载入 `out/props_demo/科技创新平台申报.bpmn`：属性下拉框中有“负责人”“信息系统”；选“信息系统 → OA”，高亮节点数等于标签计数；「（未设置）」计数等于未填的节点数。

- [ ] **Step 3: 全量测试**

Run: `python -m pytest -q` 和 `npm test`
Expected: 全部通过

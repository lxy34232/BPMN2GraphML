# BPMN ⇄ yEd GraphML 合并转换器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把多个 BPMN 2.0 文件合并为一个 yEd 可布局、可编辑的 graphml，再把 yEd 保存的 graphml 转回 BPMN（合并成一个文件 / 拆回原文件两种模式）。

**Architecture:** 一个内部图模型（`model.py`）贯穿全程；每个节点/连线都带着它代表的全部原始元素（`Origin`），因此任何合并都不丢信息，拆分模式可以精确还原。读写器各自只负责一种格式；`pipeline.py` 把它们串起来，供 CLI 和 tkinter 界面共用。

**Tech Stack:** Python ≥ 3.10，仅标准库（`xml.etree.ElementTree`、`tkinter`、`json`、`uuid`、`argparse`）；测试用 pytest 8。

**Spec:** `docs/superpowers/specs/2026-10-19-bpmn-yed-merge-design.md`

## Global Constraints

- Python ≥ 3.10；运行时**只用标准库**，pytest 仅为开发依赖。
- 输出 BPMN 的命名空间前缀固定为 `bpmn2` / `bpmndi` / `dc` / `di` / `xsi`；DI id 为 `<元素id>_di`。
- 输出文件一律 UTF-8，带 `<?xml version="1.0" encoding="UTF-8"?>` 声明。
- 新元素 ID：`"EBPM_" + str(uuid.uuid4())`。
- 同名匹配：`name.strip()` 非空且完全相等，且只跨**不同文件**。
- 拆分模式中原始元素的 ID、类型、属性、子元素**一律不改**。
- 界面文字和报告用中文。
- yEd 版本为 3.25.1（经典 `y:` graphml 格式），安装在 `C:\Program Files\yWorks\yEd\yEd.exe`。

## Review Focus

1. **跨文件 ID 冲突**：bpmn.io 风格的文件都叫 `Task_1`、`StartEvent_1`。合并模式下 ID 必须唯一（冲突的改为 `Task_1_2`，并给出警告）；拆分模式下仍写回原 ID。→ Task 2 `test_id_collision_renamed`，Task 5 `test_split_roundtrip_exact`。
2. **yEd 保存时会把节点、连线和 key 的 id 改成 `n0`/`e0`/`d0`**：读取时只能靠 `attr.name` 和 `bpmn_id` 数据识别。→ Task 4 用 `simulate_yed_save` 覆盖。
3. **在 yEd 里复制粘贴节点**会产生重复的 `bpmn_id`：第二个当作新节点处理（分配新 ID、无 origin）并警告。→ Task 4 `test_duplicate_bpmn_id_from_copy_paste`。
4. **在 yEd 里把已有连线改接到别的节点**：两种模式都按新的端点输出；拆分模式下若新端点不在该文件中，就跳过这条连线并警告。→ Task 5 `test_split_reconnected_edge`。
5. **输入不是 BPMN 或 XML 损坏**（包括误选文件）：给出带文件名的明确错误，CLI 返回 1、界面弹出提示，不要直接崩溃显示堆栈。→ Task 1 `test_invalid_file_raises`，Task 6 `test_cli_bad_input`。

---

## File Structure

```
pyproject.toml                 # 项目元数据，pytest 配置
.gitignore
README.md                      # 中文使用说明（含 yEd 操作步骤）
bpmn2graphml/
  __init__.py
  __main__.py                  # 无参数 → GUI；有参数 → cli.main
  model.py                     # Origin / Node / Edge / SourceInfo / Graph，常量
  bpmn_reader.py               # read_bpmn
  merger.py                    # merge, normalize_events, MergeReport
  yed_styles.py                # BPMN 类型 ⇄ yEd 样式 映射表
  graphml_writer.py            # write_graphml
  graphml_reader.py            # read_graphml
  bpmn_writer.py               # write_merged_bpmn, write_split_bpmn, 几何辅助函数
  pipeline.py                  # bpmn_to_graphml, graphml_to_bpmn（CLI/GUI 共用）
  cli.py                       # argparse：merge / tobpmn
  gui.py                       # tkinter App
tests/
  conftest.py                  # FIX 路径、fixture 加载辅助
  helpers.py                   # make_graph（手工构造小图）
  yed_sim.py                   # simulate_yed_save 及编辑辅助（模拟 yEd 中的操作）
  fixtures/
    科技创新平台策划.bpmn        # 根目录参考文件的副本（根目录原文件保留不动）
    科技创新平台申报.bpmn        # 手写，见 Task 1
    平台建设运行.bpmn            # 手写，见 Task 1
  test_bpmn_reader.py
  test_merger.py
  test_graphml_writer.py
  test_graphml_reader.py
  test_bpmn_writer.py
  test_cli.py
```

（与设计相比新增 `pipeline.py`：CLI 和界面共用同一组函数，避免重复。）

---

### Task 1: 项目骨架、数据模型与 BPMN 读取

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `bpmn2graphml/__init__.py`, `bpmn2graphml/model.py`, `bpmn2graphml/bpmn_reader.py`
- Create: `tests/conftest.py`, `tests/fixtures/*.bpmn`（三个）
- Test: `tests/test_bpmn_reader.py`

**Interfaces:**
- Produces（`model.py`）：
  ```python
  BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
  BPMNDI_NS, DC_NS, DI_NS, XSI_NS  # 标准 URI
  FLOW_NODE_TYPES: frozenset[str]  # task manualTask userTask serviceTask scriptTask sendTask receiveTask
                                   # businessRuleTask subProcess callActivity startEvent endEvent
                                   # intermediateThrowEvent intermediateCatchEvent exclusiveGateway
                                   # parallelGateway inclusiveGateway eventBasedGateway complexGateway
  EXPANDABLE_TYPES = frozenset({"subProcess", "callActivity"})

  @dataclass
  class Origin:
      file: str                      # 来源文件名去扩展名
      id: str
      bpmn_type: str                 # 本地标签名
      name: str | None               # None = 原文件没有 name 属性
      attrs: dict[str, str]          # 除 id/name/sourceRef/targetRef 外的属性，Clark 记法键
      children_xml: list[str]        # 除 incoming/outgoing 外的子元素，ET.tostring(encoding="unicode")
      order: int                     # 在原文件中的文档顺序
      source_id: str | None = None   # 仅 sequenceFlow
      target_id: str | None = None
      def to_dict(self) -> dict; @staticmethod def from_dict(d: dict) -> "Origin"

  @dataclass
  class Node:
      id: str; bpmn_type: str; name: str | None
      origins: list[Origin]
      bounds: tuple[float, float, float, float] | None = None   # x, y, w, h（左上角）
      expandable: bool = False       # 空的 subProcess/callActivity

  @dataclass
  class Edge:
      id: str; source: str; target: str; name: str | None
      origins: list[Origin]
      waypoints: list[tuple[float, float]] = field(default_factory=list)  # 仅中间弯折点，绝对坐标
      source_port: tuple[float, float] = (0.0, 0.0)   # 相对源节点中心的偏移
      target_port: tuple[float, float] = (0.0, 0.0)
      exported_source: str | None = None   # 写出 graphml 时的端点节点 id（用于识别 yEd 中的改接）
      exported_target: str | None = None

  @dataclass
  class SourceInfo:
      file: str
      namespaces: dict[str, str]        # 前缀 → URI（含默认空前缀 ""）
      definitions_attrs: dict[str, str] # Clark 记法键
      process_attrs: dict[str, str]     # 含 "id"
      diagram_id: str; plane_id: str
      def to_dict(self) -> dict; @staticmethod def from_dict(d: dict) -> "SourceInfo"

  @dataclass
  class Graph:
      nodes: dict[str, Node] = field(default_factory=dict)   # 插入顺序有意义
      edges: dict[str, Edge] = field(default_factory=dict)
      sources: list[SourceInfo] = field(default_factory=list)
      warnings: list[str] = field(default_factory=list)
  ```
- Produces（`bpmn_reader.py`）：`class BpmnReadError(Exception)`；`read_bpmn(path: str | os.PathLike) -> Graph`（单文件：节点/连线 id 即原 ID，每个元素恰有 1 个 origin，`sources` 长度为 1）。

**Fixtures**（手写 XML，均需包含正文所列元素；除特别说明外都写 BPMNDI）：
- `科技创新平台策划.bpmn`：从仓库根目录复制，不做改动。
- `科技创新平台申报.bpmn`：bpmn.io 风格，前缀为 `bpmn:`，`process id="Process_sb"`，不写 process 的 name：
  - `startEvent StartEvent_1 "启动平台申报"`
  - `userTask Task_1 "填写申报材料"`，带属性 `ext:owner="科技管理部"`（`xmlns:ext="http://example.com/ext"`），以及 `<bpmn:extensionElements><ext:info level="1"/></bpmn:extensionElements>`
  - `exclusiveGateway Gateway_1`（**没有** name 属性）
  - `manualTask Task_2 "部门领导审核"`（与参考文件中的任务同名）
  - `endEvent EndEvent_1 "平台申报完成"`
  - 连线：`Flow_1 StartEvent_1→Task_1`、`Flow_2 Task_1→Gateway_1`、`Flow_3 Gateway_1→Task_2 "通过"`、`Flow_4 Gateway_1→Task_1 "退回"`、`Flow_5 Task_2→EndEvent_1`
- `平台建设运行.bpmn`：前缀 `bpmn2:`，`process id="Process_js"`，**不写 BPMNDI**：
  - `startEvent StartEvent_1 "平台申报完成"`、`task Task_1 "平台建设"`、`parallelGateway Gateway_1 name=""`、`endEvent EndEvent_1 "平台建设完成"`
  - 连线：`Flow_1 StartEvent_1→Task_1`、`Flow_2 Task_1→Gateway_1`、`Flow_3 Gateway_1→EndEvent_1`

- [ ] **Step 1: 写骨架**：`pyproject.toml`（`name="bpmn2graphml"`、`requires-python=">=3.10"`、`dependencies=[]`、`[project.optional-dependencies] dev=["pytest>=8"]`、`[project.scripts] bpmn2graphml="bpmn2graphml.cli:main"`、`[tool.pytest.ini_options] testpaths=["tests"]`）；`.gitignore`（`__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`out/`）；按上面的说明写三个 fixture；`tests/conftest.py` 提供 `FIX = Path(__file__).parent / "fixtures"`，以及 `fixture_paths()`，按顺序返回 [策划, 申报, 建设运行] 三个路径。

- [ ] **Step 2: 写失败的测试** `tests/test_bpmn_reader.py`：
  ```python
  START = "EBPM_21298a9b-4681-18a2-2219-eec70541056e"
  GW = "EBPM_2783b857-45a5-40e5-84d6-3b98c770a0b8"
  SUB = "EBPM_5cd3a4cf-43f3-49b0-1962-356448c0579c"
  def test_reads_reference_nodes_and_flows():   # 12 节点，13 连线
      g = read_bpmn(FIX / "科技创新平台策划.bpmn")
      assert len(g.nodes) == 12 and len(g.edges) == 13
      assert g.nodes[START].bpmn_type == "startEvent"
      assert g.nodes[START].name == "接收到外部科技创新平台申报通知"
      assert g.nodes[GW].name == ""
      e = g.edges["EBPM_ea9d4cad-60ee-bf38-be14-817d219d55e7"]
      assert (e.source, e.target, e.name) == ("EBPM_12354ce6-5b67-fc6c-5e49-52763f5c26a9", GW, "审核不通过")
  def test_reads_bounds():           # g.nodes[START].bounds == (312, 162, 56, 56)
  def test_subprocess_marked_expandable():  # g.nodes[SUB].expandable is True；任务节点为 False
  def test_source_info():  # file=="科技创新平台策划"; process_attrs["id"]=="Process_1";
                           # definitions_attrs["id"]=="sample-diagram"; namespaces["bpmn2"]==BPMN_NS;
                           # diagram_id=="BPMNDiagram_1"; plane_id=="BPMNPlane_1"
  def test_origin_single_and_order():  # 每个元素 1 个 origin，origin.id==元素 id，order 严格递增（按文档顺序）
  def test_default_prefix_and_extensions():  # 申报：Task_1.bpmn_type=="userTask"；
      # origins[0].attrs["{http://example.com/ext}owner"]=="科技管理部"；
      # len(children_xml)==1 且包含 "extensionElements"；nodes["Gateway_1"].name is None
  def test_missing_di():          # 建设运行：所有 bounds is None
  def test_invalid_file_raises(tmp_path):  # "not xml" 内容 → pytest.raises(BpmnReadError, match="bad.bpmn")；
                                           # 根元素不是 definitions 的 XML → 同样抛出 BpmnReadError
  def test_unsupported_elements_warn(tmp_path):  # process 里有 textAnnotation 与 laneSet → warnings 中提到两者
  ```

- [ ] **Step 3: 运行** `python -m pytest tests/test_bpmn_reader.py -v`，期望失败：`ModuleNotFoundError: bpmn2graphml`。

- [ ] **Step 4: 实现** `model.py`，以及 `read_bpmn`：
  - 用 `ET.iterparse(path, events=("start-ns",))` 收集命名空间，再用 `ET.parse` 解析。
  - XML 解析失败或根元素不是 `{BPMN_NS}definitions` 时抛出 `BpmnReadError(f"{文件名}: …")`。
  - 遍历全部 `{BPMN_NS}process` 的直接子元素：`FLOW_NODE_TYPES` → Node；`sequenceFlow` → Edge；`incoming`/`outgoing` 跳过；其它元素（laneSet、textAnnotation、dataObject…）只追加一条警告。多于一个 process 时也警告。
  - `expandable` = 类型在 `EXPANDABLE_TYPES` 中，且没有任何子元素的本地名属于 `FLOW_NODE_TYPES`。
  - DI：遍历 `{BPMNDI_NS}BPMNShape`，按 `bpmnElement` 写入 bounds；`diagram_id`/`plane_id` 缺失时用 `"BPMNDiagram_1"`/`"BPMNPlane_1"`。

- [ ] **Step 5: 运行** `python -m pytest tests/test_bpmn_reader.py -v`，期望全部 PASS。

- [ ] **Step 6: 提交**：`git add pyproject.toml .gitignore bpmn2graphml tests && git commit -m "feat: data model and BPMN reader"`

---

### Task 2: 合并规则（merger）

**Files:**
- Create: `bpmn2graphml/merger.py`, `tests/helpers.py`
- Test: `tests/test_merger.py`

**Interfaces:**
- Consumes: Task 1 的 `Graph/Node/Edge/Origin`、`read_bpmn`。
- Produces:
  ```python
  class MergeError(Exception)
  FILE_GAP = 200.0            # 文件之间的横向间距
  @dataclass class MergeGroup:  name: str; kept_id: str; members: list[tuple[str, str]]  # (file, 原 id)
  @dataclass class Expansion:   subprocess_id: str; file: str; target_file: str; entry_id: str
  @dataclass class MergeReport:
      groups: list[MergeGroup]; expansions: list[Expansion]
      retyped: list[tuple[str, str, str]]     # (节点 id, 原类型, 新类型)
      warnings: list[str]
      def to_text(self) -> str                # 中文分节：合并 / 子流程展开 / 类型调整 / 警告
  def merge(graphs: list[Graph]) -> tuple[Graph, MergeReport]
  def normalize_events(graph: Graph) -> list[tuple[str, str, str]]   # 原地改型，返回改动列表
  ```
- `tests/helpers.py`：`make_graph(file: str, nodes: list[tuple[str, str, str | None]], edges: list[tuple[str, str, str, str | None]]) -> Graph`。根据参数构造单文件 Graph（每个元素带 1 个 origin，order 递增；类型在 `EXPANDABLE_TYPES` 中的节点 `expandable=True`；`sources` 中放一个最小的 SourceInfo）。

**算法**（按以下顺序执行，所有节点先以 `(file, 原id)` 为键，用并查集归并）：
1. 校验：文件名（stem）重复时抛出 `MergeError`。
2. 子流程展开：对每个 `expandable` 节点，若其 `name.strip()` 等于**另一个**文件的 stem（或该文件 `process_attrs` 中的 `name`）：
   - 入口 = 目标文件的 startEvent，没有则取目标文件中无入线的节点。子流程并入入口[0]，代表节点取入口[0]（使用它的 ID、类型和位置）。其余入口各加一条合成连线：子流程的每个前驱 → 该入口（`origins=[]`，ID 用 `EBPM_` + uuid），并警告。
   - 出口 = 目标文件的 endEvent，没有则取无出线的节点（并警告）。子流程原有的每条出线改为从出口[0] 出发；对其余每个出口，再复制一条合成连线（`origins=[]`）。
   - 被展开的子流程不参与第 3 步的同名合并。
3. 同名合并：按名称分组；每个文件只取该名称的第一个节点（同一文件里还有同名节点时，其余的不合并并警告）。如果组内跨越 ≥2 个文件就并为一组，代表节点为第一个出现的。去掉 start/end/intermediate 事件之间的差别后，组内类型仍不止一种时发出警告。
4. 折叠：为每组生成一个 Node，`origins` 按出现顺序排列。最终 ID 取代表节点的原 ID；若已被占用，用 `f"{id}_{n}"`（n 从 2 开始取最小可用值）并警告。连线做同样处理。连线端点映射到折叠后的节点。
5. 去重：`(source, target, name)` 相同的连线合并为一条，origins 合并。
6. `normalize_events`：startEvent 有入线、或 endEvent 有出线 → `intermediateThrowEvent`。
7. 位置：第 i 个文件的 x 偏移 = 前面所有文件的最大右边界 + `FILE_GAP`（第一个文件为 0）。没有 bounds 的节点放到所在文件那一列的网格中（`x = 偏移 + (k % 5) * 200`、`y = (k // 5) * 150`，尺寸取 `yed_styles` 的默认值；Task 2 先在 merger 中写死 80×60，Task 3 改为调用 `yed_styles.default_size`）。
8. `merged.sources` = 按顺序合并所有 sources；`merged.warnings` 合并各输入的警告和合并过程中的警告（报告中也有同样的内容）。

- [ ] **Step 1: 写失败的测试** `tests/test_merger.py`（`fx = [read_bpmn(p) for p in fixture_paths()]`）：
  ```python
  def test_fixtures_merge_counts():           # len(nodes)==18, len(edges)==21
  def test_same_name_merged_keeps_first_id():
      # "EBPM_81ba6f70-bd8e-b91e-041e-2556f9ce6d8e" 的 origins 文件 == ["科技创新平台策划","科技创新平台申报"]
      # "Task_2" 不在 nodes 中；名为 "通过" 的连线 target == "EBPM_81ba6f70-..."
  def test_end_start_join_retyped():
      # nodes["EndEvent_1"].bpmn_type == "intermediateThrowEvent"
      # [o.bpmn_type for o in origins] == ["endEvent","startEvent"]
      # ("EndEvent_1","endEvent","intermediateThrowEvent") in report.retyped
  def test_subprocess_expanded():
      # "EBPM_5cd3a4cf-43f3-49b0-1962-356448c0579c" 不在 nodes 中
      # nodes["StartEvent_1"].origins 中有 bpmn_type=="subProcess" 且 file=="科技创新平台策划" 的 origin
      # edges["EBPM_7a6586a2-9327-45b5-1efe-1a37c88d8586"].target == "StartEvent_1"
      # nodes["StartEvent_1"].bpmn_type == "intermediateThrowEvent"
      # report.expansions == [Expansion("EBPM_5cd3a4cf-...","科技创新平台策划","科技创新平台申报","StartEvent_1")]
  def test_empty_names_never_merge():   # 共 5 个网关节点（3 个 name=="" + Gateway_1(None) + 建设运行的网关）
  def test_id_collision_renamed():
      # nodes["Task_1_2"].origins[0] 为 (file "平台建设运行", id "Task_1")；节点和连线的 id 全部唯一；
      # 有一条警告包含 "Task_1"
  def test_same_file_same_name_not_merged():
      # A: a1 task "X", a2 task "X"；B: b1 task "X" → a1 与 b1 合并，a2 单独保留；有警告
  def test_type_mismatch_warns():   # A task "X" + B exclusiveGateway "X" → 合并，类型为 task，警告中包含 "X"
  def test_expansion_outgoing_from_end_events():
      # A: s→sub(name "B")→t；B: bs→bx，bx→be1，bx→be2（be1/be2 为 endEvent）
      # → sub 并入 bs；原 sub→t 连线的 source 变为 be1；另有一条 be2→t 连线，且 origins==[]
  def test_expansion_fallback_without_events():   # B 只有 x→y（都是 task）→ sub 并入 x；出线从 y 出发；有警告
  def test_duplicate_edges_combined():   # A p→q "go"，B p'→q' "go"（同名）→ 1 条连线，2 个 origins
  def test_duplicate_file_stem_raises(): # 两个 file 相同的图 → pytest.raises(MergeError)
  def test_report_text():   # to_text() 包含 "部门领导审核"、"科技创新平台申报"、"EBPM_81ba6f70"
  def test_positions_offset():
      # 所有节点都有 bounds；申报节点的最小 x ≥ 策划节点的最大右边界 + FILE_GAP
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_merger.py -v`，期望失败：`ImportError: merge`。

- [ ] **Step 3: 实现** `merger.py`（按上面的算法）以及 `tests/helpers.py`。

- [ ] **Step 4: 运行** `python -m pytest -v`，期望全部 PASS。

- [ ] **Step 5: 提交**：`git commit -am "feat: merge rules with report"`（先 `git add` 新文件）。

---

### Task 3: yEd 样式映射与 GraphML 输出

**Files:**
- Create: `bpmn2graphml/yed_styles.py`, `bpmn2graphml/graphml_writer.py`
- Modify: `bpmn2graphml/merger.py`（默认尺寸改用 `default_size`）
- Test: `tests/test_graphml_writer.py`

**Interfaces:**
- Consumes: `Graph`、`merge`。
- Produces（`yed_styles.py`）：
  ```python
  @dataclass(frozen=True)
  class YedStyle:
      configuration: str                       # 如 "com.yworks.bpmn.Activity.withShadow"
      properties: tuple[tuple[str, str, str], ...]   # (class, name, value)
      default_size: tuple[float, float]
      border_color: str
      label_inside: bool                       # 任务为 True；事件和网关的标签放在下方
  SUPPORTED_TYPES: tuple[str, ...]            # FLOW_NODE_TYPES 的全部类型
  def yed_style_for(bpmn_type: str) -> YedStyle
  def bpmn_type_from_yed(configuration: str, props: dict[str, str]) -> str   # props: name → value
  def default_size(bpmn_type: str) -> tuple[float, float]
  ```
- Produces（`graphml_writer.py`）：`write_graphml(graph: Graph, path) -> None`。
- graphml 中的数据键（读取方按 `attr.name` 识别）：node 上为 `bpmn_id`、`bpmn_type`、`bpmn_origins`（origins 的 JSON 列表）；edge 上为 `bpmn_id`、`bpmn_origins`、`bpmn_endpoints`（JSON 列表 `[source节点id, target节点id]`）；graph 上为 `bpmn_sources`（JSON，SourceInfo 列表）。JSON 使用 `ensure_ascii=False`。

**样式取值**（来自 yEd 3.25.1 自带示例与 jar 内枚举；属性 class：`com.yworks.bpmn.type` 用 `com.yworks.yfiles.bpmn.view.BPMNTypeEnum`，`com.yworks.bpmn.characteristic` 用 `com.yworks.yfiles.bpmn.view.EventCharEnum`，`com.yworks.bpmn.taskType` 暂定 `com.yworks.yfiles.bpmn.view.TaskTypeEnum`，**Task 7 中核实**）：

| BPMN 类型 | configuration | type | 其它属性 |
|---|---|---|---|
| task / manualTask / userTask / serviceTask / scriptTask / sendTask / receiveTask / businessRuleTask | `com.yworks.bpmn.Activity.withShadow` | `ACTIVITY_TYPE_STATELESS_TASK_PLAIN` | taskType = `TASK_TYPE_ABSTRACT` / `_MANUAL` / `_USER` / `_SERVICE` / `_SCRIPT` / `_SEND` / `_RECEIVE` / `_BUSINESS_RULE` |
| subProcess / callActivity | 同上 | `ACTIVITY_TYPE_SUBPROCESS_PLAIN` | — |
| exclusiveGateway / parallelGateway / inclusiveGateway / eventBasedGateway / complexGateway | `com.yworks.bpmn.Gateway.withShadow` | `GATEWAY_TYPE_DATA_BASED_EXCLUSIVE` / `_PARALLEL` / `_INCLUSIVE` / `_EVENT_BASED_EXCLUSIVE` / `_COMPLEX` | — |
| startEvent / endEvent / intermediateThrowEvent / intermediateCatchEvent | `com.yworks.bpmn.Event.withShadow` | `EVENT_TYPE_PLAIN` | characteristic = `EVENT_CHARACTERISTIC_START` / `_END` / `_INTERMEDIATE_THROWING` / `_INTERMEDIATE_CATCHING` |

反向映射：Activity 的 type 中含 `SUBPROCESS` → subProcess；否则按 taskType 映射，缺省为 task。Gateway 按 type 映射（`GATEWAY_TYPE_PLAIN` 或缺省 → exclusiveGateway）。Event 按 characteristic 映射：`START*` → startEvent，`END` → endEvent，`INTERMEDIATE_CATCHING` → intermediateCatchEvent，其余或缺省 → intermediateThrowEvent。其它 configuration（含 `y:ShapeNode`，即空字符串）→ task。默认尺寸：任务 140×67，网关 50×50，事件 36×36。边框色：任务 `#123EA2`，网关 `#E38B00`，开始事件 `#27AE27`，结束事件 `#C0392B`，中间事件 `#888888`。每个节点都要附加 icon 属性：`java.awt.Color` 类型的 `com.yworks.bpmn.icon.line.color=#000000`、`icon.fill=#ffffff`、`icon.fill2=#d4d4d4`。

**写法要点**：根元素 `graphml` 声明 `xmlns`、`xmlns:y="http://www.yworks.com/xml/graphml"`、`xmlns:yed="http://www.yworks.com/xml/yed/3"`、`xsi:schemaLocation`。key 为 `d6`（`for="node" yfiles.type="nodegraphics"`）、`d10`（`for="edge" yfiles.type="edgegraphics"`），以及上面列出的自定义键。节点结构为 `y:GenericNode` > `y:Geometry`、`y:Fill color="#FFFFFFE6" color2="#D4D4D4CC"`、`y:BorderStyle`、`y:NodeLabel`（任务：`modelName="internal" modelPosition="c"`；其它：`modelName="sandwich" modelPosition="s"`）、`y:StyleProperties`。任务宽度 = `max(原宽, 14 * len(name) + 20)`。连线为 `y:GenericEdge configuration="com.yworks.bpmn.Connection"` > `y:Path sx="0" sy="0" tx="0" ty="0"`（不写弯折点，布局交给 yEd）、`y:LineStyle color="#000000" type="line" width="1.0"`、`y:Arrows source="none" target="delta"`、有名称时加 `y:EdgeLabel`、`y:StyleProperties` 中 type=`CONNECTION_TYPE_SEQUENCE_FLOW`。graphml 中节点 id 直接用 Node.id。

- [ ] **Step 1: 写失败的测试** `tests/test_graphml_writer.py`（`merged, _ = merge(fx)`，写到 `tmp_path/"m.graphml"` 后用 ET 解析）：
  ```python
  def test_style_roundtrip_table():   # 对 SUPPORTED_TYPES 中除 callActivity 外的每个 t：
      s = yed_style_for(t); assert bpmn_type_from_yed(s.configuration, {n: v for _, n, v in s.properties}) == t
  def test_unknown_shape_is_task():   # bpmn_type_from_yed("com.yworks.flowchart.process", {}) == "task"；("", {}) 同上
  def test_writer_emits_yed_bpmn_nodes():
      # 每个节点都是 GenericNode，configuration 属于三种 BPMN 之一
      # bpmn_id=="EBPM_2783b857-..." 的节点：type == "GATEWAY_TYPE_DATA_BASED_EXCLUSIVE"
      # bpmn_id=="EBPM_81ba6f70-..." 的节点：taskType == "TASK_TYPE_MANUAL"，标签文字 == "部门领导审核"
  def test_writer_custom_keys():
      # 存在 attr.name 为 bpmn_id/bpmn_type/bpmn_origins(node)、bpmn_id/bpmn_origins/bpmn_endpoints(edge)、bpmn_sources(graph) 的 key
      # json.loads(graph 的 bpmn_sources) 有 3 项，file 依次为三个 stem
  def test_task_width_fits_label():   # "开展政策研究、进行需求分析" 节点宽度 >= 14*13+20
  def test_edges_sequence_flow():     # 每条边都是 Connection + CONNECTION_TYPE_SEQUENCE_FLOW；"审核不通过" 边有 EdgeLabel
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_graphml_writer.py -v`，期望失败（ImportError）。

- [ ] **Step 3: 实现** `yed_styles.py` 和 `write_graphml`；`merger.py` 中的默认尺寸改为调用 `default_size`。

- [ ] **Step 4: 运行** `python -m pytest -v`，期望全部 PASS。

- [ ] **Step 5: 目测检查（与用户一起）**：`python -c "from bpmn2graphml.bpmn_reader import read_bpmn; from bpmn2graphml.merger import merge; from bpmn2graphml.graphml_writer import write_graphml; import glob; write_graphml(merge([read_bpmn(p) for p in sorted(glob.glob('tests/fixtures/*.bpmn'))])[0], 'out/check.graphml')"`（先 `mkdir out`），然后用 `"/c/Program Files/yWorks/yEd/yEd.exe" out/check.graphml &` 打开。请用户确认：节点显示为 BPMN 图形；人工任务上有手形图标；排他网关里有 “X”；中文标签完整显示。如果任务图标不对，记录下来，留到 Task 7 修正。

- [ ] **Step 6: 提交**：`git add bpmn2graphml tests && git commit -m "feat: yEd BPMN styles and graphml writer"`

---

### Task 4: GraphML 读取（含 yEd 中的编辑）

**Files:**
- Create: `bpmn2graphml/graphml_reader.py`, `tests/yed_sim.py`
- Test: `tests/test_graphml_reader.py`

**Interfaces:**
- Consumes: `yed_styles.bpmn_type_from_yed`、`Origin.from_dict`、`SourceInfo.from_dict`、`write_graphml`。
- Produces：`class GraphmlReadError(Exception)`；`read_graphml(path) -> Graph`。
- `tests/yed_sim.py`（模拟 yEd 保存与编辑，测试共用）：
  ```python
  def simulate_yed_save(src: Path, dst: Path, edit: Callable[[ET.ElementTree], None] | None = None) -> None
      # 先执行 edit(tree)，再把 key id 改为 d0..、节点 id 改为 n0..、边 id 改为 e0..（同步更新所有引用），然后写出
  def find_node(tree, bpmn_id) -> ET.Element
  def set_label(tree, bpmn_id: str, text: str) -> None
  def delete_node(tree, bpmn_id: str) -> None            # 同时删除相连的边
  def add_task(tree, yed_id: str, label: str, task_type: str | None, x: float, y: float) -> None  # 不带 bpmn 数据
  def add_shape_node(tree, yed_id: str, label: str) -> None   # y:ShapeNode
  def add_edge(tree, yed_id: str, source_yed: str, target_yed: str) -> None
  def reconnect_edge(tree, edge_bpmn_id: str, new_target_bpmn_id: str) -> None
  def duplicate_node(tree, bpmn_id: str, new_yed_id: str) -> None  # 模拟复制粘贴，bpmn 数据原样复制
  ```
  （注意：编辑在改 id 之前执行，所以编辑时节点的 yEd id 等于 bpmn id。）

**读取规则**：
- key 按 `attr.name` / `yfiles.type` 识别，不依赖 key id。
- 递归遍历所有 `node`：带 `yfiles.foldertype` 或含子 `graph` 的组节点本身跳过，只读其中的子节点。
- 节点：
  - `y:Geometry` → bounds；所有 `y:NodeLabel` 的文本拼接后 strip → label。
  - 类型：优先取 `bpmn_type` 数据，否则用 `bpmn_type_from_yed(configuration, StyleProperties)`。
  - ID：取 `bpmn_id`；缺失或重复时生成新的 `EBPM_` ID，origins 置空并警告（文字中写明“重复”）。
  - 改名：label ≠ 存储的名称（origins[0].name，None 视为 ""）时，`node.name = label`，并写入**每一个** origin 的 name；没有改名时保留 None。
- 边：
  - source/target 通过 yEd id 映射到节点 id。
  - `y:Path` 的 sx/sy/tx/ty → port；`y:Point` → waypoints；`y:EdgeLabel` → name（规则同节点）。
  - `bpmn_endpoints` → exported_source/target。
  - ID 规则同节点。
- graph 级 `bpmn_sources` → `sources`。缺失时（例如用户在 yEd 里新建的图）给一个默认 SourceInfo：file `"merged"`、process id `"Process_1"`。
- 文件解析失败时抛出 `GraphmlReadError`，信息中带文件名。

- [ ] **Step 1: 写失败的测试** `tests/test_graphml_reader.py`（基础：`merged` → `write_graphml(a)` → `simulate_yed_save(a, b, edit)` → `read_graphml(b)`）：
  ```python
  def test_roundtrip_identity():   # 没有编辑：节点 id 集合、类型、名称、origins（to_dict 比较）与 merged 相同；
                                   # 边 id/端点/origins 相同；sources 相同；exported_source == source
  def test_geometry_read():        # 把某节点的 Geometry x 改成 1000 → bounds[0] == 1000
  def test_rename_applies_to_all_origins():   # set_label("EBPM_81ba6f70-...", "部门负责人审核") →
                                              # node.name 与两个 origin 的 name 都等于新名称
  def test_new_task_from_palette():   # add_task(..., task_type="TASK_TYPE_USER") → bpmn_type=="userTask"，origins==[]，
                                      # id 匹配 r"^EBPM_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
  def test_new_plain_shape_is_task():
  def test_new_edge_sequence_flow():  # origins==[]，exported_source is None，id 为 EBPM 格式
  def test_duplicate_bpmn_id_from_copy_paste():  # 原节点保留原 id；副本获得新 id、origins==[]；warnings 中有“重复”
  def test_waypoints_and_ports():     # 把某边的 Path 改为 sx="10" sy="0"，并加两个 Point → source_port==(10,0)，waypoints 依序
  def test_group_nodes_ignored():     # 把两个节点包进 yEd 组节点（嵌套 graph）→ 两个节点都能读到，组节点本身不是 Node
  def test_invalid_graphml_raises(tmp_path):
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_graphml_reader.py -v`，期望失败。

- [ ] **Step 3: 实现** `tests/yed_sim.py` 和 `read_graphml`。

- [ ] **Step 4: 运行** `python -m pytest -v`，期望全部 PASS。

- [ ] **Step 5: 提交**：`git add bpmn2graphml tests && git commit -m "feat: graphml reader with yEd edit detection"`

---

### Task 5: BPMN 输出（合并模式 + 拆分模式）

**Files:**
- Create: `bpmn2graphml/bpmn_writer.py`
- Test: `tests/test_bpmn_writer.py`

**Interfaces:**
- Consumes: `Graph`、`normalize_events`、`yed_styles.default_size`、`read_bpmn`（测试中用）。
- Produces：
  ```python
  SPLIT_MARGIN = 50.0
  def clip_to_rect(center: tuple[float, float], toward: tuple[float, float],
                   bounds: tuple[float, float, float, float]) -> tuple[float, float]
  def edge_points(src_bounds, tgt_bounds, bends, source_port, target_port) -> list[tuple[float, float]]
      # port 不为 (0,0) 时端点 = 中心 + port；否则从中心朝下一点（bends[0]，没有则取对方中心）裁剪到矩形边框
  def write_merged_bpmn(graph: Graph, path) -> list[str]     # 返回警告
  def write_split_bpmn(graph: Graph, out_dir) -> list[str]   # 每个 source 写出 <file>.bpmn，返回警告
  ```

**共用序列化**：`ET.register_namespace` 注册 `bpmn2/bpmndi/dc/di/xsi`，以及 sources 中其它不冲突的前缀（BPMN 模型命名空间不管原来用什么前缀，一律写成 `bpmn2`）。
- 根元素 `bpmn2:definitions` 带上 definitions_attrs；`bpmn2:process` 带上 process_attrs。
- 先写全部 flowNode：属性顺序为 `id`、`name`（name 不为 None 时才写）、其余 attrs；然后是 `children_xml`（`ET.fromstring` 还原），最后是 `incoming`/`outgoing`。
- 再写 sequenceFlow：属性顺序为 `id`、`sourceRef`、`targetRef`、`name`、其余 attrs，再加 children_xml。
- 然后写 `bpmndi:BPMNDiagram`/`BPMNPlane`（id 来自 SourceInfo，`bpmnElement` = process id），以及每个节点的 `BPMNShape`（`dc:Bounds`）、每条边的 `BPMNEdge`（`di:waypoint`，由 `edge_points` 算出）。
- 节点缺少 bounds 时用 (0, 0) 和默认尺寸。
- 写出时用 `ET.ElementTree.write(path, encoding="UTF-8", xml_declaration=True)`。

**合并模式**：先对一份深拷贝执行 `normalize_events`（处理 yEd 中新增连线造成的情况）。definitions/命名空间取 `sources[0]`，process id 取 `sources[0].process_attrs["id"]`。元素就是 graph 中的节点和边（使用合并后的 id、类型、名称；attrs/children_xml 取 origins[0]，没有 origin 时为空）。

**拆分模式**，对每个 source 文件 F：
- 节点：每个节点中 file==F 的每个 origin 都输出一个元素，使用原 id、原类型、名称、attrs、children_xml，bounds 取所在节点的 bounds。
- 新节点（origins 为空）：统计相邻节点所属的文件，归入票数最多的文件（平局按 sources 顺序取前者；没有相邻节点则归入 sources[0]），用 node.id 合成一个 origin。
- 连线：对每条边中 file==F 的每个 origin：
  - 端点未改（`edge.source == edge.exported_source`）时用 `origin.source_id`；
  - 否则用当前源节点中 file==F 的第一个 origin 的 id；找不到就跳过这条连线并警告。target 同理。
  - 合成连线（origins 为空，且 exported_source 不为 None，即 merger 生成的）在拆分模式中跳过。
- 新连线（origins 为空，且 exported_source is None）：写入每个同时包含两端（都有 file==F 的 origin）的文件 F。一个都没有时警告，警告中带上连线 id。
- 排序：节点按 order（新增的排最后），连线同理。
- 平移：使该文件所有 shape 的最小 x、最小 y 都等于 `SPLIT_MARGIN`，waypoint 一起平移。
- 输出前删掉 source/target 不在本文件中的连线（防御性处理，同时警告）。

- [ ] **Step 1: 写失败的测试** `tests/test_bpmn_writer.py`。辅助函数 `pipeline(tmp_path, edit=None)`：merge → write_graphml → simulate_yed_save(edit) → read_graphml，返回 Graph。另写 `same_xml(a: str, b: str) -> bool`：解析后递归比较 Clark 标签名、属性字典、strip 后的 text/tail 和子元素。不用 `ET.canonicalize`，因为前缀会从 `bpmn:` 变成 `bpmn2:`，C14N 文本会不同。
  ```python
  def test_clip_to_rect():   # rect (0,0,100,50)：从 (50,25) 朝 (200,25) → (100,25)；朝 (50,-100) → (50,0)
  def test_edge_points_with_ports():   # src (0,0,100,50)，port (10,0)，tgt (300,0,100,50) → 首点 (60,25)，末点 (300,25)
  def test_split_roundtrip_exact():
      # write_split_bpmn → 生成三个 <stem>.bpmn；每个文件 read_bpmn 后与原 fixture 比较：
      # {(id,type,name)} 相等，{(id,src,tgt,name)} 相等，每个 origin 的 attrs 相等，children_xml 两两 same_xml
      # 特别检查：策划中仍有 subProcess "EBPM_5cd3a4cf-..."；申报的 StartEvent_1 仍为 startEvent
  def test_split_definitions_preserved():
      # 策划输出：definitions id "sample-diagram"，targetNamespace "http://bpmn.io/schema/bpmn"，process id "Process_1"，
      # 原始文本包含 "<bpmn2:definitions"；申报输出 process id "Process_sb"
  def test_split_coordinates_translated():   # 每个输出文件所有 dc:Bounds 的 min x == min y == 50
  def test_merged_output_valid():
      # read_bpmn(合并输出)：18 个节点，id 唯一，每条连线的端点都存在；
      # 原始 XML 中每个节点的 incoming/outgoing 与连线一致；BPMNShape 18 个，BPMNEdge 21 个，每条至少 2 个 waypoint；
      # EndEvent_1 的标签为 intermediateThrowEvent
  def test_merged_renormalizes_after_new_edges():
      # edit：add_edge 从 "EBPM_873ebcef-..." 连到 START（策划的开始事件）
      # → 合并输出中 START 为 intermediateThrowEvent；拆分输出（策划）中 START 仍为 startEvent，且新连线已写入
  def test_split_new_node_assignment():
      # edit：add_task("nX", ...) + add_edge Task_1→nX + add_edge nX→Gateway_1（申报的节点）
      # → 新节点和两条新连线只出现在 科技创新平台申报.bpmn 中
  def test_split_cross_file_new_edge_warned():
      # edit：add_edge 从 "EBPM_873ebcef-..." 连到 "Task_1_2" 所在节点 → 两个文件都没有这条连线，警告中有它的 id
  def test_split_reconnected_edge():
      # edit：reconnect_edge("EBPM_96155149-f4ef-5e3a-7594-53ea337a137d", "EBPM_e68efe62-6af7-7c43-bf10-c0e40f4ef136")
      # → 策划输出中该连线 targetRef == "EBPM_e68efe62-..."
  def test_deleted_node_absent():
      # edit：delete_node("EBPM_69e928b3-1b43-eb55-f45e-5b884aa5853b")
      # → 两种输出中都没有该节点及其连线；所有 sourceRef/targetRef 都能找到对应节点
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_bpmn_writer.py -v`，期望失败。

- [ ] **Step 3: 实现** `bpmn_writer.py`。

- [ ] **Step 4: 运行** `python -m pytest -v`，期望全部 PASS。

- [ ] **Step 5: 提交**：`git add bpmn2graphml tests && git commit -m "feat: BPMN writer with merged and split modes"`

---

### Task 6: pipeline、命令行、图形界面、README

**Files:**
- Create: `bpmn2graphml/pipeline.py`, `bpmn2graphml/cli.py`, `bpmn2graphml/gui.py`, `bpmn2graphml/__main__.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 前面各任务的全部公开函数。
- Produces：
  ```python
  # pipeline.py
  def report_path_for(graphml_path: Path) -> Path    # m.graphml → m.merge-report.txt
  def bpmn_to_graphml(inputs: list[Path], output: Path) -> MergeReport   # 同时写出报告文本
  def graphml_to_bpmn(input: Path, merged: Path | None, split_dir: Path | None) -> list[str]
  # cli.py
  def main(argv: list[str] | None = None) -> int
      # merge FILES... -o OUT
      # tobpmn GRAPHML [--merged FILE] [--split DIR]（两者至少一个，否则 parser.error）
      # 捕获 BpmnReadError/GraphmlReadError/MergeError → 错误写到 stderr，返回 1；警告打印到 stdout
  # gui.py
  class App(ttk.Frame):
      def __init__(self, master: tk.Tk)        # ttk.Notebook 两个页签
  def run() -> None                            # 创建 Tk，标题 "BPMN ⇄ yEd GraphML 转换器"，mainloop
  ```

**界面**：
- 页签「BPMN → GraphML」：文件列表（Listbox），按钮「添加…」「移除」「上移」「下移」；输出路径框和「浏览…」按钮；「合并并导出」按钮；只读的报告文本框。
- 页签「GraphML → BPMN」：输入路径框和「浏览…」按钮；复选框「合并为一个文件」（附路径框和浏览按钮）、「拆分回原文件」（附文件夹框和浏览按钮）；「转换」按钮；结果文本框。
- 出错时用 `messagebox.showerror("错误", str(e))` 提示。成功后在文本框里显示报告或警告，并写明输出路径。

**README**（中文）：安装要求（Python ≥ 3.10）；启动方法（`python -m bpmn2graphml`）；CLI 示例；yEd 操作步骤：打开 graphml → 菜单「布局 › 分层」（Layout › Hierarchical）→ 需要时从右侧「BPMN」面板拖入新节点 → 「文件 › 保存」，保持 graphml 格式；合并规则摘要；两种导出模式的区别；已知限制（不支持泳道、消息流、数据对象、注释）。

- [ ] **Step 1: 写失败的测试** `tests/test_cli.py`：
  ```python
  def test_cli_merge(tmp_path):   # main(["merge", *fixture_paths(), "-o", str(tmp_path/"m.graphml")]) == 0；
                                  # m.graphml 存在；m.merge-report.txt 存在且包含 "部门领导审核"
  def test_cli_tobpmn_both(tmp_path):   # 接上一步：main(["tobpmn", g, "--merged", o, "--split", d]) == 0；
                                        # o 存在；d 下有 3 个 .bpmn
  def test_cli_tobpmn_requires_mode(tmp_path):   # 不给 --merged/--split → pytest.raises(SystemExit)
  def test_cli_bad_input(tmp_path, capsys):   # merge 一个内容为 "hello" 的 x.bpmn → 返回 1；stderr 包含 "x.bpmn"
  def test_gui_builds():   # root=tk.Tk(); root.withdraw(); app=App(root)；notebook 有 2 个页签；root.destroy()
                           # 遇到 tk.TclError 时 pytest.skip
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_cli.py -v`，期望失败。

- [ ] **Step 3: 实现** `pipeline.py`、`cli.py`、`gui.py`、`__main__.py`（`sys.argv[1:]` 为空时调用 `gui.run()`，否则 `sys.exit(cli.main())`）；写 README。

- [ ] **Step 4: 运行** `python -m pytest -v`，期望全部 PASS。手动运行 `python -m bpmn2graphml`，确认窗口能打开，两个页签都能完成一次转换。

- [ ] **Step 5: 提交**：`git add . ':!科技创新平台策划.bpmn' && git commit -m "feat: CLI, tkinter GUI and README"`（根目录的参考文件是否纳入版本库由用户决定，这里不提交）。

---

### Task 7: 端到端验证（真实 yEd + bpmn-js 渲染）

**Files:**
- Create: `tests/fixtures/yed_saved.graphml`（用户在 yEd 中真实保存的文件）
- Modify（如有需要）: `bpmn2graphml/yed_styles.py`
- Test: `tests/test_graphml_reader.py`（新增 `test_real_yed_file`）

- [ ] **Step 1: 生成输入**：`python -m bpmn2graphml merge tests/fixtures/科技创新平台策划.bpmn tests/fixtures/科技创新平台申报.bpmn tests/fixtures/平台建设运行.bpmn -o out/e2e.graphml`，然后用 `"/c/Program Files/yWorks/yEd/yEd.exe" out/e2e.graphml &` 打开。

- [ ] **Step 2: 请用户在 yEd 中操作**：「布局 › 分层」；从 BPMN 面板拖入一个“用户任务”，并从某个已有节点连一条线过去；改一个节点的名称；保存为 `out/e2e_saved.graphml`。

- [ ] **Step 3: 核实 taskType**：在 `out/e2e_saved.graphml` 中找到 `com.yworks.bpmn.taskType` 那一行，确认 class 和取值。若与 `TaskTypeEnum` 不符，更新 `yed_styles.py` 并重跑 `python -m pytest -v`。再确认自定义数据键（`bpmn_origins` 等）在 yEd 保存后仍然存在。

- [ ] **Step 4: 回归夹具**：把 `out/e2e_saved.graphml` 复制为 `tests/fixtures/yed_saved.graphml`，新增 `test_real_yed_file`：用 read_graphml 读取后，原有的 18 个节点 id 都在；新增节点类型为 userTask；改名生效。运行 `python -m pytest -v`，期望 PASS。

- [ ] **Step 5: 转回并渲染**：`python -m bpmn2graphml tobpmn out/e2e_saved.graphml --merged out/merged.bpmn --split out/split`。在会话临时目录（scratchpad）写一个页面，用 `https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-viewer.production.min.js` 渲染每个输出文件。用 Playwright 打开，确认 `importXML` 的 `warnings` 为空、截图中布局与 yEd 一致，并把截图给用户看。

- [ ] **Step 6: 用户在原平台验证**：请用户把 `out/merged.bpmn` 和 `out/split/*.bpmn` 导入原平台，确认能导入，尤其关注 `intermediateThrowEvent`。如有问题，回到相应任务修正。

- [ ] **Step 7: 提交**：`git add tests bpmn2graphml && git commit -m "test: real yEd-saved regression fixture"`

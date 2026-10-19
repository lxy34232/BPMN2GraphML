# BPMN ⇄ yEd GraphML 合并转换器 — 设计与实施计划

## Context（为什么做）

用户手上有多份标准 BPMN 2.0 流程文件（参考：项目根目录 `科技创新平台策划.bpmn`，`bpmn2:` 前缀、带 BPMNDI 坐标、ID 形如 `EBPM_<uuid>`，来自某企业流程平台，兼容 bpmn.io）。这些流程彼此关联，但分散在不同文件里。目标是：

1. 把多个 BPMN 文件**合并**成一张图，相同节点自动合并为一个；
2. 输出为 yEd 可读的 `.graphml`，用户在 yEd 里跑自动布局，并可能手工增删改节点/连线；
3. 再把 yEd 保存的 graphml **转回 BPMN 2.0**，带上 yEd 布局坐标，既能导回原平台，也能在 bpmn.io / Camunda 打开。

仓库目前为空（只有参考文件），从零开始。

## 已确认的需求（用户决定）

- **相同节点的判定**：两种都要——(a) 不同文件中**名称完全相同**的节点；(b) A 流程的结束事件与 B 流程**同名**的开始事件（首尾相接）。
- **合并方式**：合并成**一个节点**，所有连线都接到这一个节点上。
- **空子流程展开**：形如参考文件末尾的空 `subProcess`“科技创新平台申报”，若有同名的文件/流程，则**展开成那个流程的内容**。
- **技术形态**：Python + 简单图形界面。
- **BPMN 输出用途**：既要能**导回原平台**（保留原 ID 和 `bpmn2:` 写法），也要能在**通用工具**（bpmn.io/Camunda）打开。
- **两种 BPMN 输出模式都要**：(1) **合并模式**——一个合并后的大流程文件；(2) **拆分模式**——拆回原来的每个文件，保留全部原 ID、原类型，只是布局换成 yEd 排好的。
- **首尾事件合并**：在合并模式中改为中间事件（`intermediateThrowEvent`）；拆分模式中恢复原类型。
- **文件对应**：导出的文件名（去掉 `.bpmn`）与流程名/子流程名**完全一致**，按文件名匹配即可。
- **yEd 中的编辑**：用户会改名、删除，**也会新增**节点和连线，这些都要能带回 BPMN。
- **元素范围**：与参考文件差不多——开始/结束事件、任务（manualTask 等）、排他网关等网关、子流程、顺序流；**没有泳池/泳道**。

## 目标 / 非目标 / 反目标

- 目标：多文件合并 → yEd graphml → （用户在 yEd 布局/编辑）→ BPMN 2.0，往返不丢节点、连线、名称、原 ID。
- 非目标（v1）：泳池/泳道、消息流、数据对象、注释、非空子流程的内部内容；程序内自动布局（布局由 yEd 完成）。
- 反目标（技术上能跑也算失败）：
  - 空名称节点（如网关 `name=""`）被互相合并；
  - 静默地合并了不该合并的节点而用户看不到——每次合并必须有报告；
  - 原有 `EBPM_` ID 丢失或被改写，导致无法导回原平台；
  - 输出的 BPMN 在 bpmn.io 中打不开或无布局。

## 方案

### 技术栈（我的决定）
- Python ≥ 3.10，**仅标准库**：`xml.etree.ElementTree` 解析/生成 XML，`tkinter` 做界面，`uuid`、`json`。
- 测试：`pytest`（开发依赖）。
- 同时提供命令行入口，GUI 只是对同一核心函数的包装。

### 目录结构
```
bpmn2graphml/
  __init__.py
  __main__.py        # python -m bpmn2graphml → 启动 GUI；带参数 → CLI
  model.py           # 内部图模型 Node / Edge / Graph（dataclass）
  bpmn_reader.py     # BPMN 2.0 → Graph（按命名空间解析，与前缀无关）
  merger.py          # 多个 Graph → 一个 Graph + MergeReport
  yed_styles.py      # BPMN 类型 ⇄ yEd BPMN 图形样式 映射表
  graphml_writer.py  # Graph → yEd graphml
  graphml_reader.py  # yEd graphml → Graph（含用户新增元素的识别）
  bpmn_writer.py     # Graph → BPMN 2.0（semantic + BPMNDI）
  cli.py             # merge / tobpmn 两个子命令
  gui.py             # tkinter 界面
tests/
  fixtures/          # 参考文件 + 手写的配套测试文件
  test_*.py
pyproject.toml
README.md
docs/superpowers/specs/2026-10-19-bpmn-yed-merge-design.md   # 本设计的仓库内副本
```

### 内部模型（model.py）
- `Origin`（一个原始元素的完整记录）：`file`（文件名去扩展名）, `id`, `bpmn_type`（本地标签名，如 `manualTask`、`exclusiveGateway`、`startEvent`）, `name`, `extra_attrs`（其它原始属性，原样保留）, `extension_xml`（原始 `extensionElements` 等子元素序列化，原样保留）, `order`（在原文件中的位置，拆分输出时按原顺序写回）, 原连线还有 `source_id`/`target_id`。
- `Node`: `id`（合并模式使用的 ID = 首个 origin 的 ID）, `bpmn_type`（合并模式下的类型）, `name`, `origins: list[Origin]`, `bounds (x,y,w,h)`。
- `Edge`: `id`, `source`, `target`, `name`, `origins: list[Origin]`, `waypoints`, `label_bounds`。
- `Graph`: nodes（dict，保持插入顺序）, edges, `sources`：每个输入文件的 definitions 属性/命名空间、process 属性（id、name、isExecutable 等）、BPMNDiagram/BPMNPlane 的 id。合并模式用首个文件的 definitions，拆分模式用各自的。
- **关键不变量**：任何原始元素都不会被丢弃——合并、子流程展开、事件改型都只是把 origin 挂到某个合并节点上，因此拆分模式总能还原每个原文件。

### BPMN 读取（bpmn_reader.py）
- 按命名空间 URI `http://www.omg.org/spec/BPMN/20100524/MODEL` 查找元素，不依赖 `bpmn2:` 前缀。
- 读取所有 `process` 下的 flowNode（任务各类、事件各类、网关各类、subProcess、callActivity）和 `sequenceFlow`；忽略 `incoming/outgoing` 子元素（输出时由连线重新生成）。
- 从 BPMNDI 读取 `Bounds` 与 `waypoint`，没有 DI 时 bounds 留空。
- 遇到不支持的元素（lane、dataObject、textAnnotation、messageFlow）→ 记入报告警告，不中断。

### 合并规则（merger.py）——按输入顺序依次处理
1. **子流程展开**（先做）：`subProcess`/`callActivity` 若**没有内部 flowNode**，且其名称等于另一输入文件的**文件名（去扩展名）**（也接受 `process@name`），则：
   - 目标流程的入口 = 其开始事件；没有开始事件则取没有入线的节点。子流程节点**并入第一个入口节点**（子流程作为 origin 挂上去，拆分模式据此还原、并取该节点位置）；有多个入口时，其余入口也连上子流程的前驱节点，并在报告中警告。
   - 子流程的出线 → 改为从目标流程的每个结束事件出发；没有结束事件则从没有出线的节点出发，并警告。
   - 找不到目标文件则当作普通节点。
2. **同名合并**：跨**不同文件**、`name.strip()` 非空且完全相等的节点合并为一个；**同一文件内同名不合并**（我的决定）。
   - 合并节点使用**首个出现**节点的 ID、类型和位置；所有 origin 都挂在该节点上；其它节点的连线全部改接到它。
   - 类型不一致（例如任务 vs 网关）时仍合并、保留首个类型，并在报告中**警告**。
3. **事件规范化**（合并后统一做，用户已确认）：开始事件有了入线、或结束事件有了出线 → 合并模式中改为 `intermediateThrowEvent`（无类型中间事件），保留 ID 和名称；origin 中仍保留原类型，拆分模式写回原类型。这同时覆盖了“A 结束 = B 开始”的情况。
4. 去重：合并后起止点相同且名称相同的重复连线合并为一条（origins 合并）。
5. 产出 `MergeReport`：列出每一组合并（名称、涉及的文件和原 ID、保留的 ID）、每次子流程展开、所有警告。GUI 中显示，并另存为 `<输出名>.merge-report.txt`。

### GraphML 输出（graphml_writer.py + yed_styles.py）
- 使用 **yEd 自带 BPMN 图形**（`y:GenericNode`，configuration `com.yworks.bpmn.Activity.withShadow` / `com.yworks.bpmn.Gateway.withShadow` / `com.yworks.bpmn.Event.withShadow`，样式属性 `com.yworks.bpmn.taskType` / `activityType` / `type` / `characteristic`；连线 `y:GenericEdge` `com.yworks.bpmn.Connection` + `CONNECTION_TYPE_SEQUENCE_FLOW`）。这样用户从 yEd 面板“BPMN”组拖入的新节点，程序能识别类型。**实现第一步必须在 yEd 里手画一份 BPMN 样例并保存，以核对确切的属性名和取值**，映射表放在 `yed_styles.py` 一处维护。
- 每个 node/edge 写自定义 `<data>` 键：`bpmn_id`、`bpmn_type`、`bpmn_origins`（JSON：origin 列表）；graph 级 `<data>` 键 `bpmn_sources`（JSON：各文件的 definitions/process/DI 属性）。这样 graphml 自带全部信息，转回时不需要原文件。yEd 保存时会保留这些自定义数据——**步骤 1 中一并验证**。
- 名称写入 `y:NodeLabel` / `y:EdgeLabel`；节点尺寸沿用 DI 尺寸（缺省：任务 140×67，网关 50×50，事件 36×36）。
- 初始坐标：每个文件的原 DI 坐标按文件横向错开放置，合并节点用首个位置——在 yEd 布局前也可读（我的决定）。
- 不同来源文件可用不同的浅色填充以示区分（可选，我的决定，留给实现者）。

### GraphML 读取（graphml_reader.py）
- 解析 yEd 保存的文件：节点 `y:Geometry`（x,y,w,h 为左上角）、标签文本、连线 `y:Path`（`sx,sy,tx,ty` 为相对节点中心的偏移，`y:Point` 为绝对坐标）、边标签位置。
- 类型判定顺序：`bpmn_type` 数据键 → yEd BPMN 样式属性（`yed_styles` 反查）→ 其它普通图形默认 `task`，连线默认 `sequenceFlow`。**标签文本优先于 `bpmn_name`**（用户可能在 yEd 里改名）。
- 新元素（无 `bpmn_id`）：生成 `EBPM_` + `uuid4()` 形式 ID，与原平台风格一致（我的决定）。
- 被用户删除的元素自然不出现在输出中（两种模式都是）。
- 改名：标签文本写回到合并节点和它的**所有** origin。

### BPMN 输出（bpmn_writer.py）——两种模式，共用同一套序列化代码
- 通用写法：命名空间前缀固定为 `bpmn2/bpmndi/dc/di/xsi`（与参考文件一致，通过 `ET.register_namespace`）；元素顺序仿照参考文件：先 flowNode（每个带 `incoming`/`outgoing` 子元素），再 sequenceFlow；`extra_attrs`、`extension_xml` 原样写回；保留 `name=""` 这类空属性。DI id 用 `<元素id>_di`，与参考文件一致。
- BPMNDI 几何：`BPMNShape` 用 yEd 几何；`BPMNEdge` 路点 = 源端点 + 弯折点 + 目标端点。端点：若 `sx/sy` 为 0，则用节点中心到下一点的连线与节点矩形的交点（裁剪到边框），bpmn.io 中显示正常。
- **合并模式**：一个文件；definitions 用首个输入文件的属性；单个扁平 `process`，沿用首个文件的 process id；节点使用合并节点的 ID 和类型。
- **拆分模式**：输出到一个文件夹，每个原文件生成同名 `.bpmn`（使用该文件自己的 definitions/process/DI 属性）。内容 = 该文件的所有 origin（按 `order` 原顺序、原 ID、原类型——包括被展开的子流程和未改型的开始/结束事件）+ 原连线（原 source/target ID）。每个元素的位置取它所在合并节点在 yEd 中的位置；整体平移，使该文件左上角从 (50,50) 开始（我的决定）。被合并的节点在多个文件里位置相同，正是“同一节点”的含义。
- **用户新增元素在拆分模式中的归属**（我的决定）：新节点归入其相邻节点所属文件中占多数的那个（平局按输入顺序取前者）；新连线写入同时包含两个端点的每个文件；不属于任何单个文件的跨文件新连线不写入，并在报告中警告。

### 界面（gui.py，tkinter）
- 页签一「BPMN → GraphML」：添加/移除/排序多个 BPMN 文件（顺序决定合并时谁是“首个”）、选择输出路径、按钮“合并并导出”、下方文本框显示合并报告。
- 页签二「GraphML → BPMN」：选择 graphml；勾选输出模式「合并为一个文件」/「拆分回原文件」（可同时勾选）；分别选择输出文件和输出文件夹；按钮“转换”；显示结果/警告。
- CLI：`python -m bpmn2graphml merge a.bpmn b.bpmn -o merged.graphml`；`python -m bpmn2graphml tobpmn merged.graphml --merged out.bpmn --split out_dir/`。

## 实施步骤
1. 在 yEd 中手画 BPMN 样例（各类任务/网关/事件/顺序流）保存，提取样式属性 → `yed_styles.py`；仓库内写入设计文档副本。
2. `model.py` + `bpmn_reader.py`，以参考文件做测试。
3. `merger.py`：构造配套测试文件（`科技创新平台申报.bpmn`：开始→任务→结束；第三个文件含与参考文件同名任务、同名的开始/结束事件），测试三条规则 + 空名不合并 + 同文件不合并 + 报告。
4. `graphml_writer.py`，再 `graphml_reader.py`；往返测试（不经 yEd）：BPMN→graphml→BPMN 元素、ID、名称、连线一致。
5. `bpmn_writer.py`：合并模式 + 拆分模式（semantic + DI，端点裁剪）。拆分模式往返测试：每个原文件拆回后，元素 ID/类型/名称/连线集合与原文件**完全一致**（只有 DI 坐标不同）。
6. `cli.py`、`gui.py`、`__main__.py`、README（含 yEd 操作步骤：打开 → 布局 › 分层 → 保存为 graphml）。

## 验证
- `pytest`：读取、合并规则、往返一致性、新增元素识别（用手改的 graphml 夹具模拟 yEd 新增节点/改名/删除）。
- 手动端到端：合并参考文件与测试文件 → 在 yEd 打开，确认显示为 BPMN 图形且有标签 → 布局 › 分层 → 新增一个任务和连线、改一个名称 → 保存 → 转回 BPMN → 在 demo.bpmn.io 打开（可用 Playwright 自动打开并截图）确认渲染和布局正确，原 `EBPM_` ID 保留。
- 拆分模式输出的每个文件也在 demo.bpmn.io 打开检查。
- 用户确认能把两种模式的输出 BPMN 导回其原平台（只能由用户验证；尤其是合并模式中的 `intermediateThrowEvent`）。

## 我替你做的决定（请过目）
- 仅用 Python 标准库（tkinter 界面），命令行与界面共用核心逻辑。
- 同一文件内的同名节点不合并；类型不一致的同名节点仍合并，但会警告。
- 新增元素 ID 用 `EBPM_` + uuid 格式。
- yEd 布局前的初始位置：按文件横向错开放置，沿用原坐标。
- 拆分模式中坐标整体平移到左上角，新增元素按相邻节点归属文件。
- 子流程目标没有开始/结束事件时，回退到“无入线/无出线的节点”，并给出警告。

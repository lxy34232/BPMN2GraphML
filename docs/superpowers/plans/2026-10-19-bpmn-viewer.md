# BPMN 属性筛选可视化查看器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个离线可用的静态网页，用来打开 BPMN 文件，按节点属性（元素类型、来源流程，以及以后配置表补充的任意属性）筛选并高亮节点；转换器在合并输出中写入「来源流程」属性。

**Architecture:** Python 侧新增 `properties.py`，负责读写 `b2g:properties` 扩展元素，合并模式写出时调用它。网页侧是放在包目录 `bpmn2graphml/viewer/` 下的纯静态页面：bpmn-js NavigatedViewer 负责渲染；`properties.js` 是纯逻辑（提取属性、建立索引、计算匹配），在 Node 中测试；`app.js` 负责交互。`view` 命令把 BPMN 以 base64 嵌入一个临时启动页，用浏览器打开。

**Tech Stack:** Python 3.10+ 标准库；原生 HTML/CSS/JS（经典 script）；bpmn-js 17.11.1（`bpmn-navigated-viewer.production.min.js`，放在本地）；测试：pytest、`node --test` + `@xmldom/xmldom`（仅开发依赖），端到端用 Playwright MCP。

**Spec:** `docs/superpowers/specs/2026-10-19-bpmn-viewer-design.md`

## Global Constraints

- 网页运行时**不得访问任何外部 URL**，所有依赖都在 `bpmn2graphml/viewer/vendor/` 下。
- 网页脚本一律用经典 `<script src>`，不用 ES module（`file://` 下 module 会被拦截）；也不用 `alert`/`confirm`。
- 属性格式：命名空间 `https://github.com/lxy34232/BPMN2GraphML/properties`，前缀 `b2g`，结构为 `extensionElements > b2g:properties > b2g:property[name,value]`，多值时重复写同名 property。
- 内置属性名 `元素类型`；缺少属性时的取值标签为 `（未设置）`；来源属性名为 `来源流程`。
- 拆分模式输出不做任何改动。
- 界面文字为中文；高亮色为橙色（描边 `#d97706`、底色 `#fef3c7`），淡化为半透明。
- Python 运行时仍只用标准库。

## Review Focus

1. **中文文件名和中文内容的 BPMN 通过 `view` 打开**：启动页要用 UTF-8 正确解码，名称不能乱码。→ Task 4 `test_launch_page_embeds_utf8_bpmn`。
2. **BPMN 使用默认命名空间（没有前缀）或 `bpmn:` 前缀**：属性提取与前缀无关。→ Task 2 `extracts with default namespace`。
3. **展开子流程内部的节点**：也要能被提取和筛选。→ Task 2 `extracts nested nodes`。
4. **打开第二个文件**：之前的筛选状态和高亮必须清空。→ Task 5 端到端第 4 项。
5. **属性值为空串或首尾有空白**：去掉首尾空白，空值忽略，不产生空标签。→ Task 2 `ignores empty values`、Task 1 `test_read_b2g_properties_trims`。

---

## File Structure

```
bpmn2graphml/
  properties.py            # 新增：b2g 属性的读取与写入（作用于 children_xml）
  bpmn_writer.py           # 修改：合并模式写入来源流程并合并各 origin 的 b2g 属性；注册 b2g 前缀
  viewer_launch.py         # 新增：查看器路径、启动页生成、打开浏览器
  cli.py / gui.py          # 修改：view 子命令、两个按钮
  viewer/
    index.html  app.css  app.js  properties.js
    vendor/bpmn-js/        # bpmn-navigated-viewer.production.min.js、assets/{diagram-js.css,bpmn-js.css,bpmn-font/css/bpmn.css,bpmn-font/font/*}、LICENSE
pyproject.toml             # 修改：package-data 包含 viewer/**
package.json               # 新增：仅开发依赖 @xmldom/xmldom，scripts.test = "node --test tests/viewer/"
tests/
  test_properties.py       # 新增
  test_bpmn_writer.py      # 追加
  test_viewer_launch.py    # 新增（含静态资源离线检查）
  test_cli.py              # 追加
  viewer/properties.test.js  # 新增
```

---

### Task 1: Python 侧：b2g 属性读写与合并输出的「来源流程」

**Files:**
- Create: `bpmn2graphml/properties.py`, `tests/test_properties.py`
- Modify: `bpmn2graphml/bpmn_writer.py`（`_FIXED_NS`、`write_merged_bpmn`）
- Test: `tests/test_bpmn_writer.py`（追加）

**Interfaces:**
- Produces（`properties.py`）：
  ```python
  B2G_NS = "https://github.com/lxy34232/BPMN2GraphML/properties"
  SOURCE_PROP = "来源流程"
  Prop = tuple[str, str]   # (name, value)
  def read_b2g_properties(children_xml: list[str]) -> list[Prop]
      # 只读 BPMN extensionElements > {B2G_NS}properties > {B2G_NS}property；name/value 去掉首尾空白，忽略空 name 或空 value；保持文档顺序
  def with_b2g_properties(children_xml: list[str], props: list[Prop]) -> list[str]
      # 返回新的 children_xml：删除所有已有的 b2g:properties，再在 extensionElements 中写入一个新的 b2g:properties（props 为空则不写）；
      # 没有 extensionElements 时新建，位置在所有 documentation 之后、其它子元素之前；extensionElements 里其它内容原样保留
  ```
- `bpmn_writer._FIXED_NS` 增加 `"b2g": B2G_NS`。
- 合并模式中每个节点的属性计算方式：
  ```
  sources = 对每个 origin：它自身 b2g 属性里的来源流程取值；没有的话取 [origin.file]；全部拼接后去重、保持顺序
  others  = 所有 origin 中名称 ≠ 来源流程 的 b2g 属性，按 (name, value) 去重、保持顺序
  children = with_b2g_properties(origins[0].children_xml, [(SOURCE_PROP, s) for s in sources] + others)
  ```
  没有 origin 的节点（yEd 新增）不写入任何属性。

- [ ] **Step 1: 写失败的测试** `tests/test_properties.py`：
  ```python
  EXT = '<bpmn2:extensionElements xmlns:bpmn2="{BPMN}" xmlns:ext="http://example.com/ext"><ext:info level="1"/></bpmn2:extensionElements>'
  DOC = '<bpmn2:documentation xmlns:bpmn2="{BPMN}">说明</bpmn2:documentation>'
  def test_read_b2g_properties_trims():   # property name=" 负责人 " value=" 张三 " 和一个 value="" → [("负责人","张三")]
  def test_write_creates_extension_after_documentation():
      out = with_b2g_properties([DOC, '<timer xmlns="x"/>'], [("负责人","张三")])
      # out[0] 仍是 documentation，out[1] 是 extensionElements，out[2] 是 timer；read_b2g_properties(out) == [("负责人","张三")]
  def test_write_keeps_other_extension_content():   # with_b2g_properties([EXT], [("a","1")]) → 一个 extensionElements，里面同时有 ext:info 和 b2g:properties
  def test_write_replaces_existing_b2g():   # 对已有 [("a","1")] 的结果再写 [("b","2")] → read == [("b","2")]
  def test_write_empty_removes():   # 对已有 b2g 的结果写 [] → read == []，ext:info 仍在
  ```
  追加到 `tests/test_bpmn_writer.py`：
  ```python
  def _b2g(path, node_id) -> list[tuple[str, str]]:   # 解析输出文件，用 read_b2g_properties 读取该节点子元素
  def test_merged_writes_source_property(merged_out):
      # _b2g(out, "EBPM_81ba6f70-...") == [("来源流程","科技创新平台策划"), ("来源流程","科技创新平台申报")]
      # _b2g(out, START) == [("来源流程","科技创新平台策划")]
      # "StartEvent_1"（吸收了策划的子流程）的来源 == [申报, 策划]，顺序跟 origins 一致
      # Task_1（申报 userTask）的 extensionElements 中仍有 ext:info
  def test_merged_unions_b2g_from_all_origins(tmp_path):
      # helpers.make_graph 建 A、B 两个文件，都有名为 "X" 的 task；A 的 origin.children_xml = with_b2g_properties([], [("负责人","张三")])，
      # B 的为 [("负责人","李四"), ("负责人","张三")] → 合并输出的 X 节点：[("来源流程","A"),("来源流程","B"),("负责人","张三"),("负责人","李四")]
  def test_remerge_keeps_original_sources(tmp_path, merged_out):
      # 把合并输出当作输入再 merge 一次并写 merged → EBPM_81ba... 的来源仍是 [策划, 申报]，不重复，也不变成新文件名
  def test_new_node_has_no_properties(tmp_path):   # 用 pipeline + add_task 新增节点 → 合并输出中该节点 _b2g == []
  def test_split_output_has_no_b2g(split):   # 拆分输出的原始文本中不包含 B2G_NS
  ```

- [ ] **Step 2: 运行** `python -m pytest tests/test_properties.py tests/test_bpmn_writer.py -q`，期望失败（ImportError 或断言失败）。
- [ ] **Step 3: 实现** `properties.py`，并修改 `write_merged_bpmn`（注册 b2g 前缀）。
- [ ] **Step 4: 运行** `python -m pytest -q`，期望全部 PASS（原有 69 个也通过）。
- [ ] **Step 5: 提交**：`feat: write 来源流程 and merge b2g properties in merged BPMN`

---

### Task 2: 本地依赖与 `properties.js`（纯逻辑）

**Files:**
- Create: `bpmn2graphml/viewer/vendor/bpmn-js/**`（下载）、`bpmn2graphml/viewer/properties.js`、`package.json`、`tests/viewer/properties.test.js`
- Modify: `.gitignore`（加 `node_modules/`）

**Interfaces:**
- Produces（`properties.js`，挂到全局 `window.B2GProps`；Node 中用 `module.exports` 导出同一对象）：
  ```js
  TYPE_ATTR = "元素类型"; UNSET = "（未设置）"; SOURCE_ATTR = "来源流程"
  typeLabel(type: string) -> string          // manualTask→人工任务 userTask→用户任务 task→任务 serviceTask→服务任务 scriptTask→脚本任务
                                              // sendTask→发送任务 receiveTask→接收任务 businessRuleTask→业务规则任务 subProcess→子流程
                                              // callActivity→调用活动 startEvent→开始事件 endEvent→结束事件 intermediateThrowEvent→中间抛出事件
                                              // intermediateCatchEvent→中间捕获事件 boundaryEvent→边界事件 exclusiveGateway→排他网关
                                              // parallelGateway→并行网关 inclusiveGateway→包容网关 eventBasedGateway→事件网关
                                              // complexGateway→复杂网关；其它返回原值
  extractNodes(doc: Document) -> Array<{id, type, name, props: {[name]: string[]}}>
      // 只用 DOM Level 2 API（getElementsByTagNameNS、childNodes、localName、namespaceURI、getAttribute），以兼容 xmldom
      // 节点 = BPMN 命名空间下、本地名属于上面类型表的所有带 id 的元素（含子流程内部）
      // props：extensionElements 的直接子元素中，本地名为 "properties"（任意命名空间）的元素，其子元素中本地名为 "property"、
      //        name 和 value 去掉首尾空白后都非空的条目；同名多值按文档顺序、去重
  hasDiagram(doc: Document) -> boolean        // 存在 BPMNDI 命名空间的 BPMNShape
  listAttributes(nodes) -> string[]            // [TYPE_ATTR, ...自定义属性名（按首次出现顺序）]
  valuesOf(node, attr) -> string[]             // TYPE_ATTR → [typeLabel(node.type)]；否则 node.props[attr] || []
  buildIndex(nodes, attr) -> Array<{value: string, ids: string[]}>
      // 取值按首次出现顺序；存在没有该属性的节点时，末尾追加 {value: UNSET, ids}（TYPE_ATTR 永远不会有）
  matchIds(nodes, attr, selected: string[]) -> Set<string>
      // 节点的任一取值在 selected 中即匹配；selected 含 UNSET 时，没有该属性的节点也匹配
  ```

- [ ] **Step 1: 下载依赖**：从 `https://unpkg.com/bpmn-js@17.11.1/dist/` 下载 `bpmn-navigated-viewer.production.min.js`、`assets/diagram-js.css`、`assets/bpmn-js.css`、`assets/bpmn-font/css/bpmn.css` 以及该 CSS 引用的 `assets/bpmn-font/font/*` 字体文件，另从 `https://unpkg.com/bpmn-js@17.11.1/LICENSE` 下载许可证，按原目录结构放进 `bpmn2graphml/viewer/vendor/bpmn-js/`。写 `package.json`（`"private": true`，devDependencies 为 `"@xmldom/xmldom": "0.8.10"`，`scripts.test = "node --test tests/viewer/"`），执行 `npm install`；`.gitignore` 加上 `node_modules/`。
- [ ] **Step 2: 写失败的测试** `tests/viewer/properties.test.js`（`node:test` + `node:assert/strict`；用 `new DOMParser().parseFromString(xml, "text/xml")` 解析内联 XML 字符串）：
  ```js
  test("extracts b2g and camunda properties")   // b2g 节点 → props {负责人:["张三","李四"]}；camunda:properties 节点 → props {系统:["OA"]}
  test("extracts with default namespace")       // <definitions xmlns="BPMN">…<task id="t" name="T"/> → [{id:"t",type:"task",name:"T",props:{}}]
  test("extracts nested nodes")                 // subProcess 内部的 task 也在结果中，subProcess 本身也在
  test("ignores empty values")                  // value="" 和 value="  " 都不出现；value=" OA " → "OA"
  test("ignores sequence flows")                // sequenceFlow 不在结果中
  test("hasDiagram")                            // 有 BPMNShape → true，否则 false
  test("listAttributes order")                  // ["元素类型","来源流程","负责人"]（按首次出现顺序）
  test("buildIndex counts and unset")           // 3 个节点，其中 1 个没有负责人 → [{value:"张三",ids:[...]},{value:"（未设置）",ids:[那个节点]}]
  test("buildIndex type attr has no unset")
  test("matchIds any-of and unset")             // selected ["张三"] → 有张三的节点；selected ["（未设置）"] → 没有该属性的节点；selected [] → 空集合
  test("typeLabel")                             // manualTask→"人工任务"，"fooBar"→"fooBar"
  ```
- [ ] **Step 3: 运行** `npm test`，期望失败（找不到 `bpmn2graphml/viewer/properties.js`）。
- [ ] **Step 4: 实现** `properties.js`（IIFE；`typeof module !== "undefined"` 时导出）。
- [ ] **Step 5: 运行** `npm test`，期望全部 PASS。
- [ ] **Step 6: 提交**：`feat: vendor bpmn-js viewer and add properties.js`（vendor 文件和 `package-lock.json` 一并提交）

---

### Task 3: 查看器页面（B 布局）

**Files:**
- Create: `bpmn2graphml/viewer/index.html`, `app.css`, `app.js`, `tests/test_viewer_launch.py`（先写其中的静态资源检查）
- Modify: `pyproject.toml`（`[tool.setuptools.package-data] bpmn2graphml = ["viewer/*", "viewer/vendor/**/*"]`）

**Interfaces:**
- Consumes：`window.B2GProps`（Task 2）、`window.BpmnJS`（vendor 提供 NavigatedViewer）。
- Produces（供 Task 4 的启动页使用）：页面加载时，如果存在 `<script type="text/plain" id="b2g-preload" data-filename="…" data-base64="…">`，就用 UTF-8 解码 base64（`TextDecoder`）后自动打开该文件。`index.html` 中的本地资源一律用相对路径引用（`vendor/...`、`app.css`、`properties.js`、`app.js`）。

**页面行为**（按设计文档的「页面行为」一节）：
- 顶部工具条：「打开 BPMN」（隐藏的 file input）、文件名、属性 `<select>`、取值标签容器（`flex-wrap: wrap`）、「清除筛选」、「适应窗口」。整页支持拖放文件。
- 打开文件的流程：
  - `DOMParser` 解析失败（出现 `parsererror`）时，显示带文件名的错误；
  - `!hasDiagram(doc)` 时，显示设计文档中给定的“没有图形布局信息”提示；
  - 否则调用 `viewer.importXML`，再 `canvas.zoom('fit-viewport')`；
  - 然后 `extractNodes` → 填充属性下拉框（默认选中 `来源流程`，没有则选 `元素类型`）→ 清空已选取值、标记和详情卡。
- 高亮：
  - 先移除所有元素上的 `b2g-hl` / `b2g-dim` 标记；
  - 选中集合为空时直接返回；
  - 否则对匹配的节点加 `b2g-hl`，对其它节点加 `b2g-dim`；连线两端都在匹配集合中就不处理，否则加 `b2g-dim`；标签元素（`type === 'label'`）跟随其所属元素。
  - CSS：`.b2g-hl .djs-visual > :first-child { stroke:#d97706 !important; stroke-width:3px !important; fill:#fef3c7 !important }`、`.b2g-dim { opacity:.25 }`。
- 标签：每个标签显示 `取值 · 数量`，点击切换 `.on`；切换属性时清空已选。
- 详情卡：
  - `element.click` 事件中，如果点到的是节点（存在于 extractNodes 结果中），就在节点右侧显示卡片：名称、元素类型、ID，以及每个属性一行（多值用「、」连接）。卡片定位用 `canvas.viewbox()` 换算到屏幕坐标，超出右边界时改放到左侧。
  - 点到画布空白处（root）或按 Esc 时关闭卡片。
- 空状态：页面中央显示「打开或拖入一个 BPMN 文件」。

- [ ] **Step 1: 写失败的测试** `tests/test_viewer_launch.py`：
  ```python
  VIEWER = Path(bpmn2graphml.__file__).parent / "viewer"
  def test_viewer_assets_local():
      # 解析 index.html 中所有 <script src> 和 <link href>：都不以 http:// https:// // 开头，且 (VIEWER / ref) 存在
      # 每个被引用的 CSS 中的 url(...) 也都是相对路径且文件存在
  def test_viewer_no_module_scripts():   # index.html 中不包含 type="module"
  ```
- [ ] **Step 2: 运行** `python -m pytest tests/test_viewer_launch.py -q`，期望失败（index.html 不存在）。
- [ ] **Step 3: 实现** `index.html`、`app.css`、`app.js`，修改 `pyproject.toml`。
- [ ] **Step 4: 运行** `python -m pytest -q && npm test`，期望全部 PASS。
- [ ] **Step 5: 冒烟检查**：在会话临时目录起一个 `python -m http.server`，以项目根为目录，用 Playwright 打开 `bpmn2graphml/viewer/index.html`，通过 file input 上传 `out/yed_merged.bpmn`（没有就先按 README 生成；Task 1 改动后需要重新执行 `tobpmn` 生成）。确认属性下拉框里有「元素类型」「来源流程」，并且控制台没有错误。
- [ ] **Step 6: 提交**：`feat: attribute-filter viewer page (layout B)`

---

### Task 4: `view` 命令、启动页与界面按钮

**Files:**
- Create: `bpmn2graphml/viewer_launch.py`
- Modify: `bpmn2graphml/cli.py`, `bpmn2graphml/gui.py`, `README.md`
- Test: `tests/test_viewer_launch.py`（追加）、`tests/test_cli.py`（追加）

**Interfaces:**
- Produces（`viewer_launch.py`）：
  ```python
  VIEWER_DIR: Path                       # Path(__file__).parent / "viewer"
  def make_launch_page(bpmn_path: Path, out_dir: Path | None = None) -> Path
      # 读取 index.html，把相对资源路径改写为 (VIEWER_DIR / ref).as_uri()，在 </body> 前插入
      # <script type="text/plain" id="b2g-preload" data-filename="{html 转义后的文件名}" data-base64="{base64(文件字节)}"></script>；
      # 写到 out_dir（默认 tempfile.mkdtemp(prefix="b2g-view-")）/ "view.html"，返回路径
  def open_viewer(bpmn_path: Path | None = None, opener=webbrowser.open) -> Path
      # 有文件 → make_launch_page 后打开它；无文件 → 打开 VIEWER_DIR / "index.html"；返回被打开的路径
  ```
- CLI：`view [file]` 子命令。文件不存在时打印「错误：…」并返回 1。
- GUI：「GraphML → BPMN」页签加按钮「在查看器中打开」（打开 `merged_out` 路径；文件不存在时弹出 showerror）；窗口底部加按钮「打开可视化查看器」（无文件）。按钮分别保存为 `self.view_result_button`、`self.open_viewer_button`。

- [ ] **Step 1: 写失败的测试**：
  ```python
  # tests/test_viewer_launch.py
  def test_launch_page_embeds_utf8_bpmn(tmp_path):
      page = make_launch_page(FIX / "科技创新平台策划.bpmn", tmp_path)
      # 从 page 中取出 data-base64 → base64 解码后 == 原文件字节；data-filename == "科技创新平台策划.bpmn"
  def test_launch_page_assets_absolute(tmp_path):
      # page 中所有 script src / link href 都以 "file:///" 开头，且 url2pathname 后的路径存在
  def test_open_viewer_without_file():   # opener 用列表记录；返回 VIEWER_DIR/"index.html"，opener 收到它的 as_uri()
  # tests/test_cli.py
  def test_cli_view_file(monkeypatch, tmp_path):   # monkeypatch viewer_launch 的打开函数，main(["view", fixture]) == 0，并收到 view.html 的 URI
  def test_cli_view_missing(tmp_path, capsys):      # main(["view", "nope.bpmn"]) == 1，stderr 中包含 "nope.bpmn"
  # tests/test_cli.py::test_gui_builds 追加：hasattr(app, "view_result_button") and hasattr(app, "open_viewer_button")
  ```
- [ ] **Step 2: 运行** `python -m pytest tests/test_viewer_launch.py tests/test_cli.py -q`，期望失败。
- [ ] **Step 3: 实现** `viewer_launch.py`、CLI 的 `view` 子命令和 GUI 按钮；README 增加「可视化查看器」一节（打开方式、筛选方法、属性格式示例、离线说明）。
- [ ] **Step 4: 运行** `python -m pytest -q && npm test`，期望全部 PASS。
- [ ] **Step 5: 提交**：`feat: view command, launch page and GUI viewer buttons`

---

### Task 5: 端到端验证

**Files:**（只做验证；发现问题时修改对应文件，并先补测试）

- [ ] **Step 1**：用 Task 1 之后的代码重新生成 `out/yed_merged.bpmn`：`python -m bpmn2graphml tobpmn tests/fixtures/yed_saved.graphml --merged out/yed_merged.bpmn`。
- [ ] **Step 2**：生成启动页 `python -c "from bpmn2graphml.viewer_launch import make_launch_page; print(make_launch_page(__import__('pathlib').Path('out/yed_merged.bpmn'), __import__('pathlib').Path('out/view')))"`，用 Playwright 打开它的 `file:///` URL（若 Playwright 不允许 file://，改用以项目根为目录的本地 http.server 打开 `index.html` 并上传文件）。在 Playwright 中拦截所有非本地请求并记录，期望记录为空。
- [ ] **Step 3**：检查以下各项：
  1. 渲染成功，控制台没有错误；
  2. 属性下拉框为 `元素类型, 来源流程`；
  3. 选中「科技创新平台申报」后，带 `b2g-hl` 标记的元素数等于该标签上的计数；
  4. 再上传 `tests/fixtures/科技创新平台申报.bpmn`：标签和标记全部重置，下拉框只剩 `元素类型`；
  5. 点击「部门领导审核」弹出详情卡，其中「来源流程」显示“科技创新平台策划、科技创新平台申报”；
  6. 上传 `tests/fixtures/平台建设运行.bpmn`，显示“没有图形布局信息”的提示。
  每一项都截图存到 `out/`。
- [ ] **Step 4**：把截图给用户看；用 `python -m bpmn2graphml view out/yed_merged.bpmn` 在用户的默认浏览器中打开一次。

# BPMN ⇄ yEd GraphML 合并转换器

把多个 BPMN 2.0 流程文件合并为一张图，在 yEd Graph Editor 里自动布局（也可以手工编辑），然后转回 BPMN。转回时有两种方式：

- **合并模式**：输出一个合并后的大流程文件；
- **拆分模式**：拆回原来的每个文件，所有原 ID 保持不变，只是布局换成 yEd 排好的。

## 环境要求

- Python 3.10 或更高版本（只用标准库，无需安装第三方包）
- [yEd Graph Editor](https://www.yworks.com/products/yed)（已在 3.25.1 上验证）

## 启动

```bash
python -m bpmn2graphml            # 打开图形界面
```

命令行用法：

```bash
# 1. 合并多个 BPMN → graphml（同时生成 merged.merge-report.txt 合并报告）
python -m bpmn2graphml merge 科技创新平台策划.bpmn 科技创新平台申报.bpmn -o merged.graphml

# 2. yEd 保存后 → 转回 BPMN（两种方式可以只选一种，也可以都选）
python -m bpmn2graphml tobpmn merged.graphml --merged merged.bpmn --split 拆分输出/
```

## 在 yEd 中的操作

1. 用 yEd 打开生成的 `.graphml`。节点会显示为 yEd 自带的 BPMN 图形。
2. 菜单 **布局 › 分层**（Layout › Hierarchical），按需要调整参数后应用。
3. 可以修改节点或连线的名称，也可以删除元素。新增节点时，请从右侧面板的 **BPMN** 分组里拖入，这样程序才能识别它是任务、网关还是事件；其它普通图形一律当作“任务”处理。
4. **文件 › 保存**，保持 `.graphml` 格式（不要另存为 `.graphmlz`）。
5. 回到本程序，把保存好的 graphml 转回 BPMN。

## 合并规则

| 情况 | 处理方式 |
|---|---|
| 不同文件中名称完全相同的节点 | 合并成一个节点，所有连线都接到它上面；沿用最先出现的那个节点的 ID |
| A 的结束事件与 B 的开始事件同名 | 合并后，在合并模式中改为中间事件；拆分模式中恢复原类型 |
| 空的子流程，且有同名文件 | 展开为该文件的内容：入线接到它的开始事件，出线从它的结束事件引出 |
| 名称为空的节点（例如网关） | 从不参与合并 |
| 同一文件中的同名节点 | 不合并（报告中会给出警告） |
| 不同文件中 ID 相同、但不是同一节点 | 合并模式中改名为 `原ID_2`，拆分模式中保持原 ID |

每次合并都会生成 `*.merge-report.txt`，列出所有合并、展开和警告，请检查一遍，确认没有误合并。

拆分模式中，在 yEd 里新增的节点会归入与它相连节点所在的文件；跨越不同文件的新增连线无法归入任何单个文件，会被跳过，并在警告中列出。

## 可视化查看器

用来在浏览器中浏览一个 BPMN 流程（合并前或合并后的都可以），并**按节点属性筛选、高亮**。

```bash
python -m bpmn2graphml view merged.bpmn   # 直接打开指定文件
python -m bpmn2graphml view               # 打开空白查看器，再点「打开 BPMN」或把文件拖进页面
```

图形界面中：「GraphML → BPMN」页签的「在查看器中打开」会打开刚转换出的合并文件；窗口底部的「打开可视化查看器」会打开空白查看器。也可以直接双击 `bpmn2graphml/viewer/index.html`。

使用方法：

1. 在顶部「按」下拉框中选一个属性，例如「来源流程」「元素类型」。
2. 点击一个或多个取值标签，标签上的数字是节点数。图中匹配的节点会以橙色高亮，其余节点变淡；两端都高亮的连线保持正常显示。
3. 「（未设置）」标签对应没有该属性的节点，可以用来检查哪些节点还没补全信息。
4. 点击节点会弹出详情卡，列出它的全部属性。按 Esc 或点击空白处关闭。

查看器的全部依赖（bpmn-js 17.11.1）都放在本地，**不需要联网**。

### 节点属性的格式

属性写在节点的 `extensionElements` 中。同一个属性有多个取值时，就重复写同名的 `property`：

```xml
<bpmn2:manualTask id="..." name="部门领导审核">
  <bpmn2:extensionElements>
    <b2g:properties xmlns:b2g="https://github.com/lxy34232/BPMN2GraphML/properties">
      <b2g:property name="负责人" value="部门领导"/>
      <b2g:property name="信息系统" value="OA"/>
      <b2g:property name="信息系统" value="科研管理系统"/>
    </b2g:properties>
  </bpmn2:extensionElements>
</bpmn2:manualTask>
```

文件中出现的任意属性名都会自动出现在筛选列表中。Camunda/Zeebe 的 `camunda:properties` / `zeebe:properties` 结构相同，也能识别。

合并模式输出 BPMN 时，会自动给每个节点写入「来源流程」属性，取值为它来自哪些原文件。各原文件节点上已有的属性在合并时全部保留。

## 已知限制

- 不支持泳池/泳道、消息流、数据对象、注释（读取时会忽略，并给出警告）。
- 非空子流程的内部内容会原样保留，但不会在 yEd 中展开显示。
- 新增元素的 ID 格式为 `EBPM_<uuid>`。

## 开发

```bash
pip install pytest
python -m pytest
npm install && npm test   # 查看器逻辑测试（需要 Node.js）
```

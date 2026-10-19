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

## 已知限制

- 不支持泳池/泳道、消息流、数据对象、注释（读取时会忽略，并给出警告）。
- 非空子流程的内部内容会原样保留，但不会在 yEd 中展开显示。
- 新增元素的 ID 格式为 `EBPM_<uuid>`。

## 开发

```bash
pip install pytest
python -m pytest
```

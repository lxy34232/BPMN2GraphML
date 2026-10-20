import shutil
import xml.etree.ElementTree as ET

import pytest

from bpmn2graphml.bpmn_reader import read_bpmn
from bpmn2graphml.model import BPMN_NS
from bpmn2graphml.prop_table import (PropTableError, export_table, group_rows,
                                     import_report_path_for, import_table, load_docs)
from bpmn2graphml.properties import (B2G_NS, node_b2g_properties,
                                     set_node_b2g_properties)
from bpmn2graphml.table_io import read_table, write_table
from conftest import fixture_paths


def _copy_fixtures(tmp_path, paths=None):
    out = []
    for p in paths or fixture_paths():
        dst = tmp_path / p.name
        shutil.copy(p, dst)
        out.append(dst)
    return out


def _set_props(path, name, props):
    """测试准备：直接给文件中名为 name 的节点写入 b2g 属性。"""
    ns = dict(prefix_uri for _e, prefix_uri in ET.iterparse(path, events=("start-ns",)))
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)
    ET.register_namespace("b2g", B2G_NS)
    tree = ET.parse(path)
    for el in tree.getroot().iter():
        if el.tag.startswith(f"{{{BPMN_NS}}}") and el.get("name") == name:
            set_node_b2g_properties(el, props)
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def test_group_rows_fixtures_folds_subprocess():
    rows, folded = group_rows(load_docs(fixture_paths()))
    assert "科技创新平台申报" not in rows
    assert {(n.file, n.bpmn_type) for n in rows["启动平台申报"]} == {
        ("科技创新平台策划", "subProcess"), ("科技创新平台申报", "startEvent")}
    assert len(folded) == 1 and "启动平台申报" in folded[0]


def test_group_rows_single_file_keeps_subprocess_row():
    rows, folded = group_rows(load_docs(fixture_paths()[:1]))
    assert "科技创新平台申报" in rows and folded == []


def test_group_rows_skips_unnamed_nodes():
    rows, _ = group_rows(load_docs(fixture_paths()))
    assert "" not in rows
    assert all(n.name for refs in rows.values() for n in refs)


def test_export_columns_and_values(tmp_path):
    paths = _copy_fixtures(tmp_path, fixture_paths()[:2])
    _set_props(paths[0], "部门领导审核", [("来源流程", "策划"), ("负责人", "张三")])
    _set_props(paths[1], "部门领导审核", [("负责人", "李四"), ("系统", "OA")])
    s = export_table(paths, tmp_path / "t.xlsx")
    table = read_table(tmp_path / "t.xlsx")
    assert table[0] == ["节点名称", "所在文件", "元素类型", "来源流程", "负责人", "系统"]
    row = next(r for r in table if r[0] == "部门领导审核")
    assert row[1] == "科技创新平台策划；科技创新平台申报"
    assert row[2] == "人工任务"
    assert row[3] == "策划"
    assert row[4] == "张三；李四" and row[5] == "OA"
    assert s.conflicts == ["部门领导审核"]
    assert s.rows == len(table) - 1
    assert s.columns == ["负责人", "系统"]


def test_export_without_source_column(tmp_path):
    export_table(fixture_paths(), tmp_path / "t.xlsx")
    assert read_table(tmp_path / "t.xlsx")[0] == ["节点名称", "所在文件", "元素类型"]


def test_export_csv_summary_warns(tmp_path):
    s = export_table(fixture_paths(), tmp_path / "t.csv")
    assert "建议使用 .xlsx" in s.to_text()
    assert "建议使用 .xlsx" not in export_table(fixture_paths(), tmp_path / "t.xlsx").to_text()


def test_load_docs_bad_xml(tmp_path):
    bad = tmp_path / "x.bpmn"
    bad.write_text("hello", encoding="utf-8")
    with pytest.raises(PropTableError, match="x.bpmn"):
        load_docs([bad])


def test_load_docs_duplicate_names(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    p1 = shutil.copy(fixture_paths()[2], tmp_path / "a" / "same.bpmn")
    p2 = shutil.copy(fixture_paths()[2], tmp_path / "b" / "same.bpmn")
    with pytest.raises(PropTableError, match="文件名重复"):
        load_docs([p1, p2])


# —— 导入 ——

def _props_by_file(paths, name):
    """名为 name 的各节点的 b2g 属性：{(文件, 元素类型): props}。"""
    out = {}
    for d in load_docs(paths):
        for n in d.nodes:
            if n.name == name:
                out[(n.file, n.bpmn_type)] = node_b2g_properties(n.element)
    return out


def _replace_text(path, old, new):
    text = path.read_text(encoding="utf-8-sig")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _canon(el):
    kids = []
    for c in el:
        if c.tag == f"{{{B2G_NS}}}properties":
            continue
        k = _canon(c)
        if c.tag == f"{{{BPMN_NS}}}extensionElements" and not k[3]:
            continue
        kids.append(k)
    return (str(el.tag), sorted(el.attrib.items()), (el.text or "").strip(), kids)


def _parse_with_comments(path):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(path, parser).getroot()


def _bak(path):
    return path.with_name(path.name + ".bak")


def test_export_import_roundtrip_unchanged(tmp_path):
    paths = _copy_fixtures(tmp_path)
    _replace_text(paths[2], 'name="平台建设"', 'name="　平台建设　"')
    for p in paths[:2]:  # 两个同名节点取值一致，否则导入会按设计把它们统一
        _set_props(p, "部门领导审核", [("负责人", "第一行\n第二行"), ("系统", "OA")])
    export_table(paths, tmp_path / "t.xlsx")
    before = [p.read_bytes() for p in paths]
    r = import_table(tmp_path / "t.xlsx", paths)
    assert r.ok and r.changed_files == []
    assert [p.read_bytes() for p in paths] == before
    assert not any(_bak(p).exists() for p in paths)
    assert r.not_found == []


def test_fill_clear_delete_add(tmp_path):
    paths = _copy_fixtures(tmp_path)
    _set_props(paths[1], "部门领导审核", [("来源流程", "X"), ("负责人", "王五"), ("系统", "OA")])
    _set_props(paths[1], "填写申报材料", [("负责人", "赵六")])
    original = paths[1].read_bytes()
    table = tmp_path / "t.xlsx"
    export_table(paths, table)
    rows = read_table(table)
    assert rows[0] == ["节点名称", "所在文件", "元素类型", "来源流程", "负责人", "系统"]
    rows = [r[:5] + [""] for r in rows]  # 删掉「系统」列，新增一列
    rows[0][5] = "审批时限"
    for r in rows[1:]:
        if r[0] == "部门领导审核":
            r[4], r[5] = "张三；李四", "3天"
        if r[0] == "填写申报材料":
            r[4] = ""
    write_table(table, rows)
    r = import_table(table, paths)
    assert r.ok, r.error
    got = _props_by_file(paths, "部门领导审核")
    expected = [("负责人", "张三"), ("负责人", "李四"), ("审批时限", "3天")]
    assert got[("科技创新平台申报", "manualTask")] == [("来源流程", "X")] + expected
    assert got[("科技创新平台策划", "manualTask")] == expected
    assert _props_by_file(paths, "填写申报材料") == {("科技创新平台申报", "userTask"): []}
    assert _bak(paths[1]).read_bytes() == original
    assert read_bpmn(paths[1]).nodes


def test_same_name_across_files_all_written(tmp_path):
    paths = _copy_fixtures(tmp_path)
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["部门领导审核", "张三"]])
    assert import_table(tmp_path / "t.csv", paths).ok
    got = _props_by_file(paths, "部门领导审核")
    assert len(got) == 2 and all(v == [("负责人", "张三")] for v in got.values())


def test_folded_subprocess_gets_start_event_row(tmp_path):
    paths = _copy_fixtures(tmp_path)
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["启动平台申报", "张三"]])
    r = import_table(tmp_path / "t.csv", paths)
    assert r.ok and r.folded
    assert _props_by_file(paths, "科技创新平台申报") == {
        ("科技创新平台策划", "subProcess"): [("负责人", "张三")]}
    assert _props_by_file(paths, "启动平台申报") == {
        ("科技创新平台申报", "startEvent"): [("负责人", "张三")]}


def test_same_file_duplicates_reported(tmp_path):
    paths = _copy_fixtures(tmp_path)
    _replace_text(paths[2], 'name="平台建设完成"', 'name="平台建设"')
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["平台建设", "张三"]])
    r = import_table(tmp_path / "t.csv", paths)
    assert r.ok and r.same_file_dupes == ["平台建设（平台建设运行）"]
    assert len(_props_by_file(paths, "平台建设")) == 2


@pytest.mark.parametrize("rows, msg", [
    ([["节点名称", "负责人"], ["审核", "a"], ["审核", "b"]], "出现了多行"),
    ([["节点名称", "a", "a"], ["审核", "1", "2"]], "重复"),
    ([["节点名称", ""], ["审核", "1"]], "表头为空"),
    ([["节点名称", "所在文件"], ["审核", "x"]], "保留表头"),
    ([["节点名称", "负责人"], ["", "张三"]], "没有节点名称"),
    ([["节点名称", "负责人"]], "没有数据"),
])
def test_abort_writes_nothing(tmp_path, rows, msg):
    paths = _copy_fixtures(tmp_path)
    before = [p.read_bytes() for p in paths]
    write_table(tmp_path / "t.csv", rows)
    r = import_table(tmp_path / "t.csv", paths)
    assert not r.ok and msg in r.error
    assert [p.read_bytes() for p in paths] == before
    assert import_report_path_for(tmp_path / "t.csv").exists()


def test_bad_bpmn_aborts(tmp_path):
    paths = _copy_fixtures(tmp_path)
    bad = tmp_path / "x.bpmn"
    bad.write_text("hello", encoding="utf-8")
    before = [p.read_bytes() for p in paths]
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["部门领导审核", "张三"]])
    r = import_table(tmp_path / "t.csv", paths + [bad])
    assert not r.ok and "x.bpmn" in r.error
    assert [p.read_bytes() for p in paths] == before


def test_unreadable_table_aborts(tmp_path):
    r = import_table(tmp_path / "nope.xlsx", _copy_fixtures(tmp_path))
    assert not r.ok and "nope.xlsx" in r.error


def test_rewritten_file_semantically_same(tmp_path):
    [path] = _copy_fixtures(tmp_path, fixture_paths()[1:2])
    _replace_text(path, "<bpmn:process ", "<!-- 注释 --><bpmn:process ")
    before = _canon(_parse_with_comments(path))
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["部门领导审核", "张三"]])
    r = import_table(tmp_path / "t.csv", [path])
    assert r.ok and r.changed_files == [(path, 1)]
    assert _canon(_parse_with_comments(path)) == before
    text = path.read_text(encoding="utf-8")
    assert "<bpmn:definitions" in text and "<!-- 注释 -->" in text and "ns0:" not in text
    assert read_bpmn(path).nodes
    assert not path.with_name(path.name + ".tmp").exists()


def test_second_import_changes_nothing(tmp_path):
    paths = _copy_fixtures(tmp_path)
    original = paths[1].read_bytes()
    write_table(tmp_path / "t.csv", [["节点名称", "负责人"], ["部门领导审核", "张三"]])
    assert import_table(tmp_path / "t.csv", paths).changed_files
    r = import_table(tmp_path / "t.csv", paths)
    assert r.ok and r.changed_files == []
    assert _bak(paths[1]).read_bytes() == original


def test_whitespace_cells_and_headers(tmp_path):
    paths = _copy_fixtures(tmp_path)
    write_table(tmp_path / "t.csv", [["节点名称", " 负责人 "], ["部门领导审核", "  "],
                                     [" 平台建设 ", "张三"]])
    r = import_table(tmp_path / "t.csv", paths)
    assert r.ok
    assert all(v == [] for v in _props_by_file(paths, "部门领导审核").values())
    assert _props_by_file(paths, "平台建设") == {
        ("平台建设运行", "task"): [("负责人", "张三")]}


def test_report_sections(tmp_path):
    paths = _copy_fixtures(tmp_path)
    table = tmp_path / "t.csv"
    write_table(table, [["节点名称", "所在文件", "负责人"], ["不存在的节点", "", ""],
                        ["平台建设", "", "张三"]])
    r = import_table(table, paths)
    assert r.ok and r.not_found == ["不存在的节点"]
    assert "部门领导审核" in r.untouched and r.ignored_columns == ["所在文件"]
    text = r.to_text()
    for part in ("找不到对应节点", "不存在的节点", "表中没有的节点", "被忽略的列",
                 "平台建设：新增 负责人=张三", ".bak"):
        assert part in text
    assert import_report_path_for(table) == tmp_path / "t.import-report.txt"
    assert import_report_path_for(table).read_text(encoding="utf-8") == text

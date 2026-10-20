import shutil
import xml.etree.ElementTree as ET

import pytest

from bpmn2graphml.model import BPMN_NS
from bpmn2graphml.prop_table import (PropTableError, export_table, group_rows,
                                     load_docs)
from bpmn2graphml.properties import B2G_NS, set_node_b2g_properties
from bpmn2graphml.table_io import read_table
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

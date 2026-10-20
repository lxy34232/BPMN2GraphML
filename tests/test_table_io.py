import zipfile

import pytest

from bpmn2graphml.table_io import TableError, read_table, write_table

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
    def locked(*a, **k):
        raise PermissionError(13, "denied")
    monkeypatch.setattr(zipfile, "ZipFile", locked)
    with pytest.raises(TableError, match="请先关闭该文件"):
        write_table(tmp_path / "t.xlsx", ROWS)


def test_read_missing_file(tmp_path):
    with pytest.raises(TableError, match="nope.xlsx"):
        read_table(tmp_path / "nope.xlsx")

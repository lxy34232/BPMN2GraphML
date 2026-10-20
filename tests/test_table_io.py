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


# —— 读取 Excel / WPS 保存的 xlsx ——

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _make_xlsx(path, sheet_data, shared=None, styles=None,
               sheet_target="worksheets/sheet7.xml", date1904=False):
    pr = '<workbookPr date1904="1"/>' if date1904 else ""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   f'<workbook xmlns="{MAIN}" xmlns:r="{REL_NS}">{pr}'
                   '<sheets><sheet name="S" sheetId="3" r:id="rId9"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId9" Type="{REL_NS}/worksheet" Target="{sheet_target}"/>'
                   '</Relationships>')
        inner = sheet_target.lstrip("/") if sheet_target.startswith("/") else "xl/" + sheet_target
        z.writestr(inner, f'<worksheet xmlns="{MAIN}"><sheetData>{sheet_data}</sheetData></worksheet>')
        if shared is not None:
            z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{MAIN}">{shared}</sst>')
        if styles is not None:
            z.writestr("xl/styles.xml", f'<styleSheet xmlns="{MAIN}">{styles}</styleSheet>')


def test_shared_strings_rich_text_and_phonetic(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>',
               shared='<si><r><t>部门</t></r><r><t>审核</t></r><rPh><t>ブ</t></rPh></si>'
                      '<si><t>张三</t></si>')
    assert read_table(p) == [["部门审核", "张三"]]


def test_sparse_cells(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1" t="inlineStr"><is><t>a</t></is></c>'
                  '<c r="C1" t="inlineStr"><is><t>c</t></is></c></row>'
                  '<row r="3"><c r="B3" t="inlineStr"><is><t>b</t></is></c></row>')
    assert read_table(p) == [["a", "", "c"], ["", "", ""], ["", "b", ""]]


def test_numbers_and_bools(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1"><v>3</v></c><c r="B1"><v>3.0</v></c>'
                  '<c r="C1"><v>0.5</v></c><c r="D1" t="b"><v>1</v></c>'
                  '<c r="E1" t="str"><v>公式</v></c></row>')
    assert read_table(p) == [["3", "3", "0.5", "TRUE", "公式"]]


DATE_STYLES = ('<numFmts count="2">'
               '<numFmt numFmtId="164" formatCode="yyyy&quot;年&quot;m&quot;月&quot;d&quot;日&quot;"/>'
               '<numFmt numFmtId="165" formatCode="0.00%"/></numFmts>'
               '<cellXfs count="5"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/>'
               '<xf numFmtId="165"/><xf numFmtId="20"/></cellXfs>')


def test_dates_builtin_and_custom(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1" s="1"><v>46315</v></c><c r="B1" s="2"><v>46315.5</v></c>'
                  '<c r="C1" s="3"><v>0.5</v></c><c r="D1" s="4"><v>0.5</v></c></row>',
               styles=DATE_STYLES)
    assert read_table(p) == [["2026-10-20", "2026-10-20 12:00", "0.5", "0.5"]]


def test_date1904(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1" s="1"><v>0</v></c></row>', styles=DATE_STYLES,
               date1904=True)
    assert read_table(p) == [["1904-01-01"]]


def test_absolute_sheet_target(tmp_path):
    p = tmp_path / "t.xlsx"
    _make_xlsx(p, '<row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c></row>',
               sheet_target="/xl/worksheets/sheet7.xml")
    assert read_table(p) == [["x"]]


def test_escaped_letter_in_format_is_not_date(tmp_path):
    p = tmp_path / "t.xlsx"
    styles = ('<numFmts count="1"><numFmt numFmtId="170" formatCode="0.0\d"/></numFmts>'
              '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="170"/></cellXfs>')
    _make_xlsx(p, '<row r="1"><c r="A1" s="1"><v>1.5</v></c></row>', styles=styles)
    assert read_table(p) == [["1.5"]]

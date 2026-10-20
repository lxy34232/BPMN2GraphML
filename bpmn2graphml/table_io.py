"""属性表文件读写：.xlsx 与 .csv，只用标准库。

表格在内存中是 list[list[str]]，第一行为表头。
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_M = f"{{{_MAIN_NS}}}"

_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_EXTRA_COLS = 20

# cellXfs 下标
_XF_HEADER, _XF_TEXT, _XF_READONLY = 1, 2, 3


class TableError(Exception):
    pass


def write_table(path: Path, rows: list[list[str]],
                readonly_cols: frozenset[int] = frozenset()) -> None:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".csv"):
        raise TableError(f"{path.name}：不支持的表格格式（只支持 .xlsx 和 .csv）")
    try:
        if suffix == ".xlsx":
            _write_xlsx(path, rows, readonly_cols)
        else:
            _write_csv(path, rows)
    except PermissionError as e:
        raise TableError(f"无法写入 {path.name}：文件可能正在 Excel 中打开，请先关闭该文件") from e
    except OSError as e:
        raise TableError(f"无法写入 {path.name}：{e}") from e


def read_table(path: Path) -> list[list[str]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".csv"):
        raise TableError(f"{path.name}：不支持的表格格式（只支持 .xlsx 和 .csv）")
    try:
        rows = _read_xlsx(path) if suffix == ".xlsx" else _read_csv(path)
    except PermissionError as e:
        raise TableError(f"无法读取 {path.name}：文件可能正在 Excel 中打开，请先关闭该文件") from e
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as e:
        raise TableError(f"无法读取 {path.name}：{e}") from e
    return _normalize(rows)


def _normalize(rows: list[list[str]]) -> list[list[str]]:
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


# —— CSV ——

def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, lineterminator="\r\n").writerows(rows)


def _read_csv(path: Path) -> list[list[str]]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("gb18030")
    return [list(r) for r in csv.reader(io.StringIO(text, newline=""))]


# —— xlsx 写出 ——

def _col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _display_width(text: str) -> int:
    return max((sum(2 if ord(ch) > 127 else 1 for ch in line) for line in text.split("\n")),
               default=0)


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>')
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>')
_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<workbook xmlns="{_MAIN_NS}" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="属性" sheetId="1" r:id="rId1"/></sheets></workbook>')
_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>')
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<styleSheet xmlns="{_MAIN_NS}">'
    '<fonts count="2"><font><sz val="11"/><name val="等线"/></font>'
    '<font><b/><sz val="11"/><name val="等线"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="49" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
    '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="49" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1" applyNumberFormat="1"/>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="常规" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>')


def _sheet_xml(rows: list[list[str]], readonly_cols: frozenset[int]) -> str:
    width = max((len(r) for r in rows), default=0)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           f'<worksheet xmlns="{_MAIN_NS}">',
           '<sheetViews><sheetView workbookViewId="0">'
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews>',
           '<cols>']
    for c in range(width):
        w = max((_display_width(r[c]) for r in rows if c < len(r)), default=0) + 2
        style = _XF_READONLY if c in readonly_cols else _XF_TEXT
        out.append(f'<col min="{c + 1}" max="{c + 1}" width="{min(max(w, 8), 60)}" '
                   f'style="{style}" customWidth="1"/>')
    out.append(f'<col min="{width + 1}" max="{width + _EXTRA_COLS}" width="12" '
               f'style="{_XF_TEXT}" customWidth="1"/>')
    out.append('</cols><sheetData>')
    for r, row in enumerate(rows):
        out.append(f'<row r="{r + 1}">')
        for c, value in enumerate(row):
            if value == "":
                continue
            style = (_XF_HEADER if r == 0 else
                     _XF_READONLY if c in readonly_cols else _XF_TEXT)
            text = escape(_ILLEGAL_XML.sub("", value))
            out.append(f'<c r="{_col_letter(c)}{r + 1}" s="{style}" t="inlineStr">'
                       f'<is><t xml:space="preserve">{text}</t></is></c>')
        out.append('</row>')
    out.append('</sheetData></worksheet>')
    return "".join(out)


def _write_xlsx(path: Path, rows: list[list[str]], readonly_cols: frozenset[int]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", _WORKBOOK)
        z.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows, readonly_cols))


# —— xlsx 读取 ——

_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

_DATE_FMT_IDS = frozenset({14, 15, 16, 17, 22, 27, 28, 29, 30, 31, 36,
                           50, 51, 52, 53, 54, 55, 56, 57, 58})
_FMT_NOISE = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.')


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def _row_index(ref: str) -> int:
    digits = "".join(ch for ch in ref if ch.isdigit())
    return int(digits) - 1


def _text_of(el) -> str:
    """拼接 <t> 文本，跳过注音 <rPh>。"""
    parts = []
    for child in el:
        if child.tag == f"{_M}t":
            parts.append(child.text or "")
        elif child.tag == f"{_M}r":
            parts.append(_text_of(child))
    return "".join(parts)


def _is_date_format(code: str) -> bool:
    cleaned = _FMT_NOISE.sub("", code).lower()
    return "y" in cleaned or "d" in cleaned


def _date_styles(styles) -> list[bool]:
    """cellXfs 下标 → 是否为日期格式。"""
    if styles is None:
        return []
    custom = {int(f.get("numFmtId")): f.get("formatCode", "")
              for f in styles.iter(f"{_M}numFmt")}
    xfs = styles.find(f"{_M}cellXfs")
    result = []
    for xf in (xfs if xfs is not None else []):
        fid = int(xf.get("numFmtId", "0"))
        result.append(fid in _DATE_FMT_IDS or (fid in custom and _is_date_format(custom[fid])))
    return result


def _format_number(v: str, is_date: bool, date1904: bool) -> str:
    try:
        x = float(v)
    except ValueError:
        return v
    if is_date:
        epoch = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
        dt = epoch + timedelta(minutes=round(x * 24 * 60))
        return dt.strftime("%Y-%m-%d %H:%M" if dt.hour or dt.minute else "%Y-%m-%d")
    if x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return v


def _first_sheet_path(z: zipfile.ZipFile, workbook) -> str:
    sheet = workbook.find(f"{_M}sheets/{_M}sheet")
    if sheet is None:
        raise ValueError("工作簿中没有工作表")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid = sheet.get(_REL)
    target = next(r.get("Target") for r in rels.iter(_PKG_REL) if r.get("Id") == rid)
    return target.lstrip("/") if target.startswith("/") else "xl/" + target


def _read_xlsx(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = ET.fromstring(z.read(_first_sheet_path(z, workbook)))
        shared = ([_text_of(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
                  if "xl/sharedStrings.xml" in names else [])
        styles = ET.fromstring(z.read("xl/styles.xml")) if "xl/styles.xml" in names else None
    pr = workbook.find(f"{_M}workbookPr")
    date1904 = pr is not None and pr.get("date1904", "0").lower() in ("1", "true")
    is_date = _date_styles(styles)

    rows: list[list[str]] = []
    for row in sheet.iter(f"{_M}row"):
        r = int(row.get("r")) - 1 if row.get("r") else len(rows)
        rows += [[] for _ in range(r - len(rows))]
        cells: list[str] = []
        for c in row.findall(f"{_M}c"):
            ref = c.get("r")
            col = _col_index(ref) if ref else len(cells)
            cells += [""] * (col - len(cells))
            t, v = c.get("t", "n"), c.find(f"{_M}v")
            raw = v.text or "" if v is not None else ""
            if t == "s":
                value = shared[int(raw)] if raw else ""
            elif t == "inlineStr":
                is_ = c.find(f"{_M}is")
                value = _text_of(is_) if is_ is not None else ""
            elif t == "b":
                value = "TRUE" if raw == "1" else "FALSE" if raw else ""
            elif t in ("str", "e"):
                value = raw
            else:
                s = int(c.get("s", "0"))
                value = _format_number(raw, s < len(is_date) and is_date[s], date1904) if raw else ""
            cells.append(value)
        rows.append(cells)
    return rows

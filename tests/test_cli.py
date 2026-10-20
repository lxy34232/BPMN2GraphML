import shutil

import pytest

from bpmn2graphml.cli import main
from bpmn2graphml.table_io import read_table, write_table
from conftest import fixture_paths


@pytest.fixture
def graphml(tmp_path):
    out = tmp_path / "m.graphml"
    assert main(["merge", *map(str, fixture_paths()), "-o", str(out)]) == 0
    return out


def test_cli_merge(graphml):
    assert graphml.exists()
    report = graphml.with_name("m.merge-report.txt")
    assert "部门领导审核" in report.read_text(encoding="utf-8")


def test_cli_tobpmn_both(graphml, tmp_path):
    merged, split = tmp_path / "out.bpmn", tmp_path / "split"
    assert main(["tobpmn", str(graphml), "--merged", str(merged), "--split", str(split)]) == 0
    assert merged.exists()
    assert len(list(split.glob("*.bpmn"))) == 3


def test_cli_tobpmn_requires_mode(graphml):
    with pytest.raises(SystemExit):
        main(["tobpmn", str(graphml)])


def test_cli_bad_input(tmp_path, capsys):
    bad = tmp_path / "x.bpmn"
    bad.write_text("hello", encoding="utf-8")
    assert main(["merge", str(bad), "-o", str(tmp_path / "m.graphml")]) == 1
    assert "x.bpmn" in capsys.readouterr().err


def test_cli_missing_file(tmp_path, capsys):
    assert main(["merge", str(tmp_path / "nope.bpmn"), "-o", str(tmp_path / "m.graphml")]) == 1
    assert "nope.bpmn" in capsys.readouterr().err


def test_gui_builds():
    tk = pytest.importorskip("tkinter")
    from bpmn2graphml.gui import App
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    try:
        app = App(root)
        assert [app.notebook.tab(t, "text") for t in app.notebook.tabs()] == [
            "BPMN → GraphML", "GraphML → BPMN", "属性表"]
        assert hasattr(app, "prop_files") and hasattr(app, "props_log")
        assert hasattr(app, "view_result_button") and hasattr(app, "open_viewer_button")
    finally:
        root.destroy()


def test_cli_view_file(monkeypatch, tmp_path):
    import tempfile

    import bpmn2graphml.viewer_launch as vl
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    opened = []
    monkeypatch.setattr(vl, "_default_opener", opened.append)
    assert main(["view", str(fixture_paths()[0])]) == 0
    assert len(opened) == 1 and opened[0].endswith("view.html")


def test_cli_view_missing(tmp_path, capsys):
    assert main(["view", str(tmp_path / "nope.bpmn")]) == 1
    assert "nope.bpmn" in capsys.readouterr().err


def _copies(tmp_path):
    return [shutil.copy(p, tmp_path / p.name) for p in fixture_paths()]


def test_cli_props_roundtrip(tmp_path, capsys):
    paths = _copies(tmp_path)
    table = tmp_path / "t.xlsx"
    assert main(["props-export", *map(str, paths), "-o", str(table)]) == 0
    assert "已导出" in capsys.readouterr().out
    rows = read_table(table)  # 新导出的表还没有属性列，先加一列
    write_table(table, [r + (["负责人"] if i == 0 else ["张三"]) for i, r in enumerate(rows)])
    assert main(["props-import", str(table), *map(str, paths)]) == 0
    assert "t.import-report.txt" in capsys.readouterr().out


def test_cli_props_import_abort(tmp_path, capsys):
    (tmp_path / "t.csv").write_text("节点名称\n审核\n", encoding="utf-8")
    paths = _copies(tmp_path)
    assert main(["props-import", str(tmp_path / "t.csv"), *map(str, paths)]) == 1
    assert "导入已中止" in capsys.readouterr().out


def test_cli_props_export_bad_input(tmp_path, capsys):
    bad = tmp_path / "x.bpmn"
    bad.write_text("hello", encoding="utf-8")
    assert main(["props-export", str(bad), "-o", str(tmp_path / "t.xlsx")]) == 1
    assert "x.bpmn" in capsys.readouterr().err

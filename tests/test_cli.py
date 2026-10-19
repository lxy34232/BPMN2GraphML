import pytest

from bpmn2graphml.cli import main
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
        assert len(app.notebook.tabs()) == 2
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

"""Wizard: reine Helfer und Dialogabbruch (ohne IFC-Laden testbar)."""

from pathlib import Path
from types import SimpleNamespace

from fgc.pipeline import wizard
from fgc.pipeline.wizard import (
    ask_number,
    ask_yes_no,
    discover_ifc_files,
    run_wizard,
    walls_by_filter,
)


def scripted(*answers):
    it = iter(answers)
    return lambda _prompt="": next(it)


def test_discover_includes_cwd_files(tmp_path):
    (tmp_path / "eigenes.ifc").write_text("", encoding="utf-8")
    files = discover_ifc_files(tmp_path)
    assert (tmp_path / "eigenes.ifc").resolve() in files
    assert len(files) == len(set(files))  # dedupliziert


def test_ask_number_retries_until_valid(capsys):
    assert ask_number("? ", 3, input_fn=scripted("0", "vier", "2")) == 1


def test_ask_number_quit_and_empty_cancel():
    assert ask_number("? ", 3, input_fn=scripted("q")) is None
    assert ask_number("? ", 3, input_fn=scripted("")) is None


def test_ask_yes_no_default_and_explicit():
    assert ask_yes_no("? ", default=True, input_fn=scripted("")) is True
    assert ask_yes_no("? ", default=True, input_fn=scripted("n")) is False
    assert ask_yes_no("? ", default=False, input_fn=scripted("ja")) is True


def test_walls_by_filter_groups_by_is_external():
    walls = [
        SimpleNamespace(is_external=True),
        SimpleNamespace(is_external=False),
        SimpleNamespace(is_external=None),
        SimpleNamespace(is_external=True),
    ]
    groups = walls_by_filter(walls)
    assert len(groups["alle"]) == 4
    assert len(groups["aussen"]) == 2
    assert len(groups["innen"]) == 1
    assert len(groups["unbekannt"]) == 1


def test_run_wizard_cancel_at_model_selection(monkeypatch, capsys):
    monkeypatch.setattr(wizard, "discover_ifc_files", lambda: [Path("egal.ifc")])
    assert run_wizard(input_fn=scripted("q")) == 0

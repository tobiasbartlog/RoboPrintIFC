"""Gegenprüfung der Muster-API: Fehlerfälle mit deutscher Meldung, Bereichsprüfung der Regler,
leerer Pfad als Regelfehler, ungültige Querschnitte, CLI mit denselben Prüfungen."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roboprint import patterns as pt
from roboprint.api import create_app
from roboprint.api_patterns import german_validation_message
from roboprint.contracts import PatternPreview
from roboprint.patterns.checks import check_outline, check_spec, check_value
from roboprint.patterns.cli_preview import _cli

ROOT = Path(__file__).resolve().parents[2]
BOX = {"length_mm": 600, "thickness_mm": 200}
PRESET = ROOT / "core" / "src" / "roboprint" / "patterns" / "presets" / "schalen.json"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "runs", tmp_path / "projects", ROOT)) as c:
        yield c


def detail(r) -> str:
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert isinstance(d, str)
    return d


# ----------------------------------------------------------------- Regler außerhalb des Bereichs


@pytest.mark.parametrize(
    ("params", "needle"),
    [
        ({"bead_width_mm": 9999}, "über dem Maximum 60 mm"),
        ({"bead_width_mm": 5}, "unter dem Minimum 10 mm"),
        ({"shells": 99}, "über dem Maximum 4"),
        ({"shells": 0}, "unter dem Minimum 1"),
        ({"shells": 2.5}, "keine ganze Zahl"),
        ({"shells": "zwei"}, "keine Zahl"),
        ({"layer_height_mm": True}, "keine Zahl"),
        ({"layer_order": "kreuz"}, "möglich sind same, alternate"),
        ({"bead_widht_mm": 30}, "Unbekannte Parameter: bead_widht_mm"),
    ],
)
def test_out_of_range_params_give_422_in_german(client, params, needle):
    d = detail(
        client.post("/api/patterns/preview", json={"pattern": "schalen", "params": params, "outline": BOX})
    )
    assert needle in d
    # dieselbe Prüfung beim Speichern eines Presets und im SVG-Export
    d = detail(
        client.post("/api/patterns/presets", json={"name": "x", "pattern": "schalen", "params": params})
    )
    assert needle in d
    d = detail(
        client.get("/api/patterns/preview.svg", params={"pattern": "schalen", "params": json.dumps(params)})
    )
    assert needle in d


@pytest.mark.parametrize(
    ("params", "needle"),
    [
        ({"v_print_mm_s": 0}, "unter dem Minimum"),
        ({"v_print_mm_s": -5}, "unter dem Minimum"),
        ({"step_mm": 0.01}, "unter dem Minimum"),
        ({"step_mm": 0.1}, "unter dem Minimum"),
        ({"chord_tol_mm": 0.001}, "unter dem Minimum"),
        ({"chord_tol_mm": 5}, "über dem Maximum"),
        ({"eps": 0.99}, "Regelkonstante"),
        ({"eps": -0.1}, "Regelkonstante"),
        ({"delta_mm": -1}, "unter dem Minimum"),
        ({"delta_mm": 50}, "über dem Maximum"),
        ({"link_max_mm": -1}, "unter dem Minimum"),
        ({"contact_tol_mm": -1}, "unter dem Minimum"),
        ({"contact_tol_mm": 10}, "über dem Maximum"),
    ],
)
def test_rule_and_sampling_params_are_checked(client, params, needle):
    """Gegenprüfung M6 (Runde 2): Auch die übrigen Kernwerte (Abtastung, Toleranzen, Geschwindigkeit)
    werden geprüft: v = 0 gab 500 (Division), step_mm = 0,01 einen Speicherüberlauf nach Minuten,
    eps = 0,99 schaltete M2 ab."""
    d = detail(
        client.post("/api/patterns/preview", json={"pattern": "schalen", "params": params, "outline": BOX})
    )
    assert needle in d
    with pytest.raises(ValueError, match=needle):
        check_spec({"pattern": "schalen", "params": params})


def test_rule_and_sampling_defaults_are_accepted(client):
    defaults = {
        k: getattr(pt.PatternParams(), k)
        for k in (
            "v_print_mm_s",
            "step_mm",
            "chord_tol_mm",
            "eps",
            "delta_mm",
            "link_max_mm",
            "contact_tol_mm",
        )
    }
    r = client.post("/api/patterns/preview", json={"pattern": "schalen", "params": defaults, "outline": BOX})
    assert r.status_code == 200, r.text


def test_cli_rejects_zero_speed_with_exit_2(tmp_path, capsys):
    bad = tmp_path / "v0.json"
    bad.write_text(json.dumps({"name": "v0", "pattern": "schalen", "params": {"v_print_mm_s": 0}}))
    assert _cli([str(bad), str(tmp_path / "v0.svg")]) == 2
    assert "v_print_mm_s" in capsys.readouterr().err


def test_kernel_rejects_nonpositive_speed_and_negative_tolerances():
    for kw in ({"v_print_mm_s": 0.0}, {"delta_mm": -1.0}, {"link_max_mm": -1.0}, {"contact_tol_mm": -0.1}):
        with pytest.raises(ValueError):
            pt.PatternParams(**kw).validate()


def test_huge_polygon_outline_is_422(client):
    big = {"polygon": [[0, 0], [200000, 0], [200000, 300], [0, 300]]}
    assert "zu groß" in detail(client.post("/api/patterns/preview", json={"outline": big}))
    many = {"polygon": [[float(i), 0.0] for i in range(6000)] + [[6000.0, 300.0], [0.0, 300.0]]}
    assert "Punkte" in detail(client.post("/api/patterns/preview", json={"outline": many}))


def test_edge_values_of_core_params_are_accepted(client):
    for spec in pt.CORE_PARAM_SPECS:
        if spec.kind in ("float", "int"):
            for v in (spec.minimum, spec.maximum):
                v = int(v) if spec.kind == "int" else v
                assert check_value(spec, v) == v
    r = client.post(
        "/api/patterns/preview", json={"params": {"bead_width_mm": 60, "shells": 1}, "outline": BOX}
    )
    assert r.status_code == 200, r.text


def test_unknown_pattern_or_preset_is_422_not_404(client):
    """404 hieße „Route fehlt“; die Route gibt es, nur der Name im Body ist unbekannt."""
    for body in ({"pattern": "gibt_es_nicht"}, {"preset": "gibt_es_nicht"}):
        assert "Unbekanntes Muster oder Preset" in detail(client.post("/api/patterns/preview", json=body))


# ----------------------------------------------------------------- Formfehler (pydantic)


def test_nan_in_body_gives_422_not_500(client):
    for raw in (
        '{"params": {"bead_width_mm": NaN}}',
        '{"outline": {"length_mm": Infinity, "thickness_mm": 200}}',
    ):
        r = client.post("/api/patterns/preview", content=raw, headers={"content-type": "application/json"})
        d = detail(r)
        assert "endliche Zahl" in d or "höchstens" in d, d
        json.dumps(r.json(), allow_nan=False)  # Antwort ist striktes JSON


def test_form_errors_are_german_and_name_the_field(client):
    d = detail(client.post("/api/patterns/preview", json={"outline": {"length_mm": -1, "thickness_mm": 200}}))
    assert d == "Ungültige Anfrage: outline.length_mm muss größer als 0 sein"
    d = detail(client.post("/api/patterns/preview", json={"layer": -1}))
    assert d == "Ungültige Anfrage: layer muss mindestens 0 sein"
    d = detail(client.post("/api/patterns/preview", json={"unbekannt": 1}))
    assert "unbekannt ist kein erlaubtes Feld" in d
    d = detail(client.post("/api/patterns/presets", json={"id": "../x", "name": "x", "pattern": "schalen"}))
    assert d.startswith("Ungültige Anfrage: id hat ein ungültiges Format")
    r = client.post("/api/patterns/preview", json={"layer": -1})
    assert r.json()["errors"][0]["loc"] == ["body", "layer"]  # Rohfehler bleiben lesbar
    d = detail(client.get("/api/patterns/preview.svg", params={"params": "{kaputt"}))
    assert "kein gültiges JSON" in d


def test_other_routes_keep_fastapi_error_format(client):
    raw = '{"params": {"x": NaN}, "unbekannt": 1}'
    r = client.post("/api/projects/abc/jobs", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


def test_german_validation_message_picks_the_meant_union_branch():
    errors = [
        {"type": "missing", "loc": ["body", "outline", "PatternOutlineBox", "length_mm"]},
        {"type": "missing", "loc": ["body", "outline", "PatternOutlineBox", "thickness_mm"]},
        {"type": "extra_forbidden", "loc": ["body", "outline", "PatternOutlineBox", "polygon"]},
        {"type": "too_short", "loc": ["body", "outline", "PatternOutlinePolygon", "polygon"]},
    ]
    assert german_validation_message(errors) == "Ungültige Anfrage: outline.polygon hat zu wenige Einträge"


# ----------------------------------------------------------------- Querschnitt und leerer Pfad


@pytest.mark.parametrize(
    ("outline", "needle"),
    [
        ({"polygon": [[0, 0], [100, 0], [200, 0]]}, "ohne Fläche"),
        ({"polygon": [[0, 0], [600, 300], [600, 0], [0, 200]]}, "überschneidet sich selbst"),
        (
            {
                "polygon": [[0, 0], [600, 0], [600, 200], [0, 200]],
                "holes": [[[700, 0], [800, 0], [800, 100]]],
            },
            "Loch liegt außerhalb",
        ),
    ],
)
def test_invalid_outline_is_422(client, outline, needle):
    assert needle in detail(client.post("/api/patterns/preview", json={"outline": outline}))
    with pytest.raises(ValueError, match=needle):
        check_outline(outline)


def test_too_narrow_outline_is_a_rule_error_not_ok(client):
    """Ohne Pfad meldet der Kern keine Verstöße; die Vorschau darf dann nicht `ok` sein."""
    r = client.post("/api/patterns/preview", json={"outline": {"length_mm": 20, "thickness_mm": 20}})
    assert r.status_code == 200
    model = PatternPreview.model_validate(r.json())
    assert not model.paths and not model.ok
    assert [v.rule for v in model.violations if v.severity == "error"] == ["M1"]
    assert "Kein druckbarer Pfad" in model.violations[0].message


def test_check_spec_lists_pattern_params_for_unknown_keys():
    for name in pt.names():
        own = [p.name for p in pt.get(name).params]
        with pytest.raises(ValueError, match="Unbekannte Parameter: zzz"):
            check_spec({"pattern": name, "params": {"zzz": 1}})
        check_spec({"pattern": name, "params": {p.name: p.default for p in pt.get(name).params}})
        assert all(isinstance(n, str) for n in own)


# ----------------------------------------------------------------- CLI


def test_cli_writes_valid_svg_and_rejects_bad_input(tmp_path, capsys):
    svg = tmp_path / "out" / "schalen.svg"
    assert _cli([str(PRESET), str(svg), "--length", "1200", "--thickness", "300"]) == 0
    root = ET.parse(svg).getroot()
    assert (
        root.tag == "{http://www.w3.org/2000/svg}svg"
        and root.find("{http://www.w3.org/2000/svg}polyline") is not None
    )
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "A & B <x>", "pattern": "schalen", "params": {"bead_width_mm": 9999}}))
    assert _cli([str(bad), str(tmp_path / "bad.svg")]) == 2
    assert "Maximum 60 mm" in capsys.readouterr().err
    assert _cli([str(PRESET), str(tmp_path / "l.svg"), "--layer", "-1"]) == 2
    # Sonderzeichen im Namen bleiben gültiges XML; zu schmaler Querschnitt ist Regelfehler (Exit 1)
    ok = tmp_path / "amp.json"
    ok.write_text(json.dumps({"name": "A & B <x>", "pattern": "schalen", "params": {}}))
    assert _cli([str(ok), str(tmp_path / "amp.svg"), "--length", "20", "--thickness", "20"]) == 1
    ET.parse(tmp_path / "amp.svg")
    assert "Kein druckbarer Pfad" in capsys.readouterr().err

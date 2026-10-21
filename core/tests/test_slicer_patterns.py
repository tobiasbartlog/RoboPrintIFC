"""Slicer mit Druckmuster (M3.1): Vertrag, opt-in-Parameter, Schichtpfade als Ringe.

Format: docs/muster/ARTEFAKT-FORMAT.md (Nachtrag M3). Ohne Musterparameter muss der Slicer
bitgleich zu vorher schneiden (Prüfsumme des S1-Toolpaths vom Stand vor M3.1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from shapely.geometry import Point

from roboprint import drl, patterns
from roboprint.contracts import Ring, Scenario, Toolpath, dump_json, load_json
from roboprint.geometry import make_box
from roboprint.pipeline import assumptions
from roboprint.planner import PlannerParams, from_overrides, slice_params
from roboprint.slicer import SliceParams, slice_part, to_toolpath
from roboprint.slicer_patterns import path_groups, pattern_params, uses_pattern

REPO = Path(__file__).resolve().parents[2]
PRESETS = REPO / "core" / "src" / "roboprint" / "patterns" / "presets"
FUGENWAND = str(PRESETS / "fugenwand.json")
#: sha256 des kompakten Toolpath-JSON von S1 (600 x 200 x 400, T_WP = I) mit SliceParams() vor M3.1
S1_DEFAULT_SHA = "dc691e55b008c65844eb609c229e0ae5f0777a7f612cdaef1c8006c43bc1f103"
STRING_KINDS = ("print", "link", "approach", "retract")


def _box(lx: float, ly: float, lz: float):
    return make_box([lx, ly, lz], origin=[-lx / 2, -ly / 2, 0.0])


def _sha(tp: Toolpath) -> str:
    txt = json.dumps(tp.model_dump(mode="json"), separators=(",", ":"))
    return hashlib.sha256(txt.encode()).hexdigest()


def _slice(lz: float = 60.0, ly: float = 200.0, **kw):
    return slice_part(_box(600.0, ly, lz), SliceParams(**kw))


def _by_layer(sliced) -> dict[int, list]:
    out: dict[int, list] = {}
    for r in sliced.rings:
        out.setdefault(r.layer, []).append(r)
    return out


def _check_strand(sliced, n_layers: int, w: float = 30.0) -> None:
    """Ein Strang je Teil: alle Verbinder erlaubt, in der Schicht Länge 0, Schichtwechsel senkrecht."""
    rings = sliced.rings
    assert sorted({r.layer for r in rings}) == list(range(n_layers))
    pairs = zip(rings[:-1], rings[1:], strict=True)
    assert all(r.layer <= s.layer for r, s in pairs), "nach Schicht geordnet"
    for a, b in zip(rings[:-1], rings[1:], strict=True):
        assert a.link_next, (a.layer, a.kind, b.layer, b.kind)
        gap = float(np.linalg.norm(b.points[0, :2] - a.points[-1, :2]))
        if b.layer == a.layer + 1:
            assert gap <= 0.5, f"Schichtwechsel {a.layer}->{b.layer} nicht senkrecht: {gap:.2f} mm"
        else:
            assert b.layer == a.layer
            assert gap <= 1e-6, f"Verbinder in Schicht {a.layer}: {gap:.3f} mm"
    assert not rings[-1].link_next
    for r in rings:
        assert np.allclose(r.points[:, 2], (r.layer + 1) * sliced.layer_height_mm)
        assert np.allclose(r.approach, r.points[0] + [0, 0, 20.0])
        assert np.allclose(r.retract, r.points[-1] + [0, 0, 20.0])


def _check_closed_flags(sliced) -> None:
    for r in sliced.rings:
        ends_meet = bool(np.linalg.norm(r.points[-1] - r.points[0]) <= 1e-6)
        assert r.closed == ends_meet
        steps = np.linalg.norm(np.diff(r.points, axis=0), axis=1)
        assert steps.min() > 1e-9, "doppelte Wegpunkte"
        assert steps.max() <= 20.0 + 1e-6, "Wegpunktabstand > step_mm"


# --------------------------------------------------------------------------- Standard unverändert


def test_default_s1_toolpath_bit_identical() -> None:
    sliced = slice_part(_box(600.0, 200.0, 400.0))
    assert sliced.pattern is None
    tp = to_toolpath(sliced, np.eye(4), "box_01")
    assert _sha(tp) == S1_DEFAULT_SHA
    assert "pattern" not in tp.model_dump(mode="json")
    assert all(r.closed and r.kind in ("outer", "inner") for r in tp.rings)
    # explizit gesetzte Standardwerte der Musterparameter ändern nichts
    explicit = SliceParams(layer_order="same", infill_pattern="none", outfill_pattern="none",
                           pattern_params="", pattern_preset="")
    assert not uses_pattern(explicit)
    again = to_toolpath(slice_part(_box(600.0, 200.0, 400.0), explicit), np.eye(4), "box_01")
    assert _sha(again) == S1_DEFAULT_SHA


def test_default_planner_params_unchanged() -> None:
    p = PlannerParams()
    assert not p.uses_pattern
    assert slice_params(p) == SliceParams()
    summ = p.as_summary()
    for k in ("layer_order", "infill_pattern", "outfill_pattern", "pattern_params", "pattern_preset"):
        assert k not in summ, "ohne Muster bleibt summary.params wie bisher"
    assert not any("Druckmuster" in a for a in assumptions(p))


# --------------------------------------------------------------------------- Grundmuster alternate


def test_alternate_two_shells_vertical_layer_change() -> None:
    sliced = _slice(layer_order="alternate")
    _check_strand(sliced, 6)
    _check_closed_flags(sliced)
    assert sliced.pattern == {"layer_order": "alternate", "infill": "none", "outfill": "none", "params": {}}
    layers = _by_layer(sliced)
    for L, rs in layers.items():
        assert [r.kind for r in rs] == (["outer", "inner"] if L % 2 == 0 else ["inner", "outer"])
        assert all(not r.closed for r in rs), "Schalenkette: offene Segmente mit S-Kurve"
    # Schicht L + 1 ist die Umkehrung von Schicht L (gleiche XY-Geometrie)
    xy0 = np.vstack([r.points[:, :2] for r in layers[0]])
    xy1 = np.vstack([r.points[:, :2] for r in layers[1]])
    assert np.allclose(xy0[::-1], xy1, atol=1e-9)


def test_alternate_single_shell_closed_ring() -> None:
    sliced = _slice(layer_order="alternate", shells=1)
    _check_strand(sliced, 6)
    _check_closed_flags(sliced)
    assert all(r.closed and r.kind == "outer" for r in sliced.rings)
    tp = to_toolpath(sliced, np.eye(4), "x")
    assert all(r.closed and r.waypoints[0] == r.waypoints[-1] for r in tp.rings)
    # Umlaufsinn wechselt je Schicht
    a = [_signed_area(r.points[:, :2]) for r in sliced.rings[:2]]
    assert a[0] * a[1] < 0


def _signed_area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def test_same_layer_order_with_pattern_is_not_vertical() -> None:
    """`same` mit Muster: Schichtwechsel diagonal, Verbinder nur nach SPEC §5.3 (link_allowed)."""
    sliced = _slice(layer_order="same", pattern_params='{"corner_radius_mm": 22.5}')
    rs = sliced.rings
    changes = [(a, b) for a, b in zip(rs[:-1], rs[1:], strict=True) if b.layer == a.layer + 1]
    gaps = [float(np.linalg.norm(b.points[0, :2] - a.points[-1, :2])) for a, b in changes]
    assert min(gaps) > 0.5
    assert all(a.link_next == (g <= 60.0) for (a, _), g in zip(changes, gaps, strict=True))


# --------------------------------------------------------------------------- Fugenwand


def test_fugenwand_preset_one_strand_kinds() -> None:
    sliced = _slice(pattern_preset=FUGENWAND)
    _check_strand(sliced, 6)
    _check_closed_flags(sliced)
    assert sliced.pattern["outfill"] == "fugenwand" and sliced.pattern["layer_order"] == "alternate"
    assert sliced.pattern["params"]["field_length_mm"] == 300.0
    kinds = {r.kind for r in sliced.rings}
    assert kinds == {"outfill", "web"}
    for rs in _by_layer(sliced).values():
        # stoßende Segmente gleicher kind sind zusammengefasst
        assert all(a.kind != b.kind for a, b in zip(rs[:-1], rs[1:], strict=True))
        assert {r.shell for r in rs if r.kind == "outfill"} == {0}
    # im Teil (M5): alle Wegpunkte mindestens w/2 innerhalb der Außenkontur (Toleranz 1 mm)
    xy = np.vstack([r.points[:, :2] for r in sliced.rings])
    assert np.all(np.abs(xy[:, 0]) <= 300.0 - 15.0 + 1.0) and np.all(np.abs(xy[:, 1]) <= 100.0 - 15.0 + 1.0)


def test_fugenwand_rings_keep_pattern_points() -> None:
    """Die Ringe enthalten alle Punkte der Mustersegmente (keine Vergröberung der Kurven)."""
    p = SliceParams(pattern_preset=FUGENWAND)
    pp = pattern_params(p)
    planar, _ = _box(600.0, 200.0, 10.0).section([0, 0, 5.0], [0, 0, 1]).to_2D(to_2D=np.eye(4))
    sec = {0: planar.polygons_full[0]}
    paths = patterns.plan_pattern(sec, pp)
    seg_pts = np.vstack([s.points for s in paths[0].segments])
    ring_pts = np.vstack([r.points[:, :2] for r in slice_part(_box(600.0, 200.0, 10.0), p).rings])
    d = np.min(np.linalg.norm(seg_pts[:, None, :] - ring_pts[None, :, :], axis=2), axis=1)
    assert d.max() <= 1e-9


def test_fugenwand_toolpath_contract_roundtrip(tmp_path: Path) -> None:
    sliced = _slice(lz=30.0, pattern_preset=FUGENWAND)
    tp = to_toolpath(sliced, np.eye(4), "box_01")
    assert tp.pattern is not None and tp.pattern.outfill == "fugenwand"
    assert any(not r.closed for r in tp.rings)
    out = dump_json(tp, tmp_path / "toolpath.json")
    data = json.loads(out.read_text())
    assert data["pattern"]["layer_order"] == "alternate"
    assert load_json(out, Toolpath) == tp


def test_scenario_values_override_preset() -> None:
    pp = pattern_params(SliceParams(pattern_preset=FUGENWAND, layer_order="alternate",
                                    pattern_params='{"field_length_mm": 250.0}', bead_width_mm=25.0))
    assert pp.get("field_length_mm") == 250.0 and pp.bead_width_mm == 25.0
    with pytest.raises(ValueError):
        pattern_params(SliceParams(outfill_pattern="gibtsnicht"))
    with pytest.raises(ValueError):  # Fugenwand baut den ganzen Pfad, Infill daneben ist ein Widerspruch
        pattern_params(SliceParams(pattern_preset=FUGENWAND, infill_pattern="fugenwand"))


# --------------------------------------------------------------------------- Sinus (falls registriert)


@pytest.mark.skipif("sinus" not in patterns.names(), reason="Familie Wellen noch nicht gemergt")
def test_sinus_infill_strand() -> None:
    sliced = _slice(layer_order="alternate", infill_pattern="sinus")
    _check_strand(sliced, 6)
    _check_closed_flags(sliced)
    assert "infill" in {r.kind for r in sliced.rings}
    for L, rs in _by_layer(sliced).items():
        # Infill hängt außen → innen am Ende der Schalen; umgekehrte Schichten beginnen damit
        assert (rs[-1] if L % 2 == 0 else rs[0]).kind in ("infill", "web")


# --------------------------------------------------------------------------- Parameter und Vertrag


def test_scenario_and_overrides_accept_pattern_params() -> None:
    scn = json.loads((REPO / "spec" / "scenarios" / "S1_modul_referenz.json").read_text())
    scn["params"] = {"layer_order": "alternate", "infill_pattern": "none",
                     "pattern_params": {"corner_radius_mm": 22.5, "seam_corner": [1, -1]}}
    model = Scenario.model_validate(scn)
    p = from_overrides(model.params)
    assert p.uses_pattern and p.layer_order == "alternate"
    assert json.loads(p.pattern_params) == {"corner_radius_mm": 22.5, "seam_corner": [1, -1]}
    summ = p.as_summary()
    assert summ["layer_order"] == "alternate" and isinstance(summ["pattern_params"], str)
    assert "infill_pattern" not in summ
    assert any(a.startswith("Druckmuster (opt-in, A): Schichtfolge alternate") for a in assumptions(p))
    sp = slice_params(p)
    assert pattern_params(sp).corner_radius_mm == 22.5
    with pytest.raises(ValueError):
        from_overrides({"layer_order": "zickzack"})
    with pytest.raises(ValueError):
        from_overrides({"z_lift_mm": {"a": 1.0}})
    with pytest.raises(ValueError):
        from_overrides({"pattern_params": "[1, 2]"})


def test_ring_contract_kinds_and_open_segments() -> None:
    pose = [0.0, 0.0, 10.0, 0.0, 1.0, 0.0, 0.0]
    other = [5.0, 0.0, 10.0, 0.0, 1.0, 0.0, 0.0]
    for kind in ("infill", "web", "outfill"):
        Ring(layer=0, shell=2, kind=kind, closed=False, waypoints=[pose, other])
    with pytest.raises(ValidationError):
        Ring(layer=0, shell=0, kind="outer", closed=False, waypoints=[pose])
    with pytest.raises(ValidationError):
        Ring(layer=0, shell=0, kind="outer", closed=True, waypoints=[pose, other])
    with pytest.raises(ValidationError):
        Ring(layer=0, shell=0, kind="zelle", closed=False, waypoints=[pose, other])


def test_path_groups_merge_only_same_kind() -> None:
    seg = patterns.Segment
    path = patterns.LayerPath(0, 0, [
        seg("outfill", 0, [[0, 0], [10, 0]]),
        seg("outfill", 0, [[10, 0], [20, 0]]),
        seg("web", 2, [[20, 0], [20, 10]]),
        seg("web", 2, [[20, 11], [0, 11]]),  # Verbinder 1 mm: nicht zusammenfassen
        seg("outfill", 0, [[0, 11], [0, 0]]),
    ])  # fmt: skip
    groups = path_groups(path)
    assert [(k, len(p), c) for k, _, p, c in groups] == [("outfill", 3, False), ("web", 2, False),
                                                        ("web", 2, False), ("outfill", 2, False)]


def test_drl_header_lists_pattern_only_when_set() -> None:
    from types import SimpleNamespace

    def header(run_params: dict) -> str:
        part = SimpleNamespace(part_id="P", wall_id="W", status="machbar")
        tp = SimpleNamespace(rings=[])
        pp = SimpleNamespace(params=drl.DrlParams(), provenance=None, scenario_id="S", part=part,
                             toolpath=tp, trajectory=SimpleNamespace(t_s=[0.0]), run_params=run_params)
        return "\n".join(drl._header(pp, "v2", []))

    assert "Druckmuster" not in header({})
    txt = header({"layer_order": "alternate", "pattern_preset": "p.json"})
    assert "A Schichtfolge              alternate (Druckmuster, opt-in)" in txt
    assert "A Muster-Preset             p.json" in txt
    assert "Weitere Laufparameter" not in txt


def test_link_allowed_vertical_point_case() -> None:
    """Senkrechter Schichtwechsel: waagrechte Länge 0 ist ein Punkt im Querschnitt beider Schichten."""
    sliced = _slice(lz=20.0, layer_order="alternate")
    a, b = next((a, b) for a, b in zip(sliced.rings[:-1], sliced.rings[1:], strict=True) if b.layer > a.layer)
    assert a.link_next and Point(a.points[-1, :2]).distance(Point(b.points[0, :2])) <= 1e-9
    # mit link_max_mm = 0 sind auch Musterverbinder aus (jeder Ring ein eigener Strang)
    off = slice_part(_box(600.0, 200.0, 20.0), replace(SliceParams(layer_order="alternate"), link_max_mm=0.0))
    assert not any(r.link_next for r in off.rings)


# --------------------------------------------------------------------------- Gegenprüfung M3.1


def _window_wall():
    """1200 x 200 x 200 mit Öffnung x -200..200, z 60..150: Schichten 6..14 haben zwei Inseln."""
    import trimesh

    hole = trimesh.creation.box(extents=[400.0, 400.0, 90.0])
    hole.apply_translation([0.0, 0.0, 105.0])
    return _box(1200.0, 200.0, 200.0).difference(hole)


def test_layer_order_unset_means_alternate_with_pattern() -> None:
    """Ohne `layer_order` gilt mit Muster die Schichtfolge des Kerns bzw. Presets (alternate, M4);
    `same` allein ist die heutige Folge und kein Muster."""
    assert SliceParams().layer_order == "" and PlannerParams().layer_order == ""
    assert not uses_pattern(SliceParams(layer_order="same"))
    assert not PlannerParams(layer_order="same").uses_pattern
    assert "layer_order" not in PlannerParams(outfill_pattern="fugenwand").as_summary()
    sliced = _slice(outfill_pattern="fugenwand")
    assert sliced.pattern["layer_order"] == "alternate"
    _check_strand(sliced, 6)
    with pytest.raises(ValueError):
        PlannerParams(layer_order="zickzack")
    with pytest.raises(ValueError):
        uses_pattern(SliceParams(layer_order="Alternate"))


@pytest.mark.skipif("sinus" not in patterns.names(), reason="Familie Wellen noch nicht gemergt")
def test_infill_without_layer_order_is_vertical() -> None:
    """Vorher: infill_pattern allein ergab `same`, Schichtwechsel diagonal 504 mm und ohne Verbinder."""
    sliced = _slice(infill_pattern="sinus")
    assert sliced.pattern["layer_order"] == "alternate"
    _check_strand(sliced, 6)
    _check_closed_flags(sliced)


def test_explicit_same_overrides_preset() -> None:
    assert pattern_params(SliceParams(pattern_preset=FUGENWAND)).layer_order == "alternate"
    assert pattern_params(SliceParams(pattern_preset=FUGENWAND, layer_order="same")).layer_order == "same"
    assert pattern_params(SliceParams(shells=1, outfill_pattern="none", pattern_params="{}",
                                      layer_order="alternate")).layer_order == "alternate"


def test_drl_header_shows_resolved_pattern() -> None:
    """Mit Preset steht im Programmkopf das aufgelöste Muster, nicht die Standardwerte."""
    from types import SimpleNamespace

    from roboprint.contracts import ToolpathPattern

    info = ToolpathPattern(layer_order="alternate", infill="none", outfill="fugenwand")
    part = SimpleNamespace(part_id="P", wall_id="W", status="machbar")
    run_params = {"pattern_preset": "f.json", "pattern_params": "{}"}
    pp = SimpleNamespace(params=drl.DrlParams(), provenance=None, scenario_id="S", part=part,
                         toolpath=SimpleNamespace(rings=[], pattern=info),
                         trajectory=SimpleNamespace(t_s=[0.0]), run_params=run_params)
    txt = "\n".join(drl._header(pp, "v2", []))
    assert "A Schichtfolge              alternate (Druckmuster, opt-in)" in txt
    assert "A Muster                    Infill none, Outfill fugenwand" in txt
    assert "A Musterparameter           {}" in txt


@pytest.mark.parametrize("kw", [{"layer_order": "alternate"}, {"pattern_preset": FUGENWAND}])
def test_opening_links_never_cross_opening(kw: dict) -> None:
    """Teil mit Öffnung (Inselwechsel): jeder Verbinder liegt im Querschnitt beider Schichten
    (unabhängig nachgerechnet, ± 1 mm), Schichtwechsel senkrecht außer beim Wechsel der Inselzahl,
    `kind` und `closed` stimmen, der Vertrag nimmt den Toolpath an."""
    from shapely.geometry import LineString, MultiPolygon, Polygon

    mesh = _window_wall()
    sliced = slice_part(mesh, SliceParams(**kw))
    sections, islands = {}, {}
    for L in range(sliced.n_layers):
        sec = mesh.section(plane_origin=[0, 0, (L + 0.5) * 10.0], plane_normal=[0, 0, 1])
        planar, _ = sec.to_2D(to_2D=np.eye(4))
        polys = [Polygon(p.exterior, p.interiors) for p in planar.polygons_full]
        sections[L], islands[L] = MultiPolygon(polys).buffer(0), len(polys)
    assert islands[5] == 1 and islands[6] == 2 and islands[14] == 2 and islands[15] == 1
    allowed = {"outer", "inner", "hole", "infill", "web", "outfill"}
    assert {r.kind for r in sliced.rings} <= allowed
    _check_closed_flags(sliced)
    for a, b in zip(sliced.rings[:-1], sliced.rings[1:], strict=True):
        pa, pb = a.points[-1, :2], b.points[0, :2]
        gap = float(np.linalg.norm(pb - pa))
        if a.link_next:
            geom = LineString([pa, pb]) if gap > 1e-9 else Point(pa)
            for L in {a.layer, b.layer}:
                assert sections[L].buffer(1.0).covers(geom), (a.layer, b.layer, gap)
        if b.layer == a.layer + 1 and islands[a.layer] == islands[b.layer]:
            assert gap <= 0.5 and a.link_next, f"Schichtwechsel {a.layer}->{b.layer}: {gap:.1f} mm"
        if b.layer == a.layer and gap > 1e-6:  # Inselwechsel in der Schicht: Travel, nie Verbinder
            assert islands[a.layer] == 2 and not a.link_next
    Toolpath.model_validate(to_toolpath(sliced, np.eye(4), "w").model_dump(mode="json"))


@pytest.mark.parametrize("T,pat", [(200.0, "doppelwelle"), (200.0, "waben"), (150.0, "sinus")])
def test_dropped_infill_reason_reaches_toolpath_and_report(T: float, pat: str) -> None:
    """Entfällt das gewählte Infill wegen der Geometrie, nennen Toolpath und Teilbericht den Grund
    (vorher: toolpath.pattern.infill = Muster, Ringe nur Schalen, kein Hinweis)."""
    from roboprint import pattern_report

    box = make_box([600.0, T, 30.0], origin=[-300.0, -T / 2, 0.0])
    tp = to_toolpath(slice_part(box, SliceParams(infill_pattern=pat, layer_order="alternate")), np.eye(4), "b")
    d = tp.model_dump(mode="json")
    assert "infill" not in {r["kind"] for r in d["rings"]}
    notes = d["pattern"]["notes"]
    assert notes and all("Infill entfällt" in n for n in notes), notes
    assert pattern_report.metrics(d, 100.0)["notes"] == notes


def test_preview_lists_dropped_infill_as_note() -> None:
    from roboprint.patterns import preview

    d = preview({"pattern": "doppelwelle", "params": {}}, (600, 200))
    assert d["ok"] and d["notes"] and d["notes"][0].startswith("Infill entfällt")


def test_toolpath_without_notes_has_no_notes_key() -> None:
    """Ohne Hinweis bleibt toolpath.json wie bisher (kein leeres `notes`)."""
    box = make_box([600.0, 200.0, 30.0], origin=[-300.0, -100.0, 0.0])
    d = to_toolpath(slice_part(box, SliceParams(layer_order="alternate")), np.eye(4), "b").model_dump(
        mode="json", exclude_none=True
    )
    assert "notes" not in d["pattern"]

"""Slicer v0: Schnitte, Schalen, Toolpath-Bau — synthetische Meshes."""

import math

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon, box

from fgc import domain
from fgc.domain.process_params import PROVISIONAL_DEFAULTS, ProcessWindow, SliceParams
from fgc.pipeline.provenance import make_provenance
from fgc.slicer import section_layers, shell_rings, slice_wall

PARAMS = SliceParams(strand_width_mm=30.0, layer_height_mm=100.0, n_shells=2)


def wall_mesh(length=2000.0, thickness=200.0, height=1000.0) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=[length, thickness, height])
    mesh.apply_translation([0, 0, height / 2])
    return mesh


def test_section_layer_count_and_heights():
    layers = section_layers(wall_mesh(height=1000.0), layer_height_mm=100.0)
    assert len(layers) == 10
    assert layers[0].z_mm == pytest.approx(50.0)
    assert layers[-1].z_mm == pytest.approx(950.0)
    assert all(len(layer.polygons) == 1 for layer in layers)


def test_disjoint_cross_sections_yield_multiple_polygons():
    """S2-Befund: eine Schnittebene kann mehrere getrennte Konturen treffen."""
    a = wall_mesh(length=800.0)
    b = wall_mesh(length=800.0)
    b.apply_translation([1500.0, 0, 0])
    layers = section_layers(trimesh.util.concatenate([a, b]), layer_height_mm=100.0)
    assert all(len(layer.polygons) == 2 for layer in layers)


def test_shell_rings_inset_and_closed():
    poly = Polygon([(0, 0), (2000, 0), (2000, 200), (0, 200)])
    rings = shell_rings(poly, strand_width_mm=30.0, n_shells=2)
    assert {r.shell for r in rings} == {0, 1}
    for ring in rings:
        assert ring.points_xy[0] == ring.points_xy[-1]  # geschlossen
    shell0 = next(r for r in rings if r.shell == 0)
    ys = [y for _, y in shell0.points_xy]
    assert min(ys) == pytest.approx(15.0)  # halbe Strangbreite innen
    assert max(ys) == pytest.approx(185.0)


def test_shells_stop_when_contour_vanishes():
    """Schmale Kontur: zweite Schale hat keinen Platz mehr -> keine Geister-Ringe."""
    poly = Polygon([(0, 0), (2000, 0), (2000, 80), (0, 80)])  # 80 mm dick
    rings = shell_rings(poly, strand_width_mm=30.0, n_shells=3)
    assert {r.shell for r in rings} == {0}


def _notch_polygon(angle_deg: float, w: float, leg_length_w=25.0, wall_span_w=15.0) -> Polygon:
    """Materialblock mit scharfer konkaver Reflex-Kerbe (V-Kerbe von unten).

    Nachbau der `notch`-Familie aus Spike S4 (docs/spikes/s4_scripts/contours.py),
    hier direkt in mm statt normierten Strangbreiten w=1.0.
    """
    leg_length = leg_length_w * w
    wall_span = wall_span_w * w
    big = box(-leg_length, -wall_span, leg_length, wall_span)
    half = math.radians(angle_deg) / 2.0
    depth = wall_span * 1.5
    apex = (0.0, 0.0)
    p1 = (-depth * math.sin(half), -depth * math.cos(half))
    p2 = (depth * math.sin(half), -depth * math.cos(half))
    cut_wedge = Polygon([apex, p2, p1])
    return big.difference(cut_wedge)


def test_shell_rings_survive_sharp_reflex_notch():
    """S4-Regressionstest (docs/spikes/S4_offset_robustheit.md, notch-Familie).

    Scharfe konkave Reflex-Kerbe (Kerbwinkel 15°): mit shapely-Default
    mitre_limit=5 loest sich die Mitre-Spitze ab Schale k=2 als eigene
    Teilflaeche ab (MultiPolygon-Zerfall) -- mit dem Produktionswert
    mitre_limit=2.0 bleibt jede Schale eine einzelne, geschlossene Kontur.
    """
    w = PARAMS.strand_width_mm
    poly = _notch_polygon(angle_deg=15.0, w=w)
    n_shells = 3  # Schalen k=0,1,2 -> Inset bis 2.5*w

    # Kontroll-Assertion: der shapely-Default (mitre_limit=5, hier explizit
    # nachgestellt) zerfaellt bei der dritten Schale (k=2) tatsaechlich in ein
    # MultiPolygon -- sonst waere dieser Test kein echter Regressionstest.
    inset_k2 = w * (0.5 + 2)
    shrunk_default = poly.buffer(-inset_k2, join_style="mitre")
    assert shrunk_default.geom_type == "MultiPolygon"

    rings = shell_rings(poly, strand_width_mm=w, n_shells=n_shells)
    rings_per_shell: dict[int, int] = {}
    for ring in rings:
        rings_per_shell[ring.shell] = rings_per_shell.get(ring.shell, 0) + 1
    assert set(rings_per_shell) == {0, 1, 2}
    assert all(count == 1 for count in rings_per_shell.values())  # kein Zerfall


def test_mitre_limit_sourced_from_process_window_card():
    """Issue #2: ``mitre_limit`` ist eine Quelle für E1 und Slicer (ADR-013).

    Kartenwert (``materialcards/process_window.provisional.json``) und
    Code-Default (``PROVISIONAL_DEFAULTS``) müssen übereinstimmen, und
    ``SliceParams.from_window`` muss den Kartenwert übernehmen -- sonst könnten
    Slicer und ``fgc.eligibility.footprint.has_narrow_web`` mit
    unterschiedlichen mitre_limit-Werten laufen, obwohl beide dieselbe Karte
    lesen sollen.
    """
    window = ProcessWindow.load()
    assert window.mitre_limit == PROVISIONAL_DEFAULTS["mitre_limit"] == 2.0
    params = SliceParams.from_window(window)
    assert params.mitre_limit == window.mitre_limit


def test_slice_wall_toolpath_is_schema_valid():
    mesh = wall_mesh()
    toolpath = slice_wall(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), "TESTWALL00000000000000", PARAMS
    )
    artifact = toolpath.to_artifact(make_provenance("pytest"))
    domain.validate(artifact, "toolpath")


def test_slice_wall_segments_start_with_travel():
    mesh = wall_mesh()
    toolpath = slice_wall(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), "TESTWALL00000000000000", PARAMS
    )
    assert toolpath.targets[0].kind == "travel"
    by_segment: dict[str, list] = {}
    for t in toolpath.targets:
        by_segment.setdefault(t.segment_id.removesuffix("_approach"), []).append(t)
    for targets in by_segment.values():
        kinds = [t.kind for t in targets]
        assert kinds[0] == "travel"
        assert set(kinds[1:]) == {"print"}
    # Travel-Targets fahren mit Pumpen aus
    assert all(
        all(v == 0.0 for v in t.io.values()) for t in toolpath.targets if t.kind == "travel"
    )


def test_slice_wall_layers_ascend():
    mesh = wall_mesh()
    toolpath = slice_wall(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), "TESTWALL00000000000000", PARAMS
    )
    zs = [t.frame.pos_mm[2] for t in toolpath.targets]
    assert zs == sorted(zs)
    assert max(t.layer for t in toolpath.targets) == 9


def test_targets_carry_shared_nozzle_down_orientation():
    """Alle Slicer-Ziele tragen die kanonische Druck-Orientierung (Düse nach
    unten), und zwar dieselbe Konstante, aus der `fgc.placement` seine
    Anfluggeometrie ableitet (Issue #51). Ohne diese Kopplung galt eine Wand im
    Druckplan als erreichbar, in der Simulation aber nicht (Identitäts-Ziele)."""
    import numpy as np

    from fgc.domain.orientation import NOZZLE_DOWN_QUAT
    from fgc.kinematics.opw import _quat_to_rot
    from fgc.placement.evaluate import _R_NOZZLE_DOWN

    mesh = wall_mesh()
    toolpath = slice_wall(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), "TESTWALL00000000000000", PARAMS
    )
    assert toolpath.targets
    # Slicer bäckt die Orientierung in jedes Ziel (Travel + Print).
    assert all(t.frame.quat == NOZZLE_DOWN_QUAT for t in toolpath.targets)
    # Platzierung leitet ihre Rotationsmatrix aus derselben Konstante ab → kein Drift.
    np.testing.assert_allclose(_R_NOZZLE_DOWN, _quat_to_rot(NOZZLE_DOWN_QUAT))
    np.testing.assert_allclose(
        _R_NOZZLE_DOWN, np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])
    )


def test_slicer_bakes_nozzle_quat_with_real_ring_tangent():
    """Mit gesetztem Kipp fuellt der Slicer frame.quat je Ziel ueber die geteilte
    ``nozzle_quat`` mit der echten Bahntangente (aufeinanderfolgende Ringpunkte) —
    keine konstante Orientierung mehr, aber dieselbe Funktion wie ``placement``
    (Issue #61, Regressionsschutz #51)."""
    from fgc.domain.orientation import NOZZLE_DOWN_QUAT, nozzle_quat

    params = SliceParams(
        strand_width_mm=30.0, layer_height_mm=100.0, n_shells=1,
        lead_rad=math.radians(10), kipp_rad=math.radians(25),
    )
    toolpath = slice_wall(
        np.asarray(wall_mesh().vertices), np.asarray(wall_mesh().faces),
        "TESTWALL00000000000000", params,
    )
    prints = [t for t in toolpath.targets if t.kind == "print"]
    assert prints
    # Angestellt ⇒ keine reine Senkrechte mehr.
    assert any(t.frame.quat != NOZZLE_DOWN_QUAT for t in prints)
    # Je Print-Ziel entspricht die Orientierung nozzle_quat der Tangente aus dem
    # vorangehenden Ringpunkt desselben Segments — exakt die geteilte Funktion.
    by_seg: dict[str, list] = {}
    for t in prints:
        by_seg.setdefault(t.segment_id, []).append(t)
    checked = 0
    for seg_targets in by_seg.values():
        for prev, cur in zip(seg_targets, seg_targets[1:], strict=False):
            tangent = (
                cur.frame.pos_mm[0] - prev.frame.pos_mm[0],
                cur.frame.pos_mm[1] - prev.frame.pos_mm[1],
            )
            if math.hypot(*tangent) < 1e-6:
                continue
            expected = nozzle_quat(tangent, params.lead_rad, params.kipp_rad)
            np.testing.assert_allclose(cur.frame.quat, expected, atol=1e-6)
            checked += 1
    assert checked > 0


def test_placement_shares_nozzle_quat_with_slicer():
    """``placement`` leitet seine Anflug-Rotation aus derselben ``nozzle_quat`` ab
    wie der Slicer — nur mit seiner angenommenen horizontalen Tangente. Gleiche
    Konvention/Tangentenannahme ⇒ keine Divergenz (Regressionsschutz #51)."""
    from fgc.domain.orientation import nozzle_quat
    from fgc.kinematics.opw import _quat_to_rot
    from fgc.placement.evaluate import _PLACEMENT_TANGENT, nozzle_rotation

    lead, kipp = math.radians(10), math.radians(25)
    np.testing.assert_allclose(
        nozzle_rotation(lead, kipp),
        _quat_to_rot(nozzle_quat(_PLACEMENT_TANGENT, lead, kipp)),
        atol=1e-12,
    )

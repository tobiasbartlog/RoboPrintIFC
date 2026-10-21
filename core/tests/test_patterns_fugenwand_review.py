"""Gegenprüfung Fugenwand: unabhängige Geometrieprüfung ohne `patterns/metrics.py`.

Die Prüfungen rechnen direkt auf der Mittellinie (shapely/numpy): einfache Kurve, Mindestabstand
bei Bogenlängenabstand > 2·w (M2), Umkreisradius (M6), Raupe im Teil ⊕ 1 mm (M5), Überhang der
Folgeschicht = 0 (M3), senkrechter Wechsel (M4), Einteilung bei krummen Modullängen, und dass die
deklarierten Kontakte wirklich Berührungen im Band [(1 − ε)·w, w] sind.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree
from shapely.geometry import LineString, box

from roboprint import patterns as pt
from roboprint.patterns.preview import params_for

DOC_PRESETS = Path(__file__).resolve().parents[2] / "docs" / "muster" / "presets"

VARIANTS = {
    "a_gurt_gespiegelt": {"belt": True, "back_offset": "gespiegelt"},
    "b_raute": {"belt": False, "back_offset": "versetzt"},
    "c_gurt_versetzt": {"belt": True, "back_offset": "versetzt"},
}


def _densify(p: np.ndarray, step: float) -> np.ndarray:
    out = [p[:1]]
    for a, b in zip(p[:-1], p[1:], strict=True):
        n = max(1, math.ceil(float(np.linalg.norm(b - a)) / step))
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.vstack(out)


def _arc(d: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(d, axis=0), axis=1))])


def _far_pairs(d: np.ndarray, radius: float, w: float) -> tuple[np.ndarray, np.ndarray]:
    """Punktpaare näher als `radius`, die entlang des geschlossenen Zugs > 2·w auseinanderliegen."""
    s = _arc(d)
    tot = s[-1]
    pr = cKDTree(d).query_pairs(radius, output_type="ndarray")
    if len(pr) == 0:
        return pr, np.zeros(0)
    sep = np.abs(s[pr[:, 1]] - s[pr[:, 0]])
    sep = np.minimum(sep, tot - sep)
    far = pr[sep > 2 * w]
    return far, np.linalg.norm(d[far[:, 0]] - d[far[:, 1]], axis=1)


def _min_circumradius(p: np.ndarray) -> float:
    a, b, c = p[:-2], p[1:-1], p[2:]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    cr = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2 * cr)
    return float(np.nanmin(r))


def _plan(length, thickness, layers=3, **kw):
    g = box(-length / 2, -thickness / 2, length / 2, thickness / 2)
    p = params_for("fugenwand", **kw)
    return g, p, pt.plan_pattern({i: g for i in range(layers)}, p)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("thickness", [200.0, 300.0, 365.0])
@pytest.mark.parametrize("length", [730.0, 1170.0])
def test_independent_geometry_odd_lengths(variant, thickness, length):
    g, p, paths = _plan(length, thickness, **VARIANTS[variant])
    w, eps = p.w, p.eps
    assert len(paths) == 3
    lp = paths[0]
    assert "pattern_fallback" not in lp.meta
    P = np.asarray(lp.polyline())
    assert np.allclose(P[0], P[-1])  # geschlossen
    assert LineString(P).is_simple  # M2: keine (verdeckte) Kreuzung
    _, dist = _far_pairs(_densify(P, 1.0), w + 0.5, w)
    assert dist.size and dist.min() >= (1 - eps) * w - 1e-6  # M2: kein Doppelmaterial
    assert _min_circumradius(P[:-1]) >= w / 2 - 0.5  # M6 hart
    assert g.buffer(1.0).contains(LineString(P).buffer(w / 2))  # M5
    for a, b in zip(paths[:-1], paths[1:], strict=True):
        pa, pb = np.asarray(a.polyline()), np.asarray(b.polyline())
        assert np.linalg.norm(pa[-1] - pb[0]) <= 0.5  # M4 senkrecht
        assert pa.shape == pb.shape and np.allclose(pa[::-1], pb)  # alternate: exakte Umkehrung
        over = LineString(pb).buffer(w / 2).difference(LineString(pa).buffer(w / 2 + p.delta_mm))
        assert over.area < 1e-3  # M3: kein Überhang
    # Einteilung: ganze Zahl gleich langer Felder, Fugen im Abstand F, Summe = Modullänge
    m = lp.meta
    n, F = m["fit"]["count"], m["field_length_mm"]
    assert n * F == pytest.approx(length)
    xs = [g.bounds[0], *m["joints_front_x"], g.bounds[2]]
    assert np.allclose(np.diff(xs), F)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("thickness", [200.0, 300.0])
def test_declared_contacts_touch(variant, thickness):
    """Jeder deklarierte Kontakt (Fuge, Knoten, Spitze) ist eine echte Berührung zweier Zugstücke,
    die entlang des Pfads > 2·w auseinanderliegen, mit Abstand in [(1 − ε)·w, w]."""
    g, p, paths = _plan(730.0, thickness, layers=1, **VARIANTS[variant])
    lp = paths[0]
    d = _densify(np.asarray(lp.polyline()), 0.5)
    far, dist = _far_pairs(d, p.w + 0.5, p.w)
    assert lp.contacts
    for c in lp.contacts:
        q = np.asarray(c.at)
        near = np.linalg.norm(d[far[:, 0]] - q, axis=1) < p.w
        assert near.any(), (c.kind, c.at)
        best = float(dist[near].min())
        assert (1 - p.eps) * p.w - 1e-6 <= best <= p.w + 0.5, (c.kind, c.at, best)


def test_foto_preset_shows_slanted_webs():
    """Das Preset „wie Foto“ zeigt in seiner eigenen Vorschau V-Stege, keinen Mäander."""
    data = pt.preview(pt.load_preset(DOC_PRESETS / "fugenwand_foto.json"))
    assert data["ok"]
    assert max(data["paths"][0]["meta"]["web_angle_deg"]) >= 20.0


def test_mirrored_without_belt_note_points_to_variant_a():
    _, _, paths = _plan(600.0, 300.0, layers=1, belt=False, back_offset="gespiegelt")
    assert "Variante a" in paths[0].meta["note"]


@pytest.mark.parametrize(("w", "overlap"), [(25.0, 4.5), (20.0, 3.5), (25.0, 3.75)])
def test_contact_overlap_clamped_to_eps_w(w, overlap):
    """Gegenprüfung M6 (Runde 2): Der Regler reicht bis 4,5 mm (= ε·30). Bei w < 30 wird die
    Überlappung auf ε·w begrenzt (Hinweis in `adjusted`), jeder Reglerwert bleibt M2-frei."""
    data = pt.preview(
        {"pattern": "fugenwand", "params": {"bead_width_mm": w, "contact_overlap_mm": overlap}},
        {"length_mm": 600, "thickness_mm": 250},
    )
    assert data["ok"], [v for v in data["violations"] if v["severity"] == "error"]
    meta = data["paths"][0]["meta"]
    assert meta["contact_distance_mm"] >= (1 - 0.15) * w - 1e-6
    if overlap > 0.15 * w + 1e-9:
        assert "ε·w" in meta["adjusted"]

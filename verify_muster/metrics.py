"""M7 (Kontakt, berichtet) und Kennzahlen je Schicht.

- Kontaktzonen kommen aus der Paaranalyse (verify_muster/contacts.py). Je Meter Wand heisst: Zonen je
  Schicht im Mittel geteilt durch die Wandlaenge, die laengste Kante des Grundrisses von part.stl in P.
- Laengste gerade, ungestuetzte Aussenstrecke: Punkte der Arten `outer`/`outfill` im Abstand 5 mm;
  gestuetzt ist ein Punkt, an dem ein Infill-/Stegpunkt (`infill`, `web`) mit Mittellinienabstand
  <= w + CONTACT_TOL_MM liegt. Ein Abschnitt waechst, solange alle Punkte hoechstens 1 mm (A) neben
  der Sehne liegen und keiner gestuetzt ist. Eine Fuge beendet ein Feld ohnehin, weil die Bahn dort
  umkehrt.
- Fugenabstand: Mittelpunkte der Kontaktzonen `joint` je Schicht, je Wandseite (Vorzeichen der
  Querkoordinate zum Schwerpunkt der Raupenflaeche) entlang der Wandachse sortiert; berichtet werden
  die Abstaende benachbarter Fugen (min, max, Mittel ueber alle Schichten).
- Pfadlaenge je Schicht: Summe der Schichtpfade inklusive Verbinder in der Schicht.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from verify_muster import geometry as g
from verify_muster.contacts import CONTACT_TOL_MM, FILL_KINDS
from verify_muster.rules import EPS, Ctx, Rule

STRAIGHT_TOL_MM = 1.0  # (A) "gerade": Punkte <= 1 mm neben der Sehne
OUTER_KINDS = ("outer", "outfill")


def _kind_mask(P: g.LayerPath, kinds) -> np.ndarray:
    ks = np.array([e.kind for e in P.elements], dtype=object)
    return np.isin(ks[P.elem].astype(str), kinds) if len(P.elem) else np.zeros(0, bool)


def _wall_axes(C: Ctx) -> tuple[np.ndarray, np.ndarray, float]:
    """Wandachse (Einheitsvektor der laengsten Grundrisskante), Querachse und Wandlaenge in m."""
    b = C.part.mesh.bounds
    ex, ey = float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1])
    if ex >= ey:
        return np.array([1.0, 0.0]), np.array([0.0, 1.0]), max(ex, 1e-9) / 1000.0
    return np.array([0.0, 1.0]), np.array([1.0, 0.0]), max(ey, 1e-9) / 1000.0


def _joint_spacings(zones: list, axis: np.ndarray, across: np.ndarray, center: np.ndarray) -> list[float]:
    pts = np.array([z["point_P"] for z in zones if z["type"] == "joint"], float).reshape(-1, 2)
    out: list[float] = []
    if len(pts) < 2:
        return out
    side = np.sign((pts - center) @ across)
    for sgn in (-1.0, 1.0):
        u = np.sort((pts[side == sgn] - center) @ axis)
        out.extend(np.diff(u).tolist())
    return [x for x in out if x > 1e-6]


def check_m7_and_metrics(C: Ctx) -> tuple[Rule, dict]:
    R = Rule("M7", "Kontakt: Kontaktzonen (Fuge, Knoten, Schale) mit Ueberlappung 0 … eps·w, berichtet",
             False)
    axis, across, wall_m = _wall_axes(C)
    per_layer = []
    zones_all, len_all, spacings = [], [], []
    by_type_total = {"joint": 0, "node": 0, "shell": 0}
    first_zones = None
    for L in C.layers:
        paths = C.paths.get(L, [])
        zones = [z for res in C.pairs.get(L, []) for z in res.zones]
        if first_zones is None and zones:
            first_zones = zones
        by_type = {"joint": 0, "node": 0, "shell": 0}
        for z in zones:
            by_type[z["type"]] += 1
            by_type_total[z["type"]] += 1
        z_len = float(sum(z["length_mm"] for z in zones))
        R.n_checked += 1
        zones_all.append(len(zones))
        len_all.append(z_len)
        fill = [P.pts[_kind_mask(P, FILL_KINDS)] for P in paths]
        fill_pts = np.vstack(fill) if fill else np.zeros((0, 2))
        all_pts = np.vstack([P.pts for P in paths]) if paths else np.zeros((0, 2))
        center = all_pts.mean(axis=0) if len(all_pts) else np.zeros(2)
        sp = _joint_spacings(zones, axis, across, center)
        spacings.extend(sp)
        per_layer.append({
            "layer": L, "n_islands": len(C.islands[L]), "n_paths": len(paths),
            "path_length_mm": round(sum(P.length for P in paths), 2),
            "contact_zones": len(zones), "contact_zones_by_type": by_type,
            "contact_length_mm": round(z_len, 1),
            "joint_spacing_mm": [round(x, 1) for x in sp],
            "longest_straight_unsupported_outer_mm": _longest_straight_outer(C, paths, fill_pts)})
    n_l = max(len(C.layers), 1)
    R.metrics.update(
        wall_length_m=round(wall_m, 4),
        contact_zones_per_m=round(float(np.mean(zones_all)) / wall_m, 3) if zones_all else None,
        contact_length_mm_per_m=round(float(np.mean(len_all)) / wall_m, 2) if len_all else None,
        contact_zones_per_m_by_type={k: round(v / n_l / wall_m, 3) for k, v in by_type_total.items()},
        contact_band_mm=[round((1.0 - EPS) * C.w, 2), round(C.w + CONTACT_TOL_MM, 2)],
        zones_first_layer=first_zones[:50] if first_zones else [])
    if not any(zones_all):
        R.note = "keine Kontaktzonen"
    longest = [x["longest_straight_unsupported_outer_mm"] for x in per_layer
               if x["longest_straight_unsupported_outer_mm"] is not None]
    lengths = [x["path_length_mm"] for x in per_layer]
    metrics = {
        "layers": per_layer,
        "longest_straight_unsupported_outer_mm": max(longest) if longest else None,
        "joint_spacing_mm": None if not spacings else {
            "min": round(min(spacings), 1), "max": round(max(spacings), 1),
            "mean": round(float(np.mean(spacings)), 1)},
        "path_length_mm_per_layer": {"min": round(min(lengths), 2), "max": round(max(lengths), 2),
                                     "mean": round(float(np.mean(lengths)), 2)} if lengths else None,
        "path_length_mm_total": round(float(np.sum(lengths)), 2) if lengths else None,
        "n_layers": len(C.layers)}
    return R, metrics


def _longest_straight_outer(C: Ctx, paths, fill_pts: np.ndarray) -> float | None:
    tree = cKDTree(fill_pts) if len(fill_pts) else None
    best = None
    for P in paths:
        for e, el in enumerate(P.elements):
            if el.kind not in OUTER_KINDS:
                continue
            sel = np.flatnonzero(P.elem == e)
            if len(sel) < 2:
                continue
            pts, s = g.resample(P.pts[sel], 5.0)
            sup = np.zeros(len(pts), bool)
            if tree is not None:
                d, _ = tree.query(pts)
                sup = d <= C.w + CONTACT_TOL_MM
            runs = g.straight_runs(pts, s, sup, STRAIGHT_TOL_MM)
            if runs:
                m = max(r[0] for r in runs)
                best = m if best is None else max(best, m)
    return None if best is None else round(best, 1)

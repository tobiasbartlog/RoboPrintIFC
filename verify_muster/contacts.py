"""Paaranalyse eines Schichtpfads: Kreuzungen und zu tiefe Kontakte (M2) sowie Kontaktzonen (M2, M7).

Grundlage ist die dichte Abtastung des Schichtpfads (Schritt <= 2 mm, Verbinder enthalten) und der
Bogenlaengenabstand `graph_distance` (geschlossene Ringe und geschlossene Zuege zyklisch). Fuer alle
Punktpaare mit Bogenlaengenabstand > 2·w gilt:

- Abstand < (1 - eps)·w: Verletzung von M2. Ist der Abstand kleiner als 1,5 Abtastschritte, kreuzt
  sich die Mittellinie (`crossing`), sonst ist der Kontakt zu tief bzw. ein Pfadstueck faehrt ueber eine
  schon gelegte Raupe derselben Schicht (`too_deep`).
- Abstand in [(1 - eps)·w, w + CONTACT_TOL_MM]: gewollter Kontakt. Zusammenhaengende Laeufe solcher
  Punkte entlang des Pfads werden paarweise zu **Kontaktzonen** zusammengefasst (ARTEFAKT-FORMAT,
  Nachtrag 18:45): Lage (Mittelpunkt in P), Laenge (Mittel der beiden Seiten), Art
  - `joint`: eine Seite ist `outfill` und die andere `outfill` oder `web` (Fuge der Fugenwand),
  - `node`: beide Seiten `web`/`infill` (Knoten, Gurt an Gurt),
  - `shell`: alles andere, also Infill/Steg an Schale und Schale an Schale.
  Verbinder (`link`) zaehlen mit der Art des folgenden Rings.

Die Obergrenze w + CONTACT_TOL_MM (A, 0,5 mm) nimmt den erlaubten Sehnenfehler (M6, 0,5 mm) auf: Ein
Kontakt, der in der Sollkurve genau bei w liegt, darf in der Polylinie bis zu 0,5 mm weiter liegen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from verify_muster import geometry as g

CONTACT_TOL_MM = 0.5  # (A) Obergrenze Kontakt: Mittellinienabstand <= w + 0,5 mm
SHELL_KINDS = ("outer", "inner", "hole")
FILL_KINDS = ("infill", "web")


@dataclass
class PairResult:
    """Ergebnis der Paaranalyse eines Schichtpfads."""

    thr: float
    viol_i: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    viol_j: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    viol_d: np.ndarray = field(default_factory=lambda: np.zeros(0))
    viol_gd: np.ndarray = field(default_factory=lambda: np.zeros(0))
    zones: list = field(default_factory=list)


def point_kinds(P: g.LayerPath, ring_kind: dict[int, str]) -> np.ndarray:
    """Segmentart je dichtem Punkt; Verbinder tragen die Art des folgenden Rings."""
    ks = []
    for e in P.elements:
        ks.append(e.kind if e.ring >= 0 else ring_kind.get(e.link_to, "link"))
    return np.array(ks, dtype=object)[P.elem] if len(P.elem) else np.zeros(0, dtype=object)


def contact_type(ka: str, kb: str) -> str:
    s = {ka, kb}
    if "outfill" in s and s <= {"outfill", "web"}:
        return "joint"
    if s <= set(FILL_KINDS):
        return "node"
    return "shell"


def _runs(mask: np.ndarray, cyclic: bool, breaks: np.ndarray | None = None) -> list[np.ndarray]:
    """Zusammenhaengende Indexlaeufe mit mask = True (bei cyclic ueber das Ende hinweg verbunden).
    breaks[k] = True trennt die Punkte k und k + 1 (Grenze zu einem Verbinder mit Laenge > 1 mm)."""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    gap = np.diff(idx) > 1
    if breaks is not None:
        gap |= breaks[idx[:-1]]
    cuts = np.flatnonzero(gap) + 1
    runs = np.split(idx, cuts)
    if cyclic and len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == len(mask) - 1:
        runs[0] = np.concatenate([runs[-1], runs[0]])
        runs.pop()
    return runs


def _majority(values) -> str:
    vals, cnt = np.unique(np.asarray(values, dtype=str), return_counts=True)
    return str(vals[int(np.argmax(cnt))])


def analyse(P: g.LayerPath, w: float, eps: float, ring_kind: dict[int, str]) -> PairResult:
    """Paaranalyse nach dem Modul-Docstring."""
    thr = (1.0 - eps) * w
    hi = w + CONTACT_TOL_MM
    res = PairResult(thr)
    if len(P.pts) < 2:
        return res
    pairs = cKDTree(P.pts).query_pairs(r=hi, output_type="ndarray")
    if len(pairs) == 0:
        return res
    i, j = pairs[:, 0], pairs[:, 1]
    d = np.linalg.norm(P.pts[i] - P.pts[j], axis=1)
    gd = g.graph_distance(P, i, j)
    far = gd > 2.0 * w
    v = far & (d < thr)
    res.viol_i, res.viol_j, res.viol_d, res.viol_gd = i[v], j[v], d[v], gd[v]
    c = far & (d >= thr) & (d <= hi)
    if not c.any():
        return res
    ci, cj = i[c], j[c]
    n = len(P.pts)
    mask = np.zeros(n, bool)
    mask[ci] = True
    mask[cj] = True
    long_link = np.array([e.ring < 0 and P.e_len[k] > 1.0 for k, e in enumerate(P.elements)])
    breaks = np.zeros(n, bool)
    breaks[:-1] = (P.elem[1:] != P.elem[:-1]) & (long_link[P.elem[1:]] | long_link[P.elem[:-1]])
    runs = _runs(mask, P.cyclic, breaks)
    run_of = np.full(n, -1)
    for k, r in enumerate(runs):
        run_of[r] = k
    kinds = point_kinds(P, ring_kind)
    # Partner je Lauf: Lauf a beruehrt Lauf b, wenn ein Kontaktpaar zwischen ihnen liegt
    ra, rb = run_of[ci], run_of[cj]
    keys = {}
    dmin_key: dict = {}
    for a, b, pi, pj, dk in zip(ra, rb, ci, cj, d[c], strict=True):
        key = (min(a, b), max(a, b))
        dmin_key[key] = min(dmin_key.get(key, np.inf), float(dk))
        side = keys.setdefault(key, ({}, {}))
        if a <= b:
            side[0][pi] = True
            side[1][pj] = True
        else:
            side[0][pj] = True
            side[1][pi] = True
    step = P.step
    for key, (sa, sb) in sorted(keys.items()):
        ia, ib = np.array(sorted(sa)), np.array(sorted(sb))

        def extent(ix: np.ndarray) -> float:
            """Laenge der Kontaktpunkte entlang des Pfads: Summe der Schritte zwischen direkt
            benachbarten Kontaktpunkten (robust gegen Naht und geschlossene Ringe)."""
            if len(ix) == 0:
                return 0.0
            adj = np.diff(ix) == 1
            return float(np.abs(np.diff(P.s[ix]))[adj].sum()) + step

        ka, kb = _majority(kinds[ia]), _majority(kinds[ib])
        mid = 0.5 * (P.pts[ia].mean(axis=0) + P.pts[ib].mean(axis=0))
        res.zones.append({
            "type": contact_type(ka, kb), "kinds": [ka, kb],
            "point_P": [round(float(x), 2) for x in mid],
            "length_mm": round(0.5 * (extent(ia) + extent(ib)), 1),
            "min_distance_mm": round(dmin_key[key], 2),
            "overlap_mm": round(max(0.0, w - dmin_key[key]), 2),
            "rings": sorted({int(P.ring_at(int(ia[0]))), int(P.ring_at(int(ib[0])))}),
        })
    return res

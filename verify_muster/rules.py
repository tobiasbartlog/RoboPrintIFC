"""Musterregeln M1-M7 (docs/muster/AUFTRAG.md) auf den Artefakten eines Teils.

Jede Regel liefert ein `Rule` mit pass/fail, Anzahl Verletzungen, erstem Gegenbeispiel (Schicht, Ring,
Punkt in P) und Kennzahlen. Methoden und Toleranzen: verify_muster/README.md. Konstanten mit (A) sind
Annahmen aus dem Auftrag bzw. vom Orakel gesetzt und gehoeren in den SPEC-Nachtrag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree

from verify_muster import geometry as g
from verify_muster.artifacts import Part

# ---------------------------------------------------------------- Konstanten
EPS = 0.15  # (A) Kontakt-/Abstandstoleranz relativ zu w (M2, M7)
DELTA_MM = 2.0  # (A) erlaubter Ueberstand der Raupenflaeche L+1 ueber L (M3)
M4_TOL_MM = 0.5  # (A) waagrechter Versatz Ende L -> Anfang L+1
M5_MARGIN_MM = 1.0  # (A) Raupenflaeche im Querschnitt ⊕ 1 mm
M5_TOL_MM = 0.05  # numerische Toleranz der Punktpruefung
Z_TOL_MM = 0.5  # Wegpunkthoehe gegen (L+1)·h (ARTEFAKTE)
M3_AREA_TOL_MM2 = 1.0  # numerische Restflaeche (Puffer-Polygone)
R_REL_TOL = 0.03  # (A) relative Toleranz der Fenster-Kruemmung (Sehnen der Eingabe)
FOLLOW_TOL_MM = 0.5  # Trajektorie <= 0,5 mm neben dem toolpath (Ersatz fuer den Sehnenfehler)
CONTACT_TOL_MM = 0.5  # (A) Obergrenze Kontakt: Mittellinienabstand <= w + 0,5 mm
STRAIGHT_TOL_MM = 1.0  # (A) "gerade": Punkte <= 1 mm neben der Sehne
SHELL_KINDS = ("outer", "inner", "hole", "outfill")
FILL_KINDS = ("infill", "web")
OUTER_KINDS = ("outer", "outfill")
PUMP_KINDS = ("print", "link")
KNOWN_KINDS = ("print", "link", "approach", "retract", "lift", "transfer", "lower")
MAX_EXAMPLES = 20


@dataclass
class Rule:
    name: str
    title: str
    hard: bool
    n_checked: int = 0
    n_violations: int = 0
    examples: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    warnings: int = 0
    note: str | None = None

    def fail(self, layer: int | None, ring: int | None, point, message: str, **extra) -> None:
        self.n_violations += 1
        if len(self.examples) < MAX_EXAMPLES:
            ex = {"layer": layer, "ring": ring,
                  "point_P": None if point is None else [round(float(v), 3) for v in point],
                  "message": message}
            ex.update({k: (round(float(v), 4) if isinstance(v, float | np.floating) else v)
                       for k, v in extra.items()})
            self.examples.append(ex)

    @property
    def passed(self) -> bool:
        return self.n_violations == 0

    def to_json(self) -> dict:
        return {"title": self.title, "hard": self.hard, "pass": self.passed, "n_checked": self.n_checked,
                "n_violations": self.n_violations, "first": self.examples[0] if self.examples else None,
                "examples": self.examples, "warnings": self.warnings, "metrics": self.metrics,
                "note": self.note}


# ---------------------------------------------------------------- Kontext je Teil


@dataclass
class Ctx:
    part: Part
    w: float
    h: float
    step: float
    layers: list[int]
    sections: dict
    islands: dict  # L -> [Polygon]
    paths: dict  # L -> [LayerPath]
    path_island: dict  # L -> [Inselindex | -1 keine | -2 mehrere]
    ring_group: dict  # Ring -> (L, Inselindex)


def chains(part: Part) -> list[list[int]]:
    """Schichtpfade aus dem toolpath: aufeinanderfolgende Ringe derselben Schicht mit link_next."""
    out: list[list[int]] = []
    for r in part.rings:
        prev = part.rings[r.index - 1] if r.index > 0 else None
        if out and prev is not None and prev.link_next and prev.layer == r.layer:
            out[-1].append(r.index)
        else:
            out.append([r.index])
    return out


def build_ctx(part: Part) -> Ctx:
    w, h = part.w, part.h
    step = min(2.0, w / 10.0)
    kinds = {r.index: r.kind for r in part.rings}
    xy = {r.index: r.pts[:, :2] for r in part.rings}
    paths: dict[int, list] = {}
    for ch in chains(part):
        if all(len(xy[r]) for r in ch):
            L = part.rings[ch[0]].layer
            paths.setdefault(L, []).append(g.build_path(L, ch, xy, kinds, step))
    layers = sorted({r.layer for r in part.rings})
    sections, isl, p_isl, ring_group = {}, {}, {}, {}
    for L in layers:
        sec = g.section(part.mesh, (L + 0.5) * h)
        sections[L] = sec
        isl[L] = g.islands(sec)
        grown = [p.buffer(M5_MARGIN_MM) for p in isl[L]]
        p_isl[L] = []
        for P in paths.get(L, []):
            cnt = [int(shapely.contains_xy(gp, P.pts[:, 0], P.pts[:, 1]).sum()) for gp in grown]
            hit = [k for k, c in enumerate(cnt) if c > 0]
            idx = -1 if not hit else (hit[0] if len(hit) == 1 else -2)
            p_isl[L].append(idx)
            for r in P.rings:
                ring_group[r] = (L, idx if idx >= 0 else int(np.argmax(cnt)) if cnt else -1)
    return Ctx(part, w, h, step, layers, sections, isl, paths, p_isl, ring_group)


# ---------------------------------------------------------------- M1


def check_m1(C: Ctx) -> Rule:
    R = Rule("M1", "Durchgehend: je Schicht und Insel genau ein Strang", True)
    part = C.part
    for L in C.layers:
        n_isl = len(C.islands[L])
        owners: dict[int, list[int]] = {k: [] for k in range(n_isl)}
        for P, idx in zip(C.paths.get(L, []), C.path_island.get(L, []), strict=True):
            R.n_checked += 1
            if idx == -1:
                R.fail(L, P.rings[0], P.pts[0], "Schichtpfad liegt in keiner Querschnittsinsel")
            elif idx == -2:
                R.fail(L, P.rings[0], P.pts[0], "Schichtpfad verbindet mehrere Inseln (ueber eine Oeffnung)")
            else:
                owners[idx].append(P.rings[0])
        for k, rs in owners.items():
            if len(rs) != 1:
                pt = np.asarray(C.islands[L][k].representative_point().coords[0])
                R.fail(L, rs[1] if len(rs) > 1 else None, pt,
                       f"Insel {k}: {len(rs)} Schichtpfade statt 1 (Strang abgesetzt oder Insel leer)",
                       island=k, n_paths=len(rs))
    tr = part.traj
    if tr is None:
        R.note = "ohne trajectory.json nur toolpath geprueft"
        return R
    bad = [i for i, k in enumerate(tr.kind) if k not in KNOWN_KINDS]
    if bad:
        R.fail(None, int(tr.ring[bad[0]]), tr.tcp[bad[0], :2], f"unbekannte Bewegungsart {tr.kind[bad[0]]!r}",
               sample=bad[0])
    kind = np.array(tr.kind)
    groups: dict[tuple[int, int], set[int]] = {}
    for r, key in C.ring_group.items():
        groups.setdefault(key, set()).add(r)
    in_strand = 0
    for (L, k), rs in sorted(groups.items()):
        idx_print = np.flatnonzero((kind == "print") & np.isin(tr.ring, list(rs)))
        missing = sorted(set(rs) - set(tr.ring[idx_print].tolist()))
        if missing:
            R.fail(L, missing[0], part.rings[missing[0]].pts[0, :2],
                   "Ring ohne print-Samples in der Trajektorie")
        if len(idx_print) == 0:
            continue
        a, b = int(idx_print.min()), int(idx_print.max())
        seg_k, seg_r = kind[a : b + 1], tr.ring[a : b + 1]
        off = np.flatnonzero(~np.isin(seg_k, PUMP_KINDS) | ~np.isin(seg_r, list(rs)))
        if len(off):
            i = a + int(off[0])
            R.fail(L, int(tr.ring[i]), tr.tcp[i, :2],
                   f"Strang unterbrochen: {kind[i]!r} (Ring {int(tr.ring[i])}) mitten in Schicht {L}, "
                   f"Insel {k}",
                   sample=i, island=k)
        else:
            in_strand += 1
    R.metrics["groups_continuous"] = in_strand
    R.metrics["groups"] = len(groups)
    R.note = "Pumpe aus der Bewegungsart abgeleitet (an genau in print/link); DRL-Pumpenbefehle prueft G5"
    return R


# ---------------------------------------------------------------- M2


def check_m2(C: Ctx, eps: float = EPS) -> Rule:
    R = Rule("M2", "Kreuzungsfrei: Abstand >= (1-eps)·w fuer Pfadpunkte mit Bogenabstand > 2·w", True)
    thr = (1.0 - eps) * C.w
    dmin = np.inf
    for L in C.layers:
        for P in C.paths.get(L, []):
            R.n_checked += 1
            if len(P.pts) < 2:
                continue
            pairs = cKDTree(P.pts).query_pairs(r=thr, output_type="ndarray")
            if len(pairs) == 0:
                continue
            i, j = pairs[:, 0], pairs[:, 1]
            d = np.linalg.norm(P.pts[i] - P.pts[j], axis=1)
            gd = g.graph_distance(P, i, j)
            viol = (gd > 2.0 * C.w) & (d < thr)
            if not viol.any():
                continue
            v = np.flatnonzero(viol)
            dmin = min(dmin, float(d[v].min()))
            m = v[np.argmin(d[v])]
            what = "Kreuzung" if d[m] < 1.5 * C.step else "zu nah / ueberfaehrt Raupe"
            R.fail(L, P.ring_at(i[m]), P.pts[i[m]], f"{what}: Abstand {d[m]:.2f} mm < {thr:.2f} mm bei "
                   f"Bogenabstand {gd[m]:.1f} mm (Ring {P.ring_at(i[m])} / Ring {P.ring_at(j[m])})",
                   distance_mm=float(d[m]), arc_mm=float(gd[m]), other_ring=P.ring_at(j[m]),
                   other_point_P=[round(float(x), 3) for x in P.pts[j[m]]], n_pairs=int(len(v)))
    R.metrics["min_distance_violation_mm"] = None if not np.isfinite(dmin) else round(dmin, 3)
    R.metrics["threshold_mm"] = round(thr, 3)
    return R


# ---------------------------------------------------------------- M3


def check_m3(C: Ctx, delta: float = DELTA_MM) -> Rule:
    R = Rule("M3", "Ueberhangfrei: Raupenflaeche L+1 in Raupenflaeche L ⊕ delta", True)
    beads = {L: g.bead_region(C.paths.get(L, []), C.w) for L in C.layers}
    worst = 0.0
    for L in C.layers:
        if L + 1 not in beads or L not in beads:
            continue
        R.n_checked += 1
        diff = beads[L + 1].difference(beads[L].buffer(delta, quad_segs=16))
        a = float(diff.area)
        worst = max(worst, a)
        if a > M3_AREA_TOL_MM2:
            pieces = sorted(getattr(diff, "geoms", [diff]), key=lambda p: -p.area)
            pt = np.asarray(pieces[0].representative_point().coords[0])
            ring = _nearest_ring(C, L + 1, pt)
            R.fail(L + 1, ring, pt, f"Ueberhang {a:.1f} mm² ueber Schicht {L} (groesstes Stueck "
                   f"{pieces[0].area:.1f} mm²)", area_mm2=a)
    R.metrics["max_overhang_area_mm2"] = round(worst, 3)
    return R


def _nearest_ring(C: Ctx, L: int, pt) -> int | None:
    best, ring = np.inf, None
    for P in C.paths.get(L, []):
        d = np.linalg.norm(P.pts - pt, axis=1)
        k = int(np.argmin(d))
        if d[k] < best:
            best, ring = d[k], P.ring_at(k)
    return ring


# ---------------------------------------------------------------- M4


def check_m4(C: Ctx) -> Rule:
    R = Rule("M4", "Senkrechter Schichtwechsel: Ende L und Anfang L+1 waagrecht <= 0,5 mm", True)
    rings = C.part.rings
    n_vert = n_exempt = n_link = 0
    tr = C.part.traj
    for L in C.layers:
        if L + 1 not in C.islands:
            continue
        ends = [r.index for r in rings if r.layer == L]
        starts = [r.index for r in rings if r.layer == L + 1]
        if not ends or not starts:
            continue
        R.n_checked += 1
        re_, rs_ = max(ends), min(starts)
        p_end, p_start = rings[re_].pts[-1, :2], rings[rs_].pts[0, :2]
        d = float(np.linalg.norm(p_end - p_start))
        linked = rings[re_].link_next and rs_ == re_ + 1
        vertical = d <= M4_TOL_MM and linked
        if tr is not None and np.any((np.array(tr.kind) == "link") & (tr.ring == rs_)):
            n_link += 1
        if vertical:
            n_vert += 1
            continue
        if len(C.islands[L]) != len(C.islands[L + 1]):
            n_exempt += 1
            continue
        why = f"waagrecht {d:.2f} mm" if d > M4_TOL_MM else "kein Verbinder (link_next = false)"
        R.fail(L, re_, p_end, f"Schichtwechsel {L} -> {L + 1} nicht senkrecht: {why} (Ring {re_} -> {rs_})",
               horizontal_mm=d, next_ring=rs_, next_point_P=[round(float(x), 3) for x in p_start])
    n = R.n_checked
    R.metrics.update(n_changes=n, n_vertical=n_vert, n_exempt_island_change=n_exempt,
                     share_vertical=None if n == 0 else round(n_vert / n, 4),
                     share_vertical_required=None if n - n_exempt == 0 else round(n_vert / (n - n_exempt), 4),
                     n_changes_as_link_in_trajectory=n_link if tr is not None else None)
    return R


# ---------------------------------------------------------------- M5


def check_m5(C: Ctx) -> Rule:
    R = Rule("M5", "Im Teil: Raupenflaeche im Querschnitt ⊕ 1 mm, nie ueber Oeffnungen", True)
    worst = 0.0
    for L in C.layers:
        allowed = C.sections[L].buffer(M5_MARGIN_MM, quad_segs=16).buffer(-C.w / 2.0, quad_segs=16)
        for P in C.paths.get(L, []):
            R.n_checked += 1
            if allowed.is_empty:
                R.fail(L, P.rings[0], P.pts[0], "kein druckbarer Querschnitt (leer oder schmaler als w)")
                continue
            d = shapely.distance(allowed, shapely.points(P.pts))
            worst = max(worst, float(d.max()))
            bad = np.flatnonzero(d > M5_TOL_MM)
            if len(bad):
                k = bad[np.argmax(d[bad])]
                R.fail(L, P.ring_at(k), P.pts[k], f"Raupe {d[k]:.2f} mm ausserhalb des Querschnitts ⊕ 1 mm "
                       f"({len(bad)} Punkte)", excess_mm=float(d[k]))
    for r in C.part.rings:
        if len(r.pts) == 0:
            continue
        dz = np.abs(r.pts[:, 2] - (r.layer + 1) * C.h)
        if dz.max() > Z_TOL_MM:
            k = int(np.argmax(dz))
            R.fail(r.layer, r.index, r.pts[k, :2], f"Wegpunkthoehe weicht {dz[k]:.2f} mm von (L+1)·h ab")
    R.metrics["max_excess_mm"] = round(worst, 3)
    return R


# ---------------------------------------------------------------- M6


def check_m6(C: Ctx) -> Rule:
    R = Rule("M6", "Kruemmungsradius der Mittellinie >= w/2 (Ziel >= w)", True)
    hard = 0.5 * C.w * (1.0 - R_REL_TOL)
    target = C.w * (1.0 - R_REL_TOL)
    step = min(1.0, C.w / 30.0)
    rmin = np.inf
    for L in C.layers:
        for P in C.paths.get(L, []):
            R.n_checked += 1
            Rv, _, q = g.window_radius(P.polyline(), step, 0.5 * C.w)
            if len(Rv) == 0:
                continue
            k = int(np.argmin(Rv))
            rmin = min(rmin, float(Rv[k]))
            if Rv[k] < hard:
                ring = _nearest_ring_in(P, q[k])
                R.fail(L, ring, q[k], f"Kruemmungsradius {Rv[k]:.1f} mm < w/2 = {0.5 * C.w:.1f} mm",
                       radius_mm=float(Rv[k]), n_points=int((Rv < hard).sum()))
            elif Rv[k] < target:
                R.warnings += 1
    R.metrics.update(min_radius_mm=None if not np.isfinite(rmin) else round(rmin, 2),
                     hard_mm=round(0.5 * C.w, 2), target_mm=round(C.w, 2), paths_below_target=R.warnings)
    R.note = ("Fenstermethode: Umkreis von p(s-w/2), p(s), p(s+w/2) auf gleichabstaendiger Abtastung; "
              "Enden der Schichtpfade (w/2) nicht ausgewertet; Sehnenfehler ohne Sollkurve nicht pruefbar, "
              "ersetzt durch M6b")
    return R


def _nearest_ring_in(P: g.LayerPath, pt) -> int:
    return P.ring_at(int(np.argmin(np.linalg.norm(P.pts - pt, axis=1))))


def check_m6b(C: Ctx) -> Rule:
    R = Rule("M6b", "Trajektorie folgt dem toolpath (print/link <= 0,5 mm)", True)
    tr = C.part.traj
    if tr is None:
        R.note = "ohne trajectory.json nicht geprueft"
        return R
    rings = C.part.rings
    kind = np.array(tr.kind)
    worst = 0.0
    for r in rings:
        for k, ref in (("print", r.pts), ("link", None)):
            idx = np.flatnonzero((kind == k) & (tr.ring == r.index))
            if len(idx) == 0:
                continue
            if k == "link":
                if r.index == 0:
                    R.fail(r.layer, r.index, tr.tcp[idx[0], :2], "Verbinder vor dem ersten Ring")
                    continue
                ref = np.vstack([rings[r.index - 1].pts[-1], r.pts[0]])
            if len(ref) == 0:
                continue
            dense = g.densify(ref, 0.2)
            d, _ = cKDTree(dense).query(tr.tcp[idx])
            R.n_checked += len(idx)
            worst = max(worst, float(d.max()))
            if d.max() > FOLLOW_TOL_MM:
                m = int(np.argmax(d))
                R.fail(r.layer, r.index, tr.tcp[idx[m], :2],
                       f"{k}-Sample {idx[m]} liegt {d[m]:.2f} mm neben dem toolpath", sample=int(idx[m]))
    R.metrics["max_deviation_mm"] = round(worst, 3)
    return R


# ---------------------------------------------------------------- M7 und Kennzahlen


def _kind_points(P: g.LayerPath, kinds) -> np.ndarray:
    ks = np.array([P.elements[e].kind for e in range(len(P.elements))])
    return np.isin(ks[P.elem], kinds)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def check_m7_and_metrics(C: Ctx, eps: float = EPS) -> tuple[Rule, dict]:
    R = Rule("M7", "Kontakt Infill/Steg an Schale (berichtet, nicht hart)", False)
    lo, hi = (1.0 - eps) * C.w, C.w + CONTACT_TOL_MM
    b = C.part.mesh.bounds
    wall_m = max(float(b[1][0] - b[0][0]), 1e-9) / 1000.0
    per_layer = []
    zones_all, len_all = [], []
    for L in C.layers:
        paths = C.paths.get(L, [])
        shell = [P.pts[_kind_points(P, SHELL_KINDS)] for P in paths]
        fill = [P.pts[_kind_points(P, FILL_KINDS)] for P in paths]
        shell_pts = np.vstack(shell) if shell else np.zeros((0, 2))
        fill_pts = np.vstack(fill) if fill else np.zeros((0, 2))
        n_z, z_len = 0, 0.0
        if len(shell_pts) and len(fill_pts):
            tree = cKDTree(shell_pts)
            for P in paths:
                for e, el in enumerate(P.elements):
                    if el.kind not in FILL_KINDS:
                        continue
                    sel = np.flatnonzero(P.elem == e)
                    d, _ = tree.query(P.pts[sel])
                    for a, z in _runs((d >= lo) & (d <= hi)):
                        n_z += 1
                        z_len += float(P.s[sel[z]] - P.s[sel[a]]) + C.step
        R.n_checked += 1
        zones_all.append(n_z)
        len_all.append(z_len)
        longest = _longest_straight_outer(C, paths, fill_pts)
        per_layer.append({"layer": L, "n_islands": len(C.islands[L]), "n_paths": len(paths),
                          "path_length_mm": round(sum(P.length for P in paths), 2),
                          "contact_zones": n_z, "contact_length_mm": round(z_len, 1),
                          "longest_straight_unsupported_outer_mm": longest})
    has_fill = any(len(P.pts[_kind_points(P, FILL_KINDS)]) for Ps in C.paths.values() for P in Ps)
    R.metrics.update(wall_length_m=round(wall_m, 4),
                     contact_zones_per_m=round(float(np.mean(zones_all)) / wall_m, 3) if zones_all else None,
                     contact_length_mm_per_m=round(float(np.mean(len_all)) / wall_m, 2) if len_all else None,
                     contact_band_mm=[round(lo, 2), round(hi, 2)])
    if not has_fill:
        R.note = "kein Infill/Steg (kind infill/web) im toolpath"
    longest = [x["longest_straight_unsupported_outer_mm"] for x in per_layer
               if x["longest_straight_unsupported_outer_mm"] is not None]
    lengths = [x["path_length_mm"] for x in per_layer]
    metrics = {"layers": per_layer,
               "longest_straight_unsupported_outer_mm": max(longest) if longest else None,
               "path_length_mm_mean": round(float(np.mean(lengths)), 2) if lengths else None,
               "path_length_mm_total": round(float(np.sum(lengths)), 2) if lengths else None,
               "n_layers": len(C.layers)}
    return R, metrics


def _longest_straight_outer(C: Ctx, paths, fill_pts: np.ndarray) -> float | None:
    """Laengste gerade, ungestuetzte Aussenstrecke einer Schicht (kind outer/outfill). Gestuetzt ist ein
    Punkt, an dem ein Infill/Steg mit Mittellinienabstand <= w + 0,5 mm anliegt."""
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

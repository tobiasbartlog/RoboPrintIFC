"""Systemseitige Selbstpruefung je Teil (nach der Planung, vor dem Schreiben des Status).

Die unabhaengigen Pruefer (`verify/`) decken einige Fehlerklassen nicht ab (Gegenpruefung A2.4,
`docs/gegenpruefung-a2-4.md`). Das System schliesst sie selbst aus: Verletzt ein Teil eine der
Pruefungen, wird es `nicht machbar` mit Ursache.

Pruefungen (Buchstaben wie in der Aufgabe A4.2):

- a: Schichtreihenfolge ueber die Druckringe monoton nicht fallend; `layer` (k) der Samples von
     `approach`/`print`/`retract`/`link`/`lift` passt zur Ringschicht (spec/ARTEFAKTE.md: `link` vor
     Ring r + 1 hat k = Schicht von r + 1). Ablauf je Strang: jeder Ring hat genau einen
     Druckabschnitt, davor `approach` oder `link` desselben Rings, danach `retract` desselben Rings oder
     `link` des Rings r + 1; `link` nach Ring r + 1 nur direkt zwischen Druck r und Druck r + 1 und nur
     mit `toolpath.rings[r].link_next`.
- b: Travel (`lift`, `transfer`, `lower`): TCP nie im Druckstand-Solid; ueber der Teil-Grundflaeche
     (Druckstand k) liegt der TCP am Ende des Abhebens und im ganzen Transfer mindestens
     z_lift - TOL_LIFT_MM ueber der Druckstand-Oberkante; `lower` endet approach_mm ueber dem Ringstart.
- c: Teil-Grundriss liegt in der Tischplatte (Tischumriss auf Hoehe der Arbeitsflaeche aus dem
     Tisch-STL) und schneidet die Roboterbasis nicht.
- d: Jeder Druck-Wegpunkt liegt im Materialquerschnitt seiner Schicht (Toleranz TOL_PRINT_MM) und
     auf der Ringhoehe (L + 1) * h. Verbinder (SPEC §5.3): Samples hoechstens TOL_LINK_MM neben der
     Geraden vom letzten Wegpunkt von r zum ersten Wegpunkt von r + 1, das letzte Sample an deren
     Ende; die waagrechte Gerade liegt im Querschnitt der Schicht von r + 1 und beim Schichtwechsel
     auch der von r (Toleranz TOL_PRINT_MM), ihre waagrechte Laenge ist <= link_max_mm, Ring r + 1 liegt
     in Schicht L(r) oder L(r) + 1 (selbst nachgerechnet, nicht aus `link_next`); link_max_mm = 0
     verbietet Verbinder.
- e: Die Trajektorie beginnt in der Home-Pose.
- f: Teilmasse stimmen mit dem Szenario (Box) bzw. der Zerlegung ueberein.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from roboprint import frames
from roboprint.assets import REPO_ROOT, load_workstation, workstation_mesh_path
from roboprint.robot import HOME_Q
from roboprint.slicer import _section_polygons

TOL_LIFT_MM = 5.0  # Abheben/Transfer: z_lift minus Toleranz ueber der Druckstand-Oberkante
TOL_LOWER_MM = 1.0  # `lower` endet approach_mm ueber dem Ringstart (Lage und Hoehe)
TOL_PRINT_MM = 1.0  # Druck-Wegpunkt im Material (Querschnitt um die Toleranz aufgeweitet), Ringhoehe
TOL_LINK_MM = 0.5  # Verbinder-Sample neben seiner Geraden (wie SPEC §11 G3)
TOL_LINK_LEN_MM = 0.01  # waagrechte Verbinderlaenge gegen link_max_mm (Rundung der Wegpunkte)
TOL_TABLE_MM = 0.5  # Grundriss in der Tischplatte (wie die S2-Regel des Pruefers)
TOL_BASE_AREA_MM2 = 1.0  # erlaubte Schnittflaeche Grundriss / Roboterbasis (Beruehrung)
TOL_HOME_RAD = 0.0087  # 0,5 Grad
TOL_SIZE_MM = 0.5
TOL_VOLUME_REL = 0.005
MAX_SAMPLES_REPORTED = 3

_TRAVEL = ("lift", "transfer", "lower")
_RING_KINDS = ("approach", "print", "retract", "link")  # k = Schicht des eigenen Rings


@dataclass(frozen=True)
class Violation:
    check: str  # "a" .. "f"
    sample: int  # erstes betroffenes Sample (0 bei Teil-Befunden)
    message: str


def _polys(geom: Any) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    return []


def _to_P(T_WP: np.ndarray, pts_W: np.ndarray) -> np.ndarray:  # noqa: N802, N803
    return frames.transform_points(frames.invert(T_WP), pts_W)


def _runs(kind: Sequence[str], ring: Sequence[int]) -> list[tuple[int, int, str]]:
    runs: list[tuple[int, int, str]] = []
    s = 0
    for i in range(1, len(kind) + 1):
        if i == len(kind) or kind[i] != kind[s] or ring[i] != ring[s]:
            runs.append((s, i, kind[s]))
            s = i
    return runs


class _Section:
    """Materialquerschnitte je Schicht (Frame P), Mitte der Schicht wie im Slicer."""

    def __init__(self, mesh_P: Any, h: float, n_layers: int) -> None:  # noqa: N803
        self.h = h
        self.layers = [unary_union(_section_polygons(mesh_P, (i + 0.5) * h)) for i in range(n_layers)]
        # cumulative[k]: Grundriss des Druckstands k (Vereinigung der Schichten 0..k-1)
        self.cumulative: list[Polygon | MultiPolygon] = [Polygon()]
        for poly in self.layers:
            self.cumulative.append(unary_union([self.cumulative[-1], poly]))

    def stand(self, k: int) -> Any:
        return self.cumulative[max(0, min(k, len(self.layers)))]


def _table_outline_W(root: Path) -> Any:  # noqa: N802
    """Umriss der Tischplatte in W auf Hoehe der Arbeitsflaeche (Schnitt knapp unter der Oberkante)."""
    import trimesh

    ws = load_workstation(root)
    mesh = trimesh.load(workstation_mesh_path(ws, root), force="mesh")
    z = float(mesh.bounds[1][2]) - 0.5
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return Polygon()
    planar, _ = sec.to_2D(to_2D=np.eye(4))
    return unary_union([p for p in planar.polygons_full if p.area > 1e-6])


def _base_footprint_W(root: Path) -> Any:  # noqa: N802
    """Grundriss der Roboterbasis in W (konvexe Huelle von base_link, wie die Pruefung des Druckplatzes)."""
    from roboprint.planner.placement import base_footprint_S

    ws = load_workstation(root)
    T = frames.T_WS(ws)  # noqa: N806
    return affine_transform(base_footprint_S(root), [T[0, 0], T[0, 1], T[1, 0], T[1, 1], T[0, 3], T[1, 3]])


def _check_order(tr: Any, tp: Any) -> list[Violation]:
    out: list[Violation] = []
    kind, ring, layer = list(tr.kind), list(tr.ring), list(tr.layer)
    rings = tp.rings
    seq: list[tuple[int, int]] = []  # (erstes Sample, Ring) je Druckring in Druckreihenfolge
    for a, _b, k in _runs(kind, ring):
        if k == "print" and (not seq or seq[-1][1] != ring[a]):
            seq.append((a, ring[a]))
    for (_, r0), (a1, r1) in zip(seq[:-1], seq[1:], strict=False):
        if rings[r1].layer < rings[r0].layer:
            out.append(
                Violation(
                    "a",
                    a1,
                    f"Schichtreihenfolge: Ring {r1} (Schicht {rings[r1].layer}) wird nach Ring {r0} "
                    f"(Schicht {rings[r0].layer}) gedruckt",
                )
            )
            break
    for i, (k, r, ly) in enumerate(zip(kind, ring, layer, strict=True)):
        want = rings[r].layer + (1 if k == "lift" else 0)
        if (k in _RING_KINDS or k == "lift") and ly != want:
            out.append(Violation("a", i, f"{k} in Ring {r}: Druckstand k = {ly}, erwartet {want}"))
            break
    out += _check_strands(kind, ring, rings)
    return out


def _check_strands(kind: list[str], ring: list[int], rings: Sequence[Any]) -> list[Violation]:
    """Ablauf je Strang (spec/ARTEFAKTE.md); meldet den ersten Verstoss."""
    segs = _runs(kind, ring)
    printed: set[int] = set()
    for j, (a, _b, k) in enumerate(segs):
        r = ring[a]
        prev = (segs[j - 1][2], ring[segs[j - 1][0]]) if j > 0 else None
        nxt = (segs[j + 1][2], ring[segs[j + 1][0]]) if j + 1 < len(segs) else None
        msg = None
        if k == "print":
            if r in printed:
                msg = f"Ring {r} hat mehrere Druckabschnitte"
            elif prev not in (("approach", r), ("link", r)):
                msg = f"Ring {r}: vor dem Druck steht {prev}, erwartet approach oder link desselben Rings"
            elif nxt not in (("retract", r), ("link", r + 1)):
                msg = f"Ring {r}: nach dem Druck steht {nxt}, erwartet retract oder link zu Ring {r + 1}"
            printed.add(r)
        elif k == "link":
            if not 1 <= r < len(rings) or not getattr(rings[r - 1], "link_next", False):
                msg = f"Verbinder von Ring {r - 1} nach Ring {r} ohne link_next"
            elif prev != ("print", r - 1) or nxt != ("print", r):
                msg = f"Verbinder nach Ring {r} steht nicht zwischen Druck {r - 1} und Druck {r}"
        if msg is not None:
            return [Violation("a", a, f"Ablauf je Strang: {msg}")]
    missing = sorted(set(range(len(rings))) - printed)
    if missing:
        return [Violation("a", 0, f"Ablauf je Strang: Ringe ohne Druckabschnitt: {missing[:10]}")]
    return []


def _check_travel(
    tr: Any,
    tp: Any,
    P: np.ndarray,
    sec: _Section,
    z_lift: float,
    approach: float,
    T_WP: np.ndarray,  # noqa: N803
) -> list[Violation]:
    out: list[Violation] = []
    h = sec.h
    kind, ring, layer = list(tr.kind), list(tr.ring), np.asarray(tr.layer, int)
    is_travel = np.array([k in _TRAVEL for k in kind])
    # kein Travel-Sample im Druckstand-Solid
    for i in np.flatnonzero(is_travel):
        k, z = int(layer[i]), P[i, 2]
        if z >= k * h - 1e-6:
            continue
        li = int(np.floor(max(z, 0.0) / h))
        if li < len(sec.layers) and shapely.contains_xy(sec.layers[li], P[i, 0], P[i, 1]):
            out.append(
                Violation(
                    "b",
                    int(i),
                    f"{kind[i]}-Sample {int(i)}: TCP (z_P = {z:.1f} mm) im Druckstand k = {k} "
                    f"(Oberkante {k * h:.0f} mm)",
                )
            )
            break
    # Mindesthoehe ueber der Teil-Grundflaeche
    for a, b, k in _runs(kind, ring):
        if k not in ("lift", "transfer"):
            continue
        idx = np.arange(a, b) if k == "transfer" else np.array([b - 1])
        for i in idx:
            kk = int(layer[i])
            if kk <= 0 or not shapely.contains_xy(sec.stand(kk), P[i, 0], P[i, 1]):
                continue
            clr = P[i, 2] - kk * h
            if clr < z_lift - TOL_LIFT_MM:
                out.append(
                    Violation(
                        "b",
                        int(i),
                        f"{k}-Sample {int(i)}: TCP nur {clr:.1f} mm ueber dem Druckstand (k = {kk}) "
                        f"ueber der Teil-Grundflaeche, verlangt >= {z_lift - TOL_LIFT_MM:.0f} mm",
                    )
                )
                break
        else:
            continue
        break
    # `lower` endet approach_mm ueber dem Ringstart
    for a, b, k in _runs(kind, ring):
        if k != "lower":
            continue
        start_P = _to_P(T_WP, np.asarray(tp.rings[ring[a]].waypoints[0][:3], float)[None])[0]
        e = P[b - 1]
        dxy = float(np.linalg.norm(e[:2] - start_P[:2]))
        dz = float(e[2] - start_P[2])
        if dxy > TOL_LOWER_MM or abs(dz - approach) > TOL_LOWER_MM:
            out.append(
                Violation(
                    "b",
                    b - 1,
                    f"lower endet {dz:.1f} mm ueber dem Ringstart (Ring {ring[a]}, seitlich {dxy:.1f} mm), "
                    f"verlangt {approach:.0f} mm",
                )
            )
            break
    return out


def _check_print(tr: Any, tp: Any, P: np.ndarray, sec: _Section, h: float) -> list[Violation]:  # noqa: N803
    out: list[Violation] = []
    kind, ring = np.asarray(tr.kind), np.asarray(tr.ring, int)
    idx = np.flatnonzero(kind == "print")
    for r in np.unique(ring[idx]):
        ii = idx[ring[idx] == r]
        L = tp.rings[int(r)].layer  # noqa: N806
        poly = sec.layers[L] if L < len(sec.layers) else Polygon()
        ok = shapely.contains_xy(poly.buffer(TOL_PRINT_MM), P[ii, 0], P[ii, 1])
        if not ok.all():
            i = int(ii[np.flatnonzero(~ok)[0]])
            d = float(shapely.distance(poly, shapely.Point(P[i, 0], P[i, 1])))
            out.append(
                Violation(
                    "d",
                    i,
                    f"Druck-Sample {i} (Ring {int(r)}, Schicht {L}): {d:.1f} mm ausserhalb des "
                    f"Teilquerschnitts ({int((~ok).sum())} Samples im Ring)",
                )
            )
            break
        dz = np.abs(P[ii, 2] - (L + 1) * h)
        if (dz > TOL_PRINT_MM).any():
            i = int(ii[np.flatnonzero(dz > TOL_PRINT_MM)[0]])
            out.append(
                Violation(
                    "d",
                    i,
                    f"Druck-Sample {i} (Ring {int(r)}): z_P = {P[i, 2]:.1f} mm, "
                    f"Ringhoehe {(L + 1) * h:.0f} mm",
                )
            )
            break
    return out


def _check_links(
    tr: Any,
    tp: Any,
    P: np.ndarray,  # noqa: N803
    sec: _Section,
    T_WP: np.ndarray,  # noqa: N803
    link_max_mm: float,
) -> list[Violation]:
    """Verbinder auf ihrer Geraden, am Ziel, ueber Material und nicht laenger als link_max_mm."""
    kind, ring = list(tr.kind), list(tr.ring)
    rings = tp.rings
    for a, b, k in _runs(kind, ring):
        r1 = ring[a]
        if k != "link" or not 1 <= r1 < len(rings):
            continue
        r0 = r1 - 1
        ends_W = np.array([rings[r0].waypoints[-1][:3], rings[r1].waypoints[0][:3]], dtype=float)  # noqa: N806
        A, B = _to_P(T_WP, ends_W)  # noqa: N806
        pts = P[a:b]
        ab = B - A
        t = np.clip(((pts - A) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
        dev = np.linalg.norm(pts - (A + t[:, None] * ab), axis=1)
        where = f"Verbinder Ring {r0} -> {r1}"
        if link_max_mm <= 0:
            return [Violation("d", a, f"{where}: Verbinder trotz link_max_mm = {link_max_mm:g} (aus)")]
        d_layer = rings[r1].layer - rings[r0].layer
        if d_layer not in (0, 1):
            return [Violation("d", a, f"{where}: Schichtsprung {d_layer}, erlaubt 0 oder 1 (SPEC §5.3)")]
        if dev.max() > TOL_LINK_MM:
            i = a + int(np.argmax(dev))
            return [Violation("d", i, f"{where}: Sample {i} {dev.max():.2f} mm neben der Geraden")]
        if np.linalg.norm(pts[-1] - B) > TOL_LINK_MM:
            return [Violation("d", b - 1, f"{where} endet nicht am Start von Ring {r1}")]
        hlen = float(np.linalg.norm(ab[:2]))
        if hlen > link_max_mm + TOL_LINK_LEN_MM:
            return [Violation("d", a, f"{where}: {hlen:.1f} mm lang, link_max_mm = {link_max_mm:g}")]
        geom = LineString([A[:2], B[:2]]) if hlen > 1e-9 else Point(A[:2])
        for L in sorted({rings[r0].layer, rings[r1].layer}):  # noqa: N806
            poly = sec.layers[L] if L < len(sec.layers) else Polygon()
            if poly.is_empty or not poly.buffer(TOL_PRINT_MM).covers(geom):
                off = geom.difference(poly.buffer(TOL_PRINT_MM)).length if not poly.is_empty else hlen
                msg = f"{where}: {off:.1f} mm ausserhalb des Teilquerschnitts der Schicht {L}"
                return [Violation("d", a, msg)]
    return []


def _check_placement(sec: _Section, T_WP: np.ndarray, root: Path) -> list[Violation]:  # noqa: N803
    out: list[Violation] = []
    foot_P = sec.stand(len(sec.layers))  # noqa: N806
    if foot_P.is_empty:
        return [Violation("c", 0, "Teil hat keinen Grundriss")]
    foot = affine_transform(foot_P, [T_WP[0, 0], T_WP[0, 1], T_WP[1, 0], T_WP[1, 1], T_WP[0, 3], T_WP[1, 3]])
    table = _table_outline_W(root)
    outside = foot.difference(table.buffer(TOL_TABLE_MM))
    if outside.area > 1e-6:
        out.append(
            Violation(
                "c",
                0,
                f"Teil-Grundriss ragt {100 * outside.area / foot.area:.0f} % ({outside.area:.0f} mm2) "
                "ueber die Tischplatte",
            )
        )
    inter = foot.intersection(_base_footprint_W(root)).area
    if inter > TOL_BASE_AREA_MM2:
        out.append(Violation("c", 0, f"Teil-Grundriss schneidet die Roboterbasis ({inter:.0f} mm2)"))
    return out


def _check_home(tr: Any) -> list[Violation]:
    if not len(tr.q):
        return [Violation("e", 0, "Trajektorie ist leer")]
    q0 = np.asarray(tr.q[0], float)
    err = float(np.abs(q0 - HOME_Q).max())
    if err > TOL_HOME_RAD:
        return [
            Violation(
                "e",
                0,
                "Trajektorie beginnt nicht in der Home-Pose: q[0] = "
                f"{np.round(np.degrees(q0), 1).tolist()} deg (max. Abweichung {np.degrees(err):.1f} deg)",
            )
        ]
    return []


def _check_dims(
    mesh_P: Any,  # noqa: N803
    expected_size_mm: Sequence[float] | None,
    expected_volume_mm3: float | None,
) -> list[Violation]:
    out: list[Violation] = []
    lo, hi = np.asarray(mesh_P.bounds, float)
    if abs(lo[2]) > TOL_SIZE_MM:
        out.append(Violation("f", 0, f"Teil steht nicht auf z_P = 0 (Unterkante {lo[2]:.1f} mm)"))
    if expected_size_mm is not None:
        size = hi - lo
        exp = np.asarray(expected_size_mm, float)
        if np.abs(size - exp).max() > TOL_SIZE_MM:
            out.append(
                Violation(
                    "f",
                    0,
                    f"Teilmasse {np.round(size, 1).tolist()} mm stimmen nicht mit dem Szenario "
                    f"{np.round(exp, 1).tolist()} mm ueberein",
                )
            )
        if expected_volume_mm3 is None:
            expected_volume_mm3 = float(np.prod(exp))
    if expected_volume_mm3 is not None:
        vol = float(mesh_P.volume)
        if abs(vol - expected_volume_mm3) > TOL_VOLUME_REL * expected_volume_mm3:
            out.append(
                Violation(
                    "f",
                    0,
                    f"Teilvolumen {vol:.0f} mm3 statt {expected_volume_mm3:.0f} mm3 (Szenario/Zerlegung)",
                )
            )
    return out


def check_part(
    mesh_P: Any,  # noqa: N803
    T_WP: np.ndarray,  # noqa: N803
    tr: Any,
    tp: Any,
    *,
    layer_height_mm: float = 10.0,
    z_lift_mm: float = 30.0,
    approach_mm: float = 20.0,
    link_max_mm: float = 60.0,
    expected_size_mm: Sequence[float] | None = None,
    expected_volume_mm3: float | None = None,
    root: Path = REPO_ROOT,
) -> list[Violation]:
    """Alle Selbstpruefungen. `tr` hat q, tcp, kind, ring, layer; `tp` hat rings[].layer/waypoints
    (und `link_next`)."""
    h = layer_height_mm
    T_WP = np.asarray(T_WP, float)  # noqa: N806
    out = _check_dims(mesh_P, expected_size_mm, expected_volume_mm3)
    out += _check_home(tr)
    n_layers = int(round(float(mesh_P.bounds[1][2]) / h))
    sec = _Section(mesh_P, h, max(n_layers, max((r.layer for r in tp.rings), default=-1) + 1))
    out += _check_placement(sec, T_WP, root)
    if len(tr.q):
        P = _to_P(T_WP, np.asarray(tr.tcp, float)[:, :3])  # noqa: N806
        out += _check_order(tr, tp)
        out += _check_travel(tr, tp, P, sec, z_lift_mm, approach_mm, T_WP)
        out += _check_print(tr, tp, P, sec, h)
        out += _check_links(tr, tp, P, sec, T_WP, link_max_mm)
    return out


def apply(pp: Any, job: Any, tr: Any, tp: Any, params: Any, scn: Any = None) -> list[Violation]:
    """Pipeline-Naht: prueft das geplante Teil und setzt es bei Verletzung auf `nicht machbar`.

    `pp` ist der `PartPlan` (`pp.path.feasible/cause` werden ueberschrieben, falls noch machbar),
    `tr`/`tp` die Artefakt-Modelle des Teils, `scn` das Szenario (fuer die Boxmasse).
    """
    size = None
    if scn is not None and getattr(scn.source, "kind", None) == "box":
        size = [float(v) for v in scn.source.size_mm]
    vols = getattr(job, "expected_volume_mm3", None)
    size = getattr(job, "expected_size_mm", None) or size
    viol = check_part(
        job.mesh_P,
        pp.T_WP,
        tr,
        tp,
        layer_height_mm=params.layer_height_mm,
        z_lift_mm=params.z_lift_mm,
        approach_mm=params.approach_mm,
        link_max_mm=params.link_max_mm,
        expected_size_mm=size,
        expected_volume_mm3=vols,
    )
    if viol and pp.path.feasible:
        v = viol[0]
        extra = f" (+{len(viol) - 1} weitere Selbstpruefungen)" if len(viol) > 1 else ""
        pp.path.feasible = False
        pp.path.cause = {
            "sample": int(min(max(v.sample, 0), max(len(tr.q) - 1, 0))),
            "link": "Selbstpruefung",
            "obstacle": f"Pruefung {v.check}",
            "message": f"Selbstpruefung ({v.check}): {v.message}{extra}",
        }
    return viol


def check_part_dir(part_dir: str | Path, scenario_path: str | Path | None = None) -> list[Violation]:
    """Prueft ein geschriebenes Teil `parts/<id>/` (fuer Tests und Experimente). Prozessparameter
    (z_lift, An-/Abfahrt, link_max) aus `summary.json` des Laufs, falls vorhanden."""
    import trimesh

    from roboprint.contracts import PartArtifact, Toolpath, Trajectory, load_json

    d = Path(part_dir)
    prm: dict[str, Any] = {}
    summ = d.parent.parent / "summary.json"
    if summ.is_file():
        prm = json.loads(summ.read_text(encoding="utf-8")).get("params", {}) or {}
    part = load_json(d / "part.json", PartArtifact)
    tp = load_json(d / "toolpath.json", Toolpath)
    tr = load_json(d / "trajectory.json", Trajectory)
    mesh = trimesh.load(d / "part.stl", force="mesh")
    size = None
    if scenario_path is not None:
        src = json.loads(Path(scenario_path).read_text(encoding="utf-8")).get("source", {})
        if src.get("kind") == "box":
            size = [float(v) for v in src["size_mm"]]
    return check_part(
        mesh,
        np.asarray(part.T_WP, float),
        tr,
        tp,
        layer_height_mm=tp.layer_height_mm,
        z_lift_mm=float(prm.get("z_lift_mm", 30.0)),
        approach_mm=float(prm.get("approach_mm", 20.0)),
        link_max_mm=float(prm.get("link_max_mm", 60.0)),
        expected_size_mm=size,
    )

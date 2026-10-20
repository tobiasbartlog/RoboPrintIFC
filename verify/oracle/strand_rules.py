"""Strang-Regeln fuer check_run (G3): Ablauf, Schichtregel, Verbinder und Zweigwechsel je Strang.

Grundlage: spec/ARTEFAKTE.md (Abschnitt "Schichten, TCP-Hoehe und Druckstand") und SPEC §5.3
(Nutzerentscheidung 20.10.2026). Reine numpy/shapely-Funktionen ohne Roboter- oder Kollisionsmodell:
Sie bekommen Arten, Ringindizes, Positionen und Querschnitte und liefern Fehlertexte. Damit sind sie
auch ohne Pinocchio und Coal pruefbar (selftest_strand.py). Importiert roboprint nicht.

Strang: Folge `approach` -> `print` r -> `link` r+1 -> `print` r+1 -> ... -> `print` s -> `retract`, ohne
Travel (`lift`, `transfer`, `lower`) dazwischen. Ein Strang aus einem Ring ist der Fall r = s.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from shapely.geometry import LineString, Point

KINDS = ("print", "link", "approach", "retract", "lift", "transfer", "lower")
RING_KINDS = ("approach", "print", "retract")
STRAND_KINDS = ("approach", "print", "link", "retract")
TRAVEL_KINDS = ("lift", "transfer", "lower")

LINK_MAX_DEFAULT = 60.0  # mm, SPEC §10 (Nutzer 20.10.2026); 0 schaltet Verbinder ab
LINK_LINE_TOL = 0.5  # mm, Verbinder-Samples und Endpunkte neben ihrer Geraden (SPEC §11 G3)
LINK_SECTION_TOL = 1.0  # mm, waagrechte Projektion im Querschnitt
LINK_LEN_TOL = 0.01  # mm, Rundung der Wegpunkte gegen link_max_mm


def segments(kind: Sequence[str], ring: Sequence[int]) -> list[tuple[str, int, int, int]]:
    """Abschnitte gleicher (Art, Ring) in Folge: (Art, Ring, erstes Sample, letztes Sample)."""
    out: list[list] = []
    for i, (k, r) in enumerate(zip(kind, ring, strict=True)):
        r = int(r)
        if out and out[-1][0] == k and out[-1][1] == r:
            out[-1][3] = i
        else:
            out.append([k, r, i, i])
    return [tuple(s) for s in out]


def strand_runs(kind: Sequence[str]) -> list[np.ndarray]:
    """Indizes je Strang: zusammenhaengende Folgen aus approach/print/link/retract ohne Travel."""
    runs: list[list[int]] = []
    prev = False
    for i, k in enumerate(kind):
        cur = k in STRAND_KINDS
        if cur and not prev:
            runs.append([])
        if cur:
            runs[-1].append(i)
        prev = cur
    return [np.array(r, dtype=int) for r in runs]


def expected_layers(kind: Sequence[str], ring: Sequence[int], ring_layer: np.ndarray) -> np.ndarray:
    """Soll-k je Sample (ARTEFAKTE): approach/print/retract eines Rings in Schicht L -> L; link -> Schicht
    des folgenden Rings (= eigener Ringindex); Travel nach einem Ring in Schicht L -> L + 1, vor dem
    ersten Druck 0."""
    exp = np.zeros(len(kind), dtype=int)
    last_L = None
    for i, k in enumerate(kind):
        if k in STRAND_KINDS:
            exp[i] = int(ring_layer[int(ring[i])])
        else:
            exp[i] = 0 if last_L is None else last_L + 1
        if k == "print":
            last_L = int(ring_layer[int(ring[i])])
    return exp


def sequence_errors(kind: Sequence[str], ring: Sequence[int], link_next: Sequence[bool],
                    n_rings: int) -> list[str]:
    """Ablauf je Strang (ARTEFAKTE): genau ein Druckabschnitt je Ring; davor approach oder link desselben
    Rings, danach retract desselben Rings oder link des Rings r + 1; link r + 1 nur direkt zwischen
    print r und print r + 1 und nur mit toolpath.rings[r].link_next = true."""
    segs = segments(kind, ring)
    errs: list[str] = []
    printed: dict[int, int] = {}
    for s, (k, r, i0, _) in enumerate(segs):
        prev = segs[s - 1][:2] if s > 0 else None
        nxt = segs[s + 1][:2] if s + 1 < len(segs) else None
        if k == "print":
            if r in printed:
                errs.append(f"Ring {r} hat mehrere Druckabschnitte (#{printed[r]}, #{i0})")
            printed.setdefault(r, i0)
            if prev not in (("approach", r), ("link", r)):
                errs.append(f"Ring {r}: vor dem Druck (#{i0}) steht {prev}, erwartet approach oder link "
                            "desselben Rings")
            if nxt not in (("retract", r), ("link", r + 1)):
                errs.append(f"Ring {r}: nach dem Druck steht {nxt}, erwartet retract desselben Rings oder "
                            f"link des Rings {r + 1}")
        elif k == "link":
            if not 1 <= r < n_rings:
                errs.append(f"#{i0} link mit Ring {r}: kein Verbinder von Ring {r - 1} moeglich")
            elif not bool(link_next[r - 1]):
                errs.append(f"#{i0} link von Ring {r - 1} nach Ring {r}, aber toolpath.rings[{r - 1}]."
                            "link_next ist nicht true")
            if prev != ("print", r - 1) or nxt != ("print", r):
                errs.append(f"#{i0} link Ring {r} steht nicht direkt zwischen print {r - 1} und print {r} "
                            f"(davor {prev}, danach {nxt})")
    missing = sorted(set(range(n_rings)) - set(printed))
    if missing:
        errs.append(f"Ringe ohne Druckabschnitt: {missing[:10]}")
    return errs


def _seg_dev(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Abstand der Punkte p (n,3) zur Strecke a-b."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def link_errors(kind: Sequence[str], ring: Sequence[int], pos: np.ndarray, reach: np.ndarray,
                waypoints: Sequence[np.ndarray], ring_layer: np.ndarray, link_max: float,
                inv_T_WP: np.ndarray, section_of: Callable[[int], object]) -> tuple[list[str], dict]:
    """Verbinder-Geometrie (SPEC §5.3, ARTEFAKTE) fuer jeden link-Abschnitt von Ring r nach r + 1.

    - Schichtsprung L(r + 1) - L(r) in {0, 1}.
    - Waagrechte Laenge vom letzten Wegpunkt von r (A) zum ersten Wegpunkt von r + 1 (B) <= link_max
      (+ LINK_LEN_TOL); link_max <= 0 verbietet Verbinder.
    - Jedes erreichbare link-Sample <= LINK_LINE_TOL neben der Strecke A-B; das letzte print-Sample von r
      oder das erste link-Sample trifft A, das letzte link-Sample trifft B.
    - Waagrechte Projektion von A-B (Frame P) im Querschnitt der Schicht L(r + 1), beim Schichtwechsel
      auch L(r), mit LINK_SECTION_TOL Toleranz. `section_of(L)` liefert den Querschnitt (shapely, P-xy).

    pos: TCP-Positionen in W (N,3), NaN bei unerreichbaren Samples. Rueckgabe (Fehler, Kennzahlen)."""
    errs: list[str] = []
    n_links, max_dev, max_len = 0, 0.0, 0.0
    for k, r1, i0, i1 in segments(kind, ring):
        if k != "link":
            continue
        n_links += 1
        r0 = r1 - 1
        if not (0 <= r0 and r1 < len(waypoints)):
            continue  # meldet sequence_errors
        A = np.asarray(waypoints[r0], dtype=float)[-1, :3]
        B = np.asarray(waypoints[r1], dtype=float)[0, :3]
        dL = int(ring_layer[r1]) - int(ring_layer[r0])
        if dL not in (0, 1):
            errs.append(f"link #{i0} Ring {r0}->{r1}: Schichtsprung {dL} (erlaubt 0 oder 1)")
        hlen = float(np.hypot(*(B - A)[:2]))
        max_len = max(max_len, hlen)
        if link_max <= 0:
            errs.append(f"link #{i0} Ring {r0}->{r1}: Verbinder trotz link_max_mm = {link_max:g} (aus)")
        elif hlen > link_max + LINK_LEN_TOL:
            errs.append(f"link #{i0} Ring {r0}->{r1}: waagrechte Laenge {hlen:.2f} mm > link_max_mm "
                        f"{link_max:g}")
        idx = np.arange(i0, i1 + 1)
        idx = idx[reach[idx]]
        if len(idx):
            dev = _seg_dev(pos[idx], A, B)
            max_dev = max(max_dev, float(dev.max()))
            j = int(np.argmax(dev))
            if dev[j] > LINK_LINE_TOL:
                errs.append(f"link #{idx[j]} Ring {r0}->{r1}: {dev[j]:.3f} mm neben der Geraden "
                            f"({int(np.sum(dev > LINK_LINE_TOL))} Samples)")
        starts = [i for i in (i0 - 1, i0) if i >= 0 and reach[i] and kind[i] in ("print", "link")]
        if starts:
            e = min(float(np.linalg.norm(pos[i] - A)) for i in starts)
            if e > LINK_LINE_TOL:
                errs.append(f"link #{i0} Ring {r0}->{r1}: beginnt {e:.3f} mm neben dem letzten Wegpunkt "
                            f"von Ring {r0}")
        if reach[i1]:
            e = float(np.linalg.norm(pos[i1] - B))
            if e > LINK_LINE_TOL:
                errs.append(f"link #{i1} Ring {r0}->{r1}: endet {e:.3f} mm neben dem ersten Wegpunkt "
                            f"von Ring {r1}")
        a = inv_T_WP[:3, :3] @ A + inv_T_WP[:3, 3]
        b = inv_T_WP[:3, :3] @ B + inv_T_WP[:3, 3]
        geom = LineString([a[:2], b[:2]]) if np.linalg.norm(b[:2] - a[:2]) > 1e-9 else Point(a[:2])
        layers = [int(ring_layer[r1])] + ([int(ring_layer[r0])] if dL != 0 else [])
        for L in layers:
            sec = section_of(L)
            if sec.is_empty or not sec.buffer(LINK_SECTION_TOL).covers(geom):
                out = geom.difference(sec.buffer(LINK_SECTION_TOL)) if not sec.is_empty else geom
                errs.append(f"link #{i0} Ring {r0}->{r1}: waagrechte Projektion verlaesst den Querschnitt "
                            f"der Schicht {L} ({out.length:.2f} mm ausserhalb, Toleranz "
                            f"{LINK_SECTION_TOL:g} mm)")
    return errs, {"n_links": n_links, "max_link_dev_mm": max_dev, "max_link_len_mm": max_len}


def branch_changes(kind: Sequence[str], branch: np.ndarray, reach: np.ndarray) -> int:
    """Zweigwechsel zwischen aufeinanderfolgenden erreichbaren Samples innerhalb eines Strangs
    (Semantik von trajectory.summary.zweig_wechsel_in_ringen, ARTEFAKTE)."""
    n = 0
    for idx in strand_runs(kind):
        b = np.asarray(branch)[idx][np.asarray(reach)[idx]]
        n += int(np.count_nonzero(np.diff(b) != 0))
    return n


def strand_rings(ring: Sequence[int], idx: np.ndarray) -> str:
    """Kurzbeschreibung eines Strangs fuer Meldungen: 'Ringe a..b' bzw. 'Ring a'."""
    rs = sorted({int(ring[i]) for i in idx})
    return f"Ring {rs[0]}" if len(rs) == 1 else f"Ringe {rs[0]}..{rs[-1]}"

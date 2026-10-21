"""Ablaufplan des DRL-Emitters: Trajektorie -> Bewegungen und Pumpe (SPEC §5.3, §5.6).

Dialektunabhaengig und ohne Text. Schnittstelle::

    plan_steps(tr, toolpath, T_BT, T_WB, r_blend_mm, match_tol_mm) -> list[Step]

`Step` ist `Move` (movej/movel auf ein Sample), `Pump` (an/aus) oder `Comment`. Jedes
Bewegungsziel ist ein Sample der Trajektorie; nichts wird per IK neu gerechnet.

**Strang** (Nutzerentscheidung 20.10.2026): Ringe, die die Trajektorie ueber Verbinder (`link`)
verbindet, bilden einen Strang `print r [link r+1, print r+1]*` zwischen `approach` und `retract`.
Massgeblich ist die Trajektorie, nicht `link_next`: ein Strang endet, wo nach `print` etwas
anderes als `link` folgt. Ein Ring ohne Verbinder ist ein Strang aus einem Ring (alter Ablauf).

- `Pump(True)` einmal am Strangbeginn, im Stillstand nach der Anfahrt (das letzte Anfahr-`movel`
  hat radius 0); `Pump(False)` einmal am Strangende, vor dem Abfahren.
- Druck: je Toolpath-Wegpunkt ein `movel` auf das zugeordnete Druck-Sample; Verbinder: ein `movel`
  auf sein letztes Sample (= erster Wegpunkt des naechsten Rings, die Samples liegen auf der Geraden).
- radius = min(r_blend, 1/2 der angrenzenden Segmente) an allen Zielen des Strangs, auch am
  Ringende und an den Verbinder-Ecken; nur das letzte `movel` des Strangs hat radius 0 (Halt, damit
  die Pumpe dort und nicht in der Blending-Zone schaltet).
- Ziele naeher als `_MERGE_MM` am vorigen Ziel desselben Strangs werden zusammengefasst (das
  spaetere Sample bleibt), damit kein radius 0 und damit kein Halt im Strang entsteht.

**Druckmuster** (opt-in, docs/muster/ARTEFAKT-FORMAT.md): Offene Ringe (`closed = false`) laufen
wie geschlossene, je Wegpunkt ein `movel` bis zum letzten Wegpunkt. Ein Verbinder der Laenge 0 in
der Schicht faellt mit dem Ringende zusammen und wird dessen Ziel (kein Segment der Laenge 0, kein
radius 0); ein senkrechter Schichtwechsel ist ein `movel` um h nach oben, radius = min(r_blend,
h/2, ...). Der Ringkommentar nennt beides ("ueber Verbinder, senkrecht, Z +10.0 mm" bzw.
"Laenge 0", nur wenn `Toolpath.pattern` gesetzt ist); Verbinder mit waagrechter Laenge und alle
Verbinder ohne Muster behalten den bisherigen Text.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from roboprint.contracts import Toolpath, Trajectory

LINEAR_TOL_MM = 0.01  # Abweichung, ab der ein kartesischer Knick ein neues movel ist
LINEAR_TOL_RAD = 1e-6  # dito fuer gelenklineare Transfers
_SAME_MM = 1e-4
_SAME_RAD = 1e-7
_MERGE_MM = 1e-3  # Ziele im Strang naeher als das: ein Ziel (radius bleibt > 0 nach Abrunden)
ZERO_LINK_MM = 0.5  # waagrechte Laenge, bis zu der ein Verbinder "Laenge 0" bzw. ein Z-Hub ist (M4)

CARTESIAN_KINDS = ("lift", "lower", "approach", "retract")
STRAND_KINDS = ("print", "link")


@dataclass(frozen=True)
class Move:
    cmd: Literal["movej", "movel"]
    sample: int
    kind: str
    ring: int
    radius_mm: float = 0.0


@dataclass(frozen=True)
class Pump:
    """Pumpe an (Strangbeginn) oder aus (Strangende). `ring`: erster bzw. letzter Ring des Strangs,
    `links`: Verbinder im Strang, `moves`: Bewegungsziele im Strang."""

    on: bool
    ring: int
    links: int = 0
    moves: int = 0


@dataclass(frozen=True)
class Comment:
    text: str


Step = Move | Pump | Comment


def linear_breaks(P: np.ndarray, start: np.ndarray, tol: float) -> list[int]:  # noqa: N803
    """Indizes in P, an denen die Bahn start -> P[0] -> ... die Gerade verlaesst (Knick oder
    Umkehr), plus der letzte Index. Jedes Stueck dazwischen ist eine Gerade."""
    out: list[int] = []
    seg0, d, reach = start, None, 0.0
    for k in range(len(P)):
        v = P[k] - seg0
        if d is None:
            n = float(np.linalg.norm(v))
            if n > tol:
                d, reach = v / n, n
            continue
        proj = float(v @ d)
        if np.linalg.norm(v - proj * d) > tol or proj < reach - tol:
            out.append(k - 1)
            seg0 = P[k - 1]
            v = P[k] - seg0
            n = float(np.linalg.norm(v))
            d, reach = (v / n, n) if n > tol else (None, 0.0)
        else:
            reach = max(reach, proj)
    if len(P) and (not out or out[-1] != len(P) - 1):
        out.append(len(P) - 1)
    return out


def runs(kind: list[str], ring: list[int]) -> list[tuple[int, int]]:
    """Zusammenhaengende Abschnitte gleicher (kind, ring) als (Start, Ende) inklusive."""
    out, s = [], 0
    for i in range(1, len(kind) + 1):
        if i == len(kind) or kind[i] != kind[s] or ring[i] != ring[s]:
            out.append((s, i - 1))
            s = i
    return out


def match_waypoints(
    cand: list[int],
    P_W: np.ndarray,  # noqa: N803
    waypoints: np.ndarray,
    tol: float,
    ring: int,
) -> list[int]:
    """Monotone Zuordnung Wegpunkt -> Sample (Index in `cand`): das erste Sample innerhalb `tol`,
    dann weiter, solange der Abstand faellt."""
    out: list[int] = []
    j = 0
    prev_wp = None
    for w, wp in enumerate(waypoints):
        if prev_wp is not None and np.linalg.norm(wp - prev_wp) < _SAME_MM:
            continue
        dist = np.linalg.norm(P_W[cand] - wp, axis=1)
        k = j
        while k < len(cand) and dist[k] > tol:
            k += 1
        if k == len(cand):
            raise ValueError(
                f"Ring {ring}: Wegpunkt {w} {np.round(wp, 3).tolist()} liegt auf keinem Druck-Sample "
                f"(Toleranz {tol} mm)"
            )
        while k + 1 < len(cand) and dist[k + 1] < dist[k]:
            k += 1
        out.append(k)
        j = k + 1
        prev_wp = wp
    return out


def link_note(a: np.ndarray, b: np.ndarray) -> str:
    """Zusatz im Ringkommentar fuer Verbinder ohne waagrechte Laenge (Muster, M4): reiner Z-Hub
    ("senkrecht, Z +10.0 mm") oder Laenge 0 in der Schicht; sonst leer (Text wie bisher)."""
    d = np.asarray(b, float) - np.asarray(a, float)
    if math.hypot(d[0], d[1]) > ZERO_LINK_MM:
        return ""
    return f"senkrecht, Z {d[2]:+.1f} mm" if abs(d[2]) > ZERO_LINK_MM else "Laenge 0"


def ring_label(toolpath: Toolpath, ring: int, via_link: bool = False, note: str = "") -> str:
    rp = toolpath.rings[ring] if 0 <= ring < len(toolpath.rings) else None
    via = (f" (ueber Verbinder, {note})" if note else " (ueber Verbinder)") if via_link else ""
    head = f"Ring {ring}{via}"
    return head + (f": Schicht {rp.layer}, Schale {rp.shell}, {rp.kind}" if rp else "")


@dataclass
class _Strand:
    """Offener Strang: Ziele (Sample, Art, Ring) und Ringkommentare in Ausgabereihenfolge."""

    start: int  # Sample am Strangbeginn (Ende der Anfahrt, Stillstand)
    first_ring: int
    last_ring: int
    last_kind: str = "print"
    links: int = 0
    items: list[Comment | tuple[int, str, int]] = field(default_factory=list)

    def target(self, i: int, kind: str, ring: int, P_B: np.ndarray, R_B: np.ndarray | None = None) -> None:  # noqa: N803
        """Ziel anhaengen. Ein Ziel am selben Ort wie das vorige ersetzt dieses nur bei gleicher
        Orientierung (`R_B`, Drehmatrizen in B); dreht sich die Duese dort auf der Stelle (Ausweg
        des Planers, wenn psi am Verbinder der Laenge 0 nicht zu halten ist), bleiben beide Ziele,
        damit das Programm die Drehung so faehrt wie die Trajektorie und nicht auf das Segment davor
        verschmiert."""
        prev = next((it for it in reversed(self.items) if isinstance(it, tuple)), None)
        j = prev[0] if prev else self.start
        same_rot = R_B is None or np.allclose(R_B[i], R_B[j], atol=1e-9)
        if np.linalg.norm(P_B[i] - P_B[j]) < _MERGE_MM and same_rot:
            if prev is None:
                return  # faellt auf den Strangbeginn: kein eigenes Ziel
            self.items.remove(prev)
        self.items.append((i, kind, ring))

    def close(self, P_B: np.ndarray, r_blend_mm: float) -> list[Step]:  # noqa: N803
        """Pumpe an, die Ziele mit Blending (das letzte mit radius 0), Pumpe aus."""
        if self.last_kind == "link":
            raise ValueError(f"Strang endet mit dem Verbinder zu Ring {self.last_ring} statt mit Druck")
        targets = [it for it in self.items if isinstance(it, tuple)]
        if not targets:
            raise ValueError(f"Ring {self.first_ring}: Strang ohne Bewegungsziel")
        pts = [P_B[self.start]] + [P_B[i] for i, _, _ in targets]
        out: list[Step] = [Pump(True, self.first_ring, self.links, len(targets))]
        m = 0
        for it in self.items:
            if isinstance(it, Comment):
                out.append(it)
                continue
            i, kind, ring = it
            if m == len(targets) - 1:
                r = 0.0
            else:
                seg_in = float(np.linalg.norm(pts[m + 1] - pts[m]))
                seg_out = float(np.linalg.norm(pts[m + 2] - pts[m + 1]))
                r = math.floor(min(r_blend_mm, 0.5 * seg_in, 0.5 * seg_out) * 1e4) / 1e4
            out.append(Move("movel", i, kind, ring, r))
            m += 1
        out.append(Pump(False, self.last_ring, self.links, len(targets)))
        return out


def _check_link(
    toolpath: Toolpath,
    P_W: np.ndarray,  # noqa: N803
    cur: int,
    idx: list[int],
    prev_ring: int,
    ring: int,
    tol: float,
) -> None:
    """Verbinder nach spec/ARTEFAKTE.md: r -> r + 1, `link_next` gesetzt, Gerade vom Ende von r
    (letztes Druckziel) zum ersten Wegpunkt von r + 1."""
    if ring != prev_ring + 1 or ring >= len(toolpath.rings):
        raise ValueError(f"Verbinder nach Ring {ring} folgt auf Ring {prev_ring}, erlaubt nur r -> r + 1")
    if not toolpath.rings[prev_ring].link_next:
        raise ValueError(f"Verbinder von Ring {prev_ring} nach {ring}, aber link_next ist nicht gesetzt")
    a = P_W[cur]
    b = np.asarray(toolpath.rings[ring].waypoints[0][:3], dtype=float)
    if np.linalg.norm(P_W[idx[-1]] - b) > tol:
        raise ValueError(f"Verbinder nach Ring {ring} endet nicht am ersten Wegpunkt (Toleranz {tol} mm)")
    ab = b - a
    t = np.clip(((P_W[idx] - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    dev = float(np.linalg.norm(P_W[idx] - (a + t[:, None] * ab), axis=1).max())
    if dev > tol:
        raise ValueError(f"Verbinder nach Ring {ring} weicht {dev:.3f} mm von der Geraden ab")


def plan_steps(
    tr: Trajectory,
    toolpath: Toolpath,
    T_BT: np.ndarray,  # noqa: N803
    T_WB: np.ndarray,  # noqa: N803
    r_blend_mm: float,
    match_tol_mm: float,
) -> list[Step]:
    """Ablaufplan aus der Trajektorie. `T_BT[i]` = FK(q_i) @ T_FT (TCP in B, mm)."""
    n = len(tr.t_s)
    if n == 0:
        raise ValueError("Trajektorie ist leer")
    Q = np.asarray(tr.q, dtype=float)  # noqa: N806
    P_B = T_BT[:, :3, 3]  # noqa: N806
    P_W = P_B @ T_WB[:3, :3].T + T_WB[:3, 3]  # noqa: N806
    kinds, rings = list(tr.kind), list(tr.ring)

    steps: list[Step] = []
    cur = 0
    printed: set[int] = set()
    strand: _Strand | None = None

    def add_move(cmd: Literal["movej", "movel"], i: int) -> None:
        nonlocal cur
        if tr.status[i] == "unreachable":
            raise ValueError(f"Bewegungsziel Sample {i} ist unreachable")
        same = (
            np.max(np.abs(Q[i] - Q[cur])) < _SAME_RAD
            if cmd == "movej"
            else np.linalg.norm(P_B[i] - P_B[cur]) < _SAME_MM
            and np.allclose(T_BT[i, :3, :3], T_BT[cur, :3, :3], atol=1e-9)
        )
        if same and i != 0:
            cur = i
            return
        steps.append(Move(cmd, i, kinds[i], rings[i]))
        cur = i

    def strand_target(i: int) -> None:
        nonlocal cur
        if tr.status[i] == "unreachable":
            raise ValueError(f"Bewegungsziel Sample {i} ist unreachable")
        assert strand is not None
        strand.target(i, kinds[i], rings[i], P_B, T_BT[:, :3, :3])
        cur = i

    steps.append(Comment("Start (Home)"))
    steps.append(Move("movej", 0, kinds[0], rings[0]))
    labeled = None
    for s, e in runs(kinds, rings):
        idx = [i for i in range(s, e + 1) if i > cur]
        if not idx:
            continue
        kind, ring = kinds[s], rings[s]
        if strand is not None and kind not in STRAND_KINDS:
            steps += strand.close(P_B, r_blend_mm)
            strand = None
        if ring != labeled:
            # Zusatz nur bei Druckmustern (opt-in); ohne Muster bleibt der Text wie bisher
            with_note = kind == "link" and toolpath.pattern is not None
            note = link_note(P_W[cur], P_W[idx[-1]]) if with_note else ""
            label = Comment(ring_label(toolpath, ring, via_link=kind == "link", note=note))
            if strand is not None and kind == "link":
                strand.items.append(label)  # im Strang zwischen dem Ende von r und dem Verbinder
            else:
                steps.append(label)
            labeled = ring
        if kind == "transfer":
            for k in linear_breaks(Q[idx], Q[cur], LINEAR_TOL_RAD):
                add_move("movej", idx[k])
        elif kind in CARTESIAN_KINDS:
            for k in linear_breaks(P_B[idx], P_B[cur], LINEAR_TOL_MM):
                add_move("movel", idx[k])
        elif kind == "link":
            if strand is None or strand.last_kind != "print":
                raise ValueError(f"Verbinder nach Ring {ring} steht nicht direkt hinter einem Druckabschnitt")
            _check_link(toolpath, P_W, cur, idx, strand.last_ring, ring, match_tol_mm)
            strand_target(idx[-1])
            strand.links += 1
            strand.last_kind, strand.last_ring = "link", ring
        elif kind == "print":
            if ring in printed:
                raise ValueError(f"Ring {ring}: Druck-Samples nicht zusammenhaengend")
            if not 0 <= ring < len(toolpath.rings):
                raise ValueError(f"Ring {ring} fehlt im Toolpath")
            if strand is None:
                strand = _Strand(start=cur, first_ring=ring, last_ring=ring)
            elif strand.last_kind != "link" or strand.last_ring != ring:
                raise ValueError(f"Ring {ring}: Druck folgt ohne Verbinder auf Ring {strand.last_ring}")
            printed.add(ring)
            cand = [cur, *idx]
            wps = np.asarray(toolpath.rings[ring].waypoints, dtype=float)[:, :3]
            ks = match_waypoints(cand, P_W, wps, match_tol_mm, ring)
            if np.linalg.norm(P_W[idx[-1]] - wps[-1]) > match_tol_mm:
                raise ValueError(f"Ring {ring}: letztes Druck-Sample liegt nicht auf dem Ringende")
            for k in ks:
                if k > 0:
                    strand_target(cand[k])
            strand.last_kind, strand.last_ring = "print", ring
        else:
            raise ValueError(f"unbekannte Sample-Art {kind!r}")
    if strand is not None:
        steps += strand.close(P_B, r_blend_mm)
    missing = sorted(set(range(len(toolpath.rings))) - printed)
    if missing:
        raise ValueError(f"Ringe ohne Druck-Samples: {missing}")
    return steps


__all__ = ["CARTESIAN_KINDS", "STRAND_KINDS", "Comment", "Move", "Pump", "Step", "plan_steps", "ring_label"]

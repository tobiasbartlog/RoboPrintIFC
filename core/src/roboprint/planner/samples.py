"""Bausteine der Teilplanung: Ringaufgabe, Sample-Sammlung, Zustaende zwischen Ringen und Hilfen.

- `RingTask`: ein Druckring in W mit Schicht, Index im Toolpath und `link_next` (SPEC §5.3).
- `Samples`: die dichte Trajektorie in Planungsreihenfolge (je `add` ein Stueck mit Art, Ring, k).
- `Cursor`: Stand nach einem Strangende (Abheben), Ausgangspunkt des naechsten Travels.
- `OpenStrand`: der zuletzt gedruckte Ring eines Strangs, dessen Ende (Abfahren, Abheben) noch
  aussteht, weil ein Verbinder folgen kann.
- `samples_bad`: Hoehensuche, geht ein Stueck nicht (unerreichbar, d < d_hard, Zweigwechsel im Strang)?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .densify import Dense
from .graph import N_BRANCH, RingPath
from .result import IN_STRAND, Tail


@dataclass
class RingTask:
    """Ein Druckring in W: Wegpunkte (geschlossen oder, bei Mustern, offen), Schicht, Index im
    Toolpath, Verbinder erlaubt."""

    index: int
    layer: int
    p_W: np.ndarray  # (n,3)  # noqa: N815
    link_next: bool = False


@dataclass
class Samples:
    q: list[np.ndarray] = field(default_factory=list)
    ok: list[np.ndarray] = field(default_factory=list)
    p_W: list[np.ndarray] = field(default_factory=list)  # noqa: N815
    psi: list[np.ndarray] = field(default_factory=list)
    kind: list[str] = field(default_factory=list)
    ring: list[int] = field(default_factory=list)
    layer: list[int] = field(default_factory=list)
    contacts: list[Any] = field(default_factory=list)
    n: int = 0

    def add(self, d: Dense, kind: str, ring: int, layer: int, contacts: list[Any] | None = None) -> range:
        m = len(d.q)
        self.q.append(d.q)
        self.ok.append(d.ok)
        self.p_W.append(d.p_W)
        self.psi.append(d.psi)
        self.kind += [kind] * m
        self.ring += [ring] * m
        self.layer += [layer] * m
        self.contacts += contacts if contacts is not None else [None] * m
        r = range(self.n, self.n + m)
        self.n += m
        return r


#: Ein Stueck Trajektorie vor dem Anhaengen: (Samples, Art, Ring, k, Kontakte)
Piece = tuple[Dense, str, int, int, list[Any]]


@dataclass
class Cursor:
    """Stand nach einem Strangende: Gelenke, TCP, psi, Zweig (None vor dem ersten Ring), Druckstand k."""

    q: np.ndarray
    p: np.ndarray
    psi: float
    branch: int | None
    k: int


@dataclass
class OpenStrand:
    """Offener Strang: Ring `task` ist gedruckt, sein Abfahren `dr` (Kontakte `cr`) ist geplant, aber
    noch nicht angehaengt. Folgt ein Verbinder, entfaellt es; sonst endet der Strang hier."""

    task: RingTask
    q_end: np.ndarray  # Gelenkstellung am Ringende
    psi_end: float
    dr: Dense
    cr: list[Any]

    @property
    def branch(self) -> int:
        return branch_q(self.q_end)


def samples_bad(q: np.ndarray, ok: np.ndarray, contacts: list[Any], kinds: list[str], d_hard: float) -> bool:
    """Unerreichbar, unter d_hard (Kontakte geprueft) oder Zweigwechsel zwischen Strang-Samples?"""
    if not ok.all():
        return True
    d = np.array([c.d_mm if c is not None else np.inf for c in contacts])
    if bool((d < d_hard).any()):
        return True
    from roboprint.robot import branch_of

    br = np.asarray(branch_of(q), int).reshape(-1)
    inr = np.array([k in IN_STRAND for k in kinds])
    return bool(np.any(inr[1:] & inr[:-1] & (br[1:] != br[:-1])))


def pieces_bad(pieces: list[Piece], d_hard: float) -> bool:
    if not pieces:
        return False
    q = np.vstack([d.q for d, *_ in pieces])
    ok = np.concatenate([d.ok for d, *_ in pieces])
    kinds = [k for d, k, *_ in pieces for _ in range(len(d.q))]
    cons = [c for *_, cs in pieces for c in cs]
    return samples_bad(q, ok, cons, kinds, d_hard)


def tail_of(pieces: list[Piece]) -> Tail:
    """Strangende (Abfahren, Abheben) als `Tail` fuer `truncate`."""
    return Tail(
        q=np.vstack([d.q for d, *_ in pieces]),
        ok=np.concatenate([d.ok for d, *_ in pieces]),
        p_W=np.vstack([d.p_W for d, *_ in pieces]),
        psi=np.concatenate([d.psi for d, *_ in pieces]),
        kind=[k for d, k, *_ in pieces for _ in range(len(d.q))],
        ring=[r for d, _, r, *_ in pieces for _ in range(len(d.q))],
        layer=[k for d, _, _, k, _ in pieces for _ in range(len(d.q))],
        contacts=[c for *_, cs in pieces for c in cs],
    )


def last_ok(d: Dense, fallback: Dense | None, path: RingPath | None, q_default=None) -> np.ndarray:
    for x in (d, fallback):
        if x is not None and x.ok.any():
            return x.q[np.nonzero(x.ok)[0][-1]]
    if q_default is not None:
        return q_default
    if path is not None:
        return path.q[np.nonzero(path.states >= 0)[0][-1]]
    raise ValueError("keine gueltige Gelenkstellung")


def branch_q(q: np.ndarray) -> int:
    from roboprint.robot import branch_of

    return int(branch_of(q))


def reanchor(path: RingPath, q_start: np.ndarray) -> RingPath:
    """Pfad an die tatsaechliche Startstellung (Ende der Anfahrt bzw. des Verbinders) anschliessen."""
    q = path.q.copy()
    q[0] = q_start
    return RingPath(path.states, q, path.psi, path.branch, path.cost, path.restarts)


def branch_order(g) -> list[int]:
    """Zweige nach Anzahl gueltiger Knoten am Ringstart (fuer den Zweigwechsel am Transfer)."""
    v = g.valid[0].reshape(-1, N_BRANCH).sum(0)
    return [int(b) for b in np.argsort(-v) if v[b] > 0]

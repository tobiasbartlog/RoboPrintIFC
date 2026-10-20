"""Ergebnis des Planers fuer ein Teil: Samples mit Status, d_min, Ursache; Praefix eines Plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from roboprint.collision import status_of

from .params import PlannerParams

_IN_RING = frozenset({"approach", "print", "retract"})


@dataclass
class PlannedPath:
    """Ergebnis des Planers fuer ein Teil (vor der Zeitparametrierung)."""

    q: np.ndarray  # (N,6)
    reachable: np.ndarray  # (N,)
    p_W: np.ndarray  # (N,3) Soll-TCP  # noqa: N815
    psi: np.ndarray  # (N,)
    kind: list[str]
    ring: list[int]
    layer: list[int]
    branch: np.ndarray  # (N,)
    contacts: list[Any]  # Contact | None (unreachable)
    status: list[str]
    feasible: bool
    cause: dict[str, Any] | None
    d_min_mm: float | None
    branch_switches_in_rings: int
    timings_s: dict[str, float] = field(default_factory=dict)
    #: Hoehensuche (`stop_at_bad`): Anzahl Schichten von unten, die gehen; sonst None
    layers_ok: int | None = None


def _status(c: Any, ok: bool, p: PlannerParams) -> str:
    if not ok:
        return "unreachable"
    return status_of(c, p.d_target_mm, p.d_target_printed_mm)


def summarize(
    q: np.ndarray,
    ok: np.ndarray,
    p_W: np.ndarray,  # noqa: N803
    psi: np.ndarray,
    kind: list[str],
    ring: list[int],
    layer: list[int],
    contacts: list[Any],
    p: PlannerParams,
    timings: dict[str, float],
) -> PlannedPath:
    """Status, d_min, Zweigwechsel im Ring und erste Ursache zu fertig geprueften Samples."""
    status = [_status(c, o, p) for c, o in zip(contacts, ok, strict=True)]
    from roboprint.robot import branch_of

    branch = np.asarray(branch_of(q), int).reshape(-1)
    d = np.array([c.d_mm if c is not None else np.inf for c in contacts])
    d_min = float(d[np.isfinite(d)].min()) if np.isfinite(d).any() else None
    switches = 0
    for i in range(1, len(q)):
        if kind[i] in _IN_RING and kind[i - 1] in _IN_RING and ring[i] == ring[i - 1]:
            if branch[i] != branch[i - 1] and ok[i] and ok[i - 1]:
                switches += 1
    cause = None
    for i, st in enumerate(status):
        c = contacts[i]
        if st in ("collision", "unreachable") or (c is not None and c.d_mm < p.d_hard_mm):
            if st == "unreachable":
                cause = {
                    "sample": i,
                    "link": "-",
                    "obstacle": "-",
                    "message": f"Sample {i} ({kind[i]}, Ring {ring[i]}): keine Gelenkloesung",
                }
            else:
                cause = {
                    "sample": i,
                    "link": c.pair[0],
                    "obstacle": c.pair[1],
                    "message": f"Sample {i} ({kind[i]}, Ring {ring[i]}, k={layer[i]}): "
                    f"d = {c.d_mm:.1f} mm < d_hard = {p.d_hard_mm:.0f} mm "
                    f"({c.pair[0]} / {c.pair[1]})",
                }
            break
    if cause is None and switches:
        i = next(
            i
            for i in range(1, len(q))
            if kind[i] in _IN_RING and branch[i] != branch[i - 1] and ring[i] == ring[i - 1]
        )
        cause = {
            "sample": i,
            "link": "-",
            "obstacle": "-",
            "message": f"Zweigwechsel im Ring {ring[i]}",
        }
    return PlannedPath(
        q=q,
        reachable=ok,
        p_W=p_W,
        psi=psi,
        kind=kind,
        ring=ring,
        layer=layer,
        branch=branch,
        contacts=contacts,
        status=status,
        feasible=cause is None,
        cause=cause,
        d_min_mm=d_min,
        branch_switches_in_rings=switches,
        timings_s=timings,
    )


def truncate(path: PlannedPath, n: int, p: PlannerParams) -> PlannedPath:
    """Die ersten `n` Samples als eigener, neu bewerteter Pfad (Praefix eines Plans)."""
    return summarize(
        path.q[:n], path.reachable[:n], path.p_W[:n], path.psi[:n], path.kind[:n], path.ring[:n],
        path.layer[:n], path.contacts[:n], p, dict(path.timings_s),
    )  # fmt: skip


__all__ = ["PlannedPath", "summarize", "truncate"]

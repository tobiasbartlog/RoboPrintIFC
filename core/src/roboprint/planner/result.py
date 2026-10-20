"""Ergebnis des Planers fuer ein Teil: Samples mit Status, d_min, Ursache; Praefix eines Plans.

Ein Strang (SPEC §5.3) sind aufeinanderfolgende Samples der Arten `approach`, `print`, `link`,
`retract` ohne Travel dazwischen. Zweigwechsel zaehlen innerhalb eines Strangs (spec/ARTEFAKTE.md,
`zweig_wechsel_in_ringen`), Verbinder-Samples gehoeren zum folgenden Ring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from roboprint.collision import status_of

from .params import PlannerParams

#: Bewegungsarten innerhalb eines Strangs (zwischen zwei Travels)
IN_STRAND = frozenset({"approach", "print", "link", "retract"})


@dataclass
class Tail:
    """Abfahren und Abheben am Ende eines Rings, auf den im Plan ein Verbinder in die naechste
    Schicht folgt. Endet ein Praefix des Plans genau vor diesem Verbinder (Hoehensuche, `truncate`),
    schliesst der Tail den Strang dort ab, wie es die Planung des niedrigeren Teils taete."""

    q: np.ndarray  # (m,6)
    ok: np.ndarray  # (m,)
    p_W: np.ndarray  # (m,3)  # noqa: N815
    psi: np.ndarray  # (m,)
    kind: list[str]
    ring: list[int]
    layer: list[int]
    contacts: list[Any]


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
    #: Strangende je Schichtgrenze mit Verbinder, Schluessel = erstes Sample des Verbinders
    tails: dict[int, Tail] = field(default_factory=dict)


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
    """Status, d_min, Zweigwechsel im Strang und erste Ursache zu fertig geprueften Samples."""
    status = [_status(c, o, p) for c, o in zip(contacts, ok, strict=True)]
    from roboprint.robot import branch_of

    branch = np.asarray(branch_of(q), int).reshape(-1)
    d = np.array([c.d_mm if c is not None else np.inf for c in contacts])
    d_min = float(d[np.isfinite(d)].min()) if np.isfinite(d).any() else None
    sw = [
        i
        for i in range(1, len(q))
        if kind[i] in IN_STRAND and kind[i - 1] in IN_STRAND
        and branch[i] != branch[i - 1] and ok[i] and ok[i - 1]
    ]  # fmt: skip
    switches = len(sw)
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
        i = sw[0]
        cause = {
            "sample": i,
            "link": "-",
            "obstacle": "-",
            "message": f"Zweigwechsel im Strang ({kind[i]}, Ring {ring[i]})",
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
    """Die ersten `n` Samples als eigener, neu bewerteter Pfad (Praefix eines Plans).

    Beginnt bei Sample `n` ein Verbinder in die naechste Schicht, endet der Strang im Praefix mit dem
    zugehoerigen `Tail` (Abfahren, Abheben) statt offen."""
    t = path.tails.get(n)
    if t is None:
        q, ok, pw, psi = path.q[:n], path.reachable[:n], path.p_W[:n], path.psi[:n]
        kind, ring, layer, con = path.kind[:n], path.ring[:n], path.layer[:n], path.contacts[:n]
    else:
        q, ok = np.vstack([path.q[:n], t.q]), np.concatenate([path.reachable[:n], t.ok])
        pw, psi = np.vstack([path.p_W[:n], t.p_W]), np.concatenate([path.psi[:n], t.psi])
        kind, ring = path.kind[:n] + t.kind, path.ring[:n] + t.ring
        layer, con = path.layer[:n] + t.layer, path.contacts[:n] + t.contacts
    out = summarize(q, ok, pw, psi, kind, ring, layer, con, p, dict(path.timings_s))
    out.tails = {k: v for k, v in path.tails.items() if k < n}
    return out


__all__ = ["IN_STRAND", "PlannedPath", "Tail", "summarize", "truncate"]

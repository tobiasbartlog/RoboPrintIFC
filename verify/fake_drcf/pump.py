"""Pumpen- und Strangregeln fuer G5 (SPEC §5.3, §5.6, §11; spec/ARTEFAKTE.md).

Reine Funktionen ueber die vom Fake-Controller aufgezeichneten Bewegungen und Ereignisse und ihre
Zuordnung zu Trajektorien-Samples (`idx[k]` = Sample, das Bewegung k anfaehrt; Bewegung k faehrt die
Samples idx[k-1]+1 .. idx[k]). Ohne Roboter- und Kollisionsmodell, deshalb auch ohne Pinocchio pruefbar.

Regeln:
- Die Pumpe laeuft nur in Straengen: jede Bewegung mit Pumpe faehrt nur `print`- und `link`-Samples, jede
  Bewegung ueber `print`- oder `link`-Samples laeuft mit Pumpe.
- Einschalten nur im Stillstand am Strangbeginn: letzte Bewegung endet auf `approach`, das naechste
  Sample ist `print`, die Bewegung ist synchron mit radius 0.
- Ausschalten nur im Stillstand am Strangende: letzte Bewegung endet auf `print`, das naechste Sample ist
  `retract`, synchron mit radius 0. Damit gibt es kein Pumpe-aus zwischen `print` und `link`.
- Kein Halt im Strang: zwischen zwei Bewegungen mit Pumpe ohne Pumpenwechsel dazwischen hat ein `movel`
  radius > 0 (ausser ein Nachbarsegment ist kuerzer als MIN_SEGMENT_MM). Ein AO-Befehl ohne
  Zustandswechsel (z. B. erneut 5 V bei laufender Pumpe) zaehlt dabei nicht als Wechsel und ist im
  Strang selbst ein Fehler (SPEC §5.6: im Strang nur Pumpe an am Beginn, Pumpe aus am Ende).
- Kein Verweilen mit laufender Pumpe: `wait` (> 0 s) und `mwait` stehen nur als Pumpen-Vorlauf direkt
  nach dem Einschalten (SPEC §5.5). Zwischen zwei Bewegungen mit Pumpe ist auch `mwait(0)` ein Halt;
  im Stillstand am Strangende vor dem Ausschalten ist nur `mwait(0)` erlaubt (kein Verweilen).
- Jeder Wegpunkt aus toolpath.json liegt auf einem Bahnstueck, das mit laufender Pumpe gefahren wird.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

PUMP_KINDS = frozenset({"print", "link"})
WAYPOINT_TOL = 1.0  # mm, Wegpunkt neben der gefahrenen Druckbahn (wie G3)
MIN_SEGMENT_MM = 0.01  # mm, kuerzere Nachbarsegmente erlauben radius 0 (min(r_blend, 1/2 Segment))


def _pump_state(ao: dict) -> bool:
    return any(v > 0 for v in ao.values())


def pump_errors(tag: str, motions: Sequence, events: Sequence[tuple], idx: Sequence[int],
                kind: Sequence[str], pos: np.ndarray) -> list[str]:
    """Pumpenregeln (s. Moduldoku). motions: Objekte mit cmd, radius, sync, line, pump_on;
    events: ("ao", ch, val, n) / ("wait", t, n) / ("mwait", t, n), n = Anzahl Bewegungen davor;
    idx: Sample je Bewegung (vollstaendig zugeordnet); pos: TCP-Positionen je Sample (N,3)."""
    errs: list[str] = []
    N, M = len(kind), len(motions)

    def at(n: int) -> tuple[int | None, str | None, str | None]:
        if n == 0 or idx[n - 1] is None:
            return None, None, None
        i = int(idx[n - 1])
        return i, kind[i], (kind[i + 1] if i + 1 < N else None)

    ao: dict = {}
    on, n_on = False, None
    ao_after: set[int] = set()  # n je Pumpenwechsel (nur echte Zustandswechsel)
    for ev in events:
        if ev[0] == "ao":
            ao[ev[1]] = ev[2]
            now, n = _pump_state(ao), ev[3]
            if now == on:
                if on and 0 < n < M and motions[n - 1].pump_on and motions[n].pump_on:
                    errs.append(f"{tag}: Pumpenbefehl im Strang ohne Zustandswechsel (AO {ev[1]} = "
                                f"{ev[2]:g} V nach Zeile {motions[n - 1].line}); im Strang nur Pumpe an am "
                                "Beginn und aus am Ende")
            else:
                ao_after.add(n)
                i, k_i, k_next = at(n)
                what = "an" if now else "aus"
                if i is None:
                    errs.append(f"{tag}: Pumpe {what} ohne vorherige Bewegung")
                else:
                    if now and not (k_i == "approach" and k_next == "print"):
                        errs.append(f"{tag}: Pumpe an bei Sample #{i} ({k_i} -> {k_next}), nicht am "
                                    "Strangbeginn (approach -> print)")
                    if not now and not (k_i == "print" and k_next == "retract"):
                        errs.append(f"{tag}: Pumpe aus bei Sample #{i} ({k_i} -> {k_next}), nicht am "
                                    "Strangende (print -> retract)")
                    m = motions[n - 1]
                    if m.radius > 0 or not m.sync:
                        errs.append(f"{tag}: vor 'Pumpe {what}' steht der Roboter nicht (radius/asynchron, "
                                    f"Zeile {m.line})")
                n_on = n if now else None
            on = now
        elif ev[0] in ("wait", "mwait") and on:
            t, n = ev[1], ev[2]
            if (ev[0] == "wait" and t <= 0) or n == n_on:
                continue  # wait(0) bzw. Pumpen-Vorlauf t_tot am Strangbeginn
            line = motions[n - 1].line if n > 0 else "?"
            if n < M and motions[n].pump_on:
                errs.append(f"{tag}: Halt im Strang: {ev[0]}({t:g}) zwischen zwei Bewegungen mit Pumpe "
                            f"(nach Zeile {line})")
            elif t > 0:
                errs.append(f"{tag}: Verweilen mit laufender Pumpe: {ev[0]}({t:g}) nicht direkt nach dem "
                            f"Einschalten (nach Zeile {line}); t_tot nur am Strangbeginn")
    for k in range(1, M):
        a, b = idx[k - 1], idx[k]
        if a is None or b is None:
            continue
        kinds = {kind[i] for i in range(a + 1, b + 1)}
        if motions[k].pump_on and kinds - PUMP_KINDS:
            errs.append(f"{tag}: Pumpe an waehrend {sorted(kinds - PUMP_KINDS)} (Zeile {motions[k].line})")
        if not motions[k].pump_on and kinds & PUMP_KINDS:
            errs.append(f"{tag}: Druck- oder Verbinderbewegung ohne Pumpe ({sorted(kinds & PUMP_KINDS)}, "
                        f"Zeile {motions[k].line})")
    for k in range(1, M - 1):
        m = motions[k]
        if (not (m.pump_on and motions[k + 1].pump_on) or (k + 1) in ao_after
                or m.cmd not in ("movel", "amovel") or m.radius > 0):
            continue
        a, b, c = idx[k - 1], idx[k], idx[k + 1]
        if a is None or b is None or c is None:
            continue
        seg = min(float(np.linalg.norm(pos[b] - pos[a])), float(np.linalg.norm(pos[c] - pos[b])))
        if seg >= MIN_SEGMENT_MM:
            errs.append(f"{tag}: Halt im Strang: {m.cmd} mit radius 0 vor einer weiteren Bewegung mit Pumpe "
                        f"(Zeile {m.line}, Sample #{b} {kind[b]})")
    return errs


def waypoint_errors(tag: str, rings_W: Sequence[np.ndarray], pos_W: np.ndarray, kind: Sequence[str],
                    ring: np.ndarray, idx: Sequence[int], pump_on: Sequence[bool]) -> list[str]:
    """Jeder Wegpunkt aus toolpath.json (W, mm) liegt <= WAYPOINT_TOL an einem Bahnstueck seines Rings
    (Ringstart = letztes approach-/link-Sample davor, dann die print-Samples), und die Bewegung, die
    dieses Stueck faehrt, laeuft mit Pumpe."""
    errs: list[str] = []
    kind_a = np.asarray(kind)
    ring_a = np.asarray(ring)
    idx_a = np.asarray([-1 if i is None else int(i) for i in idx])
    for r, W in enumerate(rings_W):
        W = np.asarray(W, dtype=float).reshape(-1, 3)
        sel = np.flatnonzero((ring_a == r) & (kind_a == "print"))
        if not len(W):
            continue
        if not len(sel):
            errs.append(f"{tag}: Ring {r} hat keine Druck-Samples")
            continue
        i0 = int(sel[0])
        if i0 > 0 and kind_a[i0 - 1] in ("approach", "link") and ring_a[i0 - 1] == r:
            sel = np.concatenate([[i0 - 1], sel])
        s = sel[:-1][np.diff(sel) == 1]  # Bahnstuecke s -> s+1
        if not len(s):
            errs.append(f"{tag}: Ring {r} hat keine zusammenhaengende Druckbahn")
            continue
        near, dist = _nearest_segment(W, pos_W[s], pos_W[s + 1])
        bad_far, bad_pump = [], []
        for w, j in enumerate(near):
            if dist[w] > WAYPOINT_TOL:
                bad_far.append(w)
                continue
            k = int(np.searchsorted(idx_a, int(s[j]) + 1, side="left"))
            if k >= len(pump_on) or not pump_on[k]:
                bad_pump.append(w)
        if bad_far:
            w = bad_far[0]
            errs.append(f"{tag}: Ring {r}: {len(bad_far)} Wegpunkte nicht abgefahren, z. B. Nr. {w} "
                        f"{np.round(W[w], 1).tolist()} ({dist[w]:.2f} mm)")
        if bad_pump:
            errs.append(f"{tag}: Ring {r}: {len(bad_pump)} Wegpunkte ohne laufende Pumpe, "
                        f"z. B. Nr. {bad_pump[0]}")
    return errs


def _nearest_segment(P: np.ndarray, A: np.ndarray, B: np.ndarray, block: int = 64):
    """Je Punkt P[w] das naechste Bahnstueck A[j]-B[j]: (Index j (n,), Abstand (n,)), blockweise."""
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-12)
    near = np.zeros(len(P), dtype=int)
    dist = np.zeros(len(P))
    for o in range(0, len(P), block):
        p = P[o:o + block]
        t = np.clip(((p[:, None, :] - A[None]) * AB[None]).sum(2) / L2[None], 0.0, 1.0)
        d = np.linalg.norm(p[:, None, :] - (A[None] + t[..., None] * AB[None]), axis=2)
        near[o:o + block] = d.argmin(1)
        dist[o:o + block] = d.min(1)
    return near, dist

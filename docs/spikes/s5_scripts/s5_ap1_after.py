"""S5-Sonde 5 — AP-1-Nachher-Messung: SDF-Backend vs. FCL-Referenz, je Aufrufort.

Nachher-Haelfte von US 13 der PRD #183 (Issue #215) und die **AP-1-Abnahme**.
Konfigurationsgleich zur Baseline (#206, ``s5_ap1_baseline.py``): dieselbe Bahn
(``denkmal/abschnitt-1``, Modul), derselbe ``DEFAULT_TRAVEL_STRIDE = 5``, dieselbe
verduennte Sample-Auswahl, derselbe Rechner. Neu ist allein das **Backend**: die
Punkt-gegen-Glied-SDF-Inversion (:class:`fgc.collision.sdf_provider.
SdfObstacleProvider`, #213) statt der reinen FCL-Referenz.

**Drift-Vorbehalt (Hinweis aus #206):** die Pipeline ist seit S5 gewandert; die
Absolutzahlen der Baseline sind NICHT zu uebernehmen. Diese Sonde erhebt darum die
**Vorher-Haelfte (FCL) unmittelbar neu** und misst die **Nachher-Haelfte (SDF)**
im selben Prozess auf derselben Auswahl — beide Haelften konfigurationsgleich.

**Y-fach je Aufrufort (der Paper-Beleg):**

  * **Arm↔Hindernis** — ``find_collisions(self_collision=False)``: der Produktiv-
    Befund. Y = Wall(FCL) / Wall(SDF).
  * **Selbstkollision (Arm↔Arm)** — der reine Selbstkollisions-Block, isoliert als
    Wall(self=True) − Wall(self=False) je Backend. Y = FCL_self / SDF_self.

**Befund-Identitaet (der #213-Regressionsanker):** der Speedup gilt NUR, wenn FCL
und SDF **denselben** Befund liefern (rot/gelb/gruen, min-Distanz, worst_index) —
sonst misst man zwei verschiedene Urteile. Das Skript prueft die Identitaet je
self-Konfiguration als Gate; nur sicher-gruene Abstandszahlen duerfen (beiderseits
konservativ) abweichen, die rot/gelb-Befunde muessen byte-identisch sein (US 2/16).

**Budget-Ableitung (Grill-Verfahren 2026-07-14):** aus der SDF-Zeit des Produktiv-
Aufrufs (self=False) wird das Default-Aufruf-Kontingent abgeleitet — die groesste
runde Aufruf-Zahl, deren Hintergrundlauf ≤ ~5 min (300 s) auf der Referenzmaschine
bleibt. Der Wert wird als Konstante ``fgc.decompose.propose.DEFAULT_CALL_BUDGET``
festgeschrieben (die Beam-Suche #217 konsumiert ihn).

Aufruf (venv, Repo-Root)::

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_ap1_after.py

Schreibt ``docs/spikes/s5_scripts/last_ap1_after.json``.
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from pathlib import Path

from s5_harness import build_inputs

OUT = Path(__file__).resolve().parent / "last_ap1_after.json"

#: Wiederholungen der Wall-Zeit-Messung fuer die billige self=False-Konfiguration.
N_TIMING_REPEATS = 3

#: Budget-Zielzeit (s) des Grill-Verfahrens: ~5 min Hintergrundlauf.
BUDGET_TARGET_S = 300.0


def _thin(inp, stride: int):
    """Verduennte Sample-Auswahl wie der Realpfad (``thin_travel_indices``)."""
    from fgc.collision.finding import thin_travel_indices

    kept = thin_travel_indices(inp.sample_is_travel, int(stride))
    link_frames = [inp.link_frames[i] for i in kept]
    sample_layers = [inp.sample_layers[i] for i in kept]
    return kept, link_frames, sample_layers


def _fcl_provider(inp):
    """Frische FCL-Referenz (schlichter Callable → bisheriger Pfad)."""
    return inp.provider_factory()


def _sdf_provider(inp):
    """Frischer SdfObstacleProvider konfigurationsgleich zur FCL-Referenz (#213).

    Baut denselben Druckstand-Spec wie die FCL-Referenz (derselbe Nachpruefer-Satz)
    und traegt zusaetzlich die SDF-Abfrageflaechen. Fehlt das Glied-SDF-Artefakt,
    faellt ``obstacle_provider_for`` soft auf FCL zurueck — hier wird direkt gebaut,
    damit ein Fehlbestand als Fehler auffaellt statt still zu FCL zu werden.
    """
    from fgc.collision.glied_sdf import load_glied_sdf
    from fgc.collision.sdf_provider import SdfObstacleProvider

    glied = load_glied_sdf(inp.robot_name)
    return SdfObstacleProvider(inp.druckstand_spec, glied, inp.geo)


def _run(inp, provider, link_frames, sample_layers, *, self_collision: bool):
    """Echtes ``find_collisions`` → (counts, wall_s). Provider frisch je Aufruf."""
    from fgc.collision import check as C

    t0 = time.perf_counter()
    rep = C.find_collisions(
        inp.geo,
        inp.base,
        link_frames,
        sample_layers,
        provider,
        tcp_frame=inp.tcp_frame,
        tool_hull=inp.tool_hull,
        safety_distance_mm=inp.safety_distance_mm,
        self_collision=self_collision,
    )
    wall = time.perf_counter() - t0
    counts = {
        "n_samples": len(link_frames),
        "n_red": rep.n_red,
        "n_yellow": rep.n_yellow,
        "n_green": rep.n_green,
        "min_distance_mm": round(rep.min_distance_mm, 3),
        "worst_index": rep.worst_index,
    }
    return counts, wall


def _findings_identical(a: dict, b: dict, safety_mm: float) -> bool:
    """Befund-Identitaet nach dem #213-Regressionsanker (US 2/16).

    Byte-identisch verlangt sind die **Ampel-Zaehlwerte** (rot/gelb/gruen). Fuer den
    **worst**-Befund (min-Distanz < Sicherheitsabstand ⇒ rot oder gelb) zusaetzlich
    Verursacher-Sample (``worst_index``) und Eindringtiefe (``min_distance_mm``). Nur
    **sicher-gruene** Abstandszahlen (min ≥ Sicherheitsabstand) duerfen beiderseits
    konservativ abweichen — dort ist der worst-Wert eine gekappte untere Schranke,
    kein Urteil.
    """
    if (a["n_red"], a["n_yellow"], a["n_green"]) != (b["n_red"], b["n_yellow"], b["n_green"]):
        return False
    if a["min_distance_mm"] < safety_mm or b["min_distance_mm"] < safety_mm:
        if abs(a["min_distance_mm"] - b["min_distance_mm"]) >= 1e-3:
            return False
        if a["worst_index"] != b["worst_index"]:
            return False
    return True


def _round_budget(per_call_s: float, target_s: float) -> int:
    """Groesste RUNDE Aufruf-Zahl mit ``n * per_call ≤ target`` (Grill-Verfahren)."""
    raw = int(target_s // per_call_s)
    if raw < 1:
        return 0
    # Groesste runde Zahl ≤ raw: 1er/2er/5er-Leiter je Dekade (1,2,5,10,20,50,…).
    import math

    decade = 10 ** int(math.floor(math.log10(raw)))
    for mult in (5, 2, 1):
        cand = mult * decade
        if cand <= raw:
            return cand
    return decade


def main() -> None:
    inp = build_inputs()

    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE

    stride = int(DEFAULT_TRAVEL_STRIDE)
    kept, tf, tl = _thin(inp, stride)

    # === Determinismus-Gate (billige self=False-Konfig, je Backend zweimal). =====
    fcl_d1, _ = _run(inp, _fcl_provider(inp), tf, tl, self_collision=False)
    fcl_d2, _ = _run(inp, _fcl_provider(inp), tf, tl, self_collision=False)
    sdf_d1, _ = _run(inp, _sdf_provider(inp), tf, tl, self_collision=False)
    sdf_d2, _ = _run(inp, _sdf_provider(inp), tf, tl, self_collision=False)
    det_fcl = fcl_d1 == fcl_d2
    det_sdf = sdf_d1 == sdf_d2
    print(f"Determinismus FCL: {'OK' if det_fcl else 'FEHLER'}  {fcl_d1}")
    print(f"Determinismus SDF: {'OK' if det_sdf else 'FEHLER'}  {sdf_d1}")

    # === Befund-Identitaet (self=False, der #213-Regressionsanker). ==============
    ident_false = _findings_identical(fcl_d1, sdf_d1, inp.safety_distance_mm)
    print(f"Befund-Identitaet self=False FCL==SDF: {'OK' if ident_false else 'FEHLER'}")

    # === Wall-Zeiten Arm↔Hindernis (self=False, N Wiederholungen, frisch). =======
    fcl_false = []
    for _ in range(N_TIMING_REPEATS):
        _, w = _run(inp, _fcl_provider(inp), tf, tl, self_collision=False)
        fcl_false.append(w)
    sdf_false = []
    for _ in range(N_TIMING_REPEATS):
        _, w = _run(inp, _sdf_provider(inp), tf, tl, self_collision=False)
        sdf_false.append(w)

    # === Wall-Zeiten mit Selbstkollision (self=True, je EIN Lauf — teuer). =======
    fcl_true_counts, w_fcl_true = _run(inp, _fcl_provider(inp), tf, tl, self_collision=True)
    sdf_true_counts, w_sdf_true = _run(inp, _sdf_provider(inp), tf, tl, self_collision=True)
    ident_true = _findings_identical(fcl_true_counts, sdf_true_counts, inp.safety_distance_mm)
    print(f"Befund-Identitaet self=True  FCL==SDF: {'OK' if ident_true else 'FEHLER'}")

    fcl_false_med = statistics.median(fcl_false)
    sdf_false_med = statistics.median(sdf_false)
    fcl_false_min = min(fcl_false)
    sdf_false_min = min(sdf_false)

    # Selbstkollisions-Block isoliert: Wall(self=True) − Wall(self=False, Median).
    fcl_self_only = w_fcl_true - fcl_false_med
    sdf_self_only = w_sdf_true - sdf_false_med

    def yfold(fcl, sdf):
        return round(fcl / sdf, 2) if sdf > 0 else None

    # === Budget (Grill-Verfahren): SDF-Zeit des Produktiv-Aufrufs (self=False). ==
    per_call_s = sdf_false_med
    budget = _round_budget(per_call_s, BUDGET_TARGET_S)

    out = {
        "config": {
            "spike": "S5/AP-1-Nachher-Messung + Abnahme (Issue #215)",
            "baseline_ref": "docs/spikes/S5b_ap1_baseline_verduennt.md (Issue #206)",
            "reproduction": "slice_and_simulate_section('denkmal','abschnitt-1') → find_collisions",
            "travel_stride": stride,
            "safety_distance_mm": inp.safety_distance_mm,
            "freizone_radius_mm": 40.0,
            "decomposition_kind": "modul",
            "n_samples_thinned": len(kept),
            "n_layers": inp.n_layers,
            "tool_hull": inp.tool_hull is not None,
            "robot": inp.robot_name,
            "backend_after": "sdf (SdfObstacleProvider, #213)",
            "n_timing_repeats": N_TIMING_REPEATS,
            "machine": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor(),
            },
        },
        "determinism": {"fcl": det_fcl, "sdf": det_sdf},
        "befund_identitaet": {
            "self_false": ident_false,
            "self_true": ident_true,
            "counts_self_false_fcl": fcl_d1,
            "counts_self_false_sdf": sdf_d1,
            "counts_self_true_fcl": fcl_true_counts,
            "counts_self_true_sdf": sdf_true_counts,
            "note": "#213-Regressionsanker: rot/gelb + worst_index byte-identisch; "
            "der Speedup gilt nur mit identischen Befunden.",
        },
        "callsite_arm_obstacle": {
            "self_collision": False,
            "fcl_wall_s": {
                "runs": [round(w, 3) for w in fcl_false],
                "min": round(fcl_false_min, 3),
                "median": round(fcl_false_med, 3),
            },
            "sdf_wall_s": {
                "runs": [round(w, 3) for w in sdf_false],
                "min": round(sdf_false_min, 3),
                "median": round(sdf_false_med, 3),
            },
            "yfold_fcl_over_sdf_median": yfold(fcl_false_med, sdf_false_med),
            "yfold_fcl_over_sdf_min": yfold(fcl_false_min, sdf_false_min),
        },
        "callsite_self_collision": {
            "note": "Reiner Arm↔Arm-Block isoliert: Wall(self=True) − Wall(self=False).",
            "fcl_wall_self_true_s": round(w_fcl_true, 3),
            "sdf_wall_self_true_s": round(w_sdf_true, 3),
            "fcl_self_only_s": round(fcl_self_only, 3),
            "sdf_self_only_s": round(sdf_self_only, 3),
            "yfold_fcl_over_sdf": yfold(fcl_self_only, sdf_self_only),
        },
        "budget": {
            "verfahren": "groesste runde Aufruf-Zahl mit n*per_call ≤ target (Grill 2026-07-14)",
            "per_call_s_sdf_self_false_median": round(per_call_s, 3),
            "target_s": BUDGET_TARGET_S,
            "raw_max_calls": int(BUDGET_TARGET_S // per_call_s),
            "default_call_budget": budget,
            "predicted_run_s": round(budget * per_call_s, 1),
        },
    }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=True))
    print(f"\ngeschrieben: {OUT}")
    if not (det_fcl and det_sdf and ident_false and ident_true):
        raise SystemExit("Gate fehlgeschlagen (Determinismus oder Befund-Identitaet).")


if __name__ == "__main__":
    main()

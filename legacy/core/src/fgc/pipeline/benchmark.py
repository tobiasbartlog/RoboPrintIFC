"""fgc.pipeline.benchmark — produktive Verdrahtung des Benchmark-Harness (Issue #220, PRD #183).

Die **geometrie-behaftete Haelfte** des Benchmarks (der reine Harness liegt in
:mod:`fgc.decompose.benchmark`): sie faehrt die Arme **Greedy** (#165),
**Beam** (#217) und — nur bei bestandenem Sollbruch-Gate — **Beam+Surrogat** (#219)
ueber die eine produktive Tuer :func:`fgc.pipeline.actions.propose_decomposition`,
laedt das Surrogat-Modell fuers Gate, schnuert das **Protokoll** mit Provenienz
(ADR-004) und legt es ab.

Alle Arme laufen auf **demselben eingefrorenen Stand** (Projekt/Druckjob, Roboter,
Zielfunktion, Aufruf-Kontingent) — **byte-vergleichbar** ueber die Lauf-Provenienz,
ausschliesslich CPU. Der **vierte Arm Beam+GPU** entfaellt, solange #205-G2 nicht
integriert ist (:func:`fgc.pipeline.kampagne.gpu_available` ⇒ ``False``, im Protokoll
dokumentiert, nie stillschweigend).

**Sollbruch-Gate (mechanisch, Grill 2026-07-14):** :func:`load_surrogat_gate` laedt
das Modell (fail-soft bei Abwesenheit, streng-dann-fail-soft-dokumentiert bei
Fehlprovenienz) und laesst den dritten Arm **nur** zu, wenn das Modell v1-policy-konform
ist, das Invarianz-Orakel gruen hat und als Provenienz-Artefakt vorliegt — sonst
zweiarmig, **ohne Warten, ohne Wiederholung**.

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fgc.decompose.benchmark import (
    ARM_BEAM,
    ARM_BEAM_SURROGAT,
    ARM_GREEDY,
    REASON_MODELL_UNGUELTIG,
    ArmRun,
    ArmRunner,
    BenchmarkCase,
    GateDecision,
    SurrogatGateResult,
    benchmark_protocol,
    decide_arms,
    run_arms,
    surrogat_gate,
)
from fgc.decompose.propose import DEFAULT_CALL_BUDGET
from fgc.pipeline.provenance import make_provenance

_LOG = logging.getLogger(__name__)

__all__ = [
    "BenchmarkResult",
    "load_surrogat_gate",
    "make_arm_runner",
    "run_benchmark",
]


def load_surrogat_gate(model_path: Path | None) -> SurrogatGateResult:
    """Laedt das Surrogat-Modell und faellt das **mechanische** Sollbruch-Gate (#220).

    ``None``/fehlende Datei ⇒ kein Modell ⇒ zweiarmig (fail-soft, US 12). Ein
    **vorhandenes, aber provenienz-falsches** Artefakt wirft in
    :func:`fgc.decompose.surrogat.load_surrogat` (US 26) — der Benchmark **wartet nicht
    und wiederholt nicht**, sondern dokumentiert es als ``modell-ungueltig`` und laeuft
    zweiarmig weiter (der Gate-Entscheid ist nie stillschweigend). Sonst prueft
    :func:`fgc.decompose.benchmark.surrogat_gate` v1-Policy-Konformitaet + Invarianz-Orakel.
    """
    from fgc.decompose.surrogat import load_surrogat

    try:
        model = load_surrogat(model_path)
    except ValueError:
        _LOG.warning("Surrogat-Modell %s provenienz-ungueltig — Benchmark zweiarmig.", model_path)
        return SurrogatGateResult(
            ok=False,
            reason=REASON_MODELL_UNGUELTIG,
            checks={
                "modell_vorhanden": True,
                "v1_policy_konform": False,
                "invarianz_orakel_gruen": False,
            },
        )
    return surrogat_gate(model)


def make_arm_runner(
    source: str,
    *,
    model: Any | None = None,
    call_budget: int = DEFAULT_CALL_BUDGET,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
    robots_dir: Path | None = None,
) -> ArmRunner:
    """Baut den **produktiven** Arm-Laeufer: ``(arm, case) → ArmRun`` via ``propose_decomposition``.

    Jeder Arm faehrt dieselbe Tuer (:func:`fgc.pipeline.actions.propose_decomposition`) mit
    demselben Kontingent auf demselben Druckjob — nur der Strategie-Schalter unterscheidet:
    **Greedy** ``refine_collisions=True``, **Beam** ``beam_search=True``, **Beam+Surrogat**
    ``beam_search=True, surrogat=model``. Der Laeufer liest den persistierten Lauf
    (``decompose.json``) und gibt ihn als :class:`ArmRun` zurueck — die Auswertung rechnet
    daraus, nie neu (US 20).
    """
    from fgc.pipeline.actions import propose_decomposition

    def runner(arm: str, case: BenchmarkCase) -> ArmRun:
        payload = case.payload or {}
        slug = payload["slug"]
        job_id = payload.get("job_id", "default")
        kwargs: dict[str, Any] = {
            "call_budget": call_budget,
            "projects_dir": projects_dir,
            "runs_dir": runs_dir,
            "workstations_dir": workstations_dir,
            "robots_dir": robots_dir,
        }
        if arm == ARM_GREEDY:
            result = propose_decomposition(slug, source, job_id, refine_collisions=True, **kwargs)
        elif arm == ARM_BEAM:
            result = propose_decomposition(slug, source, job_id, beam_search=True, **kwargs)
        elif arm == ARM_BEAM_SURROGAT:
            result = propose_decomposition(
                slug, source, job_id, beam_search=True, surrogat=model, **kwargs
            )
        else:
            raise ValueError(f"Unbekannter Benchmark-Arm {arm!r}.")
        doc = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
        return ArmRun(
            arm=arm, case_id=case.case_id, doc=doc, run_dir=str(result.run_dir.resolve())
        )

    return runner


@dataclass
class BenchmarkResult:
    """Ergebnis von :func:`run_benchmark`: Protokoll-Pfad + Artefakt + Gate + Laeufe."""

    protocol_path: Path
    protocol: dict[str, Any]
    gate: GateDecision
    runs: list[ArmRun]


def run_benchmark(
    slug: str,
    source: str,
    out_path: Path,
    *,
    job_id: str = "default",
    model_path: Path | None = None,
    call_budget: int = DEFAULT_CALL_BUDGET,
    robot_name: str = "doosan_m1013",
    cases: list[BenchmarkCase] | None = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
    robots_dir: Path | None = None,
) -> BenchmarkResult:
    """Faehrt den Benchmark end-to-end und legt das **Protokoll** ab (Acceptance #220).

    1. **Sollbruch-Gate** (:func:`load_surrogat_gate`): entscheidet zwei-/drei-/vierarmig,
       **ohne Warten/Wiederholung** — der vierte Arm entfaellt (``gpu_available`` ⇒ ``False``).
    2. **Arme** (:func:`fgc.decompose.benchmark.run_arms`) auf **demselben eingefrorenen
       Stand** (Projekt/Druckjob, Roboter, Zielfunktion, Kontingent) — je Arm ein
       persistierter Lauf mit voller Provenienz (Strategie/Modell/Kontingent/Zielfunktion).
    3. **Protokoll** (:func:`fgc.decompose.benchmark.benchmark_protocol`): Gate-Entscheid
       (nie stillschweigend) + eingefrorener Stand + Auswertung **aus den Laufartefakten**
       (kein Nachrechnen). Nach ``out_path`` geschrieben (ADR-004, sortiert fuer den
       Byte-Vergleich).

    Ohne ``cases`` wird **ein** Fall aus ``slug``/``job_id`` gebildet (der Druckjob ist der
    eingefrorene Stand). ``call_budget`` pinnt das Kontingent fuer **alle** Arme (US 25).
    Der eigentliche Lauf ist teuer (CPU-exakte Pruef-Tuer je Arm) — die Selbstpruefung faehrt
    ihn nur mit Mini-Stichproben (Test-Protokoll #220).
    """
    from fgc.decompose.surrogat import load_surrogat
    from fgc.pipeline.kampagne import gpu_available

    gate_surrogat = load_surrogat_gate(model_path)
    gate = decide_arms(gate_surrogat, gpu_ready=gpu_available())

    model = load_surrogat(model_path) if gate_surrogat.ok else None
    if cases is None:
        cases = [
            BenchmarkCase(case_id=f"{slug}:{job_id}", payload={"slug": slug, "job_id": job_id})
        ]

    runner = make_arm_runner(
        source,
        model=model,
        call_budget=call_budget,
        projects_dir=projects_dir,
        runs_dir=runs_dir,
        workstations_dir=workstations_dir,
        robots_dir=robots_dir,
    )
    runs = run_arms(cases, gate.arms, runner)

    provenance = make_provenance(source)
    protocol = benchmark_protocol(
        gate, cases, runs, provenance, call_budget=call_budget, robot_name=robot_name
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(protocol, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return BenchmarkResult(protocol_path=out_path, protocol=protocol, gate=gate, runs=runs)

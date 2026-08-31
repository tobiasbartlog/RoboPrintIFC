"""fgc.decompose.benchmark — der **Benchmark-Harness** fuers Vergleichspaper (Issue #220, PRD #183).

Der Harness stellt die Zerlegungs-**Arme** auf **demselben eingefrorenen Stand**
gegeneinander: **Greedy** (kollisionsgetriebene Verfeinerung #165), **Beam** (#217)
und **Beam+Surrogat** (#219) — an derselben #216-Strategie-Naht, also
**byte-vergleichbar** ueber die ADR-004-Provenienz, ausschliesslich CPU. Ein
optionaler **vierter Arm Beam+GPU-Vorsortierer** laeuft nach demselben Zug-Prinzip
(nur falls #205-G2 samt Toleranzschema fertig ist — heute nicht, also entfaellt er,
blockiert nie).

**Sollbruch-Gate (Grill 2026-07-14, mechanisch).** Der dritte Arm laeuft **nur**,
wenn beim Start ein Surrogat-Modell existiert, das (1) **v1-policy-konform** trainiert
ist (nur ``cpu-exakt`` + ``gpu+cpu-grenzband``, #205-G1), (2) das **Invarianz-Orakel
gruen** hat (mit/ohne Vorsortierer identischer Sieger + Urteil, US 25) und (3) als
**Artefakt mit Provenienz** vorliegt (Merkmals-Version/-Liste, Datensatz-Stand). Fehlt
eine Bedingung, laeuft der Benchmark **zweiarmig — ohne Warten, ohne Wiederholung**.
Der Gate-Entscheid (zwei-/drei-/vierarmig) wird **nie stillschweigend** getroffen:
:meth:`GateDecision.to_dict` haelt Grund je Arm fest (:func:`decide_arms`).

**Auswertung ausschliesslich aus persistierten Laufartefakten (US 20/21/27).** Die
Kennzahlen kommen **nur** aus den ``decompose.json``-Artefakten der Arme
(:func:`evaluate_run`) — **kein Nachrechnen** von Geometrie. Wiederholung ⇒
**byte-gleiche Kennzahlen** (CPU-Arme): :func:`benchmark_kennzahlen` sammelt genau
die deterministischen Felder (Teilanzahl, c_v, Fugenflaeche, erreichbarer Anteil,
geprueft-frei-Anteil, Standplaetze, Verworfen-Gruende), die reine **Rechenzeit**
(diagnostisch, maschinenabhaengig, US 25) bleibt getrennt in ``diagnostik`` und
**nicht** Teil des Byte-Vergleichs.

Dieses Modul ist die **reine Haelfte** des Harness: Gate, Auswertung, Protokoll —
ohne Geometrie, mit **injizierbarem Arm-Laeufer** (:data:`ArmRunner`, Muster wie das
Kampagnen-Orakel #218/#190). Die produktive Verdrahtung (Arme ueber
:func:`fgc.pipeline.actions.propose_decomposition`, Modell-Gate, Protokoll-Ablage)
liegt in :mod:`fgc.pipeline.benchmark`.

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ARM_BEAM",
    "ARM_BEAM_GPU",
    "ARM_BEAM_SURROGAT",
    "ARM_GREEDY",
    "BASE_ARMS",
    "BENCHMARK_KIND",
    "BENCHMARK_SCHEMA_VERSION",
    "ArmRun",
    "ArmRunner",
    "BenchmarkCase",
    "GateDecision",
    "SurrogatGateResult",
    "benchmark_kennzahlen",
    "benchmark_protocol",
    "decide_arms",
    "evaluate_run",
    "mechanical_invariance_check",
    "run_arms",
    "surrogat_gate",
]

# --- Die Arme (feste Kennungen, feste Reihenfolge fuers Protokoll) -----------

#: Arm 1: die **kollisionsgetriebene Verfeinerung** (#165) — der Greedy an der
#: #216-Naht (Strategiename ``kollisionsgetriebene-verfeinerung``).
ARM_GREEDY = "greedy"
#: Arm 2: die **Beam-Suche** (#217) ohne Vorsortierer.
ARM_BEAM = "beam"
#: Arm 3: **Beam+Surrogat** (#219) — nur bei bestandenem Sollbruch-Gate.
ARM_BEAM_SURROGAT = "beam+surrogat"
#: Arm 4 (optional): **Beam+GPU-Vorsortierer** — nur falls #205-G2 fertig (heute nicht).
ARM_BEAM_GPU = "beam+gpu"

#: Die **immer** verfuegbaren CPU-Arme (das zweiarmige Minimum, Grill 2026-07-14):
#: ohne Modell und ohne GPU laeuft der Benchmark exakt hiermit.
BASE_ARMS: tuple[str, ...] = (ARM_GREEDY, ARM_BEAM)

#: Artefakt-Kennung + Schema-Version des Benchmark-Protokolls (ADR-004).
BENCHMARK_KIND = "benchmark-protocol"
BENCHMARK_SCHEMA_VERSION = "1"

#: Grund-Codes des Gate-Entscheids (nie stillschweigend, Acceptance #220).
REASON_KEIN_MODELL = "kein-modell"
REASON_MODELL_UNGUELTIG = "modell-ungueltig"
REASON_INVARIANZ_ROT = "invarianz-orakel-rot"
REASON_GATE_GRUEN = "gate-gruen"
REASON_GPU_NICHT_FERTIG = "gpu-vorsortierer-nicht-fertig"  # #205-G2 entfaellt


# --------------------------------------------------------------------------- #
# Sollbruch-Gate (mechanisch, Grill 2026-07-14)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SurrogatGateResult:
    """Der mechanische Gate-Befund fuer den dritten Arm (Beam+Surrogat, #219).

    ``ok`` ⇒ der Arm laeuft; ``reason`` benennt den Grund **immer** (auch bei ``ok``),
    ``model_stamp`` traegt den Modellstand (Datensatz/Seed/Merkmalsliste) fuers
    Protokoll, ``checks`` das Ergebnis der drei Einzelpruefungen (v1-policy-konform,
    Provenienz-Artefakt, Invarianz-Orakel gruen).
    """

    ok: bool
    reason: str
    model_stamp: dict[str, Any] | None = None
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "model_stamp": self.model_stamp,
            "checks": dict(self.checks),
        }


def surrogat_gate(
    model: Any | None,
    *,
    invariance_check: Callable[[Any], bool] | None = None,
) -> SurrogatGateResult:
    """Entscheidet **mechanisch**, ob der dritte Arm (Beam+Surrogat) laufen darf (#220).

    Prueft der Reihe nach — und bricht beim ersten Fehlschlag ab, ohne zu warten
    (Grill 2026-07-14: kein Datum, kein Retry):

    1. **Modell vorhanden?** ``model is None`` (kein Artefakt / Ladefehler
       fail-soft, US 12) ⇒ zweiarmig (``reason=kein-modell``). Der Aufrufer laedt das
       Modell ueber :func:`fgc.decompose.surrogat.load_surrogat` — ein **vorhandenes,
       aber provenienz-falsches** Artefakt wirft dort bereits (nie ein stiller
       Fehlkomparator, US 26).
    2. **v1-policy-konform + Provenienz-Artefakt?** Der Modellstand traegt eine
       trainingstaugliche Merkmals-Version, eine nicht-leere Merkmalsliste und einen
       Trainings-Ausweis, der **ausschliesslich** aus ``cpu-exakt`` + ``gpu+cpu-grenzband``
       gelernt hat (``label_source_distribution_used`` ⊆ Trainings-Quellen, kein
       Audit-Rest) — sonst ``reason=modell-ungueltig``.
    3. **Invarianz-Orakel gruen?** ``invariance_check(model)`` (produktiv
       :func:`mechanical_invariance_check`) belegt am Beam-Lauf, dass der Vorsortierer
       Sieger + Urteil **nicht** aendert (US 25) — sonst ``reason=invarianz-orakel-rot``.

    Nur wenn **alle drei** halten, ist ``ok=True`` (``reason=gate-gruen``).
    """
    checks: dict[str, bool] = {
        "modell_vorhanden": False,
        "v1_policy_konform": False,
        "invarianz_orakel_gruen": False,
    }
    if model is None:
        return SurrogatGateResult(ok=False, reason=REASON_KEIN_MODELL, checks=checks)
    checks["modell_vorhanden"] = True

    stamp = _model_stamp(model)
    if not _v1_policy_konform(model, stamp):
        return SurrogatGateResult(
            ok=False, reason=REASON_MODELL_UNGUELTIG, model_stamp=stamp, checks=checks
        )
    checks["v1_policy_konform"] = True

    checker = mechanical_invariance_check if invariance_check is None else invariance_check
    try:
        gruen = bool(checker(model))
    except Exception:  # noqa: BLE001 — ein defektes Modell ist ein rotes Orakel, kein Absturz
        gruen = False
    if not gruen:
        return SurrogatGateResult(
            ok=False, reason=REASON_INVARIANZ_ROT, model_stamp=stamp, checks=checks
        )
    checks["invarianz_orakel_gruen"] = True

    return SurrogatGateResult(ok=True, reason=REASON_GATE_GRUEN, model_stamp=stamp, checks=checks)


def _model_stamp(model: Any) -> dict[str, Any] | None:
    """Der Modellstand fuer Gate + Protokoll — duck-typed ueber ``stamp()``."""
    stamp = getattr(model, "stamp", None)
    if callable(stamp):
        try:
            got = stamp()
            return dict(got) if isinstance(got, dict) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _v1_policy_konform(model: Any, stamp: dict[str, Any] | None) -> bool:
    """Die v1-Policy-Konformitaet aus dem **persistierten** Modellstand + Ausweis (#220).

    Verlangt: (a) eine nicht-leere Merkmalsliste + Merkmals-Version im Stamp
    (Provenienz-Artefakt), und (b) einen Trainings-Ausweis, der ausschliesslich aus den
    Trainings-Quellen (:data:`fgc.decompose.kampagne.TRAINING_LABEL_SOURCES`) gelernt hat
    — nie mit einem ``gpu+stichproben-audit``-Rest (Policy v1, Grill 2026-07-14).
    """
    from fgc.decompose.kampagne import TRAINING_LABEL_SOURCES

    if not stamp:
        return False
    if not stamp.get("features") or not stamp.get("feature_version"):
        return False
    training = getattr(model, "training", None)
    if not isinstance(training, dict):
        return False
    dist = training.get("label_source_distribution_used")
    if not isinstance(dist, dict) or not dist:
        return False
    used_sources = {src for src, n in dist.items() if n}
    return bool(used_sources) and used_sources <= set(TRAINING_LABEL_SOURCES)


def mechanical_invariance_check(model: Any) -> bool:
    """Der **mechanische** Invarianz-Orakel-Lauf fuers Gate (US 25, #220).

    Faehrt die Beam-Suche auf einem kleinen, **deterministischen** synthetischen Szenario
    **mit** und **ohne** den Vorsortierer und belegt, dass sich der Sieger (Schnitt + je
    Reihe gewaehlte Option) und das Urteil (geprueft-frei / leerer Fall) **nicht** aendern.
    Kein Geometrie-Stack, keine Karte — reine Strategie-Einheit an der #216-Naht (dasselbe
    Muster wie ``test_surrogat``). Reordnet der Vorsortierer etwas Anderes als die
    Reihenfolge, faellt der Test rot und das Gate laesst den dritten Arm nicht zu.
    """
    from fgc.decompose.beam import BeamSuche
    from fgc.decompose.kandidaten import band_raster_kandidaten
    from fgc.decompose.objective import KriterienWerte, ObjectiveConfig
    from fgc.decompose.scorer import KandidatBewertung
    from fgc.decompose.strategie import RasterAufgabe
    from fgc.placement import WallSurface

    wall = WallSurface(length_mm=800.0, height_mm=1000.0, thickness_mm=200.0)
    cap = 2
    kandidaten = band_raster_kandidaten(wall, cap=cap)

    def bewerte(kandidat: Any) -> KandidatBewertung:
        werte = KriterienWerte(
            erreichbar=True,
            umsetzvorgaenge=float(kandidat.n_height),
            fugenflaeche_mm2=float((kandidat.n_length - 1) + (kandidat.n_height - 1)) * 1000.0,
            kinematische_marge_mm=100.0,
            volumen_cv=0.0,
        )
        return KandidatBewertung(
            kandidat=kandidat,
            werte=werte,
            reihen_gedeckt=tuple(True for _ in range(kandidat.n_height)),
            standplaetze=(),
            inseln_je_teil=tuple(1 for _ in range(kandidat.n_parts)),
        )

    class _Befund:
        def __init__(self, collides: bool) -> None:
            self.collides = collides
            self.causer_position_mm = (0.0, 0.0, 0.0) if collides else None

    def pruef_tuer(kandidat: Any, _row: int, _opt: Any) -> Any:
        # Nur geteilte Hoehe (n_height >= 2) ist frei — die Suche muss verfeinern,
        # sodass die Pruef-Reihenfolge (und ihre Umordnung) wirklich zaehlt.
        return _Befund(collides=kandidat.n_height < 2)

    def _aufgabe() -> RasterAufgabe:
        return RasterAufgabe(
            frac_at=lambda _nv, _nh: 0.0,
            start=(1, 1),
            cap=cap,
            kandidaten=band_raster_kandidaten(wall, cap=cap),
            bewerte=bewerte,
            objective=ObjectiveConfig(),
            call_budget=500,
            pruef_tuer=pruef_tuer,
        )

    _ = kandidaten  # (haelt die Generator-Naht sichtbar)
    ohne = BeamSuche().waehle_raster(_aufgabe())
    mit = BeamSuche(surrogat=model).waehle_raster(_aufgabe())

    return (
        (ohne.n_length, ohne.n_height) == (mit.n_length, mit.n_height)
        and ohne.zellen_optionen == mit.zellen_optionen
        and (ohne.provenienz or {}).get("geprueft") == (mit.provenienz or {}).get("geprueft")
        and (ohne.provenienz or {}).get("leer") == (mit.provenienz or {}).get("leer")
    )


@dataclass(frozen=True)
class GateDecision:
    """Der dokumentierte Gate-Entscheid: welche Arme laufen und **warum** (Acceptance #220).

    ``arms`` ist die feste Reihenfolge der laufenden Arme; ``surrogat``/``gpu`` tragen den
    Grund je optionalem Arm (nie stillschweigend). :meth:`arm_label` nennt zwei-/drei-/
    vierarmig fuers Protokoll.
    """

    arms: tuple[str, ...]
    surrogat: SurrogatGateResult
    gpu_included: bool
    gpu_reason: str

    @property
    def n_arms(self) -> int:
        return len(self.arms)

    def arm_label(self) -> str:
        return {2: "zweiarmig", 3: "dreiarmig", 4: "vierarmig"}.get(
            self.n_arms, f"{self.n_arms}-armig"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arms": list(self.arms),
            "arm_count": self.n_arms,
            "arm_label": self.arm_label(),
            "surrogat_arm": self.surrogat.to_dict(),
            "gpu_arm": {"included": self.gpu_included, "reason": self.gpu_reason},
        }


def decide_arms(
    surrogat: SurrogatGateResult,
    *,
    gpu_ready: bool = False,
    gpu_reason: str | None = None,
) -> GateDecision:
    """Setzt die Armliste aus dem Sollbruch-Gate zusammen (zwei-/drei-/vierarmig, #220).

    Basis sind **immer** die CPU-Arme :data:`BASE_ARMS` (Greedy + Beam). Der dritte Arm
    (Beam+Surrogat) kommt hinzu, wenn ``surrogat.ok`` (Sollbruch-Gate gruen); der vierte
    (Beam+GPU) nach demselben Zug-Prinzip, **nur** wenn ``gpu_ready`` (heute nie — #205-G2
    entfaellt, ``gpu_reason`` dokumentiert es). Der Entscheid wartet nie und wiederholt nie.
    """
    arms: list[str] = list(BASE_ARMS)
    if surrogat.ok:
        arms.append(ARM_BEAM_SURROGAT)
    reason = gpu_reason or REASON_GPU_NICHT_FERTIG
    if gpu_ready:
        arms.append(ARM_BEAM_GPU)
        reason = "gpu-vorsortierer-bereit"
    return GateDecision(
        arms=tuple(arms), surrogat=surrogat, gpu_included=gpu_ready, gpu_reason=reason
    )


# --------------------------------------------------------------------------- #
# Arm-Laeufer (injizierbar) + Orchestrierung
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BenchmarkCase:
    """Ein **eingefrorener** Benchmark-Fall: eine stabile Kennung + opake Nutzlast.

    ``payload`` ist fuer den :data:`ArmRunner` bestimmt (produktiv Projekt/Druckjob, in
    Tests ein Fake) — der reine Harness liest sie nie, er reicht sie nur durch. Alle Arme
    laufen auf **derselben** Nutzlast (der eingefrorene Stand, US 27).
    """

    case_id: str
    payload: Any = None


@dataclass
class ArmRun:
    """Das Ergebnis **eines** Arm-Laufs: das persistierte ``decompose.json`` als Dict.

    ``doc`` ist das gelesene Lauf-Artefakt (die Auswertung liest **nur** daraus, US 20/21);
    ``run_dir`` der Pfad des Laufs (fuer die Protokoll-Rueckverfolgung, ADR-004).
    """

    arm: str
    case_id: str
    doc: dict[str, Any]
    run_dir: str | None = None


#: Der injizierbare Arm-Laeufer: ``(arm, case) → ArmRun``. Produktiv faehrt er den Arm
#: ueber :func:`fgc.pipeline.actions.propose_decomposition` und liest den Lauf; in Tests
#: ein deterministisches Fake (Muster: Kampagnen-Orakel #218/#190).
ArmRunner = Callable[[str, BenchmarkCase], ArmRun]


def run_arms(
    cases: Sequence[BenchmarkCase], arms: Sequence[str], runner: ArmRunner
) -> list[ArmRun]:
    """Faehrt **jeden verfuegbaren Arm** auf **jedem** Fall (eingefrorener Stand, US 27).

    Deterministische Reihenfolge (Fall aussen, Arm innen); der ``runner`` persistiert je
    Lauf ein ``decompose.json`` und gibt es gelesen zurueck. Reiner Harness: keine
    Geometrie, kein Nachrechnen — nur Orchestrierung.
    """
    runs: list[ArmRun] = []
    for case in cases:
        for arm in arms:
            runs.append(runner(arm, case))
    return runs


# --------------------------------------------------------------------------- #
# Auswertung — ausschliesslich aus persistierten Laufartefakten (US 20/21/27)
# --------------------------------------------------------------------------- #

#: Die byte-stabilen Paper-Kennzahlen je Lauf (deterministisch, US 25) — die
#: **Rechenzeit** ist bewusst **nicht** dabei (diagnostisch, maschinenabhaengig).
KENNZAHL_FIELDS: tuple[str, ...] = (
    "teilanzahl",
    "volumen_cv",
    "fugenflaeche_mm2",
    "erreichbarer_anteil",
    "geprueft_frei_anteil",
    "standplaetze",
)


def _mean(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 6)


def _standplaetze_aus_platzierungen(sections: Sequence[dict[str, Any]]) -> int:
    """Zaehlt die **Umsetzvorgaenge** aus den persistierten Teil-Platzierungen (kein Nachrechnen).

    In Druckreihenfolge (``order``): jede Platzierung, die sich vom Vorgaenger unterscheidet
    (seitlich/Abstand/Aufstellhoehe), ist ein neuer Standplatz. Rein aus dem Artefakt
    abgeleitet — dieselbe Bottom-up-Idee wie der Scorer (#216), aber ohne Karte.
    """
    ordered = sorted(sections, key=lambda s: s.get("order", 0))
    stationen = 0
    last: tuple | None = None
    for s in ordered:
        pl = s.get("placement") or {}
        key = (
            round(float(pl.get("lateral_mm", 0.0)), 3),
            round(float(pl.get("standoff_mm", 0.0)), 3),
            round(float(pl.get("stand_height_mm", 0.0)), 3),
        )
        if key != last:
            stationen += 1
            last = key
    return stationen


def _geprueft_frei_anteil(refinement: dict[str, Any] | None) -> float | None:
    """Der **geprueft-frei-Anteil** aus dem ``refinement``-Block — arm-normalisiert.

    Beam (#217/#219): der Metriken-Katalog traegt ihn direkt
    (``metriken.geprueft_frei_anteil`` = 1.0 geprueft-frei, sonst ``None``). Greedy (#165):
    aus den ``rows`` (Anteil kollisionsfreier Hoehenreihen). Ohne ``refinement`` ⇒ ``None``
    (nie ein geratenes „frei", ADR-007).
    """
    if not refinement:
        return None
    metriken = refinement.get("metriken")
    if isinstance(metriken, dict) and "geprueft_frei_anteil" in metriken:
        val = metriken["geprueft_frei_anteil"]
        return None if val is None else round(float(val), 6)
    rows = refinement.get("rows")
    if isinstance(rows, list) and rows:
        frei = sum(1 for r in rows if r.get("collision_free"))
        return round(frei / len(rows), 6)
    return None


def _verworfen_by_grund(refinement: dict[str, Any] | None) -> dict[str, int]:
    """Die **Verworfen-Gruende** je Grund (US 10) — ``reichweite`` = Karten-Vorfilter (#214)."""
    counts: dict[str, int] = {}
    if not refinement:
        return counts
    for eintrag in refinement.get("verworfen") or []:
        grund = str(eintrag.get("grund", "?"))
        counts[grund] = counts.get(grund, 0) + 1
    return counts


def arm_provenance(doc: dict[str, Any]) -> dict[str, Any]:
    """Die **vollstaendige Provenienz je Arm** (Acceptance #220): Strategie, Modellstand,
    Kontingent, Zielfunktions-Config — alles aus dem persistierten Lauf (ADR-004).
    """
    refinement = doc.get("refinement") or {}
    provenance = doc.get("provenance") or {}
    return {
        "strategy": refinement.get("strategy"),
        "surrogate_model": refinement.get("surrogate_model"),
        "call_budget": refinement.get("call_budget"),
        "calls_used": refinement.get("calls_used"),
        "budget_exhausted": refinement.get("budget_exhausted"),
        "objective": provenance.get("objective"),
        "source": provenance.get("source"),
        "git_commit": provenance.get("git_commit"),
    }


def evaluate_run(doc: dict[str, Any]) -> dict[str, Any]:
    """Leitet **einen** Lauf aus seinem ``decompose.json``-Dict ab — **kein Nachrechnen** (US 20).

    Liefert ``{"kennzahlen": …, "diagnostik": …, "provenance": …, "verworfen": …}``:

    - ``kennzahlen`` (byte-stabil, US 25): Teilanzahl, c_v, Fugenflaeche, erreichbarer
      Anteil, geprueft-frei-Anteil, Standplaetze — alle aus den persistierten Feldern
      (``grid``/``sections``/``refinement``), nichts neu gerechnet. c_v/Fugenflaeche stehen
      **nur** im Beam-Metriken-Katalog; der Greedy traegt sie nicht ⇒ ``None`` (ehrlich, kein
      Nachrechnen von Geometrie).
    - ``diagnostik``: die **Rechenzeit** (nur Beam) — maschinenabhaengig, **nicht** Teil des
      Byte-Vergleichs (US 25).
    - ``verworfen``: die Verworfen-Gruende je Grund (Karten-Vorfilter #214 = ``reichweite``).
    """
    refinement = doc.get("refinement") or {}
    metriken = refinement.get("metriken") if isinstance(refinement, dict) else None
    metriken = metriken if isinstance(metriken, dict) else {}
    sections = doc.get("sections") or []

    reach = [
        s.get("status", {}).get("reachable_fraction")
        for s in sections
        if isinstance(s.get("status"), dict)
    ]

    cv = metriken.get("volumen_cv")
    fuge = metriken.get("fugenflaeche_mm2")
    standplaetze = metriken.get("standplaetze")
    if standplaetze is None:
        standplaetze = _standplaetze_aus_platzierungen(sections)

    kennzahlen = {
        "teilanzahl": len(sections),
        "volumen_cv": None if cv is None else round(float(cv), 6),
        "fugenflaeche_mm2": None if fuge is None else round(float(fuge), 6),
        "erreichbarer_anteil": _mean(reach),
        "geprueft_frei_anteil": _geprueft_frei_anteil(refinement),
        "standplaetze": int(standplaetze),
    }
    rechenzeit = metriken.get("rechenzeit_s")
    return {
        "kennzahlen": kennzahlen,
        "diagnostik": {"rechenzeit_s": None if rechenzeit is None else float(rechenzeit)},
        "provenance": arm_provenance(doc),
        "verworfen": _verworfen_by_grund(refinement),
    }


def benchmark_kennzahlen(runs: Sequence[ArmRun]) -> dict[str, Any]:
    """Die **byte-vergleichbare** Auswertungstabelle je Arm × Fall (US 20/21/27).

    Liest **nur** die persistierten ``decompose.json``-Dicts (:func:`evaluate_run`) und
    ordnet sie deterministisch (Arm, dann Fall). ``kennzahlen`` (byte-stabil) ist von
    ``diagnostik`` (Rechenzeit) getrennt — Wiederholung eines CPU-Arms ⇒ **byte-gleiche**
    ``kennzahlen`` (US 25). Die Provenienz je Lauf (Strategie/Modell/Kontingent/Zielfunktion)
    liegt bei, sodass jede Paper-Kennzahl ohne Nachrechnen belegbar ist.
    """
    per_arm: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        per_arm.setdefault(run.arm, []).append(
            {"case_id": run.case_id, **evaluate_run(run.doc)}
        )
    for arm in per_arm:
        per_arm[arm].sort(key=lambda row: row["case_id"])

    arme = {arm: per_arm[arm] for arm in sorted(per_arm)}
    return {
        "arme": arme,
        "kennzahl_felder": list(KENNZAHL_FIELDS),
        "hinweis": (
            "Rechenzeit steht getrennt in diagnostik (maschinenabhaengig, US 25); die "
            "kennzahlen sind byte-vergleichbar (CPU-Arme, Wiederholung bit-gleich)."
        ),
    }


# --------------------------------------------------------------------------- #
# Protokoll — der eine, provenienz-gestempelte Beleg des Benchmarks (ADR-004)
# --------------------------------------------------------------------------- #


def benchmark_protocol(
    gate: GateDecision,
    cases: Sequence[BenchmarkCase],
    runs: Sequence[ArmRun],
    provenance: dict[str, Any],
    *,
    call_budget: int,
    robot_name: str,
) -> dict[str, Any]:
    """Schnuert das **Benchmark-Protokoll** als Artefakt mit Provenienz (Acceptance #220).

    Traegt: den **Gate-Entscheid** (zwei-/drei-/vierarmig samt Grund je Arm — nie
    stillschweigend), den **eingefrorenen Stand** (Faelle, Roboter, Kontingent), die
    **Provenienz je Arm** (Strategie/Modellstand/Kontingent/Zielfunktion) und die
    **byte-vergleichbare Auswertung** (:func:`benchmark_kennzahlen`) — alles aus den
    persistierten Laeufen. Reproduzierbar: gleiche Laeufe ⇒ gleiche ``auswertung`` (bis auf
    die getrennte Rechenzeit).
    """
    run_refs = [
        {"arm": r.arm, "case_id": r.case_id, "run_dir": r.run_dir} for r in runs
    ]
    return {
        "kind": BENCHMARK_KIND,
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "provenance": provenance,
        "gate": gate.to_dict(),
        "frozen_state": {
            "robot": robot_name,
            "call_budget": int(call_budget),
            "cases": [c.case_id for c in cases],
            "n_cases": len(cases),
        },
        "runs": run_refs,
        "auswertung": benchmark_kennzahlen(runs),
    }

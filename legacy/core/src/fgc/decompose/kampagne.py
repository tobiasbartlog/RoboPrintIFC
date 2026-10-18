"""fgc.decompose.kampagne — die **Datenkampagne** des Surrogat-Kaltstarts (Issue #218).

PRD #183 Stufe 4 (US 24, Grill 2026-07-14): ein reproduzierbares Batch-Skript
sampelt den **Kandidatenraum systematisch** (dokumentierter, deterministischer
Sampling-Plan), etikettiert jeden Kandidaten mit der **exakten Prüf-Tür**
(#211-Merkmals-Schema) und legt den **Datensatz als Artefakt mit Provenienz** ab
— das eigenständige, veröffentlichbare Paper-Artefakt, das #219 (Surrogat-Training)
konsumiert.

Dieses Modul ist die **reine, deterministische Hälfte** der Kampagne: der
Sampling-Plan, die Kandidaten-Aufzählung, das Zusammenschnüren des Datensatzes
und die Umfangsansage. Die **Etikettierung** kommt als **injizierbares Orakel**
(:data:`LabelOracle`) herein — produktiv das CPU-exakte Glied-SDF-Urteil
(:func:`fgc.pipeline.kampagne.cpu_exact_oracle`, der gültige CPU-only-Fallback,
der **nicht** auf #205/GPU wartet), in Tests ein Fake. So bleibt die Kampagnen-
Logik ohne Geometrie-Abhängigkeit tief testbar (Muster: ``assess_plan`` mit
injiziertem ``check_representative``, #190).

**Label-Quelle je Etikett** (Policy v1, Grill 2026-07-14): jedes Etikett trägt
seine Herkunft — :data:`LABEL_CPU_EXACT` (``cpu-exakt``), :data:`LABEL_GPU_CPU_GRENZBAND`
(``gpu+cpu-grenzband``, setzt das #205-G1-Gate voraus) oder
:data:`LABEL_GPU_STICHPROBEN_AUDIT` (``gpu+stichproben-audit``, **nicht**
trainingstauglich, nur explorativ). Der Datensatz weist die **Herkunftsverteilung**
aus (:meth:`CampaignRun.label_source_distribution`).

**Determinismus (US 25):** gleicher Plan ⇒ bit-gleiche Kandidatenmenge (der
Sampling-Plan ist ein Produkt über sortierten Achsen-Gittern × dem stabilen
Band-Raster-Generator #216). **Umfangsansage vor Start** (#175):
:func:`campaign_scope` (N Kandidaten, ~Dauer). **Abbruch/Teilstand:**
:func:`run_campaign` prüft ``should_cancel`` vor jedem Etikett und liefert den
Teilstand mit ``cancelled=True`` — der Datensatz ist dann als ``partial`` markiert.

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from fgc.decompose.kandidaten import BandRasterKandidat, band_raster_kandidaten
from fgc.decompose.pruefung import FEATURE_SCHEMA_VERSION, PRUEF_LABEL_CPU_EXACT, PruefSample
from fgc.placement import WallSurface

__all__ = [
    "DATASET_KIND",
    "DATASET_SCHEMA_VERSION",
    "DEFAULT_CAP",
    "DEFAULT_HEIGHTS_MM",
    "DEFAULT_LENGTHS_MM",
    "DEFAULT_SECONDS_PER_LABEL",
    "DEFAULT_THICKNESSES_MM",
    "LABEL_CPU_EXACT",
    "LABEL_GPU_CPU_GRENZBAND",
    "LABEL_GPU_STICHPROBEN_AUDIT",
    "LABEL_SOURCES",
    "NON_TRAINING_LABEL_SOURCES",
    "TRAINING_LABEL_SOURCES",
    "CampaignCandidate",
    "CampaignRun",
    "CampaignScope",
    "CandidateLabel",
    "LabelOracle",
    "LabeledSample",
    "SamplingPlan",
    "campaign_scope",
    "dataset_artifact",
    "run_campaign",
]

# --- Label-Quellen (Policy v1, Grill 2026-07-14) -----------------------------

#: CPU-exaktes Prüf-Tür-Urteil (Glied-SDF, #207/#213/#215) — der gültige
#: CPU-only-Fallback, der **nicht** auf #205/GPU wartet. Identisch mit der
#: Laufbetriebs-Label-Quelle (:data:`fgc.decompose.pruefung.PRUEF_LABEL_CPU_EXACT`).
LABEL_CPU_EXACT = PRUEF_LABEL_CPU_EXACT  # "cpu-exakt"

#: GPU-vorsortiert, CPU-verifiziert im konservativen Grenzband (#205-G1-Gate
#: bestanden). Trainingstauglich (Policy v1).
LABEL_GPU_CPU_GRENZBAND = "gpu+cpu-grenzband"

#: GPU-vorsortiert, nur per Stichprobe CPU-auditiert. **Nicht trainingstauglich**
#: (nur explorativ) — der Datensatz markiert diese Etiketten entsprechend.
LABEL_GPU_STICHPROBEN_AUDIT = "gpu+stichproben-audit"

#: Alle bekannten Label-Quellen (feste Reihenfolge für die Herkunftsverteilung).
LABEL_SOURCES: tuple[str, ...] = (
    LABEL_CPU_EXACT,
    LABEL_GPU_CPU_GRENZBAND,
    LABEL_GPU_STICHPROBEN_AUDIT,
)

#: Trainingstaugliche Label-Quellen (Policy v1): CPU-exakt + GPU-mit-CPU-Grenzband.
TRAINING_LABEL_SOURCES: frozenset[str] = frozenset(
    {LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND}
)

#: Nicht trainingstaugliche Label-Quellen: nur der Stichproben-Audit.
NON_TRAINING_LABEL_SOURCES: frozenset[str] = frozenset({LABEL_GPU_STICHPROBEN_AUDIT})

#: Artefakt-Kennung + Schema-Version des Datensatzes (eigenständiges Paper-Artefakt).
DATASET_KIND = "surrogate-dataset"
DATASET_SCHEMA_VERSION = "1"

#: Grobe Kosten je Etikett (Sekunden) für die Umfangsansage — die AP-1-Nachher-
#: Messung des SDF-Backends (#215, ~9,77 s je Prüf-Tür-Aufruf). Nur eine
#: Vorhersage für die bewusste Nutzerwahl, keine Entscheidungsgröße (US 25).
DEFAULT_SECONDS_PER_LABEL = 9.77

# --- Default-Sampling-Gitter (dokumentierter Plan) ---------------------------
# Systematisches Achsen-Gitter über die druck-relevanten Wandmaße: kurze/mittlere/
# lange Wände × niedrig/mittel/hoch × dünn/dick. Klein gehalten (das kartesische
# Produkt × Band-Raster wächst schnell); je Achse über die CLI übersteuerbar.
DEFAULT_LENGTHS_MM: tuple[float, ...] = (800.0, 1600.0, 2400.0)
DEFAULT_HEIGHTS_MM: tuple[float, ...] = (1200.0, 2000.0, 2800.0)
DEFAULT_THICKNESSES_MM: tuple[float, ...] = (150.0, 250.0)
#: Teilungs-Deckel je Achse des Band-Raster-Generators (#216) — klein (``cap²``
#: Kandidaten je Wand), damit die Kampagne über Nacht durchläuft.
DEFAULT_CAP = 3


@dataclass(frozen=True)
class SamplingPlan:
    """Der **dokumentierte, deterministische Sampling-Plan** der Kampagne (US 24/25).

    Ein kartesisches Produkt über sortierte Achsen-Gitter (Wandlänge × -höhe ×
    -dicke) liefert die **Wände**; je Wand zählt der stabile Band-Raster-Generator
    (:func:`fgc.decompose.kandidaten.band_raster_kandidaten`, #216) die Kandidaten-
    Zerlegungen auf. Sampling-Einheit ist ein **Höhenreihen-Repräsentant** je
    Band-Raster (die ungünstigste Zelle der Reihe — die letzte in Druckreihenfolge,
    mit den meisten früheren Teilen als Druckstand), damit die Merkmale genau die
    :class:`fgc.decompose.pruefung.PruefSample`-Felder tragen (#211).

    Gleicher Plan ⇒ bit-gleiche Kandidatenfolge (Achsen sortiert, Band-Raster grob
    vor fein) — das Byte-Vergleichs-Versprechen (ADR-004-Geist, US 25).
    """

    lengths_mm: tuple[float, ...] = DEFAULT_LENGTHS_MM
    heights_mm: tuple[float, ...] = DEFAULT_HEIGHTS_MM
    thicknesses_mm: tuple[float, ...] = DEFAULT_THICKNESSES_MM
    cap: int = DEFAULT_CAP

    def __post_init__(self) -> None:
        if self.cap < 1:
            raise ValueError(f"cap muss ≥ 1 sein, ist {self.cap}.")
        for name, axis in (
            ("lengths_mm", self.lengths_mm),
            ("heights_mm", self.heights_mm),
            ("thicknesses_mm", self.thicknesses_mm),
        ):
            if not axis:
                raise ValueError(f"Sampling-Achse {name!r} darf nicht leer sein.")

    def walls(self) -> tuple[WallSurface, ...]:
        """Die gesampelten Wände in **stabiler** Ordnung (Länge > Höhe > Dicke)."""
        return tuple(
            WallSurface(length_mm=length, height_mm=height, thickness_mm=thick)
            for length in sorted(self.lengths_mm)
            for height in sorted(self.heights_mm)
            for thick in sorted(self.thicknesses_mm)
        )

    def candidates(self) -> Iterator[CampaignCandidate]:
        """Zählt alle Kandidaten deterministisch auf (Wand × Band-Raster × Höhenreihe)."""
        for wall in self.walls():
            for kandidat in band_raster_kandidaten(wall, cap=self.cap):
                for row_index in range(kandidat.n_height):
                    yield CampaignCandidate(wall=wall, kandidat=kandidat, row_index=row_index)

    @property
    def n_candidates(self) -> int:
        """Wie viele Kandidaten der Plan aufzählt (rein rechnerisch, ohne Aufzählung)."""
        total = 0
        for wall in self.walls():
            for kandidat in band_raster_kandidaten(wall, cap=self.cap):
                total += kandidat.n_height
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "lengths_mm": [float(v) for v in sorted(self.lengths_mm)],
            "heights_mm": [float(v) for v in sorted(self.heights_mm)],
            "thicknesses_mm": [float(v) for v in sorted(self.thicknesses_mm)],
            "cap": int(self.cap),
            "n_walls": len(self.walls()),
            "n_candidates": self.n_candidates,
        }


@dataclass(frozen=True)
class CampaignCandidate:
    """Ein Sampling-Punkt: eine **Höhenreihe** eines Band-Raster-Kandidaten (US 24).

    Der **Repräsentant** der Reihe ist die ungünstigste Zelle — die **letzte
    Spalte** in Druckreihenfolge (unten → oben, links → rechts), mit den meisten
    früheren Teilen als Druckstand (der Kollisionstreiber bei „Abschnitt", #189).
    Die Merkmale (:meth:`feature_core`) sind genau die #211-Kandidaten-Kern-Felder,
    rein aus Plan-Geometrie ableitbar (kein Roboter nötig) — die Platzierungs-/
    Podest-Merkmale reichert erst das Etikettier-Orakel an (:meth:`PruefSample.with_placement`).
    """

    wall: WallSurface
    kandidat: BandRasterKandidat
    row_index: int

    @property
    def order(self) -> int:
        """1-basierte Druckreihenfolge-Nummer des Repräsentanten (letzte Spalte)."""
        n_length = self.kandidat.n_length
        return self.row_index * n_length + n_length

    @property
    def section_id(self) -> str:
        return f"abschnitt-{self.order}"

    @property
    def key(self) -> str:
        """Stabiler Kandidaten-Schlüssel (Wandmaße + Band-Raster + Reihe)."""
        w = self.wall
        return (
            f"{w.length_mm:g}x{w.height_mm:g}x{w.thickness_mm:g}"
            f"-{self.kandidat.key}-row{self.row_index}"
        )

    def feature_core(self) -> dict[str, Any]:
        """Der #211-Kandidaten-Kern: Abschnittsmaße + Wandposition + Hindernislast.

        Spiegelt :func:`fgc.decompose.pruefung._collect_samples` feldweise — dieselben
        Schlüssel, damit die Kampagnen-Merkmale mit denen des Laufbetriebs
        deckungsgleich sind (gemeinsames :data:`FEATURE_SCHEMA_VERSION`).
        """
        z0, z1 = self.kandidat.row_bounds_mm()[self.row_index]
        x0, x1 = self.kandidat.col_bounds_mm()[-1]  # ungünstigste Zelle = letzte Spalte
        w = self.wall
        return {
            "order": self.order,
            "x0_mm": round(x0, 3),
            "x1_mm": round(x1, 3),
            "z0_mm": round(z0, 3),
            "z1_mm": round(z1, 3),
            "length_mm": round(x1 - x0, 3),
            "height_mm": round(z1 - z0, 3),
            "center_x_mm": round((x0 + x1) / 2.0, 3),
            "wall_length_mm": w.length_mm,
            "wall_height_mm": w.height_mm,
            "wall_thickness_mm": w.thickness_mm,
            # Hindernislast in Druckreihenfolge: die früheren Teile stehen als
            # Druckstand im Weg (Kollisionstreiber, Befund B10) — hier order-1.
            "n_earlier_parts": self.order - 1,
        }

    def pruef_sample(self, verdict: dict[str, Any]) -> PruefSample:
        """Baut den :class:`PruefSample`-Kern (Merkmale + exaktes Urteil) dieses Punkts."""
        return PruefSample(self.section_id, self.feature_core(), verdict)


@dataclass(frozen=True)
class CandidateLabel:
    """Das **Etikett** eines Kandidaten: exaktes Prüf-Tür-Urteil + Label-Quelle (US 24).

    ``verdict`` ist das exakte Prüf-Tür-Urteil (serialisiert), ``label_source`` seine
    Herkunft (eine von :data:`LABEL_SOURCES`). ``placement`` (optional) trägt die
    vom Orakel gewählte Platzierung, mit der :func:`run_campaign` die Podest-/
    Platzierungs-Merkmale anreichert (:meth:`PruefSample.with_placement`, #211).
    """

    verdict: dict[str, Any]
    label_source: str
    placement: Any | None = None

    def __post_init__(self) -> None:
        if self.label_source not in LABEL_SOURCES:
            raise ValueError(
                f"Unbekannte Label-Quelle {self.label_source!r} — erlaubt: {list(LABEL_SOURCES)} "
                "(Policy v1, Grill 2026-07-14)."
            )


#: Das injizierbare Etikettier-Orakel: ``CampaignCandidate`` → ``CandidateLabel``.
#: Produktiv das CPU-exakte Glied-SDF-Urteil (:func:`fgc.pipeline.kampagne.cpu_exact_oracle`),
#: in Tests ein deterministisches Fake.
LabelOracle = Callable[["CampaignCandidate"], CandidateLabel]


@dataclass(frozen=True)
class LabeledSample:
    """Ein etikettierter Datensatz: :class:`PruefSample` + seine **Label-Quelle** (US 24)."""

    sample: PruefSample
    label_source: str

    @property
    def training_safe(self) -> bool:
        """Ist diese Label-Quelle trainingstauglich (Policy v1)?"""
        return self.label_source in TRAINING_LABEL_SOURCES

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.sample.to_dict(),
            "label_source": self.label_source,
            "training_safe": self.training_safe,
        }


@dataclass
class CampaignRun:
    """Das Ergebnis eines Kampagnenlaufs: etikettierte Datensätze + Abbruch-Stand (US 24)."""

    samples: list[LabeledSample] = field(default_factory=list)
    n_total: int = 0
    cancelled: bool = False

    @property
    def n_labeled(self) -> int:
        return len(self.samples)

    def label_source_distribution(self) -> dict[str, int]:
        """Die **Herkunftsverteilung** der Etiketten (US 24): Anzahl je Label-Quelle."""
        dist = {src: 0 for src in LABEL_SOURCES}
        for ls in self.samples:
            dist[ls.label_source] = dist.get(ls.label_source, 0) + 1
        return dist

    def training_safe_count(self) -> int:
        return sum(1 for ls in self.samples if ls.training_safe)

    def non_training_count(self) -> int:
        return sum(1 for ls in self.samples if not ls.training_safe)


@dataclass(frozen=True)
class CampaignScope:
    """Die **Umfangsansage** vor Start (Muster #175): N Kandidaten + grobe Dauer."""

    n_candidates: int
    seconds_per_label: float

    @property
    def est_seconds(self) -> float:
        return self.n_candidates * self.seconds_per_label

    def announcement(self) -> str:
        """Ein Satz für die bewusste Nutzerwahl vor dem (teuren) Lauf."""
        minutes = self.est_seconds / 60.0
        return (
            f"Datenkampagne: etikettiert {self.n_candidates} Kandidaten "
            f"(~{self.seconds_per_label:.1f} s je Etikett) => geschaetzt "
            f"~{minutes:.1f} min ({self.est_seconds / 3600.0:.2f} h)."
        )


def campaign_scope(
    plan: SamplingPlan, *, seconds_per_label: float = DEFAULT_SECONDS_PER_LABEL
) -> CampaignScope:
    """Die Umfangsansage eines Plans (Muster #175) — rein, **ohne** die teure Etikettierung."""
    return CampaignScope(
        n_candidates=plan.n_candidates, seconds_per_label=float(seconds_per_label)
    )


def run_campaign(
    plan: SamplingPlan,
    oracle: LabelOracle,
    *,
    on_progress: Callable[[int, int], Any] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    limit: int | None = None,
) -> CampaignRun:
    """Etikettiert den Kandidatenraum systematisch (US 24) — abbrechbar, Teilstand verwertbar.

    Zählt die Kandidaten des ``plan`` deterministisch auf und ruft je Kandidat das
    injizierte ``oracle`` (produktiv CPU-exakt, der gültige Fallback ohne GPU). Vor
    **jedem** Etikett wird ``should_cancel`` geprüft; ein Abbruch (auch ``KeyboardInterrupt``)
    liefert den **Teilstand** mit ``cancelled=True`` — nichts geht verloren (Muster #175).
    ``on_progress(done, total)`` meldet den Fortschritt, ``limit`` deckelt die Kandidatenzahl
    (Mini-Stichprobe für Selbstprüfläufe). **Fail-soft** (ADR-013): scheitert das Orakel an
    einem Kandidaten, wird er übersprungen (der Nachtlauf kippt nie an einer Zelle).
    """
    n_total = plan.n_candidates if limit is None else min(plan.n_candidates, int(limit))
    run = CampaignRun(n_total=n_total)
    done = 0
    try:
        for candidate in plan.candidates():
            if limit is not None and done >= int(limit):
                break
            if should_cancel is not None and should_cancel():
                run.cancelled = True
                break
            try:
                label = oracle(candidate)
            except Exception:  # noqa: BLE001 — Etikettieren ist Befund, nie den Nachtlauf kippen (#164)
                done += 1
                if on_progress is not None:
                    on_progress(done, n_total)
                continue
            sample = candidate.pruef_sample(label.verdict)
            if label.placement is not None:
                sample = sample.with_placement(label.placement)
            run.samples.append(LabeledSample(sample=sample, label_source=label.label_source))
            done += 1
            if on_progress is not None:
                on_progress(done, n_total)
    except KeyboardInterrupt:
        # Ctrl-C: der bis hier gesammelte Teilstand bleibt verwertbar (#175).
        run.cancelled = True
    return run


def dataset_artifact(
    run: CampaignRun,
    plan: SamplingPlan,
    provenance: dict[str, Any],
    *,
    seconds_per_label: float = DEFAULT_SECONDS_PER_LABEL,
) -> dict[str, Any]:
    """Schnürt den **Datensatz als Artefakt mit Provenienz** (US 24) — das Paper-Artefakt.

    Trägt: die Provenienz (ADR-004: Quell-Kommando, Zeitstempel, Git-Commit), den
    Sampling-Plan (reproduzierbar), die :data:`FEATURE_SCHEMA_VERSION` (Merkmals-
    Provenienz, #219/US 26), die **Herkunftsverteilung** der Label-Quellen, die
    Trainings-Tauglichkeitszählung (Policy v1: ``gpu+stichproben-audit`` ist **nicht**
    trainingstauglich und je Sample so markiert) und die etikettierten Datensätze.
    ``partial`` ist wahr, wenn der Lauf abgebrochen wurde oder ``limit`` die
    Kandidatenmenge beschnitt (der Datensatz ist dann ehrlich als Teilstand markiert).
    """
    partial = bool(run.cancelled) or run.n_labeled < plan.n_candidates
    return {
        "kind": DATASET_KIND,
        "schema_version": DATASET_SCHEMA_VERSION,
        "feature_version": FEATURE_SCHEMA_VERSION,
        "provenance": provenance,
        "sampling_plan": plan.to_dict(),
        "n_samples": run.n_labeled,
        "n_candidates_planned": plan.n_candidates,
        "partial": partial,
        "cancelled": bool(run.cancelled),
        # Herkunftsverteilung der Etiketten (US 24).
        "label_source_distribution": run.label_source_distribution(),
        "training": {
            "training_safe_count": run.training_safe_count(),
            "non_training_count": run.non_training_count(),
            "training_safe_sources": sorted(TRAINING_LABEL_SOURCES),
            "non_training_sources": sorted(NON_TRAINING_LABEL_SOURCES),
        },
        "seconds_per_label": float(seconds_per_label),
        "samples": [ls.to_dict() for ls in run.samples],
    }

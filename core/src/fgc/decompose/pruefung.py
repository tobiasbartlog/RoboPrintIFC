"""fgc.decompose.pruefung — die Urteils-Politik der Prüf-Tür über dem Zerlegungsplan.

Das benannte Modul für die **Prüf-Tür-Politik** (Issue #190, Grill 2026-07-13):
Fokus/Global-Scoping, die Reihen-Vererbung über Repräsentanten
(:func:`fgc.decompose.printability.representative_by_row`), die drei Bedeutungen
von „kein Urteil" (``unchecked`` = noch nicht angestoßen, ``no_geometry`` =
unzuständig, ``error`` = fehlgeschlagen — Issue #170/#175) und die Cache-Politik
(nur echte Urteile, FIFO-gedeckelt). Vorher lebte diese Politik als private
Helfer-Familie in ``pipeline/actions.py`` — reine Domänenlogik über dem
Zerlegungsplan, ohne benanntes Interface.

Die eine Tür ist :func:`assess_plan`. Sie ist **rein über ihren Eingaben**: die
teure Prüf-Tür selbst (Abschnitts-Simulation, ~10 s je Höhenreihe) kommt als
**injizierbares Orakel** ``check_representative`` herein — produktiv eine Closure
über :func:`fgc.pipeline.sectionsim.clearance_verdict` (#189), in Tests ein Fake,
absehbar der #165-Autozerleger je Kandidatenplan. Stufe 1 (der gratis Ruhezustand
des interaktiven Loops) ist **derselbe Aufruf ohne Orakel**.

Job-Schema-Wissen bleibt beim Aufrufer (``actions.py``): er baut die
Cache-Signatur (``_plan_pruef_signature``) und die Override-Menge aus dem
Druckjob und persistiert das Ergebnis. **Befund, kein Gate** (ADR-013).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from fgc.decompose.freigang import DEFAULT_WRIST_RADIUS_MM, check_teilhoehe
from fgc.decompose.printability import (
    REASON_UNCHECKED,
    VERDICT_TOO_TALL,
    PartPrintability,
    combine_printability,
    representative_by_row,
)

if TYPE_CHECKING:
    from fgc.decompose.evaluate import SectionStatus
    from fgc.decompose.freigang import FreigangCheck
    from fgc.decompose.plan import DecompositionPlan
    from fgc.decompose.printability import PartPrintability

__all__ = [
    "FEATURE_SCHEMA_VERSION",
    "PRUEF_LABEL_CPU_EXACT",
    "CheckRepresentative",
    "PruefCache",
    "PruefSample",
    "PruefStats",
    "assess_plan",
    "count_representatives",
    "pruef_dataset_block",
]

#: Version der **Merkmalsliste** je geprüftem Kandidat (Issue #211, Datensammel-Pflicht
#: PRD #183 US 23). Die Provenienz des künftigen Surrogats (#219, US 26) hängt an dieser
#: Version: ändert sich der Feld-Satz oder die Bedeutung eines Merkmals in
#: :class:`PruefSample`, wird die Version **hochgezählt** (nie stillschweigend umdefiniert).
#: ``"1"`` ist der Erst-Satz: Abschnittsmaße + Wandposition + Hindernislast (aus
#: :func:`assess_plan`) plus Platzierung/Podesthöhe (angereichert beim Bundle-Schnüren).
FEATURE_SCHEMA_VERSION = "1"

#: Label-Quelle je Datensatz **im Laufbetrieb** (Issue #211, Grill 2026-07-14): immer die
#: exakte CPU-Prüfung. Die Label-*Quellen*-Frage (Surrogat darf sich nicht selbst labeln)
#: betrifft nur die Datenkampagne #218 — der reguläre Prüf-Tür-Lauf labelt stets ``cpu-exakt``.
PRUEF_LABEL_CPU_EXACT = "cpu-exakt"


@dataclass(frozen=True)
class PruefSample:
    """Ein Trainings-Datensatz je **geprüftem Kandidat** (Issue #211, PRD #183 US 23).

    Die Datensammel-Pflicht der Stufe-2-Prüf-Tür: je Höhenreihen-Repräsentant, den die
    Prüf-Tür wirklich beurteilt hat (echtes Urteil, kein ``error``/``no_geometry``-Grund),
    fällt ein Datensatz an — ``features`` (die Merkmale) + ``verdict`` (das **exakte
    Prüf-Tür-Urteil** verbatim wie im Lauf-Artefakt, :meth:`PartPrintability.to_dict`).
    Der Trainingsdatensatz für Beam/Surrogat (#217/#218/#219) füllt sich so von selbst.

    ``features`` wächst zweistufig entlang der fixierten Seams (Grill 2026-07-14):
    :func:`assess_plan` legt den **Kandidaten-Kern** (Abschnittsmaße, Wandposition,
    Hindernislast — was das reine Domänen-Modul aus Plan + Urteil kennt), der Aufrufer
    :func:`fgc.pipeline.actions.check_decomposition` reichert beim Bundle-Schnüren die
    **Platzierungs-/Podest-Merkmale** an (:meth:`with_placement`). Die Feld-Menge ist über
    :data:`FEATURE_SCHEMA_VERSION` versioniert (Surrogat-Provenienz, US 26).
    """

    section_id: str
    features: dict[str, Any]
    verdict: dict[str, Any]

    def with_placement(self, placement: Any) -> PruefSample:
        """Angereicherter Datensatz um Platzierungs-/Podest-Merkmale (Issue #211).

        Der zweite fixierte Seam: der Aufrufer kennt die **Platzierung** je Teil und legt
        sie hier additiv in die Merkmale — seitliche Position, Standoff, **Podesthöhe**
        (``stand_height_mm``, absolut über dem Boden, #132) und Gierwinkel. Fail-soft
        über ``getattr``: fehlt ein Feld, bleibt es ``None`` (nie ein Absturz beim Sammeln).
        """
        feats = dict(self.features)
        feats["lateral_mm"] = getattr(placement, "lateral_mm", None)
        feats["standoff_mm"] = getattr(placement, "standoff_mm", None)
        feats["stand_height_mm"] = getattr(placement, "stand_height_mm", None)
        feats["yaw_rad"] = getattr(placement, "yaw_rad", None)
        return replace(self, features=feats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "features": self.features,
            "verdict": self.verdict,
        }


def pruef_dataset_block(samples: list[PruefSample] | None) -> dict[str, Any] | None:
    """Der Datensammel-Block fürs Lauf-Artefakt (Issue #211) — oder ``None`` (leer).

    Verpackt die geprüften Kandidaten in **einen** additiven Block: die
    :data:`FEATURE_SCHEMA_VERSION` (Merkmals-Provenienz, US 26), die Label-Quelle
    (:data:`PRUEF_LABEL_CPU_EXACT`, im Laufbetrieb immer ``cpu-exakt``) und die Datensätze.
    Ohne geprüfte Kandidaten (Stufe-1-Ruhezustand: kein Orakel lief) ⇒ ``None``, damit der
    Aufrufer den Block gar nicht schreibt (additiv, Altläufe/Stufe-1-Läufe byte-gleich).
    """
    if not samples:
        return None
    return {
        "feature_version": FEATURE_SCHEMA_VERSION,
        "label_source": PRUEF_LABEL_CPU_EXACT,
        "samples": [s.to_dict() for s in samples],
    }


def _collect_samples(
    plan: DecompositionPlan,
    verdict_by_rep: dict[str, Any],
    printability: dict[str, PartPrintability],
) -> list[PruefSample]:
    """Kandidaten-Kern je geprüftem Repräsentanten (Issue #211) — fail-soft, rein.

    Ein Datensatz je Repräsentant mit **echtem** Prüf-Tür-Urteil (Urteils-Objekt, kein
    ``error``/``no_geometry``-Grund-String): die Merkmale, die das reine Domänen-Modul aus
    Plan + Urteil kennt (Abschnittsmaße, Wandposition, Wandmaße, Hindernislast in
    Druckreihenfolge — der Kollisionstreiber bei „Abschnitt", 0 bei „Modul"), plus das
    exakte Urteil (``printability[rep_id].to_dict()``, das an DIESEM Teil selbst geprüfte,
    nicht geerbte). **Fail-soft** (#164-Muster): jeder Fehler beim Sammeln liefert eine
    leere Liste — die Datensammel-Pflicht kippt nie den Zerlegungslauf (Befund, kein Gate).
    """
    try:
        section_by_id = {sp.section.section_id: sp.section for sp in plan.sections}
        order_index = {sp.section.section_id: i for i, sp in enumerate(plan.sections)}
        prints_in_place = plan.prints_in_place
        out: list[PruefSample] = []
        for rep_id, verdict in verdict_by_rep.items():
            # Nur echte Urteile (Objekt) sammeln — ein Grund-String (error/no_geometry,
            # #170) ist KEIN geprüfter Kandidat und liefert keine Merkmale.
            if isinstance(verdict, str):
                continue
            sec = section_by_id.get(rep_id)
            pr = printability.get(rep_id)
            if sec is None or pr is None:
                continue
            features: dict[str, Any] = {
                "order": sec.order,
                "x0_mm": sec.x0_mm,
                "x1_mm": sec.x1_mm,
                "z0_mm": sec.z0_mm,
                "z1_mm": sec.z1_mm,
                "length_mm": sec.length_mm,
                "height_mm": sec.height_mm,
                "center_x_mm": sec.center_x_mm,
                "wall_length_mm": plan.wall.length_mm,
                "wall_height_mm": plan.wall.height_mm,
                "wall_thickness_mm": plan.wall.thickness_mm,
                # Hindernislast in Druckreihenfolge (Befund B10): der Kollisionstreiber
                # bei „Abschnitt" (frühere Teile stehen als Druckstand im Weg), 0 bei „Modul".
                "n_earlier_parts": order_index.get(rep_id, 0) if prints_in_place else 0,
            }
            out.append(PruefSample(rep_id, features, pr.to_dict()))
        return sorted(out, key=lambda s: s.section_id)
    except Exception:  # noqa: BLE001 — Datensammeln ist Befund, nie den Lauf kippen (#164)
        return []

#: Das injizierbare Orakel der teuren Stufe 2: ``section_id`` des Höhenreihen-
#: Repräsentanten → Prüf-Tür-Urteil. Rückgabe ist ein echtes Urteil (Objekt mit
#: ``collides``/Ursache, i. d. R. ein :class:`fgc.collision.finding.ClearanceVerdict`),
#: ``None`` (keine Geometrie) oder ein Grund-String (:data:`REASON_NO_GEOMETRY`/
#: :data:`REASON_ERROR`, Issue #170) — ein String wird **nie** als freies Urteil
#: gelesen und **nie** gecacht.
CheckRepresentative = Callable[[str], Any]


@dataclass
class PruefStats:
    """Rechen-/Cache-Statistik eines Stufe-2-Prüflaufs (Issue #175).

    ``n_representatives`` = zu prüfende Höhenreihen-Repräsentanten im **Scope**
    (global = alle, Fokus = der Repräsentant der Fokus-Reihe); ``n_computed`` = davon
    **wirklich gerechnet** (Cache-Miss), ``n_cached`` = per Cache-Treffer übersprungen
    (Akzeptanzkriterium: ein unveränderter Stand rechnet 0). ``cancelled`` = der Lauf
    wurde abgebrochen (Teilergebnis, **nicht** persistiert).
    """

    n_representatives: int = 0
    n_computed: int = 0
    n_cached: int = 0
    cancelled: bool = False


class PruefCache:
    """Prüf-Tür-Ergebnis-Cache je (Signatur, Repräsentant) — FIFO-gedeckelt (Issue #175).

    Schlüssel ist ``(signature, section_id)``: ein unveränderter (Schnitt,
    Platzierung, Parameter)-Stand trifft denselben Schlüssel und wird **nicht**
    erneut gerechnet; jede Änderung erzeugt eine andere Signatur (Miss ⇒
    Neurechnung). Die FIFO-Deckelung (Einfügereihenfolge, dict ist geordnet)
    verhindert unbegrenztes Wachsen. Single-Process wie der Projekt-Lock
    (ADR-018); ``actions.py`` hält die **eine** prozessweite Instanz, Tests geben
    eine frische — das frühere ``clear_prueftuer_cache``-Ritual und der
    Identitätsvergleich mit dem Prozess-Cache entfallen (Issue #190).
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = int(max_entries)
        self._data: dict[Hashable, Any] = {}

    def __contains__(self, key: Hashable) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: Hashable) -> Any:
        """Das gecachte Urteil zu ``key`` — oder ``None`` (nie gecacht, s. Politik)."""
        return self._data.get(key)

    def store(self, key: Hashable, value: Any) -> None:
        """Legt ein Urteil ab; am Deckel fliegt der älteste Eintrag (FIFO)."""
        if len(self._data) >= self._max_entries:
            self._data.pop(next(iter(self._data)))
        self._data[key] = value

    def clear(self) -> None:
        """Leert den Cache (Speicherfreigabe)."""
        self._data.clear()


def count_representatives(
    plan: DecompositionPlan,
    statuses: list[SectionStatus],
    freigang: FreigangCheck | None,
    override_ids: frozenset[str] | set[str] = frozenset(),
) -> int:
    """Wie viele Höhenreihen-Repräsentanten eine **globale** Stufe-2-Prüfung rechnen
    müsste (Issue #175) — rein, **ohne** die teure Prüf-Tür.

    Speist die Umfangsansage „prüft N Abschnitte, dauert ~…" (die bewusste
    Nutzerwahl; Fokus-Prüfung bleibt Default). Ist die Wand schon nach Freigang zu
    dick (Stufe 1), ist nichts zu prüfen (``0``).
    """
    if freigang is not None and getattr(freigang, "too_thick", False):
        return 0
    status_by_id = {s.section_id: s for s in statuses}
    rep_by_section = representative_by_row(plan, status_by_id, override_ids)
    return len({rid for rid in rep_by_section.values() if rid is not None})


def _apply_teilhoehe(
    printability: dict[str, PartPrintability],
    plan: DecompositionPlan,
    freigang: FreigangCheck | None,
) -> dict[str, PartPrintability]:
    """Zweite Stufe-1-Schranke (Issue #209): zu hohe Teile → ``too_tall`` (additiv).

    Die per-Teil-Schranke „Teil zu hoch für die verbleibende freie Länge" (Gl. 9,
    :func:`fgc.decompose.freigang.check_teilhoehe`) — anders als der wand-weite
    Freigang-Befund „zu dick" hängt sie an der **einzelnen** Teilhöhe. Läuft nur im
    **Stufe-1-Ruhezustand** (kein Orakel, keine Simulation — Short-Circuit, US 3) und
    überschreibt ein zu hohes Teil mit ``too_tall``: rot, aber ``presumed`` (platzierungs-
    blinde Vermutung, kein Gate) mit doppeltem Überschuss ``excess_mm`` (Höhe) und
    ``excess_deg`` (Neigung, US 4). Die Erreichbarkeits-Kanäle (``reachable``/…) des
    bisherigen Urteils bleiben erhalten; die Prüf-Tür-Felder (Ursache/Grund) werden
    geleert (kein Prüf-Tür-Urteil). War der einfließende TCP provisorisch (#177), wird
    das analog ausgewiesen. **Fail-soft:** fehlt der Freigang-Befund (keine Tool-
    Geometrie), bleibt alles unverändert — nie ein geratenes „zu hoch". Rein.
    """
    if freigang is None:
        return printability
    ell = float(getattr(freigang, "free_length_mm", 0.0))
    rad = float(getattr(freigang, "wrist_radius_mm", DEFAULT_WRIST_RADIUS_MM))
    tcp_prov = bool(getattr(freigang, "tcp_provisional", False))
    out = dict(printability)
    for sp in plan.sections:
        sid = sp.section.section_id
        pr = out.get(sid)
        if pr is None:
            continue
        hc = check_teilhoehe(sp.section.height_mm, free_length_mm=ell, wrist_radius_mm=rad)
        if hc.too_tall:
            out[sid] = replace(
                pr,
                verdict=VERDICT_TOO_TALL,
                presumed=True,
                excess_mm=hc.excess_mm,
                excess_deg=hc.excess_deg,
                representative_id=None,
                reason=None,
                causer_link=None,
                causer_against=None,
                penetration_mm=None,
                min_distance_mm=None,
                tcp_provisional=tcp_prov,
            )
    return out


def assess_plan(
    plan: DecompositionPlan,
    statuses: list[SectionStatus],
    freigang: FreigangCheck | None,
    override_ids: frozenset[str] | set[str],
    check_representative: CheckRepresentative | None,
    *,
    signature: Hashable | None = None,
    focus_section_id: str | None = None,
    cache: PruefCache | None = None,
    on_progress: Callable[[int, int], Any] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, PartPrintability], PruefStats, list[PruefSample]]:
    """Druckbarkeits-Urteil je Teil des Zerlegungsplans — die **eine** Tür der
    Prüf-Tür-Politik (Issue #164/#175/#190).

    **Stufe 1 (gratis) = derselbe Aufruf ohne Orakel** (``check_representative=None``):
    ist die Wand nach Freigang (#163) zu dick, trägt jedes Teil ``too_thick``
    (kollisionsehrlich, keine Prüf-Tür); sonst prüft die **zweite Stufe-1-Schranke**
    (#209, :func:`_apply_teilhoehe`) je Teil „zu hoch für die freie Länge" (Gl. 9,
    Stamatopoulos) und markiert zu hohe Teile ``too_tall`` — beides ohne Simulation
    (Short-Circuit). Was keine Schranke fängt, bleibt ehrlich ``unchecked`` — **nie
    stilles Grün** (ADR-013). Der Ruhezustand des interaktiven Schnittplan-Loops (B14).

    **Stufe 2 (teuer)** mit Orakel: je **Höhenreihe** wird nur die ungünstigste
    Zelle geprüft (:func:`fgc.decompose.printability.representative_by_row`,
    ``override_ids`` sind von der Vererbung ausgenommen, #174/B36), die übrigen
    erben als ``presumed``. Grün wird **nur**, was die Prüf-Tür wirklich frei sah
    (S6/#164). ``check_representative(section_id)`` ist das injizierte Orakel
    (produktiv: Closure über :func:`fgc.pipeline.sectionsim.clearance_verdict`).

    **Cache je (Schnitt, Platzierung, Parameter)** (Issue #175): ein Repräsentant,
    dessen Schlüssel (``signature`` + ``section_id``) schon im ``cache`` liegt, wird
    **nicht** erneut gerechnet (``n_cached``); nur die neuen (``n_computed``). Ein
    unveränderter Zweitlauf rechnet 0. Gecacht werden **nur echte Urteile** —
    nie die „ungeprüft"-Gründe (``error``/``no_geometry`` als String, Issue #170):
    ein transienter Fehler darf nicht kleben bleiben, der nächste Anstoß probiert
    ihn neu. **Fokus** (``focus_section_id``): nur der Repräsentant der Fokus-Reihe
    wird (neu) gerechnet — die übrigen Reihen kommen aus dem Cache (falls schon
    geprüft) oder bleiben ``unchecked`` (nie stilles Grün). **Abbrechen**
    (``should_cancel``): vor jeder teuren Zelle geprüft; ein Abbruch liefert das
    Teilergebnis mit ``cancelled=True`` (der Aufrufer persistiert es nicht).
    **Fortschritt** (``on_progress(done, total)``): nach jedem Repräsentanten.

    ``signature`` und ``cache`` sind nur mit Orakel Pflicht (der Aufrufer baut die
    Signatur — Job-Schema-Wissen bleibt bei ihm, #190). Rückgabe
    ``(printability, stats, samples)``: ``samples`` ist der **Kandidaten-Kern** je
    geprüftem Repräsentanten (Merkmale + exaktes Urteil, Issue #211/Datensammel-Pflicht
    PRD #183 US 23) — im Stufe-1-Ruhezustand (kein Orakel) leer, in Stufe 2 ein
    :class:`PruefSample` je Repräsentant mit echtem Urteil (der Aufrufer reichert
    Platzierung/Podest an, :meth:`PruefSample.with_placement`). **Befund, kein Gate** (ADR-013).
    """
    status_by_id = {s.section_id: s for s in statuses}

    # Stufe 1: zu dick ⇒ alle too_thick, keine Prüf-Tür (nichts zu rechnen).
    if freigang is not None and getattr(freigang, "too_thick", False):
        # Stufe-1-Kurzschluss: keine Prüf-Tür lief ⇒ kein geprüfter Kandidat (samples leer).
        return combine_printability(plan, freigang, {}, {}, status_by_id), PruefStats(), []

    # Stufe 1 ohne Orakel: jedes Teil ehrlich ``unchecked`` (noch nicht geprüft) —
    # bewusst KEIN Cache-Blick (der interaktive Loop täuscht kein Urteil vor). Die
    # zweite Stufe-1-Schranke „Teil zu hoch" (Issue #209) läuft HIER, im gratis
    # Ruhezustand: sie überschreibt zu hohe Teile mit ``too_tall`` — ohne Orakel, ohne
    # Simulation (Short-Circuit, US 3). Die teure Stufe 2 überstimmt die Vermutung.
    if check_representative is None:
        printability = combine_printability(
            plan, freigang, {}, {}, status_by_id, default_reason=REASON_UNCHECKED
        )
        # Ruhezustand ohne Orakel: keine Prüf-Tür lief ⇒ kein geprüfter Kandidat (samples leer).
        return _apply_teilhoehe(printability, plan, freigang), PruefStats(), []

    if cache is None or signature is None:
        raise ValueError(
            "Stufe 2 (check_representative gesetzt) braucht signature und cache"
        )

    rep_by_section = representative_by_row(plan, status_by_id, override_ids)
    all_reps = sorted({rid for rid in rep_by_section.values() if rid is not None})

    # Scope: global = alle Repräsentanten; Fokus = nur der Repräsentant der Fokus-Reihe.
    if focus_section_id is not None:
        focus_rep = rep_by_section.get(focus_section_id)
        scope_reps = {focus_rep} if focus_rep is not None else set()
    else:
        scope_reps = set(all_reps)

    stats = PruefStats(n_representatives=len(scope_reps & set(all_reps)))
    verdict_by_rep: dict[str, Any] = {}
    done = 0
    total = stats.n_representatives
    for rep_id in all_reps:
        key = (signature, rep_id)
        if key in cache:
            # Cache-Treffer: unveränderter (Schnitt, Platzierung, Parameter)-Stand —
            # nicht erneut rechnen (auch nicht im Fokus-Scope: schon geprüft).
            verdict_by_rep[rep_id] = cache.get(key)
            if rep_id in scope_reps:
                stats.n_cached += 1
                done += 1
                if on_progress is not None:
                    on_progress(done, total)
            continue
        if rep_id not in scope_reps:
            # Außerhalb des Scopes und nicht im Cache ⇒ bleibt ``unchecked`` (kein
            # verdict_by_rep-Eintrag) — ehrlich „noch nicht geprüft", nie stilles Grün.
            continue
        if should_cancel is not None and should_cancel():
            stats.cancelled = True
            break
        verdict = check_representative(rep_id)
        # Nur echte Urteile cachen (Urteils-Objekt), NICHT die „ungeprüft"-Gründe
        # (``error``/``no_geometry`` als String, Issue #170).
        if not isinstance(verdict, str):
            cache.store(key, verdict)
        verdict_by_rep[rep_id] = verdict
        stats.n_computed += 1
        done += 1
        if on_progress is not None:
            on_progress(done, total)

    printability = combine_printability(
        plan, freigang, verdict_by_rep, rep_by_section, status_by_id,
        default_reason=REASON_UNCHECKED,
    )
    # Datensammel-Pflicht (Issue #211): je geprüftem Repräsentanten der Kandidaten-Kern
    # (Merkmale + exaktes Urteil) — fail-soft, der Aufrufer reichert Platzierung/Podest an.
    samples = _collect_samples(plan, verdict_by_rep, printability)
    return printability, stats, samples

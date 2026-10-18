"""Stufe-2-Prüf-Tür entkoppelt vom interaktiven Loop (Issue #175, Politik-Tür #190).

Prüft die Urteils-Politik an ihrer **einen Tür** ``fgc.decompose.pruefung.assess_plan``
(Issue #190): Stufe 1 = derselbe Aufruf ohne Orakel (Teile ehrlich „ungeprüft"),
Stufe 2 mit **injiziertem Orakel** ``check_representative`` (kein monkeypatch auf
actions-Private mehr) — mit **PruefCache** je (Schnitt, Platzierung, Parameter)
(nachweisbar: unveränderter Zweitlauf rechnet 0; nur echte Urteile werden gecacht;
FIFO-Deckel), **Abbrechen**, **Fortschritt**, **Fokus-Scope**. Dazu die Aktions-Naht:
``propose_decomposition`` rechnet die teure Prüf-Tür **nicht** mehr,
``check_decomposition`` läuft auf expliziten Anstoß ohne die Projekt-Sperre über die
Rechenzeit zu halten (Supersede-Wächter statt Lost-Update). Der ``last_pruef``-Marker
macht „was zuletzt geprüft (global/Fokus)" sichtbar und (über den Schnappschuss)
veraltbar.

Die teure Prüf-Tür wird als Orakel injiziert bzw. end-to-end am **öffentlichen**
Seam ``actions.clearance_verdict`` gemockt (schnell, deterministisch) — geprüft wird
die Orchestrierung, nicht die Kollisionsgeometrie. Tests geben eine **frische**
``PruefCache``-Instanz — kein ``clear_prueftuer_cache``-Ritual mehr (Issue #190).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Helfer aus der Zerlegungs-Suite wiederverwenden (voller Projekt-Aufbau).
from test_decompose import _project_with_job

from fgc.decompose import DecompositionPlan, FreigangCheck, Section, SectionPlan
from fgc.decompose.evaluate import SectionStatus
from fgc.decompose.printability import (
    REASON_ERROR,
    REASON_UNCHECKED,
    VERDICT_PRINTABLE,
    VERDICT_TOO_TALL,
    VERDICT_TOO_THICK,
    VERDICT_UNKNOWN,
)
from fgc.decompose.pruefung import (
    FEATURE_SCHEMA_VERSION,
    PRUEF_LABEL_CPU_EXACT,
    PruefCache,
    PruefSample,
    PruefStats,
    assess_plan,
)
from fgc.pipeline import actions
from fgc.placement import PlacementOption, WallSurface


@pytest.fixture
def stub_walls(install_walls, make_wall):
    """Stub-Wand + leerer Gebäudekontext (wie in der Zerlegungs-Suite)."""
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=2600.0)])


# --- Reine Plan-/Status-Fixtures (zwei Höhenreihen, je 1 Repräsentant) ---------


def _two_row_plan(kind: str = "abschnitt") -> DecompositionPlan:
    wall = WallSurface(length_mm=800.0, height_mm=1600.0, thickness_mm=200.0)
    low = SectionPlan(
        Section("abschnitt-1", 1, -400.0, 400.0, 0.0, 800.0),
        PlacementOption("platz-1", 0.0, 700.0, 0.0),
    )
    high = SectionPlan(
        Section("abschnitt-2", 2, -400.0, 400.0, 800.0, 1600.0),
        PlacementOption("platz-2", 0.0, 700.0, 0.0),
    )
    return DecompositionPlan(kind, wall, (), (low, high), 1, 2)


def _status(sid: str, order: int, *, frac: float = 1.0, margin: float = 0.3) -> SectionStatus:
    return SectionStatus(
        section_id=sid, order=order, reachable=frac >= 0.999, reachable_fraction=frac,
        n_samples=100, n_reachable=int(frac * 100), kinematic_margin=margin, mean_margin=margin,
    )


def _free_verdict():
    return SimpleNamespace(
        collides=False, causer_link=None, causer_against=None,
        penetration_mm=None, min_distance_mm=None,
    )


def _counting_clearance(monkeypatch):
    """Mockt die teure Prüf-Tür am **öffentlichen** Aktions-Seam (end-to-end) und
    zählt die tatsächlichen Rechnungen (Cache-Beweis)."""
    calls: list[str] = []

    def _fake(_artifact, _job, _plan, section_id, **_k):
        calls.append(section_id)
        return _free_verdict()

    monkeypatch.setattr(actions, "clearance_verdict", _fake)
    return calls


def _counting_oracle(verdict_for=None):
    """Injizierbares Prüf-Tür-Orakel (Issue #190) + Protokoll der Rechnungen.

    ``verdict_for(section_id)`` liefert das Urteil (Default: alles frei).
    """
    calls: list[str] = []

    def _check(section_id: str):
        calls.append(section_id)
        return _free_verdict() if verdict_for is None else verdict_for(section_id)

    return calls, _check


# --- Stufe 1: der Ruhezustand des interaktiven Loops (kein Orakel) --------------


def test_stage1_without_oracle_leaves_parts_unchecked():
    """Stufe 1 = ``assess_plan`` **ohne Orakel** (Issue #190): jedes Teil bleibt ehrlich
    ``unchecked`` — nie stilles Grün —, nichts wird gerechnet (die Entkopplung)."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]

    out, stats, _samples = assess_plan(plan, statuses, None, frozenset(), None)

    for sid in ("abschnitt-1", "abschnitt-2"):
        assert out[sid].verdict == VERDICT_UNKNOWN
        assert out[sid].reason == REASON_UNCHECKED
        assert out[sid].printable is False  # nie grün ohne Prüfung (ADR-013)
    assert stats == PruefStats()  # 0 gerechnet, 0 gecacht — kein Orakel nötig


def test_stage1_too_thick_short_circuits_without_oracle():
    """Ist die Wand nach Freigang zu dick, trägt Stufe 1 direkt ``too_thick`` (gratis,
    kollisionsehrlich) — auch das ohne Orakel."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    freigang = SimpleNamespace(too_thick=True, excess_mm=42.0, tcp_provisional=False)

    out, stats, _samples = assess_plan(plan, statuses, freigang, frozenset(), None)
    assert all(p.verdict == VERDICT_TOO_THICK for p in out.values())
    assert stats == PruefStats()


# --- Stufe 1: zweite Schranke „Teil zu hoch für die freie Länge" (Issue #209) ---


def _freigang_not_thick(
    free_length_mm: float, wrist_radius_mm: float = 60.0, *, tcp_provisional: bool = False
) -> FreigangCheck:
    """Ein Freigang-Befund, der NICHT zu dick ist — damit die Höhen-Schranke greifen kann
    (und nicht der wand-weite „zu dick"-Kurzschluss davor)."""
    return FreigangCheck(
        wall_thickness_mm=100.0,
        free_length_mm=free_length_mm,
        wrist_radius_mm=wrist_radius_mm,
        printable_depth_mm=free_length_mm + wrist_radius_mm,
        too_thick=False,
        excess_mm=0.0,
        levers=(),
        tcp_provisional=tcp_provisional,
    )


def test_stage1_too_tall_marks_tall_part_without_simulation():
    """Ein zu hohes Teil wird in Stufe 1 als ``too_tall`` markiert — OHNE Orakel, OHNE
    Simulation (Short-Circuit, US 3). Überschuss doppelt: mm (Höhe) UND Grad (Neigung)."""
    plan = _two_row_plan()  # zwei Reihen à 800 mm hoch
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    # L = 100, R = 60 ⇒ H_max = L²/R ≈ 166,7 mm < 800 mm ⇒ beide Teile zu hoch.
    freigang = _freigang_not_thick(100.0, 60.0)

    out, stats, _samples = assess_plan(plan, statuses, freigang, frozenset(), None)

    for sid in ("abschnitt-1", "abschnitt-2"):
        pr = out[sid]
        assert pr.verdict == VERDICT_TOO_TALL
        assert pr.collides and not pr.printable  # rot, aber nie grün
        assert pr.presumed is True  # platzierungsblinde Vermutung, keine Gewissheit
        assert pr.representative_id is None  # kein Prüf-Tür-Repräsentant
        assert pr.excess_mm is not None and pr.excess_mm > 0.0  # Höhen-Überschuss (mm)
        assert pr.excess_deg is not None and pr.excess_deg > 0.0  # Winkel-Überschuss (Grad)
        assert pr.to_dict()["excess_deg"] == pytest.approx(pr.excess_deg)
    # US 3: kein Orakel, nichts gerechnet — keine Simulation lief an.
    assert stats == PruefStats()


def test_stage1_short_part_not_flagged_too_tall():
    """Fehlerrichtung S6: ein großzügiger Endeffektor lässt 800-mm-Teile stumm — sie
    bleiben ehrlich ``unchecked``, nie ein falsches „zu hoch"."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    # L = 1000, R = 60 ⇒ H_max = L²/R ≈ 16667 mm ≫ 800 mm ⇒ kein Befund.
    freigang = _freigang_not_thick(1000.0, 60.0)

    out, _stats, _samples = assess_plan(plan, statuses, freigang, frozenset(), None)
    for sid in ("abschnitt-1", "abschnitt-2"):
        assert out[sid].verdict == VERDICT_UNKNOWN
        assert out[sid].reason == REASON_UNCHECKED
        assert "excess_deg" not in out[sid].to_dict()  # additiv: kein Feld ohne Befund


def test_stage1_too_tall_fail_soft_without_freigang():
    """Fail-soft: ohne Freigang-Befund (keine Tool-Geometrie) greift die Höhen-Schranke
    nicht — selbst hohe Teile bleiben ``unchecked``, nie ein geratenes „zu hoch"."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]

    out, _stats, _samples = assess_plan(plan, statuses, None, frozenset(), None)
    assert all(p.verdict == VERDICT_UNKNOWN for p in out.values())


def test_stage1_too_tall_carries_provisional_tcp():
    """Ein „zu hoch" aus einem provisorischen TCP weist die Vorläufigkeit aus (analog #177)."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    freigang = _freigang_not_thick(100.0, 60.0, tcp_provisional=True)

    out, _stats, _samples = assess_plan(plan, statuses, freigang, frozenset(), None)
    pr = out["abschnitt-1"]
    assert pr.verdict == VERDICT_TOO_TALL
    assert pr.tcp_provisional is True
    assert pr.to_dict()["tcp_provisional"] is True


def test_stage2_oracle_supersedes_too_tall_presumption():
    """Die teure Stufe 2 überstimmt die Höhen-Vermutung: läuft das Orakel (expliziter
    Anstoß), zählt sein Urteil — nicht das gratis „zu hoch" der Stufe 1."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    freigang = _freigang_not_thick(100.0, 60.0)  # in Stufe 1 wären beide „zu hoch"
    calls, oracle = _counting_oracle()

    out, stats, _samples = assess_plan(
        plan, statuses, freigang, frozenset(), oracle,
        signature=("hoehe",), cache=PruefCache(),
    )
    # Stufe 2 rechnet je Reihe einen Repräsentanten (kein „zu hoch"-Kurzschluss hier).
    assert calls  # das Orakel lief
    assert all(p.verdict != VERDICT_TOO_TALL for p in out.values())
    assert stats.n_computed >= 1


def test_stage2_requires_signature_and_cache():
    """Mit Orakel sind ``signature`` und ``cache`` Pflicht (kein stiller Prozess-Cache
    im Domänen-Modul — die eine Instanz hält der Aufrufer, Issue #190)."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    _calls, check = _counting_oracle()

    with pytest.raises(ValueError, match="signature und cache"):
        assess_plan(plan, statuses, None, frozenset(), check)


# --- Stufe 2: PruefCache je (Schnitt, Platzierung, Parameter) — nachweisbar -----


def test_stage2_cache_hit_recomputes_zero():
    """Cache-Beweis (AC): ein **unveränderter** (Schnitt, Platzierung, Parameter)-Stand
    (dieselbe Signatur, derselbe Cache) rechnet beim Zweitlauf 0."""
    calls, check = _counting_oracle()
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    cache = PruefCache()

    out1, stats1, _samples = assess_plan(
        plan, statuses, None, frozenset(), check, signature=("stand-a",), cache=cache,
    )
    assert stats1.n_computed == 2 and stats1.n_cached == 0
    assert len(calls) == 2
    assert all(out1[s].verdict == VERDICT_PRINTABLE for s in ("abschnitt-1", "abschnitt-2"))

    # Zweitlauf, unveränderte Eingaben, gleicher Cache ⇒ 0 Neurechnungen.
    out2, stats2, _samples = assess_plan(
        plan, statuses, None, frozenset(), check, signature=("stand-a",), cache=cache,
    )
    assert stats2.n_computed == 0
    assert stats2.n_cached == 2
    assert len(calls) == 2  # keine weitere Prüf-Tür-Rechnung
    assert {s: out2[s].verdict for s in out2} == {s: out1[s].verdict for s in out1}


def test_stage2_cache_invalidates_on_placement_change():
    """Eine geänderte Platzierung erzeugt eine andere Job-Signatur
    (``actions._plan_pruef_signature``, bleibt beim Aufrufer) ⇒ Cache-Miss (Neurechnung)."""
    calls, check = _counting_oracle()
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    cache = PruefCache()

    # Platzierung der unteren Reihe verschieben ⇒ neue Signatur.
    moved = SectionPlan(
        plan.sections[0].section, PlacementOption("platz-1", 120.0, 700.0, 0.0)
    )
    plan2 = DecompositionPlan(
        "abschnitt", plan.wall, (), (moved, plan.sections[1]), 1, 2
    )
    sig1 = actions._plan_pruef_signature(plan, {}, travel_stride=5)
    sig2 = actions._plan_pruef_signature(plan2, {}, travel_stride=5)
    assert sig1 != sig2  # die Signatur erfasst die Platzierung

    assess_plan(plan, statuses, None, frozenset(), check, signature=sig1, cache=cache)
    assert len(calls) == 2

    _out, stats, _samples = assess_plan(
        plan2, statuses, None, frozenset(), check, signature=sig2, cache=cache,
    )
    assert stats.n_computed >= 1  # mindestens die verschobene Reihe wird neu gerechnet


def test_stage2_error_verdict_never_cached():
    """Nur **echte** Urteile werden gecacht (Issue #170/#190): ein Grund-String
    (``error``) klebt nicht — der nächste Anstoß probiert ihn neu."""
    calls, check = _counting_oracle(verdict_for=lambda _sid: REASON_ERROR)
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    cache = PruefCache()

    out1, stats1, _samples = assess_plan(
        plan, statuses, None, frozenset(), check, signature=("stand-a",), cache=cache,
    )
    assert stats1.n_computed == 2
    assert len(cache) == 0  # der transiente Fehler liegt NICHT im Cache
    assert all(p.verdict == VERDICT_UNKNOWN for p in out1.values())
    assert all(p.reason == REASON_ERROR for p in out1.values())

    # Unveränderter Zweitlauf: kein Treffer — die Prüfung wird erneut versucht.
    _out2, stats2, _samples = assess_plan(
        plan, statuses, None, frozenset(), check, signature=("stand-a",), cache=cache,
    )
    assert stats2.n_computed == 2 and stats2.n_cached == 0
    assert len(calls) == 4


def test_pruefcache_fifo_evicts_oldest():
    """FIFO-Deckel (Issue #175): am Limit fliegt der älteste Eintrag, die jüngsten bleiben."""
    cache = PruefCache(max_entries=2)
    cache.store(("sig", "a"), "urteil-a")
    cache.store(("sig", "b"), "urteil-b")
    cache.store(("sig", "c"), "urteil-c")

    assert len(cache) == 2
    assert ("sig", "a") not in cache  # ältester Eintrag verworfen
    assert cache.get(("sig", "b")) == "urteil-b"
    assert cache.get(("sig", "c")) == "urteil-c"


def test_stage2_focus_scope_checks_only_focus_row():
    """Fokus-Scope (Default-Wahl): nur die Höhenreihe des Fokus-Teils wird gerechnet,
    die übrigen Reihen bleiben ``unchecked`` (nie stilles Grün)."""
    calls, check = _counting_oracle()
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]

    out, stats, _samples = assess_plan(
        plan, statuses, None, frozenset(), check,
        signature=("stand-a",), focus_section_id="abschnitt-1", cache=PruefCache(),
    )
    assert calls == ["abschnitt-1"]
    assert stats.n_representatives == 1 and stats.n_computed == 1
    assert out["abschnitt-1"].verdict == VERDICT_PRINTABLE
    # Die andere Reihe: ehrlich ungeprüft (noch nicht angestoßen).
    assert out["abschnitt-2"].verdict == VERDICT_UNKNOWN
    assert out["abschnitt-2"].reason == REASON_UNCHECKED


def test_stage2_cancel_returns_partial_not_persisted():
    """Abbrechen (AC-Zusatz): ``should_cancel`` stoppt vor der ersten teuren Zelle —
    Teilergebnis mit ``cancelled=True``, 0 gerechnet."""
    calls, check = _counting_oracle()
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]

    _out, stats, _samples = assess_plan(
        plan, statuses, None, frozenset(), check,
        signature=("stand-a",), cache=PruefCache(), should_cancel=lambda: True,
    )
    assert stats.cancelled is True
    assert stats.n_computed == 0
    assert calls == []


def test_stage2_progress_reported_per_representative():
    """Fortschritt (AC): ``on_progress(done, total)`` wird je Repräsentant gemeldet."""
    _calls, check = _counting_oracle()
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    seen: list[tuple[int, int]] = []

    assess_plan(
        plan, statuses, None, frozenset(), check,
        signature=("stand-a",), cache=PruefCache(),
        on_progress=lambda d, t: seen.append((d, t)),
    )
    assert seen == [(1, 2), (2, 2)]


# --- End-to-end: Entkopplung + Anstoß + last_pruef + Supersede -----------------


def _not_too_thick(monkeypatch):
    """Freigang aushebeln (Stub-Wand ist unter diesem Roboter zu dick) — so bleibt die
    Wand ein Prüf-Tür-Fall (Stufe 2), nicht der gratis too_thick-Kurzschluss (Stufe 1)."""
    monkeypatch.setattr(actions, "_freigang_finding", lambda *_a, **_k: None)


def test_propose_is_decoupled_parts_unchecked_and_scope_announced(
    tmp_path, stub_walls, monkeypatch
):
    """AC: ein Schnittplan-Edit (``propose_decomposition``) rechnet die Prüf-Tür NICHT —
    die Teile sind ``unchecked`` (nie stilles Grün) — und sagt den Prüf-Umfang an."""
    def _boom(*_a, **_k):  # pragma: no cover - darf nie laufen
        raise AssertionError("Ein Schnittplan-Edit darf die Prüf-Tür nicht anstoßen")

    monkeypatch.setattr(actions, "clearance_verdict", _boom)
    _not_too_thick(monkeypatch)
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    result = actions.propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    for s in result.sections:
        pr = s["printability"]
        assert pr["verdict"] == "unknown"
        assert pr["reason"] == REASON_UNCHECKED
    # Umfangsansage vorhanden (bewusste Wahl: prüft N Reihen, ~… s).
    assert result.pruef_scope is not None
    assert result.pruef_scope["n_representatives"] >= 1
    assert result.pruef_scope["est_seconds"] >= 0.0


def test_check_decomposition_persists_verdict_and_last_pruef(tmp_path, stub_walls, monkeypatch):
    """AC: der explizite Anstoß rechnet die Prüf-Tür, persistiert das Urteil und den
    ``last_pruef``-Marker (was geprüft: global); der Prüf-Stand ist danach ``current``,
    ein Schnittplan-Edit veraltet ihn (sichtbar, nicht gelöscht)."""
    from fgc.project import load_project, project_dir_for, pruef_status

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    _not_too_thick(monkeypatch)
    _counting_clearance(monkeypatch)  # Prüf-Tür sieht alles frei

    res = actions.check_decomposition(
        slug, "src", cache=PruefCache(), projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert res.state == "done"
    assert res.stats.n_computed >= 1

    job = res.result.artifact["print_jobs"][0]
    assert job["last_pruef"]["scope"] == "global"
    # Frisch geprüft ⇒ aktuell.
    assert pruef_status(job) == "current"
    # Geprüfte Teile tragen jetzt ein echtes Urteil (nicht mehr ``unchecked``).
    verdicts = {s["section_id"]: s["printability"]["verdict"] for s in res.result.sections}
    assert any(v == "printable" for v in verdicts.values())

    # Ein Schnittplan-Edit (neue Zerlegung) bumpt cutplan ⇒ der letzte Prüfstand veraltet.
    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    reloaded = load_project(project_dir)["print_jobs"][0]
    assert pruef_status(reloaded) == "current"  # noch aktuell
    # Struktur ändern: eine frische Auto-Zerlegung mit anderem Schnittplan.
    actions.propose_decomposition(
        slug, "src",
        cuts=[{"orientation": "horizontal", "position_mm": 900.0}],
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    after = load_project(project_dir)["print_jobs"][0]
    assert pruef_status(after) == "stale"  # letzter Prüfstand veraltet (sichtbar)


def test_check_decomposition_superseded_on_parallel_write(tmp_path, stub_walls, monkeypatch):
    """AC: die Projekt-Sperre wird NICHT über die Rechenzeit gehalten — ändert ein
    paralleler Schreibzugriff die Prüf-Eingaben während der Rechnung, wird das Ergebnis
    als ``superseded`` verworfen (kein Lost-Update auf frische Nutzeredits)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    _not_too_thick(monkeypatch)

    def _writing_clearance(*_a, **_k):
        # Simuliert einen parallelen Schreibzugriff WÄHREND der (hier gemockten) teuren
        # Rechnung — Phase 2 hält die Sperre nicht, der Schreiber blockiert also nicht:
        # der Aufstell-Toggle ist Teil der Prüf-Eingaben (_pruef_input_fields).
        actions.set_stand_mode_for_job(slug, "elevated", projects_dir=projects_dir)
        return _free_verdict()

    monkeypatch.setattr(actions, "clearance_verdict", _writing_clearance)

    res = actions.check_decomposition(
        slug, "src", cache=PruefCache(), projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert res.state == "superseded"
    assert res.result is None


def test_check_decomposition_focus_scope_marks_last_pruef_focus(tmp_path, stub_walls, monkeypatch):
    """Fokus-Prüfung (Default): ``last_pruef`` hält scope=focus + die section_id fest."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    _not_too_thick(monkeypatch)
    _counting_clearance(monkeypatch)

    # Ersten Abschnitt des rekonstruierten Plans als Fokus wählen.
    proposal = actions.propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    focus = proposal.sections[0]["section_id"]

    res = actions.check_decomposition(
        slug, "src", focus_section_id=focus, cache=PruefCache(),
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert res.state == "done"
    job = res.result.artifact["print_jobs"][0]
    assert job["last_pruef"]["scope"] == "focus"
    assert job["last_pruef"]["section_id"] == focus


# --- Datensammel-Pflicht: Merkmale + Urteil je geprüftem Kandidat (Issue #211) ---


def test_stage2_collects_pruef_sample_per_checked_candidate():
    """AC #211: je **geprüftem** Repräsentanten (Stufe-2-Prüf-Tür) fällt ein Datensatz an
    — der Kandidaten-Kern aus ``assess_plan``: Abschnittsmaße + Wandposition + exaktes Urteil."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    _calls, oracle = _counting_oracle()

    _out, _stats, samples = assess_plan(
        plan, statuses, None, frozenset(), oracle,
        signature=("stand-a",), cache=PruefCache(),
    )
    # Zwei Höhenreihen ⇒ zwei geprüfte Repräsentanten ⇒ zwei Datensätze (nach id sortiert).
    assert [s.section_id for s in samples] == ["abschnitt-1", "abschnitt-2"]
    s0 = samples[0]
    assert isinstance(s0, PruefSample)
    # Kandidaten-Kern (assess_plan-Seam): Abschnittsmaße + Wandposition + Hindernislast.
    assert s0.features["height_mm"] == 800.0
    assert s0.features["length_mm"] == 800.0
    assert s0.features["z0_mm"] == 0.0
    assert s0.features["wall_thickness_mm"] == 200.0
    assert s0.features["n_earlier_parts"] == 0  # unterste Reihe: kein früheres Teil
    # Exaktes Prüf-Tür-Urteil verbatim (das an DIESEM Teil geprüfte, nicht geerbte).
    assert s0.verdict["verdict"] == VERDICT_PRINTABLE
    assert s0.verdict["presumed"] is False
    # Platzierung/Podest reichert erst der Aufrufer an — noch NICHT im Kern.
    assert "stand_height_mm" not in s0.features


def test_stage1_collects_no_pruef_samples():
    """Ohne Orakel (Stufe-1-Ruhezustand) läuft keine Prüf-Tür ⇒ kein geprüfter Kandidat
    ⇒ leerer Datensatz (der Editor-Loop füllt den Trainingssatz nicht)."""
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]
    _out, _stats, samples = assess_plan(plan, statuses, None, frozenset(), None)
    assert samples == []


def test_stage2_error_verdict_not_collected_as_sample():
    """Ein Grund-String (``error``) ist KEIN geprüftes Urteil (Issue #170) ⇒ kein Datensatz —
    der Trainingssatz sammelt nur echte Prüf-Tür-Urteile."""
    _calls, check = _counting_oracle(verdict_for=lambda _sid: REASON_ERROR)
    plan = _two_row_plan()
    statuses = [_status("abschnitt-1", 1), _status("abschnitt-2", 2)]

    _out, _stats, samples = assess_plan(
        plan, statuses, None, frozenset(), check, signature=("stand-a",), cache=PruefCache(),
    )
    assert samples == []


def test_pruef_sample_enrichment_is_fail_soft():
    """Fail-soft (#164-Muster): ein Platzierungs-Objekt ohne die Felder erzeugt ``None``-
    Werte statt eines Absturzes — der Kandidaten-Kern bleibt erhalten."""
    s = PruefSample("x", {"height_mm": 1.0}, {"verdict": "printable"})
    out = s.with_placement(object())  # kein lateral/standoff/stand_height/yaw
    assert out.features["height_mm"] == 1.0  # Kern unversehrt
    assert out.features["stand_height_mm"] is None  # Podest fail-soft None


def test_check_decomposition_writes_pruef_dataset_artifact(tmp_path, stub_walls, monkeypatch):
    """AC #211 end-to-end: der Prüf-Tür-Lauf legt Merkmale + Urteil je geprüftem Kandidat
    im Lauf-Artefakt ab (versioniert, Label ``cpu-exakt``); Platzierung/Podest angereichert;
    schema-valide."""
    import json

    from fgc import domain

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    _not_too_thick(monkeypatch)
    _counting_clearance(monkeypatch)  # Prüf-Tür sieht alles frei

    res = actions.check_decomposition(
        slug, "src", cache=PruefCache(), projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert res.state == "done"

    artifact = json.loads((res.result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")  # additiver Block, schema-valide

    ds = artifact["pruef_dataset"]
    assert ds["feature_version"] == FEATURE_SCHEMA_VERSION  # versioniert (US 26)
    assert ds["label_source"] == PRUEF_LABEL_CPU_EXACT == "cpu-exakt"  # Laufbetrieb
    assert ds["samples"], "je geprüftem Kandidat ein Datensatz"
    sample = ds["samples"][0]
    # Merkmale: Abschnittsmaße + Wandposition (assess_plan) + Platzierung/Podest (Aufrufer).
    for key in ("height_mm", "wall_thickness_mm", "center_x_mm", "stand_height_mm", "standoff_mm"):
        assert key in sample["features"], key
    # Exaktes Prüf-Tür-Urteil je Kandidat.
    assert sample["verdict"]["verdict"] in ("printable", "collides")


def test_propose_writes_no_pruef_dataset_altlauf_loads(tmp_path, stub_walls, monkeypatch):
    """Additivität/US 12: ein Stufe-1-Lauf (``propose_decomposition``) trägt KEINEN
    ``pruef_dataset``-Block und lädt/validiert unverändert — wie ein Altlauf ohne das Feld."""
    import json

    from fgc import domain

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    _not_too_thick(monkeypatch)

    res = actions.propose_decomposition(
        slug, "src", projects_dir=projects_dir, runs_dir=runs_dir,
    )
    artifact = json.loads((res.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")  # ohne das Feld weiterhin gültig (additiv)
    assert "pruef_dataset" not in artifact


def test_background_runner_progress_and_cancel(tmp_path, stub_walls, monkeypatch):
    """Hintergrundlauf (AC): ``checkjobs.start`` liefert sofort einen Griff; der Lauf
    endet in ``done`` mit Fortschritt; ``cancel`` setzt das Abbruch-Signal."""
    import time

    from fgc.pipeline import checkjobs

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    checkjobs.reset()
    _not_too_thick(monkeypatch)
    _counting_clearance(monkeypatch)

    job = checkjobs.start(
        slug, "default",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert job.state in ("running", "done")

    # Auf Abschluss warten (der Mock rechnet in ms).
    deadline = time.time() + 15.0
    while time.time() < deadline and checkjobs.get(job.id).state == "running":
        time.sleep(0.05)
    done = checkjobs.get(job.id)
    assert done.state == "done"
    assert done.n_total >= 1
    assert done.sections is not None

    # cancel eines unbekannten Laufs ⇒ False; eines bekannten ⇒ True.
    assert checkjobs.cancel("unbekannt") is False
    assert checkjobs.cancel(job.id) is True
    checkjobs.reset()

"""Druckbarkeit als Lauf-Eigenschaft der Zerlegung — reine Logik (Issue #164).

Prueft das externe Verhalten des tiefen Moduls `fgc.decompose.printability`:
die repraesentative Reihen-Wahl (:func:`representative_by_row`, unguenstigste Zelle)
und die Verheiratung von Freigang (Stufe 1) + Pruef-Tuer (Stufe 2) zum Urteil je
Teil (:func:`combine_printability`). Der Kern des Issues ist die **Ehrlichkeit**:
gruen nur aus der Pruef-Tuer, geerbte Reihen-Urteile als ``presumed`` — beides hier
festgenagelt. Rein, ohne I/O (die teure Pruef-Tuer selbst laeuft im Actions-Test).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fgc.decompose import FreigangCheck, PartPrintability
from fgc.decompose.evaluate import SectionStatus
from fgc.decompose.plan import DecompositionPlan, Section, SectionPlan

# Paket-Interna der Prüf-Tür-Politik (Issue #190): die Bausteine von ``assess_plan``
# werden hier direkt geprüft — sie sind bewusst NICHT im Paket-Export.
from fgc.decompose.printability import (
    REASON_ERROR,
    REASON_NO_GEOMETRY,
    VERDICT_COLLIDES,
    VERDICT_PRINTABLE,
    VERDICT_TOO_THICK,
    VERDICT_UNKNOWN,
    combine_printability,
    representative_by_row,
)
from fgc.placement import PlacementOption, WallSurface


@dataclass(frozen=True)
class _FakeVerdict:
    """Ein Pruef-Tuer-Urteil-Double (dieselben Felder wie ClearanceVerdict)."""

    collides: bool
    causer_link: int | None = None
    causer_against: str | None = None
    penetration_mm: float | None = None
    min_distance_mm: float | None = None
    # Pruef-Vorbehalte (Issue #182) — Default wie ClearanceVerdict eines vollen,
    # bestaetigten Laufs (nichts ausgeduennt, kein provisorischer Endeffektor).
    travel_thinned: bool = False
    n_checked: int | None = None
    n_samples: int | None = None
    tool_provisional: bool = False
    # Kollisions-ORT (Issue #181) — Default wie ein Urteil ohne bekannten Verursacher.
    worst_original_index: int | None = None
    worst_layer: int | None = None
    causer_position_mm: tuple[float, float, float] | None = None
    red_intervals: tuple[dict, ...] = ()


def _status(
    section_id: str, order: int, *, margin: float | None, fraction: float = 1.0
) -> SectionStatus:
    return SectionStatus(
        section_id=section_id,
        order=order,
        reachable=fraction >= 0.999,
        reachable_fraction=fraction,
        n_samples=100,
        n_reachable=int(fraction * 100),
        kinematic_margin=margin,
        mean_margin=margin,
    )


def _grid_plan(n_length: int, n_height: int, kind: str = "abschnitt") -> DecompositionPlan:
    """n_length x n_height-Raster (Zellen 800x800), Druckreihenfolge unten->oben."""
    wall = WallSurface(length_mm=800.0 * n_length, height_mm=800.0 * n_height, thickness_mm=300.0)
    sections: list[SectionPlan] = []
    order = 0
    for hi in range(n_height):
        z0, z1 = 800.0 * hi, 800.0 * (hi + 1)
        for vi in range(n_length):
            x0 = -400.0 * n_length + 800.0 * vi
            order += 1
            sections.append(
                SectionPlan(
                    Section(f"abschnitt-{order}", order, x0, x0 + 800.0, z0, z1),
                    PlacementOption(f"platz-{order}", 0.0, 700.0, 0.0),
                )
            )
    return DecompositionPlan(kind, wall, (), tuple(sections), n_length, n_height)


# --- representative_by_row: kollisionsehrliche Zelle je Hoehenreihe (#174) ------


def test_representative_is_max_obstacle_load_cell_per_row():
    """Je Hoehenband wird die Zelle mit MAXIMALER Hindernislast in Druckreihenfolge
    geprueft — bei Art „abschnitt" die zuletzt gedruckte Zelle der Reihe (die durch das
    meiste frische Nachbarmaterial faehrt, Befund B10). Die kinematische Marge ist NICHT
    mehr das Kriterium (sie war blind fuer den eigentlichen Kollisionstreiber)."""
    plan = _grid_plan(n_length=3, n_height=2)
    # Margen bewusst so, dass die ALTE Regel (kleinste Marge) andere Zellen kueren
    # wuerde — der Repraesentant folgt jetzt der Hindernislast, nicht der Marge.
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.05),
        "abschnitt-2": _status("abschnitt-2", 2, margin=0.1),
        "abschnitt-3": _status("abschnitt-3", 3, margin=0.5),
        "abschnitt-4": _status("abschnitt-4", 4, margin=0.05),
        "abschnitt-5": _status("abschnitt-5", 5, margin=0.6),
        "abschnitt-6": _status("abschnitt-6", 6, margin=0.4),
    }
    reps = representative_by_row(plan, status_by_id)
    # Untere Reihe (1..3): die zuletzt gedruckte = abschnitt-3 (max Hindernislast).
    assert reps["abschnitt-1"] == reps["abschnitt-2"] == reps["abschnitt-3"] == "abschnitt-3"
    # Obere Reihe (4..6): abschnitt-6.
    assert reps["abschnitt-4"] == reps["abschnitt-5"] == reps["abschnitt-6"] == "abschnitt-6"


def test_representative_excludes_unreachable_cell():
    """Eine Zelle ohne erreichbare Pose (Marge None) wird NIE Repraesentant (Befund
    B13) — trotz maximaler Hindernislast gewinnt die erreichbare Nachbarzelle."""
    plan = _grid_plan(n_length=2, n_height=1)
    # abschnitt-2 hat die groessere Hindernislast, ist aber unerreichbar (Marge None).
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.5),
        "abschnitt-2": _status("abschnitt-2", 2, margin=None, fraction=0.0),
    }
    reps = representative_by_row(plan, status_by_id)
    # Repraesentant ist die erreichbare Zelle, nicht die hindernislastigere unerreichbare.
    assert reps["abschnitt-1"] == reps["abschnitt-2"] == "abschnitt-1"


def test_representative_none_when_no_reachable_cell_in_row():
    """Ist KEINE Zelle der Reihe erreichbar, hat die Reihe keinen Repraesentanten
    (``None``) — der Aufrufer erbt kein „frei", sondern ``unknown`` (#174/B13)."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=None, fraction=0.0),
        "abschnitt-2": _status("abschnitt-2", 2, margin=None, fraction=0.0),
    }
    reps = representative_by_row(plan, status_by_id)
    assert reps["abschnitt-1"] is None and reps["abschnitt-2"] is None


def test_representative_tiebreak_is_last_printed_cell_for_module():
    """Bei Art „modul" gibt es keine frueheren Teile als Hindernis (ADR-022) ⇒ die
    Hindernislast ist 0 fuer alle, der Gleichstand ist konstruktiv. Der Stich faellt
    dann auf die ZULETZT gedruckte Zelle (max order), nicht die erste (#174, Kern von
    B10: heute gewaenne systematisch die hindernisaermste erste Zelle)."""
    plan = _grid_plan(n_length=4, n_height=1, kind="modul")
    status_by_id = {
        f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.06) for i in range(1, 5)
    }
    reps = representative_by_row(plan, status_by_id)
    assert set(reps.values()) == {"abschnitt-4"}


def test_representative_override_cell_is_self_checked_not_inherited():
    """Eine Zelle mit eigenem Platzierungs-Override erbt kein Reihen-Urteil (ihr Urteil
    wurde an ANDERER Platzierung gemessen, Befund B36): sie zeigt auf sich selbst
    (selbst geprueft) und wird nie Repraesentant fuer die Nachbarn."""
    plan = _grid_plan(n_length=3, n_height=1)
    status_by_id = {
        f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.5) for i in range(1, 4)
    }
    # abschnitt-3 (sonst der Repraesentant, max Hindernislast) traegt einen Override.
    reps = representative_by_row(plan, status_by_id, override_ids={"abschnitt-3"})
    # Override-Zelle: selbst geprueft.
    assert reps["abschnitt-3"] == "abschnitt-3"
    # Die uebrigen erben NICHT von der Override-Zelle, sondern vom naechsten
    # erreichbaren Nicht-Override-Repraesentanten (abschnitt-2, jetzt max Last).
    assert reps["abschnitt-1"] == reps["abschnitt-2"] == "abschnitt-2"


def test_representative_override_cell_unreachable_yields_none():
    """Eine unerreichbare Override-Zelle wird weder Repraesentant noch erbt sie —
    sie bekommt ``None`` (ehrlicher Nicht-Urteils-Zustand, kein „frei")."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.5),
        "abschnitt-2": _status("abschnitt-2", 2, margin=None, fraction=0.0),
    }
    reps = representative_by_row(plan, status_by_id, override_ids={"abschnitt-2"})
    assert reps["abschnitt-2"] is None
    assert reps["abschnitt-1"] == "abschnitt-1"


# --- combine_printability: Freigang (Stufe 1) short-circuit --------------------


def _freigang(
    too_thick: bool, excess: float = 0.0, *, tcp_provisional: bool = False
) -> FreigangCheck:
    return FreigangCheck(
        wall_thickness_mm=300.0,
        free_length_mm=120.0,
        wrist_radius_mm=60.0,
        printable_depth_mm=180.0,
        too_thick=too_thick,
        excess_mm=excess,
        levers=("Tiefenteilung",) if too_thick else (),
        tcp_provisional=tcp_provisional,
    )


def test_too_thick_marks_every_part_red_as_presumed_without_pruef_tuer():
    """Zu dicke Wand ⇒ jedes Teil ``too_thick`` (wand-weit), aber **als Vermutung**
    (``presumed=True``, Issue #177): das Freigang-Kriterium ist höhenblind (Wandhöhen-
    Wache #167 fehlt), darum ist „zu dick" nie eine geprüfte Gewissheit. Die Prüf-Tür
    entfällt bewusst (Denkmal-Fall, Stufe 1) — das Überspringen ist ehrlich ausgewiesen."""
    plan = _grid_plan(n_length=2, n_height=2)
    out = combine_printability(plan, _freigang(True, excess=176.4), {}, {})
    assert len(out) == 4
    for pr in out.values():
        assert pr.verdict == VERDICT_TOO_THICK
        assert pr.collides and not pr.printable
        assert pr.presumed is True  # #177: vermutlich, nie geprüfte Gewissheit
        assert pr.representative_id is None  # kein Prüf-Tür-Repräsentant
        assert pr.excess_mm == pytest.approx(176.4)
        assert pr.tcp_provisional is False  # bestätigter TCP ⇒ Feld fehlt in to_dict
        assert "tcp_provisional" not in pr.to_dict()


def test_too_thick_with_provisional_tcp_is_never_certain_red():
    """Provisorischer TCP (Issue #177/B9): ``too_thick`` trägt ``tcp_provisional=True``
    und bleibt ``presumed`` — kein „sicher unmöglich" aus einem geschätzten TCP. Das
    Vorläufigkeits-Feld ist sichtbar (in ``to_dict``)."""
    plan = _grid_plan(n_length=1, n_height=1)
    out = combine_printability(
        plan, _freigang(True, excess=90.0, tcp_provisional=True), {}, {}
    )
    (pr,) = out.values()
    assert pr.verdict == VERDICT_TOO_THICK
    assert pr.presumed is True
    assert pr.tcp_provisional is True
    assert pr.to_dict()["tcp_provisional"] is True


# --- combine_printability: Pruef-Tuer (Stufe 2) + Reihen-Vererbung -------------


def test_collides_on_representative_inherits_presumed_to_row():
    """Kollidiert der Repraesentant (zuletzt gedruckte Zelle, max Hindernislast), erbt
    die ganze Reihe ``collides`` — der geprueft ist NICHT ``presumed``, die erbenden
    Zellen schon (,vermutlich')."""
    plan = _grid_plan(n_length=3, n_height=1)
    status_by_id = {
        f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.5) for i in range(1, 4)
    }
    rep_by_section = representative_by_row(plan, status_by_id)  # rep = abschnitt-3
    assert rep_by_section["abschnitt-1"] == "abschnitt-3"
    verdict = _FakeVerdict(
        collides=True, causer_link=2, causer_against="modul",
        penetration_mm=289.2, min_distance_mm=-289.2,
    )
    out = combine_printability(plan, _freigang(False), {"abschnitt-3": verdict}, rep_by_section)

    rep = out["abschnitt-3"]
    assert rep.verdict == VERDICT_COLLIDES and rep.presumed is False
    assert rep.representative_id == "abschnitt-3"
    # Ursache verbatim aus der Pruef-Tuer.
    assert rep.causer_link == 2 and rep.causer_against == "modul"
    assert rep.penetration_mm == pytest.approx(289.2)
    for sid in ("abschnitt-1", "abschnitt-2"):
        p = out[sid]
        assert p.verdict == VERDICT_COLLIDES and p.presumed is True
        assert p.representative_id == "abschnitt-3"
        assert p.causer_link == 2  # geerbte Ursache


def test_free_on_representative_yields_printable_and_presumed_row():
    """Sah die Pruef-Tuer den Repraesentanten (zuletzt gedruckt) frei, ist die ganze
    Reihe druckbar — der Repraesentant geprueft-gruen, die uebrigen ,vermutlich'."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.1),
        "abschnitt-2": _status("abschnitt-2", 2, margin=0.5),
    }
    rep_by_section = representative_by_row(plan, status_by_id)  # rep = abschnitt-2
    assert rep_by_section["abschnitt-1"] == "abschnitt-2"
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-2": _FakeVerdict(collides=False)}, rep_by_section
    )
    assert out["abschnitt-2"].verdict == VERDICT_PRINTABLE
    assert out["abschnitt-2"].presumed is False
    assert out["abschnitt-1"].verdict == VERDICT_PRINTABLE
    assert out["abschnitt-1"].presumed is True


def test_missing_verdict_is_unknown_never_green():
    """Fehlt fuer die Reihe ein Pruef-Tuer-Urteil (keine Geometrie), bleibt das Teil
    ``unknown`` — NICHT gruen (kein Falsch-,druckbar', Befund kein Gate)."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.5) for i in (1, 2)
    }
    rep_by_section = representative_by_row(plan, status_by_id)
    out = combine_printability(
        plan, _freigang(False), {rep_by_section["abschnitt-1"]: None}, rep_by_section
    )
    for pr in out.values():
        assert pr.verdict == VERDICT_UNKNOWN
        assert not pr.printable and not pr.known


def test_silent_freigang_never_certifies_printability():
    """Kernauflage #164: ein stummer Freigang-Befund (nicht zu dick) macht KEIN Teil
    gruen — nur die Pruef-Tuer kann ``printable`` setzen. Ohne Urteil bleibt es
    ``unknown``, nie ``printable``."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep_by_section = representative_by_row(
        plan, {"abschnitt-1": _status("abschnitt-1", 1, margin=0.5)}
    )
    # Freigang still (nicht zu dick), aber KEIN Pruef-Tuer-Urteil.
    out = combine_printability(plan, _freigang(False), {}, rep_by_section)
    assert out["abschnitt-1"].verdict == VERDICT_UNKNOWN
    assert not out["abschnitt-1"].printable


def test_row_without_representative_is_unknown_unreachable():
    """Reihe ohne gueltigen Repraesentanten (``rep_by_section[sid] is None``): das Teil
    wird ``unknown`` mit :data:`REASON_UNREACHABLE` — NIE „frei" von einer eingefrorenen
    Trajektorie erben (Issue #174/B13). Der Erreichbarkeits-Kanal (#180) wird mitgetragen."""
    from fgc.decompose.printability import REASON_UNREACHABLE

    plan = _grid_plan(n_length=2, n_height=1)
    # Keine Zelle erreichbar ⇒ representative_by_row liefert None fuer beide.
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=None, fraction=0.0),
        "abschnitt-2": _status("abschnitt-2", 2, margin=None, fraction=0.0),
    }
    rep_by_section = representative_by_row(plan, status_by_id)
    assert rep_by_section == {"abschnitt-1": None, "abschnitt-2": None}
    # Auch wenn ein (nie aufgerufenes) Pruef-Tuer-Urteil vorlaege: None ⇒ unknown.
    out = combine_printability(
        plan, _freigang(False), {}, rep_by_section, status_by_id
    )
    for pr in out.values():
        assert pr.verdict == VERDICT_UNKNOWN and not pr.printable
        assert pr.reason == REASON_UNREACHABLE
        assert pr.to_dict()["reason"] == REASON_UNREACHABLE
        assert pr.reachable is False  # zweiter Kanal ablesbar


def test_none_verdict_is_ungeprueft_no_geometry():
    """``None`` fuer die Reihe (Pruef-Tuer unzustaendig) ⇒ ``unknown`` mit Grund
    ``no_geometry`` (Issue #170) — nie gruen."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.5) for i in (1, 2)}
    rep_by_section = representative_by_row(plan, status_by_id)
    out = combine_printability(
        plan, _freigang(False), {rep_by_section["abschnitt-1"]: None}, rep_by_section
    )
    for pr in out.values():
        assert pr.verdict == VERDICT_UNKNOWN
        assert pr.reason == REASON_NO_GEOMETRY
        assert not pr.printable
        assert pr.to_dict()["reason"] == REASON_NO_GEOMETRY


def test_error_sentinel_is_ungeprueft_error_never_green():
    """Ein Fehler-String (:data:`REASON_ERROR`, geschluckte Ausnahme) wird als
    ``unknown``/``error`` gelesen — NIE als freies Urteil (der Fehler B12: ein Absturz
    darf nicht zu „frei" werden)."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {f"abschnitt-{i}": _status(f"abschnitt-{i}", i, margin=0.5) for i in (1, 2)}
    rep_by_section = representative_by_row(plan, status_by_id)
    out = combine_printability(
        plan, _freigang(False), {rep_by_section["abschnitt-1"]: REASON_ERROR}, rep_by_section
    )
    for pr in out.values():
        assert pr.verdict == VERDICT_UNKNOWN
        assert pr.reason == REASON_ERROR
        assert not pr.printable and not pr.collides
        assert pr.to_dict()["reason"] == REASON_ERROR


def test_no_geometry_sentinel_distinct_from_error():
    """Beide Gruende fuehren zu ``unknown`` (nie „frei"), bleiben aber unterscheidbar
    (Kern von B5: totes Pruefsystem ≠ unzustaendige Bibliothek)."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep = representative_by_row(plan, {"abschnitt-1": _status("abschnitt-1", 1, margin=0.5)})
    no_geo = combine_printability(plan, _freigang(False), {"abschnitt-1": REASON_NO_GEOMETRY}, rep)
    err = combine_printability(plan, _freigang(False), {"abschnitt-1": REASON_ERROR}, rep)
    assert no_geo["abschnitt-1"].reason == REASON_NO_GEOMETRY
    assert err["abschnitt-1"].reason == REASON_ERROR


# --- combine_printability: Ampel-Konjunktion Erreichbarkeit UND Druckbarkeit (#180) ---


def test_partial_reachability_never_yields_green():
    """Kern von Issue #180 (B33): ein Teil, das die Prüf-Tür **frei** sieht, aber nur
    **teilweise erreichbar** ist, wird **nicht** grün. Der Prüf-Tür-Kanal bleibt ehrlich
    (``verdict == printable``), der Erreichbarkeits-Kanal (``reachable``) macht ``.printable``
    trotzdem falsch — beide Kanäle bleiben getrennt ablesbar."""
    plan = _grid_plan(n_length=2, n_height=1)
    # abschnitt-1 voll erreichbar, abschnitt-2 nur teilweise (vor #164 rot).
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.5, fraction=1.0),
        "abschnitt-2": _status("abschnitt-2", 2, margin=0.4, fraction=0.5),
    }
    # Jede Zelle ihr eigener Repräsentant (Prüf-Tür sieht BEIDE frei).
    rep_by_section = {"abschnitt-1": "abschnitt-1", "abschnitt-2": "abschnitt-2"}
    verdicts = {
        "abschnitt-1": _FakeVerdict(collides=False),
        "abschnitt-2": _FakeVerdict(collides=False),
    }
    out = combine_printability(plan, _freigang(False), verdicts, rep_by_section, status_by_id)

    # Erreichbar + frei ⇒ grün.
    assert out["abschnitt-1"].verdict == VERDICT_PRINTABLE
    assert out["abschnitt-1"].printable is True
    assert out["abschnitt-1"].reachable is True
    # Teilweise unerreichbar: Prüf-Tür-Kanal ehrlich „printable", aber NICHT grün.
    assert out["abschnitt-2"].verdict == VERDICT_PRINTABLE
    assert out["abschnitt-2"].printable is False
    assert out["abschnitt-2"].reachable is False
    assert out["abschnitt-2"].reachable_fraction == pytest.approx(0.5)


def test_reachability_channel_serialized_only_when_unreachable():
    """Byte-Gleichheit (#180): der Erreichbarkeits-Kanal erscheint im ``to_dict`` NUR,
    wenn das Teil nicht voll erreichbar ist — sonst bleibt das Urteil byte-gleich (wie
    ``reason`` bei #170)."""
    reachable = PartPrintability("a", VERDICT_PRINTABLE, presumed=False)  # default reachable
    assert "reachable" not in reachable.to_dict()
    unreachable = PartPrintability(
        "b", VERDICT_PRINTABLE, presumed=False, reachable=False, reachable_fraction=0.5
    )
    d = unreachable.to_dict()
    assert d["reachable"] is False and d["reachable_fraction"] == pytest.approx(0.5)


def test_reachability_carried_on_all_verdicts_without_changing_color():
    """Der zweite Kanal wird auf ALLEN Urteilen mitgetragen (beide Kanäle ablesbar),
    ändert aber nur beim ``printable``-Teil die Farbe (collides/too_thick/unknown sind
    ohnehin nicht grün)."""
    plan = _grid_plan(n_length=1, n_height=1)
    status_by_id = {"abschnitt-1": _status("abschnitt-1", 1, margin=0.4, fraction=0.5)}
    rep = {"abschnitt-1": "abschnitt-1"}
    # collides + unerreichbar ⇒ bleibt rot, trägt aber den Kanal.
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-1": _FakeVerdict(collides=True, causer_link=2)},
        rep, status_by_id,
    )
    pr = out["abschnitt-1"]
    assert pr.verdict == VERDICT_COLLIDES and not pr.printable
    assert pr.reachable is False and pr.reachable_fraction == pytest.approx(0.5)


def test_no_status_by_id_is_noop_conjunction():
    """Ohne ``status_by_id`` (Altaufrufer/#164-Test) gelten alle Teile als erreichbar —
    die Konjunktion ist ein No-op, grün bleibt grün (Rückwärtskompatibilität)."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep = {"abschnitt-1": "abschnitt-1"}
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-1": _FakeVerdict(collides=False)}, rep
    )
    assert out["abschnitt-1"].printable is True
    assert out["abschnitt-1"].reachable is True


def test_no_freigang_at_all_still_uses_pruef_tuer():
    """Ohne Freigang-Befund (``None`` — kein Endeffektor): die Pruef-Tuer entscheidet
    weiterhin (kein short-circuit), gruen nur aus ihr."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep_by_section = representative_by_row(
        plan, {"abschnitt-1": _status("abschnitt-1", 1, margin=0.5)}
    )
    out = combine_printability(
        plan, None, {"abschnitt-1": _FakeVerdict(collides=False)}, rep_by_section
    )
    assert out["abschnitt-1"].verdict == VERDICT_PRINTABLE


# --- combine_printability: Pruef-Vorbehalte durchreichen (Issue #182) ----------


def test_check_door_caveats_are_carried_through_to_verdict():
    """Kern von Issue #182 (B15/B37/B38): die Ehrlichkeits-Metadaten der Pruef-Tuer
    (travel_thinned, n_checked/n_samples, tool_provisional) gingen beim Verheiraten
    bislang verloren — jetzt werden sie additiv auf das Urteil des Repraesentanten
    UND der erbenden Zellen der Reihe uebernommen (dieselbe Pruefung galt fuer die
    ganze Reihe)."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.1),
        "abschnitt-2": _status("abschnitt-2", 2, margin=0.5),
    }
    rep_by_section = representative_by_row(plan, status_by_id)  # rep = abschnitt-2
    verdict = _FakeVerdict(
        collides=False, travel_thinned=True, n_checked=42, n_samples=210,
        tool_provisional=True,
    )
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-2": verdict}, rep_by_section, status_by_id
    )
    for sid in ("abschnitt-1", "abschnitt-2"):
        pr = out[sid]
        assert pr.travel_thinned is True
        assert pr.n_checked == 42
        assert pr.n_samples == 210
        assert pr.tool_provisional is True
    d = out["abschnitt-2"].to_dict()
    assert d["travel_thinned"] is True
    assert d["n_checked"] == 42
    assert d["n_samples"] == 210
    assert d["tool_provisional"] is True


def test_check_door_caveats_default_to_false_and_stay_byte_identical():
    """Ein voller, unausgeduennter Lauf ohne provisorischen Endeffektor (Altverhalten
    vor #182 bzw. travel_stride<=1): die neuen Felder bleiben False/None und
    verschwinden ganz aus ``to_dict`` (additiv, byte-gleich zu vor #182)."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep_by_section = representative_by_row(
        plan, {"abschnitt-1": _status("abschnitt-1", 1, margin=0.5)}
    )
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-1": _FakeVerdict(collides=False)}, rep_by_section
    )
    pr = out["abschnitt-1"]
    assert pr.travel_thinned is False
    assert pr.n_checked is None
    assert pr.n_samples is None
    assert pr.tool_provisional is False
    d = pr.to_dict()
    assert "travel_thinned" not in d
    assert "n_checked" not in d
    assert "n_samples" not in d
    assert "tool_provisional" not in d


def test_too_thick_never_carries_pruef_tuer_caveats():
    """``too_thick`` hat gar keine Pruef-Tuer gesehen (Freigang-Kurzschluss, #163) — die
    Pruef-Vorbehalte bleiben auf ihrem Default (kein irrefuehrendes 'ausgeduennt
    geprueft' fuer ein Urteil, das die Pruef-Tuer nie erreicht hat)."""
    plan = _grid_plan(n_length=1, n_height=1)
    out = combine_printability(plan, _freigang(True, excess=50.0), {}, {})
    pr = out["abschnitt-1"]
    assert pr.verdict == VERDICT_TOO_THICK
    assert pr.travel_thinned is False
    assert pr.n_checked is None
    assert pr.n_samples is None
    assert pr.tool_provisional is False


# --- Kollisions-ORT der Pruef-Tuer (Issue #181, Vorarbeit fuer #165) -----------


def test_collision_location_is_carried_through_to_verdict():
    """Kern von Issue #181: der Kollisions-ORT der Pruef-Tuer (schlimmster Original-
    Index, Schicht, Verursacher-Position, rote Intervalle) geht beim Verheiraten
    NICHT verloren — additiv auf das Urteil des Repraesentanten UND der erbenden
    Zellen der Reihe uebernommen (dieselbe Pruefung galt fuer die ganze Reihe,
    genau wie die Pruef-Vorbehalte aus #182)."""
    plan = _grid_plan(n_length=2, n_height=1)
    status_by_id = {
        "abschnitt-1": _status("abschnitt-1", 1, margin=0.1),
        "abschnitt-2": _status("abschnitt-2", 2, margin=0.5),
    }
    rep_by_section = representative_by_row(plan, status_by_id)  # rep = abschnitt-2
    red_intervals = ({"link": 2, "against": "modul", "start_index": 3, "end_index": 9,
                       "worst_index": 6, "min_distance_mm": -12.5},)
    verdict = _FakeVerdict(
        collides=True, causer_link=2, causer_against="modul",
        worst_original_index=6, worst_layer=3, causer_position_mm=(10.0, 20.0, 30.0),
        red_intervals=red_intervals,
    )
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-2": verdict}, rep_by_section, status_by_id
    )
    for sid in ("abschnitt-1", "abschnitt-2"):
        pr = out[sid]
        assert pr.worst_original_index == 6
        assert pr.worst_layer == 3
        assert pr.causer_position_mm == (10.0, 20.0, 30.0)
        assert pr.red_intervals == red_intervals
    d = out["abschnitt-2"].to_dict()
    assert d["worst_original_index"] == 6
    assert d["worst_layer"] == 3
    assert d["causer_position_mm"] == [10.0, 20.0, 30.0]
    assert d["red_intervals"] == list(red_intervals)


def test_collision_location_absent_stays_byte_identical():
    """Ohne bekannten Ort (Altverhalten vor #181, bzw. ein freies Urteil ohne
    Verursacher): die neuen Felder bleiben None/leer und verschwinden ganz aus
    ``to_dict`` (additiv, byte-gleich zu vor #181)."""
    plan = _grid_plan(n_length=1, n_height=1)
    rep_by_section = representative_by_row(
        plan, {"abschnitt-1": _status("abschnitt-1", 1, margin=0.5)}
    )
    out = combine_printability(
        plan, _freigang(False), {"abschnitt-1": _FakeVerdict(collides=False)}, rep_by_section
    )
    pr = out["abschnitt-1"]
    assert pr.worst_original_index is None
    assert pr.worst_layer is None
    assert pr.causer_position_mm is None
    assert pr.red_intervals == ()
    d = pr.to_dict()
    assert "worst_original_index" not in d
    assert "worst_layer" not in d
    assert "causer_position_mm" not in d
    assert "red_intervals" not in d


def test_too_thick_never_carries_collision_location():
    """``too_thick`` hat gar keine Pruef-Tuer gesehen (Freigang-Kurzschluss, #163) —
    kein erfundener Kollisions-Ort fuer ein Urteil, das die Pruef-Tuer nie
    erreicht hat (Issue #181, dieselbe Haltung wie #182)."""
    plan = _grid_plan(n_length=1, n_height=1)
    out = combine_printability(plan, _freigang(True, excess=50.0), {}, {})
    pr = out["abschnitt-1"]
    assert pr.verdict == VERDICT_TOO_THICK
    assert pr.worst_original_index is None
    assert pr.worst_layer is None
    assert pr.causer_position_mm is None
    assert pr.red_intervals == ()


# --- PartPrintability: Eigenschaften + Serialisierung -------------------------


def test_partprintability_properties_and_to_dict():
    pr = PartPrintability(
        "abschnitt-1", VERDICT_COLLIDES, presumed=True, representative_id="abschnitt-2",
        causer_link=4, causer_against="modul", penetration_mm=206.0, min_distance_mm=-206.0,
    )
    assert pr.collides and not pr.printable and pr.known
    d = pr.to_dict()
    assert d == {
        "verdict": "collides",
        "presumed": True,
        "representative_id": "abschnitt-2",
        "causer_link": 4,
        "causer_against": "modul",
        "penetration_mm": 206.0,
        "min_distance_mm": -206.0,
        "excess_mm": None,
    }
    printable = PartPrintability("a", VERDICT_PRINTABLE, presumed=False)
    assert printable.printable and not printable.collides

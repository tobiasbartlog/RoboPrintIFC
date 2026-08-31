"""Zielfunktion der Zerlegungs-Suche (Issue #212, PRD #183 Stufe 3).

Geprueft wird das externe Verhalten des Komparators (`fgc.decompose.objective`)
an denselben Kandidaten in beiden Lesarten: lexikographisch (Default) vs.
gewichtete Summe; das harte Erreichbarkeits-K.-o. schlaegt jeden Score; ein
Quantisierungs-Gleichstand reicht die Entscheidung ans nachrangige Kriterium
durch. Dazu der Setter (`set_objective_for_job`): echo-fest deklarierte
Veraltung (#199, ``bump_if_changed`` auf ``cutplan``), sparse Persistenz
(Default entfernt das Feld — Altprojekte byte-gleich) und die Lauf-Provenienz
des Zerlegungslaufs, die die komplette Config traegt (ADR-004).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fgc import domain
from fgc.decompose import (
    CRITERIA,
    DEFAULT_QUANT_STEPS,
    DEFAULT_WEIGHTS,
    KriterienWerte,
    ObjectiveConfig,
    candidate_key,
    compare_candidates,
    objective_from_job,
    quantize,
)
from fgc.pipeline.actions import (
    create_project_from_ifc,
    propose_decomposition,
    reassess_walls_for_robot,
    set_objective_for_job,
    set_print_job,
)

ROBOT = "doosan_m1013"


def _werte(
    erreichbar: bool = True,
    umsetzvorgaenge: float = 2.0,
    fugenflaeche_mm2: float = 400_000.0,
    kinematische_marge_mm: float = 100.0,
    volumen_cv: float = 0.10,
) -> KriterienWerte:
    return KriterienWerte(
        erreichbar=erreichbar,
        umsetzvorgaenge=umsetzvorgaenge,
        fugenflaeche_mm2=fugenflaeche_mm2,
        kinematische_marge_mm=kinematische_marge_mm,
        volumen_cv=volumen_cv,
    )


# --- Komparator: lexikographisch vs. gewichtete Summe (AC 1) ---------------------


def test_lexicographic_vs_sum_disagree_on_same_candidates():
    """Dieselben zwei Kandidaten, beide Lesarten: lexikographisch gewinnt der mit
    weniger Umsetzvorgaengen (kein Aufwiegen — kein c_v kompensiert ein Einmessen);
    als gewichtete Summe kompensieren die uebrigen Kriterien genau das."""
    wenig_umsetzen = _werte(
        umsetzvorgaenge=2.0, fugenflaeche_mm2=900_000.0, kinematische_marge_mm=25.0, volumen_cv=0.40
    )
    viel_umsetzen = _werte(
        umsetzvorgaenge=3.0,
        fugenflaeche_mm2=100_000.0,
        kinematische_marge_mm=300.0,
        volumen_cv=0.05,
    )

    lex = ObjectiveConfig()  # Default: aufwiegen AUS = lexikographisch
    assert compare_candidates(wenig_umsetzen, viel_umsetzen, lex) == -1

    summe = ObjectiveConfig(aufwiegen=True, weights=dict(DEFAULT_WEIGHTS))
    assert compare_candidates(wenig_umsetzen, viel_umsetzen, summe) == 1


def test_default_ranking_is_grill_order():
    """Default-Rangfolge (Grill 2026-07-14): Umsetzvorgaenge > Fugenflaeche >
    kinematische Marge > c_v — abgeleitet aus den Default-Gewichten."""
    assert ObjectiveConfig().ranking() == CRITERIA


def test_ranking_follows_weights_not_declaration_order():
    weights = {
        "umsetzvorgaenge": 1.0,
        "fugenflaeche": 2.0,
        "kinematische_marge": 3.0,
        "volumen_cv": 4.0,
    }
    config = ObjectiveConfig(weights=weights)
    assert config.ranking() == tuple(reversed(CRITERIA))
    # Und der Komparator folgt der neuen Rangfolge: c_v entscheidet zuerst.
    gutes_cv = _werte(umsetzvorgaenge=9.0, volumen_cv=0.05)
    schlechtes_cv = _werte(umsetzvorgaenge=1.0, volumen_cv=0.60)
    assert compare_candidates(gutes_cv, schlechtes_cv, config) == -1


def test_marge_direction_is_maximized():
    """Groessere kinematische Marge = besser (der Komparator negiert intern)."""
    config = ObjectiveConfig()
    viel_marge = _werte(kinematische_marge_mm=300.0)
    wenig_marge = _werte(kinematische_marge_mm=50.0)
    assert compare_candidates(viel_marge, wenig_marge, config) == -1


# --- Hartes K.-o.: Erreichbarkeit schlaegt jeden Score (AC 1) --------------------


@pytest.mark.parametrize("aufwiegen", [False, True])
def test_ko_beats_every_score(aufwiegen):
    """Ein unerreichbarer Kandidat mit perfekten Werten verliert gegen einen
    erreichbaren mit miserablen — in beiden Lesarten (kein Gewicht wiegt das auf)."""
    config = ObjectiveConfig(aufwiegen=aufwiegen)
    perfekt_aber_ko = _werte(
        erreichbar=False,
        umsetzvorgaenge=1.0,
        fugenflaeche_mm2=0.0,
        kinematische_marge_mm=500.0,
        volumen_cv=0.01,
    )
    miserabel_aber_erreichbar = _werte(
        erreichbar=True,
        umsetzvorgaenge=99.0,
        fugenflaeche_mm2=9e9,
        kinematische_marge_mm=1.0,
        volumen_cv=5.0,
    )
    assert compare_candidates(miserabel_aber_erreichbar, perfekt_aber_ko, config) == -1
    assert candidate_key(perfekt_aber_ko, config)[0] == 1
    assert candidate_key(miserabel_aber_erreichbar, config)[0] == 0


# --- Quantisierung: Gleichstand reicht ans nachrangige Kriterium durch (AC 1) ----


def test_quantization_tie_passes_to_next_criterion():
    """Zwei Kandidaten im selben Fugenflaechen-Bin (Differenz < Schrittweite):
    die Entscheidung faellt beim nachrangigen Kriterium (Marge) — obwohl der
    Marge-Sieger die nominell GROESSERE Fugenflaeche hat."""
    config = ObjectiveConfig()
    step = config.quant_steps["fugenflaeche"]
    a = _werte(fugenflaeche_mm2=100_000.0 + 0.2 * step, kinematische_marge_mm=200.0)
    b = _werte(fugenflaeche_mm2=100_000.0, kinematische_marge_mm=100.0)
    assert quantize(a.fugenflaeche_mm2, step) == quantize(b.fugenflaeche_mm2, step)
    assert compare_candidates(a, b, config) == -1


def test_full_tie_is_zero():
    config = ObjectiveConfig()
    a = _werte()
    b = _werte(fugenflaeche_mm2=a.fugenflaeche_mm2 + 1.0)  # gleicher Bin
    assert compare_candidates(a, b, config) == 0


def test_quantize_rejects_non_positive_step():
    with pytest.raises(ValueError, match="Schrittweite"):
        quantize(1.0, 0.0)


# --- Config-Validierung: Gleichstand im Aus-Modus, unbekannte Kriterien ----------


def test_weight_tie_rejected_in_lexicographic_mode():
    weights = dict(DEFAULT_WEIGHTS, fugenflaeche=DEFAULT_WEIGHTS["umsetzvorgaenge"])
    with pytest.raises(ValueError, match="Gleichstand"):
        ObjectiveConfig(aufwiegen=False, weights=weights)


def test_weight_tie_allowed_in_sum_mode():
    weights = dict(DEFAULT_WEIGHTS, fugenflaeche=DEFAULT_WEIGHTS["umsetzvorgaenge"])
    config = ObjectiveConfig(aufwiegen=True, weights=weights)  # kein Fehler
    assert config.aufwiegen is True


def test_unknown_criterion_rejected():
    with pytest.raises(ValueError, match="Unbekannte Kriterien"):
        ObjectiveConfig(weights={**DEFAULT_WEIGHTS, "teilezahl": 5.0})


def test_non_positive_weight_rejected():
    with pytest.raises(ValueError, match="positiv"):
        ObjectiveConfig(weights={**DEFAULT_WEIGHTS, "volumen_cv": 0.0})


def test_from_dict_roundtrip_and_default():
    """from_dict(None) = Default; to_dict → from_dict ist verlustfrei; Teil-Bloecke
    erben fehlende Kriterien aus den Defaults (fail-soft additiv)."""
    assert ObjectiveConfig.from_dict(None) == ObjectiveConfig()
    config = ObjectiveConfig(aufwiegen=True, weights={**DEFAULT_WEIGHTS, "volumen_cv": 9.0})
    assert ObjectiveConfig.from_dict(config.to_dict()) == config
    partial = ObjectiveConfig.from_dict({"weights": {"umsetzvorgaenge": 7.0}})
    assert partial.weights["umsetzvorgaenge"] == 7.0
    assert partial.weights["volumen_cv"] == DEFAULT_WEIGHTS["volumen_cv"]
    assert partial.quant_steps == DEFAULT_QUANT_STEPS


# --- Setter: echo-fest (bump_if_changed), sparse Persistenz (AC 2) ---------------


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=2600.0)])


def _project_with_job(tmp_path):
    projects_dir = tmp_path / "projects"
    runs_dir = tmp_path / "runs"
    creation = create_project_from_ifc(
        "Testhaus", Path("modell.ifc"), ROBOT, "src",
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    slug = creation.project_dir.name
    set_print_job(slug, "WALLAAAAAAAAAAAAAAAAAA", str(creation.overview_run_dir),
                  projects_dir=projects_dir)
    reassess_walls_for_robot(slug, ROBOT, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    return slug, projects_dir, runs_dir


NON_DEFAULT_WEIGHTS = {
    "umsetzvorgaenge": 8.0,
    "fugenflaeche": 3.0,
    "kinematische_marge": 2.0,
    "volumen_cv": 1.0,
}


def test_set_objective_persists_and_bumps_cutplan_once(tmp_path, stub_walls):
    """Der Setter schreibt den sparse Block schema-valide und bumpt ``cutplan``
    genau bei tatsaechlicher Aenderung — derselbe Wert erneut bumpt nicht (echo-fest)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    before = load_project(pdir)["print_jobs"][0]
    cutplan_before = ((before.get("revisions") or {}).get("inputs") or {}).get("cutplan", 0)

    result = set_objective_for_job(slug, False, NON_DEFAULT_WEIGHTS, projects_dir=projects_dir)
    job = result.artifact["print_jobs"][0]
    assert job["objective"] == {"aufwiegen": False, "weights": NON_DEFAULT_WEIGHTS}
    assert result.objective["weights"] == NON_DEFAULT_WEIGHTS
    domain.validate(result.artifact, "project")
    assert job["revisions"]["inputs"]["cutplan"] == cutplan_before + 1

    # Echo: derselbe Wert erneut — kein weiterer Bump (bump_if_changed, #199).
    echo = set_objective_for_job(slug, False, NON_DEFAULT_WEIGHTS, projects_dir=projects_dir)
    echo_job = echo.artifact["print_jobs"][0]
    assert echo_job["revisions"]["inputs"]["cutplan"] == cutplan_before + 1
    assert echo_job == job


def test_set_objective_default_is_sparse_and_byte_compatible(tmp_path, stub_walls):
    """Default-Config entfernt das Feld (Altprojekte byte-gleich); der Rueckweg
    Nicht-Default → Default bumpt ``cutplan`` erneut (tatsaechliche Aenderung)."""
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)

    from fgc.project import load_project, project_dir_for

    pdir = project_dir_for(slug, projects_dir=projects_dir)
    baseline_job = load_project(pdir)["print_jobs"][0]
    assert "objective" not in baseline_job

    # Default explizit speichern: Feld bleibt weg, nichts bumpt (echo-fest).
    default_echo = set_objective_for_job(slug, projects_dir=projects_dir)
    assert default_echo.artifact["print_jobs"][0] == baseline_job
    assert default_echo.objective == {"aufwiegen": False, "weights": DEFAULT_WEIGHTS}

    set_objective_for_job(slug, True, NON_DEFAULT_WEIGHTS, projects_dir=projects_dir)
    back = set_objective_for_job(slug, projects_dir=projects_dir)
    back_job = back.artifact["print_jobs"][0]
    assert "objective" not in back_job
    # Zwei tatsaechliche Aenderungen (hin und zurueck) = zwei Bumps.
    base_cutplan = ((baseline_job.get("revisions") or {}).get("inputs") or {}).get("cutplan", 0)
    assert back_job["revisions"]["inputs"]["cutplan"] == base_cutplan + 2


def test_set_objective_rejects_tie_in_lexicographic_mode(tmp_path, stub_walls):
    slug, projects_dir, _runs_dir = _project_with_job(tmp_path)
    tied = dict(DEFAULT_WEIGHTS, volumen_cv=DEFAULT_WEIGHTS["kinematische_marge"])
    with pytest.raises(ValueError, match="Gleichstand"):
        set_objective_for_job(slug, False, tied, projects_dir=projects_dir)


# --- Lauf-Provenienz traegt die komplette Config (AC 3, ADR-004) -----------------


def test_decompose_run_provenance_carries_full_objective_config(tmp_path, stub_walls):
    """Der Zerlegungslauf stempelt die KOMPLETTE wirksame Config (Lesart +
    Gewichte + Quantisierungs-Schrittweiten) in seine Provenienz — auch fuer den
    Default (Altprojekt ohne ``objective``-Feld)."""
    slug, projects_dir, runs_dir = _project_with_job(tmp_path)

    # Default (kein objective-Feld): Provenienz traegt die gepinnte Default-Config.
    result = propose_decomposition(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    artifact = json.loads((result.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact, "decompose")
    assert artifact["provenance"]["objective"] == ObjectiveConfig().to_dict()
    assert artifact["provenance"]["objective"]["quant_steps"] == DEFAULT_QUANT_STEPS

    # Konfiguriert: die Provenienz traegt exakt die wirksame Job-Config.
    set_objective_for_job(slug, True, NON_DEFAULT_WEIGHTS, projects_dir=projects_dir)
    result2 = propose_decomposition(slug, "src", projects_dir=projects_dir, runs_dir=runs_dir)
    artifact2 = json.loads((result2.run_dir / "decompose.json").read_text(encoding="utf-8"))
    domain.validate(artifact2, "decompose")
    job = result2.artifact["print_jobs"][0]
    assert artifact2["provenance"]["objective"] == objective_from_job(job).to_dict()
    assert artifact2["provenance"]["objective"]["aufwiegen"] is True
    assert artifact2["provenance"]["objective"]["weights"] == NON_DEFAULT_WEIGHTS

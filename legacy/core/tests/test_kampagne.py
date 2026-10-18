"""Datenkampagne des Surrogat-Kaltstarts (Issue #218, PRD #183 Stufe 4, US 24).

Prüft den **reinen Kampagnen-Kern** (`fgc.decompose.kampagne`) an seinen Nähten —
das Etikettier-Orakel kommt als Fake herein (Muster wie `assess_plan` mit
injiziertem `check_representative`, #190), sodass die Tests ohne Geometrie schnell
laufen. Deckt die Akzeptanzkriterien ab: Determinismus (gleicher Plan ⇒ gleiche
Kandidatenmenge), Label-Quelle je Etikett + ausgewiesene Herkunftsverteilung,
CPU-only-Fallback vollständig etikettiert, Umfangsansage + Abbruch/Teilstand,
Datensatz-Artefakt mit Provenienz.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fgc.decompose.kampagne import (
    DATASET_KIND,
    LABEL_CPU_EXACT,
    LABEL_GPU_CPU_GRENZBAND,
    LABEL_GPU_STICHPROBEN_AUDIT,
    CampaignRun,
    CandidateLabel,
    LabeledSample,
    SamplingPlan,
    campaign_scope,
    dataset_artifact,
    run_campaign,
)
from fgc.decompose.pruefung import FEATURE_SCHEMA_VERSION, PruefSample
from fgc.pipeline.provenance import make_provenance

# --- Fixtures / Fakes ---------------------------------------------------------

#: Kleiner, schneller Plan (2 Wände × Band-Raster bis cap=2 = je 4 Kandidaten-
#: Zerlegungen, Höhenreihen aufsummiert) für die reinen Tests.
SMALL_PLAN = SamplingPlan(
    lengths_mm=(800.0,), heights_mm=(1200.0, 2000.0), thicknesses_mm=(200.0,), cap=2
)


def _free_label(candidate) -> CandidateLabel:
    """Ein CPU-exaktes „frei"-Etikett (der Fallback-Weg, US 24)."""
    return CandidateLabel(
        verdict={"label": "printable", "collides": False}, label_source=LABEL_CPU_EXACT
    )


#: Stabile Zuordnung Kandidat → Label-Quelle (rotiert über den Kandidaten-Index,
#: sodass alle drei Quellen deterministisch vorkommen — auch der Audit).
_ROTATE = (LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND, LABEL_GPU_STICHPROBEN_AUDIT)
_SOURCE_BY_KEY = {
    c.key: _ROTATE[i % 3] for i, c in enumerate(SMALL_PLAN.candidates())
}


def _mixed_label(candidate) -> CandidateLabel:
    """Etikett mit **wechselnder** Label-Quelle — für die Herkunftsverteilung."""
    src = _SOURCE_BY_KEY[candidate.key]
    return CandidateLabel(verdict={"collides": candidate.order % 2 == 0}, label_source=src)


# --- Determinismus (US 25) ----------------------------------------------------


def test_plan_candidates_deterministic():
    """Gleicher Plan ⇒ bit-gleiche Kandidatenfolge (Akzeptanz: deterministisch)."""
    keys1 = [c.key for c in SMALL_PLAN.candidates()]
    keys2 = [c.key for c in SMALL_PLAN.candidates()]
    assert keys1 == keys2
    assert len(keys1) == len(set(keys1))  # eindeutige Kandidaten


def test_n_candidates_matches_enumeration():
    """``n_candidates`` (rechnerisch) == tatsächlich aufgezählte Kandidaten."""
    assert SMALL_PLAN.n_candidates == sum(1 for _ in SMALL_PLAN.candidates())


def test_run_campaign_deterministic():
    """Gleicher Plan + gleiches Orakel ⇒ identische Datensätze (Byte-Vergleich)."""
    run1 = run_campaign(SMALL_PLAN, _free_label)
    run2 = run_campaign(SMALL_PLAN, _free_label)
    assert [ls.to_dict() for ls in run1.samples] == [ls.to_dict() for ls in run2.samples]


# --- CPU-only-Fallback: vollständig etikettiert (Akzeptanz) -------------------


def test_cpu_only_fallback_labels_every_candidate():
    """Ein Lauf mit CPU-exaktem Orakel endet **vollständig** etikettiert (US 24)."""
    run = run_campaign(SMALL_PLAN, _free_label)
    assert run.n_labeled == SMALL_PLAN.n_candidates
    assert not run.cancelled
    assert all(ls.label_source == LABEL_CPU_EXACT for ls in run.samples)
    assert run.training_safe_count() == run.n_labeled  # cpu-exakt ist trainingstauglich


# --- Label-Quelle je Etikett + Herkunftsverteilung (US 24) --------------------


def test_label_source_per_sample_and_distribution():
    run = run_campaign(SMALL_PLAN, _mixed_label)
    dist = run.label_source_distribution()
    # Jede Quelle ist im Verteilungs-Dict vertreten (auch mit 0), Summe == Etiketten.
    assert set(dist) == {LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND, LABEL_GPU_STICHPROBEN_AUDIT}
    assert sum(dist.values()) == run.n_labeled
    # Jedes Sample trägt seine Quelle + Trainings-Flag.
    for ls in run.samples:
        d = ls.to_dict()
        assert d["label_source"] in dist
        assert d["training_safe"] is (d["label_source"] != LABEL_GPU_STICHPROBEN_AUDIT)


def test_audit_labels_marked_non_training():
    """``gpu+stichproben-audit`` ist nicht trainingstauglich (Policy v1)."""
    run = run_campaign(SMALL_PLAN, _mixed_label)
    audit = [ls for ls in run.samples if ls.label_source == LABEL_GPU_STICHPROBEN_AUDIT]
    assert audit  # der Fake erzeugt welche
    assert all(not ls.training_safe for ls in audit)
    assert run.non_training_count() == len(audit)


def test_unknown_label_source_rejected():
    with pytest.raises(ValueError, match="Label-Quelle"):
        CandidateLabel(verdict={}, label_source="hokuspokus")


# --- Umfangsansage vor Start (Muster #175) ------------------------------------


def test_campaign_scope_announcement():
    scope = campaign_scope(SMALL_PLAN, seconds_per_label=10.0)
    assert scope.n_candidates == SMALL_PLAN.n_candidates
    assert scope.est_seconds == pytest.approx(SMALL_PLAN.n_candidates * 10.0)
    text = scope.announcement()
    assert str(SMALL_PLAN.n_candidates) in text
    assert "Kandidaten" in text


# --- Abbruch + Teilstand verwertbar (Akzeptanz) -------------------------------


def test_cancel_yields_partial_state():
    """``should_cancel`` bricht ab; der Teilstand bleibt verwertbar (#175)."""
    seen = {"n": 0}

    def _cancel_after_three() -> bool:
        return seen["n"] >= 3

    def _counting_label(candidate) -> CandidateLabel:
        seen["n"] += 1
        return _free_label(candidate)

    run = run_campaign(SMALL_PLAN, _counting_label, should_cancel=_cancel_after_three)
    assert run.cancelled
    assert run.n_labeled == 3  # vor dem 4. Etikett abgebrochen
    art = dataset_artifact(run, SMALL_PLAN, make_provenance("test"))
    assert art["partial"] is True
    assert art["cancelled"] is True
    assert len(art["samples"]) == 3


def test_limit_is_partial_mini_sample():
    run = run_campaign(SMALL_PLAN, _free_label, limit=2)
    assert run.n_labeled == 2
    art = dataset_artifact(run, SMALL_PLAN, make_provenance("test"))
    assert art["partial"] is True  # weniger als geplant ⇒ Teilstand


def test_progress_reports_done_total():
    seen: list[tuple[int, int]] = []
    run_campaign(SMALL_PLAN, _free_label, on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (SMALL_PLAN.n_candidates, SMALL_PLAN.n_candidates)


def test_oracle_failure_is_fail_soft():
    """Scheitert das Orakel an einem Kandidaten, kippt der Nachtlauf nicht (ADR-013)."""

    def _flaky(candidate) -> CandidateLabel:
        if candidate.order == 1:
            raise RuntimeError("boom")
        return _free_label(candidate)

    run = run_campaign(SMALL_PLAN, _flaky)
    assert not run.cancelled
    # der eine gescheiterte Kandidat wird übersprungen, der Rest ist etikettiert.
    assert run.n_labeled == SMALL_PLAN.n_candidates - sum(
        1 for c in SMALL_PLAN.candidates() if c.order == 1
    )


# --- Datensatz-Artefakt mit Provenienz (US 24) --------------------------------


def test_dataset_artifact_has_provenance_and_schema():
    run = run_campaign(SMALL_PLAN, _mixed_label)
    prov = make_provenance("fgc campaign --robot doosan_m1013")
    art = dataset_artifact(run, SMALL_PLAN, prov)

    assert art["kind"] == DATASET_KIND
    assert art["feature_version"] == FEATURE_SCHEMA_VERSION
    assert art["provenance"]["source"].startswith("fgc campaign")
    assert "created" in art["provenance"] and "git_commit" in art["provenance"]
    # Sampling-Plan reproduzierbar im Artefakt.
    assert art["sampling_plan"]["n_candidates"] == SMALL_PLAN.n_candidates
    # Herkunftsverteilung + Trainings-Ausweis.
    assert art["label_source_distribution"] == run.label_source_distribution()
    assert LABEL_GPU_STICHPROBEN_AUDIT in art["training"]["non_training_sources"]
    assert LABEL_CPU_EXACT in art["training"]["training_safe_sources"]
    # Jedes Sample trägt Merkmale + Urteil + Label-Quelle.
    for s in art["samples"]:
        assert set(s) >= {"section_id", "features", "verdict", "label_source", "training_safe"}


# --- Merkmals-Schema deckungsgleich mit #211 ----------------------------------


def test_feature_core_matches_pruef_schema():
    """Der Kandidaten-Kern trägt genau die #211-Felder; with_placement reichert an."""
    candidate = next(SMALL_PLAN.candidates())
    feats = candidate.feature_core()
    expected = {
        "order", "x0_mm", "x1_mm", "z0_mm", "z1_mm", "length_mm", "height_mm",
        "center_x_mm", "wall_length_mm", "wall_height_mm", "wall_thickness_mm",
        "n_earlier_parts",
    }
    assert set(feats) == expected
    assert feats["n_earlier_parts"] == candidate.order - 1

    # Platzierungs-Anreicherung über das Orakel (wie im Laufbetrieb, #211).
    placement = SimpleNamespace(
        lateral_mm=1.0, standoff_mm=700.0, stand_height_mm=0.0, yaw_rad=0.0
    )
    sample = candidate.pruef_sample({"collides": False}).with_placement(placement)
    assert isinstance(sample, PruefSample)
    assert sample.features["standoff_mm"] == 700.0
    assert sample.features["stand_height_mm"] == 0.0


def test_labeled_sample_roundtrip():
    ls = LabeledSample(
        sample=PruefSample("abschnitt-1", {"height_mm": 1.0}, {"collides": False}),
        label_source=LABEL_CPU_EXACT,
    )
    d = ls.to_dict()
    assert d["section_id"] == "abschnitt-1"
    assert d["label_source"] == LABEL_CPU_EXACT
    assert d["training_safe"] is True


def test_empty_run_distribution_all_zero():
    run = CampaignRun(n_total=5)
    assert run.label_source_distribution() == {
        LABEL_CPU_EXACT: 0, LABEL_GPU_CPU_GRENZBAND: 0, LABEL_GPU_STICHPROBEN_AUDIT: 0
    }


# --- CLI: Umfangsansage (dry-run) ---------------------------------------------


def test_cli_campaign_dry_run(capsys):
    """`fgc campaign --dry-run` zeigt die Umfangsansage, etikettiert nichts."""
    from fgc.pipeline.cli import main

    rc = main([
        "campaign", "--dry-run",
        "--lengths", "800", "--heights", "1200,2000", "--thicknesses", "200", "--cap", "2",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Datenkampagne" in out
    assert "dry-run" in out


@pytest.mark.slow
def test_cpu_exact_oracle_smoke():
    """Das **echte** CPU-exakte Orakel etikettiert einen Kandidaten über Geometrie (US 24).

    Beweist den CPU-only-Fallback ohne Fake: die volle Prüf-Tür-Kette (Quaderwand →
    slicen → simulieren → Kollisionsurteil) liefert ein ``cpu-exakt``-Etikett mit
    echtem ``collides``-Urteil. `slow` (voller Geometrie-Lauf, nicht in der Standardsuite).
    """
    from fgc.pipeline.kampagne import cpu_exact_oracle

    plan = SamplingPlan(
        lengths_mm=(800.0,), heights_mm=(1000.0,), thicknesses_mm=(200.0,), cap=1
    )
    candidate = next(plan.candidates())
    oracle = cpu_exact_oracle("doosan_m1013")
    label = oracle(candidate)
    assert label.label_source == LABEL_CPU_EXACT
    # Ein echtes Urteil (nicht der Fehler-Fallback): collides ist ein bool.
    assert isinstance(label.verdict.get("collides"), bool)
    # Die Platzierung ist gesetzt (für die Podest-/Platzierungs-Merkmale, #211).
    assert label.placement is not None


def test_cli_campaign_writes_dataset(tmp_path, monkeypatch):
    """`fgc campaign` schnürt den Datensatz — mit gefaktem Orakel (kein Geometrie-Lauf)."""
    import json

    from fgc.pipeline import kampagne as pk
    from fgc.pipeline.cli import main

    # Das (teure) CPU-exakte Orakel durch das schnelle Fake ersetzen — der Rest der
    # Orchestrierung (Provenienz, Verteilung, Schreiben) bleibt der echte Pfad.
    monkeypatch.setattr(pk, "select_oracle", lambda *a, **k: _free_label)

    out = tmp_path / "ds.json"
    rc = main([
        "campaign", "--yes", "--out", str(out),
        "--lengths", "800", "--heights", "1200", "--thicknesses", "200", "--cap", "2",
    ])
    assert rc == 0
    art = json.loads(out.read_text(encoding="utf-8"))
    assert art["kind"] == DATASET_KIND
    assert art["n_samples"] == art["sampling_plan"]["n_candidates"]
    assert art["partial"] is False
    assert art["label_source_distribution"][LABEL_CPU_EXACT] == art["n_samples"]

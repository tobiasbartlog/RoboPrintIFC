"""Surrogat-Vorsortierer (Issue #219, PRD #183 Stufe 4, US 24/25/26).

Geprueft wird:

- **Invarianz-Orakel (US 25):** mit und ohne aktiven Vorsortierer liefert die
  Beam-Suche bei gleichem Aufruf-Kontingent **denselben** besten Kandidaten und
  dasselbe Urteil — nur die Pruef-Reihenfolge (und die Zeit) aendern sich. Der
  Test verwendet einen **adversarischen** Vorsortierer (kehrt die Liste um), der
  die Reihenfolge maximal stoert, sowie ein **echtes** trainiertes Modell.
- **Trainings-Determinismus (US 25):** fester Seed ⇒ bit-gleiches Modell.
- **Policy-Filter:** nur ``cpu-exakt`` + ``gpu+cpu-grenzband`` trainieren;
  ``gpu+stichproben-audit`` (und urteilslose Zeilen) werden **verweigert**.
- **Provenienz-Validierung (US 26):** Laden mit falscher Merkmals-Version/-Liste
  schlaegt fehl; ein Altlauf ohne Modell laedt unveraendert (``load_surrogat``
  liefert ``None`` ⇒ Beam byte-gleich, US 12).

**Treffsicherheit ist bewusst KEIN Unit-Assert** (PRD Testing Decisions — sie ist
Gegenstand des Benchmarks #220).
"""

from __future__ import annotations

import json

import pytest
from test_beam_suche import WALL, FakePruefTuer, _aufgabe, _bewerte

from fgc.decompose.beam import BeamSuche
from fgc.decompose.kampagne import (
    LABEL_CPU_EXACT,
    LABEL_GPU_CPU_GRENZBAND,
    LABEL_GPU_STICHPROBEN_AUDIT,
    CampaignCandidate,
    SamplingPlan,
)
from fgc.decompose.pruefung import FEATURE_SCHEMA_VERSION
from fgc.decompose.surrogat import (
    SURROGATE_FEATURES,
    SURROGATE_MODEL_KIND,
    SurrogatModell,
    load_surrogat,
    policy_filter,
    save_surrogat,
    train_surrogat,
)

FIXED_PROV = {"source": "test", "created": "2026-07-15T00:00:00+00:00", "git_commit": "0"}


# --------------------------------------------------------------------------- #
# Synthetischer Datensatz (deckungsgleiche #211-Merkmale, gesteuertes Urteil)
# --------------------------------------------------------------------------- #


def _dataset(*, label_source: str = LABEL_CPU_EXACT, collide_rule=None, mix_audit: int = 0):
    """Baut ein Datensatz-Artefakt aus dem Kandidatenraum (echte feature_core-Merkmale).

    ``collide_rule(features) -> bool`` steuert das Urteil (Default: kollidiert, wenn
    mindestens zwei fruehere Teile als Druckstand im Weg stehen). ``mix_audit`` streut
    N nicht-trainingstaugliche ``gpu+stichproben-audit``-Zeilen dazwischen.
    """
    if collide_rule is None:
        collide_rule = lambda f: f["n_earlier_parts"] >= 2  # noqa: E731
    plan = SamplingPlan(
        lengths_mm=(800.0, 1600.0), heights_mm=(1200.0, 2000.0),
        thicknesses_mm=(200.0,), cap=2,
    )
    samples = []
    for i, cand in enumerate(plan.candidates()):
        feats = cand.feature_core()
        collides = bool(collide_rule(feats))
        audit = mix_audit > 0 and i % 3 == 0
        src = LABEL_GPU_STICHPROBEN_AUDIT if audit else label_source
        label = "collision" if collides else "printable"
        samples.append(
            {
                "section_id": cand.section_id,
                "features": feats,
                "verdict": {"label": label, "collides": collides},
                "label_source": src,
                "training_safe": src in {LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND},
            }
        )
    return {
        "kind": "surrogate-dataset",
        "schema_version": "1",
        "feature_version": FEATURE_SCHEMA_VERSION,
        "provenance": {
            "source": "fgc campaign …",
            "created": "2026-07-14T00:00:00+00:00",
            "git_commit": "abc",
        },
        "n_candidates_planned": len(samples),
        "n_samples": len(samples),
        "partial": False,
        "samples": samples,
    }


# --------------------------------------------------------------------------- #
# Trainings-Determinismus (US 25)
# --------------------------------------------------------------------------- #


def test_training_deterministisch_bitgleiches_modell():
    """Fester Seed + gleicher Datensatz ⇒ bit-gleiches Modell (US 25)."""
    ds = _dataset()
    a = train_surrogat(ds, source="s", provenance=FIXED_PROV, seed=7)
    b = train_surrogat(ds, source="s", provenance=FIXED_PROV, seed=7)
    # Das gelernte Modell (Baeume + Basiswert) ist bit-gleich.
    assert a.gb.to_dict() == b.gb.to_dict()
    # Auch das komplette Artefakt (bei gepinnter Provenienz) ist byte-gleich.
    assert json.dumps(a.to_artifact(), sort_keys=True) == json.dumps(
        b.to_artifact(), sort_keys=True
    )


def test_training_lernt_nicht_leeres_modell():
    """Das Training baut tatsaechlich Boosting-Baeume (kein leeres Modell)."""
    model = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV)
    assert len(model.gb.trees) == model.hyperparams["n_estimators"]
    # predict_proba liefert gueltige Wahrscheinlichkeiten (Sanity, KEINE Treffsicherheit).
    import numpy as np

    proba = model.gb.predict_proba(np.zeros((3, len(SURROGATE_FEATURES))))
    assert proba.shape == (3,)
    assert bool(((proba >= 0.0) & (proba <= 1.0)).all())


# --------------------------------------------------------------------------- #
# Policy-Filter — nur v1-policy-konforme Labels (Grill 2026-07-14)
# --------------------------------------------------------------------------- #


def test_policy_filter_verweigert_stichproben_audit():
    """``gpu+stichproben-audit`` wird nachweislich NICHT trainiert (nur explorativ)."""
    ds = _dataset(mix_audit=1)
    erg = policy_filter(ds["samples"])
    assert erg.n_non_training > 0  # es gab Audit-Zeilen
    assert LABEL_GPU_STICHPROBEN_AUDIT not in erg.label_source_distribution_used
    assert set(erg.label_source_distribution_used) <= {LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND}
    # Jede benutzte Zeile traegt eine trainingstaugliche Quelle + ein bool-Urteil.
    for s in erg.used:
        assert s["label_source"] in {LABEL_CPU_EXACT, LABEL_GPU_CPU_GRENZBAND}
        assert isinstance(s["verdict"]["collides"], bool)


def test_policy_filter_verweigert_urteilslose_zeilen():
    """Zeilen ohne entscheidendes Urteil (collides=None, z. B. error/ungeprueft) fallen heraus."""
    ds = _dataset()
    ds["samples"][0]["verdict"] = {"label": "error", "collides": None}
    erg = policy_filter(ds["samples"])
    assert erg.n_bad_verdict == 1


def test_grenzband_ist_trainingstauglich():
    """``gpu+cpu-grenzband`` (mit bestandenem #205-G1-Gate) wird mittrainiert (Policy v1)."""
    ds = _dataset(label_source=LABEL_GPU_CPU_GRENZBAND)
    model = train_surrogat(ds, source="s", provenance=FIXED_PROV)
    assert model.training["label_source_distribution_used"].get(LABEL_GPU_CPU_GRENZBAND, 0) > 0


def test_training_verweigert_wenn_nur_nicht_trainingstauglich():
    """Nur ``gpu+stichproben-audit`` ⇒ Training verweigert (kein stiller Fehlkomparator)."""
    ds = _dataset(label_source=LABEL_GPU_STICHPROBEN_AUDIT)
    with pytest.raises(ValueError, match="policy-konforme"):
        train_surrogat(ds, source="s", provenance=FIXED_PROV)


def test_training_verweigert_fremde_merkmalsversion():
    """Datensatz mit fremder Merkmals-Version ⇒ Training schlaegt fehl (#211)."""
    ds = _dataset()
    ds["feature_version"] = "999"
    with pytest.raises(ValueError, match="Merkmals-Version"):
        train_surrogat(ds, source="s", provenance=FIXED_PROV)


def test_training_ausweis_zaehlt_verworfene():
    """Der Trainings-Ausweis nennt Gesamt/benutzt/verworfen transparent."""
    ds = _dataset(mix_audit=1)
    model = train_surrogat(ds, source="s", provenance=FIXED_PROV)
    t = model.training
    assert t["n_used"] + t["n_rejected_non_training"] + t["n_rejected_bad_verdict"] == t["n_total"]
    assert t["n_rejected_non_training"] > 0


# --------------------------------------------------------------------------- #
# Provenienz-Validierung (US 26) + Altlauf-Fail-soft (US 12)
# --------------------------------------------------------------------------- #


def test_from_artifact_roundtrip():
    model = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV, seed=3)
    wieder = SurrogatModell.from_artifact(model.to_artifact())
    assert wieder.gb.to_dict() == model.gb.to_dict()
    assert wieder.seed == 3
    assert wieder.features == SURROGATE_FEATURES


def test_laden_mit_falscher_provenienz_schlaegt_fehl():
    """Falsche Merkmals-Version/-Liste/Kennung ⇒ ValueError (US 26)."""
    art = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV).to_artifact()
    with pytest.raises(ValueError, match="Merkmals-Version"):
        SurrogatModell.from_artifact({**art, "feature_version": "999"})
    with pytest.raises(ValueError, match="Merkmalsliste"):
        SurrogatModell.from_artifact({**art, "features": list(art["features"])[:-1]})
    with pytest.raises(ValueError, match="Kein Surrogat-Modell"):
        SurrogatModell.from_artifact({**art, "kind": "etwas-anderes"})
    with pytest.raises(ValueError, match="Schema"):
        SurrogatModell.from_artifact({**art, "schema_version": "999"})


def test_load_surrogat_fail_soft_und_streng(tmp_path):
    """Abwesend ⇒ None (US 12, byte-gleich); vorhanden+falsch ⇒ ValueError (US 26)."""
    model = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV)
    good = tmp_path / "model.json"
    save_surrogat(model, good)
    loaded = load_surrogat(good)
    assert isinstance(loaded, SurrogatModell)
    assert loaded.to_artifact()["kind"] == SURROGATE_MODEL_KIND

    # Altlauf ohne Surrogat-Modell: Pfad fehlt ⇒ None (der Beam laeuft byte-gleich weiter).
    assert load_surrogat(tmp_path / "gibtsnicht.json") is None
    assert load_surrogat(None) is None

    # Vorhandenes, aber provenienz-falsches Artefakt schlaegt fehl (nie stiller Fehlkomparator).
    bad = tmp_path / "bad.json"
    art = model.to_artifact()
    art["feature_version"] = "999"
    bad.write_text(json.dumps(art), encoding="utf-8")
    with pytest.raises(ValueError):
        load_surrogat(bad)


# --------------------------------------------------------------------------- #
# Invarianz-Orakel (US 25) — Vorsortierer aendert nur Reihenfolge, nie Ergebnis
# --------------------------------------------------------------------------- #


class _ReverseVorsortierer:
    """Adversarischer Vorsortierer: kehrt die Pruef-Reihenfolge maximal um (duck-typed)."""

    def vorsortiere(self, bewertungen):
        return list(reversed(list(bewertungen)))

    def stamp(self):
        return {"schema_version": "1", "note": "reverse-adversarial-test"}


def _run(surrogat, free_if):
    tuer = FakePruefTuer(free_if=free_if)
    strat = BeamSuche(surrogat=surrogat) if surrogat is not None else BeamSuche()
    wahl = strat.waehle_raster(_aufgabe(WALL, bewerte=_bewerte(), pruef_tuer=tuer, cap=2))
    return wahl, tuer


def test_invarianz_orakel_adversarischer_vorsortierer():
    """Mit/ohne (adversarischem) Vorsortierer: identischer Sieger + Urteil, nur Reihenfolge/Zeit."""
    free_if = lambda nl, nh, opt: nh >= 2  # noqa: E731 — nur geteilte Hoehe ist frei

    wahl_ohne, tuer_ohne = _run(None, free_if)
    wahl_mit, tuer_mit = _run(_ReverseVorsortierer(), free_if)

    # Bester Kandidat identisch (Schnitt + je Reihe gewaehlte Option).
    assert (wahl_ohne.n_length, wahl_ohne.n_height) == (wahl_mit.n_length, wahl_mit.n_height)
    assert wahl_ohne.zellen_optionen == wahl_mit.zellen_optionen
    # Urteil identisch (geprueft frei ja/nein, leerer Fall ja/nein).
    assert wahl_ohne.provenienz["geprueft"] == wahl_mit.provenienz["geprueft"] is True
    assert wahl_ohne.provenienz["leer"] == wahl_mit.provenienz["leer"] is False
    # NUR die Reihenfolge (und Zeit) aendern sich — der Vorsortierer hat wirklich reordnet.
    assert [c[:2] for c in tuer_ohne.calls] != [c[:2] for c in tuer_mit.calls]
    # Einzige Spur: der Modellstand in der Provenienz (ADR-004), sonst None (US 12).
    assert wahl_ohne.provenienz["surrogate_model"] is None
    assert wahl_mit.provenienz["surrogate_model"] is not None


def test_invarianz_orakel_echtes_modell():
    """Mit einem echten trainierten Modell bleibt der Sieger identisch (US 25)."""
    model = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV, seed=1)
    free_if = lambda nl, nh, opt: nh >= 2  # noqa: E731

    wahl_ohne, _ = _run(None, free_if)
    wahl_mit, _ = _run(model, free_if)

    assert (wahl_ohne.n_length, wahl_ohne.n_height) == (wahl_mit.n_length, wahl_mit.n_height)
    assert wahl_ohne.zellen_optionen == wahl_mit.zellen_optionen
    assert wahl_ohne.provenienz["geprueft"] == wahl_mit.provenienz["geprueft"]
    # Der Modellstand nennt Datensatz/Seed/Merkmalsliste (ADR-004, US 26).
    stamp = wahl_mit.provenienz["surrogate_model"]
    assert stamp["seed"] == 1
    assert stamp["feature_version"] == FEATURE_SCHEMA_VERSION
    assert stamp["features"] == list(SURROGATE_FEATURES)
    assert "dataset" in stamp


def test_vorsortiere_verwirft_nie():
    """Der Vorsortierer sortiert nur — die Kandidatenmenge bleibt vollzaehlig (kein Gate)."""
    model = train_surrogat(_dataset(), source="s", provenance=FIXED_PROV)
    plan = SamplingPlan(lengths_mm=(800.0,), heights_mm=(1000.0,), thicknesses_mm=(200.0,), cap=2)
    from fgc.decompose.kandidaten import band_raster_kandidaten
    from fgc.decompose.objective import KriterienWerte
    from fgc.decompose.scorer import KandidatBewertung

    kandidaten = band_raster_kandidaten(WALL, cap=2)
    bewertungen = [
        KandidatBewertung(
            kandidat=k,
            werte=KriterienWerte(True, float(k.n_height), 0.0, 100.0, 0.0),
            reihen_gedeckt=tuple(True for _ in range(k.n_height)),
            standplaetze=(),
            inseln_je_teil=tuple(1 for _ in range(k.n_parts)),
        )
        for k in kandidaten
    ]
    sortiert = model.vorsortiere(bewertungen)
    assert len(sortiert) == len(bewertungen)
    assert {b.kandidat.key for b in sortiert} == {b.kandidat.key for b in bewertungen}
    _ = plan, CampaignCandidate  # (Importe halten die Merkmals-Naht sichtbar)

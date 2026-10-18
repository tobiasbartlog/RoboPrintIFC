"""Benchmark-Harness — Greedy vs. Beam vs. Beam+Surrogat, byte-vergleichbar (Issue #220, PRD #183).

Zwei Ebenen:

- **Reiner Harness** (`fgc.decompose.benchmark`, ohne Geometrie): das **Sollbruch-Gate**
  (mechanisch — kein Modell ⇒ zweiarmig, gruenes Modell ⇒ dreiarmig, ungueltiges/
  invarianz-rotes Modell ⇒ zweiarmig, jeder Entscheid dokumentiert), die **Auswertung
  ausschliesslich aus persistierten Laufartefakten** (kein Nachrechnen) und die
  **byte-gleiche Wiederholung** der Kennzahlen (US 25).
- **Produktive Verdrahtung** (`fgc.pipeline.benchmark`): die Arme laufen durch
  `propose_decomposition` auf **demselben eingefrorenen Stand** (Muster/Fakes wie
  `test_beam_actions`), das Protokoll traegt Gate + Provenienz je Arm, die Auswertung
  wiederholt sich byte-gleich (CPU-Arme).
"""

from __future__ import annotations

import json

import pytest
from test_beam_actions import _install_fake_pruef_tuer
from test_decompose import _project_with_job
from test_surrogat import FIXED_PROV, _dataset

from fgc.decompose.benchmark import (
    ARM_BEAM,
    ARM_BEAM_SURROGAT,
    ARM_GREEDY,
    BASE_ARMS,
    ArmRun,
    BenchmarkCase,
    benchmark_kennzahlen,
    benchmark_protocol,
    decide_arms,
    evaluate_run,
    mechanical_invariance_check,
    run_arms,
    surrogat_gate,
)
from fgc.decompose.surrogat import train_surrogat

ROBOT = "doosan_m1013"


@pytest.fixture
def stub_walls(install_walls, make_wall):
    return install_walls([make_wall("WALLAAAAAAAAAAAAAAAAAA", height=1000.0, length=1000.0)])


@pytest.fixture(scope="module")
def coarse_map():
    from fgc.kinematics.opw import OpwKinematics
    from fgc.kinematics.reachability import ReachabilityMap

    return ReachabilityMap.build(OpwKinematics.from_robot(ROBOT), cell_mm=150.0, n_alpha=13)


def _model():
    return train_surrogat(_dataset(), source="s", provenance=FIXED_PROV, seed=1)


# --------------------------------------------------------------------------- #
# Sollbruch-Gate (mechanisch, nie stillschweigend)
# --------------------------------------------------------------------------- #


def test_gate_kein_modell_zweiarmig():
    """Ohne Modell laeuft der Benchmark zweiarmig — dokumentiert (kein Warten)."""
    gate = decide_arms(surrogat_gate(None))
    assert gate.arms == BASE_ARMS
    assert gate.arm_label() == "zweiarmig"
    assert gate.surrogat.ok is False
    assert gate.surrogat.reason == "kein-modell"
    # Der vierte Arm ist ebenfalls dokumentiert (nie stillschweigend).
    assert gate.gpu_included is False
    assert gate.to_dict()["gpu_arm"]["reason"]


def test_gate_gruenes_modell_dreiarmig():
    """Ein v1-policy-konformes Modell mit gruenem Invarianz-Orakel ⇒ dritter Arm laeuft."""
    gate = decide_arms(surrogat_gate(_model()))
    assert gate.arms == (ARM_GREEDY, ARM_BEAM, ARM_BEAM_SURROGAT)
    assert gate.arm_label() == "dreiarmig"
    assert gate.surrogat.ok is True
    assert gate.surrogat.reason == "gate-gruen"
    assert all(gate.surrogat.checks.values())
    # Der Modellstand (Datensatz/Seed/Merkmale) liegt fuers Protokoll bei (ADR-004).
    assert gate.surrogat.model_stamp["seed"] == 1


def test_gate_modell_nicht_policy_konform_zweiarmig():
    """Ein Modell mit Audit-Trainingsrest ist nicht v1-policy-konform ⇒ zweiarmig, dokumentiert."""
    model = _model()
    # Trainings-Ausweis mit nicht-trainingstauglicher Quelle manipuliert (Policy-Bruch).
    model.training["label_source_distribution_used"] = {"gpu+stichproben-audit": 5}
    res = surrogat_gate(model)
    assert res.ok is False
    assert res.reason == "modell-ungueltig"
    assert res.checks["v1_policy_konform"] is False
    assert decide_arms(res).arms == BASE_ARMS


def test_gate_invarianz_rot_zweiarmig():
    """Ist das Invarianz-Orakel rot, laeuft der dritte Arm nicht (nie ein Fehlkomparator)."""
    res = surrogat_gate(_model(), invariance_check=lambda _m: False)
    assert res.ok is False
    assert res.reason == "invarianz-orakel-rot"
    assert res.checks["v1_policy_konform"] is True
    assert res.checks["invarianz_orakel_gruen"] is False


def test_mechanical_invariance_check_gruen():
    """Der mechanische Invarianz-Lauf ist fuer ein echtes Modell gruen (US 25)."""
    assert mechanical_invariance_check(_model()) is True

    class _Reverse:
        def vorsortiere(self, bewertungen):
            return list(reversed(list(bewertungen)))

        def stamp(self):
            return {"note": "reverse"}

    # Auch ein adversarischer (umkehrender) Vorsortierer aendert den Sieger NICHT.
    assert mechanical_invariance_check(_Reverse()) is True


# --------------------------------------------------------------------------- #
# Auswertung — ausschliesslich aus persistierten Laufartefakten (US 20/21)
# --------------------------------------------------------------------------- #


def _section(order, standoff, stand_height, reach):
    return {
        "order": order,
        "placement": {"lateral_mm": 0.0, "standoff_mm": standoff, "stand_height_mm": stand_height},
        "status": {"reachable_fraction": reach},
    }


def _beam_doc(*, rechenzeit=0.5, surrogat=None):
    """Ein synthetisches Beam-``decompose.json`` (Metriken-Katalog + Provenienz)."""
    return {
        "grid": {"n_length": 1, "n_height": 2},
        "sections": [
            _section(1, 700.0, 0.0, 1.0),
            _section(2, 700.0, 300.0, 0.8),
        ],
        "refinement": {
            "strategy": "beam-suche", "call_budget": 20, "calls_used": 3,
            "budget_exhausted": False, "surrogate_model": surrogat,
            "verworfen": [{"grund": "reichweite"}, {"grund": "reichweite"}, {"grund": "kollision"}],
            "metriken": {
                "teilanzahl": 2, "volumen_cv": 0.1, "fugenflaeche_mm2": 1000.0,
                "erreichbarer_anteil": 0.9, "geprueft_frei_anteil": 1.0,
                "standplaetze": 2, "rechenzeit_s": rechenzeit,
            },
        },
        "provenance": {"objective": {"mode": "lex"}, "source": "fgc benchmark …",
                       "git_commit": "abc", "created": "2026-07-15T00:00:00+00:00"},
    }


def _greedy_doc():
    """Ein synthetisches Greedy-``decompose.json`` (#165: rows statt Metriken-Katalog)."""
    return {
        "grid": {"n_length": 1, "n_height": 2},
        "sections": [
            _section(1, 700.0, 0.0, 1.0),
            _section(2, 750.0, 0.0, 1.0),
        ],
        "refinement": {
            "strategy": "kollisionsgetriebene-verfeinerung", "call_budget": 20,
            "calls_used": 4, "budget_exhausted": False,
            "rows": [{"h_idx": 0, "collision_free": True}, {"h_idx": 1, "collision_free": False}],
        },
        "provenance": {"objective": {"mode": "lex"}, "source": "fgc benchmark …",
                       "git_commit": "abc", "created": "2026-07-15T00:00:00+00:00"},
    }


def test_evaluate_run_beam_liest_nur_artefakt():
    """Beam-Kennzahlen kommen komplett aus dem Metriken-Katalog + den Sektionen."""
    ev = evaluate_run(_beam_doc())
    k = ev["kennzahlen"]
    assert k["teilanzahl"] == 2
    assert k["volumen_cv"] == 0.1
    assert k["fugenflaeche_mm2"] == 1000.0
    assert k["geprueft_frei_anteil"] == 1.0
    assert k["standplaetze"] == 2
    assert k["erreichbarer_anteil"] == pytest.approx(0.9)  # (1.0 + 0.8) / 2
    # Rechenzeit ist getrennt (diagnostisch) — NICHT in den Kennzahlen.
    assert "rechenzeit_s" not in k
    assert ev["diagnostik"]["rechenzeit_s"] == 0.5
    # Karten-Vorfilter (#214): reichweite-Rejects belegbar (US 10).
    assert ev["verworfen"]["reichweite"] == 2
    # Provenienz je Arm vollstaendig (Strategie/Kontingent/Zielfunktion).
    assert ev["provenance"]["strategy"] == "beam-suche"
    assert ev["provenance"]["call_budget"] == 20
    assert ev["provenance"]["objective"] == {"mode": "lex"}


def test_evaluate_run_greedy_ohne_metriken():
    """Greedy hat keinen Metriken-Katalog: c_v/Fugenflaeche ehrlich None (kein Nachrechnen)."""
    ev = evaluate_run(_greedy_doc())
    k = ev["kennzahlen"]
    assert k["volumen_cv"] is None
    assert k["fugenflaeche_mm2"] is None
    # Geprueft-frei aus den rows (1 von 2 frei); Standplaetze aus den Platzierungen (2 distinct).
    assert k["geprueft_frei_anteil"] == 0.5
    assert k["standplaetze"] == 2
    assert ev["provenance"]["strategy"] == "kollisionsgetriebene-verfeinerung"


def test_benchmark_kennzahlen_wiederholung_byte_gleich():
    """Wiederholung ⇒ byte-gleiche Kennzahlen (CPU-Arme, US 25) — Rechenzeit ignoriert."""
    runs_a = [ArmRun(ARM_BEAM, "c1", _beam_doc(rechenzeit=0.5))]
    runs_b = [ArmRun(ARM_BEAM, "c1", _beam_doc(rechenzeit=9.9))]  # nur die Zeit weicht ab
    a = benchmark_kennzahlen(runs_a)["arme"][ARM_BEAM][0]["kennzahlen"]
    b = benchmark_kennzahlen(runs_b)["arme"][ARM_BEAM][0]["kennzahlen"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_run_arms_faehrt_jeden_arm_je_fall():
    """Der reine Orchestrierer faehrt jeden Arm auf jedem Fall (eingefrorener Stand)."""
    cases = [BenchmarkCase("c1"), BenchmarkCase("c2")]
    seen = []

    def runner(arm, case):
        seen.append((arm, case.case_id))
        return ArmRun(arm, case.case_id, _beam_doc())

    runs = run_arms(cases, (ARM_GREEDY, ARM_BEAM), runner)
    assert len(runs) == 4
    assert seen == [("greedy", "c1"), ("beam", "c1"), ("greedy", "c2"), ("beam", "c2")]


def test_protocol_dokumentiert_gate_und_provenienz():
    """Das Protokoll traegt den Gate-Entscheid (nie stillschweigend) + Provenienz je Arm."""
    gate = decide_arms(surrogat_gate(None))
    cases = [BenchmarkCase("c1", payload={"slug": "x"})]
    runs = [ArmRun(ARM_GREEDY, "c1", _greedy_doc()), ArmRun(ARM_BEAM, "c1", _beam_doc())]
    prot = benchmark_protocol(
        gate, cases, runs, {"source": "s", "git_commit": "a"},
        call_budget=20, robot_name=ROBOT,
    )
    assert prot["kind"] == "benchmark-protocol"
    assert prot["gate"]["arm_label"] == "zweiarmig"
    assert prot["gate"]["surrogat_arm"]["reason"] == "kein-modell"
    assert prot["gate"]["gpu_arm"]["included"] is False
    assert prot["frozen_state"]["call_budget"] == 20
    # Auswertung liegt bei, je Arm die Provenienz.
    assert prot["auswertung"]["arme"][ARM_BEAM][0]["provenance"]["strategy"] == "beam-suche"


# --------------------------------------------------------------------------- #
# Produktive Verdrahtung durch propose_decomposition (Fakes wie test_beam_actions)
# --------------------------------------------------------------------------- #


def _arme_kennzahlen(protocol):
    """Nur die byte-stabilen Kennzahlen je Arm (ohne Rechenzeit/Laufpfade)."""
    return {
        arm: [row["kennzahlen"] for row in rows]
        for arm, rows in protocol["auswertung"]["arme"].items()
    }


def test_run_benchmark_zweiarmig_end_to_end(monkeypatch, coarse_map, tmp_path, stub_walls):
    """Ohne Modell: zweiarmig, Protokoll dokumentiert, Auswertung nur aus Laeufen, byte-gleich."""
    from fgc.pipeline import actions, benchmark

    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    _install_fake_pruef_tuer(monkeypatch, collide_if=lambda nl, nh: nh <= 1)

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    out = tmp_path / "benchmarks" / "protocol.json"
    res = benchmark.run_benchmark(
        slug, "src", out, model_path=None,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    prot = res.protocol
    # Gate: zweiarmig, nie stillschweigend.
    assert prot["gate"]["arm_label"] == "zweiarmig"
    assert prot["gate"]["surrogat_arm"]["reason"] == "kein-modell"
    assert prot["gate"]["gpu_arm"]["reason"]  # dokumentiert
    assert set(prot["auswertung"]["arme"]) == {ARM_GREEDY, ARM_BEAM}
    assert out.exists()

    # Beide Arme haben je einen Lauf mit Strategie-Provenienz (aus dem Artefakt gelesen).
    beam_row = prot["auswertung"]["arme"][ARM_BEAM][0]
    assert beam_row["provenance"]["strategy"] == "beam-suche"
    assert prot["auswertung"]["arme"][ARM_GREEDY][0]["provenance"]["strategy"] == (
        "kollisionsgetriebene-verfeinerung"
    )

    # Auswertung liest NUR persistierte Laufartefakte: erneutes Evaluieren aus dem run_dir
    # liefert dieselben Kennzahlen (kein Nachrechnen).
    beam_dir = next(r.run_dir for r in res.runs if r.arm == ARM_BEAM)
    from pathlib import Path
    doc = json.loads((Path(beam_dir) / "decompose.json").read_text(encoding="utf-8"))
    assert evaluate_run(doc)["kennzahlen"] == beam_row["kennzahlen"]

    # Wiederholung ⇒ byte-gleiche Kennzahlen (CPU-Arme, US 25).
    out2 = tmp_path / "benchmarks" / "protocol2.json"
    res2 = benchmark.run_benchmark(
        slug, "src", out2, model_path=None,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    assert json.dumps(_arme_kennzahlen(res.protocol), sort_keys=True) == json.dumps(
        _arme_kennzahlen(res2.protocol), sort_keys=True
    )


def test_run_benchmark_dreiarmig_surrogat_invariant(monkeypatch, coarse_map, tmp_path, stub_walls):
    """Mit gueltigem Modell: dreiarmig; Beam+Surrogat liefert denselben Sieger wie Beam (US 25)."""
    from fgc.decompose.surrogat import save_surrogat
    from fgc.pipeline import actions, benchmark

    monkeypatch.setattr(actions, "_reach_map_for_robot", lambda *_a, **_k: coarse_map)
    _install_fake_pruef_tuer(monkeypatch, collide_if=lambda nl, nh: nh <= 1)

    model_path = tmp_path / "models" / "surrogate.json"
    save_surrogat(_model(), model_path)

    slug, projects_dir, runs_dir = _project_with_job(tmp_path)
    out = tmp_path / "benchmarks" / "protocol.json"
    res = benchmark.run_benchmark(
        slug, "src", out, model_path=model_path,
        projects_dir=projects_dir, runs_dir=runs_dir,
    )
    prot = res.protocol
    assert prot["gate"]["arm_label"] == "dreiarmig"
    assert prot["gate"]["surrogat_arm"]["ok"] is True
    arme = prot["auswertung"]["arme"]
    assert set(arme) == {ARM_GREEDY, ARM_BEAM, ARM_BEAM_SURROGAT}

    # Invarianz (US 25): Beam und Beam+Surrogat waehlen denselben Schnitt (byte-gleiche
    # deterministische Kennzahlen) — nur der Modellstand in der Provenienz unterscheidet.
    assert arme[ARM_BEAM][0]["kennzahlen"] == arme[ARM_BEAM_SURROGAT][0]["kennzahlen"]
    assert arme[ARM_BEAM][0]["provenance"]["surrogate_model"] is None
    assert arme[ARM_BEAM_SURROGAT][0]["provenance"]["surrogate_model"] is not None

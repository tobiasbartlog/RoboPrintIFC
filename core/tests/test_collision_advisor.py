"""Kollisions-Advisor: gerankte Optionsliste per Neu-Simulation (Issue #130, ADR-024).

Deckt die Akzeptanzkriterien des reinen Advisors ab (``fgc.collision.advisor``) —
schnell, mit einem *synthetischen* ``simulate``-Callable, das jeden Hebel
deterministisch auf einen Befund abbildet (dieselbe Vertrags-Rolle wie die echte
Slice+Trajektorien+Befund-Kette, nur ohne Geo-Kosten):

- **Vorher/Nachher-Nachweis je Hebel**: eine angebotene Option belegt über die
  Neu-Simulation Verbesserung (min. Abstand bzw. kollisionsfrei); nicht
  verbessernde Kandidaten erscheinen nicht.
- **Deterministisches Ranking**: gleiche Eingaben ⇒ gleiche Reihenfolge; jede Option
  trägt die anwendbare Schreibstellen-Nutzlast.

Der reale End-to-End-Durchstich (echte Simulation über die Aktion + Route) liegt in
``test_collision_advisor_action.py`` als ``slow`` markiert (teuer).
"""

from __future__ import annotations

from fgc.collision import advisor as adv


def _finding(min_distance_mm, *, n_red=0, safety=100.0):
    """Ein minimaler ``meta.collision``-artiger Befund (nur die vom Advisor gelesenen Felder)."""
    return {
        "config": {"safety_distance_mm": safety},
        "min_distance_mm": min_distance_mm,
        "n_red": n_red,
    }


# --- Metrik-Kern -------------------------------------------------------------


def test_metric_reads_finding_and_derives_margin_and_collision_free():
    m = adv.CollisionMetric.from_finding(_finding(150.0, n_red=0, safety=100.0))
    assert m is not None
    assert m.min_distance_mm == 150.0
    assert m.margin_mm == 50.0  # 150 − 100
    assert m.collision_free is True

    red = adv.CollisionMetric.from_finding(_finding(-5.0, n_red=3))
    assert red.collision_free is False
    assert adv.CollisionMetric.from_finding(None) is None


def test_improves_rules():
    base = adv.CollisionMetric.from_finding(_finding(10.0, n_red=2))
    # weniger Kollisionen ⇒ Verbesserung
    assert adv.improves(base, adv.CollisionMetric.from_finding(_finding(10.0, n_red=0)))
    # mehr Kollisionen ⇒ nie
    assert not adv.improves(base, adv.CollisionMetric.from_finding(_finding(50.0, n_red=5)))
    # gleiche Kollisionszahl, größerer Abstand ⇒ Verbesserung (über der Schwelle)
    same = adv.CollisionMetric.from_finding(_finding(10.0, n_red=0))
    assert adv.improves(same, adv.CollisionMetric.from_finding(_finding(30.0, n_red=0)))
    # gleiche Kollisionszahl, nur Rundungsrauschen ⇒ keine Verbesserung
    assert not adv.improves(same, adv.CollisionMetric.from_finding(_finding(10.0005, n_red=0)))


# --- Vorher/Nachher-Nachweis je Hebel + „nur Verbesserer erscheinen" ----------


def test_only_improving_options_appear_with_before_after_proof():
    """Basis kollidiert (n_red=4, min −10). Wir mappen genau EINEN Kandidaten je Hebel
    auf einen besseren Befund, alle anderen auf einen gleich-schlechten/schlechteren.
    Erwartung: genau drei Optionen (einer je Hebel), jede mit Vorher<Nachher-Nachweis.
    """
    baseline = _finding(-10.0, n_red=4)

    candidates = adv.build_candidates(
        section_id="abschnitt-1",
        kipp_deg=0.0,
        lead_deg=0.0,
        ik_config={},
        standoff_mm=500.0,
        stand_height_mm=300.0,
    )

    # Je Hebel den ersten Kandidaten als „Gewinner" bestimmen.
    winners = {}
    for c in candidates:
        winners.setdefault(c.kind, c)

    def simulate(override: adv.Override) -> dict:
        for kind, c in winners.items():
            if c.override == override:
                if kind == "ik_config":
                    return _finding(5.0, n_red=0)   # beseitigt Kollision
                if kind == "kipp_lead":
                    return _finding(-2.0, n_red=1)  # weniger Kollisions-Samples
                return _finding(-8.0, n_red=2)      # placement: noch weniger
        return _finding(-10.0, n_red=4)  # unverändert ⇒ keine Verbesserung ⇒ raus

    result = adv.advise(baseline, candidates, simulate)
    kinds = [o.kind for o in result.options]
    assert sorted(kinds) == ["ik_config", "kipp_lead", "placement"]

    for o in result.options:
        # Vorher/Nachher-Nachweis: Kollisionszahl sinkt (oder Abstand wächst).
        assert o.before.n_red == 4
        assert o.after.n_red < o.before.n_red or (
            o.after.min_distance_mm is not None
            and o.after.min_distance_mm > o.before.min_distance_mm
        )
        # Jede Option trägt eine anwendbare Schreibstellen-Nutzlast.
        assert o.write["setter"] in ("process-params", "placement-override")

    # Der kollisionsfreie IK-Kandidat steht vorn (Ranking: kollisionsfrei zuerst).
    assert result.options[0].kind == "ik_config"
    assert result.options[0].after.collision_free is True


def test_no_options_when_nothing_improves():
    baseline = _finding(-10.0, n_red=4)
    candidates = adv.build_candidates(section_id="a")
    # Alles bleibt gleich schlecht ⇒ leere Liste (der Advisor beschönigt nicht).
    result = adv.advise(baseline, candidates, lambda _o: _finding(-10.0, n_red=4))
    assert result.options == []
    # Basis-Metrik wird dennoch berichtet.
    assert result.baseline is not None and result.baseline.n_red == 4


def test_no_baseline_finding_yields_no_options():
    result = adv.advise(None, adv.build_candidates(section_id="a"), lambda _o: _finding(100.0))
    assert result.baseline is None
    assert result.options == []


# --- Deterministisches Ranking -----------------------------------------------


def test_ranking_is_deterministic_and_orders_by_collision_free_then_margin():
    baseline = _finding(-10.0, n_red=2)
    candidates = adv.build_candidates(section_id="a", standoff_mm=500.0, stand_height_mm=300.0)

    # Zwei kollisionsfreie (unterschiedliche Marge) + einer, der nur den Abstand hebt.
    # (Override trägt dict-Felder ⇒ nicht hashbar: per Gleichheit im Listen-Scan matchen.)
    marks = [
        (candidates[0].override, _finding(120.0, n_red=0)),  # Marge 20
        (candidates[1].override, _finding(180.0, n_red=0)),  # Marge 80 (beste)
        (candidates[2].override, _finding(-3.0, n_red=1)),   # weniger Kollisionen
    ]

    def simulate(override):
        for ov, finding in marks:
            if ov == override:
                return finding
        return _finding(-10.0, n_red=2)

    r1 = adv.advise(baseline, candidates, simulate)
    r2 = adv.advise(baseline, candidates, simulate)
    assert [o.to_dict() for o in r1.options] == [o.to_dict() for o in r2.options]

    # Kollisionsfrei zuerst, darunter größte Marge oben.
    assert r1.options[0].after.min_distance_mm == 180.0
    assert r1.options[1].after.min_distance_mm == 120.0
    assert r1.options[2].after.collision_free is False  # der Rest-Verbesserer hinten


def test_candidates_cover_all_three_levers_with_write_payloads():
    cands = adv.build_candidates(
        section_id="abschnitt-2", kipp_deg=5.0, standoff_mm=700.0, stand_height_mm=200.0
    )
    kinds = {c.kind for c in cands}
    assert kinds == {"ik_config", "kipp_lead", "placement"}

    # IK: voller Tri-State-Block über process-params.
    ik = next(c for c in cands if c.kind == "ik_config")
    assert ik.write["setter"] == "process-params" and "ik_config" in ik.write
    # Kipp/Lead: orientation über process-params, absolut (aktueller Kipp + Delta).
    kipp = next(c for c in cands if c.kind == "kipp_lead" and "Kipp" in c.label)
    assert kipp.write["setter"] == "process-params"
    assert kipp.write["orientation"]["kipp_deg"] in {5.0 + d for d in adv.KIPP_DELTAS_DEG}
    # Platzierung: placement-override mit section_id + absolutem freien Wert.
    plc = next(c for c in cands if c.kind == "placement")
    assert plc.write["setter"] == "placement-override"
    assert plc.write["section_id"] == "abschnitt-2"
    # Issue #173: Einzelfeld-Optionen mergen beim Anwenden (bewahren bestehende
    # freie Felder) — jede Platzierungs-Option traegt das merge-Flag.
    assert all(
        c.write.get("merge") is True for c in cands if c.kind == "placement"
    )

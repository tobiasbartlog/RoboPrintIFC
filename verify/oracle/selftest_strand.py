"""Selbsttests der Strang-Regeln (strand_rules, fake_drcf.pump) auf synthetischen Daten.

Ohne Roboter- und Kollisionsmodell (kein Pinocchio, kein Coal), ohne roboprint. Grundlage:
spec/ARTEFAKTE.md (Strang, link, Pumpe) und SPEC §5.3/§5.6/§11 (G3, G5).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from shapely.geometry import Point
from shapely.geometry import box as sbox

from verify.fake_drcf.pump import pump_errors, waypoint_errors
from verify.oracle.strand_rules import (
    branch_changes,
    expected_layers,
    link_errors,
    sequence_errors,
    strand_runs,
)

# --------------------------------------------------------------------------- Ablauf und Schichtregel

# Strang aus Ring 0 -> 1 (gleiche Schicht) -> 2 (Schichtwechsel), Travel, Strang aus Ring 3
SEQ = [("transfer", 0), ("lower", 0), ("approach", 0), ("print", 0), ("print", 0), ("link", 1), ("print", 1),
       ("print", 1), ("link", 2), ("link", 2), ("print", 2), ("retract", 2), ("lift", 2), ("transfer", 3),
       ("lower", 3), ("approach", 3), ("print", 3), ("retract", 3), ("lift", 3)]
RING_LAYER = np.array([0, 0, 1, 1])
LINK_NEXT = [True, True, True, False]


def _seq(seq=SEQ):
    return [k for k, _ in seq], [r for _, r in seq]


def test_expected_layers_strand():
    kind, ring = _seq()
    exp = expected_layers(kind, ring, RING_LAYER)
    #          tr lo ap p  p  l  p  p  l  l  p  re li tr lo ap p  re li
    assert exp.tolist() == [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 1, 1, 1, 2]


def test_sequence_valid_strand():
    kind, ring = _seq()
    assert sequence_errors(kind, ring, LINK_NEXT, 4) == []


def test_link_without_link_next():
    kind, ring = _seq()
    errs = sequence_errors(kind, ring, [False, True, True, False], 4)
    assert len(errs) == 1 and "link_next" in errs[0] and "Ring 0 nach Ring 1" in errs[0], errs


def test_link_not_between_prints():
    seq = [("transfer", 0), ("lower", 0), ("approach", 0), ("print", 0), ("link", 1), ("approach", 1),
           ("print", 1), ("retract", 1)]
    kind, ring = _seq(seq)
    errs = sequence_errors(kind, ring, [True, False], 2)
    assert any("nicht direkt zwischen print 0 und print 1" in e for e in errs), errs


def test_link_skipping_a_ring():
    seq = [("approach", 0), ("print", 0), ("link", 2), ("print", 2), ("retract", 2), ("lift", 2),
           ("transfer", 1), ("lower", 1), ("approach", 1), ("print", 1), ("retract", 1)]
    kind, ring = _seq(seq)
    errs = sequence_errors(kind, ring, [True, True, False], 3)
    assert any("link Ring 2 steht nicht direkt zwischen print 1 und print 2" in e for e in errs), errs
    assert any("Ring 0: nach dem Druck" in e for e in errs), errs


def test_print_without_approach_or_link():
    seq = [("transfer", 0), ("lower", 0), ("print", 0), ("retract", 0)]
    kind, ring = _seq(seq)
    errs = sequence_errors(kind, ring, [False], 1)
    assert any("vor dem Druck" in e for e in errs), errs


def test_missing_ring_and_double_print():
    seq = [("approach", 0), ("print", 0), ("retract", 0), ("lift", 0), ("transfer", 0), ("lower", 0),
           ("approach", 0), ("print", 0), ("retract", 0)]
    kind, ring = _seq(seq)
    errs = sequence_errors(kind, ring, [False, False], 2)
    assert any("mehrere Druckabschnitte" in e for e in errs) and any("ohne Druckabschnitt" in e for e in errs)


def test_strand_runs_and_branch_changes():
    kind, _ = _seq()
    runs = strand_runs(kind)
    assert [r.tolist() for r in runs] == [list(range(2, 12)), [15, 16, 17]]
    branch = np.zeros(len(kind), dtype=int)
    reach = np.ones(len(kind), dtype=bool)
    assert branch_changes(kind, branch, reach) == 0
    branch[13] = 3  # Wechsel im Travel zaehlt nicht
    assert branch_changes(kind, branch, reach) == 0
    branch[8] = 2  # Wechsel im Verbinder: hin und zurueck
    assert branch_changes(kind, branch, reach) == 2
    reach[8] = False  # unerreichbare Samples werden uebersprungen
    assert branch_changes(kind, branch, reach) == 0


# --------------------------------------------------------------------------- Verbinder-Geometrie

QUAT = [0.0, 1.0, 0.0, 0.0]
A = np.array([-85.0, -35.0, 10.0])  # letzter Wegpunkt von Ring 0
B = np.array([-55.0, -5.0, 10.0])  # erster Wegpunkt von Ring 1
LKIND = ["approach", "print", "print", "link", "link", "link", "print", "print", "retract"]
LRING = [0, 0, 0, 1, 1, 1, 1, 1, 1]
SECTION = sbox(-100, -50, 100, 50)


def _wp(*pts):
    return np.array([[*p, *QUAT] for p in pts], dtype=float)


def _link_case(dz: float = 0.0):
    b = B + [0.0, 0.0, dz]
    pos = np.array([[0, -35, 30], [-40, -35, 10], A, A + (b - A) / 3, A + 2 * (b - A) / 3, b,
                    b + [30, 0, 0], b + [55, 0, 0], b + [55, 0, 20]], dtype=float)
    wps = [_wp([0, -35, 10], A), _wp(b, b + [55, 0, 0])]
    return pos, wps


def _links(pos, wps, layers=(0, 0), link_max=60.0, section_of=lambda L: SECTION, reach=None):
    reach = np.ones(len(pos), dtype=bool) if reach is None else reach
    return link_errors(LKIND, LRING, pos, reach, wps, np.array(layers), link_max, np.eye(4), section_of)


def test_link_valid():
    pos, wps = _link_case()
    errs, m = _links(pos, wps)
    assert errs == [] and m["n_links"] == 1 and abs(m["max_link_len_mm"] - np.hypot(30, 30)) < 1e-9
    pos, wps = _link_case(dz=10.0)  # Schichtwechsel: steigt um h
    errs, _ = _links(pos, wps, layers=(0, 1))
    assert errs == []


def test_link_beside_line():
    pos, wps = _link_case()
    n = np.array([1.0, -1.0, 0.0]) / np.sqrt(2)
    pos[4] += 0.6 * n
    errs, m = _links(pos, wps)
    assert any("neben der Geraden" in e for e in errs) and abs(m["max_link_dev_mm"] - 0.6) < 1e-9, errs
    pos[4] -= 0.2 * n  # 0,4 mm: innerhalb der Toleranz
    assert _links(pos, wps)[0] == []


def test_link_endpoints():
    pos, wps = _link_case()
    pos[5] = B + [0.0, 0.0, 0.7]  # endet ueber dem Ringstart
    errs, _ = _links(pos, wps)
    assert any("endet 0.700 mm neben dem ersten Wegpunkt von Ring 1" in e for e in errs), errs
    pos, wps = _link_case()
    pos[2] = A + [0.7, 0.0, 0.0]  # Druck von Ring 0 endet neben dem letzten Wegpunkt
    errs, _ = _links(pos, wps)
    assert any("beginnt 0.700 mm neben dem letzten Wegpunkt von Ring 0" in e for e in errs), errs


def test_link_length_and_switch():
    pos, wps = _link_case()
    errs, _ = _links(pos, wps, link_max=40.0)
    assert any("waagrechte Laenge 42.43 mm > link_max_mm 40" in e for e in errs), errs
    assert _links(pos, wps, link_max=42.43)[0] == []  # Rundung LINK_LEN_TOL
    errs, _ = _links(pos, wps, link_max=0.0)
    assert any("link_max_mm = 0" in e for e in errs), errs


def test_link_layer_jump():
    pos, wps = _link_case(dz=20.0)
    errs, _ = _links(pos, wps, layers=(0, 2))
    assert any("Schichtsprung 2" in e for e in errs), errs


def test_link_outside_section():
    hole = SECTION.difference(Point(-70, -20).buffer(4.0))  # Oeffnung zwischen den Ringen
    pos, wps = _link_case()
    errs, _ = _links(pos, wps, section_of=lambda L: hole)
    assert any("verlaesst den Querschnitt der Schicht 0" in e for e in errs), errs
    small = SECTION.difference(Point(-70, -20).buffer(0.8))  # kleiner als die Toleranz 1 mm
    assert _links(pos, wps, section_of=lambda L: small)[0] == []
    # Schichtwechsel: beide Schichten zaehlen, gleiche Schicht nur die des folgenden Rings
    pos, wps = _link_case(dz=10.0)
    errs, _ = _links(pos, wps, layers=(0, 1), section_of=lambda L: hole if L == 0 else SECTION)
    assert any("Querschnitt der Schicht 0" in e for e in errs), errs
    pos, wps = _link_case()
    assert _links(pos, wps, layers=(1, 1), section_of=lambda L: hole if L == 0 else SECTION)[0] == []


def test_link_unreachable_sample_skipped():
    pos, wps = _link_case()
    pos[4] = np.nan
    reach = np.ones(len(pos), dtype=bool)
    reach[4] = False
    assert _links(pos, wps, reach=reach)[0] == []


# --------------------------------------------------------------------------- Pumpe (G5)

PKIND = ["transfer", "transfer", "lower", "approach", "print", "print", "link", "print", "print", "retract",
         "lift"]
PRING = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
PPOS = np.array([[10.0 * i, 0.0, 0.0] for i in range(len(PKIND))])
IDX = [0, 1, 2, 3, 5, 6, 8, 9, 10]  # angefahrene Samples je Bewegung
CMD = ["movej", "movej", "movel", "movel", "movel", "movel", "movel", "movel", "movel"]


def _program(radius=None, pump=None, events=None, cmd=None):
    """Gueltiger Strang: Pumpe an nach Bewegung 3 (approach), aus nach Bewegung 6 (letztes print)."""
    radius = radius or [0, 0, 0, 0, 2, 2, 0, 0, 0]
    pump = pump or [False, False, False, False, True, True, True, False, False]
    events = events if events is not None else [("ao", 1, 5.0, 4), ("wait", 3.0, 4), ("ao", 1, 0.0, 7),
                                                ("ao", 1, 0.0, 9)]
    M = [SimpleNamespace(cmd=c, radius=float(r), sync=True, line=10 + k, pump_on=p)
         for k, (c, r, p) in enumerate(zip(cmd or CMD, radius, pump, strict=True))]
    return M, events


def _pump(M, events, idx=IDX, pos=PPOS):
    return pump_errors("t", M, events, idx, PKIND, pos)


def test_pump_valid_strand():
    M, ev = _program()
    assert _pump(M, ev) == []
    ev_mwait = [*ev[:2], ("mwait", 0.0, 7), *ev[2:]]  # mwait am Strangende vor Pumpe aus ist kein Halt
    assert _pump(M, ev_mwait) == []


def test_pump_off_between_print_and_link():
    M, _ = _program(pump=[False, False, False, False, True, False, False, False, False])
    ev = [("ao", 1, 5.0, 4), ("wait", 3.0, 4), ("ao", 1, 0.0, 5), ("ao", 1, 0.0, 9)]
    errs = _pump(M, ev)
    assert any("Pumpe aus bei Sample #5 (print -> link), nicht am Strangende" in e for e in errs), errs
    assert any("Druck- oder Verbinderbewegung ohne Pumpe (['link']" in e for e in errs), errs


def test_pump_on_during_retract():
    M, _ = _program(pump=[False, False, False, False, True, True, True, True, False])
    ev = [("ao", 1, 5.0, 4), ("wait", 3.0, 4), ("ao", 1, 0.0, 8), ("ao", 1, 0.0, 9)]
    errs = _pump(M, ev)
    assert any("Pumpe an waehrend ['retract']" in e for e in errs), errs
    assert any("Pumpe aus bei Sample #9 (retract -> lift)" in e for e in errs), errs


def test_pump_on_not_at_strand_start_or_moving():
    M, _ = _program(pump=[False, False, False, True, True, True, True, False, False])
    ev = [("ao", 1, 5.0, 3), ("ao", 1, 0.0, 7), ("ao", 1, 0.0, 9)]
    errs = _pump(M, ev)
    assert any("nicht am Strangbeginn" in e for e in errs) and any("['approach']" in e for e in errs), errs
    M, ev = _program(radius=[0, 0, 0, 2, 2, 2, 0, 0, 0])
    assert any("vor 'Pumpe an' steht der Roboter nicht" in e for e in _pump(M, ev))
    M, ev = _program(radius=[0, 0, 0, 0, 2, 2, 1, 0, 0])
    assert any("vor 'Pumpe aus' steht der Roboter nicht" in e for e in _pump(M, ev))


def test_halt_in_strand():
    M, ev = _program(radius=[0, 0, 0, 0, 2, 0, 0, 0, 0])  # Verbinder mit radius 0
    errs = _pump(M, ev)
    assert any("Halt im Strang: movel mit radius 0" in e for e in errs), errs
    pos = PPOS.copy()
    pos[6] = pos[5]  # entartetes Segment: radius 0 ist dort min(r_blend, 1/2 Segment)
    assert _pump(M, ev, pos=pos) == []
    M, ev = _program()
    errs = _pump(M, [*ev[:2], ("wait", 1.0, 5), *ev[2:]])
    assert any("Halt im Strang: wait(1)" in e for e in errs), errs
    assert _pump(M, [*ev[:2], ("wait", 0.0, 5), *ev[2:]]) == []


def test_waypoints_with_pump():
    rings_W = [PPOS[[3, 5]], PPOS[[6, 8]]]  # Ringstart (approach bzw. link) und Ende
    M, _ = _program()
    pump = [m.pump_on for m in M]
    assert waypoint_errors("t", rings_W, PPOS, PKIND, PRING, IDX, pump) == []
    pump_off = pump.copy()
    pump_off[4] = False
    errs = waypoint_errors("t", rings_W, PPOS, PKIND, PRING, IDX, pump_off)
    assert any("Ring 0: 2 Wegpunkte ohne laufende Pumpe" in e for e in errs), errs
    far = [PPOS[[3, 5]], np.vstack([PPOS[[6, 8]], [[200.0, 50.0, 0.0]]])]
    errs = waypoint_errors("t", far, PPOS, PKIND, PRING, IDX, pump)
    assert any("Ring 1: 1 Wegpunkte nicht abgefahren" in e for e in errs), errs

"""Zwei Orakel der **gefaehrlichen Richtung** von Pruef-Tuer und Freigang (Issue #176, V9).

Die bestehenden Orakel (16/16-Denkmal :mod:`test_prueftuer_denkmal`, Freigang-
Formeltests :mod:`test_freigang`) exerzieren die kritische Fehlerrichtung nie —
Befunde **B3, B6, B8** der Zwischenkritik 2026-07-10: ein Orakel, das nur den
harmlosen Ast prueft, erzeugt falsches Vertrauen. Diese beiden **slow**-Tests
schliessen die Luecke mit **konstruierten** Faellen ueber echte Roboter-Geometrie
(derselbe ``find_collisions`` wie im Produktivpfad), nicht mit gemockten Zahlen:

1. **Travel-Kipp (B3/B6).** Ein Hindernis an einem **ausgeduennten** Travel-Sample:
   der volle Befund (jedes Sample) urteilt **rot**, die Pruef-Tuer mit
   Travel-Ausduennung (``stride=5``) ueberspringt es und weicht auf **frei** ab.
   Die Abweichung wird **sichtbar gemacht und dokumentiert** (nicht wegdefiniert) —
   sie ist die eine Konstellation, in der die Ausduennung das Urteil kippen kann
   (die Ausduennung entfernt rote Samples, fuegt nie welche hinzu; jede Abweichung
   ist zwingend „voll rot / Tuer frei"). Mit ``stride=1`` deckt die Tuer den Fall
   wieder auf — das isoliert die Ausduennung als alleinige Ursache.

2. **Freigang-Orakel (B8).** Der Kern-Vertrag des Freigang-Kriteriums ist „``D``
   ueberschaetzt die real druckbare Tiefe" — bislang nur **tautologisch** geprueft
   (die druckbaren Dicken der Formeltests werden aus ``L``/``R`` selbst konstruiert).
   Hier bestaetigt ein **unabhaengiges** Orakel (der volle Kollisionsbefund) die
   Richtung „voller Befund kollidiert bei Dicke ≤ ``D`` ⇒ Freigang schwieg zu Recht":
   eine Wand **duenner** als ``D`` (Freigang stumm, kein „zu dick") ist dennoch
   nicht einseitig druckbar (der uebergreifende Arm taucht ins eigene Material) —
   ``D`` ist also eine grosszuegige Obergrenze, kein zu knapper Wert (sichere
   Fehlerrichtung, S6).

Beide Faelle laufen ueber echte VHACD-Distanzen (python-fcl) ⇒ ``slow``: nur mit
``-m slow``. Uebersprungen, wenn die Kollisions-Geometrie fehlt (kein ``[geo]``-Extra
bzw. kein ``robot_geometry``-Artefakt) — dann ist das Orakel nicht anwendbar.
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from fgc.collision import finding as fd
from fgc.decompose.freigang import check_freigang, printable_depth_mm
from fgc.kinematics.opw import OpwKinematics
from fgc.simulation import transform

pytestmark = pytest.mark.slow

ROBOT = "doosan_m1013"
IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


def _flange_world_pos(kin: OpwKinematics, joints_rad: list[float]) -> np.ndarray:
    """Welt-Position des Flanschs (Glied 6) bei Basis = Identitaet (Obstacle-Anker)."""
    lf = kin.link_frames(joints_rad)
    return np.asarray(transform.compose(transform.frame_from_dict(IDENTITY), lf[6]).pos_mm)


def _box(extents: list[float], center: np.ndarray | list[float]):
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(list(center))
    return np.asarray(box.vertices), np.asarray(box.faces)


# ---------------------------------------------------------------------------
# 1) Travel-Kipp: rot nur in der Travel-Mitte (B3/B6)
# ---------------------------------------------------------------------------


def test_travel_thinning_deviates_full_red_door_free(capsys):
    """Konstruiertes Hindernis an einem **ausgeduennten** Travel-Sample.

    Voller Befund rot (prueft jedes Sample), Pruef-Tuer ``stride=5`` weicht auf frei
    ab (ueberspringt genau dieses Sample). Die Abweichung wird dokumentiert; ``stride=1``
    deckt sie wieder auf (Ausduennung ist die alleinige Ursache — Befund B3/B6).
    """
    kin = OpwKinematics.from_robot(ROBOT)

    # 14 Samples: 0..1 Druck, 2..11 ein Travel-Lauf, 12..13 Druck. Bei stride=5 behaelt
    # die Ausduennung im Lauf nur die Indizes 2, 7, 11 — 3..6, 8..10 fallen weg.
    n = 14
    kinds = ["print"] * n
    for i in range(2, 12):
        kinds[i] = "travel"
    times = [float(i) for i in range(n)]
    targets = [{"layer": 0, "kind": kinds[i]} for i in range(n)]

    kept = fd.thin_travel_indices(fd.travel_flags(times, times, kinds), 5)
    target_sample = 4
    assert target_sample not in kept, "Testaufbau: Ziel-Sample muss ausgeduennt sein"

    # Alle Samples in einer kollisionsfreien Ruhepose (Arm hoch/hinten); nur das
    # ausgeduennte Ziel-Sample taucht als Spitze nach vorn-unten in ein dort platziertes
    # Hindernis. So kollidiert ausschliesslich dieses eine (Travel-)Sample.
    q_safe = [0.0, -1.3, 0.3, 0.0, 0.8, 0.0]
    q_spike = [0.2, -0.2, 0.55, 0.0, 1.1, 0.0]
    joints = [list(q_safe) for _ in range(n)]
    joints[target_sample] = list(q_spike)
    samples = [{"joints_rad": joints[i], "t_s": times[i]} for i in range(n)]

    part_v, part_f = _box([600.0, 200.0, 1000.0], [0.0, 0.0, 500.0])  # Druckstand, ueber dem Arm
    obstacle = _box([120.0, 120.0, 120.0], _flange_world_pos(kin, q_spike))

    req = fd.FindingRequest(
        trajectory=fd.TrajectoryExcerpt(
            base_frame=IDENTITY, samples=samples, target_times_s=times
        ),
        toolpath=fd.ToolpathExcerpt(targets=targets, layer_height_mm=10.0, n_layers=100),
        part=fd.PartMesh(vertices_mm=part_v, faces=part_f),
        scene=fd.SceneInputs(mode="abschnitt", earlier_parts=(obstacle,)),
        refs=fd.RobotToolRefs(),
    )

    full = fd.build_section_finding(ROBOT, req)
    if full is None:
        pytest.skip("Kollisions-Geometrie fehlt — Orakel nicht anwendbar")
    door_thinned = fd.check_part_clearance(ROBOT, req, travel_stride=5)
    door_full = fd.check_part_clearance(ROBOT, req, travel_stride=1)
    assert door_thinned is not None and door_full is not None

    red_samples = [i for i, d in enumerate(full["distances_mm"]) if d is not None and d < 0.0]

    with capsys.disabled():
        print("\n=== Travel-Kipp: rot nur an einem ausgeduennten Travel-Sample (B3/B6) ===")
        print(f"kept(stride=5)     = {kept}  (Ziel-Sample {target_sample} faellt weg)")
        print(f"voller Befund      : n_red={full['n_red']}, rote Samples={red_samples}")
        print(f"Pruef-Tuer stride=5: collides={door_thinned.collides} "
              f"(n_checked={door_thinned.n_checked}/{door_thinned.n_samples})  <-- ABWEICHUNG")
        print(f"Pruef-Tuer stride=1: collides={door_full.collides} "
              f"(deckt den Fall wieder auf — Ausduennung ist die Ursache)")

    # Die gefaehrliche Richtung, sichtbar gemacht (nicht wegdefiniert):
    assert full["n_red"] > 0, "voller Befund muss das Travel-Sample rot sehen"
    assert red_samples == [target_sample], "nur das ausgeduennte Travel-Sample kollidiert"
    assert door_thinned.collides is False, "Pruef-Tuer stride=5 ueberspringt es → frei (Abweichung)"
    # stride=1 isoliert die Ausduennung als alleinige Ursache — kein struktureller Blindfleck.
    assert door_full.collides is True, "Pruef-Tuer stride=1 deckt denselben Kollisionsbefund auf"
    # Sicherheit ueber die Konstruktion: die Ausduennung entfernt Samples, fuegt nie welche hinzu.
    assert door_thinned.n_checked < door_thinned.n_samples
    assert door_full.n_checked == door_full.n_samples == n


# ---------------------------------------------------------------------------
# 2) Freigang-Orakel: D ueberschaetzt die real druckbare Tiefe (B8)
# ---------------------------------------------------------------------------


def test_freigang_D_overestimates_real_printable_depth(capsys):
    """Voller Befund kollidiert bei Dicke **≤ D** — Freigang schwieg, ``D`` ist grosszuegig.

    Nicht-tautologisch (Befund B8): das druckbare-Tiefe-Urteil ``D = L + R`` wird gegen
    ein **unabhaengiges** Orakel gestellt (der volle Kollisionsbefund, nicht die Formel).
    Eine Wand **duenner** als ``D`` ist laut Freigang druckbar (stumm, kein „zu dick"),
    kollidiert aber real: der uebergreifende Arm taucht ins eigene, unter dem Druckpunkt
    bereits feste Material — genau die vom Freigang-Modell **ignorierten** Armglieder.
    Damit ist erstmals belegt, dass ``D`` die real druckbare Tiefe **ueberschaetzt**
    (sichere Fehlerrichtung: Freigang unter-erkennt Unmoeglichkeit, nie umgekehrt).
    """
    free_length_mm, wrist_radius_mm = 200.0, 60.0
    depth_D = printable_depth_mm(free_length_mm, wrist_radius_mm)  # 260 mm

    # Wand deutlich DUENNER als D (200 < 260) ⇒ Freigang bleibt stumm.
    thickness_mm = 200.0
    freigang = check_freigang(
        thickness_mm, free_length_mm=free_length_mm, wrist_radius_mm=wrist_radius_mm
    )
    assert freigang.too_thick is False, "Testaufbau: Wand muss fuer Freigang druckbar (stumm) sein"

    # Reale Druckpose: Duese senkrecht nach unten an der FERNEN Wandflaeche, hoch oben —
    # der Arm muss ueber die (bis dahin feste) Nahflaeche greifen. Solutions von der IK,
    # deterministischer erster Zweig; die Wand solid bis zur Druckschicht (Druckstand).
    standoff_mm, print_z_mm, width_mm, height_mm = 400.0, 1500.0, 600.0, 1700.0
    # Aus der IK ermittelte, hier eingefrorene Gelenkloesung (Determinismus, kein IK-Drift):
    joints_rad = [1.628328, 1.183495, 1.570796, 0.0, -2.754291, 1.628328]

    part_v, part_f = _box(
        [width_mm, thickness_mm, height_mm],
        [0.0, standoff_mm + thickness_mm / 2.0, height_mm / 2.0],
    )
    layer = int(print_z_mm / 10.0)
    full = fd.build_section_finding(
        ROBOT,
        fd.FindingRequest(
            trajectory=fd.TrajectoryExcerpt(
                base_frame=IDENTITY,
                samples=[{"joints_rad": joints_rad, "t_s": 0.0}],
                target_times_s=[0.0],
            ),
            toolpath=fd.ToolpathExcerpt(
                targets=[{"layer": layer, "kind": "print"}],
                layer_height_mm=10.0,
                n_layers=int(height_mm / 10.0) + 1,
            ),
            part=fd.PartMesh(vertices_mm=part_v, faces=part_f),
            scene=fd.SceneInputs(mode="abschnitt"),
            refs=fd.RobotToolRefs(),
        ),
    )
    if full is None:
        pytest.skip("Kollisions-Geometrie fehlt — Orakel nicht anwendbar")

    penetration_mm = -(full["min_distance_mm"] or 0.0)

    with capsys.disabled():
        print("\n=== Freigang-Orakel: D ueberschaetzt die real druckbare Tiefe (B8) ===")
        print(f"D = L + R           = {free_length_mm} + {wrist_radius_mm} = {depth_D} mm")
        print(f"Wanddicke           = {thickness_mm} mm  (< D ⇒ Freigang too_thick="
              f"{freigang.too_thick}, stumm)")
        print(f"voller Befund       : n_red={full['n_red']}, "
              f"Eindringtiefe={penetration_mm:.1f} mm, "
              f"Verursacher=Glied {full['causer_link'][0]} gegen {full['causer_against'][0]}")
        print("Folgerung           : Dicke < D, aber real NICHT druckbar ⇒ D ist eine "
              "grosszuegige Obergrenze (sichere Fehlerrichtung).")

    # Der Kern-Vertrag, non-tautologisch belegt:
    assert full["n_red"] > 0, "voller Befund muss die zu-tiefe Reichweite als Kollision sehen"
    assert full["causer_against"][0] == "current_part", "Kollision gegen das eigene feste Material"
    # Freigang schwieg (Dicke ≤ D), das unabhaengige Orakel widerspricht der Druckbarkeit —
    # genau die Richtung, die bislang kein Test exerziert hat.
    assert thickness_mm < depth_D
    assert penetration_mm > 50.0, "kein Grenzfall — klarer, unabhaengiger Kollisionsbefund"

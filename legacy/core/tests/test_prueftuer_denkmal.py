"""Pruef-Tuer der Zerlegung gegen den vollen Befund — Orakel auf den 16 Denkmal-Modulen.

Akzeptanz von Issue #162 (Karte #139, Entscheidung #141, Scheibe 1):

- **Identisches rot/frei-Urteil.** Die verduennte ``find_collisions``-Instanz
  (:func:`fgc.collision.finding.check_part_clearance`, Travel-Ausduennung) liefert
  auf **jedem** der 16 real gespeicherten Denkmal-Module dasselbe kollidiert/frei-
  Urteil wie der volle Befund (:func:`fgc.collision.finding.build_section_finding`) —
  Orakel gegen die S6-Datenbasis (dort sind alle 16 Module tief rot).
- **In wenigen Sekunden je Modul.** Die reine Pruef-Tuer-Zeit (Travel-ausgeduennt,
  ohne Slice/Sim) wird je Modul gemessen und mit dem vollen Befund verglichen —
  die Zahlen wandern ins Design-Log (2026-07-10).

Beide Urteile entstehen aus **derselben** simulierten Abschnitts-Rechnung (``comp``
je Modul, ein Slice/Sim), damit der Vergleich nur die Ausduennung isoliert und die
gemessene Pruef-Tuer-Zeit die reine ``find_collisions``-Zeit ist. Alles ueber den
**Produktivpfad** (dieselben Tueren wie ``simulate_section``), kein Lauf geschrieben.

Langsam (echte VHACD-Distanzen ueber ~19,5 k Samples je Modul) ⇒ ``slow``: laeuft
nur mit ``-m slow``. Wird uebersprungen, wenn das reale Projekt oder die
Kollisions-Geometrie fehlt.
"""

from __future__ import annotations

import time

import pytest

from fgc.paths import PROJECTS_DIR

pytestmark = pytest.mark.slow

DENKMAL = PROJECTS_DIR / "denkmal" / "project.json"
TRAVEL_STRIDE = 5


def _plan_context():
    """Roboter/Tool/Wand + realer 16-Teile-Zerlegungsplan aus dem Produktivpfad."""
    from fgc.pipeline import actions as A
    from fgc.pipeline import sectionsim as S
    from fgc.project import load_project, project_dir_for

    project_dir = project_dir_for("denkmal")
    artifact = load_project(project_dir)
    job = artifact["print_jobs"][0]
    pc = S.placement_context_for_job(job)
    plan = A.plan_for_job(job, pc.wall, pc.robot, pc.tool, strict_overrides=False).plan
    return S, artifact, job, pc.robot_name, plan


def test_prueftuer_matches_full_finding_on_16_denkmal_modules(capsys):
    if not DENKMAL.exists():
        pytest.skip("Reales Projekt 'denkmal' nicht vorhanden")

    from fgc.collision.finding import check_part_clearance

    S, artifact, job, robot_name, plan = _plan_context()
    sids = [sp.section.section_id for sp in plan.sections]
    if not sids:
        pytest.skip("Zerlegungsplan des Denkmal-Jobs ist leer")

    rows: list[dict] = []
    for sid in sids:
        ctx = S.section_sim_context(artifact, job, sid, plan=plan)
        comp = S.slice_and_simulate_section(artifact, job, sid, ctx=ctx)

        t0 = time.perf_counter()
        full = S.section_collision_finding(comp, config=None)
        full_s = time.perf_counter() - t0

        if full is None:
            pytest.skip("Kollisions-Geometrie fehlt (kein voller Befund) — Orakel nicht anwendbar")

        t0 = time.perf_counter()
        # Dieselbe FindingRequest wie der volle Befund (Issue #192), nur Travel-verdünnt.
        verdict = check_part_clearance(
            comp.robot_name, comp.finding_request(config=None), travel_stride=TRAVEL_STRIDE
        )
        door_s = time.perf_counter() - t0

        assert verdict is not None
        full_collides = full["n_red"] > 0
        # Orakel: identisches rot/frei-Urteil wie der volle Befund.
        assert verdict.collides == full_collides, (
            f"Modul {sid}: Pruef-Tuer {verdict.collides} != voll {full_collides} "
            f"(n_red voll={full['n_red']}, Tuer={verdict.n_red})"
        )
        rows.append(
            {
                "sid": sid,
                "collides": verdict.collides,
                "n_red_full": full["n_red"],
                "n_red_door": verdict.n_red,
                "causer": verdict.causer_link,
                "pen_mm": verdict.penetration_mm,
                "n_samples": verdict.n_samples,
                "n_checked": verdict.n_checked,
                "full_s": full_s,
                "door_s": door_s,
            }
        )

    # Messung fuers Protokoll/Design-Log ausgeben (mit -s sichtbar).
    with capsys.disabled():
        print(f"\n=== Pruef-Tuer vs. voll: {len(rows)} Module, stride={TRAVEL_STRIDE} ===")
        for r in rows:
            urteil = "kollid." if r["collides"] else "frei"
            reds = f"{r['n_red_full']}/{r['n_red_door']}"
            samples = f"{r['n_samples']}/{r['n_checked']}"
            print(
                f"{r['sid']:<14}{urteil:<9}n_red(voll/Tür)={reds:<14}"
                f"Verurs.={str(r['causer']):<5}tiefe={r['pen_mm']:>7.1f}mm  "
                f"Samples(g/p)={samples:<14}voll={r['full_s']:>6.2f}s  Tür={r['door_s']:>6.2f}s"
            )
        door_times = sorted(r["door_s"] for r in rows)
        full_times = sorted(r["full_s"] for r in rows)
        print(
            f"Pruef-Tuer: min {door_times[0]:.2f} s / median "
            f"{door_times[len(door_times) // 2]:.2f} s / max {door_times[-1]:.2f} s"
        )
        print(f"Voller Befund: min {full_times[0]:.2f} s / max {full_times[-1]:.2f} s")

    # Alle 16 Module kollidieren real (S6-Datenbasis) — Orakel hat eine rote Zeile.
    assert all(r["collides"] for r in rows)
    # Die Pruef-Tuer prueft nie mehr Samples als die Bahn hat (Travel-ausgeduennt).
    assert all(r["n_checked"] <= r["n_samples"] for r in rows)


def test_sdf_backend_liefert_identische_pruef_tuer_befunde(capsys):
    """Regressionsanker Backend-Flip (Issue #213, US 2 — CPU-Stufe des zweistufigen Ankers).

    Je Denkmal-Modul laeuft die Pruef-Tuer einmal mit der FCL-Referenz und einmal
    mit dem SDF-Backend (:mod:`fgc.collision.backend`, App-Ebenen-Schalter) ueber
    **dieselbe** FindingRequest. Das komplette Urteil (``to_dict``) muss identisch
    sein — Verursacher-Glied, Eindringtiefe, rote Intervalle, geprueft/vermutlich-
    Zaehler. Byte-Identitaet der Eindringtiefen setzt die identische
    set_transform-Historie der fcl-Manager voraus (s. ``check.find_collisions``);
    genau die stellt das SDF-Backend nach.
    """
    if not DENKMAL.exists():
        pytest.skip("Reales Projekt 'denkmal' nicht vorhanden")
    from fgc.collision import backend as be
    from fgc.collision import glied_sdf as gs
    from fgc.collision.finding import check_part_clearance
    from fgc.paths import ROBOTS_DIR

    S, artifact, job, robot_name, plan = _plan_context()
    if not (ROBOTS_DIR / "collision" / robot_name / gs.SDF_DIR_NAME).exists():
        pytest.skip(f"Glied-SDF-Artefakt fuer {robot_name!r} fehlt")
    sids = [sp.section.section_id for sp in plan.sections]
    if not sids:
        pytest.skip("Zerlegungsplan des Denkmal-Jobs ist leer")

    rows: list[dict] = []
    for sid in sids:
        ctx = S.section_sim_context(artifact, job, sid, plan=plan)
        comp = S.slice_and_simulate_section(artifact, job, sid, ctx=ctx)
        req = comp.finding_request(config=None)

        t0 = time.perf_counter()
        v_fcl = check_part_clearance(comp.robot_name, req, travel_stride=TRAVEL_STRIDE)
        fcl_s = time.perf_counter() - t0
        if v_fcl is None:
            pytest.skip("Kollisions-Geometrie fehlt — Anker nicht anwendbar")

        try:
            be.set_collision_backend("sdf")
            t0 = time.perf_counter()
            v_sdf = check_part_clearance(comp.robot_name, req, travel_stride=TRAVEL_STRIDE)
            sdf_s = time.perf_counter() - t0
        finally:
            be.set_collision_backend(None)

        assert v_sdf is not None
        d_fcl, d_sdf = v_fcl.to_dict(), v_sdf.to_dict()
        diff = [k for k in d_fcl if d_fcl[k] != d_sdf[k]]
        assert not diff, f"Modul {sid}: Backend-Flip aendert den Befund in {diff}"
        rows.append({"sid": sid, "pen": v_fcl.penetration_mm, "fcl_s": fcl_s, "sdf_s": sdf_s})

    with capsys.disabled():
        print(f"\n=== Backend-Flip FCL vs. SDF: {len(rows)} Module identisch ===")
        for r in rows:
            print(
                f"{r['sid']:<14}tiefe={r['pen']:>7.1f}mm  "
                f"fcl={r['fcl_s']:>6.2f}s  sdf={r['sdf_s']:>6.2f}s"
            )

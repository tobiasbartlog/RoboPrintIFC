"""Gegenpruefung A2.4: Manipulierte Laufordner gegen check_run (G3) und fake_drcf (G5).

Basis ist der Mini-Lauf aus verify/oracle/minirun.py (2 Schichten, 2 Schalen, Orakel-konsistent).
Jede Manipulation beschreibt einen physikalisch falschen oder unvollstaendigen Lauf; erwartet waere,
dass mindestens ein Pruefer ihn ablehnt. verify/ wird nicht veraendert (nur importiert).

    /opt/fgc-venv/bin/python -m experiments.gegenpruefung.manipulationen [<arbeitsordner>]
"""

from __future__ import annotations

import inspect
import json
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

import numpy as np

from verify.check_run import run as check_run
from verify.fake_drcf.check import check_rundir
from verify.oracle import minirun


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _save(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def _verdict(name: str, run_dir: Path, expect_reject: bool = True) -> dict:
    ok, rep = check_run(run_dir, run_dir / "scenario.json", jobs=1)
    errs_drl, _ = check_rundir(run_dir)
    res = {"manipulation": name, "check_run": "BESTANDEN" if ok else "ABGELEHNT",
           "fake_drcf": "BESTANDEN" if not errs_drl else "ABGELEHNT",
           "check_run_fehler": rep["errors"][:3], "fake_drcf_fehler": errs_drl[:3]}
    gap = ok and not errs_drl and expect_reject
    res["luecke"] = gap
    print(f"[{'LUECKE' if gap else 'ok    '}] {name}: check_run {res['check_run']}, fake_drcf {res['fake_drcf']}")
    for e in (rep["errors"][:2] + errs_drl[:2]):
        print(f"           {e[:160]}")
    return res


def build_reversed_layers(out: Path) -> Path:
    """Wie minirun.build, aber die Ringe der oberen Schicht werden ZUERST gedruckt (Druck in die Luft,
    danach faehrt die Duese durch die schon gedruckte Schicht 1 nach unten)."""
    src = textwrap.dedent(inspect.getsource(minirun.build))
    marker = "    quat = R_to_quat(b.R_WT)\n"
    assert marker in src
    src = src.replace(marker, "    rings = rings[2:] + rings[:2]\n" + marker)
    src = src.replace("def build(", "def build_rev(")
    ns = dict(vars(minirun))
    exec(compile(src, "<build_rev>", "exec"), ns)  # noqa: S102 - Experiment, gepatchte Kopie
    return ns["build_rev"](out)


def build_extra_outer_ring(out: Path) -> Path:
    """Wie minirun.build, aber mit einer dritten Schale 15 mm AUSSERHALB des Teils (Strang neben dem
    Teil in die Luft bzw. auf den Tisch)."""
    src = textwrap.dedent(inspect.getsource(minirun.build))
    marker = "        for s in range(2):\n"
    assert marker in src
    src = src.replace(marker, "        for s in range(-1, 2):\n")
    src = src.replace('"shell": s,', '"shell": s + 1,')
    src = src.replace("def build(", "def build_extra(")
    ns = dict(vars(minirun))
    exec(compile(src, "<build_extra>", "exec"), ns)  # noqa: S102 - Experiment, gepatchte Kopie
    return ns["build_extra"](out)


def build_travel_through_print(out: Path) -> Path:
    """Wie minirun.build, aber der Travel zum letzten Ring (Schicht 1, innen) laeuft 5 mm UNTER der
    Oberkante des Druckstands k = 2 durch das gedruckte Material (Duesenspitze schleift durch die Wand)."""
    src = textwrap.dedent(inspect.getsource(minirun.build))
    marker = "        travel = start + up * (max(z_top + 30.0, start[2] + 20.0) - start[2] + 20.0)\n"
    assert marker in src
    src = src.replace(marker, marker + "        if r == 3:\n"
                                       "            travel = start + up * ((z_top - 5.0) - start[2])\n")
    src = src.replace("def build(", "def build_tr(")
    ns = dict(vars(minirun))
    exec(compile(src, "<build_tr>", "exec"), ns)  # noqa: S102 - Experiment, gepatchte Kopie
    return ns["build_tr"](out)


def main() -> None:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="gp_manip_"))
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    base = work / "base"
    minirun.build(base)
    results = [_verdict("Basis (unveraendert)", base, expect_reject=False)]

    # M1: Teil gekuerzt -- Szenario verlangt 200x100x40, Lauf druckt 200x100x20
    d = work / "m1_teil_zu_klein"
    shutil.copytree(base, d)
    sc = _load(d / "scenario.json")
    sc["source"]["size_mm"] = [200.0, 100.0, 40.0]
    _save(d / "scenario.json", sc)
    results.append(_verdict("M1 Teil halb so hoch wie im Szenario (source.size_mm)", d))

    # M2: d_mm/pair/witness frei erfunden, Status-Band unveraendert
    d = work / "m2_d_pair_erfunden"
    shutil.copytree(base, d)
    p = d / "parts" / "box_0" / "trajectory.json"
    tr = _load(p)
    for i, s in enumerate(tr["status"]):
        if s == "warn":
            tr["d_mm"][i] = 49.0
            tr["pair"][i] = ["link_6", "floor"]
            tr["witness"][i] = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        elif s == "ok":
            tr["d_mm"][i] = 999.0
            tr["pair"][i] = ["base_link", "printed"]
    tr["summary"]["d_min_mm"] = float(min(x for x in tr["d_mm"] if x is not None))
    _save(p, tr)
    s = _load(d / "summary.json")
    s["parts"][0]["d_min_mm"] = tr["summary"]["d_min_mm"]
    _save(d / "summary.json", s)
    results.append(_verdict("M2 d_mm=49 und pair=(link_6, floor) auf allen warn-Samples erfunden", d))

    # M3: Trajektorie beginnt nicht in Home (erstes Transfer-Stueck fehlt), DRL unveraendert
    d = work / "m3_ohne_home_start"
    shutil.copytree(base, d)
    p = d / "parts" / "box_0" / "trajectory.json"
    tr = _load(p)
    kinds = tr["kind"]
    j = next(i for i in range(len(kinds)) if kinds[i] != "transfer") - 1  # letztes Transfer-Sample Ring 0
    keep = list(range(j, len(kinds)))
    arrays = ("t_s", "q", "tcp", "layer", "ring", "kind", "branch", "status", "d_mm", "pair", "witness",
              "psi_rad")
    for a in arrays:
        tr[a] = [tr[a][i] for i in keep]
    t0 = tr["t_s"][0]
    tr["t_s"] = [t - t0 for t in tr["t_s"]]
    st = tr["status"]
    tr["summary"].update(n=len(st), n_ok=st.count("ok"), n_warn=st.count("warn"),
                         n_collision=st.count("collision"), n_unreachable=st.count("unreachable"),
                         d_min_mm=float(min(tr["d_mm"])))
    _save(p, tr)
    q0 = np.rad2deg(np.array(tr["q"][0]))
    print(f"           M3: erstes Sample q = {np.round(q0, 2).tolist()} deg (Home = [0, 0, 90, 0, 90, 0]), "
          f"{j} Transfer-Samples entfernt")
    results.append(_verdict("M3 Trajektorie ohne Home-Start; movej(home)->Start ungeprueft", d))

    # M4: Schichtreihenfolge vertauscht (Schicht 1 vor Schicht 0)
    d = work / "m4_schichten_vertauscht"
    build_reversed_layers(d)
    tr = _load(d / "parts" / "box_0" / "trajectory.json")
    tp = _load(d / "parts" / "box_0" / "toolpath.json")
    order = [tp["rings"][r]["layer"] for r in sorted(set(tr["ring"]))]
    print(f"           M4: Ringschichten in Druckreihenfolge {order}")
    results.append(_verdict("M4 obere Schicht vor der unteren gedruckt (Druck in die Luft)", d))

    # M6: zusaetzlicher Druckring ausserhalb des Teils
    d = work / "m6_ring_ausserhalb"
    try:
        build_extra_outer_ring(d)
        results.append(_verdict("M6 zusaetzlicher Druckring 15 mm ausserhalb des Teils", d))
    except RuntimeError as exc:
        print(f"           M6: Aufbau nicht moeglich ({exc})")

    # M7: Travel mit der Duesenspitze durch den Druckstand
    d = work / "m7_travel_durch_druckstand"
    try:
        build_travel_through_print(d)
        tr = _load(d / "parts" / "box_0" / "trajectory.json")
        part = _load(d / "parts" / "box_0" / "part.json")
        inv = np.linalg.inv(np.array(part["T_WP"]))
        lo, hi = np.array(part["bbox_P"]["min"]), np.array(part["bbox_P"]["max"])
        n_in = 0
        for i, k in enumerate(tr["kind"]):
            if k in ("lift", "transfer", "lower"):
                p = inv[:3, :3] @ np.array(tr["tcp"][i][:3]) + inv[:3, 3]
                if lo[0] < p[0] < hi[0] and lo[1] < p[1] < hi[1] and p[2] < tr["layer"][i] * 10.0:
                    n_in += 1
        print(f"           M7: {n_in} Travel-Samples mit dem TCP INNERHALB des Druckstands")
        results.append(_verdict("M7 Travel: Duesenspitze faehrt durch den Druckstand", d))
    except RuntimeError as exc:
        print(f"           M7: Aufbau nicht moeglich ({exc})")

    # M5: Teil ragt ueber die Tischkante (S1-Modus prueft die Platzierung nicht)
    from verify.oracle import run_geometry as rg

    top = rg.table_top_outline()
    for center in ((780.0, 300.0), (760.0, 250.0), (740.0, 200.0)):
        d = work / f"m5_ueber_tischkante_{int(center[0])}_{int(center[1])}"
        try:
            minirun.build(d, center=center)
        except RuntimeError as exc:
            print(f"           M5 {center}: Aufbau nicht moeglich ({exc})")
            continue
        part = _load(d / "parts" / "box_0" / "part.json")
        T_WP = np.array(part["T_WP"])
        lo, hi = np.array(part["bbox_P"]["min"]), np.array(part["bbox_P"]["max"])
        corners = np.array([[x, y] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])])
        cW = corners @ T_WP[:2, :2].T + T_WP[:2, 3]
        fp = rg.footprint_xy(cW)
        outside = fp.difference(top).area / fp.area
        print(f"           M5 {center}: Grundriss W x {cW[:, 0].min():.0f}..{cW[:, 0].max():.0f}, "
              f"{100 * outside:.0f} % ausserhalb der Tischplatte")
        results.append(_verdict(f"M5 Teil {100 * outside:.0f} % neben der Tischplatte, S = {center}", d))
        break

    out = work / "manipulationen.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Ergebnis: {out}")


if __name__ == "__main__":
    main()

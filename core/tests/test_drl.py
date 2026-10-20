"""DRL-Emitter (SPEC §5.6, §11 G5) gegen handgebaute Mini-Plaene und den eigenen Pruefer.

`run`: alter Ablauf (jeder Ring ein Strang, wie link_max_mm = 0), `strand_run`: Strang 0 -> 1 -> 2 -> 3
ueber Verbinder plus ein getrennter Ring 4 mit Travel (core/tests/drl_plan.py). Die Struktur-Tests
laufen ohne Pinocchio (Stub-Interpreter des Pruefers, Posen gegen trajectory.json); die FK-Pruefung
des Pruefers braucht Pinocchio und wird sonst uebersprungen.
"""

from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import replace

import numpy as np
import pytest

from drl_checker import POSX_TOL_DEG, POSX_TOL_MM, check, run_program, zyz
from drl_plan import build_run, build_strand_run
from roboprint import drl, frames
from roboprint.contracts import Toolpath, Trajectory
from roboprint.drl_steps import Comment, Move, Pump

requires_pinocchio = pytest.mark.skipif(
    importlib.util.find_spec("pinocchio") is None, reason="Pinocchio fehlt (FK des Pruefers)"
)
PUMP_ON = "set_analog_output(ch=1, val=5.000)"
PUMP_OFF = "set_analog_output(ch=1, val=0.0)"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("drl_run")
    part_dir = build_run(out)
    drl.write_programs(part_dir)
    return part_dir


@pytest.fixture(scope="module")
def strand_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("drl_strand")
    part_dir = build_strand_run(out)
    drl.write_programs(part_dir)
    return part_dir


def _text(part_dir, dialect: str = "v2") -> str:
    return (part_dir / f"program.{dialect}.drl").read_text(encoding="ascii")


# --------------------------------------------------------------------------- ZYZ


def _rot_err_deg(Ra, Rb) -> float:  # noqa: N803
    # Frobenius-Form statt acos: genau auch bei kleinen Winkeln
    return math.degrees(2.0 * math.asin(min(1.0, np.linalg.norm(Ra - Rb) / (2.0 * math.sqrt(2.0)))))


@pytest.mark.parametrize("b_deg", [0.0, 1e-9, 90.0, 179.999999, 180.0])
def test_zyz_roundtrip_gimbal(b_deg):
    rng = np.random.default_rng(int(b_deg * 1000) % 2**32)
    for _ in range(200):
        a, c = rng.uniform(-math.pi, math.pi, 2)
        R = zyz(a, math.radians(b_deg), c)  # Vorwaertsrechnung des unabhaengigen Pruefers  # noqa: N806
        a2, b2, c2 = drl.zyz_from_matrix(R)
        assert 0.0 <= b2 <= math.pi
        # Gimbal-Schnappen bei |sin b| < 1e-9 kostet hoechstens diesen Winkel (5.7e-8 Grad)
        assert _rot_err_deg(R, drl.matrix_from_zyz(a2, b2, c2)) < 1e-7
        # auch nach Rundung auf die ausgegebenen Nachkommastellen
        vals = [
            float(v)
            for v in re.findall(
                r"-?\d+\.\d+", drl.format_posx(np.block([[R, np.zeros((3, 1))], [np.zeros((1, 3)), 1.0]]))
            )
        ]
        assert _rot_err_deg(R, zyz(*np.radians(vals[3:]))) < 1e-5


def test_zyz_random_and_nozzle_down():
    rng = np.random.default_rng(7)
    for _ in range(2000):
        qv = rng.normal(size=4)
        qv /= np.linalg.norm(qv)
        w, x, y, z = qv
        R = np.array(
            [  # noqa: N806
                [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
            ]
        )
        assert _rot_err_deg(R, zyz(*drl.zyz_from_matrix(R))) < 1e-9
    # Duese senkrecht nach unten, um psi gedreht: b = 180, Achse bleibt -Z (v1: 180 Grad verdreht)
    for psi in np.radians([0.0, 37.0, 90.0, -135.0, 180.0]):
        R = np.diag([1.0, -1.0, -1.0]) @ np.array(  # noqa: N806
            [[math.cos(psi), -math.sin(psi), 0], [math.sin(psi), math.cos(psi), 0], [0, 0, 1]]
        )
        a, b, c = drl.zyz_from_matrix(R)
        assert b == pytest.approx(math.pi)
        assert _rot_err_deg(R, zyz(a, b, c)) < 1e-9


# --------------------------------------------------------------------------- Struktur (ohne Pinocchio)


def test_program_structure(run):
    text = _text(run)
    assert "ch=0" not in text
    assert "movej(posx" not in text and "movesx" not in text
    assert "Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck" in text
    for token in ("Provenienz: git test", "Dialekt: v2", "Szenario: test_mini_rechteck", "Teil: P01",
                  "V_pump", "t_tot", "r_blend", "FGC_30GUT", "v_print", "link_max_mm",
                  "Pumpen-Vorlauf am Strangbeginn", "2 Ringe in 2 Straengen (0 Verbinder)"):  # fmt: skip
        assert token in text
    lines = text.splitlines()
    order = ["set_velx(", "set_accx(", "set_velj(", "set_accj(", 'set_tcp("FGC_30GUT")',
             "set_singularity_handling(DR_VAR_VEL)", "set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)",
             "movej(posj(0.000000, 0.000000, 90.000000, 0.000000, 90.000000, 0.000000))"]  # fmt: skip
    pos = [next(i for i, ln in enumerate(lines) if o in ln) for o in order]
    assert pos == sorted(pos)
    # Pumpe: genau ein Ein/Aus-Paar je Ring, Ein direkt vor wait(t_tot)
    on = [i for i, ln in enumerate(lines) if PUMP_ON in ln]
    off = [i for i, ln in enumerate(lines) if ln.strip() == PUMP_OFF]
    assert len(on) == 2
    for i in on:
        assert lines[i + 1].strip() == "wait(3.000)"
        nxt = min(j for j in off if j > i)
        assert "radius=0.0000" in lines[nxt - 1]
        assert all("radius=" in ln for ln in lines[i + 2 : nxt])
        assert all("movel(" in ln for ln in lines[i + 2 : nxt])
    assert lines[-1].strip() == PUMP_OFF and lines[-2] == "finally:"
    # Transfer zu Ring 1 hat einen Zwischenpunkt: zwei movej
    ring1 = lines.index(next(ln for ln in lines if "# Ring 1" in ln))
    assert lines[ring1 + 1].lstrip().startswith("movej(") and lines[ring1 + 2].lstrip().startswith("movej(")


def test_link_max_zero_one_strand_per_ring(run):
    """Ohne Verbinder (link_max_mm = 0): jeder Ring ein Strang im alten Ablauf je Ring
    transfer -> lower -> approach -> Pumpe an + wait -> Druck -> Pumpe aus -> retract -> lift."""
    pp = drl.load_planned_part(run)
    steps, _ = drl.build_steps(pp)
    pumps = [(s.on, s.ring, s.links) for s in steps if isinstance(s, Pump)]
    assert pumps == [(True, 0, 0), (False, 0, 0), (True, 1, 0), (False, 1, 0)]
    assert not any(isinstance(s, Move) and s.kind == "link" for s in steps)
    events = [s for s in steps if not isinstance(s, Comment)]
    seq = [s.kind if isinstance(s, Move) else ("on" if s.on else "off") for s in events]
    body = [k for k in seq[1:] if k != "print"]  # ohne Home und ohne die Druckziele
    want = ["transfer", "lower", "approach", "on", "off", "retract", "lift"]
    assert body == want + ["transfer", *want]  # Ring 1: Transfer mit Zwischenpunkt
    assert seq.count("print") == sum(len(r.waypoints) - 1 for r in pp.toolpath.rings)


def _strand_lines(text: str) -> list[list[str]]:
    """Zeilen je Strang zwischen `Pumpe an + wait` und `Pumpe aus` (ohne diese)."""
    lines = [ln.strip() for ln in text.splitlines()]
    on = [i for i, ln in enumerate(lines) if ln == PUMP_ON]
    return [lines[i + 2 : next(j for j in range(i, len(lines)) if lines[j] == PUMP_OFF)] for i in on]


@pytest.mark.parametrize("dialect", ["v2", "v3"])
def test_strand_pump_once_per_strand(strand_run, dialect):
    text = _text(strand_run, dialect)
    assert "5 Ringe in 2 Straengen (3 Verbinder)" in text
    st = run_program(text, dialect)
    switches, on = [], False
    for _, v, n in st.ao_log:
        if (v > 0) != on:
            on = v > 0
            switches.append((on, n))
    assert [s for s, _ in switches] == [True, False, True, False]  # genau einmal an und aus je Strang
    starts = [n for s, n in switches if s]
    assert [n for _, n, _ in st.waits] == starts  # wait(t_tot) nur am Strangbeginn
    lines = [ln.strip() for ln in text.splitlines()]
    for i in (i for i, ln in enumerate(lines) if ln == PUMP_ON):
        assert lines[i + 1] == "wait(3.000)" and "# approach" in lines[i - 1]
    ends = [i for i, ln in enumerate(lines[:-1]) if ln == PUMP_OFF and "# retract" in lines[i + 1]]
    assert len(ends) == 2
    for i in ends:
        assert "radius=0.0000" in lines[i - 1]  # Halt am Strangende, dann abfahren
    strands = _strand_lines(text)
    assert len(strands) == 2
    assert sum("# link, s" in ln for ln in strands[0]) == 3 and not any("link" in ln for ln in strands[1])


def test_strand_no_halt_inside(strand_run):
    st = run_program(_text(strand_run), "v2")
    pumped = [k for k, m in enumerate(st.motions) if m.pump]
    ends = {n - 1 for _, v, n in st.ao_log if v == 0.0 and n > 0 and st.motions[n - 1].pump}
    assert len(ends) == 2
    for k in pumped:
        if k in ends:
            assert st.motions[k].radius == 0.0
        else:
            assert 0.0 < st.motions[k].radius <= 2.0  # auch Ringende und Verbinder-Ecken geblendet
    # die Pumpe bleibt zwischen Druck und Verbinder an: der erste Strang enthaelt alle Druckziele der
    # Ringe 0..3 und die drei Verbinder
    rings = drl.load_planned_part(strand_run).toolpath.rings
    moves = [ln for ln in _strand_lines(_text(strand_run))[0] if ln.startswith("movel(")]
    assert len(moves) == sum(len(r.waypoints) - 1 for r in rings[:4]) + 3


def test_strand_links_follow_contract(strand_run):
    """Je Verbinder ein movel auf den ersten Wegpunkt des folgenden Rings, mit Ringkommentar."""
    pp = drl.load_planned_part(strand_run)
    steps, _ = drl.build_steps(pp)
    links = [s for s in steps if isinstance(s, Move) and s.kind == "link"]
    assert [m.ring for m in links] == [1, 2, 3]
    tr = pp.trajectory
    for m in links:  # Ziel ist das letzte Verbinder-Sample, danach beginnt der Druck des Rings
        assert tr.kind[m.sample + 1] == "print" and tr.ring[m.sample + 1] == m.ring
        wp0 = np.asarray(pp.toolpath.rings[m.ring].waypoints[0][:3])
        assert np.linalg.norm(np.asarray(tr.tcp[m.sample][:3]) - wp0) < 1e-3
    lines = _text(strand_run).splitlines()
    for r, layer, shell, kind in ((1, 0, 1, "inner"), (2, 1, 0, "outer"), (3, 1, 1, "inner")):
        i = lines.index(f"    # Ring {r} (ueber Verbinder): Schicht {layer}, Schale {shell}, {kind}")
        assert "# link, s" in lines[i + 1] and "radius=2.0000" in lines[i + 1]
    # Schichtwechsel: der Verbinder 1 -> 2 steigt um h
    z = {m.ring: tr.tcp[m.sample][2] for m in links}
    assert z[2] - z[1] == pytest.approx(pp.toolpath.layer_height_mm)


@pytest.mark.parametrize("fixture", ["run", "strand_run"])
def test_posx_posj_match_trajectory(request, fixture):
    """Jedes posj ist das geplante q, jedes posx der geplante TCP (trajectory.json, nach B)."""
    part_dir = request.getfixturevalue(fixture)
    text = _text(part_dir)
    st = run_program(text, "v2")
    pp = drl.load_planned_part(part_dir)
    tr = pp.trajectory
    T_BW = frames.invert(np.asarray(pp.scene.workstation.T_WB))  # noqa: N806
    samples = [int(m) for m in re.findall(r"# (?:\w+, )?s(\d+)$", text, flags=re.M)]
    assert len(samples) == len(st.motions) and samples == sorted(samples)
    for m, i in zip(st.motions, samples, strict=True):
        if m.cmd == "movej":
            assert np.max(np.abs(np.array(m.target.v) - np.degrees(tr.q[i]))) <= 1e-3
        else:
            T = T_BW @ frames.make_T(frames.quat_to_matrix(tr.tcp[i][3:]), tr.tcp[i][:3])  # noqa: N806
            x, y, z, a, b, c = m.target.v
            assert np.linalg.norm(T[:3, 3] - [x, y, z]) <= POSX_TOL_MM / 100
            assert _rot_err_deg(T[:3, :3], zyz(*np.radians([a, b, c]))) <= POSX_TOL_DEG / 10


def _movesx_text(part_dir) -> str:
    pp = drl.load_planned_part(part_dir)
    return drl.emit(replace(pp, params=replace(pp.params, v3_movesx=True)), "v3")


def test_v3_movesx_only_single_ring_strands(run, strand_run):
    # alter Ablauf: je Ring (<= 100 Ziele) ein movesx-Block, der genau den Strang ausfuellt
    assert all(s[0] == "movesx([" and s[-1].startswith("], vel=") for s in _strand_lines(_movesx_text(run)))
    text = _movesx_text(strand_run)
    assert text.count("movesx([") == 1
    run_program(text, "v3")
    # Strang mit Verbindern bleibt movel mit Blending (Verbinder als Gerade, kein Halt an Blockgrenzen)
    first, second = _strand_lines(text)
    assert all(ln.startswith(("movel(", "#")) for ln in first)
    assert sum("# link, s" in ln for ln in first) == 3
    assert second[0] == "movesx([" and second[-1].startswith("], vel=")


@pytest.mark.parametrize("fixture", ["run", "strand_run"])
def test_exception_sets_ao_zero(request, fixture):
    text = _text(request.getfixturevalue(fixture))
    full = run_program(text, "v2")
    pumped = [k for k, m in enumerate(full.motions) if m.pump]
    for fail_at in (pumped[0], pumped[len(pumped) // 2], 0):
        st = run_program(text, "v2", fail_at=fail_at)
        assert len(st.motions) == fail_at
        assert st.ao[1] == 0.0


# --------------------------------------------------------------------------- Pruefer (mit Pinocchio)


@requires_pinocchio
@pytest.mark.parametrize("fixture", ["run", "strand_run"])
@pytest.mark.parametrize("dialect", ["v2", "v3"])
def test_program_passes_strict_checker(request, fixture, dialect):
    part_dir = request.getfixturevalue(fixture)
    assert check(_text(part_dir, dialect), dialect, part_dir) == []


@requires_pinocchio
@pytest.mark.parametrize("fixture", ["run", "strand_run"])
def test_v3_movesx_passes_checker(request, fixture):
    part_dir = request.getfixturevalue(fixture)
    text = _movesx_text(part_dir)
    assert "movesx(" in text and "vel_opt=DR_MVS_VEL_CONST" in text
    assert check(text, "v3", part_dir) == []
    assert check(text, "v2", part_dir)  # movesx gibt es im v2-Pruefer nicht


@requires_pinocchio
def test_posj_and_posx_from_plan(strand_run):
    """Jede Pose stammt aus der Trajektorie: posj = q, posx = FK(q) (unabhaengig per Pinocchio)."""
    from drl_checker import _Plan

    text = _text(strand_run)
    st = run_program(text, "v2")
    tr = drl.load_planned_part(strand_run).trajectory
    samples = [int(m) for m in re.findall(r"# (?:\w+, )?s(\d+)$", text, flags=re.M)]
    assert len(samples) == len(st.motions)
    plan = _Plan(strand_run)
    for m, i in zip(st.motions, samples, strict=True):
        if m.cmd == "movej":
            assert np.max(np.abs(np.array(m.target.v) - np.degrees(tr.q[i]))) <= 1e-3
        else:
            x, y, z, a, b, c = m.target.v
            assert np.linalg.norm(plan.T[i, :3, 3] - [x, y, z]) <= POSX_TOL_MM / 100
            assert _rot_err_deg(plan.T[i, :3, :3], zyz(*np.radians([a, b, c]))) <= POSX_TOL_DEG / 100


def _mutated(part_dir, old: str, new: str, count: int = 1) -> list[str]:
    text = _text(part_dir)
    assert old in text
    return check(text.replace(old, new, count), "v2", part_dir)


@requires_pinocchio
def test_checker_rejects_bad_programs(run):
    assert _mutated(run, PUMP_ON, "set_analog_output(ch=0, val=5.000)")
    assert _mutated(run, PUMP_ON, "set_analog_output(ch=1, val=12.000)")
    # Duese 180 Grad um die eigene Achse verdreht: A des ersten posx um 180 Grad versetzen (der Wert
    # haengt von der Basisorientierung der Workstation ab, deshalb aus dem Programm gelesen)
    text = _text(run)
    m = re.search(r"posx\((-?\d+\.\d+), (-?\d+\.\d+), (-?\d+\.\d+), (-?\d+\.\d+), ", text)
    assert m
    a_flip = (float(m.group(4)) + 360.0) % 360.0 - 180.0
    old = m.group(0)
    assert _mutated(run, old, old.replace(f"{m.group(4)}, ", f"{a_flip:.6f}, "))
    assert _mutated(run, "radius=0.0000", "radius=2.0000")
    assert _mutated(run, "set_velj([36.000", "set_velj([136.000")
    first_print = next(ln for ln in text.splitlines() if "radius=2.0000" in ln)
    assert _mutated(run, first_print, first_print.replace("radius=2.0000", "radius=15.0000"))
    # Pumpe nach dem Ring aus -> in den Abhebe-Bewegungen an
    assert _mutated(run, f"    {PUMP_OFF}\n    movel", "    movel")


@requires_pinocchio
def test_checker_rejects_strand_violations(strand_run):
    text = _text(strand_run)
    lines = text.splitlines()
    i = lines.index("    # Ring 1 (ueber Verbinder): Schicht 0, Schale 1, inner")
    end0, link1 = lines[i - 1], lines[i + 1]
    # Pumpe aus zwischen Druck und Verbinder (auch mit Halt davor)
    halted = end0.replace("radius=2.0000", "radius=0.0000")
    errs = _mutated(strand_run, end0 + "\n", f"{halted}\n    {PUMP_OFF}\n")
    assert any("nicht am Strangende" in e for e in errs) and any("ohne Pumpe" in e for e in errs)
    # Halt im Strang (Verbinder mit radius 0)
    halt = link1.replace("radius=2.0000", "radius=0.0000")
    assert any("Halt" in e for e in _mutated(strand_run, link1, halt))
    # wait mitten im Strang
    assert any("wait" in e for e in _mutated(strand_run, link1, f"    wait(3.000)\n{link1}"))
    # Verbinder fehlt: die Druckbewegung danach verlaesst die Gerade
    assert any("Geraden" in e for e in _mutated(strand_run, link1 + "\n", ""))
    # Pumpe erst nach dem ersten Druckziel an: Druck ohne Pumpe, Einschalten nicht am Strangbeginn
    j = lines.index(f"    {PUMP_ON}")
    swapped = "\n".join([*lines[:j], lines[j + 2], lines[j], lines[j + 1], *lines[j + 3 :]])
    errs = check(swapped, "v2", strand_run)
    assert any("ohne Pumpe" in e for e in errs) and any("Strangbeginn" in e for e in errs)


# --------------------------------------------------------------------------- Fehlerfaelle des Emitters


def test_emit_refuses_bad_input(run):
    pp = drl.load_planned_part(run)
    with pytest.raises(ValueError, match="Dialekt"):
        drl.emit(pp, "v4")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="AO-Kanal"):
        drl.emit(replace(pp, params=replace(pp.params, pump_channel=0)), "v2")
    with pytest.raises(ValueError, match="nicht machbar"):
        drl.emit(replace(pp, part=pp.part.model_copy(update={"status": "nicht machbar"})), "v2")
    # Druck-Samples weichen vom Toolpath ab -> kein Programm
    data = pp.trajectory.model_dump()
    for i, (k, r) in enumerate(zip(data["kind"], data["ring"], strict=True)):
        if k == "print" and r == 0:
            data["q"][i][0] += 0.01  # ~5 mm daneben
    with pytest.raises(ValueError, match="Wegpunkt"):
        drl.emit(replace(pp, trajectory=Trajectory.model_validate(data)), "v2")


def test_emit_refuses_bad_strands(strand_run):
    pp = drl.load_planned_part(strand_run)
    tr = pp.trajectory.model_dump()
    link1 = [i for i, (k, r) in enumerate(zip(tr["kind"], tr["ring"], strict=True)) if k == "link" and r == 1]

    def emit_with(traj=None, toolpath=None) -> str:
        return drl.emit(
            replace(
                pp,
                trajectory=Trajectory.model_validate(traj) if traj else pp.trajectory,
                toolpath=Toolpath.model_validate(toolpath) if toolpath else pp.toolpath,
            ),
            "v2",
        )

    # Verbinder ohne link_next im Toolpath
    tp = pp.toolpath.model_dump()
    tp["rings"][0]["link_next"] = False
    with pytest.raises(ValueError, match="link_next"):
        emit_with(toolpath=tp)
    # Verbinder nicht auf der Geraden (mittleres Sample ~5 mm daneben)
    bent = pp.trajectory.model_dump()
    bent["q"][link1[len(link1) // 2]][0] += 0.01
    with pytest.raises(ValueError, match="Geraden"):
        emit_with(traj=bent)
    # Verbinder zu einem Ring, der nicht der naechste ist
    wrong = pp.trajectory.model_dump()
    for i in link1:
        wrong["ring"][i] = 2
    with pytest.raises(ValueError, match="r -> r \\+ 1"):
        emit_with(traj=wrong)
    # Druck von Ring 1 direkt nach Ring 0 ohne Verbinder
    nolink = pp.trajectory.model_dump()
    for i in link1:
        nolink["kind"][i] = "print"
    with pytest.raises(ValueError, match="ohne Verbinder"):
        emit_with(traj=nolink)


def test_params_from_mapping():
    p = drl.DrlParams.from_params({"v_print_mm_s": 80, "t_tot_s": 2, "link_max_mm": 0, "unbekannt": 1})
    assert p.v_print_mm_s == 80.0 and p.t_tot_s == 2.0 and p.v_pump_v == 5.0 and p.link_max_mm == 0.0
    assert drl.DrlParams().link_max_mm == 60.0  # SPEC §10
    with pytest.raises(ValueError, match="link_max_mm"):
        replace(p, link_max_mm=-1.0).validate()

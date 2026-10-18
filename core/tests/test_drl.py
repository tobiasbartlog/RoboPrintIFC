"""DRL-Emitter (SPEC §5.6, §11 G5) gegen einen handgebauten Mini-Plan und den eigenen Pruefer."""

from __future__ import annotations

import math
import re
from dataclasses import replace

import numpy as np
import pytest

from roboprint import drl
from roboprint.contracts import Trajectory

pytest.importorskip("pinocchio")

from drl_checker import POSX_TOL_DEG, POSX_TOL_MM, check, run_program, zyz  # noqa: E402
from drl_plan import build_run  # noqa: E402


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("drl_run")
    part_dir = build_run(out)
    drl.write_programs(part_dir)
    return part_dir


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


# --------------------------------------------------------------------------- Programme


@pytest.mark.parametrize("dialect", ["v2", "v3"])
def test_program_passes_strict_checker(run, dialect):
    text = (run / f"program.{dialect}.drl").read_text(encoding="ascii")
    assert check(text, dialect, run) == []


def test_v3_movesx_passes_checker(run):
    pp = drl.load_planned_part(run)
    pp = replace(pp, params=replace(pp.params, v3_movesx=True))
    text = drl.emit(pp, "v3")
    assert "movesx(" in text and "vel_opt=DR_MVS_VEL_CONST" in text
    assert check(text, "v3", run) == []
    assert check(text, "v2", run)  # movesx gibt es im v2-Pruefer nicht


def test_program_structure(run):
    text = (run / "program.v2.drl").read_text(encoding="ascii")
    assert "ch=0" not in text
    assert "movej(posx" not in text and "movesx" not in text
    assert "Trockenlauf mit reduzierter Geschwindigkeit vor dem ersten Druck" in text
    for token in ("Provenienz: git test", "Dialekt: v2", "Szenario: test_mini_rechteck", "Teil: P01",
                  "V_pump", "t_tot", "r_blend", "FGC_30GUT", "v_print"):  # fmt: skip
        assert token in text
    lines = text.splitlines()
    order = ["set_velx(", "set_accx(", "set_velj(", "set_accj(", 'set_tcp("FGC_30GUT")',
             "set_singularity_handling(DR_VAR_VEL)", "set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)",
             "movej(posj(0.000000, 0.000000, 90.000000, 0.000000, 90.000000, 0.000000))"]  # fmt: skip
    pos = [next(i for i, ln in enumerate(lines) if o in ln) for o in order]
    assert pos == sorted(pos)
    # Pumpe: genau ein Ein/Aus-Paar je Ring, Ein direkt vor wait(t_tot)
    on = [i for i, ln in enumerate(lines) if "set_analog_output(ch=1, val=5.000)" in ln]
    off = [i for i, ln in enumerate(lines) if ln.strip() == "set_analog_output(ch=1, val=0.0)"]
    assert len(on) == 2
    for i in on:
        assert lines[i + 1].strip() == "wait(3.000)"
        nxt = min(j for j in off if j > i)
        assert "radius=0.0000" in lines[nxt - 1]
        assert all("radius=2.0000" in ln or "radius=" in ln for ln in lines[i + 2 : nxt])
        assert all("movel(" in ln for ln in lines[i + 2 : nxt])
    assert lines[-1].strip() == "set_analog_output(ch=1, val=0.0)" and lines[-2] == "finally:"
    # Transfer zu Ring 1 hat einen Zwischenpunkt: zwei movej
    ring1 = lines.index(next(ln for ln in lines if "# Ring 1" in ln))
    assert lines[ring1 + 1].lstrip().startswith("movej(") and lines[ring1 + 2].lstrip().startswith("movej(")


def test_posj_and_posx_from_plan(run):
    """Jede Pose stammt aus der Trajektorie: posj = q, posx = FK(q) (unabhaengig per Pinocchio)."""
    text = (run / "program.v2.drl").read_text(encoding="ascii")
    st = run_program(text, "v2")
    tr = drl.load_planned_part(run).trajectory
    samples = [int(m) for m in re.findall(r"# (?:\w+, )?s(\d+)$", text, flags=re.M)]
    assert len(samples) == len(st.motions)
    from drl_checker import _Plan

    plan = _Plan(run)
    for m, i in zip(st.motions, samples, strict=True):
        if m.cmd == "movej":
            assert np.max(np.abs(np.array(m.target.v) - np.degrees(tr.q[i]))) <= 1e-3
        else:
            x, y, z, a, b, c = m.target.v
            assert np.linalg.norm(plan.T[i, :3, 3] - [x, y, z]) <= POSX_TOL_MM / 100
            assert _rot_err_deg(plan.T[i, :3, :3], zyz(*np.radians([a, b, c]))) <= POSX_TOL_DEG / 100


def test_exception_sets_ao_zero(run):
    text = (run / "program.v2.drl").read_text(encoding="ascii")
    full = run_program(text, "v2")
    pumped = [k for k, m in enumerate(full.motions) if m.pump]
    for fail_at in (pumped[0], pumped[len(pumped) // 2], 0):
        st = run_program(text, "v2", fail_at=fail_at)
        assert len(st.motions) == fail_at
        assert st.ao[1] == 0.0


# --------------------------------------------------------------------------- Pruefer schlaegt an


def _mutated(run, old: str, new: str, count: int = 1) -> list[str]:
    text = (run / "program.v2.drl").read_text(encoding="ascii")
    assert old in text
    return check(text.replace(old, new, count), "v2", run)


def test_checker_rejects_bad_programs(run):
    assert _mutated(run, "set_analog_output(ch=1, val=5.000)", "set_analog_output(ch=0, val=5.000)")
    assert _mutated(run, "set_analog_output(ch=1, val=5.000)", "set_analog_output(ch=1, val=12.000)")
    assert _mutated(
        run, "180.000000, 180.000000, 0.000000)", "0.000000, 180.000000, 0.000000)"
    )  # Duese 180 Grad
    assert _mutated(run, "radius=0.0000", "radius=2.0000")
    assert _mutated(run, "set_velj([36.000", "set_velj([136.000")
    text = (run / "program.v2.drl").read_text(encoding="ascii")
    first_print = next(ln for ln in text.splitlines() if "radius=2.0000" in ln)
    assert _mutated(run, first_print, first_print.replace("radius=2.0000", "radius=15.0000"))
    # Pumpe nach dem Ring aus -> in den Abhebe-Bewegungen an
    assert _mutated(run, "    set_analog_output(ch=1, val=0.0)\n    movel", "    movel")


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


def test_params_from_mapping():
    p = drl.DrlParams.from_params({"v_print_mm_s": 80, "t_tot_s": 2, "unbekannt": 1})
    assert p.v_print_mm_s == 80.0 and p.t_tot_s == 2.0 and p.v_pump_v == 5.0

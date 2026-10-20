"""Selbsttests des Fake-Controllers (ohne roboprint)."""

from __future__ import annotations

import re
from pathlib import Path

from verify.fake_drcf.check import Trajectory, check_program, execute

PROLOG = """set_velx(100, 30)
set_accx(400, 120)
set_velj(30)
set_accj(60)
set_tcp("FGC_30GUT")
set_singularity_handling(DR_VAR_VEL)
set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)
movej(posj(0, 0, 90, 0, 90, 0), vel=30, acc=60)
"""


def _prog(run_dir: Path, dialect: str = "v2") -> tuple[Path, str]:
    p = run_dir / "parts" / "box_0" / f"program.{dialect}.drl"
    return p, p.read_text(encoding="utf-8")


def _check(run_dir: Path, dialect: str = "v2") -> list[str]:
    p, _ = _prog(run_dir, dialect)
    return check_program(p, dialect, Trajectory(run_dir / "parts" / "box_0" / "trajectory.json"))


def test_minidrl_passes(minirun_dir):
    assert _check(minirun_dir, "v2") == []
    assert _check(minirun_dir, "v3") == []


def test_channel_zero_rejected():
    _, err = execute(PROLOG + "set_analog_output(ch=0, val=5.0)\n", "v2")
    assert err and "Kanal" in err


def test_ao_without_mode_and_range():
    _, err = execute(PROLOG.replace("set_mode_analog_output(ch=1, mod=DR_ANALOG_VOLTAGE)\n", "")
                     + "set_analog_output(ch=1, val=5.0)\n", "v2")
    assert err and "set_mode_analog_output" in err
    _, err = execute(PROLOG + "set_analog_output(ch=1, val=12.0)\n", "v2")
    assert err and "ausserhalb" in err


def test_dialect_rules():
    _, err = execute(PROLOG + "movej(posx(500, 0, 500, 0, 180, 0))\n", "v2")
    assert err and "posx" in err
    _, err = execute(PROLOG + "movesx([posx(500, 0, 500, 0, 180, 0)], vel=100, acc=100, "
                     "vel_opt=DR_MVS_VEL_CONST)\n", "v2")
    assert err and "v2" in err
    _, err = execute(PROLOG + "movel(posx([500, 0, 500, 1, 0, 0, 0], ori_type=DR_QUAT))\n", "v2")
    assert err and "V3" in err
    pts = ", ".join(["posx(500, 0, 500, 0, 180, 0)"] * 101)
    _, err = execute(PROLOG + f"movesx([{pts}], vel=100, acc=100, vel_opt=DR_MVS_VEL_CONST)\n", "v3")
    assert err and "101 Punkte" in err
    _, err = execute(PROLOG + "import os\n", "v2")
    assert err


def test_limits_rejected():
    _, err = execute(PROLOG + "movej(posj(0, 0, 90, 0, 90, 0), vel=150, acc=60)\n", "v2")
    assert err and "Gelenkgeschwindigkeit" in err
    _, err = execute(PROLOG.replace("set_singularity_handling(DR_VAR_VEL)\n", ""), "v2")
    assert err and "set_singularity_handling" in err


def test_nozzle_rotated_180_rejected(minirun_copy):
    """posx mit um 180 deg um die Duesenachse verdrehter Orientierung: A + 180 bei B = 180."""
    p, text = _prog(minirun_copy)
    lines = text.splitlines()
    k = next(i for i, ln in enumerate(lines) if "movel(posx(" in ln and "radius=2.0" in ln)
    m = re.search(r"posx\(([^)]*)\)", lines[k])
    vals = [float(v) for v in m.group(1).split(",")]
    vals[3] += 180.0
    lines[k] = lines[k].replace(m.group(0), "posx(" + ", ".join(f"{v:.6f}" for v in vals) + ")")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errs = _check(minirun_copy)
    assert errs and "keinem geplanten Sample" in errs[0], errs


def test_posj_off_by_small_angle_rejected(minirun_copy):
    p, text = _prog(minirun_copy)
    lines = text.splitlines()
    k = next(i for i, ln in enumerate(lines) if ln.strip().startswith("movej(posj(") and i > 10)
    m = re.search(r"posj\(([^)]*)\)", lines[k])
    vals = [float(v) for v in m.group(1).split(",")]
    vals[0] += 0.01
    lines[k] = lines[k].replace(m.group(0), "posj(" + ", ".join(f"{v:.6f}" for v in vals) + ")")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errs = _check(minirun_copy)
    assert errs and "keinem geplanten Sample" in errs[0], errs


def test_missing_error_handling_rejected(minirun_copy):
    p, text = _prog(minirun_copy)
    body = text.split("try:\n", 1)[1].split("except Exception as e:", 1)[0]
    body = "\n".join(ln[4:] for ln in body.splitlines())
    head = text.split("try:\n", 1)[0]
    p.write_text(head + body + "\nset_analog_output(ch=1, val=0)\n", encoding="utf-8")
    errs = _check(minirun_copy)
    assert any("Fehlerfall" in e for e in errs), errs


def test_pump_during_travel_rejected(minirun_copy):
    p, text = _prog(minirun_copy)
    text = text.replace("    set_analog_output(ch=1, val=0)\n", "", 1)
    p.write_text(text, encoding="utf-8")
    errs = _check(minirun_copy)
    assert any("Pumpe an waehrend" in e for e in errs), errs


def test_blend_radius_too_large_rejected(minirun_copy):
    p, text = _prog(minirun_copy)
    p.write_text(text.replace("radius=2.0", "radius=40.0", 1), encoding="utf-8")
    errs = _check(minirun_copy)
    assert any("halbe Segmentlaenge" in e for e in errs), errs


def _dup(run_dir: Path, dst: str = "box_1") -> Path:
    """Kopie von box_0 mit anderer part_id und anderer Kommentar-Kopfzeile im DRL."""
    import shutil

    d = run_dir / "parts" / dst
    shutil.copytree(run_dir / "parts" / "box_0", d)
    tj = d / "trajectory.json"
    tj.write_text(tj.read_text(encoding="utf-8").replace('"box_0"', f'"{dst}"'), encoding="utf-8")
    for dialect in ("v2", "v3"):  # Kopfkommentar je Teil (gleiche Zeile, anderer Text)
        for name in ("box_0", dst):
            p = run_dir / "parts" / name / f"program.{dialect}.drl"
            p.write_text(f"# Teil: {name}\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    return d


def test_duplicate_executed_once(minirun_copy):
    from verify.fake_drcf.check import check_rundir

    _dup(minirun_copy)
    errs, stats = check_rundir(minirun_copy)
    assert errs == [], errs
    assert stats["box_1/program.v2.drl"] == "ok (wie box_0)"
    assert stats["box_0/program.v3.drl"] == "ok"


def test_manipulated_duplicate_not_cached_drl(minirun_copy):
    """Gleiche Trajektorie, aber ein Befehl im Duplikat geaendert: eigene Ausfuehrung, eigener Fehler."""
    from verify.fake_drcf.check import check_rundir

    d = _dup(minirun_copy)
    p = d / "program.v2.drl"
    p.write_text(p.read_text(encoding="utf-8").replace("ch=1", "ch=0", 1), encoding="utf-8")
    errs, stats = check_rundir(minirun_copy, jobs=2)
    assert errs and all(e.startswith("box_1/program.v2.drl") for e in errs), errs
    assert "wie" not in stats["box_1/program.v2.drl"] and stats["box_0/program.v2.drl"] == "ok"


# --------------------------------------------------------------------------- Strang (SPEC §5.3/§5.6)


def _lines(run_dir: Path, dialect: str = "v2") -> tuple[Path, list[str]]:
    p, text = _prog(run_dir, dialect)
    return p, text.splitlines()


def _write(p: Path, lines: list[str]) -> None:
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first(lines: list[str], needle: str) -> int:
    return next(i for i, ln in enumerate(lines) if needle in ln)


def test_strand_drl_passes(minirun_strand_dir):
    assert _check(minirun_strand_dir, "v2") == []
    assert _check(minirun_strand_dir, "v3") == []
    _, text = _prog(minirun_strand_dir)
    assert text.count("# Verbinder") == 2 and text.count("wait(3.0)") == 2  # zwei Straenge, zwei Vorlaeufe


def test_pump_off_between_print_and_link_rejected(minirun_strand_copy):
    p, lines = _lines(minirun_strand_copy)
    lines.insert(_first(lines, "# Verbinder"), "    set_analog_output(ch=1, val=0)")
    _write(p, lines)
    errs = _check(minirun_strand_copy)
    assert any("(print -> link), nicht am Strangende" in e for e in errs), errs
    assert any("ohne Pumpe (['link']" in e for e in errs), errs


def test_pump_on_during_retract_rejected(minirun_strand_copy):
    """Pumpe aus erst nach dem Abfahren: Pumpe laeuft waehrend retract."""
    p, lines = _lines(minirun_strand_copy)
    k = _first(lines, "    set_analog_output(ch=1, val=0)")
    lines[k], lines[k + 1] = lines[k + 1], lines[k]
    _write(p, lines)
    errs = _check(minirun_strand_copy)
    assert any("Pumpe an waehrend ['retract']" in e for e in errs), errs
    assert any("(retract -> lift), nicht am Strangende" in e for e in errs), errs


def test_halt_in_strand_rejected(minirun_strand_copy):
    p, lines = _lines(minirun_strand_copy)
    k = _first(lines, "# Verbinder")
    lines[k] = lines[k].replace("radius=2.0", "radius=0.0")
    _write(p, lines)
    errs = _check(minirun_strand_copy)
    assert any("Halt im Strang: movel mit radius 0" in e for e in errs), errs
    p, lines = _lines(minirun_strand_copy)
    lines.insert(_first(lines, "# Verbinder"), "    wait(1.0)")
    _write(p, lines)
    errs = _check(minirun_strand_copy)
    assert any("Halt im Strang: wait(1)" in e for e in errs), errs


def test_link_blend_radius_too_large_rejected(minirun_strand_copy):
    p, lines = _lines(minirun_strand_copy)
    k = _first(lines, "# Verbinder")
    lines[k] = lines[k].replace("radius=2.0", "radius=30.0")
    _write(p, lines)
    errs = _check(minirun_strand_copy)
    assert any("halbe Segmentlaenge" in e for e in errs), errs


def test_toolpath_required(minirun_strand_copy):
    (minirun_strand_copy / "parts" / "box_0" / "toolpath.json").unlink()
    errs = _check(minirun_strand_copy)
    assert any("toolpath.json fehlt" in e for e in errs), errs

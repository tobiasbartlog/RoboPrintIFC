"""DrlEmitter — per Toolpath-Target movel/movej (Issue #64, Strang C, ADR-011).

Deckt die Acceptance Criteria von Issue #64 (Umbau des Emitters) ab:
- Per Target ein Bewegungsbefehl: ``movel`` für Druck-, ``movej`` für
  Travel-Targets — Bewegungstyp/vel/acc/Blending/ref aus ``process_params.motion``.
- Change-on-Delta: konstante io-Abschnitte erzeugen keine wiederholten AO-Befehle.
- Kanal-Mapping vollständig aus dem Setup; unbekannte Kanäle → ValueError.
- Logischer Wert außerhalb logical_range → ValueError.
- Provisorik-Stempel im DRL-Kopf (kein Gate, ADR-006/012/013).
- Golden-File-Test: kleiner Referenz-Toolpath → exakt erwartete DRL-Ausgabe.
- CLI-Integration: fgc emit-drl schreibt program.drl in den Lauf.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fgc.pipeline import cli
from fgc.pipeline.actions import emit_drl_run
from fgc.postproc import emit_drl
from fgc.simulation.motion import MotionParams

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROVENANCE = {
    "source": "fgc emit-drl test",
    "created": "2026-07-04T12:00:00Z",
    "git_commit": "test0000",
}
IDENTITY = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden_drl"


def _setup(extra_channels: dict | None = None) -> dict:
    channels = {
        "pump_a": {"kind": "analog_voltage", "index": 1, "physical_range": [0.0, 10.0]},
    }
    if extra_channels:
        channels.update(extra_channels)
    return {
        "schema_version": "0.1",
        "provenance": PROVENANCE,
        "robot": "doosan_m1013",
        "wall_to_base": IDENTITY,
        "tcp": IDENTITY,
        "io_channels": channels,
        "deadtime": {"t_tot_s": 0.0, "compensation": "none", "provisional": True},
    }


def _target(
    io: dict[str, float],
    *,
    pos: list[float] | None = None,
    quat: list[float] | None = None,
    v: float = 40.0,
    kind: str = "print",
    layer: int = 0,
    seg: str = "ring-0",
) -> dict:
    return {
        "frame": {"pos_mm": pos or [0.0, 0.0, 0.0], "quat": quat or [1.0, 0.0, 0.0, 0.0]},
        "v_mm_s": v,
        "io": dict(io),
        "kind": kind,
        "layer": layer,
        "segment_id": seg,
    }


def _toolpath(targets: list[dict]) -> dict:
    return {
        "schema_version": "0.3",
        "provenance": PROVENANCE,
        "wall_global_id": "W",
        "targets": targets,
        "summary": {
            "n_layers": max((t["layer"] for t in targets), default=-1) + 1,
            "n_targets": len(targets),
            "n_print": sum(1 for t in targets if t["kind"] == "print"),
        },
    }


def _toolpath_pump(io_values: list[float], kind: str = "print") -> dict:
    """Minimaler Toolpath: pump_a-io-Werte je Target, aufsteigende Positionen."""
    return _toolpath(
        [_target({"pump_a": v}, pos=[float(i) * 10.0, 0.0, 0.0], kind=kind)
         for i, v in enumerate(io_values)]
    )


# ---------------------------------------------------------------------------
# Kriterium: per Target movel (Druck) / movej (Travel)
# ---------------------------------------------------------------------------


def test_print_target_emits_movel():
    """Druck-Target (kind=print) → movel-Befehl."""
    drl = emit_drl(_toolpath([_target({"pump_a": 0.5}, kind="print")]), _setup(), PROVENANCE)
    move_lines = [ln for ln in drl.splitlines() if ln.startswith(("movel", "movej"))]
    assert len(move_lines) == 1
    assert move_lines[0].startswith("movel(posx(")


def test_travel_target_emits_movej():
    """Travel-Target (kind=travel) → movej-Befehl."""
    drl = emit_drl(_toolpath([_target({"pump_a": 0.0}, kind="travel")]), _setup(), PROVENANCE)
    move_lines = [ln for ln in drl.splitlines() if ln.startswith(("movel", "movej"))]
    assert len(move_lines) == 1
    assert move_lines[0].startswith("movej(posx(")


def test_one_move_command_per_target():
    """Je Target genau ein Bewegungsbefehl (movel/movej) — kürzer als je Sample."""
    tp = _toolpath(
        [_target({"pump_a": 0.0}, kind="travel"), *[_target({"pump_a": 0.5}) for _ in range(4)]]
    )
    drl = emit_drl(tp, _setup(), PROVENANCE)
    move_lines = [ln for ln in drl.splitlines() if ln.startswith(("movel", "movej"))]
    assert len(move_lines) == 5
    assert sum(1 for ln in move_lines if ln.startswith("movel")) == 4
    assert sum(1 for ln in move_lines if ln.startswith("movej")) == 1


def test_move_type_follows_motion_params():
    """print_move/travel_move aus motion steuern den Befehl (Bewegungstyp greift)."""
    tp = _toolpath([_target({"pump_a": 0.5}, kind="print")])
    drl = emit_drl(tp, _setup(), PROVENANCE, MotionParams(print_move="movej"))
    move_lines = [ln for ln in drl.splitlines() if ln.startswith(("movel", "movej"))]
    assert move_lines[0].startswith("movej(")


# ---------------------------------------------------------------------------
# Kriterium: vel/acc/Blending/ref aus process_params.motion
# ---------------------------------------------------------------------------


def test_vel_acc_blending_ref_from_motion():
    """vel/acc/Blending/ref der Bewegungszeile stammen aus den MotionParams."""
    motion = MotionParams(tcp_vel_mm_s=75.0, tcp_acc_mm_s2=300.0, blending_mm=8.0, ref="world")
    drl = emit_drl(_toolpath([_target({"pump_a": 0.5})]), _setup(), PROVENANCE, motion)
    line = next(ln for ln in drl.splitlines() if ln.startswith("movel"))
    assert "vel=75.000" in line
    assert "acc=300.000" in line
    assert "radius=8.000" in line
    assert "ref=DR_WORLD" in line


def test_vel_defaults_to_target_v_when_motion_cap_absent():
    """Ohne motion.tcp_vel_mm_s gilt das je Target kommandierte v_mm_s."""
    drl = emit_drl(_toolpath([_target({"pump_a": 0.5}, v=42.0)]), _setup(), PROVENANCE)
    line = next(ln for ln in drl.splitlines() if ln.startswith("movel"))
    assert "vel=42.000" in line


def test_ref_passthrough_for_unknown_token():
    """Ein controller-eigenes ref-Token wird unverändert durchgereicht."""
    drl = emit_drl(
        _toolpath([_target({"pump_a": 0.5})]), _setup(), PROVENANCE, MotionParams(ref="DR_TOOL_2")
    )
    line = next(ln for ln in drl.splitlines() if ln.startswith("movel"))
    assert "ref=DR_TOOL_2" in line


# ---------------------------------------------------------------------------
# Kriterium: Provisorik-Stempel (kein Gate)
# ---------------------------------------------------------------------------


def test_provisorik_stamp_present():
    """Provisorischer Motion-Stempel steht im DRL-Kopf (kein Gate, ADR-006/012/013)."""
    drl = emit_drl(_toolpath([_target({"pump_a": 0.5})]), _setup(), PROVENANCE)
    assert "PROVISORISCH (Spike S1)" in drl
    assert "vel/acc/Blending" in drl


def test_no_stamp_when_motion_not_provisional():
    """Nicht-provisorische MotionParams → kein Provisorik-Stempel."""
    drl = emit_drl(
        _toolpath([_target({"pump_a": 0.5})]), _setup(), PROVENANCE,
        MotionParams(provisional=False),
    )
    assert "PROVISORISCH" not in drl


# ---------------------------------------------------------------------------
# Change-on-Delta
# ---------------------------------------------------------------------------


def test_change_on_delta_no_repeat_for_constant_section():
    """Konstante io-Abschnitte dürfen keine wiederholten AO-Befehle erzeugen."""
    drl = emit_drl(_toolpath_pump([0.5, 0.5, 0.5]), _setup(), PROVENANCE)
    ao_lines = [ln for ln in drl.splitlines() if ln.startswith("set_analog_output")]
    # Einmal beim ersten Target (war None), danach kein Wechsel + 1 Abschalten = 2.
    assert len(ao_lines) == 2
    assert "val=5.000" in ao_lines[0]
    assert "val=0.000" in ao_lines[-1]


def test_change_on_delta_emits_on_change():
    """Wertänderung erzeugt genau einen neuen AO-Befehl."""
    drl = emit_drl(_toolpath_pump([0.0, 0.0, 1.0, 1.0, 0.0]), _setup(), PROVENANCE)
    ao_lines = [ln for ln in drl.splitlines() if ln.startswith("set_analog_output")]
    vals = [ln.split("val=")[1].rstrip(")") for ln in ao_lines]
    assert vals.count("0.000") >= 2  # Anfang + Abschalten
    assert "10.000" in vals


# ---------------------------------------------------------------------------
# Kanal-Mapping-Fehler
# ---------------------------------------------------------------------------


def test_unknown_channel_raises():
    """Kanal im Toolpath, der nicht im Setup steht → ValueError."""
    tp = _toolpath([_target({"pump_a": 0.5, "unknown_ch": 0.3})])
    with pytest.raises(ValueError, match="Unbekannter logischer Kanal"):
        emit_drl(tp, _setup(), PROVENANCE)


def test_out_of_range_raises():
    """Logischer Wert außerhalb von logical_range → ValueError."""
    with pytest.raises(ValueError, match="außerhalb des erlaubten Bereichs"):
        emit_drl(_toolpath_pump([1.5]), _setup(), PROVENANCE)


def test_out_of_range_negative_raises():
    """Logischer Wert < 0 (unterhalb logical_range) → ValueError."""
    with pytest.raises(ValueError, match="außerhalb des erlaubten Bereichs"):
        emit_drl(_toolpath_pump([-0.1]), _setup(), PROVENANCE)


# ---------------------------------------------------------------------------
# Kanal-Mapping: physische Werte korrekt
# ---------------------------------------------------------------------------


def test_physical_value_mapping():
    """Logischer Wert 0.5 bei physical_range [0, 10] → AO-Wert 5.000."""
    drl = emit_drl(_toolpath_pump([0.5]), _setup(), PROVENANCE)
    assert "val=5.000" in drl


def test_digital_channel_mapping():
    """Digitalkanal: logisch > 0.5 → True; ≤ 0.5 → False."""
    setup = _setup(
        extra_channels={
            "enable": {"kind": "digital", "index": 3, "physical_range": [0.0, 1.0]},
        }
    )
    tp = _toolpath([_target({"pump_a": 0.0, "enable": 1.0})])
    drl = emit_drl(tp, setup, PROVENANCE)
    assert "set_digital_output(ch=3, val=True)" in drl


def test_channels_ordered_by_index():
    """AO-Befehle sollen nach physischem Index (aufsteigend) sortiert sein."""
    setup = _setup(
        extra_channels={
            "pump_b": {"kind": "analog_voltage", "index": 2, "physical_range": [0.0, 5.0]},
        }
    )
    tp = _toolpath([_target({"pump_a": 0.5, "pump_b": 0.5})])
    drl = emit_drl(tp, setup, PROVENANCE)
    lines = [ln for ln in drl.splitlines() if ln.startswith("set_analog_output")]
    assert "ch=1" in lines[0]
    assert "ch=2" in lines[1]


# ---------------------------------------------------------------------------
# Grad-Konvertierung (ADR-006): Quaternion → ZYZ-Euler in Grad
# ---------------------------------------------------------------------------


def test_pose_in_degrees():
    """90°-Drehung um z (quat [cos45, 0,0, sin45]) → ZYZ-Euler mit 90.000 in posx."""
    import math

    s = math.sin(math.radians(45.0))
    c = math.cos(math.radians(45.0))
    tp = _toolpath([_target({"pump_a": 0.0}, quat=[c, 0.0, 0.0, s])])
    drl = emit_drl(tp, _setup(), PROVENANCE)
    move_line = next(ln for ln in drl.splitlines() if ln.startswith(("movel", "movej")))
    assert "90.000" in move_line


def test_pose_uses_wall_to_base_from_setup():
    """Die posx-Position entsteht aus wall_to_base ∘ frame (Setup als eine Stelle)."""
    setup = _setup()
    setup["wall_to_base"] = {"pos_mm": [1000.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}
    tp = _toolpath([_target({"pump_a": 0.0}, pos=[100.0, 0.0, 0.0])])
    drl = emit_drl(tp, setup, PROVENANCE)
    move_line = next(ln for ln in drl.splitlines() if ln.startswith(("movel", "movej")))
    # 1000 (base offset) + 100 (target) = 1100 in x
    assert "1100.000" in move_line


# ---------------------------------------------------------------------------
# Golden-File-Test
# ---------------------------------------------------------------------------


def test_golden_file():
    """Kleiner Referenz-Toolpath → exakt erwartete DRL-Ausgabe (Regression)."""
    tp = _toolpath(
        [
            _target({"pump_a": 0.0}, pos=[0.0, 0.0, 0.0], v=120.0, kind="travel", seg="approach"),
            _target({"pump_a": 0.5}, pos=[100.0, 0.0, 0.0], v=40.0, kind="print"),
            _target({"pump_a": 0.5}, pos=[100.0, 50.0, 0.0], v=40.0, kind="print"),
        ]
    )
    result = emit_drl(tp, _setup(), PROVENANCE)
    golden = (GOLDEN_DIR / "program.drl").read_text(encoding="utf-8")
    assert result == golden


# ---------------------------------------------------------------------------
# Action-Test: emit_drl_run liest toolpath.json und schreibt program.drl
# ---------------------------------------------------------------------------


def test_emit_drl_run_writes_file(tmp_path):
    run_dir = tmp_path / "20260704-run"
    run_dir.mkdir()

    tp = _toolpath([_target({"pump_a": 0.0}, kind="travel"), _target({"pump_a": 0.5})])
    (run_dir / "toolpath.json").write_text(json.dumps(tp), encoding="utf-8")

    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")

    result = emit_drl_run(run_dir, setup_path, "fgc emit-drl test")
    assert result.drl_path == run_dir / "program.drl"
    assert result.drl_path.exists()
    assert result.n_targets == 2
    drl = result.drl_path.read_text(encoding="utf-8")
    assert "movel" in drl and "movej" in drl


def test_emit_drl_run_missing_toolpath_fails(tmp_path):
    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Kein Toolpath"):
        emit_drl_run(run_dir, setup_path, "fgc emit-drl test")


def test_emit_drl_run_missing_setup_fails(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "toolpath.json").write_text(
        json.dumps(_toolpath_pump([0.5])), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="Setup nicht gefunden"):
        emit_drl_run(run_dir, tmp_path / "nosetup.json", "fgc emit-drl test")


def test_emit_drl_run_passes_motion(tmp_path):
    """emit_drl_run reicht MotionParams an den Emitter durch (vel/acc/Blending/ref)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "toolpath.json").write_text(
        json.dumps(_toolpath([_target({"pump_a": 0.5})])), encoding="utf-8"
    )
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    emit_drl_run(
        run_dir, setup_path, "src", motion=MotionParams(tcp_acc_mm_s2=333.0, blending_mm=5.0)
    )
    drl = (run_dir / "program.drl").read_text(encoding="utf-8")
    assert "acc=333.000" in drl and "radius=5.000" in drl


# ---------------------------------------------------------------------------
# CLI-Integration: fgc emit-drl schreibt program.drl
# ---------------------------------------------------------------------------


def test_cli_emit_drl_writes_program(tmp_path):
    run_dir = tmp_path / "20260704-run"
    run_dir.mkdir()

    tp = _toolpath(
        [_target({"pump_a": 0.0}, kind="travel"), *[_target({"pump_a": 0.3}) for _ in range(3)]]
    )
    (run_dir / "toolpath.json").write_text(json.dumps(tp), encoding="utf-8")

    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")

    rc = cli.main(["emit-drl", "--run", str(run_dir), "--setup", str(setup_path)])
    assert rc == 0
    drl_path = run_dir / "program.drl"
    assert drl_path.exists()
    content = drl_path.read_text(encoding="utf-8")
    assert "movel" in content
    assert "set_analog_output" in content


def test_cli_emit_drl_missing_run_fails(tmp_path, capsys):
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    rc = cli.main(["emit-drl", "--run", str(tmp_path / "nope"), "--setup", str(setup_path)])
    assert rc == 1


def test_cli_emit_drl_unknown_channel_fails(tmp_path, capsys):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tp = _toolpath([_target({"pump_a": 0.5, "unknown": 0.5})])
    (run_dir / "toolpath.json").write_text(json.dumps(tp), encoding="utf-8")
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(_setup()), encoding="utf-8")
    rc = cli.main(["emit-drl", "--run", str(run_dir), "--setup", str(setup_path)])
    assert rc == 1

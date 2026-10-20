"""Artefakte eines Laufordners lesen (spec/ARTEFAKTE.md, docs/muster/ARTEFAKT-FORMAT.md).

Laufordner: `<lauf>/parts/<part_id>/{part.json, part.stl, toolpath.json, trajectory.json}`; ein
einzelner Teilordner (mit toolpath.json direkt darin) wird ebenfalls angenommen. T_WP kommt aus
part.json; fehlt es dort, wird es in summary.json bzw. scene.json gesucht. Alles wird nach Frame P
umgerechnet: p_P = T_WP⁻¹ · p_W.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


class ArtifactError(Exception):
    """Pflichtartefakt fehlt oder ist unlesbar."""


@dataclass
class Ring:
    index: int
    layer: int
    shell: int
    kind: str
    closed: bool
    link_next: bool
    pts: np.ndarray  # (n, 3) in P


@dataclass
class Trajectory:
    tcp: np.ndarray  # (N, 3) in P
    ring: np.ndarray
    kind: list[str]


@dataclass
class Part:
    part_id: str
    dir: Path
    w: float
    h: float
    T_WP: np.ndarray
    mesh: trimesh.Trimesh
    rings: list[Ring]
    traj: Trajectory | None
    pattern: dict | None
    status: str | None


def load_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactError(f"{path.name} fehlt ({path})") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"{path.name} ist kein JSON: {exc}") from exc


def part_dirs(run: Path) -> list[Path]:
    run = Path(run)
    if (run / "toolpath.json").is_file():
        return [run]
    pdir = run / "parts"
    if not pdir.is_dir():
        raise ArtifactError(f"weder parts/ noch toolpath.json in {run}")
    return sorted(p for p in pdir.iterdir() if p.is_dir())


def _find_T_WP(pdir: Path, part_id: str) -> np.ndarray:
    pj = pdir / "part.json"
    if pj.is_file():
        d = load_json(pj)
        if d.get("T_WP") is not None:
            return np.asarray(d["T_WP"], float)
    for cand in (pdir.parent.parent / "summary.json", pdir.parent.parent / "scene.json",
                 pdir / "summary.json", pdir / "scene.json"):
        if not cand.is_file():
            continue
        d = load_json(cand)
        for p in d.get("parts", []) or []:
            if p.get("part_id") == part_id and p.get("T_WP") is not None:
                return np.asarray(p["T_WP"], float)
        if d.get("T_WP") is not None:
            return np.asarray(d["T_WP"], float)
    raise ArtifactError(f"T_WP fuer Teil {part_id} nicht gefunden (part.json)")


def to_P(T_WP: np.ndarray, pts_W: np.ndarray) -> np.ndarray:
    R, t = T_WP[:3, :3], T_WP[:3, 3]
    return (np.asarray(pts_W, float)[:, :3] - t) @ R


def load_part(pdir: Path, need_trajectory: bool = True) -> Part:
    pdir = Path(pdir)
    tp = load_json(pdir / "toolpath.json")
    part_id = str(tp.get("part_id") or pdir.name)
    try:
        w = float(tp["bead_width_mm"])
        h = float(tp["layer_height_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactError("toolpath.json: bead_width_mm/layer_height_mm fehlen") from exc
    T_WP = _find_T_WP(pdir, part_id)
    stl = pdir / "part.stl"
    if not stl.is_file():
        raise ArtifactError(f"part.stl fehlt ({stl})")
    mesh = trimesh.load_mesh(stl, force="mesh")
    rings = []
    for i, r in enumerate(tp.get("rings", [])):
        wp = np.asarray(r.get("waypoints", []), float).reshape(-1, 7)
        rings.append(Ring(i, int(r["layer"]), int(r.get("shell", 0)), str(r.get("kind", "outer")),
                          bool(r.get("closed", True)), bool(r.get("link_next", False)),
                          to_P(T_WP, wp[:, :3]) if len(wp) else np.zeros((0, 3))))
    traj = None
    tj = pdir / "trajectory.json"
    if tj.is_file():
        d = load_json(tj)
        tcp = np.asarray(d["tcp"], float).reshape(-1, 7)
        traj = Trajectory(to_P(T_WP, tcp[:, :3]), np.asarray(d["ring"], int), [str(k) for k in d["kind"]])
    elif need_trajectory:
        raise ArtifactError(f"trajectory.json fehlt ({tj})")
    status = None
    if (pdir / "part.json").is_file():
        status = load_json(pdir / "part.json").get("status")
    return Part(part_id, pdir, w, h, T_WP, mesh, rings, traj, tp.get("pattern"), status)

"""Kennzahlen und Schichtvorschau eines gerechneten Teils aus `toolpath.json` (Viewer, SPEC §9).

Reine Funktionen auf den Artefakten eines Laufs; kein Roboter, keine Planung. Die Wegpunkte des
Toolpaths liegen in W; die Vorschau rechnet sie über `part.json` (`T_WP`) in den Teil-Frame P
(Draufsicht, mm). Ein **Strang** ist eine Kette aufeinanderfolgender Ringe, die per `link_next`
verbunden sind (Pumpe an, kein Halt); in der Zählung „je Schicht“ trennt die Schichtgrenze die Kette.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

#: waagrechter Versatz, bis zu dem ein Schichtwechsel als reiner Z-Hub gilt (M4)
VERTICAL_TOL_MM = 0.5
KINDS = ("outer", "inner", "hole", "infill", "web", "outfill")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_part(run_dir: Path, part_id: str) -> tuple[dict[str, Any], dict[str, Any], float]:
    """(toolpath, part, v_print_mm_s) eines Teils; FileNotFoundError, wenn das Teil fehlt."""
    pdir = run_dir / "parts" / part_id
    toolpath = _read(pdir / "toolpath.json")
    part = _read(pdir / "part.json")
    v = 100.0
    try:
        v = float(_read(run_dir / "summary.json").get("params", {}).get("v_print_mm_s", v))
    except (OSError, ValueError, TypeError):
        pass
    return toolpath, part, v


def _xy(ring: dict[str, Any]) -> np.ndarray:
    return np.asarray([w[:2] for w in ring["waypoints"]], dtype=float)


def _length(pts: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if len(pts) > 1 else 0.0


def metrics(toolpath: dict[str, Any], v_print_mm_s: float = 100.0) -> dict[str, Any]:
    """Kennzahlen des Musters (Längen je Segmentart, Stränge, Schichtwechsel, Druckzeit, Material)."""
    rings: list[dict[str, Any]] = toolpath["rings"]
    lengths = [_length(_xy(r)) for r in rings]
    total = float(sum(lengths))
    by_kind: dict[str, list[float]] = defaultdict(list)
    for r, ln in zip(rings, lengths, strict=True):
        by_kind[r["kind"]].append(ln)
    kinds = [
        {
            "kind": k,
            "rings": len(by_kind[k]),
            "length_mm": round(sum(by_kind[k]), 3),
            "share": round(sum(by_kind[k]) / total, 6) if total > 0 else 0.0,
        }
        for k in KINDS
        if k in by_kind
    ]

    # Ring r gehört zur Kette von r - 1, wenn r - 1 `link_next` trägt
    n_strands = 0
    for i in range(len(rings)):
        if i == 0 or not rings[i - 1]["link_next"]:
            n_strands += 1

    layer_ids = sorted({r["layer"] for r in rings})
    first_of: dict[int, int] = {}
    last_of: dict[int, int] = {}
    for i, r in enumerate(rings):
        first_of.setdefault(r["layer"], i)
        last_of[r["layer"]] = i
    layers: list[dict[str, Any]] = []
    for layer in layer_ids:
        idx = range(first_of[layer], last_of[layer] + 1)
        strands = 1 + sum(1 for i in idx if i < last_of[layer] and not rings[i]["link_next"])
        layers.append(
            {
                "layer": int(layer),
                "rings": len(idx),
                "strands": strands,
                "length_mm": round(sum(lengths[i] for i in idx), 3),
            }
        )

    vertical = diagonal = travel = 0
    offsets: list[float] = []
    for a, b in zip(layer_ids, layer_ids[1:], strict=False):
        last, first = last_of[a], first_of[b]
        if not rings[last]["link_next"]:
            travel += 1
            continue
        off = float(np.linalg.norm(_xy(rings[last])[-1] - _xy(rings[first])[0]))
        offsets.append(off)
        if off <= VERTICAL_TOL_MM:
            vertical += 1
        else:
            diagonal += 1

    pat = toolpath.get("pattern")
    w = float(toolpath["bead_width_mm"])
    h = float(toolpath["layer_height_mm"])
    v = float(v_print_mm_s) if v_print_mm_s > 0 else 100.0
    return {
        "part_id": toolpath["part_id"],
        "has_pattern": pat is not None,
        "layer_order": pat["layer_order"] if pat else None,
        "infill": pat["infill"] if pat else None,
        "outfill": pat["outfill"] if pat else None,
        "n_layers": len(layer_ids),
        "bead_width_mm": w,
        "layer_height_mm": h,
        "v_print_mm_s": v,
        "total_length_mm": round(total, 3),
        "print_time_s": round(total / v, 3),
        "volume_l": round(total * w * h / 1e6, 4),
        "n_rings": len(rings),
        "n_open_rings": sum(1 for r in rings if not r["closed"]),
        "n_strands": n_strands,
        "max_strands_per_layer": max((x["strands"] for x in layers), default=0),
        "kinds": kinds,
        "layer_changes": {
            "vertical": vertical,
            "diagonal": diagonal,
            "travel": travel,
            "max_offset_mm": round(max(offsets), 3) if offsets else None,
        },
        "layers": layers,
    }


def _to_p(points_w: np.ndarray, T_WP: np.ndarray) -> np.ndarray:
    """Punkte (n, 3) von W nach P."""
    inv = np.linalg.inv(T_WP)
    homo = np.hstack([points_w, np.ones((len(points_w), 1))])
    return (homo @ inv.T)[:, :3]


def _layer_path(rings: list[dict[str, Any]], layer: int, T_WP: np.ndarray) -> tuple[dict[str, Any], float]:
    segs: list[dict[str, Any]] = []
    z = 0.0
    for i, r in enumerate(rings):
        if r["layer"] != layer:
            continue
        p = _to_p(np.asarray([w[:3] for w in r["waypoints"]], dtype=float), T_WP)
        z = float(p[:, 2].mean())
        segs.append(
            {
                "ring": i,
                "kind": r["kind"],
                "shell": int(r["shell"]),
                "closed": bool(r["closed"]),
                "link_next": bool(r["link_next"]),
                "points": [[round(float(x), 2), round(float(y), 2)] for x, y in p[:, :2]],
            }
        )
    length = sum(_length(np.asarray(s["points"], dtype=float)) for s in segs)
    return (
        {
            "layer": layer,
            "segments": segs,
            "start": segs[0]["points"][0] if segs else None,
            "end": segs[-1]["points"][-1] if segs else None,
            "length_mm": round(length, 3),
        },
        z,
    )


def layer_view(toolpath: dict[str, Any], part: dict[str, Any], layer: int) -> dict[str, Any]:
    """Schicht `layer` im Frame P samt Nachbarschicht; IndexError für eine Schicht ohne Ringe."""
    rings = toolpath["rings"]
    ids = sorted({r["layer"] for r in rings})
    if layer not in ids:
        raise IndexError(f"Schicht {layer} nicht vorhanden (0 bis {ids[-1] if ids else -1})")
    T = np.asarray(part["T_WP"], dtype=float)
    path, z = _layer_path(rings, layer, T)
    nb_layer = layer + 1 if layer + 1 in ids else (layer - 1 if layer - 1 in ids else None)
    nb = _layer_path(rings, nb_layer, T)[0] if nb_layer is not None else None
    segs = path["segments"] + (nb["segments"] if nb else [])
    pts = np.asarray([p for s in segs for p in s["points"]], dtype=float)
    lo, hi = (pts.min(axis=0), pts.max(axis=0)) if len(pts) else (np.zeros(2), np.zeros(2))
    return {
        "part_id": toolpath["part_id"],
        "layer": layer,
        "n_layers": len(ids),
        "z_mm": round(z, 3),
        "bead_width_mm": float(toolpath["bead_width_mm"]),
        "bounds": [
            [round(float(lo[0]), 2), round(float(lo[1]), 2)],
            [round(float(hi[0]), 2), round(float(hi[1]), 2)],
        ],
        "path": path,
        "neighbor": nb,
        "neighbor_relation": None if nb_layer is None else ("next" if nb_layer > layer else "previous"),
    }

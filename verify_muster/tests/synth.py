"""Synthetische Laufordner fuer die Selbsttests des Muster-Orakels.

Die Bahnen werden in Frame P (xy, mm) konstruiert, je Schicht auf z = (L+1)·h gehoben, mit einer
gedrehten und verschobenen T_WP nach W gerechnet und als toolpath.json geschrieben. Die Trajektorie
folgt ARTEFAKTE (Strang: transfer -> lower -> approach -> print -> link -> ... -> retract -> lift).
Geometrie (w = 30 mm, h = 10 mm, Quader 600 × 200 mm):
- Zwei Schalen: Aussenbahn y = ±85, Innenbahn y = ±55 als abgerundete Rechtecke; Uebergang aussen ->
  innen ueber eine Kosinus-S-Kurve (Laenge 90 mm), Innenbahn endet 10 mm vor der S-Kurve.
- Sinus: eine Bahn je Seite (Unterseite, Bogen r = 85 rechts, Oberseite), links Bogen r = 70 in den
  Hohlraum, dann y = -55·cos(2π(x + 215)/300) bis x = 150 (Kontakt an beiden Bahnen bei Abstand w).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import trimesh

W = 30.0
H = 10.0
STEP = 2.0
NOZZLE_DOWN = (0.0, 1.0, 0.0, 0.0)  # (w, x, y, z): 180° um X, Duesenachse -Z_W


def T_WP_default() -> np.ndarray:
    c, s = np.cos(np.radians(30.0)), np.sin(np.radians(30.0))
    T = np.eye(4)
    T[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    T[:3, 3] = [120.0, -350.0, 900.0]
    return T


# ---------------------------------------------------------------- Bahnstuecke


def line(p0, p1, step: float = STEP) -> np.ndarray:
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    n = max(1, int(np.ceil(np.linalg.norm(p1 - p0) / step)))
    return p0 + (np.arange(n + 1) / n)[:, None] * (p1 - p0)


def arc(c, r: float, a0: float, a1: float, step: float = STEP) -> np.ndarray:
    n = max(2, int(np.ceil(abs(a1 - a0) * r / step)))
    t = np.linspace(a0, a1, n + 1)
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])


def join(*pieces) -> np.ndarray:
    out = [np.asarray(pieces[0], float)]
    for p in pieces[1:]:
        p = np.asarray(p, float)
        if np.linalg.norm(out[-1][-1] - p[0]) < 1e-9:
            p = p[1:]
        out.append(p)
    return np.vstack(out)


def rrect_open(hx: float, hy: float, r: float, x_start: float, x_end: float, cx: float = 0.0) -> np.ndarray:
    """Abgerundetes Rechteck gegen den Uhrzeigersinn, Start auf der Unterkante bei x_start (Richtung +x),
    einmal herum bis zur Unterkante bei x_end < x_start (offen)."""
    pts = join(line((x_start, -hy), (cx + hx - r, -hy)),
               arc((cx + hx - r, -hy + r), r, -np.pi / 2, 0.0),
               line((cx + hx, -hy + r), (cx + hx, hy - r)),
               arc((cx + hx - r, hy - r), r, 0.0, np.pi / 2),
               line((cx + hx - r, hy), (cx - hx + r, hy)),
               arc((cx - hx + r, hy - r), r, np.pi / 2, np.pi),
               line((cx - hx, hy - r), (cx - hx, -hy + r)),
               arc((cx - hx + r, -hy + r), r, np.pi, 1.5 * np.pi),
               line((cx - hx + r, -hy), (x_end, -hy)))
    return pts


def s_curve(x0: float, x1: float, y0: float, y1: float, step: float = STEP) -> np.ndarray:
    x = np.linspace(x0, x1, max(2, int(np.ceil((x1 - x0) / step))) + 1)
    t = (x - x0) / (x1 - x0)
    return np.column_stack([x, y0 + (y1 - y0) * (1 - np.cos(np.pi * t)) / 2])


# ---------------------------------------------------------------- Muster (eine Schicht, Vorwaertsrichtung)


def two_shells(r_out: float = 60.0, half_len: float = 300.0, cx: float = 0.0, x0: float = -100.0,
               lc: float = 90.0) -> list[dict]:
    """Zwei Schalen je Seite als ein Strang: Aussenbahn (offen) -> S-Kurve -> Innenbahn (offen)."""
    hx_o, hy_o = half_len - W / 2, 100.0 - W / 2
    x0 = cx + x0
    outer = join(rrect_open(hx_o, hy_o, r_out, x0, x0 - lc, cx), s_curve(x0 - lc, x0, -hy_o, -hy_o + W))
    inner = rrect_open(hx_o - W, hy_o - W, r_out - W, x0, x0 - lc - 10.0, cx)
    return [{"kind": "outer", "shell": 0, "xy": outer}, {"kind": "inner", "shell": 1, "xy": inner}]


def plateau(x: np.ndarray, x0: float, b: float, flat: float = 20.0, ramp: float = 30.0) -> np.ndarray:
    """Versatz b auf |x - x0| <= flat, Kosinusrampe der Laenge ramp auf 0 (Kruemmung klein)."""
    u = np.clip((np.abs(x - x0) - flat) / ramp, 0.0, 1.0)
    return b * 0.5 * (1.0 + np.cos(np.pi * u))


def sine_infill(extra_tail=None, bump: float = 0.0, outer_shift: float = 0.0) -> list[dict]:
    """Eine Bahn je Seite und Sinus-Infill (Wellenlaenge 300 mm, Kontakt bei Abstand w).

    bump: Gauss-Beule im Infill bei x = -140 (Sinus dort ~49° steil, der Versatz normal zur Bahn ist
    nur ≈ 0,65·bump). outer_shift: ebenes Plateau der unteren Aussenbahn bei x = -65 nach innen (+y),
    der Versatz normal zur Bahn ist dort genau outer_shift (exakter Grenzfall fuer M3)."""
    xb = np.arange(-285.0, 200.0 + 1e-9, 1.0)
    bottom = np.column_stack([xb, -85.0 + plateau(xb, -65.0, outer_shift)]) if outer_shift else \
        line((-285, -85), (200, -85))
    outer = join(bottom, arc((200, 0), 85, -np.pi / 2, np.pi / 2), line((200, 85), (-215, 85)))
    x = np.arange(-215.0, 150.0 + 1e-9, 1.0)
    y = -55.0 * np.cos(2 * np.pi * (x + 215.0) / 300.0)
    if bump:
        y = y + bump * np.exp(-((x + 140.0) / 25.0) ** 2)
    infill = join(arc((-215, 15), 70, np.pi / 2, 1.5 * np.pi), np.column_stack([x, y]))
    if extra_tail is not None:
        infill = join(infill, extra_tail(infill[-1]))
    return [{"kind": "outer", "shell": 0, "xy": outer}, {"kind": "infill", "shell": 1, "xy": infill}]


def stadium(r: float, half: float = 150.0, arc_step: float = 0.5) -> list[dict]:
    """Geschlossener Ring (Stadion): Geraden y = ±r von x = -half bis half, Halbkreise vom Radius r
    (Sehnenlaenge <= arc_step, Ecken auf dem Kreis). Start = Ende auf der Unterkante bei x = 0
    (closed = true wie im heutigen Format)."""
    pts = join(line((0.0, -r), (half, -r)), arc((half, 0.0), r, -np.pi / 2, np.pi / 2, step=arc_step),
               line((half, r), (-half, r)), arc((-half, 0.0), r, np.pi / 2, 1.5 * np.pi, step=arc_step),
               line((-half, -r), (0.0, -r)))
    return [{"kind": "outer", "shell": 0, "xy": pts, "closed": True}]


def mitre_rings() -> list[dict]:
    """Heutiges Format (ohne Muster): zwei geschlossene Rechteckringe mit spitzen Ecken (Mitre), Start
    an der Ecke nahe (x_min, y_min), Aussenring -> Verbinder -> Innenring."""
    def rect(hx, hy):
        return np.array([[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy], [-hx, -hy]], float)

    return [{"kind": "outer", "shell": 0, "xy": rect(285.0, 85.0), "closed": True},
            {"kind": "inner", "shell": 1, "xy": rect(255.0, 55.0), "closed": True}]


# ---------------------------------------------------------------- Schichten und Dateien


def stack(layer_fn: Callable[[int], list[list[dict]]], n_layers: int, alternate: bool = True) -> list[dict]:
    """Ringe aller Schichten in Druckreihenfolge. layer_fn(L) -> Liste der Inseln, je Insel eine Ringliste
    in Vorwaertsrichtung. Bei alternate wird in ungeraden Schichten jede Insel umgekehrt (Ringe und
    Wegpunkte) und die Inselreihenfolge gedreht. link_next: innerhalb einer Insel immer, am Schichtende
    zum ersten Ring der naechsten Schicht."""
    rings: list[dict] = []
    for L in range(n_layers):
        isl = layer_fn(L)
        if alternate and L % 2 == 1:
            isl = [[dict(r, xy=r["xy"][::-1]) for r in reversed(rs)] for rs in reversed(isl)]
        for k, rs in enumerate(isl):
            for j, r in enumerate(rs):
                last_in_island = j == len(rs) - 1
                last_in_layer = last_in_island and k == len(isl) - 1
                rings.append({"layer": L, "shell": r["shell"], "kind": r["kind"],
                              "closed": bool(r.get("closed", False)), "xy": np.asarray(r["xy"], float),
                              "link_next": (not last_in_island) or (last_in_layer and L < n_layers - 1)})
    return rings


def _to_W(T: np.ndarray, xy: np.ndarray, z: float) -> np.ndarray:
    p = np.column_stack([xy, np.full(len(xy), z)])
    return p @ T[:3, :3].T + T[:3, 3]


def box_mesh(length: float = 600.0, width: float = 200.0, height: float = 40.0, cx: float = 0.0):
    m = trimesh.creation.box(extents=(length, width, height))
    m.apply_translation((cx, 0.0, height / 2))
    return m


def pillars_mesh(height: float = 40.0) -> trimesh.Trimesh:
    """Zwei Pfeiler 250 × 200 mm mit 100 mm Oeffnung dazwischen (x ∈ [-50, 50])."""
    return trimesh.util.concatenate([box_mesh(250, 200, height, -175.0), box_mesh(250, 200, height, 175.0)])


def write_run(root: Path, rings: list[dict], mesh: trimesh.Trimesh, breaks: set[int] | None = None,
              T: np.ndarray | None = None, part_id: str = "box_m0", traj_mutator=None) -> Path:
    """Schreibt <root>/parts/<part_id>/{part.json, part.stl, toolpath.json, trajectory.json}.
    breaks: Ringindizes r, nach denen der Planer trotz link_next einen Travel setzt."""
    T = T_WP_default() if T is None else T
    breaks = breaks or set()
    pdir = Path(root) / "parts" / part_id
    pdir.mkdir(parents=True, exist_ok=True)
    mesh.export(pdir / "part.stl")
    tp_rings = []
    for r in rings:
        pw = _to_W(T, r["xy"], (r["layer"] + 1) * H)
        wps = [[*p.tolist(), *NOZZLE_DOWN] for p in pw]
        tp_rings.append({"layer": r["layer"], "shell": r["shell"], "kind": r["kind"], "closed": r["closed"],
                         "link_next": bool(r["link_next"]), "waypoints": wps})
    (pdir / "toolpath.json").write_text(json.dumps({"schema_version": "2", "part_id": part_id,
                                                     "layer_height_mm": H, "bead_width_mm": W,
                                                     "rings": tp_rings}))
    (pdir / "part.json").write_text(json.dumps({"schema_version": "2", "part_id": part_id, "wall_id": "box",
                                                 "T_WP": T.tolist(), "status": "machbar"}))
    traj = trajectory(rings, breaks)
    if traj_mutator is not None:
        traj = traj_mutator(traj)
    tcpW = np.array([s[0] for s in traj]) @ T[:3, :3].T + T[:3, 3]
    n = len(traj)
    out = {"schema_version": "2", "part_id": part_id, "t_s": [0.1 * i for i in range(n)],
           "q": [[0.0] * 6] * n, "tcp": [[*p.tolist(), *NOZZLE_DOWN] for p in tcpW],
           "layer": [s[3] for s in traj], "ring": [s[2] for s in traj], "kind": [s[1] for s in traj],
           "branch": [0] * n, "status": ["ok"] * n, "d_mm": [100.0] * n, "pair": [None] * n,
           "witness": [None] * n, "psi_rad": [0.0] * n}
    (pdir / "trajectory.json").write_text(json.dumps(out))
    return Path(root)


def trajectory(rings: list[dict], breaks: set[int]) -> list[tuple]:
    """Samples (Punkt P xyz, Art, Ring, k) nach ARTEFAKTE."""
    S: list[tuple] = []
    up = 50.0

    def add(pts, kind, ring, k):
        for p in pts:
            S.append((np.asarray(p, float), kind, ring, k))

    def p3(xy, L, dz=0.0):
        return np.array([xy[0], xy[1], (L + 1) * H + dz])

    in_strand = False
    for i, r in enumerate(rings):
        L = r["layer"]
        start = r["xy"][0]
        if not in_strand:
            k_tr = 0 if i == 0 else rings[i - 1]["layer"] + 1
            add([p3(start, L, 200.0), p3(start, L, up)], "transfer", i, k_tr)
            add([p3(start, L, up), p3(start, L, 10.0)], "lower", i, k_tr)
            add([p3(start, L, 10.0), p3(start, L, 0.0)], "approach", i, L)
        add([p3(q, L) for q in line_dense(r["xy"])], "print", i, L)
        nxt = rings[i + 1] if i + 1 < len(rings) else None
        if nxt is not None and r["link_next"] and i not in breaks:
            a, b = p3(r["xy"][-1], L), p3(nxt["xy"][0], nxt["layer"])
            add([a + t * (b - a) for t in np.linspace(0, 1, 4)], "link", i + 1, nxt["layer"])
            in_strand = True
        else:
            end = r["xy"][-1]
            add([p3(end, L, 0.0), p3(end, L, 10.0)], "retract", i, L)
            add([p3(end, L, 10.0), p3(end, L, up)], "lift", i, L + 1)
            in_strand = False
    return S


def line_dense(xy: np.ndarray, step: float = 5.0) -> np.ndarray:
    out = [xy[:1]]
    for a, b in zip(xy[:-1], xy[1:], strict=True):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + (np.arange(1, n + 1) / n)[:, None] * (b - a))
    return np.vstack(out)

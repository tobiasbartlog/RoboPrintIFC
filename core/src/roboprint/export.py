"""Teil-Artefakte und DRL-Programme in den Laufordner schreiben (SPEC §6, spec/ARTEFAKTE.md).

Gleiche Teile werden einmal serialisiert: Teile mit gleicher Geometrie **und** gleicher
Platzierung (also demselben Plan aus dem Geometrie-Cache der Zerlegung, SPEC §5.4/5) haben eine
identische Welt, damit identische Toolpaths, Trajektorien, Pruefergebnisse und Programme. Der
Repraesentant einer solchen Gruppe (das erste Teil in Laufreihenfolge) wird voll aufbereitet und
dicht geprueft (Trajektorie, Selbstpruefung, DRL); seine Pruefung gilt fuer alle Kopien. Die
Kopien bekommen dieselben Bytes, in denen nur `part_id` (toolpath.json, trajectory.json) bzw. die
Kopfzeile des Programms ersetzt ist. part.stl ist eine Byte-Kopie des Repraesentanten; part.json
stammt aus dem Repraesentanten, nur `part_id`, `wall_id` und `T_LP` (eigene Lage in der Wand) sind
teilspezifisch. Damit das stimmt, bildet `group_parts` nur Gruppen, deren Mesh in P (sortierte
Eckpunkte, Flaechenzahl) um hoechstens `COPY_TOL_MM` = 0,01 mm und deren Volumen um hoechstens
1e-4 relativ vom Repraesentanten abweicht; sonst ist das Teil ein eigener
Repraesentant. Die Wandpruefung (Volumen +-0,5 %, Ueberlappung ueber T_LP) liest weiter je Teil
sein eigenes T_LP; 0,01 mm Eckpunktabweichung liegt weit unter ihren Toleranzen. In
`summary.parts[].same_as` steht fuer jede Kopie die part_id des Repraesentanten (sonst null).

Mit `jobs > 1` laufen die Gruppen parallel in Prozessen (fork; die Plaene werden geerbt, nicht
gepickelt).
"""

from __future__ import annotations

import json
import multiprocessing as mp
import shutil
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from roboprint import frames, selfcheck
from roboprint.contracts import (
    BBox,
    Cause,
    PartArtifact,
    PartEntry,
    Placement,
    Provenance,
    Scene,
    Toolpath,
    Trajectory,
    TrajectorySummary,
    dump_json,
)
from roboprint.planner import PartPlan, PlannerParams
from roboprint.planner.kin import Kin, psi_of, rot_down
from roboprint.slicer import to_toolpath
from roboprint.timing import TimingParams, time_parametrize

GroupProgress = Callable[[int, int], None]


@dataclass
class ExportContext:
    """Alles, was die Gruppen-Ausgabe braucht (wird an fork-Kinder vererbt)."""

    out: Path
    part_jobs: list[Any]  # pipeline.PartJob
    plans: list[PartPlan]
    kin: Kin
    params: PlannerParams
    scn: Any
    scene: Scene
    provenance: Provenance
    run_params: dict[str, Any]


_CTX: ExportContext | None = None


# --------------------------------------------------------------------------- Gruppen


def _mesh_key(mesh: Any) -> str:
    from roboprint.decompose import _mesh_key as key

    return key(mesh)


def _round(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, tuple | list):
        return tuple(round(float(x), 3) for x in v)
    return round(float(v), 1)


COPY_TOL_MM = 0.01


def _same_geometry(a: Any, b: Any) -> bool:
    """Mesh in P gleich bis COPY_TOL_MM (Eckpunkte in kanonischer Reihenfolge) und gleiches Volumen."""
    va, vb = np.asarray(a.vertices, float), np.asarray(b.vertices, float)
    if va.shape != vb.shape or len(a.faces) != len(b.faces):
        return False
    va = va[np.lexsort(np.round(va, 2).T[::-1])]
    vb = vb[np.lexsort(np.round(vb, 2).T[::-1])]
    if float(np.abs(va - vb).max(initial=0.0)) > COPY_TOL_MM:
        return False
    return abs(float(a.volume) - float(b.volume)) <= 1e-4 * max(abs(float(a.volume)), 1.0)


def group_parts(part_jobs: list[Any], plans: list[PartPlan]) -> list[list[int]]:
    """Gruppen gleicher Teile (Indizes, erstes = Repraesentant): derselbe Plan (gleiche
    Geometrie aus dem Cache, gleiche Platzierung), gleiches Mesh und gleiche Sollmasse der
    Selbstpruefung. Teile ohne gemeinsamen Plan bilden je eine eigene Gruppe."""
    groups: dict[Any, list[int]] = {}
    for i, (job, pp) in enumerate(zip(part_jobs, plans, strict=True)):
        pl = pp.placement
        key = (
            id(pp.path),
            id(pp.sliced),
            round(pl.x_mm, 6),
            round(pl.y_mm, 6),
            round(pl.yaw_rad, 9),
            _mesh_key(job.mesh_P),
            _round(getattr(job, "expected_size_mm", None)),
            _round(getattr(job, "expected_volume_mm3", None)),
        )
        groups.setdefault(key, []).append(i)
    out: list[list[int]] = []
    for g in groups.values():
        reps: list[list[int]] = []
        for i in g:
            for r in reps:
                if _same_geometry(part_jobs[r[0]].mesh_P, part_jobs[i].mesh_P):
                    r.append(i)
                    break
            else:
                reps.append([i])
        out.extend(reps)
    return sorted(out, key=lambda g: g[0])


# --------------------------------------------------------------------------- Bytes


def to_json_bytes(model: Any) -> bytes:
    """Kompaktes JSON (wie `dump_json` ohne Einrueckung, gleicher Inhalt), serialisiert in
    pydantic-core statt ueber `json.dumps`, mit Zeilenende."""
    return model.model_dump_json().encode("utf-8") + b"\n"


def retag_part_id(data: bytes, old: str, new: str) -> bytes:
    """Ersetzt das Feld `part_id` (steht direkt nach `schema_version` am Dateianfang)."""
    a = b'"part_id":' + json.dumps(old, ensure_ascii=False).encode("utf-8")
    b = b'"part_id":' + json.dumps(new, ensure_ascii=False).encode("utf-8")
    i = data.find(a, 0, 256 + len(a))
    if i < 0:
        raise ValueError(f"part_id {old!r} nicht am Dateianfang gefunden")
    return data[:i] + b + data[i + len(a) :]


def retag_program(text: str, old: tuple[str, str], new: tuple[str, str]) -> str:
    """Ersetzt part_id und wall_id im Kommentarkopf eines Programms (nur dort stehen sie)."""
    lines = text.split("\n")
    n = 0
    while n < len(lines) and lines[n].startswith("#"):
        n += 1
    head = "\n".join(lines[:n])
    for o, w in zip(old, new, strict=True):
        if o != w:
            head = head.replace(o, w)
    return "\n".join([head, *lines[n:]]) if n < len(lines) else head


# --------------------------------------------------------------------------- Artefakte


def trajectory(pp: PartPlan, kin: Kin, params: PlannerParams) -> Trajectory:
    path = pp.path
    n = len(path.q)
    T = kin.tcp_W(path.q)  # noqa: N806
    ok = path.reachable
    pos = np.where(ok[:, None], T[:, :3, 3], path.p_W)
    R = np.where(ok[:, None, None], T[:, :3, :3], rot_down(path.psi))  # noqa: N806
    quat = np.array([frames.matrix_to_quat(r) for r in R])
    psi = np.where(ok, psi_of(T[:, :3, :3]), path.psi)
    t_s = time_parametrize(
        path.q,
        pos,
        path.kind,
        path.ring,
        TimingParams(
            v_print_mm_s=params.v_print_mm_s,
            v_travel_mm_s=params.v_travel_mm_s,
            joint_speed_fraction=params.joint_speed_fraction,
            t_tot_s=params.t_tot_s,
        ),
    )
    d_mm, pair, wit = [], [], []
    for c, o in zip(path.contacts, ok, strict=True):
        if not o or c is None:
            d_mm.append(None)
            pair.append(None)
            wit.append(None)
        else:
            d_mm.append(float(c.d_mm))
            pair.append([str(c.pair[0]), str(c.pair[1])])
            wit.append([[float(v) for v in c.witness_W[0]], [float(v) for v in c.witness_W[1]]])
    status = path.status
    cnt = {k: status.count(k) for k in ("ok", "warn", "collision", "unreachable")}
    return Trajectory(
        part_id=pp.part_id,
        t_s=t_s.tolist() if isinstance(t_s, np.ndarray) else [float(v) for v in t_s],
        q=path.q.tolist(),
        tcp=np.hstack([pos, quat]).tolist(),
        layer=[int(v) for v in path.layer],
        ring=[int(v) for v in path.ring],
        kind=list(path.kind),
        branch=[int(v) for v in path.branch],
        status=list(status),
        d_mm=d_mm,
        pair=pair,
        witness=wit,
        psi_rad=psi.tolist(),
        summary=TrajectorySummary(
            n=n,
            n_ok=cnt["ok"],
            n_warn=cnt["warn"],
            n_collision=cnt["collision"],
            n_unreachable=cnt["unreachable"],
            d_min_mm=path.d_min_mm,
            dauer_s=float(t_s[-1]) if n else 0.0,
            zweig_wechsel_in_ringen=path.branch_switches_in_rings,
        ),
    )


def _part_artifact(job: Any, pp: PartPlan, status: str, cause: Cause | None) -> PartArtifact:
    lo, hi = np.asarray(job.mesh_P.bounds, float)
    pl = pp.placement
    return PartArtifact(
        part_id=job.part_id,
        wall_id=job.wall_id,
        T_LP=np.asarray(job.T_LP).tolist(),
        T_SP=frames.T_SP(pl).tolist(),
        T_WP=pp.T_WP.tolist(),
        placement=Placement(x_mm=pl.x_mm, y_mm=pl.y_mm, yaw_deg=float(np.degrees(pl.yaw_rad))),
        bbox_P=BBox(min=lo.tolist(), max=hi.tolist()),
        volume_mm3=float(job.mesh_P.volume),
        n_layers=int(pp.sliced.n_layers),
        status=status,
        cause=cause,
    )


def _programs(ctx: ExportContext, tr: Trajectory, tp: Toolpath, part: PartArtifact) -> dict[str, str]:
    """DRL-Texte je Dialekt (wie `drl.write_programs`, aber aus den Modellen im Speicher)."""
    from roboprint import drl

    try:
        pp = drl.PlannedPart(
            trajectory=tr,
            toolpath=tp,
            part=part,
            scene=ctx.scene,
            params=drl.DrlParams.from_params(ctx.run_params),
            provenance=ctx.provenance,
            scenario_id=ctx.scn.id,
            run_params=ctx.run_params,
        )
        feasible = part.status == "machbar"
        steps, T_BT = drl._checked_steps(pp, allow_infeasible=not feasible)  # noqa: N806, SLF001
        return {d: drl._render(pp, d, steps, T_BT) for d in drl.DIALECTS}  # noqa: SLF001
    except ValueError as exc:
        return {d: f"# Kein Programm: Teil nicht machbar ({exc}).\n" for d in ("v2", "v3")}


def _write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("ascii", errors="replace"))


def export_group(idx: list[int], ctx: ExportContext | None = None) -> list[PartEntry]:
    """Schreibt eine Gruppe gleicher Teile; liefert die summary-Eintraege in Gruppenreihenfolge."""
    ctx = ctx or _CTX
    assert ctx is not None
    rep_job, pp = ctx.part_jobs[idx[0]], ctx.plans[idx[0]]
    tp = to_toolpath(pp.sliced, pp.T_WP, rep_job.part_id)
    tr = trajectory(pp, ctx.kin, ctx.params)
    selfcheck.apply(pp, rep_job, tr, tp, ctx.params, ctx.scn)
    path = pp.path
    status = "machbar" if path.feasible else "nicht machbar"
    cause = None
    if path.cause is not None:
        c = path.cause
        cause = Cause(
            sample=int(c["sample"]),
            t_s=float(tr.t_s[c["sample"]]),
            link=str(c["link"]),
            obstacle=str(c["obstacle"]),
            message=str(c["message"]),
        )
    tp_b, tr_b = to_json_bytes(tp), to_json_bytes(tr)
    rep_part = _part_artifact(rep_job, pp, status, cause)
    progs = _programs(ctx, tr, tp, rep_part)
    entries = []
    for k, i in enumerate(idx):
        job = ctx.part_jobs[i]
        pdir = ctx.out / "parts" / job.part_id
        pdir.mkdir(parents=True, exist_ok=True)
        same = k > 0
        if same:
            shutil.copyfile(ctx.out / "parts" / rep_job.part_id / "part.stl", pdir / "part.stl")
        else:
            job.mesh_P.export(pdir / "part.stl")
        rid = rep_job.part_id
        (pdir / "toolpath.json").write_bytes(retag_part_id(tp_b, rid, job.part_id) if same else tp_b)
        (pdir / "trajectory.json").write_bytes(retag_part_id(tr_b, rid, job.part_id) if same else tr_b)
        part = (
            rep_part.model_copy(
                update={"part_id": job.part_id, "wall_id": job.wall_id, "T_LP": np.asarray(job.T_LP).tolist()}
            )
            if same
            else rep_part
        )
        dump_json(part, pdir / "part.json")
        for d, text in progs.items():
            if same:
                text = retag_program(text, (rid, rep_job.wall_id), (job.part_id, job.wall_id))
            _write_text(pdir / f"program.{d}.drl", text)
        entries.append(
            PartEntry(
                part_id=job.part_id,
                wall_id=job.wall_id,
                status=status,
                d_min_mm=path.d_min_mm,
                n_collision=tr.summary.n_collision,
                n_unreachable=tr.summary.n_unreachable,
                same_as=rid if same else None,
            )
        )
    return entries


def _export_worker(idx: list[int]) -> list[PartEntry]:
    return export_group(idx)


def export_parts(ctx: ExportContext, jobs: int = 1, progress: GroupProgress | None = None) -> list[PartEntry]:
    """Schreibt alle Teile (Gruppen gleicher Teile einmal aufbereitet); `jobs > 1`: Gruppen
    parallel (fork). Liefert die summary-Eintraege in der Reihenfolge von `ctx.part_jobs`."""
    global _CTX
    groups = group_parts(ctx.part_jobs, ctx.plans)
    report = progress or (lambda done, total: None)
    res: dict[int, PartEntry] = {}
    workers = min(max(jobs, 1), len(groups))
    if workers > 1 and "fork" in mp.get_all_start_methods() and not mp.current_process().daemon:
        _CTX = ctx
        try:
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
                futs = [ex.submit(_export_worker, g) for g in groups]
                for n, (g, f) in enumerate(zip(groups, futs, strict=True)):
                    res.update(zip(g, f.result(), strict=True))
                    report(n + 1, len(groups))
        finally:
            _CTX = None
    else:
        for n, g in enumerate(groups):
            res.update(zip(g, export_group(g, ctx), strict=True))
            report(n + 1, len(groups))
    return [res[i] for i in range(len(ctx.part_jobs))]

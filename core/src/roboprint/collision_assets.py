"""Kollisionsgeometrie fuer `roboprint.collision`: Konvexzerlegung mit Aufmass und Cache.

Jeder Koerper ist eine Menge konvexer Teile. Jedes Teil traegt ein Aufmass `margin` (mm):
Die Kollisionsgeometrie ist die Minkowski-Summe aus Teil und Kugel(margin). Das Aufmass wird so
bestimmt, dass jeder Punkt des Roh-Meshes (Ecken, Flaechenmitten, dichte Oberflaechenproben) in
mindestens einem aufgeblasenen Teil liegt, plus `SAFETY_MM`. Die Naeherung ist damit
konservativ: Abstaende werden hoechstens unterschaetzt.

Zerlegung je Zusammenhangskomponente:
1. konvexe Huelle, wenn sie formtreu ist (Ueberdeckung <= `tol`),
2. sonst VHACD (vhacdx), wenn die Teile formtreu sind und das Volumen fuellen,
3. sonst hierarchische Huellen-Bisektion entlang der Hauptachsen, bis jede Huelle formtreu ist.

Stufe 3 ist noetig, weil VHACD auf den M1013-Kollisionsmeshes nur Schalen liefert (fuer `link_1`
z. B. 1,1e6 von 4,6e6 mm^3); eine Schale meldet tiefe Durchdringungen nicht.

Ergebnisse liegen unter `~/.cache/roboprint/collision` (oder `$ROBOPRINT_CACHE/collision`) mit
einem Hash aus Quellmesh, Parametern und `CACHE_VERSION`.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

CACHE_VERSION = "4"
SAFETY_MM = 0.5
#: Zulaessige Ueberdeckung einer Huelle ueber die Rohoberflaeche hinaus (mm).
TOL_MM = 5.0
#: VHACD-Parameter (deterministisch: asyncACD=False).
VHACD_PARAMS: dict = {
    "maxConvexHulls": 16,
    "resolution": 200_000,
    "minimumVolumePercentErrorAllowed": 1.0,
    "maxRecursionDepth": 10,
    "shrinkWrap": True,
    "fillMode": "flood",
    "maxNumVerticesPerCH": 48,
    "asyncACD": False,
    "minEdgeLength": 2,
    "findBestPlane": False,
}
_SPACING_MM = 2.0
_MAX_DEPTH = 7
_SPLIT_QUANTILES = (0.15, 0.3, 0.5, 0.7, 0.85)
_MAX_HULL_VERTICES = 128


@dataclass
class ConvexPart:
    """Konvexes Teil im Koerperframe (mm) mit Aufmass."""

    vertices: np.ndarray  # (n,3)
    faces: np.ndarray  # (m,3) int
    margin: float = 0.0

    @property
    def center(self) -> np.ndarray:
        return 0.5 * (self.vertices.min(axis=0) + self.vertices.max(axis=0))

    @property
    def radius(self) -> float:
        """Huellkugelradius um `center`, inklusive Aufmass."""
        return float(np.linalg.norm(self.vertices - self.center, axis=1).max() + self.margin)

    def trimesh(self) -> trimesh.Trimesh:
        return trimesh.Trimesh(self.vertices, self.faces, process=False)


# --------------------------------------------------------------------------- Cache


def cache_dir() -> Path:
    base = os.environ.get("ROBOPRINT_CACHE")
    d = (Path(base) if base else Path.home() / ".cache" / "roboprint") / "collision"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mesh_hash(*arrays: np.ndarray, extra: str = "") -> str:
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode())
    h.update(extra.encode())
    for a in arrays:
        a = np.ascontiguousarray(a)
        h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()[:24]


def save_parts(path: Path, parts: list[ConvexPart]) -> None:
    payload: dict[str, np.ndarray] = {"n": np.array(len(parts))}
    for i, p in enumerate(parts):
        payload[f"v{i}"] = p.vertices
        payload[f"f{i}"] = p.faces
        payload[f"m{i}"] = np.array(p.margin)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp.npz")
    np.savez_compressed(tmp, **payload)
    tmp.replace(path)


def load_parts(path: Path) -> list[ConvexPart]:
    with np.load(path) as z:
        n = int(z["n"])
        return [
            ConvexPart(z[f"v{i}"].astype(float), z[f"f{i}"].astype(np.int64), float(z[f"m{i}"]))
            for i in range(n)
        ]


def cached(tag: str, key: str, build: Callable[[], list[ConvexPart]]) -> list[ConvexPart]:
    path = cache_dir() / f"{tag}-{key}.npz"
    if path.exists():
        try:
            return load_parts(path)
        except Exception:  # noqa: BLE001 - kaputter Cache: neu erzeugen
            path.unlink(missing_ok=True)
    parts = build()
    save_parts(path, parts)
    return parts


# --------------------------------------------------------------------------- Grundbausteine


def hull_part(points: np.ndarray) -> ConvexPart:
    """Konvexe Huelle; bei mehr als `_MAX_HULL_VERTICES` Ecken auf eine Teilmenge ausgeduennt.

    Die ausgeduennte Huelle liegt innerhalb der vollen; das Aufmass (`assign_margins`) deckt den
    Rest ab. Weniger Ecken machen GJK schneller.
    """
    pts = np.asarray(points, dtype=float)
    try:
        h = trimesh.convex.convex_hull(pts)
        if len(h.vertices) < 4 or h.volume <= 1e-9:
            raise ValueError("flach")
    except Exception:  # noqa: BLE001 - flache Punktmenge: um 0,05 mm verdicken
        c = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        off = 0.05 * vt[-1]
        h = trimesh.convex.convex_hull(np.vstack([pts + off, pts - off]))
    v = np.asarray(h.vertices, float)
    if len(v) > _MAX_HULL_VERTICES:
        h = trimesh.convex.convex_hull(v[_farthest_points(v, _MAX_HULL_VERTICES)])
        v = np.asarray(h.vertices, float)
    return ConvexPart(v, np.asarray(h.faces, np.int64), 0.0)


def _farthest_points(v: np.ndarray, k: int) -> np.ndarray:
    """Deterministische Farthest-Point-Auswahl von k Indizes."""
    c = v.mean(axis=0)
    idx = [int(np.argmax(np.linalg.norm(v - c, axis=1)))]
    d = np.linalg.norm(v - v[idx[0]], axis=1)
    for _ in range(k - 1):
        i = int(np.argmax(d))
        idx.append(i)
        d = np.minimum(d, np.linalg.norm(v - v[i], axis=1))
    return np.array(idx)


def surface_samples(mesh: trimesh.Trimesh, spacing_mm: float = _SPACING_MM) -> tuple[np.ndarray, np.ndarray]:
    """Ecken, Flaechenmitten und gleichmaessige Proben samt Normalen (deterministisch)."""
    pts = [np.asarray(mesh.vertices, float), np.asarray(mesh.triangles_center, float)]
    nrm = [np.asarray(mesh.vertex_normals, float), np.asarray(mesh.face_normals, float)]
    area = float(mesh.area)
    if area > 0:
        count = int(min(600_000, max(500, area / spacing_mm**2)))
        samp, fi = trimesh.sample.sample_surface(mesh, count, seed=0)
        pts.append(np.asarray(samp, float))
        nrm.append(np.asarray(mesh.face_normals[fi], float))
    return np.vstack(pts), np.vstack(nrm)


def surface_points(mesh: trimesh.Trimesh, spacing_mm: float = _SPACING_MM) -> np.ndarray:
    return surface_samples(mesh, spacing_mm)[0]


class SurfaceRef:
    """Rohgeometrie fuer die Formtreue-Pruefung: Abstand zur Oberflaeche und Innen-Test.

    Abstand ueber die naechste Oberflaechenprobe aller Komponenten. Innen heisst innerhalb einer
    geschlossenen Komponente; getestet ueber die Normale ihrer naechsten Probe. Der Test laeuft
    nur fuer Punkte > tol von der Oberflaeche und betrifft nur die Treue, nie die Abdeckung.
    """

    def __init__(self, pts: np.ndarray, solids: list[tuple[np.ndarray, np.ndarray]]) -> None:
        self.pts = pts
        self.kd = cKDTree(pts)
        self.solids = [(cKDTree(sp), sp, sn) for sp, sn in solids if len(sp) >= 4]

    def overcover(self, x: np.ndarray, tol: float) -> float:
        """Groesster Oberflaechenabstand der Punkte x ausserhalb des Solids (exakt ueber `tol`)."""
        d, _ = self.kd.query(x)
        cand = d > tol
        if not cand.any():
            return float(d.max()) if len(d) else 0.0
        xc, dc = x[cand], d[cand]
        inside = np.zeros(len(xc), dtype=bool)
        for kd, sp, sn in self.solids:
            lo, hi = sp.min(axis=0), sp.max(axis=0)
            sel = ~inside & np.all((xc >= lo) & (xc <= hi), axis=1)
            if sel.any():
                _, i = kd.query(xc[sel])
                side = np.einsum("ij,ij->i", xc[sel] - sp[i], sn[i])
                inside[np.flatnonzero(sel)[side < 0.0]] = True
        out = dc[~inside]
        return float(out.max()) if len(out) else tol


def hull_overcover(part: ConvexPart, ref: SurfaceRef, tol: float = TOL_MM, max_samples: int = 3000) -> float:
    """Groesster Abstand eines Huellenpunkts ausserhalb des Roh-Solids zur Oberflaeche."""
    m = part.trimesh()
    count = int(np.clip(m.area / 9.0, 200, max_samples))
    samp, _ = trimesh.sample.sample_surface(m, count, seed=1)
    return ref.overcover(np.vstack([samp, part.vertices]), tol)


def _plane_form(part: ConvexPart) -> tuple[np.ndarray, np.ndarray]:
    n = np.asarray(part.trimesh().face_normals, float)
    b = np.einsum("ij,ij->i", n, part.vertices[part.faces[:, 0]])
    return n, b


def plane_distance(part: ConvexPart, pts: np.ndarray) -> np.ndarray:
    """max_f (n_f.x - b_f): <= 0 innen, sonst untere Schranke des Abstands."""
    n, b = _plane_form(part)
    dist = np.full(len(pts), -np.inf)
    for s in range(0, len(n), 256):
        dist = np.maximum(dist, (pts @ n[s : s + 256].T - b[s : s + 256]).max(axis=1))
    return dist


def assign_margins(parts: list[ConvexPart], points: np.ndarray) -> list[ConvexPart]:
    """Setzt je Teil das Aufmass, sodass jeder Punkt in einem aufgeblasenen Teil liegt."""
    if not parts:
        return parts
    pts = np.asarray(points, float)
    best = np.full(len(pts), np.inf)
    idx = np.zeros(len(pts), dtype=np.int64)
    for i, p in enumerate(parts):
        dist = plane_distance(p, pts)
        better = dist < best
        best[better] = dist[better]
        idx[better] = i
    margins = np.zeros(len(parts))
    outside = best > 1e-6
    for i, p in enumerate(parts):
        sel = outside & (idx == i)
        if sel.any():
            _, d, _ = trimesh.proximity.closest_point(p.trimesh(), pts[sel])
            margins[i] = float(np.max(d))
    return [
        ConvexPart(p.vertices, p.faces, float(m) + SAFETY_MM) for p, m in zip(parts, margins, strict=True)
    ]


def vhacd_parts(mesh: trimesh.Trimesh, params: dict | None = None) -> list[ConvexPart]:
    """VHACD-Zerlegung (Teile als konvexe Huellen der VHACD-Ausgabe, ohne Aufmass)."""
    import vhacdx

    prm = dict(VHACD_PARAMS)
    prm.update(params or {})
    out = vhacdx.compute_vhacd(
        np.asarray(mesh.vertices, np.float64), np.asarray(mesh.faces, np.uint32), **prm
    )
    parts = []
    for v, _f in out:
        if len(v) >= 4:
            try:
                parts.append(hull_part(v))
            except Exception:  # noqa: BLE001 - degeneriert; das Aufmass deckt ab
                continue
    return parts


# --------------------------------------------------------------------------- Zerlegung


def bisect_hulls(pts: np.ndarray, ref: SurfaceRef, tol: float, depth: int = 0) -> list[ConvexPart]:
    """Hierarchische Huellen-Bisektion einer Punktmenge der Oberflaeche."""
    try:
        hp = hull_part(pts)
    except Exception:  # noqa: BLE001 - flach oder zu wenige Punkte
        return []
    if depth >= _MAX_DEPTH or len(pts) < 64 or hull_overcover(hp, ref, tol) <= tol:
        return [hp]
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    best = None
    for ax in vt:
        s = (pts - c) @ ax
        for qtl in _SPLIT_QUANTILES:
            cut = float(np.quantile(s, qtl))
            left, right = s <= cut + 0.5, s >= cut - 0.5
            if left.sum() < 4 or right.sum() < 4 or left.all() or right.all():
                continue
            vol = 0.0
            for sel in (left, right):
                try:
                    vol += float(trimesh.convex.convex_hull(pts[sel]).volume)
                except Exception:  # noqa: BLE001
                    pass
            if best is None or vol < best[0]:
                best = (vol, left, right)
    if best is None:
        return [hp]
    _, left, right = best
    return bisect_hulls(pts[left], ref, tol, depth + 1) + bisect_hulls(pts[right], ref, tol, depth + 1)


def _decompose_component(
    comp: trimesh.Trimesh,
    pts: np.ndarray,
    ref: SurfaceRef,
    tol: float,
    try_vhacd: bool,
) -> list[ConvexPart]:
    try:
        hp = hull_part(pts)
    except Exception:  # noqa: BLE001
        return []
    if hull_overcover(hp, ref, tol) <= tol:
        return [hp]
    if try_vhacd and comp.is_watertight and comp.volume > 0:
        try:
            vparts = vhacd_parts(comp)
        except Exception:  # noqa: BLE001
            vparts = []
        vol = sum(abs(float(p.trimesh().volume)) for p in vparts)
        if (
            vparts
            and vol >= 0.9 * float(comp.volume)
            and max(hull_overcover(p, ref, tol) for p in vparts) <= tol
            and max(p.margin for p in assign_margins(vparts, pts)) <= tol
        ):
            return vparts
    return bisect_hulls(pts, ref, tol)


def _covered(parts: list[ConvexPart], pts: np.ndarray, slack: float = 0.5) -> bool:
    """Liegt jeder Punkt in (mindestens) einem Teil, bis auf `slack` mm?"""
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    left = np.ones(len(pts), dtype=bool)
    for p in parts:
        plo, phi = p.vertices.min(axis=0), p.vertices.max(axis=0)
        if np.any(plo > hi + slack) or np.any(phi < lo - slack):
            continue
        left[left] = plane_distance(p, pts[left]) > slack
        if not left.any():
            return True
    return False


def decompose_mesh(
    mesh: trimesh.Trimesh,
    tag: str,
    *,
    tol: float = TOL_MM,
    keep: Callable[[np.ndarray], np.ndarray] | None = None,
    keep_key: str = "",
    try_vhacd: bool = False,
    use_cache: bool = True,
) -> list[ConvexPart]:
    """Konvexzerlegung mit Aufmass eines (Teil-)Meshes, gecacht.

    `keep(points) -> bool-Maske` beschraenkt die Geometrie auf einen Bereich (z. B. Werkzeugkoerper
    ausserhalb der Freizone); `keep_key` muss ihn im Cache-Schluessel eindeutig beschreiben.
    """

    def build() -> list[ConvexPart]:
        merged = mesh.copy()
        merged.merge_vertices()
        comps = []
        samples = []
        cover = []
        for comp in merged.split(only_watertight=False):
            if comp.is_watertight:
                trimesh.repair.fix_normals(comp)
            pts, nrm = surface_samples(comp)
            if keep is not None:
                sel = keep(pts)
                pts, nrm = pts[sel], nrm[sel]
            cover.append(pts)
            if len(pts) >= 4:
                comps.append(comp)
                samples.append((pts, nrm))
        if not comps:
            return []
        # Eine Referenz fuer das ganze Mesh: Huellenpunkte in einer anderen Komponente sind innen.
        # Offene Komponenten (Werkzeug-STL) nutzen ihre Dateinormalen fuer den Innen-Test.
        ref = SurfaceRef(
            np.vstack([p for p, _ in samples]),
            samples,
        )
        parts: list[ConvexPart] = []
        # Grosse Komponenten zuerst; Komponenten, die schon in Teilen liegen, entfallen.
        order = np.argsort([-float(np.ptp(p, axis=0).max()) for p, _ in samples], kind="stable")
        for i in order:
            comp, (pts, _) = comps[i], samples[i]
            if parts and _covered(parts, pts):
                continue
            parts.extend(_decompose_component(comp, pts, ref, tol, try_vhacd and keep is None))
        return assign_margins(parts, np.vstack(cover))

    if not use_cache:
        return build()
    extra = f"{tag}|{tol}|{keep_key}|{try_vhacd}|{sorted(VHACD_PARAMS.items())}"
    key = mesh_hash(np.asarray(mesh.vertices), np.asarray(mesh.faces), extra=extra)
    return cached(tag, key, build)


def box_part(lo: np.ndarray, hi: np.ndarray) -> ConvexPart:
    """Achsparalleler Quader als konvexes Teil ohne Aufmass."""
    b = trimesh.creation.box(bounds=np.array([lo, hi], dtype=float))
    return ConvexPart(np.asarray(b.vertices, float), np.asarray(b.faces, np.int64), 0.0)


# --------------------------------------------------------------------------- Default-Assets


def link_mesh(entries) -> trimesh.Trimesh:
    """Kollisionsmeshes eines Glieds (urdf_chain.CollisionEntry) im Gliedframe, mm."""
    meshes = []
    for e in entries:
        m = trimesh.load(str(e.path), force="mesh", process=True)
        m.apply_scale(e.scale_to_mm)
        m.apply_transform(e.origin)
        meshes.append(m)
    out = trimesh.util.concatenate(meshes)
    out.merge_vertices()
    return out


def link_parts(chain) -> dict[str, list[ConvexPart]]:
    """Zerlegung je Glied der Kette (Gliedframe)."""
    return {
        name: decompose_mesh(link_mesh(chain.collision[name]), f"link-{name}")
        for name in chain.link_names
        if chain.collision.get(name)
    }


def tool_parts(
    tool_mesh_F: trimesh.Trimesh, tcp_F: np.ndarray, r_free_mm: float
) -> tuple[list[ConvexPart], list[ConvexPart]]:
    """(Werkzeugkoerper, Duesenspitze) im Flanschframe F.

    Die Teilung an der Kugel r_free um den TCP ist um 1,5 mm konservativ: Der Koerper umfasst
    alles ab r_free - 1,5 mm, die Spitze alles bis r_free + 1,5 mm (unabhaengige Pruefer ordnen
    Dreiecke an der Kugel nach Schwerpunkt zu).
    """
    tcp = np.asarray(tcp_F, dtype=float)
    r_body, r_tip = r_free_mm - 1.5, r_free_mm + 1.5

    def body_keep(p: np.ndarray) -> np.ndarray:
        return np.linalg.norm(p - tcp, axis=1) >= r_body

    def tip_keep(p: np.ndarray) -> np.ndarray:
        return np.linalg.norm(p - tcp, axis=1) <= r_tip

    key = f"{np.round(tcp, 6).tolist()}|{r_free_mm}"
    body = decompose_mesh(tool_mesh_F, "tool-body", keep=body_keep, keep_key="body" + key)
    tip = decompose_mesh(tool_mesh_F, "tool-tip", keep=tip_keep, keep_key="tip" + key)
    return body, tip


def table_parts(table_mesh_W: trimesh.Trimesh) -> list[ConvexPart]:
    return decompose_mesh(table_mesh_W, "table", tol=25.0)


def is_box(mesh: trimesh.Trimesh) -> bool:
    """Achsparalleler Quader (in seinem Frame)?"""
    lo, hi = mesh.bounds
    vol = float(np.prod(hi - lo))
    if not mesh.is_watertight or vol <= 0:
        return False
    if abs(abs(float(mesh.volume)) - vol) > 1e-6 * vol:
        return False
    v = np.asarray(mesh.vertices)
    on_x = np.isclose(v[:, 0], lo[0]) | np.isclose(v[:, 0], hi[0])
    on_y = np.isclose(v[:, 1], lo[1]) | np.isclose(v[:, 1], hi[1])
    on_z = np.isclose(v[:, 2], lo[2]) | np.isclose(v[:, 2], hi[2])
    return bool(np.all(on_x & on_y & on_z))


def clip_below(mesh: trimesh.Trimesh, z: float) -> trimesh.Trimesh | None:
    """mesh ∩ {z' <= z} als geschlossenes Solid (manifold3d)."""
    import manifold3d as mf

    lo, hi = mesh.bounds
    if z <= lo[2] + 1e-9:
        return None
    if z >= hi[2] - 1e-9:
        return mesh.copy()
    man = mf.Manifold(
        mf.Mesh(
            vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
        )
    )
    out = man.trim_by_plane((0.0, 0.0, -1.0), -float(z)).to_mesh()
    res = trimesh.Trimesh(
        np.asarray(out.vert_properties)[:, :3].astype(float),
        np.asarray(out.tri_verts, dtype=np.int64),
        process=True,
    )
    return res if len(res.faces) else None


def printed_parts(part_mesh_P: trimesh.Trimesh, z_cut_P: float) -> list[ConvexPart]:
    """Druckstand Teil ∩ {z_P <= z_cut} im Frame P; Quader direkt, sonst zerlegt (gecacht)."""
    lo, hi = part_mesh_P.bounds
    if z_cut_P <= lo[2] + 1e-9:
        return []
    if is_box(part_mesh_P):
        top = min(float(hi[2]), float(z_cut_P))
        return [box_part(lo, np.array([hi[0], hi[1], top]))]
    clipped = clip_below(part_mesh_P, z_cut_P)
    if clipped is None:
        return []
    return decompose_mesh(clipped, "printed", tol=TOL_MM)

"""Schmale URDF-Kettenauswertung: Gliedposen in B aus `q` (Doosan-Konvention = URDF-Null).

Liest Gelenk-Origins, -Achsen und die `<collision>`-Meshes direkt aus der URDF. Die Kette ist
seriell (`base_link` -> `link_1` ... `link_6`), alle Gelenke sind Drehgelenke. Laengen in mm.
`roboprint.robot` kann seine FK auf `UrdfChain.link_poses` stuetzen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_URDF = Path("third_party/doosan_m1013/urdf/m1013.white.urdf")
_PACKAGE_PREFIX = "package://dsr_description2/"
_MM_PER_M = 1000.0


def rpy_matrix(rpy: np.ndarray) -> np.ndarray:
    """URDF-rpy (fest, X dann Y dann Z) als Rotationsmatrix R = Rz(y) Ry(p) Rx(r)."""
    r, p, y = (float(v) for v in rpy)
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ]
    )


def _origin_mm(el: ET.Element | None) -> np.ndarray:
    t = np.eye(4)
    if el is None:
        return t
    xyz = np.array([float(v) for v in el.get("xyz", "0 0 0").split()])
    rpy = np.array([float(v) for v in el.get("rpy", "0 0 0").split()])
    t[:3, :3] = rpy_matrix(rpy)
    t[:3, 3] = xyz * _MM_PER_M
    return t


@dataclass(frozen=True)
class CollisionEntry:
    """Ein `<collision>`-Mesh eines Glieds: Datei, Origin im Gliedframe (mm), Faktor auf mm."""

    path: Path
    origin: np.ndarray
    scale_to_mm: float


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str
    child: str
    origin: np.ndarray  # 4x4, mm
    axis: np.ndarray  # Einheitsvektor im Kindframe
    lower: float
    upper: float


class UrdfChain:
    """Serielle Kette aus der URDF. `link_poses(q)` liefert T_B,link je Glied in mm."""

    def __init__(self, urdf_path: Path, mesh_root: Path | None = None) -> None:
        self.urdf_path = Path(urdf_path)
        tree = ET.parse(self.urdf_path).getroot()
        links = {ln.get("name"): ln for ln in tree.findall("link")}
        joints_by_parent: dict[str, Joint] = {}
        for jel in tree.findall("joint"):
            if jel.get("type") not in ("revolute", "continuous"):
                continue
            axis = np.array([float(v) for v in jel.find("axis").get("xyz").split()])
            lim = jel.find("limit")
            j = Joint(
                name=jel.get("name"),
                parent=jel.find("parent").get("link"),
                child=jel.find("child").get("link"),
                origin=_origin_mm(jel.find("origin")),
                axis=axis / np.linalg.norm(axis),
                lower=float(lim.get("lower")) if lim is not None else -np.inf,
                upper=float(lim.get("upper")) if lim is not None else np.inf,
            )
            joints_by_parent[j.parent] = j
        children = {j.child for j in joints_by_parent.values()}
        root_link = next(n for n in links if n not in children)
        self.link_names: list[str] = [root_link]
        self.joints: list[Joint] = []
        while self.link_names[-1] in joints_by_parent:
            j = joints_by_parent[self.link_names[-1]]
            self.joints.append(j)
            self.link_names.append(j.child)
        mesh_root = mesh_root or self.urdf_path.parent.parent
        self.collision: dict[str, list[CollisionEntry]] = {}
        for name in self.link_names:
            entries = []
            for coll in links[name].findall("collision"):
                mel = coll.find("geometry/mesh")
                if mel is None:
                    continue
                fn = mel.get("filename", "")
                rel = fn[len(_PACKAGE_PREFIX) :] if fn.startswith(_PACKAGE_PREFIX) else fn
                scale = np.array([float(v) for v in mel.get("scale", "1 1 1").split()])
                if not np.allclose(scale, scale[0]):
                    raise ValueError(f"nicht-uniforme Skalierung in {fn}")
                entries.append(
                    CollisionEntry(
                        path=mesh_root / rel,
                        origin=_origin_mm(coll.find("origin")),
                        scale_to_mm=float(scale[0]) * _MM_PER_M,
                    )
                )
            self.collision[name] = entries
        self._origins = np.stack([j.origin for j in self.joints])  # (n,4,4)
        self._axes = np.stack([j.axis for j in self.joints])  # (n,3)

    @property
    def n_joints(self) -> int:
        return len(self.joints)

    def link_poses_batch(self, Q: np.ndarray) -> np.ndarray:  # noqa: N803
        """(N, n_links, 4, 4): T_B,link fuer jede Zeile von Q (rad)."""
        Q = np.atleast_2d(np.asarray(Q, dtype=float))  # noqa: N806
        n = Q.shape[0]
        out = np.empty((n, len(self.link_names), 4, 4))
        cur = np.broadcast_to(np.eye(4), (n, 4, 4)).copy()
        out[:, 0] = cur
        for i, _j in enumerate(self.joints):
            rot = _axis_angle_batch(self._axes[i], Q[:, i])
            step = self._origins[i] @ rot  # (n,4,4)
            cur = cur @ step
            out[:, i + 1] = cur
        return out

    def link_poses_array(self, q: np.ndarray) -> np.ndarray:
        """(n_links, 4, 4) fuer eine Pose."""
        return self.link_poses_batch(np.asarray(q, dtype=float)[None, :])[0]

    def link_poses(self, q: np.ndarray) -> dict[str, np.ndarray]:
        """{Gliedname: T_B,link (4x4, mm)}."""
        arr = self.link_poses_array(q)
        return {name: arr[i] for i, name in enumerate(self.link_names)}


def _axis_angle_batch(axis: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """(N,4,4) homogene Drehungen um `axis` (Rodrigues)."""
    x, y, z = axis
    c = np.cos(angles)
    s = np.sin(angles)
    t = 1.0 - c
    n = angles.shape[0]
    m = np.zeros((n, 4, 4))
    m[:, 0, 0] = t * x * x + c
    m[:, 0, 1] = t * x * y - s * z
    m[:, 0, 2] = t * x * z + s * y
    m[:, 1, 0] = t * x * y + s * z
    m[:, 1, 1] = t * y * y + c
    m[:, 1, 2] = t * y * z - s * x
    m[:, 2, 0] = t * x * z - s * y
    m[:, 2, 1] = t * y * z + s * x
    m[:, 2, 2] = t * z * z + c
    m[:, 3, 3] = 1.0
    return m


@lru_cache(maxsize=4)
def load_chain(root: Path | None = None) -> UrdfChain:
    """Kette aus der Default-URDF unter `root` (Repo-Wurzel)."""
    return UrdfChain((Path(root) if root else REPO_ROOT) / DEFAULT_URDF)


def link_poses(q: np.ndarray, root: Path | None = None) -> dict[str, np.ndarray]:
    """{Gliedname: T_B,link (4x4, mm)} fuer `q` in Doosan-Konvention."""
    return load_chain(root).link_poses(q)

"""Backend-Schalter FCL↔SDF der Kollisionskontrolle — injizierbares Modul auf App-Ebene (#213).

Die eine Stelle, an der entschieden wird, **welcher Hindernis-Provider** in
:func:`fgc.collision.check.find_collisions` injiziert wird (US 14, CPU-Naht):

- ``"fcl"`` (Default): die Referenz :func:`fgc.collision.druckstand.
  obstacle_provider` — exakt der bisherige Pfad, Altläufe bleiben
  byte-identisch (US 12).
- ``"sdf"``: der :class:`fgc.collision.sdf_provider.SdfObstacleProvider` —
  Punkt-gegen-Glied-SDF-Inversion mit FCL-Nachprüfer im Grenzband.

Der Schalter lebt **bewusst nicht in** ``CollisionConfig`` (PRD #183,
Kommentar 2026-07-14): die Konfiguration eines Laufs beschreibt das *Urteil*
(Sicherheitsabstand, Freizone), nicht die *Maschinerie* — beide Backends
liefern denselben Befund (US 2), also gehört die Wahl auf App-Ebene
(Umschaltung per :func:`set_collision_backend` oder Umgebungsvariable
``FGC_COLLISION_BACKEND``). Die GPU-Naht (#205) dockt ausschließlich an
``check_representative`` an — dieser Schalter hält sie frei und kennt sie
nicht.

**Fail-soft (US 12):** ist ``"sdf"`` gewählt, aber der Roboter hat kein (oder
ein provenienz-ungültiges) Glied-SDF-Artefakt, fällt die Konstruktion still
auf die FCL-Referenz zurück — Altbestand ohne die neuen Artefakte läuft
unverändert, kein Crash, kein stiller Falschbefund (die Referenz ist das
exakte Urteil). Geladene Artefakte und Glied-Punktwolken werden je Roboter
prozessweit gecacht (die Prüf-Tür ruft je Kandidat neu).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fgc.collision import druckstand as _ds
from fgc.collision.druckstand_punkte import DEFAULT_POINT_SPACING_MM
from fgc.collision.glied_sdf import SdfProvenanceError, load_glied_sdf
from fgc.collision.sdf_provider import SdfObstacleProvider

if TYPE_CHECKING:  # nur für Typprüfer — kein Laufzeit-Import (geo-frei startbar)
    from fgc.collision.druckstand import DruckstandSpec, ObstacleSet
    from fgc.collision.robot_geometry import RobotCollisionGeometry

#: Umgebungsvariable der App-Konfiguration (gilt, solange kein
#: :func:`set_collision_backend`-Aufruf sie übersteuert).
BACKEND_ENV = "FGC_COLLISION_BACKEND"

BACKENDS = ("fcl", "sdf")

_active: str | None = None

#: Prozessweite Caches je (Roboter, Katalogpfad): Glied-SDF-Artefakt und die
#: lazily wachsenden Glied-Punktwolken (geteiltes Dict, s. ``SdfObstacleProvider``).
_sdf_cache: dict[tuple[str, str], Any] = {}
_link_points_cache: dict[tuple[str, str, float], dict[int, Any]] = {}


def collision_backend() -> str:
    """Das aktive Backend: expliziter Setzwert > Umgebungsvariable > ``"fcl"``.

    Unbekannte Werte fallen soft auf ``"fcl"`` (Altläufe brechen nie an einer
    Tippfehler-Konfiguration).
    """
    if _active is not None:
        return _active
    env = os.environ.get(BACKEND_ENV, "").strip().lower()
    return env if env in BACKENDS else "fcl"


def set_collision_backend(name: str | None) -> None:
    """Setzt das Backend programmatisch (App-Ebene); ``None`` = zurück zur Umgebung."""
    global _active
    if name is not None and name not in BACKENDS:
        raise ValueError(f"Unbekanntes Kollisions-Backend {name!r} (erlaubt: {BACKENDS})")
    _active = name


def obstacle_provider_for(
    robot_name: str,
    spec: DruckstandSpec,
    *,
    robots_dir: Path | None = None,
    geo: RobotCollisionGeometry | None = None,
) -> Callable[[int], ObstacleSet]:
    """Der eine Konstruktionspunkt des injizierten Hindernis-Providers (US 14).

    Liefert je nach :func:`collision_backend` die FCL-Referenz oder den
    ``SdfObstacleProvider``; beide erfüllen denselben Vertrag
    ``Callable[[int], ObstacleSet]``. ``geo`` kann der Aufrufer durchreichen
    (er hat die Kollisions-Geometrie meist schon geladen); fehlende/ungültige
    Glied-SDF-Artefakte fallen soft auf die FCL-Referenz zurück (US 12).
    """
    if collision_backend() != "sdf":
        return _ds.obstacle_provider(spec)
    key = (robot_name, str(robots_dir) if robots_dir is not None else "")
    try:
        glied_sdf = _sdf_cache.get(key)
        if glied_sdf is None:
            glied_sdf = load_glied_sdf(robot_name, robots_dir)
            _sdf_cache[key] = glied_sdf
        if geo is None:
            from fgc.collision.robot_geometry import load_robot_collision_geometry

            geo = load_robot_collision_geometry(robot_name, robots_dir)
    except (FileNotFoundError, SdfProvenanceError, ImportError):
        # Fail-soft: Altbestand ohne SDF-Artefakt (oder ohne Geo-Extras beim
        # SDF-Laden) urteilt weiter über die exakte FCL-Referenz.
        return _ds.obstacle_provider(spec)
    shared_link_points = _link_points_cache.setdefault((*key, DEFAULT_POINT_SPACING_MM), {})
    return SdfObstacleProvider(spec, glied_sdf, geo, link_points=shared_link_points)

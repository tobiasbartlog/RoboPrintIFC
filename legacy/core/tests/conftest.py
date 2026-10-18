"""Geteilte Fixtures der Core-Suite — benennt den Wand-Quellen-Seam (Issue #197).

Die Wandquelle ist im Aktions-Interface unsichtbar; real existieren zwei Adapter
(``ifcopenshell``-Loader und Test-Stub). Bis #197 lebte der Seam nur als
Monkeypatch-Folklore: ``make_wall`` war 10×, ``stub_walls`` 8× wortgleich über
die Suite kopiert, und die Patch-Ziele (``fgc.ifc_io.walls.load_walls`` /
``load_wall`` / ``fgc.ifc_io.context.load_context_overview``) standen 18× per
Hand ausbuchstabiert. Hier stehen sie **einmal**:

* :func:`build_wall` / Fixture ``make_wall`` — baut Stub-Wände ohne IFC.
* Fixture ``install_walls`` — installiert die Test-Adapter der drei Loader an
  ihrer *einen* Quelle. Konsumenten (`actions`, `wizard`, `api`, `cli`,
  `sectionsim`) importieren die Loader top-level per Modul-Alias, sodass dieser
  eine Patch am Quell-Modul überall greift.

Die dünnen ``stub_walls``-Fixtures der einzelnen Testdateien komponieren nur noch
``install_walls`` + ``make_wall`` mit ihrer datei-spezifischen Wand — die
duplizierte Patch-Logik ist verschwunden.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

import numpy as np
import pytest
import trimesh

from fgc.ifc_io.analysis import analyze_wall_mesh
from fgc.ifc_io.context import ContextElement
from fgc.ifc_io.walls import WallData


def build_wall(
    global_id: str = "WALLAAAAAAAAAAAAAAAAAA",
    *,
    length: float = 1500.0,
    thickness: float = 200.0,
    height: float = 900.0,
    load_bearing: bool | None = False,
    is_external: bool | None = None,
    openings: int = 0,
    name: str = "Testwand",
) -> WallData:
    """Quaderwand im Weltsystem (x/y zentriert, z ab 0) — ohne IFC/ifcopenshell.

    Deckt alle bisherigen Kopien ab: ``length``/``thickness``/``height`` steuern
    die Geometrie (überhohe Wände für Zerlegungs-Tests via ``height=2600``),
    ``global_id`` die Zuordnung im Stub-Loader.
    """
    box = trimesh.creation.box(extents=[length, thickness, height])
    verts = np.asarray(box.vertices) + np.array([0.0, 0.0, height / 2.0])
    return WallData(
        global_id=global_id,
        name=name,
        load_bearing=load_bearing,
        is_external=is_external,
        opening_count=openings,
        vertices_mm=verts,
        faces=np.asarray(box.faces),
        geometry=analyze_wall_mesh(verts),
    )


@pytest.fixture
def make_wall() -> Callable[..., WallData]:
    """Factory-Fixture: ``make_wall("WALLAAA…", height=2600.0)`` → :class:`WallData`."""
    return build_wall


@pytest.fixture
def install_walls(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[WallData]]:
    """Installiert die Test-Adapter der Wand-/Kontext-Loader an ihrer einen Quelle.

    ``install_walls([make_wall(...)], context=[slab])`` patcht ``load_walls``
    (ganze Liste), ``load_wall`` (Zuordnung per GlobalId) und
    ``load_context_overview`` (Default: leerer Gebäudekontext). Gibt die
    installierte Wandliste zurück.
    """

    def _install(
        walls: Sequence[WallData],
        *,
        context: Iterable[ContextElement] = (),
    ) -> list[WallData]:
        walls = list(walls)
        context = list(context)
        by_id = {w.global_id: w for w in walls}
        monkeypatch.setattr("fgc.ifc_io.walls.load_walls", lambda _p: walls)
        monkeypatch.setattr(
            "fgc.ifc_io.walls.load_wall",
            lambda _p, gid: by_id.get(gid, walls[0]),
        )
        monkeypatch.setattr(
            "fgc.ifc_io.context.load_context_overview", lambda _p: context
        )
        return walls

    return _install

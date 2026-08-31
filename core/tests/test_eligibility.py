"""E1-Stufe-1-Regeln einzeln und als Gesamtauswertung (ADR-013)."""

import math

import numpy as np
import trimesh
from shapely.geometry import Polygon

from fgc.domain.process_params import ProcessWindow
from fgc.domain.robot import RobotDef
from fgc.eligibility import evaluate_wall, footprint
from fgc.eligibility.rules import (
    EligibilityContext,
    check_footprint,
    check_load_bearing,
    check_openings,
    check_thickness,
    check_workspace,
)
from fgc.ifc_io.analysis import analyze_wall_mesh
from fgc.ifc_io.walls import WallData

ROBOT = RobotDef(
    name="test_robot",
    reach_mm=1300,
    max_print_height_mm=1000,
    max_print_length_mm=2000,
    workspace_provisional=True,
)

EMPTY_WINDOW = ProcessWindow()  # alle Werte None (heutiger Kartenstand)


def make_wall(
    length=1500.0, thickness=200.0, height=900.0, load_bearing=None, openings=0
) -> WallData:
    box = trimesh.creation.box(extents=[length, thickness, height])
    verts = np.asarray(box.vertices) + np.array([0, 0, height / 2])
    return WallData(
        global_id="TESTWALL00000000000000",
        name="Testwand",
        load_bearing=load_bearing,
        is_external=None,
        opening_count=openings,
        vertices_mm=verts,
        faces=np.asarray(box.faces),
        geometry=analyze_wall_mesh(verts),
    )


def ctx(**wall_kwargs) -> EligibilityContext:
    return EligibilityContext(wall=make_wall(**wall_kwargs), window=EMPTY_WINDOW, robot=ROBOT)


def test_load_bearing_missing_is_provisional_pass():
    result = check_load_bearing(ctx(load_bearing=None))
    assert result.passed and result.provisional


def test_load_bearing_true_fails():
    assert not check_load_bearing(ctx(load_bearing=True)).passed


def test_openings_defer_wall():
    result = check_openings(ctx(openings=2))
    assert not result.passed
    assert result.deferred


def test_workspace_too_high_fails():
    result = check_workspace(ctx(height=1200.0))
    assert not result.passed
    assert "Höhe" in result.reason


def test_thickness_skipped_while_window_empty():
    result = check_thickness(ctx())
    assert result.passed and result.provisional


def test_thickness_enforced_with_explicit_window_values():
    window = ProcessWindow(wall_thickness_min_mm=100.0, wall_thickness_max_mm=150.0)
    context = EligibilityContext(wall=make_wall(thickness=200.0), window=window, robot=ROBOT)
    assert not check_thickness(context).passed


# --- Stufe 2 A: Dicke aus Strangbreite × Schalenlogik (S4-Stegformel) ---------

# Test-Fixture (NICHT die echte Karte): sobald S1 die Strangbreite liefert, wird
# die Dickenuntergrenze scharf. Bei w=30, min_web=1.5, 2 Schalen:
# factor = 1.5 + 2*(2-1) = 3.5  ->  t_min = 30 * 3.5 = 105 mm.
# provisional=False stellt den Zustand NACH S1 dar (Strangbreite gemessen, Karte scharf).
STRAND_WINDOW = ProcessWindow(
    strand_width_mm=30.0, min_web_width_strand_widths=1.5, default_shells=2, provisional=False
)


def test_thickness_still_skipped_when_strand_width_missing():
    # Karte ohne Strangbreite -> heutiges Verhalten bleibt: provisional übersprungen.
    window = ProcessWindow(min_web_width_strand_widths=1.5, default_shells=2)
    context = EligibilityContext(wall=make_wall(thickness=200.0), window=window, robot=ROBOT)
    result = check_thickness(context)
    assert result.passed and result.provisional
    assert "übersprungen" in result.reason


def test_thickness_derived_lower_bound_rejects_thin_wall():
    context = EligibilityContext(
        wall=make_wall(thickness=80.0), window=STRAND_WINDOW, robot=ROBOT
    )
    result = check_thickness(context)
    assert not result.passed
    # Grund nennt die Zahlen: Ist-Dicke, Mindestdicke, Faktor, w, Schalenzahl.
    assert "80" in result.reason and "105" in result.reason
    assert "3.5×w" in result.reason and "S4" in result.reason


def test_thickness_derived_lower_bound_accepts_thick_wall():
    context = EligibilityContext(
        wall=make_wall(thickness=200.0), window=STRAND_WINDOW, robot=ROBOT
    )
    assert check_thickness(context).passed


def test_thickness_derived_bound_grows_with_shell_count():
    # 4 Schalen: factor = 1.5 + 2*3 = 7.5  ->  t_min = 225 mm; 200 mm reicht nicht mehr.
    window = ProcessWindow(
        strand_width_mm=30.0, min_web_width_strand_widths=1.5, default_shells=4
    )
    context = EligibilityContext(wall=make_wall(thickness=200.0), window=window, robot=ROBOT)
    result = check_thickness(context)
    assert not result.passed
    assert "225" in result.reason


def test_thickness_explicit_mm_takes_precedence_over_derived():
    # Explizite Untergrenze (60 mm) schlägt die abgeleitete (105 mm): 80 mm besteht.
    window = ProcessWindow(
        strand_width_mm=30.0,
        min_web_width_strand_widths=1.5,
        default_shells=2,
        wall_thickness_min_mm=60.0,
    )
    context = EligibilityContext(wall=make_wall(thickness=80.0), window=window, robot=ROBOT)
    assert check_thickness(context).passed


def test_default_shells_shared_by_e1_and_slicer():
    """ADR-013-Pin: E1 (Dickenprüfung) und Slicer (SliceParams) beziehen die
    Schalenzahl beweisbar aus derselben Karte (ProcessWindow.default_shells) --
    kein zweites, unabhängiges Default-Literal."""
    from fgc.domain.process_params import SliceParams

    window = ProcessWindow(
        strand_width_mm=30.0, min_web_width_strand_widths=1.5, default_shells=3
    )

    # Slicer: from_window übernimmt default_shells, solange kein Override kommt.
    params = SliceParams.from_window(window)
    assert params.n_shells == 3

    # E1: Dickenprüfung rechnet mit denselben 3 Schalen (S4-Stegformel).
    # factor = 1.5 + 2*(3-1) = 5.5  ->  t_min = 30 * 5.5 = 165 mm.
    too_thin = EligibilityContext(wall=make_wall(thickness=160.0), window=window, robot=ROBOT)
    result = check_thickness(too_thin)
    assert not result.passed
    assert "165" in result.reason and "3 Schalen" in result.reason

    thick_enough = EligibilityContext(wall=make_wall(thickness=170.0), window=window, robot=ROBOT)
    assert check_thickness(thick_enough).passed

    # Explizites CLI-Override schlägt weiterhin den Kartenwert (unverändertes Verhalten).
    overridden = SliceParams.from_window(window, n_shells=5)
    assert overridden.n_shells == 5


# --- Stufe 2 B: Grundriss-Geometrie (Winkel, Steg) ----------------------------


def _wedge(apex_deg: float, arm_mm: float = 500.0) -> Polygon:
    """Gleichschenkliges Dreieck mit konvexer Spitze vom Innenwinkel apex_deg."""
    half = math.radians(apex_deg) / 2.0
    tip = (0.0, 0.0)
    a = (arm_mm * math.cos(half), arm_mm * math.sin(half))
    b = (arm_mm * math.cos(half), -arm_mm * math.sin(half))
    return Polygon([tip, a, b])


def test_footprint_skipped_without_polygon():
    # v1-Wand ohne Grundriss-Quelle -> provisional durchgewinkt.
    result = check_footprint(ctx())
    assert result.passed and result.provisional
    assert "Grundriss" in result.reason


def test_min_convex_angle_of_wedge():
    assert math.isclose(footprint.min_convex_interior_angle_deg(_wedge(30.0)), 30.0, abs_tol=0.5)


def test_footprint_sharp_wedge_fails():
    window = ProcessWindow(min_convex_angle_deg=30.0)
    context = EligibilityContext(
        wall=make_wall(), window=window, robot=ROBOT, footprint=_wedge(20.0)
    )
    result = check_footprint(context)
    assert not result.passed
    assert "20°" in result.reason and "30°" in result.reason


def test_footprint_thirty_degree_wedge_passes():
    window = ProcessWindow(min_convex_angle_deg=30.0)
    context = EligibilityContext(
        wall=make_wall(), window=window, robot=ROBOT, footprint=_wedge(30.0)
    )
    assert check_footprint(context).passed


def test_footprint_narrow_web_fails():
    # w=30, 2 Schalen -> Mindeststegbreite 105 mm; ein 60-mm-Hals zerfällt.
    # Zwei Lappen (280 mm breit), verbunden durch einen Hals der Höhe 60 mm.
    dumbbell = Polygon(
        [
            (0, 0), (200, 0), (200, 110), (260, 110), (260, 0), (460, 0),
            (460, 280), (260, 280), (260, 170), (200, 170), (200, 280), (0, 280),
        ]
    )
    result = check_footprint(
        EligibilityContext(
            wall=make_wall(), window=STRAND_WINDOW, robot=ROBOT, footprint=dumbbell
        )
    )
    assert not result.passed
    assert "Steg" in result.reason and "105" in result.reason


def test_footprint_wide_rectangle_passes():
    rect = Polygon([(0, 0), (600, 0), (600, 300), (0, 300)])
    result = check_footprint(
        EligibilityContext(
            wall=make_wall(), window=STRAND_WINDOW, robot=ROBOT, footprint=rect
        )
    )
    assert result.passed and not result.provisional


def test_footprint_web_stays_provisional_without_strand_width():
    # Grundriss vorhanden, aber Strangbreite fehlt -> Steg nicht prüfbar, Winkel ok.
    window = ProcessWindow(min_convex_angle_deg=30.0)  # kein strand_width
    rect = Polygon([(0, 0), (600, 0), (600, 300), (0, 300)])
    result = check_footprint(
        EligibilityContext(wall=make_wall(), window=window, robot=ROBOT, footprint=rect)
    )
    assert result.passed and result.provisional


def test_evaluate_wall_eligible_and_artifact_shape():
    candidate = evaluate_wall(make_wall(load_bearing=False), EMPTY_WINDOW, ROBOT)
    assert candidate.eligible
    assert candidate.dimensions_mm["length"] == 1500.0
    assert {c.check for c in candidate.checks} == {
        "planarity",
        "load_bearing",
        "openings",
        "workspace",
        "thickness",
        "footprint",
    }


def test_evaluate_wall_collects_failures():
    candidate = evaluate_wall(
        make_wall(load_bearing=True, openings=1, height=1500.0), EMPTY_WINDOW, ROBOT
    )
    assert not candidate.eligible
    assert {c.check for c in candidate.failed_checks} == {
        "load_bearing",
        "openings",
        "workspace",
    }


# --- ADR-015: footprint-Check über neutrales Schnittmodul aktiv ----------------


def test_evaluate_wall_footprint_check_uses_real_polygon():
    """Nach ADR-015 berechnet evaluate_wall den Grundriss aus dem Mesh.

    Mit einem gesetzten min_convex_angle_deg läuft der Winkel-Check jetzt scharf
    (kein „kein Grundriss-Polygon verfügbar"-Hinweis); das Rechteck (90°) besteht.
    """
    window = ProcessWindow(min_convex_angle_deg=30.0)
    candidate = evaluate_wall(make_wall(load_bearing=False), window, ROBOT)
    footprint_check = next(c for c in candidate.checks if c.check == "footprint")
    assert footprint_check.passed
    # Kein "kein Grundriss-Polygon" in der Begründung — Check lief mit realem Polygon.
    assert footprint_check.reason is None or "kein Grundriss-Polygon" not in footprint_check.reason


def test_evaluate_wall_thin_wall_fails_footprint():
    """Wand, deren Grundriss-Schnitt einen zu schmalen Steg hat, schlägt fehl.

    Eine 50-mm-Wand ist schmaler als die Mindeststegbreite (105 mm = 3.5 × 30 mm
    für 2 Schalen). Der Erosionstest in check_footprint erkennt das am Mesh-Schnitt
    und lehnt die Wand ab. (Planarity-Check schlägt für diese Box nicht fehl.)
    """
    # Mindestbreite: min_web_width_factor(1.5, 2) = 3.5 → 3.5 × 30 = 105 mm
    # 50 mm < 105 mm → has_narrow_web = True → footprint fails
    candidate = evaluate_wall(make_wall(thickness=50.0, load_bearing=False), STRAND_WINDOW, ROBOT)
    footprint_check = next(c for c in candidate.checks if c.check == "footprint")
    assert not footprint_check.passed
    assert "Steg" in (footprint_check.reason or "")


def test_evaluate_wall_wide_wall_passes_footprint():
    """Rechteck-Wand mit ausreichender Dicke besteht den footprint-Check.

    200 mm > 105 mm (Mindeststegbreite bei 2 Schalen, w=30). Der Check läuft
    scharf (nicht provisional) — strand_width ist gesetzt, Polygon ist real.
    """
    candidate = evaluate_wall(make_wall(thickness=200.0, load_bearing=False), STRAND_WINDOW, ROBOT)
    footprint_check = next(c for c in candidate.checks if c.check == "footprint")
    assert footprint_check.passed
    assert not footprint_check.provisional  # voll scharf: Polygon real, strand_width gesetzt


def _prism_mesh(xy_coords: list, height: float) -> trimesh.Trimesh:
    """Prismatisches Trimesh aus 2D-Polygonkoordinaten (ohne Triangulierungs-Engine).

    Nur Seitenflächen werden erzeugt — section_at schneidet ausschließlich diese
    vertikalen Flächen und liefert trotzdem das korrekte Querschnitts-Polygon.
    Deckflächen (Boden/Decke) werden als Fan von Vertex 0 ergänzt, damit trimesh
    kein leeres Mesh zurückgibt; sie liegen bei z=0 bzw. z=height und werden von
    section_at (z=height/2) nicht berührt.
    """
    n = len(xy_coords)
    xy = np.asarray(xy_coords, dtype=float)
    bot = np.column_stack([xy, np.zeros(n)])
    top = np.column_stack([xy, np.full(n, height)])
    verts = np.vstack([bot, top])

    faces = []
    # Seitenflächen: je Kante i→(i+1)%n ein Quad aus 2 Dreiecken
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, j + n])
        faces.append([i, j + n, i + n])
    # Deckflächen als Fan (Winding egal; Schnittebene bei z=height/2 berührt sie nicht)
    for i in range(1, n - 1):
        faces.append([0, i, i + 1])
        faces.append([n, n + i + 1, n + i])

    return trimesh.Trimesh(
        vertices=verts, faces=np.array(faces, dtype=np.int64), process=False
    )


def test_evaluate_wall_nonrect_wedge_mesh_footprint_fails_sharp_angle():
    """End-zu-End: keilförmiges Wand-Mesh → evaluate_wall → footprint-Check schlägt fehl.

    Belegt das fehlende Akzeptanzkriterium (Issue #5): Eine nicht-rechteckige
    Wand wird als manuell gebautes Dreiecksprisma aufgebaut (20°-Keil-Querschnitt).
    section_at liefert das Keil-Polygon; check_footprint erkennt die 20°-Spitze
    und lehnt wegen des spitzen Winkels ab (Schwelle: 30°).
    """
    poly = _wedge(20.0, arm_mm=500.0)
    xy = list(poly.exterior.coords[:-1])  # letzter Punkt = erster (shapely-Konvention)
    height = 900.0
    mesh_tri = _prism_mesh(xy, height)
    verts = np.asarray(mesh_tri.vertices)
    wall = WallData(
        global_id="WEDGEWALL0000000000000",
        name="Keilwand-E2E",
        load_bearing=False,
        is_external=None,
        opening_count=0,
        vertices_mm=verts,
        faces=np.asarray(mesh_tri.faces),
        geometry=analyze_wall_mesh(verts),
    )
    window = ProcessWindow(min_convex_angle_deg=30.0)
    candidate = evaluate_wall(wall, window, ROBOT)
    fp = next(c for c in candidate.checks if c.check == "footprint")
    assert not fp.passed, f"Footprint-Check hätte fehlschlagen sollen; Grund: {fp.reason}"
    assert "20°" in (fp.reason or "") and "30°" in (fp.reason or "")


def test_evaluate_wall_nonrect_dumbbell_mesh_footprint_fails_narrow_web():
    """End-zu-End: hantelförmiges Wand-Mesh → evaluate_wall → footprint-Check schlägt fehl.

    Belegt das fehlende Akzeptanzkriterium (Issue #5): Eine nicht-rechteckige
    Wand (Hantel mit 60-mm-Steg) wird als manuell gebautes Prisma aufgebaut.
    section_at liefert das Hantel-Polygon; check_footprint erkennt den Steg
    (60 mm < Mindest 105 mm = 3,5×w bei 2 Schalen, w=30) und lehnt ab.
    """
    # Hantel: zwei 200×200-Felder, verbunden durch einen 60-mm-Steg (x=200..260, y=70..130)
    dumbbell_xy = [
        (0, 0), (200, 0), (200, 70), (260, 70), (260, 0), (460, 0),
        (460, 200), (260, 200), (260, 130), (200, 130), (200, 200), (0, 200),
    ]
    height = 900.0
    mesh_tri = _prism_mesh(dumbbell_xy, height)
    verts = np.asarray(mesh_tri.vertices)
    wall = WallData(
        global_id="DUMBBELL00000000000000",
        name="Hantelwand-E2E",
        load_bearing=False,
        is_external=None,
        opening_count=0,
        vertices_mm=verts,
        faces=np.asarray(mesh_tri.faces),
        geometry=analyze_wall_mesh(verts),
    )
    candidate = evaluate_wall(wall, STRAND_WINDOW, ROBOT)
    fp = next(c for c in candidate.checks if c.check == "footprint")
    assert not fp.passed, f"Footprint-Check hätte fehlschlagen sollen; Grund: {fp.reason}"
    assert "Steg" in (fp.reason or "") and "105" in (fp.reason or "")

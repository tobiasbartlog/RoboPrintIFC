"""E1-Regeln als Registry (ADR-013) — Stufe 1 und Stufe 2.

Jede Regel ist eine kleine Funktion `(EligibilityContext) -> CheckResult`.
Neue Regeln: Funktion schreiben, in STAGE1_RULES eintragen — sonst nichts.
Stufe-2-Regeln (thickness, footprint) tragen die S4-Grenzwerte, laufen aber
provisional, solange die Strangbreite fehlt (S1 offen) bzw. keine
Grundriss-Quelle angebunden ist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shapely.geometry import Polygon

from fgc.domain.models import CheckResult
from fgc.domain.process_params import ProcessWindow
from fgc.domain.robot import RobotDef
from fgc.eligibility import footprint
from fgc.ifc_io.walls import WallData


@dataclass(frozen=True)
class EligibilityContext:
    wall: WallData
    window: ProcessWindow
    robot: RobotDef
    #: Grundriss-Polygon der Wand (Welt-XY, mm) für die Stufe-2-Geometrieprüfung.
    #: v1-Wände tragen keinen Grundriss (WallData hat nur Skalare) — dann läuft
    #: check_footprint provisional durch, s. Design-Log 2026-07-02.
    footprint: Polygon | None = None


Rule = Callable[[EligibilityContext], CheckResult]


def check_planarity(ctx: EligibilityContext) -> CheckResult:
    g = ctx.wall.geometry
    if g.is_planar:
        return CheckResult("planarity", passed=True)
    return CheckResult(
        "planarity",
        passed=False,
        reason=(
            f"nicht planar: max. Abweichung {g.planarity_deviation_mm:.1f} mm "
            "von den Wandflächen (v1 nur ebene Wände, ADR-005)"
        ),
    )


def check_load_bearing(ctx: EligibilityContext) -> CheckResult:
    lb = ctx.wall.load_bearing
    if lb is None:
        return CheckResult(
            "load_bearing",
            passed=True,
            provisional=True,
            reason="Pset_WallCommon.LoadBearing fehlt im Modell — als nichttragend angenommen",
        )
    if lb:
        return CheckResult(
            "load_bearing", passed=False, reason="LoadBearing=true (Scope: nichttragend)"
        )
    return CheckResult("load_bearing", passed=True)


def check_openings(ctx: EligibilityContext) -> CheckResult:
    n = ctx.wall.opening_count
    if n == 0:
        return CheckResult("openings", passed=True)
    return CheckResult(
        "openings",
        passed=False,
        deferred=True,
        reason=f"{n} Öffnung(en) — v1 druckt nur öffnungslose Wände (OD-3), später",
    )


def check_workspace(ctx: EligibilityContext) -> CheckResult:
    g, r = ctx.wall.geometry, ctx.robot
    problems = []
    if g.height_mm > r.max_print_height_mm:
        problems.append(f"Höhe {g.height_mm:.0f} mm > {r.max_print_height_mm:.0f} mm")
    if g.length_mm > r.max_print_length_mm:
        problems.append(f"Länge {g.length_mm:.0f} mm > {r.max_print_length_mm:.0f} mm")
    if problems:
        return CheckResult(
            "workspace",
            passed=False,
            provisional=r.workspace_provisional,
            reason=f"außerhalb Arbeitsraum {r.name}: " + ", ".join(problems),
        )
    return CheckResult("workspace", passed=True, provisional=r.workspace_provisional)


def _derived_thickness_min_mm(w: ProcessWindow) -> float | None:
    """Untere Dickengrenze aus Strangbreite × Schalenlogik (S4-Stegformel).

    Eine Wand der Dicke t verhält sich beim Innen-Offset wie ein gerader Steg:
    n Schalen bestehen, sobald t ≥ (2n−1)×w. Die Karte trägt in
    min_web_width_strand_widths bereits den 1-Schalen-Wert inkl. Sicherheitsmarge
    (1.5×w = (2·1−1)+0.5); je weitere Schale +2×w. None, solange S1 die
    Strangbreite nicht geliefert hat.
    """
    if w.strand_width_mm is None or w.min_web_width_strand_widths is None:
        return None
    return footprint.min_web_width_mm(
        w.strand_width_mm, w.min_web_width_strand_widths, w.default_shells
    )


def check_thickness(ctx: EligibilityContext) -> CheckResult:
    """Wanddicke im Prozessfenster (E1-Stufe 2).

    Explizite mm-Grenzen aus der Karte haben Vorrang. Fehlt die Untergrenze, wird
    sie aus Strangbreite × Schalenlogik abgeleitet (S4). Ohne beides läuft der
    Check provisional durch — das heutige Verhalten, bis S1 die Strangbreite liefert.
    """
    w, t = ctx.window, ctx.wall.geometry.thickness_mm
    lo = w.wall_thickness_min_mm
    hi = w.wall_thickness_max_mm
    derived_lo = _derived_thickness_min_mm(w) if lo is None else None
    if lo is None:
        lo = derived_lo

    if lo is None and hi is None:
        return CheckResult(
            "thickness",
            passed=True,
            provisional=True,
            reason="Prozessfenster unbelegt (S1-Strangbreite offen) — Dickenprüfung übersprungen",
        )

    problems = []
    if lo is not None and t < lo:
        if derived_lo is not None:
            factor = footprint.min_web_width_factor(w.min_web_width_strand_widths, w.default_shells)
            problems.append(
                f"Dicke {t:.0f} mm < Mindestdicke {lo:.0f} mm "
                f"(= {factor:.1f}×w bei w={w.strand_width_mm:.0f} mm, "
                f"{w.default_shells} Schalen, S4-Stegformel)"
            )
        else:
            problems.append(f"Dicke {t:.0f} mm < Mindestdicke {lo:.0f} mm (Prozessfenster)")
    if hi is not None and t > hi:
        problems.append(f"Dicke {t:.0f} mm > Maximaldicke {hi:.0f} mm (Prozessfenster)")

    if problems:
        return CheckResult(
            "thickness", passed=False, provisional=w.provisional, reason="; ".join(problems)
        )
    return CheckResult("thickness", passed=True, provisional=w.provisional)


def check_footprint(ctx: EligibilityContext) -> CheckResult:
    """Grundriss-Geometrie (E1-Stufe 2): Mindest-Innenwinkel und Mindeststegbreite (S4).

    Braucht ein Grundriss-Polygon. WallData liefert es in v1 nicht (nur Skalare),
    die v1-Wände sind ebene, öffnungslose Rechtecke ohne spitze Ecken/Stege
    (ADR-005) — ohne Polygon läuft der Check daher provisional durch. Sobald eine
    Grundriss-Quelle angebunden ist (ctx.footprint), greifen die Prüfungen scharf.
    """
    poly = ctx.footprint
    if poly is None:
        return CheckResult(
            "footprint",
            passed=True,
            provisional=True,
            reason=(
                "kein Grundriss-Polygon verfügbar — v1-Wände sind ebene, öffnungslose "
                "Rechtecke ohne spitze Ecken/Stege (ADR-005); Prüfung greift, sobald "
                "eine Grundriss-Quelle angebunden ist"
            ),
        )

    w = ctx.window
    problems = []
    # Winkel: strangbreitenunabhängig, scharf sobald die Karte den Grenzwert trägt.
    # Halbes Grad Toleranz gegen Tessellierungs-/Rundungsrauschen (der Grenzfall
    # 30° soll bestehen, nicht an Fließkomma-Ungenauigkeit scheitern).
    if w.min_convex_angle_deg is not None:
        angle = footprint.min_convex_interior_angle_deg(poly)
        if angle is not None and angle < w.min_convex_angle_deg - 0.5:
            problems.append(
                f"spitzeste konvexe Ecke {angle:.0f}° < {w.min_convex_angle_deg:.0f}° "
                "(Offset schneidet die Spitze ab, S4)"
            )
    # Steg: braucht die Strangbreite (S1). Fehlt sie, bleibt dieser Teil provisional.
    web_provisional = True
    if w.strand_width_mm is not None and w.min_web_width_strand_widths is not None:
        web_provisional = False
        if footprint.has_narrow_web(
            poly,
            w.strand_width_mm,
            w.min_web_width_strand_widths,
            w.default_shells,
            w.mitre_limit,
        ):
            smin = footprint.min_web_width_mm(
                w.strand_width_mm, w.min_web_width_strand_widths, w.default_shells
            )
            problems.append(
                f"Grundriss hat einen Steg schmaler als {smin:.0f} mm "
                f"({w.default_shells} Schalen, S4-Stegformel)"
            )

    if problems:
        return CheckResult(
            "footprint", passed=False, provisional=w.provisional, reason="; ".join(problems)
        )
    return CheckResult("footprint", passed=True, provisional=web_provisional or w.provisional)


#: Auswertereihenfolge = Reihenfolge im Bericht.
STAGE1_RULES: tuple[Rule, ...] = (
    check_planarity,
    check_load_bearing,
    check_openings,
    check_workspace,
    check_thickness,
    check_footprint,
)

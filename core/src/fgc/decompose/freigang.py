"""Freigang-Kriterium: druckbare Tiefe aus Wanddicke + Endeffektor-Geometrie (Issue #163).

**Stufe 1 des Zerlegungs-Constraints** (Karte #139, Entscheidung #141, Scheibe 2).
Ein reines, tiefes Domänen-Modul (wie :mod:`fgc.decompose.limits`): aus **Wanddicke**,
der **freien Länge unter dem Handgelenk** ``L`` (der schlanke Nozzle-/Werkzeug-Überstand)
und dem **Handgelenk-/Unterarm-Radius** ``R`` leitet es die **druckbare Tiefe von einer
Seite** ``D`` ab und stellt **ausschließlich Unmöglichkeit** fest: ist die Wand dicker
als ``D``, kann sie von einer Seite (Düse nach unten) nicht gedruckt werden — Befund
„Wand zu dick für einseitigen Druck". **Befund, kein Gate** (ADR-013): der Befund
blockiert nie, er benennt Hebel und **erspart** die teure verdünnte Kollisionssuche
(Scheibe 2, :func:`fgc.collision.finding.check_part_clearance`) in dem klaren Fall.

**Fehlerrichtung ist das Kernkriterium (S6-Lehre).** Billige Checks irren gefährlich in
Richtung „frei"; dieses Kriterium darf nur „unmöglich" sagen, **wenn es sicher ist**.
Deshalb ist ``D`` bewusst eine **großzügige Obergrenze** der real druckbaren Tiefe:
solange ``dicke ≤ D`` bleibt der Befund stumm (keine Behauptung), erst ``dicke > D``
(die Wand ist dicker als der großzügigste einseitige Reichweitenschätzwert) ist ein
**sicherer** Unmöglichkeits-Befund. Ein falsches „unmöglich" ist damit ausgeschlossen,
solange ``L`` und ``R`` großzügig (nach oben) geschätzt sind.

**Geometriemodell (vereinfacht, s. Design-Log 2026-07-10).** Die Düse druckt
senkrecht von einer Seite; unter dem Handgelenk hängt eine **schlanke Säule** der
freien Länge ``L`` (Flansch + Werkzeug-Überstand), darüber sitzt das bauchige
**Handgelenk/der Unterarm** als Zylinder mit Radius ``R``. Der Arm greift über die
obere Nahkante des bereits gedruckten Wandmaterials; das Handgelenk darf diese Kante
gerade streifen (sein Mittelpunkt steht dann ``R`` hinter der Kante), die schlanke
Säule reicht ``L`` tiefer. Der **tiefste** von einer Seite erreichbare Druckpunkt liegt
damit **höchstens** bei ``D = L + R`` von der Nahfläche. Das Modell **ignoriert
bewusst** die Armglieder (Ober-/Unterarm, Ellbogen — Glied 1–3), deren Eintauchen der
**volle** Befund (`find_collisions`) fängt: es unter-erkennt Unmöglichkeit (sichere
Richtung), statt sie über-zu-behaupten. Weitere Vereinfachungen: senkrechte Düse
(kein Kipp), Handgelenk als Rotationskörper, Flansch+Werkzeug als schlanke Säule,
gerader Übergriff, kein Bezug zur Wandhöhe.

Deterministisch, ohne I/O (der Aufrufer reicht ``L`` und ``R`` herein); Einheiten
nach ADR-006 (Millimeter). Die Ableitung von ``L`` aus dem Endeffektor und der
provisorische ``R`` leben in :func:`free_length_under_wrist_mm` /
:data:`DEFAULT_WRIST_RADIUS_MM`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fgc.domain.tool import ToolDef

#: Rundung (mm) für den deterministischen, byte-stabilen Befund — wie die Modulgrenzen.
ROUND_DECIMALS = 3

#: **Provisorischer** Handgelenk-/Unterarm-Radius ``R`` (mm), bis eine gemessene bzw.
#: aus der Roboter-Geometrie abgeleitete Zahl ihn ersetzt (Revisionstrigger). Grob aus
#: der Kollisions-Hülle des Doosan M1013 (Glieder 4/5, Querschnitts-Halbbreite ~55 mm);
#: **großzügig nach oben** gewählt, damit ``D = L + R`` eine sichere Obergrenze bleibt
#: und kein falsches „unmöglich" entsteht (Fehlerrichtung, S6). Der Aufrufer kann ihn
#: übersteuern, sobald ein besserer Wert vorliegt.
DEFAULT_WRIST_RADIUS_MM = 60.0

#: Benannte Hebel des Befunds „Wand zu dick" (Karte #139 / Entscheidung #141): der
#: Nutzer wendet sie **manuell** an — der Befund blockiert nie (kein Gate, ADR-013).
LEVERS_TOO_THICK: tuple[str, ...] = (
    "Tiefenteilung (in der Dicke schneiden, Slicing-Option #142)",
    "längerer Endeffektor (größere freie Länge unter dem Handgelenk)",
    "höhere Aufstellung / beidseitiger Druck",
)

#: Verbindbarkeits-Winkelschranke ``φ_max^conn`` (rad) = 45° (Stamatopoulos et al.,
#: ICRA 2024, Gl. 8): die Faustregel „50 % Schicht-Überlappung an der Fuge". Konstant
#: (kein Endeffektor-Parameter) und die eine Obergrenze, die für schlanke Endeffektoren
#: (``L`` ≫ ``R``) die Sampling-Schranke Gl. 9 dominiert.
PHI_MAX_CONN_RAD = math.pi / 4

#: Benannte Hebel des Befunds „Teil zu hoch für die verbleibende freie Länge"
#: (Issue #209, PRD #183 AP-2): analog zu :data:`LEVERS_TOO_THICK`, manuell — kein Gate.
LEVERS_TOO_TALL: tuple[str, ...] = (
    "Höhenteilung (in der Höhe schneiden, niedrigere Teile)",
    "längerer Endeffektor (größere freie Länge unter dem Handgelenk)",
    "flachere Aufstellung / anderer Standplatz",
)


def printable_depth_mm(free_length_mm: float, wrist_radius_mm: float) -> float:
    """Druckbare Tiefe von **einer** Seite ``D = L + R`` (mm).

    ``L`` = freie Länge unter dem Handgelenk (schlanker Überstand), ``R`` =
    Handgelenk-/Unterarm-Radius. Bewusst eine **großzügige Obergrenze** der real
    druckbaren Tiefe (Fehlerrichtung „unmöglich nur wenn sicher", S6): negative
    Eingaben werden auf 0 geklemmt (kein negativer Reichweiten-Unsinn).
    """
    return round(max(0.0, float(free_length_mm)) + max(0.0, float(wrist_radius_mm)), ROUND_DECIMALS)


def free_length_under_wrist_mm(tool: ToolDef, flange_length_mm: float) -> float:
    """Freie Länge ``L`` (mm) unter dem Handgelenk aus Endeffektor + Flanschlänge.

    ``L = flange_length_mm + ‖tcp_pos‖``: die Strecke Handgelenk (J5) → Flansch
    (``d6``) plus der Abstand Flansch → Düsenspitze (TCP-Position, ADR-006). Nach der
    Dreiecksungleichung ist das eine **Obergrenze** der tatsächlichen Strecke J5 →
    Düsenspitze — großzügig, damit ``D`` sicher nach oben abschätzt (kein falsches
    „unmöglich"). Rein, ohne I/O.
    """
    pos = tool.tcp_frame["pos_mm"]
    tip = math.sqrt(float(pos[0]) ** 2 + float(pos[1]) ** 2 + float(pos[2]) ** 2)
    return round(max(0.0, float(flange_length_mm)) + tip, ROUND_DECIMALS)


@dataclass(frozen=True)
class FreigangCheck:
    """Freigang-Befund einer Wand: druckbare Tiefe vs. Wanddicke — nie ein Gate.

    ``too_thick`` ist strikt ``wall_thickness_mm > printable_depth_mm``: eine Wand
    **exakt auf** der druckbaren Tiefe gilt als (gerade noch) druckbar — kein Befund
    (Fehlerrichtung, S6). ``excess_mm`` = ``max(0, dicke − D)`` ist der Überschuss an
    Dicke, den ein einseitiger Druck nicht mehr erreicht (0, solange nicht zu dick).
    ``levers`` benennt die Hebel **nur** im Befund-Fall (sonst leer).
    """

    wall_thickness_mm: float
    free_length_mm: float
    wrist_radius_mm: float
    printable_depth_mm: float
    too_thick: bool
    excess_mm: float
    levers: tuple[str, ...] = ()
    #: **Vorläufigkeit** des einfließenden Werkzeug-TCP (Issue #177, Befund B9). ``True``
    #: = die freie Länge ``L`` wurde aus einem **geschätzten**, noch nicht am Gerät
    #: vermessenen TCP-Versatz gerechnet (``ToolDef.tcp_provisional``, #136). Ein zu klein
    #: geschätzter TCP verkleinert ``D`` und könnte eine real druckbare Wand fälschlich als
    #: „zu dick" melden — das Urteil ist damit **nie eine geprüfte Gewissheit**, solange der
    #: TCP provisorisch ist (der Modul-Export misstraut provisorischen TCP bereits). Additiv;
    #: nur ``True`` wird serialisiert (Altläufe/bestätigter TCP bleiben byte-gleich).
    tcp_provisional: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "wall_thickness_mm": self.wall_thickness_mm,
            "free_length_mm": self.free_length_mm,
            "wrist_radius_mm": self.wrist_radius_mm,
            "printable_depth_mm": self.printable_depth_mm,
            "too_thick": self.too_thick,
            "excess_mm": self.excess_mm,
            "levers": list(self.levers),
        }
        # Nur bei provisorischem TCP schreiben (Issue #177) — bestätigter TCP/Altläufe
        # bleiben byte-gleich (additiv, wie die Optionalfelder der Druckbarkeit).
        if self.tcp_provisional:
            d["tcp_provisional"] = True
        return d


def check_freigang(
    wall_thickness_mm: float,
    *,
    free_length_mm: float,
    wrist_radius_mm: float = DEFAULT_WRIST_RADIUS_MM,
    tcp_provisional: bool = False,
) -> FreigangCheck:
    """Freigang-Kriterium einer Wand: ist sie zu dick für einseitigen Druck? (Issue #163).

    Rein, deterministisch: druckbare Tiefe ``D = L + R`` (:func:`printable_depth_mm`)
    gegen die Wanddicke. ``too_thick`` strikt ``>`` (exakt auf ``D`` ist druckbar,
    kein Befund — Fehlerrichtung „unmöglich nur wenn sicher", S6). Nur im Befund-Fall
    trägt ``levers`` die benannten Hebel (Tiefenteilung #142, längerer Endeffektor,
    höhere Aufstellung). **Befund, kein Gate** (ADR-013): blockiert nie.

    ``tcp_provisional`` (Issue #177, Befund B9) reicht durch, ob die freie Länge ``L``
    aus einem **geschätzten** TCP gerechnet wurde (noch nicht am Gerät vermessen). Es
    ändert das ``too_thick``-Ergebnis **nicht** (die Rechnung bleibt gleich), markiert
    den Befund aber als **vorläufig** — der Aufrufer darf ihn dann nicht als geprüfte
    Gewissheit darstellen. Die eigentliche Höhen-Wache bleibt Issue #167.
    """
    depth = printable_depth_mm(free_length_mm, wrist_radius_mm)
    thickness = round(max(0.0, float(wall_thickness_mm)), ROUND_DECIMALS)
    too_thick = thickness > depth
    excess = round(thickness - depth, ROUND_DECIMALS) if too_thick else 0.0
    return FreigangCheck(
        wall_thickness_mm=thickness,
        free_length_mm=round(max(0.0, float(free_length_mm)), ROUND_DECIMALS),
        wrist_radius_mm=round(max(0.0, float(wrist_radius_mm)), ROUND_DECIMALS),
        printable_depth_mm=depth,
        too_thick=too_thick,
        excess_mm=excess,
        levers=LEVERS_TOO_THICK if too_thick else (),
        tcp_provisional=bool(tcp_provisional),
    )


# ===========================================================================
# Zweite Stufe-1-Schranke: „Teil zu hoch für die verbleibende freie Länge"
# (Issue #209, PRD #183 AP-2 — Gratiswissen ausbauen).
#
# Winkelschranken-Muster nach Stamatopoulos et al. (ICRA 2024, Gl. 9,
# ``docs/recherche/2026-07-10-adaption-chunking-literatur.md``):
#
#     φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr)
#
# — die maximal druckbare Neigung aus **Verbindbarkeit** (``φ_max^conn`` = 45°,
# konstant) **und** der **Endeffektor-Geometrie** (``φ_max^extr = arctan(R/L)``:
# der bauchige Handgelenk-Radius ``R`` als Bounding-Box-„Höhe" über der schlanken
# Säule der freien Länge ``L`` als „Länge"). Aus dieser Neigung leitet
# :func:`max_printable_height_mm` eine **großzügige Obergrenze** der druckbaren
# Teilhöhe ``H_max = L·tan(φ_sample)`` ab (geschlossen: ``L²/R`` für schlanke
# Endeffektoren ``L ≥ R``, sonst ``L``) und stellt — wie das Freigang-Kriterium in
# der Tiefe — **ausschließlich Unmöglichkeit** fest: ein Teil, das strikt höher als
# ``H_max`` ist, verlangt eine Neigung jenseits von ``φ_sample``.
#
# **Fehlerrichtung (S6, wie #163) und Grenzen des Modells.** ``H_max`` ist bewusst
# **großzügig** — für den realen M1013 (``L`` ≈ 273 mm, ``R`` = 60 mm) liegt es bei
# ``L²/R`` ≈ 1250 mm und fängt nur Teile weit jenseits der Werkzeug-Reichweite; der
# Befund bleibt stumm, solange ``höhe ≤ H_max``. Physikalisch ist die Teilhöhe **nicht
# hart** durch die Werkzeuggeometrie begrenzt (der Roboter setzt je Schicht um) — die
# Schranke ist darum eine **konservative, platzierungsblinde Vermutung** (``presumed``
# in der Druckbarkeit), kein Gate und keine geprüfte Gewissheit: ein ratschlagender
# Befund „für einen Guss zu hoch → in der Höhe teilen" (Hebel Höhenteilung). Die teure
# Prüf-Tür bleibt der eigentliche Richter und **überstimmt** die Vermutung (Stufe 2).
# ``H_max`` wächst monoton mit ``L`` (großzügig-hohe freie Länge erzeugt nie ein neues
# „zu hoch"); ein größeres ``R`` **senkt** ``H_max`` (bauchiges Handgelenk = weniger
# vertikaler Freigang) — der ``R``-Default ist darum bewusst moderat gehalten. Fehlt
# die freie Länge (``L ≤ 0``), schweigt die Schranke (fail-soft, nie ein geratenes „zu
# hoch"). Deterministisch, ohne I/O; Einheiten in Millimeter/Grad (ADR-006).
# ===========================================================================


def sample_angle_rad(free_length_mm: float, wrist_radius_mm: float) -> float:
    """Maximal druckbare Neigung ``φ_max^sample`` (rad) nach Gl. 9 (Stamatopoulos).

    ``φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr)`` mit ``φ_max^conn`` = 45°
    (:data:`PHI_MAX_CONN_RAD`) und ``φ_max^extr = arctan(R/L)`` aus der Endeffektor-
    Bounding-Box (Handgelenk-Radius ``R`` als „Höhe" über der freien Länge ``L`` als
    „Länge"). Für schlanke Endeffektoren (``L ≫ R``) ist ``φ_max^extr`` klein und
    dominiert Gl. 9 (große ``φ_max^sample`` ⇒ großzügige druckbare Höhe); ein bauchiges
    Handgelenk (``R > L``) läuft in die 45°-Verbindbarkeitsschranke. Eingaben geklemmt.
    """
    ell = max(0.0, float(free_length_mm))
    rad = max(0.0, float(wrist_radius_mm))
    # arctan(R/L) über atan2 (robust bei L = 0 → π/2); R = L = 0 ⇒ 0.
    phi_extr = math.atan2(rad, ell)
    return math.pi / 2 - min(PHI_MAX_CONN_RAD, phi_extr)


def max_printable_height_mm(free_length_mm: float, wrist_radius_mm: float) -> float:
    """Großzügige Obergrenze der druckbaren Teilhöhe ``H_max = L·tan(φ_max^sample)`` (mm).

    Aus der Winkelschranke :func:`sample_angle_rad` und der freien Länge ``L``;
    geschlossen ``L²/R`` (schlank, ``L ≥ R``) bzw. ``L`` (bauchig, ``L < R``). Bewusst
    eine **großzügige Obergrenze** (Fehlerrichtung „unmöglich nur wenn sicher", S6):
    monoton wachsend in ``L``. Fehlt die freie Länge (``L ≤ 0``), gibt es **keine**
    endliche Höhen-Schranke (``inf`` ⇒ nie „zu hoch"): lieber schweigen als raten.
    ``inf`` bleibt intern (nicht serialisiert).
    """
    ell = max(0.0, float(free_length_mm))
    if ell <= 0.0:
        return math.inf
    phi = sample_angle_rad(free_length_mm, wrist_radius_mm)
    tan = math.tan(phi)
    if not math.isfinite(tan) or tan <= 0.0:
        return math.inf
    return round(ell * tan, ROUND_DECIMALS)


@dataclass(frozen=True)
class TeilhoeheCheck:
    """Höhen-Befund **eines** Teils: Teilhöhe vs. druckbare Höhe — nie ein Gate.

    ``too_tall`` ist strikt ``part_height_mm > max_printable_height_mm``: ein Teil
    **exakt auf** der druckbaren Höhe gilt als (gerade noch) druckbar — kein Befund
    (Fehlerrichtung, S6). ``excess_mm`` = ``max(0, höhe − H_max)`` ist der Höhen-
    Überschuss, ``excess_deg`` der Winkel-Überschuss ``max(0, φ_req − φ_sample)`` in
    **Grad** (US 4): die vom Teil geforderte Neigung ``φ_req = arctan(höhe/L)`` über
    der zulässigen ``φ_sample``. Beide sind 0, solange nicht zu hoch. ``levers``
    benennt die Hebel **nur** im Befund-Fall (sonst leer).
    """

    part_height_mm: float
    free_length_mm: float
    wrist_radius_mm: float
    sample_angle_deg: float
    max_printable_height_mm: float
    too_tall: bool
    excess_mm: float
    excess_deg: float
    levers: tuple[str, ...] = ()


def check_teilhoehe(
    part_height_mm: float,
    *,
    free_length_mm: float,
    wrist_radius_mm: float = DEFAULT_WRIST_RADIUS_MM,
) -> TeilhoeheCheck:
    """Zweite Stufe-1-Schranke (Issue #209): ist ein Teil zu hoch für die freie Länge?

    Rein, deterministisch: die druckbare Höhe ``H_max`` (:func:`max_printable_height_mm`,
    Gl. 9) gegen die Teilhöhe. ``too_tall`` strikt ``>`` (exakt auf ``H_max`` ist
    druckbar, kein Befund — Fehlerrichtung „unmöglich nur wenn sicher", S6). Der
    Überschuss wird **doppelt** ausgewiesen (US 4): ``excess_mm`` (Höhe) und
    ``excess_deg`` (Neigungswinkel). Nur im Befund-Fall trägt ``levers`` die benannten
    Hebel. **Befund, kein Gate** (ADR-013): blockiert nie; fehlt die freie Länge
    (``L ≤ 0``), schweigt die Schranke (fail-soft).
    """
    ell = round(max(0.0, float(free_length_mm)), ROUND_DECIMALS)
    rad = round(max(0.0, float(wrist_radius_mm)), ROUND_DECIMALS)
    height = round(max(0.0, float(part_height_mm)), ROUND_DECIMALS)
    phi = sample_angle_rad(ell, rad)
    h_max = max_printable_height_mm(ell, rad)
    too_tall = height > h_max
    if too_tall:
        excess_mm = round(height - h_max, ROUND_DECIMALS)
        # Geforderte Neigung φ_req = arctan(höhe/L); Überschuss = φ_req − φ_sample.
        phi_req = math.atan2(height, ell) if ell > 0.0 else math.pi / 2
        excess_deg = round(math.degrees(phi_req - phi), ROUND_DECIMALS)
    else:
        excess_mm = 0.0
        excess_deg = 0.0
    # ``inf`` (keine Schranke) nie serialisieren — als 0.0 ausweisen (kein Befund).
    h_max_out = 0.0 if not math.isfinite(h_max) else h_max
    return TeilhoeheCheck(
        part_height_mm=height,
        free_length_mm=ell,
        wrist_radius_mm=rad,
        sample_angle_deg=round(math.degrees(phi), ROUND_DECIMALS),
        max_printable_height_mm=h_max_out,
        too_tall=too_tall,
        excess_mm=excess_mm,
        excess_deg=excess_deg,
        levers=LEVERS_TOO_TALL if too_tall else (),
    )

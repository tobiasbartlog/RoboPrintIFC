/**
 * Effektive-Platzierung-Selektor (Issue #171, Befunde B17/B19/B21/B22/B23 der
 * Constraint-Serie-Zwischenkritik 2026-07-10).
 *
 * **Eine** reine Lesequelle für alle Platzierungs-Leser des Viewers. Vor #171
 * leiteten mindestens sechs Lesepfade die Platzierung je auf eigene Faust ab —
 * die meisten aus der (ggf. veralteten) Zerlegungs-Platzierung OHNE die aktiven
 * Overrides des Jobs; nur der Modul-Replay am Druckort war per Bauart an die
 * frische Quelle (den Sim-Lauf) gebunden (#161). Folge: Basis-Marker, Fokus-Arm,
 * Basis-Chips, Vorbereiten-3D (inkl. Sicherheitsurteil) und die statische
 * Druckort-Ansicht konnten dauerhaft zur ALTEN Platzierung urteilen, während der
 * Arm schon an der neuen stand (B17/B19/B21).
 *
 * Dieser Selektor macht die Einquelligkeit **per Bauart**: die Leser rufen
 * ausschließlich {@link effectivePlacement} (skalare Lage am Einbauort) bzw.
 * {@link effectiveModuleFrame} (Frame-Lage am Druckort) — sie halten keinen
 * eigenen Override-/Lauf-Merge mehr. Reine Ableitung aus Zerlegungslauf,
 * Modul-Lauf und aktiven Overrides — **kein neuer Zustand** (ADR-007): der
 * Selektor rechnet nur, er persistiert nichts.
 */

import type { Frame, SectionOverride } from "../api/projects";

/** Die skalaren Platzierungsfelder, die die Einbauort-Leser brauchen (mm/rad). */
export interface PlacementScalars {
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
  yaw_rad?: number;
}

/** Effektive skalare Platzierung — alle vier Felder aufgelöst (yaw defaultet 0). */
export interface EffectivePlacement {
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
  yaw_rad: number;
}

/**
 * Effektive **skalare** Platzierung eines Teils am Einbauort: die
 * Zerlegungs-Platzierung, feldweise übersteuert durch die **gesetzten
 * (endlichen) freien Felder** eines aktiven `section_overrides`-Eintrags
 * (Issue #94/#161). Eine reine `option_id`-Referenz (Issue #25) ohne freie
 * Werte ändert nichts (ihre Werte kennt nur der Core, ADR-007); nicht-endliche
 * Override-Werte übersteuern nie. `yaw_rad` kommt weiter aus der Zerlegung
 * (Overrides tragen kein yaw). Reine Funktion, deterministisch.
 *
 * Genau dies ist die eine Naht, durch die alle Einbauort-Leser die Platzierung
 * beziehen — Basis-Marker, Fokus-Arm, Basis-Chips, Vorbereiten-3D (Bahn +
 * Sicherheitsurteil), Wand-Gesamtablauf-Basis-Marker und die Modul-Karten.
 */
export function effectivePlacement(
  placement: PlacementScalars,
  override?: SectionOverride,
): EffectivePlacement {
  const pick = (field: "lateral_mm" | "standoff_mm" | "stand_height_mm"): number => {
    const v = override?.[field];
    return typeof v === "number" && Number.isFinite(v) ? v : placement[field];
  };
  return {
    lateral_mm: pick("lateral_mm"),
    standoff_mm: pick("standoff_mm"),
    stand_height_mm: pick("stand_height_mm"),
    yaw_rad: placement.yaw_rad ?? 0,
  };
}

/**
 * Effektive **Frame**-Lage eines Moduls am Druckort: die Platzierung des
 * **Sim-Laufs** (`trajectory.meta.base_frame`, hier bereits in Workstation-
 * Koordinaten umgerechnet) gewinnt, sobald ein frischer Lauf existiert — sie ist
 * das, womit die spätere Simulation wirklich rechnet und mit dem der Arm-Replay
 * läuft (#161). Fehlt sie (kein Lauf / Altlauf ohne das Feld), gilt die
 * Zerlegungs-Lage (`module_pose.workstation`, verbatim). Gibt es beides nicht,
 * `null` (der Aufrufer zeigt dann einen Hinweis, Befund kein Gate).
 *
 * Damit beziehen statische Druckort-Ansicht UND Replay-Bühne die Modul-Lage aus
 * derselben Regel — kein Umspringen des Soll-Kastens beim Replay-Start (B19).
 * Reine Funktion.
 */
export function effectiveModuleFrame(input: {
  runFrame: Frame | null | undefined;
  decompositionFrame: Frame | null | undefined;
}): Frame | null {
  return input.runFrame ?? input.decompositionFrame ?? null;
}

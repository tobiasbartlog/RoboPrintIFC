/**
 * Druckort-Ansicht — reiner View-State des Ansichts-Umschalters
 * Einbauort ↔ Druckort (Druckplan-Neuordnung II S8, Issue #96, PRD #88,
 * ADR-022). DOM-frei und ohne three.js (Hausmuster wie `focus-store.ts` /
 * `zerlegungsart-state.ts`): hier liegt nur die Umschalt-Logik — *wann* der
 * Umschalter existiert und *welche* Ansicht gilt; das Umblenden der Szene
 * (Workstation-Mesh, Roboter an `robot_base_frame`, Modul-Rechteck) erledigt
 * `main.ts` mit den reinen Szenen-Spec-Funktionen aus `render/druckort-spec.ts`.
 *
 * Regeln (viewer/CONTEXT.md „Druckort-Ansicht", ADR-022):
 * - Der Umschalter existiert **nur am fokussierten Modul** (Zerlegungsart
 *   „modul" + gesetzter Fokus). Bei **Abschnitten entfällt er** — Einbauort
 *   *ist* der Druckort (in place gedruckt).
 * - Fällt die Voraussetzung weg (Fokus gelöst, Artwechsel, Teil verschwunden),
 *   fällt die Ansicht sauber auf „einbauort" zurück (`reconcileDruckortView`).
 */

import type { Zerlegungsart } from "./zerlegungsart-state";

/** Die zwei Ansichten des fokussierten Moduls (viewer/CONTEXT.md). */
export type DruckortView = "einbauort" | "druckort";

export interface DruckortState {
  /** Die aktive Ansicht; „einbauort" ist der abwärtskompatible Ausgangszustand. */
  view: DruckortView;
}

/** Ausgangszustand: Einbauort (die bestehende Wand-Ansicht). */
export function initDruckortState(): DruckortState {
  return { view: "einbauort" };
}

/**
 * Existiert der Umschalter? Nur bei Zerlegungsart „modul" UND fokussiertem
 * Teil (Issue #96) — bei Abschnitten ist Einbauort = Druckort, ohne Fokus
 * gibt es kein „dieses Modul", dessen Druckort gezeigt werden könnte.
 */
export function druckortAvailable(
  kind: Zerlegungsart,
  focusedSectionId: string | null,
): boolean {
  return kind === "modul" && focusedSectionId !== null;
}

/**
 * Nutzerwahl anwenden: „druckort" ist nur wählbar, wenn der Umschalter
 * existiert — sonst bleibt (bzw. wird) es „einbauort". Rein, gibt bei
 * unveränderter Ansicht denselben Zustand zurück.
 */
export function selectDruckortView(
  state: DruckortState,
  view: DruckortView,
  kind: Zerlegungsart,
  focusedSectionId: string | null,
): DruckortState {
  const next: DruckortView =
    view === "druckort" && druckortAvailable(kind, focusedSectionId)
      ? "druckort"
      : "einbauort";
  return next === state.view ? state : { view: next };
}

/**
 * Gleicht die Ansicht mit den Voraussetzungen ab: verschwindet der Modul-Fokus
 * (Fokus gelöst, Artwechsel auf „abschnitt", Teil weg nach Neubewertung),
 * fällt eine aktive Druckort-Ansicht sauber auf „einbauort" zurück — nie eine
 * verwaiste Workstation-Szene ohne Modul.
 */
export function reconcileDruckortView(
  state: DruckortState,
  kind: Zerlegungsart,
  focusedSectionId: string | null,
): DruckortState {
  if (state.view === "druckort" && !druckortAvailable(kind, focusedSectionId)) {
    return { view: "einbauort" };
  }
  return state;
}

/** true, wenn gerade die Druckort-Ansicht aktiv ist. */
export function isDruckort(state: DruckortState): boolean {
  return state.view === "druckort";
}

/**
 * Rückkehr-Kamerastand für einen Modul-Replay (Issue #137). Der Replay blendet
 * auf den Druckort um; sein Rückweg muss die Ansicht **vor** dem Replay
 * wiederherstellen (die Wand-Ansicht) — nicht die Druckort-Kamera.
 *
 * Regel: Liegt bereits ein Stash vor (`existing` ≠ null), sind wir schon am
 * Druckort (per Umschalter betreten oder laufender Replay) — DER trägt die
 * Wand-Ansicht und wird durchgereicht; die aktuelle Kamera zeigt dann längst
 * den Druckort und wäre die falsche Rückkehr. Erst ohne Stash (frisch aus der
 * Wand-Ansicht) *ist* die aktuelle Kamera die Wand-Ansicht — nur dann wird sie
 * per `snapshotCurrent` festgehalten (der Snapshot darf sonst nicht laufen).
 *
 * Generisch + DOM-/three.js-frei gehalten (Hausmuster dieses Moduls): das
 * konkrete Kamera-Objekt und das Klonen liefert `main.ts`.
 */
export function resolveReplayReturnCamera<T>(
  existing: T | null,
  snapshotCurrent: () => T,
): T {
  return existing ?? snapshotCurrent();
}

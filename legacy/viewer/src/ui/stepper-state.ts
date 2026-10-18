/**
 * Stepper des Header-Prozessbandes (UI-Redesign Scheibe 2, Issue #102) — reine,
 * DOM-freie Ableitung der Schritt-Ansicht. Wie die anderen `*-state.ts`
 * (z. B. `collapsible-state.ts`, `theme.ts`) trennt dieses Modul die
 * Zustandslogik vom DOM: aus einer **erweiterbaren** Schrittliste plus dem je
 * Schritt geltenden Staleness-Zustand und dem aktiven Reiter leitet
 * `stepperView` die Größen ab, die die Verdrahtung (`ui/shell.ts`) am Header
 * setzt (aktiver Chip, Punktfarbe, Tooltip, „›"-Trenner).
 *
 * Die Punktfarbe kommt AUSSCHLIESSLICH aus der bestehenden Staleness-Ableitung
 * (`ui/staleness.ts` / `output_status`) — hier wird nichts neu gerechnet: ein
 * Schritt bindet über sein optionales `output` an eine Output-Stufe; Schritte
 * ohne Output (Projekt, Roboter — Eingabestufen, keine veraltbaren Ausgaben)
 * gelten stets als aktuell. Aktiver Schritt = Akzent, veraltet = amber (warn),
 * sonst grün (ok). Aktiv sticht Veraltung aus (wie im Prototyp).
 *
 * **Erweiterbar:** Die Schrittliste ist Daten (`PROCESS_STEPS`). Scheibe 4
 * (#106) spaltet den früheren einen „Druckplan"-Schritt auf: „Zerlegung"
 * (eigener Reiter `zerlegung`, bindet an die Output-Stufe `druckplan` =
 * Platzierung/Zerlegung) plus übergangsweise „Slicing" (noch der bisherige
 * Reiter `druckplan`, bindet an `simulation`); #107 (Scheibe 5) löst den
 * Slicing-Reiter endgültig heraus — ohne Änderung an dieser Logik.
 *
 * Getrennt von DOM getestet (`stepper-state.test.ts`).
 */

import { type OutputName, type StageStatus, isStale } from "./staleness";
import type { TabId } from "./tabs";

/**
 * Ein Prozess-Schritt des Steppers. `tab` ist der Reiter, den ein Klick
 * aktiviert; `output` bindet den Status-Punkt (optional) an eine Output-Stufe
 * der Staleness-Ableitung. Fehlt `output`, gilt der Schritt nie als veraltet.
 */
export interface StepDef {
  id: string;
  label: string;
  tab: TabId;
  output?: OutputName;
}

/**
 * Die Prozess-Schritte (Issue #102, gespalten in Scheibe 4 / #106): fünf
 * Schritte Projekt → Roboter → Zerlegung → Slicing → Export. „Zerlegung"
 * (eigener Reiter `zerlegung`) bindet an die Output-Stufe `druckplan`
 * (Platzierung/Zerlegung — dirty-Kette der Schnittplan-Prüfung); „Slicing"
 * bleibt übergangsweise auf dem bisherigen Reiter `druckplan` und bindet an
 * `simulation` (Prozessparameter/Simulieren). #107 löst den Slicing-Reiter
 * heraus. Die Bibliothek ist bewusst kein Stepper-Schritt (Stammdaten außerhalb
 * des Prozesses — sie wird über das ▤-Icon im Header erreicht).
 */
export const PROCESS_STEPS: StepDef[] = [
  { id: "projekt", label: "Projekt", tab: "projekt" },
  { id: "roboter", label: "Roboter", tab: "roboter" },
  { id: "zerlegung", label: "Zerlegung", tab: "zerlegung", output: "druckplan" },
  { id: "slicing", label: "Slicing", tab: "druckplan", output: "simulation" },
  { id: "export", label: "Export", tab: "export", output: "export" },
];

/** Der Hinweis, dass Reiter freie Navigation sind (kein Zwangspfad). */
export const NAV_NOTE =
  "Reiter sind Navigation, kein Zwangspfad — jeder Schritt ist frei erreichbar.";

/** Die drei Punkt-Zustände eines Schritts (semantisch, nicht CSS). */
export type StepDotKind = "accent" | "stale" | "current";

/** Die CSS-Modifikatorklasse (`.dot.<x>`) zu einem Punkt-Zustand. */
export type StepDotClass = "accent" | "warn" | "ok";

/** Der Staleness-Zustand eines Schritts: seine Output-Stufe oder `"current"`. */
export function stepStatus(
  step: StepDef,
  statuses: Partial<Record<OutputName, StageStatus>>,
): StageStatus {
  if (!step.output) return "current";
  return statuses[step.output] ?? "current";
}

/** Der Punkt-Zustand: aktiv sticht aus (Akzent), sonst veraltet (amber) ↔ aktuell. */
export function stepDotKind(status: StageStatus, isActive: boolean): StepDotKind {
  if (isActive) return "accent";
  return isStale(status) ? "stale" : "current";
}

/** Bildet den Punkt-Zustand auf die `.dot`-Modifikatorklasse ab. */
export function stepDotClass(kind: StepDotKind): StepDotClass {
  switch (kind) {
    case "accent":
      return "accent";
    case "stale":
      return "warn";
    case "current":
      return "ok";
  }
}

/** Der Tooltip eines Schritts — nennt immer die freie Navigation, bei Veraltung zusätzlich den Befund. */
export function stepTooltip(step: StepDef, status: StageStatus): string {
  if (isStale(status)) {
    return `${step.label} veraltet — sichtbar, nicht gelöscht (ADR-017). ${NAV_NOTE}`;
  }
  return NAV_NOTE;
}

/** Die aus einem Schritt abgeleiteten DOM-Größen. */
export interface StepView {
  id: string;
  label: string;
  tab: TabId;
  /** true, wenn der Schritt den aktiven Reiter abbildet (Chip-Darstellung). */
  isActive: boolean;
  /** true für alle außer dem ersten Schritt — der „›"-Trenner steht davor. */
  notFirst: boolean;
  dotKind: StepDotKind;
  dotClass: StepDotClass;
  tooltip: string;
}

/**
 * Leitet die Schritt-Ansichten aus der Schrittliste, den Output-Status (aus
 * `allStageStatuses`) und dem aktiven Reiter ab. Ist die Bibliothek aktiv
 * (kein Stepper-Schritt), ist kein Schritt aktiv — alle Punkte folgen dann der
 * Staleness (Akzent nur bei einem aktiven Prozess-Schritt).
 */
export function stepperView(
  steps: StepDef[],
  statuses: Partial<Record<OutputName, StageStatus>>,
  activeTab: TabId,
): StepView[] {
  return steps.map((step, i) => {
    const status = stepStatus(step, statuses);
    const isActive = step.tab === activeTab;
    const kind = stepDotKind(status, isActive);
    return {
      id: step.id,
      label: step.label,
      tab: step.tab,
      isActive,
      notFirst: i > 0,
      dotKind: kind,
      dotClass: stepDotClass(kind),
      tooltip: stepTooltip(step, status),
    };
  });
}

/**
 * Reine, DOM-freie Logik der Workstation-Wahl (Issue #77, PRD #69).
 *
 * Spiegelt das Split-Muster von `compat.ts`/`tool.ts`: die reine Entscheidung
 * „welche Workstation ist zum aktiven Roboter inkompatibel?" lebt hier, das
 * DOM-Wiring (Option-Klasse, Warn-Element) im `WorkstationPanel` (`ui/workstation.ts`).
 *
 * WIEDERVERWENDUNG (kein zweiter Filter): die eigentliche Kompatibilitäts-Frage
 * beantwortet `isCompatible` aus `compat.ts` — dieselbe reine Funktion, die auch
 * den Endeffektor-Filter (#74) trägt und deckungsgleich zum Core-Modul
 * `domain/compat` ist (Golden-Fälle). Hier bleiben nur die dünnen, workstation-
 * spezifischen Schleifen/Warntexte.
 *
 * Befund, kein Gate (ADR-013): inkompatibel heißt „ausgrauen + warnen", nie
 * „gesperrt".
 */

import type { WorkstationDef } from "../api/projects";
import { isCompatible } from "./compat";

/**
 * Namen aller Workstations, die zum aktiven Roboter **inkompatibel** sind — die im
 * Dropdown ausgegraut (aber wählbar) werden. Ungetaggte/passende bleiben normal.
 * Reine Berechnung über den geteilten `isCompatible`-Filter (#74); das Setzen der
 * CSS-Klasse macht `WorkstationPanel`.
 */
export function incompatibleWorkstationNames(
  workstations: WorkstationDef[],
  activeRobot: string | null,
): Set<string> {
  const out = new Set<string>();
  for (const w of workstations) {
    if (!isCompatible(w.compatible_robots, activeRobot)) out.add(w.name);
  }
  return out;
}

/**
 * Warntext, wenn die **aktuell gewählte** Workstation durch einen Roboterwechsel
 * inkompatibel geworden ist — sonst `null`. Kein Auto-Reset, kein Gate: die
 * Workstation bleibt gewählt, nur der Hinweis erscheint (analog Endeffektor-Warnung).
 */
export function workstationCompatibilityWarning(
  selected: WorkstationDef | null | undefined,
  activeRobot: string | null,
): string | null {
  if (!selected || activeRobot === null) return null;
  if (isCompatible(selected.compatible_robots, activeRobot)) return null;
  return (
    `Kompatibilitäts-Warnung: Workstation „${selected.name}" ist nicht für ` +
    `Roboter „${activeRobot}" freigegeben. Befund — kein Gate; Wahl bleibt bestehen.`
  );
}

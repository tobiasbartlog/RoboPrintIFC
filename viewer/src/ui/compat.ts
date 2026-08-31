/**
 * Kompatibilitaets-Filter im Viewer (Issue #74) — reine, testbare Logik ohne DOM.
 *
 * Spiegel des Core-Moduls ``core/src/fgc/domain/compat.py``: dieselbe Frage,
 * dasselbe Verhalten (Golden-Faelle in `compat.test.ts` gegen `test_compat.py`).
 * Der **Roboter ist die Nabe** (PRD #69); getaggtes Zubehoer verweist auf ihn.
 *
 * Befund, kein Gate (ADR-013): inkompatibel heisst „ausgrauen + warnen", nie
 * „gesperrt". Das DOM-Wiring (Option-Klasse, Warn-Element) liegt in `ToolPanel`
 * (`ui/tool.ts`) — hier bleibt nur die reine Entscheidung (Split-Muster wie
 * `simulation-state`/`cutplan-state`).
 */

import type { ToolDef } from "../api/projects";

/**
 * Passt getaggtes Zubehoer zum aktiven Roboter? Leere/fehlende Tags und ein
 * fehlender aktiver Roboter (`null`) gelten als **unbekannt** = kompatibel
 * (Migrationsschutz). Nur getaggtes Zubehoer ohne den aktiven Roboter in der
 * Liste ist inkompatibel (`false`).
 */
export function isCompatible(
  compatibleRobots: string[] | null | undefined,
  activeRobot: string | null,
): boolean {
  if (!compatibleRobots || compatibleRobots.length === 0) return true;
  if (activeRobot === null) return true;
  return compatibleRobots.includes(activeRobot);
}

/**
 * Namen aller Endeffektoren, die zum aktiven Roboter **inkompatibel** sind — die
 * im Dropdown ausgegraut (aber wählbar) werden. Ungetaggte/passende bleiben
 * normal. Reine Berechnung; das Setzen der CSS-Klasse macht `ToolPanel`.
 */
export function incompatibleToolNames(
  tools: ToolDef[],
  activeRobot: string | null,
): Set<string> {
  const out = new Set<string>();
  for (const t of tools) {
    if (!isCompatible(t.compatible_robots, activeRobot)) out.add(t.name);
  }
  return out;
}

/**
 * Warntext, wenn der **aktuell gewählte** Endeffektor durch einen
 * Roboterwechsel inkompatibel geworden ist — sonst `null`. Kein Auto-Reset,
 * kein Gate: der Endeffektor bleibt gewählt, nur der Hinweis erscheint (analog
 * Payload-Warnung).
 */
export function compatibilityWarning(
  selected: ToolDef | null | undefined,
  activeRobot: string | null,
): string | null {
  if (!selected || activeRobot === null) return null;
  if (isCompatible(selected.compatible_robots, activeRobot)) return null;
  return (
    `Kompatibilitäts-Warnung: Endeffektor „${selected.name}" ist nicht für ` +
    `Roboter „${activeRobot}" freigegeben. Befund — kein Gate; Wahl bleibt bestehen.`
  );
}

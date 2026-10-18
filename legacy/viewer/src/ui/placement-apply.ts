/**
 * Anwenden-Fluss eines Platzierungs-Overrides (Issue #161, Review-Nacharbeit):
 * die Glue-Sequenz, die nach dem „Anwenden" einer Placement-Option
 * (Kollisions-Advisor #130, Singularitäts-Advisor #65/#134) die UI an den
 * frischen Override-Stand zieht, lebt hier als **eine** orchestrierende,
 * vitest-getestete Funktion mit injizierten Ports — statt als zweimal
 * kopierte, ungetestete Zeilen in `main.ts`. Die Reihenfolge ist Vertrag:
 *
 *   1. PUT placement-override (einzige Schreibstelle, ADR-007/016),
 *   2. frischen Job übernehmen (`adoptActiveJob` — MUSS vor den Markern
 *      stehen, `updateOverrideMarkers` liest den aktiven Job),
 *   3. Platzierungsfelder nachziehen (`restoreFromJob`, #94),
 *   4. ▪-Marker + Modul-Karten-Zeile nachziehen (`updatePartsOverrideMarkers`
 *      speist auch `placementDisplayValues`, #161),
 *   5. Veraltet-Badges auffrischen (`refreshRevisions`, #83),
 *   6. **Neubewertung anstoßen** (`reevaluateDecomposition`, Issue #172): der
 *      Druckplan übernimmt den frischen Override-Stand, setzt die Ampel/den
 *      Druckbarkeits- + Kollisions-Badge des Teils sofort auf „ungeprüft" und
 *      prüft debounced neu — **exakt die Semantik des manuellen Platzierungs-
 *      felds** (`onSaveOverride`). Vorher zeigten beide Advisor-Anwenden-Flüsse
 *      unmarkiert das alte Urteil zur alten Platzierung (B11/B20/B32): das harte
 *      Kriterium „niemals eine veraltete Ampel als aktuell" war verletzt.
 *
 * Schlägt der PUT fehl, passiert **nichts** an der UI (der Fehler propagiert
 * zum Panel, das ihn anzeigt — Befund, kein Gate). DOM-/three.js-frei.
 *
 * Seit Issue #193 ist die Nachzieh-Sequenz (Schritte 2–6) das allgemeine
 * **Übernahme-Protokoll** (`ui/job-adopt.ts`, Glossar viewer/CONTEXT.md):
 * dieses Modul behält sein Interface und delegiert intern — zwei Adapter am
 * selben Vertrag (`restore: "placement"` + `reevaluate`).
 */

import type { PlacementOverrideValues, PrintJob, SectionOverride } from "../api/projects";

import { adoptJobResponse } from "./job-adopt";

/** Die Effekte, die `main.ts` bereitstellt (echte Panels/Globals). */
export interface PlacementApplyPorts {
  /** PUT …/placement-override, an Projekt + Job gebunden (`setPlacementOverride`). */
  setPlacementOverride(
    sectionId: string,
    values: PlacementOverrideValues,
  ): Promise<{ print_jobs: PrintJob[] }>;
  /** Frischen Job als aktiven Job übernehmen (`currentActiveJob = job`). */
  adoptActiveJob(job: PrintJob | undefined): void;
  /** Platzierungsfelder an den frischen Stand ziehen (`placementOverridePanel.restoreFromJob`). */
  restorePlacementPanel(job: PrintJob | undefined): void;
  /** ▪-Marker + „Platzierung: …"-Zeile nachziehen (`updatePartsOverrideMarkers`). */
  updateOverrideMarkers(): void;
  /** Veraltet-Badges aus den frischen `print_jobs` (`refreshRevisions`). */
  refreshRevisions(jobs: PrintJob[]): void;
  /**
   * Neubewertung des Druckplans mit dem frischen Override-Stand anstoßen (Issue
   * #172): setzt Ampel + Druckbarkeits-/Kollisions-Badge des Teils sofort auf
   * „ungeprüft" und prüft debounced neu — dieselbe Semantik wie das manuelle
   * Platzierungsfeld (`druckplanPanel.applySectionOverrides`). Ohne diesen
   * Schritt bliebe das alte Urteil zur alten Platzierung unmarkiert stehen.
   */
  reevaluateDecomposition(overrides: SectionOverride[]): void;
}

/**
 * Platzierungs-Override anwenden und die UI nachziehen (Reihenfolge s. Kopf).
 * Liefert den frischen aktiven Job (oder `undefined`, wenn `jobId` fehlt —
 * die Ports werden dann mit `undefined` gerufen, kein Wurf, kein Gate).
 */
export async function applyPlacementOverride(
  ports: PlacementApplyPorts,
  sectionId: string,
  values: PlacementOverrideValues,
  jobId: string = "default",
): Promise<PrintJob | undefined> {
  const result = await ports.setPlacementOverride(sectionId, values);
  // Übernahme-Protokoll (Issue #193): Job übernehmen → Platzierungsfelder →
  // ▪-Marker → Badges → Neubewertung (#172) — die Reihenfolge besitzt jetzt
  // `adoptJobResponse`; hier nur noch der Adapter auf dessen Vertrag.
  return adoptJobResponse(
    {
      adoptActiveJob: (job) => ports.adoptActiveJob(job),
      restorePlacementPanel: (job) => ports.restorePlacementPanel(job),
      updateOverrideMarkers: () => ports.updateOverrideMarkers(),
      refreshRevisions: (jobs) => ports.refreshRevisions(jobs),
      reevaluateDecomposition: (overrides) => ports.reevaluateDecomposition(overrides),
    },
    result,
    { jobId, restore: "placement", reevaluate: true },
  );
}

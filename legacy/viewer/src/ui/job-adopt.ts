/**
 * Übernahme-Protokoll (Issue #193, Glossar viewer/CONTEXT.md): die feste
 * Nachzieh-Sequenz nach jeder Core-Antwort mit frischen `print_jobs` lebt hier
 * als **eine** orchestrierende, vitest-getestete Funktion mit injizierten
 * Ports — statt als 7+ divergierende Handkopien in `main.ts` (#161-Familie).
 * Mitglieder-Menge und Reihenfolge sind Vertrag (Muster `placement-apply.ts`):
 *
 *   1. **aktiven Druckjob übernehmen** (`adoptActiveJob` — MUSS zuerst stehen,
 *      die folgenden Schritte lesen den aktiven Job),
 *   2. **setSections-Fanout** (nur bei Antworten mit frischen Teilen,
 *      `opts.sections`): Zerlegungs-Ansicht → Simulation → Export →
 *      Prozessparameter-Teilformulare → Platzierungsfelder,
 *   3. **Formular-Restore** (nur als benannte Option, `opts.restore`):
 *      Prozessparameter- bzw. Platzierungs-Formulare an den frischen Stand,
 *   4. **▪-Marker der Teile-Palette** (`updateOverrideMarkers` — liest den in
 *      Schritt 1 übernommenen Job),
 *   5. **veraltet-Badges** (`refreshRevisions` aus den frischen `print_jobs`),
 *   6. **Neubewertung** (nur als benannte Option, `opts.reevaluate`, Issue
 *      #172): Ampel/Badges des Teils sofort „ungeprüft", debounced neu prüfen.
 *
 * Bewusste Abweichungen sind **benannte Optionen** mit eigenem Testfall —
 * keine stillen Varianten (Grill-Entscheidung 2026-07-13):
 *
 * - `druckplan: "panel-owns"` — die Zerlegungs-Ansicht wendet die Antwort
 *   selbst an (Rückgabewert/Generation-Guard #45); der Fanout lässt sie aus
 *   (onStandModeChange, onDecompose, onCheckApplied).
 * - `restore: "process-params"` — nach einem Prozessparameter-Schreiben ziehen
 *   die Formulare die geerbten Werte nach (#82/#92). Beim Teil-Override-
 *   Speichern (`onSaveSections`) bewusst NICHT gesetzt: der Restore würde
 *   ungespeicherte Eingaben des jeweils anderen Scopes verwerfen.
 * - `restore: "placement"` + `reevaluate` — der Platzierungs-Override-Vertrag
 *   (`placement-apply.ts`, das delegierende zweite Adapter-Paar am selben
 *   Protokoll).
 *
 * DOM-/three.js-frei; die echten Effekte (Panels/Globals) injiziert `main.ts`.
 */

import type { DecompositionSection, PrintJob, SectionOverride } from "../api/projects";
import type { Zerlegungsart } from "./zerlegungsart-state";

/**
 * Der aktive Druckjob einer Core-Antwort (Konvention: `job_id === "default"`).
 * Einzige Heimat dieses Selektors — `main.ts` sucht nicht mehr von Hand.
 */
export function findJob(jobs: PrintJob[] | undefined, jobId = "default"): PrintJob | undefined {
  return jobs?.find((j) => j.job_id === jobId);
}

/** Die Effekte, die `main.ts` bereitstellt (echte Panels/Globals). */
export interface JobAdoptPorts {
  /** Frischen Job als aktiven Druckjob übernehmen (`currentActiveJob = job`). */
  adoptActiveJob(job: PrintJob | undefined): void;
  /**
   * setSections-Fanout (Schritt 2) — nur nötig, wenn `opts.sections` übergeben
   * wird (Zerlegungs-förmige Antworten). Die Mitglieder-Menge ist Vertrag:
   * JEDE teile-führende Ansicht wird versorgt, keine darf still fehlen
   * (pollPruefCheck ließ vor #193 die Prozessparameter-Teilformulare aus).
   */
  sectionsFanout?: {
    /** Zerlegungs-Ansicht (`druckplanPanel.setSections`) — entfällt bei `druckplan: "panel-owns"`. */
    druckplan(sections: DecompositionSection[], kind: Zerlegungsart): void;
    /** Reiter Simulation (`simulationPanel.setSections`). */
    simulation(sections: DecompositionSection[]): void;
    /** Reiter Export (`exportPanel.setSections`). */
    export(sections: DecompositionSection[]): void;
    /** Teil-Override-Formulare des Gilt-für-Umschalters (`processParamsPanel.setSections`). */
    processParams(sections: DecompositionSection[], job: PrintJob | undefined): void;
    /** Platzierungsfelder + automatische Platzhalter (`placementOverridePanel.setSections`). */
    placement(sections: DecompositionSection[], job: PrintJob | undefined): void;
  };
  /** Prozessparameter-Formulare an den frischen Stand (`processParamsPanel.restoreFromJob`). */
  restoreProcessParamsPanel?(job: PrintJob | undefined): void;
  /** Platzierungsfelder an den frischen Stand (`placementOverridePanel.restoreFromJob`). */
  restorePlacementPanel?(job: PrintJob | undefined): void;
  /** ▪-Marker + „Platzierung: …"-Zeile der Teile-Palette (`updatePartsOverrideMarkers`). */
  updateOverrideMarkers(): void;
  /** Veraltet-Badges aus den frischen `print_jobs` (`refreshRevisions`). */
  refreshRevisions(jobs: PrintJob[]): void;
  /**
   * Neubewertung des Druckplans mit dem frischen Override-Stand (Issue #172):
   * Ampel + Badges des Teils sofort „ungeprüft", debounced neu prüfen
   * (`druckplanPanel.applySectionOverrides`).
   */
  reevaluateDecomposition?(overrides: SectionOverride[]): void;
}

/** Benannte Varianten des Protokolls — jede mit eigenem Testfall (#193). */
export interface JobAdoptOpts {
  /** Job-Auswahl in `print_jobs` (Standard: `"default"`). */
  jobId?: string;
  /** Frische Teile der Antwort — lösen den setSections-Fanout (Schritt 2) aus. */
  sections?: DecompositionSection[];
  /**
   * Wie die Zerlegungs-Ansicht die Teile erhält (Pflicht bei `sections`):
   * als Fanout-Schritt mit Zerlegungsart (`{ kind }`) oder `"panel-owns"` —
   * das Panel wendet die Antwort selbst an (Rückgabewert/Generation-Guard #45).
   */
  druckplan?: { kind: Zerlegungsart } | "panel-owns";
  /** Formular-Restore nach einem Schreiben ohne frische Teile (Schritt 3). */
  restore?: "process-params" | "placement";
  /** Neubewertung anstoßen (Schritt 6, Issue #172) — Platzierungs-Override-Flüsse. */
  reevaluate?: boolean;
}

/**
 * Übernahme-Protokoll ausführen (Reihenfolge s. Kopf). Liefert den übernommenen
 * Job (oder `undefined`, wenn `jobId` fehlt — die Ports werden dann mit
 * `undefined` gerufen, kein Wurf, kein Gate). Synchron: die Core-Antwort ist
 * beim Aufruf bereits da; schlug der Core-Aufruf fehl, wird das Protokoll gar
 * nicht erst betreten (der Fehler propagiert zum Panel — Befund, kein Gate).
 */
export function adoptJobResponse(
  ports: JobAdoptPorts,
  response: { print_jobs: PrintJob[] },
  opts: JobAdoptOpts = {},
): PrintJob | undefined {
  const job = findJob(response.print_jobs, opts.jobId ?? "default");
  ports.adoptActiveJob(job);
  if (opts.sections) {
    const fanout = ports.sectionsFanout;
    if (!fanout) {
      throw new Error("adoptJobResponse: opts.sections braucht ports.sectionsFanout");
    }
    if (!opts.druckplan) {
      throw new Error(
        'adoptJobResponse: opts.sections braucht opts.druckplan ({ kind } oder "panel-owns") — explizit statt still',
      );
    }
    if (opts.druckplan !== "panel-owns") {
      fanout.druckplan(opts.sections, opts.druckplan.kind);
    }
    fanout.simulation(opts.sections);
    fanout.export(opts.sections);
    fanout.processParams(opts.sections, job);
    fanout.placement(opts.sections, job);
  }
  if (opts.restore === "process-params") {
    if (!ports.restoreProcessParamsPanel) {
      throw new Error('adoptJobResponse: restore "process-params" ohne Port');
    }
    ports.restoreProcessParamsPanel(job);
  } else if (opts.restore === "placement") {
    if (!ports.restorePlacementPanel) {
      throw new Error('adoptJobResponse: restore "placement" ohne Port');
    }
    ports.restorePlacementPanel(job);
  }
  ports.updateOverrideMarkers();
  ports.refreshRevisions(response.print_jobs);
  if (opts.reevaluate) {
    if (!ports.reevaluateDecomposition) {
      throw new Error("adoptJobResponse: reevaluate ohne Port");
    }
    ports.reevaluateDecomposition(job?.section_overrides ?? []);
  }
  return job;
}

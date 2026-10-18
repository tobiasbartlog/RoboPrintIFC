/**
 * veraltet-Markierung (Issue #29): reine, three.js-/DOM-freie Ableitung, ob ein
 * nachgelagerter Stand (Druckplan, Simulation, Export) *veraltet* ist.
 *
 * Die Querschnitts-Konsistenz zwischen den Reitern (viewer/CONTEXT.md): ändert
 * sich Vorgelagertes (Wand, Roboter, Endeffektor, Schnittplan), werden
 * nachgelagerte Stände als *veraltet* markiert — sichtbar, nicht gelöscht. Das
 * Projekt hält dafür je Druckjob **Revisionsstände** (`revisions`): einen Zähler
 * je Eingabe-Stufe und je Output den Schnappschuss der Eingabe-Zähler zum
 * Zeitpunkt der letzten Erzeugung. Ein Output ist *veraltet*, wenn eine
 * vorgelagerte Eingabe-Revision neuer ist als der gespeicherte Schnappschuss.
 *
 * Das **Setzen** der Revisionen passiert im Core (`fgc.project`, einzige
 * Schreibstelle, ADR-016); hier lebt nur die **Ableitung** — der Viewer zeigt,
 * der Core rechnet/schreibt (ADR-007). Parität zur Python-Funktion
 * `fgc.project.output_status`. Fehlt `revisions` (Altprojekte), gilt nichts als
 * veraltet (rückwärtskompatibel, kein Gate).
 */

/** Die Eingabe-Stufen, deren Änderung Nachgelagertes veralten lässt. `process`
 *  (Prozessparameter, Scheibe 2 / Issue #59) ist die Rail für die Parametergruppen
 *  (Slice, später Orientierung/Bewegung): eine Änderung am `process_params`-Block
 *  veraltet Zerlegung/Simulation/Export. `workstation` (Issue #83): ein
 *  Workstation-Wechsel veraltet seit #80–82 alle Abschnitte (Ablösung des
 *  #77-Seams). Muss zu `fgc.project.revisions.INPUT_KEYS` passen. */
export const INPUT_KEYS = [
  "wall",
  "robot",
  "tool",
  "cutplan",
  "process",
  "workstation",
] as const;
export type InputKey = (typeof INPUT_KEYS)[number];

/** Die nachgelagerten Stufen mit veraltet-Markierung. */
export type OutputName = "druckplan" | "simulation" | "export";

/** Die **pro Abschnitt** existierenden Stufen (je ein `section_run`/Export, #83). */
export type SectionOutputName = "simulation" | "export";

/** Zustand einer Output-Stufe: nie erzeugt, veraltet oder aktuell. */
export type StageStatus = "missing" | "stale" | "current";

/** Ein Revisions-Schnappschuss: Zählerstand je beobachteter Eingabe (+ `section`
 *  in Pro-Abschnitts-Schnappschüssen, Issue #83; + `section_total` im Druckplan-
 *  Output-Schnappschuss, Issue #172 — die Summe aller Abschnitts-Zähler). */
export type RevisionSnapshot = Partial<Record<InputKey | "section" | "section_total", number>>;

/** Revisionsstände eines Druckjobs (project.json → print_job.revisions). */
export interface Revisions {
  inputs?: Partial<Record<InputKey, number>>;
  outputs?: Partial<Record<OutputName, RevisionSnapshot>>;
  /** Pro-Abschnitts-Zähler (Issue #83): section_id → Zähler; ein Abschnitts-Override
   *  bumpt nur diesen → nur dieser Abschnitt veraltet. */
  section_inputs?: Record<string, number>;
  /** Pro-Abschnitts-Output-Schnappschüsse (Issue #83): section_id → je Stufe der
   *  Schnappschuss der Job-Eingaben plus des Abschnitts-Zählers (`section`). */
  section_outputs?: Record<string, Partial<Record<SectionOutputName, RevisionSnapshot>>>;
}

/**
 * Welche Eingabe-Stufen ein Output beobachtet. Der Druckplan (Platzierung) hängt
 * an Wand/Roboter/Endeffektor/Workstation; Simulation und Export zusätzlich am
 * Schnittplan (cutplan). Bewusst pro Output deklariert, damit eine reine
 * Schnittplan-Änderung den Druckplan nicht veraltet (er *erzeugt* den Schnittplan).
 * Muss zu `fgc.project.revisions.OUTPUT_DEPS` passen.
 */
export const OUTPUT_DEPS: Record<OutputName, InputKey[]> = {
  druckplan: ["wall", "robot", "tool", "process", "workstation"],
  simulation: ["wall", "robot", "tool", "cutplan", "process", "workstation"],
  export: ["wall", "robot", "tool", "cutplan", "process", "workstation"],
};

/**
 * Welche Job-Eingaben ein **Pro-Abschnitts**-Output beobachtet (Issue #83): dieselben
 * wie global (`OUTPUT_DEPS`), damit strukturell/global (Schnitte, globale Params,
 * Roboter, Workstation) alle Abschnitte veraltet. Der Abschnitts-Zähler (`section`)
 * kommt in `sectionStageStatus` zusätzlich dazu. Muss zu
 * `fgc.project.revisions.SECTION_OUTPUT_JOB_DEPS` passen.
 */
export const SECTION_OUTPUT_JOB_DEPS: Record<SectionOutputName, InputKey[]> = {
  simulation: OUTPUT_DEPS.simulation,
  export: OUTPUT_DEPS.export,
};

/**
 * Welche Job-Outputs die **Summe** aller Abschnitts-Zähler (`section_total`)
 * beobachten (Issue #172): nur der **Druckplan** (der ganze Zerlegungslauf).
 * Muss zu `fgc.project.revisions.SECTION_AGGREGATE_OUTPUTS` passen — spiegelt den
 * früher hartkodierten `output === "druckplan"`-Zweig in {@link stageStatus}.
 */
export const SECTION_AGGREGATE_OUTPUTS: OutputName[] = ["druckplan"];

/** Ableitung für eine einzelne Output-Stufe. */
export function stageStatus(revisions: Revisions | undefined, output: OutputName): StageStatus {
  // Altprojekt ohne Revisionsfeld: nichts gilt als veraltet (rückwärtskompatibel).
  if (!revisions || (!revisions.inputs && !revisions.outputs)) return "current";
  const snapshot = revisions.outputs?.[output];
  if (!snapshot) return "missing";
  const inputs = revisions.inputs ?? {};
  for (const dep of OUTPUT_DEPS[output]) {
    if ((inputs[dep] ?? 0) > (snapshot[dep] ?? 0)) return "stale";
  }
  // Druckplan (Issue #172, Wurzel-Fix #161/B16/B32): der ganze Zerlegungslauf
  // veraltet bei JEDER Platzierungs-/Abschnitts-Override-Änderung — die Summe der
  // Abschnitts-Zähler ist neuer als der Druckplan-Schnappschuss. Parität zu
  // `fgc.project.revisions.output_status` (SECTION_AGGREGATE_OUTPUTS).
  if (SECTION_AGGREGATE_OUTPUTS.includes(output)) {
    const sectionTotal = sumSectionInputs(revisions);
    if (sectionTotal > (snapshot.section_total ?? 0)) return "stale";
  }
  return "current";
}

/** Summe aller Pro-Abschnitts-Zähler (Issue #172) — monoton, da Zähler nur steigen. */
function sumSectionInputs(revisions: Revisions): number {
  const si = revisions.section_inputs;
  if (!si) return 0;
  let total = 0;
  for (const v of Object.values(si)) total += v ?? 0;
  return total;
}

/** Ableitung für alle Output-Stufen auf einmal. */
export function allStageStatuses(revisions: Revisions | undefined): Record<OutputName, StageStatus> {
  return {
    druckplan: stageStatus(revisions, "druckplan"),
    simulation: stageStatus(revisions, "simulation"),
    export: stageStatus(revisions, "export"),
  };
}

/** Ob eine Output-Stufe veraltet ist (nur `"stale"`; `"missing"` ist nicht veraltet). */
export function isStale(status: StageStatus): boolean {
  return status === "stale";
}

/**
 * Pro-Abschnitts-Ableitung einer Stufe (Simulation/Export) — feingranulare Veraltung
 * (Issue #83, ADR-017-Nachtrag). Bit-gleicher Zwilling von
 * `fgc.project.revisions.section_output_status`:
 *
 * - Kein `revisions` (sehr altes Projekt) → `"current"`.
 * - Keine Pro-Abschnitts-Ebene (`section_outputs` fehlt — Altprojekt bzw. vor der
 *   ersten Abschnitts-Simulation) → Ganzjob-Veraltung wie bisher (`stageStatus`).
 * - Sonst: kein Abschnitts-Schnappschuss → `"missing"`; veraltet, wenn eine
 *   beobachtete **Job-Eingabe** neuer ist (global/strukturell → alle Abschnitte)
 *   **oder** der **Abschnitts-Zähler** neuer ist (nur dieser Abschnitt); sonst aktuell.
 */
export function sectionStageStatus(
  revisions: Revisions | undefined,
  sectionId: string,
  output: SectionOutputName,
): StageStatus {
  if (!revisions || (!revisions.inputs && !revisions.outputs)) return "current";
  // Legacy / vor erster Abschnitts-Simulation: keine Pro-Abschnitts-Ebene → Ganzjob.
  if (revisions.section_outputs === undefined) return stageStatus(revisions, output);
  const snapshot = revisions.section_outputs[sectionId]?.[output];
  if (!snapshot) return "missing";
  const inputs = revisions.inputs ?? {};
  for (const dep of SECTION_OUTPUT_JOB_DEPS[output]) {
    if ((inputs[dep] ?? 0) > (snapshot[dep] ?? 0)) return "stale";
  }
  const counter = revisions.section_inputs?.[sectionId] ?? 0;
  if (counter > (snapshot.section ?? 0)) return "stale";
  return "current";
}

/** Beide Pro-Abschnitts-Stufen (Simulation/Export) eines Abschnitts auf einmal (#83). */
export function allSectionStageStatuses(
  revisions: Revisions | undefined,
  sectionId: string,
): Record<SectionOutputName, StageStatus> {
  return {
    simulation: sectionStageStatus(revisions, sectionId, "simulation"),
    export: sectionStageStatus(revisions, sectionId, "export"),
  };
}

/** Menschliche Beschriftung eines Stufen-Zustands für ein Badge. */
export function stageStatusLabel(status: StageStatus): string {
  switch (status) {
    case "stale":
      return "veraltet";
    case "current":
      return "aktuell";
    case "missing":
      return "noch nicht erzeugt";
  }
}

/** Menschliche Beschriftung einer Output-Stufe. */
export function outputLabel(output: OutputName): string {
  switch (output) {
    case "druckplan":
      return "Druckplan";
    case "simulation":
      return "Simulation";
    case "export":
      return "Export";
  }
}

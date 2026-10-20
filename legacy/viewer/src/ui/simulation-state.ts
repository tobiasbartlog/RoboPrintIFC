/**
 * Reine, three.js-/DOM-freie Formatier- und Zustandslogik des Reiters Simulation
 * (Issue #26). Wie `cutplan-state.ts` für den Reiter Druckplan: hier liegen die
 * testbaren Funktionen, das DOM-Verdrahten steckt in `ui/simulation.ts`.
 *
 * Der Reiter zeigt je Abschnitt (in Druckreihenfolge) den Slice+Simulations-Stand:
 * ob ein Lauf existiert, Druckzeit, Achsauslastung und Warnungszahl. Alle Zahlen
 * stammen aus dem Core (trajectory.meta) — der Viewer rechnet nichts (ADR-007).
 */

/** Kennzahlen eines simulierten Abschnitts (aus der Simulate-Antwort/Trajektorie). */
export interface SectionSimSummary {
  /** Druckzeitschätzung (s) = Gesamtdauer der Trajektorie. */
  duration_s: number;
  /** Anzahl Kinematik-Warnungen (Reichweite/Achsgrenze/Singularität). */
  n_warnings: number;
  /** Achsauslastung je Achse (0..1). */
  axis_utilization: number[];
  /** Lagequelle — bei der Simulation aus der Platzierung immer 'planned'. */
  pose_source: string;
}

/** Höchste Achsauslastung über alle Achsen (0..1); 0 bei leerer Liste. */
export function maxAxisUtilization(util: number[]): number {
  return util.length > 0 ? Math.max(...util) : 0;
}

/** Das für `summaryFromMeta` benötigte Teilstück eines trajectory.json-Meta-Blocks. */
export interface TrajectoryMetaLike {
  duration_s: number;
  axis_utilization?: number[];
  warnings?: unknown[];
  pose_source?: string;
}

/**
 * Kennzahlen eines Abschnitts aus dem `meta`-Block seiner `trajectory.json`
 * gewinnen (Issue #48, Befund 3). Nach dem Projekt-Neuladen markiert
 * `setSectionRuns` die Abschnitte nur als „Lauf vorhanden"; diese reine Funktion
 * liest Druckzeit, Achsauslastung und Warnungszahl aus dem lazy nachgeladenen
 * Lauf-Artefakt (ADR-007: der Viewer rechnet nichts, er liest nur).
 */
export function summaryFromMeta(meta: TrajectoryMetaLike): SectionSimSummary {
  return {
    duration_s: meta.duration_s,
    n_warnings: meta.warnings?.length ?? 0,
    axis_utilization: meta.axis_utilization ?? [],
    pose_source: meta.pose_source ?? "planned",
  };
}

/** Formatiert eine Dauer als „s.s s", „m:ss min" oder „h:mm:ss h". */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  // Erst runden, dann verzweigen — sonst „1:60 min" bei 119.6 s (Issue #49).
  const t = Math.round(seconds * 10) / 10;
  if (t < 60) return `${t.toFixed(1)} s`;
  const total = Math.round(t);
  if (total < 3600) {
    const min = Math.floor(total / 60);
    return `${min}:${String(total % 60).padStart(2, "0")} min`;
  }
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(total % 60).padStart(2, "0")} h`;
}

/**
 * Ist der Gesamtablauf (Abschnitts-Sequenz, Issue #27) abspielbar? Genau dann,
 * wenn es Abschnitte gibt und **jeder** einen Lauf hat (`section_runs`). Reine
 * Prädikatslogik — die Sequenz spielt sonst nur Teile ab. Bei einem einzigen
 * Abschnitt genügt dessen Lauf (abwärtskompatibel: die Sequenz ist dann dieser
 * eine Abschnitt ohne Umbau-Schritt).
 */
export function sequenceReady(
  sectionIds: readonly string[],
  runSectionIds: Iterable<string>,
): boolean {
  const runs = new Set(runSectionIds);
  return sectionIds.length > 0 && sectionIds.every((id) => runs.has(id));
}

/**
 * Einzeilige Zusammenfassung eines simulierten Abschnitts für die Anzeige:
 * Druckzeit · max. Achsauslastung · Warnungszahl (Warnungen sind Befund, kein Gate).
 */
export function summaryLine(summary: SectionSimSummary): string {
  const util = (maxAxisUtilization(summary.axis_utilization) * 100).toFixed(0);
  const warn =
    summary.n_warnings === 0
      ? "keine Warnungen"
      : `${summary.n_warnings} ${summary.n_warnings === 1 ? "Warnung" : "Warnungen"}`;
  return `Druckzeit ${formatDuration(summary.duration_s)} · max. Achse ${util} % · ${warn}`;
}

/**
 * Zielfunktions-Einstellungen der Zerlegungs-Suche — reine, DOM-freie Logik
 * (Issue #212, PRD #183 Stufe 3, Grill 2026-07-14).
 *
 * EIN Gewichts-Satz, zwei Lesarten: Aufwiegen **AUS** (Default) liest die
 * Gewichts-Reihenfolge als lexikographische **Rangfolge** (kein Aufwiegen —
 * kein c_v kompensiert ein Einmessen); Aufwiegen **AN** liest dieselben Zahlen
 * als **gewichtete Summe**. Erreichbarkeit ist kein Kriterium, sondern das
 * harte K.-o. davor (Core, `fgc.decompose.objective`).
 *
 * Diese Datei hält nur die reine Logik (Default vorbelegen, Laden aus dem
 * Druckjob, Rangfolge aus Gewichten, Gleichstands-Sperre im Aus-Modus) —
 * getrennt getestet wie die übrigen `*-state.ts`. Das DOM-Verdrahten des
 * Einstellungs-Fensters liegt in `ui/objective.ts`; gerechnet (Komparator,
 * Quantisierung, Provenienz) wird ausschließlich im Core (ADR-007) — der
 * Viewer zeigt und persistiert nur (ADR-016, Setter-Route PUT …/objective).
 */

import type { ObjectiveSettings, ObjectiveWeights, PrintJob } from "../api/projects";

/** Ein Kriterium der Zielfunktion: Schlüssel (Core-Vertrag) + UI-Texte. */
export interface ObjectiveCriterion {
  key: keyof ObjectiveWeights;
  /** Anzeigename im Fenster. */
  label: string;
  /** Richtung als Nutzertext („weniger = besser" …) — reine Anzeige. */
  direction: string;
}

/**
 * Die vier Kriterien in Default-Rangfolge (Grill 2026-07-14, Entscheidung 1):
 * Umsetzvorgänge > Fugenfläche > kinematische Marge > c_v. Die Reihenfolge ist
 * zugleich der deterministische Tie-Break der Anzeige-Rangfolge (nur im
 * An-Modus möglich — im Aus-Modus ist Gleichstand gesperrt).
 */
export const OBJECTIVE_CRITERIA: readonly ObjectiveCriterion[] = [
  {
    key: "umsetzvorgaenge",
    label: "Umsetzvorgänge",
    direction: "weniger = besser (Einmessen ist der teuerste manuelle Schritt)",
  },
  { key: "fugenflaeche", label: "Fugenfläche", direction: "kleiner = besser" },
  { key: "kinematische_marge", label: "kinematische Marge", direction: "größer = besser" },
  { key: "volumen_cv", label: "Volumen-Gleichmäßigkeit (c_v)", direction: "kleiner = besser" },
];

/** Default-Gewichte — absteigend entlang der Default-Rangfolge, paarweise
 *  verschieden (Spiegel von `fgc.decompose.objective.DEFAULT_WEIGHTS`). */
export const DEFAULT_OBJECTIVE_WEIGHTS: ObjectiveWeights = {
  umsetzvorgaenge: 4,
  fugenflaeche: 3,
  kinematische_marge: 2,
  volumen_cv: 1,
};

/** Die vorbelegte Default-Config: Aufwiegen AUS (lexikographisch), Default-Gewichte. */
export function defaultObjective(): ObjectiveSettings {
  return { aufwiegen: false, weights: { ...DEFAULT_OBJECTIVE_WEIGHTS } };
}

/**
 * Lädt die Zielfunktion aus dem Druckjob — Default vorbelegt: fehlt der sparse
 * `objective`-Block (Altprojekt/Default), gilt die gepinnte Default-Config;
 * teilbelegte Gewichte erben fehlende Kriterien aus den Defaults (fail-soft,
 * derselbe Vertrag wie `ObjectiveConfig.from_dict` im Core).
 */
export function objectiveFromJob(job: PrintJob | null | undefined): ObjectiveSettings {
  const stored = job?.objective;
  if (!stored) return defaultObjective();
  return {
    aufwiegen: !!stored.aufwiegen,
    weights: { ...DEFAULT_OBJECTIVE_WEIGHTS, ...(stored.weights ?? {}) },
  };
}

/**
 * Die Rangfolge der Kriterien aus den Gewichten (Aus-Lesart): absteigend nach
 * Gewicht; gleiche Gewichte behalten die `OBJECTIVE_CRITERIA`-Reihenfolge
 * (deterministisch — relevant nur im An-Modus, im Aus-Modus sperrt der
 * Gleichstand das Speichern).
 */
export function objectiveRanking(weights: ObjectiveWeights): (keyof ObjectiveWeights)[] {
  return OBJECTIVE_CRITERIA.map((c) => c.key).sort((a, b) => weights[b] - weights[a]);
}

/** Die Kriterien-Gruppen mit gleichem Gewicht (≥ 2 Mitglieder) — der Gleichstand. */
export function tiedCriteria(weights: ObjectiveWeights): (keyof ObjectiveWeights)[][] {
  const byWeight = new Map<number, (keyof ObjectiveWeights)[]>();
  for (const c of OBJECTIVE_CRITERIA) {
    const w = weights[c.key];
    byWeight.set(w, [...(byWeight.get(w) ?? []), c.key]);
  }
  return [...byWeight.values()].filter((group) => group.length > 1);
}

/**
 * Warum das Speichern gesperrt ist — oder `null` (speicherbar).
 *
 * - Ein nicht-positives/nicht-endliches Gewicht sperrt immer (der Core weist
 *   es ebenso zurück).
 * - Gleichstand zweier Gewichte sperrt NUR im Aus-Modus (lexikographisch):
 *   die Rangfolge wäre mehrdeutig — UI-seitig verhindert (Grill 2026-07-14,
 *   Entscheidung 3). Im An-Modus (gewichtete Summe) ist Gleichstand zulässig.
 */
export function objectiveSaveBlocked(settings: ObjectiveSettings): string | null {
  for (const c of OBJECTIVE_CRITERIA) {
    const w = settings.weights[c.key];
    if (!Number.isFinite(w) || w <= 0) {
      return `Gewicht „${c.label}" muss eine positive Zahl sein.`;
    }
  }
  if (!settings.aufwiegen) {
    const ties = tiedCriteria(settings.weights);
    if (ties.length > 0) {
      const labels = ties[0]
        .map((key) => OBJECTIVE_CRITERIA.find((c) => c.key === key)?.label ?? key)
        .join(" und ");
      return (
        `Gleichstand: ${labels} tragen dasselbe Gewicht — ohne Aufwiegen ist die ` +
        "Rangfolge mehrdeutig. Gewichte unterscheiden oder Aufwiegen einschalten."
      );
    }
  }
  return null;
}

/** Der Lesarten-Text fürs Fenster: wie die aktuellen Gewichte wirken. */
export function objectiveReadingText(settings: ObjectiveSettings): string {
  const order = objectiveRanking(settings.weights)
    .map((key) => OBJECTIVE_CRITERIA.find((c) => c.key === key)?.label ?? key)
    .join(" > ");
  if (settings.aufwiegen) {
    return `Gewichtete Summe: Kriterien wiegen einander auf (Erreichbarkeit bleibt hartes K.-o.). Reihenfolge nach Gewicht: ${order}.`;
  }
  return `Rangfolge (kein Aufwiegen): ${order}. Erreichbarkeit bleibt hartes K.-o.`;
}

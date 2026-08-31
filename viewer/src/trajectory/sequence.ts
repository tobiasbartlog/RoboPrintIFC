/**
 * Reine Zeitachsen-/Sequenzlogik für das Simulations-Replay des Gesamtablaufs
 * (Issue #27), getrennt von three.js. Baut aus den einzelnen Abschnitts-
 * Trajektorien (Dauer je Abschnitt aus `trajectory.meta.duration_s`) + einer
 * Umbau-Schritt-Dauer zwischen den Abschnitten eine **Gesamtzeitleiste** und
 * bildet globale Zeit → (Abschnittsindex, lokale Abschnittszeit, „im Umbau?")
 * ab. Muster: `interpolate.ts`/`simulation-state.ts` — testbare Funktionen,
 * das three.js-Verdrahten steckt in `main.ts`.
 *
 * Darstellungsmathematik (ADR-007): kein Fachurteil, nur die Zeitachse. Die
 * Dauern kommen aus dem Core (`trajectory.meta`), der Viewer rechnet nichts.
 */

import type { RateSpan } from "./player";

/** Ein Abschnitt der Sequenz: Dauer seiner Druckphase + Reihenfolge-Schlüssel. */
export interface SequenceSegment {
  section_id: string;
  /** 1-basierte Druckreihenfolge (unten → oben). */
  order: number;
  /** Druckdauer des Abschnitts (s) = Gesamtdauer seiner Trajektorie. */
  duration_s: number;
}

/**
 * Die zusammengesetzte Gesamtzeitleiste: Abschnitte in Druckreihenfolge, mit
 * einem Umbau-Schritt fester Dauer *zwischen* je zwei Abschnitten (nicht nach
 * dem letzten). `starts_s[i]` ist die globale Startzeit der Druckphase von
 * Abschnitt i.
 */
export interface SequencePlan {
  segments: SequenceSegment[];
  /** Dauer eines Umbau-Schritts zwischen zwei Abschnitten (s). */
  umbau_s: number;
  /** Gesamtdauer der Zeitleiste (s), inkl. Umbau-Schritte. */
  total_s: number;
  /** Globale Startzeit der Druckphase je Abschnitt (s). */
  starts_s: number[];
}

/** Phase an einem Zeitpunkt: ein Abschnitt druckt, oder ein Umbau läuft. */
export type SequencePhase = "printing" | "umbau";

/** Auflösung eines globalen Zeitpunkts auf Abschnitt + Phase. */
export interface SequenceCursor {
  /** Index des aktiven (druckenden) bzw. gerade fertig gedruckten Abschnitts. */
  sectionIndex: number;
  /** Lokale Zeit im aktiven Abschnitt (s); bei Umbau = dessen Gesamtdauer. */
  localTime_s: number;
  /** Normierter Fortschritt im Abschnitt ∈ [0, 1]; bei Umbau = 1. */
  localFraction: number;
  phase: SequencePhase;
  /** Bei Umbau: Zielabschnitt-Index (sectionIndex + 1); sonst = sectionIndex. */
  toSectionIndex: number;
  /** Bei Umbau: Fortschritt des Umbau-Schritts ∈ [0, 1]; sonst 0. */
  umbauFraction: number;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/**
 * Baut die Gesamtzeitleiste aus den Abschnitts-Segmenten (nach `order`
 * sortiert) und der Umbau-Schritt-Dauer. Negative Dauern werden auf 0 geklemmt.
 */
export function buildSequencePlan(
  segments: SequenceSegment[],
  umbau_s: number,
): SequencePlan {
  const ordered = [...segments].sort((a, b) => a.order - b.order);
  const u = Math.max(0, umbau_s);
  const starts: number[] = [];
  let t = 0;
  ordered.forEach((seg, i) => {
    starts.push(t);
    t += Math.max(0, seg.duration_s);
    if (i < ordered.length - 1) t += u;
  });
  return { segments: ordered, umbau_s: u, total_s: t, starts_s: starts };
}

/**
 * Bildet eine globale Zeit auf (Abschnitt, lokale Zeit, Phase) ab. `timeGlobal`
 * wird auf [0, total_s] geklemmt. Ein Zeitpunkt genau am Ende einer Druckphase
 * zählt noch als „printing" (der Umbau beginnt erst danach). Bei nur einem
 * Abschnitt (oder umbau_s=0) gibt es nie eine Umbau-Phase — abwärtskompatibel.
 */
export function locateSequenceTime(
  plan: SequencePlan,
  timeGlobal: number,
): SequenceCursor {
  const n = plan.segments.length;
  const base: SequenceCursor = {
    sectionIndex: 0,
    localTime_s: 0,
    localFraction: 0,
    phase: "printing",
    toSectionIndex: 0,
    umbauFraction: 0,
  };
  if (n === 0) return base;

  const t = clamp(timeGlobal, 0, plan.total_s);
  for (let i = 0; i < n; i++) {
    const start = plan.starts_s[i];
    const dur = Math.max(0, plan.segments[i].duration_s);
    const printEnd = start + dur;
    if (t <= printEnd) {
      const frac = dur > 0 ? clamp((t - start) / dur, 0, 1) : 0;
      return {
        sectionIndex: i,
        localTime_s: clamp(t - start, 0, dur),
        localFraction: frac,
        phase: "printing",
        toSectionIndex: i,
        umbauFraction: 0,
      };
    }
    if (i < n - 1) {
      const umbauEnd = printEnd + plan.umbau_s;
      if (t <= umbauEnd) {
        const uf =
          plan.umbau_s > 0 ? clamp((t - printEnd) / plan.umbau_s, 0, 1) : 1;
        return {
          sectionIndex: i,
          localTime_s: dur,
          localFraction: 1,
          phase: "umbau",
          toSectionIndex: i + 1,
          umbauFraction: uf,
        };
      }
    }
  }

  // t == total_s → Ende des letzten Abschnitts (voll gedruckt).
  const last = n - 1;
  const dur = Math.max(0, plan.segments[last].duration_s);
  return {
    sectionIndex: last,
    localTime_s: dur,
    localFraction: 1,
    phase: "printing",
    toSectionIndex: last,
    umbauFraction: 0,
  };
}

/**
 * Die **vorwärts gerichtete** Abspiel-Rate an einem globalen Zeitpunkt (Issue #155):
 * innerhalb einer Druckphase gilt `printRate` (der Sitzungs-Faktor), innerhalb einer
 * Umbaupause gilt 1 (die Pause bleibt 3 s Wanduhr, skaliert NICHT mit — Erzählzeit,
 * #27). `until_s` ist die Trajektorienzeit der **nächsten** Phasengrenze; der Player
 * teilt seinen Frame dort, damit ein einziger langer Frame bei hohem Faktor nicht mit
 * Druck-Rate über die Umbaupause hinweg integriert.
 *
 * Vorwärts gerichtet heißt: am Zeitpunkt genau auf einer Grenze gilt die Rate der
 * Phase, die *nach* der Grenze beginnt (halboffene Intervalle [start, ende)). Das
 * unterscheidet sich bewusst von `locateSequenceTime` (dessen Ende-der-Druckphase noch
 * „printing" ist — für die Anzeige); hier ginge sonst ein Null-Intervall in eine
 * Endlosschleife. Reine Funktion (ADR-007), vitest daneben.
 */
export function sequenceRateAt(
  plan: SequencePlan,
  timeGlobal: number,
  printRate: number,
): RateSpan {
  const n = plan.segments.length;
  const inf = Number.POSITIVE_INFINITY;
  if (n === 0 || timeGlobal >= plan.total_s) {
    return { rate: printRate, until_s: inf };
  }
  const t = Math.max(0, timeGlobal);
  for (let i = 0; i < n; i++) {
    const start = plan.starts_s[i];
    const dur = Math.max(0, plan.segments[i].duration_s);
    const printEnd = start + dur;
    if (t < printEnd) return { rate: printRate, until_s: printEnd };
    if (i < n - 1) {
      const umbauEnd = printEnd + plan.umbau_s;
      if (t < umbauEnd) return { rate: 1, until_s: umbauEnd };
    }
  }
  return { rate: printRate, until_s: inf };
}

/**
 * Fraktions-Index in eine Target-/Segment-Liste der Länge `nTargets` für einen
 * normierten Fortschritt f ∈ [0, 1] — dieselbe Zeit→Index-Abbildung wie beim
 * TCP-Marker und Arm-Replay. Steuert, wie weit der gedruckte Strang aufgedeckt
 * wird (Segment k sichtbar, sobald f dessen Ziel-Target erreicht/passiert hat).
 */
export function targetIndexAtProgress(nTargets: number, f: number): number {
  if (nTargets <= 1) return 0;
  return clamp(f, 0, 1) * (nTargets - 1);
}

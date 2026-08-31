/**
 * Wand-Bilanz der Projektliste (UI-Redesign Scheibe 7, Issue #104) — reine,
 * DOM-freie Ableitung des Bilanz-Balkens einer Projekt-Karte.
 *
 * Der Balken zeigt die Anteile druckbar/vorläufig/ungeeignet der Wände eines
 * Projekts. Die Klassifikation stammt AUSSCHLIESSLICH aus dem
 * candidates-Artefakt des Übersichts-Laufs (`eligible` + `provisional`-Flags,
 * die der Core setzt) — der Viewer rechnet nichts neu (ADR-007). Die Regel ist
 * dieselbe wie `verdict()` in `render/model.ts` (dort für die Einfärbung der
 * Modellübersicht): sie liest nur die Flags, sie urteilt nicht.
 *
 * Dieses Modul macht daraus die reine Präsentationsmathematik (Zählen →
 * Anteile → Legende) plus einen deutschen Relativ-Zeitstempel. Getrennt von
 * DOM getestet (`wall-balance.test.ts`).
 */

import type { Candidates } from "../artifacts/types";

/** Anzahl Wände je Eignungs-Kategorie (aus den Artefakt-Flags gezählt). */
export interface WallBalance {
  druckbar: number;
  vorlaeufig: number;
  ungeeignet: number;
}

/** Segment-Breiten des 6px-Balkens in Prozent (0..100), Summe = 100. */
export interface WallBalanceSegments {
  druckbar: number;
  vorlaeufig: number;
  ungeeignet: number;
}

/**
 * Zählt die Wände je Kategorie — dieselbe Regel wie `verdict()` in
 * `render/model.ts` (Flags lesen, nicht rechnen, ADR-007):
 *   ungeeignet  = nicht eligible (rot)
 *   vorläufig   = eligible UND mind. ein bestandener provisional-Check (amber)
 *   druckbar    = eligible, kein provisional-Pass (grün)
 * Wände ohne Urteil (kann bei Altartefakten nicht vorkommen — jeder Eintrag hat
 * `eligible`) fallen bei druckbar/ungeeignet aus der `eligible`-Verzweigung.
 */
export function wallBalanceFromCandidates(candidates: Candidates): WallBalance {
  const b: WallBalance = { druckbar: 0, vorlaeufig: 0, ungeeignet: 0 };
  for (const w of candidates.walls) {
    if (!w.eligible) {
      b.ungeeignet++;
    } else if (w.checks.some((c) => c.passed && c.provisional === true)) {
      b.vorlaeufig++;
    } else {
      b.druckbar++;
    }
  }
  return b;
}

/** Gesamtzahl der bilanzierten Wände. */
export function wallBalanceTotal(b: WallBalance): number {
  return b.druckbar + b.vorlaeufig + b.ungeeignet;
}

/**
 * Segment-Anteile in Prozent, oder `null` wenn es nichts zu bilanzieren gibt
 * (kein Übersichts-Lauf / keine Wände) — dann degradiert die Karte sauber ohne
 * Balken (kein kaputter 0-%-Balken).
 */
export function wallBalanceSegments(b: WallBalance): WallBalanceSegments | null {
  const total = wallBalanceTotal(b);
  if (total <= 0) return null;
  return {
    druckbar: (b.druckbar / total) * 100,
    vorlaeufig: (b.vorlaeufig / total) * 100,
    ungeeignet: (b.ungeeignet / total) * 100,
  };
}

/** Klartext-Legende, nur nicht-leere Kategorien: „9 druckbar · 4 vorläufig · 7 ungeeignet". */
export function wallBalanceLegend(b: WallBalance): string {
  const parts: string[] = [];
  if (b.druckbar > 0) parts.push(`${b.druckbar} druckbar`);
  if (b.vorlaeufig > 0) parts.push(`${b.vorlaeufig} vorläufig`);
  if (b.ungeeignet > 0) parts.push(`${b.ungeeignet} ungeeignet`);
  return parts.join(" · ");
}

/**
 * Deutscher Relativ-Zeitstempel für den Karten-Kopf („vor 2 Std.", „gestern").
 * `nowMs` wird injiziert (testbar); ab einer Woche fällt es auf ein Datum
 * zurück.
 */
export function formatRelativeGerman(tsMs: number, nowMs: number): string {
  const diff = Math.max(0, nowMs - tsMs);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "gerade eben";
  if (min === 1) return "vor 1 Min.";
  if (min < 60) return `vor ${min} Min.`;
  const hrs = Math.floor(min / 60);
  if (hrs === 1) return "vor 1 Std.";
  if (hrs < 24) return `vor ${hrs} Std.`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "gestern";
  if (days < 7) return `vor ${days} Tagen`;
  return new Date(tsMs).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

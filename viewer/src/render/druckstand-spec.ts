/**
 * Wachsender Druckstand — reine Prisma-Spec (Kollisionskontrolle S3, US 10,
 * ADR-024, Issue #128). three.js-frei und vitest-getestet (Hausmuster wie
 * `druckort-spec.ts`).
 *
 * Statt der bisherigen Voll-Box zeigt die Kollisions-Darstellung den Druckstand
 * (Abschnitt/Modul), der **mit dem Druckfortschritt wächst** — die Wand entsteht
 * Schicht für Schicht, und nur das schon Gedruckte ist Hindernis. Diese Datei
 * rechnet ausschließlich **Darstellungsmathematik** (ADR-007-Klarstellung, wie
 * `moduleBoxSpec`): aus der vollen Bauteil-Box + dem Druckfortschritt (0..1, aus
 * der Trajektorien-Zeit, dieselbe Abbildung wie der wachsende Strang) das aktuell
 * gewachsene Prisma — Maße + lokaler Mittelpunkt. Kein Kollisions-Urteil.
 *
 * Der Druckstand wächst entlang der Höhe (z, dritte Achse, z-hoch/ADR-006) von
 * der Basis (lokal z = 0) nach oben. Die dünne three.js-Anbindung
 * (`render/druckstand.ts`) setzt Maße/Lage nur um.
 */

/** Ergebnis: Maße + lokaler Mittelpunkt des gewachsenen Prismas. */
export interface DruckstandPrism {
  /** [Länge, Dicke, gewachsene Höhe] in mm. */
  sizeMm: [number, number, number];
  /** Box-Mittelpunkt in lokalen Koordinaten (Basis bei z = 0). */
  centerLocalMm: [number, number, number];
  /** Der angewandte, geklemmte Wachstums-Anteil ∈ [0, 1]. */
  grownFraction: number;
  /** false, solange nichts gewachsen ist (Höhe 0) — dann nichts zeichnen. */
  visible: boolean;
}

/**
 * Das gewachsene Druckstand-Prisma zum Fortschritt `grownFraction` (0..1): Länge
 * und Dicke bleiben die der vollen Box, die Höhe wächst linear von 0 auf die volle
 * Höhe. Der Anteil wird auf [0, 1] geklemmt (kein Über-/Unterwachsen); nicht-endliche
 * oder negative Maße fallen sicher auf 0. Reine, deterministische Funktion.
 */
export function druckstandPrism(input: {
  /** Volle Bauteil-Box [Länge, Dicke, Höhe] in mm. */
  fullSizeMm: [number, number, number];
  /** Druckfortschritt ∈ [0, 1] (Trajektorien-Zeit / Dauer). */
  grownFraction: number;
}): DruckstandPrism {
  const length = safeDim(input.fullSizeMm[0]);
  const thickness = safeDim(input.fullSizeMm[1]);
  const fullHeight = safeDim(input.fullSizeMm[2]);
  const f = clamp01(Number.isFinite(input.grownFraction) ? input.grownFraction : 0);
  const grownHeight = fullHeight * f;
  return {
    sizeMm: [length, thickness, grownHeight],
    centerLocalMm: [0, 0, grownHeight / 2],
    grownFraction: f,
    visible: grownHeight > 0,
  };
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

function safeDim(x: number): number {
  return Number.isFinite(x) && x > 0 ? x : 0;
}

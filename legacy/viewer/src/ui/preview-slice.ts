/**
 * Billiger, IK-freier Vorschau-Slicer der Live-Vorschau „Vorbereiten"
 * (Druckplan S6, Issue #85, PRD B/#70) — **reine Darstellungsmathematik**
 * (ADR-007), ohne Renderer, ohne Core-Aufruf.
 *
 * Beim Reglerziehen (globale oder Pro-Abschnitts-Params, #82) müssen sich die
 * gesliceten Bahnen des Fokus-Abschnitts **sofort** aktualisieren — flüssig,
 * ohne den vollen Arm. Diese Funktion erzeugt dafür aus der Abschnitts-Box +
 * den effektiven Slice-Parametern gestapelte, CCW-orientierte Rechteck-
 * Umfangsringe (Schalen) als eine durchgehende Bahn. Das ist **kein** echter
 * Slice (der bleibt im Core) — es ist die billige Vorschau-Geometrie, entlang
 * derer die Düsen-Schablone (`nozzle-schablone.ts`) gleitet.
 *
 * CCW-Orientierung ist bewusst: sie ist die Konvention, aus der `nozzle_quat`
 * (#61) die Wand-Außenseite ableitet (`n_out = tangent × ẑ`) — so stimmt der
 * Kipp-Sinn der Schablone mit dem Slicer überein.
 *
 * Frame: kanonisch (x = Wandlänge, y = Wanddicke/Front zentriert um 0, z = Höhe
 * ab Wandfuß), mm.
 */

import type { Vec3 } from "./nozzle-quat";

/** Effektive Slice-Params der Vorschau (nach `resolveSectionParams`, #82). */
export interface EffectiveSlice {
  layer_height_mm?: number;
  strand_width_mm?: number;
  n_shells?: number;
}

/** Abschnitts-Box im kanonischen Frame (aus `DecompositionSection`). */
export interface SectionExtent {
  /** Längsgrenzen (mm, um die Wandmitte zentriert wie `DecompositionSection.x*`). */
  x0_mm: number;
  x1_mm: number;
  /** Höhengrenzen (mm, ab Wandfuß). */
  z0_mm: number;
  z1_mm: number;
  /** Wanddicke (mm) — die Front/Rück-Ausdehnung in y. */
  thickness_mm: number;
}

/** Ergebnis des Vorschau-Slicers: die Bahn + ableitbare Kennzahlen. */
export interface PreviewSlice {
  /** Durchgehende Bahn (mm) — Ringe je Schicht, aufsteigend gestapelt. */
  path: Vec3[];
  nLayers: number;
  /** Punkte je geschlossenem Ring (5: 4 Ecken + Rückkehr zum Start). */
  pointsPerRing: number;
  layerHeightMm: number;
  strandWidthMm: number;
  nShells: number;
}

/** Sichtbare Defaults, falls ein Feld nicht gesetzt ist (nur Vorschau, ADR-007
 *  — der Core hat die verbindlichen Karten-Defaults). */
const DEFAULT_LAYER_HEIGHT_MM = 8;
const DEFAULT_STRAND_WIDTH_MM = 30;
const DEFAULT_N_SHELLS = 1;

function posOr(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

/**
 * Ein geschlossener, CCW-orientierter Rechteck-Ring in der (x, y)-Ebene auf Höhe
 * `z`, um `inset` nach innen versetzt. 5 Punkte (Start doppelt) → geschlossen.
 */
function ring(x0: number, x1: number, yHalf: number, z: number, inset: number): Vec3[] {
  const xa = x0 + inset;
  const xb = x1 - inset;
  const yb = yHalf - inset;
  // CCW von unten-links aus Sicht von +z: (xa,-yb) → (xb,-yb) → (xb,+yb) → (xa,+yb) → zurück.
  return [
    [xa, -yb, z],
    [xb, -yb, z],
    [xb, yb, z],
    [xa, yb, z],
    [xa, -yb, z],
  ];
}

/**
 * Erzeugt die Vorschau-Bahn eines Abschnitts. Die Schichten stapeln von unten
 * (z0) nach oben mit `layer_height_mm`; je Schicht `n_shells` nach innen
 * versetzte Umfangsringe (Versatz = Strangbreite je Schale). Schalen/Schichten,
 * die durch zu großen Versatz kollabieren, werden ausgelassen — die Bahn bleibt
 * gültig (nie leer, solange die Box eine Schicht trägt).
 */
export function sliceSectionPreview(
  section: SectionExtent,
  slice: EffectiveSlice,
): PreviewSlice {
  const layerHeightMm = posOr(slice.layer_height_mm, DEFAULT_LAYER_HEIGHT_MM);
  const strandWidthMm = posOr(slice.strand_width_mm, DEFAULT_STRAND_WIDTH_MM);
  const nShells = Math.max(1, Math.round(posOr(slice.n_shells, DEFAULT_N_SHELLS)));

  const x0 = Math.min(section.x0_mm, section.x1_mm);
  const x1 = Math.max(section.x0_mm, section.x1_mm);
  const z0 = Math.min(section.z0_mm, section.z1_mm);
  const z1 = Math.max(section.z0_mm, section.z1_mm);
  const yHalf = Math.max(section.thickness_mm, strandWidthMm) / 2;

  const path: Vec3[] = [];
  let nLayers = 0;
  // Schichtmitten: erste bei z0 + h/2, dann in Schritten von h, solange sie in die Box passen.
  for (let z = z0 + layerHeightMm / 2; z <= z1 + 1e-6; z += layerHeightMm) {
    let addedRing = false;
    for (let shell = 0; shell < nShells; shell++) {
      const inset = shell * strandWidthMm + strandWidthMm / 2;
      // Ring kollabiert, wenn der Versatz Länge oder Dicke auffrisst.
      if (x1 - x0 - 2 * inset <= 0 || 2 * (yHalf - inset) <= 0) break;
      path.push(...ring(x0, x1, yHalf, z, inset));
      addedRing = true;
    }
    if (addedRing) nLayers++;
  }

  return {
    path,
    nLayers,
    pointsPerRing: 5,
    layerHeightMm,
    strandWidthMm,
    nShells,
  };
}

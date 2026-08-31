/**
 * Punktnummerierung der Bahn-/Anfahrpunkte (Issue #138): reine Auswahl-,
 * Ausdünnungs- und Sichtbarkeitslogik für die optionalen Nummern-Labels am
 * Toolpath — DOM-/three.js-frei, damit sie ohne WebGL testbar ist (vitest).
 * Die Sprite-Erzeugung + das Verdrahten an denselben Layer-/Wachs-/Travel-
 * Zustand wie die Bahnlinien lebt in `render/toolpath.ts` (ADR-007: die
 * Auswahl/Ausdünnung/Sichtbarkeit selbst ist keine Fachlogik, aber sie soll
 * trotzdem nicht im three.js-Renderpfad verborgen sein).
 *
 * Getroffene Defaults (Design-Log 2026-07-11, Issue #138):
 * - **Ansicht:** die eine vorhandene Toolpath-Darstellung (`ToolpathView`) —
 *   Wand-Einzel-Lauf, Abschnitts-Sequenz und Modul-Replay nutzen alle
 *   dieselbe Klasse; ein gemeinsamer ⚙-Schalter in der Sektion
 *   „Replay-Bühne" statt einer erfundenen zweiten Darstellung.
 * - **Punkte:** NICHT alle Targets — nur print/travel-Wechsel und
 *   Ring-/Schichtanfänge. `segment_id` (Core: `L{layer}_C{poly}_S{shell}_R{ring}`,
 *   der Anfahrpunkt trägt zusätzlich `_approach`) ändert sich bei JEDEM
 *   Schicht-, Ring- UND Anfahr-/Druck-Wechsel — ein Vergleich mit dem
 *   Vorgänger-Target genügt, ein Kind-Vergleich zusätzlich schadet nicht.
 * - **Dichte-Deckelung:** harte Obergrenze `MAX_TARGET_LABELS` gleichzeitig
 *   beschrifteter Punkte; bei Überschreitung gleichmäßig ausgedünnt (Lücken
 *   statt eines abgeschnittenen Randes) — sonst unlesbar und langsam bei
 *   tausenden Targets.
 * - **Sichtbarkeit:** ein Label ist nur sichtbar, wenn sein Ziel-Target nach
 *   demselben Layer-/Wachs-/Travel-Zustand wie die Bahnlinien ohnehin
 *   sichtbar wäre — sonst schwebten Nummern zukünftiger Schichten oder
 *   ausgeblendeter Travel-Segmente in der Luft.
 */

import type { Target, TargetKind } from "../artifacts/types";

/** Harte Obergrenze gleichzeitig beschrifteter Punkte (Lesbarkeit + Tempo). */
export const MAX_TARGET_LABELS = 150;

/** Ein zu beschriftender Zielpunkt (0-basierter Index in der Target-Liste). */
export interface TargetLabel {
  /** Index in `targets` — die Anzeigenummer ist `index + 1` (1-basiert, Roboterprogramm-Zählung). */
  index: number;
  layer: number;
  kind: TargetKind;
  pos_mm: readonly [number, number, number];
}

/**
 * Indizes der „aussagekräftigen" Punkte (Issue #138, Triage „welche Punkte"):
 * der erste Punkt, sowie jeder Target-Index, an dem sich `kind` (print/travel)
 * oder `segment_id` (Ring/Schicht) gegenüber dem Vorgänger ändert. Aufsteigend
 * sortiert, keine Duplikate.
 */
export function significantTargetIndices(targets: readonly Target[]): number[] {
  if (targets.length === 0) return [];
  const out: number[] = [0];
  for (let i = 1; i < targets.length; i++) {
    const a = targets[i - 1];
    const b = targets[i];
    if (b.kind !== a.kind || b.segment_id !== a.segment_id) out.push(i);
  }
  return out;
}

/**
 * Dünnt eine aufsteigend sortierte Indexliste gleichmäßig auf höchstens
 * `maxCount` Einträge aus (Issue #138, Triage „Dichte-Deckelung") — verteilte
 * Lücken über die ganze Bahn statt eines abgeschnittenen Randes. Der erste
 * Eintrag bleibt immer erhalten. `maxCount <= 0` liefert eine leere Liste.
 */
export function thinIndices(indices: readonly number[], maxCount: number): number[] {
  if (maxCount <= 0) return [];
  if (indices.length <= maxCount) return [...indices];
  const step = indices.length / maxCount;
  const out: number[] = [];
  const seen = new Set<number>();
  for (let k = 0; k < maxCount; k++) {
    const idx = indices[Math.min(indices.length - 1, Math.floor(k * step))];
    if (!seen.has(idx)) {
      seen.add(idx);
      out.push(idx);
    }
  }
  return out;
}

/**
 * Baut die endgültige Label-Liste: aussagekräftige Punkte, auf `maxCount`
 * gedeckelt (Default `MAX_TARGET_LABELS`). Reine Ableitung aus den Targets —
 * das Ergebnis trägt Position + Layer/Art für die Sichtbarkeitsprüfung mit,
 * damit der Aufrufer die Roh-Targets nicht erneut durchsuchen muss.
 */
export function targetLabels(
  targets: readonly Target[],
  maxCount: number = MAX_TARGET_LABELS,
): TargetLabel[] {
  const indices = thinIndices(significantTargetIndices(targets), maxCount);
  return indices.map((index) => {
    const t = targets[index];
    return { index, layer: t.layer, kind: t.kind, pos_mm: t.frame.pos_mm };
  });
}

/**
 * Layer-/Wachs-/Travel-Zustand, den die Bahnlinien gerade zeigen
 * (Spiegel der privaten `ToolpathView`-Felder, die `apply()` auswertet).
 */
export interface ToolpathVisibilityState {
  growthMode: boolean;
  growthIndex: number;
  visibleUpTo: number;
  onlyCurrent: boolean;
  travelVisible: boolean;
}

/**
 * Ob ein einzelnes Label sichtbar sein soll: der ⚙-Schalter ist an UND sein
 * Ziel-Target wäre nach genau derselben Regel sichtbar wie die Bahnlinien
 * (Layer-Slider / Wachs-Modus / Travel-Schalter, Issue #138 Triage
 * „Sichtbarkeit"). Reine Funktion — dieselbe Regel treibt sowohl die Tests
 * als auch `ToolpathView.apply()`.
 */
export function targetLabelVisible(
  label: Pick<TargetLabel, "index" | "layer" | "kind">,
  labelsEnabled: boolean,
  state: ToolpathVisibilityState,
): boolean {
  if (!labelsEnabled) return false;
  if (label.kind === "travel" && !state.travelVisible) return false;
  if (state.growthMode) return label.index <= state.growthIndex;
  return state.onlyCurrent ? label.layer === state.visibleUpTo : label.layer <= state.visibleUpTo;
}

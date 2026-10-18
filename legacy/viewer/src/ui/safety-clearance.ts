/**
 * Deep Module `ui/safety-clearance` — die reine Geometrie der **selbsterklärend
 * animierten** Sicherheitsabstand-Visualisierung der Live-Vorschau „Vorbereiten"
 * (Druckplan S6, Issue #85, PRD B/#70).
 *
 * Aus der Basislage (`standoff` der Platzierung, #80) und dem
 * `safety_min_distance_mm` der Workstation (#77) entsteht ein **lebender Puffer**
 * zwischen Roboterbasis/Arm und Wand. Beim Abstands-Optimieren (der Core sucht
 * den besten Abstand ab dem Sicherheits-Mindestabstand, #80) „atmet" der Puffer
 * sichtbar — so wird die nackte Zahl ohne Erklärung verständlich: pulsiert der
 * Puffer nah an der Wand, ist die Marge knapp; bleibt viel Luft, ist sie üppig.
 *
 * Reine Geometrie, **ohne Renderer** — per vitest prüfbar. Die three.js-
 * Darstellung + Animation liegt getrennt in `render/clearance.ts`
 * (Pure/DOM-Split). mm; die Front-Normale zeigt von der Basis zur Wand.
 */

/** Momentaner Zustand des atmenden Sicherheitspuffers (rein, ableitbar). */
export interface ClearanceState {
  /** Geplanter Abstand Basis→Wandfront (mm) — die volle Lücke. */
  standoffMm: number;
  /** Sicherheits-Mindestabstand der Workstation (mm) — die harte Untergrenze. */
  safetyMinMm: number;
  /** Marge = standoff − Mindestabstand (mm); < 0 ⇒ Mindestabstand verletzt. */
  marginMm: number;
  /** true, wenn der geplante Abstand den Mindestabstand einhält (Marge ≥ 0). */
  safe: boolean;
  /** Atmender Puls-Radius des Sicherheitskerns (mm) — oszilliert mit der Phase. */
  pulseMm: number;
  /** Atem-Anteil ∈ [0, 1] der aktuellen Phase (0 = eingeatmet, 1 = ausgeatmet). */
  breath: number;
}

/** Wie stark der Sicherheitskern beim Atmen schrumpft (Anteil des Mindestabstands). */
const BREATH_MIN_FRACTION = 0.8;

/**
 * Atem-Anteil einer Phase ∈ [0, 1): weiches Ein-/Ausatmen über einen vollen
 * Kosinus-Zyklus (0 → 0, 0.5 → 1, 1 → 0). Der Puffer „lebt" damit sichtbar.
 */
export function breathAt(phase: number): number {
  return 0.5 - 0.5 * Math.cos(2 * Math.PI * phase);
}

/**
 * Rechnet den momentanen Puffer-Zustand aus geplanter Aufstellung + Mindest-
 * abstand + Animationsphase. Der Puls-Radius atmet zwischen
 * `BREATH_MIN_FRACTION · safetyMin` und `safetyMin`; Marge/Sicherheit reagieren
 * unmittelbar auf `standoffMm` (das der Abstands-Optimierer bewegt) — so „atmet"
 * die Visualisierung beim Optimieren sichtbar mit.
 */
export function clearanceState(
  standoffMm: number,
  safetyMinMm: number,
  phase: number,
): ClearanceState {
  const safety = Math.max(0, safetyMinMm);
  const standoff = Math.max(0, standoffMm);
  const breath = breathAt(phase);
  const pulseMm = safety * (BREATH_MIN_FRACTION + (1 - BREATH_MIN_FRACTION) * breath);
  const marginMm = standoff - safety;
  return {
    standoffMm: standoff,
    safetyMinMm: safety,
    marginMm,
    safe: marginMm >= 0,
    pulseMm,
    breath,
  };
}

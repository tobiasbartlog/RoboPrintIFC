/**
 * Warnungs-Zusammenfassung fürs Trajektorien-Panel (Issue #32) — reine
 * Funktion ohne DOM. Läufe mit weitgehend unerreichbaren Zielen tragen
 * hunderte reach-Warnungen; die UI zeigt eine Zusammenfassung je Art plus die
 * frühesten Einträge, statt das Panel mit tausenden <li> zu fluten.
 */

export interface WarningLike {
  t_s: number;
  kind: string;
  message: string;
}

export interface WarningsSummary<T extends WarningLike> {
  total: number;
  /** Anzahl je Warnungs-Art (z. B. { reach: 412 }). */
  countsByKind: Record<string, number>;
  /** Die frühesten `maxShown` Warnungen (Reihenfolge der Trajektorie). */
  shown: T[];
  /** Wie viele Warnungen NICHT gezeigt werden. */
  hidden: number;
}

export function summarizeWarnings<T extends WarningLike>(
  warnings: T[],
  maxShown = 20,
): WarningsSummary<T> {
  const countsByKind: Record<string, number> = {};
  for (const w of warnings) {
    countsByKind[w.kind] = (countsByKind[w.kind] ?? 0) + 1;
  }
  const shown = warnings.slice(0, maxShown);
  return { total: warnings.length, countsByKind, shown, hidden: warnings.length - shown.length };
}

/**
 * Abspielgeschwindigkeit der Player-Leiste als **Vielfaches der Echtzeit**
 * (Issue #155, Wayfinder-Karte #139 → Entscheidung #148). DOM-frei und
 * vitest-getestet (Hausmuster wie `sim-dock-state.ts`): hier liegt nur die reine
 * Rechnung „Faktor → resultierende Replay-Dauer" und ihre Beschriftung; das
 * `<select>`-Verdrahten macht dünn `ui/simulation.ts`.
 *
 * Ein realer Wand-Abschnitt dauert Minuten bis über eine Stunde — bei 1× fährt
 * der Arm so schnell wie die echte Maschine (nötig, um enge Stellen zu beurteilen),
 * höhere Faktoren raffen die Druckphasen. Die **Umbaupausen skalieren NICHT mit**
 * (Erzählzeit, #27): sie zählen ungeteilt in die Restdauer.
 */

/** Die Geschwindigkeits-Leiter (Vielfache der Echtzeit); Voreinstellung 1×. */
export const SPEED_STEPS: readonly number[] = [
  0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 200,
];

/** Der Faktor als kurze Anzeige, z. B. „0.25×", „1×", „200×". */
export function formatRate(rate: number): string {
  return `${rate}×`;
}

/**
 * Resultierende Replay-Dauer (s): die Druckphasen werden durch den Faktor
 * geteilt, die Umbaupausen bleiben ungeteilt (Wanduhr, #27). `rate <= 0` wird auf
 * 1 geklemmt (nie Division durch 0).
 */
export function replayEta(
  printTotal_s: number,
  umbauTotal_s: number,
  rate: number,
): number {
  const r = rate > 0 ? rate : 1;
  return Math.max(0, printTotal_s) / r + Math.max(0, umbauTotal_s);
}

/**
 * Kompakte Dauer-Anzeige „~M:SS" (bzw. „~H:MM:SS" ab einer Stunde) — die Näherung
 * neben dem Faktor (z. B. „~1:44"). Auf ganze Sekunden gerundet.
 */
export function formatEta(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  if (h > 0) return `~${h}:${String(m).padStart(2, "0")}:${ss}`;
  return `~${m}:${ss}`;
}

/** Ein Options-Label: Faktor UND resultierende Replay-Dauer, z. B. „50× · ~1:44". */
export function speedOptionLabel(
  rate: number,
  printTotal_s: number,
  umbauTotal_s: number,
): string {
  return `${formatRate(rate)} · ${formatEta(replayEta(printTotal_s, umbauTotal_s, rate))}`;
}

/**
 * Druckplatz auf dem Doosantisch (Frame S, mm): Rastfeld, Einrasten und Beschreibung (Nutzerentscheidung 20.10.2026).
 * S: Ursprung Tischmitte, +x nach rechts (von vorn gesehen), +y zum Roboter hin. Alle Module eines Laufs stehen am
 * Druckplatz, Gier 0, lange Seite zum Roboter.
 *
 * Das Rastfeld spiegelt `SPOT_*` in `core/src/roboprint/planner/params.py`;
 * `core/tests/test_api.py::test_web_spot_grid_matches_core` liest die drei Konstanten mit regulären Ausdrücken.
 */
export const SPOT_STEP_MM = 50;
export const SPOT_X_RANGE_MM: readonly [number, number] = [-200, 200];
export const SPOT_Y_RANGE_MM: readonly [number, number] = [-250, 0];

export interface Spot {
  x: number;
  y: number;
}

/** Tischplatte in S, nur zum Zeichnen. */
export const TABLE_S = { x0: -800, x1: 800, y0: -625, y1: 625 } as const;
/** J1-Achse in S. */
export const ROBOT_AXIS_S: Spot = { x: 0, y: 485 };
/** Radius des Basisfußes um die J1-Achse (Hülle von `base_link` ohne Kabel: x ±91 mm), nur zum Zeichnen. */
export const ROBOT_BASE_R_MM = 90;

function axis([lo, hi]: readonly [number, number]): number[] {
  const n = Math.round((hi - lo) / SPOT_STEP_MM);
  return Array.from({ length: n + 1 }, (_, i) => lo + i * SPOT_STEP_MM);
}

/** Alle Rastpunkte, zeilenweise von der Tischmitte nach vorn. */
export function spotGrid(): Spot[] {
  return axis(SPOT_Y_RANGE_MM)
    .reverse()
    .flatMap((y) => axis(SPOT_X_RANGE_MM).map((x) => ({ x, y })));
}

const clamp = (v: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, v));
const snap = (v: number, range: readonly [number, number]) => clamp(Math.round(v / SPOT_STEP_MM) * SPOT_STEP_MM, range) + 0;

/** Nächster Rastpunkt zu (x, y); außerhalb des Felds der Randpunkt. */
export function snapSpot(x: number, y: number): Spot {
  return { x: snap(x, SPOT_X_RANGE_MM), y: snap(y, SPOT_Y_RANGE_MM) };
}

/** Um (dx, dy) Rastungen verschieben, am Rand des Felds bleiben. */
export function moveSpot(s: Spot, dx: number, dy: number): Spot {
  return snapSpot(s.x + dx * SPOT_STEP_MM, s.y + dy * SPOT_STEP_MM);
}

const mm = (v: number) => `${Math.abs(v).toLocaleString('de-DE')} mm`;

/** „50 mm vor der Tischmitte, mittig“, „Tischmitte, 200 mm rechts“. */
export function describeSpot(s: Spot): string {
  const depth = s.y === 0 ? 'Tischmitte' : `${mm(s.y)} ${s.y < 0 ? 'vor' : 'hinter'} der Tischmitte`;
  const side = s.x === 0 ? 'mittig' : `${mm(s.x)} ${s.x > 0 ? 'rechts' : 'links'}`;
  return `${depth}, ${side}`;
}

/** Abstand der Modulmitte vor der J1-Achse, quer zur Achse nicht mitgezählt. */
export function distanceBeforeRobot(s: Spot): number {
  return ROBOT_AXIS_S.y - s.y;
}

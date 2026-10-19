/** Reine Hilfen für Schritt 2: Modulraster in Wandansicht, Kennzahlen, Fortschritt je Modul. */
import type { PartArtifact } from '../contracts';

export interface Rect {
  x0: number;
  x1: number;
  z0: number;
  z1: number;
}

/**
 * Umriss eines Teils in der Wandansicht (Ebene x–z von L, mm): die acht Ecken der Teil-BBox (Frame P)
 * mit T_LP nach L, davon die Hülle in x und z.
 */
export function partRectInWall(part: Pick<PartArtifact, 'T_LP' | 'bbox_P'>): Rect {
  const { min, max } = part.bbox_P;
  const T = part.T_LP;
  let x0 = Infinity;
  let x1 = -Infinity;
  let z0 = Infinity;
  let z1 = -Infinity;
  for (const px of [min[0], max[0]])
    for (const py of [min[1], max[1]])
      for (const pz of [min[2], max[2]]) {
        const x = T[0][0] * px + T[0][1] * py + T[0][2] * pz + T[0][3];
        const z = T[2][0] * px + T[2][1] * py + T[2][2] * pz + T[2][3];
        x0 = Math.min(x0, x);
        x1 = Math.max(x1, x);
        z0 = Math.min(z0, z);
        z1 = Math.max(z1, z);
      }
  return { x0, x1, z0, z1 };
}

/** Gesamte Druckzeit (s) aus `trajectory.summary.dauer_s` je Teil. */
export function totalPrintTimeS(trajectory: Record<string, { dauer_s: number }>): number {
  return Object.values(trajectory).reduce((a, t) => a + t.dauer_s, 0);
}

/** Dauer als „1 h 05 min“ bzw. „12 min 30 s“ bzw. „45 s“. */
export function formatDuration(s: number): string {
  const total = Math.max(0, Math.round(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h} h ${String(m).padStart(2, '0')} min`;
  if (m > 0) return `${m} min ${String(sec).padStart(2, '0')} s`;
  return `${sec} s`;
}

/** Kleinster Abstand über alle Teile; null, wenn keiner bekannt ist. */
export function minDistance(parts: readonly { d_min_mm: number | null }[]): number | null {
  const v = parts.map((p) => p.d_min_mm).filter((d): d is number => d !== null);
  return v.length ? Math.min(...v) : null;
}

const STAGE_LABELS: Record<string, string> = {
  load: 'Szenario laden',
  ifc: 'Wand einlesen',
  decompose: 'Zerlegen',
  plan: 'Planen & prüfen',
  export: 'Programme schreiben',
  done: 'Fertig',
};

export function stageLabel(stage: string | null): string {
  if (!stage) return 'Wartet auf Start';
  return STAGE_LABELS[stage] ?? stage;
}

export type ModuleState = 'wartet' | 'aktiv' | 'fertig';

/**
 * Fortschritt je Modul aus der Job-Meldung „Teil i/n“ (i zählt ab 1). In der Stufe „plan“ sind die
 * Module vor i fertig, i aktiv, der Rest wartet; danach sind alle fertig, davor wartet noch jedes.
 */
export function moduleProgress(stage: string | null, message: string | null): ModuleState[] | null {
  const m = message ? /Teil\s+(\d+)\s*\/\s*(\d+)/.exec(message) : null;
  if (!m) return null;
  const i = Number(m[1]);
  const n = Number(m[2]);
  if (!(n > 0) || n > 200) return null;
  const past = stage !== null && stage !== 'plan' && stage !== 'decompose' && stage !== 'load' && stage !== 'ifc';
  return Array.from({ length: n }, (_, k): ModuleState => (past || k < i - 1 ? 'fertig' : k === i - 1 && stage === 'plan' ? 'aktiv' : 'wartet'));
}

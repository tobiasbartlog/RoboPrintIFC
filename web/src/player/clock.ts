/**
 * Eine Uhr (SPEC §9): Alles, was der Viewer zu einer Zeit `t` zeigt, kommt aus genau einem
 * Sample-Index `sampleAt(t_s, t)`. Hier liegt die reine Logik ohne React und ohne DOM:
 * Index-Suche, Sample für die Szene, Timeline-Bereiche, Kollisionsliste und Debug-Objekt.
 */
import type { Trajectory } from '../contracts';
import type { SceneSample } from '../scene/types';

export type Status = Trajectory['status'][number];
export type Kind = Trajectory['kind'][number];

/**
 * Index des Samples zur Zeit t: das letzte i mit t_s[i] ≤ t (binäre Suche, t_s streng monoton).
 * Vor dem ersten Sample 0, nach dem letzten N−1, bei leerer Trajektorie −1.
 */
export function sampleAt(tS: readonly number[], t: number): number {
  const n = tS.length;
  if (n === 0) return -1;
  if (!(t >= (tS[0] ?? 0))) return 0;
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if ((tS[mid] ?? Infinity) <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Dauer der Trajektorie (letzter Zeitstempel). */
export function duration(tr: Pick<Trajectory, 't_s'> | null): number {
  if (!tr || tr.t_s.length === 0) return 0;
  return tr.t_s[tr.t_s.length - 1] ?? 0;
}

/** Sample i so, wie die Szene es braucht. */
export function sceneSample(tr: Trajectory, i: number): SceneSample | null {
  const q = tr.q[i];
  const tcp = tr.tcp[i];
  if (!q || !tcp) return null;
  return {
    q,
    tcp,
    layer: tr.layer[i] ?? 0,
    status: tr.status[i] ?? 'ok',
    pair: tr.pair[i] ?? null,
    witness: tr.witness[i] ?? null,
    d_mm: tr.d_mm[i] ?? null,
  };
}

/** Bereich [t0, t1] auf der Zeitachse mit einem Wert (Art, Status oder Schicht). */
export interface Segment<V> {
  value: V;
  i0: number;
  i1: number;
  t0: number;
  t1: number;
}

/**
 * Zusammenhängende Bereiche gleicher Werte. Sample i gilt von t_s[i] bis t_s[i+1] (das letzte
 * Sample bis zum Ende), passend zu `sampleAt`.
 */
export function segments<V>(tS: readonly number[], values: readonly V[], keep: (v: V) => boolean = () => true): Segment<V>[] {
  const out: Segment<V>[] = [];
  const n = Math.min(tS.length, values.length);
  const end = n > 0 ? (tS[n - 1] ?? 0) : 0;
  let start = 0;
  for (let i = 1; i <= n; i++) {
    if (i === n || values[i] !== values[start]) {
      const v = values[start] as V;
      if (keep(v)) {
        out.push({ value: v, i0: start, i1: i - 1, t0: tS[start] ?? 0, t1: i < n ? (tS[i] ?? end) : end });
      }
      start = i;
    }
  }
  return out;
}

export const TRAVEL_KINDS: readonly Kind[] = ['approach', 'retract', 'lift', 'transfer', 'lower'];

/** Bereiche der Bewegungsarten (Druck und die fünf Travel-Arten). */
export function kindSegments(tr: Pick<Trajectory, 't_s' | 'kind'>): Segment<Kind>[] {
  return segments(tr.t_s, tr.kind);
}

/** Nur die auffälligen Status-Bereiche: warn, collision, unreachable. */
export function statusSegments(tr: Pick<Trajectory, 't_s' | 'status'>): Segment<Status>[] {
  return segments(tr.t_s, tr.status, (s) => s !== 'ok');
}

/** Bereiche gleichen Druckstands k (Spur je Schicht). */
export function layerSegments(tr: Pick<Trajectory, 't_s' | 'layer'>): Segment<number>[] {
  return segments(tr.t_s, tr.layer);
}

/** Ein Eintrag der Liste „Kollisionen (n)“: ein zusammenhängender Kollisionsbereich. */
export interface CollisionRange {
  i0: number;
  i1: number;
  t0: number;
  t1: number;
  /** Kritischstes Sample (kleinstes d) im Bereich. */
  iMin: number;
  tMin: number;
  dMin: number;
  link: string;
  obstacle: string;
  layer: number;
  /** Mittelpunkt der Zeugenpunkte am kritischsten Sample (W, mm), für die Kamera. */
  focus: [number, number, number] | null;
}

/** Zusammenhängende Bereiche mit Status `collision`, je Bereich das kritischste Sample. */
export function collisionRanges(
  tr: Pick<Trajectory, 't_s' | 'status' | 'd_mm' | 'pair' | 'witness' | 'layer'>,
): CollisionRange[] {
  return segments(tr.t_s, tr.status, (s) => s === 'collision').map((seg) => {
    let iMin = seg.i0;
    let dMin = Infinity;
    for (let i = seg.i0; i <= seg.i1; i++) {
      const d = tr.d_mm[i];
      if (typeof d === 'number' && d < dMin) {
        dMin = d;
        iMin = i;
      }
    }
    const pair = tr.pair[iMin] ?? null;
    const w = tr.witness[iMin] ?? null;
    return {
      i0: seg.i0,
      i1: seg.i1,
      t0: seg.t0,
      t1: seg.t1,
      iMin,
      tMin: tr.t_s[iMin] ?? seg.t0,
      dMin: Number.isFinite(dMin) ? dMin : NaN,
      link: pair?.[0] ?? 'unbekannt',
      obstacle: pair?.[1] ?? 'unbekannt',
      layer: tr.layer[iMin] ?? 0,
      focus: w ? [(w[0][0] + w[1][0]) / 2, (w[0][1] + w[1][1]) / 2, (w[0][2] + w[1][2]) / 2] : null,
    };
  });
}

/** Rückgabe von `window.__roboprint.debug()` (SPEC §9), genau diese Felder. */
export interface DebugSnapshot {
  t: number;
  sampleIndex: number;
  tcpRendered: [number, number, number] | null;
  tcpArtifact: [number, number, number] | null;
  status: Status | null;
  highlightedLinks: string[];
  obstacleVisible: boolean;
}

export interface DebugInputs {
  t: number;
  trajectory: Pick<Trajectory, 't_s' | 'tcp' | 'status' | 'pair'> | null;
  tcpRendered: readonly number[] | null;
  highlightedLinks: readonly string[];
  showObstacle: boolean;
}

/**
 * Hindernis ist sichtbar, wenn die Anzeige an ist und das Sample eine Warnung oder Kollision mit
 * bekanntem Paar trägt (dieselbe Regel wie in SceneView).
 */
export function obstacleShown(status: Status | null, pair: readonly unknown[] | null | undefined, showObstacle: boolean): boolean {
  return showObstacle && (status === 'collision' || status === 'warn') && !!pair;
}

export function debugSnapshot(d: DebugInputs): DebugSnapshot {
  const tr = d.trajectory;
  const i = tr ? sampleAt(tr.t_s, d.t) : -1;
  const tcp = tr && i >= 0 ? tr.tcp[i] : undefined;
  const status = tr && i >= 0 ? (tr.status[i] ?? null) : null;
  const pair = tr && i >= 0 ? tr.pair[i] : null;
  const r = d.tcpRendered;
  return {
    t: d.t,
    sampleIndex: i,
    tcpRendered: r && r.length >= 3 ? [r[0] ?? 0, r[1] ?? 0, r[2] ?? 0] : null,
    tcpArtifact: tcp ? [tcp[0], tcp[1], tcp[2]] : null,
    status,
    highlightedLinks: [...d.highlightedLinks],
    obstacleVisible: obstacleShown(status, pair, d.showObstacle),
  };
}

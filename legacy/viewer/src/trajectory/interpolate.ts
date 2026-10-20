/**
 * Lineare Interpolation zwischen Trajectory-Samples (ADR-007: kein Kinematik-Rechnen).
 * Der Viewer interpoliert nur zwischen vorhandenen Samples — kein Vorwärtsmodell.
 */

import type { TrajectorySample } from "../artifacts/types";

export interface InterpolatedState {
  t_s: number;
  io: Record<string, number>;
}

/**
 * Interpoliert io-Kanäle linear zwischen den umgebenden Samples.
 * t wird auf [samples[0].t_s, samples[last].t_s] geklemmt.
 */
export function interpolateSample(
  samples: TrajectorySample[],
  t: number,
): InterpolatedState {
  if (samples.length === 0) return { t_s: t, io: {} };
  if (samples.length === 1) return { t_s: samples[0].t_s, io: { ...samples[0].io } };

  const first = samples[0];
  const last = samples[samples.length - 1];
  const tc = Math.max(first.t_s, Math.min(last.t_s, t));

  // Binäre Suche: samples[lo].t_s <= tc < samples[hi].t_s
  let lo = 0;
  let hi = samples.length - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >>> 1;
    if (samples[mid].t_s <= tc) lo = mid;
    else hi = mid;
  }

  const a = samples[lo];
  const b = samples[hi];
  const dt = b.t_s - a.t_s;
  const alpha = dt === 0 ? 0 : (tc - a.t_s) / dt;

  const io: Record<string, number> = {};
  const keys = new Set([...Object.keys(a.io), ...Object.keys(b.io)]);
  for (const k of keys) {
    const va = a.io[k] ?? 0;
    const vb = b.io[k] ?? 0;
    io[k] = va + (vb - va) * alpha;
  }

  return { t_s: tc, io };
}

/** Formatiert Sekunden als "12.3 s", "1:23.4 min" oder "7:28:19 h" (Issue #33). */
export function formatTime(s: number): string {
  // Erst auf Zehntel runden, DANN verzweigen — sonst zeigt 59.97 "60.0 s" und
  // 3599.97 "59:60.0 min" (Übertrag über die Zweiggrenzen, Issue #49).
  const t = Math.round(s * 10) / 10;
  if (t < 60) return `${t.toFixed(1)} s`;
  if (t < 3600) {
    const m = Math.floor(t / 60);
    const sec = (t - m * 60).toFixed(1).padStart(4, "0");
    return `${m}:${sec} min`;
  }
  const total = Math.round(t);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")} h`;
}

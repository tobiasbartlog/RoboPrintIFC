/**
 * Druckfortschritt je Sample: was bis Sample i tatsaechlich gedruckt ist (Nutzerbeobachtung
 * 20.10.2026). Das ist bewusst nicht der Kollisions-Druckstand `layer[i]` = k aus
 * spec/ARTEFAKTE.md: k zaehlt beim Travel die eben gedruckte Schicht schon als fertig und springt
 * deshalb beim Wechsel zur inneren Schale auf L + 1 und danach zurueck auf L. Die Anzeige folgt
 * stattdessen dem Strang:
 *
 * - Volumen: die Schichten von unten, deren Ringe alle ganz gedruckt sind.
 * - Strang: die gedruckten Stuecke (Arten `print` und `link`, Pumpe an) in Druckreihenfolge,
 *   das laufende Stueck anteilig nach der Bogenlaenge des TCP.
 *
 * Beides waechst beim Vorwaertsspielen monoton. Der Status aendert den Fortschritt nicht, auch
 * `unreachable` nicht: Gezeigt wird der geplante Ablauf, der Status steht daneben.
 */
import type { Toolpath, Trajectory } from '../contracts';

/** Ein Stueck des Strangs: der `print`-Abschnitt eines Rings oder ein Verbinder (`link`). */
export interface StrandPiece {
  kind: 'ring' | 'link';
  /** Index in `toolpath.rings`; beim Verbinder der folgende Ring (wie `ring[i]` im Artefakt). */
  ring: number;
  /** Schicht des Rings, beim Verbinder die des folgenden Rings. */
  layer: number;
  /** Erstes und letztes Sample des Stuecks. */
  i0: number;
  i1: number;
}

/** Was bis zu einem Sample gedruckt ist. */
export interface PrintedState {
  /** Fertige Schichten von unten: Alle Ringe dieser Schichten sind ganz gedruckt. */
  layers: number;
  /** Fortschritt in Stuecken: ganzzahliger Teil = fertige Stuecke, Rest = Anteil des laufenden. */
  pos: number;
}

export interface PrintProgress {
  /** Gedruckte Stuecke in Druckreihenfolge (nach Sample). */
  pieces: readonly StrandPiece[];
  /** Schichten des Teils: hoechste bekannte Ringschicht + 1. */
  nLayers: number;
  /** Zustand bei Sample i, i wird auf [0, N − 1] geklemmt. */
  at: (i: number) => PrintedState;
}

type Tr = Pick<Trajectory, 'kind' | 'ring' | 'layer' | 'tcp'>;
type RingLayer = Pick<Toolpath['rings'][number], 'layer'>;

const NOTHING: PrintedState = { layers: 0, pos: 0 };

/** Zusammenhaengende Laeufe gleicher Art und gleichen Rings mit laufender Pumpe. */
function findPieces(tr: Tr, n: number, rings: readonly RingLayer[] | null): StrandPiece[] {
  const pieces: StrandPiece[] = [];
  for (let i = 0; i < n; i++) {
    const k = tr.kind[i];
    if (k !== 'print' && k !== 'link') continue;
    const kind = k === 'print' ? 'ring' : 'link';
    const ring = tr.ring[i] ?? 0;
    const last = pieces[pieces.length - 1];
    if (last && last.i1 === i - 1 && last.kind === kind && last.ring === ring) {
      last.i1 = i;
      continue;
    }
    // Ohne Toolpath gilt k der Samples: bei print und link ist k = L des (folgenden) Rings.
    const layer = rings?.[ring]?.layer ?? tr.layer[i] ?? 0;
    pieces.push({ kind, ring, layer, i0: i, i1: i });
  }
  return pieces;
}

/** Bogenlaenge des TCP bis Sample i (mm). */
function arcLength(tr: Tr, n: number): Float64Array {
  const s = new Float64Array(n);
  for (let i = 1; i < n; i++) {
    const a = tr.tcp[i - 1];
    const b = tr.tcp[i];
    s[i] = (s[i - 1] ?? 0) + (a && b ? Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) : 0);
  }
  return s;
}

/**
 * Fertige Schichten je Sample. Ein Ring ist fertig mit dem letzten Sample seines `print`-Abschnitts;
 * Ringe ohne `print`-Samples werden nie fertig und halten ihre Schicht offen.
 */
function layersPerSample(pieces: readonly StrandPiece[], n: number, rings: readonly RingLayer[] | null) {
  const layerOf = new Map<number, number>();
  if (rings) rings.forEach((r, idx) => layerOf.set(idx, r.layer));
  else for (const p of pieces) if (p.kind === 'ring') layerOf.set(p.ring, p.layer);
  let nLayers = 0;
  for (const l of layerOf.values()) nLayers = Math.max(nLayers, l + 1);

  const open = new Int32Array(nLayers);
  for (const l of layerOf.values()) if (l >= 0) open[l] = (open[l] ?? 0) + 1;
  const doneAt = new Map<number, number>();
  for (const p of pieces) if (p.kind === 'ring') doneAt.set(p.ring, Math.max(doneAt.get(p.ring) ?? -1, p.i1));
  const events = [...doneAt]
    .filter(([ring]) => (layerOf.get(ring) ?? -1) >= 0)
    .map(([ring, i]) => [i, layerOf.get(ring) ?? 0] as const)
    .sort((a, b) => a[0] - b[0]);

  const out = new Int32Array(n);
  let e = 0;
  let k = 0;
  for (let i = 0; i < n; i++) {
    for (; e < events.length && (events[e]?.[0] ?? Infinity) <= i; e++) {
      const l = events[e]?.[1] ?? 0;
      open[l] = (open[l] ?? 0) - 1;
    }
    while (k < nLayers && (open[k] ?? 0) <= 0) k++;
    out[i] = k;
  }
  return { out, nLayers };
}

/** Fortschritt in Stuecken je Sample; das laufende Stueck beginnt am Sample davor (Ringstart). */
function posPerSample(pieces: readonly StrandPiece[], s: Float64Array, n: number): Float64Array {
  const out = new Float64Array(n);
  let j = 0;
  for (let i = 0; i < n; i++) {
    while (j < pieces.length && (pieces[j]?.i1 ?? Infinity) <= i) j++;
    let f = 0;
    const p = pieces[j];
    if (p) {
      // Anker: das Sample vor dem Stueck liegt am Startpunkt (Ende der Anfahrt oder des Verbinders).
      const a = p.i0 > 0 ? p.i0 - 1 : p.i0;
      if (i > a) {
        const total = (s[p.i1] ?? 0) - (s[a] ?? 0);
        f = total > 0 ? Math.min(1, Math.max(0, ((s[i] ?? 0) - (s[a] ?? 0)) / total)) : 1;
      }
    }
    out[i] = j + f;
  }
  return out;
}

/**
 * Druckfortschritt einer Trajektorie. `rings` (aus `toolpath.rings`) liefert die Schicht je Ring
 * und die Ringe, die nie gedruckt werden; ohne Toolpath zaehlen nur die Ringe der Trajektorie.
 */
export function printProgress(tr: Tr, rings?: readonly RingLayer[] | null): PrintProgress {
  const n = Math.min(tr.kind.length, tr.ring.length, tr.tcp.length);
  const ringList = rings ?? null;
  const pieces = findPieces(tr, n, ringList);
  const { out: layers, nLayers } = layersPerSample(pieces, n, ringList);
  const pos = posPerSample(pieces, arcLength(tr, n), n);
  return {
    pieces,
    nLayers,
    at: (i) => {
      if (n === 0) return NOTHING;
      const c = Math.min(Math.max(Math.floor(Number.isFinite(i) ? i : 0), 0), n - 1);
      return { layers: layers[c] ?? 0, pos: pos[c] ?? 0 };
    },
  };
}

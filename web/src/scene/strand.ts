/**
 * Geometrie des Strangs in Frame W (mm), rein und ohne React: die Bahn aller Stuecke in
 * Druckreihenfolge (Ringe aus dem Toolpath, Verbinder als Gerade vom letzten Wegpunkt des
 * vorigen Rings zum ersten des folgenden, spec/ARTEFAKTE.md) und Raupen mit dem Querschnitt
 * Strangbreite x Schichthoehe fuer die laufende Schicht. Der TCP liegt auf der Oberkante der
 * Schicht; die Raupe haengt deshalb um h unter der Bahn. Die Komponenten schneiden nur noch
 * drawRanges zu und setzen die Spitze am laufenden Segment.
 */
import type { Toolpath } from '../contracts';
import type { PrintProgress } from './progress';

/** Polylinie eines Stuecks. */
export interface PiecePath {
  layer: number;
  /** Punkte flach [x, y, z, ...]. */
  points: Float64Array;
  /** Bogenlaenge bis Punkt k. */
  cum: Float64Array;
  /** Waagrechte Einheitsnormale (links der Fahrtrichtung) je Segment, flach [nx, ny, ...]. */
  normals: Float64Array;
  /** Gehrungsvektor je Punkt (Laenge 1/cos des halben Knickwinkels), flach [mx, my, ...]. */
  miters: Float64Array;
}

export interface StrandLayout {
  /** Erst die gedruckten Stuecke (Indizes wie `PrintProgress.pieces`), dann nie gedruckte Ringe. */
  paths: PiecePath[];
  /** Anzahl der gedruckten Stuecke am Anfang von `paths`. */
  printed: number;
}

/** Schnitt am Fortschritt `pos`: laufendes Stueck, fertige Segmente darin und die Spitze. */
export interface StrandCut {
  piece: number;
  segments: number;
  /** Punkt auf dem laufenden Segment, oder null, wenn kein Segment angefangen ist. */
  tip: [number, number, number] | null;
}

/** Vertices je Raupensegment: Oberseite, zwei Flanken, zwei Stirnflaechen (je 2 Dreiecke). */
export const BEAD_VERTS = 30;

/** Einzug der Stirnflaechen (mm), siehe `writeBead`. */
const CAP_INSET = 0.5;
/** Gehrung hoechstens doppelt so breit, damit spitze Knicke nicht ausufern. */
const MITER_MAX = 2;
const EPS = 1e-9;

type P3 = readonly [number, number, number];

function at(points: Float64Array, k: number): [number, number, number] {
  return [points[3 * k] ?? 0, points[3 * k + 1] ?? 0, points[3 * k + 2] ?? 0];
}

function samePoint(a: P3, b: P3): boolean {
  return Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(a[2] - b[2]) < 1e-6;
}

/** Normalen je Segment; senkrechte oder leere Segmente erben die des Nachbarn. */
function segmentNormals(points: Float64Array, nSeg: number): Float64Array {
  const out = new Float64Array(2 * nSeg).fill(Number.NaN);
  for (let k = 0; k < nSeg; k++) {
    const a = at(points, k);
    const b = at(points, k + 1);
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len > 1e-6) {
      out[2 * k] = -dy / len;
      out[2 * k + 1] = dx / len;
    }
  }
  const fill = (k: number, from: number) => {
    out[2 * k] = out[2 * from] ?? 0;
    out[2 * k + 1] = out[2 * from + 1] ?? 0;
  };
  for (let k = 1; k < nSeg; k++) if (Number.isNaN(out[2 * k] ?? 0)) fill(k, k - 1);
  for (let k = nSeg - 2; k >= 0; k--) if (Number.isNaN(out[2 * k] ?? 0)) fill(k, k + 1);
  for (let k = 0; k < 2 * nSeg; k++) if (Number.isNaN(out[k] ?? 0)) out[k] = 0;
  return out;
}

/** Gehrung je Punkt aus den Normalen der angrenzenden Segmente; geschlossene Ringe laufen herum. */
function miterVectors(normals: Float64Array, nSeg: number, closed: boolean): Float64Array {
  const out = new Float64Array(2 * (nSeg + 1));
  const n = (k: number): [number, number] => [normals[2 * k] ?? 0, normals[2 * k + 1] ?? 0];
  for (let k = 0; k <= nSeg; k++) {
    const prev = k > 0 ? k - 1 : closed ? nSeg - 1 : -1;
    const next = k < nSeg ? k : closed ? 0 : -1;
    const a = n(prev >= 0 ? prev : next);
    const b = n(next >= 0 ? next : prev);
    let mx = a[0] + b[0];
    let my = a[1] + b[1];
    const len = Math.hypot(mx, my);
    if (len < 1e-9) {
      [mx, my] = b;
    } else {
      mx /= len;
      my /= len;
      const cos = mx * b[0] + my * b[1];
      const scale = Math.min(MITER_MAX, 1 / Math.max(cos, 1 / MITER_MAX));
      mx *= scale;
      my *= scale;
    }
    out[2 * k] = mx;
    out[2 * k + 1] = my;
  }
  return out;
}

function makePath(layer: number, pts: readonly P3[]): PiecePath {
  const points = new Float64Array(pts.length * 3);
  pts.forEach((p, k) => points.set(p, 3 * k));
  const cum = new Float64Array(pts.length);
  for (let k = 1; k < pts.length; k++) {
    const a = pts[k - 1]!;
    const b = pts[k]!;
    cum[k] = (cum[k - 1] ?? 0) + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
  }
  const nSeg = Math.max(0, pts.length - 1);
  const closed = pts.length > 2 && samePoint(pts[0]!, pts[pts.length - 1]!);
  const normals = segmentNormals(points, nSeg);
  return { layer, points, cum, normals, miters: miterVectors(normals, nSeg, closed) };
}

function ringPoints(ring: Toolpath['rings'][number] | undefined): P3[] {
  if (!ring) return [];
  const pts: P3[] = ring.waypoints.map((w) => [w[0], w[1], w[2]] as const);
  // Geschlossen heisst: der letzte Wegpunkt wiederholt den ersten; fehlt er, wird er ergaenzt.
  if (ring.closed && pts.length > 2 && !samePoint(pts[0]!, pts[pts.length - 1]!)) pts.push(pts[0]!);
  return pts;
}

/**
 * Bahn in Druckreihenfolge. Ohne Fortschritt (keine Trajektorie) stehen alle Ringe in
 * Toolpath-Reihenfolge als ungedruckt da.
 */
export function strandLayout(toolpath: Toolpath, progress: PrintProgress | null): StrandLayout {
  const rings = toolpath.rings;
  const paths: PiecePath[] = [];
  const seen = new Set<number>();
  for (const piece of progress?.pieces ?? []) {
    if (piece.kind === 'ring') {
      seen.add(piece.ring);
      paths.push(makePath(piece.layer, ringPoints(rings[piece.ring])));
    } else {
      const from = rings[piece.ring - 1]?.waypoints;
      const to = rings[piece.ring]?.waypoints;
      const a = from?.[from.length - 1];
      const b = to?.[0];
      paths.push(makePath(piece.layer, a && b ? [[a[0], a[1], a[2]], [b[0], b[1], b[2]]] : []));
    }
  }
  const printed = paths.length;
  rings.forEach((r, idx) => {
    if (!seen.has(idx)) paths.push(makePath(r.layer, ringPoints(r)));
  });
  return { paths, printed };
}

/** Wo der Strang bei Fortschritt `pos` endet. */
export function strandCut(layout: StrandLayout, pos: number): StrandCut {
  const p = Number.isFinite(pos) ? Math.max(pos, 0) : 0;
  const piece = Math.min(Math.floor(p), layout.printed);
  const path = layout.paths[piece];
  const f = p - piece;
  if (piece >= layout.printed || !path || f <= 0) return { piece, segments: 0, tip: null };
  const nSeg = path.cum.length - 1;
  if (nSeg < 1) return { piece, segments: 0, tip: null };
  const target = f * (path.cum[nSeg] ?? 0);
  // Fertig sind die Segmente, deren Ende hoechstens bei `target` liegt (binaere Suche).
  let lo = 0;
  let hi = nSeg;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if ((path.cum[mid] ?? Infinity) <= target + EPS) lo = mid;
    else hi = mid - 1;
  }
  const segments = lo;
  if (segments >= nSeg) return { piece, segments: nSeg, tip: null };
  const c0 = path.cum[segments] ?? 0;
  const c1 = path.cum[segments + 1] ?? c0;
  const u = c1 > c0 ? (target - c0) / (c1 - c0) : 0;
  if (u <= EPS) return { piece, segments, tip: null };
  const a = at(path.points, segments);
  const b = at(path.points, segments + 1);
  return { piece, segments, tip: [a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]), a[2] + u * (b[2] - a[2])] };
}

/** Erster Punkt des laufenden Segments (Anfang der Spitze). */
export function cutStart(layout: StrandLayout, cut: StrandCut): [number, number, number] | null {
  const path = layout.paths[cut.piece];
  return path && cut.tip ? at(path.points, cut.segments) : null;
}

// ---------------------------------------------------------------- Bahnlinien

export interface StrandLines {
  /** Linienstuecke (Punktpaare) aller Pfade in Reihenfolge. */
  positions: Float32Array;
  /** Erster Vertex je Pfad; `start[paths.length]` ist die Gesamtzahl. */
  start: Int32Array;
}

export function strandLines(layout: StrandLayout): StrandLines {
  const start = new Int32Array(layout.paths.length + 1);
  let verts = 0;
  layout.paths.forEach((p, j) => {
    start[j] = verts;
    verts += 2 * Math.max(0, p.cum.length - 1);
  });
  start[layout.paths.length] = verts;
  const positions = new Float32Array(verts * 3);
  let o = 0;
  for (const p of layout.paths) {
    for (let k = 0; k + 1 < p.cum.length; k++) {
      positions.set(p.points.subarray(3 * k, 3 * k + 6), o);
      o += 6;
    }
  }
  return { positions, start };
}

/** Vertices der fertigen Bahn (`start` aus `strandLines`): alle ganzen Segmente bis zum Schnitt. */
export function linesDone(start: Int32Array, cut: StrandCut): number {
  return (start[cut.piece] ?? start[start.length - 1] ?? 0) + 2 * cut.segments;
}

// ---------------------------------------------------------------- Raupen

/** Pfade [from, to) der Schicht `layer` unter den gedruckten Stuecken (Druckreihenfolge). */
export function layerRange(layout: StrandLayout, layer: number): { from: number; to: number } {
  let from = 0;
  while (from < layout.printed && (layout.paths[from]?.layer ?? Infinity) < layer) from++;
  let to = from;
  while (to < layout.printed && (layout.paths[to]?.layer ?? Infinity) <= layer) to++;
  return { from, to };
}

function cross(a: P3, b: P3, c: P3): [number, number, number] {
  const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  const n: [number, number, number] = [
    u[1]! * v[2]! - u[2]! * v[1]!,
    u[2]! * v[0]! - u[0]! * v[2]!,
    u[0]! * v[1]! - u[1]! * v[0]!,
  ];
  const len = Math.hypot(...n) || 1;
  return [n[0] / len, n[1] / len, n[2] / len];
}

/**
 * Ein Raupensegment von a nach b (Oberkante = Bahn), Halbbreiten-Versatz oa bei a und ob bei b
 * (links positiv). Schreibt BEAD_VERTS Vertices und flache Normalen ab Vertex `v`.
 */
export function writeBead(
  pos: Float32Array,
  nrm: Float32Array,
  v: number,
  a: P3,
  b: P3,
  oa: readonly [number, number],
  ob: readonly [number, number],
  height: number,
): void {
  // Stirnflaechen um CAP_INSET eingerueckt: Innen liegen sie in der Nachbarraupe und beruehren deren
  // Oberseite und Flanken nicht (sonst flimmern Naehte an jeder Segmentgrenze).
  const corner = (p: P3, o: readonly [number, number], side: 1 | -1, top: boolean, inset = 0): P3 => {
    const len = Math.hypot(o[0], o[1]);
    const s = len > 0 ? Math.max(0, len - inset) / len : 0;
    return [p[0] + side * s * o[0], p[1] + side * s * o[1], top ? p[2] - inset : p[2] - height + inset];
  };
  const lat = corner(a, oa, 1, true);
  const rat = corner(a, oa, -1, true);
  const lab = corner(a, oa, 1, false);
  const rab = corner(a, oa, -1, false);
  const lbt = corner(b, ob, 1, true);
  const rbt = corner(b, ob, -1, true);
  const lbb = corner(b, ob, 1, false);
  const rbb = corner(b, ob, -1, false);
  const ins = Math.min(CAP_INSET, height / 4);
  const [cla, cra, clat, crat] = [corner(a, oa, 1, false, ins), corner(a, oa, -1, false, ins), corner(a, oa, 1, true, ins), corner(a, oa, -1, true, ins)];
  const [clb, crb, clbt, crbt] = [corner(b, ob, 1, false, ins), corner(b, ob, -1, false, ins), corner(b, ob, 1, true, ins), corner(b, ob, -1, true, ins)];
  // Umlauf gegen den Uhrzeigersinn von aussen gesehen: Oberseite, links, rechts, Anfang, Ende.
  const tris: [P3, P3, P3][] = [
    [lat, rat, rbt],
    [lat, rbt, lbt],
    [lab, lbt, lbb],
    [lab, lat, lbt],
    [rab, rbb, rbt],
    [rab, rbt, rat],
    [cla, cra, crat],
    [cla, crat, clat],
    [crb, clb, clbt],
    [crb, clbt, crbt],
  ];
  let o = 3 * v;
  for (const t of tris) {
    const n = cross(t[0], t[1], t[2]);
    for (const p of t) {
      pos.set(p, o);
      nrm.set(n, o);
      o += 3;
    }
  }
}

/** Versatz (Halbbreite) am Punkt k eines Pfads: Gehrung, an den Enden die Segmentnormale. */
export function offsetAt(path: PiecePath, k: number, halfWidth: number): [number, number] {
  return [(path.miters[2 * k] ?? 0) * halfWidth, (path.miters[2 * k + 1] ?? 0) * halfWidth];
}

export interface BeadBuffer {
  positions: Float32Array;
  normals: Float32Array;
  /** Erster Vertex je Pfad aus [from, to), relativ; letzter Eintrag = Gesamtzahl. */
  start: Int32Array;
  from: number;
  to: number;
}

/** Raupen aller Segmente der Pfade [from, to). */
export function beadBuffer(layout: StrandLayout, from: number, to: number, width: number, height: number): BeadBuffer {
  const paths = layout.paths.slice(from, to);
  const start = new Int32Array(paths.length + 1);
  let verts = 0;
  paths.forEach((p, j) => {
    start[j] = verts;
    verts += BEAD_VERTS * Math.max(0, p.cum.length - 1);
  });
  start[paths.length] = verts;
  const positions = new Float32Array(verts * 3);
  const normals = new Float32Array(verts * 3);
  const hw = width / 2;
  let v = 0;
  for (const p of paths) {
    for (let k = 0; k + 1 < p.cum.length; k++) {
      writeBead(positions, normals, v, at(p.points, k), at(p.points, k + 1), offsetAt(p, k, hw), offsetAt(p, k + 1, hw), height);
      v += BEAD_VERTS;
    }
  }
  return { positions, normals, start, from, to };
}

/** Vertices der fertigen Raupen der Schicht bis zum Schnitt. */
export function beadsDone(buf: BeadBuffer, cut: StrandCut): number {
  const total = buf.start[buf.start.length - 1] ?? 0;
  if (cut.piece < buf.from) return 0;
  if (cut.piece >= buf.to) return total;
  return (buf.start[cut.piece - buf.from] ?? total) + BEAD_VERTS * cut.segments;
}

/** Raupe der Spitze: vom Anfang des laufenden Segments bis zum Schnittpunkt. */
export function writeTipBead(
  pos: Float32Array,
  nrm: Float32Array,
  layout: StrandLayout,
  cut: StrandCut,
  width: number,
  height: number,
): boolean {
  const path = layout.paths[cut.piece];
  const a = cutStart(layout, cut);
  if (!path || !a || !cut.tip) return false;
  const hw = width / 2;
  const n: [number, number] = [(path.normals[2 * cut.segments] ?? 0) * hw, (path.normals[2 * cut.segments + 1] ?? 0) * hw];
  writeBead(pos, nrm, 0, a, cut.tip, offsetAt(path, cut.segments, hw), n, height);
  return true;
}

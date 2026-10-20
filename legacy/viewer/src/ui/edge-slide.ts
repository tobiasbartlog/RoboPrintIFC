/**
 * Kanten-Verschiebung der Roboterbasis (Workstation-Editor): steht der Roboter
 * auf einer Tischfläche **ohne Bohrbild**, landet er per Flächen-Pick immer im
 * Flächen-Mittelpunkt (`mountBaseToSurface`). Dieses Modul erlaubt, ihn an eine
 * **Kante der Standfläche** zu schieben: der Nutzer wählt eine Randkante + einen
 * Abstand (mm), die Basis-Mitte rutscht senkrecht zur Kante auf diesen Abstand.
 *
 * Rein rechnerisch und **three.js-frei** (vitest-prüfbar, Hausmuster wie
 * `face-align.ts`): die Randkanten einer ebenen Region sind die Dreieckskanten,
 * die nur **einem** Region-Dreieck gehören; kollineare Teilstücke werden zu
 * maximalen Segmenten verschmolzen (STL-Soups zerhacken eine Tischkante sonst
 * in viele kleine Stücke). Alle Koordinaten sind Mesh-/Workstation-lokal
 * (mm, ADR-006).
 */

import type { Vec3 } from "./face-align";

/** Eine Randkante der Standfläche als Strecke (Mesh-lokal, mm). */
export interface EdgeSegment {
  a: Vec3;
  b: Vec3;
}

const EPS = 1e-9;
/** Rundung (mm) für den Vertex-Schlüssel — identisch zu `face-align.ts`. */
const VERTEX_KEY_QUANTUM_MM = 1e-3;
/** Max. Richtungs-Abweichung (°) zweier Teilstücke derselben Kante. */
const MERGE_COLLINEAR_TOL_DEG = 1;

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
function length(a: Vec3): number {
  return Math.hypot(a[0], a[1], a[2]);
}
function scale(a: Vec3, s: number): Vec3 {
  return [a[0] * s, a[1] * s, a[2] * s];
}
function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function vertexKey(v: Vec3): string {
  const q = VERTEX_KEY_QUANTUM_MM;
  return `${Math.round(v[0] / q)},${Math.round(v[1] / q)},${Math.round(v[2] / q)}`;
}

/** Ungerichteter Kanten-Schlüssel (Reihenfolge der Endpunkte egal). */
function edgeKey(a: Vec3, b: Vec3): string {
  const ka = vertexKey(a);
  const kb = vertexKey(b);
  return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
}

/**
 * Randkanten einer ebenen Region: Kanten, die genau **ein** Region-Dreieck
 * benutzt (innere Kanten teilen sich zwei Dreiecke). `soup` sind die
 * Dreiecks-Vertices (3 je Dreieck), `triangles` die Region-Dreiecksindizes
 * (aus `PlanarRegionIndex.regionAt`). Kollineare, verbundene Teilstücke sind
 * bereits zu maximalen Segmenten verschmolzen.
 */
export function regionBoundaryEdges(soup: Vec3[], triangles: number[]): EdgeSegment[] {
  const counts = new Map<string, { edge: EdgeSegment; n: number }>();
  for (const t of triangles) {
    const v = [soup[t * 3], soup[t * 3 + 1], soup[t * 3 + 2]];
    for (let k = 0; k < 3; k++) {
      const a = v[k];
      const b = v[(k + 1) % 3];
      const key = edgeKey(a, b);
      const entry = counts.get(key);
      if (entry) entry.n += 1;
      else counts.set(key, { edge: { a, b }, n: 1 });
    }
  }
  const boundary: EdgeSegment[] = [];
  for (const { edge, n } of counts.values()) if (n === 1) boundary.push(edge);
  return mergeCollinearEdges(boundary);
}

/**
 * Verschmilzt verbundene, kollineare Teilstücke zu maximalen Segmenten —
 * die „Tischkante", die der Nutzer meint, statt vieler STL-Splitter.
 * Exportiert für die Tests; `regionBoundaryEdges` ruft sie bereits auf.
 */
export function mergeCollinearEdges(edges: EdgeSegment[]): EdgeSegment[] {
  const cosTol = Math.cos((MERGE_COLLINEAR_TOL_DEG * Math.PI) / 180);
  const segs = edges.map((e) => ({ a: e.a, b: e.b }));
  let merged = true;
  while (merged) {
    merged = false;
    outer: for (let i = 0; i < segs.length; i++) {
      for (let j = i + 1; j < segs.length; j++) {
        const m = tryMerge(segs[i], segs[j], cosTol);
        if (m) {
          segs[i] = m;
          segs.splice(j, 1);
          merged = true;
          break outer;
        }
      }
    }
  }
  return segs;
}

/** Zwei Segmente verschmelzen, wenn sie einen Endpunkt teilen und kollinear sind. */
function tryMerge(s1: EdgeSegment, s2: EdgeSegment, cosTol: number): EdgeSegment | null {
  const d1 = sub(s1.b, s1.a);
  const d2 = sub(s2.b, s2.a);
  const l1 = length(d1);
  const l2 = length(d2);
  if (l1 < EPS || l2 < EPS) return null;
  if (Math.abs(dot(d1, d2)) / (l1 * l2) < cosTol) return null;
  // Geteilten Endpunkt suchen (quantisiert, wie der Region-Index).
  const ends1 = [s1.a, s1.b];
  const ends2 = [s2.a, s2.b];
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 2; j++) {
      if (vertexKey(ends1[i]) === vertexKey(ends2[j])) {
        return { a: ends1[1 - i], b: ends2[1 - j] };
      }
    }
  }
  return null;
}

/** Nächster Punkt auf der Strecke `edge` zu `p` (geklemmt auf das Segment). */
function closestPointOnSegment(edge: EdgeSegment, p: Vec3): Vec3 {
  const d = sub(edge.b, edge.a);
  const len2 = dot(d, d);
  if (len2 < EPS) return edge.a;
  const t = Math.max(0, Math.min(1, dot(sub(p, edge.a), d) / len2));
  return add(edge.a, scale(d, t));
}

/**
 * Die dem Punkt nächste Randkante — für den Kanten-Pick: der Klickpunkt auf
 * dem Mesh wählt die Kante, neben der er liegt. `null` bei leerer Liste.
 */
export function nearestBoundaryEdge(
  edges: EdgeSegment[],
  point: Vec3,
): { edge: EdgeSegment; distanceMm: number } | null {
  let best: { edge: EdgeSegment; distanceMm: number } | null = null;
  for (const edge of edges) {
    const d = length(sub(point, closestPointOnSegment(edge, point)));
    if (!best || d < best.distanceMm) best = { edge, distanceMm: d };
  }
  return best;
}

/**
 * Schiebt die Roboterbasis an die Kante: Ergebnis ist der Punkt in der
 * Standflächen-Ebene, der `distanceMm` **senkrecht zur Kante** ins
 * Flächen-Innere liegt — längs der Kante auf Höhe des Flächen-Mittelpunkts
 * (bei symmetrischen Tischen also mittig an der Kante). Der Abstand misst
 * zur **Basis-Mitte** (dem `robot_base_frame`-Ursprung), nicht zum Fußrand.
 *
 * `interior` ist der Flächen-Mittelpunkt (Region-Zentroid) — er bestimmt
 * sowohl die Längs-Position als auch die Richtung „ins Innere". `null`, wenn
 * die Geometrie entartet ist (Zentroid auf der Kantengeraden).
 */
export function slideToEdge(
  edge: EdgeSegment,
  interior: Vec3,
  distanceMm: number,
): Vec3 | null {
  const d = sub(edge.b, edge.a);
  const len = length(d);
  if (len < EPS) return null;
  const dir = scale(d, 1 / len);
  const foot = closestPointOnSegment(edge, interior);
  const toInterior = sub(interior, foot);
  // Anteil längs der Kante entfernen → reine Senkrecht-Richtung in der Ebene.
  const inwardRaw = sub(toInterior, scale(dir, dot(toInterior, dir)));
  const inwardLen = length(inwardRaw);
  if (inwardLen < EPS) return null;
  return add(foot, scale(inwardRaw, distanceMm / inwardLen));
}

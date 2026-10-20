/**
 * Kleine Strang-Szenarien fuer die Tests, gebaut nach den Regeln aus spec/ARTEFAKTE.md
 * ("Schichten, TCP-Hoehe und Druckstand"): je Schicht zwei Schalen, Ringe als Quadrate,
 * Abtastung entlang der Bahn, `layer[i]` = Kollisions-Druckstand k.
 */
import type { Toolpath, Trajectory } from '../../contracts';

type Pose7 = [number, number, number, number, number, number, number];
type P3 = [number, number, number];
type Kind = Trajectory['kind'][number];

export const H = 10;
export const BEAD = 30;
/** Duesenachse nach unten (Drehung um X um 180 Grad). */
const DOWN = [0, 1, 0, 0] as const;

function square(x0: number, x1: number, z: number): Pose7[] {
  const corners = [
    [x0, x0],
    [x1, x0],
    [x1, x1],
    [x0, x1],
    [x0, x0],
  ];
  return corners.map(([x, y]) => [x!, y!, z, ...DOWN]);
}

/** `layers` Schichten mit je Aussenschale (0..100 mm) und Innenschale (20..80 mm). */
export function twoShellToolpath(layers: number, linkNext: boolean): Toolpath {
  const rings: Toolpath['rings'] = [];
  for (let l = 0; l < layers; l++) {
    const z = (l + 1) * H;
    rings.push({ layer: l, shell: 0, kind: 'outer', closed: true, link_next: linkNext, waypoints: square(0, 100, z) });
    rings.push({ layer: l, shell: 1, kind: 'inner', closed: true, link_next: linkNext, waypoints: square(20, 80, z) });
  }
  const last = rings[rings.length - 1];
  if (last) last.link_next = false;
  return { schema_version: '2', part_id: 'T', layer_height_mm: H, bead_width_mm: BEAD, rings };
}

const xyz = (w: Pose7 | undefined): P3 => [w?.[0] ?? 0, w?.[1] ?? 0, w?.[2] ?? 0];
const up = (p: P3, dz: number): P3 => [p[0], p[1], p[2] + dz];
const lerp = (a: P3, b: P3, u: number): P3 => [a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]), a[2] + u * (b[2] - a[2])];

/**
 * Trajektorie zum Toolpath: Straenge ueber Verbinder, wo `link_next` gilt und `useLinks` an ist,
 * sonst jeder Ring einzeln mit Abheben. Druck-Samples alle `step` mm, ohne den Ringstart (der ist
 * das letzte Sample der Anfahrt oder des Verbinders).
 */
export function buildTrajectory(tp: Toolpath, useLinks: boolean, step = 25): Trajectory {
  const kind: Kind[] = [];
  const ring: number[] = [];
  const layer: number[] = [];
  const pts: P3[] = [];
  const push = (k: Kind, r: number, l: number, p: P3) => {
    kind.push(k);
    ring.push(r);
    layer.push(l);
    pts.push(p);
  };
  const rings = tp.rings;
  const L = (r: number) => rings[r]?.layer ?? 0;
  let r = 0;
  while (r < rings.length) {
    let s = r;
    while (useLinks && s + 1 < rings.length && rings[s]?.link_next) s++;
    const start = xyz(rings[r]?.waypoints[0]);
    // Travel vor dem Strang: aus der Home-Pose k = 0, sonst k = L(vorheriger Ring) + 1.
    const kTravel = r === 0 ? 0 : L(r - 1) + 1;
    push('transfer', r, kTravel, up(start, 120));
    push('transfer', r, kTravel, up(start, 60));
    push('lower', r, kTravel, up(start, 40));
    push('lower', r, kTravel, up(start, 20));
    push('approach', r, L(r), up(start, 10));
    push('approach', r, L(r), start);
    for (let q = r; q <= s; q++) {
      const w = rings[q]?.waypoints ?? [];
      if (q > r) {
        const a = xyz(rings[q - 1]?.waypoints.at(-1));
        const b = xyz(w[0]);
        push('link', q, L(q), lerp(a, b, 0.5));
        push('link', q, L(q), b);
      }
      for (let k = 0; k + 1 < w.length; k++) {
        const a = xyz(w[k]);
        const b = xyz(w[k + 1]);
        const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) / step));
        for (let j = 1; j <= n; j++) push('print', q, L(q), lerp(a, b, j / n));
      }
    }
    const end = xyz(rings[s]?.waypoints.at(-1));
    push('retract', s, L(s), up(end, 10));
    push('retract', s, L(s), up(end, 20));
    push('lift', s, L(s) + 1, up(end, 50));
    r = s + 1;
  }
  const n = kind.length;
  return {
    schema_version: '2',
    part_id: tp.part_id,
    t_s: Array.from({ length: n }, (_, i) => i * 0.1),
    q: Array.from({ length: n }, () => [0, 0, Math.PI / 2, 0, Math.PI / 2, 0]),
    tcp: pts.map((p) => [...p, ...DOWN]),
    layer,
    ring,
    kind,
    branch: Array<number>(n).fill(0),
    status: Array<Trajectory['status'][number]>(n).fill('ok'),
    d_mm: Array<number | null>(n).fill(100),
    pair: Array<[string, string] | null>(n).fill(null),
    witness: Array<null>(n).fill(null),
    psi_rad: Array<number>(n).fill(0),
    summary: { n, n_ok: n, n_warn: 0, n_collision: 0, n_unreachable: 0, d_min_mm: 100, dauer_s: (n - 1) * 0.1, zweig_wechsel_in_ringen: 0 },
  };
}

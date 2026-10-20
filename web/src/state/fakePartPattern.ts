/**
 * Feste Beispieldaten für `fakeApi` (Kennzahlen und Schichtvorschau eines Teils mit Zickzack-Infill).
 * Sie ersetzen die Antwort der API im Fake-Betrieb und in Unit-Tests; es wird nichts gerechnet.
 */
import type { PartLayerPath, PartPatternLayer, PartPatternReport } from '../contracts';

const L = 600;
const D = 200;
const W = 30;

function rect(inset: number): [number, number][] {
  const x = L / 2 - inset;
  const y = D / 2 - inset;
  return [
    [-x, -y],
    [x, -y],
    [x, y],
    [-x, y],
    [-x, -y],
  ];
}

function zigzag(flip: boolean): [number, number][] {
  const pts: [number, number][] = [];
  const x0 = -L / 2 + 60;
  const y = D / 2 - 45;
  for (let i = 0; i <= 8; i++) pts.push([x0 + (i * (L - 120)) / 8, (i % 2 === 0) !== flip ? -y : y]);
  return pts;
}

function path(layer: number): PartLayerPath {
  const flip = layer % 2 === 1;
  const segments: PartLayerPath['segments'] = [
    { ring: 3 * layer, kind: 'outer', shell: 0, closed: true, link_next: true, points: rect(W / 2) },
    { ring: 3 * layer + 1, kind: 'inner', shell: 1, closed: true, link_next: true, points: rect(W / 2 + W) },
    { ring: 3 * layer + 2, kind: 'infill', shell: 2, closed: false, link_next: layer < 4, points: zigzag(flip) },
  ];
  const ordered = flip ? segments.slice().reverse().map((s) => ({ ...s, points: s.points.slice().reverse() })) : segments;
  return {
    layer,
    segments: ordered,
    start: ordered[0]!.points[0]!,
    end: ordered[ordered.length - 1]!.points[ordered[ordered.length - 1]!.points.length - 1]!,
    length_mm: 3200,
  };
}

export function fakePartPatternLayer(partId: string, layer: number): PartPatternLayer {
  const n = 5;
  const l = Math.min(Math.max(layer, 0), n - 1);
  const nb = l + 1 < n ? l + 1 : l - 1;
  return {
    part_id: partId,
    layer: l,
    n_layers: n,
    z_mm: (l + 1) * 10,
    bead_width_mm: W,
    bounds: [
      [-L / 2 + W / 2, -D / 2 + W / 2],
      [L / 2 - W / 2, D / 2 - W / 2],
    ],
    path: path(l),
    neighbor: path(nb),
    neighbor_relation: l + 1 < n ? 'next' : 'previous',
  };
}

export function fakePartPatternReport(partId: string): PartPatternReport {
  return {
    part_id: partId,
    has_pattern: true,
    layer_order: 'alternate',
    infill: 'zickzack',
    outfill: 'none',
    n_layers: 5,
    bead_width_mm: W,
    layer_height_mm: 10,
    v_print_mm_s: 100,
    total_length_mm: 16000,
    print_time_s: 160,
    volume_l: 4.8,
    n_rings: 15,
    n_open_rings: 5,
    n_strands: 1,
    max_strands_per_layer: 1,
    kinds: [
      { kind: 'outer', rings: 5, length_mm: 7600, share: 0.475 },
      { kind: 'inner', rings: 5, length_mm: 5200, share: 0.325 },
      { kind: 'infill', rings: 5, length_mm: 3200, share: 0.2 },
    ],
    layer_changes: { vertical: 4, diagonal: 0, travel: 0, max_offset_mm: 0 },
    layers: [0, 1, 2, 3, 4].map((layer) => ({ layer, rings: 3, strands: 1, length_mm: 3200 })),
  };
}

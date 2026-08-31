import { describe, expect, it } from "vitest";

import {
  applyFrame,
  autoTcpAlongFlangeZ,
  centerAtFlange,
  mountBaseToSurface,
  mountFaceToFlange,
  nozzleQuatFromNormal,
  offsetFrame,
  PlanarRegionIndex,
  planarRegionCentroid,
  quatBetween,
  quatRotate,
  tcpAtDistance,
  tcpAtPosition,
  type Vec3,
} from "./face-align";

const near = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;
const vecNear = (a: Vec3, b: Vec3, eps = 1e-4) => a.every((v, i) => near(v, b[i], eps));

describe("mountBaseToSurface (Roboter auf Fläche, Issue #78)", () => {
  it("richtet die Basis-+z-Achse an der Flächennormale aus (nicht −z wie beim Werkzeug)", () => {
    for (const n of [[0, 0, 1], [1, 0, 0], [0, 1, 0], [0, -1, 0], [0.3, 0.4, 0.866]] as Vec3[]) {
      const f = mountBaseToSurface(n, [0, 0, 0], 0);
      // Basis-+z landet auf der (normalisierten) Flächennormale.
      const nn = Math.hypot(n[0], n[1], n[2]);
      expect(vecNear(quatRotate(f.quat, [0, 0, 1]), [n[0] / nn, n[1] / nn, n[2] / nn])).toBe(true);
    }
  });

  it("setzt den Basis-Ursprung auf den gewählten Flächenpunkt", () => {
    const f = mountBaseToSurface([0, 0, 1], [10, 20, 30], 45);
    expect(f.pos_mm).toEqual([10, 20, 30]);
  });

  it("dreht um die Flächennormale (Drehung wirkt in der Fläche, Basis-z bleibt = Normale)", () => {
    const f = mountBaseToSurface([0, 0, 1], [0, 0, 0], 90);
    expect(vecNear(quatRotate(f.quat, [1, 0, 0]), [0, 1, 0])).toBe(true); // +x → +y
    expect(vecNear(quatRotate(f.quat, [0, 0, 1]), [0, 0, 1])).toBe(true); // z bleibt Normale
  });

  it("ist das Vorzeichen-gedrehte Gegenstück zu mountFaceToFlange", () => {
    const n: Vec3 = [0, 0, 1];
    // Werkzeug: Normale → −Flansch-z; Basis: Normale → +Basis-z.
    expect(vecNear(quatRotate(mountFaceToFlange(n, [0, 0, 0], 0).quat, n), [0, 0, -1])).toBe(true);
    expect(vecNear(quatRotate(mountBaseToSurface(n, [0, 0, 0], 0).quat, [0, 0, 1]), n)).toBe(true);
  });
});

describe("quatBetween", () => {
  it("rotates a vector onto the target direction", () => {
    const q = quatBetween([0, -1, 0], [0, 0, -1]);
    expect(vecNear(quatRotate(q, [0, -1, 0]), [0, 0, -1])).toBe(true);
  });
  it("handles the antiparallel case (180°)", () => {
    const q = quatBetween([0, 0, 1], [0, 0, -1]);
    expect(vecNear(quatRotate(q, [0, 0, 1]), [0, 0, -1])).toBe(true);
  });
  it("is identity for equal directions", () => {
    expect(quatBetween([0, 0, 1], [0, 0, 1])).toEqual([1, 0, 0, 0]);
  });
});

describe("nozzleQuatFromNormal", () => {
  const s = Math.SQRT1_2;
  it("is identity when the opening normal already points along +z", () => {
    expect(nozzleQuatFromNormal([0, 0, 1])).toEqual([1, 0, 0, 0]);
  });
  it("golden: +x opening normal ⇒ 90° about y", () => {
    const q = nozzleQuatFromNormal([1, 0, 0]);
    expect(q.every((v, i) => near(v, [s, 0, s, 0][i]))).toBe(true);
  });
  it("golden: +y opening normal ⇒ −90° about x", () => {
    const q = nozzleQuatFromNormal([0, 1, 0]);
    expect(q.every((v, i) => near(v, [s, -s, 0, 0][i]))).toBe(true);
  });
  it("golden: −z opening normal ⇒ 180° about y", () => {
    const q = nozzleQuatFromNormal([0, 0, -1]);
    expect(q.every((v, i) => near(v, [0, 0, 1, 0][i]))).toBe(true);
  });
  it("maps the TCP z-axis onto any (non-unit) opening normal", () => {
    // Schräge, nicht normierte Normale: die gedrehte z-Achse zeigt entlang ihr.
    const n: Vec3 = [2, -3, 6]; // Länge 7
    const z = quatRotate(nozzleQuatFromNormal(n), [0, 0, 1]);
    expect(vecNear(z, [2 / 7, -3 / 7, 6 / 7])).toBe(true);
  });
});

describe("mountFaceToFlange", () => {
  it("puts the picked face normal into the arm (−z) and the centroid at the origin", () => {
    // extruder30: Montagefläche bei y=-52, Außennormale -y.
    const frame = mountFaceToFlange([0, -1, 0], [0, -52, 0]);
    // Normale -y → -z
    expect(vecNear(quatRotate(frame.quat, [0, -1, 0]), [0, 0, -1])).toBe(true);
    // Zentroid → Ursprung
    expect(vecNear(applyFrame(frame, [0, -52, 0]), [0, 0, 0])).toBe(true);
    // Konkrete Werte des extruder30-Repairs: quat [0.7071,0.7071,0,0], pos [0,0,52]
    expect(vecNear(frame.pos_mm, [0, 0, 52])).toBe(true);
    const s = Math.SQRT1_2;
    expect(frame.quat.every((v, i) => near(v, [s, s, 0, 0][i]))).toBe(true);
  });

  it("body opposite the mounting face extends into +z", () => {
    const frame = mountFaceToFlange([0, -1, 0], [0, -52, 0]);
    // Ein Punkt am Körper (y=150) liegt nach dem Transform bei +z.
    const body = applyFrame(frame, [0, 150, 0]);
    expect(body[2]).toBeGreaterThan(0);
  });

  it("rotationDeg spins about the flange z-axis without tilting the mount", () => {
    const frame = mountFaceToFlange([0, -1, 0], [0, -52, 0], 90);
    // Normale bleibt auf -z (Drehung um z kippt die Montage nicht).
    expect(vecNear(quatRotate(frame.quat, [0, -1, 0]), [0, 0, -1])).toBe(true);
    // Ein x-Punkt der Fläche wandert durch die 90°-z-Drehung nach y.
    const p = applyFrame(frame, [10, -52, 0]);
    expect(near(p[2], 0)).toBe(true); // bleibt in der Flanschebene
  });
});

describe("offsetFrame", () => {
  it("adds a flange-local translation and keeps the rotation (#67)", () => {
    const base = mountFaceToFlange([0, -1, 0], [0, -52, 0]); // pos [0,0,52]
    const shifted = offsetFrame(base, [3, -4, 5]);
    expect(vecNear(shifted.pos_mm, [3, -4, 57])).toBe(true);
    expect(shifted.quat).toEqual(base.quat);
  });

  it("nudges the once-centered face centroid off the origin", () => {
    const base = mountFaceToFlange([0, -1, 0], [0, -52, 0]);
    // Ohne Versatz landet das Zentroid im Ursprung; ein x/y-Versatz schiebt es
    // um genau diesen Betrag in der Flanschebene.
    const shifted = offsetFrame(base, [2, 1, 0]);
    expect(vecNear(applyFrame(shifted, [0, -52, 0]), [2, 1, 0])).toBe(true);
  });

  it("is identity for a zero offset", () => {
    const base = centerAtFlange([[0, 0, 0], [10, 10, 10]]);
    expect(offsetFrame(base, [0, 0, 0])).toEqual(base);
  });
});

describe("autoTcpAlongFlangeZ", () => {
  it("picks the farthest point along +flange-z as the tip", () => {
    const frame = mountFaceToFlange([0, -1, 0], [0, -52, 0]);
    // Vertices der extruder30-Hülle: Spitze bei y=150 → z≈202 nach Transform.
    const verts: Vec3[] = [
      [0, -52, 0],
      [0, 150, 0],
      [30, 40, 10],
    ];
    const tcp = autoTcpAlongFlangeZ(verts, frame);
    expect(near(tcp.pos_mm[2], 202)).toBe(true);
    expect(tcp.quat).toEqual([1, 0, 0, 0]);
  });
  it("throws on empty vertex list", () => {
    expect(() => autoTcpAlongFlangeZ([], mountFaceToFlange([0, 0, 1], [0, 0, 0]))).toThrow();
  });
});

describe("centerAtFlange", () => {
  it("moves the bounding-box center to the flange origin", () => {
    // extruder-artig: y-Bereich [-52, 150] → Mitte y=49; x [-73,74.7]; z [-54.6,54.6].
    const verts: Vec3[] = [
      [-73, -52, -54.6],
      [74.7, 150, 54.6],
      [0, 40, 0],
    ];
    const frame = centerAtFlange(verts);
    // Nach dem Transform liegt die BBox-Mitte im Ursprung.
    const c = applyFrame(frame, [(-73 + 74.7) / 2, (-52 + 150) / 2, 0]);
    expect(vecNear(c, [0, 0, 0], 1e-3)).toBe(true);
    expect(frame.quat).toEqual([1, 0, 0, 0]);
  });

  it("returns identity for empty input", () => {
    expect(centerAtFlange([])).toEqual({ pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] });
  });
});

describe("tcpAtDistance", () => {
  it("places the TCP purely along flange z", () => {
    expect(tcpAtDistance(180)).toEqual({ pos_mm: [0, 0, 180], quat: [1, 0, 0, 0] });
  });
});

describe("tcpAtPosition", () => {
  it("places the TCP at free flange coordinates", () => {
    expect(tcpAtPosition(7.5, -31, 148)).toEqual({ pos_mm: [7.5, -31, 148], quat: [1, 0, 0, 0] });
  });
  it("treats NaN axes (empty inputs) as 0", () => {
    expect(tcpAtPosition(NaN, NaN, 202)).toEqual({ pos_mm: [0, 0, 202], quat: [1, 0, 0, 0] });
  });
});

/** Achsparalleles Rechteck (2 Dreiecke) in der Ebene `axis = level`. */
function quad(axis: 0 | 1 | 2, level: number, u0: number, v0: number, u1: number, v1: number): Vec3[] {
  const p = (u: number, v: number): Vec3 => {
    const out: Vec3 = [0, 0, 0];
    out[axis] = level;
    out[(axis + 1) % 3] = u;
    out[(axis + 2) % 3] = v;
    return out;
  };
  return [p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v0), p(u1, v1), p(u0, v1)];
}

describe("planarRegionCentroid", () => {
  it("returns the center of the whole planar face, not just the clicked triangle", () => {
    // Düsenöffnungs-artige Fläche z=10 aus zwei nebeneinanderliegenden Quads
    // (4 Dreiecke, gemeinsame Kante) — Klick auf Dreieck 0 liefert die Mitte
    // der Gesamtfläche [0..40]×[0..20].
    const soup = [...quad(2, 10, 0, 0, 20, 20), ...quad(2, 10, 20, 0, 40, 20)];
    const face = planarRegionCentroid(soup, 0);
    expect(vecNear(face.centroid, [20, 10, 10], 1e-6)).toBe(true);
    expect(face.triangleCount).toBe(4);
    expect(vecNear(face.normal, [0, 0, 1], 1e-6)).toBe(true);
  });

  it("does not grow into a disconnected coplanar face", () => {
    // Zweite koplanare Fläche ohne gemeinsamen Eckpunkt (Lücke bei x 20..30).
    const soup = [...quad(2, 10, 0, 0, 20, 20), ...quad(2, 10, 30, 0, 50, 20)];
    const face = planarRegionCentroid(soup, 0);
    expect(vecNear(face.centroid, [10, 10, 10], 1e-6)).toBe(true);
    expect(face.triangleCount).toBe(2);
  });

  it("does not grow around an edge onto a differently oriented face", () => {
    // Würfelkante: Deckel z=10 trifft Seitenwand x=20 (teilen Eckpunkte).
    const top = quad(2, 10, 0, 0, 20, 20); // x∈[0,20], y∈[0,20]
    const side = quad(0, 20, 0, 0, 20, 10); // y∈[0,20], z∈[0,10] — enthält (20,·,10)
    const face = planarRegionCentroid([...top, ...side], 0);
    expect(face.triangleCount).toBe(2);
    expect(vecNear(face.centroid, [10, 10, 10], 1e-6)).toBe(true);
  });

  it("throws for an out-of-range start triangle", () => {
    expect(() => planarRegionCentroid(quad(2, 0, 0, 0, 1, 1), 5)).toThrow();
  });
});

describe("PlanarRegionIndex", () => {
  it("caches a region for all of its member triangles (hover stays cheap)", () => {
    const index = new PlanarRegionIndex(quad(2, 10, 0, 0, 20, 20));
    const a = index.regionAt(0);
    const b = index.regionAt(1); // anderes Dreieck derselben Fläche
    expect(b).toBe(a); // identisches, gecachtes Objekt
    expect(a.triangles).toHaveLength(2);
  });

  it("lists the region's triangle indices for highlighting", () => {
    const soup = [...quad(2, 10, 0, 0, 20, 20), ...quad(0, 20, 0, 0, 20, 10)];
    const region = new PlanarRegionIndex(soup).regionAt(0);
    expect([...region.triangles].sort()).toEqual([0, 1]);
  });
});

import { describe, expect, it } from "vitest";

import {
  mergeCollinearEdges,
  nearestBoundaryEdge,
  regionBoundaryEdges,
  slideToEdge,
  type EdgeSegment,
} from "./edge-slide";
import type { Vec3 } from "./face-align";

const near = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;
const vecNear = (a: Vec3, b: Vec3, eps = 1e-4) => a.every((v, i) => near(v, b[i], eps));

/** Ungerichteter Segment-Vergleich (Endpunkt-Reihenfolge egal). */
function sameSegment(s: EdgeSegment, a: Vec3, b: Vec3): boolean {
  return (vecNear(s.a, a) && vecNear(s.b, b)) || (vecNear(s.a, b) && vecNear(s.b, a));
}

/** Achsparalleles Rechteck in der z=0-Ebene als 2-Dreiecks-Soup. */
function quadSoup(x0: number, y0: number, x1: number, y1: number): Vec3[] {
  return [
    [x0, y0, 0], [x1, y0, 0], [x1, y1, 0],
    [x0, y0, 0], [x1, y1, 0], [x0, y1, 0],
  ];
}

describe("regionBoundaryEdges (Randkanten der Standfläche)", () => {
  it("liefert die 4 Außenkanten eines Rechtecks, die Diagonale ist innen", () => {
    const soup = quadSoup(0, 0, 400, 200);
    const edges = regionBoundaryEdges(soup, [0, 1]);
    expect(edges).toHaveLength(4);
    expect(edges.some((e) => sameSegment(e, [0, 0, 0], [400, 0, 0]))).toBe(true);
    expect(edges.some((e) => sameSegment(e, [400, 0, 0], [400, 200, 0]))).toBe(true);
    expect(edges.some((e) => sameSegment(e, [400, 200, 0], [0, 200, 0]))).toBe(true);
    expect(edges.some((e) => sameSegment(e, [0, 200, 0], [0, 0, 0]))).toBe(true);
  });

  it("verschmilzt kollineare Teilstücke einer zerhackten Tischkante", () => {
    // Zwei Quads nebeneinander: die Unter-/Oberkante ist je in 2 Teilstücke
    // gesplittet, die Mittelkante x=200 gehört beiden Quads (innen).
    const soup = [...quadSoup(0, 0, 200, 200), ...quadSoup(200, 0, 400, 200)];
    const edges = regionBoundaryEdges(soup, [0, 1, 2, 3]);
    expect(edges).toHaveLength(4);
    expect(edges.some((e) => sameSegment(e, [0, 0, 0], [400, 0, 0]))).toBe(true);
    expect(edges.some((e) => sameSegment(e, [0, 200, 0], [400, 200, 0]))).toBe(true);
  });
});

describe("mergeCollinearEdges", () => {
  it("kettet drei kollineare Segmente zu einem, senkrechte bleiben eigenständig", () => {
    const merged = mergeCollinearEdges([
      { a: [0, 0, 0], b: [100, 0, 0] },
      { a: [100, 0, 0], b: [250, 0, 0] },
      { a: [250, 0, 0], b: [400, 0, 0] },
      { a: [400, 0, 0], b: [400, 200, 0] },
    ]);
    expect(merged).toHaveLength(2);
    expect(merged.some((e) => sameSegment(e, [0, 0, 0], [400, 0, 0]))).toBe(true);
    expect(merged.some((e) => sameSegment(e, [400, 0, 0], [400, 200, 0]))).toBe(true);
  });

  it("verschmilzt verbundene, aber nicht kollineare Segmente nicht (Ecke bleibt Ecke)", () => {
    const merged = mergeCollinearEdges([
      { a: [0, 0, 0], b: [100, 0, 0] },
      { a: [100, 0, 0], b: [100, 100, 0] },
    ]);
    expect(merged).toHaveLength(2);
  });
});

describe("nearestBoundaryEdge (Kanten-Pick)", () => {
  const rect: EdgeSegment[] = [
    { a: [0, 0, 0], b: [400, 0, 0] },
    { a: [400, 0, 0], b: [400, 200, 0] },
    { a: [400, 200, 0], b: [0, 200, 0] },
    { a: [0, 200, 0], b: [0, 0, 0] },
  ];

  it("wählt die dem Klickpunkt nächste Kante", () => {
    const hit = nearestBoundaryEdge(rect, [390, 100, 0]);
    expect(hit).not.toBeNull();
    expect(sameSegment(hit!.edge, [400, 0, 0], [400, 200, 0])).toBe(true);
    expect(near(hit!.distanceMm, 10)).toBe(true);
  });

  it("liefert null bei leerer Kantenliste", () => {
    expect(nearestBoundaryEdge([], [0, 0, 0])).toBeNull();
  });
});

describe("slideToEdge (Basis an die Kante schieben)", () => {
  it("schiebt mittig an die Unterkante: Abstand senkrecht, längs auf Zentroid-Höhe", () => {
    const p = slideToEdge({ a: [0, 0, 0], b: [400, 0, 0] }, [200, 100, 0], 120);
    expect(p).not.toBeNull();
    expect(vecNear(p!, [200, 120, 0])).toBe(true);
  });

  it("schiebt an die rechte Kante (Richtung zeigt ins Flächen-Innere)", () => {
    const p = slideToEdge({ a: [400, 0, 0], b: [400, 200, 0] }, [200, 100, 0], 50);
    expect(p).not.toBeNull();
    expect(vecNear(p!, [350, 100, 0])).toBe(true);
  });

  it("bleibt bei geneigter Standfläche in deren Ebene (3D, nicht nur z=0)", () => {
    // Ebene aus Kantenrichtung (0,1,0) und (1,0,1)/√2; Zentroid darin.
    const p = slideToEdge({ a: [0, 0, 0], b: [0, 200, 0] }, [100, 100, 100], 10 * Math.SQRT2);
    expect(p).not.toBeNull();
    expect(vecNear(p!, [10, 100, 10])).toBe(true);
  });

  it("Abstand 0 legt die Basis-Mitte direkt auf die Kante", () => {
    const p = slideToEdge({ a: [0, 0, 0], b: [400, 0, 0] }, [200, 100, 0], 0);
    expect(vecNear(p!, [200, 0, 0])).toBe(true);
  });

  it("liefert null bei entarteter Geometrie (Zentroid auf der Kantengeraden)", () => {
    expect(slideToEdge({ a: [0, 0, 0], b: [400, 0, 0] }, [200, 0, 0], 50)).toBeNull();
    expect(slideToEdge({ a: [0, 0, 0], b: [0, 0, 0] }, [200, 100, 0], 50)).toBeNull();
  });
});

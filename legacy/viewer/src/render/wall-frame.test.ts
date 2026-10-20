/**
 * PCA-Wand-Pose (Issue #99): das Wand-lokale System muss der echten Wandachse
 * folgen — nicht den Weltachsen. Der Bug: die Bbox-Näherung („Längsachse =
 * größere horizontale Ausdehnung") ließ Schnittebenen/Quader bei gedrehten
 * Wänden schräg zur Wand liegen und machte sie zu lang (Bbox = Diagonale).
 * Konvention wie im Core (`_wall_local_mesh`): Hauptachse = Wandlänge,
 * Vorzeichen-Fixup Komponentensumme ≥ 0.
 */

import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  WALL_DECORATION_FLAG,
  wallFrameFromObject,
  wallFrameFromPoints,
  wallLocalToGroup,
} from "./wall-frame";

/** Die 8 Ecken eines Wand-Quaders: Länge L um `cx`, Dicke T um `cy`, z 0..H —
 *  optional um `yaw` (um z, um das Zentrum) gedreht. */
function corners(
  L: number,
  T: number,
  H: number,
  cx = 0,
  cy = 0,
  yaw = 0,
): [number, number, number][] {
  const pts: [number, number, number][] = [];
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const z of [0, H]) {
        const dx = (sx * L) / 2;
        const dy = (sy * T) / 2;
        pts.push([cx + c * dx - s * dy, cy + s * dx + c * dy, z]);
      }
    }
  }
  return pts;
}

describe("wallFrameFromPoints: achsparallele Wand (Regressionsfall)", () => {
  const frame = wallFrameFromPoints(corners(4000, 260, 2600, 10, 20))!;

  it("findet Längsachse entlang x (yaw 0) und die echten Maße", () => {
    expect(frame.yaw).toBeCloseTo(0, 6);
    expect(frame.length_mm).toBeCloseTo(4000, 6);
    expect(frame.thickness_mm).toBeCloseTo(260, 6);
    expect(frame.height_mm).toBeCloseTo(2600, 6);
  });

  it("Nullpunkt = Vertex-Mittel, Extent-Mitte relativ dazu 0, Wandfuß z", () => {
    expect(frame.origin.x).toBeCloseTo(10, 6);
    expect(frame.origin.y).toBeCloseTo(20, 6);
    expect(frame.center.x).toBeCloseTo(0, 6);
    expect(frame.center.y).toBeCloseTo(0, 6);
    expect(frame.zMin).toBeCloseTo(0, 6);
  });

  it("Wand entlang y → yaw = π/2 (ersetzt die alte alongX-Fallunterscheidung)", () => {
    const alongY = wallFrameFromPoints(corners(4000, 260, 2600, 0, 0, Math.PI / 2))!;
    expect(alongY.yaw).toBeCloseTo(Math.PI / 2, 6);
    expect(alongY.length_mm).toBeCloseTo(4000, 6);
    expect(alongY.thickness_mm).toBeCloseTo(260, 6);
  });
});

describe("wallFrameFromPoints: gedrehte Wand (der eigentliche Bug, Issue #99)", () => {
  const yaw = Math.PI / 6; // 30°
  const frame = wallFrameFromPoints(corners(4000, 260, 2600, 500, -300, yaw))!;

  it("folgt der echten Wandachse statt der Weltachsen", () => {
    expect(frame.yaw).toBeCloseTo(yaw, 6);
  });

  it("misst die echte Länge, nicht die Bbox-Diagonale", () => {
    // Die achsparallele Bbox einer 30°-Wand wäre ~3594 mm breit in y und
    // ~3594? — entscheidend: length ist exakt 4000, nicht cos/sin-verzerrt.
    expect(frame.length_mm).toBeCloseTo(4000, 6);
    expect(frame.thickness_mm).toBeCloseTo(260, 6);
  });

  it("Vorzeichen deterministisch (Komponentensumme ≥ 0, wie Core-PCA)", () => {
    // Wand entlang 150°: die Hauptachse (−0.866, 0.5) hat Summe < 0 und wird
    // geflippt → yaw = −30°. Gleiche Punktwolke ⇒ gleiche Pose (ADR-004-Geist).
    const flipped = wallFrameFromPoints(corners(4000, 260, 2600, 0, 0, (5 * Math.PI) / 6))!;
    expect(flipped.yaw).toBeCloseTo(-Math.PI / 6, 6);
    expect(Math.cos(flipped.yaw) + Math.sin(flipped.yaw)).toBeGreaterThanOrEqual(0);
  });
});

describe("wallFrameFromPoints: degenerierte Eingaben", () => {
  it("liefert null bei zu wenigen oder ausdehnungslosen Punkten", () => {
    expect(wallFrameFromPoints([])).toBeNull();
    expect(wallFrameFromPoints([[0, 0, 0], [1, 0, 0]])).toBeNull();
    expect(
      wallFrameFromPoints([[5, 5, 0], [5, 5, 0], [5, 5, 0], [5, 5, 0]]),
    ).toBeNull();
  });
});

describe("wallLocalToGroup", () => {
  it("bildet Wand-lokale Punkte über origin+yaw in den Gruppen-Frame ab", () => {
    const frame = wallFrameFromPoints(corners(4000, 260, 2600, 100, 200, Math.PI / 2))!;
    // Wand-lokal +x (Länge) zeigt im Gruppen-Frame nach +y.
    const p = wallLocalToGroup(frame, [1000, 0, 50]);
    expect(p[0]).toBeCloseTo(100, 6);
    expect(p[1]).toBeCloseTo(1200, 6);
    expect(p[2]).toBeCloseTo(50, 6);
  });
});

describe("wallFrameFromObject: gedrehtes Wand-Mesh in der world-Gruppe", () => {
  it("liest die Pose aus den Mesh-Vertices (Issue #99)", () => {
    const world = new THREE.Group();
    // Wand als Box im z-hoch-Datenframe: Länge x, Dicke y, Höhe z.
    const geo = new THREE.BoxGeometry(4000, 260, 2600);
    const mesh = new THREE.Mesh(geo);
    mesh.rotation.z = 0.5;
    mesh.position.set(1200, -400, 1300); // Wandmitte; Fuß bei z=0
    world.add(mesh);

    const frame = wallFrameFromObject(mesh, world)!;
    expect(frame).not.toBeNull();
    expect(frame.yaw).toBeCloseTo(0.5, 5);
    expect(frame.length_mm).toBeCloseTo(4000, 4);
    expect(frame.thickness_mm).toBeCloseTo(260, 4);
    expect(frame.height_mm).toBeCloseTo(2600, 4);
    expect(frame.origin.x).toBeCloseTo(1200, 4);
    expect(frame.origin.y).toBeCloseTo(-400, 4);
    expect(frame.zMin).toBeCloseTo(0, 4);
  });

  it("übergeht Deko-Kinder am Wand-Mesh (Sockel-Streifen #113 verzerrte die PCA)", () => {
    // Regressionsfall Kellerwand 26 cm: eine 32°-Wand trägt seit #113 einen
    // Sockel-Streifen als Kind-Mesh, dessen BoxGeometry aus der ACHSPARALLELEN
    // lokalen Bbox kommt. Ohne Deko-Filter liefen dessen Vertices in die PCA:
    // yaw 32°→22,6°, Dicke 260→2339 mm — alle Overlays lagen schräg zur Wand.
    const world = new THREE.Group();
    const yaw = (32 * Math.PI) / 180;
    // Wand mit gebackenen Welt-Vertices (wie die GLB: Node-Transform = Identität).
    const wallGeo = new THREE.BoxGeometry(2500, 260, 2459)
      .rotateZ(yaw)
      .translate(2936, 9894, -1090);
    const mesh = new THREE.Mesh(wallGeo);
    world.add(mesh);

    // Sockel-Streifen wie in model.ts: 1.02 × lokale (= achsparallele) Bbox.
    wallGeo.computeBoundingBox();
    const bb = wallGeo.boundingBox!;
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry((bb.max.x - bb.min.x) * 1.02, (bb.max.y - bb.min.y) * 1.02, 70),
    );
    strip.position.set((bb.min.x + bb.max.x) / 2, (bb.min.y + bb.max.y) / 2, bb.min.z + 35);
    strip.userData[WALL_DECORATION_FLAG] = true;
    mesh.add(strip);

    const frame = wallFrameFromObject(mesh, world)!;
    expect(frame).not.toBeNull();
    // Toleranz 2 Nachkommastellen: BufferGeometry speichert float32, die
    // gebackenen Welt-Offsets (~10 m) kosten Mantisse (~0,6 µm Fehler).
    expect(frame.yaw).toBeCloseTo(yaw, 4);
    expect(frame.length_mm).toBeCloseTo(2500, 2);
    expect(frame.thickness_mm).toBeCloseTo(260, 2);
  });

  it("ohne Deko-Flag verzerrt ein Kind-Mesh den Frame (Gegenprobe)", () => {
    // Absicherung, dass der Test oben wirklich den Bug abdeckt: dasselbe
    // Kind-Mesh OHNE Flag muss die Pose messbar kippen.
    const world = new THREE.Group();
    const yaw = (32 * Math.PI) / 180;
    const wallGeo = new THREE.BoxGeometry(2500, 260, 2459).rotateZ(yaw);
    const mesh = new THREE.Mesh(wallGeo);
    world.add(mesh);
    wallGeo.computeBoundingBox();
    const bb = wallGeo.boundingBox!;
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry((bb.max.x - bb.min.x) * 1.02, (bb.max.y - bb.min.y) * 1.02, 70),
    );
    strip.position.set(0, 0, bb.min.z + 35);
    mesh.add(strip); // KEIN Deko-Flag

    const frame = wallFrameFromObject(mesh, world)!;
    expect(Math.abs(frame.yaw - yaw)).toBeGreaterThan(0.05);
    expect(frame.thickness_mm).toBeGreaterThan(1000);
  });
});

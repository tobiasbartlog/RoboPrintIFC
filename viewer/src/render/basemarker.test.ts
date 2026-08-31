import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { baseMarkerPosition, type BoxMinMax, buildBaseMarker } from "./basemarker";

describe("baseMarkerPosition", () => {
  // Wand entlang x (breiter als tief): x 0..2000, y 0..300, z 500..1500.
  const boxAlongX: BoxMinMax = { min: [0, 0, 500], max: [2000, 300, 1500] };

  it("legt die Basis lateral entlang der Längsachse und standoff vor die Front", () => {
    const [x, y, z] = baseMarkerPosition(boxAlongX, {
      lateral_mm: 200,
      standoff_mm: 700,
      stand_height_mm: 0,
    });
    // Längsachse = x: lateral verschiebt in x (Mitte 1000 + 200), Normale in y
    // (Mitte 150 + halbe Dicke 150 + standoff 700), z am Fuß der Box.
    expect(x).toBeCloseTo(1200);
    expect(y).toBeCloseTo(1000);
    expect(z).toBeCloseTo(500);
  });

  it("dreht Längs-/Normalachse, wenn die Wand entlang y liegt", () => {
    const boxAlongY: BoxMinMax = { min: [0, 0, 0], max: [300, 2000, 1000] };
    const [x, y, z] = baseMarkerPosition(boxAlongY, {
      lateral_mm: 100,
      standoff_mm: 500,
      stand_height_mm: 0,
    });
    // Längsachse = y: lateral in y (1000 + 100), Normale in x (Mitte 150 +
    // halbe Dicke 150 + standoff 500), z=0.
    expect(x).toBeCloseTo(800);
    expect(y).toBeCloseTo(1100);
    expect(z).toBeCloseTo(0);
  });

  it("die z-Lage springt mit dem Fuß der Abschnitts-Box (Umbau nach oben)", () => {
    const lower: BoxMinMax = { min: [0, 0, 0], max: [2000, 300, 1300] };
    const upper: BoxMinMax = { min: [0, 0, 1300], max: [2000, 300, 2600] };
    const pose = { lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 };
    expect(baseMarkerPosition(lower, pose)[2]).toBeCloseTo(0);
    expect(baseMarkerPosition(upper, pose)[2]).toBeCloseTo(1300);
  });

  it("hebt die Position um die Aufstellhöhe an — die Position IST die Basis (#133)", () => {
    const pose = { lateral_mm: 0, standoff_mm: 700, stand_height_mm: 400 };
    expect(baseMarkerPosition(boxAlongX, pose)[2]).toBeCloseTo(900); // Fuß 500 + 400
  });

  it("Marker == Replay-Anker: halbe Dicke + Abstand ist die Core-Konvention (#160)", () => {
    // Regression Denkmal 2026-07-12: der Core stellt die Basis des Sim-Laufs
    // (trajectory.meta.base_frame) bei y = Dicke/2 + standoff ins Wandsystem
    // (fgc.placement.base_position_in_wall). Der Marker MUSS dieselbe Zahl
    // liefern, sonst lügt die Slicing-Ansicht über die geplante Lage.
    // Denkmal-Zahlen: Wanddicke 510, Abstand 535 → Basis 790 vor der Mittelebene.
    const denkmal: BoxMinMax = { min: [-524, -255, 0], max: [524, 255, 548] };
    const [, y] = baseMarkerPosition(denkmal, {
      lateral_mm: 0,
      standoff_mm: 535,
      stand_height_mm: 0,
    });
    expect(y).toBeCloseTo(790); // == base_frame.pos_mm[1] des Core-Laufs
  });
});

describe("buildBaseMarker", () => {
  const pedestalOf = (group: THREE.Group): THREE.Mesh | undefined =>
    group.children.find(
      (c): c is THREE.Mesh =>
        c instanceof THREE.Mesh && c.geometry instanceof THREE.BoxGeometry,
    );

  it("ohne Aufstellhöhe: kein Podest-Sockel", () => {
    const group = buildBaseMarker({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 });
    expect(pedestalOf(group)).toBeUndefined();
  });

  it("Podest-Sockel reicht von der Basis (Nullpunkt) bis zum Boden (#133)", () => {
    const group = buildBaseMarker({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 400 });
    const pedestal = pedestalOf(group);
    expect(pedestal).toBeDefined();
    // Höhe = Aufstellhöhe 400, Mitte bei −200 → Sockel spannt −400..0
    // (Boden..Basis, da der Gruppen-Nullpunkt auf der Basis-Höhe liegt).
    const geo = pedestal!.geometry as THREE.BoxGeometry;
    expect(geo.parameters.depth).toBeCloseTo(400);
    expect(pedestal!.position.z).toBeCloseTo(-200);
  });

  it("Basis-Scheibe sitzt am Gruppen-Nullpunkt, nicht mehr um die Aufstellhöhe versetzt", () => {
    const group = buildBaseMarker({ lateral_mm: 0, standoff_mm: 700, stand_height_mm: 400 });
    const disc = group.children.find(
      (c): c is THREE.Mesh =>
        c instanceof THREE.Mesh && c.geometry instanceof THREE.CylinderGeometry,
    );
    expect(disc).toBeDefined();
    expect(disc!.position.z).toBeCloseTo(20);
  });
});

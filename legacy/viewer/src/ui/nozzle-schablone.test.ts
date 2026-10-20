import { describe, expect, it } from "vitest";

import { expectGoldenParity } from "../test/golden-parity";
import golden from "./nozzle-schablone.golden.json";
import { NOZZLE_DOWN_QUAT, type Vec3, nozzleQuat } from "./nozzle-quat";
import { pathTangent, schablonePoses } from "./nozzle-schablone";

// --- Golden: bekannte Bahn + Lead/Kipp -> erwartete Posen, OHNE Renderer/IK ------
// Die Quaternionen der Golden kommen aus Core nozzle_quat (gen_goldens.py) —
// dieser Test beweist zugleich, dass die Schablone die *geteilte* Quelle nutzt
// und keine eigene Orientierungsformel (Regressionsschutz #51).
describe("schablonePoses gegen geteilte Core-Golden-Fälle (Issue #85)", () => {
  it("reproduziert jede Golden-Pose bit-nah", () => {
    expectGoldenParity(
      golden.cases,
      (c) => schablonePoses(c.path as Vec3[], { leadRad: c.lead_rad, kippRad: c.kipp_rad }, 30, 8),
      (got, c, label) => {
        const { poses } = got as ReturnType<typeof schablonePoses>;
        expect(poses.length, label).toBe(c.poses.length);
        poses.forEach((pose, i) => {
          const want = c.poses[i];
          for (let k = 0; k < 3; k++) expect(pose.pos_mm[k], `${label} pos[${i}][${k}]`).toBeCloseTo(want.pos_mm[k], 9);
          for (let k = 0; k < 4; k++) expect(pose.quat[k], `${label} quat[${i}][${k}]`).toBeCloseTo(want.quat[k], 9);
        });
      },
    );
  });

  it("pathTangent reproduziert die Golden-Tangente je Bahnpunkt (TS-Hälfte, Issue #194)", () => {
    // Die Tangente steht als Eingabe im Golden; der pytest prüft nozzle_quat(tangent)==quat,
    // hier die Vorwärtsdifferenz — so ist die Schablonen-Halbschleife beidseitig zu.
    expectGoldenParity(
      golden.cases,
      (c) => (c.path as Vec3[]).map((_p, i) => pathTangent(c.path as Vec3[], i)),
      (got, c, label) => expect(got, label).toEqual(c.poses.map((p) => p.tangent)),
    );
  });
});

describe("schablonePoses reuse-Beweis: Pose je Punkt == nozzleQuat der Tangente", () => {
  it("zieht die Orientierung Punkt-für-Punkt aus der geteilten nozzleQuat", () => {
    const path: Vec3[] = [
      [0, 0, 0],
      [50, 0, 0],
      [50, 40, 0],
      [0, 40, 0],
    ];
    const orient = { leadRad: 0.1, kippRad: 0.2 };
    const { poses } = schablonePoses(path, orient, 25, 6);
    poses.forEach((pose, i) => {
      const expected = nozzleQuat(pathTangent(path, i), orient.leadRad, orient.kippRad);
      expect(pose.quat).toEqual(expected);
    });
  });
});

describe("schablonePoses Kanten & Maße", () => {
  it("reicht Wulstdicke (Strangbreite) und Stapelung (Schichthöhe) durch", () => {
    const r = schablonePoses([[0, 0, 0], [10, 0, 0]], { leadRad: 0, kippRad: 0 }, 27, 9);
    expect(r.beadWidthMm).toBe(27);
    expect(r.layerHeightMm).toBe(9);
  });

  it("leere Bahn → keine Posen; einzelner Punkt → senkrecht von oben", () => {
    expect(schablonePoses([], { leadRad: 0, kippRad: 1 }, 1, 1).poses).toEqual([]);
    const single = schablonePoses([[1, 2, 3]], { leadRad: 0.5, kippRad: 0.5 }, 1, 1);
    expect(single.poses).toHaveLength(1);
    expect(single.poses[0].quat).toEqual(NOZZLE_DOWN_QUAT);
  });

  it("letzter Punkt erbt die Tangente des vorletzten (Vorwärtsdifferenz)", () => {
    const path: Vec3[] = [[0, 0, 0], [10, 0, 0], [20, 0, 0]];
    expect(pathTangent(path, 2)).toEqual([10, 0]);
    expect(pathTangent(path, 0)).toEqual([10, 0]);
  });
});

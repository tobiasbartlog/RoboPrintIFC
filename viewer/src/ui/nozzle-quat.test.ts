import { describe, expect, it } from "vitest";

import { expectGoldenParity } from "../test/golden-parity";
import golden from "./nozzle-quat.golden.json";
import { NOZZLE_DOWN_QUAT, type Quat, degToRad, nozzleQuat } from "./nozzle-quat";

function expectQuatClose(got: Quat, want: number[], name: string): void {
  expect(got.length, name).toBe(4);
  for (let i = 0; i < 4; i++) expect(got[i], `${name}[${i}]`).toBeCloseTo(want[i], 12);
}

// --- Py↔TS-Parität: geteilte Golden-Fälle (Core nozzle_quat ist die Wahrheit) ---
describe("nozzleQuat gegen geteilte Core-Golden-Fälle (Issue #85/#61)", () => {
  it("reproduziert jeden Core-Fall bit-gleich", () => {
    expectGoldenParity(
      golden.cases,
      (c) => nozzleQuat(c.tangent as [number, number], c.lead_rad, c.kipp_rad),
      (got, c, label) => expectQuatClose(got as Quat, c.expected, label),
    );
  });
});

describe("nozzleQuat Semantik", () => {
  it("0/0 ist NOZZLE_DOWN, unabhängig von der Tangente", () => {
    for (const t of [[1, 0], [0, 1], [-3, 2], [0, 0]] as [number, number][]) {
      expect(nozzleQuat(t, 0, 0)).toEqual(NOZZLE_DOWN_QUAT);
    }
  });

  it("degenerierte Tangente fällt auf NOZZLE_DOWN zurück", () => {
    expect(nozzleQuat([0, 0], degToRad(20), degToRad(20))).toEqual(NOZZLE_DOWN_QUAT);
  });

  it("+kipp 30° bei +x-Fahrt ist der Golden-Quaternion (sin15°, cos15°, 0, 0)", () => {
    expectQuatClose(
      nozzleQuat([1, 0], 0, degToRad(30)),
      [Math.sin(degToRad(15)), Math.cos(degToRad(15)), 0, 0],
      "kipp30",
    );
  });

  it("liefert kanonische Einheitsquaternionen (w ≥ 0, Norm 1)", () => {
    const q = nozzleQuat([2, -1], degToRad(12), degToRad(7));
    expect(Math.hypot(...q)).toBeCloseTo(1, 12);
    expect(q[0]).toBeGreaterThanOrEqual(0);
  });
});

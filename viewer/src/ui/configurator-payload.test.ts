import { describe, expect, it } from "vitest";

import {
  buildCreateToolRequest,
  buildUpdateToolRequest,
  frameFromPosQuat,
  type ToolFormInput,
} from "./configurator-payload";

function validInput(overrides: Partial<ToolFormInput> = {}): ToolFormInput {
  return {
    name: "Foam Nozzle",
    vendor: "FGC-Lab",
    weightKg: 3.5,
    cogMm: [0, 0, 90],
    channels: [{ name: "pump_a", kind: "analog", description: "Pumpe A" }],
    tcpFrame: { pos_mm: [0, 0, 180], quat: [1, 0, 0, 0] },
    meshTransform: { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] },
    compatibleRobots: [],
    meshFilename: "nozzle.stl",
    meshBase64: "QUJD",
    ...overrides,
  };
}

describe("frameFromPosQuat", () => {
  it("dreht die Quaternion-Reihenfolge {x,y,z,w} → [w,x,y,z] (ADR-006)", () => {
    const frame = frameFromPosQuat({ x: 1, y: 2, z: 3 }, { x: 0.1, y: 0.2, z: 0.3, w: 0.9 });
    expect(frame.pos_mm).toEqual([1, 2, 3]);
    expect(frame.quat).toEqual([0.9, 0.1, 0.2, 0.3]);
  });
});

describe("buildCreateToolRequest", () => {
  it("baut den Request aus gültigen Eingaben", () => {
    const req = buildCreateToolRequest(validInput());
    expect(req.name).toBe("Foam Nozzle");
    expect(req.weight_kg).toBe(3.5);
    expect(req.channels.pump_a).toEqual({ kind: "analog", description: "Pumpe A", default_value: 0 });
    expect(req.tcp_frame.pos_mm).toEqual([0, 0, 180]);
    expect(req.mesh_filename).toBe("nozzle.stl");
  });

  it("trimmt Namen und Kanalnamen", () => {
    const req = buildCreateToolRequest(
      validInput({ name: "  Trim Me  ", channels: [{ name: " pump_a ", kind: "analog", description: "" }] }),
    );
    expect(req.name).toBe("Trim Me");
    expect(Object.keys(req.channels)).toEqual(["pump_a"]);
  });

  it("wirft ohne Namen", () => {
    expect(() => buildCreateToolRequest(validInput({ name: "  " }))).toThrow(/Name/);
  });

  it("wirft ohne Mesh", () => {
    expect(() => buildCreateToolRequest(validInput({ meshBase64: "" }))).toThrow(/Mesh/);
  });

  it("wirft ohne Kanal", () => {
    expect(() => buildCreateToolRequest(validInput({ channels: [] }))).toThrow(/Kanal/);
  });

  it("wirft bei doppeltem Kanalnamen", () => {
    expect(() =>
      buildCreateToolRequest(
        validInput({
          channels: [
            { name: "pump_a", kind: "analog", description: "" },
            { name: "pump_a", kind: "digital", description: "" },
          ],
        }),
      ),
    ).toThrow(/doppelt/);
  });

  it("wirft bei negativem Gewicht", () => {
    expect(() => buildCreateToolRequest(validInput({ weightKg: -1 }))).toThrow(/Gewicht/);
  });

  it("trägt compatible_robots durch und entdoppelt/verwirft leere (#71)", () => {
    const req = buildCreateToolRequest(
      validInput({ compatibleRobots: ["doosan_m1013", " doosan_m1013 ", "  ", "kuka_kr16"] }),
    );
    expect(req.compatible_robots).toEqual(["doosan_m1013", "kuka_kr16"]);
  });

  it("lässt compatible_robots leer, wenn nichts gewählt wurde (= unbekannt, #71)", () => {
    const req = buildCreateToolRequest(validInput({ compatibleRobots: [] }));
    expect(req.compatible_robots).toEqual([]);
  });
});

describe("buildUpdateToolRequest (Edit-Modus, Issue #56)", () => {
  it("lässt das Mesh weg, wenn keins neu gewählt wurde (behält das alte)", () => {
    const req = buildUpdateToolRequest(validInput({ meshBase64: "", meshFilename: "" }));
    expect(req.mesh_base64).toBeUndefined();
    expect(req.mesh_filename).toBeUndefined();
    // Stammdaten/TCP/mesh_transform/Kanäle kommen trotzdem mit.
    expect(req.weight_kg).toBe(3.5);
    expect(req.tcp_frame.pos_mm).toEqual([0, 0, 180]);
    expect(req.mesh_transform.pos_mm).toEqual([0, 0, 0]);
    expect(req.channels.pump_a).toEqual({ kind: "analog", description: "Pumpe A", default_value: 0 });
  });

  it("trägt compatible_robots im Edit-Payload durch (#71)", () => {
    const req = buildUpdateToolRequest(validInput({ compatibleRobots: ["doosan_m1013"] }));
    expect(req.compatible_robots).toEqual(["doosan_m1013"]);
  });

  it("setzt das Mesh, wenn im Editor eins neu hochgeladen wurde", () => {
    const req = buildUpdateToolRequest(validInput({ meshBase64: "REVG", meshFilename: "neu.glb" }));
    expect(req.mesh_base64).toBe("REVG");
    expect(req.mesh_filename).toBe("neu.glb");
  });

  it("enthält keinen Namen (kein Rename, Identität = Pfad)", () => {
    const req = buildUpdateToolRequest(validInput());
    expect((req as unknown as Record<string, unknown>).name).toBeUndefined();
  });

  it("wirft ohne Kanal", () => {
    expect(() => buildUpdateToolRequest(validInput({ channels: [] }))).toThrow(/Kanal/);
  });

  it("wirft bei negativem Gewicht", () => {
    expect(() => buildUpdateToolRequest(validInput({ weightKg: -1 }))).toThrow(/Gewicht/);
  });

  it("wirft bei doppeltem Kanalnamen", () => {
    expect(() =>
      buildUpdateToolRequest(
        validInput({
          channels: [
            { name: "pump_a", kind: "analog", description: "" },
            { name: "pump_a", kind: "digital", description: "" },
          ],
        }),
      ),
    ).toThrow(/doppelt/);
  });
});

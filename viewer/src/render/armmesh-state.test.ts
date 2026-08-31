import { describe, expect, it } from "vitest";

import {
  ARM_LINK_COUNT,
  attributionText,
  effectiveMode,
  initArmRenderState,
  parseArmManifest,
  requestMode,
  toggleEnabled,
  withLoadFailure,
  withMeshesLoaded,
} from "./armmesh-state";

function validManifestRaw() {
  return {
    robot: "doosan_m1013",
    units: "mm",
    upstream: {
      repo: "https://github.com/doosan-robotics/doosan-robot2",
      commit: "ec9242546ec6202835900dbcd8498e2daabfa6a6",
      license: "BSD-3-Clause © Doosan Robotics Inc.",
    },
    links: Array.from({ length: ARM_LINK_COUNT }, (_, i) => ({
      index: i,
      urdf_link: i === 0 ? "base_link" : `link_${i}`,
      file: i === 0 ? "base.glb" : `link${i}.glb`,
    })),
  };
}

describe("parseArmManifest", () => {
  it("liest 7 Glieder samt Upstream aus einem gültigen Manifest", () => {
    const m = parseArmManifest(validManifestRaw());
    expect(m.links).toHaveLength(7);
    expect(m.links[0]).toMatchObject({ index: 0, file: "base.glb" });
    expect(m.links[6]).toMatchObject({ index: 6, file: "link6.glb" });
    expect(m.upstream.license).toContain("BSD-3");
  });

  it("wirft bei falscher Gliederzahl", () => {
    const raw = validManifestRaw();
    raw.links = raw.links.slice(0, 6);
    expect(() => parseArmManifest(raw)).toThrow(/erwarte 7 Glieder/);
  });

  it("wirft, wenn ein Link-Index fehlt (0..6 unvollständig)", () => {
    const raw = validManifestRaw();
    raw.links[3].index = 9; // Index 3 fehlt jetzt
    expect(() => parseArmManifest(raw)).toThrow(/Index 3 fehlt/);
  });

  it("wirft bei fehlender Datei-Angabe", () => {
    const raw = validManifestRaw();
    (raw.links[2] as { file?: string }).file = "";
    expect(() => parseArmManifest(raw)).toThrow(/file/);
  });

  it("wirft bei fehlendem upstream", () => {
    const raw = validManifestRaw() as Record<string, unknown>;
    delete raw.upstream;
    expect(() => parseArmManifest(raw)).toThrow(/upstream/);
  });

  it("wirft bei Nicht-Objekt", () => {
    expect(() => parseArmManifest(null)).toThrow();
    expect(() => parseArmManifest("nope")).toThrow();
  });
});

describe("Render-Modus-Zustand", () => {
  it("startet in Mesh-Wunsch, zeigt aber Schema bis geladen", () => {
    const s = initArmRenderState();
    expect(s.requested).toBe("mesh");
    expect(effectiveMode(s)).toBe("schema"); // noch nicht geladen
    expect(toggleEnabled(s)).toBe(false);
  });

  it("zeigt nach erfolgreichem Load Default Mesh, Umschalter frei", () => {
    const s = withMeshesLoaded(initArmRenderState());
    expect(effectiveMode(s)).toBe("mesh");
    expect(toggleEnabled(s)).toBe(true);
  });

  it("schaltet zwischen Mesh und Schema, wenn geladen", () => {
    let s = withMeshesLoaded(initArmRenderState());
    s = requestMode(s, "schema");
    expect(effectiveMode(s)).toBe("schema");
    s = requestMode(s, "mesh");
    expect(effectiveMode(s)).toBe("mesh");
  });

  it("ignoriert Umschalten, solange nicht geladen", () => {
    const s = requestMode(initArmRenderState(), "schema");
    expect(s.requested).toBe("mesh"); // unverändert, Toggle ohnehin gesperrt
  });

  it("erzwingt bei Ladefehler Schema und sperrt den Umschalter", () => {
    let s = withMeshesLoaded(initArmRenderState());
    s = withLoadFailure(s);
    expect(effectiveMode(s)).toBe("schema");
    expect(toggleEnabled(s)).toBe(false);
    // Auch ein Umschaltversuch bleibt bei Schema.
    s = requestMode(s, "mesh");
    expect(effectiveMode(s)).toBe("schema");
  });
});

describe("attributionText", () => {
  it("fasst Lizenz + Repo + Kurz-Commit zusammen", () => {
    const t = attributionText(parseArmManifest(validManifestRaw()));
    expect(t).toContain("BSD-3");
    expect(t).toContain("doosan-robot2");
    expect(t).toContain("ec9242546e"); // 10-stelliger Kurz-Commit
  });
});

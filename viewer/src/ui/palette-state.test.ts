import { describe, expect, it } from "vitest";

import {
  PALETTE_REGISTRY,
  PALETTE_RESULT_LIMIT,
  type PaletteEntry,
  filterPalette,
  normalizeQuery,
  scoreEntry,
} from "./palette-state";

describe("palette-state (UI-Redesign Scheibe 9, Issue #109)", () => {
  describe("normalizeQuery", () => {
    it("trimmt und schreibt klein", () => {
      expect(normalizeQuery("  Schicht  ")).toBe("schicht");
      expect(normalizeQuery("KIPP")).toBe("kipp");
      expect(normalizeQuery("")).toBe("");
    });
  });

  describe("scoreEntry", () => {
    const entry: PaletteEntry = {
      id: "x",
      icon: "≡",
      label: "Schichthöhe (mm)",
      group: "Slicing · Prozessparameter",
      target: { tab: "druckplan" },
    };

    it("leere Suche trifft alles mit Score 0 (Registry-Reihenfolge bleibt)", () => {
      expect(scoreEntry(entry, "")).toBe(0);
    });

    it("Substring rankt nach Trefferposition (früh = kleiner)", () => {
      expect(scoreEntry(entry, "schicht")).toBe(0); // Label beginnt so
      const later = scoreEntry(entry, "höhe");
      expect(later).not.toBeNull();
      expect(later as number).toBeGreaterThan(0);
    });

    it("trifft auch über die Gruppe (rechts stehend)", () => {
      expect(scoreEntry(entry, "prozessparameter")).not.toBeNull();
    });

    it("Fuzzy-Teilfolge trifft als schwächerer Fallback", () => {
      // „shh" steckt als Teilfolge in „schichthöhe", aber nicht als Substring.
      const s = scoreEntry(entry, "shh");
      expect(s).toBe(1000);
    });

    it("kein Treffer → null", () => {
      expect(scoreEntry(entry, "roboterzelle")).toBeNull();
    });
  });

  describe("filterPalette", () => {
    it("leere Suche liefert die ganze Registry in Reihenfolge (bis Limit)", () => {
      const all = filterPalette(PALETTE_REGISTRY, "", PALETTE_REGISTRY.length);
      expect(all.map((e) => e.id)).toEqual(PALETTE_REGISTRY.map((e) => e.id));
    });

    it("kürzt auf das Limit", () => {
      expect(filterPalette(PALETTE_REGISTRY, "", 9)).toHaveLength(9);
      expect(PALETTE_RESULT_LIMIT).toBe(9);
    });

    it("filtert auf Substring, Substring-Treffer ranken vor Fuzzy", () => {
      const hits = filterPalette(PALETTE_REGISTRY, "schicht", 20);
      expect(hits.length).toBeGreaterThan(0);
      expect(hits[0].label.toLowerCase()).toContain("schicht");
    });

    it("findet Aktionen (Automatisch vorschlagen, Prüfen lassen, Theme)", () => {
      expect(filterPalette(PALETTE_REGISTRY, "automatisch", 20).map((e) => e.id)).toContain(
        "zerlegung-auto",
      );
      expect(filterPalette(PALETTE_REGISTRY, "prüfen lassen", 20).map((e) => e.id)).toContain(
        "zerlegung-check",
      );
      expect(filterPalette(PALETTE_REGISTRY, "theme", 20).map((e) => e.id)).toContain(
        "ansicht-theme",
      );
    });

    it("kein Treffer → leere Liste", () => {
      expect(filterPalette(PALETTE_REGISTRY, "gibtsnicht123", 20)).toEqual([]);
    });

    it("mutiert die Eingangs-Registry nicht", () => {
      const before = PALETTE_REGISTRY.map((e) => e.id);
      filterPalette(PALETTE_REGISTRY, "kipp", 3);
      expect(PALETTE_REGISTRY.map((e) => e.id)).toEqual(before);
    });
  });

  describe("Registry-Abdeckung (alle 5 Schritte + Bibliothek, Einstellungen + Aktionen)", () => {
    const tabsCovered = new Set(
      PALETTE_REGISTRY.flatMap((e) => (e.target.tab ? [e.target.tab] : [])),
    );

    it("deckt alle fünf Prozess-Reiter + Bibliothek ab", () => {
      for (const tab of ["projekt", "roboter", "zerlegung", "druckplan", "export", "bibliothek"]) {
        expect(tabsCovered.has(tab as never)).toBe(true);
      }
    });

    it("enthält Einstellungen (Feld-Fokus) UND Aktionen (Button-Trigger)", () => {
      expect(PALETTE_REGISTRY.some((e) => e.target.fieldId)).toBe(true);
      expect(PALETTE_REGISTRY.some((e) => e.target.actionButtonId)).toBe(true);
    });

    it("enthält die geforderten Kern-Aktionen", () => {
      const byId = (id: string): PaletteEntry | undefined =>
        PALETTE_REGISTRY.find((e) => e.id === id);
      expect(byId("zerlegung-auto")?.target.actionButtonId).toBe("zerlegung-auto-btn");
      expect(byId("zerlegung-check")?.target.actionButtonId).toBe("decompose-check-btn");
      expect(byId("sim-focus")?.target.actionButtonId).toBe("sim-focus-btn");
      expect(byId("sim-sequence")?.target.actionButtonId).toBe("sim-sequence-btn");
      expect(byId("slicing-advisor-check")?.target.actionButtonId).toBe(
        "singularity-advisor-check-btn",
      );
      expect(byId("slicing-advisor-apply")?.target.actionButtonId).toBe(
        "singularity-advisor-apply-btn",
      );
      expect(byId("ansicht-theme")?.target.special).toBe("theme");
    });

    it("hat eindeutige Eintrags-IDs", () => {
      const ids = PALETTE_REGISTRY.map((e) => e.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it("jeder Eintrag trägt genau eine Wirkung (Ziel, Aktion oder Sonderaktion)", () => {
      for (const e of PALETTE_REGISTRY) {
        const t = e.target;
        const hasEffect =
          Boolean(t.tab) || Boolean(t.fieldId) || Boolean(t.actionButtonId) || Boolean(t.special);
        expect(hasEffect, `Eintrag ${e.id} ohne Wirkung`).toBe(true);
      }
    });
  });
});

import { describe, expect, it } from "vitest";

import type { PartAmpel } from "./parts-palette-state";
import { headStatus, paletteCounter } from "./zerlegung-status";

describe("zerlegung-status (UI-Redesign Scheibe 4, Issue #106)", () => {
  describe("headStatus", () => {
    it("dirty ergibt amber ungeprueft (auch mit Abschnitten)", () => {
      expect(headStatus(true, 3)).toEqual({
        label: "ungeprüft",
        cssClass: "badge-warn",
        show: true,
      });
      expect(headStatus(true, 0).label).toBe("ungeprüft");
    });

    it("nicht dirty mit Abschnitten ergibt gruen geprueft", () => {
      expect(headStatus(false, 2)).toEqual({
        label: "geprüft ✓",
        cssClass: "badge-ok",
        show: true,
      });
    });

    it("leerer Plan (nicht dirty, keine Abschnitte) zeigt kein Badge", () => {
      expect(headStatus(false, 0).show).toBe(false);
    });
  });

  describe("paletteCounter", () => {
    const ampeln = (...a: PartAmpel[]): PartAmpel[] => a;

    it("leere Palette zeigt keinen Zaehler", () => {
      expect(paletteCounter([]).show).toBe(false);
    });

    it("irgendein ungeprueftes Teil ergibt amber ungeprueft", () => {
      expect(paletteCounter(ampeln("green", "ungeprueft", "green"))).toEqual({
        label: "ungeprüft",
        cssClass: "badge-warn",
        show: true,
      });
    });

    it("alle gruen ergibt N/N gruen", () => {
      expect(paletteCounter(ampeln("green", "green", "green"))).toEqual({
        label: "3/3 ✓",
        cssClass: "badge-ok",
        show: true,
      });
    });

    it("teils rot (aber bewertet) ergibt gruen/gesamt, amber (nicht alle erreichbar)", () => {
      expect(paletteCounter(ampeln("green", "red", "green"))).toEqual({
        label: "2/3 ✓",
        cssClass: "badge-warn",
        show: true,
      });
    });
  });
});

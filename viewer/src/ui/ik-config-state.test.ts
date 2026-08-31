/**
 * Wählbare IK-Konfiguration (Kollisionskontrolle S4, Issue #129, ADR-024) — reiner
 * Zustand: Formular ↔ Block, sparse Override, per-Achsen-Auflösung (global ⊕ Teil),
 * Vererbungsanzeige + ↺-Reset. Plus der **#83-Anker**: ein Teil-Override betrifft
 * nur dieses Teil — die anderen erben unverändert global (nur dieses Teil veraltet).
 */

import { describe, expect, it } from "vitest";

import {
  IK_AXES,
  emptyIkConfigForm,
  ikAxisView,
  ikConfigFormFromBlock,
  ikConfigFormHasValues,
  ikConfigRequestFromForm,
  readIkAxis,
  resetIkAxis,
  resolveIkConfig,
  setIkAxis,
} from "./ik-config-state";
import {
  emptySectionOverrideForm,
  sectionOverrideForm,
  sectionOverrideFormHasValues,
  sectionOverrideRequestFromForm,
  sectionsRequestFromForms,
} from "./section-params-state";

describe("ik-config-state (Issue #129)", () => {
  it("leeres Formular ist auto/auto/auto (heutiges Verhalten, kein Override)", () => {
    const form = emptyIkConfigForm();
    expect(ikConfigFormHasValues(form)).toBe(false);
    expect(ikConfigRequestFromForm(form)).toEqual({}); // sparse: kein Block
  });

  it("Formular ↔ Block round-trip; nur gesetzte Achsen im Request", () => {
    const form = ikConfigFormFromBlock({ shoulder: "a", wrist: "b" });
    expect(form).toEqual({ shoulder: "a", elbow: null, wrist: "b" });
    expect(ikConfigRequestFromForm(form)).toEqual({ shoulder: "a", wrist: "b" });
    expect(ikConfigFormHasValues(form)).toBe(true);
  });

  it("ungültige/fehlende Achsen werden auto (null)", () => {
    expect(ikConfigFormFromBlock(undefined)).toEqual(emptyIkConfigForm());
    expect(ikConfigFormFromBlock({})).toEqual(emptyIkConfigForm());
  });

  it("setIkAxis/resetIkAxis sind immutable und feldweise", () => {
    const a = emptyIkConfigForm();
    const b = setIkAxis(a, "elbow", "b");
    expect(readIkAxis(a, "elbow")).toBeNull(); // Original unberührt
    expect(readIkAxis(b, "elbow")).toBe("b");
    const c = resetIkAxis(b, "elbow");
    expect(readIkAxis(c, "elbow")).toBeNull();
    expect(ikConfigRequestFromForm(c)).toEqual({});
  });

  it("resolveIkConfig: gesetzte Achse übersteuert, ungesetzte erbt global", () => {
    const global = ikConfigFormFromBlock({ shoulder: "a", elbow: "a" });
    const override = ikConfigFormFromBlock({ elbow: "b" });
    expect(resolveIkConfig(global, override)).toEqual({
      shoulder: "a", // erbt global
      elbow: "b", // übersteuert
      wrist: null, // beide auto
    });
  });

  it("ikAxisView: Vererbungsanzeige + Override-Markierung (#92)", () => {
    const inherit = ikAxisView("a", null);
    expect(inherit).toEqual({ value: "", inheritedLabel: "Zustand A · erbt", overridden: false });
    const over = ikAxisView("a", "b");
    expect(over).toEqual({ value: "b", inheritedLabel: "Zustand A · erbt", overridden: true });
    const autoInherit = ikAxisView(null, null);
    expect(autoInherit.inheritedLabel).toBe("auto · erbt");
  });

  it("deckt genau die drei opw-Achsen ab", () => {
    expect([...IK_AXES]).toEqual(["shoulder", "elbow", "wrist"]);
  });
});

describe("ik_config im Abschnitts-Override — #83-Anker (nur dieses Teil)", () => {
  it("ein Teil-Override trägt ik_config, das Nachbarteil bleibt leer (erbt global)", () => {
    // Teil A übersteuert den Ellbogen; Teil B bleibt komplett leer.
    let formA = emptySectionOverrideForm();
    formA = { ...formA, ikConfig: setIkAxis(formA.ikConfig, "elbow", "b") };
    const formB = emptySectionOverrideForm();

    expect(sectionOverrideFormHasValues(formA)).toBe(true);
    expect(sectionOverrideFormHasValues(formB)).toBe(false);

    const sections = sectionsRequestFromForms({ "abschnitt-1": formA, "abschnitt-2": formB });
    // NUR Teil A trägt einen ik_config-Override → nur dieses Teil veraltet (#83);
    // Teil B ist leer (erbt komplett global).
    expect(sections["abschnitt-1"]).toEqual({ ik_config: { elbow: "b" } });
    expect(sections["abschnitt-2"]).toEqual({});
  });

  it("round-trip über sectionOverrideForm bewahrt den ik_config-Override", () => {
    const restored = sectionOverrideForm({ ik_config: { shoulder: "a" } });
    expect(readIkAxis(restored.ikConfig, "shoulder")).toBe("a");
    expect(sectionOverrideRequestFromForm(restored)).toEqual({ ik_config: { shoulder: "a" } });
  });
});

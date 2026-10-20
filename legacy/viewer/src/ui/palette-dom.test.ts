/**
 * DOM-Vertrag der ⌘K-Befehlspalette (Issue #109): jede in der reinen Registry
 * (`palette-state.ts`) genannte Element-ID MUSS in `index.html` existieren —
 * sonst zielt ein Palette-Eintrag ins Leere (Lehre aus dem Static-Asset-Check:
 * grüne Unit-Tests trotz toter Navigation). Prüft außerdem, dass das Overlay-
 * Gerüst (mit `hidden`) und der Header-Such-Auslöser vorhanden sind.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { PALETTE_REGISTRY } from "./palette-state";

const html = readFileSync(fileURLToPath(new URL("../../index.html", import.meta.url)), "utf-8");

function hasId(id: string): boolean {
  return html.includes(`id="${id}"`);
}

describe("index.html: ⌘K-Befehlspalette (Issue #109)", () => {
  it("das Overlay-Gerüst existiert und startet versteckt (nur `hidden`)", () => {
    expect(html.match(/id="command-palette"/g)).toHaveLength(1);
    // Das Overlay-Root trägt initial das hidden-Attribut (Sichtbarkeit nur so).
    const root = html.slice(html.indexOf('id="command-palette"'));
    const tagEnd = root.indexOf(">");
    expect(root.slice(0, tagEnd)).toContain("hidden");
  });

  it("Eingabefeld + Trefferliste des Overlays existieren", () => {
    expect(hasId("command-palette-input")).toBe(true);
    expect(hasId("command-palette-list")).toBe(true);
  });

  it("die Header-Such-Attrappe existiert (öffnet die Palette)", () => {
    expect(hasId("header-search")).toBe(true);
  });

  it.each(
    PALETTE_REGISTRY.flatMap((e) => {
      const t = e.target;
      const ids: { id: string; kind: string; from: string }[] = [];
      if (t.fieldId) ids.push({ id: t.fieldId, kind: "Feld", from: e.id });
      if (t.actionButtonId) ids.push({ id: t.actionButtonId, kind: "Aktion", from: e.id });
      if (t.accordionToggleId)
        ids.push({ id: t.accordionToggleId, kind: "Accordion", from: e.id });
      return ids;
    }),
  )("$from → $kind #$id existiert in index.html", ({ id }) => {
    expect(hasId(id)).toBe(true);
  });
});

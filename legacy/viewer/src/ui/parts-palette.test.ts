// @vitest-environment jsdom
/**
 * Teile-Palette am 3D-Feld — dünne DOM-Klasse (Issue #91): rendert je Teil
 * Ampel/Name/erreichbar %/▪-Marker/Platzierungs-Override-Select, klappt über
 * `.hidden` ein/aus (nie `style.display`) und meldet Auswahl + Override-Wechsel.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlacementOption } from "../api/projects";
import { PartsPalette } from "./parts-palette";
import type { PartEntry } from "./parts-palette-state";

function setupDom(): void {
  document.body.innerHTML = `
    <aside id="parts-palette" hidden>
      <div class="parts-palette-head">
        <button id="parts-palette-toggle" aria-expanded="true">▾ Teile</button>
      </div>
      <div id="parts-palette-body">
        <p id="parts-palette-empty"></p>
        <ul id="parts-palette-list"></ul>
      </div>
    </aside>
  `;
}

const OPTIONS: PlacementOption[] = [
  { option_id: "stellplatz-1", lateral_mm: 0, standoff_mm: 700, stand_height_mm: 0 },
];

function entry(id: string, over: Partial<PartEntry> = {}): PartEntry {
  return {
    section_id: id,
    order: 1,
    name: `#1 ${id}`,
    ampel: "green",
    printability: null,
    reachable_fraction: 1,
    kinematic_margin: 0.5,
    lateral_mm: 0,
    standoff_mm: 700,
    stand_height_mm: 0,
    has_override: false,
    selected: false,
    module_check: null,
    collision_badge: null,
    ...over,
  };
}

function render(palette: PartsPalette, entries: PartEntry[], override: string | null = null): void {
  palette.render({
    entries,
    options: OPTIONS,
    overrideFor: () => override,
    enabled: true,
  });
}

describe("PartsPalette (Issue #91)", () => {
  beforeEach(setupDom);

  it("rendert je Teil Ampel, erreichbar % und ein Platzierungs-Override-Select", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [entry("a", { ampel: "red", reachable_fraction: 0.42 })]);

    const row = document.querySelector<HTMLElement>(".parts-part");
    expect(row?.classList.contains("red")).toBe(true);
    expect(row?.querySelector(".parts-part-reach")?.textContent).toContain("42 %");
    expect(row?.querySelector("select.parts-part-override")).not.toBeNull();
    expect(document.getElementById("parts-palette-empty")?.hidden).toBe(true);
  });

  it("zeigt den ‚ungeprüft‘-Zustand sichtbar je Teil (Issue #170, dritter Zustand)", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [
      entry("a", {
        ampel: "ungeprueft",
        printability: {
          severity: "unknown",
          presumed: false,
          label: "ungeprüft",
          title: "Ungeprüft: die Kollisions-Prüf-Tür ist fehlgeschlagen",
        },
      }),
    ]);
    const row = document.querySelector<HTMLElement>(".parts-part");
    expect(row?.classList.contains("ungeprueft")).toBe(true);
    // Der offene Ring (◍) unterscheidet ungeprüft von grün/rot (●) und ,vermutlich‘ (◌).
    expect(row?.querySelector(".ampel")?.textContent).toBe("◍");
    const badge = row?.querySelector<HTMLElement>(".parts-part-printability");
    expect(badge?.classList.contains("unknown")).toBe(true);
    expect(badge?.textContent).toBe("ungeprüft");
    expect(badge?.hidden).toBe(false);
  });

  it("zeigt das Teil-Detail mit Platzierungswerten + Marge (Core-Artefakt, #93)", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [
      entry("a", { lateral_mm: 120, standoff_mm: 700, stand_height_mm: 400, kinematic_margin: 0.234 }),
    ]);
    const detail = document.querySelector<HTMLElement>(".parts-part-detail");
    expect(detail?.textContent).toContain("seitl. 120 mm");
    expect(detail?.textContent).toContain("Abstand 700 mm");
    // Issue #133: als absolute Höhe über dem Boden beschriftet, Wert verbatim.
    expect(detail?.textContent).toContain("Aufstellhöhe ü. Boden 400 mm");
    expect(detail?.textContent).toContain("Marge 0.234");
  });

  it("zeigt „—“ als Marge, wenn das Core-Artefakt keine liefert", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [entry("a", { kinematic_margin: null })]);
    expect(document.querySelector<HTMLElement>(".parts-part-detail")?.textContent).toContain("Marge —");
  });

  it("zeigt bei Art modul Gewicht (kg) + Grenzen-Befund je Teil (Issue #90/#95)", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [
      entry("a", {
        module_check: {
          weight_kg: 42.5,
          density_kg_m3: 1900,
          limits: [
            { limit: "max_height", limit_mm: 600, actual_mm: 800, exceeded: true },
          ],
        },
      }),
    ]);
    const mod = document.querySelector<HTMLElement>(".parts-part-module");
    expect(mod?.textContent).toContain("Gewicht 42.5 kg");
    expect(mod?.textContent).toContain("max. Höhe überschritten");
    expect(mod?.classList.contains("exceeded")).toBe(true);
  });

  it("zeigt keinen Modulgrenzen-Befund bei Art abschnitt (module_check null)", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [entry("a", { module_check: null })]);
    expect(document.querySelector(".parts-part-module")).toBeNull();
  });

  it("zeigt den ▪-Marker genau bei gesetztem Override", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, [entry("a", { has_override: true }), entry("b", { has_override: false })]);
    const [rowA, rowB] = Array.from(document.querySelectorAll<HTMLElement>(".parts-part"));
    expect(rowA.querySelector<HTMLElement>(".parts-part-marker")?.hidden).toBe(false);
    expect(rowB.querySelector<HTMLElement>(".parts-part-marker")?.hidden).toBe(true);
  });

  it("markiert das gewählte Teil und meldet den Klick (Auswahl↔Fokus)", () => {
    const onSelect = vi.fn();
    const palette = new PartsPalette({ onSelect, onOverrideChange: vi.fn() });
    render(palette, [entry("a", { selected: true }), entry("b")]);
    const [rowA] = Array.from(document.querySelectorAll<HTMLElement>(".parts-part"));
    expect(rowA.classList.contains("selected")).toBe(true);
    rowA.querySelector<HTMLButtonElement>(".parts-part-name")?.click();
    expect(onSelect).toHaveBeenCalledWith("a");
  });

  it("meldet einen Platzierungs-Override-Wechsel", () => {
    const onOverrideChange = vi.fn();
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange });
    render(palette, [entry("a")]);
    const select = document.querySelector<HTMLSelectElement>(".parts-part-override")!;
    select.value = "stellplatz-1";
    select.dispatchEvent(new Event("change"));
    expect(onOverrideChange).toHaveBeenCalledWith("a", "stellplatz-1");
  });

  it("zeigt den Leerhinweis ohne Teile", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    render(palette, []);
    expect(document.getElementById("parts-palette-empty")?.hidden).toBe(false);
    expect(document.querySelectorAll(".parts-part")).toHaveLength(0);
  });

  it("klappt ein/aus und schaltet die Leiste nur über `.hidden` (nicht style.display)", () => {
    const palette = new PartsPalette({ onSelect: vi.fn(), onOverrideChange: vi.fn() });
    palette.setVisible(true);
    const root = document.getElementById("parts-palette") as HTMLElement;
    const body = document.getElementById("parts-palette-body") as HTMLElement;
    expect(root.hidden).toBe(false);
    expect(palette.collapsed).toBe(false);

    document.getElementById("parts-palette-toggle")?.click();
    expect(palette.collapsed).toBe(true);
    expect(body.hidden).toBe(true);
    expect(body.style.display).toBe(""); // nie über display umgeschaltet
    expect(document.getElementById("parts-palette-toggle")?.getAttribute("aria-expanded")).toBe("false");

    palette.setVisible(false);
    expect(root.hidden).toBe(true);
    expect(root.style.display).toBe("");
  });
});

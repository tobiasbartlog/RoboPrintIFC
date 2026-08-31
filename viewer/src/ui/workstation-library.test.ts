// @vitest-environment jsdom
/**
 * DOM-Struktur-Smoke der Workstation-Galerie + des Formular-Editors (Issue #75).
 * Prüft Karten/Leerzustand, Galerie↔Editor-Umschaltung (nur `.hidden`), den
 * „höhenverstellbar"-Toggle (Liste ↔ min/max) und die exakte Vorbefüllung beim
 * Bearbeiten. Kein three.js, kein Netzwerk.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkstationDef } from "../api/projects";
import { WorkstationLibrary, type WorkstationLibraryCallbacks } from "./workstation-library";

function ws(name: string, overrides: Partial<WorkstationDef> = {}): WorkstationDef {
  return {
    name,
    mobility: "stationary",
    height_adjustable: false,
    base_heights_mm: [0, 150, 300],
    height_range_mm: null,
    safety_min_distance_mm: 50,
    vendor: "",
    compatible_robots: [],
    ...overrides,
  };
}

/** Baut das Workstation-Bibliothek-DOM (die relevanten ids aus index.html). */
function setupDom(): void {
  document.body.innerHTML = `
    <div id="ws-gallery">
      <button id="ws-new-btn"></button>
      <p id="ws-api-warning" hidden></p>
      <p id="ws-status"></p>
      <div id="ws-cards"></div>
      <p id="ws-empty" hidden></p>
    </div>
    <div id="ws-editor" hidden>
      <h2 id="ws-heading"></h2>
      <input id="ws-name" />
      <select id="ws-mobility">
        <option value="stationary">stationary</option>
        <option value="mobile">mobile</option>
      </select>
      <input id="ws-height-adjustable" type="checkbox" />
      <div id="ws-heights-discrete">
        <div id="ws-heights-list"></div>
        <button id="ws-add-height"></button>
      </div>
      <div id="ws-heights-range" hidden>
        <input id="ws-range-min" type="number" />
        <input id="ws-range-max" type="number" />
      </div>
      <input id="ws-safety" type="number" />
      <input id="ws-vendor" />
      <select id="ws-compatible-robots" multiple></select>
      <button id="ws-save-btn"></button>
      <p id="ws-editor-status"></p>
    </div>
  `;
}

function makeLibrary(
  list: WorkstationDef[],
  overrides: Partial<WorkstationLibraryCallbacks> = {},
): { lib: WorkstationLibrary; callbacks: WorkstationLibraryCallbacks } {
  const callbacks: WorkstationLibraryCallbacks = {
    loadWorkstations: vi.fn(async () => list),
    onCreate: vi.fn(async (req) => ws(req.name)),
    onUpdate: vi.fn(async (name) => ws(name)),
    onDelete: vi.fn(async () => {}),
    ...overrides,
  };
  return { lib: new WorkstationLibrary(callbacks), callbacks };
}

describe("WorkstationLibrary — Galerie (Issue #75)", () => {
  beforeEach(setupDom);

  it("rendert je Workstation eine Karte mit Name, Typ-Badge und Höhen-/Abstands-Text", () => {
    const { lib } = makeLibrary([]);
    lib.render([
      ws("zelle_a"),
      ws("mobil_b", {
        mobility: "mobile",
        height_adjustable: true,
        base_heights_mm: [],
        height_range_mm: { min: 200, max: 800 },
      }),
    ]);

    const cards = document.querySelectorAll("#ws-cards .ws-card");
    expect(cards).toHaveLength(2);

    const first = cards[0] as HTMLElement;
    expect(first.querySelector(".lib-card-name")?.textContent).toBe("zelle_a");
    expect(first.querySelector(".ws-card-badge")?.textContent).toBe("stationär");
    expect(first.querySelector(".ws-card-height")?.textContent).toBe("3 Podeste · 0–300 mm");
    expect(first.querySelector(".ws-card-safety")?.textContent).toContain("Sicherheitsabstand");
    expect(first.querySelector("svg")).not.toBeNull();
    expect(first.querySelector(".lib-card-edit")).not.toBeNull();
    expect(first.querySelector(".lib-card-delete")).not.toBeNull();

    const second = cards[1] as HTMLElement;
    expect(second.querySelector(".ws-card-badge")?.textContent).toBe("mobil");
    expect(second.querySelector(".ws-card-height")?.textContent).toBe("verstellbar · 200–800 mm");
  });

  it("zeigt den Leerzustand bei leerer Liste", () => {
    const { lib } = makeLibrary([]);
    lib.render([]);
    expect(document.querySelectorAll("#ws-cards .ws-card")).toHaveLength(0);
    expect((document.getElementById("ws-empty") as HTMLElement).hidden).toBe(false);
  });

  it("blendet den Leerzustand aus, sobald Workstations vorhanden sind", () => {
    const { lib } = makeLibrary([]);
    lib.render([ws("a")]);
    expect((document.getElementById("ws-empty") as HTMLElement).hidden).toBe(true);
  });

  it("schaltet Galerie↔Editor um (nur .hidden)", async () => {
    const { lib } = makeLibrary([]);
    const gallery = document.getElementById("ws-gallery") as HTMLElement;
    const editor = document.getElementById("ws-editor") as HTMLElement;

    lib.openCreate();
    expect(gallery.hidden).toBe(true);
    expect(editor.hidden).toBe(false);

    lib.setApiAvailable(true);
    await lib.openGallery();
    expect(gallery.hidden).toBe(false);
    expect(editor.hidden).toBe(true);
  });

  it("Neue-Workstation-Button öffnet den Editor leer mit einer 0-Podestzeile", () => {
    const { lib } = makeLibrary([]);
    lib; // Button verdrahtet
    (document.getElementById("ws-new-btn") as HTMLButtonElement).click();
    expect((document.getElementById("ws-editor") as HTMLElement).hidden).toBe(false);
    expect(document.getElementById("ws-heading")?.textContent).toBe("Neue Workstation");
    expect((document.getElementById("ws-name") as HTMLInputElement).readOnly).toBe(false);
    const rows = document.querySelectorAll("#ws-heights-list .ws-height-input");
    expect(rows).toHaveLength(1);
    expect((rows[0] as HTMLInputElement).value).toBe("0");
  });

  it("Bearbeiten befüllt exakt vor und sperrt den Namen (kein Rename)", () => {
    const { lib } = makeLibrary([]);
    lib.render([ws("zelle_a", { base_heights_mm: [0, 200], safety_min_distance_mm: 75 })]);
    (document.querySelector(".lib-card-edit") as HTMLButtonElement).click();

    expect(document.getElementById("ws-heading")?.textContent).toBe("Workstation bearbeiten");
    const name = document.getElementById("ws-name") as HTMLInputElement;
    expect(name.value).toBe("zelle_a");
    expect(name.readOnly).toBe(true);
    expect((document.getElementById("ws-safety") as HTMLInputElement).value).toBe("75");
    const rows = document.querySelectorAll("#ws-heights-list .ws-height-input");
    expect(Array.from(rows, (r) => (r as HTMLInputElement).value)).toEqual(["0", "200"]);
  });

  it("höhenverstellbar-Toggle blendet zwischen Podestliste und min/max um (nur .hidden)", () => {
    const { lib } = makeLibrary([]);
    lib.openEdit(
      ws("m", { height_adjustable: true, base_heights_mm: [], height_range_mm: { min: 100, max: 900 } }),
    );
    const discrete = document.getElementById("ws-heights-discrete") as HTMLElement;
    const range = document.getElementById("ws-heights-range") as HTMLElement;
    // verstellbar: Bereich sichtbar, Liste aus
    expect(range.hidden).toBe(false);
    expect(discrete.hidden).toBe(true);
    expect((document.getElementById("ws-range-min") as HTMLInputElement).value).toBe("100");

    // Toggle aus → Liste sichtbar, Bereich aus
    const chk = document.getElementById("ws-height-adjustable") as HTMLInputElement;
    chk.checked = false;
    chk.dispatchEvent(new Event("change"));
    expect(discrete.hidden).toBe(false);
    expect(range.hidden).toBe(true);
  });

  it("+ Podesthöhe fügt eine Zeile hinzu, × entfernt sie", () => {
    const { lib } = makeLibrary([]);
    lib.openCreate();
    (document.getElementById("ws-add-height") as HTMLButtonElement).click();
    expect(document.querySelectorAll("#ws-heights-list .ws-height-input")).toHaveLength(2);
    (document.querySelector("#ws-heights-list .ws-height-remove") as HTMLButtonElement).click();
    expect(document.querySelectorAll("#ws-heights-list .ws-height-input")).toHaveLength(1);
  });

  it("Speichern ruft onCreate mit dem gebauten Request und kehrt zur Galerie zurück", async () => {
    const onCreate = vi.fn(async (req) => ws(req.name));
    const { lib } = makeLibrary([], { onCreate, loadWorkstations: vi.fn(async () => []) });
    lib.setApiAvailable(true);
    lib.openCreate();
    (document.getElementById("ws-name") as HTMLInputElement).value = "zelle_neu";
    (document.getElementById("ws-save-btn") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(onCreate).toHaveBeenCalledOnce();
    expect(onCreate.mock.calls[0][0]).toMatchObject({
      name: "zelle_neu",
      height_adjustable: false,
      base_heights_mm: [0],
    });
    expect((document.getElementById("ws-editor") as HTMLElement).hidden).toBe(true);
  });

  it("Speichern zeigt die Fehlermeldung (z. B. Core-422) und bleibt im Editor", async () => {
    const onCreate = vi.fn(async () => {
      throw new Error("API-Fehler 422: base_heights_mm muss 0 enthalten");
    });
    const { lib } = makeLibrary([], { onCreate });
    lib.setApiAvailable(true);
    lib.openCreate();
    (document.getElementById("ws-name") as HTMLInputElement).value = "zelle_neu";
    (document.getElementById("ws-save-btn") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect((document.getElementById("ws-editor") as HTMLElement).hidden).toBe(false);
    expect(document.getElementById("ws-editor-status")?.textContent).toContain("422");
  });

  it("Löschen ruft nach Bestätigung onDelete mit dem Namen und frischt auf", async () => {
    const onDelete = vi.fn(async () => {});
    const { lib } = makeLibrary([ws("del_me")], {
      onDelete,
      confirmDelete: () => true,
      loadWorkstations: vi.fn(async () => []),
    });
    lib.setApiAvailable(true);
    lib.render([ws("del_me")]);
    (document.querySelector(".lib-card-delete") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(onDelete).toHaveBeenCalledWith("del_me");
  });

  it("Löschen ohne Bestätigung tut nichts", async () => {
    const onDelete = vi.fn(async () => {});
    const { lib } = makeLibrary([ws("del_me")], { onDelete, confirmDelete: () => false });
    lib.render([ws("del_me")]);
    (document.querySelector(".lib-card-delete") as HTMLButtonElement).click();
    await Promise.resolve();
    expect(onDelete).not.toHaveBeenCalled();
  });
});

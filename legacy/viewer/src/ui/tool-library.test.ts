// @vitest-environment jsdom
/**
 * DOM-Struktur-Smoke der Endeffektor-Galerie (Issue #56, Modul 3). Prüft, dass
 * aus einer Tool-Liste die erwarteten Karten (Name/Buttons) entstehen, der
 * Leerzustand bei leerer Liste greift und das Umschalten Galerie↔Editor die
 * jeweils andere Ansicht ausblendet. Kein three.js, kein Netzwerk.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ToolDef } from "../api/projects";
import { ToolLibrary, type ToolLibraryCallbacks } from "./tool-library";

function tool(name: string, overrides: Partial<ToolDef> = {}): ToolDef {
  return {
    name,
    vendor: "FGC-Lab",
    weight_kg: 3.5,
    cog_mm: null,
    mesh: `${name}.stl`,
    mesh_path: `/tools/${name}.stl`,
    mesh_transform: null,
    tcp_frame: { pos_mm: [0, 0, 180], quat: [1, 0, 0, 0] },
    channels: { pump_a: { kind: "analog", description: "", default_value: 0 } },
    compatible_robots: [],
    ...overrides,
  };
}

/** Baut das Bibliothek-DOM (die relevanten ids aus index.html). */
function setupDom(): void {
  document.body.innerHTML = `
    <div id="lib-gallery">
      <button id="lib-new-btn"></button>
      <p id="lib-api-warning" hidden></p>
      <p id="lib-status"></p>
      <div id="lib-cards"></div>
      <p id="lib-empty" hidden></p>
    </div>
    <div id="lib-editor" hidden></div>
  `;
}

function makeLibrary(
  tools: ToolDef[],
  overrides: Partial<ToolLibraryCallbacks> = {},
): { lib: ToolLibrary; callbacks: ToolLibraryCallbacks } {
  const callbacks: ToolLibraryCallbacks = {
    loadTools: vi.fn(async () => tools),
    onNew: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(async () => {}),
    thumbnailFor: vi.fn(async () => null),
    ...overrides,
  };
  return { lib: new ToolLibrary(callbacks), callbacks };
}

describe("ToolLibrary — Galerie (Issue #56)", () => {
  beforeEach(setupDom);

  it("rendert je Endeffektor eine Karte mit Name, Vendor+Gewicht und beiden Buttons", () => {
    const { lib } = makeLibrary([]);
    lib.render([tool("foam_head"), tool("two_component", { vendor: "Acme", weight_kg: 4.2 })]);

    const cards = document.querySelectorAll("#lib-cards .lib-card");
    expect(cards).toHaveLength(2);

    const first = cards[0] as HTMLElement;
    expect(first.querySelector(".lib-card-name")?.textContent).toBe("foam_head");
    expect(first.querySelector(".lib-card-meta")?.textContent).toContain("FGC-Lab");
    expect(first.querySelector(".lib-card-meta")?.textContent).toContain("3.5 kg");
    expect(first.querySelector(".lib-card-edit")).not.toBeNull();
    expect(first.querySelector(".lib-card-delete")).not.toBeNull();

    const second = cards[1] as HTMLElement;
    expect(second.querySelector(".lib-card-meta")?.textContent).toContain("Acme");
    expect(second.querySelector(".lib-card-meta")?.textContent).toContain("4.2 kg");
  });

  it("zeigt den Leerzustand bei leerer Liste (US 24)", () => {
    const { lib } = makeLibrary([]);
    lib.render([]);
    expect(document.querySelectorAll("#lib-cards .lib-card")).toHaveLength(0);
    expect((document.getElementById("lib-empty") as HTMLElement).hidden).toBe(false);
  });

  it("blendet den Leerzustand aus, sobald Endeffektoren vorhanden sind", () => {
    const { lib } = makeLibrary([]);
    lib.render([tool("a")]);
    expect((document.getElementById("lib-empty") as HTMLElement).hidden).toBe(true);
  });

  it("schaltet Galerie↔Editor um (jeweils andere Ansicht ausgeblendet)", () => {
    const { lib } = makeLibrary([]);
    const gallery = document.getElementById("lib-gallery") as HTMLElement;
    const editor = document.getElementById("lib-editor") as HTMLElement;

    lib.showEditor();
    expect(gallery.hidden).toBe(true);
    expect(editor.hidden).toBe(false);

    // openGallery reload braucht API-Verfügbarkeit; hier reicht die Sichtbarkeit.
    lib.setApiAvailable(true);
    return lib.openGallery().then(() => {
      expect(gallery.hidden).toBe(false);
      expect(editor.hidden).toBe(true);
    });
  });

  it("Neuer-Endeffektor-Button öffnet den Editor und meldet onNew (US 5/6)", () => {
    const { lib, callbacks } = makeLibrary([]);
    lib; // konstruiert, Button verdrahtet
    (document.getElementById("lib-new-btn") as HTMLButtonElement).click();
    expect(callbacks.onNew).toHaveBeenCalledOnce();
    expect((document.getElementById("lib-editor") as HTMLElement).hidden).toBe(false);
  });

  it("Bearbeiten-Button meldet den Endeffektor (US 7)", () => {
    const { lib, callbacks } = makeLibrary([]);
    lib.render([tool("edit_me")]);
    (document.querySelector(".lib-card-edit") as HTMLButtonElement).click();
    expect(callbacks.onEdit).toHaveBeenCalledWith(expect.objectContaining({ name: "edit_me" }));
  });

  it("Loeschen-Button fragt erst nach Bestätigung (US 18)", async () => {
    const onDelete = vi.fn(async () => {});
    // Bestätigung abgelehnt → kein Löschen.
    const { lib } = makeLibrary([tool("del_me")], {
      onDelete,
      confirmDelete: () => false,
    });
    lib.render([tool("del_me")]);
    (document.querySelector(".lib-card-delete") as HTMLButtonElement).click();
    await Promise.resolve();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("Loeschen-Button ruft nach Bestätigung onDelete mit dem Namen (US 17/19)", async () => {
    const onDelete = vi.fn(async () => {});
    const { lib } = makeLibrary([tool("del_me")], {
      onDelete,
      confirmDelete: () => true,
      loadTools: vi.fn(async () => []),
    });
    lib.setApiAvailable(true);
    lib.render([tool("del_me")]);
    (document.querySelector(".lib-card-delete") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(onDelete).toHaveBeenCalledWith("del_me");
  });
});

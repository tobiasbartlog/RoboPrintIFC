// @vitest-environment jsdom
/**
 * DOM-Verhalten des Workstation-Panels im Reiter Roboter (Issue #77, PRD #69).
 * Prüft: Dropdown-Befüllung, Ausgrauen inkompatibler Optionen (CSS-Klasse, NICHT
 * disabled → Befund kein Gate), Kompatibilitäts-Warnung bei fremd gewordener Wahl,
 * und die Wiederherstellung der Wahl nach Neuladen (setCurrentWorkstation).
 * Kein three.js, kein Netzwerk.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkstationDef } from "../api/projects";
import { WorkstationPanel } from "./workstation";

const M1013 = "doosan_m1013";
const KR16 = "kuka_kr16";

function ws(name: string, compatible_robots: string[] = []): WorkstationDef {
  return {
    name,
    mobility: "mobile",
    height_adjustable: true,
    base_heights_mm: [],
    height_range_mm: { min: 0, max: 600 },
    safety_min_distance_mm: 80,
    vendor: "FGC",
    compatible_robots,
  };
}

/** Baut das Workstation-Panel-DOM (die relevanten ids aus index.html). */
function setupDom(): void {
  document.body.innerHTML = `
    <p id="wsc-api-warning" hidden></p>
    <select id="wsc-select" disabled></select>
    <dl id="wsc-info"></dl>
    <p id="wsc-saved-for" hidden></p>
    <p id="wsc-compat-warning" hidden></p>
    <button id="wsc-save-btn" disabled></button>
    <p id="wsc-status"></p>
  `;
}

function optionByValue(value: string): HTMLOptionElement {
  const opt = document
    .querySelector<HTMLSelectElement>("#wsc-select")!
    .querySelector<HTMLOptionElement>(`option[value="${value}"]`);
  if (!opt) throw new Error(`Option ${value} fehlt`);
  return opt;
}

describe("WorkstationPanel (Issue #77)", () => {
  beforeEach(() => setupDom());

  it("befüllt das Dropdown aus dem Katalog", () => {
    const panel = new WorkstationPanel({ onSaveWorkstation: vi.fn() });
    panel.setWorkstations([ws("mobile_hub"), ws("zelle_fest")]);
    const options = Array.from(
      document.querySelector<HTMLSelectElement>("#wsc-select")!.options,
    ).map((o) => o.value);
    expect(options).toEqual(["mobile_hub", "zelle_fest"]);
  });

  it("graut inkompatible Optionen aus (CSS-Klasse), lässt sie aber wählbar", () => {
    const panel = new WorkstationPanel({ onSaveWorkstation: vi.fn() });
    panel.setWorkstations([ws("passt", [M1013]), ws("fremd", [KR16]), ws("ungetaggt")]);
    panel.setActiveRobot(M1013);

    expect(optionByValue("fremd").classList.contains("option-incompatible")).toBe(true);
    expect(optionByValue("passt").classList.contains("option-incompatible")).toBe(false);
    expect(optionByValue("ungetaggt").classList.contains("option-incompatible")).toBe(false);
    // Kein Gate: nicht disabled — die inkompatible Option bleibt wählbar.
    expect(optionByValue("fremd").disabled).toBe(false);
  });

  it("entgraut wieder, wenn der Roboter zurück auf unbekannt geht", () => {
    const panel = new WorkstationPanel({ onSaveWorkstation: vi.fn() });
    panel.setWorkstations([ws("fremd", [KR16])]);
    panel.setActiveRobot(M1013);
    expect(optionByValue("fremd").classList.contains("option-incompatible")).toBe(true);
    panel.setActiveRobot(null);
    expect(optionByValue("fremd").classList.contains("option-incompatible")).toBe(false);
  });

  it("warnt, wenn die gewählte Workstation durch einen Roboterwechsel fremd wird (kein Auto-Reset)", () => {
    const panel = new WorkstationPanel({ onSaveWorkstation: vi.fn() });
    panel.setWorkstations([ws("fremd", [KR16])]);
    panel.setCurrentWorkstation("fremd");
    panel.setActiveRobot(M1013);

    const warn = document.querySelector<HTMLElement>("#wsc-compat-warning")!;
    expect(warn.hidden).toBe(false);
    expect(warn.textContent).toMatch(/Kompatibilitäts-Warnung/);
    // Kein Auto-Reset: die Wahl bleibt bestehen.
    expect(document.querySelector<HTMLSelectElement>("#wsc-select")!.value).toBe("fremd");
  });

  it("stellt die gespeicherte Wahl nach Neuladen wieder her (setCurrentWorkstation)", () => {
    const panel = new WorkstationPanel({ onSaveWorkstation: vi.fn() });
    panel.setWorkstations([ws("mobile_hub"), ws("zelle_fest")]);
    // Simuliert das Öffnen eines Projekts, dessen Druckjob workstation="zelle_fest" trägt.
    panel.setCurrentWorkstation("zelle_fest");

    expect(document.querySelector<HTMLSelectElement>("#wsc-select")!.value).toBe("zelle_fest");
    const savedFor = document.querySelector<HTMLElement>("#wsc-saved-for")!;
    expect(savedFor.hidden).toBe(false);
    expect(savedFor.textContent).toContain("zelle_fest");
  });

  it("persistiert über onSaveWorkstation beim Klick auf Speichern", async () => {
    const onSaveWorkstation = vi.fn(async () => ({ compatible: true as boolean | null }));
    const panel = new WorkstationPanel({ onSaveWorkstation });
    panel.setWorkstations([ws("mobile_hub")]);
    panel.setApiAvailable(true);
    panel.setProjectOpen(true);
    document.querySelector<HTMLSelectElement>("#wsc-select")!.value = "mobile_hub";

    document.querySelector<HTMLButtonElement>("#wsc-save-btn")!.click();
    await vi.waitFor(() => expect(onSaveWorkstation).toHaveBeenCalledWith("mobile_hub"));

    const savedFor = document.querySelector<HTMLElement>("#wsc-saved-for")!;
    expect(savedFor.textContent).toContain("mobile_hub");
  });
});

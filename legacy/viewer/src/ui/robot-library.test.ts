// @vitest-environment jsdom
/**
 * DOM-Struktur-Smoke der schreibgeschützten Roboter-Galerie (Issue #76).
 * Prüft: je Roboter eine Karte mit Name/Reichweite/Traglast + PNG-Thumbnail,
 * KEINE Anlegen/Bearbeiten/Löschen-Aktionen (read-only), den PNG-Pfad je
 * Roboter, den Platzhalter bei fehlendem Bild (img-error) und den Leerzustand.
 * Kein three.js, kein Netzwerk.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RobotDef } from "../api/projects";
import { RobotLibrary, type RobotLibraryCallbacks } from "./robot-library";
import { robotSlug, robotThumbnailPath, summarizeRobot } from "./robot-library-payload";

function robot(name: string, overrides: Partial<RobotDef> = {}): RobotDef {
  return {
    name,
    reach_mm: 1300,
    max_print_height_mm: 1000,
    max_print_length_mm: 2000,
    workspace_provisional: true,
    payload_kg: 10,
    ...overrides,
  };
}

/** Baut das Roboter-Galerie-DOM (die relevanten ids aus index.html). */
function setupDom(): void {
  document.body.innerHTML = `
    <div id="lib-rubric-roboter">
      <p id="rob-api-warning" hidden></p>
      <p id="rob-status"></p>
      <div id="rob-cards"></div>
      <p id="rob-empty" hidden></p>
    </div>
  `;
}

function makeLibrary(
  list: RobotDef[],
  overrides: Partial<RobotLibraryCallbacks> = {},
): RobotLibrary {
  const callbacks: RobotLibraryCallbacks = {
    loadRobots: vi.fn(async () => list),
    ...overrides,
  };
  return new RobotLibrary(callbacks);
}

describe("robot-library-payload (Issue #76, rein)", () => {
  it("formatiert Reichweite, Traglast und Druckraum", () => {
    const s = summarizeRobot(robot("doosan_m1013"));
    expect(s.reachText).toBe("Reichweite 1300 mm");
    expect(s.payloadText).toBe("Traglast 10 kg");
    expect(s.workspaceText).toBe("Druckraum 1000 × 2000 mm");
    expect(s.provisional).toBe(true);
  });

  it("zeigt unbekannte Traglast, wenn payload_kg null ist", () => {
    expect(summarizeRobot(robot("x", { payload_kg: null })).payloadText).toBe(
      "Traglast unbekannt",
    );
  });

  it("bildet den Roboter-Namen auf den Asset-Ordner-Slug + PNG-Pfad ab", () => {
    expect(robotSlug("doosan_m1013")).toBe("m1013");
    expect(robotSlug("kuka_kr16")).toBe("kr16"); // Präfix mit _-Trenner gestrichen
    expect(robotThumbnailPath("doosan_m1013")).toBe("./robots/m1013/thumbnail.png");
    // Unbekannter Roboter: best-effort-Slug (PNG darf fehlen → Platzhalter).
    expect(robotThumbnailPath("ACME R 5")).toBe("./robots/acme_r_5/thumbnail.png");
  });
});

describe("RobotLibrary — schreibgeschützte Galerie (Issue #76)", () => {
  beforeEach(setupDom);

  it("rendert je Roboter eine Karte mit Name, Reichweite, Traglast und Thumbnail", () => {
    const lib = makeLibrary([]);
    lib.render([
      robot("doosan_m1013"),
      robot("acme_r5", { reach_mm: 900, payload_kg: null, workspace_provisional: false }),
    ]);

    const cards = document.querySelectorAll("#rob-cards .rob-card");
    expect(cards).toHaveLength(2);

    const first = cards[0] as HTMLElement;
    expect(first.dataset.robot).toBe("doosan_m1013");
    expect(first.querySelector(".lib-card-name")?.textContent).toBe("doosan_m1013");
    expect(first.querySelector(".rob-card-reach")?.textContent).toBe("Reichweite 1300 mm");
    expect(first.querySelector(".rob-card-payload")?.textContent).toBe("Traglast 10 kg");
    expect(first.querySelector(".rob-card-workspace")?.textContent).toContain("(vorläufig)");
    const img = first.querySelector("img.lib-card-thumb") as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe("./robots/m1013/thumbnail.png");

    const second = cards[1] as HTMLElement;
    expect(second.querySelector(".rob-card-payload")?.textContent).toBe("Traglast unbekannt");
    expect(second.querySelector(".rob-card-workspace")?.textContent).not.toContain("vorläufig");
  });

  it("bietet KEINE Anlegen/Bearbeiten/Löschen-Aktionen (read-only)", () => {
    const lib = makeLibrary([]);
    lib.render([robot("doosan_m1013")]);
    const card = document.querySelector("#rob-cards .rob-card") as HTMLElement;
    expect(card.querySelector("button")).toBeNull();
    expect(card.querySelector(".lib-card-actions")).toBeNull();
    expect(card.querySelector(".rob-card-readonly")?.textContent).toBe("read-only");
    // Keine „+ Neuer Roboter"-Schaltfläche im Rubrik-Container.
    expect(document.querySelector("#lib-rubric-roboter button")).toBeNull();
  });

  it("ersetzt ein fehlendes Thumbnail durch einen Platzhalter (kein Absturz)", () => {
    const lib = makeLibrary([]);
    lib.render([robot("doosan_m1013")]);
    const img = document.querySelector("#rob-cards img.lib-card-thumb") as HTMLImageElement;
    img.dispatchEvent(new Event("error"));
    expect(document.querySelector("#rob-cards img.lib-card-thumb")).toBeNull();
    const ph = document.querySelector("#rob-cards .lib-card-thumb-placeholder");
    expect(ph?.textContent).toBe("Kein Vorschaubild");
  });

  it("zeigt den Leerzustand bei leerem Bestand", () => {
    const lib = makeLibrary([]);
    lib.render([]);
    expect(document.querySelectorAll("#rob-cards .rob-card")).toHaveLength(0);
    expect((document.getElementById("rob-empty") as HTMLElement).hidden).toBe(false);
  });

  it("blendet den Leerzustand aus, sobald Roboter vorhanden sind", () => {
    const lib = makeLibrary([]);
    lib.render([robot("doosan_m1013")]);
    expect((document.getElementById("rob-empty") as HTMLElement).hidden).toBe(true);
  });

  it("openGallery lädt den Bestand nur bei verfügbarer API", async () => {
    const loadRobots = vi.fn(async () => [robot("doosan_m1013")]);
    const lib = makeLibrary([], { loadRobots });
    await lib.openGallery(); // API nicht verfügbar → kein Laden
    expect(loadRobots).not.toHaveBeenCalled();

    lib.setApiAvailable(true);
    await lib.openGallery();
    expect(loadRobots).toHaveBeenCalledOnce();
    expect(document.querySelectorAll("#rob-cards .rob-card")).toHaveLength(1);
  });
});

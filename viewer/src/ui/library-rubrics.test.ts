// @vitest-environment jsdom
/**
 * Rubriken-Umschaltung der Bibliothek (Issue #75): genau eine Sicht sichtbar,
 * umgeschaltet ausschließlich über `.hidden` (nie `style.display`). Der aktive
 * Button trägt `.active`, und jeder Wechsel meldet die Rubrik.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryRubrics, RUBRIC_IDS } from "./library-rubrics";

function setupDom(): void {
  document.body.innerHTML = `
    <nav>
      <button id="lib-rubric-btn-roboter"></button>
      <button id="lib-rubric-btn-endeffektor" class="active"></button>
      <button id="lib-rubric-btn-workstation"></button>
    </nav>
    <div id="lib-rubric-roboter" hidden></div>
    <div id="lib-rubric-endeffektor"></div>
    <div id="lib-rubric-workstation" hidden></div>
  `;
}

describe("LibraryRubrics (Issue #75)", () => {
  beforeEach(setupDom);

  it("zeigt genau die aktive Sicht (nur .hidden) und markiert ihren Button", () => {
    const rubrics = new LibraryRubrics();
    rubrics.setActive("workstation");

    expect((document.getElementById("lib-rubric-workstation") as HTMLElement).hidden).toBe(false);
    expect((document.getElementById("lib-rubric-endeffektor") as HTMLElement).hidden).toBe(true);
    expect((document.getElementById("lib-rubric-roboter") as HTMLElement).hidden).toBe(true);
    expect(document.getElementById("lib-rubric-btn-workstation")?.classList.contains("active")).toBe(
      true,
    );
    expect(document.getElementById("lib-rubric-btn-endeffektor")?.classList.contains("active")).toBe(
      false,
    );
  });

  it("nutzt kein style.display zum Umschalten (nur das hidden-Attribut)", () => {
    const rubrics = new LibraryRubrics();
    rubrics.setActive("roboter");
    for (const id of RUBRIC_IDS) {
      const view = document.getElementById(`lib-rubric-${id}`) as HTMLElement;
      expect(view.style.display).toBe("");
    }
  });

  it("ein Klick auf einen Rubrik-Button schaltet um und meldet die Rubrik", () => {
    const onRubricChanged = vi.fn();
    const rubrics = new LibraryRubrics({ onRubricChanged });
    (document.getElementById("lib-rubric-btn-workstation") as HTMLButtonElement).click();
    expect(rubrics.active).toBe("workstation");
    expect(onRubricChanged).toHaveBeenCalledWith("workstation");
  });
});

/**
 * DOM-Struktur-Vertrag des geteilten Hauptsichtfelds (Issue #30): `#viewport`
 * liegt NICHT in einem Reiter-Panel, sondern als Geschwister daneben in
 * `#tab-body` — nur so bleibt die 3D-Ansicht über die Prozess-Reiter sichtbar.
 * (Lehre aus dem GUI-Smoke 2026-07-05: grüne Checks trotz leerem Hauptsichtfeld,
 * weil die Panels schlicht kein <main> enthielten.)
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const html = readFileSync(fileURLToPath(new URL("../../index.html", import.meta.url)), "utf-8");

/** Inhalt eines Tab-Panels: vom data-panel-Marker bis zum nächsten schließenden </section>. */
function panelBody(panel: string): string {
  const start = html.indexOf(`data-panel="${panel}"`);
  expect(start, `Panel ${panel} fehlt in index.html`).toBeGreaterThan(-1);
  const end = html.indexOf("</section>", start);
  return html.slice(start, end);
}

describe("index.html: geteiltes Hauptsichtfeld (Issue #30)", () => {
  it("#viewport existiert genau einmal", () => {
    expect(html.match(/id="viewport"/g)).toHaveLength(1);
  });

  it("#viewport liegt nicht im Projekt-Panel (sondern daneben in #tab-body)", () => {
    expect(panelBody("projekt")).not.toContain('id="viewport"');
  });

  it.each(["projekt", "roboter", "zerlegung", "druckplan", "export"])(
    "Prozess-Panel %s enthält kein eigenes <main> (Viewport wird geteilt)",
    (panel) => {
      expect(panelBody(panel)).not.toContain("<main");
    },
  );

  it("der Reiter Simulation ist entfernt (Fusion in Druckplan, #86)", () => {
    expect(html).not.toContain('data-panel="simulation"');
    expect(html).not.toContain('data-tab="simulation"');
  });

  it("das Simulations-Dock liegt NEBEN dem Viewport in #tab-body, nicht im Panel (#108)", () => {
    // Wie #viewport ist das Dock ein Geschwister in #tab-body (kein Tab-Panel) —
    // nur so kann es an den Fuß des geteilten 3D-Felds ankern.
    expect(html.match(/id="sim-dock"/g)).toHaveLength(1);
    expect(panelBody("druckplan")).not.toContain('id="sim-dock"');
  });

  it("die Bibliothek behält ihre eigene Szene (#cfg-viewport)", () => {
    expect(panelBody("bibliothek")).toContain('id="cfg-viewport"');
  });
});

describe("index.html: Bibliothek-Rubriken (Issue #75)", () => {
  const body = panelBody("bibliothek");

  it.each(["roboter", "endeffektor", "workstation"])(
    "die Rubrik-Sicht %s existiert im Bibliothek-Panel",
    (rubric) => {
      expect(body).toContain(`id="lib-rubric-${rubric}"`);
      expect(body).toContain(`id="lib-rubric-btn-${rubric}"`);
    },
  );

  it("die Endeffektor-Galerie liegt unter der Endeffektor-Rubrik (#lib-gallery)", () => {
    expect(body).toContain('id="lib-gallery"');
  });

  it("die Workstation-Rubrik bringt Galerie + Formular-Editor mit", () => {
    expect(body).toContain('id="ws-gallery"');
    expect(body).toContain('id="ws-cards"');
    expect(body).toContain('id="ws-empty"');
    expect(body).toContain('id="ws-editor"');
    expect(body).toContain('id="ws-height-adjustable"');
    expect(body).toContain('id="ws-heights-discrete"');
    expect(body).toContain('id="ws-heights-range"');
    expect(body).toContain('id="ws-compatible-robots"');
  });
});

describe("index.html: Reiter Zerlegung (UI-Redesign Scheibe 4, Issue #106)", () => {
  const body = panelBody("zerlegung");

  it("hat ein eigenes Prozess-Panel mit Inspector-Aside", () => {
    expect(html).toContain('data-panel="zerlegung"');
    expect(body).toContain('id="zerlegung-aside"');
  });

  it("Kopf: Primärbutton + Kopf-Status; die getrennten Buttons sind verschmolzen", () => {
    expect(body).toContain('id="zerlegung-auto-btn"');
    expect(body).toContain('id="zerlegung-head-status"');
    // Optimalvorschlag (#23/#80) + Zerlegungsvorschlag (#24) → EINE Aktion.
    expect(html).not.toContain('id="placement-suggest-btn"');
    expect(html).not.toContain('id="decompose-btn"');
  });

  it("das Gesamtwand-Vorschlags-Panel (#22/#80) ist entfernt (Issue #134)", () => {
    // Die vorschlag-1/2/3-Liste samt „Wählen"-Mechanik hat nach der Zerlegung
    // keinen Konsumenten mehr — Slicing/Sim/Export laufen über die
    // Abschnitts-Platzierungen.
    expect(html).not.toContain('id="placement-scores"');
    expect(html).not.toContain('id="placement-status"');
  });

  it("Accordion Art & Aufstellung: Zerlegungsart, Aufstellung, Modulgrenzen, Workstation-Zeile", () => {
    expect(body).toContain('id="zerlegung-acc-art-body"');
    expect(body).toContain('id="zerlegungsart-abschnitt"');
    expect(body).toContain('id="aufstell-toggle"');
    expect(body).toContain('id="module-limits-group"');
    expect(body).toContain('id="zerlegungsart-hint"');
  });

  it("Accordion Schnittplan: Schnittliste, Add-Buttons, Fugen-Versatz", () => {
    expect(body).toContain('id="zerlegung-acc-cuts-body"');
    expect(body).toContain('id="decompose-cuts"');
    expect(body).toContain('id="decompose-add-horizontal-btn"');
    expect(body).toContain('id="decompose-add-vertical-btn"');
    expect(body).toContain('id="decompose-joint-offset"');
  });

  it("Accordion Platzierung — <Teil>: Titel + 3 Felder mit ↺ je Feld (#94, fokus-getrieben)", () => {
    expect(body).toContain('id="zerlegung-placement-title"');
    for (const f of [
      "placement-override-lateral",
      "placement-override-standoff",
      "placement-override-standheight",
    ]) {
      expect(body).toContain(`id="${f}"`);
      expect(body).toContain(`id="${f}-reset"`);
    }
  });

  it("Sticky-Footer: Pruefen-lassen-Primaerbutton + Status", () => {
    expect(body).toContain('id="decompose-check-btn"');
    expect(body).toContain('id="decompose-status"');
  });

  it("die drei Accordions nutzen das collapsible-Muster (▸/▾, aria-expanded)", () => {
    const toggles = body.match(/class="accordion-toggle"/g) ?? [];
    expect(toggles).toHaveLength(3);
    expect(body).toContain('id="zerlegung-acc-art-toggle"');
    expect(body).toContain('id="zerlegung-acc-cuts-toggle"');
    expect(body).toContain('id="zerlegung-acc-placement-toggle"');
  });

  it("KEIN Gilt-für-Scope im Zerlegungs-Reiter (der lebt im Slicing/Druckplan-Reiter, #107)", () => {
    expect(body).not.toContain('id="scope-switch"');
  });

  it("die frühere Druckplan-Rubriken-Umschaltung (#89) ist vollständig entfernt", () => {
    expect(html).not.toContain('id="druckplan-rubrics"');
    expect(html).not.toContain('id="druckplan-rubric-btn-zerlegung"');
    expect(html).not.toContain('id="druckplan-rubric-zerlegung"');
  });
});

describe("index.html: Reiter Slicing — eigener Prozess-Schritt (UI-Redesign Scheibe 5, #107)", () => {
  const body = panelBody("druckplan");

  it("ist ein 352px-Inspector mit Gilt-für-Kopf, Accordions und Sticky-Footer", () => {
    expect(html).toContain('data-panel="druckplan"');
    expect(body).toContain('id="druckplan-aside"');
    expect(body).toContain('class="inspector"');
    expect(body).toContain('class="inspector-head"');
    expect(body).toContain('class="inspector-footer"');
  });

  it("die frühere Slicing-Rubrik-Hülle (#89/#106) ist vollständig entfernt", () => {
    expect(html).not.toContain('id="druckplan-rubric-slicing"');
    expect(html).not.toContain('class="druckplan-rubric-view"');
    expect(html).not.toContain('id="druckplan-rubrics"');
  });

  it("Accordion Prozessparameter: Schichthöhe/Strangbreite/Schalen/Lead/Kipp als .field-box + je ↺ + Kopf-Notiz", () => {
    expect(body).toContain('id="slicing-acc-prozess-toggle"');
    expect(body).toContain('id="slicing-acc-prozess-body"');
    expect(body).toContain('id="slicing-prozess-scope"');
    expect(body).toContain('class="field-box"');
    for (const f of [
      "process-params-layer-height",
      "process-params-strand-width",
      "process-params-shells",
      "process-params-lead-deg",
      "process-params-kipp-deg",
    ]) {
      expect(body).toContain(`id="${f}"`);
      expect(body).toContain(`id="${f}-reset"`);
    }
  });

  it("Accordion Fortgeschritten (default zu): das einzige collapsible, mit v_print/v_travel/io", () => {
    const toggles = body.match(/class="collapsible-toggle"/g) ?? [];
    expect(toggles).toHaveLength(1);
    expect(body).toContain('id="process-params-advanced-toggle"');
    expect(body).toContain('id="process-params-advanced-body"');
    for (const f of [
      "process-params-v-print",
      "process-params-v-travel",
      "process-params-io-print",
      "process-params-io-travel",
    ]) {
      expect(body).toContain(`id="${f}"`);
    }
  });

  it("Accordion Singularitäts-Advisor: Prüfen/Anwenden im eigenen Accordion (#65)", () => {
    expect(body).toContain('id="slicing-acc-advisor-toggle"');
    expect(body).toContain('id="slicing-acc-advisor-body"');
    expect(body).toContain('id="singularity-advisor-check-btn"');
    expect(body).toContain('id="singularity-advisor-apply-btn"');
  });

  it("Accordion Kollisions-Advisor: Prüfen + gerankte Optionsliste im eigenen Accordion (#130)", () => {
    expect(body).toContain('id="slicing-acc-collision-advisor-toggle"');
    expect(body).toContain('id="slicing-acc-collision-advisor-body"');
    expect(body).toContain('id="collision-advisor-check-btn"');
    expect(body).toContain('id="collision-advisor-list"');
    expect(body).toContain('id="collision-advisor-baseline"');
  });

  it("Kollisions-Advisor: zweigeteilte Prüfung + ehrlicher Scope-Chip (Prüf-UX #139/#145)", () => {
    // Schneller Befund und teure Optionssuche sind ZWEI Knöpfe — der frühere
    // eine Knopf startete unangekündigt ~18 Neu-Simulationen (Minuten).
    expect(body).toContain('id="collision-advisor-options-btn"');
    // Der Scope-Chip ist dynamisch (Fokus-Teil), nicht mehr der falsche
    // Festtext „global".
    expect(body).toContain('id="collision-advisor-scope"');
    expect(body).not.toMatch(/acc-scope-note">global</);
  });

  it("genau drei Inspector-Accordions mit Kopf-Notiz (Prozessparameter, Sing.-Advisor, Koll.-Advisor)", () => {
    const toggles = body.match(/class="accordion-toggle has-scope"/g) ?? [];
    expect(toggles).toHaveLength(3);
  });

  it("Sticky-Footer trägt Status + Speichern (je Scope, #82-Mechanik)", () => {
    const footerIdx = body.indexOf('class="inspector-footer"');
    expect(footerIdx).toBeGreaterThan(-1);
    const footer = body.slice(footerIdx);
    expect(footer).toContain('id="process-params-status"');
    expect(footer).toContain('id="process-params-save-btn"');
  });

  it("der Modus-Umschalter „Vorbereiten/Simulieren\" ist restlos entfernt (#108 kehrt #86 um)", () => {
    expect(html).not.toContain('id="druckplan-mode"');
    expect(html).not.toContain('id="mode-vorbereiten"');
    expect(html).not.toContain('id="mode-simulieren"');
    expect(html).not.toContain('id="druckplan-simulieren"');
    // Der Simulieren-Bereich liegt nicht mehr im Slicing-Aside.
    expect(body).not.toContain('id="sim-focus-btn"');
    expect(body).not.toContain('id="sim-player"');
  });
});

describe("index.html: Simulations-Dock statt Modus-Umschalter (UI-Redesign Scheibe 6, Issue #108)", () => {
  // Das Dock lebt außerhalb der Tab-Panels (Geschwister von #viewport) — deshalb
  // gegen das ganze Dokument geprüft.
  const dockIdx = html.indexOf('id="sim-dock"');
  const dock = html.slice(dockIdx, html.indexOf("</div>", html.indexOf('id="sim-status"')) + 6);

  it("das Dock ist anfangs versteckt (nur `.hidden`) und trägt beide Simulier-Knöpfe", () => {
    const tag = html.slice(dockIdx, html.indexOf(">", dockIdx) + 1);
    expect(tag).toContain("hidden");
    expect(dock).toContain('id="sim-focus-btn"');
    expect(dock).toContain('id="sim-sequence-btn"');
  });

  it("der Fokus-Knopf ist primär (Prototyp: Akzent-Button)", () => {
    const focusTag = dock.slice(dock.indexOf('id="sim-focus-btn"'));
    expect(focusTag.slice(0, focusTag.indexOf(">"))).toContain("btn-primary");
  });

  it("der Player im Dock bringt Timeline, Zeit und Phasen-Pill mit (Player-Zustand, #48)", () => {
    expect(dock).toContain('id="sim-player"');
    expect(dock).toContain('id="sim-play-btn"');
    expect(dock).toContain('id="sim-slider"');
    expect(dock).toContain('id="sim-time"');
    expect(dock).toContain('id="sim-phase"');
    expect(dock).toContain('id="sim-back-btn"');
  });

  it("Start-Modus als DOM-Vertrag (#154): Startknöpfe anfangs sichtbar, Player versteckt", () => {
    // Zwei Modi statt Überlagerung (#148/#154): im Ausgangszustand (kein Replay)
    // stehen die Startknöpfe, der Player ist `hidden`. Die reine Modus-Wahl
    // (sim-dock-state.ts) schaltet zur Laufzeit ausschließlich über `.hidden` um —
    // im Replay verschwinden die Startknöpfe, `← Übersicht` bringt sie zurück.
    for (const id of ["sim-focus-btn", "sim-sequence-btn"]) {
      const start = dock.indexOf(`id="${id}"`);
      const tag = dock.slice(dock.lastIndexOf("<", start), dock.indexOf(">", start) + 1);
      expect(tag, `${id} sollte im Start-Modus sichtbar (nicht hidden) sein`).not.toContain(
        "hidden",
      );
    }
    const playerStart = dock.indexOf('id="sim-player"');
    const playerTag = dock.slice(
      dock.lastIndexOf("<", playerStart),
      dock.indexOf(">", playerStart) + 1,
    );
    expect(playerTag, "der Player sollte anfangs (Start-Modus) hidden sein").toContain("hidden");
  });

  it("das Geschwindigkeits-Bedienelement (#155) liegt im Dock und ist anfangs versteckt", () => {
    // Vielfaches-der-Echtzeit-Faktor im Replay-Modus (#155): ein schmales <select>,
    // das mit dem Player ein-/ausgeblendet wird (nur `.hidden`, Start-Modus = weg).
    expect(dock.match(/id="sim-speed"/g)).toHaveLength(1);
    const start = dock.indexOf('id="sim-speed"');
    const tag = dock.slice(dock.lastIndexOf("<", start), dock.indexOf(">", start) + 1);
    expect(tag, "#sim-speed sollte im Start-Modus hidden sein").toContain("hidden");
  });
});

describe("index.html: Kollisionskontrolle S3 im Player (Issue #128, ADR-024)", () => {
  const dockIdx = html.indexOf('id="sim-dock"');
  const dock = html.slice(dockIdx, html.indexOf("</div>", html.indexOf('id="sim-status"')) + 6);

  it("der Player trägt die Marker-Leiste, die Abstandszahl und das Befund-Badge", () => {
    // Anklickbare Kollisions-/Warn-Marker (US 9) — Mount-Punkt in der Timeline.
    expect(dock).toContain('id="sim-collision-markers"');
    // Live-Abstandszahl (US 11) + Kollisions-Befund-Badge (US 12/25).
    expect(dock).toContain('id="sim-collision-dist"');
    expect(dock).toContain('id="sim-collision-badge"');
  });

  it("die Marker-Leiste liegt in der Timeline (positioniert über dem Track)", () => {
    const timelineIdx = dock.indexOf("sim-timeline");
    const markersIdx = dock.indexOf('id="sim-collision-markers"');
    const sliderIdx = dock.indexOf('id="sim-slider"');
    expect(markersIdx).toBeGreaterThan(sliderIdx);
    expect(sliderIdx).toBeGreaterThan(timelineIdx);
  });

  it("Abstandszahl + Badge sind anfangs versteckt (nur bei Befund/Schalter sichtbar)", () => {
    for (const id of ["sim-collision-dist", "sim-collision-badge"]) {
      const start = dock.indexOf(`id="${id}"`);
      const tag = dock.slice(dock.lastIndexOf("<", start), dock.indexOf(">", start) + 1);
      expect(tag, `${id} sollte anfangs hidden sein`).toContain("hidden");
    }
  });
});

describe("index.html: Kollisionsbefund wird Lauf-Eigenschaft (Issue #156)", () => {
  const dockIdx = html.indexOf('id="sim-dock"');
  const dock = html.slice(dockIdx, html.indexOf("</div>", html.indexOf('id="sim-status"')) + 6);

  it("die Leiste trägt einen eigenen aufklappbaren Befundblock mit <dl> + <ul>", () => {
    expect(dock).toContain('id="sim-collision-panel"');
    expect(dock).toContain('id="sim-collision-panel-meta"');
    expect(dock).toContain('id="sim-collision-panel-warnings"');
  });

  it("der Befundblock ist anfangs zugeklappt (nur `.hidden`)", () => {
    const start = dock.indexOf('id="sim-collision-panel"');
    const tag = dock.slice(dock.lastIndexOf("<", start), dock.indexOf(">", start) + 1);
    expect(tag, "der Befundblock sollte anfangs hidden sein").toContain("hidden");
  });

  it("der Badge ist der Anker des Blocks (role=button + aria-controls), OHNE Reiterwechsel", () => {
    const start = dock.indexOf('id="sim-collision-badge"');
    const tag = dock.slice(dock.lastIndexOf("<", start), dock.indexOf(">", start) + 1);
    expect(tag).toContain('role="button"');
    expect(tag).toContain('aria-controls="sim-collision-panel"');
  });

  it("der Befundblock steht NACH dem Player (Overlay über der Leiste, #154)", () => {
    expect(dock.indexOf('id="sim-collision-panel"')).toBeGreaterThan(
      dock.indexOf('id="sim-player"'),
    );
  });
});

describe("index.html: Gilt-für-Umschalter Global↔Teil im Slicing-Kopf (Issue #92 → #107)", () => {
  const body = panelBody("druckplan");

  it("der Umschalter liegt im Inspector-Kopf VOR den Accordions, anfangs versteckt, segmented", () => {
    const scopeIdx = body.indexOf('id="scope-switch"');
    const accIdx = body.indexOf('id="slicing-acc-prozess-toggle"');
    const headIdx = body.indexOf('class="inspector-head"');
    expect(scopeIdx).toBeGreaterThan(headIdx);
    expect(scopeIdx).toBeLessThan(accIdx);
    // Anfangs versteckt (nur `.hidden`): erscheint erst bei gewähltem Teil.
    const tag = body.slice(scopeIdx, body.indexOf(">", scopeIdx) + 1);
    expect(tag).toContain("hidden");
    expect(tag).toContain("segmented");
  });

  it("bringt Global-/Teil-Option, Teil-Beschriftung und Teil-Hinweis mit", () => {
    expect(body).toContain('id="scope-global"');
    expect(body).toContain('id="scope-teil"');
    expect(body).toContain('id="scope-teil-name"');
    expect(body).toContain('id="scope-hint"');
  });

  it.each([
    "process-params-layer-height",
    "process-params-strand-width",
    "process-params-shells",
    "process-params-lead-deg",
    "process-params-kipp-deg",
    "process-params-v-print",
    "process-params-v-travel",
    "process-params-io-print",
    "process-params-io-travel",
  ])("jedes Slicing-Feld trägt sein ↺ auf-global-zurück (%s-reset)", (inputId) => {
    expect(body).toContain(`id="${inputId}-reset"`);
  });

  it("die separate Pro-Abschnitts-Overrides-Sektion (#82) ist entfernt (kein toter DOM-Rest)", () => {
    expect(html).not.toContain('id="section-params-sections"');
    expect(html).not.toContain('id="section-params-save-btn"');
    expect(html).not.toContain('id="section-params-empty"');
    expect(html).not.toContain('id="section-params-status"');
  });
});

describe("index.html: Teile-Palette am 3D-Feld (Issue #91, PRD #88)", () => {
  it("die frühere Abschnittsliste im Aside ist entfernt (kein toter DOM-Rest)", () => {
    expect(html).not.toContain('id="decompose-sections"');
    expect(html).not.toContain('class="decompose-section"');
  });

  it("die Palette lebt am geteilten 3D-Feld, nicht im Druckplan-Panel", () => {
    // Kein Palette-DOM im Panel-Körper — sie liegt neben #viewport in #tab-body.
    expect(panelBody("druckplan")).not.toContain('id="parts-palette"');
    // Palette steht NACH dem geteilten #viewport (Geschwister, Issue #30).
    const viewportIdx = html.indexOf('id="viewport"');
    const paletteIdx = html.indexOf('id="parts-palette"');
    expect(paletteIdx).toBeGreaterThan(viewportIdx);
  });

  it("bringt Kopf-Umschalter, Liste und Leerhinweis mit (Ampel/Marker/Override je Teil im JS)", () => {
    expect(html).toContain('id="parts-palette"');
    expect(html).toContain('id="parts-palette-toggle"');
    expect(html).toContain('id="parts-palette-body"');
    expect(html).toContain('id="parts-palette-list"');
    expect(html).toContain('id="parts-palette-empty"');
  });

  it("ist anfangs ausgeblendet (nur `.hidden`, sichtbar erst im Reiter Druckplan)", () => {
    const start = html.indexOf('id="parts-palette"');
    const tag = html.slice(html.lastIndexOf("<aside", start), html.indexOf(">", start) + 1);
    expect(tag).toContain("hidden");
  });
});

describe("index.html: Viewer-Einstellungen am 3D-Feld (Wand-Fokus ab Zerlegung)", () => {
  it("das ⚙-Menü lebt als Geschwister neben #viewport, nicht in einem Panel-Körper", () => {
    expect(panelBody("zerlegung")).not.toContain('id="viewer-settings"');
    const viewportIdx = html.indexOf('id="viewport"');
    const settingsIdx = html.indexOf('id="viewer-settings"');
    expect(settingsIdx).toBeGreaterThan(viewportIdx);
  });

  it("bringt Kopf-Umschalter, Schalter-Mount-Punkt und Einpassen-Button mit", () => {
    expect(html).toContain('id="viewer-settings"');
    expect(html).toContain('id="viewer-settings-toggle"');
    expect(html).toContain('id="viewer-settings-body"');
    // Die Sicht-Schalter werden aus der ToggleSpec-Liste (main.ts) in diesen
    // Mount-Punkt gebaut (ui/viewer-settings.ts) — keine hartcodierten Checkboxen.
    expect(html).toContain('id="viewer-settings-toggles"');
    expect(html).toContain('id="vs-fit-wall"');
  });

  it("ist anfangs ausgeblendet (nur `.hidden`, sichtbar erst in den Fokus-Reitern)", () => {
    const start = html.indexOf('id="viewer-settings"');
    const tag = html.slice(html.lastIndexOf("<aside", start), html.indexOf(">", start) + 1);
    expect(tag).toContain("hidden");
  });

  it("die Replay-Schalter show-arm/grow-strand sind aus dem Projekt-Panel gewandert (Issue #159)", () => {
    // Sie wohnen jetzt als JS-gebaute ⚙-Sektion „Replay-Bühne" (viewer-settings.ts),
    // erreichbar überall, wo eine Bühne läuft — im Projekt-Panel fallen sie ersatzlos.
    const projekt = panelBody("projekt");
    expect(projekt).not.toContain('id="show-arm"');
    expect(projekt).not.toContain('id="grow-strand"');
    expect(projekt).not.toContain('id="grow-strand-label"');
    // Auch nirgends sonst im statischen HTML — die Schalter werden aus ToggleSpecs
    // (main.ts) in den ⚙-Mount-Punkt gebaut, nicht als hartcodierte Checkbox.
    expect(html).not.toContain('id="show-arm"');
    expect(html).not.toContain('id="grow-strand"');
  });
});

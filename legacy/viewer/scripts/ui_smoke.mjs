/**
 * Headless-UI-Smoke-Test des fgc-viewers (Issue #30/#31, Lehre aus dem
 * GUI-Smoke 2026-07-05: tsc/vitest können grün sein, während der Reiter leer
 * bleibt). Bedient den echten Viewer über das Chrome-DevTools-Protokoll in
 * headless Edge und prüft je Reiter, dass das Hauptsichtfeld wirklich
 * sichtbar ist (Canvas mit realer Ausdehnung), plus Deeplink-Regressionen
 * (Warnungs-Deckelung #32, Stunden-Format #33).
 *
 * Voraussetzungen: Core-API (Port 8765) + Vite-Dev-Server (Port 5173) laufen,
 * mindestens ein Projekt existiert. Headless Edge selbst starten, z. B.:
 *   & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
 *     --headless=new --remote-debugging-port=9333 --user-data-dir=%TEMP%\edge-smoke about:blank
 * Aufruf:  node viewer/scripts/ui_smoke.mjs [cdp-port] [screenshot-dir]
 * Ausserdem noetig: FGC_SMOKE_RUN = absoluter Pfad eines Laufordners mit
 * trajectory.json (fuer die Deeplink-Pruefung in Schritt 5).
 * Exit-Code 0 = alle Prüfungen bestanden.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const CDP_PORT = process.argv[2] ?? "9333";
const SHOT_DIR = process.argv[3] ?? null;
if (SHOT_DIR) mkdirSync(SHOT_DIR, { recursive: true });

const failures = [];
function check(name, ok, detail = "") {
  const state = ok ? "ok " : "FAIL";
  console.log(`  [${state}] ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures.push(`${name}${detail ? ` (${detail})` : ""}`);
}

async function getPageTarget() {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
      const page = (await res.json()).find((t) => t.type === "page");
      if (page) return page;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Kein CDP-Target auf Port ${CDP_PORT} — headless Edge gestartet?`);
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const p = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(msg.error.message));
        else p.resolve(msg.result);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP-Timeout: ${method}`));
        }
      }, 20000);
    });
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function evalJs(cdp, expression) {
  const res = await cdp.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (res.exceptionDetails) throw new Error(res.exceptionDetails.text);
  return res.result.value;
}

async function shot(cdp, name) {
  if (!SHOT_DIR) return;
  const res = await cdp.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(SHOT_DIR, name), Buffer.from(res.data, "base64"));
}

// Sichtbarkeits-/Größen-Snapshot des geteilten Viewports + Panels.
const SNAP = `(() => {
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height),
      display: getComputedStyle(el).display, hidden: el.hidden };
  };
  const activePanel = [...document.querySelectorAll('.tab-panel')]
    .find((p) => !p.hidden)?.dataset.panel ?? null;
  return {
    activePanel,
    viewport: rect(document.getElementById('viewport')),
    canvas: rect(document.querySelector('#viewport canvas')),
    cfgCanvas: rect(document.querySelector('#cfg-viewport canvas')),
    aside: rect(document.querySelector('.tab-panel:not([hidden]) aside')),
  };
})()`;

async function main() {
  const target = await getPageTarget();
  const ws = await new Promise((resolve, reject) => {
    const s = new WebSocket(target.webSocketDebuggerUrl);
    s.addEventListener("open", () => resolve(s));
    s.addEventListener("error", () => reject(new Error("WebSocket-Fehler")));
  });
  const cdp = new Cdp(ws);
  await cdp.send("Runtime.enable");
  await cdp.send("Page.enable");

  console.log("1) Projektliste laden + Projekt öffnen");
  await cdp.send("Page.navigate", { url: "http://localhost:5173/" });
  await sleep(2500);
  const slug = await evalJs(cdp, `(() => {
    const li = document.querySelector('#pl-projects li');
    if (!li) return null; li.click(); return li.dataset.slug;
  })()`);
  check("Projekt in der Liste vorhanden und geöffnet", slug !== null, String(slug));
  await sleep(6000);

  console.log("1b) Header ersetzt Tabbar + Active-Job-Bar: Logo, Job-Chip, Stepper, ◐, ▤ (Issue #102)");
  const header = await evalJs(cdp, `(() => {
    const steps = [...document.querySelectorAll('#stepper [data-tab]')].map((el) => el.dataset.tab);
    const jobChip = document.getElementById('header-job-chip');
    return {
      headerPresent: !!document.getElementById('app-header'),
      tabbarGone: document.getElementById('tabbar') === null,
      jobBarGone: document.getElementById('active-job-bar') === null,
      steps,
      dots: document.querySelectorAll('#stepper .step .dot').length,
      projectName: document.getElementById('header-project-name')?.textContent ?? '',
      jobChipVisible: !!jobChip && jobChip.hidden === false && jobChip.textContent.length > 0,
      themeBtn: !!document.getElementById('header-theme-toggle'),
      libraryBtn: !!document.getElementById('header-library-btn'),
      search: !!document.getElementById('header-search'),
    };
  })()`);
  check(
    "Header vorhanden, Tabbar + Active-Job-Bar entfernt",
    header.headerPresent && header.tabbarGone && header.jobBarGone,
    JSON.stringify({ header: header.headerPresent, tabbar: header.tabbarGone, jobbar: header.jobBarGone }),
  );
  check(
    "Stepper bildet die fünf Prozess-Schritte ab (Druckplan-Split #106: Zerlegung eigener Schritt), je Schritt ein Status-Punkt",
    header.steps.join(",") === "projekt,roboter,zerlegung,druckplan,export" && header.dots === 5,
    JSON.stringify({ steps: header.steps, dots: header.dots }),
  );
  check(
    "Header zeigt Projektnamen, Druckjob-Chip, Suchfeld, Theme-◐ und Bibliothek-▤",
    header.projectName.length > 0 && header.jobChipVisible &&
      header.search && header.themeBtn && header.libraryBtn,
    JSON.stringify({ name: header.projectName, jobChip: header.jobChipVisible }),
  );
  // Theme-Toggle ◐ bedient das Modul aus Scheibe 1 (data-theme am <html> kippt).
  const themeFlip = await evalJs(cdp, `(() => {
    const before = document.documentElement.getAttribute('data-theme');
    document.getElementById('header-theme-toggle').click();
    const after = document.documentElement.getAttribute('data-theme');
    // Zurückkippen (Ausgangszustand nicht verfälschen).
    document.getElementById('header-theme-toggle').click();
    return { before, after, restored: document.documentElement.getAttribute('data-theme') };
  })()`);
  check(
    "Theme-◐ kippt data-theme (Scheibe-1-Modul) und stellt zurück",
    themeFlip.before !== themeFlip.after && themeFlip.before === themeFlip.restored,
    JSON.stringify(themeFlip),
  );

  console.log("1c) ⌘K-Befehlspalette: öffnen → filtern → ausführen → schließen (Issue #109)");
  // ⌘K/Ctrl-K öffnet das Overlay (Sichtbarkeit nur über `hidden`); die Header-
  // Such-Attrappe tut dasselbe. Filtern über die reine Registry, dann einen
  // Treffer ausführen: Reiter wechseln + Accordion öffnen + Feld fokussieren.
  const palOpen = await evalJs(cdp, `(() => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }));
    const root = document.getElementById('command-palette');
    return { hidden: root.hidden, focused: document.activeElement?.id ?? null };
  })()`);
  check(
    "⌘K öffnet die Palette (Overlay sichtbar, Eingabe fokussiert)",
    palOpen.hidden === false && palOpen.focused === "command-palette-input",
    JSON.stringify(palOpen),
  );
  // Filtern: „schichthöhe" → der Slicing-Prozessparameter-Eintrag steht oben.
  const palFilter = await evalJs(cdp, `(() => {
    const inp = document.getElementById('command-palette-input');
    inp.value = 'schichthöhe'; inp.dispatchEvent(new Event('input'));
    const rows = [...document.querySelectorAll('#command-palette-list li.cmd-row')];
    return {
      n: rows.length,
      firstLabel: rows[0]?.querySelector('.cmd-row-label')?.textContent ?? null,
      firstGroup: rows[0]?.querySelector('.cmd-row-group')?.textContent ?? null,
    };
  })()`);
  check(
    "Filter schichthöhe liefert den Slicing-Prozessparameter oben (Icon|Label|Gruppe)",
    palFilter.n > 0 && /Schichthöhe/.test(palFilter.firstLabel ?? "") &&
      /Prozessparameter/.test(palFilter.firstGroup ?? ""),
    JSON.stringify(palFilter),
  );
  // Ausführen (Klick auf die Trefferzeile): Reiter druckplan + Prozessparameter-
  // Accordion offen + das Schichthöhe-Feld fokussiert; Overlay schließt.
  await evalJs(cdp, `document.querySelector('#command-palette-list li.cmd-row').click()`);
  await sleep(700);
  const palExec = await evalJs(cdp, `(() => ({
    hidden: document.getElementById('command-palette').hidden,
    activePanel: [...document.querySelectorAll('.tab-panel')].find((p) => !p.hidden)?.dataset.panel ?? null,
    accOpen: document.getElementById('slicing-acc-prozess-toggle')?.getAttribute('aria-expanded'),
    focused: document.activeElement?.id ?? null,
  }))()`);
  check(
    "Ausführen navigiert: Reiter druckplan, Prozessparameter-Accordion offen, Schichthöhe fokussiert; Overlay zu",
    palExec.hidden === true && palExec.activePanel === "druckplan" &&
      palExec.accOpen === "true" && palExec.focused === "process-params-layer-height",
    JSON.stringify(palExec),
  );
  // Header-Such-Attrappe öffnet ebenfalls; ESC schließt wieder.
  const palEsc = await evalJs(cdp, `(() => {
    document.getElementById('header-search').click();
    const openHidden = document.getElementById('command-palette').hidden;
    const inp = document.getElementById('command-palette-input');
    inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    return { openHidden, closedHidden: document.getElementById('command-palette').hidden };
  })()`);
  check(
    "Header-Suchfeld öffnet die Palette, ESC schließt sie",
    palEsc.openHidden === false && palEsc.closedHidden === true,
    JSON.stringify(palEsc),
  );
  await shot(cdp, "smoke-command-palette.png");

  // IK-Konfiguration (Kollisionskontrolle S4, #129): das Accordion + die drei
  // Tri-State-Schalter (Schulter/Ellbogen/Handgelenk) sind im Slicing-Aside da.
  const ik = await evalJs(cdp, `(() => ({
    accordion: !!document.getElementById('slicing-acc-ikconfig-toggle'),
    selects: ['shoulder', 'elbow', 'wrist'].map(
      (a) => document.getElementById('process-params-ik-' + a)?.tagName ?? null,
    ),
    options: [...(document.getElementById('process-params-ik-shoulder')?.options ?? [])]
      .map((o) => o.value),
  }))()`);
  check(
    "IK-Konfiguration: Accordion + drei Selects (auto/a/b) vorhanden (#129)",
    ik.accordion &&
      ik.selects.every((t) => t === "SELECT") &&
      JSON.stringify(ik.options) === JSON.stringify(["", "a", "b"]),
    JSON.stringify(ik),
  );

  // Kollisions-Advisor (Kollisionskontrolle S5, #130; Prüf-UX #139/#145):
  // eigenes Accordion mit ZWEI Knöpfen — schneller Befund (eine Neu-Simulation)
  // und teure Optionssuche (das „Menü") — plus dynamischem Scope-Chip
  // (Fokus-Teil statt Festtext „global"). Reiner DOM-Vertrag — die eigentliche
  // Prüfung re-simuliert (teuer) und wird hier NICHT ausgelöst.
  const collAdv = await evalJs(cdp, `(() => {
    const t = document.getElementById('slicing-acc-collision-advisor-toggle');
    if (t && t.getAttribute('aria-expanded') !== 'true') t.click();
    return {
      accordion: !!t,
      scopeChip: (document.getElementById('collision-advisor-scope')?.textContent ?? ''),
      checkBtn: !!document.getElementById('collision-advisor-check-btn'),
      optionsBtn: !!document.getElementById('collision-advisor-options-btn'),
      list: !!document.getElementById('collision-advisor-list'),
      baseline: !!document.getElementById('collision-advisor-baseline'),
    };
  })()`);
  check(
    "Kollisions-Advisor: Accordion + Befund-/Options-Knopf + dynamischer Scope-Chip (#130, #145)",
    collAdv.accordion && collAdv.scopeChip.length > 0 && collAdv.checkBtn &&
      collAdv.optionsBtn && collAdv.list && collAdv.baseline,
    JSON.stringify(collAdv),
  );

  console.log("2) Hauptsichtfeld je Prozess-Reiter (Issue #30; Zerlegung eigener Reiter #106)");
  for (const tab of ["projekt", "roboter", "zerlegung", "druckplan", "export"]) {
    await evalJs(cdp, `document.querySelector('#stepper [data-tab="${tab}"]').click()`);
    await sleep(900);
    const s = await evalJs(cdp, SNAP);
    check(
      `Reiter ${tab}: geteiltes Viewport sichtbar mit Canvas`,
      s.activePanel === tab && !!s.canvas && !s.viewport.hidden &&
        s.canvas.w > 100 && s.canvas.h > 100,
      `canvas ${s.canvas?.w}×${s.canvas?.h}`,
    );
    await shot(cdp, `smoke-${tab}.png`);
  }

  console.log("2b) Roboter-Reiter: echte M1013-Meshes sichtbar + Schema-Toggle (Issue #41)");
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="roboter"]').click()`);
  await sleep(900);
  // Async GLB-Load abwarten (headless-robust): __armDebug bis meshLoaded pollen.
  let arm = null;
  for (let i = 0; i < 40; i++) {
    arm = await evalJs(cdp, `(() => (window.__armDebug ? window.__armDebug() : null))()`);
    if (arm && (arm.meshLoaded || arm.mode === "schema")) break;
    await sleep(500);
  }
  check(
    "Roboter-Vorschau zeigt Mesh: 7 Glied-Meshes geladen, Modus mesh",
    !!arm && arm.meshLoaded === true && arm.mode === "mesh" && arm.linkMeshCount === 7,
    arm ? `mode=${arm.mode}, meshLoaded=${arm.meshLoaded}, links=${arm.linkMeshCount}` : "kein __armDebug",
  );
  await shot(cdp, "smoke-roboter-mesh.png");

  // Umschalten auf Schema und zurück — Toggle wirkt global auf die Vorschau.
  const toEnabled = await evalJs(cdp, `(() => {
    const t = document.getElementById('arm-schema-toggle');
    return t ? !t.disabled : false;
  })()`);
  if (toEnabled) {
    await evalJs(cdp, `(() => {
      const t = document.getElementById('arm-schema-toggle');
      t.checked = true; t.dispatchEvent(new Event('change'));
    })()`);
    await sleep(500);
    const schemaArm = await evalJs(cdp, `window.__armDebug()`);
    check("Toggle → Schema: effektiver Modus schema", schemaArm.mode === "schema", `mode=${schemaArm.mode}`);
    await shot(cdp, "smoke-roboter-schema.png");
    // Zurück auf Mesh (Ausgangszustand nicht verfälschen).
    await evalJs(cdp, `(() => {
      const t = document.getElementById('arm-schema-toggle');
      t.checked = false; t.dispatchEvent(new Event('change'));
    })()`);
    await sleep(300);
  } else {
    check("Schema-Toggle bedienbar (Meshes geladen)", false, "Toggle gesperrt — Mesh-Load fehlgeschlagen?");
  }

  console.log("2c) Druckplan: Fokus-Abschnitt anklicken hebt hervor, Wand bleibt sichtbar (Issue #84)");
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(900);
  const focus0 = await evalJs(cdp, `(() => (window.__focusDebug ? window.__focusDebug() : null))()`);
  check("Fokus-Diagnose vorhanden, Ausgangszustand ohne Fokus", !!focus0 && focus0.focused === null,
    focus0 ? `boxes=${focus0.boxes}, focused=${focus0.focused}, wallVisible=${focus0.wallVisible}` : "kein __focusDebug");
  if (focus0 && focus0.boxes > 0) {
    // Ersten Abschnitt fokussieren (dieselbe Panel-Logik wie der 3D-Klick;
    // Kamera-Einfassung bleibt visueller Smoke, kein Pixel-Test).
    const id = focus0.sectionIds[0];
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(300);
    const focus1 = await evalJs(cdp, `window.__focusDebug()`);
    check(
      "Klick auf Abschnitt: hervorgehoben (Quader-Deckkraft > 0) + ganze Wand sichtbar",
      focus1.focused === id && focus1.focusedOpacity > 0 && focus1.wallVisible === true,
      `focused=${focus1.focused}, opacity=${focus1.focusedOpacity}, wallVisible=${focus1.wallVisible}`,
    );
    await shot(cdp, "smoke-druckplan-fokus.png");
    // Live-Vorschau „Vorbereiten" (#85): bei Fokus gleitet die Düsen-Schablone
    // entlang der sofort gesliceten Bahn + atmender Sicherheitspuffer.
    const prep = await evalJs(cdp, `(() => (window.__prepareDebug ? window.__prepareDebug() : null))()`);
    check(
      "Vorbereiten-Vorschau aktiv: Schablonen-Posen aus geslicetem Fokus-Abschnitt (#85)",
      !!prep && prep.active === true && prep.nPoses > 0,
      prep ? `active=${prep.active}, nPoses=${prep.nPoses}, standoff=${prep.standoffMm}, safetyMin=${prep.safetyMinMm}` : "kein __prepareDebug",
    );
    // Erneuter Klick hebt den Fokus wieder auf (Toggle → sauberer Zustand).
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(200);
    const focus2 = await evalJs(cdp, `window.__focusDebug()`);
    check("Erneuter Klick: Fokus gelöst (Toggle), Wand weiterhin sichtbar",
      focus2.focused === null && focus2.wallVisible === true, `focused=${focus2.focused}`);
    const prep2 = await evalJs(cdp, `window.__prepareDebug()`);
    check("Fokus gelöst → Live-Vorschau geräumt (#85)", prep2.active === false, `active=${prep2.active}`);
  } else {
    check("Abwärtskompatibel: ohne Zerlegung keine Quader, sauberer Fokus-Zustand",
      !!focus0 && focus0.boxes === 0 && focus0.focused === null && focus0.wallVisible === true,
      "Projekt ohne Zerlegung — Highlight-Pfad nicht ausgeübt");
  }

  console.log("2d) Simulations-Dock statt Modus-Umschalter (Issue #108, kehrt #86 um)");
  // Der frühere Reiter „Simulation" ist aus der Tab-Leiste verschwunden.
  const simTabGone = await evalJs(
    cdp,
    `document.querySelector('#stepper [data-tab="simulation"]') === null`,
  );
  check("Reiter Simulation aus der Tab-Leiste entfernt", simTabGone === true, `gone=${simTabGone}`);
  // Der Modus-Umschalter „Vorbereiten/Simulieren" ist restlos entfernt (#108).
  const modeGone = await evalJs(
    cdp,
    `document.getElementById('druckplan-mode') === null && document.getElementById('mode-simulieren') === null`,
  );
  check("Modus-Radiogroup „Vorbereiten/Simulieren\" restlos entfernt (#108)", modeGone === true, `gone=${modeGone}`);
  // Im Reiter Slicing (druckplan) blendet sich das Simulations-Dock am Fuß des
  // Viewports ein — ohne Modus-Wechsel; Simulier-Knöpfe + Player docken hier an.
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(500);
  const dockState = await evalJs(cdp, `(() => {
    const dock = document.getElementById('sim-dock');
    return {
      dockVisible: !!dock && dock.hidden === false,
      focusBtn: !!document.getElementById('sim-focus-btn'),
      seqBtn: !!document.getElementById('sim-sequence-btn'),
      player: !!document.getElementById('sim-player'),
      slider: !!document.getElementById('sim-slider'),
      phase: !!document.getElementById('sim-phase'),
    };
  })()`);
  check(
    "Slicing-Reiter zeigt das Simulations-Dock (Fokus-/Wand-Knopf + Player/Timeline/Phase)",
    dockState.dockVisible && dockState.focusBtn && dockState.seqBtn && dockState.player && dockState.slider && dockState.phase,
    JSON.stringify(dockState),
  );
  await shot(cdp, "smoke-druckplan-simulieren.png");

  console.log("2e) Reiter Zerlegung: Inspector aus Accordions + vereinter Vorschlag-Button (Issue #106)");
  // Der Druckplan-Split (#106): „Zerlegung & Platzierung" ist ein eigener Reiter
  // mit Inspector; die frühere Rubriken-Umschaltung entfällt. Der Reiter enthält
  // den vereinten Vorschlag-Button, die drei Accordions und die Slicing-Rubrik
  // NICHT (die lebt im Reiter Druckplan).
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="zerlegung"]').click()`);
  await sleep(600);
  const insp = await evalJs(cdp, `(() => ({
    panelShown: document.querySelector('.tab-panel[data-panel="zerlegung"]')?.hidden === false,
    autoBtn: !!document.getElementById('zerlegung-auto-btn'),
    accToggles: document.querySelectorAll('#zerlegung-aside .accordion-toggle').length,
    artBodyPresent: !!document.getElementById('zerlegung-acc-art-body'),
    cutsBodyPresent: !!document.getElementById('zerlegung-acc-cuts-body'),
    placementBodyPresent: !!document.getElementById('zerlegung-acc-placement-body'),
    checkBtn: document.getElementById('decompose-check-btn')?.textContent ?? null,
    rubricsGone: document.getElementById('druckplan-rubrics') === null,
    oldSuggestGone: document.getElementById('placement-suggest-btn') === null &&
      document.getElementById('decompose-btn') === null,
  }))()`);
  check(
    "Zerlegungs-Inspector: Panel sichtbar, vereinter Vorschlag-Button, 3 Accordions, Prüfen-lassen-Footer; alte Rubriken/Buttons entfernt",
    insp.panelShown && insp.autoBtn && insp.accToggles === 3 &&
      insp.artBodyPresent && insp.cutsBodyPresent && insp.placementBodyPresent &&
      /Prüfen lassen/.test(insp.checkBtn ?? "") && insp.rubricsGone && insp.oldSuggestGone,
    JSON.stringify(insp),
  );
  // Accordion einklappen/aufklappen (▸/▾ + `.hidden`), Zustand persistiert je Gruppe.
  const acc = await evalJs(cdp, `(() => {
    const t = document.getElementById('zerlegung-acc-cuts-toggle');
    const body = document.getElementById('zerlegung-acc-cuts-body');
    const before = body.hidden;
    t.click();
    const afterCollapsed = body.hidden;
    t.click();
    const afterExpanded = body.hidden;
    return { before, afterCollapsed, afterExpanded, marker: t.querySelector('.acc-marker')?.textContent };
  })()`);
  check(
    "Accordion Schnittplan klappt zu und wieder auf (nur `.hidden`, ▸/▾)",
    acc.before === false && acc.afterCollapsed === true && acc.afterExpanded === false,
    JSON.stringify(acc),
  );
  await shot(cdp, "smoke-zerlegung-inspector.png");

  console.log("2f) Teile-Palette am 3D-Feld: Auswahl↔Fokus-Sync + Override-Marker (Issue #91), jetzt im Reiter Zerlegung (#106)");
  // Die Palette schwebt über dem 3D-Feld im Reiter Zerlegung (Issue #106).
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="zerlegung"]').click()`);
  await sleep(400);
  const pal0 = await evalJs(cdp, `(() => (window.__partsPaletteDebug ? window.__partsPaletteDebug() : null))()`);
  check(
    "Teile-Palette am 3D-Feld sichtbar (Reiter Zerlegung, #106)",
    !!pal0 && pal0.visible === true,
    pal0 ? `visible=${pal0.visible}, count=${pal0.count}, collapsed=${pal0.collapsed}` : "kein __partsPaletteDebug",
  );
  if (pal0 && pal0.count > 0) {
    const id = pal0.entries[0].sectionId;
    // Palette in den Fokus setzen (dieselbe Panel-Logik wie der 3D-Klick) →
    // der Eintrag ist gewählt UND der 3D-Fokus steht auf demselben Teil (Sync).
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(200);
    const pal1 = await evalJs(cdp, `window.__partsPaletteDebug()`);
    const foc1 = await evalJs(cdp, `window.__focusDebug()`);
    check(
      "Fokus setzen ⇒ Palette-Eintrag gewählt und 3D-Fokus synchron",
      pal1.entries.find((e) => e.sectionId === id)?.selected === true && foc1.focused === id,
      `paletteSelected=${pal1.entries.find((e) => e.sectionId === id)?.selected}, focus3d=${foc1.focused}`,
    );
    // Umgekehrt: Klick auf den Teil-Namen in der Palette togglet den Fokus wieder
    // weg (Palette treibt den 3D-Fokus — beidseitig synchron).
    await evalJs(cdp, `document.querySelector('.parts-part[data-section=${JSON.stringify(id)}] .parts-part-name').click()`);
    await sleep(200);
    const foc2 = await evalJs(cdp, `window.__focusDebug()`);
    const pal2 = await evalJs(cdp, `window.__partsPaletteDebug()`);
    check(
      "Palette-Klick treibt den 3D-Fokus (Toggle löst) — beidseitig synchron",
      foc2.focused === null && pal2.entries.every((e) => e.selected === false),
      `focus3d=${foc2.focused}`,
    );
    // ▪-Marker: erscheint bei gesetztem Slicing-Override, verschwindet ohne.
    await evalJs(cdp, `window.__setSlicingOverrideMarker([${JSON.stringify(id)}])`);
    const palM = await evalJs(cdp, `window.__partsPaletteDebug()`);
    await evalJs(cdp, `window.__setSlicingOverrideMarker([])`);
    const palN = await evalJs(cdp, `window.__partsPaletteDebug()`);
    check(
      "▪-Marker erscheint bei Override und verschwindet, wenn er entfernt wird",
      palM.entries.find((e) => e.sectionId === id)?.marker === true &&
        palN.entries.find((e) => e.sectionId === id)?.marker === false,
      `mitOverride=${palM.entries.find((e) => e.sectionId === id)?.marker}, ohne=${palN.entries.find((e) => e.sectionId === id)?.marker}`,
    );
    await shot(cdp, "smoke-teile-palette.png");
  } else {
    check(
      "Abwärtskompatibel: ohne Zerlegung leere Palette am 3D-Feld (Leerhinweis)",
      !!pal0 && pal0.count === 0 && pal0.visible === true,
      "Projekt ohne Zerlegung — Palette-Einträge nicht ausgeübt",
    );
  }

  console.log("2g) Gilt-für-Umschalter Global-Teil (Slicing, Reiter Druckplan): feldweise Overrides (Issue #92; #106: nur Slicing, kein Ausgrauen struktureller Gruppen)");
  // Der Umschalter lebt seit #106 im Reiter Druckplan (Slicing) — dort wechseln.
  // Kein Teil gewählt (2f hat den Fokus gelöst) → Umschalter unsichtbar, global.
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(400);
  const scope0 = await evalJs(cdp, `(() => (window.__scopeDebug ? window.__scopeDebug() : null))()`);
  check(
    "Ohne gewähltes Teil: Umschalter unsichtbar, Scope global",
    !!scope0 && scope0.visible === false && scope0.scope === "global",
    scope0 ? JSON.stringify(scope0) : "kein __scopeDebug",
  );
  if (pal0 && pal0.count > 0 && scope0) {
    const id = pal0.entries[0].sectionId;
    // Teil wählen (Teile-Palette/Fokus) → Umschalter erscheint, Stellung Global.
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(200);
    const scope1 = await evalJs(cdp, `window.__scopeDebug()`);
    check(
      "Teil wählen: Umschalter erscheint (Stellung bleibt Global)",
      scope1.visible === true && scope1.scope === "global" && scope1.sectionId === id,
      JSON.stringify(scope1),
    );
    // Auf Teil stellen: die Slicing-Formulare übersteuern nun feldweise; die
    // strukturellen Gruppen sind seit #106 nicht mehr hier (kein Ausgrauen).
    const scope2 = await evalJs(cdp, `(() => {
      const t = document.getElementById('scope-teil');
      t.checked = true; t.dispatchEvent(new Event('change'));
      return window.__scopeDebug();
    })()`);
    check(
      "Auf Teil: Slicing-Feld bedienbar, geerbter Wert dezent als Platzhalter",
      scope2.scope === "teil" && scope2.layerDisabled === false &&
        String(scope2.layerPlaceholder).endsWith("· erbt"),
      JSON.stringify(scope2),
    );
    // Feld übersteuern → feldweiser Override markiert + sein Reset-Knopf sichtbar.
    const before = await evalJs(cdp, `window.__revisionsDebug ? window.__revisionsDebug() : null`);
    const over = await evalJs(cdp, `(() => {
      const inp = document.getElementById('process-params-layer-height');
      inp.value = '42'; inp.dispatchEvent(new Event('input'));
      return window.__scopeDebug();
    })()`);
    check(
      "Eingabe: Feld als Override markiert + Reset-Knopf sichtbar",
      over.layerOverridden === true && over.layerResetVisible === true,
      JSON.stringify(over),
    );
    // Speichern (dieselbe process-params-Route, Feld sections) → Marker + Veraltung.
    await evalJs(cdp, `document.getElementById('process-params-save-btn').click()`);
    await sleep(1500);
    const palO = await evalJs(cdp, `window.__partsPaletteDebug()`);
    check(
      "Speichern: Palette-Marker am übersteuerten Teil erscheint",
      palO.entries.find((e) => e.sectionId === id)?.marker === true,
      `marker=${palO.entries.find((e) => e.sectionId === id)?.marker}`,
    );
    // #83 bleibt in Kraft: nur der Zähler DIESES Teils wurde gebumpt.
    const revs = await evalJs(cdp, `window.__revisionsDebug()`);
    const beforeInputs = (before && before.section_inputs) || {};
    const afterInputs = (revs && revs.section_inputs) || {};
    const ownBumped = (afterInputs[id] ?? 0) > (beforeInputs[id] ?? 0);
    const otherBumped = Object.entries(afterInputs).some(
      ([sid, v]) => sid !== id && v > (beforeInputs[sid] ?? 0),
    );
    check(
      "Teil-Override veraltet NUR dieses Teil (section_inputs, #83)",
      ownBumped === true && otherBumped === false,
      JSON.stringify(afterInputs),
    );
    // Reset-Knopf: genau dieses Feld erbt wieder; Speichern raeumt den Marker.
    await evalJs(cdp, `(() => {
      const r = document.getElementById('process-params-layer-height-reset');
      if (r && !r.hidden) r.click();
    })()`);
    await evalJs(cdp, `document.getElementById('process-params-save-btn').click()`);
    await sleep(1500);
    const palR = await evalJs(cdp, `window.__partsPaletteDebug()`);
    check(
      "Reset + Speichern: Marker verschwindet (Override entfernt)",
      palR.entries.find((e) => e.sectionId === id)?.marker === false,
      `marker=${palR.entries.find((e) => e.sectionId === id)?.marker}`,
    );
    // Zurueck auf Global.
    const scope3 = await evalJs(cdp, `(() => {
      const g = document.getElementById('scope-global');
      g.checked = true; g.dispatchEvent(new Event('change'));
      return window.__scopeDebug();
    })()`);
    check(
      "Zurueck auf Global: Slicing-Feld wieder global",
      scope3.scope === "global" && scope3.layerDisabled === false,
      JSON.stringify(scope3),
    );
    // Teil abwaehlen (Toggle) → Umschalter verschwindet (Ausgangszustand).
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(200);
    const scope4 = await evalJs(cdp, `window.__scopeDebug()`);
    check(
      "Abwahl des Teils: Umschalter verschwindet, globale Werte wieder gezeigt",
      scope4.visible === false && scope4.scope === "global",
      JSON.stringify(scope4),
    );
    await shot(cdp, "smoke-scope-switch.png");
  } else {
    check(
      "Abwaertskompatibel: ohne Zerlegung kein Umschalter (kein Teil waehlbar)",
      !!scope0 && scope0.visible === false,
      "Projekt ohne Zerlegung — Scope-Pfad nicht ausgeuebt",
    );
  }

  console.log("2h) Platzierung sichtbar: Basis-Marker aller Teile + M1013-Mesh am Fokus (Issue #93)");
  // Reiter Druckplan sicherstellen (Marker/Mesh nur dort). Ohne Modus (#108):
  // solange kein Replay läuft, sind die Platzierungs-Marker aktiv.
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(400);
  const plc0 = await evalJs(cdp, `(() => (window.__placementDebug ? window.__placementDebug() : null))()`);
  check(
    "Basis-Marker aller Teile sichtbar: Marker-Anzahl = Teile-Anzahl (kein Replay)",
    !!plc0 && plc0.markers === plc0.sectionCount && plc0.meshVisible === false,
    plc0 ? `markers=${plc0.markers}, teile=${plc0.sectionCount}, mesh=${plc0.meshVisible}` : "kein __placementDebug",
  );
  if (plc0 && plc0.sectionCount > 0) {
    const id = plc0.sectionIds ? plc0.sectionIds[0] : null;
    // Falls __placementDebug keine ids liefert, den ersten Palette-Eintrag nehmen.
    const focusId = id ?? (await evalJs(cdp, `window.__partsPaletteDebug().entries[0].sectionId`));
    // Fokus setzen → das echte M1013-Mesh erscheint an der Platzierung, sein Marker weicht.
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(focusId)})`);
    await sleep(300);
    const plc1 = await evalJs(cdp, `window.__placementDebug()`);
    check(
      "Fokus ⇒ echtes M1013-Mesh sichtbar an der Platzierung, Fokus-Marker weicht (sauberer Tausch)",
      plc1.meshVisible === true && plc1.focused === focusId && plc1.hiddenMarker === focusId,
      `mesh=${plc1.meshVisible}, focused=${plc1.focused}, hiddenMarker=${plc1.hiddenMarker}`,
    );
    await shot(cdp, "smoke-platzierung-mesh.png");
    // Fokus lösen (Toggle) → Mesh verschwindet, alle Marker wieder sichtbar.
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(focusId)})`);
    await sleep(200);
    const plc2 = await evalJs(cdp, `window.__placementDebug()`);
    check(
      "Fokus gelöst ⇒ Mesh geräumt, alle Teil-Marker wieder sichtbar",
      plc2.meshVisible === false && plc2.hiddenMarker === null && plc2.markers === plc2.sectionCount,
      `mesh=${plc2.meshVisible}, hiddenMarker=${plc2.hiddenMarker}, markers=${plc2.markers}`,
    );
  } else {
    check(
      "Abwärtskompatibel: ohne Zerlegung keine Platzierungs-Marker, kein Mesh",
      !!plc0 && plc0.markers === 0 && plc0.meshVisible === false,
      "Projekt ohne Zerlegung — Marker/Mesh-Pfad nicht ausgeübt",
    );
  }

  console.log("2i) Platzierung — <Teil> (Accordion im Reiter Zerlegung, #106/#94): Fokus macht die Felder bedienbar (kein Scope) ⇒ Override wandert + nur dieses Teil veraltet");
  // Seit #106 leben die 3 Platzierungsfelder im „Platzierung — <Teil>"-Accordion
  // des Reiters Zerlegung und sind FOKUS-getrieben (kein Gilt-für-Umschalter).
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="zerlegung"]').click()`);
  await sleep(400);
  const pov0 = await evalJs(cdp, `(() => (window.__placementDebug ? window.__placementDebug() : null))()`);
  if (pov0 && pov0.sectionCount > 0) {
    const id = pov0.sectionIds[0];
    const other = pov0.sectionIds.find((s) => s !== id) ?? null;
    const posBefore = pov0.positions[id];
    const revBefore = await evalJs(cdp, `window.__revisionsDebug ? window.__revisionsDebug() : null`);
    // Teil wählen (Fokus) → die Platzierungsfelder werden bedienbar; der Accordion-
    // Titel nennt das Teil.
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(300);
    const enabled = await evalJs(cdp, `(() => {
      const inp = document.getElementById('placement-override-standoff');
      return {
        disabled: inp.disabled,
        placeholder: String(inp.placeholder),
        title: document.getElementById('zerlegung-placement-title')?.textContent ?? '',
      };
    })()`);
    check(
      "Fokus: Platzierungsfeld bedienbar, automatischer Wert dezent als Platzhalter (· Auto), Accordion-Titel nennt das Teil",
      enabled.disabled === false && enabled.placeholder.endsWith("Auto") &&
        enabled.title.startsWith("Platzierung —"),
      JSON.stringify(enabled),
    );
    // Abstand frei übersteuern (deutlich versetzt) → persistiert + Neubewertung
    // (debounced) → Basis-Marker folgt der neuen Platzierung (Issue #93/#94).
    await evalJs(cdp, `(() => {
      const inp = document.getElementById('placement-override-standoff');
      inp.value = '1200';
      inp.dispatchEvent(new Event('change'));
    })()`);
    // Setter (persist) + debounced „Prüfen" (700ms) + Core-Rundlauf + Marker-Rebuild.
    await sleep(3000);
    const pov1 = await evalJs(cdp, `window.__placementDebug()`);
    const posAfter = pov1.positions[id];
    const moved =
      !!posBefore && !!posAfter &&
      (posBefore[0] !== posAfter[0] || posBefore[1] !== posAfter[1] || posBefore[2] !== posAfter[2]);
    check(
      "Override gesetzt ⇒ Basis-Marker des Teils wandert (folgt der Platzierung nach der Neubewertung)",
      moved,
      `vorher=${JSON.stringify(posBefore)}, nachher=${JSON.stringify(posAfter)}`,
    );
    const palP = await evalJs(cdp, `window.__partsPaletteDebug()`);
    check(
      "▪-Marker zählt Platzierungs-Overrides mit (#94)",
      palP.entries.find((e) => e.sectionId === id)?.marker === true,
      `marker=${palP.entries.find((e) => e.sectionId === id)?.marker}`,
    );
    // #83: nur der Zähler DIESES Teils wurde gebumpt (Nachbar bleibt aktuell).
    const revAfter = await evalJs(cdp, `window.__revisionsDebug()`);
    const beforeS = (revBefore && revBefore.section_inputs) || {};
    const afterS = (revAfter && revAfter.section_inputs) || {};
    const ownBumped = (afterS[id] ?? 0) > (beforeS[id] ?? 0);
    const otherBumped =
      other !== null && (afterS[other] ?? 0) > (beforeS[other] ?? 0);
    check(
      "Platzierungs-Override veraltet NUR dieses Teil (section_inputs, #83)",
      ownBumped === true && otherBumped === false,
      `own=${afterS[id]}, other(${other})=${other !== null ? afterS[other] : "n/a"}`,
    );
    await shot(cdp, "smoke-platzierung-override.png");
    // ↺ zurück auf Automatik: Feld räumen → automatische Platzierung, Marker zurück.
    await evalJs(cdp, `(() => {
      const r = document.getElementById('placement-override-standoff-reset');
      if (r && !r.hidden) r.click();
    })()`);
    await sleep(3000);
    const pov2 = await evalJs(cdp, `window.__placementDebug()`);
    const posReset = pov2.positions[id];
    check(
      "↺ zurück auf Automatik ⇒ Basis-Marker kehrt zur automatischen Platzierung zurück",
      !!posBefore && !!posReset &&
        posBefore[0] === posReset[0] && posBefore[1] === posReset[1] && posBefore[2] === posReset[2],
      `automatisch=${JSON.stringify(posBefore)}, nachReset=${JSON.stringify(posReset)}`,
    );
    // Ausgangszustand: Teil abwaehlen (Fokus lösen).
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(id)})`);
    await sleep(200);
  } else {
    check(
      "Abwärtskompatibel: ohne Zerlegung keine Platzierungs-Override-Felder",
      !!pov0 && pov0.sectionCount === 0,
      "Projekt ohne Zerlegung — Platzierungs-Override-Pfad nicht ausgeübt",
    );
  }

  console.log("2j) Zerlegungsart-Weiche Abschnitte↔Module: Sichtbarkeitsmatrix + Artwechsel (Issue #95), im Reiter Zerlegung (#106)");
  // Reiter Zerlegung sicherstellen (die Weiche steht im Accordion „Art & Aufstellung").
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="zerlegung"]').click()`);
  await sleep(400);
  // Ausgangszustand: Art „abschnitt" → Aufstell-Gruppe sichtbar, Modulgrößen-Gruppe
  // versteckt (Sichtbarkeitsmatrix, nur `.hidden`); die alte deaktivierte Dropdown-
  // Option ist verschwunden (kein #decompose-kind mehr).
  const weiche0 = await evalJs(cdp, `(() => ({
    dropdownGone: document.getElementById('decompose-kind') === null,
    hasRadios: !!document.getElementById('zerlegungsart-abschnitt') && !!document.getElementById('zerlegungsart-modul'),
    modulSelectable: !document.getElementById('zerlegungsart-modul').disabled,
    aufstellHidden: document.getElementById('aufstell-group').hidden,
    moduleLimitsHidden: document.getElementById('module-limits-group').hidden,
    abschnittChecked: document.getElementById('zerlegungsart-abschnitt').checked,
  }))()`);
  check(
    "Radiogruppe oben, Dropdown-Option entfällt, Modul wählbar, Abschnitt→Aufstell sichtbar/Module-Maße aus",
    weiche0.dropdownGone && weiche0.hasRadios && weiche0.modulSelectable &&
      weiche0.abschnittChecked && weiche0.aufstellHidden === false && weiche0.moduleLimitsHidden === true,
    JSON.stringify(weiche0),
  );
  await shot(cdp, "smoke-weiche-abschnitt.png");

  // Gebäudekontext-Schalter der Kollisionskontrolle (Issue #131): eigene Gruppe im
  // Accordion „Art & Aufstellung", bei Abschnitt sichtbar (bei Modul gegenstandslos).
  // Toggeln persistiert über die Core-Route und überlebt das Umschalten (Persist/
  // Restore prüft der vitest-Anker; hier der DOM-/Sicht-Vertrag).
  const ctxAbschnitt = await evalJs(cdp, `(() => {
    const grp = document.getElementById('kontext-group');
    const box = document.getElementById('kontext-check');
    return {
      groupPresent: !!grp,
      visibleAbschnitt: !!grp && grp.hidden === false,
      isCheckbox: box?.type === 'checkbox',
      checkedInitially: box?.checked ?? null,
    };
  })()`);
  check(
    "Gebäudekontext-Schalter (#131): Gruppe + Checkbox vorhanden, bei Abschnitt sichtbar, Default aus",
    ctxAbschnitt.groupPresent && ctxAbschnitt.visibleAbschnitt &&
      ctxAbschnitt.isCheckbox && ctxAbschnitt.checkedInitially === false,
    JSON.stringify(ctxAbschnitt),
  );
  // Einschalten (persistiert über die Core-Route) + wieder aus (Ausgangszustand).
  const ctxToggle = await evalJs(cdp, `(() => {
    const box = document.getElementById('kontext-check');
    box.checked = true; box.dispatchEvent(new Event('change'));
    return { onChecked: box.checked };
  })()`);
  check(
    "Gebäudekontext-Schalter einschaltbar (Checkbox reagiert)",
    ctxToggle.onChecked === true,
    JSON.stringify(ctxToggle),
  );
  await sleep(600);
  await evalJs(cdp, `(() => {
    const box = document.getElementById('kontext-check');
    box.checked = false; box.dispatchEvent(new Event('change'));
  })()`);
  await sleep(400);
  await shot(cdp, "smoke-kontext-schalter.png");

  // Vor dem Artwechsel: Schnittebenen des aktuellen Plans merken (müssen bleiben).
  const cutsBefore = await evalJs(cdp, `(() => (window.__focusDebug ? window.__focusDebug().boxes : 0))()`);
  // Auf „Module" umschalten → Sichtbarkeitsmatrix kippt (nur `.hidden`); die Schnitte
  // bleiben (zerlegungsart-neutral, ADR-022 Punkt 5), der Plan wird ungeprüft (dirty
  // → alle Palette-Ampeln „ungeprueft"); die Palette heißt jetzt „Module".
  const weiche1 = await evalJs(cdp, `(() => {
    const modul = document.getElementById('zerlegungsart-modul');
    modul.checked = true; modul.dispatchEvent(new Event('change'));
    return {
      aufstellHidden: document.getElementById('aufstell-group').hidden,
      kontextHidden: document.getElementById('kontext-group').hidden,
      moduleLimitsHidden: document.getElementById('module-limits-group').hidden,
      boxes: window.__focusDebug ? window.__focusDebug().boxes : 0,
      dirtyAmpeln: (window.__partsPaletteDebug ? window.__partsPaletteDebug().entries : [])
        .every((e) => e.ampel === 'ungeprueft'),
      toggleText: document.getElementById('parts-palette-toggle').textContent,
    };
  })()`);
  check(
    "Artwechsel → Module: Sichtbarkeitsmatrix kippt (Aufstell aus, Module-Maße an) nur über .hidden",
    weiche1.aufstellHidden === true && weiche1.moduleLimitsHidden === false,
    JSON.stringify(weiche1),
  );
  check(
    "Artwechsel → Module: Gebäudekontext-Schalter ausgeblendet (gegenstandslos, #131/ADR-022)",
    weiche1.kontextHidden === true,
    `kontextHidden=${weiche1.kontextHidden}`,
  );
  check(
    "Artwechsel behält ALLE Schnitte (zerlegungsart-neutral, ADR-022)",
    weiche1.boxes === cutsBefore,
    `vorher=${cutsBefore}, nachher=${weiche1.boxes}`,
  );
  check(
    "Artwechsel setzt dirty (Palette-Ampeln ungeprueft) + Palette-Beschriftung Module",
    (cutsBefore === 0 || weiche1.dirtyAmpeln === true) && /Module/.test(weiche1.toggleText),
    `dirty=${weiche1.dirtyAmpeln}, toggle=${weiche1.toggleText}`,
  );
  // Re-Check mit der neuen Art abwarten (debounced 700ms + Core-Rundlauf); bei
  // gewählter Workstation zeigt die Palette dann je Modul das Gewicht (kg).
  await sleep(3500);
  const weiche2 = await evalJs(cdp, `(() => {
    const mods = Array.from(document.querySelectorAll('#parts-palette-list .parts-part-module'));
    return {
      hintShown: !document.getElementById('zerlegungsart-hint').hidden,
      nGewicht: mods.length,
      gewichtSample: mods[0] ? mods[0].textContent : null,
    };
  })()`);
  check(
    "Art Module: entweder Gewicht (kg) je Modul sichtbar, oder freundlicher Workstation-Hinweis (kein Absturz, kein Gate)",
    (weiche2.nGewicht > 0 && /kg/.test(weiche2.gewichtSample ?? "")) || weiche2.hintShown === true,
    JSON.stringify(weiche2),
  );
  await shot(cdp, "smoke-weiche-module.png");

  console.log("2k) Druckort-Ansicht: Modul fokussieren → Druckort → Roboter + Modul sichtbar → zurück (Issue #96)");
  // Die Art steht seit 2j auf „Module" und der Re-Check ist gelaufen. Ohne
  // Fokus existiert der Umschalter Einbauort↔Druckort nicht (Einbauort =
  // Druckort gilt nur für Abschnitte — bei Modulen braucht er den Fokus).
  const dk0 = await evalJs(cdp, `(() => (window.__druckortDebug ? window.__druckortDebug() : null))()`);
  check(
    "Ohne Modul-Fokus: kein Druckort-Umschalter, Ansicht Einbauort",
    !!dk0 && dk0.available === false && dk0.view === "einbauort",
    dk0 ? JSON.stringify(dk0) : "kein __druckortDebug",
  );
  const dkIds = await evalJs(cdp, `window.__focusDebug ? window.__focusDebug().sectionIds : []`);
  if (dk0 && dkIds.length > 0) {
    const dkId = dkIds[0];
    // Modul fokussieren (dieselbe Panel-Logik wie der 3D-Klick, #84).
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(dkId)})`);
    await sleep(300);
    const dk1 = await evalJs(cdp, `window.__druckortDebug()`);
    check(
      "Modul-Fokus: Umschalter Einbauort↔Druckort erscheint (Stellung Einbauort)",
      dk1.available === true && dk1.view === "einbauort",
      JSON.stringify(dk1),
    );
    // Auf Druckort schalten: Szene blendet auf die Workstation um (Roboter an
    // robot_base_frame + Modul-Rechteck an der Core-Lage) — ODER, wenn die
    // Workstation keine Platzierungs-Frames trägt, erscheint der freundliche
    // Hinweis statt der Ansicht (Befund, kein Gate — beides gültige Pfade).
    await evalJs(cdp, `(() => {
      const r = document.getElementById('druckort-view-druckort');
      r.checked = true; r.dispatchEvent(new Event('change'));
    })()`);
    await sleep(1200);
    const dk2 = await evalJs(cdp, `window.__druckortDebug()`);
    const druckortShown =
      dk2.view === "druckort" && dk2.robotVisible === true &&
      dk2.moduleVisible === true && dk2.worldVisible === false;
    const hintShown = dk2.view === "einbauort" && dk2.hint !== null;
    check(
      "Druckort: Roboter + Modul sichtbar, Wand-Szene aus — oder Frame-Hinweis (kein Gate)",
      druckortShown || hintShown,
      JSON.stringify(dk2),
    );
    await shot(cdp, "smoke-druckort.png");
    if (druckortShown) {
      // Rückweg: Einbauort stellt die Wand-Ansicht wieder her (weiche Fahrt, #84).
      await evalJs(cdp, `(() => {
        const r = document.getElementById('druckort-view-einbauort');
        r.checked = true; r.dispatchEvent(new Event('change'));
      })()`);
      await sleep(900);
      const dk3 = await evalJs(cdp, `window.__druckortDebug()`);
      check(
        "Rückweg Einbauort: Wand-Ansicht wieder sichtbar, Druckort-Szene geräumt",
        dk3.view === "einbauort" && dk3.worldVisible === true &&
          dk3.robotVisible === false && dk3.moduleVisible === false,
        JSON.stringify(dk3),
      );
    }
    // Fokus lösen (Ausgangszustand) → Umschalter verschwindet.
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(dkId)})`);
    await sleep(200);
    const dk4 = await evalJs(cdp, `window.__druckortDebug()`);
    check(
      "Fokus gelöst: Umschalter verschwindet, Ansicht bleibt Einbauort",
      dk4.available === false && dk4.view === "einbauort",
      JSON.stringify(dk4),
    );
  } else {
    check(
      "Abwärtskompatibel: ohne Teile kein Druckort-Umschalter",
      !!dk0 && dk0.available === false,
      "Projekt ohne Zerlegung — Druckort-Pfad nicht ausgeübt",
    );
  }

  console.log("2l) Modul-Simulation: Dock zeigt „Alle Module\", Fokus-Modul spielt am Druckort (Issue #97/#108)");
  // Art steht seit 2j auf Module. Das Dock ist im Slicing-Reiter ohne Modus sofort
  // da; die artabhaengigen Knoepfe pruefen (Beschriftung folgt der Zerlegungsart):
  // ▶ Fokus-Modul simulieren + Alle Module (statt Fokus-Abschnitt + Ganze Wand).
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(300);
  const simLabels = await evalJs(cdp, `(() => {
    return {
      focusBtn: document.getElementById('sim-focus-btn')?.textContent ?? null,
      seqBtn: document.getElementById('sim-sequence-btn')?.textContent ?? null,
      dockVisible: document.getElementById('sim-dock')?.hidden === false,
    };
  })()`);
  check(
    "Modul-Art: Knoepfe heissen ▶ Fokus-Modul simulieren + Alle Module (Beschriftung folgt der Art)",
    simLabels.dockVisible &&
      simLabels.focusBtn?.includes("Fokus-Modul simulieren") &&
      simLabels.seqBtn === "Alle Module",
    JSON.stringify(simLabels),
  );
  await shot(cdp, "smoke-modul-simulieren.png");
  // Fokus-Modul simulieren: Modul fokussieren + Knopf druecken -> frischer Lauf
  // (Core) und Wiedergabe in der Druckort-Ansicht (fester Roboter, Modul auf der
  // Arbeitsflaeche). Braucht die Core-API; ohne erreichbare API/Module bleibt der
  // Knopf gesperrt (dann nur die Beschriftung geprueft, kein Gate).
  const simIds = await evalJs(cdp, `window.__focusDebug ? window.__focusDebug().sectionIds : []`);
  const apiUp = await evalJs(cdp, `document.getElementById('sim-api-warning')?.hidden === true`);
  if (simIds.length > 0 && apiUp) {
    await evalJs(cdp, `window.__focusSection(${JSON.stringify(simIds[0])})`);
    await sleep(300);
    await evalJs(cdp, `document.getElementById('sim-focus-btn').click()`);
    // Slice + Simulate (Core) + Laden + Buehne bauen abwarten (headless-robust pollen).
    let msim = null;
    for (let i = 0; i < 40; i++) {
      msim = await evalJs(cdp, `(() => (window.__moduleSimDebug ? window.__moduleSimDebug() : null))()`);
      if (msim && msim.active && msim.atDruckort) break;
      await sleep(500);
    }
    check(
      "Fokus-Modul simulieren: Wiedergabe startet am Druckort (Roboter + Modul auf der Arbeitsflaeche)",
      !!msim && msim.active === true && msim.atDruckort === true &&
        msim.robotVisible === true && msim.moduleVisible === true,
      msim ? JSON.stringify(msim) : "kein __moduleSimDebug",
    );
    await shot(cdp, "smoke-modul-druckort-replay.png");
    // #154: Im Replay-Modus verschwinden die Startknöpfe, der Player steht — zwei
    // Modi statt Überlagerung (Karte #139, Entscheidung #148). Gilt für BEIDE
    // Bühnen; hier am Modul-Replay (Druckort) geprüft.
    const replayMode = await evalJs(cdp, `(() => {
      const focus = document.getElementById('sim-focus-btn');
      const seq = document.getElementById('sim-sequence-btn');
      const player = document.getElementById('sim-player');
      return {
        focusHidden: focus ? focus.hidden : null,
        seqHidden: seq ? seq.hidden : null,
        playerVisible: player ? player.hidden === false : null,
      };
    })()`);
    check(
      "Replay-Modus (#154): Startknöpfe versteckt, Player sichtbar (keine Überlagerung)",
      replayMode.focusHidden === true &&
        replayMode.seqHidden === true &&
        replayMode.playerVisible === true,
      JSON.stringify(replayMode),
    );
    // #153: Am Druckort trägt der Player die Kollisionsanzeige des AKTIVEN Moduls,
    // sobald dessen frischer Lauf einen Befund hat: Live-Abstand + modul-lokal
    // projizierte Marker. Ohne Befund (Altlauf) bleibt alles leer — kein Crash.
    // Toleranter DOM-/Debug-Vertrag (Befund-Vorkommen ist nicht garantiert).
    const mcoll = await evalJs(cdp, `(() => {
      const dbg = window.__moduleSimDebug ? window.__moduleSimDebug() : null;
      const dist = document.getElementById('sim-collision-dist');
      const markers = document.getElementById('sim-collision-markers');
      return {
        hasFinding: !!(dbg && dbg.activeCollision),
        distHidden: dist ? dist.hidden : true,
        markerCount: markers ? markers.querySelectorAll('.sim-collision-marker').length : 0,
      };
    })()`);
    check(
      "Druckort-Replay: bei Befund Live-Abstand/Marker des aktiven Moduls; ohne Befund leer (kein Crash)",
      mcoll.hasFinding
        ? (mcoll.distHidden === false || mcoll.markerCount >= 0)
        : (mcoll.markerCount === 0 && mcoll.distHidden === true),
      JSON.stringify(mcoll),
    );
    // Zurueck zur Uebersicht (Modul-Replay sauber verlassen).
    await evalJs(cdp, `(() => { const b = document.getElementById('sim-back-btn'); if (b) b.click(); })()`);
    await sleep(800);
    const mafter = await evalJs(cdp, `window.__moduleSimDebug()`);
    check(
      "Zurueck zur Uebersicht: Modul-Replay verlassen",
      mafter.active === false,
      JSON.stringify(mafter),
    );
    // #154: „← Übersicht" schaltet zuverlässig in den Start-Modus zurück — die
    // Startknöpfe sind wieder da, der Player weg (auch am Ende eines Modul-Replays).
    const startMode = await evalJs(cdp, `(() => {
      const focus = document.getElementById('sim-focus-btn');
      const player = document.getElementById('sim-player');
      return {
        focusVisible: focus ? focus.hidden === false : null,
        playerHidden: player ? player.hidden === true : null,
      };
    })()`);
    check(
      "Start-Modus zurück (#154): nach „← Übersicht\" stehen die Startknöpfe, Player weg",
      startMode.focusVisible === true && startMode.playerHidden === true,
      JSON.stringify(startMode),
    );
  } else {
    check(
      "Abwaertskompatibel: ohne Core-API/Module nur Beschriftung geprueft (Knopf gesperrt)",
      simLabels.seqBtn === "Alle Module",
      `apiUp=${apiUp}, module=${simIds.length}`,
    );
  }
  // Zurück auf „Abschnitte" (Ausgangszustand nicht verfälschen).
  await evalJs(cdp, `(() => {
    const a = document.getElementById('zerlegungsart-abschnitt');
    a.checked = true; a.dispatchEvent(new Event('change'));
  })()`);
  await sleep(2500);

  console.log("2m) Kollisionskontrolle S3: Player-Anzeigen + ⚙-Sicht-Schalter (Issue #128, ADR-024)");
  // Reiter Slicing (druckplan): der Player trägt die Kollisions-Marker-Leiste,
  // die Live-Abstandszahl und das Befund-Badge; das ⚙-Menü führt die beiden neuen
  // Sicht-Schalter (Druckstand, Abstandszahl). Reiner DOM-Vertrag — tolerant
  // gegenüber fehlendem Core/Befund (Altlauf: alles leer/versteckt, kein Absturz).
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="druckplan"]').click()`);
  await sleep(400);
  const coll = await evalJs(cdp, `(() => {
    const dist = document.getElementById('sim-collision-dist');
    const badge = document.getElementById('sim-collision-badge');
    return {
      markers: !!document.getElementById('sim-collision-markers'),
      dist: !!dist,
      badge: !!badge,
      // Altlauf/kein Befund: Abstandszahl + Badge anfangs versteckt (US 25).
      distHidden: dist ? dist.hidden : null,
      badgeHidden: badge ? badge.hidden : null,
      // Die beiden neuen ⚙-Sicht-Schalter (Druckstand, Abstandszahl) existieren.
      druckstandToggle: !!document.getElementById('vs-druckstand'),
      abstandToggle: !!document.getElementById('vs-abstandszahl'),
    };
  })()`);
  check(
    "Player trägt Kollisions-Marker-Leiste, Abstandszahl und Befund-Badge (anfangs versteckt ohne Befund)",
    coll.markers && coll.dist && coll.badge && coll.distHidden === true && coll.badgeHidden === true,
    JSON.stringify(coll),
  );
  check(
    "Menue fuehrt die Sicht-Schalter Wachsender Druckstand + Live-Abstandszahl (#128)",
    coll.druckstandToggle && coll.abstandToggle,
    JSON.stringify({ druckstand: coll.druckstandToggle, abstand: coll.abstandToggle }),
  );
  await shot(cdp, "smoke-kollision-player.png");

  // Kollisionsbefund ist Lauf-Eigenschaft (Issue #156): die Leiste trägt einen
  // eigenen aufklappbaren Befundblock (<dl> Zahlen + <ul> Vorbehalte), den der
  // Badge OHNE Reiterwechsel öffnet. Reiner DOM-Vertrag; anfangs zugeklappt.
  // Ist ein Badge sichtbar (Befund aus einem laufenden Replay), togglet ein
  // Badge-Klick den Block auf/zu, ohne den aktiven Reiter zu wechseln (#147/#157).
  const findingBlock = await evalJs(cdp, `(() => {
    const panel = document.getElementById('sim-collision-panel');
    const badge = document.getElementById('sim-collision-badge');
    const tabBefore = [...document.querySelectorAll('.tab-panel')].find((p) => !p.hidden)?.dataset.panel ?? null;
    let toggled = null, tabAfter = tabBefore;
    if (badge && badge.hidden === false) {
      badge.click();
      const openedHidden = panel.hidden;
      badge.click();
      const closedHidden = panel.hidden;
      toggled = openedHidden === false && closedHidden === true;
      tabAfter = [...document.querySelectorAll('.tab-panel')].find((p) => !p.hidden)?.dataset.panel ?? null;
    }
    return {
      panelPresent: !!panel,
      metaPresent: !!document.getElementById('sim-collision-panel-meta'),
      warnPresent: !!document.getElementById('sim-collision-panel-warnings'),
      panelHiddenInitially: panel ? panel.hidden : null,
      ariaControls: badge?.getAttribute('aria-controls') ?? null,
      badgeVisible: badge ? badge.hidden === false : false,
      toggled,
      tabUnchanged: tabBefore === tabAfter,
    };
  })()`);
  check(
    "Leisten-Befundblock (#156): <dl>+<ul> vorhanden, anfangs zugeklappt, Badge ist sein Anker",
    findingBlock.panelPresent && findingBlock.metaPresent && findingBlock.warnPresent &&
      findingBlock.panelHiddenInitially === true &&
      findingBlock.ariaControls === "sim-collision-panel",
    JSON.stringify(findingBlock),
  );
  check(
    "Badge-Klick klappt den Befundblock auf/zu OHNE Reiterwechsel (#147/#157) — oder kein Badge (Altlauf)",
    findingBlock.badgeVisible ? findingBlock.toggled === true && findingBlock.tabUnchanged : true,
    JSON.stringify(findingBlock),
  );

  console.log("2n) Replay-Bühne: vier Schalter, ein ⚙-Menü mit zwei Sektionen (Issue #159)");
  // Die vier Replay-Schalter (show-arm, grow-strand, druckstand, abstandszahl) leben
  // in der ⚙-Sektion „Replay-Bühne"; context/basis/bemassung in „Modellansicht".
  // Im Reiter Slicing (Fokus) sind beide Sektionen sichtbar und die aus dem Panel
  // gewanderten Schalter (show-arm/grow-strand) erstmals bedienbar. Reiner
  // DOM-Vertrag; das ⚙-Menü ist noch zugeklappt — Sektions-Sichtbarkeit prüft
  // `.hidden` der Sektion, nicht des (kollabierten) Menü-Körpers.
  const vs = await evalJs(cdp, `(() => {
    const root = document.getElementById('viewer-settings');
    const sec = (k) => document.querySelector('.vs-section[data-section="' + k + '"]');
    const model = sec('model-view');
    const replay = sec('replay-stage');
    return {
      // Beide benannten Sektionen existieren, je mit Überschrift.
      modelPresent: !!model, replayPresent: !!replay,
      modelTitle: model?.querySelector('.vs-section-title')?.textContent ?? null,
      replayTitle: replay?.querySelector('.vs-section-title')?.textContent ?? null,
      // Alle vier Replay-Schalter hängen in der Replay-Bühnen-Sektion.
      replayToggles: replay ? ['show-arm','grow-strand','druckstand','abstandszahl']
        .every((k) => replay.querySelector('#vs-' + k)) : false,
      // Modellansicht führt context/basis/bemassung + den Einpassen-Knopf.
      modelToggles: model ? ['context','basis','bemassung']
        .every((k) => model.querySelector('#vs-' + k)) : false,
      fitInModel: !!model?.querySelector('#vs-fit-wall'),
      // Im Reiter Slicing (Fokus): Menü sichtbar, beide Sektionen sichtbar (.hidden=false).
      rootHidden: root ? root.hidden : null,
      modelHidden: model ? model.hidden : null,
      replayHidden: replay ? replay.hidden : null,
      // Die alten Panel-Checkboxen sind ersatzlos verschwunden (Issue #159).
      oldArm: !!document.querySelector('#panel #show-arm'),
      oldStrand: !!document.querySelector('#panel #grow-strand'),
    };
  })()`);
  check(
    "⚙ trägt zwei benannte Sektionen; „Replay-Bühne\" führt alle vier Schalter, „Modellansicht\" context/basis/bemassung + Einpassen",
    vs.modelPresent && vs.replayPresent && vs.replayToggles && vs.modelToggles && vs.fitInModel &&
      vs.modelTitle === "Modellansicht" && vs.replayTitle === "Replay-Bühne",
    JSON.stringify(vs),
  );
  check(
    "Reiter Slicing (Fokus): ⚙ sichtbar, beide Sektionen sichtbar (nur `.hidden`)",
    vs.rootHidden === false && vs.modelHidden === false && vs.replayHidden === false,
    JSON.stringify(vs),
  );
  check(
    "Die Panel-Häkchen show-arm/grow-strand sind ersatzlos gefallen (#159)",
    vs.oldArm === false && vs.oldStrand === false,
    JSON.stringify(vs),
  );
  // Wirkung sofort: show-arm im ⚙ umlegen blendet den Replay-Arm live um.
  const armToggle = await evalJs(cdp, `(() => {
    const cb = document.getElementById('vs-show-arm');
    const dbg = () => (window.__moduleSimDebug ? window.__moduleSimDebug() : null);
    if (!cb) return { ok: false, reason: 'kein vs-show-arm' };
    const before = dbg();
    cb.checked = !cb.checked; cb.dispatchEvent(new Event('change'));
    const after = dbg();
    cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); // Ausgangszustand zurück
    return { ok: true, hadModule: !!(before && before.active), before, after };
  })()`);
  check(
    "Reiter Slicing: show-arm im ⚙ ist bedienbar (Umlegen feuert ohne Fehler; Wirkung am aktiven Replay)",
    armToggle.ok,
    JSON.stringify(armToggle),
  );
  await shot(cdp, "smoke-replay-buehne.png");

  console.log("3) Bibliothek: eigene Szene, geteiltes Viewport aus (Issue #28/#30)");
  // Die Bibliothek ist kein Stepper-Schritt mehr (Issue #102) — sie wird über
  // das ▤-Icon im Header erreicht.
  await evalJs(cdp, `document.getElementById('header-library-btn').click()`);
  await sleep(900);
  const lib = await evalJs(cdp, SNAP);
  check(
    "Bibliothek: cfg-Canvas sichtbar, #viewport versteckt",
    !!lib.cfgCanvas && lib.cfgCanvas.w > 100 && lib.viewport.hidden === true,
    `cfg ${lib.cfgCanvas?.w}×${lib.cfgCanvas?.h}, viewport hidden=${lib.viewport?.hidden}`,
  );
  await shot(cdp, "smoke-bibliothek.png");

  console.log("4) Zurück zu Projekt: Canvas lebt weiter");
  await evalJs(cdp, `document.querySelector('#stepper [data-tab="projekt"]').click()`);
  await sleep(900);
  const back = await evalJs(cdp, SNAP);
  check("Projekt erneut: Canvas sichtbar", !!back.canvas && back.canvas.w > 100 && !back.viewport.hidden);

  console.log("5) Deeplink-Lauf mit Trajektorie: Deckelung (#32) + Stundenformat (#33)");
  // Absoluter Pfad eines Laufordners mit trajectory.json; Vite liefert Pfade
  // ausserhalb des Projekts ueber /@fs/ aus. Maschinenabhaengig, daher per
  // Umgebungsvariable FGC_SMOKE_RUN zu setzen (siehe Kopfkommentar).
  if (!process.env.FGC_SMOKE_RUN) {
    throw new Error(
      "FGC_SMOKE_RUN nicht gesetzt: absoluten Pfad eines Laufordners mit " +
        "trajectory.json angeben, z. B. " +
        "FGC_SMOKE_RUN=C:/.../runs/20260704-192635_slice_Building-Architecture",
    );
  }
  const runUrl = `/@fs/${process.env.FGC_SMOKE_RUN.replace(/\\/g, "/")}`;
  await cdp.send("Page.navigate", { url: `http://localhost:5173/?run=${runUrl}` });
  await sleep(4000);
  const traj = await evalJs(cdp, `(() => ({
    nWarnings: document.querySelectorAll('#traj-warnings li').length,
    meta: document.getElementById('traj-meta')?.textContent ?? '',
  }))()`);
  check(
    "Warnungsliste gedeckelt (Kopf + max. 20 + Rest-Zeile)",
    traj.nWarnings > 0 && traj.nWarnings <= 22,
    `${traj.nWarnings} <li>`,
  );
  check("Dauer im Stundenformat", traj.meta.includes(" h"), traj.meta.slice(0, 60));
  await shot(cdp, "smoke-deeplink.png");

  console.log(failures.length === 0 ? "\nSmoke-Test bestanden." : `\n${failures.length} Prüfungen FEHLGESCHLAGEN:`);
  for (const f of failures) console.log(`  - ${f}`);
  process.exit(failures.length === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});

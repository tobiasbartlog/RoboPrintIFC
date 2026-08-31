/**
 * Tab-Shell + Projektliste (ADR-016): der Rahmen des interaktiven Viewers.
 *
 * - Beim Start (kein ?run=) die **Projektliste** mit „Neues Projekt aus IFC…".
 * - Nach dem Öffnen eines Projekts die **Tab-Shell** mit den fünf Reitern
 *   (Projekt, Roboter, Druckplan, Simulation, Export) plus **Bibliothek**;
 *   die hinteren vier und die Bibliothek zunächst als Platzhalter.
 * - Reiter sind Navigation, kein Zwangspfad (ui/tabs.ts): jeder Klick wechselt
 *   frei, kein Gating.
 *
 * Der Reiter Projekt beherbergt die bestehende Modellübersicht (Panel +
 * Viewport); die Shell rührt deren Fachzustand nicht an — sie schaltet nur
 * Sichtbarkeit. Der Fachzustand liegt im project.json auf der Platte (ADR-016).
 */

import type { ProjectSummary } from "../api/projects";
import { allStageStatuses, type OutputName, type Revisions, type StageStatus } from "./staleness";
import { PROCESS_STEPS, stepperView } from "./stepper-state";
import { TAB_IDS, type TabId } from "./tabs";
import {
  formatRelativeGerman,
  wallBalanceSegments,
  type WallBalance,
} from "./wall-balance";

export interface ShellCallbacks {
  /** Projekt aus der Liste öffnen (Slug). */
  onOpenProject(slug: string): void;
  /** Neues Projekt aus IFC anlegen. */
  onCreateProject(name: string, modelPath: string): void;
  /**
   * Nach jedem Reiterwechsel (Issue #30/#31): main.ts schaltet damit den
   * Szenenmodus des geteilten Hauptsichtfelds (Modellübersicht vs.
   * Roboter-Vorschau). Rein darstellend — kein Fachzustand.
   */
  onTabChanged?(id: TabId): void;
  /**
   * Klick auf Logo/Projektname im Header (Issue #102): zurück zur Projektliste.
   * Rein Navigation (kein Zwangspfad) — main.ts lädt die Liste neu.
   */
  onBackToProjectList?(): void;
  /**
   * Klick auf den Theme-Toggle ◐ im Header (Issue #102): bedient den
   * Umschalter aus Scheibe 1 (ui/theme.ts über main.ts) — kein zweiter
   * Mechanismus.
   */
  onToggleTheme?(): void;
}

export class Shell {
  private readonly projectListScreen = byId<HTMLElement>("project-list");
  private readonly shellRoot = byId<HTMLElement>("shell");
  private readonly plProjects = byId<HTMLUListElement>("pl-projects");
  private readonly plEmpty = byId<HTMLElement>("pl-empty");
  // API-Status (Issue #104): ein Punkt + Label, deckt verbunden ↔ nicht erreichbar
  // (fgc-start-Hinweis wandert ins title) ab — ersetzt die frühere #pl-api-warning.
  private readonly plApiStatus = byId<HTMLElement>("pl-api-status");
  private readonly plApiDot = byId<HTMLElement>("pl-api-dot");
  private readonly plApiLabel = byId<HTMLElement>("pl-api-label");
  // Dropzone + verstecktes Datei-Input: Anlage per Drag&Drop oder Datei-Dialog.
  private readonly plDropzone = byId<HTMLElement>("pl-dropzone");
  private readonly plFile = byId<HTMLInputElement>("pl-file");
  // Deferred Namensabfrage (erst nach Dateiwahl sichtbar).
  private readonly plForm = byId<HTMLFormElement>("pl-new");
  private readonly plChosenFile = byId<HTMLElement>("pl-chosen-file");
  private readonly plName = byId<HTMLInputElement>("pl-name");
  private readonly plModel = byId<HTMLInputElement>("pl-model");
  private readonly plCreate = byId<HTMLButtonElement>("pl-create");
  private readonly plCancel = byId<HTMLButtonElement>("pl-cancel");
  private readonly plStatus = byId<HTMLElement>("pl-status");
  // Header (Issue #102): Logo/Projektname, Druckjob-Chip, Stepper, Theme-Toggle,
  // Bibliothek-Icon — verschmilzt die frühere Tabbar + Active-Job-Bar.
  private readonly headerBrand = byId<HTMLElement>("header-brand");
  private readonly headerProjectName = byId<HTMLElement>("header-project-name");
  // Aktiver Druckjob: dauerhaft sichtbar über alle Reiter (Issue #19), jetzt Pill.
  private readonly jobChip = byId<HTMLElement>("header-job-chip");
  private readonly stepperNav = byId<HTMLElement>("stepper");
  private readonly themeToggle = byId<HTMLButtonElement>("header-theme-toggle");
  private readonly libraryBtn = byId<HTMLButtonElement>("header-library-btn");
  // Geteiltes Hauptsichtfeld (Issue #30): sichtbar in allen Prozess-Reitern,
  // ausgeblendet nur in der Bibliothek (die hat ihre eigene Szene, #28).
  private readonly sharedViewport = byId<HTMLElement>("viewport");

  private _apiAvailable = false;
  private _activeTab: TabId = "projekt";
  // Aktuelle Staleness-Zustände je Output-Stufe (Issue #102): speisen die
  // Stepper-Status-Punkte. Kommen AUSSCHLIESSLICH aus ui/staleness.ts.
  private _stepStatuses: Partial<Record<OutputName, StageStatus>> = {};

  constructor(private readonly callbacks: ShellCallbacks) {
    // Header-Navigation (Issue #102): frei, kein Zwangspfad.
    this.headerBrand.addEventListener("click", () => this.callbacks.onBackToProjectList?.());
    this.libraryBtn.addEventListener("click", () => this.setActiveTab("bibliothek"));
    this.themeToggle.addEventListener("click", () => this.callbacks.onToggleTheme?.());
    this.renderStepper();

    this.plForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = this.plName.value.trim();
      const model = this.plModel.value.trim();
      if (!name || !model) {
        this.setStatus("Name und IFC-Pfad angeben.");
        return;
      }
      callbacks.onCreateProject(name, model);
    });
    // Abbrechen räumt die Dateiwahl wieder ab (zurück zur reinen Dropzone).
    this.plCancel.addEventListener("click", () => this.resetNewProject());

    // Dropzone (Issue #104): Klick öffnet den Datei-Dialog, Drag&Drop legt ab.
    this.plDropzone.addEventListener("click", () => {
      if (!this._apiAvailable) return;
      this.plFile.click();
    });
    this.plDropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (this._apiAvailable) this.plFile.click();
      }
    });
    this.plDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (this._apiAvailable) this.plDropzone.classList.add("dragover");
    });
    this.plDropzone.addEventListener("dragleave", () => this.plDropzone.classList.remove("dragover"));
    this.plDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      this.plDropzone.classList.remove("dragover");
      if (!this._apiAvailable) return;
      const file = e.dataTransfer?.files?.[0];
      if (file) this.onFileChosen(file);
    });
    this.plFile.addEventListener("change", () => {
      const file = this.plFile.files?.[0];
      if (file) this.onFileChosen(file);
    });

    // Delegierter Klick auf einen Projektlisten-Eintrag.
    this.plProjects.addEventListener("click", (e) => {
      const li = (e.target as HTMLElement).closest<HTMLElement>("li[data-slug]");
      if (li?.dataset.slug) callbacks.onOpenProject(li.dataset.slug);
    });
  }

  /**
   * Eine IFC-Datei wurde gewählt (Dialog) oder abgelegt (Drag&Drop): erst JETZT
   * die Namensabfrage einblenden (Issue #104). Der Core braucht den absoluten
   * Disk-Pfad (ADR-016); Browser geben ihn nicht preis — wo er vorliegt
   * (`file.path`, z. B. Electron), wird er vorbefüllt, sonst der Dateiname als
   * editierbarer Ausgangswert. Der Anlage-Flow selbst bleibt unverändert.
   */
  private onFileChosen(file: File): void {
    const path = (file as unknown as { path?: string }).path ?? "";
    this.plModel.value = path || file.name;
    this.plChosenFile.textContent = `Gewählt: ${file.name}`;
    this.plForm.hidden = false;
    this.plName.focus();
  }

  /** Räumt die Dateiwahl + Namensabfrage ab (Ausgangszustand der Dropzone). */
  private resetNewProject(): void {
    this.plForm.hidden = true;
    this.plName.value = "";
    this.plModel.value = "";
    this.plChosenFile.textContent = "";
    this.plFile.value = "";
  }

  /** Zeigt die Projektliste (Startzustand) und versteckt die Tab-Shell. */
  showProjectList(projects: ProjectSummary[]): void {
    this.projectListScreen.hidden = false;
    this.shellRoot.hidden = true;
    this.resetNewProject();
    this.setStatus("");
    this.renderProjects(projects);
  }

  /** Wechselt in die Tab-Shell (Projekt geöffnet oder ?run=) und aktiviert einen Reiter. */
  showShell(active: TabId = "projekt"): void {
    this.projectListScreen.hidden = true;
    this.shellRoot.hidden = false;
    this.setActiveTab(active);
  }

  /** Aktiviert einen Reiter; blendet die übrigen Panel-Sektionen aus. */
  setActiveTab(id: TabId): void {
    for (const tab of TAB_IDS) {
      const panel = document.querySelector<HTMLElement>(`.tab-panel[data-panel="${tab}"]`);
      if (panel) panel.hidden = tab !== id;
    }
    // Geteiltes Hauptsichtfeld: nur die Bibliothek bringt ihre eigene Szene mit.
    this.sharedViewport.hidden = id === "bibliothek";
    // Bibliothek-Icon markieren, wenn die Bibliothek aktiv ist (Issue #102).
    this.libraryBtn.classList.toggle("active", id === "bibliothek");
    this._activeTab = id;
    // Stepper-Chip des aktiven Prozess-Reiters hervorheben (bei Bibliothek: keiner).
    this.renderStepper();
    this.callbacks.onTabChanged?.(id);
  }

  /**
   * Baut den Header-Stepper aus der reinen Ableitung (ui/stepper-state.ts) neu
   * auf: Akzent-Chip für den aktiven Reiter, sonst nur Text; je Schritt ein
   * 7px-Status-Punkt (Farbe aus der Staleness-Ableitung) und „›"-Trenner.
   */
  private renderStepper(): void {
    const views = stepperView(PROCESS_STEPS, this._stepStatuses, this._activeTab);
    this.stepperNav.replaceChildren();
    for (const v of views) {
      if (v.notFirst) {
        const sep = document.createElement("span");
        sep.className = "stepper-sep";
        sep.textContent = "›";
        sep.setAttribute("aria-hidden", "true");
        this.stepperNav.append(sep);
      }
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = v.isActive ? "step step-active" : "step";
      chip.dataset.tab = v.tab;
      chip.title = v.tooltip;
      if (v.isActive) chip.setAttribute("aria-current", "step");
      const dot = document.createElement("span");
      dot.className = `dot ${v.dotClass}`;
      const label = document.createElement("span");
      label.textContent = v.label;
      chip.append(dot, label);
      chip.addEventListener("click", () => this.setActiveTab(v.tab));
      this.stepperNav.append(chip);
    }
  }

  /**
   * Frischt die Stepper-Status-Punkte aus den Revisionsständen des Druckjobs
   * auf (Issue #102). Die Ableitung ist die bestehende `allStageStatuses`
   * (ui/staleness.ts) — hier wird nichts neu gerechnet.
   */
  setStepperRevisions(revisions: Revisions | undefined): void {
    this._stepStatuses = allStageStatuses(revisions);
    this.renderStepper();
  }

  /** Setzt den Projektnamen in der Logo-Zeile des Headers (Issue #102). */
  setProjectName(name: string): void {
    this.headerProjectName.textContent = name;
  }

  /**
   * Spiegelt den Theme-Zustand auf den ◐-Toggle (Issue #102): Tooltip nennt das
   * Ziel des nächsten Klicks, `aria-pressed` markiert das helle Theme. Die
   * Umschalt-/Persistenz-Logik bleibt in ui/theme.ts (Scheibe 1).
   */
  setThemeToggle(isLight: boolean, title: string): void {
    this.themeToggle.setAttribute("aria-pressed", isLight ? "true" : "false");
    this.themeToggle.title = title;
  }

  /** Der aktuell aktive Reiter — für Interaktions-Guards (Picking/Drag, Issue #30). */
  get activeTab(): TabId {
    return this._activeTab;
  }

  /**
   * Zeigt den aktiven Druckjob in der persistenten Statusleiste über alle Reiter.
   * Wird nach erfolgreicher Übernahme oder beim Öffnen eines Projekts mit
   * vorhandenem Druckjob aufgerufen (Issue #19).
   */
  updateActivePrintJob(globalId: string, wallName: string | null): void {
    const label = wallName ? `${wallName} (${globalId})` : globalId;
    this.jobChip.hidden = false;
    this.jobChip.textContent = label;
    this.jobChip.title = `Aktiver Druckjob: ${label}`;
  }

  /** Blendet den Druckjob-Chip aus (kein aktiver Job). */
  clearActivePrintJob(): void {
    this.jobChip.hidden = true;
    this.jobChip.textContent = "";
    this.jobChip.title = "";
  }

  private renderProjects(projects: ProjectSummary[]): void {
    this.plProjects.replaceChildren();
    this.plEmpty.hidden = projects.length > 0;
    for (const p of projects) {
      const li = document.createElement("li");
      li.dataset.slug = p.slug;
      li.className = "pl-card";

      const head = document.createElement("div");
      head.className = "pl-card-head";
      const name = document.createElement("span");
      name.className = "pl-card-name";
      name.textContent = p.name;
      const time = document.createElement("span");
      time.className = "pl-card-time";
      // Der Zeitstempel wird von updateProjectBalance nachgereicht (Übersichts-Lauf).
      time.dataset.role = "time";
      head.append(name, time);

      const file = document.createElement("div");
      file.className = "pl-card-file";
      file.textContent = modelName(p.model_path);

      // Platzhalter für den Bilanz-Balken (wird per updateProjectBalance gefüllt).
      const balanceSlot = document.createElement("div");
      balanceSlot.dataset.role = "balance";

      const legend = document.createElement("div");
      legend.className = "pl-card-legend";
      const open = document.createElement("span");
      open.className = "pl-card-open";
      open.textContent = "Öffnen ›";
      legend.append(open);

      li.append(head, file, balanceSlot, legend);
      this.plProjects.append(li);
    }
  }

  /**
   * Reicht die Wand-Bilanz eines Projekts nach (Issue #104): main.ts lädt die
   * candidates.json des Übersichts-Laufs asynchron und meldet die Zählung hier.
   * `balance === null` (kein Übersichts-Lauf/keine Wände) degradiert sauber —
   * keinen Balken einsetzen (kein kaputter 0-%-Balken). Die Karten rendern
   * sofort (ohne Balken), damit die Liste nicht auf die Nachladung wartet.
   */
  updateProjectBalance(slug: string, balance: WallBalance | null, createdMs: number | null): void {
    const li = this.plProjects.querySelector<HTMLElement>(`li[data-slug="${CSS.escape(slug)}"]`);
    if (!li) return;

    if (createdMs !== null && Number.isFinite(createdMs)) {
      const time = li.querySelector<HTMLElement>('[data-role="time"]');
      if (time) time.textContent = formatRelativeGerman(createdMs, Date.now());
    }

    const slot = li.querySelector<HTMLElement>('[data-role="balance"]');
    const legend = li.querySelector<HTMLElement>(".pl-card-legend");
    if (!slot || !legend) return;

    const segments = balance ? wallBalanceSegments(balance) : null;
    slot.replaceChildren();
    if (!balance || !segments) return; // sauber degradieren: kein Balken

    const bar = document.createElement("div");
    bar.className = "pl-bar";
    for (const [key, cls] of [
      ["druckbar", "ok"],
      ["vorlaeufig", "warn"],
      ["ungeeignet", "err"],
    ] as const) {
      const pct = segments[key];
      if (pct <= 0) continue;
      const seg = document.createElement("span");
      seg.className = `seg ${cls}`;
      seg.style.width = `${pct}%`;
      bar.append(seg);
    }
    slot.append(bar);

    // Legende: farbige Zähler je nicht-leerer Kategorie, „Öffnen ›" bleibt rechts.
    const open = legend.querySelector(".pl-card-open");
    legend.replaceChildren();
    for (const [key, cls, label] of [
      ["druckbar", "ok", "druckbar"],
      ["vorlaeufig", "warn", "vorläufig"],
      ["ungeeignet", "err", "ungeeignet"],
    ] as const) {
      const n = balance[key];
      if (n <= 0) continue;
      const item = document.createElement("span");
      const count = document.createElement("span");
      count.className = `count ${cls}`;
      count.textContent = String(n);
      item.append(count, document.createTextNode(` ${label}`));
      legend.append(item);
    }
    if (open) legend.append(open);
  }

  /**
   * Setzt den API-Verfügbarkeitszustand (Issue #104): ohne API sind
   * Projekt-Operationen gesperrt und der Status-Punkt wird amber (fgc-start-
   * Hinweis im title); verbunden = grüner Punkt.
   */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.plApiDot.classList.toggle("ok", available);
    this.plApiDot.classList.toggle("warn", !available);
    this.plApiLabel.textContent = available ? "Core-API verbunden" : "Core-API nicht erreichbar";
    this.plApiStatus.title = available
      ? ""
      : "Core-API nicht erreichbar — mit `fgc start` hochfahren.";
    this.plDropzone.classList.toggle("disabled", !available);
    this.plDropzone.setAttribute("aria-disabled", available ? "false" : "true");
    this.plCreate.disabled = !available;
    this.plName.disabled = !available;
    this.plModel.disabled = !available;
    if (!available) this.resetNewProject();
  }

  get apiAvailable(): boolean {
    return this._apiAvailable;
  }

  setStatus(text: string): void {
    this.plStatus.textContent = text;
  }

  setCreateBusy(busy: boolean): void {
    this.plCreate.disabled = busy || !this._apiAvailable;
    this.plCreate.textContent = busy ? "Lege an …" : "Projekt anlegen";
  }
}

function modelName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || path || "—";
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

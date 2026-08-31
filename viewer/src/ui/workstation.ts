/**
 * Workstation-Panel im Reiter Roboter (Issue #77, PRD #69): Katalog-Dropdown +
 * Kenndaten + Kompatibilitäts-Ausgrauen/-Warnung + Speichern.
 *
 * Mirror von `ToolPanel` (`ui/tool.ts`) für die Aufstell-Umgebung: zeigt alle
 * Workstation-Definitionen (GET /workstations) in einem Dropdown, darunter Kenndaten
 * (Mobilität, Höhenmodell, Sicherheitsabstand) und — bei bereits gewählter, durch
 * einen Roboterwechsel inkompatibel gewordener Workstation — eine Warnung.
 * „Speichern" persistiert die Wahl im Druckjob (PUT /projects/{slug}/workstation).
 *
 * Befund, kein Gate (ADR-013): inkompatible Workstations werden ausgegraut (aber
 * bleiben wählbar) und warnen — nichts wird gesperrt oder zurückgesetzt. Anders als
 * beim Roboter/Endeffektor veraltet eine Workstation-Änderung KEINE Outputs (Seam zu
 * #70) — der Panel ruft daher kein `refreshRevisions`.
 */

import type { WorkstationDef } from "../api/projects";
import {
  incompatibleWorkstationNames,
  workstationCompatibilityWarning,
} from "./workstation-state";

export interface WorkstationPanelCallbacks {
  /** Nutzer hat „Speichern" geklickt. Persistiert die Wahl (PUT .../workstation). */
  onSaveWorkstation(name: string): Promise<{ compatible: boolean | null }>;
}

export class WorkstationPanel {
  // Eigene id-Prefix `wsc-` (workstation choice) — trennt das Reiter-Roboter-Panel
  // sauber von der Workstation-BIBLIOTHEK (`ws-*` in der Bibliothek, sonst id-Kollision).
  private readonly select = byId<HTMLSelectElement>("wsc-select");
  private readonly info = byId<HTMLDListElement>("wsc-info");
  private readonly saveBtn = byId<HTMLButtonElement>("wsc-save-btn");
  private readonly status = byId<HTMLParagraphElement>("wsc-status");
  private readonly apiWarning = byId<HTMLElement>("wsc-api-warning");
  private readonly savedFor = byId<HTMLElement>("wsc-saved-for");
  private readonly compatWarning = byId<HTMLElement>("wsc-compat-warning");

  private _workstations: WorkstationDef[] = [];
  private _busy = false;
  private _apiAvailable = false;
  private _projectOpen = false;
  /** Name des aktiven Roboters für den Kompatibilitäts-Filter (null = unbekannt). */
  private _activeRobot: string | null = null;

  constructor(callbacks: WorkstationPanelCallbacks) {
    this.select.addEventListener("change", () => {
      this._updateInfo();
      this._updateCompatWarning();
    });

    this.saveBtn.addEventListener("click", async () => {
      const selected = this.select.value;
      if (!selected || this._busy) return;
      this._busy = true;
      this._syncButtons();
      this.saveBtn.textContent = "Speichert …";
      this.status.textContent = "Workstation wird gespeichert …";
      try {
        await callbacks.onSaveWorkstation(selected);
        this.status.textContent = "Workstation gespeichert.";
        this.savedFor.hidden = false;
        this.savedFor.textContent = `Gespeichert: ${selected}`;
        this._updateCompatWarning();
      } catch (err) {
        this.status.textContent = `Fehler: ${err}`;
      } finally {
        this._busy = false;
        this.saveBtn.textContent = "Speichern";
        this._syncButtons();
      }
    });
  }

  /** Befüllt das Dropdown mit den verfügbaren Workstation-Definitionen. */
  setWorkstations(workstations: WorkstationDef[]): void {
    this._workstations = workstations;
    this.select.replaceChildren();
    for (const w of workstations) {
      const opt = document.createElement("option");
      opt.value = w.name;
      opt.textContent = w.name;
      this.select.append(opt);
    }
    this._updateGreying();
    this._updateInfo();
    this._updateCompatWarning();
    this._syncButtons();
  }

  /**
   * Setzt den aktiven Roboter für den Kompatibilitäts-Filter (Issue #77, #74-Muster).
   * Ein Roboterwechsel graut inkompatible Workstations aus (bleiben wählbar, kein
   * `disabled`) und warnt, falls die bestehende Wahl fremd wird (kein Auto-Reset,
   * kein Gate — ADR-013).
   */
  setActiveRobot(robot: string | null): void {
    this._activeRobot = robot;
    this._updateGreying();
    this._updateCompatWarning();
  }

  /**
   * Setzt die angezeigte Workstation-Wahl und den „gespeichert für"-Hinweis.
   * Wird nach dem Öffnen eines Projekts und nach dem Speichern aufgerufen
   * (Wiederherstellung nach Neuladen).
   */
  setCurrentWorkstation(name: string | null): void {
    // Workstation-Namen sind datei-sicher ([a-z0-9_], safe_workstation_name) — ein
    // direkter Options-Abgleich genügt (kein CSS.escape/Selektor nötig).
    if (name && Array.from(this.select.options).some((o) => o.value === name)) {
      this.select.value = name;
      this._updateInfo();
      this._updateCompatWarning();
    }
    if (name) {
      this.savedFor.hidden = false;
      this.savedFor.textContent = `Aktuell: ${name}`;
    } else {
      this.savedFor.hidden = true;
    }
  }

  /** Setzt API-Verfügbarkeit: ohne API ist das Dropdown gesperrt. */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this.select.disabled = !available;
    this._syncButtons();
  }

  /** Setzt, ob ein Projekt geöffnet ist — ohne Projekt kein Speichern. */
  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._syncButtons();
  }

  setStatus(text: string): void {
    this.status.textContent = text;
  }

  private _syncButtons(): void {
    this.saveBtn.disabled =
      !this._apiAvailable || !this._projectOpen || !this.select.value || this._busy;
  }

  private _updateInfo(): void {
    const name = this.select.value;
    const ws = this._workstations.find((w) => w.name === name);
    this.info.replaceChildren();
    if (!ws) return;

    const mobility = ws.mobility === "mobile" ? "mobil" : "stationär";
    const height = ws.height_adjustable
      ? ws.height_range_mm
        ? `verstellbar ${ws.height_range_mm.min}–${ws.height_range_mm.max} mm`
        : "verstellbar"
      : `Podesthöhen [${ws.base_heights_mm.join(", ")}] mm`;
    const rows: [string, string][] = [
      ["Mobilität", mobility],
      ["Höhe", height],
      ["Sicherheitsabstand", `${ws.safety_min_distance_mm} mm`],
      ["Hersteller", ws.vendor || "—"],
    ];
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      this.info.append(dt, dd);
    }
  }

  /**
   * Graut inkompatible Workstation-Optionen aus (Issue #77) — via CSS-Klasse,
   * NICHT `disabled`: inkompatible Workstations bleiben wählbar (kein Gate). Die
   * Entscheidung kommt aus dem reinen `incompatibleWorkstationNames` (reuse
   * `isCompatible` aus compat.ts).
   */
  private _updateGreying(): void {
    const grey = incompatibleWorkstationNames(this._workstations, this._activeRobot);
    for (const opt of Array.from(this.select.options)) {
      opt.classList.toggle("option-incompatible", grey.has(opt.value));
    }
  }

  /**
   * Zeigt die Kompatibilitäts-Warnung, wenn die aktuell gewählte Workstation zum
   * aktiven Roboter inkompatibel ist (Issue #77). Kein Auto-Reset, keine Persistenz
   * — nur der Hinweis (analog Endeffektor-Warnung).
   */
  private _updateCompatWarning(): void {
    const name = this.select.value;
    const ws = this._workstations.find((w) => w.name === name) ?? null;
    const msg = workstationCompatibilityWarning(ws, this._activeRobot);
    if (msg === null) {
      this.compatWarning.hidden = true;
      this.compatWarning.textContent = "";
    } else {
      this.compatWarning.hidden = false;
      this.compatWarning.textContent = msg;
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

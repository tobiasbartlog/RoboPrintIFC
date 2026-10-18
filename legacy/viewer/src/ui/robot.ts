/**
 * Reiter Roboter (Issue #20): Roboterkatalog-Dropdown + Kenndaten + Neubewertung.
 *
 * Zeigt alle verfügbaren Roboterdefinitionen (GET /robots) in einem Dropdown;
 * darunter die Kenndaten (Reichweite, Arbeitsraum) der gewählten Definition.
 * „Neu bewerten" stößt eine Neubewertung aller Wände für den gewählten Roboter an
 * (PUT /projects/{slug}/robot) — die Modellübersicht im Reiter Projekt färbt danach
 * neu ein (Kandidaten der neuen Wahl). Roboterwahl wird im Druckjob persistiert
 * (kein Setup — ADR-006).
 *
 * v1-Beschränkung: nur Doosan M1013 (kein KUKA-Solver portiert, ADR-002/§9.2).
 */

import type { RobotDef } from "../api/projects";

export interface RobotPanelCallbacks {
  /**
   * Nutzer hat „Neu bewerten" geklickt. Der Panel-eigene Busy-Zustand wird
   * erst nach dem await geräumt; Fehler werden per `setStatus` angezeigt.
   */
  onReassess(robotName: string): Promise<void>;
  /**
   * Nutzer hat den Umschalter „Schema-Darstellung" bedient (Issue #41).
   * `schema = true` → Kapsel-Schema, `false` → echte M1013-Meshes. Wirkt global
   * auf alle ArmView-Instanzen (Vorschau + Replay).
   */
  onArmSchemaToggled(schema: boolean): void;
}

export class RobotPanel {
  private readonly robotSelect = byId<HTMLSelectElement>("robot-select");
  private readonly robotInfo = byId<HTMLDListElement>("robot-info");
  private readonly reassessBtn = byId<HTMLButtonElement>("robot-reassess-btn");
  private readonly robotStatus = byId<HTMLParagraphElement>("robot-status");
  private readonly robotApiWarning = byId<HTMLElement>("robot-api-warning");
  private readonly assessedFor = byId<HTMLElement>("robot-assessed-for");
  private readonly armSchemaToggle = byId<HTMLInputElement>("arm-schema-toggle");
  private readonly armRenderHint = byId<HTMLElement>("arm-render-hint");
  private readonly armAttribution = byId<HTMLElement>("arm-attribution");

  private _robots: RobotDef[] = [];
  private _busy = false;
  private _apiAvailable = false;
  private _projectOpen = false;

  constructor(callbacks: RobotPanelCallbacks) {
    this.robotSelect.addEventListener("change", () => {
      this._updateInfo();
    });

    this.armSchemaToggle.addEventListener("change", () => {
      callbacks.onArmSchemaToggled(this.armSchemaToggle.checked);
    });

    this.reassessBtn.addEventListener("click", async () => {
      const selected = this.robotSelect.value;
      if (!selected || this._busy) return;
      this._busy = true;
      this._syncButtons();
      this.reassessBtn.textContent = "↻ Bewertet …";
      this.robotStatus.textContent = "Eignungsprüfung läuft …";
      try {
        await callbacks.onReassess(selected);
        this.robotStatus.textContent = "Neubewertung abgeschlossen.";
      } catch (err) {
        this.robotStatus.textContent = `Fehler: ${err}`;
      } finally {
        this._busy = false;
        this.reassessBtn.textContent = "↻ Alle Wände neu bewerten";
        this._syncButtons();
      }
    });
  }

  /** Befüllt das Dropdown mit den verfügbaren Roboterdefinitionen. */
  setRobots(robots: RobotDef[]): void {
    this._robots = robots;
    this.robotSelect.replaceChildren();
    for (const r of robots) {
      const opt = document.createElement("option");
      opt.value = r.name;
      opt.textContent = r.name;
      this.robotSelect.append(opt);
    }
    this._updateInfo();
    this._syncButtons();
  }

  /**
   * Setzt die angezeigte Roboterwahl und den „zuletzt bewertet für"-Hinweis.
   * Wird nach dem Öffnen eines Projekts und nach einer Neubewertung aufgerufen.
   */
  setCurrentRobot(name: string | null): void {
    if (name && this.robotSelect.querySelector(`option[value="${CSS.escape(name)}"]`)) {
      this.robotSelect.value = name;
      this._updateInfo();
    }
    if (name) {
      this.assessedFor.hidden = false;
      this.assessedFor.textContent = `Zuletzt bewertet für: ${name}`;
    } else {
      this.assessedFor.hidden = true;
    }
  }

  /** Setzt API-Verfügbarkeit: ohne API ist das Dropdown gesperrt. */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.robotApiWarning.hidden = available;
    this.robotSelect.disabled = !available;
    this._syncButtons();
  }

  /** Setzt, ob ein Projekt geöffnet ist — ohne Projekt kein „Neu bewerten". */
  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._syncButtons();
  }

  setStatus(text: string): void {
    this.robotStatus.textContent = text;
  }

  /**
   * Spiegelt den globalen Arm-Render-Zustand in den Umschalter (Issue #41):
   * Checkbox = Schema, gesperrt solange Meshes nicht geladen sind oder der Load
   * fehlgeschlagen ist (dann steht sie auf Schema fest — Fallback).
   */
  setArmRenderState(opts: { schema: boolean; enabled: boolean; failed: boolean }): void {
    this.armSchemaToggle.checked = opts.schema;
    this.armSchemaToggle.disabled = !opts.enabled;
    if (opts.failed) {
      this.armRenderHint.textContent =
        "M1013-Meshes nicht ladbar — Kapsel-Schema (Fallback). Umschalten gesperrt.";
    } else if (!opts.enabled) {
      this.armRenderHint.textContent = "M1013-Meshes werden geladen …";
    } else {
      this.armRenderHint.textContent =
        "Vorschau und Replay zeigen die echten M1013-Glieder (Default). " +
        "Umschalten auf das schematische Kapsel-/Zylinder-Modell.";
    }
  }

  /** Setzt den BSD-3-Attributionshinweis der Meshes (aus dem Manifest, #40/#41). */
  setArmAttribution(text: string | null): void {
    if (text) {
      this.armAttribution.hidden = false;
      this.armAttribution.textContent = `Meshes: ${text}`;
      this.armAttribution.title = text;
    } else {
      this.armAttribution.hidden = true;
    }
  }

  private _syncButtons(): void {
    this.reassessBtn.disabled =
      !this._apiAvailable || !this._projectOpen || !this.robotSelect.value || this._busy;
  }

  private _updateInfo(): void {
    const name = this.robotSelect.value;
    const robot = this._robots.find((r) => r.name === name);
    this.robotInfo.replaceChildren();
    if (!robot) return;
    const rows: [string, string][] = [
      ["Reichweite", `${robot.reach_mm} mm`],
      ["Max. Druckhöhe", `${robot.max_print_height_mm} mm`],
      ["Max. Drucklänge", `${robot.max_print_length_mm} mm`],
      ["Arbeitsraum", robot.workspace_provisional ? "provisorisch" : "scharf"],
    ];
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      this.robotInfo.append(dt, dd);
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

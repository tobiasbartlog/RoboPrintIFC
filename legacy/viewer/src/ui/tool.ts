/**
 * Endeffektor-Panel im Reiter Roboter (Issue #21): Katalog-Dropdown + Kenndaten
 * + Payload-Warnung + Speichern.
 *
 * Zeigt alle verfügbaren Endeffektor-Definitionen (GET /tools) in einem Dropdown;
 * darunter Kenndaten (Gewicht, Kanäle, COG) der gewählten Definition sowie einen
 * Payload-Hinweis, falls der Roboter eine bekannte Traglast hat.
 * „Speichern" persistiert die Wahl im Druckjob (PUT /projects/{slug}/tool).
 * Payload-Überschreitung ist ein Befund, kein Gate — gespeichert wird in jedem Fall,
 * aber eine Warnung erscheint.
 */

import type { ToolDef } from "../api/projects";
import { compatibilityWarning, incompatibleToolNames } from "./compat";

export interface ToolPanelCallbacks {
  /**
   * Nutzer hat „Speichern" geklickt. Gibt payload_ok / payload_margin_kg zurück
   * (aus der API-Antwort); der Panel zeigt bei Bedarf die Warnung.
   */
  onSaveTool(toolName: string): Promise<{ payload_ok: boolean | null; payload_margin_kg: number | null }>;
  /**
   * Dropdown-Auswahl geändert (noch nicht gespeichert) — die Roboter-Vorschau
   * zeigt den gewählten Endeffektor live am Flansch (Issue #31/#49).
   */
  onSelectionChanged?(toolName: string): void;
}

export class ToolPanel {
  private readonly toolSelect = byId<HTMLSelectElement>("tool-select");
  private readonly toolInfo = byId<HTMLDListElement>("tool-info");
  private readonly saveBtn = byId<HTMLButtonElement>("tool-save-btn");
  private readonly toolStatus = byId<HTMLParagraphElement>("tool-status");
  private readonly toolApiWarning = byId<HTMLElement>("tool-api-warning");
  private readonly savedFor = byId<HTMLElement>("tool-saved-for");
  private readonly payloadWarning = byId<HTMLElement>("tool-payload-warning");
  private readonly compatWarning = byId<HTMLElement>("tool-compat-warning");

  private _tools: ToolDef[] = [];
  private _busy = false;
  private _apiAvailable = false;
  private _projectOpen = false;
  /** Traglast des aktuell gewählten Roboters (null = unbekannt). */
  private _robotPayloadKg: number | null = null;
  /** Name des aktiven Roboters für den Kompatibilitäts-Filter (Issue #74; null = unbekannt). */
  private _activeRobot: string | null = null;

  constructor(callbacks: ToolPanelCallbacks) {
    this.toolSelect.addEventListener("change", () => {
      this._updateInfo();
      this._updatePayloadWarning();
      this._updateCompatWarning();
      // Live-Vorschau (Issue #31/#49): der Wechsel ist sofort sichtbar,
      // persistiert wird weiterhin erst mit „Speichern".
      if (this.toolSelect.value) callbacks.onSelectionChanged?.(this.toolSelect.value);
    });

    this.saveBtn.addEventListener("click", async () => {
      const selected = this.toolSelect.value;
      if (!selected || this._busy) return;
      this._busy = true;
      this._syncButtons();
      this.saveBtn.textContent = "Speichert …";
      this.toolStatus.textContent = "Endeffektor wird gespeichert …";
      try {
        const result = await callbacks.onSaveTool(selected);
        this._showPayloadResult(result.payload_ok, result.payload_margin_kg);
        this.toolStatus.textContent = "Endeffektor gespeichert.";
        this.savedFor.hidden = false;
        this.savedFor.textContent = `Gespeichert: ${selected}`;
      } catch (err) {
        this.toolStatus.textContent = `Fehler: ${err}`;
      } finally {
        this._busy = false;
        this.saveBtn.textContent = "Speichern";
        this._syncButtons();
      }
    });
  }

  /** Befüllt das Dropdown mit den verfügbaren Endeffektor-Definitionen. */
  setTools(tools: ToolDef[]): void {
    this._tools = tools;
    this.toolSelect.replaceChildren();
    for (const t of tools) {
      const opt = document.createElement("option");
      opt.value = t.name;
      opt.textContent = t.name;
      this.toolSelect.append(opt);
    }
    this._updateGreying();
    this._updateInfo();
    this._updatePayloadWarning();
    this._updateCompatWarning();
    this._syncButtons();
  }

  /**
   * Setzt den aktiven Roboter für den Kompatibilitäts-Filter (Issue #74) — der
   * bestehende Roboter→ToolPanel-Leseweg (`setRobotPayload` wird parallel
   * gerufen). Ein Roboterwechsel graut inkompatibles Zubehör aus (bleibt
   * wählbar, kein `disabled`) und warnt, falls die bestehende Wahl fremd wird
   * (kein Auto-Reset, kein Gate — ADR-013).
   */
  setActiveRobot(robot: string | null): void {
    this._activeRobot = robot;
    this._updateGreying();
    this._updateCompatWarning();
  }

  /**
   * Setzt die angezeigte Werkzeugwahl und den „gespeichert für"-Hinweis.
   * Wird nach dem Öffnen eines Projekts und nach dem Speichern aufgerufen.
   */
  setCurrentTool(name: string | null): void {
    if (name && this.toolSelect.querySelector(`option[value="${CSS.escape(name)}"]`)) {
      this.toolSelect.value = name;
      this._updateInfo();
      this._updatePayloadWarning();
      this._updateCompatWarning();
    }
    if (name) {
      this.savedFor.hidden = false;
      this.savedFor.textContent = `Aktuell: ${name}`;
    } else {
      this.savedFor.hidden = true;
    }
  }

  /**
   * Setzt die Traglast des aktuell gewählten Roboters (für den Payload-Check).
   * null = unbekannt → kein Payload-Warning anzeigen.
   */
  setRobotPayload(payload_kg: number | null): void {
    this._robotPayloadKg = payload_kg;
    this._updatePayloadWarning();
  }

  /** Setzt API-Verfügbarkeit: ohne API ist das Dropdown gesperrt. */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.toolApiWarning.hidden = available;
    this.toolSelect.disabled = !available;
    this._syncButtons();
  }

  /** Setzt, ob ein Projekt geöffnet ist — ohne Projekt kein Speichern. */
  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._syncButtons();
  }

  setStatus(text: string): void {
    this.toolStatus.textContent = text;
  }

  private _syncButtons(): void {
    this.saveBtn.disabled =
      !this._apiAvailable || !this._projectOpen || !this.toolSelect.value || this._busy;
  }

  private _updateInfo(): void {
    const name = this.toolSelect.value;
    const tool = this._tools.find((t) => t.name === name);
    this.toolInfo.replaceChildren();
    if (!tool) return;

    const channels = Object.keys(tool.channels).join(", ");
    const rows: [string, string][] = [
      ["Gewicht", `${tool.weight_kg} kg`],
      ["Hersteller", tool.vendor || "—"],
      ["Kanäle", channels || "—"],
    ];
    if (tool.cog_mm) {
      rows.push(["Schwerpunkt", `[${tool.cog_mm.map((v) => v.toFixed(1)).join(", ")}] mm`]);
    }
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      this.toolInfo.append(dt, dd);
    }
  }

  private _updatePayloadWarning(): void {
    const name = this.toolSelect.value;
    const tool = this._tools.find((t) => t.name === name);
    if (!tool || this._robotPayloadKg === null) {
      this.payloadWarning.hidden = true;
      return;
    }
    this._showPayloadResult(
      tool.weight_kg <= this._robotPayloadKg,
      this._robotPayloadKg - tool.weight_kg,
    );
  }

  /**
   * Graut inkompatible Endeffektor-Optionen aus (Issue #74) — via CSS-Klasse,
   * NICHT `disabled`: inkompatibles Zubehör bleibt wählbar (kein Gate). Die
   * Entscheidung kommt aus dem reinen `incompatibleToolNames` (compat.ts).
   */
  private _updateGreying(): void {
    const grey = incompatibleToolNames(this._tools, this._activeRobot);
    for (const opt of Array.from(this.toolSelect.options)) {
      opt.classList.toggle("option-incompatible", grey.has(opt.value));
    }
  }

  /**
   * Zeigt die Kompatibilitäts-Warnung, wenn der aktuell gewählte Endeffektor
   * zum aktiven Roboter inkompatibel ist (Issue #74). Kein Auto-Reset, keine
   * Persistenz — nur der Hinweis (analog Payload-Warnung).
   */
  private _updateCompatWarning(): void {
    const name = this.toolSelect.value;
    const tool = this._tools.find((t) => t.name === name) ?? null;
    const msg = compatibilityWarning(tool, this._activeRobot);
    if (msg === null) {
      this.compatWarning.hidden = true;
      this.compatWarning.textContent = "";
    } else {
      this.compatWarning.hidden = false;
      this.compatWarning.textContent = msg;
    }
  }

  private _showPayloadResult(
    payload_ok: boolean | null,
    payload_margin_kg: number | null,
  ): void {
    if (payload_ok === null || payload_margin_kg === null) {
      this.payloadWarning.hidden = true;
      return;
    }
    if (payload_ok) {
      this.payloadWarning.hidden = true;
    } else {
      const over = Math.abs(payload_margin_kg).toFixed(2);
      this.payloadWarning.hidden = false;
      this.payloadWarning.textContent =
        `Payload-Warnung: Werkzeuggewicht übersteigt die Roboter-Traglast um ${over} kg. ` +
        `Befund — kein Gate; im echten Betrieb prüfen.`;
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

/**
 * Einstellungs-Fenster der Zielfunktion (Issue #212, PRD #183 Stufe 3) — DOM-Schicht.
 *
 * Das Fenster über `ui/objective-state.ts` (reine Logik: Default, Rangfolge,
 * Gleichstands-Sperre): EIN Gewichts-Satz, zwei Lesarten — Aufwiegen AUS
 * (Default) = die Gewichts-Reihenfolge ist die Rangfolge, AN = gewichtete
 * Summe. Gleichstand im Aus-Modus sperrt das Speichern (UI-seitige
 * Verhinderung, Grill 2026-07-14); der Core validiert zusätzlich.
 *
 * Persistiert wird ausschließlich über die Core-Route PUT …/objective
 * (Callback `onSave` in main.ts, einzige Schreibstelle `fgc.project`,
 * ADR-016) — der Viewer rechnet hier nichts (ADR-007): Komparator,
 * Quantisierung und Lauf-Provenienz leben im Core (`fgc.decompose.objective`).
 */

import type { ObjectiveSettings, ObjectiveWeights, PrintJob } from "../api/projects";
import {
  OBJECTIVE_CRITERIA,
  defaultObjective,
  objectiveFromJob,
  objectiveReadingText,
  objectiveSaveBlocked,
} from "./objective-state";

export interface ObjectiveCallbacks {
  /**
   * Speichern: persistiert die Config über PUT …/objective (Core bumpt bei
   * tatsächlicher Änderung `cutplan` — echo-fest, #199). Wirft bei Fehlern;
   * das Fenster zeigt sie als Status und bleibt offen.
   */
  onSave(settings: ObjectiveSettings): Promise<void>;
}

/** Das Einstellungs-Fenster der Zielfunktion — öffnen, laden, prüfen, speichern. */
export class ObjectivePanel {
  private readonly root = byId<HTMLElement>("objective-fenster");
  private readonly openBtn = byId<HTMLButtonElement>("objective-open-btn");
  private readonly aufwiegenInput = byId<HTMLInputElement>("objective-aufwiegen");
  private readonly weightsContainer = byId<HTMLElement>("objective-weights");
  private readonly readingLine = byId<HTMLParagraphElement>("objective-reading");
  private readonly statusLine = byId<HTMLParagraphElement>("objective-status");
  private readonly saveBtn = byId<HTMLButtonElement>("objective-save-btn");
  private readonly cancelBtn = byId<HTMLButtonElement>("objective-cancel-btn");
  private readonly resetBtn = byId<HTMLButtonElement>("objective-reset-btn");

  private readonly weightInputs = new Map<keyof ObjectiveWeights, HTMLInputElement>();
  /** Der zuletzt aus dem Druckjob geladene Stand — Grundlage beim Öffnen. */
  private loaded: ObjectiveSettings = defaultObjective();

  constructor(private readonly callbacks: ObjectiveCallbacks) {
    this.buildWeightRows();
    this.openBtn.addEventListener("click", () => this.open());
    this.cancelBtn.addEventListener("click", () => this.close());
    this.resetBtn.addEventListener("click", () => {
      this.fillForm(defaultObjective());
      this.refresh();
    });
    this.aufwiegenInput.addEventListener("change", () => this.refresh());
    this.root.addEventListener("click", (ev) => {
      // Klick auf den Schleier (außerhalb der Karte) schließt — wie Abbrechen.
      if (ev.target === this.root) this.close();
    });
    this.saveBtn.addEventListener("click", () => void this.save());
  }

  /** Je Kriterium eine Zeile (Label + Richtung + Zahlenfeld) — aus der Registry. */
  private buildWeightRows(): void {
    for (const criterion of OBJECTIVE_CRITERIA) {
      const label = document.createElement("label");
      label.className = "placement-field";
      const caption = document.createElement("span");
      caption.textContent = `${criterion.label}`;
      caption.title = criterion.direction;
      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.min = "0";
      input.id = `objective-w-${criterion.key}`;
      input.addEventListener("input", () => this.refresh());
      label.append(caption, input);
      this.weightsContainer.appendChild(label);
      this.weightInputs.set(criterion.key, input);
    }
  }

  /** Druckjob übernommen/geladen: gespeicherten Stand merken (Default vorbelegt). */
  restoreFromJob(job: PrintJob | null | undefined): void {
    this.loaded = objectiveFromJob(job);
    if (!this.root.hidden) {
      this.fillForm(this.loaded);
      this.refresh();
    }
  }

  /** Bedienbarkeit (Projekt offen?): steuert nur den Öffnen-Knopf. */
  setEnabled(enabled: boolean): void {
    this.openBtn.disabled = !enabled;
    if (!enabled) this.close();
  }

  private open(): void {
    this.fillForm(this.loaded);
    this.statusLine.textContent = "";
    this.root.hidden = false;
    this.refresh();
  }

  private close(): void {
    this.root.hidden = true;
  }

  private fillForm(settings: ObjectiveSettings): void {
    this.aufwiegenInput.checked = settings.aufwiegen;
    for (const [key, input] of this.weightInputs) {
      input.value = String(settings.weights[key]);
    }
  }

  /** Der aktuelle Formular-Stand (NaN bei leerem/ungültigem Feld — sperrt). */
  private currentSettings(): ObjectiveSettings {
    const weights = {} as ObjectiveWeights;
    for (const [key, input] of this.weightInputs) {
      weights[key] = input.value.trim() === "" ? Number.NaN : Number(input.value);
    }
    return { aufwiegen: this.aufwiegenInput.checked, weights };
  }

  /** Lesart-Zeile + Gleichstands-Sperre nachziehen (bei jeder Eingabe). */
  private refresh(): void {
    const settings = this.currentSettings();
    const blocked = objectiveSaveBlocked(settings);
    this.saveBtn.disabled = blocked !== null;
    this.statusLine.textContent = blocked ?? "";
    this.statusLine.classList.toggle("pl-warning", blocked !== null);
    this.readingLine.textContent = objectiveReadingText(settings);
  }

  private async save(): Promise<void> {
    const settings = this.currentSettings();
    const blocked = objectiveSaveBlocked(settings);
    if (blocked !== null) {
      // Doppelter Boden zur UI-Sperre: nie einen mehrdeutigen Stand speichern.
      this.statusLine.textContent = blocked;
      return;
    }
    this.saveBtn.disabled = true;
    this.statusLine.textContent = "Zielfunktion wird gespeichert …";
    this.statusLine.classList.remove("pl-warning");
    try {
      await this.callbacks.onSave(settings);
      this.loaded = settings;
      this.close();
    } catch (err) {
      this.statusLine.textContent = `Fehler beim Speichern der Zielfunktion: ${err}`;
      this.statusLine.classList.add("pl-warning");
      this.saveBtn.disabled = false;
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

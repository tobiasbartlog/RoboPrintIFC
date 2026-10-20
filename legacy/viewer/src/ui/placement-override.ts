/**
 * Freie Platzierungs-Overrides je Teil — dünne DOM-Anbindung (Druckplan-
 * Neuordnung II S5, Issue #94, PRD #88).
 *
 * Drei Zahlenfelder (seitlich / Abstand / Aufstellhöhe) im Zerlegungs-Aside,
 * die **nur mit fokussiertem Teil** (#106, Fokus aus `focus-store.ts`, #196)
 * bedienbar sind:
 * leer = das Teil wird automatisch platziert (der automatische Wert steht dezent
 * als Platzhalter, aus dem Core-Artefakt — ADR-007), Eingabe = feldweiser
 * Override, ↺ je Feld = zurück auf Automatik. Jede Änderung persistiert sofort
 * über die Core-Route (`PUT …/placement-override`, einzige Schreibstelle
 * `fgc.project`, ADR-016) — der Core bumpt nur den Zähler dieses Teils (#83)
 * und der Aufrufer (main.ts) stößt die Neubewertung an (ADR-007). Die
 * Umrechnung Formular ↔ Job liegt DOM-frei in `placement-override-state.ts`.
 */

import type {
  DecompositionSection,
  PlacementOverrideValues,
  PrintJob,
  SectionOverride,
} from "../api/projects";
import type { FocusReader } from "./focus-store";
import {
  type PlacementField,
  placementFieldView,
  placementOverrideForm,
  emptyPlacementOverrideForm,
  type PlacementOverrideForm,
} from "./placement-override-state";

/** Feld → Input-Element-Id; das ↺ je Feld heißt `${inputId}-reset` (Muster #92). */
const FIELDS: { field: PlacementField; inputId: string }[] = [
  { field: "lateral_mm", inputId: "placement-override-lateral" },
  { field: "standoff_mm", inputId: "placement-override-standoff" },
  { field: "stand_height_mm", inputId: "placement-override-standheight" },
];

export interface PlacementOverridePanelCallbacks {
  /**
   * Ein Feld wurde geändert/zurückgesetzt: die sparse Werte des Teils
   * persistieren (`PUT …/placement-override`; leer = Override entfernen) und
   * danach die Neubewertung anstoßen — Marker/Mesh folgen nach der Antwort.
   */
  onSaveOverride(sectionId: string, values: PlacementOverrideValues): Promise<void>;
}

export class PlacementOverridePanel {
  // Der Erklärtext liegt seit Scheibe 3 (#103) im ⓘ-Tooltip neben der Überschrift
  // (span.info#placement-override-hint) — dauerhaft sichtbar, keine DOM-Anbindung nötig.
  private readonly status = byId<HTMLParagraphElement>("placement-override-status");
  private readonly fields = FIELDS.map((spec) => ({
    ...spec,
    input: byId<HTMLInputElement>(spec.inputId),
    reset: byId<HTMLButtonElement>(`${spec.inputId}-reset`),
  }));

  private _sections: DecompositionSection[] = [];
  /** Persistierter Override-Stand je Teil (aus `job.section_overrides`). */
  private readonly _entries = new Map<string, SectionOverride>();
  private _apiAvailable = false;
  private _projectOpen = false;
  private _busy = false;

  constructor(
    // Das Ziel-Teil der Felder ist das FOKUSSIERTE Teil (Issue #106/#94) — seit
    // #196 direkt aus dem einen Halter (`focus-store.ts`) gelesen, statt einer
    // per setScope gefütterten Kopie. Ohne Fokus sind die Felder gesperrt/leer.
    private readonly focus: FocusReader,
    private readonly callbacks: PlacementOverridePanelCallbacks,
  ) {
    for (const f of this.fields) {
      // Persistieren beim Commit (change = Blur/Enter) — kein Debounce nötig.
      f.input.addEventListener("change", () => void this._save());
      // ↺ „zurück auf Automatik" (Issue #94): genau dieses Feld erbt wieder.
      f.reset.addEventListener("click", () => {
        f.input.value = "";
        void this._save();
      });
      f.input.addEventListener("input", () => this._syncDecoration(f.input, f.reset));
    }
    this._render();
  }

  /**
   * Fokus-Kaskaden-Mitglied `syncPlacementOverrideScope` (Issue #196): das
   * gewählte Teil hat gewechselt — Felder an den neuen Fokus (aus dem Store)
   * schreiben; Abwahl leert und sperrt sie.
   */
  onFocusChanged(): void {
    this.status.textContent = "";
    this._render();
  }

  /** Frisch bewertete Teile (Zerlegungslauf) — Quelle der automatischen Platzhalter. */
  setSections(sections: DecompositionSection[], job: PrintJob | undefined): void {
    this._sections = [...sections];
    this._readEntries(job);
    this._render();
  }

  /** Persistierten Override-Stand aus dem Druckjob nachziehen (Öffnen/Speichern). */
  restoreFromJob(job: PrintJob | undefined): void {
    this._readEntries(job);
    this._render();
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this._render();
  }

  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._render();
  }

  private _readEntries(job: PrintJob | undefined): void {
    this._entries.clear();
    for (const entry of job?.section_overrides ?? []) {
      this._entries.set(entry.section_id, { ...entry });
    }
  }

  /** Das Formular des gewählten (= fokussierten) Teils aus dem persistierten Stand. */
  private _currentForm(): PlacementOverrideForm {
    const sectionId = this.focus.get();
    if (sectionId === null) return emptyPlacementOverrideForm();
    return placementOverrideForm(this._entries.get(sectionId));
  }

  /** Die automatische Platzierung des Teils aus dem Core-Artefakt (Anzeige, ADR-007). */
  private _automaticFor(field: PlacementField): number | null {
    const section = this._sections.find((s) => s.section_id === this.focus.get());
    if (!section) return null;
    return section.placement[field];
  }

  private async _save(): Promise<void> {
    const sectionId = this.focus.get();
    if (this._busy || sectionId === null) return;
    const values: PlacementOverrideValues = {};
    for (const f of this.fields) {
      const raw = f.input.value.trim();
      if (raw === "") continue;
      const n = Number(raw);
      if (Number.isFinite(n)) values[f.field] = n;
    }
    this._busy = true;
    this._syncEnabled();
    this.status.textContent = "Platzierung wird gespeichert …";
    try {
      await this.callbacks.onSaveOverride(sectionId, values);
      this.status.textContent =
        Object.keys(values).length > 0
          ? "Gespeichert — gilt nur für dieses Teil (Neubewertung läuft, nur dieses Teil veraltet)."
          : "Zurückgesetzt — dieses Teil wird wieder automatisch platziert.";
    } catch (err) {
      this.status.textContent = `Fehler: ${err}`;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  /** Schreibt Formular + Platzhalter in die Felder (fokussiertes Teil), sonst leert sie. */
  private _render(): void {
    const teil = this.focus.get() !== null;
    // Der Erklärtext liegt seit Scheibe 3 (#103) im ⓘ-Tooltip neben der
    // Überschrift (span.info#placement-override-hint) — dauerhaft sichtbar,
    // kein Ein-/Ausblenden mehr.
    const form = this._currentForm();
    for (const f of this.fields) {
      if (teil) {
        const view = placementFieldView(this._automaticFor(f.field), form[f.field]);
        f.input.value = view.value;
        f.input.placeholder = view.placeholder;
      } else {
        f.input.value = "";
        f.input.placeholder = "";
      }
      this._syncDecoration(f.input, f.reset);
    }
    this._syncEnabled();
  }

  /** Override-Hervorhebung + ↺-Sichtbarkeit eines Feldes (nur mit Fokus-Teil). */
  private _syncDecoration(input: HTMLInputElement, reset: HTMLButtonElement): void {
    const overridden = this.focus.get() !== null && input.value.trim() !== "";
    input.classList.toggle("section-param-override", overridden);
    reset.hidden = !overridden;
  }

  private _syncEnabled(): void {
    const enabled =
      this._apiAvailable &&
      this._projectOpen &&
      !this._busy &&
      this.focus.get() !== null;
    for (const f of this.fields) {
      f.input.disabled = !enabled;
      f.reset.disabled = !enabled;
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

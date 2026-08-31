/**
 * Singularitäts-Advisor-Panel (Scheibe 6, Issue #65; Fokus-Verankerung #134) —
 * dünne DOM-Verdrahtung.
 *
 * Zeigt zur Platzierung des **Fokus-Abschnitts** (Teile-Palette, Issue #134)
 * die Core-Warnung **mit Typ** (Handgelenk/Ellbogen/Schulter) und einen
 * **„Anwenden"-Knopf**, der den Vorschlag über eine bestehende Schreib-Route
 * setzt und die Core-Neubewertung anstößt (ADR-007: Viewer SETZT nur). Ohne
 * Fokus zeigt „Prüfen" den freundlichen Hinweis statt eines Core-Aufrufs. Alle
 * Entscheidungen (Darstellung, Fokus-Hinweis, Anwenden-Abbildung) liegen
 * DOM-frei in `singularity-advisor-state.ts` (vitest); hier steht nur die
 * Verdrahtung.
 */

import type { PrintJob, SingularityAdvice, SingularitySuggestion } from "../api/projects";
import {
  type ApplyAction,
  advisorView,
  applyActionFor,
  focusHint,
} from "./singularity-advisor-state";

export interface SingularityAdvisorCallbacks {
  /** „Prüfen" geklickt: Core-Beratung zum Fokus-Abschnitt holen (Issue #134). */
  onCheck(sectionId: string): Promise<SingularityAdvice>;
  /** „Anwenden" geklickt: Vorschlag über eine bestehende Route setzen. */
  onApply(action: ApplyAction): Promise<void>;
  /** Aktueller Druckjob (für die Anwenden-Abbildung, z. B. bestehender Kipp/Lead). */
  currentJob(): PrintJob | undefined;
  /** Aktueller Fokus-Abschnitt aus der Teile-Palette (`null` = kein Fokus). */
  currentSectionId(): string | null;
}

export class SingularityAdvisorPanel {
  private readonly checkBtn = byId<HTMLButtonElement>("singularity-advisor-check-btn");
  private readonly status = byId<HTMLParagraphElement>("singularity-advisor-status");
  private readonly detail = byId<HTMLDivElement>("singularity-advisor-detail");
  private readonly applyBtn = byId<HTMLButtonElement>("singularity-advisor-apply-btn");

  private _apiAvailable = false;
  private _projectOpen = false;
  private _busy = false;
  private _suggestion: SingularitySuggestion | null = null;
  // Der Abschnitt, für den der letzte Vorschlag gilt (aus der Core-Antwort,
  // Issue #134) — Ziel des Platzierungs-Anwendens (`setPlacementOverride`).
  private _sectionId: string | null = null;

  constructor(private readonly callbacks: SingularityAdvisorCallbacks) {
    this.checkBtn.addEventListener("click", () => void this._check());
    this.applyBtn.addEventListener("click", () => void this._apply());
    this._render(null);
    this._syncButtons();
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this._syncButtons();
  }

  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._syncButtons();
  }

  /** Bei Projektwechsel/Neuladen die alte Beratung verwerfen. */
  reset(): void {
    this._suggestion = null;
    this._sectionId = null;
    this.status.textContent = "";
    this._render(null);
    this._syncButtons();
  }

  private async _check(): Promise<void> {
    if (this._busy) return;
    // Fokus-Verankerung (Issue #134): ohne gewähltes Teil kein Core-Aufruf —
    // freundlicher Hinweis (reine Logik in `focusHint`, vitest).
    const sectionId = this.callbacks.currentSectionId();
    const hint = focusHint(sectionId);
    if (hint !== null) {
      this._suggestion = null;
      this._sectionId = null;
      this._render(null);
      this.detail.hidden = false;
      this.detail.textContent = hint;
      this.status.textContent = "";
      return;
    }
    this._busy = true;
    this._syncButtons();
    this.status.textContent = "Prüfe Singularitätsnähe …";
    try {
      const advice = await this.callbacks.onCheck(sectionId as string);
      this._suggestion = advice.advice;
      this._sectionId = advice.section_id;
      this._render(advice);
    } catch (err) {
      this._suggestion = null;
      this._sectionId = null;
      this._render(null);
      this.status.textContent = `Fehler: ${err}`;
    } finally {
      this._busy = false;
      this._syncButtons();
    }
  }

  private async _apply(): Promise<void> {
    if (this._busy || this._suggestion === null) return;
    const action = applyActionFor(
      this._suggestion, this.callbacks.currentJob(), this._sectionId,
    );
    if (action.kind === "advisory") return; // config_flip: keine Schreibstelle (v1)
    this._busy = true;
    this._syncButtons();
    this.applyBtn.textContent = "Wende an …";
    this.status.textContent = "Vorschlag wird angewendet …";
    try {
      await this.callbacks.onApply(action);
      this.status.textContent = "Angewendet — Core neu bewertet; nachgelagerte Stände veralten.";
      // Nach dem Setzen ist der alte Vorschlag verbraucht.
      this._suggestion = null;
      this._sectionId = null;
      this._render(null);
    } catch (err) {
      this.status.textContent = `Fehler: ${err}`;
    } finally {
      this._busy = false;
      this.applyBtn.textContent = "Anwenden";
      this._syncButtons();
    }
  }

  private _render(advice: SingularityAdvice | null): void {
    if (advice === null) {
      this.detail.textContent = "";
      this.detail.hidden = true;
      this.applyBtn.hidden = true;
      return;
    }
    const view = advisorView(advice);
    if (view === null) {
      this.detail.hidden = false;
      this.detail.textContent =
        advice.type === null
          ? "Kein Befund für den Fokus-Abschnitt — Platzierung unerreichbar " +
            "oder Abschnitt nicht (mehr) im Plan."
          : "Keine kritische Singularität — nichts anzuwenden.";
      this.applyBtn.hidden = true;
      this.status.textContent = "";
      return;
    }
    this.detail.hidden = false;
    this.detail.innerHTML =
      `<strong>${escapeHtml(view.typeLabel)}</strong> — ${escapeHtml(view.leverLabel)}<br />` +
      `${escapeHtml(view.detail)}<br />` +
      `<span class="hint">Marge ${escapeHtml(view.marginBeforeText)} → ` +
      `${escapeHtml(view.marginAfterText)}${view.improves ? " (besser)" : ""}</span>`;
    this.applyBtn.hidden = false;
    this.applyBtn.textContent = view.applyLabel;
    this._applyEnabled = view.applyEnabled;
    this.status.textContent = "";
    this._syncButtons();
  }

  private _applyEnabled = false;

  private _syncButtons(): void {
    const base = this._apiAvailable && this._projectOpen && !this._busy;
    this.checkBtn.disabled = !base;
    this.applyBtn.disabled = !base || !this._applyEnabled;
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

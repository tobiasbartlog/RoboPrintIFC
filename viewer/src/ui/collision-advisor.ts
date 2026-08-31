/**
 * Kollisions-Advisor-Panel (Issue #130, ADR-024 Punkt 5) — dünne DOM-Verdrahtung.
 *
 * Spiegel des Singularitäts-Advisor-Panels, aber mit einer **Optionsliste** statt
 * eines Einzelvorschlags. Seit der Prüf-UX-Korrektur (Karte #139/#145) ist die
 * Prüfung **zweigeteilt**: „Kollision prüfen" holt nur den Basis-Befund des
 * geprüften Teils (EINE Neu-Simulation, ≈ 20 s); „Hebel-Optionen suchen" startet
 * bewusst das teure Menü (Basis + ~17 Kandidaten, je eine Neu-Simulation —
 * mehrere Minuten). Geprüft wird das **fokussierte Teil** (Teile-Palette), ohne
 * Fokus das erste Teil des Plans — der Scope-Chip im Accordion-Kopf sagt das
 * ehrlich (der frühere statische Hinweis „global" war falsch). Jede Options-
 * Zeile trägt einen eigenen „Anwenden"-Knopf, der die Option über eine
 * bestehende Schreib-Route setzt und die Neubewertung/Veraltung anstößt
 * (ADR-007: Viewer SETZT nur). Alle Entscheidungen (Texte, Anwenden-Abbildung)
 * liegen DOM-frei in `collision-advisor-state.ts` (vitest); hier steht nur die
 * Verdrahtung.
 */

import type { CollisionAdvice } from "../api/projects";
import type { FocusReader } from "./focus-store";
import {
  type CollisionApplyAction,
  type CollisionCheckMode,
  type CollisionOptionView,
  collisionAdvisorView,
  collisionApplyActionFor,
  collisionCheckStatus,
  collisionEmptyListText,
  collisionScopeLabel,
} from "./collision-advisor-state";

export interface CollisionAdvisorCallbacks {
  /**
   * Prüfung angestoßen: `includeOptions=false` holt nur den Basis-Befund
   * (eine Neu-Simulation), `true` zusätzlich die gerankte Optionsliste (teuer).
   */
  onCheck(includeOptions: boolean): Promise<CollisionAdvice>;
  /** „Anwenden" einer Option geklickt: über eine bestehende Route setzen. */
  onApply(action: CollisionApplyAction): Promise<void>;
  /**
   * Anzeigename eines Teils („#<order> <section_id>") für den Scope-Chip —
   * aufgelöst zur Renderzeit aus dem aktuellen Teilesatz (Issue #196; vorher
   * eine per Setter gefütterte Kopie). `null`, wenn das Teil unbekannt ist.
   */
  partName(sectionId: string): string | null;
}

export class CollisionAdvisorPanel {
  private readonly checkBtn = byId<HTMLButtonElement>("collision-advisor-check-btn");
  private readonly optionsBtn = byId<HTMLButtonElement>("collision-advisor-options-btn");
  private readonly scopeNote = byId<HTMLElement>("collision-advisor-scope");
  private readonly status = byId<HTMLParagraphElement>("collision-advisor-status");
  private readonly baseline = byId<HTMLDivElement>("collision-advisor-baseline");
  private readonly list = byId<HTMLUListElement>("collision-advisor-list");

  private _apiAvailable = false;
  private _projectOpen = false;
  private _busy = false;
  private _advice: CollisionAdvice | null = null;
  /** Modus der zuletzt gelaufenen Prüfung (für den Leer-Listen-Text). */
  private _lastMode: CollisionCheckMode = "befund";

  constructor(
    // Geprüft wird das FOKUSSIERTE Teil (Teile-Palette, #130-Verankerung) —
    // seit #196 direkt aus dem einen Halter (`focus-store.ts`) gelesen.
    private readonly focus: FocusReader,
    private readonly callbacks: CollisionAdvisorCallbacks,
  ) {
    this.checkBtn.addEventListener("click", () => void this._check("befund"));
    this.optionsBtn.addEventListener("click", () => void this._check("optionen"));
    this._renderScope();
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

  /**
   * Fokus-Kaskaden-Mitglied `syncCollisionAdvisorScope` (Issue #196): das
   * Fokus-Teil hat gewechselt — der Scope-Chip im Accordion-Kopf sagt ehrlich,
   * welches Teil die Prüfung bewertet (#130/#139/#145).
   */
  onFocusChanged(): void {
    this._renderScope();
  }

  /** Bei Projektwechsel/Neuladen die alte Beratung verwerfen. */
  reset(): void {
    this._advice = null;
    this.status.textContent = "";
    this._render(null);
    this._syncButtons();
  }

  private _scopeLabel(): string {
    const sectionId = this.focus.get();
    return collisionScopeLabel(
      sectionId,
      sectionId === null ? null : this.callbacks.partName(sectionId),
    );
  }

  private async _check(mode: CollisionCheckMode): Promise<void> {
    if (this._busy) return;
    this._busy = true;
    this._syncButtons();
    this.status.textContent = collisionCheckStatus(mode, this._scopeLabel());
    try {
      const advice = await this.callbacks.onCheck(mode === "optionen");
      this._advice = advice;
      this._lastMode = mode;
      this._render(advice);
      this.status.textContent = "";
    } catch (err) {
      this._advice = null;
      this._render(null);
      this.status.textContent = `Fehler: ${err}`;
    } finally {
      this._busy = false;
      this._syncButtons();
    }
  }

  private async _apply(index: number): Promise<void> {
    if (this._busy || this._advice === null) return;
    const option = this._advice.options[index];
    if (option === undefined) return;
    const action = collisionApplyActionFor(option);
    this._busy = true;
    this._syncButtons();
    this.status.textContent = "Option wird angewendet …";
    try {
      await this.callbacks.onApply(action);
      this.status.textContent =
        "Angewendet — Core neu bewertet; nachgelagerte Stände veralten. Erneut prüfen.";
      // Nach dem Setzen ist die alte Liste verbraucht (der Befund veraltet).
      this._advice = null;
      this._render(null);
    } catch (err) {
      this.status.textContent = `Fehler: ${err}`;
    } finally {
      this._busy = false;
      this._syncButtons();
    }
  }

  private _renderScope(): void {
    this.scopeNote.textContent = this._scopeLabel();
  }

  private _render(advice: CollisionAdvice | null): void {
    this.list.replaceChildren();
    if (advice === null) {
      this.baseline.hidden = true;
      this.baseline.textContent = "";
      this.list.hidden = true;
      return;
    }
    const view = collisionAdvisorView(advice);
    if (view === null) {
      this.baseline.hidden = false;
      this.baseline.textContent =
        advice.section_id === null
          ? "Kein Abschnitt — zuerst eine Zerlegung/Simulation erzeugen."
          : "Kein Kollisionsbefund (keine Kollisionsgeometrie) — nichts zu beraten.";
      this.list.hidden = true;
      return;
    }
    this.baseline.hidden = false;
    this.baseline.textContent = view.baselineText;
    this.list.hidden = false;
    if (view.options.length === 0) {
      const li = document.createElement("li");
      li.className = "collision-option collision-option-empty";
      li.textContent = collisionEmptyListText(this._lastMode);
      this.list.appendChild(li);
      return;
    }
    view.options.forEach((o, i) => this.list.appendChild(this._optionRow(o, i)));
  }

  private _optionRow(o: CollisionOptionView, index: number): HTMLLIElement {
    const li = document.createElement("li");
    li.className = "collision-option";
    if (o.removesCollision) li.classList.add("collision-option-removes");

    const detail = document.createElement("div");
    detail.className = "collision-option-detail";
    const badge = o.collisionFreeAfter ? " ✓ kollisionsfrei" : "";
    detail.innerHTML =
      `<strong>${escapeHtml(o.leverLabel)}</strong>${escapeHtml(badge)}<br />` +
      `${escapeHtml(o.detail)}`;
    li.appendChild(detail);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "collision-advisor-apply-btn";
    btn.textContent = o.applyLabel;
    btn.disabled = !this._canApply();
    btn.addEventListener("click", () => void this._apply(index));
    li.appendChild(btn);
    return li;
  }

  private _canApply(): boolean {
    return this._apiAvailable && this._projectOpen && !this._busy;
  }

  private _syncButtons(): void {
    const base = this._apiAvailable && this._projectOpen && !this._busy;
    this.checkBtn.disabled = !base;
    this.optionsBtn.disabled = !base;
    for (const btn of this.list.querySelectorAll<HTMLButtonElement>(".collision-advisor-apply-btn")) {
      btn.disabled = !base;
    }
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

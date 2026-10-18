/**
 * Workstation-Bibliothek (Issue #75, PRD #69): Galerie + reiner Formular-Editor.
 *
 * Spiegelt die Endeffektor-Bibliothek (`tool-library.ts`), aber ohne Mesh/WebGL:
 * die Karte ist eine schlichte SVG-Grafik (Podeststapel) mit Typ-Badge und
 * Höhen-/Abstands-Zusammenfassung, der Editor ein Formular. Die Fach-Umrechnung
 * (Formular→Payload, Workstation→Formular, Karten-Zusammenfassung) liegt rein in
 * `workstation-payload.ts` (ADR-007); diese Klasse besitzt nur das DOM und ruft
 * die `/workstations`-API über Callbacks. Ansichten schalten AUSSCHLIESSLICH über
 * das `.hidden`-Attribut (globales `[hidden]{display:none!important}`) — nie über
 * `display:flex/none`, sonst kehrt der tote-Reiter-Bug wieder (Lehre aus #56).
 */

import type { WorkstationDef, WorkstationRequest } from "../api/projects";
import {
  buildWorkstationRequest,
  podestStackSvg,
  summarizeWorkstation,
  workstationToForm,
  type WorkstationFormInput,
  type WorkstationPlacement,
} from "./workstation-payload";

export interface WorkstationLibraryCallbacks {
  /** Workstation-Katalog laden (GET /workstations). */
  loadWorkstations(): Promise<WorkstationDef[]>;
  /** Anlegen (POST /workstations). */
  onCreate(req: WorkstationRequest): Promise<WorkstationDef>;
  /** Bearbeiten (PUT /workstations/{name}); `name` ist die Identität. */
  onUpdate(name: string, req: WorkstationRequest): Promise<WorkstationDef>;
  /** Löschen bestätigt (DELETE /workstations/{name}). */
  onDelete(name: string): Promise<void>;
  /** Bestätigung vor dem Löschen; Default `window.confirm`, im Test stubbar. */
  confirmDelete?(ws: WorkstationDef): boolean;
}

/**
 * Der 3D-Editor-Anteil (Mesh + Roboter-Platzierung, Issue #78), den die Bibliothek
 * braucht. Optional injiziert — ohne ihn (jsdom-Tests) bleibt die Bibliothek
 * WebGL-frei, und der Request trägt kein Mesh/keine Frames (byte-gleich zu #75).
 */
export interface WorkstationPlacementEditor {
  reset(): void;
  loadFromDef(ws: WorkstationDef): void | Promise<void>;
  getPlacement(): WorkstationPlacement;
  setRobots(names: string[]): void;
}

export class WorkstationLibrary {
  private readonly gallery = byId<HTMLElement>("ws-gallery");
  private readonly editor = byId<HTMLElement>("ws-editor");
  private readonly cards = byId<HTMLElement>("ws-cards");
  private readonly empty = byId<HTMLElement>("ws-empty");
  private readonly newBtn = byId<HTMLButtonElement>("ws-new-btn");
  private readonly statusEl = byId<HTMLElement>("ws-status");
  private readonly apiWarning = byId<HTMLElement>("ws-api-warning");

  // Editor-Felder
  private readonly heading = byId<HTMLElement>("ws-heading");
  private readonly nameInput = byId<HTMLInputElement>("ws-name");
  private readonly mobilitySel = byId<HTMLSelectElement>("ws-mobility");
  private readonly adjustableChk = byId<HTMLInputElement>("ws-height-adjustable");
  private readonly discreteBox = byId<HTMLElement>("ws-heights-discrete");
  private readonly rangeBox = byId<HTMLElement>("ws-heights-range");
  private readonly heightsList = byId<HTMLElement>("ws-heights-list");
  private readonly addHeightBtn = byId<HTMLButtonElement>("ws-add-height");
  private readonly rangeMin = byId<HTMLInputElement>("ws-range-min");
  private readonly rangeMax = byId<HTMLInputElement>("ws-range-max");
  private readonly safetyInput = byId<HTMLInputElement>("ws-safety");
  private readonly vendorInput = byId<HTMLInputElement>("ws-vendor");
  private readonly robotsSel = byId<HTMLSelectElement>("ws-compatible-robots");
  private readonly saveBtn = byId<HTMLButtonElement>("ws-save-btn");
  private readonly editorStatus = byId<HTMLElement>("ws-editor-status");

  private _apiAvailable = false;
  /** Name der bearbeiteten Workstation (kein Rename) bzw. null im Anlege-Modus. */
  private _editingName: string | null = null;
  private _robotNames: string[] = [];
  private _selectedRobots: string[] = [];

  constructor(
    private readonly callbacks: WorkstationLibraryCallbacks,
    private readonly scene?: WorkstationPlacementEditor,
  ) {
    this.newBtn.addEventListener("click", () => this.openCreate());
    this.addHeightBtn.addEventListener("click", () => this.addHeightRow(0));
    this.adjustableChk.addEventListener("change", () => this.applyHeightMode());
    this.saveBtn.addEventListener("click", () => void this.save());
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this.newBtn.disabled = !available;
  }

  setStatus(text: string): void {
    this.statusEl.textContent = text;
  }

  /** Roboter-Katalog für die Kompatibilitäts-Tags (Issue #71-Muster). */
  setRobots(names: string[]): void {
    this._robotNames = [...names];
    this.renderRobotOptions();
    this.scene?.setRobots(names);
  }

  /** Zeigt die Galerie (blendet den Editor aus) und lädt den Katalog neu. */
  async openGallery(): Promise<void> {
    this.editor.hidden = true;
    this.gallery.hidden = false;
    await this.reload();
  }

  /** Öffnet den Editor leer für eine neue Workstation. */
  openCreate(): void {
    this._editingName = null;
    this.heading.textContent = "Neue Workstation";
    this.nameInput.readOnly = false;
    this.fillForm({
      name: "",
      mobility: "stationary",
      heightAdjustable: false,
      baseHeightsMm: [0],
      rangeMinMm: 0,
      rangeMaxMm: 0,
      safetyMinDistanceMm: 50,
      vendor: "",
      compatibleRobots: [],
    });
    this.scene?.reset();
    this.showEditor();
  }

  /** Öffnet den Editor mit exakter Vorbefüllung (Bearbeiten, kein Rename). */
  openEdit(ws: WorkstationDef): void {
    this._editingName = ws.name;
    this.heading.textContent = "Workstation bearbeiten";
    this.nameInput.readOnly = true; // Name = Identität (kein Rename, #56-Muster)
    this.fillForm(workstationToForm(ws));
    void this.scene?.loadFromDef(ws);
    this.showEditor();
  }

  /** Blendet die Galerie aus und zeigt den Editor (nur `.hidden`). */
  showEditor(): void {
    this.gallery.hidden = true;
    this.editor.hidden = false;
  }

  /** Lädt den Katalog (GET /workstations) und rendert die Karten. */
  async reload(): Promise<void> {
    if (!this._apiAvailable) return;
    try {
      const list = await this.callbacks.loadWorkstations();
      this.render(list);
      this.setStatus("");
    } catch (err) {
      this.setStatus(`Katalog konnte nicht geladen werden: ${err}`);
    }
  }

  /** Rendert die Kartenliste aus einer Workstation-Liste (rein DOM). */
  render(list: WorkstationDef[]): void {
    this.cards.replaceChildren();
    this.empty.hidden = list.length > 0;
    for (const ws of list) this.cards.append(this.buildCard(ws));
  }

  private buildCard(ws: WorkstationDef): HTMLElement {
    const summary = summarizeWorkstation(ws);
    const card = el("div", "lib-card ws-card");
    card.dataset.workstation = ws.name;

    const graphic = el("div", "ws-card-graphic");
    graphic.innerHTML = podestStackSvg(summary.podestHeights);
    const badge = el("span", `ws-card-badge ws-card-badge-${ws.mobility}`);
    badge.textContent = summary.typeBadge;
    graphic.append(badge);
    card.append(graphic);

    const body = el("div", "lib-card-body");
    const name = el("div", "lib-card-name");
    name.textContent = ws.name;
    const height = el("div", "lib-card-meta ws-card-height");
    height.textContent = summary.heightText;
    const safety = el("div", "lib-card-meta ws-card-safety");
    safety.textContent = summary.safetyText;
    body.append(name, height, safety);
    card.append(body);

    const actions = el("div", "lib-card-actions");
    const edit = button("Bearbeiten", "lib-card-edit");
    edit.addEventListener("click", () => this.openEdit(ws));
    const del = button("Löschen", "lib-card-delete");
    del.addEventListener("click", () => void this.onDeleteClicked(ws));
    actions.append(edit, del);
    card.append(actions);

    return card;
  }

  private async onDeleteClicked(ws: WorkstationDef): Promise<void> {
    const confirmFn =
      this.callbacks.confirmDelete ??
      ((w: WorkstationDef) => window.confirm(`Workstation „${w.name}" wirklich löschen?`));
    if (!confirmFn(ws)) return;
    this.setStatus(`Lösche „${ws.name}" …`);
    try {
      await this.callbacks.onDelete(ws.name);
      this.setStatus(`„${ws.name}" gelöscht.`);
      await this.reload();
    } catch (err) {
      this.setStatus(`Löschen fehlgeschlagen: ${err}`);
    }
  }

  /** Spiegelt ein Formular-Modell in die Eingabefelder (Vorbefüllung). */
  private fillForm(input: WorkstationFormInput): void {
    this.nameInput.value = input.name;
    this.mobilitySel.value = input.mobility;
    this.adjustableChk.checked = input.heightAdjustable;
    this.safetyInput.value = String(input.safetyMinDistanceMm);
    this.vendorInput.value = input.vendor;
    this.rangeMin.value = String(input.rangeMinMm);
    this.rangeMax.value = String(input.rangeMaxMm);
    this.heightsList.replaceChildren();
    const heights = input.baseHeightsMm.length ? input.baseHeightsMm : [0];
    for (const h of heights) this.addHeightRow(h);
    this._setSelectedRobots(input.compatibleRobots);
    this.applyHeightMode();
    this.editorStatus.textContent = "";
  }

  /** Blendet je nach „höhenverstellbar" zwischen Liste ↔ min/max um (nur `.hidden`). */
  private applyHeightMode(): void {
    const adjustable = this.adjustableChk.checked;
    this.discreteBox.hidden = adjustable;
    this.rangeBox.hidden = !adjustable;
  }

  /** Fügt der diskreten Podestliste eine Höhen-Zeile (Zahl + „Entfernen") hinzu. */
  private addHeightRow(value: number): void {
    const row = el("div", "ws-height-row");
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.className = "ws-height-input";
    input.value = String(value);
    const remove = button("×", "ws-height-remove");
    remove.title = "Podesthöhe entfernen";
    remove.addEventListener("click", () => row.remove());
    row.append(input, remove);
    this.heightsList.append(row);
  }

  private readHeights(): number[] {
    return Array.from(
      this.heightsList.querySelectorAll<HTMLInputElement>(".ws-height-input"),
      (i) => parseFloat(i.value),
    ).filter((v) => Number.isFinite(v));
  }

  private readForm(): WorkstationFormInput {
    return {
      name: this.nameInput.value,
      mobility: (this.mobilitySel.value as "stationary" | "mobile") || "stationary",
      heightAdjustable: this.adjustableChk.checked,
      baseHeightsMm: this.readHeights(),
      rangeMinMm: parseFloat(this.rangeMin.value),
      rangeMaxMm: parseFloat(this.rangeMax.value),
      safetyMinDistanceMm: parseFloat(this.safetyInput.value),
      vendor: this.vendorInput.value,
      compatibleRobots: this.readCompatibleRobots(),
    };
  }

  private async save(): Promise<void> {
    const form = this.readForm();
    // Client-Vorprüfung (freundliche Meldung); der Core validiert erneut.
    // Die Platzierung (Mesh + Frames, Issue #78) kommt aus dem 3D-Editor, falls
    // injiziert; ohne Szene bleibt der Request byte-gleich zum reinen Formular.
    let req: WorkstationRequest;
    try {
      req = buildWorkstationRequest(form, this.scene?.getPlacement());
    } catch (err) {
      this.editorStatus.textContent = err instanceof Error ? err.message : String(err);
      return;
    }
    this.saveBtn.disabled = true;
    this.editorStatus.textContent = "Speichere …";
    try {
      if (this._editingName) {
        await this.callbacks.onUpdate(this._editingName, req);
      } else {
        await this.callbacks.onCreate(req);
      }
      await this.openGallery();
    } catch (err) {
      // Auch der Core-422 (Branch-Regel) landet hier als lesbare Meldung.
      this.editorStatus.textContent = err instanceof Error ? err.message : String(err);
    } finally {
      this.saveBtn.disabled = false;
    }
  }

  private renderRobotOptions(): void {
    const selected = new Set(this._selectedRobots);
    const names = [...this._robotNames];
    for (const s of this._selectedRobots) if (!names.includes(s)) names.push(s);
    this.robotsSel.replaceChildren(
      ...names.map((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        opt.selected = selected.has(name);
        return opt;
      }),
    );
  }

  private _setSelectedRobots(names: string[]): void {
    this._selectedRobots = [...names];
    this.renderRobotOptions();
  }

  private readCompatibleRobots(): string[] {
    return Array.from(this.robotsSel.selectedOptions, (o) => o.value);
  }
}

function el(tag: string, className: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

function button(label: string, className: string): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  b.className = className;
  return b;
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

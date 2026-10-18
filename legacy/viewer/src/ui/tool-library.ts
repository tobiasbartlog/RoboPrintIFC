/**
 * Endeffektor-Bibliothek (Issue #56, Modul 3): Galerie-Übersicht + Umschalter
 * zur Editor-Ansicht (dem bestehenden 5-Schritt-Konfigurator).
 *
 * Der Reiter „Bibliothek" hat zwei Ansichten im selben Panel: die **Galerie**
 * (`#lib-gallery`) mit einer Karte je Endeffektor (Vorschaubild, Name, Vendor,
 * Gewicht, „Bearbeiten"/„Löschen") und dem prominenten „+ Neuer Endeffektor",
 * sowie den **Editor** (`#lib-editor`) mit dem Konfigurator. Diese Klasse steuert
 * nur Galerie + Umschaltung; den Konfigurator (three.js) besitzt main.ts und ruft
 * über die Callbacks hinein — so bleibt die Galerie ohne WebGL testbar (ADR-007:
 * der Viewer hält keinen Fachzustand, er liest `listTools()` und schreibt über
 * die Core-API).
 */

import type { ToolDef } from "../api/projects";

export interface ToolLibraryCallbacks {
  /** Endeffektor-Katalog laden (GET /tools). */
  loadTools(): Promise<ToolDef[]>;
  /** „+ Neuer Endeffektor" — Konfigurator leer öffnen. */
  onNew(): void;
  /** „Bearbeiten" — Konfigurator mit dem Endeffektor vorbefüllt öffnen. */
  onEdit(tool: ToolDef): void;
  /** „Löschen" bestätigt — DELETE /tools/{name} ausführen (main.ts). */
  onDelete(name: string): Promise<void>;
  /**
   * Vorschaubild (dataURL) für ein Tool oder `null` (Platzhalter, US 21/23).
   * Async: ein Cache-Treffer resolved sofort, ein Miss rendert das Mesh.
   */
  thumbnailFor(tool: ToolDef): Promise<string | null>;
  /** Bestätigung vor dem Löschen (US 18). Default `window.confirm`; im Test stubbar. */
  confirmDelete?(tool: ToolDef): boolean;
}

export class ToolLibrary {
  private readonly gallery = byId<HTMLElement>("lib-gallery");
  private readonly editor = byId<HTMLElement>("lib-editor");
  private readonly cards = byId<HTMLElement>("lib-cards");
  private readonly empty = byId<HTMLElement>("lib-empty");
  private readonly newBtn = byId<HTMLButtonElement>("lib-new-btn");
  private readonly statusEl = byId<HTMLElement>("lib-status");
  private readonly apiWarning = byId<HTMLElement>("lib-api-warning");

  private _apiAvailable = false;

  constructor(private readonly callbacks: ToolLibraryCallbacks) {
    this.newBtn.addEventListener("click", () => {
      this.showEditor();
      this.callbacks.onNew();
    });
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this.newBtn.disabled = !available;
  }

  setStatus(text: string): void {
    this.statusEl.textContent = text;
  }

  /** Zeigt die Galerie (blendet den Editor aus) und lädt den Katalog neu. */
  async openGallery(): Promise<void> {
    this.editor.hidden = true;
    this.gallery.hidden = false;
    await this.reload();
  }

  /** Blendet die Galerie aus und zeigt die Editor-Ansicht (Konfigurator). */
  showEditor(): void {
    this.gallery.hidden = true;
    this.editor.hidden = false;
  }

  /** Lädt den Katalog (GET /tools) und rendert die Karten. */
  async reload(): Promise<void> {
    if (!this._apiAvailable) return;
    try {
      const tools = await this.callbacks.loadTools();
      this.render(tools);
      this.setStatus("");
    } catch (err) {
      this.setStatus(`Katalog konnte nicht geladen werden: ${err}`);
    }
  }

  /** Rendert die Kartenliste aus einer Tool-Liste (rein DOM, ohne Netzwerk/GL). */
  render(tools: ToolDef[]): void {
    this.cards.replaceChildren();
    this.empty.hidden = tools.length > 0; // Leerzustand (US 24)
    for (const tool of tools) {
      this.cards.append(this.buildCard(tool));
    }
  }

  private buildCard(tool: ToolDef): HTMLElement {
    const card = el("div", "lib-card");
    card.dataset.tool = tool.name;

    // Vorschaubild: erst Platzhalter (US 23 — kein Absturz, wenn kein Mesh),
    // dann asynchron das gerenderte/gecachte Standbild einsetzen (US 2/22).
    const placeholder = el("div", "lib-card-thumb-placeholder");
    placeholder.textContent = "Vorschau …";
    card.append(placeholder);
    void this.callbacks
      .thumbnailFor(tool)
      .then((url) => {
        if (!url) {
          placeholder.textContent = "Kein Vorschaubild";
          return;
        }
        const img = document.createElement("img");
        img.className = "lib-card-thumb";
        img.alt = tool.name;
        img.src = url;
        placeholder.replaceWith(img);
      })
      .catch(() => {
        placeholder.textContent = "Kein Vorschaubild";
      });

    const body = el("div", "lib-card-body");
    const name = el("div", "lib-card-name");
    name.textContent = tool.name; // (US 3)
    const meta = el("div", "lib-card-meta");
    meta.textContent = `${tool.vendor || "—"} · ${tool.weight_kg} kg`; // Vendor + Gewicht (US 4)
    body.append(name, meta);
    card.append(body);

    const actions = el("div", "lib-card-actions");
    const edit = button("Bearbeiten", "lib-card-edit"); // (US 7)
    edit.addEventListener("click", () => this.callbacks.onEdit(tool));
    const del = button("Löschen", "lib-card-delete"); // (US 17)
    del.addEventListener("click", () => void this.onDeleteClicked(tool));
    actions.append(edit, del);
    card.append(actions);

    return card;
  }

  private async onDeleteClicked(tool: ToolDef): Promise<void> {
    const confirmFn =
      this.callbacks.confirmDelete ??
      ((t: ToolDef) =>
        window.confirm(
          `Endeffektor „${t.name}" wirklich löschen? Definition und Mesh werden entfernt.`,
        ));
    if (!confirmFn(tool)) return; // Bestätigungsdialog (US 18)
    this.setStatus(`Lösche „${tool.name}" …`);
    try {
      await this.callbacks.onDelete(tool.name);
      this.setStatus(`„${tool.name}" gelöscht.`);
      await this.reload(); // Galerie aktualisieren (US 20 zieht main.ts nach)
    } catch (err) {
      this.setStatus(`Löschen fehlgeschlagen: ${err}`);
    }
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

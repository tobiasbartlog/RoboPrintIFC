/**
 * ⌘K-Befehlspalette (UI-Redesign Scheibe 9, Issue #109) — die dünne DOM-Schicht
 * über der reinen Registry/Filterlogik (`palette-state.ts`). Sie besitzt keinen
 * Fachzustand: sie öffnet/schließt das Overlay (`#command-palette`, Sichtbarkeit
 * ausschließlich über das `hidden`-Attribut), filtert live über `filterPalette`
 * und **führt** einen Treffer aus, indem sie die bestehenden Mechanismen
 * wiederverwendet — Reiter über `shell.setActiveTab` (via `onNavigate`),
 * Accordion über einen Klick auf dessen Toggle (nur wenn `aria-expanded="false"`,
 * damit der Aufklapp-Zustand des besitzenden Panels konsistent bleibt), Feld über
 * `focus()`, Aktion über einen `.click()` auf den bestehenden Button und das
 * Theme über `onToggleTheme`.
 *
 * Tastatur: ⌘K/Ctrl-K schaltet um, ESC schließt, ↑/↓ bewegen die Auswahl, Enter
 * führt aus. Öffnen zusätzlich per Klick auf die Header-Such-Attrappe
 * (`#header-search`, Scheibe 2). Der reine Teil ist getrennt getestet
 * (`palette-state.test.ts`); der DOM-Vertrag gegen die index.html liegt in
 * `palette-dom.test.ts`.
 */

import {
  PALETTE_REGISTRY,
  type PaletteEntry,
  filterPalette,
} from "./palette-state";
import type { TabId } from "./tabs";

export interface PaletteCallbacks {
  /** Reiter wechseln — die Shell besitzt den Mechanismus (`shell.setActiveTab`). */
  onNavigate(tab: TabId): void;
  /** Theme kippen — das Modul aus Scheibe 1 (`fgcToggleTheme`), kein zweiter Weg. */
  onToggleTheme(): void;
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

export class CommandPalette {
  private readonly root = byId<HTMLElement>("command-palette");
  private readonly input = byId<HTMLInputElement>("command-palette-input");
  private readonly list = byId<HTMLUListElement>("command-palette-list");
  private readonly empty = byId<HTMLElement>("command-palette-empty");
  private readonly headerSearch = byId<HTMLElement>("header-search");

  private _results: PaletteEntry[] = [];
  private _active = 0;

  constructor(private readonly callbacks: PaletteCallbacks) {
    // Header-Such-Attrappe (Scheibe 2, #102): öffnet die Palette (war bisher tot).
    this.headerSearch.removeAttribute("aria-disabled");
    this.headerSearch.setAttribute("role", "button");
    this.headerSearch.setAttribute("tabindex", "0");
    this.headerSearch.title = "Jede Einstellung und Aktion suchen (⌘K)";
    this.headerSearch.addEventListener("click", () => this.open());
    this.headerSearch.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.open();
      }
    });

    // Live-Filter.
    this.input.addEventListener("input", () => this.render());

    // Klick auf den abgedunkelten Hintergrund schließt; Klick auf das Panel nicht.
    this.root.addEventListener("click", (e) => {
      if (e.target === this.root) this.close();
    });

    // Tastatur innerhalb des Overlays: ESC schließt, ↑/↓ + Enter navigieren.
    this.root.addEventListener("keydown", (e) => this.onKeydownInside(e));

    // Delegierter Klick auf eine Trefferzeile.
    this.list.addEventListener("click", (e) => {
      const li = (e.target as HTMLElement).closest<HTMLElement>("li[data-idx]");
      if (li?.dataset.idx) this.execute(this._results[Number(li.dataset.idx)]);
    });

    // Global: ⌘K/Ctrl-K schaltet um (öffnen ↔ schließen).
    window.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        this.toggle();
      }
    });
  }

  /** true, wenn das Overlay sichtbar ist. */
  get isOpen(): boolean {
    return !this.root.hidden;
  }

  open(): void {
    if (this.isOpen) return;
    this.root.hidden = false;
    this.input.value = "";
    this._active = 0;
    this.render();
    this.input.focus();
  }

  close(): void {
    if (!this.isOpen) return;
    this.root.hidden = true;
  }

  toggle(): void {
    if (this.isOpen) this.close();
    else this.open();
  }

  private onKeydownInside(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      e.preventDefault();
      this.close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (this._results.length) this._active = (this._active + 1) % this._results.length;
      this.renderActive();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (this._results.length)
        this._active = (this._active - 1 + this._results.length) % this._results.length;
      this.renderActive();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const entry = this._results[this._active];
      if (entry) this.execute(entry);
    }
  }

  private render(): void {
    this._results = filterPalette(PALETTE_REGISTRY, this.input.value);
    this._active = 0;
    this.list.replaceChildren();
    for (const [i, entry] of this._results.entries()) {
      const li = document.createElement("li");
      li.className = "cmd-row";
      li.dataset.idx = String(i);
      li.setAttribute("role", "option");

      const icon = document.createElement("span");
      icon.className = "cmd-row-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = entry.icon;

      const label = document.createElement("span");
      label.className = "cmd-row-label";
      label.textContent = entry.label;

      const group = document.createElement("span");
      group.className = "cmd-row-group";
      group.textContent = entry.group;

      li.append(icon, label, group);
      this.list.append(li);
    }
    this.empty.hidden = this._results.length > 0;
    this.renderActive();
  }

  /** Markiert die aktive Zeile (Tastatur-Auswahl) ohne Neuaufbau. */
  private renderActive(): void {
    const rows = this.list.querySelectorAll<HTMLElement>("li.cmd-row");
    rows.forEach((row, i) => {
      const on = i === this._active;
      row.classList.toggle("active", on);
      row.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  /**
   * Führt einen Treffer aus — in fester Reihenfolge über die bestehenden
   * Mechanismen (kein Neubau): Reiter → Accordion → Feldfokus → Aktions-Klick,
   * bzw. Theme-Sonderaktion. Schließt danach das Overlay.
   */
  private execute(entry: PaletteEntry | undefined): void {
    if (!entry) return;
    const t = entry.target;
    this.close();

    if (t.special === "theme") {
      this.callbacks.onToggleTheme();
      return;
    }
    if (t.tab) this.callbacks.onNavigate(t.tab);
    if (t.accordionToggleId) this.openAccordion(t.accordionToggleId);
    if (t.fieldId) this.focusField(t.fieldId);
    if (t.actionButtonId) {
      const btn = document.getElementById(t.actionButtonId) as HTMLElement | null;
      btn?.click(); // .click() auf disabled ist ein No-op — gewolltes Verhalten.
    }
  }

  /** Öffnet ein Accordion, indem der Toggle geklickt wird — nur wenn er zu ist. */
  private openAccordion(toggleId: string): void {
    const toggle = document.getElementById(toggleId);
    if (toggle && toggle.getAttribute("aria-expanded") === "false") toggle.click();
  }

  /** Fokussiert (und scrollt zu) das Zielfeld. */
  private focusField(fieldId: string): void {
    const el = document.getElementById(fieldId) as HTMLElement | null;
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.focus({ preventScroll: true });
  }
}

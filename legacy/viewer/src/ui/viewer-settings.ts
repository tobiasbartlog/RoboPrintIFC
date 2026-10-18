/**
 * Viewer-Einstellungen am 3D-Feld — dünne DOM-Klasse (Wand-Fokus ab Zerlegung).
 *
 * Ein schwebendes, ein-/ausklappbares Menü (⚙) rechts oben über dem geteilten
 * #viewport. Es gliedert seine Sicht-Schalter in **benannte Sektionen** (Issue
 * #159): „Modellansicht" und „Replay-Bühne". Jede Sektion trägt eine
 * erweiterbare Liste von Schaltern (je Schalter ein Boolean); neue Schalter
 * kommen als weiterer `ToggleSpec` dazu — kein DOM-Handstricken je Schalter.
 *
 * Reines Sicht-/Interaktions-Element (ADR-007): die Sektions-Sichtbarkeitsregel
 * lebt rein in `viewer-settings-state.ts`, die three.js-Wirkung je Schalter in
 * `main.ts`. Sichtbarkeit — der Leiste, JE SEKTION (#159) und je Schalter —
 * AUSSCHLIESSLICH über `.hidden` (Lehre aus #56).
 */

/** Ein Sicht-Schalter im Menü: Schlüssel, Beschriftung, optionaler Hinweis, Start. */
export interface ToggleSpec {
  /** Stabiler Schlüssel — main.ts verdrahtet daran die Wirkung. */
  key: string;
  /** Beschriftung neben der Checkbox. */
  label: string;
  /** Optionaler Erklär-Hinweis unter der Checkbox. */
  hint?: string;
  /** Startzustand der Checkbox. */
  checked: boolean;
}

/** Eine benannte Sektion im Menü (Issue #159): Titel + eigene Schalterliste. */
export interface SectionSpec {
  /** Stabiler Schlüssel — main.ts steuert daran die Sektions-Sichtbarkeit. */
  key: string;
  /** Überschrift der Sektion (z. B. „Replay-Bühne"). */
  title: string;
  /** Die Schalter dieser Sektion. */
  toggles: readonly ToggleSpec[];
  /** Ob der „Auf Wand einpassen"-Knopf in diese Sektion gehört (Modellansicht). */
  fitWall?: boolean;
}

export interface ViewerSettingsCallbacks {
  /** Ein Schalter wurde umgelegt — main.ts wendet die Sicht an. */
  onToggle(key: string, visible: boolean): void;
  /** „Auf Wand einpassen" geklickt — Kamera erneut auf die gewählte Wand einfassen. */
  onFitWall(): void;
}

export class ViewerSettings {
  private readonly root = byId<HTMLElement>("viewer-settings");
  private readonly toggleBtn = byId<HTMLButtonElement>("viewer-settings-toggle");
  private readonly body = byId<HTMLElement>("viewer-settings-body");
  private readonly list = byId<HTMLElement>("viewer-settings-toggles");
  private readonly checkboxes = new Map<string, HTMLInputElement>();
  private readonly toggleWraps = new Map<string, HTMLElement>();
  private readonly sections = new Map<string, HTMLElement>();

  constructor(
    private readonly callbacks: ViewerSettingsCallbacks,
    sections: readonly SectionSpec[],
  ) {
    this.toggleBtn.addEventListener("click", () => this._toggleCollapsed());
    for (const spec of sections) this.list.appendChild(this._buildSection(spec));
    this._reflectCollapsed();
    this._reflectRoot();
  }

  /**
   * Zeigt/verbirgt eine benannte Sektion (Issue #159) — nur über `.hidden`.
   * Das Menü selbst folgt: sichtbar ⇔ mindestens eine Sektion sichtbar.
   */
  setSectionVisible(key: string, visible: boolean): void {
    const section = this.sections.get(key);
    if (section) section.hidden = !visible;
    this._reflectRoot();
  }

  /**
   * Zeigt/verbirgt einen einzelnen Schalter (Issue #159: der Strang-Schalter
   * ist im Sequenz-Modus bedeutungslos) — nur über `.hidden`.
   */
  setToggleVisible(key: string, visible: boolean): void {
    const wrap = this.toggleWraps.get(key);
    if (wrap) wrap.hidden = !visible;
  }

  /** Aktueller Zustand eines Schalters (für die Wirkung in main.ts). */
  get(key: string): boolean {
    return this.checkboxes.get(key)?.checked ?? false;
  }

  /** Menü sichtbar ⇔ mindestens eine Sektion sichtbar (nur über `.hidden`). */
  private _reflectRoot(): void {
    const anyVisible = [...this.sections.values()].some((el) => !el.hidden);
    this.root.hidden = !anyVisible;
  }

  private _buildSection(spec: SectionSpec): HTMLElement {
    const section = document.createElement("section");
    section.className = "vs-section";
    section.dataset.section = spec.key;
    section.hidden = true; // Startzustand: Reiter-Gate blendet gezielt ein (#159).

    const title = document.createElement("h3");
    title.className = "vs-section-title";
    title.textContent = spec.title;
    section.append(title);

    for (const t of spec.toggles) section.append(this._buildToggle(t));

    // Der „Auf Wand einpassen"-Knopf gehört zur Modellansicht — er zieht mit
    // ihrer Sichtbarkeit um (Issue #159), statt frei im Menü zu schweben.
    if (spec.fitWall) {
      const fitBtn = byId<HTMLButtonElement>("vs-fit-wall");
      fitBtn.addEventListener("click", () => this.callbacks.onFitWall());
      section.append(fitBtn);
    }

    this.sections.set(spec.key, section);
    return section;
  }

  private _buildToggle(spec: ToggleSpec): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = "vs-toggle";

    const label = document.createElement("label");
    label.className = "check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = `vs-${spec.key}`;
    input.checked = spec.checked;
    input.addEventListener("change", () =>
      this.callbacks.onToggle(spec.key, input.checked),
    );
    label.append(input, document.createTextNode(` ${spec.label}`));
    wrap.append(label);

    if (spec.hint) {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = spec.hint;
      wrap.append(hint);
    }

    this.checkboxes.set(spec.key, input);
    this.toggleWraps.set(spec.key, wrap);
    return wrap;
  }

  private _toggleCollapsed(): void {
    this.body.hidden = !this.body.hidden;
    this._reflectCollapsed();
  }

  private _reflectCollapsed(): void {
    const collapsed = this.body.hidden;
    this.toggleBtn.setAttribute("aria-expanded", String(!collapsed));
    this.toggleBtn.textContent = `${collapsed ? "▸" : "▾"} ⚙ Ansicht`;
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

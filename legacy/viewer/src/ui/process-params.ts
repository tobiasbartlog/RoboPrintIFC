/**
 * Prozessparameter-Panel im Reiter Druckplan (Scheibe 2, Issue #59) — seit dem
 * Gilt-für-Umschalter (Issue #92, PRD #88) **scope-fähig**: dieselben
 * Slicing-Formulare (Prozessparameter, Anstellwinkel, Fortgeschritten) gelten
 * wahlweise **global** oder für das **gewählte Teil**.
 *
 * - **Global** (Default): der Nutzer trägt die Werte ein, „Speichern" schreibt
 *   sie über die Core-API in die `process_params.slice`/`orientation`-Blöcke des
 *   Druckjobs (`fgc.project` = einzige Schreibstelle, ADR-016). Leer gelassene
 *   Felder fallen auf die Prozessfenster-Karte/Code-Defaults zurück.
 * - **Teil** (Issue #92, ersetzt das separate #82-Panel): dieselben Felder
 *   zeigen die geerbten effektiven Werte **dezent** (Platzhalter, `scope-state`);
 *   jede Eingabe ist ein sparsamer, **feldweiser** Override über die bestehende
 *   #82-Mechanik (`process_params.sections`, Route `PUT …/process-params`,
 *   Feld `sections` — keine Duplikation). Jedes übersteuerte Feld trägt ein ↺
 *   „auf global zurück" (setzt genau dieses Feld auf erben).
 *
 * Der Panel hält nur Formularzustand; der Fachzustand liegt im project.json
 * (ADR-007). Die Umrechnung Formular ↔ Job liegt DOM-frei in
 * `ui/process-params-state.ts` + `ui/section-params-state.ts`, die Scope-Logik
 * (Vererbungsanzeige, Ein-Feld-Reset) in `ui/scope-state.ts` (alle vitest).
 */

import type {
  DecompositionSection,
  IkConfig,
  OrientationParams,
  PrintJob,
  SectionProcessOverride,
  SliceParams,
} from "../api/projects";
import {
  type CollapsibleState,
  collapsibleState,
  collapsibleView,
  toggleCollapsible,
} from "./collapsible-state";
import {
  type IkAxis,
  ikAxisView,
  ikConfigFormFromBlock,
  ikConfigRequestFromForm,
  readIkAxis,
  setIkAxis,
} from "./ik-config-state";
import {
  orientationFormFromJob,
  orientationRequestFromForm,
  sliceFormFromJob,
  sliceRequestFromForm,
} from "./process-params-state";
import {
  type OverrideFieldRef,
  type Scope,
  overrideFieldView,
  readOverrideField,
  setOverrideField,
} from "./scope-state";
import {
  type SectionOverrideForm,
  emptySectionOverrideForm,
  sectionOverrideForm,
  sectionOverrideRequestFromForm,
  sectionsRequestFromForms,
} from "./section-params-state";

/** Klartext-Beschriftung des Aufklapp-Bereichs (Issue #60). */
const ADVANCED_LABEL = "Fortgeschritten (Geschwindigkeiten, io)";

/**
 * Die Slicing-Felder des Aside-Formulars: Adresse im (Override-)Formular
 * (`scope-state`) + Input-Element-Id. Das ↺ je Feld heißt `${inputId}-reset`.
 */
const FIELDS: { ref: OverrideFieldRef; inputId: string }[] = [
  { ref: { group: "slice", field: "layerHeightMm" }, inputId: "process-params-layer-height" },
  { ref: { group: "slice", field: "strandWidthMm" }, inputId: "process-params-strand-width" },
  { ref: { group: "slice", field: "nShells" }, inputId: "process-params-shells" },
  { ref: { group: "orientation", field: "leadDeg" }, inputId: "process-params-lead-deg" },
  { ref: { group: "orientation", field: "kippDeg" }, inputId: "process-params-kipp-deg" },
  { ref: { group: "slice", field: "vPrintMmS" }, inputId: "process-params-v-print" },
  { ref: { group: "slice", field: "vTravelMmS" }, inputId: "process-params-v-travel" },
  { ref: { group: "slice", field: "ioPrint" }, inputId: "process-params-io-print" },
  { ref: { group: "slice", field: "ioTravel" }, inputId: "process-params-io-travel" },
];

/**
 * Die drei IK-Konfigurationsschalter (Kollisionskontrolle S4, #129): Achse +
 * Select-Element-Id. Das ↺ heißt `${selectId}-reset`, der geerbte Hinweis (Teil-
 * Modus) `${selectId}-hint`. Tri-State (auto/Zustand A/Zustand B), darum eigener
 * Pfad neben den numerischen FIELDS (Zustand in `SectionOverrideForm.ikConfig`).
 */
const IK_FIELDS: { axis: IkAxis; selectId: string }[] = [
  { axis: "shoulder", selectId: "process-params-ik-shoulder" },
  { axis: "elbow", selectId: "process-params-ik-elbow" },
  { axis: "wrist", selectId: "process-params-ik-wrist" },
];

export interface ProcessParamsPanelCallbacks {
  /**
   * „Speichern" im Global-Scope: Slice-, Orientierungs- und IK-Konfigurations-Block
   * persistieren (`ikConfig` #129 — die drei Tri-State-Schalter, sparse).
   */
  onSave(slice: SliceParams, orientation: OrientationParams, ikConfig: IkConfig): Promise<void>;
  /**
   * „Speichern" im Teil-Scope (Issue #92): die Abschnitts-Overrides persistieren
   * (PUT …/process-params, Feld `sections` — dieselbe #82-Route). Es gehen alle
   * bekannten Teile mit — auch leer geräumte (→ `{}`, erben wieder global).
   */
  onSaveSections(sections: Record<string, SectionProcessOverride>): Promise<void>;
  /**
   * Feuert bei jeder Feld-Eingabe (Reglerziehen, Issue #85) — für die sofortige,
   * IK-freie Live-Vorschau „Vorbereiten": die Bahn des Fokus-Abschnitts wird aus
   * den **live** (noch ungespeicherten) Formularwerten neu gesliced. Reine
   * Darstellung (ADR-007); nichts wird persistiert, bis „Speichern".
   */
  onLiveChange?(): void;
}

export class ProcessParamsPanel {
  private readonly saveBtn = byId<HTMLButtonElement>("process-params-save-btn");
  private readonly status = byId<HTMLParagraphElement>("process-params-status");

  // „Fortgeschritten"-Aufklappbereich (Issue #60): Geschwindigkeiten + io.
  private readonly advancedToggle = byId<HTMLButtonElement>("process-params-advanced-toggle");
  private readonly advancedBody = byId<HTMLElement>("process-params-advanced-body");

  /** Feld → Input + ↺-Button (Issue #92), in FIELDS-Reihenfolge. */
  private readonly fields = FIELDS.map((spec) => ({
    ...spec,
    input: byId<HTMLInputElement>(spec.inputId),
    reset: byId<HTMLButtonElement>(`${spec.inputId}-reset`),
  }));

  /** IK-Achse → Select + ↺-Button + geerbter Hinweis (#129), in IK_FIELDS-Reihenfolge. */
  private readonly ikFields = IK_FIELDS.map((spec) => ({
    ...spec,
    select: byId<HTMLSelectElement>(spec.selectId),
    reset: byId<HTMLButtonElement>(`${spec.selectId}-reset`),
    hint: byId<HTMLElement>(`${spec.selectId}-hint`),
  }));

  private _apiAvailable = false;
  private _projectOpen = false;
  private _busy = false;
  private _advanced: CollapsibleState = collapsibleState(false);

  // Geltungsbereich (Issue #92): das DOM zeigt immer das Formular des aktiven
  // Scopes; das jeweils andere liegt gestasht in _global/_sectionForms.
  // BEWUSST keine Fokus-Kopie (Issue #196): das Paar ist die Adresse des
  // GEZEIGTEN Formulars und muss dem Store nachlaufen, bis `setScope` den
  // alten Stand gestasht hat — gespeist in EINEM Hop über die Fokus-Kaskade
  // (`syncProcessParamsScope`) bzw. den Radio-Klick des Gilt-für-Umschalters.
  private _scope: Scope = "global";
  private _sectionId: string | null = null;
  /** Das globale Formular (gleiche Gestalt wie ein Override-Formular). */
  private _global: SectionOverrideForm = emptySectionOverrideForm();
  /** Die bekannten Teile (aus der Zerlegung) + ihre Override-Formulare (#82). */
  private _sections: DecompositionSection[] = [];
  private readonly _sectionForms = new Map<string, SectionOverrideForm>();

  constructor(private readonly callbacks: ProcessParamsPanelCallbacks) {
    this.advancedToggle.addEventListener("click", () => {
      this._advanced = toggleCollapsible(this._advanced);
      this._syncAdvanced();
    });
    this._syncAdvanced();
    // Live-Vorschau (Issue #85): jede Eingabe stößt die sofortige Neuberechnung
    // der Fokus-Abschnitts-Bahn an (ohne Speichern, ohne IK). Im Teil-Scope
    // zusätzlich Override-Markierung + ↺ des Feldes nachziehen (Issue #92).
    for (const f of this.fields) {
      f.input.addEventListener("input", () => {
        this._syncFieldDecoration(f.input, f.reset);
        this.callbacks.onLiveChange?.();
      });
      // ↺ „auf global zurück" (Issue #92): genau dieses Feld erbt wieder.
      f.reset.addEventListener("click", () => {
        f.input.value = "";
        this._syncFieldDecoration(f.input, f.reset);
        this.callbacks.onLiveChange?.();
      });
    }
    // IK-Konfigurationsschalter (#129): Auswahl → Override-Markierung + ↺ nachziehen.
    // Reine Konfigurationswahl (kein Live-Slice — sie wirkt erst in der Simulation).
    for (const f of this.ikFields) {
      f.select.addEventListener("change", () => this._syncIkDecoration(f));
      f.reset.addEventListener("click", () => {
        f.select.value = "";
        this._syncIkDecoration(f);
      });
    }
    this.saveBtn.addEventListener("click", async () => {
      if (this._busy) return;
      this._stash();
      this._busy = true;
      this._syncButtons();
      this.saveBtn.textContent = "Speichert …";
      this.status.textContent =
        this._scope === "teil"
          ? "Teil-Overrides werden gespeichert …"
          : "Prozessparameter werden gespeichert …";
      try {
        if (this._scope === "teil") {
          // Dieselbe #82-Route (Feld `sections`) — alle bekannten Teile gehen
          // mit, leer geräumte als `{}` (erben wieder komplett global).
          const sections = sectionsRequestFromForms(this._allSectionForms());
          await this.callbacks.onSaveSections(sections);
          const own = sectionOverrideRequestFromForm(this._currentForm());
          this.status.textContent =
            Object.keys(own).length > 0
              ? "Gespeichert — Overrides gelten nur für dieses Teil; nur seine Simulation/sein Export veralten (#83)."
              : "Zurückgesetzt — dieses Teil erbt wieder die globalen Parameter.";
        } else {
          const slice = sliceRequestFromForm(this._global.slice);
          const orientation = orientationRequestFromForm(this._global.orientation);
          const ikConfig = ikConfigRequestFromForm(this._global.ikConfig);
          await this.callbacks.onSave(slice, orientation, ikConfig);
          this.status.textContent =
            Object.keys(slice).length === 0 &&
            Object.keys(orientation).length === 0 &&
            Object.keys(ikConfig).length === 0
              ? "Zurückgesetzt — Karten-/Code-Defaults, Düse senkrecht von oben, IK auto."
              : "Gespeichert — gilt beim Slicen; Zerlegung/Simulation/Export veralten.";
        }
      } catch (err) {
        this.status.textContent = `Fehler: ${err}`;
      } finally {
        this._busy = false;
        this.saveBtn.textContent = "Speichern";
        this._syncButtons();
      }
    });
  }

  /**
   * Stellt die Formulare aus dem Druckjob wieder her (nach Projekt-Öffnen bzw.
   * nach einem Speichern): globales Formular + die Override-Formulare der
   * bekannten Teile (`process_params.sections`, #82).
   */
  restoreFromJob(job: PrintJob | undefined): void {
    this._global = {
      slice: sliceFormFromJob(job),
      orientation: orientationFormFromJob(job),
      ikConfig: ikConfigFormFromBlock(job?.process_params?.ik_config),
    };
    const overrides = job?.process_params?.sections ?? {};
    for (const section of this._sections) {
      this._sectionForms.set(
        section.section_id,
        sectionOverrideForm(overrides[section.section_id]),
      );
    }
    this._writeCurrent();
    this.status.textContent = "";
    this._syncButtons();
  }

  /**
   * Setzt die bekannten Teile (aus dem Zerlegungslauf) und baut ihre
   * Override-Formulare aus dem Druckjob neu auf (Issue #82/#92).
   */
  setSections(sections: DecompositionSection[], job: PrintJob | undefined): void {
    this._sections = [...sections].sort((a, b) => a.order - b.order);
    this._sectionForms.clear();
    const overrides = job?.process_params?.sections ?? {};
    for (const section of this._sections) {
      this._sectionForms.set(
        section.section_id,
        sectionOverrideForm(overrides[section.section_id]),
      );
    }
    this._writeCurrent();
  }

  /**
   * Gilt-für-Umschalter (Issue #92): Geltungsbereich der Formulare wechseln.
   * Der aktuelle Formularstand wird gestasht (kein Verlust ungespeicherter
   * Eingaben), dann zeigen **dieselben** Felder den neuen Scope — im Teil-Scope
   * die geerbten Werte dezent als Platzhalter, Overrides hervorgehoben + ↺.
   */
  setScope(scope: Scope, sectionId: string | null): void {
    const nextScope: Scope = scope === "teil" && sectionId !== null ? "teil" : "global";
    const nextId = nextScope === "teil" ? sectionId : null;
    if (nextScope === this._scope && nextId === this._sectionId) return;
    this._stash();
    this._scope = nextScope;
    this._sectionId = nextId;
    this._writeCurrent();
    this.status.textContent = "";
  }

  /**
   * Anzahl gesetzter Overrides im aktuellen Scope (nur Lese-Zugriff, #107) —
   * speist die Kopf-Notiz des Prozessparameter-Accordions („N Overrides" im
   * Teil-Scope, sonst „gilt global"). Liest wie `liveParams()` zunächst das DOM
   * in das aktive Formular zurück (idempotent), zählt dann die nicht-erbenden
   * Felder. Keine Verhaltensänderung an der #82/#92-Mechanik.
   */
  overrideCount(): number {
    this._stash();
    const form = this._currentForm();
    let n = 0;
    for (const f of this.fields) {
      if (readOverrideField(form, f.ref) !== null) n += 1;
    }
    for (const f of this.ikFields) {
      if (readIkAxis(form.ikConfig, f.axis) !== null) n += 1;
    }
    return n;
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this._syncButtons();
  }

  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._syncButtons();
  }

  /** Spiegelt den reinen Aufklapp-Zustand auf das DOM (Issue #60). */
  private _syncAdvanced(): void {
    const view = collapsibleView(this._advanced, ADVANCED_LABEL);
    this.advancedBody.hidden = view.bodyHidden;
    this.advancedToggle.setAttribute("aria-expanded", view.ariaExpanded);
    this.advancedToggle.textContent = view.toggleLabel;
  }

  /**
   * Die aktuellen (live, ggf. ungespeicherten) **globalen** Formularwerte als
   * sparse API-Blöcke — Eingabe für die Live-Vorschau (Issue #85). Im Teil-Scope
   * kommen sie aus dem gestashten globalen Formular.
   */
  liveParams(): { slice: SliceParams; orientation: OrientationParams } {
    this._stash();
    return {
      slice: sliceRequestFromForm(this._global.slice),
      orientation: orientationRequestFromForm(this._global.orientation),
    };
  }

  /**
   * Der aktuelle (live, ggf. ungespeicherte) Override eines Teils als sparse
   * Block — Eingabe für die Live-Vorschau (Issue #85/#92). Nur gesetzte Felder;
   * ein unbekanntes Teil ergibt `{}` (erbt komplett global).
   */
  liveOverrideFor(sectionId: string): SectionProcessOverride {
    this._stash();
    const form = this._sectionForms.get(sectionId);
    return form ? sectionOverrideRequestFromForm(form) : {};
  }

  /** Liest das DOM in das Formular des aktiven Scopes zurück. */
  private _stash(): void {
    let form = emptySectionOverrideForm();
    for (const f of this.fields) {
      form = setOverrideField(form, f.ref, fieldValue(f.input));
    }
    // IK-Schalter (#129): der Select-Wert ("" = auto/erbt) ins Formular.
    let ik = form.ikConfig;
    for (const f of this.ikFields) {
      ik = setIkAxis(ik, f.axis, ikSelectValue(f.select));
    }
    form = { ...form, ikConfig: ik };
    if (this._scope === "teil" && this._sectionId !== null) {
      this._sectionForms.set(this._sectionId, form);
    } else {
      this._global = form;
    }
  }

  /** Das Formular des aktiven Scopes (Teil-Scope: das des gewählten Teils). */
  private _currentForm(): SectionOverrideForm {
    if (this._scope === "teil" && this._sectionId !== null) {
      return this._sectionForms.get(this._sectionId) ?? emptySectionOverrideForm();
    }
    return this._global;
  }

  /** Alle bekannten Teil-Formulare (für den `sections`-Request, #82). */
  private _allSectionForms(): Record<string, SectionOverrideForm> {
    const out: Record<string, SectionOverrideForm> = {};
    for (const section of this._sections) {
      out[section.section_id] =
        this._sectionForms.get(section.section_id) ?? emptySectionOverrideForm();
    }
    return out;
  }

  /**
   * Schreibt das Formular des aktiven Scopes in die Felder. Teil-Scope: der
   * geerbte globale Wert steht dezent als Platzhalter (`overrideFieldView`),
   * übersteuerte Felder sind markiert und tragen ihr ↺.
   */
  private _writeCurrent(): void {
    const form = this._currentForm();
    const teil = this._scope === "teil";
    for (const f of this.fields) {
      if (teil) {
        const view = overrideFieldView(
          readOverrideField(this._global, f.ref),
          readOverrideField(form, f.ref),
        );
        f.input.value = view.value;
        f.input.placeholder = view.placeholder;
      } else {
        const v = readOverrideField(form, f.ref);
        f.input.value = v === null ? "" : String(v);
        // Global-Scope: leeres Feld fällt auf den Karten-Default zurück (der
        // Core kennt die verbindlichen Werte, ADR-014). Der Platzhalter macht
        // das sichtbar; „<default>" bleibt literal, da der Viewer nie rechnet.
        f.input.placeholder = "<default> · Karten-Default";
      }
      this._syncFieldDecoration(f.input, f.reset);
    }
    // IK-Konfigurationsschalter (#129): im Teil-Scope steht der Override im Select,
    // der geerbte globale Zustand dezent als Hinweis; im Global-Scope der Wert selbst.
    for (const f of this.ikFields) {
      if (teil) {
        const view = ikAxisView(
          readIkAxis(this._global.ikConfig, f.axis),
          readIkAxis(form.ikConfig, f.axis),
        );
        f.select.value = view.value;
        f.hint.textContent = view.inheritedLabel;
      } else {
        const v = readIkAxis(form.ikConfig, f.axis);
        f.select.value = v ?? "";
        f.hint.textContent = "";
      }
      this._syncIkDecoration(f);
    }
  }

  /** Override-Hervorhebung + ↺-Sichtbarkeit eines Feldes (nur im Teil-Scope). */
  private _syncFieldDecoration(input: HTMLInputElement, reset: HTMLButtonElement): void {
    const overridden = this._scope === "teil" && input.value.trim() !== "";
    input.classList.toggle("section-param-override", overridden);
    reset.hidden = !overridden;
  }

  /**
   * Override-Hervorhebung + ↺ + geerbter Hinweis eines IK-Schalters (#129). Der
   * Hinweis („Zustand A · erbt") ist nur im Teil-Scope sichtbar; das ↺ nur, wenn
   * die Achse dort fixiert (übersteuert) ist.
   */
  private _syncIkDecoration(f: {
    select: HTMLSelectElement;
    reset: HTMLButtonElement;
    hint: HTMLElement;
  }): void {
    const teil = this._scope === "teil";
    const overridden = teil && f.select.value !== "";
    f.select.classList.toggle("section-param-override", overridden);
    f.reset.hidden = !overridden;
    f.hint.hidden = !teil;
  }

  private _syncButtons(): void {
    const enabled = this._apiAvailable && this._projectOpen && !this._busy;
    this.saveBtn.disabled = !enabled;
    for (const f of this.fields) {
      f.input.disabled = !enabled;
      f.reset.disabled = !enabled;
    }
    for (const f of this.ikFields) {
      f.select.disabled = !enabled;
      f.reset.disabled = !enabled;
    }
  }
}

/** Leeres Feld → null (nicht gesetzt); sonst die endliche Zahl. */
function fieldValue(input: HTMLInputElement): number | null {
  const raw = input.value.trim();
  if (raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** Select-Wert eines IK-Schalters: "a"/"b" oder null (leer = auto/erbt). */
function ikSelectValue(select: HTMLSelectElement): "a" | "b" | null {
  return select.value === "a" || select.value === "b" ? select.value : null;
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

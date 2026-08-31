/**
 * Teile-Palette am 3D-Feld — dünne DOM-Klasse (Druckplan-Neuordnung II S2, Issue
 * #91, PRD #88). Verheiratet die reine Ableitung (`parts-palette-state.ts`) mit
 * dem DOM: eine ein-/ausklappbare Leiste am geteilten 3D-Feld mit je einem Teil
 * pro Zeile — Ampel, Name, erreichbarer Anteil, ▪-Marker (Slicing-Override) und
 * ein Platzierungs-Override-Select (Funktionsumfang der früheren Abschnittsliste
 * im Aside, die hier vollständig aufgeht).
 *
 * Sichtbarkeit AUSSCHLIESSLICH über das `.hidden`-Attribut (Leiste am Reiter
 * Druckplan, Ein-/Ausklappen des Körpers) — nie über `style.display` (Lehre aus
 * #56). Reines Sicht-/Interaktions-Element (ADR-007): der Fachzustand (Fokus,
 * Overrides) lebt im `DruckplanPanel`; Klicks melden nur zurück.
 */

import type { PlacementOption } from "../api/projects";
import { moduleCheckLine, type PartAmpel, type PartEntry } from "./parts-palette-state";
import { paletteTitle, type Zerlegungsart } from "./zerlegungsart-state";

export interface PartsPaletteCallbacks {
  /** Klick auf ein Teil: in den Fokus nehmen (Toggle) — dieselbe Auswahl wie im 3D-Feld. */
  onSelect(sectionId: string): void;
  /** Platzierungs-Override eines Teils geändert (option_id oder null = automatisch). */
  onOverrideChange(sectionId: string, optionId: string | null): void;
}

/** Was die Palette je Render zusätzlich zu den Einträgen braucht. */
export interface PartsPaletteRenderInput {
  entries: readonly PartEntry[];
  /** Wählbare Platzierungen (für das Override-Select je Teil). */
  options: readonly PlacementOption[];
  /** Aktueller Platzierungs-Override eines Teils (option_id) oder null. */
  overrideFor(sectionId: string): string | null;
  /** Bedienbarkeit (API + Projekt offen, nicht busy) — sperrt die Selects. */
  enabled: boolean;
}

export class PartsPalette {
  private readonly root = byId<HTMLElement>("parts-palette");
  private readonly toggleBtn = byId<HTMLButtonElement>("parts-palette-toggle");
  private readonly body = byId<HTMLElement>("parts-palette-body");
  private readonly list = byId<HTMLUListElement>("parts-palette-list");
  private readonly empty = byId<HTMLParagraphElement>("parts-palette-empty");

  /** Aktuelle Zerlegungsart (Issue #95) — schaltet die Palette-Beschriftung
   *  („Abschnitte"/„Module") und den Kopf-Button-Text. */
  private _kind: Zerlegungsart = "abschnitt";

  constructor(private readonly callbacks: PartsPaletteCallbacks) {
    // Ein-/Ausklappen: nur der Körper (Liste) verschwindet, die Kopfleiste bleibt.
    this.toggleBtn.addEventListener("click", () => this._toggleCollapsed());
    this._reflectCollapsed();
  }

  /** Setzt die Zerlegungsart für die Beschriftung (Issue #95) — reine Anzeige. */
  setKind(kind: Zerlegungsart): void {
    this._kind = kind;
    this._reflectCollapsed();
  }

  /** Zeigt/verbirgt die ganze Leiste (Reiter-Gate) — nur über `.hidden`. */
  setVisible(visible: boolean): void {
    this.root.hidden = !visible;
  }

  /** true, wenn die Leiste gerade eingeklappt ist (nur Kopfleiste sichtbar). */
  get collapsed(): boolean {
    return this.body.hidden;
  }

  /** Zeichnet die Teile neu (Einträge + Platzierungs-Selects). */
  render(input: PartsPaletteRenderInput): void {
    this.list.replaceChildren();
    this.empty.hidden = input.entries.length > 0;
    for (const entry of input.entries) {
      this.list.appendChild(this._buildRow(entry, input));
    }
  }

  private _buildRow(entry: PartEntry, input: PartsPaletteRenderInput): HTMLLIElement {
    const li = document.createElement("li");
    li.className = "parts-part";
    li.classList.add(ampelClass(entry.ampel));
    if (entry.selected) li.classList.add("selected");
    li.dataset.section = entry.section_id;

    const dot = document.createElement("span");
    dot.className = "ampel";
    // Ein geerbtes Reihen-Urteil (,vermutlich', #164) bekommt einen HOHLEN Punkt —
    // es darf nicht wie ein geprüftes Urteil aussehen (Ehrlichkeit, Kern des Issues).
    // Ein „ungeprüft"-Zustand (Issue #170: kein Urteil / Prüffehler) trägt einen
    // eigenen, offenen Ring — sichtbar unterscheidbar von grün/rot/,vermutlich'.
    const presumed = entry.printability?.presumed ?? false;
    const ungeprueft = entry.ampel === "ungeprueft";
    if (presumed) dot.classList.add("presumed");
    dot.textContent = presumed ? "◌" : ungeprueft ? "◍" : "●";
    dot.title = entry.printability ? entry.printability.title : ampelTitle(entry.ampel);

    // Name: Klick nimmt das Teil in den Fokus (Zwilling des 3D-Klicks, #84).
    const name = document.createElement("button");
    name.type = "button";
    name.className = "parts-part-name";
    name.textContent = entry.name;
    name.title = "Anklicken, um dieses Teil in den Fokus zu nehmen (erneut = Fokus lösen)";
    name.addEventListener("click", () => this.callbacks.onSelect(entry.section_id));

    // ▪-Marker: nur wenn das Teil individuelle Overrides trägt (Slicing #82
    // und/oder Platzierung #94).
    const marker = document.createElement("span");
    marker.className = "parts-part-marker";
    marker.textContent = "▪";
    marker.title = "Dieses Teil trägt individuelle Overrides (Slicing oder Platzierung).";
    marker.hidden = !entry.has_override;

    const pct = document.createElement("span");
    pct.className = "parts-part-reach";
    pct.textContent = `erreichbar ${(entry.reachable_fraction * 100).toFixed(0)} %`;

    // Druckbarkeits-Badge (Issue #164): das sichtbare Urteil aus dem Zerlegungslauf
    // (Freigang + repräsentative Prüf-Tür) — ohne vorherige Simulation. Grün nur,
    // was die Prüf-Tür frei sah; ein geerbtes Reihen-Urteil trägt „vermutlich".
    const printabilityEl = document.createElement("span");
    printabilityEl.className = "parts-part-printability";
    if (entry.printability) {
      printabilityEl.classList.add(entry.printability.severity); // ok | bad
      if (entry.printability.presumed) printabilityEl.classList.add("presumed");
      printabilityEl.textContent = entry.printability.label;
      printabilityEl.title = entry.printability.title;
    } else {
      printabilityEl.hidden = true;
    }

    // Kollisions-Badge (Kollisionskontrolle S3, US 12, #128): getrennter Kanal
    // neben der Platzierungs-Ampel (die bleibt unangetastet). Nur bei Befund.
    // Veraltet (Issue #182): bleibt sichtbar, wird nur markiert (.stale + Hinweis
    // im Titel) — dieselbe Ableitung wie die übrigen Stufen-Badges.
    const collisionBadgeEl = document.createElement("span");
    collisionBadgeEl.className = "parts-part-collision";
    if (entry.collision_badge) {
      collisionBadgeEl.classList.add(entry.collision_badge.status);
      collisionBadgeEl.textContent = entry.collision_badge.label;
      collisionBadgeEl.title = entry.collision_badge.title;
      if (entry.collision_badge.stale) {
        collisionBadgeEl.classList.add("stale");
        collisionBadgeEl.textContent += " · veraltet";
        collisionBadgeEl.title +=
          " Veraltet: eine Parameter-, Platzierungs- oder Kipp-Änderung seit dieser " +
          "Simulation ist noch nicht neu geprüft.";
      }
    } else {
      collisionBadgeEl.hidden = true;
    }

    // Platzierungs-Override-Select: Funktionsumfang der alten Aside-Liste (#25).
    const select = document.createElement("select");
    select.className = "parts-part-override";
    select.title = "Platzierung dieses Teils übersteuern";
    const autoOpt = document.createElement("option");
    autoOpt.value = "";
    autoOpt.textContent = "— automatisch gesucht —";
    select.append(autoOpt);
    for (const opt of input.options) {
      const o = document.createElement("option");
      o.value = opt.option_id;
      o.textContent = opt.option_id;
      select.append(o);
    }
    select.value = input.overrideFor(entry.section_id) ?? "";
    select.disabled = !input.enabled || input.options.length === 0;
    select.addEventListener("change", () => {
      this.callbacks.onOverrideChange(entry.section_id, select.value || null);
    });

    li.append(dot, name, marker, pct, printabilityEl, collisionBadgeEl, select);
    // Teil-Detail (Issue #93): Platzierungswerte (seitlich/Abstand/Aufstellhöhe)
    // + kinematische Marge — allesamt aus dem Core-Artefakt (ADR-007), keine
    // Viewer-Ableitung. Der Marker/das Mesh im 3D-Feld visualisiert dieselbe
    // Platzierung; hier stehen die Zahlen.
    li.append(this._buildDetail(entry));
    // Modulgrenzen-Befund (Issue #90/#95): Gewicht (kg) + Grenzen-Befund je Teil,
    // NUR bei Art „modul" (module_check aus dem S6-Artefakt vorhanden) — verbatim
    // aus dem Core (Ampeln unverändert), **Befund, kein Gate** (ADR-022).
    if (entry.module_check) {
      li.append(this._buildModuleCheck(entry));
    }
    return li;
  }

  /** Gewicht + Grenzen-Befund eines Moduls (Issue #90/#95), verbatim aus dem Core. */
  private _buildModuleCheck(entry: PartEntry): HTMLParagraphElement {
    const check = entry.module_check!;
    const p = document.createElement("p");
    p.className = "parts-part-module";
    if (check.limits.some((f) => f.exceeded)) p.classList.add("exceeded");
    p.textContent = moduleCheckLine(check);
    p.title =
      "Modulgewicht (Volumen × Dichte) + Obergrenzen-Befund aus dem Core-Artefakt " +
      "(ADR-022) — Befund, kein Gate.";
    return p;
  }

  /** Zahlen-Detail eines Teils: Platzierung + Bewertung, verbatim aus dem Core. */
  private _buildDetail(entry: PartEntry): HTMLParagraphElement {
    const detail = document.createElement("p");
    detail.className = "parts-part-detail";
    const margin = entry.kinematic_margin === null ? "—" : entry.kinematic_margin.toFixed(3);
    detail.textContent =
      `Platzierung: seitl. ${fmtMm(entry.lateral_mm)} · Abstand ${fmtMm(entry.standoff_mm)} · ` +
      `Aufstellhöhe ü. Boden ${fmtMm(entry.stand_height_mm)} · Marge ${margin}`;
    detail.title =
      "Platzierung + Bewertung aus dem Core-Artefakt (Plan, kein Setup — ADR-006). " +
      "Die Aufstellhöhe ist absolut über dem Boden (= Wandfuß, Issue #132/#133); " +
      "0 = Roboter steht auf dem Boden.";
    return detail;
  }

  private _toggleCollapsed(): void {
    this.body.hidden = !this.body.hidden;
    this._reflectCollapsed();
  }

  private _reflectCollapsed(): void {
    const collapsed = this.body.hidden;
    const title = paletteTitle(this._kind); // „Abschnitte" / „Module" (Issue #95)
    this.toggleBtn.setAttribute("aria-expanded", String(!collapsed));
    this.toggleBtn.textContent = `${collapsed ? "▸" : "▾"} ${title}`;
  }
}

/** Kompakte mm-Anzeige (ganzzahlig gerundet) für das Teil-Detail. */
function fmtMm(mm: number): string {
  return `${Math.round(mm)} mm`;
}

function ampelClass(ampel: PartAmpel): string {
  return ampel === "green" ? "green" : ampel === "red" ? "red" : "ungeprueft";
}

function ampelTitle(ampel: PartAmpel): string {
  return ampel === "green"
    ? "druckbar (grün) — die Prüf-Tür sah es frei"
    : ampel === "red"
      ? "nicht druckbar (rot) — Kollision oder Wand zu dick"
      : "ungeprüft — kein Druckbarkeits-Urteil (Altlauf, geänderter Schnittplan " +
        "oder fehlgeschlagene Prüfung). Kein ‚frei‘. Befund, kein Gate.";
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

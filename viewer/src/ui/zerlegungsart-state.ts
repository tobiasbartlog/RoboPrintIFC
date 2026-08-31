/**
 * Zerlegungsart-Weiche Abschnitte↔Module — reiner Zustand (Druckplan-Neuordnung
 * II S7, Issue #95, PRD #88, ADR-022). DOM-frei und vitest-getestet (wie
 * `focus-store.ts` / `parts-palette-state.ts`): hier liegen nur die
 * **Sichtbarkeitsmatrix** der artspezifischen Einstellungen und die
 * **Artwechsel-Regeln** (ADR-022 Punkt 5); das eigentliche Umblenden erledigt
 * die dünne DOM-Anbindung in `druckplan.ts` AUSSCHLIESSLICH über `.hidden`.
 *
 * Die zwei Zerlegungsarten (`core/CONTEXT.md`):
 * - **Abschnitt** (in place): vor Ort drucken, der Roboter wird umgesetzt —
 *   der Aufstell-Toggle (#81) steuert die erlaubten Podesthöhen.
 * - **Modul**: an der Workstation (dem Druckort, ADR-022) vorproduzieren und
 *   montieren — statt des Aufstell-Toggles gelten die optionalen Obergrenzen
 *   max. Modullänge/-höhe (#90).
 *
 * Artwechsel-Regeln (ADR-022 Punkt 5, BINDEND): Schnittebenen sind
 * zerlegungsart-**neutral** — ein Artwechsel behält den Schnittplan und setzt
 * nur das bestehende `dirty`-Flag (der debouncte Re-Check bewertet dieselbe
 * Geometrie mit der Logik der neuen Art). Slicing-Overrides
 * (`process_params.sections`) überleben den Wechsel (stabile Section-IDs);
 * Platzierungs-Overrides **verfallen** — ein Stellplatz am Einbauort ergibt an
 * der Workstation keinen Sinn.
 */

import type { Cut, SectionOverride, SectionProcessOverride } from "../api/projects";

/** Die zwei Zerlegungsarten (`core/CONTEXT.md`, ADR-022) — nie „Segmentierung". */
export type Zerlegungsart = "abschnitt" | "modul";

/** Robuste Normalisierung (Altprojekt/fehlendes Feld → „abschnitt"). */
export function normalizeZerlegungsart(value: string | null | undefined): Zerlegungsart {
  return value === "modul" ? "modul" : "abschnitt";
}

/**
 * Sichtbarkeitsmatrix der artspezifischen Einstellungen — als `.hidden`-Werte
 * formuliert, damit die DOM-Anbindung sie 1:1 zuweist (nie `style.display`,
 * Lehre aus #56): bei **Abschnitt** ist der Aufstell-Toggle (#81) sichtbar,
 * bei **Modul** die optionalen max-Maße-Felder (#90) — nie beide.
 */
export interface ArtVisibility {
  /** `.hidden` der Aufstell-Gruppe (Toggle Boden/erhöht, #81) — Abschnitt-only. */
  aufstellHidden: boolean;
  /** `.hidden` der Modulgrößen-Gruppe (max. Länge/Höhe, #90) — Modul-only. */
  moduleLimitsHidden: boolean;
}

/** Die Sichtbarkeitsmatrix der gewählten Art (siehe {@link ArtVisibility}). */
export function visibilityFor(art: Zerlegungsart): ArtVisibility {
  return {
    aufstellHidden: art !== "abschnitt",
    moduleLimitsHidden: art !== "modul",
  };
}

/** Überschrift der Teile-Palette je Art (Beschriftungs-Umschaltung, Issue #95). */
export function paletteTitle(art: Zerlegungsart): string {
  return art === "modul" ? "Module" : "Abschnitte";
}

/**
 * Anzeigename eines Teils je Art („Abschnitt 3" / „Modul 3"). Anzeige-Namen sind
 * Sache des Viewers — der Core-Schlüssel (`section_id`) bleibt bewusst
 * zerlegungsart-neutral stabil, damit Slicing-Overrides den Artwechsel
 * überleben (ADR-022 Punkt 5).
 */
export function partLabel(art: Zerlegungsart, order: number): string {
  return `${art === "modul" ? "Modul" : "Abschnitt"} ${order}`;
}

/**
 * Freundlicher Hinweis, wenn Art „modul" ohne Workstation am Druckjob gewählt
 * ist (die Workstation **ist** der Druckort, ADR-022) — sonst `null`. Ein
 * Hinweis, **kein Gate**: die Art bleibt wählbar, nur Vorschlag/Prüfung warten
 * auf die Workstation-Wahl.
 */
export function workstationHint(art: Zerlegungsart, hasWorkstation: boolean): string | null {
  if (art !== "modul" || hasWorkstation) return null;
  return (
    "Zerlegungsart Module braucht eine Workstation — sie ist der Druckort " +
    "(ADR-022): der Roboter sitzt fest an ihrer Basis, jedes Modul wird auf der " +
    "Arbeitsfläche stehend gedruckt. Bitte im Reiter Roboter eine Workstation wählen."
  );
}

/** Plan-Eingaben, auf die die Artwechsel-Regeln wirken (ADR-022 Punkt 5). */
export interface ArtSwitchInput {
  readonly cuts: readonly Cut[];
  readonly jointOffsetMm: number;
  readonly sectionOverrides: readonly SectionOverride[];
  /** Slicing-Overrides je Teil (`process_params.sections`, #82) — nur zur
   *  Regel-Dokumentation dabei: sie überleben den Wechsel unverändert. */
  readonly slicingSections?: Readonly<Record<string, SectionProcessOverride>>;
}

/** Ergebnis eines Artwechsels — der Plan derselben Geometrie, ungeprüft. */
export interface ArtSwitchResult {
  /** Regel 1: ALLE Schnittebenen bleiben erhalten (zerlegungsart-neutral). */
  cuts: Cut[];
  jointOffsetMm: number;
  /** Regel 3: Platzierungs-Overrides verfallen (immer leer). */
  sectionOverrides: SectionOverride[];
  /** Regel 2: Slicing-Overrides überleben unverändert (stabile Section-IDs). */
  slicingSections?: Record<string, SectionProcessOverride>;
  /** Der Plan ist nach dem Wechsel ungeprüft — der debouncte Re-Check bewertet
   *  ihn mit der Logik der neuen Art (bestehender `dirty`-Mechanismus, #25). */
  dirty: true;
}

/**
 * Wendet die Artwechsel-Regeln (ADR-022 Punkt 5) auf die Plan-Eingaben an:
 * Schnitte + Fugen-Versatz bleiben, Platzierungs-Overrides verfallen,
 * Slicing-Overrides bleiben unangetastet, der Plan wird ungeprüft (`dirty`).
 * Rein und deterministisch — die Persistenz der geräumten Overrides läuft über
 * den nächsten Re-Check (eine Schreibstelle `fgc.project`, ADR-016).
 */
export function switchArt(input: ArtSwitchInput): ArtSwitchResult {
  return {
    cuts: input.cuts.map((c) => ({ ...c })),
    jointOffsetMm: input.jointOffsetMm,
    sectionOverrides: [],
    slicingSections: input.slicingSections
      ? { ...input.slicingSections }
      : undefined,
    dirty: true,
  };
}

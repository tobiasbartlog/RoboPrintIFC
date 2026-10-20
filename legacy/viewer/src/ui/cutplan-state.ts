/**
 * Schnittplan-Zustandslogik (Issue #25) — reine TypeScript-Funktionen, ohne
 * three.js. Hält, was der Nutzer am Zerlegungsvorschlag ändert (Schnitte
 * hinzufügen/verschieben/entfernen, Fugen-Versatz, Platzierungs-Override je
 * Abschnitt) plus den ``dirty``-Zustand („ungeprüft" — AC #25): jede Änderung
 * setzt ``dirty = true``; erst eine erfolgreiche Neubewertung durch den Core
 * (`applyEvaluation`) setzt ihn wieder auf ``false`` und übernimmt die frischen
 * Abschnitte (Ampel + Geometrie + Platzierung).
 *
 * Drag (three.js, `render/cutplanes.ts`) und Zahlenfeld (`ui/druckplan.ts`)
 * rufen beide dieselbe `moveCut`-Funktion auf denselben Zustand auf — die
 * Synchronität fällt aus der Architektur, nicht aus Ad-hoc-Sync (Issue #25,
 * Architektur-Leitplanken). Die UI rechnet nie selbst (ADR-007): dieses Modul
 * kennt keine Kinematik/Ampel-Logik, nur Plan-Eingaben + Dirty-Flag.
 */

import type { Cut, DecompositionSection, SectionOverride } from "../api/projects";

export interface CutPlanState {
  /** Schnittebenen — Plan-Eingabe (Issue #24/#25). */
  cuts: Cut[];
  /** Fugen-Versatz zwischen Höhenlagen (Issue #25); wirkt nur auf vertikale Schnitte. */
  jointOffsetMm: number;
  /** Platzierungs-Override je Abschnitt (Issue #25): section_id -> option_id. */
  sectionOverrides: SectionOverride[];
  /** Letzter bekannter Core-Befund (Ampel + Geometrie + Platzierung je Abschnitt). */
  sections: DecompositionSection[];
  /**
   * true = seit der letzten Neubewertung durch den Core geändert („ungeprüft").
   * Hartes Kriterium (Issue #25 AC): niemals eine veraltete Ampel als aktuell
   * zeigen — die UI muss bei dirty=true die Ampel-Farben ausblenden/grau zeigen.
   */
  dirty: boolean;
}

/** Startzustand — optional mit einem bereits bekannten Stand (z. B. aus dem Druckjob). */
export function initCutPlanState(seed?: {
  cuts?: Cut[];
  jointOffsetMm?: number;
  sectionOverrides?: SectionOverride[];
  sections?: DecompositionSection[];
}): CutPlanState {
  return {
    cuts: seed?.cuts ? seed.cuts.map((c) => ({ ...c })) : [],
    jointOffsetMm: seed?.jointOffsetMm ?? 0,
    sectionOverrides: seed?.sectionOverrides ? seed.sectionOverrides.map((o) => ({ ...o })) : [],
    sections: seed?.sections ? seed.sections.map((s) => ({ ...s })) : [],
    // Ein wiederhergestellter Stand gilt als geprüft, solange er unverändert ist —
    // die zuletzt gespeicherten Abschnitte stammen ja aus dem referenzierten Lauf.
    dirty: false,
  };
}

/** Fügt eine neue Schnittebene hinzu — markiert den Plan als ungeprüft. */
export function addCut(state: CutPlanState, orientation: Cut["orientation"], positionMm: number): CutPlanState {
  return {
    ...state,
    cuts: [...state.cuts, { orientation, position_mm: positionMm }],
    dirty: true,
  };
}

/** Entfernt eine Schnittebene per Index — no-op bei ungültigem Index. */
export function removeCut(state: CutPlanState, index: number): CutPlanState {
  if (index < 0 || index >= state.cuts.length) return state;
  return {
    ...state,
    cuts: state.cuts.filter((_, i) => i !== index),
    dirty: true,
  };
}

/**
 * Verschiebt eine Schnittebene auf eine neue Position — von Drag (three.js)
 * *und* Zahlenfeld gleichermaßen aufgerufen (derselbe Zustand, Issue #25).
 * No-op bei ungültigem Index.
 */
export function moveCut(state: CutPlanState, index: number, positionMm: number): CutPlanState {
  if (index < 0 || index >= state.cuts.length) return state;
  // Unveränderte Position = No-op: darf weder dirty setzen noch den debounced
  // Core-Check auslösen (Issue #37 — bloßer Klick auf eine Ebene committet delta 0).
  if (state.cuts[index].position_mm === positionMm) return state;
  return {
    ...state,
    cuts: state.cuts.map((c, i) => (i === index ? { ...c, position_mm: positionMm } : c)),
    dirty: true,
  };
}

/** Setzt den Fugen-Versatz (Issue #25) — wirkt nur auf vertikale Schnitte zwischen Höhenlagen. */
export function setJointOffset(state: CutPlanState, jointOffsetMm: number): CutPlanState {
  return { ...state, jointOffsetMm, dirty: true };
}

/**
 * Weist einem Abschnitt eine Platzierung aus der Platzierungsliste zu
 * (`optionId`) oder hebt die Zuweisung auf (`optionId = null`). Freie
 * Platzierungswerte des Eintrags (Issue #94: seitlich/Abstand/Aufstellhöhe)
 * bleiben dabei erhalten — sie sind eine eigene, feldweise Ebene über der
 * Referenz und werden nur über ihre eigenen Felder (↺) geräumt.
 */
export function setSectionOverride(
  state: CutPlanState,
  sectionId: string,
  optionId: string | null,
): CutPlanState {
  const existing = state.sectionOverrides.find((o) => o.section_id === sectionId);
  const rest = state.sectionOverrides.filter((o) => o.section_id !== sectionId);
  let entry: SectionOverride | null;
  if (optionId === null) {
    // Referenz aufheben; freie Werte (#94) bleiben — sonst fällt der Eintrag weg.
    const { option_id: _drop, ...free } = existing ?? { section_id: sectionId };
    entry = hasFreeValues(free) ? { ...free } : null;
  } else {
    entry = { ...(existing ?? { section_id: sectionId }), option_id: optionId };
  }
  const sectionOverrides = entry === null ? rest : [...rest, entry];
  return { ...state, sectionOverrides, dirty: true };
}

/**
 * Ersetzt die Platzierungs-Overrides durch den frisch persistierten Stand des
 * Druckjobs (Issue #94): nach `PUT …/placement-override` hält der Panel-Zustand
 * so exakt das, was der Core gespeichert hat — die nächste „Prüfen"-Runde sendet
 * die Overrides unverändert zurück (kein Lost Update zwischen Setter und
 * Zerlegungs-Route). Markiert den Plan als ungeprüft (die Bewertung steht aus).
 */
export function replaceSectionOverrides(
  state: CutPlanState,
  overrides: SectionOverride[],
): CutPlanState {
  return {
    ...state,
    sectionOverrides: overrides.map((o) => ({ ...o })),
    dirty: true,
  };
}

/**
 * Markiert den Plan als ungeprüft, ohne eine Eingabe zu ändern (Issue #95):
 * gebraucht, wenn ein *außerhalb* des Schnittplans persistierter Parameter die
 * Bewertung beeinflusst (max. Modul-Obergrenzen, #90) — der debouncte Re-Check
 * holt danach den frischen Befund. Kein No-op-Schutz nötig: der Aufrufer
 * entscheidet, wann eine Neubewertung ansteht.
 */
export function markUnchecked(state: CutPlanState): CutPlanState {
  return { ...state, dirty: true };
}

/** true, wenn ein Eintrag (ohne section_id betrachtet) freie Werte trägt (#94). */
function hasFreeValues(entry: Partial<SectionOverride>): boolean {
  return (["lateral_mm", "standoff_mm", "stand_height_mm"] as const).some(
    (f) => typeof entry[f] === "number" && Number.isFinite(entry[f]),
  );
}

/** Die aktuell zugewiesene option_id eines Abschnitts, falls vorhanden. */
export function overrideFor(state: CutPlanState, sectionId: string): string | null {
  return state.sectionOverrides.find((o) => o.section_id === sectionId)?.option_id ?? null;
}

/**
 * Übernimmt das Ergebnis einer Core-Neubewertung („Prüfen"): frische Abschnitte
 * (Ampel + Geometrie + Platzierung), Plan gilt wieder als geprüft (dirty=false).
 * Dies ist die *einzige* Stelle, an der dirty auf false gesetzt wird — die UI
 * rechnet nie selbst (ADR-007).
 */
export function applyEvaluation(state: CutPlanState, sections: DecompositionSection[]): CutPlanState {
  return { ...state, sections, dirty: false };
}

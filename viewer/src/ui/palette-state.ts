/**
 * ⌘K-Befehlspalette (UI-Redesign Scheibe 9, Issue #109) — reine, DOM-freie
 * Zustandslogik: die statische **Registry** aller such-/anspringbaren
 * Einstellungen und Aktionen über die 5-Schritt-Struktur plus die Filterlogik.
 * Wie die anderen `*-state.ts` (theme.ts, stepper-state.ts, scope-state.ts) hält
 * dieses Modul nur Daten + reine Funktionen; das DOM-Overlay und die Ausführung
 * (Reiter wechseln, Accordion öffnen, Feld fokussieren, Aktion auslösen) liegen
 * in `ui/palette.ts`.
 *
 * Ein Registry-Eintrag beschreibt sein Ziel **deklarativ** (`PaletteTarget`) —
 * welche der vier Wirkungen (Reiter, Accordion, Feld, Aktions-Button bzw.
 * Sonderaktion Theme) beim Ausführen greifen, entscheidet allein, welche Felder
 * gesetzt sind. So bleibt die Registry frei von three.js/DOM und getrennt
 * testbar (`palette-state.test.ts`); die echten Element-IDs sind hier bloß
 * Strings, deren Existenz der DOM-Vertrag (`palette-dom.test.ts`) gegen die
 * index.html absichert.
 */

import type { TabId } from "./tabs";

/**
 * Das deklarative Ziel eines Palette-Eintrags. `palette.ts` führt es in fester
 * Reihenfolge aus: Reiter wechseln → Accordion öffnen → Feld fokussieren →
 * Aktions-Button klicken; `special: "theme"` schaltet stattdessen das Theme.
 * Alle Felder außer der Wirkung selbst sind optional — ein reiner Navigations-
 * Eintrag setzt nur `tab`, eine Aktion nur `actionButtonId` (+ ggf. `tab`).
 */
export interface PaletteTarget {
  /** Reiter, den das Ausführen aktiviert (via `shell.setActiveTab`). Fehlt nur bei `special`. */
  tab?: TabId;
  /**
   * Toggle-Button-ID des Accordions, das geöffnet werden soll. `palette.ts`
   * klickt ihn nur, wenn er `aria-expanded="false"` trägt — so bleibt der
   * Aufklapp-Zustand des besitzenden Panels konsistent (kein direktes `.hidden`).
   */
  accordionToggleId?: string;
  /** Feld, das nach der Navigation fokussiert wird (`focus()` + `scrollIntoView`). */
  fieldId?: string;
  /** Button, dessen **bestehender** Klick-Handler ausgelöst wird (`.click()`). */
  actionButtonId?: string;
  /** Sonderaktion ohne DOM-Button: `"theme"` kippt hell/dunkel (`fgcToggleTheme`). */
  special?: "theme";
}

/** Ein Eintrag der Befehlspalette: Icon | Label | Gruppe (rechts) + Ziel. */
export interface PaletteEntry {
  /** Stabiler Schlüssel (Tests/Deeplinks). */
  id: string;
  /** Ein-Zeichen-Icon (Prototyp-Stil: ≡ ∠ » ▦ ✦ ✓ ▶ ⌁ ▤ ◐). */
  icon: string;
  /** Klartext der Einstellung/Aktion (die Hauptsuchspalte). */
  label: string;
  /** Rechts stehende Gruppe („Slicing · Prozessparameter", „Zerlegung · Aktion", …). */
  group: string;
  /** Deklaratives Ziel — was das Ausführen bewirkt. */
  target: PaletteTarget;
}

/**
 * Die statische Registry: jede Einstellung und Aktion über die fünf
 * Prozess-Schritte (Projekt, Roboter, Zerlegung, Slicing, Export) plus die
 * Bibliothek und die Ansicht (Theme). Die Element-IDs sind grep-verifiziert
 * gegen `index.html` (siehe Inventar Issue #109). Reihenfolge = Anzeige-
 * Reihenfolge bei leerer Suche.
 */
export const PALETTE_REGISTRY: PaletteEntry[] = [
  // --- Projekt --------------------------------------------------------------
  { id: "projekt-open", icon: "▤", label: "Projekt / Modellübersicht", group: "Projekt", target: { tab: "projekt" } },
  { id: "projekt-context", icon: "▦", label: "Gebäudekontext ein-/ausblenden", group: "Projekt", target: { tab: "projekt", fieldId: "show-context" } },
  { id: "projekt-slice-wall", icon: "✦", label: "Gewählte Wand slicen", group: "Projekt · Aktion", target: { tab: "projekt", actionButtonId: "slice-wall-btn" } },
  { id: "projekt-adopt-job", icon: "✦", label: "Wand in Druckjob übernehmen", group: "Projekt · Aktion", target: { tab: "projekt", actionButtonId: "adopt-job-btn" } },

  // --- Roboter --------------------------------------------------------------
  { id: "roboter-select", icon: "⌁", label: "Roboter wählen", group: "Roboter", target: { tab: "roboter", fieldId: "robot-select" } },
  { id: "roboter-tool", icon: "⌁", label: "Endeffektor wählen", group: "Roboter", target: { tab: "roboter", fieldId: "tool-select" } },
  { id: "roboter-workstation", icon: "⌁", label: "Workstation wählen", group: "Roboter", target: { tab: "roboter", fieldId: "wsc-select" } },
  { id: "roboter-schema", icon: "⌁", label: "Schema-Darstellung des Arms", group: "Roboter", target: { tab: "roboter", fieldId: "arm-schema-toggle" } },
  { id: "roboter-save", icon: "✓", label: "Roboter-Auswahl speichern", group: "Roboter · Aktion", target: { tab: "roboter", actionButtonId: "robot-step-save-btn" } },
  { id: "roboter-reassess", icon: "✦", label: "Alle Wände neu bewerten", group: "Roboter · Aktion", target: { tab: "roboter", actionButtonId: "robot-reassess-btn" } },

  // --- Zerlegung ------------------------------------------------------------
  { id: "zerlegung-art", icon: "▦", label: "Zerlegungsart (Abschnitte ↔ Module)", group: "Zerlegung · Art & Aufstellung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-art-toggle", fieldId: "zerlegungsart-abschnitt" } },
  { id: "zerlegung-aufstell", icon: "▦", label: "Aufstellung (Boden ↔ erhöht)", group: "Zerlegung · Art & Aufstellung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-art-toggle", fieldId: "aufstell-floor" } },
  { id: "zerlegung-max-length", icon: "▦", label: "Modulgröße max. Länge (mm)", group: "Zerlegung · Art & Aufstellung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-art-toggle", fieldId: "module-max-length" } },
  { id: "zerlegung-max-height", icon: "▦", label: "Modulgröße max. Höhe (mm)", group: "Zerlegung · Art & Aufstellung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-art-toggle", fieldId: "module-max-height" } },
  { id: "zerlegung-joint-offset", icon: "▦", label: "Fugen-Versatz (mm)", group: "Zerlegung · Schnittplan", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-cuts-toggle", fieldId: "decompose-joint-offset" } },
  { id: "zerlegung-add-horizontal", icon: "▦", label: "Höhenschnitt hinzufügen", group: "Zerlegung · Schnittplan", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-cuts-toggle", actionButtonId: "decompose-add-horizontal-btn" } },
  { id: "zerlegung-add-vertical", icon: "▦", label: "Längsschnitt hinzufügen", group: "Zerlegung · Schnittplan", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-cuts-toggle", actionButtonId: "decompose-add-vertical-btn" } },
  { id: "zerlegung-lateral", icon: "▦", label: "Platzierung: Seitlich (mm)", group: "Zerlegung · Platzierung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-placement-toggle", fieldId: "placement-override-lateral" } },
  { id: "zerlegung-standoff", icon: "▦", label: "Platzierung: Abstand vor der Wand (mm)", group: "Zerlegung · Platzierung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-placement-toggle", fieldId: "placement-override-standoff" } },
  { id: "zerlegung-standheight", icon: "▦", label: "Platzierung: Aufstellhöhe ü. Boden (mm)", group: "Zerlegung · Platzierung", target: { tab: "zerlegung", accordionToggleId: "zerlegung-acc-placement-toggle", fieldId: "placement-override-standheight" } },
  { id: "zerlegung-auto", icon: "✦", label: "Zerlegung automatisch vorschlagen", group: "Zerlegung · Aktion", target: { tab: "zerlegung", actionButtonId: "zerlegung-auto-btn" } },
  { id: "zerlegung-check", icon: "✓", label: "Schnittplan prüfen lassen", group: "Zerlegung · Aktion", target: { tab: "zerlegung", actionButtonId: "decompose-check-btn" } },

  // --- Slicing (interner Reiter „druckplan") --------------------------------
  { id: "slicing-scope", icon: "≡", label: "Geltungsbereich (Global ↔ Teil)", group: "Slicing", target: { tab: "druckplan", fieldId: "scope-global" } },
  { id: "slicing-layer-height", icon: "≡", label: "Schichthöhe (mm)", group: "Slicing · Prozessparameter", target: { tab: "druckplan", accordionToggleId: "slicing-acc-prozess-toggle", fieldId: "process-params-layer-height" } },
  { id: "slicing-strand-width", icon: "≡", label: "Strangbreite (mm)", group: "Slicing · Prozessparameter", target: { tab: "druckplan", accordionToggleId: "slicing-acc-prozess-toggle", fieldId: "process-params-strand-width" } },
  { id: "slicing-shells", icon: "≡", label: "Schalen", group: "Slicing · Prozessparameter", target: { tab: "druckplan", accordionToggleId: "slicing-acc-prozess-toggle", fieldId: "process-params-shells" } },
  { id: "slicing-lead-deg", icon: "∠", label: "Lead/Lag (°) — Anstellwinkel", group: "Slicing · Prozessparameter", target: { tab: "druckplan", accordionToggleId: "slicing-acc-prozess-toggle", fieldId: "process-params-lead-deg" } },
  { id: "slicing-kipp-deg", icon: "∠", label: "Kipp (°) — Anstellwinkel", group: "Slicing · Prozessparameter", target: { tab: "druckplan", accordionToggleId: "slicing-acc-prozess-toggle", fieldId: "process-params-kipp-deg" } },
  { id: "slicing-v-print", icon: "»", label: "Druck-Geschwindigkeit (mm/s)", group: "Slicing · Fortgeschritten", target: { tab: "druckplan", accordionToggleId: "process-params-advanced-toggle", fieldId: "process-params-v-print" } },
  { id: "slicing-v-travel", icon: "»", label: "Travel-Geschwindigkeit (mm/s)", group: "Slicing · Fortgeschritten", target: { tab: "druckplan", accordionToggleId: "process-params-advanced-toggle", fieldId: "process-params-v-travel" } },
  { id: "slicing-io-print", icon: "»", label: "io Druck", group: "Slicing · Fortgeschritten", target: { tab: "druckplan", accordionToggleId: "process-params-advanced-toggle", fieldId: "process-params-io-print" } },
  { id: "slicing-io-travel", icon: "»", label: "io Travel", group: "Slicing · Fortgeschritten", target: { tab: "druckplan", accordionToggleId: "process-params-advanced-toggle", fieldId: "process-params-io-travel" } },
  { id: "slicing-advisor-check", icon: "✦", label: "Singularität prüfen", group: "Slicing · Advisor", target: { tab: "druckplan", accordionToggleId: "slicing-acc-advisor-toggle", actionButtonId: "singularity-advisor-check-btn" } },
  { id: "slicing-advisor-apply", icon: "✓", label: "Advisor-Vorschlag anwenden", group: "Slicing · Advisor", target: { tab: "druckplan", accordionToggleId: "slicing-acc-advisor-toggle", actionButtonId: "singularity-advisor-apply-btn" } },
  { id: "slicing-save", icon: "✓", label: "Slicing speichern", group: "Slicing · Aktion", target: { tab: "druckplan", actionButtonId: "process-params-save-btn" } },

  // --- Simulation (Dock am Fuß des Druckplan-Sichtfelds) --------------------
  { id: "sim-focus", icon: "▶", label: "Fokus-Abschnitt simulieren", group: "Simulation · Aktion", target: { tab: "druckplan", actionButtonId: "sim-focus-btn" } },
  { id: "sim-sequence", icon: "▶", label: "Ganze Wand simulieren (unten → oben)", group: "Simulation · Aktion", target: { tab: "druckplan", actionButtonId: "sim-sequence-btn" } },
  { id: "sim-play", icon: "▶", label: "Simulation abspielen / pausieren", group: "Simulation", target: { tab: "druckplan", actionButtonId: "sim-play-btn" } },

  // --- Export ---------------------------------------------------------------
  { id: "export-open", icon: "⤓", label: "Export / Roboterprogramme", group: "Export", target: { tab: "export" } },

  // --- Bibliothek -----------------------------------------------------------
  { id: "bibliothek-open", icon: "▤", label: "Bibliothek öffnen", group: "Bibliothek", target: { tab: "bibliothek" } },
  { id: "bibliothek-new-tool", icon: "✦", label: "Neuer Endeffektor", group: "Bibliothek · Aktion", target: { tab: "bibliothek", actionButtonId: "lib-new-btn" } },
  { id: "bibliothek-new-workstation", icon: "✦", label: "Neue Workstation", group: "Bibliothek · Aktion", target: { tab: "bibliothek", actionButtonId: "ws-new-btn" } },

  // --- Ansicht --------------------------------------------------------------
  { id: "ansicht-theme", icon: "◐", label: "Theme umschalten (hell/dunkel)", group: "Ansicht", target: { special: "theme" } },
];

/** Standard-Obergrenze der angezeigten Treffer (wie Prototyp). */
export const PALETTE_RESULT_LIMIT = 9;

/** Normalisiert die Sucheingabe: getrimmt + kleingeschrieben. */
export function normalizeQuery(query: string): string {
  return query.trim().toLowerCase();
}

/** true, wenn `needle` als (nicht zwingend zusammenhängende) Teilfolge in `haystack` steckt. */
function subsequenceMatch(haystack: string, needle: string): boolean {
  let i = 0;
  for (let h = 0; h < haystack.length && i < needle.length; h++) {
    if (haystack[h] === needle[i]) i++;
  }
  return i === needle.length;
}

/**
 * Bewertet einen Eintrag gegen die (bereits normalisierte) Suche. `null` =
 * kein Treffer. Kleinere Werte ranken höher: leere Suche = 0 (Registry-
 * Reihenfolge bleibt), Substring nach Trefferposition (früh = besser),
 * Fuzzy-Teilfolge als schwächerer Fallback (großer Offset).
 */
export function scoreEntry(entry: PaletteEntry, normalizedQuery: string): number | null {
  if (normalizedQuery === "") return 0;
  const hay = `${entry.label} ${entry.group}`.toLowerCase();
  const idx = hay.indexOf(normalizedQuery);
  if (idx !== -1) return idx;
  if (subsequenceMatch(hay, normalizedQuery)) return 1000;
  return null;
}

/**
 * Die reine Filterlogik: liefert die passenden Einträge, nach Relevanz sortiert
 * (stabil bei Gleichstand über die Registry-Reihenfolge) und auf `limit`
 * gekürzt. Leere Suche = alle Einträge in Registry-Reihenfolge.
 */
export function filterPalette(
  entries: PaletteEntry[],
  query: string,
  limit: number = PALETTE_RESULT_LIMIT,
): PaletteEntry[] {
  const q = normalizeQuery(query);
  const scored: { entry: PaletteEntry; score: number; order: number }[] = [];
  entries.forEach((entry, order) => {
    const score = scoreEntry(entry, q);
    if (score !== null) scored.push({ entry, score, order });
  });
  scored.sort((a, b) => a.score - b.score || a.order - b.order);
  return scored.slice(0, limit).map((s) => s.entry);
}

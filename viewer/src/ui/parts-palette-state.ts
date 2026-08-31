/**
 * Teile-Palette am 3D-Feld — reiner Zustand (Druckplan-Neuordnung II S2, Issue
 * #91, PRD #88). DOM-frei und vitest-getestet (wie `focus-store.ts` /
 * `rubrics-state.ts`): hier liegt nur die **Ableitung** der Palette-Einträge aus
 * den Abschnitten (Ampel, erreichbarer Anteil, ▪-Marker) und die Marker-Quelle
 * (welche Teile einen Slicing-Override tragen). Das eigentliche Zeichnen +
 * Ein-/Ausklappen erledigt die dünne DOM-Klasse `parts-palette.ts`.
 *
 * **Auswahl ↔ Fokus:** die Palette hält KEINEN eigenen Auswahlzustand — die
 * Auswahl *ist* der Fokus-Abschnitt (`focus-store.ts`, #84). Ein Palette-Eintrag
 * gilt genau dann als gewählt, wenn er die fokussierte `section_id` trägt; der
 * Klick in der Palette läuft durch dieselbe `toggleFocus`-Logik wie der 3D-Klick
 * (kein paralleler Zustand). So bleiben Palette und 3D-Fokus beidseitig synchron,
 * und ein Fokus-Wegfall (neue Zerlegung, `reconcileFocus`) räumt die Auswahl mit.
 *
 * **Kollisionsbadge veraltet mit den übrigen Badges (Issue #182):** das Badge
 * entwertet nicht mehr nur hart auf `null` (dirty, #172), sondern trägt zusätzlich
 * `stale` aus derselben `sectionStageStatus`-Ableitung (`staleness.ts`) wie
 * Druckplan-/Simulation-/Export-Badge — eine Parameter-/Platzierungs-/Kipp-Änderung
 * seit der letzten Simulation dieses Teils veraltet den Befund sichtbar, statt ihn
 * kommentarlos als aktuell zu zeigen.
 */

import type {
  DecompositionSection,
  ModuleCheck,
  SectionOverride,
  SectionProcessOverride,
} from "../api/projects";
import type { CollisionMeta } from "../artifacts/types";
import { collisionBadge, type CollisionBadge } from "./collision-state";
import { effectivePlacement } from "./effective-placement";
import { type PrintabilityView, printabilityView } from "./printability-state";
import { isStale, type Revisions, sectionStageStatus } from "./staleness";
import { partLabel, type Zerlegungsart } from "./zerlegungsart-state";

/** Kollisions-Badge eines Teils samt Veraltet-Markierung (Issue #182) — additiv zu
 *  {@link CollisionBadge}: `stale` sagt, ob das zugrundeliegende Simulationsergebnis
 *  gegenüber dem aktuellen Stand (Parameter-/Platzierungs-/Kipp-Änderung) veraltet
 *  ist — dieselbe Ableitung wie die übrigen Stufen-Badges (`sectionStageStatus`,
 *  `staleness.ts`). Bleibt sichtbar, wird nur markiert (kein Löschen). */
export interface PartCollisionBadge extends CollisionBadge {
  stale: boolean;
}

/** Ampel-Zustand eines Teils in der Palette. */
export type PartAmpel = "green" | "red" | "ungeprueft";

/** Ein abgeleiteter Palette-Eintrag — reine Anzeigedaten, kein DOM. */
export interface PartEntry {
  section_id: string;
  /** 1-basierte Druckreihenfolge (unten → oben). */
  order: number;
  /** Anzeigename in der Palette je Zerlegungsart („Abschnitt 1" / „Modul 1",
   *  Issue #95) — die stabile `section_id` bleibt der Schlüssel (ADR-022). */
  name: string;
  /** Die Ampel spiegelt seit #164 die **Druckbarkeit** (Core-Urteil): grün nur, was
   *  die Prüf-Tür frei sah; rot bei Kollision/zu dick. Fehlt das Urteil (Altlauf) oder
   *  ist es „ungeprüft" (unknown), steht „ungeprueft" — NICHT die Erreichbarkeit
   *  (Issue #170, B35). „ungeprueft" auch bei dirty. */
  ampel: PartAmpel;
  /** Druckbarkeits-Urteil je Teil (Issue #164/#170): Kurztext + Schweregrad
   *  (ok/bad/unknown) + ,vermutlich', reine Anzeige aus `printability-state`. `null`
   *  nur, wenn das Teil gar kein Urteil-Feld trägt (Altlauf) oder bei dirty — dann
   *  zeigt der Aufrufer „ungeprüft" über die Ampel. */
  printability: PrintabilityView | null;
  /** Erreichbarer Wandanteil ∈ [0, 1]. */
  reachable_fraction: number;
  /** Kinematische Marge (Singularitätsnähe) aus dem Core-Artefakt; `null` = keine. */
  kinematic_margin: number | null;
  /** Platzierungswerte des Teils (Core-Artefakt, ADR-022): seitlich/Abstand/Aufstellhöhe. */
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
  /** ▪-Marker: trägt das Teil individuelle Overrides (Slicing oder Platzierung, #94)? */
  has_override: boolean;
  /** true, wenn dieses Teil gerade gewählt/fokussiert ist. */
  selected: boolean;
  /** Modulgrenzen-Befund (Issue #90/#95, nur Art „modul"): Gewicht (kg) +
   *  Befund je gesetzter Obergrenze — verbatim aus dem Core-Artefakt (ADR-007),
   *  **Befund, kein Gate**. `null` bei Art „abschnitt"/Altlauf. */
  module_check: ModuleCheck | null;
  /** Kollisions-Badge des Teil-Laufs (Kollisionskontrolle S3, US 12, #128) —
   *  verbatim aus `meta.collision` des Laufs; `null`, wenn das Teil (noch) keinen
   *  Befund trägt (Altlauf / nicht simuliert) oder der Plan dirty ist (der alte
   *  Befund gälte der alten Platzierung, #172/B20). Die Platzierungs-Ampel bleibt
   *  davon unangetastet (getrennter Kanal, Regressionsanker). Trägt zusätzlich
   *  `stale` (Issue #182): eine Parameter-/Platzierungs-/Kipp-Änderung NACH der
   *  letzten Simulation veraltet den Befund, ohne ihn zu löschen (sichtbar bleiben,
   *  markiert werden — konsistent zu den übrigen Badges). */
  collision_badge: PartCollisionBadge | null;
}

/** Eingabe der Palette-Ableitung. */
export interface PartsPaletteInput {
  readonly sections: readonly DecompositionSection[];
  /** Schnittplan geändert, noch nicht neu bewertet → alle Ampeln „ungeprüft". */
  readonly dirty: boolean;
  /** Die fokussierte `section_id` (= Auswahl) oder `null` (keine). */
  readonly focusedSectionId: string | null;
  /** section_ids mit einem Override — Slicing (`slicingOverrideSectionIds`) und/oder
   *  Platzierung (`placementOverrideSectionIds`, Issue #94) — als Marker-Quelle. */
  readonly overrideSectionIds: readonly string[];
  /** Zerlegungsart (Issue #95): schaltet die Teil-Namen („Abschnitt"/„Modul");
   *  fehlt sie (Altaufrufer), gilt „abschnitt". */
  readonly kind?: Zerlegungsart;
  /** Kollisions-Befund je `section_id` (Kollisionskontrolle S3, US 12, #128) —
   *  aus `meta.collision` des jeweiligen Teil-Laufs. Fehlt (Altaufrufer, kein
   *  simuliertes Teil) ⇒ kein Badge, Status quo. */
  readonly collisionBySectionId?: Readonly<Record<string, CollisionMeta | undefined>>;
  /** Persistierte Platzierungs-Overrides des aktiven Jobs (`section_overrides`,
   *  Issue #161): gesetzte freie Felder ersetzen in der Karten-Zeile
   *  „Platzierung: …" sparse die Zerlegungs-Werte. Fehlt (Altaufrufer) ⇒
   *  Werte verbatim aus dem Zerlegungslauf, Status quo. */
  readonly placementOverrides?: readonly SectionOverride[];
  /** Revisionsstände des Druckjobs (Issue #182): speist die Veraltet-Markierung
   *  des Kollisions-Badges — dieselbe Ableitung (`sectionStageStatus`/`isStale`,
   *  Simulations-Stufe) wie die übrigen Stufen-Badges (Druckplan/Simulation/Export,
   *  `staleness.ts`). Fehlt sie (Altaufrufer) ⇒ nichts gilt als veraltet
   *  (rückwärtskompatibel, Status quo).
   */
  readonly revisions?: Revisions;
}

/**
 * Leitet die Palette-Einträge aus den Abschnitten ab (in Druckreihenfolge). Die
 * Ampel ist „ungeprüft", solange der Schnittplan geändert (dirty) und noch nicht
 * neu bewertet ist — sonst grün/rot nach dem Erreichbarkeits-Befund. Der ▪-Marker
 * setzt sich aus `overrideSectionIds`, die Auswahl aus `focusedSectionId`.
 */
export function paletteEntries(input: PartsPaletteInput): PartEntry[] {
  const overrides = new Set(input.overrideSectionIds);
  const kind = input.kind ?? "abschnitt";
  // Override-Eintrag je Teil für die ehrliche Platzierungs-Zeile (Issue #161).
  const placementOverrideById = new Map(
    (input.placementOverrides ?? []).map((o) => [o.section_id, o]),
  );
  return [...input.sections]
    .sort((a, b) => a.order - b.order)
    .map((s) => {
      // Druckbarkeits-Urteil (Issue #164/#170): grün NUR, was die Prüf-Tür frei sah;
      // rot bei Kollision/zu dick. Fehlt das Urteil (Altlauf vor #164) ODER ist es
      // „ungeprüft" (unknown — keine Geometrie/Prüffehler), zeigt die Ampel
      // „ungeprüft" — NICHT mehr die alte Erreichbarkeits-Anzeige (Issue #170, B35;
      // die Erreichbarkeit bleibt als eigene „erreichbar N %"-Zeile sichtbar). Bei
      // dirty (Schnittplan geändert) ebenso „ungeprüft". Befund, kein Gate (ADR-013).
      const pView = input.dirty ? null : printabilityView(s.printability);
      const ampel: PartAmpel = input.dirty
        ? "ungeprueft"
        : pView
          ? pView.severity === "ok"
            ? "green"
            : pView.severity === "bad"
              ? "red"
              : "ungeprueft"
          : "ungeprueft";
      return {
      section_id: s.section_id,
      order: s.order,
      // Anzeigename je Zerlegungsart (Issue #95, ADR-022: Namen sind Sache des
      // Viewers, die section_id bleibt der stabile Schlüssel).
      name: partLabel(kind, s.order),
      ampel,
      printability: pView,
      reachable_fraction: s.status.reachable_fraction,
      // Bewertung + Platzierung kommen verbatim aus dem Core-Artefakt (ADR-007) —
      // reine Anzeige, keine Viewer-Ableitung (Issue #93). Einzige Ausnahme
      // (Issue #161): trägt der aktive Job einen Platzierungs-Override, ersetzen
      // dessen gesetzte Felder die (ggf. veralteten) Zerlegungs-Werte sparse —
      // die Karte sagt dann, womit die nächste Simulation wirklich rechnet.
      kinematic_margin: s.status.kinematic_margin,
      ...placementDisplayValues(s.placement, placementOverrideById.get(s.section_id)),
      has_override: overrides.has(s.section_id),
      selected: input.focusedSectionId === s.section_id,
      // Kollisions-Badge verbatim aus dem Lauf-Artefakt (Issue #128). Bei dirty
      // (Schnittplan/Platzierungs-Override geändert, noch nicht neu bewertet, auch
      // über den Advisor-Anwenden-Pfad, Issue #172) wird es wie Ampel und
      // Druckbarkeits-Urteil auf „ungeprüft" entwertet — der alte Kollisionsbefund
      // gilt der alten Platzierung (B11/B20/B32). Sonst verbatim aus `meta.collision`,
      // zusätzlich mit der Veraltet-Markierung (Issue #182): dieselbe Ableitung wie
      // die übrigen Badges (`sectionStageStatus`, Stufe „simulation") — eine
      // Parameter-/Platzierungs-/Kipp-Änderung seit der letzten Simulation dieses
      // Teils veraltet den Befund, ohne ihn zu löschen.
      collision_badge: collisionBadgeEntry(input, s.section_id),
      // Modulgrenzen-Befund verbatim aus dem Core-Artefakt (Issue #90/#95):
      // Gewicht + Grenzen — Befund, kein Gate; fehlt bei Art „abschnitt".
      module_check: s.module_check ?? null,
      };
    });
}

/**
 * Kollisions-Badge eines Teils samt Veraltet-Markierung (Issue #182). `dirty`
 * entwertet weiterhin hart auf `null` (#172/B20 — der alte Befund gälte der alten
 * Platzierung, deren Form sich mit dem laufenden Edit noch ändern kann). Sonst
 * verbatim aus `meta.collision`, mit `stale` aus derselben Ableitung wie die
 * übrigen Stufen-Badges (`sectionStageStatus`, Stufe „simulation" — dieselben
 * Job-Eingaben: Wand/Roboter/Endeffektor/Schnittplan/Parameter/Workstation, plus
 * der Abschnitts-Zähler für Platzierungs-Overrides). Fehlen `revisions`
 * (Altaufrufer), gilt nichts als veraltet (Status quo).
 */
function collisionBadgeEntry(
  input: PartsPaletteInput,
  sectionId: string,
): PartCollisionBadge | null {
  if (input.dirty) return null;
  const badge = collisionBadge(input.collisionBySectionId?.[sectionId]);
  if (!badge) return null;
  return {
    ...badge,
    stale: isStale(sectionStageStatus(input.revisions, sectionId, "simulation")),
  };
}

/** Die drei Platzierungswerte der Karten-Zeile „Platzierung: …" (Issue #161). */
export interface PlacementDisplayValues {
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
}

/**
 * Ehrliche Platzierungswerte eines Teils (Issue #161): trägt der aktive Job
 * einen `section_overrides`-Eintrag, ersetzen dessen **gesetzte (endliche)
 * freie Felder** sparse die Werte der Zerlegungs-Platzierung — die Karte zeigt
 * dann die Platzierung, mit der die nächste Simulation wirklich rechnet, auch
 * wenn der Zerlegungslauf noch die alte Lage trägt (z. B. nach „Anwenden" eines
 * Placement-Hebels, #130/#65). Eine reine `option_id`-Referenz (#25) ohne freie
 * Werte ändert nichts (ihre Werte kennt nur der Core, ADR-007); nicht-endliche
 * Werte übersteuern nie. Reine Funktion, deterministisch.
 */
export function placementDisplayValues(
  placement: PlacementDisplayValues,
  override: SectionOverride | undefined,
): PlacementDisplayValues {
  // Einquelligkeit (Issue #171): die Karten-Zeile bezieht die Platzierung aus
  // demselben Selektor wie alle anderen Leser — kein eigener Override-Merge mehr.
  const eff = effectivePlacement(placement, override);
  return {
    lateral_mm: eff.lateral_mm,
    standoff_mm: eff.standoff_mm,
    stand_height_mm: eff.stand_height_mm,
  };
}

/**
 * Anzeigetext des Modulgrenzen-Befunds eines Teils (Issue #95): Gewicht in kg
 * plus je Obergrenze der Befund — alles verbatim aus dem Core-Artefakt
 * (ADR-007, **Befund, kein Gate**). Ohne gesetzte Obergrenzen steht nur das
 * Gewicht; verletzte Grenzen werden benannt (Ist > Grenze in mm).
 */
export function moduleCheckLine(check: ModuleCheck): string {
  const parts = [`Gewicht ${check.weight_kg.toFixed(1)} kg`];
  const exceeded = check.limits.filter((f) => f.exceeded);
  if (exceeded.length > 0) {
    for (const f of exceeded) {
      const label = f.limit === "max_length" ? "max. Länge" : "max. Höhe";
      parts.push(
        `${label} überschritten (${Math.round(f.actual_mm)} > ${Math.round(f.limit_mm)} mm)`,
      );
    }
  } else if (check.limits.length > 0) {
    parts.push("Grenzen eingehalten");
  }
  return parts.join(" · ");
}

/**
 * Marker-Ableitung (#82): welche `section_id`s tragen in `process_params.sections`
 * einen tatsächlichen Slicing-Override? Ein Teil zählt, sobald seine `slice`- oder
 * `orientation`-Gruppe mindestens ein gesetztes (endliches) Feld hat — leere
 * Blöcke (Altprojekt, zurückgesetzt) erzeugen keinen Marker. Ergebnis sortiert
 * (stabil, für sparsame Vergleiche).
 */
export function slicingOverrideSectionIds(
  sections: Record<string, SectionProcessOverride> | undefined,
): string[] {
  if (!sections) return [];
  const ids: string[] = [];
  for (const [sectionId, override] of Object.entries(sections)) {
    if (overrideHasValue(override)) ids.push(sectionId);
  }
  return ids.sort();
}

function overrideHasValue(override: SectionProcessOverride | undefined): boolean {
  if (!override) return false;
  return groupHasValue(override.slice) || groupHasValue(override.orientation);
}

function groupHasValue(group: object | undefined): boolean {
  if (!group) return false;
  return Object.values(group).some((v) => typeof v === "number" && Number.isFinite(v));
}

/**
 * Marker-Ableitung Platzierung (Issue #94): welche `section_id`s tragen in
 * `section_overrides` einen tatsächlichen Platzierungs-Override — eine
 * `option_id`-Referenz (Issue #25) und/oder mindestens ein gesetztes (endliches)
 * freies Feld (seitlich/Abstand/Aufstellhöhe)? Der ▪-Marker der Palette zählt
 * sie zusammen mit den Slicing-Overrides (`slicingOverrideSectionIds`).
 * Ergebnis sortiert und dedupliziert (stabil, für sparsame Vergleiche).
 */
export function placementOverrideSectionIds(
  overrides: readonly SectionOverride[] | undefined,
): string[] {
  if (!overrides) return [];
  const ids = new Set<string>();
  for (const entry of overrides) {
    const hasReference = typeof entry.option_id === "string" && entry.option_id !== "";
    const hasFreeValue = (["lateral_mm", "standoff_mm", "stand_height_mm"] as const).some(
      (f) => typeof entry[f] === "number" && Number.isFinite(entry[f]),
    );
    if (hasReference || hasFreeValue) ids.add(entry.section_id);
  }
  return [...ids].sort();
}

/**
 * Kollisions-Advisor — reine, DOM-freie Darstellungs- und Anwenden-Logik
 * (Issue #130, ADR-024 Punkt 5; Spiegel von `singularity-advisor-state.ts`).
 *
 * Der Core urteilt (`POST …/collision-advice`, teuer: je Kandidat eine
 * Neu-Simulation) und liefert eine **gerankte Optionsliste** (das „Menü") — anders
 * als der Singularitäts-Advisor also mehrere Vorschläge. Der Viewer *setzt* nur
 * (ADR-007): hier liegt die Umrechnung Core-Option → Anzeigezeile und Core-Option →
 * **Anwenden-Aktion** über die *bestehenden* Schreib-Routen. Kein eigener
 * Fachzustand, keine eigene Kollisionsrechnung.
 *
 * Anwenden-Abbildung je Hebel (über bestehende Setter, ADR-016):
 * - `ik_config` → `setProcessParams` mit dem Tri-State-Block (S4-Schalter, #129).
 * - `kipp_lead` → `setProcessParams` mit `orientation` (Kipp/Lead in Grad).
 * - `placement` → `setPlacementOverride` (freie Platzierungswerte des Teils, #94).
 * Alle drei bumpen die Revision ⇒ die normale Veraltung/Neubewertung wird angestoßen.
 */

import type {
  CollisionAdvice,
  CollisionOption,
  IkConfig,
  OrientationParams,
  PlacementOverrideValues,
} from "../api/projects";

/**
 * Prüf-Modus (Prüf-UX, Karte #139/#145): „befund" = nur der Basis-Befund des
 * geprüften Teils (EINE Neu-Simulation, ~20 s); „optionen" = das teure Menü
 * (Basis + ~17 Hebel-Kandidaten, je eine Neu-Simulation — mehrere Minuten).
 */
export type CollisionCheckMode = "befund" | "optionen";

/**
 * Ehrliche Scope-Beschriftung des Advisors: geprüft wird das fokussierte Teil
 * (Teile-Palette), ohne Fokus fällt der Core auf das erste Teil des Plans
 * zurück — der frühere statische Kopf-Hinweis „global" war schlicht falsch.
 */
export function collisionScopeLabel(
  sectionId: string | null,
  partName: string | null,
): string {
  if (sectionId === null) return "erstes Teil (kein Fokus)";
  return partName ?? sectionId;
}

/** Laufende Statuszeile je Prüf-Modus — nennt Teil und Kosten ehrlich. */
export function collisionCheckStatus(mode: CollisionCheckMode, scopeLabel: string): string {
  return mode === "befund"
    ? `Prüfe Kollisionsbefund von ${scopeLabel} — eine Neu-Simulation (≈ 20 s) …`
    : `Suche Hebel-Optionen für ${scopeLabel} — je Kandidat eine Neu-Simulation, ` +
      "das dauert mehrere Minuten …";
}

/**
 * Text der leeren Optionsliste je Prüf-Modus: nach dem schnellen Befund wurden
 * die Optionen bewusst NICHT gesucht (kein „nichts gefunden"-Fehlschluss).
 */
export function collisionEmptyListText(mode: CollisionCheckMode): string {
  return mode === "befund"
    ? "Hebel-Optionen nicht gesucht — der Knopf „Hebel-Optionen suchen (Minuten)“ " +
      "probiert IK-Konfiguration, Kipp/Lead und Platzierung durch."
    : "Kein Hebel beseitigt oder verbessert die Kollision nachweislich.";
}

/** Anzeige-Zeile einer Advisor-Option (rein präsentational). */
export interface CollisionOptionView {
  kind: CollisionOption["kind"];
  /** Kurzer Hebel-Badge-Text. */
  leverLabel: string;
  /** Vollständiger Core-Detailtext (min. Abstand + Marge vorher/nachher). */
  detail: string;
  minDistanceBeforeText: string;
  minDistanceAfterText: string;
  marginBeforeText: string;
  marginAfterText: string;
  /** true ⇒ nach dem Hebel kollisionsfrei (Ranking-Spitze). */
  collisionFreeAfter: boolean;
  /** true ⇒ dieser Hebel *beseitigt* die Kollision (nicht nur verbessert). */
  removesCollision: boolean;
  /** Beschriftung des „Anwenden"-Knopfs dieser Zeile. */
  applyLabel: string;
}

/** Gesamtansicht des Panels: Basis-Stand + gerankte Optionszeilen. */
export interface CollisionAdvisorView {
  /** Vorher-Stand als Text (min. Abstand + Kollisionsstatus). */
  baselineText: string;
  options: CollisionOptionView[];
}

/** Anwenden-Aktion über eine bestehende Schreib-Route (discriminated union). */
export type CollisionApplyAction =
  | { kind: "process-params-ik"; ikConfig: IkConfig }
  | { kind: "process-params-orientation"; orientation: OrientationParams }
  | { kind: "placement-override"; sectionId: string; values: PlacementOverrideValues };

const LEVER_LABEL: Record<CollisionOption["kind"], string> = {
  ik_config: "IK-Konfiguration",
  kipp_lead: "Kipp/Lead",
  placement: "Platzierung",
};

/** Abstand in mm als 1-Nachkommastellen-Text oder „∞" (kein Nahpaar). */
export function mmText(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "∞" : value.toFixed(1);
}

/**
 * Baut die Gesamtansicht aus der Core-Antwort — oder `null`, wenn es nichts zu
 * beraten gibt (kein Abschnitt oder keine Kollisionsgeometrie, `baseline === null`).
 */
export function collisionAdvisorView(advice: CollisionAdvice): CollisionAdvisorView | null {
  if (advice.baseline === null) return null;
  const b = advice.baseline;
  const status = b.collision_free ? "kollisionsfrei" : `${b.n_red} Kollisions-Samples`;
  return {
    baselineText: `Aktuell: min. Abstand ${mmText(b.min_distance_mm)} mm, Marge ${mmText(
      b.margin_mm,
    )} mm (${status}).`,
    options: advice.options.map(optionView),
  };
}

function optionView(o: CollisionOption): CollisionOptionView {
  const removesCollision = !o.collision_free_before && o.collision_free_after;
  return {
    kind: o.kind,
    leverLabel: LEVER_LABEL[o.kind],
    detail: o.detail,
    minDistanceBeforeText: mmText(o.min_distance_before_mm),
    minDistanceAfterText: mmText(o.min_distance_after_mm),
    marginBeforeText: mmText(o.margin_before_mm),
    marginAfterText: mmText(o.margin_after_mm),
    collisionFreeAfter: o.collision_free_after,
    removesCollision,
    applyLabel: `${o.label} anwenden`,
  };
}

/**
 * Bildet die Schreibstellen-Nutzlast einer Option auf eine Anwenden-Aktion über
 * eine *bestehende* Route ab (der Viewer setzt nur, ADR-007/016). Wirft nie —
 * eine unbekannte Nutzlast (künftiger Hebel) ergäbe sonst einen stillen No-Op.
 */
export function collisionApplyActionFor(option: CollisionOption): CollisionApplyAction {
  const w = option.write;
  if (w.setter === "placement-override") {
    const values: PlacementOverrideValues = {};
    if (typeof w.lateral_mm === "number") values.lateral_mm = w.lateral_mm;
    if (typeof w.standoff_mm === "number") values.standoff_mm = w.standoff_mm;
    if (typeof w.stand_height_mm === "number") values.stand_height_mm = w.stand_height_mm;
    // Issue #173: Einzelfeld-Optionen (Abstand ODER Aufstellhöhe) mergen, damit
    // der angewandte Zustand dem bewerteten Kandidaten entspricht (B18) — der
    // Kern wurde MIT dem bestehenden Override simuliert.
    if (w.merge === true) values.merge = true;
    return { kind: "placement-override", sectionId: w.section_id, values };
  }
  // setter === "process-params": genau eine Gruppe (ik_config ODER orientation).
  if (w.orientation !== undefined) {
    return { kind: "process-params-orientation", orientation: w.orientation };
  }
  return { kind: "process-params-ik", ikConfig: w.ik_config ?? {} };
}

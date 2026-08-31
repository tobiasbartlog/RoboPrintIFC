/**
 * Singularitäts-Advisor — reine, DOM-freie Darstellungs- und Anwenden-Logik
 * (Scheibe 6, Issue #65; Fokus-Verankerung Issue #134).
 *
 * Der Core urteilt (`POST …/singularity-advice`), der Viewer *setzt* (ADR-007):
 * hier liegt nur die Umrechnung Core-Vorschlag → Anzeigezeile und Core-Vorschlag →
 * **Anwenden-Aktion** über die *bestehenden* Schreib-Routen. Kein eigener
 * Fachzustand, keine eigene Kinematik. Die three.js-/DOM-Verdrahtung
 * (`singularity-advisor.ts`) bleibt dünn und ruft nur diese Funktionen.
 *
 * Seit Issue #134 ist der Advisor am **Fokus-Abschnitt** verankert (Muster
 * Kollisions-Advisor #130): geprüft wird die Platzierung des in der
 * Teile-Palette gewählten Teils; ohne Fokus zeigt das Panel den freundlichen
 * Hinweis (`focusHint`) statt einen Core-Aufruf zu machen.
 *
 * Anwenden-Abbildung je Hebel:
 * - `kipp` (Handgelenk): `process_params.orientation.kipp_deg += kipp_delta_deg`
 *   (Lead bleibt erhalten) → `setProcessParams` (bumpt die Revision, veraltet
 *   Zerlegung/Simulation/Export = Core-Neubewertung angestoßen).
 * - `placement` (Reichweite/Ellbogen): die vorgeschlagene Basis-Lage als freie
 *   Platzierungs-Override-Werte des Fokus-Abschnitts → `setPlacementOverride`
 *   (Issue #94, ADR-016).
 * - `config_flip` (Schulter): die Schulter auf den anderen a/b-Zweig fixieren →
 *   `setProcessParams(ik_config=…)` (Issue #200 — dieselbe Route wie der
 *   Kollisions-Advisor; ADR-024 Punkt 4 erfüllt den ADR-020-Revisionstrigger).
 *   Früher rein beratend (rohes opw-Bitfeld, keine Schreibstelle).
 */

import type {
  IkConfig,
  OrientationParams,
  PlacementOverrideValues,
  PrintJob,
  SingularityAdvice,
  SingularitySuggestion,
} from "../api/projects";

/** Anzeige-Zeile eines Advisor-Vorschlags (rein präsentational). */
export interface AdvisorView {
  type: "wrist" | "elbow" | "shoulder";
  lever: "kipp" | "placement" | "config_flip";
  /** Menschlicher Typ-Text mit Badge-Kürzel. */
  typeLabel: string;
  /** Kurzbeschreibung des Hebels. */
  leverLabel: string;
  /** Vollständiger Core-Detailtext. */
  detail: string;
  marginBeforeText: string;
  marginAfterText: string;
  improves: boolean;
  /** Beschriftung des „Anwenden"-Knopfs. */
  applyLabel: string;
  /** false ⇒ Knopf inaktiv (config_flip: nur Hinweis; kipp ohne Delta). */
  applyEnabled: boolean;
}

/** Anwenden-Aktion über eine bestehende Schreib-Route (discriminated union). */
export type ApplyAction =
  | { kind: "process-params"; orientation: OrientationParams }
  | { kind: "process-params-ik"; ikConfig: IkConfig }
  | { kind: "placement-override"; sectionId: string; values: PlacementOverrideValues }
  | { kind: "advisory" };

/** Menschlicher Zweig-Name je IK-Achse (Domänenbegriff, Issue #200). */
const IK_AXIS_LABEL: Record<keyof IkConfig, string> = {
  shoulder: "Schulter",
  elbow: "Ellbogen",
  wrist: "Handgelenk",
};

/**
 * Beschreibt einen a/b-Block als Domänen-Text, z. B. „Schulter auf Zweig b"
 * (Issue #200) — kein rohes opw-Bitfeld mehr. Mehrere Achsen werden verbunden;
 * ein leerer/fehlender Block ergibt den Fallback „IK-Konfiguration".
 */
export function ikConfigLabel(block: IkConfig | null): string {
  if (block === null) return "IK-Konfiguration";
  const parts = (Object.keys(IK_AXIS_LABEL) as (keyof IkConfig)[])
    .filter((axis) => block[axis] === "a" || block[axis] === "b")
    .map((axis) => `${IK_AXIS_LABEL[axis]} auf Zweig ${block[axis]}`);
  return parts.length === 0 ? "IK-Konfiguration" : parts.join(", ");
}

/**
 * Freundlicher Fokus-Hinweis (Issue #134): der Advisor prüft den Fokus-Abschnitt —
 * ohne gewähltes Teil gibt es nichts zu prüfen. `null` = Fokus vorhanden.
 */
export function focusHint(sectionId: string | null): string | null {
  return sectionId === null
    ? "Kein Teil gewählt — zuerst ein Teil in der Teile-Palette wählen; " +
        "der Advisor prüft die Platzierung des Fokus-Abschnitts."
    : null;
}

const TYPE_LABEL: Record<AdvisorView["type"], string> = {
  wrist: "Handgelenk (J5≈0)",
  elbow: "Ellbogen gestreckt",
  shoulder: "Schulter (über Basisachse)",
};

const LEVER_LABEL: Record<AdvisorView["lever"], string> = {
  kipp: "Düse kippen",
  placement: "Basis umstellen",
  config_flip: "IK-Konfiguration",
};

/** Marge als 3-Nachkommastellen-Text oder „—" (unbekannt). */
export function marginText(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "—" : value.toFixed(3);
}

/**
 * Baut die Anzeige-Zeile aus der Core-Antwort — oder `null`, wenn es nichts zu
 * beraten gibt (`advice === null`).
 */
export function advisorView(advice: SingularityAdvice): AdvisorView | null {
  const s = advice.advice;
  if (s === null) return null;
  return {
    type: s.type,
    lever: s.lever,
    typeLabel: TYPE_LABEL[s.type],
    leverLabel: LEVER_LABEL[s.lever],
    detail: s.detail,
    marginBeforeText: marginText(s.margin_before),
    marginAfterText: marginText(s.margin_after),
    improves: s.improves,
    applyLabel: applyLabel(s),
    applyEnabled: applyEnabled(s),
  };
}

function applyLabel(s: SingularitySuggestion): string {
  if (s.lever === "kipp") {
    const d = s.kipp_delta_deg ?? 0;
    return `Kipp ${d > 0 ? "+" : ""}${d}° anwenden`;
  }
  if (s.lever === "placement") return "Platzierung übernehmen";
  // config_flip (#200): Domänenbegriff statt „Bitfeld flippen", z. B.
  // „Schulter auf Zweig b fixieren".
  return `${ikConfigLabel(s.ik_config)} fixieren`;
}

function applyEnabled(s: SingularitySuggestion): boolean {
  if (s.lever === "kipp") return (s.kipp_delta_deg ?? 0) !== 0;
  if (s.lever === "placement") return s.placement !== null;
  // config_flip (#200): anwendbar über die process-params-Route, sobald der Flip
  // die Marge nachweislich hebt (der Advisor beschönigt nicht — kein Gewinn ⇒ inaktiv).
  return s.write !== null && s.improves;
}

/**
 * Bildet den Vorschlag auf eine Anwenden-Aktion über eine *bestehende* Route ab.
 *
 * Für `kipp` wird der aktuelle Kipp des Druckjobs gelesen und der Delta addiert;
 * ein gesetzter Lead bleibt erhalten (sonst würde `setProcessParams` ihn beim
 * Ersetzen des Orientierungs-Blocks verlieren). `placement` wird zu freien
 * Platzierungs-Override-Werten des Fokus-Abschnitts (`sectionId` aus der
 * Core-Antwort, Issue #134 → `setPlacementOverride` #94); ohne Abschnitt ist die
 * Aktion rein beratend. `config_flip` (#200) wird zum a/b-Block über die
 * `process-params`-Route (`setProcessParams(ik_config=…)`, dieselbe Route wie der
 * Kollisions-Advisor); ohne Block ist die Aktion rein beratend.
 */
export function applyActionFor(
  suggestion: SingularitySuggestion,
  job: PrintJob | undefined,
  sectionId: string | null = null,
): ApplyAction {
  if (suggestion.lever === "kipp") {
    const currentKipp = job?.process_params?.orientation?.kipp_deg ?? 0;
    const currentLead = job?.process_params?.orientation?.lead_deg;
    const orientation: OrientationParams = {
      kipp_deg: currentKipp + (suggestion.kipp_delta_deg ?? 0),
    };
    if (typeof currentLead === "number" && Number.isFinite(currentLead)) {
      orientation.lead_deg = currentLead;
    }
    return { kind: "process-params", orientation };
  }
  if (
    suggestion.lever === "config_flip" &&
    suggestion.write !== null &&
    suggestion.write.setter === "process-params"
  ) {
    // Der Core liefert den vollständigen a/b-Block in der write-Nutzlast (Form des
    // Kollisions-Advisors); der Viewer setzt ihn über die process-params-Route.
    return { kind: "process-params-ik", ikConfig: suggestion.write.ik_config ?? {} };
  }
  if (suggestion.lever === "placement" && suggestion.placement !== null && sectionId !== null) {
    const p = suggestion.placement;
    return {
      kind: "placement-override",
      sectionId,
      values: {
        lateral_mm: p.lateral_mm,
        standoff_mm: p.standoff_mm,
        stand_height_mm: p.stand_height_mm,
      },
    };
  }
  return { kind: "advisory" };
}

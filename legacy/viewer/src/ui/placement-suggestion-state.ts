/**
 * Kollisions-Ampel je Platzierungsvorschlag + Zerlegungs-Hinweis (Issue #231,
 * PRD #225 Slice 2, ADR-026 Punkt 2) — reine, DOM-freie Ableitung (Muster
 * `beamProgressView`/`checkProgressView`).
 *
 * Der Core liefert die Machbarkeits-Einstufung je Kandidat (`score.collision`,
 * Issue #228: `{free, status, source}`) und den Gesamt-Befund (`feasibility`)
 * bereits fertig gerechnet. Diese Datei tut **nichts** als eine Text-/Ton-
 * Nachschlagetabelle je `status`-Wert — keine eigene Schwellen-Rechnung, keine
 * neue Zwillingsfunktion (Paritäts-Manifest bleibt unberührt). Unbekannte/
 * fehlende Urteile fallen defensiv auf „nicht geprüft" (neutral), nie auf
 * einen erfundenen Zustand.
 *
 * Der Hinweis bei „kein machbarer Kandidat" trägt nur Text — der Absprung auf
 * den vorhandenen Beam-Zerlegungs-Trigger (#221/#222) ist reine DOM-Verdrahtung
 * im Panel; diese Datei ruft den Zerleger nie selbst (lose Kopplung, ADR-026).
 */

import type {
  PlacementCollisionJudgment,
  PlacementFeasibility,
  ScoredPlacementOption,
} from "../api/projects";

/** Ton der Ampel (für CSS: ok=grün, bad=rot, muted=neutral/ungeprüft). */
export type PlacementAmpelTone = "ok" | "bad" | "muted";

/** Eine Ampel-Anzeige: Ton + Anzeigetext. */
export interface PlacementAmpel {
  tone: PlacementAmpelTone;
  label: string;
}

/** Nachschlagetabelle Core-`status` → Ampel-Text/Ton (keine Schwellen-Rechnung). */
const AMPEL_BY_STATUS: Record<string, PlacementAmpel> = {
  clear: { tone: "ok", label: "frei" },
  colliding: { tone: "bad", label: "kollidierend" },
};

/** Neutrale Ampel für „nicht geprüft" (fehlender/unbekannter Befund). */
const AMPEL_UNCHECKED: PlacementAmpel = { tone: "muted", label: "nicht geprüft" };

/**
 * Bildet das Core-Kollisionsurteil eines Kandidaten auf die Ampel ab.
 * `undefined`/`null` (kein Grob-Check gelaufen) oder ein unbekannter
 * `status`-Wert (zukünftige Core-Stufe, z. B. „im Sicherheitsband") fallen
 * fail-soft auf „nicht geprüft" zurück statt abzustürzen.
 */
export function placementAmpel(
  collision: PlacementCollisionJudgment | null | undefined,
): PlacementAmpel {
  if (!collision) return AMPEL_UNCHECKED;
  return AMPEL_BY_STATUS[collision.status] ?? AMPEL_UNCHECKED;
}

/** Eine Anzeigezeile der Vorschlagsliste (Issue #231). */
export interface PlacementSuggestionRow {
  optionId: string;
  ampel: PlacementAmpel;
  /** „<erreichbarer Anteil> · <Abstand>/<Höhe>" — reine Textzusammenfassung. */
  detail: string;
}

/** Leitet die Anzeigezeilen der Vorschlagsliste aus `scored` ab (Core-Reihenfolge). */
export function placementSuggestionRows(
  scored: ScoredPlacementOption[] | null | undefined,
): PlacementSuggestionRow[] {
  return (scored ?? []).map((o) => ({
    optionId: o.option_id,
    ampel: placementAmpel(o.score.collision),
    detail:
      `erreichbar ${(o.score.reachable_fraction * 100).toFixed(0)}% · ` +
      `Abstand ${o.standoff_mm.toFixed(0)} mm / Höhe ${o.stand_height_mm.toFixed(0)} mm`,
  }));
}

/** Der Zerlegungs-Hinweis bei „kein machbarer Kandidat" (US 3 des PRD #225). */
export interface PlacementFeasibilityHint {
  /** true genau dann, wenn der Grob-Check lief UND KEIN Kandidat frei ist —
   *  bei machbaren Kandidaten oder ungeprüftem Befund erscheint kein Hinweis. */
  show: boolean;
  text: string;
}

const NO_HINT: PlacementFeasibilityHint = { show: false, text: "" };

/**
 * Leitet den Zerlegungs-Hinweis aus dem Core-Feasibility-Befund ab.
 * `checked=false` (Grob-Check nicht gelaufen) oder `feasible !== false`
 * (machbar oder unbekannt) zeigen bewusst KEINEN Hinweis — nur das belegte
 * „kein machbarer Kandidat" rechtfertigt den Absprungvorschlag.
 */
export function placementFeasibilityHint(
  feasibility: PlacementFeasibility | null | undefined,
): PlacementFeasibilityHint {
  if (!feasibility || !feasibility.checked || feasibility.feasible !== false) {
    return NO_HINT;
  }
  // Der Core-Text trägt die Begründung bereits verbatim (inkl. „Zerlegen statt
  // weiter platzieren", ADR-026 Punkt 2) — der Viewer dichtet nichts hinzu.
  return { show: true, text: feasibility.note };
}

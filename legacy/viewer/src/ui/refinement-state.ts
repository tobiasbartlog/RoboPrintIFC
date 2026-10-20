/**
 * Ableitung des Zerlegungs-Such-Ausweises für den Reiter **Zerlegung** (Issue #217,
 * PRD #183 Stufe 3) — reine, DOM-freie Funktionen (wie `zerlegung-status.ts` /
 * `parts-palette-state.ts`, vitest-getestet).
 *
 * Die Beam-Suche (#217) liefert im `refinement`-Block der Zerlegungs-Antwort zwei
 * Dinge, die der Planer nachvollziehen können muss (der Viewer rechnet nichts
 * Eigenes, ADR-007 — er übersetzt nur das Core-Urteil in Anzeigetext):
 *
 * - **Verworfen-Gründe** (US 10): warum ein Kandidat NICHT vorgeschlagen wurde —
 *   Reichweite (unerreichbar), Fragment (zerfällt), Kollision. Ohne diese Liste
 *   wäre die Suche ein Orakel.
 * - **Relaxationsausweis** (US 22): welche Constraints bei leerem Ergebnis
 *   schrittweise gelockert wurden (mehr Teile → mehr Standplätze →
 *   Tiefenteilungs-Vorschlag), damit „nichts gefunden" nie stumm passiert.
 */

import type {
  BeamProposeStatus,
  DecompositionRefinement,
  RefinementRejection,
} from "../api/projects";

/** Eine Verworfen-Zeile für die Anzeige: Kandidat + menschlicher Grundtext. */
export interface VerworfenRow {
  /** Kandidaten-Schlüssel, z. B. „band-1x1". */
  kandidat: string;
  /** Roh-Grund aus dem Core (Filter/Facetten). */
  grund: RefinementRejection["grund"];
  /** Anzeigetext des Grundes (deutsch). */
  label: string;
  /** Kurzform der Rastergröße („2×3"). */
  raster: string;
}

const GRUND_LABEL: Record<RefinementRejection["grund"], string> = {
  reichweite: "unerreichbar",
  fragment: "zerfällt in Fragmente",
  kollision: "Kollision",
};

/**
 * Die Verworfen-Gründe als Anzeigezeilen (US 10), in Core-Reihenfolge (bester zuerst).
 * Ohne Suche/`refinement` (Greedy, Altlauf) eine leere Liste — nichts zu zeigen.
 */
export function verworfenRows(
  refinement?: DecompositionRefinement | null,
): VerworfenRow[] {
  const verworfen = refinement?.verworfen ?? [];
  return verworfen.map((v) => ({
    kandidat: v.kandidat,
    grund: v.grund,
    label:
      v.grund === "kollision" && typeof v.h_idx === "number"
        ? `${GRUND_LABEL.kollision} (Reihe ${v.h_idx + 1})`
        : GRUND_LABEL[v.grund],
    raster: `${v.n_length}×${v.n_height}`,
  }));
}

const RELAX_LABEL: Record<string, string> = {
  mehr_teile: "mehr Teile",
  mehr_standplaetze: "mehr Standplätze",
  tiefenteilung_vorschlag: "Tiefenteilung (Vorschlag)",
};

/** Ein Relaxationsausweis: gezündete Stufen + ob überhaupt etwas zu zeigen ist. */
export interface RelaxAusweis {
  /** true, wenn mindestens eine Stufe gezündet wurde. */
  show: boolean;
  /** Menschliche Namen der gezündeten Stufen, in Reihenfolge. */
  stufen: string[];
  /** Zusammengesetzter Anzeigetext („gelockert: …") oder leer. */
  label: string;
  /** true, wenn die Suche trotz Relaxation leer blieb (best-effort-Vorschlag). */
  leer: boolean;
}

/**
 * Der Relaxationsausweis für den Zerlegungs-Reiter (US 22): welche Constraints
 * schrittweise gelockert wurden. Unbekannte Stufennamen werden roh durchgereicht
 * (fail-soft, kein Absturz bei neuen Core-Stufen).
 */
export function relaxAusweis(
  refinement?: DecompositionRefinement | null,
): RelaxAusweis {
  const roh = refinement?.relaxation ?? [];
  const stufen = roh.map((s) => RELAX_LABEL[s] ?? s);
  return {
    show: stufen.length > 0,
    stufen,
    label: stufen.length > 0 ? `gelockert: ${stufen.join(" → ")}` : "",
    leer: refinement?.leer === true,
  };
}

/** Ein knapper Kopfzeilen-Text der Suche (Strategie + Kontingent-Nutzung). */
export interface BeamSummary {
  show: boolean;
  label: string;
}

/**
 * Kompakter Such-Ausweis (Strategie + verbrauchte/erlaubte Aufrufe), nur wenn die
 * Beam-Suche lief (`strategy==='beam-suche'`). Kein Gate — reine Information.
 */
export function beamSummary(
  refinement?: DecompositionRefinement | null,
): BeamSummary {
  if (!refinement || refinement.strategy !== "beam-suche") {
    return { show: false, label: "" };
  }
  const used = refinement.calls_used ?? 0;
  const budget = refinement.call_budget ?? 0;
  const rest = refinement.budget_exhausted ? " (Kontingent erschöpft)" : "";
  return { show: true, label: `Beam-Suche · ${used}/${budget} Prüfungen${rest}` };
}

/** Ton der Anzeige (für CSS-Klassen: ok=grün, warn=gelb, bad=rot, muted=neutral). */
export type BeamTone = "ok" | "warn" | "bad" | "muted";

/**
 * Fortschritts-/Ergebnisanzeige des Beam-Zerlegungslaufs (Issue #221) — reine Ableitung
 * aus dem Poll-Status (`BeamProposeStatus`), DOM-frei (wie `pruef-check-state.ts`). Der
 * Fortschritt zählt **Prüf-Tür-Aufrufe** (das Aufruf-Kontingent #215), nicht Sekunden.
 */
export interface BeamProgressView {
  /** true, solange etwas anzuzeigen ist (läuft ODER frisch abgeschlossen). */
  active: boolean;
  /** true nur, solange der Lauf läuft (Fortschrittsbalken + „Abbrechen" sichtbar). */
  running: boolean;
  /** true, wenn ein Abbruch möglich ist (nur während des Laufs). */
  cancellable: boolean;
  /** Anteil ∈ [0, 1] für den Fortschrittsbalken (0, solange das Kontingent unbekannt). */
  fraction: number;
  label: string;
  tone: BeamTone;
}

/**
 * Leitet die Beam-Fortschritts-/Ergebnisanzeige aus dem Poll-Status ab. `null` = kein
 * laufender/frischer Lauf (nichts anzeigen). Terminalzustände tragen einen ehrlichen
 * Abschluss-Text (abgebrochen/fehlgeschlagen) statt eines stillen Grüns (ADR-013).
 */
export function beamProgressView(
  status?: BeamProposeStatus | null,
): BeamProgressView {
  const idle: BeamProgressView = {
    active: false,
    running: false,
    cancellable: false,
    fraction: 0,
    label: "",
    tone: "muted",
  };
  if (!status) return idle;
  switch (status.state) {
    case "running": {
      const total = status.n_total || 0;
      const done = status.n_done || 0;
      const frac = total > 0 ? Math.min(1, done / total) : 0;
      const counter = total > 0 ? `${done}/${total} Prüfungen` : "Prüfungen";
      return {
        active: true,
        running: true,
        cancellable: true,
        fraction: frac,
        label: `Beam-Suche läuft: ${counter} …`,
        tone: "muted",
      };
    }
    case "done":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 1,
        label: "Beam-Suche fertig — Sieger übernommen.",
        tone: "ok",
      };
    case "cancelled":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label: "Beam-Suche abgebrochen — der Zerlegungsstand bleibt unverändert.",
        tone: "warn",
      };
    case "error":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label: status.error
          ? `Beam-Suche fehlgeschlagen: ${status.error}`
          : "Beam-Suche fehlgeschlagen.",
        tone: "bad",
      };
    default:
      return idle;
  }
}

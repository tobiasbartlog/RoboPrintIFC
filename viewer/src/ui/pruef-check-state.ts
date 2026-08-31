/**
 * Reine Zustandsfunktionen der entkoppelten Stufe-2-Prüf-Tür (Issue #175).
 *
 * Die teure Druckbarkeitsprüfung verlässt den interaktiven Schnittplan-Loop (Befund
 * B14: ~71 s Editor-Freeze je Schnitt-Edit) und läuft nur auf **expliziten Anstoß**
 * bzw. **asynchron mit Fortschritt + Abbruch**. Diese DOM-freien Funktionen leiten aus
 * dem Hintergrundlauf-Status (`DecompositionCheckStatus`), der Umfangsansage
 * (`PruefScope`) und dem gespeicherten letzten Prüfstand (`LastPruef` + `Revisions`)
 * die Anzeige ab — kein stilles Grün (ADR-013): ausbleibende/veraltete Prüfung ist
 * sichtbar. Parität zur Core-Ableitung `fgc.project.revisions.pruef_status`.
 */

import type {
  DecompositionCheckStatus,
  LastPruef,
  PruefScope,
} from "../api/projects";
import type { InputKey, Revisions, StageStatus } from "./staleness";

/** Eingabe-Stufen, deren Änderung den letzten Prüf-Tür-Stand veralten lässt (Issue #175).
 *  Muss zu `fgc.project.revisions.PRUEF_DEPS` passen. */
export const PRUEF_DEPS: InputKey[] = [
  "wall",
  "robot",
  "tool",
  "cutplan",
  "process",
  "workstation",
];

function sumSectionInputs(revisions: Revisions | undefined): number {
  const si = revisions?.section_inputs;
  if (!si) return 0;
  let total = 0;
  for (const v of Object.values(si)) total += v ?? 0;
  return total;
}

/**
 * Zustand des letzten Prüf-Tür-Stands: `"missing"` (nie geprüft ⇒ „ungeprüft"),
 * `"stale"` (der letzte Prüfstand ist veraltet — eine Prüf-Eingabe oder ein
 * Platzierungs-/Abschnitts-Override änderte sich seither) oder `"current"`.
 * Bit-gleicher Zwilling von `fgc.project.revisions.pruef_status`.
 *
 * Ein `last_pruef` **ohne** (oder mit leerem) `input_snapshot` gilt als `"missing"`
 * (= „ungeprüft"): ohne Schnappschuss lässt sich Aktualität nicht beweisen, ein
 * `"current"` wäre ein stilles Grün (ADR-013). Diese Seite hält den Vertrag; die
 * Python-Seite wurde von ihrem Legacy-Fallback (fehlender Schnappschuss = Null-Basis)
 * hierauf angeglichen (Design-Log 2026-07-13, Issue #194).
 */
export function pruefStatus(
  revisions: Revisions | undefined,
  lastPruef: LastPruef | undefined | null,
): StageStatus {
  if (
    !lastPruef ||
    !lastPruef.input_snapshot ||
    Object.keys(lastPruef.input_snapshot).length === 0
  ) {
    return "missing";
  }
  const snap = lastPruef.input_snapshot;
  const inputs = revisions?.inputs ?? {};
  for (const dep of PRUEF_DEPS) {
    if ((inputs[dep] ?? 0) > (snap[dep] ?? 0)) return "stale";
  }
  if (sumSectionInputs(revisions) > (snap.section_total ?? 0)) return "stale";
  return "current";
}

/** Umfangsansage für die beiden Anstoß-Knöpfe (Issue #175, AC „Umfangsansage"). */
export interface ScopeAnnouncement {
  /** Beschriftung „Fokus prüfen" (Default-Wahl, schnell). */
  focusLabel: string;
  /** Beschriftung „Ganze Wand prüfen (N Abschnitte, ~X s)" — die bewusste, teure Wahl. */
  globalLabel: string;
  /** true, wenn nichts zu prüfen ist (z. B. Wand schon nach Freigang zu dick) — der
   *  globale Knopf wird dann deaktiviert. */
  globalEmpty: boolean;
}

/** Grobe Sekunden pro Höhenreihe (nur Ansage; Parität zu
 *  `fgc.pipeline.actions.PRUEF_PER_REP_SECONDS`). */
export const PER_REP_SECONDS = 10;

/**
 * Baut die Umfangsansage aus der Core-Angabe (`pruef_scope`).
 *
 * `null`/`undefined` = **unbekannter** Umfang (z. B. frisch geladenes Projekt, bevor
 * eine Zerlegungs-Antwort ihn mitliefert): der globale Knopf trägt die generische
 * Beschriftung und bleibt aktiv (die Prüfung meldet selbst „nichts zu prüfen", falls
 * leer). Nur ein **bekanntes** ``n_representatives === 0`` (Wand schon nach Freigang zu
 * dick) deaktiviert den globalen Knopf.
 */
export function scopeAnnouncement(
  scope: PruefScope | null | undefined,
): ScopeAnnouncement {
  const focusLabel = `Fokus prüfen (~${PER_REP_SECONDS} s)`;
  if (!scope) {
    return { focusLabel, globalLabel: "Ganze Wand prüfen", globalEmpty: false };
  }
  const n = scope.n_representatives;
  const secs = Math.round(scope.est_seconds ?? 0);
  const abschnitte = n === 1 ? "Abschnitt" : "Abschnitte";
  return {
    focusLabel,
    globalLabel:
      n <= 0
        ? "Ganze Wand prüfen (nichts zu prüfen)"
        : `Ganze Wand prüfen (${n} ${abschnitte}, ~${secs} s)`,
    globalEmpty: n <= 0,
  };
}

/** Ton der Anzeige (für CSS-Klassen: ok=grün, warn=gelb, bad=rot, muted=neutral). */
export type PruefTone = "ok" | "warn" | "bad" | "muted";

/** Fortschritts-/Ergebnisanzeige eines Hintergrund-Prüflaufs (Issue #175). */
export interface CheckProgressView {
  /** true, solange etwas anzuzeigen ist (läuft ODER frisch abgeschlossen). */
  active: boolean;
  /** true nur, solange der Lauf läuft (Fortschrittsbalken + „Abbrechen" sichtbar). */
  running: boolean;
  /** true, wenn ein Abbruch möglich ist (nur während des Laufs). */
  cancellable: boolean;
  /** Anteil ∈ [0, 1] für den Fortschrittsbalken (0, solange N unbekannt). */
  fraction: number;
  label: string;
  tone: PruefTone;
}

/**
 * Leitet die Fortschritts-/Ergebnisanzeige aus dem Poll-Status ab. `null` = kein
 * laufender/frischer Prüflauf (nichts anzeigen). Terminalzustände tragen einen ehrlichen
 * Abschluss-Text (abgebrochen/verworfen/fehlgeschlagen) statt eines stillen Grüns.
 */
export function checkProgressView(
  status: DecompositionCheckStatus | null | undefined,
): CheckProgressView {
  const idle: CheckProgressView = {
    active: false,
    running: false,
    cancellable: false,
    fraction: 0,
    label: "",
    tone: "muted",
  };
  if (!status) return idle;
  const scopeWord = status.scope === "focus" ? "Fokus" : "ganze Wand";
  switch (status.state) {
    case "running": {
      const total = status.n_total || 0;
      const done = status.n_done || 0;
      const frac = total > 0 ? Math.min(1, done / total) : 0;
      const counter = total > 0 ? `${done}/${total} Höhenreihen` : "Höhenreihen";
      return {
        active: true,
        running: true,
        cancellable: true,
        fraction: frac,
        label: `Prüfe ${scopeWord}: ${counter} …`,
        tone: "muted",
      };
    }
    case "done": {
      const parts: string[] = [];
      if (status.n_computed) parts.push(`${status.n_computed} gerechnet`);
      if (status.n_cached) parts.push(`${status.n_cached} aus Cache`);
      const detail = parts.length ? ` (${parts.join(", ")})` : "";
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 1,
        label: `Prüfung fertig: ${scopeWord}${detail}.`,
        tone: "ok",
      };
    }
    case "cancelled":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label: "Prüfung abgebrochen — der Stand bleibt ungeprüft.",
        tone: "warn",
      };
    case "superseded":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label:
          "Eingaben änderten sich während der Prüfung — Ergebnis verworfen, bitte neu anstoßen.",
        tone: "warn",
      };
    case "empty":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label: "Kein Abschnitt zu prüfen.",
        tone: "muted",
      };
    case "error":
      return {
        active: true,
        running: false,
        cancellable: false,
        fraction: 0,
        label: status.error
          ? `Prüfung fehlgeschlagen: ${status.error}`
          : "Prüfung fehlgeschlagen.",
        tone: "bad",
      };
    default:
      return idle;
  }
}

/** Anzeige des letzten Prüfstands („was zuletzt geprüft, veraltet?", Issue #175). */
export interface LastCheckView {
  /** false = noch nie geprüft (ungeprüft). */
  known: boolean;
  /** true = der letzte Prüfstand ist veraltet (Eingaben änderten sich seither). */
  stale: boolean;
  label: string;
  tone: PruefTone;
}

/**
 * Leitet die „letzter Prüfstand"-Zeile ab: WAS zuletzt geprüft wurde (ganze Wand vs.
 * Fokus-Teil) und OB der Stand veraltet ist — sichtbar, nicht gelöscht (#172/#182-Muster).
 */
export function lastCheckView(
  revisions: Revisions | undefined,
  lastPruef: LastPruef | undefined | null,
): LastCheckView {
  const status = pruefStatus(revisions, lastPruef);
  if (status === "missing" || !lastPruef) {
    return {
      known: false,
      stale: false,
      label: "Druckbarkeit: noch nicht geprüft",
      tone: "warn",
    };
  }
  const scopeText =
    lastPruef.scope === "focus"
      ? `Fokus-Teil${lastPruef.section_id ? ` (${lastPruef.section_id})` : ""}`
      : "ganze Wand";
  const stale = status === "stale";
  return {
    known: true,
    stale,
    label: stale
      ? `Zuletzt geprüft: ${scopeText} — veraltet (Eingaben geändert)`
      : `Zuletzt geprüft: ${scopeText}`,
    tone: stale ? "warn" : "ok",
  };
}

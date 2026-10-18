/**
 * Aufstell-Toggle-Zustand (Issue #81, PRD B/#70) — reine Logik, DOM-frei.
 *
 * Der Aufstell-Toggle ersetzt die frühere manuelle Aufstell-Liste im Reiter
 * Druckplan: „Roboter steht auf dem Boden“ (`floor`) vs. „darf auch erhöht
 * stehen“ (`elevated`). Der Zustand begrenzt, welchen Podesthöhen-Satz der Core
 * (`fgc.decompose.propose`) für die Abschnitts-/Platzierungssuche nutzen darf —
 * `floor` erzwingt Höhe 0 (mehr Höhenbänder), `elevated` erlaubt die realen
 * Podesthöhen (weniger Bänder).
 *
 * Der Viewer hält keinen Fachzustand (ADR-007/016): der Toggle wird über die
 * Core-Route `PUT /projects/{slug}/stand-mode` persistiert und beim Öffnen aus
 * dem Druckjob (`stand_mode`) wiederhergestellt. Diese Datei kapselt nur die
 * Normalisierung (Altprojekt ohne Feld → Default `floor`), damit sie ohne
 * Renderer testbar bleibt (Pure/DOM-Split).
 */

/** Die beiden Aufstell-Zustände (Parität zu `fgc.placement.suggest.STAND_MODES`). */
export type StandMode = "floor" | "elevated";

/** Default-Zustand: ein Altprojekt ohne `stand_mode`-Feld verhält sich wie `floor`. */
export const DEFAULT_STAND_MODE: StandMode = "floor";

/**
 * Normalisiert einen (möglicherweise fehlenden/unbekannten) Rohwert aus dem
 * Druckjob auf einen gültigen {@link StandMode}. Alles außer dem exakten String
 * `"elevated"` fällt auf den Default `"floor"` zurück — so laden Altprojekte
 * (Feld fehlt → `undefined`) unverändert und byte-gleich wie `floor`.
 */
export function normalizeStandMode(raw: string | null | undefined): StandMode {
  return raw === "elevated" ? "elevated" : DEFAULT_STAND_MODE;
}

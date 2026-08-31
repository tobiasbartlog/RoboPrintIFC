/**
 * Gebäudekontext-Schalter-Zustand (Issue #131, PRD #124, ADR-024) — reine Logik, DOM-frei.
 *
 * Der Schalter sagt der Kollisionskontrolle, **ob** die Simulation den Arm
 * zusätzlich gegen den Gebäudekontext (`context.json`, Issue #17) prüft. Default
 * **aus** (Altprojekte byte-gleich); bei Zerlegungsart Modul gegenstandslos (die
 * Workstation ist der Druckort, ADR-022) — dort wird der Schalter ausgeblendet,
 * nicht gelöscht.
 *
 * Der Viewer hält keinen Fachzustand (ADR-007/016): der Schalter wird über die
 * Core-Route `PUT /projects/{slug}/context-check` persistiert und beim Öffnen aus
 * dem Druckjob (`check_building_context`) wiederhergestellt. Diese Datei kapselt nur
 * die Normalisierung (Altprojekt ohne Feld → Default `false`), damit sie ohne
 * Renderer testbar bleibt (Pure/DOM-Split, Spiegel von `aufstell-state.ts`).
 */

/** Default-Zustand: ein Altprojekt ohne `check_building_context`-Feld ist `false`. */
export const DEFAULT_CONTEXT_CHECK = false;

/**
 * Normalisiert einen (möglicherweise fehlenden) Rohwert aus dem Druckjob auf einen
 * gültigen Bool-Zustand. Nur exakt `true` schaltet die Prüfung ein — alles andere
 * (fehlend/`undefined`/`null`/falsy) fällt auf den Default `false` zurück, sodass
 * Altprojekte (Feld fehlt) unverändert und byte-gleich als „aus" laden.
 */
export function normalizeContextCheck(raw: boolean | null | undefined): boolean {
  return raw === true;
}

/**
 * Freigang-Befund → Anzeige-Text (Issue #163, Karte #139 / Entscheidung #141).
 *
 * Reine Ableitung (DOM-frei, ADR-007): der Viewer rechnet nichts, er formatiert
 * nur den vom Core gelieferten {@link FreigangFinding} zur Anzeige an der
 * Zerlegung. Der Befund stellt **ausschließlich** Unmöglichkeit fest — „Wand zu
 * dick für einseitigen Druck" — nie Freiheit (S6-Lehre). **Befund, kein Gate**
 * (ADR-013): die Meldung blockiert nichts, sie benennt Hebel.
 *
 * Bewusst **still**, solange die Wand nicht zu dick ist: kein grünes „druckbar"
 * (das Kriterium bescheinigt keine Freiheit — das tut erst der volle
 * Kollisionsbefund, Scheibe 2). Fehlt der Befund ganz (`null`/`undefined` —
 * Endeffektor-/Kinematik-Geometrie unbekannt), bleibt die Anzeige leer.
 */
import type { FreigangFinding } from "../api/projects";

/** Ganze Millimeter, deutsches Format (kein Nachkomma-Rauschen in der Meldung). */
function mm(value: number): string {
  return `${Math.round(value)} mm`;
}

/**
 * Die Anzeige-Notiz zum Freigang-Befund — **nur** im Fall „zu dick", sonst `null`.
 *
 * `null` heißt „keine Meldung": entweder fehlt der Befund, oder die Wand ist
 * nicht (sicher) zu dick. Nie eine „druckbar"-Zusage (Fehlerrichtung, S6).
 */
export function freigangNotice(finding: FreigangFinding | null | undefined): string | null {
  if (!finding || !finding.too_thick) return null;
  const head =
    `Wand zu dick für einseitigen Druck: Dicke ${mm(finding.wall_thickness_mm)} ` +
    `> druckbare Tiefe ${mm(finding.printable_depth_mm)} ` +
    `(um ${mm(finding.excess_mm)}). Befund, kein Gate.`;
  const levers = finding.levers.length > 0 ? ` Hebel: ${finding.levers.join("; ")}.` : "";
  return head + levers;
}

/**
 * Sichtbarkeit + Text für das Freigang-Banner an der Zerlegung (reine Regel).
 *
 * `hidden` genau dann, wenn es nichts zu melden gibt ({@link freigangNotice}
 * liefert `null`) — das Banner belegt sonst keinen Platz.
 */
export function freigangBannerView(finding: FreigangFinding | null | undefined): {
  hidden: boolean;
  text: string;
} {
  const notice = freigangNotice(finding);
  return { hidden: notice === null, text: notice ?? "" };
}

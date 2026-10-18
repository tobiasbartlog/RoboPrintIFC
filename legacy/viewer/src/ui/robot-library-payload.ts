/**
 * Roboter-Galerie — reine Anzeige-Umrechnung (Issue #76, PRD #69).
 *
 * Getrennt vom DOM (Muster wie `workstation-payload.ts`), damit die
 * Karten-Zusammenfassung und die Roboter→PNG-Pfad-Abbildung ohne jsdom/WebGL
 * testbar bleiben. Die Roboter-Rubrik ist **schreibgeschützt**: der Bestand
 * kommt aus `GET /robots` (die Kinematik ist hart verdrahtet, kein Formular —
 * Scope-Klärung im Parent #69), hier wird nur formatiert und je Roboter ein
 * statisches, eingechecktes PNG-Thumbnail verortet.
 */

import type { RobotDef } from "../api/projects";

/** Deutsche Anzeige-Zusammenfassung eines Roboters für die Galerie-Karte. */
export interface RobotSummary {
  /** z. B. „Reichweite 1300 mm". */
  reachText: string;
  /** z. B. „Traglast 10 kg" bzw. „Traglast unbekannt". */
  payloadText: string;
  /** z. B. „Druckraum 1000 × 2000 mm" (Höhe × Länge). */
  workspaceText: string;
  /** true → Hüllwerte sind noch vorläufig (Badge/Hinweis). */
  provisional: boolean;
}

/** Formatiert eine mm-Zahl kompakt (ganze Zahlen ohne Nachkomma). */
function mm(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 10) / 10);
}

/**
 * Baut die Karten-Zusammenfassung aus einer Roboterdefinition (rein, Issue #76):
 * Reichweite, Traglast (null = unbekannt), Druckraum-Hüllwerte + Vorläufig-Flag.
 */
export function summarizeRobot(robot: RobotDef): RobotSummary {
  const payloadText =
    robot.payload_kg == null ? "Traglast unbekannt" : `Traglast ${mm(robot.payload_kg)} kg`;
  return {
    reachText: `Reichweite ${mm(robot.reach_mm)} mm`,
    payloadText,
    workspaceText: `Druckraum ${mm(robot.max_print_height_mm)} × ${mm(
      robot.max_print_length_mm,
    )} mm`,
    provisional: robot.workspace_provisional,
  };
}

/**
 * Roboter-Name → Ordner-Slug der eingecheckten Assets (Issue #40/#41: die GLBs
 * des M1013 liegen unter `public/robots/m1013/`, der Roboter heißt aber
 * `doosan_m1013`). Der Slug streicht einen führenden Hersteller-Präfix
 * (`doosan_`) und normalisiert auf Kleinbuchstaben; unbekannte Roboter bekommen
 * einen best-effort-Slug, dessen PNG schlicht fehlen darf (dann Platzhalter).
 */
export function robotSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/^(doosan|kuka|abb|fanuc|ur|universal)[_-]+/, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Pfad des statischen PNG-Thumbnails eines Roboters (Issue #76). Liegt neben den
 * GLBs unter `./robots/<slug>/thumbnail.png` (relativer Vite-`base: "./"`-Pfad).
 * Fehlt die Datei, greift in der Karte der Platzhalter (kein Absturz) — die
 * Abbildung selbst wirft nie.
 */
export function robotThumbnailPath(name: string): string {
  return `./robots/${robotSlug(name)}/thumbnail.png`;
}

/**
 * Deep Module `ui/nozzle-schablone` — die reine Geometrie der Düsen-/Werkzeug-
 * Schablone der Live-Vorschau „Vorbereiten" (Druckplan S6, Issue #85, PRD B/#70).
 *
 * Ein Düsen-Stummel gleitet entlang der frisch gesliceten Bahn des Fokus-
 * Abschnitts. Die Pose je Bahnpunkt kommt **vorwärts** aus der **einen geteilten
 * Orientierungsquelle** {@link nozzleQuat} (TS-Zwilling von Core `nozzle_quat`,
 * #61) — **keine eigene Orientierungsformel** (Regressionsschutz #51/#58): so
 * kann die billige, IK-freie Schablone niemals vom vollen Arm-Lauf
 * auseinanderdriften, weil beide dieselbe Rotation ziehen.
 *
 * Rein aus der Bahn-Geometrie, **ohne Renderer und ohne IK** — per vitest-Golden
 * prüfbar (`nozzle-schablone.golden.json`, erzeugt vom Core über
 * `viewer/scripts/gen_goldens.py`, Paar `nozzle-schablone`). Die three.js-Darstellung + Animation
 * liegt getrennt in `render/schablone.ts` (Pure/DOM-Split wie face-align).
 *
 * Frame: kanonisch (x = Wandlänge/Fahrtrichtung, y = Wanddicke/Front, z = Höhe),
 * mm, Quaternion [w, x, y, z]. Wulstdicke = Strangbreite, Stapelung = Schichthöhe.
 */

import { type Quat, type Vec3, nozzleQuat } from "./nozzle-quat";

/** Eine Schablonen-Pose: Lage + Düsen-Orientierung an einem Bahnpunkt. */
export interface SchablonePose {
  pos_mm: Vec3;
  /** Düsen-Orientierung [w, x, y, z] aus {@link nozzleQuat} (geteilte Quelle). */
  quat: Quat;
}

/** Anstellung der Düse in Radiant (aus den effektiven Orientierungs-Params, #82). */
export interface SchabloneOrientation {
  leadRad: number;
  kippRad: number;
}

/** Ergebnis: die Posen entlang der Bahn + die Stummel-Maße (Wulst/Stapel). */
export interface SchabloneResult {
  poses: SchablonePose[];
  /** Wulstdicke = Strangbreite (mm) — Durchmesser des Düsen-Stummels. */
  beadWidthMm: number;
  /** Stapelung = Schichthöhe (mm). */
  layerHeightMm: number;
}

/**
 * Horizontale Bahntangente an Punkt `i` (Vorwärtsdifferenz; der letzte Punkt
 * erbt die Tangente des vorletzten). Nur (x, y) — die Höhe zählt für die
 * Orientierung nicht (Konvention Core `nozzle_quat`). Deckungsgleiche
 * (Null-)Nachbarn liefern eine degenerierte Tangente → {@link nozzleQuat} fällt
 * dann sauber auf senkrecht-von-oben zurück.
 */
export function pathTangent(path: readonly Vec3[], i: number): [number, number] {
  const n = path.length;
  if (n < 2) return [0, 0];
  const [a, b] = i < n - 1 ? [path[i], path[i + 1]] : [path[i - 1], path[i]];
  return [b[0] - a[0], b[1] - a[1]];
}

/**
 * Schablonen-Posen aus einer bekannten Bahn + Lead/Kipp — die Kernfunktion.
 *
 * Je Bahnpunkt: Tangente bilden, Orientierung **vorwärts** aus {@link nozzleQuat}
 * (der geteilten Quelle), Position = der Bahnpunkt selbst. Keine Renderer-, keine
 * IK-Abhängigkeit. Eine leere/einpunktige Bahn ergibt entsprechend 0/1 Posen
 * (letztere senkrecht von oben, mangels Tangente).
 */
export function schablonePoses(
  path: readonly Vec3[],
  orientation: SchabloneOrientation,
  beadWidthMm: number,
  layerHeightMm: number,
): SchabloneResult {
  const poses: SchablonePose[] = path.map((p, i) => ({
    pos_mm: [p[0], p[1], p[2]] as Vec3,
    quat: nozzleQuat(pathTangent(path, i), orientation.leadRad, orientation.kippRad),
  }));
  return { poses, beadWidthMm, layerHeightMm };
}

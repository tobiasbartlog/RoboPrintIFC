/**
 * Bahn-relative Düsen-Orientierung — der **TS-Zwilling** der geteilten
 * Orientierungsquelle `fgc.domain.orientation.nozzle_quat` (Scheibe 3, Issue #61).
 *
 * Dies ist **keine** neue Orientierungsformel: es ist die bit-gleiche Spiegelung
 * der einen Core-Funktion, aus der Slicer *und* `placement` ihre Rotation
 * ableiten (Regressionsschutz #51/#58). Die Live-Vorschau „Vorbereiten" (Issue
 * #85) darf die Düsen-Schablone nicht selbst neu ausrechnen — sie leitet die
 * Pose je Bahnpunkt **vorwärts** aus genau dieser Funktion ab, damit Schablone
 * und voller Arm-Lauf nie auseinanderdriften. Die Py↔TS-Parität ist per
 * geteiltem Golden bewiesen (`nozzle-quat.golden.json`, erzeugt vom Core via
 * `viewer/scripts/gen_goldens.py`, Paar `nozzle-quat` im Manifest `fgc.parity`).
 *
 * Konvention (ADR-006): Millimeter, Einheitsquaternion **[w, x, y, z]**; Winkel
 * in Radiant. Wandkoordinaten: x = Wandlänge, y = Wanddicke/Front, z = Höhe.
 * Vorzeichen: `+lead` = in Fahrtrichtung, `+kipp` = zur Wand-Außenseite (aus dem
 * CCW-Ring eindeutig, `n_out = tangent × ẑ`).
 */

export type Vec3 = [number, number, number];
export type Quat = [number, number, number, number]; // [w, x, y, z]

/** Düse senkrecht nach unten (Nullpunkt Lead 0 / Kipp 0) — 180° um Wand-x. */
export const NOZZLE_DOWN_QUAT: Quat = [0, 1, 0, 0];

function normalize3(v: Vec3): Vec3 | null {
  const n = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (n === 0) return null;
  return [v[0] / n, v[1] / n, v[2] / n];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** Einheitsquaternion einer Drehung `angleRad` um `axis` ([w, x, y, z]). */
function axisAngleQuat(axis: Vec3, angleRad: number): Quat {
  const unit = normalize3(axis);
  if (unit === null || angleRad === 0) return [1, 0, 0, 0];
  const half = angleRad / 2;
  const s = Math.sin(half);
  return [Math.cos(half), unit[0] * s, unit[1] * s, unit[2] * s];
}

/** Hamilton-Produkt `a ⊗ b` ([w, x, y, z]) — Verkettung `R_a @ R_b`. */
function quatMul(a: Quat, b: Quat): Quat {
  const [aw, ax, ay, az] = a;
  const [bw, bx, by, bz] = b;
  return [
    aw * bw - ax * bx - ay * by - az * bz,
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
  ];
}

/** Normiert und wählt das kanonische Vorzeichen `w ≥ 0` (wie Core `_canonical`). */
function canonical(q: Quat): Quat {
  const [w, x, y, z] = q;
  let n = Math.sqrt(w * w + x * x + y * y + z * z);
  if (n === 0) return NOZZLE_DOWN_QUAT;
  if (w < 0) n = -n;
  return [w / n, x / n, y / n, z / n];
}

/**
 * Düsen-Orientierung (Quaternion [w, x, y, z]) für eine Bahntangente + Anstellung.
 *
 * Bit-gleiche Spiegelung von `fgc.domain.orientation.nozzle_quat`: nur die
 * horizontale Tangenten-Komponente (x, y) zählt; 0/0 ⇒ exakt {@link NOZZLE_DOWN_QUAT}
 * (unabhängig von der Tangente), eine degenerierte (Null-)Tangente ebenfalls.
 * `+lead` kippt um `n_out` in Fahrtrichtung, `+kipp` um die Tangente zur
 * Wand-Außenseite.
 */
export function nozzleQuat(
  tangent: readonly [number, number] | Vec3,
  leadRad = 0,
  kippRad = 0,
): Quat {
  if (leadRad === 0 && kippRad === 0) return NOZZLE_DOWN_QUAT;
  const t = normalize3([Number(tangent[0]), Number(tangent[1]), 0]);
  if (t === null) return NOZZLE_DOWN_QUAT;
  const nOut = cross(t, [0, 0, 1]); // rechte Seite der Fahrt = Wand-Außenseite (CCW)
  const qLead = axisAngleQuat(nOut, leadRad); // +lead → Düse in Fahrtrichtung
  const qKipp = axisAngleQuat(t, -kippRad); // +kipp → Düse zur Außenseite (n_out)
  return canonical(quatMul(qLead, quatMul(qKipp, NOZZLE_DOWN_QUAT)));
}

/** Grad → Radiant (Formularwerte kommen in Grad, ADR-006 rechnet in Radiant). */
export function degToRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

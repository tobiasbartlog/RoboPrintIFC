/**
 * Präsentations-FK — Vorwärtskinematik allein zur Anzeige (ADR-007-Klarstellung
 * 2026-07-04). Aus den DH-Parametern der Roboterdefinition und den `joints_rad`
 * eines Trajektorien-Samples rechnet dieses Modul die Posen aller Glieder für
 * das Kapsel-Arm-Replay. Es erzeugt **keine** Entscheidungsdaten; alle Urteile
 * (Erreichbarkeit, Warnungen) kommen weiter als Core-Artefakt. Die Kette ist
 * Standard-DH und spiegelt `OpwKinematics.forward_matrix`/`link_frames` des Core
 * 1:1 — validiert per Golden-Testorakel (`fk.test.ts`, ADR-009).
 *
 * Reine Zahlenmathematik ohne three.js: 4×4-Matrizen als zeilenmajor `number[16]`
 * (Element (r,c) = m[r*4+c]), damit das Modul isoliert testbar bleibt.
 */

export interface DhParams {
  /** Gliedlänge a_i je Achse (mm). */
  a_mm: number[];
  /** Gliedversatz d_i je Achse (mm). */
  d_mm: number[];
  /** Verdrehung alpha_i je Achse (Radiant). */
  alpha_rad: number[];
}

/** 4×4-Transformation, zeilenmajor (Länge 16). */
export type Mat4 = number[];

/** Pose eines Glieds: Position (mm) + Einheitsquaternion [w, x, y, z]. */
export interface LinkPose {
  pos_mm: [number, number, number];
  quat: [number, number, number, number];
}

export function identity(): Mat4 {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

/** Standard-DH-Matrix aus (a, d, alpha, theta) — identisch zur Core-Kette. */
export function dhMatrix(a: number, d: number, alpha: number, theta: number): Mat4 {
  const c = Math.cos(theta);
  const s = Math.sin(theta);
  const ca = Math.cos(alpha);
  const sa = Math.sin(alpha);
  return [
    c, -s * ca, s * sa, a * c,
    s, c * ca, -c * sa, a * s,
    0, sa, ca, d,
    0, 0, 0, 1,
  ];
}

/** Matrixprodukt A·B (beide zeilenmajor 4×4). */
export function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Array<number>(16).fill(0);
  for (let r = 0; r < 4; r++) {
    for (let col = 0; col < 4; col++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += a[r * 4 + k] * b[k * 4 + col];
      out[r * 4 + col] = sum;
    }
  }
  return out;
}

/**
 * Kumulierte Frames aller Glieder (Basis … Flansch) in Roboterbasis-Koordinaten.
 * Gibt 7 Matrizen zurück: Index 0 = Basis (Identität), Index 6 = Flansch.
 * Entspricht `OpwKinematics.link_frames` (6 Achsen erwartet).
 */
export function forwardChain(dh: DhParams, joints_rad: number[]): Mat4[] {
  const n = joints_rad.length;
  if (dh.a_mm.length !== n || dh.d_mm.length !== n || dh.alpha_rad.length !== n) {
    throw new Error(
      `FK: DH-Parameter (${dh.a_mm.length}) und Gelenkzahl (${n}) passen nicht zusammen`,
    );
  }
  let t = identity();
  const frames: Mat4[] = [identity()];
  for (let i = 0; i < n; i++) {
    t = multiply(t, dhMatrix(dh.a_mm[i], dh.d_mm[i], dh.alpha_rad[i], joints_rad[i]));
    frames.push(t.slice());
  }
  return frames;
}

/** Positionsspalte (mm) einer Transformation. */
export function positionOf(m: Mat4): [number, number, number] {
  return [m[3], m[7], m[11]];
}

/**
 * Rotationsanteil einer Transformation als Einheitsquaternion [w, x, y, z],
 * kanonisch mit w ≥ 0 (wie der Core-Konverter). Nur für Tests/Diagnose nötig;
 * das Rendering nutzt die Matrix direkt.
 */
export function quaternionOf(m: Mat4): [number, number, number, number] {
  const r00 = m[0], r01 = m[1], r02 = m[2];
  const r10 = m[4], r11 = m[5], r12 = m[6];
  const r20 = m[8], r21 = m[9], r22 = m[10];
  const trace = r00 + r11 + r22;
  let w: number, x: number, y: number, z: number;
  if (trace > 0) {
    const sc = Math.sqrt(trace + 1.0) * 2;
    w = 0.25 * sc;
    x = (r21 - r12) / sc;
    y = (r02 - r20) / sc;
    z = (r10 - r01) / sc;
  } else if (r00 > r11 && r00 > r22) {
    const sc = Math.sqrt(1.0 + r00 - r11 - r22) * 2;
    w = (r21 - r12) / sc;
    x = 0.25 * sc;
    y = (r01 + r10) / sc;
    z = (r02 + r20) / sc;
  } else if (r11 > r22) {
    const sc = Math.sqrt(1.0 + r11 - r00 - r22) * 2;
    w = (r02 - r20) / sc;
    x = (r01 + r10) / sc;
    y = 0.25 * sc;
    z = (r12 + r21) / sc;
  } else {
    const sc = Math.sqrt(1.0 + r22 - r00 - r11) * 2;
    w = (r10 - r01) / sc;
    x = (r02 + r20) / sc;
    y = (r12 + r21) / sc;
    z = 0.25 * sc;
  }
  let n = Math.hypot(w, x, y, z);
  if (w < 0) n = -n; // kanonisch: w ≥ 0
  return [w / n, x / n, y / n, z / n];
}

/** Geodätischer Winkel (rad) zwischen zwei Quaternionen, vorzeichenunabhängig. */
export function orientationAngle(
  a: [number, number, number, number],
  b: [number, number, number, number],
): number {
  const dot = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]);
  return 2 * Math.acos(Math.min(1, dot));
}

/** Inverse einer starren Transformation (R,t) → (Rᵀ, −Rᵀt). */
export function invertRigid(m: Mat4): Mat4 {
  const r00 = m[0], r01 = m[1], r02 = m[2];
  const r10 = m[4], r11 = m[5], r12 = m[6];
  const r20 = m[8], r21 = m[9], r22 = m[10];
  const tx = m[3], ty = m[7], tz = m[11];
  // Rᵀ
  const i00 = r00, i01 = r10, i02 = r20;
  const i10 = r01, i11 = r11, i12 = r21;
  const i20 = r02, i21 = r12, i22 = r22;
  // −Rᵀ·t
  const nx = -(i00 * tx + i01 * ty + i02 * tz);
  const ny = -(i10 * tx + i11 * ty + i12 * tz);
  const nz = -(i20 * tx + i21 * ty + i22 * tz);
  return [
    i00, i01, i02, nx,
    i10, i11, i12, ny,
    i20, i21, i22, nz,
    0, 0, 0, 1,
  ];
}

/** Frame (Position + Quaternion) als starre 4×4-Transformation. */
export function frameToMat(
  pos_mm: [number, number, number],
  quat: [number, number, number, number],
): Mat4 {
  const [w, x, y, z] = quat;
  const n = Math.hypot(w, x, y, z) || 1;
  const nw = w / n, nx = x / n, ny = y / n, nz = z / n;
  return [
    1 - 2 * (ny * ny + nz * nz), 2 * (nx * ny - nz * nw), 2 * (nx * nz + ny * nw), pos_mm[0],
    2 * (nx * ny + nz * nw), 1 - 2 * (nx * nx + nz * nz), 2 * (ny * nz - nx * nw), pos_mm[1],
    2 * (nx * nz - ny * nw), 2 * (ny * nz + nx * nw), 1 - 2 * (nx * nx + ny * ny), pos_mm[2],
    0, 0, 0, 1,
  ];
}

/**
 * **Legacy-Anker** (nur für Altläufe ohne `meta.base_frame`, Issue #66): legt den
 * FK-Flansch (Basiskoordinaten) auf ein Ziel-Frame (Wandkoordinaten):
 * ``anchor · flange = target``. Er legt bewusst den **Flansch** (nicht den TCP)
 * aufs Ziel und ist nicht konstant — bei eingefrorenen Gelenken schleift er die
 * Basis die TCP-Bahn entlang. Der bevorzugte Pfad verankert den Arm stattdessen an
 * der festen Basis (`base_frame`); dann articulieren die Gelenke und der TCP druckt.
 */
export function anchorFlangeToTarget(flange: Mat4, target: Mat4): Mat4 {
  return multiply(target, invertRigid(flange));
}

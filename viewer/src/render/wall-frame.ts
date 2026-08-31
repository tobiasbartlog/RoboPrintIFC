/**
 * Wand-Pose in der Modellübersicht (Issue #99): das Wand-lokale System, an dem
 * alle Zerlegungs-Overlays (Schnittebenen, Abschnitts-Quader, Platzierungs-
 * Marker, Live-Vorschau) ausgerichtet werden.
 *
 * Vorher leiteten die Overlay-Module das Wand-System aus der **achsparallelen
 * Bounding-Box** ab („Längsachse = größere horizontale Ausdehnung") — bei einer
 * Wand, die gedreht zu den Weltachsen steht, lagen Ebenen und Quader dadurch
 * schräg zur Wand und waren zu lang (Bbox = Diagonale). Der Core rechnet die
 * Zerlegung dagegen im PCA-Wandframe (`_wall_local_mesh`, ADR-006: x entlang
 * der Wandlänge = 2D-PCA-Hauptachse im Grundriss, y Dicke, z Höhe ab Wandfuß).
 * Dieses Modul repliziert genau diese Konvention — inklusive des
 * deterministischen Vorzeichen-Fixups (Komponentensumme der Achse ≥ 0), damit
 * Schnittpositionen und Abschnittsgrenzen (Wand-lokale mm) vorzeichenrichtig
 * auf der echten Wandachse landen.
 *
 * Reine Darstellungsmathematik (ADR-007): kein Urteil, keine Kinematik — nur
 * die Pose, an der die Overlays hängen. Die PCA (`wallFrameFromPoints`) ist
 * three.js-frei und per vitest getestet; `wallFrameFromObject` sammelt nur die
 * Vertices im Gruppen-Frame ein.
 *
 * Koordinaten: Daten-Konvention der Artefakte (mm, z hoch) — der Gruppen-Frame
 * ist der z-hoch-Frame der world-Gruppe (bereits nach three.js y-hoch rotiert).
 */

import * as THREE from "three";

/**
 * userData-Flag für reine Deko-Kinder am Wand-Mesh (z. B. der Eignungs-
 * Sockel-Streifen aus #113, dessen BoxGeometry aus der **achsparallelen**
 * lokalen Bbox kommt): solche Meshes gehören nicht zur Wandgeometrie und
 * werden bei der PCA übergangen — sonst verfälschen ihre Vertices Achse und
 * Maße des Wand-Frames (bei einer 32°-Wand: yaw 32°→22,6°, Dicke 260→2339 mm)
 * und alle daran hängenden Overlays liegen schräg (Regression von #99).
 */
export const WALL_DECORATION_FLAG = "wallDecoration";

/**
 * Die Wand-Pose im z-hoch-Gruppen-Frame plus die Wandmaße im Wand-lokalen
 * System. `origin`/`yaw` spannen das Wand-System auf: `origin` ist der
 * Wand-lokale Nullpunkt (Vertex-Mittel, wie die Core-PCA — dort leben die
 * Schnittpositionen und Abschnittsgrenzen), `yaw` die Drehung der Wand-x-Achse
 * gegen die Gruppen-x-Achse. `center` ist die Extent-Mitte **Wand-lokal
 * relativ zum Nullpunkt** (für Spannweiten/Überstände); `zMin` der Wandfuß
 * (Gruppen-z — invariant unter der Drehung um z).
 */
export interface WallFrame {
  origin: { x: number; y: number };
  yaw: number;
  center: { x: number; y: number };
  length_mm: number;
  thickness_mm: number;
  height_mm: number;
  zMin: number;
}

/**
 * PCA-Wandframe aus einer Punktwolke (mm, z hoch) — reine Funktion, spiegelt
 * `_wall_local_mesh` (Core): 2D-PCA im Grundriss, Hauptachse = Wandlänge,
 * Vorzeichen deterministisch fixiert (Komponentensumme ≥ 0). Liefert `null`
 * bei < 3 Punkten oder degenerierter Punktwolke (keine Ausdehnung).
 */
export function wallFrameFromPoints(
  points: readonly (readonly [number, number, number])[],
): WallFrame | null {
  if (points.length < 3) return null;

  let mx = 0;
  let my = 0;
  for (const [x, y] of points) {
    mx += x;
    my += y;
  }
  mx /= points.length;
  my /= points.length;

  // 2×2-Kovarianz im Grundriss (Mittel abgezogen).
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (const [x, y] of points) {
    const dx = x - mx;
    const dy = y - my;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  if (sxx + syy < 1e-12) return null;

  // Größter Eigenvektor (geschlossene Form): Hauptachse = Wandlänge.
  const lambdaMax = (sxx + syy) / 2 + Math.sqrt(((sxx - syy) / 2) ** 2 + sxy * sxy);
  let ax: number;
  let ay: number;
  if (Math.abs(sxy) > 1e-9 * (sxx + syy)) {
    ax = sxy;
    ay = lambdaMax - sxx;
  } else {
    // Diagonale Kovarianz: Achse ist x oder y.
    [ax, ay] = sxx >= syy ? [1, 0] : [0, 1];
  }
  const norm = Math.hypot(ax, ay);
  ax /= norm;
  ay /= norm;
  // Vorzeichen-Fixup wie im Core (`along.sum() < 0` → negieren) — damit die
  // Wand-lokale +x-Richtung mit dem Frame übereinstimmt, in dem der Core
  // schneidet (decompose.apply); sonst erschienen Schnitte gespiegelt.
  if (ax + ay < 0) {
    ax = -ax;
    ay = -ay;
  }
  // Rechtshändiges System: Wand-y (Dicke) = 90° links von Wand-x.
  const nx = -ay;
  const ny = ax;

  let xMin = Number.POSITIVE_INFINITY;
  let xMax = Number.NEGATIVE_INFINITY;
  let yMin = Number.POSITIVE_INFINITY;
  let yMax = Number.NEGATIVE_INFINITY;
  let zMin = Number.POSITIVE_INFINITY;
  let zMax = Number.NEGATIVE_INFINITY;
  for (const [x, y, z] of points) {
    const dx = x - mx;
    const dy = y - my;
    const u = dx * ax + dy * ay;
    const v = dx * nx + dy * ny;
    if (u < xMin) xMin = u;
    if (u > xMax) xMax = u;
    if (v < yMin) yMin = v;
    if (v > yMax) yMax = v;
    if (z < zMin) zMin = z;
    if (z > zMax) zMax = z;
  }

  return {
    origin: { x: mx, y: my },
    yaw: Math.atan2(ay, ax),
    center: { x: (xMin + xMax) / 2, y: (yMin + yMax) / 2 },
    length_mm: xMax - xMin,
    thickness_mm: yMax - yMin,
    height_mm: zMax - zMin,
    zMin,
  };
}

/**
 * PCA-Wandframe eines Wand-Objekts in den lokalen Koordinaten einer Gruppe:
 * sammelt alle Mesh-Vertices (in den Gruppen-Frame transformiert) und leitet
 * daraus die Pose ab. Liefert `null`, wenn die Wand keine Geometrie liefert.
 */
export function wallFrameFromObject(
  wallObject: THREE.Object3D,
  worldGroup: THREE.Object3D,
): WallFrame | null {
  worldGroup.updateWorldMatrix(true, false);
  wallObject.updateWorldMatrix(true, true);
  const toGroup = new THREE.Matrix4().copy(worldGroup.matrixWorld).invert();
  const points: [number, number, number][] = [];
  const v = new THREE.Vector3();
  wallObject.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh || !mesh.geometry) return;
    // Deko-Kinder (Sockel-Streifen #113 u. Ä.) überspringen — nur die echte
    // Wandgeometrie bestimmt den Frame (s. WALL_DECORATION_FLAG).
    if (mesh.userData[WALL_DECORATION_FLAG]) return;
    const pos = mesh.geometry.getAttribute("position");
    if (!pos) return;
    const m = new THREE.Matrix4().multiplyMatrices(toGroup, mesh.matrixWorld);
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos as THREE.BufferAttribute, i).applyMatrix4(m);
      points.push([v.x, v.y, v.z]);
    }
  });
  return wallFrameFromPoints(points);
}

/**
 * Hängt ein Overlay-Objekt an die Wand-Pose: Position auf den Wand-lokalen
 * Nullpunkt, Drehung um z auf die Wandachse. Kinder rechnen dann rein
 * Wand-lokal (x Länge, y Dicke, z Höhe — `zMin` bleibt absolut, da die
 * Drehung um z die Höhe nicht berührt).
 */
export function applyWallFrame(obj: THREE.Object3D, frame: WallFrame): void {
  obj.position.set(frame.origin.x, frame.origin.y, 0);
  obj.rotation.set(0, 0, frame.yaw);
}

/** Wand-lokalen Punkt in den Gruppen-Frame abbilden (reine Funktion). */
export function wallLocalToGroup(
  frame: WallFrame,
  p: readonly [number, number, number],
): [number, number, number] {
  const c = Math.cos(frame.yaw);
  const s = Math.sin(frame.yaw);
  return [
    frame.origin.x + c * p[0] - s * p[1],
    frame.origin.y + s * p[0] + c * p[1],
    p[2],
  ];
}

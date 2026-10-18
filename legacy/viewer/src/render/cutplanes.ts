/**
 * Schnittebenen des Zerlegungsvorschlags in 3D (Issue #24; Drag-Editing #25).
 *
 * Zeigt die achsparallelen Schnittebenen (horizontal = Höhenstufen, vertikal =
 * Längenteilung) als semi-transparente Flächen in der Modellübersicht. Reine
 * Darstellungsmathematik (ADR-007-Klarstellung): Lage und Ausdehnung werden aus
 * der Bounding-Box des Wand-Meshes abgeleitet — kein Urteil, keine Kinematik.
 * Die Ampel-Färbung je Abschnitt und die Platzierungen zeigt die Liste im Reiter
 * Druckplan; hier geht es nur um die Schnittgeometrie.
 *
 * Jede Ebene trägt in ``mesh.userData`` ihren Index in ``cuts`` sowie die
 * Drag-Achse (Weltraum-Einheitsvektor) und den Ursprung — main.ts nutzt das für
 * das Draggen (Pointer-Events, Achsen-Constraint-Ebene). Die eigentliche
 * Zustandsänderung (welcher Schnitt auf welche Position) läuft ausschließlich
 * über `ui/cutplan-state.ts` (`moveCut`) — dieselbe Funktion wie das Zahlenfeld,
 * damit Drag und Zahlenfeld synchron bleiben (Issue #25, Architektur-Leitplanke).
 *
 * Koordinaten: Daten-Konvention der Artefakte (mm, z hoch) — die Gruppe wird in
 * die world-Gruppe gehängt (bereits nach three.js y-hoch rotiert) und selbst an
 * die **Wand-Pose** (Issue #99, `wall-frame.ts`: PCA statt achsparalleler
 * Bbox — sonst liegen die Ebenen bei gedrehten Wänden schräg zur Wand) gesetzt.
 * Die Ebenen-Specs rechnen rein Wand-lokal (x entlang Länge, y Dicke, z ab
 * Wandfuß) — dasselbe System, in dem der Core schneidet (decompose.apply).
 */

import * as THREE from "three";

import type { Cut } from "../api/projects";
import {
  type WallFrame,
  applyWallFrame,
  wallFrameFromObject,
  wallLocalToGroup,
} from "./wall-frame";

const CUT_COLOR = 0xffb300; // amber — bewusst außerhalb der Eignungs-Palette
const CUT_COLOR_HOVER = 0xffd54f;

/** Überstand der Ebenen über die Wand hinaus (mm) — macht sie sichtbar und
 *  greifbar; exakt wandgroße Ebenen lägen komplett im Wandinneren (Issue #34/#37). */
export const CUT_PLANE_OVERHANG_MM = 150;

/** Reine Geometrie-Spec einer Schnittebene im Wand-lokalen Frame (Issue #34/#99). */
export interface CutPlaneSpec {
  /** PlaneGeometry-Spannweiten [Breite, Höhe] (mm), inkl. Überstand. */
  size: [number, number];
  /** Euler-Rotation (rad, Reihenfolge XYZ) — PlaneGeometry-Normale ist +z. */
  rotation: [number, number, number];
  /** Ebenen-Mittelpunkt im Wand-lokalen Frame (mm; z absolut, ab Wandfuß `zMin`). */
  origin: [number, number, number];
  /** Drag-Achse im Wand-lokalen Frame (Einheitsvektor). */
  axisLocal: [number, number, number];
}

/**
 * Orientierung/Lage einer Schnittebene — reine Funktion, per vitest gegen die
 * z-hoch-Konvention verifiziert (Issue #34: y-hoch-Rotationen im z-hoch-Frame
 * ließen Höhenschnitte wandparallel im Wandinneren verschwinden). Seit Issue
 * #99 rechnet die Spec **Wand-lokal** (x entlang Wandlänge, Nullpunkt = PCA-
 * Nullpunkt des Core): die Schnittposition liegt direkt auf der Wand-x-Achse,
 * die Drehung in den Gruppen-Frame übernimmt die Ebenen-Gruppe (`applyWallFrame`).
 */
export function cutPlaneSpec(cut: Cut, wall: WallFrame): CutPlaneSpec {
  const o2 = 2 * CUT_PLANE_OVERHANG_MM;
  if (cut.orientation === "horizontal") {
    // PlaneGeometry liegt in der xy-Ebene (Normale +z) — im z-hoch-Frame ist
    // das bereits horizontal: keine Rotation.
    return {
      size: [wall.length_mm + o2, wall.thickness_mm + o2],
      rotation: [0, 0, 0],
      origin: [wall.center.x, wall.center.y, wall.zMin + cut.position_mm],
      axisLocal: [0, 0, 1],
    };
  }
  // Normale entlang x; Breite (Dicke) → y, Höhe → z: zyklische Drehung x→y→z→x.
  return {
    size: [wall.thickness_mm + o2, wall.height_mm + o2],
    rotation: [Math.PI / 2, Math.PI / 2, 0],
    origin: [cut.position_mm, wall.center.y, wall.zMin + wall.height_mm / 2],
    axisLocal: [1, 0, 0],
  };
}

/** Eine drag-fähige Schnittebene: Mesh + Index in `cuts` + Drag-Achse (Weltraum). */
export interface CutPlaneHandle {
  mesh: THREE.Mesh;
  cutIndex: number;
  orientation: Cut["orientation"];
  /** Ursprung der Drag-Achse im Weltraum (Szenen-Koordinaten). */
  origin: THREE.Vector3;
  /** Richtung der Drag-Achse im Weltraum (Einheitsvektor). */
  axis: THREE.Vector3;
}

export interface CutPlanesView {
  group: THREE.Group;
  handles: CutPlaneHandle[];
  /** Wandausdehnung im Wand-System (mm) — fürs Clamping beim Draggen. */
  bounds: { length_mm: number; height_mm: number };
}

const EMPTY_VIEW: CutPlanesView = {
  group: emptyGroup(),
  handles: [],
  bounds: { length_mm: 0, height_mm: 0 },
};

function emptyGroup(): THREE.Group {
  const g = new THREE.Group();
  g.name = "decompose-cut-planes";
  return g;
}

/**
 * Baut die Schnittebenen-Gruppe relativ zum Wand-Objekt: die Gruppe hängt an
 * der PCA-Wand-Pose (Issue #99, `wall-frame.ts`), die Ebenen rechnen Wand-lokal.
 * Liefert eine leere Gruppe (keine Handles), wenn keine Schnitte vorliegen oder
 * die Wand keine Geometrie liefert.
 */
export function buildCutPlanes(
  cuts: Cut[],
  wallObject: THREE.Object3D,
  worldGroup: THREE.Object3D,
): CutPlanesView {
  const group = emptyGroup();
  if (cuts.length === 0) return { ...EMPTY_VIEW, group };

  const frame = wallFrameFromObject(wallObject, worldGroup);
  if (!frame) return { ...EMPTY_VIEW, group };
  applyWallFrame(group, frame);

  // Flächige Glas-Ebenen (Scheibe 9, #113): amber, ~12 % Deckkraft — die Fläche
  // bleibt durchscheinend, die Wand/Abschnitte scheinen durch. Die volle Kante
  // (unten) übernimmt eine separate Linie (`edge`), damit der Schnitt greifbar bleibt.
  const material = new THREE.MeshStandardMaterial({
    color: CUT_COLOR,
    roughness: 0.6,
    metalness: 0,
    transparent: true,
    opacity: 0.12,
    side: THREE.DoubleSide,
    depthWrite: false,
  });

  worldGroup.updateWorldMatrix(true, false);
  const handles: CutPlaneHandle[] = [];

  cuts.forEach((cut, cutIndex) => {
    const spec = cutPlaneSpec(cut, frame);
    const geo = new THREE.PlaneGeometry(spec.size[0], spec.size[1]);
    const plane = new THREE.Mesh(geo, material.clone());
    plane.rotation.set(spec.rotation[0], spec.rotation[1], spec.rotation[2]);
    plane.position.set(spec.origin[0], spec.origin[1], spec.origin[2]);
    plane.userData = { cutIndex, orientation: cut.orientation };

    // Voll deckende Unterkante (3 px optisch) — Akzent-Linie an der lokalen
    // Unterkante der PlaneGeometry (y = -h/2); erbt Rotation/Lage der Ebene.
    const hw = spec.size[0] / 2;
    const hh = spec.size[1] / 2;
    const edgeGeo = new THREE.BufferGeometry();
    edgeGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute([-hw, -hh, 0, hw, -hh, 0], 3),
    );
    const edge = new THREE.LineSegments(
      edgeGeo,
      new THREE.LineBasicMaterial({ color: CUT_COLOR, transparent: true, opacity: 0.95 }),
    );
    edge.raycast = () => {}; // reine Deko — Drag/Picking der Ebene unverändert
    plane.add(edge);
    group.add(plane);

    // Drag-Achse/Anker in den Weltraum: Wand-lokal → Gruppen-Frame (Wand-Pose)
    // → Welt (worldGroup) — die Achse folgt damit der echten Wandachse (#99).
    const axis = new THREE.Vector3(...spec.axisLocal)
      .applyAxisAngle(new THREE.Vector3(0, 0, 1), frame.yaw)
      .transformDirection(worldGroup.matrixWorld);
    const worldOrigin = new THREE.Vector3(...wallLocalToGroup(frame, spec.origin));
    worldGroup.localToWorld(worldOrigin);
    handles.push({ mesh: plane, cutIndex, orientation: cut.orientation, origin: worldOrigin, axis });
  });

  return { group, handles, bounds: { length_mm: frame.length_mm, height_mm: frame.height_mm } };
}

/** Hebt eine Schnittebene optisch hervor (Hover/Drag) bzw. setzt sie zurück. */
export function setCutPlaneHighlighted(mesh: THREE.Mesh, highlighted: boolean): void {
  const mat = mesh.material as THREE.MeshStandardMaterial;
  mat.color.setHex(highlighted ? CUT_COLOR_HOVER : CUT_COLOR);
  mat.opacity = highlighted ? 0.24 : 0.12;
}

/**
 * Baut eine Hilfsebene für achsen-beschränktes Draggen (Standardtrick): die
 * Ebene enthält die Drag-Achse und ist so orientiert, dass sie der Kamera
 * möglichst zugewandt ist — Mausbewegungen quer zur Achse ändern dadurch
 * stabil nur die Position entlang der Achse.
 */
export function axisDragPlane(
  origin: THREE.Vector3,
  axis: THREE.Vector3,
  camera: THREE.Camera,
): THREE.Plane {
  const viewDir = new THREE.Vector3();
  camera.getWorldDirection(viewDir);
  let right = new THREE.Vector3().crossVectors(viewDir, axis);
  if (right.lengthSq() < 1e-8) {
    right = new THREE.Vector3(1, 0, 0).cross(axis);
    if (right.lengthSq() < 1e-8) right = new THREE.Vector3(0, 1, 0).cross(axis);
  }
  right.normalize();
  const normal = new THREE.Vector3().crossVectors(axis, right).normalize();
  return new THREE.Plane().setFromNormalAndCoplanarPoint(normal, origin);
}

/** Signierte Distanz eines Punkts entlang der Achse, relativ zu `origin`. */
export function projectOntoAxis(point: THREE.Vector3, origin: THREE.Vector3, axis: THREE.Vector3): number {
  return point.clone().sub(origin).dot(axis);
}

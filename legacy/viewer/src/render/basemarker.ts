/**
 * Basis-Marker einer geplanten Platzierung (Issue #22/#27): zeigt die
 * *geplante* Roboterbasis-Lage als Zylinder + Achsenkreuz an.
 *
 * Reine Darstellungsmathematik (ADR-007-Klarstellung) — kein Urteil, keine
 * Kinematik. Ein **Plan**, kein Setup (ADR-006): verbindlich wird die
 * Basis-Lage erst durchs Antasten. `baseMarkerPosition`/`placeBaseMarkerInBox`
 * sind Box-basiert: die Aufstell-Sequenz (Issue #27) speist sie mit
 * Wand-lokalen Boxen aus den Toolpath-Targets — dort ist achsparallel korrekt.
 * Der frühere Gesamtwand-Marker der gewählten Platzierung (#22) ist mit
 * Issue #134 entfallen; die Abschnitts-Marker (#93) leben in
 * `placement-markers.ts`.
 *
 * Koordinaten: Daten-Konvention der Artefakte (mm, z hoch) — der Marker wird
 * in die world-Gruppe gehängt, die bereits nach three.js (y hoch) rotiert.
 */

import * as THREE from "three";

const MARKER_COLOR = 0x4fc3f7; // cyan — bewusst außerhalb der Eignungs-Palette
const PEDESTAL_COLOR = 0x8a9099;
const BASE_RADIUS_MM = 180;

export interface PlacementPose {
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
}

/** Achsparallele Bounding-Box in Daten-Koordinaten (mm, z hoch). */
export interface BoxMinMax {
  min: [number, number, number];
  max: [number, number, number];
}

/**
 * Reine Positionsmathematik des Basis-Markers (ADR-007): aus der Bounding-Box
 * der Wand/des Abschnitts + der geplanten Platzierung die Basis-Lage. Längsachse
 * = größere horizontale Ausdehnung (x oder y); `lateral` läuft entlang, `standoff`
 * vor der Front (halbe Dicke + Abstand), z am Fuß der Box **plus Aufstellhöhe**
 * — die Position IST die Basis (Issue #133; vorher hob `buildBaseMarker` die
 * Scheibe intern an). Getrennt von three.js, damit die Aufstell-Sequenz
 * (Issue #27) den Basis-Sprung testbar berechnen kann.
 */
export function baseMarkerPosition(
  box: BoxMinMax,
  pose: PlacementPose,
): [number, number, number] {
  const sx = box.max[0] - box.min[0];
  const sy = box.max[1] - box.min[1];
  const cx = (box.min[0] + box.max[0]) / 2;
  const cy = (box.min[1] + box.max[1]) / 2;
  const alongX = sx >= sy;
  const halfThickness = (alongX ? sy : sx) / 2;
  const normalOffset = halfThickness + pose.standoff_mm;
  return [
    cx + (alongX ? pose.lateral_mm : normalOffset),
    cy + (alongX ? normalOffset : pose.lateral_mm),
    box.min[2] + pose.stand_height_mm,
  ];
}

/**
 * Baut den Marker: Basis-Scheibe + Achsenkreuz + (bei Podest) Sockelquader.
 * Der Gruppen-Nullpunkt liegt AUF der Basis-Höhe (Issue #133) — der Aufrufer
 * positioniert den Marker also direkt an der Basis (z. B. Boden + absolute
 * Aufstellhöhe); der Podest-Sockel hängt von der Basis bis zum Boden herab.
 */
export function buildBaseMarker(pose: PlacementPose): THREE.Group {
  const group = new THREE.Group();
  group.name = "placement-base-marker";

  // Basis-Scheibe (Zylinderachse auf z gedreht — Datenkonvention z hoch).
  const discGeo = new THREE.CylinderGeometry(BASE_RADIUS_MM, BASE_RADIUS_MM, 40, 32);
  discGeo.rotateX(Math.PI / 2);
  const disc = new THREE.Mesh(
    discGeo,
    new THREE.MeshStandardMaterial({ color: MARKER_COLOR, transparent: true, opacity: 0.85 }),
  );
  disc.position.z = 20;
  group.add(disc);

  // Podest-Sockel, falls Aufstellhöhe > 0: reicht von der Basis (Nullpunkt)
  // bis zum Boden hinunter — Höhe = Aufstellhöhe (Issue #133).
  if (pose.stand_height_mm > 0) {
    const pedGeo = new THREE.BoxGeometry(400, 400, pose.stand_height_mm);
    const pedestal = new THREE.Mesh(
      pedGeo,
      new THREE.MeshStandardMaterial({
        color: PEDESTAL_COLOR,
        transparent: true,
        opacity: 0.45,
      }),
    );
    pedestal.position.z = -pose.stand_height_mm / 2;
    group.add(pedestal);
  }

  // Achsenkreuz auf Basis-Höhe: macht die geplante Basis als Frame lesbar.
  const axes = new THREE.AxesHelper(350);
  axes.position.z = 40;
  group.add(axes);

  return group;
}

// Das frühere `placeBaseMarker` (Gesamtwand-Basis-Marker am Wand-Objekt, #22/#99)
// ist mit Issue #134 entfallen — die Abschnitts-Marker (#93) leben in
// `placement-markers.ts`, die Aufstell-Sequenz nutzt `placeBaseMarkerInBox`.

/**
 * Podest-Sockel für den Replay-Arm (Issue #135, Muster des #133-Sockels oben):
 * ein halbtransparenter Quader, der von der Basis (Nullpunkt des Meshes) um
 * `heightMm` bis zum Boden hinunterreicht. Der Aufrufer positioniert das Mesh
 * an der Replay-Basis (`meta.base_frame`, `trajectory/replay-anchor.ts`).
 */
export function buildReplayPedestal(heightMm: number): THREE.Mesh {
  const geo = new THREE.BoxGeometry(400, 400, heightMm);
  // Nullpunkt des Meshes = Sockel-OBERKANTE (die Basis): der Aufrufer setzt
  // `position` direkt auf die Basis-Lage, der Quader hängt nach unten.
  geo.translate(0, 0, -heightMm / 2);
  const pedestal = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({
      color: PEDESTAL_COLOR,
      transparent: true,
      opacity: 0.45,
    }),
  );
  pedestal.name = "replay-pedestal";
  return pedestal;
}

/**
 * Positioniert den Marker relativ zu einer bereits bekannten Bounding-Box
 * (Daten-Koordinaten). Genutzt von der Aufstell-Sequenz (Issue #27), die die
 * Box je Abschnitt aus dessen Toolpath-Targets ableitet (reine Darstellung).
 */
export function placeBaseMarkerInBox(
  marker: THREE.Group,
  box: BoxMinMax,
  pose: PlacementPose,
): boolean {
  const p = baseMarkerPosition(box, pose);
  marker.position.set(p[0], p[1], p[2]);
  return true;
}


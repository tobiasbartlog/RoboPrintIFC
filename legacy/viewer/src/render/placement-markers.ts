/**
 * Basis-Marker **aller** Teil-Platzierungen + echtes M1013-Mesh am Fokus
 * (Druckplan-Neuordnung II S4, Issue #93, PRD #88).
 *
 * Der Core rechnet je Abschnitt eine Platzierung (`DecompositionSection.placement`,
 * ADR-022) samt Bewertung (`status.reachable_fraction`, `status.kinematic_margin`).
 * Dieses Modul macht sie **sichtbar**: vor der Wand erscheint je Teil ein
 * Basis-Marker (Position aus lateral/standoff, Höhe aus der Aufstellhöhe/Podest);
 * das fokussierte Teil zeigt statt des Markers das echte Roboter-Mesh in neutraler
 * Pose an seiner Platzierung.
 *
 * Reine **Darstellungsmathematik** (ADR-007-Klarstellung): die Marker-/Mesh-Pose
 * leitet sich aus der Platzierung + den Wandmaßen ab — kein Urteil, keine
 * Kinematik. Die Bewertung (erreichbarer Anteil, Marge) wird nur *gelesen*, nie
 * abgeleitet. Ein **Plan**, kein Setup (ADR-006): verbindlich wird die Basis-Lage
 * erst durchs Antasten.
 *
 * Die reinen Pose-Funktionen (`sectionPlacementBox`, `sectionMarkerPosition`,
 * `sectionBaseFrame`) sind three.js-frei und per vitest getestet; die drei.js-
 * Objekte (Marker-Gruppe, Fokus-Umschaltung) liegen dünn darum herum — der Arm
 * selbst kommt aus der bestehenden `ArmView` (Trajektorien-Player, #40/#41).
 *
 * Koordinaten: Daten-Konvention der Artefakte (mm, z hoch) — die Marker-Gruppe
 * wird in die world-Gruppe gehängt (bereits nach three.js y-hoch rotiert) und
 * selbst an die PCA-Wand-Pose gesetzt (Issue #99, `applyWallFrame`); die reinen
 * Pose-Funktionen rechnen Wand-lokal wie bei `cutplanes.ts`/`sections.ts`. Nur
 * `sectionBaseFrame` liefert den fertig komponierten Gruppen-Frame (der Arm
 * hängt direkt in der world-Gruppe, nicht in der Marker-Gruppe).
 */

import * as THREE from "three";

import type { DecompositionSection, SectionOverride } from "../api/projects";
import type { Mat4 } from "../kinematics/fk";
import { effectivePlacement } from "../ui/effective-placement";
import { buildBaseMarker, type BoxMinMax } from "./basemarker";
import { type WallFrame, applyWallFrame, wallLocalToGroup } from "./wall-frame";

/**
 * Wand-lokale Box eines Abschnitts (mm, z hoch): `x0..x1` entlang der
 * Wand-Längsachse, volle Dicke, `z0..z1` ab Wandfuß. Dieselbe Konvention wie
 * `sections.ts`/`cutplanes.ts`, damit Marker und Abschnitts-Quader
 * deckungsgleich liegen. Rein — kein three.js.
 */
export function sectionPlacementBox(section: DecompositionSection, wall: WallFrame): BoxMinMax {
  const a = Math.min(section.x0_mm, section.x1_mm);
  const b = Math.max(section.x0_mm, section.x1_mm);
  const zMin = wall.zMin + Math.min(section.z0_mm, section.z1_mm);
  const zMax = wall.zMin + Math.max(section.z0_mm, section.z1_mm);
  const half = wall.thickness_mm / 2;
  return {
    min: [a, wall.center.y - half, zMin],
    max: [b, wall.center.y + half, zMax],
  };
}

/**
 * Basis-Position eines Teil-Markers (ADR-007), **Wand-lokal** (Issue #99):
 * entlang der Wand-Längsachse in der Abschnittsmitte + `lateral`, `standoff`
 * vor der Wandfront (halbe Dicke + Abstand), z auf der **echten Basis-Höhe**
 * `wall.zMin + stand_height_mm` — die Aufstellhöhe ist seit Issue #132
 * **absolut** über dem Boden (= Wandfuß), NICHT mehr relativ zum Abschnittsfuß
 * (Issue #133: Boden-Modus ⇒ alle Marker stehen auf dem Boden vor ihrem
 * Abschnitt). Die Drehung in den Gruppen-Frame übernimmt die Marker-Gruppe
 * (`applyWallFrame`). Reine Funktion.
 */
export function sectionMarkerPosition(
  section: DecompositionSection,
  wall: WallFrame,
  override?: SectionOverride,
): [number, number, number] {
  // Einquelligkeit (Issue #171): die effektive Platzierung (Zerlegung ⊕ aktiver
  // Override) kommt aus dem EINEN Selektor — der Basis-Marker folgt so demselben
  // Abstand/Podest, mit dem der Arm-Lauf rechnet (B17), statt der alten Lage.
  const pose = effectivePlacement(section.placement, override);
  const lengthMid = (section.x0_mm + section.x1_mm) / 2;
  const zBase = wall.zMin + pose.stand_height_mm;
  const normalOffset = wall.center.y + wall.thickness_mm / 2 + pose.standoff_mm;
  return [lengthMid + pose.lateral_mm, normalOffset, zBase];
}

/**
 * Basis-Frame (4×4, zeilenmajor) des Roboter-Mesh am Fokus-Teil: die geplante
 * Roboterbasis im z-hoch-**Gruppen-Frame** (fertig durch die Wand-Pose
 * komponiert — der Arm hängt direkt in der world-Gruppe). Translation =
 * Marker-Position — die trägt die absolute Aufstellhöhe bereits (Issue #133,
 * keine Doppel-Addition); Rotation = Wand-`yaw` ⊕ `yaw_rad` der Platzierung
 * um die Hochachse. Direkt als Anker für `ArmView.setPose` nutzbar
 * (Basis→Wand). Reine Funktion.
 */
export function sectionBaseFrame(
  section: DecompositionSection,
  wall: WallFrame,
  override?: SectionOverride,
): Mat4 {
  const p = wallLocalToGroup(wall, sectionMarkerPosition(section, wall, override));
  const yaw = wall.yaw + effectivePlacement(section.placement, override).yaw_rad;
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  return [
    c, -s, 0, p[0],
    s, c, 0, p[1],
    0, 0, 1, p[2],
    0, 0, 0, 1,
  ];
}

/** Die Marker-Gruppe aller Teile + je `section_id` ihr Marker-Objekt (für die
 *  saubere Fokus-Umschaltung Marker↔Mesh). */
export interface PlacementMarkersView {
  group: THREE.Group;
  markers: Map<string, THREE.Object3D>;
}

/**
 * Baut je Abschnitt einen Basis-Marker (Scheibe + Achsenkreuz + ggf. Podest-
 * Sockel, `buildBaseMarker`) an seiner Platzierung. Leere Gruppe ohne Abschnitte.
 * Die Marker liegen dauerhaft vor der Wand (Vorbereiten-Modus) und machen das
 * Aufstellmuster + Konsolidierungspotenzial auf einen Blick lesbar.
 */
export function buildPlacementMarkers(
  sections: readonly DecompositionSection[],
  wall: WallFrame,
  overrides: readonly SectionOverride[] = [],
): PlacementMarkersView {
  const group = new THREE.Group();
  group.name = "placement-base-markers";
  applyWallFrame(group, wall);
  const overrideById = new Map(overrides.map((o) => [o.section_id, o]));
  const markers = new Map<string, THREE.Object3D>();
  for (const section of sections) {
    // Effektive Platzierung je Teil aus dem EINEN Selektor (Issue #171): Marker,
    // Podest-Sockel und Position folgen dem aktiven Override, nicht der alten Lage.
    const override = overrideById.get(section.section_id);
    const marker = buildBaseMarker(effectivePlacement(section.placement, override));
    const p = sectionMarkerPosition(section, wall, override);
    marker.position.set(p[0], p[1], p[2]);
    marker.userData = { sectionId: section.section_id };
    group.add(marker);
    markers.set(section.section_id, marker);
  }
  return { group, markers };
}

/**
 * Wendet den Fokus auf die Marker an: das fokussierte Teil zeigt statt des Markers
 * das echte Mesh — also wird sein Marker versteckt, alle anderen bleiben sichtbar.
 * `null` (kein Fokus) zeigt wieder alle Marker. Sauberer Marker↔Mesh-Tausch.
 */
export function applyPlacementFocus(
  view: PlacementMarkersView,
  focusedSectionId: string | null,
): void {
  for (const [id, marker] of view.markers) {
    marker.visible = id !== focusedSectionId;
  }
}

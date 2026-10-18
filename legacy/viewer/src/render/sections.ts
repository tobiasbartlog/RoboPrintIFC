/**
 * Klickbare Abschnitts-Körper des Zerlegungsvorschlags in 3D (Issue #84,
 * PRD B/#70).
 *
 * Legt je Abschnitt einen halbtransparenten Quader über die Wand, der als
 * **Pick-Ziel** für den Fokus-Klick dient (`main.ts` raycastet dagegen). Reine
 * Darstellungsmathematik (ADR-007): Lage und Ausdehnung leiten sich — wie bei
 * `cutplanes.ts` — aus der PCA-Wand-Pose (Issue #99, `wall-frame.ts`) plus den
 * Abschnittsgrenzen (`x0..x1` Wand-lokal, `z0..z1` ab Wandfuß) ab. Kein
 * Urteil, keine Kinematik.
 *
 * Nicht-Fokus-Quader bleiben nahezu unsichtbar (klickbar, aber nicht
 * verdeckend), damit die **ganze Wand sichtbar bleibt** und die Schnittfugen
 * (`cutplanes.ts`) lesbar bleiben; der Fokus-Quader wird sichtbar getönt
 * (`setSectionBoxFocused`). Die eigentliche Fokus-Auswahl (welche `section_id`)
 * lebt DOM-frei in `ui/focus-store.ts` — dieses Modul rendert nur.
 *
 * Koordinaten: Daten-Konvention der Artefakte (mm, z hoch) — die Gruppe wird in
 * die world-Gruppe gehängt (bereits nach three.js y-hoch rotiert) und selbst an
 * die Wand-Pose gesetzt (`applyWallFrame`); die Quader-Specs rechnen rein
 * Wand-lokal, wie bei `cutplanes.ts`.
 */

import * as THREE from "three";

import type { DecompositionSection } from "../api/projects";
import { type WallFrame, applyWallFrame, wallFrameFromObject } from "./wall-frame";

// „Clay-Studio" (Handoff-Scheibe 9, Issue #113): der Fokus-Abschnitt trägt den
// vollen Lehm-Ton, die übrigen Abschnitte werden gedimmt (entsättigt/dunkler) —
// statt der früheren violetten Fokus-Tönung mit unsichtbaren Nachbarn.
const FOCUS_COLOR = 0xc08a5a; // voller Lehm-Ton (Fokus)
const DIMMED_COLOR = 0x544f49; // gedämpfter Grau-Braun-Ton (übrige Abschnitte)

/** Leichtes Übermaß je Abschnitts-Quader (mm), damit er die Wand greifbar
 *  umschließt und beim Fokus nicht im Wandinneren z-fightet. */
const SECTION_INFLATE_MM = 30;

/** Deckkraft des Fokus-Quaders — voller Ton, hebt den Abschnitt heraus. */
const FOCUS_OPACITY = 0.85;
/** Deckkraft der übrigen (gedimmten) Abschnitts-Quader — sichtbar, aber zurückgenommen. */
const DIMMED_OPACITY = 0.4;

/** Reine Geometrie-Spec eines Abschnitts-Quaders im Wand-lokalen Frame (#99). */
export interface SectionBoxSpec {
  /** BoxGeometry-Spannweiten [x, y, z] (mm), inkl. Übermaß. */
  size: [number, number, number];
  /** Quader-Mittelpunkt im Wand-lokalen Frame (mm; z absolut ab Wandfuß). */
  origin: [number, number, number];
}

/**
 * Lage/Ausdehnung eines Abschnitts-Quaders — reine Funktion, per vitest gegen
 * die Wand-Konvention geprüft (`x0..x1` Wand-lokal entlang der Längsachse,
 * `z0..z1` ab Wandfuß, volle Dicke). Wand-lokal (Issue #99): die Drehung in den
 * Gruppen-Frame übernimmt die Quader-Gruppe (`applyWallFrame`). Kein three.js.
 */
export function sectionBoxSpec(section: DecompositionSection, wall: WallFrame): SectionBoxSpec {
  const inflate = SECTION_INFLATE_MM;
  const lengthSpan = Math.abs(section.x1_mm - section.x0_mm) + inflate;
  const lengthMid = (section.x0_mm + section.x1_mm) / 2;
  const zSpan = Math.abs(section.z1_mm - section.z0_mm) + inflate;
  const zMid = wall.zMin + (section.z0_mm + section.z1_mm) / 2;
  const thickness = wall.thickness_mm + inflate;

  return {
    size: [lengthSpan, thickness, zSpan],
    origin: [lengthMid, wall.center.y, zMid],
  };
}

/** Ein pickbarer Abschnitts-Quader: Mesh + zugehörige `section_id`. */
export interface SectionBoxHandle {
  mesh: THREE.Mesh;
  sectionId: string;
}

export interface SectionBoxesView {
  group: THREE.Group;
  handles: SectionBoxHandle[];
}

function emptyGroup(): THREE.Group {
  const g = new THREE.Group();
  g.name = "decompose-section-boxes";
  return g;
}

/**
 * Baut je Abschnitt einen pickbaren Quader relativ zum Wand-Objekt: die Gruppe
 * hängt an der PCA-Wand-Pose (Issue #99, identische Konvention wie
 * `cutplanes.ts`, damit Fugen und Abschnitts-Quader deckungsgleich liegen).
 * Liefert eine leere Gruppe (keine Handles), wenn keine Abschnitte vorliegen
 * oder die Wand keine Geometrie hat. Ein einzelner Abschnitt ist ein gültiger Fall.
 */
export function buildSectionBoxes(
  sections: DecompositionSection[],
  wallObject: THREE.Object3D,
  worldGroup: THREE.Object3D,
): SectionBoxesView {
  const group = emptyGroup();
  if (sections.length === 0) return { group, handles: [] };

  const wall = wallFrameFromObject(wallObject, worldGroup);
  if (!wall) return { group, handles: [] };
  applyWallFrame(group, wall);

  const handles: SectionBoxHandle[] = [];
  for (const section of sections) {
    const spec = sectionBoxSpec(section, wall);
    const geo = new THREE.BoxGeometry(spec.size[0], spec.size[1], spec.size[2]);
    // Startzustand: nahezu unsichtbar (opacity 0), aber voll pickbar — der
    // three.js-Raycaster ignoriert die Deckkraft. So bleibt die Wand frei,
    // bis der Klick einen Abschnitt in den Fokus nimmt (Issue #84).
    const mat = new THREE.MeshStandardMaterial({
      color: DIMMED_COLOR,
      roughness: 0.9,
      metalness: 0,
      transparent: true,
      opacity: DIMMED_OPACITY,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(spec.origin[0], spec.origin[1], spec.origin[2]);
    mesh.userData = { sectionId: section.section_id };
    group.add(mesh);
    handles.push({ mesh, sectionId: section.section_id });
  }
  return { group, handles };
}

/** Tönt einen Abschnitts-Quader: Fokus = voller Lehm-Ton, sonst gedimmt (#113). */
export function setSectionBoxFocused(mesh: THREE.Mesh, focused: boolean): void {
  const mat = mesh.material as THREE.MeshStandardMaterial;
  mat.color.setHex(focused ? FOCUS_COLOR : DIMMED_COLOR);
  mat.opacity = focused ? FOCUS_OPACITY : DIMMED_OPACITY;
  mat.needsUpdate = true;
}

/** Wendet den Fokus (eine `section_id` oder `null`) auf alle Quader an. */
export function applySectionFocus(view: SectionBoxesView, focusedSectionId: string | null): void {
  for (const h of view.handles) {
    setSectionBoxFocused(h.mesh, h.sectionId === focusedSectionId);
  }
}

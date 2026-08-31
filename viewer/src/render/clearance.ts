/**
 * three.js-Darstellung des atmenden Sicherheitspuffers der Live-Vorschau
 * „Vorbereiten" (Druckplan S6, Issue #85). Getrennt von der reinen Geometrie
 * (`ui/safety-clearance.ts`, vitest) — hier nur Renderer + Animation
 * (Pure/DOM-Split, ADR-007).
 *
 * Rendert zwischen Roboterbasis und Wandfront einen lebenden Puffer: eine
 * getönte Fläche, die den Sicherheits-Mindestabstand darstellt und beim
 * Abstands-Optimieren sichtbar „atmet". Grün, solange die Marge eingehalten ist;
 * warnrot, wenn der Mindestabstand verletzt wäre — so wird die nackte Zahl ohne
 * Erklärung verständlich.
 *
 * Frame: kanonisch (x = Wandlänge, y = Wanddicke/Front-Normale, z = Höhe). Der
 * Aufrufer platziert die Gruppe an der Basislage; +y zeigt zur Wandfront.
 */

import * as THREE from "three";

import type { ClearanceState } from "../ui/safety-clearance";

const SAFE_COLOR = 0x66bb6a; // grün — Mindestabstand eingehalten
const UNSAFE_COLOR = 0xef5350; // rot — Mindestabstand verletzt

export interface ClearanceView {
  group: THREE.Group;
  /** Übernimmt den momentanen Puffer-Zustand (Puls/Marge/Sicherheit). */
  setState(state: ClearanceState): void;
}

/**
 * Baut die Puffer-Ansicht: eine breite, flache Box entlang der Front-Normale
 * (+y), deren Tiefe der atmende Puls-Radius ist. {@link ClearanceView.setState}
 * skaliert die Tiefe mit dem Atem und färbt sicher/unsicher — die Wand-Distanz
 * wird so als lebendiger Puffer lesbar, ohne Zahl.
 *
 * `spanMm`/`heightMm` sind Breite (entlang der Wand) und Höhe der Puffer-Fläche
 * (reine Darstellung, aus der Abschnitts-Ausdehnung).
 */
export function buildClearanceView(spanMm: number, heightMm: number): ClearanceView {
  const group = new THREE.Group();
  group.name = "safety-clearance";

  // Einheits-Box (Tiefe 1 in +y); setState skaliert sie auf den Puls-Radius.
  const geo = new THREE.BoxGeometry(Math.max(spanMm, 1), 1, Math.max(heightMm, 1));
  geo.translate(0, 0.5, 0); // Vorderkante an der Basis, wächst nach +y (zur Wand)
  const mesh = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({
      color: SAFE_COLOR,
      transparent: true,
      opacity: 0.25,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  mesh.name = "clearance-buffer";
  group.add(mesh);

  const setState = (state: ClearanceState): void => {
    const mat = mesh.material as THREE.MeshStandardMaterial;
    mat.color.setHex(state.safe ? SAFE_COLOR : UNSAFE_COLOR);
    // Tiefe = atmender Puls (mind. 1 mm, damit die Box sichtbar bleibt).
    mesh.scale.y = Math.max(state.pulseMm, 1);
    // Beim Ausatmen etwas kräftiger — der Puffer „pocht" sichtbar.
    mat.opacity = 0.18 + 0.14 * state.breath;
    mat.needsUpdate = true;
  };

  return { group, setState };
}

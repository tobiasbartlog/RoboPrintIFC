/**
 * TCP-Marker: kleiner Sphere-Mesh, der sich entlang der Toolpath-Targets
 * bewegt wenn die Trajektorie abgespielt wird (ADR-007: keine Kinematik,
 * nur Interpolation zwischen vorhandenen Toolpath-Positionen).
 */

import * as THREE from "three";
import type { Target } from "../artifacts/types";

// TCP-Marker cyan (Scheibe 9, #113): ein Kreis + Quadrat als Fadenkreuz-Reticle
// (statt der roten Kugel), immer sichtbar (depthTest aus).
const TCP_COLOR = 0x4fc3f7; // cyan (Token --info)

export class TcpMarkerView {
  readonly mesh: THREE.Mesh;
  private readonly targets: Target[];

  constructor(targets: Target[]) {
    this.targets = targets;
    // Kreis (dünner Ring) als Träger-Mesh; das Quadrat hängt als Linien-Kind daran.
    this.mesh = new THREE.Mesh(
      new THREE.RingGeometry(9, 12, 24),
      new THREE.MeshBasicMaterial({
        color: TCP_COLOR,
        depthTest: false,
        transparent: true,
        side: THREE.DoubleSide,
      }),
    );
    const s = 16;
    const squareGeo = new THREE.BufferGeometry();
    squareGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(
        [-s, -s, 0, s, -s, 0, s, -s, 0, s, s, 0, s, s, 0, -s, s, 0, -s, s, 0, -s, -s, 0],
        3,
      ),
    );
    const square = new THREE.LineSegments(
      squareGeo,
      new THREE.LineBasicMaterial({ color: TCP_COLOR, depthTest: false }),
    );
    square.renderOrder = 2;
    this.mesh.add(square);
    this.mesh.renderOrder = 2;
    this.mesh.visible = false;
  }

  /**
   * Positioniert den Marker proportional zur Zeit t innerhalb [0, duration].
   * Normierter Fortschritt f → Index in der Target-Liste → lineare Interpolation.
   */
  setTime(t: number, duration: number): void {
    const { targets } = this;
    if (targets.length === 0) { this.mesh.visible = false; return; }
    this.mesh.visible = true;

    const f = duration > 0 ? Math.max(0, Math.min(1, t / duration)) : 0;
    const rawIdx = f * (targets.length - 1);
    const lo = Math.floor(rawIdx);
    const hi = Math.min(lo + 1, targets.length - 1);
    const alpha = rawIdx - lo;

    const pa = targets[lo].frame.pos_mm;
    const pb = targets[hi].frame.pos_mm;
    this.mesh.position.set(
      pa[0] + (pb[0] - pa[0]) * alpha,
      pa[1] + (pb[1] - pa[1]) * alpha,
      pa[2] + (pb[2] - pa[2]) * alpha,
    );
  }
}

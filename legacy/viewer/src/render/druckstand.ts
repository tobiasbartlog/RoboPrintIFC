/**
 * Wachsender Druckstand — dünne three.js-Anbindung (Kollisionskontrolle S3,
 * US 10, #128). Verheiratet die reine Prisma-Spec (`druckstand-spec.ts`) mit
 * three.js: ein halbtransparenter Quader, der mit dem Druckfortschritt in der
 * Höhe wächst — der schon gedruckte, als Hindernis geltende Teil des Bauteils.
 *
 * Reines Sicht-Objekt (ADR-007): die volle Box-Größe stammt aus der
 * Toolpath-Bounding-Box des Laufs, der Fortschritt aus der Trajektorien-Zeit
 * (dieselbe Abbildung wie der wachsende Strang). Koordinaten: Daten-mm (z-hoch);
 * die Welt-Gruppe dreht z-hoch → y-hoch wie bei allen Artefakten. Wird per
 * ⚙-Schalter ein-/ausgeblendet; ausgeschaltet ist das Replay unverändert.
 */

import * as THREE from "three";

import { druckstandPrism } from "./druckstand-spec";

export class DruckstandView {
  readonly group = new THREE.Group();
  private readonly mesh: THREE.Mesh;
  private _fullSizeMm: [number, number, number] = [0, 0, 0];

  constructor() {
    this.group.name = "druckstand";
    const geo = new THREE.BoxGeometry(1, 1, 1); // Einheitsbox, per scale auf die Maße gebracht
    const mat = new THREE.MeshStandardMaterial({
      color: 0x9aa7b8,
      transparent: true,
      opacity: 0.38,
      metalness: 0.1,
      roughness: 0.85,
    });
    this.mesh = new THREE.Mesh(geo, mat);
    this.group.add(this.mesh);
  }

  /**
   * Setzt die volle Bauteil-Box aus der Toolpath-Bounding-Box (Daten-mm). Die
   * Gruppe wird so verankert, dass der Druckstand an der Basis (min-z) nach oben
   * wächst und in x/y auf der Bauteilmitte sitzt.
   */
  setBox(min: readonly [number, number, number], max: readonly [number, number, number]): void {
    this._fullSizeMm = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
    this.group.position.set((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, min[2]);
  }

  /**
   * Lässt den Druckstand bis zum Fortschritt `fraction` ∈ [0,1] wachsen (aus der
   * reinen `druckstandPrism`-Spec). Höhe 0 ⇒ nichts sichtbar.
   */
  setGrowth(fraction: number): void {
    const p = druckstandPrism({ fullSizeMm: this._fullSizeMm, grownFraction: fraction });
    this.mesh.visible = p.visible;
    if (!p.visible) return;
    this.mesh.scale.set(p.sizeMm[0], p.sizeMm[1], p.sizeMm[2]);
    this.mesh.position.set(p.centerLocalMm[0], p.centerLocalMm[1], p.centerLocalMm[2]);
  }

  set visible(v: boolean) {
    this.group.visible = v;
  }
  get visible(): boolean {
    return this.group.visible;
  }

  dispose(): void {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

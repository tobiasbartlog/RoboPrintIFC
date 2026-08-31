/**
 * three.js-Darstellung der Düsen-Schablone der Live-Vorschau „Vorbereiten"
 * (Druckplan S6, Issue #85). Getrennt von der reinen Pose-Geometrie
 * (`ui/nozzle-schablone.ts`, vitest-Golden) — hier nur Renderer + Animation
 * (Pure/DOM-Split, ADR-007).
 *
 * Zeichnet die frisch geslicete Vorschau-Bahn als Linien und einen **Düsen-/
 * Werkzeug-Stummel**, der entlang der Bahn gleitet. Die Pose je Punkt kommt aus
 * der geteilten `nozzle_quat`-Quelle (siehe `ui/nozzle-schablone.ts`) — der
 * Stummel steht damit im echten Lead/Kipp. Wulstdicke = Strangbreite (Stummel-
 * Durchmesser), Stapelung = Schichthöhe (Stummel-Länge/Wulsthöhe).
 *
 * Frame: kanonisch (x = Wandlänge, y = Wanddicke, z = Höhe) — der Aufrufer hängt
 * die Gruppe in den passend gedrehten/verschobenen Wand-Frame.
 */

import * as THREE from "three";

import type { SchabloneResult } from "../ui/nozzle-schablone";

const PATH_COLOR = 0xd2793f; // Lehm-Terrakotta, wie der Toolpath (render/toolpath.ts)
const STUB_COLOR = 0x4fc3f7; // Cyan — konsistent mit dem Basis-Marker

/** Wandelt ein [w,x,y,z]-Quaternion in ein three.js-Quaternion (x,y,z,w). */
function toThreeQuat(q: readonly number[]): THREE.Quaternion {
  return new THREE.Quaternion(q[1], q[2], q[3], q[0]);
}

export interface SchabloneView {
  group: THREE.Group;
  /** Setzt den Stummel auf den Bahn-Fortschritt t ∈ [0, 1] (glatt, IK-frei). */
  setProgress(t: number): void;
  /** Punktzahl der Vorschau-Bahn (Diagnose/Smoke). */
  nPoses: number;
}

/**
 * Baut die Schablonen-Ansicht: Bahn-Linien + gleitender Düsen-Stummel. Der
 * Stummel ist ein kurzer Zylinder entlang der lokalen −z (Düsenachse zeigt zur
 * Wand); {@link SchabloneView.setProgress} interpoliert Lage **und** Rotation
 * zwischen benachbarten Posen — reine Bahn-Geometrie, keine IK.
 */
export function buildSchabloneView(result: SchabloneResult): SchabloneView {
  const group = new THREE.Group();
  group.name = "nozzle-schablone";
  const poses = result.poses;

  // Vorschau-Bahn als zusammenhängende Linie (billig, sofort).
  if (poses.length >= 2) {
    const positions: number[] = [];
    for (let i = 1; i < poses.length; i++) {
      positions.push(...poses[i - 1].pos_mm, ...poses[i].pos_mm);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    const line = new THREE.LineSegments(
      geo,
      new THREE.LineBasicMaterial({ color: PATH_COLOR }),
    );
    line.name = "schablone-path";
    group.add(line);
  }

  // Düsen-Stummel: Zylinder, dessen Achse (lokal z) die Düsenachse ist. Radius =
  // halbe Strangbreite (Wulstdicke), Höhe = Schichthöhe (die aufgetragene Raupe).
  const radius = Math.max(result.beadWidthMm, 1) / 2;
  const height = Math.max(result.layerHeightMm, 1);
  const stubGeo = new THREE.CylinderGeometry(radius, radius, height, 20);
  stubGeo.rotateX(Math.PI / 2); // Zylinderachse y → lokale z (Düsenachse)
  stubGeo.translate(0, 0, height / 2); // Wulst sitzt unter dem Bahnpunkt
  const stub = new THREE.Mesh(
    stubGeo,
    new THREE.MeshStandardMaterial({ color: STUB_COLOR, transparent: true, opacity: 0.9 }),
  );
  stub.name = "schablone-stub";
  stub.visible = poses.length > 0;
  group.add(stub);

  const setProgress = (t: number): void => {
    if (poses.length === 0) return;
    if (poses.length === 1) {
      stub.position.fromArray(poses[0].pos_mm);
      stub.quaternion.copy(toThreeQuat(poses[0].quat));
      return;
    }
    const clamped = Math.min(Math.max(t, 0), 1);
    const f = clamped * (poses.length - 1);
    const i = Math.min(Math.floor(f), poses.length - 2);
    const frac = f - i;
    const a = poses[i];
    const b = poses[i + 1];
    stub.position.set(
      a.pos_mm[0] + (b.pos_mm[0] - a.pos_mm[0]) * frac,
      a.pos_mm[1] + (b.pos_mm[1] - a.pos_mm[1]) * frac,
      a.pos_mm[2] + (b.pos_mm[2] - a.pos_mm[2]) * frac,
    );
    stub.quaternion.copy(toThreeQuat(a.quat)).slerp(toThreeQuat(b.quat), frac);
  };
  setProgress(0);

  return { group, setProgress, nPoses: poses.length };
}

/** Wand-Mesh aus wallspec.json — transparente Hülle + Kanten. */

import * as THREE from "three";
import type { WallSpec } from "../artifacts/types";

export function buildWallObject(spec: WallSpec): THREE.Group {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(spec.geometry.vertices_mm.flat(), 3),
  );
  geometry.setIndex(spec.geometry.faces.flat());
  geometry.computeVertexNormals();

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: 0x8a9099,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );

  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 20),
    new THREE.LineBasicMaterial({ color: 0x9aa3ad }),
  );

  const group = new THREE.Group();
  group.name = `wall:${spec.global_id}`;
  group.add(mesh, edges);
  return group;
}

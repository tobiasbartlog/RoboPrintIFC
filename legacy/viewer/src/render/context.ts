/** Gebäudekontext aus context.json — geisterhaftes Umgebungs-Mesh mit Kanten. */

import * as THREE from "three";
import type { BuildingContext } from "../artifacts/types";

export function buildContextObject(context: BuildingContext): THREE.Group {
  const group = new THREE.Group();
  group.name = "context";

  // Geister-Mesh (Scheibe 9, #113): grau ~10 % Deckkraft + Kanten ~22 %.
  const material = new THREE.MeshStandardMaterial({
    color: 0x556070,
    transparent: true,
    opacity: 0.1,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const edgeMaterial = new THREE.LineBasicMaterial({
    color: 0x4a5260,
    transparent: true,
    opacity: 0.22,
  });

  for (const element of context.elements) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(element.geometry.vertices_mm.flat(), 3),
    );
    geometry.setIndex(element.geometry.faces.flat());
    geometry.computeVertexNormals();

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `context:${element.global_id}`;
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), edgeMaterial);
    group.add(mesh, edges);
  }
  return group;
}

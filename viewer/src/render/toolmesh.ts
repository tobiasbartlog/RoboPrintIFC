/**
 * Endeffektor-Mesh laden (Issue #28): STL/OBJ/GLB → THREE.Object3D.
 *
 * Zwei Wege, beide zustandslos (ADR-007 — der Viewer rechnet nichts Fachliches,
 * er stellt nur dar):
 *   - `parseToolMesh(buffer, filename)` — aus einem hochgeladenen ArrayBuffer
 *     (Konfigurator, kein Netzwerk).
 *   - `loadToolMesh(url, filename)` — von einer URL (Replay: das abgelegte Mesh
 *     des Druckjob-Endeffektors, `/@fs/`-Pfad aus GET /tools).
 *
 * Einheiten: die Mesh-Koordinaten werden als **mm** interpretiert (ADR-006),
 * konsistent mit allen Artefakten. STL/OBJ sind einheitenlos, GLB wird 1:1
 * übernommen — der Nutzer richtet das Mesh im Konfigurator ohnehin per Gizmo am
 * Flansch aus, ein Skalierungsfehler fällt dort sofort auf.
 */

import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const TOOL_COLOR = 0xcbb892;

function toolMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: TOOL_COLOR,
    metalness: 0.25,
    roughness: 0.55,
    side: THREE.DoubleSide,
  });
}

function suffixOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

/** Parst ein Endeffektor-Mesh aus einem ArrayBuffer (Upload im Konfigurator). */
export async function parseToolMesh(
  buffer: ArrayBuffer,
  filename: string,
): Promise<THREE.Object3D> {
  const suffix = suffixOf(filename);
  if (suffix === ".stl") {
    const geometry = new STLLoader().parse(buffer);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, toolMaterial());
    return mesh;
  }
  if (suffix === ".obj") {
    const text = new TextDecoder().decode(buffer);
    const obj = new OBJLoader().parse(text);
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) mesh.material = toolMaterial();
    });
    return obj;
  }
  if (suffix === ".glb" || suffix === ".gltf") {
    return await new Promise<THREE.Object3D>((resolve, reject) => {
      new GLTFLoader().parse(
        buffer,
        "",
        (gltf) => resolve(gltf.scene),
        (err) => reject(err instanceof Error ? err : new Error(String(err))),
      );
    });
  }
  throw new Error(`Mesh-Format ${suffix || "(keins)"} nicht unterstützt (STL/OBJ/GLB).`);
}

/** Lädt ein Endeffektor-Mesh von einer URL (Replay am Flansch). */
export async function loadToolMesh(url: string, filename: string): Promise<THREE.Object3D> {
  const suffix = suffixOf(filename);
  if (suffix === ".glb" || suffix === ".gltf") {
    const gltf = await new GLTFLoader().loadAsync(url);
    return gltf.scene;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Mesh nicht ladbar (${res.status}): ${url}`);
  const buffer = await res.arrayBuffer();
  return parseToolMesh(buffer, filename);
}

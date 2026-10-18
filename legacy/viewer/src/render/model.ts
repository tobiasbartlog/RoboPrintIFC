/**
 * Modellübersicht: die binäre Modell-glTF (model.glb) aller Wände, eingefärbt
 * nach Eignung. Die Geometrie kommt aus der GLB (three.js GLTFLoader), die
 * Zuordnung Knoten -> GlobalId aus model_map.json, das Eignungsurteil aus
 * candidates.json. Farben und Urteile stammen ausschließlich aus den Artefakten
 * (ADR-007 — der Viewer rechnet nichts selbst):
 *   - model.glb      →  Mesh-Geometrie je Szenenknoten (Knotenname = wall_<GlobalId>)
 *   - model_map.json →  Knotenname ↔ GlobalId
 *   - candidates.json →  eligible / checks (inkl. provisional-Flag)
 *
 * Vier Kategorien (Issue #6):
 *   ELIGIBLE    (eligible=true, kein provisional-pass)       →  grün
 *   PROVISIONAL (eligible=true, mind. ein provisional-pass)  →  amber
 *   REJECTED    (eligible=false)                             →  rot
 *   UNKNOWN     (kein candidates-Eintrag für diese Wand)     →  grau
 *
 * Issue #10: ModelView ergänzt pick() + highlight() für die klickbare
 * Wand-Auswahl (Raycaster in main.ts).
 */

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { Candidates, ModelMap } from "../artifacts/types";
import { clayBrightness, hashSeed } from "./scene-palette";
import { WALL_DECORATION_FLAG } from "./wall-frame";

// „Clay-Studio" (Handoff-Scheibe 9, Issue #113): die Wände tragen einen
// einheitlichen Lehm-Ton (Material bleibt Material); die Eignung wird NICHT mehr
// als Vollfärbung, sondern als farbiger Sockel-Streifen am Wandfuß gezeigt.
const CLAY_COLOR = 0xc08a5a; // Lehm-Basiston
/** Höhe des Eignungs-Sockelstreifens am Wandfuß (mm). */
const BASE_STRIP_HEIGHT_MM = 70;
const ACCENT_COLOR = 0xd2793f; // Akzent-Orange (Auswahl-Glow/Outline)

// Sockel-Streifen-Farben (Ampel, aus dem Token-System --ok/--warn/--err):
const ELIGIBLE_COLOR = 0x43a047; // grün
const PROVISIONAL_COLOR = 0xf59e0b; // amber
const REJECTED_COLOR = 0xe53935; // rot
const UNKNOWN_COLOR = 0x8a9099; // grau

/** Normale Deckkraft (keine Selektion aktiv) — Lehm bleibt weitgehend deckend. */
const OPACITY_NORMAL = 0.9;
/** Deckkraft der ausgewählten Wand. */
const OPACITY_SELECTED = 0.98;
/** Deckkraft nicht ausgewählter Wände, wenn eine Selektion aktiv ist. */
const OPACITY_DIMMED = 0.4;

type WallVerdict = "eligible" | "provisional" | "rejected" | "unknown";

function verdict(globalId: string | undefined, candidates: Candidates | null): WallVerdict {
  if (!globalId || !candidates) return "unknown";
  const wall = candidates.walls.find((w) => w.global_id === globalId);
  if (!wall) return "unknown";
  if (!wall.eligible) return "rejected";
  const hasProvisional = wall.checks.some((c) => c.passed && c.provisional === true);
  return hasProvisional ? "provisional" : "eligible";
}

function verdictColor(v: WallVerdict): number {
  switch (v) {
    case "eligible":
      return ELIGIBLE_COLOR;
    case "provisional":
      return PROVISIONAL_COLOR;
    case "rejected":
      return REJECTED_COLOR;
    default:
      return UNKNOWN_COLOR;
  }
}

/**
 * Rückgabe von loadModelObject: drei.js-Gruppe + Klick-/Highlight-API
 * für die klickbare Wand-Auswahl (Issue #10).
 */
export interface ModelView {
  group: THREE.Group;
  /**
   * Gibt die GlobalId des angeklickten Objekts zurück (Name = "wall:<GlobalId>"),
   * oder null wenn kein Wand-Mesh getroffen.
   */
  pick(obj: THREE.Object3D): string | null;
  /**
   * Hebt eine Wand hervor (null = keine Selektion, alle Wände normal).
   * Ausgewählte Wand: volle Deckkraft; restliche: gedimmt.
   */
  highlight(globalId: string | null): void;
  /**
   * Fokussiert eine einzelne Wand (Wand-Fokus ab Zerlegung): ist `globalId`
   * gesetzt **und** `showOthers` false, werden alle übrigen Wände (Mesh, Sockel-
   * Streifen, Kanten) ausgeblendet; `showOthers` true oder `globalId` null zeigt
   * wieder alle. Verändert nur `.visible` — Farbe/Deckkraft bleibt bei
   * `highlight()`. Overlays der Fokus-Wand (Schnitte/Abschnitte) hängen an ihrem
   * eigenen Mesh und bleiben unberührt.
   */
  setWallFocus(globalId: string | null, showOthers: boolean): void;
}

/**
 * Lädt die Modell-glTF und färbt jeden Szenenknoten nach Eignung ein.
 * Asynchron, weil der GLTFLoader die binäre GLB nachlädt.
 */
export async function loadModelObject(
  url: string,
  modelMap: ModelMap,
  candidates: Candidates | null,
): Promise<ModelView> {
  const gltf = await new GLTFLoader().loadAsync(url);
  const group = gltf.scene;
  group.name = "model";

  const globalIdByNode = new Map(modelMap.walls.map((w) => [w.node, w.global_id]));

  // globalId → Liste der Materialien dieses Wandobjekts
  const materialsByGlobalId = new Map<string, THREE.MeshStandardMaterial[]>();
  // globalId → die Wand-Meshes (für den Wand-Fokus ab Zerlegung: `.visible`-Toggle;
  // Sockel-Streifen + Kanten hängen als Kinder am Mesh und folgen automatisch).
  const objectsByGlobalId = new Map<string, THREE.Object3D[]>();

  group.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;

    // Knotenname trägt die GlobalId; GLTFLoader legt sie als Mesh- oder Node-Name ab.
    const globalId = globalIdByNode.get(mesh.name) ?? globalIdByNode.get(mesh.parent?.name ?? "");

    // Einheitlicher Lehm-Ton mit ±8-%-Helligkeitsvarianz je Wand (deterministisch
    // aus der GlobalId): keine Metalness, hohe Roughness → matte Tonoberfläche.
    const clay = new THREE.Color(CLAY_COLOR);
    if (globalId) clay.multiplyScalar(clayBrightness(hashSeed(globalId)));
    const mat = new THREE.MeshStandardMaterial({
      color: clay,
      roughness: 0.95,
      metalness: 0,
      transparent: true,
      opacity: OPACITY_NORMAL,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    mesh.material = mat;
    mesh.name = globalId ? `wall:${globalId}` : mesh.name;

    if (globalId) {
      if (!materialsByGlobalId.has(globalId)) materialsByGlobalId.set(globalId, []);
      materialsByGlobalId.get(globalId)!.push(mat);
      if (!objectsByGlobalId.has(globalId)) objectsByGlobalId.set(globalId, []);
      objectsByGlobalId.get(globalId)!.push(mesh);

      // Eignungs-Befund als Sockel-Streifen am Wandfuß (~70 mm hohes zweites Mesh,
      // leichte Emissive) statt Vollfärbung. Der Streifen erbt die Mesh-Transform,
      // sitzt also automatisch an der echten Wandlage (Datenraum z hoch → Fuß = min z).
      mesh.geometry.computeBoundingBox();
      const bb = mesh.geometry.boundingBox;
      if (bb) {
        const sx = bb.max.x - bb.min.x;
        const sy = bb.max.y - bb.min.y;
        const stripColor = verdictColor(verdict(globalId, candidates));
        const strip = new THREE.Mesh(
          new THREE.BoxGeometry(sx * 1.02, sy * 1.02, BASE_STRIP_HEIGHT_MM),
          new THREE.MeshStandardMaterial({
            color: stripColor,
            emissive: new THREE.Color(stripColor).multiplyScalar(0.25),
            roughness: 0.7,
            metalness: 0,
          }),
        );
        strip.name = `wall-base:${globalId}`;
        strip.position.set(
          (bb.min.x + bb.max.x) / 2,
          (bb.min.y + bb.max.y) / 2,
          bb.min.z + BASE_STRIP_HEIGHT_MM / 2,
        );
        strip.raycast = () => {}; // reine Deko — Wand-Picking unverändert
        // Deko-Markierung: der Streifen ist ein Kind des Wand-Meshs, seine
        // achsparallele Bbox-Geometrie darf den PCA-Wand-Frame (#99) nicht
        // verfälschen — wallFrameFromObject überspringt markierte Meshes.
        strip.userData[WALL_DECORATION_FLAG] = true;
        mesh.add(strip);
      }
    }

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, 20),
      new THREE.LineBasicMaterial({ color: 0x3a2f26, transparent: true, opacity: 0.45 }),
    );
    // LineSegments fallen in wallFrameFromObject ohnehin durch den isMesh-Filter;
    // Flag trotzdem setzen, damit die Deko-Konvention vollständig ist.
    edges.userData[WALL_DECORATION_FLAG] = true;
    mesh.add(edges);
  });

  return {
    group,

    pick(obj) {
      const name = obj.name;
      if (!name.startsWith("wall:")) return null;
      const id = name.slice(5);
      return id || null;
    },

    highlight(globalId) {
      const accent = new THREE.Color(ACCENT_COLOR);
      for (const [id, mats] of materialsByGlobalId) {
        const selected = id === globalId;
        const opacity =
          globalId === null ? OPACITY_NORMAL : selected ? OPACITY_SELECTED : OPACITY_DIMMED;
        for (const mat of mats) {
          mat.opacity = opacity;
          // Auswahl = dezenter Akzent-Glow (statt reinem Deckkraft-Wechsel, #113).
          mat.emissive = selected ? accent.clone().multiplyScalar(0.35) : new THREE.Color(0x000000);
          mat.needsUpdate = true;
        }
      }
    },

    setWallFocus(globalId, showOthers) {
      for (const [id, objs] of objectsByGlobalId) {
        const visible = showOthers || globalId === null || id === globalId;
        for (const o of objs) o.visible = visible;
      }
    },
  };
}

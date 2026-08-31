/**
 * three.js-Grundgerüst: Renderer, Kamera, Orbit-Steuerung, Licht, Boden.
 * Artefaktdaten sind z-hoch (mm); die Welt-Gruppe rotiert sie in das
 * y-hoch-System von three.js — Renderlogik bleibt davon unberührt.
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { type ScenePalette, type SceneTheme, ndcToPx, readScenePalette } from "../render/scene-palette";

/**
 * Gibt alle GPU-Ressourcen unter `world` frei und entfernt die Kinder (Issue
 * #50). `Object3D.remove` löst nur die Szenengraph-Kante — Geometrien,
 * Materialien und deren Texturen bleiben sonst im GPU-Speicher und lecken über
 * Re-Slice / Sequenz-Start / Cut-Edit hinweg (irgendwann Context-Loss).
 *
 * Traversiert jeden entfernten Teilbaum und disposed:
 *  - jede `BufferGeometry` (model.glb-Meshes, EdgesGeometry je Wand, Toolpath-
 *    Linienpuffer, PlaneGeometry der Schnittebenen, Arm-/Marker-Primitive),
 *  - jedes Material (auch Material-Arrays) samt referenzierter Texturen,
 *
 * Geometrien/Materialien werden über Sets dedupliziert: innerhalb eines
 * Teilbaums geteilte Materialien (z. B. gemeinsamer Link-/Joint-Werkstoff des
 * Arms) werden genau einmal disposed. Geteilte Singletons mit der *bleibenden*
 * Szene existieren nicht — Gitter, Lichter und die Roboter-Vorschau hängen
 * direkt an `scene`, nie an `world`, und jede Session baut ihre Objekte frisch.
 */
export function clearWorld(world: THREE.Object3D): void {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();

  for (const child of [...world.children]) {
    child.traverse((obj) => {
      const node = obj as Partial<THREE.Mesh>;
      if (node.geometry) geometries.add(node.geometry);
      const material = node.material;
      if (Array.isArray(material)) {
        for (const m of material) materials.add(m);
      } else if (material) {
        materials.add(material);
      }
    });
    world.remove(child);
  }

  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) {
    disposeMaterialTextures(material);
    material.dispose();
  }
}

/** Disposed alle Texturen, die als Eigenschaften eines Materials hängen (map,
 *  normalMap, alphaMap, …) — three.js hält sie sonst im GPU-Speicher. */
function disposeMaterialTextures(material: THREE.Material): void {
  for (const value of Object.values(material as unknown as Record<string, unknown>)) {
    if (value && (value as THREE.Texture).isTexture) {
      (value as THREE.Texture).dispose();
    }
  }
}

export interface Viewport {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Gruppe für alle Artefakt-Objekte (z-hoch -> y-hoch bereits gedreht). */
  world: THREE.Group;
  /** Canvas-Element des Renderers — für Raycaster-Klickhandler (Issue #10). */
  canvas: HTMLCanvasElement;
  /** Overlay-Ebene über dem Canvas für projizierte HTML-Chips (Maß-Label, Basis-Chip). */
  overlay: HTMLElement;
  fitTo(object: THREE.Object3D): void;
  clearWorld(): void;
  /**
   * Färbt die Studio-Bühne (Hintergrund-Verlauf, Fog, Gitter) nach dem aktuellen
   * Theme neu — von der Theme-Umschaltung in `main.ts` gerufen (Scheibe 9, #113).
   */
  restyle(): void;
  /** Registriert eine je-Frame-Rückrufliste (z. B. Overlay-Chips nachführen). */
  onFrame(cb: () => void): void;
  /**
   * Projiziert einen Weltpunkt auf CSS-Pixel im Overlay. `visible` ist false,
   * wenn der Punkt hinter der Kamera liegt (Chip dann ausblenden).
   */
  project(point: THREE.Vector3): { x: number; y: number; visible: boolean };
}

/** Aktuelles Theme aus dem `data-theme` am `<html>` (Default: dunkel). */
function currentSceneTheme(): SceneTheme {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/** Liest eine CSS-Custom-Property vom Wurzelelement (für die Token-basierte Palette). */
function readToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name);
}

/** Radialer Studio-Verlauf (innen `bgInner` → außen `bgOuter`) als Canvas-Textur. */
function makeGradientTexture(inner: string, outer: string): THREE.CanvasTexture {
  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const g = ctx.createRadialGradient(
      size / 2,
      size * 0.44,
      size * 0.04,
      size / 2,
      size * 0.5,
      size * 0.72,
    );
    g.addColorStop(0, inner);
    g.addColorStop(1, outer);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Weicher, radial ausblendender Bodenfleck (ContactShadow-Ersatz, Scheibe 9). */
function makeContactShadowTexture(): THREE.CanvasTexture {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, "rgba(0,0,0,0.55)");
    g.addColorStop(0.6, "rgba(0,0,0,0.22)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  const tex = new THREE.CanvasTexture(canvas);
  return tex;
}

export function createViewport(container: HTMLElement): Viewport {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  // Overlay-Chips sollen im #viewport verankert liegen (Scheibe 9): eine
  // positionierte Bühne + eine durchklickbare Overlay-Ebene über dem Canvas.
  container.style.position = container.style.position || "relative";
  container.appendChild(renderer.domElement);
  const overlay = document.createElement("div");
  overlay.className = "viewport-overlay";
  container.appendChild(overlay);

  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(50, 1, 1, 100_000);
  camera.position.set(3000, 2500, 3000);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3f47, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(2000, 4000, 1500);
  scene.add(sun);

  // Studio-Bühne (Scheibe 9): radialer Hintergrund-Verlauf, dezenter Fog und ein
  // Gitter nur nahe der Szene (Fog blendet die fernen Linien aus = radialer
  // Falloff). Alle Farben kommen aus den CSS-Tokens (`--vp1/--vp2`), damit der
  // Theme-Umschalter die Bühne mitkippt (`restyle`).
  const grid = new THREE.GridHelper(10_000, 20);
  const gridMat = grid.material as THREE.LineBasicMaterial;
  gridMat.transparent = true;
  scene.add(grid);

  // Weicher Bodenschatten (ContactShadow-Ersatz): radialer dunkler Fleck am Boden.
  const shadowTex = makeContactShadowTexture();
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(8000, 8000),
    new THREE.MeshBasicMaterial({
      map: shadowTex,
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
    }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 1; // knapp über dem Gitter, gegen z-fighting
  shadow.renderOrder = -1;
  shadow.raycast = () => {}; // nie pickbar (reine Deko, kein Eingriff ins Picking)
  scene.add(shadow);

  let backgroundTex: THREE.CanvasTexture | null = null;
  const restyle = () => {
    const palette: ScenePalette = readScenePalette(readToken, currentSceneTheme());
    const old = backgroundTex;
    backgroundTex = makeGradientTexture(palette.bgInner, palette.bgOuter);
    scene.background = backgroundTex;
    if (old) old.dispose();
    scene.fog = new THREE.Fog(new THREE.Color(palette.bgOuter), 7000, 24000);
    const gridColor = new THREE.Color(palette.grid);
    (grid.material as THREE.LineBasicMaterial).color = gridColor;
    // GridHelper legt die Farbe zusätzlich als Vertex-Colors ab — überschreiben,
    // damit die Theme-Farbe wirklich greift.
    const colorAttr = grid.geometry.getAttribute("color") as THREE.BufferAttribute | undefined;
    if (colorAttr) {
      for (let i = 0; i < colorAttr.count; i++) {
        colorAttr.setXYZ(i, gridColor.r, gridColor.g, gridColor.b);
      }
      colorAttr.needsUpdate = true;
    }
    (grid.material as THREE.LineBasicMaterial).opacity = palette.gridOpacity;
  };
  restyle();

  const world = new THREE.Group();
  world.rotation.x = -Math.PI / 2; // Daten: z hoch -> three.js: y hoch
  scene.add(world);

  const resize = () => {
    const { clientWidth, clientHeight } = container;
    renderer.setSize(clientWidth, clientHeight);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(container);
  resize();

  const frameCallbacks: Array<() => void> = [];
  renderer.setAnimationLoop(() => {
    controls.update();
    for (const cb of frameCallbacks) cb();
    renderer.render(scene, camera);
  });

  return {
    scene,
    camera,
    controls,
    world,
    canvas: renderer.domElement,
    overlay,
    restyle,
    onFrame(cb: () => void) {
      frameCallbacks.push(cb);
    },
    project(point: THREE.Vector3) {
      const v = point.clone().project(camera);
      const { x, y } = ndcToPx(v.x, v.y, container.clientWidth, container.clientHeight);
      return { x, y, visible: v.z < 1 };
    },
    fitTo(object: THREE.Object3D) {
      const box = new THREE.Box3().setFromObject(object);
      if (box.isEmpty()) return;
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length();
      controls.target.copy(center);
      camera.position.copy(center).add(new THREE.Vector3(0.7, 0.5, 0.9).multiplyScalar(size));
      camera.near = size / 1000;
      camera.far = size * 20;
      camera.updateProjectionMatrix();
    },
    clearWorld() {
      clearWorld(world);
    },
  };
}

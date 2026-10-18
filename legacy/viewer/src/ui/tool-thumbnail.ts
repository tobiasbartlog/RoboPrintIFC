/**
 * Mesh-Vorschaubilder für die Endeffektor-Bibliothek (Issue #56, Modul 2).
 *
 * Der Viewer rendert die Thumbnails **clientseitig** (kein serverseitiges PNG,
 * ADR-007/Out of Scope): ein einzelnes Endeffektor-Mesh wird in einen kleinen
 * Offscreen-Viewport (three.js) geladen, die Kamera an seine Bounding-Box
 * gesetzt und ein `toDataURL()`-Standbild gezogen. Begründung (Design-Log
 * 2026-07-06): bei ~5 Endeffektoren und ~5-MB-STL ist ein Live-Render + Cache
 * einfacher und ohne neue Ausliefer-Endpoints als headless-Python-Rendering.
 *
 * Diese Datei trennt zwei Belange:
 *  - {@link ThumbnailCache} — die reine, three.js-freie Cache-Schicht (In-Memory
 *    + optional `localStorage`), Key = `mesh_path`. Voll unit-getestet.
 *  - {@link renderMeshThumbnail} — das GL-Standbild (nicht unit-getestet).
 */

import * as THREE from "three";

/** Minimaler Speicher-Vertrag (erfüllt von `window.localStorage`; im Test stubbar). */
export interface ThumbnailStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const STORE_PREFIX = "fgc-tool-thumb:";

/**
 * Cache für Mesh-Vorschaubilder, Key = `mesh_path` (Issue #56).
 *
 * In-Memory zuerst, dahinter optional ein `ThumbnailStore` (localStorage), damit
 * das Bild beim erneuten Öffnen des Reiters sofort da ist (US 22). Ein fehlender
 * `mesh_path` (`null`/leer) hat keinen Cache-Key ⇒ kein Eintrag, kein Rendern
 * (der Aufrufer zeigt einen Platzhalter, US 21/23). Ändert sich der `mesh_path`
 * (neues/ersetztes Mesh), ist es ein anderer Key ⇒ automatisch neu gerendert.
 */
export class ThumbnailCache {
  private readonly mem = new Map<string, string>();

  constructor(private readonly store?: ThumbnailStore) {}

  /**
   * Liefert das gecachte Vorschaubild zu `meshPath` oder berechnet es einmalig
   * über `compute` und legt es ab. `null`/leerer `meshPath` ⇒ `null` (kein
   * Rendern). `compute` wird nur bei einem Cache-Miss aufgerufen.
   */
  async getOrCompute(
    meshPath: string | null | undefined,
    compute: () => Promise<string>,
  ): Promise<string | null> {
    if (!meshPath) return null;
    const cached = this.peek(meshPath);
    if (cached) return cached;
    const rendered = await compute();
    this.set(meshPath, rendered);
    return rendered;
  }

  /** Gecachtes Bild ohne Berechnung (In-Memory, dann Store); `null` = Miss. */
  peek(meshPath: string | null | undefined): string | null {
    if (!meshPath) return null;
    const inMem = this.mem.get(meshPath);
    if (inMem) return inMem;
    const stored = this.store?.getItem(STORE_PREFIX + meshPath) ?? null;
    if (stored) this.mem.set(meshPath, stored); // in den schnellen Cache heben
    return stored;
  }

  /** Trägt ein Bild in beide Cache-Ebenen ein. */
  set(meshPath: string, dataUrl: string): void {
    this.mem.set(meshPath, dataUrl);
    try {
      this.store?.setItem(STORE_PREFIX + meshPath, dataUrl);
    } catch {
      /* localStorage voll/gesperrt — In-Memory reicht. */
    }
  }

  /** Entfernt einen Eintrag (z. B. nach dem Löschen eines Endeffektors). */
  invalidate(meshPath: string | null | undefined): void {
    if (!meshPath) return;
    this.mem.delete(meshPath);
    try {
      this.store?.removeItem(STORE_PREFIX + meshPath);
    } catch {
      /* ignore */
    }
  }
}

const THUMB_PX = 256;

/**
 * Rendert ein einzelnes Endeffektor-Mesh in ein quadratisches Standbild
 * (`data:image/png`-URL). Nutzt einen eigenen, unsichtbaren Offscreen-Renderer,
 * Kamera an die Mesh-Bounding-Box gesetzt (US 2). Wirft nur, wenn kein
 * WebGL-Kontext verfügbar ist — der Aufrufer fängt das und zeigt einen
 * Platzhalter (US 23).
 */
export function renderMeshThumbnail(mesh: THREE.Object3D): string {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  try {
    renderer.setSize(THUMB_PX, THUMB_PX);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x40454d, 1.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.3);
    sun.position.set(1, 2, 1.5);
    scene.add(sun);

    const group = new THREE.Object3D();
    group.add(mesh);
    scene.add(group);

    const box = new THREE.Box3().setFromObject(mesh);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1_000_000);
    if (!box.isEmpty()) {
      const center = box.getCenter(new THREE.Vector3());
      const radius = box.getSize(new THREE.Vector3()).length() * 0.5 || 1;
      const dist = radius / Math.sin((camera.fov * Math.PI) / 180 / 2);
      camera.position
        .copy(center)
        .add(new THREE.Vector3(0.8, 0.6, 1).normalize().multiplyScalar(dist * 1.3));
      camera.near = dist / 100;
      camera.far = dist * 100;
      camera.lookAt(center);
      camera.updateProjectionMatrix();
    }

    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  } finally {
    renderer.dispose();
  }
}

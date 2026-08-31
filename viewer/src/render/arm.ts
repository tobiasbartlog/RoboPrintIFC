/**
 * Präsentations-Arm des Roboters (ADR-007-Klarstellung 2026-07-04). Zwei
 * Darstellungen derselben FK-Pose, global umschaltbar (Issue #41):
 *
 *   - **Mesh** (Default): die echten M1013-Glieder aus
 *     `viewer/public/robots/m1013/*.glb` (Issue #40). Je Glied ein GLB, dessen
 *     Vertices so vorgebacken sind, dass `mesh.matrix = frames[i]` (DH-FK-Frame)
 *     es korrekt platziert — Skalierung/Offset stecken in den Vertices, der
 *     Viewer rechnet nichts dazu.
 *   - **Schema** (Fallback + Wahl): die bewusst schematische Kapsel-/Zylinder-
 *     Darstellung — je Glied ein Zylinder zwischen den FK-Gliedursprüngen, an
 *     jedem Gelenk eine Kugel. Bleibt der Fallback, wenn der GLB-Load scheitert.
 *
 * Die Gliedposen kommen aus der Präsentations-FK (`kinematics/fk`), die gegen
 * die Core-FK per Golden-Orakel validiert ist. Der Arm rechnet nichts
 * Urteilendes — er zeigt nur, wie die `joints_rad` eines Samples stehen.
 *
 * Der Render-Modus ist **global**: ein Modul-Zustand (`armmesh-state.ts`, rein &
 * getestet) steuert alle ArmView-Instanzen gleichzeitig; der Umschalter lebt im
 * Reiter Roboter. Scheitert der Load, erzwingt der Zustand Schema und sperrt den
 * Umschalter (nie ein leerer Arm/Viewport — Lehre 2026-07-05).
 *
 * Koordinaten: die FK liefert Gliedursprünge in Roboterbasis-Koordinaten; die
 * Anker-Transformation (`group.matrix`) legt den Flansch auf die aktuelle
 * TCP-Position des Toolpath-Players (Wandkoordinaten, z-hoch). Die Welt-Gruppe
 * dreht z-hoch → y-hoch wie bei allen Artefakten.
 */

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

import { forwardChain, positionOf, type DhParams, type Mat4 } from "../kinematics/fk";
import {
  ARM_LINK_COUNT,
  effectiveMode,
  initArmRenderState,
  parseArmManifest,
  requestMode,
  withLoadFailure,
  withMeshesLoaded,
  type ArmManifest,
  type ArmRenderState,
  type RenderMode,
} from "./armmesh-state";

const LINK_RADIUS_MM = 45;
const JOINT_RADIUS_MM = 62;
const LINK_COLOR = 0x8aa0c0;
const JOINT_COLOR = 0x4a5a72;
const BASE_COLOR = 0x2f3a4a;
// Kollisions-Einfärbung (Kollisionskontrolle S3, US 8, #128): das verursachende
// Glied leuchtet rot (Kollision) / gelb (Warnung). Rein darstellend — die Wahl
// des Glieds kommt verbatim aus dem Artefakt (ADR-007), der Viewer urteilt nicht.
const HIGHLIGHT_EMISSIVE = { red: 0xd64545, yellow: 0xd99a00 } as const;
const MESH_COLOR = 0xb9c2cc; // neutrales Roboter-Grau (GLBs tragen keine Farbe, #40)
const MIN_SEGMENT_MM = 1; // kürzere Segmente (a=d=0) nicht als Zylinder zeichnen
const UP = new THREE.Vector3(0, 1, 0); // lokale Achse der CylinderGeometry

const DEFAULT_MESH_BASE_URL = "./robots/m1013/";

// --- Globaler Mesh-/Modus-Zustand (Issue #41) -------------------------------
// Alle ArmView-Instanzen teilen sich die geladenen GLBs (einmal laden, je
// Instanz klonen) und denselben Render-Modus. Der reine Zustand liegt in
// `armmesh-state.ts`; hier nur die three.js-Objekte + Benachrichtigung.

const instances = new Set<ArmView>();
const listeners = new Set<(state: ArmRenderState) => void>();
let renderState = initArmRenderState();
let sharedMeshes: THREE.Object3D[] | null = null; // Index 0 = Basis … 6 = Flansch
let manifest: ArmManifest | null = null;
let loadPromise: Promise<void> | null = null;

function notify(): void {
  for (const cb of listeners) cb(renderState);
}

function applyModeToAll(): void {
  for (const a of instances) a.applyRenderMode();
}

/**
 * Lädt die 7 M1013-GLBs einmalig (Manifest als einzige Index→Datei-Quelle) und
 * verteilt sie an alle ArmView-Instanzen. Bei Manifest- oder Datei-Fehler:
 * Fallback auf Schema, Umschalter gesperrt, Konsolen-Warnung — nie ein leerer
 * Arm. Mehrfachaufruf ist idempotent (memoisiert).
 */
export function initArmMeshes(baseUrl: string = DEFAULT_MESH_BASE_URL): Promise<void> {
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    try {
      const res = await fetch(baseUrl + "manifest.json");
      if (!res.ok) throw new Error(`manifest.json nicht ladbar (${res.status})`);
      const parsed = parseArmManifest(await res.json());
      const loader = new GLTFLoader();
      const byIndex: THREE.Object3D[] = new Array(ARM_LINK_COUNT);
      const ordered = [...parsed.links].sort((a, b) => a.index - b.index);
      for (const link of ordered) {
        const gltf = await loader.loadAsync(baseUrl + link.file);
        byIndex[link.index] = gltf.scene;
      }
      manifest = parsed;
      sharedMeshes = byIndex;
      renderState = withMeshesLoaded(renderState);
      for (const a of instances) a.adoptMeshes();
      applyModeToAll();
    } catch (err) {
      console.warn(
        "M1013-Meshes konnten nicht geladen werden — Schema-Darstellung (Fallback).",
        err,
      );
      renderState = withLoadFailure(renderState);
      applyModeToAll();
    }
    notify();
  })();
  return loadPromise;
}

/** Schaltet den globalen Render-Modus (wirkt auf alle Instanzen). */
export function setArmRenderMode(mode: RenderMode): void {
  renderState = requestMode(renderState, mode);
  applyModeToAll();
  notify();
}

/** Aktueller globaler Render-Zustand (für Umschalter-Anzeige/Tests). */
export function getArmRenderState(): ArmRenderState {
  return renderState;
}

/** Das geladene Manifest (für die BSD-3-Attribution im Reiter), oder null. */
export function getArmManifest(): ArmManifest | null {
  return manifest;
}

/**
 * Abonniert Render-Zustandsänderungen (Load fertig/fehlgeschlagen, Moduswechsel).
 * Ruft `cb` sofort mit dem aktuellen Zustand auf.
 */
export function onArmRenderStateChange(cb: (state: ArmRenderState) => void): void {
  listeners.add(cb);
  cb(renderState);
}

/** Nur für Tests: globalen Zustand zurücksetzen. */
export function _resetArmMeshesForTest(): void {
  instances.clear();
  listeners.clear();
  renderState = initArmRenderState();
  sharedMeshes = null;
  manifest = null;
  loadPromise = null;
}

function robotMeshMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: MESH_COLOR,
    metalness: 0.35,
    roughness: 0.55,
  });
}

export class ArmView {
  readonly group = new THREE.Group();
  /**
   * Kind-Gruppe, die bei jeder Pose auf dem Flansch-Frame sitzt (Issue #28).
   * Wer ihr Objekte hinzufügt (Endeffektor-Mesh, Flansch-Achsen, TCP-Marker),
   * arbeitet in **Flansch-Koordinaten** — das lokale Transform eines Kindes ist
   * direkt seine Lage relativ zum Flansch (mm/rad, ADR-006). Unabhängig vom
   * Render-Modus (Mesh oder Schema).
   */
  readonly flange = new THREE.Group();
  private readonly dh: DhParams;
  private readonly nSegments: number;
  private readonly links: THREE.Mesh[] = [];
  private readonly joints: THREE.Mesh[] = [];
  private readonly base: THREE.Mesh;
  /** Ein Halter je Glied (Index 0 = Basis … 6 = Flansch); trägt das geklonte GLB. */
  private readonly meshHolders: THREE.Group[] = [];
  /** Material je Mesh-Halter (für die Kollisions-Einfärbung eines einzelnen Glieds, #128). */
  private readonly holderMats: THREE.MeshStandardMaterial[] = [];
  private meshLoaded = false;
  /** Aktuell rot/gelb eingefärbtes Glied (0..6, 7 = Endeffektor) oder null (#128). */
  private _highlightLink: number | null = null;

  constructor(dh: DhParams) {
    this.dh = dh;
    this.nSegments = dh.a_mm.length;
    this.group.name = "presentation-arm";
    // Anker wird pro Frame gesetzt; Matrix nicht automatisch aus pos/quat ableiten.
    this.group.matrixAutoUpdate = false;

    // Flansch-Gruppe: Matrix wird in setPose aus dem Flansch-Frame gesetzt.
    this.flange.name = "flange";
    this.flange.matrixAutoUpdate = false;
    this.group.add(this.flange);

    // Basis-Sockel am Gliedursprung 0.
    this.base = new THREE.Mesh(
      new THREE.CylinderGeometry(JOINT_RADIUS_MM * 1.6, JOINT_RADIUS_MM * 1.9, 60, 16),
      new THREE.MeshStandardMaterial({ color: BASE_COLOR, metalness: 0.3, roughness: 0.7 }),
    );
    this.base.position.set(0, 0, 30); // 30 mm über der Basis (z-hoch, vor Anker)
    this.base.rotation.x = Math.PI / 2; // Zylinderachse auf z
    this.group.add(this.base);

    // Je Segment ein Zylinder (Einheitshöhe, wird per scale.y auf die Länge gebracht),
    // je Gelenk eine Kugel. Eigenes Material je Glied (#128), damit die
    // Kollisions-Einfärbung ein EINZELNES Glied tinten kann.
    for (let i = 0; i < this.nSegments; i++) {
      const linkMat = new THREE.MeshStandardMaterial({ color: LINK_COLOR, metalness: 0.3, roughness: 0.6 });
      const link = new THREE.Mesh(new THREE.CylinderGeometry(LINK_RADIUS_MM, LINK_RADIUS_MM, 1, 12), linkMat);
      link.visible = false;
      this.links.push(link);
      this.group.add(link);

      const jointMat = new THREE.MeshStandardMaterial({ color: JOINT_COLOR, metalness: 0.4, roughness: 0.5 });
      const joint = new THREE.Mesh(new THREE.SphereGeometry(JOINT_RADIUS_MM, 16, 12), jointMat);
      this.joints.push(joint);
      this.group.add(joint);
    }

    // Mesh-Halter (Basis + je Achse = nSegments + 1 Frames). Matrix aus frames[i].
    for (let i = 0; i <= this.nSegments; i++) {
      const holder = new THREE.Group();
      holder.name = `link-mesh-${i}`;
      holder.matrixAutoUpdate = false;
      holder.visible = false;
      this.meshHolders.push(holder);
      this.group.add(holder);
    }

    instances.add(this);
    if (sharedMeshes) this.adoptMeshes();
    this.applyRenderMode();
  }

  /**
   * Klont die geteilten GLBs in die eigenen Halter (Transforms je Instanz
   * unabhängig). Idempotent — bei erneutem Aufruf werden alte Klone verworfen.
   */
  adoptMeshes(): void {
    if (!sharedMeshes) return;
    this.holderMats.length = 0;
    for (let i = 0; i < this.meshHolders.length; i++) {
      const holder = this.meshHolders[i];
      holder.clear();
      // Eigenes Material je Halter (#128): so lässt sich ein einzelnes Glied
      // kollisions-einfärben, ohne die übrigen mitzuziehen.
      const mat = robotMeshMaterial();
      this.holderMats[i] = mat;
      const src = sharedMeshes[i];
      if (!src) continue;
      const clone = src.clone(true);
      clone.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (mesh.isMesh) mesh.material = mat;
      });
      holder.add(clone);
    }
    this.meshLoaded = true;
    this._applyHighlight(); // frisch adoptierte Meshes sofort auf die Einfärbung bringen
  }

  /**
   * Färbt das verursachende Glied ein (Kollisionskontrolle S3, US 8, #128): rot
   * (Kollision) / gelb (Warnung) — oder `null`, um alle Glieder auf neutral
   * zurückzustellen. Rein darstellend: WELCHES Glied und WELCHER Status kommen
   * verbatim aus dem Artefakt (ADR-007), der Arm urteilt nicht. Wirkt auf beide
   * Darstellungen (Schema-Zylinder + Mesh-Halter). `link` 0..6, 7 = Endeffektor.
   */
  setLinkHighlight(link: number | null, status: "red" | "yellow" = "red"): void {
    this._highlightLink = link == null ? null : link;
    this._highlightStatus = status;
    this._applyHighlight();
  }

  private _highlightStatus: "red" | "yellow" = "red";

  private _applyHighlight(): void {
    const emissive = HIGHLIGHT_EMISSIVE[this._highlightStatus];
    const setEmissive = (mat: THREE.MeshStandardMaterial | undefined, on: boolean): void => {
      if (!mat) return;
      mat.emissive.setHex(on ? emissive : 0x000000);
      mat.emissiveIntensity = on ? 0.9 : 0;
    };
    const link = this._highlightLink;
    for (let i = 0; i < this.nSegments; i++) {
      const on = link != null && i === link;
      setEmissive(this.links[i]?.material as THREE.MeshStandardMaterial, on);
      setEmissive(this.joints[i]?.material as THREE.MeshStandardMaterial, on);
    }
    for (let i = 0; i < this.holderMats.length; i++) {
      // Halter 0..6 (0=Basis … 6=Flansch); Endeffektor (7) mappt auf den Flansch.
      const target = link == null ? -1 : Math.min(link, this.holderMats.length - 1);
      setEmissive(this.holderMats[i], i === target);
    }
  }

  /** Wendet den globalen Render-Modus auf diese Instanz an (Mesh ↔ Schema). */
  applyRenderMode(): void {
    const showMesh = effectiveMode(renderState) === "mesh";
    this.base.visible = !showMesh;
    // Zylinder im Schema nur, wenn ihr Segment eine Länge hat (setPose setzt das
    // Flag); im Mesh-Modus immer aus. Kugeln nur im Schema.
    for (const l of this.links) l.visible = !showMesh && l.userData.hasLength === true;
    for (const j of this.joints) j.visible = !showMesh;
    for (const h of this.meshHolders) h.visible = showMesh;
  }

  /** Sichtbarkeit des gesamten Arms schalten. */
  set visible(v: boolean) {
    this.group.visible = v;
  }
  get visible(): boolean {
    return this.group.visible;
  }

  /** Diagnose für den Headless-Smoke (#41): effektiver Modus + Mesh-Ladezustand. */
  debugInfo(): { mode: RenderMode; meshLoaded: boolean; linkMeshCount: number } {
    return {
      mode: effectiveMode(renderState),
      meshLoaded: this.meshLoaded,
      linkMeshCount: this.meshHolders.filter((h) => h.children.length > 0).length,
    };
  }

  /**
   * Stellt den Arm auf die Gelenkwinkel `joints_rad` und verankert ihn mit
   * `anchor` (starre 4×4 Basis→Wand). Im Regelfall ist `anchor` die **feste**
   * Roboterbasis im Wandsystem (`meta.base_frame`, Issue #66) — konstant über
   * die Zeit; die Gelenke articulieren, der TCP fährt die Bahn ab. (Altläufe
   * ohne base_frame nutzen den Legacy-Anker, der den Flansch pro Frame ans Ziel
   * legt.) Setzt beide Darstellungen (Zylinder + Mesh-Halter) — sichtbar ist nur
   * die aktive.
   */
  setPose(joints_rad: number[], anchor: Mat4): void {
    // group.matrix = anchor (zeilenmajor → THREE.set ist zeilenmajor).
    this.group.matrix.set(
      anchor[0], anchor[1], anchor[2], anchor[3],
      anchor[4], anchor[5], anchor[6], anchor[7],
      anchor[8], anchor[9], anchor[10], anchor[11],
      anchor[12], anchor[13], anchor[14], anchor[15],
    );

    const frames = forwardChain(this.dh, joints_rad);
    const origins = frames.map((m) => {
      const p = positionOf(m);
      return new THREE.Vector3(p[0], p[1], p[2]);
    });

    const meshMode = effectiveMode(renderState) === "mesh";

    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const dir = new THREE.Vector3();
    for (let i = 0; i < this.nSegments; i++) {
      a.copy(origins[i]);
      b.copy(origins[i + 1]);
      const len = a.distanceTo(b);
      const link = this.links[i];
      const hasLength = len >= MIN_SEGMENT_MM;
      link.userData.hasLength = hasLength;
      if (!hasLength) {
        link.visible = false;
      } else {
        link.visible = !meshMode;
        link.position.copy(a).add(b).multiplyScalar(0.5);
        dir.copy(b).sub(a).normalize();
        link.quaternion.setFromUnitVectors(UP, dir);
        link.scale.set(1, len, 1);
      }
      this.joints[i].position.copy(origins[i + 1]);
    }

    // Mesh-Halter je Glied auf sein FK-Frame setzen (Vertices vorgebacken, #40):
    // frames[i] direkt als Halter-Matrix (Basis = frames[0], Flansch = frames[6]).
    for (let i = 0; i < this.meshHolders.length; i++) {
      const m = frames[i];
      this.meshHolders[i].matrix.set(
        m[0], m[1], m[2], m[3],
        m[4], m[5], m[6], m[7],
        m[8], m[9], m[10], m[11],
        m[12], m[13], m[14], m[15],
      );
    }

    // Flansch-Gruppe auf den Flansch-Frame setzen (letztes Glied) — Kinder liegen
    // damit in Flansch-Koordinaten (Endeffektor-Mesh, Achsen, TCP-Marker).
    const f = frames[this.nSegments];
    this.flange.matrix.set(
      f[0], f[1], f[2], f[3],
      f[4], f[5], f[6], f[7],
      f[8], f[9], f[10], f[11],
      f[12], f[13], f[14], f[15],
    );
  }

  /** Hängt ein Objekt an den Flansch (Flansch-Koordinaten). Ersetzt kein anderes. */
  attachToFlange(obj: THREE.Object3D): void {
    this.flange.add(obj);
  }

  /** Entfernt alle zuvor angehängten Flansch-Objekte (behält keine Referenzen). */
  clearFlange(): void {
    this.flange.clear();
  }

  /** Meldet die Instanz vom globalen Modus-Zustand ab (beim Entfernen aus der Szene). */
  dispose(): void {
    instances.delete(this);
  }
}

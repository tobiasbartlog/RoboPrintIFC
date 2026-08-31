/**
 * Workstation-3D-Editor (Issue #78) — stellt den Roboter auf ein hochgeladenes
 * Workstation-Mesh und wählt die Arbeitsfläche. Er ist das Gegenstück zum
 * Endeffektor-Konfigurator (`configurator.ts`): dort hängt ein Werkzeug **unter**
 * den Flansch, hier steht der Roboter **oben auf** einer Fläche.
 *
 * Wiederverwendet die three.js-freie Mathematik aus `face-align.ts`
 * (`PlanarRegionIndex` fürs Flächen-Picken, `mountBaseToSurface` fürs Aufstellen)
 * und `render/arm.ts` (Kapsel-Arm in Home-Pose, am `robot_base_frame` verankert).
 * Die eigentliche Bohrbild-Erkennung rechnet der Core (POST detect-base-holes);
 * diese Klasse zeigt nur das Ergebnis und schnappt den Roboter darauf (ADR-007).
 *
 * Alle Frames sind Mesh-/Workstation-lokal (z-hoch, mm, ADR-006), identisch zum
 * Core-Matcher. Der Editor ist optional in die `WorkstationLibrary` injiziert —
 * ohne ihn (jsdom-Tests) bleibt die Bibliothek WebGL-frei.
 */

import * as THREE from "three";

import type { DetectHolesResult, Frame, WorkstationDef } from "../api/projects";
import { M1013_DH, M1013_HOME_RAD } from "../kinematics/robot";
import { ArmView } from "../render/arm";
import { loadToolMesh, parseToolMesh } from "../render/toolmesh";
import { createViewport } from "../scene/setup";
import {
  nearestBoundaryEdge,
  regionBoundaryEdges,
  slideToEdge,
  type EdgeSegment,
} from "./edge-slide";
import {
  mountBaseToSurface,
  PlanarRegionIndex,
  type PlanarRegion,
  type Vec3,
} from "./face-align";
import type { WorkstationPlacement } from "./workstation-payload";

export interface WorkstationSceneCallbacks {
  /** Bohrbild-Erkennung anstoßen (POST /workstations/{name}/detect-base-holes). */
  onDetect(name: string, robot: string): Promise<DetectHolesResult>;
}

const CLICK_MOVE_TOLERANCE_PX = 5;
const AXES_MM = 200;
const IDENTITY_ROBOT_POSE = M1013_HOME_RAD;

/** Was der Editor an `getPlacement` liefert (mesh nur bei Neu-Upload). */
type PickMode = "base" | "surface" | "edge" | null;

/** Anhebung (mm) der Kanten-Marker über die Fläche gegen z-Fighting. */
const EDGE_MARKER_LIFT_MM = 1;

/** Frame [w,x,y,z] → three.js-Objekt (Quaternion {x,y,z,w}). */
function applyFrameToObject(obj: THREE.Object3D, frame: Frame): void {
  const p = frame.pos_mm as number[];
  const q = frame.quat as number[];
  obj.position.set(p[0], p[1], p[2]);
  obj.quaternion.set(q[1], q[2], q[3], q[0]);
}

/** Frame (pos_mm + quat [w,x,y,z]) → zeilenmajor 4×4 Anker für `ArmView.setPose`. */
function frameToAnchor(frame: Frame): number[] {
  const [w, x, y, z] = frame.quat as number[];
  const [px, py, pz] = frame.pos_mm as number[];
  const xx = x * x, yy = y * y, zz = z * z;
  const xy = x * y, xz = x * z, yz = y * z;
  const wx = w * x, wy = w * y, wz = w * z;
  return [
    1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy), px,
    2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx), py,
    2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy), pz,
    0, 0, 0, 1,
  ];
}

/** Absoluter FS-Mesh-Pfad → Vite-/@fs/-URL (identisch zu configurator.ts). */
function toFsUrl(meshPath: string): string {
  return `/@fs/${meshPath.replace(/\\/g, "/")}`;
}

export class WorkstationScene {
  private readonly viewport = createViewport(byId<HTMLElement>("ws-viewport"));
  private readonly arm = new ArmView(M1013_DH);
  private readonly raycaster = new THREE.Raycaster();
  private readonly holeMarkers = new THREE.Group();

  // Szene-Objekte
  private meshObject: THREE.Object3D | null = null;
  private surfaceMarker: THREE.Object3D | null = null;
  private highlightMesh: THREE.Mesh | null = null;
  private highlightedRegion: PlanarRegion | null = null;
  private regionIndex: { soup: Vec3[]; index: PlanarRegionIndex } | null = null;

  // Zustand
  private pickMode: PickMode = null;
  private pickedBaseFace: { normal: Vec3; point: Vec3; boundary: EdgeSegment[] } | null = null;
  private slideEdge: EdgeSegment | null = null;
  private edgeMarker: THREE.Line | null = null;
  private hoverEdgeMarker: THREE.Line | null = null;
  private robotBaseFrame: Frame | null = null;
  private workSurfaceFrame: Frame | null = null;
  private meshBytes: ArrayBuffer | null = null;
  private meshFilename = "";
  private editingName: string | null = null;
  private hasSavedMesh = false;
  private _busy = false;

  // DOM
  private readonly fileInput = byId<HTMLInputElement>("ws-mesh-input");
  private readonly basePickBtn = byId<HTMLButtonElement>("ws-base-pick");
  private readonly rotationInput = byId<HTMLInputElement>("ws-base-rotation");
  private readonly edgePickBtn = byId<HTMLButtonElement>("ws-edge-pick");
  private readonly edgeDistanceInput = byId<HTMLInputElement>("ws-edge-distance");
  private readonly edgeClearBtn = byId<HTMLButtonElement>("ws-edge-clear");
  private readonly surfacePickBtn = byId<HTMLButtonElement>("ws-surface-pick");
  private readonly snapRobotSel = byId<HTMLSelectElement>("ws-snap-robot");
  private readonly autoSnapBtn = byId<HTMLButtonElement>("ws-autosnap");
  private readonly clearBtn = byId<HTMLButtonElement>("ws-clear-placement");
  private readonly statusEl = byId<HTMLElement>("ws-place-status");

  constructor(private readonly callbacks: WorkstationSceneCallbacks) {
    this.arm.setPose(IDENTITY_ROBOT_POSE, identityMat());
    this.arm.visible = false;
    this.viewport.world.add(this.arm.group);
    this.viewport.world.add(this.holeMarkers);

    this._wirePicking();
    this.fileInput.addEventListener("change", () => void this._onFileChosen());
    this.basePickBtn.addEventListener("click", () => this._togglePickMode("base"));
    this.surfacePickBtn.addEventListener("click", () => this._togglePickMode("surface"));
    this.edgePickBtn.addEventListener("click", () => this._togglePickMode("edge"));
    this.edgeClearBtn.addEventListener("click", () => this._clearSlideEdge());
    this.edgeDistanceInput.addEventListener("input", () => this._applyBase());
    this.rotationInput.addEventListener("input", () => this._applyBase());
    this.autoSnapBtn.addEventListener("click", () => void this._onAutoSnap());
    this.clearBtn.addEventListener("click", () => this._clearPlacement());
    this.reset();
  }

  /** Roboter-Katalog fürs Auto-Snap-Ziel (welcher Roboter, dessen Bohrbild passt). */
  setRobots(names: string[]): void {
    const prev = this.snapRobotSel.value;
    this.snapRobotSel.replaceChildren(
      ...names.map((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        return opt;
      }),
    );
    if (names.includes(prev)) this.snapRobotSel.value = prev;
  }

  /** Setzt den Editor auf den Leerzustand (neue Workstation / Galerie). */
  reset(): void {
    this._removeMesh();
    this._clearHighlight();
    this._setSurfaceMarker(null);
    this.holeMarkers.clear();
    this.arm.visible = false;
    this.pickMode = null;
    this.pickedBaseFace = null;
    this._setSlideEdge(null);
    this.robotBaseFrame = null;
    this.workSurfaceFrame = null;
    this.meshBytes = null;
    this.meshFilename = "";
    this.editingName = null;
    this.hasSavedMesh = false;
    this.fileInput.value = "";
    this.rotationInput.value = "0";
    this.edgeDistanceInput.value = "100";
    this._syncButtons();
    this._setStatus("Mesh laden (optional) — dann Roboter auf eine Fläche stellen.");
  }

  /**
   * Lädt eine bestehende Workstation in den Editor (Bearbeiten): das gespeicherte
   * Mesh + die Platzierungs-Frames werden exakt wiederhergestellt (kein Re-Upload).
   */
  async loadFromDef(ws: WorkstationDef): Promise<void> {
    this.reset();
    this.editingName = ws.name;
    if (ws.mesh_path && ws.mesh) {
      this._setStatus(`Lade Mesh ${ws.mesh} …`);
      try {
        const obj = await loadToolMesh(toFsUrl(ws.mesh_path), ws.mesh);
        this._adoptMesh(obj);
        this.meshFilename = ws.mesh;
        this.hasSavedMesh = true;
      } catch (err) {
        this._setStatus(`Mesh konnte nicht geladen werden: ${err}`);
        return;
      }
    }
    if (ws.robot_base_frame) {
      this.robotBaseFrame = ws.robot_base_frame;
      this._placeArm(this.robotBaseFrame);
    }
    if (ws.work_surface_frame) {
      this.workSurfaceFrame = ws.work_surface_frame;
      this._setSurfaceMarker(this.workSurfaceFrame);
    }
    this._syncButtons();
    this._setStatus(
      this.meshObject
        ? "Gespeicherte Platzierung wiederhergestellt. Fläche anklicken zum Ändern."
        : "Keine Mesh-Datei — optional eine hochladen und den Roboter platzieren.",
    );
  }

  /** Liefert Mesh (nur bei Neu-Upload) + aktuelle Frames für den Save-Request. */
  getPlacement(): WorkstationPlacement {
    return {
      ...(this.meshBytes
        ? { meshBase64: arrayBufferToBase64(this.meshBytes), meshFilename: this.meshFilename }
        : {}),
      robotBaseFrame: this.robotBaseFrame,
      workSurfaceFrame: this.workSurfaceFrame,
    };
  }

  // --- Mesh-Handling ------------------------------------------------------

  private async _onFileChosen(): Promise<void> {
    const file = this.fileInput.files?.[0];
    if (!file) return;
    this._setStatus(`Lade ${file.name} …`);
    try {
      const buffer = await file.arrayBuffer();
      const obj = await parseToolMesh(buffer, file.name);
      this._adoptMesh(obj);
      this.meshBytes = buffer;
      this.meshFilename = file.name;
      // Neues Mesh macht die alte Platzierung + das gespeicherte Mesh ungültig.
      this.hasSavedMesh = false;
      this.robotBaseFrame = null;
      this.workSurfaceFrame = null;
      this.pickedBaseFace = null;
      this._setSlideEdge(null);
      this.arm.visible = false;
      this._setSurfaceMarker(null);
      this.holeMarkers.clear();
      this._syncButtons();
      this._setStatus(`Mesh geladen — „Roboter platzieren" wählen und eine Fläche anklicken.`);
    } catch (err) {
      this._setStatus(`Mesh konnte nicht geladen werden: ${err}`);
    }
  }

  private _adoptMesh(obj: THREE.Object3D): void {
    this._removeMesh();
    this.meshObject = obj;
    applyFrameToObject(obj, { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] });
    this.viewport.world.add(obj);
    this.viewport.fitTo(obj);
  }

  private _removeMesh(): void {
    this._clearHighlight();
    this.regionIndex = null;
    if (this.meshObject) {
      this.viewport.world.remove(this.meshObject);
      disposeTree(this.meshObject);
      this.meshObject = null;
    }
  }

  // --- Picken (Fläche → Basis / Arbeitsfläche), gespiegelt aus configurator.ts

  private _wirePicking(): void {
    const canvas = this.viewport.canvas;
    let down: { x: number; y: number } | null = null;
    canvas.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY };
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved <= CLICK_MOVE_TOLERANCE_PX) this._onPick(e.clientX, e.clientY);
    });
    let hoverPending = false;
    canvas.addEventListener("pointermove", (e) => {
      if (e.buttons !== 0 || this.pickMode === null) {
        this._clearHighlight();
        return;
      }
      if (hoverPending) return;
      hoverPending = true;
      const { clientX, clientY } = e;
      requestAnimationFrame(() => {
        hoverPending = false;
        this._updateHover(clientX, clientY);
      });
    });
    canvas.addEventListener("pointerleave", () => this._clearHighlight());
  }

  private _regionUnderCursor(clientX: number, clientY: number):
    | { region: PlanarRegion; soup: Vec3[]; localPoint: Vec3 }
    | null {
    if (!this.meshObject) return null;
    const rect = this.viewport.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(ndc, this.viewport.camera);
    const hits = this.raycaster.intersectObject(this.meshObject, true);
    const hit = hits.find((h) => h.face);
    if (!hit || hit.faceIndex == null) return null;
    const mesh = hit.object as THREE.Mesh;
    if (!mesh.isMesh) return null;
    const entry = this._regionIndexFor(mesh);
    // Klickpunkt in Mesh-lokale Koordinaten (derselbe Raum wie die Soup).
    const local = this.meshObject.worldToLocal(hit.point.clone());
    return {
      region: entry.index.regionAt(hit.faceIndex),
      soup: entry.soup,
      localPoint: [local.x, local.y, local.z],
    };
  }

  /** Dreiecks-Soup + Region-Index in Mesh-lokalen Koordinaten (einmal je Upload). */
  private _regionIndexFor(mesh: THREE.Mesh): { soup: Vec3[]; index: PlanarRegionIndex } {
    if (this.regionIndex) return this.regionIndex;
    this.meshObject?.updateMatrixWorld(true);
    const root = this.meshObject?.matrixWorld.clone().invert() ?? new THREE.Matrix4();
    const toLocal = root.multiply(mesh.matrixWorld);
    const pos = mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    const index = mesh.geometry.getIndex();
    const tmp = new THREE.Vector3();
    const triCount = Math.floor((index ? index.count : pos.count) / 3);
    const soup: Vec3[] = [];
    for (let t = 0; t < triCount; t++) {
      for (let k = 0; k < 3; k++) {
        const vi = index ? index.getX(t * 3 + k) : t * 3 + k;
        tmp.fromBufferAttribute(pos, vi).applyMatrix4(toLocal);
        soup.push([tmp.x, tmp.y, tmp.z]);
      }
    }
    this.regionIndex = { soup, index: new PlanarRegionIndex(soup) };
    return this.regionIndex;
  }

  private _updateHover(clientX: number, clientY: number): void {
    const found = this._regionUnderCursor(clientX, clientY);
    if (!found) {
      this._clearHighlight();
      return;
    }
    if (this.pickMode === "edge") {
      // Kanten-Modus: statt der Fläche die nächstgelegene Randkante zeigen.
      this._clearRegionOverlay();
      const hit = this.pickedBaseFace
        ? nearestBoundaryEdge(this.pickedBaseFace.boundary, found.localPoint)
        : null;
      this._setHoverEdgeMarker(hit?.edge ?? null);
      return;
    }
    if (this.highlightedRegion === found.region) return;
    this._clearHighlight();
    this.highlightedRegion = found.region;
    const positions = new Float32Array(found.region.triangles.length * 9);
    let o = 0;
    for (const t of found.region.triangles) {
      for (let k = 0; k < 3; k++) {
        const v = found.soup[t * 3 + k];
        positions[o++] = v[0];
        positions[o++] = v[1];
        positions[o++] = v[2];
      }
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.MeshBasicMaterial({
      color: this.pickMode === "surface" ? 0x4dd0ff : 0xffb54d,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
    const overlay = new THREE.Mesh(geom, mat);
    overlay.raycast = () => {};
    overlay.renderOrder = 2;
    this.highlightMesh = overlay;
    this.meshObject?.add(overlay);
  }

  private _clearHighlight(): void {
    this._clearRegionOverlay();
    this._setHoverEdgeMarker(null);
  }

  private _clearRegionOverlay(): void {
    if (this.highlightMesh) {
      this.highlightMesh.removeFromParent();
      this.highlightMesh.geometry.dispose();
      (this.highlightMesh.material as THREE.Material).dispose();
      this.highlightMesh = null;
    }
    this.highlightedRegion = null;
  }

  private _onPick(clientX: number, clientY: number): void {
    if (this.pickMode === null) return;
    const found = this._regionUnderCursor(clientX, clientY);
    if (!found) {
      this._setStatus("Keine Fläche getroffen — direkt auf das Mesh klicken.");
      return;
    }
    if (this.pickMode === "surface") {
      // Arbeitsfläche: Mittelpunkt + Normale (Ursprung im Zentroid, +z = Normale).
      this.workSurfaceFrame = mountBaseToSurface(found.region.normal, found.region.centroid, 0);
      this._setSurfaceMarker(this.workSurfaceFrame);
      this._setStatus(
        `Arbeitsfläche gesetzt (${found.region.triangles.length} Dreiecke). ` +
          "Modus bleibt aktiv — über den Button beenden.",
      );
    } else if (this.pickMode === "edge") {
      // Randkante der Standfläche: die dem Klickpunkt nächste Kante zieht die Basis an.
      if (!this.pickedBaseFace) {
        this._setStatus("Zuerst den Roboter auf eine Fläche stellen, dann die Kante wählen.");
        return;
      }
      const hit = nearestBoundaryEdge(this.pickedBaseFace.boundary, found.localPoint);
      if (!hit) {
        this._setStatus("Keine Randkante gefunden — die Standfläche hat keinen Rand.");
        return;
      }
      this._setSlideEdge(hit.edge);
      this._applyBase();
    } else {
      // Roboterbasis: Mittelpunkt der ganzen ebenen Fläche (nicht der Klickpunkt);
      // die Randkanten der Fläche merken wir uns fürs Kanten-Schieben.
      this.pickedBaseFace = {
        normal: found.region.normal,
        point: found.region.centroid,
        boundary: regionBoundaryEdges(found.soup, found.region.triangles),
      };
      this._setSlideEdge(null); // neue Standfläche ⇒ alte Kantenwahl verfällt
      this._applyBase();
    }
  }

  private _applyBase(): void {
    if (!this.pickedBaseFace) return;
    const deg = Number.parseFloat(this.rotationInput.value) || 0;
    let point = this.pickedBaseFace.point;
    let where = "Flächen-Mittelpunkt";
    if (this.slideEdge) {
      const distance = Math.max(0, Number.parseFloat(this.edgeDistanceInput.value) || 0);
      const slid = slideToEdge(this.slideEdge, this.pickedBaseFace.point, distance);
      if (slid) {
        point = slid;
        where = `Kante, Abstand ${distance} mm (Basis-Mitte → Kante)`;
      } else {
        this._setSlideEdge(null);
        where = "Flächen-Mittelpunkt — gewählte Kante war entartet";
      }
    }
    this.robotBaseFrame = mountBaseToSurface(this.pickedBaseFace.normal, point, deg);
    this._placeArm(this.robotBaseFrame);
    this._syncButtons();
    this._setStatus(`Roboter auf die Fläche gestellt (${where}, Drehung ${deg}°).`);
  }

  /** Kantenwahl aufheben — die Basis rutscht zurück auf den Flächen-Mittelpunkt. */
  private _clearSlideEdge(): void {
    if (!this.slideEdge) return;
    this._setSlideEdge(null);
    this._applyBase();
  }

  /** Gewählte Kante setzen/löschen + ihren Marker nachziehen. */
  private _setSlideEdge(edge: EdgeSegment | null): void {
    this.slideEdge = edge;
    if (this.edgeMarker) {
      this.edgeMarker.removeFromParent();
      this.edgeMarker.geometry.dispose();
      (this.edgeMarker.material as THREE.Material).dispose();
      this.edgeMarker = null;
    }
    if (edge && this.meshObject && this.pickedBaseFace) {
      this.edgeMarker = makeEdgeLine(edge, this.pickedBaseFace.normal, 0xff8a3c);
      this.meshObject.add(this.edgeMarker);
    }
    this._syncButtons();
  }

  /** Hover-Vorschau im Kanten-Modus (Referenzvergleich — Kanten sind stabil je Fläche). */
  private _setHoverEdgeMarker(edge: EdgeSegment | null): void {
    if (this.hoverEdgeMarker && (this.hoverEdgeMarker.userData.edge as EdgeSegment) === edge) {
      return;
    }
    if (this.hoverEdgeMarker) {
      this.hoverEdgeMarker.removeFromParent();
      this.hoverEdgeMarker.geometry.dispose();
      (this.hoverEdgeMarker.material as THREE.Material).dispose();
      this.hoverEdgeMarker = null;
    }
    if (edge && this.meshObject && this.pickedBaseFace) {
      this.hoverEdgeMarker = makeEdgeLine(edge, this.pickedBaseFace.normal, 0xffd28a);
      this.hoverEdgeMarker.userData.edge = edge;
      this.meshObject.add(this.hoverEdgeMarker);
    }
  }

  private _placeArm(frame: Frame | null): void {
    if (!frame) {
      this.arm.visible = false;
      return;
    }
    this.arm.setPose(IDENTITY_ROBOT_POSE, frameToAnchor(frame));
    this.arm.visible = true;
  }

  private _togglePickMode(mode: "base" | "surface" | "edge"): void {
    this.pickMode = this.pickMode === mode ? null : mode;
    this._clearHighlight();
    this._syncButtons();
    if (this.pickMode === "base") {
      this._setStatus("Fläche für die Roboterbasis anklicken (drehbar über das Winkelfeld).");
    } else if (this.pickMode === "surface") {
      this._setStatus("Fläche als Arbeitsfläche anklicken.");
    } else if (this.pickMode === "edge") {
      this._setStatus(
        "Randkante der Standfläche anklicken — der Roboter rutscht mit dem " +
          "eingestellten Abstand an diese Kante.",
      );
    }
  }

  private _clearPlacement(): void {
    this.pickedBaseFace = null;
    this._setSlideEdge(null);
    this.robotBaseFrame = null;
    this.workSurfaceFrame = null;
    this.arm.visible = false;
    this._setSurfaceMarker(null);
    this.holeMarkers.clear();
    this.rotationInput.value = "0";
    this._syncButtons();
    this._setStatus("Platzierung gelöscht.");
  }

  // --- Auto-Snap ans Bohrbild (Core-Erkennung) ----------------------------

  private async _onAutoSnap(): Promise<void> {
    if (this._busy) return;
    if (!this.hasSavedMesh || !this.editingName) {
      this._setStatus(
        "Für die Bohrbild-Erkennung zuerst die Workstation mit Mesh speichern, dann erneut öffnen.",
      );
      return;
    }
    const robot = this.snapRobotSel.value;
    if (!robot) {
      this._setStatus("Keinen Roboter für den Abgleich gewählt.");
      return;
    }
    this._busy = true;
    this._syncButtons();
    this._setStatus(`Erkenne Bohrbild für „${robot}" …`);
    try {
      const result = await this.callbacks.onDetect(this.editingName, robot);
      this._showDetectedHoles(result.detected_holes);
      if (result.matched && result.robot_base_frame) {
        this.robotBaseFrame = result.robot_base_frame;
        this.pickedBaseFace = null; // aus Bohrbild geschnappt, nicht per Flächenklick
        this._setSlideEdge(null); // verschraubt ⇒ Kanten-Schieben gegenstandslos
        this._placeArm(this.robotBaseFrame);
        this._setStatus(
          `${result.message} — Roboter am Bohrbild ausgerichtet. Zum Übernehmen speichern.`,
        );
      } else {
        const warn = result.warnings.length ? ` (${result.warnings.join("; ")})` : "";
        this._setStatus(`${result.message}${warn}`);
      }
    } catch (err) {
      this._setStatus(`Bohrbild-Erkennung fehlgeschlagen: ${err}`);
    } finally {
      this._busy = false;
      this._syncButtons();
    }
  }

  private _showDetectedHoles(holes: DetectHolesResult["detected_holes"]): void {
    this.holeMarkers.clear();
    const mat = new THREE.MeshBasicMaterial({ color: 0xff44cc, depthTest: false });
    for (const hole of holes) {
      const r = Math.max(hole.radius_mm, 3);
      const marker = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 10), mat);
      marker.position.set(hole.center_mm[0], hole.center_mm[1], hole.center_mm[2]);
      marker.renderOrder = 3;
      this.holeMarkers.add(marker);
    }
  }

  // --- Hilfen -------------------------------------------------------------

  private _setSurfaceMarker(frame: Frame | null): void {
    if (this.surfaceMarker) {
      this.viewport.world.remove(this.surfaceMarker);
      disposeTree(this.surfaceMarker);
      this.surfaceMarker = null;
    }
    if (!frame) return;
    const group = new THREE.Group();
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(160, 40),
      new THREE.MeshBasicMaterial({
        color: 0x4dd0ff,
        transparent: true,
        opacity: 0.28,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    group.add(disc, new THREE.AxesHelper(AXES_MM));
    applyFrameToObject(group, frame);
    this.surfaceMarker = group;
    this.viewport.world.add(group);
  }

  private _syncButtons(): void {
    const hasMesh = !!this.meshObject;
    this.basePickBtn.disabled = !hasMesh;
    this.surfacePickBtn.disabled = !hasMesh;
    this.basePickBtn.classList.toggle("armed", this.pickMode === "base");
    this.surfacePickBtn.classList.toggle("armed", this.pickMode === "surface");
    this.edgePickBtn.classList.toggle("armed", this.pickMode === "edge");
    // Kanten-Schieben braucht eine per Klick gewählte Standfläche (nicht nur
    // einen gespeicherten/geschnappten Frame — dem fehlen die Randkanten).
    this.edgePickBtn.disabled = !this.pickedBaseFace;
    this.edgeDistanceInput.disabled = !this.slideEdge;
    this.edgeClearBtn.disabled = !this.slideEdge;
    this.rotationInput.disabled = !this.robotBaseFrame && !this.pickedBaseFace;
    // Auto-Snap braucht ein bereits gespeichertes Mesh (Core liest die Datei).
    this.autoSnapBtn.disabled = this._busy || !this.hasSavedMesh;
    this.clearBtn.disabled = !this.robotBaseFrame && !this.workSurfaceFrame;
  }

  private _setStatus(text: string): void {
    this.statusEl.textContent = text;
  }
}

/** ArrayBuffer → base64 (chunked, wie configurator.ts). */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/**
 * Linien-Marker für eine Randkante (mesh-lokal), leicht entlang der
 * Flächennormale angehoben, damit er nicht in der Tischplatte versinkt.
 */
function makeEdgeLine(edge: EdgeSegment, normal: Vec3, color: number): THREE.Line {
  const lift = EDGE_MARKER_LIFT_MM;
  const pts = [
    new THREE.Vector3(...edge.a).addScaledVector(new THREE.Vector3(...normal), lift),
    new THREE.Vector3(...edge.b).addScaledVector(new THREE.Vector3(...normal), lift),
  ];
  const geom = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = new THREE.LineBasicMaterial({ color, depthTest: false });
  const line = new THREE.Line(geom, mat);
  line.raycast = () => {};
  line.renderOrder = 3;
  return line;
}

/** Identitäts-Anker (zeilenmajor 4×4) für die Home-Pose vor der Platzierung. */
function identityMat(): number[] {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

/** Gibt Geometrien/Materialien eines Teilbaums frei (kein GPU-Leck bei Neu-Upload). */
function disposeTree(root: THREE.Object3D): void {
  root.traverse((obj) => {
    const node = obj as Partial<THREE.Mesh>;
    node.geometry?.dispose();
    const material = node.material;
    if (Array.isArray(material)) for (const m of material) m.dispose();
    else material?.dispose();
  });
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

/**
 * Endeffektor-Konfigurator (Bibliothek, Issue #28/#52) — Stammdatenpflege
 * außerhalb des Prozesses (`viewer/CONTEXT.md`). Ein realer Endeffektor wird
 * hochgeladen, per **Face-Align** am Roboterflansch ausgerichtet, mit TCP +
 * Kanälen versehen und über die API abgelegt.
 *
 * Positionier-Modell (Issue #52, ersetzt den früheren Frei-Drag-Gizmo): der
 * Nutzer klickt eine **Montagefläche** des Mesh an (Hover hebt die ebene
 * Zielfläche hervor, #55); ihre Normale + ihr **Flächen-Mittelpunkt**
 * (in Mesh-lokalen Koordinaten) gehen in die reine Mathematik `ui/face-align.ts`,
 * die den Flansch-lokalen Mesh-Transform liefert (Fläche bündig auf Flansch,
 * Körper ragt weg). Ein Winkel dreht um die Flansch-z-Achse. Der TCP sitzt
 * automatisch auf der Mesh-Spitze (weitester Punkt entlang +z); alternativ
 * (Issue #54) per Klick auf die Öffnungsfläche (Mittelpunkt der
 * zusammenhängenden ebenen Fläche, `planarRegionCentroid`) oder frei über
 * x/y/z-Felder relativ zum Flansch. Die gespeicherten Frames sind
 * **berechnete Daten** — nicht mehr aus
 * einer Gizmo-World/Local-Zerlegung zurückgelesen (das erzeugte am
 * `matrixAutoUpdate=false`-Flansch ein kaputtes TCP, #52).
 */

import * as THREE from "three";

import type { ToolDef } from "../api/projects";
import { M1013_DH, M1013_HOME_RAD } from "../kinematics/robot";
import { identity } from "../kinematics/fk";
import { ArmView } from "../render/arm";
import { loadToolMesh, parseToolMesh } from "../render/toolmesh";
import { createViewport } from "../scene/setup";
import {
  buildCreateToolRequest,
  buildUpdateToolRequest,
  type ChannelInput,
  type CreateToolPayload,
  type UpdateToolPayload,
} from "./configurator-payload";
import {
  applyFrame,
  autoTcpAlongFlangeZ,
  centerAtFlange,
  mountFaceToFlange,
  nozzleQuatFromNormal,
  offsetFrame,
  PlanarRegionIndex,
  quatRotate,
  tcpAtPosition,
  type Frame,
  type PlanarRegion,
  type Vec3,
} from "./face-align";

export interface ConfiguratorCallbacks {
  /** Endeffektor anlegen (POST /tools). Liefert die frische Kenndaten-Karte zurück. */
  onCreateTool(req: CreateToolPayload): Promise<ToolDef>;
  /**
   * Endeffektor bearbeiten (PUT /tools/{name}, Issue #56). `name` ist die
   * Identität (kein Rename); das Mesh im Payload ist optional (nur bei Re-Upload).
   */
  onUpdateTool(name: string, req: UpdateToolPayload): Promise<ToolDef>;
  /** Nach erfolgreichem Speichern (Anlegen ODER Bearbeiten) — zurück zur Galerie (US 16). */
  onSaved?(tool: ToolDef): void;
}

/** Absoluter FS-Mesh-Pfad → Vite-/@fs/-URL (identisch zu main.ts `fsUrl`). */
function toFsUrl(meshPath: string): string {
  return `/@fs/${meshPath.replace(/\\/g, "/")}`;
}

const FLANGE_AXES_MM = 250;
const TCP_AXES_MM = 120;
const IDENTITY_FRAME: Frame = { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] };
const CLICK_MOVE_TOLERANCE_PX = 5;

/** Frame [w,x,y,z] → three.js-Objekt (Quaternion {x,y,z,w}). */
function applyFrameToObject(obj: THREE.Object3D, frame: Frame): void {
  obj.position.set(frame.pos_mm[0], frame.pos_mm[1], frame.pos_mm[2]);
  obj.quaternion.set(frame.quat[1], frame.quat[2], frame.quat[3], frame.quat[0]);
}

export class ToolConfigurator {
  private readonly viewport = createViewport(byId<HTMLElement>("cfg-viewport"));
  private readonly arm = new ArmView(M1013_DH);
  private readonly raycaster = new THREE.Raycaster();

  // Flansch-Kinder
  private meshObject: THREE.Object3D | null = null;
  private readonly tcpMarker = new THREE.Group();

  // Berechnete Frames (Quelle der Wahrheit fürs Speichern, #52).
  private mountFrame: Frame = IDENTITY_FRAME;
  /**
   * Montage vor dem Feinversatz (#67): aus `centerAtFlange` (Upload) oder
   * `mountFaceToFlange` (Flächen-Klick). `mountFrame` = `mountBaseFrame` +
   * `mountOffset`; so nudged der Versatz die aktuelle Basis, ohne sie neu zu
   * berechnen.
   */
  private mountBaseFrame: Frame = IDENTITY_FRAME;
  /** Flansch-lokaler Feinversatz der Montage (#67), x/y in der Ebene, z axial. */
  private mountOffset: Vec3 = [0, 0, 0];
  private tcpFrame: Frame = { pos_mm: [0, 0, 150], quat: [1, 0, 0, 0] };
  /** Zuletzt gewählte Fläche in Mesh-lokalen Koordinaten (für erneutes Drehen). */
  private pickedFace: { normal: Vec3; point: Vec3 } | null = null;
  /**
   * TCP-Quelle (Issue #54): `auto` = Spitze entlang +Flansch-z, `face` =
   * Mittelpunkt der angeklickten Öffnungsfläche (mesh-lokal gemerkt, rechnet
   * bei Montage-Änderungen mit), `manual` = die x/y/z-Felder gelten.
   */
  private tcpSource: "auto" | "face" | "manual" = "auto";
  /** Flächen-Mittelpunkt der TCP-Fläche in Mesh-lokalen Koordinaten. */
  private pickedTcpCentroid: Vec3 | null = null;
  /**
   * Außennormale der TCP-Öffnungsfläche in Mesh-lokalen Koordinaten (#58): dreht
   * bei Montage-Änderungen mit und legt die TCP-z-Achse = Düsen-/Extrusionsachse
   * fest. `null` ⇒ TCP-Orientierung bleibt Identität (auto/manual).
   */
  private pickedTcpNormal: Vec3 | null = null;
  /** Mesh-Klicks setzen den TCP statt der Montagefläche (bis Button-Ende, #55). */
  private tcpPickArmed = false;
  /** Dreiecks-Soup + Region-Index je Teil-Mesh (einmal je Upload, #55). */
  private readonly regionIndices = new Map<THREE.Object3D, {
    soup: Vec3[];
    index: PlanarRegionIndex;
  }>();
  /** Hover-Overlay der ebenen Fläche unter dem Cursor (Kind des Endeffektor-Mesh). */
  private highlightMesh: THREE.Mesh | null = null;
  private highlightedRegion: PlanarRegion | null = null;

  // Upload-Zustand
  private meshBytes: ArrayBuffer | null = null;
  private meshFilename = "";

  // Edit-Modus (Issue #56): beim „Bearbeiten" ist ein bestehender Endeffektor
  // geladen; Speichern ruft dann updateTool statt createTool, der Name ist fix.
  private _editMode = false;
  private _editingName: string | null = null;
  /** Beim Bearbeiten geladenes, nicht neu hochgeladenes Mesh (bleibt erhalten). */
  private _hasExistingMesh = false;

  // DOM
  private readonly fileInput = byId<HTMLInputElement>("cfg-mesh-input");
  private readonly nameInput = byId<HTMLInputElement>("cfg-name");
  private readonly heading = byId<HTMLElement>("cfg-heading");
  private readonly vendorInput = byId<HTMLInputElement>("cfg-vendor");
  private readonly weightInput = byId<HTMLInputElement>("cfg-weight");
  private readonly cogX = byId<HTMLInputElement>("cfg-cog-x");
  private readonly cogY = byId<HTMLInputElement>("cfg-cog-y");
  private readonly cogZ = byId<HTMLInputElement>("cfg-cog-z");
  private readonly compatibleRobotsSelect = byId<HTMLSelectElement>("cfg-compatible-robots");
  private readonly channelList = byId<HTMLElement>("cfg-channels");
  private readonly addChannelBtn = byId<HTMLButtonElement>("cfg-add-channel");
  private readonly saveBtn = byId<HTMLButtonElement>("cfg-save-btn");
  private readonly statusEl = byId<HTMLElement>("cfg-status");
  private readonly apiWarning = byId<HTMLElement>("cfg-api-warning");
  private readonly tcpReadout = byId<HTMLElement>("cfg-tcp-readout");
  private readonly mountStatus = byId<HTMLElement>("cfg-mount-status");
  private readonly rotationInput = byId<HTMLInputElement>("cfg-mount-rotation");
  private readonly mountOffX = byId<HTMLInputElement>("cfg-mount-offset-x");
  private readonly mountOffY = byId<HTMLInputElement>("cfg-mount-offset-y");
  private readonly mountOffZ = byId<HTMLInputElement>("cfg-mount-offset-z");
  private readonly tcpPickBtn = byId<HTMLButtonElement>("cfg-tcp-pick");
  private readonly tcpX = byId<HTMLInputElement>("cfg-tcp-x");
  private readonly tcpY = byId<HTMLInputElement>("cfg-tcp-y");
  private readonly tcpZ = byId<HTMLInputElement>("cfg-tcp-z");

  private _apiAvailable = false;
  private _busy = false;
  //: Roboter-Katalog für das Mehrfach-Auswahlfeld „passt zu Roboter(n)" (#71).
  private _robotNames: string[] = [];
  //: Aktuell gewählte Kompatibilitäts-Tags — überlebt ein spätes setRobots.
  private _selectedRobots: string[] = [];

  constructor(private readonly callbacks: ConfiguratorCallbacks) {
    // Arm aufrecht (Doosan-Nullstellung, #53) + Flansch-Achsen.
    this.arm.setPose(M1013_HOME_RAD, identity());
    this.viewport.world.add(this.arm.group);
    this.arm.attachToFlange(new THREE.AxesHelper(FLANGE_AXES_MM));

    // TCP-Marker (Kugel + Achsen) am Flansch, Startlage entlang Flansch-z.
    // Klein (4 mm), damit er beim präzisen Einstellen die Spitze nicht verdeckt (#55).
    const tcpBall = new THREE.Mesh(
      new THREE.SphereGeometry(4, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xff3333, depthTest: false }),
    );
    tcpBall.renderOrder = 3;
    this.tcpMarker.add(tcpBall, new THREE.AxesHelper(TCP_AXES_MM));
    applyFrameToObject(this.tcpMarker, this.tcpFrame);
    this.arm.attachToFlange(this.tcpMarker);

    this.viewport.fitTo(this.arm.group);

    this._wirePicking();
    this._wireForm();
    this._updateTcpReadout();
    this._syncButtons();
  }

  /** Klick auf eine Mesh-Fläche = Face-Pick (vom Orbit-Drag per Bewegungsschwelle
   *  getrennt); Hover hebt die ebene Zielfläche unter dem Cursor hervor (#55). */
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
    // Hover rAF-gedrosselt; während eines Orbit-Drags (Taste gedrückt) aus.
    let hoverPending = false;
    canvas.addEventListener("pointermove", (e) => {
      if (e.buttons !== 0) {
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

  /** Raycast auf das Endeffektor-Mesh + ebene Fläche um das getroffene Dreieck. */
  private _regionUnderCursor(clientX: number, clientY: number):
    | { mesh: THREE.Mesh; region: PlanarRegion; soup: Vec3[] }
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
    return { mesh, region: entry.index.regionAt(hit.faceIndex), soup: entry.soup };
  }

  /**
   * Dreiecks-Soup + Region-Index eines Teil-Mesh, einmal je Upload gebaut
   * (Mesh-lokale Koordinaten — kürzt Vorfahren inkl. Flansch heraus und ist
   * damit unabhängig von der Montage-Lage und der Flansch-Weltmatrix).
   */
  private _regionIndexFor(mesh: THREE.Mesh): { soup: Vec3[]; index: PlanarRegionIndex } {
    const cached = this.regionIndices.get(mesh);
    if (cached) return cached;
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
    const entry = { soup, index: new PlanarRegionIndex(soup) };
    this.regionIndices.set(mesh, entry);
    return entry;
  }

  private _updateHover(clientX: number, clientY: number): void {
    const found = this._regionUnderCursor(clientX, clientY);
    if (!found) {
      this._clearHighlight();
      return;
    }
    if (this.highlightedRegion === found.region) return;
    this._clearHighlight();
    this.highlightedRegion = found.region;
    // Region-Dreiecke als halbtransparentes Overlay in Mesh-lokalen Koordinaten —
    // als Kind des Endeffektor-Mesh folgt es der Montage-Lage automatisch.
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
      color: this.tcpPickArmed ? 0xff5544 : 0xffb54d,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
    const overlay = new THREE.Mesh(geom, mat);
    overlay.raycast = () => {}; // nie selbst Raycast-Ziel
    overlay.userData.isHighlight = true; // von _meshLocalVertices ausgenommen
    overlay.renderOrder = 2;
    this.highlightMesh = overlay;
    this.meshObject?.add(overlay);
  }

  private _clearHighlight(): void {
    if (this.highlightMesh) {
      this.highlightMesh.removeFromParent();
      this.highlightMesh.geometry.dispose();
      (this.highlightMesh.material as THREE.Material).dispose();
      this.highlightMesh = null;
    }
    this.highlightedRegion = null;
  }

  private _onPick(clientX: number, clientY: number): void {
    const found = this._regionUnderCursor(clientX, clientY);
    if (!found) {
      if (this.meshObject) {
        this.mountStatus.textContent = "Keine Fläche getroffen — direkt auf das Mesh klicken.";
      }
      return;
    }
    if (this.tcpPickArmed) {
      this._onTcpFacePick(found.region);
      return;
    }
    // Montage (#55): der Mittelpunkt der ganzen ebenen Fläche landet im
    // Flansch-Ursprung — nicht der Klickpunkt; so sitzt die Montagefläche
    // exakt zentriert, auch wenn der Klick daneben lag.
    this.pickedFace = { normal: found.region.normal, point: found.region.centroid };
    this._applyMount();
  }

  /** Rechnet Mesh-Transform + Auto-TCP aus der gewählten Fläche + Drehwinkel. */
  private _applyMount(): void {
    if (!this.meshObject || !this.pickedFace) return;
    const deg = Number.parseFloat(this.rotationInput.value) || 0;
    this._applyMountFrame(mountFaceToFlange(this.pickedFace.normal, this.pickedFace.point, deg));
    const off = this.mountOffset.some((v) => v !== 0)
      ? ` Versatz [${this.mountOffset.join(", ")}] mm.`
      : "";
    this.mountStatus.textContent =
      `Fläche ausgerichtet (Drehung ${deg}°).${off} TCP folgt der Montage.`;
  }

  /** Flansch-lokaler Feinversatz aus den Eingabefeldern (leer = 0), #67. */
  private _readMountOffset(): Vec3 {
    return [
      Number.parseFloat(this.mountOffX.value) || 0,
      Number.parseFloat(this.mountOffY.value) || 0,
      Number.parseFloat(this.mountOffZ.value) || 0,
    ];
  }

  /**
   * Legt eine Montage-Basis (aus Upload-Zentrierung oder Flächen-Klick) fest,
   * addiert den aktuellen Feinversatz (#67) und wendet das Ergebnis auf das
   * Mesh an — der TCP rechnet über {@link _recomputeTcp} mit.
   */
  private _applyMountFrame(base: Frame): void {
    this.mountBaseFrame = base;
    this.mountOffset = this._readMountOffset();
    this.mountFrame = offsetFrame(base, this.mountOffset);
    if (this.meshObject) applyFrameToObject(this.meshObject, this.mountFrame);
    this._recomputeTcp();
  }

  /** TCP-Fläche gewählt (Issue #54): Mittelpunkt der zusammenhängenden ebenen
   *  Fläche, mesh-lokal gemerkt wie die Montagefläche. Der Modus bleibt aktiv
   *  (#55) — nachjustieren per weiterem Klick, beenden über den Button. */
  private _onTcpFacePick(region: PlanarRegion): void {
    this.pickedTcpCentroid = region.centroid;
    // #58: Außennormale der Öffnung = Düsenrichtung → orientiert die TCP-z-Achse.
    this.pickedTcpNormal = region.normal;
    this.tcpSource = "face";
    this.mountStatus.textContent =
      `TCP + Düsenrichtung aus der gewählten Fläche gesetzt (${region.triangles.length} Dreiecke). ` +
      "TCP-Modus bleibt aktiv — über den Button beenden.";
    this._recomputeTcp();
  }

  /** Klick-Modus „TCP-Fläche wählen" schalten (Button-Zustand inklusive). */
  private _setTcpPickArmed(armed: boolean): void {
    this.tcpPickArmed = armed;
    this.tcpPickBtn.textContent = armed
      ? "TCP-Klick aktiv — Öffnungsfläche anklicken (hier beenden)"
      : "TCP-Fläche wählen";
    this.tcpPickBtn.classList.toggle("armed", armed);
    this._clearHighlight(); // Farbe des Hovers hängt am Modus
  }

  /** TCP je Quelle (#54): Felder (manual) > gewählte Fläche (face) > Spitze (auto). */
  private _recomputeTcp(): void {
    if (this.tcpSource === "manual") {
      this.tcpFrame = tcpAtPosition(
        Number.parseFloat(this.tcpX.value),
        Number.parseFloat(this.tcpY.value),
        Number.parseFloat(this.tcpZ.value),
      );
    } else if (this.tcpSource === "face" && this.pickedTcpCentroid && this.pickedTcpNormal) {
      // #58: Öffnungsnormale mesh-lokal → in Flansch-Koordinaten drehen (nur
      // Rotation der Montage), dann TCP-z entlang der Düsen-/Extrusionsachse.
      const nozzle = quatRotate(this.mountFrame.quat, this.pickedTcpNormal);
      this.tcpFrame = {
        pos_mm: applyFrame(this.mountFrame, this.pickedTcpCentroid),
        quat: nozzleQuatFromNormal(nozzle),
      };
    } else if (this.meshObject) {
      const verts = this._meshLocalVertices();
      this.tcpFrame = verts.length
        ? autoTcpAlongFlangeZ(verts, this.mountFrame)
        : { pos_mm: [0, 0, 150], quat: [1, 0, 0, 0] };
    }
    // Felder spiegeln den aktiven TCP — außer der Nutzer tippt gerade selbst.
    if (this.tcpSource !== "manual") this._writeTcpInputs();
    applyFrameToObject(this.tcpMarker, this.tcpFrame);
    this._updateTcpReadout();
  }

  private _writeTcpInputs(): void {
    const p = this.tcpFrame.pos_mm;
    this.tcpX.value = p[0].toFixed(1);
    this.tcpY.value = p[1].toFixed(1);
    this.tcpZ.value = p[2].toFixed(1);
  }

  /** Alle Mesh-Vertices in Mesh-lokalen Koordinaten (Geometrie-Raum, vor mountFrame). */
  private _meshLocalVertices(): Vec3[] {
    const obj = this.meshObject;
    if (!obj) return [];
    obj.updateMatrixWorld(true);
    const inv = obj.matrixWorld.clone().invert();
    const m = new THREE.Matrix4();
    const tmp = new THREE.Vector3();
    const verts: Vec3[] = [];
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh || !mesh.geometry || mesh.userData.isHighlight) return;
      const pos = mesh.geometry.getAttribute("position");
      if (!pos) return;
      m.multiplyMatrices(inv, mesh.matrixWorld);
      for (let i = 0; i < pos.count; i++) {
        tmp.fromBufferAttribute(pos as THREE.BufferAttribute, i).applyMatrix4(m);
        verts.push([tmp.x, tmp.y, tmp.z]);
      }
    });
    return verts;
  }

  private _wireForm(): void {
    this.fileInput.addEventListener("change", () => void this._onFileChosen());
    this.rotationInput.addEventListener("input", () => this._applyMount());

    // Feinversatz (#67): schiebt die aktuelle Montage-Basis in der Flanschebene.
    // Mit Fläche über _applyMount (aktualisiert auch den Status), sonst direkt
    // auf die gespeicherte Basis (z. B. die Upload-Zentrierung).
    const onMountOffset = (): void => {
      if (this.pickedFace) this._applyMount();
      else if (this.meshObject) this._applyMountFrame(this.mountBaseFrame);
    };
    for (const el of [this.mountOffX, this.mountOffY, this.mountOffZ]) {
      el.addEventListener("input", onMountOffset);
    }

    // TCP (#54): Tippen schaltet auf manuell; alle drei Felder leer = zurück
    // zu automatisch (Spitze) — die Felder füllen sich dann wieder.
    const onTcpInput = (): void => {
      const empty = [this.tcpX, this.tcpY, this.tcpZ].every((el) => el.value.trim() === "");
      if (empty) {
        this.tcpSource = "auto";
        this.pickedTcpCentroid = null;
        this.pickedTcpNormal = null;
      } else {
        this.tcpSource = "manual";
      }
      this._recomputeTcp();
    };
    for (const el of [this.tcpX, this.tcpY, this.tcpZ]) {
      el.addEventListener("input", onTcpInput);
    }
    this.tcpPickBtn.addEventListener("click", () => this._setTcpPickArmed(!this.tcpPickArmed));

    this.addChannelBtn.addEventListener("click", () => this._addChannelRow());
    // Eine Startzeile, damit mindestens ein Kanal offensichtlich ist.
    this._addChannelRow("pump_a", "analog", "");

    this.saveBtn.addEventListener("click", () => void this._onSave());
  }

  private async _onFileChosen(): Promise<void> {
    const file = this.fileInput.files?.[0];
    if (!file) return;
    this.statusEl.textContent = `Lade ${file.name} …`;
    try {
      const buffer = await file.arrayBuffer();
      const obj = await parseToolMesh(buffer, file.name);
      // Vorheriges Mesh ersetzen.
      this._clearHighlight();
      this.regionIndices.clear();
      if (this.meshObject) this.arm.flange.remove(this.meshObject);
      this.meshObject = obj;
      this.pickedFace = null;
      this.pickedTcpCentroid = null;
      this.pickedTcpNormal = null;
      this.tcpSource = "auto";
      this._setTcpPickArmed(false);
      // Feinversatz (#67) beim neuen Mesh zurücksetzen — er galt der alten Fläche.
      this.mountOffX.value = "";
      this.mountOffY.value = "";
      this.mountOffZ.value = "";
      this.mountOffset = [0, 0, 0];
      applyFrameToObject(obj, IDENTITY_FRAME);
      this.arm.attachToFlange(obj);
      this.meshBytes = buffer;
      this.meshFilename = file.name;
      // Default: Mesh am Flansch **zentrieren**, damit es nicht an seinem
      // Geometrie-Ursprung wegschwebt (#52); die bündige Montage kommt per
      // Flächen-Klick. Der Geometrie-Ursprung liegt oft nicht auf einer
      // Montagefläche → ohne Zentrierung säße das Mesh sichtbar neben dem Flansch.
      this._applyMountFrame(centerAtFlange(this._meshLocalVertices()));
      this.mountStatus.textContent =
        `Mesh geladen und am Flansch zentriert — jetzt die Montagefläche anklicken.`;
      this.statusEl.textContent = "";
      this._syncButtons();
    } catch (err) {
      this.statusEl.textContent = `Mesh konnte nicht geladen werden: ${err}`;
    }
  }

  private _addChannelRow(name = "", kind: "analog" | "digital" = "analog", desc = ""): void {
    const row = document.createElement("div");
    row.className = "cfg-channel-row";

    const nameIn = document.createElement("input");
    nameIn.type = "text";
    nameIn.placeholder = "Kanalname (z. B. pump_a)";
    nameIn.value = name;
    nameIn.className = "cfg-ch-name";

    const kindSel = document.createElement("select");
    kindSel.className = "cfg-ch-kind";
    for (const k of ["analog", "digital"]) {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = k;
      kindSel.append(opt);
    }
    kindSel.value = kind;

    const descIn = document.createElement("input");
    descIn.type = "text";
    descIn.placeholder = "Beschreibung";
    descIn.value = desc;
    descIn.className = "cfg-ch-desc";

    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "×";
    del.className = "cfg-ch-del";
    del.title = "Kanal entfernen";
    del.addEventListener("click", () => row.remove());

    row.append(nameIn, kindSel, descIn, del);
    this.channelList.append(row);
  }

  private _readChannels(): ChannelInput[] {
    const rows = Array.from(this.channelList.querySelectorAll<HTMLElement>(".cfg-channel-row"));
    return rows.map((row) => ({
      name: (row.querySelector<HTMLInputElement>(".cfg-ch-name")?.value ?? "").trim(),
      kind: (row.querySelector<HTMLSelectElement>(".cfg-ch-kind")?.value ?? "analog") as
        | "analog"
        | "digital",
      description: row.querySelector<HTMLInputElement>(".cfg-ch-desc")?.value ?? "",
    }));
  }

  /**
   * Befüllt das Mehrfach-Auswahlfeld „passt zu Roboter(n)" aus GET /robots (#71).
   * Einmalig beim Start verdrahtet (main.ts); die aktuelle Auswahl (`_selectedRobots`)
   * wird nach dem Neuaufbau der Optionen wiederhergestellt, damit eine im Edit-Modus
   * gesetzte Wahl nicht verloren geht, wenn der Katalog später eintrifft.
   */
  setRobots(names: string[]): void {
    this._robotNames = [...names];
    this._renderRobotOptions();
  }

  /** Baut die <option>-Liste neu und markiert die aktuell gewählten Tags. */
  private _renderRobotOptions(): void {
    const selected = new Set(this._selectedRobots);
    // Auch gewählte Tags anzeigen, die (noch) nicht im Katalog stehen — sonst
    // fiele beim Bearbeiten eines Altbestands eine unbekannte Wahl still weg.
    const names = [...this._robotNames];
    for (const s of this._selectedRobots) if (!names.includes(s)) names.push(s);
    this.compatibleRobotsSelect.replaceChildren(
      ...names.map((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        opt.selected = selected.has(name);
        return opt;
      }),
    );
  }

  /** Setzt die gewählten Kompatibilitäts-Tags und spiegelt sie ins Auswahlfeld. */
  private _setSelectedRobots(names: string[]): void {
    this._selectedRobots = [...names];
    this._renderRobotOptions();
  }

  /** Liest die aktuell im Feld markierten Roboter-Tags (Issue #71). */
  private _readCompatibleRobots(): string[] {
    return Array.from(this.compatibleRobotsSelect.selectedOptions, (o) => o.value);
  }

  private _readCog(): [number, number, number] | null {
    const x = parseFloat(this.cogX.value);
    const y = parseFloat(this.cogY.value);
    const z = parseFloat(this.cogZ.value);
    if ([x, y, z].every((v) => Number.isFinite(v))) return [x, y, z];
    return null;
  }

  private async _onSave(): Promise<void> {
    if (this._busy) return;
    const formInput = {
      name: this.nameInput.value,
      vendor: this.vendorInput.value,
      weightKg: parseFloat(this.weightInput.value),
      cogMm: this._readCog(),
      channels: this._readChannels(),
      compatibleRobots: this._readCompatibleRobots(),
      // Berechnete Frames (#52) — nicht aus der three.js-Objektlage zurückgelesen.
      tcpFrame: this.tcpFrame,
      meshTransform: this.meshObject ? this.mountFrame : IDENTITY_FRAME,
      meshFilename: this.meshFilename,
      // Mesh nur mitschicken, wenn im Editor neu hochgeladen (sonst bleibt das alte, US 15).
      meshBase64: this.meshBytes ? arrayBufferToBase64(this.meshBytes) : "",
    };

    let save: () => Promise<ToolDef>;
    try {
      if (this._editMode && this._editingName) {
        const req: UpdateToolPayload = buildUpdateToolRequest(formInput);
        const name = this._editingName;
        save = () => this.callbacks.onUpdateTool(name, req);
      } else {
        const req: CreateToolPayload = buildCreateToolRequest(formInput);
        save = () => this.callbacks.onCreateTool(req);
      }
    } catch (err) {
      this.statusEl.textContent = `${err instanceof Error ? err.message : err}`;
      return;
    }

    const savingEdit = this._editMode;
    this._busy = true;
    this._syncButtons();
    this.saveBtn.textContent = "Speichert …";
    this.statusEl.textContent = savingEdit
      ? "Änderungen werden gespeichert …"
      : "Endeffektor wird abgelegt …";
    try {
      const tool = await save();
      this.statusEl.textContent = savingEdit
        ? `Endeffektor „${tool.name}" aktualisiert.`
        : `Endeffektor „${tool.name}" gespeichert — im Reiter Roboter wählbar.`;
      this.callbacks.onSaved?.(tool); // zurück zur Galerie (US 16)
    } catch (err) {
      this.statusEl.textContent = `Speichern fehlgeschlagen: ${err}`;
    } finally {
      this._busy = false;
      this.saveBtn.textContent = savingEdit ? "Änderungen speichern" : "Endeffektor speichern";
      this._syncButtons();
    }
  }

  private _updateTcpReadout(): void {
    const p = this.tcpFrame.pos_mm;
    // Düsenachse = TCP-z-Achse (#58): sichtbar machen, damit die Orientierung
    // (nicht nur die Position) prüfbar ist.
    const z = quatRotate(this.tcpFrame.quat, [0, 0, 1]);
    this.tcpReadout.textContent =
      `TCP am Flansch: [${p[0].toFixed(1)}, ${p[1].toFixed(1)}, ${p[2].toFixed(1)}] mm · ` +
      `Düsenachse [${z[0].toFixed(2)}, ${z[1].toFixed(2)}, ${z[2].toFixed(2)}]`;
  }

  /**
   * Öffnet den Konfigurator leer für einen neuen Endeffektor (Issue #56).
   * Setzt Formular + Szene zurück und entsperrt den Namen.
   */
  openCreate(): void {
    this._editMode = false;
    this._editingName = null;
    this._hasExistingMesh = false;
    this.heading.textContent = "Neuer Endeffektor";
    this.nameInput.readOnly = false;
    this.nameInput.value = "";
    this._resetForm();
    this.statusEl.textContent = "";
    this.saveBtn.textContent = "Endeffektor speichern";
    this._syncButtons();
  }

  /**
   * Öffnet den Konfigurator im Edit-Modus, vorbefüllt mit dem gewählten
   * Endeffektor (Issue #56). Stellt Mesh, `mesh_transform` und `tcp_frame` EXAKT
   * wieder her (keine Neu-Zentrierung, keine Neuberechnung), sperrt den Namen.
   * Ein neues Mesh ist optional; ohne Re-Upload bleibt das bestehende erhalten.
   */
  async openEdit(tool: ToolDef): Promise<void> {
    this._editMode = true;
    this._editingName = tool.name;
    this._hasExistingMesh = false;
    this.heading.textContent = `Endeffektor bearbeiten: ${tool.name}`;

    this._resetForm();

    // Stammdaten (US 12) — Name gesperrt (US 13).
    this.nameInput.value = tool.name;
    this.nameInput.readOnly = true;
    this.vendorInput.value = tool.vendor ?? "";
    this.weightInput.value = String(tool.weight_kg);
    if (tool.cog_mm) {
      this.cogX.value = String(tool.cog_mm[0]);
      this.cogY.value = String(tool.cog_mm[1]);
      this.cogZ.value = String(tool.cog_mm[2]);
    }
    // Kompatibilitäts-Tags vorbefüllen (Issue #71); Altbestand ohne Feld = leer.
    this._setSelectedRobots(tool.compatible_robots ?? []);

    // Logische Kanäle (US 11).
    this.channelList.replaceChildren();
    const entries = Object.entries(tool.channels);
    if (entries.length === 0) {
      this._addChannelRow("pump_a", "analog", "");
    } else {
      for (const [name, decl] of entries) {
        this._addChannelRow(name, decl.kind, decl.description ?? "");
      }
    }

    // Mesh (US 8): das gespeicherte Mesh laden — kein Re-Upload nötig.
    if (tool.mesh_path && tool.mesh) {
      this.statusEl.textContent = `Lade Mesh ${tool.mesh} …`;
      try {
        const obj = await loadToolMesh(toFsUrl(tool.mesh_path), tool.mesh);
        if (this.meshObject) this.arm.flange.remove(this.meshObject);
        this._clearHighlight();
        this.regionIndices.clear();
        this.meshObject = obj;
        applyFrameToObject(obj, IDENTITY_FRAME);
        this.arm.attachToFlange(obj);
        this._hasExistingMesh = true;
        // mesh_transform EXAKT wiederherstellen — NICHT neu zentrieren (US 9).
        const mt: Frame = tool.mesh_transform
          ? {
              pos_mm: tool.mesh_transform.pos_mm as Vec3,
              quat: tool.mesh_transform.quat as [number, number, number, number],
            }
          : IDENTITY_FRAME;
        this.mountBaseFrame = mt;
        this.mountOffset = [0, 0, 0];
        this.mountFrame = mt;
        applyFrameToObject(obj, mt);
        this.statusEl.textContent = "";
        this.mountStatus.textContent =
          "Gespeicherte Ausrichtung wiederhergestellt. Für Änderungen eine Fläche anklicken.";
      } catch (err) {
        this.statusEl.textContent = `Mesh konnte nicht geladen werden: ${err}`;
      }
    }

    // tcp_frame EXAKT wiederherstellen (inkl. quat, #58/US 10) — kein Recompute,
    // damit die gespeicherte Düsenrichtung nicht auf Identität zurückfällt.
    this.tcpFrame = {
      pos_mm: tool.tcp_frame.pos_mm as Vec3,
      quat: tool.tcp_frame.quat as [number, number, number, number],
    };
    this.tcpSource = "manual";
    this.pickedTcpCentroid = null;
    this.pickedTcpNormal = null;
    this._writeTcpInputs();
    applyFrameToObject(this.tcpMarker, this.tcpFrame);
    this._updateTcpReadout();

    this.saveBtn.textContent = "Änderungen speichern";
    this._syncButtons();
  }

  /** Setzt Szene + Formularfelder auf den Leerzustand (geteilt von openCreate/openEdit). */
  private _resetForm(): void {
    this._clearHighlight();
    this.regionIndices.clear();
    if (this.meshObject) {
      this.arm.flange.remove(this.meshObject);
      this.meshObject = null;
    }
    this.meshBytes = null;
    this.meshFilename = "";
    this.fileInput.value = "";
    this.pickedFace = null;
    this.pickedTcpCentroid = null;
    this.pickedTcpNormal = null;
    this._setTcpPickArmed(false);
    this.mountBaseFrame = IDENTITY_FRAME;
    this.mountFrame = IDENTITY_FRAME;
    this.mountOffset = [0, 0, 0];
    this.tcpFrame = { pos_mm: [0, 0, 150], quat: [1, 0, 0, 0] };
    this.tcpSource = "auto";
    this.vendorInput.value = "";
    this.weightInput.value = "";
    this.cogX.value = "";
    this.cogY.value = "";
    this.cogZ.value = "";
    this._setSelectedRobots([]);
    this.rotationInput.value = "0";
    this.mountOffX.value = "";
    this.mountOffY.value = "";
    this.mountOffZ.value = "";
    this.tcpX.value = "";
    this.tcpY.value = "";
    this.tcpZ.value = "";
    this.mountStatus.textContent =
      "Noch keine Fläche gewählt — Mesh laden und eine Fläche anklicken.";
    this.channelList.replaceChildren();
    this._addChannelRow("pump_a", "analog", "");
    applyFrameToObject(this.tcpMarker, this.tcpFrame);
    this._updateTcpReadout();
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this._syncButtons();
  }

  private _syncButtons(): void {
    // Speichern/TCP-Pick brauchen ein Mesh: entweder neu hochgeladen ODER (im
    // Edit-Modus) das bestehende, geladene Mesh (kein Re-Upload nötig, US 15).
    const hasMesh = !!this.meshBytes || this._hasExistingMesh;
    this.saveBtn.disabled = !this._apiAvailable || this._busy || !hasMesh;
    this.tcpPickBtn.disabled = this._busy || !hasMesh;
  }
}

/** ArrayBuffer → base64 (chunked, damit große Meshes den Call-Stack nicht sprengen). */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

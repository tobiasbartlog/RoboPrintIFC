/**
 * fgc-viewer — zustandsloser Abspieler der Core-Artefakte (ADR-007).
 * main.ts verdrahtet nur Module: artifacts (laden) -> render (drei.js) -> ui.
 *
 * Erweiterung Issue #9 (ADR-014): Parameter-Panel für Re-Slicing über die
 * lokale Core-API. Der Viewer rechnet weiterhin nichts — er schickt nur
 * Parameter an die API und lädt den erzeugten Laufordner als neue Artefakte.
 *
 * Erweiterung Issue #10: Klickbare Wand-Auswahl im Gesamtmodell.
 * Raycaster auf model.glb-Knoten → Eignungsbericht aus candidates.json →
 * „Diese Wand slicen" (postSlice mit model_path aus model_map.json + GlobalId).
 */

import * as THREE from "three";

import { isApiAvailable, postSlice } from "./api/client";
import { cancelBeamPropose, cancelDecompositionCheck, createProject, createTool, createWorkstation, deleteTool, deleteWorkstation, detectBaseHoles, exportSectionDrl, getBeamPropose, getCollisionAdvice, getDecompositionCheck, getSingularityAdvice, listProjects, listRobots, listTools, listWorkstations, loadProject, proposeDecomposition, startBeamPropose, startDecompositionCheck, setContextCheck, setModuleLimits, setObjective, setPlacementOverride, setPrintJob, setProcessParams, setRobot, setStandMode, setTool, setWorkstation, simulateSection, suggestPlacement, updateTool, updateWorkstation } from "./api/projects";
import type { BeamProposeStatus, Cut, DecompositionCheckStatus, DecompositionSection, FreigangFinding, Frame, PlacementOption, PlacementSuggestionResult, PrintJob, ProjectSummary, RobotDef, SectionOverride, ToolDef, WorkstationDef } from "./api/projects";
import { effectivePlacement } from "./ui/effective-placement";
import { loadFromFileList, loadFromUrl } from "./artifacts/load";
import type {
  Candidates,
  CollisionMeta,
  RunData,
  Target,
  Toolpath,
  Trajectory,
  TrajectoryWarning,
} from "./artifacts/types";
import {
  ArmView,
  getArmManifest,
  initArmMeshes,
  onArmRenderStateChange,
  setArmRenderMode,
} from "./render/arm";
import { attributionText, effectiveMode, toggleEnabled } from "./render/armmesh-state";
import {
  baseMarkerPosition,
  buildBaseMarker,
  buildReplayPedestal,
  placeBaseMarkerInBox,
  type BoxMinMax,
  type PlacementPose,
} from "./render/basemarker";
import {
  axisDragPlane,
  buildCutPlanes,
  projectOntoAxis,
  setCutPlaneHighlighted,
  type CutPlanesView,
} from "./render/cutplanes";
import {
  applySectionFocus,
  buildSectionBoxes,
  type SectionBoxesView,
} from "./render/sections";
import { wallFrameFromObject, type WallFrame } from "./render/wall-frame";
import {
  applyPlacementFocus,
  buildPlacementMarkers,
  sectionBaseFrame,
  type PlacementMarkersView,
} from "./render/placement-markers";
import { PreparePreview } from "./render/prepare-preview";
import {
  druckortSceneSpec,
  druckortSceneSpecForRun,
  type DruckortRunLike,
  type DruckortSceneSpec,
} from "./render/druckort-spec";
import { adoptJobResponse, findJob, type JobAdoptPorts } from "./ui/job-adopt";
import { applyPlacementOverride, type PlacementApplyPorts } from "./ui/placement-apply";
import {
  druckortAvailable,
  initDruckortState,
  isDruckort,
  reconcileDruckortView,
  resolveReplayReturnCamera,
  selectDruckortView,
  type DruckortState,
  type DruckortView,
} from "./ui/druckort-state";
import { buildContextObject } from "./render/context";
import { loadModelObject, type ModelView } from "./render/model";
import { TcpMarkerView } from "./render/tcpmarker";
import { BuildSeq } from "./render/buildseq";
import { ToolpathView } from "./render/toolpath";
import { buildWallObject } from "./render/wall";
import { identity } from "./kinematics/fk";
import { M1013_DH, M1013_HOME_RAD } from "./kinematics/robot";
import { createViewport } from "./scene/setup";
import { sceneModeForTab } from "./ui/scene-mode";
import { ViewerSettings } from "./ui/viewer-settings";
import {
  isFocusTab,
  viewerSettingsSections,
  wallFocusVisibility,
} from "./ui/viewer-settings-state";
import type { TabId } from "./ui/tabs";
import { computeArmPose, interpJoints } from "./trajectory/armreplay";
import { replayPedestal, sectionLiftMm } from "./trajectory/replay-anchor";
import { formatTime, interpolateSample } from "./trajectory/interpolate";
import { TrajectoryPlayer, type PlayerState, type RateSpan } from "./trajectory/player";
import {
  buildSequencePlan,
  locateSequenceTime,
  sequenceRateAt,
  targetIndexAtProgress,
  type SequencePlan,
} from "./trajectory/sequence";
import { moduleReplayFrame, projectModuleMarkers } from "./trajectory/modulereplay";
import { DruckplanPanel } from "./ui/druckplan";
import { ObjectivePanel } from "./ui/objective";
import { FocusStore, registerFocusEffects, type FocusEffects } from "./ui/focus-store";
import {
  clearedCollisionFindings,
  distanceReadout,
  linkHighlightAt,
  replayStatusLine,
  sampleIndexAtTime,
  statusAtIndex,
  timelineMarkers,
} from "./ui/collision-state";
import { DruckstandView } from "./render/druckstand";
import {
  placementOverrideSectionIds,
  slicingOverrideSectionIds,
} from "./ui/parts-palette-state";
import { simPlaysAtDruckort } from "./ui/sim-actions";
import { PlacementOverridePanel } from "./ui/placement-override";
import { ProcessParamsPanel } from "./ui/process-params";
import { ScopeSwitch } from "./ui/scope-switch";
import { globalParamsFrom, resolveSectionParams } from "./ui/section-params-state";
import { degToRad } from "./ui/nozzle-quat";
import { SingularityAdvisorPanel } from "./ui/singularity-advisor";
import { CollisionAdvisorPanel } from "./ui/collision-advisor";
import { ExportPanel } from "./ui/export";
import { Panel } from "./ui/panel";
import { RobotPanel } from "./ui/robot";
import { CommandPalette } from "./ui/palette";
import { Shell } from "./ui/shell";
import { wallBalanceFromCandidates } from "./ui/wall-balance";
import { SimulationPanel, type SequenceItem } from "./ui/simulation";
import { ToolConfigurator } from "./ui/configurator";
import { ToolLibrary } from "./ui/tool-library";
import { WorkstationLibrary } from "./ui/workstation-library";
import { WorkstationScene } from "./ui/workstation-scene";
import { RobotLibrary } from "./ui/robot-library";
import { LibraryRubrics } from "./ui/library-rubrics";
import { ThumbnailCache, renderMeshThumbnail } from "./ui/tool-thumbnail";
import { ToolPanel } from "./ui/tool";
import { WorkstationPanel } from "./ui/workstation";
import { loadToolMesh } from "./render/toolmesh";
import {
  THEME_STORAGE_KEY,
  type ThemeState,
  setTheme,
  themeFromStorage,
  themeView,
  toggleTheme,
} from "./ui/theme";

// --- Hell/Dunkel-Theme (UI-Redesign Scheibe 1, Issue #101) -------------------
// Die reine Umschalt-/Persistenz-Logik lebt in ui/theme.ts; hier nur die
// Verdrahtung: den in localStorage gemerkten Wert beim Start auf das <html>
// anwenden (überlebt Reload) und einen programmatischen Umschalter bereitstellen.
// Der sichtbare ◐-Umschalter im Header folgt in Scheibe 2 (Issue #102) und ruft
// dann `fgcToggleTheme()`. Sichtbarkeit/Look laufen ausschließlich über das
// `data-theme`-Attribut — kein display-Toggle (Issue #46/#101).
let themeStateCurrent: ThemeState = themeFromStorage(
  (() => {
    try {
      return localStorage.getItem(THEME_STORAGE_KEY);
    } catch {
      return null; // localStorage kann (private mode) werfen — dann Default (dunkel).
    }
  })(),
);

// Die Studio-Bühne (Scheibe 9, #113) hört auf dieselbe Theme-Umschaltung wie die
// CSS-Token: `applyTheme` setzt `data-theme` am <html> und färbt danach die 3D-
// Bühne (Hintergrund-Verlauf/Fog/Gitter) neu. Beim Start ist das Viewport noch
// nicht erzeugt (createViewport färbt sich dann selbst); der Hook wird nach der
// Viewport-Erzeugung registriert.
let restyleScene: (() => void) | null = null;

function applyTheme(state: ThemeState): void {
  const view = themeView(state);
  document.documentElement.setAttribute("data-theme", view.themeAttr);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, view.storageValue);
  } catch {
    /* Persistenz best effort — ohne localStorage bleibt die Wahl nur zur Laufzeit. */
  }
  restyleScene?.();
}

/** Spiegelt den Theme-Zustand auf den ◐-Toggle im Header (Issue #102), sobald die Shell existiert. */
function syncThemeToggle(): void {
  const view = themeView(themeStateCurrent);
  shell.setThemeToggle(view.isLight, view.toggleTitle);
}

/** Kippt hell↔dunkel, wendet an und persistiert (vom ◐-Umschalter genutzt). */
function fgcToggleTheme(): void {
  themeStateCurrent = toggleTheme(themeStateCurrent);
  applyTheme(themeStateCurrent);
  syncThemeToggle();
}

/** Setzt das Theme explizit (⌘K-Palette/Deeplink später). */
function fgcSetTheme(theme: "dark" | "light"): void {
  themeStateCurrent = setTheme(theme);
  applyTheme(themeStateCurrent);
  syncThemeToggle();
}

applyTheme(themeStateCurrent);
// Bis der Header-Umschalter existiert (Scheibe 2) über das window erreichbar,
// damit die Umschaltung schon jetzt funktioniert und prüfbar ist.
(window as unknown as Record<string, unknown>).fgcToggleTheme = fgcToggleTheme;
(window as unknown as Record<string, unknown>).fgcSetTheme = fgcSetTheme;

const viewport = createViewport(document.getElementById("viewport")!);
// Ab jetzt kippt der ◐-Umschalter auch die 3D-Bühne (Scheibe 9, #113): das
// Viewport liest seine Farben aus denselben CSS-Token wie das restliche UI.
restyleScene = () => viewport.restyle();
viewport.restyle();

// --- Projizierte Overlay-Chips (Scheibe 9, #113): Maß-Labels an den Schnitt-
// ebenen („z 1200 ⇅") und Basis-Chips an den Platzierungs-Markern („Basis ·
// Podest <h>"). Reine Darstellung (ADR-007): HTML-Chips über dem Canvas, je
// Frame an den projizierten Weltpunkt nachgeführt; die Drag-/Picking-Logik der
// Ebenen bleibt unberührt (das Overlay ist durchklickbar, pointer-events:none).
interface OverlayChip {
  el: HTMLElement;
  point: THREE.Vector3;
  visible: () => boolean;
}
let overlayChips: OverlayChip[] = [];

viewport.onFrame(() => {
  for (const c of overlayChips) {
    if (!c.visible()) {
      c.el.style.display = "none";
      continue;
    }
    const p = viewport.project(c.point);
    if (!p.visible) {
      c.el.style.display = "none";
      continue;
    }
    c.el.style.display = "";
    c.el.style.left = `${p.x}px`;
    c.el.style.top = `${p.y}px`;
  }
});

function clearOverlayChips(pred: (c: OverlayChip) => boolean): void {
  const keep: OverlayChip[] = [];
  for (const c of overlayChips) {
    if (pred(c)) c.el.remove();
    else keep.push(c);
  }
  overlayChips = keep;
}

function addOverlayChip(
  text: string,
  cls: string,
  point: THREE.Vector3,
  visible: () => boolean,
): void {
  const el = document.createElement("div");
  el.className = cls;
  el.textContent = text;
  viewport.overlay.appendChild(el);
  overlayChips.push({ el, point, visible });
}

/** Baut die Maß-Labels an den Schnittebenen neu (nach jedem `updateCutPlanes`). */
function rebuildCutMeasureLabels(): void {
  clearOverlayChips((c) => c.el.classList.contains("measure-label"));
  if (!cutPlanes) return;
  for (const h of cutPlanes.handles) {
    const cut = currentCuts[h.cutIndex];
    if (!cut) continue;
    const axis = h.orientation === "horizontal" ? "z" : "x";
    const text = `${axis} ${Math.round(cut.position_mm)} ⇅`;
    addOverlayChip(
      text,
      "measure-label",
      h.origin.clone(),
      () =>
        showBemassung &&
        viewport.world.visible &&
        !robotPreview.visible &&
        (cutPlanes?.group.visible ?? false),
    );
  }
}

/** Baut die Basis-Chips an den Platzierungs-Markern neu (nach `updatePlacementScene`). */
function rebuildBasisChips(): void {
  clearOverlayChips((c) => c.el.classList.contains("basis-chip"));
  if (!placementMarkers) return;
  placementMarkers.group.updateWorldMatrix(true, true);
  for (const section of druckplanPanel.getSections()) {
    const marker = placementMarkers.markers.get(section.section_id);
    if (!marker) continue;
    // Effektive Aufstellhöhe aus dem EINEN Selektor (Issue #171): der Chip nennt
    // das Podest, mit dem gerechnet wird, nicht die ggf. veraltete Zerlegungs-Lage.
    const h = Math.round(
      effectivePlacement(section.placement, sectionOverrideFor(section.section_id)).stand_height_mm,
    );
    const text = h > 0 ? `Basis · Podest ${h}` : "Basis";
    const point = marker.getWorldPosition(new THREE.Vector3());
    addOverlayChip(
      text,
      "basis-chip",
      point,
      () =>
        showBasis &&
        viewport.world.visible &&
        !replayActive &&
        !robotPreview.visible &&
        marker.visible,
    );
  }
}

// --- Roboter-Vorschau (Issue #31) im geteilten Hauptsichtfeld (Issue #30) ---
// Kapsel-Arm in Home-Pose mit Flansch-Achsen; der gewählte Endeffektor hängt
// als Mesh am Flansch. Eigene z-hoch-Gruppe neben `world`; sichtbar nur im
// Reiter Roboter (sceneModeForTab). Reine Darstellung (ADR-007).
const robotPreview = new THREE.Group();
robotPreview.name = "robot-vorschau";
robotPreview.rotation.x = -Math.PI / 2; // Daten: z hoch -> three.js: y hoch
robotPreview.visible = false;
viewport.scene.add(robotPreview);
const previewArm = new ArmView(M1013_DH);
previewArm.setPose(M1013_HOME_RAD, identity());
previewArm.attachToFlange(new THREE.AxesHelper(250));
robotPreview.add(previewArm.group);
let previewToolName: string | null = null;
let previewToolMesh: THREE.Object3D | null = null;
// Dropdown-Auswahl im Reiter Roboter (noch nicht gespeichert) — die Vorschau
// zeigt sie live; null = dem persistierten Druckjob-Tool folgen (Issue #31/#49).
let previewSelectedTool: string | null = null;
// Lade-Sequenz gegen A→B→A-Race: nur die jüngste Anforderung darf anhängen (Issue #49).
let previewLoadSeq = 0;

/** Hängt das Mesh des in der Vorschau gezeigten Endeffektors an den Flansch (Issue #31). */
function updateRobotPreviewTool(): void {
  const name = previewSelectedTool ?? currentTool;
  const tool = name ? loadedTools.find((t) => t.name === name) : undefined;
  const wanted = tool?.mesh_path && tool.mesh ? tool.name : null;
  if (wanted === previewToolName) return;
  const seq = ++previewLoadSeq;
  if (previewToolMesh) {
    previewArm.flange.remove(previewToolMesh);
    previewToolMesh = null;
  }
  previewToolName = wanted;
  if (!tool || !tool.mesh_path || !tool.mesh) return;
  const xf = tool.mesh_transform;
  loadToolMesh(fsUrl(tool.mesh_path), tool.mesh)
    .then((obj) => {
      if (seq !== previewLoadSeq) return; // inzwischen neuere Anforderung — verwerfen
      if (xf) {
        obj.position.set(xf.pos_mm[0], xf.pos_mm[1], xf.pos_mm[2]);
        obj.quaternion.set(xf.quat[1], xf.quat[2], xf.quat[3], xf.quat[0]); // [w,x,y,z] → three
      }
      previewToolMesh = obj;
      previewArm.attachToFlange(obj);
    })
    .catch(() => {
      /* Mesh optional — die Vorschau bleibt der Kapsel-Arm (kein Fehler). */
    });
}

// Kamerastand der Modellübersicht beim Wechsel in die Roboter-Vorschau merken —
// zurück im Prozess-Reiter sieht der Nutzer wieder seinen alten Blickwinkel.
let worldCamera: {
  pos: THREE.Vector3;
  target: THREE.Vector3;
  near: number;
  far: number;
} | null = null;

/**
 * Kamerafit auf die Welt — läuft die Roboter-Vorschau (Reiter Roboter), wird
 * der Fit nur als Restore-Ziel in `worldCamera` abgelegt und die Vorschau-Kamera
 * unangetastet gelassen (Issue #43: „Neu bewerten" riss die Kamera sonst auf
 * das unsichtbare Modell, und der Reiterwechsel restaurierte den veralteten Stand).
 */
function fitWorld(target: THREE.Object3D): void {
  if (!robotPreview.visible) {
    viewport.fitTo(target);
    return;
  }
  const keep = {
    pos: viewport.camera.position.clone(),
    target: viewport.controls.target.clone(),
    near: viewport.camera.near,
    far: viewport.camera.far,
  };
  viewport.fitTo(target);
  worldCamera = {
    pos: viewport.camera.position.clone(),
    target: viewport.controls.target.clone(),
    near: viewport.camera.near,
    far: viewport.camera.far,
  };
  viewport.camera.position.copy(keep.pos);
  viewport.controls.target.copy(keep.target);
  viewport.camera.near = keep.near;
  viewport.camera.far = keep.far;
  viewport.camera.updateProjectionMatrix();
}

/** Schaltet das geteilte Hauptsichtfeld je Reiter um (Issue #30/#31). */
function applySceneMode(tab: TabId): void {
  const preview = sceneModeForTab(tab) === "robot-vorschau";
  if (preview && !robotPreview.visible) {
    worldCamera = {
      pos: viewport.camera.position.clone(),
      target: viewport.controls.target.clone(),
      near: viewport.camera.near,
      far: viewport.camera.far,
    };
    robotPreview.visible = true;
    viewport.world.visible = false;
    // Live-Vorschau in der Roboter-Vorschau pausieren (rAF-Takt aus, #85).
    preparePreview.setVisible(false);
    updateRobotPreviewTool();
    viewport.fitTo(robotPreview);
  } else if (!preview && robotPreview.visible) {
    robotPreview.visible = false;
    viewport.world.visible = true;
    // Zurück im geteilten Feld: Live-Vorschau am Fokus wieder aufsetzen (#85).
    updatePreparePreview();
    if (worldCamera) {
      viewport.camera.position.copy(worldCamera.pos);
      viewport.controls.target.copy(worldCamera.target);
      viewport.camera.near = worldCamera.near;
      viewport.camera.far = worldCamera.far;
      viewport.camera.updateProjectionMatrix();
    }
  }
}

// Viewer-Einstellungen am 3D-Feld (Wand-Fokus ab Zerlegung): das schwebende
// ⚙-Menü hält den Kontext-Schalter + „Auf Wand einpassen". Seine Wirkung
// (Isolieren/Kamera) fährt applyWallFocus/fitToWall über die bestehenden
// Objekte — kein zweiter Zustand (ADR-016).
// Sicht-Schalter des ⚙-Menüs: Basis-Marker + Bemaßung standardmäßig an, der
// Gebäudekontext aus (Fokus = nur die gewählte Wand). Die Sichtbarkeits-Bools
// werden je Frame von den Overlay-Chip-Prädikaten gelesen (updateOverlayChips);
// die 3D-Basis-Marker schaltet applyOverlayToggles.
let showBasis = true;
let showBemassung = true;
// Kollisionskontrolle S3 (#128): zwei ⚙-Sicht-Schalter. Druckstand (wachsender
// Bauteil-Quader statt Voll-Box) standardmäßig AUS — Aus lässt das Replay
// unverändert; die Live-Abstandszahl standardmäßig AN (nur sichtbar, wenn der
// Lauf einen Befund trägt). Beides reine Sicht (ADR-007).
let showDruckstand = false;
let showAbstandszahl = true;
// Abspielgeschwindigkeit als Vielfaches der Echtzeit (Issue #155): eine Sitzungs-
// Eigenschaft des Schauens — sie überlebt Lauf-/Modul-/Bühnenwechsel und startet bei
// 1× („so schnell fährt die Maschine wirklich"). Jeder neue TrajectoryPlayer liest sie
// live über seine rateAt-Closure (sofortige Wirkung); die Umbaupausen skalieren NICHT
// mit (Erzählzeit, #27) — dafür sorgt `sequenceRateAt` (1× in der Pause).
let replaySpeed = 1;

/** rateAt für einen Sequenz-/Modul-Replay: Faktor in Druckphasen, 1× in Umbaupausen. */
function sequencePlaybackRate(plan: SequencePlan): (t: number) => RateSpan {
  return (t) => sequenceRateAt(plan, t, replaySpeed);
}

/** rateAt für einen Einzel-Lauf (keine Umbaupause): konstant der Sitzungs-Faktor. */
function constantPlaybackRate(): RateSpan {
  return { rate: replaySpeed, until_s: Number.POSITIVE_INFINITY };
}

/** Summe der Umbaupausen eines Plans (ungeteilt in die Restdauer, #155). */
function umbauTotalOf(plan: SequencePlan): number {
  return plan.umbau_s * Math.max(0, plan.segments.length - 1);
}

const viewerSettings = new ViewerSettings(
  {
    onToggle(key, visible) {
      if (key === "context") {
        applyWallFocus(false);
      } else if (key === "basis") {
        showBasis = visible;
        applyOverlayToggles();
      } else if (key === "bemassung") {
        showBemassung = visible;
      } else if (key === "druckstand") {
        showDruckstand = visible;
        if (druckstand) druckstand.visible = visible; // Wand-Bühne
        // Druckort-Bühne (#152): der Druckstand des laufenden Moduls folgt
        // demselben Schalter, ohne das Wand-Verhalten zu berühren.
        if (moduleReplay?.druckstand) moduleReplay.druckstand.visible = visible;
        applyCollisionAtTime(currentTrajTime);
      } else if (key === "abstandszahl") {
        showAbstandszahl = visible;
        applyCollisionAtTime(currentTrajTime); // Wand-Replay
        reapplyModuleCollisionFrame(); // Druckort-Replay (#153)
      } else if (key === "show-arm") {
        // Kapsel-Arm des Einzel-/Sequenz-Replays (Issue #18, aus #159 hierher).
        if (armView) armView.visible = visible;
      } else if (key === "grow-strand") {
        // Wachsender Strang: Zeit- statt Layer-Aufdeckung (Issue #27, aus #159).
        applyStrandReveal();
      } else if (key === "target-numbers") {
        // Punktnummerierung der Bahn-/Anfahrpunkte (Issue #138): EIN Schalter für
        // alle gerade lebenden ToolpathView-Instanzen (Einzel-Lauf, aktives
        // Modul, Abschnitts-Sequenz) — dieselbe Bühne, egal welcher Modus läuft.
        toolpathView?.setLabelsVisible(visible);
        moduleReplay?.toolpath?.setLabelsVisible(visible);
        for (const s of sequence?.loaded ?? []) s.view.setLabelsVisible(visible);
      }
    },
    onFitWall() {
      fitToWall();
    },
  },
  [
    {
      // „Modellansicht" (Issue #159): an den Wand-Fokus gebunden (isFocusTab).
      key: "model-view",
      title: "Modellansicht",
      fitWall: true,
      toggles: [
        {
          key: "context",
          label: "Gebäude/Kontext einblenden",
          hint:
            "Zeigt das restliche Gebäude (übrige Wände + Gebäudekontext) blass um " +
            "die gewählte Wand. Aus = nur die gewählte Wand.",
          checked: false,
        },
        { key: "basis", label: "Basis-Marker anzeigen", checked: true },
        { key: "bemassung", label: "Bemaßung (Maße an Schnitten)", checked: true },
      ],
    },
    {
      // „Replay-Bühne" (Issue #159): sichtbar, wo eine Bühne läuft — in den
      // Fokus-Reitern und im Reiter Projekt mit offenem Lauf. Die vier Schalter
      // steuern dieselbe Bühne, egal aus welchem Reiter.
      key: "replay-stage",
      title: "Replay-Bühne",
      toggles: [
        { key: "show-arm", label: "Roboterarm (Schema)", checked: true },
        {
          key: "grow-strand",
          label: "Strang wächst mit (Zeit)",
          hint:
            "Der gedruckte Strang wächst zeitgetreu mit dem Replay; Travel erzeugt " +
            "keinen Strang. Aus = ganzer Toolpath (Layer-Slider).",
          checked: true,
        },
        {
          key: "druckstand",
          label: "Wachsender Druckstand",
          hint:
            "Zeigt beim Replay den Bauteil-Quader, der mit dem Druckfortschritt in " +
            "der Höhe wächst (statt Voll-Box). Aus = Replay wie bisher.",
          checked: false,
        },
        {
          key: "abstandszahl",
          label: "Live-Abstandszahl (Kollision)",
          hint:
            "Zeigt im Player den minimalen Abstand (mm) am aktuellen Sample, sofern " +
            "der Lauf einen Kollisions-Befund trägt.",
          checked: true,
        },
        {
          key: "target-numbers",
          label: "Punktnummern (Bahn-/Anfahrpunkte)",
          hint:
            "Nummeriert print/travel-Wechsel und Ring-/Schichtanfänge am Toolpath " +
            "(max. 150 Labels gleichzeitig, sonst gleichmäßig ausgedünnt). Folgt " +
            "Layer-Slider, Wachs-Modus und Travel-Schalter wie die Bahnlinien.",
          checked: false,
        },
      ],
    },
  ],
);

/**
 * Ob am geteilten 3D-Feld eine Replay-Bühne offen ist (Issue #159): ein Lauf mit
 * Toolpath ist geladen (Arm/TCP/Strang/Druckstand hängen dann am `toolpathView`).
 * Einziger impurer Zuträger für die reine `viewerSettingsSections`-Regel — hier
 * lebt die Antwort auf „läuft hier ein Replay", nicht in `isFocusTab`.
 */
function replayStageOpen(): boolean {
  return toolpathView !== null;
}

/**
 * Zieht die Sichtbarkeit der zwei ⚙-Sektionen nach (Issue #159): „Modellansicht"
 * folgt dem Wand-Fokus, „Replay-Bühne" zeigt sich, wo eine Bühne läuft (auch im
 * Reiter Projekt mit offenem Lauf). Das Menü selbst folgt: sichtbar ⇔ mindestens
 * eine Sektion sichtbar. Aufzurufen bei Reiterwechsel und bei Lauf-Wechsel.
 */
function refreshViewerSettingsSections(): void {
  const vis = viewerSettingsSections(shell.activeTab, replayStageOpen());
  viewerSettings.setSectionVisible("model-view", vis.modelView);
  viewerSettings.setSectionVisible("replay-stage", vis.replayStage);
}

/** Wendet die Overlay-Sicht-Schalter auf die 3D-Objekte an (Basis-Marker-Gruppe). */
function applyOverlayToggles(): void {
  if (placementMarkers) placementMarkers.group.visible = showBasis;
}

/** Fasst die Kamera auf die gewählte Wand ein (Fallback: bisherige Rangfolge). */
function fitToWall(): void {
  const wallObj =
    currentWallGlobalId && modelObject
      ? modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`)
      : null;
  fitWorld(wallObj ?? toolpathView?.group ?? wallObject ?? modelObject?.group ?? viewport.world);
}

/**
 * Wand-Fokus ab Zerlegung: isoliert in den Fokus-Reitern die gewählte Wand im
 * geteilten 3D-Feld (übrige Wände + Gebäudekontext-Geist treten zurück) und
 * fasst die Kamera auf Wunsch neu ein. Ohne Fokus-Reiter oder ohne gewählte
 * Wand bleibt die Gesamtansicht; der Gebäudekontext folgt dann dem Projekt-
 * Panel. In der Druckort-Ansicht (#96) ruht das Kamera-Einfassen (dort besitzt
 * syncDruckort die Kamera).
 */
function applyWallFocus(refitCamera: boolean): void {
  const focus = isFocusTab(shell.activeTab);
  const vis = wallFocusVisibility(
    shell.activeTab,
    !!currentWallGlobalId,
    viewerSettings.get("context"),
  );
  if (modelObject) {
    modelObject.setWallFocus(vis.isolateWall ? currentWallGlobalId : null, vis.showOtherWalls);
  }
  if (contextObject) {
    contextObject.visible = focus ? vis.showContextGhost : panel.contextVisible;
  }
  if (refitCamera && focus && currentWallGlobalId && !isDruckort(druckortState)) {
    fitToWall();
  }
}

let toolpathView: ToolpathView | null = null;
// Replay auf echter Bandlage (Issue #135): Abschnitts-Läufe liegen abschnitts-
// lokal (z ab Abschnittsfuß); diese Hub-Gruppe hebt die komplette Replay-Szene
// (Teil-Mesh, Bahn, TCP, Arm, wachsender Druckstand, Podest-Sockel) um
// `meta.section_z0_mm` — der Boden (Gitter) bleibt bei 0, die Basis landet auf
// ihrer absoluten Aufstellhöhe. Altläufe ohne das Feld: Hub 0, bit-identisch.
let replayLift: THREE.Group | null = null;
let wallObject: ReturnType<typeof buildWallObject> | null = null;
let contextObject: ReturnType<typeof buildContextObject> | null = null;
let modelObject: ModelView | null = null;
let trajectoryPlayer: TrajectoryPlayer | null = null;
let tcpMarker: TcpMarkerView | null = null;
let armView: ArmView | null = null;

// Kollisionskontrolle S3 (#128): wachsender Druckstand + der Befund des aktuell
// abgespielten Laufs. `currentCollision` speist Glied-Einfärbung (US 8),
// Timeline-Marker (US 9) und Live-Abstandszahl (US 11); `collisionFindings`
// sammelt je Teil den Befund für die Palette-Badges (US 12). Alles verbatim aus
// `meta.collision` (ADR-007) — fehlt der Block, bleibt alles neutral (US 25).
let druckstand: DruckstandView | null = null;
let currentCollision: CollisionMeta | null = null;
let currentCollisionTimes: number[] = [];
const collisionFindings = new Map<string, CollisionMeta>();

/**
 * Übernimmt den Kollisions-Befund eines frisch geladenen Laufs (#128): setzt die
 * Player-Anzeigen (Badge + anklickbare Timeline-Marker) und — bei bekanntem Teil —
 * das Palette-Badge. Fehlt `meta.collision` (Altlauf), räumt es alles ab und die
 * ehrliche „keine Kollisionsprüfung"-Zeile bleibt (US 25). Verbatim (ADR-007).
 */
function setupCollisionForRun(traj: Trajectory, sectionId?: string | null): void {
  currentCollision = traj.meta.collision ?? null;
  currentCollisionTimes = traj.samples.map((s) => s.t_s);
  simulationPanel.setCollisionFinding(currentCollision, currentCollisionTimes, traj.meta.duration_s);
  if (sectionId) recordCollisionFinding(sectionId, currentCollision);
  applyCollisionAtTime(0);
}

/** Merkt den Befund eines Teils (oder löscht ihn) und aktualisiert die Palette-Badges. */
function recordCollisionFinding(sectionId: string, collision: CollisionMeta | null): void {
  if (collision) collisionFindings.set(sectionId, collision);
  else collisionFindings.delete(sectionId);
  druckplanPanel.setCollisionFindings(Object.fromEntries(collisionFindings));
}

/**
 * Wendet den Befund auf die aktuelle Replay-Zeit an (#128): Glied-Einfärbung (US 8)
 * + Live-Abstandszahl (US 11, ⚙-abschaltbar). Ohne Befund/ohne Schalter neutral —
 * das Replay bleibt dann unverändert. Reine Zeit-Abbildung (Darstellungsmathematik).
 */
function applyCollisionAtTime(time: number): void {
  if (!currentCollision) {
    armView?.setLinkHighlight(null);
    simulationPanel.setCollisionDistance(null);
    return;
  }
  const idx = sampleIndexAtTime(currentCollisionTimes, time);
  const hl = linkHighlightAt(currentCollision, idx);
  armView?.setLinkHighlight(hl ? hl.link : null, hl?.status ?? "red");
  simulationPanel.setCollisionDistance(
    showAbstandszahl ? distanceReadout(currentCollision, idx) : null,
    statusAtIndex(currentCollision, idx),
  );
}

/** Räumt den Kollisions-Replay-Zustand ab (kein Lauf aktiv / Übersicht). */
function clearCollisionReplay(): void {
  currentCollision = null;
  currentCollisionTimes = [];
  armView?.setLinkHighlight(null);
  simulationPanel.setCollisionDistance(null);
}

// Modell/Wand-Info des aktuell geladenen Laufs — für Re-Slicing (Issue #9).
// model_path: absoluter Pfad aus toolpath.params (0.3) oder context.model (Fallback).
let currentModelPath: string | null = null;
let currentGlobalId: string | null = null;

// Wand-Auswahl im Gesamtmodell (Issue #10).
// model_path kommt aus model_map.json (walls-list-Lauf), resolved auf absoluten Pfad.
let currentWallsListModelPath: string | null = null;
let currentCandidates: Candidates | null = null;

// Aktives Projekt (Issue #19): Slug + Pfad des Übersichts-Laufs für Druckjob-Übernahme.
// Gesetzt beim Öffnen/Anlegen eines Projekts; null beim ?run=-Direkteinstieg.
let currentProjectSlug: string | null = null;
let currentAssessmentRun: string | null = null;

// Aktiver Roboter (Issue #20): aus dem Druckjob-Feld „robot".
// null = noch nicht gesetzt (z. B. Direkteinstieg oder neues Projekt ohne Job).
let currentRobot: string | null = null;

// Aktiver Endeffektor (Issue #21): aus dem Druckjob-Feld „tool".
// null = noch nicht gesetzt.
let currentTool: string | null = null;

// Aktive Workstation (Issue #77): aus dem Druckjob-Feld „workstation".
// null = noch nicht gesetzt. Veraltet KEINE Outputs (Seam zu #70).
let currentWorkstation: string | null = null;

// Geladene Workstation-Definitionen (Issue #77) — für das Reiter-Roboter-Dropdown.
let loadedWorkstations: WorkstationDef[] = [];

// Geladene Roboter-Definitionen — für Payload-Lookup (Issue #21).
let loadedRobots: RobotDef[] = [];

// Geladene Endeffektor-Definitionen (Issue #21/#28) — für den Katalog (ToolPanel)
// und das Mesh am Flansch im Replay (mesh_path/mesh_transform des Druckjob-Tools).
let loadedTools: ToolDef[] = [];

// Platzierung (Issue #22): Wand + erfasste Aufstellmöglichkeiten des aktiven
// Druckjobs — Spiegel des project.json-Stands (Fachzustand liegt dort). Die
// Liste speist seit Issue #134 nur noch die Override-Referenz-Dropdowns der
// Teile-Palette (#94a, Altprojekte); Gesamtwand-Wahl + Basis-Marker (#22)
// sind entfallen.
let currentWallGlobalId: string | null = null;
let currentPlacements: PlacementOption[] = [];
// Aktiver Druckjob (Issue #65): für die Anwenden-Abbildung des Singularitäts-
// Advisors (bestehender Kipp/Lead, Slice-Block bewahren). Wird beim Öffnen und
// nach mutierenden Aktionen aktualisiert.
let currentActiveJob: PrintJob | undefined;

/** Aktiver Platzierungs-Override eines Teils (Issue #171): die eine Quelle, aus
 *  der alle Einbauort-Leser (Marker, Fokus-Arm, Basis-Chips, Vorbereiten-3D,
 *  Gesamtablauf-Marker) ihre Override-Werte über den Effektive-Platzierung-
 *  Selektor beziehen. `undefined` = kein Override, gilt die Zerlegungs-Lage. */
function sectionOverrideFor(sectionId: string | null | undefined): SectionOverride | undefined {
  if (!sectionId) return undefined;
  return currentActiveJob?.section_overrides?.find((o) => o.section_id === sectionId);
}

// Frische Sim-Lauf-Platzierung je Modul-Laufordner (Issue #171/#161, B19): der
// Frame-Face des Selektors braucht am Druckort die Lauf-`base_frame`; die
// statische Ansicht wird sonst aus der (ggf. veralteten) Zerlegungs-Lage gebaut
// und der Soll-Kasten springt beim Replay-Start um. Reiner Lese-Cache (ADR-007,
// kein Fachzustand), per Laufordner-Pfad; ein neuer Lauf hat einen neuen Pfad.
const moduleRunBaseFrameCache = new Map<string, Frame | null>();

/** Laufordner des Sim-Laufs des fokussierten Moduls (aus `section_runs`) oder null. */
function focusedModuleRunPath(): string | null {
  const id = focusStore.get();
  const run = currentActiveJob?.section_runs?.find((r) => r.section_id === id);
  return run?.run ?? null;
}

/** Als `DruckortRunLike` verpackte, gecachte Lauf-`base_frame` — oder null, wenn
 *  (noch) nicht geladen; dann baut der Aufrufer aus der Zerlegungs-Lage. */
function cachedModuleRun(runPath: string | null): DruckortRunLike | null {
  if (!runPath || !moduleRunBaseFrameCache.has(runPath)) return null;
  return { trajectory: { meta: { base_frame: moduleRunBaseFrameCache.get(runPath) ?? null } } };
}

/** Lädt die Lauf-`base_frame` eines Modul-Laufs einmalig in den Cache (Issue #171).
 *  Liefert `true`, wenn dadurch eine frische Lage bekannt wurde (⇒ Szene neu bauen). */
async function ensureModuleRunFrameCached(runPath: string | null): Promise<boolean> {
  if (!runPath || moduleRunBaseFrameCache.has(runPath)) return false;
  try {
    const run = await loadFromUrl(fsUrl(runPath));
    moduleRunBaseFrameCache.set(runPath, run.trajectory?.meta.base_frame ?? null);
    return true;
  } catch {
    moduleRunBaseFrameCache.set(runPath, null); // Lauf nicht ladbar → Zerlegungs-Lage
    return false;
  }
}

// Zerlegung (Issue #24): Schnittebenen des aktiven Druckjobs (Plan-Eingaben) +
// ihre 3D-Darstellung in der Modellübersicht.
let currentCuts: Cut[] = [];
let cutPlanes: CutPlanesView | null = null;
// Klickbare Abschnitts-Quader + weiche Kamera-Einfassung (Issue #84). Die
// Fokus-Auswahl selbst hält der Fokus-Store (unten); hier liegt
// nur die 3D-Darstellung (Pick-Ziele + Highlight).
let sectionBoxes: SectionBoxesView | null = null;

// Wand-/Teil-Fokus (Issue #84/#196): der EINE Halter „welches Teil ist
// fokussiert" (`ui/focus-store.ts`) — reiner Sicht-Zustand (ADR-007), kein
// Fachzustand. Geschrieben wird er nur über `druckplanPanel.focusSection`
// (3D-Klick/Teile-Palette → toggle) und die Zerlegungs-Abgleiche (reconcile);
// alle Wirkungen sind die unten registrierte Vertragsliste
// (`registerFocusEffects`, FOCUS_EFFECT_ORDER), alle Leser rufen `get()`.
const focusStore = new FocusStore();

// Platzierung sichtbar (Issue #93, PRD #88): Basis-Marker ALLER Teil-Platzierungen
// dauerhaft vor der Wand (Vorbereiten-Modus) + das echte M1013-Mesh (neutrale Pose)
// am fokussierten Teil. Reine Darstellung eines Plans (ADR-007): Pose aus
// Platzierung + Wandmaßen; die Bewertung liest die Palette nur. Der Fokus tauscht
// sauber Marker↔Mesh. Der Arm wird lazy erzeugt (teilt die geladenen GLBs, #41).
let placementMarkers: PlacementMarkersView | null = null;
let placementArm: ArmView | null = null;

// Live-Vorschau „Vorbereiten" (Issue #85, PRD B/#70): Düsen-Schablone +
// sofortige Bahnen + atmender Sicherheitsabstand für den Fokus-Abschnitt. Reine
// Darstellung/Animation (ADR-007), an die world-Gruppe gehängt — die reine
// Fach-Geometrie liegt in ui/nozzle-schablone|preview-slice|safety-clearance.
const preparePreview = new PreparePreview(viewport.world);

// Modus-Fusion „Vorbereiten↔Simulieren" (Issue #86, PRD B/#70): der aktuelle
// Modus des geteilten 3D-Felds. Vorbereiten = Live-Vorschau am Fokus (#85);
// Simulieren = voller Arm-Lauf über die bestehenden Simulier-Aktionen (ADR-007).
// Im Simulieren-Modus ruht die Live-Vorschau, damit nichts gegeneinander läuft.
// Läuft gerade ein Trajektorien-Replay im geteilten 3D-Feld? (Issue #108, ersetzt
// den Modus `planMode` der Fusion #86.) Während eines Replays ruhen die Live-
// Vorschau (#85) und die Platzierungs-Marker (#93); ohne Replay sind sie aktiv —
// Schnittplan-Bearbeitung und Simulation koexistieren ohne Modus.
let replayActive = false;

// --- Druckort-Ansicht (Druckplan-Neuordnung II S8, Issue #96, ADR-021/022) ---
// Ansichts-Umschalter Einbauort ↔ Druckort am fokussierten Modul: Druckort
// blendet die Szene auf die Workstation um — Mesh, M1013 an robot_base_frame,
// Modul-Rechteck an der vom CORE gerechneten Lage (`module_pose`, Invertierung
// der Relativpose-Leserichtung). Reine Darstellung (ADR-007): die Lage kommt
// als Artefakt, hier wird nur umgeblendet; die reine Umschalt-Logik lebt in
// `ui/druckort-state.ts`, die Szenen-Spec in `render/druckort-spec.ts`.
// Eigene z-hoch-Gruppe neben `world` (wie robotPreview) — Workstation-
// Koordinaten sind Mesh-lokal (mm, z hoch, ADR-006).
const druckortGroup = new THREE.Group();
druckortGroup.name = "druckort-szene";
druckortGroup.rotation.x = -Math.PI / 2; // Daten: z hoch -> three.js: y hoch
druckortGroup.visible = false;
viewport.scene.add(druckortGroup);
let druckortState: DruckortState = initDruckortState();
let druckortArm: ArmView | null = null;
let druckortModule: THREE.Group | null = null;
let druckortWsMesh: THREE.Object3D | null = null;
// Bau-Zähler gegen A→B→A-Races bei asynchron geladenen Bühnen-Meshes (Endeffektor
// am Flansch + Workstation-Mesh, #49/#151). EIN bump je Neubau/Teardown (in
// clearDruckortScene) — nicht je Mesh, sonst entwertet ein Mesh den Guard des
// anderen im selben Bau (der #151-Defekt). Reine Logik in render/buildseq.ts.
const druckortBuildSeq = new BuildSeq();
// Kamerastand der Wand-Ansicht — der Rückweg stellt ihn weich wieder her (#84).
let einbauortCamera: {
  pos: THREE.Vector3;
  target: THREE.Vector3;
  near: number;
  far: number;
} | null = null;

const druckortToggleEl = document.getElementById("druckort-toggle") as HTMLElement;
const druckortEinbauortRadio = document.getElementById(
  "druckort-view-einbauort",
) as HTMLInputElement;
const druckortDruckortRadio = document.getElementById(
  "druckort-view-druckort",
) as HTMLInputElement;
const druckortHintEl = document.getElementById("druckort-hint") as HTMLElement;

// „Plan — vor dem Druck antasten"-Chip (UI-Redesign Scheibe 3, #103): schwebt
// unten im Viewport, nur im Reiter Druckplan sichtbar (onTabChanged, nur `.hidden`).
const planChipEl = document.getElementById("plan-chip") as HTMLElement;

// Simulations-Dock (UI-Redesign Scheibe 6, #108): feste Leiste am Fuß des
// Viewports, nur im Reiter Slicing (druckplan) sichtbar (onTabChanged, nur `.hidden`).
const simDockEl = document.getElementById("sim-dock") as HTMLElement;

druckortEinbauortRadio.addEventListener("change", () => applyDruckortSelection("einbauort"));
druckortDruckortRadio.addEventListener("change", () => applyDruckortSelection("druckort"));

/** Gecachte Sim-Lauf-`base_frame` des fokussierten Moduls (Issue #171, B19) —
 *  der Frame-Face des Effektive-Platzierung-Selektors am Druckort. `null`, solange
 *  (noch) nicht geladen; dann baut die Szene aus der Zerlegungs-Lage. */
function focusedModuleRunFrame(): Frame | null {
  return cachedModuleRun(focusedModuleRunPath())?.trajectory?.meta.base_frame ?? null;
}

/** Lädt die frische Lauf-Lage des fokussierten Moduls nach und baut die Druckort-
 *  Szene neu, sobald sie da ist (Issue #171, B19): so zeigt die statische Ansicht
 *  dieselbe Lage wie der Player — der Soll-Kasten springt beim Replay-Start nicht. */
function scheduleDruckortRunFrame(): void {
  void ensureModuleRunFrameCached(focusedModuleRunPath()).then((fresh) => {
    if (fresh && isDruckort(druckortState) && !moduleReplay) refreshDruckortScene();
  });
}

/** Das fokussierte Teil (für die Druckort-Szene), oder `undefined`. */
function focusedDruckortSection(): DecompositionSection | undefined {
  const id = focusStore.get();
  return druckplanPanel.getSections().find((s) => s.section_id === id);
}

/** Nutzerwahl am Umschalter: Druckort nur am fokussierten Modul (`druckort-state`). */
function applyDruckortSelection(view: DruckortView): void {
  const next = selectDruckortView(
    druckortState,
    view,
    druckplanPanel.getKind(),
    focusStore.get(),
  );
  if (next.view === druckortState.view) {
    renderDruckortToggle();
    return;
  }
  if (next.view === "druckort") {
    enterDruckort();
  } else {
    druckortState = next;
    exitDruckortScene(true);
    renderDruckortToggle();
  }
}

/**
 * Wechselt in die Druckort-Ansicht (Issue #96): Szene auf die Workstation
 * umblenden — oder, wenn Voraussetzungen fehlen (keine Workstation, keine
 * Frames, kein `module_pose` im Lauf), den freundlichen Hinweis zeigen und in
 * der Wand-Ansicht bleiben (Befund, kein Gate — nie eine kaputte Szene).
 */
function enterDruckort(): void {
  const section = focusedDruckortSection();
  const ws = loadedWorkstations.find((w) => w.name === currentWorkstation) ?? null;
  const wall = placementWallDims();
  // Statische Ansicht aus dem Frame-Face des Selektors (Issue #171, B19): existiert
  // ein frischer Sim-Lauf, folgt der Soll-Kasten SEINER Lage — dieselbe Regel wie
  // der Player, kein Umspringen beim Replay-Start. Ist die Lauf-Lage noch nicht
  // geladen, baut die Szene aus der Zerlegungs-Lage und `scheduleDruckortRunFrame`
  // zieht sie nach.
  const result = druckortSceneSpec({
    workstation: ws,
    section,
    thicknessMm: wall?.thickness_mm ?? 0,
    runBaseFrame: focusedModuleRunFrame(),
  });
  if (!result.ok) {
    druckortState = { view: "einbauort" };
    renderDruckortToggle();
    setDruckortHint(result.hint);
    return;
  }
  setDruckortHint(null);
  druckortState = { view: "druckort" };
  // Kamerastand der Wand-Ansicht merken — der Rückweg stellt ihn wieder her.
  einbauortCamera = {
    pos: viewport.camera.position.clone(),
    target: viewport.controls.target.clone(),
    near: viewport.camera.near,
    far: viewport.camera.far,
  };
  buildDruckortScene(result.spec);
  viewport.world.visible = false;
  preparePreview.clear(); // Live-Vorschau (#85) ruht am Druckort
  druckortGroup.visible = true;
  frameDruckort();
  renderDruckortToggle();
  scheduleDruckortRunFrame(); // frische Lauf-Lage nachziehen (Issue #171, B19)
}

/** Baut die Druckort-Szene aus der reinen Spec: Roboter + Modul-Rechteck sofort,
 *  das Workstation-Mesh asynchron (optional — ohne Mesh reichen Roboter + Modul). */
function buildDruckortScene(spec: DruckortSceneSpec): void {
  clearDruckortScene();
  // M1013 (echtes Mesh, teilt die global geladenen GLBs, #41) an robot_base_frame.
  if (!druckortArm) {
    druckortArm = new ArmView(M1013_DH);
    druckortGroup.add(druckortArm.group);
  }
  druckortArm.setPose(M1013_HOME_RAD, spec.robotAnchor);
  druckortArm.visible = true;
  // Endeffektor-Mesh am Flansch (Issue #151, analog Wand-Arm main.ts:1637). Der
  // Druckort-Arm wird über Modulwechsel wiederverwendet, darum VOR dem Anhängen
  // den Flansch leeren (kein Doppel-Anhängen). Der Guard (Bau-Zähler, in
  // clearDruckortScene je Neubau erhöht) verwirft ein stale Async-Mesh — er teilt
  // sich den Zähler mit dem Workstation-Mesh und überlebt dessen Laden im selben Bau.
  druckortArm.clearFlange();
  attachToolMeshToArm(druckortArm, druckortBuildSeq.guard(druckortBuildSeq.current));
  // Soll-Umriss des Moduls an der Core-Lage (module_pose.workstation, verbatim):
  // nur noch die EdgesGeometry — Lage, Orientierung und Sollgröße auf der
  // Arbeitsfläche (#152, Entscheidung #147 „Soll als Linie, Ist als Volumen").
  // Die frühere halbtransparente Voll-Box entfällt; das Ist-Volumen zeigt beim
  // Replay der wachsende Druckstand (DruckstandView, je Modul in updateModuleReplay).
  const [lengthMm, thicknessMm, heightMm] = spec.moduleBox.sizeMm;
  const geometry = new THREE.BoxGeometry(
    Math.max(lengthMm, 1),
    Math.max(thicknessMm, 1),
    Math.max(heightMm, 1),
  );
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x9be2ff }),
  );
  geometry.dispose(); // nur als Kanten-Quelle gebraucht; EdgesGeometry hält eigene Puffer.
  const c = spec.moduleBox.centerLocalMm;
  edges.position.set(c[0], c[1], c[2]);
  const moduleGroup = new THREE.Group();
  moduleGroup.name = "druckort-modul";
  moduleGroup.add(edges);
  const p = spec.moduleFrame.pos_mm as number[];
  const q = spec.moduleFrame.quat as number[]; // [w,x,y,z] → three (x,y,z,w)
  moduleGroup.position.set(p[0], p[1], p[2]);
  moduleGroup.quaternion.set(q[1], q[2], q[3], q[0]);
  druckortGroup.add(moduleGroup);
  druckortModule = moduleGroup;
  // Workstation-Mesh (optional, ADR-021) asynchron — Bau-Guard gegen Races. NUR
  // den aktuellen Zähler erfassen, NICHT weiterzählen (sonst stirbt der Tool-Guard
  // desselben Baus, #151); der nächste clearDruckortScene() invalidiert ohnehin.
  if (spec.meshPath && spec.meshFile) {
    const wsValid = druckortBuildSeq.guard(druckortBuildSeq.current);
    const file = spec.meshFile;
    loadToolMesh(fsUrl(spec.meshPath), file)
      .then((obj) => {
        if (!wsValid() || !isDruckort(druckortState)) return;
        druckortWsMesh = obj;
        druckortGroup.add(obj);
        frameDruckort(); // Einfassung ans volle Bild anpassen (weich, #84)
      })
      .catch(() => {
        /* Mesh optional — Roboter + Modul reichen (kein Fehler). */
      });
  }
}

/** Räumt Modul-Rechteck + Workstation-Mesh (GPU-sauber); der Arm bleibt versteckt. */
function clearDruckortScene(): void {
  druckortBuildSeq.bump();
  if (druckortModule) {
    druckortGroup.remove(druckortModule);
    disposeSubtree(druckortModule);
    druckortModule = null;
  }
  if (druckortWsMesh) {
    druckortGroup.remove(druckortWsMesh);
    disposeSubtree(druckortWsMesh);
    druckortWsMesh = null;
  }
  if (druckortArm) druckortArm.visible = false;
}

/** Gibt Geometrien/Materialien eines Teilbaums frei (Muster workstation-scene). */
function disposeSubtree(root: THREE.Object3D): void {
  root.traverse((obj) => {
    const node = obj as Partial<THREE.Mesh>;
    node.geometry?.dispose();
    const material = node.material;
    if (Array.isArray(material)) for (const m of material) m.dispose();
    else material?.dispose();
  });
}

/** Verlässt die Druckort-Szene; `tweenBack` fährt weich zur Wand-Ansicht (#84). */
function exitDruckortScene(tweenBack: boolean): void {
  clearDruckortScene();
  druckortGroup.visible = false;
  viewport.world.visible = !robotPreview.visible;
  setDruckortHint(null);
  updatePreparePreview();
  if (tweenBack && einbauortCamera) {
    viewport.camera.near = einbauortCamera.near;
    viewport.camera.far = einbauortCamera.far;
    viewport.camera.updateProjectionMatrix();
    startCameraTween(einbauortCamera.pos.clone(), einbauortCamera.target.clone());
  }
  einbauortCamera = null;
}

/** Weiche Kamera-Einfassung der Druckort-Szene — dieselbe #84-Tween-Mechanik. */
function frameDruckort(): void {
  const box = new THREE.Box3().setFromObject(druckortGroup);
  if (box.isEmpty()) return;
  const target = box.getCenter(new THREE.Vector3());
  const diag = box.getSize(new THREE.Vector3()).length();
  const dir = new THREE.Vector3().subVectors(
    viewport.camera.position,
    viewport.controls.target,
  );
  if (dir.lengthSq() < 1e-6) dir.set(0.7, 0.5, 0.9);
  dir.normalize();
  // near/far großzügig auf die Szene stellen (fitTo-Muster), Fahrt per Tween.
  viewport.camera.near = Math.max(1, diag / 1000);
  viewport.camera.far = Math.max(10000, diag * 10);
  viewport.camera.updateProjectionMatrix();
  startCameraTween(
    target.clone().addScaledVector(dir, Math.max(diag, 1) * 0.9),
    target.clone(),
  );
}

/** Spiegelt Verfügbarkeit + Ansicht in den Umschalter (nur `.hidden`). */
function renderDruckortToggle(): void {
  const available =
    shell.activeTab === "druckplan" &&
    !replayActive &&
    !robotPreview.visible &&
    druckortAvailable(druckplanPanel.getKind(), focusStore.get());
  druckortToggleEl.hidden = !available;
  if (!available) setDruckortHint(null);
  druckortEinbauortRadio.checked = druckortState.view === "einbauort";
  druckortDruckortRadio.checked = druckortState.view === "druckort";
}

function setDruckortHint(text: string | null): void {
  druckortHintEl.hidden = text === null;
  druckortHintEl.textContent = text ?? "";
}

/**
 * Gleicht die Druckort-Ansicht mit ihren Voraussetzungen ab (Fokus, Art,
 * Modus, Reiter): fallen sie weg, kehrt die Szene sauber zur Wand-Ansicht
 * zurück; wandert der Fokus auf ein anderes Modul (oder liefert eine
 * Neubewertung frische Lagen), wird die Szene neu aufgebaut.
 */
function syncDruckort(): void {
  // Während eines Modul-Replays (Issue #97) gehört die Druckort-Bühne dem
  // Abspieler — der #96-Zustandsautomat lässt sie in Ruhe (kein Abräumen).
  if (moduleReplay) return;
  const focused = focusStore.get();
  let next = reconcileDruckortView(druckortState, druckplanPanel.getKind(), focused);
  if (
    next.view === "druckort" &&
    (shell.activeTab !== "druckplan" || replayActive || robotPreview.visible)
  ) {
    next = { view: "einbauort" };
  }
  if (next.view !== druckortState.view) {
    druckortState = next;
    exitDruckortScene(true);
  } else if (isDruckort(druckortState)) {
    refreshDruckortScene();
  }
  renderDruckortToggle();
}

/** Baut die aktive Druckort-Szene am aktuellen Fokus-Teil neu auf (frische Lage). */
function refreshDruckortScene(): void {
  const section = focusedDruckortSection();
  const ws = loadedWorkstations.find((w) => w.name === currentWorkstation) ?? null;
  const wall = placementWallDims();
  // Frame-Face des Selektors (Issue #171, B19): frischer Sim-Lauf gewinnt über die
  // Zerlegungs-Lage — statische Ansicht und Player teilen EINE Regel.
  const result = druckortSceneSpec({
    workstation: ws,
    section,
    thicknessMm: wall?.thickness_mm ?? 0,
    runBaseFrame: focusedModuleRunFrame(),
  });
  if (!result.ok) {
    druckortState = { view: "einbauort" };
    exitDruckortScene(true);
    setDruckortHint(result.hint);
    renderDruckortToggle();
    return;
  }
  buildDruckortScene(result.spec);
  frameDruckort();
  scheduleDruckortRunFrame(); // frische Lauf-Lage nachziehen, falls noch nicht im Cache
}

// --- Modul-Simulation am Druckort (Druckplan-Neuordnung II S9, Issue #97,
// PRD #88, ADR-022 §6) ---
// Reuse der Druckort-Szene (#96) als Bühne für den vollen Arm-Lauf: der M1013
// sitzt fest an der Workstation-Basis (robot_base_frame), das Modul steht auf der
// Arbeitsfläche an der S8-Modul-Pose. „Fokus-Modul simulieren" spielt einen Lauf,
// „Alle Module" alle in Montagereihenfolge (unten → oben, links → rechts) — über
// DIESELBE TrajectoryPlayer-Instanz (`trajectoryPlayer`); das Modul auf der Fläche
// wird je Schritt durchgetauscht. Reine Darstellungsmathematik (ADR-007): die
// Gelenke fahren die vom Core gerechnete Bahn, der Transform kommt aus der
// Modul-Pose (#96) — keine neue Kinematik. Eine Montage-Simulation am Einbauort
// ist ausdrücklich out of scope (PRD #88, ADR-022 §6).
interface ModuleReplayStep {
  section: DecompositionSection;
  spec: DruckortSceneSpec;
  samples: Trajectory["samples"];
  /** Toolpath-Targets des Moduls (abschnittslokale data-mm) für den TCP-Marker (#151). */
  targets: Target[];
  /** Voller Toolpath des Moduls für den wachsenden Strang (ToolpathView, #152); null = kein Strang. */
  toolpath: Toolpath | null;
  duration_s: number;
  /** Kollisions-Befund des Modul-Laufs (verbatim, #153); null = Altlauf ohne Befund. */
  collision: CollisionMeta | null;
  /** `t_s` je Sample des Modul-Laufs (parallel zu `meta.collision`), für die modul-lokale Zeit. */
  sampleTimes: number[];
}
interface ModuleReplayState {
  steps: ModuleReplayStep[];
  plan: SequencePlan;
  built: number; // Index des gerade auf der Arbeitsfläche stehenden Moduls (-1 = keiner)
  /** TCP-Marker des aktuell gebauten Moduls (unter dessen moduleGroup, #151). */
  tcp: TcpMarkerView | null;
  /** Wachsender Strang des aktuell gebauten Moduls (unter dessen moduleGroup, #152). */
  toolpath: ToolpathView | null;
  /** Wachsender Druckstand (Ist-Volumen) des aktuell gebauten Moduls (#152). */
  druckstand: DruckstandView | null;
}
let moduleReplay: ModuleReplayState | null = null;

/** Druckort-Szenen-Spec eines Moduls (wie `refreshDruckortScene`), oder null.
 *  Der **Lauf ist Pflicht-Argument** (Issue #161, Review-Nacharbeit): die reine,
 *  getestete `druckortSceneSpecForRun` zieht `trajectory.meta.base_frame` selbst
 *  aus dem Lauf — die Bühne folgt der Platzierung des Sim-Laufs, Arm und Bühne
 *  teilen EINE Quelle; ohne das Feld (Altlauf) gilt die Zerlegungs-Lage. */
function moduleSceneSpecFor(
  section: DecompositionSection,
  run: DruckortRunLike,
): DruckortSceneSpec | null {
  const ws = loadedWorkstations.find((w) => w.name === currentWorkstation) ?? null;
  const wall = placementWallDims();
  const result = druckortSceneSpecForRun({
    workstation: ws,
    section,
    thicknessMm: wall?.thickness_mm ?? 0,
    run,
  });
  return result.ok ? result.spec : null;
}

/** Beendet einen laufenden Modul-Replay: Player stoppen, Druckort-Bühne abräumen. */
function teardownModuleReplay(): void {
  if (!moduleReplay) return;
  moduleReplay = null;
  trajectoryPlayer?.destroy();
  trajectoryPlayer = null;
  // Kollisions-Einfärbung des wiederverwendeten Druckort-Arms zurücksetzen (#153),
  // damit ein gelb/rot gefärbtes Glied nicht in die nächste Bühne übertritt.
  druckortArm?.setLinkHighlight(null);
  simulationPanel.setCollisionDistance(null);
  exitDruckortScene(true); // zurück zur Wand-Ansicht (weich, #84)
  renderDruckortToggle();
}

/**
 * „Fokus-Modul simulieren"/„Im Player ansehen" bei Modulen: einen Modul-Lauf am
 * Druckort abspielen (der Lauf ist frisch → nie veraltet). Fehlt die Druckort-
 * Lage (Workstation/Frames/Modul-Pose), bleibt es bei einem Befund (kein Gate).
 */
async function playModuleRunAtDruckort(sectionId: string, runPath: string): Promise<void> {
  const section = druckplanPanel.getSections().find((s) => s.section_id === sectionId);
  if (!section) return;
  try {
    const run = await loadFromUrl(fsUrl(runPath));
    if (!run.trajectory) {
      simulationPanel.setStatus("Modul-Lauf ohne Trajektorie — erst neu simulieren.");
      return;
    }
    // Bühne folgt dem Sim-Lauf (Issue #161): die Platzierung DIESES Laufs
    // (meta.base_frame) treibt den moduleGroup-Transform — nicht die ggf.
    // veraltete Zerlegungs-Lage (z. B. nach angewandtem Placement-Hebel #130).
    const spec = moduleSceneSpecFor(section, run);
    if (!spec) {
      simulationPanel.setStatus(
        "Modul-Lage am Druckort fehlt — Workstation + Platzierungs-Frames prüfen (ADR-022).",
      );
      return;
    }
    const modCollision = run.trajectory.meta.collision ?? null;
    startModuleReplay(
      [{
        section,
        spec,
        samples: run.trajectory.samples,
        targets: run.toolpath?.targets ?? [],
        toolpath: run.toolpath ?? null,
        duration_s: run.trajectory.meta.duration_s,
        collision: modCollision,
        sampleTimes: run.trajectory.samples.map((s) => s.t_s),
      }],
      `Modul ${sectionId} am Druckort`,
    );
    // Kollisions-Befund des Moduls (US 12, #128): Palette-Badge merken. Player-Badge,
    // anklickbare Marker (modul-lokal projiziert), Glied-Einfärbung + Live-Abstand
    // treibt updateModuleReplay je Frame verbatim aus meta.collision (ADR-007, #153).
    recordCollisionFinding(sectionId, modCollision);
    // Der Kollisionsbefund ist jetzt Lauf-Eigenschaft (#156): er steht im Befund-
    // Badge + aufklappbaren Befundblock der Leiste, NICHT mehr als 160-Zeichen-Satz
    // in der Player-Zeile. Trägt der Lauf einen Befund, bleibt #sim-status leer (das
    // Badge ist der Anker); Altläufe ohne Befund behalten die ehrliche Zeile (US 25).
    simulationPanel.setStatus(modCollision ? "" : replayStatusLine(`Modul ${sectionId}`, null));
  } catch (err) {
    simulationPanel.setStatus(`Modul-Lauf konnte nicht geöffnet werden: ${err}`);
  }
}

/** „Alle Module": alle Modul-Läufe in Montagereihenfolge am Druckort abspielen. */
async function startModuleSequenceAtDruckort(items: SequenceItem[]): Promise<void> {
  try {
    const steps: ModuleReplayStep[] = [];
    for (const item of items) {
      const run = await loadFromUrl(fsUrl(item.runPath));
      // Platzierung je Modul aus dessen EIGENEM Lauf (meta.base_frame, #161).
      const spec = moduleSceneSpecFor(item.section, run);
      if (!run.trajectory || !spec) continue;
      const modCollision = run.trajectory.meta.collision ?? null;
      steps.push({
        section: item.section,
        spec,
        samples: run.trajectory.samples,
        targets: run.toolpath?.targets ?? [],
        toolpath: run.toolpath ?? null,
        duration_s: run.trajectory.meta.duration_s,
        collision: modCollision,
        sampleTimes: run.trajectory.samples.map((s) => s.t_s),
      });
      // Kollisions-Befund je Modul fürs Palette-Badge merken (#128, verbatim).
      recordCollisionFinding(item.section.section_id, modCollision);
    }
    if (steps.length === 0) {
      simulationPanel.setStatus("Kein Modul-Lauf mit Trajektorie + Druckort-Lage gefunden.");
      return;
    }
    startModuleReplay(steps, `Alle Module — ${steps.length} am Druckort`);
    // Statuszeile sagt die Wahrheit (#153): trägt IRGENDein Modul einen Befund, fällt
    // der Festtext „keine Kollisionsprüfung" (seit #128 falsch); die Kollisionsanzeige
    // folgt dann dem aktiven Modul. Nur wenn KEIN Modul einen Befund hat (Altläufe),
    // bleibt die ehrliche Zeile (US 25).
    const anyFinding = steps.some((s) => s.collision !== null);
    simulationPanel.setStatus(
      `Alle Module laufen — ${steps.length} in Montagereihenfolge am Druckort ` +
        (anyFinding
          ? "(Modul auf der Arbeitsfläche je Schritt durchgetauscht; " +
            "Kollisionskontrolle folgt dem aktiven Modul)."
          : "(Modul auf der Arbeitsfläche je Schritt durchgetauscht; keine Kollisionsprüfung)."),
    );
  } catch (err) {
    simulationPanel.setStatus(`Modul-Sequenz konnte nicht geladen werden: ${err}`);
  }
}

/**
 * Gemeinsamer Start (Issue #97): baut die Druckort-Bühne und treibt DIESELBE
 * TrajectoryPlayer-Instanz über die Modul-Zeitleiste (`buildSequencePlan`) —
 * bei einem Modul ein Lauf, bei mehreren die Sequenz mit Wechsel-Schritt.
 */
function startModuleReplay(steps: ModuleReplayStep[], label: string): void {
  // Kamerastand der WAND-Ansicht als Rückweg sichern — VOR dem Abräumen (#137):
  // `teardownModuleReplay` unten fährt `exitDruckortScene` und nullt den Stash,
  // während die Kamera noch am Druckort steht. Läuft schon ein Replay bzw. sind
  // wir per Umschalter am Druckort, trägt der bestehende Stash die Wand-Ansicht;
  // nur frisch aus der Wand-Ansicht *ist* die aktuelle Kamera die Wand-Ansicht.
  const returnCamera = resolveReplayReturnCamera(einbauortCamera, () => ({
    pos: viewport.camera.position.clone(),
    target: viewport.controls.target.clone(),
    near: viewport.camera.near,
    far: viewport.camera.far,
  }));

  teardownSequence();
  teardownModuleReplay();
  resetRunState();

  shell.setActiveTab("druckplan");
  beginReplay();

  // Gesicherte Wand-Ansicht als Rückweg setzen, Bühne auf den Druckort blenden.
  einbauortCamera = returnCamera;
  druckortState = { view: "druckort" }; // für den async Mesh-Guard in buildDruckortScene
  viewport.world.visible = false;
  druckortGroup.visible = true;

  const plan = buildSequencePlan(
    steps.map((s) => ({
      section_id: s.section.section_id,
      order: s.section.order,
      duration_s: s.duration_s,
    })),
    UMBAU_SECONDS,
  );
  moduleReplay = { steps, plan, built: -1, tcp: null, toolpath: null, druckstand: null };

  const player = new TrajectoryPlayer(
    plan.total_s,
    (state) => updateModuleReplay(state),
    sequencePlaybackRate(plan), // Faktor in Druckphasen, 1× in Umbaupausen (#155)
  );
  trajectoryPlayer = player;
  simulationPanel.showPlayer(plan.total_s, label);
  // Geschwindigkeits-Anzeige (#155): Druckphasen skalieren, Umbaupausen bleiben 3 s.
  simulationPanel.setSpeedModel(replaySpeed, plan.total_s - umbauTotalOf(plan), umbauTotalOf(plan));
  updateModuleReplay(player.state); // Startbild (erstes Modul auf der Fläche, Arm am Start)
  player.play();
}

/**
 * Setzt Bühne + Arm für die globale Zeit (Issue #97): welches Modul auf der
 * Arbeitsfläche steht (Durchtauschen je Schritt) und wie der feste M1013 die Bahn
 * abfährt. Reine Darstellungsmathematik (ADR-007): Gelenke aus der Core-Bahn,
 * Anker = Workstation-Roboterbasis (spec.robotAnchor).
 */
function updateModuleReplay(state: PlayerState): void {
  if (!moduleReplay) return;
  const { steps, plan } = moduleReplay;
  const cur = locateSequenceTime(plan, state.time);
  const frame = moduleReplayFrame(cur); // reine Ableitung (#151), vitest daneben
  const idx = frame.moduleIndex;
  const step = steps[idx];
  // Modul auf der Arbeitsfläche je Schritt durchtauschen (dieselbe Bühne).
  if (moduleReplay.built !== idx) {
    buildDruckortScene(step.spec);
    moduleReplay.built = idx;
    // TCP-Marker, wachsender Strang und Druckstand des aktiven Moduls unter
    // dessen moduleGroup (druckortModule) — NICHT unter druckortGroup: alle drei
    // Views bauen in abschnittslokalen data-mm, moduleGroup trägt die
    // module_pose.workstation (#151/#152). Der vorherige Teilbaum (samt alten
    // Views) wurde von clearDruckortScene GPU-sauber abgeräumt (disposeSubtree),
    // darum ist der Zustand je Modul frisch — kein Übertrag zwischen Modulen.
    const tcp = new TcpMarkerView(step.targets);
    druckortModule?.add(tcp.mesh);
    moduleReplay.tcp = tcp;
    // Wachsender Strang (#152, wie #27): Print wächst zeitgetreu, Travel erzeugt
    // keinen Strang. Ohne Toolpath (Altlauf) kein Strang.
    if (step.toolpath) {
      const toolpath = new ToolpathView(step.toolpath);
      toolpath.setLabelsVisible(viewerSettings.get("target-numbers"));
      druckortModule?.add(toolpath.group);
      moduleReplay.toolpath = toolpath;
    } else {
      moduleReplay.toolpath = null;
    }
    // Wachsender Druckstand als Ist-Volumen (#152, ADR-024): Maße aus der
    // Targets-AABB des Moduls, Höhe wächst mit dem Fortschritt. Sichtbarkeit am
    // ⚙-Schalter `showDruckstand` — aus lässt die Bühne bei Soll-Umriss + Strang.
    if (step.targets.length > 0) {
      const box = targetsBox(step.targets);
      const druckstand = new DruckstandView();
      druckstand.setBox(box.min, box.max);
      druckstand.visible = showDruckstand;
      druckstand.setGrowth(0);
      druckortModule?.add(druckstand.group);
      moduleReplay.druckstand = druckstand;
    } else {
      moduleReplay.druckstand = null;
    }
    // Kollisionsanzeige des NEU aktiven Moduls (#153, Entscheidung #147 Variante b):
    // Badge + anklickbare Marker NUR dieses Moduls, dessen modul-lokale Intervalle
    // auf die Sequenzachse projiziert (Modul-Offset, keine Marker über Umbaupausen).
    // Verbatim aus meta.collision (ADR-007); Altlauf ohne Befund ⇒ leer, kein Crash.
    const localMarkers = step.collision
      ? timelineMarkers(step.collision, step.sampleTimes, step.duration_s)
      : [];
    simulationPanel.setModuleCollision(
      step.collision,
      projectModuleMarkers(localMarkers, plan, idx),
    );
    frameDruckort();
  }
  if (frame.armVisible) {
    if (druckortArm) {
      druckortArm.setPose(interpJoints(step.samples, cur.localFraction), step.spec.robotAnchor);
      druckortArm.visible = true;
    }
    simulationPanel.setPhase(
      `Modul #${step.section.order} druckt — ${idx + 1}/${steps.length} am Druckort`,
    );
  } else {
    // Wechsel-Schritt: das nächste Modul kommt auf die Arbeitsfläche (Arm ruht).
    if (druckortArm) druckortArm.visible = false;
    simulationPanel.setPhase(
      `Modul-Wechsel → #${step.section.order} — nächstes Modul auf die Arbeitsfläche`,
    );
  }
  // TCP-Marker aus der LOKALEN Modulzeit speisen (localFraction), nicht aus der
  // Sequenz-Gesamtzeit; im Umbau ruht er mit dem Arm (frame.markerVisible=false).
  if (moduleReplay.tcp) {
    moduleReplay.tcp.setTime(frame.markerFraction, 1);
    moduleReplay.tcp.mesh.visible = frame.markerVisible && step.targets.length > 0;
  }
  // Strang + Druckstand aus der lokalen Modulzeit (frame.growthFraction, #152)
  // mitwachsen lassen — synchron zu Arm/TCP; im Umbau 0 (neues Modul startet
  // leer). Dieselbe Zeit→Index-Abbildung wie beim Einzel-/Sequenz-Replay (#27).
  if (moduleReplay.toolpath) {
    moduleReplay.toolpath.setGrowth(
      targetIndexAtProgress(step.targets.length, frame.growthFraction),
    );
  }
  moduleReplay.druckstand?.setGrowth(frame.growthFraction);
  // Glied-Einfärbung (US 8) + Live-Abstandszahl (US 11) folgen der MODUL-LOKALEN
  // Zeit des aktiven Moduls (#153) — im Umbau ruhen sie mit dem Arm (neutral).
  applyModuleCollisionFrame(step, cur.localTime_s, frame.armVisible);
  simulationPanel.setPlayerState(state.time, state.playing);
}

/**
 * Wendet den Kollisions-Befund des aktiven Moduls auf einen Frame an (#153):
 * Glied-Einfärbung am Druckort-Arm (`setLinkHighlight`, US 8) + Live-Abstandszahl
 * (US 11, ⚙-abschaltbar) aus der **modul-lokalen** Zeit. Ohne Befund (Altlauf) oder
 * im Umbau (`!printing`) neutral — kein Crash. Reine Zeit-Abbildung (ADR-007).
 */
function applyModuleCollisionFrame(
  step: ModuleReplayStep,
  localTime_s: number,
  printing: boolean,
): void {
  const c = step.collision;
  if (!c || !printing) {
    druckortArm?.setLinkHighlight(null);
    simulationPanel.setCollisionDistance(null);
    return;
  }
  const idx = sampleIndexAtTime(step.sampleTimes, localTime_s);
  const hl = linkHighlightAt(c, idx);
  druckortArm?.setLinkHighlight(hl ? hl.link : null, hl?.status ?? "red");
  simulationPanel.setCollisionDistance(
    showAbstandszahl ? distanceReadout(c, idx) : null,
    statusAtIndex(c, idx),
  );
}

/**
 * Frischt Glied-Einfärbung + Live-Abstand des Druckort-Replays für die aktuelle
 * Player-Zeit auf (#153) — z. B. wenn der ⚙-Schalter „Abstandszahl" umgelegt wird.
 * Ohne laufenden Modul-Replay ein No-op.
 */
function reapplyModuleCollisionFrame(): void {
  if (!moduleReplay || !trajectoryPlayer) return;
  const cur = locateSequenceTime(moduleReplay.plan, trajectoryPlayer.state.time);
  const frame = moduleReplayFrame(cur);
  const step = moduleReplay.steps[frame.moduleIndex];
  if (step) applyModuleCollisionFrame(step, cur.localTime_s, frame.armVisible);
}

// Diagnose-Hook für den Headless-Smoke (#97): Zustand des Modul-Replays am
// Druckort — sichtbar nur für die Automatisierung, ohne UI-Nebenwirkung.
(window as unknown as { __moduleSimDebug?: () => unknown }).__moduleSimDebug = () => ({
  active: moduleReplay !== null,
  atDruckort: moduleReplay !== null && druckortGroup.visible,
  steps: moduleReplay?.steps.length ?? 0,
  built: moduleReplay?.built ?? -1,
  robotVisible: moduleReplay !== null && !!druckortArm && druckortArm.visible,
  moduleVisible: moduleReplay !== null && druckortModule !== null,
  // Endeffektor am Flansch + TCP-Marker am Druckort (#151).
  toolAtFlange: !!druckortArm && druckortArm.flange.children.length > 0,
  markerVisible: !!moduleReplay?.tcp && moduleReplay.tcp.mesh.visible,
  // Kollisionsanzeige des aktiven Moduls (#153): trägt der aktive Modul-Lauf einen
  // Befund? (steuert Live-Abstand + Glied-Einfärbung + Marker — sonst alles leer.)
  activeCollision:
    moduleReplay !== null &&
    moduleReplay.built >= 0 &&
    (moduleReplay.steps[moduleReplay.built]?.collision ?? null) !== null,
});

// Letzte Schnittplan-Prüf-Antwort (Issue #45): zwischengespeichert, bis das
// Panel per Generation-Guard entschieden hat (onCheckApplied) — stale
// Antworten erreichen Simulation/Export/Revisionen nie.
let lastCheckResult: Awaited<ReturnType<typeof proposeDecomposition>> | null = null;

// Wachsender Strang (Issue #27): der gedruckte Toolpath wird nach Trajektorien-
// Zeit aufgedeckt (nicht nur Layer-Slider). Diese Zustände speisen die reine
// Aufdeck-Mathematik (`ToolpathView.setGrowth`, `targetIndexAtProgress`).
let currentTargets: Target[] | null = null;
let currentTrajDuration = 0;
let currentTrajTime = 0;
let lastLayer = { layer: 0, onlyCurrent: false };

// Abschnitts-Sequenz (Issue #27): der Gesamtablauf über alle Abschnitte in
// Druckreihenfolge, mit sichtbarem Umbau-Schritt dazwischen. Umbau-Dauer ist
// reine Darstellung (kein Fachwert) — 3 s je Basis-Sprung.
const UMBAU_SECONDS = 3;

interface SeqSection {
  item: SequenceItem;
  targets: Target[];
  trajectory: Trajectory;
  view: ToolpathView;
  tcp: TcpMarkerView;
  box: BoxMinMax;
  /** z-Hub (mm) auf die echte Bandlage des Abschnitts (Issue #135) — Bahn/TCP
   *  liegen abschnitts-lokal, `meta.section_z0_mm` hebt sie an (Altläufe: 0). */
  lift: number;
}
interface SequenceState {
  loaded: SeqSection[];
  plan: SequencePlan;
  arm: ArmView;
  /** Hub-Gruppe des Sequenz-Arms (Issue #135): z folgt dem aktiven Abschnitt. */
  armLift: THREE.Group;
  player: TrajectoryPlayer;
  baseMarker: THREE.Group | null;
  baseKey: string | null;
}
let sequence: SequenceState | null = null;

/**
 * Deckt den Toolpath des aktuellen Einzel-Laufs auf (Issue #27): bei „Strang
 * wächst mit" nach Trajektorien-Zeit (Wachs-Modus), sonst nach Layer-Slider.
 * Reine Darstellungsmathematik (ADR-007) — der Index kommt aus der normierten
 * Zeit, dieselbe Abbildung wie TCP-Marker/Arm.
 */
function applyStrandReveal(): void {
  if (!toolpathView) return;
  if (viewerSettings.get("grow-strand") && currentTargets && currentTargets.length > 0) {
    const f = currentTrajDuration > 0 ? currentTrajTime / currentTrajDuration : 0;
    toolpathView.setGrowth(targetIndexAtProgress(currentTargets.length, f));
  } else {
    toolpathView.setVisibleUpTo(lastLayer.layer, lastLayer.onlyCurrent);
  }
}

/** Achsparallele Bounding-Box der Toolpath-Targets (Daten-mm) — für den Basis-Marker. */
function targetsBox(targets: Target[]): BoxMinMax {
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (const t of targets) {
    const p = t.frame.pos_mm;
    for (let k = 0; k < 3; k++) {
      if (p[k] < min[k]) min[k] = p[k];
      if (p[k] > max[k]) max[k] = p[k];
    }
  }
  return { min, max };
}

/** Gibt die Traglast des angegebenen Roboters zurück, oder null wenn unbekannt. */
function robotPayloadKg(robotName: string | null): number | null {
  if (!robotName) return null;
  return loadedRobots.find((r) => r.name === robotName)?.payload_kg ?? null;
}

/**
 * Hängt das Endeffektor-Mesh des aktiven Druckjobs an den Flansch des Arms
 * (Issue #28). Das Mesh (aus dem Konfigurator abgelegt) wird über seinen
 * `mesh_path` (/@fs/-URL) geladen und mit `mesh_transform` (Lage relativ zum
 * Flansch, [w,x,y,z] → three (x,y,z,w)) platziert. Fehlt Tool/Mesh, bleibt das
 * Replay wie bisher (abwärtskompatibel). Asynchron, ohne den Aufbau zu blockieren.
 */
function attachToolMeshToArm(arm: ArmView, stillValid?: () => boolean): void {
  if (!currentTool) return;
  const tool = loadedTools.find((t) => t.name === currentTool);
  if (!tool || !tool.mesh_path || !tool.mesh) return;
  const filename = tool.mesh;
  const xf = tool.mesh_transform;
  loadToolMesh(fsUrl(tool.mesh_path), filename)
    .then((obj) => {
      // Bühne inzwischen neu gebaut/abgeräumt (Druckort, #151): stale Mesh nicht
      // anhängen — sonst doppelte Endeffektoren über Modulwechsel hinweg.
      if (stillValid && !stillValid()) {
        disposeSubtree(obj);
        return;
      }
      if (xf) {
        const p = xf.pos_mm;
        const q = xf.quat; // [w, x, y, z]
        obj.position.set(p[0], p[1], p[2]);
        obj.quaternion.set(q[1], q[2], q[3], q[0]);
      }
      arm.attachToFlange(obj);
    })
    .catch(() => {
      /* Mesh optional — Replay bleibt ohne Mesh (kein Fehler). */
    });
}

const panel = new Panel({
  async onRunSelected(files) {
    try {
      await showRun(await loadFromFileList(files));
    } catch (err) {
      panel.setStatus(`Laden fehlgeschlagen: ${err}`);
    }
  },
  onLayerChanged(layer, onlyCurrent) {
    // Layer-Slider merken; im Wachs-Modus deckt die Zeit auf (Slider ignoriert).
    lastLayer = { layer, onlyCurrent };
    if (!viewerSettings.get("grow-strand")) toolpathView?.setVisibleUpTo(layer, onlyCurrent);
  },
  onTravelToggled(visible) {
    toolpathView?.setTravelVisible(visible);
  },
  onWallToggled(visible) {
    if (wallObject) wallObject.visible = visible;
  },
  onContextToggled(visible) {
    if (contextObject) contextObject.visible = visible;
  },
  onModelToggled(visible) {
    if (modelObject) modelObject.group.visible = visible;
  },

  /**
   * Re-Slice-Anfrage vom Parameter-Panel (Issue #9).
   * null-Werte = Karten-Default übernehmen (leeres Feld lässt der Viewer offen,
   * die API füllt den Default aus der Prozessfenster-Karte — ADR-013/014).
   */
  async onReslice(layerHeightMm, strandWidthMm, shells) {
    if (!currentModelPath || !currentGlobalId) {
      panel.setStatus("Modellinformation fehlt — Lauf neu laden.");
      return;
    }
    panel.setStatus("Slicing …");
    panel.setResliceBusy(true);
    try {
      const resp = await postSlice({
        model_path: currentModelPath,
        global_id: currentGlobalId,
        layer_height_mm: layerHeightMm,
        strand_width_mm: strandWidthMm,
        n_shells: shells,
      });
      // Absoluter Windows-Pfad → /@fs/-URL des Vite-Dev-Servers.
      const runUrl = `/@fs/${resp.run_dir.replace(/\\/g, "/")}`;
      const newRun = await loadFromUrl(runUrl);
      await showRun(newRun);
      // Browser-URL aktualisieren, damit der Lauf direkt teil-bar/neu-ladbar ist.
      history.replaceState(null, "", `/?run=${runUrl}`);
    } catch (err) {
      panel.setStatus(`Re-Slicing fehlgeschlagen: ${err}`);
    } finally {
      panel.setResliceBusy(false);
    }
  },

  onTrajectoryPlay() { trajectoryPlayer?.play(); },
  onTrajectoryPause() { trajectoryPlayer?.pause(); },
  onTrajectorySeek(t) { trajectoryPlayer?.seek(t); },

  /**
   * Wand in den aktiven Druckjob des geöffneten Projekts übernehmen (Issue #19).
   * Eignung ist Befund, kein Gate — auch ungeeignete Wände kommen durch.
   */
  async onAdoptToJob(globalId, wallName, _eligible) {
    if (!currentProjectSlug || !currentAssessmentRun) {
      panel.setStatus("Kein Projekt geöffnet — zuerst ein Projekt anlegen.");
      return;
    }
    panel.setAdoptBusy(true);
    try {
      const project = await setPrintJob(
        currentProjectSlug,
        globalId,
        currentAssessmentRun,
        "default",
        wallName ?? undefined,
      );
      shell.updateActivePrintJob(globalId, wallName);
      // Neue Wand → alte Platzierungen sind hinfällig (set_print_job setzt den
      // Job neu auf); Reiter Druckplan zurücksetzen (Issue #22).
      currentWallGlobalId = globalId;
      currentPlacements = [];
      // set_print_job baut den Job serverseitig KOMPLETT neu — Roboter-/
      // Endeffektor-Wahl ist weg; die UI muss mitziehen (Issue #44).
      currentRobot = null;
      currentTool = null;
      previewSelectedTool = null;
      panel.setCurrentRobot(null);
      robotPanel.setCurrentRobot(null);
      toolPanel.setCurrentTool(null);
      toolPanel.setRobotPayload(null);
      toolPanel.setActiveRobot(null);
      updateRobotPreviewTool();
      // Alte Schnittebenen der vorherigen Wand aus der 3D-Ansicht nehmen (Issue #44).
      currentCuts = [];
      updateCutPlanes();
      druckplanPanel.restoreFromJob([]);
      // Neue Wand → Zerlegung/Abschnitts-Läufe des alten Jobs sind hinfällig (Issue #26/#29).
      simulationPanel.reset();
      exportPanel.reset();
      // Badges aus den frischen Revisionsständen: „noch nicht erzeugt" statt
      // fälschlich „aktuell" (Issue #44).
      refreshRevisions(project.print_jobs);
      // Neue Wand → etwaiges Replay beenden, Live-Vorschau wieder aufsetzen (#108).
      endReplay();
      updatePlacementPrecondition();
      panel.setStatus("Druckjob gespeichert.");
    } catch (err) {
      panel.setStatus(`Druckjob konnte nicht gespeichert werden: ${err}`);
    } finally {
      panel.setAdoptBusy(false);
    }
  },

  /**
   * Direkt-Slicing aus der Wand-Auswahl (Issue #10).
   * Erzeugt einen regulären Lauf via POST /slice und öffnet ihn im Viewer
   * (Einzelwand-Ansicht mit Toolpath, wie nach fgc slice).
   */
  async onSliceWall(globalId) {
    if (!currentWallsListModelPath) {
      panel.setStatus("Modellpfad fehlt — Wände-Lauf neu laden.");
      return;
    }
    panel.setStatus("Slicing …");
    panel.setSliceWallBusy(true);
    try {
      const resp = await postSlice({
        model_path: currentWallsListModelPath,
        global_id: globalId,
      });
      const runUrl = `/@fs/${resp.run_dir.replace(/\\/g, "/")}`;
      const newRun = await loadFromUrl(runUrl);
      await showRun(newRun);
      history.replaceState(null, "", `/?run=${runUrl}`);
    } catch (err) {
      panel.setStatus(`Slicing fehlgeschlagen: ${err}`);
    } finally {
      panel.setSliceWallBusy(false);
    }
  },
});

/**
 * Räumt den kompletten Lauf-/3D-Zustand ab — gemeinsame Grundlage von showRun
 * UND startSequence (Issue #38): `clearWorld` detacht nur; ohne das Nullen
 * würde der Raycaster weiter gegen die entfernte Modellgruppe picken
 * (Ghost-Pick auf unsichtbare Wände) und das Reslice-Panel auf den alten
 * Einzel-Lauf zeigen.
 */
function resetRunState(): void {
  // Bestehenden Player stoppen und Marker/Arm entfernen (Issue #14/#18).
  trajectoryPlayer?.destroy();
  trajectoryPlayer = null;
  // Aufdeck-Zustand zurücksetzen (Issue #27): erst der neue Lauf setzt ihn.
  currentTargets = null;
  currentTrajDuration = 0;
  currentTrajTime = 0;
  // Marker/Arm hängen seit Issue #135 in der Replay-Hub-Gruppe (bzw. bei der
  // Sequenz in Abschnitts-Hub-Gruppen) — `removeFromParent` detacht sie VOR
  // clearWorld, damit die geteilten Arm-GLBs (#41) nicht disposed werden.
  if (tcpMarker) {
    tcpMarker.mesh.removeFromParent();
    tcpMarker = null;
  }
  if (armView) {
    armView.group.removeFromParent();
    armView.dispose(); // vom globalen Render-Modus-Zustand abmelden (Issue #41)
    armView = null;
  }
  // Wachsender Druckstand + Kollisions-Replay-Zustand abräumen (#128).
  if (druckstand) {
    druckstand.group.removeFromParent();
    druckstand.dispose();
    druckstand = null;
  }
  clearCollisionReplay();
  if (placementArm) {
    placementArm.group.removeFromParent();
    placementArm.dispose(); // vom globalen Render-Modus-Zustand abmelden (Issue #41/#93)
    placementArm = null;
  }

  viewport.clearWorld();
  replayLift = null; // clearWorld hat die Replay-Hub-Gruppe entfernt (Issue #135)
  toolpathView = null;
  wallObject = null;
  contextObject = null;
  modelObject = null;
  cutPlanes = null; // clearWorld hat auch die Schnittebenen entfernt (Issue #24)
  sectionBoxes = null; // clearWorld hat auch die Abschnitts-Quader entfernt (Issue #84)
  placementMarkers = null; // clearWorld hat auch die Platzierungs-Marker entfernt (Issue #93)

  // Wand-Auswahl-/Re-Slicing-Kontext des alten Laufs aufheben (Issue #10/#9/#38).
  currentCandidates = null;
  currentWallsListModelPath = null;
  currentModelPath = null;
  currentGlobalId = null;
  panel.setResliceParams(null, false);
  panel.hideWallReport();
}

// Reentrancy-Guard (Issue #45): überlappende Ladevorgänge (Doppelklick auf
// Projekt/Abschnitt) würden nach ihrem jeweiligen clearWorld BEIDE ihr Modell
// einfügen — der zweite Aufruf wird verworfen.
let showRunBusy = false;

async function showRun(run: RunData): Promise<void> {
  if (showRunBusy) return;
  showRunBusy = true;
  try {
    await showRunInner(run);
  } finally {
    showRunBusy = false;
  }
}

async function showRunInner(run: RunData): Promise<void> {
  if (!run.wallspec && !run.toolpath && !run.modelMap && !run.trajectory) {
    panel.setStatus("Im Ordner liegen keine darstellbaren Artefakte (wallspec, toolpath, model_map oder trajectory).");
    return;
  }
  // Sequenz-Modus verlassen, falls aktiv (Issue #27) — Einzel-Lauf übernimmt.
  teardownSequence();
  resetRunState();

  // Wand-Auswahl-Kontext für den neuen Lauf setzen (Issue #10).
  currentCandidates = run.candidates;
  currentWallsListModelPath = run.modelMap?.model ?? null;

  // Modellübersicht: binäre model.glb, eingefärbt nach Eignung — Issue #6.
  if (run.modelMap && run.modelGlbUrl) {
    modelObject = await loadModelObject(run.modelGlbUrl, run.modelMap, run.candidates);
    viewport.world.add(modelObject.group);
  }

  // Replay auf echter Bandlage (Issue #135): die Hub-Gruppe hebt alle
  // abschnitts-lokalen Lauf-Objekte um `meta.section_z0_mm` (0 bei Altläufen/
  // Übersichts-Läufen — dann bit-identisch zu heute). Modellübersicht und
  // Gebäudekontext liegen in Weltkoordinaten und bleiben draußen.
  const liftMm = sectionLiftMm(run.trajectory?.meta);
  replayLift = new THREE.Group();
  replayLift.name = "replay-lift";
  replayLift.position.z = liftMm;
  viewport.world.add(replayLift);

  if (run.wallspec) {
    wallObject = buildWallObject(run.wallspec);
    replayLift.add(wallObject);
  }
  if (run.toolpath) {
    toolpathView = new ToolpathView(run.toolpath);
    toolpathView.setLabelsVisible(viewerSettings.get("target-numbers"));
    replayLift.add(toolpathView.group);
  }
  if (run.context) {
    contextObject = buildContextObject(run.context);
    contextObject.visible = panel.contextVisible;
    viewport.world.add(contextObject);
  }

  // Schalter-Zustände des Panels auf die frischen Objekte anwenden (Issue #49):
  // abgewählte Checkboxen (Travel/Wand/Modellübersicht) gelten auch nach Neuladen.
  toolpathView?.setTravelVisible(panel.travelVisible);
  if (wallObject) wallObject.visible = panel.wallVisible;
  if (modelObject) modelObject.group.visible = panel.modelVisible;

  // Kamera fokussieren: Toolpath > einzelne Wand > Modellübersicht > Welt.
  // Bei aktiver Roboter-Vorschau nur als Restore-Ziel merken (Issue #43).
  fitWorld(toolpathView?.group ?? wallObject ?? modelObject?.group ?? viewport.world);

  // Wand-Fokus ab Zerlegung: Isolierung + Gebäudekontext an die frisch gebauten
  // Objekte anlegen (ohne Kamera-Refit — der Lauf lädt in der Modellübersicht).
  applyWallFocus(false);

  // Target-Zahl aus dem Summary lesen (ADR-007); Fallback für alte Läufe
  // (schema_version 0.1, ohne summary): Länge der Target-Liste.
  const targetCount = run.toolpath?.summary?.n_targets ?? run.toolpath?.targets.length ?? 0;
  panel.showRun(run, toolpathView?.maxLayer ?? 0, targetCount);
  panel.setStatus("");
  // Layer-Slider-Ausgangsstand für den Aufdeck-Umschalter merken (Issue #27).
  lastLayer = { layer: toolpathView?.maxLayer ?? 0, onlyCurrent: false };

  // Modell/Wand-Info für Re-Slicing merken (Issue #9).
  // Erste Wahl: toolpath.params.model_path (0.3, absoluter Pfad).
  // Fallback: context.model (ältere Läufe, kann relativ sein).
  currentModelPath = run.toolpath?.params?.model_path ?? run.context?.model ?? null;
  currentGlobalId = run.toolpath?.wall_global_id ?? null;

  // Parameter-Panel: nur bei Slice-Läufen mit Wand-Info anzeigen.
  const canReslice = !!(currentModelPath && currentGlobalId);
  panel.setResliceParams(run.toolpath?.params ?? null, canReslice);

  // Trajektorien-Animation (Issue #14) + Präsentations-FK-Arm (Issue #18)
  if (run.trajectory) {
    const traj = run.trajectory;
    const targets = run.toolpath?.targets ?? null;

    // TCP-Marker entlang des Toolpath (falls vorhanden)
    if (targets && targets.length > 0) {
      tcpMarker = new TcpMarkerView(targets);
      replayLift?.add(tcpMarker.mesh);
    }

    // Kapsel-Arm: fährt die Bahn per Präsentations-FK ab (ADR-007-Klarstellung).
    // In der Hub-Gruppe (#135) landet die Basis (`meta.base_frame`, lokal ggf.
    // negativ) auf ihrer absoluten Aufstellhöhe über dem Boden.
    armView = new ArmView(M1013_DH);
    armView.visible = viewerSettings.get("show-arm");
    replayLift?.add(armView.group);
    // Endeffektor-Mesh des Druckjobs am Flansch (Issue #28) — falls gesetzt.
    attachToolMeshToArm(armView);

    // Podest-Sockel am Replay-Arm (Issue #135, Muster basemarker.ts/#133):
    // steht die Basis über dem Boden (absolute Aufstellhöhe > 0), reicht ein
    // Sockel von der Basis bis zum Boden hinunter — sonst keiner.
    const pedestal = replayPedestal(traj.meta.base_frame ?? null, liftMm);
    if (pedestal) {
      const mesh = buildReplayPedestal(pedestal.heightMm);
      mesh.position.set(pedestal.xMm, pedestal.yMm, pedestal.topZMm);
      replayLift?.add(mesh);
    }

    const duration = traj.meta.duration_s;
    const updateArm = (time: number) => {
      const f = duration > 0 ? time / duration : 0;
      const pose = computeArmPose(M1013_DH, traj.samples, targets, f, traj.meta.base_frame ?? null);
      armView?.setPose(pose.joints_rad, pose.anchor);
    };

    // Wachs-Zustand für diesen Lauf setzen (Issue #27): der Strang wächst nach
    // Trajektorien-Zeit, gesteuert über `applyStrandReveal`.
    currentTargets = targets;
    currentTrajDuration = duration;
    currentTrajTime = 0;

    // Wachsender Druckstand (Kollisionskontrolle S3, US 10, #128): dünnes
    // three.js-Objekt, Maße aus der Toolpath-Box, Wachstum aus der Zeit. Nur
    // sichtbar bei eingeschaltetem ⚙-Schalter — aus lässt das Replay unverändert.
    if (targets && targets.length > 0) {
      const box = targetsBox(targets);
      druckstand = new DruckstandView();
      druckstand.setBox(box.min, box.max);
      druckstand.visible = showDruckstand;
      druckstand.setGrowth(0);
      replayLift?.add(druckstand.group);
    }

    trajectoryPlayer = new TrajectoryPlayer(duration, (state) => {
      const interp = interpolateSample(traj.samples, state.time);
      panel.updateTrajectoryState(state.time, state.playing, interp.io);
      // Replay-Player im Reiter Simulation spiegeln (Issue #48) — no-op, solange
      // er ausgeblendet ist; aktiv, wenn „Im Player ansehen" hier gestartet hat.
      simulationPanel.setPlayerState(state.time, state.playing);
      tcpMarker?.setTime(state.time, duration);
      updateArm(state.time);
      // Strang zeitgetreu mitwachsen lassen (Issue #27), synchron zu Arm/TCP.
      currentTrajTime = state.time;
      applyStrandReveal();
      // Druckstand mitwachsen (US 10) + Kollisions-Einfärbung/Abstandszahl (US 8/11).
      druckstand?.setGrowth(duration > 0 ? state.time / duration : 0);
      applyCollisionAtTime(state.time);
    }, constantPlaybackRate); // Einzel-Lauf ohne Umbau: konstant der Sitzungs-Faktor (#155)
    updateArm(0); // Arm sofort auf Startpose stellen
    // Kollisions-Befund dieses Laufs übernehmen (US 8/9/11/12/25) — verbatim,
    // fehlt der Block, bleibt alles neutral und die ehrliche Zeile steht.
    setupCollisionForRun(traj);
    panel.showTrajectory(traj);
  } else {
    panel.hideTrajectory();
  }
  // Anfangs-Aufdeckung anwenden (Wachs-Modus: leerer Strang bei t=0; sonst
  // ganzer Toolpath nach Layer-Slider) — Issue #27.
  applyStrandReveal();

  // Schnittebenen des Zerlegungsvorschlags neu aufsetzen (Issue #24) —
  // clearWorld hat sie entfernt, die Modellübersicht ist jetzt geladen.
  updateCutPlanes();

  // ⚙-Sektion „Replay-Bühne" nachziehen (Issue #159): trägt der frische Lauf
  // einen Toolpath, ist die Bühne offen — im Reiter Projekt taucht das Menü dann
  // mit dieser Sektion auf; ein Übersichts-Lauf ohne Toolpath lässt es verborgen.
  refreshViewerSettingsSections();
}

/**
 * Zeigt die Schnittebenen des Zerlegungsvorschlags in der Modellübersicht
 * (Issue #24). Reine Darstellung eines Plans (ADR-007): Lage approximiert über
 * die Bounding-Box des Wand-Meshes; keine Ebenen ohne Schnitte/Wand/Übersicht.
 */
function updateCutPlanes(): void {
  if (cutPlanes) {
    viewport.world.remove(cutPlanes.group);
    cutPlanes = null;
  }
  if (currentCuts.length === 0 || !currentWallGlobalId || !modelObject) {
    rebuildCutMeasureLabels();
    return;
  }
  const wallObj = modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`);
  if (!wallObj) {
    rebuildCutMeasureLabels();
    return;
  }
  const planes = buildCutPlanes(currentCuts, wallObj, viewport.world);
  cutPlanes = planes;
  viewport.world.add(planes.group);
  rebuildCutMeasureLabels();
}

/**
 * Baut die klickbaren Abschnitts-Quader in der Modellübersicht neu auf (Issue
 * #84). Reine Darstellung eines Plans (ADR-007): Lage aus der Bounding-Box des
 * Wand-Meshes + Abschnittsgrenzen; keine Quader ohne Abschnitte/Wand/Übersicht.
 * Der zuletzt gewählte Fokus wird nach dem Neuaufbau wieder hervorgehoben.
 */
function updateSectionBoxes(): void {
  if (sectionBoxes) {
    viewport.world.remove(sectionBoxes.group);
    sectionBoxes = null;
  }
  const sections = druckplanPanel.getSections();
  if (sections.length === 0 || !currentWallGlobalId || !modelObject) return;
  const wallObj = modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`);
  if (!wallObj) return;
  const boxes = buildSectionBoxes(sections, wallObj, viewport.world);
  sectionBoxes = boxes;
  viewport.world.add(boxes.group);
  // Simulieren-Knöpfe an die (evtl. per Re-Check bestätigte) Art spiegeln (#97).
  simulationPanel.setKind(druckplanPanel.getKind());
  // Fokus-Highlight nach dem Neuaufbau wiederherstellen (frische Quader).
  applySectionFocus(boxes, focusStore.get());
  // Basis-Marker aller Teile + Fokus-Mesh am frisch bewerteten Abschnittssatz (#93).
  updatePlacementScene();
  // Live-Vorschau am frisch bewerteten Abschnitt nachziehen (Standoff/Params, #85).
  updatePreparePreview();
  // Druckort-Ansicht mit dem frischen Abschnittssatz abgleichen (Issue #96):
  // neue Modul-Lagen aufnehmen bzw. bei weggefallenen Voraussetzungen verlassen.
  syncDruckort();
}

/**
 * Baut die Basis-Marker **aller** Teile neu auf und positioniert das Fokus-Mesh
 * (Issue #93, PRD #88). Reine Darstellung eines Plans (ADR-007): je Teil ein
 * Marker aus seiner Platzierung + den Wandmaßen (Position aus lateral/standoff,
 * Höhe aus der Aufstellhöhe/Podest); das fokussierte Teil zeigt statt des Markers
 * das echte M1013-Mesh in neutraler Pose. Sichtbar nur im **Vorbereiten-Modus**
 * der Modellübersicht — im Simulieren-Modus (#86) und in der Roboter-Vorschau
 * (#31) bleiben Marker/Mesh geräumt, damit die Live-Vorschau (#85) und der volle
 * Arm-Lauf unbeeinträchtigt bleiben. Wird nach jeder Core-Neubewertung/Fokus-
 * Änderung aufgerufen (frische Platzierungen).
 */
function updatePlacementScene(): void {
  if (placementMarkers) {
    viewport.world.remove(placementMarkers.group);
    placementMarkers = null;
  }
  const wall = placementWallDims();
  const sections = druckplanPanel.getSections();
  if (wall && sections.length > 0) {
    // Marker aller Teile aus dem EINEN Selektor (Issue #171): jeder folgt seinem
    // aktiven Platzierungs-Override, nicht der ggf. veralteten Zerlegungs-Lage.
    placementMarkers = buildPlacementMarkers(
      sections,
      wall,
      currentActiveJob?.section_overrides ?? [],
    );
    viewport.world.add(placementMarkers.group);
  }
  updatePlacementFocusMesh(wall);
  applyOverlayToggles(); // Basis-Schalter (⚙) auf die frische Marker-Gruppe anwenden
  rebuildBasisChips();
}

/**
 * Die Wandmaße für die Platzierungs-Marker — oder `null`, wenn die Marker ruhen
 * sollen: während eines Replays (#108), in der Roboter-Vorschau (#31) oder ohne
 * Wand/Modellübersicht. Ein `null` räumt Marker und Mesh (siehe Aufrufer).
 */
function placementWallDims(): WallFrame | null {
  if (replayActive || robotPreview.visible) return null;
  if (!currentWallGlobalId || !modelObject) return null;
  const wallObj = modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`);
  if (!wallObj) return null;
  return wallFrameFromObject(wallObj, viewport.world);
}

/**
 * Positioniert/zeigt das echte M1013-Mesh am Fokus-Teil (Issue #93) und versteckt
 * dabei dessen Marker — sauberer Marker↔Mesh-Tausch. Ohne Fokus (oder ohne
 * Marker/Wand) ruht der Arm und alle Marker sind sichtbar. Der Arm teilt die
 * global geladenen GLBs (#41); scheitert deren Load, zeigt er das Kapsel-Schema.
 */
function updatePlacementFocusMesh(wall: WallFrame | null): void {
  const sectionId = focusStore.get();
  const section = wall
    ? druckplanPanel.getSections().find((s) => s.section_id === sectionId)
    : undefined;
  if (!placementMarkers || !section || !wall) {
    if (placementArm) placementArm.visible = false;
    if (placementMarkers) applyPlacementFocus(placementMarkers, null); // alle Marker zeigen
    return;
  }
  if (!placementArm) {
    placementArm = new ArmView(M1013_DH);
    viewport.world.add(placementArm.group);
  }
  // Fokus-Arm an der effektiven Platzierung (Issue #171): derselbe Selektor wie
  // die Marker — Arm und Basis-Marker des Teils divergieren nach Override nicht.
  placementArm.setPose(M1013_HOME_RAD, sectionBaseFrame(section, wall, sectionOverrideFor(section.section_id)));
  placementArm.visible = true;
  applyPlacementFocus(placementMarkers, section.section_id);
}

/**
 * Reagiert auf einen Fokus-Wechsel (Issue #84): den Fokus-Quader hervorheben
 * (die anderen bleiben unsichtbar → ganze Wand sichtbar) und die Kamera weich
 * einfassen. Reine Darstellung/Animation (ADR-007), von der Fokus-Auswahl im
 * Panel getrieben — kein eigener Fachzustand hier.
 */
/**
 * Speist die ▪-Marker der Teile-Palette (Issue #91): aus dem *persistierten*
 * Druckjob (`process_params.sections`, #82) leitet `slicingOverrideSectionIds`
 * ab, welche Teile einen Slicing-Override tragen — der Marker erscheint/verschwindet
 * genau mit dem Override. Reine Anzeigequelle (ADR-007). Nach jeder Änderung an den
 * Abschnitts-Overrides bzw. am Abschnittssatz aufgerufen.
 */
function updatePartsOverrideMarkers(): void {
  // Union aus Slicing- (#82/#91) und Platzierungs-Overrides (#94): der ▪-Marker
  // erscheint, sobald ein Teil IRGENDEINEN individuellen Override trägt.
  const ids = new Set([
    ...slicingOverrideSectionIds(currentActiveJob?.process_params?.sections),
    ...placementOverrideSectionIds(currentActiveJob?.section_overrides),
  ]);
  druckplanPanel.setSlicingOverrideSections([...ids].sort());
  // Ehrliche Modul-Karte (Issue #161): die Karten-Zeile „Platzierung: …" zeigt
  // für übersteuerte Teile die Override-Werte des aktiven Jobs (sparse) statt
  // der ggf. veralteten Zerlegungs-Platzierung — dieselbe Quelle wie die Marker.
  druckplanPanel.setPlacementOverrideValues(currentActiveJob?.section_overrides ?? []);
}

/** Anzeigename eines Teils („#<order> <section_id>") aus dem aktuellen Teilesatz,
 *  oder `null` (kein/unbekanntes Teil) — für Scope-Chip, Teil-Option, Titel. */
function partNameFor(sectionId: string | null): string | null {
  const section = druckplanPanel.getSections().find((s) => s.section_id === sectionId);
  return section ? `#${section.order} ${section.section_id}` : null;
}

// Die Wirkungen eines Fokus-Wechsels (Issue #196; früher die handgepflegte
// `onFocusChanged`-Kaskade): Mitglieder + Reihenfolge sind der vitest-Vertrag
// FOCUS_EFFECT_ORDER (`ui/focus-store.ts`) — hier stehen nur die echten
// Effekte. Registriert wird EINMAL, unten nach den Panel-Konstruktionen.
const focusEffects: FocusEffects = {
  /** Fokus-Quader hervorheben — die anderen bleiben unsichtbar, ganze Wand sichtbar (#84). */
  highlightSectionBox(sectionId) {
    if (sectionBoxes) applySectionFocus(sectionBoxes, sectionId);
  },
  /** Fokus tauscht Marker↔Mesh am gewählten Teil (Issue #93) — sauberer Wechsel. */
  swapPlacementFocusMesh() {
    updatePlacementFocusMesh(placementWallDims());
  },
  /** Gilt-für-Umschalter (Issue #92): erscheint nur bei gewähltem Teil; Abwahl
   *  fällt auf Global zurück. Betrifft seit dem Druckplan-Split (#106) NUR die
   *  Slicing-Rubrik. */
  reconcileScopeSwitch(sectionId) {
    scopeSwitch.onFocusChanged(partNameFor(sectionId));
  },
  /** Slicing-Formulare auf den wirksamen Scope stellen (+ Kopf-Notiz #107) —
   *  EIN Hop statt des früheren Umwegs über den Umschalter-Callback (#196);
   *  läuft NACH reconcileScopeSwitch (liest dessen frische Stellung). */
  syncProcessParamsScope(sectionId) {
    processParamsPanel.setScope(scopeSwitch.scope, sectionId);
    updateSlicingScopeNote();
  },
  /** Platzierung-Accordion (Zerlegung, Issue #106/#94): fokus-getrieben, ohne
   *  Scope — ein gewähltes Teil macht seine Platzierungsfelder bedienbar. */
  syncPlacementOverrideScope() {
    placementOverridePanel.onFocusChanged();
  },
  /** Accordion-Titel „Platzierung — <Teil>" (#106). */
  setPlacementTitle(sectionId) {
    druckplanPanel.setPlacementTitle(partNameFor(sectionId));
  },
  /** Druckort-Ansicht (Issue #96): Fokus weg/gewandert → Ansicht abgleichen
   *  (verlassen bzw. an der frischen Modul-Lage neu aufbauen), Umschalter zeigen. */
  syncDruckort() {
    syncDruckort();
  },
  /** Kamera weich einfassen (#84). */
  frameFocus(sectionId) {
    frameFocus(sectionId);
  },
  /** Live-Vorschau „Vorbereiten" am Fokus neu aufbauen (#85). */
  updatePreparePreview() {
    updatePreparePreview();
  },
  /** Fokus ist das Standard-Ziel des „Fokus … simulieren"-Knopfs (Issue #86). */
  syncSimulationDock() {
    simulationPanel.onFocusChanged();
  },
  /** Kollisions-Advisor prüft das Fokus-Teil (sonst das erste) — Scope-Chip
   *  ehrlich mitführen (Prüf-UX #139/#145). */
  syncCollisionAdvisorScope() {
    collisionAdvisorPanel.onFocusChanged();
  },
};

/**
 * Baut die Live-Vorschau „Vorbereiten" für den Fokus-Abschnitt neu auf (Issue
 * #85): billige, IK-freie Düsen-Schablone entlang der sofort gesliceten Bahn +
 * atmender Sicherheitspuffer. Reine Darstellung (ADR-007): sie liest die
 * **effektiven** Params (global ⊕ Abschnitts-Override, #82) aus den *live*
 * Formularwerten (Reglerziehen, noch ungespeichert) und die geplante Platzierung
 * (#80). Ohne Fokus/Wand/Übersicht oder in der Roboter-Vorschau: keine Vorschau.
 */
function updatePreparePreview(): void {
  const sectionId = focusStore.get();
  // Während eines Replays (Issue #108) und in der Druckort-Ansicht (Issue #96)
  // ruht die billige Live-Vorschau — dort läuft der volle Arm-Lauf bzw. die
  // Workstation-Szene. Kein Fokus/Wand/Übersicht: ebenfalls nichts.
  if (replayActive || isDruckort(druckortState) || !sectionId || robotPreview.visible || !currentWallGlobalId || !modelObject) {
    preparePreview.clear();
    return;
  }
  const section = druckplanPanel.getSections().find((s) => s.section_id === sectionId);
  const wallObj = modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`);
  if (!section || !wallObj) {
    preparePreview.clear();
    return;
  }
  const wall = wallFrameFromObject(wallObj, viewport.world);
  if (!wall) {
    preparePreview.clear();
    return;
  }
  // Effektive Params: global (live) ⊕ Teil-Override (live) → effektiv (#82/#92).
  const live = processParamsPanel.liveParams();
  const globalParams = globalParamsFrom(live.slice, live.orientation);
  const override = processParamsPanel.liveOverrideFor(sectionId);
  const effective = resolveSectionParams(globalParams, override);
  const orientation = {
    leadRad: degToRad(effective.orientation?.lead_deg ?? 0),
    kippRad: degToRad(effective.orientation?.kipp_deg ?? 0),
  };
  // Sicherheits-Mindestabstand aus der Workstation des Druckjobs (#77); Default 50.
  const ws = loadedWorkstations.find((w) => w.name === currentWorkstation);
  const safetyMinMm = ws?.safety_min_distance_mm ?? 50;
  preparePreview.update({
    section,
    wall,
    slice: effective.slice ?? {},
    orientation,
    safetyMinMm,
    // Effektive Platzierung (Issue #171): senkt ein Override den Abstand unters
    // Minimum, wird die Sicherheits-Vorschau nicht-grün (B21) — eine Quelle mit
    // Marker/Arm/Karte.
    override: sectionOverrideFor(sectionId),
  });
}

/**
 * Fasst den Fokus-Abschnitt weich mit der Kamera ein (Issue #84): der
 * Orbit-Punkt wandert sanft auf den Abschnitts-Mittelpunkt, der Abstand bleibt
 * groß genug, dass die **ganze Wand sichtbar** bleibt (Bezug zu Nachbarn und
 * Schnittfugen). Ohne Fokus fährt die Einfassung weich auf die Wandmitte
 * zurück. Nur in der Modellübersicht (nicht in der Roboter-Vorschau).
 */
function frameFocus(sectionId: string | null): void {
  // In der Druckort-Ansicht (Issue #96) rahmt die Workstation-Szene die Kamera
  // (frameDruckort) — die Wand-Einfassung darf nicht dagegen fahren.
  if (isDruckort(druckortState)) return;
  if (robotPreview.visible || !currentWallGlobalId || !modelObject) return;
  const wallObj = modelObject.group.getObjectByName(`wall:${currentWallGlobalId}`);
  if (!wallObj) return;
  const wallBox = new THREE.Box3().setFromObject(wallObj);
  if (wallBox.isEmpty()) return;
  const target = wallBox.getCenter(new THREE.Vector3());
  if (sectionId && sectionBoxes) {
    const handle = sectionBoxes.handles.find((h) => h.sectionId === sectionId);
    if (handle) handle.mesh.getWorldPosition(target);
  }
  // Abstand ≥ Wanddiagonale → die ganze Wand bleibt im Bild; Blickrichtung
  // beibehalten (nur der Orbit-Punkt wandert, kein harter Kameraschwenk).
  const diag = wallBox.getSize(new THREE.Vector3()).length();
  const dir = new THREE.Vector3().subVectors(viewport.camera.position, viewport.controls.target);
  if (dir.lengthSq() < 1e-6) dir.set(0.7, 0.5, 0.9);
  dir.normalize();
  const toPos = target.clone().addScaledVector(dir, Math.max(diag, 1) * 0.9);
  startCameraTween(toPos, target.clone());
}

// --- Weiche Kamera-Einfassung (Issue #84) ---
// Reine Darstellung (ADR-007): eased Tween von Kamera-Position + Orbit-Ziel,
// getrieben vom Fokus-Zustand. setAnimationLoop rendert ohnehin jeden Frame
// (Damping) — der Tween mutiert nur Kamera/Ziel über die Zeit.
interface CameraTween {
  start: number;
  dur: number;
  fromPos: THREE.Vector3;
  toPos: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toTarget: THREE.Vector3;
}
let cameraTween: CameraTween | null = null;
const CAMERA_TWEEN_MS = 600;

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function startCameraTween(toPos: THREE.Vector3, toTarget: THREE.Vector3): void {
  cameraTween = {
    start: performance.now(),
    dur: CAMERA_TWEEN_MS,
    fromPos: viewport.camera.position.clone(),
    toPos,
    fromTarget: viewport.controls.target.clone(),
    toTarget,
  };
  requestAnimationFrame(stepCameraTween);
}

function stepCameraTween(now: number): void {
  if (!cameraTween) return;
  const raw = Math.min(1, (now - cameraTween.start) / cameraTween.dur);
  const e = easeInOutCubic(raw);
  viewport.camera.position.lerpVectors(cameraTween.fromPos, cameraTween.toPos, e);
  viewport.controls.target.lerpVectors(cameraTween.fromTarget, cameraTween.toTarget, e);
  viewport.camera.updateProjectionMatrix();
  if (raw < 1) {
    requestAnimationFrame(stepCameraTween);
  } else {
    cameraTween = null;
  }
}

/**
 * Voraussetzungs-Hinweis im Reiter Druckplan (Issue #22): Platzierung braucht
 * einen Druckjob mit Wand und Roboter. Kein Gate — nur Orientierung.
 */
function updatePlacementPrecondition(): void {
  let hint: string | null = null;
  if (!currentProjectSlug) {
    hint = "Kein Projekt geöffnet — zuerst ein Projekt anlegen.";
  } else if (!currentWallGlobalId) {
    hint = "Zuerst im Reiter Projekt eine Wand in den Druckjob übernehmen.";
  } else if (!currentRobot) {
    hint = "Zuerst im Reiter Roboter bewerten — die Platzierung braucht die Kinematik des Roboters.";
  }
  druckplanPanel.setPrecondition(hint);
  // Der Reiter Simulation teilt dieselben Voraussetzungen (Wand + Roboter) und
  // braucht zusätzlich einen Schnittplan (Issue #26) — dessen Fehlen zeigt die
  // Abschnittsliste selbst (leerer Zustand). Der Reiter Export (Issue #29) teilt
  // sie ebenfalls und braucht zusätzlich simulierte Abschnitte.
  simulationPanel.setPrecondition(hint);
  exportPanel.setPrecondition(hint);
}

/**
 * Stellt die Abschnitte des referenzierten Zerlegungslaufs wieder her (Issue #24):
 * der Viewer spielt das decompose.json-Artefakt nur ab (ADR-007), die Eingaben
 * (Zerlegungsart + Schnittebenen) kommen aus dem Druckjob (project.json — ADR-016).
 */
async function restoreDecomposition(job: PrintJob): Promise<void> {
  const kind = job.decomposition_kind ?? "abschnitt";
  if (!job.decompose_run) return;
  try {
    const res = await fetch(`${fsUrl(job.decompose_run)}/decompose.json`);
    if (!res.ok) return;
    const artifact = (await res.json()) as {
      sections: DecompositionSection[];
      freigang?: FreigangFinding | null;
    };
    // Übernahme-Protokoll (#193): Job + voller setSections-Fanout (Zerlegungs-
    // Ansicht, Simulation/Export #26/#29, Teil-Override-Formulare #82/#92,
    // Platzierungsfelder #94) + ▪-Marker (#91) + veraltet-Badges (inkl.
    // last_pruef, #175). Vor #193 fehlte hier refreshRevisions (Divergenz =
    // Bug, #161-Familie).
    adoptJobResponse(jobAdoptPorts, { print_jobs: [job] }, {
      jobId: job.job_id,
      sections: artifact.sections,
      druckplan: { kind },
    });
    // Freigang-Befund „Wand zu dick" (Issue #163) verbatim aus dem Lauf — so
    // überlebt das Banner das Neuladen (additiv; Altläufe ohne Feld → still).
    druckplanPanel.setFreigang(artifact.freigang);
    // Prüf-Umfang (Issue #175) wird erst mit der nächsten Zerlegungs-Antwort
    // scharf (bis dahin generischer „Ganze Wand prüfen"-Knopf).
    druckplanPanel.setPruefScope(null);
    // Klickbare Abschnitts-Quader für den Fokus-Klick aufbauen (Issue #84).
    updateSectionBoxes();
  } catch {
    // Zerlegungslauf nicht (mehr) lesbar — Panel bleibt ohne Abschnitte, kein Fehler.
  }
}

// --- Klickbare Wand-Auswahl (Issue #10) ---
// Raycaster auf model.glb-Knoten; Drag-Schwelle 5 px, damit OrbitControls
// nicht mit einfachen Klicks kollidiert.

let mouseDownX = 0;
let mouseDownY = 0;
const raycaster = new THREE.Raycaster();

viewport.canvas.addEventListener("mousedown", (e) => {
  mouseDownX = e.clientX;
  mouseDownY = e.clientY;
});

viewport.canvas.addEventListener("click", (e) => {
  if (!modelObject) return;
  // three.js-Raycaster ignoriert visible=false NICHT — eine per Checkbox
  // ausgeblendete Modellübersicht darf nicht pickbar sein (Issue #49).
  if (!modelObject.group.visible) return;
  // Drag (> 5 px) → Orbit-Steuerung, kein Pick (gilt für alle Reiter).
  if (Math.hypot(e.clientX - mouseDownX, e.clientY - mouseDownY) > 5) return;

  // Reiter Zerlegung/Druckplan (Issue #84/#106): Klick auf einen Abschnitts-
  // Quader nimmt ihn in den Fokus (Toggle im `focus-store.ts`, #196);
  // Highlight + weiche Kamera-Einfassung folgen über die registrierte
  // Fokus-Kaskade. Fokus/Teile-Palette leben in beiden Reitern.
  if (shell.activeTab === "zerlegung" || shell.activeTab === "druckplan") {
    if (!sectionBoxes || sectionBoxes.handles.length === 0) return;
    const rectD = viewport.canvas.getBoundingClientRect();
    raycaster.setFromCamera(
      new THREE.Vector2(
        ((e.clientX - rectD.left) / rectD.width) * 2 - 1,
        -((e.clientY - rectD.top) / rectD.height) * 2 + 1,
      ),
      viewport.camera,
    );
    const hit = raycaster.intersectObjects(
      sectionBoxes.handles.map((h) => h.mesh),
      false,
    )[0];
    if (!hit) return;
    const handle = sectionBoxes.handles.find((h) => h.mesh === hit.object);
    if (handle) druckplanPanel.focusSection(handle.sectionId);
    return;
  }

  // Wand-Auswahl nur im Reiter Projekt — dort lebt der Eignungsbericht; in den
  // anderen Reitern gehört der Klick dem Orbit bzw. dem Schnittebenen-Drag.
  if (shell.activeTab !== "projekt") return;

  const rect = viewport.canvas.getBoundingClientRect();
  raycaster.setFromCamera(
    new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    ),
    viewport.camera,
  );

  const hits = raycaster.intersectObjects(modelObject.group.children, true);

  let pickedId: string | null = null;
  for (const hit of hits) {
    const id = modelObject.pick(hit.object);
    if (id) {
      // Kante (LineSegments) überspringen — es zählt der Mesh-Treffer.
      if (hit.object instanceof THREE.LineSegments) continue;
      pickedId = id;
      break;
    }
    // Versuch: Elternknoten (wenn GLTFLoader Mesh unter Node legt)
    const parentId = hit.object.parent ? modelObject.pick(hit.object.parent) : null;
    if (parentId) { pickedId = parentId; break; }
  }

  if (pickedId) {
    modelObject.highlight(pickedId);
    const candidate = currentCandidates?.walls.find((w) => w.global_id === pickedId) ?? null;
    panel.showWallReport(pickedId, candidate);
  } else {
    // Klick ins Leere → Selektion aufheben.
    modelObject.highlight(null);
    panel.hideWallReport();
  }
});

// --- Reiter Roboter (Issue #20): Roboterkatalog + Neubewertung ---
const robotPanel = new RobotPanel({
  /**
   * Neubewertung für den gewählten Roboter (Issue #20).
   * Ruft PUT /projects/{slug}/robot auf → neuer Befund-Lauf →
   * overview_run aktualisiert → Modellübersicht neu eingefärbt.
   */
  async onReassess(robotName) {
    if (!currentProjectSlug) {
      shell.setStatus("Kein Projekt geöffnet — zuerst ein Projekt anlegen.");
      return;
    }
    const project = await setRobot(currentProjectSlug, robotName, "default");
    currentRobot = robotName;
    currentAssessmentRun = project.overview_run;
    // Roboterwechsel → Druckplan/Simulation/Export veralten (Issue #29).
    refreshRevisions(project.print_jobs);
    panel.setCurrentRobot(robotName);
    robotPanel.setCurrentRobot(robotName);
    // Payload an ToolPanel weitergeben (Issue #21): neuer Roboter → Payload-Check aktualisieren.
    toolPanel.setRobotPayload(robotPayloadKg(robotName));
    // Aktiven Roboter für den Kompatibilitäts-Filter (Issue #74): inkompatibles
    // Zubehör ausgrauen + ggf. warnen, wenn die bestehende Wahl fremd wird.
    toolPanel.setActiveRobot(robotName);
    // Workstation-Filter am selben Roboterwechsel ausrichten (Issue #77).
    workstationPanel.setActiveRobot(robotName);
    // Roboter jetzt bekannt → Druckplan-Voraussetzung neu prüfen (Issue #22).
    updatePlacementPrecondition();
    // Modellübersicht mit neuer Eignungseinfärbung laden.
    const run = await loadFromUrl(fsUrl(project.overview_run));
    await showRun(run);
  },

  /**
   * Umschalter „Schema-Darstellung" (Issue #41) — wirkt global auf alle
   * ArmView-Instanzen (Vorschau + Replay). Default Mesh; bei Ladefehler ist der
   * Umschalter gesperrt und steht fest auf Schema (Fallback).
   */
  onArmSchemaToggled(schema) {
    setArmRenderMode(schema ? "schema" : "mesh");
  },
});

// --- M1013-Meshes des Präsentations-Arms laden (Issue #41) ---
// Einmal laden, alle ArmView-Instanzen (Vorschau + Replay) teilen sie; Default
// Mesh. Der Umschalter im Reiter Roboter spiegelt den Zustand; bei Ladefehler
// bleibt der Kapsel-Arm (Fallback), der Umschalter wird gesperrt.
onArmRenderStateChange((state) => {
  robotPanel.setArmRenderState({
    schema: effectiveMode(state) === "schema",
    enabled: toggleEnabled(state),
    failed: state.failed,
  });
  const manifest = getArmManifest();
  robotPanel.setArmAttribution(manifest ? attributionText(manifest) : null);
});
void initArmMeshes();

// Diagnose-Hook für den Headless-Smoke (#41): effektiver Render-Modus +
// Mesh-Ladezustand + Zahl der Glied-Meshes der Roboter-Vorschau.
(window as unknown as { __armDebug?: () => unknown }).__armDebug = () =>
  previewArm.debugInfo();

// Diagnose-Hook für den Headless-Smoke (#84): Fokus-Zustand + Sichtbarkeit.
// Seit #196 trivial: `focused` ist ein `focusStore.get()` — kein eigener
// Sync-Nachweis mehr nötig, der Halter ist einer.
(window as unknown as { __focusDebug?: () => unknown }).__focusDebug = () => {
  const focused = focusStore.get();
  const handle = sectionBoxes?.handles.find((h) => h.sectionId === focused);
  const mat = handle?.mesh.material as THREE.MeshStandardMaterial | undefined;
  return {
    boxes: sectionBoxes?.handles.length ?? 0,
    sectionIds: sectionBoxes?.handles.map((h) => h.sectionId) ?? [],
    focused,
    focusedOpacity: mat?.opacity ?? 0,
    wallVisible: (modelObject?.group.visible ?? false) && viewport.world.visible,
    tweenActive: cameraTween !== null,
  };
};

/** Erlaubt dem Headless-Smoke, einen Abschnitt per section_id zu fokussieren,
 *  ohne einen echten 3D-Klick simulieren zu müssen (Kamera bleibt visueller
 *  Smoke, kein Pixel-Test) — die Auswahl läuft durch dieselbe Panel-Logik. */
(window as unknown as { __focusSection?: (id: string) => void }).__focusSection = (id: string) => {
  druckplanPanel.focusSection(id);
};

// Diagnose-Hook für den Headless-Smoke (#85): Zustand der Live-Vorschau
// „Vorbereiten" — aktiv, Zahl der Schablonen-Posen, Standoff/Mindestabstand.
(window as unknown as { __prepareDebug?: () => unknown }).__prepareDebug = () =>
  preparePreview.debugInfo();

// Diagnose-Hook für den Headless-Smoke (#91): Zustand der Teile-Palette am
// 3D-Feld — sichtbar/eingeklappt und je Teil Ampel/erreichbar/Marker/Auswahl,
// direkt aus dem gerenderten DOM gelesen (belegt Ampel + Marker + Auswahl↔Fokus).
(window as unknown as { __partsPaletteDebug?: () => unknown }).__partsPaletteDebug = () => {
  const root = document.getElementById("parts-palette");
  const body = document.getElementById("parts-palette-body");
  const rows = Array.from(document.querySelectorAll<HTMLElement>("#parts-palette-list .parts-part"));
  return {
    visible: root ? !root.hidden : false,
    collapsed: body ? body.hidden : true,
    count: rows.length,
    focused: focusStore.get(),
    entries: rows.map((li) => ({
      sectionId: li.dataset.section ?? null,
      ampel: li.classList.contains("green")
        ? "green"
        : li.classList.contains("red")
          ? "red"
          : "ungeprueft",
      selected: li.classList.contains("selected"),
      marker: !(li.querySelector<HTMLElement>(".parts-part-marker")?.hidden ?? true),
    })),
  };
};

// Erlaubt dem Headless-Smoke, den ▪-Override-Marker eines Teils deterministisch
// zu setzen (echter Render-Pfad, wie __focusSection den Fokus setzt) — ohne einen
// vollen process-params-Speichervorgang zu fahren (#91).
(window as unknown as { __setSlicingOverrideMarker?: (ids: string[]) => void }).__setSlicingOverrideMarker =
  (ids: string[]) => {
    druckplanPanel.setSlicingOverrideSections(ids);
  };

// Diagnose-Hook für den Headless-Smoke (#93): Basis-Marker aller Teile + das
// echte M1013-Mesh am Fokus. `markers` soll der Teile-Anzahl entsprechen;
// `meshVisible` belegt, dass der Fokus das Mesh zeigt, `hiddenMarker` den zum
// Mesh getauschten Teil-Marker.
(window as unknown as { __placementDebug?: () => unknown }).__placementDebug = () => {
  let hiddenMarker: string | null = null;
  const positions: Record<string, [number, number, number]> = {};
  if (placementMarkers) {
    for (const [id, m] of placementMarkers.markers) {
      if (!m.visible) hiddenMarker = id;
      // Marker-Position (world) — der Smoke prüft, dass sie dem Platzierungs-
      // Override folgt (Issue #94). Auf ganze mm gerundet (stabiler Vergleich).
      positions[id] = [
        Math.round(m.position.x),
        Math.round(m.position.y),
        Math.round(m.position.z),
      ];
    }
  }
  return {
    markers: placementMarkers ? placementMarkers.markers.size : 0,
    sectionCount: druckplanPanel.getSections().length,
    sectionIds: placementMarkers ? [...placementMarkers.markers.keys()] : [],
    positions,
    meshVisible: !!placementArm && placementArm.visible,
    hiddenMarker,
    focused: focusStore.get(),
  };
};

// Diagnose-Hook für den Headless-Smoke (#96): Zustand der Druckort-Ansicht —
// Umschalter-Verfügbarkeit (nur am fokussierten Modul), aktive Ansicht,
// Hinweis (fehlende Workstation-Frames, kein Gate) und die Sichtbarkeit von
// Roboter/Modul/Workstation-Mesh bzw. der Wand-Ansicht (Rückweg).
(window as unknown as { __druckortDebug?: () => unknown }).__druckortDebug = () => ({
  available: !druckortToggleEl.hidden,
  view: druckortState.view,
  hint: druckortHintEl.hidden ? null : druckortHintEl.textContent,
  robotVisible: druckortGroup.visible && !!druckortArm && druckortArm.visible,
  moduleVisible: druckortGroup.visible && druckortModule !== null,
  wsMeshVisible: druckortGroup.visible && druckortWsMesh !== null,
  worldVisible: viewport.world.visible,
});

// --- Endeffektor-Panel (Issue #21): Katalog-Dropdown + Payload-Check ---
const toolPanel = new ToolPanel({
  /**
   * Endeffektor-Wahl im Druckjob persistieren (Issue #21).
   * PUT /projects/{slug}/tool → Payload-Befund zurück (kein Gate, nur Warnung).
   */
  async onSaveTool(toolName) {
    if (!currentProjectSlug) {
      shell.setStatus("Kein Projekt geöffnet — zuerst ein Projekt anlegen.");
      return { payload_ok: null, payload_margin_kg: null };
    }
    const result = await setTool(currentProjectSlug, toolName, "default");
    currentTool = toolName;
    toolPanel.setCurrentTool(toolName);
    // Roboter-Vorschau nachziehen (Issue #31): der Nutzer steht beim Speichern
    // typischerweise im Reiter Roboter und sieht den Wechsel sofort.
    updateRobotPreviewTool();
    // Auch der Flansch eines aktiven Replay-Arms trägt sonst das alte Mesh
    // weiter, bis ein neuer Lauf geladen wird (Issue #49).
    if (armView) {
      armView.clearFlange();
      attachToolMeshToArm(armView);
    }
    // Endeffektorwechsel → Druckplan/Simulation/Export veralten (Issue #29).
    refreshRevisions(result.print_jobs);
    return { payload_ok: result.payload_ok, payload_margin_kg: result.payload_margin_kg };
  },

  /** Dropdown-Wechsel (noch nicht gespeichert): Vorschau live nachziehen (Issue #31/#49). */
  onSelectionChanged(toolName) {
    previewSelectedTool = toolName;
    updateRobotPreviewTool();
  },
});

// --- Workstation-Panel (Issue #77, PRD #69): Aufstell-Umgebung-Wahl am Druckjob ---
// Mirror des Endeffektor-Panels: Katalog-Dropdown + Kompatibilitäts-Ausgrauen/-Warnung.
// WICHTIG: kein refreshRevisions nach dem Speichern — ein Workstation-Wechsel veraltet
// bewusst KEINE Outputs (Druckplan/Simulation/Export). Die Workstation-Werte konsumiert
// erst der Druckplan-Automatismus (#70). Das ist der Seam zu PRD B (#70).
const workstationPanel = new WorkstationPanel({
  async onSaveWorkstation(name) {
    if (!currentProjectSlug) {
      shell.setStatus("Kein Projekt geöffnet — zuerst ein Projekt anlegen.");
      return { compatible: null };
    }
    const result = await setWorkstation(currentProjectSlug, name, "default");
    currentWorkstation = name;
    workstationPanel.setCurrentWorkstation(name);
    // Art „modul" braucht eine Workstation als Druckort (Issue #95, ADR-022):
    // den freundlichen Hinweis nachziehen (kein Gate).
    druckplanPanel.setWorkstationPresent(!!name);
    // BEWUSST kein refreshRevisions(result.print_jobs): Workstation-Wechsel veraltet
    // nichts (Seam zu #70) — anders als set_tool/set_robot.
    return { compatible: result.compatible };
  },
});

// --- Roboter-Schritt: Sticky-Footer „Speichern" (UI-Redesign Scheibe 8, #105) ---
// Eine sichtbare Speichern-Aktion für den ganzen Schritt. Sie leitet an die
// bestehenden, weiterhin verdrahteten (aber verborgenen) Sektions-Buttons weiter:
// deren Aktiv-Zustand gattert jeden Aufruf (ein disabled Button feuert kein
// click), sodass Endeffektor- und Workstation-Persistenz byte-gleich bleiben —
// jeweils ihr eigener Core-Endpoint mit eigener Veraltungs-Semantik (kein Umbau).
const robotStepSaveBtn = document.getElementById("robot-step-save-btn");
robotStepSaveBtn?.addEventListener("click", () => {
  (document.getElementById("tool-save-btn") as HTMLButtonElement | null)?.click();
  (document.getElementById("wsc-save-btn") as HTMLButtonElement | null)?.click();
});

// --- Bibliothek (Issue #28/#56): Endeffektor-Galerie + Konfigurator ---

// Vorschaubild-Cache (Issue #56, Modul 2): Key = mesh_path, In-Memory +
// localStorage; beim erneuten Öffnen des Reiters sofort da (US 22).
const thumbnailCache = new ThumbnailCache(
  typeof localStorage !== "undefined" ? localStorage : undefined,
);

/**
 * Vorschaubild eines Endeffektors (dataURL) oder null (Platzhalter, US 21/23).
 * Cache-Treffer resolved sofort; ein Miss lädt das Mesh (mesh_path → /@fs/) und
 * rendert ein Standbild. Fehler (kein Mesh, GL) → null, die Karte zeigt einen
 * Platzhalter statt abzustürzen.
 */
async function thumbnailForTool(tool: ToolDef): Promise<string | null> {
  if (!tool.mesh_path || !tool.mesh) return null;
  const meshPath = tool.mesh_path;
  return thumbnailCache.getOrCompute(meshPath, async () => {
    const mesh = await loadToolMesh(fsUrl(meshPath), tool.mesh as string);
    return renderMeshThumbnail(mesh);
  });
}

/** Katalog + Reiter-Roboter-Dropdown nach Anlegen/Bearbeiten/Löschen auffrischen (US 20). */
async function refreshToolCatalog(): Promise<void> {
  try {
    loadedTools = await listTools();
    toolPanel.setTools(loadedTools);
    toolPanel.setCurrentTool(currentTool);
  } catch {
    /* best effort — der Endeffektor liegt trotzdem ab. */
  }
}

const configurator = new ToolConfigurator({
  /**
   * Endeffektor aus dem Konfigurator anlegen (POST /tools). Nach Erfolg den
   * Katalog neu laden, damit der neue Endeffektor sofort (ohne Neustart) im
   * Reiter Roboter wählbar ist — die aktuelle Auswahl bleibt erhalten.
   */
  async onCreateTool(req) {
    const tool = await createTool(req);
    await refreshToolCatalog();
    return tool;
  },

  /**
   * Endeffektor bearbeiten (PUT /tools/{name}, Issue #56). Das ersetzte Mesh
   * invalidiert das Vorschaubild (mesh_path evtl. gleich, Inhalt neu), danach
   * Katalog + Dropdown auffrischen.
   */
  async onUpdateTool(name, req) {
    const tool = await updateTool(name, req);
    if (tool.mesh_path) thumbnailCache.invalidate(tool.mesh_path);
    await refreshToolCatalog();
    return tool;
  },

  /** Nach dem Speichern (Anlegen ODER Bearbeiten) zurück in die Galerie (US 16). */
  onSaved() {
    void toolLibrary.openGallery();
  },
});

const toolLibrary = new ToolLibrary({
  loadTools: () => listTools(),
  onNew() {
    configurator.openCreate();
  },
  onEdit(tool) {
    toolLibrary.showEditor();
    void configurator.openEdit(tool);
  },
  async onDelete(name) {
    const removed = loadedTools.find((t) => t.name === name);
    await deleteTool(name);
    if (removed?.mesh_path) thumbnailCache.invalidate(removed.mesh_path);
    // Gelöschter Endeffektor darf nicht mehr als aktuelle Wahl gelten.
    if (currentTool === name) currentTool = null;
    await refreshToolCatalog();
  },
  thumbnailFor: thumbnailForTool,
});

// „Zurück zur Übersicht" im Editor → Galerie (ohne Speichern). Optional verdrahtet,
// damit ein fehlender Button (Altstand) den Start nicht abbricht.
document
  .getElementById("lib-back-btn")
  ?.addEventListener("click", () => void toolLibrary.openGallery());

// --- Bibliothek-Rubrik Workstation (Issue #75): Galerie + Formular-Editor ---
/**
 * Workstation-Katalog + Reiter-Roboter-Dropdown nach Anlegen/Bearbeiten/Löschen
 * auffrischen (Issue #77) — mirror von refreshToolCatalog: eine in der Bibliothek
 * geänderte Workstation ist im Reiter Roboter sofort wählbar (ohne Neustart).
 */
async function refreshWorkstationCatalog(): Promise<void> {
  try {
    loadedWorkstations = await listWorkstations();
    workstationPanel.setWorkstations(loadedWorkstations);
    workstationPanel.setActiveRobot(currentRobot);
    workstationPanel.setCurrentWorkstation(currentWorkstation);
  } catch {
    /* best effort — die Workstation liegt trotzdem ab. */
  }
}

// 3D-Editor der Workstation-Bibliothek (Mesh + Roboter-Platzierung, Issue #78).
// Injiziert in die Bibliothek; die Bohrbild-Erkennung ruft die Core-API.
const workstationScene = new WorkstationScene({
  onDetect: (name, robot) => detectBaseHoles(name, robot),
});

const workstationLibrary = new WorkstationLibrary(
  {
    loadWorkstations: () => listWorkstations(),
    async onCreate(req) {
      const ws = await createWorkstation(req);
      await refreshWorkstationCatalog();
      return ws;
    },
    async onUpdate(name, req) {
      const ws = await updateWorkstation(name, req);
      await refreshWorkstationCatalog();
      return ws;
    },
    async onDelete(name) {
      await deleteWorkstation(name);
      await refreshWorkstationCatalog();
    },
  },
  workstationScene,
);

document
  .getElementById("ws-back-btn")
  ?.addEventListener("click", () => void workstationLibrary.openGallery());

// --- Bibliothek-Rubrik Roboter (Issue #76): schreibgeschützte Galerie ---
// Read-only: nur GET /robots, kein Schreibpfad (Kinematik hart verdrahtet, #69).
const robotLibrary = new RobotLibrary({
  loadRobots: () => listRobots(),
});

// Rubriken-Umschaltung Roboter / Endeffektor / Workstation (nur .hidden, #75).
const libraryRubrics = new LibraryRubrics({
  onRubricChanged(id) {
    if (id === "endeffektor") void toolLibrary.openGallery();
    else if (id === "workstation") void workstationLibrary.openGallery();
    else if (id === "roboter") void robotLibrary.openGallery();
  },
});

// Druckplan-Split (UI-Redesign Scheibe 4, Issue #106): die frühere Rubriken-
// Umschaltung „Zerlegung & Platzierung" ↔ „Slicing" (#89) entfällt. „Zerlegung"
// ist ein eigener Reiter (Inspector mit Accordions); der Reiter „Druckplan"
// behält übergangsweise nur die Slicing-Rubrik + den Simulieren-Bereich (die
// Slicing-Sicht steht jetzt direkt sichtbar, kein Umschalter). #107 löst sie.

// --- Reiter Zerlegung (Issue #106) / früher Druckplan-Platzierung (#22) ---
// Der Panel steuert weiterhin dieselben Element-Ids (dokument-globales byId) —
// sie leben jetzt im Zerlegungs-Inspector statt in der Druckplan-Rubrik.
const druckplanPanel = new DruckplanPanel(focusStore, {
  /**
   * Aufstell-Toggle umgeschaltet (Issue #81): den Zustand über die Core-Route
   * persistieren (PUT /projects/{slug}/stand-mode) und die Neubewertung anstoßen.
   * Der Core leitet aus dem Toggle den Podesthöhen-Satz und damit die Höhenteilung
   * ab; ein frischer Zerlegungsvorschlag (proposeDecomposition) liefert Schnitte +
   * Abschnitte zurück ans Panel (ADR-007) und versorgt Simulation/Export.
   */
  async onStandModeChange(mode) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const persisted = await setStandMode(currentProjectSlug, mode, "default");
    // Übernahme-Protokoll (#193) auch für den Persistenz-Schritt (Marker/Badges
    // idempotent — setStandMode veraltet keine Outputs).
    const persistedJob = adoptJobResponse(jobAdoptPorts, persisted);
    // Ohne Roboter/Wand ist keine Zerlegung berechenbar — dann nur persistieren.
    if (!persistedJob?.robot || !persistedJob?.wall_global_id) return null;
    const result = await proposeDecomposition(currentProjectSlug, "abschnitt", "default");
    currentCuts = result.cuts;
    updateCutPlanes();
    // Übernahme-Protokoll (#193): Job + voller setSections-Fanout (inkl. der vor
    // #193 fehlenden Prozessparameter-Teilformulare) + ▪-Marker + Badges; die
    // Zerlegungs-Ansicht wendet die Antwort selbst an (Rückgabewert).
    adoptJobResponse(jobAdoptPorts, result, { sections: result.sections, druckplan: "panel-owns" });
    druckplanPanel.setPruefScope(result.pruef_scope); // Umfangsansage (Issue #175)
    return { cuts: result.cuts, sections: result.sections, freigang: result.freigang };
  },

  /**
   * Gebäudekontext-Schalter umgeschaltet (Issue #131): über die Core-Route
   * `PUT /projects/{slug}/context-check` persistieren. Der Schalter ändert keinen
   * Zerlegungsplan — er wirkt erst bei der nächsten Simulation; darum kein
   * Re-Decompose, nur den aktiven Job aktualisieren (ADR-007/016).
   */
  async onContextCheckChange(enabled) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const persisted = await setContextCheck(currentProjectSlug, enabled, "default");
    adoptJobResponse(jobAdoptPorts, persisted); // Übernahme-Protokoll (#193), ohne Teile
  },

  /**
   * Zerlegungsvorschlag berechnen (POST /projects/{slug}/decomposition, Issue #24):
   * Core schlägt eine Zerlegung in erreichbare Abschnitte vor. Die Schnittebenen
   * landen im Druckjob (Plan-Eingaben) und werden in der 3D-Ansicht gezeigt; die
   * Abschnitte (mit Ampel + Platzierung) gehen an das Panel zurück. Read-only.
   */
  async onDecompose(kind) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const result = await proposeDecomposition(currentProjectSlug, kind, "default");
    currentCuts = result.cuts;
    updateCutPlanes();
    // Übernahme-Protokoll (#193): Job + voller setSections-Fanout (Simulation/
    // Export #26/#29, Prozessparameter-Teilformulare, Platzierungsfelder #94) +
    // ▪-Marker + Badges; die Zerlegungs-Ansicht wendet die Antwort selbst an
    // (Rückgabewert). Schnittplan neu → Simulation/Export veralten.
    adoptJobResponse(jobAdoptPorts, result, { sections: result.sections, druckplan: "panel-owns" });
    // Gemerkte Kollisionsbefunde je Teil leeren (Issue #182): section_ids sind
    // ordnungsbasiert und können sich in der neuen Zerlegung wiederholen — ein
    // alter Befund darf nicht an einem neuen Teil kleben bleiben. Neue Läufe
    // füllen die Badges bei der nächsten Simulation wieder (wie beim Projekt-Öffnen).
    collisionFindings.clear();
    druckplanPanel.setCollisionFindings(clearedCollisionFindings());
    druckplanPanel.setPruefScope(result.pruef_scope); // Umfangsansage (Issue #175)
    return { cuts: result.cuts, sections: result.sections, freigang: result.freigang };
  },

  /**
   * Manuell editierten Schnittplan neu bewerten („Prüfen", Issue #25). Ruft
   * denselben Endpoint wie onDecompose, aber MIT den Plan-Eingaben (Schnitte,
   * Fugen-Versatz, Overrides) — die UI rechnet nie selbst (ADR-007). Der Core
   * baut die Abschnittsgeometrie (from_cuts) + Ampel, legt sie als Lauf ab und
   * liefert die frischen Abschnitte + den tatsächlich verwendeten Fugen-Versatz
   * zurück ans Panel.
   */
  async onCheckCutPlan(kind, cuts, jointOffsetMm, sectionOverrides) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const result = await proposeDecomposition(currentProjectSlug, kind, "default", {
      cuts,
      jointOffsetMm,
      sectionOverrides,
    });
    // KEINE Nebenwirkungen hier (Issue #45): ob die Antwort gilt, entscheidet
    // das Panel (Generation-Guard). Erst onCheckApplied wendet sie an —
    // verworfene stale Antworten erreichen Simulation/Export/3D nie.
    lastCheckResult = result;
    return {
      cuts: result.cuts,
      jointOffsetMm: result.joint_offset_mm,
      sections: result.sections,
      freigang: result.freigang,
    };
  },

  /** Prüf-Antwort wurde vom Panel übernommen (nicht stale, Issue #45). */
  onCheckApplied() {
    if (!lastCheckResult) return;
    // Cuts/3D laufen bereits über onCutsChanged. Übernahme-Protokoll (#193):
    // Job + voller setSections-Fanout + ▪-Marker + Badges (Schnittplan geändert
    // → Simulation/Export veralten); die Zerlegungs-Ansicht hat die Antwort
    // selbst angewandt (Generation-Guard #45).
    adoptJobResponse(jobAdoptPorts, lastCheckResult, {
      sections: lastCheckResult.sections,
      druckplan: "panel-owns",
    });
    druckplanPanel.setPruefScope(lastCheckResult.pruef_scope); // Umfangsansage (Issue #175)
    lastCheckResult = null;
  },

  /**
   * Synchron bei jeder Schnitt-Änderung (Zahlenfeld / Hinzufügen / Entfernen /
   * Neubewertung): die Schnittebenen in der 3D-Ansicht sofort nachziehen —
   * reine Darstellungsmathematik (ADR-007), kein Core-Aufruf. Das Draggen
   * bewegt das Mesh direkt und committet erst am Drag-Ende (siehe unten), daher
   * ruft `setCutPosition` diesen Rückruf bewusst NICHT.
   */
  onCutsChanged(cuts) {
    currentCuts = cuts;
    updateCutPlanes();
    // Klickbare Abschnitts-Quader an den frischen Abschnittssatz anpassen (Issue #84).
    updateSectionBoxes();
  },

  /**
   * Zerlegungsart umgeschaltet (Issue #95, ADR-022): das Panel hat die
   * Artwechsel-Regeln bereits auf seinen Zustand angewendet (Schnitte behalten,
   * Platzierungs-Overrides verworfen, dirty) und stößt den debouncten Re-Check
   * an — jener persistiert Art + geräumte Overrides über `proposeDecomposition`
   * (die eine Schreibstelle, ADR-016). Hier nur eine Diagnose-Notiz; die 3D-
   * Beschriftungen ziehen mit den Abschnitten der Prüf-Antwort nach.
   */
  onArtChanged(art) {
    /* Persistenz + 3D-Beschriftungen laufen über den Re-Check (proposeDecomposition). */
    // Simulieren-Knöpfe folgen der Art sofort (Issue #97): „Fokus-Modul" + „Alle
    // Module" bei Modulen, sonst „Fokus-Abschnitt" + „Ganze Wand".
    simulationPanel.setKind(art);
    // Druckort-Ansicht (Issue #96): der Umschalter existiert nur bei Art
    // „modul" — ein Artwechsel gleicht Ansicht + Sichtbarkeit sofort ab.
    syncDruckort();
  },

  /**
   * Optionale Modul-Obergrenzen geändert (Issue #90/#95): über die #90-Route
   * `PUT …/module-limits` persistieren (einzige Schreibstelle `fgc.project`,
   * ADR-016). Wie setStandMode/setWorkstation veraltet der Aufruf **keine**
   * Outputs; die Neubewertung (Gewicht/Grenzen-Befund je Teil) stößt das Panel
   * debounced an.
   */
  async onModuleLimitsChange(maxLengthMm, maxHeightMm) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const result = await setModuleLimits(currentProjectSlug, maxLengthMm, maxHeightMm, "default");
    adoptJobResponse(jobAdoptPorts, result); // Übernahme-Protokoll (#193), ohne Teile
  },

  /**
   * Stufe-2-Prüf-Tür anstoßen (Issue #175): startet den Hintergrundlauf und poll't
   * ihn (Fortschritt/Abbruch über das Panel). Bei `done` übernimmt es die frischen
   * Abschnitte (mit echtem Druckbarkeits-Urteil) — sonst bleibt der Stand „ungeprüft".
   */
  onStartPruef(scope, focusSectionId) {
    if (!currentProjectSlug) return;
    void startPruefCheck(currentProjectSlug, scope === "focus" ? focusSectionId : null);
  },

  /** Laufenden Hintergrund-Prüflauf abbrechen (Issue #175). */
  onCancelPruef() {
    void cancelPruefCheck();
  },

  /**
   * Beam-Zerlegungslauf anstoßen (Issue #221, Folge #217): startet den Hintergrundlauf
   * und poll't ihn (Fortschritt in Prüf-Tür-Aufrufen, Abbruch über das Panel). Bei
   * `done` übernimmt es den Sieger-Schnittplan (frische Abschnitte) und speist den
   * Such-Ausweis (Verworfen-Gründe/Relaxation) über den bestehenden refinement-state.
   */
  onStartBeam() {
    if (!currentProjectSlug) return;
    void startBeamRun(currentProjectSlug);
  },

  /** Laufenden Beam-Zerlegungslauf abbrechen (Issue #221). */
  onCancelBeam() {
    void cancelBeamRun();
  },

  /**
   * Kollisions-Ampel je Platzierungsvorschlag (Issue #231, ADR-026 Punkt 2):
   * fragt den bestehenden Optimalvorschlag rein lesend ab
   * (POST …/placement-suggestion, Issue #23/#80) — der Core liefert je
   * Kandidat die fertig gerechnete Kollisions-Einstufung (Issue #228) und den
   * Gesamt-Befund `feasibility`. Keine Auswahl/Persistenz, keine Neubewertung
   * anderer Panels — reine Vorschau.
   */
  async onCheckPlacementSuggestion(): Promise<PlacementSuggestionResult> {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    return suggestPlacement(currentProjectSlug);
  },
});

// --- Stufe-2-Prüf-Tür: Hintergrundlauf starten, poll'en, abbrechen (Issue #175) ---
// Ein aktiver Prüflauf je Zeit (der Registry löst ältere Läufe desselben Jobs ab).
let activePruefCheckId: string | null = null;
let pruefPollTimer: number | null = null;

/** Startet den Prüflauf und beginnt zu poll'en (setzt einen laufenden ab). */
async function startPruefCheck(slug: string, focusSectionId: string | null): Promise<void> {
  cancelPruefPoll();
  try {
    const started = await startDecompositionCheck(slug, "default", focusSectionId);
    activePruefCheckId = started.check_id;
    druckplanPanel.setCheckStatus(started);
    schedulePruefPoll(slug, started.check_id);
  } catch (err) {
    console.error("Prüf-Tür-Anstoß fehlgeschlagen", err);
    druckplanPanel.setCheckStatus({
      check_id: "", slug, job_id: "default", scope: focusSectionId ? "focus" : "global",
      state: "error", n_total: 0, n_done: 0, n_computed: 0, n_cached: 0,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

function schedulePruefPoll(slug: string, checkId: string): void {
  pruefPollTimer = window.setTimeout(() => void pollPruefCheck(slug, checkId), 800);
}

function cancelPruefPoll(): void {
  if (pruefPollTimer !== null) {
    window.clearTimeout(pruefPollTimer);
    pruefPollTimer = null;
  }
}

/** Ein Poll-Schritt: Status holen, anzeigen; bei Abschluss die Abschnitte übernehmen. */
async function pollPruefCheck(slug: string, checkId: string): Promise<void> {
  if (activePruefCheckId !== checkId) return; // ein neuer Lauf hat übernommen
  let status: DecompositionCheckStatus;
  try {
    status = await getDecompositionCheck(slug, checkId);
  } catch {
    // Lauf abgeräumt/unbekannt (404) — poll'en einstellen.
    activePruefCheckId = null;
    return;
  }
  druckplanPanel.setCheckStatus(status);
  if (status.state === "running") {
    schedulePruefPoll(slug, checkId);
    return;
  }
  // Terminal: bei „done" die frischen Abschnitte + Revisionen übernehmen (ADR-007).
  activePruefCheckId = null;
  if (status.state === "done" && status.sections && status.print_jobs) {
    // Übernahme-Protokoll (#193): Job + voller setSections-Fanout + ▪-Marker +
    // Badges (last_pruef). Vor #193 fehlten hier die Prozessparameter-
    // Teilformulare des Fanouts (Divergenz = Bug, #161-Familie).
    adoptJobResponse(jobAdoptPorts, { print_jobs: status.print_jobs }, {
      sections: status.sections,
      druckplan: { kind: druckplanPanel.getKind() },
    });
  }
}

/** Bricht den laufenden Prüflauf ab (Issue #175, AC-Zusatz). */
async function cancelPruefCheck(): Promise<void> {
  const id = activePruefCheckId;
  if (!id || !currentProjectSlug) return;
  cancelPruefPoll();
  try {
    const status = await cancelDecompositionCheck(currentProjectSlug, id);
    druckplanPanel.setCheckStatus(status);
  } catch {
    /* Lauf schon weg — ignorieren */
  }
  activePruefCheckId = null;
}

// --- Beam-Zerlegungslauf: Hintergrundlauf starten, poll'en, abbrechen (Issue #221) ---
// Ein aktiver Beam-Lauf je Zeit (der Core-Registry löst ältere Läufe desselben Jobs ab).
let activeBeamId: string | null = null;
let beamPollTimer: number | null = null;

/** Startet den Beam-Lauf und beginnt zu poll'en (setzt einen laufenden ab). */
async function startBeamRun(slug: string): Promise<void> {
  cancelBeamPoll();
  try {
    const started = await startBeamPropose(slug, "default");
    activeBeamId = started.beam_id;
    druckplanPanel.setBeamStatus(started);
    scheduleBeamPoll(slug, started.beam_id);
  } catch (err) {
    console.error("Beam-Anstoß fehlgeschlagen", err);
    druckplanPanel.setBeamStatus({
      beam_id: "", slug, job_id: "default", state: "error", n_total: 0, n_done: 0,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

function scheduleBeamPoll(slug: string, beamId: string): void {
  // Beam-Läufe zählen Prüf-Tür-Aufrufe (sekundengenaue Schritte sind hier zu fein) —
  // ein etwas ruhigeres Intervall als bei der Prüf-Tür genügt.
  beamPollTimer = window.setTimeout(() => void pollBeamRun(slug, beamId), 1000);
}

function cancelBeamPoll(): void {
  if (beamPollTimer !== null) {
    window.clearTimeout(beamPollTimer);
    beamPollTimer = null;
  }
}

/** Ein Poll-Schritt: Status holen, anzeigen; bei „done" Sieger + Ausweis übernehmen. */
async function pollBeamRun(slug: string, beamId: string): Promise<void> {
  if (activeBeamId !== beamId) return; // ein neuer Lauf hat übernommen
  let status: BeamProposeStatus;
  try {
    status = await getBeamPropose(slug, beamId);
  } catch {
    // Lauf abgeräumt/unbekannt (404) — poll'en einstellen.
    activeBeamId = null;
    return;
  }
  druckplanPanel.setBeamStatus(status);
  if (status.state === "running") {
    scheduleBeamPoll(slug, beamId);
    return;
  }
  // Terminal: bei „done" den Sieger-Schnittplan übernehmen (wie die Prüf-Tür, ADR-007)
  // und den Such-Ausweis (Verworfen-Gründe/Relaxation) in den refinement-state speisen.
  activeBeamId = null;
  druckplanPanel.setRefinement(status.refinement);
  if (status.state === "done" && status.sections && status.print_jobs) {
    adoptJobResponse(jobAdoptPorts, { print_jobs: status.print_jobs }, {
      sections: status.sections,
      druckplan: { kind: druckplanPanel.getKind() },
    });
    // Schnittebenen des Siegers in die 3D-Ansicht nachziehen (Darstellungsmathematik).
    currentCuts = druckplanPanel.getCuts();
    updateCutPlanes();
    updateSectionBoxes();
  }
}

/** Bricht den laufenden Beam-Lauf ab (Issue #221). */
async function cancelBeamRun(): Promise<void> {
  const id = activeBeamId;
  if (!id || !currentProjectSlug) return;
  cancelBeamPoll();
  try {
    const status = await cancelBeamPropose(currentProjectSlug, id);
    druckplanPanel.setBeamStatus(status);
  } catch {
    /* Lauf schon weg — ignorieren */
  }
  activeBeamId = null;
}

// --- Prozessparameter (Scheibe 2, Issue #59) — seit dem Gilt-für-Umschalter
// (Issue #92) scope-fähig: dieselben Formulare gelten global ODER für das
// gewählte Teil (feldweise Overrides, #82-Mechanik) ---
const processParamsPanel = new ProcessParamsPanel({
  /**
   * Slice-Basisparameter im Druckjob persistieren (PUT …/process-params). Der
   * Core schreibt den process_params.slice-Block (einzige Schreibstelle, ADR-016)
   * und bumpt die Prozessparameter-Revision → Zerlegung/Simulation/Export veralten.
   */
  async onSave(slice, orientation, ikConfig) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const project = await setProcessParams(
      currentProjectSlug, slice, orientation, "default", undefined, ikConfig,
    );
    // Übernahme-Protokoll (#193) mit benannter Option restore: die Teil-
    // Platzhalter (geerbte Werte) ziehen an die neuen globalen Werte (#82/#92);
    // veraltet-Badges nachziehen (Issue #59/#61).
    adoptJobResponse(jobAdoptPorts, project, { restore: "process-params" });
    updateSlicingScopeNote();
  },
  /**
   * Teil-Overrides persistieren (Issue #92; PUT …/process-params, Feld `sections` —
   * dieselbe #82-Route). Die globalen slice/orientation-Werte werden unverändert
   * mitgesendet (idempotent), damit sie nicht verloren gehen; der Core schreibt den
   * process_params.sections-Block (einzige Schreibstelle, ADR-016) und bumpt NUR
   * die Zähler der geänderten Teile (#83 — nur diese veralten).
   */
  async onSaveSections(sections) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const slice = currentActiveJob?.process_params?.slice ?? {};
    const orientation = currentActiveJob?.process_params?.orientation ?? {};
    // Globales ik_config (#129) unverändert mitsenden (idempotent), damit die
    // Abschnitts-Speicherung es nicht verwirft (wie slice/orientation).
    const ikConfig = currentActiveJob?.process_params?.ik_config ?? {};
    const project = await setProcessParams(
      currentProjectSlug, slice, orientation, "default", sections, ikConfig,
    );
    // Übernahme-Protokoll (#193): Job + ▪-Marker (#91) + Badges. BEWUSST ohne
    // restore-Option: ein restoreFromJob würde hier ungespeicherte Eingaben des
    // jeweils anderen Scopes (gestashte Formulare, #92) verwerfen.
    adoptJobResponse(jobAdoptPorts, project);
    updateSlicingScopeNote();
  },
  // Reglerziehen: Fokus-Abschnitts-Bahn sofort neu slicen (Live-Vorschau, #85) —
  // im Teil-Scope aus global ⊕ live Override (updatePreparePreview löst selbst auf).
  onLiveChange() {
    updatePreparePreview();
    updateSlicingScopeNote();
  },
});

// --- Freie Platzierungs-Overrides je Teil (Druckplan-Neuordnung II S5,
// Issue #94, PRD #88) ---
// Drei Felder (seitlich/Abstand/Aufstellhöhe) im Teil-Scope des Gilt-für-
// Umschalters: leer = automatische Platzierung; jede Änderung persistiert über
// die dünne Core-Route (PUT …/placement-override, einzige Schreibstelle
// fgc.project) und stößt die Neubewertung an — nur dieses Teil veraltet (#83).
const placementOverridePanel = new PlacementOverridePanel(focusStore, {
  async onSaveOverride(sectionId, values) {
    // Ein Fluss, ein Vertrag (#193): exakt dieselbe getestete Sequenz wie die
    // Advisor-Anwenden-Flüsse (PUT → Übernahme-Protokoll mit restore:
    // "placement" + Neubewertung #172). Beseitigt die Reihenfolge-Divergenz
    // der früheren Hand-Sequenz (▪-Marker VOR dem Formular-Restore).
    await applyPlacementOverride(placementApplyPorts, sectionId, values);
  },
});

// --- Gilt-für-Umschalter Global↔Teil (Issue #92, PRD #88) ---
// Erscheint im Reiter Druckplan (Slicing), sobald ein Teil gewählt (fokussiert)
// ist: schaltet die Slicing-Formulare auf das Teil um (feldweise Overrides).
// Seit dem Druckplan-Split (#106) betrifft er NUR noch die Slicing-Formulare —
// die strukturellen Gruppen (Zerlegungsart/Aufstellung/Schnittplan) und die
// Platzierungsfelder leben im eigenen Reiter Zerlegung OHNE Scope (Platzierung
// ist dort fokus-getrieben, siehe FOCUS_EFFECT_ORDER/#196). #107 verschiebt den
// Umschalter endgültig in den Slicing-Schritt.
const scopeSwitch = new ScopeSwitch(focusStore, {
  // Nur noch Radio-Klicks (Issue #196): fokus-getriebene Scope-Wechsel laufen
  // als Kaskaden-Mitglied `syncProcessParamsScope` (FOCUS_EFFECT_ORDER).
  onScopeChanged(scope, sectionId) {
    processParamsPanel.setScope(scope, sectionId);
    updateSlicingScopeNote();
  },
});

/**
 * Kopf-Notiz des Prozessparameter-Accordions (Slicing, #107): im Teil-Scope
 * „N Override(s)", sonst „gilt global". Rein darstellend — die Zahl kommt aus
 * dem unveränderten ProcessParamsPanel (`overrideCount`). Aufgerufen bei jedem
 * Scope-Wechsel, jeder Feld-Eingabe (Live) und nach jedem Speichern/Neuladen.
 */
function updateSlicingScopeNote(): void {
  const el = document.getElementById("slicing-prozess-scope");
  if (!el) return;
  if (scopeSwitch.scope === "teil") {
    const n = processParamsPanel.overrideCount();
    el.textContent = n === 1 ? "1 Override" : `${n} Overrides`;
    el.classList.toggle("has-overrides", n > 0);
  } else {
    el.textContent = "gilt global";
    el.classList.remove("has-overrides");
  }
}

/**
 * Dünne DOM-Verdrahtung eines Slicing-Accordions (#107): Klick kippt den
 * Aufklapp-Zustand (▸/▾ + `.hidden`), je Gruppe in localStorage persistiert —
 * dasselbe Muster wie die Zerlegungs-Accordions (#106), hier ohne eigene Klasse.
 * Die Fortgeschritten-Gruppe hat ihr eigenes Toggle (ProcessParamsPanel) und
 * wird hier NICHT verdrahtet.
 */
function wireSlicingAccordion(
  toggleId: string,
  bodyId: string,
  key: string,
  defaultExpanded: boolean,
): void {
  const toggle = document.getElementById(toggleId);
  const body = document.getElementById(bodyId);
  if (!toggle || !body) return;
  const storageKey = `fgc.slicing.acc.${key}`;
  let expanded = defaultExpanded;
  try {
    const v = localStorage.getItem(storageKey);
    if (v !== null) expanded = v !== "0";
  } catch {
    /* localStorage nicht verfügbar (private mode) — Default nutzen. */
  }
  const marker = toggle.querySelector<HTMLElement>(".acc-marker");
  const render = (): void => {
    body.hidden = !expanded;
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (marker) marker.textContent = expanded ? "▾" : "▸";
  };
  toggle.addEventListener("click", () => {
    expanded = !expanded;
    try {
      localStorage.setItem(storageKey, expanded ? "1" : "0");
    } catch {
      /* nicht persistieren, kein Fehler. */
    }
    render();
  });
  render();
}

// Slicing-Accordions Prozessparameter + Singularitäts-Advisor verdrahten (#107);
// beide per Default aufgeklappt. „Fortgeschritten" gehört ProcessParamsPanel.
wireSlicingAccordion("slicing-acc-prozess-toggle", "slicing-acc-prozess-body", "prozess", true);
wireSlicingAccordion("slicing-acc-advisor-toggle", "slicing-acc-advisor-body", "advisor", true);
// Kollisions-Advisor (Kollisionskontrolle S5, #130): eigenes Accordion, default zu
// (teuer — läuft erst auf Knopfdruck). Bleibt global wie der Singularitäts-Advisor.
wireSlicingAccordion("slicing-acc-collision-advisor-toggle", "slicing-acc-collision-advisor-body", "collision-advisor", false);
// IK-Konfiguration (Kollisionskontrolle S4, #129): eigenes Accordion, default zu.
wireSlicingAccordion("slicing-acc-ikconfig-toggle", "slicing-acc-ikconfig-body", "ikconfig", false);
updateSlicingScopeNote();

// Diagnose-Hook für den Headless-Smoke (#92): Zustand des Gilt-für-Umschalters
// + Vererbungsanzeige eines Referenzfeldes (Slicing), aus dem echten DOM.
(window as unknown as { __scopeDebug?: () => unknown }).__scopeDebug = () => {
  const layer = document.getElementById("process-params-layer-height") as HTMLInputElement | null;
  return {
    visible: !(document.getElementById("scope-switch")?.hidden ?? true),
    scope: scopeSwitch.scope,
    sectionId: scopeSwitch.sectionId,
    advisorDisabled: (document.getElementById("singularity-advisor-check-btn") as HTMLButtonElement | null)?.disabled ?? null,
    layerDisabled: layer?.disabled ?? null,
    layerPlaceholder: layer?.placeholder ?? null,
    layerOverridden: layer?.classList.contains("section-param-override") ?? null,
    layerResetVisible: !(document.getElementById("process-params-layer-height-reset")?.hidden ?? true),
  };
};

// Diagnose-Hook für den Headless-Smoke (#92/#83): die Revisionsstände des
// aktiven Druckjobs — belegt, dass ein Teil-Override nur dieses Teil veraltet.
(window as unknown as { __revisionsDebug?: () => unknown }).__revisionsDebug = () =>
  currentActiveJob?.revisions ?? null;

// Ports des Übernahme-Protokolls (Issue #193, Glossar viewer/CONTEXT.md): die
// getestete Nachzieh-Sequenz nach jeder Core-Antwort mit frischen `print_jobs`
// (Job übernehmen → setSections-Fanout → ▪-Marker → veraltet-Badges → ggf.
// Restore/Neubewertung) lebt in `ui/job-adopt.ts`; hier stehen nur die echten
// Effekte. ALLE Flüsse laufen über dieselben Ports — Protokoll-Parität per
// Konstruktion statt per Copy-Paste (#161-Familie).
const jobAdoptPorts: JobAdoptPorts = {
  adoptActiveJob(job) {
    currentActiveJob = job;
    // Zielfunktions-Fenster nachziehen (Issue #212): der frisch übernommene
    // Druckjob trägt den persistierten `objective`-Block (Default, wenn er fehlt).
    objectivePanel.restoreFromJob(job);
  },
  sectionsFanout: {
    druckplan(sections, kind) {
      druckplanPanel.setSections(sections, kind);
    },
    simulation(sections) {
      simulationPanel.setSections(sections);
    },
    export(sections) {
      exportPanel.setSections(sections);
    },
    processParams(sections, job) {
      processParamsPanel.setSections(sections, job);
    },
    placement(sections, job) {
      placementOverridePanel.setSections(sections, job);
    },
  },
  restoreProcessParamsPanel(job) {
    processParamsPanel.restoreFromJob(job);
  },
  restorePlacementPanel(job) {
    placementOverridePanel.restoreFromJob(job);
  },
  updateOverrideMarkers() {
    updatePartsOverrideMarkers();
  },
  refreshRevisions(jobs) {
    refreshRevisions(jobs);
  },
  reevaluateDecomposition(overrides) {
    // Dieselbe Neubewertung wie das manuelle Platzierungsfeld (Issue #172):
    // Ampel + Druckbarkeits-/Kollisions-Badge sofort „ungeprüft", debounced neu
    // prüfen — nie ein altes Urteil zur alten Platzierung als aktuell.
    druckplanPanel.applySectionOverrides(overrides);
  },
};

// Einstellungs-Fenster der Zielfunktion (Issue #212, PRD #183 Stufe 3): ein
// Gewichts-Satz, zwei Lesarten; Gleichstand im Aus-Modus sperrt das Fenster
// (ui/objective-state.ts). Persistenz über PUT …/objective (einzige
// Schreibstelle `fgc.project`, ADR-016); eine tatsächliche Änderung veraltet
// den Zerlegungsplan (Core bumpt `cutplan` echo-fest, #199) — die Badges
// ziehen über das Übernahme-Protokoll (#193) nach.
const objectivePanel = new ObjectivePanel({
  async onSave(settings) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const result = await setObjective(
      currentProjectSlug,
      settings.aufwiegen,
      settings.weights,
      "default",
    );
    adoptJobResponse(jobAdoptPorts, result); // Übernahme-Protokoll (#193), ohne Teile
  },
});

// Ports des Anwenden-Flusses eines Platzierungs-Overrides (Issue #161): der
// PUT plus das Übernahme-Protokoll (`restore: "placement"` + Neubewertung) —
// `ui/placement-apply.ts` delegiert seit #193 intern an `ui/job-adopt.ts`
// (zwei Adapter am selben Vertrag). BEIDE Advisors (Singularität #65/#134,
// Kollision #130) UND das manuelle Platzierungsfeld (`onSaveOverride`) laufen
// über dieselben Ports — Anwenden-Parität per Konstruktion statt Copy-Paste.
const placementApplyPorts: PlacementApplyPorts = {
  setPlacementOverride(sectionId, values) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    return setPlacementOverride(currentProjectSlug, sectionId, values, "default");
  },
  adoptActiveJob(job) {
    currentActiveJob = job;
  },
  restorePlacementPanel(job) {
    placementOverridePanel.restoreFromJob(job);
  },
  updateOverrideMarkers() {
    updatePartsOverrideMarkers();
  },
  refreshRevisions(jobs) {
    refreshRevisions(jobs);
  },
  reevaluateDecomposition(overrides) {
    // Dieselbe Neubewertung wie das manuelle Platzierungsfeld (`onSaveOverride`,
    // Issue #172): Ampel + Druckbarkeits-/Kollisions-Badge sofort „ungeprüft",
    // debounced neu prüfen — nie ein altes Urteil zur alten Platzierung als aktuell.
    druckplanPanel.applySectionOverrides(overrides);
  },
};

// --- Singularitäts-Advisor (Issue #65, Fokus-Verankerung #134): Typ-Warnung + „Anwenden" ---
const singularityAdvisorPanel = new SingularityAdvisorPanel({
  /**
   * Core-Beratung zur Platzierung des Fokus-Abschnitts holen (read-only,
   * ADR-007; Issue #134 — Muster Kollisions-Advisor #130). Ohne Fokus ruft
   * das Panel gar nicht erst an (freundlicher Hinweis, `focusHint`).
   */
  async onCheck(sectionId) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    return getSingularityAdvice(currentProjectSlug, sectionId, "default");
  },
  /**
   * Vorschlag anwenden — über eine *bestehende* Schreib-Route (ADR-007/016):
   * Kipp → `process_params.orientation` (Slice + IK bewahrt), Config-Flip →
   * `process_params.ik_config` (a/b-Block, Slice + Orientierung bewahrt, #200,
   * dieselbe Route wie der Kollisions-Advisor), Platzierung → freie Override-Werte
   * des Fokus-Abschnitts (`setPlacementOverride`, #94). Der Core bumpt die Revision
   * → Neubewertung angestoßen.
   */
  async onApply(action) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    if (action.kind === "process-params" || action.kind === "process-params-ik") {
      const slice = currentActiveJob?.process_params?.slice ?? {};
      // Je Hebel die *andere* process-params-Gruppe bewahren, damit ein Hebel die
      // übrigen Prozessparameter nicht auf Default zurücksetzt (Parität zum
      // Kollisions-Advisor #130): Kipp bewahrt ik_config (#129), Config-Flip die
      // Orientierung.
      const orientation =
        action.kind === "process-params"
          ? action.orientation
          : (currentActiveJob?.process_params?.orientation ?? {});
      const ikConfig =
        action.kind === "process-params-ik"
          ? action.ikConfig
          : (currentActiveJob?.process_params?.ik_config ?? {});
      const project = await setProcessParams(
        currentProjectSlug, slice, orientation, "default", undefined, ikConfig,
      );
      // Übernahme-Protokoll (#193), restore zeigt den angewandten Hebel im Formular.
      adoptJobResponse(jobAdoptPorts, project, { restore: "process-params" });
    } else if (action.kind === "placement-override") {
      // Platzierungsfelder + ▪-Marker an den frischen Override-Stand ziehen (#94) —
      // getestete Sequenz in `ui/placement-apply.ts` (Issue #161).
      await applyPlacementOverride(placementApplyPorts, action.sectionId, action.values);
    }
  },
  currentJob() {
    return currentActiveJob;
  },
  /** Fokus-Abschnitt aus dem einen Halter (Issue #84/#134/#196). */
  currentSectionId() {
    return focusStore.get();
  },
});

// --- Kollisions-Advisor (Issue #130): gerankte Optionsliste + „Anwenden" ---
const collisionAdvisorPanel = new CollisionAdvisorPanel(focusStore, {
  /**
   * Prüfung vom Core holen (read-only, ADR-007). Bewertet wird der fokussierte
   * Abschnitt (sonst der erste des Plans). `includeOptions=false` = nur der
   * Basis-Befund (eine Neu-Simulation, ≈ 20 s); `true` = das teure Menü (je
   * Hebel-Kandidat eine Neu-Simulation, mehrere Minuten) — Prüf-UX #139/#145.
   */
  async onCheck(includeOptions: boolean) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    return getCollisionAdvice(
      currentProjectSlug, focusStore.get(), "default", includeOptions,
    );
  },
  /** Anzeigename des Fokus-Teils für den Scope-Chip (Renderzeit-Auflösung, #196). */
  partName(sectionId) {
    return partNameFor(sectionId);
  },
  /**
   * Eine Option anwenden — über eine *bestehende* Schreib-Route (ADR-007/016). Die
   * process-params-Hebel bewahren die jeweils andere Gruppe (Slice/Orientierung/IK),
   * damit ein Hebel die übrigen Prozessparameter nicht auf Default zurücksetzt. Der
   * Core bumpt die Revision ⇒ die normale Veraltung/Neubewertung wird angestoßen.
   */
  async onApply(action) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    if (action.kind === "placement-override") {
      // Platzierungsfelder + ▪-Marker an den frischen Override-Stand ziehen —
      // Parität zum Singularitäts-Advisor (#65/#134); vorher zeigte die UI nach
      // „Anwenden" weiter den alten Stand (Issue #161). Sequenz getestet in
      // `ui/placement-apply.ts` (Review-Nacharbeit #161).
      await applyPlacementOverride(placementApplyPorts, action.sectionId, action.values);
      return;
    }
    const slice = currentActiveJob?.process_params?.slice ?? {};
    const orientation =
      action.kind === "process-params-orientation"
        ? action.orientation
        : (currentActiveJob?.process_params?.orientation ?? {});
    const ikConfig =
      action.kind === "process-params-ik"
        ? action.ikConfig
        : (currentActiveJob?.process_params?.ik_config ?? {});
    const project = await setProcessParams(
      currentProjectSlug, slice, orientation, "default", undefined, ikConfig,
    );
    // Übernahme-Protokoll (#193), restore zeigt den angewandten Hebel im Formular.
    adoptJobResponse(jobAdoptPorts, project, { restore: "process-params" });
  },
});

// --- Reiter Simulation (Issue #26): Abschnitts-Slicing + Simulation aus Platzierung ---
const simulationPanel = new SimulationPanel(focusStore, {
  /**
   * Einen Abschnitt slicen + simulieren (POST …/sections/{id}/simulate).
   * Der Core erzeugt aus dem Abschnitts-Teil-Mesh + der geplanten Platzierung
   * einen Lauf mit toolpath + trajectory (pose_source=planned); der Druckjob
   * verweist je Abschnitt darauf (section_runs). Kinematisches Replay.
   */
  async onSimulate(sectionId) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    const result = await simulateSection(currentProjectSlug, sectionId, "default");
    // Reiter Export: Abschnitt hat jetzt einen Lauf → exportierbar; Simulations-
    // Revision aufgefrischt (Issue #29). Bewusst KEINE Job-Übernahme (#193):
    // dieser Fluss liest nur section_runs — Kandidat fürs Protokoll, aber eine
    // Verhaltensänderung bräuchte ein eigenes Issue.
    const job = findJob(result.print_jobs);
    exportPanel.setSectionRuns(job?.section_runs ?? []);
    refreshRevisions(result.print_jobs);
    return result;
  },

  /**
   * Den Abschnitts-Lauf im Replay-Player öffnen (ADR-007): Lauf laden + im
   * geteilten 3D-Feld anzeigen und im Reiter Simulation bedienen (Issue #48) —
   * ohne Reiterwechsel, mit „Zurück zur Übersicht" als Rückweg.
   */
  onOpenRun(sectionId, runPath) {
    // Venue folgt der Zerlegungsart (Issue #97): Module spielen am Druckort
    // (Workstation-Bühne, S8), Abschnitte in place im geteilten 3D-Feld (#48).
    if (simPlaysAtDruckort(druckplanPanel.getKind())) {
      void playModuleRunAtDruckort(sectionId, runPath);
    } else {
      void openSectionRun(sectionId, runPath);
    }
  },

  /**
   * Gesamtablauf abspielen (Issue #27): alle Abschnitts-Läufe laden und über
   * eine gemeinsame Zeitleiste in Druckreihenfolge abspielen — mit sichtbarem
   * Umbau-Schritt zwischen den Abschnitten. Reine Darstellung (ADR-007): die
   * Sequenz-/Zeitachsen-Mathematik liegt in `trajectory/sequence.ts`.
   */
  onPlaySequence(items) {
    // „Alle Module" spielt am Druckort in Montagereihenfolge (Issue #97); „Ganze
    // Wand" bleibt der in-place-Gesamtablauf mit Umbau-Schritt (#27).
    if (simPlaysAtDruckort(druckplanPanel.getKind())) {
      void startModuleSequenceAtDruckort(items);
    } else {
      void startSequence(items);
    }
  },

  // Abspielgeschwindigkeit (Issue #155): der Faktor klebt an der Sitzung — hier nur
  // die Modul-Variable setzen. Der laufende Player liest `replaySpeed` je Frame über
  // seine rateAt-Closure, der Wechsel wirkt also sofort (Umbaupausen bleiben 3 s).
  onSpeedChange(rate) { replaySpeed = rate; },

  // Replay-Player im Reiter Simulation (Issue #48): dieselbe Player-Instanz wie
  // im Reiter Projekt, nur hier bedient — kein Zwangswechsel mehr.
  onPlay() { trajectoryPlayer?.play(); },
  onPause() { trajectoryPlayer?.pause(); },
  onSeek(t) { trajectoryPlayer?.seek(t); },

  /** „Zurück zur Übersicht" (Issue #48, Befund 1): Modellübersicht wiederherstellen. */
  onBackToOverview() { void backToOverview(); },
});

// Fokus-Wirkungen registrieren (Issue #196): EIN Subscriber, der die Vertrags-
// liste FOCUS_EFFECT_ORDER abarbeitet — NACH den Panel-Konstruktionen, damit
// die panel-eigene Subscription (Teile-Palette/Prüf-Tür in druckplan.ts) wie
// bisher vor der Kaskade rendert.
registerFocusEffects(focusStore, focusEffects);

// --- Simulations-Dock: Replay-Zustand statt Modus (Issue #108, ersetzt #86) ---
// Kein Modus-Umschalter mehr: Schnittplan-Bearbeitung und Simulation koexistieren.
// Während ein Trajektorien-Replay läuft (`replayActive`), ruhen die Live-Vorschau
// (#85) und die Platzierungs-Marker (#93); ohne Replay sind sie aktiv. Reine
// Darstellung/Orchestrierung (ADR-007) — keine neue Kinematik.

/**
 * Beginnt ein Replay im geteilten 3D-Feld (Issue #108) — bevor ein Abschnitts-
 * Lauf, der Gesamtablauf oder ein Modul-Lauf im Dock-Player gezeigt wird. Räumt
 * die Live-Vorschau (#85) und die Platzierungs-Marker (#93) ab und verlässt die
 * Druckort-Ansicht, wenn sie nicht ohnehin dem Modul-Replay gehört (#96/#97).
 */
function beginReplay(): void {
  if (replayActive) return;
  replayActive = true;
  preparePreview.clear();
  updatePlacementScene(); // Platzierungs-Marker/-Mesh ruhen während des Replays (#93)
  syncDruckort(); // Druckort-Ansicht abgleichen (#96)
}

/**
 * Beendet ein Replay (Projekt-/Wandwechsel oder „Zurück zur Übersicht", #108):
 * etwaigen Modul-Replay am Druckort abräumen, Platzierungs-Marker + Live-Vorschau
 * wieder aufsetzen und die Druckort-Sichtbarkeit an den frischen Zustand angleichen.
 */
function endReplay(): void {
  replayActive = false;
  teardownModuleReplay(); // etwaigen Modul-Replay am Druckort abräumen (Issue #97)
  updatePlacementScene(); // Platzierungs-Marker/-Mesh wieder zeigen (#93)
  updatePreparePreview(); // Live-Vorschau am Fokus wieder aufsetzen (#85)
  syncDruckort(); // Druckort-Sichtbarkeit angleichen (#96)
}

// --- Reiter Export (Issue #29): DRL je Abschnitt + veraltet-Markierung ---
const exportPanel = new ExportPanel({
  /**
   * DRL eines Abschnitts erzeugen (POST …/sections/{id}/export). Der Core nutzt
   * die bestehende Emit-Aktion; mit gemessenem Setup vollständig, sonst
   * Antasten-Hinweis (kein Gate). Die Antwort trägt die aufgefrischten
   * Revisionsstände (veraltet-Markierung) mit.
   */
  async onExport(sectionId) {
    if (!currentProjectSlug) throw new Error("Kein Projekt geöffnet.");
    return exportSectionDrl(currentProjectSlug, sectionId, "default");
  },
});

/**
 * Aktualisiert die veraltet-Badges des Reiters Export aus den Revisionsständen
 * des Druckjobs (Issue #29). Wird nach jeder Änderung an einer Prozessstufe
 * aufgerufen, deren API-Antwort die aktualisierten `print_jobs` liefert.
 */
function refreshRevisions(printJobs: PrintJob[] | undefined): void {
  const job = findJob(printJobs);
  exportPanel.setRevisions(job?.revisions);
  // Header-Stepper-Punkte aus derselben Staleness-Ableitung nachziehen (Issue #102).
  shell.setStepperRevisions(job?.revisions);
  // Veraltet-Markierung des Kollisions-Badges der Teile-Palette (Issue #182) —
  // dieselbe Quelle wie die übrigen Stufen-Badges.
  druckplanPanel.setRevisions(job?.revisions);
  // Letzter Stufe-2-Prüf-Tür-Stand (Issue #175): „zuletzt geprüft (global/Fokus),
  // veraltet?" — dieselbe Revisions-Quelle, aus derselben Antwort.
  druckplanPanel.setLastPruef(job?.last_pruef);
}

/**
 * Lädt einen Abschnitts-Lauf und spielt ihn im Replay-Player ab (Issue #48).
 * Das Replay läuft im geteilten 3D-Feld und wird im Reiter Simulation bedient —
 * kein Zwangswechsel in den Reiter Projekt mehr (Befund 2); wir stellen aber den
 * Reiter Simulation aktiv, damit der Player sichtbar ist, und **starten das
 * Replay sofort**, damit der Roboter sichtbar losläuft (Regressionsfix zu #48:
 * showRun ohne play() ließ den Arm nur statisch bei t=0 stehen). „Zurück zur
 * Übersicht" (Befund 1) stellt die Modellübersicht danach wieder her.
 */
async function openSectionRun(sectionId: string, runPath: string): Promise<void> {
  try {
    const run = await loadFromUrl(fsUrl(runPath));
    await showRun(run);
    // Kollisions-Befund dieses Teils fürs Palette-Badge merken (#128) — showRun
    // hat currentCollision aus meta.collision gesetzt (null bei Altlauf).
    recordCollisionFinding(sectionId, currentCollision);
    // Der Kollisionsbefund ist jetzt Lauf-Eigenschaft (#156): er steht im Befund-
    // Badge + aufklappbaren Befundblock der Leiste (und im Reiter Projekt in
    // #traj-meta/#traj-warnings), NICHT mehr als 160-Zeichen-Satz in der Player-
    // Zeile. Mit Befund bleibt #sim-status leer; Altläufe behalten die ehrliche
    // Zeile (US 25).
    simulationPanel.setStatus(
      currentCollision ? "" : replayStatusLine(`Abschnitt ${sectionId}`, null),
    );
    // Player wohnt im Simulations-Dock am Fuß des Slicing-Reiters (#108).
    shell.setActiveTab("druckplan");
    beginReplay();
    simulationPanel.showPlayer(currentTrajDuration, `Abschnitt ${sectionId}`);
    // Geschwindigkeits-Anzeige (#155): Einzel-Lauf ohne Umbaupause.
    simulationPanel.setSpeedModel(replaySpeed, currentTrajDuration, 0);
    trajectoryPlayer?.play();
  } catch (err) {
    simulationPanel.setStatus(`Abschnitts-Lauf konnte nicht geöffnet werden: ${err}`);
  }
}

/**
 * „Zurück zur Übersicht" (Issue #48, Befund 1): den Übersichts-Lauf des Projekts
 * neu laden — das baut die Modellübersicht inkl. Schnittebenen im geteilten
 * 3D-Feld wieder auf (showRun ruft am Ende updateCutPlanes aus dem noch
 * gültigen Druckjob-Zustand). Ohne diesen Rückweg blieb nach einem Replay nur
 * ein erneutes Projekt-Öffnen.
 */
async function backToOverview(): Promise<void> {
  simulationPanel.hidePlayer();
  endReplay(); // Replay beenden: Modul-Replay abräumen, Marker/Live-Vorschau zurück (#108)
  if (!currentAssessmentRun) return;
  try {
    const run = await loadFromUrl(fsUrl(currentAssessmentRun));
    await showRun(run);
    simulationPanel.setStatus("Zurück zur Modellübersicht.");
    // showRun hat die Szene neu gebaut → Marker + Live-Vorschau am Fokus erneut setzen.
    updatePlacementScene();
    updatePreparePreview();
    syncDruckort();
  } catch (err) {
    simulationPanel.setStatus(`Modellübersicht konnte nicht geladen werden: ${err}`);
  }
}

// --- Abschnitts-Sequenz: Gesamtablauf mit Umbau-Schritt (Issue #27) ---

/** Verlässt den Sequenz-Modus: Player stoppen, Zustand + Panel zurücksetzen. */
function teardownSequence(): void {
  if (!sequence) return;
  sequence.player.destroy();
  sequence = null;
  panel.setSequenceMode(false);
  // Strang-Schalter im ⚙-Menü wieder freigeben (Issue #159): im Einzel-Lauf ist
  // er bedeutungsvoll (Kopplung zog aus panel.setSequenceMode hierher um).
  viewerSettings.setToggleVisible("grow-strand", true);
}

/**
 * Startet den Gesamtablauf (Issue #27): lädt alle Abschnitts-Läufe, stapelt ihre
 * Toolpaths (alle in Wandkoordinaten) und spielt sie über eine gemeinsame
 * Zeitleiste ab. Der wachsende Strang, Arm/TCP und der Umbau-Schritt werden in
 * `updateSequence` gesetzt; die Zeitachsen-Mathematik ist rein (`sequence.ts`).
 */
// Reentrancy-Guard (Issue #45): Doppelklick auf „Gesamtablauf abspielen" würde
// zwei konkurrierende Player + doppelte Views hinterlassen.
let sequenceLoading = false;

async function startSequence(items: SequenceItem[]): Promise<void> {
  if (sequenceLoading) return;
  sequenceLoading = true;
  try {
    // Vorherigen Zustand (Einzel-Lauf oder alte Sequenz) abräumen — derselbe
    // vollständige Reset wie showRun (Issue #38: kein Ghost-Picking auf der
    // detachten Modellgruppe, kein aktives Reslice-Panel im Sequenz-Modus).
    teardownSequence();
    resetRunState();

    // Alle Abschnitts-Läufe laden (Toolpath + Trajektorie je Abschnitt).
    const loaded: SeqSection[] = [];
    for (const item of items) {
      const run = await loadFromUrl(fsUrl(item.runPath));
      if (!run.toolpath || !run.trajectory) continue;
      // Echte Bandlage je Abschnitt (Issue #135): Bahn + TCP liegen abschnitts-
      // lokal (z ab Abschnittsfuß) und werden um `meta.section_z0_mm` gehoben —
      // die Reihen stapeln sich an ihrer echten Höhenlage statt am Wandfuß.
      const lift = sectionLiftMm(run.trajectory.meta);
      const liftGroup = new THREE.Group();
      liftGroup.name = `seq-lift-${item.section.section_id}`;
      liftGroup.position.z = lift;
      viewport.world.add(liftGroup);
      const view = new ToolpathView(run.toolpath);
      view.setGrowth(-1); // zunächst nichts sichtbar (noch nicht an der Reihe)
      view.setLabelsVisible(viewerSettings.get("target-numbers"));
      liftGroup.add(view.group);
      const tcp = new TcpMarkerView(run.toolpath.targets);
      liftGroup.add(tcp.mesh);
      loaded.push({
        item,
        targets: run.toolpath.targets,
        trajectory: run.trajectory,
        view,
        tcp,
        box: targetsBox(run.toolpath.targets),
        lift,
      });
      // Kollisions-Befund je Abschnitt fürs Palette-Badge merken (#128, verbatim).
      recordCollisionFinding(item.section.section_id, run.trajectory.meta.collision ?? null);
    }
    if (loaded.length === 0) {
      simulationPanel.setStatus("Kein Abschnitts-Lauf mit Toolpath + Trajektorie gefunden.");
      return;
    }

    const arm = new ArmView(M1013_DH);
    arm.visible = viewerSettings.get("show-arm");
    // Hub-Gruppe des Arms (Issue #135): der Anker (`meta.base_frame`) ist
    // abschnitts-lokal — die Gruppe hebt ihn je Schritt auf die echte Bandlage.
    const armLift = new THREE.Group();
    armLift.name = "seq-arm-lift";
    armLift.add(arm.group);
    viewport.world.add(armLift);
    // Endeffektor-Mesh des Druckjobs am Flansch (Issue #28) — falls gesetzt.
    attachToolMeshToArm(arm);

    const plan = buildSequencePlan(
      loaded.map((l) => ({
        section_id: l.item.section.section_id,
        order: l.item.section.order,
        duration_s: l.trajectory.meta.duration_s,
      })),
      UMBAU_SECONDS,
    );

    const player = new TrajectoryPlayer(
      plan.total_s,
      (state) => updateSequence(state),
      sequencePlaybackRate(plan), // Faktor in Druckphasen, 1× in Umbaupausen (#155)
    );
    sequence = { loaded, plan, arm, armLift, player, baseMarker: null, baseKey: null };
    trajectoryPlayer = player;
    armView = arm;

    viewport.fitTo(viewport.world);
    panel.setSequenceMode(true);
    // Strang-Schalter im ⚙-Menü ausblenden (Issue #159): im Gesamtablauf deckt die
    // Zeit den Strang zwingend auf — der Schalter ist bedeutungslos (wie früher das
    // Panel-Label, das setSequenceMode ausblendete).
    viewerSettings.setToggleVisible("grow-strand", false);
    panel.showTrajectory(syntheticSeqTrajectory(loaded, plan));
    // Replay im Druckplan-Reiter bedienen (Issue #48/#86): kein Zwangswechsel;
    // „Zurück zur Übersicht" ist der Rückweg. Player wohnt im Simulieren-Bereich.
    shell.setActiveTab("druckplan");
    beginReplay();
    simulationPanel.showPlayer(plan.total_s, `Gesamtablauf — ${loaded.length} Abschnitte`);
    // Geschwindigkeits-Anzeige (#155): Druckphasen skalieren, Umbaupausen bleiben 3 s.
    simulationPanel.setSpeedModel(replaySpeed, plan.total_s - umbauTotalOf(plan), umbauTotalOf(plan));
    updateSequence(player.state); // Startbild (leerer Strang, Arm am ersten Abschnitt)
    player.play(); // „Gesamtablauf abspielen" spielt sofort ab (Regressionsfix zu #48)
    simulationPanel.setStatus(
      `Gesamtablauf läuft — ${loaded.length} Abschnitte, ${formatTime(plan.total_s)} ` +
        "inkl. Umbau-Schritte. Steuerung unten (Play/Pause, Zeit-Slider).",
    );
  } catch (err) {
    simulationPanel.setStatus(`Gesamtablauf konnte nicht geladen werden: ${err}`);
  } finally {
    sequenceLoading = false;
  }
}

/**
 * Setzt den 3D-Zustand des Gesamtablaufs für die globale Zeit `state.time`
 * (Issue #27): welcher Abschnitt wächst, wo Arm/TCP stehen, ob gerade ein
 * Umbau-Schritt läuft. Bereits gedruckte Abschnitte bleiben stehen (kumulativ).
 */
function updateSequence(state: PlayerState): void {
  if (!sequence) return;
  const { loaded, plan, arm } = sequence;
  const cur = locateSequenceTime(plan, state.time);

  loaded.forEach((l, i) => {
    if (i < cur.sectionIndex) {
      l.view.setGrowth(Number.POSITIVE_INFINITY); // fertig gedruckt, bleibt stehen
      l.tcp.mesh.visible = false;
    } else if (i === cur.sectionIndex) {
      if (cur.phase === "printing") {
        l.view.setGrowth(targetIndexAtProgress(l.targets.length, cur.localFraction));
        l.tcp.setTime(cur.localTime_s, l.trajectory.meta.duration_s);
      } else {
        // Umbau: der gerade fertige Abschnitt bleibt voll gedruckt stehen.
        l.view.setGrowth(Number.POSITIVE_INFINITY);
        l.tcp.mesh.visible = false;
      }
    } else {
      l.view.setGrowth(-1); // noch nicht an der Reihe → unsichtbar
      l.tcp.mesh.visible = false;
    }
  });

  if (cur.phase === "printing") {
    const l = loaded[cur.sectionIndex];
    const pose = computeArmPose(
      M1013_DH,
      l.trajectory.samples,
      l.targets,
      cur.localFraction,
      l.trajectory.meta.base_frame ?? null,
    );
    // Arm auf die echte Bandlage des aktiven Abschnitts heben (Issue #135) —
    // der Anker ist abschnitts-lokal, die Hub-Gruppe stellt die Höhenlage her.
    sequence.armLift.position.z = l.lift;
    arm.setPose(pose.joints_rad, pose.anchor);
    arm.visible = viewerSettings.get("show-arm");
    // Basis-Marker aus dem EINEN Selektor (Issue #171, B17): der Arm folgt der
    // Lauf-Platzierung (meta.base_frame), der Marker der effektiven Platzierung
    // (Zerlegung ⊕ Override) — beide tragen dasselbe Override-Delta, kein
    // Auseinanderdriften mehr (auch über den Advisor-Anwenden-Pfad).
    updateSequenceBase(
      cur.sectionIndex,
      effectivePlacement(l.item.section.placement, sectionOverrideFor(l.item.section.section_id)),
      l.box,
    );
    const phase = `Abschnitt #${l.item.section.order} druckt — ${cur.sectionIndex + 1}/${loaded.length}`;
    panel.setSequencePhase(phase);
    simulationPanel.setPhase(phase); // Replay-Player im Reiter Simulation (Issue #48)
    const io = interpolateSample(l.trajectory.samples, cur.localTime_s).io;
    panel.updateTrajectoryState(state.time, state.playing, io);
    simulationPanel.setPlayerState(state.time, state.playing);
  } else {
    // Umbau-Schritt: Arm aus, Basis fährt von der aktuellen zur nächsten Lage.
    arm.visible = false;
    const from = loaded[cur.sectionIndex];
    const to = loaded[cur.toSectionIndex];
    sequence.armLift.position.z = to.lift; // nächster Abschnitt (Arm ruht, #135)
    // Umbau-Interpolation zwischen den EFFEKTIVEN Lagen beider Teile (Issue #171):
    // beide Endpunkte tragen ihr Override-Delta, damit der Marker über den Umbau
    // nicht zwischen veralteten Lagen fährt.
    const fromPlace = effectivePlacement(from.item.section.placement, sectionOverrideFor(from.item.section.section_id));
    const toPlace = effectivePlacement(to.item.section.placement, sectionOverrideFor(to.item.section.section_id));
    const pf = baseMarkerPosition(from.box, fromPlace);
    const pt = baseMarkerPosition(to.box, toPlace);
    const u = cur.umbauFraction;
    updateSequenceBase(cur.toSectionIndex, toPlace, to.box, [
      pf[0] + (pt[0] - pf[0]) * u,
      pf[1] + (pt[1] - pf[1]) * u,
      pf[2] + (pt[2] - pf[2]) * u,
    ]);
    const phase =
      `Umbau: Abschnitt #${from.item.section.order} → #${to.item.section.order} — ` +
      "Basis fährt zur nächsten Platzierung";
    panel.setSequencePhase(phase);
    simulationPanel.setPhase(phase); // Replay-Player im Reiter Simulation (Issue #48)
    panel.updateTrajectoryState(state.time, state.playing, {});
    simulationPanel.setPlayerState(state.time, state.playing);
  }
}

/**
 * Baut/positioniert den Basis-Marker der Sequenz (Issue #27). Der Marker wird
 * neu gebaut, wenn sich Abschnitt oder Aufstellhöhe ändert (andere Geometrie);
 * `overridePos` setzt die Position direkt (Umbau-Interpolation), sonst aus der
 * Abschnitts-Box + Platzierung.
 */
function updateSequenceBase(
  index: number,
  pose: PlacementPose,
  box: BoxMinMax,
  overridePos?: [number, number, number],
): void {
  if (!sequence) return;
  const key = `${index}:${pose.stand_height_mm}`;
  if (sequence.baseKey !== key || !sequence.baseMarker) {
    if (sequence.baseMarker) viewport.world.remove(sequence.baseMarker);
    const marker = buildBaseMarker(pose);
    sequence.baseMarker = marker;
    sequence.baseKey = key;
    viewport.world.add(marker);
  }
  const marker = sequence.baseMarker;
  if (overridePos) marker.position.set(overridePos[0], overridePos[1], overridePos[2]);
  else placeBaseMarkerInBox(marker, box, pose);
}

/**
 * Synthetische „Trajektorie" für das bestehende Player-Panel im Sequenz-Modus:
 * Gesamtdauer über alle Abschnitte + zeitversetzt zusammengeführte Warnungen.
 * Keine Samples (der io-Verlauf kommt je aktivem Abschnitt aus `updateSequence`).
 */
function syntheticSeqTrajectory(loaded: SeqSection[], plan: SequencePlan): Trajectory {
  const warnings: TrajectoryWarning[] = [];
  loaded.forEach((l, i) => {
    const start = plan.starts_s[i];
    for (const w of l.trajectory.meta.warnings ?? []) {
      warnings.push({
        t_s: start + w.t_s,
        kind: w.kind,
        message: `[#${l.item.section.order}] ${w.message}`,
      });
    }
  });
  return {
    schema_version: "0.1",
    provenance: loaded[0].trajectory.provenance,
    samples: [],
    meta: { duration_s: plan.total_s, io_compensated: false, warnings },
  };
}

// --- Schnittebenen per Drag verschieben (Issue #25) ---
// Eine Schnittebene lässt sich entlang ihrer Achse ziehen. Die verbindliche
// Zustandsänderung (Position → moveCut) läuft über das Panel (`setCutPosition`),
// das dieselbe cutplan-state-Funktion nutzt wie das Zahlenfeld — daher bleiben
// Drag und Zahlenfeld synchron (kein Ad-hoc-Sync). Während des Ziehens wird nur
// das Mesh visuell entlang der Achse bewegt (Darstellungsmathematik, ADR-007);
// erst am Drag-Ende committet `setCutPosition` die Position, was den debounced
// Core-Refresh (Prüfen) auslöst und die Ebenen verbindlich neu aufbaut.
interface CutDrag {
  cutIndex: number;
  mesh: THREE.Mesh;
  origin: THREE.Vector3; // Ankerpunkt der Drag-Achse (Weltraum)
  axis: THREE.Vector3; // Drag-Achse (Weltraum, Einheitsvektor)
  plane: THREE.Plane; // achsen-beschränkte Hilfsebene fürs Raycasting
  startPositionMm: number; // Position vor dem Drag (Plan-Eingabe)
  startLocal: THREE.Vector3; // Mesh-Position vor dem Drag (Gruppen-lokal)
  localAxis: THREE.Vector3; // Drag-Achse im Gruppen-lokalen Frame
  /** Achsanteil des Greifpunkts beim pointerdown — ohne diesen Anker spränge
   *  die Ebene beim ersten pointermove um den Versatz Greifpunkt→Zentrum (Issue #42). */
  grabOffset: number;
  delta: number; // zuletzt gemessene Verschiebung entlang der Achse (mm)
}

/** Totzone (mm): kleinere Deltas sind Klick-Zittern, kein Verschieben (Issue #42). */
const CUT_DRAG_MIN_MM = 1;
let cutDrag: CutDrag | null = null;

function pointerNdc(e: PointerEvent): THREE.Vector2 {
  const rect = viewport.canvas.getBoundingClientRect();
  return new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  );
}

viewport.canvas.addEventListener("pointerdown", (e) => {
  if (!cutPlanes || cutPlanes.handles.length === 0) return;
  // Nur die primäre Taste zieht Ebenen — Rechts-/Mittelklick gehört dem Orbit
  // (Pan/Dolly, Issue #42).
  if (e.button !== 0) return;
  // Schnittebenen-Drag nur, wo der Schnittplan Thema ist (Projekt/Zerlegung/
  // Druckplan, #106) — und nur in der Modellübersicht (nicht in der Roboter-
  // Vorschau). Das Ziehen bleibt synchron mit den Zahlenfeldern (setCutPosition).
  if (
    shell.activeTab !== "projekt" &&
    shell.activeTab !== "zerlegung" &&
    shell.activeTab !== "druckplan"
  )
    return;
  raycaster.setFromCamera(pointerNdc(e), viewport.camera);
  const hit = raycaster.intersectObjects(
    cutPlanes.handles.map((h) => h.mesh),
    false,
  )[0];
  if (!hit) return;
  // Verdeckungstest (Issue #37): liegt eine Modell-/Wandfläche näher, gehört
  // der Klick der Wandauswahl bzw. dem Orbit — nicht der (DoubleSide-)Ebene
  // dahinter. Gegriffen wird die Ebene an ihrem sichtbaren Überstand. Eine
  // ausgeblendete Modellgruppe verdeckt nichts (Issue #49).
  if (modelObject && modelObject.group.visible) {
    const occluder = raycaster.intersectObjects(modelObject.group.children, true)[0];
    if (occluder && occluder.distance < hit.distance) return;
  }
  const handle = cutPlanes.handles.find((h) => h.mesh === hit.object);
  if (!handle) return;
  // Welt-Drag-Achse in den Gruppen-lokalen Frame (nur Rotation, keine Skalierung).
  const groupQuatInv = cutPlanes.group.getWorldQuaternion(new THREE.Quaternion()).invert();
  const plane = axisDragPlane(handle.origin, handle.axis, viewport.camera);
  // Greifpunkt-Anker (Issue #42): Achsanteil des pointerdown-Strahls auf der
  // Hilfsebene — pointermove misst Deltas relativ dazu, nicht zum Zentrum.
  const grab = new THREE.Vector3();
  const grabOffset = raycaster.ray.intersectPlane(plane, grab)
    ? projectOntoAxis(grab, handle.origin, handle.axis)
    : 0;
  cutDrag = {
    cutIndex: handle.cutIndex,
    mesh: handle.mesh,
    origin: handle.origin.clone(),
    axis: handle.axis.clone(),
    plane,
    // Frische Quelle statt evtl. veraltetem currentCuts (Issue #42): das Panel
    // hält den committeten Stand auch im Debounce-Fenster.
    startPositionMm:
      druckplanPanel.getCuts()[handle.cutIndex]?.position_mm ??
      currentCuts[handle.cutIndex]?.position_mm ??
      0,
    startLocal: handle.mesh.position.clone(),
    localAxis: handle.axis.clone().applyQuaternion(groupQuatInv).normalize(),
    grabOffset,
    delta: 0,
  };
  setCutPlaneHighlighted(handle.mesh, true);
  viewport.controls.enabled = false; // Orbit-Steuerung während des Ziehens aus
  viewport.canvas.setPointerCapture(e.pointerId);
});

viewport.canvas.addEventListener("pointermove", (e) => {
  if (!cutDrag) return;
  raycaster.setFromCamera(pointerNdc(e), viewport.camera);
  const point = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(cutDrag.plane, point)) return;
  // Relativ zum Greifpunkt-Anker (Issue #42) — kein Sprung beim ersten move.
  cutDrag.delta = projectOntoAxis(point, cutDrag.origin, cutDrag.axis) - cutDrag.grabOffset;
  cutDrag.mesh.position.copy(cutDrag.startLocal).addScaledVector(cutDrag.localAxis, cutDrag.delta);
});

function endCutDrag(e: PointerEvent): void {
  if (!cutDrag) return;
  const { cutIndex, mesh, startPositionMm, delta } = cutDrag;
  cutDrag = null;
  setCutPlaneHighlighted(mesh, false);
  viewport.controls.enabled = true;
  if (viewport.canvas.hasPointerCapture(e.pointerId)) {
    viewport.canvas.releasePointerCapture(e.pointerId);
  }
  // Erst jetzt in den Schnittplan-Zustand schreiben (Drag-Ende): dieselbe
  // moveCut-Funktion wie das Zahlenfeld; löst den debounced Core-Refresh aus.
  // Nur echte Verschiebungen committen — Klick-Zittern unterhalb der Totzone
  // darf weder dirty setzen noch eine Core-Neubewertung anstoßen (Issue #37/#42).
  if (Math.abs(delta) > CUT_DRAG_MIN_MM) {
    druckplanPanel.setCutPosition(cutIndex, startPositionMm + delta);
  }
  // Ebenen sofort auf den maßgeblichen Panel-Stand neu aufbauen: nach Commit
  // rechnen Folge-Drags sonst gegen veraltete Handles (Doppelzählung, Issue
  // #42); ohne Commit setzt es die minimal bewegte Ebene optisch zurück.
  currentCuts = druckplanPanel.getCuts();
  updateCutPlanes();
}

viewport.canvas.addEventListener("pointerup", endCutDrag);
viewport.canvas.addEventListener("pointercancel", endCutDrag);

// --- Tab-Shell + Projektliste (ADR-016) ---
// Einen absoluten Laufordner-Pfad (Windows/POSIX) in die /@fs-URL des
// Vite-Dev-Servers übersetzen — derselbe Weg wie bei postSlice.run_dir.
function fsUrl(runPath: string): string {
  return `/@fs/${runPath.replace(/\\/g, "/")}`;
}

// Reentrancy-Guard (Issue #45): Doppelklick auf einen Projektlisten-Eintrag
// startet sonst zwei überlappende Ladevorgänge.
let projectOpening = false;

const shell = new Shell({
  // Logo/Projektname im Header (Issue #102): zurück zur Projektliste (kein Zwangspfad).
  onBackToProjectList() {
    if (!shell.apiAvailable) {
      shell.showProjectList([]);
      return;
    }
    listProjects()
      .then((projects) => showProjects(projects))
      .catch((err) => shell.setStatus(`Projektliste fehlgeschlagen: ${err}`));
  },
  // Theme-Toggle ◐ im Header (Issue #102): bedient das Modul aus Scheibe 1.
  onToggleTheme() {
    fgcToggleTheme();
  },
  async onOpenProject(slug) {
    if (projectOpening) return;
    projectOpening = true;
    shell.setStatus("Öffne Projekt …");
    try {
      const project = await loadProject(slug);
      // Aktives Projekt merken (für Druckjob-Übernahme, Issue #19).
      currentProjectSlug = project.slug;
      currentAssessmentRun = project.overview_run;
      shell.setProjectName(project.name); // Projektname in die Header-Logo-Zeile (Issue #102)
      panel.setProjectOpen(true);
      robotPanel.setProjectOpen(true);
      toolPanel.setProjectOpen(true);
      workstationPanel.setProjectOpen(true);
      druckplanPanel.setProjectOpen(true);
      objectivePanel.setEnabled(true); // Zielfunktions-Fenster freischalten (Issue #212)
      processParamsPanel.setProjectOpen(true);
      placementOverridePanel.setProjectOpen(true);
      simulationPanel.setProjectOpen(true);
      simulationPanel.reset();
      exportPanel.setProjectOpen(true);
      exportPanel.reset();
      endReplay(); // Projektwechsel → etwaiges Replay beenden, Live-Vorschau zurück (#108)
      // Aktiven Druckjob aus project.json wiederherstellen (nach Neuladen) —
      // vor showRun, damit Schnittebenen/Marker direkt mitgezeichnet werden.
      // Übernahme-Protokoll (#193), ohne Teile: Job (Anwenden-Abbildung der
      // Advisors #65) + ▪-Marker + veraltet-Badges (Stepper-Punkte #102,
      // Export-/Palette-Badges #29/#182, last_pruef #175).
      const activeJob = adoptJobResponse(jobAdoptPorts, project);
      singularityAdvisorPanel.setProjectOpen(true);
      singularityAdvisorPanel.reset();
      collisionAdvisorPanel.setProjectOpen(true);
      collisionAdvisorPanel.reset();
      if (activeJob) {
        shell.updateActivePrintJob(activeJob.wall_global_id, activeJob.wall_name ?? null);
        // Roboterwahl wiederherstellen (Issue #20).
        currentRobot = activeJob.robot ?? null;
        // Endeffektor-Wahl wiederherstellen (Issue #21).
        currentTool = activeJob.tool ?? null;
        // Workstation-Wahl wiederherstellen (Issue #77).
        currentWorkstation = activeJob.workstation ?? null;
        // Platzierung wiederherstellen (Issue #22): Plan-Eingaben (Altprojekte —
        // sie speisen nur noch die Override-Referenzen #94a, Issue #134).
        currentWallGlobalId = activeJob.wall_global_id;
        currentPlacements = activeJob.placements ?? [];
        // Zerlegung wiederherstellen (Issue #24): Schnittebenen als Plan-Eingaben.
        currentCuts = activeJob.cuts ?? [];
      } else {
        shell.clearActivePrintJob();
        currentRobot = null;
        currentTool = null;
        currentWorkstation = null;
        currentWallGlobalId = null;
        currentPlacements = [];
        currentCuts = [];
      }
      const run = await loadFromUrl(fsUrl(project.overview_run));
      await showRun(run);
      shell.showShell("projekt");
      shell.setStatus(""); // Erfolg: „Öffne Projekt …" nicht stehen lassen (Issue #33)
      panel.setCurrentRobot(currentRobot);
      robotPanel.setCurrentRobot(currentRobot);
      toolPanel.setCurrentTool(currentTool);
      // Roboter-Vorschau folgt wieder dem (frisch geladenen) Druckjob-Tool (Issue #49).
      previewSelectedTool = null;
      updateRobotPreviewTool();
      // Payload-Check aktualisieren (Issue #21): Roboter-Traglast aus geladener Liste.
      toolPanel.setRobotPayload(robotPayloadKg(currentRobot));
      // Kompatibilitäts-Filter am geladenen Roboter ausrichten (Issue #74).
      toolPanel.setActiveRobot(currentRobot);
      // Workstation-Wahl + Kompatibilitäts-Filter wiederherstellen (Issue #77).
      workstationPanel.setCurrentWorkstation(currentWorkstation);
      workstationPanel.setActiveRobot(currentRobot);
      // Kollisions-Befunde des alten Projekts verwerfen (#128): neue Läufe füllen
      // die Badges bei der nächsten Simulation/Öffnung wieder.
      collisionFindings.clear();
      druckplanPanel.setCollisionFindings(clearedCollisionFindings());
      // Reiter Druckplan füllen (Issue #22/#24): Formular + Zerlegung aus dem
      // referenzierten Lauf (decompose.json, ADR-016).
      druckplanPanel.restoreFromJob(
        currentPlacements,
        activeJob?.decomposition_kind ?? "abschnitt",
        // Schnittplan-Eingaben mitgeben (Issue #35): sonst ist die Schnittliste
        // nach dem Neuladen leer und die erste Änderung überschreibt den
        // persistierten Plan mit einem einzelnen Schnitt.
        activeJob?.cuts ?? [],
        activeJob?.joint_offset_mm ?? 0,
        activeJob?.section_overrides ?? [],
        activeJob?.stand_mode ?? "floor",
        activeJob?.module_limits ?? null,
        !!activeJob?.workstation,
        // Gebäudekontext-Schalter nach Neuladen wiederherstellen (Issue #131).
        activeJob?.check_building_context ?? false,
      );
      // Revisionsstände (#182) kamen bereits über das Übernahme-Protokoll (#193).
      // Teil-Override-Formulare zunächst leeren (Issue #82/#92); restoreDecomposition
      // baut sie wieder auf, sobald ein Zerlegungslauf vorliegt.
      processParamsPanel.setSections([], activeJob);
      // Prozessparameter-Formular aus dem Druckjob wiederherstellen (Issue #59).
      processParamsPanel.restoreFromJob(activeJob);
      // Platzierungsfelder (Issue #94): persistierten Override-Stand laden;
      // die automatischen Platzhalter kommen mit restoreDecomposition.
      placementOverridePanel.setSections([], activeJob);
      updatePartsOverrideMarkers(); // ▪-Marker der Teile-Palette zurücksetzen (Issue #91)
      updatePlacementPrecondition();
      if (activeJob) {
        await restoreDecomposition(activeJob);
        // Vorhandene Abschnitts-Läufe markieren (Issue #26) — nach setSections.
        simulationPanel.setSectionRuns(activeJob.section_runs ?? []);
        // Reiter Export (Issue #29): Abschnitts-Läufe wiederherstellen (die
        // Revisionsstände kamen bereits über das Übernahme-Protokoll, #193).
        exportPanel.setSectionRuns(activeJob.section_runs ?? []);
      }
    } catch (err) {
      shell.setStatus(`Öffnen fehlgeschlagen: ${err}`);
    } finally {
      projectOpening = false;
    }
  },
  async onCreateProject(name, modelPath) {
    shell.setStatus("Lege Projekt an (Modellübersicht rechnen) …");
    shell.setCreateBusy(true);
    try {
      const project = await createProject(name, modelPath);
      // Aktives Projekt merken (für Druckjob-Übernahme, Issue #19).
      currentProjectSlug = project.slug;
      currentAssessmentRun = project.overview_run;
      panel.setProjectOpen(true);
      robotPanel.setProjectOpen(true);
      toolPanel.setProjectOpen(true);
      workstationPanel.setProjectOpen(true);
      druckplanPanel.setProjectOpen(true);
      objectivePanel.setEnabled(true); // Zielfunktions-Fenster freischalten (Issue #212)
      processParamsPanel.setProjectOpen(true);
      placementOverridePanel.setProjectOpen(true);
      singularityAdvisorPanel.setProjectOpen(true);
      singularityAdvisorPanel.reset();
      collisionAdvisorPanel.setProjectOpen(true);
      collisionAdvisorPanel.reset();
      currentActiveJob = undefined;
      simulationPanel.setProjectOpen(true);
      simulationPanel.reset();
      exportPanel.setProjectOpen(true);
      exportPanel.reset();
      endReplay(); // neues Projekt → etwaiges Replay beenden, Live-Vorschau zurück (#108)
      shell.clearActivePrintJob();  // neues Projekt hat noch keinen Druckjob
      currentRobot = null;
      currentTool = null;
      currentWorkstation = null;
      currentWallGlobalId = null;
      currentPlacements = [];
      currentCuts = [];
      panel.setCurrentRobot(null);
      robotPanel.setCurrentRobot(null);
      toolPanel.setCurrentTool(null);
      workstationPanel.setCurrentWorkstation(null);
      workstationPanel.setActiveRobot(null);
      previewSelectedTool = null;
      updateRobotPreviewTool();
      druckplanPanel.restoreFromJob([]);
      processParamsPanel.setSections([], undefined); // neues Projekt: keine Teile (Issue #82/#92)
      processParamsPanel.restoreFromJob(undefined); // neues Projekt: leeres Formular (Issue #59)
      placementOverridePanel.setSections([], undefined); // neues Projekt: keine Platzierungs-Overrides (Issue #94)
      updatePartsOverrideMarkers(); // Teile-Palette leeren (Issue #91)
      updatePlacementPrecondition();
      const run = await loadFromUrl(fsUrl(project.overview_run));
      await showRun(run);
      shell.showShell("projekt");
      shell.setStatus(""); // Erfolg: Anlege-Status nicht stehen lassen (Issue #33)
    } catch (err) {
      shell.setStatus(`Anlegen fehlgeschlagen: ${err}`);
    } finally {
      shell.setCreateBusy(false);
    }
  },

  /** Reiterwechsel: Szenenmodus des geteilten Hauptsichtfelds (Issue #30/#31). */
  onTabChanged(id) {
    applySceneMode(id);
    // Viewer-Einstellungen: die zwei ⚙-Sektionen erscheinen je Reiter × Lauf-offen
    // (Issue #159) — „Modellansicht" in den Fokus-Reitern, „Replay-Bühne" wo eine
    // Bühne läuft (auch im Reiter Projekt mit offenem Lauf). applyWallFocus isoliert
    // in den Fokus-Reitern die gewählte Wand. Nach applySceneMode (Kamera-Restore),
    // damit der Wand-Fokus die Kamera als Letztes setzt.
    refreshViewerSettingsSections();
    applyWallFocus(true);
    // Teile-Palette (Issue #91): schwebt über dem 3D-Feld im Reiter Zerlegung
    // (Issue #106) und weiterhin im Reiter Druckplan (Slicing/Fokus).
    const overModel = id === "zerlegung" || id === "druckplan";
    druckplanPanel.setPaletteVisible(overModel);
    // Plan-Chip „vor dem Druck antasten" (#103): im Reiter Zerlegung schwebend
    // unten mittig. Im Reiter Slicing belegt das Simulations-Dock (#108) den Fuß
    // des Viewports — dort tritt der Chip zurück (Überlappung vermeiden, Prototyp).
    planChipEl.hidden = id !== "zerlegung";
    // Simulations-Dock (#108): nur im Reiter Slicing (druckplan) — die Simulier-
    // Aktionen + der Player docken hier an. Sichtbarkeit nur über `.hidden`.
    simDockEl.hidden = id !== "druckplan";
    // Druckort-Ansicht lebt nur im Reiter Druckplan (Issue #96): Wechsel raus
    // verlässt sie sauber zur Wand-Ansicht, der Umschalter verschwindet.
    syncDruckort();
    // Bibliothek öffnet mit der aktiven Rubrik-Galerie — Bestand sofort sichtbar
    // (Issue #75: setActive frischt über onRubricChanged die richtige Galerie auf).
    if (id === "bibliothek") libraryRubrics.setActive(libraryRubrics.active);
  },
});

// ⌘K-Befehlspalette (UI-Redesign Scheibe 9, Issue #109): Overlay über der App,
// das jede Einstellung/Aktion sucht und ausführt. Die reine Registry/Filterlogik
// lebt in ui/palette-state.ts; hier nur die Verdrahtung ihrer Wirkungen an die
// BESTEHENDEN Mechanismen — Reiterwechsel über die Shell, Theme über das Modul
// aus Scheibe 1 (Accordion-Öffnen/Aktions-Klicks löst die Palette selbst über
// die realen Elemente aus, ADR-016: kein zweiter Zustand).
const commandPalette = new CommandPalette({
  onNavigate: (tab) => shell.setActiveTab(tab),
  onToggleTheme: () => fgcToggleTheme(),
});
// Diagnose-Hook für den Headless-Smoke (#109): Palette öffnen/filtern/ausführen
// aus dem echten DOM treiben (window.__palette), analog zu window.__scopeDebug.
(window as unknown as { __palette?: unknown }).__palette = commandPalette;

// Projektliste anzeigen + die Wand-Bilanz-Balken asynchron nachreichen
// (UI-Redesign Scheibe 7, Issue #104): die Karten rendern sofort; je Projekt
// wird danach der Übersichts-Lauf gelesen (loadProject → candidates.json) und
// die Bilanz gemeldet. Projekte ohne Übersichts-Lauf/candidates degradieren
// sauber (kein Balken, kein Zeitstempel). Nichts neu rechnen (ADR-007) — die
// Zählung liest nur die eligible/provisional-Flags des Artefakts.
function showProjects(projects: ProjectSummary[]): void {
  shell.showProjectList(projects);
  void enrichProjectCards(projects);
}

async function enrichProjectCards(projects: ProjectSummary[]): Promise<void> {
  await Promise.all(
    projects.map(async (p) => {
      try {
        const project = await loadProject(p.slug);
        const res = await fetch(`${fsUrl(project.overview_run)}/candidates.json`);
        // Vite beantwortet fehlende /@fs-Dateien mit index.html + Status 200
        // (SPA-Fallback) — ein fehlendes candidates ist am Content-Type erkennbar.
        if (!res.ok || !res.headers.get("content-type")?.includes("json")) {
          shell.updateProjectBalance(p.slug, null, null);
          return;
        }
        const candidates = (await res.json()) as Candidates;
        const balance = wallBalanceFromCandidates(candidates);
        const createdMs = Date.parse(candidates.provenance?.created ?? "");
        shell.updateProjectBalance(p.slug, balance, Number.isFinite(createdMs) ? createdMs : null);
      } catch {
        // Netzfehler / kaputtes Artefakt: sauber ohne Balken degradieren.
        shell.updateProjectBalance(p.slug, null, null);
      }
    }),
  );
}

// Dev/Automation und Fallback-Direkteinstieg: ?run=<url-basis>, z. B.
// /@fs/C:/pfad/zum/laufordner. Unverändert — lädt den Lauf direkt in die
// Tab-Shell (Reiter Projekt), ohne Projektliste (ADR-016-Fallback).
const runParam = new URLSearchParams(location.search).get("run");

// API-Verfügbarkeit prüfen: asynchron. Steuert Parameter-Panel (Panel) und
// die Projekt-Operationen (Shell).
isApiAvailable().then((available) => {
  panel.setApiAvailable(available);
  shell.setApiAvailable(available);
  robotPanel.setApiAvailable(available);
  toolPanel.setApiAvailable(available);
  workstationPanel.setApiAvailable(available);
  druckplanPanel.setApiAvailable(available);
  processParamsPanel.setApiAvailable(available);
  placementOverridePanel.setApiAvailable(available);
  singularityAdvisorPanel.setApiAvailable(available);
  collisionAdvisorPanel.setApiAvailable(available);
  simulationPanel.setApiAvailable(available);
  exportPanel.setApiAvailable(available);
  configurator.setApiAvailable(available);
  toolLibrary.setApiAvailable(available);
  workstationLibrary.setApiAvailable(available);
  robotLibrary.setApiAvailable(available);
  if (available) {
    // Roboterkatalog laden (Issue #20): einmalig beim Start, ändert sich nicht.
    listRobots()
      .then((robots) => {
        loadedRobots = robots;
        robotPanel.setRobots(robots);
        // Endeffektor-Konfigurator: Kompatibilitäts-Tags aus dem Katalog (Issue #71).
        configurator.setRobots(robots.map((r) => r.name));
        // Workstation-Editor: dieselben Kompatibilitäts-Tags (Issue #72/#75).
        workstationLibrary.setRobots(robots.map((r) => r.name));
        // Payload an ToolPanel weitergeben, falls Roboter bereits gesetzt (Issue #21).
        toolPanel.setRobotPayload(robotPayloadKg(currentRobot));
        // Kompatibilitäts-Filter am aktiven Roboter ausrichten (Issue #74).
        toolPanel.setActiveRobot(currentRobot);
        // Workstation-Filter am selben aktiven Roboter ausrichten (Issue #77).
        workstationPanel.setActiveRobot(currentRobot);
      })
      .catch(() => robotPanel.setStatus("Roboterkatalog konnte nicht geladen werden."));
    // Endeffektor-Katalog laden (Issue #21): einmalig beim Start.
    // loadedTools versorgt auch das Mesh-am-Flansch im Replay (Issue #28).
    listTools()
      .then((tools) => {
        loadedTools = tools;
        toolPanel.setTools(tools);
        toolPanel.setCurrentTool(currentTool);
      })
      .catch(() => toolPanel.setStatus("Endeffektor-Katalog konnte nicht geladen werden."));
    // Workstation-Katalog laden (Issue #77): einmalig beim Start, für das Dropdown
    // im Reiter Roboter. Änderungen in der Bibliothek frischen ihn separat auf.
    listWorkstations()
      .then((workstations) => {
        loadedWorkstations = workstations;
        workstationPanel.setWorkstations(workstations);
        workstationPanel.setCurrentWorkstation(currentWorkstation);
      })
      .catch(() => workstationPanel.setStatus("Workstation-Katalog konnte nicht geladen werden."));
  }
  // Ohne ?run= die Projektliste befüllen, sobald wir die API-Lage kennen.
  if (!runParam && available) {
    listProjects()
      .then((projects) => showProjects(projects))
      .catch((err) => shell.setStatus(`Projektliste fehlgeschlagen: ${err}`));
  }
});

// Theme-Toggle ◐ im Header initial mit dem (persistierten) Theme spiegeln (Issue #102).
syncThemeToggle();

if (runParam) {
  shell.showShell("projekt");
  panel.setStatus(`Lade ${runParam} …`);
  loadFromUrl(runParam)
    .then(showRun)
    .catch((err) => panel.setStatus(`Laden fehlgeschlagen: ${err}`));
} else {
  // Startzustand ohne Parameter: Projektliste (wird nach dem API-Check befüllt).
  shell.showProjectList([]);
}

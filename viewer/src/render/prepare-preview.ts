/**
 * Steuerung der Live-Vorschau „Vorbereiten" (Druckplan S6, Issue #85, PRD B/#70).
 *
 * Bündelt die drei Bausteine des Vorbereiten-Modus für den Fokus-Abschnitt zu
 * **einer** billigen, IK-freien 3D-Rückkopplung:
 *  - `ui/preview-slice.ts` → die sofort geslicete Vorschau-Bahn (Reglerziehen),
 *  - `ui/nozzle-schablone.ts` → die Schablonen-Posen aus der geteilten
 *    `nozzle_quat`-Quelle (#61), gerendert als gleitender Düsen-Stummel,
 *  - `ui/safety-clearance.ts` → der atmende Sicherheitspuffer aus Basislage +
 *    `safety_min_distance_mm` (#77).
 *
 * Diese Klasse ist reine Darstellung/Animation (ADR-007): sie rechnet keinen
 * Fachzustand, sondern liest die effektiven Params (#82) und die geplante
 * Platzierung (#80) und spiegelt sie ins 3D-Feld. Die Fachlogik (Posen, Puffer)
 * liegt in den getesteten reinen Modulen; hier nur three.js + ein rAF-Takt für
 * das Gleiten/Atmen (Muster von `stepCameraTween`).
 */

import * as THREE from "three";

import type { DecompositionSection, SectionOverride } from "../api/projects";
import type { WallFrame } from "./wall-frame";
import { effectivePlacement } from "../ui/effective-placement";
import { schablonePoses } from "../ui/nozzle-schablone";
import { type EffectiveSlice, sliceSectionPreview } from "../ui/preview-slice";
import { clearanceState } from "../ui/safety-clearance";
import { type SchabloneView, buildSchabloneView } from "./schablone";
import { type ClearanceView, buildClearanceView } from "./clearance";

/** Periode (ms) eines Stummel-Durchlaufs entlang der Bahn (visueller Takt). */
const GLIDE_PERIOD_MS = 4000;
/** Periode (ms) eines Atemzugs des Sicherheitspuffers. */
const BREATH_PERIOD_MS = 2600;

export interface PreparePreviewInput {
  section: DecompositionSection;
  wall: WallFrame;
  slice: EffectiveSlice;
  orientation: { leadRad: number; kippRad: number };
  safetyMinMm: number;
  /** Aktiver Platzierungs-Override des Teils (Issue #171): der Sicherheitspuffer
   *  urteilt über den **effektiven** Abstand (Zerlegung ⊕ Override). Ohne Override
   *  gilt die Zerlegungs-Platzierung wie bisher. */
  override?: SectionOverride;
}

export class PreparePreview {
  private readonly root = new THREE.Group();
  private schablone: SchabloneView | null = null;
  private clearance: ClearanceView | null = null;
  private standoffMm = 0;
  private safetyMinMm = 0;
  private rafId: number | null = null;
  private startTime = 0;

  constructor(parent: THREE.Object3D) {
    this.root.name = "prepare-preview";
    parent.add(this.root);
  }

  /**
   * Baut die Vorschau für den Fokus-Abschnitt neu auf und startet die Animation.
   * Bei jedem Reglerziehen erneut aufgerufen → die Bahn aktualisiert sich sofort
   * (billig, keine IK). Ohne Fokus/Wand: {@link clear}.
   */
  update(input: PreparePreviewInput): void {
    this.disposeViews();
    const { section, wall, slice, orientation, safetyMinMm } = input;
    // Effektive Platzierung aus dem EINEN Selektor (Issue #171): senkt ein
    // Override den Abstand unters Minimum, wird die Vorschau nicht-grün (B21).
    const placement = effectivePlacement(section.placement, input.override);

    // Kanonischer Frame: x = Wandlänge (Wand-lokal, wie section.x*), y =
    // Wanddicke, z = Höhe ab Wandfuß. Die Gruppe wird an die PCA-Wand-Pose
    // gehängt (Issue #99): Position = Wand-Nullpunkt, um z auf die echte
    // Wandachse gedreht (Quaternionen drehen mit) — vorher Bbox-Näherung,
    // die bei gedrehten Wänden schräg lag.
    this.root.position.set(wall.origin.x, wall.origin.y, wall.zMin);
    this.root.rotation.set(0, 0, wall.yaw);

    const preview = sliceSectionPreview(
      {
        x0_mm: section.x0_mm,
        x1_mm: section.x1_mm,
        z0_mm: section.z0_mm,
        z1_mm: section.z1_mm,
        thickness_mm: wall.thickness_mm,
      },
      slice,
    );
    const poses = schablonePoses(
      preview.path,
      orientation,
      preview.strandWidthMm,
      preview.layerHeightMm,
    );
    this.schablone = buildSchabloneView(poses);
    this.root.add(this.schablone.group);

    // Sicherheitspuffer an der Wandfront des Abschnitts (+y), wächst zur Basis.
    const spanMm = Math.abs(section.x1_mm - section.x0_mm);
    const heightMm = Math.abs(section.z1_mm - section.z0_mm);
    this.clearance = buildClearanceView(spanMm, heightMm);
    this.clearance.group.position.set(
      (section.x0_mm + section.x1_mm) / 2,
      wall.center.y + wall.thickness_mm / 2,
      (section.z0_mm + section.z1_mm) / 2,
    );
    this.root.add(this.clearance.group);

    this.standoffMm = placement.standoff_mm;
    this.safetyMinMm = safetyMinMm;
    this.root.visible = true;
    this.start();
  }

  /** Entfernt die Vorschau und stoppt die Animation (kein Fokus). */
  clear(): void {
    this.stop();
    this.disposeViews();
    this.root.visible = false;
  }

  /** Blendet die Vorschau aus/ein, ohne sie zu verwerfen (Reiterwechsel). */
  setVisible(visible: boolean): void {
    this.root.visible = visible && this.schablone !== null;
    if (visible && this.schablone) this.start();
    else this.stop();
  }

  /** Diagnose für den Headless-Smoke (#85): Zustand der Vorschau. */
  debugInfo(): {
    active: boolean;
    nPoses: number;
    standoffMm: number;
    safetyMinMm: number;
    safe: boolean;
  } {
    return {
      active: this.root.visible && this.schablone !== null,
      nPoses: this.schablone?.nPoses ?? 0,
      standoffMm: this.standoffMm,
      safetyMinMm: this.safetyMinMm,
      safe: this.standoffMm >= this.safetyMinMm,
    };
  }

  private start(): void {
    if (this.rafId !== null) return;
    this.startTime = performance.now();
    const step = (now: number): void => {
      if (!this.root.visible) {
        this.rafId = null;
        return;
      }
      const elapsed = now - this.startTime;
      this.schablone?.setProgress((elapsed % GLIDE_PERIOD_MS) / GLIDE_PERIOD_MS);
      const phase = (elapsed % BREATH_PERIOD_MS) / BREATH_PERIOD_MS;
      this.clearance?.setState(clearanceState(this.standoffMm, this.safetyMinMm, phase));
      this.rafId = requestAnimationFrame(step);
    };
    this.rafId = requestAnimationFrame(step);
  }

  private stop(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  private disposeViews(): void {
    for (const view of [this.schablone?.group, this.clearance?.group]) {
      if (!view) continue;
      this.root.remove(view);
      view.traverse((obj) => {
        const mesh = obj as Partial<THREE.Mesh>;
        mesh.geometry?.dispose();
        const mat = mesh.material;
        if (Array.isArray(mat)) for (const m of mat) m.dispose();
        else mat?.dispose();
      });
    }
    this.schablone = null;
    this.clearance = null;
  }
}

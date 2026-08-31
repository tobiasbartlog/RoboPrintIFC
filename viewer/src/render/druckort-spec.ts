/**
 * Druckort-Szene — reine Spec-Funktionen (Druckplan-Neuordnung II S8,
 * Issue #96, PRD #88, ADR-022). three.js-frei und vitest-getestet (Hausmuster
 * wie `placement-markers.ts`): aus der vom **Core** gerechneten Modul-Lage
 * (`DecompositionSection.module_pose`, `fgc.decompose.module_pose`) und den
 * Workstation-Stammdaten (ADR-021) entsteht die *Beschreibung* der
 * Druckort-Szene — Roboter-Anker an `robot_base_frame`, Modul-Rechteck an der
 * Modul-Lage, Workstation-Mesh-Quelle. Die dünne three.js-Anbindung in
 * `main.ts` setzt sie nur um.
 *
 * Reine **Darstellungsmathematik** (ADR-007-Klarstellung): die Lage selbst
 * kommt als Core-Artefakt, hier wird nur in Render-Formen (zeilenmajore 4×4,
 * Box-Maße) umgerechnet — kein Urteil, keine Kinematik. Fehlen die
 * Voraussetzungen (keine Workstation, keine Frames, kein `module_pose` im
 * Lauf), liefert `druckortSceneSpec` einen **freundlichen Hinweis** statt
 * einer kaputten Szene — Befund, kein Gate (ADR-013-Geist).
 *
 * Koordinaten: Workstation-Mesh-System (mm, z hoch, ADR-006) — identisch zum
 * Workstation-Editor (#78). Quaternionen [w, x, y, z]; die Quaternion-Algebra
 * (`quatMul`/`quatRotate`) kommt aus `ui/face-align.ts` — EIN Dialekt statt
 * einer weiteren Kopie (#123: „eine Frame-Algebra", Design-Log 2026-07-10).
 */

import type { Frame, ModulePose } from "../api/projects";
import type { Mat4 } from "../kinematics/fk";
import { effectiveModuleFrame } from "../ui/effective-placement";
import { quatMul, quatRotate, type Quat, type Vec3 } from "../ui/face-align";

/** Frame (pos_mm + quat [w,x,y,z], ADR-006) → zeilenmajore 4×4-Matrix.
 *  Dieselbe Abbildung wie der Workstation-Editor (`frameToAnchor`, #78) —
 *  direkt als Anker für `ArmView.setPose` nutzbar. Reine Funktion. */
export function frameToMat4(frame: Frame): Mat4 {
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

/**
 * Modul-Frame aus dem **Simulationslauf** (Issue #161): Der Arm folgt im
 * Modul-Replay den Gelenken des Trajektorienlaufs, dessen Platzierung
 * `trajectory.meta.base_frame` (= base_in_wall, Issue #66) trägt. Damit
 * Soll-Kasten, Stranglinien und TCP-Marker (alle unter der `moduleGroup`)
 * deckungsgleich mit dem Arm liegen, muss die `moduleGroup` **dieselbe**
 * Platzierung tragen wie der Lauf:
 *
 *   T_ws←modul = T_ws←basis ∘ T_modul←basis⁻¹
 *              = robot_base_frame ∘ invert(base_frame)
 *
 * — dieselbe Invertierung der Leserichtung wie `fgc.decompose.module_pose`
 * (ADR-022), nur mit der Platzierung des Sim-Laufs statt der des
 * Zerlegungslaufs. Reine Frame-Algebra (mm, Quaternionen [w,x,y,z], ADR-006),
 * deterministisch, DOM-/three.js-frei; `quatMul`/`quatRotate` aus
 * `ui/face-align.ts` (ein Dialekt, #123).
 */
export function runModuleFrame(robotBaseFrame: Frame, baseInWall: Frame): Frame {
  const qA = robotBaseFrame.quat as Quat;
  const pA = robotBaseFrame.pos_mm as number[];
  const [wB, xB, yB, zB] = baseInWall.quat as Quat;
  const pB = baseInWall.pos_mm as Vec3;
  // M = A ∘ B⁻¹: quat = qA · conj(qB); pos = pA − R(qM)·pB.
  const qM = quatMul(qA, [wB, -xB, -yB, -zB]);
  const r = quatRotate(qM, pB);
  return {
    pos_mm: [pA[0] - r[0], pA[1] - r[1], pA[2] - r[2]],
    quat: qM,
  };
}

/** Das Teil-Rechteck, wie es die Zerlegung liefert (Ausschnitt aus
 *  `DecompositionSection` — nur die Geometrie-Felder). */
export interface SectionRect {
  x0_mm: number;
  x1_mm: number;
  z0_mm: number;
  z1_mm: number;
}

/**
 * Maße + lokaler Mittelpunkt des Modul-Rechtecks im **Modul-System** der
 * Core-Lage. Das Modul-System ist das abschnitts-lokale Wandsystem der
 * Simulation (`_wall_local_basis` + Abschnitts-Verschiebung): x zentriert
 * entlang der Teil-Länge, **y zentriert über die Wanddicke** (PCA um den
 * Schwerpunkt ⇒ Wandkörper y ∈ [−Dicke/2, +Dicke/2], die Basis steht bei
 * +standoff auf der +y-Seite), Modulfuß bei z = 0. Toolpath, Trajektorie und
 * Kollisionsbefund leben in genau diesem System — der Soll-Umriss muss dieselbe
 * Konvention tragen, sonst ragt der Druck seitlich aus dem Kasten (Bugfix
 * 2026-07-09: vorher lag die Box bei y ∈ [−Dicke, 0], „Front bei 0", und stand
 * damit eine halbe Wanddicke zu weit von der Roboterbasis weg).
 * `sizeMm` = [Länge, Dicke, Höhe]; `centerLocalMm` ist der Box-Mittelpunkt in
 * Modul-Koordinaten. Reine Funktion.
 */
export interface ModuleBoxSpec {
  sizeMm: [number, number, number];
  centerLocalMm: [number, number, number];
}

export function moduleBoxSpec(section: SectionRect, thicknessMm: number): ModuleBoxSpec {
  const length = Math.abs(section.x1_mm - section.x0_mm);
  const height = Math.abs(section.z1_mm - section.z0_mm);
  const thickness = Math.max(0, thicknessMm);
  return {
    sizeMm: [length, thickness, height],
    centerLocalMm: [0, 0, height / 2],
  };
}

/** Die Workstation-Felder, die die Druckort-Szene braucht (ADR-021-Stammdaten). */
export interface DruckortWorkstation {
  name: string;
  mesh?: string | null;
  mesh_path?: string | null;
  robot_base_frame?: Frame | null;
  work_surface_frame?: Frame | null;
}

/** Das fokussierte Teil, so weit die Szene es braucht. */
export interface DruckortSection extends SectionRect {
  section_id: string;
  module_pose?: ModulePose;
}

/** Beschreibung der Druckort-Szene — von `main.ts` in three.js umgesetzt. */
export interface DruckortSceneSpec {
  /** Anker (zeilenmajore 4×4) des Roboters an `robot_base_frame`. */
  robotAnchor: Mat4;
  /** Modul-Frame in Workstation-Koordinaten — mit `runBaseFrame` aus der
   *  Platzierung des Sim-Laufs abgeleitet (#161), sonst die Zerlegungs-Lage
   *  (`module_pose.workstation`, verbatim). */
  moduleFrame: Frame;
  /** Maße + lokaler Mittelpunkt des Modul-Rechtecks. */
  moduleBox: ModuleBoxSpec;
  /** Mesh-Datei der Workstation (optional — ohne Mesh nur Roboter + Modul). */
  meshFile: string | null;
  /** Absoluter Pfad der Mesh-Datei für die /@fs/-URL (optional). */
  meshPath: string | null;
}

export type DruckortSceneResult =
  | { ok: true; spec: DruckortSceneSpec }
  | { ok: false; hint: string };

/**
 * Baut die Szenen-Beschreibung der Druckort-Ansicht — oder einen freundlichen
 * Hinweis, warum sie (noch) nicht gezeigt werden kann. Alle Hinweise sind
 * **Befund, kein Gate**: nichts stürzt ab, der Nutzer erfährt den nächsten
 * Schritt. Rein und deterministisch.
 */
export function druckortSceneSpec(input: {
  workstation: DruckortWorkstation | null | undefined;
  section: DruckortSection | null | undefined;
  thicknessMm: number;
  /** Platzierung des Trajektorienlaufs (`trajectory.meta.base_frame`, #161):
   *  wenn vorhanden, folgt die Bühne dem Sim-Lauf (eine Quelle mit dem Arm);
   *  fehlt sie (kein Lauf / Altlauf), gilt die Zerlegungs-Lage wie bisher. */
  runBaseFrame?: Frame | null;
}): DruckortSceneResult {
  const { workstation, section, thicknessMm } = input;
  if (!section) {
    return { ok: false, hint: "Kein Modul im Fokus — zuerst ein Modul wählen." };
  }
  if (!workstation) {
    return {
      ok: false,
      hint:
        "Keine Workstation am Druckjob — sie ist der Druckort (ADR-022). " +
        "Bitte im Reiter Roboter eine Workstation wählen.",
    };
  }
  if (!workstation.robot_base_frame || !workstation.work_surface_frame) {
    return {
      ok: false,
      hint:
        `Die Workstation „${workstation.name}" trägt keine Platzierungs-Frames ` +
        "(Roboterbasis + Arbeitsfläche, ADR-021) — in der Bibliothek den Roboter " +
        "auf das Mesh stellen und die Arbeitsfläche wählen. Befund, kein Gate.",
    };
  }
  // Bühne folgt dem Sim-Lauf (Issue #161): trägt der Lauf eine Platzierung
  // (`meta.base_frame`), ist SIE die Quelle des moduleGroup-Transforms — Arm
  // (Gelenke des Laufs) und Bühne (Box/Strang/TCP) teilen dann EINE Platzierung.
  // Ohne Lauf bzw. bei Altläufen ohne das Feld bleibt die Zerlegungs-Lage
  // (module_pose) — Befund, kein Gate, kein Crash.
  const runFrame = input.runBaseFrame
    ? runModuleFrame(workstation.robot_base_frame, input.runBaseFrame)
    : null;
  // Frame-Face des Effektive-Platzierung-Selektors (Issue #171): der Sim-Lauf
  // gewinnt über die Zerlegungs-Lage — statische Ansicht und Replay-Bühne teilen
  // damit EINE Regel (kein Umspringen des Soll-Kastens beim Replay-Start, B19).
  const moduleFrame = effectiveModuleFrame({
    runFrame,
    decompositionFrame: section.module_pose?.workstation,
  });
  if (!moduleFrame) {
    return {
      ok: false,
      hint:
        "Der Zerlegungslauf trägt noch keine Modul-Lage — einmal neu prüfen " +
        "(Knopf „Prüfen“), dann rechnet der Core die Lage am Druckort.",
    };
  }
  return {
    ok: true,
    spec: {
      robotAnchor: frameToMat4(workstation.robot_base_frame),
      moduleFrame,
      moduleBox: moduleBoxSpec(section, thicknessMm),
      meshFile: workstation.mesh ?? null,
      meshPath: workstation.mesh_path ?? null,
    },
  };
}

/** Der Ausschnitt eines geladenen Laufs (`RunData`), den die Druckort-Bühne
 *  braucht (#161): nur `trajectory.meta.base_frame` — strukturell, damit die
 *  reine Funktion ohne Lade-/three.js-Imports testbar bleibt. */
export interface DruckortRunLike {
  trajectory?: { meta: { base_frame?: Frame | null } } | null;
}

/**
 * Szenen-Spec direkt aus dem **geladenen Lauf** (Issue #161): zieht die
 * Platzierung des Sim-Laufs (`trajectory.meta.base_frame`) selbst aus dem Lauf
 * und reicht sie als `runBaseFrame` an {@link druckortSceneSpec} durch. Damit
 * ist die Verdrahtung „Bühne folgt dem Lauf" Teil der reinen, getesteten
 * Funktion statt ungetesteter Glue in `main.ts` — ein Aufrufer kann den Frame
 * nicht mehr still vergessen (der Lauf ist Pflicht-Argument). Ohne Lauf bzw.
 * bei Altläufen ohne das Feld gilt die Zerlegungs-Lage (Befund, kein Gate).
 */
export function druckortSceneSpecForRun(input: {
  workstation: DruckortWorkstation | null | undefined;
  section: DruckortSection | null | undefined;
  thicknessMm: number;
  run: DruckortRunLike | null | undefined;
}): DruckortSceneResult {
  return druckortSceneSpec({
    workstation: input.workstation,
    section: input.section,
    thicknessMm: input.thicknessMm,
    runBaseFrame: input.run?.trajectory?.meta.base_frame ?? null,
  });
}

/**
 * Arm-Replay-Mathematik: aus einem normierten Fortschritt f ∈ [0,1] die
 * Gelenkwinkel und die Anker-Transformation für das Kapsel-Arm-Replay.
 * Darstellungsmathematik (ADR-007-Klarstellung) — konsumiert Artefakte, erzeugt
 * keine.
 *
 * Anker = **feste Roboterbasis** im Wandsystem (`meta.base_frame` = base_in_wall,
 * Issue #66): die Basis steht fix an der geplanten Lage, die Gelenke fahren die
 * Bahn ab und der TCP (nicht der Flansch) druckt — die Düse von oben, wie der Core
 * die IK löst. Fehlt `base_frame` (Altläufe), fällt der Anker auf das Legacy-
 * Verhalten zurück (Flansch pro Frame ans Ziel gelegt, `anchorFlangeToTarget`) —
 * dort schleift die Basis bei eingefrorenen Gelenken mit.
 *
 * f wird über den Fraktions-Index in die 1:1 langen Sample-/Target-Listen
 * abgebildet — dieselbe Zeit→Index-Abbildung wie beim TCP-Marker
 * (`render/tcpmarker`), damit Bahn und Marker deckungsgleich laufen.
 */

import {
  anchorFlangeToTarget,
  forwardChain,
  frameToMat,
  type DhParams,
  type Mat4,
} from "../kinematics/fk";
import type { Frame, Target, TrajectorySample } from "../artifacts/types";

export interface ArmPose {
  joints_rad: number[];
  anchor: Mat4;
}

interface IndexPair {
  lo: number;
  hi: number;
  alpha: number;
}

/** Fraktions-Index in eine Liste der Länge `len` für Fortschritt f ∈ [0,1]. */
function indexAt(len: number, f: number): IndexPair {
  const raw = Math.max(0, Math.min(1, f)) * (len - 1);
  const lo = Math.floor(raw);
  const hi = Math.min(lo + 1, len - 1);
  return { lo, hi, alpha: raw - lo };
}

/**
 * Gelenkwinkel bei Fortschritt f. Lineare Interpolation ist zulässig, weil die
 * Trajectory die Winkel über die ±π-Naht entfaltet speichert (stetig, Core
 * `simulation.build._unwrap`).
 */
export function interpJoints(samples: TrajectorySample[], f: number): number[] {
  if (samples.length === 0) return [0, 0, 0, 0, 0, 0];
  if (samples.length === 1) return [...samples[0].joints_rad];
  const { lo, hi, alpha } = indexAt(samples.length, f);
  const a = samples[lo].joints_rad;
  const b = samples[hi].joints_rad;
  return a.map((va, j) => va + (b[j] - va) * alpha);
}

/** Ziel-Frame (TCP in Wandkoordinaten) bei Fortschritt f: Position linear, Quaternion nlerp. */
export function interpTargetFrame(targets: Target[], f: number): {
  pos_mm: [number, number, number];
  quat: [number, number, number, number];
} {
  const { lo, hi, alpha } = indexAt(targets.length, f);
  const pa = targets[lo].frame.pos_mm;
  const pb = targets[hi].frame.pos_mm;
  const pos: [number, number, number] = [
    pa[0] + (pb[0] - pa[0]) * alpha,
    pa[1] + (pb[1] - pa[1]) * alpha,
    pa[2] + (pb[2] - pa[2]) * alpha,
  ];
  const qa = targets[lo].frame.quat;
  const qb0 = targets[hi].frame.quat;
  // Vorzeichenangleich (q und −q sind dieselbe Rotation), dann normalisierte Lerp.
  const dot = qa[0] * qb0[0] + qa[1] * qb0[1] + qa[2] * qb0[2] + qa[3] * qb0[3];
  const s = dot < 0 ? -1 : 1;
  const q: [number, number, number, number] = [
    qa[0] + (s * qb0[0] - qa[0]) * alpha,
    qa[1] + (s * qb0[1] - qa[1]) * alpha,
    qa[2] + (s * qb0[2] - qa[2]) * alpha,
    qa[3] + (s * qb0[3] - qa[3]) * alpha,
  ];
  const n = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  return { pos_mm: pos, quat: [q[0] / n, q[1] / n, q[2] / n, q[3] / n] };
}

/**
 * Arm-Pose bei Fortschritt f: interpolierte Gelenkwinkel + Anker.
 *
 * Mit `baseFrame` (bevorzugt, Issue #66) ist der Anker die **feste** Basis im
 * Wandsystem (`base_in_wall`) — über die Zeit konstant; die Gelenke articulieren,
 * der TCP druckt. Ist `anchor · forwardChain(joints)[6] · tcp = target`, sofern die
 * Gelenke die echte IK-Lösung sind (Core `build_trajectory`).
 *
 * Ohne `baseFrame` (Altläufe): Legacy-Anker, der den FK-Flansch pro Frame auf das
 * interpolierte Ziel-Frame legt (Basis schleift bei eingefrorenen Gelenken mit).
 * Ohne Targets **und** ohne baseFrame ist der Anker die Identität — der Arm steht
 * in Roboterbasis-Koordinaten am Weltursprung.
 */
export function computeArmPose(
  dh: DhParams,
  samples: TrajectorySample[],
  targets: Target[] | null,
  f: number,
  baseFrame?: Frame | null,
): ArmPose {
  const joints = interpJoints(samples, f);
  if (baseFrame) {
    return { joints_rad: joints, anchor: frameToMat(baseFrame.pos_mm, baseFrame.quat) };
  }
  const flange = forwardChain(dh, joints)[6];
  let target: Mat4 = flange;
  if (targets && targets.length > 0) {
    const fr = interpTargetFrame(targets, f);
    target = frameToMat(fr.pos_mm, fr.quat);
  }
  return { joints_rad: joints, anchor: anchorFlangeToTarget(flange, target) };
}

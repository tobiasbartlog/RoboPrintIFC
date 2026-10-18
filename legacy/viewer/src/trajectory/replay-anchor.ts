/**
 * Replay-Anker auf der echten Bandlage (Issue #135) — reine Spec-Funktionen,
 * DOM-/three.js-frei und vitest-getestet (Hausmuster `collision-state.ts`).
 *
 * Abschnitts-Läufe liegen **abschnitts-lokal** (z ab Abschnittsfuß, x um die
 * Abschnittsmitte); seit Issue #135 nennt `trajectory.meta.section_z0_mm` die
 * echte Höhenlage des Abschnittsfußes über dem Boden (= Wandfuß, `z = 0` im
 * Daten-System). Der Viewer hebt die komplette Replay-Szene (Teil-Mesh, Bahn,
 * TCP, Arm, wachsender Druckstand) um diesen Wert — der Boden (Gitter) bleibt
 * bei 0, die Basis (`meta.base_frame`, lokal ggf. negativ) landet auf ihrer
 * absoluten Aufstellhöhe.
 *
 * **Abwesenheit ist sicher:** Altläufe ohne `section_z0_mm` (und Modul-Läufe)
 * liefern Hub 0 — das Replay bleibt bit-identisch zu heute (ADR-007, verbatim).
 */

import type { Frame } from "../artifacts/types";

/** Ausschnitt der Trajektorien-Meta, den der Replay-Anker liest. */
export interface ReplayLiftMeta {
  section_z0_mm?: number;
}

/**
 * z-Hub (mm) der Replay-Szene: die echte Bandlage des simulierten Abschnitts,
 * verbatim aus `meta.section_z0_mm`. Fehlt das Feld (Altlauf/Modul) oder ist es
 * nicht endlich, gilt 0 (altes Verhalten).
 */
export function sectionLiftMm(meta: ReplayLiftMeta | null | undefined): number {
  const z0 = meta?.section_z0_mm;
  return typeof z0 === "number" && Number.isFinite(z0) ? z0 : 0;
}

/** Unterhalb dieser Höhe (mm) gilt die Basis als „am Boden" — kein Sockel. */
export const PEDESTAL_MIN_MM = 1;

/** Podest-Sockel des Replay-Arms: Lage (lokal, ungehoben) + Höhe bis zum Boden. */
export interface ReplayPedestalSpec {
  /** Basis-Position im abschnitts-lokalen Daten-System (mm) — Sockel-Oberkante. */
  xMm: number;
  yMm: number;
  topZMm: number;
  /** Sockelhöhe (mm) = absolute Aufstellhöhe der Basis über dem Boden. */
  heightMm: number;
}

/**
 * Podest-Sockel unter der Replay-Basis (Muster `basemarker.ts`, Issue #133):
 * steht die Basis nach dem Hub über dem Boden (absolute Aufstellhöhe
 * `base_frame.z + Hub > 0`), reicht ein Sockel von der Basis bis zum Boden
 * hinunter. `null` ohne `base_frame` (Altlauf — der Legacy-Anker schleift die
 * Basis mit, ein fester Sockel wäre gelogen) und bei Basis am Boden.
 */
export function replayPedestal(
  baseFrame: Frame | null | undefined,
  liftMm: number,
): ReplayPedestalSpec | null {
  if (!baseFrame) return null;
  const [x, y, z] = baseFrame.pos_mm;
  const heightMm = z + liftMm; // absolute Aufstellhöhe über dem Boden
  if (!Number.isFinite(heightMm) || heightMm < PEDESTAL_MIN_MM) return null;
  return { xMm: x, yMm: y, topZMm: z, heightMm };
}

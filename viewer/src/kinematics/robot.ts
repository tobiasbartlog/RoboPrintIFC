/**
 * Roboter-DH für die Präsentations-FK des Viewers (Arm-Replay).
 *
 * v1 kennt genau den Doosan M1013 (Primärplattform, §9.2) — die Trajektorie
 * trägt (noch) keinen Roboternamen, also ist dies der feste Default. Die Werte
 * spiegeln `robots/doosan_m1013.json` (`kinematics`-Block); der FK-Test wacht
 * per Golden-Orakel darüber, dass diese Konstante nicht vom Core abdriftet
 * (`fk.test.ts`: `M1013_DH` muss `fk.golden.json.dh` entsprechen).
 *
 * Sobald ein Lauf seinen Roboter deklariert (Folge-Issue), wird die DH aus der
 * Roboterdefinition geladen statt hier hinterlegt.
 */

import type { DhParams } from "./fk";

export const M1013_DH: DhParams = {
  a_mm: [0.0, 620.0, 0.0, 0.0, 0.0, 0.0],
  d_mm: [152.5, 34.5, 0.0, 559.0, 0.0, 121.0],
  alpha_rad: [
    1.5707963267948966, 0.0, 1.5707963267948966, -1.5707963267948966,
    1.5707963267948966, 0.0,
  ],
};

/**
 * Aufrechte Ruhepose (Doosan-Nullstellung) in DH-Winkeln (Issue #53): die
 * DH-Kette ist gegen die Doosan-Gelenkkonvention um `_START` versetzt —
 * `q_dh = [0,…,0]` wäre die seitlich abgeknickte Pose, nicht der stehende
 * Roboter. Für Vorschau/Konfigurator (Flansch oben, z-Achse senkrecht).
 */
export const M1013_HOME_RAD: number[] = [0, Math.PI / 2, Math.PI / 2, 0, 0, Math.PI];

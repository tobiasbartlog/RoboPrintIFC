import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Group, Object3D, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import scene from '../../../fixtures/run_demo/scene.json';
import { mat4FromRows } from '../math';
import { tcpFromScene } from '../tcp';
import { ANCHOR_NAME, applyQ, flangeOf, parseRobot } from '../urdf';

const URDF = resolve(__dirname, '../../../../third_party/doosan_m1013/urdf/m1013.white.urdf');
const HOME = [0, 0, Math.PI / 2, 0, Math.PI / 2, 0];

// Unabhaengig mit Pinocchio gerechnet (FK der URDF, T_WB * T_BF * T_FT aus scene.json):
//   pin.buildModelFromUrdf(m1013.white.urdf); q = (0, 0, pi/2, 0, pi/2, 0); Frame link_6
const EXPECTED_POS = [1204.96048441, 1124.48532595, 1479.41343862];
const EXPECTED_QUAT = [0.707178783, -0.000216021, -0.707034735, 0.000072002];

function buildSceneGraph() {
  const robot = parseRobot(readFileSync(URDF, 'utf8'), {
    packageBase: '/x',
    loadMesh: (_url, done) => done(new Object3D()),
  });
  // Wie SceneView: URDF (m) unter einer Gruppe mit T_WB * Skalierung 1000.
  const root = new Group();
  root.matrixAutoUpdate = false;
  root.matrix.copy(mat4FromRows(scene.workstation.T_WB)).scale(new Vector3(1000, 1000, 1000));
  root.add(robot);
  return { robot, root };
}

describe('tcpFromScene', () => {
  it('Home-Pose: TCP stimmt mit der unabhaengigen FK auf < 0.01 mm ueberein', () => {
    const { robot, root } = buildSceneGraph();
    applyQ(robot, HOME);
    root.updateMatrixWorld(true);
    const pose = tcpFromScene(flangeOf(robot)!, scene.tool.T_FT);
    EXPECTED_POS.forEach((v, i) => expect(Math.abs(pose[i]! - v)).toBeLessThan(0.01));
    const sign = Math.sign(pose[3] * EXPECTED_QUAT[0]!);
    EXPECTED_QUAT.forEach((v, i) => expect(Math.abs(sign * pose[3 + i]! - v)).toBeLessThan(1e-6));
  });

  it('Flansch-Anker haengt am Flansch und rechnet zurueck nach mm', () => {
    const { robot } = buildSceneGraph();
    const anchor = flangeOf(robot)!.getObjectByName(ANCHOR_NAME)!;
    expect(anchor.scale.x).toBeCloseTo(0.001, 12);
  });

  it('J1 dreht den TCP um die Basisachse (Radius und Hoehe bleiben)', () => {
    const { robot, root } = buildSceneGraph();
    applyQ(robot, [0.5, 0, Math.PI / 2, 0, Math.PI / 2, 0]);
    root.updateMatrixWorld(true);
    const pose = tcpFromScene(flangeOf(robot)!, scene.tool.T_FT);
    const r0 = Math.hypot(EXPECTED_POS[0]! - 780, EXPECTED_POS[1]! - 1090);
    const r1 = Math.hypot(pose[0] - 780, pose[1] - 1090);
    expect(r1).toBeCloseTo(r0, 2);
    expect(pose[2]).toBeCloseTo(EXPECTED_POS[2]!, 2);
    expect(Math.hypot(pose[0] - EXPECTED_POS[0]!, pose[1] - EXPECTED_POS[1]!)).toBeGreaterThan(100);
  });
});

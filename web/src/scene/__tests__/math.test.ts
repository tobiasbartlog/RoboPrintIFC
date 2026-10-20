import { Matrix4, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import { clipHeightMm, clipPlaneAboveInW, clipPlaneInW, mat4FromRows, matrixToPose7, pose7ToMatrix } from '../math';

describe('math', () => {
  it('mat4FromRows liest zeilenweise (Translation in der letzten Spalte)', () => {
    const m = mat4FromRows([
      [0, -1, 0, 10],
      [1, 0, 0, 20],
      [0, 0, 1, 30],
      [0, 0, 0, 1],
    ]);
    const p = new Vector3(1, 0, 0).applyMatrix4(m);
    expect(p.toArray()).toEqual([10, 21, 30]);
  });

  it('pose7ToMatrix und matrixToPose7 sind invers, Quaternion (w, x, y, z)', () => {
    const s = Math.SQRT1_2;
    const pose = [1, 2, 3, s, 0, 0, s]; // 90 Grad um Z
    const m = pose7ToMatrix(pose);
    const p = new Vector3(1, 0, 0).applyMatrix4(m);
    expect(p.x).toBeCloseTo(1, 9);
    expect(p.y).toBeCloseTo(3, 9);
    expect(p.z).toBeCloseTo(3, 9);
    const back = matrixToPose7(m);
    pose.forEach((v, i) => expect(back[i]).toBeCloseTo(v, 9));
  });

  it('matrixToPose7 verwirft eine Skalierung', () => {
    const m = new Matrix4().makeScale(1000, 1000, 1000);
    m.setPosition(5, 6, 7);
    const p = matrixToPose7(m);
    expect(p.slice(0, 3)).toEqual([5, 6, 7]);
    expect(p[3]).toBeCloseTo(1, 12);
  });

  it('clipHeightMm: k fertige Schichten -> z_P <= k*h, begrenzt auf n_layers', () => {
    expect(clipHeightMm(0, 10, 4)).toBe(0);
    expect(clipHeightMm(3, 10, 4)).toBe(30);
    expect(clipHeightMm(9, 10, 4)).toBe(40);
    expect(clipHeightMm(null, 10, 4)).toBe(Infinity);
  });

  it('clipPlaneInW: behaelt Punkte unterhalb der Schnitthoehe, auch bei verschobenem Teil', () => {
    const T_WP = mat4FromRows([
      [1, 0, 0, 780],
      [0, 1, 0, 605],
      [0, 0, 1, 901],
      [0, 0, 0, 1],
    ]);
    const plane = clipPlaneInW(20, T_WP);
    // Abstand >= 0 heisst behalten (three schneidet bei clippingPlanes das Negative weg).
    expect(plane.distanceToPoint(new Vector3(780, 605, 901 + 19))).toBeGreaterThan(0);
    expect(plane.distanceToPoint(new Vector3(780, 605, 901 + 21))).toBeLessThan(0);
    expect(plane.distanceToPoint(new Vector3(0, 0, 901 + 20))).toBeCloseTo(0, 9);
  });

  it('clipPlaneAboveInW: behaelt Punkte oberhalb, mit clipPlaneInW ein Band dazwischen', () => {
    const T_WP = mat4FromRows([
      [0, -1, 0, 780],
      [1, 0, 0, 605],
      [0, 0, 1, 901],
      [0, 0, 0, 1],
    ]);
    const low = clipPlaneAboveInW(10, T_WP);
    const high = clipPlaneInW(20, T_WP);
    const inBand = (z: number) => low.distanceToPoint(new Vector3(700, 600, 901 + z)) >= 0 && high.distanceToPoint(new Vector3(700, 600, 901 + z)) >= 0;
    expect(inBand(5)).toBe(false);
    expect(inBand(15)).toBe(true);
    expect(inBand(25)).toBe(false);
  });
});

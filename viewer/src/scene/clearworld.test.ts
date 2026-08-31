/**
 * Leak-Nachweis für `clearWorld` (Issue #50): `Object3D.remove` allein gibt
 * keine GPU-Ressourcen frei. Diese Tests belegen, dass jeder entfernte Teilbaum
 * seine Geometrien, Materialien (auch Arrays) und deren Texturen disposed und
 * dass `renderer.info.memory`-artige Zähler über wiederholte Clear-Zyklen nicht
 * wachsen.
 */

import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { clearWorld } from "./setup";

function world(): THREE.Group {
  return new THREE.Group();
}

describe("clearWorld: Ressourcen-Freigabe", () => {
  it("disposed Geometrie und Material jedes entfernten Mesh und leert die Welt", () => {
    const w = world();
    const geometry = new THREE.BufferGeometry();
    const material = new THREE.MeshStandardMaterial();
    const geoSpy = vi.spyOn(geometry, "dispose");
    const matSpy = vi.spyOn(material, "dispose");
    w.add(new THREE.Mesh(geometry, material));

    clearWorld(w);

    expect(geoSpy).toHaveBeenCalledTimes(1);
    expect(matSpy).toHaveBeenCalledTimes(1);
    expect(w.children).toHaveLength(0);
  });

  it("steigt in verschachtelte Teilbäume ab (Kind-Kanten wie EdgesGeometry)", () => {
    const w = world();
    const parent = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial());
    const childGeo = new THREE.BufferGeometry();
    const childMat = new THREE.LineBasicMaterial();
    const childGeoSpy = vi.spyOn(childGeo, "dispose");
    const childMatSpy = vi.spyOn(childMat, "dispose");
    parent.add(new THREE.LineSegments(childGeo, childMat));
    w.add(parent);

    clearWorld(w);

    expect(childGeoSpy).toHaveBeenCalledTimes(1);
    expect(childMatSpy).toHaveBeenCalledTimes(1);
  });

  it("disposed jedes Material eines Material-Arrays", () => {
    const w = world();
    const matA = new THREE.MeshBasicMaterial();
    const matB = new THREE.MeshBasicMaterial();
    const spyA = vi.spyOn(matA, "dispose");
    const spyB = vi.spyOn(matB, "dispose");
    const mesh = new THREE.Mesh(new THREE.BufferGeometry());
    mesh.material = [matA, matB];
    w.add(mesh);

    clearWorld(w);

    expect(spyA).toHaveBeenCalledTimes(1);
    expect(spyB).toHaveBeenCalledTimes(1);
  });

  it("disposed Texturen, die am Material hängen (map, normalMap, …)", () => {
    const w = world();
    const map = new THREE.Texture();
    const normalMap = new THREE.Texture();
    const mapSpy = vi.spyOn(map, "dispose");
    const normalSpy = vi.spyOn(normalMap, "dispose");
    const material = new THREE.MeshStandardMaterial({ map, normalMap });
    w.add(new THREE.Mesh(new THREE.BufferGeometry(), material));

    clearWorld(w);

    expect(mapSpy).toHaveBeenCalledTimes(1);
    expect(normalSpy).toHaveBeenCalledTimes(1);
  });

  it("disposed ein innerhalb des Teilbaums geteiltes Material genau einmal", () => {
    const w = world();
    const shared = new THREE.MeshStandardMaterial();
    const spy = vi.spyOn(shared, "dispose");
    const group = new THREE.Group();
    group.add(new THREE.Mesh(new THREE.BufferGeometry(), shared));
    group.add(new THREE.Mesh(new THREE.BufferGeometry(), shared));
    w.add(group);

    clearWorld(w);

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("leakt keinen GPU-Speicher über wiederholte Clear-Zyklen (renderer.info.memory-Analog)", () => {
    // Zähler-Analog zu renderer.info.memory: dispose senkt live wieder.
    let liveGeometries = 0;
    let liveTextures = 0;
    const w = world();

    const track = () => {
      const geometry = new THREE.BufferGeometry();
      const texture = new THREE.Texture();
      liveGeometries += 1;
      liveTextures += 1;
      geometry.addEventListener("dispose", () => (liveGeometries -= 1));
      texture.addEventListener("dispose", () => (liveTextures -= 1));
      const material = new THREE.MeshStandardMaterial({ map: texture });
      w.add(new THREE.Mesh(geometry, material));
    };

    for (let cycle = 0; cycle < 25; cycle += 1) {
      track();
      clearWorld(w);
      // Nach jedem Clear sind alle in diesem Zyklus erzeugten Ressourcen frei.
      expect(liveGeometries).toBe(0);
      expect(liveTextures).toBe(0);
      expect(w.children).toHaveLength(0);
    }
  });
});

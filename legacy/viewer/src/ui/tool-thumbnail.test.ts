/**
 * Cache-Schicht der Endeffektor-Vorschaubilder (Issue #56, Modul 2). Getestet
 * wird nur der Cache — das GL-Rendern (`renderMeshThumbnail`) ist bewusst nicht
 * unit-getestet (PRD Testing Decisions).
 */

import { describe, expect, it, vi } from "vitest";

import { ThumbnailCache, type ThumbnailStore } from "./tool-thumbnail";

function memStore(): ThumbnailStore {
  const map = new Map<string, string>();
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  };
}

describe("ThumbnailCache", () => {
  it("berechnet pro mesh_path nur einmal (gleicher Key ⇒ selber Eintrag)", async () => {
    const cache = new ThumbnailCache();
    const compute = vi.fn(async () => "data:img/A");

    const first = await cache.getOrCompute("tools/a.stl", compute);
    const second = await cache.getOrCompute("tools/a.stl", compute);

    expect(first).toBe("data:img/A");
    expect(second).toBe("data:img/A");
    expect(compute).toHaveBeenCalledTimes(1); // zweiter Zugriff aus dem Cache
  });

  it("rendert bei geändertem mesh_path neu (anderer Key)", async () => {
    const cache = new ThumbnailCache();
    const compute = vi.fn(async () => "data:img");

    await cache.getOrCompute("tools/a.stl", compute);
    await cache.getOrCompute("tools/a.glb", compute); // ersetztes Mesh → neuer Pfad

    expect(compute).toHaveBeenCalledTimes(2);
  });

  it("rendert nicht ohne mesh_path (fehlend ⇒ null, kein Cache)", async () => {
    const cache = new ThumbnailCache();
    const compute = vi.fn(async () => "data:img");

    expect(await cache.getOrCompute(null, compute)).toBeNull();
    expect(await cache.getOrCompute("", compute)).toBeNull();
    expect(compute).not.toHaveBeenCalled();
  });

  it("liefert aus dem Store, ohne neu zu rendern (sofort beim erneuten Öffnen)", async () => {
    const store = memStore();
    // Vorbefüllt (wie beim ersten Rendern in einer früheren Sitzung).
    new ThumbnailCache(store).set("tools/a.stl", "data:img/cached");

    const cache = new ThumbnailCache(store);
    const compute = vi.fn(async () => "data:img/new");
    const result = await cache.getOrCompute("tools/a.stl", compute);

    expect(result).toBe("data:img/cached");
    expect(compute).not.toHaveBeenCalled();
  });

  it("peek liefert Miss (null) und Hit ohne Berechnung", () => {
    const cache = new ThumbnailCache();
    expect(cache.peek("tools/a.stl")).toBeNull();
    cache.set("tools/a.stl", "data:img");
    expect(cache.peek("tools/a.stl")).toBe("data:img");
  });

  it("invalidate entfernt den Eintrag ⇒ danach wird neu gerendert", async () => {
    const store = memStore();
    const cache = new ThumbnailCache(store);
    const compute = vi.fn(async () => "data:img");

    await cache.getOrCompute("tools/a.stl", compute);
    cache.invalidate("tools/a.stl");
    await cache.getOrCompute("tools/a.stl", compute);

    expect(compute).toHaveBeenCalledTimes(2);
    expect(cache.peek("tools/a.stl")).toBe("data:img"); // nach Neu-Render wieder da
  });
});

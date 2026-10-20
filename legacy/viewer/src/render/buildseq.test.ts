import { describe, expect, it } from "vitest";

import { BuildSeq } from "./buildseq";

// Modelliert die Aufruf-Reihenfolge in `buildDruckortScene` (main.ts): jeder
// Bau beginnt mit `clearDruckortScene()` → genau EIN bump; danach erfassen
// Tool-Mesh (Flansch) und Workstation-Mesh JE den aktuellen Zähler, ohne selbst
// zu zählen.
describe("BuildSeq — Druckort-Bau-Zähler (#151)", () => {
  it("(a) direkt nach dem Bau ist der Guard des Tool-Meshes gültig", () => {
    const seq = new BuildSeq();
    seq.bump(); // clearDruckortScene() zu Bau-Beginn
    const toolGuard = seq.guard(seq.current);
    expect(toolGuard()).toBe(true);
  });

  it("(b) nach einem weiteren Bau/Teardown (bump) ist der alte Guard ungültig", () => {
    const seq = new BuildSeq();
    seq.bump();
    const toolGuard = seq.guard(seq.current);
    seq.bump(); // nächster clearDruckortScene() (Modulwechsel oder Teardown)
    expect(toolGuard()).toBe(false);
  });

  it("(c) das Workstation-Mesh im SELBEN Bau entwertet den Tool-Guard NICHT (der #151-Defekt)", () => {
    const seq = new BuildSeq();
    seq.bump(); // Bau-Beginn
    const toolGuard = seq.guard(seq.current); // Endeffektor am Flansch erfasst N
    // Workstation-Mesh vorhanden (ADR-021): erfasst NUR, zählt nicht weiter.
    const wsGuard = seq.guard(seq.current);
    // Beide Async-Loads treffen im selben Bau ein → beide dürfen anhängen.
    expect(toolGuard()).toBe(true);
    expect(wsGuard()).toBe(true);
  });

  it("beide Guards eines Baus überleben gemeinsam bis zum nächsten bump", () => {
    const seq = new BuildSeq();
    seq.bump();
    const toolGuard = seq.guard(seq.current);
    const wsGuard = seq.guard(seq.current);
    expect(toolGuard()).toBe(true);
    expect(wsGuard()).toBe(true);
    seq.bump(); // Neubau
    expect(toolGuard()).toBe(false);
    expect(wsGuard()).toBe(false);
  });

  it("startet bei 0 und zählt monoton", () => {
    const seq = new BuildSeq();
    expect(seq.current).toBe(0);
    seq.bump();
    expect(seq.current).toBe(1);
    seq.bump();
    expect(seq.current).toBe(2);
  });
});

import { describe, expect, it, vi } from "vitest";
import { TrajectoryPlayer } from "./player";

// requestAnimationFrame ist in Node nicht verfügbar; TrajectoryPlayer nutzt es
// nur in play(). Die zustandslosen Methoden (seek, state, destroy) lassen sich
// ohne Mock testen.
vi.stubGlobal("requestAnimationFrame", () => 0);
vi.stubGlobal("cancelAnimationFrame", () => {});

describe("TrajectoryPlayer", () => {
  it("initial state: time=0, playing=false", () => {
    const player = new TrajectoryPlayer(10, () => {});
    expect(player.state.time).toBe(0);
    expect(player.state.playing).toBe(false);
    expect(player.state.duration).toBe(10);
  });

  it("seek clamps to [0, duration]", () => {
    const player = new TrajectoryPlayer(10, () => {});
    player.seek(-5);
    expect(player.state.time).toBe(0);
    player.seek(99);
    expect(player.state.time).toBe(10);
    player.seek(7.5);
    expect(player.state.time).toBeCloseTo(7.5);
  });

  it("onChange is called on seek", () => {
    const times: number[] = [];
    const player = new TrajectoryPlayer(10, (s) => times.push(s.time));
    player.seek(4);
    expect(times).toEqual([4]);
  });

  it("pause is no-op when not playing", () => {
    const player = new TrajectoryPlayer(10, () => {});
    expect(() => player.pause()).not.toThrow();
    expect(player.state.playing).toBe(false);
  });

  it("destroy does not throw", () => {
    const player = new TrajectoryPlayer(10, () => {});
    expect(() => player.destroy()).not.toThrow();
  });
});

// Abspielgeschwindigkeit (Issue #155): `advance` rechnet Wanduhr → Trajektorienzeit
// über eine zeitabhängige Rate und teilt jeden Frame an den Phasengrenzen.
describe("TrajectoryPlayer.advance — Rate + Phasengrenzen (#155)", () => {
  const constRate = (rate: number) =>
    () => ({ rate, until_s: Number.POSITIVE_INFINITY });

  it("skaliert die Trajektorienzeit mit konstanter Rate", () => {
    const p = new TrajectoryPlayer(1000, () => {}, constRate(10));
    expect(p.advance(0, 1)).toBeCloseTo(10); // 1 Wanduhr-s × 10 = 10 Traj-s
    expect(p.advance(0, 5)).toBeCloseTo(50);
    expect(p.advance(100, 2)).toBeCloseTo(120);
  });

  it("rastet exakt auf duration ein — kein Drift bei riesigem Budget", () => {
    const p = new TrajectoryPlayer(100, () => {}, constRate(200));
    expect(p.advance(95, 999)).toBe(100);
    expect(p.advance(100, 5)).toBe(100);
  });

  it("bei Rate 0 steht die Zeit (kein Fortschritt)", () => {
    const p = new TrajectoryPlayer(100, () => {}, constRate(0));
    expect(p.advance(30, 5)).toBe(30);
  });

  // Zwei Druckphasen (Rate 200) mit einer 3-s-Umbaupause (Rate 1) dazwischen:
  // [0,10) print · [10,13) umbau · [13,23) print.
  const twoPhase = (t: number) => {
    if (t < 10) return { rate: 200, until_s: 10 };
    if (t < 13) return { rate: 1, until_s: 13 };
    return { rate: 200, until_s: Number.POSITIVE_INFINITY };
  };

  it("verschluckt die Umbaupause NICHT: ein langer Frame bei 200× teilt an der Grenze", () => {
    const p = new TrajectoryPlayer(23, () => {}, twoPhase);
    // Von kurz vor der Grenze mit 1 s Wanduhr-Budget: die Druckphase ist in µs
    // durchlaufen, danach greift die 1×-Umbau-Rate — der Frame bleibt IN der Pause.
    const t = p.advance(9.99, 1);
    expect(t).toBeGreaterThan(10); // Grenze überschritten
    expect(t).toBeLessThan(13); // aber die Pause NICHT übersprungen
    expect(t).toBeCloseTo(10.99995, 3); // Rest-Budget (~1 s) × Rate 1
  });

  it("die Umbaupause dauert 3 s Wanduhr, unabhängig von der Druck-Rate", () => {
    const p = new TrajectoryPlayer(23, () => {}, twoPhase);
    expect(p.advance(10, 3)).toBeCloseTo(13); // genau 3 s Wanduhr → Pause vorbei
    expect(p.advance(10, 2.9)).toBeCloseTo(12.9); // noch mittendrin
  });
});

// „kein RAF-Echtlauf": ein manuell getakteter requestAnimationFrame, dessen
// Zeitstempel wir setzen — so integriert der Player deterministisch über Frames.
describe("TrajectoryPlayer — Integration über getaktete Frames (#155)", () => {
  function fakeRaf() {
    let cb: FrameRequestCallback | null = null;
    vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
      cb = fn;
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {
      cb = null;
    });
    return (nowMs: number) => {
      const f = cb;
      cb = null;
      f?.(nowMs);
    };
  }

  it("spielt mit Rate 10 ohne Drift bis duration und stoppt", () => {
    const tick = fakeRaf();
    const p = new TrajectoryPlayer(100, () => {}, () => ({
      rate: 10,
      until_s: Number.POSITIVE_INFINITY,
    }));
    p.play();
    tick(1000); // erster Frame setzt _lastTs (dt = 0)
    expect(p.state.time).toBe(0);
    tick(1500); // +0.5 s Wanduhr × 10 = 5 Traj-s
    expect(p.state.time).toBeCloseTo(5);
    tick(2000); // → 10
    expect(p.state.time).toBeCloseTo(10);
    tick(60000); // riesiger Sprung → rastet auf duration, stoppt
    expect(p.state.time).toBe(100);
    expect(p.state.playing).toBe(false);
  });
});

/**
 * TrajectoryPlayer — verwaltet den Abspiel-Zustand der Trajektorie.
 * Rechnet keine Kinematik (ADR-007); arbeitet nur mit der Zeitachse.
 *
 * Abspielgeschwindigkeit (Issue #155): der Player integriert echte RAF-Sekunden
 * (Wanduhr) über eine **zeitabhängige Rate** in Trajektorienzeit. Die Rate ist
 * NICHT konstant — sie kann je Phase verschieden sein: in einer Druckphase gilt
 * der Sitzungs-Faktor (z. B. 200×), in einer Umbaupause gilt 1× (die Pause bleibt
 * 3 s Wanduhr, unabhängig vom Faktor — Erzählzeit, #27). Die Zeitachse selbst
 * (Slider/Marker/Wachstum) bleibt Trajektorienzeit; nur die Abspiel-*Rate* skaliert.
 */

/**
 * Die Rate ab einem Trajektorien-Zeitpunkt, gültig bis zur nächsten Phasengrenze.
 * Eine reine Auskunft (z. B. aus `sequenceRateAt`): „ab hier gilt `rate`, und zwar
 * bis `until_s`" — der Player teilt einen Frame an `until_s`, damit ein einziger
 * langer Frame bei hohem Faktor nicht mit der falschen Rate über eine Grenze
 * hinweg integriert (sonst frisst er die Umbaupause).
 */
export interface RateSpan {
  /** Abspiel-Rate ab dem Abfragezeitpunkt (Trajektoriensekunden je Wanduhr-Sekunde). */
  rate: number;
  /** Trajektorienzeit, bis zu der diese Rate gilt (nächste Phasengrenze); Infinity = keine weitere. */
  until_s: number;
}

/** Liefert die geltende Rate + ihre Grenze für einen Trajektorien-Zeitpunkt. */
export type RateAt = (t: number) => RateSpan;

/** Voreinstellung: konstante Echtzeit (1×), keine Phasengrenzen. */
const REALTIME: RateAt = () => ({ rate: 1, until_s: Number.POSITIVE_INFINITY });

export interface PlayerState {
  time: number;
  playing: boolean;
  duration: number;
}

export class TrajectoryPlayer {
  private _time = 0;
  private _playing = false;
  private _animId: number | null = null;
  private _lastTs: number | null = null;
  private readonly _rateAt: RateAt;
  readonly duration: number;

  constructor(
    duration: number,
    private readonly onChange: (state: PlayerState) => void,
    rateAt?: RateAt,
  ) {
    this.duration = duration;
    this._rateAt = rateAt ?? REALTIME;
  }

  get state(): PlayerState {
    return { time: this._time, playing: this._playing, duration: this.duration };
  }

  play(): void {
    // Am Ende → von vorne
    if (this._time >= this.duration) this._time = 0;
    if (this._playing) return;
    this._playing = true;
    this._lastTs = null;
    this._schedule();
  }

  pause(): void {
    if (!this._playing) return;
    this._playing = false;
    if (this._animId !== null) {
      cancelAnimationFrame(this._animId);
      this._animId = null;
    }
    this._emit();
  }

  seek(t: number): void {
    this._time = Math.max(0, Math.min(this.duration, t));
    this._emit();
  }

  destroy(): void {
    this._playing = false;
    if (this._animId !== null) {
      cancelAnimationFrame(this._animId);
      this._animId = null;
    }
  }

  /**
   * Rückt die Trajektorienzeit um ein Wanduhr-Budget `dtWall` (s) vor und teilt
   * den Schritt an jeder Phasengrenze: nie wird über eine Grenze hinweg mit einer
   * Rate integriert (sonst verschluckt ein langer Frame bei 200× die Umbaupause).
   * Rastet exakt auf `duration` ein — kein Drift. Reine Zeitrechnung, testbar mit
   * fake timers (Issue #155). `public` nur für den Test; im Betrieb ruft es `_schedule`.
   */
  advance(t0: number, dtWall: number): number {
    let t = Math.max(0, Math.min(this.duration, t0));
    let budget = Math.max(0, dtWall);
    // Guard gegen Endlosschleife bei degeneriertem rateAt (until_s <= t o. Ä.).
    for (let guard = 0; guard < 10000 && budget > 1e-9 && t < this.duration; guard++) {
      const span = this._rateAt(t);
      const rate = Math.max(0, span.rate);
      if (rate === 0) break; // Rate 0: die Zeit steht, das Restbudget verfällt hier.
      // Grenze dieses Spans in Trajektorienzeit — nie vor `t`, nie über `duration`.
      const boundary = Math.min(Math.max(span.until_s, t), this.duration);
      const wallToBoundary = (boundary - t) / rate; // Wanduhr-Sekunden bis zur Grenze
      if (boundary <= t) break; // degenerierter rateAt (until_s <= t): kein Fortschritt
      if (wallToBoundary <= budget) {
        t = boundary; // exakt auf die Grenze einrasten, dann die neue Rate lesen
        budget -= wallToBoundary;
      } else {
        t += budget * rate;
        budget = 0;
      }
    }
    return Math.min(t, this.duration);
  }

  private _schedule(): void {
    this._animId = requestAnimationFrame((now) => {
      this._animId = null;
      if (!this._playing) return;
      if (this._lastTs === null) this._lastTs = now;
      const dtWall = (now - this._lastTs) / 1000;
      this._lastTs = now;
      this._time = this.advance(this._time, dtWall);
      this._emit();
      if (this._time < this.duration) {
        this._schedule();
      } else {
        this._playing = false;
        this._emit();
      }
    });
  }

  private _emit(): void {
    this.onChange(this.state);
  }
}

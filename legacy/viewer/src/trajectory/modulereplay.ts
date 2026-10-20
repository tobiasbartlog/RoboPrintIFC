/**
 * Reine Ableitung für das Modul-Replay am Druckort (Issue #151), getrennt von
 * three.js (Hausmuster #128). Bildet den Sequenz-Cursor (aus `locateSequenceTime`)
 * auf die **Bühnenzustände eines Frames** ab: welches Modul aktiv ist, ob Arm +
 * Endeffektor und TCP-Marker sichtbar sind, und mit welchem lokalen Fortschritt
 * der Marker gespeist wird.
 *
 * Darstellungsmathematik (ADR-007): kein Fachurteil, nur Zeit → lokale Modulzeit.
 * Beim Drucken folgt der Marker der Bahn des aktiven Moduls (`localFraction`);
 * im Umbau-Schritt ruhen Arm/Werkzeug und Marker, während das nächste Modul auf
 * die Arbeitsfläche kommt.
 */

import type { SequenceCursor, SequencePlan } from "./sequence";

export interface ModuleReplayFrame {
  /** Index des Moduls, das auf der Arbeitsfläche steht bzw. gebaut wird. */
  moduleIndex: number;
  /** Arm samt Endeffektor am Flansch sichtbar (nur in der Druckphase). */
  armVisible: boolean;
  /** TCP-Marker sichtbar (nur in der Druckphase des aktiven Moduls). */
  markerVisible: boolean;
  /** Normierter Fortschritt ∈ [0, 1] für `TcpMarkerView.setTime` (lokale Modulzeit). */
  markerFraction: number;
  /**
   * Wachstum von Strang + Druckstand ∈ [0, 1] aus der lokalen Modulzeit (#152).
   * In der Druckphase = `localFraction`; im Umbau **0** — das ankommende
   * Ziel-Modul ist noch nicht gedruckt (der Strang/Druckstand des neuen Moduls
   * startet leer). Bewusst getrennt von `markerFraction` (die im Umbau 1 ist,
   * aber dort ohnehin unsichtbar): Wachstum verlangt den Frisch-Start.
   */
  growthFraction: number;
}

/**
 * Leitet die Bühnenzustände eines Modul-Replay-Frames aus dem Sequenz-Cursor ab.
 * In der Druckphase ist das aktive Modul `sectionIndex`; im Umbau-Schritt kommt
 * bereits das Ziel-Modul (`toSectionIndex`) auf die Fläche, aber Arm und Marker
 * ruhen, bis dessen Druckphase beginnt.
 */
export function moduleReplayFrame(cursor: SequenceCursor): ModuleReplayFrame {
  const printing = cursor.phase === "printing";
  return {
    moduleIndex: printing ? cursor.sectionIndex : cursor.toSectionIndex,
    armVisible: printing,
    markerVisible: printing,
    markerFraction: printing ? cursor.localFraction : 1,
    growthFraction: printing ? cursor.localFraction : 0,
  };
}

/**
 * Modul-lokaler Timeline-Marker, wie ihn `timelineMarkers` (collision-state.ts)
 * über der **Modul-Dauer** erzeugt: die Fraktionen ∈ [0, 1] beziehen sich auf die
 * Druckphase des Moduls, `seekTime_s` ist die Sprung-Zeit in **modul-lokalen**
 * Sekunden. Minimalform (kein three.js, kein DOM) — die Projektion verschiebt nur
 * diese vier Zeitfelder und lässt alles Übrige (Status, Titel) unangetastet.
 */
export interface ModuleLocalMarker {
  startFraction: number;
  endFraction: number;
  midFraction: number;
  /** Sprung-Ziel in **modul-lokalen** Sekunden. */
  seekTime_s: number;
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/**
 * Projiziert die modul-lokalen Timeline-Marker des **aktiven** Moduls auf die
 * Gesamt-Sequenzachse (Issue #153, Entscheidung #147, Variante b). Reine
 * Darstellungsmathematik (ADR-007): nur eine Zeit-Verschiebung, kein Fachurteil.
 *
 * - **(a) nur das aktive Modul:** die Eingabe-Marker gehören genau zum Modul
 *   `moduleIndex`; andere Module werden nie berührt.
 * - **(b) Modul-Offset:** modul-lokale Sekunden `t` liegen auf der Sequenzachse bei
 *   `starts_s[moduleIndex] + t`; die Fraktionen werden auf `total_s` normiert und
 *   `seekTime_s` trägt die verschobene Sequenz-Zeit (Klick bleibt im Modul).
 * - **(c) keine Marker über Umbaupausen:** die lokalen Zeiten liegen in
 *   `[0, duration]`, also innerhalb der Druckphase `[start, start+duration]` —
 *   die anschließende `umbau_s`-Pause bekommt konstruktionsbedingt nie einen Marker.
 *
 * Ein unbekannter `moduleIndex` (oder eine leere Zeitleiste) liefert `[]`.
 */
export function projectModuleMarkers<M extends ModuleLocalMarker>(
  markers: readonly M[],
  plan: SequencePlan,
  moduleIndex: number,
): M[] {
  const segment = plan.segments[moduleIndex];
  const start = plan.starts_s[moduleIndex];
  if (!segment || start == null || plan.total_s <= 0) return [];
  const duration = Math.max(0, segment.duration_s);
  const total = plan.total_s;
  return markers.map((m) => ({
    ...m,
    startFraction: clamp01((start + m.startFraction * duration) / total),
    endFraction: clamp01((start + m.endFraction * duration) / total),
    midFraction: clamp01((start + m.seekTime_s) / total),
    seekTime_s: start + m.seekTime_s,
  }));
}

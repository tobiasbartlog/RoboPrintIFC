/**
 * Toolpath-Rendering: je Schicht zwei Linienobjekte (print/travel), damit der
 * Layer-Slider und die Travel-Sichtbarkeit reine visibility-Schalter sind.
 * Print-Segmente tragen die Farbe des Ziel-Targets — Lehm-Terrakotta;
 * Travel bleibt zurückhaltend grau-blau.
 *
 * Zwei Aufdeck-Modi (ADR-007, reine Darstellung):
 * - **Layer-Modus** (`setVisibleUpTo`): Sichtbarkeit nach Schicht (Layer-Slider).
 * - **Wachs-Modus** (`setGrowth`, Issue #27): der gedruckte Strang wächst nach
 *   Trajektorien-**Zeit** — je Segment ist bekannt, an welchem Ziel-Target-Index
 *   es endet; sichtbar sind alle Segmente bis zum aktuellen Fraktions-Index.
 *   Innerhalb eines Layer/Art-Buckets sind die Segmente aufsteigend nach
 *   Target-Index abgelegt (build iteriert i aufsteigend), also ist der
 *   sichtbare Anteil ein zusammenhängendes Präfix → `geometry.setDrawRange`.
 *
 * Punktnummerierung (Issue #138, `setLabelsVisible`): optionale Sprite-Labels
 * an den „aussagekräftigen" Targets (print/travel-Wechsel, Ring-/Schicht-
 * anfänge — Auswahl + Dichte-Deckelung reine Funktionen in
 * `target-labels-state.ts`, vitest-getestet). Jedes Label folgt derselben
 * Layer-/Wachs-/Travel-Sichtbarkeit wie die Bahnlinien (`targetLabelVisible`),
 * damit keine Nummer einer ausgeblendeten Schicht in der Luft schwebt.
 */

import * as THREE from "three";
import type { Target, TargetKind, Toolpath } from "../artifacts/types";
import {
  targetLabelVisible,
  targetLabels,
  type ToolpathVisibilityState,
} from "./target-labels-state";

const PRINT_COLOR = 0xd2793f;
// Kräftiges Gelb statt Grau-Blau: Travel-Segmente sind oft nur wenige mm
// lang (Schalenwechsel, Schichtsprung) und sonst kaum von Wandkanten/Grid
// (ebenfalls grau-blau) zu unterscheiden.
const TRAVEL_COLOR = 0xffce3a;

// Punktnummerierung (Issue #138): dezentes dunkles Chip-Rund mit heller
// Ziffer — lesbar vor hellem wie dunklem Theme-Hintergrund, ohne mit der
// Print-/Travel-Farbgebung der Linien zu konkurrieren.
const LABEL_BG = "rgba(20, 22, 26, 0.78)";
const LABEL_FG = "#f4f1ea";
const LABEL_CANVAS_SIZE = 64;
/** Feste Weltgröße (mm) der Label-Sprites — kein Autoskalieren durch three.js. */
const LABEL_WORLD_SIZE_MM = 55;

/** Baut die Canvas-Textur eines Punktnummer-Labels (rundes Chip + Ziffern). */
function makeLabelSprite(text: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = LABEL_CANVAS_SIZE;
  canvas.height = LABEL_CANVAS_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const r = LABEL_CANVAS_SIZE / 2;
    ctx.fillStyle = LABEL_BG;
    ctx.beginPath();
    ctx.arc(r, r, r - 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = LABEL_FG;
    // Längere Nummern (vierstellig bei sehr langen Bahnen) etwas kleiner setzen,
    // damit sie im runden Chip nicht abgeschnitten wirken.
    const fontSize = text.length <= 2 ? 30 : text.length === 3 ? 24 : 18;
    ctx.font = `bold ${fontSize}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, r, r + 1);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true }),
  );
  sprite.renderOrder = 3; // über den (ebenfalls depthTest:false) Travel-Linien
  sprite.scale.set(LABEL_WORLD_SIZE_MM, LABEL_WORLD_SIZE_MM, 1);
  return sprite;
}

/** Ein platziertes Nummern-Label + die Daten, die seine Sichtbarkeit steuern. */
interface LabelEntry {
  index: number;
  layer: number;
  kind: TargetKind;
  sprite: THREE.Sprite;
}

/** Ein Linienobjekt eines Layer/Art-Buckets + der Ziel-Target-Index je Segment. */
interface KindLines {
  lines: THREE.LineSegments;
  /** Ziel-Target-Index je Segment (aufsteigend), 1:1 zu je 2 Positionen. */
  destIdx: number[];
}

interface LayerLines {
  print: KindLines | null;
  travel: KindLines | null;
}

/** Anzahl Elemente in aufsteigend sortiertem `arr`, die ≤ `x` sind (Binärsuche). */
function countUpTo(arr: number[], x: number): number {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (arr[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export class ToolpathView {
  readonly group = new THREE.Group();
  readonly maxLayer: number;
  private readonly layers = new Map<number, LayerLines>();
  private travelVisible = true;
  private visibleUpTo: number;
  private onlyCurrent = false;
  // Wachs-Modus (Issue #27): aktiv, sobald `setGrowth` gerufen wurde; der
  // Layer-Slider (`setVisibleUpTo`) schaltet ihn wieder ab.
  private growthMode = false;
  private growthIndex = 0;
  // Punktnummerierung (Issue #138): Standard AUS (⚙-Schalter „Punktnummern"),
  // konsistent zu „Wachsender Druckstand" — aus lässt die Bühne unverändert.
  private readonly labelsGroup = new THREE.Group();
  private readonly labelEntries: LabelEntry[] = [];
  private labelsEnabled = false;

  constructor(toolpath: Toolpath) {
    this.group.name = `toolpath:${toolpath.wall_global_id}`;
    // Schichtzahl aus dem vorberechneten Summary lesen (Core rechnet, ADR-007);
    // Fallback für alte Läufe (schema_version 0.1, ohne summary): selbst ableiten.
    this.maxLayer = toolpath.summary
      ? toolpath.summary.n_layers - 1
      : toolpath.targets.reduce((m, t) => Math.max(m, t.layer), 0);
    this.visibleUpTo = this.maxLayer;
    this.build(toolpath.targets);
    this.labelsGroup.name = "toolpath-labels";
    this.buildLabels(toolpath.targets);
    this.group.add(this.labelsGroup);
    this.apply();
  }

  /** Baut die Nummern-Sprites der aussagekräftigen Punkte (Issue #138, reine Auswahl in target-labels-state.ts). */
  private buildLabels(targets: Target[]): void {
    for (const label of targetLabels(targets)) {
      const sprite = makeLabelSprite(String(label.index + 1));
      sprite.position.set(label.pos_mm[0], label.pos_mm[1], label.pos_mm[2]);
      sprite.visible = false;
      this.labelsGroup.add(sprite);
      this.labelEntries.push({ index: label.index, layer: label.layer, kind: label.kind, sprite });
    }
  }

  /** Segment i verbindet Target i-1 mit Target i; Layer/Art kommen vom Ziel. */
  private build(targets: Target[]): void {
    const byLayerKind = new Map<string, { positions: number[]; destIdx: number[] }>();
    for (let i = 1; i < targets.length; i++) {
      const from = targets[i - 1].frame.pos_mm;
      const to = targets[i].frame.pos_mm;
      const key = `${targets[i].layer}:${targets[i].kind}`;
      let bucket = byLayerKind.get(key);
      if (!bucket) byLayerKind.set(key, (bucket = { positions: [], destIdx: [] }));
      bucket.positions.push(...from, ...to);
      bucket.destIdx.push(i);
    }

    for (const [key, { positions, destIdx }] of byLayerKind) {
      const [layerStr, kind] = key.split(":");
      const layer = Number(layerStr);
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      // Gedruckte Bahnen im Akzent-Streifenmuster (Scheibe 9, #113): gestrichelt
      // (LineDashed) statt durchgezogen — der gedruckte Strang liest sich als
      // Materialauftrag. Travel bleibt durchgezogen (kräftiges Gelb).
      const isPrint = kind === "print";
      const lines = new THREE.LineSegments(
        geometry,
        isPrint
          ? new THREE.LineDashedMaterial({
              color: PRINT_COLOR,
              dashSize: 7,
              gapSize: 3.5,
            })
          : new THREE.LineBasicMaterial({
              color: TRAVEL_COLOR,
              // Travel-Segmente sind oft nur wenige mm lang und liegen direkt an
              // der (opaken, depth-schreibenden) Wandkante -> ohne depthTest
              // rendern, sonst werden sie von der Kante verdeckt/unsichtbar.
              depthTest: false,
            }),
      );
      if (isPrint) lines.computeLineDistances();
      lines.renderOrder = kind === "travel" ? 1 : 0;
      const entry = this.layers.get(layer) ?? { print: null, travel: null };
      entry[kind as "print" | "travel"] = { lines, destIdx };
      this.layers.set(layer, entry);
      this.group.add(lines);
    }
  }

  setVisibleUpTo(layer: number, onlyCurrent: boolean): void {
    this.growthMode = false;
    this.visibleUpTo = layer;
    this.onlyCurrent = onlyCurrent;
    this.apply();
  }

  setTravelVisible(visible: boolean): void {
    this.travelVisible = visible;
    this.apply();
  }

  /**
   * Wachs-Modus (Issue #27): deckt den gedruckten Strang bis zum Fraktions-
   * Index `targetIndex` (∈ [0, n-1], darf gebrochen sein) auf — synchron zur
   * Trajektorien-Zeit. `Infinity` = ganzer Abschnitt sichtbar (bereits
   * gedruckt), negative Werte = nichts sichtbar (noch nicht an der Reihe).
   * Travel-Segmente erzeugen keinen Strang, folgen aber demselben Fortschritt
   * (und dem Travel-Schalter), damit die Ansicht konsistent ist.
   */
  setGrowth(targetIndex: number): void {
    this.growthMode = true;
    this.growthIndex = targetIndex;
    this.apply();
  }

  /**
   * ⚙-Schalter „Punktnummern" (Issue #138): schaltet die Nummern-Labels
   * global ein/aus. Auch eingeschaltet bleibt ein Label nur sichtbar, wenn
   * sein Target nach dem aktuellen Layer-/Wachs-/Travel-Zustand ohnehin
   * sichtbar wäre (`targetLabelVisible`) — kein Sonderfall gegenüber den Linien.
   */
  setLabelsVisible(visible: boolean): void {
    this.labelsEnabled = visible;
    this.apply();
  }

  private visibilityState(): ToolpathVisibilityState {
    return {
      growthMode: this.growthMode,
      growthIndex: this.growthIndex,
      visibleUpTo: this.visibleUpTo,
      onlyCurrent: this.onlyCurrent,
      travelVisible: this.travelVisible,
    };
  }

  private applyLabels(): void {
    if (this.labelEntries.length === 0) return;
    const state = this.visibilityState();
    for (const l of this.labelEntries) {
      l.sprite.visible = targetLabelVisible(l, this.labelsEnabled, state);
    }
  }

  private apply(): void {
    this.applyLabels();
    for (const [layer, entry] of this.layers) {
      for (const kind of ["print", "travel"] as const) {
        const k = entry[kind];
        if (!k) continue;
        const total = k.destIdx.length;
        let count: number;
        let visible: boolean;
        if (this.growthMode) {
          count = countUpTo(k.destIdx, this.growthIndex);
          visible = count > 0 && (kind === "print" || this.travelVisible);
        } else {
          const layerOn = this.onlyCurrent
            ? layer === this.visibleUpTo
            : layer <= this.visibleUpTo;
          count = total;
          visible = layerOn && (kind === "print" || this.travelVisible);
        }
        k.lines.visible = visible;
        k.lines.geometry.setDrawRange(0, count * 2);
      }
    }
  }
}

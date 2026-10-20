import type { PartArtifact, Scene, Toolpath } from '../contracts';
import type { PrintedState, PrintProgress } from './progress';

/**
 * Einheiten der 3D-Szene: Millimeter, Z oben (wie die Artefakte, SPEC §2). Es gibt keine
 * Umrechnung zwischen Artefakt und Szene. Nur die URDF ist in Metern und liegt deshalb unter
 * einer Gruppe mit Skalierung 1000; das Werkzeug-Mesh haengt in einem Anker mit Skalierung
 * 1/1000 am Flansch und ist damit wieder in mm.
 */

/** Pose [x, y, z, qw, qx, qy, qz] in mm, Quaternion (w, x, y, z). */
export type Pose7 = [number, number, number, number, number, number, number];

/** 4x4-Matrix zeilenweise wie in den Artefakten (Spaltenvektoren, p_A = T_AB * p_B). */
export type Mat4Rows = readonly (readonly number[])[];

export type SceneStatus = 'ok' | 'warn' | 'collision' | 'unreachable';

/** Ein Sample der Trajektorie, so wie die Szene es braucht. */
export interface SceneSample {
  q: readonly number[];
  tcp: readonly number[];
  /** Kollisions-Druckstand k (Artefakt `layer[i]`): Hindernis der Pruefung, nicht die Anzeige. */
  layer: number;
  /**
   * Was bis zu diesem Sample gedruckt ist (`progress.ts`); daraus zeigt die Szene Volumen und Strang.
   * Fehlt es, zeigt das Teil k Schichten (`layer`).
   */
  printed?: PrintedState | null;
  status: SceneStatus;
  /** [Glied, Hindernis] des kritischen Paars, z. B. ['link_3', 'printed']. */
  pair: readonly [string, string] | null;
  /** Zeugenpunkte in W (mm). */
  witness: readonly [readonly number[], readonly number[]] | null;
  /** Abstand in mm (optional, nur fuer die Beschriftung der Kontaktlinie). */
  d_mm?: number | null;
}

export interface LoadedPart {
  part: PartArtifact;
  /** Absolute oder relative URL von part.stl (Frame P). */
  stlUrl: string;
  toolpath?: Toolpath | null;
  /** Druckfortschritt der Trajektorie (`printProgress`), fuer Strang und Volumen. */
  progress?: PrintProgress | null;
}

/** Geladener Lauf: scene.json plus die Teile, die der Viewer zeigen kann. */
export interface LoadedRun {
  scene: Scene;
  parts: Record<string, LoadedPart>;
}

export interface SceneApi {
  /** Gerenderte TCP-Pose in W (mm) aus dem Szenengraphen, oder null solange der Roboter laedt. */
  tcpRendered: () => Pose7 | null;
  /** Gelenkwinkel, die der Roboter im Szenengraphen gerade zeigt (rad), oder null. */
  jointValues: () => number[] | null;
  /** True, sobald Roboter, Tisch und Werkzeug geladen sind. */
  ready: () => boolean;
  /** Richtet die Kamera auf einen Punkt in W (mm) aus. */
  focusOn: (p: readonly [number, number, number]) => void;
}

export interface SceneViewProps {
  run: LoadedRun | null;
  partId: string | null;
  sample: SceneSample | null;
  highlightedLinks: string[];
  obstacleVisible: boolean;
  /** Basis-URL der Assets; Default `/api/assets`. */
  assetBase?: string;
  showToolpath?: boolean;
  onApi?: (api: SceneApi | null) => void;
}

/**
 * TypeScript-Spiegel der Artefakt-Schemas (schemas/*.schema.json).
 * Der Viewer liest diese Strukturen nur — er berechnet nichts (ADR-007).
 */

export interface Provenance {
  source: string;
  created: string;
  git_commit: string;
}

export interface Frame {
  pos_mm: [number, number, number];
  quat: [number, number, number, number];
}

export type TargetKind = "print" | "travel";

export interface Target {
  frame: Frame;
  v_mm_s: number;
  io: Record<string, number>;
  kind: TargetKind;
  layer: number;
  segment_id: string;
}

/** Vorberechnete Kennzahlen; der Core rechnet, der Viewer liest nur (ADR-007). */
export interface ToolpathSummary {
  n_layers: number;
  n_targets: number;
  n_print: number;
}

/**
 * Slice-Parameter des Laufs (ab schema_version 0.3, Issue #9).
 * Einstiegspunkt für das Viewer-Parameter-Panel: Panel liest diese Werte
 * als Ausgangswerte, leere Felder = Karten-Default (ADR-014).
 */
export interface ToolpathParams {
  model_path: string;
  layer_height_mm: number;
  strand_width_mm: number;
  n_shells: number;
}

export interface Toolpath {
  schema_version: string;
  provenance: Provenance;
  wall_global_id: string;
  targets: Target[];
  /** Ab schema_version 0.2; ältere Läufe (0.1) haben ihn nicht -> Fallback. */
  summary?: ToolpathSummary;
  /** Ab schema_version 0.3: Slice-Parameter für das Parameter-Panel (Issue #9). */
  params?: ToolpathParams;
}

export interface WallSpec {
  schema_version: string;
  provenance: Provenance;
  global_id: string;
  name?: string;
  geometry: {
    vertices_mm: number[][];
    faces: number[][];
  };
  openings?: unknown[];
  targets: Record<string, unknown>;
}

export interface ContextElement {
  global_id: string;
  ifc_type: string;
  name?: string;
  geometry: {
    vertices_mm: number[][];
    faces: number[][];
  };
}

export interface BuildingContext {
  schema_version: string;
  provenance: Provenance;
  model: string;
  /** Nur bei Slice-Läufen gesetzt (die ausgeschlossene Wand). Fehlt im Übersichts-Lauf (Issue #17). */
  wall_global_id?: string;
  elements: ContextElement[];
}

/** Ein Zuordnungseintrag aus model_map.json: GLB-Szenenknoten <-> GlobalId. */
export interface ModelMapEntry {
  node: string;
  global_id: string;
}

/**
 * GlobalId-Zuordnung zur binären Modell-glTF (model_map.json, Issue #6).
 * Die Geometrie selbst liegt binär in `mesh_file` (model.glb); dieses Artefakt
 * bindet jeden Szenenknoten an die GlobalId seiner Wand, damit der Viewer die
 * GLB-Knoten nach Eignung einfärben kann (ADR-007: der Viewer rechnet nichts).
 */
export interface ModelMap {
  schema_version: string;
  provenance: Provenance;
  model: string;
  mesh_file: string;
  walls: ModelMapEntry[];
}

/** Einzelner Kandidaten-Check aus candidates.json. */
export interface CandidateCheck {
  check: string;
  passed: boolean;
  provisional?: boolean;
  reason?: string;
}

/** Eine Wand im candidates.json mit Eignungsurteil. */
export interface Candidate {
  global_id: string;
  /** Wand-Anzeigename aus IFC (optional, fehlt bei älteren Artefakten). */
  name?: string;
  eligible: boolean;
  checks: CandidateCheck[];
}

/** Eignungsprüfungs-Artefakt (candidates.json). */
export interface Candidates {
  schema_version: string;
  provenance: Provenance;
  model: string;
  walls: Candidate[];
}

/** Ein Sample der Trajektorie (zeitparametriert). */
export interface TrajectorySample {
  t_s: number;
  joints_rad: [number, number, number, number, number, number];
  io: Record<string, number>;
}

/** Kinematik-Warnung aus der Simulation (Issue #12). */
export interface TrajectoryWarning {
  t_s: number;
  kind: "singularity" | "joint_limit" | "reach" | "other";
  message: string;
}

/**
 * Kollisions-Befund der Kollisionskontrolle (ADR-024, Issue #127/#128) — spiegelt
 * `meta.collision` aus `schemas/trajectory.schema.json`. **Rein additiv & optional:**
 * Altläufe und Simulationen ohne Kollisionsgeometrie LASSEN den Block ganz weg
 * (nicht `null`). Der Viewer zeigt ihn nur **verbatim** an (ADR-007, kein
 * Viewer-Geometrieurteil): Abstandskurve, Verursacher und Intervalle liegen als zu
 * `samples` PARALLELE Arrays vor, damit `samples` byte-gleich bleibt.
 */
export interface CollisionConfig {
  safety_distance_mm: number;
  freizone_radius_mm: number;
  provisional: boolean;
  context_enabled?: boolean;
  mode?: "abschnitt" | "modul";
}

/** Ein verdichtetes Kollisions-/Warn-Intervall (zusammenhängende Samples). */
export interface CollisionInterval {
  status: "red" | "yellow" | "green";
  start_index: number;
  end_index: number;
  min_distance_mm?: number | null;
  worst_index?: number;
  link?: number | null;
  against?: string | null;
}

/** `meta.collision` — vollständiger Kollisions-Befund eines Laufs (verbatim). */
export interface CollisionMeta {
  config: CollisionConfig;
  min_distance_mm: number | null;
  worst_index?: number;
  n_red: number;
  n_yellow: number;
  n_green: number;
  tool_provisional?: boolean;
  /** Abstandskurve: minimaler Abstand je Sample (mm), parallel zu `samples`; null = außerhalb Prüfnähe. */
  distances_mm: (number | null)[];
  /** Verursachendes Glied je Sample (0..6, 7 = Endeffektor), parallel zu `samples`. */
  causer_link?: (number | null)[];
  /** Verursachendes Hindernis je Sample (z. B. 'current_part', 'ground'), parallel zu `samples`. */
  causer_against?: (string | null)[];
  intervals: CollisionInterval[];
  /** Index-Bereiche [start,end] der Travel-Abschnitte (nicht lückenlos geprüft). */
  travel_intervals?: [number, number][];
  travel_not_continuously_checked?: boolean;
}

/** Meta-Block der Trajectory (Gesamtdauer, Achsauslastung, Warnungen). */
export interface TrajectoryMeta {
  duration_s: number;
  io_compensated: boolean;
  /**
   * Lagequelle Wand↔Roboterbasis (Issue #26): 'measured' = gemessenes Setup
   * (Antast-Verfahren, Voraussetzung des echten Drucks); 'planned' = geplante
   * Platzierung (nur Simulation). Fehlt bei Altläufen → implizit 'measured'.
   */
  pose_source?: "planned" | "measured";
  /**
   * Roboterbasis im Wandsystem (base_in_wall = invert(wall_to_base)) — fester
   * Replay-Anker (Issue #66). Der Viewer verankert den Arm damit fix an der
   * geplanten Lage; die Gelenke fahren die Bahn ab, der TCP druckt. Fehlt bei
   * Altläufen → Legacy-Anker (Basis pro Frame ans Ziel gelegt).
   */
  base_frame?: Frame;
  /**
   * Echte Höhenlage des simulierten Abschnitts (Issue #135): z0 (mm) des
   * Abschnittsfußes über dem Boden (= Wandfuß). Toolpath/Trajektorie liegen
   * abschnitts-lokal (z ab Abschnittsfuß); der Viewer hebt die Replay-Szene
   * um diesen Wert auf die echte Bandlage. Fehlt bei Altläufen und bei
   * Zerlegungsart Modul (Druckort = Workstation) — dann gilt 0.
   */
  section_z0_mm?: number;
  axis_utilization?: [number, number, number, number, number, number];
  warnings?: TrajectoryWarning[];
  /**
   * Kollisions-Befund (ADR-024, Issue #127/#128) — additiv & optional. Fehlt bei
   * Altläufen und Läufen ohne Kollisionsgeometrie; der Viewer muss das Fehlen
   * anstandslos verkraften (ehrliche Statuszeile bleibt, keine Marker/Badges).
   */
  collision?: CollisionMeta;
}

/** Ausführbare Bewegung als Zeitreihe (trajectory.json, Issue #12). */
export interface Trajectory {
  schema_version: "0.1";
  provenance: Provenance;
  samples: TrajectorySample[];
  meta: TrajectoryMeta;
}

/** Inhalt eines geladenen Laufordners; Artefakte sind einzeln optional. */
export interface RunData {
  folderName: string;
  wallspec: WallSpec | null;
  toolpath: Toolpath | null;
  context: BuildingContext | null;
  /** GlobalId-Zuordnung zur Modell-glTF (walls-list-Läufe, Issue #6). */
  modelMap: ModelMap | null;
  /** URL der binären model.glb (fetch-/Objekt-URL); nur wenn modelMap vorliegt. */
  modelGlbUrl: string | null;
  /** Eignungsprüfungs-Ergebnisse; fehlt bei slice-Läufen. */
  candidates: Candidates | null;
  /** Zeitparametrierte Trajektorie (Issue #14); fehlt wenn fgc simulate nicht lief. */
  trajectory: Trajectory | null;
}

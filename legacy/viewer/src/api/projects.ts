/**
 * Lokale Core-API (ADR-014/016): dünner Fetch-Wrapper um die Projekt-Endpoints.
 *
 * Das Projekt ist die langlebige Persistenz-Einheit (ADR-016); der Viewer hält
 * keinen Fachzustand (ADR-007), er ruft nur GET/POST /projects und lädt danach
 * den referenzierten Übersichts-Lauf als Artefakte. HTTP-Transport, Fehler-
 * Mapping und `API_URL` liegen seit #118 einmal in `./http` ({@link request}).
 */

import type { Revisions, RevisionSnapshot } from "../ui/staleness";
import { request } from "./http";

/** Kurzinfo eines Projekts für die Projektliste (GET /projects). */
export interface ProjectSummary {
  slug: string;
  name: string;
  model_path: string;
  n_print_jobs: number;
}

/** Ein Druckjob im Projekt (project.json → print_jobs). */
export interface PrintJob {
  job_id: string;
  wall_global_id: string;
  /** Anzeigename der Wand (optional, nur für die UI-Anzeige). */
  wall_name?: string;
  /** Verweis auf den Übersichts-Lauf mit Eignungsbefunden (absoluter Pfad). */
  assessment_run?: string;
  /** Name der Roboterdefinition — Laufparameter, kein Setup (ADR-006, Issue #20). */
  robot?: string;
  /** Name der Endeffektor-Definition — Laufparameter (Issue #21). */
  tool?: string;
  /** Name der gewählten Workstation-Definition — Aufstell-Umgebung (Issue #77, PRD #69).
   *  Additiv/optional; veraltet KEINE Outputs (Seam zu #70 — die Werte konsumiert
   *  erst der Druckplan-Automatismus). */
  workstation?: string;
  /** Aufstell-Toggle (Issue #81, PRD B/#70): 'floor' (Roboter am Boden) | 'elevated'
   *  (darf erhöht stehen). Begrenzt den Podesthöhen-Satz, den die Abschnittssuche
   *  nutzen darf. Additiv/optional; fehlt das Feld (Altprojekt), gilt 'floor'. */
  stand_mode?: "floor" | "elevated";
  /** Gebäudekontext-Schalter der Kollisionskontrolle (Issue #131, ADR-024): steht
   *  `true`, prüft die Simulation den Arm zusätzlich gegen den Gebäudekontext
   *  (context.json). Additiv/optional; fehlt das Feld (Altprojekt), gilt `false`
   *  (aus). Bei Zerlegungsart Modul gegenstandslos. */
  check_building_context?: boolean;
  /** Erfasste Aufstellmöglichkeiten — Plan-Eingaben, keine Scores (Issue #22, ADR-016).
   *  Seit Issue #134 nur noch lesbar (Altprojekte, Override-Referenzen #94a) —
   *  der Gesamtwand-Vorschlag wird nicht mehr angestoßen/angezeigt. */
  placements?: PlacementOption[];
  /** option_id der gewählten Aufstellmöglichkeit — Altprojekte (Issue #22/#134). */
  selected_placement?: string | null;
  /** Verweis auf den Bewertungslauf (placement.json) — Altprojekte (Issue #22/#134). */
  placement_run?: string;
  /** Zerlegungsart (Issue #24/#95): 'abschnitt' (vor Ort drucken) oder 'modul'
   *  (an der Workstation vorproduzieren, ADR-022). */
  decomposition_kind?: "abschnitt" | "modul";
  /** Optionale Obergrenzen der Modulgröße (Issue #90) — sparse; wirken nur bei
   *  Art 'modul'. Fehlt der Block (Altprojekt), begrenzt nur der Arbeitsraum. */
  module_limits?: { max_length_mm?: number; max_height_mm?: number };
  /** Zielfunktion der Zerlegungs-Suche (Issue #212, PRD #183) — sparse; fehlt der
   *  Block (Altprojekt/Default), gilt die gepinnte Default-Config (lexikographisch,
   *  Umsetzvorgänge > Fugenfläche > kinematische Marge > c_v). */
  objective?: ObjectiveSettings;
  /** Schnittebenen des Zerlegungsvorschlags — Plan-Eingaben, keine Ampeln (Issue #24/#25). */
  cuts?: Cut[];
  /** Fugen-Versatz zwischen Höhenlagen (Issue #25) — wirkt nur auf vertikale Schnitte. */
  joint_offset_mm?: number;
  /** Platzierungs-Overrides je Abschnitt (Issue #25) — Plan-Eingabe. */
  section_overrides?: SectionOverride[];
  /** Verweis auf den Zerlegungslauf (decompose.json) mit Abschnitten + Ampeln (Issue #24). */
  decompose_run?: string;
  /** Je Abschnitt ein Verweis auf den Slice+Simulations-Lauf (Issue #26). */
  section_runs?: SectionRun[];
  /** Prozessparameter des Druckjobs (Scheibe 2, Issue #59) — Wahrheitsquelle der
   *  Slice-Basisparameter; fehlt der Block, gelten Karten-/Code-Defaults. */
  process_params?: ProcessParams;
  /** Revisionsstände der Prozessstufen für die veraltet-Markierung (Issue #29). */
  revisions?: Revisions;
  /** Letzter Stand der Stufe-2-Prüf-Tür (Issue #175): WAS zuletzt geprüft wurde
   *  (global vs. Fokus) + der Eingabe-Schnappschuss. Fehlt (noch nie geprüft) ⇒
   *  „ungeprüft". Additiv/optional. */
  last_pruef?: LastPruef;
  runs?: string[];
}

/** Letzter Stufe-2-Prüf-Tür-Stand am Druckjob (Issue #175). */
export interface LastPruef {
  /** 'global' = ganze Wand geprüft, 'focus' = nur die Höhenreihe des Fokus-Teils. */
  scope: "global" | "focus";
  /** section_id des geprüften Fokus-Teils (bei scope==='focus'), sonst null. */
  section_id?: string | null;
  /** Eingabe-Zähler-Schnappschuss zum Prüfzeitpunkt — gegen die aktuellen Zähler
   *  vergleicht `pruefStatus` (veraltet der letzte Prüfstand?). */
  input_snapshot?: RevisionSnapshot;
}

/** Basis-Slice-Parameter (Scheibe 2, Issue #59; #60) — nur gesetzte Felder überschreiben
 *  die Karte/Code-Defaults; ungesetzte fallen darauf zurück.
 *
 *  Die „Fortgeschritten"-Felder (Issue #60) sind bisher unkonfigurierbare, aber
 *  existierende Slice-Werte: `v_print_mm_s`/`v_travel_mm_s` (Bahngeschwindigkeit je
 *  Zielart) und `io_print`/`io_travel` (io-Skalar je Zielart — der Core dehnt ihn
 *  gleichförmig auf alle io-Kanäle aus). */
export interface SliceParams {
  layer_height_mm?: number;
  strand_width_mm?: number;
  n_shells?: number;
  v_print_mm_s?: number;
  v_travel_mm_s?: number;
  io_print?: number;
  io_travel?: number;
}

/** Bahn-relativer Anstellwinkel der Düse (Scheibe 3, Issue #61) — Grad. Nur gesetzte
 *  Felder überschreiben; 0/0 (bzw. fehlend) = senkrecht von oben (heutiges Verhalten). */
export interface OrientationParams {
  lead_deg?: number;
  kipp_deg?: number;
}

/** Der Zustand einer IK-Konfigurationsachse (Issue #129, ADR-024): `"a"` = Zustand A,
 *  `"b"` = Zustand B; fehlend = auto (kein Constraint, Default). */
export type IkAxisState = "a" | "b";

/** Wählbare IK-Konfiguration (Issue #129, ADR-024) — drei Tri-State-Schalter
 *  Schulter/Ellbogen/Handgelenk. Gesetzte Achsen filtern die 8 IK-Lösungszweige
 *  (Bitschema `opw.py`: SHOULDER=1/ELBOW=2/WRIST=4) hart; fehlend = auto. */
export interface IkConfig {
  shoulder?: IkAxisState;
  elbow?: IkAxisState;
  wrist?: IkAxisState;
}

/** Abschnitts-Override der Gradierungs-Ebene (Druckplan S3, Issue #82; ik_config
 *  #129) — je Abschnitt dieselben sparse Gruppen wie global; nur gesetzte Felder
 *  übersteuern, ungesetzte erben global (`resolveSectionParams`). */
export interface SectionProcessOverride {
  slice?: SliceParams;
  orientation?: OrientationParams;
  ik_config?: IkConfig;
}

/** Prozessparameter-Block eines Druckjobs (Rail für spätere Gruppen, Issue #59/#61).
 *
 *  `sections` (Issue #82) bildet `section_id` → Abschnitts-Override ab: die
 *  Gradierungs-Ebene, auf der jeder Abschnitt jeden Parameter individuell
 *  übersteuern darf; fehlt der Block (Altprojekt), erbt jeder Abschnitt global.
 *  `ik_config` (Issue #129) ist die global wählbare IK-Konfiguration. */
export interface ProcessParams {
  slice?: SliceParams;
  orientation?: OrientationParams;
  ik_config?: IkConfig;
  sections?: Record<string, SectionProcessOverride>;
}

/** Antwort auf POST /projects/{slug}/sections/{section_id}/export (Issue #29). */
export interface ExportDrlResult {
  slug: string;
  job_id: string;
  section_id: string;
  /** Abschnitts-Lauf, in dem die program.drl liegt (ADR-004). */
  run_dir: string;
  /** Pfad der geschriebenen program.drl. */
  drl_path: string;
  /** true = vollständiges (lauffähiges) DRL; false = gekennzeichnete Ausgabe (Stub). */
  complete: boolean;
  /**
   * Herkunft des Setups (Issue #136), ehrlich benannt:
   * - 'measured' — Antast-Setup im Lauf (Art „abschnitt")
   * - 'none' — Antasten fehlt noch (Art „abschnitt")
   * - 'generated' — aus Stammdaten generiert (Art „modul", ADR-022)
   * - 'generated_incomplete' — Art „modul", Stammdaten fehlen/provisorisch
   */
  setup_source: "measured" | "none" | "generated" | "generated_incomplete";
  /** Hinweis/Fehlbestand, wenn unvollständig (sonst ""). */
  note: string;
  n_samples: number;
  print_jobs: PrintJob[];
}

/** Verweis auf den Slice+Simulations-Lauf eines Abschnitts (Issue #26). */
export interface SectionRun {
  section_id: string;
  /** Laufordner-Pfad des Abschnitts-Laufs (toolpath.json + trajectory.json). */
  run: string;
}

/** Antwort auf POST /projects/{slug}/sections/{section_id}/simulate (Issue #26). */
export interface SimulateSectionResult {
  slug: string;
  job_id: string;
  section_id: string;
  /** Laufordner des Abschnitts-Laufs (toolpath.json + trajectory.json, ADR-004). */
  run_dir: string;
  /** Lagequelle: immer 'planned' (Simulation aus der Platzierung). */
  pose_source: "planned" | "measured";
  /** Druckzeitschätzung (s) — Gesamtdauer der Trajektorie. */
  duration_s: number;
  n_targets: number;
  n_warnings: number;
  io_compensated: boolean;
  /** Achsauslastung je Achse (0..1). */
  axis_utilization: number[];
  warnings: { t_s: number; kind: string; message: string }[];
  print_jobs: PrintJob[];
}

/** Eine achsparallele Schnittebene im Wand-System (Issue #24). */
export interface Cut {
  /** 'horizontal' = Ebene bei z=position_mm (Höhenstufe); 'vertical' = bei x (Längenteilung). */
  orientation: "horizontal" | "vertical";
  position_mm: number;
}

/**
 * Platzierungs-Override eines Teils — zwei additive Formen (Issue #25/#94):
 * `option_id` referenziert eine erfasste Aufstellmöglichkeit (Bewertungsmodus,
 * Issue #22); die freien Felder (Issue #94: seitlich/Abstand/Aufstellhöhe,
 * sparse) übersteuern feldweise die automatische bzw. referenzierte
 * Platzierung — leer = erbt (automatische Platzierung).
 */
export interface SectionOverride {
  section_id: string;
  option_id?: string;
  lateral_mm?: number;
  standoff_mm?: number;
  stand_height_mm?: number;
}

/** Freie Platzierungswerte eines Teil-Overrides (Issue #94), sparse. */
export interface PlacementOverrideValues {
  lateral_mm?: number;
  standoff_mm?: number;
  stand_height_mm?: number;
  /**
   * Issue #173: `true` bewahrt zuvor gesetzte freie Override-Felder und legt nur
   * die hier gesetzten Werte feldweise darüber (Anwenden-Pfad einer Einzelfeld-
   * Option des Kollisions-Advisors: Abstand ODER Aufstellhöhe). Fehlt/`false` =
   * Neuaufbau (manuelles Formular — ein weggelassenes Feld wird abgeräumt).
   */
  merge?: boolean;
}

/**
 * Sicherheitsabstands-Befund eines frei übersteuerten Teils (Issue #94): Abstand
 * vor der Wandfront gegen den Workstation-Mindestabstand (#77) — Befund, kein
 * Gate (der Viewer zeigt, der Core urteilt, ADR-007).
 */
export interface PlacementCheck {
  standoff_mm: number;
  safety_min_distance_mm: number;
  below_min_distance: boolean;
}

/** Ampel-Befund eines Abschnitts — reine Daten, kein Gate (Issue #24). */
export interface SectionStatus {
  /** grün (voll erreichbar) / rot. */
  reachable: boolean;
  reachable_fraction: number;
  n_samples: number;
  n_reachable: number;
  kinematic_margin: number | null;
  mean_margin: number | null;
  warnings: { kind: string; target_index: number; detail: string; value: number | null }[];
}

/**
 * Befund zu genau einer Modul-Obergrenze (Issue #90): eingehalten oder verletzt,
 * nie ein Gate. `exceeded` ist strikt `actual_mm > limit_mm` (exakt auf der
 * Grenze = eingehalten).
 */
export interface LimitFinding {
  limit: "max_length" | "max_height";
  limit_mm: number;
  actual_mm: number;
  exceeded: boolean;
}

/**
 * Modulgrenzen-Befund eines Teils bei Zerlegungsart „modul" (Issue #90/#95, S6):
 * Gewicht (Volumen × Dichte) + je gesetzter Obergrenze ein {@link LimitFinding}
 * — verbatim aus dem Zerlegungslauf (decompose.json), **Befund, kein Gate**
 * (ADR-022). Bei Art „abschnitt"/Altlauf nicht vorhanden.
 */
export interface ModuleCheck {
  weight_kg: number;
  density_kg_m3: number;
  /** Nur Einträge für tatsächlich gesetzte Obergrenzen (keine Grenzen → leer). */
  limits: LimitFinding[];
}

/**
 * Lage eines Moduls am Druckort (Issue #96, ADR-021/022) — vom Core gerechnet
 * (`fgc.decompose.module_pose`, Invertierung der Relativpose-Leserichtung):
 * `workstation` = Modul-Frame in Workstation-(Mesh-)Koordinaten (dort leben
 * Mesh + `robot_base_frame`), `on_surface` = dieselbe Pose relativ zur
 * Arbeitsfläche. Nur bei Art „modul" UND Workstation mit Platzierungs-Frames
 * vorhanden (additiv) — sonst zeigt der Viewer einen Hinweis, kein Gate.
 */
export interface ModulePose {
  workstation: Frame;
  on_surface: Frame;
}

/**
 * Druckbarkeits-Urteil eines Teils (Issue #164, Karte #139/#141 Scheibe 3) —
 * verheiratet Freigang (#163) und repräsentative Prüf-Tür (#162) zu **einem**
 * sichtbaren Urteil je Teil, verbatim aus dem Zerlegungslauf (decompose.json).
 *
 * **Ehrlichkeit (Kern des Issues):** `verdict === "printable"` (grün) sagt **nur**,
 * was die Prüf-Tür wirklich frei gesehen hat — ein stummer Freigang-Befund wird nie
 * grün (S6-Lehre). `presumed` (,vermutlich') kennzeichnet ein **geerbtes** Reihen-
 * Urteil: nicht dieses Teil, sondern die ungünstigste Zelle seiner Höhenreihe
 * (`representative_id`) wurde geprüft — es darf nicht wie ein geprüftes aussehen.
 * **Befund, kein Gate** (ADR-013). Nur bei echtem Urteil vorhanden (additiv).
 */
export interface PartPrintability {
  /** 'printable' = Prüf-Tür sah es frei (grün); 'collides' = Prüf-Tür sah eine
   *  Kollision; 'too_thick' = Wand schon nach Freigang zu dick (teure Prüfung
   *  entfiel); 'too_tall' = Teil schon nach der zweiten Stufe-1-Schranke zu hoch für
   *  die freie Länge (Issue #209, Gl. 9 Stamatopoulos; teure Prüfung entfiel; wie
   *  `too_thick` rot, aber `presumed`); 'unknown' = kein Urteil (,ungeprüft', mit `reason`). */
  verdict: "printable" | "collides" | "too_thick" | "too_tall" | "unknown";
  /** Grund eines ,ungeprüft'-Urteils: 'no_geometry' = Prüf-Tür unzuständig
   *  (Altprojekt/keine Kollisions-Geometrie, Issue #170), 'error' = Prüfung
   *  fehlgeschlagen (geloggt, #170), 'unreachable' = Reihe ohne erreichbaren
   *  Repräsentanten (kein Erben von einer eingefrorenen Trajektorie, Issue #174/B13),
   *  'unchecked' = die teure Stufe-2-Prüf-Tür wurde für dieses Teil (noch) NICHT
   *  angestoßen (Issue #175: sie verlässt den interaktiven Loop, läuft nur auf
   *  expliziten Anstoß/asynchron) — der ehrliche Ruhezustand nach einem Schnitt-Edit.
   *  Nur bei verdict === 'unknown'. Alle bleiben ,ungeprüft', nie ,frei'. */
  reason?: "no_geometry" | "error" | "unreachable" | "unchecked" | null;
  /** true = ,vermutlich' (nicht an diesem Teil selbst geprüft): geerbtes Reihen-Urteil
   *  (ungünstigste Zelle der Höhenreihe geprüft) ODER ein `too_thick`-Urteil (Issue #177) —
   *  das Freigang-Kriterium ist höhenblind, solange die Wandhöhen-Wache #167 fehlt, darum
   *  ist „zu dick" nie eine geprüfte Gewissheit (die falsifizierende Prüf-Tür entfiel). */
  presumed: boolean;
  /** section_id der tatsächlich geprüften Zelle (== eigener id, wenn selbst geprüft). */
  representative_id?: string | null;
  /** Verursachendes Glied (Eindringrichtung) aus der Prüf-Tür (TOOL_INDEX = Endeffektor). */
  causer_link?: number | null;
  /** Gegenspieler der Kollision (Druckstand/Boden/…) aus der Prüf-Tür. */
  causer_against?: string | null;
  /** Eindringtiefe (mm) der schlimmsten Kollision aus der Prüf-Tür. */
  penetration_mm?: number | null;
  /** Minimaler Abstand (mm) aus der Prüf-Tür (negativ = Eindringung). */
  min_distance_mm?: number | null;
  /** Überschuss (mm): Dicken-Überschuss aus dem Freigang-Befund (bei `too_thick`)
   *  bzw. Höhen-Überschuss aus der zweiten Stufe-1-Schranke (bei `too_tall`, Issue #209). */
  excess_mm?: number | null;
  /** Winkel-Überschuss (Grad) der zweiten Stufe-1-Schranke (Issue #209) — nur bei
   *  `too_tall`: um wie viel die vom Teil geforderte Neigung die druckbare
   *  φ_max^sample (Gl. 9, Stamatopoulos) übersteigt. Der Zwilling zu `excess_mm` (Höhe). */
  excess_deg?: number | null;
  /** Erreichbarkeits-Kanal (Issue #180, Befund B33): `false` = Teil nur teilweise
   *  erreichbar. Nur bei `false` vorhanden (ein voll erreichbares Teil trägt das Feld
   *  nicht — dann gilt „erreichbar"). Das Urteil KOMBINIERT beide Kanäle: grün nur bei
   *  Prüf-Tür-frei UND voller Erreichbarkeit — `verdict==='printable'` kann bestehen
   *  bleiben (der Prüf-Tür-Kanal ist ehrlich), das Teil ist dann aber NICHT grün. */
  reachable?: boolean;
  /** Erreichbarer Wandanteil ∈ [0, 1] (Issue #180) — nur zusammen mit `reachable===false`
   *  vorhanden (sonst über `status.reachable_fraction` lesbar). */
  reachable_fraction?: number;
  /** Vorläufigkeit (Issue #177, Befund B9) — bei `verdict==='too_thick'` (bzw.
   *  `'too_tall'`, Issue #209): `true` = die druckbare Tiefe/Höhe wurde aus einem
   *  geschätzten (provisorischen) Werkzeug-TCP gerechnet und ist doppelt vorläufig
   *  (platzierungsblind + geschätzt). Nur bei `true` vorhanden (additiv). */
  tcp_provisional?: boolean;
  /** Prüf-Vorbehalte der Prüf-Tür (Issue #182, Befunde B15/B37/B38) — nur bei
   *  `verdict==='printable'|'collides'` (ein `too_thick`-Urteil hat keine Prüf-Tür
   *  gesehen): `true` = die Bahn wurde NICHT lückenlos geprüft (nur jedes
   *  travel_stride-te Travel-Sample) — dieselbe Rechtfertigung, mit der die
   *  Travel-Ausdünnung intern begründet wird, ging bislang auf dem Ampel-Pfad verloren.
   *  Nur bei `true` vorhanden (additiv). */
  travel_thinned?: boolean;
  /** Tatsächlich geprüfte Samples der Bahn (nach Travel-Ausdünnung, Issue #182) —
   *  nur zusammen mit `n_samples` vorhanden (additiv, nur bei echtem Prüf-Tür-Urteil). */
  n_checked?: number;
  /** Samples der Bahn vor Ausdünnung (Nenner zu `n_checked`, Issue #182). */
  n_samples?: number;
  /** Der Endeffektor lief als provisorische Hülle (offener PRD-Punkt 3) durch die
   *  Prüf-Tür (Issue #182) — nicht zu verwechseln mit `tcp_provisional` (Freigang-
   *  Kriterium, `too_thick`). Nur bei `true` vorhanden (additiv). */
  tool_provisional?: boolean;
}

/** Ein Abschnitt des Zerlegungsvorschlags: Geometrie + Platzierung + Ampel (Issue #24). */
export interface DecompositionSection {
  section_id: string;
  /** 1-basierte Druckreihenfolge (unten → oben). */
  order: number;
  x0_mm: number;
  x1_mm: number;
  z0_mm: number;
  z1_mm: number;
  placement: PlacementOption;
  status: SectionStatus;
  /** Sicherheitsabstands-Befund (Issue #94) — nur bei freiem Platzierungs-Override
   *  + gewählter Workstation vorhanden (additiv). Befund, kein Gate. */
  placement_check?: PlacementCheck;
  /** Modulgrenzen-Befund (Issue #90/#95) — nur bei Art „modul" vorhanden (additiv).
   *  Gewicht + Grenzen-Befund je Teil, verbatim aus dem Core. Befund, kein Gate. */
  module_check?: ModuleCheck;
  /** Lage des Moduls am Druckort (Issue #96, ADR-022) — nur bei Art „modul" mit
   *  Workstation-Frames vorhanden (additiv), verbatim aus dem Core. */
  module_pose?: ModulePose;
  /** Druckbarkeits-Urteil je Teil (Issue #164/#170) — Freigang + repräsentative
   *  Prüf-Tür, verbatim aus dem Core. Auch ,ungeprüft' (verdict==='unknown', mit
   *  `reason`) wird geschrieben; nur Altläufe (vor #164) haben gar kein Feld — dann
   *  gilt ebenfalls ,ungeprüft' (nie die alte Erreichbarkeits-Anzeige). Befund, kein Gate. */
  printability?: PartPrintability;
}

/**
 * Freigang-Befund der Wand (Issue #163, Karte #139 / Entscheidung #141, Scheibe 2):
 * druckbare Tiefe von einer Seite (`printable_depth_mm` = freie Länge unter dem
 * Handgelenk + Handgelenk-/Unterarm-Radius) gegen die Wanddicke — verbatim aus dem
 * Zerlegungslauf (decompose.json). **Wand-weit** (nicht je Teil), stellt
 * **ausschließlich** Unmöglichkeit fest (`too_thick` nur, wenn Dicke strikt > Tiefe),
 * nie Freiheit (S6-Lehre). **Befund, kein Gate** (ADR-013): blockiert nie, benennt
 * Hebel. Fehlt (Endeffektor-/Kinematik-Geometrie unbekannt) → nicht vorhanden.
 */
export interface FreigangFinding {
  wall_thickness_mm: number;
  /** Freie Länge L unter dem Handgelenk (schlanker Nozzle-/Werkzeug-Überstand, mm). */
  free_length_mm: number;
  /** Handgelenk-/Unterarm-Radius R (mm) — provisorisch bis gemessen. */
  wrist_radius_mm: number;
  /** Druckbare Tiefe D = L + R von einer Seite (mm), großzügige Obergrenze. */
  printable_depth_mm: number;
  /** Wanddicke strikt > D — sicher zu dick für einseitigen Druck. */
  too_thick: boolean;
  /** Überschuss max(0, Dicke − D) (mm); 0, solange nicht zu dick. */
  excess_mm: number;
  /** Benannte Hebel im Befund-Fall (leer, wenn nicht zu dick). */
  levers: string[];
  /** Vorläufigkeit (Issue #177, Befund B9) — `true` = die freie Länge L wurde aus einem
   *  geschätzten, noch nicht am Gerät vermessenen Werkzeug-TCP (#136) gerechnet; der
   *  Befund ist dann vorläufig, nie eine geprüfte Gewissheit. Nur bei `true` vorhanden. */
  tcp_provisional?: boolean;
}

/** Ein verworfener Kandidat der Zerlegungs-Suche (Issue #217, US 10) — verbatim aus
 *  dem Core. `grund` = warum der Schnitt nicht vorgeschlagen wurde. */
export interface RefinementRejection {
  /** Kandidaten-Schlüssel, z. B. „band-1x1". */
  kandidat: string;
  n_length: number;
  n_height: number;
  teilanzahl: number;
  /** Verworfen-Grund: Reichweite (K.-o.), Fragment (zerfällt), Kollision. */
  grund: "reichweite" | "fragment" | "kollision";
  /** Nur bei `grund==='kollision'`: die kollidierende Höhenreihe. */
  h_idx?: number;
}

/** Metriken-Katalog je Zerlegungslauf (Issue #217, US 20) — verbatim aus dem Core. */
export interface RefinementMetrics {
  teilanzahl: number;
  volumen_cv: number;
  fugenflaeche_mm2: number;
  erreichbarer_anteil: number;
  /** Anteil geprüft-freier Reihen (1.0 = Sieger; null = ungeprüfter Vorschlag). */
  geprueft_frei_anteil: number | null;
  standplaetze: number;
  /** Rein diagnostisch (nicht Teil der Entscheidung, US 25). */
  rechenzeit_s: number;
}

/** Tiefenteilungs-Vorschlag der letzten Relaxationsstufe (Issue #217) — nie automatisch. */
export interface RefinementDepthHint {
  hinweis: string;
  anwendung: "manuell";
  muster: string;
}

/**
 * Verfeinerungs-/Suche-Provenienz eines Zerlegungslaufs (Issue #165/#217), verbatim
 * aus `decompose.json`. `strategy` benennt die Strategie (ADR-004). Die Beam-Suche
 * (#217) füllt Beam-Breite/Kontingent, Verworfen-Gründe (US 10), Relaxationsausweis
 * (US 22) und den Metriken-Katalog (US 20); die #165-Verfeinerung nutzt denselben
 * Kanal mit `rows`. Nur bei aktiver Suche vorhanden (Befund, kein Gate).
 */
export interface DecompositionRefinement {
  strategy: string;
  beam_width?: number;
  call_budget?: number;
  calls_used?: number;
  budget_exhausted?: boolean;
  cancelled?: boolean;
  geprueft?: boolean;
  /** true = die Suche fand keinen erreichbaren, kollisionsfreien Schnitt (best effort). */
  leer?: boolean;
  /** Gezündete Relaxationsstufen in Reihenfolge (US 22). */
  relaxation?: string[];
  /** Verworfene Kandidaten mit Grund (US 10). */
  verworfen?: RefinementRejection[];
  metriken?: RefinementMetrics;
  tiefenteilung_vorschlag?: RefinementDepthHint | null;
  /** Surrogat-Modellstand (#219) — bis dahin null. */
  surrogate_model?: unknown;
  /** Fallback-Vermerk (kein-scorer/unzustaendig), wenn die Suche auf den Greedy fiel. */
  fallback?: string;
  /** Je Höhenreihe gewählter Hebel (#165-Verfeinerung) — bei Beam nicht belegt. */
  rows?: unknown[];
}

/** Antwort auf POST /projects/{slug}/decomposition (Issue #24). */
export interface DecompositionResult {
  slug: string;
  job_id: string;
  /** Laufordner des Zerlegungslaufs (decompose.json, ADR-004). */
  run_dir: string;
  decomposition_kind: "abschnitt" | "modul";
  cuts: Cut[];
  /** Fugen-Versatz, wie ihn der Core tatsächlich verwendet hat (Issue #25). */
  joint_offset_mm: number;
  sections: DecompositionSection[];
  print_jobs: PrintJob[];
  /** Verfeinerungs-/Suche-Provenienz (Issue #165/#217) — nur bei aktiver Suche
   *  (Beam/kollisionsgetriebene Verfeinerung) vorhanden. Befund, kein Gate. */
  refinement?: DecompositionRefinement | null;
  /** Freigang-Befund der Wand (Issue #163) — nur vorhanden, wenn der Core ihn
   *  rechnen konnte (Endeffektor + Kinematik bekannt). Befund, kein Gate. */
  freigang?: FreigangFinding | null;
  /** Umfangsansage der Stufe-2-Prüf-Tür (Issue #175): wie viele Höhenreihen eine
   *  **globale** Prüfung rechnen müsste + grobe Dauer — für die bewusste Wahl
   *  „prüft N Abschnitte, dauert ~…", ohne die teure Prüfung anzustoßen. */
  pruef_scope?: PruefScope | null;
}

/** Umfangsansage der Stufe-2-Prüf-Tür (Issue #175). */
export interface PruefScope {
  /** Höhenreihen-Repräsentanten, die eine globale Prüfung rechnen müsste (0 = nichts
   *  zu prüfen, z. B. Wand schon nach Freigang zu dick). */
  n_representatives: number;
  /** Teile insgesamt (für die Anzeige „N von M"). */
  n_parts: number;
  /** Grobe Zeitschätzung einer globalen Prüfung (s). */
  est_seconds: number;
}

/**
 * Zustand/Fortschritt eines Hintergrund-Prüflaufs (Issue #175) — Antwort auf
 * POST/GET/POST-cancel `…/decomposition-check[/{check_id}[/cancel]]`.
 *
 * Die entkoppelte Stufe-2-Prüf-Tür läuft im Hintergrund (nicht mehr im interaktiven
 * Loop, Befund B14): der Viewer stößt an, poll't `state`/`n_done`/`n_total` und kann
 * abbrechen. Bei `done` tragen `sections` (mit frischer `printability`) + `print_jobs`
 * das Ergebnis — der Viewer aktualisiert ohne Nachladen.
 */
export interface DecompositionCheckStatus {
  check_id: string;
  slug: string;
  job_id: string;
  /** 'global' = ganze Wand, 'focus' = nur die Höhenreihe des Fokus-Teils. */
  scope: "global" | "focus";
  section_id?: string | null;
  /** 'running' | 'done' | 'cancelled' | 'superseded' | 'empty' | 'error'. */
  state: "running" | "done" | "cancelled" | "superseded" | "empty" | "error";
  n_total: number;
  n_done: number;
  /** Tatsächlich gerechnete Repräsentanten (Rest kam aus dem Cache). */
  n_computed: number;
  n_cached: number;
  error?: string | null;
  sections?: DecompositionSection[] | null;
  print_jobs?: PrintJob[] | null;
}

/**
 * Zustand/Fortschritt eines Beam-Zerlegungslaufs (Issue #221, Folge #217) — Antwort auf
 * POST/GET/POST-cancel `…/decomposition-beam[/{beam_id}[/cancel]]`.
 *
 * Die Beam-Suche (#217, PRD #183 Stufe 3) läuft als Hintergrundlauf (nicht im Request-
 * Pfad): der Viewer stößt an, poll't `state`/`n_done`/`n_total` (verbrauchte / erlaubte
 * **Prüf-Tür-Aufrufe**, nicht Sekunden) und kann abbrechen. Bei `done` tragen `sections`
 * (Sieger-Schnittplan mit Ampeln) + `print_jobs` + `run_dir` das Ergebnis und `refinement`
 * den Such-Ausweis (Verworfen-Gründe US 10, Relaxationsausweis US 22, Metriken US 20) —
 * verbatim aus dem Lauf, gespeist in `refinement-state.ts`. Der Viewer aktualisiert ohne
 * Nachladen; der Core rechnet, der Viewer zeigt (ADR-007).
 */
export interface BeamProposeStatus {
  beam_id: string;
  slug: string;
  job_id: string;
  /** 'running' | 'done' | 'cancelled' | 'error'. */
  state: "running" | "done" | "cancelled" | "error";
  /** Erlaubte Prüf-Tür-Aufrufe (Aufruf-Kontingent #215); 0, solange unbekannt. */
  n_total: number;
  /** Verbrauchte Prüf-Tür-Aufrufe (Fortschritt in Aufrufen). */
  n_done: number;
  error?: string | null;
  /** Laufordner des Sieger-Zerlegungslaufs (decompose.json, ADR-004); bei `done` gesetzt. */
  run_dir?: string | null;
  sections?: DecompositionSection[] | null;
  print_jobs?: PrintJob[] | null;
  /** Such-Ausweis verbatim aus dem Lauf (bei `done`): Verworfen-Gründe/Relaxation/Metriken. */
  refinement?: DecompositionRefinement | null;
}

/** Eine reale Aufstellmöglichkeit: geplante Basis-Lage relativ zur Wand (Issue #22). */
export interface PlacementOption {
  option_id: string;
  /** Seitliche Position der Basis entlang der Wandlänge (mm). */
  lateral_mm: number;
  /** Abstand der Basis vor der Wandfront (mm). */
  standoff_mm: number;
  /** Aufstellhöhe der Basis (mm, z. B. Podest). */
  stand_height_mm: number;
  yaw_rad?: number;
  /** Prior-geführt gewählter IK-Konfig-Zweig dieses Vorschlags (Issue #233,
   *  ADR-026 Punkt 5). Nur der Optimalvorschlag setzt ihn; beim Übernehmen
   *  (`select_placement`) fährt die Simulation genau diesen Zweig. Fehlt = auto. */
  ik_config?: IkConfig;
}

/** Voller Projektstand (POST /projects, GET /projects/{slug}). */
export interface Project {
  slug: string;
  name: string;
  model_path: string;
  /** Laufordner-Pfad (absolut) des Übersichts-Laufs — /@fs-Quelle der Modellübersicht. */
  overview_run: string;
  print_jobs: PrintJob[];
}

/** Kenndaten einer Roboterdefinition aus GET /robots (Issue #20). */
export interface RobotDef {
  name: string;
  reach_mm: number;
  max_print_height_mm: number;
  max_print_length_mm: number;
  workspace_provisional: boolean;
  /** Traglast in kg (Issue #21, statischer Payload-Check). Null = unbekannt. */
  payload_kg: number | null;
}

/** Deklaration eines logischen IO-Kanals eines Endeffektors (ADR-011, Issue #21). */
export interface ChannelDecl {
  kind: "analog" | "digital";
  description: string;
  default_value: number;
}

/** Ein Frame (Lage) in mm/rad (ADR-006): Position + Einheitsquaternion [w,x,y,z]. */
export interface Frame {
  pos_mm: [number, number, number] | number[];
  quat: [number, number, number, number] | number[];
}

/** Kenndaten einer Endeffektor-Definition aus GET /tools (Issue #21/#28). */
export interface ToolDef {
  name: string;
  vendor: string;
  weight_kg: number;
  cog_mm: [number, number, number] | null;
  mesh: string | null;
  /** Absoluter Pfad der Mesh-Datei (Issue #28); Viewer lädt ihn als /@fs/-URL. */
  mesh_path: string | null;
  /** Lage des Mesh relativ zum Flansch (Issue #28); null = Identität. */
  mesh_transform: Frame | null;
  /** TCP-Frame relativ Flansch (ADR-006) — der Bibliothek-Editor stellt ihn
   *  beim „Bearbeiten" exakt wieder her (Issue #56). */
  tcp_frame: Frame;
  channels: Record<string, ChannelDecl>;
  /** Namen der Roboter, zu denen der Endeffektor passt (Kompatibilitäts-Tags,
   *  Issue #71). Leer = „unbekannt", nicht „inkompatibel"; noch keine
   *  Filterwirkung (#74). GET /tools liefert immer ein Array (Default []). */
  compatible_robots: string[];
}

/**
 * Request-Body für PUT /tools/{name} — Endeffektor bearbeiten (Issue #56).
 *
 * Wie `CreateToolRequest`, aber ohne `name` (Identität = Pfad-Parameter, kein
 * Rename) und mit **optionalem** Mesh: fehlen `mesh_base64`/`mesh_filename`,
 * bleibt die bestehende Mesh-Datei erhalten; nur Stammdaten/TCP/Kanäle/
 * `mesh_transform` werden neu geschrieben.
 */
export interface UpdateToolRequest {
  vendor: string;
  weight_kg: number;
  cog_mm: [number, number, number] | null;
  channels: Record<string, ChannelDecl>;
  tcp_frame: Frame;
  mesh_transform: Frame;
  /** Kompatibilitäts-Tags (Issue #71); leer = „unbekannt". */
  compatible_robots: string[];
  mesh_filename?: string;
  mesh_base64?: string;
}

/** Request-Body für POST /tools — Endeffektor aus Mesh-Upload anlegen (Issue #28). */
export interface CreateToolRequest {
  name: string;
  vendor: string;
  weight_kg: number;
  cog_mm: [number, number, number] | null;
  channels: Record<string, ChannelDecl>;
  tcp_frame: Frame;
  mesh_transform: Frame;
  /** Kompatibilitäts-Tags (Issue #71); leer = „unbekannt". */
  compatible_robots: string[];
  mesh_filename: string;
  mesh_base64: string;
}

/** Antwort auf PUT /projects/{slug}/tool: Projekt + Payload-Befund (Issue #21). */
export interface SetToolResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  /** null wenn kein Roboter gesetzt oder Traglast unbekannt */
  payload_ok: boolean | null;
  /** Spielraum in kg (negativ = Überschreitung). null wenn nicht berechenbar. */
  payload_margin_kg: number | null;
}

/** GET /tools — alle Endeffektor-Definitionen auflisten (Issue #21). */
export async function listTools(): Promise<ToolDef[]> {
  const body = await request<{ tools: ToolDef[] }>("GET", "/tools");
  return body.tools;
}

/**
 * POST /tools — Endeffektor aus einem Mesh-Upload anlegen (Endeffektor-Konfigurator,
 * Issue #28). Der Core validiert (Format/Größe/Ladbarkeit/Schema) und legt Mesh +
 * Definition im Tools-Verzeichnis ab; die Antwort ist die frische Kenndaten-Karte,
 * die der Viewer sofort (ohne Neustart) in den Katalog einfügt.
 */
export async function createTool(req: CreateToolRequest): Promise<ToolDef> {
  return request<ToolDef>("POST", "/tools", req);
}

/**
 * PUT /tools/{name} — bestehenden Endeffektor bearbeiten (Bibliothek-Editor,
 * Issue #56). Der Name ist die Identität (kein Rename). Ohne neues Mesh im Body
 * bleibt die bestehende Mesh-Datei erhalten. 404, wenn der Endeffektor fehlt.
 */
export async function updateTool(name: string, req: UpdateToolRequest): Promise<ToolDef> {
  return request<ToolDef>("PUT", `/tools/${encodeURIComponent(name)}`, req);
}

/**
 * DELETE /tools/{name} — Endeffektor löschen (Bibliothek, Issue #56). Entfernt
 * `<name>.json` UND die Mesh-Datei. Kein projektübergreifender „in-Verwendung"-
 * Check (Out of Scope). 404, wenn der Endeffektor nicht existiert.
 */
export async function deleteTool(name: string): Promise<void> {
  await request<{ deleted: string }>("DELETE", `/tools/${encodeURIComponent(name)}`);
}

/**
 * PUT /projects/{slug}/tool — Endeffektor-Wahl persistieren (Issue #21).
 *
 * Liefert Projekt + Payload-Befund zurück. payload_ok=false → sichtbare Warnung
 * im Viewer, aber kein Gate (Befund, kein Gate — ADR-013/CONTEXT).
 */
export async function setTool(
  slug: string,
  tool: string,
  jobId: string = "default",
): Promise<SetToolResult> {
  return request<SetToolResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/tool`,
    { tool, job_id: jobId },
  );
}

// Die früheren Wrapper `evaluatePlacements` (POST …/placements) und
// `selectPlacement` (PUT …/placement-selection) sind mit Issue #134 entfallen:
// der Gesamtwand-Platzierungsvorschlag (#22/#80) hat für die Wahl/Anwendung
// einer Platzierung nach der Zerlegung keinen Konsumenten mehr —
// Slicing/Sim/Export laufen über die Abschnitts-Platzierungen, das Anwenden des
// Singularitäts-Advisors über `setPlacementOverride` (#94). Die Core-Routen
// bestehen weiter (Altprojekte). `suggestPlacement` (POST …/placement-
// suggestion) lebt seit Issue #231 als rein lesende Machbarkeits-Vorschau
// wieder auf — siehe unten.

/** Das explizite Machbarkeits-Urteil eines Vorschlags-Kandidaten (Issue #228,
 *  ADR-026 Punkt 1) — nur vorhanden, wenn der Kollisions-Grob-Check lief. Der
 *  Core rechnet, der Viewer bildet `status` nur auf Text/Ampel ab (Issue #231,
 *  keine eigene Schwellen-Rechnung). */
export interface PlacementCollisionJudgment {
  free: boolean;
  status: string;
  source: string;
}

/** Score einer bewerteten Platzierungsoption — Ausschnitt der Felder, die die
 *  Vorschlagsliste (Issue #231) braucht; `collision` fehlt ohne Grob-Check. */
export interface PlacementScoreDto {
  reachable_fraction: number;
  kinematic_margin: number | null;
  collision?: PlacementCollisionJudgment;
  /** Prior-geführt gewählter IK-Konfig-Zweig dieser Option (Issue #233, ADR-026
   *  Punkt 5) — a/b-Block; fehlt ohne Konfig-Suchachse (Bewertungsmodus). */
  ik_config?: IkConfig;
}

/** Ein bewerteter Platzierungskandidat aus `scored` (POST …/placements bzw.
 *  …/placement-suggestion). */
export interface ScoredPlacementOption {
  option_id: string;
  lateral_mm: number;
  standoff_mm: number;
  stand_height_mm: number;
  yaw_rad: number;
  score: PlacementScoreDto;
}

/** Gesamt-Befund „(kein) machbarer Kandidat" einer Vorschlagsliste (Issue #228,
 *  ADR-026 Punkt 2). `feasible=null` bei `checked=false` heißt „unbekannt", nie
 *  „unmachbar" (kein Grob-Check gelaufen, z. B. fehlende Kollisionsgeometrie). */
export interface PlacementFeasibility {
  checked: boolean;
  feasible: boolean | null;
  n_feasible: number;
  n_total: number;
  note: string;
}

/** Antwort auf POST …/placements und POST …/placement-suggestion (Core-Modell
 *  `EvaluatePlacementsResponse`). */
export interface PlacementSuggestionResult {
  slug: string;
  job_id: string;
  run_dir: string;
  scored: ScoredPlacementOption[];
  selected: string | null;
  feasibility: PlacementFeasibility | null;
}

/**
 * POST /projects/{slug}/placement-suggestion — Machbarkeits-Vorschau des
 * Optimalvorschlags (Issue #231, ADR-026 Punkt 2).
 *
 * Rein lesend: fragt den bestehenden Core-Optimalvorschlag (Issue #23/#80) ab
 * und liefert je Kandidat die fertig gerechnete Kollisions-Einstufung
 * (`score.collision`, Issue #228) plus den Gesamt-Befund `feasibility`. Der
 * Viewer wendet daraus **nichts an** — keine Auswahl, keine Persistenz
 * (`selectPlacement`/`setPlacementOverride` bleiben die Schreibstellen); diese
 * Route dient ausschließlich der Kollisions-Ampel + dem Machbarkeits-Hinweis.
 */
export async function suggestPlacement(
  slug: string,
  jobId: string = "default",
  standoffMm: number = 700,
  nBest: number = 3,
): Promise<PlacementSuggestionResult> {
  return request<PlacementSuggestionResult>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/placement-suggestion`,
    { job_id: jobId, standoff_mm: standoffMm, n_best: nBest },
  );
}

/**
 * POST /projects/{slug}/decomposition — Zerlegungsvorschlag berechnen (Issue #24)
 * oder einen manuell editierten Schnittplan neu bewerten (Issue #25, „Prüfen").
 *
 * Ohne ``cuts`` (Default): der Core sucht selbst eine Zerlegung in Abschnitte
 * (Zerlegungsart „abschnitt", in place) — wie bisher. Mit ``cuts``: die
 * Schnittebenen sind Plan-Eingaben aus dem Viewer (Drag/Zahlenfeld/Hinzufügen/
 * Entfernen, `ui/cutplan-state.ts`); dieser Aufruf *ist* die Neubewertung —
 * die UI rechnet nie selbst (ADR-007). Das gerechnete Ergebnis liegt im
 * Zerlegungslauf (decompose.json, ADR-004); der Druckjob trägt nur
 * Zerlegungsart + Schnittebenen + Fugen-Versatz + Overrides + Lauf-Verweis
 * (ADR-016).
 */
export async function proposeDecomposition(
  slug: string,
  kind: "abschnitt" | "modul" = "abschnitt",
  jobId: string = "default",
  edit?: {
    cuts?: Cut[];
    jointOffsetMm?: number;
    sectionOverrides?: SectionOverride[];
  },
): Promise<DecompositionResult> {
  return request<DecompositionResult>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/decomposition`,
    {
      job_id: jobId,
      decomposition_kind: kind,
      cuts: edit?.cuts,
      joint_offset_mm: edit?.jointOffsetMm ?? 0,
      section_overrides: edit?.sectionOverrides,
    },
  );
}

/**
 * POST /projects/{slug}/decomposition-check — Stufe-2-Prüf-Tür anstoßen (Issue #175).
 *
 * Startet die entkoppelte Druckbarkeitsprüfung als **Hintergrundlauf** (sie verlässt
 * den interaktiven Schnittplan-Loop, Befund B14: ~71 s Freeze) und kehrt sofort mit
 * `state="running"` + `check_id` zurück. `focusSectionId` prüft nur die Höhenreihe des
 * Fokus-Teils (Default-Wahl, schnell); `undefined`/`null` prüft **global** (die bewusste,
 * teure Wahl, deren Umfang über `pruef_scope` angesagt wird). Danach mit
 * `getDecompositionCheck` poll'en und ggf. `cancelDecompositionCheck` rufen.
 */
export async function startDecompositionCheck(
  slug: string,
  jobId: string = "default",
  focusSectionId?: string | null,
): Promise<DecompositionCheckStatus> {
  return request<DecompositionCheckStatus>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/decomposition-check`,
    { job_id: jobId, focus_section_id: focusSectionId ?? null },
  );
}

/**
 * GET /projects/{slug}/decomposition-check/{check_id} — Fortschritt/Ergebnis eines
 * Hintergrund-Prüflaufs (Issue #175). 404, wenn der Lauf unbekannt ist (abgeräumt).
 */
export async function getDecompositionCheck(
  slug: string,
  checkId: string,
): Promise<DecompositionCheckStatus> {
  return request<DecompositionCheckStatus>(
    "GET",
    `/projects/${encodeURIComponent(slug)}/decomposition-check/${encodeURIComponent(
      checkId,
    )}`,
  );
}

/**
 * POST /projects/{slug}/decomposition-check/{check_id}/cancel — laufenden
 * Hintergrund-Prüflauf abbrechen (Issue #175, AC-Zusatz). Der Lauf persistiert nichts
 * (der Stand bleibt „ungeprüft"/„veraltet"); der Zustand geht auf `cancelled` über.
 */
export async function cancelDecompositionCheck(
  slug: string,
  checkId: string,
): Promise<DecompositionCheckStatus> {
  return request<DecompositionCheckStatus>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/decomposition-check/${encodeURIComponent(
      checkId,
    )}/cancel`,
  );
}

/**
 * POST /projects/{slug}/decomposition-beam — Beam-Zerlegungslauf anstoßen (Issue #221).
 *
 * Startet die Beam-Suche (#217, PRD #183 Stufe 3) als **Hintergrundlauf** (sie kostet
 * Prüf-Tür-Aufrufe, darum außerhalb des Request-Pfads) und kehrt sofort mit
 * `state="running"` + `beam_id` zurück. `callBudget` deckelt die erlaubten Prüf-Tür-
 * Aufrufe (`undefined`/`null` = Core-Default #215). Danach mit `getBeamPropose` poll'en
 * und ggf. `cancelBeamPropose` rufen; bei `done` liefert die Antwort Sieger + Such-Ausweis.
 */
export async function startBeamPropose(
  slug: string,
  jobId: string = "default",
  callBudget?: number | null,
): Promise<BeamProposeStatus> {
  return request<BeamProposeStatus>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/decomposition-beam`,
    { job_id: jobId, call_budget: callBudget ?? null },
  );
}

/**
 * GET /projects/{slug}/decomposition-beam/{beam_id} — Fortschritt/Ergebnis eines
 * Beam-Zerlegungslaufs (Issue #221). 404, wenn der Lauf unbekannt ist (abgeräumt).
 */
export async function getBeamPropose(
  slug: string,
  beamId: string,
): Promise<BeamProposeStatus> {
  return request<BeamProposeStatus>(
    "GET",
    `/projects/${encodeURIComponent(slug)}/decomposition-beam/${encodeURIComponent(
      beamId,
    )}`,
  );
}

/**
 * POST /projects/{slug}/decomposition-beam/{beam_id}/cancel — laufenden Beam-Lauf
 * abbrechen (Issue #221). Der Lauf persistiert nichts; der Zustand geht auf `cancelled`.
 */
export async function cancelBeamPropose(
  slug: string,
  beamId: string,
): Promise<BeamProposeStatus> {
  return request<BeamProposeStatus>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/decomposition-beam/${encodeURIComponent(
      beamId,
    )}/cancel`,
  );
}

/**
 * POST /projects/{slug}/sections/{section_id}/simulate — Abschnitt slicen +
 * simulieren (Issue #26).
 *
 * Der Core erzeugt aus dem Abschnitts-Teil-Mesh einen Toolpath und daraus + der
 * geplanten Platzierung eine Trajektorie (``pose_source="planned"``) in **einem**
 * Lauf; der Druckjob verweist je Abschnitt darauf (``section_runs``, ADR-016).
 * Es ist ein kinematisches Replay ohne Kollisionsprüfung (PRD Out of Scope).
 */
export async function simulateSection(
  slug: string,
  sectionId: string,
  jobId: string = "default",
): Promise<SimulateSectionResult> {
  return request<SimulateSectionResult>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/sections/${encodeURIComponent(
      sectionId,
    )}/simulate`,
    { job_id: jobId },
  );
}

/**
 * POST /projects/{slug}/sections/{section_id}/export — DRL je Abschnitt (Issue #29).
 *
 * Der Core nutzt die bestehende Emit-Aktion (Issue #13): liegt im Abschnitts-Lauf
 * ein gemessenes Setup (Kanal-Mapping, ADR-011) → vollständiges DRL
 * (`complete=true`); sonst ein sichtbar gekennzeichneter Antasten-Hinweis
 * (`complete=false`, `note` gesetzt) statt eines unmarkiert unvollständigen
 * Programms — kein Gate (ADR-006). Frischt zugleich die Export-Revision auf
 * (veraltet-Markierung).
 */
export async function exportSectionDrl(
  slug: string,
  sectionId: string,
  jobId: string = "default",
): Promise<ExportDrlResult> {
  return request<ExportDrlResult>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/sections/${encodeURIComponent(
      sectionId,
    )}/export`,
    { job_id: jobId },
  );
}

/**
 * PUT /projects/{slug}/process-params — Prozessparameter setzen (Scheibe 2/3,
 * Issue #59/#61).
 *
 * Der Core schreibt die `process_params`-Gruppen `slice` (Basis-Slice-Parameter)
 * und `orientation` (bahn-relativer Lead-/Kipp-Winkel in Grad) schema-validiert in
 * den Druckjob (`fgc.project` = einzige Schreibstelle, ADR-016) und bumpt die
 * Prozessparameter-Revision → Zerlegung/Simulation/Export veralten (ADR-017).
 * `simulate_section` und `placement` verrechnen die Werte danach aus dem Job
 * (Slice aus der Karte übersteuert, Orientierung über die geteilte `nozzle_quat`).
 * Je Gruppe: nur gesetzte Felder überschreiben; alle leer → der Block wird entfernt
 * (Karten-/Code-Defaults bzw. Düse senkrecht von oben).
 *
 * `sections` (Gradierungs-Ebene, Issue #82) ist optional: fehlt es (`undefined`),
 * bleiben die bestehenden Abschnitts-Overrides unberührt (getrennt vom globalen
 * Speichern); ein Objekt (auch `{}`) ersetzt sie (leer → Block entfällt, jeder
 * Abschnitt erbt wieder global).
 */
export async function setProcessParams(
  slug: string,
  slice: SliceParams,
  orientation: OrientationParams,
  jobId: string = "default",
  sections?: Record<string, SectionProcessOverride>,
  ikConfig: IkConfig = {},
): Promise<Project> {
  const body: Record<string, unknown> = {
    slice,
    orientation,
    ik_config: ikConfig,
    job_id: jobId,
  };
  if (sections !== undefined) body.sections = sections;
  return request<Project>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/process-params`,
    body,
  );
}

/**
 * Ein gezielter Vorschlag des Singularitäts-Advisors (Issue #65) — reine Daten.
 *
 * Je Typ ein Hebel: `kipp` (Handgelenk → `kipp_delta_deg` auf
 * `process_params.orientation` addieren), `placement` (Reichweite/Ellbogen →
 * bessere Basis-Lage `placement`), `config_flip` (Schulter/konfig-abhängig →
 * IK-Konfiguration als a/b-Block `ik_config`, Issue #200 — kein rohes opw-Bitfeld
 * mehr; `write` trägt die Schreibstellen-Nutzlast in genau der Form des
 * Kollisions-Advisors). `margin_before`/`margin_after` = kinematische Marge
 * vor/nach dem Vorschlag aus der Neubewertung des Core (beim Config-Flip bahn-weit).
 */
export interface SingularitySuggestion {
  type: "wrist" | "elbow" | "shoulder";
  lever: "kipp" | "placement" | "config_flip";
  margin_before: number | null;
  margin_after: number | null;
  improves: boolean;
  detail: string;
  kipp_delta_deg: number | null;
  placement: PlacementOption | null;
  /** Config-Flip (#200): der anzuwendende a/b-Tri-State-Block; sonst null. */
  ik_config: IkConfig | null;
  /** Config-Flip (#200): Schreibstellen-Nutzlast wie beim Kollisions-Advisor; sonst null. */
  write: CollisionWrite | null;
}

/** Antwort auf POST /projects/{slug}/singularity-advice (Issue #65/#134). */
export interface SingularityAdvice {
  slug: string;
  job_id: string;
  /** Der bewertete Fokus-Abschnitt (Issue #134); null = kein Fokus (leeres Ergebnis). */
  section_id: string | null;
  /** Dominanter Typ der schlechtesten erreichten Pose der Abschnitts-Platzierung. */
  type: "wrist" | "elbow" | "shoulder" | null;
  near: boolean;
  measure: number | null;
  /** Gezielter Vorschlag; null = nichts zu beraten (kein Fokus/unerreichbar/unkritisch). */
  advice: SingularitySuggestion | null;
}

/**
 * POST /projects/{slug}/singularity-advice — Singularitäts-Advisor (Issue #65/#134).
 *
 * Read-only (ADR-007): der Core klassifiziert die schlechteste erreichte Pose der
 * Platzierung des **Fokus-Abschnitts** (`section_id`, Issue #134 — Muster
 * Kollisions-Advisor #130) nach Typ und leitet den passenden Hebel + Vorher/
 * Nachher-Marge ab. Das „Anwenden" schreibt der Viewer danach über die bestehenden
 * Routen (`process-params` für den Kipp-Delta, `placement-override` #94 für die
 * Platzierung des Abschnitts). Ohne `section_id` antwortet der Core freundlich
 * leer (`type=null`, `advice=null`) — kein Fehler.
 */
export async function getSingularityAdvice(
  slug: string,
  sectionId: string | null = null,
  jobId: string = "default",
): Promise<SingularityAdvice> {
  return request<SingularityAdvice>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/singularity-advice`,
    { job_id: jobId, section_id: sectionId },
  );
}

/**
 * Anwendbare Schreibstellen-Nutzlast einer Kollisions-Advisor-Option (Issue #130).
 *
 * Diskriminiert über `setter`: `"process-params"` trägt entweder `ik_config` (IK-
 * Hebel) oder `orientation` (Kipp/Lead-Hebel); `"placement-override"` trägt
 * `section_id` + sparse freie Platzierungswerte. Der Viewer bildet das auf die
 * *bestehenden* Routen (`setProcessParams` / `setPlacementOverride`) ab — der
 * Advisor selbst schreibt nichts (ADR-007/016).
 */
export type CollisionWrite =
  | { setter: "process-params"; ik_config?: IkConfig; orientation?: OrientationParams }
  | {
      setter: "placement-override";
      section_id: string;
      lateral_mm?: number;
      standoff_mm?: number;
      stand_height_mm?: number;
      /** Issue #173: Einzelfeld-Option mergt (bewahrt bestehende freie Felder). */
      merge?: boolean;
    };

/** Ein Hebel der gerankten Liste des Kollisions-Advisors (Issue #130). */
export type CollisionLever = "ik_config" | "kipp_lead" | "placement";

/** Eine gangbare Option der Optionsliste — Vorher/Nachher-Nachweis + Nutzlast. */
export interface CollisionOption {
  kind: CollisionLever;
  label: string;
  detail: string;
  collision_free_before: boolean;
  collision_free_after: boolean;
  min_distance_before_mm: number | null;
  min_distance_after_mm: number | null;
  margin_before_mm: number | null;
  margin_after_mm: number | null;
  write: CollisionWrite;
}

/** Basis-Metrik (Vorher-Stand) des Kollisionsbefunds (Issue #130). */
export interface CollisionBaseline {
  min_distance_mm: number | null;
  margin_mm: number | null;
  collision_free: boolean;
  n_red: number;
}

/** Antwort auf POST /projects/{slug}/collision-advice (Issue #130). */
export interface CollisionAdvice {
  slug: string;
  job_id: string;
  /** Bewerteter Abschnitt; null = kein Abschnitt vorhanden. */
  section_id: string | null;
  /** Vorher-Metrik; null = keine Kollisionsgeometrie / kein Abschnitt. */
  baseline: CollisionBaseline | null;
  /** Gerankte, gangbare Optionen (nur Verbesserer). */
  options: CollisionOption[];
}

/**
 * POST /projects/{slug}/collision-advice — Kollisions-Advisor (Issue #130).
 *
 * Read-only (ADR-007, Muster ADR-020): der Core re-simuliert jeden Hebel-Kandidaten
 * mit derselben Maschinerie und liest denselben `meta.collision`-Befund (#127) —
 * keine Parallel-Metrik. Ergebnis ist eine gerankte Optionsliste (das „Menü"); das
 * Anwenden schreibt der Viewer danach über die bestehenden Routen.
 *
 * `includeOptions=false` (Prüf-UX #139/#145): nur der Basis-Befund — genau eine
 * Neu-Simulation (≈ 20 s) statt Basis + ~17 Kandidaten (mehrere Minuten).
 */
export async function getCollisionAdvice(
  slug: string,
  sectionId: string | null = null,
  jobId: string = "default",
  includeOptions: boolean = true,
): Promise<CollisionAdvice> {
  return request<CollisionAdvice>(
    "POST",
    `/projects/${encodeURIComponent(slug)}/collision-advice`,
    { job_id: jobId, section_id: sectionId, include_options: includeOptions },
  );
}

/** Stufenlos verstellbarer Höhenbereich in mm (Issue #72/#75); min < max. */
export interface HeightRange {
  min: number;
  max: number;
}

/**
 * Kenndaten einer Workstation aus GET /workstations (Issue #72/#75).
 *
 * Eine Entity für stationäre Zelle und mobile Workstation (`mobility`). Das
 * Höhenmodell hängt an `height_adjustable`: nicht-verstellbar → geordneter Satz
 * `base_heights_mm` (inkl. 0); verstellbar → `height_range_mm` {min,max}. Genau
 * eines der Höhenfelder ist gesetzt (Branch-Regel, im Core erzwungen).
 */
export interface WorkstationDef {
  name: string;
  mobility: "stationary" | "mobile";
  height_adjustable: boolean;
  base_heights_mm: number[];
  height_range_mm: HeightRange | null;
  safety_min_distance_mm: number;
  vendor: string;
  /** Kompatibilitäts-Tags (Issue #71/#72); leer = „unbekannt", nicht „inkompatibel". */
  compatible_robots: string[];
  /** Optionales Umgebungs-Mesh (Issue #78); Dateiname + absoluter Pfad (/@fs/-URL). */
  mesh?: string | null;
  mesh_path?: string | null;
  /** Lage der Roboterbasis relativ zum Mesh-Ursprung (ADR-006); null = nicht platziert. */
  robot_base_frame?: Frame | null;
  /** Arbeitsfläche als Frame (ADR-006); null = nicht gewählt. */
  work_surface_frame?: Frame | null;
}

/**
 * Request-Body für POST/PUT /workstations — Workstation anlegen/bearbeiten
 * (Issue #72/#75/#78). Strukturierte Zahlenfelder plus optionaler Mesh-Upload
 * (`mesh_base64` + `mesh_filename`, base64-in-JSON wie der Endeffektor, ADR-021)
 * und die Platzierungs-Frames (ADR-006). Bei PUT ist der Name die Identität
 * (Pfad-Parameter, kein Rename); der Core ignoriert `name` im Body.
 * `safety_min_distance_mm` = null → Core-Default (50). Fehlen die Mesh-Felder beim
 * Update, bleibt das bestehende Mesh erhalten; ein `null`-Frame löscht die Lage.
 */
export interface WorkstationRequest {
  name: string;
  mobility: "stationary" | "mobile";
  height_adjustable: boolean;
  base_heights_mm: number[];
  height_range_mm: HeightRange | null;
  safety_min_distance_mm: number | null;
  vendor: string;
  compatible_robots: string[];
  mesh_filename?: string | null;
  mesh_base64?: string | null;
  robot_base_frame?: Frame | null;
  work_surface_frame?: Frame | null;
}

/** Ein auf dem Workstation-Mesh erkanntes Bohrloch (Issue #78). */
export interface DetectedHole {
  center_mm: number[];
  radius_mm: number;
  normal: number[];
}

/**
 * Antwort auf POST /workstations/{name}/detect-base-holes (Issue #78): das
 * Ergebnis der Bohrbild-Erkennung. `matched` = ein zum Roboter-Bohrbild passendes
 * Muster gefunden; dann trägt `robot_base_frame` die vorgeschlagene Basis-Lage
 * (der Editor schnappt den Roboter darauf). Immer Befund, kein Gate (ADR-013).
 */
export interface DetectHolesResult {
  matched: boolean;
  robot_base_frame: Frame | null;
  detected_holes: DetectedHole[];
  warnings: string[];
  message: string;
}

/**
 * POST /workstations/{name}/detect-base-holes — Bohrbild auf dem Workstation-Mesh
 * erkennen und mit dem Basis-Bohrbild des Roboters abgleichen (Issue #78). Liest
 * das **gespeicherte** Mesh der Workstation; deshalb erst nach dem Speichern
 * sinnvoll. 404 bei unbekannter Workstation/Roboter, 422 ohne Mesh/base_mount.
 */
export async function detectBaseHoles(
  name: string,
  robot: string,
): Promise<DetectHolesResult> {
  return request<DetectHolesResult>(
    "POST",
    `/workstations/${encodeURIComponent(name)}/detect-base-holes`,
    { robot },
  );
}

/** GET /workstations — alle Workstation-Definitionen auflisten (Issue #72/#75). */
export async function listWorkstations(): Promise<WorkstationDef[]> {
  const body = await request<{ workstations: WorkstationDef[] }>("GET", "/workstations");
  return body.workstations;
}

/**
 * POST /workstations — Workstation anlegen (Bibliothek, Issue #72/#75). Der Core
 * validiert (Höhen-Branch-Regel, Schema) und legt das Artefakt atomar ab; 422 bei
 * ungültiger Eingabe (Name leer, Branch-Regel verletzt). Antwort = frische Karte.
 */
export async function createWorkstation(req: WorkstationRequest): Promise<WorkstationDef> {
  return request<WorkstationDef>("POST", "/workstations", req);
}

/**
 * PUT /workstations/{name} — bestehende Workstation bearbeiten (Editor, Issue
 * #72/#75). Der Name ist die Identität (kein Rename). 404, wenn sie fehlt; 422
 * bei verletzter Höhen-Branch-Regel.
 */
export async function updateWorkstation(
  name: string,
  req: WorkstationRequest,
): Promise<WorkstationDef> {
  return request<WorkstationDef>(
    "PUT",
    `/workstations/${encodeURIComponent(name)}`,
    req,
  );
}

/**
 * DELETE /workstations/{name} — Workstation löschen (Bibliothek, Issue #72/#75).
 * Kein projektübergreifender „in-Verwendung"-Check (Out of Scope). 404, wenn die
 * Workstation nicht existiert.
 */
export async function deleteWorkstation(name: string): Promise<void> {
  await request<{ deleted: string }>(
    "DELETE",
    `/workstations/${encodeURIComponent(name)}`,
  );
}

/** Antwort auf PUT /projects/{slug}/workstation: Projekt + Kompat-Befund (Issue #77). */
export interface SetWorkstationResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  /** Kompatibilität zum Roboter des Jobs: true/false bzw. null (kein Roboter gesetzt). */
  compatible: boolean | null;
}

/**
 * PUT /projects/{slug}/workstation — Workstation-Wahl persistieren (Issue #77, PRD #69).
 *
 * Mirror von `setTool`: der Core setzt das `workstation`-Feld im Druckjob (einzige
 * Schreibstelle `fgc.project`, ADR-016) und liefert den Kompatibilitäts-Befund gegen
 * den Roboter des Jobs. Inkompatibel = Befund, kein Gate (ADR-013) → Warnung, aber
 * gespeichert. Anders als setRobot/setTool veraltet dieser Aufruf **keine** Outputs
 * (kein Revisions-Bump) — die Workstation-Werte konsumiert erst der Druckplan-
 * Automatismus (#70). Das ist der Seam zu PRD B (#70).
 */
export async function setWorkstation(
  slug: string,
  workstation: string,
  jobId: string = "default",
): Promise<SetWorkstationResult> {
  return request<SetWorkstationResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/workstation`,
    { workstation, job_id: jobId },
  );
}

/** Antwort auf PUT /projects/{slug}/stand-mode: Projekt + gesetzter Toggle (Issue #81). */
export interface SetStandModeResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  stand_mode: "floor" | "elevated";
}

/**
 * PUT /projects/{slug}/stand-mode — Aufstell-Toggle persistieren (Issue #81, PRD B/#70).
 *
 * Mirror von `setWorkstation`: der Core setzt das `stand_mode`-Feld im Druckjob
 * (einzige Schreibstelle `fgc.project`, ADR-016). Der Toggle begrenzt den
 * Podesthöhen-Satz, den die Abschnittssuche nutzen darf (`floor` = Boden,
 * `elevated` = reale Podesthöhen). Wie setWorkstation veraltet dieser Aufruf
 * **keine** Outputs; die Neubewertung stößt der Druckplan über die Zerlegungs-
 * Route an (ADR-007).
 */
export async function setStandMode(
  slug: string,
  standMode: "floor" | "elevated",
  jobId: string = "default",
): Promise<SetStandModeResult> {
  return request<SetStandModeResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/stand-mode`,
    { stand_mode: standMode, job_id: jobId },
  );
}

/** Antwort auf PUT /projects/{slug}/context-check: Projekt + gesetzter Schalter (Issue #131). */
export interface SetContextCheckResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  check_building_context: boolean;
}

/**
 * PUT /projects/{slug}/context-check — Gebäudekontext-Schalter persistieren (Issue #131).
 *
 * Spiegel von `setStandMode`: der Core setzt das `check_building_context`-Feld im
 * Druckjob (einzige Schreibstelle `fgc.project`, ADR-016). Bei „ein" prüft die
 * nächste Simulation den Arm zusätzlich gegen den Gebäudekontext (context.json,
 * Issue #17); bei Zerlegungsart Modul gegenstandslos (ADR-022). Wie setStandMode
 * veraltet dieser Aufruf **keine** Outputs — der Schalter wirkt erst bei der
 * nächsten Simulation.
 */
export async function setContextCheck(
  slug: string,
  checkBuildingContext: boolean,
  jobId: string = "default",
): Promise<SetContextCheckResult> {
  return request<SetContextCheckResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/context-check`,
    { check_building_context: checkBuildingContext, job_id: jobId },
  );
}

/** Antwort auf PUT /projects/{slug}/module-limits: Projekt + gesetzte Grenzen (Issue #90). */
export interface SetModuleLimitsResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  module_limits: { max_length_mm?: number; max_height_mm?: number };
}

/**
 * PUT /projects/{slug}/module-limits — optionale Obergrenzen der Modulgröße
 * persistieren (Issue #90, PRD #88, ADR-022).
 *
 * Mirror von `setStandMode`: der Core schreibt den sparse `module_limits`-Block
 * in den Druckjob (einzige Schreibstelle `fgc.project`, ADR-016). `null` je
 * Grenze = keine Obergrenze; beide `null` = Block entfernen. Die Grenzen wirken
 * auf die Rasterverfeinerung der Art 'modul' + den Gewichts-/Grenzen-Befund je
 * Teil; wie setStandMode veraltet dieser Aufruf **keine** Outputs — die
 * Neubewertung stößt der Druckplan über die Zerlegungs-Route an (ADR-007).
 */
export async function setModuleLimits(
  slug: string,
  maxLengthMm: number | null,
  maxHeightMm: number | null,
  jobId: string = "default",
): Promise<SetModuleLimitsResult> {
  return request<SetModuleLimitsResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/module-limits`,
    { max_length_mm: maxLengthMm, max_height_mm: maxHeightMm, job_id: jobId },
  );
}

/** Gewicht je Kriterium der Zielfunktion (Issue #212, PRD #183 Stufe 3). */
export interface ObjectiveWeights {
  /** Anzahl Standplätze/Umsetzvorgänge — weniger = besser (Einmessen ist teuer). */
  umsetzvorgaenge: number;
  /** Fugenfläche — kleiner = besser. */
  fugenflaeche: number;
  /** Kinematische Marge — größer = besser (der Core dreht die Richtung intern). */
  kinematische_marge: number;
  /** Volumen-Gleichmäßigkeit c_v — kleiner = besser (Komfort, Default-Schlusslicht). */
  volumen_cv: number;
}

/** Zielfunktion der Zerlegungs-Suche: EIN Gewichts-Satz, zwei Lesarten (Issue #212).
 *  `aufwiegen` false (Default) = die Gewichts-Reihenfolge ist die lexikographische
 *  Rangfolge (Gleichstand zweier Gewichte unzulässig — UI-seitig verhindert);
 *  true = gewichtete Summe derselben Zahlen. */
export interface ObjectiveSettings {
  aufwiegen: boolean;
  weights: ObjectiveWeights;
}

/** Antwort auf PUT /projects/{slug}/objective: Projekt + wirksame Config (Issue #212). */
export interface SetObjectiveResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  objective: ObjectiveSettings;
}

/**
 * PUT /projects/{slug}/objective — Zielfunktion der Zerlegungs-Suche persistieren
 * (Issue #212, PRD #183 Stufe 3, Grill 2026-07-14).
 *
 * Mirror von `setModuleLimits`: der Core schreibt den sparse `objective`-Block in
 * den Druckjob (einzige Schreibstelle `fgc.project`, ADR-016); der Default entfernt
 * das Feld (Altprojekte byte-gleich). Eine **tatsächliche** Änderung veraltet den
 * Zerlegungsplan (Eingabe-Stufe `cutplan`, echo-fest #199) — ein unter der alten
 * Zielfunktion gesuchter Plan gilt ehrlich als veraltet. Die komplette Config
 * (inkl. Quantisierungs-Schrittweiten, Verfahrens-Parameter) stempelt der nächste
 * Zerlegungslauf in seine Provenienz (ADR-004); Erreichbarkeit bleibt hartes K.-o.
 */
export async function setObjective(
  slug: string,
  aufwiegen: boolean,
  weights: ObjectiveWeights,
  jobId: string = "default",
): Promise<SetObjectiveResult> {
  return request<SetObjectiveResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/objective`,
    { aufwiegen, weights, job_id: jobId },
  );
}

/** Antwort auf PUT /projects/{slug}/placement-override (Issue #94): Projekt +
 *  gespeicherter sparse Eintrag des Teils (leer = Override entfernt). */
export interface SetPlacementOverrideResult {
  slug: string;
  name: string;
  model_path: string;
  overview_run: string;
  print_jobs: PrintJob[];
  section_id: string;
  override: SectionOverride | Record<string, never>;
}

/**
 * PUT /projects/{slug}/placement-override — freien Platzierungs-Override eines
 * Teils persistieren (Issue #94, PRD #88).
 *
 * Mirror von `setStandMode`/`setModuleLimits`-Muster: der Core schreibt die freien
 * Werte in den `section_overrides`-Eintrag des Teils (einzige Schreibstelle
 * `fgc.project`, ADR-016) und bumpt bei tatsächlicher Änderung NUR den
 * Pro-Abschnitts-Zähler dieses Teils (#83 — nur dieses Teil veraltet). Leere
 * Werte (alle Felder unbelegt) entfernen den Override — zurück zur automatischen
 * Platzierung. Die Neubewertung (Ampel/erreichbar %/Marge) stößt der Druckplan
 * über die Zerlegungs-Route an (ADR-007).
 */
export async function setPlacementOverride(
  slug: string,
  sectionId: string,
  values: PlacementOverrideValues,
  jobId: string = "default",
): Promise<SetPlacementOverrideResult> {
  return request<SetPlacementOverrideResult>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/placement-override`,
    { section_id: sectionId, job_id: jobId, ...values },
  );
}

/** GET /robots — alle Roboterdefinitionen auflisten (Issue #20). */
export async function listRobots(): Promise<RobotDef[]> {
  const body = await request<{ robots: RobotDef[] }>("GET", "/robots");
  return body.robots;
}

/** GET /projects — alle Projekte auflisten. */
export async function listProjects(): Promise<ProjectSummary[]> {
  const body = await request<{ projects: ProjectSummary[] }>("GET", "/projects");
  return body.projects;
}

/** POST /projects — Projekt aus einer IFC-Datei anlegen. */
export async function createProject(
  name: string,
  modelPath: string,
  robot?: string,
): Promise<Project> {
  return request<Project>("POST", "/projects", {
    name,
    model_path: modelPath,
    robot,
  });
}

/** GET /projects/{slug} — Projekt laden. */
export async function loadProject(slug: string): Promise<Project> {
  return request<Project>("GET", `/projects/${encodeURIComponent(slug)}`);
}

/**
 * PUT /projects/{slug}/robot — Roboterwahl + Neubewertung (Issue #20).
 *
 * Erzeugt einen neuen Befund-Lauf für den gewählten Roboter, aktualisiert
 * ``overview_run`` (Modellübersicht neu einfärben) und setzt ``robot`` + ``assessment_run``
 * im Druckjob. Eignung ist ein Befund, kein Gate (ADR-013).
 */
export async function setRobot(
  slug: string,
  robot: string,
  jobId: string = "default",
): Promise<Project> {
  return request<Project>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/robot`,
    { robot, job_id: jobId },
  );
}

/**
 * PUT /projects/{slug}/print-job — Druckjob setzen oder überschreiben.
 *
 * ``assessmentRun`` ist der absolute Pfad des Übersichts-Laufs (walls-list),
 * der die Eignungsbefunde enthält. Er wird referenziert, nicht kopiert
 * (ADR-016). Eignung ist ein Befund, kein Gate: auch ungeeignete Wände können
 * übernommen werden.
 */
export async function setPrintJob(
  slug: string,
  wallGlobalId: string,
  assessmentRun: string,
  jobId: string = "default",
  wallName?: string,
): Promise<Project> {
  return request<Project>(
    "PUT",
    `/projects/${encodeURIComponent(slug)}/print-job`,
    {
      wall_global_id: wallGlobalId,
      assessment_run: assessmentRun,
      job_id: jobId,
      wall_name: wallName ?? null,
    },
  );
}

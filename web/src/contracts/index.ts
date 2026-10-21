/**
 * Verträge zwischen Planer (Python) und Viewer: Re-Exports der generierten Typen.
 * Die Dateien `<Name>.ts` entstehen aus `schemas/<Name>.schema.json` (`npm run gen:contracts`),
 * die Schemas aus `python -m roboprint export-contracts web/src/contracts/schemas`.
 * Gemeinsame Teiltypen werden bewusst nur aus einer Datei re-exportiert (keine Namenskonflikte).
 */
import type { Trajectory } from './Trajectory';
import type { PartEntry } from './Summary';
import type { Ring } from './Toolpath';
import type { PatternContact, PatternSegment } from './PatternPreview';

export type { Example } from './Example';
export type { Health } from './Health';
export type { JobCreate } from './JobCreate';
export type { JobCreated } from './JobCreated';
export type { JobState } from './JobState';
export type { BBox, Cause, PartArtifact, Placement } from './PartArtifact';
export type { PartLayerPath, PartLayerSegment, PartPatternLayer } from './PartPatternLayer';
export type { PartKindStat, PartLayerChanges, PartLayerStat, PartPatternReport } from './PartPatternReport';
export type { PatternCatalog, PatternInfo, PatternParamSpec } from './PatternCatalog';
export type { PatternPresetCreate } from './PatternPresetCreate';
export type { PatternPreset, PatternPresetEntry } from './PatternPresetEntry';
export type {
  PatternArrow,
  PatternCell,
  PatternConnector,
  PatternContact,
  PatternFit,
  PatternLayerChange,
  PatternMetrics,
  PatternNextLayer,
  PatternPath,
  PatternPathMetrics,
  PatternPreview,
  PatternSegment,
  PatternTiming,
  PatternViolation,
} from './PatternPreview';
export type { PatternOutlineBox, PatternOutlinePolygon, PatternPreviewRequest } from './PatternPreviewRequest';
export type { ProjectCreate } from './ProjectCreate';
export type { ProjectCreated } from './ProjectCreated';
export type { ProjectInfo } from './ProjectInfo';
export type { BoxSource, IfcSource, PlacementOverride, Scenario, ScenarioLimits } from './Scenario';
export type { Scene, SceneParams, SceneRobot, SceneTool, SceneWorkstation } from './Scene';
export type { PartEntry, Provenance, Summary, WallEntry } from './Summary';
export type { Ring, Toolpath, ToolpathPattern } from './Toolpath';
export type { Trajectory, TrajectorySummary } from './Trajectory';

/** Literale, die der Viewer als eigene Typen braucht. */
export type SampleStatus = Trajectory['status'][number];
export type SampleKind = Trajectory['kind'][number];
export type PartStatus = PartEntry['status'];
export type RingKind = Ring['kind'];
export type PatternSegmentKind = PatternSegment['kind'];
export type PatternContactKind = PatternContact['kind'];

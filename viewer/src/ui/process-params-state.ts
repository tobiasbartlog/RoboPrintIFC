/**
 * Prozessparameter-Serialisierung (Scheibe 2, Issue #59) — reine, DOM-freie
 * Funktionen zwischen dem Druckjob (`project.json` → `print_job.process_params`)
 * und dem Panel-Formular. Der Viewer hält keinen Fachzustand (ADR-007): die
 * Werte leben im Job auf der Platte, hier liegt nur die Umrechnung Formular ↔ Job.
 *
 * Die Basis-Slice-Parameter (Schichthöhe, Strangbreite, Schalen) sind je optional:
 * ein leeres Feld heißt „nicht gesetzt" → der Core fällt auf die Prozessfenster-
 * Karte/Code-Defaults zurück. Das Formular trägt darum `number | null` je Feld;
 * nur gesetzte Felder gehen als Override an die API (`sliceRequestFromForm`).
 */

import type { OrientationParams, PrintJob, SliceParams } from "../api/projects";

/**
 * Formularzustand der Slice-Basisparameter — `null` = Feld leer (nicht gesetzt).
 *
 * Die „Fortgeschritten"-Felder (Scheibe 2b, Issue #60) — `vPrintMmS`/`vTravelMmS`
 * (Bahngeschwindigkeit je Zielart) und `ioPrint`/`ioTravel` (io-Skalar je Zielart) —
 * liegen im selben Formular wie die Basisfelder: sie gehören zum selben
 * `process_params.slice`-Block, nur im UI unter einem Aufklapp-Bereich versteckt.
 */
export interface SliceForm {
  layerHeightMm: number | null;
  strandWidthMm: number | null;
  nShells: number | null;
  vPrintMmS: number | null;
  vTravelMmS: number | null;
  ioPrint: number | null;
  ioTravel: number | null;
}

/**
 * Formularzustand des bahn-relativen Anstellwinkels (Scheibe 3, Issue #61) — in
 * **Grad**, `null` = Feld leer (nicht gesetzt → senkrecht von oben). `+lead` =
 * in Fahrtrichtung, `+kipp` = zur Wand-Außenseite.
 */
export interface OrientationForm {
  leadDeg: number | null;
  kippDeg: number | null;
}

/** Leeres Formular (kein Feld gesetzt). */
export function emptySliceForm(): SliceForm {
  return {
    layerHeightMm: null,
    strandWidthMm: null,
    nShells: null,
    vPrintMmS: null,
    vTravelMmS: null,
    ioPrint: null,
    ioTravel: null,
  };
}

/** Leeres Orientierungsformular (0/0 = senkrecht von oben). */
export function emptyOrientationForm(): OrientationForm {
  return { leadDeg: null, kippDeg: null };
}

/**
 * Liest den `process_params.slice`-Block eines Druckjobs ins Formular. Fehlt der
 * Block (Altprojekt) oder ein einzelnes Feld, bleibt es `null` (nicht gesetzt) —
 * so wird nach dem Neuladen genau der persistierte Stand wiederhergestellt.
 */
export function sliceFormFromJob(job: PrintJob | undefined): SliceForm {
  return sliceFormFromBlock(job?.process_params?.slice);
}

/**
 * Liest einen `slice`-Block (global ODER je Abschnitt, Issue #82) ins Formular.
 * Fehlt der Block oder ein Feld, bleibt es `null` (nicht gesetzt → erbt).
 */
export function sliceFormFromBlock(s: SliceParams | undefined): SliceForm {
  return {
    layerHeightMm: numOrNull(s?.layer_height_mm),
    strandWidthMm: numOrNull(s?.strand_width_mm),
    nShells: numOrNull(s?.n_shells),
    vPrintMmS: numOrNull(s?.v_print_mm_s),
    vTravelMmS: numOrNull(s?.v_travel_mm_s),
    ioPrint: numOrNull(s?.io_print),
    ioTravel: numOrNull(s?.io_travel),
  };
}

/**
 * Baut aus dem Formular den API-Request-Block: nur gesetzte Felder (nicht `null`,
 * endlich) werden übernommen — leere Felder bleiben weg, damit der Core sie auf
 * Karte/Default fallen lässt. Ein komplett leeres Formular ergibt `{}` (der Core
 * entfernt den Block dann).
 */
export function sliceRequestFromForm(form: SliceForm): SliceParams {
  const out: SliceParams = {};
  if (isSet(form.layerHeightMm)) out.layer_height_mm = form.layerHeightMm;
  if (isSet(form.strandWidthMm)) out.strand_width_mm = form.strandWidthMm;
  if (isSet(form.nShells)) out.n_shells = form.nShells;
  if (isSet(form.vPrintMmS)) out.v_print_mm_s = form.vPrintMmS;
  if (isSet(form.vTravelMmS)) out.v_travel_mm_s = form.vTravelMmS;
  if (isSet(form.ioPrint)) out.io_print = form.ioPrint;
  if (isSet(form.ioTravel)) out.io_travel = form.ioTravel;
  return out;
}

/** true, wenn im Formular mindestens ein Feld gesetzt ist. */
export function sliceFormHasValues(form: SliceForm): boolean {
  return (
    isSet(form.layerHeightMm) ||
    isSet(form.strandWidthMm) ||
    isSet(form.nShells) ||
    isSet(form.vPrintMmS) ||
    isSet(form.vTravelMmS) ||
    isSet(form.ioPrint) ||
    isSet(form.ioTravel)
  );
}

/**
 * Liest den `process_params.orientation`-Block (Grad) eines Druckjobs ins
 * Formular. Fehlt der Block (Altprojekt) oder ein Feld, bleibt es `null` (0/0 =
 * senkrecht von oben) — so wird nach dem Neuladen der persistierte Stand exakt
 * wiederhergestellt.
 */
export function orientationFormFromJob(job: PrintJob | undefined): OrientationForm {
  return orientationFormFromBlock(job?.process_params?.orientation);
}

/**
 * Liest einen `orientation`-Block (global ODER je Abschnitt, Issue #82) ins
 * Formular. Fehlt der Block oder ein Feld, bleibt es `null` (0/0 = senkrecht).
 */
export function orientationFormFromBlock(o: OrientationParams | undefined): OrientationForm {
  return { leadDeg: numOrNull(o?.lead_deg), kippDeg: numOrNull(o?.kipp_deg) };
}

/**
 * Baut aus dem Formular den API-Request-Block: nur gesetzte Felder (nicht `null`,
 * endlich) werden übernommen — leere bleiben weg, damit der Core sie auf 0
 * (senkrecht von oben) fallen lässt. Komplett leer → `{}` (Block wird entfernt).
 */
export function orientationRequestFromForm(form: OrientationForm): OrientationParams {
  const out: OrientationParams = {};
  if (isSet(form.leadDeg)) out.lead_deg = form.leadDeg;
  if (isSet(form.kippDeg)) out.kipp_deg = form.kippDeg;
  return out;
}

/** true, wenn im Orientierungsformular mindestens ein Feld gesetzt ist. */
export function orientationFormHasValues(form: OrientationForm): boolean {
  return isSet(form.leadDeg) || isSet(form.kippDeg);
}

function numOrNull(v: number | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function isSet(v: number | null): v is number {
  return v !== null && Number.isFinite(v);
}

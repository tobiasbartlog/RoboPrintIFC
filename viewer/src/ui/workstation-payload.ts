/**
 * Workstation-Editor — reine Daten-Umrechnung + Validierung (Issue #75).
 *
 * Getrennt vom DOM, damit Formular→Payload, Workstation→Formular (Vorbefüllung
 * beim Bearbeiten) und die Karten-Zusammenfassung ohne jsdom/WebGL testbar
 * bleiben. Der Core validiert erneut gegen `workstation.schema.json` **und** die
 * Höhen-Branch-Regel (ADR-014/ADR-007: der Viewer rechnet nichts Fachliches);
 * die Client-Prüfung liefert nur eine frühe, freundliche Meldung.
 */

import type { Frame, WorkstationDef, WorkstationRequest } from "../api/projects";

/**
 * Platzierungs-Anteil des Workstation-Requests (Issue #78): der 3D-Editor
 * (`workstation-scene.ts`) liefert das optional neu hochgeladene Mesh + die
 * gesetzten Frames. Getrennt vom reinen Formular, damit `buildWorkstationRequest`
 * ohne Szene (Tests, kein WebGL) byte-gleich das alte Verhalten behält.
 */
export interface WorkstationPlacement {
  /** Nur bei Neu-Upload gesetzt; sonst bleibt das bestehende Mesh erhalten. */
  meshFilename?: string;
  meshBase64?: string;
  /** Aktuelle Lage im Editor (null = nicht/entfernt platziert → Core löscht sie). */
  robotBaseFrame?: Frame | null;
  workSurfaceFrame?: Frame | null;
}

/** Formular-Eingaben des Workstation-Editors (roher UI-Zustand). */
export interface WorkstationFormInput {
  name: string;
  mobility: "stationary" | "mobile";
  heightAdjustable: boolean;
  /** Podesthöhen — nur genutzt, wenn NICHT höhenverstellbar. */
  baseHeightsMm: number[];
  /** Höhenbereich min/max — nur genutzt, wenn höhenverstellbar. */
  rangeMinMm: number;
  rangeMaxMm: number;
  safetyMinDistanceMm: number;
  vendor: string;
  compatibleRobots: string[];
}

/** Deutsche Anzeige-Zusammenfassung einer Workstation für die Galerie-Karte. */
export interface WorkstationSummary {
  /** „stationär" | „mobil". */
  typeBadge: string;
  /** z. B. „3 Podeste · 0–300 mm" bzw. „verstellbar · 200–800 mm". */
  heightText: string;
  /** z. B. „Sicherheitsabstand 50 mm". */
  safetyText: string;
  /** Podesthöhen für die SVG-Grafik (leer bei verstellbar). */
  podestHeights: number[];
}

/** Deutsches Typ-Label aus dem `mobility`-Feld (Issue #75). */
export function mobilityLabel(mobility: string): string {
  return mobility === "mobile" ? "mobil" : "stationär";
}

/** Formatiert eine mm-Zahl kompakt (ganze Zahlen ohne Nachkomma). */
function mm(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 10) / 10);
}

/**
 * Baut die Karten-Zusammenfassung aus einer Workstation-Definition (rein,
 * Issue #75): Typ-Badge, Höhen-/Abstands-Text, Podeststapel für die Grafik.
 */
export function summarizeWorkstation(ws: WorkstationDef): WorkstationSummary {
  const typeBadge = mobilityLabel(ws.mobility);
  const safetyText = `Sicherheitsabstand ${mm(ws.safety_min_distance_mm)} mm`;

  if (ws.height_adjustable && ws.height_range_mm) {
    const { min, max } = ws.height_range_mm;
    return {
      typeBadge,
      heightText: `verstellbar · ${mm(min)}–${mm(max)} mm`,
      safetyText,
      podestHeights: [],
    };
  }

  const heights = [...ws.base_heights_mm];
  const n = heights.length;
  const noun = n === 1 ? "Podest" : "Podeste";
  const lo = n ? Math.min(...heights) : 0;
  const hi = n ? Math.max(...heights) : 0;
  return {
    typeBadge,
    heightText: `${n} ${noun} · ${mm(lo)}–${mm(hi)} mm`,
    safetyText,
    podestHeights: heights,
  };
}

/**
 * Erzeugt eine schlichte SVG-Grafik (Podeststapel) für die Karte (Issue #75).
 * Kein Mesh-Thumbnail — rein aus den strukturierten Höhen. Bei verstellbaren
 * Workstations (leere Liste) eine Rampe als „stufenloser Bereich".
 */
export function podestStackSvg(podestHeights: number[]): string {
  const W = 200;
  const H = 120;
  if (podestHeights.length === 0) {
    // Verstellbar: eine Rampe/Doppelpfeil als „stufenlos".
    return (
      `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" class="ws-card-graphic-svg" role="img">` +
      `<polygon points="20,100 180,100 180,30" class="ws-podest ws-podest-ramp" />` +
      `<line x1="185" y1="30" x2="185" y2="100" class="ws-podest-arrow" />` +
      `</svg>`
    );
  }
  const sorted = [...podestHeights].sort((a, b) => a - b);
  const maxH = sorted[sorted.length - 1] || 1;
  const baseY = H - 12;
  const barW = Math.max(14, Math.floor((W - 40) / sorted.length) - 8);
  const gap = 8;
  const totalW = sorted.length * barW + (sorted.length - 1) * gap;
  const x0 = (W - totalW) / 2;
  const bars = sorted
    .map((h, i) => {
      // Höhe 0 als niedriges Sockel-Rechteck (Boden), sonst proportional.
      const barH = 12 + (h / maxH) * (baseY - 24);
      const x = x0 + i * (barW + gap);
      const y = baseY - barH;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${barH.toFixed(
        1,
      )}" rx="2" class="ws-podest" />`;
    })
    .join("");
  return (
    `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" class="ws-card-graphic-svg" role="img">` +
    `<line x1="10" y1="${baseY}" x2="${W - 10}" y2="${baseY}" class="ws-podest-floor" />` +
    bars +
    `</svg>`
  );
}

/**
 * Baut den `POST`/`PUT /workstations`-Request aus den Formular-Eingaben und
 * prüft die Höhen-Branch-Regel clientseitig (freundliche Meldung, bevor der
 * Core mit 422 antwortet). Der Core validiert erneut.
 *
 * Wirft `Error` bei: leerem Namen, negativem Sicherheitsabstand, verletzter
 * Branch-Regel (verstellbar: min<max; fest: geordnete Podeste inkl. 0).
 *
 * `placement` (Issue #78) ist optional: nur wenn der 3D-Editor Mesh/Frames
 * liefert, werden die entsprechenden Request-Felder ergänzt — sonst bleibt der
 * Request byte-gleich zum reinen Formular (kein Mesh, keine Frames).
 */
export function buildWorkstationRequest(
  input: WorkstationFormInput,
  placement?: WorkstationPlacement,
): WorkstationRequest {
  const name = input.name.trim();
  if (!name) throw new Error("Name der Workstation fehlt.");
  if (!Number.isFinite(input.safetyMinDistanceMm) || input.safetyMinDistanceMm < 0) {
    throw new Error("Sicherheitsabstand muss eine Zahl ≥ 0 mm sein.");
  }

  let baseHeights: number[] = [];
  let range: { min: number; max: number } | null = null;

  if (input.heightAdjustable) {
    const { rangeMinMm: min, rangeMaxMm: max } = input;
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      throw new Error("Höhenbereich verlangt Zahlen für min und max.");
    }
    if (!(min < max)) {
      throw new Error(`Höhenbereich verlangt min < max (bekam min=${min}, max=${max}).`);
    }
    range = { min, max };
  } else {
    baseHeights = input.baseHeightsMm.filter((h) => Number.isFinite(h));
    if (baseHeights.length === 0) {
      throw new Error("Mindestens eine Podesthöhe angeben (geordneter Satz inkl. 0).");
    }
    if (baseHeights.some((h, i) => i > 0 && h <= baseHeights[i - 1])) {
      throw new Error(
        `Podesthöhen müssen streng aufsteigend geordnet sein (bekam ${baseHeights.join(", ")}).`,
      );
    }
    if (!baseHeights.includes(0)) {
      throw new Error("Podesthöhen müssen 0 (Bodenhöhe) enthalten.");
    }
  }

  const req: WorkstationRequest = {
    name,
    mobility: input.mobility,
    height_adjustable: input.heightAdjustable,
    base_heights_mm: baseHeights,
    height_range_mm: range,
    safety_min_distance_mm: input.safetyMinDistanceMm,
    vendor: input.vendor.trim(),
    compatible_robots: dedupeRobots(input.compatibleRobots),
  };

  // Platzierung (Issue #78) nur ergänzen, wenn eine Szene sie liefert. Mesh nur
  // bei Neu-Upload (sonst bleibt das bestehende erhalten); die Frames spiegeln
  // stets den aktuellen Editor-Stand (null löscht die Lage — Request ist der Stand).
  if (placement) {
    if (placement.meshBase64 && placement.meshFilename) {
      req.mesh_base64 = placement.meshBase64;
      req.mesh_filename = placement.meshFilename;
    }
    if ("robotBaseFrame" in placement) req.robot_base_frame = placement.robotBaseFrame ?? null;
    if ("workSurfaceFrame" in placement) req.work_surface_frame = placement.workSurfaceFrame ?? null;
  }

  return req;
}

/**
 * Füllt das Editor-Formular EXAKT aus einer geladenen Workstation vor (Issue
 * #75, kein Re-Zentrieren, kein Rename): die Höhenfelder werden branch-genau
 * gespiegelt; fehlt ein Bereich bei verstellbar, gilt 0/0.
 */
export function workstationToForm(ws: WorkstationDef): WorkstationFormInput {
  return {
    name: ws.name,
    mobility: ws.mobility,
    heightAdjustable: ws.height_adjustable,
    baseHeightsMm: [...ws.base_heights_mm],
    rangeMinMm: ws.height_range_mm ? ws.height_range_mm.min : 0,
    rangeMaxMm: ws.height_range_mm ? ws.height_range_mm.max : 0,
    safetyMinDistanceMm: ws.safety_min_distance_mm,
    vendor: ws.vendor,
    compatibleRobots: [...ws.compatible_robots],
  };
}

/** Kompatibilitäts-Tags entdoppeln + leere Namen verwerfen (Issue #71/#72). */
function dedupeRobots(names: string[]): string[] {
  const out: string[] = [];
  for (const raw of names) {
    const name = raw.trim();
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

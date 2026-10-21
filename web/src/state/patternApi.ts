/** Schmale Schnittstelle des Mustererstellers zum Backend (echt: `api/patternClient.ts`). */
import type { PatternCatalog, PatternPresetCreate, PatternPresetEntry, PatternPreview, PatternPreviewRequest } from '../contracts';

export interface PatternApi {
  getCatalog(): Promise<PatternCatalog>;
  /** Vorschau einer Schicht (Kern rechnet, < 100 ms). `signal` bricht veraltete Anfragen ab. */
  preview(req: PatternPreviewRequest, signal?: AbortSignal): Promise<PatternPreview>;
  savePreset(body: PatternPresetCreate): Promise<PatternPresetEntry>;
  /** SVG-Export, vom Kern gezeichnet (Doku und Katalog). */
  svg(req: PatternPreviewRequest, widthPx?: number): Promise<string>;
}

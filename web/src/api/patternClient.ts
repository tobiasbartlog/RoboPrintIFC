/**
 * Client des Mustererstellers (`/api/patterns`, siehe core/src/roboprint/api_patterns.py).
 * Der Browser rechnet keine Geometrie: Er schickt Parameter und zeichnet die Antwort.
 */
import type { PatternCatalog, PatternPresetCreate, PatternPresetEntry, PatternPreview, PatternPreviewRequest } from '../contracts';
import type { PatternApi } from '../state/patternApi';
import { API_BASE, ApiError } from './client';

async function failure(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') detail = body.detail;
  } catch {
    /* Antwort ohne JSON */
  }
  return new ApiError(res.status, detail || `HTTP ${res.status}`);
}

async function send(path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw await failure(res);
  return res;
}

export const realPatternApi: PatternApi = {
  async getCatalog() {
    return (await send('/patterns')).json() as Promise<PatternCatalog>;
  },
  async preview(req: PatternPreviewRequest, signal?: AbortSignal) {
    return (await send('/patterns/preview', req, signal)).json() as Promise<PatternPreview>;
  },
  async savePreset(body: PatternPresetCreate) {
    return (await send('/patterns/presets', body)).json() as Promise<PatternPresetEntry>;
  },
  async svg(req: PatternPreviewRequest, widthPx = 1400) {
    return (await send(`/patterns/preview?format=svg&width_px=${widthPx}`, req)).text();
  },
};

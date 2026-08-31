/**
 * Lokale Core-API (ADR-014): dünner Fetch-Wrapper um POST /slice.
 *
 * Der Viewer rechnet nichts (ADR-007) — er schickt nur Parameter an die API
 * und lädt den erzeugten Laufordner als neue Artefakte. Jeder Klick auf
 * „Neu slicen" erzeugt einen regulären, provenienzgestempelten Laufordner
 * (ADR-004), genau wie ein CLI-Aufruf.
 *
 * HTTP-Transport, Fehler-Mapping und `API_URL` leben seit #118 einmal in
 * `./http`; hier bleibt nur die Slice-spezifische Fassade.
 */

import { ApiError, API_URL, request } from "./http";

export interface SliceRequest {
  model_path: string;
  global_id: string;
  layer_height_mm?: number | null;
  strand_width_mm?: number | null;
  n_shells?: number | null;
  with_context?: boolean;
}

export interface SliceResponse {
  run_dir: string;
  n_layers: number;
  n_targets: number;
  n_print: number;
}

/**
 * Prüft, ob die Core-API erreichbar ist (GET /docs, Timeout 1 s).
 * Wirft keine Exception — liefert `false`, wenn nicht erreichbar.
 */
export async function isApiAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/docs`, {
      method: "HEAD",
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * POST /slice — sliced eine Wand und liefert den Laufordner-Pfad.
 * Wirft einen Error mit lesbarer Meldung bei HTTP-Fehler oder Netzwerkproblem.
 *
 * HTTP-Fehler kommen als {@link ApiError} („API-Fehler <status>: …") aus dem
 * geteilten Adapter durch; ist die API nicht erreichbar (fetch wirft), bleibt
 * die bisherige „Netzwerkfehler …"-Meldung erhalten.
 */
export async function postSlice(req: SliceRequest): Promise<SliceResponse> {
  try {
    return await request<SliceResponse>("POST", "/slice", req);
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(`Netzwerkfehler: Core-API nicht erreichbar (${err})`);
  }
}

/**
 * Der eine HTTP-Adapter zur lokalen Core-API (ADR-014/007, Issue #118).
 *
 * Vor #118 trug jede Route ihren eigenen `fetch`/`headers`/`jsonOrThrow`-Wrapper
 * und das HTTP-Fehler-Mapping lag doppelt (client.ts + projects.ts); `API_URL`
 * lebte zweifach. Hier lebt beides **einmal**:
 *
 * - {@link API_URL} — die eine Basis-URL (Port muss mit `API_PORT` in
 *   `viewer_launch.py` übereinstimmen).
 * - {@link request} — `request<T>(method, path, body?)`: setzt bei gesetztem
 *   Body den JSON-Header, ruft `fetch` und wirft bei HTTP-Fehler eine
 *   {@link ApiError}. Erfolgs-Antworten werden als `T` (JSON) geliefert.
 * - {@link ApiError} — ein typisierter HTTP-Fehler mit `status` und `detail`.
 *   Die `message` behält die bisherige, in der UI angezeigte Form
 *   „API-Fehler <status>: <detail>" (kein Aufrufer parst sie, aber der Text
 *   bleibt stabil); wer verzweigen will, liest `err.status`/`err.detail`.
 *
 * Der Viewer rechnet weiterhin nichts (ADR-007) — dieser Adapter transportiert
 * nur Parameter zur API und JSON-Artefakt-Verweise zurück.
 */

/** Port muss mit API_PORT in viewer_launch.py übereinstimmen. */
export const API_URL = "http://localhost:8765";

/**
 * Ein HTTP-Fehler der Core-API (Issue #118). `status` ist der HTTP-Statuscode
 * (404 = Projekt/Definition fehlt, 422 = ungültige Eingabe — der Fehlerkontrakt
 * des Seams `actions↔api`), `detail` die Klartext-Meldung des Core
 * (`{"detail": …}`) bzw. der `statusText`. `message` behält die bisherige Form
 * „API-Fehler <status>: <detail>", damit in der UI angezeigte Texte unverändert
 * bleiben.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`API-Fehler ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Liest `{"detail": …}` aus einer Fehler-Antwort (Fallback: `statusText`). */
async function detailFrom(res: Response): Promise<string> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    /* kein JSON-Body — statusText genügt */
  }
  return detail;
}

/**
 * Ein API-Aufruf: `fetch` auf `API_URL + path`, JSON rein/raus. Ein gesetzter
 * `body` wird als JSON serialisiert (mit Content-Type-Header); GET/DELETE ohne
 * Body senden keinen. Bei HTTP-Fehler (`!res.ok`) wirft die Funktion eine
 * {@link ApiError} mit `status`/`detail`; sonst liefert sie den geparsten Body
 * als `T`. Netzwerkfehler (fetch wirft) schlagen unverändert durch — der
 * jeweilige Aufrufer entscheidet, ob er sie in eine eigene Meldung übersetzt.
 */
export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    throw new ApiError(res.status, await detailFrom(res));
  }
  return res.json() as Promise<T>;
}

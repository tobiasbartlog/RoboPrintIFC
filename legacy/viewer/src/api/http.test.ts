/**
 * Erste Tests der Fetch-Schicht (Issue #118): der geteilte HTTP-Adapter `http.ts`
 * war bis hierhin ungetestet. Ein gemockter `fetch` prüft den Erfolgsfall, das
 * Fehler-Mapping je Status (404/422) und den `ApiError`-Kontrakt
 * (`status`/`detail`/`message`). Zusätzlich eine Stichprobe über `projects.ts`,
 * dass die dünnen Wrapper denselben Adapter benutzen (kein Eigenbau mehr).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL, ApiError, request } from "./http";
import { listTools, setTool } from "./projects";
import { postSlice } from "./client";

/** Baut eine minimale `Response`-Attrappe für den gemockten `fetch`. */
function fakeResponse(
  body: unknown,
  init: { ok?: boolean; status?: number; statusText?: string; noJson?: boolean } = {},
): Response {
  const { ok = true, status = 200, statusText = "OK", noJson = false } = init;
  return {
    ok,
    status,
    statusText,
    json: async () => {
      if (noJson) throw new SyntaxError("Unexpected end of JSON input");
      return body;
    },
  } as unknown as Response;
}

function mockFetch(res: Response): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async () => res);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("request", () => {
  it("liefert den geparsten JSON-Body im Erfolgsfall (200)", async () => {
    mockFetch(fakeResponse({ hello: "welt" }));
    const body = await request<{ hello: string }>("GET", "/ping");
    expect(body).toEqual({ hello: "welt" });
  });

  it("schickt Methode, Pfad und JSON-Body samt Content-Type", async () => {
    const fn = mockFetch(fakeResponse({ ok: true }));
    await request("PUT", "/projects/haus/tool", { tool: "duese", job_id: "default" });

    expect(fn).toHaveBeenCalledTimes(1);
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe(`${API_URL}/projects/haus/tool`);
    expect(init).toMatchObject({
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: "duese", job_id: "default" }),
    });
  });

  it("sendet für GET/DELETE ohne Body weder Body noch Content-Type", async () => {
    const fn = mockFetch(fakeResponse({ tools: [] }));
    await request("GET", "/tools");

    const [, init] = fn.mock.calls[0];
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(init.headers).toBeUndefined();
  });

  it("wirft ApiError mit status=404 und detail aus dem {detail}-Body", async () => {
    mockFetch(
      fakeResponse({ detail: "Projekt 'x' nicht gefunden" }, {
        ok: false,
        status: 404,
        statusText: "Not Found",
      }),
    );

    await expect(request("GET", "/projects/x")).rejects.toMatchObject({
      status: 404,
      detail: "Projekt 'x' nicht gefunden",
    });
  });

  it("wirft ApiError mit status=422 und behält die Meldungsform 'API-Fehler 422: …'", async () => {
    mockFetch(
      fakeResponse({ detail: "Höhen-Branch-Regel verletzt" }, {
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
      }),
    );

    let caught: unknown;
    try {
      await request("PUT", "/workstations/w", {});
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const apiErr = caught as ApiError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.detail).toBe("Höhen-Branch-Regel verletzt");
    expect(apiErr.message).toBe("API-Fehler 422: Höhen-Branch-Regel verletzt");
  });

  it("fällt auf statusText zurück, wenn der Fehler-Body kein detail bzw. kein JSON trägt", async () => {
    mockFetch(fakeResponse(null, { ok: false, status: 500, statusText: "Server Error", noJson: true }));

    await expect(request("GET", "/kaputt")).rejects.toMatchObject({
      status: 500,
      detail: "Server Error",
      message: "API-Fehler 500: Server Error",
    });
  });
});

describe("projects.ts wrappers nutzen den geteilten Adapter", () => {
  it("listTools entpackt das tools-Array (Erfolgsfall)", async () => {
    mockFetch(fakeResponse({ tools: [{ name: "duese" }] }));
    const tools = await listTools();
    expect(tools).toEqual([{ name: "duese" }]);
  });

  it("setTool reicht den ApiError (422) unverändert durch", async () => {
    mockFetch(fakeResponse({ detail: "ungültig" }, { ok: false, status: 422 }));
    await expect(setTool("haus", "duese")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("postSlice (client.ts)", () => {
  it("liefert die SliceResponse im Erfolgsfall", async () => {
    mockFetch(fakeResponse({ run_dir: "runs/x", n_layers: 3, n_targets: 9, n_print: 6 }));
    const res = await postSlice({ model_path: "m.ifc", global_id: "W" });
    expect(res.n_layers).toBe(3);
  });

  it("reicht HTTP-Fehler als ApiError durch (kein 'Netzwerkfehler')", async () => {
    mockFetch(fakeResponse({ detail: "keine Targets" }, { ok: false, status: 422 }));
    await expect(postSlice({ model_path: "m.ifc", global_id: "W" })).rejects.toMatchObject({
      status: 422,
      message: "API-Fehler 422: keine Targets",
    });
  });

  it("übersetzt Netzwerkausfälle (fetch wirft) in die Netzwerkfehler-Meldung", async () => {
    const fn = vi.fn(async () => {
      throw new TypeError("failed to fetch");
    });
    vi.stubGlobal("fetch", fn);

    await expect(postSlice({ model_path: "m.ifc", global_id: "W" })).rejects.toThrow(
      /Netzwerkfehler: Core-API nicht erreichbar/,
    );
  });
});

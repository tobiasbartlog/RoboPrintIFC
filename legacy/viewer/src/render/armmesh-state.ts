/**
 * Zustands- und Manifest-Logik für die M1013-Mesh-Darstellung des
 * Präsentations-Arms (Issue #41) — **reine TypeScript-Funktionen ohne three.js**,
 * damit die Lade-/Fallback-/Umschalt-Entscheidung isoliert per vitest prüfbar
 * bleibt (Muster der `ui/*-state.ts`). Das three.js-Objekt-Handling liegt dünn
 * in `render/arm.ts` darum herum.
 *
 * Zwei Verantwortungen:
 *   1. `parseArmManifest` — validiert `manifest.json` (die einzige Quelle für
 *      Link-Index → Datei, #40) und liefert die 7 Glieder (Index 0 = Basis …
 *      6 = Flansch) plus den Upstream-/Lizenz-Hinweis (BSD-3-Attribution).
 *   2. Der Render-Modus-Zustand (`mesh` | `schema`) mit Fallback: schlägt der
 *      GLB-Load fehl, erzwingt der Zustand `schema` und sperrt den Umschalter —
 *      es darf nie ein leerer Arm/Viewport entstehen (harte Lehre 2026-07-05).
 */

/** Vom Nutzer gewählte bzw. effektive Darstellung des Arms. */
export type RenderMode = "mesh" | "schema";

/** Ein Glied aus dem Manifest: Index (0 = Basis … 6 = Flansch) + GLB-Datei. */
export interface ArmManifestLink {
  index: number;
  urdf_link: string;
  file: string;
}

/** Upstream-/Lizenz-Herkunft der Meshes (für die BSD-3-Attribution im Reiter). */
export interface ArmManifestUpstream {
  repo: string;
  commit: string;
  license: string;
}

/** Validiertes Manifest der M1013-GLBs. */
export interface ArmManifest {
  robot: string;
  units: string;
  links: ArmManifestLink[];
  upstream: ArmManifestUpstream;
}

/** Erwartete Gliederzahl: Basis + 6 Achsen = 7 Frames (`forwardChain`). */
export const ARM_LINK_COUNT = 7;

/**
 * Render-Modus-Zustand des Arms. `requested` ist die Nutzerwahl (Default Mesh),
 * `meshAvailable` sagt, ob die GLBs geladen sind, `failed` markiert einen
 * Ladefehler. Der effektive Modus und die Umschalter-Sperre leiten sich rein
 * daraus ab (`effectiveMode`, `toggleEnabled`).
 */
export interface ArmRenderState {
  requested: RenderMode;
  meshAvailable: boolean;
  failed: boolean;
}

/** Startzustand: Default Mesh gewünscht, aber noch nicht geladen (zeigt Schema). */
export function initArmRenderState(): ArmRenderState {
  return { requested: "mesh", meshAvailable: false, failed: false };
}

/** GLBs erfolgreich geladen — der gewünschte Modus (Default Mesh) greift jetzt. */
export function withMeshesLoaded(state: ArmRenderState): ArmRenderState {
  return { ...state, meshAvailable: true, failed: false };
}

/**
 * GLB-Load fehlgeschlagen (Manifest- oder Datei-Fehler): Fallback auf Schema,
 * Wunsch auf Schema zurückgesetzt, Umschalter wird gesperrt (`toggleEnabled`
 * = false). Nie ein leerer Arm.
 */
export function withLoadFailure(state: ArmRenderState): ArmRenderState {
  return { ...state, requested: "schema", meshAvailable: false, failed: true };
}

/**
 * Nutzer schaltet den Modus um. Ohne verfügbare Meshes (noch nicht geladen oder
 * Fehler) bleibt der Zustand unverändert — der Umschalter ist dann ohnehin
 * gesperrt (`toggleEnabled`).
 */
export function requestMode(state: ArmRenderState, mode: RenderMode): ArmRenderState {
  if (state.failed || !state.meshAvailable) return state;
  return { ...state, requested: mode };
}

/**
 * Effektiv dargestellter Modus: Mesh nur, wenn geladen **und** gewünscht;
 * sonst (noch am Laden, Fehler, oder Nutzer will Schema) das Zylinder-Schema.
 */
export function effectiveMode(state: ArmRenderState): RenderMode {
  if (state.failed || !state.meshAvailable) return "schema";
  return state.requested;
}

/** Der Umschalter ist nur bedienbar, wenn Meshes geladen sind und kein Fehler vorliegt. */
export function toggleEnabled(state: ArmRenderState): boolean {
  return state.meshAvailable && !state.failed;
}

function asRecord(raw: unknown, ctx: string): Record<string, unknown> {
  if (typeof raw !== "object" || raw === null) {
    throw new Error(`Arm-Manifest: ${ctx} ist kein Objekt`);
  }
  return raw as Record<string, unknown>;
}

function asString(raw: unknown, ctx: string): string {
  if (typeof raw !== "string" || raw.length === 0) {
    throw new Error(`Arm-Manifest: ${ctx} fehlt oder ist kein String`);
  }
  return raw;
}

/**
 * Validiert das rohe `manifest.json` (die einzige Quelle Link-Index → Datei) und
 * liefert ein typisiertes Manifest. Wirft bei fehlenden Feldern, falscher
 * Gliederzahl oder unvollständigem Index 0..6 — der Aufrufer behandelt das als
 * Ladefehler (Fallback Schema).
 */
export function parseArmManifest(raw: unknown): ArmManifest {
  const obj = asRecord(raw, "Wurzel");
  const linksRaw = obj.links;
  if (!Array.isArray(linksRaw) || linksRaw.length !== ARM_LINK_COUNT) {
    throw new Error(
      `Arm-Manifest: erwarte ${ARM_LINK_COUNT} Glieder, gefunden ${
        Array.isArray(linksRaw) ? linksRaw.length : "keine Liste"
      }`,
    );
  }
  const links: ArmManifestLink[] = linksRaw.map((entry, i) => {
    const link = asRecord(entry, `Glied ${i}`);
    const index = link.index;
    if (typeof index !== "number" || !Number.isInteger(index)) {
      throw new Error(`Arm-Manifest: Glied ${i} hat keinen ganzzahligen index`);
    }
    return {
      index,
      urdf_link: asString(link.urdf_link, `Glied ${i}.urdf_link`),
      file: asString(link.file, `Glied ${i}.file`),
    };
  });
  // Index 0..6 müssen vollständig genau einmal vorkommen (sonst falsche FK-Zuordnung).
  const seen = new Set(links.map((l) => l.index));
  for (let i = 0; i < ARM_LINK_COUNT; i++) {
    if (!seen.has(i)) throw new Error(`Arm-Manifest: Glied-Index ${i} fehlt`);
  }
  const up = asRecord(obj.upstream, "upstream");
  const upstream: ArmManifestUpstream = {
    repo: asString(up.repo, "upstream.repo"),
    commit: asString(up.commit, "upstream.commit"),
    license: asString(up.license, "upstream.license"),
  };
  return {
    robot: typeof obj.robot === "string" ? obj.robot : "",
    units: typeof obj.units === "string" ? obj.units : "",
    links,
    upstream,
  };
}

/**
 * Kurz-Attribution für den Info-Text/Tooltip im Reiter Roboter (BSD-3, #41):
 * Lizenz + Repo @ Kurz-Commit. Rein aus dem Manifest — keine zweite Quelle.
 */
export function attributionText(manifest: ArmManifest): string {
  const shortCommit = manifest.upstream.commit.slice(0, 10);
  return `${manifest.upstream.license} — ${manifest.upstream.repo} @ ${shortCommit}`;
}

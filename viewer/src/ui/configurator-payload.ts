/**
 * Endeffektor-Konfigurator — reine Daten-Umrechnung + Validierung (Issue #28).
 *
 * Getrennt von three.js, damit die Gizmo→Daten-Abbildung und Formular→Payload
 * ohne WebGL testbar bleibt (vitest, PRD Testing Decisions: UI-Gizmos bewusst
 * ohne Test, aber die Nicht-three.js-Umrechnung schon). Das Ergebnis ist der
 * Request-Body für `POST /tools`; der Core validiert erneut gegen das Schema und
 * legt ab (ADR-014: der Viewer rechnet nichts Fachliches, ADR-007).
 *
 * Frames sind mm/rad (ADR-006): Position + Einheitsquaternion **[w, x, y, z]**.
 * three.js liefert Quaternionen als {x, y, z, w} — `frameFromPosQuat` dreht die
 * Reihenfolge an genau dieser einen Stelle um.
 */

export interface Frame {
  pos_mm: [number, number, number];
  quat: [number, number, number, number];
}

export interface ChannelInput {
  name: string;
  kind: "analog" | "digital";
  description: string;
}

export interface ToolFormInput {
  name: string;
  vendor: string;
  weightKg: number;
  cogMm: [number, number, number] | null;
  channels: ChannelInput[];
  tcpFrame: Frame;
  meshTransform: Frame;
  /** Namen der Roboter, zu denen der Endeffektor passt (Issue #71); leer = „unbekannt". */
  compatibleRobots: string[];
  meshFilename: string;
  meshBase64: string;
}

export interface ChannelDeclPayload {
  kind: "analog" | "digital";
  description: string;
  default_value: number;
}

export interface CreateToolPayload {
  name: string;
  vendor: string;
  weight_kg: number;
  cog_mm: [number, number, number] | null;
  channels: Record<string, ChannelDeclPayload>;
  tcp_frame: Frame;
  mesh_transform: Frame;
  compatible_robots: string[];
  mesh_filename: string;
  mesh_base64: string;
}

/**
 * Payload für PUT /tools/{name} — Endeffektor bearbeiten (Issue #56). Wie
 * `CreateToolPayload`, aber ohne `name` (Identität = Pfad, kein Rename) und mit
 * **optionalem** Mesh: nur mitgeschickt, wenn im Editor ein neues hochgeladen
 * wurde. Fehlt es, behält der Core die bestehende Mesh-Datei.
 */
export interface UpdateToolPayload {
  vendor: string;
  weight_kg: number;
  cog_mm: [number, number, number] | null;
  channels: Record<string, ChannelDeclPayload>;
  tcp_frame: Frame;
  mesh_transform: Frame;
  compatible_robots: string[];
  mesh_filename?: string;
  mesh_base64?: string;
}

/** Baut ein Schema-Frame aus einer three.js-Position + -Quaternion ({x,y,z,w}). */
export function frameFromPosQuat(
  pos: { x: number; y: number; z: number },
  quat: { x: number; y: number; z: number; w: number },
): Frame {
  return {
    pos_mm: [pos.x, pos.y, pos.z],
    quat: [quat.w, quat.x, quat.y, quat.z],
  };
}

/**
 * Baut den `POST /tools`-Request aus den Formular-Eingaben und validiert clientseitig
 * (klare Fehlermeldung, bevor der Upload rausgeht). Der Core validiert erneut.
 *
 * Wirft `Error` bei: leerem Namen, fehlendem Mesh, keinem/leerem/doppeltem Kanal,
 * negativem Gewicht.
 */
export function buildCreateToolRequest(input: ToolFormInput): CreateToolPayload {
  if (!input.name.trim()) throw new Error("Name des Endeffektors fehlt.");
  if (!input.meshBase64 || !input.meshFilename) {
    throw new Error("Kein Mesh hochgeladen — zuerst eine STL/OBJ/GLB-Datei laden.");
  }
  validateStammdaten(input);

  return {
    name: input.name.trim(),
    vendor: input.vendor.trim(),
    weight_kg: input.weightKg,
    cog_mm: input.cogMm,
    channels: buildChannels(input.channels),
    tcp_frame: input.tcpFrame,
    mesh_transform: input.meshTransform,
    compatible_robots: dedupeRobots(input.compatibleRobots),
    mesh_filename: input.meshFilename,
    mesh_base64: input.meshBase64,
  };
}

/**
 * Baut den `PUT /tools/{name}`-Payload aus den Editor-Eingaben (Issue #56). Der
 * Name gehört nicht in den Body (Identität = Pfad, kein Rename). Das Mesh ist
 * **optional**: nur wenn im Editor eine neue Datei gewählt wurde (`meshBase64`
 * gesetzt), geht es mit — sonst behält der Core die bestehende Mesh-Datei.
 *
 * Wirft `Error` bei: keinem/leerem/doppeltem Kanal, negativem Gewicht.
 */
export function buildUpdateToolRequest(input: ToolFormInput): UpdateToolPayload {
  validateStammdaten(input);

  const payload: UpdateToolPayload = {
    vendor: input.vendor.trim(),
    weight_kg: input.weightKg,
    cog_mm: input.cogMm,
    channels: buildChannels(input.channels),
    tcp_frame: input.tcpFrame,
    mesh_transform: input.meshTransform,
    compatible_robots: dedupeRobots(input.compatibleRobots),
  };
  // Mesh nur mitschicken, wenn im Editor neu hochgeladen (sonst bleibt das alte).
  if (input.meshBase64 && input.meshFilename) {
    payload.mesh_base64 = input.meshBase64;
    payload.mesh_filename = input.meshFilename;
  }
  return payload;
}

/** Gewicht ≥ 0 und mindestens ein Kanal (ADR-011) — geteilte Vorprüfung. */
function validateStammdaten(input: ToolFormInput): void {
  if (!Number.isFinite(input.weightKg) || input.weightKg < 0) {
    throw new Error("Gewicht muss eine Zahl ≥ 0 kg sein.");
  }
  if (input.channels.length === 0) {
    throw new Error("Mindestens ein logischer Kanal muss deklariert werden (ADR-011).");
  }
}

/** Kompatibilitäts-Tags entdoppeln + leere Namen verwerfen (Issue #71). Reihenfolge
 *  bleibt erhalten; leer = „unbekannt" (der Core schreibt das Feld dann gar nicht). */
function dedupeRobots(names: string[]): string[] {
  const out: string[] = [];
  for (const raw of names) {
    const name = raw.trim();
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

/** Kanal-Zeilen → schema-naher Record; wirft bei leerem/doppeltem Namen. */
function buildChannels(rows: ChannelInput[]): Record<string, ChannelDeclPayload> {
  const channels: Record<string, ChannelDeclPayload> = {};
  for (const ch of rows) {
    const name = ch.name.trim();
    if (!name) throw new Error("Ein Kanal hat keinen Namen.");
    if (channels[name]) throw new Error(`Kanalname doppelt: ${name}.`);
    channels[name] = { kind: ch.kind, description: ch.description.trim(), default_value: 0.0 };
  }
  return channels;
}

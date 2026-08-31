/**
 * Kollisionskontrolle S3 — reine Ableitung der Replay-Darstellung aus dem
 * Kollisions-Befund (`meta.collision`, ADR-024, Issue #128). DOM-/three.js-frei
 * und vitest-getestet (Hausmuster wie `parts-palette-state.ts` / `focus-store.ts`).
 *
 * **ADR-007 — nichts Urteilendes:** dieses Modul rechnet KEINE Geometrie und
 * fällt KEIN Kollisions-Urteil. Es liest den Befund **verbatim** aus dem
 * Artefakt: die Abstandskurve (`distances_mm`), das verursachende Glied
 * (`causer_link`) und die verdichteten Intervalle (`intervals`) — alles zu
 * `samples` PARALLEL. Daraus leitet es nur *Darstellung* ab: Glied-Einfärbung
 * (US 8), anklickbare Timeline-Marker (US 9), die Live-Abstandszahl (US 11) und
 * das Kollisions-Badge je Teil/Player (US 12).
 *
 * **Abwesenheit ist sicher (US 25):** fehlt `meta.collision` (Altlauf, Lauf ohne
 * Kollisionsgeometrie — der Block wird ganz weggelassen, nicht null), liefern
 * alle Ableitungen den Status quo: `null`/leere Listen, und die ehrliche
 * „keine Kollisionsprüfung"-Zeile bleibt. Kein Marker, kein Badge, kein Crash.
 *
 * **Neu-Zerlegung leert die gemerkten Befunde (Issue #182):** `clearedCollisionFindings`
 * — section_ids sind ordnungsbasiert und können sich wiederholen; ein alter Befund darf
 * nicht an einem neuen Teil kleben bleiben (kein altes Grün/Rot an falscher Stelle).
 */

import type { CollisionMeta } from "../artifacts/types";

export type { CollisionMeta } from "../artifacts/types";

/** Kollisions-Ampel (getrennt von der Platzierungs-Ampel — die bleibt unangetastet). */
export type CollisionStatus = "red" | "yellow" | "green";

/** Trägt der Lauf überhaupt einen Kollisions-Befund? (US 25 — sonst Status quo). */
export function hasCollisionFinding(c: CollisionMeta | null | undefined): c is CollisionMeta {
  return c != null;
}

/** Gesamt-Ampel des Befunds: rot vor gelb vor grün (verbatim aus n_red/n_yellow). */
export function overallCollisionStatus(c: CollisionMeta): CollisionStatus {
  if (c.n_red > 0) return "red";
  if (c.n_yellow > 0) return "yellow";
  return "green";
}

/**
 * Index des Samples zur Zeit `t` (s): größter Index mit `t_s <= t`, geklemmt auf
 * [0, n−1]. Reine Zeit-Abbildung (Darstellungsmathematik) — dieselbe Zeitachse
 * wie Arm/TCP; `sampleTimes` sind die `t_s` der Samples (parallel zu `distances_mm`).
 */
export function sampleIndexAtTime(sampleTimes: readonly number[], t: number): number {
  const n = sampleTimes.length;
  if (n === 0) return 0;
  if (t <= sampleTimes[0]) return 0;
  if (t >= sampleTimes[n - 1]) return n - 1;
  let lo = 0;
  let hi = n - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >>> 1;
    if (sampleTimes[mid] <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

/**
 * Kollisions-Status an einem Sample-Index — als reiner Lookup im **verbatim**
 * gelieferten Intervall (kein Neu-Urteilen aus Abstand/Sicherheitsabstand). Kein
 * deckendes Intervall ⇒ grün (sicher, nicht geprüft).
 */
export function statusAtIndex(c: CollisionMeta, index: number): CollisionStatus {
  for (const iv of c.intervals) {
    if (index >= iv.start_index && index <= iv.end_index) return iv.status;
  }
  return "green";
}

/** Verursachendes Glied am Sample-Index (0..6, 7 = Endeffektor), oder null. */
export function causerLinkAt(c: CollisionMeta, index: number): number | null {
  return c.causer_link?.[index] ?? null;
}

/** Minimaler Abstand (mm) am Sample-Index; null = außerhalb Prüfnähe / nicht gemessen. */
export function distanceAt(c: CollisionMeta, index: number): number | null {
  const d = c.distances_mm?.[index];
  return d ?? null;
}

/** Glied-Einfärbung (US 8): welches Glied ist am Sample-Index rot/gelb einzufärben? */
export interface LinkHighlight {
  /** Glied-Index (0..6, 7 = Endeffektor). */
  link: number;
  status: "red" | "yellow";
}

/**
 * Das einzufärbende Glied am Sample-Index — nur bei rot/gelb **und** bekanntem
 * Verursacher-Glied; grün oder unbekanntes Glied ⇒ null (nichts einfärben,
 * Arm bleibt neutral). US 8.
 */
export function linkHighlightAt(c: CollisionMeta, index: number): LinkHighlight | null {
  const status = statusAtIndex(c, index);
  if (status === "green") return null;
  const link = causerLinkAt(c, index);
  if (link == null) return null;
  return { link, status };
}

/**
 * Live-Abstandszahl im Player (US 11): kompakter mm-Text am Sample-Index. Rot,
 * wenn der Status Kollision meldet; außerhalb der Prüfnähe eine ehrliche Notiz.
 */
export function distanceReadout(c: CollisionMeta, index: number): string {
  const d = distanceAt(c, index);
  if (d == null) return "Abstand — (außer Prüfnähe)";
  const rounded = Math.round(d);
  return statusAtIndex(c, index) === "red"
    ? `Kollision (${rounded} mm)`
    : `Abstand ${rounded} mm`;
}

/** Anklickbarer Timeline-Marker (US 9): Fraktion + Zeit eines Kollisions-/Warn-Intervalls. */
export interface CollisionMarker {
  status: "red" | "yellow";
  /** Position auf der Timeline ∈ [0,1] (Intervall-Mitte) — Ziel des Klick-Sprungs. */
  midFraction: number;
  startFraction: number;
  endFraction: number;
  /** Sprung-Ziel in Sekunden (Intervall-Mitte). */
  seekTime_s: number;
  title: string;
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/**
 * Anklickbare Timeline-Marker (US 9): je rot/gelb-Intervall ein Marker, aus den
 * **verbatim** gelieferten `intervals`. Die Zeit-/Fraktions-Umrechnung ist reine
 * Darstellungsmathematik (Sample-Index → `t_s` → Anteil an der Dauer). Grüne
 * Intervalle erzeugen keinen Marker; ohne Dauer/Samples bleibt die Liste leer.
 */
export function timelineMarkers(
  c: CollisionMeta,
  sampleTimes: readonly number[],
  duration_s: number,
): CollisionMarker[] {
  if (duration_s <= 0 || sampleTimes.length === 0) return [];
  const markers: CollisionMarker[] = [];
  const timeAt = (i: number): number =>
    sampleTimes[Math.max(0, Math.min(sampleTimes.length - 1, i))];
  for (const iv of c.intervals) {
    if (iv.status !== "red" && iv.status !== "yellow") continue;
    const startT = timeAt(iv.start_index);
    const endT = timeAt(iv.end_index);
    const midT = (startT + endT) / 2;
    markers.push({
      status: iv.status,
      startFraction: clamp01(startT / duration_s),
      endFraction: clamp01(endT / duration_s),
      midFraction: clamp01(midT / duration_s),
      seekTime_s: midT,
      title: markerTitle(iv.status, iv),
    });
  }
  return markers;
}

function markerTitle(
  status: "red" | "yellow",
  iv: CollisionMeta["intervals"][number],
): string {
  const head = status === "red" ? "Kollision" : "Warnung (eng)";
  const bits: string[] = [head];
  if (iv.min_distance_mm != null) bits.push(`min. Abstand ${Math.round(iv.min_distance_mm)} mm`);
  if (iv.link != null) bits.push(linkName(iv.link));
  if (iv.against) bits.push(`gegen ${iv.against}`);
  bits.push("— anklicken, um hierher zu springen");
  return bits.join(" · ");
}

/** Kollisions-Badge je Teil / im Player (US 12) — getrennt von der Platzierungs-Ampel. */
export interface CollisionBadge {
  status: CollisionStatus;
  /** Kurztext neben dem Punkt („Kollision" / „eng" / „kollisionsfrei"). */
  label: string;
  title: string;
}

/**
 * Kollisions-Badge eines Laufs/Teils (US 12): rot/gelb/grün aus dem Gesamtbefund,
 * **verbatim**. `null`, wenn der Lauf keinen Befund trägt (Altlauf) — dann zeigt
 * die Palette wie heute kein Badge (die Platzierungs-Ampel bleibt unangetastet).
 */
export function collisionBadge(c: CollisionMeta | null | undefined): CollisionBadge | null {
  if (!c) return null;
  const status = overallCollisionStatus(c);
  const label =
    status === "red" ? "Kollision" : status === "yellow" ? "eng" : "kollisionsfrei";
  const bits: string[] = [];
  if (c.min_distance_mm != null) bits.push(`min. Abstand ${Math.round(c.min_distance_mm)} mm`);
  if (c.n_red > 0) bits.push(`${c.n_red} Kollisions-Samples`);
  if (c.n_yellow > 0) bits.push(`${c.n_yellow} Warn-Samples`);
  if (c.config.provisional) bits.push("vorläufige Grenzwerte");
  return {
    status,
    label,
    title: `Kollisionskontrolle: ${label}${bits.length ? " — " + bits.join(", ") : ""} (ADR-024, Befund, kein Gate).`,
  };
}

/**
 * Statuszeile des Players (US 25): trägt der Lauf einen Befund, verschwindet die
 * ehrliche „keine Kollisionsprüfung"-Zeile und weicht der Befund-Zusammenfassung;
 * Altläufe ohne Befund behalten die ehrliche Zeile (unverändert zu heute).
 */
export function collisionStatusLine(c: CollisionMeta | null | undefined): string {
  if (!c) return "Kinematisches Replay — keine Kollisionsprüfung.";
  const status = overallCollisionStatus(c);
  const head =
    status === "red"
      ? "Kollisionskontrolle: Kollision gefunden"
      : status === "yellow"
        ? "Kollisionskontrolle: enge Stellen (Warnung)"
        : "Kollisionskontrolle: kollisionsfrei";
  const bits: string[] = [];
  if (c.n_red > 0) bits.push(`${c.n_red} rot`);
  if (c.n_yellow > 0) bits.push(`${c.n_yellow} gelb`);
  if (c.min_distance_mm != null) bits.push(`min. Abstand ${Math.round(c.min_distance_mm)} mm`);
  if (c.config.provisional) bits.push("vorläufige Grenzwerte");
  if (c.travel_not_continuously_checked) bits.push("Travel nicht lückenlos geprüft");
  return bits.length ? `${head} — ${bits.join(", ")}.` : `${head}.`;
}

/** Ein Befund-Paar (Zahl) für die Definitionsliste `#traj-meta` / den Leisten-Block (#156). */
export interface CollisionMetaPair {
  label: string;
  value: string;
}

/**
 * Zerlegt den Kollisionsbefund in **überfliegbare Zahl-Paare** (Issue #156): der
 * frühere 160-Zeichen-Satz (`collisionStatusLine`) zerfällt — die **Zahlen**
 * (`n_red`, `n_yellow`, `n_green`, `min_distance_mm`, `mode`) werden hier zu
 * Paaren für eine Definitionsliste. Reine Ableitung, **verbatim** aus
 * `meta.collision` (ADR-007); dieselbe Funktion speist BEIDE Schauplätze —
 * Reiter Projekt (`#traj-meta`) und die Leiste im Reiter Slicing (#128/#153).
 * Die **Vorbehalte** kommen getrennt aus `collisionCaveats` (→ Warnungspunkte).
 */
export function collisionMetaPairs(c: CollisionMeta): CollisionMetaPair[] {
  const status = overallCollisionStatus(c);
  const statusText =
    status === "red"
      ? "Kollision gefunden"
      : status === "yellow"
        ? "enge Stellen (Warnung)"
        : "kollisionsfrei";
  const pairs: CollisionMetaPair[] = [
    { label: "Kollisionskontrolle", value: statusText },
    { label: "Kollisions-Samples (rot)", value: String(c.n_red) },
    { label: "Warn-Samples (gelb)", value: String(c.n_yellow) },
    { label: "Freie Samples (grün)", value: String(c.n_green) },
  ];
  if (c.min_distance_mm != null) {
    pairs.push({ label: "Min. Abstand", value: `${Math.round(c.min_distance_mm)} mm` });
  }
  if (c.config.mode) {
    pairs.push({
      label: "Prüf-Modus",
      value: c.config.mode === "modul" ? "Modul (am Druckort)" : "Abschnitt (in place)",
    });
  }
  return pairs;
}

/**
 * Zerlegt den Kollisionsbefund in **Vorbehalte** (Issue #156): die Warnungspunkte
 * des früheren Satzes — `provisional` ⇒ „vorläufige Grenzwerte";
 * `travel_not_continuously_checked` ⇒ „Travel nicht lückenlos geprüft". Leere
 * Liste, wenn keiner der Vorbehalte gilt (dann kein `<li>`). Reine Ableitung
 * (ADR-007); speist die `<ul>`-Warnungslisten BEIDER Schauplätze (#156).
 */
export function collisionCaveats(c: CollisionMeta): string[] {
  const out: string[] = [];
  if (c.config.provisional) out.push("Kollisionsbefund: vorläufige Grenzwerte");
  if (c.travel_not_continuously_checked) {
    out.push("Kollisionsbefund: Travel nicht lückenlos geprüft");
  }
  return out;
}

/**
 * Statuszeile nach „simulieren + Replay öffnen" (Issue #135, Symptom 3): die
 * frühere Festtext-Zeile „… (keine Kollisionsprüfung)" stand im Widerspruch zum
 * gleichzeitig sichtbaren Kollisions-Badge + Live-Abstand. Jetzt verbatim aus
 * `meta.collision` abgeleitet: mit Befund nennt die Zeile dessen Zusammenfassung
 * (`collisionStatusLine`), ohne Befund bleibt die ehrliche Zeile (US 25).
 */
export function replayStatusLine(
  label: string,
  c: CollisionMeta | null | undefined,
): string {
  if (!c) return `${label} simuliert — Replay läuft (keine Kollisionsprüfung).`;
  return `${label} simuliert — Replay läuft. ${collisionStatusLine(c)}`;
}

/**
 * Leert die je Teil gemerkten Kollisionsbefunde bei einer Neu-Zerlegung (Issue #182):
 * `section_id`s werden ordnungsbasiert vergeben (`abschnitt-1`, `abschnitt-2`, …) und
 * können sich zwischen zwei Zerlegungen desselben Druckjobs wiederholen — ein alter
 * Befund (andere Geometrie/Platzierung) darf nie an einem neuen Teil mit derselben ID
 * kleben bleiben. Reine Funktion (liefert immer ein leeres Objekt) — der Zwilling des
 * bereits bestehenden Musters beim Projekt-Öffnen (`main.ts`: `collisionFindings.clear()`
 * + `setCollisionFindings({})`), hier für die Neu-Zerlegung nachgezogen.
 */
export function clearedCollisionFindings(): Record<string, CollisionMeta | undefined> {
  return {};
}

/** Sprechender Glied-Name für Titel/Tooltip (0..6, 7 = Endeffektor). */
export function linkName(link: number): string {
  return link === 7 ? "Endeffektor" : `Glied ${link}`;
}

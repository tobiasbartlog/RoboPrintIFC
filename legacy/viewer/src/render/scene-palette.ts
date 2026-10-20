/**
 * Reine Darstellungs-Helfer der Viewport-Optik „Clay-Studio" (Handoff-Scheibe 9,
 * Issue #113) — DOM- und three.js-frei, damit die Farb-/Varianz-/Projektions-
 * Mathematik ohne Browser per vitest prüfbar bleibt (wie die anderen `*-state`).
 *
 * Die Szene bezieht ihre Farben aus den CSS-Design-Tokens (`--vp1/--vp2/--grid`,
 * je Theme in `style.css`), damit der ◐-Umschalter auch die 3D-Bühne kippt und
 * keine Hexwerte doppelt gepflegt werden. `readScenePalette` nimmt einen reinen
 * Token-Leser (`getComputedStyle` in `setup.ts`, ein Stub im Test) und leitet
 * die Bühnen-Farben ab; die Gitter-Deckkraft (radialer Falloff) hängt am Theme.
 */

/** Die beiden Themes der App — hier gespiegelt, um `ui/theme` nicht zu three.js zu ziehen. */
export type SceneTheme = "dark" | "light";

/** Aufgelöste Bühnen-Farben eines Themes (Hex/CSS-Farbe als String). */
export interface ScenePalette {
  /** Zentrum des radialen Studio-Verlaufs (`--vp1`). */
  bgInner: string;
  /** Rand des radialen Studio-Verlaufs (`--vp2`) — zugleich Fog-Farbe. */
  bgOuter: string;
  /** Farbe der Gitterlinien. */
  grid: string;
  /** Deckkraft der Gitterlinien: dezent nahe der Szene (radialer Falloff via Fog). */
  gridOpacity: number;
}

/** Gitter-Deckkraft je Theme (Scheibe 9: ~0.06 dunkel / ~0.09 hell). */
const GRID_OPACITY: Record<SceneTheme, number> = { dark: 0.06, light: 0.09 };

/** Gitter-Linienfarbe je Theme — bewusst deckend gehalten; die Sichtbarkeit
 *  steuert `gridOpacity`, weil three.js den Alpha-Kanal der `--grid`-rgba-Token
 *  beim Farb-Parsen ignoriert. */
const GRID_COLOR: Record<SceneTheme, string> = { dark: "#9aa3ae", light: "#3a3a34" };

/** Fallback-Farben, falls ein Token (noch) nicht aufgelöst ist (SSR/Test ohne CSS). */
const FALLBACK: Record<SceneTheme, { vp1: string; vp2: string }> = {
  dark: { vp1: "#2a2f36", vp2: "#23272d" },
  light: { vp1: "#eceae5", vp2: "#dedbd4" },
};

/**
 * Löst die Bühnen-Palette aus den CSS-Tokens auf. `read(name)` liefert den Wert
 * einer Custom-Property (z. B. `--vp1`); leere/fehlende Werte fallen auf die
 * Scheibe-9-Vorgaben zurück. Rein — kein DOM, kein three.js.
 */
export function readScenePalette(read: (name: string) => string, theme: SceneTheme): ScenePalette {
  const fb = FALLBACK[theme];
  const vp1 = (read("--vp1") || "").trim() || fb.vp1;
  const vp2 = (read("--vp2") || "").trim() || fb.vp2;
  return {
    bgInner: vp1,
    bgOuter: vp2,
    grid: GRID_COLOR[theme],
    gridOpacity: GRID_OPACITY[theme],
  };
}

/**
 * Deterministische Helligkeits-Varianz (±8 %) je Wand — aus einem Zahlen-Seed
 * (z. B. Hash der GlobalId). Gibt einen Multiplikator in [0.92, 1.08] zurück,
 * mit dem der Lehm-Basiston pro Wand leicht aufgehellt/abgedunkelt wird, damit
 * die Wände nicht wie ein einziger Flächenblock wirken. Rein & reproduzierbar.
 */
export function clayBrightness(seed: number): number {
  // Fract(sin·k)-Hash: reproduzierbar, gleichverteilt genug für eine Tönung.
  const h = Math.sin(seed * 12.9898) * 43758.5453;
  const frac = h - Math.floor(h); // [0, 1)
  return 1 + (frac * 2 - 1) * 0.08; // ±8 %
}

/** Stabiler 32-bit-Hash eines Strings (GlobalId → Seed für `clayBrightness`). */
export function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Normalized Device Coordinates (x, y ∈ [-1, 1], three.js-`Vector3.project`) auf
 * CSS-Pixel im Overlay der Größe `widthPx × heightPx` abbilden. y wird gespiegelt
 * (NDC: oben = +1; CSS: oben = 0). Rein — die Kamera-Projektion selbst bleibt in
 * three.js (`setup.ts`), diese Funktion nur die Pixel-Umrechnung fürs Maß-Label.
 */
export function ndcToPx(
  ndcX: number,
  ndcY: number,
  widthPx: number,
  heightPx: number,
): { x: number; y: number } {
  return {
    x: (ndcX * 0.5 + 0.5) * widthPx,
    y: (-ndcY * 0.5 + 0.5) * heightPx,
  };
}

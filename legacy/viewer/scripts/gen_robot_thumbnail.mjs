/**
 * Erzeugt ein statisches, eingechecktes PNG-Thumbnail je Roboter für die
 * schreibgeschützte Roboter-Galerie der Bibliothek (Issue #76).
 *
 * Bewusst KEIN Headless-WebGL-Render: der vorhandene CDP-Smoke-Harness
 * (`ui_smoke.mjs`) braucht Core-API + Vite-Dev-Server + ein Projekt + headless
 * Edge und ist damit nicht deterministisch offline lauffähig. Stattdessen malt
 * dieses Skript OHNE Fremdabhängigkeiten (nur `node:zlib`) eine schlichte,
 * stilisierte Arm-Silhouette in einen RGBA-Puffer und kodiert daraus ein
 * gültiges, nicht-leeres PNG. Die Grafik ist eine ehrliche Platzhalter-Qualität
 * und kann später durch einen echten FK-Render ersetzt werden (Design-Log
 * 2026-07-07). Ausgabe neben den GLBs: viewer/public/robots/m1013/thumbnail.png.
 *
 * Aufruf:  node viewer/scripts/gen_robot_thumbnail.mjs
 */

import { deflateSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const W = 480;
const H = 360;

// Dunkles Panel-Theme des Viewers (style.css: .lib-card-thumb Hintergrund #14171b,
// Akzent #d2793f). Arm in Stahl-Ton, TCP-Düse im Akzent.
const BG = [20, 23, 27];
const FLOOR = [55, 61, 69];
const PEDESTAL = [110, 120, 130];
const LINK = [176, 190, 197];
const JOINT = [214, 222, 226];
const TCP = [210, 121, 63];

const buf = new Uint8Array(W * H * 4);

function fill(color) {
  for (let i = 0; i < W * H; i++) {
    buf[i * 4] = color[0];
    buf[i * 4 + 1] = color[1];
    buf[i * 4 + 2] = color[2];
    buf[i * 4 + 3] = 255;
  }
}

function px(x, y, color) {
  const xi = Math.round(x);
  const yi = Math.round(y);
  if (xi < 0 || yi < 0 || xi >= W || yi >= H) return;
  const i = (yi * W + xi) * 4;
  buf[i] = color[0];
  buf[i + 1] = color[1];
  buf[i + 2] = color[2];
  buf[i + 3] = 255;
}

/** Gefüllte Scheibe (runde Kappe für Gelenke/Segment-Enden). */
function disk(cx, cy, r, color) {
  const r2 = r * r;
  for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) {
    for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
      const dx = x - cx;
      const dy = y - cy;
      if (dx * dx + dy * dy <= r2) px(x, y, color);
    }
  }
}

/** Dickes Segment als Scheiben-Stempelung (runde Kappen, keine Fremdlib). */
function segment(x0, y0, x1, y1, r, color) {
  const steps = Math.ceil(Math.hypot(x1 - x0, y1 - y0));
  for (let s = 0; s <= steps; s++) {
    const t = s / steps;
    disk(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, color);
  }
}

function rect(x0, y0, x1, y1, color) {
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) px(x, y, color);
}

// --- Szene: M1013 in einer aufrechten, greifenden Home-nahen Pose --------------
fill(BG);
// Boden
segment(40, 302, W - 40, 302, 3, FLOOR);
// Sockel / Basis (Podest)
rect(200, 270, 280, 302, PEDESTAL);
disk(240, 270, 26, LINK); // Schulterbasis
// Oberarm (Schulter -> Ellbogen)
segment(240, 265, 240, 165, 17, LINK);
disk(240, 165, 21, JOINT); // Ellbogen
// Unterarm (Ellbogen -> Handgelenk)
segment(240, 165, 356, 120, 15, LINK);
disk(356, 120, 18, JOINT); // Handgelenk
// Hand / Flansch
segment(356, 120, 392, 176, 13, LINK);
disk(392, 176, 14, JOINT); // Flansch
// Düse / TCP nach unten
segment(392, 176, 392, 214, 7, LINK);
disk(392, 218, 9, TCP); // TCP-Punkt (Akzent)

// --- PNG-Kodierung (nur node:zlib) --------------------------------------------
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const typeBytes = Buffer.from(type, "ascii");
  const body = Buffer.concat([typeBytes, data]);
  const out = Buffer.alloc(body.length + 8);
  out.writeUInt32BE(data.length, 0);
  body.copy(out, 4);
  out.writeUInt32BE(crc32(body), out.length - 4);
  return out;
}

// IHDR: 8-bit, Truecolor+Alpha (Farbtyp 6)
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(W, 0);
ihdr.writeUInt32BE(H, 4);
ihdr[8] = 8;
ihdr[9] = 6;

// Rohbild: je Scanline ein Filterbyte 0 + RGBA-Zeile
const raw = Buffer.alloc(H * (1 + W * 4));
for (let y = 0; y < H; y++) {
  const rowStart = y * (1 + W * 4);
  raw[rowStart] = 0;
  Buffer.from(buf.buffer, y * W * 4, W * 4).copy(raw, rowStart + 1);
}
const idat = deflateSync(raw, { level: 9 });

const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk("IHDR", ihdr),
  chunk("IDAT", idat),
  chunk("IEND", Buffer.alloc(0)),
]);

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "..", "public", "robots", "m1013");
mkdirSync(outDir, { recursive: true });
const outPath = join(outDir, "thumbnail.png");
writeFileSync(outPath, png);
console.log(`PNG geschrieben: ${outPath} (${png.length} Bytes, ${W}×${H})`);

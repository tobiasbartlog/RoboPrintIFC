/**
 * Druckbarkeits-Urteil → Anzeige (Issue #164) — reine Ableitung, vitest.
 *
 * Der Kern des Issues ist die **Ehrlichkeit**: grün NUR aus der Prüf-Tür (nie aus
 * einem stummen Freigang-Befund), ein geerbtes Reihen-Urteil als ,vermutlich'
 * erkennbar, und der Zähler zählt nur geprüft-frei als ✓ (das lügende „16/16 ✓"
 * fällt). Alles hier festgenagelt.
 */

import { describe, expect, it } from "vitest";

import type { PartPrintability } from "../api/projects";
import { printabilityCaveats, printabilityCounter, printabilityView } from "./printability-state";

describe("printabilityView — ehrliches Urteil je Teil (Issue #164/#170)", () => {
  it("fehlendes Urteil (Altlauf) ⇒ null (Aufrufer zeigt ‚ungeprüft‘)", () => {
    expect(printabilityView(null)).toBeNull();
    expect(printabilityView(undefined)).toBeNull();
  });

  it("unknown ⇒ eigene ‚ungeprüft‘-Ansicht (severity unknown), NIE null/frei (Issue #170)", () => {
    const v = printabilityView({ verdict: "unknown", presumed: false });
    expect(v).toMatchObject({ severity: "unknown", presumed: false, label: "ungeprüft" });
  });

  it("unknown nennt den Grund im Titel — error ≠ no_geometry (B5)", () => {
    const err = printabilityView({ verdict: "unknown", presumed: false, reason: "error" });
    const noGeo = printabilityView({ verdict: "unknown", presumed: false, reason: "no_geometry" });
    expect(err?.title).toContain("fehlgeschlagen");
    expect(noGeo?.title).toContain("keine Kollisions-Geometrie");
    expect(err?.title).not.toEqual(noGeo?.title);
  });

  it("unknown/unreachable nennt die unerreichbare Reihe im Titel (Issue #174/B13)", () => {
    const un = printabilityView({ verdict: "unknown", presumed: false, reason: "unreachable" });
    expect(un).toMatchObject({ severity: "unknown", label: "ungeprüft" });
    expect(un?.title).toContain("keine erreichbare Zelle");
    const noGeo = printabilityView({ verdict: "unknown", presumed: false, reason: "no_geometry" });
    expect(un?.title).not.toEqual(noGeo?.title);
  });

  it("unknown/unchecked nennt den ausstehenden Anstoß im Titel (Issue #175)", () => {
    const un = printabilityView({ verdict: "unknown", presumed: false, reason: "unchecked" });
    expect(un).toMatchObject({ severity: "unknown", label: "ungeprüft" });
    expect(un?.title).toContain("noch nicht angestoßen");
    // Distinkt von den übrigen Gründen (nicht „Fehler"/„keine Geometrie").
    const err = printabilityView({ verdict: "unknown", presumed: false, reason: "error" });
    const noGeo = printabilityView({ verdict: "unknown", presumed: false, reason: "no_geometry" });
    expect(un?.title).not.toEqual(err?.title);
    expect(un?.title).not.toEqual(noGeo?.title);
  });

  it("printable (geprüft) ist grün und NICHT vermutlich", () => {
    const v = printabilityView({ verdict: "printable", presumed: false });
    expect(v).toMatchObject({ severity: "ok", presumed: false, label: "frei" });
  });

  it("printable (geerbt) ist grün, aber als ,vermutlich' erkennbar", () => {
    const v = printabilityView({ verdict: "printable", presumed: true });
    expect(v?.severity).toBe("ok");
    expect(v?.presumed).toBe(true);
    expect(v?.label).toBe("vermutlich frei");
  });

  it("collides trägt Verursacher-Glied + Eindringtiefe im Text", () => {
    const p: PartPrintability = {
      verdict: "collides",
      presumed: false,
      causer_link: 4,
      penetration_mm: 206,
    };
    const v = printabilityView(p);
    expect(v?.severity).toBe("bad");
    expect(v?.label).toContain("kollidiert");
    expect(v?.label).toContain("Glied 4");
    // „tief" benennt die Größe (Issue #238): Eindringtiefe, keine Kollisionshöhe —
    // ohne das Wort wurde die Zahl als Schnitthöhen-Empfehlung fehlgedeutet.
    expect(v?.label).toContain("206 mm tief");
  });

  it("collides geerbt ist als ,vermutlich' erkennbar", () => {
    const v = printabilityView({
      verdict: "collides",
      presumed: true,
      causer_link: 2,
      penetration_mm: 289,
    });
    expect(v?.presumed).toBe(true);
    expect(v?.label).toContain("vermutlich kollidiert");
  });

  it("too_thick ist rot und als ,vermutlich' ausgewiesen (höhenblind, Issue #177/B7)", () => {
    // Der Core setzt presumed=true für too_thick (Freigang-Kriterium ist höhenblind,
    // Wandhöhen-Wache #167 fehlt) — die Anzeige muss ,vermutlich' zeigen, keine Gewissheit.
    const v = printabilityView({ verdict: "too_thick", presumed: true, excess_mm: 176 });
    expect(v?.severity).toBe("bad");
    expect(v?.presumed).toBe(true);
    expect(v?.label).toBe("vermutlich zu dick · 176 mm");
    expect(v?.title).toContain("HÖHENBLIND");
    expect(v?.title).toContain("#167");
  });

  it("too_tall ist rot und als ,vermutlich' ausgewiesen — Überschuss in mm UND Grad (Issue #209)", () => {
    // Zweite Stufe-1-Schranke (Gl. 9): der Core setzt presumed=true (platzierungsblind).
    const v = printabilityView({
      verdict: "too_tall",
      presumed: true,
      excess_mm: 633,
      excess_deg: 24,
    });
    expect(v?.severity).toBe("bad");
    expect(v?.presumed).toBe(true);
    expect(v?.label).toBe("vermutlich zu hoch · 633 mm · 24°");
    expect(v?.title).toContain("PLATZIERUNGSBLIND");
    expect(v?.title).toContain("24°");
  });

  it("too_tall ohne Winkel-Feld (Altlauf) zeigt nur den mm-Überschuss (additiv)", () => {
    const v = printabilityView({ verdict: "too_tall", presumed: true, excess_mm: 500 });
    expect(v?.severity).toBe("bad");
    expect(v?.label).toBe("vermutlich zu hoch · 500 mm");
    expect(v?.label).not.toContain("°");
  });

  it("too_tall trägt nie Prüf-Tür-Vorbehalte (keine Prüf-Tür gesehen)", () => {
    const v = printabilityView({ verdict: "too_tall", presumed: true, excess_mm: 500, excess_deg: 20 });
    expect(v?.title).not.toContain("Travel");
    expect(v?.title).not.toContain("Samples geprüft");
  });

  it("too_thick mit provisorischem TCP weist die Vorläufigkeit zusätzlich aus (Issue #177/B9)", () => {
    const v = printabilityView({
      verdict: "too_thick",
      presumed: true,
      excess_mm: 90,
      tcp_provisional: true,
    });
    expect(v?.severity).toBe("bad");
    expect(v?.label).toContain("TCP vorläufig");
    expect(v?.title).toContain("geschätzten");
  });
});

describe("printabilityCaveats — Prüf-Vorbehalte durchreichen (Issue #182, B15/B37/B38)", () => {
  it("keine Vorbehalte (Altlauf/too_thick) ⇒ leere Liste", () => {
    expect(printabilityCaveats({ verdict: "printable", presumed: false })).toEqual([]);
  });

  it("travel_thinned ⇒ ‚Travel nicht lückenlos geprüft‘", () => {
    const caveats = printabilityCaveats({
      verdict: "printable",
      presumed: false,
      travel_thinned: true,
    });
    expect(caveats).toContain("Travel nicht lückenlos geprüft");
  });

  it("n_checked < n_samples ⇒ ‚n von m Samples geprüft‘", () => {
    const caveats = printabilityCaveats({
      verdict: "printable",
      presumed: false,
      n_checked: 42,
      n_samples: 210,
    });
    expect(caveats).toContain("42 von 210 Samples geprüft");
  });

  it("n_checked === n_samples (voll geprüft) ⇒ kein Samples-Vorbehalt", () => {
    const caveats = printabilityCaveats({
      verdict: "printable",
      presumed: false,
      n_checked: 210,
      n_samples: 210,
    });
    expect(caveats.some((c) => c.includes("Samples geprüft"))).toBe(false);
  });

  it("tool_provisional ⇒ ‚Endeffektor-Hülle provisorisch‘", () => {
    const caveats = printabilityCaveats({
      verdict: "printable",
      presumed: false,
      tool_provisional: true,
    });
    expect(caveats).toContain("Endeffektor-Hülle provisorisch");
  });

  it("alle drei Vorbehalte gleichzeitig, gemeinsam ausgewiesen", () => {
    const caveats = printabilityCaveats({
      verdict: "printable",
      presumed: false,
      travel_thinned: true,
      n_checked: 42,
      n_samples: 210,
      tool_provisional: true,
    });
    expect(caveats).toEqual([
      "Travel nicht lückenlos geprüft",
      "42 von 210 Samples geprüft",
      "Endeffektor-Hülle provisorisch",
    ]);
  });
});

describe("printabilityView — Prüf-Vorbehalte im Tooltip (Issue #182)", () => {
  it("printable mit Vorbehalten nennt sie im Titel — Tür-,frei' sieht nicht staerker aus", () => {
    const v = printabilityView({
      verdict: "printable",
      presumed: false,
      travel_thinned: true,
      n_checked: 5,
      n_samples: 20,
      tool_provisional: true,
    });
    expect(v?.severity).toBe("ok");
    expect(v?.title).toContain("Travel nicht lückenlos geprüft");
    expect(v?.title).toContain("5 von 20 Samples geprüft");
    expect(v?.title).toContain("Endeffektor-Hülle provisorisch");
  });

  it("collides mit Vorbehalten nennt sie ebenfalls im Titel", () => {
    const v = printabilityView({
      verdict: "collides",
      presumed: false,
      causer_link: 4,
      penetration_mm: 206,
      travel_thinned: true,
    });
    expect(v?.title).toContain("Travel nicht lückenlos geprüft");
  });

  it("printable ohne Vorbehalte (Altverhalten) — Titel unveraendert, kein leeres Klammerpaar", () => {
    const v = printabilityView({ verdict: "printable", presumed: false });
    expect(v?.title).not.toContain("()");
    expect(v?.title).toBe("Druckbar: die Prüf-Tür hat dieses Teil kollisionsfrei gesehen. Befund, kein Gate.");
  });

  it("too_thick traegt nie Prüf-Tür-Vorbehalte (keine Prüf-Tür gesehen)", () => {
    const v = printabilityView({ verdict: "too_thick", presumed: true, excess_mm: 90 });
    expect(v?.title).not.toContain("Travel");
    expect(v?.title).not.toContain("Samples geprüft");
  });
});

describe("printabilityView — Ampel-Konjunktion Erreichbarkeit UND Druckbarkeit (Issue #180)", () => {
  it("printable + voll erreichbar (reachable fehlt/true) ⇒ grün (No-op, Altverhalten)", () => {
    expect(printabilityView({ verdict: "printable", presumed: false })?.severity).toBe("ok");
    expect(
      printabilityView({ verdict: "printable", presumed: false, reachable: true })?.severity,
    ).toBe("ok");
  });

  it("printable ABER teilweise unerreichbar (reachable=false) ⇒ NICHT grün, sondern rot (B33)", () => {
    const v = printabilityView({
      verdict: "printable",
      presumed: false,
      reachable: false,
      reachable_fraction: 0.5,
    });
    // Kern des Issues: Kollisionsfreiheit macht ein unerreichbares Teil NICHT grün.
    expect(v?.severity).toBe("bad");
    // Beide Kanäle ablesbar: kollisionsfrei UND teilweise unerreichbar (mit Anteil).
    expect(v?.label).toContain("kollisionsfrei");
    expect(v?.label).toContain("unerreichbar");
    expect(v?.label).toContain("50 %");
  });

  it("vermutlich frei + unerreichbar bleibt ,vermutlich' erkennbar und rot", () => {
    const v = printabilityView({
      verdict: "printable",
      presumed: true,
      reachable: false,
      reachable_fraction: 0.3,
    });
    expect(v?.severity).toBe("bad");
    expect(v?.presumed).toBe(true);
    expect(v?.label).toContain("vermutlich");
  });

  it("ein unerreichbares printable-Teil zählt NICHT als geprüftes ✓ (Zähler-Konjunktion)", () => {
    const green = printabilityView({ verdict: "printable", presumed: false });
    const unreachable = printabilityView({
      verdict: "printable",
      presumed: false,
      reachable: false,
      reachable_fraction: 0.5,
    });
    // 1 grün + 1 rot (unerreichbar) ⇒ „1/2 nicht druckbar", nie „2/2 ✓".
    expect(printabilityCounter([green, unreachable])).toEqual({
      label: "1/2 nicht druckbar",
      cssClass: "badge-warn",
      show: true,
    });
  });
});

describe("printabilityCounter — ehrlicher Palette-Zähler (Issue #164/#170)", () => {
  it("leere Palette ⇒ null (kein Teil)", () => {
    expect(printabilityCounter([])).toBeNull();
  });

  it("nur ungeprüfte (Altlauf/Prüffehler) ⇒ ‚N ungeprüft‘ — NIE ‚alles geprüft‘ (B34/B35)", () => {
    // null = fehlendes Urteil (Altlauf), severity unknown = kaputtes/kein Urteil.
    const unknownView = printabilityView({ verdict: "unknown", presumed: false, reason: "error" });
    expect(printabilityCounter([null, null])).toEqual({
      label: "2 ungeprüft",
      cssClass: "badge-warn",
      show: true,
    });
    expect(printabilityCounter([unknownView, null])).toEqual({
      label: "2 ungeprüft",
      cssClass: "badge-warn",
      show: true,
    });
  });

  it("gemischt: geprüft-frei + ungeprüft weisen den Nenner ehrlich aus (B34)", () => {
    const free = () => printabilityView({ verdict: "printable", presumed: false });
    const views = [free(), free(), free(), free(), null, null, null, null];
    // 4 druckbar, 4 ungeprüft — nie „4/4 ✓" (der B34-Defekt).
    expect(printabilityCounter(views)).toEqual({
      label: "4 druckbar · 4 ungeprüft",
      cssClass: "badge-warn",
      show: true,
    });
  });

  it("das lügende 16/16-Häkchen fällt: alle kollidieren ⇒ nicht druckbar (warn)", () => {
    const views = Array.from({ length: 16 }, () =>
      printabilityView({ verdict: "too_thick", presumed: true, excess_mm: 176 }),
    );
    expect(printabilityCounter(views)).toEqual({
      label: "16/16 nicht druckbar",
      cssClass: "badge-warn",
      show: true,
    });
  });

  it("alle geprüft-frei ⇒ N/N druckbar ✓ (grün)", () => {
    const views = [
      printabilityView({ verdict: "printable", presumed: false }),
      printabilityView({ verdict: "printable", presumed: false }),
    ];
    expect(printabilityCounter(views)).toEqual({
      label: "2/2 druckbar ✓",
      cssClass: "badge-ok",
      show: true,
    });
  });

  it("vermutlich-frei zählt NICHT als geprüftes ✓ (ehrlich, warn)", () => {
    const views = [
      printabilityView({ verdict: "printable", presumed: false }),
      printabilityView({ verdict: "printable", presumed: true }),
    ];
    // 1 geprüft-frei von 2 ⇒ nicht alle geprüft, badge-warn.
    expect(printabilityCounter(views)).toEqual({
      label: "1/2 druckbar ✓",
      cssClass: "badge-warn",
      show: true,
    });
  });
});

import { describe, expect, it } from "vitest";

import type { BeamProposeStatus, DecompositionRefinement } from "../api/projects";
import {
  beamProgressView,
  beamSummary,
  relaxAusweis,
  verworfenRows,
} from "./refinement-state";

const beam = (over: Partial<DecompositionRefinement> = {}): DecompositionRefinement => ({
  strategy: "beam-suche",
  beam_width: 20,
  call_budget: 20,
  calls_used: 3,
  budget_exhausted: false,
  geprueft: true,
  leer: false,
  relaxation: [],
  verworfen: [],
  ...over,
});

describe("refinement-state (Beam-Suche, Issue #217)", () => {
  describe("verworfenRows (US 10)", () => {
    it("ohne refinement (Greedy/Altlauf) leer", () => {
      expect(verworfenRows(undefined)).toEqual([]);
      expect(verworfenRows(null)).toEqual([]);
      expect(verworfenRows(beam())).toEqual([]);
    });

    it("uebersetzt die drei Verworfen-Gruende in Anzeigetext", () => {
      const r = beam({
        verworfen: [
          { kandidat: "band-2x2", n_length: 2, n_height: 2, teilanzahl: 4, grund: "reichweite" },
          { kandidat: "band-2x1", n_length: 2, n_height: 1, teilanzahl: 2, grund: "fragment" },
          {
            kandidat: "band-1x1",
            n_length: 1,
            n_height: 1,
            teilanzahl: 1,
            grund: "kollision",
            h_idx: 0,
          },
        ],
      });
      const rows = verworfenRows(r);
      expect(rows.map((x) => x.label)).toEqual([
        "unerreichbar",
        "zerfällt in Fragmente",
        "Kollision (Reihe 1)", // h_idx 0 => 1-basiert
      ]);
      expect(rows[0].raster).toBe("2×2");
      expect(rows[2].kandidat).toBe("band-1x1");
    });
  });

  describe("relaxAusweis (US 22)", () => {
    it("ohne gezuendete Stufe nichts zu zeigen", () => {
      expect(relaxAusweis(beam()).show).toBe(false);
      expect(relaxAusweis(beam()).label).toBe("");
    });

    it("gezuendete Stufen werden in Reihenfolge menschlich ausgewiesen", () => {
      const r = beam({
        relaxation: ["mehr_teile", "mehr_standplaetze", "tiefenteilung_vorschlag"],
        leer: true,
      });
      const a = relaxAusweis(r);
      expect(a.show).toBe(true);
      expect(a.stufen).toEqual(["mehr Teile", "mehr Standplätze", "Tiefenteilung (Vorschlag)"]);
      expect(a.label).toBe(
        "gelockert: mehr Teile → mehr Standplätze → Tiefenteilung (Vorschlag)",
      );
      expect(a.leer).toBe(true);
    });

    it("unbekannte Stufen fail-soft roh durchreichen", () => {
      expect(relaxAusweis(beam({ relaxation: ["neue_stufe"] })).stufen).toEqual(["neue_stufe"]);
    });
  });

  describe("beamSummary", () => {
    it("nur bei Beam-Suche sichtbar", () => {
      expect(beamSummary(undefined).show).toBe(false);
      expect(
        beamSummary({ strategy: "kollisionsgetriebene-verfeinerung" }).show,
      ).toBe(false);
    });

    it("zeigt Strategie + Kontingent-Nutzung", () => {
      expect(beamSummary(beam({ calls_used: 7, call_budget: 20 })).label).toBe(
        "Beam-Suche · 7/20 Prüfungen",
      );
    });

    it("weist ein erschoepftes Kontingent aus", () => {
      expect(
        beamSummary(beam({ calls_used: 20, call_budget: 20, budget_exhausted: true })).label,
      ).toBe("Beam-Suche · 20/20 Prüfungen (Kontingent erschöpft)");
    });
  });

  describe("beamProgressView (Auslöser, Issue #221)", () => {
    const status = (over: Partial<BeamProposeStatus> = {}): BeamProposeStatus => ({
      beam_id: "b1",
      slug: "haus",
      job_id: "default",
      state: "running",
      n_total: 20,
      n_done: 5,
      ...over,
    });

    it("null = nichts anzeigen (idle)", () => {
      const v = beamProgressView(null);
      expect(v.active).toBe(false);
      expect(v.running).toBe(false);
    });

    it("laeuft: Fortschritt in Pruef-Tuer-Aufrufen, abbrechbar", () => {
      const v = beamProgressView(status({ n_done: 5, n_total: 20 }));
      expect(v.running).toBe(true);
      expect(v.cancellable).toBe(true);
      expect(v.fraction).toBeCloseTo(0.25);
      expect(v.label).toBe("Beam-Suche läuft: 5/20 Prüfungen …");
    });

    it("unbekanntes Kontingent: Bruch 0, generischer Zaehler", () => {
      const v = beamProgressView(status({ n_total: 0, n_done: 0 }));
      expect(v.fraction).toBe(0);
      expect(v.label).toBe("Beam-Suche läuft: Prüfungen …");
    });

    it("done: voller Balken, Sieger uebernommen (kein stilles Gruen)", () => {
      const v = beamProgressView(status({ state: "done" }));
      expect(v.running).toBe(false);
      expect(v.cancellable).toBe(false);
      expect(v.fraction).toBe(1);
      expect(v.tone).toBe("ok");
    });

    it("abgebrochen: ehrlicher Abschlusstext, warn", () => {
      const v = beamProgressView(status({ state: "cancelled" }));
      expect(v.active).toBe(true);
      expect(v.running).toBe(false);
      expect(v.tone).toBe("warn");
    });

    it("fehler: rote Meldung mit Ursache", () => {
      const v = beamProgressView(status({ state: "error", error: "kaputt" }));
      expect(v.tone).toBe("bad");
      expect(v.label).toBe("Beam-Suche fehlgeschlagen: kaputt");
    });
  });
});

Herzschlag: 2026-10-20T22:53:19+02:00 · Session: start · Phase: M3 · Status: laeuft

# MUSTER-PROGRESS: Druckmuster (Infill und Outfill)

Auftrag: `docs/muster/AUFTRAG.md`. Herzschlag-Skript: `scripts/herzschlag.py`.
Die erste Zeile setzt nur das Skript.

## Aufgaben

| Aufgabe | Phase | Status | Branch | Commit |
|---|---|---|---|---|
| Einrichtung, Ausgangslage verify --fast, Artefaktformat (`docs/muster/ARTEFAKT-FORMAT.md`) | M0 | erledigt | v2/muster | 9b0510e |
| R Recherche → `docs/muster/recherche.md` (Teil 1) | M1 | erledigt, gemergt | v2/muster-recherche | a6b6636 |
| R2 Recherche Sollbruchstellen, Fachwerkwände | M1 | erledigt, gemergt | v2/muster-recherche | ae788b2 |
| K Kern `core/src/roboprint/patterns/` (Schnittstelle, alternate, Schalen, metrics M1–M7, Vorschau, Presets) | M1 | erledigt, gemergt (63 Tests grün) | v2/muster-kern | 074763c |
| O Orakel `verify_muster/` mit Selbsttests (58) | M1 | erledigt, gemergt | v2/muster-orakel | 4b50b13 |
| F Fugenwand (Foto, O2): Gurt gespiegelt, Gurt versetzt, Rautenkette; Presets, Bilder, Doku | M1/M2 | erledigt, gemergt | v2/muster-fugenwand | f20f439 |
| 2D-Musterersteller: API `/api/patterns*`, CLI `pattern-preview`, Web-Reiter „Muster“ (e2e 11/11) | M3/M4 | erledigt, gemergt | v2/muster-ersteller | 5f0f769 |
| I-Wellen (Sinus, Zickzack gerundet, Trapez, Mäander) | M2 | erledigt, gemergt | v2/muster-wellen | d3bceca |
| I-Mehrfach (Doppelwelle, Waben, Fermat-Spirale) | M2 | erledigt, gemergt | v2/muster-mehrfach | d15cb95 |
| Outfill O1/O3 (nur wenn Zeit; O2 = Fugenwand) | M2 | offen | v2/muster-outfill | |
| Topologie (Öffnungen, Inseln, Laibungsstege, Naht, Abschrägung) | M2 | erledigt, gemergt | v2/muster-topologie | 6bf2292 |
| Einbau Slicer + Vertrag + Schema/TS | M3 | erledigt (auf v2/muster-einbau, noch nicht gemergt) | v2/muster-einbau | b78ce7d |
| Einbau Planer/Timing/DRL | M3 | gebaut, Gegenprüfung läuft (wf_0e4879c6-203) | v2/muster-einbau | 36ced12 |
| Musterszenarien, `scripts/verify_muster.py`, SPEC-Nachtrag | M3 | wartet (wf_0e4879c6-203) | v2/muster-einbau | |
| Viewer: Musterwahl im Ablauf, Schichtvorschau des Teils, Legende, Kennzahlen | M4 | läuft (wf_eeffd1a6-6c2) | v2/muster-viewer | |
| Katalog-Generator `scripts/muster_katalog.py` (Vorschau-Kennzahlen, Bilder) | M5 | erledigt, gemergt (Neulauf nach M3 nötig) | v2/muster-katalog | 5755006+ |
| Vorschau-Laufzeit (metrics): Fugenwand 1200×200 146 → 70 ms; Wellen noch 120–380 ms | M4 | erledigt, gemergt; Wellen offen | v2/muster-perf | 81a874f |
| Wellen-Fix: Planung < 100 ms, Absturz L-Querschnitt | M2 | läuft (wf_eeffd1a6-6c2) | v2/muster-wellenfix | |
| Vergleich mit Roboterprüfung, MUSTERKATALOG final, Testdrucke | M5 | offen | v2/muster-katalog | |
| Gegenprüfung und Härtung | M6 | offen | v2/muster | |
| Kernfehler `shells.shell_chain`/`clear_end` stürzt bei Inseln < ~4·w ab (auch Grundmuster) | M6 | offen | v2/muster-haertung | |
| Abschluss: Morgenbericht, PROGRESS, Draft-PR | M7 | offen | v2/muster | |

## Gate-Stand

| Prüfung | Status | Kennzahl | Stand |
|---|---|---|---|
| G1–G8 (`scripts/verify.py`) | --fast grün (G1 G2 G3 G5 G8) | Ausgangslage | M0 18:10 |
| Muster (`scripts/verify_muster.py`) | | | |

## Gate-Einwände

(Belege, wo ein bestehendes Kriterium mit einem Muster kollidiert. Die Entscheidung trifft der Nutzer.)

1. **G3-Abdeckung „≥ 95 % des Schalenbereichs“ (SPEC §11) gegen Fugenwand.** Die Fugenwand deckt den
   Schalenbereich (Querschnitt minus Innenpuffer 2·w) nur zu 60–89 % ab, weil die Außenhaut aus Feldern
   mit Fugen besteht und die Stege schräg nach innen laufen (Agent F, 600×200 … 1000×300). Das ist
   gewollt (Sollbruchstellen, Zellen). Vorschlag: Für Teile mit Muster ersetzt die Musterprüfung G9
   (M3 überhangfrei, M5 im Teil) die Abdeckungsregel; die Abdeckung wird nur berichtet.
2. **Heutiges Format gegen M2/M4/M6 (Orakel O, S1 6 Schichten).** Ohne Muster ist der Schichtwechsel
   diagonal (42 mm), Mitre-Ecken haben Radius ≈ 7,6 mm < w/2, und der Verbinder Schale 0 → 1 läuft
   23 mm neben der Außenraupe. Vorschlag: G9 prüft M1–M7 hart nur bei Teilen mit Musterparametern und
   berichtet sie sonst.

## Weichen für den Nutzer

(gebündelt, je mit Empfehlung)

## Protokoll

### 2026-10-20 17:50 Vorbereitung (lokal)
- Branch `v2/muster` von `v2/strang` (99c802c) abgezweigt, Auftrag, Fortschrittsdatei und
  Herzschlag-Skript angelegt.
- Cloud-Routinen: ein Start-Lauf und stündliche Wächter von 19:00 bis 09:00 (Europe/Berlin).
- `spec/` und `verify/` bleiben gesperrt. SPEC-Ergänzungen kommen als Nachtrag nach `docs/muster/`,
  das Muster-Orakel als Vorschlag nach `verify_muster/`.

### 2026-10-20 18:10 M0 Einrichtung (Session start)
- `v2/strang` gemergt, `verify.py --fast` grün (G1, G2, G3, G5, G8; G4/G6/G7 nicht im Schnelllauf).
- Artefaktformat für Muster festgelegt (`docs/muster/ARTEFAKT-FORMAT.md`): neue `kind` `infill`/`web`/`outfill`,
  `closed=false` für offene Segmente, Schichtpfad = Ringfolge mit `link_next`, senkrechter Wechsel als
  Verbinder mit waagrechter Länge ≤ 0,5 mm, opt-in-Parameter `layer_order`, `infill_pattern`, `outfill_pattern`.
- M1-Workflow gestartet (R sonnet, K opus, O opus; K und O je mit Gegenlese-Agent).

### 2026-10-20 18:25 Nutzer-Nachtrag 18:20 übernommen (Session start)
- Nachtrag: Outfill = Sollbruchstellen (O2, Foto `docs/muster/referenz/fugenwand-foto.jpg`), dazu
  parametrischer 2D-Musterersteller. Prioritäten neu: Kern/Orakel → Fugenwand → Musterersteller →
  Infill-Wellen/alternate → O1/O3.
- Foto geprüft: Lesart des Vorbereiters passt (gerade Felder, stumpfe Fugen, gerundete Ecken, V-Stege zu
  Knoten, Rauten über den Fugen).
- Erster M1-Workflow (wf_d820e0f7-2b1) gestoppt, weil er den Nachtrag nicht kannte. Recherche Teil 1 war
  fertig und ist gemergt; Kern und Orakel als WIP-Commits gesichert und vom neuen Workflow fortgesetzt.
- Neuer Workflow wf_67176cf2-d22: R2, K (+Gegenlesen) → F Fugenwand (+Gegenlesen), O (+Gegenlesen).

### 2026-10-20 18:55 M2 vorgezogen (Session start)
- Kern-Schnittstelle (fd4536c auf v2/muster-kern) ist stabil dokumentiert, Familien registrieren sich per
  Datei unter `patterns/families/`. Deshalb startet M2 parallel zur Gegenlese von K/O:
  Workflow wf_3c365435-7f4 mit Wellen, Topologie → Mehrfach/Fermat, Musterersteller Backend → Web,
  je mit Gegenprüfung.

### 2026-10-20 19:30 K gemergt (Session start)
- Kern mit Gegenprüfung gemergt: `plan_pattern`, `measure`, `preview`, `preview_svg`, Presets, `fit_to_length`,
  Familien per Datei unter `patterns/families/`. Grundmuster: Schalen als ein Strang, Schalenwechsel als
  S-Kurve (Radius w) ohne Doppelmaterial, Naht in der Mitte eines Eckbogens. ruff grün, 63 Mustertests grün.

### 2026-10-20 19:55 O und F gemergt (Session start)
- Orakel `verify_muster/` (58 Selbsttests, CLI `python -m verify_muster.check <lauf>`), unabhängig von `roboprint`.
- Fugenwand mit drei Varianten (Gurt gespiegelt = Lesart des Nachtrags, Gurt versetzt, Rautenkette).
  Empfehlung des Agenten: Rautenkette, Feldlänge 300 mm, r = w (1,21 l je m und Schicht, Schalen 1,28 l).
  Gurtvarianten brauchen bei r = w mindestens 230 mm Wanddicke; bei 200 mm nur mit r ≈ 21 mm (M6-Warnung).
- Nach Merge: ruff grün, `pytest core verify_muster -n 2`: 449 bestanden, 2 übersprungen.

### 2026-10-20 20:15 Wellen und Musterersteller gemergt (Session start)
- Infill-Wellen `sinus`, `zickzack`, `trapez`, `maeander` (role infill) mit Kernänderung `shell_chain(open_end)`.
- Musterersteller: Reiter „Muster“ in der Kopfzeile (`/?view=muster`), Regler aus ParamSpecs, Entprellung 120 ms,
  SVG-Vorschau mit Folgeschicht, Kontakten und Verstößen, Presets speichern, SVG-Export; API und CLI.
  Vorschau-Laufzeit 70–110 ms bei 600×200 (Ziel 100 ms knapp), bei langen Modulen darüber – Kosten in `metrics`.
- Nach Merge ein Testkonflikt (Preset-Reihenfolge) behoben. ruff grün, `pytest core verify_muster`: 592 grün,
  Web lint/typecheck/test (141) grün.

### 2026-10-20 21:20 Topologie, Laufzeit, Katalog gemergt (Session start)
- **Befund Topologie:** `examples/Building-Architecture.ifc` hat **keine Öffnungen** (kein IfcOpeningElement,
  IfcWindow, IfcDoor); jeder Schnitt hat eine Insel. Einziger Querschnittswechsel in S2 ist die 45°-Schräge am
  Wandkopf. S5 (Modul mit Öffnung) wird deshalb synthetisch (Fenster in einer 200-mm-Wand).
- Topologie: je Insel ein Strang, Laibungsstege aus dem ganzen Teil (0 mm² Überhang über Brüstung),
  Abschrägung als Doppelring mit Wende; Grenze: je Laibung eine Fuge auf einer Wandseite (bis 41 mm tief),
  weil ein Strang nur zwei Enden hat. Mindestwanddicke mit Öffnung 150 mm.
- Laufzeit der Vorschau: Fugenwand und Schalen < 100 ms; die vier Wellenmuster 120–380 ms (Planung in
  `families/wellen.py`). Ein alter Absturz von `sinus` auf einem L-Querschnitt mit extremen Parametern ist offen.
- Nach Merge: ruff grün, `pytest core verify_muster`: 736 grün, 2 übersprungen.

### 2026-10-20 21:45 M2 abgeschlossen (Session start)
- Doppelwelle/Waben/Fermat gemergt. Doppelwelle geht in S1 (Band 50 mm) **nicht**: Hub 2A = 12,25 mm, Zellen
  ≤ 10,75 mm, Wenderadius 26,5 mm < w; nötig ist ein Band ≥ 55,5 mm (2 Schalen ab ≈ 206 mm Wand, 1 Schale
  ab 145 mm). Waben in S1 ebenso nicht (zwei Eckbögen ≥ 15 mm an 60°-Flanke brauchen 15 mm Hub).
- Laufzeittest der Vorschau bewertet nur, wenn die Last ≤ Kernzahl ist (sonst Skip mit Messwert), damit G8
  unter Last der Agenten nicht zufällig rot wird.
- Nach Merge: ruff grün, `pytest core verify_muster`: 805 grün (der Laufzeittest rot unter Last 12, jetzt Skip).

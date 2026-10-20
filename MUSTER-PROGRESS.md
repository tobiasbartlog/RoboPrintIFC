Herzschlag: 2026-10-20T18:50:10+02:00 · Session: start · Phase: M1 · Status: laeuft

# MUSTER-PROGRESS: Druckmuster (Infill und Outfill)

Auftrag: `docs/muster/AUFTRAG.md`. Herzschlag-Skript: `scripts/herzschlag.py`.
Die erste Zeile setzt nur das Skript.

## Aufgaben

| Aufgabe | Phase | Status | Branch | Commit |
|---|---|---|---|---|
| Einrichtung, Ausgangslage verify --fast, Artefaktformat (`docs/muster/ARTEFAKT-FORMAT.md`) | M0 | erledigt | v2/muster | 9b0510e |
| R Recherche → `docs/muster/recherche.md` (Teil 1) | M1 | erledigt, gemergt | v2/muster-recherche | a6b6636 |
| R2 Recherche Sollbruchstellen, Fachwerkwände | M1 | läuft (wf_67176cf2-d22) | v2/muster-recherche | |
| K Kern `core/src/roboprint/patterns/` (Schnittstelle, alternate, 2 Schalen, metrics M1–M7) | M1 | läuft (wf_67176cf2-d22, auf WIP a383b1f) | v2/muster-kern | |
| O Orakel `verify_muster/` mit Selbsttests | M1 | läuft (wf_67176cf2-d22, auf WIP add8523) | v2/muster-orakel | |
| F Fugenwand (Foto, O2) mit Varianten, Presets, Bildern – Priorität 2 | M1/M2 | läuft (wf_67176cf2-d22, nach K) | v2/muster-fugenwand | |
| 2D-Musterersteller: API `POST /api/patterns/preview`, CLI `pattern-preview`, Web-Reiter „Muster“ – Priorität 3 | M3/M4 | offen | v2/muster-ersteller | |
| I-Wellen (Sinus, Zickzack gerundet, Trapez/Mäander) | M2 | offen | v2/muster-wellen | |
| I-Mehrfach (Doppelwelle/Kettenglied, Waben, Fermat) | M2 | offen | v2/muster-mehrfach | |
| Outfill O1/O3 (nur wenn Zeit; O2 = Fugenwand) | M2 | offen | v2/muster-outfill | |
| Topologie (Öffnungen, Inseln, Laibungsstege, Naht, Übergänge) | M2 | offen | v2/muster-topologie | |
| Einbau Slicer + Vertrag + Schema/TS | M3 | offen | v2/muster-einbau | |
| Einbau Planer/Timing/DRL | M3 | offen | v2/muster-einbau | |
| Musterszenarien, `scripts/verify_muster.py`, SPEC-Nachtrag | M3 | offen | v2/muster-einbau | |
| Viewer: Musterwahl, 2D-Vorschau, Legende, Kennzahlen | M4 | offen | v2/muster-viewer | |
| Vergleich, MUSTERKATALOG, Testdrucke | M5 | offen | v2/muster-katalog | |
| Gegenprüfung und Härtung | M6 | offen | v2/muster | |
| Abschluss: Morgenbericht, PROGRESS, Draft-PR | M7 | offen | v2/muster | |

## Gate-Stand

| Prüfung | Status | Kennzahl | Stand |
|---|---|---|---|
| G1–G8 (`scripts/verify.py`) | --fast grün (G1 G2 G3 G5 G8) | Ausgangslage | M0 18:10 |
| Muster (`scripts/verify_muster.py`) | | | |

## Gate-Einwände

(Belege, wo ein bestehendes Kriterium mit einem Muster kollidiert. Die Entscheidung trifft der Nutzer.)

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

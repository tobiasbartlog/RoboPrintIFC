Herzschlag: 2026-10-18T22:43:38+02:00 · Session: orchestrator · Phase: P0

# PROGRESS — Nachtlauf v2

Ablauf und Regeln stehen in `spec/NACHTLAUF.md`, die Gates in `spec/SPEC.md` §11.

## Gate-Stand

| Gate | Status | Kennzahl | Stand |
|---|---|---|---|
| G1 Kinematik | rot | — | 2026-10-18 Vorbereitung |
| G2 Kollision | rot | — | |
| G3 Referenzmodul S1 | rot | — | |
| G4 Beispiel-IFC S2 + S3 | rot | — | |
| G5 DRL | rot | — | |
| G6 Viewer | rot | — | |
| G7 Laufzeit | rot | — | |
| G8 Qualität | rot | — | |

## Ausgangslage (Vorbereitung 2026-10-18)

Diagnose von v1 durch sechs Review-Agenten, Kurzfassung:

- **Zerlegung:** 0 von 12 Modulen und 0 von 8 Abschnitten kollisionsfrei.
- **Ursachen:**
  - J3-Grenze im falschen Gelenksystem geprüft.
  - IK-Zweig nur aus dem Seed gewählt.
  - Zerlegung standardmäßig ohne Kollisionsprüfung.
  - Gierfreiheit um die Düse nie genutzt.
- **Gegenprobe:** Mit korrekter Grenze und natürlichem Zweig ist ein Modul 600 × 906 mm frei
  (d_min 0,09 mm). Das Problem ist also lösbar.
- **Kollisionsanzeige:**
  - Fünf getrennte Zeitabbildungen im Viewer.
  - Druckstand ausgeblendet.
  - Eingefrorene unerreichbare Posen als rot gewertet.
  - Boden der untersten Reihe und Tisch fehlen als Hindernis.
- **DRL:**
  - ZYZ-Fehler bei B ≈ 180°: Düse um 180° verdreht.
  - AO-Kanäle 0/1/2 statt 1/2.
  - `movej(posx)` ohne `sol`.
  - `radius = 0`, also Stopp an jedem Punkt.
  - Totzeit nicht im Programm.
  - Globale IFC-Koordinaten.
- Details: `docs/doosan-drl.md`, `docs/ux-leitbild.md`, SPEC §12.

## Gate-Einwände

(Belege, falls ein Gate nach Ansicht eines Agenten falsch ist. Die Entscheidung trifft der Nutzer.)

## Annahmen, die der Nutzer bestätigen muss

Siehe SPEC §10 (mit „A“ markiert) und §13.

## Protokoll

### 2026-10-18 Vorbereitung
- Branch `v2-nachtlauf` angelegt. v1 nach `legacy/` verschoben, Assets bleiben.
- SPEC, NACHTLAUF, Szenarien S1–S3, Gate-Runner `verify/run.py`, Hooks, Cloud-Setup.
- Offen: alles ab P0.

### 2026-10-18 22:43 Start (orchestrator)
- Umgebung: Python 3.12.3 (/opt/fgc-venv), ifcopenshell/trimesh/fcl/pinocchio/coal/manifold3d ok,
  tesseract_robotics ok (optional), Node v22.22.0, Playwright 1.56.1, 4 vCPU.
- Session startete auf dem Default-Branch; der Guard-Hook greift trotzdem. Die Regeln
  (Push nur auf v2-nachtlauf und v2/*, kein Force-Push, kein Merge, Sperre spec/ + verify/ nach P0)
  hält der Orchestrator zusätzlich selbst ein und gibt sie an jeden Agenten weiter.
- Ausgangslage `verify.py` (voll): G1–G8 rot (alle Schritte "fehlt"), wie erwartet.
- Ohne ultracode-Freigabe: Agent-Tool mit Hintergrund-Subagenten in Worktrees, max. 6 parallel.

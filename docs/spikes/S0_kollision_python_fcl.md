# Spike S0 — python-fcl auf Windows + Distanz-Performance mit echter trajectory.json (prüft ADR-024, PRD #124)

Status: **grün** · 2026-07-08

## Frage

Läuft `python-fcl` auf Windows (Python 3.14, venv) stabil, und ist die
Mesh-Distanzrechnung Arm↔Druckstand schnell genug für den **automatischen
Kollisions-Befund je Simulation** (ADR-024) — bevor die Scheiben S1–S6
geschnitten werden? Dokumentierter Rückfall bei Scheitern: handkalibrierte
Kapseln (ADR-024-Revisionstrigger).

## Vorgehen

Vier Messsonden unter `docs/spikes/s0_scripts/` (Aufruf je Sonde im
Docstring; venv, Repo-Root). Testdaten: der echte Lauf
`runs/20260708-161603_slice_Denkmal` — die Trajektorie des Nutzer-Fotos
(M1013-Ellbogen in der Wand): 25 217 Samples, 82 Schichten à 10 mm,
Tool `30gut`, Basis bei y = 615 mm vor der Wand.

- **Armgeometrie:** die gevendorten URDF-`<collision>`-Meshes je Glied,
  in DH-Gliedframes gebracht mit **derselben Offset-Formel wie
  `convert_robot_meshes.py`** (Import, keine Kopie); Posen je Sample aus
  `OpwKinematics.link_frames` + `base_frame` der Trajektorie.
- **Druckstand-Proxy:** wallspec-Geometrie bei der aktuellen Schichthöhe
  gekappt (Oberkante = ⌊TCP-z / Schichthöhe⌋·Schichthöhe, TCP aus dem
  Tool-TCP wie `setup["tcp"]`), dazu eine Boden-Box; Hindernis-Manager je
  Schicht lazy gecacht. Basis↔Boden ist ausgenommen (erlaubter
  Dauerkontakt, montiert).
- Gemessen: Installation, Determinismus, ms/Sample für vier
  Geometrie-Varianten, Selbstkollision (nicht-benachbarte Paare),
  Volllauf, Tunneling-Kennzahl.

**Lehrgeld der ersten Sondenversion** (im Protokoll, damit S1 es nicht
wiederholt): Schichtzuordnung über die **Flansch**-Höhe baut den Druckstand
um die Werkzeuglänge zu hoch — alle 25 217 Samples meldeten Kollision
(min. −347 mm). Die Schicht muss aus der **TCP**-Höhe kommen.

## Ergebnis

- [x] **Installation grün.** `python-fcl 0.7.0.11` bringt ein
  `cp314-win_amd64`-Wheel, Import + `trimesh.collision.CollisionManager`
  funktionieren auf Anhieb (Smoke-Test exakt 200 mm zwischen zwei Boxen),
  keine DLL-/Runtime-Probleme. Zusatzpakete: `mapbox-earcut 2.0.0`
  (Triangulation fürs Kappen — braucht auch die Footprint-Extrusion in S1),
  `vhacdx 0.0.10` (Konvexzerlegung), `fast-simplification 0.1.13` (getestet,
  verworfen, s. u.). → **S1 nimmt `python-fcl`, `mapbox-earcut`, `vhacdx`
  in `fgc-core[geo]` auf.**
- [x] **Determinismus:** wiederholte Query und Manager-Neuaufbau liefern
  bitgleiche Distanzen — Goldens sind möglich (ADR-024-Konsequenz bestätigt).
  (VHACD-Determinismus über Maschinen hinweg prüft S1 per Golden.)
- [x] **Exakte Roh-Meshes allein sind zu langsam:** 23,9 ms/Sample →
  **602 s Volllauf** — untauglich für den automatischen Befund je Sim.
  Zwei Kostentreiber: signierte Distanz *durchdringender* BVH-Paare und
  exakte Nahdistanz getrennter Paare (32 ms) bei 3 k–47 k Faces je Glied.
- [x] **Urteilsgeometrie-Vergleich** (1 009 Posen-Teilmenge, gegen exakte
  Referenz; „verpasst/falsch" = Fehlklassifikation an der 0-mm-Schwelle):

  | Variante | ms/Sample | Abweichung (getrennt) | verpasst/falsch |
  |---|---|---|---|
  | A exakte Meshes (Referenz) | 21,5 | — | — |
  | B konvexe Hülle je Glied | 0,06 | untere Schranke; +15 % zu viel Rot/Gelb | 49 falsch |
  | D dezimiert (~1 500 Faces) | 3,5 | **bis +20 mm überschätzt** (gefährliche Richtung) | 9 verpasst |
  | E **VHACD-Konvexzerlegung** | 2,3 | ±5,5 mm max, ⌀ 0,31 mm | 2 verpasst / 3 falsch |

  Dezimierung scheidet aus (erfindet Abstand), die nackte Hülle warnt
  chronisch zu viel (genau das Kapsel-Argument aus ADR-024, nur milder).
  **VHACD ist formtreu und konvex-schnell.**
- [x] **S1-Rezept validiert (Volllauf, alle 25 217 Samples):**
  Breitphase = Glied-Hüllen-Distanz (untere Schranke der echten Distanz;
  > Sicherheitsabstand ⇒ sicher grün), Nahphase = VHACD-Distanz als Urteil:
  **44 s statt 602 s** (1,74 ms/Sample) — und das bei pathologischen 66 %
  Nahphasen-Anteil dieser Kollisions-Trajektorie; gesunde Bahnen liegen bei
  wenigen Sekunden. Klassifikation deckungsgleich mit der exakten Referenz
  (7 548 vs. 7 538 Samples ≤ 0 mm; 14 756 vs. 14 698 < 50 mm).
- [x] **Offline-Anteil gehört ins Artefakt:** Hüllen + VHACD kosten einmalig
  21,9 s je Roboter → als deterministisches Konvertier-Derivat in
  `fgc.collision.robot_geometry` cachen (Muster `convert_robot_meshes.py`),
  nicht in den Simulationspfad. Druckstand-Rebuild je Schicht ist
  vernachlässigbar (0,22 s für 82 Schichten inkl. BVH-Aufbau).
- [x] **Selbstkollision:** 15 nicht-benachbarte Gliedpaare paarweise =
  16,7 ms/Sample naiv — braucht in S1 dieselbe Breitphase (Hüllen-Paare
  zuerst); min. Paarabstand im Testlauf 33 mm (keine Selbstkollision).
- [x] **Fachlicher Befund als Nebenprodukt:** die Foto-Trajektorie
  kollidiert wirklich — 7 538/25 217 Samples ≤ 0 mm (min. −99 mm exakt),
  **278 rote Intervalle**, Top-Verursacher `link5`/`link2`/`link4` gegen den
  Druckstand, dazu 119 Samples `link5` unter Bodenniveau. Das Nutzer-Foto
  ist quantitativ bestätigt; genau dieser Lauf taugt als Regressions-Fixture
  für S1/S2.
- [x] **Tunneling-Kennzahl (offener PRD-Punkt 1):** TCP-Schrittweite median
  19,9 mm, p99 20 mm — Druckzüge sind gegen die 50-mm-Schwelle dicht genug
  gesampelt. **Travel-Moves springen bis 1 052 mm je Sample-Schritt** —
  Travel-Tunneling ist real; die bewusste v1-Grenze (sample-basiert) bleibt
  vertretbar, sollte aber im Befund als „Travel nicht lückenlos geprüft"
  ehrlich beschriftet werden.

## Grenzen der Sonde (kein Gegenstand des Spikes, für S1 notiert)

- **Endeffektor fehlt** als Kollisionskörper (offener PRD-Punkt 3) — die
  Distanzen um die Düse sind ohne Tool-Hülle optimistisch.
- **Freizone** nicht modelliert; die Sonde hat implizit eine (Druckstand
  endet an der Oberkante der letzten fertigen Schicht unter dem TCP).
- Druckstand aus der **gekappten wallspec-Geometrie** statt echter
  Footprint-Prismen (S1 extrudiert die Slicer-Umrisse); die wallspec war
  nicht wasserdicht (`is_watertight = false`), das Kappen funktionierte
  trotzdem — echte Prismen sind sauber geschlossen zu bauen.
- Schichtzuordnung über TCP-Höhe ist eine Näherung; S1 kennt die Schicht
  exakt aus dem Toolpath.

## Empfehlung für S1 (als Nachtrag in ADR-024 übernommen)

1. `robot_geometry` konvertiert offline je Glied: VHACD-Konvexstücke
   (Urteilsgeometrie) + konvexe Hülle (Breitphase), deterministisch
   abgelegt und im Roboterkatalog referenziert.
2. `check` rechnet zweiphasig: Hüllen-Distanz, nur bei
   ≤ Sicherheitsabstand VHACD-Distanz; berichtete Eindringtiefen stammen
   aus der VHACD-Geometrie (±5 mm formtreu). Die exakten Roh-Meshes bleiben
   Referenz für Tests/Goldens.
3. Selbstkollision über dieselbe Zweiphasen-Mechanik, benachbarte Paare
   ausgenommen; Basis↔Boden ausgenommen.
4. Dependencies: `python-fcl`, `mapbox-earcut`, `vhacdx` → `fgc-core[geo]`.

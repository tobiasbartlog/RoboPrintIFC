# Tesseract-Spike (A1.6, SPEC 5.2)

Frage: Löst Tesseract/Descartes mit `sampleToolAxis` die Druckaufgabe S1 schneller oder besser als der eigene Ladder-Graph?
Code: `experiments/tesseract_spike/` (`build_env.py`, `run_descartes.py`, `sweep.py`, `fit_opw.py`). Wandzeit des Spikes: ca. 25 min.

## Setup
- `tesseract-robotics-nanobind 0.35.0.8` (Python 3.12, 2 Threads). Das URDF lädt nach zwei Anpassungen: `package://` durch `file://` ersetzt; das Attribut `tesseract:make_convex` ist Pflicht (hier `true`, also eine konvexe Hülle je Mesh, kein VHACD).
- SRDF und Plugin-YAML selbst geschrieben: Gruppe `base_link`→`link_6`, ACM, Kinematik-Plugin OPW + KDL, Kontaktmanager Bullet.
- **OPW-Parameter für den M1013 passen exakt** (per Fit gegen die URDF-FK mit `py_opw_kinematics` gefunden): a1=0, a2=0, b=0,0345, c1=0,1525, c2=0,62, c3=0,559, c4=0,121, Offsets 0, Vorzeichen +1. Gelenkwinkel gleich URDF-Konvention, Werkzeugrotation Identität. Positionsabweichung zur URDF-FK 0,1 bis 0,4 mm (die URDF rundet pi/2 auf 1,571).
- Der TCP muss als eigener Link `tcp` im URDF stehen, die Gruppe endet aber an `link_6`. Endet sie am TCP, ignoriert das OPW-Plugin den TCP-Versatz stillschweigend (erster Versuch lieferte "Lösungen" mit falscher Pose).
- Welt: Tisch als konvexe Hülle von `doosantisch.stl`, Druckstand als Box (Schichten 1..k-1), Werkzeugkörper = konvexe Hülle der Vertices außerhalb r_free = 40 mm um den TCP (Spitze ausgenommen). Kein Boden.
- Aufgabe: Rechteckring 560 x 160 mm um die Mitte der Arbeitsfläche, Wegpunkte alle 20 mm (73), TCP-z nach unten, `sampleToolAxis` z, 15° (24 Samples), Abstand 10 mm (Vertex-Prüfung).

## Zahlen (Schicht 20, 2 Threads)
| Variante | Ergebnis | Laufzeit Solve |
|---|---|---|
| ohne Kollision | Lösung, aber 73/73 Samples kollidieren (link_4 im Tisch, bis 0,31 m tief) | 0,06 s |
| Vertex-Kollision, 10 mm | Lösung, 0 Samples < 10 mm (unabhängiger Nachcheck mit Bullet) | 4,3 s |
| + Edge-Kollision | gleiche Lösung | 137 s |
| Schicht 39 / Ring bei y+100 mm | Lösung | 1,7 s / 2,0 s |
| Samples 5° statt 15° | Lösung | 4,6 s |
| + redundante Lösungen | gleiche Lösung | 37 s |

Lösung: max |Δq| zwischen Wegpunkten 0,04 rad, kein Zweigwechsel (q3, q5 ohne Vorzeichenwechsel), Gelenkgrenzen eingehalten. Schicht 1 scheiterte nur, weil der Stand dort Höhe 0 hat (Spike-Artefakt).
Knoten- und Kantenzahlen sind aus Python nicht abfragbar (nur Erfolg und Pfad). Umgebungsaufbau 0,5 s.

## Bewertung
- Qualität: Ein Ring wird gefunden, aber nur als Gelenkdistanz-Optimum. Es fehlen Abstandskosten (λ_d), ψ-Kosten (λ_ψ), die Kantenschranke Δq_max und die Zweigstrafe. Nachrüstbar über Python-Subklassen (`createEdgeEvaluator`/`createStateEvaluator`), deren Aufrufe dann pro Knoten durch den Interpreter laufen.
- Kollision: Nur konvexe Hüllen (konservativer als VHACD, die Treue ±6 mm ist so nicht erreichbar). Es gibt kein d_min je Pose, nur "Kontakt innerhalb Margin ja/nein". Status `ok/warn/collision/unreachable` und Zeugenpunkte wären separat zu bauen. Der Druckstand je Schicht erfordert einen Umbau der Environment (URDF neu laden, 0,5 s).
- Geschwindigkeit: 4 s pro Ring bei Vertex-Prüfung. Ein Modul mit 40 Schichten kommt damit auf Minuten, ohne Travel. Ein Vergleich mit dem eigenen Planer war nicht möglich (auf diesem Branch nicht vorhanden); die Größenordnung ist nicht automatisch besser.
- API-Stabilität: Das Binding ist jung (0.35) und hat Lücken (kein `flattenCopy`, `getState` nur über Namen/Werte, Konvexpflicht per Attributfehler, stilles Ignorieren des TCP im OPW). Die Wheel bringt eigene Bullet/VTK/PCL-Bibliotheken mit.
- Integrationsaufwand hinter der Backend-Naht: mittel (ca. 3 bis 5 Tage für URDF/SRDF-Generator, Stand-Updates, Statusabbildung, Angleich an die Orakel).

## Empfehlung
**Hinter der Backend-Naht übernehmen: nein.** Der Vorteil (fertiger Ladder-Graph, schnell mit OPW) wiegt die fehlenden Kosten- und Statusfunktionen und die Hüllen-Kollision nicht auf; G3 würde dadurch nicht besser. Als optionaler zweiter Backend-Kandidat bleibt es denkbar, falls der eigene Planer an der Laufzeit scheitert. Der OPW-Parametersatz oben ist unabhängig davon für die eigene IK nutzbar.

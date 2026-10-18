# RoboPrintIFC v2

Vom IFC-Wandmodell zu kollisionsfrei druckbaren Modulen und einem lauffähigen
Doosan-M1013-Programm (DRL) für den Lehm-3D-Druck. Dies ist ein **geführter
Neustart**: `legacy/` enthält v1 als Nachschlagewerk, alles Neue entsteht in
`core/` (Python-Paket `roboprint`) und `web/` (React-Viewer).

Fertig heißt **grün**: `python scripts/verify.py` endet mit Exit-Code 0.

## Wegweiser

- `spec/SPEC.md`: was gebaut wird. Konventionen, Datenverträge, Algorithmen und die
  Abnahme-Gates G1–G8. Lies die betroffenen Abschnitte vor jeder Implementierung.
- `spec/NACHTLAUF.md`: Phasen, Rollen, Merge-Ablauf. Lies sie, wenn du orchestrierst.
- `PROGRESS.md`: aktueller Stand. Lies sie beim Start, ergänze sie am Ende jeder Aufgabe.
- `docs/doosan-drl.md`: belegte DRL-Semantik. Lies sie vor jeder Arbeit an DRL-Ausgabe,
  Bewegungsbefehlen, Gelenkkonvention oder Analogausgängen.
- `docs/ux-leitbild.md`: Ziel-UX. Lies sie vor jeder Änderung in `web/`.
- `legacy/`: v1, nur lesen. Portiere daraus (Liste in SPEC §12); importiere nie daraus.

## Befehle

- `python scripts/verify.py`: alle Gates. `--gate G3` für eines, `--fast` ohne die langen
  Szenarien G4/G7. Bericht unter `runs/verify/report.json`.
- `python -m pytest core -q -n 2` und `python -m ruff check core verify`
- `npm --prefix web run lint|typecheck|test|e2e`
- Die übrigen Skripte stehen in `core/pyproject.toml` und `web/package.json`.

## Konventionen

Die eine Quelle ist SPEC §2. Diese Kurzform steht hier, weil jede Änderung sie berührt:

- Intern Millimeter und Radiant, Z nach oben, rechtshändig. Grad gibt es nur im DRL-Emitter.
- Gelenkwinkel immer in **Doosan-Steuerungskonvention** (= URDF-Nullstellung). Die
  Home-Pose (0, 0, 90, 0, 90, 0)° ist gültig. Achsgrenzen gelten in dieser Konvention.
- Frames: W (Workstation), B (Roboterbasis), S (Arbeitsfläche), P (Teil), L (Wand). Jeder
  Übergang hat genau eine Funktion in `core/src/roboprint/frames.py`.
- Quaternionen in der Reihenfolge (w, x, y, z).
- Status je Sample: `ok`, `warn`, `collision`, `unreachable`. Unerreichbar ist ein eigener
  Status und wird nie als Kollision oder als frei gezählt.

## Arbeitsweise

- **Gate zuerst**: Jede Aufgabe nennt das Gate, das sie grün macht. Erledigt ist sie, wenn
  das Gate grün ist, die Unit-Tests grün sind, ein PROGRESS-Eintrag steht und ein Commit da ist.
- Die **Orakel** in `verify/` sind unabhängig: Sie rechnen mit Pinocchio, Coal und der URDF
  und lesen nur Artefakte. Sie importieren `roboprint` nie.
- `spec/` und `verify/` sind nach Phase P0 gesperrt (Hook). Hältst du ein Gate für falsch,
  trage die Belege unter „Gate-Einwände“ in PROGRESS.md ein und arbeite an anderem weiter.
- Schwellen aus der SPEC bleiben fest. Wenn etwas physikalisch unmöglich ist, belege es mit
  Zahlen und Szenario in PROGRESS.md; das ist ein gültiges Ergebnis.
- Tests prüfen Verhalten gegen Orakel, Physik oder Herstellerdoku. Goldens nur für externe
  Formate (DRL-Text) und erst, wenn der Fake-Controller sie akzeptiert.
- Kleine, tiefe Module mit schmaler Schnittstelle; Dateien möglichst unter ~600 Zeilen.
- Bezeichner im Code englisch, UI-Texte und Doku deutsch. Fachbegriffe siehe SPEC §3.
- Commits: Conventional Commits, einer je erledigter Aufgabe. Push nur auf `v2-nachtlauf`
  und `v2/*`.

## Fallstricke

- Die Cloud-VM hat 4 vCPU. Wenn andere Agenten laufen, nimm `pytest -n 2`.
- `robots/collision/*`, `robots/reachability/*` und der `kinematics`-Block in
  `robots/doosan_m1013.json` stammen aus v1 und nutzen die alte DH-Konvention
  q_dh = q_doosan + (−180°, +90°, +90°, 0, 0, 0). v2 baut Kinematik und Kollisionsgeometrie
  aus `third_party/doosan_m1013/urdf/` und deren Meshes; die Gelenkgrenzen in der JSON sind
  bereits Steuerungskonvention.
- `tools/30gut`: Der TCP liegt 134 mm neben der Flanschachse, die Düsenachse ist Flansch-X.
  Eine Drehung um die Düsenachse bewegt deshalb alle sechs Achsen.
- Die Wände in `examples/Building-Architecture.ifc` liegen in globalen Koordinaten
  (x ≈ 7000 mm). Ohne die Wand-Frame-Transformation (SPEC §2) ist nichts erreichbar.
- `legacy/docs/design-log.md` ist 878 KB groß: gezielt greppen.

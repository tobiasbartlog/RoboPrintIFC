# Spike S3 — IK-Roundtrip Doosan (prüft ADR-002, Orakel ADR-009a)

Status: **grün (Software)** · offener HITL-Punkt: Grasshopper-Stichprobe

## Frage
Lässt sich der für den Doosan M1013 zuständige Solver aus visose/Robots korrekt
nach Python portieren (FK/IK), und schließt der 1000-Posen-Roundtrip FK→IK→FK
innerhalb der Toleranzen?

## Vorgehen
1. Im Robots-Quellcode verifizieren, welcher Solver für den M1013 verwendet wird
2. Solver portieren, Attribution in NOTICE (ADR-010)
3. Orakel: 1000 Zufallsposen, Roundtrip FK→IK→FK, Toleranzprüfung
   (Position < 0,01 mm, Orientierung < 1e-6 rad)
4. Stichprobe (~20 Targets) gegen Robots in Grasshopper (HITL)

## Ergebnis

- [x] **Solverfamilie bestätigt — aber anders als in ADR-002/S3 vermutet.**
  Der M1013 nutzt in Robots **`SphericalWristKinematics` (OPW, Ortho-Parallel-
  Basis + Spherical Wrist)**, **nicht** `OffsetWristKinematics`. Der Offset-
  Wrist-Solver ist in Robots ausschließlich den Universal Robots (`RobotUR`)
  zugeordnet. Belegkette im Quellcode (Commit-Stand siehe Protokoll):
  - `src/Robots/RobotArms/RobotDoosan.cs`:
    `private protected override SphericalWristKinematics CreateSolver() => new(this);`
  - `src/Robots/RobotArms/RobotUR.cs`:
    `private protected override OffsetWristKinematics CreateSolver() => new(this);`
  - `src/Robots/Kinematics/SphericalWristKinematics.cs`: analytische OPW-Lösung,
    im Kommentar als „adapted from https://github.com/Jmeyer1292/opw_kinematics"
    ausgewiesen.
  Portiert wurde folgerichtig **der tatsächlich verwendete OPW-Solver** — genau
  die Verifikationspflicht, die ADR-002 vor dem Port fordert. (Randnotiz: Der
  Robots-`OffsetWristKinematics` verweist seinerseits auf ur_kinematics/
  ros-industrial; für den Doosan irrelevant.)

- [x] **Roundtrip grün: 1000/1000.** `core/tests/test_kinematics.py::
  test_roundtrip_1000_poses` (seed `20260704`). Für jede erreichbare IK-Lösung
  jeder Zufallspose reproduziert die FK die Zielpose; gemessene Maxima liegen um
  Größenordnungen unter den festgenagelten Toleranzen (analytisch ~1e-9 mm /
  ~1e-12 rad). Zusätzlich prüft `test_roundtrip_all_valid_solutions_exact`, dass
  **alle** erreichbaren Lösungen (nicht nur eine) frame-exakt sind.
  - **Toleranzen (festgenagelt):** Position < 0,01 mm, Orientierung < 1e-6 rad.
  - **Ausreißer/Singularitätsnähe:** Die automatisierte Stichprobe meidet das
    Handgelenks-Singularitätsband (Achse 5 nahe 0/±π, Marge 0,1 rad > Solver-
    Schwelle 1,24e-2 rad). Im Singularitätszweig koppelt Robots Achse 4 und 6
    (setzt j4=0 und bündelt die Rotation in j6); die Lösung bleibt *eine gültige*
    Auslage, ist aber nicht mehr frame-exakt gegenüber der Ausgangskonfiguration
    (Position weiter exakt, Orientierung bis ~1e-4 rad). Das ist erwartetes
    OPW-Verhalten und Gegenstand der Konfig-/Singularitätswahl in **Issue #11**,
    nicht des Roundtrip-Orakels.

- [ ] **Grasshopper-Differenzvergleich: offen (HITL).** Der Vergleich identischer
  Targets gegen Robots in Grasshopper ist Handarbeit für den Menschen und
  **noch nicht erfolgt**. Durchführung: ~20 Targets in Grasshopper mit Robots
  lösen (M1013), dieselben Targets mit `OpwKinematics.inverse` rechnen, je
  Konfiguration die Gelenkwinkel-Differenz bilden (Konfigurationswahl
  Shoulder/Elbow/Wrist beachten — Bitschema identisch zu Robots'
  `RobotConfigurations`: Shoulder=1, Elbow=2, Wrist=4). Erwartung: Differenz im
  numerischen Rauschen. → Ergebnis hier eintragen: max. Abweichung ___

- [x] **Portierter Code lebt in `core/src/fgc/kinematics/`** (`opw.py`), FK/IK als
  reguläres Modul (kein Wegwerf-Spike), inkl. dauerhaftem pytest-Orakel.

## Portierungsentscheidungen
- **Einheiten (ADR-006):** intern mm/Radiant/Quaternion `[w, x, y, z]`; DH-Werte
  (a, d in mm; alpha, Achsgrenzen in Radiant) in `robots/doosan_m1013.json`.
- **FK = Standard-DH** (Robots `MechanismKinematics.DH`); für den M1013 wendet der
  OPW-Zweig **keine** zusätzliche Flanschrotation an (anders als der Offset-Wrist).
- **IK zeilenweise portiert** aus `SphericalWristKinematics.InverseKinematics`,
  inkl. der abschließenden Abbildung `_signs`/`_start` auf die Roboter-Gelenk-
  konvention und Normierung auf [-π, π]. `acos`-Domänenschutz bildet Robots'
  `double.IsNaN`-Zweig 1:1 nach (Winkel 0 + „unreachable").
- **M1013-Geometrie** aus Robots-Bibliothek (Branch `libraries`, RWTH.xml):
  a = [0, 620, 0, 0, 0, 0] mm, d = [152.5, 34.5, 0, 559, 0, 121] mm,
  alpha = [π/2, 0, π/2, -π/2, π/2, 0], Achsgrenzen J3 ±160°, sonst ±360°.

## Protokoll
- **2026-07-04** — Robots-Quellcode (GitHub `visose/Robots`, Branch `master`) via
  gh-API inspiziert. Befund: Doosan → `SphericalWristKinematics` (OPW), nicht
  Offset-Wrist (s. o.). Port nach `core/src/fgc/kinematics/opw.py`, 1000-Posen-
  Orakel grün (`core/tests/test_kinematics.py`), Attribution in NOTICE. Offen:
  Grasshopper-Stichprobe (HITL).

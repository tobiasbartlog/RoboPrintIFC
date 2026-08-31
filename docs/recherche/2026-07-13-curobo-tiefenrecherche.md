# Tiefenrecherche: NVIDIA cuRobo — Neubewertung gegen Primärquellen + Implementierungsplan

**Datum:** 2026-07-13
**Vorgänger:** [2026-07-12-nachtrag-neuheitskern-shen2026.md](2026-07-12-nachtrag-neuheitskern-shen2026.md) (Abschnitt 3: cuRobo geprüft und abgelehnt, mit Revisionstrigger)
**Anlass:** Tobias will cuRobo trotz Ablehnung neu bewertet haben — für die
Kollisionserkennung und wegen der geplanten **Tiefenkamera** (der „Code, den
es dafür gibt": die RealSense-/nvblox-Beispiele in cuRobo v1 bzw. der
Mapper in cuRoboV2, s. Abschnitt 5). Die Vorgänger-Recherche hatte cuRobo
nur über **Sekundärquellen** geprüft; diese Recherche geht gegen Doku,
Quellcode, Issues, Lizenztexte und Paper.

**Verifikations-Status (ehrlich):**

- **Quellcode-geprüft (Volltext gelesen, Stand `main` 2026-07-13):**
  `curobo/collision_checking.py`, `curobo/_src/collision/collision_robot_scene.py`,
  `curobo/_src/geom/collision/collision_scene.py`, `curobo/scene.py`,
  `curobo/perception.py`, `curobo/_src/perception/mapper/mapper_cfg.py`,
  Auszüge aus `curobo/_src/perception/mapper/mapper.py` und
  `curobo/_src/geom/collision/checker_collision.py`, `curobo/robot_builder.py`,
  `curobo/sphere_fit.py`, `curobo/types.py`, `curobo/inverse_kinematics.py`,
  `curobo/runtime.py`, `pyproject.toml`, `README.md`, `CHANGELOG.md`,
  `docs/getting-started/installation.rst`, `docs/reference/benchmarks.rst`,
  `curobo/examples/getting_started/volumetric_mapping.py` und
  `build_robot_model.py`, `curobo/tests/conftest.py`; außerdem die
  Community-Config [Lab-CORO/curobo_doosan `src/m1013/m1013.yml`](https://github.com/Lab-CORO/curobo_doosan/blob/main/src/m1013/m1013.yml).
- **Repo-Metadaten via GitHub-API verifiziert:** Lizenz-SPDX (`Apache-2.0`
  auf `main`), Release-Historie (v0.8.0 am 2026-04-18), Datei-Bäume von
  `main` und Tag `v0.7.8`, Issue-Liste (letzte 30, sehr aktiv,
  Push 2026-07-10).
- **Doku-/Webseiten werkzeuggestützt extrahiert** (Extraktions-Tool fasst
  Seiten zusammen; wörtliche Zitate sind so übernommen, wie das Werkzeug
  sie geliefert hat — nicht Screenshot-verifiziert): curobo.org (v1-Doku),
  v1-Install-Seite, v1-Performance-Tuning-Seite, nvblox-README/-Lizenz.
- **Paper NICHT als PDF-Volltext gelesen:** arXiv-Abstract-Seiten von
  [2310.17274](https://arxiv.org/abs/2310.17274) (cuRobo v1) und
  [2603.05493](https://arxiv.org/abs/2603.05493) (cuRoboV2) plus
  arXiv-HTML-Extraktion von 2603.05493v2. Zahlen daraus sind
  extraktions-, nicht lektüregeprüft.
- **Aussagen Dritter (Trefferlage):** cuRobo-Discussion #272 (M1013-Config),
  README von [DoosanRobotics/doosan-robot-isaac-driver](https://github.com/DoosanRobotics/doosan-robot-isaac-driver).
- **Nicht geprüft:** kein eigener Testlauf (keine NVIDIA-GPU-Umgebung in
  dieser Session); alle Performance-Zahlen sind Herstellerangaben.

---

## 0 Das eine Ergebnis vorweg: cuRobo ist seit April 2026 ein anderes Projekt

Die Ablehnung vom 2026-07-12 wurde gegen **cuRobo v1** (bis v0.7.8)
ausgesprochen. Am **18.04.2026** erschien **v0.8.0 „cuRoboV2 research and
Open Source (Apache 2.0)"** ([Releases](https://github.com/NVlabs/curobo/releases),
via GitHub-API verifiziert) — ein **kompletter Rewrite**:

- **Lizenzwechsel:** v0.7.8 stand unter der „NVIDIA License" —
  *„The Work and any derivative works thereof only may be used or intended
  for use non-commercially"*, wobei „non-commercially" definiert ist als
  *„for research or evaluation purposes only"*
  ([LICENSE@v0.7.8](https://github.com/NVlabs/curobo/blob/v0.7.8/LICENSE)).
  `main` steht jetzt unter **Apache-2.0** (SPDX via API bestätigt;
  [LICENSE@main](https://github.com/NVlabs/curobo/blob/main/LICENSE);
  README: *„cuRobo is released under the Apache 2.0 license"*; Beispiel-
  Roboter-Assets separat in `LICENSE_ASSETS`). Kommerzielle Nutzung,
  Redistribution, Modifikation: erlaubt.
- **API-Bruch:** README: *„cuRoboV2 is a significant rewrite and the public
  API has changed from cuRobo v1. If you depend on the v1 API, pin to the
  v0.7.8 tag."* Changelog 0.8.0: *„Major refactor breaks most existing api."*
  Die in der Aufgabenstellung genannten v1-Klassen (`RobotWorld` in
  `src/curobo/wrap/model/robot_world.py`, `WorldCollision`/`WorldMeshCollision`/
  `WorldBloxCollision`/`WorldVoxelCollision` in `src/curobo/geom/sdf/world*.py`,
  `CudaRobotModel` in `src/curobo/cuda_robot_model/`) existieren nur noch im
  v0.7.8-Baum.
- **nvblox raus, eigener Mapper rein:** cuRoboV2 hat **keine
  nvblox-Abhängigkeit mehr**; die Tiefenkamera-Schiene ist ein hauseigenes
  block-sparses TSDF/ESDF-Subsystem (`curobo/_src/perception/mapper/`,
  Abschnitt 5).
- **Neues Paper:** [arXiv 2603.05493](https://arxiv.org/abs/2603.05493)
  „cuRoboV2: Dynamics-Aware Motion Generation with Depth-Fused Distance
  Fields for High-DoF Robots" (Sundaralingam, Murali, Birchfield;
  v1 05.03.2026, v2 16.04.2026).
- **Doku-Falle:** [curobo.org](https://curobo.org/) serviert weiterhin die
  **v1**-Doku (nvblox, Isaac-Sim-Beispiele, „experimental support for
  Windows"); die V2-Doku liegt unter
  [nvlabs.github.io/curobo](https://nvlabs.github.io/curobo) bzw. im Repo
  unter `docs/`. Wer heute curobo.org liest, liest das alte Projekt.

Das Projekt ist sehr lebendig: 1 689 Stars, 6 offene Issues, letzter Push
2026-07-10, laufend gemergte Fixes (GitHub-API 2026-07-13).

---

## 1 Architektur & Fähigkeiten (Frage 1)

### 1.1 Was cuRoboV2 ist

GPU-Bibliothek (PyTorch + CUDA + [Warp](https://github.com/NVIDIA/warp))
für: FK/IK (optimierungsbasiert, batch), Kollisionsprüfung
(Roboter↔Welt + Selbstkollision), Trajektorienoptimierung (B-Spline,
momentenbewusst), geometrische Planung (PRM), MPC, Motion-Retargeting,
Volumetrie aus Tiefenbildern ([README](https://github.com/NVlabs/curobo),
`curobo/`-Modulliste). CUDA-Kernel werden zur Laufzeit über `cuda-core`
kompiliert (Kernel-Quellen als Package-Data, `pyproject.toml`), optional
ein pybind-Backend.

### 1.2 Kollisionswelt-Repräsentationen (Quellcode-verifiziert)

`curobo/_src/geom/collision/collision_scene.py` (Klasse `SceneCollision`)
bündelt `SceneData` (GPU-Tensor-Speicher) + `CollisionChecker` (Warp-Kernel).
Welt-Typen laut `collision_types`-Property und `curobo/scene.py`:

| Typ | Klasse (`curobo.scene`) | Bemerkung |
|---|---|---|
| Quader | `Cuboid` | analytisch |
| Kugel/Kapsel/Zylinder | `Sphere`, `Capsule`, `Cylinder` | analytisch |
| Mesh | `Mesh` | Warp-Mesh-SDF-Abfrage, `max_distance`-Kappe (`checker_collision.py`) |
| Voxel-/SDF-Gitter | `VoxelGrid` | Distanzfeld als `feature_tensor`; Quelle: eigener Code **oder** `Mapper.compute_esdf()` |

Tiefenkamera-Welt: nicht mehr über nvblox, sondern `Mapper` → `VoxelGrid`
(Abschnitt 5). Szenen-Verwaltung ist **inkrementell**: `SceneData.add_obstacle`,
`remove_obstacle`, `update_obstacle_pose`, `enable_obstacle`,
`update_voxel_data(voxel_coords, features)` — alle in
`collision_scene.py`/`data_scene.py` mit vorreservierten Caches
(`cache={"cuboid": N, "mesh": M, "voxel": L}`).

### 1.3 Roboter-Kollisionsmodell: **ausschließlich Kugeln**

Der Roboter ist in cuRobo **immer eine Kugelmenge** — es gibt keinen
Exakt-Mesh-Modus für den Arm (`curobo/sphere_fit.py`: *„cuRobo represents
robot links and scene obstacles as collections of spheres for fast GPU
collision checking"*). Erzeugung: `RobotBuilder.fit_collision_spheres()`
mit dem **MorphIt**-Optimierer (Adam-basiert, Loss aus *coverage* vs.
*protrusion*, `--sphere-density` steuert die Anzahl;
`curobo/examples/getting_started/build_robot_model.py`). Die Franka bekommt
im Tutorial 87 Kugeln über 9 Links, mit Gütemetriken je Link
(`cover%`, `protr%`, `prot_mm`, `gap_mm`, `vol_ratio`). Wichtig für uns:
Die Kugel-Näherung ist **nicht konservativ per Konstruktion** — sie hat
sowohl Überstand (falsch-positiv nah an der Wand) als auch Lücken
(falsch-negativ), beides wird gemessen, aber nicht auf null garantiert.
Selbstkollision: Kugelpaar-Prüfung mit Ignore-Matrix
(`compute_collision_matrix()`, per Zufalls-Sampling erzeugt;
V2-Kernel „map-reduce self-collision", README).

### 1.4 Python-Einstieg für reine Kollisionsabfrage (ohne Motion-Gen)

Genau dafür existiert ein eigenes öffentliches Modul —
[`curobo/collision_checking.py`](https://github.com/NVlabs/curobo/blob/main/curobo/collision_checking.py):
*„This module provides robot-scene collision checking for custom pipelines.
… Use this module when building custom collision-aware pipelines outside
the main solvers."*

```python
from curobo.collision_checking import RobotCollisionChecker, RobotCollisionCheckerCfg
cfg = RobotCollisionCheckerCfg.load_from_config(robot_config="m1013.yml", scene_model="scene.yml")
checker = RobotCollisionChecker(cfg)
scene_d, self_d = checker.get_scene_self_collision_distance_from_joints(q)  # q: [batch, horizon, dof]
```

Kernmethoden (alle in
[`curobo/_src/collision/collision_robot_scene.py`](https://github.com/NVlabs/curobo/blob/main/curobo/_src/collision/collision_robot_scene.py),
Klasse `RobotSceneCollision`, Volltext gelesen):

- `get_scene_self_collision_distance_from_joints(q)` — **eine** batchweise
  Abfrage liefert Welt- **und** Selbstkollisionsdistanz je Sample;
  differenzierbar (PyTorch-Autograd).
- `validate(q)` — binäre Frei/Kollidiert-Maske je Konfiguration.
- `get_collision_vector(...)` — Distanz + Gradient (für Advisor-artiges).
- `update_world(scene_cfg)`, darunter `SceneCollision.load_collision_model`,
  `update_obstacle_pose`, `enable_obstacle`, `update_voxel_data`.
- `get_point_robot_distance(points, q)` — Distanz **Punktwolke ↔
  Roboterkugeln**. Das ist strukturell exakt die Shen-Inversion aus
  PRD #183 (Druckstand als Punktwolke gegen den Arm), nur mit Kugeln
  statt Glied-SDFs, GPU-parallel in einer JIT-Funktion
  (`_point_robot_distance`, Zeile ~518 ebd.).
- `get_swept_sphere_distance(...)` (`collision_scene.py`) — **Swept-Volumen**
  über Trajektorienschritte. Das adressiert genau die in ADR-024 bewusst
  offen gelassene v1-Grenze „Travel-Tunneling bei ~1-m-Sprüngen".

Batch-IK separat: `curobo.inverse_kinematics.InverseKinematics`
(kollisionsbewusst, seeds-parallel; Benchmark s. Abschnitt 7). Für unseren
Anwendungsfall (Urteil über **gegebene** Gelenkbahnen aus der eigenen
OPW-IK) ist der IK-Teil nicht nötig — der Checker konsumiert direkt
`joints`-Tensoren.

---

## 2 Eigener Roboter: Doosan M1013 (Frage 2)

- **Keine Doosan-Config im cuRobo-Repo** (v0.7.8- und main-Baum per API
  durchsucht: 0 Treffer „doosan"; mitgeliefert sind u. a. Franka, UR5e/UR10e,
  Unitree G1, in v1 zusätzlich iiwa, Kinova, TM12, Jaco).
- **Community-Config existiert:** [Lab-CORO/curobo_doosan](https://github.com/Lab-CORO/curobo_doosan)
  (`src/m1013/m1013.yml`, geprüft) — v1-Format, URDF + Meshes + Kugeln.
  Aber: nur **13 Kugeln** für den ganzen Arm, Radien 65–164 mm
  (link1 = eine einzige 164-mm-Kugel), **keine Lizenzdatei** im Repo.
  Als Referenz nützlich, produktiv unbrauchbar für uns: Bei 50 mm
  Sicherheitsabstand im Nahbereich Wand↔Handgelenk wäre das genau die
  „chronisch falsch warnende dicke Hüllgeometrie", die ADR-024 verworfen
  hat. In der cuRobo-Discussion
  [#272](https://github.com/NVlabs/curobo/discussions/272) vom Maintainer
  freundlich zur Kenntnis genommen, nicht ins Repo übernommen.
- **Offizieller Doosan-Bezug existiert:** [DoosanRobotics/doosan-robot-isaac-driver](https://github.com/DoosanRobotics/doosan-robot-isaac-driver)
  (BSD-3-Clause, aber README-Disclaimer „research purposes … not for
  commercial use"; Isaac Sim + cuRobo → Echtzeitkommandos an Doosan-Arme;
  7 Commits, dünn). Beleg dafür, dass cuRobo+Doosan praktisch funktioniert,
  keine wiederverwendbare Config-Quelle.
- **Der realistische Weg (V2):** eigenes `m1013.yml` per `RobotBuilder`
  aus unserem **gevendorten URDF** (`third_party/doosan_m1013/`, ADR-024)
  bauen: `RobotBuilder("m1013.urdf", assets).fit_collision_spheres()` →
  `compute_collision_matrix()` → `build()`/`save()`; optional `save_xrdf()`
  (XRDF = NVIDIAs URDF-Erweiterung um Kugeln/Ignore-Matrix/Limits, auch von
  Isaac Sim/cuMotion konsumiert). Kugeldichte je Link nachsteuerbar
  (`refit_link_spheres("link6", sphere_density=3.0)`), Fit-Metriken
  (`prot_mm`/`gap_mm`) quantifizieren die Formtreue; `RobotDebugger`
  prüft die Retract-Pose auf Restkollisionen. **Aufwandsschätzung:
  0,5–2 Tage** inkl. Feinjustage der Handgelenk-Links — das eigentliche
  Risiko ist nicht der Bau, sondern ob die Kugel-Formtreue im
  Nahbereich reicht (Abschnitt 8/Risiken).

---

## 3 Wachsendes Werkstück: inkrementelle Welt-Updates (Frage 3)

Drei belegte Mechanismen, alle Quellcode-verifiziert:

1. **Mesh/Cuboid je Schicht anhängen:** `SceneData.add_obstacle(Mesh(...))`
   in vorreserviertem `mesh_cache`; Footprint-Prisma je Schicht (unser
   ADR-024-Rezept) ließe sich 1:1 abbilden; Deaktivieren/Ersetzen über
   `enable_obstacle`/`update_obstacle_pose` (namensbasiert; Fix der
   namensbasierten Routing-Bugs frisch in `main`, Changelog „Latest
   Commit"). Kostenprofil: Tensor-Slot-Befüllung, kein Neubau — aber
   **keine publizierte Update-Latenz**; muss der Spike messen.
2. **Voxel-/SDF-Gitter fortschreiben:** `SceneCollision.update_voxel_data
   (voxel_coords, features)` aktualisiert ein `VoxelGrid` in place — wir
   könnten unser eigenes (CPU-gebautes, deterministisches) Druckstand-SDF
   je Schicht hochladen. Das hält die **Wahrheit auf der CPU** und nutzt
   die GPU nur als Abfragebeschleuniger.
3. **In die TSDF stempeln:** `Mapper.update_static_obstacles(scene)`
   stempelt Cuboids/Meshes analytisch in einen separaten, nicht
   verfallenden Geometrie-Kanal (*„combined with the dynamic (depth)
   channel using min() for collision"*), danach `compute_esdf()` →
   `VoxelGrid`. Docstring-Warnung: *„not intended to be called every
   frame"* — der Stempel-Kanal wird je Aufruf **komplett neu** gestempelt.
   Für Schicht-Takt (alle paar Minuten) unkritisch, für Sample-Takt
   ungeeignet.

Fazit: „Druckstand wächst Schicht für Schicht" ist mit cuRoboV2 gut
abbildbar — am saubersten für uns über (2), weil dann dieselben
Druckstand-Daten CPU-Referenz und GPU-Backend speisen. Zusätzlich passt
`get_point_robot_distance` (Punkte↔Kugeln) direkt auf das
`DruckstandPunkte`-Konzept aus #183 — Schichtfortschritt = Punkte anhängen,
identisch zum CPU-Plan.

---

## 4 Determinismus & Reproduzierbarkeit (Frage 5)

Was die Primärquellen hergeben:

- **Dokumentiert (v1-Doku, [Performance-Tuning-Seite](https://curobo.org/notes/03_performance_tuning.html)):**
  *„Using a LBFGS history value less than 12 provides deterministic results
  in trajectory optimization"* (Tradeoff: langsamere Konvergenz). Gleiche
  Aussage im Changelog 0.7.x (*„Add note on deterministic behavior to
  website. Use lbfgs history < 12 for deterministic optimization
  results."*). Das betrifft die **Optimierer**, nicht die reine
  Distanzabfrage.
- **Repo-Praxis:** `curobo/tests/conftest.py` setzt Seeds + 
  `torch.backends.cudnn.deterministic = True` — die eigene Testsuite
  erwartet Run-zu-Run-Reproduzierbarkeit auf derselben Maschine.
- **Nicht gefunden:** irgendeine Zusage zu **Bit-Gleichheit über
  GPUs/Treiber/CUDA-Versionen hinweg**. Issue-Suche „deterministic":
  ein einziger, nicht einschlägiger Treffer (#415).
- **Einordnung (Inferenz, nicht curobo-spezifisch belegt):** Die reinen
  Kollisions-Kernel (Kugel↔Cuboid/Mesh/Voxel) sind feste
  Reduktionstopologien; Run-zu-Run-Stabilität auf identischer
  HW/SW-Konfiguration ist plausibel, **Bit-Gleichheit über verschiedene
  GPUs ist bei GPU-Gleitkomma grundsätzlich nicht zu erwarten** —
  Ablehnungsgrund (b) bleibt für Byte-Goldens sachlich richtig.

**Trägt (b) für unseren Anwendungsfall?** Differenziert:

- Für **Goldens/Paper-Benchmark nach ADR-004** (Byte-Vergleich der
  Artefakte): ja, (b) trägt. Ein cuRobo-Artefakt wäre je Rechner
  verschieden — als Golden-Referenz unbrauchbar.
- Für das **Urteil** („kollidiert / frei / Warnung" + Distanz mit
  50-mm-Sicherheitsband): nein, nicht zwingend. Ein Toleranzvergleich
  (Distanzen bis ε, Status-Gleichheit außerhalb eines Grenzbands um die
  Schwellen) ist wissenschaftlich sauber formulierbar. Bedingung: Der
  **CPU-Pfad bleibt die Referenz und die einzige Golden-Quelle**;
  GPU-Ergebnisse sind eigene Artefakte mit GPU-/Treiber-Provenienz und
  werden nur toleranzverglichen. ADR-004 selbst muss dafür nicht geändert
  werden — es braucht nur die Regel „GPU-Befunde sind nie Goldens"
  (analog zur bestehenden Surrogat-Regel „sortiert nur, urteilt nie").

Kontrast zur CPU-Seite bleibt bestehen: python-fcl ist bei uns nachweislich
bitgleich (Spike S0, `fgc/collision/check.py`-Docstring) — dieser Vorteil
ist real und bleibt der Grund, warum die Referenz CPU bleibt.

---

## 5 Tiefenkamera: v1-nvblox vs. V2-Mapper (Frage 4)

**Was Tobias gesehen hat, war fast sicher cuRobo v1:** Der v0.7.8-Baum
enthält `examples/isaac_sim/realsense_collision.py`, `realsense_mpc.py`,
`realsense_reacher.py`, `realsense_viewer.py`, `examples/nvblox_example.py`,
World-Configs `collision_nvblox*.yml` und die Klasse `WorldBloxCollision`
(`src/curobo/geom/sdf/world_blox.py`). Diese Schiene hängt an
`nvblox`/`nvblox_torch`, die v1-Doku empfiehlt dafür Docker und warnt vor
dem PyTorch-C++-ABI-Problem (`D_GLIBCXX_USE_CXX11_ABI=0`,
[v1-Install-Seite](https://curobo.org/get_started/1_install_instructions.html)).
nvblox selbst: Apache-2.0 (+ BSD-3 für voxblox-Anteile,
[LICENSE](https://github.com/nvidia-isaac/nvblox/blob/public/LICENSE.md)),
weiter aktiv (v0.0.10 im Mai 2026), Linux/Jetson-orientiert.

**In cuRoboV2 ist das ersetzt** durch das eigene Mapper-Subsystem
(`curobo/_src/perception/mapper/`, `curobo.perception`):

- **Pipeline:** `CameraObservation(depth_image, intrinsics, pose)` →
  `Mapper.integrate(...)` (block-sparses TSDF, lock-freie voxelzentrische
  Kernel) → `Mapper.compute_esdf()` (exakter Euklid-Distanztransform via
  **Parallel Banding Algorithm**, alternativ Jump Flooding;
  `MapperCfg.edt_solver`) → **`VoxelGrid`, das direkt als Kollisionswelt
  dient** (Changelog 0.8.0: *„The resulting VoxelGrid can be passed
  directly to motion planning for voxel-based collision checking"*).
- **Zusatzfähigkeiten (Quellcode/Changelog):** `RobotSegmenter` (den
  eigenen Arm aus dem Tiefenbild maskieren), `FilterDepth`,
  Multi-Kamera-Fusion, **LiDAR-Integration** (neu, `LidarObservation`),
  Decay für dynamische Szenen, `save_blocks()`/`load_blocks()`-Checkpoints,
  Mesh-Extraktion (Marching Cubes) und `PoseDetector`/`SDFPoseDetector`
  (Punktwolke↔Modell-Registrierung — interessant fürs **Einmessen**, #116).
- **RealSense konkret:** Referenzbeispiel
  `curobo/examples/reference/live_volumetric_mapping_mpc.py` —
  *„live RGB-D TSDF/ESDF mapping reference example with Franka MPC using a
  RealSense backend"* (Changelog). Tutorial mit Sun3D-RGB-D-Datensatz:
  `curobo/examples/getting_started/volumetric_mapping.py`.
- **Reifegrad:** sehr junge, aber sehr aktiv entwickelte Codebasis
  (Mapper-Featureschübe in fast jedem Commit-Block seit April 2026;
  V2-Paper beansprucht *„up to 10× faster and in 8× less memory than the
  state-of-the-art at manipulation scale, with up to 99% collision
  recall"* — man beachte: **99 % Recall heißt 1 % übersehene Kollisionen**,
  eine Näherung, kein Beweisinstrument).
- **Plattform:** V2-Installationsdoku nennt **nur Ubuntu ≥ 20.04, NVIDIA-GPU
  > Turing, ≥ 4 GB VRAM, Treiber ≥ 580.65.06, Python ≥ 3.10 (> 3.13 nicht
  validiert), CUDA 12/13** (`docs/getting-started/installation.rst`).
  **Windows kommt in der V2-Doku nicht vor.** v1 hatte „experimental
  support for Windows" (curobo.org; Changelog „Add partial support for
  Windows") — aber v1 ist die non-kommerzielle Lizenz. WSL2 wird in keiner
  der beiden Dokus explizit behandelt (CUDA-on-WSL2 ist generell gangbar —
  unverifizierte Inferenz, wäre Spike-Gegenstand). Für die
  Baustellen-Realität ist ohnehin eher ein Jetson/Linux-Kistchen neben der
  Kamera plausibel als der Windows-Planungsrechner.

**Der Weg für uns wäre:** RealSense/Tiefenkamera → `CameraObservation` →
`Mapper` → ESDF-`VoxelGrid` = **Ist-Zustand** der Zelle/des Druckstands →
(a) Kollisionswelt für Prüfungen gegen die Realität statt des Plans,
(b) Ist-vs-Soll-Vergleich (gedruckte Geometrie gegen Slicer-Soll). Das ist
ein **eigenes Standbein** mit eigener Hardware-Voraussetzung und muss die
Plan-Prüf-Tür nicht anfassen.

---

## 6 Anforderungen & Lizenz — Zusammenfassung (Frage 6)

| Punkt | cuRobo v0.7.8 (v1) | cuRobo ≥ 0.8.0 (V2, aktuell) |
|---|---|---|
| Lizenz | **NVIDIA License, nur nicht-kommerziell** („research or evaluation purposes only"; Redistribution nur unter derselben Lizenz) | **Apache-2.0** (Assets separat, `LICENSE_ASSETS`) |
| Plattform lt. Doku | Ubuntu 20.04/22.04, „experimental support for Windows", Jetson (Docker) | **nur Ubuntu ≥ 20.04 dokumentiert**; Windows unerwähnt |
| GPU | „VOLTA or newer", ≥ 4 GB VRAM | „> Turing", ≥ 4 GB VRAM, Treiber ≥ 580.65.06 |
| Python | 3.8–3.10 | ≥ 3.10, „> 3.13 is not validated" |
| PyTorch/CUDA | PyTorch ≥ 1.15, CUDA 11.8 (Isaac-Sim-Pfad) | torch ≥ 2.5 (cu12) / ≥ 2.9 (cu13), CUDA 12/13 über `cuda-core`; Kernel-Laufzeitkompilierung |
| Tiefenkamera | nvblox/`nvblox_torch` (Apache-2.0), Docker empfohlen, ABI-Falle | eingebauter Mapper, RealSense-/LiDAR-Beispiele |

Für ein Paper mit Ziel Automation in Construction ist die Apache-2.0-Lage
unproblematisch (auch spätere kommerzielle Verwertung des Tools bliebe
frei). Achtung nur bei Fremd-Configs: Lab-CORO-Repo **ohne Lizenz**,
Doosan-Driver BSD-3 mit Forschungs-Disclaimer — eigene Kugel-Configs aus
unserem gevendorten URDF bauen, nicht kopieren.

**Friktion für unser Repo konkret:** Unser Core läuft auf Python 3.14
(Spike S0); cuRoboV2 ist bis 3.13 nicht einmal validiert. Ein
cuRobo-Backend liefe also realistisch in einer **separaten venv/Umgebung
oder auf einem Linux-Rechner** und spräche mit der Pipeline über
Artefakte/CLI — was ADR-004 (dateibasierte Pipeline) ohnehin nahelegt.

---

## 7 Performance-Einordnung (Frage 7)

**Publizierte Zahlen (Herstellerangaben, nicht nachgemessen):**

- v1-Paper ([2310.17274](https://arxiv.org/abs/2310.17274)): Motion
  Generation im Schnitt 50 ms (60× schneller als Stand der Technik),
  Geometrieplanung 20 ms, **> 7 000 kollisionsgeprüfte IK-Abfragen/s**;
  Referenz-HW „massively parallel GPUs" (die 30-ms/RTX-4090-Zahl der
  Vorgänger-Recherche stammt von der v1-Website).
- V2-Paper ([2603.05493](https://arxiv.org/abs/2603.05493), HTML-Extraktion):
  Experimente auf **RTX 4090**; Planungszeit Franka 35 ms (42 ms mit
  Dynamik); ESDF „up to 10× faster and in 8× less memory than the
  state-of-the-art" (Vergleichsgröße implizit nvblox), „up to 99% collision
  recall"; 61×-Speedup bezieht sich auf **Whole-Body-Kinematik bei
  High-DoF-Humanoiden**, nicht auf Manipulator-Kollisionschecks.
- V2-Doku ([benchmarks.rst](https://github.com/NVlabs/curobo/blob/main/docs/reference/benchmarks.rst),
  RTX 6000 Ada): IK-Batch 100 Posen: Franka 2,6 ms, kollisionsfrei 2,7 ms;
  dual-UR10e 6,1/15,6 ms. Für reine Kollisions-/Gradientenkosten liefert
  `benchmark/cost_gradient_benchmark.py` Zeiten je Roboter — Zahlen stehen
  nicht in der Doku, das Skript ist da (selbst laufen lassen).

**Übertragung auf unseren Fall (Schätzung, klar als solche markiert):**
Unsere Prüf-Tür-Last ist „25 217 Samples × (6-DOF-FK + Distanz gegen
Druckstand + Selbstkollision)". In cuRobo ist das **ein** Aufruf
`get_scene_self_collision_distance_from_joints(q)` mit
`q.shape == [25217, 1, 6]` und (bei feiner M1013-Config) ~60–150 Kugeln —
also ~2–4 M Kugel-Primitive-Abfragen, was nach den IK-Benchmarks (ein
IK-Solve macht intern hunderte solcher Auswertungen in Millisekunden)
im Bereich **deutlich unter einer Sekunde** liegen sollte, gegenüber heute
30–44 s FCL (Spike S0) bzw. der 10-s-Zielmarke (#144). **Aber:** Es gibt
keine publizierte Zahl für exakt diese Abfrageform; VRAM, Welt-Update-Takt
und die Kugel-Formtreue-Frage kann nur ein eigener Spike klären. Die
RTX-4090-/RTX-6000-Referenzen sind High-End; auf einer Mittelklasse-GPU
schrumpfen die Faktoren, kippen aber nicht das Vorzeichen.

---

## 8 Die drei Ablehnungsgründe nach der Recherche + Einsatzmuster (Frage 8)

**(a) CUDA-/NVIDIA-Zwang vs. „reproduzierbar auf jedem PC" — bleibt
richtig, verliert aber an Schärfe als Totalausschluss.** cuRoboV2 ist und
bleibt CUDA-only (GPU > Turing, Linux-Doku). Als **Ersatz** des CPU-Pfads
scheidet es damit weiterhin aus. Als **optionales Extra** (eigene
Umgebung, Feature-Detection, sauberer Degradationspfad „kein NVIDIA →
CPU-Pfad, keine Funktionseinbuße im Urteil") verletzt es das Versprechen
nicht — dasselbe Muster fahren wir mit `core[geo]` schon heute
(Lazy-Import + freundlicher Fehlpfad, `fgc/collision/check.py`).

**(b) GPU-Gleitkomma vs. Byte-Gleichheit — bestätigt, aber präzisiert.**
Keine Quelle verspricht Cross-Hardware-Bitgleichheit; dokumentiert ist nur
Optimierer-Determinismus unter Bedingungen (LBFGS-History < 12).
Konsequenz nicht „unbenutzbar", sondern: **CPU bleibt Golden-Referenz,
cuRobo-Ausgaben sind eigene Artefakte mit GPU-Provenienz und werden
toleranzverglichen** (Status-Gleichheit + Distanz-ε). ADR-004 bleibt
unangetastet; der Paper-Benchmark läuft weiter über den CPU-Pfad.

**(c) Engpass bereits adressiert — bestätigt, und der Trigger bleibt.**
Die Glied-SDF-Inversion trifft den gemessenen 53-%-`set_transform`-Posten
direkt, läuft auf jedem PC, ist bitgleich und liefert den
Advisor-Gradienten. Nichts in dieser Recherche spricht dafür, sie durch
cuRobo zu ersetzen. **Neu ist:** (c) war nie ein Argument gegen die
*anderen* Einsatzmuster — Durchsatz für die Datenkampagne (#183, Batch
über Nacht) und das Tiefenkamera-Standbein wurden am 2026-07-12 gar nicht
bewertet. Dort konkurriert cuRobo nicht mit der Glied-SDF, sondern ergänzt
sie.

**Bewertung der drei Muster aus dem Auftrag:**

- **(i) Zweit-Backend hinter derselben Prüf-Tür-Naht:** passt
  architektonisch perfekt — `check_representative` ist als injizierbares
  Orakel genau dafür gebaut (`fgc/decompose/pruefung.py`), und PRD #183
  fordert ohnehin den Backend-Umschalter mit Regressionsanker „identische
  Befunde". Einschränkung: Das cuRobo-Urteil ist Kugel-genähert; „identische
  Befunde" ist nur im Toleranz-/Grenzband-Sinn erreichbar. Als **Befund,
  kein Gate** (ADR-013-Sprachgebrauch) und nie als Golden: tragfähig.
- **(ii) Grob-Vorsortierer vor der exakten CPU-Prüfung:** das stärkste
  Muster. Geometrisch statt gelernt, konservativ auslegbar: Kandidaten mit
  `min_distance > Sicherheitsabstand + Kugel-Formtreue-Band (prot_mm/gap_mm
  aus dem Builder) + ε` gelten als „vermutlich frei", alles andere geht in
  die exakte Prüfung. Identische Ehrlichkeitssemantik wie der geplante
  Surrogat-Vorsortierer („sortiert/filtert Kandidaten, urteilt nie") —
  nur ohne Trainingsbedarf. Besonders wertvoll für die **Datenkampagne**
  und die Beam-Suche (viele Kandidaten × viele Posen).
- **(iii) Tiefenkamera/nvblox-Standbein:** einziges Muster **ohne
  CPU-Alternative im Projektplan** — für „Ist-Zustand der Baustelle gegen
  Plan" gibt es bei uns nichts Vergleichbares, und cuRoboV2 bringt die
  komplette Kette (Segmentierung, TSDF, ESDF, Pose-Registrierung) mit.
  Eigene Hardware-Voraussetzung (Linux/Jetson + NVIDIA-GPU + Kamera),
  eigener Spike, koppelbar an #116 (Einmessen).

---

## Teil 2 — Implementierungsplan: cuRobo als optionales Backend

Leitplanken (aus den Bedingungen oben): CPU/FCL bzw. künftig Glied-SDF
bleibt Referenz und einzige Golden-Quelle; cuRobo ist ein **optionales
Extra mit eigener Umgebung**, das ohne NVIDIA-GPU sauber degradiert; alle
Andockpunkte sind bestehende Nähte (`check_representative`-Orakel,
Hindernis-Provider-Vertrag, Backend-Umschalter aus #183); Tiefenkamera ist
eine eigene spätere Phase.

### Phase G0 — Reihenfolge festhalten (kein Code)

- **Entscheidungsempfehlung:** Den Revisionstrigger **nicht überholen**.
  Glied-SDF (#183 Paket 1) zuerst bauen und messen — sie ist
  komplementär, nicht konkurrent (CPU-Referenz, bitgleich, Selbstkollision,
  Advisor-Gradient), und die Messung liefert die Basiszahl, gegen die ein
  GPU-Backend überhaupt erst ehrlich bewertbar ist.
- **Eine Ausnahme rechtfertigt Vorziehen von G1:** wenn die
  **Datenkampagne** (#183) früher Durchsatz braucht als die Glied-SDF
  liefert, oder wenn die **Tiefenkamera-Beschaffung** ansteht und G4
  vorbereitet werden soll.
- Gate: #183-Messung (FCL vs. Glied-SDF, je Aufrufort) liegt vor **oder**
  Ausnahme-Beschluss in einer Grill-Session.

### Phase G1 — Spike „cuRobo-Machbarkeit M1013" (isoliert, wegwerfbar)

- **Ziel:** Drei Zahlen und ein Urteil: (1) Laufzeit der
  25 217-Sample-Foto-Bahn (`get_scene_self_collision_distance_from_joints`,
  Welt = Druckstand-Mesh + Boden), (2) Welt-Update-Kosten je Schicht,
  (3) Befund-Abweichung gegen die FCL-Goldens (Status je Sample,
  Distanz-Differenzen, getrennt Arm↔Welt / Selbstkollision) — daraus die
  Kugel-Formtreue-Frage beantworten: Wie breit muss das Grenzband sein,
  damit kein FCL-Rot als cuRobo-Grün durchrutscht, und wie viel Gelb-Spam
  erzeugt der Kugel-Überstand im Nahbereich?
- **Vorgehen:** `RobotBuilder` auf unser gevendortes M1013-URDF
  (Kugeldichte hoch, Fit-Metriken protokollieren; Lab-CORO-Config nur als
  Plausibilitäts-Referenz); Bahn + Druckstand aus vorhandenen
  ADR-004-Artefakten laden (JSON rein, JSON raus — kein Import von `fgc`
  in der cuRobo-venv nötig).
- **Voraussetzungen:** Rechner mit NVIDIA-GPU; Ubuntu oder WSL2-Versuch
  (WSL2-Tauglichkeit ist selbst ein Spike-Ergebnis); eigene venv
  (Python 3.11/3.12, `uv pip install .[cu12-torch]`).
- **Aufwand:** 2–4 Tage inkl. Umgebungsgefrickel.
- **Gate:** Speedup ≥ 10× gegenüber FCL-Referenz **und** ein Grenzband
  existiert, in dem gilt: kein einziges FCL-Rot wird außerhalb des Bandes
  grün. Scheitert das Band (Kugeln zu grob trotz hoher Dichte), endet
  cuRobo hier als Prüf-Tür-Kandidat — Muster (iii) bleibt davon unberührt.
- **Risiken:** WSL2/Treiber-Reibung; VRAM bei feiner Kugel-Config ×
  25k-Batch; Mesh-`max_distance`-Kappe (Distanzen jenseits ~0,1 m werden
  gekappt — für unser 50-mm-Band okay, für Advisor-Weitsicht nicht).

### Phase G2 — optionales Backend hinter der Naht (`core[gpu]` o. ä.)

- **Ziel:** cuRobo als zweite Implementierung hinter dem
  Hindernis-Provider-/Prüf-Tür-Seam, per Konfiguration schaltbar
  (dieselbe Stelle, an der #183 US 14 den FCL↔SDF-Schalter fordert):
  produktiv eine Closure wie `check_representative`, die statt
  `sectionsim.clearance_verdict` einen cuRobo-Lauf (Subprozess/CLI gegen
  die separate venv, Artefakt-in/Artefakt-out nach ADR-004) anstößt.
- **Ehrlichkeit/Artefakte:** Befunde tragen
  `collision_backend: curobo-<version>` + GPU-/Treiber-Provenienz;
  Ampel-Semantik unverändert („geprüft frei" nur aus der exakten Prüf-Tür —
  cuRobo-Grün außerhalb des Grenzbands darf als eigener Befundtyp
  erscheinen, z. B. `presumed_free_gpu`, nie als `geprüft`); **Goldens
  bleiben CPU**; Regressionsanker: Denkmal-Suite mit umgeschaltetem
  Backend → identische Status-Urteile im Toleranzschema.
- **Degradation:** Feature-Detection (GPU + venv vorhanden?) mit klarer
  Fehlermeldung nach dem `GEO_HINT`-Muster; ohne GPU existiert der
  Schalter schlicht nicht.
- **Aufwand:** 1–2 Wochen. **Gate:** Regressionsanker grün; ein
  dokumentierter Lauf auf einem GPU-Rechner + ein Lauf ohne GPU
  (Degradationspfad) im selben Repo-Stand.
- **Risiken:** Zwei-Umgebungen-Wartung; Versionsdrift cuRobo `main`
  (API noch in Bewegung — Pin auf Release-Tag).

### Phase G3 — Durchsatz-Nutzer: Datenkampagne + Beam-Vorsortierung

- **Ziel:** Muster (ii) produktiv: die Datenkampagne etikettiert
  GPU-vorsortiert (exakte Prüf-Tür nur fürs Grenzband + Stichproben-Audit
  aller „vermutlich frei"), die Beam-Suche bekommt einen geometrischen
  Vorsortierer neben dem gelernten. Semantik identisch zum
  Surrogat-Vertrag aus #183: **sortiert/priorisiert, verwirft nie ohne
  exaktes Urteil** — bzw. verwirft nur mit dem in G1 kalibrierten
  konservativen Band, und das wird im Datensatz-Artefakt ausgewiesen.
- **Voraussetzungen:** G1+G2; #183-Beam-Grill gelaufen.
- **Aufwand:** Tage (die Naht existiert dann schon).
- **Gate:** Invarianz-Orakel wie beim Surrogat: gleiche Urteile und
  gleicher bester Kandidat mit/ohne GPU-Vorsortierung.

### Phase G4 — Tiefenkamera-Standbein (eigener Spike, eigene Hardware)

- **Ziel:** RealSense (o. ä.) → `Mapper` → ESDF-`VoxelGrid` als
  **Ist-Zustand**: (a) Ist-vs-Soll des Druckstands (gedruckte Schicht
  gegen Slicer-Soll), (b) perspektivisch Kollisionswelt „Realität statt
  Plan", (c) Kopplung an #116/Einmessen via `PoseDetector`
  (Punktwolke↔Modell-Registrierung).
- **Voraussetzungen:** Linux-Rechner oder Jetson mit NVIDIA-GPU an der
  Zelle; Kamera; unabhängig von G2/G3 startbar (das Standbein lohnt auch,
  wenn die Prüf-Tür für immer CPU bleibt).
- **Aufwand:** 1–2 Wochen Spike (Sun3D-Tutorial nachfahren → eigene
  Kamera → ein Druckstand-Scan mit Ist-Soll-Differenzbild als Artefakt).
- **Gate (Grill-Session):** Differenzbild eines echten (oder simulierten)
  Druckstands mit dokumentierter Auflösung/Latenz; Entscheidung, ob das
  ein Paper-2/3-Strang wird.
- **Risiken:** junger Code (Mapper-API bewegt sich schnell), Linux-only,
  99-%-Recall-Charakter der Voxelisierung (nie als alleiniges
  Sicherheitsurteil verwenden).

### Verhältnis zum Glied-SDF-Paket aus #183 (explizit)

**Ergänzung, nicht Konkurrenz; Reihenfolge unverändert.** Die Glied-SDF
bleibt Arbeitspaket 1 und der Weg zur 10-s-Marke auf jedem PC; der
Revisionstrigger („CPU verfehlt die Marke → GPU-Backend neu bewerten")
bleibt formal bestehen, und diese Recherche ist die vorgezogene
Bewertungsgrundlage für den Fall, dass er auslöst: dann ist cuRoboV2
(Apache-2.0, `RobotCollisionChecker`) der designierte Kandidat, und G1/G2
sind der Plan. Unabhängig vom Trigger dürfen G1 (klein) und G4
(Tiefenkamera) aus eigenem Recht starten — sie beschleunigen nicht die
Prüf-Tür, sondern erschließen Durchsatz (Datenkampagne) und Realitätsbezug
(Baustelle), die der CPU-Plan gar nicht adressiert.

---

## Quellenverzeichnis (Kern)

- Repo: <https://github.com/NVlabs/curobo> (main, Push-Stand 2026-07-10) · [Releases](https://github.com/NVlabs/curobo/releases) · [LICENSE@main](https://github.com/NVlabs/curobo/blob/main/LICENSE) · [LICENSE@v0.7.8](https://github.com/NVlabs/curobo/blob/v0.7.8/LICENSE) · [CHANGELOG.md](https://github.com/NVlabs/curobo/blob/main/CHANGELOG.md)
- V2-Doku (aus Repo `docs/`): [installation.rst](https://github.com/NVlabs/curobo/blob/main/docs/getting-started/installation.rst) · [benchmarks.rst](https://github.com/NVlabs/curobo/blob/main/docs/reference/benchmarks.rst) · Site: <https://nvlabs.github.io/curobo>
- v1-Doku (weiter online): <https://curobo.org/> · [Install](https://curobo.org/get_started/1_install_instructions.html) · [Performance Tuning/Determinismus](https://curobo.org/notes/03_performance_tuning.html)
- Quellcode-Belege (Pfade im Repo, main): `curobo/collision_checking.py`, `curobo/_src/collision/collision_robot_scene.py`, `curobo/_src/geom/collision/collision_scene.py`, `curobo/_src/geom/collision/checker_collision.py`, `curobo/scene.py`, `curobo/perception.py`, `curobo/_src/perception/mapper/{mapper.py,mapper_cfg.py}`, `curobo/robot_builder.py`, `curobo/sphere_fit.py`, `curobo/examples/getting_started/{volumetric_mapping.py,build_robot_model.py}`, `curobo/examples/reference/live_volumetric_mapping_mpc.py`, `pyproject.toml`, `curobo/tests/conftest.py`; v0.7.8: `src/curobo/wrap/model/robot_world.py`, `src/curobo/geom/sdf/world_blox.py`, `examples/isaac_sim/realsense_*.py`
- Paper: [arXiv 2310.17274](https://arxiv.org/abs/2310.17274) (v1) · [arXiv 2603.05493](https://arxiv.org/abs/2603.05493) (V2)
- nvblox: <https://github.com/nvidia-isaac/nvblox> ([LICENSE.md](https://github.com/nvidia-isaac/nvblox/blob/public/LICENSE.md): Apache-2.0 + BSD-3-voxblox)
- Doosan: [Discussion #272](https://github.com/NVlabs/curobo/discussions/272) · [Lab-CORO/curobo_doosan](https://github.com/Lab-CORO/curobo_doosan) · [DoosanRobotics/doosan-robot-isaac-driver](https://github.com/DoosanRobotics/doosan-robot-isaac-driver)

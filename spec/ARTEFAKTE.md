# ARTEFAKTE — Präzisierung von SPEC §6 und der Prüf-Schnittstellen

Stand 2026-10-18, vom Orchestrator vor `spec/LOCKED` festgelegt. Ergänzt SPEC §6, §5.1 und §11
um die Namen und Semantik, die dort offen sind. Bei Widerspruch gilt SPEC.md.
Orakel (`verify/`) und System (`core/`) halten sich beide an diese Datei.

## Allgemein

- Alle JSON-Dateien tragen `"schema_version": "2"`.
- Homogene Transformationen: 4×4 als verschachtelte Liste, zeilenweise, Translation in mm.
- Posen als Liste `[x, y, z, qw, qx, qy, qz]` (mm, Quaternion w-zuerst).
- Pfade in `scene.json` sind relativ zur Repo-Wurzel.
- Gliednamen: `base_link`, `link_1` … `link_6`, `tool_body`, `nozzle_tip`.
  Hindernisnamen: `floor`, `table`, `printed`; bei Selbstkollision der Name des anderen Glieds.

## Schichten, TCP-Höhe und Druckstand

- Schichten sind ab 0 nummeriert. Schicht L belegt z_P ∈ [L·h, (L+1)·h].
- Beim Druck von Schicht L liegt der TCP (Düsenspitze) auf z_P = (L+1)·h.
- `layer[i]` in `trajectory.json` ist **die Anzahl k der fertigen Schichten**, die für Sample i als
  Druckstand gilt: Hindernis = Teil-Solid ∩ {z_P ≤ k·h}.
  - Samples der Arten `print`, `approach`, `retract` eines Rings in Schicht L: k = L.
  - Samples der Art `link` (Verbinder, SPEC §5.3) vor einem Ring in Schicht L: k = L, also die
    Schicht des **folgenden** Rings. Beim Schichtwechsel ist die eben gedruckte Schicht damit fertig.
  - Samples der Arten `lift`, `transfer`, `lower` nach einem Ring in Schicht L: k = L + 1
    (SPEC §5.1: bei Travel zählt die eben gedruckte Schicht als fertig).
  - Travel vor dem ersten Ring (aus der Home-Pose): k = 0.
- `ring[i]`: Index in `toolpath.rings`. `approach`/`print`/`retract` → eigener Ring;
  `link` → der folgende Ring; `lift` → der eben gedruckte Ring; `transfer`/`lower` → der folgende
  Ring. Vor dem ersten Ring 0.
- **Strang** (Nutzerentscheidung 20.10.2026, SPEC §5.3): Ablauf je Strang aus den Ringen r … s:
  `transfer` (`movej`) → `lower` (senkrecht, `movel`, endet `approach_mm` über dem Ringstart) →
  `approach` (`approach_mm` senkrecht) → `print` r → `link` r + 1 → `print` r + 1 → … → `link` s →
  `print` s → `retract` (`approach_mm` senkrecht) → `lift` (senkrecht, `movel`). Ein Strang aus einem
  Ring ist der Fall r = s. Der erste Strang beginnt mit `transfer` aus der Home-Pose.
- Jeder Ring hat genau einen zusammenhängenden `print`-Abschnitt. Direkt davor steht `approach`
  desselben Rings (Strangbeginn) oder `link` desselben Rings (Ring r + 1 im Strang). Direkt danach
  steht `retract` desselben Rings (Strangende) oder `link` des Rings mit dem nächsthöheren Index.
- `link` von Ring r nach Ring r + 1 ist nur erlaubt, wenn `toolpath.rings[r].link_next = true`.
  Die `link`-Samples liegen auf der Geraden vom letzten Wegpunkt von r zum ersten Wegpunkt von r + 1
  und beginnen bzw. enden an diesen Punkten.
- Die Pumpe läuft in `print` und `link`, sonst nicht. Der Roboter hält im Strang nicht an.

## Kollisions-Schnittstelle (für G2)

```python
from roboprint.collision import World
world = World(part_mesh_P: trimesh.Trimesh, T_WP: np.ndarray, layer_height_mm: float = 10.0,
              root: Path = <Repo-Wurzel>)
c = world.distance(q: np.ndarray, layer: int)   # layer = k fertige Schichten (s. o.)
c.d_mm: float            # vorzeichenbehaftet, < 0 bei Durchdringung
c.pair: tuple[str, str]  # (Glied, Hindernis)
c.witness_W: tuple[np.ndarray, np.ndarray]  # Zeugenpunkte in W, mm
```
Roboter, Werkzeug und Workstation lädt `World` aus den Default-Assets
(`third_party/doosan_m1013/urdf/m1013.white.urdf`, `tools/30gut.json`, `workstations/doosantisch.json`).

## Kinematik-Schnittstelle (für G1)

```python
from roboprint.robot import fk, ik, JOINT_LIMITS
fk(q) -> np.ndarray          # 4×4 T_BF in mm, q in rad, Doosan-Konvention
ik(T_BF) -> list[tuple[int, np.ndarray]]   # (Zweig 0–7, q); nur Lösungen in den Grenzen
JOINT_LIMITS: np.ndarray     # 6×2 in rad
```
`ik` liefert je Zweig alle Lösungen innerhalb der Grenzen, auch die um ±2π verschobenen
Varianten der Gelenke mit ±360°-Grenze sind zulässig, aber nicht Pflicht. Zweig-Bits
(Annahme **A**, nach der `sol_space`-Tabelle des Doosan-Manuals): Bit 2 (Wert 4) = Schulter
Righty, Bit 1 (Wert 2) = Ellbogen Above, Bit 0 (Wert 1) = Handgelenk Flip. 0 = Lefty/Below/NoFlip,
7 = Righty/Above/Flip. Die geometrische Definition steht im Docstring von `roboprint.robot`.

## Dateien im Laufordner

### summary.json
```
schema_version, scenario_id, scenario_path, params {…alle Werte aus SPEC §10, Schlüssel in
snake_case mit Einheit, z. B. layer_height_mm, bead_width_mm, d_hard_mm, d_target_mm, d_target_printed_mm, r_free_mm},
assumptions [Text…], walls [{wall_id, name, eligible, reason|null, length_mm, thickness_mm,
height_mm, volume_mm3, part_ids[]}], parts [{part_id, wall_id, status, d_min_mm|null,
n_collision, n_unreachable}], timings_s {stage: Sekunden}, provenance {git_commit, created,
command}
```
`status` ∈ {`machbar`, `nicht machbar`}. Bei `source.kind = box` gibt es genau eine Wand `box`.

### scene.json
```
schema_version, robot {urdf}, workstation {mesh, T_WB, T_WS},
tool {mesh, T_FT, mesh_transform}, params {d_hard_mm, d_target_mm, d_target_printed_mm, r_free_mm, layer_height_mm}
```
`mesh_transform` ist die 4×4-Pose des Werkzeugmeshes im Flansch-Frame F (Mesh in mm).

### parts/<part_id>/part.json
```
schema_version, part_id, wall_id, T_LP, T_SP, T_WP,
placement {x_mm, y_mm, yaw_deg}, bbox_P {min [3], max [3]}, volume_mm3,
n_layers, status, cause|null {sample, t_s, link, obstacle, message}
```

### parts/<part_id>/toolpath.json
```
schema_version, part_id, layer_height_mm, bead_width_mm,
rings [{layer, shell, kind, closed, link_next, waypoints [[x,y,z,qw,qx,qy,qz], …]}]
```
Wegpunkte in W. `kind` ∈ {`outer`, `inner`, `hole`}. Bei `closed = true` wiederholt der letzte
Wegpunkt den ersten. Die Düsenachse +Z_T zeigt nach −Z_W. `link_next` (bool, Default `false`):
Der Slicer erlaubt einen Verbinder zum Ring mit dem nächsthöheren Index (Bedingungen SPEC §5.3).
Ob der Planer ihn nutzt, zeigt die Trajektorie.

### parts/<part_id>/trajectory.json
Genau die Arrays aus SPEC §6 (`t_s`, `q`, `tcp`, `layer`, `ring`, `kind`, `branch`, `status`,
`d_mm`, `pair`, `witness`) plus `schema_version`, `part_id`, `psi_rad[N]` (Gierwinkel ψ je Sample)
und `summary {n, n_ok, n_warn, n_collision, n_unreachable, d_min_mm, dauer_s,
zweig_wechsel_in_ringen}`. Bei `unreachable` sind `d_mm`, `pair` und `witness` null; `q` trägt dann
die letzte gültige Lösung nur zur Anzeige und wird nicht geprüft. `zweig_wechsel_in_ringen` zählt
Zweigwechsel zwischen aufeinanderfolgenden erreichbaren Samples innerhalb eines Strangs
(`approach`, `print`, `link`, `retract` ohne Travel dazwischen); der Name bleibt aus Kompatibilität.

Nachtrag 19.10.2026 (Nutzerentscheidung): `status`, `d_mm`, `pair`, `witness` und `summary.d_min_mm`
beziehen sich auf d_status nach SPEC §2: Minimum über alle Paare außer den Gliedpaaren mit genau einem
Gelenk dazwischen ((`base_link`, `link_2`), (`link_1`, `link_3`), (`link_2`, `link_4`), (`link_3`,
`link_5`), (`link_4`, `link_6`)); diese Paare nur, wenn ihr Abstand < d_hard ist (Nutzerentscheidung
Tobias, 19.10.2026: „Nebeneinanderliegende Achsen können wir gerne rausnehmen, da sie ja eigentlich
nicht kollidieren können.“). Die Paarreihenfolge im Artefakt ist beliebig (`["link_2", "base_link"]`
oder umgekehrt). `World.distance` liefert d_status ebenfalls.

Sollabstand Druckstand (Nutzerentscheidung Tobias, 19.10.2026, „ja stimme zu“): `warn` gilt, wenn ein
zählendes Paar unter seinem Sollabstand liegt, gegen `printed` unter `d_target_printed_mm` (20 mm),
sonst unter `d_target_mm` (50 mm); `collision` bei d < 0. `d_mm` ist das Minimum über die zählenden
Paare, der Status daher nicht allein aus `d_mm` ablesbar. `d_target_printed_mm` steht in
`scene.json params`, `summary.json params` und `scenario.params`.

### DRL
`program.v2.drl`, `program.v3.drl`. Gelenkziele stehen als `posj(...)`, kartesische Ziele als
`posx(...)` mit `ref=DR_BASE`. Die Posen sind T_BT (Basis B, TCP), also nicht in W.

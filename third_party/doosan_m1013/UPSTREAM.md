# Doosan M1013 — vendorte Originale

Quelle der Wahrheit für das M1013-Modell (URDF + Meshes), aus der die
Viewer-GLBs (`viewer/public/robots/m1013/`) abgeleitet werden und aus der später
auch der Core seine **Kollisionsgeometrie** zieht. Kollision/Simulation nutzen
**nie** die Viewer-GLBs (Draco/Quantisierung wäre als Numerik-Input tabu) —
immer die `<collision>`-Meshes von hier.

## Bezugsquelle

- **Repo:** https://github.com/doosan-robotics/doosan-robot2
- **Commit (gepinnt):** `ec9242546ec6202835900dbcd8498e2daabfa6a6`
- **Lizenz:** BSD-3-Clause © 2024 Doosan Robotics Inc. — vollständig in `LICENSE`.

## Inhalt

| Pfad | Upstream-Herkunft |
| --- | --- |
| `urdf/m1013.white.urdf` | `dsr_description2/urdf/m1013.white.urdf` (referenziert visual **und** collision) |
| `meshes/m1013_white/*.dae` | `dsr_description2/meshes/m1013_white/` — Visual-Meshes (10 DAE) |
| `meshes/m1013_collision/*.dae` | `dsr_description2/meshes/m1013_collision/` — Collision-Meshes (10 DAE) |
| `LICENSE` | Repo-Wurzel `LICENSE` |

Die DAE tragen ihre Koordinaten in Millimeter; das URDF skaliert sie per
`<mesh scale="0.001">` nach Meter (URDF-Weltmaß).

## Reproduzieren

```sh
git clone --filter=blob:none --sparse https://github.com/doosan-robotics/doosan-robot2.git
cd doosan-robot2
git checkout ec9242546ec6202835900dbcd8498e2daabfa6a6
git sparse-checkout set dsr_description2/urdf dsr_description2/meshes/m1013_white dsr_description2/meshes/m1013_collision
# dann urdf/m1013.white.urdf, meshes/m1013_white, meshes/m1013_collision und LICENSE hierher kopieren
```

## Ableitung der Viewer-GLBs

`core/scripts/convert_robot_meshes.py` (trimesh, DAE via pycollada) erzeugt aus
diesen Originalen deterministisch ein GLB je Glied plus `manifest.json`. Siehe
Design-Log 2026-07-05 „M1013-Meshes".

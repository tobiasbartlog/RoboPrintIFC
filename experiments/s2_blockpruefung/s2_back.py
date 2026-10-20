"""check_run auf S2 in Teilmengen (je Wand; große Wände in Blöcken), weil der volle Lauf OOM geht.

Wände bis 45 Teile werden komplett geprüft (inkl. Wand-Prüfungen Volumen/Überlappung).
Größere Wände nur in Blöcken: dort sind die Wandfehler (Teilvolumen) erwartbar und werden getrennt gezählt.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/user/RoboPrintIFC")
SRC = ROOT / "runs/verify/S2"
OUT = ROOT / "runs/s2chunks_back"
SCEN = "spec/scenarios/S2_beispiel_ifc_modul.json"
PY = "/opt/fgc-venv/bin/python"

s = json.loads((SRC / "summary.json").read_text())
shutil.rmtree(OUT, ignore_errors=True)
jobs = []
for w in s["walls"]:
    ids = w["part_ids"]
    if not ids:
        continue
    if "right back" not in w["name"]:
        continue
    blocks = [ids[i:i + 14] for i in range(0, len(ids), 14)]
    for b, keep in enumerate(blocks):
        name = f"{w['wall_id'][:8]}_{b}"
        d = OUT / name
        (d / "parts").mkdir(parents=True)
        shutil.copy(SRC / "scene.json", d)
        sub = dict(s)
        sub["parts"] = [p for p in s["parts"] if p["part_id"] in keep]
        sub["walls"] = [dict(x, part_ids=[i for i in x["part_ids"] if i in keep]) for x in s["walls"]]
        (d / "summary.json").write_text(json.dumps(sub))
        for k in keep:
            (d / "parts" / k).symlink_to(SRC / "parts" / k)
        jobs.append((w["name"], len(blocks) == 1, name, d))

res = []
for wall, full, name, d in jobs:
    p = subprocess.run([PY, "-m", "verify.check_run", str(d), "--scenario", SCEN], cwd=ROOT,
                       capture_output=True, text=True)
    errs = [ln for ln in (p.stdout + p.stderr).splitlines() if ln.startswith("FEHLER")]
    part_errs = [e for e in errs if not e.startswith("FEHLER Wand")]
    wall_errs = [e for e in errs if e.startswith("FEHLER Wand")]
    res.append({"wall": wall, "block": name, "full_wall": full, "exit": p.returncode,
                "part_errors": part_errs, "wall_errors": wall_errs,
                "tail": (p.stdout + p.stderr).strip().splitlines()[-1:]})
    print(json.dumps(res[-1], ensure_ascii=False), flush=True)
(OUT / "result.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
sys.exit(0)

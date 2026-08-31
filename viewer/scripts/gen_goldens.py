"""Gen-Treiber: regeneriert die geteilten Py↔TS-Goldens aus dem Manifest (#195).

Der Core ist die Wahrheit (ADR-009): die eine Registratur der Paare lebt in
``fgc.parity`` (``core/src/fgc/parity.py``); dieses Skript ist nur der Treiber,
der ihre Golden-Dateien schreibt. Es ersetzt die früheren Skelett-Kopien
(gen_fk_golden, gen_nozzle_golden, gen_section_params_golden,
gen_staleness_section_golden, gen_staleness_golden).

Neu erzeugen (vom Repo-Root, venv) — alle oder einzelne Paare:

    .venv/Scripts/python.exe viewer/scripts/gen_goldens.py [pair ...]

Bekannte Paare listet ``--list``. Bei geteilten Golden-Dateien (staleness) wird
immer die ganze Datei geschrieben. Rezept für neue Paare: docs/paritaet.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fgc.parity import MANIFEST, generate

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> None:
    if "--list" in argv:
        for entry in MANIFEST:
            print(f"{entry.pair}: {entry.golden} [{entry.block}]")
        return
    for path, blocks in generate(root=REPO, only=argv or None):
        print(f"{path} geschrieben: {', '.join(blocks)}.")


if __name__ == "__main__":
    main(sys.argv[1:])

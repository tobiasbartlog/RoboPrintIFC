"""G5: python -m verify.fake_drcf <laufordner>... (Exit 0 genau bei Bestehen)."""

from __future__ import annotations

import sys
from pathlib import Path

from verify.fake_drcf.check import check_rundir


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("Aufruf: python -m verify.fake_drcf <laufordner>...", file=sys.stderr)
        return 2
    all_errs = []
    for a in args:
        errs, stats = check_rundir(Path(a))
        for k, v in stats.items():
            print(f"{a}: {k}: {v}")
        all_errs += [f"{a}: {e}" for e in errs]
    for e in all_errs[:60]:
        print(f"FEHLER {e}")
    print(f"fake_drcf: {'BESTANDEN' if not all_errs else 'NICHT BESTANDEN'} ({len(all_errs)} Fehler)")
    return 0 if not all_errs else 1


if __name__ == "__main__":
    sys.exit(main())

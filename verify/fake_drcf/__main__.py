"""G5: python -m verify.fake_drcf [--jobs N] <laufordner>... (Exit 0 genau bei Bestehen).

Teile mit identischer Trajektorie und identischem Programmtext (ohne Kommentarzeilen) werden einmal
ausgefuehrt. --jobs: Arbeitsprozesse (Default VERIFY_JOBS oder min(4, CPUs))."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from verify.fake_drcf.check import check_rundir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="*", type=Path)
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("VERIFY_JOBS", "0")) or
                    max(1, min(4, os.cpu_count() or 1)))
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.run_dirs:
        print("Aufruf: python -m verify.fake_drcf [--jobs N] <laufordner>...", file=sys.stderr)
        return 2
    all_errs = []
    for a in args.run_dirs:
        errs, stats = check_rundir(a, jobs=max(1, args.jobs))
        for k, v in stats.items():
            print(f"{a}: {k}: {v}")
        all_errs += [f"{a}: {e}" for e in errs]
    for e in all_errs[:60]:
        print(f"FEHLER {e}")
    print(f"fake_drcf: {'BESTANDEN' if not all_errs else 'NICHT BESTANDEN'} ({len(all_errs)} Fehler)")
    return 0 if not all_errs else 1


if __name__ == "__main__":
    sys.exit(main())

"""Herzschlag fuer Cloud-Nachtlaeufe: entscheiden, ob eine Session uebernimmt, und die Zeile setzen.

Die erste Zeile der Fortschrittsdatei lautet
    Herzschlag: <ISO-Zeit> · Session: <Kennung> · Phase: <Phase> · Status: <bereit|laeuft|FERTIG>

pruefen  liest die Zeile aus einem Git-Ref (Standard origin/v2/muster) und endet mit
         0 = uebernehmen, 3 = andere Session lebt (beenden), 4 = Lauf fertig (beenden).
setzen   schreibt die Zeile in die Datei im Arbeitsbaum (Commit und Push macht die Session).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # noqa: BLE001 - ohne tzdata (Windows) reicht der feste Sommerzeit-Versatz
    BERLIN = timezone(timedelta(hours=2))

LINE = re.compile(r"^Herzschlag: (?P<t>\S+) · Session: (?P<s>\S+) · Phase: (?P<p>\S+) · Status: (?P<st>\S+)")


def _now() -> datetime:
    return datetime.now(BERLIN).replace(microsecond=0)


def pruefen(args: argparse.Namespace) -> int:
    text = subprocess.run(["git", "show", f"{args.ref}:{args.datei}"], capture_output=True, text=True,
                          encoding="utf-8", check=False).stdout
    m = LINE.match(text.splitlines()[0] if text else "")
    if not m:
        print(f"UEBERNEHMEN: keine Herzschlagzeile in {args.ref}:{args.datei}")
        return 0
    if m["st"] == "FERTIG":
        print(f"BEENDEN: Lauf ist fertig ({m['t']}, Session {m['s']})")
        return 4
    if m["s"] == args.session:
        print(f"UEBERNEHMEN: eigene Session {m['s']}")
        return 0
    try:
        age = (_now() - datetime.fromisoformat(m["t"])).total_seconds() / 60.0
    except ValueError:
        age = float("inf")
    if m["st"] == "laeuft" and age < args.max_min:
        print(f"BEENDEN: Session {m['s']} lebt (Herzschlag vor {age:.0f} min, Phase {m['p']})")
        return 3
    print(f"UEBERNEHMEN: Herzschlag von {m['s']} vor {age:.0f} min, Status {m['st']}, Phase {m['p']}")
    return 0


def setzen(args: argparse.Namespace) -> int:
    with open(args.datei, encoding="utf-8") as f:
        lines = f.read().splitlines()
    new = f"Herzschlag: {_now().isoformat()} · Session: {args.session} · Phase: {args.phase} · Status: {args.status}"
    if lines and LINE.match(lines[0]):
        lines[0] = new
    else:
        lines.insert(0, new)
    with open(args.datei, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(new)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pruefen")
    p.add_argument("--session", required=True)
    p.add_argument("--datei", default="MUSTER-PROGRESS.md")
    p.add_argument("--ref", default="origin/v2/muster")
    p.add_argument("--max-min", type=float, default=75.0)
    s = sub.add_parser("setzen")
    s.add_argument("--session", required=True)
    s.add_argument("--phase", required=True)
    s.add_argument("--status", default="laeuft", choices=["bereit", "laeuft", "FERTIG"])
    s.add_argument("--datei", default="MUSTER-PROGRESS.md")
    args = ap.parse_args()
    return pruefen(args) if args.cmd == "pruefen" else setzen(args)


if __name__ == "__main__":
    sys.exit(main())

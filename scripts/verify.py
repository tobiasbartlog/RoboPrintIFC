"""Einstieg fuer die Abnahme: python scripts/verify.py [--fast] [--gate G1 ...].

Duenner Wrapper um verify/run.py, damit der Befehl aus jedem Verzeichnis gleich lautet.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from verify.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

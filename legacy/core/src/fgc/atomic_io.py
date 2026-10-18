"""Atomarer Rename mit kurzem Retry gegen transiente Windows-Sharing-Fehler (Issue #158).

``os.replace`` ist auf Windows zwar **atomar**, aber nicht retry-frei: hält ein
anderer Prozess (Defender/Echtzeitscanner, Suchindexer, Backup-Agent) kurzzeitig
ein Handle auf die eben geschriebene Temp- oder die Zieldatei, liefert der Rename
``ERROR_ACCESS_DENIED`` (WinError 5) oder ``ERROR_SHARING_VIOLATION`` (WinError 32)
— statt zu warten. Das trifft jede atomare Schreibstelle (ADR-018) und macht die
Testsuite auf Windows sporadisch rot; im Produktivbetrieb bricht dann eine
Mutation mit ``PermissionError`` ab, obwohl der Zustand konsistent ist und ein
Wiederholungsversuch durchgelaufen wäre. Auf POSIX tritt das nicht auf (Rename
ignoriert offene Handles).

Diese eine Stelle wiederholt **nur** den ``os.replace``-Aufruf kurz. Die
Atomarität aus ADR-018 bleibt unverändert: es wird weiterhin genau eine
Temp-Datei einschwenkt, halb geschriebene Dateien kann es nicht geben.
"""

from __future__ import annotations

import os
import time

#: WinError-Codes, die transient (fremdes Handle) und darum retry-würdig sind:
#: 5 = ERROR_ACCESS_DENIED, 32 = ERROR_SHARING_VIOLATION. Jeder andere Code — und
#: auf POSIX jeder Fehler, da ``winerror`` dort fehlt — wird sofort durchgereicht.
_TRANSIENT_WINERRORS = frozenset({5, 32})

#: Backoff *zwischen* den Versuchen (Sekunden): 5 Versuche = 4 Pausen, 10–50 ms,
#: leicht wachsend. Summe der Wartezeit im schlimmsten Fall ~110 ms.
_BACKOFF_SECONDS = (0.01, 0.02, 0.03, 0.05)
_MAX_ATTEMPTS = len(_BACKOFF_SECONDS) + 1


def replace_with_retry(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
    """``os.replace(src, dst)`` mit kurzem Retry gegen transienten WinError 5/32.

    Wiederholt den **atomaren** Rename bis zu ``_MAX_ATTEMPTS`` Mal mit wachsendem
    Backoff (10–50 ms), aber ausschließlich bei ``OSError`` mit
    ``winerror in {5, 32}`` (transiente Windows-Sharing-Verletzung durch ein
    fremdes Handle). Jeder andere Fehler — und auf POSIX jeder Fehler, weil
    ``winerror`` dort nicht existiert — wird **sofort unverändert** durchgereicht.
    Ist auch der letzte Versuch erfolglos, fliegt die letzte Original-Exception
    (nichts wird verschluckt).
    """
    for attempt in range(_MAX_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in _TRANSIENT_WINERRORS:
                raise  # nicht-transient (inkl. POSIX ohne winerror): durchreichen
            if attempt == _MAX_ATTEMPTS - 1:
                raise  # Versuche erschöpft: Original-Exception weiterwerfen
            time.sleep(_BACKOFF_SECONDS[attempt])

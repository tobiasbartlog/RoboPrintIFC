"""Kompatibilitaets-Filter: passt Zubehoer zum aktiven Roboter? (Issue #74).

Eine winzige, reine Funktion beantwortet die eine Frage der Bibliothek: Passt ein
getaggtes Zubehoer (Endeffektor, Workstation — alles mit ``compatible_robots``)
zum aktuell gewaehlten Roboter? Der **Roboter ist die Nabe** (PRD #69); das
Zubehoer verweist auf ihn.

Semantik (Migrationsschutz, deckungsgleich mit dem Viewer-Spiegel
``viewer/src/ui/compat.ts`` — Golden-Faelle):

- getaggt + Roboter in der Liste  -> ``True``  (passt)
- getaggt + Roboter NICHT in Liste -> ``False`` (fremd)
- keine/leere Tags                 -> ``True``  (unbekannt, nicht inkompatibel)
- kein aktiver Roboter (``None``)   -> ``True``  (unbekannte Auswahl)

**Befund, kein Gate** (ADR-013): das Ergebnis grauteil nur aus/warnt; es sperrt
nichts. ``False`` heisst „ausgrauen + warnen", nicht „verboten".
"""

from __future__ import annotations

from collections.abc import Sequence


def is_compatible(
    compatible_robots: Sequence[str] | None,
    active_robot: str | None,
) -> bool:
    """Gibt ``True`` zurueck, wenn das Zubehoer zum aktiven Roboter passt.

    Leere/fehlende Tags (``None`` oder leere Sequenz) und ein fehlender aktiver
    Roboter (``None``) gelten als **unbekannt** und damit als kompatibel
    (Migrationsschutz). Nur getaggtes Zubehoer, dessen Tag-Liste den aktiven
    Roboter *nicht* enthaelt, ist inkompatibel (``False``).
    """
    if not compatible_robots:
        return True
    if active_robot is None:
        return True
    return active_robot in compatible_robots

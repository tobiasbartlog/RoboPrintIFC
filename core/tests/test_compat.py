"""Golden-Faelle des Kompatibilitaets-Filters (Issue #74, domain/compat).

Diese Faelle sind im Geiste deckungsgleich mit dem Viewer-Spiegel
``viewer/src/ui/compat.test.ts`` — beide Seiten muessen verhaltensgleich
antworten (Kern rechnet, Viewer graut nur aus).
"""

from __future__ import annotations

import pytest

from fgc.domain.compat import is_compatible

M1013 = "doosan_m1013"
KR16 = "kuka_kr16"


@pytest.mark.parametrize(
    ("compatible_robots", "active_robot", "expected"),
    [
        # getaggt + passend -> True
        ((M1013, KR16), M1013, True),
        ((M1013,), M1013, True),
        # getaggt + fremd -> False
        ((KR16,), M1013, False),
        ((M1013,), KR16, False),
        # leere/fehlende Tags -> True (unbekannt, Migrationsschutz)
        ((), M1013, True),
        (None, M1013, True),
        # kein aktiver Roboter -> True (unbekannte Auswahl)
        ((M1013,), None, True),
        ((), None, True),
        (None, None, True),
    ],
)
def test_is_compatible_golden(
    compatible_robots: tuple[str, ...] | None,
    active_robot: str | None,
    expected: bool,
) -> None:
    assert is_compatible(compatible_robots, active_robot) is expected


def test_accepts_list_as_well_as_tuple() -> None:
    """Die Signatur nimmt jede Sequenz — Liste (API) wie Tupel (Domaene)."""
    assert is_compatible([KR16], M1013) is False
    assert is_compatible([M1013, KR16], M1013) is True

"""DER parametrisierte Py↔TS-Paritätstest über das Manifest (ADR-009, Issue #195).

Der Paritätsbeweis lebt von **geteilten Golden-Dateien**: der Core erzeugt sie
(``python viewer/scripts/gen_goldens.py``), beide Seiten rechnen ihre eigene
Ableitung dagegen — pytest hier, vitest drüben (``expectGoldenParity`` in
``viewer/src/test/golden-parity.ts``). Die Registratur der Paare ist
``fgc.parity.MANIFEST``; je Eintrag prüft :func:`fgc.parity.verify` die
Core-Hälfte. Ein Manifest-Eintrag ohne Golden (Datei/Block fehlt oder leer)
wird hier rot — die frühere Konvention konnte das nicht erzwingen (#74/#175
entstanden ohne Golden). Löst die #194-Handleser (test_viewer_goldens.py) und
die verstreuten Golden-Leser in test_process_params_sections/test_export ab.

Rezept für Zwilling N+1: ``docs/paritaet.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fgc.parity import MANIFEST, ParityPair, verify

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda entry: entry.pair)
def test_golden(entry: ParityPair) -> None:
    """Die Core-Hälfte jedes registrierten Paares reproduziert sein Golden."""
    verify(entry, root=REPO)


def test_every_golden_registered() -> None:
    """Jede Golden-Datei im Viewer gehört zu einem Manifest-Eintrag (und umgekehrt).

    Fängt den Degradations-Pfad „Zwilling N+1 legt ein Golden an, registriert es
    aber nicht" — dann liest es niemand auf der Core-Seite.

    **Abgrenzung (#202):** die Endung ``*.golden.json`` gehört exklusiv dieser
    Paritäts-Familie (Py-Ableitung ↔ TS-Zwilling über ein geteiltes Golden).
    Die API-Kontrakt-Familie (``viewer/src/api/contract/``) ist bewusst KEIN
    Paritäts-Paar — es gibt keinen TS-Zwilling, der etwas nachrechnet; die Datei
    IST die Core-Antwort, geprüft per tsc-Typzuweisung. Sie trägt darum das
    eigene Schema ``*.contract.json`` mit eigener zweiseitiger Registratur
    (``test_api_contract.py``) und fällt so nicht in diesen Scan.
    """
    on_disk = {
        p.relative_to(REPO).as_posix()
        for p in (REPO / "viewer" / "src").rglob("*.golden.json")
    }
    registered = {entry.golden for entry in MANIFEST}
    assert on_disk == registered

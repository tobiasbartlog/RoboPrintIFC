"""Retry-um-``os.replace`` gegen transienten WinError 5/32 (Issue #158).

Auf Windows kann ``os.replace`` mit ``ERROR_ACCESS_DENIED`` (5) oder
``ERROR_SHARING_VIOLATION`` (32) fehlschlagen, wenn ein Fremdprozess kurzzeitig
ein Handle auf die eben geschriebene Datei hält — ein transienter Fehler, der
beim Wiederholen verschwindet. ``replace_with_retry`` wiederholt darum kurz,
aber ausschließlich für diese Codes. Geprüft wird das Verhalten ohne echten
``os.replace``: die Ausnahme wird gestubbt (Monkeypatch), damit die Tests auch
auf POSIX laufen (wo ``winerror`` sonst nicht existiert).
"""

from __future__ import annotations

import pytest

import fgc.atomic_io as atomic_io


class _FakeOSError(PermissionError):
    """OSError mit gesetztem ``winerror`` — auf jeder Plattform konstruierbar.

    Auf POSIX trägt ``OSError`` kein ``winerror``; als Python-Subklasse mit
    ``__dict__`` können wir das Attribut hier plattformunabhängig setzen und so
    das Windows-Verhalten simulieren, das ``replace_with_retry`` per
    ``getattr(exc, "winerror", None)`` liest.
    """

    def __init__(self, winerror: int | None) -> None:
        super().__init__("stub replace failure")
        self.winerror = winerror


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff nicht wirklich schlafen — hält die Tests schnell."""
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _s: None)


def test_retries_transient_winerror_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zwei transiente WinError-5-Fehlschläge, dann Erfolg → kein Fehler, 3 Aufrufe."""
    calls = {"n": 0}

    def fake_replace(_src: object, _dst: object) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeOSError(5)

    monkeypatch.setattr(atomic_io.os, "replace", fake_replace)

    atomic_io.replace_with_retry("src", "dst")

    assert calls["n"] == 3


def test_sharing_violation_winerror_32_is_also_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """WinError 32 (ERROR_SHARING_VIOLATION) ist ebenfalls transient und wird wiederholt."""
    calls = {"n": 0}

    def fake_replace(_src: object, _dst: object) -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise _FakeOSError(32)

    monkeypatch.setattr(atomic_io.os, "replace", fake_replace)

    atomic_io.replace_with_retry("src", "dst")

    assert calls["n"] == 2


def test_non_transient_winerror_is_raised_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """WinError 13 ist kein Sharing-Fehler → sofort durchgereicht, kein Retry."""
    calls = {"n": 0}

    def fake_replace(_src: object, _dst: object) -> None:
        calls["n"] += 1
        raise _FakeOSError(13)

    monkeypatch.setattr(atomic_io.os, "replace", fake_replace)

    with pytest.raises(PermissionError):
        atomic_io.replace_with_retry("src", "dst")

    assert calls["n"] == 1  # genau ein Versuch, nicht wiederholt


def test_oserror_without_winerror_is_raised_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """POSIX-Fall: ``OSError`` ohne ``winerror`` (None) → sofort durchgereicht."""
    calls = {"n": 0}

    def fake_replace(_src: object, _dst: object) -> None:
        calls["n"] += 1
        raise _FakeOSError(None)

    monkeypatch.setattr(atomic_io.os, "replace", fake_replace)

    with pytest.raises(PermissionError):
        atomic_io.replace_with_retry("src", "dst")

    assert calls["n"] == 1


def test_exhausted_attempts_reraise_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dauerhafter WinError 5 → nach erschöpften Versuchen fliegt die Exception."""
    calls = {"n": 0}
    sentinel = _FakeOSError(5)

    def fake_replace(_src: object, _dst: object) -> None:
        calls["n"] += 1
        raise sentinel

    monkeypatch.setattr(atomic_io.os, "replace", fake_replace)

    with pytest.raises(PermissionError) as excinfo:
        atomic_io.replace_with_retry("src", "dst")

    assert excinfo.value is sentinel  # Original-Exception, nicht verschluckt/ersetzt
    assert calls["n"] == atomic_io._MAX_ATTEMPTS

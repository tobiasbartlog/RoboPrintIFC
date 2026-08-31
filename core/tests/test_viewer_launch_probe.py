"""API-Probe-Klassifikation des GUI-Starts (Issue #39).

Ein *veralteter* Server (kennt /projects nicht) wird ersetzt — aber ein
gesunder, nur gerade beschäftigter Server (Timeout auf /openapi.json, weil
eine C-Extension den GIL hält) darf NICHT gekillt werden. Die Probe muss
Timeout von "veraltet"/"down" unterscheiden und bei Timeout geduldiger
nachfassen, statt taskkill /F zu schicken.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from fgc.pipeline import viewer_launch as vl


def _fake_urlopen_returning(spec: dict):
    def fake(url, timeout=None):  # noqa: ARG001 — Signatur wie urllib
        return io.BytesIO(json.dumps(spec).encode("utf-8"))

    return fake


def test_probe_current(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_urlopen_returning({"paths": {"/projects": {}}})
    )
    assert vl._probe_api(1.0) == "current"


def test_probe_stale_without_projects_route(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_urlopen_returning({"paths": {"/docs": {}}})
    )
    assert vl._probe_api(1.0) == "stale"


def test_probe_timeout_is_not_stale(monkeypatch):
    def fake(url, timeout=None):  # noqa: ARG001
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert vl._probe_api(1.0) == "timeout"


def test_probe_urlerror_with_timeout_reason_is_timeout(monkeypatch):
    def fake(url, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert vl._probe_api(1.0) == "timeout"


def test_probe_connection_refused_is_down(monkeypatch):
    def fake(url, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert vl._probe_api(1.0) == "down"


def test_startup_probe_retries_timeout_patiently():
    calls: list[float] = []

    def probe(timeout_s: float) -> str:
        calls.append(timeout_s)
        return "timeout" if len(calls) == 1 else "current"

    assert vl._startup_probe(probe) == "current"
    assert calls == [1.0, 5.0]  # zweite Chance mit größerem Timeout


def test_startup_probe_timeout_twice_stays_timeout():
    assert vl._startup_probe(lambda _t: "timeout") == "timeout"


def test_startup_probe_stale_needs_no_retry():
    calls: list[float] = []

    def probe(timeout_s: float) -> str:
        calls.append(timeout_s)
        return "stale"

    assert vl._startup_probe(probe) == "stale"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [("current", True), ("stale", False), ("timeout", False), ("down", False)],
)
def test_is_api_running_true_only_for_current(monkeypatch, status, expected):
    monkeypatch.setattr(vl, "_probe_api", lambda _t=1.0: status)
    assert vl.is_api_running() is expected


def test_probe_httpexception_is_down(monkeypatch):
    """BadStatusLine & Co. (fremder Nicht-HTTP-Dienst) dürfen nicht crashen (Issue #47)."""
    import http.client

    def fake(url, timeout=None):  # noqa: ARG001
        raise http.client.BadStatusLine("kein http")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert vl._probe_api(1.0) == "down"


@pytest.mark.parametrize(
    ("status", "busy", "expected"),
    [
        ("current", True, "ok"),
        ("current", False, "ok"),
        ("timeout", True, "keep"),  # beschäftigter Server: nicht anfassen
        ("stale", True, "replace"),  # veraltete fgc-API: ersetzen
        ("down", True, "blocked"),  # fremder/unklarer Belegter: NICHT killen (Issue #47)
        ("stale", False, "start"),
        ("down", False, "start"),
    ],
)
def test_startup_decision(status, busy, expected):
    assert vl._startup_decision(status, busy) == expected

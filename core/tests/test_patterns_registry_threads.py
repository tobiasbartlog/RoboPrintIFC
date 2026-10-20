"""Der Musterkatalog ist auch beim ersten, gleichzeitigen Abruf vollständig (API mit Threadpool).

Befund aus der Gegenprüfung M4: Viewer und Playwright fragen `/api/patterns` gleich nach dem Serverstart
parallel ab. Setzte `load_families` das Geladen-Kennzeichen vor den Importen, bekam der zweite Thread
einen Katalog nur mit „schalen“ (e2e `muster-ablauf.spec.ts` scheiterte so in 2 von 4 Läufen)."""

from __future__ import annotations

import importlib
import pkgutil
import threading
import types

from roboprint.patterns import registry


def test_concurrent_first_load_sees_all_families(monkeypatch):
    full = registry.names()
    assert "sinus" in full and len(full) > 1
    pkg = importlib.import_module("roboprint.patterns.families")
    fam_modules = {m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_")}
    saved = dict(registry._PATTERNS)
    # Zustand direkt nach dem Serverstart: Familien noch nicht registriert, nichts geladen
    base = {n: p for n, p in saved.items() if p.family not in fam_modules}
    monkeypatch.setattr(registry, "_PATTERNS", base)
    monkeypatch.setattr(registry, "_loaded", False)

    entered = threading.Event()
    release = threading.Event()

    def slow_import(name: str):
        mod = importlib.import_module(name)  # liegt in sys.modules: Registrierung von Hand nachholen
        if name.startswith("roboprint.patterns.families."):
            entered.set()
            release.wait(5)
            fam = name.rsplit(".", 1)[-1]
            registry._PATTERNS.update({n: p for n, p in saved.items() if p.family == fam})
        return mod

    monkeypatch.setattr(registry, "importlib", types.SimpleNamespace(import_module=slow_import))
    seen: list[list[str]] = []
    t1 = threading.Thread(target=lambda: seen.append(registry.names()))
    t1.start()
    assert entered.wait(5)
    t2 = threading.Thread(target=lambda: seen.append(registry.names()))
    t2.start()
    t2.join(0.3)  # vorher kam der zweite Abruf hier mit halbem Katalog zurück
    release.set()
    t1.join(5)
    t2.join(5)
    assert len(seen) == 2
    assert seen[0] == full and seen[1] == full

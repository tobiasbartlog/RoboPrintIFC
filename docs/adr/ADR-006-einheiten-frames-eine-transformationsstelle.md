# ADR-006 — Einheiten, Frames und die eine Transformationsstelle

Status: angenommen · 2026-06-10

## Kontext
Einheiten-/Frame-Verwechslung ist die klassische Spätfehlerquelle — deshalb hier am strengsten.

## Entscheidung
Intern durchgängig: Millimeter, Radiant, rechtshändige Koordinatensysteme, Quaternionen `[w, x, y, z]`. IFC (Meter) wird ausschließlich in `ifc_io` konvertiert; Grad existieren ausschließlich in den Emittern. Es gibt genau eine Stelle, an der Bauteilwelt und Roboterwelt verheiratet werden: das Setup-Artefakt (Wandlage relativ zur Roboterbasis + TCP). Kein anderes Modul trifft implizite Annahmen über die Aufspannung.

## Konsequenzen
Ein Kalibrier-/Registrierworkflow (Wandnullpunkt am Roboter antasten → Setup schreiben) ist von Anfang an Teil des Systems.

## Revisionstrigger
Keiner — Verstöße sind Bugs, keine Architekturänderung.

## Nachtrag 2026-07-09 — Das Setup wird je Zerlegungsart anders *befüllt* (Issue #136)

Das Setup bleibt **die eine Transformationsstelle** — es wird nur je **Zerlegungsart**
anders *befüllt*, nicht dupliziert. Bei Art **„abschnitt"** entsteht es weiter über das
**Antast-Verfahren** (gemessenes `setup.json`, `setup_source="measured"`; ohne Antasten
der gekennzeichnete Hinweis). Bei Art **„modul"** (ADR-022) — Roboterbasis und Druckfläche
sind konstruktiv auf derselben Platte verschraubt, es gibt nichts anzutasten — **generiert**
der Export das Setup aus Stammdaten: Workstation-Frames (feste Platzierung) + Werkzeug-TCP
+ Workstation-`io_channels`/`deadtime` (S1), `setup_source="generated"`. Beide Wege münden in
**dasselbe** Setup-Artefakt und denselben Emitter-Pfad (`_emit_drl_from_setup`); Bauteil- und
Roboterwelt werden weiterhin an genau **einer** Stelle verheiratet. Das Gate des Modul-Exports
prüft „kein beteiligter Wert fehlt oder ist provisorisch" (Frames, nicht-provisorischer TCP,
bestätigtes Kanal-Mapping, gemessene Totzeit) — Befund, kein Gate (ADR-013).

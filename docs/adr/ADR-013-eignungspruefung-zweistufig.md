# ADR-013 — Eignungsprüfung E1 zweistufig

Status: angenommen · 2026-07-02 (Grill-Session)

## Kontext
Das Zielbild beginnt vor der Architektur v0.1: aus einem vollen IFC-Modell die druckbaren Wände filtern (`fgc walls list` → `candidates.json`). Die dafür nötigen Prozessfenster-Zahlen (Strangbreite, min./max. Wanddicke) existieren aber noch nicht belastbar — sie kommen erst aus Spike S4 und den Extruderversuchen.

## Entscheidung
- **Stufe 1 (ab M0, ohne Versuchsdaten):** Planarität, `LoadBearing = false`, Öffnungsanzahl (v1: 0, vgl. OD-3), Höhe/Länge gegen Arbeitsraum des Zielroboters.
- **Stufe 2 (sobald S4-Zahlen vorliegen):** Wanddicke im Prozessfenster. Grenzen als konfigurierbare Parameter mit `provisional`-Flag — die P4-Logik gilt auch für Prozessparameter.
- Eine provisorische Prozessparameter-Karte (`materialcards/process_window.provisional.json`) ist die eine Quelle für E1 **und** Slicer.

## Konsequenzen
`candidates.json` kennzeichnet Stufe-2-Checks als `provisional`; Wände mit Öffnungen werden gelistet, aber als `deferred` markiert.

## Revisionstrigger
S4 + Versuche liefern belastbare Zahlen → provisional-Flags fallen, Karte wird gemessen.

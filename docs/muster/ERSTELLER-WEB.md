# Musterersteller im Viewer (`web/`)

Parametrischer 2D-Musterersteller nach dem Nutzer-Nachtrag vom 20.10.2026, 18:20
(`docs/muster/AUFTRAG.md`). Der Browser rechnet keine Fachlogik (SPEC §9): Jede Vorschau kommt
aus `POST /api/patterns/preview`, gerechnet von `core/src/roboprint/patterns/`.

## Platz im Viewer

Ein Reiter „Muster“ in der Kopfzeile, neben „Ablauf“. Begründung nach `docs/ux-leitbild.md`:

- Das Leitbild hat vier Schritte mit je einer Hauptaktion und einem Zustand (fehlt, veraltet,
  aktuell). Der Musterersteller braucht weder Modell noch Lauf und hat keinen Zustand, der
  veralten kann. Als fünfter Schritt würde er den Stepper verwässern.
- Ein Drawer im Parameterpanel wäre zu eng: Die Vorschau braucht die große Fläche.
- Der Reiter ist von jedem Schritt aus mit einem Klick erreichbar; `/?view=muster` öffnet ihn direkt.

In der Ansicht „Muster“ liegt die Vorschau samt Kennzahlen in der Hauptfläche, alle Regler
liegen im Seitenpanel (einklappbare Abschnitte).

## Bedienung

1. **Muster** wählen (aus `GET /api/patterns`, gruppiert nach Rolle) oder ein gespeichertes
   Muster laden.
2. **Maße:** Modullänge und Wanddicke frei eingeben oder aus einem Modul des letzten Laufs bzw.
   einer Wand des Modells übernehmen.
3. **Regler** entstehen aus den ParamSpecs des Kerns (deutsche Beschriftung, Einheit, Bereich,
   Schritt). Geänderte Regler sind fett und lassen sich einzeln zurücksetzen. Entprellt:
   120 ms nach der letzten Änderung geht eine Anfrage raus, veraltete Anfragen werden
   abgebrochen. Bei einem Fehler (422) bleibt die letzte gültige Vorschau stehen.
4. **Speichern** als benanntes Preset (`POST /api/patterns/presets`), **SVG exportieren**
   (der Kern zeichnet es, `?format=svg`).

## Darstellung

Strang nach Segmentart eingefärbt (Außenschale, Innenschale, Laibungsschale, Infill/Gurt, Steg,
Außenfeld/Endkappe), Richtungspfeile, Start (Kreis) und Ende (Quadrat), Folgeschicht blass
gestrichelt, Kontakte nach Art (Fuge, Knoten, Schale), Regelverstöße M1–M7 rot (Fehler) bzw.
orange gestrichelt (Warnung). Die Legende zeigt die Arten, die in der Vorschau vorkommen; neue
Segment- und Kontaktarten des Kerns erscheinen dort mit neutraler Farbe und ihrem Namen, bis
`web/src/state/patterns.ts` sie beschriftet.

Kennzahlen: Pfadlänge und Druckzeit je Schicht, Material je Meter, Zellen, Kontakte (Anzahl,
Länge, nach Art), Fugenabstand, längste gerade Außenstrecke, kleinster Radius, kleinster
Strangabstand, Schichtwechsel. „An Modullänge anpassen“ erscheint als Kasten „Anpassung an die
Modullänge“ mit Feldzahl und tatsächlicher Feldlänge, sobald ein Muster ein `fit_to_length`-
Ergebnis in `meta` liefert; der Schalter dazu ist ein Bool-Regler des Musters.

## Tests

- `web/src/state/patterns.test.ts`, `patternStore.test.ts`, `pattern/PatternBuilder.test.tsx`
  (Vitest, gegen eine Fake-API; geprüft wird die Anbindung, nicht die Geometrie).
- `web/e2e/muster.spec.ts` (Playwright gegen die echte API): Muster wählen, Regler ziehen,
  Vorschau ändert sich, Speichern, SVG-Export, kein Überlauf bei 1280 × 800. Screenshots
  `web/e2e/screenshots/muster*.png`.

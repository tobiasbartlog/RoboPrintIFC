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

## Musterwahl im Ablauf (M4)

Der Ablauf („Zerlegen & prüfen“) trägt jetzt die Musterwahl bis in den Lauf. Der Browser rechnet
auch hier nichts: Wahl und Regler gehen als Jobparameter an die API, Kennzahlen und Schichten
kommen aus dem fertigen Lauf.

- **Wahl** im Seitenpanel, Kasten „Druckmuster“ über den Druckeinstellungen: Muster (gespeicherte
  Muster, Infill, Außenhaut, ganze Wand, aus `GET /api/patterns`) und Schichtfolge (Standard,
  gleich, wechselnd). Standard ist „Kein Muster“ mit Schichtfolge „Standard“; dann geht kein
  Musterparameter in den Job, der Lauf schneidet wie vorher. Die Wahl zählt zur Basis des Laufs:
  Ändert sie sich, ist der Lauf „veraltet“.
- **Jobparameter** (`POST /api/projects/{id}/jobs`, `params`): `pattern_preset` (Preset-id; der Server
  löst sie in die Preset-Datei auf, mitgeliefert oder eigen, und meldet unbekannte ids mit 422),
  `infill_pattern`, `outfill_pattern`, `layer_order`, `pattern_params` (Objekt). Muster und
  Parameter werden schon beim Anlegen des Jobs geprüft (422 mit Klartext), nicht erst im Jobprozess.
  Ein Infill-Muster geht nach `infill_pattern`, Außenhaut und „ganze Wand“ nach `outfill_pattern`.
- **„Für Lauf verwenden“** im Musterersteller übernimmt das gewählte Muster (bzw. Preset) samt den
  geänderten Reglern als `pattern_params` und wechselt nach „Zerlegen & prüfen“ (ohne Modell nach
  „Modell“; die Wahl bleibt gesetzt). Beim Laden eines Presets gehen nur Abweichungen vom Preset mit.
  Strangbreite, Schichthöhe, Abtastabstand und Verbinder gelten aus den Druckeinstellungen des
  Ablaufs, nicht aus dem Musterersteller (der Kern liest sie immer aus dem Szenario).
- **Kennzahlen je Teil** (Teil-Panel, gewähltes Teil): `GET /api/pattern-report/metrics?run_id&part_id`
  (`core/src/roboprint/pattern_report.py`, Vertrag `PartPatternReport`): Bahnlänge und Anteil je
  Segmentart, Druckzeit (Länge / v_print), Material, Stränge (Pumpe an, kein Halt), Schichtwechsel
  (senkrecht ≤ 0,5 mm, schräg, mit Absetzen), offene Segmente. Auch Läufe ohne Muster bekommen die
  Zahlen für die Schalen.
- **Schichtvorschau** (2D, gewähltes Teil, Schicht per Regler oder Pfeiltasten):
  `GET /api/pattern-report/layer?run_id&part_id&layer` (Vertrag `PartPatternLayer`): Polylinien je
  Ring im Teil-Frame P (aus `toolpath.json` über `T_WP`), Start (Kreis), Ende (Quadrat),
  Richtungspfeile, Nachbarschicht (Folgeschicht, bei der letzten die Vorgängerschicht) blass
  gestrichelt.
- **Farben:** Segmentarten haben in der 2D-Vorschau, der Legende und der 3D-Ansicht dieselben Farben
  (Außenschale blau, Innenschale cyan, Laibung türkis, Infill rosa, Steg grün, Außenfeld violett).
  In 3D färben sich Bahn und Raupen nur, wenn das Teil Musterarten (`infill`, `web`, `outfill`)
  enthält; Schalen behalten die Teilfarbe, damit Läufe ohne Muster unverändert aussehen. Die Legende
  oben links in der 3D-Ansicht erscheint ebenfalls nur dann.

### Tests

- `core/tests/test_api_pattern_run.py`: Kennzahlen gegen die Slicer-Geometrie, Schicht im Frame P
  (T_WP ≠ I), Endpunkte, Durchreichen der Parameter bis in `scenario.json`, Preset-ids (mitgeliefert
  und eigen), 422 bei Ungültigem, Standard unverändert.
- `web/src/state/patternChoice.test.ts`, `web/src/components/PatternRun.test.tsx`,
  `web/src/scene/__tests__/kindColors.test.ts` (Vitest, Fake-API; geprüft wird die Anbindung).
- `web/e2e/muster-ablauf.spec.ts` (Playwright, echte API und echter Kern): Muster und Schichtfolge im
  Ablauf wählen, der abgefangene Job wird mit genau diesen Parametern auf einem Quader
  600 × 200 × 60 mm gerechnet, Kennzahlen, Schichtvorschau (alternate kehrt die Reihenfolge um),
  3D-Legende; „Für Lauf verwenden“; Preset-id an die echte API. Screenshots
  `web/e2e/screenshots/muster-ablauf-*.png`, `muster-schicht.png`, `muster-3d.png`,
  `muster-fuer-lauf.png`.

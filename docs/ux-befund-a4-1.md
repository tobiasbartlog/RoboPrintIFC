# UX-Befund A4.1 (Phase P4)

Geprüft gegen die Checkliste in `docs/ux-leitbild.md`. Grundlage: die Screenshots unter
`web/e2e/screenshots/` (Stand 0dc2ac9) und eigene Aufnahmen gegen die echten Läufe `verify/S1` und
`verify/S3` (Desktop 1440 × 900, 1280 × 800, schmal 1024 × 768, hell und dunkel).

Schwere: **hoch** = verletzt einen Checklistenpunkt sichtbar, **mittel** = erschwert den Weg eines
Neulings, **niedrig** = Feinschliff. Status: **behoben** in diesem Commit oder **offen** als Aufgabe.

## Top 10

| # | Mangel | Checklistenpunkt | Beleg | Schwere | Status |
|---|---|---|---|---|---|
| 1 | Abstandszahl an der Kontaktlinie rot auf rotem Druckstand bzw. gelb auf gelbem Tisch, praktisch unlesbar | Kollisionsmoment: Kontaktlinie mit Zahl | `g6-s3-kollision.png`, `g6-3-wiedergabe.png` (alt) | hoch | behoben |
| 2 | Direkteinstieg: Schritt „Zerlegen & prüfen“ zeigt grünes „aktuell“, ist aber gesperrt („Erst ein Modell wählen.“) | Kein Grün ohne erfüllten Zustand | `g6-s3-kollision.png`, `player-kollision.png` (alt) | hoch | behoben |
| 3 | Seitenpanel läuft seitlich über: DRL-Vorschau und Beispielknöpfe werden rechts abgeschnitten | Kein horizontaler Überlauf | `g6-4-export.png` (alt), eigene Aufnahme `model-dark` 1024 px | hoch | behoben |
| 4 | Parameter: jede Zeile trägt einen deaktivierten Knopf „Zurücksetzen“ ohne Grund | Jeder deaktivierte Knopf nennt den Grund | `2-zerlegen.png` (alt) | mittel | behoben |
| 5 | Export: zwei gleich gefüllte Download-Knöpfe je Teil (v2 und v3), auch bei nicht machbarem Teil | Genau eine hervorgehobene Hauptaktion | `g6-4-export.png` (alt) | mittel | behoben |
| 6 | Ursache „nicht machbar“ als Rohlog („Sample 336 (transfer, Ring 0, k=0): d = 8.4 mm < d_hard …“) | Kein Rohfehler ohne Klartext | eigene Aufnahme `decompose-direct` (S3) | mittel | behoben |
| 7 | Interne Begriffe und schwer lesbare Zahlen: „d_min“, „Samples“, „IK-Zweig“, „62112 Samples“, Zeit „1.309,0 / 1.442,0 s“, „1 Bereiche“, „Standard 0.3 rad“ | Klartext auf Deutsch | `g6-2-zerlegen.png`, `g6-3-wiedergabe.png` (alt) | mittel | behoben |
| 8 | 3D-Ansicht in Schritt 1 und 2 leer (nur Gitter); die gewählte Wand erscheint nicht in 3D, kein Hinweis | Neuling kommt ohne Handbuch durch; Wandliste synchron zur 3D-Auswahl | `g6-1-modell.png`, `g6-2-zerlegen.png` | hoch | teilweise: Leerhinweis ergänzt, Wandvorschau offen |
| 9 | Zerlegen zeigt nur eine Teileliste: kein Raster der Module in Wandansicht, keine Kennzahlen Druckzeit, kein Fortschritt je Modul | Ablauf Schritt 2 (Leitbild) | `g6-2-zerlegen.png` | mittel | offen |
| 10 | Texte aus dem Kern ohne Umlaute („Wand zu duenn“, „Schichthoehe“, „Duese“, „ueber“, „Waende“), Beispielnamen als Kennungen („S1_modul_referenz“); Bericht zum Export fehlt | Klartext auf Deutsch; Export „dazu ein Bericht“ | `g6-1-modell.png`, `g6-4-export.png` | niedrig | offen |

## Aufgaben im Einzelnen

### 1 Kontaktzahl lesbar (behoben)
`web/src/scene/ContactOverlay.tsx`: Die Zahl steht jetzt in einem Kästchen mit Theme-Hintergrund
(`--mantine-color-body`), Theme-Textfarbe und einem Rand in der Statusfarbe; Dezimalkomma (de-DE).

### 2 Kein Grün auf gesperrtem Schritt (behoben)
`web/src/state/stepper.ts`: Ein direkt geöffneter Lauf macht „Zerlegen & prüfen“ betretbar, dort
erscheint die Teileliste. „Zerlegen & prüfen“ selbst bleibt ohne Wand deaktiviert und sagt
„Erst im Schritt Modell eine Wand wählen.“ Test in `stepper.test.ts`.

### 3 Kein seitlicher Überlauf im Panel (behoben)
`web/src/App.tsx`: Das Seitenpanel scrollt nur senkrecht (Mantine-`ScrollArea` legte den Inhalt als
`display: table` an und wuchs mit der DRL-Vorschau). Die DRL-Vorschau hat einen eigenen
Scrollkasten in beide Richtungen. Beispiele sind Karten mit umbrechendem Namen und einzeiliger
Beschreibung (voller Text im Tooltip).

### 4 Zurücksetzen nur, wenn es etwas zurückzusetzen gibt (behoben)
`web/src/components/ParamsPanel.tsx`: Der Knopf erscheint nur bei geändertem Wert, dazu ein
Abzeichen „geändert“ am Parameter. Defaults mit Dezimalkomma.

### 5 Eine Hauptaktion im Export (behoben)
`web/src/components/ExportStep.tsx`: Gefüllt ist nur der Download im gewählten Dialekt (Parameter,
Standard v2) und nur bei machbarem Teil; der andere Dialekt ist neutral, „anzeigen“ heißt
„Vorschau“. Ein Satz erklärt Dialekt und Firmware.

### 6 Ursache in Klartext (behoben)
`web/src/components/DecomposeStep.tsx`: „Erstes Problem bei 0:02,7 min: Glied 3 ↔ Tisch zu nah. In
der Simulation ansehen, dann Parameter oder Wand ändern.“ Die Rohmeldung liegt unter „Details“.
Ungeeignete Wände enden mit der Handlung „Andere Wand wählen.“

### 7 Begriffe und Zahlen (behoben)
„kleinster Abstand“, „Bahnpunkte … frei / unter Sollabstand“, „Armstellung“ (Glossar SPEC §3),
„Bahnpunkt 62.188 von 68.933“, Spielzeit als `m:ss,s min`, Singular/Plural bei „Bereich(e)“,
Timeline-Spur „Bewegung“ statt „Art“, Teil-Abzeichen ohne Großschreibung (`box_01` statt `BOX_01`).

### 8 Wand in 3D zeigen (offen, größer)
Leerhinweis in der 3D-Ansicht ist ergänzt („Hier erscheinen nach ‚Zerlegen & prüfen‘ …“).
Offen: Die API liefert unter `/api/projects/{id}` nur Maße, keine Geometrie. Nötig ist ein
Wandmesh (z. B. `walls/{wall_id}.stl` im Frame L) und eine Szene „Modell“, die alle Wände zeigt,
die gewählte hervorhebt und per Klick auswählt (synchron zur Liste).

### 9 Modulraster und Kennzahlen (offen, größer)
Schritt 2 braucht ein Raster der Module in Wandansicht (2D, gefärbt nach Status) und Kennzahlen
Anzahl, Druckzeit (aus `t_s` je Teil), kleinster Abstand; dazu Fortschritt je Modul während des
Jobs (`stage`/`message` liefern heute nur Text). Kann der Viewer aus `summary.json` und
`part.json` (BBox in L) ohne Fachlogik zeichnen; die Druckzeit sollte `summary.json` liefern.

### 10 Texte aus dem Kern, Bericht (offen)
Die Eignungsgründe (`core`), die Annahmenliste in `summary.json` und die Szenario-Beschreibungen
schreiben ASCII-Umschrift. Im Kern auf UTF-8 mit Umlauten umstellen (DRL-Kopf darf ASCII bleiben).
Beispiele bräuchten einen Anzeigenamen („Referenzmodul 600 × 200 × 400 mm“). Für den Export fehlt
ein herunterladbarer Bericht (z. B. `summary.json` und `check.json` als lesbares HTML/PDF).

## Weitere Beobachtungen (nicht in den Top 10)

- Nach dem Laden eines Beispiels rutscht „Weiter zu Zerlegen & prüfen“ unter den Falz (1280 × 800).
  Vorschlag: Beispielliste nach dem Öffnen einklappen.
- S1 ist „machbar“, aber 100 % der Bahnpunkte liegen unter dem Sollabstand 50 mm. Eine verdichtete
  Aussage („durchgehend unter Sollabstand, kleinster Abstand 10,8 mm ≥ 10 mm hart“) fehlt.
- Ganzer Tisch wird bei Warnung gelb eingefärbt; sehr dominant, eine Kante oder ein Fleck um den
  Kontaktpunkt würde reichen.
- Geprüft und in Ordnung: Kollision zeigt Glied rot, Hindernis eingeblendet, Kontaktlinie mit Zahl;
  Timeline mit Bereichsbalken; Listeneintrag springt, pausiert und richtet die Kamera aus; Hell- und
  Dunkelmodus lesbar; kein Seitenüberlauf bei 1024, 1280 und 1440 px Breite.

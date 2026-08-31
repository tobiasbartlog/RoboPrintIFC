# ADR-022 — Modul-Zerlegung: Workstation als Druckort, Platzierung als Relativpose

Status: **Angenommen** (2026-07-07, Grill zur Druckplan-Neuordnung II);
**Nachtrag 2026-07-09** (Issue #132): Aufstellhöhen bei Art „Abschnitt" absolut
Kontext-Grill: 2026-07-07 (Nutzerwunsch nach Abschluss von PRD B/#70)

## Kontext

Die Zerlegungsart **Modul** (Glossar `core/CONTEXT.md`: separat gedruckt,
danach versetzt und gefügt) war bisher eine deklarierte „spätere Option":
im Viewer eine deaktivierte `<option>`, im Core ein `ValueError` in
`decompose.propose`/`from_cuts`. Der Nutzer will sie jetzt funktionsfähig —
die Wahl Abschnitt↔Modul ist eine entscheidende Logikveränderung für die
Wandaufteilung: bei **Abschnitt** wird der Roboter an der Wand umgesetzt
(auch in der Höhe), bei **Modul** wird vorproduziert und auf der Baustelle
montiert. Fügegeometrie (Verbindungsgeometrien) ist explizit ausgeklammert
und folgt später.

Gleichzeitig liegen seit ADR-021 die Workstation-Frames (`robot_base_frame`,
`work_surface_frame`) als Stammdaten vor — bewusst noch ohne Konsumenten
(„nur der Druckplan-Automatismus wird sie nutzen", Naht #77).

## Entscheidung

1. **Kein neuer Begriff „Druckstation": der Druckort der Modul-Fertigung ist
   die Workstation.** Der Roboter sitzt fest an `robot_base_frame`, jedes
   Modul wird auf der Arbeitsfläche (`work_surface_frame`) positioniert.
   Damit bekommen die ADR-021-Frames genau den vorgesehenen Konsumenten.

2. **Platzierung wird als Relativpose zwischen Roboterbasis und Druckobjekt
   verallgemeinert** — ein Konzept, zwei Leserichtungen: bei Abschnitt steht
   das Objekt (Roboter bewegt sich durch die Welt), bei Modul steht der
   Roboter (Modul liegt vor ihm). Rechnerisch identisch: `placement.suggest`
   auf das Modul-Rechteck liefert die Pose, sie wird nur invertiert
   interpretiert. Datenmodell (`PlacementOption` je Section) und
   Bewertungsmaschinerie (`evaluate`, Ampeln) bleiben unverändert.

3. **Module werden stehend in Einbauorientierung gedruckt.** Schichtaufbau
   und FGC-Gradient müssen der eingebauten Wand entsprechen; liegend drucken
   würde die Schichtrichtung um 90° kippen. Dadurch ist die
   Modul-Erreichbarkeitsprüfung dieselbe Rechteck-Prüfung wie bei
   Abschnitten.

4. **Modulgröße:** harter Begrenzer ist der Arbeitsraum an der festen
   Platzierung; dazu optionale globale Obergrenzen max. Modullänge/-höhe
   (Transport/Montage). Das Modulgewicht (Volumen × Dichte, Dichte als
   Materialparameter mit Default) wird je Modul angezeigt — **Befund, kein
   Gate**.

5. **Schnittebenen sind zerlegungsart-neutral.** Der Wechsel Abschnitt↔Modul
   behält den Schnittplan und setzt nur das bestehende `dirty`-Flag; der
   Re-Check bewertet dieselbe Geometrie mit der Logik der neuen Art.
   Slicing-Overrides (`process_params.sections`) überleben den Wechsel
   (stabile Section-IDs vorausgesetzt); Platzierungs-Overrides verfallen —
   ein Stellplatz am Einbauort ergibt an der Workstation keinen Sinn.

6. **Reihenfolge:** Druckreihenfolge = Montagereihenfolge (unten→oben,
   links→rechts), keine Umsortier-Funktion in v1. Die
   „Ganze Wand"-Simulation heißt im Modul-Modus „Alle Module" und spielt
   sequentiell am Druckort; eine Montage-Simulation (Kran) ist out of scope
   bis Fügegeometrie existiert.

## Alternativen erwogen

- **Eigenes Konzept „Druckstation"** neben der Workstation — verworfen:
  dupliziert Stammdaten (Mesh, Frames, Sicherheitsabstand), und die
  stationäre Workstation *ist* fachlich der Vorfertigungsplatz.
- **Zweites Platzierungs-Konzept für Module** (Modul-Pose statt
  Roboter-Pose) — verworfen: dieselbe Relativpose, zwei Begriffe hätten
  Glossar, Datenmodell und Bewertung gespalten.
- **Liegend drucken zulassen** — verworfen für v1: kippt die
  Schichtrichtung gegen die Einbauorientierung und bräuchte eine eigene
  strukturelle Bewertung.
- **Modul erst nach der UI-Neuordnung** (nur strukturell verankern) — vom
  Nutzer abgelehnt: Modul soll jetzt funktionieren, Fügegeometrie darf
  später kommen.
- **Schnittplan beim Artwechsel verwerfen** — verworfen: destruktiv,
  widerspricht „veraltet, nicht gelöscht" (ADR-017-Geist) und verhindert
  den explorativen Vergleich beider Arten.

## Konsequenzen

- `decompose.propose`/`from_cuts` akzeptieren `kind='modul'`: eine feste
  Platzierung an der Workstation statt Suche je Zelle; Verfeinerung
  zusätzlich gegen max. Länge/Höhe.
- Der Druckjob erhält optionale Felder für max. Modullänge/-höhe und die
  Dichte-Referenz; `kind` existiert bereits.
- Der Viewer bekommt die Druckort-Ansicht (Einbauort ↔ Druckort) am
  fokussierten Modul; Trajektorien/Export je Modul laufen im
  Workstation-Frame — die Naht aus #77/#79 wird damit geschlossen.
- Das Glossar wurde geschärft (Platzierung, Zerlegung, Workstation in
  `core/CONTEXT.md`; Teil, Teile-Palette, Gilt-für-Umschalter,
  Druckort-Ansicht in `viewer/CONTEXT.md`).

## Nachtrag 2026-07-09 — Absolute Aufstellhöhen bei Art „Abschnitt" (Issue #132)

Revidiert die **abschnitts-lokale Höhen-Konvention** der Abschnitts-Platzierung
(Punkt 2 sprach von „rechnerisch identisch" — für die *Höhe* stimmte das nur an
der untersten Reihe). Bisher bewertete `Section.as_surface` jeden Abschnitt als
Mini-Wand ab `z = 0`, und `stand_height_mm` war relativ zum Abschnittsfuß — der
Boden-Modus (`stand_mode="floor"`, #81) klemmte damit auf ein **Phantom-Podest
am Abschnittsfuß**: obere Reihen meldeten 100 % Erreichbarkeit, die ein M1013
(Reichweite 1300 mm) vom Boden nie erreicht (Design-Log 2026-07-09, Grill).

Neu (Design-Log 2026-07-09 „Grill: Platzierungsmodell nach Zerlegung"):

- **`stand_height_mm` ist überall absolut über dem Boden** (Boden = Wandfuß
  `z = 0`) — Artefakte, freie Overrides (#94), UI. `lateral_mm`/`standoff_mm`
  bleiben abschnittsrelativ (Abschnittsmitte/Wandfront).
- **Suche + Bewertung sehen die echte Höhenlage:** die `WallSurface` trägt ein
  `z_offset_mm` (Default 0.0 = alte Konvention), `Section.as_surface` setzt es
  auf `z0_mm`; IK-Ziele liegen auf `z0..z1` absolut, die Basis auf
  `stand_height_mm` absolut. Boden-Modus ⇒ Höhensatz `[0]` absolut; erhöht ⇒
  realer Workstation-Satz (`base_heights_mm`/`height_range_mm`) bzw.
  Fallback-Raster 0–3000 mm — alles absolut.
- **Eine Umrechnungsnaht:** das abschnitts-lokale Sim-Frame (Toolpath/Mesh mit
  z ab Abschnittsfuß) entsteht in der Setup-Komposition
  (`fgc.pipeline.actions._planned_setup`, Parameter `z_offset_mm`):
  `stand_height_local = stand_height_abs − z0`, negativ erlaubt.
- **Art „Modul" bleibt unberührt:** die feste Workstation-Platzierung ist
  weiterhin relativ zur Arbeitsfläche (der Modulfuß liegt auf ihr — dieser
  ADR-Kern gilt unverändert); `as_surface(..., z_offset_mm=0.0)`.
- **Befund, kein Gate:** im Boden-Modus unerreichbare obere Reihen werden
  weiterhin geschnitten — die Ampel (`fgc.decompose.evaluate`) sagt jetzt die
  Wahrheit (rot/teilerreichbar statt fälschlich grün).
- **Rückwärtskompatibilität:** für die unterste Reihe (`z0 = 0`) ist absolut ≡
  lokal — Platzierung, Bewertung und Trajektorie sind bit-identisch zu vorher
  (Regressionsanker in `core/tests/test_decompose.py` /
  `test_section_simulation.py`); Altprojekte (durchweg `stand_height 0`) laden
  byte-gleich und bedeuten fortan korrekt „Boden".

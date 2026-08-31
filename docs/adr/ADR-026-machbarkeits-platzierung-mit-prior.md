# ADR-026 — Platzierungsvorschlag optimiert Machbarkeit; Messwissen als Prior-Tabelle

Status: angenommen · 2026-07-22 (Tobias-Entscheidung nach Grilling-Session,
ausgelöst durch die Sweep-Studien `experiments/collision_standoff_sweep`:
der automatische Vorschlag ist voll erreichbar, aber tief kollidierend)

## Kontext

`placement.suggest` optimierte allein die **Erreichbarkeit** (voller
erreichbarer Anteil → Min-Marge → Mean-Marge, Issue #98). Kollision war ein
optionaler Grob-Check (Issue #131, „Befund, kein Gate"), der in der
Standardkonfiguration (`collision_free=None`) **nicht lief**. Die Messstudien
belegen die Konsequenz quantitativ:

- Der automatische Vorschlag (standoff 230 mm, denkmal Modul 1) ist voll
  erreichbar, aber tief kollidierend (Durchdringung bis −258 mm, ~8000 rote
  Samples). Kollisionsfreiheit und Erreichbarkeit sind im Abstand
  **gegenläufig**; für hohe Module existiert gar kein gemeinsames Fenster.
- Zwei ungenutzte Hebel sind quantifiziert: **IK-Konfiguration** modulweit
  (Konfig `baa`: +80 % machbare Bandhöhe gegenüber auto) und **Podesthöhe**
  (~300 mm: +150 mm; nicht monoton — 600 mm kippt). Der Gewinner verschiebt
  sich mit dem Setup (nie hartkodieren).
- Das kontrollierte W×T-Prädikat-Gitter (`data_grid/`, synthetische Quader)
  liefert H_max und Best-Setup (Abstand, Basishöhe, IK-Konfig) je
  (Breite, Dicke) — gemessen am Doosan M1013 mit dem denkmal-Tool, also
  **roboter- und werkzeugspezifisch**, und mit nicht-monotonen Effekten.

## Entscheidung

**1. Machbarkeit statt Erreichbarkeit.** `suggest` optimiert kollisionsfrei
**und** erreichbar. Der Grob-Check (#131) läuft standardmäßig — als zweiter
**Vorfilter vor** der teuren `evaluate`-Schleife (symmetrisch zur
Reichweitenkarte #214, gleiches Fail-soft: streicht der Filter alle, wird
trotzdem bewertet). Das Kollisionsurteil bleibt vorderster Sortierschlüssel
**und** wird explizites Feld im Score („Befund, kein Gate" — keine leeren
Vorschlagslisten).

**2. „Kein machbarer Kandidat" ist das Zerlegungs-Signal — lose gekoppelt.**
`suggest` ruft den Zerleger nie selbst; Pipeline/Viewer erkennen den Befund
und bieten den vorhandenen Zerlegungs-Trigger (#221/#222) an. Vorbeugend
gehört die Platzierbarkeit in die Zerlegungs-Zielfunktion (laufender Track);
der Placement-Befund ist Sicherheitsnetz und Auslöser.

**3. Messwissen als versionierte Prior-Tabelle, die lenkt und nie urteilt.**
Die kompakte W×T-Zusammenfassung wird Datenartefakt im Core, geschlüsselt auf
**Roboter + Tool**, mit ADR-004-Provenienz (Herkunfts-Commit,
Gitter-Parameter — Muster des Surrogat-Ausweises #219). Die „Funktion" ist
konservative Interpolation über die Stützstellen (kein Fit — die Effekte
haben Knicke). Der Prior formt nur die Suche: Abstands-Raster verdichten,
Konfig-Shortlist ordnen. Geurteilt wird immer auf der echten Geometrie
(Grob-Check + `evaluate`). Fehlender/unpassender Eintrag → neutraler Prior,
Suche wie ohne. Abgebrochene Messzellen gehen als `angenommen-unmachbar` mit
ehrlichem Status in die Tabelle, nie als erfundener Messwert.

**4. Tool-Toleranz = konfigurierte Sicherheitszone.** Der Prior gilt auch für
ein nicht vermessenes Tool, wenn ‖Δ TCP-Versatz‖ **und** Δ Hüllmaß ≤ der in
der GUI eingestellten `safety_distance_mm` liegen. Das Hüllmaß wird beim
Upload einmalig aus dem Mesh berechnet und additiv im Tool-Artefakt
gespeichert (Migrationslogik wie `compatible_robots`, #71: fehlt das Feld →
„unbekannt" → neutraler Prior). Keine eigene Toleranz-Konstante.

**5. IK-Konfiguration wird Suchachse — prior-geführt.** Je Kandidat werden
die Prior-Konfig(s) plus `auto` bewertet (`config_filter`, #129/#200);
findet die Shortlist nichts Machbares, eskaliert die Suche einmalig auf alle
8. Die gewählte Konfig ist Teil des Vorschlags nach außen — Bewertung,
Simulation und Druck fahren dieselbe Konfig.

**6. Harter neuer Default, kein Legacy-Schalter.** Das alte Verhalten ist
durch Messung als falsch belegt; Tests/Goldens werden im selben Zug
aktualisiert. Für Forschungs-Vergleiche bleibt der Altzustand über die
vorhandenen `suggest`-Parameter **explizit konstruierbar** — es gibt keinen
benannten Produktions-Schalter zurück.

## Konsequenzen

- Die Standardvorschläge ändern sich absichtlich — Bruch der
  Byte-Gleichheits-Linie von #214/#219, dokumentiert statt versteckt.
- Viewer: Kollisions-Ampel je Vorschlag + Absprung auf den
  Zerlegungs-Trigger. Der Core liefert die Einstufung fertig mit — der
  Viewer rechnet nichts, es entsteht keine neue Zwillingsfunktion
  (Paritäts-Manifest unberührt).
- Tool-Schema wächst additiv um das Hüllmaß-Feld; Prior-Tabelle ist ohne
  Codeänderung regenerierbar (neue Messläufe ersetzen Annahmen).
- Offene Folgearbeiten (Issues): fehlende W×T-Zellen nachmessen (Läufe
  brachen nativ ab — vermutlich derselbe 0xC0000005-Crash wie bei der
  505-mm-Wand der Dicken-Studie), Tool-TCP-Studie (aufgeschoben).

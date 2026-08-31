# Viewer (fgc-viewer)

TypeScript-Viewer des FGC-Planners: Abspieler der Core-Artefakte (ADR-007,
eingeschränkt durch ADR-014) und — mit dem GUI-Ausbau 2026-07 — die
Prozess-Oberfläche über der Core-API. Dieses Glossar fixiert die Sprache der
GUI-Konzepte; die Pipeline-Begriffe (Projekt, Druckjob, Platzierung,
Zerlegung, …) leben in `core/CONTEXT.md`.

## Language

**Reiter**:
Einer der Schritte des GUI-Prozesses — Projekt, Roboter, **Zerlegung**,
Druckplan, Export (der frühere Reiter Simulation ist seit #86 als Modus
„Simulieren" im Druckplan absorbiert; seit dem Druckplan-Split Scheibe 4 / #106
ist die Zerlegung ein eigener Reiter, der bisherige Reiter Druckplan behält
übergangsweise die Slicing-Rubrik, bis #107 sie als „Slicing" herauslöst).
Reiter sind *Navigation, kein Zwangspfad*: Zurückspringen
ist immer erlaubt; Änderungen an vorgelagerten Reitern markieren
nachgelagerte Stände als **veraltet**, löschen sie aber nicht.
_Avoid_: Wizard-Schritt (der Konsolen-Wizard `fgc start` ist ein anderer,
linearer Einstieg), Seite

**Bibliothek**:
Der Bereich außerhalb des Prozesses für projektunabhängige Stammdaten —
v. a. der Endeffektor-Konfigurator (`tools/`). Im Prozess (Reiter Roboter)
wird nur *ausgewählt*, gepflegt wird in der Bibliothek.
_Avoid_: Einstellungen (das sind App-Präferenzen), Konfigurator (das ist die
eine Funktion darin)

**veraltet**:
Der Zustand eines nachgelagerten Arbeitsstands (z. B. Zerlegung, Simulation),
dessen vorgelagerte Grundlage sich geändert hat (anderer Roboter, andere
Wand). Veraltete Stände bleiben sichtbar und werden markiert — konsistent zum
Prinzip „Befund, kein Gate" der Eignungsprüfung.
_Avoid_: ungültig, gelöscht

**Übernahme-Protokoll**:
Die feste Nachzieh-Sequenz nach jeder Core-Antwort mit frischen
Druckjob-Daten: aktiven Druckjob übernehmen, Panels versorgen,
Override-Marker der **Teile-Palette**, **veraltet**-Badges, ggf.
Neubewertung — eine Reihenfolge als getesteter Vertrag; bewusste
Abweichungen sind benannte Optionen, keine stillen Varianten.
_Avoid_: Refresh (zu generisch), Panel-Sync (das ist die
Fokus-Synchronisation)

**Darstellungsmathematik**:
Rechnung, die der Viewer selbst ausführen darf (ADR-007-Klarstellung
2026-07-04): Zeit-Interpolation und **Präsentations-FK** (Gliedstellungen aus
`joints_rad` für das Arm-Replay; per Testorakel gegen die Core-FK validiert).
Alles Urteilende (Erreichbarkeit, Bewertung, Warnungen) kommt weiterhin als
Core-Artefakt.
_Avoid_: Fachlogik, Berechnung (zu unspezifisch)

**Teil**:
GUI-Sammelbegriff für ein Element der Zerlegung eines Druckjobs — je nach
Zerlegungsart ein *Abschnitt* oder ein *Modul* (core/CONTEXT.md). UI-Texte
nennen die konkrete Art, sobald sie feststeht („Abschnitte", „Module").
_Avoid_: Objekt, Bauteil (mehrdeutig — die IFC-Wand ist das Bauteil)

**Teile-Palette**:
Die ein-/ausklappbare Leiste am 3D-Feld des Druckplans mit allen Teilen des
Druckjobs: je Teil Ampel, Name, erreichbarer Anteil und ein Marker ▪, sobald
das Teil individuelle Overrides trägt (Slicing oder Platzierung). Auswahl in
der Palette und Fokus in der 3D-Ansicht sind beidseitig synchron.
_Avoid_: Objektliste, Abschnittsliste

**Gilt-für-Umschalter**:
Der Geltungsbereichs-Schalter im Druckplan-Aside (Global ↔ gewähltes Teil,
OrcaSlicer-Vorbild): auf „Teil" gestellt zeigen dieselben Formulare die
geerbten Werte, jede Eingabe wird zum sparsamen, feldweisen Override (↺ setzt
das Feld auf global zurück). Strukturelle Einstellungen (Zerlegungsart,
Schnittplan, Aufstellung, Modulgrenzen) bleiben dabei ausgegraut — sie
*erzeugen* die Teile erst und können nicht je Teil gelten.
_Avoid_: Override-Modus, Objekt-Einstellungen (es gibt kein eigenes Menü)

**Druckort-Ansicht**:
Ansichts-Umschalter am fokussierten Modul (Einbauort ↔ Druckort): Druckort
blendet die Szene auf die Workstation um — Workstation-Mesh, Roboter an
`robot_base_frame`, Modul auf der Arbeitsfläche; Modul-Simulationen spielen
dort. Bei Abschnitten entfällt der Umschalter (Einbauort = Druckort).
_Avoid_: Stationsansicht

**Modellübersicht**:
Die 3D-Ansicht des Gesamtmodells (`model.glb` + `model_map.json` +
`candidates.json` eines walls-list-Laufs), nach Eignungsbefund eingefärbt,
mit klickbarer Wand-Auswahl — künftig inklusive Gebäudekontext
(Nicht-Wand-Elemente, halbtransparent).
_Avoid_: Szene, Gesamtansicht

**Wand-Fokus**:
Der Sicht-Zustand des geteilten 3D-Felds ab dem Reiter *Zerlegung* (weiter in
*Slicing* und *Export*): es zeigt standardmäßig **nur die gewählte Wand**, die
übrigen Wände der Modellübersicht und der Gebäudekontext-Geist treten zurück.
Das schwebende **Viewer-Einstellungen**-Menü (⚙, rechts oben am 3D-Feld) blendet
über „Gebäude/Kontext einblenden" die Umgebung wieder blass ein — ein
Sicht-Schalter, kein Fachzustand (ADR-007). Ohne gewählte Wand entfällt der
Fokus (nichts zu isolieren); der Reiter *Projekt* bleibt Modellübersicht.
_Avoid_: Isolation, Einzelwand-Modus

## Relationships

- Ein **Reiter** zeigt immer den Stand eines *Druckjobs* (core/CONTEXT.md);
  persistiert wird ausschließlich über die Core-API ins `project.json` —
  der Viewer hält keinen Fachzustand (ADR-007/014/016).
- Die **Bibliothek** pflegt Artefakte (`tools/`), die *Projekte* nur
  referenzieren.
- **Darstellungsmathematik** konsumiert Artefakte, erzeugt aber nie welche.

## Example dialogue

> **Dev:** „Der Nutzer hat im Reiter Roboter den Endeffektor gewechselt —
> lösche ich dann die Zerlegung?"
> **Domain expert:** „Nein. Der Druckplan wird als **veraltet** markiert und
> bleibt sichtbar; die Ampeln je Abschnitt werden erst nach der Neubewertung
> durch den Core wieder scharf. Gelöscht wird nur auf ausdrücklichen Wunsch."

## Flagged ambiguities

- „Simulation" meint im Viewer das *Abspielen* der `trajectory.json`
  (kinematisches Replay); das *Erzeugen* der Trajektorie heißt weiterhin
  Simulation im Core-Sinn (`fgc simulate`). Im UI-Text deshalb „Simulation
  abspielen" statt „simulieren", wenn das Replay gemeint ist.

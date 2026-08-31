# Design-Log

Chronologisches Entscheidungstagebuch des Projekts — die Rohdaten für das
spätere Paper (Methodikkapitel, „design rationale"). Jeder Eintrag hält fest:
**Frage, erwogene Alternativen, Entscheidung, Begründung**, plus Verweis auf
ein ADR, wenn die Entscheidung Architekturrang hat.

> **Zur Veröffentlichung:** Dies ist das unveränderte Arbeitstagebuch der
> Entwicklung. Einige Einträge verweisen auf interne Arbeitsdateien des
> Entwicklungs-Repositorys (Statusdatei, Werkzeug-Konfiguration, Issue-Nummern),
> die hier nicht mit abgelegt sind. Einträge werden grundsätzlich nicht
> nachträglich umgeschrieben — Korrekturen stehen als neuer Eintrag darin.

Regeln:

- Jede Designentscheidung — auch kleine (Parameterwahl, verworfene Ansätze,
  Namenskonventionen) — bekommt zeitnah einen Eintrag. Verworfene Wege sind
  genauso wertvoll wie gewählte.
- Große Entscheidungen bekommen zusätzlich ein ADR unter `docs/adr/`;
  das Log verweist dann nur kurz darauf.
- Neue Einträge unten anfügen, bestehende nie umschreiben (Korrekturen als
  neuer Eintrag mit Verweis).

---

## 2026-06-10 — Fundament (Nachtrag, Details in den ADRs)

Die Grundsatzentscheidungen der Startphase, je als ADR dokumentiert:

- **ADR-001** Hybrid: Python-Kern + TypeScript-Viewer (statt reinem Python- oder Web-Stack).
- **ADR-002** Kinematik selbst portieren, Herstellertools (Robots) nur als Testorakel.
- **ADR-003** Vorwärtsmodell + Pareto-Suche statt Inversion des Prozessmodells.
- **ADR-004** Dateibasierte Artefakt-Pipeline: ein Laufordner je Lauf, JSON-Artefakte mit Schema + Provenienz statt In-Memory-Kopplung.
- **ADR-005** Geometrie-Kernel Mesh-basiert (trimesh/shapely), nicht BRep — ausdrücklich revisionsfähig.
- **ADR-006** Einheiten (mm), Frames (Quaternion w-first), genau eine Transformationsstelle beim IFC-Import.
- **ADR-007** Viewer ist zustandsloser Abspieler, rechnet nichts. *(2026-07-02 teilweise revidiert → ADR-014.)*
- **ADR-008** Konfigurationsraum deklarativ (Karten/JSON statt Code).
- **ADR-009** Drei Testorakel (analytisch, Hersteller-Sim, Hardware).
- **ADR-010** Lizenz- und Provenienzregeln (Status: vorgeschlagen).

## 2026-06-10 … 2026-06-30 — Spikes S1–S4 (Nachtrag, Details in docs/spikes/)

- **S1/S1b** Analog-IO-Ansteuerung Doosan (AO) und KUKA (ANOUT) erprobt.
- **S2** Tessellation IFC→Mesh gegen Beispielmodell geprüft; Settings `USE_WORLD_COORDS` + Default-Toleranzen festgelegt (vorläufig grün).
- **S3** IK-Roundtrip validiert.
- **S4** Offset-Robustheit (shapely-Buffer) untersucht; Extras scipy/networkx/rtree als Laufzeit-Abhängigkeiten von `trimesh.section()` identifiziert.

## 2026-07-02 — Grill-Session Pipeline-Semantik (Nachtrag)

- **ADR-011** IO als logische Kanäle im Toolpath (E2).
- **ADR-012** Totzeit-Kompensation gehört in `simulation`, t_tot ins Setup (E3).
- **ADR-013** Eignungsprüfung E1 zweistufig; fehlende Psets ⇒ provisorisches Bestehen statt Ablehnung.

## 2026-07-02 — Interaktiver Einstieg `fgc start` (Grill-Session)

**Frage:** Der Programmstart ist umständlich (venv aktivieren, Pfade und
GlobalIds abtippen, Viewer separat starten). Wie vereinfachen?

**Alternativen:** (a) nur Wrapper-Skript für die bestehende CLI, (b) ein
Kombi-Befehl slice+view, (c) interaktiver Wizard, der durch Modell- und
Wandauswahl führt.

**Entscheidung:** (c) — Wizard als eigenes Subkommando `fgc start`
(nacktes `fgc` zeigt weiterhin die Hilfe; die skriptbaren Befehle
`walls list`/`slice` bleiben unverändert für Tests und Automatisierung).
Einzelentscheidungen aus der Grill-Session:

- **IFC-Suche:** `examples/` (rekursiv) + Startverzeichnis (flach), Auswahl
  per Nummer. Verworfen: Config-Suchpfade (zu viel Maschinerie für M0),
  Zuletzt-benutzt-Historie (persistenter Zustand).
- **Wandliste:** nummeriert, mit E1-Eignungsurteil je Wand; auch ungeeignete
  Wände wählbar (Warnung, wie `fgc slice`) — fürs Forschungsprojekt sind
  gerade die problematischen Wände interessant. Verworfen: nur geeignete
  anzeigen; Liste ohne Prüfung.
- **Innen/außen-Filter:** aus `Pset_WallCommon.IsExternal`, das dafür neu in
  den IFC-Import aufgenommen wurde; fehlender Wert ⇒ Gruppe „unbekannt".
- **Slice-Parameter:** keine Rückfragen, Defaults aus dem Prozessfenster.
  Der Wunsch, Parameter interaktiv zu variieren, wandert in den Viewer
  (→ ADR-014), nicht in den Wizard.
- **Viewer öffnen:** Wizard startet den Vite-Dev-Server bei Bedarf selbst
  (inkl. einmaligem `npm install`) und öffnet den Browser mit der
  `?run=`-URL. Verworfen: nur URL ausgeben (genau der Handgriff, der weg
  sollte).
- **Wrapper `fgc.cmd`** im Repo-Root, nutzt die `.venv` ohne Aktivierung;
  ohne Auto-Setup (bei fehlender venv nur klare Anleitung). *Annahme nach
  Frage-Timeout — von Tobias zu bestätigen.*
- **Schnitt:** Wizard = reine Dialogführung (`pipeline/wizard.py`);
  Artefakt-Schreiben in `pipeline/actions.py` (gemeinsam mit CLI, später
  API), Formatierung in `pipeline/report.py`, Viewer-Start in
  `pipeline/viewer_launch.py`.

## 2026-07-02 — Parameter-Variation im Viewer ⇒ lokale Core-API (ADR-014)

**Frage:** Slicing-Parameter sollen künftig im Viewer variiert werden können.
Das kollidiert mit ADR-007 („Viewer rechnet nichts").

**Alternativen:** (a) aufschieben und nur notieren, (b) ADR-007 jetzt
revidieren und eine lokale Core-API planen, (c) Kompromiss Wizard-Schleife
(„nochmal mit anderen Parametern?").

**Entscheidung:** (b) — ADR-007 wird revidiert; der in ADR-007/ADR-001
vorgesehene Revisionstrigger („FastAPI-Wrapper statt Logik im Viewer") gilt
als ausgelöst. Kern der Folgeentscheidung: Die API bleibt ein dünner Wrapper
um dieselbe Pipeline und **schreibt weiterhin Laufordner** (ADR-004 bleibt
unangetastet, jeder Klick im Viewer bleibt als provenienter Lauf
reproduzierbar — wichtig fürs Paper). Verworfen: API liefert Artefakte nur
in-memory (Provenienz-Lücken); Hybrid mit Opt-in-Speichern (zwei Codepfade).
Umsetzung als eigenes Issue, heute nur die Entscheidung. → **ADR-014**

## 2026-07-02 — Doku-Struktur: README als Handbuch + dieses Design-Log

**Frage:** Wo leben Funktionsdoku und Entscheidungswege dauerhaft?

**Entscheidung README:** Die Root-README ist das Benutzerhandbuch — ein
Abschnitt je Funktion, Pflegeregel „ohne README-Abschnitt ist ein Feature
unfertig". Verworfen: separates `docs/manual.md` (zwei Orte), README je
Paket (kein Ort zeigt den Gesamtworkflow).

**Entscheidung Design-Log:** ADRs bleiben die formale Quelle für
Architekturentscheidungen; dieses Log fängt chronologisch *alle*
Entscheidungen inkl. Alternativen und verworfener Wege ab. Verworfen:
Mini-ADRs für alles (zu schwergewichtig, keine Chronologie), ein
konsolidiertes Gesamtdokument (ADR-Struktur ginge verloren).
Sprache Deutsch (konsistent zur übrigen Doku, Übersetzung fürs Paper ist
trivial); bestehende Entscheidungen kompakt rückwirkend nachgetragen
(siehe oben). *Sprache + Nachtrag: Annahmen nach Frage-Timeout — von Tobias
zu bestätigen.*

## 2026-07-02 — Spike S4 abgeschlossen: Druckbarkeitsregeln aus Offset-Sweep

**Frage:** Welche konkreten Zahlen (Mindestinnenradius, Mindeststegbreite,
Mindestwinkel, join_style/mitre_limit) sollen in
`materialcards/process_window.provisional.json` für E1-Stufe 2 und den
Slicer stehen? Der frühere Nachtrag-Eintrag „S4 … untersucht" (Abschnitt
„2026-06-10 … 2026-06-30") war unpräzise — es gab noch keine Zahlen, nur
Voruntersuchungen zu Laufzeit-Abhängigkeiten.

**Vorgehen:** Sechs parametrische Testkonturfamilien
(`docs/spikes/s4_scripts/contours.py`) über 4 Schalen (k=0..3, Inset =
(0.5+k)×w) und 5 join_style/mitre_limit-Kombinationen geswept
(`offset_stress.py`); Degenerationen (leer, invalid, MultiPolygon-Zerfall,
Sliver, Roundtrip-Verlust) klassifiziert. Kontrollkontur `wall_segment`
zeigte ausschließlich erwartetes, sauberes Verschwinden (kein Bug in der
Sweep-Pipeline).

**Zusätzlich zum Plan gebaut:** Neben der geplanten `wedge`-Familie (konvexe
Spitze, Innenwinkel 90–15°) wurde eine `notch`-Familie (konkave
Reflex-Kerbe, gleicher Winkelbereich) ergänzt. Grund: an konvexen Spitzen
hat `mitre_limit` beim Erodieren (negativer Buffer) nachweislich **keinen**
Einfluss (identische Flächen für mitre_limit 1/2/5) — das eigentliche
„Mitre-Spike"-Risiko, das der Plan mit dem mitre_limit-Sweep prüfen wollte,
tritt nur an konkaven (Reflex-)Ecken auf. Ohne die Ergänzung hätte der
join_style/mitre_limit-Teil der Fragestellung keine Datengrundlage gehabt.

**Ergebnis (Details/Begründung: `docs/spikes/S4_offset_robustheit.md`):**
Mindestinnenradius 0.5×w, Mindeststegbreite 1.5×w (für 1 Schale, Formel für
mehr Schalen im Protokoll), Mindestwinkel 30° (bindend: konvexe Spitze, nicht
die Kerbe), empfohlen `join_style="mitre"` mit `mitre_limit=2.0`.

**Wichtiger Fund:** `core/src/fgc/slicer/shells.py` ruft `buffer(-inset,
join_style="mitre")` **ohne** explizites `mitre_limit` auf → shapely-Default
5.0. Bei diesem Wert zerfällt die Kontur an Reflex-Kerben ≤30° (ab Schale
k=3) bzw. ≤15° (schon ab k=2) nachweislich in ein MultiPolygon (echtes
Topologie-Artefakt, nicht nur Flächenverlust) — von `_as_polygons()` zwar
defensiv abgefangen, aber mit Maßhaltigkeitsverlust. **Kein Fix in diesem
Spike** (out of scope, `core/src/` bleibt unangetastet); Empfehlung als
Folge-Issue: `mitre_limit=2.0` explizit setzen.

**Verworfen:** pyclipper-Vergleich (keine unerklärlichen shapely-Artefakte
aufgetreten, das MultiPolygon-Verhalten ist durch die Mitre-Geometrie exakt
erklärbar); U-Formen für die Steg-Familie (Rechteck-Hantel reicht, gleicher
Degenerationsmechanismus).

**Einschränkung:** Alle Zahlen normiert in Strangbreiten w (w selbst noch
unbekannt, S1 offen) — `process_window.provisional.json` bleibt
`provisional: true`, bis S1/S1b mm-Werte liefern.

## 2026-07-02 — Statusdatei `docs/status.md` als LLM-Einstieg

**Frage:** Agenten (und Menschen) mussten den Projektfortschritt bei jedem
Sessionstart aus Plan, Design-Log, Spike-Protokollen und Issues
zusammensuchen. Wo lebt der aktuelle Stand?

**Alternativen:** (a) keine eigene Datei — Fortschritt bleibt aus Git-Historie
und Issues ableitbar; (b) Status-Abschnitt oben im Umsetzungsplan; (c) eigene
Datei `docs/status.md`.

**Entscheidung:** (c) — eigene, bewusst kurze Datei mit Statustabelle
(Phasen/Spikes/Issues), „Was als Nächstes" und Einstiegspunkten; in
`CLAUDE.md` als Pflichtlektüre beim Sessionstart verankert. Pflegeregel:
wird im selben Commit aktualisiert, der einen Meilenstein/Spike/ein Issue
abschließt oder öffnet; sie beschreibt nur den Ist-Zustand — Historie bleibt
im Design-Log, Entscheidungen in ADRs, Aufgaben in Issues. Verworfen:
(a) genau das Suchproblem; (b) vermischt stabilen Plan mit volatilem Status
und macht Plan-Diffs unleserlich.

## 2026-07-02 — Produktionsrisiko aus Spike S4 gefixt: `mitre_limit=2.0`

**Frage:** Spike S4 hatte ein Produktionsrisiko gefunden: `shell_rings()`
(`core/src/fgc/slicer/shells.py`) ruft `polygon.buffer(-inset,
join_style="mitre")` ohne explizites `mitre_limit` auf, also den
shapely-Default 5.0 — genau der Wert, bei dem der Spike MultiPolygon-Zerfall
an scharfen konkaven Reflex-Kerben nachweist. Welcher `mitre_limit`-Wert soll
im Produktionscode stehen?

**Alternativen:** Default 5.0 belassen (Status quo, per Spike widerlegt);
`mitre_limit=1.0` (praktisch durchgehend Bevel, kein Zusatznutzen gegenüber
2.0 laut Spike-Messreihe); `mitre_limit=2.0`; `join_style="round"` statt
Mitre (größerer Eingriff, im Spike nicht als nötig ermittelt).

**Entscheidung:** `mitre_limit=2.0`, explizit im `buffer()`-Aufruf gesetzt.

**Begründung:** Bei Default 5.0 zerfällt die Kontur nachweislich ab
Kerbwinkel ≤30° (Schale k=3) bzw. ≤15° (schon ab k=2) in ein MultiPolygon —
die Mitre-Spitze löst sich als eigene Teilfläche ab, ein echtes
Topologie-Artefakt. Mit 2.0 bleibt der Join bis exakt 60° Kerbwinkel
„echtes" Mitre und fällt darunter automatisch auf bevel-ähnliches Verhalten
zurück; im gesamten getesteten Bereich (15°–90°, 4 Schalen) trat weder
Zerfall noch Invalidität auf, nur geringfügig höherer Flächenverlust an sehr
spitzen Kerben. `mitre_limit=1.0` wäre noch konservativer, entspricht im
Testbereich aber praktisch durchgehend Bevel — kein Zusatznutzen gegenüber
2.0.

**Umsetzung:** Fix in `shells.py` (Kommentar verweist auf S4-Protokoll) plus
Regressionstest in `core/tests/test_slicer.py`
(`test_shell_rings_survive_sharp_reflex_notch`), der eine 15°-Reflex-Kerbe
nachbaut (analog zur `notch`-Familie aus `docs/spikes/s4_scripts/contours.py`)
und per Kontroll-Assertion zeigt, dass der shapely-Default bei dieser Kontur
tatsächlich zu einem MultiPolygon zerfällt, während `mitre_limit=2.0` jede
Schale als einzelnen Ring liefert. Damit ist das im S4-Protokoll notierte
Folge-Issue erledigt — kein separates GitHub-Issue nötig.

## 2026-07-02 — E1-Stufe 2 (A): Dickenuntergrenze aus Strangbreite × Schalenlogik

**Frage:** Der Umsetzungsplan §1 definiert Stufe 2 als „Wanddicke im
Prozessfenster des Extruders (min./max. aus Strangbreite × Schalenlogik)".
Die Karte trägt aber noch keine mm-Grenzen (`strand_width_mm` ist null bis
S1). Woher kommt die Dickengrenze, und wie verhält sich `check_thickness`,
solange die Strangbreite fehlt?

**Alternativen:** (a) Weiter nur explizite mm-Grenzen aus der Karte prüfen
und ansonsten provisional überspringen (Status quo, ignoriert die
Schalenlogik des Plans); (b) Untergrenze fest verdrahtet aus einem
Default-mm-Wert (verletzt P4 — keine erfundenen Zahlen); (c) Untergrenze aus
der S4-Stegformel ableiten, sobald die Strangbreite gesetzt ist, explizite
mm-Grenzen behalten Vorrang.

**Entscheidung:** (c). `check_thickness` prüft explizite
`wall_thickness_min/max_mm` mit Vorrang; fehlt die Untergrenze, aber
`strand_width_mm` ist gesetzt, wird sie aus `w × (min_web_width_strand_widths
+ 2·(n−1))` abgeleitet (S4-Stegformel). Eine Obergrenze wird **nicht**
abgeleitet (S4 liefert dafür keine Zahl) — sie bleibt bei expliziten
mm-Werten. Solange `strand_width_mm` null ist, bleibt das Verhalten wie
heute: provisional übersprungen mit klarem Grund. Der Code-Pfad ist real und
schaltet scharf, sobald S1 die Strangbreite liefert.

**Begründung:** Eine Wand der Dicke t verhält sich beim Innen-Offset wie ein
gerader Steg — n Schalen bestehen, sobald t ≥ (2n−1)×w (S4). Die
Sicherheitsmarge steckt bereits im Kartenwert `min_web_width_strand_widths =
1.5` (= (2·1−1)+0.5×w, also +0.5×w = halbe Strangbreite für die 1-Schale);
je weitere Schale +2×w. Das reproduziert die S4-Tabelle exakt (1/2/3 Schalen
→ 1.5/3.5/5.5×w) und erfindet keine neue Zahl. Kein Obergrenzen-Fake: S4
untersucht Offset-Degeneration (untere Grenze), zu dicke Wände sind offset-
robust — eine Obergrenze wäre Pseudogenauigkeit.

**Schalenzahl-Herkunft:** n ist ein Slice-Parameter (`SliceParams.n_shells`,
Laufzeit/CLI), kein Kartenwert. E1 läuft aber vor dem Slicing und kennt die
spätere Schalenzahl nicht. Neues Kartenfeld `default_shells` (=2, deckt sich
mit dem `SliceParams`-Default) ist die für E1 angenommene Planungs-Schalenzahl
und bleibt die eine Quelle (ADR-013). `SliceParams` liest es bewusst noch
nicht (verdrahtet weiter seinen eigenen Default 2) — die Kopplung beider auf
`default_shells` ist ein späterer, eigener Aufräumschritt, hier
scope-vermeidend ausgelassen.

## 2026-07-02 — E1-Stufe 2 (B): Grundriss-Geometriechecks ohne Grundriss-Quelle in v1

**Frage:** Die S4-Geometrieregeln (Mindest-Innenwinkel 30°, Mindeststegbreite,
Mindestinnenradius 0.5×w) brauchen einen Grundriss-Polygon. `WallData` hat
keinen — nur Skalare (Länge/Höhe/Dicke/Planarität). Woher kommt der Grundriss,
und was tut die Regel für v1-Wände?

**Alternativen:** (a) Grundriss im Mesh schneiden — die Funktion dafür lebt in
`slicer/sections.py`, das hieße eine Abhängigkeit `eligibility→slicer`
(Architekturrang → ADR) oder die Schnittfunktion in ein neutrales Modul
extrahieren (Über-Refactoring gegen die Modularitätsregel); (b) den Grundriss
provisorisch aus dem Mesh selbst nachbauen (Duplizierung von `sections.py`);
(c) die Geometriechecks als reine, einzeln getestete Funktionen bauen und über
einen optionalen `footprint`-Slot im Kontext anbinden — fehlt der Grundriss
(v1), läuft die Regel provisional durch.

**Entscheidung:** (c). Neues Modul `core/src/fgc/eligibility/footprint.py` mit
reinen shapely-Funktionen (`min_convex_interior_angle_deg`, `has_narrow_web`,
`min_web_width_mm`), ohne Projekt-Imports. Neue Registry-Regel `check_footprint`
wendet sie auf `ctx.footprint` an; ist keiner gesetzt (v1: `WallData` liefert
keinen), passiert der Check provisional mit klarem Grund. Der Mindestinnenradius
0.5×w wird **nicht** als harter Check umgesetzt — ohne Krümmungsanalyse
(Kreisbogen-Fitting je Ecke) wäre jede Zahl Pseudogenauigkeit; dokumentiert
offen im Modul-Docstring.

**Begründung:** Der v1-Scope sind ebene, öffnungslose Rechteckwände (ADR-005) —
90°-Ecken, keine spitzen Winkel oder Stege im Grundriss; ein Grundriss-Check
würde sie ohnehin bestehen. Die Prüf-Logik ist trotzdem real und vollständig
gegen synthetische Polygone getestet (spitzer Winkel <30° fällt durch, 30°
besteht, schmaler Hals zerfällt im Erosionstest). Damit bleibt E1 modular und
slicer-frei (kein neues ADR nötig, ADR-013-Rahmen gewahrt), ohne Scheinlösung.
Der Winkelvergleich trägt 0.5° Toleranz gegen Tessellierungs-/Rundungsrauschen,
damit der Grenzfall 30° besteht. Das Anbinden einer echten Grundriss-Quelle
(neutrales Schnittmodul **oder** bewusste `eligibility→slicer`-Abhängigkeit)
ist ein Folgeschritt mit eigener Entscheidung/ADR — erst wenn nicht-rechteckige
Grundrisse in Scope kommen.

**Namenskonvention/Konsequenz:** `footprint` ist ein neuer Prüfname —
aufgenommen in `CHECK_NAMES` (models.py), das candidates-Schema-Enum und die
Kartenfelder `min_convex_angle_deg` (=30, aus S4) und `default_shells`. Der
Check erscheint damit als provisorische Zeile in jedem `candidates.json`
(analog zu `thickness`), bis eine Grundriss-Quelle angebunden ist.

## 2026-07-03 — Architektur-Review: fünf Vertiefungs-Refactors (Übersicht)

Systematischer Review der Codebasis auf „seichte" Module (Schnittstelle so
komplex wie die Implementierung) und verstreute Konzepte, mit Blick auf den
kommenden dritten Einstiegspunkt (ADR-014-API). Fünf Kandidaten identifiziert
und alle umgesetzt — je Entscheidung ein Eintrag unten. Verhalten nach außen
unverändert (Ausnahme: neuer `summary`-Block in `toolpath.json`, Schema 0.2);
Testsuite von 52 auf 63 Tests gewachsen. Begleitend entstand `core/CONTEXT.md`
(Glossar der Core-Pipeline), auf das `CONTEXT-MAP.md` bereits verwies.

## 2026-07-03 — „Lauf" als Typ statt Konvention: `Run`-Objekt

**Frage:** Das Kernkonzept von ADR-004 — ein Lauf ist ein Ordner mit
provenienz-gestempelten, schema-validierten Artefakten — existierte nur als
Aufruf-Konvention: `create_run_dir` → `make_provenance` → Artefakt-Dict →
`write_artifact`, zweimal offen ausgecodet (actions.py, cli.py), `run_dir` und
`provenance` als lose Locals. Zudem baute jede Aufrufstelle den
Provenienz-`source`-String als freien f-String, der die argparse-Flag-Namen
nachbuchstabiert (Drift-Risiko bei Flag-Umbenennung).

**Alternativen:** (a) Status quo (Vier-Aufrufe-Sequenz je Aufrufer);
(b) `Run`-Objekt, das Ordner + Provenienz zusammen besitzt; für den
source-String: strukturierte Beschreibung vs. fertiger String.

**Entscheidung:** (b) — `Run.create(command, label, *, source, runs_dir)` legt
Ordner an und stempelt Provenienz genau einmal; `run.write(kind, artifact)`
validiert und schreibt. Der source-String wird von Buildern erzeugt, die bei
den argparse-Flags in `cli.py` co-lokalisiert sind (`slice_source`,
`walls_list_source`); `slice_to_run` nimmt den *fertigen* String — die
ADR-014-API hat kein argparse und baut ihren eigenen. Der Wizard nutzt
`slice_source` mit (Provenienz bleibt „die CLI-Zeile, die den Lauf
reproduziert"). Nebeneffekt: `candidates.json` bettet jetzt denselben
Provenienz-Stempel ein wie der Lauf (vorher zwei `make_provenance`-Aufrufe →
zwei Zeitstempel). Test-Seam: `runs_dir`-Injektion statt nur
`RUNS_DIR`-Monkeypatch — Läufe sind erstmals ohne Disk-Globbing testbar.

## 2026-07-03 — Aktionsschicht symmetrisch: `evaluate_walls`/`walls_to_run`

**Frage:** `pipeline/actions.py` (laut eigenem Docstring die gemeinsame
Schicht für CLI, Wizard und künftige API) enthielt nur `slice_to_run`. Die
`walls list`-Orchestrierung (Prozessfenster + Roboter laden, Wände evaluieren)
war in CLI und Wizard dupliziert; der „nicht druckgeeignet"-Warnblock war
byte-identisch an zwei Stellen; der Wizard-Slice-Pfad war ungetestet.

**Alternativen:** (a) Duplikation bis zur API-Umsetzung (Issue #1) stehen
lassen; (b) Aktionen jetzt bauen, API dockt später nur noch an.

**Entscheidung:** (b). `evaluate_walls(model_path, robot_name, *, walls=None)`
besitzt die Konfig-Beschaffung; der optionale `walls`-Parameter trägt beide
Fälle (alle Wände des Modells vs. vorgefilterte Teilmenge des Wizards) ohne
zweiten Codepfad. `walls_to_run` schreibt zusätzlich das candidates-Artefakt
und liefert die Kandidaten mit heraus (CLI druckt die Tabelle, ohne das eben
geschriebene JSON neu zu lesen). Reason-Formatierung als
`report.candidate_reasons`; die umgebenden `print`-Zeilen bleiben bewusst in
den Aufrufern (CLI → stderr, Wizard → stdout, unterschiedliche Nachsätze).
Wizard schreibt weiterhin kein `candidates.json`. Neuer Integrationstest
belegt: Wizard-Slice und CLI-Slice erzeugen für dieselbe Wand geometrisch
identische Toolpaths.

## 2026-07-03 — Artefakt-Serialisierung in die Domäne: `wallspec_artifact` + Toolpath-`summary`

**Frage:** (a) Jedes Artefakt hatte einen Konstruktor in der Domäne — außer
`wallspec`, dessen Dict (inkl. `schema_version`, Vertex-Rundung) inline in
`actions.slice_to_run` entstand. (b) `n_layers`/`n_targets`/`n_print` wurden
dreimal aus derselben Target-Liste abgeleitet (SliceRun-DTO, report, Viewer),
weil `toolpath.json` keinen Summary-Block trug.

**Alternativen:** Für (b): Viewer weiterrechnen lassen (Status quo, drei
Ableitungsstellen); Summary als optionales Feld (dann bleibt die Ableitung
überall nötig); Summary als Pflichtfeld mit Schema-Bump.

**Entscheidung:** `wallspec_artifact(...)` in `domain/models.py`, bewusst mit
primitiven Feldern statt `WallData` (keine `ifc_io`-Abhängigkeit der Domäne).
`Toolpath.summary()` berechnet die Kennzahlen genau einmal;
`Toolpath.to_artifact` schreibt sie als Pflichtfeld `summary`, Toolpath-Schema
gebumpt auf `0.2` (Schemas versionieren unabhängig, `const`-validiert; alle
anderen bleiben 0.1). `SliceRun` schrumpft auf `run_dir` + `Toolpath` +
`n_context` — die Anzeige-Zahlen waren Re-Berechnung auf der falschen Ebene.
Der Viewer liest `summary` statt zu rechnen (ADR-007), mit Fallback-Ableitung
für alte 0.1-Läufe (Viewer validiert nicht, alte Läufe bleiben abspielbar).

## 2026-07-03 — Schalenzahl-Kopplung + eine Heimat für die S4-Stegformel

**Frage:** Der im Eintrag „E1-Stufe 2 (A)" (2026-07-02) bewusst aufgeschobene
Aufräumschritt: `ProcessWindow.default_shells` (E1) und `SliceParams.n_shells`
(Slicer) waren zwei unabhängige `2`-Literale für ein Konzept — E1 hätte gegen
eine andere Schalenzahl prüfen können, als der Slicer druckt (verletzt das
„eine Karte"-Versprechen von ADR-013). Außerdem baute
`rules.check_thickness` die S4-Stegformel `min_web + 2·(n−1)` inline nach,
nur für den Begründungstext.

**Entscheidung:** `SliceParams.from_window` übernimmt `window.default_shells`
(explizite Overrides wie `--shells` gewinnen weiterhin); das Fallback-Literal
existiert nur noch einmal, in `PROVISIONAL_DEFAULTS["default_shells"]` —
derselbe Topf wie die übrigen „Slicer-v0-Defaults bis S1/S4". Die Formel
bekommt genau eine Heimat: `footprint.min_web_width_factor(min_web, n_shells)`;
Prüfung und Begründungstext rufen sie. Neuer Test pinnt das ADR-013-Versprechen
(synthetische Karte mit `default_shells=3` → Slicer sliced 3 Schalen UND E1
rechnet die Mindestdicke mit 3).

## 2026-07-03 — `SCHEMA_DIR`-Duplikat entfernt

**Frage:** `fgc/paths.py` nennt sich „die eine Stelle, die das Monorepo-Layout
kennt" — aber `domain/__init__.py` berechnete `SCHEMA_DIR` unabhängig, mit
anderem `parents[]`-Index (latenter Bug beim dokumentierten
Wheel-Install-Umzug).

**Entscheidung:** `domain/__init__.py` importiert `SCHEMA_DIR` aus `fgc.paths`
(Re-Export bleibt, kein Import-Zyklus — `paths.py` importiert nur `pathlib`).
Zwei hartcodierte Verzeichnistiefen → eine.

## 2026-07-03 — Doosan M1013 wird Primärplattform (revidiert §8.5 „Parität")

**Frage:** Grill-Session 2026-07-02 hatte KUKA zur gleichwertigen
Druckplattform erhoben — voller Ausbau beider Stränge (Spike + Kinematik +
Emitter + Trockenlauf) wäre aber ~die Hälfte von Phase 2 als Duplikat, vor
dem ersten echten Druck.

**Alternativen:** (a) Parität beibehalten (Zwei-Controller-Nachweis stärkt
Übertragbarkeits-Argument im Prozess-Paper); (b) Plattformwahl vertagen bis
Demonstrator-Größe feststeht; (c) Primärplattform jetzt festlegen.

**Entscheidung:** (c), Doosan M1013 — unter der Annahme, dass der
M3-Wandabschnitt in ~0,8–1,0 m Wandlänge passt (Doosan-Reichweite ≈ 1,3 m).
Beide Spikes S1/S1b bleiben (billig, entscheiden OD-1/OD-2, liefern t_tot
beider Aufbauten), aber danach wird nur der Doosan-Strang voll ausgebaut:
S3 portiert zuerst die Offset-Wrist, `DrlEmitter` zuerst scharf,
Trockenlauf/Validierung zuerst am M1013. KUKA bleibt Spike-validiert in
Reserve; `KrlEmitter`-Ausbau erst, wenn der Doosan-Strang am Gerät bewiesen
ist oder die Demonstrator-Größe KUKA erzwingt.

**Begründung:** Erfolgsbild ist Demonstrator + Papers, nicht Toolbreite;
Doosan-AO-Eigenheiten sind bereits bekannt (E2/ADR-011), DRL schlanker als
KRL inkl. Programmsplitting. Revisionstrigger: Messplan der Dissertation
verlangt Abschnitt > Doosan-Arbeitsraum.

## 2026-07-03 — Kalibrier-Workflow als Arbeitspaket in Phase 2

**Frage:** ADR-006 verspricht einen Kalibrier-/Registrierworkflow
(Wandnullpunkt antasten → Setup schreiben) „von Anfang an" — aber kein
Phasen-Arbeitspaket im Umsetzungsplan baut ihn; Phase 2 setzt das
Setup-Artefakt für Trockenläufe stillschweigend voraus.

**Alternativen:** (a) setup.json für M1 von Hand tippen, Workflow auf M3
vertagen; (b) kleines Arbeitspaket in Phase 2.

**Entscheidung:** (b) — dokumentiertes 3-Punkt-Antast-Verfahren (Posen vom
Teach-Pendant) plus CLI-Helfer `fgc setup new`, der daraus die setup.json
rechnet, validiert und schreibt. Begründung: Frame-Fehler sind die von
ADR-006 benannte Spätfehlerquelle; ~1 Tag Aufwand gegen „Roboter fährt
daneben" am Gerät.

## 2026-07-03 — Phase 3 (Konfigurator-Schiene) an die Laborkampagne gekoppelt

**Frage:** Phase 3 (materials/thermal/configurator, Pareto-Front) stand als
eigenständiger Meilenstein M2 im Plan — aber ihr wissenschaftlicher Wert
hängt an gemessenen Materialkurven (P4); mit Platzhaltern ist die
Pareto-Front zahlenmäßig wertlos.

**Alternativen:** (a) wie geplant als eigenständiger Meilenstein (Methodik
allein publizieren); (b) an die Laborkampagne koppeln; (c) auf einen
KPI-Rechner ohne Pareto-Suche eindampfen.

**Entscheidung:** (b) — Phase 3 wird wie Phase 4 zeitlich an die
Materialversuche der Dissertation gekoppelt. Vorher wird nur gebaut, was der
Gradienten-Druck ohnehin braucht: das φ-Feld im Slicer (segmentweise
IO-Werte in der S1-Auflösung). materials/thermal/configurator starten erst,
wenn erste echte Messkurven vorliegen. Damit verschiebt sich das
Methodik-Paper hinter die ersten Messungen — bewusst akzeptiert, weil das
Erfolgsbild (Grill 2026-07-03) Demonstrator + Papers mit echten Zahlen ist.

## 2026-07-03 — Grundriss-Quelle für den footprint-Check: neutrales Schnittmodul

**Frage:** E1-Stufe 2 braucht das Grundriss-Polygon für die S4-Regeln;
schneiden kann heute nur der Slicer. Neutrales Schnittmodul oder bewusste
`eligibility→slicer`-Abhängigkeit? (Vorgemerkt in status.md.)

**Alternativen:** (a) neutrales Geometrie-Modul, von beiden genutzt;
(b) eligibility importiert die Slicer-Schnittfunktion direkt; (c) vertagen.
Vertagen schied aus: Der Filter-Anspruch „volles Modell → druckbare Wände"
(inkl. L-/T-Wände) ist als Paper-Abbildung Teil des Zielbilds.

**Entscheidung:** (a), festgehalten als ADR-015 — horizontaler Mesh-Schnitt
wandert in `geometry/section.py`, eligibility und slicer hängen beide davon
ab. Begründung: Abhängigkeiten zeigen weiter strikt nach unten (§5), die
Kandidatenprüfung bleibt ohne Slicer ladbar.

## 2026-07-03 — Lokale Core-API implementiert: POST /slice (Issue #4)

**Frage:** Wie wird ADR-014 konkret umgesetzt — welche Datei, welcher Portkonflikt-Umgang, wie
wird der Provenienz-Quellstring ohne argparse gebaut?

**Entscheidung:**

- **`fgc/pipeline/api.py`** — die FastAPI-App; `API_PORT = 8765` (kein Konflikt mit Vite 5173).
  `post_slice()` ruft `slice_to_run()` direkt auf (kein eigener Codepfad), der Provenienz-Quellstring
  wird per `_api_slice_source()` co-lokalisiert zur Endpoint-Funktion gebaut (analog zu
  `cli.slice_source` für argparse). FastAPI + uvicorn als Laufzeit-Deps (`core/pyproject.toml`
  Hauptabhängigkeiten); httpx in `[dev]` für TestClient.

- **`viewer_launch.py`** — `API_URL`/`API_PORT`-Konstanten und `ensure_api_server()` nach
  demselben Muster wie `ensure_server()` für den Vite-Dev-Server: Subprocess-Start (eigenem
  Konsolenfenster auf Windows), Warte-Schleife bis `/docs` erreichbar.

- **`wizard.py`** — `ensure_api_server()` wird in Schritt 5 (Viewer öffnen) vor `open_run()`
  aufgerufen; CLI und Wizard ohne Viewer-Öffnung bleiben API-frei.

**Verworfen:** API_PORT in `api.py` exportieren und in `viewer_launch.py` importieren (würde
`fastapi` beim Import von `viewer_launch` ziehen, obwohl die API optional ist); separate
`api`-Extra-Gruppe in `pyproject.toml` (fastapi/uvicorn sind Kern-Laufzeitdeps, kein Opt-in).

**Test-Strategie:** TestClient (starlette/httpx) im selben Prozess; RUNS_DIR per
`monkeypatch.setattr(runfolder, "RUNS_DIR", tmp_path)` injiziert (gleicher Test-Seam wie CLI-Tests).
Vier Tests: gültiger Lauf + Artifact-Validierung, API-Targets == CLI-Targets (Identitätstest),
404 bei unbekannter GlobalId, `with_context=False` lässt context.json weg. Alle 67 Tests grün.

## 2026-07-03 — Issue #1 bleibt „jetzt", klickbare Wand-Auswahl kommt mit hinein

**Frage:** Grill-Session zum Restplan: Issue #1 (lokale Core-API +
Parameter-UI, ADR-014) konkurriert zeitlich mit dem kritischen Pfad
(S3/S1/S1b), und die Reihenfolge-Invariante „kein Slicer-Feinschliff vor
S1/S1b" nimmt der Parameter-Variation vorerst den Hauptnutzen. Parken?
Und: Gehört die im Plan als „spätere Komfortschicht" geführte klickbare
Modellauswahl (Wand anklicken → Eignungsbericht) dazu?

**Alternativen:** Issue #1 parken bis nach M1 / jetzt wie geplant /
nur API-Skelett. Auswahl: Komfortschicht später / mit #1 bündeln / streichen.

**Entscheidung:** Issue #1 wird jetzt umgesetzt (Begründung: schnelles
visuelles Feedback hilft schon beim Debugging von Slicer v0 und bei Demos;
dünner Wrapper, überschaubarer Aufwand) — **erweitert** um die klickbare
Wand-Auswahl im Viewer, da API + Viewer-UI ohnehin zusammen entstehen.
Leitplanken unverändert: UI ruft nur `pipeline.actions`, jeder Klick bleibt
ein regulärer Lauf, Overrides gegen die Prozessfenster-Karte nach der
bestehenden Regel (Karte ist Quelle, explizite Overrides gewinnen).
Benanntes Risiko: Frontend-Scope-Wachstum — wenn die Auswahl-UI mehr als
„glTF laden, Wand picken, candidates-Eintrag anzeigen" verlangt, wird sie
wieder abgespalten.

## 2026-07-03 — Neutrales Schnittmodul implementiert + footprint-Check aktiv (Issue #5, ADR-015)

**Frage:** ADR-015 war beschlossen (2026-07-03), aber noch nicht umgesetzt:
Der horizontale Mesh-Schnitt (heute in `slicer/sections.py`) sollte in ein
neutrales Geometrie-Modul wandern, damit `eligibility` und `slicer` beide
dasselbe Modul nutzen, ohne voneinander abzuhängen.

**Entscheidung und Umsetzung:**

- **`fgc/geometry/section.py`** — neues neutrales Modul mit `section_at(mesh,
  z_mm) → list[Polygon]`. Die Implementierung (`_section_at` + `_to_world_xy`)
  wurde 1:1 aus `slicer/sections.py` extrahiert; die private API-Grenze bleibt
  im neuen Modul. `section_layers` in `slicer/sections.py` ruft jetzt
  `geometry.section.section_at` statt der lokalen Hilfsfunktion.

- **`evaluate_wall`** in `fgc/eligibility/__init__.py` — berechnet jetzt den
  Grundriss: trimesh aus `wall.vertices_mm/faces`, horizontaler Schnitt bei
  `(z_min+z_max)/2`, erstes Polygon als `footprint` an `EligibilityContext`.
  `check_footprint` läuft damit nicht mehr provisional wegen fehlendem Polygon,
  sondern mit einem real berechneten Grundriss.

**Winkel des Schnitts:** Wandmitte (z-Midpoint). Für aufrechte, öffnungslose
Wände (v1-Scope) ist der Grundriss an jeder Höhe gleich; die Mitte ist ein
stabiler Defaultwert. Verworfen: `z_min + epsilon` (zu nah an der Bodenplatte,
numerisch empfindlich), parametrisierbares z (unnötige Komplexität — v1 kennt
keine schrägen Wände).

**Mehrere Polygone:** `section_at` kann mehrere disjunkte Polygone liefern
(S2-Befund). `evaluate_wall` nimmt das erste (nach Schwerpunkt-x sortiert). Für
Verbund-Wände (zwei getrennte Abschnitte) wird damit nur ein Teilabschnitt
geprüft — bewusst akzeptiert: getrennte Abschnitte sind in v1 außerhalb des
Scopes, und ein Grundriss pro Polygon wäre ein anderes Datenmodell (Issue für
später).

**Tests:** 10 neue Tests — 7 in `test_geometry.py` (bekannte Meshes → erwartete
Polygone; Konsistenz mit section_layers), 3 neue in `test_eligibility.py`
(footprint-Check läuft mit realem Polygon; 50-mm-Wand schlägt fehl → „Steg";
200-mm-Wand besteht, nicht provisional). Gesamtsuite: 77 Tests grün.

**Hinweis Schalenzahl/Strangbreite:** Der Steg-Check bleibt provisional bis S1
die Strangbreite liefert (wie bisher). Der Winkel-Check (30°) ist
strangbreitenunabhängig und läuft scharf, sobald `min_convex_angle_deg` in der
Karte steht — heute noch `null`. Die Grundriss-Quelle ist jetzt angebunden;
das provisorische Flag kommt nur noch von der Prozessfenster-Karte, nicht mehr
vom fehlenden Polygon.

## 2026-07-03 — Modell-glTF (model.glb) + GlobalId-Mapping, Viewer färbt nach Eignung (Issue #6)

**Frage:** Der `fgc walls list`-Lauf erzeugt `candidates.json` mit Eignungsurteilen,
aber keine Geometrie. Issue #6 verlangt wörtlich das Modell-**glTF** samt
GlobalId-Mapping als schema-/provenienz-konformes Artefakt. Wie kommt der Viewer
zu einer Gesamtansicht aller Wände, eingefärbt nach Eignung?

**Alternativen:**
(a) Reines JSON-Artefakt `model_mesh.json` (vertices_mm + faces pro GlobalId) nach
    dem `context.json`-Muster — kein GLTFLoader nötig, aber **kein glTF** und damit
    am wörtlichen Akzeptanzkriterium vorbei. (So war der erste, verworfene Durchgang
    gebaut; Begründung dort: es gebe keinen glTF-Exporter im Stack — was falsch ist.)
(b) Echtes binäres glTF (GLB) über **trimesh** (bereits Abhängigkeit; `trimesh.Scene`
    exportiert GLB nativ, Knotennamen bleiben beim Re-Import erhalten) **plus** ein
    schlankes JSON-Mapping `model_map.json` daneben, das jeden GLB-Szenenknoten an
    die GlobalId bindet und auf die Binärdatei verweist. Der Lauf bleibt so
    schema-/provenienz-konform, obwohl die Geometrie binär ist.
(c) Viewer liest direkt das IFC-Modell — verstößt gegen ADR-007 (Viewer rechnet
    nichts) und ADR-001 (kein IFC-Stack im Browser).

**Entscheidung:** (b). trimesh ist bereits im Dependency-Stack und schreibt GLB
ohne Zusatzabhängigkeit; die Annahme des ersten Durchgangs (kein glTF-Exporter
verfügbar) war schlicht falsch. Die binäre GLB kann selbst kein `schema_version`/
Provenienzblock tragen (ADR-004) — deshalb liegt das eigentliche **Artefakt** als
`model_map.json` daneben: es trägt Provenienz + Schema, listet je Wand
`{node, global_id}` und verweist über `mesh_file` auf `model.glb`. Ein Szenenknoten
je Wand, Knotenname `wall_<GlobalId>` (trimesh erhält ihn beim Export; verifiziert).
trimesh wendet beim GLB-Export **keine** Achsen-Konvertierung an (POSITION-Accessor
bleibt z-hoch mm) — der Viewer hängt die GLB deshalb in dieselbe z-hoch→y-hoch
gedrehte `world`-Gruppe wie die JSON-Meshes, ohne Sonderbehandlung.

**Umsetzung:**
- `schemas/model_map.schema.json` — neues Schema (`mesh_file` = "model.glb" +
  `walls[]` mit `node`/`global_id`); ersetzt das JSON-Mesh-Schema des ersten Durchgangs.
- `domain.models.model_map_artifact()` + `wall_node_name()` + `MODEL_GLB_FILE` —
  Artefakt-Konstruktor ohne `ifc_io`-Import (nimmt nur die GlobalId-Liste); die eine
  Stelle, die Knoten benennt, teilen sich Konstruktor und GLB-Export.
- `geometry/gltf.export_walls_glb()` — baut die `trimesh.Scene` (ein Knoten je Wand)
  und schreibt `model.glb`; neutrales Geometriemodul ohne fgc-Importe (ADR-015).
- `pipeline/actions.walls_to_run` — Wände **einmal** geladen (`load_walls`), zweifach
  genutzt: Eignung → `candidates.json`, Geometrie → `model.glb` + `model_map.json`.
  `WallsListRun` trägt `model_glb_path` + `model_map_path`.
- **Viewer:** `load.ts` reicht `model_map.json` + eine GLB-URL durch (Objekt-URL im
  FileList-Fall, `/@fs`-Pfad im `?run=`-Fall — Vite `fs.allow: [".."]` liefert die
  .glb aus); `render/model.ts` lädt die GLB async per three.js `GLTFLoader`
  (`three/addons/loaders/GLTFLoader.js`) und färbt jeden Knoten nach Eignung ein;
  `panel.ts` zeigt „X / Y Wände druckbar" aus `candidates.json` (ADR-007: Viewer
  liest, rechnet nicht).
- **Vier Kategorien:** geeignet (grün), provisional bestanden (amber, mind. ein
  pass mit provisional=true), abgelehnt (rot), unbekannt/grau (kein candidates-Eintrag).

**Tests:** 2 Unit-Tests in `test_actions.py`:
  - `test_walls_to_run_writes_valid_model_glb_and_map` — GLB existiert + lädt via
    trimesh (Knotennamen tragen GlobalIds), `model_map.json` schema-valide, verweist
    auf `model.glb`;
  - `test_model_map_covers_all_candidates` — GlobalId-Abdeckung vollständig, jeder
    Eintrag bindet `wall_<GlobalId>` an seine GlobalId.
  Gesamtsuite: 81 Tests grün, ruff clean; Ende-zu-Ende an `Building-Architecture.ifc`
  (`fgc walls list`) geprüft (4 Wände, GLB-Knoten == Mapping). Viewer bleibt ohne
  automatisierte Tests (`tsc --noEmit` grün).

**Korrektur zum ersten (unveröffentlichten) Durchgang:** Der ursprüngliche
Log-Eintrag begründete den reinen JSON-Weg mit „kein glTF-Exporter im Stack" — das
war faktisch falsch (trimesh exportiert GLB). Da der Commit nie publiziert wurde,
wird der Eintrag hier durch diesen ersetzt statt als Nachtrag geführt.

## 2026-07-03 — Viewer-Parameter-Panel: Re-Slicing über lokale Core-API (Issue #9, ADR-014)

**Frage:** ADR-014 beschloss, Slice-Parameter im Viewer änderbar zu machen
(Viewer sendet, Core-API rechnet, Viewer lädt Ergebnis). Wie werden die
Ausgangswerte des Panels befüllt, und wo lebt die API-Kommunikation?

**Ausgangswerte — Alternativen:**
(a) Viewer behält eigene Defaults (Kopplung an Karte vermieden, aber Panel
    zeigt nie, womit der aktuelle Lauf erzeugt wurde);
(b) Panel liest aus `toolpath.json` zurück, welche Parameter den Lauf erzeugt
    haben — setzt einen neuen optionalen Block im Toolpath voraus (Schema-Bump).

**Entscheidung:** (b) — `toolpath.json` bekommt einen optionalen `params`-Block
(Schlüssel: `model_path`, `layer_height_mm`, `strand_width_mm`, `n_shells`) ab
Schema-Version 0.3. Ältere 0.2-Läufe bleiben abspielbar; ihr Panel zeigt leere
Felder (= Karten-Default). Leere Felder bedeuten explizit: „Karten-Default
übernehmen" — die API füllt den Rest (`null`-Übergabe, ADR-013). Das `model_path`
ist der aufgelöste, absolute Pfad, damit der Viewer ihn ohne Kontextwissen direkt
an `POST /slice` weitergeben kann (kein CLI-Wissen im Browser nötig).

**Schema-Strategie:** `schema_version` als Enum `["0.2", "0.3"]` statt `const "0.2"`,
`params` als optionales Objekt mit `additionalProperties: false` — rückwärtskompatibel
(alte Läufe validieren weiter, neue Läufe validieren sauber). Verworfen: neues
Schema-File (unnötige Infrastruktur für ein optionales Feld derselben Artefaktart).

**API-Client im Viewer:** Neues Modul `viewer/src/api/client.ts` mit `isApiAvailable()`
(HEAD /docs, 1,5-s-Timeout) und `postSlice()` (POST /slice). Bewusst schlanker
Fetch-Wrapper, kein State. `isApiAvailable()` wird beim Seitenload einmalig asynchron
aufgerufen (kein Blockieren des Viewers); Ergebnis schaltet das Fieldset frei oder
hält es deaktiviert mit Hinweistext. Port 8765 als Konstante (`API_URL`) — muss mit
`API_PORT` in `viewer_launch.py` übereinstimmen (ADR-014).

**URL nach Re-Slice:** `history.replaceState` aktualisiert die Browser-URL auf den
neuen Laufordner, damit der Lauf direkt link-bar/neu-ladbar ist. Verworfen:
Browser-Reload (verliert Szene), neue Tab (verliert Zoom/Kamera).

**Offline-Fallback:** Panel sichtbar, Fieldset disabled, Hinweistext sichtbar;
der restliche Viewer bleibt voll funktionsfähig (ADR-007 unverändert für alle
Read-Pfade). Kein Exception-Handling in der Haupt-Load-Schleife — der Check ist
rein additiv.

**Tests (Core-seitig):** Drei neue Integrationstests in `test_api.py`:
- `test_post_slice_toolpath_has_params_block` — Schema 0.3, alle vier Felder,
  `model_path` aufgelöst, Schema-Validierung über `domain.validate`.
- `test_post_slice_partial_override_fills_remaining_from_card` — ein Feld explizit,
  Rest aus Karte; Typen und Bereiche geprüft.
- `test_post_slice_no_overrides_uses_card_defaults` — kein Override, alle vier
  Felder vollständig befüllt.
Gesamtsuite: 84 Tests grün, ruff clean, `tsc --noEmit` + `vite build` grün.

**Viewer-Tests:** Keine automatisierten Tests (ADR-007/ADR-014-Konvention);
Ende-zu-Ende manuell verifizierbar mit `fgc start` (startet API + Viewer).

## 2026-07-04 — Klickbare Wand-Auswahl im Viewer: Raycaster, Eignungsbericht, Direkt-Slicing (Issue #10)

**Frage:** Wie wird die im Design-Log 2026-07-03 beschlossene klickbare Wand-Auswahl konkret umgesetzt, ohne den dort festgehaltenen Scope (glTF laden, Wand picken, candidates-Eintrag anzeigen, direkt slicen) zu überschreiten?

**Entscheidungen im Einzelnen:**

- **`ModelView`-Interface statt nackter `THREE.Group`** (`render/model.ts`):
  `loadModelObject` gibt jetzt ein `ModelView`-Objekt zurück, das neben der `group` zwei Methoden kapselt: `pick(obj)` liest den Knotennamen (`wall:<GlobalId>`) und gibt die GlobalId zurück; `highlight(globalId)` setzt alle Wandmaterialien auf Normal-/Ausgewählt-/Gedimmt-Deckkraft (0,65/0,95/0,22). Materialien werden bei der Einfärbung nach GlobalId gebündelt (Map), damit `highlight()` nur Opacity-Writes braucht — kein erneutes `traverse()`. Alternativ erwogen: Farbe statt Opacity für Highlighting (verworfen, da die Eignungsfarbe lesbar bleiben soll); Property statt Interface (verworfen, klare API besser für spätere Tests).

- **Raycaster in `main.ts`** mit Drag-Schwelle 5 px: mousedown → click, Hypot > 5 px → Orbit-Geste, nicht Klick. Kanten (`THREE.LineSegments`) werden übersprungen — nur Mesh-Treffer zählen. Falls GLTFLoader Meshes unter einem Gruppenknoten anlegt, wird der Elternknoten als Fallback geprüft. Alternativ erwogen: Pointer-Events statt click/mousedown (Komplexitätsmehrwert marginal für diesen Anwendungsfall; click + Drag-Gate reicht).

- **`model_path` als absoluter Pfad in `candidates.json`/`model_map.json`** (`pipeline/actions.py`): `model_path.resolve()` wird einmalig in `walls_to_run` aufgerufen. Der aufgelöste Pfad landet in beiden Artefakten — identisch zu `toolpath.json` (Issue #9). Der Viewer liest ihn aus `model_map.json` und gibt ihn direkt an `POST /slice` weiter, ohne CWD-Wissen. Tests in `test_actions.py` angepasst: `.name == "modell.ifc"` + `.is_absolute()` statt hartcodiertem String (ADR-014).

- **`canvas`-Property im `Viewport`** (`scene/setup.ts`): statt `renderer.domElement` in `main.ts` nachzuschlagen, trägt `createViewport` den Canvas explizit im Rückgabe-Interface. Kein Architekturrang (Refactoring auf Modulebene).

- **Panel-Methoden `showWallReport` / `hideWallReport` / `setSliceWallBusy`** (`ui/panel.ts`): Eignungsbericht-Sektion (`#wall-report`) mit GlobalId-Anzeige, Check-Liste (Symbol, Checkname, optional Begründung und „vorläufig"-Badge) und „Diese Wand slicen"-Button. Button sichtbar für alle Wände mit `candidates`-Eintrag, aber disabled für abgelehnte Wände (Tooltip erklärt Grund) und bei fehlender API. `setApiAvailable` zieht den Button-Disabled-Zustand nach, wenn der Bericht gerade gezeigt wird.

- **`onSliceWall`-Callback** (`main.ts`): ruft `postSlice({ model_path: currentWallsListModelPath, global_id })` auf (kein anderer Parameter — Karten-Defaults greifen), wartet auf den neuen Laufordner, lädt ihn per `loadFromUrl` + `showRun` und aktualisiert die Browser-URL per `history.replaceState`. Identisches Muster wie `onReslice` (Issue #9).

**Scope-Haltung (Abbruchkriterium):** Kein Mehrbedarf entstanden — glTF laden, Wand picken, candidates-Eintrag anzeigen, direkt slicen. Kein ADR nötig (keine Architekturentscheidung neuen Rangs). Abgelehnte Wände im Beispielmodell (alle vier) machen den Ablehnungsweg real prüfbar; der Slice-Weg wurde nicht Ende-zu-Ende automatisiert getestet (manuell verifizierbar mit geeignetem Modell).

**Tests:** Core: 84 Tests grün (unverändert; `test_actions.py` — zwei Assertions auf `.is_absolute()` + `.name` statt Gleichheit). Viewer: `tsc --noEmit` + `vite build` grün, kein neuer automatisierter Test (ADR-007/ADR-014-Konvention).

## 2026-07-04 — Bugfix Viewer-Laden: Vite-HTML-Fallback maskiert fehlende Artefakte (Regression aus Issue #6)

**Symptom:** Jeder `?run=`-Load endete mit „Laden fehlgeschlagen: SyntaxError: JSON.parse: unexpected character at line 1 column 1".

**Ursache (per curl-Loop gegen den Dev-Server verifiziert):** Vite beantwortet fehlende Dateien unter `/@fs/` nicht mit 404, sondern mit der `index.html` und **Status 200** (SPA-Fallback). `fetchJson` in `viewer/src/artifacts/load.ts` prüfte nur `res.ok` und parste damit HTML als JSON. Ausgelöst wurde das erst durch Issue #6: Seitdem holt `loadFromUrl` fünf Artefakte, aber kein Lauftyp besitzt alle fünf (Slice-Läufe ohne `model_map.json`/`candidates.json`, walls-list-Läufe ohne `wallspec`/`toolpath`/`context.json`) — vor #6 existierten alle drei abgefragten Dateien in jedem Slice-Lauf, der Fallback fiel nie auf.

**Alternativen:** (a) Content-Type-Prüfung in `fetchJson` (fehlendes Artefakt = jede Nicht-JSON-Antwort); (b) `JSON.parse`-Fehler je Datei abfangen (maskiert auch echt korrupte Artefakte — verworfen); (c) Vite-Fallback für `/@fs/` abschalten (kein stabiler Konfigurationspunkt dafür — verworfen).

**Entscheidung:** (a) — `fetchJson` liefert `null`, wenn `res.ok` fehlt **oder** der Content-Type kein JSON ist (Vite liefert echte Artefakte als `application/json`, den Fallback als `text/html`). Verifiziert mit einem Wegwerf-Harness gegen beide Lauftypen: fehlende Artefakte → `null`, vorhandene → geparst, kein Throw.

**Regressionstest-Seam:** Keiner vorhanden — der Viewer bleibt per Konvention ohne automatisierte Tests (Issues #6/#9/#10). Hier dokumentiert statt erzwungen; die Prüfung lief über den reproduzierbaren curl-/Harness-Loop.

## 2026-07-04 — Bugfix Core-API: CORS-Header für den Viewer-Origin (Regression aus Issue #4/#9)

**Symptom:** Panel zeigt „Core-API nicht erreichbar — Viewer im Abspieler-Modus", obwohl die API auf Port 8765 läuft und per curl antwortet.

**Ursache (per curl mit Origin-Header verifiziert):** Der Viewer (Port 5173) ruft die API (Port 8765) cross-origin. Die FastAPI-App hatte keine CORS-Middleware: `HEAD /docs` kam ohne `access-control-allow-origin` zurück, Preflight `OPTIONS /slice` gab 405. Der Browser blockt damit sowohl `isApiAvailable()` als auch `postSlice()`. Die TestClient-Integrationstests aus #4 laufen im selben Prozess und können CORS prinzipiell nicht sehen — deshalb blieb es im Batch unentdeckt.

**Entscheidung:** `CORSMiddleware` in `api.py`, `allow_origins` nur `http://localhost:5173` und `http://127.0.0.1:5173` — die API bleibt ein reiner Localhost-Dienst, kein Wildcard-Origin. Regressionstest `test_slice_preflight_allows_viewer_origin` (Preflight → 200 + `access-control-allow-origin`), zuerst rot gesehen, nach dem Fix grün. Suite: 85 Tests grün.

## 2026-07-04 — Kinematik-Kern Doosan M1013: OPW statt Offset-Wrist (Spike S3, Issue #7)

**Frage:** Welchen Solver aus visose/Robots (MIT) braucht der M1013, und wie wird er portiert (ADR-002)?

**Befund (Verifikation vor dem Port, ADR-002-Pflicht):** Entgegen der Annahme in ADR-002/Umsetzungsplan („Offset-Wrist") verwendet Robots für den Doosan den **`SphericalWristKinematics` (OPW, Ortho-Parallel-Basis + Spherical Wrist)** — Beleg: `RobotDoosan.CreateSolver() => new SphericalWristKinematics(this)`. Der `OffsetWristKinematics` ist in Robots ausschließlich den Universal Robots (`RobotUR`) zugeordnet. Robots' OPW-Solver ist adaptiert aus `Jmeyer1292/opw_kinematics` (Apache-2.0, Brandstötter u. a.). Details im Spike-Protokoll `docs/spikes/S3_ik_roundtrip.md`; Attribution in `NOTICE` (ADR-010).

**Alternativen:** (a) trotzdem einen Offset-Wrist-Solver bauen — verworfen, würde nicht das Robots-Orakel reproduzieren und widerspricht der Verifikationspflicht; (b) numerischen IK-Solver (Jacobi) — verworfen, kein analytisches Orakel, langsamer, keine vollständige Lösungsmenge; (c) **OPW-Solver 1:1 portieren** — gewählt.

**Entscheidung:** FK als Standard-DH (`MechanismKinematics.DH`, ohne Flanschrotation für den OPW-Zweig), IK zeilenweise aus `SphericalWristKinematics.InverseKinematics` inkl. `_signs`/`_start`-Abbildung und [-π, π]-Normierung. Geometrieparameter (a, d, alpha, Achsgrenzen) aus der Robots-Bibliothek (Branch `libraries`, RWTH.xml, `model="M1013"`) nach `robots/doosan_m1013.json` (Schema 0.2, `kinematics`-Block; mm/Radiant nach ADR-006). Reine Datenklasse `domain.robot.Kinematics`, Solver in `fgc.kinematics.opw.OpwKinematics` (NumPy).

**Toleranzen (S3 festgenagelt):** Position < 0,01 mm, Orientierung < 1e-6 rad. Das 1000-Posen-Orakel (ADR-009a) ist als dauerhafter pytest-Test 1000/1000 grün (analytisch ~1e-9/1e-12). Die automatisierte Stichprobe meidet das Handgelenks-Singularitätsband (Achse 5 nahe 0/±π); im Singularitätszweig koppelt der Solver Achse 4/6 (nicht frame-exakt) — das ist erwartetes OPW-Verhalten und gehört in die Konfig-/Singularitätswahl (Issue #11), nicht ins Roundtrip-Orakel.

**Offen (HITL):** Grasshopper-Stichprobe (~20 identische Targets gegen Robots) als dokumentierte Handarbeit — noch nicht erfolgt, im Spike-Protokoll als offener Punkt geführt.

**Tests:** Core 93 grün (8 neu in `test_kinematics.py`), ruff sauber.

## 2026-07-04 — Konfigurationswahl, Achsgrenzen, Singularitätsnähe (Issue #11, Strang B)

**Frage:** Wie wird aus den bis zu acht mehrdeutigen IK-Lösungen je Target (Issue #7) eine *fahrbare* Gelenkfolge für die Simulation (Strang C) — deterministisch, bahnstetig, achsgrenz- und singularitätsgeprüft — ohne die schmale Schnittstelle (P3) aufzuweichen?

**Konfigurationswahl — Alternativen:** (a) fester Konfigurationsvorzug (immer Shoulder/Elbow/Wrist = 0) — verworfen, springt bei Grenzverletzung unstetig und ignoriert die Vorgeschichte; (b) globale Optimierung über die ganze Bahn (Graph-Kürzeste-Wege über alle Konfig-Ketten) — verworfen als Überbau für die aktuelle Reichweite, teuer und schwerer erklärbar; (c) **greedy Nächste-Nachbar-Suche im Gelenkraum** — gewählt. Je Target die dem Vorgänger nächste *zulässige* Lösung (erstes Target: nächste zum `seed`, Standard = Nullstellung), Gleichstände deterministisch über den Konfigurationsindex. Das ist reproduzierbar (gleiche Bahn → gleiche Folge) und hält entlang einer stetigen Bahn die Konfiguration konstant (kein Springen), weil dieselbe Konfiguration für eine glatte Bewegung stets den kleinsten Gelenkabstand liefert. Revisionstrigger: enge Passagen, in denen greedy sich in eine Sackgasse wählt — dann (b) nachrüsten.

**Gelenkabstand über die ±π-Naht:** Der Solver normiert Lösungen auf [−π, π]; eine glatte TCP-Bewegung kann dabei die ±π-Grenze eines Gelenks überschreiten (3,13 → −3,13). Der Abstand misst deshalb die *kürzeste* Winkeldifferenz (`atan2(sin Δ, cos Δ)`), damit dieser rein numerische Sprung nicht als weite Bewegung zählt. Bewusst offen gelassen: das eigentliche *Gelenk-Unwrapping* für Achsen mit >±180°-Bereich (M1013: J1/J2/J4/J5/J6 ±360°) — für #11-Scope (keine Konfigsprünge) genügt die Naht-korrekte Metrik; echtes Unwrapping ist Sache der Trajektorienausgabe (Strang C).

**Achsgrenzen / Unfahrbarkeit:** Warnungen sind **Daten** (`ConfigWarning`, Ziel: `Trajectory.meta.warnings`, Issue #12), keine Exceptions. *Unfahrbar* ist nur ein Target, für das keine Lösung innerhalb `joint_limits_rad` existiert; es kommt als Target mit `joints_rad=None` zurück, mit Warnung `joint_limits` (erreichbar, aber außerhalb der Grenzen) bzw. `unreachable` (außerhalb des Arbeitsraums). Der Vorgängerbezug überlebt die Lücke, damit die Bahn danach stetig bleibt.

**Singularitätsnähe-Maß — Alternativen:** (a) den bestehenden booleschen Wrist-Flag (`|j5|<1,24e-2`) als Maß nehmen — verworfen, erfasst nur die Handgelenks-, nicht Ellenbogen-/Schultersingularität und ist nicht kontinuierlich; (b) Yoshikawa-Manipulierbarkeit `√det(JJᵀ)` — verworfen, skalenabhängig und nicht [0,1]-normiert, dadurch kein roboterunabhängiger Schwellwert; (c) **reziproke Konditionszahl (σ_min/σ_max) der längen-normierten Jacobi-Matrix** — gewählt. Die geometrische 6×6-Jacobi-Matrix wird exakt aus der DH-Kette gebaut (`z_i × (o_e − o_i)` / `z_i`, gegen zentrale FK-Differenzen getestet); die Translationszeilen werden durch die charakteristische Länge Σ|a|+Σ|d| geteilt, damit Translations- und Rotationsanteil dimensionslos vergleichbar sind. Ergebnis ∈ [0,1] (1 = gut konditioniert, 0 = singulär), fällt bei jeder Rangminderung gegen 0 — roboterunabhängig schwellbar.

**Warnschwelle `DEFAULT_SINGULARITY_WARN = 0,01`:** Empirisch kalibriert (5000 Zufallsposen + Wrist-Sweep): der harte OPW-Koppelzweig (Solver setzt j4=0, koppelt in j6) greift ab |j5| ≈ 1,24e-2 rad → Maß ≈ 0,004; die Schwelle 0,01 (Maß bei |j5| ≈ 0,033 rad) feuert mit Marge *davor*, sodass die frame-inexakte Koppelzone stets angekündigt ist. Median nicht-singulärer Posen ≈ 0,044.

**Scope-Haltung:** Kein neues ADR — baut innerhalb der Modulgrenzen von `fgc.kinematics` (§5, ADR-002/006) auf #7 auf, keine Architekturentscheidung neuen Rangs. Neue Datei `core/src/fgc/kinematics/select.py`, `jacobian`/`singularity_measure` als Methoden auf `OpwKinematics` (reine FK-/Geometrie-Ableitung, gehören zum Solver). Der Kern aus #7 (`forward`/`inverse`) bleibt unberührt — das 1000-Posen-Orakel bleibt grün.

**Tests:** Core 106 grün (13 neu in `test_config_selection.py`: Jacobi gegen FK-Differenzen, Maß ∈ [0,1] und Abfall zur Wrist-Singularität, Determinismus, Bahnstetigkeit einer glatten Trajektorie ohne Konfigsprünge, Target außerhalb Arbeitsraum, künstlich enge Achsgrenzen, echte J3-Grenze, unfahrbares Mittel-Target, Singularitätswarnung), ruff sauber. 1000-Posen-Orakel (#7) unverändert grün.

## 2026-07-04 — 3-Punkt-Antastverfahren + `fgc setup new` (Issue #8, Strang C, ADR-006)

**Frage:** ADR-006 beschloss, dass es genau eine Stelle gibt, an der Bauteilwelt
und Roboterwelt verheiratet werden — das Setup-Artefakt. Das Setup-Schema
existierte bereits; gebaut werden musste der Workflow, der es aus
Roboter-Posen befüllt: `fgc setup new`.

**Dreipunkt-Verfahren — Alternativen:**

(a) TCP-Frame direkt als Rotationsmatrix/Eulerwinkel vom Pendant ablesen
    (Roboter speichert das intern so, Konverter nötig) — verworfen: Eulerwinkel
    sind reihenfolgeabhängig und die eine fehlerträchtige Stelle, die ADR-006
    explizit vermeiden will; zudem sind xyz-Positionen am Pendant ablesbar, die
    Orientation nicht in jedem Modus.

(b) Zwei-Punkt-Verfahren (Ursprung + X-Achse, Z-Achse aus Weltnormal ableiten)
    — verworfen: setzt voraus, dass die Wand aufrecht und weltausgerichtet
    steht; für schräge Wände (Paper-Zielbild) nicht tauglich.

(c) **Dreipunkt-Verfahren** (Industriestandard: Ursprung, X-Achse, XY-Ebene)
    — gewählt. Drei TCP-Positionen genügen, um einen vollständigen rechtshändigen
    Frame zu berechnen; das Verfahren ist Teach-Pendant-agnostisch (nur x,y,z
    in mm nötig, keine Orientierungsanzeige), und jeder Hiwi kann es anhand
    der README-Schritt-für-Schritt-Anleitung reproduzierbar durchführen.

**Mathematik:** Gram-Schmidt-Orthogonalisierung auf den Richtungsvektoren
P1−P0 (X-Achse) und P2−P0 (Y-Hilfsvektor): X = normalize(P1−P0);
Y_raw = P2−P0 − (P2−P0)·X̂ · X̂; Y = normalize(Y_raw); Z = X × Y
(rechtshändig, Wandnormale). Rotationsmatrix aus Spalten [X, Y, Z] →
Quaternion [w, x, y, z] via Shepperd-Methode (numerisch stabil über alle
Rotationen, keine Fallunterscheidung über Kippwinkel). Implementierung in
`core/src/fgc/setup/frame3p.py`; numpy-Abhängigkeit wie in `kinematics/opw.py`.

**Degenerations-Checks (müssen verständliche Fehlermeldungen liefern):**
- |P1−P0| < 1e-6 mm → P0 und P1 identisch
- |P2−P0| < 1e-6 mm → P0 und P2 identisch
- |Y_raw| < 1e-6 mm → P2 liegt auf der X-Achse (kollinear)
Alle drei werden als `ValueError` mit erklärendem Deutsch-Text geworfen und
in `_cmd_setup_new` auf Rückgabe 1 + stderr umgelenkt.

**Provisorische Defaults ohne `--template`:**
TCP (200 mm Düsenoffset entlang Flansch-Z, provisional), Kanal-Mapping
(Pump A/B → AO0/AO1 0–10 V, Schaum → AO2 0–5 V, Doosan-M1013-Aufbau) und
Totzeit (3,0 s, `provisional: true`) in `fgc.setup.PROVISIONAL_*`. Der
`deadtime.provisional`-Slot ist im Setup-Schema bereits vorgesehen; für TCP
und io_channels gibt es kein Schema-Flag (Frame-Def ist `additionalProperties:
false`) — daher Nutzer-Warnung auf stderr, kein Schema-Feld. Verworfen:
eigenes Schema-Flag für provisional TCP (Overhead für alle Frame-Instanzen
im Schema).

**`--template`-Option:** Liest ein bestehendes Setup-JSON und übernimmt TCP,
io_channels und deadtime daraus — `wall_to_base` wird stets aus den drei Posen
neu berechnet. Praxisfall: TCP und IO-Kanäle einmalig kalibriert, für jede neue
Aufspannung nur den Frame updaten.

**Neue Dateien:** `core/src/fgc/setup/__init__.py`,
`core/src/fgc/setup/frame3p.py` (Dreipunkt-Mathe + Shepperd-Konverter);
CLI-Erweiterung in `core/src/fgc/pipeline/cli.py` (`fgc setup new` +
Hilfsfunktionen `setup_new_source`, `_parse_xyz`, `_prompt_xyz`).

**Tests:** 17 neue in `core/tests/test_setup.py` — 5 Geometrie (Identität,
Z-up, 90° Y, 45° Z, beliebige Rotation), 5 Degenerations-Tests (identische
Paare, kollinear, fast-kollinear), 2 Schema-Validierungen, 5 CLI-Tests
(Erfolgsfall, mit Template, kollinear → 1, identisch → 1, ungültiges Format → 1).
Roundtrip-Toleranz: 1e-9 mm / 1e-9 rad (rechnerisch exakt, kein Messfehler).
Gesamtsuite: 123 Tests grün, ruff clean.

## 2026-07-04 — Simulation: Toolpath+Setup → Trajectory, Zeitparametrierung, io-Shift (Issue #12, Strang C, ADR-012)

**Frage:** Strang C schließt sich — aus dem zeitfreien Toolpath (#9), der
bahnstetigen Konfigurationswahl (#11) und dem Setup (#8) muss die `trajectory.json`
entstehen: die eine Stelle, an der **Zeit** in die Pipeline kommt (ADR-012/E3).
Zu klären waren drei Dinge: das Zeitmodell, die Achslimit-Quelle und die konkrete
io-Totzeitkompensation.

**Zeitmodell — Alternativen:**

(a) Globale trapezförmige Geschwindigkeitsplanung über die ganze Bahn
    (S-Curve/TOPP) — verworfen für v0: hoher Implementierungs- und
    Testaufwand, überzogen, solange keine echten Achs-Beschleunigungsdaten
    (S1) vorliegen.

(b) Rest-to-rest je Segment (an jedem Target anhalten) — verworfen: ignoriert
    die kommandierte Druckgeschwindigkeit `v_mm_s` und überschätzt die Druckzeit
    grob; unrealistisch für einen kontinuierlichen Extrusionsdruck.

(c) **Stückweise konstante Segmentgeschwindigkeit** (gewählt): jedem Segment
    wird die längste dreier Untergrenzen als Dauer zugewiesen —
    (1) kartesische Distanz / `v_mm_s` (die **Druckzeitschätzung** kommt aus der
    kommandierten Geschwindigkeit), (2) max_j |Δq_j| / v_max_j
    (Achsgeschwindigkeit), (3) Achsbeschleunigung. Beschleunigung ist die
    endliche Differenz der Segmentgeschwindigkeiten über die halbe Nachbardauer;
    sie wird durch **iterative Streckung** (nur wachsende dt → monoton, konvergent)
    eingehalten, mit einem **globalen Skalierungs-Sicherungsnetz** als Garantie
    (globale Skalierung um f teilt v durch f, a durch f² → ein Schritt erzwingt
    beide Grenzen). Ergebnis: streng monotone Zeitachse, Grenzen nachweislich
    eingehalten. Als v0-Vereinfachung dokumentiert; TOPP kommt, wenn S1 echte
    Beschleunigungen liefert.

**Gelenkentfaltung:** `select_along_path` normiert die gewählten Winkel auf
[−π, π]; benachbarte, physisch nahe Konfigurationen können dadurch an der ±π-Naht
numerisch springen (3,14 → −3,14). Für eine stetige, differenzierbare Zeitreihe
werden die Samples **entfaltet** gespeichert (jeder Schritt = kürzeste
Winkeldifferenz, aufaddiert). So sind die `joints_rad` sprungfrei und die
naive endliche Differenz misst die wahre Bewegung — Voraussetzung für die
v/a-Invarianten-Tests.

**Achslimit-Quelle:** `joint_velocity_limits_rad_s` /
`joint_acceleration_limits_rad_s2` neu im `kinematics`-Block von
`robots/doosan_m1013.json` (eine Quelle, wie die DH-Parameter) — Geschwindigkeiten
aus dem Datenblatt (J1/J2 120°/s, J3 180°/s, J4–J6 225°/s), Beschleunigungen
**provisorisch** = 4× Geschwindigkeit (v_max in ~0,25 s), bis S1 misst.
`Kinematics.from_dict` liest beide optional; fehlen sie, setzt `fgc.simulation`
konservative Fallbacks.

**Frame-Kette (ADR-006):** Der Toolpath trägt Düsen-Poses im **Wandsystem**; die
IK (`opw`) braucht die **Flansch-Pose in Roboterbasis**. Neue reine
Quaternion-/Frame-Algebra `fgc.simulation.transform` bildet
`wall_to_base ∘ target ∘ tcp⁻¹` — die eine Transformationsstelle, kein zweiter
Frame-Konverter neben `frame3p`.

**io-Totzeitkompensation (ADR-012):** Die io-Werte je Bahnposition werden über
die geometrische Zeitachse zur Schrittfunktion; bei
`deadtime.compensation = simulation_shift` liest Sample i seine io bei
`t_i + t_tot` (Vorziehen um −t_tot), nach Bahnende sind alle Kanäle 0 (Pumpe
schaltet t_tot vor Schluss ab). `meta.io_compensated = true`. Bei
`native_lookahead`/`none` bleibt die io roh, `io_compensated = false`. Unfahrbare
Targets halten die letzte gültige Gelenklösung und erscheinen als Warnung
(`meta.warnings`, Kind aus #11 auf das Trajectory-Vokabular reach/joint_limit/
singularity gemappt) — die Simulation bricht nie ab.

**Neue Dateien:** `core/src/fgc/simulation/{transform,timeparam,build}.py` +
`__init__.py`-Export (`build_trajectory`, `Trajectory`); Aktion `simulate_run`
in `pipeline/actions.py`; CLI `fgc simulate --run --setup [--robot]` in
`pipeline/cli.py`. Geändert: `domain/robot.py` (Achslimits),
`robots/doosan_m1013.json`.

**Tests:** 12 neue in `core/tests/test_simulation.py` — Schema-Validität,
Monotonie, v-Grenzen, a-Grenzen, Achsauslastung ∈ [0,1], Druckzeit =
letzter t_s, io-Shift zieht Onset vor (simulation_shift), kein Shift bei
native_lookahead/none, Warnung bei unfahrbarem Target, CLI-Integration
(Erfolg + fehlender Toolpath → 1 + unbekannter Lauf → 1). Synthetische Toolpaths
aus FK einer glatten Gelenkbahn (kein IFC nötig). Gesamtsuite: 136 Tests grün,
ruff clean.

## 2026-07-04 — DrlEmitter-Gerüst (Issue #13, Strang C, ADR-011)

**Frage:** Wie wird die totzeitkompensierte Trajectory (Issue #12) zu einem
lauffähigen DRL-Programm (Doosan M1013)? Welche AO-Strategie, und wann kommt
der Feinschliff?

**Entscheidung:** Gerüst sofort bauen, Feinschliff wartet auf Spike S1 (Sequenz-
Invariante aus dem Umsetzungsplan). Das Gerüst emittiert Change-on-Delta
(nur bei io-Wertänderung ein AO-Befehl), physische AO-Werte linear aus dem
Setup-Kanal-Mapping (ADR-011), Grad-Konvertierung ausschließlich im Emitter
(ADR-006). S1-abhängige Stellen (`vel_default`, `acc_default`) im DRL als
Platzhalter markiert.

**Alternativen:** (a) Alle AO-Befehle ohne Delta-Prüfung emittieren — verwirft;
der Controller-Bus wäre unnötig belastet. (b) AO-Strategie sofort optimieren
(Blending, thread_run) — wartet auf S1-Messung, kein Feinschliff ohne echte
Latenz-Zahlen. (c) Emitter als Klasse statt Funktion — Funktion ausreichend,
konsistent mit `build_trajectory`-Stil des Codebase.

**Kanal-Mapping:** Logischer Wert (0..1 default) → linear auf physical_range
gemappt; Werte außerhalb logical_range → `ValueError` (verständliche Meldung
mit Kanal, Wert, erlaubtem Bereich). Unbekannte Kanäle → `ValueError` mit
ADR-011-Verweis. Sortierung der IO-Befehle nach physischem `index`.

**DRL-Format:** `movej([deg…], vel=vel_default, acc=acc_default)` für joint-space
Bewegung (Trajectory trägt joints_rad). Mode-Setup am Kopf
(`set_mode_analog_output`, `set_mode_analog_current`). Abschalt-Block am Ende.
Provenienz als Kommentar-Header. Referenzformat: `docs/spikes/s1_programs/s1_ao_ramp.drl`.

**Neue Dateien:** `core/src/fgc/postproc/emitter.py` (`emit_drl`-Funktion),
`core/src/fgc/postproc/__init__.py` (Export), `core/tests/test_drl_emitter.py`
(17 Tests), `core/tests/fixtures/golden_drl/program.drl` (Referenz-DRL).
Geändert: `pipeline/actions.py` (`EmitDrlRun`, `emit_drl_run`),
`pipeline/cli.py` (`fgc emit-drl --run --setup`), `README.md`.

**Tests:** Change-on-Delta (konstante Abschnitte → kein Repeat, Wechsel → Emit),
Fehlerfälle (unbekannter Kanal, Wert außerhalb logical_range), Digital-Mapping,
Kanalreihenfolge nach Index, Grad-Konvertierung (π/2 → 90.000000),
Golden-File (3-Sample-Fixture → exakt erwartete DRL-Ausgabe), Action-Test
(`emit_drl_run` schreibt program.drl), CLI-Integration (Erfolg + Fehler → 1).
Gesamtsuite: 153 Tests grün, ruff clean.

## 2026-07-04 — Viewer-Trajektorien-Animation (Issue #14, Strang C)

**Frage:** Wie wird die zeitparametrierte `trajectory.json` (Issue #12) im Viewer
abspielbar, ohne die ADR-007-Grenze (kein Rechnen im Viewer) zu verletzen?
Insbesondere: Die Samples haben `joints_rad`, aber keine TCP-Position — Kinematik
im Viewer ist verboten.

**Entscheidung TCP-Visualisierung:** Der Viewer kennt auch den Toolpath (mit
`frame.pos_mm` je Target). Da `fgc simulate` genau für jeden Toolpath-Target
ein Sample erzeugt, ist die Abbildung t → TCP-Position durch normierte
Zeitinterpolation entlang der Toolpath-Target-Liste möglich, ohne Gelenk-FK zu
rechnen. Der Marker ist ein rotes Kugel-Mesh (r = 8 mm), das sich proportional
zur Abspielzeit entlang der bereits im Viewer vorhandenen Toolpath-Linie bewegt.
Verworfen: (a) TCP aus `joints_rad` per FK — verletzt ADR-007; (b) kein 3D-Marker,
nur io-Panel — schlechtere Prüfbarkeit der Bahn.

**Entscheidung Zeit-Slider:** Range-Input, intern 0–10 000 Schritte (Auflösung
0,01 % der Gesamtdauer). Drag-Flag verhindert Slider-Feedback-Schleife zwischen
Player und UI. Play/Pause als Toggle-Button mit ▶/⏸.

**Entscheidung io-Darstellung:** Balken je logischem Kanal (Name + Wert + visueller
Füllgrad). Kanäle werden bei Kanalwechsel im Lauf dynamisch neu aufgebaut.

**Entscheidung Tests:** Vitest als Test-Runner (passt zur bestehenden Vite-Pipeline,
keine zusätzliche Infrastruktur). Interpolationslogik und Player-Zustandsmaschine
als reine TypeScript-Funktionen testbar; rAF-abhängige Animation nur via Stub
getestet. Verworfen: kein eigener Test-Runner (Issue fordert ausdrücklich Tests).

**Abwärtskompatibilität:** `RunData.trajectory` ist nullable; `showRun` prüft das
Feld und zeigt/versteckt das Panel. Alle bisherigen Artefakt-Typen (wallspec,
toolpath, model_map) sind unberührt.

**Neue Dateien:** `viewer/src/trajectory/interpolate.ts`, `viewer/src/trajectory/player.ts`,
`viewer/src/render/tcpmarker.ts`, `viewer/src/trajectory/interpolate.test.ts`,
`viewer/src/trajectory/player.test.ts`.
Geändert: `artifacts/types.ts` (Trajectory-Typen + RunData), `artifacts/load.ts`
(trajectory.json laden), `ui/panel.ts` (Trajectory-Panel-Methoden),
`index.html` (HTML-Sektion), `style.css` (Trajektorien-Stile), `main.ts` (Verdrahtung),
`package.json` (vitest), `vite.config.ts` (test-Block), `README.md`, `docs/status.md`.

**Tests:** 18 Viewer-Tests grün (13 interpolate, 5 player); Core 153 Tests + ruff unverändert grün.


## 2026-07-04 — GUI-Direkteinstieg `start_viewer.cmd` (ohne Wizard)

**Frage:** Wie startet man Viewer+API, ohne dass die Wand vorab in der Konsole
festgelegt wird (`fgc start` erzwingt die Wandauswahl im Dialog)?

**Alternativen:** (a) Wizard um einen „nur öffnen"-Modus erweitern;
(b) eigenes CLI-Subkommando `fgc viewer`; (c) `__main__` in
`pipeline/viewer_launch.py` + doppelklickbare `start_viewer.cmd` am Repo-Root.

**Entscheidung:** (c). `python -m fgc.pipeline.viewer_launch` startet API- und
Vite-Server (bestehende `ensure_*`-Helfer, ADR-014) und öffnet den neuesten
Lauf mit `model_map.json` — dort funktioniert die klickbare Wand-Auswahl
(Issue #10) inkl. Direkt-Slicing. Kein neues Kommando, keine neue Logik;
die CMD-Datei ist nur ein Explorer-tauglicher Wrapper. Fehlt ein
Übersichts-Lauf, öffnet der leere Viewer mit Hinweis auf `fgc walls list`.

**Kontext:** Entstanden zu Beginn der Grill-Session „interaktiver Viewer"
(Wand- und Roboterwahl in der GUI, Platzierungsvorschläge, Zerlegung,
Simulation) — der Direkteinstieg ist die Vorstufe des künftigen GUI-Prozesses.

## 2026-07-04 — Eignung ist Befund, kein Gate (Grill-Session interaktiver Viewer)

**Frage:** Der Viewer deaktivierte „Diese Wand slicen" für ungeeignete Wände
hart (`eligible: false`) — der Wizard erlaubt dieselben Wände dagegen mit
Warnung. Welches Verhalten ist richtig, und wann läuft E1 im künftigen
GUI-Flow (Roboterwahl in der GUI)?

**Alternativen:** (a) Viewer-Gate behalten (streng); (b) Gate lockern auf
Warnung (Wizard-Parität); (c) Gate ganz entfernen ohne Warnung.

**Entscheidung:** (b). Button immer aktiv, bei ungeeigneten Wänden
Beschriftung „Trotzdem slicen (nicht geeignet)" + Tooltip-Warnung
(`viewer/src/ui/panel.ts`). Begründung aus der Grill-Session: Die Eignung
ist ein **Befund**, kein Freigabe-Gate — ungeeignete Wände sollen künftig
über Roboter-Platzierung oder Zerlegung „passend gemacht" werden; dafür
muss man sie auswählen und weiterverarbeiten können. Außerdem urteilt der
Workspace-Check heute gegen einen festen Default-Roboter
(`fgc walls list --robot doosan_m1013`), bevor in der GUI überhaupt ein
Roboter gewählt wurde.

**Angenommene Richtung (noch nicht umgesetzt):** E1 wird
roboter-parametrisiert — die Prüfung läuft im Ziel-Flow nach der Roboterwahl
(neuer Endpoint à la `POST /evaluate {model_path, robot}`), die
Modellübersicht färbt je gewähltem Roboter neu ein.

## 2026-07-04 — Roboterwahl in der GUI: Doosan-only, Lauf-Parameter, kein Setup

**Frage:** Was heißt „Roboter auswählen" im künftigen GUI-Flow?

**Entscheidung (Grill-Session):** (1) Auswahlmechanik generisch — neuer
Endpoint `GET /robots` (listet `robots/*.json`), Dropdown in der GUI,
Auswahl triggert die roboter-parametrisierte E1-Neubewertung. (2) Vorerst
bleibt Doosan M1013 der einzige Eintrag: eine KUKA-JSON ohne portierten
Spherical-Wrist-Solver (ADR-002) würde Funktionalität vortäuschen; §9.2
baut ohnehin nur den Doosan-Strang voll aus. (3) Die Roboterwahl ist ein
*Planungs-/Lauf-Parameter* (wie heute `--robot`), ausdrücklich **nicht**
das Setup — das bleibt das gemessene Kalibrier-Artefakt (ADR-006).

## 2026-07-04 — Platzierung (2 Modi) und Zerlegung (2 Arten), Grill-Session

**Frage:** Wie sehen Positionierungsvorschläge für den Roboter aus, und was
passiert physisch mit zerlegten Teilen?

**Entscheidungen:**
1. **Platzierung** (neues Konzept, s. core/CONTEXT.md): geplante Basis-Lage
   relativ zur Wand. Zwei Modi: *Optimalvorschlag* (frei gerechnet) und
   *Bewertungsmodus* (Nutzer gibt reale Aufstellmöglichkeiten vor, System
   bewertet). Bewertungsmetrik: erreichbarer Wandanteil (IK) + kinematische
   Marge (Achsgrenzen/Singularität, Maschinerie aus `select_along_path`).
   Platzierung ≠ Setup: verbindlich wird die Lage erst durchs Antasten.
2. **Zerlegung** in zwei Arten: *Abschnitte* (in place, unten→oben, je
   Abschnitt eigene Platzierung, Fuge = Druckunterbrechung) — Fokus v1;
   *Module* (separat gedruckt, montiert, Fügegeometrie nötig) — spätere
   Option. Die GUI fragt die Zerlegungsart ab, das Datenmodell sieht beide
   vor. Begriff „Segment" bewusst vermieden (im Slicer als `segment_id`
   vergeben).
3. Alles Rechnen (Vorschläge, Bewertung) liegt im Core (neue Endpoints),
   der Viewer zeigt nur an — ADR-007/014 bleiben intakt.

Verworfen: nur diskrete Podest-Höhenliste als einziger Modus (Nutzer will
volle Einstellbarkeit + Bewertung eigener Optionen); Module-first (Fokus
liegt auf monolithischem In-place-Druck).

## 2026-07-04 — Zerlegungsvorschläge: Schnitte, Anpassung, Interaktion

**Entscheidung (Grill-Session):** (a) v1 nur ebene, achsparallele Schnitte
(horizontal = Höhenstufen, vertikal = Längenteilung); Fugen-Versatz zwischen
Höhenlagen als einfacher Parameter denkbar, echte Verzahnung erst mit
Zerlegungsart „Modul". (b) Anpassbar ist alles: Schnitte verschieben,
hinzufügen, entfernen, je Abschnitt die Platzierung übersteuern; nach jeder
Änderung bewertet der Core neu, Abschnitte bekommen eine Ampel
(grün/rot — Befund, kein Gate). (c) Interaktion: Schnittebenen im 3D-Viewer
per Drag verschieben *und* numerische Felder mit Live-Vorschau.
Vorschlag = Liste von Paaren (Abschnitt, Platzierung), je Abschnitt 100 %
erreichbar; gerechnet im Core, angezeigt im Viewer (ADR-007/014).

## 2026-07-04 — Projekt als Persistenz-Einheit (ADR-016)

**Frage:** Wo lebt der Arbeitsstand des GUI-Prozesses (Wand, Roboter,
Platzierungen, Zerlegung mit manuellen Anpassungen)?

**Entscheidung:** Neues Konzept **Projekt** (`projects/<name>/project.json`):
Modell + 1..n Druckjobs (je Druckjob eine Wand + Roboter + Zerlegung +
Platzierungen + Lauf-Verweise). Läufe bleiben unveränderliche
Rechen-Protokolle (ADR-004), das Projekt ist die editierbare Klammer.
GUI-Start = Projektliste + „Neues Projekt aus IFC…". Details und verworfene
Alternativen (Lauf-Ketten, localStorage): **ADR-016**.

## 2026-07-04 — Simulation v1: kinematisches Replay, FK im Viewer

**Frage:** Wie wird „der Roboter druckt" visualisiert, wo läuft die
Arm-Kinematik, und braucht v1 Kollisionsprüfung?

**Entscheidungen (Grill-Session):**
1. **Präsentations-FK im Viewer** aus `trajectory.json/joints_rad`
   (Klarstellung in ADR-007 ergänzt; validiert per Testorakel gegen
   Core-FK). Verworfen: Gliedframes je Sample ins Artefakt schreiben
   (Aufblähung für reine Darstellung); FK-Endpoint (zu chatty für 60 fps).
   Die gegenteilige Entscheidung aus Issue #14 ist überholt.
2. **Roboter-Darstellung:** zunächst Kapsel-/Zylinder-Schema aus den
   DH-Parametern; offizielle Doosan-URDF-Meshes als Folge-Issue.
3. **Simulationsumfang v1:** kinematisches Abspielen — Arm bewegt sich,
   Strang wächst zeitgetreu, Abschnitte nacheinander mit sichtbarem
   Umbau-Schritt. **Keine Kollisionsprüfung in v1** (ehrlich ausgewiesen);
   später gehört sie als Bewertungskriterium in Platzierung/Zerlegung.

## 2026-07-04 — Endeffektor als eigenes Artefakt; Kanal-Deklaration im Tool

**Frage:** Wie wird der Endeffektor (Upload + Eigenschaften + visuelles
Ausrichten am Flansch) modelliert, und wem gehören die logischen Kanäle?

**Entscheidungen (Grill-Session):**
1. **`tools/<name>.json` + Mesh-Datei** (STL/OBJ/GLB), analog zu `robots/`:
   Name, TCP-Frame relativ Flansch, Gewicht/Schwerpunkt, Mesh-Verweis.
   Konfigurator in der GUI: Mesh hängt am Flansch (Roboter in Home-Pose),
   Ausrichten per Gizmo, TCP-Marker setzen, Speichern via API.
2. **Kanal-Aufteilung:** Der Endeffektor *deklariert* seine logischen
   Kanäle; das Setup *mappt* sie auf physische Ausgänge — ADR-011 bleibt,
   bekommt aber die Kanalliste als Quelle. Slicer/Toolpath prüfen künftig
   gegen die Deklaration des gewählten Endeffektors.
3. **Gewicht v1:** nur statischer Payload-Check (≤ Traglast), keine
   Dynamik-/Momentenrechnung. Düsendurchmesser bleibt in der
   Prozessfenster-Karte.

## 2026-07-04 — GUI-Prozess: fünf Reiter + Bibliothek (Abschluss Grill-Session)

**Frage:** Wie wird der interaktive Viewer-Prozess in Reiter aufgeteilt?

**Entscheidungen:**
1. **Fünf Prozess-Reiter:** (1) Projekt — Liste/Neu aus IFC (ADR-016),
   Modellübersicht *mit Gebäudekontext*, Wand → Druckjob; (2) Roboter —
   Roboter- + Endeffektor-Wahl, E1-Neubewertung je Wahl; (3) Druckplan —
   Platzierung *und* Zerlegung in einem Reiter (sie iterieren
   gegeneinander, getrennte Tabs erzwängen Ping-Pong); (4) Simulation —
   Slicen/Simulieren je Abschnitt, Arm-Replay; (5) Export — DRL +
   Übergabe-Checkliste („Platzierung ist Plan — vorm Druck antasten →
   Setup").
2. **Endeffektor-Konfigurator als Bibliothek** außerhalb des Prozesses
   (Stammdatenpflege wie robots/), im Prozess wird nur gewählt.
3. **Reiter sind Navigation, kein Zwangspfad:** Zurückspringen erlaubt;
   vorgelagerte Änderungen markieren nachgelagerte Stände als *veraltet*
   statt sie zu löschen.
4. **Gesetzte Anforderung:** `walls_to_run` exportiert künftig auch
   Nicht-Wand-Elemente (Decken/Dächer/Stützen) als Kontextgeometrie in den
   Übersichts-Lauf — der Kontext-Schalter greift damit auch in der
   Modellübersicht.
5. **Notiz Simulation ohne gemessenes Setup:** Die GUI-Simulation rechnet
   aus der *Platzierung* (Plan) + Endeffektor-TCP; `trajectory.meta`
   vermerkt die Quelle (geplant vs. gemessen). Das gemessene Setup bleibt
   Voraussetzung für den echten Druck, nicht für die Simulation.

## 2026-07-04 — Projekt-Fundament: Schema, project-Modul, API, Tab-Shell (Issue #16)

**Frage:** Wie wird das Projekt (ADR-016) als Persistenz-Einheit erstmals
end-to-end durchgestochen — Schema, Core-Modul, API, GUI?

**Entscheidungen:**
1. **`project.schema.json`** (neu, `schema_version` 0.1): Projekt =
   `name` + absoluter `model_path` + `overview_run` (Verweis auf den
   Übersichts-Lauf) + `print_jobs` (in diesem Slice leere Struktur, aber
   Minimal-Item `job_id` + `wall_global_id` + `runs`-Verweise bereits
   definiert). `additionalProperties: false` schützt gegen eingebettete
   Ergebnisse (Provenienz-Bypass, Revisionstrigger ADR-016). Pfade werden
   absolut aufgelöst abgelegt — Portabilität ist v1 bewusst nachrangig
   (Läufe unter `runs/` sind ohnehin lokal/gitignored).
2. **`fgc.project` als einzige Schreibstelle:** `store.write_project`
   validiert gegen das Schema und schreibt — analog zum Laufordner
   (ADR-004). Validierung passiert auch beim **Lesen** (`load_project`),
   damit vertragswidrige Projekte nie in die GUI gelangen. Das Modul
   ergänzt `domain.VALIDATABLE_KINDS` um `"project"` (Registry teilt sich
   den `provenance`-$def aus `setup.schema.json`), zählt aber ausdrücklich
   nicht zu den Lauf-Artefakten.
3. **Aktion in `pipeline.actions`, nicht im Modul:** Die orchestrierende
   `create_project_from_ifc` (Übersichts-Lauf erzeugen → referenzieren)
   lebt bei den anderen Aktionen — die eine Tür für CLI/API (Glossar
   `core/CONTEXT.md`) — und delegiert die Persistenz an `fgc.project`.
   Alternative „alle CRUD im Modul" verworfen: `walls_to_run` liegt in
   `actions`, sonst Zirkelbezug. `list_projects`/`load_project` sind reine
   Store-Reads und werden von der API direkt aufgerufen (kein Lauf, keine
   Fachlogik in der API).
4. **API dünne Wrapper:** `GET/POST /projects`, `GET /projects/{slug}`.
   Antwort verweist auf `overview_run` (absoluter Laufpfad); der Viewer
   baut daraus die `/@fs/`-URL — derselbe Weg wie bei `POST /slice`.
5. **Tab-Shell im Viewer:** Fünf Reiter (Projekt real, die anderen vier +
   Bibliothek als Platzhalter) plus Projektliste-Startschirm. Reiter sind
   Navigation, kein Zwangspfad (reine Zustandslogik in `ui/tabs.ts`,
   `canNavigate` immer `true`, per vitest belegt). Der Reiter Projekt
   beherbergt die bestehende Modellübersicht unverändert; `?run=` bleibt
   als Fallback-Direkteinstieg erhalten (lädt direkt in den Reiter
   Projekt, ohne Projektliste). Verweist auf ADR-016 (kein neues ADR).


## 2026-07-04 — Gebäudekontext im Übersichts-Lauf (Issue #17)

**Frage:** Die Modellübersicht zeigt bislang nur IfcWall-Elemente — Decken,
Dächer, Stützen fehlen, der vorhandene Kontext-Schalter greift im
Übersichts-Lauf ins Leere. Wie fügen wir den Gebäudekontext in den
walls-list-Lauf ein, ohne das Artefakt-Schema zu brechen?

**Alternativen:**
1. Neues Artefakt `building_context.json` (anderer Name, anderes Schema).
2. Bestehendes `context.schema.json` erweitern: `wall_global_id` aus
   `required` entfernen (optionales Feld), bleibt in `properties`.
3. Sentinel-Wert (`""` oder `null`) für `wall_global_id` im Übersichts-Fall.

**Entscheidung:** Option 2 — `wall_global_id` wird optional im Schema.

**Begründung:**
- Option 1 erfordert einen neuen Artefaktnamen, neues Schema und neue
  Ladelogik im Viewer — unverhältnismäßig für eine inhaltlich fast
  identische Struktur.
- Option 3 bringt semantisch leere Felder in alle Artefakte; schlechter
  Vertrag (Absenz vs. Sentinel).
- Option 2 ist aufwärtskompatibel: bestehende Slice-Läufe mit
  `wall_global_id` validieren weiterhin (das Feld ist noch in `properties`);
  neue Übersichts-Läufe ohne `wall_global_id` validieren ebenfalls.

**Viewer-Anpassung minimal:** Der Viewer lädt `context.json` bereits für
alle Läufe, rendert es halbtransparent und der Kontext-Schalter greift
generisch auf `contextObject.visible` — keine neue UI-Logik nötig. Das
Raycaster-Target ist auf `modelObject.group.children` beschränkt: Kontext-
geometrie war und bleibt nicht pickbar.

**Wände aus dem Übersichts-Kontext ausgeschlossen:** `load_context_overview`
nutzt `exclude_ifc_types=("IfcWall",)` in `load_context`, damit
`product.is_a("IfcWall")` auch IfcWallStandardCase u.ä. trifft. Wände sind
bereits in `model.glb`; ein zweites Mal im Kontext wäre redundant und würde
die klickbare Wand-Auswahl optisch stören.

**Kein context.json bei reinen Wand-Modellen:** Wenn `load_context_overview`
eine leere Liste zurückgibt, schreibt `walls_to_run` kein `context.json`.
So laden Bestandsläufe weiterhin ohne Kontext.


## 2026-07-04 — Präsentations-FK + Kapsel-Arm-Replay (Issue #18)

**Frage:** Der Viewer soll den Roboterarm die Bahn abfahren zeigen. Nach der
ADR-007-Klarstellung (2026-07-04) darf er dafür Vorwärtskinematik rechnen —
aber nur zur Anzeige, gegen die Core-FK per Testorakel validiert. Zwei offene
Entwurfsfragen: (1) Wie wird die Viewer-FK gegen den Core abgesichert? (2) In
welchem Koordinatensystem wird der Arm gezeichnet, damit sein Flansch den
TCP-Marker trifft, obwohl der Lauf **kein** Setup-Artefakt trägt?

**FK-Testorakel (Frage 1):**
- **Entscheidung:** Der Core bekommt eine öffentliche FK-Methode
  `OpwKinematics.link_frames(joints_rad)` (7 kumulierte Glied-Frames Basis…
  Flansch, dieselbe Standard-DH-Kette wie `forward_matrix`). Ein Generator
  `viewer/scripts/gen_fk_golden.py` schreibt daraus `fk.golden.json`
  (DH-Parameter + 20 Konfigurationen mit Gliedposen). Der Viewer-Test
  `fk.test.ts` rechnet dieselbe Kette in TS und vergleicht mit Toleranz
  **Position < 1e-6 mm, Quaternion-Komponentendifferenz < 1e-8** (beobachtet
  ~1e-9; beide Ketten sind analytisch identisch, nur double-Rauschen trennt sie).
- **Quaternion-Metrik statt geodätischem Winkel:** `2·acos(dot)` verstärkt nahe
  `dot=1` künstlich (Auslöschung in `1−dot`); beobachtet 2,4e-6 rad trotz
  komponentenweiser Übereinstimmung ~1e-12. Daher vergleicht das Orakel die
  vorzeichenangeglichenen Quaternion-Komponenten direkt — numerisch stabil und
  eine schärfere Schranke.
- **Driftschutz:** Die im Viewer hinterlegte Roboterkonstante `M1013_DH`
  (`kinematics/robot.ts`, Spiegel von `robots/doosan_m1013.json`) wird im Test
  gegen `fk.golden.json.dh` geprüft — driftet sie vom Core ab, schlägt der Test an.

**Anker statt Setup (Frage 2):**
- **Befund:** Die Trajectory-`joints_rad` ergeben per FK die **Flansch-Pose in
  Roboterbasis-Koordinaten**; der Toolpath/TCP-Marker lebt in
  **Wandkoordinaten**. Die Brücke ist das Setup (`wall_to_base`, `tcp`) — das
  aber **nicht** im Laufordner liegt (bestehende Trajektorie-Läufe haben nur
  wallspec/toolpath/context/trajectory). Empirisch bestätigt an
  `runs/…_192635` (dort zudem degeneriert: Ziel außerhalb Arbeitsraum → alle
  Gelenke 0, Flansch konstant).
- **Alternativen:** (a) Setup als neues Artefakt in den Lauf schreiben und im
  Viewer anwenden — bricht Abwärtskompatibilität (Bestandsläufe ohne Setup) und
  ist ein Core-Eingriff. (b) Hand-Auge-Kalibrierung (AX=ZB) aus den
  Flansch/Target-Korrespondenzen lösen — fragil, überdimensioniert für einen
  Schema-Arm. (c) **Anker pro Frame:** `anchor = target ∘ flange⁻¹`, sodass
  `anchor · flange = target` — der FK-Flansch landet exakt auf dem
  interpolierten TCP-Frame.
- **Entscheidung:** Option (c). Der Werkzeugversatz steckt implizit im Anker;
  „Arm-Flansch trifft TCP-Position" gilt damit **konstruktiv** für alle Läufe,
  ohne Setup-Wissen. Für erreichbare Bahnen (feste Aufstellung, konstante
  Zielorientierung) ist der Anker über die Zeit konstant → Basis steht fest,
  nur die Achsen artikulieren. Ein einmaliger Anker (Sample 0) würde bei
  degenerierten/unfahrbaren Läufen (eingefrorene Home-Pose) den Flansch **nicht**
  auf dem wandernden Marker halten — deshalb pro Frame.
- **Ehrliche Grenze:** Bei unfahrbaren Bahnen zeigt der Arm die eingefrorene
  Home-Konfiguration, die entlang des Ziels verschoben wird (Basis „fliegt");
  die Erreichbarkeits-Warnung steht ohnehin im Trajektorien-Panel. Für einen
  Schema-Arm ohne Kollisionsprüfung akzeptabel.

**Darstellung:** Kapsel-/Zylinder-Schema (je Glied ein Zylinder zwischen den
Gliedursprüngen, Kugeln an den Gelenken, Sockel an der Basis) — bewusst als
Schema erkennbar; die Segmentlängen sind konstant (√(a²+d²) je Achse), nur Lage/
Orientierung werden pro Frame gesetzt. Reine Replay-Mathematik (Winkel- und
Ziel-Interpolation, Anker) liegt in `trajectory/armreplay.ts` und ist eigen
getestet (Flansch trifft interpoliertes Ziel < 1e-6 mm). Kein neues ADR — die
ADR-007-Klarstellung deckt die Präsentations-FK bereits ab.

## 2026-07-05 — Wand → Druckjob: Übernahme aus dem Eignungsbericht (Issue #19)

**Frage:** Wie wird eine angeklickte Wand in den Druckjob des geöffneten Projekts
übernommen — und wie bleibt das auch für ungeeignete Wände möglich (Befund, kein
Gate)?

**Entscheidungen:**

1. **Schema-Erweiterung rückwärtskompatibel:** `print_job` in
   `project.schema.json` bekommt zwei neue optionale Felder: `assessment_run`
   (Laufordner-Pfad des Übersichts-Laufs mit den Eignungsbefunden) und
   `wall_name` (Anzeigename aus `candidates.json`, nur für die UI, keine
   Normdaten). Beide sind nicht in `required` — Bestandsprojekte mit leeren
   `print_jobs` validieren weiterhin. Alternative „Befunddaten direkt in den
   Druckjob einbetten" verworfen: verletzt ADR-016 (Projekt enthält nie
   Rechenergebnisse). Alternative „eigenes `assessment.schema.json`" verworfen:
   Überschuss für eine Laufpfad-Referenz.

2. **Aktion `set_print_job` in `pipeline/actions.py`:** Lädt das Projekt,
   setzt oder ersetzt den Druckjob mit dem angegebenen `job_id`, bewahrt
   bestehende `runs`-Verweise beim Überschreiben, schreibt via `write_project`
   zurück (einzige Schreibstelle bleibt gewahrt). `assessment_run` wird absolut
   aufgelöst — identisch zum Umgang mit `overview_run` in `project_artifact`.
   Alternative „CRUD direkt im `fgc.project`-Modul" verworfen: würde
   `walls_to_run` als Abhängigkeit in das Modul ziehen (oder Zirkelbezug).

3. **API `PUT /projects/{slug}/print-job`:** Dünner Aktions-Wrapper,
   analog zu `POST /projects`. Liefert das vollständige `ProjectResponse`
   zurück — der Viewer muss nicht nachladen. Alternative `PATCH` verworfen
   (semantisch korrekt, aber unüblicher und FastAPI-typisch PUT für Ressourcen-
   Ersetzen).

4. **Projektslug im Viewer-Zustand (main.ts):** `currentProjectSlug` und
   `currentAssessmentRun` werden bei `onOpenProject`/`onCreateProject` gesetzt.
   Beim `?run=`-Direkteinstieg bleiben sie `null`; der Adopt-Button ist dann
   deaktiviert. Alternative „Slug aus der URL ableiten" verworfen: Direkteinstieg
   hat keine Slug-URL, wäre fragil.

5. **Wiederherstellung nach Neuladen:** Beim Öffnen eines Projekts liest
   `onOpenProject` das erste `print_jobs`-Element mit `job_id === "default"` und
   befüllt damit die aktive-Job-Bar. So ist „persistiert, nach Neuladen
   wiederhergestellt" (Akzeptanzkriterium) ohne eigene State-Persistenz
   implementiert — der Core ist die einzige Quelle.

6. **Aktive-Job-Bar:** Persistente Statusleiste zwischen `#tabbar` und
   `#tab-body` im Shell-HTML — sichtbar über alle Reiter, flexbox-eingebettet,
   kein gesonderter Z-Index/Overlay. Zeigt Wandname (falls vorhanden) und
   GlobalId. Alternative „Badge im Reiter Projekt" verworfen: nicht reiter-
   übergreifend sichtbar. Alternative „in der Tabbar selbst" verworfen:
   vermengt Navigation mit Status.

**Neue Dateien:** keine.
**Geändert:** `schemas/project.schema.json`, `core/src/fgc/pipeline/actions.py`
(neuer Dataclass `PrintJobResult` + Funktion `set_print_job`),
`core/src/fgc/pipeline/api.py` (neues Modell `SetPrintJobRequest` + Endpoint),
`core/tests/test_project.py` (9 neue Tests), `viewer/src/artifacts/types.ts`
(optionales `name`-Feld in `Candidate`), `viewer/src/api/projects.ts`
(`PrintJob`-Interface + `setPrintJob`-Funktion), `viewer/src/ui/panel.ts`
(Adopt-Button + `setProjectOpen`/`setAdoptBusy`), `viewer/index.html`
(Adopt-Button + Active-Job-Bar), `viewer/src/ui/shell.ts`
(`updateActivePrintJob`/`clearActivePrintJob`), `viewer/src/main.ts`
(Zustand + Callback-Verdrahtung), `viewer/src/style.css` (Stile).

**Tests:** 182 Core-Tests (9 neu) + 35 Viewer-Tests (unverändert) grün,
ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — Roboterkatalog + roboter-parametrisierte Eignung (Issue #20)

**Frage:** Wie wird die Roboterwahl im Viewer persistiert, und wie stößt sie eine
Neubewertung an, ohne neue Fachlogik in der API einzuführen (ADR-014)?

**Entscheidungen:**

1. **Schema-Erweiterung `robot` im Druckjob (rückwärtskompatibel):** Das Feld
   `robot` (optionaler String) wird in `print_job` ergänzt — nicht in `required`,
   damit Bestandsprojekte weiter valide bleiben. Verworfen: robot-Feld auf
   Projekt-Ebene (dann müsste bei mehreren Druckjobs unklar bleiben, welcher Roboter
   für welchen Job gilt). Verworfen: robot-Feld im Übersichts-Lauf einbetten
   (verletzt ADR-016: Projekt enthält keine Rechenergebnisse).

2. **Aktion `reassess_walls_for_robot` in `pipeline/actions.py`:** Ruft
   `walls_to_run(model_path, robot_name, source)` auf (bestehende, bereits
   roboter-parametrisierte Aktion), aktualisiert `project.overview_run` und im
   passenden Druckjob `assessment_run` + `robot`. Schreibt via `write_project`
   zurück. Existiert kein Job mit dem angegebenen `job_id`, wird nur
   `overview_run` aktualisiert (kein Fehler). Alternative „separate `set_robot`-
   Aktion ohne Lauf-Erzeugung": würde die Modellübersicht nicht neu einfärben
   (kein neuer `candidates.json`-Stand) — abgelehnt.

3. **`GET /robots`:** Scannt `robots/*.json` und gibt je Roboter einen
   `RobotInfoModel` zurück (Name, Reichweite, Arbeitsraum). Dünner Wrapper —
   `RobotDef.load()` erledigt die Datei-Logik. v1: nur `doosan_m1013.json`;
   die Mechanik ist generisch (neuer `robots/`-Eintrag erscheint automatisch).
   KUKA fehlt bewusst (kein Spherical-Wrist-Solver portiert, ADR-002/§9.2).

4. **`PUT /projects/{slug}/robot`:** Dünner Aktions-Wrapper um
   `reassess_walls_for_robot`. Liefert `ProjectResponse` zurück — der Viewer muss
   nicht nachladen. Fehler bei unbekanntem Slug oder Roboter → 404. Alternative
   `PATCH` verworfen (analog Issue #19: PUT für Ressourcen-Ersetzen
   FastAPI-typischer).

5. **`RobotPanel` im Viewer (`ui/robot.ts`):** Dropdown (befüllt via `GET /robots`),
   Kenndaten-DL, „Neu bewerten"-Button. Enabled nur wenn API + Projekt offen.
   Verworfen: Dropdown direkt in `shell.ts` (zu eng an Shell-Zustand gekoppelt,
   kein eigenes Testangriffspunkt).

6. **„geprüft für {robot}" im Eignungsbericht:** Panel hält `_currentRobot`,
   gesetzt via `setCurrentRobot(name)`. In `showWallReport` wird ein neues
   `<p id="wall-report-robot">` befüllt. Verworfen: robot aus
   `candidates.json`-Provenienz auslesen (der `source`-String ist unstrukturiert,
   Parsen wäre fragil).

7. **`currentRobot` im Viewer-Zustand (main.ts):** Wird beim Öffnen eines Projekts
   aus dem aktiven Druckjob gelesen (`activeJob.robot ?? null`) und nach jeder
   Neubewertung aktualisiert. Null beim `?run=`-Direkteinstieg (kein Projekt).
   Alternative „Roboter aus overview_run-Provenienz" verworfen (übersieht den Fall
   „noch kein Job vorhanden").

**Neue Dateien:** `viewer/src/ui/robot.ts`.
**Geändert:** `schemas/project.schema.json` (neues Feld `robot` in `print_job`),
`core/src/fgc/pipeline/actions.py` (`ReassessResult` + `reassess_walls_for_robot`),
`core/src/fgc/pipeline/api.py` (`RobotInfoModel`/`RobotListResponse`/`GET /robots`/
`SetRobotRequest`/`PUT /projects/{slug}/robot`),
`core/tests/test_project.py` (8 neue Tests),
`viewer/src/api/projects.ts` (`RobotDef`/`listRobots`/`setRobot`, `robot?` in `PrintJob`),
`viewer/src/ui/panel.ts` (`wallReportRobot`, `_currentRobot`, `setCurrentRobot`,
Anzeige in `showWallReport`),
`viewer/index.html` (Roboter-Tab real + `wall-report-robot`),
`viewer/src/main.ts` (`RobotPanel`-Verdrahtung, `currentRobot`-Zustand),
`viewer/src/style.css` (Roboter-Tab-Stile).

**Tests:** 190 Core-Tests (8 neu) + 35 Viewer-Tests (unverändert) grün,
ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — Endeffektor-Domäne + Katalog: Schema, Kanal-Deklaration, Payload-Check (Issue #21)

**Frage:** Der Endeffektor soll ein eigenes, projektunabhängiges Artefakt werden (analog zu `robots/`) — mit TCP-Frame, Gewicht/Schwerpunkt, Mesh-Verweis und Deklaration der logischen IO-Kanäle (ADR-011). Wie fügt er sich ins bestehende Muster ein, und wer prüft die Traglast?

**Entscheidungen:**

1. **Schema `schemas/tool.schema.json` (neue Datei):** Felder: `schema_version`, `name`, `vendor`, `tcp_frame` ($ref setup.schema.json#/$defs/frame — ADR-006), `weight_kg` (≥0), `cog_mm` (optional), `mesh` (optional), `channels` (Kanalname → Kanaldeklaration mit `kind: "analog"|"digital"`, `description`, `default_value`). `additionalProperties: false` überall. `"tool"` wird in `VALIDATABLE_KINDS` aufgenommen und ins Schema-Registry eingehangen — gleicher Mechanismus wie `"project"`. Verworfen: Kanäle als Liste (Map ist einfacher für Lookup und Validierung); separates `channels.schema.json` (Overhead für wenige Felder).

2. **Domänenklasse `fgc.domain.tool.ToolDef`** (analog `RobotDef`): Dataclass mit `load(name)`, `channel_names`-Property, `payload_ok(payload_kg)` und `payload_margin_kg(payload_kg)`. `ChannelDecl` als eigene frozen Dataclass. Die Klasse ruft beim Laden `domain.validate(raw, "tool")` auf — gleicher Vertrag wie das geplante Tool-Schema. Verworfen: Kanaldeklaration nur als Dict (macht Typen unsicher und Testen aufwendiger).

3. **Referenz-Endeffektor `tools/two_component_nozzle.json`** (neue Datei): Zweikomponenten-Düse mit `pump_a` / `pump_b` / `foam` (alle analog), Gewicht 3,5 kg, TCP-Versatz 210 mm entlang Flansch-Z (provisorisch). Dieses Artefakt ist Test-Fixture und Nutzungsbeispiel zugleich.

4. **Payload-Check: Befund, kein Gate.** `ToolDef.payload_ok(payload_kg)` liefert `True/False`, `payload_margin_kg` den Spielraum (negativ = Überschreitung). In `set_tool_for_job` wird nach dem Schreiben der Payload-Check durchgeführt (Roboter aus dem Job) und das Ergebnis im `SetToolResult` mitgeliefert. Die API-Antwort trägt `payload_ok` und `payload_margin_kg`; der Viewer zeigt eine Warnung bei `payload_ok=false`, blockiert aber nicht. Verworfen: Payload-Check als eigener Endpoint (unnötig — der PUT/save-Aufruf trägt das Ergebnis direkt zurück); Dynamik/Momente (v2, braucht gemessene Massenträgheiten).

5. **`RobotDef.payload_kg` (neu, optional):** `robots/doosan_m1013.json` hatte bereits das Feld `payload_kg: 10` — `RobotDef.load()` liest es jetzt (rückwärtskompatibel: fehlt es, ist `payload_kg=None`). Damit hat `get_robots` auch `payload_kg` im `RobotInfoModel`; der Viewer kann die Traglast client-seitig für den Inline-Payload-Hinweis nutzen (vor dem Speichern-Klick).

6. **API `GET /tools`** (analog `GET /robots`): scannt `tools/*.json` via `ToolDef.load`; gibt `ToolListResponse` mit je `ToolInfoModel` (inkl. `channels` als Dict). Neue Endeffektoren erscheinen ohne Codeänderung.

7. **API `PUT /projects/{slug}/tool`**: dünner Wrapper um `set_tool_for_job`. Liefert `SetToolResponse` mit Projekt + Payload-Befund. Fehlt der Endeffektor → 404; kein Druckjob → 422 (explizite Fehlermeldung).

8. **Viewer `ToolPanel` (`viewer/src/ui/tool.ts`):** Dropdown (GET /tools), Kenndaten-DL, Inline-Payload-Hinweis (live, client-seitig: `tool.weight_kg` vs. `_robotPayloadKg`), Speichern-Button mit Payload-Warnung-Anzeige nach der API-Antwort. Payload an `toolPanel` wird propagiert beim Laden der Roboterliste und nach jeder Neubewertung.

9. **`print_job.tool` im Schema** (rückwärtskompatibel optional): Bestandsprojekte validieren weiterhin; Wahl nach Neuladen aus `activeJob.tool` wiederhergestellt.

10. **`TOOLS_DIR`** in `fgc.paths` — die eine Stelle, die das Monorepo-Layout kennt.

**Scope-Grenze (bewusst ausgelassen):** Endeffektor-Konfigurator (visuelles Ausrichten am Flansch per Gizmo) ist ein eigener Slice (#28, Bibliothek); Kanal-Prüfung gegen Toolpath/Setup ist Folgeschritt. Kein neues ADR — die Entscheidungen liegen innerhalb des bestehenden Rahmens (ADR-011, ADR-016).

**Neue Dateien:** `schemas/tool.schema.json`, `tools/two_component_nozzle.json`, `core/src/fgc/domain/tool.py`, `core/tests/test_tool.py`, `viewer/src/ui/tool.ts`.
**Geändert:** `core/src/fgc/paths.py` (`TOOLS_DIR`), `core/src/fgc/domain/__init__.py` (`VALIDATABLE_KINDS`), `core/src/fgc/domain/robot.py` (`payload_kg`), `core/src/fgc/pipeline/actions.py` (`SetToolResult`, `set_tool_for_job`), `core/src/fgc/pipeline/api.py` (`RobotInfoModel.payload_kg`, Tool-Endpoints), `schemas/project.schema.json` (`tool` in `print_job`), `viewer/src/api/projects.ts` (`ToolDef`, `SetToolResult`, `listTools`, `setTool`, `tool?` in `PrintJob`, `payload_kg` in `RobotDef`), `viewer/index.html` (Endeffektor-UI im Roboter-Reiter), `viewer/src/main.ts` (`ToolPanel`-Verdrahtung, `currentTool`, `loadedRobots`), `viewer/src/style.css` (Tool-Stile), `README.md`, `docs/status.md`.

**Tests:** 211 Core-Tests (21 neu) + 35 Viewer-Tests (unverändert) grün, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — placement-Modul: Bewertungsmodus der Platzierung (Reiter Druckplan, Issue #22)

**Frage:** Der Nutzer soll im Reiter Druckplan seine realen Aufstellmöglichkeiten (Basis-Lage relativ zur Wand) vorgeben und vom Core bewerten lassen. Welche Metrik, welches Sampling, wo leben Eingaben/Ergebnisse, und wie bleibt die Platzierung erkennbar ein Plan (kein Setup, ADR-006)?

**Entscheidungen:**

1. **Deep module `fgc.placement`** hinter schmaler Tür: `evaluate(wall, robot, tool, option) → PlacementScore`. Eingaben sind reine Daten (`WallSurface` als Rechteck Länge×Höhe im Wand-Koordinatensystem, `PlacementOption` mit `lateral_mm`/`standoff_mm`/`stand_height_mm`/`yaw_rad`) — dadurch mit synthetischen Fixtures (klein/hoch) testbar, ohne IFC. Verworfen: Bewertung über die volle Mesh-Geometrie (für Erreichbarkeit zählt die abzufahrende Fläche, nicht das Volumen).

2. **Metrik = erreichbarer Wandanteil + kinematische Marge.** Je Rasterpunkt wird das Flansch-Ziel gerechnet (Düse senkrecht nach unten, TCP-Frame des Endeffektors herausmultipliziert) und die **bestehende** Konfigurationswahl (`select_along_path`, Issue #11) entscheidet Erreichbarkeit/Achsgrenzen/Singularitätsnähe — nichts dupliziert. `reachable_fraction` = Anteil fahrbarer Punkte; `kinematic_margin` = kleinstes Singularitätsnähe-Maß der erreichten Punkte (0 = singulär, 1 = gut), zusätzlich `mean_margin`. Warnungen der Konfigurationswahl kommen als **Daten** im Score heraus (kein Abbruch — „Befund, kein Gate"). Verworfen: eigene Reichweiten-Heuristik (Kugelradius) — zu grob, ignoriert Achsgrenzen und Orientierung.

3. **Festes Sampling-Raster 150 mm** (`SAMPLE_SPACING_MM`) über Wandlänge × Wandhöhe, mindestens 2×2 Punkte, Reihenfolge Höhe außen/Länge innen (je „Schicht" eine stetige Punktfolge für die Konfigurationswahl). Deterministisch: gleiche Wand + gleiche Auflösung → gleiche Stichprobe → gleicher Score (ADR-004-Geist). 150 mm hält die Bewertung bei Dutzenden IK-Aufrufen schnell und erfasst Reichweitengrenzen in der Höhe sicher. Verworfen: zufällige Stichprobe (nicht reproduzierbar), Toolpath-basiertes Sampling (Platzierung kommt vor dem Slicen).

4. **Bewertung als Lauf, Eingaben im Projekt (ADR-004/016-Trennung):** `evaluate_placements` legt einen regulären, provenienz-gestempelten Lauf mit `placement.json` (neues Schema `schemas/placement.schema.json`, `"placement"` in `ARTIFACT_KINDS`) ab. Im Druckjob landen nur die *Plan-Eingaben* (`placements`), die Wahl (`selected_placement`) und der *Verweis* (`placement_run`) — nie Scores. Alle drei Felder optional → Bestandsprojekte validieren weiter (rückwärtskompatibel). `fgc.project.write_project` bleibt die einzige Schreibstelle.

5. **Wahl markieren ohne Neubewertung:** eigene leichte Aktion `select_placement` (+ `PUT /projects/{slug}/placement-selection`) setzt nur `selected_placement`; `option_id=null` hebt die Wahl auf, unbekannte option_id → `ValueError`/422. Verworfen: Wahl nur über erneutes `POST /placements` (rechnet unnötig, obwohl deterministisch).

6. **Roboter Pflicht, Endeffektor optional:** ohne `print_job.robot` → `ValueError` (Kinematik nötig, Issue #20); ohne `print_job.tool` rechnet der Core mit Null-TCP (Düse am Flansch). Wandmaße kommen aus `candidates.json` des `assessment_run` (`dimensions_mm`) — keine erneute IFC-Öffnung.

7. **GUI Reiter Druckplan (`viewer/src/ui/druckplan.ts`):** editierbare Options-Liste (Name, seitlich, Abstand, Höhe; `yaw_rad` bewusst nicht exponiert — die Basisdrehung geht bei einem 6R-Arm in Achse 1 auf und ändert den Score praktisch nicht), „Bewerten" → Score-Liste (Prozent, Marge, Warnungszahl), „Wählen" je Option. Kennzeichnung als **Plan** über gerahmten Hinweis „Plan — vor dem Druck antasten" (ADR-006). Nach Neuladen: Formular + Wahl aus dem Druckjob, Scores per Fetch aus `placement_run/placement.json` (Viewer spielt Artefakte ab, ADR-007).

8. **Basis-Marker in 3D (`viewer/src/render/basemarker.ts`):** cyan Basis-Scheibe + Achsenkreuz (+ Podest-Quader bei Aufstellhöhe > 0) in der Modellübersicht (Reiter Projekt — der einzige Viewport). Lage approximiert über die Bounding-Box des Wand-Meshes (Längsachse = größere horizontale Ausdehnung, Front = +Normalseite) — reine Darstellungsmathematik (ADR-007-Klarstellung), visuell geprüft, kein Test. Verworfen: exaktes Wand-Frame aus IFC in den Viewer transportieren (eigener Slice; für einen Plan-Marker reicht die Approximation).

9. **Wandwechsel invalidiert Platzierungen:** `set_print_job` baut den Job neu auf (bestehendes Verhalten) — der Viewer setzt den Reiter Druckplan dann zurück (neue Wand → alte Stellplätze hinfällig).

**Scope-Grenze (bewusst ausgelassen):** Optimalvorschlag (System rechnet frei) ist #23; Zerlegung bei < 100 % Erreichbarkeit ist #24; Kollision Basis↔Gebäudekontext ist nicht Teil der Metrik (v1 bewertet nur Erreichbarkeit + Marge). Kein neues ADR — alles im Rahmen von ADR-004/006/007/014/016.

**Neue Dateien:** `core/src/fgc/placement/{__init__,evaluate,artifact}.py`, `schemas/placement.schema.json`, `core/tests/test_placement.py`, `viewer/src/ui/druckplan.ts`, `viewer/src/render/basemarker.ts`.
**Geändert:** `core/src/fgc/domain/__init__.py` (`ARTIFACT_KINDS` + `"placement"`), `core/src/fgc/pipeline/actions.py` (`PlacementEvalResult`/`evaluate_placements`, `SelectPlacementResult`/`select_placement`), `core/src/fgc/pipeline/api.py` (`POST /projects/{slug}/placements`, `PUT /projects/{slug}/placement-selection`), `schemas/project.schema.json` (`placements`/`selected_placement`/`placement_run` in `print_job`), `viewer/src/api/projects.ts` (Placement-Typen, `evaluatePlacements`, `selectPlacement`), `viewer/index.html` (Reiter Druckplan real), `viewer/src/main.ts` (Druckplan-Verdrahtung, Basis-Marker, Wiederherstellen), `viewer/src/style.css` (Druckplan-Stile), `README.md`, `docs/status.md`.

**Tests:** 228 Core-Tests (17 neu) + 35 Viewer-Tests (unverändert) grün, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — placement-Modul: Optimalvorschlag fuer die Roboterbasis (Issue #23)

**Frage:** Der Nutzer soll nicht immer Aufstellpositionen manuell eingeben muessen — besonders bei ueberhohen Waenden (Wand > Roboterreichweite) ist unklar, welche Podesthoehe die Erreichbarkeit maximiert. Wie sucht das System deterministisch die beste Basis-Lage?

**Entscheidungen:**

1. **Rastersuche ueber seitlich + Hoehe:** `fgc.placement.suggest(wall, robot, tool)` legt ein festes 2D-Raster an — 3 seitliche Positionen (-length/4, 0, +length/4) x 7 Hoehenstufen (0…3000 mm in 500-mm-Schritten) = 21 Kandidaten. Jeder Kandidat wird mit dem bestehenden `evaluate` bewertet. Sortiert nach `reachable_fraction` (primaer), `mean_margin` (sekundaer); die `n_best` besten werden zurueckgegeben. Deterministisch: gleiche Eingaben → gleiche Vorschlaege (ADR-004-Geist). Verworfen: zufallige Suche (nicht reproduzierbar); Gradientenabstieg (teuer, lokale Minima, bricht die Deterministik ohne Startwert-Konvention).

2. **Vorschlaege in dieselbe Vergleichsliste wie manuelle Optionen:** option_ids der Vorschlaege beginnen mit `vorschlag-` (Rang 1 = bester). Manuelle Optionen bleiben erhalten; erneuter Aufruf ersetzt alte `vorschlag-*`-Optionen (kein Duplikat-Akkumulation). So kann der Nutzer manuell und automatisch generierten Optionen nebeneinander vergleichen und eine waehlen — gleiche Wahlmechanik, gleiche Darstellung. Verworfen: separater Bereich im UI fuer Vorschlaege (inkonsistente Interaktion, doppelte Wahl-Logik).

3. **Standoff-Parameter ueber API exponiert:** `standoff_mm` (Default 700 mm) ist ein API-Parameter, weil er von Labor-Randbedingungen abhaengt (Sicherheitsabstand, Platzverhaeltnisse). `n_best` (Default 3) steuert, wie viele Vorschlaege in die Liste kommen. Beide Werte sind von der GUI nicht exponiert (v1-Vereinfachung — Defaults reichen fuer den Forschungsbetrieb).

4. **Aktion `suggest_placement` delegiert an `evaluate_placements`:** Die Aktion ruft `suggest` fuer die besten Grid-Kandidaten, fuegt sie als neue `vorschlag-{rank}`-Dicts zu den manuellen Optionen hinzu, und ruft dann `evaluate_placements` fuer alle Optionen auf. So entsteht ein regulaerer, provenienz-gestempelter Bewertungslauf (ADR-004) — der Viewer bekommt denselben Artefakt-Typ wie beim manuellen Bewertungsmodus. Verworfen: Scores direkt aus `suggest` ohne erneuten `evaluate`-Aufruf in den Lauf schreiben (haette eigene Lauf-Schreiblogik erfordert, die `evaluate_placements` dupliziert).

5. **Busy-Zustand in der GUI:** Der „Optimalvorschlag"-Button wechselt Text zu „Rechnet …" und sperrt alle Buttons, bis die Antwort kommt. Fehler erscheinen im Status-Feld. Die Rechenzeit (2–10 s) ist fuer einen Plan-Schritt akzeptabel; ein Fortschritts-Streaming (SSE) wurde fuer v1 nicht umgesetzt (ausreichend als Befund, kein Abbruch). Das feste 21-Punkte-Raster ist zugleich der „Timeout"-Mechanismus der PRD-Vorgabe: statt eines Wall-Clock-Timeouts, der die Suche nicht-deterministisch abbrechen koennte, ist die Rastergroesse fest verdrahtet (nicht ueber die API vergroesserbar) — die Rechenzeit ist damit von vornherein gedeckelt, ohne die Determinismus-Anforderung zu gefaehrden.

6. **Kein neues ADR:** Der Optimalvorschlag liegt vollstaendig im Rahmen von ADR-004 (Lauf), ADR-006 (Plan, kein Setup), ADR-007 (Core rechnet, Viewer zeigt), ADR-014 (duenner API-Wrapper) und ADR-016 (Druckjob traegt nur Eingaben + Verweis). Scope-Grenzen (bewusst ausgelassen): Kollision Basis↔Gebaeude, nicht-rechteckige Suchgebiete, Parallelisierung der Rasterauswertung.

7. **Bestehende Auswahl bleibt beim Vorschlag erhalten + Kontext-Ladecode zusammengefuehrt:** Beim Review vor dem Commit fiel auf, dass `suggest_placement` `evaluate_placements` ohne `selected` aufrief — das haette eine bereits getroffene Wahl (`selected_placement`) bei jedem Optimalvorschlag stillschweigend geloescht, obwohl der Vorschlag die Liste nur *ergaenzen* soll. Fix: `suggest_placement` reicht `job.get("selected_placement")` durch (Test `test_suggest_placement_preserves_existing_selection`). Dabei auch das doppelt vorhandene Laden von Roboter/Endeffektor/Wandflaeche aus `evaluate_placements` und `suggest_placement` in `_placement_context_for_job` zusammengefuehrt (eine Stelle statt zwei — Drift-Risiko beseitigt).

**Neue Dateien:** `core/src/fgc/placement/suggest.py`.
**Geaendert:** `core/src/fgc/placement/__init__.py` (`suggest`, `DEFAULT_STANDOFF_MM` exportiert), `core/src/fgc/pipeline/actions.py` (`suggest_placement`-Aktion, `_placement_context_for_job`-Helfer), `core/src/fgc/pipeline/api.py` (`POST /projects/{slug}/placement-suggestion`), `core/tests/test_placement.py` (13 neue Tests), `viewer/src/api/projects.ts` (`suggestPlacement`-Funktion + `SuggestPlacementResult`-Typ), `viewer/src/ui/druckplan.ts` (`onSuggest`-Callback + „Optimalvorschlag"-Button + Busy-Zustand + Options-Sync), `viewer/index.html` (`placement-suggest-btn`), `viewer/src/main.ts` (`onSuggest`-Verdrahtung), `README.md`, `docs/status.md`.

**Tests:** 241 Core-Tests (13 neu) + 35 Viewer-Tests (unveraendert) gruen, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — decompose-Modul: Zerlegungsvorschlag in Abschnitte (Issue #24)

**Frage:** Reicht keine einzelne Platzierung fuer 100 % der Wand (ueberhoch/ueberlang), muss der Core eine Zerlegung in nacheinander druckbare Teile vorschlagen. Wie wird geteilt, wie werden die Teil-Meshes erzeugt, und wie landet das schema-konform + ADR-016-konform im Projekt — ohne die Platzierungslogik zu duplizieren?

**Entscheidungen:**

1. **Neues deep module `fgc.decompose` mit drei Tueren (`propose`/`apply`/`evaluate`):** `propose(wall, robot, tool)` liefert einen `DecompositionPlan` (achsparallele Schnittebenen + Paare Abschnitt/Platzierung, Reihenfolge unten → oben); `apply(wall_mesh, plan)` die wasserdichten Abschnitts-Meshes; `evaluate(plan, robot, tool)` die Ampel je Abschnitt. Die Begriffe folgen `core/CONTEXT.md`: **Abschnitt** (nicht „Segment" — im Slicer vergeben), **Zerlegung**, **Platzierung**.

2. **Reichweite ausschliesslich ueber `fgc.placement` (nichts dupliziert):** Jeder Abschnitt wird als eigenstaendige, abschnitts-lokale `WallSurface` (Laenge x Hoehe, bei z=0 beginnend) von seiner Platzierung aus bewertet — mit dem bestehenden `suggest` (Optimalvorschlag je Abschnitt) und `evaluate` (Ampel). Die Aufstellhoehe der Platzierung ist damit abschnitts-lokal (Podest relativ zum Abschnittsfuss); der reale z-Versatz steckt in der Abschnitts-z-Grenze. So braucht `decompose` keine eigene Kinematik.

3. **Teilungsgroesse: Arbeitsraum-Startschaetzung + Verfeinerung entlang der blockierenden Achse.** Startwert `n_v = ceil(L/max_print_length)`, `n_h = ceil(H/max_print_height)` (grobe E1-Huellwerte). Ist die repraesentative Zelle nicht gruen, wird getestet, ob eine zusaetzliche **Laengen-** oder **Hoehenteilung** den erreichbaren Anteil staerker hebt — die staerkere gewinnt. Damit teilt eine ueberhohe Wand nur horizontal (n_v bleibt 1), eine ueberlange nur vertikal (n_h bleibt 1). Verworfen: fester Ratio-Vergleich `extent/max_extent` (kippt bei schmalen Zellen faelschlich auf die andere Achse); Gradientenverfahren (nicht-deterministisch, teuer). Da alle Zellen gleich gross sind, genuegt **eine** Platzierungssuche fuer alle Abschnitte (nur die option_id unterscheidet sich) — spart Rechenzeit, bleibt deterministisch. Obergrenze `MAX_DIVISIONS=16` gegen Endlosverfeinerung (dann best effort, `evaluate` faerbt rot).

4. **Mesh-Teilung mit trimesh + eigener shapely-Deckelung (statt geometry/section.py).** `geometry/section.py` (ADR-015) liefert nur 2D-Umriss-Polygone eines horizontalen Schnitts — nicht die 3D-Teilung. Gewaehlt: `trimesh.Trimesh.slice_plane(cap=False)` je innerer Grenze. `cap=True` scheiterte, weil in dieser Umgebung **keine Triangulierungs-Engine** (mapbox_earcut/triangle/manifold3d) installiert ist; deshalb wird die planare Schnittflaeche **selbst** gedeckelt: offene Randkanten in der Schnittebene → shapely `polygonize` → `triangulate` (Delaunay, mit contains-Filter), Deckel-Dreiecke anhaengen, am Ende `fix_normals`. Ergebnis: wasserdichte Teile, Volumensumme = Wandvolumen (Test: rel. 1e-3). v1-Grenze: die Deckelung nimmt loch-freie (konvexe/einfache) Schnittquerschnitte an — fuer achsparallele Schnitte durch quaderfoermige Waende ist der Querschnitt ein Rechteck; Oeffnungen in der Schnittebene sind eine spaetere Verfeinerung (read-only v1). Kein neuer Dependency, kein Revisionstrigger von ADR-015 ausgeloest (das Schnittmodul bleibt neutral; die 3D-Teilung ist Aufgabe von `decompose`, nicht von `geometry/section.py`).

5. **Persistenz strikt nach ADR-016.** Der Zerlegungslauf (`decompose.json`, neues Schema `schemas/decompose.schema.json`) traegt das **gerechnete** Ergebnis: Schnittebenen, Abschnitte, Platzierungen, Ampeln — provenienz-gestempelt (ADR-004). Der Druckjob traegt nur die **Eingaben** (`decomposition_kind`, `cuts`) und den **Verweis** (`decompose_run`) — nie Ampeln/Meshes. Spiegelt exakt das placement-Muster (Issue #22): Aktion `propose_decomposition`, duenner API-Wrapper `POST /projects/{slug}/decomposition`, gemeinsamer Kontext-Helfer `_placement_context_for_job`.

6. **Zerlegungsart wird abgefragt und gespeichert; nur „abschnitt" gerechnet.** Das Schema kennt `enum ["abschnitt", "modul"]`; die GUI zeigt „Abschnitte (in place)" aktiv und „Module (zum Montieren)" sichtbar, aber disabled/„spaeter". `propose`/die Aktion/der Endpoint lehnen `kind="modul"` mit `ValueError`/422 ab (braucht Fuegegeometrie). So ist die Sprache vollstaendig, die Funktion v1-ehrlich begrenzt.

7. **GUI read-only (Editing ist #25).** Reiter Druckplan: Zerlegungsart-Select + „Zerlegungsvorschlag"-Button (Busy-Zustand) + Abschnittsliste mit Ampel-Faerbung (gruener/roter linker Rand), z/x-Grenzen und Platzierung je Abschnitt. 3D (`render/cutplanes.ts`): die Schnittebenen als semi-transparente amberfarbene `PlaneGeometry`-Flaechen in der Modelluebersicht — reine Darstellungsmathematik (ADR-007-Klarstellung), Lage/Ausdehnung aus der Wand-Bounding-Box (wie `basemarker.ts`), visuell geprueft, kein Test. Nach Neuladen: Zerlegungsart + Schnittebenen aus dem Druckjob, Abschnitte per Fetch aus `decompose_run/decompose.json` (Viewer spielt Artefakte ab, ADR-007).

8. **Kein neues ADR:** Der Zerlegungsvorschlag liegt vollstaendig im Rahmen von ADR-004 (Lauf), ADR-006 (Plan, kein Setup; mm/rad), ADR-007 (Core rechnet, Viewer zeigt), ADR-014 (duenner API-Wrapper) und ADR-016 (Druckjob traegt nur Eingaben + Verweis). Scope-Grenzen (bewusst ausgelassen): Editieren des Schnittplans (#25), Slicen/Simulieren je Abschnitt (#26), Kollision Basis↔Gebaeude, Oeffnungen in der Schnittebene, „modul"-Zerlegung.

**Neue Dateien:** `core/src/fgc/decompose/{__init__,plan,propose,apply,evaluate,artifact}.py`, `schemas/decompose.schema.json`, `core/tests/test_decompose.py`, `viewer/src/render/cutplanes.ts`.
**Geaendert:** `core/src/fgc/domain/__init__.py` (`ARTIFACT_KINDS` + `"decompose"`), `core/src/fgc/pipeline/actions.py` (`DecomposeResult`/`propose_decomposition`), `core/src/fgc/pipeline/api.py` (`POST /projects/{slug}/decomposition`), `schemas/project.schema.json` (`decomposition_kind`/`cuts`/`decompose_run` in `print_job`), `viewer/src/api/projects.ts` (Zerlegungs-Typen + `proposeDecomposition`), `viewer/src/ui/druckplan.ts` (Zerlegungs-Abschnitt: Art-Select, Button, Abschnittsliste), `viewer/index.html` (Zerlegungs-Block), `viewer/src/main.ts` (`onDecompose`-Verdrahtung, Schnittebenen-Rendering, Wiederherstellen), `viewer/src/style.css` (Zerlegungs-Stile), `README.md`, `docs/status.md`.

**Tests:** 258 Core-Tests (17 neu) + 35 Viewer-Tests (unveraendert) gruen, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — Schnittplan-Editing: Drag + Zahlenfeld, Override, Ampel-Neubewertung (Issue #25)

**Frage:** Wie wird der read-only-Zerlegungsvorschlag (#24) editierbar, ohne die Architektur-Leitplanke „der Viewer rechnet nichts Fachliches" (ADR-007) zu verletzen — und so, dass 3D-Drag und Zahlenfeld nachweislich denselben Schnitt ändern?

1. **Ein Schnittplan-Zustand, zwei Eingabewege (Drag + Zahlenfeld) über dieselbe Funktion.** Die Zustandslogik (`addCut`/`moveCut`/`removeCut`/`setSectionOverride`/Dirty) liegt als **reine TypeScript-Funktionen** in `viewer/src/ui/cutplan-state.ts`, vollständig von three.js getrennt und mit vitest getestet (16 Fälle). Sowohl das Drag (main.ts) als auch das Zahlenfeld (druckplan.ts) rufen dieselbe `moveCut`-Funktion auf denselben Zustand — Synchronität fällt aus der Architektur, nicht aus Ad-hoc-Sync. Verworfen: zwei getrennte Positionsquellen mit Abgleich (driftet, testet schlecht).

2. **Drag committet erst am Drag-Ende, nicht live.** Während des Ziehens bewegt main.ts nur das Ebenen-Mesh visuell entlang der Achse (Darstellungsmathematik); `panel.setCutPosition` schreibt erst auf `pointerup` in den Zustand und löst den debounced Core-Refresh aus. Begründung: `setCutPosition` feuert bewusst **nicht** `onCutsChanged` (kein 3D-Rebuild pro Frame während des eigenen Drags — das würde die gezogene Ebene unter dem Cursor neu aufbauen); das Zahlenfeld dagegen feuert `onCutsChanged`, weil es kein Mesh direkt bewegt. Die achsen-beschränkte Drag-Ebene + `projectOntoAxis` (in `render/cutplanes.ts`) liefern die Verschiebung entlang der festen Welt-Achse; der Anker (`origin`, `startPositionMm`) wird bei `pointerdown` eingefroren, daher stören zwischenzeitliche Rebuilds den laufenden Drag nicht. Die Orbit-Steuerung pausiert während des Drags (`controls.enabled = false`).

3. **Neubewertung ausschließlich über den Core, Ampel nie veraltet-als-aktuell (ADR-007).** Nach jeder Änderung ist der Plan **dirty**; die Ampel zeigt „ungeprüft" statt eines alten Werts. Ein „Prüfen"-Button und ein Debounce (700 ms) rufen `onCheckCutPlan` → **denselben** Endpoint wie der Vorschlag (`POST /projects/{slug}/decomposition`), aber **mit** den Plan-Eingaben (`cuts`, `joint_offset_mm`, `section_overrides`). Der Core baut die Abschnittsgeometrie (`fgc.decompose.from_cuts`) + Ampel und legt sie als Lauf ab; erst die Antwort setzt die Ampel grün/rot. Ein Endpoint für Vorschlag **und** Neubewertung (ohne/mit `cuts`) statt zwei paralleler Wege — weniger API-Fläche, ein Schreibpfad (ADR-016).

4. **Fugen-Versatz + Platzierungs-Override als Plan-Eingaben.** Der Fugen-Versatz staffelt vertikale Schnitte zwischen Höhenlagen (versetzte Stoßfugen); der Override weist einem Abschnitt eine Option aus der Platzierungsliste (#22) statt der automatisch gesuchten zu. Beide sind reine Eingaben im Druckjob (`cuts`/`joint_offset_mm`/`section_overrides`), das gerechnete Ergebnis bleibt im Lauf (ADR-016). Kein neues ADR: alles im Rahmen von ADR-004/006/007/014/016.

**Prozessnotiz (kein Design):** Der #25-Subagent (sonnet) traf mitten im `druckplan.ts`-Rewrite auf ein Session-Limit; der Orchestrator hat die Teilarbeit gerettet statt sie zu verwerfen (kaputtes Anführungszeichen repariert, `main.ts`-Verdrahtung — `onCheckCutPlan`/`onCutsChanged` + Drag-Handler — nach dem Design des Subagenten fertiggestellt) und die fehlende Doku ergänzt. Der Drag-Gestus selbst ist tsc-/vitest-grün, aber nicht im Browser durchgeklickt — ein manueller GUI-Test wird empfohlen.

**Neue Dateien:** `viewer/src/ui/cutplan-state.ts`, `viewer/src/ui/cutplan-state.test.ts`.
**Geaendert:** `core/src/fgc/decompose/{__init__,plan,propose,artifact}.py` + `pipeline/{actions,api}.py` (`from_cuts`/`apply_overrides` + editierter Schnittplan im Endpoint), `core/tests/test_decompose.py`, `schemas/{decompose,project}.schema.json`, `viewer/src/render/cutplanes.ts` (Drag-Primitive: `handles`/`axisDragPlane`/`projectOntoAxis`/`setCutPlaneHighlighted`), `viewer/src/ui/druckplan.ts` (Editier-UI), `viewer/src/api/projects.ts` (`proposeDecomposition`-Editier-Parameter), `viewer/src/main.ts` (Callbacks + Drag-Verdrahtung), `README.md`, `docs/status.md`.

**Tests:** 274 Core-Tests (16 neu) + 51 Viewer-Tests (16 neu) gruen, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — Abschnitts-Slicing + Simulation aus der Platzierung (Issue #26)

**Frage:** Wie entsteht je Abschnitt des Schnittplans (#24/#25) ein druckbarer Lauf — Toolpath **und** Trajektorie — ohne CLI und **ohne gemessenes Setup**, sodass der Querschnitt Slicer + Simulation den bestehenden Code nutzt (nicht dupliziert) und alles ADR-004/007/016-konform bleibt?

**Entscheidungen:**

1. **Slicer-Eingang genutzt statt dupliziert.** `slice_wall(vertices, faces, …)` nimmt bereits ein beliebiges Mesh — also fliesst das Abschnitts-**Teil-Mesh** aus `fgc.decompose.apply(wall_mesh, plan)` direkt hinein; kein neuer Slicer-Pfad. Verworfen: eine parallele „section slicer"-Funktion (haette den Slicer gespalten). Das Wand-Mesh wird zuvor per 2D-PCA (dieselbe Konvention wie `analyze_wall_mesh`/`WallSurface`) ins **Wand-lokale** System gebracht (`_wall_local_mesh`: x = Laengsachse zentriert, z ab Fuss 0), damit die Schnittebenen des Plans (die dort leben) passen; Achsen-Vorzeichen deterministisch fixiert (Summe ≥ 0).

2. **Abschnitts-lokale Verschiebung vor dem Slicen.** Das Teil-Mesh eines Abschnitts (z. B. z 1300…2600) wird um (`-center_x`, 0, `-z0`) verschoben, bevor es gesliced wird — so liegen die Targets im **Abschnittsbereich** (z in [0, Hoehe]) und passen zur **abschnitts-lokalen** Platzierung (die `fgc.decompose` je Abschnitt als eigenstaendige, bei z=0 beginnende `WallSurface` sucht, s. Log 2026-07-24). Ohne diese Verschiebung waere die Lage-Kette Toolpath↔Platzierung um z0 versetzt. Testkriterium: max. Target-z bleibt weit unter der vollen Wandhoehe.

3. **Simulation aus dem Plan: `pose_source` in den Trajektorien-Metadaten.** `build_trajectory(..., pose_source="measured" | "planned")` stempelt `meta.pose_source`; der Wert aendert die Rechnung nicht, nur den Herkunftsnachweis. Aus der geplanten Platzierung + Endeffektor-TCP baut `_planned_setup` ein Setup-Dict: `wall_to_base = (rot_z(yaw), (lateral, standoff, stand_height))⁻¹` (dieselbe base←wand-Kette wie `fgc.placement.evaluate`), `tcp` aus der ToolDef, `deadtime` ohne Kompensation (t_tot=0 — ein Plan traegt keine gemessene Totzeit). So bleibt das gemessene Setup Voraussetzung des **echten** Drucks; nur die Simulation ist aus dem Plan zulaessig (Design-Log 2026-07-04). `fgc simulate` (gemessenes Setup) bleibt `"measured"` (Default, rueckwaertskompatibel — Altlaeufe ohne Feld gelten implizit als gemessen). Verworfen: ein „planned setup.json"-Artefakt auf die Platte schreiben — die Lage ist ein Plan, kein Setup (ADR-006); sie lebt schon im Druckjob (`placements`) und wird nur zur Simulationszeit zum Frame verrechnet.

4. **Ein regulaerer Lauf je Abschnitt, Druckjob verweist (ADR-004/016).** `simulate_section` erzeugt **einen** `slice`-Lauf mit `wallspec` + `toolpath.json` + `trajectory.json` unter einer Provenienz; der Druckjob traegt nur den **Verweis** je Abschnitt in `section_runs` (`section_id → run`, neues optionales Schema-Feld, rueckwaerts­kompatibel) — nie eingebettete Ergebnisse. Ein erneutes Simulieren desselben Abschnitts **ersetzt** den `section_runs`-Eintrag (neuer Lauf), der alte bleibt als unveraenderliches Artefakt auf der Platte. `fgc.project` bleibt die einzige Schreibstelle. Den Plan rekonstruiert `_plan_for_job` aus den Druckjob-Eingaben (`from_cuts`/`propose` + Overrides) — spiegelt `propose_decomposition`, sodass die Abschnitts-IDs mit dem Reiter Druckplan uebereinstimmen.

5. **GUI: bestehender Player, keine neue Abspiel-Logik (ADR-007).** Reiter Simulation listet die Abschnitte in `order` mit Ampel, Geometrie und je Abschnitt „Slicen + Simulieren" (Busy); die Antwort zeigt Druckzeit, max. Achsauslastung und Warnungszahl. „Im Player ansehen" laedt den Abschnitts-Lauf und ruft `showRun` — der **bestehende** Trajektorien-Player (#14/#18) im Reiter Projekt fuehrt das Replay. Der Reiter wechselt dazu auf „projekt" (dort liegen Viewport + Player-Bedienung). Formatier-/Zustandslogik (Dauer, max. Achse, Zusammenfassung) als reine TS-Funktionen (`ui/simulation-state.ts`, vitest). Deutliche Kennzeichnung „kinematisches Replay — keine Kollisionspruefung" als Badge im Reiter **und** als Lagequelle-Zeile im Player.

6. **Kein neues ADR.** Alles im Rahmen von ADR-004 (Lauf), ADR-006 (Plan vs. Setup; mm/rad), ADR-007 (Core rechnet, Viewer zeigt), ADR-012 (io-Totzeit — hier bewusst ohne Kompensation, weil Plan), ADR-014 (duenner API-Wrapper), ADR-016 (Druckjob traegt nur Verweise). Scope-Grenzen (bewusst ausgelassen): Kollisionspruefung (PRD Out of Scope), Strang/Sequenz ueber alle Abschnitte (#27), Export je Abschnitt (#29), Oeffnungen in der Schnittebene.

**Neue Dateien:** `viewer/src/ui/simulation.ts`, `viewer/src/ui/simulation-state.ts`, `viewer/src/ui/simulation-state.test.ts`, `core/tests/test_section_simulation.py`.
**Geaendert:** `core/src/fgc/simulation/build.py` (`pose_source`-Parameter + `meta.pose_source`), `core/src/fgc/pipeline/actions.py` (`simulate_section`, `SectionSimResult`, Helfer `_wall_local_mesh`/`_planned_setup`/`_plan_for_job`), `core/src/fgc/pipeline/api.py` (`POST /projects/{slug}/sections/{section_id}/simulate`), `core/tests/test_simulation.py` (pose_source-Tests), `schemas/trajectory.schema.json` (`meta.pose_source`), `schemas/project.schema.json` (`section_runs` in `print_job`), `viewer/src/artifacts/types.ts` (`TrajectoryMeta.pose_source`), `viewer/src/api/projects.ts` (`SectionRun`/`SimulateSectionResult`/`simulateSection`), `viewer/src/ui/panel.ts` (Lagequelle-Zeile im Trajektorien-Panel), `viewer/index.html` (Reiter-Simulation-Panel), `viewer/src/main.ts` (`SimulationPanel`-Verdrahtung, `openSectionRun`), `viewer/src/style.css` (Simulation-Stile), `README.md`, `docs/status.md`.

**Tests:** 284 Core-Tests (10 neu) + 58 Viewer-Tests (7 neu) gruen, ruff clean, `tsc --noEmit` clean.


## 2026-07-05 — Replay: wachsender Strang + Abschnitts-Sequenz mit Umbau-Schritt (Issue #27)

**Frage:** Wie wird das Simulations-Replay (#26: je Abschnitt ein Lauf) vom Einzel-Abschnitt zum **Gesamtablauf** — der gedruckte Strang wächst zeitgetreu mit, und die Abschnitte spielen in Druckreihenfolge mit einem sichtbaren Umbau-Schritt dazwischen — ohne dass der Viewer Fachliches rechnet (ADR-007) und ohne den bestehenden Player/`ToolpathView` zu duplizieren?

**Entscheidungen:**

1. **Strang wächst nach Trajektorien-Zeit, nicht nach Layer-Slider.** Der bestehende `ToolpathView` bekommt einen zweiten Aufdeck-Modus (`setGrowth`) statt eines Zweit-Renderers: `build` merkt je Segment den **Ziel-Target-Index**; da die Segmente innerhalb eines Layer/Art-Buckets aufsteigend nach Index abgelegt sind, ist der sichtbare Anteil ein zusammenhängendes Präfix → `geometry.setDrawRange(0, count*2)` (Binärsuche `countUpTo`). Der normierte Fortschritt f → Fraktions-Index (`targetIndexAtProgress`, `f*(n-1)`) ist **dieselbe** Zeit→Index-Abbildung wie TCP-Marker/Arm-Replay — daher wächst der Strang synchron zu Arm/TCP und ist bei Pause/Seek konsistent. Ganze Segmente (der Strang endet höchstens ein Segment hinter dem TCP, nie davor); eine Teil-Segment-Interpolation wäre Overengineering. **Travel erzeugt keinen Strang:** print ist der Strang (Travel-Linien folgen demselben Fortschritt + Travel-Schalter, nur zur Konsistenz). Verworfen: Aufdeckung nach Layer-Slider-Höhe (nicht zeitgetreu) und ein paralleler wachsender Linien-Renderer (Duplikat).

2. **Wachs-Modus als Schalter, Standard an.** „Strang wächst mit (Zeit)" schaltet zwischen Wachs-Modus (Zeit) und dem klassischen Layer-Slider (ganzer Toolpath). Standard **an** — das ist die Kernfunktion des Issues. Die Abwärtskompatibilität (Kriterium 4) bezieht sich auf die **Sequenz** (ein Abschnitt = wie bisher), nicht auf die Aufdeckung; wer den ganzen Toolpath sehen will, schaltet den Strang aus (dann greift der Layer-Slider wie zuvor). Der Umschalt-/Aufdeck-Zustand lebt in `main.ts` (`applyStrandReveal`), gefüttert aus der Player-Zeit.

3. **Gesamtzeitleiste = Abschnitts-Dauern + Umbau-Dauer, als reine Funktionen.** `trajectory/sequence.ts` (getrennt von three.js, vitest): `buildSequencePlan` reiht die Abschnitte nach `order` und legt zwischen je zwei Abschnitten einen Umbau-Schritt fester Dauer (**3 s**, reine Darstellung — kein Fachwert; die echte Umbauzeit ist Prozess, nicht Simulation); `locateSequenceTime(plan, t)` bildet die globale Zeit auf `{ sectionIndex, localTime, localFraction, phase: "printing"|"umbau", toSectionIndex, umbauFraction }` ab. Ein Zeitpunkt genau am Ende einer Druckphase zählt noch als „printing" (Umbau beginnt strikt danach); bei einem Abschnitt oder `umbau_s=0` gibt es nie eine Umbau-Phase (abwärtskompatibel). Muster: `interpolate.ts`/`simulation-state.ts`.

4. **Umbau-Schritt: Basis springt, Gedrucktes bleibt stehen.** In der Umbau-Phase ist der Arm aus, der Basis-Marker fährt von der aktuellen zur nächsten Platzierung (lineare Interpolation zwischen zwei `baseMarkerPosition`-Lagen), eine Beschriftung im Player nennt den Wechsel; die z-Lage der Basis springt mit dem Fuß der Abschnitts-Box (höhere Abschnitte → höhere Basis). Bereits gedruckte Abschnitte bleiben **kumulativ** sichtbar (`setGrowth(Infinity)`), künftige sind unsichtbar (`setGrowth(-1)`). Die Basis-Sprung-Mathematik wurde aus `placeBaseMarker` als reine `baseMarkerPosition(box, pose)` herausgezogen (+ `placeBaseMarkerInBox`) und getestet; die Abschnitts-Box leitet der Viewer aus den Toolpath-Targets ab (`targetsBox`, Darstellung).

5. **Ein zusätzlicher Modus, kein Ersatz; bestehender Player wiederverwendet.** „Gesamtablauf abspielen" (aktiv sobald `sequenceReady` — jeder Abschnitt hat einen Lauf) lädt alle Abschnitts-Läufe, stapelt ihre Toolpaths (alle in Wandkoordinaten) und treibt sie über **einen** `TrajectoryPlayer` (Dauer = Gesamtzeitleiste). Für Slider/Warnungen bekommt das bestehende Trajektorien-Panel eine **synthetische** Trajektorie (Gesamtdauer + zeitversetzt zusammengeführte Abschnitts-Warnungen, keine Samples). Der Einzelabschnitt (#26 „Im Player ansehen") bleibt unverändert anwählbar; `showRun`/`openSectionRun` verlassen den Sequenz-Modus sauber (`teardownSequence`).

6. **Kein neues ADR.** Alles Darstellungsmathematik im Rahmen von ADR-007 (Viewer zeigt, rechnet nichts), ADR-007-Klarstellung 2026-07-04 (Präsentations-FK/-Zeitachse), ADR-004/016 (Läufe/Verweise). Scope-Grenzen (bewusst ausgelassen): echte Umbauzeit/-kinematik, Kollisionsprüfung (PRD Out of Scope), Export je Abschnitt (#29).

**Neue Dateien:** `viewer/src/trajectory/sequence.ts`, `viewer/src/trajectory/sequence.test.ts`, `viewer/src/render/basemarker.test.ts`.
**Geaendert:** `viewer/src/render/toolpath.ts` (Wachs-Modus `setGrowth` + `countUpTo`), `viewer/src/render/basemarker.ts` (`baseMarkerPosition`/`placeBaseMarkerInBox`/`BoxMinMax`), `viewer/src/ui/simulation-state.ts` (`sequenceReady`) + `simulation-state.test.ts`, `viewer/src/ui/simulation.ts` (Sequenz-Button + `onPlaySequence`/`SequenceItem`), `viewer/src/ui/panel.ts` (Strang-Schalter, Sequenz-Phase, `setSequenceMode`), `viewer/index.html` (Sequenz-Button, Strang-Schalter, Phasen-Zeile), `viewer/src/style.css`, `viewer/src/main.ts` (`applyStrandReveal`, `startSequence`/`updateSequence`/`updateSequenceBase`/`syntheticSeqTrajectory`/`teardownSequence`), `README.md`, `docs/status.md`.

**Tests:** 284 Core-Tests (unveraendert) + 80 Viewer-Tests (22 neu: sequence 15, basemarker 3, sequenceReady 4) gruen, ruff clean, `tsc --noEmit` clean.

## 2026-07-05 — Endeffektor-Konfigurator: Upload, Gizmo-Ausrichtung, TCP-Marker (Issue #28)

**Frage:** Wie wird ein realer Endeffektor in der **Bibliothek** (Stammdaten außerhalb des Prozesses) hochgeladen, visuell am Roboterflansch ausgerichtet, mit TCP + logischen Kanälen versehen und abgelegt — sodass er ohne Neustart im Katalog erscheint, sein TCP von placement/Simulation identisch gelesen wird und sein Mesh im Replay am Flansch hängt, ohne dass der Viewer Fachliches rechnet (ADR-007) und ohne den bestehenden FK-/Arm-/Katalog-Code zu duplizieren?

**Entscheidungen:**

1. **Bibliothek, nicht Prozess-Reiter.** Der Konfigurator lebt im Reiter **Bibliothek** (`viewer/CONTEXT.md`: Stammdatenpflege außerhalb des Prozesses). Im Reiter Roboter wird nur *gewählt*, gepflegt wird hier. Kein neuer Prozess-Reiter.

2. **Mesh-Formate STL/OBJ/GLB, Koordinaten = mm (ADR-006).** STL/OBJ sind einheitenlose Dreiecksnetze, GLB binäres glTF; alle drei werden 1:1 als mm interpretiert (konsistent zu allen Artefakten). Ein Skalierungsfehler fällt beim Ausrichten am Flansch sofort auf. Verworfen: automatische Einheiten-Heuristik (rät, überrascht); STEP/IGES (bräuchte einen CAD-Kernel).

3. **Upload über die API als base64-in-JSON (ADR-014).** `POST /tools` nimmt das Mesh base64-kodiert im JSON-Body (plus `mesh_filename` fürs Format) statt multipart/form-data — konsistent zur bestehenden reinen JSON-API (CORS/Fehlerbehandlung schon dafür ausgelegt) und einfacher, weil die Metadaten (Kanäle als Dict, zwei Frames) komplexes JSON sind. Endeffektor-Meshes sind klein; eine Größengrenze (50 MB) + Ladbarkeitsprüfung (trimesh) fangen Fehlbedienung ab. Verworfen: multipart (mischt komplexes JSON in Formfelder); In-Memory-Upload ohne Ablage (widerspricht ADR-004/016 — Stammdaten liegen auf der Platte).

4. **Ablageort = Tools-Verzeichnis, Name datei-sicher + zugleich `name`-Feld.** `create_tool_from_upload` normalisiert den Namen (`safe_tool_name`, analog `project_slug`, aber mit `_`), legt `<name><suffix>` (Mesh) und `<name>.json` (Definition) ab und lädt zurück (validiert erneut). Der Name ist Dateiname *und* Referenz im Druckjob (`tool`). Gleicher Name überschreibt (Stammdaten-Pflege). `GET /tools` findet den neuen Endeffektor ohne Neustart. Die Validier-/Bau-Logik sitzt in `fgc.domain.tool` (`validate_mesh_bytes`/`build_tool_artifact`/`safe_tool_name`/`mesh_suffix`) — testbar, die Aktion bleibt dünn (schreibt nur).

5. **Flansch-Transform-Konvention: Kind der Flansch-Gruppe.** `ArmView` bekommt eine `flange`-Kind-Gruppe, deren Matrix je Pose auf den Flansch-Frame (`forwardChain[6]`) gesetzt wird. Wer ihr Objekte hinzufügt (Endeffektor-Mesh, TCP-Marker, Achsenkreuz), arbeitet direkt in **Flansch-Koordinaten** — das lokale Transform eines Kindes *ist* seine Lage relativ zum Flansch. So liefert der Gizmo (`TransformControls` am Mesh bzw. TCP-Marker) ohne Extra-Rechnung die gespeicherten Frames; im Konfigurator steht der Arm in **Home-Pose** mit identischem Anker (`identity()`), im Replay trägt derselbe Mechanismus das Mesh an den bewegten Flansch. Kein Neubau der FK/Arm-Kette (#18 wiederverwendet).

6. **Schema rückwärtskompatibel um `mesh_transform` erweitert.** `tool.schema.json` hatte `mesh` (Dateiname) bereits (optional); neu ist das optionale Feld **`mesh_transform`** (Frame, Lage des Mesh relativ zum Flansch, `setup.schema.json#/$defs/frame`). Fehlt es, gilt Identität (Mesh-Ursprung im Flansch) — Altdefinitionen (z. B. `two_component_nozzle.json`) bleiben gültig. Der TCP nutzt das bestehende `tcp_frame` unverändert — daher liest placement/Simulation (`_planned_setup`, #26) den im Konfigurator gesetzten TCP **identisch** (Konsistenztest: `create_tool_from_upload` → `ToolDef.load` → `_planned_setup(...)['tcp']` == gesetzter TCP).

7. **Gizmo/TCP als reine Darstellung; nur die Umrechnung getestet (ADR-007, PRD Testing Decisions).** `TransformControls` (Translate/Rotate, `setSpace("local")`) bewegen Mesh bzw. TCP-Marker nur zur Anzeige; die Orbit-Steuerung pausiert während des Ziehens (`dragging-changed`). Beim Speichern werden die lokalen Transforms zu Frames — die Umrechnung `frameFromPosQuat` (three `{x,y,z,w}` → Schema `[w,x,y,z]`) und der Payload-Bau `buildCreateToolRequest` (Validierung: Name, Mesh, ≥1 Kanal, kein Doppelkanal, Gewicht ≥ 0) sind reine TS-Funktionen ohne three.js, mit vitest getestet. Die Gizmos selbst bewusst ohne Test (visuell geprüft).

8. **Mesh im Replay am Flansch, sonst wie bisher.** Der Simulations-Arm (#18/#27) bekommt optional das Mesh des Druckjob-Endeffektors an den Flansch gehängt (`GET /tools` liefert dazu `mesh_path` als absoluten Pfad → `/@fs/`-URL, wie `model.glb`; `mesh_transform` als Lage). Fehlt Tool/Mesh, bleibt das Replay unverändert (abwärtskompatibel). Kein neuer Renderpfad — dieselbe `loadToolMesh`-Funktion wie im Konfigurator (STL/OBJ/GLB → Object3D).

9. **Kein neues ADR.** Alles im Rahmen von ADR-004 (Ablage), ADR-006 (mm/rad; Frames; TCP), ADR-007 (Core validiert/legt ab, Viewer zeigt), ADR-011 (logische Kanäle), ADR-013 (Payload = Befund, kein Gate), ADR-014 (dünner API-Wrapper), ADR-016 (Endeffektor = Stammdaten-Artefakt, Druckjob referenziert). Scope-Grenzen (bewusst ausgelassen): Momenten-/Dynamik-Check (v1 nur statischer Payload), Kanal-Mapping (bleibt im Setup), Editieren bestehender Endeffektoren im UI (Überschreiben per gleichem Namen genügt v1), Kollisions-/Reichweiten-Vorschau im Konfigurator.

**Neue Dateien:** `viewer/src/render/toolmesh.ts`, `viewer/src/ui/configurator.ts`, `viewer/src/ui/configurator-payload.ts`, `viewer/src/ui/configurator-payload.test.ts`, `core/tests/test_tool_configurator.py`.
**Geaendert:** `schemas/tool.schema.json` (`mesh_transform`), `core/src/fgc/domain/tool.py` (Feld + `safe_tool_name`/`mesh_suffix`/`validate_mesh_bytes`/`build_tool_artifact`), `core/src/fgc/pipeline/actions.py` (`create_tool_from_upload`, `CreateToolResult`), `core/src/fgc/pipeline/api.py` (`FrameModel`, `POST /tools`, `ToolInfoModel.mesh_path`/`mesh_transform`, `_tool_info_model`), `viewer/src/render/arm.ts` (`flange`-Gruppe + `attachToFlange`/`clearFlange`), `viewer/src/api/projects.ts` (`createTool`, `Frame`/`CreateToolRequest`, `ToolDef.mesh_path`/`mesh_transform`), `viewer/index.html` (Bibliothek-Panel), `viewer/src/main.ts` (Konfigurator-Verdrahtung, `attachToolMeshToArm`, `loadedTools`), `viewer/src/style.css`, `README.md`, `docs/status.md`.

**Tests:** 305 Core-Tests (21 neu) + 88 Viewer-Tests (8 neu) gruen, ruff clean, `tsc --noEmit` clean, `vite build` gruen.

## 2026-07-05 — Export-Reiter (DRL je Abschnitt) + veraltet-Markierung (Issue #29)

**Frage:** Wie schließt der Reiter **Export** den Prozess ab — je Abschnitt ein DRL-Programm, ehrlich gegenüber dem fehlenden gemessenen Setup — und wie wird die **Querschnitts-Konsistenz** zwischen den Reitern gesichert, sodass sich ändernde Eingaben (Wand, Roboter, Endeffektor, Schnittplan) nachgelagerte Stände (Druckplan, Simulation, Export) sichtbar als *veraltet* markieren, ohne sie zu löschen und ohne dass der Viewer Fachliches rechnet (ADR-007)?

**Entscheidungen:**

1. **DRL über die bestehende Emit-Aktion, nicht neu implementiert.** `export_section_drl` (API `POST /projects/{slug}/sections/{section_id}/export`) ist ein dünner Wrapper: mit gemessenem Setup im Abschnitts-Lauf ruft er die bestehende `emit_drl_run`/`fgc.postproc.emit_drl` (#13, Change-on-Delta, Kanal-Mapping ADR-011, Grad-Konvertierung ADR-006). Die `program.drl` landet im Abschnitts-Lauf (ADR-004, Provenienz als Kommentarblock) — genau wie `fgc emit-drl` es schon tat. Voraussetzung ist ein simulierter Abschnitt (`section_runs`, #26), der die `trajectory.json` trägt.

2. **Ohne Setup: gekennzeichneter Antasten-Hinweis statt unmarkiert unvollständigem Programm — kein Gate.** Ohne gemessenes Setup fehlt das Kanal-Mapping (ADR-011); ein vollständiges, fahrbares Programm ist nicht erzeugbar. Statt eines *unmarkiert* unvollständigen (versehentlich fahrbaren) Programms schreibt der Core eine reine **Kommentar-Ausgabe** („UNVOLLSTÄNDIG — Antasten fehlt" + Kernsatz + Provenienz), das Ergebnis trägt `complete=false`, `setup_source="none"` und den `note`-Hinweis. Der Nutzer *darf* trotzdem exportieren (ADR-006/013: Befund, kein Gate), aber unmissverständlich gekennzeichnet. Verworfen: io-loses movej-Programm erzeugen (dupliziert den Emitter, wäre ein fahrbares Teilprogramm ohne Materialsteuerung — irreführend); Export ohne Setup blockieren (widerspricht „Befund, kein Gate").

3. **Übergabe-Checkliste mit Plan-vs.-Setup-Kernsatz.** Der Reiter zeigt statisch **aufbauen → antasten (→ Setup) → drucken** mit dem Kernsatz „Die Platzierung ist ein Plan — verbindlich wird die Lage erst durchs Antasten" (ADR-006, `core/CONTEXT.md`) — die eine Stelle, die den Nutzer an das Antast-Verfahren erinnert, bevor er ein DRL fährt.

4. **veraltet-Markierung = Revisionsstände im Projekt, Ableitung als reine Funktion.** Modelliert im `project.json` je Druckjob als `revisions`: `inputs` = ein Zähler je Eingabe-Stufe (`wall`/`robot`/`tool`/`cutplan`), erhöht bei Änderung; `outputs` = je nachgelagerter Stufe (`druckplan`/`simulation`/`export`) der **Schnappschuss** der Eingabe-Zähler zum Zeitpunkt der letzten Erzeugung. Ein Output ist *veraltet*, wenn eine von ihm beobachtete Eingabe-Revision neuer ist als sein Schnappschuss. Das **Setzen** (bump/refresh) passiert ausschließlich im Core (`fgc.project.revisions`, aufgerufen aus den Aktionen — `fgc.project` bleibt die einzige Schreibstelle, ADR-016): Roboterwechsel bumpt `robot`, Endeffektorwechsel `tool`, neue Wand `wall`, neuer Schnittplan `cutplan`; `evaluate_placements`/`suggest`/`propose_decomposition` frischen `druckplan` auf, `simulate_section` `simulation`, `export_section_drl` `export`. Die **Ableitung** „ist X veraltet?" ist eine **reine TypeScript-Funktion** (`ui/staleness.ts`, three.js-frei, vitest) mit einer Python-Parität (`fgc.project.output_status`, pytest).

5. **Beobachtete Eingaben pro Output — der Schnittplan veraltet nicht sich selbst.** `druckplan` beobachtet `wall/robot/tool` (nicht `cutplan` — die Zerlegung *erzeugt* den Schnittplan); `simulation` und `export` beobachten zusätzlich `cutplan`. So markiert ein Roboterwechsel alle drei Stufen (Akzeptanzkriterium), eine reine Schnittplan-Änderung nur Simulation/Export. Das Neuerzeugen der jeweiligen Stufe hebt die Markierung **stufenweise** auf (Druckplan → Simulation → Export), weil jeder Refresh nur seinen eigenen Schnappschuss aktualisiert.

6. **Nichts wird gelöscht; rückwärtskompatibel.** Die Markierung ist Zusatzinfo, kein Gate: veraltete Stände bleiben sichtbar (Badges im Reiter Export, `stage-stale`), die referenzierten Läufe unberührt. Bestehende Projekte ohne `revisions`-Feld laden unverändert und gelten als **nicht veraltet** (Default in beiden Ableitungen). Das Schema wurde additiv um `print_job.revisions` (+ `revision_snapshot`-$def) erweitert.

7. **ADR-017 angelegt.** Die veraltet-Markierung hat Architekturrang (Querschnitts-Konsistenz, zweites Konsistenzmodell neben den Läufen) → **ADR-017** hält Revisionsstände-Modell + reine Ableitung fest; dieser Log-Eintrag verweist darauf. Die Export-Aktion selbst bleibt im Rahmen bestehender ADRs (004/006/011/013/014/016).

**Neue Dateien:** `core/src/fgc/project/revisions.py`, `core/tests/test_export.py`, `viewer/src/ui/staleness.ts`, `viewer/src/ui/staleness.test.ts`, `viewer/src/ui/export.ts`, `docs/adr/ADR-017-veraltet-markierung-revisionsstaende.md`.
**Geaendert:** `schemas/project.schema.json` (`revisions` + `revision_snapshot`), `core/src/fgc/project/__init__.py` (Export der Revisions-Helfer), `core/src/fgc/pipeline/actions.py` (`export_section_drl`/`ExportDrlResult`/`_write_antasten_stub`/`ANTASTEN_HINT`; Revisions-Bumps/-Refreshes in `set_print_job`/`reassess_walls_for_robot`/`set_tool_for_job`/`evaluate_placements`/`propose_decomposition`/`simulate_section`), `core/src/fgc/pipeline/api.py` (`POST …/export`), `viewer/src/api/projects.ts` (`ExportDrlResult`/`exportSectionDrl`, `PrintJob.revisions`), `viewer/index.html` (Export-Panel), `viewer/src/main.ts` (Export-Verdrahtung, `refreshRevisions`), `viewer/src/style.css`, `README.md`, `docs/status.md`.

**Tests:** 318 Core-Tests (13 neu) + 93 Viewer-Tests (5 neu) gruen, ruff clean, `tsc --noEmit` clean, `vite build` gruen. **Damit ist PRD #15 (interaktiver Viewer) komplett.**

## 2026-07-05 — Doppelklick-Start reparieren: Projektliste statt Lauf-Deeplink + selbstheilende API

**Frage:** Nach dem PRD-#15-Batch (#16–#29, ADR-016) ließ sich das Programm über
`start_viewer.cmd` nicht mehr sinnvoll starten — der Doppelklick landete in einem
zustandslosen Lauf, in dem alle neuen Reiter „Kein Projekt geöffnet" meldeten. Wie
sieht der „schöne, einfache Start" aus, der zur neuen projektbasierten Architektur
passt, und warum wirkte der Start überhaupt kaputt?

**Diagnose:** Zwei Ursachen, die zusammenfielen.
1. **Falscher Einstieg.** `start_gui()` (aus der Grill-Session bd1cfdd, vor ADR-016)
   öffnete per `?run=<neuester model_map-Lauf>` einen **rohen Laufordner** — der
   „Fallback-Direkteinstieg" für Dev/Automation. Damit bleibt `currentProjectSlug`
   null, also melden Reiter Roboter/Druckplan/Simulation/Export „Kein Projekt
   geöffnet". Nach ADR-016 ist die **Projektliste** der kanonische Einstieg.
2. **Veralteter API-Server.** Auf Port 8765 hing ein `uvicorn` vom Vortag (vor dem
   Batch), der nur `POST /slice` kannte. `ensure_api_server()` prüfte die Lebendigkeit
   über `/docs` — das beantwortet auch der alte Server — und startete ihn daher nie
   neu. Der frische Viewer redete also gegen eine alte API; `GET /projects` gab 404,
   die Projektliste blieb leer/fehlerhaft.

**Entscheidungen:**

1. **`start_gui()` öffnet die Projektliste (`VIEWER_URL` ohne `?run=`).** Der
   Doppelklick fährt beide Server hoch und landet auf der Projektliste (ADR-016) —
   Projekt öffnen oder neu aus IFC anlegen. Der `?run=`-Deeplink bleibt in `main.ts`
   als Dev/Automation-Fallback erhalten, ist aber nicht mehr der Doppelklick-Weg.
   `newest_model_run()` bleibt als (nun ungenutzter) Helfer stehen.

2. **API-Gesundheitscheck wird versionsbewusst.** `is_api_running()` prüft jetzt
   `/openapi.json` auf die `/projects`-Routen statt nur `/docs`. So gilt ein
   veralteter Server korrekt als „nicht die aktuelle API". Dieselben Helfer nutzt der
   Wizard (`open_run`), der damit ebenfalls gehärtet ist.

3. **Selbstheilender Start: veralteten Server auf dem Port ersetzen.** Ist die
   aktuelle API nicht erreichbar, aber der Port belegt (`_listening_pids`), räumt
   `ensure_api_server()` den Port frei (`_free_port`: Windows `taskkill`, sonst
   `SIGTERM`) und startet die aktuelle API. Ohne das Freimachen könnte `uvicorn` den
   Port nicht binden und der Viewer bliebe an der alten API kleben. Verworfen:
   `psutil` als Abhängigkeit (nicht installiert, unnötig für den einen Port); auf
   jeden Start hart neustarten (würde einen gesunden laufenden Server unnötig killen).

4. **Port-Erkennung sprachunabhängig + IPv6-tauglich.** Erste Fassung filterte
   `netstat`-Zeilen auf den Status `"LISTENING"` — auf deutschem Windows heißt der
   aber `"ABHÖREN"`, also fand sie nichts. Der lauschende Socket wird jetzt am
   **Wildcard-Fernziel** (`0.0.0.0:0` / `[::]:0`) und **PID > 0** erkannt (WARTEND-
   Zeilen tragen PID 0) — lokalisierungsunabhängig. `-p TCP` (nur IPv4) wurde
   entfernt, damit auch IPv6-Sockets erfasst werden (Vite lauscht auf `[::1]:5173`).

**Geaendert:** `core/src/fgc/pipeline/viewer_launch.py` (`start_gui`, `is_api_running`,
`ensure_api_server`, neu `_listening_pids`/`_free_port`), `README.md`, `docs/status.md`.

**Tests:** Kein automatischer Test für den Launcher (keiner vorhanden). Manuell
verifiziert: (a) frischer Start → `GET /projects` 200, Viewer öffnet die Projektliste;
(b) Integrationstest mit simuliertem Alt-Server (nur `/docs`, kein `/projects`) →
`is_api_running()` False, `ensure_api_server()` ersetzt ihn, danach `/projects`
vorhanden; (c) `_listening_pids` erkennt API (IPv4) und Vite (IPv6). ruff clean.

## 2026-07-05 — Blank-Screen beim Start: verlorenes index.html/style.css-Markup aus Issue #25

**Frage:** Nach dem Launcher-Fix (Eintrag oben) zeigte der Viewer weiterhin *nichts* —
leere Seite statt Projektliste. Warum, obwohl tsc/vitest/vite build grün?

**Diagnose:** Headless-Browser (Edge `--dump-dom` + `--enable-logging=stderr`) zeigt:
`Uncaught Error: Element #decompose-cuts fehlt in index.html`. Der `DruckplanPanel`-
Konstruktor (Modul-Top-Level in main.ts) wirft → das gesamte Bundle stirbt vor
`showProjectList` → alle Elemente bleiben `hidden` → weißer Bildschirm.
Ursache: Beim Issue-#25-Subagenten (Session-Limit mitten im druckplan.ts-Rewrite,
s. PRD-#15-Lehren) wurden druckplan.ts + main.ts gerettet, aber die zugehörigen
**index.html- und style.css-Ergänzungen gingen verloren**: 5 Element-IDs
(`decompose-cuts`, `decompose-add-horizontal-btn`, `decompose-add-vertical-btn`,
`decompose-joint-offset`, `decompose-check-btn`) + Styles (Schnittzeilen,
`ungeprueft`-Ampel, `decompose-override`). tsc kann fehlende DOM-IDs nicht sehen
(`byId<...>("...")` mit Non-Null-Semantik); die vitest-Suiten testen reine Logik
ohne index.html — deshalb blieb alles grün.

**Entscheidungen:**

1. **Fehlendes #25-Markup nachgetragen:** Schnittplan-Block im Reiter Druckplan
   (Schnittliste, + Höhenschnitt/+ Längsschnitt, Fugen-Versatz-Feld, Prüfen-Button)
   in `viewer/index.html`; Styles in `viewer/src/style.css` (inkl. `ungeprueft` =
   orange Ampel für editierte, noch nicht neu bewertete Schnittpläne). Veralteter
   „Read-only … folgt (#25)"-Hinweistext (index.html + README) korrigiert.

2. **Verifikation per Headless-Browser, nicht nur Typcheck:** Edge headless
   (`--dump-dom`, Console via stderr-Logging) — Projektliste sichtbar, keine
   Uncaught Errors. Genau die Lücke, die tsc/vitest nicht abdecken (Verdrahtung
   Code ↔ statisches HTML). ID-Abgleich `byId/getElementById` ↔ `index.html`
   ergibt 0 fehlende IDs.

**Lehre (Prozess):** Wenn ein Subagent mitten in einem Multi-File-Feature stirbt,
reicht „Code kompiliert + Tests grün" als Rettungs-Kriterium nicht — statische
Assets (index.html, style.css) gehören explizit gegen die Element-Referenzen des
geretteten Codes geprüft. Ein Smoke-Test im echten Browser nach jedem Batch hätte
das sofort gezeigt (war als offener Punkt notiert).

**Geaendert:** `viewer/index.html`, `viewer/src/style.css`, `README.md`.
**Tests:** tsc clean; Headless-Render: Projektliste sichtbar, Console fehlerfrei.

## 2026-07-05 — Reiter-Klicks wirkungslos + zwei Slice-artige Buttons im Eignungsbericht

**Frage:** Beim manuellen Durchklicken (erster echter GUI-Test der 5-Reiter-Kette,
war als offener Punkt notiert): (a) Klicks auf die Tab-Leiste wechseln den Reiter
nicht — der Reiter Projekt bleibt stehen; (b) nach Klick auf eine Wand stehen
„Diese Wand slicen" und „In Druckjob übernehmen" nebeneinander — zwei Buttons,
die beide nach Slicen klingen. Warum, obwohl tsc/vitest (inkl. tabs.test) grün?

**Diagnose (a):** Kein JS-Fehler — eine CSS-Kaskaden-Falle. `.tab-panel[hidden]
{ display: none }` (style.css) hat dieselbe Spezifität (0,2,0) wie die späteren
Panel-Regeln `.tab-panel[data-panel="projekt"] { display: flex }` und
`.tab-panel[data-panel="bibliothek"] { display: flex }` — bei Gleichstand gewinnt
die Quellordnung, also blieben Projekt- und Bibliothek-Panel trotz gesetztem
`hidden`-Attribut sichtbar. Das Projekt-Panel (100 % Höhe) verdeckte jeden anderen
Reiter; `shell.setActiveTab` arbeitete korrekt (deshalb grüne Tests — vitest prüft
Attribute, keine CSS-Kaskade). `#project-list`/`#active-job-bar` haben eigene
`[hidden]`-Regeln mit ID-Spezifität und waren nicht betroffen.

**Entscheidungen:**

1. **`#tab-body .tab-panel[hidden] { display: none }`:** ID im Selektor hebt die
   Spezifität über jede `.tab-panel[data-panel=…]`-Regel — robust auch gegen
   künftige Panel-Regeln weiter unten in der Datei. Verworfen: `!important`
   (Holzhammer, versteckt das eigentliche Problem); Regeln umsortieren (fragil —
   die Bibliothek-Regel liegt 1000 Zeilen tiefer, der nächste Anbau bräche es wieder).

2. **Genau eine Primäraktion je Modus im Eignungsbericht:** Im Projektfluss
   (Projekt geöffnet) erscheint nur noch „In Druckjob übernehmen" — gesliced wird
   dort je Abschnitt über den Reiter Simulation (ADR-016). Das Direkt-Slicing
   „Diese Wand slicen" (Issue #10) bleibt dem Abspieler-Modus ohne Projekt
   (`?run=`-Deeplink) vorbehalten; dort ist umgekehrt der Übernehmen-Button
   versteckt (kein Projekt = kein Ziel). Verworfen: beide Buttons zeigen und nur
   umbenennen (die Doppelung selbst ist das Missverständnis); Direkt-Slicing ganz
   entfernen (bricht den dokumentierten Abspieler-/Dev-Weg).

**Geaendert:** `viewer/src/style.css` (`#tab-body .tab-panel[hidden]`),
`viewer/src/ui/panel.ts` (`showWallReport`: Sichtbarkeit nach `_projectOpen`),
`README.md`.
**Tests:** tsc clean, 93 vitest grün; Headless-Edge-Smoke (echte Kaskade):
verstecktes Projekt-/Bibliothek-Panel jetzt `display: none`, sichtbare Panels
sichtbar; App-Start ohne Uncaught Errors, Projektliste sichtbar.

## 2026-07-05 — Bug-Durchklick Teil 2: leere Prozess-Reiter → geteiltes Hauptsichtfeld, Roboter-Vorschau, 11 verifizierte Bugs (#30–#39)

**Frage:** Nutzer-Befund: In den Reitern Roboter/Druckplan/Simulation/Export ist
nur das linke Panel sichtbar — nichts im Hauptsichtfeld; außerdem fehlt ein
3D-Modell des Roboters. Ursache? Und welche weiteren Fehler stecken in der
Reiter-Kette (war als offener Punkt notiert: Druckplan→Export ungeprüft)?

**Vorgehen:** (1) Headless-Durchklick per CDP in Edge (Screenshots +
getComputedStyle-Diagnose) — reproduziert; (2) Multi-Agent-Review (Workflow:
10 Finder-Blickwinkel → adversariale Verifikation → Sweep). Die 10 Finder
fielen dem Subagenten-Session-Limit zum Opfer; Sweep + 6 Verifizierer liefen
durch und lieferten 6 zusätzliche Befunde (5× CONFIRMED, 1× PLAUSIBLE). Alle
11 Befunde wurden **zuerst** als Issues #30–#39 gesichert, dann mit je einem
roten Test nachgewiesen, dann gefixt. Offener Punkt: die 10 Finder-Blickwinkel
sind nie vollständig gelaufen — eine erneute Tiefenprüfung lohnt.

**Diagnose Kernbefund (#30):** Kein CSS-/JS-Fehler, sondern eine Struktur-Lücke:
nur die Panels „projekt" und „bibliothek" enthielten überhaupt ein `<main>` mit
Canvas — die anderen vier Reiter bestanden nur aus dem Aside. PRD #15 verlangt
aber Schnittebenen-Drag *im 3D* (Story 16, Reiter Druckplan) und sichtbares
Arm-Replay (Stories 23–25, Reiter Simulation); die Hint-Texte verwiesen als
Notlösung auf „(Reiter Projekt)".

**Entscheidungen:**

1. **Geteiltes Hauptsichtfeld (#30):** Das eine `<main id="viewport">` wandert
   aus dem Projekt-Panel heraus und liegt als Geschwister neben den Panels in
   `#tab-body` (flex) — Reiterwechsel tauscht nur das Aside, Szene/Kamera/
   WebGL-Kontext bleiben stehen; der ResizeObserver in `scene/setup.ts` fängt
   die Breitenänderung. Bibliothek behält ihre eigene Szene (`#cfg-viewport`),
   dort wird `#viewport` versteckt (`ui/shell.ts`). Verworfen: ein Viewport je
   Reiter (mehrere WebGL-Kontexte + Zustandssync); Canvas beim Wechsel
   umhängen (Reparenting-Flackern, fragil). DOM-Vertrag als vitest
   (`shell-structure.test.ts` liest index.html) — genau die Lücke, die den
   Bug an tsc/vitest vorbeigelassen hat.
2. **Roboter-Vorschau als Szenenmodus (#31):** Eigene z-hoch-Gruppe
   `robot-vorschau` neben `world`; im Reiter Roboter wird `world` aus- und die
   Vorschau eingeblendet (Kapsel-Arm Home-Pose + Flansch-Achsen + Endeffektor-
   Mesh des Druckjobs, wechselt live). Kamerastand der Modellübersicht wird
   gemerkt und beim Verlassen zurückgesetzt (inkl. near/far). Zuordnung Reiter→
   Szene als reine Funktion `ui/scene-mode.ts` (vitest). Verworfen: Arm in die
   Modellübersicht stellen (geht im Gebäude unter, falscher Maßstabskontext).
3. **Schnittebenen-Orientierung (#34):** `render/cutplanes.ts` rotierte nach
   y-hoch-Konvention in der z-hoch-Weltgruppe — Höhenschnitte lagen wandparallel
   im Wandinneren, Längsschnitte als wanddicken-hohe Finne. Fix: Orientierung/
   Lage als reine Funktion `cutPlaneSpec` (z-hoch; Euler-Golden-Test via three)
   + Überstand `CUT_PLANE_OVERHANG_MM = 150`, damit Ebenen sichtbar aus der
   Wand ragen und greifbar sind.
4. **Schnittplan-Restore (#35):** `onOpenProject` reicht jetzt
   `cuts`/`joint_offset_mm`/`section_overrides` aus dem Druckjob an
   `restoreFromJob` durch — vorher war die Schnittliste nach Neuladen leer,
   „Prüfen" tot, 3D-Drag ein stiller No-op, und die erste Änderung überschrieb
   den persistierten Plan.
5. **Lost-Update-Schutz (#36):** Generation-Zähler je Plan-Änderung; eine
   Prüf-Antwort wird nur angewendet, wenn die Generation noch stimmt (sonst
   verworfen), und ein Prüfwunsch im Busy-Fenster wird nachgeholt statt
   verworfen. Frischer Zerlegungsvorschlag/Projekt-Restore entwerten laufende
   Prüfungen. Verworfen: Eingaben während der Prüfung sperren (nimmt dem
   Editieren den Fluss; PRD will Debounce-Bedienmuster).
6. **Klick-Kaperei am Schnittebenen-Drag (#37):** pointerdown raycastet jetzt
   auch das Modell und lässt der näheren Wandfläche den Vortritt
   (Verdeckungstest — gegriffen wird am sichtbaren Überstand); Commit nur bei
   |delta| > 0; `moveCut` ist bei unveränderter Position ein No-op (kein
   dirty, kein unnötiger Core-Lauf pro Klick). Zusätzlich Guards: Wandauswahl
   nur im Reiter Projekt, Ebenen-Drag nur Projekt/Druckplan.
7. **Teardown-Symmetrie (#38):** `resetRunState()` extrahiert — showRun UND
   startSequence räumen jetzt identisch ab (modelObject & Co. genullt,
   Reslice-Panel zu). Vorher: Ghost-Picking auf der detachten Modellgruppe im
   Sequenz-Modus.
8. **Warnungs-Deckelung (#32) + Stundenformat (#33):** `summarizeWarnings`
   (reine Funktion): Kopfzeile „N Warnungen gesamt (412× reach …)" + erste 20
   + Restzeile statt hunderter `<li>`; `formatTime` kennt jetzt „7:28:19 h"
   (Sekunden vor der Zerlegung gerundet — kein „:60"). Projektlisten-Status
   wird nach Erfolg geleert.
9. **API-Probe: Timeout ≠ veraltet (#39):** `_probe_api` klassifiziert
   current/stale/timeout/down; `_startup_probe` gibt bei Timeout eine geduldige
   zweite Probe (5 s). Ersetzt (taskkill) wird nur „stale"/„down"-mit-Belegung —
   nie wegen eines Timeouts, denn auch die gesunde API kann den GIL sekundenlang
   an ifcopenshell/trimesh verlieren. Bei Timeout: Hinweis + weiterlaufen lassen.
10. **UI-Smoke als dauerhaftes Skript:** `viewer/scripts/ui_smoke.mjs` (CDP,
    headless Edge) prüft je Reiter sichtbares Canvas, Bibliotheks-Sonderfall,
    Warnungs-Deckelung und Stundenformat im echten Browser — die Klasse Fehler,
    die tsc/vitest strukturell nicht sehen (zweiter Beleg nach dem
    Reiter-Kaskaden-Bug vom Vormittag).

**Geaendert:** `viewer/index.html`, `viewer/src/style.css`,
`viewer/src/ui/shell.ts`, `viewer/src/main.ts`, `viewer/src/ui/druckplan.ts`,
`viewer/src/ui/cutplan-state.ts`, `viewer/src/ui/panel.ts`,
`viewer/src/ui/warnings.ts` (neu), `viewer/src/ui/scene-mode.ts` (neu),
`viewer/src/render/cutplanes.ts`, `viewer/src/trajectory/interpolate.ts`,
`viewer/scripts/ui_smoke.mjs` (neu), `core/src/fgc/pipeline/viewer_launch.py`,
Tests (5 neue vitest-Dateien + Erweiterungen, `core/tests/test_viewer_launch_probe.py`),
`README.md`, `docs/status.md`.
**Tests:** 330 pytest + 123 vitest grün (alle neuen Tests zuerst rot), tsc
clean, ruff clean, `vite build` grün; UI-Smoke bestanden (Canvas sichtbar in
allen 5 Prozess-Reitern, Roboter-Vorschau im Screenshot verifiziert,
Warnungsliste 22 statt hunderter Einträge, Dauer „7:28:19 h").

## 2026-07-05 — M1013-Meshes: Bezugsquelle, Format, Kinematik (Grill-Session → #40/#41)

**Frage:** Wie kommt das echte 3D-Modell des Doosan M1013 in den Viewer —
native Dateien (DAE/STL) direkt parsen oder einmalig konvertieren, und woher
kommen die Bytes?

**Alternativen und Entscheidungen (je Ast):**

1. **Bezugsquelle:** Laufzeit-Download von GitHub (Netzpflicht, kein Pinning)
   und Nutzer-Upload wie beim Endeffektor (#28, Handarbeit für den fest
   verdrahteten Primärroboter) verworfen. → **Einmalig vendoren**, Quelle
   `doosan-robotics/doosan-robot2` (BSD-3-Clause), Commit-Hash gepinnt.
2. **Originale vs. Derivate:** Nur-GLB verworfen, weil Kollisionskontrolle/
   Simulation später im **Core** rechnen (ADR-007: Viewer urteilt nicht) und
   dafür die URDF-`<collision>`-Geometrie brauchen — nie die Viewer-GLBs
   (Draco/Quantisierung wäre ohnehin tabu als Numerik-Input). →
   `third_party/doosan_m1013/` (URDF + visual+collision Meshes + LICENSE +
   UPSTREAM.md) als Quelle der Wahrheit; `viewer/public/robots/m1013/*.glb`
   nur abgeleitetes Präsentations-Artefakt.
3. **Nativ parsen vs. konvertieren:** ColladaLoader im Viewer (Laufzeit-
   Skalierung m→mm, langsameres/fragileres Parsing, +1 Loader im Bundle)
   verworfen. → **Konvertierskript** `core/scripts/convert_robot_meshes.py`
   mit trimesh (schon Core-Dependency; kein Blender/assimp); mm-Skalierung
   wird eingebacken. Kein Draco (kein WASM-Decoder in Bundle/ui_smoke;
   nachrüstbar).
4. **Kinematik:** urdf-loader (npm) verworfen — wäre eine zweite, ungeprüfte
   FK neben der golden-orakel-validierten Präsentations-FK und umginge das
   geplante Schema „DH aus Roboterdefinition" (robots/doosan_m1013.json). →
   **Eigene DH-FK bleibt einzige Wahrheit**; je Glied ein konstanter Offset
   URDF-Linkframe↔DH-Gliedframe (posenunabhängig, da beide Frames starr am
   selben Glied; einmalig in Nullstellung berechnet) wird als Root-Node-
   Transform ins GLB gebacken — ArmView setzt `mesh.matrix = frames[i]`,
   keine zweite Zahlenquelle.
5. **Zylinder-Arm:** Entfernen verworfen (GLB-Ladefehler = unsichtbarer
   Roboter, Klasse „weißer Bildschirm bei grünen Checks" vom 05.07.). →
   **UI-Toggle** „Schema-Darstellung" im Roboter-Reiter (Nutzerwunsch,
   perspektivisch als Kollisions-Schema-Ansicht), Default Mesh, bei
   Ladefehler automatischer Fallback auf Zylinder + Sperrung des Toggles.

**Umsetzung:** als Issues #40 (Vendoring + Konvertierung, ready-for-agent)
und #41 (ArmView-Rendering + Toggle, blocked-by #40) — getrennt von den noch
uncommitteten Bugfixes #30–#39.

## 2026-07-05 — Tiefenprüfung 2 (nachgeholt): 37 verifizierte Befunde, Fixes für #42–#47/#49

**Frage:** Die beim ersten Multi-Agent-Review dem Session-Limit zum Opfer
gefallenen 10 Finder-Blickwinkel wurden nachgeholt (Stand e14113d, 48 Agenten,
56 Kandidaten → 37 CONFIRMED/PLAUSIBLE, 0 widerlegt). Darunter drei
unvollständige eigene Fixes — was ist zu härten?

**Befunde/Entscheidungen (Issues #42–#50, Fixes außer #48/#50):**

1. **Drag-Mechanik gehärtet (#42):** Greifpunkt-Anker (Achsanteil des
   pointerdown-Strahls auf der Hilfsebene) — ohne ihn sprang die Ebene beim
   ersten pointermove um den Versatz Greifpunkt→Zentrum (der #37-delta-0-Guard
   griff nur beim perfekt bewegungslosen Klick). Totzone `CUT_DRAG_MIN_MM = 1`.
   Ausgangsposition aus `druckplanPanel.getCuts()` (nicht dem im
   Debounce-Fenster veralteten `currentCuts`); nach Drag-Ende Ebenen sofort auf
   den Panel-Stand neu bauen (keine Doppelzählung bei Folge-Drags). Nur
   Primärtaste zieht (`e.button === 0`); ausgeblendete Modellübersicht wird
   weder gepickt noch wirkt sie als Occluder (Raycaster prüft `visible` nicht).
2. **Kamera-Schutz der Roboter-Vorschau (#43):** `fitWorld()` — läuft die
   Vorschau, wird ein showRun-Kamerafit nur als Restore-Ziel in `worldCamera`
   abgelegt und die Vorschau-Kamera unangetastet gelassen („Neu bewerten" im
   Reiter Roboter riss die Kamera sonst auf das unsichtbare Modell).
3. **Wandübernahme synchronisiert UI (#44):** `set_print_job` baut den Job
   serverseitig neu → Viewer setzt jetzt currentRobot/currentTool/Vorschau
   zurück, räumt die alten Schnittebenen ab und holt die Badges aus den
   frischen Revisionsständen („noch nicht erzeugt" statt „aktuell").
4. **Nebenläufigkeit (#45):** Schnittplan-Editing auch während `_busy`
   (Zerlegungsvorschlag) gesperrt inkl. der Zahlenfelder/Lösch-Buttons;
   Prüf-Nebenwirkungen (Simulation/Export/Revisionen) laufen nur noch über
   `onCheckApplied` — verworfene stale Antworten erreichen main.ts nie; der
   Stale-Zweig setzt kein `_recheckWanted` mehr (die auslösende Änderung hat
   ihren eigenen Timer; nach Projektwechsel wäre die Nachholung falsch);
   Reentrancy-Guards für showRun, onOpenProject, startSequence. Offen: Write-
   Lock im Core (#45 bleibt dafür offen).
5. **CSS-Kaskade systematisch (#46):** globale Regel `[hidden] { display:
   none !important }` am Ende von style.css ersetzt alle punktuellen
   [hidden]-Regeln — dritte Ausprägung derselben Falle (`#slice-wall-btn/
   #adopt-job-btn { display:block }` hatte den Ein-Primäraktion-Fix de facto
   ausgehebelt; `#controls label` die Schalter-Labels).
6. **viewer_launch (#47):** `_startup_decision` — getötet wird nur die
   nachweislich veraltete fgc-API („stale"); „down"+belegt = fremder Dienst →
   Meldung statt taskkill. `http.client.HTTPException` wird gefangen.
7. **Kleinbefunde (#49):** formatTime/formatDuration runden vor der
   Verzweigung (kein „60.0 s"/„1:60 min"; formatDuration kann jetzt Stunden);
   `_trajDragging` über pointerdown/-up (klebte nach Klick ohne Wertänderung);
   `nextPlacementCounter` (keine doppelten stellplatz-IDs nach Löschen);
   Löschen des letzten Schnitts erreicht den Core (Prüfen bei cuts=0 erlaubt,
   wenn Abschnitte existieren); Override-Dropdowns folgen Add/Remove der
   Aufstellmöglichkeiten; showRun wendet Travel/Wand/Modell-Schalter an;
   Vorschau-Mesh-Race per Lade-Sequenznummer; Replay-Arm-Flansch wird beim
   Tool-Speichern aktualisiert; Roboter-Vorschau wechselt live mit dem
   Dropdown (README-Zusage jetzt wahr); CORS erlaubt jede localhost-Origin
   (Vite-Ausweichports).

**Bewusst offen:** #48 (Replay ersetzt Modellübersicht ohne Rückweg +
Player-Bedienung im Reiter Simulation — architektonisch, ein Wurf) und #50
(clearWorld-dispose-Leak) als ready-for-agent-Issues.

**Geaendert:** viewer/src/main.ts, ui/druckplan.ts, ui/panel.ts, ui/tool.ts,
ui/simulation-state.ts, trajectory/interpolate.ts, style.css,
core/src/fgc/pipeline/viewer_launch.py, api.py; Tests: interpolate.test.ts,
simulation-state.format.test.ts (neu), placement-counter.test.ts (neu),
test_viewer_launch_probe.py erweitert.
**Tests:** 338 Core- + 135 Viewer-Tests grün (neue zuerst rot), tsc/ruff clean,
vite build grün, UI-Smoke bestanden.

## 2026-07-05 — Core-Write-Lock: Nebenläufigkeit der einen Projekt-Schreibstelle (#45, ADR-018)

**Frage:** Issue #45 (Tiefenprüfung 2) hatte 6 Punkte; die Viewer-Guards
(Punkte 1, 3–6) sind in `7d6637b` behoben. **Offen war Punkt 2:** die Core-API
führt die synchronen Aktions-Endpunkte im FastAPI-Threadpool aus → zwei parallele
mutierende Requests auf dasselbe Projekt machen je `load_project → mutieren →
write_project` und überschreiben sich (**Lost Update**); zudem war `write_project`
nicht atomar. Wie serialisieren wir die Read-Modify-Write-Sektion?

**Alternativen:**
- *In-Process-`threading.RLock` je aufgelöstem Projektpfad* (Registry im
  `store`), Kontextmanager `project_lock(project_dir)` um jede `load→write`-Sektion.
- *Dateibasierter Cross-Process-Lock* (Lockfile/`filelock`): deckt auch mehrere
  Prozesse ab, aber mehr Mechanik.
- *Endpunkte `async` + `asyncio.Lock`*: würde die synchronen Aktionen umschreiben.
- *Optimistische Nebenläufigkeit* (Versionsfeld + Retry): mehr Zustand als nötig.
- *Atomares Schreiben:* Temp-Datei + `os.replace` vs. Belassen des direkten
  `write_text`.

**Entscheidung:** In-Process-**`RLock`** je `.resolve()`-tem Pfad + Kontextmanager
`project_lock`; jede der 9 mutierenden Aktionen in `actions.py` umschließt ihre
`load→write`-Sektion damit. `write_project` schreibt **atomar** (Temp im selben
Verzeichnis + `os.replace`), Schema-Validierung davor bleibt (ADR-016).
`create_project_from_ifc` bleibt ungelockt (neuer eindeutiger Ordner, keine RMW).

**Begründung:** Der Launcher hält genau **einen** Core-Prozess auf Port 8765
(`viewer_launch`), Single-Process ist die Norm — ein In-Process-Lock deckt die
reale Nebenläufigkeit (Threadpool) vollständig ab; ein Cross-Process-Filelock
wäre ungenutzte Mechanik (dokumentiert als Revisionstrigger, falls je
Mehrprozessbetrieb kommt). **`RLock` statt `Lock`**, weil `suggest_placement` den
Lock hält und an `evaluate_placements` delegiert, das denselben Projekt-Lock
erneut nimmt — mit `Lock` ein Selbst-Deadlock; Reentranz je Thread löst das ohne
die verschachtelte Aktion aufzubrechen. `os.replace` ist auf Windows/POSIX ein
atomarer Rename → `load_project` sieht nie ein zerrissenes File. Architekturrang
(Nebenläufigkeits-Invariante der einen Schreibstelle) → ADR-018.

**Geändert:** `core/src/fgc/project/store.py` (`project_lock` + atomares
`write_project`), `core/src/fgc/project/__init__.py` (Export), 9 Aktionen in
`core/src/fgc/pipeline/actions.py` (mit `project_lock` umschlossen);
`core/tests/test_project_concurrency.py` (neu: Lost-Update-Reproduktion ohne
Lock, N×M-Serialisierung mit Lock, End-to-End `set_print_job`, Atomarität).
**Tests:** 342 Core-Tests grün (+4), ruff clean. Verweis: ADR-018, Issue #45.

## 2026-07-05 — M1013 vendoren + Konvertierskript (trimesh→GLB je Glied, Issue #40)

**Frage:** Umsetzung der Grill-Session-Entscheidungen (Eintrag oben
„M1013-Meshes: Bezugsquelle, Format, Kinematik") — konkret: welche URDF-Variante,
wie den Offset numerisch, wie deterministisch exportieren, wohin die
Skalierung/den Offset backen?

**Entscheidungen (je Ast):**

- **URDF-Variante:** `m1013.white.urdf` (statt `.urdf`/`.blue`) vendoren — sie
  referenziert visual **und** collision in einem File und ist farbneutral. Eine
  URDF genügt als Quelle für beide Mesh-Sätze.
- **Gepinnter Commit:** `ec9242546ec6202835900dbcd8498e2daabfa6a6`
  (`doosan-robotics/doosan-robot2`, BSD-3-Clause). In `UPSTREAM.md` samt
  Reproduktionsbefehl (sparse-checkout) festgehalten.
- **Einheiten/Skalierung:** Die DAE tragen ihre Zahlen in **Millimeter** (bestätigt:
  Basis-Extents ~214×440 mm), das URDF skaliert per `<mesh scale="0.001">` nach
  Meter. Statt auf trimesh' `<unit>`-Interpretation zu vertrauen (das DAE
  deklariert fälschlich `meter="1"`), leite ich den effektiven mm-Faktor aus dem
  **URDF-Scale-Attribut** ab: `scale · 1000` (= 1 bei 0.001). `up_axis` ist Z_UP →
  keine Achsdrehung nötig.
- **Offset numerisch:** Alles in **Millimeter** gerechnet. `urdfFrame_i(0)` =
  Vorwärtskette der URDF-Gelenkursprünge (xyz·1000, rpy als fixed-axis Rz·Ry·Rx);
  `dhFrame_i(0)` = `OpwKinematics.link_frames([0]*6)` (Core = einzige
  Kinematik-Wahrheit). `offset_i = dhFrame_i(0)⁻¹ · urdfFrame_i(0)`. Base:
  offset = I (beide Frames = Identität). Verifikation: mit den DH-Frames
  zusammengesetzt ergibt sich ein senkrecht ~1452 mm hoher Arm (plausibel für die
  M1013-Nullstellung, Reichweite 1300 mm).
- **Backen in Vertices statt Root-Node-Transform:** Der Grill-Eintrag nannte
  „Root-Node-Transform"; ich backe Skalierung + Offset direkt in die
  **Vertex-Positionen** (ein Mesh je GLB, Identitäts-Node). Ergebnis für den
  Viewer identisch (`mesh.matrix = frames[i]`), aber unabhängig davon, wie der
  glTF-Loader Node-Hierarchie/Skalierung interpretiert — robuster, eine
  Fehlerquelle weniger.
- **Determinismus:** feste Glied-/Datei-Reihenfolge, Vertices auf 6 Stellen
  gerundet, `scene.metadata` geleert, keine Zeitstempel — zweifacher Lauf liefert
  bytegleiche GLBs (verifiziert). Material/Farbe verworfen (Viewer schattiert
  selbst, hält GLB klein); kein Draco.
- **Test-Strategie:** Der Smoke-Check validiert die **eingecheckten** Artefakte
  (nicht neu erzeugen — 15 MB DAE-Parse): Manifest-Vollständigkeit, Draco-Freiheit,
  mm-Skala je Glied (10 < max-Extent < 1600, fängt verlorene Skalierung), und die
  zusammengesetzte Reichweite (1000–1800 mm). Plus: Vendor-Originale vorhanden
  (URDF, 10+10 DAE, LICENSE, UPSTREAM.md).

**Nicht-Ziel (Folge-Issue #41):** ArmView-Rendering der GLBs + Schema-Toggle.

**Geändert:** `third_party/doosan_m1013/` (URDF + 20 DAE + LICENSE + UPSTREAM.md,
neu), `core/scripts/convert_robot_meshes.py` (neu), `viewer/public/robots/m1013/`
(7 GLB + manifest.json, erzeugt), `core/tests/test_robot_meshes.py` (neu, 4
Tests), `core/pyproject.toml` (`pycollada` in `[geo]`), `README.md` (Funktionen-
Abschnitt). **Tests:** 346 Core-Tests grün (+4), ruff clean. Verweis: Issue #40.

## 2026-07-05 — ArmView: echte M1013-Meshes rendern + Schema-Toggle (Issue #41)

**Frage:** Umsetzung der Grill-Entscheidungen (Eintrag „M1013-Meshes") im Viewer:
Wie hängt der Präsentations-Arm die #40-GLBs an die eigene DH-FK, wie wird der
Mesh↔Schema-Umschalter global über beide Arm-Stellen (Vorschau + Replay)
verdrahtet, und wie bleibt „nie ein leerer Viewport" (Lehre 2026-07-05)
garantiert?

**Entscheidungen (je Ast):**

- **GLB je Gliedframe, keine zweite FK:** Jedes Glied-GLB hängt in einem eigenen
  Halter (`THREE.Group`, `matrixAutoUpdate=false`) direkt unter `ArmView.group`;
  `setPose` setzt `holder.matrix = frames[i]` (zeilenmajor via `Matrix4.set`) —
  exakt wie die Zylinder platziert werden. Offsets/Skalierung sind laut #40 in die
  Vertices eingebacken, der Viewer rechnet nichts dazu. Basis = frames[0], Flansch
  = frames[6]. Das Glied-6-Mesh ist ein **Geschwister** der Flansch-Gruppe (beide
  frames[6]), nicht deren Kind — sonst würde das #28-Flansch-Koordinatensystem
  das Mesh doppelt transformieren.
- **Globaler Modus als Modul-Zustand:** Ein Modul-Singleton in `render/arm.ts`
  (Instanz-Registry + geteilte GLBs + `RenderMode`) steuert **alle** ArmView-
  Instanzen gleichzeitig; der Umschalter im Reiter Roboter ruft `setArmRenderMode`
  auf, alle vier Konstruktionsstellen (Vorschau, Replay, Sequenz, Konfigurator)
  ziehen synchron nach. Kein Halb-Mesh/Halb-Schema. Alternative „Toggle je
  Instanz durchreichen" verworfen (vier Verdrahtungswege, Drift-Risiko).
- **Reine Entscheidungslogik separat:** Manifest-Validierung + Modus-/Fallback-
  Zustandsmaschine liegen three.js-frei in `render/armmesh-state.ts` (Muster der
  `ui/*-state.ts`), unit-getestet (`armmesh-state.test.ts`, 12 Fälle). `arm.ts`
  hält nur das dünne three.js-Objekt-Handling darum.
- **Fallback = Schema + Sperre:** Manifest-/GLB-Ladefehler → `withLoadFailure`
  erzwingt Schema, sperrt den Umschalter, Konsolen-Warnung. Die Zylinder bleiben
  vollständig im Code (Schema-Modus **und** Fallback). Bis die GLBs geladen sind,
  zeigt der Arm ebenfalls Schema (`effectiveMode` = schema solange
  `!meshAvailable`) — nie ein leerer Arm.
- **Meshes einmal laden, je Instanz klonen:** `initArmMeshes` lädt die 7 GLBs
  einmalig (memoisiert) über `manifest.json` (einzige Index→Datei-Quelle) und
  klont sie in jede Instanz (unabhängige Transforms). Cloned Meshes bekommen ein
  neutrales Roboter-Grau (die GLBs tragen laut #40 keine Farbe).
- **Attribution aus dem Manifest:** `attributionText` liest `upstream`
  (Lizenz/Repo/Kurz-Commit) und zeigt sie als Info-Text unter dem Umschalter
  (BSD-3, #40-Pflicht).
- **Smoke prüft Sichtbarkeit, nicht nur Canvas:** `window.__armDebug` liefert
  effektiver Modus + Mesh-Ladezustand + Zahl der Glied-Meshes; `ui_smoke.mjs`
  pollt bis geladen und assertiert Mesh-Modus mit 7 Gliedern, schaltet auf Schema
  und zurück, speichert Mesh-/Schema-Screenshots (visueller Abgleich, AC #41).
- **Leak-Vermeidung:** `ArmView.dispose()` meldet die Instanz vom globalen
  Zustand ab; der neu erzeugte Replay-/Sequenz-Arm wird in `resetRunState`
  disposed (die Langläufer Vorschau + Konfigurator bleiben registriert).

**Geändert:** `viewer/src/render/armmesh-state.ts` (+`.test.ts`, neu),
`viewer/src/render/arm.ts` (Mesh-Halter + globaler Controller + Modus/Fallback),
`viewer/index.html` (Umschalter + Attribution im Reiter Roboter),
`viewer/src/ui/robot.ts` (`onArmSchemaToggled` + `setArmRenderState`/
`setArmAttribution`), `viewer/src/main.ts` (Verdrahtung + `initArmMeshes` +
`__armDebug` + `dispose`), `viewer/scripts/ui_smoke.mjs` (Roboter-Mesh-Prüfung +
Toggle + Screenshots), `README.md` (Funktionen-Abschnitt). **Tests:** 147
Viewer-Tests grün (+12), `tsc --noEmit && vite build` clean; 346 Core-Tests grün,
ruff clean (Core unberührt). Verweis: Issue #41 (blocked-by #40).

## 2026-07-05 — Druck-Orientierung: eine geteilte Konstante für Slicer + Platzierung (Issue #51)

**Frage:** Ein Abschnitt galt im Druckplan als **100 % erreichbar**
(`fgc.decompose`/`fgc.placement`), in der Abschnitts-Simulation aber als **0 %**
(1661/1661 „keine IK-Lösung"). Woher der Selbstwiderspruch?

**Befund:** Zwei Module rechneten mit **verschiedener TCP-/Düsen-Orientierung**.
`fgc.placement.evaluate` legte die Düse senkrecht nach unten (`_R_NOZZLE_DOWN =
diag(1,-1,-1)`), der **Slicer** emittierte seine Toolpath-Ziele dagegen mit
**Identitäts-Quaternion** (`slicer/build.py`, alter Kommentar: „Düse senkrecht
nach unten, Identitätsquaternion — Konvention wird mit M1/ADR-006 verfeinert" —
der Kommentar meinte nozzle-down, der Code schrieb Identität). `build_trajectory`
nahm die Ziel-Orientierung wörtlich → über die Wand unerreichbare Flansch-Lage.

**Entscheidung:** Eine kanonische Druck-Orientierung als **einzige Quelle**:
`fgc.domain.orientation.NOZZLE_DOWN_QUAT = (0,1,0,0)` (ADR-006). Der Slicer bäckt
sie in **jedes** Ziel-Frame ein; `placement.evaluate` leitet sein `_R_NOZZLE_DOWN`
per `_quat_to_rot` aus **derselben** Konstante ab. Damit können Feasibility und
Simulation nicht mehr auseinanderdriften. Alternative „Orientierung erst in der
Simulation aufprägen, Toolpath identitätsfrei lassen" verworfen — der Toolpath
ist das Artefakt, das auch der Emitter/Viewer lesen; die Orientierung gehört
sichtbar hinein.

**Wichtig (Abgrenzung):** Dieser Fix behebt eine *echte* latente Inkonsistenz,
war aber **nicht** die Ursache des konkret gemeldeten „Simulation fällt
auseinander". Das lag an einem kaputten TCP-Frame (~2 m Versatz) des
Endeffektors `extruder30` aus dem #28-Konfigurator (`configurator.ts` +
`matrixAutoUpdate=false`-Flansch → fehlerhafte Gizmo→Flansch-lokal-Umrechnung).
Getrennt verfolgt.

**Geändert:** `core/src/fgc/domain/orientation.py` (neu), `core/src/fgc/slicer/
build.py` (Ziele tragen `NOZZLE_DOWN_QUAT`), `core/src/fgc/placement/evaluate.py`
(`_R_NOZZLE_DOWN` aus der Konstante), `core/tests/test_slicer.py` (Konsistenztest
Slicer↔Platzierung). **Tests:** Core grün, ruff clean. Verweis: Issue #51.

## 2026-07-05 — Endeffektor-Konfigurator: Face-Align statt Frei-Drag-Gizmo (Issue #52)

**Frage:** Der #28-Konfigurator speicherte kaputte TCP-/Mesh-Transforms (z. B.
`extruder30`: TCP ~2 m Versatz bei ~200 mm Mesh → Simulation 100 % unerreichbar,
Arm „fällt auseinander"). Ursache: `configurator.ts` las `tcpMarker.position`/
`meshObject.position` — lokale Lagen von Objekten am `ArmView.flange`, der mit
`matrixAutoUpdate=false` + manuell gesetzter Matrix läuft; `TransformControls`
rechnete den World-Drag über die unzuverlässige Flansch-Weltmatrix zurück auf
lokal → Müll. Zusätzlicher Nutzerwunsch: bessere Positionierung.

**Entscheidung — Positionier-Modell Face-Align (ersetzt den Frei-Drag):**

- **Fläche wählen (Raycast-Klick):** die gewählte Fläche legt sich bündig auf die
  Flanschebene, ihre Außennormale zeigt in den Arm (−Flansch-z), der Körper ragt
  weg (+z); der Klickpunkt landet im Flansch-Ursprung. Montagekonvention nach
  Nutzerentscheid (ADR-006-nah). Danach Drehung um Flansch-z per Zahlenfeld.
- **Auto-TCP:** der TCP sitzt automatisch auf dem entlang +Flansch-z am weitesten
  entfernten Mesh-Punkt (die Spitze); Zahlenfeld justiert den Abstand.
- **Strukturelle Fehlerbehebung:** die Transforms werden **direkt** aus der
  Mesh-Geometrie in Flansch-lokalen Koordinaten gerechnet (`ui/face-align.ts`,
  three.js-frei, vitest) und sind die **Quelle der Wahrheit** fürs Speichern —
  kein Zurücklesen einer Gizmo-World/Local-Zerlegung mehr. Alle Vertex-/Normalen-
  Rechnungen kürzen die Vorfahren (inkl. Flansch) heraus (`inv(meshObject.
  matrixWorld) · child.matrixWorld`), daher unabhängig von der fehlerhaften
  Flansch-Weltmatrix. `TransformControls` entfällt (Bundle −17 kB).
- **Abgrenzung:** behebt die #28-Ursache des gemeldeten Symptoms. Der bereits
  gelieferte #51-Orientierungs-Fix ist eine getrennte Sache; `extruder30.json`
  wurde als Platzhalter repariert (TCP z=202), mit dem neuen Modell sauber
  neu setzbar. Die Face-Align-Mathematik reproduziert exakt diese Platzhalter-
  Werte (Konsistenztest).

**Geändert:** `viewer/src/ui/face-align.ts` (+`.test.ts`, neu, 9 Fälle),
`viewer/src/ui/configurator.ts` (Raycast-Face-Pick + Rotation + Auto-TCP; Speichern
aus berechneten Frames; `TransformControls` raus), `viewer/index.html` (Face-Pick-
Anleitung + Rotations-/TCP-Abstands-Feld statt Gizmo-Radios), `viewer/src/style.css`
(tote `.cfg-gizmo`-Regeln raus), `README.md` (Funktionen). **Tests:** 156 Viewer-
Tests grün (+9), `tsc --noEmit && vite build` clean, Headless-Smoke (Bibliothek-
Init) grün. Verweis: Issue #52 (⇐ #28, Diagnose #51).

## 2026-07-05 — Konfigurator: Mesh beim Upload am Flansch zentrieren (Issue #52, Nachtrag)

**Frage:** Nutzer-Screenshot: der hochgeladene Endeffektor sitzt sichtbar
**neben** dem Flansch, nicht darauf. CDP-Messung (temporärer `__cfgDebug`-Hook):
Flansch-Weltlage = link-mesh-6-Weltlage (Arm/Flansch stimmen) — die Ursache ist,
dass der **Geometrie-Ursprung** der STL nicht auf einer Montagefläche liegt
(extruder30: Zentroid y≈71, Ausdehnung y∈[-52,150]). Bei Identitäts-Mount schwebt
der Körper daher bis ~150 mm neben dem Flansch, bis eine Fläche geklickt wird.

**Verworfen:** Auto-Montage auf der *flächengrößten* Fläche — für extruder30 ist
das die +y-Fläche (Area 11807), Mount würde den Endeffektor falsch herum
aufsetzen. Nicht robust.

**Entscheidung:** Beim Upload das Mesh an seiner **Bounding-Box-Mitte** am Flansch
**zentrieren** (`centerAtFlange`, reine Funktion + vitest) — orientierungsneutral,
nie daneben. Die bündige Montage kommt weiterhin per **Flächen-Klick**
(`mountFaceToFlange`), passend zum Nutzer-Modell. Kein Raten der Montagefläche.

**Geändert:** `viewer/src/ui/face-align.ts` (`centerAtFlange` + Test),
`viewer/src/ui/configurator.ts` (Upload zentriert). **Tests:** 158 Viewer-Tests
grün (+2), Build + Smoke grün. Verweis: Issue #52.

## 2026-07-05 — M1013-GLB-Baking: korrespondierendes Posenpaar statt Null↔Null (Issue #53)

**Frage:** Nutzer-Screenshot (Bibliothek): nach dem Face-Align-Klick sitzt der
Endeffektor samt Flansch-Achsenkreuz und TCP-Marker am Boden **neben** dem
Roboter — obwohl `mountFrame`/TCP plausibel sind (TCP-Readout ~148 mm) und alle
drei Objekte korrekt am `ArmView.flange` hängen.

**Diagnose:** Der Flansch-Frame selbst stand falsch. `link_frames([0]*6)` der
DH-Kette ist **nicht** der aufrechte Roboter, sondern eine seitlich abgeknickte
Pose (Flansch bei (620, −34.5, −527.5) mm). Das Konvertierskript #40 backte den
je-Glied-Offset aber als `dhFrame_i(0)⁻¹ · urdfFrame_i(0)` — es setzte URDF-Null
(aufrecht, Doosan-Konvention) und DH-Null gleich, zwei **verschiedene physische
Posen**. Ergebnis: der Mesh-Arm *sah* bei q=0 aufrecht aus, während der echte
DH-Flansch (Anker für Endeffektor/TCP/Achsen) an der geknickten Pose lag; bei
q≠0 waren zusätzlich alle Glieder gegeneinander verdreht.

**Numerisch verifiziert** (Skript-Experiment, Konstanzprüfung des Offsets über
zufällige Posen): `q_urdf_i = q_dh_i − _START_i` mit `_START = (0, π/2, π/2, 0,
0, π)` (alle Vorzeichen +1) und Basiswechsel `B = Rz(π)`; Alternative Vorzeichen
divergieren um bis zu 2258 mm, die richtige Wahl bleibt ≤ 0.4 mm konstant (Rest
= auf 3 Dezimalen gerundete rpy-Werte im Vendor-URDF — akzeptiert, rein visuell).

**Entscheidung:**
1. Offset im Konvertierskript am korrespondierenden Posenpaar berechnen
   (`dhFrame_i(_START)⁻¹ · Rz(π) · urdfFrame_i(0)`), GLBs + Manifest neu erzeugt.
2. Viewer-Home-Pose (Konfigurator + Roboter-Vorschau) auf die aufrechte
   Doosan-Nullstellung `M1013_HOME_RAD = [0, π/2, π/2, 0, 0, π]`
   (`kinematics/robot.ts`) statt `[0,…,0]` — der Flansch zeigt oben, wie es das
   Montage-Mentalmodell des Konfigurators erwartet. `armreplay` bleibt
   roboter-agnostisch (Fallback unverändert).
3. Regressionstests: `test_flange_link_sits_on_dh_flange_frame` (link6-GLB lokal
   < 150 mm vom Flansch-Ursprung; alt: ~2 m) und aufrechte Montage bei `_START`
   (Basis am Boden, Höhe ~1450 mm) statt des alten `[0]*6`-Reichweitentests.

**Nicht entschieden/offen:** Die Basis-Ausrichtung (B = Rz(π) vs. Gelenk-1-Offset
π) ist kinematisch nicht unterscheidbar und betrifft nur die Blickrichtung des
Basis-Sockels — gewählt: Rz(π). Ob die DH-Gelenkwinkel des Core der realen
Doosan-Controller-Konvention entsprechen (relevant erst für movej/Joint-Export
auf echter Hardware), ist eine getrennte Frage; IK↔FK sind in sich konsistent
(Loop-Closure numerisch 0).

**Geändert:** `core/scripts/convert_robot_meshes.py` (Offset + Doku),
`viewer/public/robots/m1013/*.glb` + `manifest.json` (neu gebacken),
`viewer/src/kinematics/robot.ts` (`M1013_HOME_RAD`), `viewer/src/ui/
configurator.ts` + `viewer/src/main.ts` (Home-Pose), `core/tests/
test_robot_meshes.py` (Regression #53). **Tests:** 348 Core- + 158 Viewer-Tests
grün, ruff/tsc clean, Headless-Smoke bestanden; Screenshot Roboter-Reiter:
Endeffektor sitzt auf dem Flansch des aufrechten Arms. Verweis: Issue #53 (⇐ #40/#41; erklärt auch den „Arm fällt auseinander"-Anteil aus #51/#52).

## 2026-07-05 — Konfigurator: TCP per Öffnungsflächen-Klick + freie x/y/z-Eingabe (Issue #54)

**Frage:** Nach #53 passt die Montage, aber der Auto-TCP (weitester Punkt entlang
+Flansch-z) trifft nicht immer die Extruderöffnung — der TCP ließ sich nur über
ein einzelnes z-Abstands-Feld verschieben. Nutzerwunsch: Klick auf die Fläche
der Extruderöffnung → TCP = Flächenmittelpunkt; alternativ frei als x/y/z
relativ zum Flansch-Ursprung.

**Entscheidung — drei TCP-Quellen mit klarer Rangfolge:**

- **auto** (Default): Spitze entlang +Flansch-z, wie bisher.
- **face:** eigener Klick-Modus („TCP-Fläche wählen"-Button, scharfgeschaltet
  bis zum Flächen-Klick). Der TCP springt auf den Mittelpunkt der
  **zusammenhängenden ebenen Fläche** um das getroffene Dreieck —
  Region-Growing über die Dreiecks-Soup (`planarRegionCentroid`,
  `ui/face-align.ts`, three.js-frei): Nachbarn teilen ≥ 1 quantisierten
  Eckpunkt (1 µm-Raster; STL dupliziert Eckpunkte), Normale ≤ 5° zur
  Start-Normale, alle Eckpunkte ≤ 0.5 mm neben der Start-Ebene. Getrennte
  koplanare Flächen wachsen nicht mit. Flächengewichteter Mittelpunkt.
  Der Flächen-Mittelpunkt ist **mesh-lokal** gemerkt (wie die Montagefläche)
  und rechnet bei Montage-Änderungen (neue Fläche, Drehung) mit.
- **manual:** drei x/y/z-Felder (mm, Flansch-relativ) ersetzen das alte
  z-Abstands-Feld. Sie spiegeln immer den aktiven TCP (bei auto/face
  vorbefüllt); Tippen schaltet auf manual, alle drei Felder leeren kehrt zu
  auto zurück. Verworfen: Felder nur als Override ohne Spiegelung — der Nutzer
  sähe die Auto-Werte nicht und könnte nicht von ihnen aus feinjustieren.

**Verifiziert an der echten `extruder30.stl`** (101 140 Dreiecke): Start am
Spitzen-Dreieck (y=150) → Region 405 Dreiecke, Mittelpunkt (35.75, 150, −0.03),
Normale +y, 68 ms — die Öffnungsfläche wird als Ganzes erkannt, Laufzeit
klick-tauglich.

**Geändert:** `viewer/src/ui/face-align.ts` (`planarRegionCentroid`,
`tcpAtPosition`), `viewer/src/ui/face-align.test.ts` (+6 Fälle: Region über
Dreiecksgrenzen, getrennte koplanare Fläche, Kanten-Stopp, Bereichsfehler,
freie Position), `viewer/src/ui/configurator.ts` (TCP-Quellen-Zustand,
Klick-Modus, x/y/z-Verdrahtung), `viewer/index.html` (Schritt 3 neu),
`viewer/src/style.css` (`#cfg-tcp-pick` + `.armed`), `README.md`. **Tests:**
164 Viewer-Tests grün (+6), tsc clean, Headless-Smoke bestanden; Raycast-Klick
selbst bewusst ohne Test (PRD Testing Decisions), Region-Mathe am echten Mesh
geprüft. Verweis: Issue #54 (⇐ #52/#53).

## 2026-07-05 — Konfigurator-Feinschliff: Flächen-Mittelpunkt-Montage, Hover-Hervorhebung, feiner TCP-Marker (Issue #55)

**Frage:** Nutzer-Feedback nach #54: (1) der Extruder sitzt „nur fast" zentriert
auf dem Flansch, (2) der Flächen-Klick funktioniert nicht gut, (3) die TCP-Kugel
ist zu dick zum präzisen Einstellen.

**Diagnose:** (1) Die Montage legte den **Klickpunkt** in den Flansch-Ursprung —
wer nicht exakt die Flächenmitte trifft, montiert daneben. (2) Es gab kein
Feedback, welche Fläche ein Klick treffen würde; zudem fiel der TCP-Modus nach
einem Klick sofort auf „Montage" zurück — ein Folgeklick verschob unbemerkt den
ganzen Endeffektor. (3) Kugelradius 14 mm verdeckte die Spitze.

**Entscheidung:**
- **Montage am Flächen-Mittelpunkt:** der Montage-Klick nutzt jetzt dieselbe
  `planarRegionCentroid`-Mathematik wie der TCP-Klick — der Mittelpunkt der
  zusammenhängenden ebenen Fläche landet im Flansch-Ursprung, nicht der
  Klickpunkt. An `extruder30.stl` verifiziert: Montagefläche y=−52 → Region
  118 Dreiecke, Mittelpunkt exakt (0, −52, 0).
- **Hover-Hervorhebung (beide Modi):** die ebene Fläche unter dem Cursor wird
  als halbtransparentes Overlay hervorgehoben (orange = Montage, rot =
  TCP-Modus), rAF-gedrosselt, während Orbit-Drags aus. Dafür `face-align.ts`
  zu `PlanarRegionIndex` refaktoriert: Nachbarschaftskarte einmal je Mesh,
  gefundene Regionen für alle Mitglieds-Dreiecke gecacht (erste Abfrage nach
  Indexbau 1 ms, gecacht 0 ms bei 101k Dreiecken). Das Overlay hängt als Kind
  am Endeffektor-Mesh (folgt der Montage-Lage), ist vom Raycast und von
  `_meshLocalVertices` ausgenommen.
- **TCP-Modus bleibt aktiv** bis der Button ihn beendet — nachjustieren per
  weiterem Klick, kein versehentliches Ummontieren.
- **TCP-Kugel 14 → 4 mm.**

**Geändert:** `viewer/src/ui/face-align.ts` (`PlanarRegionIndex` + Cache,
`planarRegionCentroid` als Wrapper), `viewer/src/ui/configurator.ts`
(Region-Index je Teil-Mesh, Hover-Overlay, Montage-Zentroid, persistenter
TCP-Modus, Kugelgröße), `viewer/index.html` (Hinweistexte), `face-align.test.ts`
(+2 Cache-/Regionslisten-Fälle), `README.md`. **Tests:** 166 Viewer-Tests grün
(+2), tsc clean, Headless-Smoke bestanden; Region-Mathe an der echten
`extruder30.stl` geprüft. Verweis: Issue #55 (⇐ #54).

## 2026-07-05 — Arm-Replay: feste Roboterbasis statt mitschleifender Basis (Issue #66)

**Frage:** Nutzer-Report — in der Simulation „fährt die Basis hin und her", der
Arm bleibt „starr in sich"; gedruckt werde mit der Flanschmitte statt dem TCP;
der Endeffektor solle standardmäßig „von oben" extrudieren.

**Befund:** Das Arm-Replay verankerte den ganzen Arm pro Frame mit
`anchor = target · flange_FK⁻¹` (`viewer/src/kinematics/fk.ts:anchorFlangeToTarget`,
gesetzt als `group.matrix`). Dieser Anker (a) legt bewusst den **Flansch** — nicht
den TCP — aufs Ziel und (b) ist **nicht konstant**: bei eingefrorenen Gelenken
(Core füllt bei unerreichbaren Targets `(0,)*6`, `simulation/build.py`) schleift
er die Basis die TCP-Bahn entlang. Der frühere Kommentar „für erreichbare Bahnen
konstant" galt nur bei TCP = Flansch (Identitäts-Werkzeug) — mit echtem
TCP-Versatz wackelt die Basis um `flange·tcp·flange⁻¹`. Die Düse-nach-unten-
Konvention war im Core bereits korrekt (`domain/orientation.py:NOZZLE_DOWN_QUAT`,
Issue #51); sie wurde nur nicht sichtbar, weil der Anker die Basis verdrehte, um
den Home-Flansch aufs Ziel zu zwingen.

**Alternativen:**
1. *Anker aus einem Frame einfrieren* (viewer-only): Basis fix, aber weiterhin
   Flansch statt TCP auf der Bahn; der Werkzeugversatz bliebe unmodelliert.
2. *Festes Basis-Frame als Core-Artefakt* (gewählt): der Core liefert die
   Roboterbasis im Wandsystem, der Viewer setzt sie nur — ADR-007-konform.

**Entscheidung / Ableitung:** `build_trajectory` schreibt
`meta.base_frame = invert(wall_to_base)` (Roboterbasis im Wandsystem, `base_in_wall`).
Der Viewer verankert damit den Arm **fix**: `anchor = frameToMat(base_frame)`,
konstant über die Zeit. Streng geprüfte Kette (Core `_flange_frames`:
`flange_base = compose(wall_to_base, target) ∘ tcp⁻¹`):

```
anchor · forwardChain(joints)[6]  = M_wand←base · M_base←flansch = Flansch in Wandkoords
anchor · flange · tcp             = target (Düse trifft das Ziel exakt)
```

Mit den echten IK-Gelenken articuliert der Arm, der **TCP** (nicht der Flansch)
fährt die Bahn ab, die Düse von oben — alle drei Symptome behoben, sobald ein Lauf
neu simuliert wird. `base_frame` deckt beide Produktionspfade (measured/planned) ab
(eine Konvergenzstelle in `build_trajectory`). **Randfall unerreichbar** (konstante
Gelenke): der Arm steht jetzt ehrlich fix im Home, während der TCP-Marker wegdriftet
— statt die Nicht-Erreichbarkeit durch eine mitschleifende Basis zu kaschieren;
`meta.warnings` (kind `reach`) flankiert es. Der `tcp_frame` wandert **nicht** in
GET /tools: die Korrektheit folgt aus den IK-Gelenken, der Düsenversatz steckt im am
Flansch angehängten Werkzeug-Mesh (`mesh_transform`).

**Diagnose (Nutzerwunsch „erst diagnostizieren"):** Der zuletzt betrachtete
Abschnitts-Lauf war komplett unerreichbar (alle Gelenke 0, 1661/1661 `reach`) — ein
**veralteter** Lauf. Nach frischem Simulieren sind alle 6 Abschnitte der Testwand
(Kellerwand 26 cm, Tool 30gut, standoff 700 mm) erreichbar (uniq_joints 1493–1968,
je 4–9 `reach`-Warnungen ≈ 0 %), `base_frame` in jedem Lauf geschrieben. Der
Default-Standort (700 mm vor der Wand, 500 mm hoch) trägt — kein separater
Erreichbarkeits-Fix nötig. **Altläufe** ohne `base_frame` fallen auf den Legacy-
Anker zurück (rückwärtskompatibel); für das korrigierte Verhalten neu simulieren.

**Geändert:** `core/src/fgc/simulation/build.py` (base_frame in meta),
`schemas/trajectory.schema.json` (`meta.base_frame`, additiv/optional, `$ref` auf
`setup.schema.json#/$defs/frame`), `viewer/src/artifacts/types.ts`,
`viewer/src/trajectory/armreplay.ts` (`computeArmPose(..., baseFrame?)` + Doku),
`viewer/src/kinematics/fk.ts` + `viewer/src/render/arm.ts` (Doku),
`viewer/src/main.ts` (beide Replay-Aufrufe reichen `meta.base_frame` durch),
`docs/adr/ADR-007-*.md` (Klarstellung base_frame). **Tests:** Core 35 (Simulation/
Section/Schema, +3 base_frame-Fälle) grün, Viewer 172 grün (armreplay +4:
konstanter Anker, TCP-trifft-Ziel, Legacy-Fallback), tsc/vite build clean; realer
Pipeline-Lauf bestätigt `base_frame` + Erreichbarkeit aller 6 Abschnitte.
Verweis: Issue #66.

## 2026-07-06 — Konfigurator: flansch-lokaler Feinversatz der Montage (Issue #67)

**Frage:** Nach der Flächen-Mittelpunkt-Montage aus #55 sitzt der Endeffektor
zentriert auf dem flächengewichteten Mittelpunkt der Montagefläche. Ist diese
Fläche größer oder asymmetrisch, liegt ihr Mittelpunkt aber nicht zwangsläufig
auf der Flanschmitte — der Nutzer braucht eine Möglichkeit, die Montage
nachträglich fein unter den Flansch zu schieben, ohne die bündige Ausrichtung
zu verlieren.

**Entscheidung:** Drei Eingabefelder **„Versatz am Flansch (mm)"**
(`cfg-mount-offset-x/y/z`) schieben die Montage-Basis **flansch-lokal** nach:
x/y in der Flanschebene, z axial. Der Konfigurator trennt dazu die
**`mountBaseFrame`** (aus Upload-Zentrierung `centerAtFlange` bzw. Flächen-Klick
`mountFaceToFlange`) vom **`mountOffset`**; das angewandte Frame ist
`mountFrame = offsetFrame(mountBaseFrame, mountOffset)`. So nudged der Versatz
die **aktuelle Basis**, statt sie neu zu berechnen (ein zweiter Nudge hebt den
ersten nicht auf, die Ausrichtung bleibt bündig). Der Versatz wirkt als reine,
three.js-freie Funktion **`offsetFrame(frame, [x,y,z])`** in `face-align.ts`
(addiert die Translation, Rotation bleibt) — per vitest geprüft. Der **TCP
wandert mit** (er rechnet über die Montage-Lage). Beim Laden eines **neuen Mesh**
wird der Versatz **zurückgesetzt** (die Felder geleert), da er der alten Fläche
galt. Führt die Montage-Arbeit aus #55 (⇐ #54) fort.

**Begründung:** Die Trennung Basis/Versatz hält den Nudge idempotent und die
Ausrichtungs-Mathematik unberührt; eine reine `offsetFrame`-Funktion bleibt ohne
3D-Kontext testbar (ADR-007). Der Reset beim Mesh-Wechsel verhindert, dass ein
Versatz stillschweigend auf eine unpassende neue Fläche übertragen wird.

**Geändert:** `viewer/src/ui/face-align.ts` (`offsetFrame`),
`viewer/src/ui/configurator.ts` (Basis/Versatz getrennt, Felder verdrahtet,
Reset), `viewer/src/ui/face-align.test.ts` (+1 Fall), `viewer/index.html`
(die drei Versatz-Felder), `README.md`. Verweis: Issue #67 (⇐ #55 ⇐ #54).

## 2026-07-06 — Öffnungs-Klick setzt auch die Düsenrichtung (tcp_frame-Orientierung, #58)

**Frage:** Der TCP-Klick auf die Extruderöffnung (#54/#55) setzte nur
`tcp_frame.pos_mm`; die `quat` blieb Identität. Damit lag die Extrusionsachse
auf der **Flansch-z-Achse** statt auf der echten Düsenachse — die kanonische
Druck-Orientierung „Düse nach unten" (`NOZZLE_DOWN`, Core) richtete den Flansch
senkrecht aus, die Düse druckte in der Simulation aber horizontal. Woher nimmt
der Konfigurator die Düsenrichtung?

**Alternativen:** (a) Weiterhin hand-gesetzte `quat` je Werkzeug (der
`30gut`-Stopgap) — fehleranfällig, pro Mesh neu zu raten. (b) TCP-z aus der
Flansch-z-Achse plus manuellem Winkel — verlagert die Rateaufgabe nur.
(c) **TCP-z-Achse aus der Flächennormale der angeklickten Öffnung ableiten** —
die Geometrie kennt die Düsenrichtung bereits.

**Entscheidung:** (c). Der Öffnungs-Klick merkt sich zusätzlich die
**Außennormale** der ebenen Region (mesh-lokal, `pickedTcpNormal`); beim
Neurechnen des TCP wird sie mit der Montage-Rotation in Flansch-Koordinaten
gedreht und über die neue **reine, three.js-freie** Funktion
**`nozzleQuatFromNormal(normal)`** (`face-align.ts`, = kürzeste Rotation der
TCP-z-Achse `[0,0,1]` auf die Normale, delegiert an `quatBetween`) in ein
Quaternion überführt. Golden-Werte per vitest: `+x ⇒ 90° um y`,
`+y ⇒ −90° um x`, `+z ⇒ Identität`, `−z ⇒ 180° um y`. Der Klick/Gizmo bleibt
test-frei (visueller Smoke, PRD Testing Decisions). Die **automatische** (Spitze
entlang +z) und **manuelle** (x/y/z-Felder) TCP-Quelle behalten die
Identitäts-Orientierung — dort gibt es keine Öffnungsnormale, und Altwerkzeuge
bleiben unverändert gültig. Der TCP-Readout zeigt jetzt neben der Position die
**Düsenachse** (gedrehte TCP-z), damit die Orientierung sichtbar prüfbar ist.

**Begründung:** Die Normale→Quaternion-Ableitung ist die einzige neue Rechnung
und als reine Funktion mit Golden-Werten testbar (ADR-009-Muster); der Rest ist
Verdrahtung. Core bleibt unberührt: die Transformationskette
`T_base_flansch = (wall_to_base ∘ target) ∘ tcp⁻¹` (`simulation/transform.py`)
konsumiert `tcp_frame.quat` bereits — steht die TCP-z-Achse auf der Düsenachse,
zeigt die physische Düse unter `NOZZLE_DOWN` senkrecht nach unten (Düsenachse in
Wandkoords ≈ (0,0,−1)). Löst den `30gut`-Stopgap sauber ab; rückwärtskompatibel
(ADR-007: der Viewer übergibt das volle Frame, der Core validiert).

**Geändert:** `viewer/src/ui/face-align.ts` (`nozzleQuatFromNormal`),
`viewer/src/ui/face-align.test.ts` (+5 Golden-Fälle),
`viewer/src/ui/configurator.ts` (`pickedTcpNormal`, Face-TCP-quat, Readout),
`README.md`. Verweis: Issue #58 (⇐ #57, ⇐ #54/#55).

---

## 2026-07-06 — Prozessparameter-Rail: `process_params.slice` am Druckjob (Issue #59, ⇐ PRD #57)

**Frage:** Wie kommen die **Slice-Basisparameter** (Schichthöhe, Strangbreite,
Schalen) editierbar in den Prozess, ohne die Provenienz der Läufe zu umgehen und
ohne die veraltet-Konsistenz (ADR-017) zu brechen? Der dünnste End-to-End-Durchstich
als Rail für die späteren Parametergruppen (Orientierung #61, Bewegung).

**Entscheidung:** Ein **optionaler** `process_params`-Block im `print_job`
(`project.schema.json`), additiv, mit je einer Untergruppe — Scheibe 2 füllt
`slice` (`layer_height_mm`/`strand_width_mm`/`n_shells`, je optional). `fgc.project`
bleibt die einzige, beim Schreiben **und** Lesen schema-validierte Schreibstelle
(ADR-016); die neue Aktion `set_process_params` + Route `PUT …/process-params`
setzen den Block. `simulate_section` liest die Werte über den neuen Helper
`domain.process_params.job_slice_overrides(job)` → `SliceParams.from_window(window,
**overrides)`: gesetzte Job-Felder schlagen die Karte, ungesetzte fallen auf
Karte/Code-Default zurück. Fehlt der Block (Altprojekt), ändert sich nichts.

**Revisionen:** Neuer **Eingabezähler `process`** in `INPUT_KEYS` und in `OUTPUT_DEPS`
für **alle drei** Outputs (druckplan/simulation/export) — die Slice-Parameter fließen
in Zerlegung, Simulation und Export. Änderung an `process_params` bumpt `process` →
alle drei veralten (sichtbar, nichts gelöscht). Python↔TS synchron gehalten
(`fgc.project.revisions` ↔ `ui/staleness.ts`), je mit Test.

**Alternativen (verworfen):**
- *Flacher `slice_*`-Block direkt am Job* statt geschachteltem `process_params.slice`:
  verworfen — die späteren Gruppen (Orientierung/Bewegung) bräuchten je eigene
  Top-Level-Felder; das geschachtelte Objekt ist die saubere Rail (ein Ort, eine
  additive Erweiterung je Scheibe).
- *Bestehenden Eingabezähler wiederverwenden* (z. B. `tool`): verworfen — die
  Prozessparameter sind eine eigene Eingabe-Stufe (ADR-017 verlangt, dass neue
  Stufen ihre Abhängigkeit explizit deklarieren); ein eigener `process`-Zähler
  hält die Semantik sauber.
- *Reachability/Zerlegung geometrisch aus den Slice-Parametern rechnen*: verworfen
  für diese Scheibe — `placement.evaluate`/`decompose` bewerten die Wandfläche
  kinematisch und slicen nicht; sie hängen über den `process`-Zähler (Druckplan-
  Stufe) an den Prozessparametern (veralten korrekt), lesen sie aber nicht
  geometrisch. Realer Slice-Konsument ist `simulate_section`.

**Panel:** Minimales Formular im Reiter Druckplan (drei Felder + „Speichern"); die
Formular↔Job-Serialisierung liegt DOM-frei in `ui/process-params-state.ts` (vitest).
Leeres Feld = nicht gesetzt (Karte gilt); leeres Formular entfernt den Block.

**Geändert:** `schemas/project.schema.json` (`process_params.slice` + `process`-
Revision), `core/src/fgc/project/revisions.py`, `core/src/fgc/domain/process_params.py`
(`job_slice_overrides`), `core/src/fgc/pipeline/actions.py` (`set_process_params`,
`simulate_section`), `core/src/fgc/pipeline/api.py` (`PUT …/process-params`),
`viewer/src/ui/staleness.ts`, `viewer/src/api/projects.ts` (`setProcessParams`),
`viewer/src/ui/process-params-state.ts` + `.test.ts`, `viewer/src/ui/process-params.ts`,
`viewer/index.html`, `viewer/src/main.ts`, `viewer/src/style.css`, `README.md`.
Tests: `core/tests/test_project.py`, `core/tests/test_export.py`,
`core/tests/test_section_simulation.py`, `viewer/src/ui/staleness.test.ts`.
Verweis: Issue #59 (⇐ PRD #57); ADR-016, ADR-017.

---

## 2026-07-06 — Scheibe 3: bahn-relativer Anstellwinkel über geteilte `nozzle_quat` (Issue #61)

**Frage:** Wie bekommt der Druck einen **Lead-/Lag-** und **Kipp-Winkel** der Düse,
ohne dass Erreichbarkeitsbewertung (Ampel) und Simulation auseinanderdriften —
die exakte Falle aus Issue #51?

**Entscheidung:** Die bisherige Konstante `NOZZLE_DOWN_QUAT` wird zur **reinen
Funktion** `fgc.domain.orientation.nozzle_quat(tangente, lead, kipp)` — **die eine
geteilte Orientierungsquelle**. Der Slicer (`slicer/build.py`) füllt `frame.quat`
je Ziel darüber mit der **echten Bahntangente** (aufeinanderfolgende Ringpunkte);
`placement.evaluate` ruft **dieselbe** Funktion mit seiner **angenommenen
horizontalen Tangente** (+x entlang der Wandlänge). Keine Rotation wird dupliziert
→ strukturell kein Drift (Regressionsschutz #51). Der Winkel lebt als zweite Gruppe
`process_params.orientation` (in **Grad** persistiert) auf der #59-Rail; Slicer und
Ampel lesen ihn über `job_orientation(job)`.

**Vorzeichenkonvention (bewusst festgelegt):** Aus einem **CCW-orientierten
Druckring** ist die Wand-Außenseite eindeutig die **rechte Seite der Fahrtrichtung**,
`n_out = tangente × ẑ` (Innenraum liegt bei CCW links). Damit:
- **`+lead` kippt die Düse in Fahrtrichtung** (Drehung um `n_out`); `−lead` = Lag.
- **`+kipp` kippt die Düse zur Wand-Außenseite** (Drehung um die Tangente, mit `−kipp`
  im Quaternion, damit +kipp Richtung `n_out` zeigt).
Nullpunkt **`0/0` ⇒ exakt `NOZZLE_DOWN_QUAT`**, und zwar **unabhängig von der
Tangente** (früh per `if lead==0 and kipp==0: return NOZZLE_DOWN_QUAT` — garantiert
Bit-Gleichheit zum heutigen Toolpath). Golden-Werte in `tests/test_orientation.py`
(z. B. Fahrt +x, kipp 30° ⇒ TCP-z = (0, −sin30, −cos30), Quat = (sin15°, cos15°, 0, 0)).

**Reine Funktion, keine numpy-Abhängigkeit** in `domain.orientation`: Quaternion-
Produkt (Hamilton) + Achse-Winkel lokal implementiert (`_quat_mul`/`_axis_angle_quat`),
kanonisch `w ≥ 0` wie `_rot_to_quat`. So bleibt `domain` frei von `kinematics`-Import
(kein Zyklusrisiko).

**Wirkung auf die Ampel:** `placement.evaluate` nimmt `lead_rad`/`kipp_rad` (Default
0/0 = heutiges Verhalten) und leitet die Anflug-Rotation über `_nozzle_rotation` aus
`nozzle_quat(_PLACEMENT_TANGENT, …)` ab. Kipp ändert damit die Flansch-Ziel-
Orientierung → **nachweisbar** die Erreichbarkeit (Test:
`test_kipp_changes_reachability_evaluation`). Durchgereicht durch `decompose.evaluate`,
`placement.suggest.suggest` und die Aktionen `evaluate_placements`,
`propose_decomposition`, `suggest_placement`, `simulate_section`.

**Alternativen (verworfen):**
- *Rotation im Slicer und in placement getrennt aufbauen* (jeweils eigene Achse-
  Winkel-Kette): genau der #51-Fehler in neuer Form — verworfen zugunsten **einer**
  Funktion, die beide aufrufen (Konsistenztest `test_placement_shares_nozzle_quat_with_slicer`).
- *Winkel in Radiant im Job persistieren*: verworfen — die UI und der Nutzer denken
  in Grad; Umrechnung nach Radiant liegt an genau einer Stelle (`job_orientation`).
- *Orientierung an `tcp_frame.quat` hängen* (wie #58 der Klick-TCP): verworfen — das
  ist ein Werkzeug-fixer Offset, nicht **bahn-relativ**; Lead/Kipp müssen je Ziel aus
  der Tangente entstehen.
- *Harte Winkelgrenzen erzwingen*: verworfen — „Befund, kein Gate": Werte werden nicht
  gekappt (weiche Grenzen, Warnung statt Sperre), konsistent zur Eignungsprüfung.

**Geändert:** `core/src/fgc/domain/orientation.py` (`nozzle_quat`),
`core/src/fgc/domain/process_params.py` (`OrientationParams`, `job_orientation`,
`SliceParams.lead_rad/kipp_rad`), `core/src/fgc/slicer/build.py`,
`core/src/fgc/placement/evaluate.py`, `core/src/fgc/placement/suggest.py`,
`core/src/fgc/decompose/evaluate.py`, `core/src/fgc/pipeline/actions.py`
(`set_process_params` + Ampel-/Slice-Pfade), `core/src/fgc/pipeline/api.py`
(`OrientationParamsModel`), `schemas/project.schema.json` (`process_params.orientation`),
`viewer/src/api/projects.ts`, `viewer/src/ui/process-params-state.ts` (+ `.test.ts`),
`viewer/src/ui/process-params.ts`, `viewer/index.html`, `viewer/src/main.ts`, `README.md`.
Tests: `core/tests/test_orientation.py` (Golden), `core/tests/test_slicer.py`
(Slicer bäckt `nozzle_quat` + Konsistenz mit placement), `core/tests/test_placement.py`
(Kipp beeinflusst Ampel).
Verweis: Issue #61 (⇐ PRD #57); baut auf #59; ADR-006, ADR-016, ADR-017.

---

## 2026-07-06 — `clearWorld` gibt GPU-Ressourcen frei (Issue #50)

**Frage:** Wie verhindert der Viewer den VRAM-Leak, der bei jedem Re-Slice,
Sequenz-Start und Cut-Edit entsteht? Bisher entfernte `clearWorld` die
Welt-Kinder nur per `world.remove(child)` — das löst nur die Szenengraph-Kante;
Geometrien, Materialien und Texturen bleiben im GPU-Speicher (wachsender VRAM,
irgendwann WebGL-Context-Loss).

**Entscheidung:** `clearWorld` traversiert jeden entfernten Teilbaum und ruft
`geometry.dispose()`, `material.dispose()` (auch je Element von Material-Arrays)
und `dispose()` auf allen Textur-Eigenschaften der Materialien (map, normalMap,
… — per `isTexture`-Prüfung über die Material-Properties). Geometrien und
Materialien werden über `Set`s dedupliziert, damit innerhalb eines Teilbaums
geteilte Werkstoffe (z. B. gemeinsamer Link-/Joint-Werkstoff des Arms) genau
einmal disposed werden. Die Funktion wurde aus der `createViewport`-Closure als
frei testbare `export function clearWorld(world)` herausgezogen (die
Viewport-Methode delegiert nur noch).

**Shared-Material-Caveat:** Disposed wird ausschließlich, was unter `world`
hängt. Geteilte Singletons mit der *bleibenden* Szene gibt es nicht — Gitter,
Lichter und die Roboter-Vorschau (`robotPreview`) hängen direkt an `scene`, nie
an `world`, und jede Session/jeder Abschnitt baut seine Welt-Objekte frisch
(model.glb, Wand-Meshes, Toolpath, Kontext, TCP-Marker, Arm, Schnittebenen,
Basis-Marker). Die geklonten Schnittebenen-Materialien (`material.clone()` je
Ebene) sind ohnehin pro Ebene eigen — gefahrlos zu disposen.

**Alternativen verworfen:**
- *Nur Geometrien disposen*: unzureichend — Materialien und deren Texturen
  belegen ebenfalls GPU-Speicher.
- *Modulweiter `WeakSet` gegen Doppel-Dispose*: verworfen — persistiert über
  Aufrufe hinweg; ein lokales `Set` je `clearWorld`-Aufruf reicht und ist sauber.

**Leak-Nachweis (Akzeptanzkriterium):** `viewer/src/scene/clearworld.test.ts` —
belegt Dispose je Geometrie/Material/Array-Element/Textur, Dispose-genau-einmal
für ein geteiltes Material und (als `renderer.info.memory`-Analog über
`dispose`-Events gezählte Live-Ressourcen) keine wachsenden Zähler über 25
Clear-Zyklen.

**Geändert:** `viewer/src/scene/setup.ts` (`clearWorld` extrahiert + Dispose-Logik),
`viewer/src/scene/clearworld.test.ts` (neu). Kein README-Eintrag: reiner
Speicher-Leak-Fix ohne sichtbare Verhaltensänderung.
Verweis: Issue #50 (Tiefenprüfung 2); ADR-007/014.

---

## 2026-07-06 — Endeffektor-Bibliothek: Übersicht, Bearbeiten, Löschen (Issue #56)

**Frage:** Der Reiter Bibliothek konnte bisher nur *neu anlegen*. Es fehlte eine
Übersicht des Bestands, das Bearbeiten (falsche Ausrichtung/TCP/Stammdaten
korrigieren) und das Löschen. Wie strukturieren wir das, ohne die Prinzipien
(Endeffektor = `tools/<name>.json` + Mesh, Name = Identität, Viewer zustandslos,
Core einzige Schreibstelle) anzutasten?

**Entscheidung:** Der Bibliothek-Reiter bekommt zwei Ansichten im selben Panel —
eine **Galerie** (Karten mit Vorschaubild/Name/Vendor/Gewicht + Bearbeiten/Löschen
+ „+ Neuer Endeffektor") und den **Editor** (der bestehende 5-Schritt-Konfigurator,
von „ganzer Tab" zu „Ansicht innerhalb der Bibliothek"). Core-seitig zwei neue
Endpoints als dünne Aktions-Wrapper: `PUT /tools/{name}` (`update_tool_from_upload`,
Mesh optional) und `DELETE /tools/{name}` (`delete_tool`, entfernt JSON + Mesh).

- **Kein Rename (Out of Scope, bewusst):** Der Name ist Dateiname *und* `name`-Feld
  *und* der String, auf den `PrintJob.tool` verweist. Ein Rename müsste alle
  Projekte mitziehen — verworfen. Im Editor ist das Namensfeld Read-only; ein
  abweichender Name im Update-Body existiert gar nicht (Identität = Pfad-Parameter).
- **Mesh beim Update optional:** Ohne neues Mesh bleibt die bestehende Datei +
  Dateiname erhalten (nur Stammdaten/TCP/`mesh_transform`/Kanäle werden neu
  geschrieben); mit neuem Mesh greift dieselbe Validierung wie beim Anlegen, und
  ein altes Mesh mit abweichendem Dateinamen (Formatwechsel .stl→.glb) wird
  entfernt, damit keine Waise zurückbleibt.
- **Exakte Wiederherstellung (kein Re-Centering):** „Bearbeiten" stellt
  `mesh_transform` und `tcp_frame` (inkl. Düsenrichtungs-`quat`, #58) **direkt**
  auf die gespeicherten Frames und ruft **nicht** die Auto-Zentrierung/Auto-TCP-
  Heuristik auf — sonst würde „Bearbeiten" die Lage ungewollt neu berechnen. Dafür
  liefert `GET /tools` jetzt zusätzlich `tcp_frame`.

**Client-Thumbnails (die zentrale Abwägung):** Die Vorschaubilder rendert der
**Viewer live** (three.js-Offscreen-`toDataURL`) und cacht sie (In-Memory +
`localStorage`, Key = `mesh_path`).
- *Alternative A — serverseitiges PNG / headless-Python-Rendering:* verworfen.
  Bräuchte eine schwere Render-Abhängigkeit im Core, einen neuen Ausliefer-Endpoint
  und einen Invalidierungs-/Cache-Pfad auf der Platte — deutlich mehr Fläche für
  ~5 Endeffektoren.
- *Alternative B — gar kein Bild, nur Name/Icon:* verworfen; die visuelle
  Wiedererkennung ist der halbe Sinn einer Galerie (US 2).
- **Gewählt (Client-Render + Cache):** Der Viewer lädt das Mesh ohnehin schon fürs
  Replay (`loadToolMesh`), die Mesh-Größe ist klein (~5 MB STL), die Zahl klein
  (~5). Ein `data:`-URL-Cache je `mesh_path` macht das Bild beim erneuten Öffnen
  sofort da; ändert sich das Mesh, ist es ein anderer Key ⇒ automatisch neu.
  Bewusst nicht getestet ist das GL-Rendern selbst; getestet ist die **Cache-
  Schicht** (`ThumbnailCache`, vitest). Passt zu ADR-007 (Darstellung, keine
  Fachrechnung) und vermeidet neue Server-Fläche.

**Robustheit:** Lädt/rendert ein Mesh nicht (Altbestand ohne Datei, kaputt), zeigt
die Karte einen Platzhalter statt zu crashen (US 21/23). Nach jedem
Create/Update/Delete frischt der Viewer Galerie **und** `#tool-select` (Reiter
Roboter) auf (US 20).

**Weißbildschirm-Falle beachtet:** Die zwei Ansichten schalten über das
`hidden`-Attribut; das globale `[hidden]{display:none!important}` (style.css)
überstimmt das `#lib-editor{display:flex}` — sonst blieben beide sichtbar (dieselbe
Kaskaden-Falle wie bei den Tab-Panels, Design-Log 2026-07-05). Die neuen DOM-ids
(`lib-gallery`, `lib-editor`, `lib-cards`, `lib-empty`, `lib-new-btn`, `lib-status`,
`lib-api-warning`, `lib-back-btn`, `cfg-heading`) liegen alle in `index.html` und
sind gegen die `byId`-Aufrufe geprüft. Die Galerie-Ansichten sind `<div>` (kein
verschachteltes `<section>`), damit der DOM-Vertrag des geteilten Hauptsichtfelds
(`shell-structure.test.ts`) intakt bleibt.

**Test-Infrastruktur:** Der Galerie-Smoke braucht ein DOM — dafür `jsdom` als
Vitest-devDependency ergänzt und der Test per `// @vitest-environment jsdom`
umgestellt (erster DOM-Test im Viewer; die übrigen Tests bleiben `node`).

**Geändert:** `core/src/fgc/pipeline/actions.py` (`update_tool_from_upload`,
`delete_tool`), `core/src/fgc/pipeline/api.py` (`PUT/DELETE /tools/{name}`,
`tcp_frame` in `ToolInfoModel`), `core/tests/test_tool_configurator.py`;
`viewer/index.html` (Galerie + Editor-Wrapper), `viewer/src/style.css`,
`viewer/src/api/projects.ts` (`updateTool`/`deleteTool`/`tcp_frame`),
`viewer/src/ui/configurator.ts` (Edit-Modus), `viewer/src/ui/configurator-payload.ts`
(`buildUpdateToolRequest`), `viewer/src/ui/tool-library.ts` (neu),
`viewer/src/ui/tool-thumbnail.ts` (neu), `viewer/src/main.ts` (Verdrahtung) plus
Tests. Verweis: Issue #56; ADR-007/014/016.

---

## 2026-07-06 — Reproduzierbarer Start auf jedem PC (idempotentes Bootstrap)

**Frage:** Nach einem `git pull` startete das Tool auf einem zweiten PC nicht
(zuhause lief alles). Ursache: Die `.venv` wird von Hand angelegt und driftet
*still* von `core/pyproject.toml` weg — der Pull hatte `fastapi`/`uvicorn` (neue
Kern-Deps) und `pycollada` (geo-Extra) hinzugefügt, aber niemand führte
`pip install -e` erneut aus. Beim Start scheiterte dann `import fastapi`, die
Core-API kam nicht hoch. `pip check` bemerkte es nicht, weil die installierten
`fgc-core`-Metadaten selbst veraltet waren. Zusätzlich war die dokumentierte
Einrichtung (`py -3.12 -m venv`) brüchig: die Maschine hatte nur Python 3.14 und
kein `py -3.12`, obwohl `pyproject` nur `>=3.12` verlangt.

**Alternativen:**
- *Nur Deps von Hand nachinstallieren* — behebt das Symptom, nicht das Driften;
  beim nächsten Dep-Zuwachs wieder kaputt.
- *Deps committen / venv versionieren* — verworfen; venv/node_modules bleiben
  gitignoriert (plattform-/Python-spezifische Binärartefakte).
- *Bei jedem Start blind `pip install -e` + `npm ci`* — korrekt, aber je Start
  mehrere Sekunden verschenkt.
- **Gewählt:** *Idempotentes Bootstrap mit Hash-Markern.* Ein Skript
  (`scripts/bootstrap.ps1`, POSIX-Spiegel `scripts/bootstrap.sh`) ist die
  einzige Provisionierungs-Quelle: legt die `.venv` an (sucht sich ein
  vorhandenes Python `>=3.12` selbst, keine Minor erzwungen), synchronisiert
  `core[dev,geo]` und die Viewer-Deps. Ob etwas zu tun ist, entscheiden
  SHA-256-Marker über `pyproject.toml` (`.venv\.deps-hash`) bzw.
  `package-lock.json` (`viewer\node_modules\.deps-hash`) — passt der Hash, ist
  der Lauf ein Sekunden-No-Op.

**Selbstheilend:** `fgc.cmd` und `start_viewer.cmd` rufen das Bootstrap im
Leisemodus vor dem Start auf; ein frisch gepulltes Repo startet dadurch ohne
Handgriff sauber. `setup.cmd`/`setup.sh` bleiben als expliziter Einrichtungsweg
(Doppelklick) mit Pause bei Fehlern.

**Begründung:** Verhindert das Driften *strukturell* statt es je Maschine von
Hand zu heilen, ohne die Startzeit zu belasten und ohne Binärartefakte zu
versionieren. `npm ci` wird bevorzugt (reproduzierbar aus dem Lockfile), fällt
bei gesperrten Windows-Binaries (esbuild/rollup, EPERM) automatisch auf
`npm install` zurück.

**Neu:** `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `setup.cmd`,
`setup.sh`. **Geändert:** `start_viewer.cmd`, `fgc.cmd` (Bootstrap-Aufruf),
`README.md` (Schnellstart). Kein ADR — Werkzeug-/Betriebsentscheidung ohne
Architekturrang.

## 2026-07-06 — Replay bedient im Reiter Simulation + Rückweg zur Übersicht + Kennzahlen nach Neuladen (Issue #48)

**Frage:** Die Tiefenprüfung 2 fand drei zusammenhängende Befunde am
Simulations-Replay (PRD-Stories 22–26): (1, major) „Im Player ansehen"/
„Gesamtablauf"/das Auto-Öffnen nach dem Simulieren riefen `resetRunState`/
`clearWorld` und **zerstörten die Modellübersicht ohne Rückweg** — danach zeigte
der Reiter Druckplan weder Schnittebenen noch Basis-Marker, das Ebenen-Drag war
tot, nur erneutes Projekt-Öffnen reparierte. (2, minor) Jeder „Slicen +
Simulieren"-Klick öffnete **ungefragt** den Player und wechselte in den Reiter
Projekt; die Player-Bedienung lebte nur im Projekt-Aside, obwohl das Replay laut
PRD in den Reiter Simulation gehört. (3, minor) Nach Projekt-Neuladen fehlten die
Kennzahlen je Abschnitt (Druckzeit, Achsauslastung, Warnungszahl): `setSectionRuns`
markierte nur „Lauf vorhanden", `trajectory.meta` wurde nie nachgeladen.

**Alternativen:**
- *Befund 1 — Modellübersicht als persistenter Szenen-Bestandteil, Replay als
  zweiter Layer:* am saubersten, aber teuer und fehleranfällig im geteilten
  Einzel-`world`-Modell (Dual-Layer-Verwaltung, `clearWorld`-Dispose,
  Picking-/Drag-Guards je Layer). **Verworfen** zugunsten der einfacheren, vom
  Issue ausdrücklich angebotenen Alternative.
- **Gewählt (Befund 1):** *„← Zurück zur Übersicht"-Aktion* — lädt den
  Übersichts-Lauf (`currentAssessmentRun`) neu; `showRun` baut die Modellübersicht
  inkl. Schnittebenen + Basis-Marker aus dem noch gültigen Druckjob-Zustand wieder
  auf (`updateCutPlanes`/`updatePlacementMarker` am Ende von `showRun`). Der
  Rückweg ist damit ein Ein-Klick statt „Projekt neu öffnen".
- **Gewählt (Befund 2):** *Replay im Reiter Simulation spiegeln, kein
  Zwangswechsel.* Ein kompakter Player (Play/Pause, Zeit-Slider, Phase, Zurück-
  Button) sitzt im Simulation-Aside und bedient **dieselbe** `TrajectoryPlayer`-
  Instanz wie das Projekt-Panel — kein zweiter Player, nur eine zweite Bedien-/
  Anzeige-Fläche. Das Auto-Öffnen nach „Slicen + Simulieren" entfällt (die
  Kennzahlen erscheinen in der Zeile; das Replay startet man bewusst); „Im Player
  ansehen" und „Gesamtablauf abspielen" wechseln **nicht** mehr in den Reiter
  Projekt. Das Projekt-Panel-Player bleibt als Zweitanzeige erhalten
  (abwärtskompatibel für den `?run=`-Direkteinstieg und Einzelwand-Slices).
- **Gewählt (Befund 3):** *Kennzahlen lazy aus `trajectory.json` nachladen.*
  `setSectionRuns` stößt je Lauf ein `loadSummary(runPath)` an; main.ts liest den
  `meta`-Block und leitet die Summary über die neue **reine** Funktion
  `summaryFromMeta` ab (ADR-007: der Viewer rechnet nichts, er liest nur). Eine
  stale Antwort (Reset/Neu-Simulieren zwischenzeitlich) wird über den Lauf-Pfad-
  Vergleich verworfen.

**Begründung:** Die drei Befunde sind ein Wurf — alle drei drehen sich darum, dass
das Replay bislang den Projekt-Reiter kaperte statt im Reiter Simulation zu leben.
Die gewählte Kombination respektiert ADR-007 (der Viewer setzt/zeigt nur, alle
Zahlen und die Bahn kommen als Core-Artefakt) und bleibt strikt modular: die
urteilsfreie Zustands-/Formatierlogik (`summaryFromMeta`) liegt bei den reinen
TS-Funktionen (`ui/simulation-state.ts`, vitest), das DOM-Verdrahten in
`ui/simulation.ts`, die Szenen-/Player-Orchestrierung in `main.ts`. Bewusst **nicht**
gemacht: den Dual-Layer-Scene-Umbau, ein automatisches Zurückspringen beim
Reiterwechsel (überraschend, verlöre die Wiedergabe) und ein zweiter
`TrajectoryPlayer` (Zustands-Duplikat). Kein ADR — Interaktions-/UI-Entscheidung
ohne Architekturrang, ADR-007 unverändert gültig.

**Neu:** Player-Block `#sim-player` in `index.html`; `summaryFromMeta` +
`showPlayer`/`setPlayerState`/`setPhase`/`hidePlayer` + `loadSummary`-Callback in
`ui/simulation-state.ts`/`ui/simulation.ts`; `backToOverview`/`loadSectionSummary`
in `main.ts`; 3 vitest-Fälle für `summaryFromMeta`. **Geändert:** `main.ts`
(kein `setActiveTab("projekt")` mehr beim Replay, Player-Spiegelung in
`showRunInner`/`updateSequence`), `ui/simulation.ts` (kein Auto-Öffnen nach
Simulieren), `style.css`, `README.md`. 220 Viewer-Tests grün, `tsc --noEmit` +
`vite build` clean.

---

## 2026-07-06 — Realistisches Bewegungsmodell `simulation.motion` (Issue #62, Scheibe 4)

**Frage:** Die Simulation zeitparametrierte bislang **stückweise-konstant**
(`timeparam.parametrize`): je Toolpath-Segment eine konstante
Gelenkgeschwindigkeit, Fahrbarkeit nur an den groben Zielen geprüft. Scheibe 4
(PRD #57) verlangt ein Modell, das die reale Bewegung so echt wie möglich
abbildet — Beschleunigungsrampen und **movel** (kartesisch-gerade
Werkzeugbewegung) — und das die Fahrbarkeit der *ganzen* Geraden ehrlich
beurteilt statt nur ihrer Endpunkte.

**Alternativen:**
- *Fahrbarkeit weiter nur an den Zielen prüfen:* billig, aber verfehlt genau die
  Singularität/Reichweitengrenze **mitten** in einer movel-Geraden. Verworfen.
- *Stiller Gelenk-Fallback bei nicht fahrbarer movel-Gerade* (heimlich auf movej
  umschalten, um „irgendeine" Bewegung zu liefern): **verworfen** — das kaschiert
  einen echten physikalischen Befund und gibt eine physisch nicht fahrbare gerade
  Werkzeugbahn als machbar aus.
- *Blending/Look-ahead gleich mitliefern:* bewusst auf **Scheibe 4b / Issue #63**
  vertagt, damit dieses Slice klein und die Halt-an-jedem-Ziel-Semantik prüfbar
  bleibt.

**Entscheidung (Architekturrang → ADR-019):** neues, tiefes, isoliert testbares
Modul `fgc.simulation.motion`, das `build_trajectory` aufruft:
- **Trapez-Geschwindigkeitsprofile** (Rampe/Halt/Bremse), ruhe-zu-ruhe je Segment,
  unter der eingestellten Beschleunigung; ohne Blending hält der Arm an jedem Ziel.
- **movel-lineare TCP-Interpolation** (dichte Zwischenposen entlang der
  kartesischen Geraden, Position linear + Orientierung per Slerp, IK je Pose) für
  Druck; **movej-Gelenkinterpolation** für Travel. Bewegungstyp + Dynamik aus
  `process_params.motion` (Rail aus #59).
- **Ehrliche Befunde:** eine einzige `select_along_path` über die *ganze* dichte
  Bahn hält die Konfiguration, die die Geraden fahrbar lässt; eine unfahrbare/
  singuläre Zwischenstelle wird als **verortete** `meta.warnings` (mit
  interpolierter Zeit) gemeldet, der Arm friert dort auf der letzten gültigen
  Lösung ein (sichtbar, wie das Home aus #66/#56) — **kein** stiller Rückfall auf
  Gelenkinterpolation.

**Begründung:** movel bedeutet „die ganze Gerade fahrbar", nicht nur die
Endpunkte — die alte grobe Prüfung verfehlte das. Ein stiller Fallback wäre die
bequeme, aber unehrliche Lösung; das Projekt behandelt Urteile konsequent als
**Befund, nicht als kaschierten Durchlauf** (core/CONTEXT.md). Die kartesischen
vel/acc-Grenzen und Abtastdichten in `MotionParams` sind **provisorisch markiert**
(`provisional=True`, Spike S1), bis am Gerät gemessene Werte vorliegen — analog
den provisorischen Slice-/Workspace-Werten. Blending ist bewusst separat (#63),
damit das Slice ein prüfbares, kleines Bewegungsmodell bleibt.

**Neu:** `core/src/fgc/simulation/motion.py` (`MotionParams`, `trapezoid_times`,
`slerp`/`densify_line`/`densify_joints`, `build_motion`, `motion_from_job`);
`core/tests/test_motion.py` (17 Fälle: Trapez-Grenzen, movel-Linearität,
Monotonie, **Mitten-in-movel-Singularität ⇒ verortete Warnung + Einfrieren statt
Ausweichbogen**, movej-Gelenkinterpolation, `process_params.motion`-Overrides);
`docs/adr/ADR-019-*`; `motion`-Block in `schemas/project.schema.json`.
**Geändert:** `simulation/build.py` (nutzt `build_motion` statt `parametrize`;
`_tcp_poses` statt `_flange_frames`; io-Schrittfunktion über die Target-Zeiten,
dichteunabhängig), `simulation/__init__.py`, `pipeline/actions.py`
(`simulate_section` reicht `motion_from_job(job)` durch), `tests/test_simulation.py`
(io-Onset zeit- statt indexbasiert, Sample-Zahl ≥ Target-Zahl), `README.md`.
34 Simulations-/Motion-Tests grün, restliche Core-Suite grün (ruff clean; ein
Windows-`os.replace`-Flake in `project/store.py` unabhängig, isoliert grün).

## 2026-07-06 — #62-Nachtrag: NaN in trajectory.json (movej ohne Bewegung) + JSON-Guardrail

**Frage:** Nach #62 lud der Viewer frisch simulierte Abschnitte nicht mehr —
`showRun` warf `SyntaxError: ... "t_s": NaN ... is not valid JSON`.

**Ursache:** Ein `movej`-Travel-Segment **ohne Gelenkbewegung** (identische
Start/End-Konfiguration) → `_limit_ratio` liefert `math.inf` → in
`trapezoid_times` wird `s_ramp = v²/(2a) = inf²/(2·inf) = NaN`. Python
`json.dump` schreibt `NaN` als Literal (Default `allow_nan=True`) — ungültiges
JSON (RFC 8259), an dem der Browser-`JSON.parse` scheitert.

**Alternativen:** (a) `_limit_ratio` endlichen Fallback statt `inf`;
(b) movej-Zweig Null-Bewegung sonderbehandeln; (c) `trapezoid_times` gegen
nicht-endliche Dynamik härten.

**Entscheidung:** (c) — `trapezoid_times` fällt bei nicht-endlicher vel/acc auf
endliche Floor-Zeiten zurück (Null-Bewegung ~ 0 Zeit, physikalisch korrekt).
Zusätzlich `write_artifact` mit `allow_nan=False`: künftig scheitert jeder
`NaN`/`Inf` **laut beim Schreiben** am Entstehungsort statt still eine unladbare
Datei auszuliefern.

**Begründung:** Wurzelbehebung im tiefen Modul (nicht am Symptom), plus eine
Schutzschicht, die die Fehlerklasse für **alle** Artefakte abfängt. Regressionstest
`test_trapezoid_nonfinite_dynamics_yield_no_nan`. Gefunden per Live-Reproduktion
(headless-CDP-Klick), nachdem zwei reine Code-Analysen die Ursache verfehlten —
Lehre: UI-Ladefehler am echten Lauf reproduzieren, nicht raten.

## 2026-07-06 — #64: DRL-Emitter-Umbau auf per-Target movel/movej + Provisorik-Stempel

**Frage:** Der bisherige Emitter erzeugte **ein `movej` je Simulations-Sample**
mit `vel/acc=0` (Gerüst aus #13). Für ein controller-natives, kürzeres DRL soll
er auf **per Toolpath-Target** umstellen: `movel` für Druck-, `movej` für
Verfahrbewegungen, mit den `process_params.motion`-Werten (vel/acc/Blending/ref).
Woher nimmt der Emitter die Ziele und die Pose, und wie kommt die Provisorik zum
Nutzer?

**Alternativen:**
- **Datenquelle:** (a) weiter aus `trajectory.json` (dichter Gelenk-Stream) —
  passt aber nicht zu „per Target" (die Samples sind viel dichter als die
  Targets, kein Target-Marker im Stream); (b) aus `toolpath.json` (die Targets
  mit `kind`/`frame`/`v_mm_s`/`io`) + `process_params.motion`. → **(b)**.
- **Pose-Form:** (a) Gelenk-`posj` je Target (bräuchte IK im Emitter — koppelt
  ihn an die Kinematik); (b) kartesische `posx` (Task-Pose), der Controller löst
  die IK. → **(b)**: hält den Emitter kinematikfrei; die IK/Bahnwahl bleibt in der
  Simulation (ADR-002/011). `movej(posx(…))` ist gültiges Doosan-DRL.
- **Frame:** die `posx` entsteht aus `wall_to_base ∘ frame` (Setup als *die eine*
  Transformationsstelle, ADR-006); Orientierung als ZYZ-Euler in Grad (Doosan-
  Konvention) — Grad ausschließlich im Emitter (ADR-006).
- **Blending/ref-Herkunft:** neue Felder `blending_mm`/`ref` an `MotionParams`
  (+ `MOTION_PARAM_KEYS`), damit `process_params.motion` die *eine* Quelle bleibt
  (#59-Rail). `build_motion` liest sie (noch) nicht — die geometrische Verrundung
  ist #63; hier nur das `radius=`-Argument der DRL-Zeile.
- **Provisorik:** (a) hartes Gate bis S1 — verworfen (ADR-013: Eignung/Zahlen sind
  Befund, kein Gate); (b) **Provisorik-Stempel** im DRL-Kopf + sichtbare Kennzeichnung
  im Reiter Export. → **(b)**.

**Entscheidung:** `emit_drl(toolpath, setup, provenance, motion)` erzeugt je Target
`movel`(print)/`movej`(travel) mit `posx`, `vel`/`acc`/`radius`/`ref` aus `motion`
(fällt für `vel` auf das je Target kommandierte `v_mm_s` zurück, wenn
`tcp_vel_mm_s` fehlt). io-Change-on-Delta + Kanal-Mapping unverändert (ADR-011),
jetzt über die Targets statt die Samples. Der DRL-Kopf trägt bei
`motion.provisional` einen Provisorik-Stempel (vel/acc/Blending als angenommen,
kein Gate — ADR-006/012/013); `index.html` (Reiter Export) kennzeichnet die
Ausgabe zusätzlich statisch als provisorisch. `emit_drl_run`/CLI lesen jetzt
`toolpath.json` statt `trajectory.json`; der dichte Gelenk-Stream
(`trajectory.json`) bleibt unangetastet für den Viewer-Replay.

**Begründung:** Trennung der Zuständigkeiten — die Simulation besitzt IK/Zeit/den
dichten Stream, der Emitter besitzt nur die Übersetzung Toolpath→DRL-Text (grad-
und controller-nah). Das DRL wird kürzer und dem Controller (IK der Cartesian-
Ziele + Blending) überlassen. `process_params.motion` bleibt die eine Quelle für
Bewegungstyp/Dynamik. **Geändert:** `postproc/emitter.py` (Umbau),
`postproc/__init__.py`, `simulation/motion.py` (nur additive Felder
`blending_mm`/`ref`, von `build_motion` ungenutzt), `pipeline/actions.py`
(`emit_drl_run` liest Toolpath + reicht `motion_from_job` durch),
`pipeline/cli.py` (Hilfetexte), `viewer/index.html` (Provisorik-Hinweis),
`tests/test_drl_emitter.py` (neu auf Targets + Golden-File), Golden
`fixtures/golden_drl/program.drl`, `tests/test_export.py` (Assertions auf
movel/movej), `README.md`. Volle Core-Suite grün, ruff clean; Viewer `tsc`/vitest
grün.

## 2026-07-06 — #63 (Scheibe 4b): Blending — Ecken-Verrundung in Simulation + Zeit

**Frage:** Scheibe 4 (#62) hält an jedem Wegpunkt voll an. Mit gesetztem
`blending_mm` (`process_params.motion`, seit #64 im Datenmodell, vom Emitter als
`radius=` geschrieben) soll `build_motion` die Ecke **geometrisch verrunden**
*und* die Geschwindigkeit dort erhalten (Bahn und Zeit ändern sich). Wie
verrunden, und wie bleibt die Ecken-Geschwindigkeit > 0?

**Alternativen:**
- **Verrundungsgeometrie:** (a) controller-echter **Kreisbogen** tangential an
  beide Segmente; (b) **quadratische Bézier**-Kurve mit der Ecke als Kontrollpunkt
  (Eintritt `E` = `r` vor der Ecke, Austritt `X` = `r` danach); (c) Catmull-Rom/
  B-Spline über mehrere Wegpunkte. → **(b)**: reine, lokale, parameterfreie Formel
  (nur `r`), garantiert C¹-glatt und stabil, ohne Ebenen-/Tangenten-Sonderfälle
  eines Kreisbogens. Da Blending ohnehin **provisorisch** ist (der echte
  Verrundungsverlauf ist controller-spezifisch, S1), reicht eine plausible,
  robuste Näherung; Kreisbogen bleibt Revisionsoption nach S1.
- **Radius-Deckelung:** `r = min(blending_mm, |ap|/2, |pb|/2)` — die halbe
  Segmentlänge verhindert, dass sich die Verrundungsfenster benachbarter Ecken
  überlappen (jede Ecke nimmt höchstens die Hälfte jedes Nachbarsegments).
- **Geschwindigkeitserhalt:** (a) je Segment weiter ein eigenes ruhe-zu-ruhe-
  Trapez, nur die Geometrie verrunden — verworfen, die Ecke bliebe ein Vollstopp;
  (b) **movel-Segmente über eine verblendete Ecke zu EINEM Trapez zusammenfassen**
  (verkettete Bogenlänge). → **(b)**: die Ecke liegt im Inneren eines ruhe-zu-ruhe-
  Profils ⇒ Geschwindigkeit dort strikt > 0 (v=0 nur an den beiden Enden), und die
  Gesamtzeit sinkt (keine Zwischen-Bremse/-Rampe). Beweisbar ohne neue Dynamik.
- **Integrationsstelle:** die Ecken-Samples werden **vor der IK** auf die Bézier
  umgesetzt (reine Umpositionierung, Sample-Anzahl/Indizes unverändert) — so
  bleiben Warnungs-Verortung und `target_times` gültig, und die IK löst die
  tatsächlich verrundete Geometrie (FK zeigt die Verrundung ehrlich).
- **Geltungsbereich:** nur **movel↔movel**-Ecken (Verrundung im TCP-Raum
  wohldefiniert); movej-Travel-Ecken behalten den Vollstopp — bewusst außerhalb
  der provisorischen Scheibe.

**Entscheidung:** `MotionParams.blending_mm > 0` ⇒ `build_motion` verrundet jede
movel↔movel-Ecke per `blend_corner`/`_bezier3` (Ecken-Samples innerhalb `r` auf
die Bézier E→P(Kontrolle)→X umgesetzt) und fasst die angrenzenden movel-Segmente
zu einem Trapez zusammen. `blending_mm == 0`/None ⇒ **bit-genau** das
Scheibe-4-Verhalten (Vollstopp). Alles als **provisorisch** markiert
(`MotionParams.provisional`, S1). ADR-019 um einen Blending-Nachtrag ergänzt.

**Begründung:** Wurzelnahe Umsetzung im tiefen Modul, die beide geforderten
Effekte nachweislich liefert (Geometrie *und* Zeit), rückwärtskompatibel und
isoliert testbar, ohne die provisorischen vel/acc-Werte anzutasten. Tests:
`test_blend_corner_entry_exit_and_clamp` (Geometrie-Formel),
`test_blending_rounds_corner_geometry` (Ecke abgekürzt),
`test_blending_keeps_corner_velocity_and_shortens_time` (v>0 + Zeit sinkt),
`test_blending_zero_matches_full_stop_scheibe4` (Regression Vollstopp).
**Geändert:** `simulation/motion.py`, `tests/test_motion.py`, `README.md`,
`docs/adr/ADR-019`, `docs/status.md`. Core 421 grün (1 bekannter os.replace-
Windows-Flake), ruff clean. Emitter/Viewer unberührt.

## 2026-07-06 — #65 (Scheibe 6): Singularitäts-Advisor — Typ-Klassifikation + gezielte Vorschläge

**Frage:** Das reziproke Konditionsmaß (#11) sagt nur *wie nah* an einer
Singularität, nicht *welcher Art* und nicht *was hilft*. Wie klassifizieren wir die
Nähe nach Typ (Handgelenk/Ellbogen/Schulter) und leiten je Typ einen anwendbaren
Hebel (Kipp/Platzierung/Config-Flip) mit nachweisbarer Vorher/Nachher-Marge ab —
ohne ein neues Skalarmaß und ohne Urteilendes in den Viewer zu ziehen (ADR-007)?

**Alternativen:**
- **Nähe-Metrik:** (a) je Typ ein eigenes Skalar — verworfen (dupliziert die
  Rangbetrachtung, driftet gegen `singularity_measure`); (b) **Nähe bleibt das
  Konditionsmaß**, nur eine geometrische **Typ**-Aufteilung kommt dazu. → (b).
- **Typ-Indikatoren aus den Gelenkwinkeln:** Handgelenk = J5 (`joints[4]`) nahe
  0/±π; Ellbogen = Schulter→Handwurzel-Abstand nahe Streckung `c2+c3` / Faltung
  `|c2−c3|`; Schulter = radialer Abstand der Handwurzel von z0 nahe dem
  geometrischen Minimum (Offset `b`). Drei dimensionslose Schwere-Werte ∈ [0,1],
  größter gewinnt (deterministisch). Bänder physikalisch motiviert
  (`WRIST_BAND_RAD=0.35`, `SHOULDER/ELBOW_BAND_FRACTION=0.12/0.10` der Reichweite),
  im Scheibe-6-Spike an synthetischen Posen verifiziert (Handgelenk/Ellbogen/
  Schulter sauber getrennt).
- **Hebel je Typ:** Handgelenk→**Kipp-Delta** (`process_params.orientation`),
  Reichweite/Ellbogen→**Platzierungsoption** (`placement.suggest`),
  Schulter/konfig-abhängig→**Config-Flip** (andere IK-Konfiguration). Der Kipp-Hebel
  sucht das Delta, das die **kinematische Marge in derselben `placement.evaluate`**
  anhebt, ohne den erreichbaren Anteil zu senken — ein Spike-Scan fand robuste
  Wand-/Platzierungs-Fixtures (z. B. 600×700 mm, Abstand 500, Podest 300: Marge
  0.0004 → 0.12 bei Kipp −40°).
- **Vorher/Nachher-Marge:** (a) eigener Bewertungspfad — verworfen (Nachweis
  wertlos, wenn nicht dieselbe Metrik); (b) **dieselbe `placement.evaluate`**. → (b).
- **Anwenden:** (a) neue Schreib-Route — verworfen; (b) **bestehende Schreibstellen**
  (ADR-016): Kipp über `PUT …/process-params` (Slice-/Lead-Block bewahrt),
  Platzierung über Bewertung/Auswahl; der `process`-Bump veraltet Downstream
  (ADR-017). → (b). Config-Flip in v1 **rein beratend** (keine Persistenz der
  Konfigurationswahl).
- **Referenzposen:** **bewusst weggelassen** (nur Start-Seed der Konfigurationswahl,
  #11) — der Advisor bewertet die real gesampelte Wandbahn, keine hinterlegten
  Sollposen. Scope-Grenze wie im Acceptance-Kriterium.
- **Modul-Heimat:** `singularity` in `fgc.kinematics` (reine Kinematik); der
  Advisor in `fgc.placement` (nutzt `evaluate`/`suggest` + `singularity`, saubere
  Importrichtung, kein Zyklus).

**Entscheidung:** Zwei tiefe Module — `fgc.kinematics.singularity` (`classify`) +
`fgc.placement.advisor` (`advise`/`suggestion_for`) — plus read-only Aktion
`advise_singularity` und Route `POST …/singularity-advice`. Viewer: reine
Darstellungs-/Anwenden-Logik in `ui/singularity-advisor-state.ts` (vitest), dünnes
Panel `ui/singularity-advisor.ts` im Reiter Druckplan; „Anwenden" ruft die
bestehenden Routen. ADR-020 angelegt.

**Begründung:** Wurzelnahe Umsetzung im Core (ADR-007), keine neue Metrik (baut auf
#11), nachweisbare Margenverbesserung in derselben Bewertung, rückwärtskompatibel
(kein Vorschlag ohne Wahl/Roboter). Tests: `test_singularity.py` (7, Typ je
synthetischer Pose), `test_singularity_advisor.py` (7, Hebel je Typ + Kipp hebt
Marge), `test_placement.py` (+4 Aktion/API), vitest `singularity-advisor-state`
(10). **Geändert:** `kinematics/singularity.py`, `kinematics/__init__.py`,
`placement/advisor.py`, `placement/__init__.py`, `pipeline/actions.py`,
`pipeline/api.py`, `tests/test_singularity*.py`, `tests/test_placement.py`,
Viewer `api/projects.ts`, `ui/singularity-advisor*.ts(+test)`, `main.ts`,
`index.html`, `README.md`, `docs/adr/ADR-020`, `docs/status.md`. Core 436 Tests
grün bis auf die bekannten os.replace-Windows-Flakes (ordnungsabhängig, isoliert
grün), ruff clean; Viewer 230 + tsc grün.
---

## 2026-07-06 — Scheibe 2b: Prozessparameter-Panel-Ausbau (Issue #60, PRD #57)

**Frage 1 — Aufklapp-Muster für „Fortgeschritten".** Wie den optionalen
Fortgeschritten-Bereich im Prozessparameter-Panel ein-/ausklappen, ohne einen
`<details>`-Zoo einzuführen?

**Alternativen:** (a) natives `<details>`/`<summary>` je Bereich; (b) eine
schwergewichtige Accordion-Komponente; (c) ein schlichtes, wiederverwendbares
Muster — Button + versteckter Körper, der reine Zustand als DOM-freie Funktion.

**Entscheidung:** (c). Neues Modul `ui/collapsible-state.ts` — Zustand ist ein
einzelnes Boolean (`expanded`), `toggleCollapsible`/`setCollapsible` sind reine
Transitionen, `collapsibleView` leitet die drei DOM-Eigenschaften ab (Körper
versteckt, `aria-expanded`, Button-Label mit ▸/▾-Marker). Das Panel
(`ui/process-params.ts`) hält nur die Instanz und spiegelt `collapsibleView` aufs
DOM. 7 vitest-Fälle für die reine Funktion.

**Begründung:** Konsistent zu den anderen `*-state.ts`/`*.test.ts` im Viewer
(Fachlogik von three.js/DOM getrennt, isoliert testbar). `<details>` streut den
Zustand ins DOM und ist schlecht prüfbar; ein Muster statt vieler `<details>`
bleibt wiederverwendbar für spätere Bereiche.

**Frage 2 — io_print/io_travel: dict oder Skalar im Job?** `SliceParams.io_print`/
`io_travel` sind `dict[str, float]` (Kanal → Wert, v0 `pump_a`/`pump_b`). Wie im
UI editierbar machen?

**Alternativen:** (a) voller per-Kanal-Editor im Job/Panel (die Kanäle hängen am
gewählten Endeffektor, im Panel nicht ohne Weiteres bekannt); (b) den Dict im Job
speichern, im UI aber nur einen repräsentativen Wert zeigen (lossy beim Round-Trip);
(c) im Job **einen Skalar** je Zielart persistieren und beim Lesen gleichförmig auf
die io-Kanäle der Basis-`SliceParams` ausdehnen.

**Entscheidung:** (c). Der Job-Block trägt `io_print`/`io_travel` als **Skalar**;
`job_slice_overrides` dehnt ihn über die Kanäle aus (`{ch: wert für ch in
base.io_*}`). Analog `v_print_mm_s`/`v_travel_mm_s` als Skalare, additiv in
`SLICE_PARAM_KEYS`; die io-Keys getrennt in `IO_PARAM_KEYS` (Skalar→dict-Übergang).
Der Slicer (`build_toolpath`) verbraucht die Werte unverändert je Ziel als `v_mm_s`/
`io` — sie wirken durch Slice → Simulation → Export.

**Begründung:** v0 nutzt für alle Pumpen ohnehin denselben Wert (0,5/0,5 bzw.
0,0/0,0); per-Kanal-Differenzierung ist ein Materialphasen-Thema (φ-Feld/Gradierung).
Ein Skalar hält den „Fortgeschritten"-Bereich schlicht (vier Zahlenfelder), ist
voll round-trip-fähig und rückwärtskompatibel (fehlender Block = Karten-/Code-
Default). Die Gruppen bleiben auf **einer Rail** (`process_params.slice`) — kein
neuer Block, dieselbe `PUT …/process-params`-Route und veraltet-Markierung (ADR-017).

**Frage 3 — Reiter Projekt aus dem Simulations-Rückweg lösen.** Das Standalone-
Reslice im Reiter Projekt (Issue #9, `?run=`-Abspieler) konkurriert im Projektfluss
mit dem Vorwärtsweg (Slice-Parameter im Druckplan, Slicen je Abschnitt in der
Simulation).

**Alternativen:** (a) das Reslice-Panel ganz entfernen (bräche den `?run=`-
Abspieler-Modus ohne Projekt); (b) im Projektfluss nur die Basis-Slice-Felder
read-only spiegeln; (c) das Standalone-Reslice auf den Abspieler-Modus **ohne
Projekt** beschränken (im Projektfluss ausblenden).

**Entscheidung:** (c). `Panel.setResliceParams`/`setProjectOpen` blenden das
Reslice-Panel aus, sobald ein Projekt offen ist (`_syncReslice`) — parallel zur
schon bestehenden Logik, die im Projektfluss statt „Diese Wand slicen" nur „In
Druckjob übernehmen" zeigt (Issue #10). Der `?run=`-Abspieler behält das Reslice.

**Begründung:** Der Vorwärtsfluss bleibt die eine Quelle im Projekt; kein
konkurrierendes, laufordner-erzeugendes Reslice im Reiter Projekt und kein
Rücksprung. Der Abspieler-Modus (kein Projekt) bleibt voll funktionsfähig —
minimale, gezielte Änderung statt Entfernen.

**Verifikation:** 231 Viewer-Tests (24 neu: 7 collapsible-state + Erweiterungen
process-params-state) + tsc/`vite build` grün; Core-Tests der berührten Pfade
(test_project, test_section_simulation, test_slicer, test_eligibility, test_api)
grün, ruff clean. Flow-through-Test `test_simulate_section_uses_job_speeds_and_io`
belegt v_print/v_travel/io bis in die Toolpath-Targets.

## 2026-07-07 — Endeffektor-Kompatibilitäts-Tags `compatible_robots` (Issue #71, PRD #69)

**Frage:** Wie trägt ein Endeffektor die Roboter, zu denen er passt, ohne den
Altbestand zu brechen und ohne schon eine Filterwirkung einzuführen (die kommt in
#74)? Und wie unterscheidet man „passt nirgends hin" von „noch nicht getaggt"?

**Alternativen:** (a) das Feld immer schreiben (leere Liste als Default im
Artefakt) — brächte jeden bestehenden `tools/*.json` beim nächsten Speichern zum
Wackeln und macht „fehlt" von „leer" nicht unterscheidbar; (b) Kompatibilität als
Gate (inkompatible Endeffektoren gar nicht wählbar) — verstößt gegen „Befund, kein
Gate"; (c) das Feld **optional** halten, nur bei nicht-leerer Wahl ins Artefakt
schreiben, und **leer/fehlend = „unbekannt"** (nie „inkompatibel").

**Entscheidung:** (c). `tool.schema.json` bekommt optionales `compatible_robots`
(Array von Roboter-Namen, `additionalProperties: false` bleibt gültig). `ToolDef`
führt es als `tuple[str, ...] = ()`; `build_tool_artifact` schreibt es **nur bei
nicht-leerer Liste** (so bleibt ein untagged Altbestand byte-gleich). Create/
Update-API-Modelle und `GET /tools` führen es mit Default `[]` durch. Der Editor
bekommt ein `<select multiple>` „passt zu Roboter(n)", befüllt aus `GET /robots`
über eine neue `ToolConfigurator.setRobots(names)` (einmalig beim Start verdrahtet,
analog `robotPanel.setRobots`); die Wahl wird beim Bearbeiten vorbefüllt. Der
Viewer entdoppelt die Wahl und verwirft leere Namen (`dedupeRobots`); eine
gespeicherte, im Katalog (noch) unbekannte Wahl bleibt sichtbar statt still
wegzufallen. **Roboter = Nabe** (Memory PRD #69): der Endeffektor verweist auf den
Roboter, nicht umgekehrt.

**Begründung:** Optional-und-nur-bei-Bedarf-schreiben ist der Migrationsschutz —
kein erzwungenes Feld, kein None-vs-missing-Durcheinander, und „unbekannt" ≠
„inkompatibel" hält die Tür für jeden Roboter offen, bis #74 gezielt ausgraut
(weiter kein Gate). Additiv über die ganze Kette, exakt dem Muster von
`mesh_transform` (#28) und `tcp_frame` in der `GET /tools`-Antwort (#56) folgend.

**Verifikation:** Core 445 pytest grün (neu: build_tool_artifact trägt/omittet das
Feld, ToolDef-Default leer, create/update-Roundtrip, POST/GET/PUT-Roundtrip inkl.
„PUT ohne Feld leert die Tags"), ruff clean. Viewer 244 vitest grün (neu:
Payload-Bau trägt `compatible_robots` durch, entdoppelt, leer bleibt leer — Create
und Update), tsc clean.

## 2026-07-07 — Workstation-Entity: Aufstell-Umgebung als Core+API-Stammdaten (Issue #72, PRD #69)

**Frage:** Wie modelliert man die Aufstell-Umgebung des Roboters — die stationäre
Zelle *und* die mobile, zur Wand fahrende Workstation — samt Höhenmodell
(feste Podeste vs. stufenlos verstellbar), ohne zwei parallele Entitäten zu
pflegen? Und wie erzwingt man die Höhen-Konsistenz, die das rohe JSON-Schema
nicht ausdrücken kann?

**Alternativen:** (a) zwei getrennte Entitäten „Zelle" und „Workstation" — doppelte
Schemas/APIs/UI für 90 % identische Felder; (b) eine Entity mit `type`-Feld, aber
das Höhenmodell per `oneOf` im Schema erzwungen (verstellbar ⇒ nur `height_range_mm`,
fest ⇒ nur `base_heights_mm`) — `oneOf` mit `additionalProperties: false` und
`$ref`-Frames wird schnell unleserlich und liefert kryptische Validierungsfehler;
(c) **eine** Entity mit `mobility`-Feld (`stationary|mobile`), das Schema erlaubt
beide Höhenfelder, und die **Branch-Regel** (welches Feld je nach
`height_adjustable` nötig/gültig ist) lebt als Domänen-Prüfung in
`load`/`build` — wie beim Endeffektor (`domain/tool`).

**Entscheidung:** (c). Neues tiefes Modul `domain/workstation` mit frozener
`WorkstationDef`, `safe_workstation_name`, `build_workstation_artifact` und einer
privaten `_validate_height_model` (von `load` und `build` geteilt): verstellbar ⇒
`height_range_mm` mit `min < max`; nicht-verstellbar ⇒ `base_heights_mm` streng
aufsteigend geordnet und **enthält 0** (Bodenhöhe). Verstoß → klarer `ValueError`
(API → 422). `workstation.schema.json` (`additionalProperties: false`,
`safety_min_distance_mm` Default 50, optionales `compatible_robots` wie #71) in
`VALIDATABLE_KINDS` registriert. Volle CRUD-API `GET/POST/PUT/DELETE /workstations`
als dünne Aktions-Wrapper (ADR-014) über neue Aktionen
`create/update/delete/list_workstation`.

**Atomares Schreiben (bewusst *nicht* das Tool-Muster):** `create_tool_from_upload`
schreibt `.json` per direktem `write_text` (nicht atomar) — akzeptabel dort, weil
ein Mesh ohnehin daneben liegt. Für die Workstation folgt der Schreibpfad
(`write_workstation_artifact`) stattdessen exakt `write_project` (ADR-018): erst in
eine Temp-Datei im selben Verzeichnis, dann `os.replace` — nie ein halb
geschriebenes File. Die Read-Modify-Write-Sektionen (create/update/delete) laufen
unter einem per-Pfad `workstation_lock` (RLock-Registry, Muster wie `project_lock`),
damit parallele API-Requests im FastAPI-Threadpool keinen Lost Update erzeugen.

**Begründung:** Eine Entity + `mobility` statt zweier Typen hält Schema/API/UI
einfach (die UI in #75 verzweigt nur an einem Feld). Branch-Regel in der Domäne
statt im Schema gibt lesbare Fehlermeldungen und hält das Schema flach. Atomar wie
`write_project` ist der ausdrücklich geforderte Standard (ADR-018) — die
Stammdaten-Datei ist die einzige Quelle, ein Torso-File wäre teurer als beim
mesh-begleiteten Tool. Kein neuer ADR nötig: ADR-018 deckt das atomare Schreiben,
ADR-016 die projektunabhängigen Stammdaten; das Modul spiegelt `domain/tool`.

**Verifikation:** Core 466 pytest grün (neu `test_workstation.py`, 21 Tests:
Schema-Registrierung/Validierung/`additionalProperties`, Höhen-Branch-Regel beide
Zweige, Roundtrip stationär+mobil+verstellbar, CRUD-Aktionen, CRUD-API inkl.
atomarer Schreibprüfung „keine .tmp-Reste" und 404 bei Unbekannt), ruff clean.
Viewer unberührt.

---

## 2026-07-07 — Roboter: robot.schema.json + Validierung + sichtbare Defektmeldung (Issue #73, PRD #69)

**Frage:** Roboterdefinitionen (`robots/*.json`) wurden — anders als Endeffektoren
und (seit #72) Workstations — nicht schema-validiert, und `GET /robots`
übersprang kaputte Definitionen **still** (`except Exception: continue`). Ein
Tippfehler in einer Roboterdatei ließ den Roboter kommentarlos aus dem Katalog
verschwinden. Diese Robustheits-Scheibe zieht das Schema-Muster nach — **read-only**,
rein additiv, keine Schreibpfade (Roboter bleiben im #69-Scope unangetastet).

**Alternativen:** (a) `additionalProperties: false` strikt — bricht aber am
M1013, der Kommentarfelder `_note`/`_source`/`_units`/`_limits_source` trägt;
(b) diese Kommentarfelder einzeln als optionale Properties modellieren — brüchig,
jeder neue Kommentar bräuchte eine Schema-Änderung; (c) `additionalProperties: false`
**plus** `patternProperties {"^_": {}}` je Objektebene — erlaubt beliebige
Unterstrich-Kommentare, verbietet alles andere. Für die Defektmeldung: (x) nur
loggen (unsichtbar für den Viewer), (y) nur ein Antwortfeld (nicht im Serverlog),
(z) **beides** — Log-Warnung *und* `errors`-Feld.

**Entscheidung:** (c) + (z). `schemas/robot.schema.json` (`const schema_version 0.2`,
`workspace` required mit `max_print_*_mm`, optionale `kinematics` mit
`solver`/`a_mm`/`d_mm`/`alpha_rad`/`joint_limits_rad` required + optionalen
vel/acc-Limits), `additionalProperties: false` + `patternProperties ^_` auf jeder
Ebene, registriert in `VALIDATABLE_KINDS`. `RobotDef.load` ruft `validate(raw,
"robot")` (lokaler Import wie `WorkstationDef.load`, kein Zirkel) — der M1013 lädt
byte-gleich unverändert. `GET /robots` meldet einen Defekt jetzt **sichtbar**:
`_LOG.warning(...)` **und** neues Antwortfeld `errors: list[{name, error}]`
(Default `[]`); gültige Roboter kommen weiter (report-and-continue, kein
Endpoint-Crash an einer kaputten Datei).

**Begründung:** Das Schema spiegelt exakt das Endeffektor-/Workstation-Muster
(P2/ADR-004: JSON-Schema ist die Wahrheit). `patternProperties ^_` hält die
vorhandenen Provenienz-Kommentare gültig, ohne das Schema aufzuweichen (jedes
*nicht*-Unterstrich-Fremdfeld fällt weiterhin durch). Log **und** `errors`-Feld,
weil beide Beobachter existieren: der Betreiber sieht die Warnung im Serverlog,
der Viewer/Client kann den Defekt aus der Antwort anzeigen. Kein neuer ADR nötig
(folgt dem bestehenden Schema-/Validierungspfad).

**Verifikation:** Core 474 pytest grün (neu `test_robot.py`, 8 Tests:
Schema-Registrierung, Referenz-Robots validieren+laden, M1013 unverändert,
Unterstrich-Kommentare erlaubt, `additionalProperties` abgelehnt, `workspace`
required, `load` wirft bei Defekt, `GET /robots` meldet Defekt in `errors` **und**
Log), ruff clean. Viewer unberührt.

## 2026-07-07 — Kompatibilitätsfilter: inkompatibles Zubehör ausgrauen + warnen (#74, PRD #69)

**Frage:** Die `compatible_robots`-Tags (#71) existierten, hatten aber noch keine
Wirkung. #74 verdrahtet sie in die Endeffektor-Auswahl (Reiter Roboter): passt
das gewählte Zubehör zum aktiven Roboter? Wie soll „passt nicht" sich anfühlen —
und wo lebt die Entscheidung, damit Core und Viewer nicht auseinanderdriften?

**Alternativen:** (a) Sichtbarkeit — (a1) inkompatibles Zubehör `disabled`
(unwählbar) vs. (a2) nur **ausgrauen**, wählbar bleibend; (b) bei Roboterwechsel
eines fremd gewordenen Endeffektors — (b1) Auto-Reset der Wahl vs. (b2) nur
**warnen**, Wahl behalten; (c) Ort der Regel — (c1) nur im Viewer (Gefahr:
divergiert vom Kern) vs. (c2) eine reine Funktion **doppelt** (Core
`domain/compat.py` + Viewer `ui/compat.ts`) mit geteilten Golden-Fällen; (d)
ungetaggtes Zubehör — (d1) als inkompatibel behandeln vs. (d2) als **unbekannt =
kompatibel** (Migrationsschutz).

**Entscheidung:** (a2) + (b2) + (c2) + (d2). `is_compatible(compatible_robots,
active_robot)`: leere/fehlende Tags → `True`, aktiver Roboter `None` → `True`
(unbekannte Auswahl), sonst Mitgliedschaftstest. Wortgleich in `compat.py` und
`compat.ts`. Ausgrauen via CSS-Klasse `option-incompatible` (kein `disabled` —
bleibt wählbar). Warnung analog zur Payload-Warnung (gleiches inline-Element
`#tool-compat-warning`), feuert nur, wenn der **schon gewählte** Endeffektor durch
den Roboterwechsel fremd wird; kein Auto-Reset, keine Persistenz. Aktiver Roboter
über den bestehenden Roboter→ToolPanel-Leseweg (`setActiveRobot` parallel zu
`setRobotPayload`). Ausgrau-/Warn-Entscheidung als reine Funktionen
(`incompatibleToolNames`, `compatibilityWarning`), DOM-Wiring getrennt
(Split-Muster wie `simulation-state`/`cutplan-state`).

**Begründung:** „Befund, kein Gate" (**ADR-013**) — die Eignung ist ein Hinweis,
kein Verbot; genauso hier: der Nutzer darf bewusst ein fremdes Werkzeug wählen
(Sonderfall, Provisorium). Ungetaggt = unbekannt (nicht inkompatibel) hält
Altbestand ohne Tags für jeden Roboter nutzbar (Migrationsschutz). Die reine
Funktion doppelt statt geteilt, weil Core (Python) und Viewer (TS) getrennte
Laufzeiten sind; Golden-Fälle auf beiden Seiten sichern die Verhaltensgleichheit
statt einer geteilten Implementierung. Kein neuer ADR nötig (ADR-013 regiert
bereits „Befund, kein Gate").

**Verifikation:** Core 484 pytest grün (neu `test_compat.py`, 10 Golden-Fälle:
passend→true, fremd→false, leer/None→true, kein Roboter→true, Liste wie Tupel),
ruff clean. Viewer 256 vitest grün (neu `compat.test.ts`, 12 Tests: `isCompatible`
Golden, `incompatibleToolNames` Ausgrau-Menge, `compatibilityWarning` Warn-Logik),
tsc clean.

---

## 2026-07-07 — Bibliothek: Rubriken-Umschaltung + Workstation-Galerie & -Editor (UI, Issue #75, PRD #69)

**Frage:** Wie bekommt der Reiter Bibliothek die dritte Entity (Workstation, Core
seit #72) in die Oberfläche — und wie ordnet sich die bestehende Endeffektor-
Galerie ein, ohne den tote-Reiter-Bug (#56) wieder auszulösen?

**Alternativen:** (a) Sicht-Umschaltung — (a1) je Rubrik ein eigener Reiter in der
Top-Tab-Leiste vs. (a2) eine **Rubriken-Leiste innerhalb** des Bibliothek-Panels;
(b) Toggle-Mechanik — (b1) `style.display`/CSS-Klasse vs. (b2) ausschließlich das
`.hidden`-Attribut; (c) Workstation-Karte — (c1) 3D-Mini-Preview/Thumbnail wie beim
Endeffektor vs. (c2) schlichte **SVG-Grafik** aus den strukturierten Höhen; (d)
Editor — (d1) den Konfigurator-Rahmen (mit Viewport) wiederverwenden vs. (d2)
**reines Formular** ohne Gizmo/WebGL; (e) Code-Ort der Fachlogik — (e1) alles in
der DOM-Klasse vs. (e2) Pure-Logik-Modul + DOM-Smoke (Split wie
`configurator-payload`/`tool-library`).

**Entscheidung:** (a2) + (b2) + (c2) + (d2) + (e2). Drei Rubrik-Sichten
(`#lib-rubric-roboter|endeffektor|workstation`) im selben Panel, umgeschaltet über
`LibraryRubrics` **nur via `.hidden`**. Roboter-Rubrik ist ein **Platzhalter**
(echte Read-only-Galerie folgt in #76). Workstation-Karte: `podestStackSvg`
(Rechteckstapel bzw. Rampe bei verstellbar) + Typ-Badge (stationär/mobil) +
`summarizeWorkstation` (N Podeste + Bereich bzw. `min–max`, Sicherheitsabstand).
Editor = Formular; der **„höhenverstellbar"-Toggle** blendet Podestliste ↔ min/max
wieder nur über `.hidden` um. Bearbeiten befüllt exakt vor + sperrt den Namen
(`readOnly`, kein Rename, #56-Muster). Pure-Logik in `ui/workstation-payload.ts`
(Formular→Request mit Client-Vorprüfung der Branch-Regel, Workstation→Formular,
Karten-Zusammenfassung) und `ui/library-rubrics.ts`; `ui/workstation-library.ts`
hält nur DOM + Callbacks an die `/workstations`-API. Roboter-Tags aus `GET /robots`
(#71-Muster, `setRobots`/Auswahl-Erhalt). Kein Core-Change nötig (#72 vollständig).

**Begründung:** Das `.hidden`-only-Prinzip ist die harte Lehre aus #56 (globales
`[hidden]{display:none!important}` überstimmt `display:flex` → tote Sicht trotz
grüner Checks); deshalb auch der HTML-Struktur-Vertrag in `shell-structure.test`
(alle drei Rubrik-Sichten vorhanden). SVG statt Thumbnail, weil die Workstation
**reine strukturierte Daten** ist (kein Mesh) — kein three.js, kein Cache, testbar
im jsdom. Reines Formular statt Konfigurator-Rahmen, weil es weder Upload noch
Face-Align/Gizmo gibt. Split Pure/DOM hält die Branch-Regel und die Zusammenfassung
deterministisch testbar (ADR-007: der Viewer rechnet nichts Fachliches — der Core
validiert die Höhen-Branch-Regel erneut, 422 wird freundlich im Editor gezeigt).
Kein neuer ADR (ADR-007/#56-Muster regieren bereits).

**Verifikation:** Viewer 293 vitest grün (+32 neu: `workstation-payload.test.ts`
17, `workstation-library.test.ts` 12, `library-rubrics.test.ts` 3, plus
`shell-structure` um die drei Rubrik-Sichten erweitert), `tsc --noEmit` clean,
`vite build` ok. Core unberührt (kein Change) → Suite unverändert grün.

## 2026-07-07 — Bibliothek: Roboter-Galerie (read-only) + statisches PNG-Thumbnail (Issue #76, PRD #69)

**Frage:** Wie füllt die Rubrik Roboter (bisher Platzhalter aus #75) den
Roboterbestand — und woher kommt das Thumbnail, wenn kein Live-FK-Render laufen
soll?

**Entscheidung:** Schreibgeschützte Galerie aus `GET /robots`, Karten mit
Name/Reichweite/Traglast (+ Druckraum-Hüllwerte, `(vorläufig)`-Marker) und einem
**statischen, eingecheckten PNG** je Roboter. **Kein** Anlegen/Bearbeiten/Löschen,
kein Formular, dafür ein `read-only`-Badge. Split Pure/DOM wie bei #75:
`ui/robot-library-payload.ts` (`summarizeRobot`, `robotSlug`, `robotThumbnailPath`)
rein und jsdom-frei, `ui/robot-library.ts` hält nur DOM + einen `loadRobots`-
Callback. Thumbnail-Pfad `./robots/<slug>/thumbnail.png` neben den GLBs (#40/#41);
Slug streicht den Hersteller-Präfix (`doosan_m1013`→`m1013`). Fehlt das PNG,
ersetzt `img.onerror` es durch einen Platzhalter (kein Absturz). Das `errors`-Feld
aus #73 wird in der read-only-Galerie ignoriert. Kein Core-Change.

**PNG-Erzeugung (wichtig — ersetzbar):** Alternativen waren (a) Headless-WebGL-
Snapshot des Arms in Home-Pose über den vorhandenen CDP-Smoke-Harness
(`ui_smoke.mjs`) und (b) ein deterministisch generiertes PNG in Platzhalter-
Qualität. Gewählt: **(b)**. Der CDP-Harness braucht Core-API (8765) + Vite-Dev-
Server (5173) + ein Projekt + headless Edge gleichzeitig laufend — offline nicht
zuverlässig/deterministisch. Das abhängigkeitsfreie Skript
`viewer/scripts/gen_robot_thumbnail.mjs` (nur `node:zlib`) malt eine stilisierte
Arm-Silhouette (Sockel + 3 Segmente + orangefarbene TCP-Düse, dunkler Panel-
Hintergrund) in einen RGBA-Puffer und kodiert daraus ein gültiges PNG
(480×360, ~2,4 kB, Farbtyp 6, ein IDAT). Ausgabe:
`viewer/public/robots/m1013/thumbnail.png` (eingecheckt, per `vite build` nach
`dist/robots/m1013/` kopiert). **Ein echter FK-Render kann dieses PNG später
1:1 ersetzen** — die Karte lädt jede Datei unter dem konventionellen Pfad.

**Begründung:** Read-only ist die Scope-Klärung aus #69 (Kinematik hart
verdrahtet: `_START`/`_SIGNS`, vendored Meshes, Viewer-DH — Vendoring-Arbeit,
kein Formular). Statisches PNG statt Live-FK, weil ein Render je Karte einen
laufenden three.js-Kontext + Mesh-Load in der Galerie erzwänge; das Standbild
genügt der Übersicht und bleibt jsdom-testbar. Der `onerror`-Platzhalter hält die
Galerie robust für künftige Roboter ohne eingechecktes Bild. Kein neuer ADR
(ADR-007/#56-`.hidden`-Muster regieren bereits; hier ohnehin keine Sicht-Toggles
innerhalb der Rubrik).

**Verifikation:** Viewer 302 vitest grün (+9 neu in `robot-library.test.ts`:
Payload-Formatierung inkl. unbekannter Traglast, Slug/PNG-Pfad, Karten-DOM-Smoke,
keine Aktions-Buttons, Platzhalter bei img-error, Leerzustand, API-Lade-Gate),
`tsc --noEmit` clean, `vite build` ok (PNG in `dist/` vorhanden, 2357 B, Signatur
`89504e47…` verifiziert). Core unberührt.

## 2026-07-07 — Workstation-Wahl am Druckjob + Kompatibilitätsfilter, ohne Veraltung (Issue #77, PRD #69 — Seam zu #70)

**Frage:** Wie wählt ein Druckjob eine Workstation (analog Roboter/Endeffektor),
und was passiert mit nachgelagerten Ständen, wenn die Workstation wechselt?

**Entscheidung:** `print_job.workstation` als **schlichter, optionaler String**
(Workstation-Name), additiv in `project.schema.json` (`additionalProperties: false`
bleibt; Altprojekte ohne Feld laden byte-gleich). Persistiert über die einzige
Schreibstelle `fgc.project` (ADR-016): neue Aktion `set_workstation_for_job`
(spiegelt `set_tool_for_job`) + dünne Route `PUT /projects/{slug}/workstation`
(spiegelt `PUT …/tool`; 404 bei unbekannter Workstation, 422 bei fehlendem Job).
Die Auswahl-UI lebt im Reiter **Roboter** unter dem Endeffektor-Panel
(`WorkstationPanel`, DOM-ids **`wsc-*`** statt `ws-*`, um Kollision mit der
Workstation-**Bibliothek** zu vermeiden). Sie **wiederverwendet** den #74-Filter:
Ausgrauen/Warnung über `isCompatible` (dieselbe reine Funktion wie beim
Endeffektor) in einem reinen Modul `ui/workstation-state.ts`
(`incompatibleWorkstationNames`/`workstationCompatibilityWarning`), DOM getrennt
im Panel. Aktiver Roboter über denselben `setActiveRobot`-Leseweg wie ToolPanel.
Kein Payload-Check (die Workstation trägt kein Flanschgewicht) — stattdessen ein
Kompat-Befund `compatible` in der Antwort.

**Kern der Scheibe — bewusst KEINE Veraltung (der Seam zu #70):** anders als
Roboter- und Endeffektorwechsel (die `bump_input` rufen und Druckplan/Simulation/
Export nach ADR-017 veralten) bumpt `set_workstation_for_job` **keine** Eingabe-
Revision. `workstation` ist **absichtlich nicht** in `INPUT_KEYS`
(`fgc.project.revisions`) und nicht in `OUTPUT_DEPS`. Begründung: die Workstation-
Werte (Podesthöhen/Mobilität) werden erst vom **Druckplan-Automatismus (#70)**
konsumiert — in dieser Scheibe entsteht **kein** aus der Workstation abgeleiteter
Output, also gibt es nichts zu veralten. Erst #70 (PRD B) fügt die Ableitung hinzu
und entscheidet dort, ob/wie ein Workstation-Wechsel dann veraltet. Diese Auslassung
ist an drei Stellen dokumentiert (Schema-Beschreibung von `workstation`, Docstring
von `set_workstation_for_job`/`SetWorkstationResult`, Kommentar in `main.ts` beim
ausgelassenen `refreshRevisions`) und durch Tests abgesichert.

**Alternativen verworfen:** (a) Workstation als weiterer `INPUT_KEY` mit sofortiger
Veraltung — verworfen, weil es einen Output vortäuscht, den es noch nicht gibt
(false staleness, verwirrt den Nutzer). (b) Workstation-Existenz beim Setzen
**nicht** prüfen (reiner String) — verworfen zugunsten von `WorkstationDef.load`
(klares 404 bei Tippfehler, mirror zu `set_tool`), das Feld bleibt schema-seitig
trotzdem ein freier String. (c) Auto-Reset einer inkompatibel gewordenen Wahl —
verworfen (ADR-013 „Befund, kein Gate": nur ausgrauen + warnen).

**Verifikation:** Core 497 pytest grün (u. a. `test_workstation_choice.py`:
Persistenz, Schema-Roundtrip inkl. Altprojekt ohne Feld, Kompat-Befund, 404,
**und die No-Staleness-Assertion** — nach `set_workstation` bleiben Druckplan/
Simulation/Export `current`, `revisions.inputs` unverändert, kein Key `workstation`;
plus Kontrasttest, dass ein Endeffektorwechsel weiterhin veraltet, und dass
`bump_input("workstation")` abgewiesen wird), ruff clean. Viewer 316 vitest grün
(+14: `workstation-state.test.ts` Ausgrauen/Warnen, `workstation.test.ts` jsdom-
Panel Dropdown/Ausgrauen-ohne-disabled/Warnung-ohne-Auto-Reset/Restore-nach-
Neuladen/Speichern), `tsc --noEmit` + `vite build` clean. Schließt die Kind-Issue-
Kette von PRD #69 (#71–#77) ab. Kein neuer ADR (ADR-016 Schreibstelle, ADR-013
Befund/kein-Gate, ADR-017 Revisionen regieren bereits; die *Auslassung* aus #17 ist
die eigentliche Entscheidung).

## 2026-07-07 — Workstation-Mesh + Roboter-Platzierung + Bohrbild-Erkennung (Issue #78, ADR-021)

**Frage:** Der Nutzer will bei stationären Workstations (a) einen Mesh-Upload,
(b) den Roboter „wie beim Endeffektor" per Flächen-Mittelpunkt + Drehung
positionieren, (c) die Arbeitsfläche wählen, (d) die 4 Basis-Bohrlöcher auf dem
Mesh erkennen und den Roboter darauf ausrichten (Lochradius darf leicht
abweichen). Außerdem missfällt das zentrierte, nebeneinander liegende
Rubriken-Menü der Bibliothek.

**Entscheidung (Details + Begründung: ADR-021):** Die in #72/#75 bewusst
mesh-freie Workstation wird **additiv und rückwärtskompatibel** umgekehrt.

- **Menü (sofort, reines CSS):** die Rubriken-Leiste (Roboter/Endeffektor/
  Workstation) wird von einer zentrierten, gestrandeten Spalte zur **linken
  Seitenleiste** (`.lib-rubrics` → `flex-direction:column`, fester 168px-Streifen
  mit `border-right`, `.lib-rubric` linksbündig mit `border-left`-Akzent;
  `.lib-rubric-view` füllt die Restbreite). Ursache des alten Bildes war, dass das
  Bibliothek-Panel eine Flex-**Zeile** ist und die als Top-Leiste gebaute Nav nie
  `flex-direction:column` bekam. Kein JS/HTML, nur `viewer/src/style.css`.
- **Optionale Felder** `mesh`, `robot_base_frame`, `work_surface_frame` auf
  `workstation.schema.json`/`WorkstationDef`/API (Frames `{pos_mm, quat[w,x,y,z]}`,
  ADR-006). Fehlen sie → reine Zahlenfelder wie zuvor (`additionalProperties:false`
  bleibt; Altbestand lädt byte-gleich).
- **Mesh-Upload spiegelt den Endeffektor** (ADR-014): base64-in-JSON, Validierung
  über die geteilten `domain/tool`-Helfer (`mesh_suffix`/`validate_mesh_bytes`),
  Ablage `<name><suffix>` neben `<name>.json`; Update ohne Re-Upload erhält das
  Mesh, Delete entfernt das Geschwister, Formatwechsel entfernt die Waise —
  identisch zu `update_tool_from_upload`.
- **Roboter-auf-Fläche:** neue **vorzeichen-gedrehte** reine Funktion
  `mountBaseToSurface` in `ui/face-align.ts` — Basis-+z → **Flächennormale**
  (statt Werkzeug-Normale → −Flansch-z), Ursprung im Flächen-Mittelpunkt, Drehung
  um die Normale (`q = spin ∘ align`). Neuer WebGL-Editor `ui/workstation-scene.ts`
  (die bisher reine Formular-Ansicht bekommt ein Sichtfeld) mit derselben
  Raycast-/Hover-/`PlanarRegionIndex`-Pipeline wie der Konfigurator; der Kapsel-Arm
  (`ArmView`) wird am `robot_base_frame` verankert. Optional in die
  `WorkstationLibrary` injiziert → jsdom-Tests bleiben WebGL-frei, der Request ohne
  Szene byte-gleich zu #75.
- **Roboter-Bohrbild** als maschinenlesbares optionales `base_mount` auf
  `robot.schema.json` (Roboter bleiben **read-only** — nur Daten). M1013
  **provisorisch** aus dem Doosan-Installationshandbuch §3.3.1 (recherchiert +
  gegen das vendored Basis-Mesh abgeglichen): **4 × Ø9 mm** für M8 auf einem
  **150 × 150 mm-Quadrat** (Mitten ±75, BCD Ø212,1), Montageebene z=0. (Das
  base.glb modelliert die Löcher **nicht** — daher werden sie auf dem
  Workstation-Mesh erkannt.)
- **Bohrbild-Erkennung im Core** (`fgc.geometry.holes`, nicht Viewer — ADR-007):
  oberste horizontale Fläche schneiden (reuses `section.py`:
  `polygons_full → interiors` = Löcher), Kreise fitten, ein zum `base_mount`
  passendes N-Loch-Bild per 2D-Starrkörper-Abgleich mit **Radius-Toleranz**
  suchen (der reale Lochradius darf abweichen), `robot_base_frame` vorschlagen
  (Zentroid + Normale + Drehung, bit-gleich zur Viewer-Konvention). Route
  `POST /workstations/{name}/detect-base-holes`. **Befund, kein Gate** (ADR-013):
  Treffer → Auto-Snap, kein Treffer → nur Warnung, nie Sperre. Auto-Snap liest das
  **gespeicherte** Mesh, ist also erst nach dem Speichern aktiv; manuelles
  Flächen-Picken geht jederzeit.

**Kopplung:** Der #77-Seam bleibt — eine Workstation-Änderung veraltet weiter
**keine** Outputs; `robot_base_frame`/`work_surface_frame` sind Stammdaten, die
erst der Druckplan-Automatismus (#70) konsumiert, hier **nicht** in Trajektorien
verdrahtet.

**Alternativen verworfen:** Bohrbild als reine Zahlen statt Erkennung (Nutzer will
Erkennung auf dem realen Mesh); hartes Kompatibilitäts-Gate (ADR-013); Mesh nur
für `stationary` (optional-für-alle ist kleinere Schema-Fläche); Detektion im
Viewer (Core hat trimesh/shapely + `section.py`-Muster); Frei-Drag-Gizmo (Frames
werden berechnet, nicht zurückgelesen — #28/#52).

**Verifikation:** Core 523 pytest grün (u. a. `test_base_mount.py` 18 neu —
Erkennung auf einer deterministischen Loch-Platte, Radius-Toleranz passt/passt
nicht, No-Match ohne Exception, Frame reproduziert die Löcher; `test_workstation.py`
+8 Mesh-Roundtrip/-Upload/-Delete/API-base64), ruff clean. Viewer 324 vitest grün
(+8: `mountBaseToSurface`-Golden inkl. Vorzeichen-Kontrast zu `mountFaceToFlange`,
`buildWorkstationRequest`-Platzierungs-Passthrough), `tsc --noEmit` + `vite build`
clean. Menü-Fix per Headless-Render geprüft (linke Rail, aktive Rubrik mit
Akzent-Rand); der laufende Workstation-Editor per CDP live geprüft (alle
Platzierungs-DOM-IDs vorhanden, `#ws-viewport`-Canvas 852×862, keine
Lade-Exceptions). **Offen (Runtime):** manueller Durchklick der vollen Kette
(Mesh hochladen → Fläche klicken → Arbeitsfläche → Auto-Snap) am Gerät; die
M1013-Maße sind provisorisch bis zur Bestätigung.

## 2026-07-07 — Druckplan S1: placement/suggest — zentral + Podesthöhe + optimierter Abstand (Issue #80, PRD #70)

**Frage:** Wie soll der Optimalvorschlag (`fgc.placement.suggest`) die Roboterbasis
wählen, jetzt wo die Workstation (Podesthöhen, Sicherheits-Mindestabstand, #72/#77)
existiert? Bisher: 2D-Raster über *seitlich × Höhe bei fixem 700-mm-Abstand* — der
Abstand war willkürlich fix, die Höhen frei erfunden (0…3000 in 500er-Schritten),
seitlich unnötig gerastert.

**Entscheidung:** Die Kandidatenmenge an die reale Workstation binden — drei Achsen
neu belegt: (1) **seitlich = fest die Abschnittsmitte** (`lateral_mm = 0`), der
Roboter steht zentral, keine seitliche Rasterung mehr; (2) **Höhe = aus dem realen
Podesthöhen-Satz** — `base_heights_mm` (nicht höhenverstellbar, inkl. 0) bzw. ein
500-mm-Raster über `height_range_mm` (höhenverstellbar), beste Höhe gewinnt;
(3) **Abstand = optimierte Achse** — Raster ab `safety_min_distance_mm` (Default 50)
bis `robot.reach_mm` in 150-mm-Schritten (`DISTANCE_STEP_MM`). Auswahlkriterium
bleibt die bestehende Sortierung `(reachable_fraction, mean_margin)` absteigend →
das ist genau „beste mittlere Marge bei vollem erreichbaren Anteil"; damit werden
Singularitätsnähen aktiv wegoptimiert. `_raster(lo, hi, step)` startet strikt bei
`lo` und enthält immer den Endpunkt → der gewählte Abstand liegt **nie** unter dem
Sicherheits-Mindestabstand.

**`evaluate` unangetastet** (nur Kandidatenmenge + Auswahl ändern sich, wie im Issue
gefordert). **Fallback:** ohne Workstation (`workstation=None`, Altprojekt) läuft
weiter das bisherige 2D-Raster (`_fallback_grid`, seitlich × Höhe bei fixem
`standoff_mm`) — bestehende placement-Routen/-UI unverändert. Die Aktion
`suggest_placement` lädt die Workstation aus dem Druckjob-Feld `workstation` (#77)
und reicht sie durch; fehlt sie, fällt sie sauber auf den Fallback zurück.

**Alternativen verworfen:** Abstand weiter fix (verschenkt die Marge-Optimierung,
die gerade Singularitätswarnungen wegräumt); Höhen weiter frei rastern statt aus
dem Podestsatz (die Workstation *kennt* ihre realen Höhen — frei erfundene sind
nicht baubar); auf `height_adjustable` **nicht** verzweigen (die Domäne garantiert
je nach Flag genau eines der Höhenfelder, #72-Branch-Regel — also darauf verzweigen,
nicht auf `mobility`); Determinismus über Sortier-Zufall (bewusst feste Raster +
stabile Sortierung, ADR-004-Geist).

**Verifikation:** Core 528 pytest grün (+6 in `test_placement.py`: Golden
seitlich = Abschnittsmitte; beste Höhe aus Podestsatz — Boden-only 0 vs. Podeststapel
> 0; Abstand marge-optimal bei voller Erreichbarkeit und ≥ Sicherheitsabstand;
Determinismus Wand/Roboter/Workstation; `height_range`-Rasterung mobil), ruff clean.
Kein Viewer-Change (Core-only; die placement-API/UI zeigt die neuen Vorschläge über
die bestehende `vorschlag-*`-Mechanik sofort). **Offen (Runtime):** manueller
Durchklick am Gerät mit einer real gewählten Workstation.

## 2026-07-07 — Druckplan S2: Aufstell-Toggle „Boden ↔ erhöht" end-to-end (Issue #81, PRD B/#70)

**Frage:** Wie ersetzt der Aufstell-Toggle die manuelle Aufstell-Liste, und wie
konsumiert die Zerlegung ihn — sodass „Boden" mehr Höhenbänder ergibt als „erhöht"?

**Entscheidung:** Neues optionales Job-Feld `stand_mode` (`floor`|`elevated`),
**additiv** in `project.schema.json` (Altprojekt ohne Feld lädt byte-gleich, gilt
`floor`). Der Toggle begrenzt den Podesthöhen-Satz, den die Abschnittssuche nutzen
darf: `fgc.placement.suggest(..., stand_mode=…)` klemmt bei `floor` die Höhen-
Kandidaten auf `[0]`, bei `elevated` auf den realen Satz (`base_heights_mm` bzw.
`height_range_mm`, #80). `fgc.decompose.propose`/`from_cuts` reichen `workstation`
+ `stand_mode` durch bis in `_reachable_fraction`.

**Kern-Kniff (sonst wirkungslos):** `_grid_counts` seedete die Höhenteilung aus dem
roboter-festen `max_print_height_mm` und verfeinerte nur nach oben — beide Toggle-
Zustände bekamen denselben Startwert, der Unterschied verschwand. Deshalb startet die
Suche **mit Workstation** bewusst bei `(1, 1)` und verfeinert rein toggle-abhängig:
`floor` (Basis am Boden) macht überhohe Zellen schlechter erreichbar → mehr
Höhenteilungen als `elevated` (Basis darf aufs Podest). **Ohne Workstation** bleibt
der bewährte Arbeitsraum-Seed (Golden-Tests unverändert). `from_cuts` bleibt erhalten:
manuelle Schnitte bestimmen die Abschnitte, der Toggle nur die Platzierungssuche.

**API + UI:** dünner Setter `set_stand_mode_for_job` (einzige Schreibstelle
`fgc.project`, ADR-016) + Route `PUT /projects/{slug}/stand-mode` — mirror
`set_workstation_for_job`/`PUT .../workstation`, **bewusst ohne Veraltung** (kein
`bump_input`, Seam-Muster wie #77): die Neubewertung ist der nachfolgende
`propose_decomposition` (bumpt dort `cutplan`). Im Viewer ersetzt ein Radio-Toggle
(`aufstell-floor`/`aufstell-elevated`) die manuelle Stellplatz-Liste (add/eval/
`placement-options` entfernt); Umschalten persistiert über `setStandMode` und stößt
`proposeDecomposition` an → frische Schnitte/Ampeln (ADR-007, UI rechnet nie selbst).
Reine Normalisierung in `ui/aufstell-state.ts` (DOM-frei, vitest — Altprojekt→`floor`).
`Optimalvorschlag` + Scores + Schnittplan-Editing bleiben; Section-Overrides degradieren
sauber auf „automatisch gesucht" (ohne manuelle Optionen).

**Alternativen verworfen:** Toggle als Revisions-Input, der alles veraltet (unnötig —
die Neubewertung erledigt der Zerlegungslauf, konsistent zum #77-Seam); manuelle Liste
behalten und Toggle daneben (PRD/Issue sagen „ersetzt"); Höhenteilung weiter aus
`max_print_height` (verschluckt den Toggle-Effekt, s. o.).

**Verifikation:** Core 537 pytest grün (+9 in `test_decompose.py`: floor>elevated
Höhenbänder, Toggle-Determinismus, `from_cuts` mit Workstation/Toggle, Setter-Persistenz
ohne Veraltung, unbekannter Modus, end-to-end persistierter Toggle steuert Zerlegung,
Route persistiert+restauriert+422+404), ruff clean. Viewer 329 vitest grün (+5
`aufstell-state.test.ts`), tsc clean. **Offen (Runtime):** manueller Durchklick der
Toggle→Neubewertung-Kette am Gerät mit real gewählter Workstation.

---

## 2026-07-07 — Druckplan S3: Pro-Abschnitts-Overrides + Auflösung (#82)

**Frage:** Wie bekommt jeder Abschnitt eine eigene Gradierung, ohne die globale
Prozessparameter-Quelle (#59/#60/#61) zu duplizieren oder die Py↔TS-Grenze zu
brechen?

**Entscheidung:** Ein additiver Block `process_params.sections` (`section_id →
{slice, orientation}`, sparse) trägt je Abschnitt genau dieselben Felder wie global.
Eine **reine, kartenfreie** Auflösefunktion `resolve_section_params(global, override)`
mischt feldweise (gesetztes Abschnittsfeld gewinnt, sonst erbt global, sonst
weg → Karte/Default) — bit-genau das Muster von `job_slice_overrides`. Ergebnis ist
wieder sparse, damit es sich als normaler `slice`/`orientation`-Block weiterlesen
lässt. Der TS-Zwilling `resolveSectionParams` spiegelt sie; die Parität ist über
**geteilte Golden-Fälle** (`viewer/src/ui/section-params.golden.json`, erzeugt vom
Core-Skript `gen_section_params_golden.py`) bewiesen — dasselbe Konventionsmuster wie
`gen_fk_golden.py`.

**Alternativen verworfen:** (a) Auflösung liefert **fertige** effektive `SliceParams`
inkl. Karten-Fallback — verworfen, weil der Viewer die Prozessfenster-Karte nicht
kennt und die Parität dann kartenabhängig würde; die reine Dict-Merge bleibt beidseitig
identisch. (b) io/Winkel je Abschnitt in einer **abweichenden** Form speichern —
verworfen zugunsten „Sektions-Block = global-Block", damit dieselben Reader/Requests
(`sliceFormFromBlock`/`orientationFormFromBlock`) wiederverwendbar sind. (c) `motion`
je Abschnitt — bewusst **nicht** (bleibt global; Issue nennt nur Slice+Orientierung).
(d) `null` im Override kappt einen globalen Wert — verworfen: `None`/`null`
übersteuert **nie** (nur gesetzte Felder), sonst wäre „leer = erbt" nicht eindeutig.

**Schema:** `slice`/`orientation` in `$defs` (`slice_overrides`/`orientation_overrides`)
extrahiert und sowohl global als auch je Abschnitt referenziert (eine Quelle statt
Duplikat-Drift). Altprojekte ohne `sections` laden byte-gleich (additiv).

**Persistenz-Seam:** `set_process_params(sections=…)` reinigt je Abschnitt (nur
gesetzte Felder, leere Abschnitte/Gruppen fallen weg); `sections=None` lässt die
bestehenden Overrides **unberührt** (getrennt vom globalen Speichern). Die Änderung
bumpt weiterhin den `process`-Revisionszähler (Simulation/Export veralten) — die
**per-Abschnitt-Veraltung** ist bewusst #83 überlassen, hier nur auflösen + persistieren.

**UI:** Eigenes DOM-Panel `SectionParamsPanel` (nicht das globale erweitert), gespeist
aus dem Zerlegungslauf (`setSections`). Leeres Feld = erbt (Platzhalter zeigt den
geerbten Wert), gefülltes Feld = Override (Akzentrahmen `.section-param-override`).
Reine Formular↔Job-Logik + Auflösung DOM-frei in `section-params-state.ts` (vitest).

**Verifikation:** Core 549 pytest grün (+ `test_process_params_sections.py` Resolve/
Golden/Job-Helper, + Schema- & Persistenz-Tests in `test_project.py`), ruff clean.
Viewer 339 vitest grün (+ `section-params-state.test.ts` inkl. geteilte Golden-Parität),
tsc clean. **Offen (Runtime):** Headless-UI-Smoke (Edge auf Port 9333) + manueller
Durchklick der Abschnitts-Overrides am Gerät.

---

## 2026-07-07 — Feingranulare Veraltung: Pro-Abschnitts-Revisionen (#83, ADR-017-Nachtrag)

**Frage:** Ein Abschnitts-Override (#82) veraltete bislang über den `process`-Bump
den **ganzen** Job (alle Abschnitte + Druckplan). Wie stalet man **nur** den
betroffenen Abschnitt, ohne den Kern der Veraltet-Maschinerie (ADR-017) umzuwerfen?

**Alternativen:** (a) Neues, paralleles Konsistenzmodell nur für Abschnitte —
verworfen (zweite Wahrheitsquelle, Drift-Risiko, widerspricht „einzige
Schreibstelle"). (b) Nachgelagerte Abschnitts-Stände bei Override löschen —
verworfen (widerspricht „sichtbar, nicht gelöscht"). (c) **Additive Erweiterung**
des bestehenden Modells um eine Pro-Abschnitts-Ebene — **gewählt**.

**Entscheidung:** `revisions` trägt optional `section_inputs` (Zähler je
`section_id`) und `section_outputs` (je Abschnitt je Stufe der Schnappschuss der
Job-Eingaben **plus** des Abschnitts-Zählers). Ein Abschnitts-Override
(`set_process_params(sections=…)`) bumpt via `bump_section_input` **nur** den
Zähler dieses Abschnitts; `simulate_section`/`export_section_drl` frischen zusätzlich
zum Job-Schnappschuss den **Abschnitts**-Schnappschuss auf (`refresh_section_output`).
Ableitung: reine Funktion `section_output_status` (Core) ↔ `sectionStageStatus`
(`ui/staleness.ts`), Parität über geteilte Golden-Fälle
(`staleness-section.golden.json`, erzeugt von `gen_staleness_section_golden.py`).
Die Ebene entsteht **lazy**; fehlt sie (Altprojekt / vor erster Abschnitts-Sim),
fällt die Ableitung auf `output_status` (Ganzjob) zurück — rückwärtskompatibel.

**Global/strukturell bleibt Job-weit:** `set_process_params` bumpt `process` **nur**
bei einer Änderung der *globalen* Gruppen (Diff gegen den alten Stand — nötig, weil
der Viewer beim Abschnitts-Speichern die globalen Werte unverändert mitsendet; ein
unveränderter Wert darf nicht veralten). Schnitte/`cutplan`, Roboter/`robot`,
Workstation/`workstation` bumpen weiter Job-Eingaben → alle Abschnitte veralten.

**Reconciliation #77/#81-Seam:** Der Issue-Text listet „Workstation-Wechsel" explizit
als global-veraltende Änderung — im Widerspruch zum #77-Seam („workstation bumpt
nichts"). Aufgelöst zugunsten von #83: seit #80–82 **treibt** der Druckplan-
Automatismus die Workstation-Werte (Podesthöhen/Mobilität) tatsächlich, damit ist ein
Workstation-Wechsel eine echte Eingabeänderung. `workstation` wurde in `INPUT_KEYS`
+ `OUTPUT_DEPS` (alle drei Stufen) aufgenommen; `set_workstation_for_job` bumpt jetzt.
Die drei #77-Tests, die den Nicht-Bump festhielten, wurden entsprechend gedreht
(Design-Rationale bleibt in ADR-021/#77 erhalten, der Seam ist im Nachtrag als
abgelöst dokumentiert). **`stand_mode` (#81) bleibt ohne Bump** — er löst keinen
Automatismus aus, sondern parametrisiert nur den nächsten `propose`-Lauf (der
`cutplan` bumpt); der Issue-Text nennt ihn nicht.

**Verifikation:** Core 556 pytest grün (+ Pro-Abschnitts-Tests & geteilte Golden-
Parität in `test_export.py`, gedrehte Workstation-Tests in `test_workstation_choice.py`),
ruff clean. Viewer 345 vitest grün (+ `sectionStageStatus`-Fälle & Golden-Parität in
`staleness.test.ts`), tsc clean. **Offen (Runtime):** manueller Durchklick — ein
Abschnitts-Override darf nur dessen Sim/Export-Badge einfärben. Siehe ADR-017-Nachtrag.

---

## 2026-07-07 — Druckplan S5: Fokus-Abschnitt anklicken + weiche Kamera-Einfassung (#84)

**Frage:** Wie wird ein Abschnitt im geteilten 3D-Feld zum *Fokus* — Grundlage
für Live-Vorschau (#85/S6) und Simulieren-Modus (#86/S7) — ohne den Bezug zu
Nachbarn und Schnittfugen zu verlieren? Und wo lebt der Auswahlzustand?

**Alternativen erwogen:**
1. *Fokus = Kamera-Zoom, der die Nachbarn ausblendet.* Verworfen: der Issue
   fordert ausdrücklich „ganze Wand bleibt sichtbar" — Nachbarn/Fugen sind der
   Kontext, den der Nutzer beim Gradieren braucht.
2. *Pick gegen die Schnittebenen (#24) statt eigener Geometrie.* Verworfen: die
   Ebenen sind die **Fugen** (Ränder), kein Abschnitts-Volumen — ein Klick „auf
   den Abschnitt" trifft die Fläche, nicht die Kante. Eigene, pro Abschnitt
   pickbare Quader sind die ehrliche Repräsentation.
3. *Fokus-Zustand in main.ts / im three.js-Code.* Verworfen zugunsten des
   Pure/DOM-Splits (wie `cutplan-state.ts`): die Auswahllogik muss ohne Renderer
   testbar sein.

**Entscheidung:**
- **Reine Auswahllogik** `viewer/src/ui/focus-state.ts` (`FocusState =
  { focusedSectionId: string | null }`, `toggleFocus`/`focusSection`/`clearFocus`/
  `reconcileFocus`), DOM- und three.js-frei, vitest-getestet. Genau ein Fokus
  oder keiner; **Klick togglet** (erneuter Klick auf den Fokus löst ihn) → der
  „kein Fokus"-Zustand fällt gratis aus der Interaktion. `reconcileFocus` lässt
  einen Fokus, dessen Abschnitt durch neue Zerlegung/Neubewertung verschwand,
  sauber wegfallen (abwärtskompatibel, auch bei nur einem Abschnitt).
- Der **Druckplan-Panel** hält diesen Zustand (`DruckplanPanel._focus`) und
  meldet Änderungen über `onFocusChanged(sectionId|null)` — der 3D-Klick in
  main.ts ruft `druckplanPanel.focusSection(id)`, die Auswahl bleibt im Panel.
- **Pickbare Quader** `viewer/src/render/sections.ts`: je Abschnitt ein Quader
  aus der Wand-Bounding-Box + Abschnittsgrenzen (dieselbe Konvention wie
  `cutplanes.ts`: `x0..x1` zentriert entlang der Längsachse, `z0..z1` ab Wandfuß,
  volle Dicke — reine Fn `sectionBoxSpec`, vitest). **Normal opacity 0**
  (unsichtbar, aber der three.js-Raycaster ignoriert Deckkraft → voll pickbar) →
  die ganze Wand bleibt frei; nur der Fokus-Quader wird getönt (opacity 0.28,
  gedämpftes Violett, bewusst außerhalb Ampel-Grün/Rot, Amber-Fugen, Cyan-Basis).
- **Weiche Kamera-Einfassung** in main.ts, **vom Fokus getrieben**: eased Tween
  (`easeInOutCubic`, 600 ms) von Kamera-Position + Orbit-Ziel. Ziel = Abschnitts-
  Mittelpunkt, **Abstand ≥ Wanddiagonale × 0,9** → die ganze Wand bleibt im Bild
  (kein Nachbar-Ausblenden, kein harter Sprung). Blickrichtung bleibt erhalten;
  nur der Orbit-Punkt wandert. Kein Fokus → Tween zurück auf die Wandmitte.
  Reine Darstellung/Animation (ADR-007, Kamera ist kein Fachzustand).

**Begründung:** Der Split hält die Urteilsfreiheit (Viewer rechnet nichts,
ADR-007) und die Testbarkeit (Auswahllogik vitest-rein, Geometrie-Spec vitest-
rein; Kamera/Animation bleiben visueller Smoke). Der opacity-0-Pick-Trick macht
Abschnitte klickbar, **ohne** die Wand zu verdecken — genau die „ganze Wand
sichtbar"-Anforderung.

**Verifikation:** Viewer **359 vitest grün** (+14: `focus-state.test.ts` 9,
`sections.test.ts` 5), tsc + `vite build` clean. `ui_smoke.mjs` um einen
Druckplan-Schritt erweitert (Diagnose-Hooks `__focusDebug`/`__focusSection`):
Ausgangszustand ohne Fokus → Abschnitt fokussieren (Quader-Deckkraft > 0 **und**
Wand sichtbar) → Toggle löst den Fokus wieder. Headless-CDP-Lauf bestanden
(boxes=6, focused=abschnitt-1, opacity=0.28, wallVisible=true; Toggle→null). Die
einzige rote Smoke-Zeile ist der vorbestehende, unabhängige Bibliothek-cfg-Canvas
0×0-Layout-Flake im Headless (Konfigurator-Viewport, von #84 nicht berührt).

## 2026-07-07 — Druckplan S6: Live-Vorschau „Vorbereiten" — Düsen-Schablone + sofortige Bahnen + Sicherheitsabstand (#85, PRD B/#70)

**Frage:** Wie gibt der Modus **Vorbereiten** beim Reglerziehen eine sofortige,
billige, **IK-freie** Rückkopplung im 3D-Feld — eine Düsen-Schablone entlang der
frisch gesliceten Bahn des Fokus-Abschnitts (#84) + einen verständlichen
Sicherheitsabstand — **ohne** vom vollen Arm-Lauf auseinanderzudriften?

**Kern-Entscheidung (die eine geteilte Orientierungsquelle):** Die Schablonen-
Pose je Bahnpunkt kommt **vorwärts** aus `nozzle_quat` (#61) — **derselben**
Funktion, aus der Slicer und `placement` ihre Rotation ziehen —, **nicht** aus
einer neuen Formel. Da `nozzle_quat` im Core (Python) lebt, spiegelt die Vorschau
sie als **bit-gleichen TS-Zwilling** `viewer/src/ui/nozzle-quat.ts` (Muster
`resolveSectionParams`/#82): Golden-Fälle werden **vom Core** erzeugt
(`viewer/scripts/gen_nozzle_golden.py` → `nozzle-quat.golden.json`) und vom vitest
bit-nah reproduziert. Damit gilt der Regressionsschutz #51/#58 auch für die
Schablone: Schablone↔voller Lauf können nicht driften, weil beide dieselbe
Rotation ziehen. Der Golden der Schablonen-Posen (`nozzle-schablone.golden.json`)
enthält die Quaternionen **aus dem Core** je Bahnpunkt — der Test beweist
zugleich die Wiederverwendung, nicht nur die Korrektheit.

**Alternativen verworfen:** (1) *Eigene Lead/Kipp-Formel im Viewer* — genau der
Drift-Fehler, den #51 ausschloss; verworfen. (2) *Core je Regler-Tick neu slicen
lassen* — zu teuer/langsam für „flüssig beim Ziehen", widerspricht „billig,
IK-frei". Stattdessen ein **billiger Vorschau-Slicer** `ui/preview-slice.ts`
(reine Darstellungsmathematik, ADR-007): gestapelte, **CCW**-orientierte
Rechteck-Umfangsringe aus Abschnitts-Box + effektiven Slice-Params. CCW ist
bewusst — es ist die Konvention, aus der `nozzle_quat` die Wand-Außenseite
ableitet (`n_out = tangent × ẑ`), sonst kippte die Schablone falschherum. (3)
*Effektive Params aus dem gespeicherten Job* — dann wäre die Vorschau erst nach
„Speichern" live; stattdessen liest sie die **live**, ungespeicherten
Formularwerte (neue `onLiveChange`-Callbacks + `liveParams`/`liveOverrideFor` an
`ProcessParamsPanel`/`SectionParamsPanel`) und löst sie mit **derselben**
`resolveSectionParams`-Auflösung wie #82 auf (global ⊕ Override → effektiv).

**Sicherheitsabstand als lebende Zahl:** `ui/safety-clearance.ts` (rein) rechnet
aus `standoff` (#80) + `safety_min_distance_mm` (#77) einen **atmenden** Puffer
(Puls zwischen 0,8·Mindestabstand und Mindestabstand über einen Kosinus-Zyklus)
+ die Marge/Sicherheits-Flag. `render/clearance.ts` färbt grün (Marge ≥ 0) bzw.
rot und pulsiert die Puffer-Tiefe — die Zahl wird ohne Erklärung verständlich und
reagiert sichtbar auf die Abstands-Optimierung.

**Pure/DOM-Split:** Reine Geometrie (Posen, Vorschau-Bahn, Puffer) DOM-/renderer-
frei + vitest (`nozzle-quat`, `nozzle-schablone`, `preview-slice`,
`safety-clearance`); three.js + Animation getrennt in `render/schablone.ts`,
`render/clearance.ts`, gebündelt in der Steuerung `render/prepare-preview.ts`
(rAF-Takt fürs Gleiten/Atmen, Muster `stepCameraTween`; an `viewport.world`
gehängt, in der Roboter-Vorschau pausiert). Die Vorschau erscheint **nur bei
Fokus** (baut auf #84 auf) und wird beim Fokus-Lösen geräumt.

**Verifikation:** Viewer **381 vitest grün** (+22: `nozzle-quat` 5,
`nozzle-schablone` 5, `preview-slice` 7, `safety-clearance` 5), tsc + `vite build`
clean. `ui_smoke.mjs` um einen Vorbereiten-Schritt erweitert (Diagnose-Hook
`__prepareDebug`): bei Fokus `active=true, nPoses=2050, standoff=700,
safetyMin=50`; Fokus gelöst → `active=false`. Headless-CDP-Lauf bestanden; die
einzige rote Zeile ist der vorbestehende, unabhängige Bibliothek-cfg-Canvas
0×0-Flake (von #85 nicht berührt). Viewer-only, kein Core-Change.

---

## 2026-07-07 — Modus-Fusion „Vorbereiten↔Simulieren", Reiter Simulation absorbiert (#86, PRD B/#70, Abschluss)

**Frage:** Die letzte Scheibe von PRD B (Druckplan-Redesign): den separaten Reiter
**Simulation** in den Reiter **Druckplan** überführen und die zwei Modi eines
geteilten 3D-Felds (OrcaSlicer-artig) klar machen — **Vorbereiten** (einstellen +
billige Live-Vorschau, #85) vs. **Simulieren** (voller, echter Arm-Lauf: slice +
IK + Timing). Wie ohne neue Kinematik und ohne Altprojekte zu brechen?

**Entscheidung:** Ein **Moduswechsel** oben im Druckplan (Radiogruppe
Vorbereiten/Simulieren). Vorbereiten reaktiviert die Live-Vorschau am Fokus (#85);
Simulieren blendet den absorbierten **Simulieren-Bereich** ein (der ganze frühere
`ui/simulation.ts` inkl. Trajektorien-Player wandert per DOM in das Druckplan-Panel)
und **ruht** die Live-Vorschau. Der Wechsel ist bewusst, damit nicht mit veralteten
Werten simuliert wird. Zwei Simulieren-Knöpfe: **„Fokus-Abschnitt simulieren"**
(sliced + simuliert den Fokus-Abschnitt mit den aktuellen Werten → frischer Lauf,
nie veraltet, und spielt ihn sofort als vollen Arm-Lauf ab) und **„Ganze Wand
(unten → oben)"** (die bestehende Gesamtablauf-Sequenz #27 mit Umbau-Schritt).
Reine Darstellung/Orchestrierung über die **bestehenden** Simulier-Aktionen
(`simulate_section`, `section_runs`, Sequenz-Player) — **keine neue Kinematik**
(ADR-007). Kein Core-Change, viewer-only.

**Alternativen erwogen:** (1) *Neuen zweiten Reiter behalten und nur umbenennen* —
verfehlt die Fusion („Planen und Sehen an einem Ort") und den PRD-Kern. (2) *Player
neu bauen im Druckplan* — verworfen: dieselbe `TrajectoryPlayer`-Instanz +
`showRun`-Verdrahtung wiederverwenden ist risikoärmer und hält das Verhalten
identisch; nur der DOM-Wohnort und `setActiveTab("simulation")→"druckplan")`
wechseln. (3) *Beim Simulieren automatisch alle veralteten Abschnitte neu rechnen* —
verworfen zugunsten **Sichtbarmachen** (#83-Badges) + gezieltem Re-Sim des
Fokus-Abschnitts; der Fokus-Lauf entsteht ohnehin frisch, ist also nie veraltet.

**Backward-Compat (US 24):** `focusTarget(focusedId, sectionIds)` gibt bei genau
**einem** Abschnitt diesen auch ohne expliziten Fokus → Einzelabschnitts-/Override-
freie Altprojekte spielen wie bisher (Fokus-Knopf funktioniert, Sequenz = der eine
Abschnitt ohne Umbau). Feingranulare Veraltung über `sectionStageStatus` (#83):
nur tatsächlich veraltete Abschnitte tragen ein „veraltet"-Badge, ein simulierter
unveränderter bleibt grün. Fehlt `revisions` (sehr altes Projekt), gilt nichts als
veraltet.

**Pure/DOM-Split:** Modus-Prädikate + `focusTarget` + `staleSimSections` rein in
`ui/druckplan-mode.ts` (vitest, 11 Tests); DOM-Umschalter in `ui/plan-mode-panel.ts`;
`ui/tabs.ts` von 5 auf 4 Prozess-Reiter (Simulation entfernt). DOM-Vertrag in
`shell-structure.test.ts` (Player + Simulieren-Bereich im Druckplan, Reiter
Simulation weg), `scene-mode.test.ts`/`tabs.test.ts` nachgezogen.

**Verifikation:** Viewer **392 vitest grün** (+11 `druckplan-mode`), `tsc --noEmit`
+ `vite build` clean. `ui_smoke.mjs` um Schritt 2d erweitert: Reiter Simulation aus
der Tab-Leiste weg (`gone=true`), Umschalten auf Simulieren blendet den
Simulieren-Bereich mit Fokus-/Wand-Knopf + Player ein (`simVisible=true`);
Prozess-Reiter-Schleife auf 4 reduziert. Headless-CDP-Lauf bestanden; einzige rote
Zeile ist der vorbestehende, unabhängige Bibliothek-cfg-Canvas-0×0-Flake (von #86
nicht berührt). **PRD B (#70) ist damit komplett.**

---

## 2026-07-07 — Grill: Druckplan-Neuordnung II — Zerlegungsart-Weiche, Modul an der Workstation, Teile-Palette (ADR-022)

**Frage:** Der Druckplan-Reiter ist nach #80–#86 organisch auf 12 Sektionen
gewachsen. Der Nutzer will: Geometrieaufteilung klar von Slicing trennen,
zuerst die Aufteilung visualisieren, globale und teilspezifische
Einstellungen ordnen, Roboter-Positionierung sichtbar/einstellbar machen —
und die Zerlegungsart **Modul** (Vorproduktion + Montage) soll jetzt
funktionieren, Fügegeometrie später.

**Entscheidungen (Interview, Ast für Ast):**

1. **Scope:** Modul wird funktionsfähig (ebene Stoßfugen, keine
   Fügegeometrie/Montage-Simulation) — Architekturrang, siehe **ADR-022**:
   Workstation = Druckort, Platzierung = Relativpose, stehend in
   Einbauorientierung, Arbeitsraum + optionale max. Länge/Höhe als Grenzen,
   Gewicht als Befund, Schnitte zerlegungsart-neutral (Artwechsel behält
   sie, dirty), Druck- = Montagereihenfolge.
2. **Rubriken-Schnitt (2er, fachlich):** Sidebar-Rubriken „Zerlegung &
   Platzierung" und „Slicing" (Muster `library-rubrics.ts`); Modus-Schalter
   Vorbereiten↔Simulieren bleibt panel-global darüber. Ein 3er-Schnitt
   (Zerlegung|Platzierung|Slicing) wurde verworfen: Zerlegung und
   Platzierung sind im Core eine verkoppelte Rechnung. Ein
   Geltungsbereichs-Schnitt (Einstellungen|Teile) wurde erwogen und vom
   Nutzer wieder verworfen.
3. **Zerlegungsart als Weiche** ganz oben in der Rubrik (Radiogruppe statt
   Dropdown-Detail): Abschnitt zeigt Aufstell-Toggle, Modul zeigt max.
   Modullänge/-höhe; darunter Zerlegungsvorschlag, Schnittplan
   (Collapsible), alte Sektionen Aufstellung/Optimalvorschlag/Bewertung
   gehen darin bzw. in der Teile-Palette auf.
4. **Teile-Palette** statt dritter Rubrik: ein-/ausklappbare Leiste am
   3D-Feld, je Teil Ampel/Name/erreichbar %, Marker ▪ bei individuellen
   Overrides; Auswahl ↔ 3D-Fokus beidseitig synchron.
5. **Gilt-für-Umschalter** (OrcaSlicer-Muster) statt separatem
   Objekt-Menü: Global ↔ gewähltes Teil; dieselben Formulare, geerbte Werte
   dezent, Eingabe = feldweiser sparse Override (#82-Mechanik), ↺ je Feld;
   strukturelle Einstellungen im Teil-Modus **ausgegraut** (nicht
   ausgeblendet — Formular springt sonst); Slicing voll übersteuerbar,
   Singularitäts-Advisor bleibt global. Platzierungs-Override künftig mit
   freien Werten, nicht nur Optionsauswahl.
6. **Visualisierung:** Basis-Marker aller Platzierungen dauerhaft vor der
   Wand (Aufstellmuster + Konsolidierungspotenzial sichtbar); Fokus-Teil =
   **echtes M1013-Mesh** (GLBs aus `viewer/public/robots/m1013/` existieren)
   statt Kapsel-Arm; Reichweiten-Hüllkurven verworfen (Ampel trägt die
   Information, Überlappung wird Matsch). Modul-Fokus: **Druckort-Ansicht**
   (Einbauort ↔ Workstation-Szene, Kamera-Einfassung aus #84
   wiederverwendet).
7. **Simulation im Modul-Modus:** „Fokus-Modul" am Druckort; „Ganze Wand" →
   „Alle Module" (sequentiell am Druckort, Player spielt Abschnitte schon
   heute sequentiell); Montage-Simulation explizit out of scope.
8. **Globale Platzierungs-Einstellungen = Suchraum-Vorgaben** (Toggle,
   Workstation-Bindung), keine manuelle Wand-Platzierung als vererbter
   Default — die wäre für zerlegte Wände semantisch schief; „relativ zur
   ganzen Wand" ist der Spezialfall unzerlegte Wand = ein Teil.

**Korrektur einer Fehlannahme des Nutzers:** Der Core optimiert die
Zerlegung *bereits* auf abschnitts-lokale Platzierungen
(`decompose/propose.py`: Verfeinerung bis jede Zelle von ihrer eigenen
Platzierung grün ist; `from_cuts`: `suggest` je Abschnitt) — das Problem war
Sichtbarkeit im UI, nicht die Logik.

**Glossar:** `core/CONTEXT.md` — Platzierung (Relativpose, zwei
Leserichtungen), Zerlegung (Modul jetzt v1, Details), **Workstation** neu;
`viewer/CONTEXT.md` — Reiter (fünf→vier, Korrektur nach #86), **Teil**,
**Teile-Palette**, **Gilt-für-Umschalter**, **Druckort-Ansicht** neu.

## 2026-07-07 — Druckplan-Neuordnung II S1: Rubriken „Zerlegung & Platzierung"/„Slicing" (#89, PRD #88)

**Frage:** Wie den überlangen Druckplan-Aside (zwölf gestapelte Sektionen)
in die zwei im Grill (PRD #88) beschlossenen Rubriken „Zerlegung &
Platzierung" und „Slicing" ordnen, ohne Bedienpfade zu verlieren und ohne
den toten-Reiter-Bug (#56) zu riskieren — und wie das Rubriken-Muster der
Bibliothek dabei entdoppeln?

**Alternativen:**
1. *`library-rubrics.ts` kopieren und für den Druckplan anpassen* —
   verworfen: zwei nahezu gleiche Umschalter, die auseinanderdriften.
2. *Ein geteiltes, generisches Rubriken-Modul* (reiner `RubricsState<Id>` +
   dünne DOM-Klasse `Rubrics<Id>`), das beide Aufrufer über Ids/Startsicht
   parametrieren — **gewählt**.
3. *Schnittplan zusätzlich als Collapsible* (so die PRD-Klammer): verworfen
   zugunsten der bindenden Akzeptanz „globale Blöcke immer ausgeklappt,
   einzig ‚Fortgeschritten' einklappbar" — kein neues Collapsible, reine
   Neuordnung.

**Entscheidung:**
- Neues geteiltes Modul: `viewer/src/ui/rubrics-state.ts` (DOM-frei, vitest:
  aktive Rubrik, `setActive` meldet Änderung, defensive Id-Kopie) +
  `viewer/src/ui/rubrics.ts` (generische DOM-Klasse, Umschalten
  **ausschließlich über `.hidden`**, aktiver Button `.active`, optionaler
  `onRubricChanged`). `library-rubrics.ts` ist jetzt ein dünner Aufsatz
  darauf — Verhalten byte-gleich, sein jsdom-Test bleibt unverändert grün.
- Druckplan-Aside: Modus-Schalter Vorbereiten↔Simulieren bleibt
  **panel-global** oben; darunter die Rubriken-Nav (horizontale Tabs) mit
  zwei Sichten. „Zerlegung & Platzierung" = Aufstellung + Bewertung,
  Zerlegungsvorschlag, Schnittplan; „Slicing" = Prozessparameter,
  Anstellwinkel, Fortgeschritten (**einzig** einklappbar),
  Pro-Abschnitts-Overrides, Singularitäts-Advisor. Der Simulieren-Bereich
  (#86) bleibt unverändert und panel-global (nach den Rubriken, vom Modus
  gesteuert). Alle DOM-Ids bleiben — `DruckplanPanel` findet seine Elemente
  per `getElementById`, deshalb ist die Umsortierung risikoarm.
- `main.ts` instanziiert den Druckplan-Umschalter direkt über das generische
  `Rubrics` (Start „zerlegung"); Diagnose-Hook `__druckplanRubricsDebug`
  für den Headless-Smoke.

**Begründung:** Ein State/DOM-Split hält die Auswahllogik testbar und die
Sichtbarkeit an genau einer Stelle (`.hidden`), womit das globale
`[hidden]{display:none!important}` jedes `display:flex` schlägt (Schutz vor
#56). Additiv, Viewer-only, keine neue Funktionalität — nur Ordnung.

**Doku:** README-Abschnitt „Druckplan-Rubriken", `shell-structure.test.ts`
um den Druckplan-Rubriken-Vertrag erweitert, `ui_smoke.mjs` Schritt 2e
(Rubrikenwechsel), Glossar unverändert (Begriffe „Rubrik"/„Zerlegung"/
„Platzierung" bereits fixiert).

## 2026-07-07 — Druckplan-Neuordnung II S6: Core Modul-Zerlegung — `kind='modul'`, Modulgrenzen, Gewicht als Befund (#90, PRD #88, ADR-022)

**Frage:** Wie wird die Zerlegungsart **Modul** im Core funktionsfähig
(ADR-022), ohne die byte-gleiche Art „abschnitt" oder die bestehende
Determinismus-/Additivitäts-Zusage zu brechen — und wo lebt die neue
Modulgrenzen-/Gewichtslogik, ohne einen zweiten Dichte-Default zu erfinden?

**Alternativen:**
1. *Modul über eine eigene Platzierungssuche je Zelle* (wie „abschnitt", nur
   mit anderer Kandidatenmenge) — verworfen: ADR-022 fixiert die Modul-Lage
   als **eine feste Platzierung an der Workstation** (Roboter sitzt fest,
   Modul steht vor ihm); eine Suche je Zelle würde diese Invariante
   verwässern und wäre teurer.
2. *Gewicht/Grenzen inline in `propose`/`evaluate` rechnen* — verworfen:
   das Hausmuster verlangt ein reines, tiefes Modul (no I/O, deterministisch,
   pytest + Golden). Neues `fgc.decompose.limits` (`ModuleLimits`,
   `LimitFinding`, `ModuleCheck`, `check_module`/`check_plan`).
3. *Eigener Dichte-Parameter/Config* — verworfen: die **Prozessfenster-Karte**
   ist die eine Quelle für Prozessparameter (ADR-013), wie `default_shells`.
   Neues Feld `density_kg_m3` in Karte + `ProcessWindow` +
   `PROVISIONAL_DEFAULTS` (Lehm-typischer Platzhalter 1900 kg/m³, provisorisch
   bis S1).
4. *Obergrenzen als Gate* — verworfen: ADR-022 sagt „Befund, kein Gate".
   Grenzen verfeinern nur das Raster (Zelle > Grenze ⇒ weitere Teilung, `ceil`
   garantiert Zellen ≤ Grenze); verletzte Grenzen/Gewicht werden nur gemeldet,
   nie blockiert. Der harte Begrenzer bleibt der Arbeitsraum (in `propose`).
5. *`kind='modul'` still auf „abschnitt" zurückfallen lassen, wenn keine
   Workstation gewählt ist* — verworfen: die Workstation **ist** der Druckort
   (ADR-022). Ohne sie kommt ein freundlicher, verortbarer `ValueError`
   (`_check_kind`) statt eines stillen, verwirrenden Fallbacks.

**Entscheidung:**
- `propose`/`from_cuts` akzeptieren `kind='modul'`: der bisherige `ValueError`
  entfällt, `_check_kind` validiert Art **und** Modul-Druckort. Bei „modul"
  gilt für alle Teile die **eine feste Platzierung** `_module_placement`
  (Relativpose aus `robot_base_frame`/`work_surface_frame`, sonst
  Standard-Abstand; nie unter dem Sicherheits-Mindestabstand). Die
  Rasterverfeinerung (`_module_grid_counts`) bewertet jede Zelle an dieser
  festen Lage (`placement.evaluate`, keine Suche) und startet aus den
  optionalen Obergrenzen — leer = nur Arbeitsraum. Druckreihenfolge =
  Montagereihenfolge unten→oben.
- Neues reines Modul `fgc.decompose.limits`: Gewicht = Volumen × Dichte (auf
  3 NK gerundet, deterministisch), je gesetzter Obergrenze ein Befund
  (`exceeded` strikt `>` — exakt auf der Grenze gilt als eingehalten),
  Reihenfolge Länge vor Höhe. pytest + Golden
  (`fixtures/module_limits.golden.json`): keine Grenzen, exakt-auf-Grenze,
  Verletzung, Gewichtsrechnung, Dichte-Default = Kartenwert.
- Additive Schemas: `decompose.schema.json` (`sections[].module_check` +
  `module_limits`-Echo), `project.schema.json` (`print_job.module_limits`,
  sparse). Beide nur bei „modul" belegt; „abschnitt" + Altprojekte laden
  byte-gleich (bestehende Goldens grün).
- Setter `set_module_limits_for_job` in `fgc.project`-Kette (ADR-016, einzige
  Schreibstelle) + Route `PUT /projects/{slug}/module-limits` — Spiegel von
  `set_stand_mode_for_job` / `PUT .../stand-mode`, **bewusst ohne Veraltung**
  (die Neubewertung ist der nachfolgende `propose_decomposition`, bumpt
  dort `cutplan`).

**Begründung:** Ein reines, golden-getestetes `limits`-Modul hält Gewicht/
Grenzen deterministisch und testbar außerhalb der Kinematik; die feste
Workstation-Platzierung schließt zugleich die #77/#79-Frame-Naht (die
ADR-021-Frames bekommen ihren vorgesehenen Konsumenten). „Befund, kein Gate"
und „eine Quelle" (Karte) bleiben gewahrt; Additivität hält alle bestehenden
Goldens und Altprojekte byte-gleich.

**Doku:** Kein README-Abschnitt (folgt mit der UI-Scheibe S7/#95 laut
Issue #90); Glossar bereits mit ADR-022 geschärft. `docs/status.md`
aktualisiert. Tests: `test_module_limits.py` (Golden + Grenzfälle),
`test_decompose.py` erweitert (Modul propose/from_cuts, feste Platzierung,
Obergrenzen-Verfeinerung, freundlicher Hinweis ohne Workstation, Setter +
Route). Core-Suite grün (nur die bekannte os.replace-WinError-5-Windows-
Temp-Race-Flake), ruff clean.

---

## 2026-07-07 — Druckplan-Neuordnung II S2: Teile-Palette am 3D-Feld (Issue #91, PRD #88)

**Frage:** Die einzelnen Teile (Abschnitte) eines Druckjobs lebten als lange
Liste (`#decompose-sections`) im Druckplan-Aside — mit Ampel, erreichbarem
Anteil, Platzierungs-Override-Select und Fokus-Klick. PRD #88 will sie stattdessen
als **Teile-Palette am 3D-Feld** (OrcaSlicer-Vorbild): eine ein-/ausklappbare
schmale Leiste mit Auswahl↔Fokus-Sync und Override-Markern. Wie zerlegen wir das
modular, ohne einen parallelen Auswahlzustand zu bauen?

**Alternativen:**
- *Palette in den Aside legen* (nur umsortieren) — verworfen: „am 3D-Feld" ist
  eine bewusste UX-Entscheidung (Glossar „Teile-Palette"), die Nähe zur 3D-Box
  macht den Auswahl↔Fokus-Bezug greifbar.
- *Eigener Auswahlzustand in der Palette* — verworfen: es gibt bereits den
  Fokus-Zustand (#84). Ein zweiter Zustand müsste ständig synchron gehalten
  werden (Fehlerquelle). Stattdessen **ist** die Auswahl der Fokus.
- *Marker aus den Live-Formularwerten der Overrides ableiten* — verworfen für v1:
  der Marker soll den **persistierten** Override anzeigen (`process_params.sections`),
  nicht ungespeicherte Tastenanschläge; das ist eindeutig definiert und stabil.

**Entscheidung:**
- **Reines Modul** `viewer/src/ui/parts-palette-state.ts`: `paletteEntries`
  (Einträge in Druckreihenfolge, Ampel grün/rot/ungeprüft, erreichbar %, ▪-Marker,
  Auswahl) + `slicingOverrideSectionIds` (Marker-Quelle: welche `section_id`s in
  `process_params.sections` eine **nicht-leere** slice/orientation-Gruppe tragen).
  DOM-/three.js-frei, vitest.
- **Dünne DOM-Klasse** `viewer/src/ui/parts-palette.ts` (`PartsPalette`): rendert
  je Teil Ampel/Name/erreichbar %/▪-Marker/Platzierungs-Override-Select, klappt
  Kopf↔Körper und schaltet die ganze Leiste **ausschließlich über `.hidden`**
  (nie `style.display`, Lehre aus #56). Meldet Auswahl + Override-Wechsel zurück.
- **Auswahl ↔ Fokus:** die Palette hält **keinen** eigenen Zustand — der
  `DruckplanPanel` besitzt weiter den Fokus (`focus-state.ts`, #84). Palette-Klick
  → `focusSection` (toggleFocus), 3D-Klick → `focusSection` → `_renderPalette`
  markiert den Eintrag; beide Richtungen laufen über **denselben** Zustand.
  `reconcileFocus` bei neuer Zerlegung räumt Auswahl + Fokus gemeinsam.
- **Marker-Speisung:** `main.ts` ruft nach jeder Änderung an `process_params.sections`
  (Speichern, Zerlegung wiederherstellen, Projekt öffnen/anlegen) einen kleinen
  Helper `updatePartsOverrideMarkers()` → `druckplanPanel.setSlicingOverrideSections`.
- **Sichtbarkeit:** die Leiste liegt als Geschwister neben `#viewport` in `#tab-body`
  (position:absolute über dem geteilten 3D-Feld) und wird von `onTabChanged` nur
  im Reiter Druckplan eingeblendet.
- **Alte Liste entfernt:** `#decompose-sections` + tote CSS-Regeln
  (`.decompose-section*`, `.decompose-override`, `.section-focus-handle`, `.fokus`)
  raus; `shell-structure.test.ts` zieht den Vertrag nach (Palette am 3D-Feld statt
  im Panel, alte Liste weg).

**Begründung:** Der Pure/DOM-Split hält die Ableitung testbar (18 neue vitest),
die Wiederverwendung des Fokus-Zustands schließt die Sync-Fehlerquelle konstruktiv
aus (kein paralleler Zustand), und der Marker aus dem persistierten Job ist
eindeutig definiert. Viewer-only, additiv, kein Core-Change.

**Doku:** README-Abschnitt „Teile-Palette am 3D-Feld …" (Reiter Druckplan #91);
`docs/status.md` aktualisiert. `ui_smoke.mjs` um Schritt 2f erweitert (Auswahl↔
Fokus-Sync über `__partsPaletteDebug`/`__focusSection`, Marker über
`__setSlicingOverrideMarker`); bei der Gelegenheit drei vorbestehende, im
`node --check` fehlerhaft schließende Rubriken-Strings aus Schritt 2e (#89)
repariert. Viewer 424 vitest grün (+18: parts-palette-state 8, parts-palette 6,
shell-structure +4), tsc + `vite build` clean. **Headless-CDP hier nicht gelaufen**
(braucht Core+Vite+Edge+Projekt) — Smoke-Schritt nur im Code ergänzt. Offen
(Runtime): manueller Durchklick + Headless-Lauf am Gerät.

## 2026-07-07 — Druckplan-Neuordnung II S3: Gilt-für-Umschalter Global↔Teil (Issue #92, PRD #88)

**Frage:** Die Gradierungs-Ebene (#82) lebte als eigene Aside-Sektion mit einem
kompletten Formularsatz **je Abschnitt** — bei vielen Teilen ein langer, doppelter
Formularstapel neben den globalen Slicing-Formularen. PRD #88 will stattdessen den
**Gilt-für-Umschalter** (OrcaSlicer-Vorbild, Glossar `viewer/CONTEXT.md`): Global ↔
gewähltes Teil in **denselben** Formularen. Wie bauen wir das, ohne die #82-Mechanik
zu duplizieren und ohne die granulare Veraltung (#83) zu brechen?

**Alternativen:**
- *Separate Teil-Formulare behalten und nur einklappen* — verworfen: der doppelte
  Formularsatz bleibt (Pflegelast, Drift-Gefahr zwischen global und je Teil);
  das PRD verlangt ausdrücklich „dieselben Formulare".
- *Strukturelle Gruppen im Teil-Modus ausblenden statt ausgrauen* — verworfen:
  das Formular würde springen (Layout-Shift); Glossar-Vorgabe ist explizit
  „ausgegraut, nicht ausgeblendet".
- *Zweiter Override-Store im Panel (eigene Map, eigene Auflösung)* — verworfen:
  `process_params.sections` + `resolveSectionParams` (#82) sind die eine Quelle;
  jede Kopie müsste synchron gehalten werden.
- *↺ persistiert sofort je Feld (eigener API-Call pro Reset)* — verworfen: alle
  übrigen Slicing-Eingaben sind Save-Button-basiert; ein sofort schreibendes ↺
  wäre ein inkonsistentes Bedienmuster und erzeugte API-Chattiness. ↺ setzt das
  Feld im Formular zurück, „Speichern" persistiert wie gehabt.

**Entscheidung:**
- **Reines Scope-Modul** `viewer/src/ui/scope-state.ts`: Geltungsbereich +
  Fokus-Abgleich (`reconcileScopeFocus` — Abwahl ⇒ Global, Teil-Wechsel behält
  die Stellung), Sichtbarkeit (`switchVisible`: nur bei gewähltem Teil),
  **Ausgrau-Matrix** (`groupEnabled`: Aufstellung/Zerlegung/Schnittplan im
  Teil-Modus gesperrt, Slicing frei, Advisor global), **Vererbungsanzeige**
  (`overrideFieldView`: Override-Wert im Feld, geerbter Wert dezent als
  Platzhalter) und **Ein-Feld-Reset** (`resetOverrideField`, immutable).
  DOM-frei, vitest (18 Fälle inkl. #83-Anker).
- **Dünne DOM-Anbindung** `viewer/src/ui/scope-switch.ts` (`ScopeSwitch`):
  Radio-Paar oben im Aside, sichtbar **nur** über `.hidden` (Lehre aus #56),
  meldet den wirksamen Geltungsbereich per Callback.
- **`ProcessParamsPanel` wird scope-fähig** statt eines zweiten Panels: die
  **selben neun Inputs** zeigen je nach Scope das globale Formular oder das
  Override-Formular des gewählten Teils (Stash/Write beim Umschalten — keine
  ungespeicherte Eingabe geht verloren). Teil-Scope: Platzhalter = geerbter
  globaler Wert, Override-Hervorhebung `.section-param-override`, je Feld ein
  ↺ (`${inputId}-reset`). „Speichern" schreibt im Teil-Scope über **dieselbe**
  Route (`PUT …/process-params`, Feld `sections`, alle bekannten Teile sparse) —
  `section-params-state.ts` (#82) bleibt die eine Umrechnungs-/Auflösequelle.
- **Alte Sektion entfällt:** `viewer/src/ui/section-params.ts`
  (`SectionParamsPanel`) + ihr DOM (`#section-params-*`) + tote CSS
  (`.section-params-block`) sind entfernt; `shell-structure.test.ts` zieht den
  Vertrag nach (Umschalter vor der Rubriken-Leiste, ↺ je Feld, alte Ids weg).
- **Ausgrau-Matrix im `DruckplanPanel`:** `setStructuralLocked(locked)` sperrt
  Aufstell-Toggle, Optimalvorschlag, Zerlegungsart, Zerlegungsvorschlag und den
  ganzen Schnittplan-Block ausschließlich über `disabled` — nie `.hidden`.
- **#83 unverändert:** der Umschalter nutzt dieselbe Route, der Core bumpt beim
  Teil-Override weiter nur `section_inputs[teil]`; abgesichert per vitest
  (scope-state.test.ts, `sectionStageStatus`) und im Smoke (Schritt 2g über den
  neuen Hook `__revisionsDebug`).

**Begründung:** Ein Formularsatz statt n+1 (das PRD-Kernversprechen), null
Duplikation der Override-Mechanik (#82 bleibt die eine Quelle für Umrechnung und
Auflösung), und die Ausgrau-Matrix als **Daten** im reinen Modul macht die
UX-Regel („strukturell erzeugt Teile, kann nicht je Teil gelten") testbar statt
implizit. Viewer-only, additiv, kein Core-Change.

**Doku:** README-Abschnitt „Gilt-für-Umschalter Global↔Teil …" (+ Verweise in
den #82/#89-Abschnitten); `docs/status.md` aktualisiert. `ui_smoke.mjs` um
Schritt 2g erweitert (Teil wählen → Umschalter erscheint → Feld übersteuern →
▪-Marker + nur dieses Teil veraltet → ↺ + Speichern räumt den Marker →
Ausgrau-Matrix rein/raus; Hooks `__scopeDebug`/`__revisionsDebug`). Viewer
**454 vitest grün** (+30: scope-state 18, shell-structure +13, −1 Assertion der
alten Sektion), tsc + `vite build` clean, `node --check ui_smoke.mjs` grün.
**Headless-CDP hier nicht gelaufen** (braucht Core+Vite+Edge+Projekt) —
Smoke-Schritt nur im Code ergänzt. Offen (Runtime): manueller Durchklick +
Headless-Lauf am Gerät.

---

## 2026-07-07 — Platzierung sichtbar: Basis-Marker aller Teile + M1013-Mesh am Fokus (Issue #93, PRD #88)

**Frage:** Der Core rechnet je Abschnitt eine Platzierung samt Bewertung (ADR-022).
Wie macht der Viewer das Aufstellmuster aller Teile auf einen Blick sichtbar,
ohne ein neues Urteil zu erfinden (ADR-007)?

**Entscheidung:** In der Modellübersicht (Vorbereiten-Modus) erscheinen dauerhaft
**Basis-Marker aller Teil-Platzierungen** vor der Wand; das **fokussierte** Teil
zeigt statt des Markers das **echte M1013-Mesh** (bestehende GLB-Link-Kette des
Trajektorien-Players, #40/#41) in neutraler Pose (`M1013_HOME_RAD`) an seiner
Platzierung. Das Teil-Detail der Teile-Palette (#91) zeigt zusätzlich die
Platzierungswerte (seitl./Abstand/Aufstellhöhe) + erreichbar % + kinematische
Marge — verbatim aus `DecompositionSection.placement`/`status`.

**Alternativen:**
- *Nur den gewählten Job-Marker (#22) lassen* — verworfen: er zeigt eine
  Ganzwand-Platzierung, nicht das per-Teil-Muster (Kernanliegen des PRD). Der
  alte Marker bleibt additiv bestehen (kein Regressionsrisiko), die neuen
  per-Teil-Marker liegen in eigener Gruppe `placement-base-markers`.
- *Mesh je Teil dauerhaft* — verworfen: n Arme = Clutter + Kosten; ein Mesh nur
  am Fokus reicht (Marker↔Mesh-Tausch), die anderen Teile bleiben Marker.
- *Marker-Achse aus der Abschnitts-Box ableiten (`baseMarkerPosition`)* —
  verworfen für kurze Abschnitte (Länge < Dicke): die Längsachse wird **explizit**
  aus `wall.alongX` genommen (`sectionMarkerPosition`), deckungsgleich zu
  `sections.ts`/`cutplanes.ts`.

**Begründung/Umsetzung:** Reine Pose-Mathematik (Marker-Position + Mesh-Basis-Frame
aus Platzierung + Wandmaßen) three.js-frei in
`viewer/src/render/placement-markers.ts` (vitest); die three.js-Objekte dünn
darum herum, der Arm aus der bestehenden `ArmView` (teilt die global geladenen
GLBs, #41). Aufbau über den Fokus-/Modus-Zustand in `main.ts`
(`updatePlacementScene`/`updatePlacementFocusMesh`); im Simulieren-Modus (#86)
und in der Roboter-Vorschau (#31) ruhen Marker/Mesh — Live-Vorschau (#85) und
voller Arm-Lauf bleiben unberührt. Bewertung kommt verbatim aus dem Core
(`parts-palette-state.ts` reicht `kinematic_margin` + Platzierung durch, kein
Viewer-Urteil). Viewer-only, additiv, kein Core-Change.

**Doku:** README-Abschnitt „Platzierung sichtbar …"; `docs/status.md`
aktualisiert. `ui_smoke.mjs` um Schritt 2h erweitert (Marker-Anzahl =
Teile-Anzahl; Fokus ⇒ Mesh sichtbar + Fokus-Marker weicht; Hook
`__placementDebug`). Viewer **465 vitest grün** (+11: placement-markers 8,
parts-palette-state +1, parts-palette +2), tsc + `vite build` clean,
`node --check ui_smoke.mjs` grün. **Headless-CDP hier nicht gelaufen** (braucht
Core+Vite+Edge+Projekt) — Smoke-Schritt nur im Code ergänzt. Offen (Runtime):
manueller Durchklick + Headless-Lauf am Gerät.

---

## 2026-07-07 — Druckplan S5: Freie Platzierungs-Overrides je Teil end-to-end (Issue #94, PRD #88)

**Frage:** Der Platzierungs-Override eines Teils konnte bisher nur eine erfasste
Aufstellmöglichkeit **referenzieren** (`option_id`, #25). Wie trägt er künftig
**freie Werte** (seitliche Position, Abstand, Aufstellhöhe) — end-to-end
(Schema/Setter/API/Core-Bewertung/Viewer), ohne Altprojekte zu brechen, ohne den
Viewer urteilen zu lassen (ADR-007) und ohne die #83-Veraltung zu verletzen?

**Entscheidung:** Der `section_overrides`-Eintrag wird **additiv** um drei
optionale freie Felder (`lateral_mm`/`standoff_mm`/`stand_height_mm`) erweitert;
`option_id` wird optional. Beide Formen **koexistieren** im selben Eintrag: die
freien Werte übersteuern die referenzierte bzw. automatisch gesuchte Basis
**feldweise** (sparse). Persistiert wird über eine **dünne** Route
`PUT /projects/{slug}/placement-override` (Mirror `…/module-limits`/`…/stand-mode`)
und den Setter `set_placement_override_for_job` in `fgc.pipeline.actions`
(Schreiben nur via `fgc.project`, ADR-016). Der Core **bewertet** den freien
Override mit der **bestehenden** `evaluate`-Maschinerie (kein Parallel-Evaluator);
im UI wohnen die Felder im **Teil-Scope des Gilt-für-Umschalters** (#92,
S3-Muster: geerbt dezent = automatischer Wert als Platzhalter, Eingabe =
Override, ↺ zurück auf Automatik).

**Alternativen:**
- *Neuen Override-Typ / zweite Liste neben `section_overrides`* — verworfen: eine
  additive Erweiterung derselben Liste hält Altprojekte byte-gleich und lässt
  Referenz + freie Werte im selben Eintrag koexistieren (feldweise über der Basis).
- *Freie Werte als vollwertige `option_id`=`frei-<id>`-Platzierung ohne Basis* —
  verworfen: nur gesetzte Felder sollen übersteuern; ungesetzte müssen die
  automatische (bzw. referenzierte) Platzierung **erben**. Die Auflösung baut
  daher `frei-<id>` **auf der Basis** und ersetzt nur die gesetzten Felder.
- *Sicherheits-Mindestabstand als Gate (Speichern/Bewerten blockieren)* —
  verworfen (CONTEXT „Befund, kein Gate", wie #77): ein unterschrittener Abstand
  wird als `placement_check`-Befund (`below_min_distance`) im Zerlegungslauf
  gemeldet, blockiert aber nichts. Neuer reiner Helfer
  `fgc.decompose.check_safety_distance`.
- *Platzierungs-Override wie `process`/`cutplan` global veralten* — verworfen
  (#83): er bumpt nur den **Pro-Abschnitts-Zähler** dieses Teils
  (`bump_section_input`) → nur seine Simulation/sein Export veralten. Konsequenz:
  `propose_decomposition` bumpt `cutplan` nur noch bei **struktureller** Änderung
  (Zerlegungsart/Schnitte/Fugen-Versatz); eine reine Override-Änderung bumpt je
  geändertes Teil, eine unveränderte „Prüfen"-Runde bumpt nichts.

**Begründung/Umsetzung:** Zerlegungs-Route und Simulation teilen dieselbe
Override-Auflösung (`_resolve_section_overrides`, `strict`-Flag: Route wirft bei
unbekannter `option_id`, Simulation ignoriert stale still) — nichts dupliziert.
Der ▪-Marker der Teile-Palette zählt jetzt **auch** Platzierungs-Overrides
(`placementOverrideSectionIds`, `main.ts` bildet die Union mit den
Slicing-Overrides). Viewer-Zustand DOM-frei in `placement-override-state.ts`
(vitest), dünne DOM-Anbindung `placement-override.ts`; nach dem Speichern
übernimmt der Schnittplan-Zustand den persistierten Stand
(`replaceSectionOverrides`) und stößt die debounced Neubewertung an — Marker/Mesh
(#93) folgen der Antwort. API-`SectionOverrideModel` sendet freie Felder mit
`exclude_none` (sparse; keine `null` im project.json).

**Doku:** README-Abschnitt „Freie Platzierungs-Overrides je Teil …" (+ #91-Marker
präzisiert); `docs/status.md` aktualisiert. `ui_smoke.mjs` um Schritt 2i erweitert
(Override setzen ⇒ Basis-Marker wandert + ▪-Marker + nur dieses Teil veraltet, ↺
kehrt zur Automatik zurück; Hook `__placementDebug` um Marker-Positionen
erweitert). Core: pytest der betroffenen Suites grün (die einzigen Fehlschläge im
Vollauf waren der bekannte `os.replace`-`PermissionError [WinError 5]` auf
Persistenz-/Reload-Tests — in Isolation grün), `ruff` clean. Viewer **479 vitest
grün** (+14: placement-override-state 10, parts-palette-state +3, cutplan-state +2,
−1 alte Assertion), tsc + `vite build` clean, `node --check ui_smoke.mjs` grün.
**Headless-CDP hier nicht gelaufen** (braucht Core+Vite+Edge+Projekt) —
Smoke-Schritt nur im Code ergänzt. Offen (Runtime): manueller Durchklick +
Headless-Lauf am Gerät.

---

## 2026-07-07 — Zerlegungsart-Weiche Abschnitte↔Module end-to-end (#95, S7; deckt S6/#90 mit; PRD #88, ADR-022)

**Frage:** Wie wird die Zerlegungsart **Modul** (bisher deaktivierte Dropdown-Option
+ `ValueError` im Core) im Viewer funktionsfähig — als *Weiche* Abschnitte↔Module
mit korrekter Artwechsel-Semantik, ohne die bestehenden Abschnitt-Pfade zu stören?

**Entscheidungen:**

- *Prominente Radiogruppe ganz oben in der Rubrik statt Dropdown-Option* —
  gewählt (Issue-Vorgabe): die frühere deaktivierte `<option>` entfällt, die Art
  ist eine sichtbare, gewichtige Weiche. Sie blendet die artspezifischen
  Einstellungen **ausschließlich über `.hidden`** um (Abschnitt → Aufstell-Toggle
  #81; Modul → max. Modullänge/-höhe #90) und schaltet die Beschriftungen
  (Palette „Abschnitte"/„Module", Teil-Namen).
- *Reines Weiche-State-Modul (`zerlegungsart-state.ts`) + dünne DOM-Anbindung* —
  gewählt (Hausmuster, wie `focus-state.ts`/`rubrics-state.ts`): die
  Sichtbarkeitsmatrix (`visibilityFor`) und die Artwechsel-Regeln (`switchArt`)
  liegen DOM-frei und vitest-getestet; `DruckplanPanel` ruft sie nur.
- *Artwechsel EXACT per ADR-022 Punkt 5* — gewählt: Schnittebenen sind
  zerlegungsart-**neutral**; der Wechsel **behält alle Schnitte** und setzt nur
  das bestehende `dirty`-Flag, der debouncte Re-Check bewertet mit der neuen Art.
  **Slicing-Overrides** (`process_params.sections`) **überleben** (stabile
  Section-IDs); **Platzierungs-Overrides** (`section_overrides`) **verfallen** (ein
  Stellplatz am Einbauort ergibt an der Workstation keinen Sinn). Alle drei Regeln
  sind in vitest belegt (`switchArt`) + eine pytest auf der Aktions-/Routen-Seite
  (`test_art_switch_keeps_cuts_survives_slicing_verfaellt_placement`).
- *Kein neuer Core-Pfad für das Räumen der Platzierungs-Overrides* — gewählt
  (ADR-016, „eine Schreibstelle"): der Viewer räumt sie im Panel-Zustand
  (`switchArt` → `sectionOverrides: []`), der ohnehin folgende Re-Check
  (`proposeDecomposition`) sendet die geräumten Overrides + die neue Art und
  **persistiert** sie über `fgc.project` — nichts dupliziert, kein zweiter Setter.
- *max-Maße über die #90-Route (`PUT …/module-limits`), nicht neu erfunden* —
  gewählt: der Setter existiert seit #90 (Mirror von `…/stand-mode`, sparse,
  veraltet keine Outputs); der Viewer bekommt nur die dünne TS-Funktion
  `setModuleLimits`.
- *„modul" ohne Workstation → Hinweis, kein Gate* — gewählt (ADR-022): die
  Workstation *ist* der Druckort; fehlt sie, zeigt die Weiche einen freundlichen
  Hinweis statt zu rechnen (der Core würde 422 werfen — der Panel-Guard fängt es
  vorher ab, kein Absturz). Die Art bleibt wählbar.
- *Modulgewicht + Grenzen-Befund je Teil in der Palette (deckt #90/S6-README mit)*
  — gewählt: bei Art „modul" zeigt jede Palette-Zeile Gewicht (kg) + Grenzen-Befund
  aus dem S6-Artefakt (`DecompositionSection.module_check`, verbatim), **Befund,
  kein Gate**; die Ampeln bleiben unverändert vom Core.

**Erwogene Alternativen:**

- *Dropdown behalten, „modul" nur aktivieren* — verworfen: die Art ist eine
  entscheidende Logikweiche (in place ↔ vorproduzieren), eine versteckte
  Dropdown-Zeile würde ihr nicht gerecht (Issue-Vorgabe: prominente Radiogruppe).
- *Sichtbarkeit über `style.display`* — verworfen (Lehre aus #56, tote-Reiter-Bug):
  ausschließlich `.hidden` (globales `[hidden]{display:none!important}`).
- *Neue Core-Aktion `clear_placement_overrides_for_job`* — verworfen: der Re-Check
  ist bereits die eine Schreibstelle und persistiert `section_overrides` aus dem
  Request; ein zweiter Setter wäre Duplikat (ADR-016).
- *Platzierungs-Overrides über den Artwechsel behalten* — verworfen (ADR-022): ein
  Stellplatz am Einbauort ist an der Workstation sinnlos; sie verfallen.
- *Schnittplan beim Artwechsel verwerfen* — verworfen (ADR-022, ADR-017-Geist):
  destruktiv; die Schnitte sind zerlegungsart-neutral und bleiben.

**Doku:** README-Abschnitt „Modul-Zerlegung — Zerlegungsart-Weiche Abschnitte↔Module"
(deckt **S6/#90 und S7/#95** ab; die #90-README war hierher zurückgestellt); Hinweis
an der `/decomposition`-API präzisiert (modul rechnet jetzt, 422 nur ohne
Workstation); `docs/status.md` aktualisiert. `ui_smoke.mjs` um Schritt 2j erweitert
(Artwechsel: Schnitte bleiben, dirty, Sichtbarkeitsmatrix kippt, Gewicht sichtbar;
`node --check` grün). Viewer **495 vitest grün** (+16: zerlegungsart-state 16,
parts-palette-state +2, parts-palette +2, −1 alte Namens-Assertion), tsc + `vite
build` clean. Core: pytest der betroffenen Suites grün, `ruff` clean; im Vollauf war
der **einzige** Fehlschlag der bekannte `os.replace`-`PermissionError [WinError 5]`
auf einem Persistenz-Test (unter Last) — in Isolation grün. **Headless-CDP hier
nicht gelaufen** (braucht Core+Vite+Edge+Projekt) — Smoke-Schritt nur im Code
ergänzt. Offen (Runtime): manueller Durchklick + Headless-Lauf am Gerät.

## 2026-07-07 — Druckplan-Neuordnung II S8: Druckort — Core Modul-Pose + Druckort-Ansicht Einbauort↔Workstation (#96, PRD #88, ADR-021/022)

**Frage:** Wie wird der **Druckort** der Modul-Fertigung sichtbar — die Lage des
Moduls auf der Arbeitsfläche der Workstation aus der Platzierungs-Relativpose
berechnen (Invertierung der Leserichtung, ADR-022) und im Viewer als
Ansichts-Umschalter Einbauort↔Druckort zeigen — ohne eine zweite
Frame-/Quaternion-Konvention und ohne die Abschnitt-Pfade anzufassen?

**Entscheidungen:**

- *Neues reines Core-Modul `fgc.decompose.module_pose`* — gewählt (Hausmuster
  `limits.py`): kein I/O, keine Kinematik; `module_pose(placement, base, surface)`
  rechnet `T_ws←modul = T_ws←basis ∘ T_modul←basis⁻¹` (ADR-022 Punkt 2 wörtlich:
  der Roboter steht, das Modul liegt vor ihm — dieselbe Relativpose, invertiert
  gelesen), dazu `on_surface` relativ zur Arbeitsfläche. Damit bekommen die
  ADR-021-Frames (`robot_base_frame`/`work_surface_frame`) ihren **ersten
  Konsumenten** — die Naht aus #77/#79 ist geschlossen.
- *Frame-Algebra ausschließlich aus `fgc.simulation.transform`* — gewählt
  (ADR-006, eine Transformationsstelle): `compose`/`invert`/`quat_normalize`
  wiederverwendet, `placement_frame` bildet exakt die `placement.evaluate`-
  Konvention (`_rot_z(yaw)` + Translationsvektor) als Quaternion-Frame ab —
  keine zweite Konvention, kein NumPy nötig.
- *Roundtrip als Testorakel* — gewählt (Akzeptanzkriterium):
  `placement_from_pose` rekonstruiert die Relativpose exakt aus der
  Arbeitsflächen-Lage (`T_modul←basis = (T_ws←flaeche ∘ on_surface)⁻¹ ∘
  T_ws←basis` — die Frames kürzen sich); pytest prüft den Roundtrip auch mit
  gedrehten UND gekippten Frames (die Rekonstruktion ist frame-unabhängig, weil
  die Kette exakt den Platzierungs-Frame übrig lässt).
- *Modul liegt vor der Basis entlang deren −y-Achse* — dokumentierte Konvention
  (Docstring): die Relativpose trägt keine Azimut-Information, wo die
  Arbeitsfläche um die Basis liegt; die invertierte Lesung setzt das Modul dahin,
  wo bei „abschnitt" die Wand stünde (Basis bei +y vor der Modulfront). Mit den
  Frames aus `_module_placement` (#90) landet der Modulfuß exakt auf
  Arbeitsflächenhöhe (pytest belegt z=0 end-to-end).
- *`module_pose` additiv je Teil in Lauf + Antwort, nur bei Frames* — gewählt
  (Muster `module_check` #90/`placement_check` #94): `pose_plan` je Teil (Teile
  mit Platzierungs-Override #94 bekommen ihre eigene Lage); ohne Frames
  (Altbestand, ADR-021 optional) fehlt das Feld und der Lauf bleibt byte-gleich
  (pytest). Schema-`$defs` `frame`/`module_pose` ergänzt, Art „abschnitt"
  unverändert (Golden grün).
- *Reiner Druckort-View-State (`druckort-state.ts`) + reine Szenen-Spec
  (`druckort-spec.ts`) + dünnes Umblenden in `main.ts`* — gewählt (Hausmuster
  `focus-state`/`placement-markers`): Umschalt-Logik (nur am **fokussierten
  Modul**, bei Abschnitten kein Umschalter; `reconcileDruckortView` fällt bei
  Fokus-/Art-/Modus-/Reiterwechsel sauber auf Einbauort zurück) und
  Szene-oder-Hinweis (`druckortSceneSpec`: Roboter-Anker, Modul-Rechteck-Maße,
  Mesh-Quelle) sind DOM-/three.js-frei und vitest-getestet (24 neue Tests).
- *Eigene z-hoch-Gruppe neben `world` statt Umbau der Weltgruppe* — gewählt
  (Muster `robotPreview` #31): die Druckort-Szene lebt in `druckort-szene`
  (Workstation-Mesh via `loadToolMesh` + Sequenz-Guard, M1013-`ArmView` an
  `robot_base_frame`, Modul-Quader an `module_pose.workstation` verbatim);
  Umblenden nur über `visible`, der Rückweg stellt den gemerkten Kamerastand
  der Wand-Ansicht weich wieder her — beide Fahrten über die bestehende
  #84-Tween-Mechanik (`startCameraTween`, easeInOutCubic), kein zweiter Tween.
- *Fehlende Voraussetzungen → Hinweis statt Ansicht* — gewählt (ADR-013-Geist,
  Issue-Vorgabe): keine Workstation / keine Frames (Altbestand) / kein
  `module_pose` im Lauf (Altlauf, einmal „Prüfen") zeigen je einen klaren
  Hinweis am Umschalter und bleiben in der Wand-Ansicht — Befund, kein Gate,
  nie eine kaputte Szene.

**Erwogene Alternativen:**

- *Modul-Pose im Viewer rechnen* (er hat die Frames + Platzierung ja) —
  verworfen (ADR-007): die Lage ist Fachurteil-nah und gehört als Artefakt in
  den Lauf; der Viewer rechnet nur Darstellungsformen (Frame→4×4, Box-Maße).
- *Pose in `_module_placement`/propose einbauen statt eigenem Modul* —
  verworfen: `propose` plant (Raster/Platzierung), die Lage ist eine reine
  Ableitung daraus; ein eigenes tiefes Modul hält den Roundtrip isoliert testbar.
- *Nur `on_surface` (oder nur `workstation`) ins Artefakt* — verworfen: der
  Viewer braucht Workstation-Mesh-Koordinaten (dort leben Mesh + Roboter), der
  Roundtrip-Vertrag die Arbeitsflächen-Sicht; beide sind dieselbe Pose, zweimal
  ausgedrückt — keine Redundanz-Falle, weil beide aus einer Rechnung stammen.
- *Druckort als eigener Szenenmodus in `scene-mode.ts`* — verworfen: der Modus
  hängt am Reiter, die Druckort-Ansicht am Fokus-Teil — ein Zustand im
  Druckplan (wie `planMode`), kein Reiter-Mapping.
- *Kamera per `fitTo` hart springen* — verworfen (Issue-Vorgabe „weiche
  Kamera-Einfassung"): beide Richtungen fahren über den #84-Tween.

**Doku:** README-Abschnitt „Druckort sichtbar — Modul-Pose (Core) +
Druckort-Ansicht Einbauort↔Workstation"; `docs/status.md` aktualisiert;
`ui_smoke.mjs` um Schritt 2k erweitert (Modul fokussieren → Druckort → Roboter
+ Modul sichtbar → zurück; toleriert den Frame-Hinweis-Pfad; `node --check`
grün). Core: `pytest tests/test_module_pose.py` (11 Tests, Roundtrip-Orakel) +
`test_decompose.py` erweitert (module_pose end-to-end mit/ohne Frames), `ruff`
clean; im Vollauf (600 grün) fielen ausschließlich 6 Persistenz-/Placement-/
Simulations-Tests mit dem bekannten `os.replace`-`PermissionError [WinError
5]`-Flake (Maschine unter Last) — alle 6 in Isolation grün. Viewer **519 vitest grün** (+24: druckort-state 14,
druckort-spec 10), tsc + `vite build` clean. **Headless-CDP hier nicht
gelaufen** (braucht Core+Vite+Edge+Projekt) — Smoke-Schritt nur im Code
ergänzt. Offen (Runtime): manueller Durchklick + Headless-Lauf am Gerät.

---

## 2026-07-07 — Druckplan-Neuordnung II S9: Modul-Simulation — Fokus-Modul am Druckort + „Alle Module" (#97, PRD #88, ADR-022 §6) — SCHLIESST PRD #88

**Frage:** Wie wird der Simulieren-Modus (#86) artabhängig, sodass Module am
**Druckort** (Workstation-Bühne S8/#96) statt in place simuliert werden — „Fokus-
Modul simulieren" + „Alle Module" statt „Fokus-Abschnitt" + „Ganze Wand" — ohne
neue Kinematik und ohne den Abschnitt-Modus zu verändern?

**Entscheidung:**

- *Reine Beschriftungs-/Sequenzlogik in der bestehenden `druckplan-mode`-Schicht
  erweitert* — gewählt (Hausmuster, Issue-Vorgabe): `focusSimLabel`/
  `sequenceSimLabel` (+ Tooltips + Hinweise `focusSimHint`/`sequenceSimHint`)
  und `simPlaysAtDruckort(kind)` liegen DOM-frei neben `focusTarget`/
  `staleSimSections`. **Kein** paralleles Modus-Modul. `simulation.ts` weist die
  Strings 1:1 zu (`setKind`), `main.ts` schaltet nur die Venue.
- *Abschnitt-Modus bit-identisch* — gewählt (Regressionstest): die Abschnitt-
  Zweige der neuen Funktionen liefern **wörtlich** die alten Strings aus
  index.html/`simulation.ts` (Knopf-Labels, Tooltips, alle drei Fokus-Hinweise,
  alle drei Sequenz-Hinweise). Ein `describe`-Block „Abschnitt-Modus bleibt
  bit-identisch (Regression)" friert sie ein.
- *„Alle Module" reusest die S8-Bühne + DIESELBE `TrajectoryPlayer`-Instanz* —
  gewählt (Issue-Vorgabe, ADR-007): `startModuleReplay` baut die Druckort-Szene
  (`buildDruckortScene` aus #96) und treibt `trajectoryPlayer` über
  `buildSequencePlan`/`locateSequenceTime` (dieselbe Zeitachse wie die Abschnitts-
  Sequenz #27). Je Schritt wird das **Modul auf der Arbeitsfläche durchgetauscht**
  (Bühne am nächsten Modul neu gebaut), der feste M1013 fährt die Bahn per
  `interpJoints` am `robot_base_frame`-Anker — reine Darstellungsmathematik, der
  Transform kommt aus der **S8-Modul-Pose** (#96), **keine neue Kinematik**.
- *Venue-Weiche in `main.ts` statt im Panel* — gewählt: `onOpenRun`/
  `onPlaySequence` prüfen `simPlaysAtDruckort(getKind())` → Module gehen zu
  `playModuleRunAtDruckort`/`startModuleSequenceAtDruckort`, Abschnitte
  unverändert zu `openSectionRun`/`startSequence`.
- *`syncDruckort` respektiert den laufenden Replay* — gewählt: während eines
  Modul-Replays (`moduleReplay !== null`) lässt der #96-Zustandsautomat die
  Bühne in Ruhe; `teardownModuleReplay` (Rückweg „Zurück zur Übersicht",
  Moduswechsel auf Vorbereiten, Projekt-/Wandwechsel) stellt die Wand-Ansicht
  weich wieder her.

**Erwogene Alternativen:**

- *Montage-Simulation am Einbauort (Kran/Fügen in die Wand)* — **out of scope**
  (PRD #88, ADR-022 §6): Druckreihenfolge *ist* Montagereihenfolge (unten→oben,
  links→rechts), keine Umsortier-Funktion in v1. Nur die Druck-Wiedergabe am
  Druckort, nicht das Einbauen.
- *Zweite Player-Instanz/eigener Modul-Sequenz-Renderer* — verworfen (Issue-
  Vorgabe „dieselbe TrajectoryPlayer-Instanz"): die Bühne (`druckortGroup`/
  `druckortArm`) und die reine Sequenz-Zeitachse (#27) werden wiederverwendet.
- *Trajektorie am Druckort neu rechnen (Transform der IK)* — verworfen (ADR-007):
  der Viewer rechnet nichts; die Gelenke der Core-Bahn spielen am festen
  Workstation-Roboter, das Modul liegt an der #96-Pose (Anzeige-FK).
- *Labels im DOM/index.html statisch belassen und nur umschalten* — verworfen:
  die Strings sind Beschriftungslogik → in die getestete `druckplan-mode`-Schicht,
  `simulation.ts` setzt `textContent`/`title` daraus.

**Doku:** README-Abschnitt „Modul-Simulation — Fokus-Modul am Druckort + „Alle
Module""; `docs/status.md` aktualisiert (**PRD #88 komplett**, #89–#97 done);
`ui_smoke.mjs` um **Schritt 2l** erweitert (Art „modul" → Simulieren → „Alle
Module" sichtbar → „Fokus-Modul simulieren" spielt am Druckort; `__moduleSimDebug`;
toleriert fehlende Core-API/Module über den Beschriftungs-Zweig; `node --check`
grün). Viewer **528 vitest grün** (+9: artabhängige Simulieren-Knöpfe inkl.
Abschnitt-Regression), tsc + `vite build` clean. **Headless-CDP hier nicht
gelaufen** (braucht Core+Vite+Edge+Projekt) — Smoke-Schritt nur im Code ergänzt.
Offen (Runtime): manueller Durchklick + Headless-Lauf am Gerät.

## 2026-07-07 — Viewer-Overlays an der echten Wand-Pose statt Bbox-Näherung (Issue #99)

**Frage:** Warum liegen die Schnittebenen/Abschnitts-Quader schräg zur Wand
(Nutzer-Screenshot: „Ebenen so schräg gezogen", violetter Fokus-Quader ragt
diagonal aus der Wand)?

**Befund:** Der Core schneidet korrekt im PCA-Wandframe (`_wall_local_mesh`,
ADR-006) — aber alle Viewer-Overlays (cutplanes/sections/placement-markers/
basemarker/prepare-preview) näherten das Wand-System über die **achsparallele
Bounding-Box** („Längsachse = größere horizontale Ausdehnung"). Bei einer Wand,
die gedreht zu den Weltachsen steht, liegen die Overlays dadurch schräg zur
Wand und sind zu lang (Bbox = Diagonale).

**Entscheidung:** Neues Modul `viewer/src/render/wall-frame.ts`: 2D-PCA der
Wand-Vertices im Grundriss, **exakt die Core-Konvention** inkl. deterministischem
Vorzeichen-Fixup (Komponentensumme der Achse ≥ 0) — damit Schnittpositionen und
Abschnittsgrenzen vorzeichenrichtig auf der echten Wandachse landen. Nullpunkt =
Vertex-Mittel (dort leben die Core-Schnitte, `decompose.apply`), Extent-Mitte
separat für Spannweiten. Die Overlay-Gruppen hängen an `origin`+`yaw`
(`applyWallFrame`), die Spec-Funktionen rechnen rein **Wand-lokal** — die alte
`alongX`-Fallunterscheidung (0° oder 90°) entfällt als Spezialfall des yaw.
Drag-Achsen der Schnittebenen (#25) werden durch die Wand-Pose in den Weltraum
transformiert; das Drag-Handling in `main.ts` war bereits rotationsfest
(`getWorldQuaternion`).

**Erwogene Alternativen:** (a) Wand-Pose vom Core als Artefakt mitliefern —
sauber, aber neue API-/Schema-Fläche für reine Darstellung (ADR-007: der Viewer
rechnet Darstellungsmathematik selbst); verworfen für v1, PCA im Viewer ist
deterministisch dieselbe Konvention. (b) `IfcLocalPlacement` der Wand nutzen —
verworfen: der Core nutzt es auch nicht (PCA ist die kanonische Quelle beider
Seiten). `baseMarkerPosition`/`placeBaseMarkerInBox` bleiben Box-basiert: die
Aufstell-Sequenz (#27) speist sie mit Wand-lokalen Boxen aus Toolpath-Targets —
dort ist achsparallel korrekt.

**Doku/Verifikation:** README (Zerlegungsvorschlag Punkt 4). Neue reine
PCA-Tests (`wall-frame.test.ts`: gedrehte Wand → yaw exakt, Länge ≠ Diagonale,
Vorzeichen-Fixup, degenerierte Eingaben, Mesh-Traversal); Spec-Tests auf
Wand-lokal umgestellt. Viewer 534 vitest + tsc grün. Headless-Smoke: 8
Fehlschläge **identisch auf sauberem HEAD** (vorbestehend, veraltete
Core-API-Instanz auf 8765 vermutet) — keine Regression durch #99.

## 2026-07-07 — Platzierungs-Tiebreak: Min-Marge vor Mean-Marge + Zentrums-Präferenz (Issue #98)

**Frage:** Warum stellt die Platzierungssuche den Roboter seitlich versetzt
(seitl. 313 mm), obwohl zentriert die ferne Ecke deutlich robuster erreichbar
wäre (Nutzer-Screenshot: Ecke wird „nicht erreicht", 9 Warnungen)?

**Befund:** Sortierkriterium war `(reachable_fraction, mean_margin)`. Bei voll
erreichbaren Kandidaten entschied die **mittlere** Marge — seitlich minimal
besser (0,036 vs 0,035), während die ferne untere Ecke bei ≈ 1275 mm von
1300 mm Reichweite (M1013) lag: Worst-Case massiv schlechter, floss aber nicht
ein.

**Entscheidung:** Sortierung `(reachable_fraction, kinematic_margin,
mean_margin, −|lateral|)` — voller Anteil, dann beste **Min-Marge** (die
schlechteste Stelle entscheidet), dann Mean, bei exaktem Gleichstand die
zentrale Lage. `kinematic_margin` existierte bereits im Score (#22) — nur das
Auswahlkriterium ändert sich; weiterhin deterministisch (ADR-004-Geist).

**Erwogene Alternativen:** Nur Zentrums-Präferenz ohne Min-Marge — verworfen:
behebt den Fallback-Fall, aber nicht die Abstands-Achse mit Workstation (#80),
die dasselbe Mean-vs-Worst-Case-Problem hat.

**Doku/Verifikation:** README (Optimalvorschlag), Test
`test_suggest_tiebreak_prefers_worst_case_margin_then_center`; bestehender
#80-Abstands-Test auf das neue Kriterium geschärft. Core 609 pytest + ruff grün.

## 2026-07-07 — Aufstell-Toggle gilt auch im Workstation-losen Fallback (Issue #100)

**Frage:** Warum steht der Roboter auf 500 mm Podest, obwohl der Aufstell-Toggle
(Default `floor` in `propose_decomposition`) auf Boden steht?

**Befund:** `stand_mode` (#81) wurde nur in `_workstation_heights` angewendet —
das Altprojekt-Fallback-Raster (`_fallback_grid`, ohne Workstation am Druckjob)
suchte immer 0–3000 mm Höhe.

**Entscheidung:** `stand_mode` an `_fallback_grid` durchreichen: `floor` →
Höhenkandidaten `[0]`, `elevated` → bisheriges 500-mm-Raster. Konsistent mit dem
Workstation-Pfad; `suggest`-Default bleibt `elevated` (bestehende Aufrufer wie
der Singularitäts-Advisor unverändert).

**Doku/Verifikation:** README (Optimalvorschlag Fallback + Aufstell-Toggle),
Tests `test_suggest_fallback_floor_mode_clamps_height` /
`…_elevated_mode_keeps_height_grid`.

## 2026-07-07 — UI-Redesign: Handoff-Paket → Issue-Schnitt #101–#109

**Frage:** Wie wird das Design-Handoff `docs/design/design_handoff_ui_redesign/`
(Redesign des Viewers: Tokens/IBM Plex/Themes, Header+Stepper, Druckplan-Split
in eigene Prozess-Schritte „Zerlegung" und „Slicing", ⌘K-Palette) abgearbeitet —
direkt in einer Session, massiv parallel (Ultracode), oder als Issue-Kette?

**Erwogene Alternativen:** (a) Eine große Implementier-Session — verworfen:
8 Scheiben über praktisch alle Viewer-Dateien, hohes Session-Limit-Risiko ohne
Wiederaufsetzpunkt (Lehre aus #25). (b) Parallel per Multi-Agent-Workflow —
verworfen: die Scheiben schreiben in dieselben Dateien (style.css, main.ts,
shell.ts) und hängen voneinander ab; Parallelisierung brächte Merge-Konflikte
statt Tempo. (c) `/to-issues` + sequenzieller issue-orchestrator — gewählt.

**Entscheidung:** 9 Issues #101–#109 (`ready-for-agent`), 1:1 nach den
Handoff-Scheiben mit EINER Abweichung: Scheibe 5 ist geteilt in #107
(Slicing-Reiter + 5-Schritt-Routing) und #108 (Simulations-Dock) — beides
einzeln demobar, halbiert das dickste Paket. Abhängigkeitskette:
#101 → #102 → #106 → #107 → {#108, #109}; Nebenstränge #103/#104 (⇐ #101)
und #105 (⇐ #102). Bewusste, im Handoff entschiedene Umkehrungen früherer
Entscheidungen — werden bei Umsetzung je mit eigenem Log-Eintrag dokumentiert:
#107 kehrt die Rubriken-Navigation #89 um (Rubriken → eigene Prozess-Schritte),
#108 kehrt die Modus-Fusion #86 um (Modus-Radiogroup → Dock, Veraltet-Schutz
leistet die ADR-017-Markierung).

**Doku/Verifikation:** Handoff-Paket eingecheckt (README + klickbarer Prototyp
+ tokens.css als Spezifikation); status.md aktualisiert. Umsetzung folgt per
issue-orchestrator, schwere Scheiben (#106/#107) mit starkem Modell.

## 2026-07-07 — UI-Redesign Scheibe 1: Design-Tokens, IBM Plex, Theme-Umschalter (Issue #101)

**Start des UI-Redesigns.** Frage: Wie werden die Tokens aus dem Handoff
(`tokens.css`) und der Hell/Dunkel-Umschalter in den bestehenden Viewer-Stack
integriert — ohne HTML-Umbau, offline-tauglich, hausmusterkonform?

**Frage 1 — Schrift offline:** Der Prototyp lädt IBM Plex per Google-Fonts-CDN
(`<link href="fonts.googleapis.com…">`). Der Viewer muss aber offline/
selbstständig laufen (statischer dist-Ordner, kein Netz garantiert).
Alternativen: (a) CDN-Link wie im Prototyp — verworfen, bricht offline und macht
den Build von einem Fremd-Host abhängig. (b) `@fontsource`-npm-Paket —
verworfen, zieht eine Laufzeit-Abhängigkeit + viele Dateien ohne Mehrwert.
(c) **Subsets selbst hosten** — gewählt: die latin-/latin-ext-woff2-Subsets
(Sans 400/500/600/700, Mono 400/500 = 12 Dateien) nach `viewer/src/fonts/`
vendored und per lokalem `@font-face` eingebunden; Vite hasht/bündelt sie in
`dist/assets/`. Begründung: identisches Muster wie das bereits vendored
M1013-Mesh (#40), null Netz-/Laufzeit-Abhängigkeit, `font-display: swap` fällt
bis zum Laden auf „Segoe UI"/system-ui zurück. latin-ext deckt die deutschen/
europäischen Zeichen ab; die Unicode-Glyphen der UI (ⓘ ◐ ▤ …) liegen ohnehin
außerhalb von IBM Plex und fallen sauber auf Systemschriften zurück.

**Frage 2 — Theme-Persistenz/DOM:** Alternativen: (a) `prefers-color-scheme`
automatisch — verworfen, der Nutzer soll bewusst wählen (Handoff: ◐-Toggle).
(b) Theme im `project.json`/Core — verworfen, es ist eine App-Präferenz, kein
Fachzustand (ADR-016 gilt dem Fachzustand). (c) **`localStorage` +
`data-theme` am `<html>`, Logik als reines `ui/theme.ts`** — gewählt, Hausmuster
der `*-state.ts` (wie `collapsible-state.ts`): DOM-/storage-freier Zustand +
`themeView`-Ableitung, vitest-getestet; die dünne Verdrahtung (localStorage
lesen/schreiben, Attribut setzen) in `main.ts`. Default = dunkel; nur
`[data-theme="light"]` überschreibt die Palette. Sichtbarkeit/Look
ausschließlich über Attribut + CSS-Variablen — **kein display-Toggle** (#46).

**Frage 3 — sichtbarer Umschalter jetzt oder in Scheibe 2:** Scheibe 1 baut
kein HTML um; der ◐-Umschalter wohnt laut Handoff im Header (Scheibe 2/#102).
Entscheidung: In dieser Scheibe wird über `window.fgcToggleTheme()`/
`fgcSetTheme()` umgeschaltet (voll funktional + reload-fest, per CDP verifiziert:
dunkel → toggle → hell → localStorage `fgc-theme=light` → Reload bleibt hell);
der Header-Button klemmt sich in Scheibe 2 an dieselbe Funktion. So bleibt die
Scheibe „nur Präsentation", ohne Layout anzufassen.

**Frage 4 — Bestandsregeln mappen:** „schrittweise" (Handoff). In dieser Scheibe
nur der neue `:root`-Block (verbatim tokens.css, hell+dunkel), die Bausteine und
die eindeutig ersetzbaren Literale (`#1a120b`/`#10151b` → `var(--accent-fg)`,
Mono-Readout → `var(--font-mono)`). Die je-Panel-Farbliterale (`#43a047` usw.)
bleiben, bis die Panels in den Scheiben 3–8 ohnehin umgebaut werden — vermeidet
riskante Massen-Edits ohne visuellen Gegenwert.

**Doku/Verifikation:** README-Abschnitt „Design-Tokens + Theme-Umschalter";
`ui/theme.test.ts` (11 Fälle) grün, Viewer-Suite 545 grün, `tsc`+`vite build`
grün (Fonts landen in `dist/assets/`); Theme-Toggle+Reload live per CDP geprüft.
`ui_smoke.mjs`: 8 vorbestehende Fehlschläge (Platzierungs-Override/section_inputs/
Modulgewicht/Druckort-Frames/cfg-Canvas — Core-/Umgebungs-seitig), identisch mit
und ohne diese Scheibe (per Stash-Baseline gegengeprüft) — diese Scheibe fügt
keinen neuen Fehler hinzu.

## 2026-07-07 — Grill-Session: Ortsaufgelöste Porosität (φ-Feld), Infill, LLM-Anbindung kiconnect

**Kontext:** Wunsch: Slicing-Einstellungen (Infill-Muster, Winkel, Geschwindigkeit)
per LLM (kiconnect/RWTH) steuern; zusätzlich sollen Wandbereiche unterschiedliche
Porosität bekommen, gemappt auf die Endeffektor-AOs. Befund vorab: `Target` trägt
schon heute `io`-Kanalwerte je Bahnpunkt (ADR-011), der DRL-Emitter setzt AOs per
Change-on-Delta; aber kein Infill, kein φ-Feld, Pumpenwerte konstant 0.5/0.5,
`materials/` leerer Stub, Spike S1 (AO-Rampen während movel) offen.

**Frage 1 — Scope-Schnitt:** Alternativen: PRD #68 erweitern / nur Domäne, LLM
später / **zwei PRDs, Domäne zuerst** — gewählt. Porosität+Infill werden ein
eigenes Domänen-PRD (deterministisch, ohne LLM lauffähig); PRD #68 bleibt klein
und bekommt später nur zusätzliche Tools auf die neuen Parameter. Bestätigt die
#68-Abgrenzung („Porosität ist eigenes Domänen-Thema").

**Frage 2 — Physik der Porosität:** Porosität = **Pumpen-Mischverhältnis zweier
Komponenten** (pump_a/pump_b), kontinuierlicher Skalar → AO-Spannungen.
Alternativen (mehrere unabhängige Kennlinien, diskrete Rezepturstufen) verworfen.

**Frage 3 — Feld vs. Punkte:** Die Porosität trägt **nicht** der Druckpunkt,
sondern ein **Porositätsfeld (φ-Feld)** im Wand-Koordinatensystem; der Slicer
tastet es beim Erzeugen jedes Targets ab (Grasshopper-Attractor-Muster).
Begründung: Feld bleibt gültig bei Re-Slice mit anderen Parametern; für ein LLM
beschreibbar, ohne tausende Punkte anzufassen. Punkt-Overrides (zweite
Wahrheitsquelle) verworfen.

**Frage 4 — Feld-Repräsentation:** Geordnete Liste von **Feld-Features** unter
einem gemeinsamen Interface „φ an Punkt p?": v1 deklarative Bausteine (Basiswert,
Box/Zone, Höhenband, Gradient), Schema hält Feature-Typ `grid` offen für den
späteren **Ansys/FEM-Import** (FEM-Ergebnis → Umrechnungsregel → Rastergrid als
ein Feature unter demselben Dach). Voxelgrid-only und Formel/Expression verworfen.

**Frage 5 — Kombination:** **Maler-Modell** — Auswertung in Listenreihenfolge,
späteres Feature überschreibt frühere in seinem Geltungsbereich. Minimum-gewinnt
und gewichtete Mischung verworfen (nicht übersteuerbar bzw. nicht vorhersagbar).

**Frage 6 — φ→Pumpen-Kalibrierung:** Lebt in der **MaterialCard**
(`materialcards/`, analog Prozessfenster-Karte: die eine Quelle): Stützstellen-
Tabelle φ → Anteile (share_a, share_b), linear interpoliert; Slicer rechnet
Gesamtstrom aus v_print × Strangquerschnitt und teilt nach Anteilen auf. Startet
`provisional` mit 2 Stützstellen. Hartkodiert-linear und Kennlinie-im-Endeffektor
verworfen (Mischverhältnis ist Material-, nicht Werkzeugeigenschaft).

**Frage 7 — räumliche Auflösung / Spike S1:** **Segmentierung, stufenweise
konstant**: Slicer unterteilt lange Züge auf `phi_target_resolution_mm` (Feld
existiert schon in der Prozessfenster-Karte, bisher null), je Teilstück eine
Feld-Abtastung; Emitter schaltet an Stückgrenzen (kann er schon). Unabhängig vom
S1-Ausgang; fällt S1 positiv aus, sind Rampen ein reiner Emitter-Upgrade.

**Frage 8 — Totzeit:** v1 **ohne** t_tot-Kompensation der Schaltpunkte; der
erwartete Ortsversatz (t_tot × v) wird ehrlich als Kennzahl ausgewiesen.
Kompensation als eigenes Issue, sobald gemessene t_tot-Werte existieren.

**Frage 9 — Infill vs. φ:** Getrennt: das φ-Feld steuert v1 **nur das Material**
(Mikro-Porosität); **Infill** (Makro-Porosität) wird normaler Slice-Parameter im
bestehenden Override-Mechanismus (global/Abschnitt). Feld-gesteuerte Infilldichte
bleibt als Ausbaustufe im Schema angelegt, v1 baut sie nicht.

**Frage 10 — Infill-Scope v1:** Ein Muster: parallele Linien als durchgehender
**Zickzack** (druckfreundlich, keine Abrisse), Parameter Linienabstand, Winkel,
optional alternierend je Schicht — hinter einer Muster-Schnittstelle
(Region → Polylinien). **Custom-Infills per LLM**: mittelfristig als deklarative
Muster-DSL (LLM emittiert Beschreibung, deterministischer Interpreter zeichnet,
geometrisch validiert + Viewer-Preview); langfristige Vision LLM-generierter
Muster-Code (sandboxed) — braucht dann ein eigenes ADR, jetzt kein Arbeitspaket.

**Frage 11 — semantische Referenzen:** Feld-Features dürfen **beides**: absolute
Primitive im Wand-Frame **und** semantische Bezüge („um Öffnung <GlobalId>,
Randbreite r", „Sockel h"), die der Core beim Slicen gegen die Wandgeometrie
auflöst. Robust gegen Modelländerungen, und das LLM spricht wie der Nutzer denkt.

**Frage 12 — kiconnect:** OpenAI-kompatibler Endpunkt ⇒ **nur eine
Provider-Konfiguration** (Base-URL + API-Key) im Sinne von PRD #68, kein
Sondercode. Zu verifizieren beim Umsetzen: Tool-/Function-Calling des dortigen
Modells (sonst JSON-im-Text-Fallback).

**Frage 13 — LLM-Gating:** **Vorschlags-Modus, flüchtig im Chat**: das LLM-Tool
liefert den validierten Parameter-/Feld-Block nur als Vorschau zurück; der Chat
rendert „Übernehmen", erst der Klick ruft die normale Aktion (ADR-014/016/017
greifen dann wie immer). Kein persistenter Entwurfs-Zustand (verworfen: zweiter
Zustandspfad in project.json). Direkt-Schreiben verworfen (Nutzerwunsch:
Bestätigung im Chat).

**Konsequenzen:** φ-Feld persistiert als Teil der `process_params` im Druckjob
(ADR-016), Änderungen bumpen die Prozess-Revision (ADR-017). Viewer zeigt φ als
Farbkodierung der Targets aus `toolpath.json` (reines Abspielen, ADR-007). LLM
braucht Lese-Tools (Wandmaße, Öffnungen mit GlobalIds, aktuelle Parameter), damit
es Zonen platzieren kann. ADR-023 (Porositätsfeld) vorgeschlagen; PRD-Schnitt:
(1) Domäne φ-Feld+Infill, (2) LLM-Assistent-Erweiterung auf die neuen Parameter.

## 2026-07-07 — UI-Redesign Scheibe 2: Header mit Stepper statt Tabbar (Issue #102)

**Frage:** Wie ersetzt die zweite Scheibe des UI-Redesigns die Tabbar + die
Active-Job-Bar durch den einen 50px-Header des Prototyps, ohne die Tab-Logik
oder das Fachverhalten anzufassen — insbesondere: woher kommen die
Status-Punkte des Steppers?

**Entscheidung:**

- **Ein Header** (`#app-header`) verschmilzt `#tabbar` + `#active-job-bar`
  (beide entfernt): links Logo-Kachel + Projektname (Klick → Projektliste),
  Druckjob-Chip als Pill (ersetzt die Active-Job-Bar, Issue #19), Mitte der
  Stepper, rechts Suchfeld-Attrappe + Theme-◐ + Bibliothek-▤. Maße/Farben/Typo
  verbatim aus dem Prototyp (`FGC-Planner Prototyp.dc.html`), über die Tokens
  aus Scheibe 1. Sichtbarkeit weiterhin nur über `.hidden` (Lehre #46/#56).
- **Stepper-Status-Punkte aus der bestehenden Veraltet-Ableitung, nichts neu
  gerechnet:** Ein Schritt bindet über ein optionales `output` an eine
  Output-Stufe von `ui/staleness.ts`; die Farbe folgt `allStageStatuses`
  (amber = `stale`, sonst grün), der aktive Schritt sticht als Akzent aus.
  Schritte ohne Output (Projekt/Roboter — Eingabestufen, keine veraltbaren
  Ausgaben) gelten stets als aktuell. **Verworfen:** die Punktfarbe im Prototyp
  aus separaten Flags (`s.dirty`/`s.staleSim`/`s.staleExport`) neu abzuleiten —
  das dupliziert die Python↔TS-Paritätslogik. `staleness.ts` bleibt
  unangetastet.
- **Erweiterbare Schrittliste als reines Modul:** `ui/stepper-state.ts`
  (`PROCESS_STEPS` Daten + `stepperView`, vitest-getestet wie die anderen
  `*-state.ts`) bildet in dieser Scheibe die vier Prozess-Reiter ab (Druckplan =
  **ein** Schritt). Die 5-Schritt-Aufteilung Zerlegung/Slicing der Folge-Issues
  (#106/#107) ist als Datenänderung vorgesehen — der Test deckt die 5er-Liste
  bereits ab. Die **Bibliothek ist bewusst kein Stepper-Schritt** (Stammdaten
  außerhalb des Prozesses) und wird über das ▤-Icon erreicht.
- **Theme-◐ bedient das Modul aus Scheibe 1**, kein zweiter Mechanismus: der
  Header-Klick ruft über eine Shell-Callback `fgcToggleTheme()` (ui/theme.ts);
  `main.ts` spiegelt Zustand + Tooltip + `aria-pressed` per `shell.setThemeToggle`
  zurück (Boot-Sync + nach jedem Toggle).
- **Suchfeld ist eine Attrappe** (ohne Funktion) bis zur ⌘K-Palette (Scheibe 6,
  Issue #109).

**Begründung:** Der Stepper macht den Prozess-Fortschritt (inkl. Veraltung)
sichtbar, ohne ein Gate einzuführen (Reiter bleiben freie Navigation, Tooltip
sagt das). Die Bindung der Punktfarbe an die **eine** vorhandene Ableitung hält
die Veraltet-Semantik an einem Ort (ADR-017) und die Python↔TS-Parität heil.

**Konsequenzen:** `ui_smoke.mjs` an die neue DOM-Struktur angepasst
(Prozess-Reiter über `#stepper [data-tab=…]`, Bibliothek über
`#header-library-btn`) + ein Header-Prüfblock (Header ersetzt Tabbar/Job-Bar,
vier Schritte mit je einem Punkt, Job-Chip/Projektname/◐/▤ vorhanden, ◐ kippt
`data-theme`). Viewer-Tests 557 grün (12 neu in `stepper-state.test.ts`),
`tsc`+`vite build` sauber; Smoke unverändert bei den 8 vorbestehenden
Core/Umgebungs-Fehlschlägen, alle neuen Header-Prüfungen grün.

## 2026-07-08 — Grill-Session: Roboter-Livesteuerung über ROS2 (Vorentscheidungen, vor Spike)

**Frage:** Ist eine Livesteuerung des Druckprozesses aus dem Tool heraus
(statt Datei-Export) realistisch, und wie wäre sie zu schneiden? Betrifft
ADR-004 (dateibasierte Pipeline) und die bisher ausgeklammerte Online-Regelung.

**Entscheidungen (Grill-Interview, noch kein PRD):**

- **Zielbild gestuft:** v1 = Streaming + Monitoring (Plan bleibt vorberechnet),
  Closed-Loop-Regelung als Langfristziel. Verworfen: nur Remote-Start.
- **Roboter-Scope:** v1 nur Doosan M1013 (offizieller `doosan-robot2`-Treiber);
  KUKA später — Streaming-Schnittstelle im Core deshalb roboterneutral schneiden
  (analog Toolpath↔Trajectory-Split). Hardware-Zugang: regelmäßig, vor Ort.
- **ROS2 ist gesetzt (Zweck, nicht Mittel):** Sensor-Ökosystem für späteres
  Closed-Loop + Anschlussfähigkeit. Verworfen: DRL-Socket-Streaming ohne ROS
  (wäre billiger, trägt aber das Langfristziel nicht).
- **Topologie:** dedizierter Linux-Rechner am Roboter als „Druckserver"
  (ROS2-Stack + Bridge). Verworfen: WSL2/Docker auf dem Windows-PC
  (DDS-Discovery-Bastelei), ROS2 nativ auf Windows (ungetestet).
- **Schnittstelle:** Core-API bleibt einziger Ansprechpartner des Viewers
  (ADR-007/014 intakt); Core bekommt Bridge-Client und relayt Telemetrie per
  WebSocket. Jeder Live-Druck erzeugt einen regulären Laufordner mit
  As-Run-Telemetrie → ADR-004 überlebt den Livemodus.
- **Streaming-Modell:** segmentweise Bewegungs-Goals (z. B. pro Layer/Segment);
  die Bridge setzt Pumpen-AO selbst synchron zum Fortschritt → IO-Hoheit beim
  PC, OD-1/Spike S1 wird dadurch neu gestellt (Latenz der IO-Service-Calls
  statt bahnsynchrone Controller-AOs). Pumpen hängen an AO/DO des
  Doosan-Controllers (ADR-011-Mapping bleibt gültig). Verworfen: ganze Bahn als
  ein Goal (Sackgasse Richtung Closed-Loop), Servo-Streaming (für v1
  überdimensioniert, Echtzeitrisiko im nassen Lehm).
- **Ausfall-Politik:** Bridge hält den kompletten Druckplan lokal und druckt
  bei Tool-Verbindungsabriss autonom weiter; Tool ist Fernbedienung + Monitor.
  Nur Bridge↔Roboter-Abriss stoppt (Pumpe sofort aus, Arm hält, Zustand bleibt
  für Wiederaufnahme).
- **v1-Scope:** Trockenlauf-Modus (M1: Bahn fahren, IO nur loggen),
  Start/Pause(segmentweise)/Abbruch + Fortschritt/Ist-Gelenke im bestehenden
  Arm-Replay, globaler Speed-/Flow-Override-Regler. Resume nach Absturz → v2.
- **Antast-Gate:** Material-Druck NUR mit `pose_source=measured` (hartes Gate,
  strenger als der Export-Stub heute); Trockenlauf auch mit `planned`, aber
  zwangsweise reduzierte Geschwindigkeit + Warnung — der Trockenlauf ist das
  Werkzeug zur Aufstellungs-Verifikation.
- **Einstieg:** zeitboxter Spike VOR jedem Tool-Code: Doosan-Emulator +
  `doosan-robot2` auf dem Linux-Rechner, Segment-Goals aus einer echten
  `trajectory.json` abspielen, IO-Latenz/Jitter messen (Ziel: ±100–200 ms für
  Lehm ausreichend). PRD + Issues erst nach dem Spike; UI-Redesign #101–#109
  läuft parallel normal weiter.

**Begründung:** Regelmäßiger Roboterzugang macht das Vorhaben realistisch; das
Druckserver-Modell hält das Windows-Tool ROS-frei, bewahrt die ADRs und macht
aus „live" trotzdem Artefakte (As-Run-Protokoll). Bei Architekturrang (Kippen
von ADR-004-Grenzen, neue Systemkomponente Druckserver) folgt ein ADR nach dem
Spike.

**Konsequenzen:** Spike-Ergebnis entscheidet, ob Segment-Goals + IO-Service-
Calls tragen; danach PRD. Spikes S1/S3 werden durch den neuen Spike teilweise
abgelöst bzw. endlich messbar.

## 2026-07-08 — UI-Redesign Scheibe 3: Erklärtexte → ⓘ-Tooltips (Issue #103)

Frage: Die vielen `.hint`-Erklärabsätze in den Prozess-Panels (Projekt,
Roboter, Druckplan, Export) fluten die Fläche. Der Handoff will sie in native
`title=""`-Tooltips neben Überschrift/Label verlagern (`<span class="info">ⓘ</span>`,
Baustein aus Scheibe 1) — mit drei sichtbar bleibenden Ausnahmen.

**Entscheidung — was wandert, was bleibt:**

- **Statische Fließtext-`.hint` → ⓘ-Tooltip** neben der jeweiligen Überschrift
  bzw. dem Label (gekürzt, Fachaussage unverändert). Betroffen: alle Erklär-
  absätze der vier Prozess-Panels (Roboter/Endeffektor/Workstation-Köpfe,
  Modus, Aufstellung, Bewertung, Zerlegungsvorschlag, Schnittplan, Platzierung
  je Teil, Prozessparameter, Anstellwinkel auf die beiden Feld-Labels verteilt,
  Fortgeschritten, Singularitäts-Advisor, Simulieren, Replay, Querschnitts-
  Konsistenz, DRL-Programme).
- **Dynamische `.hint`-Zeilen bleiben** (Status/Empty/API-Warnung/Precondition,
  `arm-render-hint` = Live-Mesh-Status, `zerlegungsart-hint`, `singularity-
  advisor-detail`, `druckort-hint`): keine Fließtexte, sondern vom JS befüllte
  Rückmeldungen. Kein Umbau.
- **Drei sichtbare Ausnahmen (kompakter Stil, Bausteine Scheibe 1):**
  1. „Plan — vor dem Druck antasten" (ADR-006) → schwebender Pill-Chip
     `#plan-chip` unten im geteilten Viewport (Geschwister neben `#viewport` in
     `#tab-body`, `position:absolute`), nur im Reiter Druckplan sichtbar
     (`main.ts onTabChanged`, AUSSCHLIESSLICH über `.hidden` — Lehre aus #56).
  2. Provisorik-/S1-Warnung im Export → kompakte amber `.warn-box` statt Absatz.
  3. „vorläufig"-Badge im Eignungsbericht → unverändert Badge (`panel.ts`,
     `provisional-badge`), kein Eingriff nötig.

**Issue-Nummern raus aus der sichtbaren UI:** alle `#NNN` aus sichtbaren Texten
UND `title=""`-Tooltips entfernt (Überschriften „Zerlegungsvorschlag/Schnittplan/
Singularitäts-Advisor", Button-Titles, ↺-Reset-Titles, Header-Suchfeld, zwei
JS-Titles in `parts-palette.ts`/`robot-library.ts`, Bibliothek-Hinweise); in
HTML-/Code-Kommentaren bleiben sie stehen. Fachaussagen (Ampeln, „Befund, kein
Gate" ADR-013, Veraltet-Markierung ADR-017) wörtlich erhalten.

**Verworfen:** (a) Tooltip-Library (Floating-UI o. ä.) — native `title=""`
reicht, kein Framework (Handoff). (b) `scope-hint`/`placement-override-hint` als
eigene Absätze behalten — stattdessen zu `span.info` mit unveränderter Element-ID
(Struktur-Vertrag `shell-structure.test.ts` bleibt grün); `scope-hint` behält die
bestehende `hidden`-Steuerung (nur im Teil-Scope sichtbar, Parität zum alten
Absatz), `placement-override-hint` wird dauerhaft sichtbarer Marker (die tote
DOM-Anbindung in `placement-override.ts` entfiel, sonst `tsc`-TS6133).

**Doku/Verifikation:** README-Abschnitt „Erklärtexte als ⓘ-Tooltips" ergänzt;
Viewer-Suite 557 grün, `tsc`+`vite build` sauber, `ui_smoke.mjs` unverändert
(interagiert nur über Element-IDs, die alle erhalten blieben — die 8 vor-
bestehenden Core-/Umgebungs-Fehlschläge bleiben, kein neuer). Bibliothek- und
Projektlisten-Erklärtexte bleiben Absätze (außerhalb der Prozess-Panels →
Scheiben 7/8).

## 2026-07-08 — Projektliste mit Karten, Wand-Bilanz-Balken und IFC-Dropzone (UI-Redesign Scheibe 7, Issue #104)

**Frage:** Wie den Startbildschirm (Projektliste) auf das Redesign heben, und
woher die Segmente des Wand-Bilanz-Balkens nehmen, ohne die Klassifikation neu
zu rechnen (ADR-007)?

**Entscheidungen:**

- **Bilanz-Regel gespiegelt, nicht dupliziert-neu-erfunden.** Der Balken zählt
  druckbar/vorläufig/ungeeignet exakt nach `verdict()` aus `render/model.ts`
  (druckbar = eligible ohne provisional-Pass, vorläufig = eligible mit
  provisional-Pass, ungeeignet = nicht eligible). Erwogen: `verdict()`
  exportieren und wiederverwenden — verworfen, weil es in `model.ts` an three.js
  hängt (THREE im Vitest-Pfad) und eine andere Signatur (per-GlobalId-Lookup,
  4. Kategorie „unknown"/grau) hat. Stattdessen eine **reine, getestete**
  `ui/wall-balance.ts`, die nur die Artefakt-Flags liest (kein Neu-Rechnen,
  ADR-007) und Zählung → Anteile → Legende macht. Begründung: das Modul folgt
  dem Repo-Muster (`*-state.ts`, vitest) und bleibt DOM-/THREE-frei; die
  Regel-Doppelung ist bewusst per Kommentar an beide Stellen gebunden.

- **Datenbeschaffung: Karten sofort, Balken asynchron nachgereicht.**
  `GET /projects` (ProjectSummary) trägt weder `overview_run` noch Zeitstempel
  noch Kandidaten. Also lädt `main.ts` je Projekt `loadProject(slug)` →
  `candidates.json` des Übersichts-Laufs und meldet die Bilanz über
  `shell.updateProjectBalance`. Erwogen: alles vor dem Rendern sammeln —
  verworfen (blockiert die Liste, riskiert das `#pl-projects li`-Timing des
  Smoke-Tests). Gewählt: Karten rendern sofort ohne Balken, die Bilanz kommt
  progressiv; **kein Übersichts-Lauf/kein candidates ⇒ kein Balken** (sauber
  degradiert, kein 0-%-Balken). Zeitstempel aus `provenance.created`, relativ
  formatiert (`formatRelativeGerman`, testbar mit injiziertem `now`).

- **IFC-Dropzone + deferred Namensabfrage, Anlage-Flow unverändert.** Klick =
  Datei-Dialog, Drag&Drop = ablegen; erst danach erscheint die Namensabfrage.
  Kern-Spannung: der Core braucht den **absoluten Disk-Pfad** (`model_path`,
  ADR-016), den ein Browser aus Sandbox-Gründen bei Dialog/Drop **nicht**
  preisgibt (`C:\fakepath\…`). Entscheidung: den IFC-Pfad als **editierbares,
  vorbefülltes Feld** neben dem Namen behalten (aus `file.path`, wo vorhanden —
  z. B. Electron —, sonst dem Dateinamen). So bleibt `onCreateProject(name,
  model)` byte-identisch (kein API-/Schema-Eingriff), die Dropzone ist reine
  UX-Schale, und der bestehende „Pfad tippen"-Weg bleibt als Superset erhalten.

- **DOM-Vertrag des Smoke gewahrt.** Die Karten bleiben `li[data-slug]` in
  `#pl-projects` (delegierter Klick, Smoke-Schritt 1). Die frühere
  `#pl-api-warning` entfällt zugunsten eines Status-Punkts (`.dot.ok/.warn`);
  die geteilte `.pl-warning`-Klasse (andere Panels) bleibt.

**Verifikation:** `ui/wall-balance.ts` + Test (12 Fälle); Viewer-Suite **569
grün** (54 Dateien), `tsc` + `vite build` sauber. `ui_smoke.mjs` gegen die
laufende Core-API/Vite: Schritt 1 („Projekt in der Liste geöffnet") grün, **8
Fehlschläge = unveränderter Vorbestand** (Core-Schreibpfad + Bibliothek-Canvas,
s. Memory), **kein neuer**. Screenshot bestätigt Balken/Legende/Zeitstempel aus
echten candidates (6 vorläufig · 186 ungeeignet). Der Smoke wurde nicht
angepasst — der Projektlisten-Vertrag blieb kompatibel.

## 2026-07-08 — Roboter-Schritt + Bibliothek angleichen (UI-Redesign Scheibe 8, #105)

**Frage:** Wie den Reiter Roboter und die Bibliothek auf das Redesign
(`docs/design/design_handoff_ui_redesign/`) heben, ohne die bestehenden
Auswahl-/Warn-/Neubewerten-/Speicher-Flows umzubauen?

**Reiter Roboter — drei Sektionen + Sticky-Footer.** Das Aside wird ein
352-px-Panel aus scrollendem Rumpf (drei `.robot-section`: Roboter/
Endeffektor/Workstation, je Select + `.robot-kenndaten`-Grid Label `--muted`/
Wert Plex Mono) und einem festen Footer. Alle bestehenden IDs bleiben
(`robot-select`, `robot-info`, `tool-*`, `wsc-*`, `arm-schema-toggle` …) —
reiner Restyle, die Panel-Klassen (`robot.ts`/`tool.ts`/`workstation.ts`)
sind unangetastet. „Neu bewerten" wird zu **„↻ Alle Wände neu bewerten"**
(Akzent-Outline, volle Breite, unter dem Roboter-Select); die Busy-Texte in
`robot.ts` zogen mit.

**Entscheidung Sticky-Speichern (die eigentliche Spannung):** Der Prototyp
zeigt **einen** „Speichern"-Footer, die reale App persistiert Endeffektor und
Workstation aber über **zwei unabhängige Core-Endpoints** mit
**unterschiedlicher Veraltungs-Semantik** (Endeffektor-Wechsel veraltet
Outputs via `refreshRevisions`, Workstation bewusst **nicht** — Seam zu #70),
und der Roboter persistiert über den Neubewerten-Lauf. **Alternativen:**
(a) einen echten Merge-Save bauen, der beide PUTs bündelt — verworfen, weil er
Panel-Logik umbaut (Rebuild statt Restyle) **und** ein Re-PUT des unveränderten
Endeffektors spurious Veraltung injizieren könnte; (b) die zwei Sektions-Buttons
sichtbar lassen — verworfen, weil zwei „Speichern" nicht dem Prototyp
entsprechen und im scrollenden Panel wegscrollen. **Gewählt:** die beiden
Sektions-Buttons (`tool-save-btn`/`wsc-save-btn`) bleiben **verdrahtet, aber
`hidden`**; ein einziger Footer-Button `robot-step-save-btn` leitet den Klick an
beide weiter. Deren `disabled`-Zustand (aus den Panel-Klassen) **gattert** jeden
Aufruf — ein disabled Button feuert kein `click` —, sodass jeder Flow
byte-gleich bleibt und die Gating-Regeln (kein Speichern ohne Projekt/API)
automatisch erhalten sind. Die Weiterleitung sind zwei Zeilen in `main.ts`,
keine Änderung an Panel-Klassen, keine API/Schema-Berührung.

**Warnungen** bleiben eigene `<p>`-Elemente (nicht in Grid-Zellen wie im
Prototyp, der sie nur als OK-Fall zeigt), aber neu als kompakte amber
Befund-Zeilen (`.tool-payload-warning` jetzt token-basiert `--warn` statt
Hardcode `#e07f3f`) — „Befund, kein Gate" (ADR-013) unverändert, Ausgrauen
inkompatibler Optionen bleibt.

**Bibliothek.** Die Rubriken-Rail wird 176 px; die **aktive Rubrik** ist ein
gefüllter **Chip** (`--chip`/`--chipbd`, Radius 8 px) statt der
Border-Left-Markierung, inaktive schlicht `--muted`. Karten bekommen den großen
Radius (`--r-lg`), `--field`-Thumbnails und `--border2`-Aktionsbuttons; die
read-only-Pille der Roboter-Karten (#76) nutzt jetzt `--border2`/`--r-pill`.
Konfigurator + Workstation-Editor: **nur Token-Mapping** (u. a.
`#14171b`→`--field`, `#7bb0ff`→`--info`, Lösch-Hover `#d66`→`--err`), kein
struktureller Umbau — wie vom Issue vorgegeben.

**Verifikation:** Viewer-Suite **569 grün** (54 Dateien), `tsc` + `vite build`
sauber. Live-Durchklick gegen laufende Core-API + Vite (headless Edge/CDP):
drei Sektionen mit Plex-Mono-Kenndaten, Aside 352 px, Akzent-Outline-
Neubewerten, sichtbarer Footer-Speichern bei verborgenen Sektions-Buttons;
Bibliothek Rail 176 px, aktive Rubrik-Chip (Radius 8 px, `--chip`-Fläche),
Karten Radius 10 px, read-only-Pille — **keine JS-Exceptions**. Der
DOM-Vertrag des `ui_smoke.mjs` (arm-schema-toggle, header-library-btn,
cfg-Canvas, `.tab-panel aside`) blieb kompatibel; er wurde nicht angepasst.

## 2026-07-08 — Prozess-Schritt „Zerlegung": Inspector mit Accordions + schwebende Teile-Palette (UI-Redesign Scheibe 4, #106)

**Frage:** Wie wird die frühere Druckplan-Rubrik „Zerlegung & Platzierung" (#89)
ein eigener Prozess-Schritt (Inspector, 352 px, Accordions), **ohne** die
bewährte Fachlogik zu forken und ohne Core/API/Schema zu berühren?

**Entscheidung — Re-Komposition statt Neubau.** Die Zerlegungs-DOM (alle
Element-Ids) wandert in einen neuen `<section data-panel="zerlegung">` und wird
dort als Inspector mit drei Accordions (Art & Aufstellung / Schnittplan /
Platzierung) neu gruppiert. Weil `document.getElementById` **dokument-global**
ist, steuert die bestehende `DruckplanPanel`-Klasse dieselben Ids unverändert
weiter — die subtile Dirty-/Generation-/Debounce-Maschinerie (#25/#36/#45)
bleibt byte-gleich. Reuse verbatim: `cutplan-state`, `zerlegungsart-state`,
`aufstell-state`, `placement-override-state`, `parts-palette-state`,
`focus-state`, `collapsible-state`, `rubrics-state`. Alternativen verworfen:
(a) neue `ZerlegungPanel`-Klasse — hätte die Maschinerie dupliziert
(Regressionsrisiko); (b) DOM physisch „verschieben" per Edit — nicht robust,
daher Neubau der Sektion + String-Marker-Chirurgie zum Entfernen der alten
Rubrik.

**Vereinigung #23/#80 + #24 → EINE Aktion.** Der frühere „Optimalvorschlag"
(#23/#80, beste Basis-Lage) und „Zerlegungsvorschlag" (#24, erreichbare Teile)
werden zu **einem** Primärbutton „✦ Automatisch vorschlagen": `_runAuto()` ruft
`_suggest()` **dann** `_decompose()` unter EINEM Busy-Fenster — beide weiterhin
über die bestehenden Schreibstellen (`suggestPlacement`/`proposeDecomposition`,
ADR-016). Begründung: der Prototyp zeigt genau einen Kopf-Button; „erst beste
Lage, reicht sie nicht → zerlegen" ist die natürliche Reihenfolge. Die getrennten
Buttons `#placement-suggest-btn`/`#decompose-btn` sind entfernt (nicht nur
versteckt) — kein toter DOM-Rest.

**Kein Gilt-für-Scope im Zerlegungs-Reiter.** Der Scope-Umschalter bleibt im
Reiter Druckplan (Slicing) und treibt nur noch `processParamsPanel`; die
frühere Kopplung an `placementOverridePanel.setScope` **und** die
Ausgrau-Matrix (`druckplanPanel.setStructuralLocked`) entfallen aus dem
Scope-Callback. Die „Platzierung — <Teil>"-Felder werden stattdessen
**fokus-getrieben** (in `onFocusChanged`: `setScope("teil"|…, id)`) — ein
gewähltes Teil macht seine Felder bedienbar und beschriftet das Accordion.
Damit entfällt in diesem Reiter jedes Ausgrauen (Ziel des 5-Schritt-Designs,
Handoff Scheibe 5).

**Stepper 5-stufig.** `PROCESS_STEPS` (rein, `stepper-state.ts`) wird
Projekt → Roboter → **Zerlegung** (`tab:"zerlegung"`, Output `druckplan` =
Platzierung/Zerlegung) → **Slicing** (übergangsweise `tab:"druckplan"`, Output
`simulation`) → Export. Der Test antizipierte diese 5-Schritt-Form schon (#102);
die Dirty→amber-Kette (Kopf-Badge, Palette-Zähler, Stepper-Punkt) leitet sich
unverändert aus `staleness.ts` ab. Neue reine Ableitung `zerlegung-status.ts`
(vitest): `headStatus(dirty, n)` (ungeprüft ↔ geprüft ✓) und
`paletteCounter(ampeln)` („N/M ✓" ↔ „ungeprüft").

**Accordion-Persistenz.** `collapsible-state.ts`-Muster (▸/▾); der
Aufklapp-Zustand je Gruppe liegt in `localStorage`
(`fgc.zerlegung.acc.<key>`, Default: aufgeklappt) — bewusst keine Core-Persistenz
(reine Präsentation, ADR-007). Die Accordion-Köpfe tragen einen dedizierten
`.acc-marker`-Span, weil ihre Labels geschachtelte ⓘ-/Titel-Spans enthalten und
der `collapsibleView.toggleLabel` sie sonst überschriebe.

**Verifikation:** Viewer-Suite **581 grün** (55 Dateien; +`zerlegung-status`,
angepasst: `tabs`/`stepper-state`/`shell-structure`), `tsc` + `vite build`
sauber. Live-Durchklick der Zerlegungs-Kette gegen laufende Core-API (8765) +
Vite (5173) via headless Edge/CDP (`ui_smoke.mjs`, an die neue Struktur
angepasst): Stepper fünf Schritte, Reiter Zerlegung mit Canvas, Inspector
(vereinter Button + 3 Accordions + „✓ Prüfen lassen"-Footer, alte Rubriken/
Buttons entfernt), Accordion klappt nur über `.hidden`, Teile-Palette schwebt im
Reiter Zerlegung, Fokus↔Palette synchron, Platzierung-Accordion fokus-getrieben
(Feld bedienbar, Titel „Platzierung — #1 …"), Scope-Umschalter nur noch Slicing,
Zerlegungsart-Weiche Abschnitte↔Module — **alle #106-Prüfungen grün, keine
JS-Exceptions**. Die verbleibenden Smoke-Fails sind **vorbestehend und
umgebungsbedingt**, nicht durch diese Scheibe: (a) Speichern-Nebenwirkungen mit
leeren `revisions` treffen auch den **unangetasteten** process-params-Pfad (2g)
→ veraltete Core-Instanz auf 8765; (b) Modul-Gewicht/Druckort/Modul-Sim scheitern
an der Test-Workstation `zelle_fest` **ohne Platzierungs-Frames** (deren eigener
Hinweis sagt es); (c) `#cfg-viewport`-Canvas 0×0 headless. Kein Fail durch die
Re-Komposition.

## 2026-07-08 — UI-Redesign Scheibe 5: Slicing als eigener Prozess-Schritt (Issue #107)

**Frage:** Zweiter Teil des Druckplan-Splits — die Rubrik „Slicing" (#89) soll
ein eigener Prozess-Schritt mit Inspector (352 px) werden; die Rubriken-
Navigation `druckplan-rubrics` entfällt. Wie ohne Fork der bewährten Fachlogik?

**Umkehrung von #89 (dokumentiert):** #89 hatte „Zerlegung & Platzierung" ↔
„Slicing" als **Rubriken-Umschalter** im Druckplan-Aside eingeführt. Der Handoff
kehrt das um: **je Belang ein eigener Schritt** (Zerlegung in #106, Slicing in
#107). Die Rubriken-Rail war ein Zwischenschritt, kein Zielbild — der Stepper
trägt die Navigation, die Rubriken werden überflüssig.

**Entscheidung / Umsetzung:**

- **Recompose statt Fork.** `ScopeSwitch` (#92), `ProcessParamsPanel` (#59/#60/
  #61/#82), `SingularityAdvisorPanel` (#65) treiben unverändert dieselben
  Element-Ids (dokument-globales `byId`). Das index.html-Aside wurde neu
  komponiert (Inspector-Kopf mit Gilt-für, drei Accordions, Sticky-Footer), die
  Panels blieben intakt. Einzige Ergänzung: eine **rein lesende**
  `ProcessParamsPanel.overrideCount()` für die Kopf-Notiz „N Overrides".
- **Fortgeschritten = Bestands-Collapsible.** Das mittlere Accordion ist das
  vorhandene `process-params-advanced-*`-Collapsible (Toggle gehört
  `ProcessParamsPanel`); Prozessparameter- und Advisor-Accordion bekamen eine
  dünne, in `localStorage` persistierte DOM-Verdrahtung in `main.ts`
  (`wireSlicingAccordion`, `fgc.slicing.acc.<key>`), kein neuer Zustandstyp.
- **Gilt-für als Segmented im Kopf.** Die Radios bleiben (ScopeSwitch
  unverändert), nur die Optik wird Segmented (`.segmented`, #101); das aktive
  Teil-Segment in Akzent. Der Scope lebt **nur** im Slicing-Kopf.
- **Felder als `.field-box`** (#101, Einheit rechts im Feld) im 2-spaltigen
  Grid; Override-Hervorhebung über `.field-box:has(input.section-param-override)`
  — die Override-Klasse setzt weiterhin `ProcessParamsPanel` auf das `<input>`.
- **Nichts gelöscht.** Der Modus-/Simulieren-Bereich (#86) bleibt unter den
  Slicing-Parametern erhalten (Test-Vertrag `shell-structure.test.ts` prüft es);
  die Veraltet-Kette (Speichern → Sim/Export amber, stufenweises Aufheben) läuft
  unverändert über `ui/staleness.ts`.
- **Tab-Schlüssel bleibt `druckplan`.** Der interne `data-panel`/`TabId` bleibt
  `druckplan` (kein Ripple durch main.ts/render), der Stepper beschriftet den
  Schritt als „Slicing" (`PROCESS_STEPS[].label`, #106); `stepper-state.ts` und
  die 5-Schritt-Routing-Logik blieben **unangetastet** (nur Kommentar-Nachzug).

**Verifikation:** Viewer-Suite **587 grün** (55 Dateien; `shell-structure.test`
auf den neuen Slicing-Inspector-Vertrag umgestellt: Accordions, Sticky-Footer,
Gilt-für im Kopf vor dem Modus, `druckplan-rubric*` entfernt), `tsc` +
`vite build` sauber. Live-Durchklick gegen laufende Core-API (8765) + Vite (5173,
IPv6-`::1`) via headless Edge/CDP (`ui_smoke.mjs`): **alle Slicing-Prüfungen
grün** — Gilt-für unsichtbar ohne Teil / erscheint bei Fokus, geerbter Wert als
Platzhalter „erbt 2", Eingabe = markierter Override + ↺, Reset+Speichern räumt,
Simulieren-Modus zeigt weiterhin Fokus-/Wand-Knopf + Player im selben Reiter,
Live-Vorschau am Fokus-Abschnitt. Die **9 verbleibenden Smoke-Fails sind exakt
die vorbestehende, umgebungsbedingte Baseline** (stale Core-API → leere
`revisions`/`section_inputs`; Test-Workstation `zelle_fest` ohne Platzierungs-
Frames; `#cfg-viewport` 0×0 headless) — **kein neuer Fail durch #107**.

## 2026-07-08 — Simulations-Dock statt Modus-Umschalter (UI-Redesign Scheibe 6, Issue #108)

**Frage:** Wie wird das Simulieren im Reiter Slicing dargestellt, nachdem
Scheibe 5 (#107) den Modus-/Simulieren-Bereich (#86) übergangsweise unter den
Slicing-Parametern belassen hat? Der Design-Handoff-Prototyp zeigt eine feste
**Dock-Leiste** am Fuß des Viewports statt eines Modus-Umschalters.

**Alternativen:**

- **(A) Modus-Umschalter „Vorbereiten↔Simulieren" (#86) beibehalten.** Verworfen:
  Der Prototyp ist maßgeblich; der Modus war ein bewusster Zwischenschritt (US 24),
  den die Veraltet-Markierung (ADR-017) inhaltlich überflüssig macht — sie ist der
  eigentliche „nicht mit veralteten Werten simulieren"-Schutz (nur veraltete Teile
  amber). Zwei parallele Schutzmechanismen sind Redundanz.
- **(B) Dock + Modus behalten.** Verworfen: doppelte Bedienachse; der Handoff sagt
  „Modus entfällt ersatzlos".
- **(C) Dock statt Modus, Modus-Radiogroup ersatzlos entfernt.** **Gewählt.**

**Entscheidung:** Der Modus-Umschalter (#86) und der eingeblendete Simulieren-
Bereich im Slicing-Aside sind **ersatzlos entfallen**. Die Simulier-Aktionen
(Fokus-Teil / ganze Wand bzw. alle Module) und der Trajektorien-Abspieler docken
in eine **feste Leiste `#sim-dock`** am Fuß des Viewports an (Panel-Hintergrund
96 %, Border oben; nur im Reiter Slicing sichtbar, Geschwister von `#viewport` in
`#tab-body`, `.hidden`-getrieben). Die Timeline (5 px Track, Fill+Knopf in Akzent),
die Zeit (Plex Mono) und die Phasen-Pill **spiegeln den bestehenden Player-Zustand**
(`simulation-state` unverändert). Schnittplan-Bearbeitung und Simulation
**koexistieren ohne Modus**.

**Begründung / Umkehrung von #86:** #86 hatte den früheren Reiter Simulation als
*Modus* im Druckplan absorbiert; #108 kehrt genau den **Modus-Teil** um (Modus →
Dock), behält aber alles andere aus #86 (kein separater Reiter Simulation, die
zwei artabhängigen Simulieren-Knöpfe #97, der Player #26/#27/#48). Viewer-intern
ersetzt ein `replayActive`-Flag den früheren `planMode`: solange **kein** Replay
läuft, sind Live-Vorschau (#85) und Platzierungs-Marker (#93) aktiv; während eines
Replays ruhen sie (vorher an „Simulieren-Modus" gebunden). Der `?run=`-Abspieler-
Deeplink ist ein eigener Pfad (Reiter Projekt) und bleibt unberührt.

**Modul-Reorg:** Die reine Modus-Logik `ui/druckplan-mode.ts` + `ui/plan-mode-panel.ts`
(Modus-Prädikate `initPlanMode`/`isSimulateMode`/… + `staleSimSections`) sind
**gelöscht**; die weiter benötigten reinen Helfer (`focusTarget`, artabhängige
Knopf-Labels/Hints `focusSimLabel`/`sequenceSimLabel`/…, `simPlaysAtDruckort`) sind
nach **`ui/sim-actions.ts`** umgezogen (Test `sim-actions.test.ts`). Die
feingranulare Veraltet-Anzeige je Abschnitt (#83) im alten Simulieren-Bereich
entfällt in der UI — sie lebt weiter in der Teile-Palette/Stepper-Ableitung.

**Verifikation:** Viewer-Suite **584 grün** (55 Dateien; `shell-structure.test`
auf den Dock-Vertrag umgestellt: Dock neben `#viewport`, Modus-Radiogroup entfernt,
Player/Timeline/Phase im Dock), `tsc` + `vite build` sauber. Live-Durchklick gegen
laufende Core-API (8765) + Vite (5173, IPv6-`::1`) via headless Edge/CDP
(`ui_smoke.mjs`): **alle Dock-Prüfungen grün** — Modus-Radiogroup restlos entfernt,
Slicing zeigt das Dock (Fokus-/Wand-Knopf + Player/Timeline/Phase), Modul-Art
beschriftet „▶ Fokus-Modul simulieren" + „Alle Module", Live-Vorschau ohne Modus
aktiv, `?run=`-Deeplink (Warnungs-Deckelung #32 + Stundenformat #33) grün. Die **9
verbleibenden Smoke-Fails sind exakt die vorbestehende, umgebungsbedingte Baseline**
(stale Core-API → leere `revisions`/`section_inputs`; Test-Workstation `zelle_fest`
ohne Platzierungs-Frames; `#cfg-viewport` 0×0 headless) — **kein neuer Fail durch #108**.

## 2026-07-08 — ⌘K-Befehlspalette (UI-Redesign Scheibe 9, Issue #109)

**Frage:** Wie wird die letzte Redesign-Scheibe — eine Befehlspalette, die *jede*
Einstellung und Aktion der neuen 5-Schritt-Struktur suchbar macht und dorthin
navigiert — gebaut, ohne einen zweiten Zustand neben den bestehenden Panels
aufzuspannen und ohne Core/API/Schema anzufassen?

**Entscheidung / Aufteilung (Hausmuster `*-state.ts`):** Die **Registry + Filter**
liegen als reines, DOM-freies Modul `ui/palette-state.ts` (vitest:
`palette-state.test.ts`), die Overlay-/DOM-Schicht in `ui/palette.ts`. Ein
Registry-Eintrag beschreibt sein Ziel **deklarativ** (`PaletteTarget`): optional
`tab`, `accordionToggleId`, `fieldId`, `actionButtonId` bzw. `special: "theme"`.
Welche der vier Wirkungen greifen, entscheidet allein, welche Felder gesetzt sind
— so bleibt die Registry frei von three.js/DOM und die Element-IDs sind bloß
Strings.

**Ausführen = bestehende Mechanismen wiederverwenden (kein zweiter Zustand):**
Reiter über `shell.setActiveTab`; Accordion öffnen durch **Klick auf dessen
Toggle, aber nur wenn `aria-expanded="false"`** — nicht durch direktes Setzen von
`.hidden` (das würde den privaten Aufklapp-Zustand des besitzenden Panels —
`DruckplanPanel._accStates` bzw. die `wireSlicingAccordion`-Closure — desynchronisieren);
Feld per `focus()` + `scrollIntoView`; Aktion per `.click()` auf den bestehenden
Button (auf `disabled` ein No-op = gewolltes Verhalten); Theme über `fgcToggleTheme`
(`ui/theme.ts`, Scheibe 1 — kein zweiter Mechanismus). Sichtbarkeit des Overlays
**ausschließlich über `hidden`** (Lehre #46/#101; das globale `[hidden]{display:none
!important}` sticht die `display`-Kaskade).

**Erwogene Alternativen:** (a) eine `openAccordion()`-Methode auf den Panels
exportieren — verworfen, weil der Klick-Toggle denselben Effekt hat, Persistenz +
Marker gratis mitnimmt und keine neue öffentliche API braucht; (b) Handler-Funktionen
importieren statt `.click()` — verworfen, die Panel-Handler sind privat und an die
DOM-Elemente gebunden; `.click()` ist der schmalste, ehrlichste Reuse.

**Filter:** getrimmte, kleingeschriebene Suche; leere Suche = ganze Registry in
Reihenfolge; **Substring** rankt nach Trefferposition (früh = besser), eine
**Fuzzy-Teilfolge** als schwächerer Fallback (großer Offset). Ranking stabil über
die Registry-Reihenfolge, Limit 9 (Prototyp). Registry-Abdeckung: alle fünf
Prozess-Schritte + Bibliothek + Ansicht, Einstellungen **und** Aktionen.

**DOM-Vertrag:** `ui/palette-dom.test.ts` prüft, dass das Overlay-Gerüst (mit
`hidden`) + der Header-Auslöser existieren **und** jede in der Registry genannte
Feld-/Aktions-/Accordion-ID wirklich in `index.html` steht — Registry und echtes
DOM können nicht mehr auseinanderlaufen (Lehre Static-Asset-Check: grüne
Unit-Tests trotz toter Navigation).

**Verifikation:** Viewer-Suite **664 grün** (57 Dateien; neu `palette-state` +
`palette-dom` = 24 + 63 Tests), `tsc` + `vite build` sauber. Live-Durchklick gegen
laufende Core-API (8765) + Vite (5173) via headless Edge/CDP (`ui_smoke.mjs`, neuer
Schritt 1c): **⌘K öffnet (Overlay sichtbar, Eingabe fokussiert)** → Filter
„schichthöhe" liefert genau den Slicing-Prozessparameter (Icon|Label|Gruppe) →
**Ausführen navigiert** (Reiter druckplan, Prozessparameter-Accordion offen,
Schichthöhe-Feld fokussiert, Overlay zu) → Header-Suchfeld öffnet, **ESC schließt**
— alle vier grün. Die **9 verbleibenden Smoke-Fails sind exakt die vorbestehende,
umgebungsbedingte Baseline** (stale Core-API → leere `revisions`/`section_inputs`;
Test-Workstation `zelle_fest` ohne Platzierungs-Frames; `#cfg-viewport` 0×0
headless) — **kein neuer Fail durch #109**.

## 2026-07-08 — Architektur-Review Kandidat 1: `plan_for_job` als die eine Rekonstruktions-Tür des Zerlegungsplans

**Kontext:** Der ultracode-Architektur-Review (nach #101–#109; Bericht
`%TEMP%\architecture-review-2026-07-08.html`) fand als stärksten Kandidaten:
das Konzept „Zerlegungsplan eines Druckjobs" ist **zweimal verdrahtet** —
`propose_decomposition` (actions.py:2944–2972) reicht Workstation,
Aufstell-Toggle und Modulgrenzen an `propose/from_cuts`, die Spiegel-Funktion
`_plan_for_job` (actions.py:950–983, Konsument `simulate_section`) tut das
nicht; #77/#81/#90 kamen nur an einer Stelle an. Folge (von zwei
Verifikations-Agenten am Code bestätigt): **Modul-Simulation (#97) läuft
core-seitig in „modul braucht eine Workstation" → 422**, obwohl der Job eine
Workstation trägt; bei Abschnitt+Workstation bzw. `stand_mode="elevated"`
weicht die simulierte Platzierung **still** vom Druckplan ab
(suggest.py-Fallback-Raster). Kein Testfall mit Zerlegungsart „modul"
existiert. Zusatzbefund beim Grilling: die Pfade unterscheiden sich bewusst
in der Override-Strenge (`strict=True` beim Schreiben, `strict=False` beim
Rekonstruieren) — das muss Interface werden, nicht verloren gehen.

**Frage:** Wie wird daraus **eine** Tür „Druckjob rein, Zerlegungsplan raus",
obwohl der Schreibpfad seine Plan-Eingaben (kind/cuts/joint_offset/overrides)
als frische, noch nicht persistierte Argumente bekommt?

**Alternativen:** (a) Schreibpfad baut einen **Kandidaten-Job** (Job-Kopie +
frische Eingaben) und ruft dieselbe Tür; (b) optionale Override-Parameter an
der Tür (Interface trägt beide Welten + Vorrangregel); (c) zwei Funktionen
mit gemeinsamem Kern (`plan_from_inputs` + `plan_for_job`). Ort: `pipeline`
vs. `fgc.decompose` (verworfen: decompose bleibt pur, kennt das
project.json-Schema bewusst nicht — Schema-Leak). Schnitt: ein Issue (Tür =
Fix) vs. Hotfix + Refactor getrennt.

**Entscheidung (Grill mit Nutzer, 2026-07-08):** Variante **(a)**: public
`plan_for_job(job, wall, robot, tool, *, strict_overrides, workstations_dir)`
in `pipeline/actions.py`; `propose_decomposition` merged seine frischen
Eingaben in eine Job-Kopie und ruft dieselbe Tür (`strict_overrides=True`),
`simulate_section` ruft sie mit `strict_overrides=False`;
`_resolve_section_overrides`-Auflösung wandert hinter das Interface.
`simulate_section` (und api.py) bekommen `workstations_dir` durchgereicht.
**Ein** Issue — die Tür ist der Bug-Fix, kein Zwischenzustand. Neuer
Glossarbegriff **Zerlegungsplan** in `core/CONTEXT.md` (rekonstruiert, nie
persistiert; ADR-016).

**Begründung:** Ein Interface statt Kopien macht „Simulation zeigt denselben
Plan wie der Reiter Druckplan" von der Docstring-Behauptung zur erzwungenen
Eigenschaft; der Kandidaten-Job hält das Interface pur (genau der Zustand,
der bei Erfolg persistiert wird). Deletion-Test bestanden: ohne die Tür
dupliziert jeder Aufrufer die komplette Eingaben-Sammlung — faktisch heute
schon, nur unvollständig und falsch. Tests: Modul-Job-Simulationsfall (hätte
den 422 sofort gezeigt), Abschnitt+Workstation-Identität zum decompose-Lauf,
Identitäts-Orakel Schreib- == Lesepfad.

## 2026-07-08 — Gap-Analyse UI-Redesign: Handoff vs. Umsetzung #101–#109 → Nacharbeit #113–#115

**Kontext:** Nutzer-Eindruck nach Abschluss von #101–#109: „das Redesign
sollte stärkere Veränderungen bringen — davon wurde wenig umgesetzt."
Drei parallele Code-Prüfungen glichen jede Handoff-Scheibe
(`docs/design/design_handoff_ui_redesign/design_handoff_ui_redesign_v2/`)
gegen den Viewer-Code ab.

**Befund:** (1) Die Scheiben 1–8 sind strukturell vollständig und sauber
umgesetzt (Tokens 1:1, Plex vendored, Tabbar restlos entfernt, Accordions,
Sim-Dock, Palette, Projektliste, Bibliothek). (2) **Handoff-Scheibe 9
„Viewport-Optik" wurde nie umgesetzt** — Ursache ist ein Nummerierungs-
Unfall beim Issue-Schnitt: README-Scheibe 5 wurde in #107+#108 geteilt,
dadurch bekam die ⌘K-Palette (README-Scheibe 6) das Etikett „Scheibe 9"
(#109) und die echte Scheibe 9 fiel ohne Issue unter den Tisch. Sie trägt
den größten sichtbaren Anteil (Studio-Hintergrund, Lehm-Ton-Wände mit
Eignungs-Sockel statt Ampel-Vollfärbung, Glas-Schnittebenen mit Maß-Labels,
cyaner TCP-Marker, Kontaktschatten); zudem wirkt der Theme-Umschalter nicht
auf die three.js-Szene (Hintergrund hart `0x1c1e22`). (3) **Layout
spiegelverkehrt:** Screenshots und #106 fordern 3D links / Inspector rechts /
Teile-Palette links oben; umgesetzt wurde Inspector links (Erbe des
geteilten Viewports #30, Asides vor `#viewport` im DOM) und Palette rechts —
ein Umsetzungsfehler, kein Schnittfehler. (4) Feinschliff: Platzhalter-
Wortlaute („automatisch 650" statt „650 · Auto", „erbt 8" statt „8 · erbt",
fehlender „· Karten-Default"), Export-Empty-Hint nennt alte Reiternamen.

**Alternativen:** alles in ein Sammel-Issue (verworfen: Scheibe 9 ist ein
eigener three.js-Arbeitsgang mit eigener Abnahme-Referenz, das Entspiegeln
ein kleiner CSS/DOM-Eingriff) vs. drei getrennte Issues nach Arbeitsgang.

**Entscheidung:** Drei Issues, alle `ready-for-agent`: **#113**
Viewport-Optik (Spezifikation = Handoff-README Scheibe 9 + Screenshots
10/11, nur Material/Licht/Farbe, Szene bezieht Farben nach Möglichkeit aus
den CSS-Tokens), **#114** Layout entspiegeln (Viewport links, Inspector
rechts, Palette links oben auf `.float-panel`), **#115** Feinschliff
(Wortlaute, Export-Hint, Rest-Hints, `.overridden`-Vereinheitlichung).

**Begründung/Lehre:** Beim Schneiden eines Handoffs muss die Scheiben-Liste
des Quelldokuments am Ende **abgezählt** gegen die Issue-Liste stehen —
eine Umnummerierung mitten im Schnitt (Split von Scheibe 5) hat hier die
visuell wichtigste Scheibe verschluckt. Anforderungen aus dem einleitenden
Teil eines Handoffs („Inspector rechts") brauchen eine explizite
Abnahme-Zeile im Issue, sonst überlebt das Bestandslayout.

## 2026-07-08 — Architektur-Review Kandidat 2: gemessenes Wand-Frame — Konvention & Sensorik (Grill, → Issue #116)

**Kontext:** Der Review fand (adversarial verifiziert, von mir am Code
nachgeprüft): `three_point_frame` (`setup/frame3p.py`) produziert ein Wand-Frame
mit **X=Länge, Y=Höhe, Z=Normale**, während Toolpath/`_planned_setup` das
Wandsystem **X=Länge, Y=standoff/Front, Z=Höhe** nutzen. Gemessenes Setup ∘
Slicer-Target ⇒ Schichten laufen in die Wandnormale ⇒ **Wand druckt gekippt**;
kein Test kreuzt den Seam. Der gemessene Pfad ist der Pflichtpfad des ersten
realen Materialdrucks (Antast-Gate `pose_source=measured`).

**Frage:** Wie richten wir das gemessene Frame auf die Toolpath-Konvention aus —
internes Remapping (A), geänderte Antast-Prozedur (B), und mit welchem
Front-Vorzeichen?

**Entscheidung / Richtung (Grill mit Nutzer):**
- **Manuelles 3-Punkt-Antasten ist nicht die Ziel-UX.** Der Nutzer will das
  Wand-Frame perspektivisch **per Sensorik** erfassen (automatische
  Registrierung). Konkreter Ansatz wird **separat später** gegrillt (verwandt
  mit ROS2-Live-PRD #111). Deshalb **jetzt kein Code-Fix**, sondern als **Issue
  #116** festgehalten.
- **v1-Constraint fixiert:** Roboter steht in v1 **immer senkrecht** zur Wand
  (standoff = reine Normale, yaw um die Höhenachse) → **Front == Normale exakt**;
  bislang stille Annahme von `_planned_setup`, nun dokumentiert.
- **Front-Vorzeichen** (Halbraumseite des Roboters) wird **am realen Roboter**
  festgelegt, nicht vorab geraten.
- **Invariante unabhängig vom Erfassungsweg:** das Setup-Modul trägt „`wall_to_base`
  liegt immer im Toolpath-Wandsystem" als Code + **Ketten-Orakel** (`measured ==
  planned` bei gleicher Aufstellung), statt sie in Bedienungs-Prosa auszulagern.

**Begründung:** Kein Aufwand in eine Antast-UX stecken, die der Nutzer ohnehin
durch Sensorik ersetzen will; die eigentliche Härtung (Invariante im Setup-Modul
+ Orakel) gilt für jeden Erfassungsweg und wird beim Schneiden des Sensorik-PRDs
mitgenommen. ADR-006 stuft die Konventionsverletzung als Bug ein — kein Re-Open.

## 2026-07-08 — Layout entspiegelt: 3D links, Inspector rechts (#114)

**Frage:** Das Redesign-Handoff zeigt auf allen Prozess-Screenshots (02/04/05/06)
das 3D-Feld **links** und den Inspector **rechts** (352 px), die Teile-Palette
schwebend **links oben**. Umgesetzt (Erbe des geteilten Hauptsichtfelds #30) war
das Spiegelbild: Asides links mit `border-right`, Palette rechts oben. Wie
zurückdrehen, ohne Verhalten zu brechen?

**Alternativen:**
- (A) DOM-Reihenfolge in `#tab-body` umsortieren (`#viewport` vor die Panels).
  Verworfen: bricht die Quell-Reihenfolge-Assertions in `shell-structure.test.ts`
  (u. a. „Palette steht NACH dem #viewport") und riskiert index-basierte Lookups.
- (B) **CSS `order: -1` am `#viewport`** — die eine Zeile kippt die Flex-Spalte,
  der DOM bleibt unverändert. Gewählt.

**Entscheidung:** Reines CSS/DOM-Umsortieren ohne Logikänderung:
- `#viewport { order: -1 }` (3D links, Inspector rechts).
- Prozess-Asides (`#panel`, `#robot-panel-aside`, `#druckplan-aside`,
  `#export-aside`) `border-right` → `border-left`; `#zerlegung-aside` erbt den
  Trenner nun als `border-left` auf `.inspector`.
- Teile-Palette nach `left:12px` und auf den `.float-panel`-Baustein (tokens.css:
  Blur/Radius r-lg/Schatten) umgestellt — die Eigenkopie in `.parts-palette`
  (background/border/radius/box-shadow) entfernt.
- Schwebende Overlays an die linke Viewport-Spalte angepasst: `.sim-dock`
  `left:0; right:352px`, `.plan-chip` zentriert über der linken Spalte
  (`left: calc(50% - 176px)`). `.druckort-toggle` (bottom-left) bleibt.

**Begründung:** `order` ist die risikoärmste Drehung — kein DOM-Umbau, also keine
gebrochenen Struktur-/Smoke-Assertions, keine Picking-/Reiter-/Sichtbarkeitslogik
angefasst (Sichtbarkeit weiter nur über `hidden`). Fachlich ändert sich nichts;
es ist die im Handoff (Issue #106) ohnehin geforderte Anordnung. Verifikation:
tsc clean, Viewer-Tests 664 grün, ui_smoke ohne neue Fehler (die vorbestehenden
umgebungsbedingten Fails unverändert).

## 2026-07-08 — Viewport-Optik „Clay-Studio" (Handoff-Scheibe 9, Issue #113)

**Frage:** Beim Issue-Schnitt des UI-Redesigns fiel die Handoff-Scheibe 9
(„Viewport-Optik") durch eine Umnummerierung unter den Tisch. Wie holt man die
three.js-Bühne auf den Soll-Zustand (Screenshots 10/11) — nur Material/Licht/
Farbe, ohne Picking/Drag/Artefakt-Lesen/Kamera anzufassen (Handoff-Protokoll
Punkt 3)?

**Alternativen (Theme→Bühne):**
- (A) Eigene Hexwerte je Theme im Szenen-Code duplizieren. Verworfen: doppelte
  Pflege, driftet gegen die CSS-Token, und die Bühne bliebe stumm gegenüber ◐.
- (B) **Palette aus den CSS-Tokens lesen** (`getComputedStyle` auf `--vp1/--vp2`
  …) und die Bühne bei jeder Theme-Umschaltung neu färben. Gewählt.

**Entscheidung:**
- Neues reines Modul `render/scene-palette.ts` (vitest): `readScenePalette`
  (Token-Leser → Bühnen-Farben, Gitter-Deckkraft je Theme), `clayBrightness`
  (deterministische ±8-%-Varianz je Wand), `hashSeed`, `ndcToPx` (Projektion →
  Overlay-Pixel). Alles DOM-/three.js-frei geprüft.
- `scene/setup.ts` bekommt `restyle()` (Studio-Verlauf als CanvasTexture aus
  `--vp1/--vp2`, dezenter Fog = Verlaufsrand, Gitter nur nahe der Szene via Fog-
  Falloff, radialer Bodenschatten), eine durchklickbare Overlay-Ebene
  (`pointer-events:none`), `onFrame()` und `project()`. `main.ts` hängt
  `restyle()` an dieselbe `applyTheme`-Verdrahtung wie die CSS-Token — ◐ kippt
  jetzt auch die 3D-Bühne.
- Wände (`render/model.ts`): einheitlicher Lehm-Ton `#c08a5a` (±8 % Varianz,
  roughness hoch, keine Metalness); Eignung als Sockel-Streifen am Wandfuß
  (~70 mm, grün/amber/rot, leichte Emissive) statt Vollfärbung; Auswahl =
  Akzent-Glow (Emissive) statt reinem Deckkraft-Wechsel. Der Streifen ist
  nie pickbar (`raycast = () => {}`) — Wand-Picking unverändert.
- Zerlegung: Fokus-Abschnitt voller Ton, übrige gedimmt (`#544f49`,
  `render/sections.ts`); Schnittebenen als Glas-Ebenen (amber ~12 %) mit voller
  Unterkante (`render/cutplanes.ts`); Maß-Label „z &lt;mm&gt; ⇅" als projizierter
  HTML-Chip. TCP-Marker cyan Kreis+Quadrat (`render/tcpmarker.ts`), gedruckte
  Bahnen gestrichelt (`render/toolpath.ts`), Basis-Chip „Basis · Podest &lt;h&gt;".

**Begründung:** Token-basierte Bühne = eine Wahrheit für Farben und
Theme-Reaktivität ohne Duplikat. Alle neuen Chips sind ein durchklickbares
Overlay über dem Canvas — Drag der Schnittebenen, Picking und Kamera bleiben
unangetastet; die Sockel-Streifen/Kanten/Chips sind als Deko nicht raycastbar.
Verifikation: tsc clean, Viewer-Tests 670 grün (664 + 6 neue in
`scene-palette.test.ts`), `vite build` grün. Der Headless-Smoke ließ sich in
dieser Umgebung nicht gegen den frischen Build fahren (Port 5173 von einer
fremden, veralteten Vite-Instanz belegt); die smoke-relevanten Marker-/
Abschnitts-Zusicherungen (Fokus-Deckkraft > 0, Marker-Geometrie/-Lagen
unverändert) wurden per Code-Prüfung abgesichert.

## 2026-07-08 — Redesign-Feinschliff: Platzhalter-Wortlaute, Export-Empty, Rest-Hints (#115)

**Frage:** Die Gap-Analyse Handoff vs. Umsetzung (#101–#109) fand mehrere
Label-Abweichungen von den Screenshots (Handoff-Protokoll Punkt 5 „Labels exakt"
/ Punkt 6 „Screenshot hat Vorrang"): abweichende Platzhalter-Formate, ein
Export-Empty-Hinweis mit veralteten Reiternamen und noch stehende statische
`.hint`-Absätze in Bibliothek/Konfigurator.

**Entscheidungen:**
- **Platzhalter-Formate** an die Screenshots angeglichen (Suffix-Konvention
  `<wert> · <quelle>` statt Präfix): Platzierung „650 · Auto" (früher
  „automatisch 650"; null → „Auto"), Slicing-Teil-Scope „8 · erbt" (früher
  „erbt 8"; global ungesetzt → „Karten-Default · erbt"), Slicing-Global-Scope
  neu „<default> · Karten-Default" (früher leer ohne Hinweis). `<default>`
  bleibt **literal** — der Viewer kennt die Karten-Defaults nicht und rechnet
  nie selbst (ADR-007/014). State-Tests (placement-override-state, scope-state)
  auf die neuen Strings gezogen.
- **Export-Empty** von zwei Sätzen mit den alten Reiternamen „Druckplan"/
  „Simulation" auf einen kurzen Empty-State mit „Zerlegung"/„Slicing" gekürzt.
- **Override-Kennzeichnung** (Alternativen: auf tokens.css-Baustein
  `.field-box.overridden` umstellen ODER Input-Klasse `section-param-override`
  behalten + Brücke dokumentieren): **Input-Klasse behalten** gewählt. Begründung:
  beide Übersteuer-Schritte setzen die Klasse bereits **einheitlich** auf das
  `<input>` (nur das Input weiß je Feld, ob es gefüllt ist), aber ihre Wrapper
  unterscheiden sich (Slicing `.field-box`, Platzierung `.placement-field`) — der
  tokens-Baustein markiert dagegen die Wrapper-Box. Ein Umbau auf `.overridden`
  müsste in zwei Panels die Klassenlogik duplizieren und bräuchte für
  `.placement-field` ohnehin eine eigene Regel. Die CSS-Brücke
  (`:has(input.section-param-override)` bzw. `.placement-field input…`) ist daher
  in `style.css` als bewusste Entscheidung dokumentiert statt entfernt.
- **Rest-Hints (Grauzone, Item 4):** Prozess-Panels tragen seit Scheibe 3 (#103)
  keinen statischen Fließtext mehr — bestätigt. In Bibliothek/Konfigurator
  wurden die statischen Erklärabsätze nach dem Scheibe-3-Muster in ⓘ-Tooltips
  verlagert: Roboter-/Endeffektor-Bibliothek-Intro, Konfigurator-Intro (Sibling
  zum dynamischen `#cfg-heading`, damit dessen `textContent`-Update den Tooltip
  nicht überschreibt → neue `.cfg-heading-row`-Flexzeile), Schritt-2/3/5-Köpfe,
  Feinjustage- und „Passt zu Roboter(n)"-Label. **Bewusst als Absatz belassen:**
  alle konditionalen Status-/API-Hinweise (`*-api-warning`, `*-status`,
  `*-empty`, `cfg-mount-status`, `cfg-tcp-readout`, `reslice-api-hint` — von JS
  ein-/ausgeblendet) sowie die sichtbaren Ausnahmen aus Scheibe 3 (Provisorik-
  Box, „Plan — vor dem Druck antasten"-Chip).

**Begründung:** Wortlaut = Abnahme-Kriterium (Screenshot hat Vorrang); die
Suffix-Konvention macht Quelle (Auto/erbt/Karten-Default) einheitlich lesbar.
Verifikation: `npx tsc --noEmit` clean, Viewer-Tests grün, Headless-Smoke ohne
neue Fehler (nur die bekannten Umgebungsfälle).

## 2026-07-08 — Wand-Fokus ab Zerlegung + schwebendes Viewer-Einstellungen-Menü (Viewer-only)

**Frage:** Ab dem Reiter Zerlegung ist die Wand gewählt, das geteilte 3D-Feld
zeigt aber weiter das **ganze Gebäudemodell** (alle Wände der Modellübersicht +
Gebäudekontext-Geist). Das lenkt von Schnitten/Abschnitten/Platzierung ab. Der
Nutzer will „ab Zerlegung nur noch die gewählte Wand fokussiert; das Gebäude
über Kontext einblendbar" — und dafür „irgendwo ein aufklappbares
Viewer-Einstellungen-Menü".

**Erwogene Alternativen (Menü-Ort, gegrillt via AskUserQuestion):**
(a) schwebendes ⚙-Float-Panel am 3D-Feld (wie die Teile-Palette), (b) ein
einklappbarer Block im jeweiligen Reiter-Aside, (c) nur in der ⌘K-Palette.
**Entscheidung: (a)** — konsistent mit dem bestehenden `.float-panel`-Muster
(Teile-Palette, Druckort-Umschalter), auf allen Fokus-Reitern gleich erreichbar,
ohne pro Reiter dupliziertes Aside-DOM. Platz **rechts oben** (Teile-Palette
sitzt links oben).

**Erwogene Alternativen (Bedeutung von „Kontext"):** Der Begriff kollidiert:
`context.json` ist der Nicht-Wand-Geist (Issue #17), „das Gebäude" sind die
**anderen Wände** aus `model.glb`. (a) ein Schalter zeigt beides (andere Wände
gedimmt + Kontext-Geist), (b) nur der Kontext-Geist, (c) zwei getrennte
Schalter. **Entscheidung: (a)** — ein Regler „Gebäude/Kontext einblenden"
(Standard aus). Begründung: der Nutzer denkt „Umgebung an/aus", nicht in den
zwei Artefaktquellen; ein Schalter ist die kleinste erlernbare Fläche.

**Fokus-Reiter:** Zerlegung, Slicing (interner Schlüssel `druckplan`), Export.
Projekt bleibt Modellübersicht (Wandauswahl), Roboter die Roboter-Vorschau.
Ohne gewählte Wand (`currentWallGlobalId === null`) bleibt die Gesamtansicht —
es gibt nichts zu isolieren.

**Zwei Autoritäten für den Kontext-Geist, bewusst getrennt:** In den
Fokus-Reitern steuert das ⚙-Menü `contextObject.visible`; in der Modellübersicht
(Reiter Projekt) bleibt der bestehende Projekt-Panel-Schalter „Gebäudekontext"
(Issue #17) die Autorität. `applyWallFocus` gibt die Kontext-Sicht beim Verlassen
eines Fokus-Reiters an das Projekt-Panel zurück (`focus ? vis.showContextGhost :
panel.contextVisible`). Alternative „ein einziger globaler Kontext-Zustand"
verworfen: hätte den #17-Schalter umverdrahten müssen (mehr Fläche, kein
Nutzergewinn).

**Kamera:** Beim Wechsel **in** einen Fokus-Reiter fasst die Kamera die Wand ein
(`fitToWall` über die bestehende `fitWorld`-Rangfolge); der Kontext-Toggle
refittet **nicht** (kein Kamerasprung beim Ein-/Ausblenden), dafür der Button
„Auf Wand einpassen". In der Druckort-Ansicht (#96) ruht das Einfassen — dort
besitzt `syncDruckort` die Kamera (`!isDruckort(druckortState)`-Wächter).

**Architektur (Modularität vor allem):** reine Ableitung DOM-/three.js-frei in
`ui/viewer-settings-state.ts` (`isFocusTab`, `wallFocusVisibility`; vitest 6),
dünne DOM-Klasse `ui/viewer-settings.ts`, Wand-Isolation als reine
`.visible`-Umschaltung `ModelView.setWallFocus` in `render/model.ts` (Sockel-
Streifen + Kanten hängen als Kinder am Wand-Mesh und folgen automatisch; Overlays
der Fokus-Wand bleiben unberührt). `main.ts` verdrahtet nur (`applyWallFocus`/
`fitToWall`), kein zweiter Zustand (ADR-016). DOM-Vertrag in
`shell-structure.test.ts` nachgezogen.

**Begründung:** Weniger im Bild = klarere Zerlegungs-/Slicing-Arbeit; „Befund,
kein Gate"-Geist bleibt (der Kontext ist einen Klick entfernt, nichts wird
gelöscht). Reine Darstellung/Interaktion (ADR-007) — kein Core-/API-/Schema-
Change. Verifikation: `npx tsc --noEmit` clean, Viewer **679 vitest grün**,
`vite build` clean. **Offen (Runtime):** manueller Durchklick am Gerät.

## 2026-07-08 — ⚙-Menü: erweiterbare Sicht-Schalter (Basis, Bemaßung) + Positions-Fix (Nachtrag)

**Frage:** Nutzer will im ⚙-Menü mehr Schalter (Basis an/aus, Bemaßung, …), und
das Panel überdeckte den rechten Inspector-Aside.

**Positions-Fix:** `.viewer-settings` ankerte an `#tab-body` (volle Breite) →
`right: 12px` lag über dem 352px-Inspector (#114: Viewport links, Inspector
rechts). Auf `right: 364px` (352 + 12) gesetzt, wie `#sim-dock` (`right: 352px`)
— Panel sitzt jetzt rechts oben ÜBER der Viewport-Spalte.

**Erweiterbarkeit:** Statt je Schalter HTML zu stricken hält `ui/viewer-settings.ts`
jetzt eine **`ToggleSpec[]`-Liste** (Schlüssel/Label/Hint/Start), baut die
Checkboxen in einen Mount-Punkt (`#viewer-settings-toggles`) und meldet
`onToggle(key, visible)`. `main.ts` verdrahtet je Schlüssel die Wirkung. Neue
Schalter = ein Listeneintrag. Erste drei: `context` (Default aus, füttert
`wallFocusVisibility`), `basis` (Default an → `placementMarkers.group.visible` +
Basis-Chip-Prädikat), `bemassung` (Default an → measure-label-Prädikat). Die
Chip-Bools werden je Frame in `updateOverlayChips` gelesen — kein manuelles
Refresh; die 3D-Basis-Gruppe schaltet `applyOverlayToggles` (auch nach jedem
Marker-Rebuild).

**Begründung:** Sicht-Schalter sind reine Präferenzen (ADR-007); eine Liste
statt Handverdrahtung hält künftige Schalter (Schnittebenen, Travel, Roboter-
Mesh …) billig. Verifikation: `tsc` clean, **679 vitest grün**, `vite build`
clean.

## 2026-07-08 — Grill: Kollisionskontrolle + Ausweich-Optionen (Wrist/Elbow/…) → ADR-024

**Anlass:** Nutzer-Foto — der M1013-Ellbogen taucht beim Replay von
Abschnitt 1 sichtbar durch das Wandvolumen; die Statuszeile sagt ehrlich
„keine Kollisionsprüfung". Wunsch: Kollisionskontrolle einbauen + zum
Ausweichen „verschiedene Optionen im Menü" (Wrist, Elbow, …).

**Codebasis-Befund vor dem Grillen:** (a) Die analytische IK rechnet bereits
alle 8 Konfigurationen (`SHOULDER/ELBOW/WRIST`-Bits, `opw.py`),
`select_along_path` wählt automatisch — das Wunsch-Menü ist das Freischalten
einer vorhandenen Wahl, keine neue Kinematik. (b) Der Singularitäts-Advisor
(ADR-020) ist die fertige Blaupause „Core rechnet Befund + Hebel → dünne
Route → Prüfen/Anwenden". (c) Die URDF-Kollisionsmeshes des M1013 sind genau
für diesen Zweck gevendort. (d) Zwei Lücken: keine Arm-Kollisionsgeometrie im
Core (Viewer-Kapseln sind reine Anzeige), kein Volumen des „bereits
Gedruckten" zur Simulationszeit (Wand = Rechteck; Footprint-Polygon lebt
upstream im Slicer).

**11 Fragen, Entscheidungen (Details/Verworfenes in ADR-024):**

1. **Kollisionspaare v1:** Arm↔Gedrucktes, Arm↔Boden/Podest/Workstation,
   Arm↔Gebäudekontext (manuell zuschaltbar; bei Modulen gegenstandslos),
   Selbstkollision.
2. **Prüfstellen:** Simulation je Bahnpunkt (Kern) + Grob-Check in der
   Platzierungsbewertung (Ausbaustufe). Viewer urteilt nie (ADR-007).
3. **Semantik:** minimaler Abstand je Sample + zwei Schwellen (<0 rot,
   <Sicherheitsabstand gelb — weicher Lehm), nicht binär.
4./5. **Geometrie:** exakte Kollisionsmeshes statt Kapseln — Nutzer-Entscheid
   *gegen* die Empfehlung Kapseln, mit gutem Grund: Handgelenk/Tool arbeiten
   prozessbedingt dauernd nah an der Wand, dicke Kapseln warnen dort
   chronisch. Ausprägung: `python-fcl` via vorhandenem `trimesh`,
   Breitphasen-Filter (AABB/Kapsel) vor der exakten Distanz.
6. **Druckstand:** Footprint-Prisma je Schicht (frühere Teile voll, aktuelles
   wächst; Freizone um den Druckpunkt); Druckreihenfolge = Montagereihenfolge
   war schon entschieden (PRD #88).
7. **Advisor-Hebel v1:** IK-Konfiguration je Teil, Kipp/Lead-Sweep,
   Platzierung. Travel-Move-Entschärfung + feinere Zerlegung +
   Toolverlängerung bewusst später.
8. **Konfigurationswahl:** drei Einzelschalter (Schulter/Ellbogen/Handgelenk,
   Default auto), harter Filter; unerreichbar unter Vorgabe = Warnung
   (Befund, kein Gate). Macht den ADR-020-Config-Flip anwendbar.
9. **Artefakt:** additiv Abstandskurve + Verursacher je Sample + Intervalle
   in `meta`; eigenes Kollisions-Badge je Teil, Ampel unangetastet.
10. **Replay-UI:** Glied-Einfärbung rot/gelb, Timeline-Marker, wachsender
    Druckstand statt Voll-Box, Live-Abstandszahl — alle vier, Nr. 4 (und die
    Sicht-Schalter generell) über das ⚙-Ansicht-Menü an-/abwählbar.
11. **Verpackung:** PRD mit blockierendem Spike S0 (python-fcl auf Windows +
    Performance-Probe mit echter `trajectory.json`) → S1 Kollisionsmodul Core
    → S2 Trajektorien-Befund → S3 Replay-Darstellung → S4 IK-Konfiguration
    end-to-end → S5 Kollisions-Advisor → S6 Platzierungs-Grob-Check.

**Abgeleitet ohne Frage:** Befund automatisch bei jeder Sim, Advisor auf
Knopfdruck (teuer); Advisor liefert — anders als ADR-020 — eine *gerankte
Optionsliste* statt eines Einzelvorschlags (das ist wörtlich das gewünschte
„Menü").

**Doku:** ADR-024; Glossar `core/CONTEXT.md` +5 Begriffe (Kollisionskontrolle,
Druckstand, Freizone, IK-Konfiguration, Kollisions-Advisor). PRD-Issue folgt
direkt im Anschluss.


## 2026-07-08 — Spike S0: python-fcl grün; Urteilsgeometrie = VHACD-Konvexzerlegung (ADR-024-Nachtrag)

**Frage:** Läuft `python-fcl` auf Windows (Python 3.14), und ist die
Distanzrechnung Arm↔Druckstand schnell genug für den automatischen Befund je
Simulation? (Blockierender Spike aus PRD #124; Rückfall wären Kapseln.)

**Vorgehen:** Vier Messsonden (`docs/spikes/s0_scripts/`) gegen die echte
Foto-Trajektorie `runs/20260708-161603_slice_Denkmal` (25 217 Samples,
82 Schichten): URDF-`<collision>`-Meshes je Glied mit der Offset-Formel aus
`convert_robot_meshes.py`, Druckstand = wallspec-Geometrie je Schicht gekappt,
Schichtzuordnung über die TCP-Höhe (Lehrgeld: über die Flansch-Höhe gebaut ist
der Druckstand um die Werkzeuglänge zu hoch — 100 % Pseudo-Kollisionen).

**Alternativen (gemessen, 1 009-Posen-Teilmenge gegen exakte Referenz):**
exakte Roh-Meshes 21,5 ms/Sample (Volllauf 602 s — zu langsam); nackte
Glied-Hüllen 0,06 ms, aber +15 % chronische Fehlwarnungen (das
Kapsel-Argument in milder Form); Dezimierung auf 1 500 Faces 3,5 ms, aber
bis **+20 mm erfundener Abstand** (gefährliche Richtung, verworfen);
**VHACD-Konvexzerlegung 2,3 ms bei ±5,5 mm Formtreue (⌀ 0,31 mm)** —
gewählt.

**Entscheidung:** Spike **grün**. S1-Rezept: Breitphase = Hüllen-Distanz
(untere Schranke, > Sicherheitsabstand ⇒ grün), Urteil = VHACD-Distanz;
Volllauf damit 44 s statt 602 s (1,74 ms/Sample) bei pathologischen 66 %
Nahphasen-Anteil, Klassifikation deckungsgleich (7 548 vs. 7 538 Samples
≤ 0 mm). Offline-Anteil (Hüllen+VHACD, 21,9 s je Roboter) wird
Konvertier-Derivat in `fgc.collision.robot_geometry`; Dependencies
`python-fcl`/`mapbox-earcut`/`vhacdx` kommen mit S1 in `fgc-core[geo]`.
Determinismus bitgleich (Goldens möglich). Nebenprodukt: die
Foto-Trajektorie kollidiert nachweislich (7 538 Samples, 278 rote
Intervalle, min. −99 mm, Verursacher link5/link2/link4) — taugt als
Regressions-Fixture für S1/S2. Travel-Tunneling real (Sprünge bis ~1 m je
Sample-Schritt), Druckzüge dicht (p99 20 mm) — v1-Grenze bleibt, Befund
soll Travel als „nicht lückenlos geprüft" beschriften.

**Doku:** Protokoll `docs/spikes/S0_kollision_python_fcl.md`; Nachtrag in
ADR-024 (Revisionstrigger „Spike scheitert" abgeräumt). Nächster Schritt:
Scheiben S1–S6 aus PRD #124 schneiden.

## 2026-07-08 — S1a: Kollisions-Geometrie-Artefakt je Glied (Issue #125, ADR-024)

**Frage:** Wie legt der Core die Urteilsgeometrie (VHACD) + Breitphasen-Hülle
je M1013-Glied ab, sodass sie deterministisch, geo-frei importierbar und aus
dem Roboterkatalog auffindbar ist — ohne Simulations-Einbau in dieser Scheibe?

**Alternativen:**
- *Ablageformat:* NPZ/GLB (kompakt) vs. **JSON** (gewählt). NPZ ist über den
  Zip-Zeitstempel nicht byte-deterministisch, GLB backt Normalen/Nodes ein;
  JSON mit `sort_keys` + gerundeten Vertices ist garantiert bitgleich und
  diffbar. Kosten: 3,6 MB je Roboter — akzeptabel für ein Einmal-Derivat.
- *Rundung:* 6 Dezimalen (wie GLB-Skript) vs. **3 Dezimalen** (gewählt) —
  Mikrometer, weit unter der 5,5-mm-Toleranz, halbiert grob die Dateigröße.
- *VHACD-Determinismus:* Default `asyncACD=True` verworfen (parallele
  Zerlegung nicht reproduzierbar) → **`asyncACD=False`**, übrige Parameter =
  trimesh-Defaults (mit denen Spike S0 die ±5,5 mm gemessen hat); zweifacher
  Lauf byte-gleich verifiziert.
- *Katalog-Bindung:* eigenes `RobotDef`-Feld vs. **additive `collision_geometry`-
  Referenz**, die die Ladefunktion direkt aus dem Katalog-JSON liest (RobotDef
  unangetastet → Bestand lädt byte-gleich, Feld ist optional im Schema).
- *Modulschnitt:* schwere Geo-Importe (`trimesh`, `vhacdx`) **lazy** in den
  Funktionen statt auf Modulebene → Core startet ohne `fgc-core[geo]` sauber,
  `_require_geo()` meldet freundlich `pip install fgc-core[geo]`. Zerlegung
  `decompose_link` ist rein (Arrays rein, Dict raus, keine Datei-I/O); das
  URDF-/DAE-Lesen + Schreiben lebt im Offline-Skript.

**Entscheidung:** Neues Modul `fgc.collision.robot_geometry` (Dataclasses
`LinkCollisionGeometry`/`RobotCollisionGeometry`, `decompose_link`,
`load_robot_collision_geometry`) + Offline-Skript
`core/scripts/convert_robot_collision.py` (Muster `convert_robot_meshes.py`,
Offset-Formel `worldV = frames[i]·v` **importiert**, nicht kopiert). Derivat
unter `robots/collision/doosan_m1013/` (7 Glied-JSONs + `manifest.json` mit
Provenienz: Upstream-Commit, VHACD-Parameter). Katalog referenziert additiv.
`python-fcl`/`mapbox-earcut`/`vhacdx` in `fgc-core[geo]`.

**Begründung:** Determinismus + byte-gleiche Ablage sind die harte Anforderung
(Goldens, ADR-024-Konsequenz) — JSON+`sort_keys`+`asyncACD=False` liefern sie
am direktesten. Die Zweiteilung Hülle (untere Schranke) / VHACD (Urteil) ist
genau das S0-Rezept; pytest sichert beide Eigenschaften an bekannten DH-Posen
(Hülle ⊇ Roh-Mesh; VHACD-Formtreue p99 ≤ 5,5 mm, gemessen 4,1 mm auf link_2).
Kein README-Abschnitt — nutzer-sichtbar erst mit S3 (Muster #90).


## 2026-07-08 — Kollisionskern S1b: Druckstand + Zweiphasen-Check (Issue #126, ADR-024)

**Frage:** Wie baut der Core-Kollisionskern (a) den schichtweise wachsenden
**Druckstand** als Hindernissatz und (b) den **Befund je Sample** (min. Abstand
+ Verursacher) — rein, deterministisch und schnell genug für den automatischen
Befund je Simulation (Foto-Trajektorie 25 217 Samples)?

**Entscheidung:** Zwei reine Module (kein I/O, kein Schema-/API-Change — das ist
S2). `fgc.collision.druckstand`: `DruckstandSpec` → `build_obstacle_set(spec, L)`
liefert je **Schicht** einen `ObstacleSet` (frühere Teile voll, aktuelles Teil
als **Footprint-Prisma** = echter Slicer-Umriss aus `geometry.section.section_at`
extrudiert bis `L·layer_height`, Boden, zuschaltbarer Kontext; Modul-Variante nur
Modul + Arbeitsfläche). `obstacle_provider` cacht je Schicht (Rebuild je Schicht,
nicht je Sample). `layer_per_sample` bindet die Schicht **aus dem Toolpath**
(Bisektion über `target_times`, wie die io-Zeitreihe) statt aus einer TCP-Näherung
(Spike-Lehrgeld S0). `fgc.collision.check.find_collisions`: Link-Frames (FK,
extern) → über `simulation.transform.compose(base, link)` (die eine Transform-
Stelle) in Weltkoordinaten, dann je Glied zweiphasig gegen die Hindernisgruppen;
Selbstkollision nur `|i−j| ≥ 2` (`nonadjacent_pairs`), Basis (Glied 0) von der
Hindernisprüfung ausgenommen (Basis↔Boden = erlaubter Dauerkontakt), Endeffektor
als **provisorische** konvexe Tool-Hülle am TCP.

**Alternativen / Abwägungen:**
- *Breitphase: per-Glied-Hüllendistanz (Nachtrag ADR-024) vs. **AABB-Filter je
  Glied** (ADR-024 Punkt 1).* Beide sind untere Schranken (AABB ⊇ Hülle ⊇ Mesh,
  nie fälschlich sicher). Gemessen: per-Glied-Hüllen-`min_distance` kostet 6–7
  fcl-Aufrufe/Sample → **146 s**; eine **kombinierte** Hüllen+VHACD-Abfrage
  (2 Aufrufe/Sample) → **117–146 s** (das 384-Stück-VHACD-Query + das Setzen
  aller 384 Stück-Transformationen je nahem Sample dominieren, und diese
  Foto-Bahn ist ~100 % nah). Gewählt: **numpy-AABB-Breitphase** (Ecken durch die
  Pose transformiert, rein rechnerisch, keine fcl-Kosten) → VHACD-Urteil **nur**
  für Glieder, deren AABB-Lücke ≤ Sicherheitsabstand ist → **29,8 s** für
  25 217 Samples (Spike-Referenz 44 s, Schwelle < 60 s). Die #125-Hülle liefert
  die AABB-Bounds und bleibt die tightere untere Schranke des Eigenschafts-Tests.
- *Grün-Distanz für ferne Glieder:* die AABB-Lücke (untere Schranke) wird als
  Distanz berichtet — konservativ (nie zu optimistisch), Klassifikation nie
  fälschlich sicher; die exakte VHACD-Distanz nur im Nahbereich (dort zählt sie).
- *Determinismus:* python-fcl liefert bei Wiederholung **bitgleiche** Distanzen
  (Spike S0) — die gesamte Distanzsequenz reproduziert byte-genau (Golden
  `core/tests/goldens/collision_check_slice.json`). Die signierte Distanz
  durchdringender Paare ist history-abhängig (EPA-Warmstart), aber je fixer
  Sequenz reproduzierbar; deshalb prüft der Golden die *Sequenz*, nicht die
  Invarianz einer isolierten Einzelpose.
- *Freizone:* nicht ins Prisma geschnitten (Boolesche Mesh-Operation, nicht-
  deterministisch/langsam), sondern als Radius um den Druckpunkt, den `check`
  je Sample am nächsten Punkt der ausgenommenen (wachsenden) Gruppe auswertet —
  Rebuild bleibt je Schicht.
- *Performance-Anker:* ohne Endeffektor (wie der Spike) und ohne Selbstkollision
  gemessen (beide separat getestet); die Foto-Bahn kollidiert real (7557 rote
  Samples, deckungsgleich mit dem Spike-Befund 7538).

**Begründung:** Der AABB-Filter ist genau der in ADR-024 Punkt 1 vorgesehene
billige Breitphasen-Filter; er hält die exakten fcl-Abfragen auf nahe Paare
begrenzt und bringt die pathologische 100-%-nah-Foto-Bahn unter die 60-s-Marke,
ohne die konservative Garantie (keine Fehlklassifikation „sicher") aufzugeben.
Kein README-Abschnitt — nutzer-sichtbar erst mit S3 (Akzeptanzkriterium #126).

## 2026-07-08 — Kollisions-Befund additiv ins Trajektorien-Schema + Simulations-Einbau (Issue #127, ADR-024, PRD #124)

**Frage:** Wie wandert der Kollisions-Befund (aus #126) so ins Trajektorien-
Artefakt und in die Simulation, dass er **automatisch bei jeder Simulation**
(Abschnitt wie Modul) entsteht, ohne die Altläufe zu brechen und ohne je die
Simulation zu kippen (Befund, kein Gate)?

**Entscheidung / Umsetzung:**
- *Ein optionaler `meta.collision`-Block, `samples` unangetastet.* Der ganze
  Befund liegt additiv unter `meta.collision`; die **Abstandskurve**
  (`distances_mm`) und der **Verursacher** je Sample (`causer_link`/
  `causer_against`) liegen als zu `samples` **parallele Arrays** dort — so bleibt
  `samples` byte-gleich und Altläufe (ohne den Block) validieren unter dem
  erweiterten Schema unverändert. Verworfen: neue Felder in `samples[]` — hätte
  jedes Sample geändert und die Byte-Gleichheit der Bestands-Bahn gebrochen.
- *`Infinity` → `null`.* Glieder außerhalb der Breitphase melden in `check`
  Distanz `inf`; das ist **kein gültiges JSON** (der Schreiber verbietet
  NaN/Infinity, Lehre aus dem #62-NaN). Der Befund mappt `inf`→`null`
  („nicht gemessen, sicher grün") statt eines irreführenden Sentinel-Werts.
- *Fail-soft an einer Stelle.* `fgc.collision.finding.build_section_finding` ist
  die eine Tür „Trajektorie + Toolpath + Teil-Mesh rein, Befund raus"; fehlt die
  `collision_geometry`-Referenz (Altprojekt/Roboter ohne #125-Artefakt), liefert
  sie `None` (Befund fehlt schlicht — **kein** `null`-Füllen). `simulate_section`
  kapselt jeden weiteren Fehler zu `None` (Geo-Extras fehlen, Check-Fehler) →
  die Trajektorie entsteht immer. Regressionsanker als Test abgesichert.
- *Schicht + Travel-Kennzeichnung aus dem Toolpath.* Die Schicht je Sample kommt
  über `druckstand.layer_per_sample` aus der Target-Zeitachse (`Trajectory.
  target_times`, neu — **nicht serialisiert**, nur zur Laufzeit weitergereicht),
  nicht aus einer TCP-Höhen-Näherung. Travel-Abschnitte werden analog aus der
  Target-`kind` verdichtet als `travel_intervals` markiert
  („nicht lückenlos geprüft": Travel springt bis ~1 m je Schritt, Spike S0).
- *Konfig-Echo mit `provisional`-Geist.* `CollisionConfig`
  (Sicherheitsabstand 50 mm aus `check`, Freizone-Platzhalter **40 mm**) ist an
  `simulate_section` übergebbar (konfigurierbar, US 4) und wird als
  `config`-Echo mitgeschrieben, `provisional: true` wie bei den Prozessfenster-
  Karten (bis S1/S4 gemessene Werte liefern).
- *„Alle Module" ist kein eigener Backend-Pfad.* Der Sequenz-Knopf „Alle Module"
  (Viewer, #97) spielt bereits simulierte Teile ab und ruft je Teil dieselbe
  `simulate_section`-Tür (auch für Modul-Jobs, `plan.kind`). Das Verdrahten von
  `simulate_section` deckt damit beide Arten ab; der `mode` steuert den
  Druckstand (Abschnitt: Boden/Podest; Modul: nur wachsendes Modul + Arbeits-
  fläche). Der zuschaltbare **Gebäudekontext** wird im Echo geführt, das Kontext-
  Mesh selbst folgt einer späteren Scheibe.

**Determinismus / Fixture:** Gleicher Lauf ⇒ bitgleicher Befund (python-fcl
deterministisch + stabile Rundung, `ROUND_DECIMALS=3`). Die Foto-Trajektorie
`runs/20260708-161603_slice_Denkmal` dient als Regressions-Fixture; Golden ist
Intervall-Anzahl + min. Abstand (`core/tests/goldens/collision_finding_denkmal.json`,
`slow`). Kein README-Abschnitt — nutzer-sichtbar erst mit S3 (Akzeptanzkriterium).

## 2026-07-08 — Kollisionskontrolle S3: Replay-Darstellung im Viewer (Issue #128, PRD #124, ADR-024)

**Frage:** Wie zeigt der Viewer den `meta.collision`-Befund (S1a/#127) im Replay,
ohne ADR-007 zu verletzen (keine Viewer-Geometrieurteile) — und ohne Altläufe
oder die bestehende Platzierungs-Ampel zu stören?

**Entscheidung / Begründung:**

- *Alles verbatim, nichts Urteilendes.* Die neue reine Ableitung
  `viewer/src/ui/collision-state.ts` liest den Befund **nur** aus: Glied-Status
  per **Lookup im gelieferten `intervals`** (kein Neu-Urteil aus Abstand vs.
  Sicherheitsabstand), verursachendes Glied aus `causer_link`, Marker-Zeiten aus
  den Sample-`t_s` (reine Zeit-Abbildung, „Darstellungsmathematik"). So bleibt
  das Urteil im Core (ADR-024), der Viewer zeigt.
- *Abwesenheit = Status quo (US 25, Regressionsanker).* Fehlt `meta.collision`
  (Altlauf, Lauf ohne Kollisionsgeometrie — Block fehlt ganz, **kein** `null`),
  liefern alle Ableitungen `null`/leere Listen; die ehrliche
  „keine Kollisionsprüfung"-Zeile bleibt, keine Marker/Badges, kein Absturz. Als
  vitest-Regression abgesichert.
- *Getrennter Badge-Kanal — Platzierungs-Ampel bit-identisch.* Das
  Kollisions-Badge je Teil ist ein eigenes Feld (`PartEntry.collision_badge`),
  getrennt von `ampel` (erreichbar/nicht). Der Platzierungs-Ampel-Pfad wurde
  nicht angefasst; ein vitest-Anker prüft, dass ein rotes Kollisions-Badge die
  grüne Platzierungs-Ampel nicht kippt.
- *⚙-Sicht-Schalter für Druckstand + Abstandszahl.* Beide neuen Anzeigen hängen
  als `ToggleSpec`-Einträge im bestehenden ⚙-Menü (kein DOM-Handstricken):
  **Druckstand Standard aus** (aus lässt das Replay bit-gleich), **Abstandszahl
  Standard an**. Glied-Einfärbung/Marker/Badge sind dagegen immer sichtbar,
  sobald ein Befund vorliegt — sie sind der Kern der Scheibe, kein Sicht-Schalter.
- *Wachsender Druckstand als reine Prisma-Spec.* `render/druckstand-spec.ts`
  (vitest) wächst entlang der Höhe (z) mit dem Druckfortschritt (Zeit/Dauer,
  dieselbe Abbildung wie der wachsende Strang); `render/druckstand.ts` ist die
  dünne three.js-Hülle. Volle Box aus der Toolpath-Bounding-Box.
- *Einzel-Glied-Einfärbung braucht eigene Materialien.* `ArmView` hatte je ein
  **geteiltes** Link-/Joint-Material und ein Halter-Material — damit hätte ein
  Highlight alle Glieder getönt. Umgestellt auf **Material je Glied/Halter**, so
  färbt `setLinkHighlight` genau das verursachende Glied (Emissive rot/gelb).
- *Tiefe Verdrahtung am In-place-Abschnitts-Replay; Sequenz/Modul nur Badges.*
  Glied-Einfärbung + Abstandszahl + Druckstand hängen am kanonischen
  `showRunInner`-Player (Fokus-Abschnitt); Sequenz (#27) und Modul-Replay (#97)
  sammeln je Teil den Befund fürs Palette-Badge und setzen das Player-Badge, ohne
  das Replay-Verhalten bei ausgeschalteten Schaltern zu ändern.

Reine Sicht (ADR-007) — keine neue Kinematik, kein neues Skalarmaß.

## 2026-07-08 — Kollisionskontrolle S4: IK-Konfiguration wählbar end-to-end (Issue #129, PRD #124, ADR-024/020)

**Frage:** Wie wird der IK-Lösungszweig (Schulter/Ellbogen/Handgelenk) *wählbar* —
persistiert, gefiltert, angezeigt — ohne die heutige Bahnwahl zu verändern?

**Alternativen:**
- *Weiche Präferenz (Seed statt Filter):* die Vorgabe nur als Startlösung an
  `select_along_path` geben. Verworfen (ADR-024): nicht erklärbar („warum hängt
  der Ellbogen trotz Vorgabe wieder unten?"), schwer testbar.
- *Eigene Schreib-Route/Artefaktfeld:* verworfen — die process-params-Schreibstelle
  (`set_process_params`, ADR-016) trägt bereits slice/orientation global + je Teil;
  eine dritte Gruppe reiht sich additiv ein, keine neue Route.
- *ik_config als eigene Section-Mechanik:* verworfen — `resolve_section_params`
  löst die Gruppen generisch; `ik_config` einfach in `SECTION_OVERRIDE_GROUPS`
  aufgenommen (Strings statt Zahlen, „gesetzt" = nicht None). Der geteilte
  Golden-Fall (Py↔TS-Parität) bekam ik_config-Fälle.

**Entscheidung:** Drei Tri-State-Schalter (auto/Zustand A/Zustand B, Default auto),
persistiert wie ein Slicing-Parameter: global (`process_params.ik_config`) + je Teil
(`process_params.sections[id].ik_config`, #92-Gilt-für). Übersetzung Block→Filter:
`IkConfigFilter.from_block` („a"→Bit 0, „b"→Bit 1, fehlend→auto). Der Filter läuft
**hart** in `select_along_path` (neuer Parameter `config_filter`), durchgereicht über
`build_motion`/`build_trajectory`; `simulate_section` baut ihn aus dem *effektiven*
ik_config des Abschnitts. Unter der Vorgabe unerreichbare Bahnpunkte → Warnung
`ik_config` (neuer `WarningKind` + Trajektorien-Schema-Enum), Target ohne Lösung,
kein Gate.

**Begründung / Regressionsanker:** `IkConfigFilter.is_auto` short-circuitet den
Filter komplett — `auto/auto/auto` (bzw. `config_filter=None`) lässt die
Nächste-Nachbar-Wahl **bit-identisch** wie bisher; ein expliziter Test vergleicht
ohne Filter / `None` / all-auto Ziel für Ziel (Gelenke, Konfiguration, Warnungen).
Schema additiv/sparse (`ik_config_overrides`-$def, `enum ["a","b"]`), Altprojekte
laden byte-gleich; ein Abschnitts-Override bumpt nur den Pro-Abschnitts-Zähler (#83),
eine globale Änderung die `process`-Revision. Der Singularitäts-Advisor-Config-Flip
wird damit anwendbar (ADR-020-Revisionstrigger erfüllt). Viewer: reine Zustandslogik
`ik-config-state.ts` + dünnes DOM (Accordion „IK-Konfiguration", drei `<select>` im
ProcessParamsPanel), vitest-Anker für die per-Teil-Vererbung.

## 2026-07-08 — Kollisionskontrolle S5: Kollisions-Advisor mit gerankter Optionsliste (Issue #130, PRD #124, ADR-024 Punkt 5, Muster ADR-020)

**Frage:** Wie berät ein Advisor zu Kollisionsbefunden, wenn — anders als beim
Singularitäts-Advisor (ADR-020) — nicht *ein* Vorschlag, sondern ein **Menü**
gangbarer Optionen gefragt ist, und die Bewertung je Kandidat eine teure
Neu-Simulation kostet?

**Alternativen:**
- *Parallel-Metrik (billiger Ersatz-Score statt Neu-Simulation):* verworfen
  (ADR-024) — der Advisor muss dieselbe Wahrheit bewerten wie die Anzeige, sonst
  driftet „Advisor sagt besser" von „Befund sagt schlechter". Also **dieselbe**
  `meta.collision`-Kette (#127) je Kandidat, keine zweite Metrik.
- *Automatisch bei jeder Simulation mitlaufen:* verworfen — zu teuer (je Hebel eine
  Neu-Simulation); der Advisor läuft **auf Knopfdruck**. Der *Befund* entsteht
  weiterhin automatisch, die *Beratung* nicht.
- *Eigener Apply-Pfad je Hebel:* verworfen (ADR-016) — jede Option trägt die
  Nutzlast einer **bestehenden** Schreibstelle (`process-params` für ik_config bzw.
  Kipp/Lead-Orientierung, `placement-override` für die Platzierung); das Anwenden
  ist ein dünner Aufruf dieser Setter, kein neuer Schreibweg.
- *Advisor rechnet die Simulation selbst:* verworfen — das reine Modul
  `fgc.collision.advisor` ist über ein `simulate`-Callable **entkoppelt** (DOM-/IO-/
  Geo-frei, schnell + isoliert testbar mit synthetischem `simulate`); die Aktion
  `advise_collision` füttert die echte Kette hinein.

**Entscheidung:** `fgc.collision.advisor` (rein) baut das deterministische Hebel-Menü
(IK-Konfiguration / Kipp-Lead-Sweep / Platzierung, absolute Overrides + Schreibstellen-
Nutzlast), re-simuliert jeden Kandidaten über das übergebene `simulate` und rankt die
**Verbesserer**: `improves` = nie mehr Kollisions-Samples, weniger Kollisionen ODER
minimaler Abstand um > 1 mm gewachsen (über der Befund-Rundung). Reihenfolge:
kollisionsfrei zuerst, darunter größte Marge, dann feste Kandidatenreihenfolge als
stabiler Tiebreak. Damit `simulate_section` und der Advisor **bit-identisch** dieselbe
Slice+Trajektorien+Befund-Kette fahren, wurde deren Kern in `_slice_and_simulate_section`
extrahiert (die eine Rechen-Tür; `simulate_section` persistiert danach, der Advisor
liest nur den Befund). Route `POST …/collision-advice` (dünn, ADR-014); das Anwenden
läuft im Viewer über die bestehenden Routen.

**Begründung / Anker:** Vorher/Nachher-Nachweis je Hebel + „nur Verbesserer erscheinen"
+ deterministisches Ranking als schnelle pytest mit synthetischem `simulate`
(`test_collision_advisor.py`); der reale End-to-End-Durchstich (echte Neu-Simulation
über die Aktion, doosan_m1013 mit Kollisionsgeometrie) als `slow`-Test
(`test_collision_advisor_action.py`) — nie die 25k-Foto-Trajektorie. Die Extraktion
der Kern-Tür ließ die bestehenden `simulate_section`-Tests unverändert grün
(Regressionsanker: kein Verhaltensdrift der echten Simulation). Viewer:
`collision-advisor-state.ts` (rein, vitest) + dünne `collision-advisor.ts`, die die
Optionsliste statt eines Einzelvorschlags rendert; der Advisor bleibt global (die #92
Ausgrau-Matrix unverändert).

## 2026-07-08 — Kollisionskontrolle S6: Platzierungs-Grob-Check + Gebäudekontext-Schalter (Issue #131, PRD #124, ADR-024 Konsequenz „Ausbaustufe Grob-Check")

**Frage:** Wie fließt eine Kollisionsbewertung in den Platzierungs-Optimalvorschlag,
ohne dessen Kern (`evaluate`/`suggest`) anzutasten und ohne die #98-Sortierung zu
verändern, solange nichts kollidiert? Und wie wird der Gebäudekontext-Check am
Druckjob zu-/abschaltbar, additiv und byte-kompatibel?

**Alternativen (Grob-Check):**
- *Exakte Mesh-Distanz je Kandidat (wie die Simulation):* verworfen — zu teuer, der
  Optimalvorschlag muss interaktiv bleiben. Stattdessen wenige Stichproben-Posen +
  Breitphasen-Hülle (untere Distanz-Schranke, #125), kein python-fcl.
- *Gate statt Befund (kollidierende Kandidaten verwerfen):* verworfen (ADR-024) —
  Befund, kein Gate; die Platzierungs-Ampel behält ihre Bedeutung. Kollision wird
  ein zusätzlicher, **vorderster** Sortier-Schlüssel: kollidierend rutscht hinter
  frei, mehr nicht.
- *Alle Armglieder + Endeffektor testen:* verworfen — Handgelenk (4/5) und Flansch/
  Endeffektor sitzen prozessbedingt an der Wandfront (y≈0) und würden chronisch
  fehlwarnen (empirisch: „alles kollidiert"). Nur Rotator/Oberarm/Ellbogen (Glieder
  1–3) tauchen bei zu naher/hoher Aufstellung hinter die Druckebene — genau der
  Ellbogen-durch-die-Wand-Fehler des Auslöser-Fotos.
- *Kern von `evaluate`/`suggest` erweitern:* verworfen (Modularität) — der Grob-Check
  ist ein eigenes reines Modul (`fgc.collision.coarse`), in `suggest` als optionales
  Prädikat eingehängt; ohne Prädikat (bzw. Roboter ohne Kollisionsgeometrie) ist der
  zusätzliche Sortier-Schlüssel konstant → #98 bit-identisch.

**Alternativen (Kontext-Schalter):**
- *Neue Schreibstelle/Revisions-Bump:* verworfen (ADR-016/wie #81) — dünne Route
  `PUT …/context-check` als `stand-mode`-Spiegel + Setter `set_context_check_for_job`
  über die eine Schreibstelle `fgc.project`; kein Revisions-Bump (wirkt erst bei der
  nächsten Simulation).
- *Feld immer schreiben (auch false):* verworfen — sparse/additiv: „aus" entfernt das
  Feld, Altprojekte laden byte-gleich.
- *Nur das Konfig-Echo kippen, ohne echte Prüfung:* verworfen — der Schalter soll die
  Simulation wirklich treiben. `build_section_finding` nimmt den Gebäudekontext
  (context.json, Issue #17) bei „ein" und Zerlegungsart Abschnitt als zusätzliches
  Hindernis auf, in Abschnitts-lokale Koordinaten transformiert (dieselbe Wand-Basis
  wie das Teil-Mesh). Bei Modul gegenstandslos (ADR-022) — dort ignoriert, im Viewer
  ausgeblendet.

**Entscheidung:** (1) `fgc.collision.coarse.path_collides` — wenige Posen (grobes
Raster), Breitphasen-Hüllen der Glieder 1–3 als AABB gegen das Wandvolumen hinter der
Front (Eindringtiefe > 20 mm). `suggest(collision_free=…)` sortiert kollisionsfrei
zuerst, dann #98; `suggest_placement` baut das Prädikat fail-soft (keine Geometrie →
None → bit-identisch). (2) Schema-Feld `check_building_context` (bool, additiv/sparse);
`simulate_section` leitet daraus `CollisionConfig(context_enabled=…)` ab (bei Modul
erzwungen aus) und reicht die transformierte Kontextgeometrie an die Befund-Tür.

**Begründung / Anker:** `test_placement_coarse.py` — „kollidierender Kandidat rutscht
hinter frei" + „None/all-free bit-identisch zu #98" (expliziter Regressionsanker) +
nachweisliche Grob-Kollision mit echter M1013-Breitphasen-Geometrie (Fixture-Muster:
Standoff 700 frei, 300 kollidiert) + Workstation-Grid-Integration. `test_collision_finding.py`
— Kontext nur bei „ein" geprüft (aus + Kontextgeometrie == kein Kontext, byte-gleich),
Modul gegenstandslos. `test_decompose.py` — Setter additiv/sparse + Route persistiert &
restauriert. Viewer: `kontext-state.ts` (vitest) + dünner Checkbox-DOM im DruckplanPanel,
`ui_smoke.mjs`-Schritt (sichtbar bei Abschnitt, ausgeblendet bei Modul). Der reale
End-to-End-Durchstich der Kontext-Simulation bleibt manuell/`slow` — nie die 25k-Foto-
Trajektorie im Default-Lauf.

## 2026-07-09 — GUI-Start: Core-API mit `--reload` (Schutz gegen veraltete 8765-Instanz)

**Frage.** Nach einem `git pull` auf einem anderen Rechner war die Roboterliste
leer und Overlays wirkten veraltet. Ursache war *nicht* fehlender Code (der
Checkout war mit origin synchron), sondern eine seit dem Vortag laufende
Core-API auf Port 8765: `fgc.domain.load_schema` ist `@cache`-dekoriert, die
alte Instanz hatte also `robot.schema.json` aus ihrer Startzeit eingefroren und
wies die inzwischen (#125) um `collision_geometry` erweiterte
`robots/doosan_m1013.json` als schema-invalide ab → `/robots` = `[]`. Der
Start-Probe-Weg (`_probe_api`/`_startup_decision`) stuft eine solche Instanz als
`current` ein (sie kennt `/projects`) und ersetzt sie bewusst nicht — die Lücke:
`current` prüft nur Routenpräsenz, nicht den Code-/Schemastand.

**Alternativen.** (a) Beim Start immer den Port freiräumen/killen — verworfen:
die vorhandene, sorgfältige „busy≠stale"-Logik (Issue #39/#47, tötet nie einen
langsam antwortenden oder fremden Dienst) würde ausgehebelt. (b) Versions-/
Build-Signatur über einen Health-Endpoint vergleichen — mehr Oberfläche, für den
Ein-Nutzer-Forschungsstand unverhältnismäßig. (c) Den vom Launcher gestarteten
Server `--reload` geben, damit er dem Arbeitsbaum folgt.

**Entscheidung.** (c): `ensure_api_server` startet uvicorn mit `--reload`,
`--reload-dir` auf `core/src` + `schemas/` + `robots/` und
`--reload-include=*.json`; `uvicorn` → `uvicorn[standard]` (bringt `watchfiles`,
den event-basierten Reloader, der — anders als der Fallback-`StatReload`, nur
`*.py` — auch die validierten JSON-Stammdaten beobachtet). `runs/`/`projects/`
bewusst NICHT beobachtet (Reload-Sturm). Die Probe-/Entscheidungslogik bleibt
unangetastet.

**Begründung.** Praktisch jede inhaltliche Änderung fasst `.py` an → der
gestartete Server lädt neu und leert den Schema-`@cache`; reine JSON-Edits
greifen über `watchfiles`. Damit kann ein launcher-gestarteter Server nach einem
Pull nicht mehr auf altem Stand kleben. Restrisiko: eine *manuell ohne*
`--reload` gestartete Instanz altert weiter — dokumentiert, kein Launcher-Fall.
`test_viewer_launch_probe.py` unverändert grün (20).

**Nebenbefund (kein Code-Change).** Die Meldung „Slicing schräg" bei
`Kellerwand 26 cm` ist kein Fehler des aktuellen Codes: Nachrechnen der
Viewer-Mathematik (`wallFrameFromPoints`→`cutPlaneSpec`→`applyWallFrame`) auf der
echten Wandgeometrie ergibt Höhenschnitte bei konstantem Welt-Z (exakt
horizontal) und den Längsschnitt exakt vertikal, Rahmen deckungsgleich mit der
Core-Zerlegung (`decompose.json`: x −1250…+1250 mittig, z 0…2459 ab Wandfuß, 6
Abschnitte). Die schräge Optik ist die perspektivische Ansicht einer im Grundriss
um 32° gedrehten Wand; „Auf Wand einpassen" bzw. eine wandsenkrechte Kamera lässt
die Schnitte gerade erscheinen.

## 2026-07-09 — Korrektur: „Slicing schräg" WAR ein Bug — #113-Sockel-Streifen verfälschte den PCA-Wand-Frame

**Korrektur zum Nebenbefund im Eintrag weiter oben (2026-07-09, GUI-Start):**
die Einschätzung „schräge Optik = Perspektive, kein Code-Fehler" war falsch.
Die dortige Nachrechnung fütterte die PCA nur mit den Wand-Vertices aus der
GLB — der *lebende* Viewer füttert mehr.

**Frage.** Nutzer-Screenshot (Kellerwand 26 cm, 32° im Grundriss): Schnittebenen
und Abschnitts-Quader liegen sichtbar verdreht zur Wand, ein zweiter „dicker"
Quader erscheint ~30° gegen die Wand gedreht, Basis-Marker verstreut.

**Befund.** Seit dem Clay-Studio-Redesign (#113, 2026-07-08) hängt an jedem
Wand-Mesh ein Kind-Mesh: der Eignungs-Sockelstreifen (`model.ts`), dessen
BoxGeometry aus der **achsparallelen lokalen Bbox** kommt (bei gebackenen
Welt-Vertices = Welt-AABB, 2258×1545 statt 2500×260). `wallFrameFromObject`
(#99, `wall-frame.ts`) sammelt per `traverse` **alle** Kind-Mesh-Vertices ein —
die acht AABB-Ecken des Streifens verzerrten die PCA: yaw 32°→22,6°, Länge
2500→2732, Dicke 260→**2339 mm** (numerisch am echten Modell verifiziert).
Alle Overlays am Wand-Frame (Schnittebenen, Abschnitts-Quader, Platzierungs-
Marker, Live-Vorschau) lagen dadurch schräg — #113 hatte #99 stillschweigend
regressiert. (Die Kanten-LineSegments sind harmlos: `isMesh`-Filter.)

**Alternativen.** (a) Streifen nicht als Kind des Wand-Meshs führen — verworfen:
er soll die Wand-Transform erben, Umhängen verkompliziert Fokus/Sichtbarkeit.
(b) In `wallFrameFromObject` nur das Wurzel-Mesh lesen — verworfen: die
Funktion soll Subtrees mit mehreren echten Geometrie-Meshes weiter tragen.
(c) Deko-Konvention: `WALL_DECORATION_FLAG` in `userData`, PCA überspringt
markierte Meshes.

**Entscheidung.** (c): `wall-frame.ts` exportiert `WALL_DECORATION_FLAG` und
übergeht markierte Kinder; `model.ts` markiert Sockel-Streifen **und** Kanten
(letztere zur Vollständigkeit der Konvention). Zwei Regressionstests in
`wall-frame.test.ts`: 32°-Wand mit Streifen → exakte Pose; Gegenprobe ohne
Flag → messbar gekippt (schützt den Test selbst). Viewer 734 vitest grün
(+2), tsc clean. Merke fürs Muster: **jedes neue Kind-Objekt an einem
Wand-Mesh braucht das Deko-Flag** — sonst wandert es in die Wand-Pose.

## 2026-07-09 — Grill: Platzierungsmodell nach Zerlegung — absolute Aufstellhöhen, Gesamtwand-Vorschlag entfällt

**Frage.** Nutzer-Befund am Zerlegung-Reiter (Kellerwand, 3 Reihen × 2 Spalten):
alle 6 Abschnitte melden identisch „seitl. 0 / Abstand 230 / Höhe 0 / 100 %",
die Basis-Marker schweben am Abschnittsfuß in der Luft, und nur die eine
„Gesamtwand-Basis" (vorschlag-1, ehrlich 24 %) reagiert auf Zerlegungsänderungen.
Ursache: `Section.as_surface` bewertet jeden Abschnitt als „kleine Wand für
sich" ab z=0 — die Platzierungssuche kennt die echte Höhenlage nicht, und
`stand_mode="floor"` klemmt die Höhe *abschnitts-lokal* (= Phantom-Podest am
Abschnittsfuß, für Reihe 2/3 physikalisch unmöglich: M1013 1,3 m Reichweite,
mobile_hub real 0–600 mm). Sim/Export rechnen konsistent mit der schwebenden
Basis (Plan ≠ Setup), aber Ampeln/Werte sind unter Boden-Modus falsch (100 %
statt rot) und der Aufstell-Toggle (#81/#100) ist für obere Reihen wirkungslos.

**Alternativen.** (1) Höhen-Semantik: (a) absolut über dem Boden + ehrliche
Bewertung an der echten Höhenlage; (b) abschnitts-lokal behalten, nur Anzeige
ehrlicher; (c) Hybrid mit drittem Modus „Gerüst/beliebig hoch". (2) Feld:
`stand_height_mm` absolut überall vs. lokal mit UI-Umrechnung. (3) Gesamtwand-
Vorschlag: abschaffen vs. nur vor der Zerlegung zeigen vs. behalten.

**Entscheidung (Grill mit Nutzer, 2026-07-09).** (1a) **Höhen absolut + ehrlich**:
Bodenniveau = Wandfuß; Suche/Bewertung sehen jeden Abschnitt an seiner echten
z0–z1-Lage; Boden-Modus = Basis absolut 0; erhöht-Modus rastert den realen
Workstation-Bereich absolut; obere Reihen werden ehrlich rot/teilerreichbar
(Befund, kein Gate). (2) **Feld absolut überall** (Artefakt, UI, freie
Overrides #94); Umrechnung ins abschnitts-lokale Sim-Frame (`local = absolut −
z0`, negativ erlaubt) an genau einer Naht (Setup-Komposition). Altprojekte
(durchweg 0) laden byte-gleich und bedeuten fortan korrekt „Boden"; veraltete
Sims fängt #83. (3) **Gesamtwand-Vorschlag abgeschafft** für Abschnitts-Jobs
(Nutzer: „verstehe nicht, wieso das überhaupt in Frage gestellt wird") — Panel,
`selected_placement`-Wahl und Gesamtwand-Marker entfallen; Singularitäts-
Advisor verankert am Fokus-Abschnitt (Muster #130); Schema-Felder bleiben
lesbar. Viewer: Marker/Fokus-Roboter auf echter Basis-Höhe, Podest-Sockel bei
> 0, absolute Aufstellhöhe in der Teil-Liste. **Regressionsanker:** Reihe 1
(z0=0) bit-identisch (absolut ≡ lokal). Revidiert die abschnitts-lokale
Konvention aus ADR-022 → ADR-Nachtrag mit der Umsetzung.

**Out of scope (bewusst):** explizite Standort-Konsolidierung (ein Stellplatz
je Spalte); Reichweiten-bewusstes Auto-Rastern der Zerlegung.

## 2026-07-09 — Umsetzung #132: `z_offset_mm` an der WallSurface, Platzierungssuche je Höhenreihe, Naht in `_planned_setup`

**Frage.** Wie bekommt die Platzierungssuche/-bewertung die echte Höhenlage
eines Abschnitts (Entscheidung „absolute Aufstellhöhen", Eintrag oben) —
minimal-invasiv, ohne die Bewertungsmaschinerie zu duplizieren?

**Alternativen.** (a) Feld `z_offset_mm` an `WallSurface` (Default 0.0);
(b) zusätzlicher Parameter an `evaluate`/`suggest`; (c) eigener
Abschnitts-Bewertungspfad.

**Entscheidung.** (a) **`z_offset_mm` als Feld der `WallSurface`** (Default 0.0
= alte Konvention, alle bestehenden Konstruktor-Aufrufe unverändert):
`_flange_targets` legt die z-Stichproben auf `z_offset..z_offset+height`,
`Section.as_surface` setzt per Default `z0_mm` (Art „modul" explizit `0.0` —
der Modulfuß liegt auf der Arbeitsfläche, ADR-022). So fließt die Höhenlage
durch `suggest`/`evaluate`/Grob-Check (`coarse._wall_box`) ohne neue
Signaturen. Dazu drei bewusste Detail-Entscheidungen:

1. **Platzierungssuche je Höhenreihe** in `propose` (statt einer Suche für
   alle Zellen): Zellen einer Reihe teilen Größe + Höhenlage → eine Suche je
   Reihe, Spalten erben sie (deterministisch, n_h statt 1 Suchen). Unterste
   Reihe bit-identisch zu vorher (Regressionsanker).
2. **`_grid_counts`/`_reachable_fraction` bleiben am Boden (z_offset 0):**
   die Rasterverfeinerung ist eine Zellgrößen-Heuristik („wie groß darf eine
   Zelle sein"); würde sie an der echten Höhenlage messen, liefe sie im
   Boden-Modus für unerreichbare obere Reihen bis an den Teilungs-Cap (16×16-
   Explosion), obwohl Teilen dort nichts verbessert. Unerreichbar schneidet
   trotzdem — Befund, kein Gate, die Ampel sagt die Wahrheit.
3. **Die eine Umrechnungsnaht** Plan (absolut) → Sim-Frame (abschnitts-lokal)
   ist `fgc.pipeline.actions._planned_setup(..., z_offset_mm=section.z0_mm)`:
   `stand_height_local = stand_height_abs − z0`, negativ erlaubt; Art „modul"
   und ganze Wand übergeben 0.0 (byte-gleich).

Schemas: nur `description` von `stand_height_mm` präzisiert (absolut, Boden =
Wandfuß), keine Strukturänderung — Altprojekte (`stand_height 0`) laden
byte-gleich. ADR-022-Nachtrag geschrieben; README-Abschnitt „Absolute
Aufstellhöhen" ergänzt. Tests: Regressionsanker z0=0 (Suche+Bewertung+Naht),
Reihe auf 1646 mm vom Boden nicht grün, mobile_hub-Höhen nur aus [0, 600],
Naht 400 abs bei z0 819.6 ⇒ lokal −419.6, oberer Abschnitt verankert Basis
bei z = −1300 im Sim-Frame.

## 2026-07-09 — Issue #133: Viewer zieht die absoluten Aufstellhöhen nach (Marker/Fokus-Roboter auf Basis-Höhe, Podest-Sockel, Beschriftung)

**Frage.** Seit #132 ist `stand_height_mm` absolut über dem Boden (= Wandfuß,
`wall.zMin` im Viewer-Wand-Frame) — der Viewer zeichnete Basis-Marker und
Fokus-Roboter aber weiter am **Abschnittsfuß** (`sectionMarkerPosition`:
`zFoot`), obere Reihen schwebten. Wo sitzt die Höhe künftig — im Marker-Bau
(`buildBaseMarker` hob die Scheibe intern um `stand_height` an) oder in der
Positions-Funktion?

**Alternativen.** (a) Marker-Position bleibt am Boden, `buildBaseMarker`
behält den internen Hub — dann zeigt `sectionMarkerPosition` nicht die Basis
und die Basis-Chips (`getWorldPosition`) klebten am Boden; (b) Position IST
die Basis: `sectionMarkerPosition` liefert `wall.zMin + stand_height_mm`
(absolut), der Gruppen-Nullpunkt von `buildBaseMarker` liegt AUF der Basis,
der Podest-Sockel hängt von der Basis bis zum Boden herab.

**Entscheidung.** (b). `sectionMarkerPosition` → `wall.zMin +
stand_height_mm`; `sectionBaseFrame` addiert die Aufstellhöhe **nicht mehr
doppelt** (Frame-z = Marker-z, Test verankert); `buildBaseMarker`: Scheibe
bei +20, Achsenkreuz +40, Sockel `−stand_height..0`. Die Box-/Wand-Aufrufer
(`baseMarkerPosition`, `placeBaseMarker`) heben ihre z-Lage um
`stand_height_mm` an — für die Aufstell-Sequenz (#27) bleibt die sichtbare
Scheibenhöhe dadurch **bit-identisch** (reiner Nullpunkt-Umzug).
Regressionsanker: unterste Reihe im Boden-Modus (stand_height 0) steht exakt
wie vorher; Boden-Modus ⇒ alle Marker stehen auf dem Boden vor ihrem
Abschnitt. Beschriftung überall **„Aufstellhöhe ü. Boden"** (Teil-Detail der
Palette, #94-Override-Feld, Befehls-Palette) + Tooltip „absolut über dem
Boden (= Wandfuß); 0 = Boden" — Werte weiter verbatim aus dem Core-Artefakt
(ADR-007), kein Core-/API-/Schema-Change. Viewer 741 Tests grün, tsc + vite
build clean.

## 2026-07-09 — Issue #134: Gesamtwand-Platzierungsvorschlag entfällt, Singularitäts-Advisor verankert am Fokus-Abschnitt

**Frage.** Der Job-Level-Platzierungsvorschlag der ganzen Wand (#22/#80:
`placements`/`selected_placement`, Panel „vorschlag-1/2/3 · Wählen/gewählt
(Plan)", cyan Gesamtwand-Basis-Marker) hat nach der Zerlegung keinen
Pipeline-Konsumenten mehr — Slicing/Sim/Export laufen über die
Abschnitts-Platzierungen; er speiste nur noch den Singularitäts-Advisor
(`actions.py`, `selected_placement`) und stiftete Verwirrung (24 % neben
sechs „100 %"-Abschnitten). Wie abschaffen, ohne Altprojekte zu brechen —
und woran verankert sich der Advisor danach?

**Alternativen.** (1) Advisor-Anker: (a) Fokus-Abschnitt per `section_id`
(Muster Kollisions-Advisor #130, `plan_for_job`), ohne Fokus freundlich leer;
(b) ohne section_id auf den ersten Abschnitt zurückfallen (wie #130);
(c) Advisor mit abschaffen. (2) Stale `section_id`: leer vs. Fallback erster
Abschnitt. (3) Viewer-Anwenden des Platzierungs-Hebels:
`evaluatePlacements`+`selectPlacement` (alt) vs. `setPlacementOverride` (#94).
(4) Core-Routen/Funktionen: löschen vs. bestehen lassen, nur nicht mehr rufen.

**Entscheidung.** (1a) + (2 leer): `advise_singularity(slug, job_id,
section_id)` rekonstruiert den Plan über `plan_for_job` (inkl. Overrides #94),
bewertet den Fokus-Abschnitt als Fläche an seiner echten Höhenlage
(`Section.as_surface`, #132; Art „modul" am Boden wie `decompose.evaluate`,
ADR-022) und antwortet ohne/mit stale `section_id` **freundlich leer** (kein
Fehler, kein stiller Abschnittswechsel — bewusste Abweichung vom
#130-Fallback, weil der Viewer den Fokus ohnehin reconciled und der Nutzer
sonst unbemerkt einen anderen Abschnitt beraten bekäme). Route
`singularity-advice` bekommt additiv `section_id` (Request+Response). (3)
Platzierungs-Hebel schreibt als **freie Override-Werte des Fokus-Abschnitts**
über `PUT …/placement-override` (#94, ADR-016) — `ApplyAction` im Viewer wird
`placement-override` (Spiegel Kollisions-Advisor); Kipp bleibt
`process-params`. Ohne Fokus zeigt „Prüfen" den Hinweis „Teil in der
Teile-Palette wählen" (reine Logik `focusHint`, vitest) — kein Core-Aufruf.
(4) Core-Funktionen (`evaluate_placements`/`select_placement`/
`suggest_placement`) + Routen bleiben bestehen (Altprojekte/API); der Viewer
ruft sie nicht mehr: `evaluatePlacements`/`selectPlacement`/`suggestPlacement`
+ `ScoredPlacement` aus `api/projects.ts` entfernt, „✦ Automatisch
vorschlagen" löst nur noch den Zerlegungsvorschlag aus, Panel
(`placement-scores`/`placement-status` + CSS), Gesamtwand-Marker
(`updatePlacementMarker`, `placeBaseMarker`) und `nextPlacementCounter`
gelöscht — die #93-Abschnitts-Marker (`placement-markers.ts`) sind unberührt.
Schema unverändert: `placements`/`selected_placement`/`placement_run` bleiben
lesbar, Altprojekt lädt byte-gleich (Test
`test_legacy_placement_fields_survive_reload_byte_identical`); eine erfasste
`placements`-Liste speist weiter die Override-Referenz-Dropdowns (#94a).
Bilanz: Core ruff clean, test_placement/test_singularity_advisor/test_project/
test_api 116 grün; Viewer tsc clean, 741 Tests grün, vite build clean.

## 2026-07-09 — Issue #135: Kollisionskontrolle + Replay folgen der absoluten Höhen-Semantik (Boden/Druckstand/Basis im echten Frame)

**Frage.** Die Simulation rechnet abschnitts-lokal (z ab Abschnittsfuß, #132-
Naht `_planned_setup`); Kollisions-Hindernissatz und Viewer-Replay kannten die
echte Höhenlage aber nicht: der Boden wäre am Abschnittsfuß gelandet (für obere
Reihen ist dort Luft bzw. die untere Reihe), frühere Teile fehlten ganz, und
das Replay von Abschnitt 3 (real ~1229–1844 mm) renderte am Wandfuß mit
schwebender Basis — dazu die Festtext-Statuszeile „(keine Kollisionsprüfung)"
neben Kollisions-Badge + Live-Abstand. Wo bekommt die Kette die z0-Lage her?

**Alternativen.** (1) Hindernisse: (a) additive Parameter an
`build_section_finding` (`section_z0_mm`, `earlier_parts`), Boden synthetisch
bei lokal −z0; (b) alles im Aufrufer in ein absolutes Frame umrechnen (Samples
verschieben — bräche die byte-gleichen `samples`); (c) Boden auch für z0 = 0
einführen. (2) Viewer-Hub: (a) `meta.section_z0_mm` additiv im Trajektorien-
Artefakt, eine Hub-Gruppe hebt die Replay-Szene; (b) der Viewer liest z0 aus
dem Zerlegungs-Artefakt (kann vom Lauf-Stand abweichen — stale). (3) Statuszeile:
Festtext behalten vs. verbatim aus `meta.collision` ableiten.

**Entscheidung.** (1a) + (2a) + (3 verbatim). Core: `build_section_finding`
bekommt additiv `section_z0_mm` (Default 0.0 = altes Verhalten) und
`earlier_parts` (Default leer); bei Art „abschnitt" und z0 > 0 kommt der reale
Boden als Slab mit Oberkante **lokal −z0** (`druckstand.ground_slab`, feste
6-m-Maße wie das #126-Golden-Fixture — deterministisch), die **früheren Teile**
(Druckreihenfolge, aus dem ohnehin geschnittenen `apply(mesh, plan)`) werden ins
abschnitts-lokale System des aktuellen Abschnitts verschoben (Konvention
`local −= center_x/z0` wie Teil-Mesh + Kontext #131) und als volle Hindernisse
geführt (`part0`, …). Für **z0 = 0 bleibt der Boden bewusst weg** — v1-Lehrgeld
#127 (Slab am Fuß = chronische Fehlwarnungen, Basis↔Boden ist erlaubter
Dauerkontakt; Link-1-Hülle liegt nur 56,8 mm über der Basisplatte, gegen 50 mm
Sicherheitsabstand) und zugleich der **Regressionsanker**: z0=0-Befund
bit-identisch (Test), Goldens #126/#127 strukturell unberührt (bauen ihren
Spec selbst). Der **Advisor** (#130) läuft über dieselbe `_SectionComputation`
(neues Feld `earlier_parts`) — keine Parallel-Metrik. `simulate_section`
persistiert additiv **`meta.section_z0_mm`** (nur Art „abschnitt"; Schema
additiv erweitert). Viewer: reine Spec-Fns in `trajectory/replay-anchor.ts`
(`sectionLiftMm` verbatim aus der Meta, `replayPedestal` = Sockelhöhe aus
`base_frame.z + Hub`); eine **Hub-Gruppe** `replay-lift` hebt Teil-Mesh, Bahn,
TCP, Arm, wachsenden Druckstand (#128) und den neuen **Podest-Sockel**
(`buildReplayPedestal`, Muster #133) um z0 — Altläufe ohne Feld: Hub 0,
bit-identisch. Die **Ganze-Wand-Sequenz** (#27) bekommt je Abschnitt eine
Hub-Gruppe + eine Arm-Hub-Gruppe, deren z je Schritt dem aktiven Abschnitt
folgt (der Sequenz-Basis-Marker stand seit #133 schon auf absoluter Höhe und
passt jetzt zur gehobenen Bahn). `resetRunState` detacht Arm/TCP/Druckstand
per `removeFromParent` (Eltern-agnostisch — die geteilten Arm-GLBs #41 dürfen
nicht in `clearWorld` laufen). Statuszeile: `replayStatusLine` (collision-state,
vitest) — mit Befund die Befund-Zusammenfassung, ohne Befund die ehrliche
Zeile; der Festtext in `simulation.ts` wurde neutralisiert („Replay startet …"),
Abschnitts- wie Modul-Replay setzen die abgeleitete Zeile beim Öffnen.

**Ehrlicher Randbefund (kein Fehlalarm):** ist eine obere Reihe vom Boden aus
komplett unerreichbar, friert die Bahn in der DH-Null-Pose ein, deren Handgelenk
~527 mm unter der Basisplatte hängt — gegen den realen Boden bei −z0 ist das
**ehrlich rot** (der eingefrorene Arm stünde im Boden). Der e2e-Test nutzt darum
das Nutzer-Szenario „obere Reihe, erhöht" (Podest-Override 1300): echte Bahn,
kein `ground`-Intervall. Out of scope (bewusst): x-Versatz der Spalten in der
Ganze-Wand-Sequenz (Abschnitte bleiben in x um ihre Mitte zentriert — Bänder
stapeln jetzt korrekt in z, Spalten überlagern sich wie bisher).

Bilanz: Core ruff clean; test_druckstand 13 (+2 neu), test_collision_finding 11
(+4 neu; 2 slow-Goldens deselektiert/geskippt — Fixture-Lauf fehlt lokal, sie
bauen ihren Spec ohnehin selbst), test_collision_check/advisor/advisor_action +
test_section_simulation 36 grün (inkl. 2 neuer e2e-#135-Tests); volle Core-Suite
**692 grün** (1 skip, 4 slow deselektiert), ruff clean; Viewer tsc clean,
**751 Tests grün** (+10: replay-anchor 9, replayStatusLine 3, −2 alte
Festtexte), vite build clean. Schema nur additiv (`meta.section_z0_mm`).

## 2026-07-09 — Druckjob-Mutation als deep Seam (Issue #119)

**Frage:** Jeder reine Druckjob-Setter in `core/src/fgc/pipeline/actions.py`
(`set_tool_for_job`, `set_workstation_for_job`, `set_stand_mode_for_job`,
`set_module_limits_for_job`, `set_placement_override_for_job`,
`set_process_params`, `select_placement`, `set_print_job`,
`set_context_check_for_job`) buchstabierte **wörtlich dieselbe Choreografie** aus:
`project_dir_for` → `project_lock` → `load_project` → Job suchen (14× byte-gleicher
`ValueError`) → Job in der Liste ersetzen → `write_project` → Result mit dem 4-Feld-
Kopf `(project_dir, project_path, artifact, job_id)`. Die eigentliche Fachlogik
(Feld setzen, Befund rechnen) waren 5–15 Zeilen in 60–90 Zeilen Verdrahtung; die
Revisions-Entscheidung (`bump_input` vs. „BEWUSST kein Bump" vs. `bump_section_input`)
lebte nur als Kommentar + Copy-Paste. Reiner Refactor gesucht, kein Verhaltenswechsel.

**Alternativen der Seam-Signatur:** (a) ein Context-Manager `druckjob_transaction(...)`,
der Lock hält und den Job herausgibt — nah am `with`-Idiom, aber der Aufrufer müsste
Lookup-Fehler und Job-Ersetzung weiter selbst schreiben (die Choreografie bliebe halb
draußen). (b) Ein Seam, der die Bumps als **Datenparameter** (`bump=None,
bump_sections=(), refresh=()`) nimmt und den Job selbst mutiert — scheitert an den
**konditionalen** Bumps (`set_placement_override`/`set_process_params`/#25-Referenz
diffen alt gegen neu, die Entscheidung *ist* Fachlogik). (c) **gewählt:** ein
**Mutator-Callback** `dict|None -> JobMutation`, der den Job verändert **und** die
Veraltungs-Semantik *deklariert* (`bump_inputs`/`bump_sections` als Tupel), plus einen
`befund`-Rückkanal; der Seam `mutate_print_job(slug, job_id, mutator, *, upsert=False,
projects_dir=None) -> MutationOutcome` besitzt Lock/Lookup/Bump-Anwendung/Write.

**Entscheidung/Begründung:** (c), umgesetzt in `core/src/fgc/project/mutate.py`
(exportiert aus `fgc.project`). Warum diese Form:
- **Fachlogik vs. Mechanik getrennt:** der Mutator *entscheidet* (rechnet den Diff,
  baut den Sparse-Block, ruft `RobotDef.load` fürs Payload-Befund); der Seam
  *führt aus* (Lock, Lookup-Fehler, `bump_input`/`bump_section_input`, `write_project`).
  Lock (ADR-018), Fehlertext und Bump-Mechanik haben genau einen Wohnort.
- **Bump als sichtbare Deklaration (ADR-017):** `bump_inputs=("tool",)` bzw. das leere
  Tupel bei `set_stand_mode`/`set_context_check`/`set_module_limits`/`select_placement`
  machen die „BEWUSST kein Bump"-Fälle im Aufruf sichtbar statt als Kommentar. Die
  konditionalen Fälle (`set_placement_override`, `set_process_params`) berechnen ihr
  `bump_sections`/`bump_inputs` als Tupel und übergeben es — der Diff bleibt Fachlogik.
- **Upsert-Variante** (`upsert=True`) für `set_print_job`: kein „existiert nicht"-Lookup,
  der Mutator bekommt `None` (Anlegen) und der neue Job wird **ans Ende** gestellt —
  byte-gleich zum bisherigen `other_jobs + [new_job]` (die anderen Setter ersetzen
  in-place und behalten die Listenposition).
- **Befund-Rückkanal** (`JobMutation.befund` → `MutationOutcome.befund`): `payload_ok`/
  `payload_margin_kg` (Tool), `compatible` (Workstation), der gespeicherte Sparse-Block
  (`module_limits`/`override`/`slice_params`). Bewusst „Befund", nicht „Gate" (ADR-013):
  auch Payload-Überschreitung/Inkompatibilität wird gespeichert. Er wandert damit **in**
  den Lock (vorher rechneten Tool/Workstation den Befund knapp außerhalb) — die
  Rückgabewerte sind byte-gleich (reiner Datei-Read von RobotDef/compat, kein Projekt-
  zustand); nur die Fehler-*Reihenfolge* bleibt gewahrt, indem `ToolDef.load`/
  `WorkstationDef.load` **im** Mutator (nach `load_project`) laufen.
- **Reentranz gewahrt (ADR-018, RLock):** der Seam nimmt `project_lock` erneut; die
  lock-haltende Delegation `suggest_placement` → `evaluate_placements` bleibt außen vor
  (lauf-erzeugend) und funktioniert weiter. Direkt am Seam getestet.

**Scope-Grenze:** nur die 9 reinen Druckjob-Mutationen. Lauf-erzeugende Aktionen
(`propose_decomposition`, `simulate_section`, `export_section_drl`,
`evaluate_placements`/`suggest_placement`, `reassess_walls_for_robot`) bleiben **draußen**
— sie weichen stärker ab (`refresh_output` statt `bump_input`, Lauf-Erzeugung im Lock,
teils Rechnung außerhalb). Der Seam trägt darum **kein** `refresh`-Parameter (YAGNI:
keine der 9 frischt einen Output auf). Der Porositätsfeld-Setter aus PRD #110 kann als
zehnter Aufrufer ~10 Zeilen Fachlogik beisteuern statt ~70 Zeilen Choreografie.

**Result-Dedup:** die 14 Result-Dataclasses mit identischem 4-Feld-Kopf erben jetzt
`_JobArtifactResult` (Feldreihenfolge unverändert → api.py-Aufrufer via Keyword/Attribut
unberührt). `ProjectCreation` bleibt eigenständig (anderer Feldsatz/-reihenfolge).

**Bilanz:** neue Testdatei `core/tests/test_mutate_print_job.py` (Lookup-Fehler, Upsert
vs. In-place, Bump-Deklaration, Befund-Kanal, Serialisierung, Reentranz) — die 13
impliziten Wiederholungen in den Setter-Tests entfallen. Volle Core-Suite grün, ruff
clean; keine bestehende Test-/Schema-Änderung nötig (byte-gleiches öffentliches
Verhalten). README unberührt (kein nutzersichtbares Verhalten geändert). Kein ADR-
Konflikt — stärkt ADR-016/017/018; `actions.py` bleibt die eine Tür (ADR-014), wird
darin nur tiefer.

## 2026-07-09 — Fehlerkontrakt + Umschlag + HTTP-Adapter je Seamseite einmal (Issue #118)

**Frage:** Der Seam `actions ↔ api ↔ projects.ts` war beidseitig eine flache
Kopier-Familie (Architektur-Review 2026-07-08, Kandidat 5). Core: der
Fehlerkontrakt der Aktionsaufrufe (`FileNotFoundError → 404`, `ValueError`/`OSError
→ 422`) lag ~20-fach kopiert je Endpoint; 9 Endpoints machten zusätzlich einen
**Vorab-`load_project`** nur als Existenz-Check vor der Aktion (Doppel-Load); die
PUT-Setter wiederholten denselben 5-Feld-Projektumschlag als eigenes Response-Modell.
Viewer: jede Route trug ihren eigenen `fetch`/`jsonOrThrow`-Wrapper, `API_URL` lebte
doppelt (client.ts + projects.ts), das HTTP-Fehler-Mapping zweimal, und `api/` hatte
**kein** Test. Reiner Refactor gesucht — jede Route behält Statuscode, Body
(Feldnamen/-reihenfolge) und Fehlersemantik.

**Alternativen (Handler-Scoping, die offene Designfrage der Issue):**
(a) **app-weiter FastAPI-Exception-Handler** auf rohe `FileNotFoundError → 404` —
verworfen: tarnt auch *interne* Dateifehler (heute ehrliche 500er) als 404.
(b) **eigener Exception-Typ**, den die Aktionen werfen und ein Handler mappt —
verworfen als zu invasiv: die Aktionen werfen absichtlich die Standard-Ausnahmen
(`FileNotFoundError`/`ValueError`/`OSError`), CLI und Wizard verlassen sich darauf;
ein API-spezifischer Typ hätte die Aktionsschicht verunreinigt.
(c) **expliziter Kontextmanager um genau den Aktionsaufruf** — gewählt.

**Entscheidung/Begründung (Core):**
- **`action_errors()`** (Kontextmanager in `api.py`) trägt den 404/422-Kontrakt
  **einmal**. Gescopt ist er, weil nur der `with`-Block den Aktionsaufruf umschließt:
  Fehler aus dem übrigen Endpoint-Code (interne Dateifehler) bleiben ehrliche 500er.
  `FileNotFoundError` ist `OSError`-Unterklasse → **zuerst** gefangen; die Reihenfolge
  „Projekt fehlt (404) vor Eingabe ungültig (422)" bleibt erhalten. Angewandt auf alle
  Endpoints mit exakt diesem zweistufigen Block (Print-Job-Setter, lauf-erzeugende
  Projekt-Aktionen, Advisor, `put_tools`/`put_workstations`/`detect-base-holes`); die
  Partialformen (`post_tools`/`post_workstations` nur 422, `delete_*`/`get_project` nur
  404, `post_projects`/`post_slice` mit `KeyError`/`RuntimeError`) blieben **unberührt**
  — dort hätte der volle Kontrakt das Verhalten geändert.
- **9 Vorab-`load_project` gestrichen.** Die 404-Semantik trägt jetzt der Seam: die
  Aktion lädt das Projekt (via `mutate_print_job`/`reassess_walls_for_robot`) und wirft
  `FileNotFoundError` → 404. **Sonderfall `put_print_job`:** dessen Aktion fängt kein
  `FileNotFoundError`, der Vorab-Load trug hier allein die 404 — erst **nach** Einführung
  von `action_errors` gestrichen (sonst 500 statt 404), abgesichert mit
  `test_api_put_print_job_missing_project_404_via_seam`.
- **Projekt-Umschlag einmal:** `ProjectResponse` (5 Felder) nach vorn gezogen; die 6
  Setter-Modelle (`SetTool/Workstation/StandMode/ContextCheck/ModuleLimits/
  PlacementOverride Response`) **erben** davon und legen nur ihr **Befund**-Extra additiv
  daneben (`payload_ok`, `compatible`, … — Befund, kein Gate, ADR-013). Feldreihenfolge
  (Basis zuerst) byte-gleich → Response-Body unverändert. `_project_envelope` baut die
  fünf Felder an einer Stelle.
- **Bewusst NICHT umgesetzt:** ein *eigener* Exception-Handler-Typ; `ApiError.status`-
  Verzweigung in der UI (heute Zukunfts-, nicht Akutschmerz — kein Aufrufer verzweigt);
  Angleichung der Partialform-Endpoints (Verhaltensänderung).

**Entscheidung/Begründung (Viewer):**
- **`api/http.ts`** ist der eine Adapter: `request<T>(method, path, body?)` +
  `class ApiError { status, detail }`; `API_URL` lebt **einmal** (der Kommentar-Bezug zu
  `viewer_launch.py` bleibt). `client.ts` und `projects.ts` sind jetzt Einzeiler-
  Registrierungen. `ApiError.message` behält die Form „API-Fehler `<status>`: `<detail>`"
  (in der UI angezeigt, `err.message`); wer will, liest `err.status`/`err.detail`.
  `postSlice` behält seine „Netzwerkfehler …"-Meldung bei fetch-Ausfall (fängt
  Nicht-`ApiError` ab und übersetzt), HTTP-Fehler kommen als `ApiError` durch.

**Bilanz:** neue Testdatei `viewer/src/api/http.test.ts` (Erfolgsfall, Fehler-Mapping
404/422, `ApiError.status`/`.detail`/`.message`, Body/Header-Form, Stichprobe über
`projects.ts` und `client.ts` — die erste je gemockter `fetch`) → Viewer **762** grün
(751 + 11), `tsc` clean. Core **708** passed / 1 skipped (705 + 3: 404-Mapping,
422-Mapping, `put_print_job`-404-Regression), ruff clean; **keine** bestehende Test-
oder Schema-Änderung nötig (byte-gleiches öffentliches Verhalten). README unberührt
(kein nutzersichtbares Verhalten geändert). Kein ADR-Konflikt — setzt ADR-014 („dünner
Wrapper", „die eine Tür") erst konsequent um; nächster Feld-Setter (Porositätsfeld je
Druckjob, PRD #110) ist je Seamseite eine Registrierung statt ~120 Zeilen Vierfach-Edit.

## 2026-07-09 — Grill: Architektur-Review-Sextett #116–#123 — Realdruck-Pfad, Frame-Ort, main.ts-Timing

**Frage:** Grill-Session zu den sechs offenen Architektur-Review-Befunden
(#116 gemessenes Wand-Frame, #117 Wand-Frame-Modul/Datum, #120 Schnittplan-Store,
#121 Bühne, #122 Druckjob-Spiegel, #123 Frame-Algebra). Auslöser der Neubewertung:
der **erste Realdruck steht in Wochen bevor**.

**Neue Faktenlage (vom Nutzer, im Code bestätigt):**

1. Erster Realdruck = **Module** (ADR-022) an der Workstation. Roboterbasis und
   Druckfläche sind **auf derselben Platte verschraubt** → die Relativpose steht
   konstruktiv fest (x, y, yaw **und z**); eine Tischdrehung ändert das Druckbild
   nicht; das Modul steht **zentral** auf der Fläche — exakt das Modell von
   `_module_placement` (`decompose/propose.py:188-215`, `lateral_mm=0`) und
   `decompose/module_pose.py`. **Auf diesem Pfad wird nichts angetastet.**
2. Abschnitts-Druck (Roboter wird an der Wand umgesetzt) kommt real **nach** dem
   Modul-Druck.
3. Das „Antast-Gate" (`actions.py:528-546`) prüft faktisch nicht Geometrie,
   sondern ob **Verkabelung + Totzeit** bekannt sind: `emitter.py:58` verlangt
   `setup["io_channels"]` (ADR-011), und `_planned_setup` liefert genau das nicht
   (nur `robot`/`wall_to_base`/`tcp`/`deadtime=0`). Der Name hat die echte
   Vorbedingung verdeckt. ⇒ **Spike S1 ist der kritische Pfad** zum ersten
   Materialdruck, nicht das Wand-Frame.

**Entscheidungen:**

1. **#116 zerfällt.** (a) Modul-Pfad → neues **Issue #136**: der Export generiert
   das Setup bei Art „modul" selbst (Workstation-Frames + feste Platzierung +
   Werkzeug-TCP + Workstation-`io_channels`/`deadtime`); Gate-Semantik von
   „`setup.json` existiert" auf „**kein beteiligter Wert fehlt oder ist
   provisorisch**", Stub nennt den konkreten Fehlbestand; `setup_source`
   ehrlich (`generated`). (b) Abschnitts-Pfad → #116 rescoped auf
   **Wieder-Registrierung nach Umsetzen** (gegen das bereits Gedruckte), später
   mit Sensorik/PRD #111 zu grillen. Der frame3p-Konventions-Widerspruch ist auf
   dem Modul-Pfad **toter Code**: die Mathematik liefert bei Antastung auf einer
   liegenden Fläche (P2 Richtung Roboter) bereits X=Länge/Y=Front/Z=Höhe — der
   Bug sitzt in Docstring + CLI-Prompt („P2 … Wandhöhe"), nicht in der Formel.
2. **S1-Werte wohnen an der Workstation:** `io_channels` + `deadtime` werden
   additive Workstation-Stammdaten-Felder (Muster ADR-021; Altbestand ohne
   Felder = „unbestätigt"). Verkabelung und Schlauch-Totzeit sind Eigenschaften
   des Aufbaus, nicht des Werkzeugs (dasselbe Werkzeug kann an zwei Robotern
   anders verkabelt sein).
3. **#123: die eine Frame-Algebra zieht nach `fgc.domain.frames`**, nicht nach
   `fgc.geometry.frames` (Issue-Vorschlag korrigiert). Begründung: `geometry`
   ist **nachweislich fgc-importfrei** (Docstring-Vertrag, per Grep bestätigt) —
   ein Einzug dorthin bräche den Vertrag oder erzeugte den Zyklus
   domain→geometry→domain und ließe `domain/orientation._quat_mul` als
   geduldeten 4. Dialekt zurück. In `domain` daneben ist der Import paketintern
   ⇒ `_quat_mul` stirbt mit: **4 Dialekte → 1**. Die numpy-Grenze ist dann keine
   Konvention, sondern **erzwungen** (domain ist numpy-frei: Tupel rein/raus;
   frame3p/opw/evaluate/holes konvertieren an ihrem Rand). Viewer-Hälfte:
   `render/frames.ts` (`frameToMat`/`applyFrame`) mit **Core-erzeugten Golden**
   nach dem nozzle-quat-Muster (#61/#85).
4. **#117: Re-Open der Entscheidung vom 2026-07-07 (#99)** — die Wand-Pose wird
   **publiziertes Artefaktdatum**, der Viewer spielt sie ab (Muster
   `base_frame`/#66), `wall-frame.ts` verliert seine PCA. Die damalige
   Ablehnungsprämisse („reine Darstellung") ist entfallen: **ADR-023 §1
   persistiert das φ-Feld im Wand-Koordinatensystem** — der Frame wird
   Bezugsfläche persistierter Fachdaten, und die PCA über Wand-Vertices driftet
   bei IFC-Re-Export/Neu-Tessellierung ⇒ ein nicht eingefrorener Frame würde
   persistierte φ-Bezüge still verschieben. Randbedingung: `geometry.wallframe`
   liefert **nackte Achsen/Skalare, keinen `domain.Frame`** (geometry bleibt
   fgc-importfrei; den Frame baut der Aufrufer).
5. **#120/#121/#122 erst nach dem Realdruck**, Reihenfolge **#122 → #120 → #121**
   (Spiegel zuerst — er ist der Stamm). Der Viewer wird bis zum Druck
   eingefroren: die drei Refactorings fassen ungetestete Verdrahtung an, deren
   Regressionen man erst am Gerät bemerkt. Einzige Ausnahme: der bestätigte
   Kamera-Bug in `startModuleReplay` (falsche Rückkehr-Ansicht nach Modul-Replay,
   on-top-Fund aus #121) → isolierter Vorab-Fix als **Issue #137**, weil
   Modul-Replay genau der Pfad des ersten Drucks ist. #117/#123 ebenfalls nach
   dem Realdruck (dann `ready-for-agent` setzen).
6. **Rückweg gemessener Werte:** v1 manuell (Pendant ablesen → eintippen),
   **vollautomatisch später** über den ROS2-Druckserver (PRD #111) — kein
   eigener Socket in diesem Kontext.
7. **Kraft-Antasten ohne Zusatzsensorik** (für den späteren Abschnitts-Pfad) am
   hinterlegten Manual verifiziert (`docs/manuals/Doosan_DRL_Programming_Manual.md`,
   Beispiel Z. 7481–7524): `task_compliance_ctrl` → `set_desired_force` →
   `while check_force_condition(DR_AXIS_Z, max=…)` — **True solange KEIN
   Kontakt** (Betragsvergleich, richtungsblind); Default-Modus `DR_FC_MOD_ABS`;
   **Non-FTS-A-Falle** (`stx`/`fd`/`dir` werden `float[3]`); `check_robot_fts()`
   klärt die Sensorlage (offene Frage im drl-nutzungsplan). **Nie mit der
   Düsenspitze antasten** (Bruchrisiko, Lehm in der Düse, provisorischer TCP);
   `set_tool`/`set_tool_shape` zwingend, sonst geht Schwerkraft als
   Kontaktkraft durch.

**Verworfen:** `fgc.geometry.frames` (Vertragsbruch/Zyklus, `_quat_mul` bliebe);
Top-Level `fgc.frames` (Zyklus domain→frames→domain, `_quat_mul` bliebe ebenso);
Antasten der Flächenhöhe für Module (vom Nutzer korrigiert: z steht durch die
Verschraubung konstruktiv fest — es gibt nichts anzufahren); Gate als
Datei-Existenz beibehalten (ein veraltetes Setup — altes Werkzeug, alte
Verkabelung — bestünde unbemerkt); Gate ganz abschaffen (beim allerersten
Materialdruck ist eine übersehene Warnung teurer als ein Klick);
TCP-Socket-Rückkanal jetzt (überschneidet sich mit PRD #111).

**Nebenprodukte:** Issue #138 (Punktnummerierung der Bahn ein-/ausschaltbar,
Nutzerwunsch, needs-triage); #124 geschlossen (war laut Status/2c4ce68 komplett).

Bezug: ADR-006, ADR-007, ADR-011, ADR-013, ADR-021, ADR-022, ADR-023;
Design-Log 2026-07-04 (Antastverfahren), 2026-07-07 (#99), 2026-07-08 (#116-Grill);
`docs/manuals/drl-nutzungsplan.md` §3.5; Spike S1. Issues: #116, #117, #120,
#121, #122, #123, #136, #137, #138.

## 2026-07-09 — Workstation-Editor: Roboterbasis an eine Randkante schieben (Tisch ohne Bohrung)

**Frage:** Beim Flächen-Pick landet die Roboterbasis immer im flächengewichteten
Mittelpunkt der Standfläche (`mountBaseToSurface`, #78). Auf einem Tisch **ohne
Bohrbild** will man den Roboter aber oft an den Rand stellen (Reichweite zur
Wand, Kabelführung). Nutzerwunsch: eine **Kante wählen + Abstand eingeben**,
der Roboter rutscht dorthin.

**Alternativen:**

1. **Frei ziehen (Drag-Gizmo)** — verworfen: genau das Muster, das beim
   Endeffektor-Konfigurator kaputte Frames erzeugte (#28/#52); außerdem nicht
   reproduzierbar dokumentierbar („wo genau steht er jetzt?").
2. **Numerische x/y-Offsets in Mesh-Koordinaten** — verworfen: der Nutzer
   denkt physisch („20 cm von der Tischkante"), nicht in Mesh-Achsen; bei
   gedrehten/geneigten Flächen unbrauchbar.
3. **Kanten-Pick + Abstand (gewählt):** Randkanten der ebenen Standfläche =
   Dreieckskanten, die nur **einem** Region-Dreieck gehören; kollineare
   Teilstücke werden zu maximalen Segmenten verschmolzen (STL zerhackt eine
   Tischkante sonst in Splitter). Klick wählt die dem Klickpunkt nächste
   Randkante (Hover zeigt sie als Linie), die Basis-Mitte rutscht **senkrecht
   zur Kante** auf den Abstand, **längs** bleibt sie auf Höhe des
   Flächen-Zentroids (symmetrischer Tisch ⇒ mittig an der Kante).

**Entscheidung:** Variante 3 als neues reines Modul
`viewer/src/ui/edge-slide.ts` (`regionBoundaryEdges`/`mergeCollinearEdges`/
`nearestBoundaryEdge`/`slideToEdge`, three.js-frei, 11 vitest) + dünner
DOM-Anteil in `workstation-scene.ts` (Pick-Modus „edge", Abstandsfeld wirkt
live, „Zurück zur Flächenmitte"). Hausmuster wie `face-align.ts`.

**Festlegungen:** Der Abstand misst zur **Basis-Mitte** (`robot_base_frame`-
Ursprung), nicht zum Fußrand — der M1013-Fußabdruck ist bis zur Bestätigung
der `base_mount`-Maße provisorisch (#78), eine Fußrand-Semantik wäre
Scheingenauigkeit; bei Bedarf später als Umschalter nachrüstbar. Kein
Schema-/API-Change: gespeichert wird weiterhin nur der `robot_base_frame` —
Kante + Abstand sind Editor-Eingaben, kein Artefaktdatum. Deshalb braucht
die Kantenwahl nach dem Wieder-Öffnen einer gespeicherten Workstation einen
neuen Flächen-Pick (dem gespeicherten Frame fehlen die Randkanten). Ein
Bohrbild-Snap löscht die Kantenwahl (verschraubt wird nicht geschoben).

Verifikation: Viewer 773 vitest grün (+11), tsc + `vite build` clean.
Bezug: Issue #78, ADR-021, ADR-006; Design-Log 2026-07-07 (#78).

## 2026-07-09 — Modul-Export: Setup aus Stammdaten generieren, Gate „nichts Provisorisches" (Issue #136)

**Frage:** Umsetzung von #136 aus dem Grill gleichen Datums (Sextett #116–#123):
Bei Zerlegungsart **Modul** (erster Realdruck, ADR-022) soll der Export das Setup
**selbst generieren** statt ein gemessenes `setup.json` zu verlangen; das
„Antast-Gate" (`setup.json` existiert → `measured`) wird auf „**kein beteiligter
Wert fehlt oder ist provisorisch**" umgestellt und `setup_source` ehrlich benannt.

**Entscheidungen bei der Umsetzung:**

1. **S1-Felder additiv an der Workstation** (`io_channels` + `deadtime`), Muster
   ADR-021: als `$defs` in `setup.schema.json` herausgezogen und von
   `workstation.schema.json` per `$ref` wiederverwendet (die eine Quelle des
   Kanal-/Totzeit-Schemas, statt Copy-Paste). `WorkstationDef`/`build_workstation_artifact`/
   API (`WorkstationRequest`/`WorkstationInfoModel`, create/update) tragen sie
   additiv; Altbestand ohne Felder lädt als `None` = „unbestätigt". `additionalProperties:false`
   bleibt. Begründung (Grill): Verkabelung + Schlauch-Totzeit sind Eigenschaften des
   **Aufbaus**, nicht des Werkzeugs.

2. **Export-Verzweigung nach Zerlegungsart** in `export_section_drl` (neuer Parameter
   `workstations_dir`): bei `kind=="modul"` baut `_generate_module_setup` das Setup aus
   Workstation-Frames (feste Platzierung über `plan_for_job` → `_module_placement`) +
   Werkzeug-TCP + Workstation-`io_channels`/`deadtime`. Die Emit-Naht wurde als
   `_emit_drl_from_setup(run_dir, setup, …)` **geteilt** (emit_drl_run ruft sie jetzt
   auch) — ein Setup-**Dict** rein, kein Zwang zur Datei. Kette-Orakel hält by
   construction: die Modul-Platzierung kommt aus **derselben** Tür (`plan_for_job`,
   z-Offset 0) wie die Simulation, `wall_to_base` ist byte-gleich.

3. **TCP-„Provisorisch"**: neues optionales, additives `tcp_provisional`-Bool am
   **Endeffektor** (tool.schema.json/ToolDef/build_tool_artifact), Geist von
   ADR-013/`deadtime.provisional`. Nur geschrieben, wenn `True` (Altbestand byte-gleich,
   fehlend/False = bestätigt — der Konfigurator-Upload trägt einen realen TCP). Erwogen
   und verworfen: ein `provisional`-Flag am Frame selbst (Frame-Schema hat
   `additionalProperties:false`, wäre invasiver) oder ein Vergleich gegen
   `PROVISIONAL_TCP` (fragil, koppelt an konkrete Zahlen). Ein **fehlender** Endeffektor
   ist ein eigener benannter Fehlbestand (ohne TCP kein Setup).

4. **`setup_source` ehrlich:** `generated` (vollständig) bzw. `generated_incomplete`
   (Stub mit benanntem Fehlbestand) neben den bestehenden `measured`/`none` des
   Abschnitts-Pfads. Viewer-Typ (`api/projects.ts`) + API-Docstring nachgezogen; die
   `export.ts`-Anzeige nutzt ohnehin nur `complete`/`note`. Der Stub nennt den
   Fehlbestand konkret („es fehlt: …") — Befund, kein Gate (ADR-013-Geist).

5. **io_channels „bestätigt" = vorhanden** (kein eigenes Provisorik-Flag): pragmatisch,
   weil die Verkabelung entweder bekannt ist oder nicht; die Provisorik-Semantik trägt
   die Totzeit über ihr `provisional`-Feld. Dokumentiert, falls später ein feineres
   Modell nötig wird.

**ADR-006-Nachtrag** ergänzt: das Setup bleibt **die eine Transformationsstelle** — es
wird nur je Zerlegungsart anders **befüllt** (gemessen vs. generiert).

Verifikation: pytest (core) — neues `test_module_export.py` (generierter Voll-Export +
Ketten-Orakel; Gate je Fehlbestand: io_channels/Totzeit/Frames/TCP/Endeffektor;
Altbestand-Load; Round-Trips) sowie die betroffenen Suiten (workstation/export/setup/
tool/drl_emitter) grün; `ruff check` clean.
Bezug: ADR-006 (Nachtrag), ADR-011, ADR-012, ADR-013, ADR-021, ADR-022; Spike S1;
Design-Log 2026-07-09 (Grill #116–#123). Issue #136.

## 2026-07-09 — Wayfinder-Karte #139: Kollisionsfreier, flüssiger Abschnitts- & Moduldruck (Grill-Session)

**Frage:** Realdruck-Test an der Denkmal-Wand deckte drei Wunden auf: (a) der Arm
taucht beim Druck der hinteren Stränge oben bis −193 mm in frisch gedrucktes
Material des eigenen Teils (Abschnitte **und** Module), (b) die Kollisionsprüfung
eines einzelnen fokussierten Abschnitts läuft real > 3 min (Spike S0 maß 30–44 s an
einer *grünen* 25k-Bahn; die reale Bahn hat 8688 rot / 2405 gelb — die AABB-
Breitphase greift kaum, fast überall urteilt VHACD), (c) das Modul-Slicing scheiterte
an fehlendem `work_surface_frame` mit generischer Meldung, obwohl `druckort-spec.ts`
den präzisen Hinweis längst baut.

**Alternativen:** (1) Teile pauschal kleiner schneiden (Magic Number) — verworfen:
behandelt das Symptom, nicht die Grenze. (2) Tiefenteilung (vertikale Fuge, hinten
zuerst) im automatischen Zerleger — verworfen für v1: durchgehende Fuge im
Querschnitt, Verbund frisch-an-fest, Standsicherheit der schlanken Scheibe,
Porositätsgradient unterbrochen. (3) Kollisionsgetriebene Zerlegung — **gewählt**.

**Entscheidungen (Tobias):**
1. **Zerlegung kollisionsgetrieben:** die Teilgröße endet dort, wo der Grob-Check
   (`fgc.collision.coarse`) von der besten Platzierung aus keine Arm-Eindringung
   mehr meldet; Hebel Bandhöhe/Breite/Podest (Reihenfolge = Ticket #141, vorab
   #140 Validierung Grob-Check gegen Realbefund).
2. **Tiefenteilung nur manuell:** der Automatismus schlägt sie nie vor, aber der
   Nutzer darf bewusst in der Tiefe schneiden — als Option im Slicing (#142).
3. **Performance ist ein Algorithmus-Ast, kein UI-Scope-Problem:** Zielmarke
   Fokus-Teil ≤ ~10 s (nach Profiling #143 bestätigen oder ehrlich revidieren,
   Strategie #144); Prüf-UX (Fokus-Default, Hintergrund + Fortschritt + Abbruch)
   unabhängig davon (#145). Zusatzbefund: der Nutzer prüfte unwissentlich immer global.
4. **Modul-Druckweg als dritter Ast:** geführte Workstation-Einrichtung (#146,
   realer Stolperweg doosantisch: Frame nachgetragen → Viewer-Cache + veralteter
   Zerlegungslauf blockieren weiter), Replay-Parität am Druckort (#147 — `updateModuleReplay`
   bewegt nur den Arm: kein Endeffektor, keine Bahn, kein Druckstand), Player-Leiste (#148).
5. **Karte plant, Issues setzen um:** die Karte endet, wenn nichts mehr zu
   entscheiden ist; Umsetzung über den normalen Issue-Fluss.

**Sofort ausgegliedert (keine offene Entscheidung):** #149 `ready-for-agent` —
`moduleSceneSpecFor` (main.ts) verflacht das `DruckortSceneResult` auf `spec | null`
und verschluckt den präzisen `hint`.

Bezug: ADR-013, ADR-022, ADR-024; Wayfinder-Karte #139 (Tickets #140–#148, Bug #149).

## 2026-07-09 — Kamera-Rückweg nach Modul-Replay (Issue #137)

*(Eintrag nachgetragen: die Umsetzung landete in `17cfefd`, während
`docs/design-log.md` uncommittete Änderungen einer parallelen Session trug —
der Eintrag durfte deshalb nicht im selben Commit mitfahren.)*

**Frage:** `startModuleReplay` fuhr nach Ende eines Modul-Replays an die falsche
„Wand-Ansicht" zurück. Warum, und wie isoliert fixen, ohne dem Bühnen-Refactor
#121 vorzugreifen?

**Befund:** Der Rückkehr-Stash `einbauortCamera` wurde NACH `teardownModuleReplay`
gesetzt. Dieses ruft `exitDruckortScene(true)`, das (a) einen async-Tween zur
Wand-Ansicht startet und (b) `einbauortCamera` sofort nullt — die Kamera steht in
dem Moment aber noch am Druckort. Der unmittelbar folgende Stash übernahm damit
die Druckort-Position als vermeintliche Wand-Ansicht. Zweiter Trigger: Start aus
der per Umschalter betretenen Druckort-Ansicht (dort hält `einbauortCamera` bereits
die echte Wand-Ansicht, wurde aber überschrieben).

**Alternativen:**
1. Stash unbedingt vor den Tween ziehen und immer die aktuelle Kamera snapshotten.
   Verworfen: greift nur den frisch-aus-der-Wand-Fall, nicht den „schon am
   Druckort"-Fall (dort ist die aktuelle Kamera = Druckort, also falsch).
2. Nur snapshotten, wenn `einbauortCamera == null`, sonst den bestehenden Stash
   weiterverwenden. **Gewählt** — deckt beide Trigger ab: ein vorhandener Stash
   trägt immer die Wand-Ansicht (er entsteht nur beim Betreten des Druckorts).

**Entscheidung:** Rückkehr-Kamera vor dem Abräumen per reiner, DOM-freier Funktion
`resolveReplayReturnCamera(existing, snapshotCurrent) = existing ?? snapshotCurrent()`
bestimmen (Heimat `ui/druckort-state.ts`, Hausmuster der View-State-Module).
Regressionsschutz per vitest: der Fall „Stash vorhanden" darf `snapshotCurrent`
gar nicht aufrufen — genau der Bugkern.

**Begründung:** ~20-Zeilen-Fix ohne Eingriff in die Bühnen-/Kamera-Stack-Struktur;
diese Aufräumung bleibt ausdrücklich #121 vorbehalten (Kamera-Stack). Bezug: #121,
Grill 2026-07-09 (#116–#123).

## 2026-07-09 — Spike S5: Profiling der Kollisionskontrolle an Abschnitt 1 (Issue #143)

**Frage:** Wo geht die Zeit von `find_collisions` an der realen Abschnitt-1-Bahn
(Denkmal, Modul) hin, und welcher der drei Hypothesen-Hebel (Distanz nur bis
Schwelle / Travel-Ausdünnung / Hindernis-Caching) bringt wie viel? Zielmarke der
Karte #139: „Fokus-Teil ≤ ~10 s". Protokoll: `docs/spikes/S5_profiling_kollision_abschnitt1.md`,
Sonden `docs/spikes/s5_scripts/`.

**Alternativen (Messmethode):**
1. Bahn aus der 6-MB-`trajectory.json` zurückrechnen. Verworfen — fehleranfällig,
   und die Footprint-Geometrie (Druckstand) fehlt dort.
2. **Gewählt:** Reproduktion über den Produktivpfad `_slice_and_simulate_section`
   + Gate `verify_reproduction`, das byte-genau die Ticket-Zahlen (8688/2405/8442,
   min −290,444 mm) trifft — so wird derselbe Produktivcode mit denselben Eingaben
   profiliert, keine Nachbildung.

**Befund (gemessen, reproduzierbar):**
- `find_collisions` (self=False, Produktiv-Konfiguration) = **~11,5 s** über 19 535
  Samples (~0,59 ms/Sample), **nicht** > 3 min. Der ganze Fokus-Abschnitt rechnet
  end-to-end ~19 s (Slice+Sim ~5–7 s, FK ~0,75 s, find_collisions ~11,5 s,
  Validieren+Schreiben ~1 s).
- **Dominanter Posten ist nicht die fcl-Distanz, sondern das Positionieren der
  VHACD-Urteilsgeometrie** (`set_transform`, **~53 %**, 1 566 305 Aufrufe — ~36
  Konvexstücke je nahem Glied je Sample). fcl `min_distance` ist nur ~18 % (1,7 s).
- Der AABB-Breitphasenfilter **verwirft 67,8 %** aller Glied↔Hindernis-Paare — der
  Ticket-Verdacht „greift kaum" ist widerlegt.
- **Hebel-Ranking:** (1) `set_transform` verschlanken 2–4 s (außerhalb der 3
  Hypothesen; berührt VHACD/Formtreue, ADR-024); (2) **H2 Travel-Ausdünnung** ~2,8 s
  / 36 % (sicher, Travel ist ohnehin „nicht lückenlos geprüft"); (3) **H1 Distanz
  nur bis Schwelle** ≤1,9 s (gemessen: `in_collision` 4× billiger als `min_distance`,
  ersetzt aber das gelbe Band nicht, `set_transform` bleibt); (4) **H3 Hindernis-
  Caching** ~0 (Rebuild 0,08 s / 0,8 %, Cache greift schon — Hypothese widerlegt).
- **Selbstkollision** (`self_collision=True`, produktiv AUS) kostet allein ~184 s
  (~15×) — der **einzige** gemessene Pfad, der die „> 3 min" erreicht.

**Entscheidung/Konsequenz (für #144, reine Messvorarbeit, kein Code geändert):**
`find_collisions ≤ 10 s` ist mit **H2 allein** erreichbar (~11,5 → ~8,7 s), mit
H1 zusätzlich ~7–8 s; der stärkste Hebel `set_transform` ist eine Strategiefrage
mit Formtreue-Abwägung. Die **> 3-min-Zielmarke des Fokus-Teils ist zu
verifizieren**, bevor optimiert wird: in dieser Umgebung ist der Abschnitt ~19 s;
> 3 min nur mit Selbstkollision. #143 misst, #144 entscheidet die Strategie.

**Begründung:** Auftrag war reine AFK-Messung (Grenze: nur `docs/spikes/**`,
`design-log`, `status`). Zahlen nie geschätzt außer klar benannt; `set_transform`
als eigentlicher Kostentreiber war nicht antizipiert und verschiebt die Strategie
weg von der (kleinen) fcl-Distanz-Hypothese. Bezug: Karte #139, ADR-024, Spike S0.

## 2026-07-09 — Modul-Replay-Parität: was gehört auf die Druckort-Bühne? (#147, Karte #139)

**Frage:** Die Druckort-Bühne (`updateModuleReplay`, `main.ts:1175-1203`) bewegt nur den
Kapsel-Arm. Welche Parität zum Wand-Replay ist gewollt — Endeffektor, TCP-Marker,
Bahn-Aufdeckung, wachsender Druckstand, Live-Abstandszahl, Timeline-Marker?

**Befund (Code, keine Entscheidung):**
- `ToolpathView`/`TcpMarkerView`/`DruckstandView` backen **keinen Frame ein** — sie bauen
  in abschnittslokalen data-mm und geben eine Group zurück. Sie gehören unter
  `moduleGroup` (`main.ts:848`, trägt `module_pose.workstation`), nicht unter
  `druckortGroup`. `ArmView` beweist das Muster (`spec.robotAnchor` als übergebene Mat4).
- Endeffektor ist **ein Aufruf**: `attachToolMeshToArm()` (`main.ts:1300`) existiert, wird
  für den Wand-Arm gerufen (`main.ts:1637`), nie für `druckortArm`.
- `meta.collision` wird je Modul geladen (`main.ts:1105`) und **weggeworfen**.
- Der Befund am Druckort ist **zuständig, nicht geborgt**: genau ein Lauf je Abschnitt,
  gerechnet gegen dessen eigene `base_frame`. `PlacementOption` ist eine *relative* Pose
  Roboterbasis↔Objekt (ADR-022); `module_pose.py:85-99` drückt dieselbe Platzierung nur in
  Workstation-Koordinaten aus. `context_enabled` ist für Module gegenstandslos
  (`finding.py:279-291`). ⇒ Die Statuszeile „keine Kollisionsprüfung" (`main.ts:1113`)
  ist seit #128 **falsch**.
- `fgc.collision.check` prüft den Arm gegen ein **schichtweise wachsendes Prisma**
  (Footprint + Freizone, ohne Boden/frühere Teile — `check.py:81-90`, ADR-024), nicht
  gegen das fertige Modul.

**Alternativen (Modul-Box):** (1) statische Vollbox stehen lassen; (2) ersatzlos entfernen;
(3) Kanten behalten, Füllung durch mitwachsenden Druckstand ersetzen.

**Entscheidung: (3) — Soll als Linie, Ist als Volumen.**
Die Kanten (`EdgesGeometry`, `main.ts:838-841`) bleiben als Soll-Umriss; die
halbtransparente Füllung (`main.ts:829-837`) weicht `DruckstandView`.

**Begründung:** Die statische Box macht zwei Jobs auf einmal — *Soll* (Modul-Lage,
Orientierung, Größe auf der Arbeitsfläche) und *Ist* (hier steht Material). Als Ist ist sie
falsch: der Arm fährt in Sekunde 10 sichtbar durch volles Material, während die
Abstandszahl daneben Freiraum meldet — weil real erst zwei Schichten stehen. Bild und Zahl
widersprechen sich, und die Zahl hat recht. Da der Druckstand **das Hindernismodell der
Prüfung selbst** ist, macht sein Mitwachsen die Bühne erst zu dem, was sie behauptet zu
sein. Ersatzloses Entfernen (2) verlöre bei t=0 die Modul-Lage — die Information, wegen
der die Druckort-Bühne existiert.

**Alternativen (Timeline-Marker):** (a) alle Module auf der Sequenz-Gesamtleiste;
(b) nur das aktive Modul; (c) gar keine Marker am Druckort.

**Entscheidung: (b).**

**Begründung:** Die Marker aus #128 sind zum *Anklicken* gebaut („spring zu dieser
Kollision"). Auf einer Sequenzleiste über n Module mit `UMBAU_SECONDS`-Pausen
(`main.ts:1152-1166`) wechselt ein Klick nicht nur die Zeit, sondern die Bühne:
`buildDruckortScene` (`main.ts:1182`) baut neu auf und setzt den gewachsenen Druckstand
zurück. Das ist ein anderes Interaktionsversprechen als an der Wand. Die Gesamtübersicht,
die (a) verspricht, liefert billiger und lesbarer das Kollisions-Badge je Modul in der
Teile-Palette (existiert seit #128) — die ohnehin überladene Leiste (#148) muss sie nicht
auch noch tragen. (c) wäre zahnlos: eine Abstandszahl ohne Sprungziel.

**Reihenfolge:** #151 (Endeffektor + TCP) → #152 (Strang + Druckstand) → #153
(Kollisionsanzeige). Sie ist zugleich Abhängigkeitsreihenfolge: #153 ohne #152 widerspricht
sich selbst — die Zahl meldet frei, das Bild zeigt die Vollbox.

**Unberührt:** Die provisorische Endeffektor-Hülle (offener PRD-#124-Punkt 3, Out-of-scope
der Karte #139) bleibt provisorisch. Das Tool wird am Druckort *angezeigt*, es beurteilt
nichts neu; der Befund kommt verbatim aus dem Artefakt (ADR-007).

## 2026-07-09 — Spike S6: Grob-Check gegen den Realbefund validiert (Issue #140, Karte #139)

**Frage:** Taugt der fcl-freie Grob-Check `fgc.collision.coarse.path_collides` als
Kollisions-Constraint der Zerlegung (#141) — meldet er das reale Eintauchen zuverlässig,
das der volle VHACD-Befund `find_collisions` zeigt, insbesondere **ohne Falsch-Negative**?
AFK-Recherche an der realen Denkmal-Zerlegung (Modul, 16 Teile). Protokoll
`docs/spikes/S6_grobcheck_vs_realbefund.md`, Sonden `docs/spikes/s6_scripts/`.

**Alternativen (Messmethode):**
1. Grob-Check-Argumente aus handgeschriebenen Konstanten. Verworfen — validierte eine
   Nachbildung, nicht die reale Nutzung.
2. **Gewählt:** beide Urteile je Teil aus demselben Produktivpfad — `plan_for_job` (16
   Module + Platzierungen), `_slice_and_simulate_section`→`build_section_finding`
   (voller Befund, kein Lauf geschrieben), `coarse.path_collides` mit der Teil-Wandfläche
   (`Section.as_surface`, `z_offset=0` Modul-Konvention). Reproduktions-Anker: `abschnitt-1`
   trifft den gespeicherten `meta.collision` byte-genau.

**Befund (gemessen, reproduzierbar):**
- **Konfusionsmatrix 16 Module: TP=16, FP=0, FN=0, TN=0** — aber **entartet**: alle 16
  Module kollidieren real (min. Abstand −206…−436 mm), es gibt keine „grüne" Zeile. Der
  Grob-Check liefert bei Modul für **alle** Teile bit-identisch dasselbe Urteil (gleiche
  abstrakte Box + feste Workstation-Platzierung standoff 485 mm) — er fängt alle **tiefen**
  Kollisionen, was aber kein Treue-Beweis ist.
- **Verursacher:** von 189 594 roten Samples verursacht **link2 46,1 %, Handgelenk link4
  39,4 %, link3 14,5 %**. `(1,2,3)` deckt **60,6 %** ab, **39,4 % gehen strukturell
  verloren** (Handgelenk, bewusst außen — ADR-024 Kontext 2). `causer_against` zu **100 %
  „modul"** (Arm ↔ wachsender Druckstand — der Grob-Check adressiert den richtigen
  Gegenspieler).
- **Kosten:** Median **1,98 ms**, p95 3,64 ms (9 Posen) — weit unter 100 ms. Feines Raster
  (81 Posen) ~16–24 ms, immer noch < 100 ms.
- **Sensitivität** (pen ∈ {5,20,50} mm × Raster grob/default/fein): auf der realen
  entarteten Fläche **immer „kollidiert"** — die Richtig-Positiven hängen weder an Schwelle
  noch Raster.
- **Falsch-Negativ-Sonde** (nur standoff eines realen Moduls variiert, um die fehlende
  „grüne" Zeile zu erzwingen): bei standoff **700/900/1300 mm** sagt der Grob-Check „frei",
  während der volle Befund **3357/5213/5712 rote** Samples zeigt — **drei Falsch-Negative**
  aus zwei Quellen: (a) **Glieder-Zuschnitt** (900 mm Handgelenk-dominant, 1300 mm
  Endeffektor+link5), (b) **Rastergröbe** (700 mm: link2 *ist* im Grob-Check, wird vom
  9-Posen-Raster über die abstrakte Rechteck-Fläche dennoch verfehlt).

**Entscheidung/Konsequenz (für #141, reine Validierung, kein Code geändert):**
`path_collides` ist **so wie er ist NICHT** hinreichend treu als Zerlegungs-Constraint —
sein Fehlerbias zeigt Richtung „frei" (die falsche Richtung für einen Constraint). Für
seinen entworfenen Zweck (Aussortieren im Optimalvorschlag, Befund kein Gate) genügt er.
Empfehlung: der treue Constraint ist eine **verdünnte Instanz von `find_collisions`
selbst** (S5: ~8,7 s mit Travel-Ausdünnung, kein struktureller Blindfleck), nicht der
geometrische Grob-Ersatz. Bleibt #141 doch beim Grob-Check, ist die minimale Erweiterung:
**Handgelenk + Endeffektor mit Freizonen-Schutz aufnehmen und das Raster verdichten**
(beides < 100 ms, adressiert je eine Fehlerquelle) — die Rechteck-statt-Prisma-Lücke
bleibt. #140 liefert die Zahlen, #141 entscheidet.

**„−193 mm" (Ticket-Wert):** nicht einem gespeicherten Lauf/Teil zuzuordnen und **nicht
geglättet**. Gespeichert: `abschnitt-1` −290,444 mm, `abschnitt-20` (frühere Zerlegung)
−145,095 mm; die 16 aktuellen Module −206…−436 mm — kein Teil trifft −193 mm. Es ist
offenbar die Grill-Session-Realdruck-Beobachtung (status.md), größenordnungsmäßig im
Fächer der standoff-Sonde (700 mm → −177,5 mm), aber ohne aktuelles Gegenstück. Bleibt
offen.

**Begründung:** Auftrag war reine AFK-Validierung (Grenze: nur `docs/spikes/**`,
`design-log`, `status`; kein Lauf geschrieben, `project.json` unangetastet). Zahlen nie
geschätzt; der Kernbefund (39,4 % Handgelenk-Verursacher + Rastergröbe ⇒ leichte
Falsch-Negative) war aus dem Code (`ARM_LINK_INDICES`, 9-Posen-Raster) plausibel, aber erst
die Falsch-Negativ-Sonde belegt ihn am realen Teil. Bezug: Karte #139, ADR-024, Spike S0/S5.

## 2026-07-09 — Player-Leiste: Armaturenbrett mit zwei Modi, Geschwindigkeit, Befund als Lauf-Eigenschaft (#148, Karte #139)

**Frage:** Die Leiste unter dem 3D-Feld (`#sim-dock`) überlagert sich selbst. Was muss
dauerhaft sichtbar sein, was darf in einen Detail-Bereich? Zwei Zeilen, Popover, Kürzung?

**Befund (Code):**
- `#sim-dock` (`viewer/index.html:1068-1097`) trägt **fünf Zwecke**: Startknöpfe,
  Warnhinweise, Player, Befund, Statussatz. `#sim-focus-btn`/`#sim-sequence-btn` werden
  **nie versteckt**, auch wenn `#sim-player` sichtbar ist.
- Der Überlauf ist strukturell: `.sim-dock` (`style.css:1484`) ist eine Flex-Zeile mit
  `nowrap`, `right: 352px`; fast alle Kinder `flex:none; white-space:nowrap`.
- `TrajectoryPlayer` läuft in **Echtzeit** (`trajectory/player.ts:66-69`, kein Faktor).
  Ein realer Abschnitt der Denkmal-Wand: **5212 s ≈ 87 min**
  (`runs/20260706-090729_slice_Denkmal/trajectory.json`). „Play" startet heute einen
  87-Minuten-Film; faktisch ist der Slider die Bedienung.
- `setStatus` vermischt **Lauf-Eigenschaften** (`collision-state.ts:241`) mit
  **vergänglichen Aktionsmeldungen** (`main.ts:1086,1109`).
- `#traj-meta` (`<dl>`) und `#traj-warnings` (`<ul>`) existieren und leben
  (`ui/panel.ts:86-96`) — strukturierte Heimat für Lauf-Eigenschaften, heute halb leer.
- Der DOM-Vertrag (`shell-structure.test.ts:247-302`) prüft nur Existenz, Reihenfolge,
  `hidden` — ein Umbau, der IDs und Reihenfolge behält, bleibt grün.

**Leitregel (entschieden):** *In der Leiste steht nur, was sich mit der Zeit ändert.*
Fachliches, kein ästhetisches Kriterium. Es sortiert von allein: Zeit, Play, Phase,
Abstandszahl, Marker gehören hinein; Befundtext (Eigenschaft des Laufs), Statussatz
(Meldung über die letzte Aktion) und Übersicht-Knopf (Navigation) nicht.

**Alternativen (Zweck):** (1) Transportmittel — nur Zeit/Play, alles andere zieht aus;
(2) Armaturenbrett — Zeit, Phase, Befund-Zustand gemeinsam, mit Hierarchie.
**Entscheidung: (2).** Phase und Befund-Zustand ändern sich mit der Zeit.

**Alternativen (Layout):** (a) zwei Zeilen; (b) Popover am Badge; (c) Kürzung mit „mehr…";
(d) zwei **Modi** in einer Zeile.
**Entscheidung: (d), eine Zeile.**
**Begründung:** Startknöpfe und Player sind nie gleichzeitig sinnvoll — `← Übersicht`
(`#sim-back-btn`) führt bereits in den Start-Zustand zurück. Die Leiste ist nicht
überladen, weil zu viel hineingehört, sondern weil sie **zwei Zustände gleichzeitig
zeigt**. Der Replay-Modus verliert die zwei längsten Knöpfe und wird netto leerer als
heute — ohne Umbruch, Popover oder Kürzung. Zwei Zeilen kosten dauerhaft vertikale
Bildfläche, also genau das, was beim Betrachten der Wand knapp ist.

**Alternativen (Geschwindigkeit):** (i) Vielfaches der Echtzeit; (ii) Wunschdauer
(„ganzer Lauf in ~60 s").
**Entscheidung: (i), Leiter ~0,25×…200×, Voreinstellung 1×, klebt an der Sitzung.**
**Begründung:** Der Faktor bleibt an der Echtzeit verankert, sonst geht die physikalische
Aussage „so schnell fährt die Maschine wirklich" verloren — die man zur Beurteilung enger
Stellen (−193 mm) braucht. Empfohlen war eine Voreinstellung, die den Lauf auf ~1 min
einpasst; der Nutzer entschied auf **1×** als vorhersagbaren Anker. Damit 1× kein
Reibungspunkt wird, klebt der gewählte Faktor an der Sitzung statt am Lauf — er ist eine
Eigenschaft des Schauens, wie die ⚙-Schalter. **`UMBAU_SECONDS = 3` (`main.ts:1232`)
skaliert nicht mit**: Erzählzeit, keine Prozesszeit; sonst wird bei hohem Faktor genau der
Umbau-Schritt unsichtbar, den #27 sichtbar machen wollte.

**Alternativen (Statussatz):** (a) aufteilen nach Textsorte — Befund nach `#traj-meta` /
`#traj-warnings`, Badge als Anker; (b) Popover am Badge; (c) nur kürzen.
**Entscheidung: (a).**
**Begründung:** Ein Ding, ein Zweck. Der Befund ist kein Status, sondern ein Ergebnis:
„3 rot, 5 gelb, min. 12 mm" gehört in eine Liste, die man überfliegt, nicht in einen Satz,
den man liest; die Vorbehalte („vorläufige Grenzwerte", „Travel nicht lückenlos geprüft")
sind Warnungen, und `#traj-warnings` steht genau dafür leer daneben. (b) ließe den Befund
Fließtext, (c) löst nichts. Preis: (a) fasst `panel.ts` an und zerlegt
`collision-state.ts:241` — dafür ist der Befund an Wand und Druckort derselbe, was #153
ohnehin braucht.

**Umsetzung:** #154 (Zwei-Modi) → #155 (Geschwindigkeit) + #156 (Befund als
Lauf-Eigenschaft).

**Nebenfund, bewusst vertagt:** Es gibt **zwei Player** — `#trajectory-panel`
(`traj-play-btn`/`traj-slider`/`seq-phase`, `index.html:154-170`) und die Leiste. #156
läuft mitten hinein. Als Karten-Ticket #157 aufgenommen statt hier miterledigt.

## 2026-07-09 — Zwei Player im Viewer: keiner weicht, es sind zwei Schauplätze (#157, Karte #139)

**Frage:** `#trajectory-panel` (`traj-play-btn`/`traj-slider`/`traj-time`/`seq-phase`) und die
Leiste `#sim-dock` (`sim-play-btn`/`sim-slider`/`sim-time`/`sim-phase`) zeigen dieselbe
Trajektorienzeit. Welcher Player bleibt?

**Befund, der die Frage auflöst:** Sie sind **nie gleichzeitig sichtbar**. `aside#panel`
(`index.html:114-198`) steckt vollständig in `<section class="tab-panel" data-panel="projekt">`
(113–199); `#sim-dock` schaltet über `main.ts:3740` (`simDockEl.hidden = id !== "druckplan"`).
Dass derselbe `TrajectoryPlayer`-Callback beide speist, ist kein Doppel-Rendering, sondern der
Spiegel, den `main.ts` selbst so kommentiert: „no-op, solange er ausgeblendet ist".

**Alternativen:** (a) Leiste bleibt, Panel-Transport fällt; (b) Panel bleibt, Leiste fällt;
(c) beide bleiben — zwei Schauplätze mit verschiedenem Zweck.
**Entscheidung: (c).**
**Begründung:** Reiter **Projekt** ist der **Abspieler-Modus** (ADR-007): „Laufordner öffnen…"
lädt einen fertigen Lauf aus `runs/` **ohne Core-API**; dort ist das Panel der *einzige*
Transport, die Leiste existiert nicht. Reiter **Slicing** ist die **Werkstatt**: `sim-focus-btn`
slict + simuliert frisch. (a) nähme dem Abspieler-Modus seinen Play-Knopf. `#seq-phase` ist
folgerichtig kein Duplikat, sondern die Projekt-Instanz von `#sim-phase` (`main.ts:3311-3312`,
`3333-3334` setzen denselben String) — beide bleiben.

**Präzisierung der #148-Regel:** „In der Leiste steht nur, was sich mit der Zeit ändert" regelt
den *Inhalt der Leiste im Reiter Slicing* — sie war nie eine Regel über Duplikate. `#traj-io`
ändert sich mit der Zeit und bleibt im Panel, weil es in einem anderen Reiter wohnt.

**Der eigentliche Fehler, den die Frage freilegte:** Vier Schalter steuern dieselbe Replay-Bühne
im geteilten 3D-Feld, sind aber je nur in einer Reiter-Gruppe **erreichbar**, während sie
**überall wirken**: `show-arm`/`grow-strand` im `aside#panel` (nur Reiter Projekt),
`druckstand`/`abstandszahl` im ⚙ (`isFocusTab("projekt") === false`, `viewer-settings-state.test.ts:21`).
`main.ts:1265`/`1332` lesen `panel.growStrandOn` aus der Checkbox, egal ob sichtbar — im Reiter
Slicing wächst der Strang nach einem unsichtbaren, unbedienbaren Schalter.
**Alternativen:** (i) nur `show-arm`/`grow-strand` ins ⚙ (Ticket-Vorschlag); (ii) ein Menü mit
reiterabhängig gefilterten Einträgen; (iii) zwei benannte Sektionen mit eigener Sichtbarkeitsregel.
**Entscheidung: (iii)** — ⚙-Sektion **„Replay-Bühne"** (Arm, Strang, Druckstand, Abstandszahl),
sichtbar wo eine Bühne läuft (also auch im Reiter Projekt bei offenem Lauf); Sektion
**„Modellansicht"** (Kontext, Basis, Bemaßung) bleibt an `isFocusTab`.
**Begründung:** (i) nähme die Häkchen aus dem einzigen Reiter, in dem sie heute bedienbar sind.
`isFocusTab` ist der falsche Türsteher: es fragt „ist das ein Wand-Fokus-Reiter", nicht „läuft
hier ein Replay". (iii) benennt die Kategorie, die es ohnehin gibt, und macht die
Sichtbarkeitsregel ehrlich, statt sie im Menü zu verstecken. Umsetzung: **#159**.

**Korrektur zum Eintrag „Player-Leiste entrümpeln (#148)" oben:** Dort steht, `#traj-warnings`
„steht genau dafür leer daneben". **Das ist falsch.** `panel.ts:496-518` füllt die Liste bereits
mit den zusammengefassten Trajektorien-Warnungen (`reach` etc., Deckelung aus #32), und
`#traj-meta` trägt schon Dauer, letztes Sample, „io kompensiert", Lagequelle und
Max. Achsauslastung (`panel.ts:459-491`). Der Kollisionsbefund zieht in einen **bewohnten** Block.
Zweitens ist die #156-Zusage „Badge-Klick öffnet `#trajectory-panel`" **nicht erfüllbar**: der
Badge lebt im Reiter Slicing, das Panel im Reiter Projekt — der Klick müsste den Reiter wechseln,
was #147 dem Geist nach verbietet („ein Klick darf die Bühne nicht wechseln"). **Folge:** Der
Befund ist Lauf-Eigenschaft **beider** Schauplätze; die Zerlegungsfunktion (Zahlen → Meta-Paare,
Vorbehalte → Warnungspunkte) bleibt rein und wird zweimal benutzt — im Panel und in einem eigenen,
aufklappbaren Befundblock der Leiste. #156 ist entsprechend kommentiert; Reihenfolge **#157 vor #156**.

**Out of scope (Karte #139):** die Befund-Parität des Abspieler-Modus im Übrigen (Reiter Projekt
zeigt weder Badge noch Timeline-Marker noch Abstandszahl, obwohl ein Lauf von der Platte seinen
`meta.collision`-Block mitbringt). Echter Mangel, aber die Karte macht den *Modul-Druckweg*
begehbar, sie vervollständigt nicht den Abspieler-Modus.

## 2026-07-09 — Retry mit Backoff um `os.replace` gegen transienten WinError 5/32 (#158)

**Frage:** Die atomare Schreibstelle `write_project` (ADR-018) schwenkt ihre Temp-Datei per
`os.replace` ein. Auf Windows scheitert dieser Rename sporadisch mit `PermissionError [WinError 5]`
(bzw. 32), wenn ein Fremdprozess (Defender, Suchindexer, Backup) kurz ein Handle auf die eben
geschriebene Datei hält — `os.replace` ist dort atomar, aber nicht retry-frei. Folge: die Suite ist
auf Windows sporadisch rot mit *wechselnden* Tests (der Fehler trifft jeden Pfad, der die
Schreibstelle benutzt), im Produktivbetrieb bricht eine Mutation mit `PermissionError` ab, obwohl
der Zustand konsistent ist und ein Wiederholungsversuch durchgelaufen wäre. Auf POSIX tritt das
nicht auf (Rename ignoriert offene Handles).

**Alternativen:**
(a) Retry-Schleife direkt in `write_project` inline — zweite atomare Schreibstelle
(`write_workstation_artifact`, ADR-021) bliebe ungeschützt oder bekäme eine Kopie derselben Schleife.
(b) **Ein gemeinsamer Helfer** `fgc.atomic_io.replace_with_retry(src, dst)`, den beide Schreibstellen
benutzen.
(c) Den Retry in `paths.py` unterbringen.
(d) Optimistisch nichts tun / Fehler nach oben reichen und die Aktion scheitern lassen.

**Entscheidung: (b)** — neues Modul `core/src/fgc/atomic_io.py` mit `replace_with_retry(src, dst)`:
bis zu 5 Versuche, Backoff 10–50 ms, fängt **nur** `OSError` mit
`getattr(exc, "winerror", None) in {5, 32}`, reicht alles andere sofort durch und wirft nach
erschöpften Versuchen die Original-Exception. Beide atomaren Schreibstellen (`write_project` **und**
`write_workstation_artifact`) rufen ihn auf.

**Begründung:** Der Fehlerkreis im Issue trifft `test_workstation_choice.py` mit — dessen Schreibpfad
läuft über `write_workstation_artifact`. Damit ist die im Issue offen gelassene Triage-Frage
(„gilt der Retry auch für die Workstation-/Tool-Artefakte?") *empirisch* mit **ja** beantwortet: die
zweite Schreibstelle ist nachweislich betroffen. Ein gemeinsamer Helfer statt zweier Kopien hält die
Retry-Politik an *einer* Stelle (Grep-Kriterium: jedes `os.replace` einer atomaren Schreibstelle
geht durch `replace_with_retry`). `paths.py` (c) ist der falsche Ort — reine Repo-Pfad-Konstanten,
kein I/O-Verhalten. (d) verwirft den Sinn: der Fehler ist transient und verschwindet beim Wiederholen.
Die Atomarität aus ADR-018 bleibt unangetastet (weiterhin Temp-Datei + atomarer Rename), darum kein
neuer ADR, sondern eine robustheits-lokale Ergänzung der bestehenden Entscheidung.

**`winerror`-Zugriff über `getattr(..., None)`:** auf POSIX trägt `OSError` kein `winerror`-Attribut;
`getattr` liefert dort `None`, `None ∉ {5, 32}` → jeder POSIX-Fehler wird sofort durchgereicht, kein
Leerlauf-Retry. Damit läuft der Helfer (und sein Test, `test_atomic_io.py`, mit gestubbtem `os.replace`)
plattformunabhängig.

**Verifikation:** Lackmustest `test_mutate_print_job.py::test_lock_serializes_concurrent_mutations`
(scheiterte vorher isoliert in ~2/6 Läufen mit `assert 35 == 40`, weil ein Worker-Thread am WinError 5
starb und seine Bumps verlor) ist nach dem Fix 6/6 grün; `test_project.py` + `test_workstation_choice.py`
dreimal in Folge grün.

## 2026-07-09 — Modul-Replay S1: Endeffektor am Flansch + TCP-Marker am Druckort (Issue #151, Karte #139 → #147)

**Frage:** Der Druckort-Arm (`druckortArm`) zeigte im Modul-Replay nur die nackten Kapseln/Meshes —
kein Werkzeug am Flansch, kein TCP-Marker auf der Bahn. Beide Views (`attachToolMeshToArm`,
`TcpMarkerView`) existierten bereits aus dem Wand-Pfad (#28/#14). Wie ruft man sie am Druckort auf,
ohne (a) über Modulwechsel hinweg doppelte Endeffektoren anzuhängen und (b) den Marker im falschen
Koordinatensystem (Wand-Ursprung statt Modul-Lage) zu platzieren?

**Alternativen — Endeffektor-Anhängung:**
(a) Tool je Modulwechsel an den frisch gebauten Arm hängen — aber der Druckort-Arm wird über
`buildDruckortScene` **wiederverwendet** (nicht neu erzeugt), also würde die Flansch-Gruppe Meshes
akkumulieren.
(b) `clearFlange()` **vor** jedem Anhängen in `buildDruckortScene` (Muster `arm.ts:401-406`), plus
Sequenz-Guard gegen ein zu spät aufgelöstes Async-Mesh eines schon abgeräumten Baus.
(c) Den Arm je Modulwechsel wegwerfen und neu bauen (wie der Wand-Arm je Lauf) — teurer Neuaufbau,
verwirft die bestehende Wiederverwendungs-Logik.

**Alternativen — TCP-Marker-Ort:**
(d) Unter `druckortGroup` parken (wie der Arm) — falsch: die Marker-View baut in **abschnittslokalen
data-mm**, `druckortGroup` trägt aber keine Modul-Pose, der Marker läge am Wand-Ursprung.
(e) Unter der **`moduleGroup`** des aktiven Moduls parken — die trägt `module_pose.workstation`, also
liegt der Marker in derselben lokalen data-mm-Welt wie das Modul-Rechteck: korrekte Bahn-Lage.

**Entscheidung: (b) + (e).**
- **Endeffektor:** `buildDruckortScene` ruft `druckortArm.clearFlange()` und dann
  `attachToolMeshToArm(druckortArm, guard)`. Der Guard kapselt `druckortLoadSeq` (in
  `clearDruckortScene` je Neubau/Teardown erhöht): löst das Async-Mesh nach einem neueren Bau auf,
  wird es verworfen (`disposeSubtree`) statt angehängt. `attachToolMeshToArm` bekam dafür ein
  **optionales** `stillValid`-Argument — der Wand-Pfad (`main.ts:1637` u. a.) ruft es weiter ohne
  Guard, bit-identisch.
- **TCP-Marker:** je Modul-Bau (`moduleReplay.built !== idx`) eine frische `TcpMarkerView(step.targets)`,
  hinzugefügt zu `druckortModule` (der `moduleGroup`); der alte Marker wird mit seiner `moduleGroup`
  über `disposeSubtree` GPU-sauber abgeräumt. Gespeist aus der **lokalen** Modulzeit
  (`locateSequenceTime → localFraction`), nicht der Sequenz-Gesamtzeit. Im Umbau-Schritt ruhen Arm,
  Werkzeug (Kind des Flansches, folgt `druckortArm.visible = false`) und Marker (`markerVisible=false`).
- **Hausmuster (#128):** die reine Ableitung Cursor → Bühnenzustand (aktiver Modul-Index,
  Arm-/Marker-Sichtbarkeit, Marker-Fraktion) liegt three.js-frei in
  `viewer/src/trajectory/modulereplay.ts` (`moduleReplayFrame`) mit `modulereplay.test.ts` daneben;
  `updateModuleReplay` verdrahtet nur three.js. Der bisher inline berechnete `idx` und die
  Phasen-Sichtbarkeit ziehen jetzt aus dieser getesteten Funktion.

**Begründung:** (b) hält den einen wiederverwendeten Druckort-Arm konsistent, ohne den teuren
Neuaufbau aus (c); der Sequenz-Guard schließt die Async-Race, die reines `clearFlange` allein offen
ließe. (e) folgt genau der Koordinaten-Semantik der bestehenden Bühne (Modul-Rechteck baut in
denselben data-mm) — der Marker liegt damit **auf der echten Modul-Bahn**. Die provisorische
Endeffektor-Hülle bleibt provisorisch (PRD #124 Punkt 3): das Werkzeug wird **angezeigt**, es
beurteilt nichts (ADR-007). Kein neuer ADR — reine Präsentations-Verdrahtung im Rahmen von ADR-007/022.

**Regressionsanker (Kriterium „Wand-Replay bit-identisch"):** der Wand-Pfad wurde nicht angefasst
(die neue `attachToolMeshToArm`-Signatur ist rückwärtskompatibel, zweites Argument optional). Beleg:
alle bestehenden vitest-Tests weiter grün (Baseline 66 Dateien / 775 Tests → 67 / 779 mit den vier
neuen `moduleReplayFrame`-Tests).

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` 67 Dateien / 779 Tests
grün, `npm run build` clean.

## 2026-07-09 — Korrektur zu #151: der Bau-Guard verwarf den Endeffektor immer (Bau-Zähler-Semantik)

**Frage:** Der erste #151-Commit (`20f5d03`) hängte den Endeffektor am Druckort-Flansch **nie** an,
sobald die Workstation ein Mesh trägt (Normalfall, ADR-021). Ursache: der Sequenz-Guard des
Tool-Meshes und der `++`-Zähler des Workstation-Meshes teilten sich `druckortLoadSeq`, aber das
Workstation-Mesh **erhöhte** den Zähler **im selben Bau** — nach `const toolSeq = druckortLoadSeq` (N)
lief `const seq = ++druckortLoadSeq` (N+1) noch synchron. Löste das async geladene Tool-Mesh später
auf, war `toolSeq (N) !== druckortLoadSeq (N+1)` → `disposeSubtree(obj); return;`. `toolAtFlange` blieb
dauerhaft `false`. Die vitest-Tests fingen das nicht (nur die three.js-freie `moduleReplayFrame`),
`ui_smoke.mjs` lief nicht.

**Analyse der Zähler-Semantik:** `druckortLoadSeq` wurde nur an zwei Stellen verändert — in
`clearDruckortScene()` und beim Workstation-Mesh. `buildDruckortScene` ruft als Erstes
`clearDruckortScene()`, der Zähler ist damit **pro Bühnen-Neubau bereits genau einmal erhöht**. Das
zweite `++` war also redundant: ein neuer Bau (oder Teardown) zählt über `clearDruckortScene` ohnehin
weiter und invalidiert jeden offenen Guard. Beide Aufrufer von `clearDruckortScene` (`buildDruckortScene`
und `exitDruckortScene`) bumpen — der Guard invalidiert bei echtem Neubau **und** Teardown.

**Alternativen:**
(a) Nur das `++` beim Workstation-Mesh zu einem Lese-Zugriff entschärfen (Minimalfix) — korrekt, aber
weiter ein nackter `let`-Zähler mit zwei entfernten Mutationsstellen, ununterscheidbar von einem
künftigen versehentlichen `++`.
(b) Die Zähler-/Guard-Logik als kleine reine, three.js-freie Klasse `BuildSeq`
(`viewer/src/render/buildseq.ts`) herausziehen: `bump()` (genau an der Neubau-/Teardown-Stelle),
`current` (nur lesen), `guard(seq)`. main.ts hält eine Instanz.

**Entscheidung: (b).** Der Fix ist substanziell (a) — kein `++` mehr im selben Bau — aber verankert in
einer benannten Invariante: „EIN bump je Neubau/Teardown, nie je Mesh". Die Klasse macht die Regel
testbar, wo die reine `moduleReplayFrame` es nicht konnte. Neue Tests (`buildseq.test.ts`) modellieren
die Aufruf-Reihenfolge von `buildDruckortScene`: (a) direkt nach dem Bau ist der Tool-Guard gültig,
(b) nach einem weiteren `bump` ungültig, (c) — der Regressionsanker — das Erfassen des
Workstation-Mesh-Guards im **selben** Bau lässt den Tool-Guard gültig. Test (c) schlägt gegen die alte
`++`-Semantik fehl und hält jetzt.

**Wand-Replay:** unverändert; `attachToolMeshToArm` behält die rückwärtskompatible Signatur (der
Wand-Pfad ruft weiter ohne Guard).

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` 68 Dateien / 784 Tests
grün (779 → 784 mit den 5 neuen `BuildSeq`-Tests), `npm run build` clean. Fix in denselben #151-Commit
amendiert (noch nicht gepusht).

## 2026-07-09 — #152: Druckfortschritt am Druckort — wachsender Strang + Druckstand statt Vollbox

**Frage:** Am Druckort (#96/#97) stand das Modul von Sekunde null als **volle, halbtransparente Box**
da, während der Arm hindurchfuhr — die Bühne zeigte das *Soll* als Volumen, aber keinerlei *Ist*.
Entscheidung #147 (Wayfinder-Karte #139): „**Soll als Linie, Ist als Volumen**". Wie überträgt sich
das ohne neue Kinematik und ohne den Wand-Pfad zu berühren?

**Entscheidung:** Die Voll-Box-Füllung (`MeshStandardMaterial`) in `buildDruckortScene` entfällt; der
**Soll-Umriss** bleibt als `EdgesGeometry`-Rechteck stehen (Lage/Orientierung/Sollgröße). Das
**Ist-Volumen** zeigt beim Replay der schon für die Wand-Bühne existierende **`DruckstandView`**
(#128/ADR-024), gespeist aus der **Targets-AABB** des aktiven Moduls und `setGrowth(fraction)` aus der
modul-lokalen Zeit — dasselbe Volumen, gegen das `fgc.collision.check` rechnet. Dazu ein **wachsender
Strang** über die bestehende **`ToolpathView.setGrowth`** (#27). Beide Views hängen — wie der
TCP-Marker (#151) — unter der `moduleGroup` (abschnittslokale data-mm), werden **je Modul** frisch
erzeugt und beim Modulwechsel über `disposeSubtree(druckortModule)` mit abgeräumt.

**Alternativen:**
(a) Eine zweite, eigene Wachstums-Ableitung neben `moduleReplayFrame` stellen — verworfen (Batch-Hinweis
    #151: „Bau darauf auf, keine zweite Ableitung daneben"). Stattdessen ein Feld `growthFraction` in
    denselben reinen Frame.
(b) `markerFraction` für das Wachstum wiederverwenden — verworfen: im **Umbau-Schritt** ist
    `markerFraction = 1` (der Marker ist dort ohnehin unsichtbar), aber das **ankommende** Ziel-Modul
    ist noch **nicht** gedruckt. Wachstum verlangt dort **0**, sonst zeigte das frisch eingewechselte
    Modul sofort einen voll gewachsenen Druckstand/Strang. Darum ein **eigenes** Feld:
    `growthFraction = printing ? localFraction : 0`.
(c) Views in `buildDruckortScene` statt in `updateModuleReplay` erzeugen — verworfen: `buildDruckortScene`
    hat keine Targets (die stecken im `ModuleReplayStep`), und die Bühne dient auch der reinen
    Druckort-Ansicht (#96) ohne Replay. Views gehören dorthin, wo die Targets sind — analog #151.

**Begründung:** Ein Feld in der bestehenden reinen Ableitung (`moduleReplayFrame`) hält Zeit→Wachstum
three.js-frei und vitest-nah (Hausmuster #128); die Trennung von `markerFraction` ist die eigentliche
fachliche Einsicht (Marker ruht im Umbau, Wachstum startet neu bei 0). Der Reset je Modul fällt gratis
aus dem #151-Lebenszyklus (frische Views unter `moduleGroup`, `disposeSubtree` beim Wechsel) — kein
globaler Zustand über Module hinweg. Der ⚙-Schalter `showDruckstand` wird am Druckort nur
**mitverdrahtet** (Erzeugung mit `visible = showDruckstand`, Toggle-Handler aktualisiert
`moduleReplay.druckstand`), ohne sein Wand-Verhalten oder seine Struktur zu ändern (Rücksicht auf #159).

**Wand-Replay:** unberührt (Regressionsanker) — `showRun` und der globale `druckstand`/`toolpathView`
bleiben wie gehabt.

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` 68 Dateien / 787 Tests grün
(784 → 787 mit 3 neuen `moduleReplayFrame`-Wachstumstests), `npm run build` clean.

## 2026-07-09 — #153: Kollisionsanzeige am Druckort — Abstandszahl, Glied-Einfärbung, Marker des aktiven Moduls (Karte #139 → #147)

**Frage:** Am Druckort (#96/#97) wird der Kollisions-Befund eines Modul-Laufs geladen
(`recordCollisionFinding` fürs Palette-Badge), aber `updateModuleReplay` las ihn nie — er wurde
weggeworfen. Wie zeigt die Druckort-Bühne ihn (Glied-Einfärbung, Live-Abstand, Timeline-Marker) genau
wie das Wand-Replay (#128), ohne den Wand-Pfad zu berühren, und wie bilden sich die **modul-lokalen**
Intervalle des aktiven Moduls auf die **Sequenzachse** der Player-Leiste ab (Entscheidung #147,
Variante b: nur das aktive Modul, keine Marker über Umbaupausen, Klick bleibt im Modul)?

**Entscheidung:** Eine neue reine Funktion `projectModuleMarkers(markers, plan, moduleIndex)` in
`viewer/src/trajectory/modulereplay.ts` (neben `moduleReplayFrame`) verschiebt die von
`timelineMarkers` (collision-state.ts) über der **Modul-Dauer** erzeugten Marker auf die
Gesamt-Sequenzachse: `seekTime_s → starts_s[moduleIndex] + seekTime_s`, Fraktionen auf `total_s`
normiert. `main.ts` speist beim Modulwechsel (`built !== idx`) Badge + projizierte Marker über die
neue Panel-Methode `SimulationPanel.setModuleCollision(collision, markers)` ein und wendet je Frame
`applyModuleCollisionFrame(step, cur.localTime_s, printing)` an — Glied-Einfärbung am
**`druckortArm`** (`setLinkHighlight` aus `linkHighlightAt`) + Live-Abstand (`distanceReadout`,
⚙-`showAbstandszahl`) aus der **modul-lokalen** Sample-Zeit. `ModuleReplayStep` trägt dazu jetzt
`collision` + `sampleTimes`. Die Lügen-Statuszeile in `startModuleSequenceAtDruckort` fällt, sobald
irgendein Modul einen Befund trägt (`anyFinding`); sonst bleibt die ehrliche Zeile.

**Alternativen:**
(a) Marker im Panel projizieren (Panel bekommt `plan` + `moduleIndex`) — verworfen: das Panel würde
    Sequenz-Wissen tragen; die Projektion ist reine Darstellungsmathematik und gehört testbar,
    three.js-/DOM-frei nach `trajectory/` (Hausmuster #151/#152). Das Panel bekommt fertige Marker.
(b) `projectModuleMarkers` gegen `CollisionMeta` neu rechnen lassen (Intervalle → Marker + Shift in
    einem) — verworfen: das dupliziert die rot/gelb-Marker-Erzeugung aus `timelineMarkers`. Die neue
    Funktion ist bewusst **generisch** über eine `ModuleLocalMarker`-Minimalform (nur die vier
    Zeitfelder) und verschiebt nur — Status/Titel bleiben unangetastet, keine ui→trajectory-Kopplung.
(c) `applyCollisionAtTime` (Wand-Pfad) am Druckort mitbenutzen — verworfen: es färbt `armView`
    (Wand-Arm) und liest `currentCollision`/`currentCollisionTimes` (Wand-Zustand). Der Druckort hat
    einen eigenen Arm (`druckortArm`) und einen Befund **je Step**; ein eigener Frame-Applier hält
    beide Pfade getrennt (Wand-Replay bit-identisch, Regressionsanker).
(d) Beim Einzel-Modul (`playModuleRunAtDruckort`) `setCollisionFinding` (Wand-Weg) beibehalten —
    verworfen: das setzte die Marker über der Modul-Dauer, was für ein Einzelmodul zufällig stimmt,
    aber die Marker-Erzeugung doppelt neben `updateModuleReplay` stellt. Jetzt treibt
    `updateModuleReplay` die Anzeige für **beide** Wege (Einzel wie Sequenz) einheitlich; der direkte
    `setCollisionFinding`-Aufruf im Einzel-Pfad entfällt.

**Bedingung (c) „keine Marker über Umbaupausen":** fällt konstruktionsbedingt aus — modul-lokale
Zeiten liegen in `[0, duration]`, also innerhalb der Druckphase `[start, start+duration]`; die
anschließende `umbau_s`-Pause bekommt nie einen Marker. Der Klick (`onSeek(seekTime_s)`) landet auf
einer **Sequenz-Zeit innerhalb der Druckphase** des aktiven Moduls — `seek` re-emittiert, aber
`built` bleibt gleich, also kein Bühnenwechsel.

**Altlauf ohne Befund (US 25):** `step.collision === null` ⇒ `setModuleCollision(null, [])` räumt
Badge + Marker ab, `applyModuleCollisionFrame` stellt Arm neutral + blendet die Zahl aus; die
Statuszeile bleibt die ehrliche „keine Kollisionsprüfung". Kein Crash.

**⚙-Schalter:** `showDruckstand` war am Druckort schon mitverdrahtet (#152); `showAbstandszahl` frischt
jetzt zusätzlich den Druckort-Frame (`reapplyModuleCollisionFrame`). Struktur der ⚙-Schalter unberührt
(Rücksicht auf #159) — nur ihre Zustände werden mitgelesen.

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` 68 Dateien / 793 Tests grün
(787 → 793 mit 6 neuen `projectModuleMarkers`-Tests), `npm run build` clean. `ui_smoke.mjs` Schritt 2l
um einen Druckort-Kollisions-Check ergänzt (`__moduleSimDebug.activeCollision`), Skript nicht ausgeführt
(braucht Core-API + Vite-Dev + headless Edge).

## 2026-07-09 — Player-Leiste S1: zwei Modi statt Überlagerung (Issue #154, Karte #139 → #148)

**Frage:** Das `#sim-dock` zeigte die Startknöpfe (`#sim-focus-btn`, `#sim-sequence-btn`) und den
Player (`#sim-player`) **gleichzeitig** — die Startknöpfe wurden nie versteckt, auch wenn ein Replay
lief. In der einzeiligen Leiste überlagerten sich so bei gefüllter Phase + Badge + Abstandszahl die
Elemente. Wie auflösen, ohne die Zeile zu brechen?

**Alternativen:**
(a) `flex-wrap` auf `.sim-dock` — verworfen: das erlaubt eine zweite Zeile und ändert die Dock-Höhe;
    vertikale Bildfläche ist knapp, das Dock ankert am Fuß des 3D-Felds.
(b) Textlängen kürzen / Popover für die Hinweise — verworfen: behandelt das Symptom, nicht die
    Ursache. Die Ursache ist, dass **zwei Zustände gleichzeitig** stehen, nicht die Breite einzelner
    Texte.
(c) **Zwei Modi (gewählt):** Start-Modus (Startknöpfe + Hinweise sichtbar, Player weg) und
    Replay-Modus (Player sichtbar, Startknöpfe weg). Genau ein Satz Elemente steht je Zeit in der
    Leiste — die Zeile bleibt kurz und einzeilig, keine Höhenänderung. `← Übersicht` **und** das Ende
    eines Laufs (`hidePlayer`/`reset`) stellen den Start-Modus her.

**Entscheidung:** (c). Die Modus-Wahl liegt als reine, DOM-freie Funktion in
`viewer/src/ui/sim-dock-state.ts` (`simDockMode`, `simDockHidden`): Eingabe = *Replay läuft? API
erreichbar? Vorbedingung gesetzt?*, Ausgabe = welche der fünf Elemente `hidden` sind (Startknöpfe,
API-Warnung, Vorbedingung, Player). Die dünne DOM-Anbindung (`_applyDockMode`) sitzt in
`viewer/src/ui/simulation.ts` und weist **ausschließlich `.hidden`** zu (Lehre aus #56 — kein
`style.display`, keine CSS-Klassen-Gymnastik). Getrieben wird sie an den bereits zentralen Punkten
`showPlayer` (→ Replay), `hidePlayer`/`reset` (→ Start), `setApiAvailable`, `setPrecondition` — die
für **beide Bühnen** gelten (Wand-Replay und Modul-Replay am Druckort, `teardownModuleReplay` ruft
`hidePlayer` über `backToOverview`/`endReplay`).

**Begründung:** Die Modus-Wahl ist reine Zustandslogik und gehört testbar (vitest) ins `ui/`-Hausmuster
(wie `druckort-state.ts`/`scope-state.ts`); `main.ts`/`simulation.ts` verdrahten nur. Der bestehende
DOM-Vertrag (IDs, Reihenfolge) bleibt unangetastet — `shell-structure.test.ts` bekommt nur das
`hidden`-Verhalten der Startknöpfe (Start-Modus als DOM-Ausgangszustand) ergänzt. Als zusätzliches Netz
gegen künftiges Zeilenwuchern trägt `#sim-status` ein `min-width: 0` (statt `flex-wrap`) — die Note darf
unter ihre Inhaltsbreite schrumpfen. Die ⚙-Schalter-Struktur bleibt unberührt (Rücksicht auf #159).

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` grün (Baseline 793 + neue
`sim-dock-state`-Tests + ein Test in `shell-structure.test.ts`), `npm run build` clean. `ui_smoke.mjs`
Schritt 2l um zwei Modus-Checks ergänzt (Replay-Modus: Startknöpfe weg + Player da; nach `← Übersicht`:
Startknöpfe zurück); Skript nicht ausgeführt (braucht Core-API + Vite-Dev + headless Edge).

## 2026-07-09 — Player-Leiste S2: Abspielgeschwindigkeit als Vielfaches der Echtzeit (Issue #155, Karte #139 → #148)

**Frage:** `TrajectoryPlayer` lief in **Echtzeit** (`_time + dt` mit echten RAF-Sekunden). Ein realer
Abschnitt der Denkmal-Wand dauert ≈ 87 min — „Play" war unbenutzbar, nur der Slider. Der Player braucht
eine **Rate** (Vielfaches der Echtzeit, Default 1×). Der Knackpunkt: `buildSequencePlan` backt die
Umbaupausen (`UMBAU_SECONDS = 3`) **in die Trajektorienzeit** ein (`total_s`/`starts_s` enthalten sie).
Wie skaliert man die Druckphasen mit dem Faktor, ohne die Umbaupausen mitzuskalieren (bei 200× wären 3 s
= 15 ms Wanduhr, unsichtbar — genau das, was #27 sichtbar machen wollte) **und** ohne die Zeitachse zu
verschieben (der Slider muss Trajektoriensekunden zeigen)?

**Alternativen:**
(a) Naiv `_time + dt * rate` mit **konstanter** Rate — verworfen: skaliert die Umbaupausen mit; bei
    200× verschwindet der 3-s-Umbau-Schritt. Verletzt „UMBAU skaliert NICHT mit".
(b) Umbau-Länge **im Plan** mit `rate` strecken (`umbau_s * rate`) — verworfen: dann wandert die
    Zeitachse mit dem Faktor, der Slider zeigt keine Trajektoriensekunden mehr. Verletzt Kriterium 1
    („Faktor wirkt auf das Abspielen, nicht auf die Zeitachse").
(c) **Zeitabhängige Rate** im Player: `rateAt(t) → { rate, until_s }` liefert den Faktor innerhalb einer
    Druckphase und **1×** innerhalb einer Umbaupause; der Player integriert Wanduhr → Trajektorienzeit
    und **teilt jeden Frame an den Phasengrenzen**.

**Entscheidung:** (c). `TrajectoryPlayer` bekommt ein optionales `rateAt` (`RateSpan = { rate, until_s }`,
Default konstant 1×). Die Phasen-Rate ist eine **reine, vorwärts gerichtete** Funktion `sequenceRateAt`
neben `buildSequencePlan`/`locateSequenceTime` (`trajectory/sequence.ts`): sie nutzt die vom Plan bereits
bekannten Phasengrenzen und gibt `rate = printRate` in `[start, printEnd)`, `rate = 1` in der Umbaupause,
plus `until_s` = nächste Grenze. **Vorwärts gerichtet** (halboffene Intervalle) — anders als
`locateSequenceTime` (dessen Druck-Ende noch „printing" ist, für die Anzeige), sonst entstünde am
Grenzpunkt ein Null-Intervall → Endlosschleife. Der Player-Kern `advance(t0, dtWall)` läuft in einer
Schleife: er liest `rateAt(t)`, rechnet die Wanduhr-Sekunden **bis zur Grenze** (`(until_s − t)/rate`),
rastet auf die Grenze ein, wenn das Budget reicht (dann liest die nächste Iteration die neue Rate),
sonst integriert er den Rest — so **frisst kein einziger langer Frame bei 200× die Umbaupause**, und der
Player rastet **driftfrei** exakt auf `duration` ein (`Math.min`, wie zuvor). Für das Einzel-/Wand-Replay
(keine Umbaupause) ist `rateAt` konstant der Faktor (`until_s = ∞`). Der Faktor ist eine **Sitzungs-
Eigenschaft** (Modul-Variable `replaySpeed` in `main.ts`, wie `showDruckstand` & Co.): jeder neu erzeugte
Player liest ihn **live** über seine `rateAt`-Closure (Wechsel wirkt sofort), er überlebt Lauf-/Modul-/
Bühnenwechsel und startet bei 1× — kein `localStorage`. Bedienelement: ein schmales `<select>`
(`#sim-speed`) im **Replay-Modus** der Leiste — die `hidden`-Matrix in `ui/sim-dock-state.ts` bekommt ein
`speed`-Feld (sichtbar wie der Player), nur `.hidden` (Lehre aus #56). Jede Option nennt Faktor **und**
resultierende Replay-Dauer („50× · ~1:44"); die Dauer-Rechnung (`replayEta = Σ Druckphasen / rate +
Σ Umbaupausen`, ungeteilt) und -Formatierung (`formatEta`) liegen als reine Funktionen in
`ui/speed-control.ts` mit vitest. **Eine Zeile bleibt eine Zeile** (#154) — keine Höhenänderung. Die
⚙-Schalter-Struktur bleibt unberührt (Rücksicht auf #159).

**Begründung:** Nur die zeitabhängige Rate erfüllt beide harten Kriterien gleichzeitig — Faktor aufs
Abspielen (a scheitert) und Zeitachse in Trajektoriensekunden (b scheitert). Die Phasengrenzen-Aufteilung
ist der eigentliche Kern: ohne sie verschluckt ein langer Frame bei hohem Faktor die Umbaupause; mit ihr
bleibt der Umbau-Schritt 3 s Wanduhr und auch bei 200× sichtbar. Die reine `sequenceRateAt`/`advance`-
Trennung folgt dem `trajectory/`-Hausmuster (`interpolate.ts`/`sequence.ts`) und ist mit fake timers
(kein RAF-Echtlauf) testbar — der Boundary-Split-Test fährt genau den 200×-Fall über eine Umbaupause.

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` grün (Baseline 804 → 827:
neue Tests in `speed-control.test.ts`, `sequence.test.ts` (`sequenceRateAt`), `player.test.ts` (`advance`
+ getaktete Frames), `sim-dock-state.test.ts`, `shell-structure.test.ts`), `npm run build` clean.
`ui_smoke.mjs` nicht ausgeführt (Auftrag).

---

## 2026-07-09 — Kollisionsbefund wird Lauf-Eigenschaft: traj-meta/-warnings + eigener Leisten-Block (Issue #156)

**Frage:** Der Kollisionsbefund stand als ~160-Zeichen-Satz (`replayStatusLine`) in der
Player-Leiste `#sim-status` und vermischte dort **zwei Textsorten**: eine Lauf-Eigenschaft
(der Befund, bleibt während des Abspielens stehen) und vergängliche Aktionsmeldungen. Wohin
gehört der Befund, und wie zerlegt man ihn, ohne die einzeilige Leiste zu sprengen?

**Widerlegter Body (wichtig):** Der Ticket-Body traf zwei Annahmen, die die **Korrektur aus
#157** kippte — und die Korrektur hat laut Auftrag Vorrang: (1) „`#traj-warnings` steht heute
leer daneben" ist falsch — `panel.ts` füllt die Liste bereits mit den gedeckelten
Trajektorien-Warnungen (#32), und `#traj-meta` trägt schon Dauer/Sample/io/**Lagequelle**/
Achsauslastung; der Befund zieht also in einen **bewohnten** Block und muss sich **einordnen**
(und die Lagequelle-Zeile entdoppeln), nicht einnisten. (2) „Badge-Klick öffnet
`#trajectory-panel`" ist unmöglich — der Badge lebt im Reiter **Slicing**, `#trajectory-panel`
im Reiter **Projekt**; die beiden sind **nie gleichzeitig sichtbar** (#157), ein Klick müsste
den Reiter wechseln — genau das, was #147 verbietet („ein Klick darf die Bühne nicht
wechseln").

**Erwogene Alternativen:**
- *(A)* Body wörtlich: Badge-Klick wechselt in den Reiter Projekt und fokussiert
  `#trajectory-panel`. **Verworfen** — Reiter-/Bühnenwechsel per Klick (gegen #147/#157).
- *(B)* Befund nur im Reiter Projekt, in der Leiste nur das kurze Badge. **Verworfen** — die
  Werkstatt (Slicing) ist der Ort, an dem man simuliert und den Befund sofort lesen will;
  ein Reiterwechsel zum Nachlesen reißt aus der Arbeit.
- *(C, gewählt)* Befund an **beiden** Schauplätzen aus **einer** reinen Funktion; in der
  Leiste ein **eigener, aufklappbarer** Block, den der Badge **ohne Reiterwechsel** öffnet.

**Entscheidung:** Eine reine, DOM-/three.js-freie Zerlegung `collisionMetaPairs` (Zahlen →
Definitions-Paare: `n_red`/`n_yellow`/`n_green`/`min_distance_mm`/Prüf-Modus) und
`collisionCaveats` (Vorbehalte → Warnungspunkte: `provisional` ⇒ „vorläufige Grenzwerte";
`travel_not_continuously_checked` ⇒ „Travel nicht lückenlos geprüft") in
`viewer/src/ui/collision-state.ts`, vitest daneben, **verbatim** aus `meta.collision`
(ADR-007). **Beide** Schauplätze konsumieren sie: (a) Reiter Projekt — die Paare ordnen sich
in die bewohnte `#traj-meta`, die Vorbehalte in `#traj-warnings` (vor die Trajektorien-
Warnungen) ein; die **Lagequelle-Zeile** behauptet den Befund nicht mehr doppelt (bei Befund
nur „geplant (Platzierung)", der ehrliche „…keine Kollisionsprüfung"-Zusatz bleibt nur ohne
Befund). (b) Reiter Slicing — die `#sim-dock`-Leiste bekommt `#sim-collision-panel` (ein
`<dl>` + `<ul>`), das der Badge (jetzt `role="button"`-Anker, Enter/Space/Klick) auf-/zuklappt;
als **Overlay** (`position:absolute`, `bottom:100%`) über der Leiste, damit **eine Zeile eine
Zeile bleibt** (#154). Sichtbarkeit nur über `.hidden` (#56). `#sim-status` trägt keinen
160-Zeichen-Satz mehr: mit Befund leer (Badge + Block sind der Anker), Aktionsmeldungen
bleiben; Altläufe ohne Block behalten die ehrliche Zeile (US 25) — keine leeren dl/ul, kein
Crash. Wand und Druckort speisen denselben Block (am Druckort aus dem aktiven Modul,
`setModuleCollision`, #153). Der Phasen-Pill-Tooltip verneint die Kollisionsprüfung nicht mehr
pauschal (verweist auf das Badge). Die ⚙-Schalter-Struktur bleibt unberührt (Rücksicht auf
#159). `replayStatusLine` bleibt für den Altlauf-Fall (`…keine Kollisionsprüfung`) in Gebrauch.

**Begründung:** Der Befund ist ein Ergebnis, kein Status — als überfliegbare Definitionsliste
+ Warnungspunkte liest er sich besser als ein Fließsatz und dupliziert nichts. Eine einzige
reine Funktion für beide Schauplätze verhindert Aussagen-Drift zwischen Abspieler-Modus und
Werkstatt (das war ohnehin die Absicht; der Body hatte nur einen Zielort zu wenig). Der eigene
Leisten-Block löst den Zielkonflikt aus #157/#147 (Befund in der Werkstatt lesbar, ohne Reiter-
/Bühnenwechsel) und respektiert #154 (Overlay statt zweiter Zeile).

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` grün (Baseline
827 → 836: neue Tests in `collision-state.test.ts` für `collisionMetaPairs`/`collisionCaveats`
+ neuer `#sim-collision-panel`-Block in `shell-structure.test.ts`), `npm run build` clean.
`ui_smoke.mjs` um Schritt 2m (Befundblock vorhanden, anfangs zugeklappt, Badge-Klick togglet
ohne Reiterwechsel) ergänzt, aber **nicht ausgeführt** (Auftrag).

## 2026-07-09 — Replay-Bühne: vier Schalter in eine benannte ⚙-Sektion, sichtbar wo eine Bühne läuft (Issue #159, Karte #139 → #157)

**Frage:** Vier Schalter steuern **dieselbe** Replay-Bühne im geteilten 3D-Feld, lagen aber
auf einander ausschließenden Reitern: `show-arm`/`grow-strand` als Panel-Häkchen im `aside#panel`
(nur im Reiter **Projekt** erreichbar), `druckstand`/`abstandszahl` im ⚙-Menü (nur in den
**Fokus-Reitern** sichtbar). Wirksam waren alle vier **überall** — im Reiter Slicing wuchs der
Strang also nach einem Schalter, den man dort weder sah noch umlegen konnte. Wie bringt man die
vier an **einen** Ort, der dort auftaucht, wo die Bühne läuft?

**Alternativen:** (a) Alles ins ⚙-Menü, aber weiter am `isFocusTab`-Gate hängen — dann bliebe
das Menü im Reiter Projekt unsichtbar, obwohl dort beim geladenen Lauf die Bühne läuft; die
Panel-Häkchen wären nur verschoben, nicht erreichbar gemacht. (b) Die Panel-Häkchen im Reiter
Projekt lassen und im Slicing **zusätzlich** spiegeln — zwei Zustände für einen Schalter (ADR-016
widerspricht). (c) **Gewählt:** Das ⚙-Menü bekommt **zwei benannte Sektionen** mit **getrennter
Sichtbarkeit**. „Modellansicht" (`context`/`basis`/`bemassung` + Einpassen) bleibt an `isFocusTab`.
„Replay-Bühne" (`show-arm`/`grow-strand`/`druckstand`/`abstandszahl`) zeigt sich, **wo eine Bühne
läuft**: in den Fokus-Reitern immer, im Reiter Projekt sobald dort ein Lauf offen ist. `isFocusTab`
ist der falsche Türsteher — es fragt „ist das ein Wand-Fokus-Reiter", nicht „läuft hier ein Replay".

**Entscheidung:** Die reine **Sektions-Sichtbarkeitsregel** `viewerSettingsSections(tab, replayOpen)`
(+ `viewerSettingsMenuVisible`) landet DOM-frei in `viewer/src/ui/viewer-settings-state.ts` (vitest
über Reiter × Lauf-offen): `modelView = isFocusTab(tab)`, `replayStage = isFocusTab(tab) || (tab ===
"projekt" && replayOpen)`, Menü sichtbar ⇔ mindestens eine Sektion. „Lauf offen" bestimmt `main.ts`
impur daran, ob ein Toolpath geladen ist (`toolpathView !== null` — daran hängen Arm/TCP/Strang/
Druckstand). `ui/viewer-settings.ts` wird um **Sektions-Struktur** erweitert (`SectionSpec` mit
Titel + eigener `ToggleSpec`-Liste + optionalem `fitWall`-Knopf); `setSectionVisible(key, visible)`
schaltet je Sektion nur `.hidden`, das Menü folgt (sichtbar ⇔ eine Sektion sichtbar), `setToggleVisible`
blendet **einzelne** Schalter aus. Die zwei Panel-Häkchen (`show-arm`, `grow-strand`, samt
`#grow-strand-label`) **fallen ersatzlos** aus `index.html`; `panel.growStrandOn`/`panel.armVisible`
entfallen — die Aufrufer in `main.ts` (`applyStrandReveal`, `onLayerChanged`, Einzel-/Sequenz-Arm)
lesen künftig `viewerSettings.get("grow-strand")`/`get("show-arm")`, die `change`-Wirkung
(`armView.visible` / `applyStrandReveal`) zieht in den `onToggle`-Callback um (Wirkung sofort). Die
Sequenz-Modus-Kopplung wandert mit: `panel.setSequenceMode` blendet nicht mehr das Strang-Label aus,
stattdessen ruft `main.ts` an den Start/Teardown-Stellen `viewerSettings.setToggleVisible("grow-strand",
…)`. **Keine Verhaltensänderung der Bühne selbst** — nur Ort und Erreichbarkeit der Schalter;
Defaults unverändert (Arm an, Strang wächst an, Druckstand aus, Abstandszahl an).

**Begründung:** Ein Schalter, der überall wirkt, gehört an einen Ort, der überall auftaucht, wo er
wirkt — die Sektion folgt der Bühne, nicht dem Wand-Fokus. Die getrennte Sichtbarkeit hält die
„Modellansicht" (Fokus-gebunden) sauber von der „Replay-Bühne" (Lauf-gebunden) getrennt, statt beide
an ein grobes Menü-Gate zu hängen. Die Regel bleibt eine **reine Funktion** (testbar über Reiter ×
Lauf-offen), die Sichtbarkeit **ausschließlich `.hidden`** (Lehre aus #56), ein Zustand je Schalter
(ADR-016).

**Verifikation (aus `viewer/`):** `npx tsc --noEmit` clean, `npx vitest run` grün (Baseline 836 → 842:
sechs neue Fälle in `viewer-settings-state.test.ts` für `viewerSettingsSections`/`viewerSettingsMenuVisible`
über Reiter × Lauf-offen; `shell-structure.test.ts` um den Nachweis ergänzt, dass `show-arm`/`grow-strand`
aus dem Projekt-Panel verschwunden sind), `npm run build` clean. `ui_smoke.mjs` um Schritt 2n (zwei
benannte Sektionen, vier Schalter in „Replay-Bühne", beide im Slicing sichtbar, alte Panel-Häkchen weg,
`show-arm` bedienbar) ergänzt, aber **nicht ausgeführt** (Auftrag).

## 2026-07-09 — Soll-Umriss am Druckort lag eine halbe Wanddicke neben dem Druck (Bugfix, Realdruck-Beobachtung)

**Frage:** Am Druckort ragt der Druck (Strang/Druckstand/TCP-Marker) sichtbar zum Roboter hin aus
dem blauen Soll-Kasten heraus — welcher von beiden steht falsch, und warum?

**Befund:** Der Druck steht richtig, der Kasten falsch. `moduleBoxSpec`
(`viewer/src/render/druckort-spec.ts`) zeichnete die Modul-Box mit der Konvention „Modulfront bei
y = 0, Körper dahinter (y ∈ [−Dicke, 0])" — übernommen aus der (ebenfalls irrigen) Docstring-Erzählung
von `fgc.decompose.module_pose` und `fgc.placement` („Abstand der Basis vor der Wandfront"). Das
tatsächliche Modul-System der Core-Lage ist aber das **PCA-zentrierte Wandsystem** der Simulation
(`_wall_local_basis`: xy um den Schwerpunkt zentriert): Toolpath, Trajektorie und Kollisionsbefund
liegen bei **y ∈ [−Dicke/2, +Dicke/2]**. Empirisch am Denkmal-Modul verifiziert
(`runs/20260709-204347_slice_Denkmal/toolpath.json`: Targets y −240…+240 bei 480 mm Wanddicke).
Der Kasten stand damit eine halbe Wanddicke zu weit von der Roboterbasis, der Druck „außerhalb".

**Alternativen:** (a) Box auf die echte Konvention legen (y-zentriert), (b) Toolpath/Trajektorie auf
„Front bei 0" umziehen (Front-Semantik erzwingen), (c) nur dokumentieren.

**Entscheidung:** (a) — `centerLocalMm[1] = 0`; die Trajektorie ist die physikalische Wahrheit
(sie fährt der Roboter, gegen sie rechnet `fgc.collision.check`), die Anzeige folgt ihr (ADR-007).
(b) hätte alle bestehenden Läufe, Golden-Files und den DRL-Export verschoben — für einen reinen
Anzeigefehler. Die irrigen Docstrings in `module_pose.py` sind textlich korrigiert (Mathematik
unverändert; der Roundtrip kürzt die Frames, ihm war die Erzählung egal).

**Folgefrage (offen, needs-triage-Issue):** Der Platzierungs-„Abstand" (`standoff_mm`) misst damit
faktisch Basis → Modul-**Mittelebene**, nicht → nächstliegende Modulfläche; die reale Freidistanz
ist `Abstand − Dicke/2`, und `placement.evaluate` sampelt seine Erreichbarkeits-Ziele auf der
Mittelebene (y = 0), nicht über die Dickenausdehnung. Ob „Abstand" semantisch auf die Modulfront
umgestellt werden soll (Domänenfrage: was misst der Aufsteller am Tisch?), entscheidet Tobias —
eine Umstellung verschöbe alle Trajektorien und gehört nicht in einen Anzeige-Bugfix.

**Verifikation:** Viewer `npx tsc --noEmit` clean, `npx vitest run` grün (druckort-spec-Tests auf
die zentrierte Konvention nachgezogen).

## 2026-07-09 — Kollisionsprüfung zweigeteilt: schneller Befund vs. teure Optionssuche (Prüf-UX, Karte #139 / #145 / #150)

**Frage:** Die Kollisionsprüfung im Viewer „dauert ewig und wird global berechnet" (Realdruck-
Beobachtung, deckungsgleich mit den offenen > 3 min aus Karte #139/#150). Woher kommt die Zeit
wirklich, und was ist die ehrliche Bedienung?

**Befund (beantwortet die in S5 offene > 3-min-Frage):** Der Knopf „Kollision prüfen" war der
**Kollisions-Advisor** (#130): Basis-Befund + ~17 Hebel-Kandidaten, je Kandidat eine **volle
Neu-Simulation** (Slice + Trajektorie + `find_collisions`, ~19 s end-to-end nach S5) ⇒ **~6 min**
je Klick — ohne Ankündigung, ohne Fortschritt. Dazu log der statische Kopf-Hinweis „global":
geprüft wurde schon immer der fokussierte (sonst der erste) Abschnitt (`currentFocusedSection`
→ `advise_collision`). Obendrein lief der **loop-invariante Unterbau je Kandidat neu**: IFC-Wand
laden, Zerlegung (`apply` schneidet die ganze Wand in alle Teile), Verschiebung, Basis-Parameter.

**Alternativen:** (a) Advisor unverändert lassen, nur Warntext; (b) `find_collisions` beschleunigen
(Travel-Ausdünnung/`set_transform`) — das ist die #144-Strategieentscheidung, noch ungegrillt;
(c) Bedienung zweiteilen (schneller Nur-Befund vs. bewusste Optionssuche) + loop-invariante Arbeit
hoisten; (d) Hintergrundlauf mit Fortschritt + Abbruch (#145 voll).

**Entscheidung:** (c) — additiv und ohne Vorgriff auf #144: `advise_collision(include_options=False)`
liefert nur den Basis-Befund (genau EINE Neu-Simulation, ≈ 20 s; gleiche Metrik, read-only);
Route/Request additiv (`include_options`, Default true). Neuer `_SectionSimContext` bündelt den
loop-invarianten Unterbau (Plan, IFC-Mesh, Teile, frühere Teile, Basis-SliceParams, Kinematik) und
wird EINMAL je Beratung gebaut; IK-/Platzierungs-Kandidaten teilen zusätzlich den geslicten Toolpath
(Cache je (lead, kipp) — nur die Orientierung formt den Toolpath). Viewer: zwei Knöpfe
(„Kollision prüfen (≈ 20 s)" / „Hebel-Optionen suchen (Minuten)"), dynamischer Scope-Chip
(Fokus-Teil statt Festtext „global"), Statuszeile nennt Teil + erwartete Dauer, leere Optionsliste
nach Nur-Befund sagt „nicht gesucht" statt fälschlich „kein Hebel". (d) bleibt als #145 offen
(Hintergrundlauf, Fortschritt, Abbruch); (b) bleibt #144.

**Begründung:** Der Nutzer wollte eine Antwort auf „kollidiert es?" — die kostet eine Simulation,
nicht achtzehn. Die teure Menü-Suche bleibt wertvoll, aber als bewusster, benannter Schritt.
Das Hoisting ändert keine Semantik (dieselben Eingaben je Kandidat, Determinismus-Test grün),
es entfernt nur pro Kandidat wiederholte identische Arbeit.

**Verifikation:** Core: `test_collision_advisor_action.py` grün inkl. neuem slow-Test
(Nur-Befund = genau 1 Aufruf der Kern-Tür) und bestehendem Determinismus-/e2e-Test über die echte
Re-Simulation (373 s — bestätigt nebenbei die gemessene Menü-Dauer); volle Suite + ruff s. Commit.
Viewer: 847 vitest grün (+11: Scope/Status/Leer-Text, Struktur), tsc clean; `ui_smoke.mjs`
Kontrakt-Schritt auf zwei Knöpfe + Scope-Chip erweitert.

## 2026-07-10 — Druckort-Bühne folgt dem Simulationslauf statt dem Zerlegungslauf (Issue #161)

**Frage:** Nach dem Annehmen einer Placement-Hebel-Option des Kollisions-Advisors
(Abstand/Aufstellhöhe, #130) und anschließender Neu-Simulation liegen am Druckort Soll-Kasten,
Stranglinien und TCP-Marker sichtbar neben der Armposition, und die Modul-Karte behauptet weiter
die alte Platzierung — warum, und welche Quelle soll gelten?

**Befund:** Zwei unabhängig alternde Platzierungsquellen. Die Bühne (`moduleGroup` — Soll-Kasten,
Strang, TCP-Marker, Druckstand) las `section.module_pose.workstation` aus dem **Zerlegungslauf**
(nur `propose_decomposition` schreibt sie), der Arm folgte den Gelenken des **Trajektorienlaufs**,
dessen `meta.base_frame` (= base_in_wall, #66) die Platzierung *dieses* Sim-Laufs trägt. Ein
placement-override bumpt nur den Pro-Abschnitts-Zähler; nach „Anwenden" stößt der Viewer weder
Neuzerlegung noch Sections-Nachladen an. Geometrisch: Arm-TCP(Welt) = robot_base_frame ∘
invert(base_frame_sim) ∘ toolpath, Bühne(Welt) = robot_base_frame ∘ invert(platzierung_zerlegung)
∘ toolpath — deckungsgleich nur bei gleicher Platzierung. Nebenbefund: der placement-Zweig von
`collisionAdvisorPanel.onApply` zog — anders als der Singularitäts-Advisor — Platzierungsfelder +
▪-Marker nicht nach.

**Alternativen:** (a) Bühne folgt dem Sim-Lauf (`meta.base_frame` als Transform-Quelle);
(b) nach „Anwenden" automatisch neu zerlegen (`propose_decomposition` anstoßen) — teuer, macht
das Abspielen zur Schreibaktion, löst das Grundproblem (zwei Quellen) nicht; (c) nur dokumentieren.

**Entscheidung:** (a), in drei Teilen, NUR Viewer: (1) **Kernfix** — `runModuleFrame(robot_base_frame,
base_frame) = T_ws←basis ∘ T_modul←basis⁻¹` als reine Funktion in `render/druckort-spec.ts`
(dieselbe Invertierung der Leserichtung wie `fgc.decompose.module_pose`, ADR-022, nur mit der
Platzierung des Sim-Laufs); `druckortSceneSpec` bekommt den optionalen `runBaseFrame`,
`moduleSceneSpecFor` reicht ihn beim Lauf-Laden durch — je Modul aus dessen EIGENEM Lauf, auch bei
„Alle Module". Ohne Lauf bzw. Altlauf ohne das Feld bleibt die Zerlegungs-Lage (Befund, kein Gate,
kein Crash — ADR-013-Geist); der Frame steckt im per-Step-Spec, das der Modulwechsel ohnehin neu
baut (kein veralteter Frame, BuildSeq-Guard unberührt). (2) **Anwenden-Parität** — der
placement-Zweig von `collisionAdvisorPanel.onApply` zieht `placementOverridePanel.restoreFromJob` +
`updatePartsOverrideMarkers` nach (exakt wie der Singularitäts-Advisor #65/#134). (3) **Ehrliche
Modul-Karte** — `placementDisplayValues` (rein, `parts-palette-state.ts`) ersetzt in der
Karten-Zeile „Platzierung: …" sparse die Zerlegungs-Werte durch gesetzte Override-Felder des
aktiven Jobs (Quelle `currentActiveJob.section_overrides` über `updatePartsOverrideMarkers` —
derselbe Weg wie die ▪-Marker); reine option_id-Referenzen ändern nichts (ihre Werte kennt nur
der Core, ADR-007), nicht-endliche Werte übersteuern nie.

**Begründung:** Die Trajektorie ist die physikalische Wahrheit (Lehre aus dem
Soll-Kasten-Bugfix 2026-07-09): der Arm fährt sie, der Kollisionsbefund rechnet gegen sie — die
Bühne hat ihr zu folgen, nicht einem älteren Plan-Artefakt. Box, Strang, TCP-Marker und Druckstand
hängen alle unter der `moduleGroup`: EIN Transform, EINE Quelle mit dem Arm. Das Wand-Replay bleibt
bit-identisch (eigener Pfad, `computeArmPose` unberührt); alle neuen Signaturen sind optional-additiv.

**Verifikation:** Viewer `npx tsc --noEmit` clean, `npx vitest run` **859 grün** (847 Bestand + 12
neu: `runModuleFrame`-Algebra inkl. Orakel (A∘B⁻¹)(B(p)) = A(p), `druckortSceneSpec` mit/ohne
`runBaseFrame` + fehlender `module_pose`, `placementDisplayValues` sparse/option_id/NaN +
`paletteEntries`-Durchgriff). Kein bestehender Test angefasst (Beleg „Bestand unverändert").

## 2026-07-10 — Review-Nacharbeit #161: eine Frame-Algebra, getestete Verdrahtung, getesteter Anwenden-Fluss

**Frage:** Das Review der #161-Änderungen bestätigte drei Befunde: (1) `runModuleFrame` führte
**private `quatMul`/`quatRotate`-Kopien** in `render/druckort-spec.ts` ein, obwohl
`ui/face-align.ts` identische Helfer ([w,x,y,z], gleiche Formeln) exportiert — eine fünfte
Quaternion-Dialekt-Kopie, die die protokollierte #123-Konsolidierung („eine Frame-Algebra …
4 Dialekte → 1") übersehen würde; die Duplikat-Entscheidung war zudem nicht im Design-Log.
(2) Die Durchreichung `run.trajectory.meta.base_frame` → `moduleSceneSpecFor` (der Kernfix)
war **ungetestete Glue** in `main.ts` mit Default-Parameter `= null` — ein Refactoring auf
`moduleSceneSpecFor(section)` bliebe tsc-clean und vitest-grün, das Original-Symptom käme
unbemerkt zurück. (3) Die **Anwenden-Parität** des Kollisions-Advisors
(`restoreFromJob` + `updatePartsOverrideMarkers` nach angewandter Placement-Option) existierte
nur als ungetestete, aus dem Singularitäts-Advisor kopierte Zeilen.

**Alternativen:** Zu (1): Kopien behalten und nur im Log dokumentieren; auf das geplante
`render/frames.ts` (#123) warten. Zu (2): nur den Default-Parameter entfernen (tsc-Schutz ohne
Test); einen Wrapper-Test gegen `main.ts` schreiben (dort nicht testbar, DOM/three.js). Zu (3):
Copy-Paste belassen und per Kommentar koppeln.

**Entscheidung:** (1) **Reuse statt Kopie:** `druckort-spec.ts` importiert `quatMul`/`quatRotate`
(+ `Quat`/`Vec3`) aus `ui/face-align.ts` — der Import render → ui ist Hausmuster
(`prepare-preview.ts`); wenn #123 die Algebra nach `render/frames.ts` zieht, wandert genau EINE
Quelle mit. (2) **Verdrahtung wird reine Funktion:** neues `druckortSceneSpecForRun` in
`druckort-spec.ts` nimmt den **geladenen Lauf** (strukturell `DruckortRunLike`, nur
`trajectory.meta.base_frame`) und zieht den Frame SELBST heraus; `moduleSceneSpecFor` in
`main.ts` verlangt den Lauf als **Pflicht-Argument** (kein Default mehr) und reicht ihn durch —
„Frame vergessen" ist jetzt ein tsc-Fehler, „falsch extrahiert" ein roter vitest
(3 neue Tests: Lauf-Frame gewinnt über `module_pose`, Altlauf ohne Feld → Zerlegungs-Lage,
kein Lauf/keine Trajektorie → kein Crash). (3) **Anwenden-Fluss wird Modul:** neues
`ui/placement-apply.ts` mit `applyPlacementOverride(ports, sectionId, values)` — die Sequenz
PUT → Job übernehmen (`adoptActiveJob` MUSS vor den Markern liegen, `updatePartsOverrideMarkers`
liest den aktiven Job) → Platzierungsfelder → ▪-Marker/Karten-Zeile → Veraltet-Badges ist
getesteter Vertrag (3 Tests: Reihenfolge + frischer Job, unbekannte job_id ohne Wurf,
PUT-Fehler ohne UI-Wirkung); BEIDE Advisors (Singularität #65/#134, Kollision #130) rufen
dieselbe Funktion über dieselben `placementApplyPorts` — Parität per Konstruktion statt
per Copy-Paste.

**Begründung:** Modularität vor allem: die Dialekt-Kopie war genau die Sorte stiller Divergenz,
die #123 abschaffen will (eine spätere Korrektur an einer Kopie erreicht die andere nicht —
Bühne und Konfigurator rechnen dann verschieden). Glue, die einen Regressionsfall des Issues
trägt, gehört in eine reine, getestete Funktion (Hausmuster `parts-palette-state.ts`) — der
Test beweist dann das Verhalten, nicht nur die Existenz der Zeilen.

**Verifikation:** Viewer `npx tsc --noEmit` clean, `npx vitest run` **865 grün** (859 + 6 neu:
3× `druckortSceneSpecForRun`, 3× `applyPlacementOverride`). Bestehende `runModuleFrame`-Tests
(inkl. Algebra-Orakel) unverändert grün — Beleg, dass der Helfer-Tausch bit-gleich rechnet.

## 2026-07-10 — Kollisions-Constraint in der Zerlegung: zweistufig, IK+Platzierung automatisch, Kipp nie (Grilling #141)

**Frage:** Wie wird `propose_decomposition` kollisionsgetrieben (Karte #139, Ast 1)? Realbefund:
die Zerlegung schneidet rein nach Reichweite („16/16 ✓, erreichbar 100 %"), real kollidieren
alle 16 Denkmal-Module (−206…−436 mm, S6) — wo greift der Constraint, welche Hebel in welcher
Reihenfolge, was passiert im Abbruchfall, welches Kostenbudget?

**Alternativen:** (a) Grob-Check `path_collides` ertüchtigen — von #140/S6 disqualifiziert
(Fehlerbias Richtung „frei": Handgelenk = 39,4 % der Verursacher strukturell ausgeschlossen,
plus Rastergröbe). (b) Nur prüfen + melden, ohne Schnittänderung. (c) Strangreihenfolge je
Schicht fern→nah — der Arm schwebte dann über noch ungedrucktem Material derselben Schicht;
als billigster Ausweg geprüft, **Domänen-Urteil Tobias: prozessbedingt nicht frei wählbar,
verworfen**. (d) Kipp als automatischer Hebel. (e) Hartes Gate im Abbruchfall.

**Entscheidung (HITL Tobias, Resolution-Kommentar in #141):** **Zweistufig.** Stufe 1:
analytisches **Freigang-Kriterium** je Wand (druckbare Tiefe von einer Seite aus Wanddicke +
Endeffektor-Geometrie + Handgelenk-Radius) — stellt **ausschließlich Unmöglichkeit** fest, nie
Freiheit (die Fehlerrichtung billiger Checks muss die sichere sein); „Wand zu dick" wird sofort
und gratis erkannt. Stufe 2: **verdünnte `find_collisions`-Instanz** (Empfehlung B aus #140;
Travel-Ausdünnung nach S5) als zweites Verfeinerungskriterium neben der Reichweite — eine Zelle
gilt erst als gut, wenn sie von der besten Option aus frei ist; verfeinert wird entlang der
verursachenden Achse (`causer_link` + Eindringrichtung), nicht per Heuristik. Hebel je Zelle
vor dem Kleinerschneiden: **IK-Konfiguration** (prozessneutral — Düse, Bahn, Druckergebnis
identisch) + **Platzierung** (Abstand/Aufstellhöhe/seitlich) automatisch; danach Bandhöhe
senken, dann Breite teilen. **Kipp ist ganz raus aus der Automatik** (neigt die Düse, greift in
den Prozess ein) — bleibt ausschließlich manueller Advisor-Hebel. **Tiefenteilung wird nie
automatisch angewandt** (Karte #139), darf aber als konkreter **Vorschlag** benannt werden
(Anwendung manuell über das #142-Bedienbild). **Abbruchfall: Befund, kein Gate — aber nie ohne
Ausweg:** der Lauf nennt immer mindestens einen nachprüfbar freien 100-%-Vorschlag (kleinere
Teile + IK/Platzierung, sonst Tiefenteilungs-Vorschlag); existiert keiner, ehrlicher Befund
„keine einfahrbare Zerlegung" mit Hebeln. Kostenbudget: Stufe 1 gratis; Stufe 2 repräsentativ
(ungünstigste Zelle je Reihe, Prüfung an den Verfeinerungsschritten), Ziel ~1–2 min je Lauf;
`_SectionSimContext` wird wiederverwendet. Serie: **#162** (Prüf-Tür) → **#163**
(Freigang-Kriterium, unabhängig) → **#164** (Druckbarkeit als Lauf-Eigenschaft, erster
Durchstich) → **#165** (Verfeinerung; Scope-Schärfung: synchron, kein Ad-hoc-Job-Framework bis
#145) → **#166** (100-%-Vorschlag; Tiefenteilungs-Übernahme wartet auf #142).

**Begründung:** Erreichbarkeit ist notwendig, aber nicht hinreichend — die Düse kommt an jeden
Bahnpunkt, während Ellbogen/Handgelenk durch frisches Material fahren; das darf kein grünes
Häkchen erzeugen. Die Fehlerrichtungs-Asymmetrie ordnet die Stufen: Billiges darf nur verwerfen
(Stufe 1), Freiheit bescheinigt nur der echte Befund (Stufe 2). IK vor Kipp, weil IK das
Druckergebnis nicht ändert; „immer ein Ausweg", weil ein roter Befund ohne Handlungsoption den
Nutzer alleinlässt (ADR-013-Geist: Befund statt Gate, aber ehrlich UND hilfreich).

## 2026-07-10 — Umsetzung #162: Prüf-Tür der Zerlegung — verdünnte `find_collisions`-Instanz je Teil

**Frage:** Wie bekommt die kollisionsgetriebene Zerlegung (#141, Stufe 2) einen
wiederverwendbaren, **treuen** Prüf-Baustein „kollidiert dieses Teil + Option?", der in
wenigen Sekunden urteilt statt ~11,5 s (S5)? Verlangt: dasselbe rot/frei-Urteil wie der volle
Befund (kein struktureller Blindfleck), kein Lauf-Artefakt, `_SectionSimContext`-Reuse.

**Alternativen:** (a) Grob-Check `path_collides` — von S6/#140 disqualifiziert (Handgelenk =
39,4 % der Verursacher strukturell ausgeschlossen, Fehlerbias „frei"); verworfen als Urteil.
(b) `set_transform`/VHACD verschlanken (S5-Hebel #1, ~53 % der Zeit) — der stärkste Hebel, aber
Formtreue-Trigger (ADR-024/S0) und Strategie-Frage von **#144**; hier bewusst nicht. (c)
Distanz-nur-bis-Schwelle (S5-H1) — klein (0,5–1,9 s), berührt den `find_collisions`-Innenloop;
als optional markiert, hier weggelassen. (d) **Travel-Ausdünnung (S5-H2)** — der sichere,
hypothesengetriebene Hebel (~36 % der Zeit in 30,6 % Samples), Travel ist ohnehin „nicht
lückenlos geprüft" (ADR-024). (e) Print-Samples mit ausdünnen — verworfen: dort passiert die
Kollision, Ausdünnen dürfte das Urteil kippen (Fehlerrichtung „frei").

**Entscheidung:** Neue **reine Core-Tür** `fgc.collision.finding.check_part_clearance` +
`ClearanceVerdict` (`collides`, `min_distance_mm`, `penetration_mm` = Eindringtiefe,
`causer_link` = Eindringrichtung, `n_red/n_checked/n_samples`). Sie ist **derselbe**
`find_collisions` wie der volle Befund (kein Blindfleck: alle Glieder inkl.
Handgelenk/Endeffektor urteilen mit) — nur mit **Travel-ausgedünnten** Samples: alle
Druck-Samples + jedes `travel_stride`-te Travel-Sample (`DEFAULT_TRAVEL_STRIDE = 5`, S5), je
Travel-Lauf inkl. Anfang **und** Ende (Übergang Druck↔Travel bleibt geprüft). Der
Aufbau-Unterbau (Geo/FK/Druckstand/TCP) wurde aus `build_section_finding` in `_prepare_finding`
extrahiert — **eine** Quelle, beide Türen (voll vs. verdünnt) teilen ihn; `build_section_finding`
bleibt byte-identisch (Bestandstests unverändert grün). Actions-Tie-in `check_section_clearance`
(kein Lauf, kein Mutieren) slict+simuliert **ein** Teil + `Override` (Platzierung/IK) über die
geteilte Kern-Tür und reicht einen vorgebauten `_SectionSimContext` durch — für den
Verfeinerungs-Loop (#165) baut der Unterbau **einmal**, viele Optionen teilen ihn.

**Messung (16 Denkmal-Module, `test_prueftuer_denkmal.py`, `slow`, stride=5):** Orakel grün —
**16/16 identisches kollidiert-Urteil** wie der volle Befund (alle Module real rot, S6-Datenbasis
bestätigt; `n_red` Tür ≤ voll, weil ausgedünnt, Urteil unverändert). Prüf-Tür-Zeit je Modul
(reine `find_collisions`, ohne Slice/Sim): **min 7,0 s / Median 9,6 s / max 16,2 s** gegen voll
**9,5–18,2 s** — ~15–26 % schneller, deckungsgleich mit der S5-Schätzung (~11,5 s → ~8,7 s). Die
großen, druck-dichten Module (15 k+ rote Print-Samples) bleiben ~14–16 s: der **Print-Boden**
dominiert, und den senkt nur der `set_transform`/VHACD-Hebel — genau die **Naht zu #144**, die
das Issue benennt („hier nur die sicheren S5-Hebel").

**Begründung:** Die Fehlerrichtung muss „kollidiert" sein, nicht „frei" (#141) — deshalb der
echte VHACD-Befund (kein Grob-Ersatz) und deshalb nur Travel (schon als lückenhaft deklariert)
ausgedünnt, Print voll. Eine Quelle für den Aufbau (`_prepare_finding`) hält voll und verdünnt
deckungsgleich (keine Parallel-Metrik, ADR-024-Geist). Reine Core-Funktion ohne
Benutzeroberfläche ⇒ kein README-Abschnitt (Konsument ist die Zerlegung, #164/#165). Tests: 7
schnelle Einheitstests (Travel-Flags/Ausdünnung/Urteil-Parität) + 3 `slow` (16-Modul-Orakel,
Actions-Verdikt, ctx-Reuse); Bestands-Kollisionssuite unverändert grün, ruff clean.

## 2026-07-10 — Umsetzung #163: Freigang-Kriterium — Befund „Wand zu dick für einseitigen Druck"

**Frage:** Wie bekommt die kollisionsgetriebene Zerlegung (#141, **Stufe 1**) ein **billiges,
analytisches** Kriterium, das „Wand zu dick für einseitigen Druck" **sofort und gratis** erkennt
und damit die teure verdünnte Kollisionssuche (Scheibe 2, #162) in dem klaren Fall erspart —
aus Wanddicke, freier Länge unter dem Handgelenk und Handgelenk-/Unterarm-Radius? Kern-Auflage
(#141/S6): das Kriterium darf **nur** Unmöglichkeit feststellen, **nie** Freiheit; die
Fehlerrichtung muss die sichere sein („unmöglich" nur, wenn sicher).

**Geometriemodell (und seine Vereinfachungen).** Die Düse druckt senkrecht (nozzle-down) von
**einer** Seite; unter dem Handgelenk hängt eine **schlanke Säule** der freien Länge `L`
(Flansch `d6` + Werkzeug-Überstand), darüber sitzt das bauchige **Handgelenk/der Unterarm** als
Zylinder mit Radius `R`. Der Arm greift über die obere Nahkante des bereits gedruckten
Wandmaterials; das Handgelenk darf diese Kante gerade streifen (Mittelpunkt dann `R` hinter der
Kante), die schlanke Säule reicht `L` tiefer. Der **tiefste** von einer Seite erreichbare
Druckpunkt liegt damit **höchstens** bei `D = L + R` von der Nahfläche. Ist die Wanddicke strikt
`> D`, ist die Wand sicher zu dick für einseitigen Druck. **Vereinfachungen, bewusst und
dokumentiert:** (1) Das Modell **ignoriert die Armglieder** (Ober-/Unterarm, Ellbogen — Glied
1–3), deren tiefes Eintauchen der **volle** `find_collisions`-Befund fängt (S6: link2 46 %,
link4 39 % der Verursacher); es **unter-erkennt** Unmöglichkeit (sichere Richtung), statt sie
über-zu-behaupten. (2) Senkrechte Düse (kein Kipp). (3) Handgelenk/Unterarm als Rotationskörper
eines Radius. (4) Flansch+Werkzeug als schlanke Säule. (5) Gerader Übergriff, kein Bezug zur
Wandhöhe. (6) `D = L + R` ist eine **großzügige Obergrenze** der real druckbaren Tiefe: `L`
selbst ist per Dreiecksungleichung eine Obergrenze (`d6 + ‖tcp_pos‖ ≥` echte Strecke J5→Spitze),
und der Radius wird `L` **hinzugerechnet** statt abgezogen. Damit ist ein **falsches
„unmöglich" ausgeschlossen**, solange `L`/`R` nach oben geschätzt sind — genau die S6-Fehler­
richtung. `R` ist ein **provisorischer** Modul-Default (`DEFAULT_WRIST_RADIUS_MM = 60 mm`, grob
aus der M1013-Kollisionshülle der Glieder 4/5, großzügig nach oben); der Revisionstrigger ist
eine gemessene bzw. per-Roboter aus der Geometrie abgeleitete Zahl (die reine Funktion nimmt `R`
als Parameter — der Austausch ist ein Einzeiler).

**Alternativen:** (a) Die Armglieder mitmodellieren (Ellbogen-Sweep analytisch) — verworfen: das
hängt an der vollen Kinematik + Platzierung, ist genau **Stufe 2** (verdünnter `find_collisions`,
#162); ein analytischer Nachbau hätte denselben nicht-quantifizierbaren Rest-Fehler wie der von
S6 disqualifizierte Grob-Check. (b) `D` als *bester* (nicht großzügiger) Schätzwert — verworfen:
kippte die Fehlerrichtung Richtung „unmöglich" (Fehlalarm bei druckbaren Wänden). (c) `R` als
neues Roboter-Schemafeld — aufgeschoben (Scope): der provisorische Modul-Default reicht v1, die
reine Funktion hält `R` bereits als Parameter offen. (d) Den Befund je Teil statt wand-weit —
verworfen: die Dicke ist eine **Wand**-Eigenschaft (bei Längs-/Höhenteilung unverändert; die
Tiefenteilung #142, die sie senken würde, ist noch nicht implementiert), also **ein** Top-Level-
Block `freigang` im Zerlegungslauf (parallel zu `module_limits`).

**Denkmal-Fall gegen den vollen Befund (Protokoll-Bewertung, Akzeptanz).** Referenz-Endeffektor
`30gut` (TCP `[134,0,73]` ⇒ `‖tcp‖ = 152,6`) am M1013 (Flansch `d6 = 121`): `L = 273,6`,
`R = 60` ⇒ **druckbare Tiefe `D ≈ 333,6 mm`**. Denkmal-Wand **480 mm** ⇒ `too_thick`, Überschuss
**146 mm**; das Denkmal-**Modul** (510 mm, S6) ⇒ Überschuss **176 mm**. Der **volle** Befund
zeigt für alle 16 Denkmal-Module real Eindringungen **−206 … −436 mm** (S6). Beide zeigen
dasselbe Vorzeichen „zu dick" — das analytische Kriterium erspart in diesem Fall die teure Suche.
Die Zahlen messen **verschiedene** Größen und sind **nicht** eins-zu-eins vergleichbar: der
Freigang-Überschuss (146–176 mm) ist die überschüssige **Dicke** entlang der Wandquerachse; die
−206…−436 mm sind die **Eindring­tiefe des Arms** (v. a. Ober-/Unterarm) in den wachsenden
Druckstand — größer, weil sie den ganzen Arm-Sweep enthalten, den das Kriterium bewusst
ausklammert. Der **Gegenprobe-Fall** (Akzeptanz „kein falsches unmöglich"): eine 200-mm-Wall mit
demselben Endeffektor ⇒ `200 < 333,6` ⇒ **kein Befund** (druckbar), verifiziert per Unit- **und**
API-Test.

**Entscheidung/Umsetzung:** Neues reines, tiefes Modul `fgc.decompose.freigang`
(`check_freigang` + `FreigangCheck` + `printable_depth_mm` + `free_length_under_wrist_mm`,
Muster `fgc.decompose.limits`); `too_thick` strikt `>` (exakt auf `D` = druckbar). Additiv im
Zerlegungslauf: Top-Level-Block `freigang` (Schema erweitert, `additionalProperties:false` hält
— Altläufe ohne Feld byte-gleich gültig), gebaut in `decompose_artifact`, gerechnet in
`propose_decomposition` über den fail-soften Helfer `_freigang_finding` (kein Endeffektor / keine
Kinematik / keine Dicke ⇒ `None`, nie ein geratenes „zu dick"). API-Antwort +Feld `freigang`;
Viewer: reine `ui/freigang-state.ts` (`freigangNotice`/`freigangBannerView`) formatiert den
verbatim Core-Befund in ein amber Banner am Fuß des Zerlegungs-Inspectors (`#decompose-freigang`,
`.hint.warn`), gespeist aus Decompose/Prüfen/Stand-Mode-Antwort **und** aus dem wiederhergestellten
Lauf (`setFreigang`, überlebt Neuladen). **Befund, kein Gate** (ADR-013): blockiert nie.

**Begründung:** Erreichbarkeit ist notwendig, nicht hinreichend (#141); ein billiges Kriterium mit
Fehlerbias Richtung „frei" wäre die falsche Richtung (S6) — deshalb `D` als Obergrenze und der
Verzicht auf jede „druckbar"-Zusage. Wand-weit statt je Teil, weil die Dicke eine Wand-Eigenschaft
ist. Reine Domänen-Funktion (Parameter `L`/`R`) hält das provisorische `R` austauschbar. **Tests:**
23 pytest (reine Formel, Grenzfall, „kein falsches unmöglich" parametrisiert, freie-Länge-
Obergrenze, Denkmal-Referenz, Serialisierung/Schema, Actions-fail-soft) + 1 API-Integrationstest
(#freigang reist end-to-end) + 7 vitest (`freigang-state`) — **alle schnell, keine `slow`**;
Denkmal↔Vollbefund-Abgleich ist die obige **Protokoll**-Bewertung, **kein** Live-Test (der volle
Befund läuft nicht in dieser Suite). Viewer tsc + build + 872 vitest grün, ruff clean.

## 2026-07-10 — Umsetzung #164: Druckbarkeit wird sichtbare Lauf-Eigenschaft der Zerlegung

**Frage:** Wie wird **Druckbarkeit** eine je Teil sichtbare **Lauf-Eigenschaft** der Zerlegung —
sodass das lügende „16/16 ✓ / erreichbar 100 %" bei real kollidierenden Modulen (Denkmal,
Realbefund 2026-07-09/10) fällt —, indem `propose_decomposition` die final geschnittenen Teile mit
dem Freigang-Kriterium (#163) **und** der Prüf-Tür (#162) prüft und je Teil druckbar/kollidiert +
Ursache **additiv** in den Lauf schreibt (Scheibe 3 der Constraint-Serie, Karte #139 / #141)? Und
das **im Kostenrahmen** (Prüf-Tür ~10 s/Teil, 16 Module voll = ~2,7 min)?

**Zweistufig, Fehlerrichtung stets „kollidiert" (S6/#141).** Neues reines, tiefes Modul
`fgc.decompose.printability` (`PartPrintability`, `representative_by_row`, `combine_printability`)
verheiratet die beiden Kriterien der Serie zu **einem** Urteil je Teil: **Stufe 1 (gratis):** ist
die Wand nach dem Freigang-Kriterium sicher zu dick, trägt **jedes** Teil `too_thick` (wand-weit,
nie „vermutlich") mit dem Dicken-Überschuss als Ursache — die **teure Prüf-Tür entfällt** (genau der
klare Fall, für den #163 gebaut wurde: „erspart die teure Suche"). **Stufe 2 (teuer, nur sonst):**
die verdünnte Prüf-Tür (#162) urteilt, aber **repräsentativ** — je **Höhenreihe** nur die
ungünstigste Zelle; die übrigen Zellen **erben** das Urteil, ehrlich als `presumed` gekennzeichnet.
Der `_SectionSimContext`-Reuse aus #162 wird je Repräsentant genutzt (`_clearance_verdict_for_section`
/ `_decompose_printability` in `actions.py`).

**Wahl der „ungünstigsten Zelle je Reihe" (Kostenrahmen, begründet).** Eine **Reihe** ist ein
Höhenband `(z0, z1)` — die Höhe ist der dominante Kollisionstreiber (höhere Reihe = mehr Druckstand
darunter); innerhalb der Reihe unterscheiden sich die Zellen nur seitlich und verhalten sich
ähnlich. Geprüft wird die **collision-anfälligste** Zelle, damit ein „frei"-Urteil die ganze Reihe
in der **sicheren** Richtung deckt (kein Falsch-„frei", S6/#141). Proxy aus der **bereits
gerechneten Ampel** (gratis, `_worst_key`): kleinste kinematische Marge (extremste, am tiefsten
eintauchende Pose; fehlende Marge = am ungünstigsten) → kleinster erreichbarer Anteil → größte
Grundfläche (mehr Druck-Samples = mehr Kollisionsgelegenheiten) → Reihenfolge (deterministischer
Stich). Bei den Denkmal-Modulen ist die Ampel flach (alle Margen ≈ 0,06) → der Stich fällt
deterministisch auf die erste Zelle der Reihe; das ist unkritisch, weil dort ohnehin Stufe 1 greift.

**Ehrlichkeit der Anzeige ist der Kern (#164).** Zwei Auflagen, im Core **und** Viewer festgenagelt:
(1) **Grün nur aus der Prüf-Tür.** `verdict == "printable"` wird **ausschließlich** gesetzt, wenn die
Prüf-Tür ein Teil (bzw. seinen Repräsentanten) frei gesehen hat. Ein **stummer** Freigang-Befund
(nicht zu dick) bescheinigt **nie** Druckbarkeit — er lässt das Urteil `unknown` (nie grün). `too_thick`
ist rot, nicht grün. (2) **„vermutlich" ≠ geprüft.** Ein geerbtes Reihen-Urteil trägt `presumed=True`
und zeigt sich als **hohler, blasser** Ampelpunkt + kursives „vermutlich …"-Badge — es darf nicht wie
ein geprüftes aussehen. Der Palette-Zähler (`printabilityCounter`) zählt nur **geprüft-frei** als ✓
(„16/16 nicht druckbar" statt „16/16 ✓"); die per-Teil-Ampel spiegelt seit #164 die **Druckbarkeit**,
fällt aber bei fehlendem Urteil (Altlauf) auf die Erreichbarkeit zurück (kein Crash, Befund kein Gate).

**Alternativen.** (a) **Freigang NICHT short-circuiten, die Prüf-Tür auch bei „zu dick" laufen lassen**
(um für Denkmal die Verursacher-Glied-Ursache zu erhalten) — verworfen: das bräche die **dokumentierte
#163-Zusage** („erspart die teure Suche im klaren Fall") und kostete ~40–70 s je „Prüfen" ohne
Erkenntnisgewinn (die Wand ist schon sicher unmöglich). Die Freigang-Ursache „zu dick, Überschuss X mm"
ist die **Wurzelursache** und benennt konkretere Hebel als „Glied 2 taucht 289 mm ein". Stufe 2 bleibt
gebaut, getestet und greift für freigang-stille Wände. (b) **Alle Zellen voll prüfen** — der
Kostenrahmen (2,7 min) verbietet es. (c) **Kombiniertes Urteil erst im Viewer** — verworfen: die
Ehrlichkeitsregeln (grün nur aus Prüf-Tür) gehören in den Core (ADR-007), nicht doppelt in TS.
(d) **Ampel-Bedeutung unverändert lassen (Erreichbarkeit) + separates Badge** — verworfen: dann bliebe
der Ampelpunkt grün, während das Teil kollidiert; das Issue verlangt, dass die **Ampel** die
Druckbarkeit zeigt.

**Additiv, fail-soft (ADR-013).** Neues per-Teil-Feld `sections[].printability` im
`decompose.schema.json`; **nur echte Urteile** werden geschrieben (`unknown` weggelassen) → Altläufe
ohne das Feld bleiben byte-gleich gültig. Jeder Fehler der Prüf-Tür (kein Modell, keine Kollisions-
Geometrie, leeres Teil) wird zu `None`/`unknown` und kippt den Zerlegungslauf nie. Für synthetische
Testprojekte (kein reales Modell) fällt Stufe 2 sofort fail-soft aus → schnell, kein Feld geschrieben.

**Denkmal-Ergebnis.** `propose_decomposition(kind="modul")` legt **16 Module** an, alle rot
`too_thick` (Überschuss 176 mm, Ursache), **ohne Simulation**, in ~1,3 s (Stufe-1-Abkürzung; kein
VHACD). Gegenprobe für Stufe 2 (freigang umgangen, `slow`): dieselben 16 Module rot `collides` mit
Verursacher **Glied 2 / Eindringtiefe 289 mm**, davon **4 geprüft + 12 vermutlich** (4 Höhenreihen),
~71 s für die 4 Repräsentanten — der Beweis, dass die Reihen-Vererbung + der `_SectionSimContext`-Reuse
auf echter Geometrie tragen.

**Tests.** Core: `test_printability.py` (10 schnelle Einheitstests: Repräsentanten-Wahl inkl. None-Marge
+ flacher Stich, Stufe-1-short-circuit, Reihen-Vererbung mit/ohne Kollision, „grün nur aus Prüf-Tür",
`unknown`, Serialisierung) + `test_decompose.py` (Artefakt schreibt Urteil schema-valide + lässt
`unknown` weg + Golden ohne Feld byte-gleich) + `test_printability_denkmal.py` (**Stufe 1: schnell**,
16 Module rot `too_thick` + Ursache, ohne Simulation; **Stufe 2: `slow`**, 16 rot `collides` mit
Verursacher, 4 geprüft + 12 vermutlich). **Der Stufe-2-Denkmal-Test ist als `slow` markiert** (echte
VHACD über 4 Repräsentanten, ~71 s) — er läuft **nicht** in der Standard-Suite. Viewer:
`printability-state.test.ts` (10) + Druckbarkeits-Fälle in `parts-palette-state.test.ts` (Ampel rot bei
erreichbar-aber-kollidiert, grün nur aus Prüf-Tür, „vermutlich" erkennbar, Altlauf-Rückfall, dirty).
872 → 888 vitest, tsc/`vite build` grün, ruff clean. **Noch keine Schnittänderung** (Scheibe 4).

## 2026-07-10 — Priorisierung nach Literatur-Verifikation: Tool vor Fugen, Roadmap E→A→C→B

**Frage.** Die Recherche II ist gegen 18 Volltexte verifiziert (Commit `f9cd970`).
Welche der Optionen A–F zuerst, und wie wird daraus eine Veröffentlichung?

**Kontext/Befunde.** (1) Querbefund: keine der neun Zerlegungs-Quellen prüft je
einen Armkörper gegen den wachsenden Druckstand — unsere Prüf-Tür ist damit das
Neuheitsargument, nicht ein Detail. (2) Zwei Fehlzitate in der Extraktion
gefunden (sinusförmige Verzahnung existiert unter der zitierten DOI nicht;
Fugen-Zugfestigkeiten gehören Poudel, nicht McPherson) → Option D hat aktuell
keinen einzigen verifizierten Festigkeitswert. (3) INF-3DP belegt: statisches
SDF + Fortschrittsfeld genügt für den wachsenden Stand, Voxel-SDF statt
neuronal reicht für die Vorzeichenabfrage.

**Alternativen.** (a) Fugen (D) zuerst — verworfen: Nutzer-Entscheid, Fugenwerte
aktuell nicht relevant, Tool (Bahnplanung/Zerlegung/Platzierung) zuerst; zudem
Evidenz kollabiert (s. o.), D braucht Poudel + Materialversuch → zweites Paper.
(b) Beam-Search (B) zuerst — verworfen: bei 7–16 s Prüf-Tür je Kandidat
unbezahlbar; B braucht E als Enabler, und Wus Zielfunktion J_G (Überhang) misst
bei nicht drehbarer Wand die falsche Größe. (c) SDF sofort bauen — verworfen:
der S5-53-%-Posten (`set_transform`) verteilt sich auf Arm↔Hindernis
(`check.py:368`, profitiert vom SDF) und Selbstkollision (`check.py:382`,
profitiert nicht); Split ist ungemessen.

**Entscheidung.** Roadmap im Recherche-Doc
(`docs/recherche/2026-07-10-adaption-chunking-literatur.md`, Abschnitte
„Ist-Zustand → Optimierungspotenzial" + „Roadmap"): Schritt 0 Messung
set_transform-Split → Schritt 1 Voxel-SDF-ObstacleProvider (E, #144; Naht
existiert: `obstacle_provider` `check.py:265`) → Schritt 2 Winkel-/Höhenschranke
Stufe 1 (A, parallel möglich) → Schritt 3 RM4D-Karte M1013 (C1, Vorfilter;
C2/B* danach grillen, P1-SDF liefert dessen Hindernisgeometrie) → Schritt 4
Beam-Search-Zerlegung (B) mit eigener Zielfunktion (erreichbarer Anteil, c_v,
Fugenfläche), nur Beam-Überlebende durch die Prüf-Tür; #165-Greedy bleibt als
Vergleichsmethode → Schritt 5 Benchmark + Paper (Ziel Automation in
Construction, Fallback RCIM/CAD; vier gegen die Literatur geprüfte Claims,
Risiko „kein Realdruck" als Methods-Paper positionierbar).

**Begründung.** E ist der einzige Schritt ohne Designrisiko und macht B und C2
erst bezahlbar; Messung vor Design, weil sonst evtl. die falsche Hälfte des
53-%-Postens optimiert wird. Die Roadmap-Schritte 1–4 sind zugleich die
Paper-Methoden — kein Doppelaufwand.

---

## 2026-07-10 — CI war rot, seit der Geometrie-Stack kam; Batch-Läufe in die Cloud

**Frage:** Der `/issue-orchestrator` verlangt in Schritt 0 eine grüne Baseline, bevor er
eine Issue-Welle abarbeitet. Beim Vorbereiten des ersten Cloud-Batchlaufs (Welle 1 der
Ehrlichkeits-Nacharbeiten, Spec #168) fiel auf: **GitHub Actions ist auf `main` seit
Längerem durchgehend rot** — die letzten fünf Läufe alle `failure`. Lokal sind dieselben
Suiten grün. Warum?

**Befund:** `.github/workflows/ci.yml` installierte `core[dev]`, also **ohne** das
`geo`-Extra. Die Testmodule importieren `numpy`, `trimesh`, `ifcopenshell` und `fcl`
jedoch **hart** am Modulkopf (kein `pytest.importorskip`, kein `conftest.py`-Guard) —
57 der Dateien tun das. Folge: `ModuleNotFoundError` schon in der pytest-**Collection**,
38 Collect-Errors, der Lauf endet rot, bevor ein einziger Test läuft. Der Widerspruch
lokal-grün/CI-rot ist damit kein Flake, sondern eine Umgebungslücke: das Projekt-venv
hat den Stack, der Runner nicht.

**Alternativen:**

1. `importorskip`-Guards in die 57 Testmodule — CI bliebe schlank, aber die
   Kollisions-/Geometrie-Tests würden auf dem Runner **still übersprungen**. Das ist
   genau die Fehlerrichtung, gegen die die ganze Constraint-Serie kämpft: Unwissen sähe
   aus wie Grün (vgl. #170, „Prüf-Fehler sichtbar").
2. `core[dev,geo]` im Workflow installieren — CI wird langsamer (Wheels für
   `python-fcl`/`vhacdx`/`ifcopenshell`), prüft dafür das, was das Projekt real tut.

**Entscheidung:** (2). Ein CI-Lauf, der die Urteilsgeometrie nicht importieren kann,
prüft die Software nicht, die wir bauen. Lieber langsam und ehrlich als schnell und
blind — dieselbe Regel wie bei der Prüf-Tür.

**Zweite Entscheidung (Cloud-Batch):** Die Issue-Wellen sollen künftig als Claude-Code-
Web-Session laufen können (Laptop zuklappen). Dafür nötig, weil eine Web-Session nur das
**Repo** sieht und keine User-Ebene:

- Der Skill `issue-orchestrator` wandert von `~/.claude/skills/` nach
  `.claude/skills/issue-orchestrator/` **ins Repo** (damit auch versioniert und
  reviewbar, statt nur auf einem Rechner zu leben).
- `scripts/cloud-setup.sh` stellt die Umgebung her: `gh`-CLI (im Web-Sandbox nicht
  vorinstalliert), `core[dev,geo]`, `viewer`-npm-Deps, plus Rauchprobe.
- CLAUDE.md nennt die **Prüfbefehle** jetzt explizit — der Orchestrator liest sie dort
  (Schritt 0 verlangt „die Kommandos aus CLAUDE.md", die es bis dahin nicht gab).

**Konsequenz für Cloud-Läufe:** Der GitHub-Proxy der Web-Sessions erlaubt Pushes nur auf
den Session-Branch. Die Batch-Regel „ein Push am Ende" bleibt gültig, das Ergebnis landet
aber als Branch/PR statt direkt auf `main` — Review durch Tobias ist damit erzwungen,
was für eine unbeaufsichtigte 14-Issue-Welle ohnehin die richtige Reihenfolge ist.

---

## 2026-07-10 — Zwei plattformabhängige Tests: CI/Linux rot, Windows grün

**Frage:** Nach dem geo-Extra-Fix erreichte die CI erstmals die Test-Phase — und
zwei Tests fielen, die lokal (Windows) grün sind. Beides sind Plattform-Wahrheiten,
die die Collection-Blockade zuvor verdeckt hatte, kein neuer Regress.

**Fall 1 — `test_link_frames_flange_matches_forward` (Kinematik):** Die Schwelle
`ori < 1e-12` liegt unter der float64-Auflösung von `ori = 2·acos(dot)` nahe dot=1
— der kleinste darstellbare Wert ≠ 0 ist bereits ~4,2·10⁻⁸. Der Test bestand nur,
weil Windows-BLAS `dot == 1.0` exakt traf; Linux liegt 1 ulp daneben (2,98·10⁻⁸).
**Testfehler, kein Software-Fehler.** Schwelle auf `1e-6` — fängt jede echte
Orientierungsabweichung, ist aber plattformrobust. Der Positionskanal (`pos < 1e-9`)
bleibt unverändert (hat Reserve).

**Fall 2 — `test_decompose_link_is_deterministic_matches_artifact` (VHACD):** Der Test
vergleicht eine frische Konvexzerlegung **byte-genau** mit dem eingecheckten
`base.json`. Die VHACD-Zerlegung ist über Plattformen hinweg **nicht reproduzierbar**
(Windows-Vertices ≠ Linux-Vertices); `base.json` ist ein Windows-Artefakt.

**Alternativen (mit Tobias, HITL):** (a) Toleranz statt Byte-Gleichheit — würde die
byte-identisch-Zusage aufweichen; (b) Byte-Test auf die Herkunftsplattform beschränken.
**Entscheidung: (b)** — `skipif(sys.platform != "win32")`. Damit bleibt Determinismus
**auf einer Plattform** byte-genau garantiert (ADR-004 gilt per Plattform), und
plattformübergreifende Byte-Gleichheit wird **ehrlich nicht behauptet**, statt sie
per aufgeweichter Toleranz vorzutäuschen — dieselbe Ehrlichkeitsregel wie sonst.

**Konsequenz (wichtig für Cloud-Läufe):** Regeneriert eine Linux-Session (Cloud/CI)
ein Kollisions-Artefakt wie `base.json`, ist es **nicht** byte-gleich zum eingecheckten
Windows-Stand. Kollisionsgeometrie-Artefakte gehören daher auf der Herkunftsplattform
erzeugt; die Ehrlichkeits-Welle #168 (V-Serie) berührt sie nicht.

---

## 2026-07-10 — Cloud-Batchlauf: die drei Umgebungs-Blocker von claude.ai/code

**Frage:** Die Ehrlichkeits-Welle (#168-Serie) soll als Claude-Code-Web-Session
laufen (Laptop zuklappen). Die Cloud-Umgebung erwies sich als sperriger als
gedacht — drei Blocker, alle empirisch in der Session selbst gelöst (die
Web-Claude hat diagnostiziert, gefixt, committet).

1. **Arbeitsverzeichnis:** Das Setup läuft in `/home/user`, das Repo liegt in
   `/home/user/RoboPrintIFC`. Setup-Kommando daher `cd /home/user/RoboPrintIFC && bash
   scripts/cloud-setup.sh`; das Skript leitet `REPO_DIR` aus `BASH_SOURCE` ab.

2. **Python-Version:** Das Image bringt 3.12/3.13 unter `/usr/bin` mit, aber
   `/usr/local/bin/python(3)` **und** das `update-alternatives`-Ziel zeigen auf
   3.11 (< Projekt-Minimum 3.12). Ein blankes `python -m pytest` (so ruft der
   Orchestrator) träfe 3.11 und bräche in der Collection ab. Kein pyenv (die
   Patch-Version 3.11.15 war ein Ablenker). **Fix:** venv auf dem ersten
   ≥3.12-Interpreter, `python`/`python3` per **exec-Wrapper** (nicht Symlink!)
   dorthin. Empirisch bestätigt: ein Symlink aufs venv-Python bricht die
   venv-Erkennung (Python folgt dem Link, verliert `pyvenv.cfg`, landet im
   System-Prefix); ein Wrapper behält sie. Wrapper in `/usr/local/bin` **und**
   `~/.local/bin` (beide auf jedem PATH), Akzeptanztest in frischer Login-Shell.

3. **Egress-Policy (der lehrreichste):** Der Proxy gibt GitHub **nur für dieses
   eine Repo** frei. Damit liefern (a) die Fremd-PPAs deadsnakes/ondrej 403
   (`apt-get update` bricht ab — apt bleibt unbrauchbar) und (b) die
   `gh`-Release-Assets von `github.com/cli/cli` 403. Das ist eine
   Policy-Ablehnung, kein Netzfehler — **nicht drumherum routen**. `proxy.golang.org`
   ist hingegen freigegeben, also wird `gh` aus dem Quelltext über den
   sanktionierten Go-Modul-Proxy gebaut (`go install …@v2.63.2`). Die vorige
   Fassung (gh als Direkt-Binary) wäre genau an dieser Policy gescheitert.

**Ergebnis:** `scripts/cloud-setup.sh` ist idempotent und in der Cloud
verifiziert (ruff clean, viewer 888 grün, geo-Stack importierbar, Baseline-pytest
grün). **Offen bleibt der GH_TOKEN:** die Issue-Operationen des Orchestrators
(`gh issue view/close/comment`) brauchen einen gültigen fine-grained PAT (nur
dieses Repo, Issues read/write, kurze Ablaufzeit) als Umgebungsvariable — ohne
den kann die Session die Umgebung einrichten und Code committen, aber keine
Issues schließen. Push aus der Web-Session ist per GitHub-Proxy auf den
Session-Branch beschränkt (Ergebnis kommt als Branch/PR, Review erzwungen).

---

## 2026-07-10 — Umsetzung #170: Prüf-Fehler sichtbar — Fehlerklasse, Log, „ungeprüft"-Zustand, ehrlicher Zähler-Nenner

**Frage:** Die Zwischenkritik (`docs/reviews/2026-07-10-constraint-serie-zwischenkritik.md`,
Befunde B5/B12/B34/B35) zeigte: jeder **Prüf-Fehler** stellte still das entlarvte „16/16 ✓"-Bild
wieder her. Die zwei schluckenden `except Exception`-Stellen der Prüf-Tür verschluckten **jede**
Ausnahme **ohne Log** und lieferten `None`; `combine_printability` machte daraus `unknown`; der
Artefakt-Schreiber **ließ `unknown` weg**; der Viewer fiel auf die alte **Erreichbarkeits-Ampel**
samt altem Zähler zurück. Ein **totes Prüfsystem** (Regression/fehlende Bibliothek) war so nicht von
einem **unzuständigen** (Altprojekt ohne Kollisions-Geometrie) zu unterscheiden. Wie wird der
Prüf-Fehler durchgängig **sichtbar** — vom Core bis zur Palette — als Ende-zu-Ende-Scheibe (Fundament
für #180/#182), streng **Befund, kein Gate** (ADR-013)?

**Alternativen.**
- *(a) Fehler werfen statt schlucken* (die naheliegende B5-Nacharbeit). **Verworfen:** widerspricht
  „Befund, kein Gate" — ein Prüf-Fehler an **einem** Teil darf den ganzen Zerlegungslauf nicht kippen.
  Der Fehler muss **sichtbar**, aber **nicht fatal** sein.
- *(b) Ein einziger „ungeprüft"-Topf ohne Grund.* **Verworfen:** B5 verlangt ausdrücklich, „totes
  Prüfsystem" von „unzuständig" zu unterscheiden — sonst bleibt eine Dauer-Regression unsichtbar
  hinter einer legitimen Altprojekt-Anzeige.
- *(c) Reachability als Ampel-Rückfall behalten* (Status quo). **Verworfen:** genau die B35-Lüge —
  die alte Erreichbarkeits-Anzeige ist ununterscheidbar von einem geprüften Stand.
- *(d) Ungeprüfte aus dem Zähler-Nenner rechnen* (Status quo, B34). **Verworfen:** erzeugt „4/4 ✓"
  bei 12 ungeprüften Teilen — dieselbe Lüge in klein.

**Entscheidung (Ende-zu-Ende, beide Nähte).**
1. **Core — Fehlerklasse + Log.** Die zwei Stellen (`_section_clearance_check`,
   `_clearance_verdict_for_section` in `pipeline/actions.py`) **loggen** jede Ausnahme
   (`logging.warning`, `exc_info=True`; erster Logger dieser Datei) und geben statt `None` einen
   **Grund** zurück: `REASON_NO_GEOMETRY` (Prüf-Tür lief, war aber unzuständig — `check_part_clearance`
   lieferte `None`) vs. `REASON_ERROR` (Ausnahme geschluckt). `combine_printability` liest die
   Grund-Strings und setzt `PartPrintability(verdict=unknown, reason=…)` — **ein String wird nie als
   freies Urteil missdeutet** (`isinstance(verdict, str)`-Guard vor dem `getattr(...collides)`, sonst
   würde ein Absturz zu „frei", genau B12). Neue Konstanten `REASON_NO_GEOMETRY`/`REASON_ERROR` +
   Feld `reason` in `fgc.decompose.printability`; `to_dict` schreibt `reason` **nur** bei `unknown`
   (echte Urteile byte-gleich).
2. **Core — Schreiber schreibt `unknown` mit `reason`.** Beide Schreibstellen
   (`decompose/artifact.py:_section_dict`, `actions.py`) schreiben `printability` jetzt für **alle**
   Teile inkl. „ungeprüft" — die Fehlerklasse landet im `decompose.json` (`sections[].printability.reason`,
   Schema additiv erweitert). **Altläufe byte-gleich**: ohne das `printability`-Argument (Altlauf)
   erscheint das Feld gar nicht — die frühere „unknown weglassen"-Regel (die B34/B35 zementierte) ist
   damit bewusst umgekehrt (der Testname `..._writes_printability_including_ungeprueft` hält das fest).
3. **Viewer — dritter Zustand sichtbar.** `printabilityView` liefert für `unknown` eine eigene
   Ansicht (`severity: "unknown"`, Label „ungeprüft", Grund im Titel) statt `null`; nur ein
   **fehlendes** Feld (Altlauf) bleibt `null`. `paletteEntries` färbt die Ampel bei fehlendem/`unknown`
   Urteil **„ungeprüft"** — **nicht** mehr Erreichbarkeit (B35); die Erreichbarkeit bleibt als eigene
   „erreichbar N %"-Zeile. Darstellung: offener Ring **◍** (vs. `●` grün/rot, `◌` „vermutlich") + amber,
   gestrichelt umrandetes „ungeprüft"-Badge (`.parts-part-printability.unknown`).
4. **Viewer — ehrlicher Zähler.** `printabilityCounter`: Nenner = **alle** Teile; Ungeprüfte
   (`null` = Altlauf/dirty **oder** `severity: "unknown"`) werden **ausgewiesen** — „4 druckbar ·
   12 ungeprüft"; „N/N druckbar ✓" nur, wenn wirklich jedes Teil geprüft-frei ist. Liefert `null` nur
   bei leerer Palette.

**Begründung.** Die Fehlerrichtung bleibt konsequent **nie „frei"**: no_geometry und error führen
beide zu „ungeprüft", der `isinstance`-Guard schließt aus, dass ein geschluckter Absturz grün wird
(B12). Die **Unterscheidbarkeit** (B5) lebt als `reason` im Artefakt (Lauf-Eigenschaft, konsistent zum
#164-Geist „Druckbarkeit ist Lauf-Eigenschaft") **und** im Tooltip. Der Zähler-Nenner (B34) und die
Altlauf-Anzeige (B35) sind rein subtraktiv ehrlich — die Erreichbarkeit verschwindet nicht, sie ist nur
nicht länger als Druckbarkeits-Ampel getarnt. Alles reine Ableitung im Viewer (ADR-007), alles Befund,
kein Gate (ADR-013). Kein neues ADR nötig (füllt die #164-Scheibe an ihrer Fehlerkante).

**Namensschema-Entscheidung.** Die Fehlerklassen heißen exakt `no_geometry`/`error` (Issue-Vokabular),
als geschlossenes Enum im Schema (`printability.reason`) und im Viewer-Typ. Verworfen: `library`/`crash`
o. Ä. (weniger an der Domänensprache „unzuständig vs. fehlgeschlagen").

**Tests an beiden Nähten.** Core: `combine_printability` bildet `None`/`no_geometry`/`error` → `unknown`
mit `reason` (nie grün); die beiden Actions-Helfer loggen + geben `REASON_ERROR` (Ausnahme) bzw.
`REASON_NO_GEOMETRY` (Prüf-Tür `None`) zurück; der Artefakt-Schreiber schreibt „ungeprüft" mit Grund
(`test_printability.py`, `test_decompose.py`). Viewer: `printabilityView` (dritter Zustand + Grund im
Titel), `printabilityCounter` (Nenner-Regel „4 druckbar · 4 ungeprüft", „N ungeprüft"),
`parts-palette-state` (Altlauf/`unknown` ⇒ Ampel „ungeprüft", nicht Erreichbarkeit) und `parts-palette`
(DOM: ◍ + „ungeprüft"-Badge). ruff/pytest/vitest/tsc/build grün.

---

## 2026-07-10 — Umsetzung #169: Abschnitts-ID-Strenge in `check_section_clearance`

**Frage:** Befund B4 der Zwischenkritik (`docs/reviews/2026-07-10-constraint-serie-zwischenkritik.md`)
zeigte: `check_section_clearance` (Pipeline-Aktions-Naht der Prüf-Tür, #162) ersetzt eine unbekannte
`section_id` still durch den **ersten** Abschnitt des Plans (`section_id if section_id in sids else
sids[0]`) — tendenziell der freieste, weil er noch keine früher gedruckten Teile als Hindernis trägt.
Der Aufruf kennt bereits eine Ebene tiefer (`_section_sim_context`) einen präzisen Fehler für unbekannte
Abschnitte, der durch die vorherige stille Reparatur nie erreicht wird. Die **Job-ID** desselben
Aufrufs ist dagegen schon streng (unbekannt ⇒ `ValueError`, kein Rückfall auf einen anderen Job). Wie
wird die Abschnitts-ID ebenso streng, ohne die Reuse-Semantik des vorgereichten `ctx` (#165-Vorarbeit)
zu brechen?

**Alternativen.**
- *(a) Nur den Fallback auf `sids[0]` streichen, `ctx` weiter unbedingt gewinnen lassen.*
  **Verworfen:** deckt nicht den zweiten Teil des Issues — ein explizit übergebenes `section_id`, das
  vom mitgereichten `ctx` abweicht, würde weiter still zugunsten des `ctx` aufgelöst; derselbe
  ID-Fehler (Tippfehler, Plan-Drift nach Neuzerlegung, künftiger #165-Loop) bliebe durch die Hintertür
  „ctx gewinnt immer" möglich.
- *(b) `section_id` immer Vorrang vor `ctx` geben, `ctx` nur als Cache-Hinweis.* **Verworfen:** der
  ganze Sinn des vorgereichten `ctx` (#165-Vorarbeit, Reuse aus `_section_sim_context`) ist, dass er
  bereits **für einen bestimmten Abschnitt** aufgebaut wurde — würde man ihn bei abweichender
  `section_id` einfach ignorieren, liefe die Prüfung mit dem *falschen* Unterbau (Toolpath/Verts eines
  anderen Abschnitts) unter dem *verlangten* Namen: subtiler als der ursprüngliche Bug.
- *(c) Konflikt zwischen `ctx` und explizitem `section_id` als Fehler behandeln, sonst `ctx` gewinnt;
  ohne `ctx` gilt die bestehende Job-ID-Strenge sinngemäß auf `section_id`.* **Gewählt.**

**Entscheidung.** In `check_section_clearance` (`core/src/fgc/pipeline/actions.py`) löst sich die
Abschnitts-ID jetzt wie die Job-ID weiter oben in derselben Funktion:
- Kein `ctx`, keine `section_id` ⇒ wie bisher der erste Abschnitt (Default-Verhalten unverändert —
  kein Bruch bestehender Aufrufer, die bewusst „den ersten Abschnitt" meinen).
- Kein `ctx`, `section_id` bekannt ⇒ dieser Abschnitt (unverändert).
- Kein `ctx`, `section_id` unbekannt ⇒ **`ValueError`**, die ID benennt sich selbst plus die
  vorhandenen IDs (`f"Abschnitt {section_id!r} existiert nicht … (vorhanden: {sids})"`) — kein
  stiller Rückfall mehr.
- `ctx` vorhanden, `section_id` `None` oder identisch zum `ctx`-Abschnitt ⇒ `ctx` gewinnt (Reuse
  #165 unverändert).
- `ctx` vorhanden, `section_id` **abweichend** ⇒ **`ValueError`** („Kontext-vs-ID-Konflikt"): der
  Aufruf wird zurückgewiesen statt still (zugunsten des `ctx`) aufgelöst — das dritte
  Akzeptanzkriterium des Issues.

**Begründung.** ADR-013 (Befund/Gate-Trennung) bleibt unberührt: Ein Kollisions-**Befund**
(„kollidiert"/„frei"/„ungeprüft") darf den Zerlegungslauf nie kippen — ein **ID-Fehler** ist aber kein
Kollisions-Befund, sondern ein Programmier-/Eingabefehler (falsche ID hereingereicht) und gehört
deshalb zur Kategorie, die schon die Job-ID-Prüfung im selben Aufruf hart abfängt. Ein stiller
Rückfall auf `sids[0]` hätte im künftigen #165-Verfeinerungs-Loop (iteriert über Zellen-IDs eines
frisch geschnittenen Plans) dazu geführt, dass jede veraltete ID lautlos das Urteil des freiesten
Abschnitts liefert — genau der stumme Fehlerpfad, den die Ehrlichkeits-Welle (#170) an anderer Stelle
schon beseitigt hat. Die tiefere Fehlerprüfung in `_section_sim_context` wird dadurch nicht mehr
umgangen; sie bleibt als zusätzliches Netz erhalten (z. B. wenn ein bekanntes `section_id` durch eine
Race zwischen `sids`-Auflösung und `plan.sections` doch nicht mehr existiert).

**Test.** `core/tests/test_collision_advisor_action.py::test_check_section_clearance_section_id_strictness`
(`slow`, echte Simulation): bekannte ID ⇒ Urteil unverändert (dieselbe Prüf-Tür-Assertion wie
`test_check_section_clearance_real_verdict`); unbekannte ID ⇒ `ValueError`, der die ID nennt; `ctx`
eines anderen Abschnitts + widersprechende `section_id` ⇒ `ValueError` mit „widerspricht". ruff/pytest
grün.

---

## 2026-07-10 — Ampel-Konjunktion: grün nur bei Erreichbarkeit UND Druckbarkeit (Issue #180, Befund B33)

**Frage.** Seit #164 zeigt jedes Teil ein Druckbarkeits-Urteil (Freigang + repräsentative
Prüf-Tür). Der Befund B33 der Zwischenkritik (drittes Issue der Ehrlichkeits-Welle) legte eine
Regression *in die verbotene Richtung* frei: das neue Druckbarkeits-Urteil **überstimmte** einen
bereits vorhandenen, härteren **roten Erreichbarkeits-Befund**. Ein Teil, das der Arm nur zu
50 % erreicht (vor #164 rot), konnte grün werden, sobald die Prüf-Tür seine repräsentative Zelle
kollisionsfrei sah — die Prüf-Tür ist strukturell blind für Unerreichbarkeit (unfahrbare Posen
werden eingefroren, nicht gemeldet). Wie verbindet man die beiden Kanäle, ohne den einen zu
verstecken?

**Alternativen.**
1. *Ersetzen (Status quo, verworfen):* Druckbarkeit ersetzt die Erreichbarkeits-Ampel. Genau der
   B33-Fehler — ein weicherer Befund überschreibt einen härteren.
2. *Gate:* ein unerreichbares Teil hart abweisen. Verworfen — verletzt ADR-013 (Befund statt Gate);
   der Plan darf nie blockiert werden, und beide Befunde sollen sichtbar bleiben.
3. *Konjunktion, ein Kanal ersetzt den anderen im `verdict`:* z. B. `verdict` bei Unerreichbarkeit
   auf `unknown`/`collides` umschreiben. Verworfen — das würde den *ehrlichen* Prüf-Tür-Kanal
   fälschen (die Prüf-Tür *sah* das Teil frei); der Grund wäre nicht mehr ablesbar.
4. **Konjunktion, beide Kanäle getrennt transportiert (gewählt):** das Urteil trägt weiterhin den
   Prüf-Tür-`verdict` **und** zusätzlich den Erreichbarkeits-Kanal (`reachable`/`reachable_fraction`).
   Grün (`PartPrintability.printable`) ist die **Und-Verknüpfung** — Prüf-Tür-`printable` **und**
   voll erreichbar. Die UI kombiniert beide sichtbar.

**Entscheidung.** Konjunktion an **beiden Nähten**, beide Kanäle bleiben ablesbar:
- **Core** (`fgc.decompose.printability`): `PartPrintability` bekommt `reachable`/`reachable_fraction`;
  `printable` = `verdict == printable` **und** `reachable`. `combine_printability` nimmt den optionalen
  `status_by_id` (der Reichweiten-Befund, in der Pipeline ohnehin vorhanden) und stempelt beide Kanäle
  auf **jedes** Urteil (auch too_thick/collides/unknown — beide Kanäle immer lesbar). Ohne
  `status_by_id` (Altaufrufer, reine #164-Tests) ist die Konjunktion ein **No-op** (alle Teile gelten
  als erreichbar) — die bestehenden #164-Ampeltests laufen **unverändert grün** (kein stilles
  Anpassen nötig). `_decompose_printability` (`pipeline/actions.py`) reicht `status_by_id` in beide
  `combine_printability`-Aufrufe (Stufe-1-Short-Circuit **und** Stufe-2).
- **Viewer** (`ui/printability-state.ts`, `printabilityView`): bei `verdict === "printable"` und
  `reachable === false` wird die Ampel **rot** mit Text *„kollisionsfrei, aber teilweise unerreichbar
  (N %)"* — die Kombinationsregel. Fehlt `reachable` (voll erreichbar / Altlauf), No-op → grün wie
  bisher (bestehende vitest-Fälle unverändert). Der Kopfzähler `printabilityCounter` folgt
  automatisch (severity ist schon rot) — ein unerreichbares Teil zählt nicht als geprüftes ✓.

**Byte-Gleichheit.** Der Erreichbarkeits-Kanal wird im `to_dict`/Artefakt **nur bei nicht voller
Erreichbarkeit** geschrieben (genau wie `reason` bei #170) — voll erreichbare Teile bleiben
byte-gleich, das Schema (`decompose.schema.json`, `additionalProperties: false`) ist additiv um
`reachable`/`reachable_fraction` erweitert. Für voll erreichbare Teile bleibt der erreichbare Anteil
über `sections[].status.reachable_fraction` lesbar (keine Dopplung im Normalfall).

**Begründung.** ADR-013 gewahrt: kein Gate, nur ein ehrlicherer Befund. ADR-007 gewahrt: der Viewer
rechnet nichts, er kombiniert zwei bereits vom Core publizierte Kanäle zur Anzeige. Die Konjunktion
liegt bewusst **doppelt** (Core `printable` + Viewer `printabilityView`), damit sie an der
Pipeline-Aktions-Naht **und** an der reinen Zustandsfunktion getestet festgenagelt ist — beide sind
die Stellen, an denen ein künftiger Refactor sie versehentlich wieder auf „Ersetzen" zurückdrehen
könnte.

**Tests.** Core: `test_printability.py` — `test_partial_reachability_never_yields_green` (frei +
50 % erreichbar ⇒ `verdict` bleibt `printable`, `.printable` ist `False`),
`test_reachability_channel_serialized_only_when_unreachable` (Byte-Gleichheit),
`test_reachability_carried_on_all_verdicts_without_changing_color`,
`test_no_status_by_id_is_noop_conjunction`. Pipeline-Aktions-Naht: `test_decompose.py`
`test_decompose_printability_partial_reachability_never_green` (`_decompose_printability` mit
gemockter Prüf-Tür, ein erreichbares + ein 50 %-erreichbares Teil ⇒ nur das erreichbare grün).
Viewer: vier neue `printability-state.test.ts`-Fälle (No-op grün, rote Kombination mit N %,
`vermutlich`-Erhalt, Zähler-Konjunktion). Bestehende #164-Ampeltests **unverändert grün** (No-op).
ruff/pytest/vitest/tsc/build grün.

## 2026-07-10 — Override-Merge: Einzelfeld-Optionen bewahren bestehende freie Felder (#173, Befund B18)

**Frage.** Das Anwenden einer **Einzelfeld-Option** des Kollisions-Advisors
(Abstand ODER Aufstellhöhe) baute den `section_overrides`-Eintrag des Teils in
`set_placement_override_for_job` **neu auf** — ein zuvor gesetztes freies Feld
verschwand still. Szenario (B18): Nutzer setzt Abstand 600 mm als Override und
wendet danach „Aufstellhöhe 200 mm" an ⇒ der Abstands-Override fällt weg, die
effektive Platzierung fällt für den Abstand auf die Automatik zurück. Der
Advisor hat den Kandidaten aber **mit** dem alten Override simuliert und
bewertet (`_slice_and_simulate_section` legt die sparse Kandidaten-Platzierung
feldweise auf `ctx.placement`, das die bestehenden Overrides bereits enthält) —
die versprochene Marge galt also für einen Zustand, den das Anwenden gar nicht
herstellt: **angewandter Zustand ≠ bewerteter Kandidat**.

**Alternativen.**
1. *Advisor schreibt alle Felder* (wie der Singularitäts-Advisor). Verworfen:
   der Advisor kennt nur die **effektiven** Basiswerte (auto + Override), nicht,
   welche davon freie Overrides sind — alle drei zu schreiben würde
   auto-berechnete Werte als Overrides einfrieren.
2. *Merge in `set_placement_override_for_job`* — dort liegt `old_entry`, also
   genau der bestehende sparse Override; das Preservieren ist präzise auf die
   tatsächlich gesetzten freien Felder beschränkt. **Gewählt.**

**Entscheidung.** `set_placement_override_for_job` bekommt ein keyword-only
`merge: bool = False`. Default (`False`) = **Neuaufbau/Replace** wie bisher —
ein `None`-Feld löscht ein zuvor gesetztes Feld, das **manuelle
Platzierungs-Formular** und der **Singularitäts-Advisor** (schreibt ohnehin alle
drei Felder) sind unberührt. Mit `merge=True` startet `_mutate` aus den
bestehenden freien Feldern des `old_entry` (nur `PLACEMENT_OVERRIDE_FIELDS`) und
legt die übergebenen sparse Werte feldweise darüber; die `option_id`-Referenz
(#25) bleibt wie gehabt erhalten. Die „alles leer ⇒ Eintrag entfernen"-Prüfung
läuft jetzt über `has_free` (byte-gleich zum bisherigen `not free`-Check im
Nicht-Merge-Fall).

**Plumbing.** Der Advisor markiert seine beiden Platzierungs-`write`-Nutzlasten
(Abstand/Aufstellhöhe) mit `"merge": True` (`fgc.collision.advisor`); die
API-Route (`SetPlacementOverrideRequest.merge`, Default `False`) reicht es an
die Aktion. Viewer: `CollisionWrite`/`PlacementOverrideValues` tragen ein
optionales `merge`, `collisionApplyActionFor` übernimmt es aus der Nutzlast,
`setPlacementOverride` sendet es (spreadet `...values` in den Body). Der
Singularitäts-Advisor-Pfad und das Formular setzen `merge` nicht → Replace.

**Begründung.** ADR-013/016 gewahrt: kein Gate, `fgc.project` bleibt die einzige
Schreibstelle; der Merge ist additiv und opt-in. Konsistenz mit dem
Singularitäts-Advisor (der alle Felder schreibt) wird per Merge hergestellt
statt per Feld-Duplikation im Advisor. Der Effekt ist symmetrisch
(Abstand↔Aufstellhöhe), weil `merge` feldneutral über `PLACEMENT_OVERRIDE_FIELDS`
arbeitet.

**Tests.** Core Pipeline-Aktions-Naht (`test_decompose.py`):
`test_set_placement_override_merge_preserves_other_free_fields` (A setzen, B
mergen ⇒ beide da; symmetrisch am Nachbarn; Kontrast: ohne `merge` räumt Replace
ab), `test_propose_decomposition_effective_placement_has_both_merged_fields`
(end-to-end: die vom Zerlegungslauf abgeleitete effektive Platzierung trägt A UND
B), `test_api_put_placement_override_merge_preserves_existing` (Route-Plumbing).
`test_collision_advisor.py`: Platzierungs-Kandidaten tragen `merge=True`. Viewer
`collision-advisor-state.test.ts`: `merge` fließt in die Anwenden-Aktion,
Altdaten ohne Flag ergeben kein `merge`. ruff/pytest/vitest/tsc/build grün.

## 2026-07-10 — Effektive-Platzierung-Selektor: eine Lesequelle für alle Platzierungs-Leser (Issue #171, V3-Lesepfad)

**Frage.** Die Constraint-Serie-Zwischenkritik zählte (B23) mindestens **sechs**
Lesepfade, die im Viewer die Platzierung eines Teils je selbst ableiten — nur
**einer** (der Modul-Replay am Druckort, `druckortSceneSpecForRun`, #161) war per
Bauart an die frische Quelle gebunden. Die übrigen lasen die (ggf. veraltete)
Zerlegungs-Platzierung **ohne** die aktiven Overrides des Jobs; Folge: Basis-Marker,
Fokus-Arm, Basis-Chips, Vorbereiten-3D (inkl. Sicherheitsurteil) und die statische
Druckort-Ansicht konnten dauerhaft zur **alten** Lage urteilen, während der Arm
schon an der neuen stand (B17/B19/B21). Wie eine **einzige** Naht bauen, ohne neuen
Zustand (ADR-007)?

**Die aufgezählten Leser (V3).** Einbauort/**skalar** (`section.placement` ⊕
Override): (1) Basis-Marker aller Teile (`buildPlacementMarkers`/`sectionMarkerPosition`),
(2) Fokus-Arm (`sectionBaseFrame`), (3) Basis-Chips (`rebuildBasisChips`),
(4) Vorbereiten-3D Bahn+Sicherheitsurteil (`PreparePreview`), (5) Wand-Gesamtablauf-
Basis-Marker (`updateSequence`), (6) Modul-Karten (`placementDisplayValues`).
Druckort/**Frame** (Lauf vs. Zerlegung): (7) statische Druckort-Ansicht
(`enterDruckort`/`refreshDruckortScene`), (8) Replay-Bühne (`druckortSceneSpecForRun`).

**Entscheidung.** Ein neues reines Modul `viewer/src/ui/effective-placement.ts` mit
zwei Faces: `effectivePlacement(placement, override)` (skalar: Zerlegung feldweise
übersteuert durch die gesetzten freien Override-Felder — der frühere Merge aus
`placementDisplayValues` #161, jetzt zentral) und `effectiveModuleFrame({runFrame,
decompositionFrame})` (Frame: frischer Sim-Lauf gewinnt über die Zerlegungs-Lage).
**Alle** Leser 1–8 beziehen daraus. Die skalaren reinen Reader-Funktionen bekommen
einen optionalen `override`-Parameter und rufen **intern** den Selektor — es gibt
keinen Bypass mehr, auch der Aufruf ohne Override läuft durch die eine Funktion.

**B19 (Soll-Kasten springt).** Die statische Druckort-Ansicht bekommt die frische
Lauf-`base_frame` über einen reinen Lese-Cache je Laufordner (`section_runs` →
`loadFromUrl`, `ensureModuleRunFrameCached`, kein Fachzustand). Beim Eintritt/Refresh
baut die Szene sofort aus dem Cache (oder Zerlegungs-Lage) und zieht per
`scheduleDruckortRunFrame` die geladene Lage nach — dieselbe Regel wie der Player.

**Verworfen.** (a) Die Wurzel (Zerlegungslauf altert nach Override unmarkiert,
B16/B32) in den Core-Revisionen zu heilen — außerhalb des Viewer-Scopes dieses
Issues; der Selektor macht die *Ableitung* ehrlich, nicht die Persistenz. (b) Den
Frame-Face in `druckort-spec.ts` belassen — er ist jetzt Teil desselben Selektor-
Moduls, damit „eine Naht" auch für die Druckort-Leser gilt. (c) B22 (1-mm-Soll-
Kasten aus UI-Zustand) — betrifft die Box-**Dicke**, nicht die Platzierung; außerhalb
dieses Lesepfads, bleibt offen.

**Einquelligkeit strukturell (Wahl).** Gewählt: **Import-/Lint-Regel als vitest**
(`effective-placement.test.ts`) statt Aufrufketten-Test. Begründung: `main.ts` ist
DOM-/three.js-schwer und nicht sinnvoll unit-testbar (ein Aufrufketten-Test müsste
den halben Viewer mocken); die Import-Regel ist dagegen deterministisch, billig und
fängt genau die Regression, die #171 verhindern will — ein **neuer** Direktleser.
Der Test prüft je Reader-Modul: (i) es importiert den Selektor, (ii) es liest **kein**
skalares Feld direkt aus `*.placement.*` (Direktzugriff ⇒ roter Test). Dazu die reinen
Selektor-Tests über alle Fälle (Override gesetzt/nicht, nicht-endlich, option_id-only,
Lauf da/fehlt/beides-null) plus ein behavioraler Reader-Test (`sectionMarkerPosition`
folgt dem Override).

**Ergebnis.** Einquelligkeit gilt per Bauart, nicht per Disziplin; der Viewer bleibt
zustandsloser Abspieler (ADR-007). Viewer **916 vitest** (+18) grün, tsc + vite build
grün; keine Core-Berührung. Kein bestehender Test angefasst (Beleg für „Verhalten
unverändert" außer an den vier gefixten Nähten).

---

## 2026-07-10 — Advisor-Anwenden invalidiert + Druckplan-Revision an der Quelle (Issue #172)

**Frage.** Beide Advisor-Anwenden-Flüsse (Kollisions- #130, Singularitäts-Advisor
#65/#134) ließen nach „Anwenden" einer Platzierungs-Option Ampel, Druckbarkeits-
und Kollisions-Badge des Teils **unmarkiert** stehen — das alte Urteil zur alten
Platzierung, direkt neben den per #161 ehrlich aktualisierten neuen Override-Werten
(Befunde B11/B20/B32). Das manuelle Platzierungsfeld (`onSaveOverride`) macht es
richtig: es stößt die Neubewertung an, Ampel/Badges gehen sofort auf „ungeprüft".
Zusätzlich (Wurzel von #161, B16/B32): der Druckplan-**Output** in den Core-Revisionen
veraltete bei einem Platzierungs-/Abschnitts-Override **nicht** — der Zerlegungslauf
trug danach eine überholte Platzierung, blieb aber „aktuell".

**Entscheidung.** Zwei Nähte, je an der Quelle:

1. **Viewer — Anwenden-Parität.** Der eine getestete Anwenden-Fluss
   (`ui/placement-apply.ts`, den BEIDE Advisors nutzen, #161) bekommt einen sechsten
   Schritt: `reevaluateDecomposition(overrides)` → `druckplanPanel.applySectionOverrides`
   — **exakt** die Sequenz des manuellen Felds (dirty setzen → Ampel/Badges „ungeprüft"
   → debouncte Neuprüfung). Parität per Konstruktion, nicht per Copy-Paste. Zusätzlich
   entwertet `paletteEntries` bei `dirty` jetzt auch das **Kollisions-Badge** (`null`),
   nicht nur Ampel + Druckbarkeit — der alte Kollisionsbefund gilt der alten Platzierung
   (B20). Damit zeigt die Modul-Karte nie neue Override-Werte neben unmarkierten alten
   Urteilen.

2. **Core — Druckplan-Revision an der Quelle.** Statt jeden Leser einzeln nachzuziehen
   (#161-Symptompflege) beobachtet der Druckplan-Output in der Revisionsmechanik
   (`project/revisions.py`) jetzt die **Summe aller Pro-Abschnitts-Zähler**
   (`SECTION_AGGREGATE_DEP = "section_total"`, nur für `druckplan`): `refresh_output`
   schnappt sie beim (Neu-)Erzeugen, `output_status` meldet den Druckplan **veraltet**,
   sobald die Summe seither gestiegen ist. Da `section_inputs`-Zähler nur steigen
   (nie gelöscht), ist die Summe monoton — ein Anstieg ⇒ zuverlässig veraltet. Ein
   Platzierungs-Override (`set_placement_override_for_job` → `bump_section_input`) oder
   Abschnitts-Slicing/-IK-Override (`set_process_params` sections) veraltet damit den
   ganzen Zerlegungslauf; die **per-Abschnitt**-Stufen (Simulation/Export) veralten wie
   bisher feingranular nur für das betroffene Teil (`section_output_status` unberührt).
   TS-Parität in `ui/staleness.ts` (`stageStatus` druckplan). Schema: additiver Key
   `section_total` im `revision_snapshot`.

**Alternativen (verworfen).** (a) Den Druckplan als neue Job-Eingabe (`bump_input`)
veralten — würde Simulation/Export mitreißen und die feingranulare #83-Ebene brechen;
der aggregierte Beobachter trifft nur den ganzen Plan. (b) Pro Leser im Viewer die alte
Quelle als veraltet ausweisen — genau die #161-Symptompflege, die #172 an der Wurzel
ersetzt. (c) Das alte Urteil beim Anwenden **löschen** statt als „ungeprüft" markieren —
ein Befund darf sichtbar veralten, nicht so tun als sei nie geprüft worden (ADR-013).

**Byte-Gleichheit.** Ohne je gesetzten Abschnitts-Override bleibt `section_inputs` leer,
`refresh_output` schreibt **kein** `section_total` in den Druckplan-Schnappschuss —
Altprojekte/-Jobs unverändert (`output_status` fällt auf Summe 0 zurück). Zwei
Bestandstests (`test_set_process_params_(ik_config_)section_override_stales_only_that_section`)
behaupteten das alte Verhalten (Druckplan bleibt „current" bei Abschnitts-Override) —
sie sind auf das neue, korrekte Urteil „stale" nachgezogen (die per-Abschnitt-Aussage
„nur dieses Teil" gilt weiter für Simulation/Export).

**Tests.** Core: `test_placement_override_stales_druckplan_output_at_source`
(Pipeline-Aktions-Naht: propose → override ⇒ druckplan stale → re-propose ⇒ current),
`test_section_override_stales_druckplan_at_source` + `test_druckplan_snapshot_byte_equal_
without_section_overrides` (reine Revisionsmechanik). Viewer: `placement-apply.test.ts`
(sechster Schritt `reevaluate` im Vertrag, mit frischem Override-Stand), `parts-palette-
state.test.ts` (dirty entwertet Kollisions-Badge, B20-Szenario). ruff/pytest/vitest/
tsc/build grün.

---

## 2026-07-10 — Umsetzung #174: Repräsentanten-Wahl der Reihen-Vererbung kollisionsehrlich

**Kontext (Ehrlichkeits-Welle, Befunde B10/B13/B26/B36 der Constraint-Serie-Zwischenkritik).**
Die Druckbarkeits-Ampel (#164) prüft je Höhenreihe nur **eine** Zelle (die teure Prüf-Tür
kostet ~10 s/Teil) und lässt die übrigen ihr Urteil `presumed` erben. Die Wahl dieser
Repräsentanten-Zelle (`representative_by_row` in `decompose/printability.py`) war
**kollisions-blind**: sie kürte die Zelle mit der kleinsten kinematischen Marge, Stich bei
Gleichstand `min(order)`. Der Review zeigte drei Löcher, alle mit Fehlerrichtung „frei":

- **B10:** kein Term maß die **Hindernislast** aus früher gedruckten Teilen — den
  eigentlichen Kollisionstreiber bei Art „Abschnitt" (der Arm fährt durch das frische
  Material der Nachbarbänder). Bei „Abschnitt" ist der Metriken-Gleichstand innerhalb einer
  Reihe **konstruktiv** (eine Platzierung, gleiche Zellmaße), also griff `min(order)` immer
  und kürte die **zuerst** gedruckte, hindernisärmste Zelle — die als einzige keine frischen
  Nachbarn als Hindernis hat. Eine kollidierende Reihe konnte so „frei/vermutlich frei" erben.
- **B13:** eine Zelle **ohne erreichbare Pose** (fehlende Kinematik-Marge) bekam `-inf` und
  gewann die Wahl **zwingend** — die Simulation friert eine unfahrbare Pose auf der letzten
  gültigen Gelenkstellung ein, die Prüf-Tür urteilt dann über eine **eingefrorene**,
  physikalisch bedeutungslose Trajektorie (typisch „frei"), die die ganze Reihe erbt.
- **B36:** die Vererbung stand auf einem nie gegen den vollen Befund validierten Proxy, und
  sie ignorierte, dass einzelne Zellen **eigene Platzierungs-Overrides** tragen können — ein
  geerbtes Urteil wäre dann an einer **anderen** Platzierung gemessen worden.

**Entscheidung (V4 der Zwischenkritik).** Die vier Auswahlregeln:

1. **Hindernislast-Max statt Kinematik.** Repräsentant je Reihe ist die Zelle mit
   **maximaler Hindernislast in Druckreihenfolge** (`_obstacle_load`). Der Term ist **keine
   Heuristik**, sondern die tatsächliche Wahrheit, die `actions._section_sim_context` als
   `earlier_parts` als Hindernis stellt: bei „abschnitt" die **Position in Druckreihenfolge**
   (`plan.sections` liegt in Druckreihenfolge; jedes Teil davor steht real als Hindernis —
   innerhalb einer Reihe monoton mit der Reihenfolge), bei „modul" **0 für alle** (am
   Workstation-Druckort steht kein früheres Teil, ADR-022). **Begründung des Hindernislast-
   Terms:** die hindernislastigste Zelle ist die collision-anfälligste; ein „frei"-Urteil auf
   ihr deckt die Reihe in der **sicheren** Richtung (S6-Lehre) — anders als die kinematische
   Marge, die den dominanten Kollisionstreiber gar nicht sieht.
2. **Stich = zuletzt gedruckt.** Bei Gleichstand der Hindernislast (konstruktiv bei „modul";
   0 für alle) `max(order)` statt `min(order)` — die zuletzt gedruckte Zelle, nicht die
   hindernisärmste erste.
3. **Kein margenloser Repräsentant.** Zellen ohne erreichbare Pose (`kinematic_margin is
   None`) sind aus der Wahl ausgeschlossen (`_has_reachable_pose`). Ist **keine** Zelle der
   Reihe erreichbar, erbt die Reihe kein „frei", sondern den **ehrlichen Nicht-Urteils-
   Zustand** `unknown` mit neuem Grund `REASON_UNREACHABLE` (Muster des „ungeprüft"-Zustands
   aus #170) — nie ein Urteil von einer eingefrorenen Trajektorie.
4. **Override-Zellen ausgenommen.** Zellen mit eigenem Platzierungs-Override (`job
   ["section_overrides"]`) sind von der Vererbung ausgenommen: sie werden **selbst geprüft**
   (eigener Repräsentant, falls erreichbar) oder als `unknown`/`unreachable` ausgewiesen, und
   sie werden **nie** Repräsentant für Nachbarn (ihr Urteil gilt einer anderen Platzierung).

`representative_by_row` gibt jetzt `section_id → section_id | None` zurück (None = kein
gültiger Repräsentant); `combine_printability` setzt dafür `unknown`/`unreachable`.
`_decompose_printability` (actions.py) sammelt die Override-IDs aus dem Job, reicht sie
durch und ruft die Prüf-Tür nur für die echten (nicht-None) Repräsentanten. Schema additiv:
`reason`-Enum um `unreachable` erweitert (Altläufe byte-gleich). Viewer: Typ + eigener
„ungeprüft: keine erreichbare Zelle in der Reihe"-Titel (`printability-state.ts`), rein
ableitend (ADR-007). Alles Befund, kein Gate (ADR-013).

**Validierung gegen den vollen Befund (neuer Slow-Test, Akzeptanz #174).**
`test_vererbung_orakel.py` (`slow`, ~105 s, selbst-enthalten mit echter Roboter-Geometrie,
Muster des 16/16-Orakels aber ohne Denkmal): eine **nicht-zu-dicke** 150-mm-Wand (D ≈
181 mm ⇒ Freigang schweigt, Stufe 2 läuft) in **eine Reihe mit drei Zellen**. Ergebnis, das
den Fix belegt: der Repräsentant ist **abschnitt-3** (zuletzt gedruckt, 2 frühere Teile als
Hindernis), voller Befund **kollidiert** (n_red = 4106); abschnitt-2 (1 früheres Teil)
kollidiert ebenfalls (4108); **abschnitt-1 (0 frühere Teile) ist frei** (n_red = 0). Die
**alte** Wahl hätte abschnitt-1 (hindernisärmste, `min(order)`) gekürt und die Reihe
fälschlich „frei" erben lassen — die zwei real kollidierenden Zellen wären grün gewesen (die
B10-Falle auf Reihenebene). Die neue Wahl erbt korrekt „kollidiert". Der Test dokumentiert
jede Abweichung geerbt↔voll als Testbefund (hier: abschnitt-1 geerbt-kollidiert vs. real-frei
— **sichere** Richtung, erwartet) und prüft hart nur die ehrlichen Verträge: der Repräsentant
stimmt mit seinem eigenen vollen Befund überein, und **kein** geerbtes Urteil ist grün, wo
der volle Befund kollidiert (die gefährliche Richtung falsch-grün).

**Alternativen (verworfen).** (a) Hindernislast als **Anzahl geometrisch naher** früherer
Teile statt aller früheren — mehr Rechenaufwand, und „alle früheren Teile" ist genau die
Hindernis-Wahrheit, die die Simulation ohnehin stellt (kein Proxy nötig). (b) Override-Zellen
**gar nicht** prüfen (nur `unknown`) statt selbst prüfen — verschenkt ein ehrlich
erreichbares Urteil; das Issue erlaubt „selbst geprüft ODER ungeprüft", Selbstprüfung ist
ehrlicher. (c) Für „keine erreichbare Zelle" `REASON_NO_GEOMETRY` wiederverwenden — verwischt
die Ursache (Prüf-Tür unzuständig ≠ Reihe unerreichbar); ein eigener Grund ist die ehrliche
Wahl (Kern der Welle). (d) Die kinematische Marge als **zweiten** Term behalten — sie sieht
den Kollisionstreiber nicht und würde die klare Hindernislast-Regel nur verwässern.

**Tests.** Core: `test_printability.py` (5 Bestandstests der alten Marge-Regel auf die neue
Hindernislast-/Stich-/Reachability-Regel nachgezogen + neu: Override-Ausschluss, Modul-Stich
zuletzt-gedruckt, Reihe-ohne-Repräsentant ⇒ `unreachable`), `test_decompose.py` (5
Pipeline-Aktions-Naht-Tests je Regel mit konstruiertem 2×3-Mehr-Zellen-Szenario, gemockte
Prüf-Tür, die die Auswahl protokolliert), `test_vererbung_orakel.py` (der Slow-Orakel-Test).
Viewer: `printability-state.test.ts` (+1 `unreachable`-Titel). Die Denkmal-Stufe-2-Tests
(`test_printability_denkmal.py`, `slow`) bleiben unberührt (alle 16 Module rot — die Wahl
ändert nur, *welche* Zelle je Reihe geprüft wird, nicht das all-rot-Ergebnis). ruff/pytest/
tsc/build grün.

## 2026-07-11 — Gemeinsamer Urteils-Helper + zwei Orakel der gefährlichen Richtung (#176, Ehrlichkeits-Welle, Befunde B3/B6/B8)

**Frage.** Die Zwischenkritik 2026-07-10 fand drei zusammenhängende Lücken an der
Naht Prüf-Tür ↔ voller Befund: (B6) beide Türen duplizieren den `find_collisions`-
Urteils-Aufruf samt urteilsrelevanter Parameter **wörtlich** — schaltet eine spätere
Scheibe (z. B. #181) an einer Seite die Selbstkollision zu, altern die Prüfungen
auseinander, mit Fehlerrichtung „frei" auf der Tür-Seite; (B3) das 16/16-Orakel
exerziert die **gefährliche Richtung** (voll rot / Tür frei durch Travel-Ausdünnung)
nie — alle 16 Module sind durch **unausgedünnte** Druck-Samples rot; (B8) der
Freigang-Akzeptanznachweis ist **tautologisch** — die „druckbaren" Dicken werden aus
denselben `L`/`R` konstruiert, gegen die das Kriterium prüft, der Kern-Vertrag „`D`
überschätzt die real druckbare Tiefe" ist damit unverifiziert.

**Entscheidung (V9).** (1) Der duplizierte Urteils-Aufruf wandert in **einen**
Helper `fgc.collision.finding._run_finding(inp, link_frames, sample_layers)` — er
führt `find_collisions` mit den urteilsrelevanten Parametern (Selbstkollision aus,
Sicherheitsabstand, Endeffektor am TCP) aus; **nur die Sample-Auswahl** parametrisiert
ihn. Voller Befund reicht alle Samples, die Prüf-Tür die Travel-ausgedünnten. Beide
können nicht mehr auseinanderaltern. Die **Sample-Rückrechnung/Indizierung** (`kept`,
`thin_travel_indices`) bleibt bewusst beim jeweiligen Aufrufer — Naht zu #181, das den
Kollisions-ORT additiv an der Prüf-Tür ergänzt, ohne diesen geteilten Kern zu berühren.
(2) Zwei **markierte Slow-Tests** (`test_prueftuer_gefahrrichtung.py`) exerzieren die
gefährliche Richtung **echt** (konstruiert, echte Roboter-Geometrie, derselbe
`find_collisions` wie im Produktivpfad; ~3 s zusammen; skippen ohne Kollisions-Geometrie).

**Travel-Kipp (B3/B6).** 14 Samples, ein Travel-Lauf (2..11), Ausdünnung `stride=5`
behält im Lauf nur 2/7/11. Ein Hindernis genau an der Spitzenpose des **ausgedünnten**
Samples 4 ⇒ voller Befund **rot** (n_red=1, nur Sample 4), Prüf-Tür `stride=5` **frei**
(überspringt es), `stride=1` **rot** (isoliert die Ausdünnung als alleinige Ursache). Die
Abweichung wird per `capsys` **sichtbar dokumentiert** (nicht wegdefiniert): sie ist die
eine Konstellation, in der die Ausdünnung kippt (sie entfernt rote Samples, fügt nie
welche hinzu ⇒ jede Abweichung ist zwingend „voll rot / Tür frei").

**Freigang-Orakel (B8, non-tautologisch).** Eine Wand **dünner** als `D` (200 mm <
`D`=`L`+`R`=260 mm ⇒ Freigang stumm, kein „zu dick") ist laut **unabhängigem** vollem
Kollisionsbefund dennoch nicht einseitig druckbar: der übergreifende Arm taucht 347 mm
ins eigene, bereits feste Material (`current_part`, Glied 6) — genau die vom Freigang-
Modell **ignorierten** Armglieder/Übergriff. Damit ist erstmals belegt, dass `D` die real
druckbare Tiefe **überschätzt** (sichere Fehlerrichtung: Freigang unter-erkennt
Unmöglichkeit, nie umgekehrt). Der volle Befund ist unabhängig von `L`/`R` — der frühere
Zirkelschluss ist durchbrochen.

**Alternativen (verworfen).** (a) Nur die **Verdrahtung** (Sicherheitsabstand) als
Konstante teilen statt des ganzen Aufrufs — B6 nennt genau das Zuschalten der
Selbstkollision als künftigen Drift-Trigger; der Aufruf selbst muss geteilt sein. (b)
Sample-Auswahl/Rückrechnung **in** den Helper ziehen — verwischte die für #181 nötige
saubere Trennung Urteils-Kern ↔ Ort/Indizierung; die Rückrechnung bleibt lokal beim
Aufrufer. (c) Den Travel-Kipp per realem Denkmal-Gegenbeispiel zeigen — an echten Daten
nicht demonstrierbar (dort dominieren Druck-Kollisionen, ADR-Anhang der Zwischenkritik);
der konstruierte Fall ist die Verifizierer-Skizze, deterministisch und aussagekräftiger.
(d) Das Freigang-Orakel über die real fehlende Denkmal-Wand fahren (skippt hier) statt
selbst-enthalten — ein Test, der nur skippt, verifiziert nichts; selbst-enthalten mit
echter Geometrie läuft überall mit `[geo]`.

**Kein README-Abschnitt** (interner Helfer + Orakel-Tests, keine neue Nutzerfunktion —
wie #169). **Verifikation.** Bestehende Äquivalenz-Tests (`test_collision_finding.py`)
**unverändert** grün — Wächter, dass sich außer der Struktur nichts geändert hat; die
zwei neuen Slow-Tests grün (`-m slow -k "travel_thinning or freigang_D"`); ruff clean;
Core-Standard-Suite 790 passed / 3 skipped.

---

## 2026-07-11 — „zu dick" ehrlich: vermutlich statt Gewissheit, provisorischer TCP nie „sicher unmöglich" (#177, Ehrlichkeits-Welle, Befunde B7/B9)

**Frage.** Das Freigang-Urteil `too_thick` (#163/#164) war eine geprüfte **Gewissheit**
(`presumed=False`, alle Teile rot-sicher, die falsifizierende Prüf-Tür entfiel). Es ist
aber **höhenblind** (kennt weder Wandhöhe noch Aufstellung) und rechnet zudem mit dem
TCP des Endeffektors, der **provisorisch** (geschätzt, nicht am Gerät vermessen, #136)
sein kann. Beides kann ein falsches Rot als Gewissheit erzeugen, dessen Falsifikation
nie läuft — das gespiegelte „16/16 ✓"-Problem (Zwischenkritik B7, B9). Wie macht man
`too_thick` ehrlich, **ohne** die eigentliche Wandhöhen-Wache (**#167**) hier zu bauen?

**Entscheidung.**
1. **`too_thick` ist jetzt `presumed=True`** — „vermutlich zu dick", nie geprüfte
   Gewissheit, solange #167 fehlt. Der vorhandene `presumed`-Mechanismus (#164:
   „nicht an diesem Teil selbst geprüft / vermutlich") wird konsistent
   **erweitert**: bisher trug ihn nur ein geerbtes Reihen-Urteil, jetzt auch das
   höhenblinde Freigang-Urteil. Viewer-Anzeige (blasser hohler Punkt + kursives
   „vermutlich"-Badge) greift dadurch automatisch; `representative_id` bleibt `None`
   (kein Prüf-Tür-Repräsentant — unterscheidbar vom Reihen-Erben).
2. **Vorläufigkeits-Feld `tcp_provisional`** durch das Befund-Schema: `FreigangCheck`
   (wand-weit) und `PartPrintability` (je Teil) tragen es; `_freigang_finding` liest
   `tool.tcp_provisional`. Bei provisorischem TCP entsteht kein „sicher unmöglich" —
   das Urteil ist ohnehin `presumed`, das Feld weist die Vorläufigkeit **zusätzlich
   sichtbar** aus (Label „· TCP vorläufig", Tooltip). Additiv, nur bei `True`
   serialisiert (Altläufe/bestätigter TCP byte-gleich, Muster wie `reason`/`reachable`).

**Prüf-Tür-Überspringen (Akzeptanzpunkt 2) — bewusste Wahl: weiter überspringen, aber
als „vermutlich, ungeprüft" ausgewiesen.** Alternative wäre, bei `too_thick` doch die
teure Prüf-Tür zu fahren. Verworfen: der ganze Wert des Freigang-Kurzschlusses (#163)
ist, die ~71 s-Kollisions-Simulation (B14) im klaren Fall zu **sparen** (Denkmal:
16 Module in ~1–2 s ohne Simulation); sie wieder anzuschalten würde #163 aushebeln.
Das Überspringen ist legitim, solange es **ehrlich** ist: `presumed=True` sagt genau
„vermutlich, nicht selbst geprüft" — Befund statt Gate (ADR-013), nicht ersatzloses
Übergehen. Die echte Falsifikation ist die Wandhöhen-Wache **#167**, die separat bleibt.

**Alternativen (verworfen).** (a) Ein **eigenes** Vermutungs-Feld für Höhenblindheit
statt `presumed` wiederzuverwenden — verworfen: der Auftrag verlangt den vorhandenen
Mechanismus konsistent zu nutzen, und die Anzeige-Semantik ist identisch („nicht selbst
geprüft"). (b) Bei `tcp_provisional` den Freigang-Befund **unterdrücken** (kein
`too_thick`) — verworfen: das `L` aus einem geschätzten TCP ist immer noch die beste
verfügbare Zahl; ein sichtbar-vorläufiger Befund ist ehrlicher als gar keiner (der
Auftrag erlaubt „Feld ODER unterbleibt" — Feld gewählt). (c) `tcp_provisional` auch auf
den Prüf-Tür-Pfad (collides/printable) durchreichen — außer Scope (#177 betrifft das
Freigang-/`too_thick`-Urteil; die Prüf-Tür-TCP-Vorläufigkeit ist ein eigenes Thema).

**Verweis.** Die eigentliche Wandhöhen-Wache bleibt **#167** (hier nur referenziert, nicht
umgesetzt). Verwandt: der Modul-Export misstraut `tcp_provisional` bereits (`actions.py`
Gate), das Freigang-Kriterium zieht damit nach.

**Verifikation.** Core: `test_printability` (too_thick jetzt `presumed=True` +
`tcp_provisional`-Serialisierung), `test_freigang` (Aktions-Naht: provisorischer TCP ⇒
Vorläufigkeit durchgereicht, kein Gewissheits-Rot; Schema-Validierung), Denkmal-Slow-Test
(`presumed=True`) nachgezogen. Viewer: `printability-state` (Anzeige „vermutlich zu dick"
+ „TCP vorläufig"). Schema `decompose.schema.json` additiv um `tcp_provisional` (freigang +
printability). ruff/pytest/tsc/build grün.

---

## 2026-07-11 — Prüf-Vorbehalte durchreichen + Kollisionsbadge mit Veraltet-Ableitung (#182, Ehrlichkeits-Welle, Befunde B15/B37/B38)

**Frage.** #177 (oben) hat bewusst offengelassen, ob `tool_provisional` (die
Prüf-Tür-eigene Vorläufigkeit — der Endeffektor lief als provisorische Hülle) auf den
Prüf-Tür-Pfad (`printable`/`collides`) durchgereicht wird. Dieselbe Lücke betrifft
`travel_thinned`/`n_checked`/`n_samples`: die verdünnte Prüf-Tür (`check_part_clearance`,
#162, ADR-024 S5-Hebel) prüft nur jedes `travel_stride`-te Travel-Sample und rechtfertigt
das intern gerade damit, dass Travel „nicht lückenlos geprüft" markiert sei — aber
`combine_printability` liest aus dem `ClearanceVerdict` bislang nur `collides`/
`causer_link`/`causer_against`/`penetration_mm`/`min_distance_mm`, die Ehrlichkeits-Felder
gehen beim Verheiraten verloren. Ein Tür-„frei" sieht damit stärker aus, als es ist —
während derselbe Vorbehalt im Kollisionsbefund des Players (`travel_not_continuously_checked`)
längst prominent steht. Zusätzlich: das Palette-Kollisionsbadge entwertete nur hart über
das lokale `dirty`-Flag (#172/B20) statt über dieselbe Veraltet-Ableitung
(`sectionStageStatus`/`isStale`, `staleness.ts`) wie Druckplan-/Simulation-/Export-Badge —
und eine Neu-Zerlegung leerte die je Teil gemerkten Kollisionsbefunde nicht, obwohl
`section_id`s ordnungsbasiert vergeben werden und sich wiederholen können.

**Entscheidung.**
1. **Prüf-Vorbehalte additiv durchreichen.** `PartPrintability` bekommt vier neue
   Felder (`travel_thinned: bool`, `n_checked`/`n_samples: int | None`,
   `tool_provisional: bool`), `combine_printability` liest sie per `getattr` vom
   Repräsentanten-`ClearanceVerdict` (Default `False`/`None` — Doubles ohne die Felder
   bleiben kompatibel) und vererbt sie mit dem übrigen Urteil an die ganze Höhenreihe
   (dieselbe Prüfung galt für alle Erbenden). Nur bei einem echten Prüf-Tür-Urteil
   gesetzt — `too_thick` hat keine Prüf-Tür gesehen, die Felder bleiben `False`/`None`.
   `to_dict()` schreibt additiv (nur was zutrifft/gesetzt ist, Altläufe byte-gleich);
   Schema `decompose.schema.json` entsprechend erweitert (`additionalProperties: false`
   verlangt das). Viewer: `printabilityCaveats` (`ui/printability-state.ts`) baut daraus
   dieselbe Wortwahl wie `collisionCaveats` (#156) — „Travel nicht lückenlos geprüft",
   „n von m Samples geprüft", „Endeffektor-Hülle provisorisch" — und hängt sie an den
   Tooltip von `printable`/`collides`.
2. **Kollisionsbadge veraltet über `sectionStageStatus`.** `paletteEntries` bekommt ein
   optionales `revisions`-Feld; das Kollisions-Badge trägt zusätzlich `stale` aus
   `isStale(sectionStageStatus(revisions, sectionId, "simulation"))` — derselben
   Ableitung wie die Stufen-Badges. `dirty` entwertet weiterhin hart auf `null` (#172
   bleibt Vorrang: der alte Befund gälte einer Form, die sich mitten im Edit noch
   ändern kann); erst danach greift die feinere Stale-Markierung. Bleibt **sichtbar**,
   wird nur markiert (`.stale`-Klasse + Tooltip-Zusatz) — konsistent zum
   „veraltet bleibt sichtbar" Prinzip (viewer/CONTEXT.md), keine neue Löschung.
3. **Neu-Zerlegung leert die gemerkten Befunde.** `clearedCollisionFindings()`
   (`ui/collision-state.ts`, immer `{}`) wird im `onDecompose`-Pfad aufgerufen — der
   Zwilling des bereits bestehenden Musters beim Projekt-Öffnen (`collisionFindings.clear()`
   + `setCollisionFindings({})`), jetzt auch für „✦ Automatisch vorschlagen" gezogen.

**Alternativen (verworfen).** (a) Das Kollisionsbadge bei `dirty` NICHT mehr hart auf
`null` setzen, sondern durchweg über `stale` — verworfen: der `dirty`-Fall deckt eine
Situation ab, in der sich die Abschnitts-**Form** selbst noch ändern kann (laufendes
Edit), das ist eine härtere Unsicherheit als „Parameter seit der letzten Simulation
geändert" und der bestehende Regressionsanker (#172/B20) soll nicht aufgeweicht werden.
(b) `travel_thinned`/`tool_provisional` auch bei `too_thick` (aus dem Freigang-Pfad)
tragen — verworfen: die Prüf-Tür wird dort gar nicht aufgerufen (#163-Kurzschluss), ein
gesetztes Feld würde einen Prüf-Tür-Kontakt vortäuschen, den es nie gab. (c) Ein
Filter statt Voll-Leerung der Kollisionsbefunde bei Neu-Zerlegung (nur wirklich
wiederverwendete IDs räumen) — verworfen: unnötig fein für den Nutzen; die Voll-Leerung
ist bereits das etablierte Muster beim Projekt-Öffnen und garantiert Kollisionsfreiheit
mit alten Ständen ohne zusätzliche ID-Abgleichslogik.

**Verweis.** Blocked-by #170 (Urteils-Struktur/Palette-Module, hier wiederverwendet).
Aufbauend auf #180 (Ampel-Konjunktion), #171 (Effektive-Platzierung-Selektor), #172
(Advisor-Invalidieren/Revisions-Signal, hier für `druckplanPanel.setRevisions`
wiederverwendet). `tool_provisional` ergänzt die in #177 bewusst ausgesparte
Prüf-Tür-Vorläufigkeit (dort nur `tcp_provisional`, Freigang-Kanal).

**Verifikation.** Core: `test_printability` (Pass-through auf Repräsentant + Reihe,
Byte-Gleichheit ohne Vorbehalte, `too_thick` trägt nie Prüf-Tür-Vorbehalte); Schema
additiv erweitert. Viewer: `printability-state.test.ts` (`printabilityCaveats` +
Tooltip-Integration), `parts-palette-state.test.ts` (Stale-Ableitung mit/ohne
`revisions`, dirty bleibt Vorrang), `collision-state.test.ts` (`clearedCollisionFindings`).
`npm test`/`npm run build` grün (933 Tests); `ruff check core` clean, Core-Suite
(`test_decompose.py`/`test_printability.py`) 114 passed.

## 2026-07-11 — Stufe-2-Prüf-Tür raus aus dem interaktiven Loop: expliziter Anstoß/async + Cache + Sperre freigeben (Issue #175, PRD #168)

**Frage.** Die teure Stufe-2-Prüf-Tür (Druckbarkeit je Höhenreihe, #162/#164) lief
bislang **im** `POST …/decomposition` mit — bei jedem Schnitt-Edit synchron, unter der
Projekt-Sperre, ohne Cache, ohne Fortschritt (Befund B14: ~71 s Editor-Freeze je Edit).
Nutzer mieden dadurch das Prüfen; die Ehrlichkeits-Funktion sabotierte ihre eigene
Nutzung (Karten-Zielmarke #139: Fokus-Teil ≤ ~10 s, Wand im Hintergrund). Wie entkoppeln,
ohne das „Befund, kein Gate / kein stilles Grün"-Prinzip (ADR-013) zu verletzen?

**Erwogene Alternativen.**
- (a) *Nur schneller machen* (weiter im Loop, aber mit Cache) — verworfen: der erste,
  ungecachte Lauf friert weiterhin ~71 s; das eigentliche Problem ist die **Kopplung**
  an den Edit, nicht allein die Kosten.
- (b) *Ein neues Output-Stage `pruef` in der geteilten `OUTPUT_DEPS`/`output_status`* für
  die Veraltung des Prüfstands — verworfen: die Reiter-Verträge prüfen `output_status`
  byte-genau (`==`-Dicts in test_export/test_project); ein neuer Schlüssel bräche sie.
  Stattdessen ein **eigener Marker** `print_job.last_pruef` mit Eingabe-Schnappschuss +
  reine Ableitung `pruef_status` (Parität `revisions.py` ↔ `ui/pruef-check-state.ts`),
  self-contained, ohne die geteilte Maschinerie zu stören.
- (c) *FastAPI `BackgroundTasks`* für den Async-Lauf — verworfen: laufen nach der Antwort,
  **ohne** Fortschritts-/Abbruch-Griff. Der Viewer braucht beides → kleiner In-Process-
  Registry `checkjobs` (start/get/cancel), Single-Process wie der Projekt-Lock (ADR-018).
- (d) *Persistenz der Stufe-2-Ergebnisse in einem eigenen Artefakt* — verworfen: der
  bestehende Zerlegungslauf (`decompose.json`, `sections[].printability`) ist die richtige
  Stelle; der Check schreibt ihn über `propose_decomposition(printability_override=…)`
  **wieder** und erbt so alle Artefakt-/Veraltungs-Pfade (kein Zweitschema).

**Entscheidung.**
1. **Split.** `propose_decomposition` (interaktiver Loop) rechnet nur noch **Stufe 1**
   (`_decompose_printability_stage1`: too_thick-Kurzschluss gratis, sonst jedes Teil ehrlich
   `unknown/reason="unchecked"` — neuer Grund, nie stilles Grün). Die teure **Stufe 2**
   (`_decompose_printability_stage2`) läuft nur in der neuen Aktion `check_decomposition`.
2. **Cache je (Schnitt, Platzierung, Parameter).** Prozessweiter `_PRUEFTUER_CACHE`, Schlüssel
   = `_plan_pruef_signature` (alle Zellgeometrien + Platzierungen + `process_params` + Roboter/
   Endeffektor/Workstation/Zerlegungsart + Travel-Stride) × `section_id`. Unveränderter Stand
   ⇒ 0 Neurechnungen (nachweisbar per Test: `n_computed`/`n_cached` in `PruefStats`). Jede
   Änderung ⇒ andere Signatur ⇒ Miss. FIFO-gedeckelt.
3. **Sperre nicht über die Rechenzeit.** `check_decomposition` in drei Phasen: kurz sperren
   (laden/rekonstruieren + Eingabe-Schnappschuss), **ohne** Sperre rechnen (Cache/Fortschritt/
   Abbruch), kurz sperren (Supersede-Wächter — Eingaben unverändert? — dann persistieren). Ein
   paralleler Schreibzugriff während der Rechnung ⇒ `superseded` (kein Lost-Update auf frische
   Edits) statt stiller Überschreibung.
4. **Async + Fortschritt + Abbruch.** Hintergrundlauf-Registry `fgc.pipeline.checkjobs`
   (Daemon-Thread je Lauf, `should_cancel`/`on_progress`/`on_scope`); Routen `POST …/
   decomposition-check`, `GET …/{check_id}`, `POST …/{check_id}/cancel`.
5. **Fokus = Default, Umfangsansage für Global.** `check_decomposition(focus_section_id=…)`
   prüft nur die Reihe des Fokus-Teils (schnell); global prüft alle Reihen. `propose`-Antwort
   trägt `pruef_scope` (N Repräsentanten + ~s) für die bewusste Wahl „prüft N Abschnitte, ~…".
6. **Sichtbarer letzter Prüfstand.** `print_job.last_pruef` (scope global/focus + section_id +
   Eingabe-Schnappschuss); `pruef_status` leitet „veraltet?" gegen die aktuellen `revisions`
   ab (dieselbe #172/#182-Logik: Prüf-Eingaben + `section_total`).

**Begründung.** Die Entkopplung ist die riskanteste Änderung der Ehrlichkeits-Serie
(Async, Cache-Invalidierung, Sperr-Freigabe, Abbrechen). Der Split hält den interaktiven
Pfad billig (Stufe 1 ist gratis) und **ehrlich** (unchecked ist sichtbar, kein stilles
Grün, ADR-013); der Cache macht Wiederholungen/Fokus nach einem Edit billig; die
Phasen-Sperre erhält parallele Bearbeitung; der Supersede-Wächter verhindert Lost-Updates
ohne die Sperre lange zu halten. Der `last_pruef`-Marker macht den Prüfstand sichtbar
veraltbar, ohne die byte-genauen `output_status`-Verträge anzufassen.

**Verworfen (Details).** Das Rechnen im Check-Thread nutzt denselben `_clearance_verdict_for_section`
wie zuvor (kein zweiter Rechenpfad); `check_decomposition` persistiert bewusst über
`propose_decomposition` (Reuse aller Artefakt-/Revisions-Pfade) statt eines eigenen Writers.
Über-Invalidierung des Caches (ein Edit an einer oberen Zelle verwirft auch untere) bewusst
in Kauf genommen: der Hauptnutzen ist „Wiederprüfung ohne Edit = sofort" + „Fokus nach Edit
billig", nicht feingranulare Teil-Invalidierung (die `earlier_parts`-Kopplung machte sie
unsicher).

**Verifikation.** Core: `test_pruef_check.py` (Stufe-1-Ruhezustand ohne Prüf-Tür-Aufruf,
Cache-Treffer rechnet 0, Invalidierung bei Platzierungsänderung, Fokus-Scope, Abbrechen,
Fortschritt, End-to-end Entkopplung + Umfangsansage, `last_pruef` global/Fokus,
Supersede bei parallelem Schreibzugriff, Hintergrundlauf); bestehende Suites
(`test_printability`/`test_vererbung_orakel`/`test_project`/`test_export`/
`test_workstation_choice`) grün; `ruff check core` clean. Viewer: `pruef-check-state.test.ts`
(pruefStatus-Parität, Umfangsansage, Fortschritt/Terminalzustände, letzter Prüfstand) +
`printability-state.test.ts` (unchecked-Grund) — 951 Tests, `tsc`/`vite build` grün.

## 2026-07-11 — Kollisions-ORT der Prüf-Tür: Original-Index, Schicht, Verursacher-Position, rote Intervalle (Issue #181, Ehrlichkeits-Welle, Befund B24, Vorarbeit #165)

**Frage.** #165 (Textbaustein N1 des Berichts) will eine kollidierende Zelle „entlang
der Verursacher-Achse teilen, keine Heuristik" — dafür muss die Prüf-Tür
(`check_part_clearance`/`ClearanceVerdict`, #162) mehr liefern als nur das eine
schlimmste Sample: einen Ort. Zwei Lücken (Befund B24): (1) `ClearanceVerdict.
causer_link`/`causer_against` benennen nur *welches* Glied gegen *was*, nicht *wo*
(Weltposition) und nicht *wann* (Schicht) — beide werden intern in `find_collisions`
ohnehin berechnet (Glied-Frames je Sample, `sample_layers`) und bislang weggeworfen.
(2) Der `worst_index` von `check_part_clearance` zeigt auf die **Travel-ausgedünnte**
Sample-Liste (#162, S5-Hebel) — ohne Rückrechnung ist er auf die Bahn (Toolpath/
Trajektorie, Original-Indizierung) nicht rückführbar, genau der Blindfleck, den #165
sonst geerbt hätte. Blocked-by #176 (gemeinsamer Urteils-Helper), der den geteilten
`_run_finding`-Kern zwischen vollem Befund und Prüf-Tür fixiert hat — dieser Kern
bleibt hier unangetastet, der Kollisions-Ort wird ausschließlich am Prüf-Tür-Aufrufer
(`check_part_clearance`) ergänzt.

**Entscheidung.**
1. **Rückrechnung als eigene, getestete Funktion.** `finding.original_sample_index
   (kept, thinned_index)` macht `thin_travel_indices`s Ausdünnungs-Abbildung explizit
   umkehrbar: Position `j` im `kept`-Rückgabewert *ist* bereits die Abbildung (Wert =
   Original-Index), die neue Funktion macht das nur robust (kein `IndexError`, `None`
   außerhalb `[0, len(kept))` — der `-1`-Sentinel eines Berichts ohne endlichen Abstand
   ist der Hauptfall). Gezielt an den Rändern getestet (Anfang **und** Ende eines
   Travel-Laufs bleiben laut `thin_travel_indices`-Vertrag immer erhalten — genau dort
   weicht Ausdünnungs- von Original-Index typischerweise am stärksten ab).
2. **Verursacher-Position im Teil-System, ohne den Urteils-Kern zu berühren.**
   `_causer_position_mm(base, link_frames, causer_link, tcp_frame)` (neu, rein, kein
   Geo) verkettet `transform.compose(base, link)` — dieselbe eine Transformationsstelle
   wie `find_collisions` intern (ADR-006), hier nur auf **einen** Frame statt die ganze
   Bahn angewendet, in `check_part_clearance` NACH dem geteilten `_run_finding`-Aufruf.
   `base` (Basis im Teil-/Wandsystem) macht `compose(base, link)` bereits zur
   Teil-System-Position — kein zusätzlicher Umrechnungsschritt nötig. Endeffektor-
   Verursacher (`TOOL_INDEX`) verketten zusätzlich den TCP-Frame (derselbe `world_tcp`
   wie `print_point` in `check.find_collisions`).
3. **`ClearanceVerdict` bekommt vier neue Felder** (additiv, alle mit Default
   `None`/leer): `worst_original_index`, `worst_layer` (aus `sample_layers`, derselben
   Toolpath-Bisektion wie der volle Befund), `causer_position_mm`, `red_intervals`
   (neue `RedInterval`-Dataclass: `link`/`against`/`start_index`/`end_index`/
   `worst_index`, alle Original-indiziert, plus `min_distance_mm` — **alle** roten
   Intervalle statt nur des schlimmsten Samples, der eigentliche Hebel für #165s
   „Teilen entlang der Achse"). `from_report` nimmt die Zusatzargumente optional
   (`kept`/`link_frames`/`sample_layers`/`base`/`tcp_frame`) — ohne sie (hypothetischer
   Altaufrufer) bleiben Schicht/Position `None`, der Index fällt auf Identität zurück
   (keine bekannte Ausdünnung ⇒ kein Sample übersprungen). `to_dict()` trägt sie
   unconditional (wie die bestehenden Verursacher-Felder — `ClearanceVerdict` ist kein
   schema-validiertes Artefakt).
4. **`PartPrintability`/`decompose.schema.json` additiv mitgezogen** — konsistent mit
   #182s Präzedenzfall (`travel_thinned`/`n_checked`/`n_samples`/`tool_provisional`):
   `combine_printability` liest die vier neuen Felder per `getattr` vom
   Repräsentanten-`ClearanceVerdict` und vererbt sie mit dem übrigen Urteil an die
   ganze Höhenreihe; `to_dict()` schreibt additiv (nur was gesetzt ist, Altläufe/
   `too_thick`/`unknown` bleiben byte-gleich); Schema entsprechend erweitert
   (`additionalProperties: false` verlangt das explizit, `red_intervals` als
   Array-of-Objects mit eigenem `additionalProperties: false`).

**Alternativen (verworfen).** (a) Den Original-Index direkt in `check.find_collisions`/
`CollisionReport` mitführen — verworfen: der geteilte Urteils-Kern (#176) kennt die
Ausdünnung gar nicht (die Sample-Auswahl bleibt bewusst beim Aufrufer, s.
`_run_finding`-Docstring); die Rückrechnung gehört an die Prüf-Tür, die die Ausdünnung
vornimmt. (b) Die Positions-Berechnung in `check.find_collisions` selbst mit ausgeben
(dort wird `world`/`print_point` je Sample ohnehin berechnet) — verworfen: würde die
geteilte, gut abgehangene Kernfunktion anfassen und die Rückgabestruktur für den
vollen Befund (`build_section_finding`) unnötig aufblähen, der diese Position nicht
braucht; eine schlanke Neuberechnung für **ein** Sample in `finding.py` (rein, kein
Geo) ist billig und hält den Kern unberührt. (c) `red_intervals` ungefiltert (alle
Status, nicht nur rot) mitführen — verworfen: #165 braucht ausschließlich die
kollidierenden Bereiche, gelb/grün blähen die Nutzlast ohne Hebel für die
Achsen-Teilung auf.

**Verweis.** Blocked-by #176 (gemeinsamer Urteils-Helper, hier wiederverwendet, nicht
verändert). Bleibt konsistent mit #182s Feldern (`travel_thinned`/`n_checked`/
`n_samples`) — dieselbe Travel-Ausdünnung, an der auch die hiesige Rückrechnung hängt.
Vorarbeit für #165 (Teilen entlang der Verursacher-Achse).

**Verifikation.** Core: `test_collision_finding.py` (Rückrechnung inkl. Rand-Fällen
Anfang/Ende eines Travel-Laufs, synthetischer `from_report`-Test für Ort/Schicht/
Position/Intervalle, Additivität ohne die neuen Argumente, konstruierte Kollisionen an
Innen- und Randpositionen eines Travel-Laufs über die echte `check_part_clearance`,
Fall ohne Kollision ⇒ Ort bleibt leer); `test_printability.py` (Ort wird an
Repräsentant **und** erbende Reihe durchgereicht, bleibt byte-gleich ohne bekannten Ort,
`too_thick` trägt nie einen Kollisions-Ort); `test_decompose.py` (Schema-Validierung
mit gesetztem Ort); `test_collision_advisor_action.py`
(`test_check_section_clearance_reports_collision_location`, `slow`, Pipeline-
Aktions-Naht: konstruierte, real kollidierende Testwand über `check_section_clearance`
— Ort und rote Intervalle plausibel gegen `n_samples`/`causer_link`/`causer_against`).
`ruff check core` clean; volle Kern-Suite grün.

## 2026-07-11 — `mitre_limit` als echte Kartenquelle statt Zwillings-Literal (Issue #2)

**Frage.** Issue #2 (Nachtrag zum S4-Befund) verlangt, `mitre_limit=2.0` explizit
an *allen* passenden `buffer(..., join_style="mitre")`-Stellen zu setzen und zu
prüfen, ob der Wert sinnvoll aus `materialcards/process_window.provisional.json`
bezogen werden kann (ADR-013, „eine Quelle für E1 und Slicer"). Der Fix selbst
(`shells.shell_rings`) stand bereits seit dem 2026-07-02-Eintrag oben im Code —
seither hat aber auch `fgc.eligibility.footprint.has_narrow_web` (E1-Stufe-2-
Stegcheck) denselben `mitre_limit=2.0` als **zweites, unabhängiges** Literal
bekommen. Genau das Muster, vor dem ADR-013 warnt (E1 und Slicer duplizieren
denselben Prozesswert), lag damit tatsächlich vor — nur eben nicht dokumentiert
entschieden.

**Alternativen:**
1. Status quo belassen: zwei inline `mitre_limit=2.0`-Literale (`shells.py`,
   `footprint.py`), je mit Kommentar auf den Spike. Einfach, aber genau die
   Divergenzgefahr, die ADR-013 vermeiden soll — ein künftiger Fix an einer
   Stelle vergisst leicht die andere.
2. Nur einen gemeinsamen Python-Konstanten-Import (z. B. `shells.DEFAULT_MITRE_LIMIT`
   in `footprint.py` importieren). Zentralisiert das Literal, verletzt aber
   `footprint.py`s bewusste Projekt-Import-Freiheit (Docstring: „ohne
   Projekt-Imports, damit sie einzeln testbar bleiben") und wäre eine
   Slicer→Eligibility-Kopplung in die falsche Richtung.
3. **Gewählt:** `mitre_limit` als Feld in `ProcessWindow` (Default aus
   `PROVISIONAL_DEFAULTS`, gespiegelt in `materialcards/process_window.provisional.json`)
   und in `SliceParams` (über `SliceParams.from_window`). `shell_rings()` und
   `has_narrow_web()` bekommen je einen neuen `mitre_limit`-Parameter mit
   Fallback-Default 2.0 (für Aufrufer ohne Karte, v. a. Tests) — die
   Produktionspfade (`build.build_toolpath`, `eligibility.rules.check_footprint`)
   reichen den Kartenwert jetzt explizit durch.

**Begründung.** `mitre_limit` wird — anders als `strand_width_mm` oder
`wall_thickness_min_mm` — nicht aus S1/Extruderversuchen gemessen; es ist eine
reine Offset-Robustheitszahl aus Spike S4 (notch-Familie), unabhängig von
Material oder Strangbreite (normiert). Es qualifiziert sich damit exakt wie
`default_shells`/`density_kg_m3` für den etablierten Karten-Pattern: einmal in
`PROVISIONAL_DEFAULTS` benennen, in `ProcessWindow` UND `SliceParams` spiegeln,
in der JSON-Karte referenzieren. Der Aufwand blieb vertretbar (zwei Aufrufer,
je eine Änderung an der einen Schreibstelle), weil beide Konsumenten
(`shell_rings` über `build_toolpath`/`SliceParams`, `has_narrow_web` über
`eligibility.rules`/`ProcessWindow`) bereits exakt eine Aufrufstelle im
Produktionscode haben — kein invasives Umbauen mehrerer Call-Sites nötig.
Anders als die S1-abhängigen Felder bleibt `mitre_limit` nicht `null`/wartend:
der Wert ist aus dem Spike bereits belastbar, nur eben (noch) nicht
mm-skaliert wie Strangbreite — das betrifft ihn nicht, da er dimensionslos ist.

**Verweis.** Ergänzt den 2026-07-02-Eintrag oben (dort der ursprüngliche
Code-Fix in `shells.py` + Regressionstest); ADR-013 (eine Quelle E1/Slicer).

**Verifikation.** `core/tests/test_slicer.py::test_mitre_limit_sourced_from_process_window_card`
(Karten-/Default-/`SliceParams`-Übereinstimmung, Muster analog
`test_module_limits.py::test_weight_uses_density_default_from_process_window_card`);
bestehender Regressionstest `test_shell_rings_survive_sharp_reflex_notch`
unverändert grün (Fallback-Default deckt sich weiter mit dem Kartenwert);
volle Kern-Suite + `ruff check core` grün, Viewer unberührt (kein
`mitre_limit`-Bezug dort).

## 2026-07-11 — Punktnummerierung der Bahn-/Anfahrpunkte, ein-/ausschaltbar (Issue #138)

**Frage.** Issue #138 (Nutzerwunsch Grill 2026-07-09) wünscht eine ein-/aus-
schaltbare Nummerierung der Slicer-Targets in der 3D-Ansicht, lässt aber vier
Fragen bewusst offen: welche Ansicht(en), welche Punkte, welche Darstellung
und wo der Schalter sitzt. Vor der Umsetzung stand der IST-Zustand: gibt es
bereits genau eine Toolpath-Darstellung, an die sich anschließen lässt, oder
mehrere konkurrierende?

**Befund im Code.** Es gibt genau **eine** Rendering-Klasse für Slicer-Targets
als Bahn: `ToolpathView` (`viewer/src/render/toolpath.ts`). Sie wird an drei
Stellen in `main.ts` instanziiert — Einzel-Lauf (`toolpathView`), aktives
Druckort-Modul (`moduleReplay.toolpath`) und Abschnitts-Sequenz
(`sequence.loaded[i].view`) —, aber immer dieselbe Klasse mit demselben
Layer-Slider-/Wachs-/Travel-Sichtbarkeitsmodell (`apply()`). Das bestehende
⚙-Menü am 3D-Feld (`viewer-settings.ts`/`viewer-settings-state.ts`, Issue
#159) trägt bereits eine benannte Sektion „Replay-Bühne" mit genau den vier
Schaltern, die auf dieselbe(n) `ToolpathView`-Instanz(en) wirken (Roboterarm,
Strang wächst mit, Wachsender Druckstand, Live-Abstandszahl) — der Code legt
die Antwort auf alle vier Triage-Fragen bereits nahe.

**Entscheidungen (den vier Triage-Fragen folgend):**

1. **Welche Ansicht(en):** die eine vorhandene `ToolpathView` — sie bedient
   Vorbereiten-Vorschau/Zerlegung/Slicing/Export (Einzel-Lauf), Simulieren-
   Replay (Modul- und Sequenz-Modus) gleichermaßen. Keine zweite Darstellung
   erfunden; ein gemeinsamer ⚙-Schalter wirkt auf jede gerade lebende Instanz.
   *Verworfen:* getrennte Schalter je Ansicht — hätte drei Häkchen für
   dieselbe Bahndarstellung bedeutet, ohne fachlichen Unterschied.
2. **Welche Punkte:** NICHT alle Targets (können tausende sein). Beschriftet
   werden der erste Punkt sowie jeder print/travel-Wechsel und jeder
   Ring-/Schichtanfang — `segment_id` (Core: `L{layer}_C{poly}_S{shell}_R{ring}`,
   der Anfahrpunkt zusätzlich `_approach`) ändert sich bei jedem dieser drei
   Ereignisse, ein Vergleich mit dem Vorgänger-Target genügt also als
   Auswahlregel. Bei wenigen Targets (kleine Wand/Modul) bleiben ohnehin alle
   markiert — die Regel deckelt nur den worst case.
   *Verworfen:* jeden n-ten Punkt (Modulo-Sampling) — hätte print/travel-
   Wechsel verpassen können, gerade die Stellen, an denen die Nummer beim
   Abgleich mit dem Roboterprogramm am meisten hilft.
3. **Darstellung:** Sprite-Labels (Canvas-Textur, rundes Chip + Ziffer, feste
   Weltgröße 55 mm, `depthTest: false`) mit harter Dichte-Deckelung
   `MAX_TARGET_LABELS = 150`; bei Überschreitung gleichmäßig ausgedünnt
   (verteilte Lücken statt eines abgeschnittenen Randes). Jedes Label folgt
   zusätzlich derselben Layer-/Wachs-/Travel-Sichtbarkeit wie die Bahnlinien
   (`targetLabelVisible`) — sonst schwebten Nummern ausgeblendeter Schichten
   sichtbar in der Luft, ein Lesbarkeits- wie Vertrauensproblem.
   *Verworfen:* DOM-Overlay-Chips (das bestehende Muster für Maß-/Basis-Labels,
   `addOverlayChip` in `main.ts`) — hätte für DREI gleichzeitig lebende
   `ToolpathView`-Instanzen (Sequenz-Modus: ein Chip-Satz je Abschnitt) eigenes
   Rebuild-/Teardown-Bookkeeping in `main.ts` gebraucht; als Sprite im
   `ToolpathView.group` selbst folgen die Labels Transform, Aufbau und Abbau
   der Gruppe automatisch mit — weniger Code, kein neuer Zustand in `main.ts`.
4. **Ort des Schalters:** ⚙-Menü am 3D-Feld, Sektion „Replay-Bühne" (nicht der
   Reiter Druckplan) — der fünfte Schalter neben Roboterarm/Strang/Druckstand/
   Abstandszahl, gleiche Sichtbarkeitsregel (`viewerSettingsSections`,
   unverändert). Default **aus**, wie „Wachsender Druckstand": eine Ansicht,
   die tausende Ziffern ungefragt einblendet, wäre auf Anhieb überladen.

**Verweis.** ADR-007 (Viewer zeigt nur, keine Fachlogik); Issue #159
(⚙-Sektionen „Modellansicht"/„Replay-Bühne", Vorbild für den fünften Schalter).

**Verifikation.** Neue reine Auswahl-/Ausdünnungs-/Sichtbarkeitslogik in
`viewer/src/render/target-labels-state.ts` (`significantTargetIndices`,
`thinIndices`, `targetLabels`, `targetLabelVisible`), 15 neue vitest-Fälle in
`target-labels-state.test.ts` (Auswahl bei Kind-/Ring-/Schicht-Wechseln,
Ausdünnung über 1000 Punkte, alle vier Sichtbarkeits-Modi). `ToolpathView`
(`toolpath.ts`) baut die Sprites einmalig und schaltet sie über
`setLabelsVisible`; `main.ts` verdrahtet den ⚙-Schalter „Punktnummern" auf
alle drei Instanz-Stellen. `npm --prefix viewer test` (76 Dateien/966 Tests)
und `npm --prefix viewer run build` (tsc --noEmit + vite build) grün. Viewer-
only, core/ unberührt.

---

## 2026-07-12 — Platzierungs-Abstand misst ab der Wandfläche (Issue #160, ADR-025)

**Frage.** `standoff_mm` („Abstand"): Distanz Basis → Wand-**Mittelebene**
(bisherige Core-Rechnung) oder Basis → Wand-/Modul-**Fläche** (bisherige
Viewer-Anzeige, Docstrings, physische Intuition)? Ausgelöst durch eine reale
Kollision am Denkmal (510 mm dick): Override „Abstand 535" → die
Slicing-Ansicht zeigte den Roboter 790 mm vor der Wandmitte, die Simulation
stellte ihn auf 535 (nur 280 mm vor der Fläche); das Kollisionsurteil des
Laufs meldete −120,6 mm Durchdringung. Beide Ansichten lasen also denselben
Wert unter verschiedenen Konventionen — genau die in Issue #160 offene
Domänenfrage; deren Anmerkung „kein Blocker, Anzeige und Rechnung
deckungsgleich" galt nur für die Druckort-Ansicht (Kasten-Fix), nicht für
die Einbauort-Marker.

**Alternativen.** (1) Semantik auf Wandfläche umstellen; (2) Mittelebene
behalten, nur Anzeige/Beschriftung fixen; (3) beides anzeigen. — Tobias
(Domänenentscheidung, 2026-07-12): **Wandfläche** — der Abstand ist das
Zollstock-Maß am Aufstellort.

**Entscheidung.** Eine Umrechnungsnaht
`fgc.placement.base_position_in_wall(placement, thickness_mm)`
(y = Dicke/2 + standoff, Inverse `standoff_from_base_y`); alle Frame-Bauer
(evaluate, coarse, `_planned_setup`, `module_pose`) laufen durch sie.
`coarse._wall_box` dabei von y ∈ [−Dicke, 0] auf ±Dicke/2 korrigiert (lag
eine halbe Dicke zu tief). `_module_placement` zieht die halbe Moduldicke
von der Frame-Distanz ab — Modul-Pose an der Workstation physisch identisch.
Gespeicherte Werte werden **reinterpretiert, nicht migriert** (sichere
Richtung: Roboter steht weiter weg; Zerlegung/Platzierung nach dem Update
neu bewerten). Details + verworfene Varianten: **ADR-025**.

**Verifikation.** Neue Orakel: `base_position_in_wall` (Denkmal-Zahlen
535/510 → 790), Roundtrip, Dicken-Monotonie der Bewertung
(`test_placement.py`), `wall_to_base`-y in `test_section_simulation.py`;
Modul-Pose-/Export-/Decompose-Erwartungen auf die neue Semantik gehoben.
Der Denkmal-Live-Test pinnte 16 Module und schlug **schon auf main** fehl
(Projektdaten-Drift → 18); er prüft jetzt zählrobust das Urteil statt der
Teilungszahl. Volle Prüfkette grün (ruff, pytest core, vitest, tsc+build).

**Betriebshinweis.** Wer 535 mm Freiraum wollte und unter alter Lesart 790
eintrug, trägt jetzt wieder 535 ein — die Zahl bedeutet endlich das Maß, das
man misst.

## 2026-07-12 — PRD #183 nachgeschärft: Neuheitskern-Korrektur (Shen 2026), Glied-SDF-Inversion, GPU-Ablehnung, Surrogat-Vorsortierer, Umsetz-Metrik

**Frage.** Gezielte Nachrecherche zu PRD #183 (Grill-Session): Hält der
Neuheitskern („niemand prüft den Arm gegen den wachsenden Druckstand")
einem Stresstest stand, und welche der vier neuen Schienen (Shen et al.
2026, cuRobo/GPU, Surrogat-Lernen, Umsetz-Sequenzierung) gehören in die
PRD? Recherche-Nachtrag:
`docs/recherche/2026-07-12-nachtrag-neuheitskern-shen2026.md`.

**Alternativen + Entscheidungen (Grill 2026-07-12, Tobias; Neuheits-
Positionierung an Claude delegiert).**

1. *Neuheitskern:* (a) Kopplung als Kern, (b) Neuheit auf neue Schiene
   verschieben, (c) engen Claim verteidigen. → **(a)**: Shen et al. 2026
   (arXiv 2606.29766, Volltext gelesen) prüfen den Arm differenzierbar
   gegen das wachsende Werkstück — aber auf Trajektorienebene, Desktop-
   Maßstab, redundanzabhängig (8 DOF; unser 6-DOF-M1013 mit voll
   bestimmter Düsenpose hat keine kontinuierliche Redundanz). Neuer Claim:
   erste Pipeline mit diesem Check als **Schiedsrichter einer diskreten
   Zerlegungs- und Platzierungssuche im Bau-Maßstab, ab IFC**. Zitat +
   Abgrenzung in PRD und Paper-Skizze; Korrektur der Recherche II als
   Nachtrag, Alttext bleibt stehen.
2. *SDF-Arbeitspaket:* (a) Druckstand-SDF wie geplant, (b) Inversion nach
   Shen (statische Glied-SDFs offline + Druckstand als wachsende
   Punktwolke), (c) Mess-Spike entscheidet. → **(b)**: teure Vorarbeit
   gehört auf das, was sich nie ändert (Glieder), nicht auf das, was bei
   jedem Druck wächst (Wand). US 15 (kein Feld-Neubau) konstruktiv gelöst
   (Punkte anhängen), Selbstkollision fällt im selben Schema gratis ab —
   das bedingte Kapseltabellen-Paket entfällt. FCL bleibt Nachprüfer im
   Grenzband, Regressionsanker „identische Befunde" bleibt; Mess-Spike
   umgewidmet zum Vorher/Nachher-Beleg fürs Paper.
3. *GPU/cuRobo:* (a) ablehnen + Revisionstrigger, (b) Auto-Backend bei
   Hardware-Erkennung, (c) erst messen. → **(a)**: CUDA-Abhängigkeit
   gegen das Jeder-PC-Versprechen; GPU-Gleitkomma bricht Byte-Gleichheit
   der Goldens und die ADR-004-Vergleichbarkeit des Benchmarks (Ergebnis
   hinge vom Rechner ab); Engpass (53 % `set_transform`, S5) durch die
   Inversion bereits adressiert. Übernommen wird nur das **Batch-Prinzip**
   (vektorisierte Abfragen). **Revisionstrigger:** verfehlt die
   Glied-SDF-Prüf-Tür die 10-s-Marke (#144) auf CPU, wird ein GPU-Backend
   neu bewertet.
4. *Surrogat-Lernen* (gelernter Vorsortierer der Prüf-Tür): (a) nur
   Datensammlung, (b) volles Arbeitspaket, (c) weglassen. → **(b)**
   (Tobias, gegen die engere Empfehlung (a)): geometrisch-kinematische
   Druckbarkeits-Surrogate sind im Bau-Kontext unbeackert, und die
   Pipeline erzeugt die Trainingsdaten als Nebenprodukt. Rolle v1: **nur
   sortieren, nie verwerfen** (unsichtbar für Ampel/Befunde, keine neue
   Ehrlichkeits-Semantik; Aussieben = notierte Ausbaustufe mit eigenem
   Gate). Kaltstart per **Datenkampagne** (Batch-Sampling des
   Kandidatenraums, exakte Prüf-Tür etikettiert; Datensatz =
   veröffentlichbares Paper-Artefakt). Benchmark bekommt den dritten Arm
   Greedy vs. Beam vs. Beam+Surrogat.
5. *Umsetz-Sequenzierung:* (a) Kriterium + Metrik in #183, volle
   Sequenzierung eigenes Issue, (b) voll in #183, (c) gar nicht. →
   **(a)**: „Anzahl Standplätze/Umsetzvorgänge" wird Zielfunktions-
   Kandidat der Beam-Suche (Gewichtung weiter im Grill-Gate) und
   Pflicht-Metrik im Benchmark-Katalog; die volle Reihenfolge-Optimierung
   (TSP/SSP, Einmess-Kosten, Kopplung #116) als eigenes Issue
   ausgegliedert (Paper-3-Kandidat).

**Begründung des Rahmens.** Publikationsziel bleibt Automation in
Construction; Tobias' Leitlinie im Grill: Werkzeugqualität vor
Neuheits-Claim („Hauptsache das Tool funktioniert am Ende richtig gut") —
die Inversion und das Batch-Prinzip zahlen genau darauf ein. Neue
Phasen-Reihenfolge in #183: Messung → Glied-SDF → Schranke (parallel) →
Karte → Datenkampagne → Beam-Grill → Beam → Surrogat.

## 2026-07-13 — Architektur-Review „tiefe Module": Top 5 gegrillt → Issues #188–#193

**Methode.** Review nach /improve-codebase-architecture (ultracode): 7
Bereichs-Explorer (Pipeline, Zerlegung/Platzierung, Sim/Kinematik/Kollision,
Projekt/Domain/Slicer, Viewer-Verdrahtung, Py↔TS-Zwillinge, Test-Seams),
20 Kandidaten, jeder adversarial verifiziert (Belege nachgezählt,
Deletion-Test, ADR-Abgleich): 19 bestätigt, 1 abgeschwächt (Druckort-Schnitt
→ ist Issue #121, dort weiterführen). Gesund befundet und nicht angefasst:
api.py als ehrlich flacher 1:1-Adapter, plan_for_job, placement.evaluate als
die eine Metrik, der Slicer-Strang (ADR-015-Seam mit zwei Adaptern), die pure
Viewer-Schicht. Grundmuster der Friktion überall gleich: **tiefes Verhalten
ohne benanntes Interface**. Report als lokale HTML (temp, nicht im Repo).

**Entscheidungen (Grill, Tobias):**

1. *Gradierungs-Drift (#188):* Abschnitts-Overrides slice/orientation
   (a) echt wirken lassen, (b) nur orientation, (c) zurückbauen → **(a)**:
   UI/Persistenz/Veraltung/Prüf-Cache behandeln sie längst als wirksam;
   Abschnitte sind getrennte Druckvorgänge mit eigener Platzierung,
   Fugen-Verantwortung beim Nutzer (Befund, kein Gate). Zuerst mergen,
   die Extraktion verschiebt danach den gefixten Code.
2. *Extraktions-Schnitt (#189/#190):* (a) zwei Module —
   pipeline/sectionsim.py (Rechenkette) + decompose/pruefung.py
   (Urteils-Politik assess_plan), (b) ein Modul → **(a)**: Domäne zur
   Domäne (printability/freigang liegen dort), der #165-Autozerleger wird
   zweiter Produktiv-Aufrufer von assess_plan; check_representative als
   injizierbarer Orakel-Seam (ersetzt monkeypatch auf Private), PruefCache
   als Objekt — der Test-Zweig `cache is _PRUEFTUER_CACHE` entfällt.
3. *Testmigration:* (a) hart ohne Aliase, (b) Übergangs-Aliase → **(a)**:
   Aliase wären genau die flachen Pass-throughs, die der Review anprangert;
   Denkmal-/Golden-Orakel als Byte-Anker gegen Regressionen.
4. *ADR-022-Leserichtung (#191):* (a) eigene Scheibe nach #189, (b) in die
   Extraktion integrieren → **(a)**: Move und Umsemantisierung getrennt
   reviewbar. Design-Log statt ADR-Nachtrag — ADR-022 regelt WAS gilt,
   hier ändert sich nur WO es beantwortet wird.
5. *FindingRequest (#192):* (a) gruppiert ~6 Gruppen, (b) flach → **(a)**:
   die scene-Gruppe ist die DruckstandSpec-Naht (8 von 18 Parametern nur
   dafür); Invarianten stehen an der Gruppe, an der sie gelten.
6. *Übernahme-Protokoll (#193):* Divergenzen der 7 main.ts-Kopien
   (a) normalisieren, Abweichung = Bug, (b) konservieren → **(a)**:
   fehlende Schritte sind die #161-Familie; tragende Abweichungen werden
   benannte Optionen im Vertrag. placement-apply.ts delegiert (zwei
   Adapter am selben Vertrag).
7. *Kein PRD:* Report + dieses Protokoll sind die Spezifikation;
   /to-issues schnitt direkt 6 Issues. Reihenfolge:
   #188 → #189 → {#190, #191, #192 parallel} ∥ #193 (Viewer, unabhängig).

**Glossar:** „Prüf-Tür" neu in core/CONTEXT.md (benennt jetzt das Modul
decompose/pruefung), „Übernahme-Protokoll" neu in viewer/CONTEXT.md.

**Offen (bewusst noch ohne Issue):** die übrigen bestätigten Kandidaten des
Reports — u. a. focus-store (Strong), Py↔TS-Paritäts-Halbschleifen (Strong;
inkl. real gefundener Drift an der last_pruef-Kante: TS „missing" vs. Python
„current", und CI fährt kein vitest), Wand-Quellen-conftest (Strong),
propose_decomposition-Persistier-Tür, Config-Flip a/b-Block, coarse-Widmung,
API-Kontrakt-Orakel. Bei Bedarf aus dem Report nachziehen.
*(Erledigt noch am selben Tag — s. Nachtrag unten.)*

## 2026-07-13 — Nachtrag: Rest des Architektur-Reviews verissued (#194–#204)

Frage: Zuschnitt der übrigen 10 bestätigten Kandidaten (Karten 6–15) als
Issues (Tobias: „mach jetzt auch noch die anderen"). Entscheidungen beim
Schneiden:

- **Parität zweigeteilt:** #194 (Halbschleifen schließen: pytest-Leser für
  alle 5 Goldens, Ganzjob-/Prüf-Familie bekommt Goldens, die reale
  last_pruef-Divergenz TS↔Py wird entschieden, vitest kommt in die CI) →
  #195 (Parity-Manifest-Harness mechanisiert die Fälle, blocked-by #194).
  Alternative „ein Großissue" verworfen: die Drift blutet heute, das
  Harness kann warten.
- **Karte 16 (Druckort) nicht dupliziert** — identische Diagnose liegt als
  #121 (Bühnen-Modul) vor; der Review-Verifier stufte den engeren
  druckort-only-Schnitt selbst herab (bräuchte 20–25 Ports, Quer-Lecks
  blieben).
- **#204 (Plan-Feld-Registry) trigger-gebunden** an PRD #110 — bei 3
  Bestandsschaltern trägt der Umbau seine Kosten nicht; bis dahin Backlog.
- **#202 (Kontrakt-Orakel):** Default-Variante Golden-Responses aus den
  vorhandenen TestClient-Erfolgspfaden (Hausmuster, drittes
  Goldens-Orakel); OpenAPI-Generat (32/34 response_model) als notierte
  Alternative, Abweichung im PR zu begründen.
- **#200 (Config-Flip):** margin_after bahn-weit über das
  Neu-Simulations-Muster des Kollisions-Advisors (#130) statt
  Ein-Pose-Wert — keine Parallel-Metrik (ADR-020/024).
- **Blocked-by-Kanten:** #195←#194; #196←#193 (weich, beide kneten
  main.ts); #197←#189 (dieselben Testdateien + actions.py); #198←#190
  (dieselbe actions-Region); #199–#203 frei; #204 wartet auf seinen
  Trigger.

Damit ist der Review vollständig in den Tracker überführt: #188–#204
(17 Issues aus 20 bestätigten Kandidaten; 3 gingen in bestehende Arbeit
auf: Karte 16 → #121, Karten 1+K1-Test-Seams → #189/#190 zusammengeführt).

## 2026-07-13 — #188 umgesetzt: Abschnitts-Overrides wirken in der Kern-Tür (Gradierungs-Drift geschlossen)

**Frage.** Wie schließen wir die Drift, dass `process_params.sections`
(slice/orientation, #82/#83) persistiert, veraltet, den Prüf-Cache invalidiert
und in der Live-Vorschau wirkt — aber die Kern-Tür `_slice_and_simulate_section`
mit den **globalen** Werten slict (nur `ik_config` war abschnitts-effektiv)?

**Alternativen.** (a) Zwei dünne 2-Parameter-Leser in `domain/process_params.py`
als Spiegel der bestehenden Job-Leser; (b) `effective_section_params` direkt in
`actions.py` auffächern (io-Ausdehnung/Grad→Radiant dort duplizieren);
(c) Signatur der Kern-Tür um fertige Params erweitern (Aufrufer lösen selbst auf).

**Entscheidung: (a)** — wie im Grill vom selben Tag beschlossen.
`section_slice_overrides(job, section_id)` / `section_orientation(job, section_id)`
lesen den **effektiven** Block des Abschnitts (`effective_section_params`, #82)
durch **denselben** Übersetzungs-Kern wie ihre globalen Zwillinge: die
io-Skalar-Ausdehnung wurde als `_slice_overrides_from_block` geteilt (statt
kopiert), die Grad→Radiant-Übersetzung war schon geteilt
(`_orientation_from_block`). `_section_sim_context` bezieht `base_params` jetzt
je Abschnitt, `_slice_and_simulate_section` die Orientierung — Signatur
unverändert, alle vier Aufrufer (Simulation, Kollisions-Advisor,
Clearance-Check, Prüf-Tür) erben die Gradierung; der Export liest den
Simulations-Lauf und stimmt damit automatisch. (b) verworfen: genau die
Umrechnungs-Duplikation, die #51/#160 als Drift-Quelle identifiziert haben;
(c) verworfen: 4 Aufrufer anfassen für null Zusatznutzen.

**Begründung/Beweis.** Ohne Abschnitts-Override ist
`section_slice_overrides(job, sid) == job_slice_overrides(job)` (dieselbe
Auflösung, leerer Override) — der Regressionsanker
(`test_section_without_override_is_byte_identical`) belegt byte-gleiche Targets
+ Parameter-Echo, auch wenn der **Nachbar** übersteuert. End-to-end
(`core/tests/test_section_overrides_pipeline.py`): Abschnitts-`layer_height_mm`
×2 halbiert `n_layers` **nur dieses** Laufs (vor dem Fix rot); Kipp-Override
kippt `frame.quat` nur dieses Abschnitts (Muster #61), der Nachbar bleibt
senkrecht. `effective_section_params` hat damit ≥2 im Core konsumierte Gruppen
(slice, orientation, ik_config) — der Seam ist echt statt hypothetisch.
Advisor-Hebel unverändert: ein explizites `override` (Kipp/Lead absolut,
ik_config-Block) übersteuert weiterhin auch den Abschnitts-Override — der
Advisor probiert Kandidaten bewusst *anstelle* des persistierten Stands.
Toolpath-Cache der Advisor-Schleife bleibt korrekt: `base_params` sind je
`_SectionSimContext` (= je Abschnitt) fix, der Cache-Schlüssel (lead, kipp)
deckt weiter alle toolpath-formenden Freiheitsgrade.

## 2026-07-13 — #189 umgesetzt: Abschnitts-Simulations-Kern als benanntes Modul `fgc/pipeline/sectionsim.py`

**Frage.** Wie bekommt der ~600-LOC-Rechenkern (Zerlegungsplan-Kontext →
Teil-Mesh schneiden → slicen → Trajektorie → Kollisionskontrolle gegen den
Druckstand → Clearance-Urteil) ein benanntes Interface, ohne sein Verhalten
anzufassen? Er lebte als 15 private Helfer in der 4800-LOC-Türen-Sammlung
`actions.py`: 5er-Tupel-Ritual an 15 Entpack-Stellen, `_SectionSimContext`
9/12 und `_SectionComputation` 7/11 Felder `Any`, ~70 Unterstrich-Referenzen
in 10 Testdateien.

**Alternativen.** (a) Extraktion als `pipeline/sectionsim.py`, Tests hart ans
neue Interface migriert, keine Alias-Re-Exports (Grill-Entscheidung vom selben
Tag, Punkte 2/3); (b) Übergangs-Aliase der alten `_`-Namen in `actions.py`;
(c) Move und ADR-022-Umsemantisierung in einem Zug.

**Entscheidung: (a)** — reiner Move + Typisierung, Semantik byte-gleich.
`sectionsim.py` exportiert `PlacementContext` (Dataclass mit 5 benannten
Feldern statt 5er-Tupel), `SectionSimContext`/`SectionComputation` (öffentlich,
konkret typisiert: `Toolpath`, `Trajectory`, `SliceParams`, `Section`,
`PlacementOption`, `OpwKinematics`, `np.ndarray` statt `Any`) sowie
`placement_context_for_job`, `section_sim_context`,
`slice_and_simulate_section`, `clearance_verdict` und die fail-soften
Befund-Aufrufe `section_collision_finding`, `section_clearance_check`,
`section_context_geometry`, `planned_setup`. `actions.py` (4807 → 4192 LOC)
behält nur Türen (laden → Kern rufen → Lauf/Projekt schreiben), die
Prüf-Tür-Politik (`_decompose_printability*`, Cache, `_plan_pruef_signature`)
und Persistenz — die Politik zieht mit #190 nach `decompose/pruefung.py` um.
Einzige Richtungs-Naht: `section_sim_context` lädt `plan_for_job` lazy aus
`actions` (die Rekonstruktions-Tür bleibt laut Glossar dort; kein Importzyklus,
da nur zur Laufzeit). Wand-lokale Basis/Mesh und
`_wall_surface_from_assessment` bleiben modulprivat in `sectionsim` (keine
externen Konsumenten). (b) verworfen: Aliase wären genau die flachen
Pass-throughs, die der Review anprangert; (c) verworfen: Move und
Umsemantisierung getrennt reviewbar (#191).

**Beweis.** Verhalten byte-gleich per Move (keine Logikänderung, nur Renames +
`PlacementContext`-Entpacken an den Türen); Denkmal-Orakel
(`test_prueftuer_denkmal`, slow) und volle Suite grün. Grep-clean: kein Test
referenziert mehr `actions._section_sim_context` /
`_slice_and_simulate_section` / `_placement_context_for_job` /
`_section_collision_finding` / `_clearance_verdict_for_section`; die
Monkeypatch-Seams der Tests zeigen jetzt auf öffentliche Namen
(`actions.clearance_verdict` für die Stage-2-Orchestrierung,
`sectionsim.section_sim_context` für den Kern). Der
`decompose/printability.py`-Docstring zitiert den öffentlichen Namen.

## 2026-07-13 — #190 umgesetzt: Prüf-Tür-Politik als `fgc/decompose/pruefung.py` (assess_plan + injizierbares Orakel + PruefCache)

**Frage.** Wie bekommt die Urteils-Politik der Prüf-Tür (Fokus/Global-Scoping,
Reihen-Vererbung, die drei Bedeutungen von „kein Urteil", Cache-Politik
nur-echte-Urteile + FIFO 512) ein benanntes Domänen-Interface? Sie lebte als
~360-LOC-Privat-Suite in `actions.py` (`_decompose_printability*`, Cache-Dict
mit Test-Sonderzweig `cache is _PRUEFTUER_CACHE`, produktions-toter Wrapper),
Tests stellten den Orakel-Seam per `monkeypatch.setattr` auf Private her.

**Alternativen.** (a) Domäne zur Domäne: `fgc/decompose/pruefung.py` mit **einer**
Tür `assess_plan` (Stufe 1 = derselbe Aufruf ohne Orakel), `check_representative`
als injizierbarem Parameter, `PruefCache` als Objekt (Grill vom selben Tag,
Punkt 2); (b) Politik in `pipeline/sectionsim.py` mitziehen (ein Modul);
(c) nur die Privaten in `actions.py` öffentlich benennen.

**Entscheidung: (a).** `pruefung.py` exportiert `assess_plan(plan, statuses,
freigang, override_ids, check_representative, *, signature, focus_section_id,
cache, on_progress, should_cancel) -> (printability, PruefStats)` sowie
`PruefCache` (eigene FIFO-Politik, Deckel parametrierbar, Default 512),
`PruefStats` und `count_representatives` (Umfangsansage-Kern). Das
Leere-Dict-Protokoll `{}, {}` der Stufe 1 verschwindet: ohne Orakel liefert
dieselbe Tür den ehrlichen `unchecked`-Ruhezustand (bewusst ohne Cache-Blick —
der interaktive Loop täuscht kein Urteil vor); `signature`/`cache` sind nur mit
Orakel Pflicht (ValueError sonst — kein stiller Prozess-Cache im Domänen-Modul).
Der Seam trägt zwei echte Adapter: die Produktiv-Closure über
`sectionsim.clearance_verdict` (#189) in `check_decomposition` (löst bewusst
über das Modul-Global auf — der öffentliche Test-Seam der Orchestrierung
bleibt) und die Test-Fakes; der dritte Adapter (#183/#165-Autozerleger je
Kandidatenplan) ist absehbar. `actions.py` behält Job-Schema-Wissen und
Persistenz: `_plan_pruef_signature`, `_pruef_override_ids`,
`_decompose_pruef_scope` (jetzt dünn über `count_representatives` +
`PRUEF_PER_REP_SECONDS`) und hält die **eine** prozessweite
`PruefCache`-Instanz (lazy erzeugt — `actions` bleibt geo-frei importierbar,
`fgc.decompose` zieht trimesh/shapely). Gelöscht: der tote Wrapper
`_decompose_printability`, der Test-Zweig `cache is _PRUEFTUER_CACHE`,
`clear_prueftuer_cache` samt Test-Ritual (Tests injizieren frische
`PruefCache`-Instanzen über den `cache`-Parameter).
`combine_printability`/`representative_by_row` sind Paket-Interna (aus dem
`fgc.decompose`-Export genommen; `representative_by_row` hat keinen Konsumenten
außerhalb des Pakets mehr), `REASON_UNCHECKED` ist sauber exportiert.
(b) verworfen: printability/freigang liegen in `decompose`, die Politik urteilt
über dem Zerlegungsplan, nicht über der Simulation; (c) verworfen: ließe den
Test-Sonderzweig und das monkeypatch-auf-Private-Muster bestehen.

**Beweis.** 0 `monkeypatch.setattr` auf actions-Private in den Prüf-Tür-Tests
(Supersede-Test simuliert den parallelen Schreibzugriff jetzt im gemockten
öffentlichen `actions.clearance_verdict` statt in einem gefakten Stage-2);
Politik-Tests (`test_pruef_check.py`, Repräsentanten-Tests in
`test_decompose.py`) laufen am neuen Interface mit injiziertem Orakel, neu
dazu: FIFO-Deckel-Test und „error wird nie gecacht" (die Cache-Politik am
Objekt). Verhalten unverändert: alle bestehenden Prüf-Tür-Tests inkl.
Supersede/Fortschritt/Abbruch grün, Denkmal-Orakel
(`test_denkmal_representative_pruef_tuer_inherits_row_verdict`, slow) grün auf
echter Geometrie, volle Core-Suite grün. Kein README-Abschnitt nötig
(reine Binnen-Architektur, keine nutzersichtbare Funktion).

## 2026-07-13 — #191 umgesetzt: ADR-022-Leserichtung als Plan-Member (kind-Konditionale 10 → 2)

**Frage.** Die Zerlegungsart-Konvention (Art „Abschnitt": echte Höhenlage `z0`
+ frühere Teile als Druckstand + Gebäudekontext; Art „Modul": Fuß auf der
Arbeitsfläche, nichts davon) war an 10 Produktions-Stellen in 4 Dateien als
inline `kind`-Stringvergleich kodiert — darunter 3 byte-identische Ternaries
(`section_z0_mm=… if plan_kind == "abschnitt" else 0.0`) plus 3 Kopien in Tests;
zwei Zwillinge waren nur per Kommentar synchron (surface-Regel `evaluate`↔
`advise_singularity`, `_obstacle_load`↔`earlier_parts`). Genau diese Klasse
gebar die Bugs #132 (Phantom-Podest) und #135 (z0-lose Kollisionskette). Wie
antwortet der Plan selbst, ohne die Semantik anzufassen (eigene Scheibe NACH dem
reinen Move #189)?

**Alternativen.** (a) `kind` als Feld auf `SectionPlan` (die Bullet-Formulierung
des Issues) — verworfen: `SectionPlan` ist ein reines Paar (Abschnitt,
Platzierung), das Feld dupliziert die autoritative `DecompositionPlan.kind` und
bräuchte Stempelung/Default an ~20 Konstruktionsstellen — genau die Sync-per-
Konvention, die #191 tötet. (b) `__post_init__`-Stempelung der Kind auf jede
`SectionPlan` — verworfen als „clever"/identitätsverändernd. (c) **Der
`DecompositionPlan` (= „der Plan" des Titels) trägt die Member; Section-Helfer
nehmen die `Section`** — gewählt.

**Entscheidung: (c).** Neue Member in `decompose/plan.py` (die einzige Stelle mit
`kind`-Leserichtungs-Vergleich):

- `DecompositionPlan.prints_in_place` (`kind == "abschnitt"`) — der Kern der
  Leserichtung; gemeinsamer Member der Zwillinge `_obstacle_load`
  (`decompose/printability.py`) und `earlier_parts` (`pipeline/sectionsim.py`).
- `DecompositionPlan.building_context_applicable` (`kind != "modul"`) — eigenes
  Prädikat (andere Domänen-Frage, heute gleicher Wert).
- `DecompositionPlan.sim_z0_mm(section) -> float | None` — `z0` bei „Abschnitt",
  `None` bei „Modul"; das `None` kodiert zugleich die Präsenz von
  `meta.section_z0_mm`.
- `DecompositionPlan.surface_for_evaluation(section, thickness_mm)` — kapselt den
  None/0.0-Entscheid; gemeinsamer Member von `decompose/evaluate` und
  `advise_singularity`.

`SectionSimContext`/`SectionComputation` tragen die abgeleiteten Werte
**vorgerechnet** (`section_z0_mm: float | None`, `building_context_applicable:
bool`) — Muster wie das bereits fertig abgeleitete `earlier_parts`. Die
Befund-/Setup-Nähte lesen `comp.section_z0_mm or 0.0` (None → 0.0) und
`comp.building_context_applicable`, die meta-Präsenz `if comp.section_z0_mm is
not None`. Damit sind die 10 Produktions-Stellen und die 3 Test-Kopien reine
Feld-/Methodenzugriffe; die Leserichtungs-`kind`-Vergleiche im Core gehen 10 → 2
(beide in `plan.py`, Grep-Beleg unten).

Abgegrenzt bleiben die `kind == "modul"`-Vergleiche der **Plan-Konstruktion**
(`decompose/propose.py`: Platzierungsalgorithmus) und der **Modul-Fertigungs-
Features** (`pipeline/actions.py`: Setup-Generierung #136, Modulgewicht/-Lagen/
-Grenzen #90/#96) sowie die `mode`-Routing-Interna in `collision/finding.py`/
`druckstand.py` — eine andere Achse (Modul-Feature statt Leserichtungs-z0), die
das Issue bewusst nicht umfasst.

**Beweis.** Verhalten byte-gleich (keine Logikänderung, nur benannte Member +
Vorrechnung; `section.z0_mm` und `sim_z0_mm` sind für Art „Abschnitt" identisch,
`or 0.0`/None-Zweig deckt „Modul" wie zuvor). Grep `kind == "abschnitt" |
kind != "modul"` als Leserichtung: **vorher** 10 Produktions-Stellen (evaluate,
advise_singularity, sectionsim ×3, actions ×3, printability, + earlier-parts-
Guard) + 3 Test-Kopien; **nachher** nur `plan.py:160` (`prints_in_place`) und
`plan.py:171` (`building_context_applicable`). Denkmal-Orakel (slow) + Zerlegungs-
/Kollisions-Suiten + volle Core-Suite grün. Kein ADR-Nachtrag (ADR-022 entscheidet
WAS gilt; hier ändert sich nur WO es beantwortet wird — ihr Nachtrag fordert die
Naht selbst). Kein README-Abschnitt (reine Binnen-Architektur, keine
nutzersichtbare Funktion).

## 2026-07-13 — FindingRequest-Wertobjekt: Kollisions-Türen 18/19 → 2/3 (Issue #192)

**Frage.** Die Naht Simulation → **Kollisionskontrolle** zerlegte beidseits
vorhandene Wertobjekte in einen 18/19-Parameter-Sack: `build_section_finding`
(18 Param.), `check_part_clearance` (19), `_prepare_finding` wiederholte
dieselben 18. Die identische Namensliste war 10× im Produktionscode
buchstabiert, die Invarianten (abschnitts-lokales System, Boden bei −z0,
Kontext-Schalter) lebten in sechs Docstrings; additive Änderungen amplifizierten
(#135 = 39 Fundstellen, #131 = 21). Wie bündeln, ohne das Verhalten anzufassen?

**Alternativen.** (a) Ein flaches `FindingArgs`-Objekt (18 Felder in einem
Container) — verworfen: bündelt die Buchhaltung, benennt aber keine Naht; die
DruckstandSpec-Bedeutung der 8 scene-Parameter bliebe unsichtbar. (b) Die
Türen an die `SectionComputation` hängen (Methode statt freie Funktion) —
verworfen: `finding.py` muss ohne `[geo]` und ohne `pipeline` importierbar
bleiben (Reinheit), die Türen dürfen nicht auf den Sim-Kern zeigen. (c)
**Frozen, gruppiertes `FindingRequest` in `fgc.collision.finding`** (6 Gruppen),
gebaut von **einer** Naht `SectionComputation.finding_request(config=…,
context=…)` — gewählt (Grill-Entscheidung 2026-07-13).

**Entscheidung: (c).** Sechs frozen Dataclasses in `collision/finding.py`:
`TrajectoryExcerpt` (base_frame, samples, target_times_s), `ToolpathExcerpt`
(targets, layer_height_mm, n_layers), `PartMesh` (vertices_mm, faces),
`SceneInputs` (mode, section_z0_mm, earlier_parts, context) — **die
DruckstandSpec-Naht**, 8 der 18 Parameter dienten nur ihr, `RobotToolRefs`
(tool, tools_dir, robots_dir) und das bündelnde `FindingRequest`. Die
Invarianten stehen **einmal** an den Gruppen-Definitionen (nicht mehr in sechs
Docstrings). Die Türen schrumpfen auf `build_section_finding(robot_name,
request)` und `check_part_clearance(robot_name, request, *, travel_stride=…)`;
`_prepare_finding` nimmt das Objekt. Der Builder `finding_request` sitzt an
`SectionComputation` (#189, kennt den Sim-Kern) und mappt die vorgerechneten
Felder (#191: `section_z0_mm`, `earlier_parts`) auf die Gruppen — die eine
Marshaling-Naht, von den fail-soften Wrappern `section_collision_finding`
(actions ×2) und `section_clearance_check` gerufen. `context` bündelt die
früheren zwei Felder `context_vertices_mm`/`context_faces` zu einem
`(verts, faces) | None` — genau die Form, die `section_context_geometry` schon
liefert.

**Beweis.** Verhalten byte-gleich (nur Bündelung, keine Logikänderung;
`toolpath_artifact["targets"]` == `comp.target_dicts` und
`["summary"]["n_layers"]` == `comp.toolpath.summary()["n_layers"]`, s.
`Toolpath.to_artifact` — die eine Naht liest darum byte-identische Werte wie
die zwei alten Call-Sites). Grep `part_vertices_mm=` (der Marker der
Door-Namensliste): **vorher** 6 Produktions-Call-Sites (finding ×2, actions ×2,
sectionsim ×2) + Signatur-Deklarationen (die „10×" des Issues) und 11
Test-Stellen; **nachher** 0 — die Feldnamen leben je **einmal** in den fünf
Gruppen-Dataclasses, der Bund wird **einmal** in `finding_request` assembliert
und **einmal** in `_prepare_finding` gelesen (~3 statt 10). Die Tests ersetzen
das `_finding_kwargs`-Splatting durch das Objekt (`dataclasses.replace` für
Varianten). Kollisions-/Zerlegungs-Suiten + Denkmal-Orakel (slow) + volle
Core-Suite grün. Kein ADR-Nachtrag (ADR-024 entscheidet WAS geprüft wird; hier
ändert sich nur die Signatur der Türen). Kein README-Abschnitt (reine
Binnen-Architektur, keine nutzersichtbare Funktion; der Funktionsname
`check_part_clearance` in §Issue #182 bleibt gültig).

## 2026-07-13 — cuRobo neu bewertet: verbindliche Integration als optionales GPU-Backend (PRD #205), Revisionstrigger abgelöst

**Frage.** Tobias wollte die cuRobo-Ablehnung vom 2026-07-12 (Recherche II,
Abschnitt 3) neu bewertet haben — für die Kollisionserkennung und wegen der
geplanten Tiefenkamera. Tiefenrecherche gegen Primärquellen (Quellcode `main`
+ `v0.7.8`, Lizenztexte, GitHub-API, arXiv):
`docs/recherche/2026-07-13-curobo-tiefenrecherche.md`. Kernbefund: cuRobo ist
seit v0.8.0 („cuRoboV2", 18.04.2026) ein anderes Projekt — **Apache-2.0**
statt „non-commercial", kompletter Rewrite, eigener block-sparser
TSDF/ESDF-Mapper statt nvblox, öffentliche Batch-Kollisions-API ohne
Motion-Gen-Stack (`RobotCollisionChecker`, `get_point_robot_distance` =
strukturell die Shen-Inversion aus #183). Die Ablehnung bewertete faktisch
das alte Projekt (curobo.org serviert weiter die v1-Doku).

**Alternativen + Entscheidungen (Grill 2026-07-13, Tobias).**

1. *Reihenfolge:* (a) Revisionstrigger abwarten, (b) verbindlich
   integrieren nach Glied-SDF-Messung, (c) sofort parallel → **(b)**:
   cuRobo ist gesetzt (nicht mehr trigger-abhängig), aber blocked-by
   **#183 Arbeitspaket 1** (Glied-SDF gebaut + gemessen = ehrliche
   Vergleichsbasis); danach parallel zum #183-Rest, damit die
   Datenkampagne den GPU-Durchsatz nutzt. Der Revisionstrigger vom
   2026-07-12 ist damit abgelöst.
2. *PRD-Ort:* (a) eigene PRD, (b) Nachtrag in #183, (c) zwei PRDs →
   **(a)**: PRD #205; #183 bleibt Paper-1-Scope (CPU, jeder PC).
3. *Funktionsumfang:* alle vier Muster — Zweit-Backend/Vorsortierer der
   Prüf-Tür, Durchsatz für Datenkampagne/Beam, Tiefenkamera-Standbein,
   Batch-IK-**Vergleich** (ergebnisoffen mit Metriken; ein IK-Tausch wäre
   eine eigene spätere Entscheidung mit eigenem Gate + ADR — die eigene
   OPW-IK bleibt Produktivpfad).
4. *Verpackung:* (a) Monorepo-Schwesterpaket mit eigener venv, (b) eigenes
   Plugin-Repo, (c) `core[gpu]`-Extra → **(a)**; (c) scheitert real am
   Python-Split (Core 3.14, cuRoboV2 ≤ 3.13) — Brücke als Subprozess/CLI,
   Artefakt rein/raus.
5. *Schalter:* App-/Rechner-Ebene, Default aus; ohne CUDA **ausgegraut mit
   Hinweis** „GPU nicht gefunden" (nicht versteckt); lückenlose Provenienz
   (Backend, cuRobo-Version, GPU, Treiber) in Artefakten und
   Projekt-Versionierung. Projektdateien bleiben maschinenunabhängig.
6. *Semantik:* Vorsortierer + eigener Befundtyp „vermutlich frei (GPU)";
   echtes „geprüft frei" bleibt CPU-exklusiv; GPU-Ergebnisse nie Goldens,
   nur Toleranzvergleich (ADR-004 unangetastet; Befund, kein Gate,
   ADR-013).
7. *G1-Rückfalllinie:* scheitert die Kugel-Formtreue (kein brauchbares
   konservatives Grenzband), schrumpft der Scope definiert (nur noch
   sortieren/priorisieren, nie Status setzen) — kein offenes Nachbessern;
   Tiefenkamera + IK-Vergleich unberührt.
8. *Tiefenkamera:* zweistufig — G4a Nahscan Ist-vs-Soll mit der
   vorhandenen **D405** (Nahbereich bis ~50 cm), G4b zellenweite
   Kollisionswelt erst nach Beschaffungs-Gate (Weitbereichs-Kamera, Budget
   vorhanden). Hardware-Lage: Windows-PC mit NVIDIA-GPU **und** Linux-Box
   vorhanden → G1-Spike direkt auf Linux, WSL2 wird nicht verfolgt.

**Begründung.** Die drei Ablehnungsgründe bleiben als **Leitplanken**
bestehen, tragen aber nur gegen den *Ersatz* des CPU-Pfads: (a) CUDA-Zwang
→ optionales Extra mit Degradation; (b) GPU-Gleitkomma (keine
Cross-GPU-Bitgleichheit zugesagt) → CPU bleibt Golden-Referenz; (c) Engpass
durch Glied-SDF adressiert → Glied-SDF zuerst. Neu ist: (c) war nie ein
Argument gegen Datenkampagnen-Durchsatz und Tiefenkamera — beides wurde am
2026-07-12 nicht bewertet, und das Kamera-Standbein hat als einziges Muster
keine CPU-Alternative im Projekt. Größte Risiken (PRD/Recherche): Kugel-
Formtreue im 50-mm-Nahbereich (der Arm ist in cuRobo immer eine Kugelmenge,
nicht konservativ per Konstruktion — G1-Gate), Zwei-Umgebungen-Wartung,
API-Bewegung auf `main` (Pin auf Release-Tag), Herstellerangaben-Charakter
aller Performance-Zahlen. Modul-Schnitt (Grill bestätigt): Brücken-CLI als
die eine Tür des GPU-Pakets; Core-Naht als injizierbares Brücken-Modul an
derselben Stelle wie das `check_representative`-Orakel (zugleich der
#183-US-14-Backend-Umschalter); Viewer nur reine Schalter-/Befund-Zustände.

## 2026-07-13 — Wand-Quellen-Seam benannt: eine Loader-Naht, `conftest.py`-Fixtures (#197)

**Frage.** Die Wandquelle war im Aktions-Interface unsichtbar, der Seam existierte
nur als Monkeypatch-Folklore: 18 wortgleiche Patches von
`fgc.ifc_io.walls.load_walls`/`load_wall`/`fgc.ifc_io.context.load_context_overview`
über 12 Testdateien, getragen von der undokumentierten Invariante, dass die
Konsumenten-Module die Loader *lazy im Funktionskörper* importierten (einziger
Nutzen: Patchbarkeit — `ifcopenshell` ist via `actions.py` ohnehin top-level
geladen). Mangels `core/tests/conftest.py` waren `make_wall` 10× und `stub_walls`
8× kopiert (plus Quer-Import `test_pruef_check`→`test_decompose`). Zusätzlich
hatten `TOOLS_DIR`/`WORKSTATIONS_DIR` je zwei Bindungen (`fgc.paths` + Import-Kopie
in `tool.py`/`workstation.py`), weshalb `test_tool_configurator` 9× **beide**
patchte. Wie benennen, ohne die Produktionspfade anzufassen?

**Alternativen.** (a) `walls=`/`wall_loader=`-Parameter durch **alle** tiefen
Aktionen fädeln (`create_project_from_ifc`→`walls_to_run`,
`simulate_section`→`section_sim_context`→…) und die Lazy-Imports zu *nackten*
Top-Level-Imports machen — verworfen: große Signatur-Fläche über ~10 Funktionen,
reale Verhaltens-/Regressionsgefahr für eine reine Test-Seam-Benennung; die
`stub_walls`-Nutzung liegt in 30/29/18 Tests je Datei, das Durchfädeln explodiert.
(b) Zentrale `conftest.py`-Fixtures + **Modul-Alias-Imports** top-level — gewählt.

**Entscheidung: (b).** Die Konsumenten importieren die Loader top-level als
**Modul-Alias** (`from fgc.ifc_io import walls as ifc_walls` / `context as
ifc_context` in `actions`/`wizard`/`api`/`cli`/`sectionsim`) und rufen
`ifc_walls.load_walls(...)` zur Aufrufzeit — die Lazy-Imports sind weg, der
Attribut-Lookup bleibt an **einer** Quelle patchbar. `core/tests/conftest.py`
hält den Fixture-Satz: `build_wall`/`make_wall` (eine flexible Quaderwand-Factory
statt 10 Kopien) und `install_walls` (die *eine* Stelle der drei Loader-Patches,
optional mit `context=`). Die datei-spezifischen `stub_walls`-Fixtures schrumpfen
auf eine Zeile (`install_walls([make_wall(...)])`) — die duplizierte Patch-Logik
ist verschwunden, die Test-Signaturen (`def test_x(stub_walls)`) unverändert.
`ToolDef.load`/`WorkstationDef.load` lesen ihre Verzeichnis-Konstante jetzt zur
Aufrufzeit aus `fgc.paths` (`paths.TOOLS_DIR`/`paths.WORKSTATIONS_DIR`) statt einer
Import-Kopie — ein Patch auf `fgc.paths` genügt überall.

**Beweis.** Produktionspfade byte-gleich (nur Import-Ort + Konstanten-Lookup, keine
Logikänderung; CLI/API/Wizard nutzen den IFC-Default unverändert). Grep der
Loader-Patch-Strings in Test**dateien**: **vorher** 18 (+ die Doppel-Patches),
**nachher** 0 — sie leben je einmal in `install_walls`. `make_wall` 10×→0 Kopien
(`build_wall` in conftest, `test_eligibility` behält seine spezialisierte
Regel-Wand mit eigener Signatur), `stub_walls` 8× duplizierte Bodies→0, Quer-Import
`test_pruef_check`→`test_decompose.make_wall` weg. Doppel-Patch `TOOLS_DIR` 9×→1,
`WORKSTATIONS_DIR`-Zwiespalt (`test_module_export`) aufgelöst → `fgc.paths`.
`ruff check core` grün; betroffene Suiten + volle Core-Suite grün. Kein
README-Abschnitt (keine nutzersichtbare Funktion; reine Test-/Binnen-Naht), kein
ADR (Signatur-/Import-Ort, keine Architekturentscheidung).

## 2026-07-13 — Persistier-Tür der Zerlegung entflochten: `_persist_decompose_run` + `DecomposeBundle`, Phase-3-Sperre ist echtes RMW (#198, ADR-018)

**Frage.** `propose_decomposition` war zugleich interaktive Neubewertungs-Tür UND
einzige Persistier-Tür der Stufe-2-Prüfurteile. 2 ihrer 12 Parameter
(`printability_override`, `last_pruef`) waren reiner interner Seitenkanal mit
unsichtbarem Paar-Kontrakt: `last_pruef` wirkte nur bei
`printability_override != None`. Und `check_decomposition` Phase 3 rief unter
gehaltener Sperre `propose_decomposition` auf, das die **komplette Stufe-1-Bewertung
neu rechnete** (`plan_for_job` mit Platzierungssuche, `evaluate` mit IK-Sampling je
Abschnitt) — obwohl Phase 1 plan/statuses/freigang bereits berechnet hatte (0
Wiederverwendung). Das widersprach ADR-018s Begründung „der pessimistische Lock ist
kurz gehalten (nur die RMW-Sektion)" und dem eigenen Phase-3-Docstring „Sperre kurz".

**Ablösung.** Dieser Eintrag löst die Teilentscheidung des Eintrags **2026-07-11
(Issue #175)** ab — dort unter „Verworfen (Details)": „`check_decomposition`
persistiert bewusst über `propose_decomposition` (Reuse aller
Artefakt-/Revisions-Pfade) statt eines eigenen Writers", und Alternative (d), die den
`printability_override=…`-Wieder-Schreibweg als bewusst gewählt begründete. Die
Wiederaufnahme lohnt, weil ADR-018 einen benennbaren Rang hat: die eine Schreibstelle
soll ihre Sperre nur über die kurze RMW-Sektion halten, nicht über eine
Neubewertung mit IK-Sampling. Der alte Eintrag bleibt unverändert stehen.

**Erwogene Alternativen.**
- *Beibehalten (Reuse über `propose_decomposition`)* — verworfen: hält die
  180-Zeilen-Neubewertung unter der Sperre und lässt den Paar-Kontrakt-Seitenkanal
  stehen; genau die zwei Befunde, die #198 adressiert.
- *Eigener Zweit-Writer für die Stufe-2-Ergebnisse* — verworfen (schon 2026-07-11,
  hier bestätigt): ein zweites Artefakt-/Veraltungs-Schema. Stattdessen **eine**
  geteilte Persistier-Tür mit genau zwei Aufrufern (echter Seam).
- *Persistier-Tür ohne eigene Sperre, Caller hält den Lock* — verworfen: bräche
  ADR-018s Grep-Kriterium (jede `write_project`-Stelle liegt in einem
  `with project_lock`-Block). Die Tür (re-)nimmt den **reentranten** `project_lock`
  selbst (RLock, ADR-018) — der Caller hält den äußeren Lock über seine
  Lese-/Supersede-Sektion, das Nesting ist ein No-op.

**Entscheidung.**
1. **`_persist_decompose_run(slug, project_dir, source, job_id, bundle, section_overrides,
   *, runs_dir=None, last_pruef=None)`** — der 79-Zeilen-Persistier-Block als eine interne
   Tür (Vorbild `JobMutation`/`mutate_print_job`): schreibt `decompose.json` + die
   Plan-Eingaben/den Lauf-Verweis in den Druckjob (ADR-016), rechnet **nichts** neu.
   Genau zwei Aufrufer.
2. **`DecomposeBundle`** — Wertobjekt mit der `decompose_artifact`-Parameterliste
   (plan, statuses, module_checks, placement_checks, module_poses, freigang,
   printability …) plus dem, was `sections`/`DecomposeResult` brauchen (pruef_scope,
   Roboter-/Endeffektor-Name, wall_global_id, module_limits). Ersetzt den
   Seitenkanal: der interaktive Stufe-1-Aufrufer und der Stufe-2-Aufrufer reichen
   dasselbe sichtbare Bündel durch dieselbe Tür.
3. **`propose_decomposition`: 12 → 10 Parameter** — `printability_override`/`last_pruef`
   entfallen, der Paar-Kontrakt verschwindet. Die Aktion rechnet nur noch Stufe 1
   (`assess_plan` ohne Orakel), schnürt das Bündel, ruft die Tür mit `last_pruef=None`.
4. **`check_decomposition` Phase 3 = Reload + Supersede-Wächter + Persistier-Tür.**
   plan/statuses/freigang aus Phase 1, das Urteil aus Phase 2; die billigen reinen
   Zusatz-Befunde (`_decompose_findings`: Modulgrenzen/Modul-Lage/Sicherheitsabstand —
   pure Funktionen des Plans) dürfen unter der kurzen Sperre bleiben. **Keine**
   `plan_for_job`/`evaluate`-Neubewertung mehr unter der Sperre. `last_pruef` gesetzt
   (global/Fokus). Da das Feld allein an `last_pruef` hängt (nicht mehr am
   Override-Paar), fällt der unsichtbare Kontrakt weg.

**Begründung.** Der Seam ist echt (zwei Aufrufer, ein Vertrag), nicht bloß eine
Extraktion für einen Aufrufer. Die Phase-3-Sperre ist jetzt das, was ADR-018 verspricht:
nur die RMW-Sektion. Byte-Gleichheit: die Tür reproduziert die Artefakt-Felder, die
Veraltungs-Logik (cutplan vs. Pro-Abschnitts-Zähler) und den `last_pruef`-Schnappschuss
unverändert; die reinen Findings sind Funktionen des Plans (Phase-1-Plan == Reuse), das
API-/Viewer-Verhalten bleibt gleich. Bewusst in Kauf genommen: Phase 3 nutzt den
Phase-1-Plan (`strict_overrides=False`) statt einer strikten Neuableitung — genau der
Plan, gegen den die Prüf-Tür tatsächlich urteilte (konsistenter, kein zweiter
Rechenpfad).

**Verifikation.** `ruff check core` grün; **eigene Tür-Tests**
`test_persist_decompose_run.py` (Bundle→Lauf+Job ohne `last_pruef`; Marker samt
Eingabe-Schnappschuss; fehlender Druckjob wirft; reentrant unter gehaltenem
Projekt-Lock — die ADR-018-Kante); `test_pruef_check` (Entkopplung, `last_pruef`
global/Fokus, Supersede bei parallelem Schreibzugriff, Fortschritt/Abbruch,
Hintergrundlauf), `test_decompose`/`test_section_overrides_pipeline`/`test_module_export`/
`test_export` grün; volle Core-Suite + `pytest -m slow -k denkmal` grün. Kein
README-Abschnitt (keine nutzersichtbare Funktion; interne Persistier-Naht), kein neuer
ADR (die Entscheidung bedient ADR-018, sie ändert es nicht).

## 2026-07-13 — #193 umgesetzt: Übernahme-Protokoll als getesteter Vertrag — `ui/job-adopt.ts`, 7+ main.ts-Handkopien normalisiert

**Frage.** Die Nachzieh-Sequenz nach jeder Core-Antwort mit frischen
`print_jobs` (aktiven Druckjob übernehmen → setSections-Fanout → ▪-Marker →
veraltet-Badges → ggf. Restore/Neubewertung) existierte als 7+ divergierende
Handkopien im vitest-untestbaren `main.ts`. Normalisieren (Abweichung = Bug)
oder Divergenzen konservieren? — Entschieden im Grill 2026-07-13
(Architektur-Review, Punkt 6): **normalisieren**; tragende Abweichungen werden
benannte Optionen mit eigenem Testfall.

**Entscheidung.** Ports-Muster von `placement-apply.ts` verallgemeinert:
`ui/job-adopt.ts` mit `adoptJobResponse(ports, response, opts?)` besitzt
Mitglieder-Menge und Reihenfolge als vitest-Vertrag (`job-adopt.test.ts`,
calls-Array-Assertion, 9 Tests). Der eine default-Job-Selektor heißt
`findJob` und lebt nur noch dort — `main.ts` enthält kein
`j.job_id === "default"` mehr. Alle Flüsse laufen über den Vertrag:
onStandModeChange (beide Schritte), onContextCheckChange, onDecompose,
onCheckApplied, onModuleLimitsChange, pollPruefCheck, processParams
onSave/onSaveSections, onSaveOverride, beide Advisor-onApply
(process-params-Zweige), onOpenProject und restoreDecomposition.
`applyPlacementOverride` behält sein Interface und delegiert intern
(zwei Adapter am selben Vertrag; `placement-apply.test.ts` unverändert grün);
`onSaveOverride` ist jetzt ein Einzeiler über `applyPlacementOverride`.

**Als Bug behoben (Normalisierung):**

1. `restoreDecomposition` lief ohne `refreshRevisions` — jetzt Teil des
   Protokolls (onOpenProject verliert dafür drei redundante Einzel-Setzungen:
   Stepper-, Palette- und Export-Revisionen kommen aus dem einen Schritt).
2. `onStandModeChange`/`onDecompose`/`onCheckApplied`/`pollPruefCheck` ließen
   die Prozessparameter-Teilformulare aus dem setSections-Fanout aus — nach
   einer frischen Zerlegung zeigten die Gilt-für-Formulare veraltete Teile.
3. `onSaveOverride` hatte die Reihenfolge gegenüber dem getesteten Vertrag
   direkt daneben vertauscht (▪-Marker VOR dem Formular-Restore) — jetzt
   exakt die placement-apply-Sequenz.
4. Bare-Persistenz-Flüsse (onContextCheckChange, onModuleLimitsChange,
   setStandMode-Schritt 1) übernehmen jetzt über das Protokoll (Marker/Badges
   idempotent — diese Routen veralten nichts).

**Benannte Optionen (tragende Abweichungen, je eigener Testfall):**

- `druckplan: "panel-owns"` — die Zerlegungs-Ansicht wendet die Antwort selbst
  an (Rückgabewert/Generation-Guard #45): onStandModeChange, onDecompose,
  onCheckApplied. Der Fanout überspringt genau sie, nichts sonst.
- `restore: "process-params"` — Teil-Platzhalter an neue globale Werte ziehen
  (#82/#92): processParams onSave, Advisor-Anwenden. `onSaveSections` setzt
  die Option bewusst NICHT: ein restoreFromJob würde dort ungespeicherte
  Eingaben des jeweils anderen Scopes (gestashte Formulare) verwerfen.
- `restore: "placement"` + `reevaluate` — der Platzierungs-Override-Vertrag
  (#161/#172), von `placement-apply.ts` gesetzt.

**Nicht angefasst (beobachtete Kandidaten, eigenes Issue nötig):**
`onSimulate` übernimmt den Job bewusst weiterhin nicht (liest nur
`section_runs`; eine Übernahme wäre Verhaltensänderung), ebenso die
Roboter-/Tool-/Wand-Flüsse (rufen nur `refreshRevisions`, adoptieren nie —
`currentActiveJob` bleibt dort potenziell stale, #161-verwandt).

**Verifikation.** vitest 77 Dateien / 976 Tests grün (neu: `job-adopt.test.ts`
9, `placement-apply.test.ts` unverändert 3); `tsc --noEmit` + `vite build`
grün. `ui_smoke.mjs` (Headless-CDP, Edge) kontrolliert verglichen: Projekt-
Zustand vor jedem Lauf zurückgesetzt, Baseline (gestasht) vs. Branch je 2×
— identische Fehlbild-Menge (6 vorbestehende Umgebungs-/Timing-Flakes:
Modul-Simulations-Timing, Bibliotheks-Canvas 0×0 headless, Deeplink-Lauf ohne
Warnungs-/Dauer-Daten; Baseline schlug in einem Lauf sogar 9× fehl), keine
Regression durch #193. Kein README-Abschnitt (keine nutzersichtbare Funktion —
inneres Viewer-Protokoll), kein ADR (bedient ADR-007/016, ändert sie nicht);
Glossar-Begriff „Übernahme-Protokoll" stand bereits in viewer/CONTEXT.md.

## 2026-07-13 — #196 umgesetzt: Wand-/Teil-Fokus als focus-store — ein Halter, Subscriber-Vertrag statt 7 Kopien und 10-Ziel-Kaskade

**Frage.** „Welches Teil ist fokussiert" lag als 7 Kopien in 7 Dateien
(druckplan.ts Quelle; main.ts `currentFocusedSection`, scope-switch,
process-params, placement-override, simulation, collision-advisor), synchron
gehalten allein durch die handgepflegte 10-Ziel-Kaskade `onFocusChanged`
(main.ts) plus zweiten Pull-Pfad (8 `getFocusedSectionId`-Pollstellen) und
einen Zwei-Hop-Sonderweg über den Gilt-für-Umschalter. Einziger Sync-Nachweis:
der Headless-Smoke mit Debug-Hooks. Wie zu EINEM Halter machen?

**Alternativen.** (a) Store mit Panel-Selbst-Subscriptions (jedes Panel
abonniert selbst — Reihenfolge implizit aus Konstruktionsreihenfolge, nicht
testbar); (b) Store + EIN registrierter Subscriber, der die Wirkungen als
benannte, geordnete Vertragsliste abarbeitet (job-adopt-Muster #193);
(c) nur Kopien durch `get()` ersetzen, Kaskade behalten.

**Entscheidung: (b).** Neu `ui/focus-store.ts` (DOM-frei): `FocusStore` mit
`get()/toggle()/reconcile()/subscribe()` (No-ops feuern nicht) — absorbiert
die `focus-state.ts`-Logik (#84), die Datei entfällt samt produktions-toter
Exporte (focusSection, clearFocus, isFocused). Die Kaskade wird
`FOCUS_EFFECT_ORDER` (11 benannte Wirkungen; Highlight → Marker↔Mesh →
Gilt-für-Umschalter → Slicing-Scope → Platzierungsfelder → Titel → Druckort →
Kamera → Live-Vorschau → Sim-Dock → Kollisions-Advisor) +
`registerFocusEffects(store, ports)` — Mitglieder + Reihenfolge sind
vitest-Vertrag (`focus-store.test.ts`), main.ts liefert nur die Effekte.
Details:

- **druckplan.ts delegiert**: `focusSection` → `store.toggle`,
  `_reconcileFocus` → `store.reconcile` (deckt den Fall „Teil verschwindet
  durch Neuzerlegung"); Palette/Prüf-Tür rendern über eine eigene, VOR den
  Effekten registrierte Subscription (bisherige Reihenfolge bleibt).
  `getFocusedSectionId` entfällt; die 8 main.ts-Pollstellen lesen
  `focusStore.get()`.
- **Panels lesen statt Kopien zu halten**: simulation/placement-override/
  collision-advisor bekommen den Store als `FocusReader` injiziert
  (`setFocusedSection`/`setScope`-Füttersetter entfallen); der
  Kollisions-Advisor löst den Teil-Namen zur Renderzeit über einen
  `partName`-Callback auf.
- **Gilt-für-Umschalter ohne Fokus-Kopie**: scope-switch hält nur noch die
  Radio-**Stellung**; `scope-state.ts` wird von `ScopeState` auf
  Choice-Funktionen umgestellt (`selectScopeChoice`/`reconcileScopeChoice`/
  `effectiveScope(choice, focusedId)`). Der Zwei-Hop-Pfad zu process-params
  entfällt: das Kaskaden-Mitglied `syncProcessParamsScope` ruft
  `processParamsPanel.setScope(scopeSwitch.scope, id)` direkt (ein Hop, NACH
  `reconcileScopeSwitch`); `onScopeChanged` feuert nur noch für Radio-Klicks.
- **Bewusst KEINE Fokus-Kopie, aber Zustand geblieben**: process-params behält
  `_scope/_sectionId` als Adresse des GEZEIGTEN Formulars — sie muss dem Store
  nachlaufen, bis `setScope` den alten Stand gestasht hat (sonst gingen
  ungespeicherte Eingaben verloren); als Kommentar dokumentiert.
- **Debug-Hooks trivial statt weg**: `__focusDebug().focused` ist jetzt
  `focusStore.get()` (der Smoke nutzt die Hooks weiter als Sichtbarkeits-,
  nicht mehr als Sync-Orakel); `__focusSection` läuft unverändert über
  `druckplanPanel.focusSection` → `store.toggle`.

**Bekannte, kleine Verhaltensangleichung** (Divergenz der Kopien war der
Punkt): `simulationPanel.reset()` nullte bisher NUR die eigene Fokus-Kopie
(druckplan behielt den Fokus bis zum nächsten reconcile). Mit einem Halter
teilt das Sim-Dock jetzt exakt den Palette-Fokus — verschwindet ein Teil,
räumt `reconcile` beide gemeinsam.

**Verifikation.** vitest 77 Dateien / 981 Tests grün (neu:
`focus-store.test.ts` 13, portiert die focus-state-Fälle + Vertrag);
`tsc --noEmit` + `vite build` grün. `ui_smoke.mjs` (Headless-CDP, Edge)
baseline-verglichen (Branch → stash/Baseline → Branch): Fehlbild-Menge des
Branch-Laufs (4) ist Teilmenge der Baseline (6) — verbleibend nur die
vorbekannten Umgebungs-/Timing-Flakes (Bibliotheks-Canvas 0×0 headless,
Deeplink-Warnungen/Stundenformat) plus ein VORBESTEHENDER 2k-Befund
(Druckort-Umschalter-Verfügbarkeit im Reiter Zerlegung, identisch in der
Baseline; Kandidat für ein eigenes Issue). Alle Fokus-Checks (2c/2f/2g/2h/2i)
grün. Kein README-Abschnitt (inneres Viewer-Muster, nicht nutzersichtbar),
kein ADR (reiner Sicht-Zustand, bedient ADR-007).

## 2026-07-13 — Py↔TS-Paritätshälften schließen + `last_pruef`-Semantik (Issue #194)

**Frage.** Der ADR-009-Paritätsbeweis hatte Löcher: drei Zwillinge (`fk`,
`nozzle-quat`, `nozzle-schablone`) hatten ein Golden, aber **keinen pytest-Leser**
(Halbschleife), drei Syncpunkte der Ganzjob-/Prüf-Familie standen „nur per
Kommentar", und die CI (ein Job) fuhr ruff+pytest, **null vitest** — eine bewusste
Core-Änderung (DH, `nozzle_quat`-Konvention, Revisions-Konstanten) konnte grün
durchlaufen. Zudem eine reale Drift: `last_pruef` **ohne** `input_snapshot` ergab
TS `"missing"`, Python aber `"current"`/`"stale"` — trotz Kommentar „bit-gleicher
Zwilling".

**Entscheidung.**
- Neues `core/tests/test_viewer_goldens.py` liest alle bislang offenen Viewer-
  Goldens: `fk` (Gliedposen via `OpwKinematics.link_frames` in fk.test.ts-Toleranz
  **plus** exakter DH-Abgleich gegen `RobotDef`), `nozzle-quat` (8 Fälle exakt),
  `nozzle-schablone` (Orientierung je Bahnpunkt aus `nozzle_quat`).
- Ganzjob-/Prüf-Familie bekommt ein geteiltes Golden `viewer/src/ui/staleness.golden.json`
  (`viewer/scripts/gen_staleness_golden.py`): `constants` (die sechs Kommentar-
  Syncpunkte — `INPUT_KEYS`, `OUTPUT_DEPS`, `SECTION_OUTPUT_JOB_DEPS`,
  `SECTION_AGGREGATE_OUTPUTS`, `PRUEF_DEPS`, `PER_REP_SECONDS`), `output_cases`,
  `pruef_cases`. pytest **und** vitest deep-equalen die Konstanten und rechnen die
  Fälle nach. Dafür bekam `staleness.ts` ein Laufzeit-`INPUT_KEYS`-Array (Typ daraus
  abgeleitet) und ein benanntes `SECTION_AGGREGATE_OUTPUTS` (löst den hartkodierten
  `output === "druckplan"`-Zweig ab); `pruef-check-state.ts` exportiert `PER_REP_SECONDS`.
- **Schablonen-Tangente ins Golden.** Die Vorwärtsdifferenz (`pathTangent`) ist
  TS-Domäne, nicht Core — darum steht die Tangente jetzt als **Eingabe** je Fall im
  Golden (der Python-Nachbau `_tangent` in `gen_nozzle_golden.py` entfällt). pytest
  prüft die Core-Hälfte `nozzle_quat(tangent)==quat`, vitest die TS-Hälfte
  `pathTangent(path,i)==tangent` — beide Halbschleifen zu.
- CI: zweiter Job `viewer` (`npm ci` + `npm test` + `run build`).

**`last_pruef`-Kante — Alternativen.** (a) Python behält den Legacy-Fallback
(fehlender Schnappschuss = Null-Basis → rechnet Veraltung, meist `"current"`), TS
zieht nach; (b) TS hält den Vertrag (kein Schnappschuss ⇒ `"missing"`), Python zieht
nach. **Gewählt: (b).** Ohne Schnappschuss lässt sich Aktualität nicht *beweisen*;
ein `"current"` wäre genau das stille Grün, das ADR-013 („Befund, kein stilles
Grün") verbietet — `"missing"` (= „ungeprüft") ist die ehrliche Anzeige. Der
Legacy-Fallback hatte keinen realen Zweck (ein echter Prüfstand trägt immer den
vollen `pruef_input_snapshot`); er war nur eine unbeabsichtigte Null-Basis-Rechnung.
`revisions.pruef_status` gibt jetzt `"missing"` bei fehlendem **oder leerem**
`input_snapshot`; `pruefStatus` (TS) behandelt zusätzlich das leere `{}` als
`"missing"` (vorher: `{}` ist truthy → hätte gerechnet). Der Widerspruch ist als
Golden-`pruef_case` verewigt und war vor dem Angleich rot (reproduziert), danach grün.

**Verifikation.** pytest `test_viewer_goldens.py` 7 grün; volle Core-Suite grün;
vitest 77 Dateien / 987 Tests grün; `tsc --noEmit`+`vite build` grün; ruff grün.
Drift-Probe: eine künstliche `nozzle_quat`-Störung färbt den pytest-Leser rot
(Guard greift). Kein README (interner Paritäts-/Testvertrag, nicht nutzersichtbar);
kein neues ADR (bedient ADR-009/ADR-013/ADR-017).

## 2026-07-13 — Parity-Harness als tiefes Modul: Manifest + Gen-Treiber + EIN pytest (Issue #195)

**Frage.** Der ADR-009-Paritätsbeweis war nach #194 zwar geschlossen, aber eine
unerzwungene 6-Schritte-Konvention: 5 Gen-Skripte mit identischem Skelett,
verstreute handgeschriebene Leseschleifen (pytest in test_viewer_goldens/
test_process_params_sections/test_export, vitest je Datei), drei
Vergleichs-Mechaniken (toEqual / toBeCloseTo(…,12) / Quaternion-Toleranz) — und
sie degradierte messbar (#74 entstand am selben Tag ohne Golden wie #82 mit;
#175 wieder ohne; 0 Treffer „Golden|Zwilling|Parit" in docs/agents/). Wie wird
die Konvention ein Modul?

**Alternativen.** (a) Nur Doku (Rezept in docs/agents/, Skripte bleiben) — die
Degradation ist ein Erzwingungs-, kein Wissensproblem; (b) Manifest als
eigenes Skript unter viewer/scripts mit sys.path-Import in pytest — Import-
Hack, zweite Wahrheit neben dem Core; (c) **Manifest als Core-Modul
`fgc.parity`** mit Gen-Treiber und parametrisiertem pytest darüber. **Gewählt:
(c).**

**Entscheidung.**
- **`core/src/fgc/parity.py`** ist die eine Registratur: `golden_doc(path,
  comment, header?, ensure_ascii?)` je Golden-Datei + `register(pair, fn,
  cases, golden, compare?, case_builder?, block?, doc_check?)` je Paar;
  Default-Skelett ist `{**case, "expected": fn(case)}` + bit-gleicher
  Vergleich. Heterogene Paare werden nicht zwangs-manifestiert: eigener
  `case_builder`/`compare` (fk: Toleranz + DH-`doc_check`; nozzle-schablone:
  Posen-Bau), `cases=None` registriert einen Konstanten-Block (`fn(None)`
  deep-equal — staleness-constants). Mehrere Paare teilen sich eine Datei
  über `block` (staleness: constants/output_cases/pruef_cases).

## 2026-07-15 — Messstudie: Abstand-Sweep belegt, dass Höhen-Zerlegung eine Machbarkeitsbedingung ist (≥4 Bänder)

**Frage:** Der automatische Vorschlag platziert Modul 1 (denkmal) bei 230 mm und
kollidiert tief; die Domänen-Intuition war „Modul weiter weg → unten kollisionsfrei,
oben nicht mehr in die Ecken → nur in der Höhe teilen (2 Module)". Stimmt das
quantitativ, und wie viele Bänder braucht es wirklich?

**Vorgehen:** Neue reproduzierbare Messstudie unter
`experiments/collision_standoff_sweep/` (Skript + Plots + Rohdaten). Für Modul 1
(`abschnitt-1`, 785×822 mm, `modul`-Modus, am Boden) wird `standoff_mm` von 150 bis
1200 mm über den Produktivpfad (`sectionsim.slice_and_simulate_section` +
`section_collision_finding`, `Override(placement=…)`) durchgefahren. Je Bahn-Sample:
signierte Mindestdistanz + verursachendes Glied (`causer_link`); Höhe aus der
Toolpath-Schicht (`druckstand.layer_per_sample`); Erreichbarkeit je Höhe aus den
verorteten IK-`reach`-Warnungen (`trajectory.meta.warnings[].t_s`).

**Befund:** (1) Kein einziger Abstand macht den vollen 822-mm-Modul gleichzeitig
kollisionsfrei **und** erreichbar. Nah (≈230 mm) voll erreichbar, aber ~8000 rote
Samples (Durchdringung bis −258 mm); fern (800–850 mm) rot=0, aber 56–61 % des
Pfades unerreichbar. (2) Die max. von unten zusammenhängend **machbare** Bandhöhe
über alle Abstände ist ≈ **260 mm** (bei standoff 400 mm) ⇒ Modul 1 braucht
mindestens ⌈822/260⌉ = **4 Höhenbänder, nicht 2**. (3) Das limitierende Glied
wandert mit Abstand/Höhe (link_2 Oberarm → link_4 Unterarm → link_5 Handgelenk →
Werkzeug); „Schulter unten, Unterarm oben" ist nur eine Näherung.

**Entscheidung/Konsequenz:** Kollision und Erreichbarkeit sind im Abstand gegenläufig
(„Schere"); die Zerlegungs-Zielfunktion muss beide Achsen **je Höhenzone** führen
(Abstand `d` mit `reach(d,h)≥Schwelle` **und** `Mindestdistanz(d,h)≥Sicherheit` für
alle `h` der Zone; Schnitte dort, wo die machbare Region endet) und die Zahl der
Bänder/Fugen minimieren. Kein ADR (Messstudie, keine Architektur); Doku in
`experiments/collision_standoff_sweep/README.md`. **Offen:** Wandstärke-Diskrepanz
(Projekt 510 mm vs. UI „176 mm") vor Absolutwert-Aussagen im Paper klären; Studie
bislang ein Modul/ein Projekt.

## 2026-07-15 — Dicken-Studie: Wandstärke schrumpft die machbare Region; dicke+lange Module nicht druckbar; nativer fcl-Crash

**Frage:** Wie hängt die machbare Region (kollisionsfrei & erreichbar) von der
**Wandstärke** ab? Anschlussmessung zur Abstand-Sweep-Studie, über mehrere reale
Wände statt einer.

**Vorgehen:** `sweep_thickness.py` fährt den Abstand-Sweep über 7 reale,
**öffnungsfreie** Wände des denkmal-Modells (256 Wände, 161 öffnungsfrei via
`opening_count==0`), kuratiert auf Höhe ≈ 3060 mm (fast konstant), Dicken 80–620 mm.
Je Wand frische Modul-Zerlegung (`plan_for_job`, Modul 0), `pc.wall` aus IFC-
Geometrie (Assessment-Pfad umgangen). **Wandstärken-Frage geklärt:** die „176 mm"
aus dem UI-Screenshot waren eine andere Wand als die gemessene 510-mm-Wand (vom
Nutzer bestätigt).

**Befund:** (1) Dickere Wände schrumpfen die machbare Bandhöhe klar (≈760 mm bei
80–130 mm → 300 mm bei 300 mm Dicke); die **620-mm-Wand hat gar keine machbare
Region** (Bandhöhe 10 mm — bei keinem Abstand druckbar). (2) Die **Modul-Länge ist
ein starker Mit-Treiber** (Confound): die Einbrüche bei 300 mm und 620 mm sind die
längsten Module (~1100 mm), die 489-mm-Wand erholt sich (kürzeres Modul). ⇒ Dicke
UND Grundriss bestimmen die Bänderzahl gemeinsam. (3) **Nativer Crash:** die
505-mm-Wand (`2d9LuxY1D3owMKr995JmXw`, öffnungsfrei) lässt python-fcl/VHACD mit
0xC0000005 abstürzen — kein Python-`try/except` fängt das; deshalb je Wand ein
Subprozess (Isolation).

**Entscheidung/Konsequenz:** Die Zielfunktion muss Dicke *und* Modul-Grundriss
führen, nicht nur die Höhe. Confound bewusst nicht herausgerechnet (Nutzer wollte
„reale Wände, wie sie sind"), aber in `figT1` per Punktfarbe transparent gemacht.
Kein ADR. Doku im README (Abschnitt „Dicken-Studie"). **Offen:** nativer fcl-Crash
als Issue diagnostizieren; ggf. Studie mit fixem Grundriss zur Dicken-Isolierung
wiederholen.

## 2026-07-15 — IK-Pilot: die richtige Einzel-Konfiguration hebt die machbare Bandhöhe um +80 %; Konfig-Übergänge unnötig

**Frage (Validität):** Die Abstand-/Dicken-Studien nutzten *eine* IK-Konfiguration
(auto von `select_along_path`, optimiert auf Bahn-Kontinuität, nicht Kollision). Der
Doosan hat 8. Sind die gemessenen Kollisionen Konfigurations-Artefakte?

**Vorgehen:** `sweep_ik.py` fährt den Abstand-Sweep am denkmal-Modul 0
(785×822 @ 510 mm, base=0) für alle 8 Konfigs (shoulder×elbow×wrist) + auto durch;
`Override(placement, ik_config)` erzwingt je Konfig. Strenge Latte (reach ≈ 100 % &
grün). Methodischer Plan zuvor per Grilling festgezurrt (Prädikat `druckbar(W,H,T)`,
Achsen W/H/T, optimiert über Abstand+Basishöhe+IK, seitl. fix zentral, synthetische
Quader fürs Gitter).

**Befund:** (1) IK-Konfigwahl rettet stark: beste Einzel-Konfig `baa` (Schulter-Flip)
gibt H_max = 450 mm vs. auto/aaa 250 mm — **+80 %**. Alle übrigen 6 Konfigs ~10 mm
(fast überall unerreichbar). (2) **Stufe a unnötig:** die per-Zelle-Union (freies
Konfig-Wechseln, optimistischer Bound) liefert *ebenfalls* 450 mm — eine einzelne
Konfig fürs ganze Modul holt den vollen Gewinn, kein Travel-Übergangsmodell nötig.
(3) auto reproduziert Studie 1 (bei d=300 red=3726 == aaa) — die auto-Wahl ist eine
bestimmte, kollisions- unbewusste Konfig.

**Entscheidung/Konsequenz:** IK-Konfiguration wird ein **modulweiter Hebel** in der
Zielfunktion (welche der 8 fürs ganze Modul), neben Abstand + Basishöhe; die
b→a-Staffelung endet bei **b** (keine Übergänge). Die früheren Einzel-Konfig-Studien
sind ~80 % pessimistisch — beim Prädikat-Gitter wird über die 8 Konfigs optimiert.
Kein ADR. Doku im README (Abschnitt „IK-Konfiguration").

## 2026-07-15 — Basishöhen-Pilot: Roboter-Podest hilft, aber mit Optimum (~300 mm); Über-Anheben kippt

**Frage:** Wie viel bringt ein Roboter-Podest (Basishöhe `stand_height_mm`), und ist
„höher = besser"? Der Roboter kann heute nicht hoch — lohnt der Umbau?

**Vorgehen:** `sweep_ik.py --base-heights 0 300 600` am denkmal-Modul 0, je Basishöhe
über alle 8 IK-Konfigs best-over-8 (Einwand des Nutzers: Gewinner-Konfig kann sich mit
der Basishöhe verschieben — also nicht `baa` festhalten). Probe bestätigte vorab, dass
`stand_height_mm` im modul-Modus greift (base=600 räumte bei einem Punkt die Kollision
komplett ab: red 2454→0).

**Befund:** Umgekehrtes U. H_max(beste Einzel-Konfig): 0 mm → 490, 300 mm → **640**,
600 mm → 170. (1) Optimum ~300 mm (+150 mm vs. Boden). (2) **Über-Anheben (600 mm)
kippt** — Basis blickt von oben, Wandfuß unerreichbar, H_max (von unten zusammenhängend)
bricht ein. (3) **Gewinner-Konfig verschiebt sich** (baa→aab bei 600 mm) — bestätigt
empirisch, dass die optimale IK setup-abhängig ist. (4) Kombiniert: base0/auto ~250 →
IK(baa) 490 → +Podest(300) 640 ≈ **2,5×**. (5) Konfig-Mischen (Stufe a) nur bei 600 mm
relevant (union 390 >> single 170); am Optimum 300 mm baa allein = 640.

**Entscheidung/Konsequenz:** Basishöhe wird ein **grob diskreter Hebel mit Optimum** in
der Zielfunktion (nicht monoton maximieren). Alle drei Hebel (Abstand, IK, Basishöhe)
sind wirksam und werden gemeinsam optimiert; IK-Gewinner nie hartkodiert. Nebenprodukt:
ein ~300-mm-Podest rechtfertigt sich (2,5× Bandhöhe). Kein ADR. Doku im README
(Abschnitt „Basishöhe / Roboter-Podest").
- **Gen-Treiber `viewer/scripts/gen_goldens.py [pair …]`** (`generate()` im
  Modul) regeneriert alle 6 Golden-Dateien in einem Lauf; die 5 Skelett-Kopien
  (gen_fk/nozzle/section_params/staleness_section/staleness) sind gelöscht.
  Bit-Identität verifiziert: ein Gen-Lauf mit den alten `_comment`-Strings
  reproduzierte alle 6 Dateien byte-gleich (git diff leer); danach nur die
  `_comment`-Zeilen auf gen_goldens.py umgestellt.
- **EIN parametrisierter pytest** `test_parity.py::test_golden[pair]` über
  `MANIFEST` (`fgc.parity.verify`): fehlende Datei, fehlender/leerer Block,
  Fall-Anzahl-/Namens-Drift und Ableitungs-Drift werden rot — ein
  Manifest-Eintrag ohne Golden ist ab jetzt sichtbar. Rückrichtung:
  `test_every_golden_registered` (jede `viewer/src/**/*.golden.json` gehört
  einem Paar). Die #194-Handleser (test_viewer_goldens.py) und die zwei
  älteren Voll-Schleifen-Leser (test_process_params_sections, test_export)
  gehen darin auf.
- **Viewer-Helper `expectGoldenParity(cases, fn, compare?)`**
  (`viewer/src/test/golden-parity.ts`, ~20 LOC): die eine vitest-Leseschleife
  (leere Fall-Liste schlägt fehl, Default deep-equal auf `expected`); alle 8
  bestehenden Golden-Loops (fk, nozzle-quat, nozzle-schablone ×2,
  section-params, staleness output/section, pruef) laufen darüber. Stolperer:
  Constraint `C extends { name?: string }` scheiterte an TS-weak-type-Regel
  für die namenlosen fk-Fälle → `C extends object` + Cast im Label.
- **Rezept-Doku `paritaet.md`** (Zwilling N+1 = 1 Manifest-Eintrag
  + 1 TS-Funktion + 3-Zeilen-vitest) + Verweis in CLAUDE.md (Agent skills) —
  schließt die 0-Treffer-Lücke.

**Verifikation.** Gen-Lauf bit-identisch (s. o.); ruff grün; pytest
test_parity 9 grün (8 Paare + Registratur); vitest 77 Dateien / 987 Tests
grün; tsc + vite build grün; volle Core-Suite grün. README: Verweise der
vier Funktions-Abschnitte auf die alten Gen-Skripte auf gen_goldens.py
umgestellt (kein neuer Abschnitt — interner Testvertrag, nicht
nutzersichtbar); kein ADR (Mechanisierung von ADR-009, keine neue
Architekturentscheidung).

## 2026-07-13 — #199 umgesetzt: Diff-dann-bump im Seam `mutate_print_job` — `JobMutation` deklariert beobachtete Pfade

**Frage.** Die Veraltungs-Semantik des tiefen revisions-Kerns (ADR-017) leckte
als Aufrufer-Konvention: 9 Setter wählten selbst unter 3 Bump-Konventionen
(3× immer-bumpen, 2× Hand-Diff im Setter, 4× bewusst-nie), `set_robot`
(`reassess_walls_for_robot`) umging den Seam ganz. Realisierter Bug dieser
Bauart: #161 (B16/B32). Wie wird das Diff EIN getesteter Mechanismus statt
je-Setter-Code?

**Alternativen.** (a) `JobMutation` deklariert **beobachtete Feldpfade**, der
Seam difft Alt gegen Neu einmal (Grill-Schritt 1); (b) gleich die 4
Pseudo-Dep-Familien (OUTPUT_DEPS, section, section_total, PRUEF_DEPS) zu
EINEM deklarativen Dep-Modell vereinheitlichen; (c) belassen.

**Entscheidung: (a)** — (b) bleibt ausdrücklich Non-Goal bis zum nächsten
Feuern des ADR-017-Triggers (#116/#187). Umsetzung:

- **`JobMutation` neu (hart, ohne Aliase):** `bump_if_changed:
  dict[input_key, tuple[Pfad, ...]]` (gepunktete Pfade, echo-fest),
  `bump_sections_if_changed: str` (EIN section-gekeyter Pfad — Dict
  `{sid: Block}` wie `process_params.sections` ODER Liste mit
  `section_id`-Feld wie `section_overrides`; Reihenfolge egal) und
  `bump_always` (expliziter Rebuild-Modus). `bump_inputs`/`bump_sections`
  sind ersatzlos weg; leere Deklaration bleibt das sichtbare „BEWUSST kein
  Bump".
- **Vergleichs-Vertrag des Seams:** leer == nicht gesetzt (`{}`/`[]`/`None`
  gleichwertig, wie die abgelösten Hand-Diffs mit `… or None`); unbekannte
  Eingabe-Stufen in der Deklaration schlagen sofort fehl (auch ohne
  Änderung — Tippfehler fliegen nicht erst beim ersten Wechsel auf).
- **Hand-Diffs wurden Daten:** `set_placement_override_for_job` (2 Zeilen)
  und `set_process_params` (~12 Zeilen) deklarieren nur noch Pfade;
  `set_tool`/`set_workstation` sind dadurch **gratis echo-fest** (gleicher
  Wert bumpt nicht — die EINZIGE gewollte Verhaltensänderung, getestet für
  alle vier deklarierenden Setter); `set_print_job` sagt `bump_always`
  („wall" — Rebuild, Diff wäre falsch).
- **`set_robot` durch den Seam:** `mutate_print_job` bekommt `missing_ok`
  (fehlender Druckjob ist kein Fehler — nur `overview_run` wird gepflegt)
  und `artifact_updates` (Top-Level-Felder im selben Schreiben);
  `reassess_walls_for_robot` deklariert `bump_always=("robot",)` —
  bedingungslos wie bisher, jeder Aufruf erzeugt einen frischen Befund-Lauf.
- **Bewusst NICHT angefasst:** das dritte Hand-Diff in
  `_persist_decompose_run` (#198) — es ist kein `mutate_print_job`-Setter
  (eigener Run-Write, `refresh_output` NACH den Bumps, strukturell-vs-
  Abschnitt-Konditional) und bleibt beim nächsten Schritt auf dem Tisch.

**Grenzfall dokumentiert:** die zwei alten Hand-Diffs normalisierten leere
Blöcke gegensätzlich (Platzierung: leerer Alt-Eintrag ≠ entfernt → bump;
Prozess-Sections: `or {}` → kein bump). Beide Zustände sind durch die Setter
nicht erzeugbar (nur per Hand-Edit des project.json); der Seam wählt
einheitlich „leer == nicht gesetzt".

**Verifikation.** Seam-Tests (test_mutate_print_job) auf die neue
Deklaration umgestellt + neue Fälle (echo, gepunktete Pfade, beide
Section-Formen, missing_ok/artifact_updates, Tippfehler-Fail); Echo-Tests je
deklarierendem Setter (tool/workstation/process/placement); bestehende
Staleness-Tests + TS-Zwillinge (staleness.ts, pruef-check-state.ts,
staleness.golden.json) unverändert grün — reine Seam-Verschiebung, die
Ableitung (`output_status`/`section_output_status`/`pruef_status`) ist
unberührt. Kein README-Abschnitt (nicht nutzersichtbar), kein ADR (ADR-017
regelt WAS veraltet; hier ändert sich nur, WO das Diff gerechnet wird).

## 2026-07-13 — Config-Flip des Singularitäts-Advisors anwendbar (Issue #200, ADR-024 Punkt 4)

**Frage.** Der Singularitäts-Advisor emittierte für den Schulter-/konfig-
abhängigen Typ ein rohes opw-Bitfeld (`Suggestion.config: int`, 0 Konsumenten
im Repo; UI-Text „Konfiguration auf Bitfeld {n} flippen"); der Anwenden-Knopf
war hart totgelegt (`applyEnabled=false`), obwohl die persistierbare
IK-Konfiguration seit #129 als a/b-Block über `set_process_params(ik_config=…)`
produktiv schreibt und **ADR-024 Punkt 4 den ADR-020-Revisionstrigger wörtlich
für erfüllt erklärt**. Wie zieht der Code den Vollzug nach?

**Alternativen.**
- *Bitfeld beibehalten, im Viewer nach a/b übersetzen:* verworfen — zweite
  Übersetzungsstelle neben `IkConfigFilter.from_block`, und der Viewer soll
  nicht rechnen (ADR-007). Die Übersetzung gehört an **eine** Core-Stelle.
- *Vollen Zielpose-Block (alle 3 Achsen) fixieren:* verworfen — die
  Ellbogen-/Handgelenk-Bits gelten nur für die *eine* schlechteste Pose;
  bahn-weit fixiert würden viele Bahnpunkte unerreichbar. Der Schulter-Hebel
  fixiert **nur die Schulter**, Rest bleibt auto (drei Einzelschalter).
- *Ein-Pose-Marge weiterreichen (wie bisher):* verworfen — der harte Filter
  betrifft die **ganze Bahn**; eine Marge, die nur die schlechteste Pose
  bewertet, verspricht eine Verbesserung, die bahn-weit nicht gelten muss.

**Entscheidung.**
- **Bit→Block an einer Stelle:** neue `kinematics.select.config_to_block(int)
  → {"shoulder":"a"|"b", …}` als Gegenrichtung zu `IkConfigFilter.from_block`
  (die es bislang 0× gab). Gesetztes Bit → Zweig `"b"`, gelöscht → `"a"`;
  Roundtrip getestet (`from_block(config_to_block(c)).allows(c)` wahr und
  schließt jede andere Konfiguration aus).
- **`_advise_config_flip` bahn-weit + a/b-Block:** liest den aktuellen
  Schulter-Zweig der schlechtesten Pose über `config_to_block`, fixiert die
  Schulter auf den **anderen** Zweig und lässt **dieselbe** `placement.evaluate`
  die Vorher/Nachher-Marge über die gesampelte Bahn rechnen — dafür bekam
  `evaluate`/`AdvisorContext.score` einen `config_filter`-Parameter (durch bis
  `select_along_path`, wo der harte Filter seit #129 sitzt). `Suggestion.config`
  entfällt; neu sind `ik_config` (der Block) + `write`
  (`{"setter":"process-params","ik_config":block}`) — **genau die Form des
  Kollisions-Advisors**. Bahnpunkte, die erst unter der Vorgabe unerreichbar
  werden, sinken ehrlich in die Marge ein und werden im Detailtext als Befund
  benannt (kein Gate, US 14).
- **Viewer:** `applyEnabled=true` für `config_flip` (sobald der Flip die Marge
  hebt — kein Gewinn ⇒ inaktiv, der Advisor beschönigt nicht); neue
  `ApplyAction`-Variante `process-params-ik` → bestehende
  `setProcessParams(ik_config=…)`-Route (dieselbe wie der Kollisions-Advisor,
  jede andere process-params-Gruppe bleibt erhalten). UI-Text nennt den
  **Domänenbegriff** („Schulter auf Zweig b fixieren", `ikConfigLabel`) statt
  „Bitfeld flippen".

**Begründung.** Ein Domänenbegriff (IK-Konfiguration), eine Schreibstelle
(`set_process_params(ik_config)`) — der Seam trägt jetzt zwei echte Adapter
(Kollisions- und Singularitäts-Advisor). „Bahn-weit ehrlich" verhindert das
Kern-Missverständnis, ein Ein-Pose-Flip repräsentiere die ganze Bahn.

**Verifikation.** Core: `test_singularity_advisor` um a/b-Block-Flip,
Payload-Form (`write` == Kollisions-Advisor-Form, kein `config` mehr) und
`config_to_block`↔`from_block`-Roundtrip erweitert; `test_placement`
(advise_singularity end-to-end) grün. Viewer: `singularity-advisor-state.test`
auf a/b-Block + aktiven Knopf + `process-params-ik`-Aktion umgestellt.
ruff + vitest + build grün. Kein neuer ADR (ADR-024 Punkt 4 hatte die
Entscheidung schon getroffen; dieser Eintrag protokolliert den Code-Vollzug).

## 2026-07-13 — Flansch-Ziel-Raster als öffentlicher Seam, coarse ohne Privat-Importe, config_filter am einen Schnitt (Issue #201)

**Frage.** `collision.coarse.path_collides` nähte sich seine Implementation aus
**6 privaten Symbolen zweier Fremdmodule** zusammen (`check._corner_box`/`._matrix`
+ `evaluate._flange_targets`/`._homogeneous`/`._nozzle_rotation`/`._rot_z`) und baute
dabei die **t_wall_base-Invariante ein zweites Mal** (`_homogeneous(_rot_z(yaw),
base_position_in_wall(...))` — dieselbe Kette wie in `_flange_targets`). Das
Flansch-Ziel-Raster ist ein echter Seam mit drei externen Privat-Konsumenten
(`coarse`, `placement.advisor`, `test_slicer`), blieb aber privat buchstabiert.
Dazu die Drift aus #200: `evaluate`/`advisor` bekamen den harten
`config_filter` schon, `coarse` rief `select_along_path` weiter filterlos —
Erreichbarkeits-Ranking und Grob-Kollision hätten verschiedene IK-Zweige bewerten
können.

**Alternativen (die _corner_box/_matrix-Frage).**
- *coarse als Platzierungs-Ranking-Prädikat nach `placement` ziehen:* verworfen —
  invertierte die Import-Richtung (`placement` würde von der Kollisions-
  /Robotergeometrie abhängen); `coarse` **ist** die Grob-Stufe der
  Kollisionskontrolle (ADR-024) und gehört als Schwester von `check.py` in
  `fgc.collision`. Größerer, riskanter Umzug ohne Gewinn.
- *Neues `geometry`-Helfer-Modul für `matrix`/`corner_box`:* verworfen — die zwei
  sind reine numpy-Helfer (Frame→4×4, AABB-Ecken), die schon in `check.py` leben und
  dort intern gebraucht werden; ein drittes Modul spaltet den Seam nur.
- **Gewählt:** `_corner_box`/`_matrix` **öffentlich in `check`** (`corner_box`/
  `matrix`) widmen. `coarse` (Nachbar im selben Paket) trifft sie über den
  öffentlichen Namen — minimaler Churn, kein invertierter Import.

**Entscheidung.**
- `evaluate.flange_targets(...)` + `evaluate.nozzle_rotation(...)` **öffentlich**
  (dokumentierte Invarianten: Basiskoordinaten, Höhe-außen-Ordnung, geteilte
  `nozzle_quat`-Konvention). `flange_targets` gibt jetzt eine `FlangeTargets`-
  NamedTuple **inkl. `t_wall_base`** zurück — die Wand→Basis-Kette lebt **genau
  einmal** (dort); `coarse` bezieht sie von dort und verliert `_homogeneous`/`_rot_z`/
  `base_position_in_wall` **ersatzlos**.
- `check.corner_box`/`check.matrix` öffentlich (numpy-Geometrie-Helfer).
- `coarse.path_collides` bekommt `config_filter: IkConfigFilter | None = None` und
  reicht ihn an `select_along_path` durch — **derselbe Schnitt** wie evaluate/advisor
  (seit #200). `coarse`: 6 Privat-Importe → **0**.
- `test_slicer` nutzt `nozzle_rotation` (öffentlich). Die Modul-Konstanten
  `_R_NOZZLE_DOWN`/`_PLACEMENT_TANGENT` bleiben privat — sie sind **nicht** der
  gewidmete Seam, sondern White-Box-Anker der Drift-Regression (#51), die bewusst die
  interne Herleitung prüfen.

**Begründung.** Ein Seam, ein Name, eine t_wall_base-Kette: die drei externen
Konsumenten treffen zwei öffentliche Funktionen statt sechs privater; das Ranking
kann sich nicht mehr am Konfigurationszweig spalten. Default (`config_filter=None`/
all-auto) bleibt **bit-identisch** (Regressionsanker).

**Verifikation.** `test_placement_coarse` (Bit-Identität #98, Kollision rutscht
hinter frei, echte M1013-Geometrie), `test_placement`, `test_slicer`,
`test_singularity_advisor`, `test_collision_check` grün (86 passed). ruff grün.
Volle Core-Suite grün. Kein neuer ADR (Um-/Öffentlich-Widmung ohne
Architekturrang); kein README (interner Core-Seam, nicht nutzersichtbar).

## 2026-07-13 — Kontrakt-Orakel für projects.ts: Golden-Responses gegen die Spiegel-Typen, `Wire<T>`-tsc-Prüfung, eigenständige Familie (Issue #202)

**Frage.** `viewer/src/api/projects.ts` (30 Fetch-Wrapper, 52 handgepflegte Typen)
spiegelt 34 Routen / 39 Pydantic-Modelle in `core/src/fgc/pipeline/api.py`, hatte
aber **kein Testorakel**: der TS-Compiler prüft die Fiktion nur gegen sich selbst.
Eine Feld-Umbenennung in einem Antwortmodell blieb grün und brach erst zur
GUI-Laufzeit. 65 Viewer-Dateien importieren aus diesem Spiegel.

**Alternativen.**
- *Typen aus dem OpenAPI-Schema generieren und per tsc gegen den Spiegel halten*
  (Issue-Alternative): verworfen — bräuchte Codegen-Werkzeug (`openapi-typescript`)
  als neue Abhängigkeit + einen Vergleich generierter gegen handgepflegte Typen; mehr
  Toolchain-Risiko als Golden-JSON + eine `.test.ts`.
- *Wiederverwendung des `fgc.parity`-Harness* (#195): verworfen (aber Konventionen
  übernommen). Das Paritäts-Harness beweist *Zwillingsfunktions*-Parität — Py `fn(case)`
  gegen einen TS-Zwilling, **beide** gegen ein Golden verglichen. Hier gibt es keinen
  TS-Zwilling, der etwas nachrechnet: die Golden **ist** die Core-Antwort, der Beweis
  ist die *strukturelle Typ-Konformität* dieser Antwort gegen den handgepflegten
  Spiegel, erzwungen von `tsc`. Ein Zwang ins `register(pair, fn, cases, compare, …)`-
  Skelett würde `fn`/`compare` missbrauchen (es gibt keine Python-Neuableitung zum
  Vergleichen). Eigenständige Familie, die die *Hauskonventionen* erbt (eingecheckte
  Golden-JSON, ein Gen-Treiber, ein schneller Leser/Enforcement-Test).
- *Laufzeit-Typ-Guards in vitest*: verworfen als Primärmechanik — TS-Typen sind zur
  Laufzeit gelöscht, ein Guard wäre ein **dritter** handgepflegter Spiegel (driftet
  mit). Der einzige Ort, an dem sich api.py-Drift gegen den TS-Spiegel prüfen lässt,
  ist `tsc`.

**Entscheidung.**
- **Golden-Responses**: die Core-TestClient-Erfolgspfade legen je Route eine echte
  Antwort als `viewer/src/api/contract/*.contract.json` ab (19 abgedeckte Routen),
  Pfade sanitisiert (`<tmp>`/`<repo>` — reproduzierbar, maschinenunabhängig).
- **Core-Seite** `core/tests/test_api_contract.py`: schnelle Enforcement-Tests (jede
  Route mit `response_model` ist Golden **oder** als `TODO` mit Grund verzeichnet —
  kein stilles Loch; `contract-manifest.json` bleibt frisch) plus ein env-getorter
  Gen-Treiber (`FGC_REGEN_API_GOLDENS=1`).
- **TS-Seite** `viewer/src/api/projects.contract.test.ts`: jede Golden wird ihrem
  Spiegel-Typ über `conforms<T>(golden)` zugewiesen; `tsc --noEmit` (`npm run build`)
  ist die Prüftür. `Wire<T>` weitet String-/Zahl-**Literal-Unions** auf ihren Basistyp
  (JSON-Importe tragen keine Literaltypen — `"floor"` ist `string` —, würden sonst
  falsch-positiv anschlagen), hält aber Feldname, Präsenz und string↔number↔boolean
  scharf. vitest belegt zusätzlich das Laden und das Manifest (kein stilles Loch).
- **Namensschema `*.contract.json`, nicht `*.golden.json`:** der #195-Wächter
  `test_parity.py::test_every_golden_registered` erzwingt „jede `*.golden.json`
  unter `viewer/src` ist im `fgc.parity`-MANIFEST registriert" — die Endung ist
  die Invariante der Paritäts-Familie. Statt dort eine Verzeichnis-Ausnahme zu
  schnitzen (weicht den Wächter auf), trägt die Kontrakt-Familie ihre eigene
  Endung mit eigener zweiseitiger Registratur (`test_no_unregistered_contract_files`
  spiegelt den Paritäts-Wächter: Datei ↔ COVERED-Eintrag, plus Verbot von
  `.golden.json` im Kontrakt-Verzeichnis); der Paritäts-Wächter dokumentiert die
  Abgrenzung im Docstring.
- **Grenze (bewusst, v1):** ein *zusätzliches* api.py-Feld ohne Spiegel-Feld bleibt
  unbemerkt (strukturelle Zuweisung erlaubt Extra-Felder auf Werten). Umbenennung,
  Wegfall und Typwechsel eines Pflichtfelds werden erkannt — die Drift-Klasse der AC.
- **Abdeckung:** 19 Routen mit projects.ts-Spiegel (Umschlag-Familie, Kataloge,
  Set-Befunde, Zerlegung/Simulation/Export). TODO (sichtbar, mit Grund): Mesh-Upload-
  Routen (POST/PUT tools/workstations, detect-base-holes), Advisor-Routen
  (singularity/collision — teuer/leer möglich), die #134-entfallenen Platzierungs-
  Wrapper (kein Spiegel mehr), die Doppel-Modelle (decomposition-check GET/cancel,
  placement-suggestion), `/slice` (client.ts, via http.test.ts) und die beiden
  `dict`-Deletes.

**Befund des Orakels am ersten Tag.** `SetPlacementOverrideResult.override` ist im
Spiegel als `SectionOverride | Record<string,never>` getypt, aber `SectionOverride`
verlangt `section_id` als Pflichtfeld — die **echte** Antwort trägt im `override`-Feld
nur die sparse freien Werte (`{standoff_mm}`, ohne `section_id`; das steht separat als
Geschwisterfeld). Der akkurate Spiegel wäre `PlacementOverrideValues`. Da die 52 Typen
unberührt bleiben müssen (AC), kodiert der Test den akkuraten Kontrakt test-lokal
(`Omit<…,"override"> & { override: PlacementOverrideValues }`) und markiert die
Imprecision als Folgeticket. Genau der Zweck des Orakels: es fand am ersten Tag eine
reale Spiegel-Unschärfe.

**Verifikation (Drift-Demo, danach zurückgenommen).** `duration_s → duration_seconds`
in `SimulateSectionResponse` (api.py) + Golden-Regen → `npm run build` rot mit
„Property 'duration_s' is missing … but required" — die Viewer-Suite bricht
nachweislich. Nach Rücknahme grün. ruff grün; vitest 1011 passed (+22); Core-
Enforcement 4 passed/1 skipped (inkl. Rückrichtungs-Wächter). Kein neuer ADR (Testinfrastruktur, kein
Architekturrang; ADR-014 dünner Wrapper unangetastet), kein README (kein
nutzersichtbares Feature).

## 2026-07-13 — Eine Grün-Schwelle, ein Verfeinerungs-Loop (Issue #203)

`propose.py` importiert `GREEN_THRESHOLD` jetzt aus `evaluate.py` statt es
zweit zu definieren, und der 14-zeilige Verfeinerungs-Loop (Kopie aus #90)
lebt nur noch einmal als private `_refine(frac_at, n_v, n_h, cap)` mit den
zwei bestehenden `frac_at`-Adaptern in `_grid_counts`/`_module_grid_counts` —
rein mechanisch, numerisch unverändert (Goldens bit-identisch).

## 2026-07-14 — PRD #183 aktualisiert: cuRobo-Abgleich mit #205, Budget als Aufruf-Kontingent, AP-1-Abnahme relativ, vierter Benchmark-Arm (Issues #183/#205/#178/#165/#144)

**Frage.** Ist PRD #183 (2026-07-10, nachgeschärft 2026-07-12) noch auf den
Projektstand zugeschnitten — nach der Refactoring-Serie #188–#204 und dem
neuen cuRobo-PRD #205 (2026-07-13), das den #183-Revisionstrigger auslöste?

**Methode.** Multi-Agent-Aktualitäts-Review (43 Agenten): 5 parallele Leser
(PRD #183 komplett, PRD #205 + cuRobo-Tiefenrecherche, Code-Stand der
Kollisions-/Prüf-Tür-/Platzierungs-Nähte, Design-Log-/Issue-Timeline seit
2026-07-09, Web-Verifikation der externen Annahmen), 4 Kreuz-Prüfer
(cuRobo-Überlappung, Code-Drift, Messwerte/offene Entscheidungen,
Publikation), jeder Befund adversarial gegen die Primärquellen verifiziert
(inkl. Strohmann-Prüfung). Ergebnis: 25 Befunde bestätigt, 8 verworfen,
10 Punkte explizit „passt noch".

**Gesamturteil.** Architektur, Stufenfolge und Neuheitskern halten; die
Web-Verifikation fand keine konkurrierende Arbeit gegen den Claim
(Arm-gegen-wachsenden-Druckstand-Check als Schiedsrichter einer diskreten
Zerlegungs-/Platzierungssuche im Bau-Maßstab ab IFC). Kein einziger durch
#188–#204 veralteter Code-Name im PRD — die Refactorings haben die Nähte
*geschaffen*, die die Arbeitspakete brauchen. Alle Befunde waren Text-Drift,
keine Struktur-Fehler ⇒ **Body-Edit + datierter Korrektur-Kommentar statt
Neuschnitt** (Alternativen verworfen: „so lassen" hieße, jeder Agent liest
den cuRobo-Widerspruch; „neu schneiden" verwürfe eine tragfähige Struktur).

**Entscheidungen (Tobias, 2026-07-14):**

1. **Label-Quelle der Datenkampagne** — #183 („exakte Prüf-Tür etikettiert
   über Nacht") und #205 US 7 („GPU-vorsortiert, Stunden statt Wochen")
   widersprachen sich im Wortlaut. Entschieden: jedes Etikett trägt seine
   Herkunft (`cpu-exakt` | `gpu+cpu-grenzband` | `gpu+stichproben-audit`);
   welche Mischung fürs Training v1 zulässig ist, entscheidet der
   Beam-/Surrogat-Grill; der veröffentlichte Datensatz weist die
   Herkunftsverteilung aus. Laufbetrieb (US 23) bleibt CPU-exakt.
   Alternativen verworfen: „CPU etikettiert alles" (nähme #205 US 7 zurück),
   „GPU etikettiert, CPU auditiert" (legte die Policy fest, bevor Zahlen zur
   Grenzband-Treue existieren).
2. **Benchmark** — die drei Paper-Arme (Greedy/Beam/Beam+Surrogat) laufen
   CPU-only und byte-vergleichbar (ADR-004); ein **vierter Zusatzarm
   Beam+GPU-Vorsortierer ist explizit erlaubt** — eigene Provenienz +
   Toleranzschema (Definition bei #205), nie stillschweigend.
3. **#178 entschieden (beides)** — Such-Budget als **Aufruf-Kontingent**
   statt Sekunden (Determinismus; zusätzlich tragend: das Invarianz-Orakel
   #183-US 25 „gleicher Budget-Endstand ⇒ identisches Ergebnis" ist mit
   Zeitbudget nicht byte-vergleichbar prüfbar) UND #144 vorgezogen in
   Gestalt von #183-Arbeitspaket 1 (Glied-SDF ist der gewählte
   Beschleunigungshebel; H1/H2/H5 nur falls das SDF die Erwartung verfehlt).
   Folgen: #178 geschlossen, #165 auf Aufruf-Kontingent umgeschrieben +
   blocked-by #183-AP-1 + `ready-for-agent` entfernt.
4. **AP-1-Abnahme relativ** — Vorher/Nachher-Beleg FCL vs. Glied-SDF je
   Aufrufort plus Befund-Identität; die absolute 10-s-Marke (#144) bleibt
   bis zur Aufklärung von #150 unbestätigt und blockiert AP 1 nicht.
   Messtechnisch dabei festgehalten: die Baseline ist auf der **produktiv
   verdünnten** Konfiguration neu zu erheben (S5-52,8 % war unverdünnt, die
   7–16 s enthalten bereits stride=5 — sonst wäre der Y-fach-Beleg schief).

**Weitere Body-Änderungen:** US 14 zweigeteilt (FCL↔Glied-SDF am
Hindernis-Provider-Vertrag; GPU ausschließlich an der
`check_representative`-Naht der Prüf-Tür-Politik #190 — GPU sickert nie in
den CPU-Pfad); US 25 auf beliebige aktive Vorsortierer generalisiert;
Regressionsanker zweistufig (CPU byte-identisch, GPU nur Toleranzschema);
Further Notes: cuRoboV2-Abgrenzungspflicht fürs Paper
(`get_point_robot_distance` ist strukturell dieselbe Inversion — Abgrenzung
über konservative Glied-SDFs vs. Kugel-Approximation, Jeder-PC vs.
CUDA-Zwang, Pipeline-Schiedsrichter vs. Bibliotheks-Primitiv), RichMap
(arXiv 2604.06778) geprüft → RM4D gewählt (keine
No-false-negative-Garantie dort), Sollbruchstelle Surrogat (Paper 1
notfalls zweiarmig, Beam+Surrogat sonst Follow-up), Realwelt-Vorbehalt
DR_AVOID (#179) als zu klärende Limitation, Quellenlage um die gehärtete
cuRobo-Tiefenrecherche ergänzt. **AP 1 ist doppelt kritischer Pfad**: es
liefert die Paper-Zahl und entblockt das #205-G1-Gate (dessen „≥10×"
braucht die Glied-SDF-Messung als Vergleichsgröße).

**Seam-Mapping** (Code-Stand nach #188–#204, als #183-Kommentar für die
Folge-Issues): `SdfObstacleProvider` erfüllt den injizierten
`obstacle_provider`-Vertrag (`collision/check.py`), Punktwolken-Quelle
`SceneInputs`/`DruckstandSpec` (#192); Reichweitenkarte auf
`flange_targets`/`t_wall_base` (#201) + `base_position_in_wall` (ADR-025);
Beam über `assess_plan`/`PruefCache` (#190) mit Persistenz nur für den
Sieger durch `_persist_decompose_run`/`DecomposeBundle` (#198),
Strategie-Interface als Extraktion von `propose._refine` (#203);
Datensammlung als Rückgabe neben `PruefStats`, Persistenz ausschließlich
über die eine Tür — kein zweiter Seitenkanal.

Kein ADR (PRD-Scoping und Entscheidungs-Vollzug, kein Architekturrang);
kein README-Abschnitt (nicht nutzersichtbar). GitHub: #183 Body + Kommentar,
#205 Spiegel-Kommentar (inkl. Anregung G3-Schnitt: Kampagnen-Durchsatz
braucht nur G1+G2), #178 Resolution + geschlossen, #165 Body + Label,
#144 Kommentar.

## 2026-07-14 — Beam-/Surrogat-Grill vorgezogen abgeschlossen + PRD #183 komplett verissued (#206–#220)

**Frage.** Das Beam-Grill-Gate von PRD #183 stand zwischen „ganze PRD in einem
Rutsch verissuen" und der Umsetzung. Tobias-Entscheid: Grill vorziehen (vor
den AP-1/AP-2-Messungen) — wo Zahlen fehlen, wird das *Verfahren* entschieden
statt des Werts.

**Acht Entscheidungen (Tobias, Grill 2026-07-14):**

1. **Kriterien (Domäne zuerst):** Erreichbarkeit = hartes K.-o., kein
   Gewicht. Rangfolge: Umsetzvorgänge > Fugenfläche > kinematische Marge >
   c_v — Einmessen ist der teuerste manuelle Schritt, c_v ist Komfort.
   Kein fehlendes Kriterium.
2. **Form: lexikographisch als Default.** Kein Aufwiegen (kein c_v
   kompensiert ein Einmessen); eliminiert die Gewichts-Kalibrierung, im
   Paper nur die Rangfolge zu rechtfertigen, trivial byte-vergleichbar.
   Stetige Kriterien quantisiert; Schrittweiten = Verfahrens-Parameter,
   Eichung nach AP 2 an echten Kandidaten. Alternative gewichtete Summe
   verworfen als Default (Zahlen vor den Messungen nicht kalibrierbar).
3. **Einstellungs-Fenster: ein Gewichts-Satz, zwei Lesarten.** Aufwiegen
   AN = gewichtete Summe, AUS (Default) = Gewichts-Reihenfolge ist die
   Rangfolge; Gleichstand im Aus-Modus UI-seitig verhindert.
   Druckjob-Parameter (ADR-007/-016), volle Lauf-Provenienz (ADR-004),
   Paper-Benchmark pinnt den Default. Alternative getrennte Controls
   (Rangfolge-Liste + Gewichte) verworfen: zwei Zustände, die
   auseinanderlaufen können.
4. **Budget-Verfahren:** Default-Kontingent = größte runde Aufruf-Zahl mit
   Hintergrundlauf ≤ ~5 min auf der Referenzmaschine (Messung nach AP 1,
   SDF-Backend, produktiv verdünnt); Konstante + Design-Log; je Druckjob
   übersteuerbar (Provenienz trägt den Wert — langsamere Maschine ⇒
   längerer Lauf, bit-gleicher Schnitt). Beam-Breite k aus dem Kontingent
   abgeleitet, kein eigener Parameter.
5. **Relaxationsleiter (US 22):** mehr Teile → mehr Standplätze →
   Tiefenteilungs-Vorschlag (#166-Muster, Anwendung manuell). Nie
   relaxiert: Sicherheitsabstand, Erreichbarkeits-K.-o., Ehrlichkeitsregel,
   Kipp-/Tiefenteilungs-Automatik (#141/#165 gelten auch im Beam). Jede
   gezündete Stufe namentlich im Befund + Provenienz.
6. **Label-Policy v1:** Training aus `cpu-exakt` + `gpu+cpu-grenzband`
   (Letzteres nur mit bestandenem #205-G1-Gate — das belegt genau das
   konservative Grenzband); `gpu+stichproben-audit` nicht trainingstauglich,
   nur explorativ, im Datensatz markiert. CPU-only-Kampagne bleibt Fallback.
7. **Sollbruchstelle — Gate statt Datum:** dritter Benchmark-Arm nur, wenn
   beim Start der finalen Läufe ein Modell existiert (v1-policy-konform
   trainiert, Invarianz-Orakel grün, Artefakt mit Provenienz); sonst
   zweiarmig einreichen, Surrogat als Follow-up. Der Benchmark wartet nie
   und wird nicht wiederholt — das Surrogat muss den Zug erwischen.
8. **Vierter Arm (Beam+GPU): opportunistisch, gleiches Zug-Prinzip** —
   #205-G2 fertig ⇒ mitmessen als Zusatzmaterial (Kern-Claims ruhen auf den
   drei CPU-Armen); sonst entfällt er. Blockiert nie.

Alle acht in den #183-Body eingearbeitet (Grill-Gate-Klauseln entfernt,
Testing Decisions für die Beam-Suche spezifiziert); Grill-Protokoll als
Issue-Kommentar.

**Verissuen (15 Slices, #206–#220, alle needs-triage + Modellempfehlung):**
AP 1: #206 Baseline-Messung, #207 GliedSdf, #208 DruckstandPunkte,
#213 SdfObstacleProvider (→207/208), #215 Nachher-Messung/AP-1-Abnahme +
Kontingent-Ableitung (→206/213, entblockt #205-G1). AP 2: #209
Stufe-1-Schranke, #210 ReachabilityMap, #214 Vorfilter-Integration (→210).
Stufe 3: #212 Zielfunktion+Fenster, #216 Strategie-Interface+Generator+
Scorer (→212/214), #217 Beam end-to-end (→215/211/216). Stufe 4: #211
Datensammel-Pflicht, #218 Datenkampagne (→215/211), #219 Surrogat
(→217/218). Publikation: #220 Benchmark-Harness (→217/#165; #219 nur via
Gate). Sieben sofort startbar (#206–#212). Schnitt-Entscheidungen:
Baseline- und Nachher-Messung getrennt (Baseline läuft parallel zur
SDF-Entwicklung), Vorfilter-Integration ungeteilt (Bewertung/Optimal-
vorschlag/Advisor teilen die evaluate-Maschinerie seit #200), Zielfunktion
mit injizierten Kriterien vor dem Scorer (deterministisch testbar ohne
Karte), AP 2 nicht hinter AP 1 gehängt (kein technischer Blocker — reine
Prioritäts-Empfehlung).

## 2026-07-14 — Core-pytest parallelisiert: pytest-xdist `-n auto` (Werkzeug, vor dem #206–#220-Batch)

**Frage.** Vor dem AFK-Batch #206–#220 fällt die Prüfsuite bei jedem der 16
Issues an. Die Core-pytest lief single-core in 15+ min — 16 × ~15 min ≈ 4 h
reines Testen. Kann der Prüf-Loop beschleunigt werden?

**Messung.** 851 Testfunktionen auf 16 Kernen. `--durations=25` zeigt: die
Zeit kommt nicht aus der Masse, sondern aus ~15 schweren End-to-End-Tests
(je 25–147 s): `test_export.py`, `test_section_simulation.py`,
`test_section_overrides_pipeline.py` — echte Slice-/Simulations-Läufe
(Staling, Byte-Identität, Overrides).

**Entscheidung.** `pytest-xdist` als dev-dep + `addopts = "-m 'not slow'
-n auto"`. Ergebnis: 865 passed, 1 skipped in **8:52** statt 15+ min. Der
Boden liegt jetzt beim längsten Einzeltest (147 s), nicht mehr an der Summe.

**Verworfen: die schweren Tests `slow` markieren.** Genau diese Tests
sichern `decompose`/`section-sim`/`export` — die Bereiche, die #209/#211/
#213/#214/#217 dieses Batches anfassen. Sie aus der Standard-Suite zu
nehmen zieht das Regressionsnetz dort weg, wo es am meisten gebraucht wird.
Die eigentliche Beschleunigung (Fixture-Caching der Mesh-Loads, kleinere
Testmodelle) ist echte Arbeit und gehört in ein eigenes Issue, nicht in
einen Hack mitten im Batch.

## 2026-07-14 — AP-1-Baseline: FCL-Referenz produktiv verdünnt, je Aufrufort (Issue #206)

**Frage.** Vorher-Hälfte von US 13 der PRD #183: Was kostet `find_collisions`
**konfigurationsgleich zum Realpfad** (Travel-Stride 5), getrennt nach Aufrufort
(Arm↔Hindernis vs. Selbstkollision), als Baseline für den Paper-Beleg „SDF
beschleunigt Y-fach je Posten"? Die S5-Zahl (52,8 % `set_transform`, ~11,5 s) wurde
**unverdünnt** (stride=1) gemessen und taugt nicht als Vorher-Wert.

**Vorgehen.** Die S5-Sonden erweitert (nicht neu gebaut): neue Sonde
`docs/spikes/s5_scripts/s5_ap1_baseline.py` baut auf `s5_harness.build_inputs()`,
dünnt die Sample-Auswahl mit **derselben** Produktivfunktion `finding.
thin_travel_indices(flags, DEFAULT_TRAVEL_STRIDE=5)` aus wie `check_part_clearance`
und spiegelt den `find_collisions`-Loop mit Timern **getrennt nach Aufrufort**. Gates:
Determinismus (zwei Läufe byte-identisch) + Nachbildung trifft die echten
rot/gelb/grün-Zahlen. Protokoll `docs/spikes/S5b_ap1_baseline_verduennt.md`.

**Ergebnis (verdünnt, 11 968 von 16 203 Samples, Modul, safety 50 / freizone 40).**
`find_collisions` self=False (Produktiv-Befund): Median **7,03 s** — bestätigt, dass
die PRD-Zahl „7–16 s je Teil" stride=5 bereits enthält. Je Aufrufort:
**Arm↔Hindernis** 23 468 fcl-Aufrufe, 0,94 s (0,040 ms/Aufruf), `set_transform`
3,40 s; **Selbstkollision (Arm↔Arm)** 54 248 fcl-Aufrufe, **122,59 s** (2,26 ms/Aufruf,
~56× teurer je Aufruf), `set_transform` 13,56 s, voller self=True-Lauf 147,7 s.
AABB-Breitphase verwirft 71,5 % (Arm) / 78,4 % (self).

**Befund/Entscheidung.** Die zwei Aufruforte sind **grundverschiedene Kostenblöcke**:
Arm↔Hindernis läuft Glied gegen einen kompakten Druckstand-Mesh (fcl billig,
`set_transform` dominiert wie in S5); Selbstkollision prüft **zwei** VHACD-Manager
(~36×36 Stückpaare) gegeneinander — daher der 56×-Aufpreis je Aufruf und 122,6 s in
Summe. Eine reine self=False-Baseline hätte diesen Block übersehen (PRD: „kein
Kostenblock übersehen"). Für #215 ist deshalb der Y-Faktor **je Aufrufort getrennt**
zu berichten; der Glied-SDF-Hebel liegt vor allem auf Arm↔Arm.

**Konfiguration festgeschrieben** (Protokoll-Tabelle), damit die AP-1-Abnahme (#215)
konfigurationsgleich laufen kann: Lauf `denkmal/abschnitt-1` (Modul), Reproduktion
`slice_and_simulate_section`, stride=5, safety 50 mm, freizone 40 mm, Tool `30gut`,
Rechner ausgewiesen. **Drift festgehalten:** Die Pipeline ist seit S5 (2026-07-09)
um dutzende Commits fortgeschritten; der 2026-07-09-Lauf reproduziert nicht mehr
byte-genau (S5: 19 535 Samples / 8688-2405-8442). Der aktuelle deterministische
Fingerabdruck ist 16 203 Samples / 6187-1938-8078 (voll) bzw. 5106-1142-5720
(verdünnt); die S5-Sonden (`s5_harness.py`) sind darauf re-gepinnt (Kommentar
`RE-PINNED 2026-07-14`). Empfehlung an #215: Baseline **unmittelbar vor** der
Nachher-Messung mit derselben Sonde neu erheben (liefert beide Hälften
konfigurationsgleich), statt Absolutzahlen zu übernehmen.

**Kein Produktivcode geändert** (`core/src/fgc/collision/*` unberührt) — reiner
Spike. Kein ADR (Messung, keine Architekturentscheidung), kein README (interner
Spike). Nebenbei: Sonden auf API-Drift nachgezogen (`_slice_and_simulate_section`
→ `slice_and_simulate_section`, `_corner_box`/`_matrix` → öffentlich per #201) und
ein pre-existing F541-Lint in `s5_cprofile.py` gefixt.

## 2026-07-14 — Glied-SDF: statisches Voxel-SDF je Armglied, konservativ gegen die FCL-Referenz (Issue #207)

**Frage.** Wie wird `GliedSdf` (PRD #183, Arbeitspaket 1) so gebaut, dass die
SDF-Distanz die FCL-Referenz **nie überschätzt** — und woher kommt die
Quellgeometrie?

**Entscheidungen.**

1. **Quelle = #125-Urteilsgeometrie (VHACD-Stücke), nicht die Roh-Meshes.**
   Der FCL-Pfad (`check.py`) urteilt über genau diese Stücke; SDF und Referenz
   sprechen damit über dieselbe Geometrie, und die Feld-Semantik
   (`min_i d_i` über die Stücke, negativ = innen) ist identisch mit
   `CollisionManager.min_distance_*`. Alternative (Roh-Meshes als Quelle)
   verworfen: hätte eine zweite Urteilswahrheit neben der FCL-Referenz erzeugt
   und den Befund-Identitäts-Anker von #213/#215 (US 2) unterlaufen.
2. **Exakte Knotenwerte, Konservativität über ein Interpolationsband.** Die
   Knoten tragen exakte Distanzen (außen: nächste Stück-Oberfläche über einen
   BVH; innen: konvex-exakter Ebenentest je Stück). Trilineare Interpolation
   eines 1-Lipschitz-Felds irrt um höchstens die halbe Zelldiagonale
   (√3/2·voxel) — dieses Band wird bei **jeder** Abfrage abgezogen
   (`interpolation_band_mm`, bei 8 mm Voxel ≈ 6,9 mm): Unterschätzen erlaubt,
   Überschätzen ausgeschlossen. Außerhalb des Gitters gilt die analytische
   Distanz zur Objekt-AABB (untere Schranke, Muster Breitphasen-Filter).
   Alternative (Knotenwerte selbst konservativ verfälschen) verworfen: mischt
   Feld und Politik, das Band wäre nicht mehr getrennt konfigurier-/belegbar.
3. **Auflösung 8 mm, Gitterrand 80 mm als Defaults.** 80 mm > Sicherheitsabstand
   (50 mm) + Band — alle urteilsrelevanten Abfragen landen im Gitter; Artefakt
   gesamt ~3 MB (float32-`.npy` je Glied). Zusätzliches Sicherheitsband je
   Abfrage konfigurierbar (`safety_band_mm`), Auflösung je Build
   (`--voxel-mm`).
4. **Provenienz + Lade-Validierung (US 17/18):** Manifest trägt Roboter,
   Auflösung, Formatstand und den **Buildstand als SHA-256-Fingerabdruck der
   Quelldateien** (#125-Derivat inkl. Manifest); `load_glied_sdf` validiert
   alle vier gegen Katalog und aktuelle Quellgeometrie und wirft sonst
   `SdfProvenanceError` mit Bauanleitung — kein stilles Urteilen mit
   veralteten Feldern. Ablage als Unterordner des katalog-referenzierten
   Kollisions-Derivats (`robots/collision/<robot>/sdf/`), kein neues
   Katalogfeld nötig.

**Belegt** (`core/tests/test_glied_sdf.py`): Ground-Truth-Vergleich gegen
FCL-Distanzen (Kugel-Sonde) an gesampelten Gelenkkonfigurationen über den
Welt→Gliedframe-Rückweg — nie überschätzt, Innenpunkte nie „frei", plus
Gegenprobe (höchstens 2 Bänder darunter), analytischer Würfel-Test der reinen
Build-Funktion, Provenienz-Fehlpfade, Determinismus-Spot-Check (Rebuild
bitgleich). Kein ADR (Architektur liegt in PRD #183/ADR-024), kein README
(internes Modul).

## 2026-07-14 — DruckstandPunkte: wachsender Druckstand als Punktwolke, Anhängen statt Feld-Umbau (Issue #208)

**Frage.** Wie wächst der Druckstand als Punktwolke (Gegenstück zu `GliedSdf`,
#207) so, dass Schichtfortschritt **reines Anhängen** bleibt und dabei
garantiert bit-identisch zu einem frischen Aufbau ist?

**Entscheidungen.**

1. **Jede Schicht-Punktmenge ist eine reine Funktion ihrer Schichthöhe.**
   `advance_layer(n)` hängt je fehlender Schicht genau den deterministisch
   gesampelten Grundriss-Schnitt bei `layer_top_mm(spec, k)` an (dieselbe
   Höhensemantik wie das Footprint-Prisma, #126) — nie eine Neuberechnung
   älterer Schichten. Weil die Schnittfunktion nur von `(Grundriss, Höhe,
   Punktabstand)` abhängt, nicht vom Aufrufmuster, ist Schritt-für-Schritt-
   Anhängen **bit-identisch** zum direkten Vorspulen auf dieselbe Zielschicht
   (Abnahme 1, belegt per `np.testing.assert_array_equal`, auch bei
   Mehrfach-/Rückwärtsaufrufen als No-Op).
2. **Stehenbleibende ältere Schichten sind konservativ, nicht falsch.** Eine
   Schicht-Fläche, die später von neuem Material überdeckt (also innen liegt)
   ist, bleibt in der Wolke statt gelöscht zu werden — ein Innenpunkt kann den
   minimalen Abstand zu einem Außenpunkt nur überschätzen, nie unterschätzen
   (der kürzeste Weg von außen quert zwangsläufig die echte Oberfläche).
   Damit ist "nie entfernen, nur anhängen" ohne Kollisions-Risiko und erlaubt
   den denkbar einfachsten Append-Vertrag. Alternative (Fenster über die
   letzten k Schichten, ältere verwerfen) verworfen: hätte echte Rebuild-
   Logik zurückgebracht, genau das Problem, das die Inversion (Shen 2026)
   auflöst.
3. **Punktabstand-Default 15 mm = 30 % der 50-mm-Sicherheitsmarge.**
   Abgeleitet von `check.DEFAULT_SAFETY_DISTANCE_MM`
   (`DEFAULT_POINT_SPACING_MM = round(0.3 * DEFAULT_SAFETY_DISTANCE_MM, 1)`),
   passend zum Design-Log-Eintrag 2026-07-12 ("deutlich unter dem
   Sicherheitsabstand … 15–20 mm Raster ist konservativ genug"; Shen et al.
   2026 fahren 2 mm bei 3 mm Marge, ≈ 67 % — unser Verhältnis von 30 % ist
   konservativer, weil unser Sicherheitsabstand selbst schon eine großzügige
   Prozessmarge für weichen Lehm trägt, kein reiner Zahlenpuffer).
4. **Statische Hindernisse im selben Vertrag, einmalig gesampelt (US 15).**
   Workstation-Arbeitsfläche und Gebäudekontext werden bei Konstruktion
   **einmal** zu Punktwolken unterteilt (`trimesh.remesh.subdivide_to_size` —
   deterministisch, anders als `sample_surface`s Zufallsstichprobe) und
   wachsen nie; dieselbe Abschnitt/Modul-Weiche wie
   `druckstand.build_obstacle_set` (Abschnitt: frühere Teile + Boden +
   Kontext; Modul: nur Arbeitsfläche) — kein zweites Vokabular für dieselbe
   Entscheidung.
5. **Quell-Naht = `DruckstandSpec` selbst.** `DruckstandPunkteSpec.
   from_druckstand_spec` spiegelt ein bestehendes `DruckstandSpec` (aus
   `SceneInputs`/`FindingRequest`, #192) 1:1 in die Punktwolken-Eingaben —
   beide Backends (FCL-Meshes, Punktwolke) entstehen so aus derselben Szene,
   kein zweiter Konstruktionsweg.

**Belegt** (`core/tests/test_druckstand_punkte.py`): Bit-Gleichheit
Schritt-für-Schritt vs. Direktsprung (auch bei Mehrfach-/Rückwärtsaufrufen),
Schicht 0 ohne Punkte, Clamping auf `n_layers`, streng wachsende Punktzahl je
Schicht, Punktabstand-Invariante für Grundriss-Gitter **und** Mesh-Unterteilung,
Default-Herleitung (15 mm = 30 % von 50 mm), Abschnitt- vs. Modul-Weiche der
Statik, volle Punktmenge = Wachsend + Statik, Naht-Treue zu `DruckstandSpec`.
Kein ADR (Architektur liegt in PRD #183/ADR-024), kein README (internes Modul).

## 2026-07-14 — Zweite Stufe-1-Schranke: „Teil zu hoch für die freie Länge" (Issue #209)

**Frage.** PRD #183 AP-2 („Gratiswissen ausbauen") verlangt neben dem
Freigang-Kriterium (#163, „Wand zu dick") eine **zweite analytische
Stufe-1-Schranke** nach dem Winkelmuster von Stamatopoulos (Gl. 9,
`docs/recherche/2026-07-10-adaption-chunking-literatur.md`): „Teil zu hoch für
die verbleibende freie Länge" — gratis, gleiche S6-Fehlerrichtung wie #163,
Überschuss-Ausweis in mm **und** Grad (US 4).

**Modell (Gl. 9, bewusst vereinfacht).** `φ_max^sample = π/2 − min(φ_max^conn,
φ_max^extr)` mit `φ_max^conn = 45°` (konstant, 50-%-Überlappungs-Faustregel) und
`φ_max^extr = arctan(R/L)` aus der Endeffektor-Bounding-Box (Handgelenk-Radius
`R` über freier Länge `L`). Daraus die druckbare Höhe `H_max = L·tan(φ_sample)`,
geschlossen **`L²/R`** für schlanke Endeffektoren (`L ≥ R`) bzw. `L` sonst. Ein
Teil ist `too_tall`, wenn seine Höhe **strikt** über `H_max` liegt; der Überschuss
wird doppelt ausgewiesen: `excess_mm = höhe − H_max` und
`excess_deg = arctan(höhe/L) − φ_sample`.

**Entscheidungen und verworfene Alternativen.**
1. **Mapping `arctan(R/L)` statt `arctan(L/R)`.** Beide sind zu Gl. 8/9
   verträglich; `arctan(R/L)` gibt für den realen M1013 (`L ≈ 273`, `R = 60`)
   `H_max = L²/R ≈ 1250 mm` — eine **großzügige** Schranke, die nur Teile weit
   jenseits der Werkzeug-Reichweite fängt. Das faithful-wirkende `arctan(L/R)`
   ergäbe `H_max = max(L, R) ≈ 273 mm` und würde **jeden** normal hohen Abschnitt
   fälschlich flaggen (die Teilhöhe ist physikalisch **nicht hart** durch die
   Werkzeuggeometrie begrenzt — der Roboter setzt je Schicht um). Verworfen.
2. **`presumed = True`, kein Gate.** Weil die Höhe placement-abhängig ist, ist
   „zu hoch" — wie „zu dick" seit #177 — nie eine geprüfte Gewissheit, sondern
   eine **platzierungsblinde Vermutung**: ein ratschlagender Befund „für einen
   Guss zu hoch → in der Höhe teilen" (Hebel Höhenteilung). Kein Gate (ADR-013).
3. **Verdrahtung in `pruefung.assess_plan` (Stufe-1-Pfad), NICHT in
   `combine_printability`.** `combine_printability` verheiratet Freigang
   (wand-weit) + Prüf-Tür und wird von der ganzen Politik geteilt; ein per-Teil-
   Höhen-Gate dort hätte den Verdikt-Fluss aller Stufe-2-Tests gestört
   (Fixtures mit kleiner freier Länge + hohen Abschnitten). Die per-Teil-Schranke
   sitzt darum eine Ebene höher, in `_apply_teilhoehe`, und überschreibt die
   Stufe-1-Urteile additiv. Das trifft zugleich die PRD-Formulierung
   („Stufe-1-Pfad in decompose/pruefung.py").
4. **Nur Stufe 1, Stufe 2 überstimmt.** Der Höhen-Override läuft **ausschließlich**
   im gratis Ruhezustand (kein Orakel → keine Simulation, Short-Circuit, US 3).
   Läuft die teure Prüf-Tür (expliziter Anstoß, Stufe 2), zählt ihr Urteil je
   Repräsentant — die Vermutung wird überstimmt. Das ist konsistent mit der
   `presumed`-Semantik (die reale Prüfung supersediert die billige Annahme) und
   hält den Blast-Radius auf bestehende Tests bei **null** (alle übrigen
   `assess_plan`-Aufrufer reichen `freigang=None` oder `too_thick` herein).
5. **Additiv (US 11/12).** Neuer `verdict = "too_tall"` (Schema-Enum erweitert),
   neues Feld `excess_deg` (nur bei `too_tall` serialisiert). Ampel-Semantik
   unverändert: `too_tall → severity "bad"` (rot), wie `too_thick`. Altläufe
   ohne die Felder bleiben byte-gleich gültig; fehlt die Tool-Geometrie
   (`freigang=None`), schweigt die Schranke (fail-soft).

**Belegt.** `core/tests/test_freigang.py` (reine Formeln Gl. 9, geschlossene Form
`L²/R`, Grenzwert strikt `>`, Überschuss mm+Grad, Monotonie in `L`, fail-soft bei
`L ≤ 0`); `core/tests/test_pruef_check.py` (Stufe-1-Override ohne Simulation, kein
Fehlalarm bei großzügigem Endeffektor, fail-soft ohne Freigang, provisorischer TCP,
Stufe 2 überstimmt); `viewer/src/ui/printability-state.test.ts` (rote „vermutlich zu
hoch"-Ampel mit mm+Grad, additiv ohne Grad-Feld, keine Prüf-Tür-Vorbehalte). ruff +
scoped Core-Tests + vitest + tsc grün. README-Abschnitt unter „Funktionen". Kein
eigener ADR (Architektur liegt in PRD #183; Muster folgt #163/ADR-013).

## 2026-07-14 — ReachabilityMap: 4D-Reichweitenkarte nach RM4D-Muster, direkt-invers aus der OPW-IK (Issue #210)

**Frage.** Wie wird die einmalig offline gebaute Reichweitenkarte des M1013
(PRD #183, Arbeitspaket 2 „Gratiswissen") so gebaut, dass sie **am Kartenraster
keine falschen Negative** gegenüber der OPW-IK hat — und wie bleiben Vorwärts-
(„Pose erreichbar von Basis?") und Inversabfrage („Basispositionen für Pose?")
eine einzige Struktur?

**Entscheidungen.**

1. **RM4D-Koordinaten (p_z, alpha, x_t, y_t), binär** (`fgc.kinematics.
   reachability`): Posenhöhe über der Basis, Anflugwinkel zur Vertikalen,
   kanonische Basisposition (horizontaler Versatz Basis−Pose im Azimut-Frame
   der Anflugrichtung). Der M1013 erfüllt beide RM4D-Annahmen exakt (J1/J6 =
   ±360°) — eine Struktur beantwortet vorwärts und invers ohne separaten
   Inversionsschritt. Alternative Zacharias-6D verworfen (~67× größer, eigener
   Inversionsschritt), B\* (Optimierung statt Karte) bleibt spätere Option —
   die Karte ist der Vorfilter für #214/#216, das Urteil bleibt bei der
   Prüf-Tür (Ehrlichkeitsregel ADR-007/#164).
2. **Aufbau direkt-invers über die analytische OPW-IK, keine Sampling-Orgie:**
   jede 4D-Zelle wird an ihrem Knoten exakt ausgewertet (Repräsentant-Pose →
   IK → „Lösung innerhalb der Achsgrenzen?"). Dafür eine **belegte Reduktion**:
   beim M1013 sind alle Achsen außer J3 Vollkreis-Achsen (auf [−π, π] normierte
   Lösungen dort nie limitiert) — Erreichbarkeit hängt nur vom Positionszweig
   der OPW-IK ab (Handgelenkzentrum, 4 Schulter/Ellbogen-Zweige). Der Build
   vektorisiert exakt diese Formeln (zeilengleich zu `opw.inverse_matrix`);
   die Voraussetzung wird **hart geprüft** (`ValueError` statt stiller
   Falschkarte für Roboter mit beschnittenen Achsen). Voller Build
   61×37×61×61 ≈ 8,4 M Zellen in ~2 s. Alternative (skalare IK je Zelle)
   verworfen: Minuten statt Sekunden bei identischem Ergebnis — die
   Äquivalenz ist per Raster-Gegenprüfung gegen die skalare IK belegt.
3. **Entartetes Azimut (senkrechter Anflug, unser Hauptfall Düse-nach-unten):
   Versatz ungedreht kanonisieren.** Dort ist die Karte rotationssymmetrisch;
   die Wahl kostet am Knoten keine Korrektheit (jede Zelle exakt ausgewertet)
   und hält den Knoten-Roundtrip exakt. Alternative (auf Radiusachse
   kollabieren) verworfen: hätte Knoten auf fremde Zellen gerundet — genau die
   falschen Negative, die der Vertrag ausschließt.
4. **Min-Aggregation als punktweises UND** (`min_over_poses`, Vahrenkamp
   Gl. 3 / RM4D IV-D): Basispositionen, die **alle** Posen einer Höhenreihe
   erreichen (US 6 — kein Umsetzen mitten in der Reihe). Frame-Quelle ist der
   #201-Seam: `flange_targets` liefert Basis-Ziele (Vorwärtsabfrage) +
   `t_wall_base`; `frames_in_wall` hebt sie ins Wandsystem (Inversabfrage) —
   die Wand→Basis-Kette wird konsumiert, nicht dupliziert. Standplatz-Semantik
   ADR-025/#132: Kandidaten-Basen aufrecht (Yaw frei, J1-Invarianz),
   `base_z_mm` absolut über dem Boden; die Abstand↔y-Naht bleibt allein
   `base_position_in_wall`/`standoff_from_base_y`.
5. **Provenienz + Lade-Validierung (US 17/18):** Artefakt
   `robots/reachability/doosan_m1013/` (`values.npy` packbits ~1 MB +
   `manifest.json`; Skript `core/scripts/build_reachability_map.py`,
   deterministisch, keine Zeitstempel). Manifest trägt Formatstand, Roboter,
   Auflösung und den **SHA-256-Fingerabdruck der Katalog-Kinematik**
   (DH-Parameter + Achsgrenzen; Zeitlimits bewusst außen vor);
   `load_reachability_map` validiert alle vier gegen `robots/<name>.json` und
   wirft sonst `ReachabilityProvenanceError` mit Bauanleitung — kein stiller
   Falschfilter. Auflösung 50 mm / 5° (RM4D-Papierwerte) als Default.

**Belegt** (`core/tests/test_reachability.py`): Stichproben-Gegenprüfung an
400 gesampelten Rasterknoten gegen die skalare OPW-IK (keine falschen
Negative, dank direkt-inversem Build sogar exakt; beide Klassen in der
Stichprobe erzwungen) + Mini-Abnahme am committeten Artefakt in voller
Auflösung; Knoten-Roundtrip der Kanonisierung inkl. α ∈ {0, π};
Min-Aggregation über eine konstruierte Höhenreihe (UND-Eigenschaft + Fall
„Basis erreicht Pose A, fällt aus dem Reihen-Minimum"); Vorwärts- ==
Inversabfrage über den echten `flange_targets`-Weg; Provenienz-Fehlpfade
(falscher Roboter, geänderte Katalog-Kinematik, Formatstand, Gitterform,
fehlendes Artefakt); Vollkreis-Voraussetzung hart. ruff + scoped Core-Tests
grün. Kein ADR (Architektur liegt in PRD #183), kein README (internes Modul,
Konsumenten #214/#216).

## 2026-07-14 — Datensammel-Pflicht: Merkmale + Prüf-Tür-Urteil je Kandidat (Issue #211)

**Frage:** PRD #183 Stufe 4 (US 23) verlangt, dass sich der Trainingsdatensatz
fürs künftige Surrogat (#219) **von selbst füllt**: je geprüftem Kandidat sollen
Merkmale (Abschnittsmaße, Wandposition, Platzierung, Podesthöhe) + das exakte
Prüf-Tür-Urteil strukturiert im Laufartefakt landen — additiv und fail-soft
(#164-Muster), ohne einen zweiten Persistenz-Seitenkanal.

**Seams (im PRD-Kommentar 2026-07-14 fixiert, so umgesetzt):**

1. **`assess_plan` gibt den Kandidaten-Kern neben `PruefStats` zurück.** Die
   Rückgabe wird von `(printability, stats)` zu `(printability, stats, samples)`.
   `samples` ist je **geprüftem Repräsentanten** (Höhenreihe mit echtem
   Prüf-Tür-Urteil, kein `error`/`no_geometry`-String) ein `PruefSample`
   (`section_id`, `features`, `verdict`). Der Kern trägt, was das reine
   Domänen-Modul aus Plan + Urteil kennt: Abschnittsmaße (`x0/x1/z0/z1`,
   `length/height`, `center_x`), Wandmaße, `order` und **Hindernislast**
   (`n_earlier_parts` in Druckreihenfolge — der Kollisionstreiber B10 bei
   „Abschnitt", 0 bei „Modul"); `verdict` ist `PartPrintability.to_dict()` des
   an diesem Teil selbst geprüften (nicht geerbten) Urteils. Stufe 1 (kein
   Orakel) und der `too_thick`-Kurzschluss liefern `[]` — der interaktive
   Editor-Loop füllt den Trainingssatz nicht.
2. **`check_decomposition` reichert Platzierung/Podest an** (Phase 3, aus dem
   Phase-1-Plan): `PruefSample.with_placement` legt `lateral_mm`, `standoff_mm`,
   **`stand_height_mm` (Podesthöhe)** und `yaw_rad` additiv in die Merkmale.
   Getrennter Seam, weil nur der Aufrufer die Platzierung je Teil kennt.
3. **Persistenz ausschließlich über `_persist_decompose_run`/`DecomposeBundle`**
   (#198): neues Bundle-Feld `pruef_samples`; `decompose_artifact` schreibt
   **einen** additiven Top-Level-Block `pruef_dataset` (`feature_version`,
   `label_source`, `samples`). Kein zweiter Seitenkanal.

**Entscheidungen/Alternativen:**

- **Rückgabe-Arität statt Anhängen an `PruefStats`.** Erwogen: `samples` in
  `PruefStats` unterbringen (arität-erhaltend). Verworfen — `PruefStats` ist
  Rechen-/Cache-Statistik, keine Datensätze; der Grill fixierte „als Rückgabe
  **neben** `PruefStats`". Preis: ~20 Aufruf-Stellen (2 produktiv, Rest Tests)
  auf das 3-Tupel umgestellt (`, _samples`).
- **Merkmalsliste versioniert** (`FEATURE_SCHEMA_VERSION = "1"`, Konstante in
  `pruefung.py`, im Block als `feature_version`) — Vorgriff auf die
  Surrogat-Provenienz (US 26): wächst der Feld-Satz oder ändert sich eine
  Bedeutung, wird hochgezählt, nie stillschweigend umdefiniert.
- **Label im Laufbetrieb immer `cpu-exakt`** (`PRUEF_LABEL_CPU_EXACT`, Grill
  2026-07-14): der reguläre Prüf-Tür-Lauf labelt stets die exakte CPU-Prüfung;
  die Label-*Quellen*-Frage (Surrogat labelt sich nicht selbst) betrifft nur die
  Datenkampagne #218.
- **Fail-soft durchgehend** (#164): `_collect_samples` (assess_plan) und
  `_enrich_pruef_samples` (actions) fangen jede Ausnahme und liefern
  `[]`/den unangereicherten Kern — die Datensammel-Pflicht kippt nie den Lauf
  (Befund, kein Gate).
- **Schema additiv:** `features` bleibt ein **offenes** Objekt
  (`additionalProperties`: number/int/bool/string/null), über `feature_version`
  versioniert, damit die Merkmalsliste ohne Schema-Bruch wachsen kann; `verdict`
  `$ref`t die bestehende `printability`-Definition (das exakte Urteil verbatim).

**Belegt** (`core/tests/test_pruef_check.py`): ein Datensatz je geprüftem
Repräsentanten mit Kern-Merkmalen + exaktem Urteil (Stufe 2); Stufe 1/`error`
sammeln nichts; `with_placement` fail-soft; end-to-end schreibt `pruef_dataset`
(versioniert, `cpu-exakt`, Platzierung/Podest angereichert) schema-valide ins
Lauf-Artefakt; ein Stufe-1-Lauf trägt **keinen** Block und lädt/validiert
unverändert (Additivität/US 12). ruff + scoped Core-Tests grün. Kein ADR
(Architektur in PRD #183), kein README (internes Datenartefakt, kein
nutzersichtbares Feature; Konsumenten #217/#218/#219).

## 2026-07-14 — Zielfunktions-Modul + Einstellungs-Fenster: lexikographisch/gewichtet über EINEM Gewichts-Satz (Issue #212)

**Frage.** PRD #183 Stufe 3 (Grill 2026-07-14, Entscheidungen 1–3): Wie wird
die Zielfunktion der Zerlegungs-Suche implementiert — Komparator, Persistenz,
Fenster — bevor Scorer (#216) und Beam (#217) sie konsumieren?

**Entscheidungen (Umsetzung entlang des Grills):**

- **Modul `fgc.decompose.objective`, Kriterienwerte injiziert.** Der Komparator
  (`candidate_key`/`compare_candidates`) rechnet über `KriterienWerte`
  (erreichbar, Umsetzvorgänge, Fugenfläche mm², kinematische Marge mm, c_v) —
  keine Karte, kein Raycast: die Lieferanten verdrahtet die Beam-Suche
  (#216/#217). Dadurch deterministisch und ohne Geometrie-Stack testbar
  (Schnitt-Entscheidung aus dem Verissuen-Log 2026-07-14).
- **K.-o. als erste Schlüssel-Komponente.** `candidate_key` beginnt mit
  `0/1` (erreichbar/nicht) — ein unerreichbarer Kandidat verliert in BEIDEN
  Lesarten gegen jeden erreichbaren; kein Gewicht wiegt das auf. Erwogen:
  Erreichbarkeit als hoch gewichtetes Kriterium — verworfen (Grill: hartes
  K.-o., kein Gewicht).
- **Ein Gewichts-Satz, zwei Lesarten.** Aus (Default): Gewichts-Reihenfolge =
  Rangfolge (`ranking()` sortiert absteigend), lexikographischer Vergleich der
  quantisierten Werte; An: gewichtete Summe über DENSELBEN quantisierten Werten
  (die Quantisierung normiert die Einheiten auf Bin-Zählungen — kein zweiter
  Normierungs-Mechanismus). Default-Gewichte 4/3/2/1 entlang der
  Grill-Rangfolge Umsetzvorgänge > Fugenfläche > Marge > c_v.
- **Quantisierung: `floor(value/step + 0.5)`,** Schrittweiten als benannte
  Verfahrens-Parameter (`QUANT_FUGENFLAECHE_MM2 = 50 000` ≙ 0,05 m²,
  `QUANT_MARGE_MM = 25`, `QUANT_VOLUMEN_CV = 0.05`, Umsetzvorgänge Schritt 1 =
  identisch) — alle PROVISORISCH bis zur Eichung an echten Kandidaten nach
  AP 2; die Marge wird vor der Quantisierung negiert (größer = besser).
- **Gleichstand im Aus-Modus doppelt verhindert:** UI-seitig
  (`objectiveSaveBlocked` sperrt Speichern + benennt die Kriterien, Grill
  Entscheidung 3) UND Core-seitig (`ObjectiveConfig.__post_init__` wirft —
  kein stiller mehrdeutiger Komparator, falls ein Client die GUI umgeht). Im
  An-Modus (Summe) ist Gleichstand zulässig.
- **Setter `set_objective_for_job` bumpt `cutplan` echo-fest** —
  `bump_if_changed={"cutplan": ("objective",)}` (#199): anders als die reinen
  Parametrier-Setter (#81/#90, bewusst ohne Bump), denn ein unter der alten
  Zielfunktion GESUCHTER Plan ist nach der Änderung ehrlich veraltet (die
  Suche #217 konsumiert die Config). Persistenz sparse: der Default entfernt
  das `objective`-Feld — Altprojekte byte-gleich.
- **Lauf-Provenienz trägt die komplette Config** (`decompose.json →
  provenance.objective`: Lesart + Gewichte + Schrittweiten) — gestempelt in
  `_persist_decompose_run` (die eine Persistier-Tür, #198), AUCH für den
  Default (der Paper-Benchmark pinnt ihn). Erwogen: eigener Artefakt-Block —
  verworfen, der Grill sagt „in die Lauf-Provenienz" (ADR-004); der
  provenance-`$def` (setup.schema) bekommt das optionale Feld dokumentiert.
- **Fenster als Overlay im Reiter Zerlegung** („⚖ Zielfunktion …" unter
  „Automatisch vorschlagen", Muster ⌘K-Palette: `hidden`-Sichtbarkeit):
  Aufwiegen-Schalter + vier Gewichtsfelder (aus der Kriterien-Registry
  `objective-state.ts` gebaut) + Lesart-Zeile, die Rangfolge/Summe benennt.
  Reine Logik in `ui/objective-state.ts` (getestet), DOM in `ui/objective.ts`,
  Nachziehen über das Übernahme-Protokoll (`adoptActiveJob`, #193).

**Belegt** (`core/tests/test_objective.py`, `viewer/src/ui/objective-state.test.ts`):
lexikographisch vs. Summe entscheiden an denselben Kandidaten verschieden;
K.-o. schlägt jeden Score (beide Lesarten); Quantisierungs-Gleichstand reicht
ans nachrangige Kriterium durch; Setter echo-fest (gleicher Wert bumpt nicht,
hin+zurück = zwei Bumps), Default sparse/byte-gleich; Provenienz trägt die
volle Config (Default + konfiguriert); Fenster: Default vorbelegt,
speichert/lädt roundtrip, Gleichstand nur im Aus-Modus gesperrt (benannt),
DOM-Vertrag der Element-IDs. Kontrakt-Golden `set-objective.contract.json`
(+ Manifest-Regen). Kein ADR (Architekturentscheid liegt im PRD-#183-Grill,
hier Umsetzung).

## 2026-07-14 — SdfObstacleProvider: SDF-Backend am Hindernis-Provider-Vertrag, FCL-Nachprüfer im Grenzband (Issue #213)

**Frage.** PRD #183 AP 1, letzte Scheibe: Wie verheiraten Glied-SDF (#207) und
Druckstand-Punktwolke (#208) zur Punkt-gegen-Glied-SDF-Inversion, sodass (a)
der bestehende Provider-Vertrag `obstacle_provider: Callable[[int],
ObstacleSet]` hält, (b) die Befunde **byte-identisch** zur FCL-Referenz
bleiben (US 2) und (c) der Backend-Schalter auf App-Ebene liegt, nicht in
`CollisionConfig` (PRD-Kommentar 2026-07-14)?

**Entscheidungen.**

- **Der injizierte Provider IST der Backend-Schalter.**
  `SdfObstacleProvider` (`collision/sdf_provider.py`) erfüllt den Vertrag
  (`__call__` delegiert an `druckstand.obstacle_provider` — dieselben Meshes
  speisen den FCL-Nachprüfer) und trägt zusätzlich die SDF-Abfrageflächen;
  `find_collisions` erkennt sie per Duck-Typing (`_sdf_surface`). Ein
  schlichter Callable läuft byte-identisch wie bisher (US 12). Konstruktion +
  Umschaltung leben im neuen App-Ebenen-Modul `collision/backend.py`
  (`set_collision_backend`, Env `FGC_COLLISION_BACKEND`, Default `fcl`);
  fehlendes/ungültiges SDF-Artefakt fällt soft auf die FCL-Referenz zurück.
  Erwogen: Schalter in `CollisionConfig` — verworfen (PRD: Konfiguration
  beschreibt das Urteil, nicht die Maschinerie; GPU-Naht #205 bleibt bei
  `check_representative`).
- **Befund-Identität durch Konstruktion: SDF filtert, FCL urteilt.** Die
  Inversion liefert je Glied eine **untere Schranke** der exakten Distanz
  (Punkt-AABB-Breitphase + Bins, Top-K in die Batch-SDF-Abfrage, Deckungs-
  radius abgezogen); nur im **Grenzband** (Schranke ≤ Sicherheitsabstand)
  läuft der unveränderte FCL-Referenzpfad. Jedes Paar mit exakter Distanz
  < Sicherheitsabstand landet zwingend im Grenzband ⇒ rote/gelbe Samples,
  Verursacher und Eindringtiefen identisch; nur sicher-grüne Zahlen dürfen
  abweichen (beiderseits konservative Schranken).
- **Befund (Messung): fcl-Distanzen penetrierender Paare hängen an der
  set_transform-Historie des Managers** (Early-Exit im dynamischen AABB-Baum;
  positive Distanzen sind historie-frei, Abfragen read-only — Sonden-Skript
  2026-07-14). Erster Wurf (SDF überspringt `_set_parts`) lieferte darum
  abweichende Eindringtiefen auf den Denkmal-Modulen. Konsequenz: das
  SDF-Backend **stellt die Referenz-Transformhistorie exakt nach** (Trigger =
  Gruppen-AABB-Lücke wie bisher) und spart nur die read-only-Abfragen. Damit
  sind alle 16 Denkmal-Prüf-Tür-Befunde `to_dict()`-identisch (verifiziert).
  Notiert: derselbe Effekt bedeutet, dass schon heute voller Befund und
  Prüf-Tür (andere Sample-Menge) verschiedene Eindringtiefen melden können —
  „byte-genau" ist nur je Aufrufmuster definiert.
- **Selbstkollision im Punkt-Schema.** Punkte von Glied j (Urteilsgeometrie-
  Oberfläche, dieselbe deterministische Sampling-Funktion wie #208; Tool-Hülle
  liefert die Punktseite für Paare mit dem Endeffektor) gegen das SDF von
  Glied i; die früher bedingungslose FCL-Paar-Distanz läuft nur noch im
  Grenzband. Der Endeffektor selbst (kein eigenes SDF) urteilt gegen
  Hindernisse weiter über den Referenzpfad.
- **Deckungsradien (konservativ, dokumentierte Annahme):** Druckstand-Wolke
  `hypot(√2·spacing, layer_height)`, Glied-/Tool-Samples `spacing/√3`.
  Voraussetzung: Grundriss-Features deutlich breiter als der Punktabstand
  (15 mm vs. Wanddicken ≥ ~100 mm) — dünnere Features könnten die Deckung
  verletzen (dann greift der Nachprüfer nicht sicher); als Grenze notiert.
- **Performance-Stand (ehrlich, Vorgriff auf #215):** Sonde (256 Punkte,
  früher Grenzband-Beweis), Drift-Anker (1-Lipschitz-Schranke, Wiederver-
  wendung über Samples), Bin-Breitphase, Gather-Cache; dazu zwei bit-neutrale
  Beschleunigungen bestehender Module (Trilinear-Gather statt Ganz-Gitter-
  `astype` in `glied_sdf`; vektorisiertes `covers` im Grundriss-Sampling
  #208). Auf den **tiefroten** Denkmal-Modulen bleibt die SDF-Tür ~2× langsamer
  (10–22 s vs. 5–6,5 s je Modul): die Byte-Identität erzwingt dort ohnehin
  Transform-Replay + FCL-Urteile — der Gewinn liegt bei grünen/gelben Bahnen
  (Suche #216/#217), nicht bei Dauer-Rot. Optionen für #215, falls die
  Vorher/Nachher-Zahl nicht reicht: batchweise Schranken über alle Samples je
  Glied (Shen-Batching quer zur Bahn) oder ein historie-freies Urteil
  (paarweise fcl.distance) — Letzteres bräche die bestehenden Goldens und
  wäre ein eigener Entscheid.

## 2026-07-14 — Reichweitenkarte als Vorfilter der Platzierung: ein Parameter, drei Aufrufer (Issue #214)

**Frage.** Wie wird die binäre 4D-Reichweitenkarte (#210) als **Vorfilter** vor
Bewertungsmodus, Optimalvorschlag und Kollisions-Advisor verdrahtet, ohne dass sie
je „urteilt" (ADR-007/#164) und ohne Altläufe zu brechen (US 12)?

**Entscheidung.** Analog zum `config_filter`-Muster (#200/#201): **ein Parameter (die
Karte), drei Aufrufer**. Die Karte lebt fachlich in `kinematics`, die Wand-Geometrie
in `placement` — die eine neue Adapter-Naht `fgc.placement.reachmap` verheiratet beide
über den bestehenden #201-Seam (`flange_targets` → `frames_in_wall`), **ohne**
`t_wall_base` oder die `nozzle_quat`-Konvention zu duplizieren.

- **Bewertungsmodus** (`evaluate`, Parameter `reach_map`): trägt bei gesetzter Karte
  ein **getrenntes** Feld `reach_estimate` (`is_estimate: true`, `source:
  reachability_map`) — die Karten-Schätzung des erreichbaren Anteils (US 7). Das
  IK-Urteil `reachable_fraction` (Ampel-Basis) bleibt unberührt (US 11). `to_dict`
  nimmt den Schlüssel **nur** mit, wenn eine Karte gerufen wurde → ohne Karte
  byte-gleich (US 12).
- **Optimalvorschlag** (`suggest`, Parameter `reach_map`): streicht **vor** der teuren
  `evaluate`-Schleife die laut Karte aussichtslosen Kandidaten (`option_survives`).
  **Lenient** (nur Schätzung 0 fällt weg — die Karte hat am Raster keine falschen
  Negative, #210) und **fail-soft** (leerer Filter ⇒ volles Raster, kein Verhungern):
  die Top-n_best bleiben das IK-Urteil.
- **Standplatz je Höhenreihe** (`reachmap.standplatz_fuer_reihe`, US 5/6): punktweises
  **Minimum über die Bahnposen** (`min_over_poses`) — die Basen, die garantiert *alle*
  Posen der Reihe erreichen. Konstruierte Reihe im Test: zentral-nahe Basen decken
  alles, eine lateral versetzte erreicht 3/7 Posen (Teilfall „erreicht eine, aber
  nicht die ganze Reihe") und fällt heraus.
- **Kollisions-Advisor** (`collision.advisor.advise`, Parameter `reachable`): der
  reine Advisor bleibt DOM-/Geo-frei — die Karte kommt als injiziertes Prädikat
  (wie `simulate`). Nur der **Platzierungs-Hebel** bewegt die Basis, also prüft das
  Prädikat nur ihn; unerreichbare Gegenmaßnahmen werden **vor** der Neu-Simulation
  verworfen → kürzere Liste (US 8, nachgewiesen im Test).

**Verdrahtung fail-soft.** Die Aktionen (`suggest_placement`, `advise_collision`)
laden die Karte über den einen Punkt `_reach_map_for_robot` — jeder Fehlbestand (kein
Artefakt, veraltete Provenienz US 18, Roboter ohne Kinematik) wird zu `None`, die
Aktion läuft dann byte-gleich zu Altläufen.

**Alternativen verworfen.** (a) Die Karte in `reachable_fraction` einrechnen — bräche
die Ehrlichkeitsregel (die Karte würde urteilen) und die Ampel. Verworfen: die
Schätzung steht als eigenes, markiertes Feld daneben. (b) `reach_estimate` immer
serialisieren — bräche die byte-Gleichheit der Altläufe/Goldens. Verworfen:
konditionales `to_dict`. (c) Den aggressiven Vorfilter (hohe Schwelle) — könnte am
Raster echte Kandidaten wegfiltern (falsche Negative zwischen Knoten). Verworfen:
lenient (nur Schätzung 0) + fail-soft, damit `evaluate` der Richter bleibt.

**Test.** `core/tests/test_reachfilter.py` (10 Fälle): Standplatz = UND über die Reihe
(konstruierte Reihe, deckt alle vs. Teilfall), Schätzung gekennzeichnet + Urteil/Ampel
unverändert, Advisor-Liste kürzer, `evaluate`/`suggest`/`advise` ohne Karte byte-gleich.
Die bestehenden `test_placement`/`test_collision_advisor*`/`test_reachability` bleiben
grün (byte-Gleichheit belegt, inkl. Schema-Validierung des Platzierungs-Artefakts).

## 2026-07-14 — Nachtrag #214: Bewertungsmodus-Aktion reicht die Karte durch (AC2 end-to-end)

**Lücke.** Die Kern-`evaluate()` füllt `reach_estimate` nur mit injizierter Karte —
die Aktion `evaluate_placements` (die den `placement.json`-Bewertungslauf schreibt)
rief sie aber **ohne** `reach_map`. Die gekennzeichnete Schätzung landete daher nie im
Artefakt/der API-Antwort; AC2 war nur auf Kern-Ebene, nicht end-to-end erfüllt.

**Fix.** `evaluate_placements` lädt die Karte fail-soft (`_reach_map_for_robot`, wie
`suggest_placement`) und reicht sie an `evaluate(..., reach_map=…)` durch. Das
`score`-Schema (`schemas/placement.schema.json`, `additionalProperties: false`)
bekommt das optionale, **nicht-required** `reach_estimate`-Feld — mit Karte trägt jede
Option die markierte Schätzung, ohne Karte fehlt der Schlüssel (Altläufe byte-gleich,
US 12). Ampel/`reachable_fraction` unverändert.

**Kein Viewer-Handgriff.** Die früheren placement-Wrapper sind mit #134 aus
`viewer/src/api/projects.ts` entfallen; die Route `POST …/placements` hat keinen
TS-Spiegel mehr (Antwortmodell `EvaluatePlacementsResponse.scored: list[dict]`, lose).
Das additive Feld fließt durch die dict-Nutzlast, ohne einen Spiegeltyp oder das
Kontrakt-Orakel (#202) zu brechen — daher kein Vitest nötig.

**Test.** Zwei Aktions-Fälle in `test_placement.py`: mit real vorhandener doosan-Karte
trägt jede Option im Artefakt (und in `scored`) die gekennzeichnete `reach_estimate`
(`is_estimate: true`, `source: reachability_map`), Ampel-Basis daneben unverändert;
ohne Karte (fail-soft `None` gepatcht) fehlt der Schlüssel — byte-gleich.

## 2026-07-14 — AP-1-Nachher-Messung + Abnahme: SDF vs. FCL je Aufrufort, Default-Aufruf-Kontingent abgeleitet (Issue #215)

**Frage.** PRD #183 AP 1, Nachher-Hälfte von US 13 + **AP-1-Abnahme**: Wie schnell
ist die Glied-SDF-Prüf-Tür (#213) gegenüber der FCL-Referenz **je Aufrufort**
(Arm↔Hindernis vs. Selbstkollision), konfigurationsgleich zur Baseline (#206)? Und
welches **Default-Aufruf-Kontingent** folgt daraus nach dem Grill-Budget-Verfahren
(2026-07-14)?

**Methode.** Neue Sonde `docs/spikes/s5_scripts/s5_ap1_after.py` (Sonde 5) auf dem
re-gepinnten `s5_harness` (um Roboter + `DruckstandSpec` erweitert, damit der
`SdfObstacleProvider` konfigurationsgleich zur FCL-Referenz gebaut wird). Sie ruft das
**echte** `find_collisions` je Backend × self-Konfiguration auf der produktiv
verdünnten Auswahl (`travel_stride=5`, 11 968 Samples, Denkmal/Modul). **Baseline
unmittelbar neu erhoben** (Drift-Warnung aus #206 bestätigt: FCL self=False heute
**4,23 s**, nicht 7,03 s wie #206 — nur die konfigurationsgleiche Neuerhebung liefert
einen belastbaren Y-Faktor). Protokoll `docs/spikes/S5c_ap1_nachher_abnahme.md`,
Artefakt `last_ap1_after.json`.

**Gates grün.** Determinismus (FCL + SDF, self=False, je zweimal byte-identisch);
**Befund-Identität (#213-Regressionsanker)** FCL == SDF je self-Konfiguration:
self=False **5106 rot / 1142 gelb / 5720 grün**, min −149,824 mm, worst_index 9794;
self=True **5123 / 6845 / 0**, min −214,13 mm, worst_index 11542 — rot/gelb + Verursacher
+ Eindringtiefe byte-identisch. **Der Speedup gilt nur mit identischen Befunden** — das
ist hier belegt (nur sicher-grüne Abstandszahlen dürfen beiderseits konservativ
abweichen).

**Ergebnis — Y-fach je Aufrufort (ehrlich):**

| Aufrufort | FCL | SDF | Y = FCL/SDF |
|---|---:|---:|---:|
| Arm↔Hindernis (self=False, Median/3) | 4,23 s | 9,77 s | **0,43 ×** |
| Selbstkollision (Wall(self=True) − Wall(self=False)) | 100,5 s | 237,6 s | **0,42 ×** |

Auf diesem **tiefroten** Denkmal-Modul ist die SDF-Tür ~2,3–2,4× **langsamer** — auf
beiden Aufruforten. Das ist **kein Fehlschlag, sondern exakt der in #213 vorab
dokumentierte Befund**: Byte-Identität erzwingt auf Dauer-Rot ohnehin Transform-Replay
+ FCL-Grenzband-Urteile; wenn praktisch jedes Sample im Grenzband liegt (self=True: 0
grün), kommt die SDF-Breitphase oben drauf, ohne Abfragen sparen zu können. Der Gewinn
der SDF-Inversion liegt bei **grünen/gelben Bahnen** (die Suche #216/#217 bewertet
überwiegend nicht-kollidierende Kandidaten), nicht bei Dauer-Rot. Ehrlich so
ausgewiesen — kein Schönrechnen; die #213-Optionen (Shen-Batching quer zur Bahn /
historie-freies Urteil) bleiben als spätere Beschleunigung notiert.

**AP-1-Abnahme (relativ, Entscheidung 2026-07-14): abgenommen.** Beide Teile liegen
vor — Vorher/Nachher je Aufrufort (konfigurationsgleich, deterministisch) **und**
Befund-Identität. Die absolute 10-s-Marke bleibt bei #144/#150 (blockiert AP 1 nicht).
**Entblockt #205-G1:** dessen „≥10× vs. Glied-SDF" braucht die SDF-Zeit als Nenner —
Arm↔Hindernis 9,77 s / Selbstkollision-Block 237,6 s; #205 per Kommentar informiert.

**Default-Aufruf-Kontingent.** Grill-Verfahren: größte runde Aufruf-Zahl mit
Hintergrundlauf ≤ ~5 min (300 s). Ein „Aufruf" = eine exakte Prüf-Tür
(`find_collisions` je Kandidat, produktiv self=False, SDF); Messung 9,77 s ⇒
300/9,77 = 30 roh ⇒ **20** (≈195 s ≤ 300 s). Festgeschrieben als benannte Konstante
**`fgc.decompose.propose.DEFAULT_CALL_BUDGET = 20`** — dasselbe Modul, das die
Beam-Suche #217 importiert (Beam-Breite k daraus abgeleitet); je Druckjob
übersteuerbar, die Provenienz trägt den Wert. Der Wert ist **konservativ** (aus dem
langsamsten, tiefroten Fall — grüne Kandidaten laufen schneller).

**Alternativen verworfen.** (a) Zeit-Budget in Sekunden statt Aufrufen — nicht
byte-vergleichbar (#178-Entscheid, Invarianz-Orakel US 25). (b) Kontingent aus einem
grünen (schnelleren) Lauf ableiten — überschätzte die real leistbare Aufrufzahl auf
schwierigen Wänden; der Worst-Case ist die sichere Wahl. (c) Konstante in `objective`
oder einem neuen `beam`-Modul — verworfen: die Such-Obergrenzen leben bereits in
`propose` (`MAX_DIVISIONS`), #217 baut auf `propose._refine`.

**Kein ADR** (Mess-/Abnahme-Scheibe + Verfahrens-Vollzug, kein Architekturrang).
**Kein README-Abschnitt** — das Kontingent ist ein interner Such-Parameter, noch nicht
nutzersichtbar (der Konsument, die Beam-Suche #217, ist ungebaut; Präzedenz #206/#213:
Planungsstand ohne README). GitHub: #205-Kommentar mit den Messzahlen (G1-Nenner).

## 2026-07-14 — Zerlegungs-Strategie-Interface + Band-Raster-Generator + billiger Scorer (Issue #216)

**Frage.** PRD #183 Stufe 3 (Grill 2026-07-14, US 19): Wie werden die drei
Suche-Bausteine geschnitten — Strategie-Naht, Kandidaten-Generator, billiger
Scorer — bevor der Beam-Loop (#217) sie konsumiert, ohne den heutigen
`propose`-Pfad zu verändern und ohne Prüf-Tür?

**Entscheidungen:**

- **Interface als Extraktion, nicht als Neubau.** `propose._refine` (#203) ist
  nach `fgc.decompose.strategie` gewandert: `ZerlegungsStrategie.waehle_raster
  (RasterAufgabe) → RasterWahl`; der bisherige Loop lebt zeichenidentisch als
  `GreedyAchsenVerfeinerung` weiter (Default in `propose` — Pläne bit-gleich,
  Goldens in `test_decompose` grün). Die `RasterAufgabe` trägt **beide**
  Sichtweisen: `frac_at`/`start`/`cap` (Orakel-getriebene Greedys — der
  #165-Greedy hängt an derselben Naht, kein Umbau dort) und optional
  `kandidaten`/`bewerte`/`objective`/`call_budget` (kandidaten-basierte
  Strategien, Beam #217; `None`-Defaults = heutiger Pfad, fail-soft wie #214).
  Erwogen: zwei getrennte Interfaces je Strategie-Familie — verworfen (US 19
  verlangt EINE Naht für den byte-vergleichbaren Paper-Vergleich; ein
  Interface, dessen Aufgabe beide Kontexte trägt, hält den Vergleich fair).
  `provenance()` nennt Strategie + Surrogat-Modellstand (`None` bis #219) —
  gestempelt wird der Block vom Zerlegungslauf (#217, ADR-004).
- **Generator: Band-Raster in stabiler Ordnung.** `fgc.decompose.kandidaten`
  erzeugt alle achsparallelen `n_länge × n_höhe`-Raster bis `cap`
  (`MAX_DIVISIONS`), Schnitte aus `propose._build_cuts` (nichts dupliziert —
  ein Sieger ist 1:1 ein `propose`-Raster). Ordnung deterministisch grob→fein
  (Teilanzahl, dann Höhen-, dann Längenteilung) als Teil des
  Byte-Versprechens; Kandidatenzahl `cap²` klein (Z-Chunking-Warnung vor 2^n).
- **Scorer: Karte + EIN Masken-Raster, keine IK je Kandidat.**
  `fgc.decompose.scorer.BilligerScorer.bewerte(kandidat)` liefert die
  #212-`KriterienWerte` samt Diagnose (`KandidatBewertung`): Erreichbarkeit
  (K.-o.) und **Anzahl Standplätze** aus `standplatz_fuer_reihe` (#214,
  punktweises Minimum über Unter- UND Oberkante jeder Höhenreihe), bottom-up
  zu Umsetzvorgängen gruppiert (aufeinanderfolgende Reihen mit gemeinsamem
  Standplatz teilen einen — Min-Aggregation über Reihen); **kinematische
  Marge** als Karten-Proxy „Standplatz-Robustheit" (Chessboard-Distanz der
  Standplatz-Maske × Gitterschritt, PROVISORISCH bis AP-2-Eichung wie die
  #212-Schrittweiten); **Fugenfläche, c_v, Raycast-Inselkarte** per Masken-/
  Matrixbewertung nach Han (Gl.-6–9-Muster: ein bool-Raster der Wandfront,
  vektorisiert; Inselzählung im Z-Chunking-Muster, `INSEL_RASTER_MM = 10` statt
  1 mm — Bau-Maßstab). Öffnungen als injizierte Maske; >1 Insel je Teil =
  Fragment-Indiz (Wu-Analogon) als **Diagnose für #217-Verworfen-Gründe**
  (US 10), bewusst kein zweites K.-o. neben der Erreichbarkeit. Erwogen:
  exakte Geometrie statt Maske (teurer, Han/Z-Chunking belegen das Raster)
  und Marge aus IK-Stichproben (widerspricht „billig, keine IK je Kandidat").
  Reihen-Masken je Höhenlinie memoisiert (gleiche Linie ⇒ eine Kartenabfrage,
  Ergebnis bit-gleich). Alles Schätzung/Vorfilter (ADR-007/#164) — das Urteil
  bleibt bei der Prüf-Tür, die hier bewusst nicht vorkommt.

**Belegt** (`core/tests/test_zerlegung_suche.py`, 13 Tests): Greedy trägt das
Interface + Provenienz-Block; injizierte Strategie steuert `propose`
nachweislich, Default bit-gleich zum extrahierten Loop; Generator + Scorer
deterministisch (zwei frische Instanzen ⇒ bit-gleiche Kandidaten/Bewertungen);
Masken-Matrix analytisch verankert (volle Front) und öffnungs-ehrlich (Fuge
durch Öffnung = 0, Inseln zählen, c_v > 0 bei Asymmetrie); **Scorer→Komparator
end-to-end**: Karten-K.-o. an echten Kandidaten (3,2-m-Wand ungeteilt verliert
gegen jede gedeckte Teilung), unter Erreichbaren entscheidet die Fugenfläche,
`candidate_key`-Sortierung reiht komplett. Kein README (interne Such-Bausteine
ohne GUI-Sichtbarkeit, Präzedenz #215); kein ADR (Architekturrang liegt im
PRD-#183-Grill, hier Umsetzung).

---

## 2026-07-15 — Kollisionsgetriebene Verfeinerung an der Strategie-Naht (Issue #165)

**Frage.** Wie wird `propose_decomposition` *kollisionsgetrieben* (Constraint-Serie
Scheibe 4, Karte #139 / Entscheidung #141): eine Zelle gilt erst als gut, wenn sie
**von der besten automatischen Option aus** frei ist (Prüf-Tür #162) — angehängt an
die #216-Strategie-Naht, ohne zweiten Verfeinerungs-Loop.

**Entscheidung.**
- Neue Strategie `KollisionsGetriebeneVerfeinerung` in `fgc.decompose.strategie`,
  implementiert dasselbe `ZerlegungsStrategie.waehle_raster(RasterAufgabe)` wie der
  Achsen-Greedy (#216) — **eine** Naht, kein paralleler Loop. Statt des billigen
  Reichweiten-Orakels `frac_at` treibt ein **injiziertes Prüf-Tür-Orakel**
  (`RasterAufgabe.pruef_tuer: (BandRasterKandidat, row_index, ZellenOption) → PruefBefund
  | None`) die Verfeinerung. `fgc.decompose` bleibt **geo-frei** (Duck-Typing
  `PruefBefund`-Protokoll auf `ClearanceVerdict`).
- **Hebel-Reihenfolge (strikt #141):** je Zelle deterministisches Menü
  (`option_menu`) — Basis → **IK** (prozessneutral, je Achse beide Zweige) →
  **Platzierung** (Standoff/Aufstellhöhe/seitlich, als **Deltas** auf die je Reihe
  gesuchte Basis-Lage, damit Orakel und `propose` dasselbe Delta auf dieselbe Basis
  anwenden — byte-vergleichbar). Reicht Hebel 1 nicht, subdividiert die Verfeinerung
  **entlang der verursachenden Achse aus dem Befund** (`causing_axis`).
- **Verursachende Achse — aus dem Befund, keine Heuristik.** `causing_axis` liest die
  `causer_position_mm` (abschnitts-lokal, #181) und vergleicht die relative Auslenkung
  aus der Zellmitte: `rel_x = |x|/(Länge/2)` gegen `rel_z = |z−Höhe/2|/(Höhe/2)`. Die
  größere Achse ist „zu groß" → geteilt. **Gleichstand und fehlende Position ⇒ Höhe**
  (der „Bandhöhe senken zuerst"-Vorrang der #141-Reihenfolge). *Erwogen:* eine feste
  Heuristik „immer Höhe zuerst" — verworfen, weil #141 ausdrücklich „entlang der
  verursachenden Achse" fordert; und ein Richtungsvektor statt Position — der Befund
  trägt aber Position + Verursacher-Glied (#181), keinen Vektor.
- **Kipp/Tiefe nie automatisch:** das Menü kennt kein Kipp/Lead-Feld (prozessrelevant,
  bleibt Advisor-Hebel), und die Verfeinerung teilt nur Höhe/Länge (Band-Raster, kein
  Tiefen-Freiheitsgrad — #142). Beides durch Negativ-Invarianten-Tests gesichert.
- **Aufruf-Kontingent statt Zeitbudget (#178/#215):** die Strategie zählt jeden
  Orakel-Aufruf hart gegen `call_budget` (Default `DEFAULT_CALL_BUDGET`=20); erschöpft
  ⇒ best effort (ehrlich rot). Determinismus: gleiche Aufruffolge ⇒ gleicher Schnitt,
  maschinenunabhängig. `MAX_DIVISIONS`-Deckel bleibt.
- **Fail-soft:** ohne Orakel oder bei `None`-Befund (unzuständig, keine
  Kollisions-Geometrie) fällt die Strategie auf den Achsen-Greedy zurück (byte-gleiche
  Pläne) — nie ein geratenes „frei" (ADR-013).

**Nachvollzug.** Der gewählte **Platzierungs-Hebel** landet je Reihe in den
Teil-Platzierungen (`propose` addiert das Delta auf die Reihen-Platzierung); die
Provenienz (Strategie/Kontingent/Aufrufe/Hebel je Reihe) trägt ein neuer additiver
Block `DecompositionPlan.refinement` → `decompose.json.refinement` (Schema erweitert,
additiv; Altläufe byte-gleich). Der IK-Hebel bleibt in der Provenienz (das Plan-Modell
trägt keine IK — die wendet der Aufrufer über `process_params.ik_config` an).

**Produktive Verdrahtung.** `fgc.pipeline.sectionsim.collision_pruef_tuer` baut das
echte Orakel über den **wiederverwendeten `SectionSimContext`** (#189): Kandidaten-
Schnitte als temporäre Plan-Eingaben durch dieselbe `plan_for_job`-Tür, Zell-Option als
Advisor-Override versuchsweise angewandt, Urteil aus derselben Travel-verdünnten
Prüf-Tür wie Stufe 2 (`section_clearance_check`, #162) — keine Parallel-Metrik.
`propose_decomposition(refine_collisions=True)` schaltet sie ein (Default aus ⇒
byte-gleich); `plan_for_job` reicht `pruef_tuer`/`call_budget` an `propose` durch, nur
Art „abschnitt" + Auto-Vorschlag.

**Belegt** (`core/tests/test_decompose_kollision.py`, 18 Tests, synthetisches Orakel wie
die Advisor-Tests): (a) ein kollidierender Fall endet frei — Re-Prüf-Orakel je finalem
Teil frei, für Höhen- **und** Längen-Subdivision entlang der Befund-Achse; (b) gewählte
Optionen in `plan.refinement` + Teil-Platzierung + `decompose.json` (schema-valide);
(c) Determinismus (zwei Läufe ⇒ bit-gleicher Schnitt + Optionen); (d) Negativ-
Invarianten Kipp/Tiefe nie automatisch. Plus Kontingent-Deckel, `MAX_DIVISIONS`-Deckel,
Greedy-Fallback (kein Orakel / unzuständig), Default-Pfad byte-gleich. Kein ADR
(Architekturrang liegt in #141/#183; hier Umsetzung an der bestehenden #216-Naht).

## 2026-07-15 — Beam-Suche end-to-end: zweite Strategie an der #216-Naht, k aus dem Kontingent, Relaxationsleiter (Issue #217, PRD #183 Stufe 3)

**Frage.** Die Bausteine der Zerlegungs-Suche standen (Strategie-Interface #216,
Generator/Scorer #216, Zielfunktion #212, Kontingent #215, Datensammel-Pflicht
#211, Prüf-Tür #190). Wie fügt sich die **Beam-Suche end-to-end** zusammen, ohne
einen Sonderpfad neben Greedy und kollisionsgetriebener Verfeinerung aufzumachen?

**Entscheidung.** `fgc.decompose.beam.BeamSuche` implementiert dieselbe schmale
Tür `ZerlegungsStrategie.waehle_raster(RasterAufgabe) → RasterWahl` (#216) —
kein zweiter Loop. Ablauf: **alle** Band-Raster-Kandidaten billig bewerten
(`aufgabe.bewerte`, gratis), per `candidate_key` (#212) ordnen, die besten **k**
behalten, **nur die Überlebenden** durch die Prüf-Tür (`aufgabe.pruef_tuer`, je
Reihe von der besten automatischen Option aus). Der erste vollständig
kollisionsfreie Kandidat gewinnt (Ehrlichkeitsregel ADR-007: „geprüft frei" nur
aus der Prüf-Tür).

**k aus dem Kontingent (kein Parameter).** `beam_breite(call_budget) = max(1,
budget)` — der Beam hält so viele Kandidaten, wie das harte Kontingent (#215) im
günstigsten Fall (ein Aufruf je Kandidat) exakt prüfen könnte. **Ein** Kontingent
steuert damit Vorauswahl (billig) und Prüfung (teuer); deterministisch,
byte-vergleichbar (US 25 — Aufrufe zählen, keine Zeit).

**Relaxationsleiter (US 22, Grill 2026-07-14 Entsch. 5).** Bei leerem Ergebnis
Stufe für Stufe, **jede gezündete Stufe namentlich** in der Provenienz:
(1) `mehr_teile` — feinere Band-Raster bis `MAX_DIVISIONS` regenerieren und
prüfen; (2) `mehr_standplaetze` — via injizierter `rescore`-Fabrik mit
erweitertem Podesthöhen-Satz neu bewerten; (3) `tiefenteilung_vorschlag` — reiner
Hinweis (#166-Muster, **manuell**, nie automatisch) + best-effort-Vorschlag
(ehrlich ungeprüft, `evaluate` färbt). **Alternative** „mehr Teile = Kandidaten
jenseits k prüfen" verworfen: weil k = Kontingent, ist nach der Beam-Prüfung kein
Kontingent mehr übrig — die Stufe wäre toter Code; „mehr Teile" ist daher das
**Anheben des Teilungs-Deckels** (Regeneration), nicht das Erweitern des Fensters.

**Nie relaxiert:** Sicherheitsabstand, Erreichbarkeits-K.-o. (unerreichbar wird
nie Sieger — nur best effort), Ehrlichkeitsregel, Kipp-/Tiefenteilungs-Automatik
(Menü ohne Kipp/Lead, Band-Raster bleiben 2D). Abbruch (`should_cancel`) zündet
keine weitere Stufe (best effort, `cancelled` in der Provenienz).

**Metriken + Verworfen-Gründe.** Der additive `refinement`-Block trägt den
**Metriken-Katalog je Lauf** (US 20: Teilanzahl, c_v, Fugenfläche, erreichbarer
Anteil, geprüft-frei-Anteil, Standplätze, `rechenzeit_s` — diagnostisch, nicht
Teil der Entscheidung), die **Verworfen-Gründe je Kandidat** (US 10:
`reichweite`/`fragment`/`kollision`, dedupliziert) und den Relaxationsausweis. Die
#211-Kandidaten-Urteile+Merkmale landen unverändert über `assess_plan` →
`pruef_dataset` beim Prüfen des Sieger-Plans (keine zweite Datenspur).

**Verdrahtung.** `propose(..., scorer=…, objective=…, pruef_tuer=…)` schaltet die
Beam-Suche ein (`_grid_counts` baut die `RasterAufgabe` mit `bewerte`/`objective`
und wählt `BeamSuche`, wenn ein Scorer da ist; explizite `strategie` gewinnt
immer). Ohne `scorer` byte-gleich (Greedy / #165-Verfeinerung). Viewer:
`ui/refinement-state.ts` (`verworfenRows`/`relaxAusweis`/`beamSummary`, reine
Ableitung, ADR-007) + TS-Typen `DecompositionRefinement`/`RefinementRejection`/
`RefinementMetrics` (additiv, Golden ohne `refinement` bleibt valide).

**Belegt** (`core/tests/test_beam_suche.py`, 17 Tests, synthetische Lieferanten
+ ein Integrationsteil mit echtem `BilligerScorer`): kollidierende Zerlegung wird
nicht vorgeschlagen (US 9), nur Überlebende durch die Prüf-Tür, Kontingent-
Determinismus bit-gleich (US 25), Leiter Stufe für Stufe (US 22) + Nie-Relaxieren-
Negativtests, Verworfen-Gründe (US 10), Metriken-Katalog vollständig (US 20),
Hintergrundlauf Fortschritt/Abbruch (Muster #145/#175 im Thread), Fail-soft
(kein Scorer / unzuständig ⇒ Greedy). Viewer: `refinement-state.test.ts` (8 Tests).
Kein ADR (Architekturrang in #141/#183; Umsetzung an der bestehenden #216-Naht).

## 2026-07-15 — Beam-Suche end-to-end in actions verdrahtet: produktive Scorer-Fabrik + Hintergrundlauf (Issue #217, Nachtrag)

**Frage.** Die Beam-Strategie hing an der `propose`-Ebene und war voll getestet,
aber in `actions.propose_decomposition` nicht aktivierbar — im echten App-Lauf lief
nie ein Beam (Greedy-Default), kollidierende Zerlegungen wären weiter vorgeschlagen
worden (untergräbt AC US 9 + Hintergrundlauf im Realbetrieb).

**Entscheidung.** Drei Nähte ergänzt, alle fail-soft + byte-gleich im Default:
1. **Scorer-Fabrik** `actions._beam_search_setup(pc, job, workstation, stand_mode)`:
   baut `BilligerScorer` aus `_reach_map_for_robot` (#210, fail-soft — ohne Karte
   `(None, None, None)` ⇒ Greedy), `objective_from_job` (#212) und die konfigurierte
   `BeamSuche` (Fortschritt/Abbruch + `rescore`-Fabrik für die Stufe „mehr
   Standplätze": Podesthöhen-Satz aus `_workstation_heights`, `floor`→`elevated`).
2. **Aktivierung** `propose_decomposition(beam_search=True, on_progress=,
   should_cancel=, robots_dir=)`: baut `pruef_tuer` (collision_pruef_tuer, #165) +
   Beam, reicht `scorer`/`objective`/`strategie` durch `plan_for_job`→`propose`; der
   Sieger fließt durch die bestehende `_persist_decompose_run`/`DecomposeBundle`-Tür
   (#198), `decompose_artifact` serialisiert `plan.refinement` (Metriken/Verworfen/
   Relaxation) unverändert. `beam_search` hat Vorrang vor `refine_collisions`; ohne
   Karte fällt es byte-gleich auf Greedy zurück (die teure Prüf-Tür läuft dann nicht).
3. **Hintergrundlauf** `checkjobs.start_beam_propose`/`get_beam_propose`/
   `cancel_beam_propose` (+ `BeamProposeJob`): dasselbe In-Process-Registry-Muster wie
   `start` (#175) — Daemon-Thread, Fortschritt in Prüf-Tür-**Aufrufen**, `threading.
   Event`-Abbruch, älterer Lauf desselben (Projekt, Druckjob) wird abgebrochen.

**Offen (bewusst, eigenes UI-Issue):** ein sichtbarer HTTP-Endpoint + Viewer-Trigger
für den Beam-Hintergrundlauf (analog `POST …/decomposition-check`) ist NICHT gebaut —
die Actions-Funktion + der Background-Job sind fertig und getestet, der Aufrufer fehlt.

**Belegt** (`core/tests/test_beam_actions.py`, 6 Tests): Scorer-Fabrik aus echter
(grob gebauter) `ReachabilityMap` + fail-soft ohne Karte; End-to-end durch
`propose_decomposition(beam_search=True)` mit gefaktem `collision_pruef_tuer` —
kollidierender grober Schnitt wird nicht vorgeschlagen, kollisionsfreier Sieger +
vollständiger Metriken-Katalog + Kollisions-Verworfen-Grund im persistierten,
schema-validen `decompose.json`; Default + fehlende Karte byte-gleich (kein
`refinement`); Hintergrundlauf `start_beam_propose` läuft mit Fortschritt bis `done`.

---

## 2026-07-15 — Datenkampagne: systematisches Sampling + Etikettierung mit Label-Quelle, Datensatz-Artefakt (Issue #218)

**Frage:** Wie liefert der Surrogat-Kaltstart (PRD #183 Stufe 4, US 24) einen
reproduzierbaren, veröffentlichbaren Trainingsdatensatz — ein Batch-Skript, das
den Kandidatenraum systematisch sampelt, mit der exakten Prüf-Tür etikettiert und
je Etikett seine **Label-Quelle** ausweist, ohne auf #205/GPU zu warten?

**Alternativen erwogen:**
- *Etikettierung über den echten Projekt-/IFC-Pfad* (`check_decomposition`): verworfen
  — die Prüf-Tür lädt das Wand-Mesh aus IFC (`section_sim_context`), ein standalone
  Batch bräuchte je Wand ein synthetisches IFC-Modell + Projekt. Stattdessen
  etikettiert das CPU-Orakel selbst-enthaltend über **synthetische Quaderwände**
  mit derselben Kette (`from_cuts`→`apply`→`slice_wall`→`build_trajectory`→
  `section_clearance_check`), nur ohne die IFC-Naht.
- *Label-Quelle als globales Datensatz-Feld* (ein Wert für den ganzen Lauf):
  verworfen — die Policy v1 (Grill 2026-07-14) verlangt **je Etikett** die Quelle
  (`cpu-exakt` | `gpu+cpu-grenzband` | `gpu+stichproben-audit`), damit ein
  gemischter Datensatz (GPU-vorsortiert + CPU-Grenzband + Audit) sauber filterbar
  bleibt; `gpu+stichproben-audit` ist **nicht trainingstauglich**, je Sample so
  markiert (`training_safe`).
- *Merkmale neu definieren:* verworfen — der Kandidaten-Kern spiegelt feldweise
  `pruefung._collect_samples` (#211) unter derselben `FEATURE_SCHEMA_VERSION`, damit
  Kampagne und Laufbetrieb deckungsgleich sind (#219 mischt beide Quellen).

**Entscheidung:** Zwei Module. Die **reine, geometriefreie Hälfte**
`fgc.decompose.kampagne` (Sampling-Plan, Kandidaten-Aufzählung, Verschnürung,
Umfangsansage) mit **injizierbarem Etikettier-Orakel** (`LabelOracle`, Muster wie
`assess_plan`/`check_representative` #190 — tief testbar ohne Geometrie); die
**geometrie-behaftete Hälfte** `fgc.pipeline.kampagne` (`cpu_exact_oracle`,
`select_oracle` GPU-bevorzugt→CPU-Fallback, `run_data_campaign`). CLI `fgc campaign`
mit Umfangsansage (`campaign_scope`, ~9,77 s/Etikett aus AP-1 #215), Bestätigung
(`--yes`/`--dry-run`), `--limit`-Mini-Stichprobe und Ctrl-C→Teilstand.

- **Sampling-Plan** deterministisch: kartesisches Produkt sortierter Achsen-Gitter
  (Länge×Höhe×Dicke) × stabiler Band-Raster-Generator (#216); Sampling-Einheit =
  Höhenreihen-Repräsentant (ungünstigste Zelle = letzte Spalte, `n_earlier_parts =
  order−1`). Default: 3×3×2 Achsen, `cap=3`. Gleicher Plan ⇒ bit-gleiche
  Kandidatenmenge (US 25).
- **Datensatz-Artefakt** (`dataset_artifact`, ADR-004): Provenienz (Quell-Kommando,
  Zeitstempel, Git-Commit), Sampling-Plan, `feature_version`, `label_source_distribution`
  (Herkunftsverteilung), Trainings-Ausweis (`training_safe_count`/`non_training_count`),
  Samples mit `label_source` + `training_safe`; `partial` bei Abbruch oder `--limit`.
- **GPU-Naht:** `gpu_available()` stets `False` (#205 nicht integriert); `select_oracle`
  fällt geräuschlos auf `cpu_exact_oracle` zurück — die Kampagne wartet nicht auf #205.
- **Fail-soft** (ADR-013): ein an einem Kandidaten gescheitertes Etikett wird
  übersprungen (als `ungeprueft`/`error`-Verdict), kippt nie den Nachtlauf.

**Begründung:** Die Naht-Wahl (reines Orakel-Interface) hält die Kampagnen-Logik
byte-vergleichbar und schnell testbar; die synthetische Quaderwand macht das Batch
standalone (kein IFC), ohne die produktive Prüf-Tür-Kette zu duplizieren. Kein ADR
(kein Architekturrang) — die Provenienz-/Ehrlichkeits-Prinzipien sind ADR-004/-013,
das Merkmals-Schema #211, die Label-Policy der PRD-#183-Grill 2026-07-14.

**Belegt** (`core/tests/test_kampagne.py`, 19 Tests): Determinismus (gleicher Plan ⇒
gleiche Kandidaten/Datensätze); CPU-only-Fallback vollständig etikettiert; Label-Quelle
je Sample + Herkunftsverteilung; Audit nicht trainingstauglich; Umfangsansage;
Abbruch→Teilstand + `--limit`-partial; Fail-soft bei Orakel-Fehler; Datensatz mit
Provenienz + Merkmals-Schema deckungsgleich #211; CLI dry-run + Schreiben (gefaktes
Orakel); `slow`: echtes CPU-exaktes Orakel etikettiert über die volle Geometrie-Kette.

## 2026-07-15 — Surrogat-Vorsortierer: deterministisches GBM, invarianter Beam-Einbau (Issue #219)

**Frage:** PRD #183 Stufe 4 — das **Surrogat** über den #211-Kandidaten-Merkmalen:
welches Lernmodell, wie deterministisch trainiert (fester Seed ⇒ bitgleich, nur
policy-konforme Labels), und **wie in die Beam-Suche (#217) einbauen, ohne Urteil
oder besten Kandidaten zu verändern** (Invarianz-Orakel US 25, Ehrlichkeitsregel
ADR-007/#164)?

**Modellwahl:** kleines **Gradient-Boosting** (logistischer Verlust, Newton-Blätter,
`max_depth=3`, 60 Runden) — kein Deep Learning (PRD). `scikit-learn` ist **nicht** im
venv; statt eine schwere Abhängigkeit einzuziehen, eine **dependency-arme, exakt
deterministische** GBM-Implementierung in numpy (`fgc.decompose.surrogat`): gierige
Least-Squares-Splits mit stabilen Tie-Breaks (erstes Merkmal, kleinste Schwelle),
**keine Zufallsquelle** (kein Subsampling). Damit ist Determinismus **unbedingt**;
der `seed` pinnt die (heute leere) stochastische Fläche und wandert in die Provenienz
— „fester Seed ⇒ bitgleiches Modell" gilt trivial und ist so getestet.

**Merkmale:** bewusst der **Kandidaten-Kern** (`SURROGATE_FEATURES` = die
`feature_core`-Felder: Abschnittsmaße, Wandposition, Wandmaße, `n_earlier_parts`) —
**ohne** die Platzierungs-/Podest-Merkmale. Begründung: zur **Vorsortier-Zeit** (Ordnen
der Kandidatenliste) liegt die per-Reihe gesuchte Platzierung noch nicht vor; das
Surrogat ist ein Vorsortierer, kein Gate — eine Merkmals-Teilmenge kostet nur
Sortier-Güte (Benchmark #220), nie Korrektheit. `feature_version` (#211) versioniert
die Bedeutung; das Laden validiert sie (US 26).

**Policy-Filter:** trainiert **ausschließlich** aus `TRAINING_LABEL_SOURCES`
(`cpu-exakt` + `gpu+cpu-grenzband` — letztere wird nur bei bestandenem #205-G1-Gate
vergeben); `gpu+stichproben-audit` und urteilslose Zeilen (`collides` kein `bool`,
z. B. `error`/`ungeprueft`) werden **verweigert** (`policy_filter`). Kein Trainingsrest ⇒
`ValueError` (nie ein stiller Fehlkomparator). Der Trainings-Ausweis nennt
benutzt/verworfen transparent.

**Einbau (der Kern der Entscheidung):** Das Surrogat ist in v1 **ausschließlich
Vorsortierer** der Beam-Kandidatenliste — es **reordnet nur die Pruef-Reihenfolge**
(`BeamSuche(surrogat=…)`, duck-typed `vorsortiere`/`stamp`; Risiko-Score je Kandidat =
Maximum der Reihen-Kollisionswahrscheinlichkeit, „vermutlich frei zuerst"). Damit das
Ergebnis **invariant** bleibt, wurde die Sieger-Auswahl von „**erster** kollisionsfreier
gewinnt" auf „**zielfunktions-bester** kollisionsfreier gewinnt" umformuliert
(`beam._pruefe`): der Sieger ist der Kandidat mit kleinstem Zielfunktions-Rang, den die
Prüf-Tür frei sah — **unabhängig von der Pruef-Reihenfolge**. In Zielfunktions-Ordnung
ist das **byte-gleich** zum alten Verhalten (der erste freie ist dann per Definition der
zielfunktions-beste; alle #217-Goldens bleiben grün); mit Vorsortierer ändern sich **nur
Reihenfolge und Zeit**, nie Sieger oder Urteil. Verworfen wird nie, in Ampel/Befund
taucht das Surrogat nicht auf — die einzige Spur ist `refinement.surrogate_model`
(Modellstand: Datensatz-Stand, Seed, Merkmalsliste/-Version), sonst `None` (US 12).

**Verworfen:** (a) Surrogat als **Tie-Break unter der Zielfunktion** in `_ordne` — würde
den Sieger innerhalb von Zielfunktions-Gleichständen verschieben (Invarianz gebrochen).
(b) Surrogat **entscheidet** (erster frei gewinnt in Surrogat-Ordnung) — bricht Invarianz
und die Ehrlichkeitsregel; das gehört in den **budget-limitierten Benchmark-Arm** #220
(Sollbruch-Gate), nicht in den invarianten v1-Vorsortierer. (c) `scikit-learn`/LightGBM
als Abhängigkeit — zu schwer für den einen kleinen Vorsortierer; die numpy-GBM ist klein,
deterministisch und ohne Build-Kette.

**Artefakt/Laden (US 26):** versioniertes Modell-Artefakt (`kind`, `schema_version`,
`feature_version`, `features`, `seed`, Hyperparameter, Provenienz, Datensatz-Stand,
Trainings-Ausweis, serialisierte Bäume). `from_artifact`/`load_surrogat` validieren
Kennung, Schema und **Provenienz** (fremde Merkmals-Version/-Liste ⇒ `ValueError`); ein
Altlauf ohne Modell lädt unverändert (`load_surrogat(None/fehlt) → None` ⇒ Beam byte-gleich).
CLI `fgc surrogate-train --dataset … --out … --seed …`.

**Begründung:** Kein ADR (kein Architekturrang; die Prinzipien sind ADR-004 Provenienz,
ADR-007/#164 Ehrlichkeit, #211 Merkmals-Schema, PRD-#183-Grill 2026-07-14 Label-Policy).
**Treffsicherheit ist bewusst KEIN Unit-Assert** (PRD Testing Decisions) — sie ist
Gegenstand des Benchmarks #220.

**Belegt** (`core/tests/test_surrogat.py`, 14 Tests): Invarianz-Orakel mit
**adversarischem** (umkehrendem) Vorsortierer **und** echtem Modell (identischer
Schnitt + Optionen + Urteil, nur Reihenfolge/Zeit); Trainings-Determinismus (Seed ⇒
bitgleiches Modell + Artefakt); Policy-Filter verweigert `gpu+stichproben-audit` und
urteilslose Zeilen nachweislich, `gpu+cpu-grenzband` trainiert mit; Laden mit falscher
Merkmals-Version/-Liste/Kennung schlägt fehl; `load_surrogat` fail-soft (fehlt ⇒ `None`),
streng bei vorhandener Fehl-Provenienz; Vorsortierer verwirft nie. Alle #217-Beam-Tests
(`test_beam_suche`/`test_beam_actions`) bleiben grün (byte-gleiche Sieger-Auswahl).

## 2026-07-15 — Benchmark-Harness: Greedy vs. Beam vs. Beam+Surrogat, byte-vergleichbar, Sollbruch-Gate mechanisch (Issue #220)

**Frage:** Wie stellt man die drei Zerlegungs-Arme (Greedy #165, Beam #217,
Beam+Surrogat #219) fürs Vergleichspaper gegeneinander — auf **einem eingefrorenen
Stand**, **byte-vergleichbar**, ausschließlich CPU, und so, dass jede Paper-Kennzahl
**ohne Nachrechnen** belegbar ist? Und wie entscheidet man mechanisch, ob der dritte
(und ggf. vierte) Arm überhaupt läuft, ohne je zu warten?

**Entscheidung.** Zwei Hälften nach dem Kampagnen-Muster (#218/#190): der **reine
Harness** `fgc.decompose.benchmark` (Gate, Auswertung, Protokoll — geometriefrei, tief
testbar mit injiziertem **Arm-Läufer**), die **produktive Verdrahtung**
`fgc.pipeline.benchmark` (Arme über die eine Tür `propose_decomposition`, Modell-Gate,
Ablage). CLI `fgc benchmark --project … [--model …] --out …`.

- **Eine Tür, drei Schalter.** Alle Arme laufen über `propose_decomposition` mit
  **demselben Aufruf-Kontingent** (#215) auf demselben Druckjob: Greedy
  `refine_collisions=True`, Beam `beam_search=True`, Beam+Surrogat
  `beam_search=True, surrogat=model`. Dafür wurde `propose_decomposition` um einen
  `surrogat=`-Parameter ergänzt (durchgereicht an `_beam_search_setup`, Default `None`
  ⇒ byte-gleich zum reinen Beam) — die einzige Produktionsänderung. So ist der Vergleich
  an der #216-Naht fair, kein Sonderpfad (US 27).
- **Sollbruch-Gate mechanisch (Grill 2026-07-14), nie stillschweigend.** `surrogat_gate`
  prüft drei Bedingungen der Reihe nach und bricht beim ersten Fehlschlag ab (kein Datum,
  kein Retry, kein Warten): (1) Modell vorhanden (`load_surrogat` fail-soft ⇒ `None`;
  ein vorhandenes, aber provenienz-falsches Artefakt dokumentiert
  `load_surrogat_gate` als `modell-ungueltig` statt zu crashen), (2) **v1-policy-konform**
  (Merkmals-Version/-Liste im Modellstand + Trainings-Ausweis ⊆ `cpu-exakt`/`gpu+cpu-grenzband`,
  kein Audit-Rest), (3) **Invarianz-Orakel grün** (`mechanical_invariance_check`: ein
  kleiner deterministischer Beam-Lauf mit/ohne Vorsortierer → identischer Sieger + Urteil,
  US 25). Nur alle drei ⇒ dritter Arm. `decide_arms` setzt zwei-/drei-/vierarmig zusammen;
  der **vierte Arm Beam+GPU** entfällt (`gpu_available()` ⇒ `False`, #205-G2 nicht fertig),
  im Protokoll mit Grund. `GateDecision.to_dict` hält Grund je Arm fest.
- **Auswertung nur aus Laufartefakten, byte-gleich (US 20/21/27).** `evaluate_run` liest
  **nur** das `decompose.json` je Arm — kein Geometrie-Nachrechnen: Teilanzahl,
  erreichbarer Anteil (Sektions-Ampeln), geprüft-frei-Anteil (Beam: Metriken-Katalog;
  Greedy: aus `rows`), Standplätze (aus den Teil-Platzierungen), Verworfen-Gründe
  (`reichweite` = Karten-Vorfilter #214). c_v/Fugenfläche stehen **nur** im
  Beam-Metriken-Katalog; der Greedy trägt sie nicht ⇒ ehrlich `null` (statt Geometrie
  nachzurechnen). Die **Rechenzeit** ist diagnostisch getrennt (`diagnostik`,
  maschinenabhängig) — **nicht** im Byte-Vergleich (US 25): Wiederholung eines CPU-Arms
  ⇒ byte-gleiche `kennzahlen`.

**Alternativen verworfen:** (a) Arme direkt über die Strategie-Einheit
(`waehle_raster`) statt `propose_decomposition` fahren — verworfen, weil dann die reale
Lauf-Provenienz (`provenance.objective` #212, Sektions-Ampeln, `refinement`) fehlt; die
eine produktive Tür ist der ehrlichere Vergleich. (b) Den Greedy nachträglich um einen
Metriken-Katalog erweitern, damit c_v/Fugenfläche uniform sind — verworfen, weil das
#165s Artefaktform (und Goldens) ändert; ehrliches `null` + „kein Nachrechnen" ist
korrekter. (c) Bad-Provenance-Modell den Benchmark crashen lassen — verworfen: das Gate
läuft mechanisch zweiarmig weiter, dokumentiert den Grund.

**Begründung:** Kein ADR (kein Architekturrang; die Prinzipien sind ADR-004 Provenienz/
Byte-Vergleichbarkeit, ADR-007/#164 Ehrlichkeit, PRD-#183-Grill 2026-07-14
Sollbruch-Gate + vierter Arm opportunistisch). README-Abschnitt (`fgc benchmark`).

**Belegt** (`core/tests/test_benchmark.py`, 12 Tests): Gate zweiarmig ohne Modell /
dreiarmig mit gültigem Modell / zweiarmig bei Policy-Bruch (Audit-Rest) bzw. rotem
Invarianz-Orakel — jeder Entscheid dokumentiert; `mechanical_invariance_check` grün für
echtes **und** adversarisch-umkehrendes Modell; `evaluate_run` liest nur das Artefakt
(Beam mit Katalog, Greedy ohne ⇒ `null`); Wiederholung ⇒ byte-gleiche Kennzahlen
(Rechenzeit ignoriert); Protokoll trägt Gate + Provenienz je Arm. Produktiv durch
`propose_decomposition` (Fakes wie `test_beam_actions`): zweiarmiger End-to-end-Lauf
(Protokoll geschrieben, Auswertung nur aus den run_dirs, Wiederholung byte-gleich) und
dreiarmiger Lauf (Beam == Beam+Surrogat in den deterministischen Kennzahlen — Invarianz
US 25 —, nur der Modellstand in der Provenienz unterscheidet). ruff grün; alle
#217/#219-Bestandstests bleiben grün.

## 2026-07-15 — Beam-Zerlegungslauf auslösbar: HTTP-Trias + Viewer-Trigger für den Hintergrundlauf (Issue #221, Folge #217)

**Frage:** #217 hat die Beam-Zerlegung end-to-end verdrahtet und getestet — Actions-Naht
(`propose_decomposition(beam_search=True)`), produktiver Scorer, Prüf-Tür, Persistenz des
Siegers, **und** den Hintergrund-Job (`checkjobs.start_beam_propose`/`get_beam_propose`/
`cancel_beam_propose`). Es fehlte nur der **Auslöser**: keine HTTP-Route, kein Viewer-Knopf.
Wie zieht man ihn nach, ohne neue Logik im Viewer und byte-arm gegen die Kontrakt-Goldens?

**Entscheidung.** Die bestehende **entkoppelte Stufe-2-Prüf-Tür (#175)** ist die exakte
Vorlage — dasselbe „start spawnt Thread, gibt sofort `id` zurück; Viewer poll't; cancel
setzt Signal"-Muster. Also eine **analoge Trias** `…/decomposition-beam[/{beam_id}[/cancel]]`
als **dünner Wrapper** (ADR-014) über die schon fertigen `checkjobs`-Beam-Funktionen; im
Viewer der **gleiche Poll-Loop** wie `startPruefCheck` und dieselbe Panel-Mechanik.

- **Response = Griff-Objekt.** `BeamProposeStatusResponse` spiegelt `BeamProposeJob.to_dict`
  1:1 (`beam_id`/`state`/`n_done`/`n_total`/`run_dir`/`sections`/`print_jobs`) — Fortschritt
  zählt **Prüf-Tür-Aufrufe** (Aufruf-Kontingent #215), nicht Sekunden.
- **Such-Ausweis in der Antwort, nicht per Zweit-Fetch.** Das Griff-Objekt trug bisher
  **nicht** den `refinement`-Block (Verworfen-Gründe US 10, Relaxationsausweis US 22,
  Metriken US 20) — der lebt im `decompose.json` des Siegers. Additiv ergänzt: `BeamProposeJob`
  bekommt ein Feld `refinement`, das `checkjobs._run` bei `done` **einmal aus dem Sieger-Lauf
  nachliest** (`_read_refinement`, fail-soft: fehlt der Block, weil der Beam auf den Greedy
  fiel, bleibt es `None`). So speist der Viewer `refinement-state.ts` direkt aus der
  Poll-Antwort — kein getrenntes `/@fs`-Nachladen, konsistent mit „Core rechnet, Viewer
  zeigt" (ADR-007). Kein zweiter Rechenschritt, nur ein Datei-Lesen.
- **Viewer rein Verdrahtung.** API-Client (`startBeamPropose`/`getBeamPropose`/
  `cancelBeamPropose`), eine **neue reine** Fortschritts-Ableitung `beamProgressView`
  (DOM-frei, vitest — Muster `checkProgressView` #175) neben den bestehenden
  `beamSummary`/`relaxAusweis`/`verworfenRows`, und die DOM-dünne Anbindung in `druckplan.ts`
  (Knopf/Progress/Cancel + `setBeamStatus`/`setRefinement`/`_renderBeam`). **Keine neue
  Kinematik/Logik** (ADR-007).
- **Kontrakt-Golden (#202).** Die Start-Route ist als COVERED registriert
  (`decomposition-beam.contract.json` ↔ `BeamProposeStatus`), GET+cancel als TODO (gleiches
  Modell — wie die #175-Trias). Golden ist wie bei `decomposition-check` ein
  **Running-Snapshot** (Start kehrt sofort zurück); die `done`-Variante mit Sieger/refinement
  ist als Folgeticket vermerkt.

**Alternativen verworfen:** (a) Die Route liest `decompose.json` selbst, statt das Griff-Objekt
zu erweitern — verworfen, weil die Route dünn bleiben soll (ADR-014) und das Griff-Objekt der
kanonische Ort für „alles, was die Poll-Antwort trägt" ist (wie `CheckJob`). (b) Kein
`refinement` in der Antwort, Viewer lädt es wie beim Projekt-Öffnen per `/@fs` aus dem
run_dir — verworfen, weil das einen zweiten, verzögerten Netzwerkweg für Daten schafft, die
der Lauf ohnehin gerade produziert hat; das Issue verlangt Verworfen-Gründe/Metriken **in der
Response**. (c) Eigenes Panel/Reiter — verworfen, der Block gehört sichtbar neben die
Prüf-Tür im Reiter Zerlegung.

**Begründung:** Kein ADR (kein Architekturrang; die Prinzipien sind ADR-014 dünner Wrapper,
ADR-007/#164 Ehrlichkeit + „Core rechnet, Viewer zeigt", das #175-Hintergrundlauf-Muster).
README-Abschnitt (Beam-Auslöser) + status.md-Notiz.

**Belegt:** neue vitest-Fälle für `beamProgressView` (laufend/Kontingent-unbekannt/done/
abgebrochen/Fehler); Kontrakt-Golden regeneriert (`FGC_REGEN_API_GOLDENS=1`, Manifest frisch,
21 COVERED); volle Prüf-Suite grün.

## 2026-07-15 — Glied-SDF-Provenienz plattformunabhängig: Zeilenenden vor dem Hash normalisieren (CI/Linux rot, Windows grün)

**Frage:** Der Nacht-Orchestrator-Batch (#206–#220) lief lokal (Windows) grün, aber
die Linux-CI ist seit dem Glied-SDF-Batch (#207) rot — jeder Merge #206…#220 mit
`conclusion: failure`, unbemerkt. 14 Errors + 1 Folgefehler, alle eine Wurzel:
`SdfProvenanceError` „Quellgeometrie hat sich seit dem Build geändert".

**Root Cause:** `glied_sdf.source_fingerprint` hasht `read_bytes()` der Quell-`.json`
**roh**. `.gitattributes` schützt nur die `.npy`-Gitter vor CRLF-Normalisierung; die
gehashten `.json` sind Text → Windows-Checkout **CRLF**, Linux-CI **LF** (`core.autocrlf`).
Ein auf Windows gebautes Manifest speichert CRLF-Hashes → Windows-Load matcht (grün),
Linux-Load hasht LF ≠ gespeichert → rot. Klassisch (vgl. Einträge 2026-07-10
„CI war rot, seit der Geometrie-Stack kam" / „CI/Linux rot, Windows grün").

**Alternativen verworfen:** (a) SDF-Artefakte nicht committen, in CI bauen — Build ist
teuer (VHACD/Voxel), die `.npy` sollen versioniert/reproduzierbar sein. (b) Nur
`.gitattributes eol=lf` + renormalisieren, ohne Code-Fix — der Hash bliebe zeilenenden-
abhängig; wer mit abweichender `core.autocrlf`/Editor-Config baut, bräche die Provenienz
erneut. (c) Quell-`.json` als binär markieren — es sind editierbare Textartefakte, binär
verlöre saubere Diffs.

**Entscheidung:** Zwei Ebenen. (1) `source_fingerprint` normalisiert Zeilenenden
**byte-weise** vor dem Hash (`\r\n`→`\n`) — der Fingerabdruck ist damit plattform- und
git-config-unabhängig, egal wie die Datei ausgecheckt ist. (2) Zusätzlich `.gitattributes
robots/collision/**/*.json text eol=lf` als Hygiene (kanonisch LF, saubere Diffs), analog
zum bestehenden `.npy`-binary-Schutz. Manifest neu gebaut ⇒ gespeicherte Hashes LF-
normalisiert; die `.npy` blieben bit-identisch (nur `manifest.json` geändert).

**Begründung/Beleg:** Kein ADR. Bewiesen: `hash(roh CRLF)=c636…` ≠ `hash(norm LF)=cd6f…`
= gespeichert im neuen Manifest ⇒ Windows (CRLF→LF normalisiert) **und** Linux-CI (LF)
berechnen beide `cd6f…` == gespeichert. Prozess-Lehre: Batch-Verifikation nur lokal auf
Windows verdeckt genau diese Klasse — die Linux-CI ist der maßgebliche Prüfstand, nicht
der lokale Lauf. 27 SDF-Tests + ruff grün lokal; CI-Grün ist der eigentliche Beleg.

## 2026-07-22 — Placement-Vorschlag: Machbarkeit statt Erreichbarkeit, Sweep-Wissen als Prior (ADR-026)

**Frage:** Die Standardvorschläge von `placement.suggest` sind oft suboptimal —
die Sweep-Studien (`experiments/collision_standoff_sweep`) belegen: der
automatische Vorschlag (230 mm) ist voll erreichbar, aber tief kollidierend
(−258 mm). Wie wird das Placement verbessert, und wie fließen die gesammelten
Messdaten (Abstand-, Dicken-, IK-, Basishöhen-Sweeps, W×T-Prädikat-Gitter) ein,
ohne je Vorschlag alles neu zu rechnen?

**Alternativen verworfen:** (a) Sweep-Daten als *Urteil* (Nachschlagetabelle
statt Kollisionsrechnung) — verworfen, die Dicken-Studie belegt starke
Geometrieabhängigkeit (Bandhöhe 760→10 mm über die Dicken), fremde Messwerte
urteilen auf neuer Geometrie falsch. (b) Voller Kollisionsbefund je Kandidat —
verworfen, ~13 s je Kandidat, interaktiv unbrauchbar. (c) Hartes Kollisions-Gate
— verworfen, „alle rot" ist laut Studie ein reguläres Ergebnis; leere
Vorschlagslisten brächen Aufrufer. (d) Auto-Loop `suggest`→Zerleger bei
Unmachbarkeit — verworfen, verfilzt zwei Module und holt die teure
Zerlegungssuche ungefragt in den Vorschlagspfad. (e) Gefittete
H_max(W,T)-Formel als Konstanten — verworfen, 9 Stützstellen mit belegt
nicht-monotonen Effekten (Basishöhe 300 top, 600 kippt): Interpolation über
eine versionierte Tabelle ist ehrlicher als ein Fit. (f) Prior nur bei exaktem
Tool-Namen — verworfen, Anforderung ist Weitergeltung für geometrisch ähnliche
Tools. (g) Volle IK-Achse (alle 8 je Zelle) — verworfen, 6 von 8 Konfigs sind
laut IK-Pilot fast überall wertlos (~10 mm Bandhöhe). (h) Legacy-Schalter fürs
alte Verhalten — verworfen, das alte Ziel ist durch Messung widerlegt; für
Benchmarks bleibt der Altzustand über die vorhandenen Parameter explizit
konstruierbar.

**Entscheidung:** Sechs Punkte, Details in **ADR-026**: (1) Grob-Check (#131)
default-an als zweiter **Vorfilter vor** `evaluate` (Muster Reichweitenkarte
#214, gleiches Fail-soft); Kollisionsurteil vorderster Sortierschlüssel +
explizites Machbarkeits-Feld im Score. (2) „Kein machbarer Kandidat" = Signal
zum Zerlegen, lose gekoppelt über Pipeline/Viewer an den vorhandenen Trigger
(#221/#222). (3) W×T-Gitter wird versionierte **Prior-Tabelle** im Core
(Roboter+Tool-geschlüsselt, ADR-004-Provenienz wie #219); Prior verdichtet
Raster und ordnet Konfigs, urteilt nie; fehlt er → neutral. (4) Tool-Toleranz =
konfigurierte `safety_distance_mm` (GUI-Zone) für ‖Δ TCP‖ und Δ Hüllmaß;
Hüllmaß wird beim Upload berechnet und additiv im Tool-Artefakt gespeichert.
(5) IK-Konfiguration wird prior-geführte Suchachse (Shortlist + auto,
Eskalation auf alle 8 nur bei Leerlauf); gewählte Konfig wandert in den
Vorschlag nach außen. (6) Harter neuer Default ohne Legacy-Schalter;
Tests/Goldens im selben Zug.

**Datenstand:** W×T-Gitter 9/12 Zellen; die 3 fehlenden (800/1100 × 550,
1100 × 400) brachen mehrfach nativ ab (vermutlich 0xC0000005 wie die
505-mm-Wand) — sie gehen als `angenommen-unmachbar` mit ehrlichem Status in
die Tabelle, nicht als Messwert. Folge-Issues: Crash diagnostizieren + Zellen
nachmessen; Tool-TCP-Studie (aufgeschoben, Tobias 2026-07-22).

**Begründung:** Der Prior kann nichts kaputt machen (er lenkt nur die Suche,
geurteilt wird auf der echten Geometrie) — deshalb darf die
Ähnlichkeits-Toleranz pragmatisch an der Sicherheitszone hängen. Die
Arbeitsteilung Zerleger (vorbeugend) / Placement-Befund (Sicherheitsnetz)
hält beide Module sauber. ADR-026, da Architekturrang (neues Datenartefakt,
bewusster Default-Bruch, Modul-Grenzziehung Placement↔Zerlegung).

## 2026-07-22 — Placement Slice 1 (#228): Grob-Check default-an + Machbarkeits-Befund end-to-end

**Frage:** Wie wird ADR-026 Punkt 1 umgesetzt (Grob-Check default-an, Vorfilter
vor `evaluate`, explizites Machbarkeits-Feld, Gesamt-Befund bis in die
Vorschlags-API), ohne die Modul-Reinheit von `placement.suggest` (geo-frei
startbar) zu opfern und mit minimalem Test-/Golden-Bruch?

**Entscheidungen (klein, aber festgehalten):**
- **Default-an im `suggest`-Prädikat, nicht nur in der Aktion.** AC #1 verlangt,
  dass ein *bare* `suggest(wand, roboter, tool)` kollisionsbewusst ist. Deshalb
  baut `suggest` das Prädikat bei `collision_free=None` **selbst**
  (`default_collision_free`: lazy Import von `collision.coarse` +
  `load_robot_collision_geometry`, fail-soft → `None` = ungeprüft). Alternative
  „nur die Aktion verdrahtet es" verworfen — dann wäre der reine Funktionsaufruf
  nicht default-an. Der Lazy-Import hält `suggest` ohne Geo-Stack startbar.
- **Vorfilter *entfernt* kollidierende Kandidaten (statt sie nur zu demoten).**
  Symmetrisch zum Reichweiten-Vorfilter #214 (`if survivors: grid = survivors`):
  bei vorhandenen freien Kandidaten werden kollidierende **gar nicht bewertet**
  (spart teure `evaluate`-Läufe bei tief kollidierenden Rastern). Der frühere
  Post-`evaluate`-Sortierschlüssel (#131) demotete nur — das bewertete jeden
  Kandidaten teuer. Der Sortierschlüssel bleibt als dokumentierter Anker (unter
  den Überlebenden konstant; trägt den Fail-soft-Fall „alle kollidierend").
- **Kollisionsurteil als optionales Score-Feld** (`PlacementScore.collision`,
  `{free,status,source}`), `to_dict` nur bei Vorhandensein — byte-gleich zum
  reinen Reichweiten-Zustand, wenn der Grob-Check nicht lief (Muster
  `reach_estimate`). Schema `placement.schema.json` additiv erweitert.
- **Gesamt-Befund als eigene schmale Naht** `feasibility_finding` (rein rechnend,
  `checked`/`feasible`/`n_feasible`). `checked=False` ⇒ `feasible=None` (ehrlich
  „unbekannt" bei fehlender Geometrie, nicht „unmachbar"). Der Befund wird in
  `suggest_placement` aus den Vorschlägen verdichtet und über einen neuen
  optionalen `evaluate_placements(collision_predicate=…, feasibility=…)`-Parameter
  bis in `PlacementEvalResult.feasibility` und die API-Antwort durchgereicht —
  der Bewertungsmodus bleibt ohne die Parameter byte-gleich.
- **Alt-Zustand ohne Legacy-Schalter** (ADR-026 Punkt 6 / US 15):
  `collision_free=lambda o: True` = alles frei ⇒ kein Vorfilter, reine
  Erreichbarkeits-Sortierung, kein Feld. Genau ein Test konstruiert ihn so.

**Demo-Beleg (denkmal Modul 1, 785×822 mm, t=510, M1013, Modul-Szene):**
Alt-Default (Erreichbarkeit-only) wählt standoff **300 mm** (`path_collides=True`,
tief kollidierend — deckt sich mit dem ~230-mm-Sweep-Befund); neuer Default wählt
**750 mm** (`path_collides=False`), `feasibility.feasible=True`. Der Standard-
vorschlag ist damit nicht mehr die kollidierende Nahlage.

**Prüfstand:** ruff clean; `test_placement.py`/`test_placement_coarse.py` grün
(Coarse-Suite auf die Vorfilter-Semantik neu geschrieben). Offen für Folge-Slices:
Prior-Tabelle, IK-Achse, Tool-Hüllmaß, Viewer-Ampel.

## 2026-07-22 — Placement Slice 3 (#229): Tool-Hüllmaß beim Upload berechnen

**Frage:** Wie wird ADR-026 Punkt 4 (zweite Größe der Tool-Ähnlichkeits-Regel)
umgesetzt, ohne den Vorschlagspfad mit Mesh-Ladekosten zu belasten und ohne
Altbestand zu brechen?

**Entscheidungen:**
- **Berechnung ausschließlich im Upload-Pfad**, nicht als Property/Lazy-Load auf
  `ToolDef`. `fgc.domain.tool.compute_tool_envelope(mesh_bytes, suffix,
  mesh_transform)` läuft in `create_tool_from_upload` direkt nach
  `validate_mesh_bytes` (trimesh ist dort schon geladen) und wird als
  fertiger Wert an `build_tool_artifact` gereicht — `ToolDef.load` liest nur
  noch das gespeicherte Feld, kein Mesh-Zugriff beim Laden/Vorschlag.
- **Messbezug: Flansch-Frame, nicht Mesh-Roh-Koordinaten.** Die Vertices werden
  mit `mesh_transform` (fehlt ⇒ `IDENTITY_FRAME`) in den Flansch transformiert
  (gleiche aktive-Rotations-Konvention wie
  `fgc.simulation.transform.quat_rotate`, hier als Rotationsmatrix aus dem
  Quaternion für die vektorisierte NumPy-Rechnung). `length_mm` = z-Spanne
  (Flanschachse), `radius_mm` = größter radialer Abstand zur z-Achse — beides
  reine Extremwert-Aggregation, deterministisch unabhängig von
  Vertex-Reihenfolge/Dreiecksliste.
- **Nur bei tatsächlichem Mesh-Byte-Upload neu berechnet.** `update_tool_from_upload`
  liefert ohne neue `mesh_bytes` den vorhandenen `envelope_mm`-Wert der
  bestehenden `ToolDef` unverändert weiter — auch wenn `mesh_transform` sich
  bei der Bearbeitung ändert (Feinversatz #67 ohne Re-Upload). Verworfen: bei
  jeder `mesh_transform`-Änderung neu rechnen (hätte ein zusätzliches
  Mesh-Laden beim reinen Metadaten-Edit erzwungen, gegen „nur beim Upload,
  wo trimesh ohnehin läuft"). Der Prior *lenkt, urteilt nie* (ADR-026) — ein
  kurzzeitig leicht veraltetes Hüllmaß nach einer Fein-Justage ohne Re-Upload
  kostet höchstens Suchqualität, nie Korrektheit.
- **Additives Objektfeld `envelope_mm: {radius_mm, length_mm}`** (eigener
  `$defs/envelope` in `tool.schema.json`, `additionalProperties: false`) statt
  zweier Flat-Felder — hält beide Größen der Ähnlichkeits-Regel als eine
  Einheit zusammen. Migrationslogik identisch zu `compatible_robots` (#71):
  `build_tool_artifact` schreibt das Feld nur bei tatsächlich berechnetem
  Wert; Altbestand/Tools ohne Mesh laden mit `envelope_mm=None` = „unbekannt".
- **API additiv:** `EnvelopeModel` in `ToolInfoModel`, in `GET`/`POST`/`PUT
  /tools` durchgereicht — kein neues Request-Feld (der Wert ist abgeleitet,
  nicht nutzereingegeben).

**Prüfstand:** ruff clean; neue Tests in `test_tool_configurator.py` — deterministische
Werte an Quader-Meshes unter Identität/Translation/90°-Rotation der
`mesh_transform`, Determinismus-Wiederholung, `build_tool_artifact` schreibt/lässt
das Feld weg, Altbestands-Round-Trip byte-gleich ohne das Feld, Create/Update
(mit/ohne neues Mesh) persistieren korrekt, API-Round-Trip (`GET`/`POST /tools`).
Volle Core-Suite grün. Offen für Folge-Slices: Prior-Tabelle (nutzt `envelope_mm`
für die Δ-Hüllmaß-Ähnlichkeit), IK-Achse, Viewer-Ampel.

## 2026-07-22 — Placement Slice 4 (#230): Prior-Artefakt-Format + Lademodul `placement.prior`

**Frage:** In welchem Format wird das W×T-Messwissen versioniert abgelegt, wo lebt
es, und wie liest das Lademodul es konservativ aus — **ohne** schon in die Suche
einzugreifen (das ist #232)?

**Entscheidungen (Format-Details):**
- **Kompakte Zusammenfassung, nicht das Rohgitter.** Das Artefakt trägt je
  (W,T)-Zelle nur H_max + Best-Setup (`{standoff_mm, base_height_mm, ik_config}`),
  nicht die ~Tausende Roh-Zeilen des Gitters. Quelle ist allein `meta_wt.json`
  (Feld `hmax_by_wt`, Zell-Format `[H_max, base_height, config, standoff]`) — die
  `wall_*.json`-Rohdaten werden nicht angefasst. Muster des Surrogat-Ausweises
  (#219): versioniertes Artefakt (`kind: "placement-prior"`, `schema_version: "1"`)
  mit ADR-004-Provenienz, das Laden **validiert** Kennung+Version und wirft bei
  Fremdartefakt (nie stilles Deuten).
- **Volles W×T-Produkt, fehlende Zellen ehrlich.** Der Generator bildet
  `widths × thicks` (12 Zellen) und markiert jede nicht in `hmax_by_wt`
  vorhandene als `status: "angenommen-unmachbar"` (`h_max_mm: null`, `best: null`)
  — die 3 abgebrochenen Zellen (800×550, 1100×400, 1100×550) gehen so als
  **ehrliche Annahme, nie erfundener Messwert** hinein (Ersatz durch Messung #226).
- **Schlüssel Roboter+Tool im Dateinamen + im Inhalt.** Ablage unter neuem
  Repo-Pfad `paths.PRIORS_DIR` (`priors/placement_prior.<robot>.<tool>.json`,
  parallel zu `tools/`, `robots/`). Der Referenz-Tool-Block trägt Name + TCP-Versatz
  + `envelope_mm` (aus #229) — genau die beiden Größen der Ähnlichkeitsregel; fehlt
  das Hüllmaß, steht `null` (nur namensgleiches Tool passt dann). Verworfen: Ablage
  als Python-Paketdaten in `fgc/placement/data/` — der Prior ist Mess*daten*, kein
  Code, und soll ohne Wheel-Rebuild regenerierbar sein.
- **Byte-Stabilität über `sort_keys`, nicht über Insertion-Order.** `dump_artifact`
  serialisiert mit `sort_keys=True, ensure_ascii=False, allow_nan=False` — dadurch
  ist die Ausgabe **unabhängig** von der Zeilen-/Dict-Reihenfolge des Gitters
  (Golden-Roundtrip-Test permutiert `hmax_by_wt` und erwartet bit-gleich). Die
  Provenienz-Pfade werden **repo-relativ** gestempelt (nicht die absolute
  Worktree-Adresse), damit das eingecheckte Artefakt über Maschinen reproduzierbar
  bleibt; der `created`-Zeitstempel darf (wie bei jeder Provenienz) je Lauf
  differieren — der Roundtrip-Test fixiert die Provenienz.
- **Regenerieren ohne Codeänderung:** reine Kernfunktion `build_prior_artifact`
  (Gitter-Meta + Referenz-Tool → Dict) + CLI `python -m fgc.placement.prior_build`
  mit Defaults, die das eingecheckte Artefakt reproduzieren.

**Entscheidungen (Lade-/Query-Modul `placement.prior`):**
- **Konservative Interpolation = nächste schlechtere Zelle, kein Fit.** Für eine
  Modulmaße zwischen Stützstellen wählt `_conservative_cell` die kleinste Zelle mit
  W≥length **und** T≥thickness (größeres W und T ⇒ kleineres H_max). Modulmaße
  **größer** als das Gitter hat keine dominierende Stützstelle ⇒ fehlende Zelle ⇒
  neutraler Prior (kein Extrapolieren ins Blaue). Verworfen: numerische
  Interpolation/Fit — ADR-026 hält die Effekte für nicht-monoton (Knicke), ein Fit
  würde Machbarkeit vortäuschen.
- **Neutraler Prior als eine Antwortform für alle Fehlfälle.** Kein Artefakt,
  fremder Roboter, unbekanntes/unähnliches Tool, außerhalb Gitter,
  provenienz-ungültig ⇒ `NEUTRAL_PRIOR` (`is_neutral=True`), Suche wie ohne
  Messwissen. Ein provenienz-ungültiges/unlesbares Artefakt wird beim Laden
  **übersprungen** (zählt als abwesend), statt zu werfen — ein defektes Prior-File
  darf die Platzierung nie lahmlegen. Der Robot-Filter sitzt im Datei-Glob
  (`placement_prior.<robot>.*.json`) **und** am geladenen Inhalt.
- **`angenommen-unmachbar` ≠ neutral.** Solche Zellen liefern einen
  **neutral-breiten** Prior (keine Verdichtung, leere Konfig-Shortlist) **mit**
  `feasibility_expectation = "infeasible"` — die Erwartung ist Lenkung (breiter
  suchen / Zerlegung erwägen), nie ein Urteil.
- **Tool-Ähnlichkeit:** namensgleich ⇒ immer; sonst ‖Δ TCP-Versatz‖ **und**
  Δ Hüllmaß (max über radius/length) ≤ `safety_distance_mm`. Fehlt das Hüllmaß an
  einem der Tools ⇒ „unbekannt" ⇒ kein Übertrag (großzügig, aber ehrlich — ein
  falscher Prior kostet nur Suchzeit, nie Korrektheit, ADR-026).

**Bewusst NICHT in diesem Slice:** die Einbindung in `suggest` (Abstands-/Höhen-
Verdichtung, IK-Shortlist als Suchachse) — das ist #232. Dieses Modul rechnet nur,
ist isoliert getestet und hat null Aufrufer im Urteilspfad.

**Prüfstand:** ruff clean; `test_placement_prior.py` (19 Tests) — Generator-Golden
(byte-stabil, reihenfolge-unabhängig), Abgleich des eingecheckten Artefakts gegen
das Realgitter (Zellen+Gitter+Tool deckungsgleich, 3 `angenommen-unmachbar`),
konservative Interpolation (exakte/zwischenliegende Stützstelle, worse-cell),
Tool-Ähnlichkeit (innerhalb/außerhalb Zone, fehlendes Hüllmaß), alle Fehlfälle
(fehlendes Artefakt, fremder Roboter, unbekanntes Tool, außerhalb Gitter,
provenienz-ungültig). Volle Core-Suite grün (1107 passed, 3 skipped).

## 2026-07-22 — Placement Slice 2 (#231): wo lebt die Kollisions-Ampel im Viewer, wenn der frühere Gesamtwand-Vorschlag entfallen ist?

**Frage:** #228 liefert je Kandidat `score.collision` + den Gesamt-Befund
`feasibility` fertig gerechnet in der Antwort von `POST …/placement-suggestion`.
Aber genau dieser Wrapper (`suggestPlacement`) und seine UI (die frühere
Vergleichsliste `vorschlag-1/2/3`) sind mit Issue #134 aus dem Viewer entfernt
worden — der Gesamtwand-Optimalvorschlag hat seit der Zerlegung (#80/#132, die
Abschnitts-Platzierung sucht der Core je Teil automatisch) keinen Konsumenten
mehr für die **Auswahl/Anwendung** einer Platzierung. Wo zeigt der Viewer die
Ampel, ohne diese überholte Architektur (Wahl aus einer Gesamtwand-Liste)
wiederzubeleben?

**Alternativen:**
1. Den alten `vorschlag-1/2/3`-Flow (Liste + Auswahl-Knopf) vollständig
   restaurieren.
2. Die Ampel in die Zerlegungs-Sektionsplatzierung einweben (`decompose.propose`
   ruft `suggest` intern) — aber die Zerlegung ruft `suggest` bewusst
   `collision_free=_reachability_only` (Kollision in der Zielfunktion ist
   ADR-026 explizit **out of scope**, eigener Track); der Sektions-Callsite
   trüge also nie ein echtes `score.collision`.
3. Eine **rein lesende Vorschau**: `suggestPlacement` als reiner GET-artiger
   Query-Wrapper (keine Auswahl, keine Persistenz) im bestehenden Accordion
   „Platzierung" des Zerlegungs-Reiters, mit einem Absprung-Knopf zum
   vorhandenen Beam-Trigger bei „kein machbarer Kandidat".

**Entscheidung:** Alternative 3. Die Route bleibt unverändert (ADR-026-Vorgabe:
„bestehende Routen unverändert"); der Viewer bekommt einen **neuen, schmalen**
Lese-Wrapper (`suggestPlacement`, POST …/placement-suggestion) plus einen Knopf
„Kollisions-Ampel prüfen" im Accordion „Platzierung" (dieselbe Stelle wie die
Platzierungs-Overrides — Platzierung ist Platzierung, keine zweite Rubrik nötig).
Bei `feasibility.checked=true && feasible=false` erscheint der Core-Befundtext
verbatim + ein Knopf, der zum vorhandenen „✦ Beam-Zerlegung suchen"-Knopf
scrollt/fokussiert (kein automatischer Start — der Vorschlag ruft den Zerleger
nie selbst, ADR-026 Punkt 2, „Absprung anbieten" ≠ „auslösen"). Alternative 1
verworfen: das PRD nennt einen „geführten Zerlegungs-Flow" explizit Out of
Scope, und eine Wahl-UI über eine Gesamtwand-Kandidatenliste würde genau das
faktisch wiederbeleben, obwohl niemand sie mehr anwendet (Slicing/Sim/Export
laufen über Abschnitts-Platzierungen). Alternative 2 verworfen: sie würde ein
Feld zeigen, das an dieser Stelle nie gesetzt ist (irreführend) — die
Sektionsplatzierung bleibt bewusst reachability-only, bis #232/Folge-Issues
Machbarkeit in die Zerlegungs-Zielfunktion einweben.

**Ampel-Ableitung (`ui/placement-suggestion-state.ts`, DOM-frei, Muster
`beamProgressView`/`checkProgressView`):** eine reine Nachschlagetabelle
`status → {tone, label}` (`clear` → grün „frei", `colliding` → rot
„kollidierend"); fehlendes/unbekanntes Urteil fällt fail-soft auf neutral
„nicht geprüft" — keine Schwellen-Rechnung, keine neue Zwillingsfunktion
(Paritäts-Manifest unberührt). Die Tabelle ist bewusst offen für einen
künftigen dritten Core-Status (PRD-Text nennt „im Sicherheitsband" als
Zielbild, den der Grob-Check heute noch nicht kennt — nur die exakte
Kollisionskontrolle könnte ihn liefern) — ein neuer Tabelleneintrag reicht,
kein Umbau.

**Contract-Manifest:** der Eintrag `POST …/placement-suggestion` bleibt
`"status": "todo"` (keine Golden-Kontraktprüfung), aber der `reason`-Text wird
korrigiert — er behauptete fälschlich weiter "kein projects.ts-Spiegel"; jetzt
gibt es wieder einen (`PlacementSuggestionResult`), nur ohne Golden (Folgeticket).

**Prüfstand:** `npm --prefix viewer test` (12 neue Tests in
`placement-suggestion-state.test.ts`: Ampel je Status/fehlend/unbekannt,
Zeilenableitung inkl. Core-Reihenfolge, Hinweis nur bei „kein machbarer
Kandidat"); volle Viewer-Suite (1064 Tests) + `npm --prefix viewer run build`
grün.


## 2026-07-23 — Prior lenkt die Vorschlagssuche: Raster-Verdichtung + Tool-Ähnlichkeit über die Sicherheitszone (Issue #232, PRD #225, ADR-026 Punkt 3–4)

**Frage:** Wie bindet `placement.suggest` das Prior-Messwissen (#230) so ein, dass
es die Suche **beschleunigt**, ohne je die Korrektheit zu gefährden? Geurteilt
wird weiter vom Grob-Check (#228) + `evaluate` auf der echten Geometrie — der
Prior darf nur die Kandidatenmenge formen.

**Entscheidung:** Der Prior verdichtet zwei Raster-Achsen und schließt **nie**
kategorisch aus. Neue reine Funktion `_densified_raster(lo, hi, focus, window,
coarse_step, fine_step)`: ein **grobes** Grundraster (`PRIOR_COARSE_DISTANCE_STEP_MM`
300 mm bzw. `HEIGHT_STEP_MM` für Höhen) deckt `[lo, hi]` lückenlos ab, ein **feines**
Fenster (`DISTANCE_STEP_MM` 150 mm bzw. `PRIOR_HEIGHT_FINE_STEP_MM` 150 mm) um die
gemessene Best-Stützstelle verdichtet dort, wo die Antwort erwartet wird; Endpunkte
und die Fokus-Stützstelle selbst sind immer enthalten (aufsteigend, dedupt). Die
Abstands-Achse verdichtet um `standoff_focus_mm` (Fenster ±`PRIOR_STANDOFF_WINDOW_MM`
150 mm), das Podesthöhen-Raster um `base_height_focus_mm` (~300 mm, Fenster
±`PRIOR_HEIGHT_WINDOW_MM` 200 mm) — Letzteres **nur** bei höhenverstellbarer
Workstation (`height_range_mm`); der diskrete `base_heights_mm`-Satz bleibt
unangetastet (nie eine Podesthöhe erfinden, die das Gerät nicht kann).

**Default-an, fail-soft:** `suggest` lädt den Prior selbst aus `(robot.name, tool,
wall.length/thickness/height, safety_distance_mm)`. Ein explizit übergebener
`prior=` gewinnt (Test-Injektion / Pipeline-Vorbau) und umgeht das Laden. Jeder
Fehlfall ⇒ neutraler Prior ⇒ die Suche ist **verhaltensgleich zu #228** (getestet:
`prior=None` mit dem hüllmaßlosen Test-Tool == `prior=NEUTRAL_PRIOR`).

**Sicherheitszone statt eigener Konstante (ADR-026 Punkt 4):** die Tool-Toleranz
hängt an der **konfigurierten** GUI-Zone `safety_distance_mm` (Default
`DEFAULT_SAFETY_ZONE_MM` 50 mm = `collision.check.DEFAULT_SAFETY_DISTANCE_MM`), nicht
an einer Prior-eigenen Schwelle. Enge Zone ⇒ strengere Übertragbarkeit (getestet:
dasselbe leicht abweichende Tool passt bei 50 mm, nicht bei 5 mm). Die
Ähnlichkeitsregel selbst lebt bereits in `PriorTable.tool_matches` (#230) — hier
nur konsumiert, nicht dupliziert.

**Alternativen verworfen:** (a) *Prior gatet aussichtslose Standoffs weg* — würde
aus „lenkt" ein „urteilt" machen; ein falscher Prior könnte den echten Sieger
verlieren. Verworfen: das grobe Grundraster hält jeden Bereich erreichbar. (b)
*Eigene Prior-Toleranz-Konstante* — verworfen, ADR-026 bindet die Tool-Toleranz
bewusst an die GUI-Zone (ein Regler, kein zweiter). (c) *Diskrete `base_heights_mm`
zwischen-interpolieren* — verworfen, die Podesthöhen sind physisch vorhanden oder
nicht; nur der stufenlose `height_range_mm`-Fall wird verdichtet.

**Prüfstand:** `python -m ruff check core` clean; 6 neue Tests in `test_placement_prior_search.py`
(Aufruf-Zähler: mit Prior messbar weniger `evaluate`-Aufrufe bei ≥-gutem Sieger;
Fail-soft-Abdeckung ferner Kandidaten; Höhen-Verdichtung deckt vollen Bereich;
Neutral == #228; `angenommen-unmachbar` neutral-breit + nie gegatet; Determinismus)
+ 1 in `test_placement_prior.py` (enge Zone strenger). Volle Core-Suite grün bis auf
den bekannten Memory-Flake `test_broadphase_hull_contains_raw_mesh` (unter
paralleler xdist-Last, isoliert grün — unabhängig von dieser Änderung).

## 2026-07-23 — IK-Konfiguration als prior-geführte Suchachse + Durchreichung bis Simulation (Issue #233, PRD #225, ADR-026 Punkt 5)

**Frage:** Wie wird die IK-Konfiguration (Schulter/Ellbogen/Handgelenk, 8 Zweige)
Suchachse des Optimalvorschlags — prior-geführt —, und wie fährt die Simulation
nachweislich denselben Zweig wie die Bewertung, ohne je eine Konfig hartzukodieren?

**Entscheidung (Suchachse in `placement.suggest`):** Je Kandidat wird der Zweig
mitgesucht. Mit anwendbarem Prior nur die Shortlist der W×T-Zelle plus `auto`
(`config_shortlist`, über `evaluate`s `config_filter`, #129/#200); ohne anwendbaren
Prior direkt die volle Achse (`ALL_IK_CONFIGS`, alle 8). Findet die Shortlist
**keinen** machbaren Kandidaten (nichts erreichbar/kollisionsfrei), eskaliert die
Achse **einmalig** auf alle 8 (`_config_axis(prior) → (achse, can_escalate)`). Der
gewählte Zweig steht als a/b-Block in `PlacementScore.ik_config` (leer = auto) und
fließt über `to_dict` ins `placement.json` und in die API-Nutzlast `scored`.

**Kern-Einsicht (warum `baa` gewinnt):** Im reinen Reichweiten-`evaluate` erreicht
`auto` fast immer 1.0 — `baa` kann dort nie schlagen. Die Studien-Erwartung
(`baa` +80 % machbare Bandhöhe) ist ein **Kollisions**-Effekt: `baa` bleibt frei,
wo `auto` in die Wand taucht. Darum urteilt der Grob-Check in der Achse
**konfig-bewusst** — `default_collision_free` liefert jetzt
`(option, config_filter) -> bool` und reicht `config_filter` an `path_collides`
(#200) durch. Die Konfig-Wahl je Kandidat rankt `_config_key` = (kollisionsfrei
zuerst, dann Reichweite/Marge): so gewinnt der **machbar machende** Zweig, nicht
der mit der höchsten Roh-Reichweite. Auf dem denkmal-nahen Modul (Prior-Zelle
800×250 ⇒ `baa`) schlägt `baa` `auto` — bestätigt am M1013.

**Verträglichkeit mit #228:** Ein **extern** übergebenes `collision_free`
(`option -> bool`, Test-Injektion / Alt-Zustand `lambda o: True`) bleibt
konfig-agnostisch — für alle Zweige gleich. So bleiben die #228-Tests (Vorfilter
lässt kollidierende Lagen fallen, „alle rot" fail-soft, Alt-Zustand ohne Feld)
bit-treu. Der Vorfilter „kollidierende raus" greift jetzt nach der Achse: eine Lage
fällt nur, wenn **kein** Zweig sie rettet (fail-soft: kollidieren alle in jedem
Zweig, bleibt das volle Feld — nie leere Liste).

**Durchreichung bis Simulation (nach außen):** Der Sieger-Zweig zählt zu den
Plan-Eingaben. `suggest_placement` legt ihn als `ik_config` an die
Vorschlags-Aufstellmöglichkeit; `evaluate_placements` bewertet unter genau diesem
`config_filter` (persistierter Score konsistent zur Vorschlags-Bewertung) und
persistiert den Block auf der `placement`; `select_placement` (Übernehmen)
überträgt ihn in `process_params.ik_config` — echo-fest, bumpt Druckplan/Simulation
nur bei echter Änderung. Damit fährt `sectionsim` über die **eine** bestehende Tür
`IkConfigFilter.from_block(effective_section_params(...)["ik_config"])` denselben
Zweig wie die Bewertung. Additive Schema-Felder: `placements[].ik_config`
(project), `score.ik_config` (placement); Viewer-Spiegel `PlacementScoreDto`/
`PlacementOption` um optionales `ik_config` ergänzt. Manuelle/`auto`-Lagen tragen
keinen Block ⇒ byte-gleich zu vorher.

**Alternativen verworfen:** (a) *Konfig auf Reichweite statt Kollision ranken* —
verworfen, `auto` dominiert die Reichweite; der Studien-Effekt wäre unsichtbar. (b)
*Kollision je Zweig auch im extern injizierten Prädikat* — verworfen, bräche die
`option -> bool`-Injektion der #228-Tests; extern bleibt konfig-agnostisch. (c)
*`select_placement` rein lassen, Konfig separat setzen lassen* — verworfen, das
Übernehmen eines Vorschlags **ist** das Adoptieren seines Zweigs (sonst würde die
gefundene Konfig nie gefahren — genau der Zweck des Issues). (d) *Konfig
hartkodieren (`baa`)* — ausdrücklich verboten; der Sieger verschiebt sich mit Wand
und Setup (Test: anderer Prior ⇒ anderer Sieger-Zweig).

**Prüfstand:** `python -m ruff check core` clean; neues `test_placement_ik_axis.py`
(7 Tests: `baa` schlägt `auto` + Sieger nach außen; nur Shortlist+`auto` bewertet
[gezählt]; Eskalation auf alle 8 im konstruierten Fall; kein Prior ⇒ volle Achse;
Sieger verschiebt sich mit Prior [nicht hartkodiert]; Determinismus); neuer
Integrationstest in `test_placement.py` (Vorschlag → Projekt-Artefakt → Übernahme →
Sim-Tür fährt `baa`). Volle Core-Suite + Viewer-Build grün.


---

## 2026-07-24 — Beam-Suche für Modul-Jobs: Zerlegungsart übernehmen, Scorer modul-lokal (Issue #237); Badge benennt Eindringtiefe (Issue #238)

**Frage:** Warum kommt die Beam-Suche (#217/#221) am Denkmal-Modul-Job leer zurück
(`calls_used: 0`, 256/256 Kandidaten `reichweite`-verworfen — einschließlich
`band-1x4`, den die exakte Bewertung gleichzeitig mit `reachable_fraction: 1.0`
ausweist), und wie wird sie für Zerlegungsart „modul" (ADR-022) tragfähig?

**Diagnose (aus den Laufdaten `runs/20260724-081755` + `081813`):** Zwei
unabhängige Ursachen. (1) `checkjobs.start_beam_propose` reicht kein `kind`
durch und `propose_decomposition` defaultete auf `"abschnitt"` — der Beam-Lauf
suchte eine In-situ-Zerlegung der ganzen 3060-mm-Wand, obwohl der Job „modul"
trägt (der Lauf sagt `kind: abschnitt`). (2) `BilligerScorer` bewertet
Höhenreihen auf **absoluter Wandhöhe** (`row_bounds_mm`, oberste Reihe bis
3060 mm — vor der Wand für den M1013 unerreichbar); im Modul-Modus wird jedes
Modul aber am Druckort **ab z = 0** an der festen Workstation-Platzierung
gedruckt. Nebenbefund: das Palette-Badge „kollidiert · Glied 2 · 486 mm" wurde
als **Kollisionshöhe** gelesen („bei ~480 schneiden") — die Zahl ist die
**Eindringtiefe** (FCL-Trennverschiebung; bei einem quer durch die 130-mm-Wand
liegenden Oberarm real > Wanddicke).

**Entscheidung:**

- `propose_decomposition(kind=None)` (neuer Default) übernimmt die im Druckjob
  gespeicherte Zerlegungsart; die HTTP-Route reicht ihre Art weiterhin explizit
  herein. Hintergrund-Trigger (Beam #221, Benchmark #220) stellen die Job-Art
  damit nie mehr stillschweigend um.
- `BilligerScorer(fixe_platzierung=…)` = Modul-Modus: genau ein
  Standplatz-Kandidat (die feste Druckort-Platzierung,
  `fgc.decompose.propose.modul_druckort_platzierung`), jede Reihe modul-lokal
  `(0, Reihenhöhe)` bewertet (Memoisation je Zellgröße — alle Reihen eines
  Band-Kandidaten sind gleich groß). Umsetzvorgänge = 1 (feste Basis, der Kran
  setzt Module), Margen-Proxy = 0 (kein Verschiebe-Spielraum) — der
  #212-Komparator unterscheidet dann über die Fugenfläche, d. h. weniger Teile
  zuerst; genau die gewollte Ordnung.
- `propose` fährt für „modul" dieselbe Kandidaten-Naht wie `_grid_counts`
  (RasterAufgabe + BeamSuche/#165); Modul-Obergrenzen (#90) filtern die
  Kandidatenmenge hart vor (ceil-Herleitung wie der Greedy-Start).
- Hebel-Menü für „modul" **platzierungs-frei** (`option_menu(placement_levers=False)`,
  additives `RasterAufgabe.menu`): die Druckort-Platzierung ist fest (ADR-022),
  ein automatisches Platzierungs-Delta wäre eine stille Lageänderung, die der
  persistierte Plan (nur `cuts`) nicht reproduzieren könnte. Aus demselben Grund
  entfällt die Relaxationsstufe „mehr Standplätze" für „modul".
- `collision_pruef_tuer` erzwingt nicht mehr `"abschnitt"`, sondern reicht die
  Zerlegungsart der Kandidaten-Job-Kopie durch — die Prüf-Tür urteilt am
  Druckort mit derselben Maschinerie wie die Stufe-2-Prüfung (die den Modul-Fall
  nachweislich kann, s. Lauf 081813).
- Viewer-Badge: „kollidiert · Glied N · X mm **tief**" (#238) — nur Anzeigetext,
  der Tooltip sagte es schon richtig.

**Alternativen verworfen:** (a) *Scorer-Reihen für „modul" einfach auf z=0
verschieben, Standplatz-Suche behalten* — verworfen: es gibt keine freie
Standplatz-Wahl am Druckort, die Suche würde Standplätze „finden", die die feste
Aufstellung nicht hat (unehrlicher Vorfilter). (b) *Platzierungs-Deltas auch für
„modul" zulassen (Kran kann das Modul ja versetzen)* — verworfen für v1: der
gewählte Hebel landet nur in der Provenienz, der persistierte Plan trägt nur
`cuts` — ein Delta-abhängiges „geprüft frei" wäre nach dem Speichern nicht
reproduzierbar; später als eigener, persistierter Hebel denkbar. (c)
*Umsetzvorgänge = Teilanzahl (jedes Modul ein Kran-Zug)* — verworfen: doppelt
die Information der Fugenfläche (beide monoton in der Teilanzahl) und macht den
Gewichts-Slider „Umsetzvorgänge" für „modul" bedeutungsschwer; 1 ist die
ehrliche Roboter-Sicht (kein Umsetzen der Basis). (d) *`kind` im Beam-Trigger
hart auf „modul" stellen* — verworfen: der Trigger soll der Job-Wahrheit folgen,
nicht eine andere Art erzwingen (dasselbe Muster wie die Simulation, #112).

**Prüfstand:** `ruff` clean; neue Tests: `test_zerlegung_suche.py` (Scorer-
Modul-Modus: in-situ-K.-o. vs. modul-lokal gedeckt, Determinismus),
`test_beam_suche.py` (propose „modul" end-to-end mit Fake-Prüf-Tür: Suche findet
die nötige Höhenteilung, Menü platzierungs-frei, Obergrenzen-Filter),
`test_beam_actions.py` (Prüf-Tür reicht Zerlegungsart durch;
`propose_decomposition` ohne `kind` übernimmt „modul" aus dem Job, Job-Art bleibt
unverändert), Viewer `printability-state.test.ts` („mm tief"). Volle Core-Suite
+ Viewer-Suite + Build grün. #217-Regressionsanker (Art „abschnitt" byte-gleich)
unverändert.

# RoboPrintIFC (FGC-Planner)

Planungs- und Slicing-System für funktional gradierten Lehm-3D-Druck: IFC-Modell laden → druckbare Wände filtern → slicen → Roboterkinematik simulieren → KRL/DRL exportieren → drucken.

## Schnellstart

Nach `git clone`/`git pull` genügt **ein** Schritt — Doppelklick auf `setup.cmd`
(oder `.\setup.cmd` im Repo-Root):

```powershell
.\setup.cmd
```

Das richtet die Python-`.venv` (inkl. `core[dev,geo]`) und die Viewer-Deps
(`viewer/node_modules`) ein. Danach:

```powershell
.\fgc start          # interaktiver Wizard, oder
.\start_viewer.cmd   # GUI-Direkteinstieg (Projektliste im Browser)
```

**Reproduzierbar auf jedem PC:** `setup.cmd` (bzw. `scripts/bootstrap.ps1`) ist
*idempotent* — es installiert nur, was gegenüber `core/pyproject.toml` bzw.
`viewer/package-lock.json` driftete (Hash-Marker), sonst ist es ein
Sekunden-No-Op. Es sucht sich ein vorhandenes **Python ≥ 3.12** selbst (keine
bestimmte Minor-Version nötig) und braucht **Node.js** für den Viewer.

**Selbstheilend:** `fgc.cmd` und `start_viewer.cmd` rufen das Bootstrap vor dem
Start automatisch auf. Ein frisch gepulltes Repo, dem die venv fehlt oder deren
Abhängigkeiten seit dem letzten Mal wuchsen (z. B. `fastapi`/`uvicorn` neu in den
Kern-Deps), startet dadurch ohne Handgriff sauber — man muss `setup.cmd` nicht
selbst aufrufen, es passiert beim ersten Start.

`fgc.cmd` nutzt automatisch die `.venv` — kein Aktivieren nötig. In einer
aktivierten venv steht `fgc` auch direkt zur Verfügung. Unter Linux/macOS
übernimmt `./setup.sh` (bzw. `scripts/bootstrap.sh`) dieselbe Einrichtung.

## Funktionen

### `fgc start` — interaktiver Einstieg

Führt in fünf Schritten vom IFC-Modell zur gesliceten Wand im Viewer, ohne dass man Pfade oder GlobalIds kennen muss:

1. **Modell wählen** — alle `*.ifc` aus `examples/` und dem aktuellen Verzeichnis werden nummeriert angeboten.
2. **Wände lesen** — das Modell wird analysiert; angezeigt wird, wie viele Wände es gibt, aufgeteilt nach außen/innen (aus `Pset_WallCommon.IsExternal`; fehlt die Angabe: „unbekannt").
3. **Filter + Wand wählen** — nummerierte Tabelle mit Name, Maßen (LxHxD), GlobalId und dem E1-Eignungsurteil (druckbar ja/nein mit Gründen, `~` = provisorische Prüfung). Auswahl per Nummer; auch ungeeignete Wände sind wählbar (mit Warnung).
4. **Slicen** — mit den Default-Parametern aus dem Prozessfenster (siehe `fgc slice` für manuelle Parameter). Ergebnis ist ein Laufordner unter `runs/`.
5. **Viewer öffnen?** — bei „Ja" wird der Vite-Dev-Server bei Bedarf gestartet (inkl. einmaligem `npm install`) und der Browser mit dem Lauf geöffnet. Bei „Nein" wird die URL zum späteren Ansehen ausgegeben.

`Enter` oder `q` bricht jeden Dialog ab.

### `start_viewer.cmd` — GUI-Direkteinstieg per Doppelklick

Startet Core-API (Port 8765) und Viewer (Port 5173), falls sie nicht laufen,
und öffnet den Browser auf der **Projektliste** (ADR-016) — ganz ohne
Konsolen-Dialog. Dort ein Projekt öffnen oder neu aus einer IFC-Datei anlegen;
alle weiteren Schritte (Wand wählen, Roboter, Platzierung, Simulation, Export)
laufen im Reiter-Fluss darüber.

- Doppelklick auf `start_viewer.cmd` im Repo-Root (Windows Explorer), oder:

```powershell
.\.venv\Scripts\python.exe -m fgc.pipeline.viewer_launch
```

Der Start ist **selbstheilend**: Hängt noch ein *veralteter* Core-API-Server
(einer älteren fgc-Version) auf Port 8765, wird er erkannt (fehlende
`/projects`-Routen) und durch die aktuelle API ersetzt — sonst würde der Viewer
stumm gegen die alte API laufen. Der Wizard `fgc start` bleibt der geführte Weg
über die Konsole; der `?run=<laufordner>`-Deeplink lädt einen Laufordner weiterhin
direkt (Dev/Automation-Fallback), ist aber nicht mehr der Doppelklick-Start.

### `fgc walls list` — Wände prüfen (E1)

```powershell
.\fgc walls list examples\Building-Architecture.ifc [--robot doosan_m1013]
```

Listet alle `IfcWall`-Instanzen mit Maßen und Eignungsurteil (zweistufige Prüfung, ADR-013) und schreibt `candidates.json` in einen neuen Laufordner.

| Option | Bedeutung | Default |
|---|---|---|
| `--robot` | Roboterdefinition aus `robots/` | `doosan_m1013` |

Beispielausgabe:

```
GlobalId                 Name                             LxHxD [mm]           eignet sich
------------------------------------------------------------------------------------------------
1AQAupaRP1txwK1AGiN61V   house - outer wall - house righ  1800x3626x200        nein  (~workspace)
```

`~workspace` heißt: der Arbeitsraum-Check schlug provisorisch fehl (Wand größer als der Druckraum des Roboters).

**Zweistufige Prüfung (ADR-013):**

- **Stufe 1** (immer scharf): Planarität, `LoadBearing=false`, Öffnungsanzahl (v1: 0), Höhe/Länge gegen den Arbeitsraum.
- **Stufe 2** (Prozessfenster, provisorisch bis S1): zwei Checks aus den Spike-S4-Regeln.
  - `thickness` — **Wanddicke**. Explizite mm-Grenzen aus der Prozessfenster-Karte haben Vorrang. Fehlen sie, wird die Mindestdicke aus der Strangbreite abgeleitet: Eine Wand verhält sich beim Slicen wie ein Steg, `n` Schalen brauchen `w × (1.5 + 2·(n−1))` (S4-Stegformel, `n` = `default_shells` der Karte). Solange die Strangbreite `w` fehlt (Spike S1 offen), wird der Check provisorisch übersprungen; sobald S1 die Zahl liefert, greift die Grenze automatisch scharf.
  - `footprint` — **Grundriss-Geometrie**: Mindest-Innenwinkel konvexer Ecken (30°) und Mindeststegbreite (Erosionstest). Der Grundriss wird aus dem Wand-Mesh geschnitten (neutrales Schnittmodul `geometry/section.py`, ADR-015): horizontaler Schnitt in Wandmitte → Umriss-Polygon. Der Check läuft jetzt scharf, sobald die Strangbreite in der Prozessfenster-Karte gesetzt ist (Spike S1 offen); bis dahin ist der Steg-Teil provisional. Den Winkel-Check (30°) ist strangbreitenunabhängig und läuft scharf, sobald `min_convex_angle_deg` in der Karte steht. (Mindestinnenradius 0.5×w bleibt bewusst offen — ohne Krümmungsanalyse keine belastbare Zahl.)

**„provisional" (`~`)** heißt: die Prüfung stützt sich auf noch nicht endgültig gemessene Prozesszahlen (P4) oder eine noch nicht angebundene Datenquelle. Bestandene provisorische Checks werden im Bericht als `[provisional: …]` ausgewiesen, ein provisorischer Fehlschlag mit `~` markiert. Sie werden **scharf**, sobald Spike S1 die Strangbreite liefert und die Karte gemessen ist.

### `fgc slice` — Wand slicen

```powershell
.\fgc slice examples\Building-Architecture.ifc --wall 1AQAupaRP1txwK1AGiN61V [Optionen]
```

Sliced genau eine Wand (GlobalId aus `candidates.json` bzw. `fgc walls list`) und schreibt einen Laufordner mit `wallspec.json`, `toolpath.json` und `context.json`. Eine laut E1 ungeeignete Wand wird mit Warnung trotzdem gesliced (explizite Auswahl).

| Option | Bedeutung | Default |
|---|---|---|
| `--wall` | GlobalId der Wand (Pflicht) | — |
| `--robot` | Roboterdefinition aus `robots/` | `doosan_m1013` |
| `--layer-height` | Schichthöhe in mm | Prozessfenster-Karte, sonst 10.0 |
| `--strand-width` | Strangbreite in mm | Prozessfenster-Karte, sonst 30.0 |
| `--shells` | Anzahl Schalen je Kontur | 2 |
| `--no-context` | kein `context.json` (Gebäudekontext) schreiben | Kontext wird geschrieben |

### Lokale Core-API — Re-Slicing aus dem Viewer (ADR-014)

Die Core-API ist ein dünner FastAPI-Wrapper um dieselbe Pipeline wie CLI und Wizard — keine eigene Fachlogik, kein eigener Zustand. Jeder API-Aufruf erzeugt einen regulären Laufordner mit schema-validierten Artefakten inkl. Provenienz (ADR-004 bleibt unangetastet).

**`fgc start`** fährt die API automatisch zusammen mit dem Viewer-Dev-Server hoch. CLI und Wizard funktionieren weiterhin ohne laufende API.

Manuell starten:

```powershell
.venv\Scripts\python -m uvicorn fgc.pipeline.api:app --port 8765
# Dokumentation: http://localhost:8765/docs
```

#### `POST /slice`

Sliced eine Wand und antwortet mit dem Verweis auf den erzeugten Laufordner:

```json
POST http://localhost:8765/slice
{
  "model_path": "C:/…/RoboPrintIFC/examples/Building-Architecture.ifc",
  "global_id": "1AQAupaRP1txwK1AGiN61V",
  "layer_height_mm": 500,
  "strand_width_mm": null,
  "n_shells": null,
  "with_context": true
}
```

`layer_height_mm`, `strand_width_mm`, `n_shells` sind optional — `null` bedeutet: Default aus der Prozessfenster-Karte (dieselbe Regel wie `fgc slice`). Antwort:

```json
{
  "run_dir": "C:/…/runs/20260703-120000_slice_Building-Architecture",
  "n_layers": 7,
  "n_targets": 1248,
  "n_print": 1008
}
```

Der Laufordner enthält `wallspec.json`, `toolpath.json` (und optional `context.json`) — schema-validiert, mit Provenienz, identisch zu einem `fgc slice`-Aufruf mit denselben Parametern.

### Design-Tokens + Theme-Umschalter Hell/Dunkel (UI-Redesign Scheibe 1, Issue #101)

Erste Scheibe des UI-Redesigns nach dem internen Design-Handoff. Sie tauscht **nur Präsentation** aus — gleiche App, neuer Look, kein HTML-Umbau, kein Fachverhalten geändert.

**Design-Tokens:** Die zentrale `viewer/src/style.css` trägt jetzt den vollständigen Token-Satz aus `tokens.css` (verbatim übernommen): Flächen (`--bg`/`--panel`/`--field`/`--chip`), Linien (`--border`/`--border2`/`--chipbd`), Text (`--text`/`--muted`/`--dim`), Akzent (`--accent`/`--accent-fg`), Ampel/Status (`--ok`/`--err`/`--warn`/`--info`), Viewport-Verlauf, Radien (`--r-sm`…`--r-pill`) und Schatten. Dazu die wiederkehrenden Bausteine späterer Scheiben (`.btn-primary`, `.btn-secondary`, `.btn-accent-outline`, `.btn-add`, `.field-box`, `.segmented`, `.switch`, `.dot`, `.info`, `.badge-*`, `.float-panel`).

**Schrift:** **IBM Plex Sans** (400/500/600/700) und **IBM Plex Mono** (400/500) sind **selbst gehostet** (latin-/latin-ext-woff2-Subsets in `viewer/src/fonts/`, per `@font-face` eingebunden, von Vite gebündelt) — der Viewer läuft damit **offline**, ohne den Google-Fonts-CDN des Prototyps. Zahlenwerte, IDs und Dateinamen setzt Plex Mono (`--font-mono`), die UI Plex Sans (`--font-sans`).

**Theme-Umschalter:** Ein Hell/Dunkel-Umschalter setzt `data-theme="light"` auf `<html>` (Dunkel ist der Default, nur `[data-theme="light"]` überschreibt die Palette). Die Wahl wird in `localStorage` (`fgc-theme`) persistiert und **überlebt den Reload** — beim Start wird der gemerkte Wert angewandt. Die reine Umschalt-/Persistenz-Logik liegt DOM- und localStorage-frei in `viewer/src/ui/theme.ts` (vitest-getestet: Default, Normalisierung unbekannter Werte, Rehydrierung, Toggle, abgeleitete Ansicht). Sichtbarkeit/Look laufen ausschließlich über Attribut + CSS-Variablen — **kein display-Toggle** (Issue #46). In dieser Scheibe wird umgeschaltet über `fgcToggleTheme()`/`fgcSetTheme("light"|"dark")`; der **sichtbare ◐-Umschalter im Header** folgt in Scheibe 2 (Issue #102). Der `?run=`-Abspieler-Modus erhält durch diese Scheibe bereits sein Token-Styling und bleibt funktional.

### Header mit Stepper statt Tabbar (UI-Redesign Scheibe 2, Issue #102)

Zweite Scheibe des UI-Redesigns: die frühere **Tabbar** und die darunterliegende **Active-Job-Bar** verschmelzen zu **einem** 50px-**Header** (`#app-header`). Nur DOM/CSS ändern sich — die Tab-Wechsel-Logik in `viewer/src/ui/shell.ts` und das Fachverhalten bleiben.

- **Links:** eine **Logo-Kachel** („FG", Plex Mono) + der **Projektname**. Ein Klick darauf führt **zurück zur Projektliste** (Navigation, kein Zwangspfad). Daneben der **Druckjob-Chip** als Pill (Plex Mono) — er zeigt den aktiven Druckjob (Wand-Name + GlobalId) und ersetzt die frühere Active-Job-Bar (Issue #19).
- **Mitte — Stepper:** die Prozess-Schritte **Projekt › Roboter › Druckplan › Export** mit „›"-Trennern. Der **aktive** Schritt ist ein Chip (hervorgehoben), die inaktiven nur Text. Jeder Schritt trägt einen **7px-Status-Punkt**: **Akzent** = aktiver Schritt, **amber** = veraltet, **grün** = aktuell. Die Punktfarbe kommt **ausschließlich** aus der bestehenden Veraltet-Ableitung (`viewer/src/ui/staleness.ts` / `output_status`) — der Stepper rechnet nichts neu. Ein Klick auf einen Schritt wechselt den Reiter (frei, kein Gating; der Tooltip sagt das, bei Veraltung nennt er zusätzlich den Befund, ADR-017). Die **Bibliothek** ist bewusst **kein** Stepper-Schritt (Stammdaten außerhalb des Prozesses) — sie wird über das ▤-Icon rechts erreicht.
- **Rechts:** ein **Suchfeld** (⌕ „Suchen… ⌘K") — es öffnet die ⌘K-Befehlspalette (Scheibe 9, Issue #109); der **Theme-Toggle ◐**, der den Umschalter aus Scheibe 1 (`ui/theme.ts`) bedient (kein zweiter Mechanismus; Tooltip nennt das Ziel des nächsten Klicks, `aria-pressed` markiert das helle Theme); das **Bibliothek-Icon ▤**.

Die Schrittliste des Steppers ist **erweiterbar** angelegt: die reine, vitest-getestete Ableitung `viewer/src/ui/stepper-state.ts` (`PROCESS_STEPS` + `stepperView`) bildet in dieser Scheibe die bestehenden vier Prozess-Reiter ab (Druckplan = **ein** Schritt) und trägt bereits die 5-Schritt-Aufteilung **Zerlegung/Slicing** der Folge-Issues (#106/#107) ohne Logikänderung. Ein Schritt bindet über ein optionales `output` an eine Veraltet-Stufe; Schritte ohne Output (Projekt/Roboter — Eingabestufen) gelten stets als aktuell.

### Erklärtexte als ⓘ-Tooltips (UI-Redesign Scheibe 3, Issue #103)

Dritte Scheibe des UI-Redesigns: die vielen **Erklär-Absätze** (`.hint`) in den Prozess-Panels (Projekt, Roboter, Druckplan, Export) verschwinden aus der Fläche. Ihr Text wandert **gekürzt** in das native `title=""` eines **ⓘ-Markers** (`<span class="info">ⓘ</span>`, Baustein aus Scheibe 1) neben der jeweiligen Überschrift bzw. dem Label — beim Überfahren erscheint der Hinweis als Tooltip (keine Tooltip-Library). Die Fachaussagen bleiben **unverändert**; nur ihre Darstellung wechselt von Dauer-Text zu abrufbarem Hinweis. **Dynamische** `.hint`-Zeilen (Status, Leerhinweise, API-Warnungen, Live-Mesh-Status, der Workstation-Hinweis der Zerlegungsart, der Advisor-Befund) bleiben als vom Programm befüllte Rückmeldungen erhalten.

**Drei Ausnahmen bleiben sichtbar** — im kompakten Stil der Bausteine aus Scheibe 1:

- **„Plan — vor dem Druck antasten"** (ADR-006) → ein **schwebender Pill-Chip** unten im geteilten 3D-Feld (`#plan-chip`), nur im Reiter **Druckplan** sichtbar. Er erinnert daran, dass die Platzierung die *geplante* Basis-Lage ist und erst über das Antast-Verfahren als Setup verbindlich wird (Details im ⓘ des Chips).
- **Provisorik-/S1-Warnung im Export** → eine **kompakte amber Box** (`.warn-box`) statt eines Absatzes: die DRL-Bewegungsgrenzen stammen aus angenommenen Prozesswerten, das Programm entsteht trotzdem (**kein Gate**), ist aber bis zur S1-Messung als vorläufig zu behandeln.
- **„vorläufig"-Badge im Eignungsbericht** → bleibt unverändert ein **Badge** an der betroffenen Prüfung.

**Issue-Nummern** (#24, #25 …) sind aus allen **sichtbaren** UI-Texten und Tooltips entfernt und leben nur noch in Code-/HTML-Kommentaren. Die Sichtbarkeit des Plan-Chips läuft — wie alle Reiter-abhängigen Elemente — **ausschließlich über das `hidden`-Attribut** (`main.ts onTabChanged`, Lehre aus #56).

### Prozess-Schritt „Zerlegung" — Inspector mit Accordions + schwebende Teile-Palette (UI-Redesign Scheibe 4, Issue #106)

Vierte Scheibe des UI-Redesigns und **erster Teil des Druckplan-Splits**: die frühere Rubrik „Zerlegung & Platzierung" wird ein **eigener Prozess-Schritt „Zerlegung"** — ein neuer Reiter zwischen **Roboter** und **Druckplan**. Der Stepper im Header ist damit fünfstufig: **Projekt → Roboter → Zerlegung → Slicing → Export** (der bisherige Reiter **Druckplan** behält übergangsweise die Slicing-Rubrik + den Simulieren-Bereich, bis Scheibe 5 ihn als „Slicing" herauslöst). Der Reiter Zerlegung ist ein **Inspector (352 px)** aus, von oben:

1. **Kopf** — Titel „Zerlegung", Hinweis **„gilt global ⓘ"** und der volle-Breite-Primärbutton **„✦ Automatisch vorschlagen"**. Dieser Button löst den *Zerlegungsvorschlag* (erreichbare Teile) aus — die **Platzierung sucht der Core dabei je Teil automatisch** (zentral, beste Podesthöhe, optimierter Abstand — #80/#132; über die eine Schreibstelle, ADR-016; die UI rechnet nichts, ADR-007). Der frühere *Gesamtwand-Optimalvorschlag* („vorschlag-1/2/3" + „Wählen") ist mit Issue #134 **entfallen** — er hatte nach der Zerlegung keinen Konsumenten mehr (s. u. „Platzierungsvorschlag entfallen"). Ein **Kopf-Status-Badge** zeigt „ungeprüft" (amber), sobald der Schnittplan geändert wurde, sonst „geprüft ✓" (grün).
2. **Accordion „Art & Aufstellung"** — Zerlegungsart als Segmented (**Abschnitte | Module**); bei „Abschnitte" der Aufstell-Toggle „Roboter auf dem Boden / darf erhöht", bei „Module" die zwei Modulgrenzen-Felder (max. Länge/Höhe). Darunter eine dezente **Workstation-Zeile** (freundlicher Hinweis, wenn „Module" ohne Workstation gewählt ist — Befund, kein Gate).
3. **Accordion „Schnittplan"** — je Schnitt eine Zeile mit rechtsbündiger Zahleneingabe (Plex Mono) + Löschen, zwei gestrichelte Add-Buttons (Höhen-/Längsschnitt) und die Fugen-Versatz-Zeile. Die Schnittebenen lassen sich **weiterhin im 3D-Feld ziehen** — Ziehen und Zahlenfeld bleiben synchron (derselbe Zustand, `ui/cutplan-state.ts`, unverändert).
4. **Accordion „Platzierung — <Teil>"** — die drei Felder Seitlich/Abstand/Höhe des in der Teile-Palette **gewählten** Teils. **Fokus-getrieben** (kein Gilt-für-Umschalter in diesem Reiter): ein gewähltes Teil macht seine Felder bedienbar und beschriftet das Accordion; leer = automatische Platzierung (dezenter Platzhalter „<wert> · Auto"), Eingabe = feldweiser Override (Akzent-Feld + ↺).
5. **Sticky-Footer** — Status links, Primärbutton **„✓ Prüfen lassen"** rechts: er ruft den Core (`from_cuts` + `evaluate`), erst dessen Antwort färbt die Ampeln wieder scharf.

Die **Teile-Palette** schwebt weiterhin über dem 3D-Feld; ihr Kopf trägt jetzt einen **Zähler** („N/M ✓" grün bzw. „ungeprüft" amber). Die **Dirty-Kette** ist durchgängig: jede Schnittplan-Änderung setzt „ungeprüft" — im Kopf-Badge, im Palette-Zähler **und** im Stepper-Punkt Zerlegung (amber) —, erst „Prüfen lassen" hebt sie stufenweise auf (Ableitung aus `ui/staleness.ts`, nichts neu gerechnet). Die Accordions folgen dem `collapsible-state.ts`-Muster (▸/▾) mit **je Gruppe persistiertem** Aufklapp-Zustand; die Fachlogik (`cutplan-state`, `zerlegungsart-state`, `aufstell-state`, `placement-override-state`, `parts-palette-state`, `focus-state`) ist **unverändert wiederverwendet**. Sichtbarkeit läuft ausschließlich über das `hidden`-Attribut; **keine Core-/API-/Schema-Änderungen**. Es gibt in diesem Reiter **keinen Gilt-für-Scope** — der lebt künftig nur im Slicing-Schritt (#107).

### Freigang-Kriterium — Befund „Wand zu dick für einseitigen Druck" (Issue #163)

Im Reiter **Zerlegung** meldet der Core sofort und gratis, wenn eine Wand **zu dick für einseitigen Druck** ist. Das **Freigang-Kriterium** (Stufe 1 des kollisionsgetriebenen Zerlegungs-Constraints, Karte #139 / Entscheidung #141) leitet aus **Wanddicke**, der **freien Länge unter dem Handgelenk** (dem schlanken Nozzle-/Werkzeug-Überstand des Endeffektors) und dem **Handgelenk-/Unterarm-Radius** die **druckbare Tiefe von einer Seite** ab. Ist die Wand dicker als diese Tiefe, erscheint über dem „Prüfen lassen"-Fuß ein amber Banner:

> „Wand zu dick für einseitigen Druck: Dicke 480 mm > druckbare Tiefe 334 mm (um 146 mm). Befund, kein Gate. Hebel: Tiefenteilung (in der Dicke schneiden, Slicing-Option #142); längerer Endeffektor (größere freie Länge unter dem Handgelenk); höhere Aufstellung / beidseitiger Druck."

Das Kriterium stellt **ausschließlich Unmöglichkeit** fest, nie Freiheit: es schweigt, solange die Wand nicht *sicher* zu dick ist (die druckbare Tiefe ist bewusst eine großzügige Obergrenze — ein nachweislich druckbarer Fall löst nie einen Fehlalarm aus). Eine grüne „druckbar"-Zusage gibt es hier nicht — die bescheinigt erst der volle Kollisionsbefund. Es ist ein **Befund, kein Gate** (ADR-013): der Plan wird nie blockiert, das Banner benennt nur die Hebel. Der Befund lebt wand-weit im Zerlegungslauf (`decompose.json`, Feld `freigang`) und überlebt das Neuladen des Projekts; Altläufe ohne das Feld bleiben gültig (die Anzeige bleibt dann still). Fehlt die Endeffektor- oder Kinematik-Geometrie, wird nichts behauptet (kein Befund). In der GUI ist das Banner ein **reiner Abspiel-Effekt** (ADR-007) der Core-Zahlen; die Rechnung selbst ist die reine Domänen-Funktion `fgc.decompose.check_freigang`.

### Zweite Stufe-1-Schranke — Befund „Teil zu hoch für die freie Länge" (Issue #209)

Neben „zu dick" (in der **Tiefe**) fängt der Reiter **Zerlegung** jetzt eine zweite Unmöglich-Klasse gratis ab: ein **Teil, das zu hoch für die freie Länge** unter dem Handgelenk ist. Die Schranke folgt dem **Winkelmuster von Stamatopoulos** (Gl. 9, `docs/recherche/2026-07-10-adaption-chunking-literatur.md`): aus der **Verbindbarkeit** (45°) und der **Endeffektor-Geometrie** (freie Länge `L`, Handgelenk-Radius `R`) ergibt sich die maximal druckbare Neigung `φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr)`, daraus eine **großzügige druckbare Höhe** `H_max`. Ist ein Teil **strikt höher** als `H_max`, ist es rot **„vermutlich zu hoch"** — mit dem **Überschuss doppelt ausgewiesen: in Millimetern und in Grad** (z. B. „vermutlich zu hoch · 210 mm · 6°"):

> „Vermutlich zu hoch für die freie Länge unter dem Handgelenk (zweite Stufe-1-Schranke, Gl. 9): der Überschuss beträgt 210 mm (6° über der druckbaren Neigung). Das Urteil ist PLATZIERUNGSBLIND … Keine geprüfte Gewissheit; die teure Kollisions-Prüfung entfiel bewusst (vermutlich, ungeprüft). Befund, kein Gate."

Wie „zu dick" fällt der Befund in die **sichere Fehlerrichtung** (S6): `H_max` ist bewusst großzügig (für den realen M1013 ≈ 1250 mm) und fängt nur Teile **weit jenseits** der Werkzeug-Reichweite — ein Fehlalarm auf normal hohe Teile ist ausgeschlossen. Weil die Teilhöhe physikalisch **nicht hart** durch die Werkzeuggeometrie begrenzt ist (der Roboter setzt je Schicht um), ist der Befund eine **platzierungsblinde Vermutung** (`presumed`, nie ein grünes/geprüftes Urteil) und ein **Ratschlag „in der Höhe teilen"** (Hebel: Höhenteilung, längerer Endeffektor, flachere Aufstellung). Er läuft **gratis in Stufe 1** — der **Short-Circuit ohne Simulation** (im interaktiven Loop erscheint „zu hoch" sofort); die teure **Prüf-Tür (Stufe 2) überstimmt** die Vermutung, sobald sie ausdrücklich angestoßen wird. Fehlt die Endeffektor-/Kinematik-Geometrie, schweigt die Schranke (fail-soft). Das Urteil lebt je Teil im Zerlegungslauf (`decompose.json`, `sections[].printability.verdict = "too_tall"` mit `excess_mm`/`excess_deg`, additiv); Altläufe bleiben byte-gleich gültig. Reine Domänen-Funktion `fgc.decompose.check_teilhoehe`, verdrahtet in `fgc.decompose.pruefung.assess_plan` (Stufe-1-Pfad); die GUI zeigt nur (ADR-007).

### Zielfunktion der Zerlegungs-Suche — Einstellungs-Fenster „⚖ Zielfunktion …" (Reiter Zerlegung, Issue #212, PRD #183 Stufe 3)

Wonach soll die automatische Zerlegungs-Suche (Beam, #217) Kandidaten vergleichen? Der Reiter **Zerlegung** bekommt dafür ein **Einstellungs-Fenster** (Knopf „⚖ Zielfunktion …" unter „Automatisch vorschlagen"): **ein Gewichts-Satz, zwei Lesarten** (Grill 2026-07-14). **Aufwiegen AUS (Default):** kein Aufwiegen — die **Gewichts-Reihenfolge ist die Rangfolge** (lexikographisch), Default **Umsetzvorgänge > Fugenfläche > kinematische Marge > c_v** (Einmessen ist der teuerste manuelle Schritt; kein c_v-Komfort kompensiert ein zusätzliches Umsetzen). Erst wenn ein Kriterium **gleichauf** liegt, entscheidet das nächste — dafür werden stetige Kriterien **quantisiert** (Schrittweiten sind benannte Verfahrens-Parameter in `fgc.decompose.objective`, PROVISORISCH bis zur Eichung nach AP 2). **Aufwiegen AN:** dieselben Zahlen wirken als **gewichtete Summe**. In beiden Lesarten ist die **Erreichbarkeit ein hartes K.-o.** davor — ein unerreichbares Teil macht den Kandidaten wertlos, kein Gewicht wiegt das auf. Ein **Gleichstand zweier Gewichte im Aus-Modus** wäre eine mehrdeutige Rangfolge — das Fenster **sperrt das Speichern** und benennt die gleichauf liegenden Kriterien (der Core weist ihn zusätzlich zurück); „↺ Standard" stellt den gepinnten Default wieder her. Gespeichert wird als **Druckjob-Parameter** (sparse: der Default lässt Altprojekte byte-gleich; Route `PUT …/objective`, einzige Schreibstelle `fgc.project`, ADR-016); eine **tatsächliche** Änderung veraltet den Zerlegungsplan (echo-fest, #199 — ein unter der alten Zielfunktion gesuchter Plan ist ehrlich „veraltet"). Jeder Zerlegungslauf **stempelt die komplette wirksame Config** (Lesart + Gewichte + Quantisierungs-Schrittweiten) in seine **Provenienz** (`decompose.json → provenance.objective`, ADR-004) — auch den Default, reproduzierbar für den Paper-Benchmark. Der Komparator selbst (`fgc.decompose.objective`: `candidate_key`/`compare_candidates`) arbeitet über **injizierten Kriterienwerten** — die echten Lieferanten (Reichweitenkarte #210, Raycast-Scorer) verdrahtet die Beam-Suche (#216/#217); der Viewer zeigt und persistiert nur (ADR-007).

### Reichweitenkarte als Vorfilter der Platzierung (Issue #214, PRD #183 AP 2)

Die binäre 4D-Reichweitenkarte (#210) beantwortet „ist diese Flanschpose von dieser Basis erreichbar?" in Mikrosekunden und dient nun als **Vorfilter** vor den drei Platzierungs-Aufrufern — **ein Parameter (die Karte), drei Aufrufer** (dasselbe `config_filter`-Muster wie #200/#201). **Ehrlichkeitsregel (ADR-007/#164): die Karte filtert, urteilt nie** — „geprüft frei" entsteht ausschließlich in der Prüf-Tür, die Ampel-Semantik bleibt unberührt (US 11).

- **Optimalvorschlag** (`fgc.placement.suggest.suggest`, Reiter Druckplan): die laut Karte aussichtslosen Basis-Lagen (Karten-Schätzung 0) werden **gar nicht erst simuliert** — nur die Überlebenden gehen durch die teure `evaluate`-Bewertung (US 5). Der Vorfilter ist **lenient** (nichts Erreichbares wird weggefiltert — die Karte hat am Raster keine falschen Negative) und **fail-soft** (würde er alle streichen, greift das volle Raster) — die beste Lage und das Ranking bleiben das IK-Urteil.
- **Standplatz je Höhenreihe** (`fgc.placement.reachmap.standplatz_fuer_reihe`, US 6): das **punktweise Minimum über die Bahnposen** einer Reihe liefert in < 1 s die Basispositionen, die garantiert **alle** Posen der Reihe erreichen (kein Umsetzen mitten in der Reihe). Basen, die nur einen Teil der Reihe erreichen, fallen heraus (`ReachabilityMap.min_over_poses`, Vahrenkamp Gl. 3 / RM4D IV-D).
- **Bewertungsmodus** (`fgc.placement.evaluate.evaluate` + Aktion `evaluate_placements`, US 7): mit Karte trägt der `PlacementScore` — und damit jede Option im `placement.json`-Artefakt und der API-Antwort — ein zusätzliches Feld `reach_estimate`: den geschätzten erreichbaren Anteil, **klar als Schätzung gekennzeichnet** (`is_estimate: true`, `source: reachability_map`). Das IK-Urteil `reachable_fraction` (die Ampel-Basis) bleibt unverändert daneben stehen.
- **Kollisions-Advisor** (`fgc.collision.advisor.advise`, US 8): Platzierungs-Gegenmaßnahmen, deren neue Basis die Wand laut Karte nicht mehr erreicht, werden **vor** der teuren Neu-Simulation verworfen — eine kürzere Antwort ohne verschwendete Simulationen.

**Ohne Karte byte-gleich** (US 12): fehlt das Karten-Artefakt (`robots/reachability/<robot>/`) oder ist seine Provenienz veraltet, laden die Aktionen fail-soft `None` — `evaluate`/`suggest`/`advise` verhalten sich dann bit-identisch zu Altläufen (kein `reach_estimate`, ungefiltertes Raster, vollständige Kandidatenliste).

### Platzierung optimiert Machbarkeit — Kollisions-Grob-Check default-an (Issue #228, ADR-026)

Der **Optimalvorschlag** der Platzierung (`fgc.placement.suggest.suggest`, Reiter Druckplan) optimiert jetzt **Machbarkeit statt Erreichbarkeit**: der billige Kollisions-Grob-Check (#131, `fgc.collision.coarse.path_collides`) läuft **standardmäßig** als **zweiter Vorfilter vor** der teuren `evaluate`-Schleife (direkt hinter dem Reichweiten-Vorfilter #214). Kollidierende Basis-Lagen werden **gar nicht erst bewertet** — bei einem tief kollidierenden Raster spart das viele teure Bewertungen. Damit gewinnen kollisionsfreie Lagen vor kollidierenden, **ohne Zutun des Aufrufers** (bewusster neuer Default, ADR-026 Punkt 6 — kein Legacy-Schalter).

- **Befund, kein Gate.** Das Kollisionsurteil ist **vorderster Sortierschlüssel** *und* ein explizites Feld im Score (`PlacementScore.collision` → `{"free": bool, "status": "clear"|"colliding", "source": "coarse"}`), sichtbar in jeder Option des `placement.json`-Artefakts und der API-Antwort. Der Vorschlag ruft den Zerleger **nie selbst** (lose Kopplung, ADR-026 Punkt 2).
- **Fail-soft „alle rot" (Muster #214).** Streicht der Grob-Check *alle* Kandidaten, wird das volle Raster bewertet — die Vorschlagsliste bleibt **nie leer**, kein Fehler. Der Gesamt-Befund **„kein machbarer Kandidat"** wandert als `feasibility` (`checked`/`feasible`/`n_feasible`) bis in die Antwort der Vorschlags-Route (`POST …/placement-suggestion`); der Core rechnet, der Viewer zeigt (Ampel/Hinweis sind Folge-Issue).
- **Alt-Zustand explizit konstruierbar** (Benchmark-Vergleichbarkeit, US 15): `suggest(..., collision_free=lambda o: True)` behandelt alles als frei ⇒ kein Vorfilter, reine Erreichbarkeits-Optimierung, #98-Sortierung bit-identisch, kein Kollisionsfeld. Ein benannter Produktions-Schalter zurück existiert nicht.
- **Ohne Kollisionsgeometrie byte-gleich.** Fehlt die Roboter-Breitphasen-Geometrie (#125, Altprojekt) oder der Geo-Stack, läuft die Suche fail-soft **ungeprüft** — kein `collision`-Feld, `feasibility.checked=false` („unbekannt", nicht „unmachbar"), Kandidatenliste wie zuvor.

**Demo-Beleg (denkmal Modul 1, 785×822 mm, Dicke 510 mm, M1013):** der Alt-Default (Erreichbarkeit-only) wählt die nahe, tief kollidierende Lage (~230–300 mm Abstand); der neue Default wählt eine kollisionsfreie Lage (750 mm) und meldet `feasible=true`.

### Viewer: Kollisions-Ampel je Platzierungsvorschlag + Absprung auf den Zerlegungs-Trigger (Issue #231, ADR-026 Punkt 2)

Der Machbarkeits-Befund aus #228 wird im Viewer sichtbar — im Reiter **Zerlegung**, Accordion **„Platzierung"**, unter den Override-Feldern des fokussierten Teils: der Knopf **„Kollisions-Ampel prüfen"** fragt den bestehenden Optimalvorschlag rein lesend ab (`POST …/placement-suggestion`, Issue #23/#80) und zeigt je Kandidat die fertig gerechnete Einstufung — der Viewer rechnet **keine eigene Schwelle** (keine neue Zwillingsfunktion, Paritäts-Manifest unberührt), er bildet nur `score.collision.status` auf Ampelfarbe/-text ab (`clear` → grün „frei", `colliding` → rot „kollidierend", fehlend/unbekannt → neutral „nicht geprüft").

- **Bei „kein machbarer Kandidat"** (`feasibility.checked=true`, `feasible=false`) erscheint der Core-Befundtext verbatim samt einem Knopf **„Zum Zerlegungs-Trigger ↓"**, der zum vorhandenen **Beam-Zerlegungs-Trigger** (#221/#222, Knopf „✦ Beam-Zerlegung suchen" im selben Reiter) scrollt/fokussiert — er startet ihn **nicht** automatisch. Bei mindestens einem machbaren Kandidaten oder ungeprüftem Befund (`checked=false`) erscheint **kein** Hinweis.
- **Lose Kopplung.** Der Vorschlag ruft den Zerleger nie selbst; der Absprung ist reine DOM-Verdrahtung im Panel (ADR-026 Punkt 2).
- **Reine Vorschau.** Der Knopf ändert nichts an Plan/Fachzustand — keine Auswahl, keine Persistenz; bestehende Platzierungs-Routen/-Abläufe (Override-Felder, Automatischer Zerlegungsvorschlag, Beam-Suche) bleiben unverändert.
- **DOM-freie Ableitung** (`ui/placement-suggestion-state.ts`, vitest) — Muster `beamProgressView`/`checkProgressView`: `placementAmpel`/`placementSuggestionRows`/`placementFeasibilityHint` bilden die Core-Antwort rein textuell ab.

### Platzierungs-Prior aus Sweep-Messwissen — Tabelle + Lademodul (Issue #230, ADR-026 Punkt 3)

Das teuer erhobene **W×T-Prädikat-Gitter** (`experiments/collision_standoff_sweep/data_grid/`) wird produktiv nutzbar — als versioniertes Datenartefakt plus rein rechnendes Lademodul. **Noch ohne** Einbindung in die Suche (das ist Folge-Issue #232): der Prior **lenkt** eine spätere Suche (Abstands-/Basishöhen-Verdichtung, IK-Konfig-Shortlist, Machbarkeits-Erwartung), **urteilt aber nie** — geurteilt wird immer auf der echten Geometrie (Grob-Check + `evaluate`).

- **Generator** `fgc.placement.prior_build` — regeneriert die Tabelle **ohne Codeänderung** aus den Gitterdaten:

  ```
  PYTHONPATH=core/src python -m fgc.placement.prior_build \
      --grid-meta experiments/collision_standoff_sweep/data_grid/meta_wt.json \
      --robot doosan_m1013 --tool 30gut
  ```

  Alle Argumente haben Defaults, die das eingecheckte Artefakt reproduzieren. Je (Breite, Dicke) wird H_max + Best-Setup (Abstand, Basishöhe, IK-Konfig) abgelegt, geschlüsselt auf **Roboter + Tool**, mit ADR-004-Provenienz (Herkunfts-Commit, Gitter-Parameter, Referenz-Tool = Name/TCP-Versatz/Hüllmaß). Byte-stabil (`sort_keys`, unabhängig von der Zeilenreihenfolge des Gitters — Golden-Roundtrip).
- **Ehrliche Annahme statt erfundener Messwert.** Die 3 im Gitter abgebrochenen Zellen (800×550, 1100×400, 1100×550) gehen mit Status `angenommen-unmachbar` ein (kein H_max, kein Best-Setup); Ersatz durch Messung ist Folgearbeit (#226). Eingecheckt: `priors/placement_prior.doosan_m1013.30gut.json` (12 Zellen, 9 gemessen).
- **Lademodul** `fgc.placement.prior` — schmale Tür `placement_prior(roboter, tool, modulmaße, sicherheitszone) → PlacementPrior`. **Konservative Interpolation:** für eine Modulmaße zwischen den Stützstellen die **nächste schlechtere** Zelle (größeres W **und** T ⇒ kleineres H_max, **kein Fit** — die Effekte haben Knicke). **Tool-Toleranz = konfigurierte Sicherheitszone** (ADR-026 Punkt 4): der Prior gilt für ein fremdes Tool, wenn ‖Δ TCP-Versatz‖ **und** Δ Hüllmaß ≤ `safety_distance_mm`; fehlt das Hüllmaß (Altbestand vor #229) ⇒ „unbekannt" ⇒ nur das namensgleiche Referenz-Tool passt.
- **Jeder Fehlfall ⇒ neutraler Prior** (Suche wie ohne Messwissen): kein Artefakt, fremder Roboter, unbekanntes/unähnliches Tool, Modulmaße außerhalb des Gitters, provenienz-ungültiges Artefakt. Eine `angenommen-unmachbar`-Zelle liefert dagegen einen **neutral-breiten** Prior **mit** Unmachbarkeits-Erwartung.

### Prior lenkt die Vorschlagssuche — Raster-Verdichtung um die Best-Stützstellen (Issue #232, ADR-026 Punkt 3–4)

Der Prior aus #230 ist jetzt in `fgc.placement.suggest` **eingebunden** — er **lenkt** die Suche, **urteilt aber nie**: geurteilt wird weiter vom Kollisions-Grob-Check (#228) + `evaluate` auf der echten Geometrie. Ein falscher Prior kostet nur Suchzeit, nie Korrektheit.

- **Default-an, fail-soft.** `suggest` lädt den Prior selbst aus `(robot, tool, wall.length/thickness/height, safety_distance_mm)` (GUI-Sicherheitszone, Default 50 mm — **keine eigene Prior-Konstante**, dieselbe Zone wie die Tool-Ähnlichkeit). Jeder Fehlfall ⇒ neutraler Prior ⇒ Suche **verhaltensgleich zu #228**. Ein explizit übergebener `prior=…` (Test-Injektion, Pipeline-Vorbau) gewinnt und umgeht das Laden.
- **Abstands-Raster verdichten.** Mit anwendbarem Prior wird die Abstands-Achse im Fenster ±150 mm um die gemessene Best-Standoff-Stützstelle **fein** (`DISTANCE_STEP_MM` 150 mm) gerastert, außerhalb **grob** (`PRIOR_COARSE_DISTANCE_STEP_MM` 300 mm) — dadurch **messbar weniger `evaluate`-Aufrufe** bei gleichem oder besserem Sieger.
- **Podesthöhen-Raster verdichten** um die belegte Besthöhe (~300 mm) im Fenster ±200 mm (`PRIOR_HEIGHT_FINE_STEP_MM` 150 mm) — **nur** bei einer höhenverstellbaren Workstation (`height_range_mm`); der diskrete `base_heights_mm`-Satz wird nie erfunden.
- **Verdichtung schließt nie aus (fail-soft).** Das grobe Grundraster deckt den ganzen Reichweiten-/Höhenbereich lückenlos ab — auch weit außerhalb des Prior-Fensters bleiben Kandidaten. Der Prior konzentriert die Suche, verwirft aber keinen Kandidaten kategorisch.
- **`angenommen-unmachbar` ⇒ neutral-breite Suche.** Eine angenommen-unmachbare Zelle trägt keine Fokus-Stützstelle ⇒ das Raster bleibt neutral-breit (identisch zum neutralen Prior); die Unmachbarkeits-Erwartung ist **reine Info, nie ein Gate** — die Vorschlagsliste bleibt nie leer.
- **Determinismus erhalten.** Feste, dedupte, aufsteigende Raster ⇒ gleiche Eingaben + Prior → gleiche Ausgabe.

### IK-Konfiguration als prior-geführte Suchachse + Durchreichung bis Simulation (Issue #233, ADR-026 Punkt 5)

Der **Optimalvorschlag** (`fgc.placement.suggest.suggest`) sucht jetzt auch den **IK-Konfigurationszweig** (Schulter/Ellbogen/Handgelenk, 8 Zweige) mit — **prior-geführt**. So fährt die Simulation nachweislich **dieselbe** Konfiguration wie die Bewertung; die Konfig ist **nie hartkodiert** (der Sieger verschiebt sich mit Wand und Setup — Studienbeleg: Zweig `baa` bleibt frei, wo `auto` in die Wand taucht).

- **Prior-Shortlist zuerst, sonst volle Achse.** Mit anwendbarem Prior werden je Kandidat **nur** die Konfig(s) der passenden W×T-Zelle **plus `auto`** bewertet (`config_shortlist`, über den vorhandenen `config_filter` von `evaluate`, #129/#200). Ohne anwendbaren Prior läuft direkt die **volle Achse** (alle 8 Zweige).
- **Eskalation, wenn die Shortlist nichts findet.** Findet die Shortlist **keinen** machbaren Kandidaten (nichts erreichbar/kollisionsfrei), eskaliert die Suche **einmalig** auf alle 8 Zweige.
- **Gewählt wird der machbar-machende Zweig, nicht der reichweitenstärkste.** Der Grob-Check (#131) läuft in der Achse **konfig-bewusst** (`path_collides(..., config_filter=…)`); je Kandidat rankt „kollisionsfrei zuerst, dann Reichweite/Marge". Damit gewinnt `baa` dort, wo `auto` kollidiert — deckt sich mit dem Sweep-Befund (`baa` +80 % machbare Bandhöhe).
- **Nach außen sichtbar.** Der Sieger-Zweig steht als a/b-Block in `PlacementScore.ik_config` (leer = auto) und wandert ins `placement.json` **und** in die API-Nutzlast `scored`. Die Vorschlags-Aufstellmöglichkeit persistiert ihn im Projekt-Artefakt (`placements[].ik_config`).
- **Übernehmen fährt die Konfig.** `select_placement` überträgt den Zweig der gewählten Aufstellmöglichkeit in `process_params.ik_config` — die Simulation liest ihn über die **eine** bestehende Tür `IkConfigFilter.from_block`. Manuelle/`auto`-Lagen tragen keinen Block ⇒ byte-gleich zu vorher.
- **Verträglichkeit erhalten.** Ein **extern** übergebenes `collision_free` (Alt-Zustand `lambda o: True`, Test-Injektion) bleibt konfig-agnostisch; die #228-Vorfilter-Semantik (kollidierende Lagen fallen, „alle rot" fail-soft) und der Determinismus bleiben bit-treu.

### Druckbarkeit je Teil — Ampel statt „16/16 ✓" bei kollidierenden Teilen (Issue #164)

Im Reiter **Zerlegung** trägt jetzt **jedes Teil** ein sichtbares **Druckbarkeits-Urteil** — direkt aus dem Zerlegungslauf, **ohne vorherige Simulation**. Damit fällt das lügende „16/16 ✓ / erreichbar 100 %": ein Teil, das der Arm zwar *erreicht*, beim Drucken aber *rammt*, ist nicht mehr grün. Der Core verheiratet dazu die beiden Kriterien der Serie (Karte #139 / Entscheidung #141, Scheibe 3) zu **einem** Urteil je Teil:

- **Freigang zu dick** (Stufe 1, gratis, #163) ⇒ jedes Teil ist rot **„zu dick"** mit dem Dicken-Überschuss als Ursache; die teure Kollisions-Prüfung entfällt (für die Denkmal-Wand: alle 16 Module rot in ~1–2 s, ohne Simulation).
- sonst **repräsentative Prüf-Tür** (Stufe 2, #162): weil die verdünnte Kollisions-Prüfung ~10 s je Teil kostet, prüft der Core je **Höhenreihe nur die ungünstigste Zelle** und die übrigen Zellen der Reihe **erben** das Urteil. Ein kollidierendes Teil zeigt **Verursacher-Glied + Eindringtiefe** als Ursache (z. B. „kollidiert · Glied 2 · 289 mm tief" — das Wort „tief" benennt die Größe seit Issue #238: die Zahl ist die **Eindringtiefe** des Glieds in den Druckstand, keine Kollisions- oder Schnitthöhe; sie wurde ohne den Zusatz als Schnitthöhen-Empfehlung fehlgedeutet).

**Ehrlich angezeigt (der Kern):** **Grün** bekommt **nur**, was die Prüf-Tür wirklich frei gesehen hat — ein stummer Freigang-Befund wird nie zum grünen Häkchen. Ein **geerbtes Reihen-Urteil** ist als **„vermutlich"** gekennzeichnet (blasser, hohler Ampelpunkt, kursives Badge) und sieht nicht wie ein geprüftes aus. Der Palette-Zähler zählt entsprechend nur **geprüft-frei** als ✓ (bei kollidierenden Teilen z. B. „16/16 nicht druckbar" statt „16/16 ✓"). Es ist ein **Befund, kein Gate** (ADR-013): der Plan wird nie blockiert. Das Urteil lebt je Teil im Zerlegungslauf (`decompose.json`, Feld `sections[].printability`) und überlebt das Neuladen; Altläufe ohne das Feld bleiben gültig (dann steht wie bisher nur die Erreichbarkeit). Reine Domänen-Funktionen `fgc.decompose.representative_by_row` / `combine_printability`; die GUI zeigt nur (ADR-007). *(Noch keine Schnittänderung — das automatische Verkleinern kollidierender Teile folgt in Scheibe 4.)*

### Kollisionsgetriebene Verfeinerung — Teile automatisch kleiner schneiden, bis sie frei sind (Issue #165, Constraint-Serie Scheibe 4)

Der **eigentliche Constraint** der Serie (Karte #139 / Entscheidung #141): der automatische Zerlegungsvorschlag schneidet Teile jetzt nicht mehr nur nach **Reichweite**, sondern verkleinert sie so lange, bis jede Zelle **von der besten automatischen Option aus kollisionsfrei** ist (Prüf-Tür #162). Eingeschaltet wird das im Reiter **Zerlegung** über „✦ Automatisch vorschlagen" mit aktiver Verfeinerung (Core: `propose_decomposition(..., refine_collisions=True)`); ohne die Option bleibt der Vorschlag der reine Reichweiten-Vorschlag (byte-gleich).

**Hebel-Reihenfolge (strikt nach der HITL-Entscheidung #141):** Pro Zelle probiert der Core zuerst — automatisch erlaubt — **(1) IK-Konfiguration** (prozessneutral: ein anderer Lösungszweig Schulter/Ellbogen/Handgelenk verlegt den Arm im Raum) und **Platzierung** (Abstand/Aufstellhöhe/seitlich). Meldet die Prüf-Tür eine Zelle danach immer noch kollidierend, wird kleiner geschnitten: **(2) Bandhöhe senken**, dann **(3) Breite teilen** — **entlang der verursachenden Achse aus dem Befund** (Verursacher-Glied + Position am schlimmsten Sample, keine Heuristik: liegt die Kollision hoch, wird die Höhe geteilt; liegt sie seitlich, die Breite; Gleichstand ⇒ Bandhöhe zuerst). **Kipp wird nie automatisch variiert** (prozessrelevant — bleibt ausschließlich manueller Advisor-Hebel), **Tiefenteilung nie automatisch angewandt** (nur Vorschlag, manuell #142).

**Kosten & Determinismus.** Jede Prüf-Tür-Prüfung ist eine verdünnte Abschnitts-Simulation (~Sekunden). Der Core prüft je Höhenreihe nur den **Repräsentanten** (die ungünstigste Zelle) und deckelt die Gesamtkosten über ein **Aufruf-Kontingent** (`DEFAULT_CALL_BUDGET`, #178/#215) — eine **feste Anzahl Prüf-Tür-Aufrufe je Lauf**, **kein Zeitbudget**: gleicher Input ⇒ gleiche Aufruffolge ⇒ **gleicher Schnitt**, maschinenunabhängig (eine langsamere Maschine rechnet nur länger, der Plan ist byte-gleich). Der `MAX_DIVISIONS`-Deckel bleibt; ist Kontingent oder Deckel erschöpft, endet die Verfeinerung **best effort** (die Ampel färbt ehrlich rot — Befund, kein Gate). Die Prüf-Tür läuft als Hintergrundlauf mit Fortschritt (Prüf-UX-Muster #145) und nutzt denselben `SectionSimContext` (#189) wie die echte Simulation — **keine Parallel-Metrik**.

**Nachvollziehbar.** Der je Reihe gewählte **Platzierungs-Hebel landet in den Teil-Platzierungen** (`sections[].placement`), die volle Provenienz (Strategie, Aufruf-Kontingent, verbrauchte Aufrufe, gewählter Hebel + Kollisions-Status je Reihe) im additiven Block **`refinement`** des Zerlegungslaufs (`decompose.json`); Altläufe/Reichweiten-Vorschläge ohne das Feld bleiben byte-gleich gültig. Die Verfeinerung hängt an der **einen** Strategie-Naht aus #216 (`fgc.decompose.strategie.KollisionsGetriebeneVerfeinerung` an `ZerlegungsStrategie.waehle_raster`) — **kein zweiter Verfeinerungs-Loop** neben dem Achsen-Greedy; das produktive Prüf-Tür-Orakel baut `fgc.pipeline.sectionsim.collision_pruef_tuer`. **Befund, kein Gate** (ADR-013): der Plan wird nie blockiert.

### Beam-Suche — Zerlegung als Suche: billig bewerten, nur Überlebende exakt prüfen (Issue #217, PRD #183 Stufe 3)

Statt die Zerlegung parametrisch zu **raten** und den Kollisionsbefund erst hinterher zu bekommen, ist die Zerlegung jetzt eine **Suche** — die zweite Strategie an derselben #216-Naht (`fgc.decompose.beam.BeamSuche` an `ZerlegungsStrategie.waehle_raster`, kein Sonderpfad). Das Literatur-Muster: **billige Bewertung vorn, teures Urteil hinten** (Wu 2019, Han 2025).

- **Alle** Band-Raster-Kandidaten werden vom billigen **Scorer** gratis bewertet (Reichweite/Umsetzvorgänge aus der Karte #210/#214, Fugenfläche/c_v/Fragment-Inseln aus der Masken-Matrix), der **Zielfunktions-Komparator** (#212, lexikographisch: Umsetzvorgänge > Fugenfläche > kinematische Marge > c_v) ordnet sie.
- Der Beam behält die besten **k** — und **k wird aus dem Aufruf-Kontingent abgeleitet** (`beam_breite(call_budget)`, kein eigener Parameter): der Beam hält so viele Kandidaten, wie das Kontingent im günstigsten Fall exakt prüfen könnte.
- **Nur die Beam-Überlebenden** durchlaufen die **Prüf-Tür** (das exakte Kollisionsurteil je Höhenreihe, von der besten automatischen Option aus). Jeder Aufruf zählt gegen das **harte Aufruf-Kontingent** (`DEFAULT_CALL_BUDGET`, #215, je Druckjob übersteuerbar, kein Zeitbudget) — der erste vollständig kollisionsfreie Kandidat gewinnt. Eine kollidierende Zerlegung wird so **gar nicht erst vorgeschlagen**; die Suche findet automatisch den besseren Schnitt (die Ampel bleibt unverändert Sache von `evaluate`).

**Relaxationsleiter (bei leerem Ergebnis, Stufe für Stufe).** Findet die Suche keinen erreichbaren, kollisionsfreien Schnitt, werden die Constraints **schrittweise** gelockert — **jede gezündete Stufe namentlich** im `refinement`-Block: **(1) mehr Teile** (feinere Band-Raster bis zum harten Deckel), **(2) mehr Standplätze** (mit erweitertem Podesthöhen-Satz neu bewerten), **(3) Tiefenteilungs-Vorschlag** (#166-Muster, **manuell** anzuwenden, nie automatisch). **Nie relaxiert:** Sicherheitsabstand, das Erreichbarkeits-K.-o. (ein unerreichbarer Kandidat wird nie „geprüft frei" — nur best effort ein ehrlich rot bewerteter Vorschlag), die Ehrlichkeitsregel („geprüft frei" nur aus der Prüf-Tür) und die Kipp-/Tiefenteilungs-Automatik (#141/#165 — das Menü trägt kein Kipp/Lead, die Suche teilt nie selbst die Tiefe).

**Determinismus & Nachvollzug.** Gleicher Input + gleiches Kontingent ⇒ **bit-gleicher Schnitt** (Aufrufe zählen, keine Zeit; stabile Tie-Breaks). Der `refinement`-Block trägt den **Metriken-Katalog je Lauf** (US 20: Teilanzahl, c_v, Fugenfläche, erreichbarer Anteil, geprüft-frei-Anteil, Anzahl Standplätze, Rechenzeit), die **Verworfen-Gründe je Kandidat** (US 10: `reichweite` / `fragment` / `kollision`) und den **Relaxationsausweis**. Der Viewer zeigt sie im Reiter **Zerlegung** (`ui/refinement-state.ts`: `verworfenRows` / `relaxAusweis` / `beamSummary` — reine Ableitung, ADR-007). Die Suche ist **hintergrundlauffähig** mit Fortschritt + Abbruch (`on_progress`/`should_cancel`, Muster #145/#175). **End-to-end im App-Lauf**: `actions.propose_decomposition(..., beam_search=True)` baut den `BilligerScorer` aus der geladenen **Reichweitenkarte** (#210, `_reach_map_for_robot`, fail-soft → ohne Karte byte-gleicher Greedy), fährt die produktive Prüf-Tür (`collision_pruef_tuer`, #165/#189) und persistiert **nur den Sieger** über `_persist_decompose_run`/`DecomposeBundle` (#198) — Metriken/Verworfen/Relaxation landen im `refinement`-Block von `decompose.json`. Als Hintergrundlauf über `checkjobs.start_beam_propose` (Fortschritt in Prüf-Tür-**Aufrufen**, Abbruch — dasselbe Registry-Muster wie die Stufe-2-Prüfung #175). Für die Strategie-Einheit/Tests direkt über `propose(..., scorer=…, objective=…, pruef_tuer=…)`; ohne `beam_search`/`scorer` bleibt alles byte-gleich (die #165-Verfeinerung bzw. der Reichweiten-Greedy). **Befund, kein Gate** (ADR-013). Der sichtbare Viewer-Trigger/HTTP-Endpoint für diesen Beam-Hintergrundlauf ist mit **Issue #221** nachgezogen (siehe nächster Abschnitt) — bis dahin war nur die Actions-Naht + der Background-Job fertig und getestet.

### Beam-Zerlegung auslösbar — Knopf, Fortschritt, Abbrechen im Reiter Zerlegung (Issue #221, Folge #217)

Die Beam-Suche (#217) hatte alles außer dem **Auslöser**: die Actions-Naht und der Hintergrund-Job (`checkjobs.start_beam_propose`) waren fertig, aber kein Knopf sprach sie an. Issue #221 zieht ihn nach — analog zur entkoppelten Stufe-2-Prüf-Tür (#175).

- **Bedienung.** Im Reiter **Zerlegung** (unter dem Prüf-Tür-Block) sitzt der Knopf **„✦ Beam-Zerlegung suchen"**. Ein Klick startet die kollisionsgetriebene Beam-Suche als **Hintergrundlauf** — der Editor friert nicht ein. Ein **Fortschrittsbalken** zeigt die verbrauchten **Prüf-Tür-Aufrufe** (`n_done/n_total`, das Aufruf-Kontingent #215 — Fortschritt in *Aufrufen*, nicht Sekunden), daneben **„Abbrechen"**. Ein Abbruch persistiert nichts (der Zerlegungsstand bleibt unverändert); der laufende Knopf ist gesperrt, solange die Suche läuft.
- **Ergebnis.** Bei Erfolg übernimmt der Viewer den **Sieger-Schnittplan** (frische Abschnitte + Ampeln, wie nach einem Zerlegungsvorschlag) ohne Nachladen und zeigt den **Such-Ausweis** aus dem `refinement`-Block: die **Beam-Kopfzeile** („Beam-Suche · k/n Prüfungen"), den **Relaxationsausweis** (welche Constraints bei leerem Ergebnis gelockert wurden, US 22) und die **Verworfen-Gründe je Kandidat** (Reichweite / Fragment / Kollision, US 10). Kein stilles Grün: abgebrochen/fehlgeschlagen tragen einen ehrlichen Abschlusstext (ADR-013).
- **HTTP-Route (analog `decomposition-check`).** `POST /projects/{slug}/decomposition-beam` stößt an und kehrt sofort mit `state="running"` + `beam_id` zurück; `GET …/decomposition-beam/{beam_id}` poll't Fortschritt/Ergebnis; `POST …/{beam_id}/cancel` bricht ab. Die Trias spiegelt `checkjobs.start_beam_propose`/`get_beam_propose`/`cancel_beam_propose`; die Antwort trägt bei `done` zusätzlich den `refinement`-Block verbatim aus dem Sieger-Lauf (`decompose.json`), damit der Viewer den Ausweis direkt speist.
- **Core rechnet, Viewer zeigt (ADR-007).** Der Viewer-Trigger ist reine Verdrahtung: der API-Client (`viewer/src/api/projects.ts`: `startBeamPropose`/`getBeamPropose`/`cancelBeamPropose`), die reine Fortschritts-/Ausweis-Ableitung (`ui/refinement-state.ts`: `beamProgressView` + die bestehenden `beamSummary`/`relaxAusweis`/`verworfenRows`) und die DOM-dünne Panel-Anbindung (`ui/druckplan.ts`). Neue Kinematik/Logik entsteht im Viewer nicht. Die Start-Route ist im Kontrakt-Golden-Harness (#202) registriert (`decomposition-beam.contract.json` ↔ `BeamProposeStatus`).

### Beam-Suche für Modul-Jobs — Zerlegungsart wird übernommen, Scorer bewertet am Druckort (Issue #237, Folge #217/#221)

Der Beam-Knopf war für Druckjobs der Zerlegungsart **„modul"** (an der Workstation vorproduziert, ADR-022) strukturell blind — der Denkmal-Befund: alle 256 Kandidaten mit Grund `reichweite` verworfen, 0 Prüf-Tür-Aufrufe, leeres Ergebnis, obwohl der aktive Plan exakt bewertet 100 % erreichbar war. Zwei Ursachen, beide behoben:

- **Zerlegungsart wird übernommen.** `propose_decomposition` erzwang per Default „abschnitt"; der Hintergrund-Trigger (`checkjobs.start_beam_propose`) reichte keine Art durch — die Beam-Suche suchte also immer eine **In-situ-Zerlegung der ganzen Wand**. Jetzt gilt `kind=None` ⇒ **die im Druckjob gespeicherte Art** (die HTTP-Route reicht ihre Art weiterhin explizit herein); Hintergrundläufe stellen die Job-Art nie mehr stillschweigend um.
- **Modul-lokaler Scorer.** Der billige Vorfilter bewertete Höhenreihen auf **absoluter Wandhöhe** (oberste Reihe z. B. bei 3060 mm — vor der Wand unerreichbar). Im Modul-Modus wird jedes Modul aber am Druckort **ab z = 0** an der **festen** Workstation-Platzierung gedruckt. `BilligerScorer(fixe_platzierung=…)` bewertet Reihen jetzt **modul-lokal** an genau dieser Platzierung (ein Standplatz-Kandidat, keine Suche; Umsetzvorgänge = 1, Margen-Proxy 0 — der Komparator unterscheidet dann über die Fugenfläche: weniger Teile zuerst). Die **Prüf-Tür urteilt am Druckort** (`collision_pruef_tuer` reicht die Zerlegungsart der Job-Kopie durch statt „abschnitt" zu erzwingen — dieselbe Maschinerie, die das Modul-Urteil der Stufe-2-Prüfung schon rechnet).
- **Hebel-Menü platzierungs-frei.** Für „modul" probiert die Suche je Reihe nur **Basis + IK-Konfiguration** (`option_menu(placement_levers=False)`): die Druckort-Platzierung ist fest (ADR-022), ein automatisches Platzierungs-Delta wäre eine stille Lageänderung. Die Relaxationsstufe „mehr Standplätze" entfällt aus demselben Grund; „mehr Teile" und der Tiefenteilungs-Vorschlag bleiben.
- **Modul-Obergrenzen (#90)** filtern die Kandidatenmenge hart vor (dieselbe ceil-Herleitung wie der Greedy-Startwert): die Suche schlägt nie ein Raster vor, dessen Zellen `max_length_mm`/`max_height_mm` verletzen.

Damit findet „✦ Beam-Zerlegung suchen" für Modul-Jobs automatisch die Schnitthöhe, deren Module die Prüf-Tür am Druckort **geprüft frei** sieht — genau der Fall „Modul kollidiert bei den obersten Lagen ⇒ niedriger schneiden", der vorher von Hand geraten werden musste. Art „abschnitt" bleibt byte-gleich (alle #217-Regressionsanker unverändert).

### `fgc campaign` — Datenkampagne: Kandidatenraum systematisch sampeln + exakt etikettieren (Issue #218, PRD #183 Stufe 4)

Das Surrogat (#219, „vermutlich frei / vermutlich kollidiert") braucht einen **Kaltstart-Trainingsdatensatz**. `fgc campaign` ist das **reproduzierbare Batch-Skript**, das den **Kandidatenraum systematisch** sampelt, jeden Kandidaten mit der **exakten Prüf-Tür** etikettiert und den **Datensatz als eigenständiges, veröffentlichbares Paper-Artefakt mit Provenienz** ablegt.

```bash
fgc campaign --out datasets/surrogate_dataset.json   # Default-Plan, CPU-exakt
fgc campaign --dry-run                                # nur die Umfangsansage
fgc campaign --lengths 800,1600 --heights 1200,2000 --thicknesses 200 --cap 3 --limit 50 --yes
```

- **Systematischer, deterministischer Sampling-Plan** (`fgc.decompose.kampagne.SamplingPlan`): ein kartesisches Produkt über sortierte Achsen-Gitter (Wandlänge × -höhe × -dicke) liefert die Wände; je Wand zählt der stabile **Band-Raster-Generator** (#216) die Kandidaten-Zerlegungen auf, Sampling-Einheit ist der **Höhenreihen-Repräsentant** (die ungünstigste Zelle, mit den meisten früheren Teilen als Druckstand). **Gleicher Plan ⇒ bit-gleiche Kandidatenmenge** (Achsen sortiert, Band-Raster grob vor fein — US 25).
- **Merkmale = #211-Schema.** Je Kandidat trägt der Datensatz genau die `PruefSample`-Felder (Abschnittsmaße, Wandposition, Hindernislast + Platzierung/Podesthöhe) unter derselben `FEATURE_SCHEMA_VERSION` wie der Laufbetrieb — deckungsgleich mit der Datensammel-Pflicht (#211), damit #219 beide Quellen mischen kann.
- **Label-Quelle je Etikett** (Policy v1, Grill 2026-07-14): jedes Etikett trägt seine Herkunft — `cpu-exakt` | `gpu+cpu-grenzband` | `gpu+stichproben-audit`. Etikettiert wird **bevorzugt GPU-vorsortiert** über #205-G2 (`select_oracle`, sofern `gpu_available()`) — der **CPU-only-Fallback (Glied-SDF, #215) ist der gültige Weg und wartet nicht auf #205** (`cpu_exact_oracle`, etikettiert selbst-enthaltend über synthetische Quaderwände mit derselben Prüf-Tür-Kette wie der produktive Weg). Der Datensatz weist die **Herkunftsverteilung** aus (`label_source_distribution`); `gpu+stichproben-audit` ist **nicht trainingstauglich** und je Sample so markiert (`training_safe: false`).
- **Umfangsansage vor Start** (Muster #175): der Lauf nennt zuerst **N Kandidaten + geschätzte Dauer** (`campaign_scope`, ~9,77 s je Etikett aus der AP-1-Messung #215) und fragt nach Bestätigung (`--yes` überspringt, `--dry-run` zeigt nur die Ansage). **Abbruch** per Ctrl-C jederzeit — der **Teilstand bleibt verwertbar** (der Datensatz wird geschrieben und als `partial` markiert); `--limit N` etikettiert nur die ersten N (Mini-Stichprobe für Selbstprüfläufe).
- **Datensatz-Artefakt mit Provenienz** (ADR-004): `provenance` (reproduzierbares Quell-Kommando, Zeitstempel, Git-Commit), der Sampling-Plan, die Merkmals-Version, die Herkunftsverteilung, der Trainings-Ausweis und die etikettierten Datensätze. Reine, geometriefreie Kampagnen-Logik in `fgc.decompose.kampagne` (Sampling-Plan, Aufzählung, Verschnürung, Umfangsansage — tief testbar mit injiziertem Orakel); das produktive CPU-Orakel + die Orchestrierung in `fgc.pipeline.kampagne`. **Befund, kein Gate** (ADR-013): ein an einem Kandidaten gescheitertes Etikett wird übersprungen, kippt nie den Nachtlauf.

### Surrogat-Vorsortierer — Beam schneller, Ergebnis identisch: deterministisches GBM über den Kandidaten-Merkmalen (Issue #219, PRD #183 Stufe 4)

Das **Surrogat** ist ein kleines, **deterministisches Gradient-Boosting-Modell** (kein Deep Learning) über den #211-Kandidaten-Merkmalen, das die Beam-Suche (#217) **schneller macht, ohne ihr Ergebnis zu verändern**. Es **sortiert nur vor** — es verwirft nie, urteilt nie und taucht in **keiner Ampel und keinem Befund** auf (Ehrlichkeitsregel ADR-007/#164). `fgc.decompose.surrogat`.

- **Vorsortierer, kein Entscheider.** Der Beam bewertet alle Kandidaten billig (Scorer #216) und ordnet sie per Zielfunktion (#212). Ist ein Surrogat aktiv (`BeamSuche(surrogat=…)`), **reordnet es nur die Pruef-Reihenfolge** der Beam-Überlebenden — die vermutlich kollisionsfreien zuerst durch die (teure) Prüf-Tür (Risiko je Kandidat = größte Reihen-Kollisionswahrscheinlichkeit). Der **Sieger bleibt der zielfunktions-beste kollisionsfreie Kandidat** (`beam._pruefe` wählt ihn unabhängig von der Pruef-Reihenfolge).
- **Invarianz-Orakel (US 25).** Mit und ohne aktiven Vorsortierer liefert die Suche bei **gleichem Aufruf-Kontingent denselben besten Kandidaten und dasselbe Urteil** — nur die Reihenfolge der Prüf-Tür-Aufrufe (und die Zeit) ändern sich. Die einzige Spur des Surrogats ist der **Modellstand** im `refinement.surrogate_model`-Feld der Lauf-Provenienz (Datensatz-Stand, Seed, Merkmalsliste/-Version), falls aktiv (ADR-004); **ohne Surrogat bleibt alles byte-gleich** (`None`, US 12).
- **Deterministisches Training (US 25).** Fester Seed ⇒ **bit-gleiches Modell**: das Boosting hat keine Zufallsquelle (kein Subsampling; exakte, gierige Splits mit stabilen Tie-Breaks). `scikit-learn` ist bewusst **keine** Abhängigkeit — die numpy-GBM ist klein und ohne Build-Kette.
- **Policy-Filter (Grill 2026-07-14).** Trainiert wird **ausschließlich aus v1-policy-konformen Labels**: `cpu-exakt` + `gpu+cpu-grenzband` (letztere nur mit bestandenem #205-G1-Gate); `gpu+stichproben-audit` und urteilslose Zeilen (`collides` kein Wahrheitswert) werden **verweigert** (`policy_filter`). Bleibt keine Trainingszeile, schlägt das Training fehl (nie ein stiller Fehlkomparator). Der Trainings-Ausweis nennt benutzt/verworfen transparent.
- **Merkmale = Kandidaten-Kern.** Das Surrogat nutzt die `feature_core`-Felder (Abschnittsmaße, Wandposition, Wandmaße, `n_earlier_parts`) — **ohne** die Platzierungs-/Podest-Merkmale, die beim Ordnen der Kandidatenliste noch nicht vorliegen. Als Vorsortierer kostet die Teilmenge nur Sortier-Güte (Benchmark #220), nie Korrektheit; `feature_version` (#211) versioniert die Bedeutung.
- **Versioniertes Artefakt mit Provenienz (US 26).** Das Modell ist ein Artefakt (`kind`, `schema_version`, `feature_version`, `features`, `seed`, Hyperparameter, Provenienz, Datensatz-Stand, Trainings-Ausweis, serialisierte Bäume). **Laden validiert die Provenienz** (`SurrogatModell.from_artifact`/`load_surrogat`): eine fremde Merkmals-Version/-Liste schlägt fehl. Ein **Altlauf ohne Modell lädt unverändert** — `load_surrogat` liefert bei fehlender Datei `None`, der Beam läuft byte-gleich ohne Vorsortierer.

```bash
fgc campaign --out datasets/surrogate_dataset.json         # 1) Datensatz (#218)
fgc surrogate-train --dataset datasets/surrogate_dataset.json --out models/surrogate.json --seed 0   # 2) Modell (#219)
```

**Treffsicherheit ist bewusst kein Test-Assert**, sondern **Gegenstand des Benchmarks #220** (PRD Testing Decisions): das Surrogat verändert das Beam-Ergebnis nicht, sein Nutzen (weniger Prüf-Tür-Aufrufe / kürzere Zeit) wird dort als dritter Arm gemessen. **Befund, kein Gate** (ADR-013).

### `fgc benchmark` — Benchmark-Harness fürs Vergleichspaper: Greedy vs. Beam vs. Beam+Surrogat (Issue #220, PRD #183)

Der **Benchmark-Harness** stellt die drei Zerlegungs-**Arme** auf **demselben eingefrorenen Stand** gegeneinander — an derselben #216-Strategie-Naht, also **byte-vergleichbar** über die ADR-004-Provenienz, ausschließlich CPU. Er liefert die Zahlen fürs Vergleichspaper (Ziel *Automation in Construction*).

```bash
fgc benchmark --project <slug> --job default --out benchmarks/protocol.json          # zweiarmig (kein Modell)
fgc benchmark --project <slug> --model models/surrogate.json --out benchmarks/protocol.json   # dreiarmig, falls Gate grün
```

- **Drei Arme, eine Tür.** **Greedy** (kollisionsgetriebene Verfeinerung #165), **Beam** (#217) und **Beam+Surrogat** (#219) laufen alle über `propose_decomposition` (`refine_collisions` / `beam_search` / `beam_search + surrogat`) mit **demselben Aufruf-Kontingent** (#215) auf demselben Druckjob — nur der Strategie-Schalter unterscheidet. So ist der Vergleich fair und byte-vergleichbar (US 27).
- **Sollbruch-Gate (mechanisch, Grill 2026-07-14).** Der **dritte Arm läuft nur**, wenn beim Start ein Surrogat-Modell existiert, das (1) **v1-policy-konform** trainiert ist (nur `cpu-exakt` + `gpu+cpu-grenzband`, kein `gpu+stichproben-audit`-Rest), (2) das **Invarianz-Orakel grün** hat (mechanischer Beam-Lauf mit/ohne Vorsortierer → identischer Sieger + Urteil, US 25) und (3) als **Artefakt mit Provenienz** vorliegt (Merkmals-Version/-Liste, `SurrogatModell.from_artifact`). Fehlt eine Bedingung, läuft der Benchmark **zweiarmig — ohne Warten, ohne Wiederholung**. Der **vierte Arm Beam+GPU-Vorsortierer** läuft nach demselben Zug-Prinzip (nur falls #205-G2 samt Toleranzschema fertig — heute `gpu_available()` ⇒ `False`, also entfällt er). **Jeder Gate-Entscheid (zwei-/drei-/vierarmig) steht mit Grund je Arm im Protokoll — nie stillschweigend.**
- **Auswertung ausschließlich aus persistierten Laufartefakten (US 20/21/27).** Die Kennzahlen kommen **nur** aus den `decompose.json`-Läufen der Arme (`evaluate_run`) — **kein Nachrechnen** von Geometrie: Teilanzahl, c_v, Fugenfläche (aus dem Beam-Metriken-Katalog; der Greedy trägt sie nicht ⇒ ehrlich `null`), erreichbarer Anteil (aus den Sektions-Ampeln), geprüft-frei-Anteil (Beam: Metriken; Greedy: aus den `rows`), Standplätze (aus den Teil-Platzierungen), Verworfen-Gründe (`reichweite` = Karten-Vorfilter #214). Die **Rechenzeit** ist diagnostisch getrennt (`diagnostik`, maschinenabhängig) — **nicht** Teil des Byte-Vergleichs. **Wiederholung ⇒ byte-gleiche Kennzahlen** (CPU-Arme, US 25).
- **Protokoll mit Provenienz (ADR-004).** Ein Artefakt (`kind: benchmark-protocol`) mit dem Gate-Entscheid, dem eingefrorenen Stand (Fälle, Roboter, Kontingent), der **Provenienz je Arm** (Strategie, Modellstand, Kontingent, Zielfunktions-Config) und der byte-vergleichbaren Auswertung — jede Paper-Behauptung ist ohne Nachrechnen belegbar. Reine, geometriefreie Harness-Logik in `fgc.decompose.benchmark` (Gate, Auswertung, Protokoll — tief testbar mit injiziertem Arm-Läufer); die produktive Verdrahtung (Arme über `propose_decomposition`, Modell-Gate, Ablage) in `fgc.pipeline.benchmark`. **Der echte Lauf ist teuer** (CPU-exakte Prüf-Tür je Arm) — Selbstprüfläufe fahren nur Mini-Stichproben.

### Prüf-Fehler sichtbar — Fehlerklasse, Log, „ungeprüft"-Zustand und ehrlicher Zähler-Nenner (Issue #170)

Bis hierher konnte ein **Prüf-Fehler** das entlarvte „16/16 ✓"-Bild still wiederherstellen: die Kollisions-Prüf-Tür verschluckte **jede** Ausnahme wortlos, das Teil bekam „kein Urteil", und der Viewer fiel auf die alte Erreichbarkeits-Ampel zurück — ein **totes Prüfsystem war unsichtbar**. Issue #170 macht den Fehler durchgängig sichtbar:

- **Log + Fehlerklasse im Core.** Die zwei schluckenden Stellen der Prüf-Tür (`fgc.pipeline.actions._section_clearance_check` / `_clearance_verdict_for_section`) **loggen** jede Ausnahme (`logging.warning`, mit Traceback) und unterscheiden im Ergebnis **`no_geometry`** (Prüf-Tür *unzuständig* — Altprojekt/Roboter ohne Kollisions-Geometrie) von **`error`** (Prüfung *fehlgeschlagen* — Regression/fehlende Bibliothek). Beide führen zum Teil-Zustand **„ungeprüft"**, **nie** zu „frei" (ein geschluckter Absturz wird nie grün). Der Grund steht als `printability.reason` im `decompose.json` (Schema erweitert, additiv).
- **Dritter Zustand „ungeprüft" je Teil.** Der Viewer zeigt „ungeprüft" sichtbar und **unterscheidbar** von grün/rot/„vermutlich": amber Ampel mit **offenem Ring (◍)** und ein amber, gestrichelt umrandetes **„ungeprüft"-Badge**, dessen Tooltip den Grund nennt (unzuständig vs. fehlgeschlagen).
- **Ehrlicher Kopfzähler.** Der Nenner umfasst **alle** Teile; Ungeprüfte werden **ausgewiesen** statt aus dem Nenner gerechnet — z. B. **„4 druckbar · 12 ungeprüft"**. Ein Lauf mit fehlgeschlagener Prüfung sieht **nie** wie „alles geprüft" aus. Das beruhigende „N/N druckbar ✓" steht nur, wenn wirklich jedes Teil geprüft-frei ist.
- **Altläufe ehrlich.** Beim Laden eines **Altlaufs** (vor #164, ohne Urteil) erscheint je Teil **„ungeprüft"** — **nicht** mehr die alte Erreichbarkeits-Anzeige (die bleibt als eigene „erreichbar N %"-Zeile sichtbar). Alles **Befund, kein Gate** (ADR-013). Reine Zustandsfunktionen `ui/printability-state.ts` (`printabilityView`/`printabilityCounter`) und `ui/parts-palette-state.ts`; die GUI leitet nur ab (ADR-007).

### Ampel-Konjunktion — grün nur bei Erreichbarkeit UND Druckbarkeit (Issue #180)

Bis hierher **ersetzte** das neue Druckbarkeits-Urteil die Erreichbarkeits-Ampel — mit einer Regression in die verbotene Richtung: ein Teil, das die Prüf-Tür *kollisionsfrei* sah, aber nur **teilweise erreichbar** ist (vorher rot), konnte grün werden; ein **50 %-erreichbares** Teil erschien so „druckbar". Issue #180 verheiratet die beiden Kanäle zu einer **Konjunktion** statt einer Ersetzung:

- **Grün nur bei beidem.** Ein Teil wird **nur** dann „printable" (grün), wenn die Prüf-Tür es **frei** sah **und** es **voll erreichbar** ist. **Unerreichbarkeit erzeugt nie „printable"** — ein kollisionsfreies, aber nur teilweise erreichbares Teil ist **rot**, nicht grün.
- **Beide Kanäle bleiben ablesbar (Befund statt Gate).** Der Prüf-Tür-Kanal bleibt ehrlich (`verdict` kann „printable" bleiben — die Prüfung *sah* es frei); der Erreichbarkeits-Kanal steht als eigener Wert daneben. Das Teil trägt dann sichtbar **„kollisionsfrei, aber teilweise unerreichbar (N %)"**, und die bestehende „erreichbar N %"-Zeile der Palette bleibt. Nichts wird verdeckt.
- **Kopfzähler folgt.** Ein unerreichbares Teil zählt **nicht** als geprüftes ✓ — das beruhigende „N/N druckbar ✓" verlangt jetzt auch volle Erreichbarkeit.

Das Urteil transportiert **beide Kanäle** je Teil (`decompose.json`, `sections[].printability`: der Erreichbarkeits-Wert `reachable`/`reachable_fraction` wird nur bei *nicht* voller Erreichbarkeit geschrieben — voll erreichbare Teile bleiben byte-gleich, wie `reason` bei #170). Die Konjunktion liegt sowohl im Core (`fgc.decompose.combine_printability`, `PartPrintability.printable` = frei **und** erreichbar) als auch in der reinen Viewer-Zustandsfunktion `ui/printability-state.ts` (`printabilityView`), damit sie an beiden Nähten festgenagelt ist. Altläufe ohne den Kanal gelten als erreichbar (Konjunktion ist dann ein No-op). **Befund, kein Gate** (ADR-013); die GUI leitet nur ab (ADR-007).

### Reihen-Vererbung kollisionsehrlich — welche Zelle je Höhenreihe geprüft wird (Issue #174)

Weil die Prüf-Tür ~10 s je Teil kostet, prüft der Core je **Höhenreihe** nur **eine** Zelle und lässt die übrigen ihr Urteil als **„vermutlich"** erben (#164). **Welche** Zelle das ist, wählt der Core jetzt **kollisionsehrlich** (statt nach der collision-blinden kinematischen Marge):

- **Höchste Hindernislast, zuletzt gedruckt.** Repräsentant ist die Zelle mit der **größten Hindernislast in Druckreihenfolge** — die zuletzt gedruckte Zelle der Reihe, die durch das **meiste frisch gedruckte Nachbarmaterial** fährt (der eigentliche Kollisionstreiber beim Abschnitts-Druck). Vorher gewann systematisch die *erste*, hindernisärmste Zelle — eine kollidierende Reihe konnte so fälschlich „vermutlich frei" erben.
- **Kein Urteil von einer unerreichbaren Pose.** Eine Zelle **ohne erreichbare Pose** wird nie Repräsentant (ihre Prüfung liefe über eine eingefrorene, bedeutungslose Bahn). Ist **keine** Zelle der Reihe erreichbar, erbt die Reihe **kein „frei"**, sondern **„ungeprüft"** mit dem Grund *„keine erreichbare Zelle in der Reihe"*.
- **Zellen mit eigener Platzierung erben nicht.** Trägt eine Zelle einen eigenen **Platzierungs-Override**, wurde ihr Urteil an einer *anderen* Platzierung gemessen — sie wird **selbst geprüft** (oder als „ungeprüft" ausgewiesen) und erbt nie das Reihen-Urteil, noch vertritt sie ihre Nachbarn.

Das ist **Befund, kein Gate** (ADR-013) und rein Core-seitig (`fgc.decompose.representative_by_row`); der Viewer zeigt nur (ADR-007). Der Slow-Test `test_vererbung_orakel.py` validiert die Vererbung an einer nicht-zu-dicken Wand gegen den **vollen** Kollisionsbefund je Zelle: der Repräsentant deckt die Reihe nachweislich in der sicheren Richtung, und kein geerbtes Urteil ist grün, wo der volle Befund kollidiert.

### „zu dick" ehrlich — vermutlich statt Gewissheit, provisorischer TCP nie „sicher unmöglich" (Issue #177)

Das Freigang-Urteil **„zu dick"** (Stufe 1, #163) war bisher eine geprüfte **Gewissheit**: alle Teile rot-sicher, und die falsifizierende Kollisions-Prüf-Tür entfiel. Das Kriterium ist aber **höhenblind** — es kennt weder Wandhöhe noch Aufstellung und kann für eine **niedrige, dicke Wand** (Sockel, bei der das Handgelenk frei über der Krone hängt) irren. Die eigentliche **Wandhöhen-Wache ist Issue #167** (noch offen); bis dahin wird „zu dick" ehrlich als Vermutung transportiert (Befunde B7, B9):

- **Vermutlich zu dick, nicht geprüft.** Ein `too_thick`-Teil erscheint in Palette und Ampel als **„vermutlich zu dick"** (blasser, hohler Ampelpunkt + kursives „vermutlich"-Badge — dieselbe ehrliche Kennzeichnung wie ein geerbtes Reihen-Urteil), **nie** als geprüfte Gewissheit. Das Überspringen der teuren Kollisions-Prüfung bleibt (der Sinn von #163: der Denkmal-Fall in ~1–2 s ohne Simulation), ist jetzt aber ausdrücklich als **„vermutlich, ungeprüft"** ausgewiesen — Befund statt Gate, nicht ersatzloses Übergehen.
- **Provisorischer TCP erzeugt kein „sicher unmöglich".** Ist der Werkzeug-TCP noch nicht am Gerät vermessen (`tcp_provisional`, #136 — der Modul-Export misstraut solchen Werten längst), könnte die daraus gerechnete druckbare Tiefe zu klein sein und eine real druckbare Wand fälschlich sperren. Das Urteil trägt dann ein sichtbares **Vorläufigkeits-Feld** (Zusatz **„· TCP vorläufig"** im Label, Erklärung im Tooltip) — der Befund unterbleibt nicht, wird aber nie als Gewissheit dargestellt.

Beides lebt additiv im Zerlegungslauf (`decompose.json`: `freigang.tcp_provisional` wand-weit, `sections[].printability.tcp_provisional` je Teil — nur bei provisorischem TCP geschrieben, Altläufe/bestätigter TCP byte-gleich). Rein Core-seitig (`fgc.decompose.check_freigang` / `combine_printability`); der Viewer zeigt nur (`ui/printability-state.ts`, ADR-007). **Befund, kein Gate** (ADR-013).

### Prüf-Vorbehalte durchreichen + Kollisionsbadge mit Veraltet-Ableitung (Issue #182)

Die **Prüf-Tür** der Zerlegung (`check_part_clearance`, #162) prüft **verdünnt**: nur jedes `travel_stride`-te Travel-Sample geht durch, die Druck-Samples voll (ADR-024, S5-Hebel) — intern gerade damit gerechtfertigt, dass Travel „nicht lückenlos geprüft" markiert ist. Diese Ehrlichkeits-Metadaten (`travel_thinned`, `n_checked`/`n_samples`, `tool_provisional` — der Endeffektor lief als provisorische Hülle) gingen beim **Verheiraten** zum Druckbarkeits-Urteil (`combine_printability`) bislang verloren (Befunde B15/B37/B38): ein Tür-„frei" sah stärker aus, als es war. Jetzt werden sie **additiv** auf `PartPrintability` übernommen (`travel_thinned`/`n_checked`/`n_samples`/`tool_provisional`, nur bei einem echten Prüf-Tür-Urteil `printable`/`collides`, nur geschrieben, was zutrifft — Altläufe byte-gleich) und im Tooltip des Druckbarkeits-Urteils ausgewiesen (`ui/printability-state.ts`: `printabilityCaveats`), konsistent zur Wortwahl des Kollisionsbefunds im Player (`collisionCaveats`, Issue #156).

Zwei weitere Ehrlichkeits-Lücken schließt dasselbe Issue in der Teile-Palette:

- **Palette-Kollisionsbadge veraltet wie die übrigen Badges.** Es entwertete bislang nur hart auf „kein Badge" bei `dirty` (frisch editierter, noch nicht neu bewerteter Schnittplan, #172/B20 — bleibt). Jetzt trägt es zusätzlich `stale` aus **derselben** Ableitung wie Druckplan-/Simulation-/Export-Badge (`sectionStageStatus`/`isStale`, `staleness.ts`, Stufe „simulation"): eine Parameter-, Platzierungs- oder Kipp-Änderung seit der letzten Simulation dieses Teils markiert das Badge veraltet, statt es kommentarlos als aktuell zu zeigen — **veraltet bleibt sichtbar, wird nur markiert** (viewer/CONTEXT.md), nicht gelöscht.
- **Neu-Zerlegung leert die gemerkten Kollisionsbefunde.** `section_id`s werden ordnungsbasiert vergeben (`abschnitt-1`, `abschnitt-2`, …) und können sich zwischen zwei Zerlegungen desselben Druckjobs wiederholen — ohne Leerung klebte ein alter Befund am neuen Teil derselben ID. „✦ Automatisch vorschlagen" leert jetzt die je Teil gemerkten Befunde (`clearedCollisionFindings`, `ui/collision-state.ts`), denselben Zwilling des bestehenden Musters beim Projekt-Öffnen.

Alles additiv (Schema `printability`-Objekt erweitert, `additionalProperties: false` entsprechend nachgezogen) und rein Ableitung im Viewer (ADR-007); der Core rechnet/schreibt (`fgc.decompose.printability.combine_printability`). **Befund, kein Gate** (ADR-013).

### Prüf-Tür raus aus dem interaktiven Loop — expliziter Anstoß + Cache + Sperre freigeben (Reiter Zerlegung, Issue #175)

Die teure **Stufe-2-Prüf-Tür** (Druckbarkeit je Höhenreihe, #162/#164) fror bislang bei **jedem** Schnitt-Edit den Editor ein: die `POST …/decomposition`-„Prüfen lassen"-Runde rechnete synchron, unter der Projekt-Sperre, ohne Cache und ohne Fortschritt die ~10 s/Reihe mit (Befund B14: ~71 s Freeze) — Nutzer mieden dadurch das Prüfen, und die Ehrlichkeits-Funktion sabotierte ihre eigene Nutzung (Karten-Zielmarke #139: Fokus-Teil schnell). Issue #175 löst die Prüf-Tür aus dem interaktiven Loop:

- **Schnitt-Edit blockiert nicht mehr.** „Prüfen lassen" (der Schnittplan-Neubewertungs-Button) rechnet nur noch die **gratis** Stufe 1 (Erreichbarkeit + Freigang): ist die Wand nach Freigang zu dick, tragen alle Teile sofort **„zu dick"**; sonst bleibt jedes Teil ehrlich **„ungeprüft"** (`printability.reason = "unchecked"`, neuer Grund) — **nie stilles Grün** (ADR-013). Die teure Prüf-Tür läuft dort nicht mehr mit.
- **Expliziter Anstoß / Hintergrundlauf mit Fortschritt.** Ein eigener **Prüf-Tür-Block** unter dem Schnittplan bietet zwei Knöpfe: **„Fokus prüfen (~10 s)"** (Default-Wahl — nur die Höhenreihe des fokussierten Teils) und **„Ganze Wand prüfen (N Abschnitte, ~X s)"** (die bewusste, teurere Wahl mit **Umfangsansage** aus `pruef_scope`). Die Prüfung läuft als **Hintergrundlauf** (`POST …/decomposition-check` → `GET …/{check_id}` gepollt) mit **Fortschrittsbalken** („Prüfe … 3/8 Höhenreihen") und **Abbrechen**-Knopf; ein Abbruch persistiert nichts (der Stand bleibt „ungeprüft").
- **Ergebnis-Cache je (Schnitt, Platzierung, Parameter).** Ein Repräsentant, dessen Signatur (Zellgeometrie + Platzierung + Prozessparameter + Roboter/Endeffektor/Workstation) unverändert ist, wird **nicht** erneut gerechnet — nach einem Edit lässt sich so **nur** das Fokus-Teil billig nachprüfen; ein unveränderter Zweitlauf rechnet **0** (der Fortschritt zeigt „N aus Cache").
- **Projekt-Sperre nicht über die Rechenzeit gehalten.** Der Hintergrundlauf lädt/rekonstruiert nur an den kurzen Rändern unter der Sperre; die eigentliche Prüfung läuft **ohne** Sperre — parallele Schreibzugriffe (Schnitt verschieben, Slice-Param ändern) bleiben möglich, der Editor friert nicht. Ändern sich die Prüf-Eingaben **während** der Rechnung, wird das Ergebnis als **verworfen** gemeldet (kein Lost-Update auf frische Edits) statt still überschrieben.
- **Sichtbarer letzter Prüfstand.** Eine Zeile zeigt **was zuletzt geprüft wurde** (ganze Wand vs. Fokus-Teil) und ob der Stand **veraltet** ist (eine Schnitt-/Platzierungs-/Parameter-Änderung seither) — dieselbe Veraltungs-Ableitung wie die übrigen Badges (#172/#182-Muster), sichtbar markiert, nicht gelöscht.

Der Marker lebt am Druckjob (`print_job.last_pruef`: Reichweite + Eingabe-Schnappschuss, additiv); das Urteil im Zerlegungslauf (`decompose.json`, `sections[].printability`) wie bisher. Reine Aktions-Naht `fgc.pipeline.actions.check_decomposition` (Cache, Fortschritt, Abbruch, Supersede-Wächter) + Hintergrundlauf-Registry `fgc.pipeline.checkjobs`; reine Viewer-Zustandsfunktionen `ui/pruef-check-state.ts` (Fortschritt/Umfang/letzter-Prüfstand). **Befund, kein Gate** (ADR-013).

### Prozess-Schritt „Slicing" — eigener Inspector + 5-Schritt-Routing (UI-Redesign Scheibe 5, Issue #107)

Fünfte Scheibe des UI-Redesigns und **zweiter Teil des Druckplan-Splits**: die frühere Rubrik „Slicing" (#89) wird ein **eigener Prozess-Schritt** mit einem **Inspector (352 px)** rechts. Damit ist die Rubriken-Navigation `druckplan-rubrics` (#89) vollständig entfallen — die Umkehrung ist bewusst: statt eines Umschalters im Druckplan-Aside gibt es jetzt **einen eigenen Schritt je Belang**. Der Stepper im Header ist damit endgültig fünfstufig **Projekt → Roboter → Zerlegung → Slicing → Export**; der interne Reiter-Schlüssel bleibt `druckplan` (data-panel), beschriftet als „Slicing". Der Inspector von oben:

1. **Kopf** — Titel „Slicing" und der **Gilt-für-Umschalter** (Segmented **Global | <Teilname>**, das aktive Teil-Segment in Akzent). Der Scope existiert **nur hier** — im Reiter Zerlegung gibt es keinen. Sichtbar wird er erst, wenn in der Teile-Palette ein Teil **gewählt** (fokussiert) ist.
2. **Accordion „Prozessparameter"** — ein **2-spaltiges `.field-box`-Grid** (Schichthöhe, Strangbreite, Schalen, Lead/Lag, Kipp) mit der **Einheit rechts im Feld**. Platzhalter-Konvention: im Global-Scope zeigt ein leeres Feld „<default> · Karten-Default" (es fällt auf den Karten-Default zurück), im Teil-Scope den geerbten globalen Wert dezent („8 · erbt"). Jede Eingabe im Teil-Scope wird zum **feldweisen, sparsamen Override** (Akzent-Feld + ↺ „auf global zurück"). Der Accordion-Kopf zeigt im Teil-Scope **„N Overrides"**, sonst **„gilt global"**.
3. **Accordion „Fortgeschritten"** (per Default zugeklappt) — Druck-/Travel-Geschwindigkeit und io Druck/io Travel. Der Aufklapp-Zustand gehört weiterhin `ProcessParamsPanel` (`process-params-advanced-*`, `collapsible-state.ts`), unverändert.
4. **Accordion „Singularitäts-Advisor"** — Befund-Box + Buttons **„Prüfen"** / **„Anwenden"**; Kopf-Hinweis **„Fokus-Teil"** (der Advisor prüft seit Issue #134 die Platzierung des in der Teile-Palette **fokussierten** Teils; ohne Fokus zeigt „Prüfen" einen freundlichen Hinweis).
5. **Accordion „Kollisions-Advisor"** (per Default zugeklappt) — **„Kollision prüfen (≈ 20 s)"** (nur Basis-Befund, eine Neu-Simulation) + **„Hebel-Optionen suchen (Minuten)"** (gerankte **Optionsliste**, das „Menü") mit je Zeile einem eigenen **„Anwenden"**-Knopf; der Scope-Chip nennt dynamisch das geprüfte **Fokus-Teil** (Issue #130, Prüf-UX #139/#145, s. u.).
6. **Sticky-Footer** — Status links, **„Speichern"** rechts: speichert im Geltungsbereich des Gilt-für-Umschalters (global bzw. `process_params.sections`, #82-Mechanik) über die bestehende Core-Route.

Das Simulieren wohnt seit Scheibe 6 (#108, s. u.) **nicht mehr im Slicing-Aside**, sondern im **Simulations-Dock** am Fuß des Viewports; den früheren Modus-/Simulieren-Bereich (#86) gibt es nicht mehr. Die **Veraltet-Kette** ist unangetastet: Speichern in Slicing färbt **Simulation** und **Export** amber (Stepper-Punkte + Badges aus der bestehenden `ui/staleness.ts`-Ableitung); Prüfen/Simulieren/Exportieren heben sie stufenweise auf. Die Fachlogik (`ScopeSwitch`/`scope-state`, `ProcessParamsPanel`/`section-params-state`, `SingularityAdvisorPanel`) ist **unverändert wiederverwendet** (recompose, kein Fork); Sichtbarkeit läuft ausschließlich über `hidden`; **keine Core-/API-/Schema-Änderungen**, Staleness-Parität unangetastet.

### Simulations-Dock statt Modus-Umschalter (UI-Redesign Scheibe 6, Issue #108)

Sechste Scheibe des UI-Redesigns: **Simulieren wird ein Dock statt eines Modus**. Am **Fuß des Viewports** (nur im Reiter **Slicing** sichtbar) sitzt eine feste Leiste `#sim-dock` (Panel-Hintergrund 96 %, Border oben) mit — von links — dem **Primär-Knopf „▶ <Fokus-Teil> simulieren"**, dem **Sekundär-Knopf „Ganze Wand"** (bzw. „Alle Module" bei Modul-Zerlegung, #97) und dem **Trajektorien-Abspieler**: Play/Pause, **Timeline** (5 px Track, Fill + Knopf in Akzent), **Zeit** (Plex Mono) und **Phasen-Pill** („Abschnitt 1 druckt" ⓘ). Der Player-Teil erscheint erst beim Abspielen; **Timeline, Zeit und Phasen-Pill spiegeln den bestehenden Player-Zustand** (dieselbe Player-Instanz, `simulation-state` unverändert). Die bestehenden Simulier-Aktionen und der Player (#26/#27/#48, Modul-Simulation #97) **docken hier an** — kein neuer Player, keine neue Kinematik (ADR-007).

Die **Modus-Radiogroup „Vorbereiten/Simulieren"** (#86) ist damit **ersatzlos entfallen**: Schnittplan-Bearbeitung und Simulation **koexistieren ohne Modus**. Den „nicht mit veralteten Werten simulieren"-Schutz leistet allein die **Veraltet-Markierung** (nur veraltete Teile amber, ADR-017); ein frisch über „Fokus simulieren" erzeugter Lauf entsteht aus den *aktuellen* Werten (nie veraltet). Diese **Umkehrung von #86 (Modus → Dock)** ist im Design-Log (2026-07-08) dokumentiert. Solange **kein** Replay läuft, sind die Live-Vorschau (#85) und die Platzierungs-Marker (#93) aktiv; während eines Replays ruhen sie — Viewer-intern über ein `replayActive`-Flag statt des früheren `planMode`. Der **`?run=`-Abspieler-Deeplink** bleibt unverändert funktional (eigener Pfad im Reiter Projekt). Pure/DOM-Split (ADR-007): die reine Aktions-/Beschriftungslogik (Simulier-Ziel `focusTarget`, artabhängige Knopf-Labels) liegt DOM-frei in `viewer/src/ui/sim-actions.ts` (vitest); das Dock treibt `viewer/src/ui/simulation.ts`. Der DOM-Vertrag (Dock neben `#viewport`, Modus-Radiogroup entfernt) ist in `shell-structure.test.ts` festgezurrt, das Dock statt Umschalter im `ui_smoke.mjs`. Sichtbarkeit ausschließlich über `hidden`; **keine Core-/API-/Schema-Änderungen**.

### Projektliste mit Karten, Wand-Bilanz-Balken und IFC-Dropzone (UI-Redesign Scheibe 7, Issue #104)

Siebte Scheibe des UI-Redesigns: der **Startbildschirm** (Viewer ohne `?run=`) wird eine **zentrierte Spalte** (max. 840 px). Der Kopf trägt links die **Logo-Kachel** („FG", Plex Mono) und den Titel **„FGC-Planner"**, rechts den **API-Status**: ein grüner Punkt + „Core-API verbunden", wenn die Core-API erreichbar ist — sonst ein **amber Punkt** + „Core-API nicht erreichbar", und der bisherige `fgc start`-Hinweis wandert ins `title`-Attribut.

Projekte erscheinen als **Karten im 2er-Grid** (`--panel`, Radius 12 px; Hover = Akzent-Rahmen): Name + Zeitstempel („vor 2 Std.", „gestern") oben, darunter der **IFC-Dateiname** in Plex Mono. Jede Karte zeigt einen **Wand-Bilanz-Balken** (6 px hoch, Segmente grün/amber/rot anteilig) mit **Legende** („9 druckbar · 4 vorläufig · 7 ungeeignet"). Die Anteile stammen **ausschließlich** aus dem `candidates.json`-Artefakt des Übersichts-Laufs — dieselbe Regel wie die Einfärbung der Modellübersicht (`render/model.ts` `verdict()`): *druckbar* = eligible ohne provisional-Pass, *vorläufig* = eligible mit provisional-Pass, *ungeeignet* = nicht eligible. Es wird **nichts neu gerechnet** (ADR-007), nur die vom Core gesetzten `eligible`/`provisional`-Flags gezählt; die reine Zähl-/Anteils-Mathematik lebt getestet in `ui/wall-balance.ts`. Die Karten rendern **sofort**, die Balken werden je Projekt asynchron nachgereicht (Übersichts-Lauf lesen). **Projekte ohne Übersichts-Lauf** (oder ohne ladbares `candidates.json`) **degradieren sauber**: kein Balken statt eines kaputten 0-%-Balkens.

**„Neues Projekt aus IFC"** ist eine **Dropzone über die volle Breite** (gestrichelt, Plus-Kachel, „IFC-Datei hierher ziehen oder durchsuchen…"): ein Klick öffnet den Datei-Dialog, ein Drag&Drop legt die IFC ab. Das **Namensfeld wird erst nach der Dateiwahl** abgefragt (mit dem editierbaren IFC-Pfad daneben, aus der Datei vorbefüllt). Der eigentliche **Anlage-Flow bleibt unverändert** (`POST /projects` mit `model_path`, ADR-016) — der Core liest die IFC vom absoluten Disk-Pfad; wo der Browser ihn nicht preisgibt (Sandbox), vervollständigt man ihn im vorbefüllten Feld.

### Roboter-Schritt + Bibliothek im neuen Design (UI-Redesign Scheibe 8, Issue #105)

Achte Scheibe des UI-Redesigns: der **Reiter Roboter** und die **Bibliothek** werden an die Design-Tokens angeglichen — reiner Restyle, alle Auswahl-, Warn- und Neubewerten-Flows bleiben funktional unverändert.

**Reiter Roboter** ist jetzt ein 352 px breites Panel aus **drei Sektionen** (Roboter / Endeffektor / Workstation), je durch eine dünne Trennlinie getrennt. Jede Sektion hat einen **Select** über die volle Breite und darunter ein **Kenndaten-Grid** — Label in `--muted`, Wert in **Plex Mono** (Reichweite/Traglast/Druckhöhe, Gewicht/Kanäle, Podesthöhen …). Die bestehenden **Warnungen** (Payload-Überschreitung, Endeffektor-/Workstation-Kompatibilität) bleiben als kompakte amber Befund-Zeilen — **Befund, kein Gate** (ADR-013), inkompatibles Zubehör wird weiterhin nur ausgegraut, nie gesperrt. Unter dem Roboter-Select sitzt **„↻ Alle Wände neu bewerten"** als Akzent-Outline-Button (volle Breite). Der Panel-Rumpf scrollt; darunter bleibt ein **Sticky-Footer „Speichern"** stehen, der die Wahl von Endeffektor und Workstation persistiert (er leitet an die bestehenden, weiterhin verdrahteten Sektions-Speicherpfade weiter — je ein eigener Core-Endpoint mit eigener Veraltungs-Semantik; die Roboterwahl selbst persistiert über den Neubewerten-Lauf).

**Bibliothek:** Die Rubriken-Rail links ist 176 px breit; die **aktive Rubrik** wird als gefüllter **Chip** dargestellt (`--chip`-Fläche, `--chipbd`-Rahmen, Radius 8 px) statt der früheren Border-Left-Markierung, die inaktiven Rubriken sind schlichter `--muted`-Text. Die **Karten** tragen den großen Radius (`--r-lg`, 10 px), ein `--field`-Thumbnail und `--border2`-Aktionsbuttons; Roboter-Karten sind **read-only** (keine Bearbeiten/Löschen-Aktionen, `#76`) und tragen eine dezente **read-only-Pille** (`--border2`-Rahmen, Radius Pille). Der **Endeffektor-Konfigurator** und der **Workstation-Editor** bekommen nur das Token-Mapping (Farben/Radien), keinen strukturellen Umbau.

### ⌘K-Befehlspalette — jede Einstellung & Aktion suchen und anspringen (UI-Redesign Scheibe 9, Issue #109)

Letzte Scheibe des UI-Redesigns: eine **Befehlspalette** als Overlay über der ganzen App. **⌘K / Ctrl-K** öffnet und schließt sie (Umschalter), **ESC** schließt, und die bislang funktionslose **Suchfeld-Attrappe** im Header (Scheibe 2) öffnet sie ebenfalls (Klick oder Enter/Space). Das Overlay folgt dem Prototyp: 600 px breites Panel auf Panel-Hintergrund, Radius 14 px, Modal-Schatten, abgedunkelter (leicht unscharfer) Hintergrund; Klick daneben schließt.

Getippt wird oben in ein Suchfeld; darunter erscheinen **Trefferzeilen „Icon | Label | Gruppe (rechts)"**, Hover/aktive Zeile = Akzent 12 %. Die **Registry** deckt alle **fünf Prozess-Schritte plus die Bibliothek** ab — sowohl **Einstellungen** (Schichthöhe, Strangbreite, Schalen, Lead/Kipp, Geschwindigkeiten & io, Zerlegungsart, Aufstellung, Modulgrößen, Fugen-Versatz, Platzierungs-Overrides, Roboter-/Endeffektor-/Workstation-Wahl …) als auch **Aktionen** (Automatisch vorschlagen, Höhen-/Längsschnitt, Prüfen lassen, Fokus-/Ganze-Wand-Simulieren, Singularität prüfen/anwenden, Neuer Endeffektor/Workstation, **Theme umschalten**). ↑/↓ bewegen die Auswahl, Enter oder Klick führt aus.

**Ausführen** navigiert an den Ort der Einstellung bzw. löst die Aktion aus — und zwar über die **bestehenden** Mechanismen, ohne zweiten Zustand: Reiter wechseln (`shell.setActiveTab`), das Ziel-Accordion öffnen (Klick auf dessen Toggle, nur wenn es zu ist — der Aufklapp-Zustand des besitzenden Panels bleibt konsistent), das Feld fokussieren bzw. den bestehenden Aktions-Button klicken (Theme über `ui/theme.ts`). Die Sichtbarkeit des Overlays läuft ausschließlich über das `hidden`-Attribut; es gibt **keine Core-/API-/Schema-Änderung**. Die Filterlogik ist ein reines, vitest-getestetes Zustandsmodul (`ui/palette-state.ts`: Registry + Substring-/Fuzzy-Filter), die dünne DOM-/Overlay-Schicht liegt in `ui/palette.ts`; ein DOM-Vertrag (`ui/palette-dom.test.ts`) sichert ab, dass jede in der Registry genannte Element-ID wirklich in der `index.html` existiert.

### Projekt-GUI — Tab-Shell + Projekte (Issue #16, ADR-016)

Das **Projekt** ist die langlebige, editierbare Persistenz-Einheit der GUI (ADR-016): ein IFC-Modellpfad plus 1..n **Druckjobs**. Es liegt als schema-validiertes `project.json` unter `projects/<slug>/` und **verweist** auf Läufe (Übersichts-Lauf, später Slice/Simulation) — es enthält nie eingebettete Rechenergebnisse. Läufe bleiben die unveränderlichen Rechen-Artefakte (ADR-004); das Projekt ist die veränderliche Klammer darüber.

**Beim Start** (Viewer ohne `?run=`) zeigt die GUI die **Projektliste** und den Knopf **„Neues Projekt aus IFC…"**. Ein neues Projekt anlegen erzeugt Projektordner + `project.json` **und** den Übersichts-Lauf (`walls list`: `candidates.json` + `model.glb` + `model_map.json`), auf den das Projekt verweist; danach öffnet sich der Reiter **Projekt** mit der nach Eignung eingefärbten Modellübersicht und klickbarer Wand-Auswahl. Ein bestehendes Projekt öffnen stellt denselben Stand wieder her.

**Tab-Shell:** Vier Prozess-Reiter — **Projekt, Roboter, Druckplan, Export** — plus ein **Bibliothek**-Bereich (Stammdaten außerhalb des Prozesses). Der frühere fünfte Reiter **Simulation** ist seit der Modus-Fusion (Issue #86, s. u.) im Reiter **Druckplan** aufgegangen. Reiter sind **Navigation, kein Zwangspfad**: jeder Reiter ist von jedem aus frei erreichbar. Alle Prozess-Reiter teilen sich **ein** 3D-Hauptsichtfeld (s. u.).

Projekt-Operationen laufen über die lokale Core-API (dünne Aktions-Wrapper, ADR-014): `GET /projects` (listen), `POST /projects` (aus IFC anlegen), `GET /projects/{slug}` (laden). Ohne laufende API bleibt die Projektliste sichtbar, mit Hinweis „mit `fgc start` hochfahren"; die einzige Schreibstelle für `project.json` ist das Core-Modul `fgc.project` (validiert gegen `schemas/project.schema.json`).

**Fallback-Direkteinstieg unverändert:** Der `?run=`-Parameter (und `start_viewer.cmd`) lädt weiterhin einen Laufordner direkt in den Reiter Projekt, ohne den Umweg über die Projektliste.

#### Atomares Schreiben mit Retry gegen transienten WinError 5/32 (Issue #158)

Die atomaren Schreibstellen (`project.json` via `fgc.project.write_project`, Workstation-Artefakte via `fgc.domain.workstation.write_workstation_artifact`) schwenken ihre Temp-Datei über **einen gemeinsamen Helfer** `fgc.atomic_io.replace_with_retry(src, dst)` ein. Grund: `os.replace` ist auf Windows zwar atomar (ADR-018), aber nicht retry-frei — hält ein Fremdprozess (Defender/Echtzeitscanner, Suchindexer, Backup-Agent) kurzzeitig ein Handle auf die eben geschriebene Datei, scheitert der Rename mit `ERROR_ACCESS_DENIED` (WinError 5) oder `ERROR_SHARING_VIOLATION` (WinError 32), statt zu warten. Ohne Retry brach dann eine Projekt-Mutation mit `PermissionError` ab, obwohl der Zustand konsistent war (und auf CI machte es die Suite sporadisch rot, mit wechselnden Tests je Lauf).

Der Helfer wiederholt **nur** den `os.replace`-Aufruf: bis zu 5 Versuche mit wachsendem Backoff (10–50 ms), aber ausschließlich bei `OSError` mit `winerror in {5, 32}`. Jeder andere Fehler — und auf POSIX jeder Fehler, weil `winerror` dort fehlt (`os.replace` ignoriert offene Handles) — wird sofort unverändert durchgereicht; nach erschöpften Versuchen fliegt die Original-Exception. Die Atomarität aus ADR-018 bleibt unberührt: weiterhin genau eine Temp-Datei + atomarer Rename, halb geschriebene Dateien kann es nicht geben. Tests: `core/tests/test_atomic_io.py` (gestubbter `os.replace`, plattformunabhängig auch auf POSIX).

### Geteiltes 3D-Hauptsichtfeld + Roboter-Vorschau (Issue #30/#31)

Alle fünf Prozess-Reiter teilen sich **ein** 3D-Hauptsichtfeld **links**, der
jeweilige **Inspector rechts** (Redesign-Handoff, Issue #114) — der
Reiterwechsel tauscht nur das rechte Panel, die Szene bleibt stehen. Damit sind Basis-Marker der Platzierung (Issue #22), die
Schnittebenen des Zerlegungsvorschlags inklusive Drag-Editing (Issue #24/#25)
und das Trajektorien-Replay direkt im jeweiligen Reiter sichtbar, nicht nur im
Reiter Projekt.

- **Reiter Roboter:** zeigt statt der Modellübersicht eine **Roboter-Vorschau** —
  der M1013-Arm (echte Meshes per Default, umschaltbar auf das Kapsel-Schema —
  siehe „M1013-Meshes im Präsentations-Arm", Issue #41) in Home-Pose (aufrechte
  Doosan-Nullstellung, Flansch oben — Issue #53) mit
  Flansch-Achsenkreuz; der gewählte Endeffektor hängt als Mesh am Flansch und
  wechselt live mit der Auswahl. Beim Verlassen des Reiters kehrt die
  Modellübersicht mit dem vorherigen Kamerastand zurück.
- **Bibliothek:** behält ihre eigene Konfigurator-Szene (Issue #28); das
  geteilte Hauptsichtfeld ist dort ausgeblendet.
- **Wandauswahl** (Klick → Eignungsbericht) bleibt dem Reiter Projekt
  vorbehalten; das Ziehen von Schnittebenen funktioniert im Reiter Projekt und
  Druckplan. Ein Klick, der auf der Wand landet, greift keine dahinter
  liegende Schnittebene mehr — gegriffen wird am sichtbaren Überstand der
  Ebenen (Issue #37).

### Viewer — Läufe ansehen

Statische Web-App (Vite + three.js), zustandsloser Abspieler der Core-Artefakte: Wand-Mesh, Druck-/Travel-Pfade mit Schicht-Slider, Gebäudekontext als Geister-Mesh. Details: [viewer/README.md](viewer/README.md).

```powershell
cd viewer; npm install; npm run dev   # http://localhost:5173
```

Laufordner laden per „Laufordner öffnen…", Drag&Drop — oder direkt per URL:
`http://localhost:5173/?run=/@fs/C:/…/RoboPrintIFC/runs/<lauf>` (gibt `fgc start` fertig aus).

### Viewer-Parameter-Panel — Re-Slicing ohne CLI (Issue #9, ADR-014)

Ist die lokale Core-API erreichbar (läuft nach `fgc start` automatisch), erscheint im Viewer-Seitenpanel ein **„Slice-Parameter"-Abschnitt**: Schichthöhe, Strangbreite und Schalenzahl lassen sich anpassen; ein Klick auf **„Neu slicen"** sendet die Parameter per `POST /slice` an die API, wartet auf den neuen Laufordner und lädt dessen Artefakte in die bestehende Ansicht — ohne Neustart oder CLI-Aufruf.

**Ausgangswerte:** Das Panel liest die Parameter des zuletzt geladenen Laufs aus `toolpath.params` (Schema-Version 0.3, ab Issue #9 geschrieben). Leere Felder bedeuten „Karten-Default übernehmen" — die API füllt den Rest aus der Prozessfenster-Karte (ADR-013/014). Ältere Läufe (0.2, ohne `params`-Block) zeigen leere Felder.

**Offline-Modus:** Ist die API nicht erreichbar (z. B. reiner Viewer-Start ohne `fgc start`), bleibt das Panel sichtbar, aber deaktiviert mit dem Hinweis „Core-API nicht erreichbar — Viewer im Abspieler-Modus." Der Viewer ist voll funktionsfähig; kein Eignungscheck, kein Slicing, nur Abspielen.

Jeder Klick erzeugt einen regulären, provenienzgestempelten Laufordner (ADR-004) — identisch zu einem `fgc slice`-Aufruf, reproduzierbar und archivierbar.

### Modellübersicht — alle Wände eingefärbt nach Eignung

`fgc walls list` schreibt neben `candidates.json` die binäre Modell-glTF `model.glb` (ein Szenenknoten je Wand, Knotenname `wall_<GlobalId>`) sowie das schema-/provenienz-konforme Mapping `model_map.json`, das jeden GLB-Knoten an seine GlobalId bindet und über `mesh_file` auf die GLB verweist. Der Viewer lädt die GLB per three.js `GLTFLoader` und verbindet die Knoten über das Mapping mit den Eignungsurteilen aus `candidates.json`.

Die Wände tragen einen **einheitlichen Lehm-Ton** (Material bleibt Material — leichte Helligkeitsvarianz je Wand). Die Eignung wird **nicht mehr als Vollfärbung**, sondern als farbiger **Sockel-Streifen am Wandfuß** (~70 mm) gezeigt:

| Sockel-Streifen | Bedeutung |
|---|---|
| Grün | geeignet (alle Checks scharf bestanden) |
| Amber | geeignet, aber mind. ein Check nur provisorisch bestanden (Prozessparameter noch nicht gemessen) |
| Rot | nicht geeignet |
| Grau | keine Kandidaten-Information vorhanden |

Im Seitenbereich des Viewers erscheint die Zusammenfassung **„X / Y Wände druckbar"**. Der Viewer rechnet dabei nichts selbst (ADR-007) — Geometrie, Urteile und Sockel-Farben kommen vollständig aus den Artefakten.

### Viewport-Optik „Clay-Studio" (Handoff-Scheibe 9, Issue #113)

Das geteilte 3D-Feld ist eine ruhige Studio-Bühne statt eines schwarzen Kastens. Sämtliche Bühnen-Farben stammen aus den CSS-Design-Tokens (`--vp1/--vp2/--accent/--ok/--warn/--err/--info`), damit der **Theme-Umschalter ◐ auch die 3D-Bühne mitkippt** (Hintergrund, Fog, Gitter):

- **Studio-Hintergrund**: radialer Verlauf (`--vp1` innen → `--vp2` außen) statt Schwarz, dezenter Fog; das Gitter ist nur nahe der Szene sichtbar (der Fog blendet die fernen Linien aus) und sehr zurückhaltend (Deckkraft ~0.06 dunkel / ~0.09 hell). Ein weicher, radial auslaufender **Bodenschatten** setzt die Szene auf.
- **Wände**: Lehm-Ton mit ±8 % Helligkeitsvarianz je Wand (matt, keine Metalness); Eignung als Sockel-Streifen (s. o.). Die **Auswahl** einer Wand zeigt einen dezenten Akzent-Glow statt eines reinen Deckkraft-Wechsels.
- **Zerlegung**: der Fokus-Abschnitt steht im vollen Lehm-Ton, die übrigen Abschnitte sind gedimmt (entsättigt/dunkler). Die Schnittebenen sind flächige **Glas-Ebenen** (amber, ~12 % Deckkraft) mit voll deckender Unterkante; an jeder Ebene schwebt ein **Maß-Label** („z 1200 ⇅", Plex Mono, amber Rahmen) als HTML-Chip über dem projizierten Punkt. Das Draggen der Ebenen bleibt unverändert.
- **Slicing/Simulation**: die gedruckten Bahnen erscheinen im Akzent-Streifenmuster (gestrichelt); der **TCP-Marker** ist ein cyanfarbenes Kreis-plus-Quadrat-Fadenkreuz; die Platzierungs-Marker tragen einen Chip **„Basis · Podest &lt;h&gt;"**.

Die Chips liegen als durchklickbares Overlay (`pointer-events:none`) über dem Canvas — Picking, Drag und Kamera bleiben unberührt (Handoff-Protokoll: nur Material/Licht/Farbe).

Laufordner mit `model.glb` laden:

```powershell
.\fgc walls list examples\Building-Architecture.ifc
# gibt aus: candidates.json + model.glb + model_map.json im neuen Laufordner
# Viewer: http://localhost:5173/?run=/@fs/C:/…/runs/<lauf>
```

### Klickbare Wand-Auswahl — Eignungsbericht + Direkt-Slicing (Issue #10)

Im nach Eignung eingefärbten Gesamtmodell (nach `fgc walls list`) lässt sich jede Wand anklicken:

- **Klick auf eine Wand** hebt sie hervor (volle Deckkraft, Rest gedimmt) und zeigt im Seitenpanel den Eignungsbericht: alle Einzel-Checks mit Symbol (✓/✗), Checkname, Begründungstext und einem „vorläufig"-Badge für provisorische Checks.
- **Abgelehnte Wände** zeigen alle Ablehnungsgründe und sind trotzdem slicebar — der Button heißt dann „Trotzdem slicen (nicht geeignet)" (Parität zum Wizard). Die Eignung ist ein **Befund**, kein Gate: ungeeignete Wände werden später über Roboter-Platzierung oder Zerlegung passend gemacht.
- **„Diese Wand slicen"** (sobald die Core-API erreichbar ist) ruft `POST /slice` auf, wartet auf den neuen Laufordner und öffnet ihn in der Einzelwand-Ansicht — identisch zum Ergebnis eines `fgc slice`-Aufrufs. Der Button erscheint nur im **Abspieler-Modus ohne Projekt** (`?run=`-Deeplink); im Projektfluss zeigt der Bericht stattdessen „In Druckjob übernehmen" (Issue #19) — gesliced wird dort je Abschnitt über den Reiter Simulation.
- **Klick ins Leere** hebt die Selektion auf.
- **Drag-Schwelle:** Bewegungen > 5 px werden als Orbit-Geste gewertet, nicht als Klick.

Die Modellansicht ist aus `candidates.json` + `model_map.json` + `model.glb` des `fgc walls list`-Laufs aufgebaut. `model_path` in diesen Artefakten ist der aufgelöste absolute Pfad, damit der Viewer ihn ohne CWD-Wissen direkt an `POST /slice` weitergeben kann (ADR-014).

**Ende-zu-Ende:**

```powershell
.\fgc walls list examples\Building-Architecture.ifc
# → neuer Laufordner mit candidates.json + model.glb + model_map.json
# Viewer: http://localhost:5173/?run=/@fs/C:/…/runs/<lauf>
# → Wand anklicken → Eignungsbericht lesen
# → „Diese Wand slicen" (bzw. „Trotzdem slicen" bei ungeeigneten Wänden) → Einzelwand-Ansicht
```

*(Die vier Wände des Beispielmodells sind aktuell alle abgelehnt — Bericht und „Trotzdem slicen"-Weg sind damit real prüfbar.)*

### Gebäudekontext in der Modellübersicht (Issue #17)

Neben den Wänden (eingefärbt nach Eignung) zeigt die **Modellübersicht** jetzt auch Decken, Dächer, Stützen und sonstige Nicht-Wand-Elemente des IFC-Modells als **halbtransparentes Kontext-Mesh**. So lassen sich Wände räumlich im Gebäude einordnen, ohne dass Schichtaufbau oder Eignungsurteil verdeckt werden.

**Was exportiert wird:**

`fgc walls list` ruft nach dem GLB-Export der Wände `load_context_overview` auf, das alle `IfcProduct`-Instanzen tesselliert — außer:
- `IfcWall` und Untertypen (bereits in `model.glb`)
- Nicht-körperliche Elemente: `IfcOpeningElement`, `IfcSpace`, `IfcAnnotation`, `IfcGrid` (würden die Ansicht verdecken oder sind rein geometrielos)

Das Ergebnis wird als schema-validiertes `context.json`-Artefakt in den Laufordner geschrieben. Fehlen Nicht-Wand-Elemente (rein-Wand-Modelle), wird kein `context.json` erzeugt.

**Viewer-Steuerung:**

- Das Kontext-Mesh erscheint automatisch, sobald `context.json` im geladenen Lauf liegt.
- Die Checkbox **„Gebäudekontext"** im Seitenpanel blendet den Kontext ein/aus — wie bei Einzel-Wand-Läufen (kein neuer Schalter nötig).
- Das Kontext-Mesh ist **nicht pickbar**: Klicks durch halbtransparente Elemente selektieren die dahinterliegende Wand (oder nichts), nicht den Kontext.

**Bestandsläufe bleiben unverändert:** Läufe ohne `context.json` (aus älteren `fgc walls list`-Aufrufen) laden weiterhin problemlos; der Kontext-Schalter wird in diesem Fall nicht angezeigt.

### Wand-Fokus ab Zerlegung + Viewer-Einstellungen (⚙-Menü am 3D-Feld)

Sobald die Wand feststeht, lenkt das geteilte 3D-Feld den Blick auf **genau diese Wand**: Ab dem Reiter **Zerlegung** (und weiter in **Slicing** und **Export**) zeigt es standardmäßig **nur die gewählte Wand** — die übrigen Wände der Modellübersicht und der Gebäudekontext-Geist treten zurück, damit Schnittebenen, Abschnitte und Platzierung ungestört lesbar bleiben. Beim Wechsel in einen dieser Reiter fasst die Kamera die Wand automatisch ein. Der Reiter **Projekt** bleibt die **Modellübersicht** mit allen Wänden und klickbarer Wand-Auswahl.

**Viewer-Einstellungen (⚙):** Ein schwebendes, ein-/ausklappbares Menü **rechts oben** über dem 3D-Feld (nur in den Fokus-Reitern sichtbar, `.float-panel` wie die Teile-Palette) hält die Sicht-Schalter des Fokus-Modus:

- **„Gebäude/Kontext einblenden"** (Standard **aus**): blendet das restliche Gebäude wieder ein — die übrigen Wände der Modellübersicht (gedimmt) **und** den Gebäudekontext-Geist (`context.json`, Nicht-Wand-Elemente) blass um die gewählte Wand. So lässt sich die Wand bei Bedarf räumlich im Gebäude einordnen, ohne den Reiter zu verlassen.
- **„Basis-Marker anzeigen"** (Standard **an**): blendet die Platzierungs-Basis-Marker (#93/#22) samt Basis-Chips im 3D-Feld aus/ein.
- **„Bemaßung (Maße an Schnitten)"** (Standard **an**): blendet die Maß-Labels an den Schnittebenen aus/ein.
- **„Auf Wand einpassen"**: fasst die Kamera erneut auf die gewählte Wand ein (nach freiem Drehen/Zoomen).

Die Schalter kommen aus einer **erweiterbaren Liste** (`ToggleSpec[]` in `main.ts`, gebaut von `ui/viewer-settings.ts`) — weitere Sicht-Schalter kommen als weiterer Eintrag dazu, ohne HTML-Handarbeit.

**Ohne gewählte Wand** (Wand noch nicht übernommen) bleibt die Gesamtansicht — es gibt nichts zu isolieren. Reine Darstellung/Interaktion (ADR-007): Die reine Ableitung „welche Reiter fokussieren, was der Kontext-Schalter zeigt" liegt DOM-/three.js-frei in `viewer/src/ui/viewer-settings-state.ts` (vitest-getestet), die dünne DOM-Klasse in `viewer/src/ui/viewer-settings.ts`; das Isolieren einer Wand ist eine reine `.visible`-Umschaltung in der Modellübersicht (`ModelView.setWallFocus`, `viewer/src/render/model.ts`).

**Zwei benannte ⚙-Sektionen: „Modellansicht" und „Replay-Bühne" (Issue #159):** Das ⚙-Menü gliedert seine Schalter in **zwei Sektionen mit getrennter Sichtbarkeit** — statt einer flachen Liste, die pauschal am Reiter-Gate hängt.

- **„Modellansicht"** (`context`/`basis`/`bemassung` + „Auf Wand einpassen") bleibt an den **Wand-Fokus** gebunden: sichtbar nur in den Fokus-Reitern (Zerlegung/Slicing/Export).
- **„Replay-Bühne"** (`Roboterarm`/`Strang wächst mit`/`Wachsender Druckstand`/`Live-Abstandszahl`/`Punktnummern`) zeigt sich, **wo eine Bühne läuft** — in den Fokus-Reitern **und** im Reiter **Projekt, sobald dort ein Laufordner geladen ist**. Die fünf Schalter steuern **dieselbe** Replay-Bühne im geteilten 3D-Feld, egal aus welchem Reiter man sie umlegt; die Wirkung folgt sofort.

Die früheren Panel-Häkchen **„Roboterarm (Schema)"** und **„Strang wächst mit (Zeit)"** im Reiter Projekt **fallen ersatzlos** — sie sind in die ⚙-Sektion „Replay-Bühne" gewandert und damit erstmals auch im Reiter **Slicing** bedien- und sichtbar (vorher wirkten sie dort, ohne erreichbar zu sein). Die Default-Zustände bleiben unverändert (**Arm an, Strang wächst an**, Druckstand aus, Abstandszahl an). Im **Sequenz-Modus** (Gesamtablauf) ist der Strang-Schalter bedeutungslos — die Zeit deckt den Strang zwingend auf — und wird in der Sektion ausgeblendet (statt wie früher das Panel-Label).

Das ⚙-Menü ist damit im Reiter **Projekt mit offenem Lauf** sichtbar (mit **nur** der Sektion „Replay-Bühne"), im Reiter **Projekt ohne Lauf** sowie in **Roboter/Bibliothek** bleibt es **verborgen**. Sichtbarkeit — je Sektion und für den Strang-Schalter — **ausschließlich über `.hidden`** (Lehre aus #56). Die reine **Sektions-Sichtbarkeitsregel** (Eingabe: aktiver Reiter × ist ein Lauf offen; Ausgabe: welche Sektionen sichtbar, und daraus ob das Menü überhaupt sichtbar ist) liegt DOM-frei in `viewerSettingsSections(...)`/`viewerSettingsMenuVisible(...)` (`viewer/src/ui/viewer-settings-state.ts`, vitest-getestet über Reiter × Lauf-offen). „Lauf offen" bestimmt `main.ts` daran, ob ein Toolpath geladen ist (Arm/TCP/Strang/Druckstand hängen dann am `toolpathView`).

### Punktnummerierung der Bahn-/Anfahrpunkte (⚙-Sektion „Replay-Bühne", Issue #138)

Der ⚙-Schalter **„Punktnummern (Bahn-/Anfahrpunkte)"** (Standard **aus**) beschriftet die Slicer-Targets der geladenen Toolpath-Darstellung mit runden Nummern-Chips — je Target die 1-basierte Position in der Bahn (dieselbe Zählung wie im erzeugten Roboterprogramm). Da eine Wand tausende Targets tragen kann, wird **nicht jedes** Target beschriftet:

- **Beschriftet werden** der erste Punkt sowie jeder **print/travel-Wechsel** und jeder **Ring-/Schichtanfang** — die Punkte, an denen sich in der Bahn tatsächlich etwas ändert. Läuft eine Bahn über hunderte gleichförmige Zwischenpunkte einer Schale, bleiben die dazwischen unbeschriftet.
- **Dichte-Deckelung:** höchstens 150 Labels gleichzeitig; bei mehr aussagekräftigen Punkten wird die Auswahl **gleichmäßig ausgedünnt** (Lücken über die ganze Bahn statt nur am Anfang) — lesbar und ohne Ruckeln auch bei sehr langen Bahnen.
- **Sichtbarkeit folgt der Bahn:** ein Label ist nur sichtbar, wenn sein Target nach dem aktuellen **Layer-Slider**, **Wachs-Modus** (Strang wächst mit) und **Travel-Schalter** ohnehin sichtbar wäre — keine schwebenden Nummern zukünftiger Schichten oder ausgeblendeten Travels.
- **Ein Schalter für alle Bühnen:** Einzel-Lauf, aktives Druckort-Modul und Abschnitts-Sequenz zeigen alle dieselbe `ToolpathView` — der eine ⚙-Schalter wirkt auf jede gerade lebende Instanz, keine zweite Darstellung nötig.

Reine Auswahl-/Ausdünnungs-/Sichtbarkeitslogik in `viewer/src/render/target-labels-state.ts` (`significantTargetIndices`, `thinIndices`, `targetLabels`, `targetLabelVisible`; vitest-getestet, three.js-frei); die Sprite-Erzeugung und das Verdrahten an den Layer-/Wachs-/Travel-Zustand liegt in `viewer/src/render/toolpath.ts` (`ToolpathView.setLabelsVisible`). Reine Darstellung (ADR-007) — kein Fachurteil, nur eine Lesehilfe.

### Wand in den Druckjob übernehmen (Issue #19)

Im Reiter **Projekt** kann jede angeklickte Wand per **„In Druckjob übernehmen"** dauerhaft in den Druckjob des geöffneten Projekts eingetragen werden. Der Eignungsbericht zeigt je Modus genau **eine** Primäraktion: im Projektfluss diesen Übernehmen-Button, im Abspieler-Modus ohne Projekt (`?run=`) stattdessen „Diese Wand slicen" (Issue #10).

- **Auch ungeeignete Wände** sind übernehmbar — der Button heißt dann „Trotzdem übernehmen (nicht geeignet)" mit Tooltip-Warnung (Eignung ist **Befund, kein Gate**, ADR-013: ungeeignete Wände werden später über Roboter-Platzierung oder Zerlegung passend gemacht).
- Der **aktive Druckjob** (Wand-Name + GlobalId) erscheint nach der Übernahme dauerhaft als **Druckjob-Chip** im Header (seit Scheibe 2/Issue #102; früher die Active-Job-Bar) — sichtbar auf allen Reitern.
- Nach einem Neu-Laden des Projekts wird der zuletzt gespeicherte Druckjob automatisch wiederhergestellt.
- Der Druckjob **verweist** auf den Übersichts-Lauf als Befundquelle (`assessment_run`); die Befunddaten selbst werden nicht kopiert (ADR-016).

**Technische Details:**

Der Endpoint `PUT /projects/{slug}/print-job` setzt oder überschreibt den aktiven Druckjob:

```json
PUT http://localhost:8765/projects/mein-projekt/print-job
{
  "wall_global_id": "1AQAupaRP1txwK1AGiN61V",
  "assessment_run": "C:/…/runs/20260705-123456_walls-list_Building",
  "job_id": "default",
  "wall_name": "outer wall - south"
}
```

Das `project.json` wird schema-valide zurückgeschrieben; `assessment_run` zeigt auf den Übersichts-Lauf mit `candidates.json`. Die GUI bearbeitet in v1 einen aktiven Druckjob je Projekt (feste `job_id = "default"`); das Datenmodell erlaubt mehrere Druckjobs (verschiedene `job_id`-Werte).

### Roboterkatalog + roboter-parametrisierte Eignung (Reiter Roboter, Issue #20)

Im Reiter **Roboter** wählt der Nutzer die Roboterdefinition für den aktuellen Druckjob. Die Wahl stößt eine Neubewertung aller Wände mit dem gewählten Roboter an — die Modellübersicht im Reiter Projekt färbt sich danach neu ein, und der Eignungsbericht weist aus, für welchen Roboter geprüft wurde.

**Ablauf:**

1. Projekt öffnen (Reiter Projekt).
2. Zum Reiter **Roboter** wechseln: das Dropdown zeigt alle Roboterdefinitionen aus `robots/` mit Kenndaten (Reichweite, max. Druckhöhe/länge, Arbeitsraum-Status).
3. Roboter auswählen und **„Neu bewerten"** klicken.
4. Ein neuer Befund-Lauf (`walls-list`) wird erstellt; `project.overview_run` und `print_job.assessment_run` zeigen auf den neuen Lauf.
5. Die Modellübersicht (Reiter Projekt) einfärbt sich mit den Eignungsurteilen des gewählten Roboters; der Eignungsbericht beim Klick auf eine Wand zeigt „geprüft für: {robot}".
6. Die Roboterwahl ist im Druckjob persistiert und wird nach Neuladen wiederhergestellt.

**v1-Beschränkung:** Nur der Doosan M1013 ist verfügbar (kein KUKA-Solver portiert, ADR-002/§9.2). Die Mechanik (Dropdown, Neubewertung, Persistenz) ist generisch — ein neuer Eintrag in `robots/` erscheint automatisch im Katalog.

**Robuster Katalog (Issue #73):** Roboterdefinitionen werden gegen `schemas/robot.schema.json` validiert (registriert in `domain.VALIDATABLE_KINDS`; `RobotDef.load` prüft beim Laden). Eine **defekte** Definition (Schema-Verstoß, kaputtes JSON) wird von `GET /robots` nicht mehr still übersprungen, sondern **sichtbar gemeldet**: als Warnung im Log **und** als Eintrag im neuen Antwortfeld `errors` (`{name, error}`). Der Katalog bleibt trotzdem lieferbar — gültige Roboter kommen weiter, nur die kaputte Datei fehlt und wird benannt (report-and-continue). Roboter bleiben im #69-Scope **read-only** (rein additive Validierung, keine Schreibpfade). Unterstrich-präfixierte Felder (`_note`, `_source`, …) sind als Kommentare erlaubt.

**Technische Details:**

`PUT /projects/{slug}/robot` löst die Neubewertung aus:

```json
PUT http://localhost:8765/projects/mein-projekt/robot
{
  "robot": "doosan_m1013",
  "job_id": "default"
}
```

Antwort ist das vollständige `ProjectResponse` mit aktualisiertem `overview_run`. Der neue Befund-Lauf enthält `candidates.json` mit den Eignungsurteilen des gewählten Roboters; der Viewer lädt ihn via `/@fs/`-URL. Der Roboterkatalog wird über `GET /robots` abgefragt.

Die Roboterwahl ist ein **Laufparameter** (wählt den Solver für den Workspace-Check), kein Setup (ADR-006): das Setup entsteht erst beim 3-Punkt-Antasten am Gerät.

### Endeffektor-Katalog + Payload-Check (Reiter Roboter, Issue #21)

Im Reiter **Roboter** wählt der Nutzer unterhalb des Roboter-Dropdowns auch den Endeffektor für den aktuellen Druckjob. Der Endeffektor ist ein projektunabhängiges Stammdaten-Artefakt (`tools/<name>.json`) mit TCP-Frame relativ Flansch, Gewicht/Schwerpunkt und Deklaration der logischen IO-Kanäle (ADR-011).

**Ablauf:**

1. Projekt öffnen, Roboter auswählen (Reiter Roboter).
2. Im selben Reiter: Endeffektor-Dropdown befüllt sich aus `GET /tools`.
3. Endeffektor auswählen und **„Speichern"** klicken.
4. Die Wahl wird im Druckjob persistiert (`print_job.tool`); nach Neuladen wiederhergestellt.
5. Payload-Check: Überschreitet das Werkzeuggewicht die Traglast des gewählten Roboters, erscheint eine **Warnung** — kein Gate (Befund, kein Gate).

**Endeffektor-Definition** (`tools/two_component_nozzle.json`): Referenz-Zweikomponenten-Düse mit drei logischen Kanälen (`pump_a`, `pump_b`, `foam`). Neue Definitionen unter `tools/` erscheinen automatisch im Katalog. Schema: `schemas/tool.schema.json`.

**Logische Kanäle (ADR-011):** Der Endeffektor *deklariert* seine Kanäle (Name + Art analog/digital); das Setup-Artefakt *mappt* sie auf physische AO-/DO-Ausgänge. Diese Trennung hält ADR-011 aufrecht.

**Payload-Check (v1):** Statischer Vergleich Werkzeuggewicht ≤ Roboter-Traglast. Überschreitung ist ein sichtbarer Befund, kein Gate. Dynamik-/Momentenberechnung ist v2.

**API:**

```json
GET  http://localhost:8765/tools
PUT  http://localhost:8765/projects/mein-projekt/tool
{ "tool": "two_component_nozzle", "job_id": "default" }
```

Antwort auf `PUT /tool` enthält `payload_ok` (bool | null) und `payload_margin_kg` (float | null). Der Viewer zeigt die Warnung, wenn `payload_ok = false`.

### Workstation-Wahl + Kompatibilitätsfilter (Reiter Roboter, Issue #77, PRD #69)

Unterhalb des Endeffektors wählt der Nutzer im Reiter **Roboter** die **Workstation** — die Aufstell-Umgebung des Roboters (stationäre Zelle oder mobile, ggf. höhenverstellbare Workstation). Die Workstation ist ein projektunabhängiges Stammdaten-Artefakt (`workstations/<name>.json`, angelegt in der Bibliothek, Issue #72/#75); im Prozess wird nur *ausgewählt*.

**Ablauf:**

1. Projekt öffnen, Roboter auswählen (Reiter Roboter).
2. Im selben Reiter: Workstation-Dropdown befüllt sich aus `GET /workstations`.
3. Workstation auswählen und **„Speichern"** klicken.
4. Die Wahl wird im Druckjob persistiert (`print_job.workstation`, additiv im Schema); nach Neuladen wiederhergestellt. Altprojekte ohne das Feld laden unverändert.

**Kompatibilitätsfilter (dieselbe Logik wie beim Endeffektor, #74):** Workstations, die nicht zum aktiven Roboter passen (`compatible_robots` gesetzt und Roboter nicht enthalten), werden im Dropdown **ausgegraut** (CSS `option-incompatible`), bleiben aber **wählbar** (kein `disabled`). Wird die bereits gewählte Workstation durch einen Roboterwechsel fremd, erscheint eine **Warnung** — **kein Auto-Reset, kein Gate** (ADR-013). Leere/fehlende Tags oder kein aktiver Roboter gelten als „unbekannt" = kompatibel (Migrationsschutz). Der Filter nutzt dieselbe reine Funktion `is_compatible` / `isCompatible` wie der Endeffektor-Filter.

**Veraltung (seit Issue #83 — Ablösung des ursprünglichen #70-Seams):** Ein Workstation-Wechsel veraltet — wie ein Roboter- oder Endeffektorwechsel — die nachgelagerten Stände (Druckplan/Simulation/Export) **und alle Abschnitte**. `workstation` ist seit #83 ein Eingabe-Revisions-Zähler (`INPUT_KEYS`). Ursprünglich (#77) war das **bewusst ausgelassen** (Seam zu PRD B), weil noch kein Output die Workstation-Werte nutzte; seit der Druckplan-Automatismus (#80–82) die Podesthöhen/Mobilität tatsächlich konsumiert, ist der Wechsel eine echte Eingabeänderung und veraltet entsprechend (Design-Log 2026-07-07, ADR-017-Nachtrag).

**API:**

```json
GET  http://localhost:8765/workstations
PUT  http://localhost:8765/projects/mein-projekt/workstation
{ "workstation": "mobile_hub", "job_id": "default" }
```

Antwort auf `PUT /workstation` enthält `compatible` (bool | null — Kompatibilität zum Roboter des Jobs; null, wenn kein Roboter gesetzt). Kein Payload-Check (die Workstation trägt kein Gewicht am Flansch). Persistiert wird ausschließlich über `fgc.project` (einzige Schreibstelle, ADR-016).

### Bibliothek: Workstation-Mesh + Roboter-Platzierung + Bohrbild-Erkennung (Issue #78, ADR-021)

Die **Rubriken-Navigation** der Bibliothek (Roboter / Endeffektor / Workstation) sitzt jetzt als **linke Seitenleiste** statt zentriert nebeneinander.

Der **Workstation-Editor** (Rubrik *Workstation* → **„+ Neue Workstation"** oder **„Bearbeiten"**) bekommt neben dem Formular ein 3D-Sichtfeld. Alle Mesh-/Platzierungs-Felder sind **optional** — ohne sie bleibt die Workstation reine Zahlenfelder wie bisher (Altbestand lädt unverändert).

**Ablauf:**

1. **Mesh laden** (STL/OBJ/GLB) über das Feld *Mesh* — die Aufstell-Umgebung erscheint im Sichtfeld (Upload wie beim Endeffektor: base64-in-JSON, ADR-014, abgelegt neben `<name>.json` in `workstations/`).
2. **Roboter platzieren:** Knopf **„Roboter platzieren: Fläche wählen"**, dann eine Mesh-Fläche anklicken — der Roboter (Kapsel-Arm in Home-Pose) wird mit der Basis auf den **Flächen-Mittelpunkt** gestellt, die Basis-Achse zeigt entlang der Flächennormale. Das Feld **„Drehung um die Normale (°)"** dreht ihn zusätzlich (wie die Endeffektor-Ausrichtung, nur „oben auf" statt „unter dem Flansch").
3. **An eine Kante schieben** (Tisch ohne Bohrung): Knopf **„An Kante schieben: Kante wählen"**, dann eine **Randkante der Standfläche** anklicken (Hover zeigt die jeweils nächste Kante als Linie) — die Basis rutscht **senkrecht zur Kante** auf den eingestellten **Abstand (mm)**, längs der Kante bleibt sie auf Höhe des Flächen-Mittelpunkts (beim rechteckigen Tisch also mittig an der Kante). Der Abstand misst zur **Basis-Mitte** (dem `robot_base_frame`-Ursprung), nicht zum Fußrand; das Abstandsfeld wirkt live. **„Zurück zur Flächenmitte"** hebt die Kantenwahl wieder auf. Die Kantenwahl braucht eine per Klick gewählte Standfläche (nach dem Wieder-Öffnen einer gespeicherten Workstation also einmal neu die Fläche anklicken); ein Bohrbild-Snap ersetzt sie — verschraubt wird nicht geschoben.
4. **Arbeitsfläche wählen:** Knopf **„Arbeitsfläche wählen"**, dann die Fläche anklicken — sie wird als Scheibe + Achsenkreuz markiert und als `work_surface_frame` gespeichert.
5. **Am Bohrbild ausrichten** (Auto-Snap): Knopf **„Roboter am Bohrbild ausrichten"** erkennt die **4 Basis-Bohrlöcher** des gewählten Roboters auf dem **gespeicherten** Mesh und schnappt die Basis darauf. Der reale Lochradius darf leicht vom Roboter-Bohrbild abweichen (Radius-Toleranz); passt kein Bild, erscheint nur eine Warnung — **kein Gate** (ADR-013). Weil der Core die abgelegte Mesh-Datei liest, erst nach dem **Speichern** aktiv.
6. **Speichern** übernimmt Mesh + Platzierung. Ein Roboterwechsel veraltet weiterhin **keine** Outputs (Seam zu #70): die Frames sind Stammdaten, die erst der Druckplan-Automatismus (#70) nutzt.

**Roboter-Bohrbild (`base_mount` in `robots/<name>.json`, read-only):** Für den Doosan M1013 **provisorisch** aus dem Installationshandbuch: 4 × Ø9 mm (M8) auf einem 150 × 150 mm-Quadrat (Lochkreis Ø212,1 mm), Montageebene z=0 — vor dem realen Bohren zu bestätigen.

**API:**

```json
POST http://localhost:8765/workstations                 // {..., "mesh_base64", "mesh_filename", "robot_base_frame", "work_surface_frame"}
POST http://localhost:8765/workstations/zelle_halle_a/detect-base-holes
{ "robot": "doosan_m1013" }
// → { "matched": true, "robot_base_frame": {...}, "detected_holes": [...], "warnings": [], "message": "…" }
```

Die Bohrbild-Erkennung rechnet der **Core** (`fgc.geometry.holes`, trimesh/shapely): oberste horizontale Fläche schneiden, Innen-Ringe als Löcher fitten, ein passendes N-Loch-Bild suchen, `robot_base_frame` vorschlagen (Antwort ist stets ein Befund, auch ohne Treffer — kein Gate). Die Platzierungs-Mathematik im Viewer (`mountBaseToSurface`) ist bit-gleich zum Core-Matcher.

### Platzierung: Gesamtwand-Vorschlag entfallen — Abschnitts-Platzierungen sind die Wahrheit (Issue #22/#23 → #134)

Der frühere **Job-Level-Platzierungsvorschlag für die ganze Wand** (Bewertungsmodus #22 mit „Wählen"/`selected_placement`, Optimalvorschlag #23/#80 mit den `vorschlag-1/2/3`-Optionen und dem cyan Gesamtwand-Basis-Marker in der Modellübersicht) ist mit **Issue #134 entfallen** (Design-Log 2026-07-09): nach der Zerlegung hatte er **keinen Konsumenten mehr** — Slicing, Simulation und Export laufen vollständig über die **Abschnitts-Platzierungen** des Zerlegungsplans (je Teil automatisch gesucht, #80/#132, bzw. frei übersteuert, #94), und eine „24 %"-Gesamtwand-Zeile neben sechs „100 %"-Abschnitten stiftete nur Verwirrung.

Was bleibt:

- **Schema/Altprojekte:** Die Druckjob-Felder `placements`, `selected_placement` und `placement_run` bleiben im Schema **lesbar** — Altprojekte mit gesetzten Feldern laden **byte-gleich**; eine erfasste `placements`-Liste speist weiterhin die Override-Referenz-Dropdowns der Teile-Palette (#94a). Sie werden nur nicht mehr befüllt oder angezeigt.
- **Core-Routen:** `POST …/placements`, `PUT …/placement-selection` und `POST …/placement-suggestion` bestehen unverändert (API-Nutzer/Altprojekte); der Viewer ruft sie nicht mehr.
- **Core-Module:** `fgc.placement.evaluate`/`suggest` sind unverändert die Bewertungs-/Suchmaschinerie — sie arbeiten jetzt ausschließlich **je Abschnitt** (Zerlegungsvorschlag #24/#132, freie Overrides #94, Advisors #65/#130) mit der #98-Sortierung und dem Grob-Kollisions-Check #131.
- **Singularitäts-Advisor:** ist am **Fokus-Abschnitt** verankert (s. Abschnitt „Singularitäts-Advisor", Issue #134).

### Aufstell-Toggle „Boden ↔ erhöht" (Reiter Druckplan, Issue #81, PRD B/#70)

Ein **Aufstell-Toggle** ersetzt im Reiter **Druckplan** die frühere manuelle Aufstell-Liste („+ Aufstellmöglichkeit" / „Bewerten"): der Nutzer sagt nur noch, **ob** der Roboter erhöht stehen darf, den Rest rechnet der Core.

- **„Roboter steht auf dem Boden"** (`floor`) — die Aufstellhöhe ist fest **0**.
- **„darf auch erhöht stehen"** (`elevated`) — der Druckplan-Automatismus darf aus den **realen Podesthöhen der gewählten Workstation** wählen (#77/#80).

Der Toggle gilt auch **ohne gewählte Workstation** (Altprojekt-Fallback, Issue #100): `floor` klemmt das Fallback-Höhenraster auf die Bodenhöhe — vorher suchte der Fallback trotz Boden-Modus Höhen bis 3000 mm und stellte den Roboter aufs Podest.

**Wirkung auf die Zerlegung:** Der Toggle begrenzt den Podesthöhen-Satz, den die Abschnittssuche (`fgc.decompose.propose`) nutzen darf. `floor` klemmt die Basis auf Bodenhöhe → die vertikale Reichweite je Aufstellung ist kleiner → der Core leitet **mehr, kleinere Höhenbänder** (Abschnitte) ab. `elevated` erlaubt das Podest → **weniger Bänder**. Die manuellen Schnitte (`from_cuts`, Schnittplan-Editing #25) bleiben davon unberührt — der Toggle steuert nur die automatische Platzierungssuche je Abschnitt.

**Bedienung:** Toggle umschalten → der Viewer persistiert den Zustand über `PUT /projects/{slug}/stand-mode` und stößt sofort die **Neubewertung** an (frischer Zerlegungsvorschlag; Schnitte + Ampeln werden neu gezeichnet — ADR-007, die UI rechnet nie selbst). Nach dem Neuladen des Projekts ist der Zustand wiederhergestellt.

**Additiv/rückwärtskompatibel:** Das Job-Feld `stand_mode` ist optional; **Altprojekte ohne das Feld laden byte-gleich** und verhalten sich wie `floor`. Der Toggle-Setter selbst veraltet **keine** Outputs (kein Revisions-Bump); die Neubewertung ist der nachfolgende Zerlegungslauf, der `cutplan` bumpt (der Toggle begrenzt nur den Podesthöhen-Satz, den die Abschnittssuche nutzen darf). Das bleibt so auch nach #83 — anders als der Workstation-Wechsel, der seit #83 direkt bumpt (der Toggle löst keinen Automatismus aus, er parametrisiert nur den nächsten `propose`-Lauf).

**API:**

```json
PUT http://localhost:8765/projects/mein-projekt/stand-mode
{ "stand_mode": "elevated", "job_id": "default" }
```

**Core:** dünner Setter `set_stand_mode_for_job` (einzige Schreibstelle `fgc.project`, ADR-016); `fgc.decompose.propose(wall, robot, tool, *, workstation, stand_mode)` und `from_cuts(...)` konsumieren den Toggle; `fgc.placement.suggest(..., stand_mode=…)` begrenzt den Podesthöhen-Satz (`floor` → `[0]`).

### Absolute Aufstellhöhen — Abschnitte an ihrer echten Höhenlage bewertet (Issue #132, ADR-022-Nachtrag)

Die **Aufstellhöhe** (`stand_height_mm`) einer Platzierung bedeutet überall **absolut über dem Boden** — Bodenniveau = Wandfuß (`z = 0`). Das gilt für die automatische Platzierungssuche je Abschnitt, die Ampel-Bewertung, freie Platzierungs-Overrides (#94) und die Anzeige. Seitliche Position und Abstand bleiben abschnittsrelativ (Mitte des Abschnitts / Wandfläche — zur Abstand-Semantik siehe den eigenen Abschnitt zu Issue #160/ADR-025).

**Was sich dadurch ändert (Design-Log 2026-07-09, Grill):**

- **Suche + Bewertung sehen die echte Höhenlage:** ein Abschnitt der zweiten oder dritten Reihe wird an seiner tatsächlichen Höhe (`z0…z1`) bewertet, nicht mehr als „Mini-Wand ab 0". Vorher stand die Basis im Boden-Modus auf einem **Phantom-Podest am Abschnittsfuß** — obere Reihen meldeten 100 % Erreichbarkeit, die ein M1013 (Reichweite 1300 mm) vom Boden nie erreicht.
- **Boden-Modus (`floor`)** heißt jetzt wirklich Boden: Höhensatz `[0]` absolut, für **alle** Reihen. Obere Reihen jenseits der Reichweite werden **ehrlich rot/teilerreichbar** — ein **Befund, kein Gate**: geschnitten und simuliert wird trotzdem, die Ampel sagt die Wahrheit.
- **Erhöht-Modus (`elevated`)** wählt aus dem **realen** Höhensatz der Workstation (diskrete Podesthöhen bzw. Hub-Bereich, z. B. mobile Workstation 0–600 mm) — absolut; ohne Workstation aus dem Fallback-Raster 0–3000 mm.
- **Je Höhenreihe eine eigene Platzierung:** der Zerlegungsvorschlag sucht die beste Basis je Reihe (untere Reihe ggf. Boden, obere Reihe Podesthöhe) statt einer identischen Pseudo-Platzierung für alle Teile.
- **Simulation/Export:** die Umrechnung ins abschnitts-lokale Sim-Frame (`lokal = absolut − z0`, negativ erlaubt — die Basis darf unterhalb des Abschnittsfußes stehen) passiert an genau **einer** Naht in der Setup-Komposition; der 3D-Replay verankert den Arm damit auf der echten Höhe.
- **Rückwärtskompatibel:** für die unterste Reihe (`z0 = 0`) ist absolut ≡ lokal — Platzierung, Bewertung und Trajektorie sind bit-identisch zu vorher. Altprojekte (durchweg `stand_height 0`) laden byte-gleich und bedeuten fortan korrekt „Boden". Zerlegungsart **„Modul"** ist nicht betroffen: dort bleibt die Höhe relativ zur Arbeitsfläche der Workstation (ADR-022).
- **Viewer zieht nach (Issue #133):** Basis-Marker und Fokus-Roboter stehen auf der echten Basis-Höhe `Boden + stand_height` (statt am Abschnittsfuß zu schweben), bei Aufstellhöhe > 0 mit Podest-Sockel vom Boden bis zur Basis; die Anzeige heißt überall **„Aufstellhöhe ü. Boden"** — Details im Abschnitt „Platzierung sichtbar" (#93).

**Core:** `fgc.placement.WallSurface` trägt ein `z_offset_mm` (Default 0 = Wandfuß), `Section.as_surface` setzt es auf `z0_mm`; die Umrechnungsnaht ist `fgc.pipeline.actions._planned_setup(..., z_offset_mm=…)`. Schema-Beschreibungen (`decompose`/`project`) präzisiert, keine Strukturänderung.

### Abstand vor der Wand — `standoff_mm` misst ab der Wandfläche (Issue #160, ADR-025)

Der **Abstand** einer Platzierung (`standoff_mm`, Formularfeld „Abstand vor der Wand (mm)") ist der **freie Abstand der Roboterbasis vor der nächstliegenden Wand-/Modulfläche** — das Zollstock-Maß am Aufstellort. Simulation, Kollisionsurteil, Platzierungssuche und alle Marker rechnen mit genau diesem Maß; die Umrechnung in die Wandsystem-Koordinate (`y = Dicke/2 + Abstand`) passiert an **einer** Naht (`fgc.placement.base_position_in_wall`).

- **Vorher** las der Core den Wert als Distanz zur Wand-**Mittelebene**, die Anzeige aber als Distanz zur Fläche — bei dicken Wänden stand der Roboter real eine halbe Wanddicke näher, als die Slicing-Ansicht zeigte (Auslöser: Denkmal, 510 mm dick, sichtbare Kollision im Replay trotz „Abstand 535").
- **Sicherheitsabstand ehrlich:** der `placement_check`-Befund (`below_min_distance`) vergleicht jetzt echten Freiraum gegen `safety_min_distance_mm` — vorher war der Vergleich um die halbe Wanddicke zu optimistisch. Auch die Grobkollisions-Wandbox (`fgc.collision.coarse`) liegt jetzt korrekt um die Mittelebene (±Dicke/2).
- **Bestandsprojekte:** gespeicherte Abstandswerte werden **reinterpretiert** (gleicher Zahlenwert = mehr Freiraum, sichere Richtung) — nach dem Update Zerlegung/Platzierung einmal **neu bewerten**; wer unter der alten Lesart künstlich große Werte eintrug, trägt jetzt das gewünschte echte Maß ein.
- **Modul-Druckort unverändert:** die aus den Workstation-Frames abgeleitete feste Modul-Platzierung ergibt dieselbe physische Pose wie bisher (Frame-Distanz − halbe Moduldicke).

### Effektive Platzierung — eine Lesequelle für alle Platzierungs-Anzeigen (Issue #171)

Alle Stellen im Viewer, die eine **Platzierung zeigen** — Basis-Marker aller Teile, der Fokus-Roboter am gewählten Teil, die **„Basis · Podest"**-Chips, die Live-Vorschau **„Vorbereiten"** (Bahn **und** atmender Sicherheitsabstand), der **Gesamtablauf** (Arm **und** Basis-Marker) und die **Modul-Karten** — leiten die Lage jetzt aus **einer** reinen Funktion ab (`viewer/src/ui/effective-placement.ts`): der **automatisch gesuchten Zerlegungs-Platzierung**, feldweise übersteuert durch die **freien Platzierungs-Overrides** (#94) des Teils. Am **Druckort** gewinnt zusätzlich die Lage des **frischen Simulationslaufs** über die Zerlegungs-Lage (wie schon der Replay, #161).

Sichtbar wird das an drei Ehrlichkeits-Fixes: (1) nach einem angewandten Platzierungs-Hebel (Kollisions-/Singularitäts-Advisor) stehen **Arm und Basis-Marker** im Gesamtablauf **nicht mehr auseinander**; (2) die **statische Druckort-Ansicht** zeigt dieselbe Lage wie der Player — der Soll-Kasten **springt beim Replay-Start nicht mehr um**, wenn ein frischer Lauf existiert; (3) senkt ein Override den Abstand unter den Workstation-Mindestabstand, wird die **Vorbereiten-Vorschau nicht-grün**. Alles bleibt **reine Ableitung** (kein neuer Zustand, ADR-007); die Einquelligkeit ist per Import-Regel-Test strukturell abgesichert (neuer Direktleser ⇒ roter Test).

### Zerlegungsvorschlag — Wand in erreichbare Abschnitte teilen (Reiter Druckplan, Issue #24)

Reicht keine einzelne Platzierung für 100 % der Wand (z. B. eine überhohe oder überlange Wand), schlägt der Core im Reiter **Druckplan** eine **Zerlegung** in **Abschnitte** vor (Zerlegungsart „Abschnitt", in place — gedruckt an der Endposition, Reihenfolge unten → oben, je Abschnitt eine eigene Platzierung, Anschlussfuge = Druckunterbrechung). Die GUI fragt die **Zerlegungsart** ab: „Abschnitte (in place)" ist aktiv; „Module (zum Montieren)" ist sichtbar, aber als „später" gekennzeichnet (braucht Fügegeometrie).

Bedienung:

1. Voraussetzung: Druckjob mit Wand (Reiter Projekt) und Roboter (Reiter Roboter); Endeffektor optional (Default: Düse am Flansch).
2. Zerlegungsart wählen (Default „Abschnitte in place"), dann **„Zerlegungsvorschlag"**.
3. Der Core legt wandparallele Schnittebenen — **horizontal** (Höhenstufen) bei einer überhohen Wand, **vertikal** (Längenteilung) bei einer überlangen — sodass jeder Abschnitt von seiner Platzierung aus (angestrebt) 100 % erreichbar ist.
4. **3D-Ansicht (Reiter Projekt):** die Schnittebenen erscheinen als semi-transparente amberfarbene Flächen in der Modellübersicht. Sie hängen an der **echten Wand-Pose** (Issue #99): der Viewer leitet das Wand-System per 2D-PCA aus den Wand-Vertices ab — dieselbe Konvention wie der Core (`_wall_local_mesh`) — statt der früheren achsparallelen Bounding-Box-Näherung, die bei Wänden schräg zu den Weltachsen schiefe, zu lange Ebenen zeichnete. Dasselbe gilt für Abschnitts-Quader (#84), Platzierungs-Marker (#22/#93) und die Live-Vorschau (#85); auch die Drag-Achsen der Schnittebenen (#25) folgen der echten Wandachse.
5. **Abschnittsliste (Reiter Druckplan):** je Abschnitt eine **Ampel** (grün = voll erreichbar, rot = nicht), die Höhen-/Längengrenzen (z/x) und die zugeordnete Platzierung (Podest, seitlich, Abstand). Die Ampel ist ein **Befund, kein Gate** — ein roter Abschnitt blockiert den Plan nicht.

Der Vorschlag ist der Startpunkt: das **Editieren** des Schnittplans (Ebenen verschieben/hinzufügen, neu bewerten) ist implementiert — siehe „Schnittplan-Editing" (Issue #25); das Slicen/Simulieren je Abschnitt siehe Reiter Simulation (Issue #26).

**Algorithmus:** Die Startteilung schätzt der Roboter-Arbeitsraum (`max_print_*`); verfeinert wird entlang der *tatsächlich* blockierenden Achse — getestet wird, ob eine zusätzliche Längen- **oder** Höhenteilung den erreichbaren Anteil stärker hebt (die stärkere gewinnt). So bleibt der Vorschlag für eine überhohe Wand horizontal, für eine überlange vertikal. Die Reichweite je Abschnitt kommt ausschließlich aus der bestehenden Platzierungssuche (`fgc.placement.suggest`/`evaluate`, Issue #22/#23) — nichts dupliziert. Deterministisch: gleiche Wand + gleicher Roboter → gleicher Schnittplan.

**Artefakte (ADR-004/016):** Die Zerlegung ist ein regulärer, provenienz-gestempelter Lauf (`runs/<stamp>_decompose_<slug>/decompose.json`, Schema `schemas/decompose.schema.json`) mit Schnittebenen, Abschnitten, Platzierungen und Ampeln. Der Druckjob trägt nur die **Eingaben** — Zerlegungsart (`decomposition_kind`), Schnittebenen (`cuts`) — und den **Verweis** auf den Lauf (`decompose_run`), nie die Ampeln/Meshes.

**Core-Modul `fgc.decompose` (deep module):**

- `propose(wall, robot, tool)` → `DecompositionPlan` (Schnittebenen + Paare Abschnitt/Platzierung, Reihenfolge unten → oben)
- `apply(wall_mesh, plan)` → wasserdichte Abschnitts-Meshes (trimesh `slice_plane` + shapely-Deckelung; Volumensumme ≈ Wandvolumen)
- `evaluate(plan, robot, tool)` → Ampel je Abschnitt (erreichbar/nicht — Befund, kein Gate)

„Segment" ist bewusst vermieden (im Slicer vergeben: `segment_id`); die Einheit heißt **Abschnitt**.

**API:**

```json
POST http://localhost:8765/projects/mein-projekt/decomposition
{ "job_id": "default", "decomposition_kind": "abschnitt" }
```

Antwort: `run_dir` (Zerlegungslauf), `cuts`, `sections` (je Abschnitt Geometrie + Platzierung + Ampel-`status`) und `print_jobs`. `decomposition_kind: "modul"` rechnet seit #90/#95 die Modul-Zerlegung an der Workstation (siehe „Modul-Zerlegung"); ohne gewählte Workstation antwortet die Route mit 422 + freundlichem Hinweis.

### Schnittplan-Editing — Schnitte anpassen, Platzierung übersteuern, neu bewerten (Reiter Druckplan, Issue #25)

Der Zerlegungsvorschlag (Issue #24) ist der **Startpunkt**, nicht das letzte Wort: Im Reiter **Druckplan** lässt sich der Schnittplan von Hand anpassen — der Kern der „selbst noch was antasten"-Anforderung.

- **Schnittebene verschieben — per Drag *und* per Zahlenfeld.** In der 3D-Übersicht wird eine Schnittebene mit der Maus entlang ihrer Achse gezogen (die Orbit-Steuerung pausiert dabei); alternativ trägt man die Position ins Zahlenfeld ein. Beide schreiben in **denselben** Schnittplan-Zustand (`ui/cutplan-state.ts`, dieselbe `moveCut`-Funktion) — Drag zum Explorieren, Zahl zum Festzurren; sie bleiben immer synchron, kein Ad-hoc-Abgleich.
- **Schnitte hinzufügen/entfernen** (horizontal = Höhenstufe, vertikal = Längenteilung) und optionaler **Fugen-Versatz**: versetzt die vertikalen Stoßfugen zwischen benachbarten Höhenlagen gegeneinander (kein durchgehender Vertikalspalt).
- **Platzierung je Abschnitt übersteuern:** Statt der automatisch gesuchten Platzierung lässt sich jedem Abschnitt eine Option aus der Platzierungsliste (Bewertungsmodus, Issue #22) zuweisen.
- **Neubewertung läuft immer über den Core (ADR-007):** Nach jeder Änderung gilt die Ampel als **ungeprüft** (dirty) — sie zeigt nie einen veralteten Stand als aktuell. Ein **„Prüfen"-Button** (zusätzlich debounced nach jeder Änderung) schickt Schnitte + Fugen-Versatz + Overrides an den Core (`fgc.decompose.from_cuts` + `evaluate`); erst die Antwort färbt die Ampel grün/rot. Die UI rechnet nie selbst.
- **Persistiert im Druckjob:** Der angepasste Schnittplan (Schnitte, Fugen-Versatz, Overrides) landet über denselben Endpoint wie der Vorschlag (`POST /projects/{slug}/decomposition` **mit** `cuts`) als provenienz-gestempelter Lauf; der Druckjob trägt nur die Eingaben + den Lauf-Verweis (ADR-016). Nach Neuladen wiederhergestellt.

Die Schnittplan-Zustandslogik (Schnitt hinzufügen/verschieben/entfernen, Override, Dirty-Zustand) ist als **reine TypeScript-Funktionen** von three.js getrennt (`ui/cutplan-state.ts`) und mit vitest getestet.

### Prozessparameter — Basis-Slice-Parameter am Druckjob (Reiter Druckplan, Issue #59)

Der Druckjob trägt einen optionalen **Prozessparameter-Block** (`process_params`), der zur **Wahrheitsquelle** für das Slicen wird. Scheibe 2 füllt seine erste Gruppe, `slice`: **Schichthöhe**, **Strangbreite** und **Schalenzahl**.

- **Panel im Reiter Druckplan** (unter „Bewertung"): drei Felder + **„Speichern"**. Gespeicherte Werte schreibt der Core über `PUT /projects/{slug}/process-params` in den `process_params.slice`-Block des Druckjobs (`fgc.project` = **einzige, schema-validierte Schreibstelle**, ADR-016). Nach Neuladen wird das Formular aus dem Job wiederhergestellt.
- **Leer = Default:** Ein leer gelassenes Feld ist *nicht gesetzt* — der Core fällt für dieses Feld auf die **Prozessfenster-Karte / Code-Defaults** zurück. Ein komplett leeres Formular entfernt den Block wieder (voll rückwärtskompatibel; Altprojekte ohne Block laden unverändert).
- **Wirkung beim Slicen:** `simulate_section` liest die Slice-Basisparameter aus dem Druckjob (statt nur aus der Materialkarte); explizite Job-Werte überschreiben die Karte, ungesetzte fallen darauf zurück.
- **veraltet-Markierung (ADR-017):** Eine Änderung an `process_params` bumpt einen eigenen **Revisions-Eingabezähler** (`process`) → **Zerlegung, Simulation und Export veralten** (sichtbar markiert, nichts gelöscht). Die Ableitung „ist X veraltet?" bleibt eine reine Funktion mit Python↔TS-Parität (`fgc.project.output_status` ↔ `ui/staleness.ts`).

Diese Gruppe ist die **Rail**, auf die spätere Scheiben (Orientierung, Bewegung) ihre eigenen Parametergruppen im selben `process_params`-Block aufsetzen. Die Formular↔Job-Serialisierung liegt als **reine TypeScript-Funktionen** (`ui/process-params-state.ts`) und ist mit vitest getestet.

### Fortgeschritten — Druck-/Travel-Geschwindigkeit + io editierbar (Reiter Druckplan, Issue #60)

Unter dem Prozessparameter-Panel liegt ein **einklappbarer „Fortgeschritten"-Bereich** (schlichtes Aufklapp-Muster, kein `<details>`): ein Umschalt-Knopf (`▸`/`▾ Fortgeschritten`) blendet vier Felder auf. Sie machen bisher **unkonfigurierbare, aber existierende** Slice-Werte editierbar:

- **Druck-Geschwindigkeit (`v_print_mm_s`)** und **Travel-Geschwindigkeit (`v_travel_mm_s`)** — die Bahngeschwindigkeit je Zielart (mm/s).
- **io Druck (`io_print`)** und **io Travel (`io_travel`)** — der io-Wert je Zielart. Als **ein Skalar** eingegeben, den der Core beim Slicen **gleichförmig auf alle io-Kanäle** (v0: `pump_a`/`pump_b`) ausdehnt; per-Kanal-Differenzierung gehört in die spätere Materialphase.

Alle vier gehören zur `slice`-Gruppe und fließen über denselben Weg wie die Basisparameter: **`PUT /projects/{slug}/process-params` → `process_params.slice`** → beim **Slicen** (`simulate_section`) landen sie je Toolpath-Ziel als `v_mm_s` bzw. `io`, wirken damit durch **Slice → Simulation → Export** und werden **nach Neuladen wiederhergestellt**. Leer = Karten-/Code-Default (v_print 100 / v_travel 250 mm/s, io 0,5 / 0,0); Änderungen **veralten** Zerlegung/Simulation/Export (ADR-017). Der **reine Aufklapp-Zustand** liegt DOM-frei in `ui/collapsible-state.ts` (vitest); die Feld-Serialisierung erweitert `ui/process-params-state.ts`.

**Reiter Projekt vom Simulations-Rückweg gelöst:** Das **Standalone-Reslice** im Reiter Projekt (`?run=`-Abspieler, Issue #9) ist jetzt auf den **Abspieler-Modus ohne Projekt** beschränkt. Im Projektfluss fließt der Prozess **vorwärts** — Slice-Parameter setzt man im Reiter Druckplan, gesliced wird je Abschnitt im Reiter Simulation; der Reiter Projekt dient dann nur der Modellübersicht + Wandübernahme, ohne konkurrierendes Reslice und ohne Rücksprung.

### Anstellwinkel — bahn-relativer Lead-/Kipp-Winkel der Düse (Reiter Druckplan, Issue #61)

Die zweite Gruppe des Prozessparameter-Blocks, `orientation`, stellt die Düse **bahn-relativ** an: ein **Lead-/Lag-Winkel** (in/gegen Fahrtrichtung) und ein **Kipp-Winkel** (zur Wand-Außenseite). Beide werden im Panel **in Grad** eingetragen (zwei zusätzliche Felder „Lead/Lag (°)" und „Kipp (°)").

- **Eine geteilte Orientierungsquelle:** Die frühere Konstante `NOZZLE_DOWN_QUAT` ist jetzt die reine Funktion `fgc.domain.orientation.nozzle_quat(tangente, lead, kipp)`. **Slicer und Erreichbarkeitsbewertung rufen dieselbe Funktion** — der Slicer mit der echten Bahntangente (aufeinanderfolgende Ringpunkte) je Ziel, `placement.evaluate` mit seiner angenommenen horizontalen Tangente entlang der Wandlänge. Damit können **Erreichbarkeit (Ampel) und Simulation nicht auseinanderdriften** (Regressionsschutz zu Issue #51).
- **Vorzeichenkonvention:** `+Lead` kippt die Düse **in Fahrtrichtung**, `+Kipp` **zur Wand-Außenseite** (aus dem CCW-orientierten Druckring eindeutig: die Außenseite ist die rechte Seite der Fahrtrichtung).
- **Nullpunkt `0/0` = heutiges Verhalten:** Ohne gesetzten Winkel (leer bzw. 0/0) zeigt die Düse **senkrecht von oben** — bit-identisch zum bisherigen Toolpath. Weiche Grenzen: die Werte werden **nicht gekappt** (Befund/Warnung statt Sperre).
- **Wirkung auf die Ampel:** Ein gesetzter **Kipp** verändert die Flansch-Ziel-Orientierung und damit **nachweisbar die Erreichbarkeits-Bewertung** — die Ampel je Abschnitt (und der Optimalvorschlag/Bewertungsmodus) rechnen mit der angestellten Düse.
- **Persistenz + veraltet-Markierung:** „Speichern" schreibt Lead/Kipp (Grad) über `PUT /projects/{slug}/process-params` in den `process_params.orientation`-Block des Druckjobs und bumpt — wie die Slice-Gruppe — den `process`-Revisionszähler → Zerlegung/Simulation/Export veralten sichtbar. Im **Arm-Replay** steht die Düse dann entsprechend angestellt.

### Pro-Abschnitts-Overrides — die Gradierungs-Ebene (Reiter Druckplan, Issue #82)

Über den globalen Prozessparametern liegt die **Gradierungs-Ebene**: **jeder Abschnitt** darf **jeden** Parameter individuell übersteuern; ungesetzte Felder **erben** den globalen Wert. Unter dem globalen Panel erscheint je Abschnitt (nach der Zerlegung) ein Formular mit denselben Feldern — Slice (Schichthöhe, Strangbreite, Schalen, Druck-/Travel-Geschwindigkeit, io) **und** Orientierung (Lead/Kipp).

- **Sparse Auflösung (Core, `fgc.domain.process_params`):** Die reine Funktion `resolve_section_params(global, override)` mischt „global + Abschnitts-Override → effektiv" **feldweise** — gesetztes Abschnittsfeld gewinnt, sonst erbt es global, ist ein Feld nirgends gesetzt fällt es weiter auf die Prozessfenster-Karte/Code-Defaults. Dieselbe Semantik wie `job_slice_overrides` (nur gesetzte Felder übersteuern). `effective_section_params(job, section_id)` ist der bequeme Durchstich je Abschnitt.
- **Py↔TS-Parität:** Die TS-Zwillingsfunktion `resolveSectionParams` (`viewer/src/ui/section-params-state.ts`) rechnet **bit-gleich**; bewiesen über **geteilte Golden-Fälle** (`viewer/src/ui/section-params.golden.json`, erzeugt von `viewer/scripts/gen_goldens.py`, Paar `section-params` im Paritäts-Manifest `fgc.parity`), die pytest **und** vitest gegen ihre jeweilige Auflösung prüfen.
- **Additives Schema:** Der optionale Block `process_params.sections` bildet `section_id → {slice, orientation}` (sparse) ab. **Altprojekte ohne den Block laden byte-gleich** — jeder Abschnitt erbt dann komplett global.
- **UI (geerbt vs. übersteuert sichtbar):** Ein **leeres** Feld erbt global — der geerbte (effektive) Wert steht als **Platzhalter** („erbt 8" bzw. „erbt (Karte/Default)"). Ein **gefülltes** Feld ist ein Override und wird **hervorgehoben** (Akzentrahmen, `.section-param-override`). Persistiert wird `process_params.sections` über dieselbe Route `PUT /projects/{slug}/process-params` (Feld `sections`); nach dem Neuladen ist genau der Stand wiederhergestellt. Die globalen Werte werden dabei unverändert mitgesendet (getrennt speicherbar von der globalen Gruppe). *Seit Issue #92 wohnt diese Bedienung im **Gilt-für-Umschalter** (s. u.) — die frühere separate Formular-Sektion je Abschnitt ist darin aufgegangen.*
- **Overrides wirken in Simulation, Prüf-Tür und Export (Issue #188):** Die Abschnitts-Overrides der Gruppen **Slice** und **Orientierung** werden nicht nur persistiert und in der Live-Vorschau gezeigt, sondern **wirklich gerechnet**: die eine Kern-Tür (`fgc.pipeline.sectionsim.slice_and_simulate_section`, seit #189 als benanntes Modul) slict und orientiert jeden Abschnitt mit seinen **effektiven** Werten (`section_slice_overrides`/`section_orientation`, dieselbe Auflösung wie `effective_section_params`). Eine abschnittsweise geänderte Schichthöhe ändert also `n_layers` des Abschnitts-Laufs, ein Kipp-Override kippt **nur** die Bahn dieses Abschnitts — und weil der **DRL-Export** den Simulations-Lauf liest und **Prüf-Tür/Kollisions-Advisor/Clearance-Check** dieselbe Tür nutzen, gilt die Gradierung überall. Abschnitte **ohne** Override rechnen byte-gleich wie zuvor (Altprojekte unverändert).

### Feingranulare Veraltung — Pro-Abschnitts-Revisionen (Reiter Druckplan/Simulation/Export, Issue #83)

Ein Abschnitts-Override (Gradierungs-Ebene, #82) soll **nicht den ganzen Job veralten**, sondern nur den betroffenen Abschnitt. Dafür trägt der Druckjob neben den Job-weiten Revisionsständen (ADR-017) eine **Pro-Abschnitts-Revisionsebene** (ADR-017-Nachtrag).

- **Nur dieser Abschnitt (Core, `fgc.project.revisions`):** Setzt der Nutzer einen Abschnitts-Override (`process_params.sections[id]`), bumpt der Core **nur** den Zähler dieses Abschnitts (`revisions.section_inputs[id]`) → **nur** dessen Simulation/Export veraltet, die Nachbarn bleiben **aktuell**. Beim Neu-Simulieren/-Exportieren eines Abschnitts wird sein eigener Schnappschuss (`revisions.section_outputs[id]`) aufgefrischt — abschnittsweise, nicht job-weit.
- **Strukturell/global veraltet weiterhin alles:** Schnitte (`cutplan`), **globale** Slice-/Orientierungs-Params (`process`), **Roboter** (`robot`) und **Workstation** (`workstation`) bumpen die **Job-Revision** → **alle** Abschnitte veralten. (Der Workstation-Wechsel veraltet seit #80–82 alle Abschnitte — Ablösung des ursprünglichen #77-Seams, s. u.)
- **Py↔TS-Parität:** Die Ableitung „ist Abschnitt X veraltet?" bleibt eine **reine Funktion** — Core `section_output_status(job, id)` ↔ TS `sectionStageStatus(revisions, id, stage)` (`viewer/src/ui/staleness.ts`), bewiesen über **geteilte Golden-Fälle** (`viewer/src/ui/staleness-section.golden.json`, erzeugt von `viewer/scripts/gen_goldens.py`, Paar `staleness-section` im Paritäts-Manifest `fgc.parity`), die pytest **und** vitest prüfen.
- **Additiv/rückwärtskompatibel:** Die Ebene (`section_inputs`/`section_outputs`) entsteht **lazy** mit der ersten Abschnitts-Änderung/-Simulation. **Altprojekte ohne die Ebene verhalten sich wie bisher** (Ganzjob-Veraltung).

### Fokus-Abschnitt — anklicken + weiche Kamera-Einfassung (Reiter Druckplan, Issue #84, PRD B/#70)

Im Reiter **Druckplan** lässt sich ein Abschnitt im geteilten 3D-Feld als **Fokus** wählen — die Grundlage für die spätere Live-Vorschau (S6) und den Simulieren-Modus (S7).

- **Klickbare Abschnitte:** Je Abschnitt liegt ein (normal unsichtbarer, aber pickbarer) Quader über der Wand. Ein **Klick** darauf nimmt den Abschnitt in den **Fokus**; ein erneuter Klick auf denselben Abschnitt gibt den Fokus wieder frei (Toggle). Alternativ fokussiert ein Klick auf den Abschnittsnamen in der Liste denselben Abschnitt — beide Wege teilen dieselbe Auswahl.
- **Kontext-Hervorhebung:** Der Fokus-Quader wird sichtbar getönt und die Zeile in der Abschnittsliste markiert; die **anderen Abschnitte bleiben unsichtbar**, sodass die **ganze Wand samt Schnittfugen sichtbar bleibt** — der Bezug zu den Nachbarn geht nicht verloren.
- **Weiche Kamera-Einfassung:** Die Kamera fasst den Fokus mit einer **sanften Animation** (eased Tween, kein harter Sprung) ein — der Orbit-Punkt wandert auf den Abschnitts-Mittelpunkt, der Abstand bleibt aber groß genug, dass die ganze Wand im Bild bleibt.
- **Sauberer Ausgangszustand:** Kein Fokus ist der Default; ein einzelner Abschnitt und Altpläne verhalten sich unverändert (abwärtskompatibel). Ein neuer Zerlegungsvorschlag oder eine Neubewertung, die den Fokus-Abschnitt entfernt, lässt den Fokus sauber auf „kein Fokus" zurückfallen.

Reine Darstellung/Interaktion (ADR-007): Die **Fokus-Auswahllogik** liegt als reine, DOM- und three.js-freie Funktionen in `viewer/src/ui/focus-state.ts` (vitest-getestet — setzen/togglen/kein Fokus/Abgleich mit vorhandenen Abschnitten); die Abschnitts-Quader (`viewer/src/render/sections.ts`) und die Kamera-Einfassung sind reine Darstellung, vom Fokus-Zustand getrieben. Kamera/Animation bleiben **visueller Smoke** (`viewer/scripts/ui_smoke.mjs`), kein Pixel-Test.

### Live-Vorschau „Vorbereiten" — Düsen-Schablone + sofortige Bahnen + atmender Sicherheitsabstand (Reiter Druckplan, Issue #85, PRD B/#70)

Ist ein Abschnitt im **Fokus** (#84), gibt der Modus **Vorbereiten** beim Reglerziehen eine **sofortige, billige, IK-freie** Rückkopplung im geteilten 3D-Feld — ohne den vollen Arm zu simulieren:

- **Düsen-/Werkzeug-Schablone:** Ein Düsen-Stummel gleitet entlang der frisch gesliceten Bahn des Fokus-Abschnitts. Die **Pose je Bahnpunkt** kommt **vorwärts** aus der **einen geteilten Orientierungsquelle** `nozzle_quat` (#61) — im echten Lead/Kipp, **keine eigene Formel**. Wulstdicke = Strangbreite, Stapelung = Schichthöhe. Weil Schablone **und** voller Arm-Lauf dieselbe Rotation ziehen, können sie **nicht auseinanderdriften** (Regressionsschutz #51/#58).
- **Sofortige Bahnen:** Jede Feld-Eingabe an den globalen Prozessparametern **oder** am Pro-Abschnitts-Override (#82) sliced die Bahn des Fokus-Abschnitts **sofort** neu (aus den **live**, noch ungespeicherten Werten) — ein billiger Vorschau-Slicer erzeugt gestapelte, CCW-orientierte Umfangsringe (keine IK, kein Core-Aufruf). Die effektiven Params (global ⊕ Override) kommen aus derselben `resolveSectionParams`-Auflösung wie #82.
- **Atmender Sicherheitsabstand:** Zwischen Roboterbasis und Wandfront lebt ein Puffer aus Basislage (`standoff`, #80) + `safety_min_distance_mm` der Workstation (#77). Er **„atmet" sichtbar** (Puls zwischen 0,8·Mindestabstand und Mindestabstand) und wird **grün**, solange die Marge eingehalten ist, **rot** bei Unterschreitung — so wird die nackte Zahl ohne Erklärung verständlich und reagiert auf die Abstands-Optimierung.

Pure/DOM-Split (ADR-007): Die **reine Geometrie** liegt DOM- und renderer-frei in `viewer/src/ui/nozzle-quat.ts` (TS-Zwilling von Core `nozzle_quat`, Py↔TS-Parität über die geteilten Golden `nozzle-quat.golden.json`), `viewer/src/ui/nozzle-schablone.ts` (Schablonen-Posen, Golden `nozzle-schablone.golden.json` — Quaternionen je Bahnpunkt **aus dem Core** erzeugt, `viewer/scripts/gen_goldens.py`), `viewer/src/ui/preview-slice.ts` (Vorschau-Bahn) und `viewer/src/ui/safety-clearance.ts` (Puffer-Zustand) — alle vitest-getestet **ohne** Renderer/IK. Die three.js-Darstellung + Animation liegt getrennt in `viewer/src/render/schablone.ts`, `viewer/src/render/clearance.ts` und der Steuerung `viewer/src/render/prepare-preview.ts`; das Gleiten/Atmen bleibt **visueller Smoke** (`ui_smoke.mjs`, `__prepareDebug`).

### Modus-Fusion „Vorbereiten↔Simulieren" — der Reiter Simulation geht auf (Reiter Druckplan, Issue #86, PRD B/#70)

> **Überholt durch #108 (UI-Redesign Scheibe 6, s. o. „Simulations-Dock statt Modus-Umschalter"):** Der hier beschriebene **Modus-Umschalter „Vorbereiten↔Simulieren"** ist ersatzlos entfallen — Simulieren ist jetzt ein **Dock** am Fuß des Viewports, Schnittplan-Bearbeitung und Simulation koexistieren ohne Modus (Veraltet-Markierung = Schutz). Der Reiter **Simulation** bleibt entfernt; die zwei Simulieren-Knöpfe und der Trajektorien-Abspieler leben unverändert weiter (nur im Dock). Der folgende Abschnitt beschreibt den historischen #86-Stand.

Die OrcaSlicer-artige Fusion schließt PRD B ab: ein **geteiltes 3D-Feld mit zwei Modi**, der frühere separate Reiter **Simulation** ist entfernt. Planen und Sehen liegen jetzt an **einem** Ort — im Reiter **Druckplan**.

- **Moduswechsel Vorbereiten↔Simulieren:** Ein Umschalter oben im Reiter Druckplan. **Vorbereiten** = einstellen mit sofortiger Live-Vorschau am Fokus-Abschnitt (S6/#85). Klick auf **Simulieren** blendet den Simulieren-Bereich ein und zeigt den **vollen, möglichst echten Arm-Lauf** (slice + IK + Timing) über die **bestehenden** Simulier-Aktionen (ADR-007 — **keine neue Kinematik**). Der Wechsel ist **bewusst** (erst einstellen, dann Vorschau), damit nicht versehentlich mit **veralteten** Werten simuliert wird; im Simulieren-Modus ruht die billige Live-Vorschau.
- **Zwei Simulieren-Knöpfe:** Standard **„Fokus-Abschnitt simulieren"** sliced + simuliert den fokussierten Abschnitt (#84) mit den **aktuellen** Werten (frischer Lauf → nie veraltet) und spielt ihn **sofort** als vollen Arm-Lauf ab. Zweiter Knopf **„Ganze Wand (unten → oben)"** spielt alle Abschnitte in Druckreihenfolge über die **Sequenz aus #27** (mit sichtbarem Umbau-Schritt). Bei genau **einem** Abschnitt genügt dieser eine auch ohne expliziten Fokus (abwärtskompatibel, US 24).
- **Trajektorien-Abspieler im Druckplan:** Der Player (Play/Scrub, wachsender Strang, Gesamtablauf-Sequenz — #14/#18/#27/#48) ist mitsamt „← Zurück zur Übersicht" in den Reiter Druckplan gezogen. Es bleibt **dieselbe** Player-Instanz und dasselbe Verhalten; nur der Wohnort wechselt.
- **Feingranulare Veraltung sichtbar (#83):** Nur die **tatsächlich** veralteten Abschnitte tragen im Simulieren-Bereich ein **„veraltet"-Badge**; ein simulierter, unveränderter Abschnitt bleibt **grün**.

Pure/DOM-Split (ADR-007): Die reine Modus-Logik (Modus-Prädikate, das Simulier-Ziel `focusTarget`, die veralteten Abschnitte `staleSimSections`) liegt renderer-/DOM-frei in `viewer/src/ui/druckplan-mode.ts` (vitest). Der DOM-Umschalter steht in `viewer/src/ui/plan-mode-panel.ts`; der Simulieren-Bereich ist der absorbierte `viewer/src/ui/simulation.ts`. Der DOM-Vertrag (Player + Simulieren-Bereich im Druckplan, Reiter Simulation entfernt) ist in `shell-structure.test.ts` festgezurrt, das Umschalten + der entfernte Reiter im `ui_smoke.mjs`.

### Druckplan-Rubriken „Zerlegung & Platzierung" / „Slicing" (Reiter Druckplan, Issue #89, PRD #88)

Der Druckplan-Aside war eine lange Stapelung aus zwölf Sektionen. Sie ist in **zwei Rubriken** geordnet — umgeschaltet wird wie in der Bibliothek über zwei Tabs, **ausschließlich** über das `.hidden`-Attribut (kein `display`-Umschalten, Schutz vor dem toten-Reiter-Bug #56). **Reine Neuordnung — keine neue Funktionalität; alle bisherigen Bedienpfade bleiben erreichbar.**

- **Modus-Schalter bleibt panel-global:** Der Umschalter **Vorbereiten↔Simulieren** (#86) steht unverändert **über** den Rubriken; der Simulieren-Bereich bleibt unangetastet und wird weiter vom Modus (nicht von der Rubrik) ein-/ausgeblendet.
- **Rubrik „Zerlegung & Platzierung":** Aufstellung (Boden↔erhöht + Optimalvorschlag) samt Bewertung, **Zerlegungsvorschlag** (Zerlegungsart + Vorschlag) und **Schnittplan** (Schnitte setzen/verschieben/entfernen, Fugen-Versatz, „Prüfen").
- **Rubrik „Slicing":** **Prozessparameter** (Schichthöhe/Strangbreite/Schalen), **Anstellwinkel** (Lead/Kipp), **Fortgeschritten** (Geschwindigkeiten/io) und der **Singularitäts-Advisor** (#65). Die Gradierungs-Ebene (#82) bedient sich hier seit #92 über den **Gilt-für-Umschalter** (s. u.) statt über eine eigene Sektion.
- **Immer ausgeklappt, einzig „Fortgeschritten" einklappbar:** Innerhalb einer Rubrik stehen alle globalen Blöcke offen; die frühere zwölfteilige Stapelreihenfolge entfällt. Nur der „Fortgeschritten"-Bereich bleibt collapsible.

Geteiltes Rubriken-Modul (Entdopplung von `library-rubrics.ts`): die reine Auswahllogik liegt DOM-frei in `viewer/src/ui/rubrics-state.ts` (`RubricsState`, vitest), die dünne DOM-Klasse in `viewer/src/ui/rubrics.ts` (`Rubrics`, Sichtbarkeit nur über `.hidden`). Sowohl die **Bibliothek** (`library-rubrics.ts`, Verhalten byte-gleich) als auch der **Druckplan** (`main.ts`) nutzen dasselbe Modul. Der DOM-Vertrag (zwei Rubrik-Sichten mit ihrer Zuordnung, „Fortgeschritten" als einziges Collapsible, Simulieren-Bereich panel-global) steht in `shell-structure.test.ts`; der Rubrikenwechsel ist als Schritt 2e im `ui_smoke.mjs` abgesichert.

### Teile-Palette am 3D-Feld — Ampel, Override-Marker, Auswahl↔Fokus-Sync (Reiter Druckplan, Issue #91, PRD #88)

Die einzelnen **Teile** (Abschnitte) eines Druckjobs stehen nicht mehr als lange Liste im Aside, sondern in einer **Teile-Palette**: einer ein-/ausklappbaren schmalen Leiste **am geteilten 3D-Feld** des Druckplans (schwebend **oben links**, `.float-panel`; seit Issue #114, nur im Reiter Druckplan/Zerlegung sichtbar). Die frühere Abschnittsliste (`#decompose-sections`) ist damit **vollständig** in die Palette aufgegangen — ihr Funktionsumfang bleibt erhalten.

- **Je Teil eine Zeile:** **Ampel** (grün erreichbar / rot nicht erreichbar / orange „ungeprüft" nach einer Schnittplan-Änderung), **Name** (`#<Reihenfolge> <id>`), **erreichbarer Anteil** in Prozent und der **Platzierungs-Override-Select** (dieselbe Wahl wie zuvor: „automatisch gesucht" oder eine benannte Aufstellmöglichkeit übersteuern, #25).
- **▪-Marker bei Overrides:** Trägt ein Teil einen **individuellen Override** — Slicing (`process_params.sections`, #82) **oder Platzierung** (`section_overrides`, #25/#94) — erscheint hinter dem Namen ein **▪**; wird der letzte Override entfernt, verschwindet der Marker wieder.
- **Auswahl ↔ 3D-Fokus beidseitig synchron:** Klick auf ein Teil in der Palette nimmt es in den 3D-**Fokus** (#84); Klick auf die Abschnitts-Box im 3D-Feld wählt dasselbe Teil in der Palette. Beides läuft durch **denselben** Fokus-Zustand (`focus-state.ts`) — es gibt **keine** parallele Auswahl. Fällt der Fokus-Abschnitt durch eine neue Zerlegung weg, räumt `reconcileFocus` die Auswahl mit.
- **Ein-/ausklappbar:** Ein Kopf-Umschalter blendet den Palette-Körper aus/ein — **ausschließlich** über `.hidden` (nie `display`, Schutz vor dem toten-Reiter-Bug #56).

Pure/DOM-Split wie im Hausmuster: die reine Ableitung (Einträge, Ampel, Marker, Auswahl) liegt DOM-frei in `viewer/src/ui/parts-palette-state.ts` (`paletteEntries`/`slicingOverrideSectionIds`, vitest), die dünne DOM-Klasse in `viewer/src/ui/parts-palette.ts` (`PartsPalette`). Der `DruckplanPanel` füttert sie und hält die Fokus-/Override-Zustände; der DOM-Vertrag (Palette am 3D-Feld statt im Panel, alte Liste entfernt) steht in `shell-structure.test.ts`, der Sync- + Marker-Pfad als Schritt 2f im `ui_smoke.mjs`.

### Gilt-für-Umschalter Global↔Teil — feldweise Slicing-Overrides in denselben Formularen (Reiter Druckplan, Issue #92, PRD #88)

Der **Gilt-für-Umschalter** (Glossar `viewer/CONTEXT.md`, OrcaSlicer-Vorbild): sobald in der **Teile-Palette** (#91) ein **Teil** gewählt ist, erscheint **oben im Druckplan-Aside** der Geltungsbereichs-Schalter **Global ↔ gewähltes Teil**. Die frühere separate Sektion „Pro-Abschnitts-Overrides" (#82) ist darin **vollständig aufgegangen** — es gibt kein zweites Formular mehr.

- **Dieselben Formulare, zwei Geltungsbereiche:** Auf **„Teil"** gestellt zeigen die **selben** Slicing-Formulare (Prozessparameter, Anstellwinkel, Fortgeschritten) die **geerbten effektiven Werte dezent** als Platzhalter („erbt 8" bzw. „erbt (Karte/Default)"). Jede Eingabe erzeugt einen **feldweisen, sparsamen Override** über die bestehende #82-Mechanik (`process_params.sections`, Auflösung `resolveSectionParams` — keine Duplikation, keine zweite Ablage); leere Gruppen fallen weg. „Speichern" persistiert über **dieselbe Route** `PUT /projects/{slug}/process-params` (Feld `sections`).
- **↺ „auf global zurück":** Jedes übersteuerte Feld trägt ein kleines **↺**, das **genau dieses eine Feld** wieder erben lässt; alle anderen Overrides bleiben stehen. Übersteuerte Felder sind hervorgehoben (`.section-param-override`), der ▪-Marker in der Teile-Palette erscheint/verschwindet mit dem gespeicherten Override.
- **Ausgrau-Matrix:** Im Teil-Modus sind die **strukturellen** Einstellungen (Aufstellung, Zerlegungsart/Zerlegungsvorschlag, Schnittplan) **ausgegraut** (disabled) — sie *erzeugen* die Teile erst und können nicht je Teil gelten. Ausschließlich `disabled`, nie ausgeblendet: das Formular springt nicht. Der **Singularitäts-Advisor bleibt bedienbar** (er prüft seit Issue #134 das fokussierte Teil). Abwahl des Teils oder Zurückstellen auf „Global" zeigt sofort wieder die globalen Werte.
- **Granulare Veraltung bleibt (#83):** Ein Teil-Override veraltet **nur dieses Teil** (der Core bumpt nur dessen `section_inputs`-Zähler); eine globale Eingabe veraltet wie bisher **alle** Teile.

Hausmuster: die reine Scope-Logik (Geltungsbereich + Fokus-Abgleich, Ausgrau-Matrix `groupEnabled`, Vererbungsanzeige `overrideFieldView`, Ein-Feld-Reset `resetOverrideField`) liegt DOM-frei in `viewer/src/ui/scope-state.ts` (vitest, inkl. #83-Anker); die dünne DOM-Anbindung sind `viewer/src/ui/scope-switch.ts` (Umschalter, Sichtbarkeit nur über `.hidden`) und das scope-fähige `viewer/src/ui/process-params.ts` (die frühere `section-params.ts`-Panelklasse ist entfernt, die reine `section-params-state.ts`-Mechanik bleibt die eine Quelle). DOM-Vertrag in `shell-structure.test.ts`, der Bedienpfad (Teil wählen → Feld übersteuern → Marker + nur dieses Teil veraltet) als Schritt 2g im `ui_smoke.mjs`.

### Platzierung sichtbar — Basis-Marker aller Teile + echtes M1013-Mesh am Fokus (Reiter Druckplan, Issue #93, PRD #88)

Der Core rechnet je **Teil** (Abschnitt) längst eine **Platzierung** (seitliche Position, Abstand, Aufstellhöhe/Podest) samt Bewertung — S4 macht sie **sichtbar**. Im geteilten 3D-Feld des Druckplans (Vorbereiten-Modus) erscheinen **dauerhaft Basis-Marker aller Teil-Platzierungen** vor der Wand, sodass das **Aufstellmuster** und das **Konsolidierungspotenzial** auf einen Blick lesbar sind. Alles reine Darstellung (ADR-007) — **keine neuen Urteile im Viewer**.

- **Marker je Teil:** Position aus `lateral`/`standoff`, Höhe = die **echte, absolute Aufstellhöhe über dem Boden** (`wall.zMin + stand_height_mm`, Issue #132/#133 — nicht mehr der Abschnittsfuß): im Boden-Modus stehen **alle** Marker auf dem Boden vor ihrem Abschnitt, bei Aufstellhöhe > 0 zeigt ein **Podest-Sockel** die volle Höhe **vom Boden bis zur Basis**. Dieselbe Basis-Marker-Darstellung wie die gewählte Platzierung (#22), nur je Teil an seiner eigenen `PlacementOption`. Sie aktualisieren sich nach jeder **Core-Neubewertung** (Zerlegungsvorschlag, „Prüfen", Aufstell-Toggle).
- **Fokus zeigt das echte Roboter-Mesh:** Das fokussierte Teil zeigt statt des Markers das **echte M1013-Mesh** (dieselbe GLB-Link-Kette wie der Trajektorien-Player, #40/#41) in **neutraler Pose** an seiner Platzierung — die Basis steht auf **derselben absoluten Aufstellhöhe** wie der Marker (Issue #133, keine Doppel-Addition). Fokus-Wechsel und -Lösen tauschen **sauber** zwischen Marker und Mesh; scheitert der GLB-Load, greift wie überall das Kapsel-Schema.
- **Teil-Detail in der Palette:** Jede Zeile der **Teile-Palette** (#91) zeigt zusätzlich die **Platzierungswerte** (seitl./Abstand/**Aufstellhöhe ü. Boden**, Issue #133) und die **Bewertung** (erreichbarer Anteil, kinematische Marge) — **verbatim aus dem Core-Artefakt** (`DecompositionSection.placement`/`status`), keine Viewer-Ableitung.
- **#85/#86 unberührt:** Marker und Mesh leben nur im **Vorbereiten-Modus** der Modellübersicht; im **Simulieren-Modus** (#86) und in der Roboter-Vorschau (#31) ruhen sie, damit die Live-Vorschau (#85) und der volle Arm-Lauf unbeeinträchtigt bleiben.

Hausmuster: die reinen Pose-Funktionen (Marker-Position + Mesh-Basis-Frame aus Platzierung + Wandmaßen) liegen three.js-frei in `viewer/src/render/placement-markers.ts` (`sectionPlacementBox`/`sectionMarkerPosition`/`sectionBaseFrame`, vitest); die three.js-Objekte (Marker-Gruppe, Fokus-Umschaltung) sind dünn darum herum, der Arm kommt aus der bestehenden `ArmView`. Der `main.ts` treibt Auf-/Abbau über den Fokus- und Modus-Zustand; der Marker-/Mesh-Pfad steht als Schritt 2h im `ui_smoke.mjs` (Marker-Anzahl = Teile-Anzahl; Fokus ⇒ Mesh sichtbar; Hook `__placementDebug`).

### Freie Platzierungs-Overrides je Teil — seitlich/Abstand/Aufstellhöhe im Teil-Scope (Reiter Druckplan, Issue #94, PRD #88)

Der **Platzierungs-Override** eines Teils konnte bisher nur eine **erfasste Aufstellmöglichkeit** referenzieren (`option_id`, #25). S5 erlaubt zusätzlich **freie Werte**: Ein Teil trägt eine übersteuerte **seitliche Position**, einen **Abstand** und eine **Aufstellhöhe** direkt — statt (oder ergänzend zu) einer Referenz. Der Core **bewertet** den Override mit der **bestehenden** `evaluate`-Maschinerie (Ampel/erreichbarer Anteil/kinematische Marge) — der Viewer urteilt nicht (ADR-007).

- **Im Teil-Scope des Gilt-für-Umschalters:** Die drei Felder (seitlich/Abstand/Aufstellhöhe) sind **nur bedienbar, wenn ein Teil gewählt** und der Umschalter (#92) auf „Teil" gestellt ist — dasselbe S3-Muster wie die Slicing-Overrides: ein **leeres** Feld erbt die **automatische** Platzierung (der automatische Wert steht als **Platzhalter** „automatisch 712"), eine **Eingabe** ist ein feldweiser Override (hervorgehoben), und ein **↺** je Feld setzt es **zurück auf Automatik**. Leert man alle Felder, kehrt das Teil vollständig zur automatischen Platzierung zurück.
- **Sparse & additiv, Altprojekte byte-gleich:** Die freien Werte liegen im **selben** `section_overrides`-Eintrag wie die `option_id` — beide Formen koexistieren (die freien Werte übersteuern die referenzierte/automatische Basis **feldweise**). Nur gesetzte Felder werden gespeichert; ein bestehender `option_id`-Override bleibt gültig, ein Altprojekt ohne freie Werte lädt **byte-gleich**.
- **Persistenz über die eine Schreibstelle:** Eine **dünne** Route `PUT /projects/{slug}/placement-override` (Mirror von `…/module-limits`/`…/stand-mode`) schreibt die sparse Werte über `fgc.project` (ADR-016); nach dem Neuladen ist genau der Stand wiederhergestellt.
- **Sicherheitsabstand = Befund, kein Gate:** Liegt der freie **Abstand** unter dem `safety_min_distance_mm` der gewählten Workstation (#77), meldet der Core im Zerlegungslauf einen **`placement_check`**-Befund (`below_min_distance`) — **er blockiert nichts**, das Speichern und die Neubewertung laufen normal weiter.
- **Nur dieses Teil veraltet (#83):** Ein Platzierungs-Override bumpt **nur den Pro-Abschnitts-Zähler** dieses Teils → **nur seine** Simulation/sein Export veralten, die Nachbarn bleiben aktuell. Eine **strukturelle** Schnittplan-Änderung (Zerlegungsart/Schnitte/Fugen-Versatz) veraltet weiterhin **alle** Teile (`cutplan`-Bump); eine unveränderte „Prüfen"-Runde bumpt **nichts**.
- **▪-Marker & Marker/Mesh folgen:** Der **▪-Marker** der Teile-Palette (#91) zählt jetzt **auch** Platzierungs-Overrides (Union aus Slicing- und Platzierungs-Overrides). Nach der Neubewertung **wandern** der Basis-Marker und das M1013-Mesh (#93) sofort auf die neue Platzierung.

Hausmuster: die Formular↔Job-Umrechnung + Vererbungsanzeige liegen DOM-frei in `viewer/src/ui/placement-override-state.ts` (vitest), die dünne DOM-Anbindung in `viewer/src/ui/placement-override.ts`; die Marker-Zählung erweitert `parts-palette-state.ts` (`placementOverrideSectionIds`). Core-seitig teilen Zerlegungs-Route und Simulation dieselbe Override-Auflösung (`_resolve_section_overrides`), der Setter ist `set_placement_override_for_job`, der Sicherheits-Befund `fgc.decompose.check_safety_distance`. Der End-to-End-Pfad (Override setzen ⇒ Marker wandert + nur dieses Teil veraltet) steht als Schritt 2i im `ui_smoke.mjs`.

### Modul-Zerlegung — Zerlegungsart-Weiche Abschnitte↔Module (Reiter Druckplan, Issue #90 + #95, PRD #88, ADR-022)

Die Zerlegung kennt **zwei Arten** (`core/CONTEXT.md`): **Abschnitte** (in place — vor Ort drucken, der Roboter wird umgesetzt) und **Module** (an der **Workstation** vorproduzieren und montieren). Bisher war „Modul" eine deaktivierte Dropdown-Option und im Core ein `ValueError`; #90 (Core, S6) und #95 (Viewer end-to-end, S7) machen die Art **funktionsfähig** — Fügegeometrie bleibt bewusst ausgeklammert (folgt später).

**Der Druckort der Modul-Fertigung ist die Workstation (ADR-022):** Der Roboter sitzt fest an ihrer Basis (`robot_base_frame`), jedes Modul steht stehend in **Einbauorientierung** auf der Arbeitsfläche (`work_surface_frame`). Statt einer Platzierungssuche je Zelle gilt daher **eine feste Platzierung** für alle Teile — rechnerisch dieselbe Relativpose wie bei „Abschnitt", nur invertiert gelesen (das Modul steht, der Roboter bleibt). Datenmodell und Bewertungsmaschinerie (`evaluate`, Ampeln) bleiben unverändert.

- **Prominente Radiogruppe ganz oben in der Rubrik „Zerlegung & Platzierung":** Abschnitte ↔ Module — sie ersetzt die frühere deaktivierte Dropdown-Option. Die Weiche blendet die **artspezifischen Einstellungen** um (ausschließlich über `.hidden`): **Abschnitt** zeigt den Aufstell-Toggle (Boden↔erhöht, #81), **Modul** die optionalen Felder **max. Modullänge/-höhe**. Auch die **Beschriftungen** schalten mit (Teile-Palette „Abschnitte"/„Module", Teil-Namen „Abschnitt N"/„Modul N").
- **Artwechsel-Semantik (ADR-022 Punkt 5):** Schnittebenen sind **zerlegungsart-neutral** — ein Artwechsel **behält alle Schnitte** und setzt nur das bestehende `dirty`-Flag; der debouncte **Re-Check** bewertet dieselbe Geometrie mit der Logik der **neuen** Art. **Slicing-Overrides** (`process_params.sections`, #82) **überleben** den Wechsel (stabile Section-IDs); **Platzierungs-Overrides** (`section_overrides`, #25/#94) **verfallen** — ein Stellplatz am Einbauort ergibt an der Workstation keinen Sinn.
- **Modulgewicht + Grenzen-Befund je Teil (S6):** Bei Art „modul" zeigt die Teile-Palette je Modul zusätzlich das **Gewicht** (Volumen × Dichte, Dichte-Default aus der Prozessfenster-Karte `density_kg_m3`, ADR-013) und — falls Obergrenzen gesetzt — den **Grenzen-Befund** (eingehalten/überschritten). Das ist ein **Befund, kein Gate** (ADR-022): der harte Begrenzer der Modulgröße ist der **Arbeitsraum** an der festen Platzierung; die Obergrenzen (Transport/Montage) verfeinern nur das Raster. Die **Ampeln** kommen unverändert vom Core.
- **max-Maße persistieren über die #90-Route:** Die optionalen Obergrenzen schreibt der Viewer über `PUT /projects/{slug}/module-limits` (sparse: leer = keine Grenze, beide leer = Block entfernt; Mirror von `…/stand-mode`) in den Druckjob (`module_limits`) — wie der Aufstell-Toggle veraltet dieser Aufruf **keine** Outputs; die Neubewertung stößt der Druckplan über die Zerlegungs-Route an.
- **Ohne Workstation → freundlicher Hinweis, kein Absturz, kein Gate:** Ist Art „modul" gewählt, aber der Druckjob trägt **keine Workstation** (der Druckort fehlt), zeigt der Viewer einen Hinweis („bitte zuerst eine Workstation wählen") statt einen Vorschlag zu rechnen; die Art bleibt wählbar, nichts blockiert.
- **Reihenfolge = Montagereihenfolge:** Druckreihenfolge unten → oben, links → rechts; eine Umsortier-Funktion gibt es in v1 nicht.

**Core-Kern (#90, S6):** `fgc.decompose.propose`/`from_cuts` akzeptieren `kind='modul'` (feste Workstation-Platzierung, `_module_placement`); `fgc.decompose.limits` (`check_module`/`check_plan`, rein/deterministisch) rechnet Gewicht + `LimitFinding` je Obergrenze; `propose_decomposition` legt `module_check` je Teil additiv in Lauf und Antwort (Schema-Felder `module_check`/`module_limits`); der Setter ist `set_module_limits_for_job`, die Route `PUT …/module-limits`. Art „modul" ohne Workstation wirft einen **freundlichen** `ValueError` (Route → 422).

Hausmuster: der reine Weiche-Zustand (Sichtbarkeitsmatrix + die drei Artwechsel-Regeln) liegt DOM-frei in `viewer/src/ui/zerlegungsart-state.ts` (`visibilityFor`/`switchArt`/`workstationHint`, vitest — alle drei Regeln getestet: Schnitte bleiben / Slicing überlebt / Platzierung verfällt), die dünne DOM-Anbindung im `DruckplanPanel`. Die Palette zeigt den Modulgrenzen-Befund über `parts-palette-state.moduleCheckLine`. Der Artwechsel geht über die **eine** Schreibstelle (`proposeDecomposition` → `fgc.project`, ADR-016): der Re-Check sendet die geräumten Overlays und die neue Art, der Core persistiert sie. Der End-to-End-Pfad (Artwechsel: Schnitte bleiben, dirty, Gewicht sichtbar) steht als Schritt 2j im `ui_smoke.mjs`.

### Druckort sichtbar — Modul-Pose (Core) + Druckort-Ansicht Einbauort↔Workstation (Reiter Druckplan, Issue #96, PRD #88, ADR-021/022)

Der **Druckort** der Modul-Fertigung wird sichtbar: am **fokussierten Modul** erscheint am 3D-Feld der Ansichts-Umschalter **Einbauort ↔ Druckort**. „Druckort" blendet die Szene auf die **Workstation** um — Workstation-Mesh, das echte **M1013-Mesh an `robot_base_frame`** und das **Modul-Rechteck auf der Arbeitsfläche**, konsistent zur vom Core gerechneten Lage — mit **weicher Kamera-Einfassung** (#84-Tween-Mechanik); der Rückweg stellt die Wand-Ansicht (inkl. Kamerastand) weich wieder her. Bei **Abschnitten entfällt der Umschalter** — Einbauort *ist* der Druckort (in place gedruckt).

- **Core-Modul Modul-Pose (`fgc.decompose.module_pose`, rein/deterministisch):** aus der Platzierungs-**Relativpose** eines Teils und den Workstation-Frames `robot_base_frame` + `work_surface_frame` (ADR-021 — die Frames bekommen hier ihren **ersten Konsumenten**, Schluss der Naht #77/#79) entsteht die **Lage des Moduls auf der Arbeitsfläche**: die *Invertierung der Leserichtung* (ADR-022) — bei Modul steht der Roboter, das Modul liegt vor ihm (`T_ws←modul = T_ws←basis ∘ T_modul←basis⁻¹`). Der **Roundtrip** Relativpose ↔ Arbeitsflächen-Lage ist verlustfrei (pytest-Orakel, auch mit gedrehten/gekippten Frames). Frame-Algebra ausschließlich aus `fgc.simulation.transform` (ADR-006: mm, Quaternionen `[w, x, y, z]`, eine Transformationsstelle).
- **Lage je Teil additiv im Artefakt/über die API:** Bei Art „modul" mit Workstation-Frames trägt jedes Teil in `decompose.json` und der `/decomposition`-Antwort ein `module_pose` (`workstation` = Modul-Frame in Workstation-Mesh-Koordinaten, `on_surface` = dieselbe Pose relativ zur Arbeitsfläche). Teile mit **Platzierungs-Override** (#94) bekommen ihre eigene Lage. Art „abschnitt" und Altläufe bleiben **byte-gleich** (kein Feld).
- **Ohne Workstation-Frames → freundlicher Hinweis, keine kaputte Szene:** Fehlt die Workstation am Druckjob, fehlen ihre Platzierungs-Frames (ADR-021 optional, Altbestand) oder trägt der Lauf noch keine Lage (einmal „Prüfen"), zeigt der Umschalter den passenden Hinweis und bleibt in der Wand-Ansicht — **Befund, kein Gate**.
- **Sauberes Zurückfallen:** Fokus gelöst, Artwechsel auf „Abschnitte", Moduswechsel auf „Simulieren" oder Reiterwechsel verlassen die Druckort-Ansicht automatisch zur Wand-Ansicht (`reconcileDruckortView`); wandert der Fokus auf ein anderes Modul, baut sich die Szene an dessen Lage neu auf.

Hausmuster: die reine Umschalt-Logik (nur am Modul-Fokus, Rückfall-Regeln) liegt DOM-frei in `viewer/src/ui/druckort-state.ts`, die reinen Szenen-Spec-Funktionen (Frame→4×4, Modul-Rechteck-Maße, Szene-oder-Hinweis) three.js-frei in `viewer/src/render/druckort-spec.ts` — beide vitest-getestet; `main.ts` blendet nur um (ADR-007: die Lage kommt als Core-Artefakt, der Viewer rechnet reine Darstellungsmathematik). Der End-to-End-Pfad (Modul fokussieren → Druckort → Roboter + Modul sichtbar → zurück) steht als Schritt 2k im `ui_smoke.mjs` (`__druckortDebug`).

### Modul-Simulation — Fokus-Modul am Druckort + „Alle Module" (Reiter Druckplan/Simulieren-Modus, Issue #97, PRD #88, ADR-022 §6)

Der **Simulieren-Modus** (#86) wird **artabhängig**: die zwei Simulieren-Knöpfe folgen der **Zerlegungsart**. Bei **Abschnitten** bleibt alles **unverändert** — „Fokus-Abschnitt simulieren" + „Ganze Wand (unten → oben)" mit Umbau-Schritt, in place im geteilten 3D-Feld (#26/#27). Bei **Modulen** heißen sie **„Fokus-Modul simulieren"** und **„Alle Module"** und spielen **am Druckort** (der Workstation-Bühne aus S8/#96): der M1013 sitzt **fest** an der Roboterbasis, das Modul steht auf der **Arbeitsfläche** an der vom Core gerechneten Modul-Pose.

- **„Fokus-Modul simulieren":** sliced das fokussierte Modul und simuliert es zu einem **frischen Lauf** (aktuelle Werte → nie veraltet), dann spielt der volle Arm-Lauf **in der Druckort-Ansicht** ab — der feste Roboter fährt die Bahn, das Modul liegt auf der Arbeitsfläche. Wie bei Abschnitten genügt bei **genau einem** Modul dieses eine, auch ohne expliziten Fokus (US 24).
- **„Alle Module" (statt „Ganze Wand"):** spielt **alle Module sequentiell in Montagereihenfolge** (= Druckreihenfolge, **unten → oben, links → rechts**, `core/CONTEXT.md`) am Druckort über **eine Gesamtzeitleiste** ab — **dieselbe `TrajectoryPlayer`-Instanz** wie bei Abschnitten. Zwischen zwei Modulen läuft ein **Wechsel-Schritt**: das **Modul auf der Arbeitsfläche wird durchgetauscht** (die Bühne baut sich am nächsten Modul neu auf), eine Beschriftung im Player nennt den Wechsel. **Veraltete Module** tragen ihr **„veraltet"-Badge** (#83-Mechanik unverändert).
- **Reine Darstellungsmathematik (ADR-007):** die Gelenke fahren die vom **Core** gerechnete Bahn, der Transform der Bühne kommt aus der **S8-Modul-Pose** (#96) — **keine neue Kinematik**. Kinematisches Replay, **keine Kollisionsprüfung** (PRD Out of Scope).
- **Ausdrücklich out of scope (PRD #88, ADR-022 §6):** eine **Montage-Simulation am Einbauort** (Kran/Fügen der Module in die Wand) wird **nicht** gebaut — die Druckreihenfolge *ist* die Montagereihenfolge, eine Umsortier-Funktion gibt es in v1 nicht.

Hausmuster: die reine **Beschriftungs-/Sequenzlogik** (Knopf-Labels, Tooltips, Hinweise je Art + „spielt am Druckort?") liegt DOM-frei in `viewer/src/ui/druckplan-mode.ts` (vitest, inkl. **Abschnitt-Regressionstest** — der Abschnitt-Modus ist bit-identisch zu vorher); die dünne DOM-Anbindung in `viewer/src/ui/simulation.ts` weist die Strings zu, `main.ts` schaltet die **Venue** (in place ↔ Druckort-Bühne) und treibt die geteilte `TrajectoryPlayer`-Instanz. Der End-to-End-Pfad (Art „modul" → Simulieren → „Alle Module" sichtbar → „Fokus-Modul simulieren" spielt am Druckort) steht als Schritt 2l im `ui_smoke.mjs` (`__moduleSimDebug`). **Schließt PRD #88** ab (Druckplan-Neuordnung II, #89–#97).

**Endeffektor am Flansch + TCP-Marker am Druckort (Issue #151):** Der Druckort-Arm zeigt jetzt — wie der Wand-Arm (#28) — den **gewählten Endeffektor** als Mesh am Flansch und einen **TCP-Marker** (cyanes Kreis-plus-Quadrat-Fadenkreuz) auf der Bahn des aktiven Moduls. Der Endeffektor hängt beim Bühnen-Aufbau (`buildDruckortScene`) am Flansch; da der Druckort-Arm über Modulwechsel **wiederverwendet** wird, leert `clearFlange()` den Flansch **vor** jedem Anhängen (kein Doppel-Anhängen), und ein Bau-Guard (`BuildSeq`/`druckortBuildSeq`, `viewer/src/render/buildseq.ts`) verwirft ein zu spät geladenes Mesh eines schon abgeräumten Baus. Der Zähler wird **nur** beim Neubau/Teardown (`clearDruckortScene`) erhöht — nie innerhalb eines Baus, sonst entwertete das asynchron geladene Workstation-Mesh den Guard des Endeffektors desselben Baus. Der TCP-Marker sitzt unter der **`moduleGroup`** des aktiven Moduls — **nicht** unter der Druckort-Gruppe: die Marker-View baut in **abschnittslokalen data-mm**, und die `moduleGroup` trägt die **Modul-Pose** (`module_pose.workstation`), sodass der Marker auf der **echten Modul-Lage** liegt statt am Wand-Ursprung. Er wird aus der **lokalen Modulzeit** gespeist (`localFraction`), nicht aus der Sequenz-Gesamtzeit. Im **Umbau-Schritt** ruhen Arm/Endeffektor und Marker; beim Modulwechsel wird der alte Marker mit seiner `moduleGroup` GPU-sauber abgeräumt und für das nächste Modul neu gebaut. Die **provisorische Endeffektor-Hülle bleibt provisorisch** (PRD #124 Punkt 3): das Werkzeug wird **angezeigt**, es beurteilt nichts. Hausmuster: die reine Ableitung Cursor → Bühnenzustand (aktives Modul, Sichtbarkeit, Marker-Fraktion) liegt three.js-frei in `viewer/src/trajectory/modulereplay.ts` (`moduleReplayFrame`, vitest daneben); `main.ts` verdrahtet nur. Diagnose im `__moduleSimDebug` (`toolAtFlange`, `markerVisible`).

**Druckfortschritt am Druckort — wachsender Strang + Druckstand statt Vollbox (Issue #152):** Am Druckort stand das Modul bisher von Sekunde null als **volle Box** da, während der Arm hindurchfuhr. Nach Entscheidung #147 („**Soll als Linie, Ist als Volumen**") zeigt die Bühne jetzt den **Druckfortschritt**: Der **Soll-Umriss** bleibt als **Kanten-Rechteck** (`EdgesGeometry` der Modul-Box) stehen — Lage, Orientierung und Sollgröße auf der Arbeitsfläche; die frühere halbtransparente **Voll-Box entfällt**. An ihre Stelle tritt beim Replay das **Ist-Volumen** als **wachsender Druckstand** (`DruckstandView`, gespeist aus der **Targets-AABB** des aktiven Moduls): ein Quader, der schichtweise mit der modul-lokalen Zeit in der Höhe wächst — dasselbe Volumen, gegen das `fgc.collision.check` rechnet (ADR-024). Zusätzlich deckt ein **wachsender Strang** (`ToolpathView` mit `setGrowth`) den gedruckten Toolpath zeitgetreu auf; **Travel erzeugt keinen Strang** (wie #27). Beide Views hängen — wie der TCP-Marker (#151) — unter der **`moduleGroup`** des aktiven Moduls (abschnittslokale data-mm, Modul-Pose auf der `moduleGroup`), **nicht** unter der Druckort-Gruppe. **Je Modul frisch:** beim Modulwechsel baut `buildDruckortScene` die Bühne neu, der alte Teilbaum wird GPU-sauber abgeräumt (`disposeSubtree`) und Strang + Druckstand für das neue Modul neu erzeugt — kein Übertrag zwischen Modulen, „Alle Module" bleibt über die ganze Sequenz konsistent. Der **⚙-Schalter „Wachsender Druckstand"** wirkt auch hier (derselbe Schalter wie an der Wand, Standard aus). Hausmuster: die reine **Zeit→Wachstums-Ableitung** liegt three.js-frei in `moduleReplayFrame` als Feld **`growthFraction`** (in der Druckphase = `localFraction`, im **Umbau 0** — das ankommende Modul startet leer; bewusst getrennt von `markerFraction`, vitest daneben); den Target-Index für den Strang liefert `targetIndexAtProgress` (#27). `main.ts` verdrahtet nur.

**Soll-Umriss liegt auf der echten Druckposition (Bugfix 2026-07-09):** Der Kanten-Umriss (`moduleBoxSpec` in `viewer/src/render/druckort-spec.ts`) zeichnete die Modul-Box mit der Konvention „Modulfront bei y = 0, Körper dahinter (y ∈ [−Dicke, 0])" — das **Modul-System der Core-Lage ist aber das PCA-zentrierte Wandsystem der Simulation**: Toolpath, Trajektorie und Kollisionsbefund liegen bei **y ∈ [−Dicke/2, +Dicke/2]** (empirisch am Denkmal-Modul verifiziert: Targets y −240…+240 bei 480 mm Wanddicke). Der Kasten stand dadurch eine **halbe Wanddicke zu weit von der Roboterbasis** weg, und der Druck (Strang, Druckstand, TCP-Marker — alle aus echten Target-Daten) ragte sichtbar zum Roboter hin **aus dem Kasten heraus**. Fix: die Box ist jetzt y-zentriert (`centerLocalMm[1] = 0`) und deckt sich mit dem Ist-Volumen. Merke: der angezeigte **„Abstand"** der Platzierung misst von der Roboterbasis zur **Modul-Mittelebene**, nicht zur nächstliegenden Modulfläche — die reale Freidistanz zur nahen Kante ist also `Abstand − Dicke/2`.

**Kollisionsanzeige am Druckort — Abstandszahl, Glied-Einfärbung, Marker des aktiven Moduls (Issue #153):** Der **Kollisions-Befund** eines Modul-Laufs wurde am Druckort bislang geladen, aber im Replay **weggeworfen**. Jetzt zeigt die Druckort-Bühne ihn — genau wie das Wand-Replay (#128), **verbatim** aus `meta.collision` (ADR-007, der Viewer rechnet nichts) und **folgend der modul-lokalen Zeit** des aktiven Moduls: Die **Glied-Einfärbung** (US 8) lässt das verursachende Glied des **Druckort-Arms** rot/gelb leuchten (`ArmView.setLinkHighlight`, gespeist aus `causer_link`); die **Live-Abstandszahl** (US 11) nennt den minimalen Abstand am aktuellen Sample und gehorcht dem **⚙-Schalter „Live-Abstandszahl"**. Die **Timeline-Marker** zeigen **nur das aktive Modul** (Entscheidung #147, Variante b): die modul-lokalen Intervalle werden auf die **Sequenzachse projiziert** (Modul-Offset + Normierung auf die Gesamtdauer), sodass ein Klick **innerhalb** des laufenden Moduls springt und die **Bühne nicht wechselt**; über die **Umbaupausen** (`UMBAU_SECONDS`) entsteht **kein** Marker, und andere Module tragen keine. Im **Umbau-Schritt** ruhen Einfärbung und Abstandszahl mit dem Arm. Die **Statuszeile sagt die Wahrheit**: trägt ein Modul (bzw. bei „Alle Module" irgendeines) einen Befund, fällt der bis dahin falsche Festtext **„keine Kollisionsprüfung"** (seit #128 überholt) und die Kollisionskontrolle folgt dem aktiven Modul; **Altläufe ohne Befund** (der Block fehlt ganz) behalten die **ehrliche Zeile** — **keine Marker, keine Zahl, keine Einfärbung, kein Absturz** (US 25). Das **Kollisions-Badge je Modul** trägt weiterhin die **Teile-Palette** (Gesamtübersicht, #128), bewusst nicht die Player-Leiste. Regressionsanker: **Platzierungs-Ampel bit-identisch** unangetastet, **Wand-Replay unverändert**. Hausmuster: die reine **Projektion modul-lokaler Marker auf die Sequenzzeit** liegt three.js-/DOM-frei in `viewer/src/trajectory/modulereplay.ts` (`projectModuleMarkers`, vitest daneben); `main.ts` verdrahtet Arm-Einfärbung + Abstandszahl je Frame (`applyModuleCollisionFrame`), die dünne DOM-Anbindung (`setModuleCollision`) sitzt in `viewer/src/ui/simulation.ts`. Diagnose im `__moduleSimDebug` (`activeCollision`), Prüfschritt im `ui_smoke.mjs` (2l).

**Player-Leiste S1 — zwei Modi statt Überlagerung (Issue #154):** Das `#sim-dock` zeigte bisher **zwei Zustände gleichzeitig** — die **Startknöpfe** (`▶ … simulieren`, `Ganze Wand`/`Alle Module`) blieben sichtbar, auch wenn der **Player** lief; das war die Ursache der **Überlagerung** in der einzeiligen Leiste (nicht die Textlängen). Jetzt hat die Leiste genau **zwei Modi**: Im **Start-Modus** (kein Replay) stehen die zwei Startknöpfe und die kompakten Hinweise (API-Warnung, Vorbedingung), der Player ist versteckt; im **Replay-Modus** (ein Lauf spielt) steht der Player, die **Startknöpfe verschwinden**. **`← Übersicht`** schaltet zuverlässig zurück in den Start-Modus — und **auch das Ende eines Replays** (Lauf geschlossen/gewechselt, `reset`) stellt ihn her, nicht nur der Knopf. Das gilt für **BEIDE Bühnen**: Wand-Replay (in place) **und** Modul-Replay am Druckort (beide bedienen dieselbe `#sim-dock`-Leiste, `showPlayer`/`hidePlayer`/`teardownModuleReplay`). **Eine Zeile bleibt eine Zeile** — kein Umbruch, kein Popover, keine zweite Zeile (vertikale Fläche ist knapp); als Netz gegen künftiges Wuchern bekommt `#sim-status` ein `min-width: 0` (statt `flex-wrap`), und die Modus-Umschaltung hält die Zeile ohnehin kurz. **Sichtbarkeit ausschließlich über `.hidden`** (Lehre aus #56 — kein `style.display`, keine CSS-Gymnastik). Hausmuster: die reine **Modus-Wahl** (Eingabe = *Replay läuft? API erreichbar? Vorbedingung gesetzt?*, Ausgabe = welche Elemente `hidden` sind) liegt DOM-frei in `viewer/src/ui/sim-dock-state.ts` (`simDockMode`, `simDockHidden`, vitest daneben); die dünne DOM-Anbindung (`_applyDockMode`) sitzt in `viewer/src/ui/simulation.ts`, `main.ts` verdrahtet nur. Prüfschritt im `ui_smoke.mjs` (Schritt 2l: Replay-Modus → Startknöpfe weg + Player da; nach `← Übersicht` → Startknöpfe zurück).

**Player-Leiste S3 — Kollisionsbefund wird Lauf-Eigenschaft (Issue #156):** Der lange Kollisions-Satz (`…enge Stellen (Warnung) — 3 rot, 5 gelb, min. Abstand 12 mm, vorläufige Grenzwerte, Travel nicht lückenlos geprüft.`) stand bisher als **~160-Zeichen-Statuszeile** in der Player-Leiste (`#sim-status`) und **vermischte zwei Textsorten**: eine **Lauf-Eigenschaft** (der Befund, der während des Abspielens stehen bleibt) und **vergängliche Aktionsmeldungen** („Modul-Lauf konnte nicht geöffnet werden…"). Der Befund ist kein Status, er ist ein **Ergebnis** — und wird jetzt **zerlegt**: die **Zahlen** (`n_red`, `n_yellow`, `n_green`, `min_distance_mm`, Prüf-Modus) werden zu überfliegbaren **Definitions-Paaren**, die **Vorbehalte** (`provisional` ⇒ „vorläufige Grenzwerte"; `travel_not_continuously_checked` ⇒ „Travel nicht lückenlos geprüft") zu **Warnungspunkten**. Der Befund erscheint an **beiden Schauplätzen** aus **derselben reinen Funktion** (`collisionMetaPairs`/`collisionCaveats` in `viewer/src/ui/collision-state.ts`, vitest daneben, **verbatim** aus `meta.collision`, ADR-007):

- **Reiter Projekt (Abspieler-Modus):** die Paare ordnen sich in die schon **bewohnte** `#traj-meta`-Definitionsliste ein (neben Dauer, letztes Sample, „io kompensiert", Lagequelle, Max. Achsauslastung), die Vorbehalte in die `#traj-warnings`-Liste (vor die Trajektorien-Warnungen) — sie **verdrängen nichts**. Die **Lagequelle-Zeile** behauptet den Befund **nicht mehr ein zweites Mal**: sie sagt bei Befund nur noch „geplant (Platzierung)" (der Befundblock steht daneben), der ehrliche Zusatz „— Replay, keine Kollisionsprüfung" bleibt nur **ohne** Befund (Entdoppelung, #157).
- **Reiter Slicing (Werkstatt):** die `#sim-dock`-Leiste bekommt einen **eigenen, aufklappbaren Befundblock** (`#sim-collision-panel`) — das **Befund-Badge** ist sein **Anker**: ein Klick (oder Enter/Space) klappt ihn **auf/zu**, **ohne Reiterwechsel und ohne Bühnenwechsel** (Lehre aus #147/#157 — ein Klick darf die Bühne nicht wechseln). Der Block liegt als **Overlay über der Leiste** (`position: absolute`), damit **eine Zeile eine Zeile bleibt** (#154): die Dock-Zeile bricht nicht um und bleibt gleich hoch. Sichtbarkeit **ausschließlich über `.hidden`** (Lehre aus #56).

Die Player-Zeile (`#sim-status`) trägt **keinen 160-Zeichen-Satz** mehr: bei einem Lauf **mit** Befund bleibt sie leer (das Badge + der Block sind der Anker), **Aktionsmeldungen** erscheinen weiterhin (aber als kurzlebige Notiz, nicht als Lauf-Eigenschaft). **Wand und Druckort** zeigen denselben Befundblock — am Druckort speist ihn der Befund des **aktiven Moduls** (`setModuleCollision`, #153). **Altläufe ohne `meta.collision`** (der Block fehlt ganz): **keine leeren `dl`/`ul`-Einträge, kein leerer Befundblock, kein Absturz** — die ehrliche Statuszeile/Lagequelle bleibt wie bisher (US 25). DOM-Vertrag in `shell-structure.test.ts` (neuer Block `#sim-collision-panel` mit `#sim-collision-panel-meta`/`-warnings`, Badge als `role="button"`-Anker), Prüfschritt im `ui_smoke.mjs` (2m: Block vorhanden, anfangs zugeklappt, Badge-Klick togglet ohne Reiterwechsel). Hinweis: Der Body dieses Tickets war durch die **Korrektur aus #157** in zwei Prämissen widerlegt (`#traj-warnings` ist nicht leer, sondern schon bewohnt; ein Badge-Klick kann `#trajectory-panel` nicht öffnen, weil beide Reiter nie gleichzeitig sichtbar sind) — die Umsetzung folgt der Korrektur, nicht dem Body (Design-Log 2026-07-09).

**Player-Leiste S2 — Abspielgeschwindigkeit als Vielfaches der Echtzeit (Issue #155):** Der Player lief bisher **in Echtzeit** — ein realer Abschnitt der Denkmal-Wand dauert **≈ 87 min**, also startete „Play" einen 87-Minuten-Film und nur der Slider war benutzbar. Neu: ein schmales `<select>` im **Replay-Modus** der Leiste (`#sim-speed`, mit dem Player ein-/ausgeblendet, nur `.hidden`) wählt die **Geschwindigkeit als Vielfaches der Echtzeit** — Leiter `0.25 / 0.5 / 1 / 2 / 5 / 10 / 25 / 50 / 100 / 200`. Jede Option nennt **Faktor UND resultierende Replay-Dauer** (z. B. „50× · ~1:44"). **Voreinstellung 1×** behält die physikalische Aussage („so schnell fährt die Maschine wirklich" — nötig, um enge Stellen zu beurteilen). Der Faktor **klebt an der Sitzung** (Modul-Variable `replaySpeed` in `main.ts`, wie die ⚙-Schalter): er überlebt Lauf-, Modul- und Bühnenwechsel und startet beim ersten Öffnen bei 1×; eine Änderung während eines laufenden Replays **wirkt sofort**. Die **Zeitachse bleibt Trajektorienzeit** — Slider, Marker und Wachstum zeigen weiter Trajektoriensekunden; nur die Abspiel-*Rate* skaliert. Kern: `TrajectoryPlayer` bekommt eine **zeitabhängige Rate** (`rateAt(t) → { rate, until_s }`), nicht eine konstante — in einer **Druckphase** gilt der Faktor, in einer **Umbaupause** gilt **1×**, damit `UMBAU_SECONDS = 3` **nicht mitskaliert** (Erzählzeit, #27; der Umbau-Schritt bleibt 3 s Wanduhr und ist auch bei 200× sichtbar). Der Player **teilt jeden Frame an den Phasengrenzen** (`advance`), damit ein einziger langer Frame bei hohem Faktor nicht mit Druck-Rate über die Umbaupause hinweg integriert, und rastet **driftfrei** exakt auf `duration` ein. Die reinen Bausteine liegen im `ui/`/`trajectory/`-Hausmuster mit vitest daneben: die Phasen-Rate `sequenceRateAt` (`trajectory/sequence.ts`, vorwärts gerichtet), die Dauer-Rechnung/-Anzeige `replayEta`/`formatEta`/`speedOptionLabel` (`ui/speed-control.ts`) und die erweiterte `hidden`-Matrix (`speed`) in `ui/sim-dock-state.ts`.

**Bühne folgt dem Simulationslauf — Platzierung aus `meta.base_frame` (Issue #161):** Nach dem Annehmen einer **Placement-Hebel-Option** des Kollisions-Advisors (#130) und anschließender Neu-Simulation lagen am Druckort Soll-Kasten, Stranglinien und TCP-Marker **neben dem Arm**: die Bühne (`moduleGroup`) las die Platzierung aus dem **Zerlegungslauf** (`module_pose.workstation` — nur „Prüfen"/`propose_decomposition` schreibt sie), der Arm folgte den Gelenken des **Trajektorienlaufs**, dessen `meta.base_frame` die Platzierung *dieses* Laufs trägt — zwei unabhängig alternde Quellen. Jetzt gilt: trägt der Modul-Lauf ein `meta.base_frame`, wird der Bühnen-Transform **daraus** abgeleitet — `T_ws←modul = robot_base_frame ∘ invert(base_frame)` (reine Funktion `runModuleFrame` in `viewer/src/render/druckort-spec.ts`, vitest daneben; dieselbe Invertierung der Leserichtung wie `fgc.decompose.module_pose`, ADR-022). Soll-Kasten, Strang, TCP-Marker und Druckstand hängen alle unter der `moduleGroup`: **EIN Transform, EINE Quelle mit dem Arm**. Bei „Alle Module" gilt das je Modul aus dessen **eigenem** Lauf. **Altläufe ohne das Feld** und die reine Druckort-Ansicht ohne Lauf behalten die Zerlegungs-Lage — Befund, kein Gate, kein Crash. Dazu zwei Ehrlichkeits-Fixes: **„Anwenden" einer Placement-Option** des Kollisions-Advisors zieht — wie beim Singularitäts-Advisor — Platzierungsfelder + ▪-Marker sofort nach; und die **Modul-Karte** der Teile-Palette zeigt in der Zeile „Platzierung: …" die **Override-Werte des aktiven Jobs** (sparse: nur überschriebene Felder ersetzen die Zerlegungs-Werte; reine Funktion `placementDisplayValues` in `parts-palette-state.ts`, vitest) statt der veralteten Zerlegungs-Platzierung — reine `option_id`-Referenzen ändern nichts (ihre Werte kennt nur der Core, ADR-007).

### Kollisionskontrolle — Befund im Replay: Glied-Einfärbung, Timeline-Marker, wachsender Druckstand, Abstandszahl, Badge (Reiter Druckplan/Simulieren, PRD #124, ADR-024, Issues #125–#131)

Jede Simulation (Abschnitt wie Modul) erzeugt automatisch einen **Kollisions-Befund** — der Viewer **zeigt** ihn im Replay, **rechnet aber nichts** (ADR-007, keine Viewer-Geometrieurteile). Der Befund liegt **additiv & optional** als `meta.collision` in der `trajectory.json` (S1a/#127): Sicherheitsabstand/Freizone (Platzhalterwerte mit **„vorläufig"-Geist**, bis S1/S4 gemessene Werte liefern), die **Abstandskurve** je Sample, das **verursachende Glied**, die verdichteten **Kollisions-/Warn-Intervalle** und der Gesamtbefund (`min_distance_mm`, `n_red/n_yellow/n_green`). **Befund, kein Gate** — die Simulation liefert immer.

Die S3-Darstellung im Player (alles **verbatim** aus dem Artefakt):

- **Glied-Einfärbung (US 8):** das **verursachende Glied** des Roboterarms leuchtet **rot** (Kollision) / **gelb** (Warnung) am aktuellen Sample — beide Darstellungen (Schema-Zylinder + M1013-Mesh). Welches Glied und welcher Status kommen aus `causer_link`/`intervals`, nicht aus einer Viewer-Rechnung.
- **Anklickbare Timeline-Marker (US 9):** je rot/gelb-Intervall ein Marker über dem Zeit-Slider; ein Klick **springt** zur Intervall-Mitte (`onSeek`). Ihre Zeit-/Positions-Umrechnung ist reine Darstellungsmathematik (Sample-Index → `t_s` → Anteil).
- **Wachsender Druckstand (US 10):** statt der Voll-Box wächst der Bauteil-Quader **mit dem Druckfortschritt** in der Höhe (dieselbe Abbildung wie der wachsende Strang). Reine **Prisma-Spec** + dünnes three.js-Objekt; per **⚙-Sicht-Schalter** „Wachsender Druckstand" zuschaltbar (**Standard aus** — aus lässt das Replay unverändert).
- **Live-Abstandszahl (US 11):** der minimale Abstand (mm) am aktuellen Sample im Player, rot bei Kollision; per **⚙-Sicht-Schalter** „Live-Abstandszahl" abschaltbar (**Standard an**).
- **Kollisions-Badge je Teil (US 12):** in der **Teile-Palette** und im Player ein Ampel-Pill (rot „Kollision" / gelb „eng" / grün „kollisionsfrei"). Es ist ein **getrennter Kanal** — die **Platzierungs-Ampel** (erreichbar/nicht erreichbar) bleibt **bit-identisch unangetastet**.
- **Ehrliche Statuszeile (US 25):** die bisherige Zeile **„keine Kollisionsprüfung"** verschwindet, sobald ein Lauf einen Befund trägt, und weicht der Befund-Zusammenfassung. **Altläufe ohne Befund** (der Block fehlt ganz, kein `null`) behalten die ehrliche Zeile — **keine Marker, keine Badges, kein Absturz**.
- **Travel „nicht lückenlos geprüft":** Travel-Abschnitte springen bis ~1 m je Sample-Schritt (Spike S0); Zwischenzustände können übersprungen werden (Tunneling, v1-Grenze). Der Befund kennzeichnet das ehrlich (`travel_not_continuously_checked`).

**Echte Höhenlage (Issue #135, Folge der absoluten Aufstellhöhen #132–#134):** Die Simulation rechnet **abschnitts-lokal** (z ab Abschnittsfuß) — Kollisionskontrolle und Replay kennen seither die **echte Bandlage**:

- **Boden bei absolut 0:** Für obere Reihen (z0 > 0) führt der Hindernissatz den **realen Boden** als Slab mit Oberkante bei **lokal −z0** (`fgc.collision.druckstand.ground_slab`) — nicht am Abschnittsfuß, wo für obere Reihen Luft bzw. die untere Reihe ist (kein „unter Boden"-Fehlalarm). Für die **unterste Reihe (z0 = 0)** bleibt der Boden wie bisher **weg** (Basis↔Boden ist erlaubter Dauerkontakt; v1-Lehrgeld #127) — ihr Befund ist **bit-identisch** (Regressionsanker, Goldens #126/#127 unverändert).
- **Frühere Teile auf ihren echten Bändern:** die in Druckreihenfolge bereits gedruckten Teile (unten → oben, links → rechts, ADR-022) sind **volle Hindernisse**, ins abschnitts-lokale System des aktuellen Abschnitts verschoben (`part0`, `part1`, … als Verursacher). Die Basis steht seit #132 ohnehin auf ihrer **absoluten** Aufstellhöhe (Naht `_planned_setup`). Der **Kollisions-Advisor** (#130) bewertet seine Kandidaten mit **demselben** Hindernissatz (keine Parallel-Metrik). Befunde oberer Reihen ändern sich dadurch erwartbar — Befund, kein Gate.
- **Replay auf echter Bandlage:** die Trajektorie nennt die Höhenlage additiv als **`meta.section_z0_mm`**; der Viewer hebt die komplette Replay-Szene (Teil-Mesh, Bahn, TCP, Arm, wachsender Druckstand) um diesen Wert — der Boden (Gitter) bleibt bei 0, die Basis (`meta.base_frame`, lokal ggf. negativ) landet auf ihrer **absoluten Aufstellhöhe**; steht sie über dem Boden, hängt ein **Podest-Sockel** von der Basis bis zum Boden (Muster #133). Die **Ganze-Wand-Sequenz** (#27) hebt jeden Abschnitt auf sein echtes Band (der Arm folgt je Schritt). **Altläufe ohne das Feld** (und Modul-Läufe — Druckort ist die Workstation, ADR-022) rendern **bit-identisch** wie bisher.
- **Statuszeile ohne Widerspruch:** die Zeile nach „simulieren + Replay öffnen" leitet sich **verbatim aus `meta.collision`** ab (`replayStatusLine`): mit Befund nennt sie dessen Zusammenfassung, nur Altläufe ohne Befund behalten die ehrliche Zeile „(keine Kollisionsprüfung)" — der frühere Festtext stand im Widerspruch zu Kollisions-Badge + Live-Abstand.

Hausmuster: die reine **Ableitung** (Abstandskurve → Färbung/Marker/Badge/Abstandszahl/Statuszeile) liegt DOM-/three.js-frei in `viewer/src/ui/collision-state.ts` (vitest), die **Druckstand-Prisma-Spec** in `viewer/src/render/druckstand-spec.ts` (vitest), der **Replay-Anker auf echter Bandlage** (z-Hub aus `meta.section_z0_mm`, Podest-Sockel-Spec) in `viewer/src/trajectory/replay-anchor.ts` (vitest); die dünne Anbindung verteilt sich auf `ui/simulation.ts` (Marker/Abstandszahl/Badge), `render/arm.ts` (`setLinkHighlight`), `render/druckstand.ts` (wachsendes Objekt) und `ui/parts-palette*.ts` (Palette-Badge). Der DOM-Vertrag steht in `shell-structure.test.ts`, der Player-Schritt als 2m im `ui_smoke.mjs`. Die Roboter-/Kollisions-Geometrie und der Kollisions-Advisor (Freizeichnen) leben im Core (S1/S2/S4, ADR-024) — der Viewer bleibt reiner Abspieler.

#### Platzierungs-Grob-Check + Gebäudekontext-Schalter (Reiter Druckplan/Zerlegung, Kollisionskontrolle S6, Issue #131, ADR-024)

Zwei Abrundungen der Kollisionskontrolle:

- **Platzierungs-Grob-Check (US 20):** der **Optimalvorschlag** der Platzierung (Reiter Zerlegung, „✦ Automatisch vorschlagen") bewertet Kollisionen jetzt **grob** mit, damit er keine Aufstellungen mehr liefert, die erst in der Simulation durchfallen. Für jeden Kandidaten prüft ein **billiger** Check (`fgc.collision.coarse.path_collides`) an **wenigen Stichproben-Posen** und nur mit der **Breitphasen-Hülle** je Glied (#125, kein python-fcl), ob ein **Armglied** (Rotator/Oberarm/Ellbogen) hinter die Druckebene in den Wandkörper taucht — genau der Ellbogen-durch-die-Wand-Fehler des Auslöser-Fotos. Handgelenk und Endeffektor bleiben außen (sie arbeiten prozessbedingt an der Wandfront). Ein Kandidat, dessen Bahn grob kollidiert, **rutscht im Ranking hinter die kollisionsfreien**; kollidiert nichts, bleibt die bisherige #98-Sortierung (erreichbarer Anteil → Min-Marge → Mean-Marge → zentrale Lage) **bit-identisch**. **Befund, kein Gate:** die Platzierungs-Ampel (erreichbar/nicht erreichbar) behält ihre Bedeutung; der Kern von `evaluate`/`suggest` bleibt unangetastet (additiver Sortier-Schlüssel). Ohne Kollisionsgeometrie (Altprojekt/Roboter ohne Artefakt) entfällt der Grob-Check spurlos.
- **Gebäudekontext-Schalter (US 6):** ein **Schalter im Druckplan** (Accordion „Art & Aufstellung", Reiter Zerlegung) schaltet zu, ob die Simulation den Arm **zusätzlich gegen den Gebäudekontext** (`context.json`, Nicht-Wand-Elemente aus dem Übersichts-Lauf, Issue #17) prüft. **Standard aus.** Bei **Zerlegungsart Modul** ist er **gegenstandslos** (die Workstation ist der Druckort, ADR-022) — dort wird er ausgeblendet, nicht gelöscht. Umschalten persistiert über die dünne Route `PUT /projects/{slug}/context-check` (Spiegel von `stand-mode`, einzige Schreibstelle `fgc.project`, ADR-016) und **überlebt das Neuladen** (aus dem Druckjob-Feld `check_building_context` wiederhergestellt). Wie der Aufstell-Toggle veraltet der Schalter **keine** Outputs — er wirkt erst bei der nächsten Simulation: bei „ein" trägt der `meta.collision`-Befund den Gebäudekontext als zusätzliches Hindernis (in Abschnitts-lokale Koordinaten transformiert), das Konfig-Echo `context_enabled` kippt entsprechend. Additiv/sparse: „aus" entfernt das Feld, **Altprojekte laden byte-gleich**.

Hausmuster: der Grob-Check ist ein eigenes reines Core-Modul (`fgc.collision.coarse`, wiederverwendet die #125-Hüllen + `check`-Breitphase), in `suggest` als optionales Prädikat eingehängt (Regression: „kollidierend rutscht hinter frei" + „sonst #98 bit-identisch", `test_placement_coarse.py`). Der Kontext-Schalter folgt dem `stand-mode`-Muster: Setter `set_context_check_for_job` + Route, reine Zustandslogik `viewer/src/ui/kontext-state.ts` (vitest) + dünner Checkbox-DOM im `DruckplanPanel`; Schema additiv (`check_building_context`), Persist/Restore als API-Test + `ui_smoke.mjs`-Schritt (Sicht bei Abschnitt, ausgeblendet bei Modul).

### Singularitäts-Advisor — Typ-Warnung + Ein-Klick-Vorschlag am Fokus-Abschnitt (Reiter Druckplan, Issue #65, Fokus-Verankerung #134)

Das reziproke Konditionsmaß (Issue #11) sagt nur, **wie nah** eine Pose an einer Singularität ist — der Advisor sagt zusätzlich, **welcher Art** sie ist und **was dagegen hilft**. Im Reiter **Druckplan** prüft **„Singularität prüfen"** die Platzierung des **Fokus-Abschnitts** (das in der Teile-Palette gewählte Teil — Issue #134, Muster Kollisions-Advisor #130) und nennt Typ + gezielten Vorschlag samt Vorher/Nachher-Marge; ein **„Anwenden"-Knopf** setzt den Vorschlag. **Ohne Fokus** zeigt „Prüfen" den freundlichen Hinweis, zuerst ein Teil in der Teile-Palette zu wählen — kein Core-Aufruf, kein Fehler.

- **Fokus-Verankerung (Issue #134):** Der Core rekonstruiert den Zerlegungsplan (`plan_for_job`, inkl. Platzierungs-Overrides #94) und bewertet den Abschnitt an seiner **echten Höhenlage** (#132; Art „modul" am Boden, ADR-022) — nicht mehr die frühere Gesamtwand-`selected_placement` (entfallen, s. Abschnitt „Platzierung: Gesamtwand-Vorschlag entfallen").
- **Typ-Klassifikation (Core, `fgc.kinematics.singularity`):** aus den **Gelenkwinkeln** der schlechtest-konditionierten erreichten Pose — **Handgelenk** (J5≈0, Achsen J4∥J6 koppeln), **Ellbogen gestreckt** (J3 nahe Streckung, Handwurzel am Reichweitenrand) oder **Schulter** (Handwurzel über der Basis-Drehachse z0). Es wird **kein neues Skalarmaß** erfunden: die Nähe bleibt das Konditionsmaß, hier kommt nur die Typ-Unterscheidung dazu.
- **Gezielter Hebel je Typ (Core, `fgc.placement.advisor`):** **Handgelenk → Kipp-Delta** (bahn-relativer Kipp, `process_params.orientation`), **Reichweite/Ellbogen → Platzierungsoption** (bessere Basis-Lage aus `fgc.placement.suggest` für den Abschnitt), **Schulter/konfig-abhängig → Config-Flip** (die **Schulter auf den anderen a/b-Zweig fixieren**, Issue #200). Die **Vorher/Nachher-Marge** kommt aus **derselben Core-Bewertung** (`placement.evaluate`) — ein angewandter Kipp-Delta hebt die kinematische Marge nachweisbar an, ohne den erreichbaren Anteil zu senken.
- **Config-Flip anwendbar (Issue #200, ADR-024 Punkt 4):** Der Config-Flip nennt seit #200 den **Domänenbegriff** statt eines rohen opw-Bitfelds — der Knopf heißt z. B. **„Schulter auf Zweig b fixieren"** und ist **aktiv** (früher rein beratend). Der Advisor emittiert den persistierbaren **a/b-Tri-State-Block** (`ik_config`) + dieselbe **Schreibstellen-Nutzlast** wie der Kollisions-Advisor (`{"setter":"process-params","ik_config":…}`); „Anwenden" setzt ihn über **dieselbe** `PUT …/process-params`-Route (`ik_config`, #129) — der Schreibstellen-Seam trägt jetzt zwei echte Adapter. Die **Marge ist bahn-weit ehrlich**: der harte Filter betrifft die ganze Bahn, nicht die schlechteste Pose — Vorher/Nachher kommen aus einer **Neu-Bewertung mit gesetztem Filter** (dieselbe `placement.evaluate`, keine Parallel-Metrik); unter der Vorgabe unerreichbare Bahnpunkte erscheinen als **Befund** (kein Gate) im Detailtext. Bringt der Flip keinen Margengewinn, bleibt der Knopf inaktiv (der Advisor beschönigt nicht).
- **„Anwenden" = Core setzt + bewertet neu (ADR-007/016):** Der Viewer **rechnet nichts selbst**. Der Knopf schreibt den Vorschlag über eine **bestehende** Schreib-Route — Kipp bzw. Config-Flip über `PUT …/process-params` (die jeweils andere Prozessparameter-Gruppe — Slice/Orientierung/IK — bleibt erhalten, ein gesetzter Lead bleibt erhalten), Platzierung als **freie Platzierungs-Override-Werte des Fokus-Abschnitts** über `PUT …/placement-override` (#94, Issue #134) — und bumpt damit den Revisionszähler → Zerlegung/Simulation/Export veralten sichtbar. Nach einer angewandten **Platzierungs-Option** entwertet die UI Ampel, Druckbarkeits- und Kollisions-Badge des Teils sofort auf **„ungeprüft"** und stößt die Neubewertung an — genau wie das manuelle Platzierungsfeld und der Kollisions-Advisor (Issue #172, geteilte Sequenz `ui/placement-apply.ts`; s. Kollisions-Advisor-Abschnitt).
- **Read-only Urteil:** `POST /projects/{slug}/singularity-advice` (Body: `job_id`, `section_id`) liefert Typ, Nähe (`near`/`measure`), den bewerteten Abschnitt (`section_id`) und den Vorschlag als **Daten** (kein Gate); ohne `section_id`, bei stale Abschnitt oder unkritischer Marge ist die Antwort **freundlich leer** (`type=null`, `advice=null`).
- **Referenzposen bewusst weggelassen (nur Start-Seed):** Der Advisor bewertet die **real gesampelte Wandbahn** der Abschnitts-Platzierung, keine hinterlegten Sollposen — eine bewusste Scope-Grenze dieser Scheibe (Design-Log 2026-07-06, ADR-020).

### Kollisions-Advisor — schneller Befund + gerankte Optionsliste auf Knopfdruck (Reiter Druckplan/Slicing, Kollisionskontrolle S5, Issue #130, ADR-024 Punkt 5; Prüf-UX Karte #139/#145)

Das Gegenstück zum Singularitäts-Advisor für **Kollisionsbefunde** — mit dem prägenden Unterschied: der Kollisions-Advisor liefert eine **gerankte Liste** gangbarer Optionen (das gewünschte „Menü"), nicht einen Einzelvorschlag. Im Reiter **Druckplan** (Slicing) prüft das eigene Accordion **„Kollisions-Advisor"** den Befund des **fokussierten** Teils (Teile-Palette; ohne Fokus das erste Teil des Plans — der **Scope-Chip** im Accordion-Kopf sagt jederzeit, welches Teil geprüft wird).

- **Zweigeteilte Prüfung (Prüf-UX #139/#145):** **„Kollision prüfen (≈ 20 s)"** holt **nur den Basis-Befund** — genau *eine* Neu-Simulation des geprüften Teils, dieselbe Metrik (min. Abstand, Marge, Kollisions-Samples), read-only. **„Hebel-Optionen suchen (Minuten)"** startet bewusst das teure Menü: Basis + ~17 Hebel-Kandidaten, je Kandidat eine volle Neu-Simulation — das dauert **mehrere Minuten** und war zuvor unangekündigt hinter dem einen Prüfen-Knopf versteckt (die real beobachteten „> 3 min Wartezeit" aus Karte #139/#150). Nach dem schnellen Befund sagt die Liste ehrlich „Hebel-Optionen nicht gesucht" statt fälschlich „kein Hebel gefunden". API: `include_options` (additiv, Default `true`) an `POST /projects/{slug}/collision-advice`.
- **Auf Knopfdruck, weil teuer:** Der Advisor läuft **nicht automatisch**. Die Optionssuche probiert drei Hebel mit **derselben** Simulations-/Bewertungs-Maschinerie und liest denselben `meta.collision`-Befund (#127) — **keine Parallel-Metrik** (ADR-024). Der loop-invariante Unterbau (IFC laden, Zerlegung schneiden, Basis-Parameter) entsteht seit der Prüf-UX-Korrektur **einmal je Beratung** (`_SectionSimContext`) statt je Kandidat, und IK-/Platzierungs-Kandidaten teilen den geslicten Toolpath (Cache je Orientierung) — die Optionssuche bleibt dennoch bewusst ein Minuten-Schritt (die Neu-Simulationen selbst sind der Preis).
- **Drei Hebel (Core, `fgc.collision.advisor`):** **IK-Konfiguration** (S4-Schalter, #129 — anderer Lösungszweig verlegt den Arm), **Kipp/Lead-Sweep** (bahn-relativer Anstellwinkel dreht aus dem Hindernis) und **Platzierung** (andere Basis-Lage schafft Freiraum). Der reine Advisor ist von der realen Simulation über ein `simulate`-Callable **entkoppelt** (DOM-/IO-/Geo-frei, isoliert testbar); die Aktion `advise_collision` füttert die *echte* Slice+Trajektorien+Befund-Kette hinein (dieselbe Kern-Tür `fgc.pipeline.sectionsim.slice_and_simulate_section`, die auch `simulate_section` fährt).
- **Vorher/Nachher-Nachweis je Option:** Jede Zeile trägt **kollisionsfrei ja/nein** und **min. Abstand + Marge vorher/nachher** aus der Neu-Simulation. Es erscheinen **nur Verbesserer** — ein Kandidat, der die Kollision nicht beseitigt oder den minimalen Abstand nicht (über Rundungsrauschen hinaus) vergrößert, taucht nicht auf. Das **Ranking ist deterministisch**: kollisionsfrei zuerst, darunter größte Marge oben, feste Kandidatenreihenfolge als Tiebreak.
- **„Anwenden" = bestehende Setter (ADR-007/016):** Jede Option trägt ihre **Schreibstellen-Nutzlast**; der Ein-Klick-Knopf der Zeile schreibt ausschließlich über eine **bestehende** Route — IK-Konfiguration und Kipp/Lead über `PUT …/process-params` (die jeweils andere Gruppe bleibt erhalten), Platzierung über `PUT …/placement-override` — und stößt damit die **normale Veraltung/Neubewertung** an (die Liste veraltet danach; erneut prüfen). Der Advisor selbst schreibt nichts. Nach einer angewandten **Platzierungs-Option** zieht die UI Platzierungsfelder + ▪-Marker sofort nach (Parität zum Singularitäts-Advisor, Issue #161); Modul-Karte und Druckort-Bühne folgen dem frischen Stand (s. „Bühne folgt dem Simulationslauf"). **Entwertung wie beim manuellen Platzierungsfeld (Issue #172):** das „Anwenden" **beider** Advisors stößt dieselbe Neubewertung an wie eine manuelle Feldeingabe — Ampel, Druckbarkeits- **und** Kollisions-Badge des Teils gehen sofort sichtbar auf **„ungeprüft"** (das alte Urteil galt der alten Platzierung), gefolgt von der debouncten Neuprüfung durch den Core. So steht in der Modul-Karte nie ein neuer Override-Wert neben einem unmarkierten alten Urteil. Zusätzlich veraltet der **Druckplan-Output in den Core-Revisionen** bei jeder Platzierungs- oder Abschnitts-Override-Änderung an der Quelle (`fgc.project.revisions`: der Druckplan beobachtet die Summe der Pro-Abschnitts-Zähler) — der gespeicherte Zerlegungslauf trägt danach eine überholte Platzierung und wird als **veraltet** ausgewiesen (Wurzel-Fix von #161, Befunde B11/B16/B20/B32). Eine **Einzelfeld-Platzierungsoption** (Abstand **oder** Aufstellhöhe) **mergt** beim Anwenden mit dem bestehenden Override statt ihn neu aufzubauen (Issue #173): ein zuvor gesetztes freies Feld bleibt erhalten. Der Advisor hat den Kandidaten **mit** dem alten Override simuliert und bewertet — so entspricht der angewandte Zustand dem bewerteten Kandidaten, und die versprochene Marge gilt für die Platzierung, die das Anwenden tatsächlich herstellt. (Die Route `PUT …/placement-override` trägt dafür ein additives `merge`-Flag; das manuelle Platzierungs-Formular baut den Eintrag weiterhin neu auf — ein geleertes Feld räumt es ab.)
- **Read-only Urteil:** `POST /projects/{slug}/collision-advice` liefert die Basis-Metrik (`baseline`) und die `options` als **Daten** (kein Gate); fehlt Kollisionsgeometrie oder gibt es keinen Abschnitt, ist `baseline=null` und die Liste leer.
- **Ehrlicher Scope statt „global":** Der frühere statische Kopf-Hinweis **„global"** war falsch — geprüft wurde schon immer der fokussierte (sonst der erste) Abschnitt. Der Scope-Chip zeigt jetzt dynamisch das geprüfte Teil (`Fokus-Teil #N` bzw. „erstes Teil (kein Fokus)"), und die Statuszeile nennt Teil + erwartete Dauer. Das Accordion bleibt auch im **Teil-Modus** bedienbar (die #92 Ausgrau-Matrix ist unverändert). Viewer: reines State-Modul `collision-advisor-state.ts` (vitest) + dünne DOM-Klasse `collision-advisor.ts`, die die Optionsliste rendert.

### Abschnitts-Slicing + Simulation aus der Platzierung (Reiter Druckplan/Simulieren-Modus, Issue #26)

> Hinweis: „Reiter Simulation" unten meint seit der Modus-Fusion (#86) den **Simulieren-Bereich** im Reiter **Druckplan** — es gibt keinen eigenen Reiter Simulation mehr.

Aus dem Schnittplan (Reiter Druckplan) wird je **Abschnitt** ein druckbarer Lauf — **ohne CLI und ohne gemessenes Setup**. Der Reiter **Simulation** listet die Abschnitte in Druckreihenfolge (unten → oben); je Abschnitt lässt sich **„Slicen + Simulieren"** anstoßen (Busy-Zustand).

- **Abschnitts-Slicing:** Der Core schneidet aus dem Wand-Mesh das **Teil-Mesh** des Abschnitts (`fgc.decompose.apply`) und reicht es in den *bestehenden* Slicer (`slice_wall`, dessen Eingang dafür genutzt wird — der Slicer wird nicht dupliziert). Das Teil-Mesh wird zuvor ins **abschnitts-lokale** System verschoben (x um die Abschnittsmitte, z ab Abschnittsfuß), sodass die Targets im Abschnittsbereich liegen und zur abschnitts-lokalen Platzierung passen.
- **Simulation aus dem Plan:** Statt eines gemessenen Setups baut der Core die Lage Wand↔Roboterbasis aus der **geplanten Platzierung** des Abschnitts (`PlacementOption`) + dem Endeffektor-TCP und erzeugt daraus die Trajektorie (`fgc.simulation.build_trajectory`). Die Metadaten vermerken die Lagequelle: **`pose_source: "planned"`** (mit gemessenem Setup — z. B. `fgc simulate` — weiterhin `"measured"`). Das gemessene Setup bleibt Voraussetzung des **echten Drucks**; nur die Simulation ist aus dem Plan zulässig (Design-Log 2026-07-04).
- **Ein regulärer Lauf je Abschnitt:** Toolpath und Trajektorie landen in **einem** provenienz-gestempelten Lauf (ADR-004); der Druckjob verweist je Abschnitt darauf über `section_runs` (`section_id → Lauf`, ADR-016) — die Ergebnisse werden nie eingebettet.
- **Player im Reiter Simulation (Issue #48):** „Im Player ansehen" spielt den Abschnitts-Lauf **direkt im geteilten 3D-Hauptsichtfeld** ab und wird **im Reiter Simulation** bedient (Zeit-Slider, Play/Pause; TCP-Marker, Kapsel-Arm-Replay und io-Verlauf laufen in der geteilten Szene). Der Klick wechselt **nicht** mehr in den Reiter Projekt, und „Slicen + Simulieren" öffnet den Player **nicht mehr ungefragt** — die Kennzahlen erscheinen in der Zeile, das Replay startet man bewusst. Je Abschnitt zeigt die Zeile **Druckzeitschätzung, maximale Achsauslastung und Warnungszahl** (Kinematik-Warnungen aus `trajectory.meta`) — auch **nach dem Projekt-Neuladen** (die Kennzahlen werden lazy aus der `trajectory.json` des Abschnitts-Laufs nachgeladen, nicht nur „Lauf vorhanden" angezeigt).
- **Zurück zur Übersicht (Issue #48):** Weil das Replay die **Modellübersicht** (Schnittebenen, Basis-Marker) im geteilten 3D-Feld überblendet, gibt es im Player den Rückweg **„← Zurück zur Übersicht"** — er lädt den Übersichts-Lauf neu und baut Schnittebenen + Basis-Marker wieder auf (statt wie zuvor nur durch erneutes Projekt-Öffnen).
- **Deutliche Kennzeichnung:** „**Kinematisches Replay — keine Kollisionsprüfung**" (PRD Out of Scope). Der Player weist die Lagequelle „geplant" zusätzlich aus.

API: `POST /projects/{slug}/sections/{section_id}/simulate` (dünner Wrapper um die Aktion `simulate_section`). Die Formatier-/Zustandslogik des Reiters (Druckzeit, max. Achsauslastung, Zusammenfassung, Kennzahlen aus `trajectory.meta` per `summaryFromMeta`) ist als **reine TypeScript-Funktionen** von three.js getrennt (`ui/simulation-state.ts`) und mit vitest getestet.

### Wachsender Strang + Abschnitts-Sequenz mit Umbau-Schritt (Reiter Simulation, Issue #27)

Das Simulations-Replay wird vom Einzel-Abschnitt zum **Gesamtablauf** des Druckjobs. Zwei Bausteine, beide reine Darstellung (ADR-007 — der Viewer rechnet nichts, alle Dauern kommen aus `trajectory.meta`):

- **Wachsender Strang (Zeit statt Layer):** Beim Abspielen wächst der gedruckte Toolpath **zeitgetreu** mit — synchron zu Arm und TCP, konsistent bei Pause und Seek. Der Strang wird nach Trajektorien-**Zeit** aufgedeckt (normierter Fortschritt → Ziel-Target-Index, dieselbe Abbildung wie TCP-Marker/Arm), nicht mehr nur nach dem Layer-Slider; **Travel-Bewegungen erzeugen keinen Strang**. Der Schalter **„Strang wächst mit (Zeit)"** im Trajektorien-Panel schaltet zwischen Zeit-Aufdeckung (Wachs-Modus, Standard) und dem klassischen Layer-Slider (ganzer Toolpath) um. Umgesetzt als zweiter Modus in `ToolpathView` (`setGrowth`) über `geometry.setDrawRange` — nicht als Zweit-Renderer.
- **Abschnitts-Sequenz mit Umbau-Schritt:** **„Gesamtablauf abspielen"** (im Reiter Simulation, aktiv sobald **jeder** Abschnitt simuliert ist) spielt alle Abschnitte in **Druckreihenfolge** (unten → oben) über **eine Gesamtzeitleiste** ab — **im Reiter Simulation bedient** (Issue #48), mit „Zurück zur Übersicht" als Rückweg. Zwischen zwei Abschnitten läuft ein sichtbarer **Umbau-Schritt**: der Basis-Marker fährt zur nächsten Platzierung, eine Beschriftung im Player nennt den Wechsel (`#1 → #2`), und **bereits gedruckte Abschnitte bleiben stehen** (kumulativ, nicht zurückgesetzt). Der aktive Abschnitt wächst, Arm/TCP fahren seine Bahn.
- **Beide Zugänge bleiben:** Der **Einzelabschnitt** ist über „Im Player ansehen" (Issue #26) direkt anwählbar; die Sequenz ist ein zusätzlicher Modus, kein Ersatz. Druckjobs mit nur **einem** Abschnitt verhalten sich wie bisher (die Sequenz ist dann dieser eine Abschnitt ohne Umbau-Schritt — abwärtskompatibel).

Die Sequenz-/Zeitachsen-Logik (globale Zeit → Abschnittsindex + lokale Zeit + „im Umbau?", Aufbau der Gesamtzeitleiste aus den Abschnitts-Dauern + Umbau-Dauer) ist als **reine TypeScript-Funktionen** von three.js getrennt (`trajectory/sequence.ts`) und mit vitest getestet; die Basis-Sprung-Mathematik als `baseMarkerPosition` (`render/basemarker.ts`).

### Endeffektor-Konfigurator — Upload, Face-Align am Flansch, TCP per Fläche/Feld (Bibliothek, Issue #28/#52/#54/#58)

Der **Reiter Bibliothek** ist die Stammdatenpflege *außerhalb* des Prozesses (`viewer/CONTEXT.md`): ein realer Endeffektor wird hochgeladen, visuell am Roboter ausgerichtet und als projektunabhängiges Artefakt (`tools/<name>.json` + Mesh-Datei) abgelegt. Im Prozess (Reiter Roboter) wird ein Endeffektor nur *ausgewählt* — angelegt wird er hier.

- **Mesh hochladen:** STL, OBJ oder GLB. Die Mesh-Koordinaten werden als **mm** interpretiert (ADR-006). Der Core prüft Format, Größe (≤ 50 MB) und Ladbarkeit (kaputte/leere Dateien werden mit klarer Meldung abgelehnt — kein Absturz).
- **Am Flansch ausrichten (Face-Align, #52):** Die Szene zeigt den Roboter in **Home-Pose** (M1013-Mesh bzw. Kapsel-Arm, #18/#41) mit sichtbarem **Flansch-Koordinatensystem**. Beim Upload wird das Mesh zunächst **am Flansch zentriert** (damit es nicht an seinem Geometrie-Ursprung neben den Flansch schwebt). Statt eines fehleranfälligen Frei-Drag-Gizmos klickst du dann die **Montagefläche** des Mesh an — beim Überfahren wird die **ebene Fläche unter dem Cursor hervorgehoben** (#55), sodass vor dem Klick sichtbar ist, was gewählt wird: sie legt sich **bündig auf die Flanschebene** (Außennormale zeigt in den Arm, Körper ragt weg), der **Mittelpunkt der ganzen Fläche** — nicht der Klickpunkt — landet im Flansch-Ursprung (die Montage sitzt also auch bei ungenauem Klick exakt zentriert). Ein Zahlenfeld **dreht** zusätzlich um die Flansch-z-Achse. Das Ergebnis (Mesh-Lage relativ zum Flansch) sind **Daten** — direkt aus der Mesh-Geometrie gerechnet (`ui/face-align.ts`), nicht aus einer Gizmo-Objektlage zurückgelesen (das erzeugte am Flansch mit `matrixAutoUpdate=false` ein kaputtes TCP, #52).
- **TCP (drei Wege, #54):** Der rote **TCP-Marker** (Werkzeugarbeitspunkt, z. B. Düsenspitze) sitzt per Default **automatisch** auf dem entlang +Flansch-z am weitesten entfernten Mesh-Punkt (die Spitze). Trifft die Heuristik nicht die Öffnung: **„TCP-Fläche wählen"** drücken und die Fläche der **Extruderöffnung** anklicken — der TCP springt auf den **Mittelpunkt der zusammenhängenden ebenen Fläche** (Region-Growing um das getroffene Dreieck, nicht nur das eine Dreieck; die Fläche ist mesh-lokal gemerkt und rechnet bei Montage-Änderungen mit). Der Modus bleibt zum **Nachjustieren aktiv** (Hover-Hervorhebung rot statt orange), bis der Button ihn beendet — Klicks montieren währenddessen nichts um (#55). Alternativ die **x/y/z-Felder** (mm, relativ zum Flansch-Ursprung) direkt editieren — sie zeigen immer den aktiven TCP; alle drei Felder leeren kehrt zu **automatisch** zurück. Der TCP wird relativ zum Flansch gespeichert (`tcp_frame`, ADR-006) — exakt im Format, das **Platzierung und Simulation** bereits lesen (#21/#26).
- **Düsenrichtung aus der Öffnungsnormale (#58):** Der Öffnungs-Klick setzt nicht nur die TCP-**Position**, sondern auch dessen **Orientierung** — die **TCP-z-Achse = Extrusions-/Düsenachse** wird auf die nach außen zeigende Normale der angeklickten ebenen Öffnungsfläche gedreht (reine Ableitung `nozzleQuatFromNormal`, mit Golden-Werten vitest-getestet). Damit ist ein **frisch angelegtes Werkzeug ab dem Klick korrekt orientiert**: die kanonische Druck-Orientierung „Düse nach unten" (`NOZZLE_DOWN`, Core) führt in der Simulation die **echte Düse senkrecht nach unten** statt der Flanschachse — der Readout zeigt die aktuelle **Düsenachse** neben der Position. Früher blieb die `quat` Identität, sodass die Extrusionsrichtung fälschlich auf der Flansch-z-Achse lag und die Düse horizontal druckte (löst den `30gut`-Stopgap sauber ab). **Rückwärtskompatibel:** die automatische/manuelle TCP-Quelle bleibt bei Identität, bestehende Werkzeuge laden unverändert (ADR-007: der Viewer übergibt das volle Frame, der Core validiert).
- **Feinversatz der Montage (#67):** Drei Felder **„Versatz am Flansch (mm)"** (x/y in der Flanschebene, z axial) schieben die berechnete Montage-Basis flansch-lokal nach — nützlich, wenn die Montagefläche größer oder asymmetrisch ist und ihr flächengewichteter Mittelpunkt nicht der Flanschmitte entspricht. Der **TCP wandert mit**, die bündige Ausrichtung bleibt erhalten. Der Versatz wird beim Laden eines **neuen Mesh zurückgesetzt** (er galt der alten Fläche).
- **Stammdaten + Kanäle:** Formular für Name, Hersteller, Gewicht/Schwerpunkt und die Deklaration der **logischen Kanäle** (ADR-011; z. B. `pump_a`, `pump_b`, `foam` — analog/digital). Der Endeffektor *deklariert* die Kanäle; das Setup mappt sie später auf physische Ausgänge.
- **Speichern:** `POST /tools` validiert (Format/Größe/Ladbarkeit/**Schema**) und legt Mesh-Datei + `<name>.json` im Tools-Verzeichnis ab. Der neue Endeffektor ist **ohne Neustart** im Katalog (Reiter Roboter) wählbar und im Druckjob übernehmbar; der dortige Payload-Check (Gewicht vs. Traglast) bleibt ein **Befund, kein Gate** (#21).
- **Mesh im Replay:** Hat der Endeffektor eines Druckjobs ein Mesh, hängt es im Simulations-Replay (#18/#27) am **Flansch** des Arms (an der im Konfigurator gesetzten `mesh_transform`-Lage). Ohne Mesh bleibt das Replay wie bisher (abwärtskompatibel).

Das Schema `tool.schema.json` wurde rückwärtskompatibel um das optionale Feld **`mesh_transform`** (Lage des Mesh relativ zum Flansch) erweitert; `mesh` (Dateiname) gab es bereits. Die Speicher-Aktion `create_tool_from_upload` (Kern: `fgc.domain.tool.build_tool_artifact`/`validate_mesh_bytes`/`safe_tool_name`) ist mit pytest abgedeckt (Upload-Validierung, Schema-Validität, TCP-Konsistenz mit placement/simulation); die **Face-Align-Mathematik** (Montage-Frame + Auto-TCP) und Formular→Payload als reine TypeScript-Funktionen (`ui/face-align.ts` + `ui/configurator-payload.ts`, vitest). Der Raycast-Klick und die 3D-Anzeige selbst sind bewusst ohne Test (PRD Testing Decisions), visuell geprüft.

**Tool-Hüllmaß beim Upload (`envelope_mm`, ADR-026 Punkt 4, PRD #225, Issue #229):** Beim Speichern eines Endeffektors mit Mesh berechnet der Core einmalig eine Hüllkennzahl — **Bounding-Radius um die Flanschachse** (größter radialer Abstand eines Mesh-Punkts zur Flansch-z-Achse) **+ Länge entlang ihr** (z-Ausdehnung) — und speichert sie additiv im Tool-Artefakt (`fgc.domain.tool.compute_tool_envelope`, gerechnet im Flansch-Frame über die gesetzte `mesh_transform`, Default Identität). Sie ist die zweite Größe der Tool-Ähnlichkeits-Regel des Platzierungs-Priors (neben dem TCP-Versatz): ein nicht vermessenes Tool profitiert vom Prior, wenn ‖Δ TCP-Versatz‖ **und** Δ Hüllmaß innerhalb der eingestellten Sicherheitszone liegen. Die Rechnung passiert **nur beim Upload** (trimesh läuft dort ohnehin für die Mesh-Validierung) — der spätere Platzierungs-Vorschlagspfad lädt nie ein Mesh. **Migrationslogik wie `compatible_robots` (#71):** Altbestand ohne `envelope_mm` lädt unverändert und gilt als „unbekannt" (⇒ neutraler Prior); `build_tool_artifact` schreibt das Feld nur, wenn tatsächlich berechnet — ein Tool ohne Mesh bleibt ohne das Feld (kein Raten). Beim **Bearbeiten** (`update_tool_from_upload`, #56) wird das Hüllmaß nur bei tatsächlich neu hochgeladenem Mesh neu berechnet; bleibt das Mesh unverändert (reine Metadaten-/Ausrichtungs-Änderung), bleibt der bisherige Wert erhalten. `GET`/`POST`/`PUT /tools` tragen `envelope_mm` durch (`EnvelopeModel`, `{radius_mm, length_mm}`). Getestet: deterministische Werte an bekannten Quader-Meshes (Identität/Translation/Rotation der `mesh_transform`), Altbestands-Round-Trip byte-gleich ohne das Feld, Update mit/ohne neues Mesh, API-Round-Trip.

### Bibliothek: Endeffektoren verwalten — Übersicht, Bearbeiten, Löschen (Issue #56)

Der Reiter **Bibliothek** ist nicht mehr nur „neu anlegen", sondern eine echte Endeffektor-Bibliothek mit zwei Ansichten im selben Reiter:

- **Übersicht (Galerie):** Beim Öffnen des Reiters erscheinen **Karten** aller angelegten Endeffektoren (`GET /tools`) — je Karte ein **Mesh-Vorschaubild**, der **Name** und die wichtigsten **Stammdaten** (Hersteller, Gewicht). Oben rechts der prominente Button **„+ Neuer Endeffektor"**; ist die Bibliothek leer, zeigt sie einen klaren **Leerzustand** statt einer leeren Fläche. Pro Karte: **„Bearbeiten"** und **„Löschen"**.
- **Vorschaubilder (clientseitig, gecacht):** Der Viewer rendert die Thumbnails **live** aus dem Mesh (three.js-Offscreen-Standbild, `ui/tool-thumbnail.ts`) — kein serverseitiges PNG. Ein **Cache** (In-Memory + `localStorage`, Key = `mesh_path`) macht das Bild beim erneuten Öffnen **sofort** sichtbar; ändert sich das Mesh, wird neu gerendert. Lädt/rendert ein Mesh nicht (Altbestand ohne Datei, kaputtes Mesh), zeigt die Karte einen **Platzhalter** statt abzustürzen.
- **Editor:** „+ Neuer Endeffektor" und „Bearbeiten" öffnen **denselben** 5-Schritt-Konfigurator (s. o.). Beim **Bearbeiten** ist er mit dem gewählten Endeffektor **vorbefüllt** — gespeichertes **Mesh** (kein Re-Upload nötig), **Ausrichtung** (`mesh_transform`) und **TCP** (`tcp_frame`, inkl. Düsenrichtung) werden **exakt** wiederhergestellt (keine ungewollte Neu-Zentrierung), dazu Kanäle und Stammdaten. Der **Name ist gesperrt** (Read-only) — er ist die Identität, auf die Druckjobs per String verweisen (**kein Rename**). Ein Mesh lässt sich optional neu hochladen; ohne neuen Upload bleibt das bestehende erhalten. **„Zurück zur Übersicht"** kehrt ohne Speichern zurück; nach dem Speichern landet man automatisch wieder in der Galerie (mit aktualisiertem Vorschaubild).
- **Löschen:** Ein **Bestätigungsdialog** geht voran; danach entfernt der Core **`<name>.json` UND die Mesh-Datei** (`DELETE /tools/{name}`). Es gibt v1 **keinen** projektübergreifenden „ist-in-Verwendung"-Check.
- **Katalog-Konsistenz:** Nach **Anlegen, Bearbeiten oder Löschen** frischt der Viewer sowohl die **Galerie** als auch das Endeffektor-Dropdown im Reiter **Roboter** (`#tool-select`) auf — der Bestand bleibt überall synchron, ohne Neustart.

**Core-API (ADR-014/016, einzige Schreibstelle im Core):** neu `PUT /tools/{name}` (Bearbeiten; Mesh optional — ohne neues Mesh bleibt die Datei erhalten, `name`/Identität fix) und `DELETE /tools/{name}` (Definition + Mesh; 404 bei unbekanntem Namen). Kern-Logik als testbare Aktionen `update_tool_from_upload` / `delete_tool` (pytest: Update mit/ohne Mesh, Formatwechsel entfernt das alte Mesh, 404, Mesh-Validierung nur bei geliefertem Mesh). `GET /tools` liefert jetzt zusätzlich `tcp_frame`, damit der Editor den gespeicherten TCP wiederherstellen kann. Viewer-Tests: Update-Payload-Bau (Mesh weglassen/mitschicken, Name gesperrt — vitest), Thumbnail-Cache (vitest) und ein DOM-Struktur-Smoke der Galerie (Karten/Leerzustand/Umschalten — vitest, jsdom). Die Editor-3D-Anzeige selbst bleibt bewusst ohne Test (PRD Testing Decisions).

### Bibliothek: Endeffektor-Kompatibilitäts-Tags (`compatible_robots`, Issue #71)

Jeder Endeffektor kann eine Liste **„passt zu Roboter(n)"** tragen (`compatible_robots`) — die Roboter, für die er vorgesehen ist. Der **Roboter ist die Nabe**; der Endeffektor verweist auf ihn.

- **Editor-Feld:** In den **Stammdaten** des Konfigurators gibt es ein **Mehrfach-Auswahlfeld** „passt zu Roboter(n)", befüllt aus `GET /robots`. Die Wahl wird beim Speichern (`POST`/`PUT /tools`) mitgeschickt und beim **Bearbeiten korrekt vorbefüllt**.
- **Migrationsschutz:** Ein Endeffektor **ohne** Tags (Altbestand) lädt und speichert **unverändert** — das Feld wird nicht erzwungen. **Keine Auswahl = „unbekannt", nicht „inkompatibel"**: der Endeffektor bleibt für jeden Roboter wählbar. Fehlt das Feld oder ist es leer, schreibt der Core es gar nicht ins Artefakt.
- **Noch keine Filterwirkung:** Dieser Slice führt nur das **Feld** ein, das round-trippt und nach Neuladen erhalten bleibt. Das **Ausgrauen** inkompatibler Endeffektoren im Reiter Roboter (mit Warnung, kein Gate) folgt in #74.

Das Schema `tool.schema.json` wurde rückwärtskompatibel um das optionale Feld **`compatible_robots`** (Array von Roboter-Namen) erweitert (`additionalProperties: false` bleibt gültig). Das Feld läuft additiv durch die gesamte Kette: `ToolDef`, `build_tool_artifact`, Create/Update-API-Modelle, `GET /tools`-Antwort und den Editor. Tests: pytest-Roundtrip mit/ohne `compatible_robots` (Domäne + API), vitest-Payload-Bau (Feld wird durchgetragen, entdoppelt, leer bleibt leer).

### Reiter Roboter: Kompatibilitätsfilter — inkompatibles Zubehör ausgrauen + warnen (Issue #74)

Die in #71 eingeführten `compatible_robots`-Tags bekommen jetzt **Filterwirkung** in der Endeffektor-Auswahl (Reiter Roboter). Eine winzige, reine Funktion `is_compatible(compatible_robots, active_robot)` beantwortet die eine Frage „passt Zubehör X zum aktuell gewählten Roboter?" — **getaggt + passend → ja, getaggt + fremd → nein, leer/fehlend → unbekannt = ja** (Migrationsschutz; der **Roboter ist die Nabe**). Die Funktion liegt **verhaltensgleich doppelt** vor: `core/src/fgc/domain/compat.py` (Core) und `viewer/src/ui/compat.ts` (Viewer), mit geteilten Golden-Fällen (pytest ↔ vitest).

- **Ausgrauen, aber wählbar:** Inkompatible Endeffektoren erscheinen im Dropdown **ausgegraut** (CSS-Klasse `option-incompatible`), bleiben aber **auswählbar** — kein `disabled`. **Befund, kein Gate** (ADR-013): der Filter sperrt nichts.
- **Warnung bei Roboterwechsel:** Wird ein **bereits gewählter** Endeffektor durch einen Roboterwechsel inkompatibel, erscheint eine **Warnung** (analog zur Payload-Warnung, gleiches inline-Element). **Kein Auto-Reset**, keine Persistenz-Nebenwirkung — die Wahl bleibt bestehen.
- **Ungetaggtes Zubehör** bleibt für **jeden** Roboter normal wählbar (kein Ausgrauen, keine Warnung).

Der aktive Roboter kommt über den bestehenden Roboter→ToolPanel-Leseweg (`setActiveRobot`, parallel zu `setRobotPayload`). Die Ausgrau-/Warn-Entscheidung steckt in reinen Funktionen (`incompatibleToolNames`, `compatibilityWarning`); das DOM-Wiring im `ToolPanel` ist davon getrennt (Split-Muster wie `simulation-state`/`cutplan-state`). Tests: pytest-Golden-Fälle (`test_compat.py`), vitest für Ausgrau-Menge + Warn-Logik (`compat.test.ts`).

### Bibliothek: Workstation-Entity — Aufstell-Umgebung des Roboters (Core+API, Issue #72)

Die **Workstation** ist die Aufstell-Umgebung des Roboters als eigenes, projektunabhängiges Stammdaten-Artefakt (`workstations/<name>.json`) — analog zum Endeffektor (`tools/`). **Eine** Entity bildet per `mobility`-Feld beide Ausprägungen ab: die **stationäre Zelle** (`stationary`, fester Aufstellort) und die **mobile Workstation** (`mobile` — fährt zur Wand, druckt vor Ort). Dieser Slice ist **Core+API** (die Bibliotheks-UI folgt in #75).

- **Höhenmodell (Branch am `height_adjustable`):** nicht-verstellbar → ein geordneter Satz **`base_heights_mm`** (Podesthöhen, streng aufsteigend, **enthält 0** = Bodenhöhe); verstellbar → ein stufenloser **`height_range_mm`** `{min, max}` mit `min < max`. Diese Konsistenz ist eine **Domänen-Regel über das rohe Schema hinaus**: das Schema erlaubt beide Felder, `WorkstationDef.load`/`build_workstation_artifact` erzwingen den Zweig und werfen bei Verstoß einen klaren `ValueError` (API → 422).
- **Weitere Felder:** `safety_min_distance_mm` (Mindest-Sicherheitsabstand zur Wand, **Default 50**), `vendor` (optional) und `compatible_robots` (Kompatibilitäts-Tags wie beim Endeffektor, #71; leer = „unbekannt", nicht „inkompatibel"). Kein Mesh, kein Upload — reine strukturierte Zahlenfelder.
- **CRUD-API:** `GET/POST/PUT/DELETE /workstations` (dünne Aktions-Wrapper, Pydantic-Modelle wie `/tools`). **Schreiben ist atomar** (Temp-Datei + `os.replace`, ADR-018 — dasselbe Muster wie `write_project`, serialisiert je Datei über einen `workstation_lock`), **nicht** das nicht-atomare Tool-Write-Muster. `POST` überschreibt bei Namensgleichheit (Stammdaten-Pflege); `PUT`/`DELETE` liefern **404** bei unbekannter Workstation.

Schema: `schemas/workstation.schema.json` (`additionalProperties: false`), registriert in `domain.VALIDATABLE_KINDS`. Zwei Referenz-Definitionen liegen bei: `workstations/zelle_fest.json` (stationär, feste Podesthöhen 0/200/400) und `workstations/mobile_hub.json` (mobil, höhenverstellbar 0–600 mm). Tests: pytest-Roundtrip stationär + mobil + höhenverstellbar, Höhen-Branch-Regel, Schema-Validierung (`additionalProperties`/`mobility`), CRUD-API inkl. atomarer Schreibprüfung und 404.

### Bibliothek: Rubriken-Umschaltung + Workstation-Galerie & -Editor (UI, Issue #75)

Der Reiter **Bibliothek** wird in **drei Rubriken** aufgeteilt — **Roboter · Endeffektor · Workstation** —, umgeschaltet oben über eine Reiter-Leiste. Die Umschaltung nutzt **ausschließlich das `.hidden`-Attribut** (das globale `[hidden]{display:none!important}` schlägt jedes `display:flex`); nie `display:none/flex`, sonst kehrt der tote-Reiter-Bug wieder (Lehre aus #56).

- **Rubrik Roboter:** die schreibgeschützte Roboter-Galerie (s. **Issue #76** unten).
- **Rubrik Endeffektor:** die **bestehende** Endeffektor-Galerie + Konfigurator (#28/#56), unverändert, nur unter die neue Rubrik einsortiert.
- **Rubrik Workstation (neu):** spiegelt die Endeffektor-Galerie, aber **ohne Mesh/WebGL**. Jede **Karte** zeigt eine schlichte **SVG-Grafik** (Podeststapel bzw. Rampe bei verstellbar), einen **Typ-Badge** (stationär/mobil) und eine **Höhen-/Abstands-Zusammenfassung** (N Podeste + Bereich bzw. `min–max` bei verstellbar, Sicherheitsabstand). Leerzustand + prominenter **„+ Neue Workstation"**. Pro Karte **Bearbeiten**/**Löschen** (mit Bestätigung); nach Anlegen/Bearbeiten/Löschen frischt die Galerie über die `/workstations`-API auf.
- **Editor = reines Formular** (kein Gizmo, kein WebGL): Typ-Wahl, **„höhenverstellbar"-Toggle** (blendet zwischen **diskreter Podestliste** und **min/max-Bereich** um — wieder nur über `.hidden`), Podesthöhen-Zeilen (hinzufügen/entfernen) bzw. min/max, **Sicherheitsabstand** (Default 50), **Roboter-Kompatibilitäts-Tags** (Mehrfachauswahl aus `GET /robots`, #71-Muster). **Bearbeiten befüllt exakt vor** und **sperrt den Namen** (kein Rename, #56-Muster). Verletzt die Eingabe die Höhen-Branch-Regel, meldet erst die Client-Vorprüfung, sonst der **Core-422** freundlich im Editor.

Die Fach-Umrechnung liegt rein und testbar getrennt vom DOM: `ui/workstation-payload.ts` (Formular→Request, Workstation→Formular, Karten-Zusammenfassung + SVG) und `ui/library-rubrics.ts` (Rubrik-Toggle); `ui/workstation-library.ts` besitzt nur das DOM und ruft die API über Callbacks (ADR-007). Getestet: vitest deckt die Payload-/Formularlogik (Branch-Regel, Vorbefüllung, Round-Trip, Zusammenfassung), die Galerie-DOM-Smoke (Karten/Leerzustand/Editor-Toggle/Speichern/Löschen), den Rubrik-Toggle und den HTML-Struktur-Vertrag (`shell-structure.test`: alle drei Rubrik-Sichten) ab.

### Bibliothek: Roboter-Galerie (read-only) + statisches PNG-Thumbnail (UI, Issue #76)

Die **Rubrik Roboter** der Bibliothek zeigt den Roboterbestand aus `GET /robots` als **schreibgeschützte Galerie** — je Roboter eine **Karte** mit den Kern-Stammdaten (**Name, Reichweite, Traglast**, dazu die Druckraum-Hüllwerte + `(vorläufig)`-Marker) und einem **statischen, eingecheckten PNG-Thumbnail** (kein Live-FK-Render). Ein **`read-only`-Badge** und der Verzicht auf jede Anlegen-/Bearbeiten-/Löschen-Aktion machen sichtbar: hier wird **nicht** editiert.

- **Warum read-only:** ein funktionsfähiger neuer Roboter verlangt roboterspezifische **Solver-Konstanten** (`_START`/`_SIGNS`), vendored **per-Glied-Meshes** und die **Viewer-DH** — das ist Entwickler-/Vendoring-Arbeit, kein Formular (Scope-Klärung im Parent #69). Das additive `errors`-Feld aus #73 wird in dieser read-only-Galerie ignoriert (kein Absturz, wenn vorhanden).
- **Thumbnail-Verortung:** je Roboter unter `./robots/<slug>/thumbnail.png` neben den GLBs (#40/#41); der Slug streicht einen Hersteller-Präfix (`doosan_m1013` → `m1013`). **Fehlt das PNG**, ersetzt ein `img.onerror`-Handler das Bild durch einen **Platzhalter** („Kein Vorschaubild") statt eines Absturzes.
- **M1013-PNG:** einmalig erzeugt und eingecheckt unter `viewer/public/robots/m1013/thumbnail.png` (480×360, gültiges PNG). Erzeugt vom abhängigkeitsfreien Skript `viewer/scripts/gen_robot_thumbnail.mjs` (nur `node:zlib`), das eine stilisierte Arm-Silhouette in Platzhalter-Qualität malt — kein Headless-WebGL (der CDP-Smoke-Harness braucht Core+Vite+Edge+Projekt, offline nicht deterministisch lauffähig). Ein echter FK-Render kann das PNG später ersetzen (Design-Log 2026-07-07).

Die Formatierung + die Roboter→PNG-Abbildung liegen rein und DOM-frei in `ui/robot-library-payload.ts` (`summarizeRobot`, `robotSlug`, `robotThumbnailPath`); `ui/robot-library.ts` besitzt nur das DOM und lädt read-only über einen `loadRobots`-Callback (ADR-007). Getestet: vitest deckt die reine Payload-Logik (Stammdaten-Formatierung, unbekannte Traglast, Slug/PNG-Pfad) und die Galerie-DOM-Smoke ab (Karten mit Name/Reichweite/Traglast + Thumbnail, **keine** Aktions-Buttons, Platzhalter bei fehlendem Bild, Leerzustand, Lade-Gate an der API-Verfügbarkeit).

### Export — DRL je Abschnitt + Übergabe-Checkliste, veraltet-Markierung (Reiter Export, Issue #29)

Der **Reiter Export** schließt den Prozess ab und sichert die **Querschnitts-Konsistenz** zwischen den Reitern.

- **DRL je Abschnitt:** Je Abschnitt (Druckreihenfolge, muss zuvor im Reiter Simulation simuliert sein) lässt sich mit **„DRL exportieren"** ein DRL-Programm erzeugen (`program.drl` im Abschnitts-Lauf, ADR-004). Der Core nutzt dafür die **bestehende Emit-Aktion** (`fgc.postproc.emit_drl`, #13) als dünnen Wrapper (`export_section_drl`, API `POST /projects/{slug}/sections/{section_id}/export`) — nicht neu implementiert.
- **Setup je Zerlegungsart — Antasten (Abschnitt) vs. generiert (Modul):** Das Setup bleibt die eine Transformationsstelle (ADR-006), wird aber je **Zerlegungsart** anders befüllt. Bei **Art „abschnitt"** gilt das gemessene Setup: liegt im Abschnitts-Lauf ein `setup.json` mit Kanal-Mapping (ADR-011), entsteht ein **vollständiges** DRL; fehlt es (Regelfall bis zum Antasten), erscheint der **sichtbar gekennzeichnete Antasten-Hinweis** (`setup_source: "none"`). Bei **Art „modul"** (ADR-022, s. u.) **generiert** der Export das Setup selbst — der manuelle `setup.json`-Schritt entfällt. Kein Gate (ADR-006/013): die Ausgabe entsteht so oder so, nur sichtbar gekennzeichnet.
- **Übergabe-Checkliste:** **aufbauen → antasten (→ Setup) → drucken**, mit dem Kernsatz *„Die Platzierung ist ein Plan — verbindlich wird die Lage erst durchs Antasten"* (ADR-006, `core/CONTEXT.md`).
- **veraltet-Markierung (Querschnitts-Konsistenz):** Ändert sich Vorgelagertes — **Wand, Roboter, Endeffektor** oder **Schnittplan** — werden nachgelagerte Stände (**Druckplan, Simulation, Export**) als **veraltet** markiert: sichtbar (Badges je Stufe), **nicht gelöscht**. Ein Roboterwechsel (Reiter Roboter) veraltet z. B. alle drei; die Neubewertung/Neuerzeugung der jeweiligen Stufe hebt die Markierung **stufenweise** auf. Grundlage sind **Revisionsstände** im Druckjob (`project.json` → `print_job.revisions`): ein Zähler je Eingabe-Stufe und je Output der Schnappschuss der Zähler zum Zeitpunkt der letzten Erzeugung. Das **Setzen** der Revisionen passiert ausschließlich im Core (`fgc.project`, einzige Schreibstelle, ADR-016); die **Ableitung** „ist X veraltet?" ist eine **reine TypeScript-Funktion** (`ui/staleness.ts`, deterministisch mit vitest getestet, ADR-007) mit einer Python-Parität (`fgc.project.output_status`). Altprojekte ohne Revisionsfeld gelten als **nicht veraltet** (rückwärtskompatibel).

Getestet: pytest deckt die Export-Aktion ab (vollständiges DRL mit Setup, gekennzeichneter Antasten-Hinweis ohne Setup, Fehlerfälle, API-Wrapper) und das Revisions-Setzen in `fgc.project` (Roboterwechsel bumpt die Eingabe-Revision, Neuerzeugung frischt die Output-Revision auf); vitest deckt die Veralterungs-Ableitung ab (Roboterwechsel veraltet alle drei Stufen, stufenweises Aufheben, Altprojekte nicht veraltet).

### Modul-Export — Setup aus Stammdaten generieren, Gate „nichts Provisorisches" (Reiter Export, Issue #136)

Der erste Realdruck sind **Module** an der Workstation (ADR-022): Roboterbasis und Druckfläche sind auf **derselben Platte verschraubt**, die Relativpose steht konstruktiv fest (x, y, yaw **und** z), das Modul steht zentral. **Auf diesem Pfad wird nichts angetastet.** Bei Zerlegungsart **Modul** generiert der Export das Setup deshalb **selbst** aus Stammdaten, statt ein gemessenes `setup.json` zu verlangen:

- **Woraus das Setup entsteht:** Workstation-Frames (`robot_base_frame`/`work_surface_frame` → feste Platzierung, `_module_placement`) + Werkzeug-TCP (`tool.tcp_frame`) + Workstation-`io_channels`/`deadtime`. Das generierte Setup trägt **dieselbe** `wall_to_base` wie die Simulation (`_planned_setup`, z-Offset 0) — generiertes Setup ∘ Slicer-Target == geplante TCP-Pose in Basis (Ketten-Orakel). `setup_source` heißt ehrlich **`generated`** (nicht fälschlich `measured`).
- **S1-Werte wohnen an der Workstation:** `io_channels` (Verkabelung, ADR-011) und `deadtime` (Totzeit, ADR-012) sind seit #136 **additive, optionale** Workstation-Stammdaten-Felder (Muster ADR-021) — Eigenschaften des Aufbaus, nicht des Werkzeugs. Sie kommen aus **Spike S1**; bis dahin ggf. mit `deadtime.provisional: true`. Altbestand ohne die Felder gilt als **„unbestätigt"** und lädt unverändert.
- **Gate „nichts Provisorisches" statt Datei-Existenz:** Der Export prüft, ob **kein beteiligter Wert fehlt oder provisorisch ist** — Frames vorhanden, Endeffektor gewählt und TCP **nicht** provisorisch (neues optionales `tcp_provisional`-Feld am Endeffektor), `io_channels` bestätigt, Totzeit gemessen (nicht provisorisch). Ist alles bestätigt → **vollständiges** DRL (`complete=true`, `setup_source: "generated"`). Fehlt etwas → wie bisher ein Kommentar-Stub, aber mit **konkret benanntem Fehlbestand** („es fehlt: …", `setup_source: "generated_incomplete"`). **Befund, kein Gate** (ADR-013-Geist): exportieren geht immer, nur sichtbar gekennzeichnet.
- **Art „abschnitt" unverändert:** der gemessene `setup.json`-Pfad bleibt, bis die Wieder-Registrierung (#116) existiert.

Getestet: pytest deckt den generierten Modul-Export ab (vollständiges DRL bei bestätigten Stammdaten inkl. Ketten-Orakel; je fehlendem/provisorischem Baustein — Frames, io_channels, Totzeit, TCP, Endeffektor — ein Stub mit benanntem Fehlbestand), den Altbestand-Load (Workstation ohne die neuen Felder → `None`) und den Round-Trip der additiven Felder (`io_channels`/`deadtime` an der Workstation, `tcp_provisional` am Endeffektor).

### `fgc setup new` — Aufspannung kalibrieren (3-Punkt-Antastverfahren, ADR-006, §9.3)

Das Setup-Artefakt `setup.json` ist die eine Stelle, an der Bauteilwelt und
Roboterwelt verheiratet werden: Lage der Wand relativ zur Roboterbasis
(`wall_to_base`-Frame), Werkzeug-TCP, Kanal-Mapping und Totzeit.

`fgc setup new` berechnet den `wall_to_base`-Frame aus drei Punkten, die am
Roboter angetastet werden — Industriestandard-Dreipunkt-Verfahren, auch als
„Frame-Teach" am Teach-Pendant bekannt.

#### Schritt-für-Schritt (Hiwi-Anleitung)

**Vorbereitung:** Roboter einschalten, Sicherheitsbereich freigeben, Extruder
montieren (oder Dummy-Spitze einschrauben). Roboter in eine sichere
Ausgangsstellung bringen.

**Punkt 1 — Wandursprung (P0):**
1. Roboter so verfahren, dass die Düsenspitze exakt am gewünschten
   Wandnullpunkt steht (typisch: Vorderkante unten links der Druckfläche,
   Einblasseite des Extruders auf Wandoberfläche).
2. Am Teach-Pendant die aktuelle TCP-Position ablesen (Basis-Koordinaten):
   `X, Y, Z` in mm — Werte notieren.
3. Eingabe: `P0 (x,y,z in mm): 1023.4,−217.8,12.0`

**Punkt 2 — X-Achse (P1):**
4. Roboter mindestens 100 mm entlang der Wandlänge bewegen (ohne dabei die
   Orientierung zu ändern — reines TCP-Translieren).
5. Erneut die aktuelle Position ablesen und notieren.
6. Eingabe: `P1 (x,y,z in mm): 1223.4,−217.8,12.0`

**Punkt 3 — XY-Ebene (P2):**
7. Zurück zu P0. Dann mindestens 50 mm in Wandhöhenrichtung bewegen
   (d. h. senkrecht zur X-Achse, aber in der Wandfläche — typisch: Roboter
   aufwärts verfahren, ohne Rotationsänderung).
8. Position ablesen und notieren.
9. Eingabe: `P2 (x,y,z in mm): 1023.4,−217.8,112.0`

**Kommando ausführen:**

```powershell
# Interaktiv (promptet für P0, P1, P2):
.\fgc setup new --output examples\setup_wand1.json

# Oder mit direkt angegebenen Posen (z. B. aus Protokoll):
.\fgc setup new \
  --p0 1023.4,-217.8,12.0 \
  --p1 1223.4,-217.8,12.0 \
  --p2 1023.4,-217.8,112.0 \
  --robot doosan_m1013 \
  --output examples\setup_wand1.json
```

**Ergebnis prüfen:**

```
setup.json:   C:\…\examples\setup_wand1.json
wall_to_base: pos_mm=[1023.4, -217.8, 12.0]
              quat  =[1.0, 0.0, 0.0, 0.0]
robot:        doosan_m1013
```

Das `quat`-Feld gibt die Wandorientierung als Quaternion `[w, x, y, z]` aus
(ADR-006). Für eine Wand parallel zur Basis-XY-Ebene ist es die Identität
`[1,0,0,0]`; bei geneigten oder schräg stehenden Wänden weicht es ab. Wert
plausibel prüfen: bei kleinen Wandneigungen sollte `w ≈ 1` gelten.

**Provisorische Werte ohne `--template`:**
TCP (Düse 200 mm entlang Flansch-Z), Kanal-Mapping (Pump A/B → AO0/AO1
0–10 V, Schaum → AO2 0–5 V) und Totzeit (3,0 s) sind provisorisch markiert
(`deadtime.provisional: true`). Sie müssen nach Spike S1/S1b mit gemessenen
Werten aktualisiert werden. Existiert bereits ein kalibriertes Setup, können
TCP, IO-Kanäle und Totzeit daraus übernommen werden:

```powershell
.\fgc setup new --p0 … --p1 … --p2 … \
  --template examples\setup_kalibriert.json \
  --output examples\setup_wand2.json
```

#### Koordinatensystem-Konvention (ADR-006)

| Achse | Richtung |
|---|---|
| X | Wandlänge (von P0 nach P1) |
| Y | Wandhöhe (von P0 nach P2, senkrecht zu X in der Wandfläche) |
| Z | Wandnormale (X × Y, rechtshändig — zeigt von der Wand weg) |

Alle Koordinaten in mm, Quaternionen `[w, x, y, z]` nach ADR-006.

**Degenerierte Eingaben** werden mit verständlicher Fehlermeldung abgelehnt:
- P0 = P1 oder P0 = P2 (identische Punkte) → Abbruch
- P2 liegt auf der X-Achse (P0, P1, P2 kollinear) → Abbruch

### Kinematik-Kern Doosan M1013 — FK/IK (Issue #7, Spike S3)

Vorwärts- und Inverskinematik für die Primärplattform Doosan M1013. Der Solver
ist der analytische **OPW-Solver** (Ortho-Parallel-Basis + Spherical Wrist), aus
visose/Robots (MIT) nach Python portiert (`fgc.kinematics.opw`, Attribution in
[`NOTICE`](NOTICE), ADR-002/ADR-010). Solverwahl gegen den Robots-Quellcode
verifiziert: Der M1013 nutzt dort `SphericalWristKinematics` (OPW), **nicht** den
Offset-Wrist-Solver (der ist für Universal Robots) — Befund im
[Spike-Protokoll S3](docs/spikes/S3_ik_roundtrip.md).

Einheiten strikt nach ADR-006: Position in mm, Winkel in Radiant, Orientierung
als Quaternion `[w, x, y, z]`. Die Geometrieparameter (DH: `a`, `d`, `alpha`;
Achsgrenzen) liegen im `kinematics`-Block von `robots/doosan_m1013.json`.

```python
from fgc.kinematics import OpwKinematics

kin = OpwKinematics.from_robot("doosan_m1013")
frame = kin.forward([0.2, -0.4, 0.7, 0.1, 0.8, -0.3])   # 6 Gelenkwinkel (rad) → Frame
solutions = kin.inverse(frame)                           # Frame → bis zu 8 Konfigurationen
```

`inverse` liefert bis zu acht Lösungen mit Konfigurations-Bitfeld
(Shoulder/Elbow/Wrist) und Flags `unreachable`/`singularity`. Das
1000-Posen-Orakel (Roundtrip FK→IK→FK, ADR-009a) läuft als dauerhafter pytest-Test
`core/tests/test_kinematics.py` mit den in S3 festgenagelten Toleranzen (Position
< 0,01 mm, Orientierung < 1e-6 rad).

### Konfigurationswahl entlang einer Bahn (Issue #11)

Für fahrbare Trajektorien (Strang C) wählt `fgc.kinematics.select_along_path`
aus den mehrdeutigen IK-Lösungen je Target **eine** Gelenklösung —
**deterministisch** (gleiche Bahn → gleiche Lösungsfolge über Läufe hinweg) und
**bahnstetig** (keine Konfigurationssprünge zwischen benachbarten Targets). Die
Schnittstelle bleibt schmal (P3): Frame(s) rein, gewählte Gelenklösung(en) plus
Warnliste raus.

```python
from fgc.kinematics import OpwKinematics, select_along_path

kin = OpwKinematics.from_robot("doosan_m1013")
frames = [kin.forward(q) for q in trajektorie]      # eine glatte Bahn
sol = select_along_path(kin, frames, seed=trajektorie[0])

sol.drivable                 # True, wenn jedes Target eine zulässige Lösung hat
sol.targets[0].joints_rad    # gewählte 6 Gelenkwinkel (rad) — None = unfahrbar
sol.targets[0].configuration # Shoulder/Elbow/Wrist-Bitfeld der Wahl
sol.warnings                 # Liste von ConfigWarning (Daten, keine Exceptions)
```

Die Wahl ist eine **Nächste-Nachbar-Suche im Gelenkraum**: je Target die dem
Vorgänger nächste zulässige Lösung (erstes Target: nächste zum `seed`, Standard =
Nullstellung), Gleichstände über den Konfigurationsindex aufgelöst — das macht
sie reproduzierbar und hält die Konfiguration entlang einer stetigen Bahn
konstant. Der Gelenkabstand misst über die ±π-Naht hinweg, damit ein rein
numerischer Sprung der auf [−π, π] normierten IK nicht als weite Bewegung zählt.

Geprüft wird gegen die **Achsgrenzen** der Roboterdefinition
(`joint_limits_rad`): Ein Target, für das keine Lösung innerhalb der Grenzen
existiert, ist *unfahrbar* — es kommt als Target ohne Gelenklösung
(`joints_rad=None`) samt Warnung zurück (`joint_limits`, wenn erreichbar aber
außerhalb der Grenzen; `unreachable`, wenn außerhalb des Arbeitsraums), **nicht**
als Exception. Der Vorgängerbezug überlebt eine solche Lücke, die Bahn bleibt
danach stetig.

Die **Singularitätsnähe** quantifiziert `OpwKinematics.singularity_measure` als
reziproke Konditionszahl der längen-normierten Jacobi-Matrix ∈ [0, 1] (1 = gut
konditioniert, 0 = singulär) — ein roboterunabhängiges Maß, das bei Handgelenks-,
Ellenbogen- und Schultersingularität gleichermaßen gegen 0 fällt. Unterschreitet
die gewählte Lösung die Warnschwelle `DEFAULT_SINGULARITY_WARN` (0,01, kalibriert
oberhalb des harten OPW-Koppelzweigs bei |j5| ≈ 1,24e-2 rad), kommt eine Warnung
`singularity` mit dem gemessenen Wert. Warnungen sind Daten für das spätere
`Trajectory.meta.warnings` (Issue #12). Tests: `core/tests/test_config_selection.py`
(Determinismus, Bahnstetigkeit, Arbeitsraum-/Achsgrenz-Grenzfälle,
Singularitätsnähe).

### IK-Konfiguration wählbar — harter Filter über die 8 Lösungszweige (Kollisionskontrolle S4, Issue #129, ADR-024/020)

Der IK-Lösungszweig ist **wählbar** — drei Tri-State-Schalter Schulter/Ellbogen/
Handgelenk, je **auto** (Default, kein Constraint), **Zustand A** oder **Zustand
B**. Ein fixierter Zustand filtert die vorhandenen 8 IK-Konfigurationen
(`opw.py`-Bitschema: Schulter=1, Ellbogen=2, Handgelenk=4) in
`select_along_path` **hart** — gesetzte Bits schließen alle Lösungen mit falschem
Bit aus, **keine weiche Präferenz** (ADR-024, verworfene Alternative). So wird
zugleich der bislang beratende Config-Flip des Singularitäts-Advisors anwendbar
(ADR-020-Revisionstrigger erfüllt).

```python
from fgc.kinematics import IkConfigFilter, select_along_path

# Ellbogen auf Zustand B fixieren, Schulter/Handgelenk auto:
f = IkConfigFilter.from_block({"elbow": "b"})   # "a"→Bit 0, "b"→Bit 1, fehlend→auto
sol = select_along_path(kin, frames, config_filter=f)
```

**auto/auto/auto ist der Regressionsanker:** ohne gesetzte Achse (bzw.
`config_filter=None`) greift der Filter nicht und die Bahnwahl ist **bit-identisch**
zu heute (`IkConfigFilter.is_auto` short-circuitet). Ein Bahnpunkt, der ohne die
Vorgabe fahrbar wäre, unter ihr aber keine zulässige Lösung mehr hat, wird *unter
der Vorgabe unerreichbar*: Warnung `ik_config` im Trajektorien-Artefakt
(`meta.warnings`, „IK-Konfiguration schließt alle Lösungen dieses Bahnpunkts aus")
— **Befund, kein Gate** (US 14); der Arm friert dort auf der letzten gültigen
Lösung ein.

Persistiert wird die Wahl **wie ein Slicing-Parameter** über die bestehende
process-params-Schreibstelle (ADR-016, keine neue Route): global
(`process_params.ik_config`) und je Teil über den Gilt-für-Umschalter
(`process_params.sections[id].ik_config`, #92-Muster — geerbt dezent, sparse
Override, ↺ zurück). Ein Abschnitts-Override **veraltet nur dieses Teil** (#83),
eine globale Änderung alle. Additiv/sparse: fehlt der Block (Altprojekte), gilt
auto/auto/auto und alles lädt byte-gleich. Im Viewer wählt das Accordion
**IK-Konfiguration** (Reiter Druckplan/Slicing) die drei Schalter; reine
Zustandslogik in `viewer/src/ui/ik-config-state.ts`. Tests:
`core/tests/test_config_selection.py` (Regressionsanker, harter Filter, Warnung),
`core/tests/test_export.py` (Teil-Veraltung), `viewer/src/ui/ik-config-state.test.ts`.

### `fgc simulate` — Trajectory: Zeit + Totzeitkompensation (Issue #12, Strang C)

Wo der Toolpath **zeitfrei** endet, beginnt die Simulation: Aus einem bestehenden
Lauf (mit `toolpath.json`) plus einem Setup (`fgc setup new`) entsteht die
**Trajectory** — die ausführbare Bewegung als Zeitreihe (`trajectory.json`,
Schema 0.1). Sie ist die eine Stelle, an der **Zeit** entsteht (ADR-012/E3): der
Slicer bleibt zeitfrei, der Viewer und die Emitter (DRL/KRL) lesen die Zeit hier.

```bash
# Lauf mit toolpath.json (aus fgc slice) + setup.json (aus fgc setup new)
fgc simulate --run runs/20260704-120000_slice_Building --setup examples/setup.json
# → schreibt trajectory.json in denselben Lauf
```

Was dabei passiert:

1. **Frames → Basis.** Jede Toolpath-Pose (Düse im Wandsystem) wird über das
   Setup zur **TCP-Pose in Roboterbasis** verkettet (`wall_to_base ∘ target`,
   `fgc.simulation.transform`, ADR-006: eine Transformationsstelle); `tcp⁻¹`
   verkettet daraus die Flansch-Pose für die IK.
2. **Bewegungsmodell (`fgc.simulation.motion`, Issue #62, ADR-019).** Das Modell
   bildet die reale Bewegung ab und ersetzt die frühere stückweise-konstante
   Zeitparametrierung:
   - **Trapez-Geschwindigkeitsprofile** (Rampe/Halt/Bremse): jedes Segment fährt
     unter der eingestellten Beschleunigung von Ruhe auf die kommandierte
     Geschwindigkeit und wieder auf Ruhe. **Ohne** Blending hält der Arm an jedem
     Ziel.
   - **Blending / Ecken-Verrundung** (`blending_mm`, Scheibe 4b / Issue #63,
     **provisorisch** Spike S1): ein gesetzter Verrundungsradius verrundet Ecken
     zwischen zwei aufeinanderfolgenden **movel**-Bewegungen — die Bahn kürzt die
     Ecke als quadratische Bézier-Kurve ab (statt den scharfen Wegpunkt exakt
     anzufahren, `motion.blend_corner`; der Radius wird auf die halbe Länge jedes
     angrenzenden Segments gedeckelt) und die angrenzenden movel-Segmente teilen
     sich **ein** Trapezprofil. Dadurch bleibt die Geschwindigkeit am verblendeten
     Wegpunkt **> 0** (kein Vollstopp) und die Gesamtzeit sinkt. `blending_mm == 0`
     ⇒ exakt das Vollstopp-Verhalten (Halt an jedem Ziel). Verrundungsformel und
     -werte sind provisorisch, bis Spike S1 das gerätespezifische Blending misst;
     movej-Travel-Ecken behalten bewusst den Vollstopp.
   - **movel-lineare TCP-Interpolation** für Druck-Ziele: der TCP wird dicht
     entlang der **kartesischen Geraden** abgetastet (Position linear, Orientierung
     per Slerp), je Zwischenpose die IK befragt. **movej-Gelenkinterpolation** für
     Travel-Bewegungen. Bewegungstyp und Dynamik (vel/acc) kommen aus
     `process_params.motion` (mit **provisorischen** Defaults, Spike S1).
   - **Ehrliche Befunde:** `kinematics.select_along_path` (Issue #11) läuft über
     die *ganze* dichte Bahn und hält die Konfiguration, die die Geraden fahrbar
     lässt. Eine unfahrbare/singuläre **Zwischen**stelle mitten in einer
     movel-Geraden wird als **verortete Warnung** gemeldet (mit ihrer Zeit); der
     Arm friert dort auf der letzten gültigen Gelenklösung ein (sichtbar, wie das
     eingefrorene Home aus Issue #66) — **kein** stiller Rückfall auf
     Gelenkinterpolation, der die Stelle kaschiert. Die Zeitachse ist streng
     monoton; die Achs-v/a-Grenzen (`joint_velocity_limits_rad_s` /
     `joint_acceleration_limits_rad_s2` aus `robots/doosan_m1013.json`) werden je
     Segment garantiert eingehalten.
3. **io-Totzeitkompensation (ADR-012).** Deklariert das Setup
   `deadtime.compensation = simulation_shift`, wird die io-Zeitreihe um **−t_tot**
   verschoben (der Pumpenvorlauf gegen die Materialsystem-Totzeit) und
   `meta.io_compensated = true` gesetzt. Bei `native_lookahead` (Controller
   kompensiert selbst, z. B. KUKA ANOUT-Vorlauf) oder `none` unterbleibt der
   Shift, `meta.io_compensated = false`.

`meta` trägt die **Gesamtdauer** (Druckzeitschätzung), die **Achsauslastung** je
Gelenk (`axis_utilization` ∈ [0, 1]) und die Kinematik-Warnungen (`warnings` mit
`t_s`/`kind`/`message`; `kind` ∈ singularity/joint_limit/reach), jetzt auch
**verortet mitten in einer movel-Geraden**. Ein unfahrbares Target/Zwischenpose
hält die letzte gültige Gelenklösung und erscheint als Warnung — die Simulation
bricht nicht ab. Tests: `core/tests/test_motion.py` (Trapez-Grenzen,
movel-Linearität, Monotonie, Mitten-in-movel-Singularität ⇒ verortete Warnung
statt Fallback, movej-Gelenkinterpolation, `process_params.motion`-Overrides) und
`core/tests/test_simulation.py` (Shift-Verhalten, Schema-Validität, CLI).

**Bewegungsparameter (`process_params.motion`, Issue #62).** Der Druckjob darf den
Bewegungstyp je Zielart (`print_move`/`travel_move`, movel/movej) und die
Dynamik übersteuern: `tcp_acc_mm_s2` (kartesische Beschleunigung des Trapezes),
optional `tcp_vel_mm_s` (Deckel der Reisegeschwindigkeit), `sample_step_mm`
(Abtastschritt der movel-Geraden), `blending_mm` (Ecken-Verrundungsradius, s. o.)
sowie `travel_step_rad`/`travel_speed_frac` für
movej. Fehlt der Block (Altprojekt), gelten die provisorischen Defaults. Die
kartesischen vel/acc-Werte sind **provisorisch markiert** (`MotionParams.provisional`),
bis Spike S1 am Gerät gemessene Grenzen liefert.

### `fgc emit-drl` — DRL-Programm erzeugen (Issue #13/#64, Strang C, ADR-011)

Aus einem Lauf mit `toolpath.json` (erzeugt von `fgc slice`) und einem
`setup.json` (erzeugt von `fgc setup new`) wird ein controller-natives
DRL-Programm für den Doosan M1013 erzeugt:

```powershell
fgc emit-drl --run runs\20260704-120000_slice_Building --setup examples\setup.json
# → schreibt program.drl in denselben Lauf
```

| Option | Bedeutung |
|---|---|
| `--run` | Laufordner mit `toolpath.json` (aus `fgc slice`) |
| `--setup` | Setup-Artefakt mit Kanal-Mapping (aus `fgc setup new`) |

**Was dabei passiert:**

1. **Per Toolpath-Target movel/movej (Issue #64).** Je Target ein
   Bewegungsbefehl statt eines `movej` je Simulations-Sample: `movel(posx(…), vel,
   acc, radius, ref)` für Druck- (`kind == "print"`), `movej(posx(…), …)` für
   Verfahr-Targets (`kind == "travel"`). Der Bewegungstyp je Zielart, vel/acc, der
   Blending-Radius (`radius=`) und das Bezugssystem (`ref=`) stammen aus
   `process_params.motion` (Bewegungsmodell, Issue #62). Der dichte Gelenk-Stream
   der Simulation (`trajectory.json`) bleibt für den Viewer-Replay erhalten; die
   DRL wird kürzer und dem Controller (IK der Cartesian-Ziele) überlassen.
2. **Kanal-Mapping (ADR-011).** Physische AO-/DO-Indizes, Modus (Spannung/Strom/digital)
   und Wertebereiche kommen ausschließlich aus `setup.io_channels` — nirgendwo sonst.
   Unbekannte logische Kanäle oder Werte außerhalb des erlaubten Bereichs werden
   mit einer verständlichen Fehlermeldung abgelehnt.
3. **Change-on-Delta.** AO/DO-Befehle werden nur bei Wertänderung emittiert —
   konstante io-Abschnitte erzeugen keine wiederholten Schreibzugriffe.
4. **Grad-Konvertierung (ADR-006).** Die Ziel-Pose wird über das Setup
   (`wall_to_base ∘ frame`) in Roboterbasis-Koordinaten gebracht und als `posx`
   mit ZYZ-Euler-Grad emittiert — Grad entstehen ausschließlich im Emitter.
5. **Provenienz + Provisorik-Stempel.** Die Provenienz des Aufrufs steht als
   Kommentarblock im DRL-Kopf; darunter ein **Provisorik-Stempel** (Spike S1): die
   Bewegungsgrenzen (vel/acc/Blending) stammen aus angenommenen Prozesswerten,
   nicht aus am Gerät gemessenen Grenzen.

**Provisorisch (kein Gate, ADR-006/012/013):** Die vel/acc/Blending-Grenzen sind
bis zur S1-Messung (Roboterzugang, Latenz-/Grenzwert-Messung) vorläufig. Das DRL
trägt dazu den Provisorik-Stempel im Kopf und der **Reiter Export** kennzeichnet
die Ausgabe sichtbar als provisorisch — das Programm entsteht trotzdem, es gibt
kein Gate.

### Viewer-Trajektorien-Animation — Bewegung und io-Verlauf prüfen (Issue #14)

Liegt in einem Laufordner eine `trajectory.json` (erzeugt von `fgc simulate`), erscheint im Viewer-Seitenpanel der Abschnitt **„Trajektorie"**:

- **Zeit-Slider + Play/Pause** — spielt die Bewegung in Echtzeit ab; der Slider kann jederzeit gezogen werden.
- **TCP-Marker** — kleiner roter Punkt auf der 3D-Bahn, der synchron zur Zeit entlang der Toolpath-Targets wandert (ADR-007: keine Kinematik, nur Interpolation zwischen vorhandenen Positionen).
- **io-Verlauf** — je logischem Kanal ein Balken, der den interpolierten Pumpenwert [0 … 1] anzeigt; totzeitkompensierte Kanäle (`meta.io_compensated = true`) sind entsprechend vorverschoben.
- **Metadaten** — Gesamtdauer, maximale Achsauslastung, io-Kompensationsstatus.
- **Warnungen** — alle Kinematik-Warnungen aus `meta.warnings` (Singularität, Achsgrenze, Erreichbarkeit) mit Zeitstempel.

**Abwärtskompatibilität:** Läufe ohne `trajectory.json` (ältere Slice-Läufe, Wände-Läufe) zeigen das Panel nicht; alle bisherigen Funktionen (Schicht-Slider, Re-Slicing-Panel, Wand-Auswahl) bleiben unverändert.

**Ende-zu-Ende:**

```powershell
.\fgc slice examples\Building-Architecture.ifc --wall <GlobalId>
.\fgc simulate --run runs\<lauf> --setup examples\setup.json
# Viewer: http://localhost:5173/?run=/@fs/C:/…/runs/<lauf>
# → „Trajektorie"-Panel → ▶ abspielen
```

### Präsentations-FK: Kapsel-Arm-Replay (Issue #18)

Bei Läufen mit `trajectory.json` zeigt der Viewer zusätzlich den **Roboterarm**, der die Bahn abfährt — als bewusst schematische Kapsel-/Zylinder-Darstellung (je Glied ein Zylinder zwischen den Gelenken, an jedem Gelenk eine Kugel; offizielle URDF-Meshes folgen in einem späteren Issue):

- **Bewegung synchron zum Player** — der Arm stellt sich zu jeder Zeit auf die interpolierten `joints_rad` des Samples (Play/Pause/Seek wirken sofort). Der Ein-/Ausschalter **„Roboterarm (Schema)"** liegt im Trajektorien-Panel.
- **Feste Basis, TCP druckt von oben (Issue #66)** — der Arm wird an der **festen Roboterbasis** verankert (`trajectory.meta.base_frame` = Roboterbasis im Wandsystem, vom Core geliefert): die Basis steht fix an der geplanten Platzierung, die Gelenke fahren die Bahn ab, und der **TCP** (nicht die Flanschmitte) trifft die Toolpath-Ziele — die Düse senkrecht von oben (`NOZZLE_DOWN_QUAT`, Issue #51). Ist eine Platzierung nicht erreichbar (konstante Gelenke), bleibt der Arm ehrlich in der Home-Pose stehen, während der TCP-Marker wegläuft (statt die Basis mitzuschleifen); die `reach`-Warnung erscheint im Player. **Altläufe** ohne `base_frame` nutzen den früheren Anker (Flansch aufs Ziel) — für das korrigierte Verhalten den Abschnitt neu **„Slicen + Simulieren"**.
- **Nur Darstellungsmathematik (ADR-007-Klarstellung 2026-07-04/2026-07-05)** — der Viewer rechnet die Gliedposen ausschließlich zur Anzeige und **setzt** das Basis-Frame nur, das der Core als Artefakt liefert. Die Vorwärtskinematik (`viewer/src/kinematics/fk.ts`) spiegelt die Standard-DH-Kette der Core-FK 1:1 und ist per **Golden-Testorakel** gegen den Core validiert (`fk.golden.json` aus `viewer/scripts/gen_goldens.py`, erzeugt vom Core aus `OpwKinematics.link_frames`; Toleranz Position < 1e-6 mm, Quaternion-Komponenten < 1e-8 — ADR-009-Muster). Alle Urteile (Erreichbarkeit, Warnungen) bleiben Core-Artefakte.
- **Abwärtskompatibilität** — Läufe ohne `trajectory.json` laden unverändert; der Arm erscheint nur mit Trajektorie.

Das Golden-Orakel bei Änderung an den DH-Parametern oder der Core-FK neu erzeugen (Gen-Treiber des Paritäts-Manifests `fgc.parity`, regeneriert ohne Argument **alle** geteilten Goldens):

```powershell
.venv\Scripts\python.exe viewer\scripts\gen_goldens.py fk
```

### M1013-Meshes vendoren + GLBs erzeugen (Issue #40)

Das echte Doosan-M1013-Modell liegt reproduzierbar im Repo, statt zur Laufzeit geladen oder von Hand nachgebaut zu werden. Die Kette hat zwei Stufen:

- **Originale (Quelle der Wahrheit):** `third_party/doosan_m1013/` enthält URDF + Visual- **und** Collision-DAE-Meshes des M1013, die `LICENSE` (BSD-3-Clause © Doosan Robotics) und `UPSTREAM.md` mit Repo-URL und **gepinntem Commit** (`ec92425…`). Kollisionsprüfung/Simulation im Core ziehen später ausschließlich aus diesen Originalen — nie aus den Viewer-GLBs.
- **Viewer-GLBs (abgeleitet):** `viewer/public/robots/m1013/` hält ein GLB je Glied (`base.glb`, `link1.glb`…`link6.glb`) plus `manifest.json` (Link-Index → Datei, Upstream-Commit, Lizenzhinweis). Erzeugt vom **Konvertierskript** `core/scripts/convert_robot_meshes.py` (trimesh, DAE via `pycollada`; kein Blender/assimp, **kein Draco**).

In jedes GLB **eingebacken** sind (1) die Meter→mm-Skalierung und (2) der konstante Offset URDF-Linkframe ↔ DH-Gliedframe (`offset_i = dhFrame_i(_START)⁻¹ · Rz(π) · urdfFrame_i(0)`, berechnet am **korrespondierenden Posenpaar**: die aufrechte Doosan-Nullstellung des URDF entspricht in der DH-Kette den Winkeln `_START = (0, π/2, π/2, 0, 0, π)`, nicht `[0,…,0]` — Issue #53; DH aus `robots/doosan_m1013.json`). Damit setzt der Viewer später schlicht `mesh.matrix = frames[i]` — keine zweite Zahlenquelle (Rendering/Toggle: Folge-Issue #41). Ein pytest-Smoke-Check (`core/tests/test_robot_meshes.py`) prüft Manifest-Vollständigkeit, mm-Skala je Glied, die aufrechte Montage bei `_START` (~1450 mm hoch, Basis am Boden) und dass das Flanschglied `link6.glb` lokal am Flansch-Ursprung liegt (Regression #53).

GLBs neu erzeugen (deterministisch, vom Repo-Root; `pycollada` aus `fgc-core[geo]`):

```powershell
.venv\Scripts\python.exe core\scripts\convert_robot_meshes.py
```

### M1013-Meshes im Präsentations-Arm + Schema-Toggle (Issue #41)

Der Präsentations-Arm (Roboter-Vorschau im Reiter Roboter **und** Replay-Arm im
Hauptsichtfeld) zeigt per Default die **echten M1013-Glieder** aus den GLBs
(Issue #40) statt der Kapsel-/Zylinder-Schemadarstellung. Beides teilt sich
dieselbe Präsentations-FK (`forwardChain`, Golden-Orakel-validiert): je Glied
hängt sein GLB direkt am DH-Gliedframe (`mesh.matrix = frames[i]`, Offsets sind
in die Vertices eingebacken — keine zweite Kinematik/FK im Viewer). Die
Flansch-Kinder (Endeffektor-Mesh, TCP-Marker, Flansch-Achsen — Issue #28) sitzen
in beiden Darstellungen unverändert korrekt.

- **Umschalter „Schema-Darstellung":** liegt im Reiter Roboter (Abschnitt
  *Darstellung*) und wirkt **global** auf alle Arm-Instanzen gleichzeitig
  (Vorschau + Replay). Default ist Mesh; angehakt zeigt der Arm das Kapsel-Schema.
- **Fallback (nie ein leerer Viewport):** scheitert der GLB-Load (Manifest fehlt,
  Fetch-Fehler), fällt der Arm automatisch auf das Zylinder-Schema zurück, gibt
  eine Konsolen-Warnung aus und **sperrt** den Umschalter (er steht dann fest auf
  Schema). Die Zylinder-Darstellung bleibt vollständig im Code — sie ist zugleich
  Schema-Modus und Fallback.
- **Meshes einmal laden, je Instanz klonen:** die 7 GLBs werden einmalig über
  `manifest.json` (die einzige Quelle Link-Index → Datei) geladen und pro
  ArmView-Instanz geklont (unabhängige Transforms).
- **BSD-3-Attribution:** Lizenz-, Repo- und Commit-Hinweis stammen aus dem
  Manifest (`upstream`) und stehen als Info-Text unter dem Umschalter.
- **Lade-/Fallback-/Umschalt-Logik** liegt three.js-frei und unit-getestet in
  `viewer/src/render/armmesh-state.ts` (`armmesh-state.test.ts`); der Headless-
  Smoke (`viewer/scripts/ui_smoke.mjs`) prüft über den `window.__armDebug`-Hook,
  dass die Roboter-Vorschau tatsächlich 7 Glied-Meshes im Mesh-Modus zeigt.

### Laufordner-Anatomie

Jeder Pipeline-Aufruf erzeugt einen Ordner `runs/<zeitstempel>_<befehl>_<modell>/` (ADR-004). Mögliche Artefakte, alle schema-validiert (`schemas/`):

| Datei | Inhalt | erzeugt von |
|---|---|---|
| `candidates.json` | alle Wände mit Eignungsflags und Ablehnungsgründen | `fgc walls list` |
| `model.glb` | binäre Modell-glTF aller Wände (ein Szenenknoten je Wand) für den Viewer (Issue #6) | `fgc walls list` |
| `model_map.json` | GlobalId-Zuordnung zu den `model.glb`-Knoten (schema-/provenienz-konform, verweist per `mesh_file`) | `fgc walls list` |
| `wallspec.json` | Geometrie + Metadaten der ausgewählten Wand | `fgc slice`, `fgc start`, `POST /slice` |
| `toolpath.json` | roboterunabhängige Bahnpunkte (print/travel, Schichten, IO-Kanäle) + `summary`-Block (`n_layers`, `n_targets`, `n_print`) + `params`-Block (Slice-Parameter für das Viewer-Panel; ab Schema 0.3, Issue #9) | `fgc slice`, `fgc start`, `POST /slice` |
| `context.json` | restliches Gebäude als Kontext-Meshes für den Viewer | `fgc slice`, `fgc start`, `POST /slice` |
| `trajectory.json` | ausführbare Bewegung als Zeitreihe (`samples` mit `t_s`/`joints_rad`/`io`; `meta` mit Gesamtdauer, Achsauslastung, Warnungen, `io_compensated`); io totzeitkompensiert (ADR-012, Issue #12) | `fgc simulate` |
| `program.drl` | controller-natives DRL-Programm für den Doosan M1013: per Toolpath-Target `movel` (Druck) / `movej` (Travel) mit vel/acc/Blending/ref aus `process_params.motion`, Change-on-Delta-IO, Kanal-Mapping aus Setup (ADR-011), ZYZ-Euler-Grad (ADR-006); Provisorik-Stempel im Kopf (vel/acc/Blending provisorisch bis S1, kein Gate) | `fgc emit-drl` |

Jedes Artefakt trägt eine `provenance` (Quell-Kommandozeile, Zeitstempel) — jeder Lauf ist damit reproduzierbar dokumentiert.

## Struktur

| Pfad | Inhalt |
|---|---|
| `core/` | Python-Paket `fgc` (CLI + Fachlogik), src-Layout; `geometry/` — neutrales Schnittmodul (ADR-015) |
| `viewer/` | Statische Web-App (Vite + three.js) |
| `schemas/` | JSON-Schemas der Datenverträge (Single Source für Core und Viewer) |
| `robots/` | Roboterdefinitionen (JSON) + Gelenkmeshes (glTF) |
| `materialcards/` | Material- und Prozessparameter-Karten (provisional-Flag nach P4) |
| `examples/` | IFC-Beispieldateien, Setups |
| `runs/` | Laufordner (gitignored, siehe OneDrive-Hinweis) |
| `docs/adr/` | Architekturentscheidungen |
| `docs/design-log.md` | chronologisches Entscheidungstagebuch (Paper-Grundlage) |
| `docs/spikes/` | Spike-Protokolle S1–S4 |

Weitere Dokumente: [Systemarchitektur](architektur.md) · [Architekturentscheidungen](adr/) · [Design-Log](design-log.md)

## Entwicklung

```powershell
.venv\Scripts\python -m pytest core
.venv\Scripts\python -m ruff check core
```

**Headless-UI-Smoke-Test** (`viewer/scripts/ui_smoke.mjs`): bedient den echten
Viewer über CDP in headless Edge und prüft, was tsc/vitest nicht sehen — dass
jeder Reiter wirklich ein sichtbares 3D-Hauptsichtfeld hat (CSS-Kaskade,
DOM-Verdrahtung; Lehre aus dem GUI-Smoke 2026-07-05). Voraussetzung: API +
Vite-Dev-Server laufen (`fgc start`), mindestens ein Projekt existiert.

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --headless=new --remote-debugging-port=9333 --user-data-dir=$env:TEMP\edge-smoke about:blank
node viewer/scripts/ui_smoke.mjs 9333          # Exit-Code 0 = bestanden
```

Hinweis Python-Version: Basis-Abhängigkeiten laufen auf 3.12+. Für `ifcopenshell` ggf. Wheel-Verfügbarkeit für die installierte Version prüfen; notfalls 3.12-venv verwenden.

**Doku-Regel:** Jede neue oder geänderte Funktion bekommt ihren Abschnitt unter „Funktionen" in dieser README — sonst gilt sie als unfertig. Designentscheidungen wandern ins [Design-Log](docs/design-log.md).

## OneDrive (wichtig!)

Das Repo liegt bewusst in OneDrive (Entscheidung §8.9 des Plans). **Pflicht-Mitigation, einmalig manuell:**

1. OneDrive-Symbol → Einstellungen → Konto → **Ordner auswählen** → den Ordner `RoboPrintIFC/runs` (und `viewer/node_modules`) **abwählen**.
2. `runs/` ist zusätzlich gitignored; Backup läuft über den Git-Remote, nicht über OneDrive.

Ohne Schritt 1 synchronisiert OneDrive jeden Pipelinelauf (Meshes, glTF) und riskiert Sperrkonflikte mit laufenden Prozessen.

# Spike S5 — Profiling der Kollisionskontrolle an Abschnitt 1 (Denkmal-Wand) (Issue #143, Karte #139)

Status: **grün (Messung abgeschlossen)** · 2026-07-09

> AFK-Vorarbeit für die Strategie-Entscheidung #144. Dieser Spike **misst**, er
> optimiert nicht: kein Produktivcode geändert (`core/src/fgc/collision/*`
> unberührt). Alle Zahlen sind reproduzierbar über die Sonden unter
> `docs/spikes/s5_scripts/`.

## Frage

Wo geht die Zeit von `fgc.collision.check.find_collisions` an der **realen
Abschnitt-1-Bahn** hin, und welcher der drei naheliegenden Hebel (Distanz nur bis
Schwelle / Travel-Ausdünnung / Hindernis-Caching) bringt wie viel? Zielmarke aus
der Karte: „Fokus-Teil ≤ ~10 s".

## Welcher Lauf — und warum

Profiliert wird `runs/20260709-140251_slice_Denkmal`, der jüngste Abschnitt-1-Lauf
des Druckjobs `default` in `projects/denkmal/project.json`
(`section_runs → abschnitt-1`, Provenienz
`POST /projects/denkmal/sections/abschnitt-1/simulate`). Sein gespeicherter
`meta.collision`-Block trägt **exakt** die Ticket-Zahlen:

| Kennzahl | gespeicherter Lauf | Ticket |
|---|---|---|
| Samples gesamt | 19 535 | — |
| rot / gelb / grün | **8688 / 2405** / 8442 | ~8688 rot / ~2405 gelb |
| min. Abstand | −290,444 mm | — |
| Zerlegungsart | `modul` (freizone 40 mm, safety 50 mm) | — |

Der Lauf ist ein **Modul** (die Denkmal-Wand ist per `decomposition_kind: "modul"`
zerlegt); „Abschnitt 1" ist die `section_id` `abschnitt-1`. Die Sample-Zahlen
passen byte-genau, also ist dies der im Ticket gemeinte Lauf.

**Reproduktion statt Rückrechnung.** Statt die Bahn aus der 6-MB-`trajectory.json`
zurückzurechnen, baut `s5_harness.py` sie deterministisch über den **Produktivpfad**
`actions._slice_and_simulate_section("denkmal", "abschnitt-1")` und prüft, dass
`find_collisions` byte-genau 8688 / 2405 / 8442 und min −290,444 mm liefert
(`verify_reproduction` → MATCH). So wird **derselbe** Produktivcode mit denselben
Eingaben profiliert, nicht eine Nachbildung.

## Vorgehen

Drei Sonden unter `docs/spikes/s5_scripts/` (Aufruf je Sonde im Docstring; venv,
Repo-Root). Alle rufen den echten `find_collisions` bzw. dieselben Produktiv-Helfer.

- **`s5_cprofile.py`** — cProfile auf den echten `find_collisions` (Grobverteilung,
  voller Dump `last_cprofile.txt`). Nur Profiler-Overhead, kein Wrapper im Hot-Path.
- **`s5_instrumented.py`** — Zeile-für-Zeile-Nachbildung des `find_collisions`-Loops
  (ruft dieselben Helfer `_corner_box`/`_aabb_gap`/`_obstacle_groups`/`_matrix`/
  `_set_parts`/`_in_freizone`/`transform.compose` und die echten fcl-Manager) mit
  `perf_counter`-Messpunkten je Posten + Zählern. Ein Korrektheits-Gate prüft, dass
  die Nachbildung dieselben rot/gelb/grün-Zahlen liefert (MATCH). Misst zusätzlich
  Travel-Zeitanteil, fcl-über/unter-Schwelle und **Selbstkollision** (eigener
  Volllauf mit `self_collision=True`).
- **`s5_threshold.py`** — misst Hypothese 1 direkt: für jedes nahe (Glied,Hindernis)-
  Paar am selben positionierten Manager **beide** Abfragen, `min_distance_other`
  vs. der billige `in_collision_other`, getrennt gemessen.

Messumgebung: Windows 11, Python 3.14, Projekt-venv, `python-fcl 0.7.0.11`,
`doosan_m1013` (VHACD-Urteilsgeometrie + Hüllen-Breitphase nach S0/#125), Tool
`30gut` (provisorische Endeffektor-Hülle aktiv). Produktiv-Konfiguration:
`self_collision=False` (so baut `finding.build_section_finding` den Befund).

## Ergebnis

### 1 — Gesamtlaufzeit

`find_collisions` (self=False, Produktiv-Konfiguration), drei saubere Vollläufe:
**10,6 / 12,2 / 11,8 s** → **~11,5 s** typisch, **~0,59 ms/Sample** über 19 535
Samples. (cProfile bläht auf 17,2 s `total_tt` — Profiler-Overhead, nur für die
Verteilung genutzt.)

**Wichtiger Befund vorab — `find_collisions` ist nicht der 3-Minuten-Treiber.**
Der ganze Fokus-Abschnitt rechnet in dieser Umgebung in ~19 s end-to-end:

| Posten des Fokus-Abschnitts (self=False) | Zeit |
|---|---|
| Slice + Trajektorie (`_slice_and_simulate_section`, inkl. IFC-Laden/Decompose) | ~5–7 s |
| FK `kin.link_frames` je Sample (für den Befund) | ~0,75 s |
| **`find_collisions`** | **~11,5 s** |
| `trajectory`-Artefakt validieren (jsonschema) + serialisieren (5,2 MB) | ~1,0 s |
| **Summe** | **~19 s** |

Die im Ticket genannten „> 3 min" ließen sich mit der Produktiv-Konfiguration
**nicht reproduzieren** — wohl aber mit `self_collision=True`: dann kostet
`find_collisions` allein **~184 s** (s. u.). Siehe „Einschränkungen".

### 2 — Zeitanteil je Posten (instrumentierte Nachbildung, Gate: MATCH)

Die Nachbildung erfasst 9,53 s der ~11,5 s; die Differenz (~2 s) sind die in
`find_collisions` erzeugten `SampleResult`-Objekte, `_classify` und `_report`
(nicht instrumentiert). Anteile beziehen sich auf die erfassten 9,53 s; die
cProfile-Spalte (Eigenzeit am **echten** Code) bestätigt die Reihenfolge.

| Posten | instrum. s | Anteil | cProfile tottime | was |
|---|---:|---:|---:|---|
| **`set_transform` (VHACD-Stücke positionieren)** | **5,03** | **52,8 %** | **8,04 s** | ~36 Konvexstücke je nahem Glied je Sample neu setzen |
| **fcl `min_distance_other` (Urteil)** | **1,70** | **17,8 %** | 2,34 s | die exakte Nahdistanz je nahem Paar |
| `_matrix` (Frame→4×4, Quat→Rot) | 0,83 | 8,7 % | 0,39 s + 0,48 s | homogene Matrizen je Glied je Sample |
| `transform.compose` (FK-Verkettung) | 0,67 | 7,0 % | 0,34 s | Welt-Frames = `compose(base, link)` |
| AABB-Ecken transformieren + min/max | 0,60 | 6,3 % | 0,54 s (numpy reduce) | Welt-AABB je geprüftem Glied |
| `_aabb_gap` (Breitphase) | 0,42 | 4,4 % | 0,68 s | AABB-Lücke Glied↔Hindernis |
| `_in_freizone` (Freizonen-Test) | 0,20 | 2,1 % | 0,19 s | Nahpunkt in der Freizone? |
| `_obstacle_groups` (Druckstand-Rebuild) | 0,08 | 0,8 % | 0,00 s | Hindernisgruppen je Schicht |

**Kernbefund:** Nicht die fcl-Distanzabfrage dominiert, sondern das
**Positionieren der VHACD-Urteilsgeometrie** (`set_transform`, ~53 %). Ursache:
Die VHACD-Zerlegung liefert je Glied **~36 Konvexstücke** (maxConvexHulls = 64),
und `_set_parts` ruft `set_transform` je Stück — **1 566 305 Aufrufe** über den
Lauf. Positionieren (5,0 s) kostet ~3× so viel wie das eigentliche Urteil (1,7 s).

### 3 — Kennzahlen-Tabelle

| Kennzahl | Wert |
|---|---|
| Samples gesamt / rot / gelb / grün | 19 535 / 8688 / 2405 / 8442 |
| Travel-Samples (nicht extrudierend) | 5985 (30,6 %) |
| Schichten (Druckstand-Rebuilds) | 82 |
| Breitphasen-Auswertungen (`_aabb_gap`, Arm↔Hindernis) | 135 079 |
| davon vom AABB-Filter **verworfen** | 91 610 = **67,8 %** |
| davon durchgelassen → fcl-Aufruf | 43 469 |
| `set_transform`-Aufrufe (Stücke positionieren) | 1 566 305 (~36 je fcl-Aufruf) |
| fcl `min_distance`-Aufrufe | 43 469 |
| Zeit je fcl-`min_distance`-Aufruf | 0,039–0,044 ms |
| fcl-Aufrufe mit Ergebnis > Sicherheit (nur „grün") | 8851 (20,4 %) |
| Gesamtlaufzeit `find_collisions` (self=False) | **~11,5 s** (~0,59 ms/Sample) |

Der Ticket-Verdacht „AABB-Breitphasenfilter greift kaum" ist **widerlegt**: Der
Filter verwirft **67,8 %** aller Glied↔Hindernis-Paare, bevor fcl befragt wird.
Er greift also deutlich — die verbleibende Zeit steckt in den unvermeidlich
nahen Paaren (Handgelenk/Endeffektor am wachsenden Modul).

### 4 — Die drei Hypothesen, gemessen (nicht umgesetzt)

**H1 — Distanz nur bis Schwelle statt exakt.** Gemessen (`s5_threshold.py`, an
allen 43 469 nahen Paaren):

| | Zeit gesamt | ms/Aufruf |
|---|---:|---:|
| `min_distance_other` (heute) | 1,92 s | 0,044 |
| `in_collision_other` (Ja/Nein, 0 mm) | 0,49 s | 0,011 |

`in_collision` ist **4× billiger**, beantwortet aber nur **rot/nicht-rot** — das
**gelbe** Sicherheitsband (0…50 mm, 23 248 Aufrufe) braucht zwingend eine Distanz,
und der Befund berichtet die Eindringtiefe rot aus der VHACD-Distanz (ADR-024).
Ein früh abbrechender Test kann `min_distance` also **nicht ersetzen**, nur die
klar durchdringenden Fälle (11 370 Aufrufe mit `in_collision=True`) früh abfangen.
Vor allem: `set_transform` (5,0 s) fällt für **beide** Wege an und bleibt.
**Gemessener Deckel: 1,9 s** (das gesamte `min_distance`), realistisch 0,5–1 s.
→ **kleiner Hebel.**

**H2 — Sample-Ausdünnung bei Travel.** 5985 der 19 535 Samples sind Travel
(30,6 %); sie verbrauchen **3,51 s = 36,0 %** der Prüfzeit (also leicht
überproportional — die Approach/Retract-Bögen am Modul liegen nah). Travel ist im
Befund ohnehin als **„nicht lückenlos geprüft"** markiert (ADR-024, Tunneling bis
~1 m/Schritt). Eine 5×-Ausdünnung der Travel-Samples spart ~2,8 s.
→ **größter sicher realisierbarer Hebel: ~2,8–3,5 s (36 %).** Preis: Travel-
Tunneling wird gröber (bewusste v1-Grenze bleibt).

**H3 — Hindernis-Caching über Schichten.** `_obstacle_groups` läuft **82×**
(einmal je Schicht, der `group_cache` greift bereits), Gesamtkosten **0,08 s =
0,8 %**, ~0,97 ms je Rebuild. Ein inkrementeller Aufbau (Schicht n = n−1 + neue
Schicht) spart aus 0,08 s praktisch nichts. → **kein Hebel** (Hypothese durch
Messung widerlegt; der Cache erledigt das schon).

**Zusatz-Posten — Selbstkollision (`self_collision=True`, produktiv AUS).**
Als eigener Volllauf: **+132 s** fcl-Zeit, gesamt **~160–184 s** (~15× der ganzen
Prüfung), 82 405 zusätzliche fcl-Aufrufe über die nicht-benachbarten Gliedpaare
(410 235 Breitphasen-Auswertungen, 79,9 % verworfen). Das ist der einzige gemessene
Weg, der die „> 3 min" des Tickets erreicht. Produktiv ist Selbstkollision **aus**
(`finding.py`), der reale Befund braucht sie nicht.

## Hebel-Ranking (Ausgang ~11,5 s)

| # | Hebel | gemessene Grundlage | erwartete Ersparnis | Restlaufzeit | Preis / Risiko |
|---|---|---|---:|---:|---|
| 1 | **`set_transform` verschlanken** (außerhalb der 3 Hypothesen) | 5,0 s / 53 %; ~36 VHACD-Stücke je nahem Glied | 2–4 s (bei halber Stückzahl / gebündeltem Setzen) | ~7–9 s | berührt VHACD-Urteilsgeometrie → Formtreue-Trigger (ADR-024/S0); oder API-Umbau (ein Manager/Glied, Sammel-Transform) |
| 2 | **H2 Travel-Ausdünnung** | 3,5 s / 36 % in 30,6 % der Samples | ~2,8 s (5×-Ausdünnung) | ~8,7 s | Travel-Tunneling gröber (schon als „nicht lückenlos" markiert) |
| 3 | **H1 Distanz nur bis Schwelle** | `min_distance` 1,9 s; `in_collision` 4× billiger | 0,5–1,9 s (nur rote Fälle kurzschließbar) | ~9,6–11 s | gelbes Band braucht weiter Distanz; `set_transform` bleibt |
| 4 | **H3 Hindernis-Caching** | Rebuild 0,08 s / 0,8 % | ~0 | ~11,5 s | kein Hebel — Cache greift schon |

Hebel sind teils kombinierbar: H2 senkt die Sample-Zahl und damit auch
`set_transform`/`min_distance` **anteilig** mit. H2 + H1 ⇒ grob ~7–8 s.

## Ist „Fokus-Teil ≤ ~10 s" erreichbar?

**Für `find_collisions`: ja.** Schon **H2 allein** (Travel-Ausdünnung) bringt
~11,5 s → ~8,7 s, mit H1 zusätzlich ~7–8 s. Der stärkste Hebel (`set_transform`,
#1) liegt außerhalb der drei genannten Hypothesen und würde die Prüfung am
deutlichsten drücken, berührt aber die VHACD-Urteilsgeometrie (Formtreue-Trigger,
ADR-024) — das ist eine Strategie-Entscheidung für #144, keine Messfrage mehr.

**Für den ganzen Fokus-Abschnitt: Zielmarke offen / vermutlich zu revidieren.**
In dieser Umgebung braucht der Produktiv-Abschnitt **~19 s** end-to-end (davon
`find_collisions` ~11,5 s), **nicht** > 3 min. Die „> 3 min" waren nur mit
`self_collision=True` reproduzierbar — was der automatische Befund gar nicht nutzt.
**Empfehlung für #144:** zuerst belastbar klären, wo die realen > 3 min herkommen
(lief Selbstkollision aktiv? steckt die Zeit im HTTP-/Viewer-/Schreibpfad, in einer
wiederholten Simulation oder im Kollisions-Advisor?), **bevor** `find_collisions`
optimiert wird — denn `find_collisions` ist mit ~11,5 s nicht der 3-Minuten-Treiber.
Ist das Ziel enger gefasst („`find_collisions` ≤ 10 s"), ist es mit H2 erreichbar.

## Einschränkungen / Unsicherheiten

- **„> 3 min" nicht reproduziert.** In dieser Umgebung (Produktiv-Konfiguration,
  self=False) misst der Fokus-Abschnitt ~19 s. Der einzige gemessene > 3-min-Pfad
  ist `self_collision=True` (~184 s). Woher die im Ticket beobachteten > 3 min real
  stammen, ist **offen** und sollte in #144 zuerst verifiziert werden. Der volle
  HTTP-`simulate`-Pfad (Lauf schreiben, `project.json` mutieren) wurde bewusst
  **nicht** gemessen (Seiteneffekte außerhalb des Spike-Auftrags); die Teilkosten
  Validieren+Serialisieren (~1 s) sind gemessen und klein.
- **Posten-Summe deckt ~9,5 s der ~11,5 s.** Die Differenz (~2 s) sind
  `SampleResult`/`_classify`/`_report` (nicht instrumentiert); die Verteilung der
  restlichen Posten ist davon unberührt und per cProfile am echten Code bestätigt.
- **Absolutzeiten sind maschinen-/lastabhängig** (Einzelmaschine, keine
  isolierte Bank); die **relativen** Anteile und Zählwerte sind die belastbare
  Grundlage. Die fcl-Distanzen selbst sind deterministisch (S0, byte-gleich).
- Zahlen gelten für **diesen** Modul-Lauf (ein wachsendes Hindernis, keine
  früheren Teile, kein Boden). Ein Abschnitt-Modus-Lauf mit Boden + früheren
  Teilen hätte mehr Hindernisgruppen und damit mehr fcl-Aufrufe pro nahem Sample —
  die `set_transform`-Dominanz bliebe qualitativ, die Anteile verschöben sich.

## Konsequenz (für #144)

1. Der Haupt-Hebel ist **nicht** die fcl-Distanz, sondern das **Positionieren der
   VHACD-Urteilsgeometrie** (`set_transform`, ~53 %). Jede Strategie, die die
   Prüfzeit spürbar drückt, muss hier ansetzen (weniger Stücke oder billigeres
   Positionieren) — mit Formtreue-Abwägung gegen S0/ADR-024.
2. **Travel-Ausdünnung (H2)** ist der sichere, hypothesengetriebene Hebel (~36 %).
3. **Distanz-nur-bis-Schwelle (H1)** und **Hindernis-Caching (H3)** sind klein bzw.
   wirkungslos — beide durch Messung entkräftet.
4. Bevor die 10-s-Zielmarke gesetzt wird: **die reale > 3-min-Beobachtung
   verifizieren** (Selbstkollision? voller Request-Pfad?). `find_collisions` allein
   ist ~11,5 s.

## Sonden

- `docs/spikes/s5_scripts/s5_harness.py` — reproduziert die reale Bahn + Gate.
- `docs/spikes/s5_scripts/s5_cprofile.py` → `last_cprofile.txt`.
- `docs/spikes/s5_scripts/s5_instrumented.py` → `last_instrumented.json`.
- `docs/spikes/s5_scripts/s5_threshold.py` → `last_threshold.json`.

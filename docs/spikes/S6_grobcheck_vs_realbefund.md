# Spike S6 — Grob-Check gegen den Realbefund validieren (Denkmal-Wand) (Issue #140, Karte #139)

Status: **grün (Validierung abgeschlossen)** · 2026-07-09

> AFK-Recherche für die Constraint-Entscheidung #141. Dieser Spike **validiert**,
> er repariert nicht: kein Produktivcode geändert (`core/src/**` unberührt). Alle
> Zahlen sind reproduzierbar über die Sonden unter `docs/spikes/s6_scripts/`.

## Frage

Meldet der fcl-freie Grob-Check (`fgc.collision.coarse.path_collides`) das reale
Eintauchen zuverlässig, das der volle Befund (`fgc.collision.check.find_collisions`)
zeigt? Er ist der Kandidat für den **Kollisions-Constraint der Zerlegung** (#141) —
dafür muss er dem vollen VHACD-Befund hinreichend treu sein, insbesondere **ohne
Falsch-Negative** (Grob-Check sagt „frei", voller Befund ist rot — das würde ein
kollidierendes Teil durch den Constraint durchlassen).

## Welche Teile — und warum

Das reale Projekt `projects/denkmal/project.json` (Druckjob `default`) ist per
`decomposition_kind: "modul"` zerlegt: **16 Module** (4 Länge × 4 Höhe, aus 3+3
Schnittebenen), Workstation `doosantisch`, Roboter `doosan_m1013`, Endeffektor
`30gut`. Ich nehme **alle 16 Module** — das ist die aktuelle, im Projekt
gespeicherte Zerlegung (die im Ticket genannten „12 Abschnitte" gehören zu einer
früheren `abschnitt`-Zerlegung; der Druckjob trägt heute die Modul-Weiche, s.
„−193 mm" unten). Nur zwei Module haben gespeicherte Läufe (`abschnitt-1`,
`abschnitt-20` — letzteres stammt aus einer **früheren** Zerlegung und liegt gar
nicht mehr im aktuellen 16-Teile-Plan). Die übrigen 14 Befunde werden über den
**Produktivpfad reproduziert** (kein Lauf geschrieben) — je Teil ~15–29 s, gesamt
~5,7 min, innerhalb des Budgets.

**Wichtige strukturelle Beobachtung vorab.** Bei Zerlegungsart **Modul** teilen
sich **alle 16 Teile dieselbe abstrakte Grob-Check-Eingabe**: gleiche
Teil-Wandfläche (785,4 × 822,1 × 510 mm, `z_offset = 0` — das Modul steht am
Druckort auf der Arbeitsfläche, ADR-022) und **dieselbe feste
Workstation-Platzierung** (`lateral 0 / standoff 485 / stand_height 0`). Der
Grob-Check kennt nur diese Rechteck-Box + Pose, nicht die echte Clay-Geometrie —
also liefert er **für alle 16 Teile bit-identisch dasselbe Urteil**. Der volle
Befund dagegen variiert je Teil (echtes Footprint-Prisma, echte Bahn). Das prägt
die Konfusionsmatrix (s. u.).

## Vorgehen

Beide Urteile je Teil aus **demselben Produktivpfad** wie die GUI, nicht aus
handgeschriebenen Konstanten (`docs/spikes/s6_scripts/`, Aufruf je Sonde im
Docstring; venv, Repo-Root):

- **Plan-Kontext** aus `actions.plan_for_job` (dieselbe Tür wie `simulate_section`)
  → 16 Sektionen mit Grenzen + je feste Platzierung; Roboter/Tool/Orientierung aus
  `actions._placement_context_for_job` + `job_orientation`.
- **Voller Befund** je Teil: `actions._slice_and_simulate_section` (in-memory, kein
  Lauf) → `finding.build_section_finding` mit **exakt** den Argumenten, die
  `simulate_section` für „modul" setzt (`mode="modul"`, `section_z0=0`, keine
  früheren Teile, kein Boden, `CollisionConfig()` default). Liefert
  `n_red`/`n_yellow`/`n_green`, `min_distance_mm`, `causer_link[]`,
  `causer_against[]` (via `report_to_dict`).
- **Grob-Urteil** je Teil: `coarse.path_collides` mit `Section.as_surface(thickness,
  z_offset=0)` (Modul-Konvention) + Teil-Platzierung + Roboter/Tool/Orientierung
  desselben Jobs. Grober AABB-Test der Glieder 1–3 gegen die Wandbox.
- **Falsch-Negativ-Sonde** (`s6_fn_probe.py`): variiert **nur den standoff** eines
  realen Moduls und legt Grob-Urteil neben den vollen Befund — sie erzwingt die
  „free"-Zeile, die die entartete Realzerlegung selbst nicht hergibt (s. u.).

Messumgebung: Windows 11, Python 3.14, Projekt-venv, `python-fcl 0.7.0.11`,
`doosan_m1013` (VHACD-Urteil + Hüllen-Breitphase), Tool `30gut`
(provisorische Endeffektor-Hülle aktiv). `self_collision=False` (Produktiv).

Reproduktions-Anker: der neu gerechnete Befund von `abschnitt-1` trifft den
gespeicherten `meta.collision`-Block byte-genau (8688 rot / 2405 gelb / 8442 grün,
min −290,444 mm) — derselbe Code, dieselben Eingaben.

## Ergebnis

### 1 — Konfusionsmatrix (Grob-Check × voller Befund), 16 Module

| | voll **rot** (n_red > 0) | voll **grün** (n_red = 0) |
|---|---|---|
| **Grob-Check „kollidiert"** | **TP = 16** | FP = 0 |
| **Grob-Check „frei"** | **FN = 0** | TN = 0 |

Alle 16 Module sind im vollen Befund **rot** (`n_red` 8688…15 760, min. Abstand
**−206,156 … −435,519 mm**), und der Grob-Check meldet für alle 16 „kollidiert".
**Null Falsch-Negative** — auf **diesem** Projekt lässt der Grob-Check kein reales
Eintauchen durch.

**Aber die Matrix ist entartet:** es gibt **keine „grüne" Zeile**. Die feste
Workstation-Platzierung (standoff 485 mm bei einem 510 mm dicken Modul) ist so
aggressiv, dass **jedes** Modul real tief kollidiert — und so tief (Glieder 2/3
tauchen Hunderte mm ein), dass selbst das grobe 9-Posen-Raster sicher anspricht.
Die Matrix bestätigt „fängt alle realen Kollisionen", **kann aber die eigentlich
gefährliche Frage nicht prüfen**: *Sagt der Grob-Check je fälschlich „frei", wenn
der volle Befund rot ist?* Dafür braucht es einen Fall, in dem ein Teil real *nicht
mehr überall* kollidiert — den liefert die Falsch-Negativ-Sonde (Abschnitt 5).

### 2 — Verursacher der roten Samples (aggregiert über alle 16 Module)

Über alle Module verursachen **189 594** rote Samples ihren `causer_link` so:

| verursachendes Glied | rote Samples | Anteil | vom Grob-Check `(1,2,3)` erfasst? |
|---|---:|---:|---|
| **link2** (Oberarm) | 87 425 | **46,1 %** | ja |
| **link4** (Handgelenk) | 74 719 | **39,4 %** | **nein** (bewusst außen) |
| **link3** (Ellbogen) | 27 450 | **14,5 %** | ja |
| link1 (Rotator) | 0 | 0 % | ja |

- **Von `ARM_LINK_INDICES = (1,2,3)` abgedeckt: 60,6 %** (114 875 Samples).
- **Strukturell verloren: 39,4 %** (74 719 Samples) — sie werden **allein vom
  Handgelenk (Glied 4)** am tiefsten verursacht, und das Handgelenk schließt der
  Grob-Check bewusst aus (ADR-024 Kontext 2: Handgelenk/Flansch/Endeffektor sitzen
  prozessbedingt an der Wandfront `y ≈ 0` und würden sonst chronisch fehlwarnen).
- `causer_against` ist zu **100 % `"modul"`** — jede reale Kollision ist Arm ↔
  wachsender **Druckstand** (das eigene Modul), kein Boden, keine früheren Teile,
  keine Selbstkollision. Der Gegenspieler, den der Grob-Check adressiert
  (Armglied ↔ Wandvolumen), ist **der richtige**.

Wichtige Lesart: `causer_link` ist je Sample das **tiefste** Glied. Dass das
Handgelenk auf 39,4 % der roten Samples der tiefste Verursacher ist, heißt nicht,
dass die Glieder 2/3 dort *nicht* auch eintauchen — auf **diesem** Projekt tun sie
es tief genug, dass der Grob-Check trotzdem „kollidiert" sagt. Die 39,4 % sind aber
die **strukturelle Blindstelle**: sobald ein Teil existiert, bei dem **nur** das
Handgelenk/der Endeffektor eintaucht, ist der Grob-Check blind (s. Abschnitt 5).

### 3 — Kosten je `path_collides`

Über 80 Aufrufe (16 Teile × 5 Wiederholungen), Default-Parameter:

| Kennzahl | Wert |
|---|---|
| Posen des groben Rasters (`_COARSE_FRACTION = 0.5`) | **9** je Aufruf |
| Median | **1,98 ms** |
| p95 | **3,64 ms** |
| Max | 4,31 ms |

**Weit unter 100 ms — Faktor ~25–50 Reserve.** Der Grob-Check ist billig; Kosten
sind kein Argument gegen ihn (und auch kein Argument, ihn *nicht* zu verfeinern).

### 4 — Sensitivität (Eindringschwelle × Rasterweite)

Da die Teil-Fläche für alle 16 Module identisch ist, ist die Sensitivität ein
Einmalbefund am Modul-Rechteck:

| `penetration_mm` | Raster | Posen | Urteil | Zeit |
|---:|---|---:|---|---:|
| 5 / 20 / 50 | grob (2× Weite) | 4 | kollidiert | ~1,2–2,2 ms |
| 5 / 20 / 50 | default (0,5×) | 9 | kollidiert | ~1,9–3,6 ms |
| 5 / 20 / 50 | fein (0,25×) | 81 | kollidiert | ~16–24 ms |

**In allen neun Kombinationen: „kollidiert".** Das Urteil ist hier **nicht** knapp
— die Glieder 2/3 tauchen Hunderte mm ein, weit jenseits jeder sinnvollen
Eindringschwelle. Selbst das feine 81-Posen-Raster bleibt unter 100 ms. Die
Sensitivität zeigt also: die **richtig-positiven** Fälle hängen weder an der
Schwelle noch am Raster. Die **Falsch-Negativen** (Abschnitt 5) hingegen hängen an
**beidem** — am Glieder-Zuschnitt **und** am groben Raster.

### 5 — Falsch-Negativ-Sonde: die gefährliche Zelle erzwungen

Weil die Realzerlegung keine „grüne" Zeile hat, variiert `s6_fn_probe.py` **nur den
standoff** von `abschnitt-1` (echte Clay-Geometrie, alles andere unverändert) und
legt Grob-Urteil neben den vollen Befund:

| standoff | Grob-Check | voll `n_red` | voll `n_yellow` | min. mm | tiefste Verursacher (rot) | |
|---:|---|---:|---:|---:|---|---|
| 485 (real) | **kollidiert** | 8688 | 2405 | −290,4 | link2 8115 / link3 401 / link4 172 | TP ✔ |
| 700 | **frei** | 3357 | 1000 | −177,5 | link2 1630 / link3 501 / link4 1226 | **FN** ✗ |
| 900 | **frei** | 5213 | 1678 | −45,3 | link4 4414 / link2 509 / link3 289 | **FN** ✗ |
| 1100 | frei | 0 | 135 | +38,4 | (nur gelb: link4 135) | TN ✔ |
| 1300 | **frei** | 5712 | 238 | −69,6 | **tool(7) 4998 / link5 714** | **FN** ✗ |

**Drei Falsch-Negative** — der Grob-Check sagt „frei", während der volle Befund
tausende rote Samples zeigt. Sie decken **beide** Fehlerquellen auf:

1. **Glieder-Zuschnitt** (900 mm, 1300 mm): bei 900 mm ist das **Handgelenk** (link4)
   der dominante Verursacher (4414 rot), bei 1300 mm **Endeffektor + link5** (5712
   rot) — genau die Glieder, die der Grob-Check bewusst ausschließt. Reine
   strukturelle Blindstelle.
2. **Rastergröbe** (700 mm): hier ist **link2** (im Grob-Check *enthalten*) mit 1630
   roten Samples ein Hauptverursacher — trotzdem urteilt der Grob-Check „frei". Sein
   9-Posen-Raster über die abstrakte Rechteck-Fläche trifft die eintauchenden
   Konfigurationen der echten, dichten Bahn (inkl. Anfahr-/Rückzugsbögen, Travel,
   Infill) schlicht **nicht**. Der Grob-Check prüft **9 Düse-nach-unten-Posen auf
   einem Rechteck**, der volle Befund die **~19 500 Samples der realen Bahn gegen das
   wachsende Prisma** — das sind strukturell verschiedene Dinge.

## Antwort auf die Ticket-Frage

**Nein — `path_collides` meldet das reale Eintauchen *nicht* zuverlässig genug, um
so wie er ist der Kollisions-Constraint der Zerlegung zu sein.**

Auf der realen Denkmal-Zerlegung liefert er zwar **null Falsch-Negative** (16/16
korrekt „kollidiert") — aber **nur, weil dort jedes Modul so tief kollidiert, dass
selbst ein grobes 9-Posen-Arm-Raster anspricht**. Das ist ein entarteter Fall (feste
zu enge Platzierung), kein Treue-Beweis. Sobald ein Teil real *nicht mehr überall
tief* kollidiert (Falsch-Negativ-Sonde: schon ein größerer standoff), produziert der
Grob-Check **leicht Falsch-Negative** aus zwei unabhängigen Gründen: (a) er ignoriert
Handgelenk (4/5) und Endeffektor, die real **39,4 %** der roten Samples am tiefsten
verursachen; (b) sein grobes Raster über eine abstrakte Rechteck-Fläche verfehlt
Eintauchungen der echten dichten Bahn — sogar von Gliedern, die er *prüft*.

**Für seinen entworfenen Zweck ist er in Ordnung:** der Grob-Check sortiert im
Optimalvorschlag (`suggest_placement`) offensichtlich schlechte Aufstellungen nach
hinten (Befund, kein Gate) — dafür genügt „grob, konservativ, billig". Als
**Constraint**, der Teile *durchlässt* oder *sperrt*, ist ein Werkzeug mit Fehlerbias
Richtung „frei" jedoch die falsche Richtung.

## Konsequenz für den Zerlegungs-Constraint (#141)

Der Constraint braucht **Treue mit Fehlerbias Richtung „kollidiert"** (konservativ),
nicht Richtung „frei". Zwei Wege, mit Zahlen:

- **A — Grob-Check ertüchtigen (nicht empfohlen als alleinige Lösung).** Minimal
  nötig: (1) Handgelenk (4/5) + Endeffektor (`TOOL_INDEX`) **mitprüfen**, aber vor
  der prozessbedingten Front-Fehlwarnung durch die **Freizone** am Druckpunkt
  schützen (sonst kehrt genau das ADR-024-Problem zurück, das ihre Ausklammerung
  vermeidet); (2) das Raster deutlich verdichten (fein = 81 Posen ~16–24 ms, immer
  noch < 100 ms) **und** gegen das echte Footprint-Prisma statt die volle
  Rechteck-Box testen. Kosten bleiben klein (< 100 ms). **Aber**: damit baut man
  Schritt für Schritt `find_collisions` nach — nur ohne dessen VHACD-Treue. Der
  Rest-Fehler (Hülle statt VHACD, Raster statt echter Bahn) bleibt und ist nicht
  quantifizierbar konservativ.
- **B — Constraint = verdünnte Instanz des echten Befunds (empfohlen).** Der treue
  Constraint ist eine **billigere Ausführung von `find_collisions` selbst**, nicht
  der geometrische Grob-Ersatz: Spike S5 zeigt, dass `find_collisions` ~11,5 s
  kostet und mit **Travel-Ausdünnung ~8,7 s / weiter ausdünnbar** wird — und dass er
  auf **diesem** Modul-Lauf ohnehin je Teil läuft. Ein Constraint, der das echte
  Prisma + die echte (verdünnte) Bahn + alle Glieder prüft, hat **keinen
  strukturellen Blindfleck**; sein Preis (Sekunden je Kandidat) ist die
  Grilling-Frage #141, keine Messfrage mehr.

**Empfehlung:** #141 sollte `path_collides` **nicht** unverändert als Constraint
setzen. Wenn ein billiger Vor-Filter gewünscht ist, taugt der Grob-Check als
**konservativer Aussortierer** („sicher kollidiert → raus", nie „sicher frei"), aber
die eigentliche Constraint-Entscheidung braucht den vollen (verdünnten) Befund. Die
minimale Grob-Check-Erweiterung, falls #141 doch bei ihm bleibt: **Handgelenk +
Endeffektor mit Freizonen-Schutz aufnehmen und das Raster verdichten** — beides
zusammen < 100 ms, beides adressiert je eine der zwei gemessenen Fehlerquellen; die
Rechteck-statt-Prisma-Lücke bleibt.

## Einschränkungen / Unsicherheiten

- **Entartete Konfusionsmatrix.** Die reale Zerlegung hat keine „grüne" Zeile (alle
  16 Module kollidieren real). TP=16/FN=0 belegt „fängt alle **tiefen**
  Kollisionen", **nicht** allgemeine Treue. Die Falsch-Negativ-Aussage stützt sich
  auf die standoff-Sonde (ein reales Modul, nur standoff variiert) — ein
  **konstruierter**, aber aus demselben Produktivpfad gerechneter Fall, kein
  zweiter Realdatensatz.
- **Modul-spezifisch.** Alle Zahlen gelten für Zerlegungsart **Modul** (ein
  wachsendes Hindernis, kein Boden, keine früheren Teile). Ein **Abschnitt**-Modus-
  Lauf hätte zusätzlich Boden + frühere Teile als Hindernisse — mehr rote Samples,
  andere Verursacher-Verteilung; der Glieder-Blindfleck (Handgelenk/Endeffektor)
  bliebe qualitativ, die Anteile verschöben sich.
- **Grob-Check heute nicht per-Teil im Einsatz.** In Produktion läuft
  `path_collides` **einmal auf der ganzen Wand** im Optimalvorschlag
  (`_coarse_collision_predicate` in `suggest_placement`), nie je Teil. Dieser Spike
  validiert die **hypothetische** Per-Teil-Nutzung, die #141 bräuchte — die
  Argumente sind aus demselben Produktivpfad abgeleitet, die Nutzung ist neu.
- **Absolutzeiten maschinenabhängig** (Einzelmaschine); die relativen Aussagen
  (< 100 ms, Verursacher-Anteile, FN-Fälle) sind die belastbare Grundlage. Die
  fcl-Distanzen sind deterministisch (S0).

## „−193 mm" — der Ticket-Wert

Das Ticket nennt als reale Beobachtung „der Arm taucht **oben
bis −193 mm** in frisch gedrucktes Material des eigenen Teils". Diesen Wert **konnte
ich nicht** einem gespeicherten Lauf oder Teil zuordnen — er ist **nicht** erfunden
geglättet, sondern bleibt als Diskrepanz stehen:

- Der gespeicherte `abschnitt-1`-Lauf zeigt **−290,444 mm**, der (aus einer früheren
  Zerlegung stammende, nicht mehr im Plan liegende) `abschnitt-20`-Lauf **−145,095
  mm**.
- Meine Reproduktion der **aktuellen 16 Module** zeigt min. Abstände von **−206,156
  bis −435,519 mm** — **kein** Teil trifft −193 mm.
- −193 mm ist offenbar die **Grill-Session-Beobachtung des Realdruck-Tests**
  (status.md, Karte #139), keine Kennzahl eines heute gespeicherten Laufs. Zwischen
  der Beobachtung und jetzt wurde die Zerlegung mehrfach neu geschnitten (der
  Druckjob trägt `cutplan`-Revision **16**) und die Platzierung geändert; der
  min. Abstand hängt stark an Modulgröße **und** standoff (die Falsch-Negativ-Sonde
  zeigt bei standoff 700 mm z. B. −177,5 mm, bei 1300 mm −69,6 mm). −193 mm passt
  größenordnungsmäßig in diesen Fächer, entspricht aber **keinem** aktuell
  gespeicherten oder rekonstruierten Teil. **Der Wert bleibt offen** und sollte, wenn
  #141 ihn braucht, gegen den dann gültigen Zerlegungsstand neu ermittelt werden.

## Sonden

- `docs/spikes/s6_scripts/s6_harness.py` — Plan-Kontext + `coarse_verdict` /
  `full_finding` je Teil aus dem Produktivpfad; direkt aufgerufen ein Selbsttest der
  Datenbasis (Sektionen, Fläche, Platzierung, gespeicherte `meta.collision`).
- `docs/spikes/s6_scripts/s6_validate.py` → `last_validate.json` — Konfusionsmatrix,
  Verursacher, Kosten, Sensitivität über alle 16 Module.
- `docs/spikes/s6_scripts/s6_fn_probe.py` → `last_fn_probe.json` — Falsch-Negativ-
  Sonde (standoff-Sweep an `abschnitt-1`).

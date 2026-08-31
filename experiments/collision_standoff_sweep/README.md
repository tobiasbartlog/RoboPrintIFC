# Abstand-Sweep: kollisionsfreies Höhenfenster eines Wandmoduls

**Messstudie zur Begründung der Höhen-Zerlegung im funktional gradierten
Lehm-3D-Druck (Doosan M1013).**

## Zusammenfassung

Für ein reales Wandmodul (Projekt `denkmal`, Modul 1, 785 × 822 mm, am Boden)
wird der Abstand zwischen Roboterbasis und Wandfront (`standoff`) von 150 mm bis
1200 mm durchgefahren. Pro Abstand simuliert der Produktivpfad den kompletten
Modul-Druck bottom→top; der Kollisionsbefund liefert je Bahn-Sample die signierte
Mindestdistanz, das verursachende Roboterglied und — über die Toolpath-Schicht —
die Druckhöhe. Zusätzlich wird die kinematische Erreichbarkeit **pro Höhe** aus
den verorteten IK-Warnungen gewonnen.

**Kernbefund:** Es gibt **keinen einzigen Abstand**, bei dem der volle 822-mm-Modul
gleichzeitig kollisionsfrei *und* erreichbar ist.

- **Nah (≈ 230 mm, der aktuelle automatische Vorschlag):** voll erreichbar, aber
  tief kollidierend (≈ 8000 rote Samples, Durchdringung bis −258 mm).
- **Fern (800–850 mm):** vollständig kollisionsfrei (0 rote Samples), aber
  **56–61 % des Druckpfades sind kinematisch unerreichbar**.
- **Dazwischen** existiert kein Fenster, das beide Bedingungen erfüllt.

Das ist der quantitative Beleg dafür, dass ein Modul dieser Höhe **in der Höhe
zerlegt werden muss** — die Zerlegung ist keine Optimierung, sondern eine
Machbarkeitsbedingung. Das limitierende Glied wandert dabei mit dem Abstand
(Unterarm → Oberarm → Unterarm → Handgelenk); die einfache Vorstellung „Schulter
unten, Unterarm oben" ist eine Näherung.

**Wie viele Bänder?** Die maximale von unten zusammenhängend **machbare** Bandhöhe
(kollisionsfrei *und* erreichbar) beträgt über alle Abstände **≈ 260 mm** (bei
standoff 400 mm). Da im Print-then-assemble-Workflow jedes Sub-Modul am Boden
startet und die Machbarkeit bei `(Abstand, Höhe)` direkt auf ein bodengestartetes
kürzeres Modul übertragbar ist (gleiche Armpose, gleiche gewachsene Geometrie
unterhalb der Höhe), folgt: Modul 1 (822 mm) braucht **mindestens ⌈822/260⌉ = 4
Höhenbänder** — nicht 2. Diese Zahl gilt unter den festen Hebeln (nur Abstand
variiert, seitl./Yaw/Podest fest); zusätzliche Freiheitsgrade könnten sie senken.

## Fragestellung

Aus der Domänen-Analyse (Roboterarm dreht sich beim nahen Druck in das Bauteil;
beim Erreichen der oberen fernen Ecken kollidiert ein oberes Glied):

1. **Unten** muss der Abstand groß genug sein, dass kein Glied beim Drucken in die
   nahe Wand einschwenkt.
2. **Oben** setzt die Kollision beim Erreichen der fernen Ecken eine maximale
   Druckhöhe — die natürliche **Schnittlinie**.
3. **Reichweite** begrenzt den Abstand nach oben: zu weit weg, und die fernen Ecken
   sind nicht mehr erreichbar.

Ziel dieser Messung: die drei Bedingungen aus **Simulationswerten** statt aus
Vermutung belegen und als Grundlage für eine Zerlegungs-Zielfunktion bereitstellen.

## Methodik

### Testfall

| | |
|---|---|
| Roboter | Doosan M1013 (`robots/doosan_m1013.json`, OPW-Kinematik) |
| Projekt / Modul | `denkmal`, Modul 1 (`abschnitt-1`) |
| Modulmaße | Länge 785,4 mm · Höhe 822,1 mm · Schichthöhe 10 mm |
| Wandstärke | 510 mm (Projektwert; vgl. Anmerkung unten) |
| Szenen-Modus | `modul` — wachsendes Modul + Arbeitsfläche, kein Boden/Kontext/Nachbarn (beide Module am Boden, wie im Print-then-assemble-Workflow) |
| Geplante Platzierung | standoff 230 mm · seitl. 0 mm · Aufstellhöhe 0 mm |
| Freie Variable | nur `standoff_mm` (seitl./Höhe/Yaw fest) |

### Simulations- und Auswertungspfad

Alles über den **Produktivpfad** — dieselben Türen wie `simulate_section`, kein
Lauf geschrieben:

1. `sectionsim.section_sim_context(...)` — loop-invarianter Unterbau (IFC/Slice)
   einmal gebaut und je Abstand wiederverwendet.
2. `sectionsim.slice_and_simulate_section(..., override=Override(placement={"standoff_mm": d}))`
   — übersteuert je Abstand nur den Standoff, baut Trajektorie (IK, `pose_source="planned"`).
3. `sectionsim.section_collision_finding(comp, config=None)` — voller Befund
   (`fgc.collision.finding.build_section_finding`): je Sample signierte
   Mindestdistanz + verursachendes Glied (`causer_link`) + Hindernis.
4. Schicht je Sample aus dem Toolpath: `fgc.collision.druckstand.layer_per_sample`
   (keine TCP-Höhen-Näherung). Höhe = Schicht × Schichthöhe.
5. Erreichbarkeit je Höhe: jede `reach`-Warnung aus `trajectory.meta.warnings` trägt
   `t_s`; über dieselbe Bisektion auf ihre Schicht abgebildet und gegen die
   Sampleanzahl der Schicht normiert (`reach_frac`).

### Kollisions-Klassifikation

Aus `fgc.collision.check._classify` (Sicherheitsabstand 50 mm; weicher Lehm macht
„knapp vorbei" zum Schaden):

| Mindestdistanz | Status | Bedeutung |
|---|---|---|
| `< 0 mm` | **rot** | echte Durchdringung / Kollision |
| `0 … 50 mm` | **gelb** | innerhalb Sicherheitsabstand |
| `≥ 50 mm` | **grün** | frei |

Gespeichert wird die *signierte* Mindestdistanz je Zelle, damit beide Grenzen
(harte Kollision bei 0 mm, Sicherheitsabstand bei 50 mm) im Nachhinein zeichenbar
sind. Glied-Index → Klartext über das URDF-/Manifest-Mapping
(`robots/collision/doosan_m1013/manifest.json`): 1 = `link_1` (über J1), 2 =
`link_2` (Oberarm, 620 mm), 4 = `link_4` (Unterarm, 559 mm), 5 = `link_5`
(Handgelenk), 7 = Werkzeug.

### Reproduktion

```bash
# venv-Python, aus dem Repo-Root; Geo-Extras (fgc-core[geo]) nötig
PYTHONPATH=core/src python experiments/collision_standoff_sweep/sweep.py \
    --standoff-min 150 --standoff-max 1200 --standoff-step 50 --module-index 0
PYTHONPATH=core/src python experiments/collision_standoff_sweep/plots.py
```

Deterministisch (keine Zufallskomponente). Laufzeit ≈ 5 min (22 Abstände × ~13 s je
voller Befund über ~19,5 k Samples). Rohdaten in `data/` (`grid.csv`, `summary.csv`,
`meta.json`, `run.log`), Abbildungen in `data/figures/`.

## Ergebnisse

Verlauf über den Abstand (Auszug aus `summary.csv`; `reach%` = Anteil erreichbarer
Pfad-Samples = 1 − reach-Warnungen / Samples):

| standoff (mm) | rot | gelb | grün | min. Distanz (mm) | unterste nicht-grüne Höhe | limit. Glied unten | reach % |
|--:|--:|--:|--:|--:|--:|:--|--:|
| 150 | 10884 | 2299 | 6338 | −304,6 | 10 mm | link_4 (Unterarm) | 100 |
| 230 (Vorschlag) | ~8500 | – | – | ~ −260 | ~40 mm | link_2 (Oberarm) | ~99 |
| 300 | 3726 | 4515 | 11318 | −240,7 | 60 mm | link_2 (Oberarm) | 99 |
| 400 | 3176 | 1165 | 15270 | −195,4 | 260 mm | link_2 (Oberarm) | 96 |
| 500 | 3803 | 862 | 14992 | −166,5 | 200 mm | link_2 (Oberarm) | 88 |
| 600 | 5203 | 841 | 13593 | −93,0 | 80 mm | link_2 (Oberarm) | 75 |
| 700 | 2492 | 3882 | 13146 | −31,2 | 140 mm | link_3 (Ellbogen) | 55 |
| 750 | 374 | 4223 | 14919 | −9,4 | 200 mm | link_4 (Unterarm) | 49 |
| **800** | **0** | 1734 | 17782 | **+19,1** | 250 mm | link_4 (Unterarm) | **44** |
| **850** | **0** | 59 | 19457 | **+48,5** | 430 mm | link_4 (Unterarm) | **39** |
| 900 | 476 | 238 | 18802 | −42,0 | 790 mm | link_5 (Handgelenk) | 33 |
| 1000 | 3808 | 238 | 15470 | −68,5 | 650 mm | link_5 (Handgelenk) | 22 |
| 1150 | 13804 | 238 | 5474 | −69,6 | 230 mm | link_5 (Handgelenk) | 2 |
| 1200 | 0 | 0 | 19516 | (+877,6) | – | – | 0 (voll unerreichbar) |

Der letzte Abstand (1200 mm) ist degeneriert: der Modul liegt vollständig außerhalb
der Reichweite (100 % IK-Warnungen), „keine Kollision" ist dort bedeutungslos.

### Abbildungen (`data/figures/`)

- **`fig1_clearance.png`** — Heatmap Abstand × Höhe der signierten Mindestdistanz;
  schwarze Kontur = Kollisionsgrenze (0 mm), gestrichelt = Sicherheitsabstand
  (50 mm); Kurve = unterste nicht-grüne Höhe (Kollisionsbeginn von unten).
- **`fig2_limiter.png`** — je Zelle das limitierende Glied: zeigt, wie sich der
  Verursacher über Abstand und Höhe verschiebt.
- **`fig3_tradeoff.png`** — die „Schere": kollisionsfreie Höhe von unten steigt mit
  dem Abstand, erreichbare Höhe von unten fällt; ihr Minimum (machbar) bleibt ≤ 260 mm.
- **`fig4_feasible.png`** — die machbare Region (kollisionsfrei **und** erreichbar):
  belegt, dass kein Abstand den vollen Modul deckt.

## Schlussfolgerungen für die Zielfunktion

1. **Zerlegung ist eine Machbarkeitsbedingung, keine Kür.** Kein Abstand erfüllt
   Kollisionsfreiheit und Erreichbarkeit für den vollen 822-mm-Modul gleichzeitig.
   Der Suchraum ist erst durch Höhen-Zerlegung nicht-leer — und zwar in **≥ 4
   Bänder** (max. machbare Bandhöhe ≈ 260 mm), nicht in 2.
2. **Kollision und Reichweite sind gegenläufig im Abstand.** Kollisionsfreiheit
   verlangt große Abstände (≥ 800 mm), Erreichbarkeit kleine (≤ ~350 mm für > 95 %).
   Genau diese Kopplung macht eine Zielfunktion nötig, die beide Achsen
   gleichzeitig führt.
3. **Der aktuelle Vorschlag (230 mm) optimiert nur die Reichweite** und nimmt die
   Kollision als nachträgliches Etikett hin — konsistent mit dem Befund, dass die
   nahe Platzierung voll erreichbar, aber tief rot ist.
4. **Das limitierende Glied ist abstands- und höhenabhängig.** Für eine
   Zielfunktion genügt nicht eine feste „Schnitthöhe"; die maximale kollisionsfreie
   Höhe `h_frei(d)` und der erreichbare Abstandsbereich müssen aus der machbaren
   Region gelesen werden.

**Kandidat für die Zielfunktion (Folgeschritt):** minimiere die Zahl der Module /
Fugen unter der harten Bedingung, dass jede Höhenzone in der machbaren Region liegt
— d. h. wähle je Zone einen Abstand `d` mit `reach(d,h) ≥ Schwelle` und
`Mindestdistanz(d,h) ≥ Sicherheitsabstand` für alle `h` der Zone, und setze die
Schnitthöhen dort, wo die machbare Region endet.

## Erweiterung: Dicken-Studie über reale Wände

Zweite Messreihe (`sweep_thickness.py` → `data_thickness/`, `thickness_plots.py`):
Der Abstand-Sweep wird über **mehrere reale, öffnungsfreie Wände** des denkmal-
Modells gefahren (256 Wände, 161 öffnungsfrei; Auswahl `opening_count == 0`),
kuratiert auf **Höhe ≈ 3060 mm** (fast konstant) und **Dicken 80–620 mm**. Jede Wand
wird frisch modul-zerlegt (`plan_for_job`, keine gespeicherten Schnitte), gemessen
wird Modul 0. `pc.wall` kommt direkt aus der IFC-Geometrie (Assessment umgangen);
jede Wand läuft in einem **eigenen Subprozess** (isoliert native Crashes, s. u.).

**Ergebnis** (max. von unten machbare Bandhöhe = kollisionsfrei & erreichbar, über
alle Abstände; „Bänder" = ⌈Wandhöhe 3060 / Bandhöhe⌉):

| Dicke (mm) | Modul L×H (mm) | max. Bandhöhe (mm) | bei Abstand | Bänder für 3060 mm |
|--:|:--|--:|--:|--:|
| 80  | 936×765  | 760 | 650 | 5 |
| 130 | 620×765  | 760 | 450 | 5 |
| 180 | 825×765  | 720 | 750 | 5 |
| 225 | 902×765  | 530 | 450 | 6 |
| 300 | 1124×765 | 300 | 850 | 11 |
| 489 | 844×765  | 570 | 450 | 6 |
| 620 | 1106×765 | **10** | 150 | **∞ (nicht druckbar)** |
| 505 | — | — | — | nativer Crash (s. u.) |

**Kernbefunde:**

1. **Dickere Wände schrumpfen die machbare Region.** Der Trend ist klar fallend:
   von ~760 mm Bandhöhe bei 80–130 mm auf 300 mm bei 300 mm Dicke. Die **620-mm-Wand
   hat gar keine machbare Region mehr** (Bandhöhe 10 mm) — ihr Modul ist bei *keinem*
   Abstand kollisionsfrei-und-erreichbar (fig `figT2`: durchgehend rot/grau). Dicke
   verschiebt zudem den optimalen Abstand nach außen (dickere Wand = fernere Front).
2. **Die Modul-Länge (Grundriss) ist ein starker Mit-Treiber** (Confound, in `figT1`
   als Punktfarbe kodiert). Die zwei Einbrüche (300 mm → 300 mm; 620 mm → 10 mm) sind
   die **längsten** Module (~1100 mm); die 489-mm-Wand erholt sich auf 570 mm, weil ihr
   Modul kürzer ist (844 mm). Für die Zielfunktion heißt das: **Dicke UND
   Modul-Grundriss** bestimmen die Bänderzahl gemeinsam — dicke *und* lange Module
   sind faktisch nicht druckbar.
3. **Nativer Absturz im Kollisions-Stack (Fund).** Die 505-mm-Wand
   (`2d9LuxY1D3owMKr995JmXw`, 990×3060, öffnungsfrei) lässt den Kollisions-Befund
   (python-fcl/VHACD) mit **0xC0000005 (Speicherzugriffsfehler)** abstürzen — ein
   *nativer* Crash, den kein Python-`try/except` fängt. Deshalb die Subprozess-
   Isolation. Das ist ein echter Robustheitsbug auf realer, gültiger Geometrie und
   sollte als Issue verfolgt werden (reproduzierbar via
   `sweep_thickness.py --gids 2d9LuxY1D3owMKr995JmXw`).

**Abbildungen (`data_thickness/figures/`):**
- `figT1_band_vs_thickness.png` — max. machbare Bandhöhe über Wandstärke; Punktfarbe = Modul-Länge (Confound).
- `figT2_feasible_maps.png` — Feasible-Maps (Abstand × Höhe) je Wand, nach Dicke sortiert.

## Erweiterung: IK-Konfiguration (Pilot)

Dritte Messreihe (`sweep_ik.py` → `data_ik/`, `ik_plots.py`): Validitätstest für die
bisherigen Ergebnisse. Der Doosan hat je Werkzeugpose bis zu **8 Gelenk-
konfigurationen** (shoulder×elbow×wrist ∈ {a,b}³); die früheren Studien nutzten
**eine** (die auto-Wahl von `select_along_path`, die auf Bahn-Kontinuität optimiert,
nicht auf Kollisionsvermeidung). Frage: Sind die gemessenen Kollisionen Artefakte der
Konfigurationswahl?

**Setup:** denkmal Modul 0 (785×822 @ 510 mm), base=0, lateral=0, Abstand-Sweep ×
alle 8 Konfigs + auto. Latte: streng (reach ≈ 100 % & grün).

**Ergebnis — IK-Konfigwahl rettet erheblich:**

| Konfig (eine je Modul) | H_max (kontig. machbar von unten) |
|:--|--:|
| **baa** (shoulder b) | **450 mm** |
| auto / aaa | 250 mm |
| alle übrigen | ~10 mm (fast überall unerreichbar/kollidiert) |

1. **+80 % machbare Bandhöhe** allein durch die richtige Einzel-Konfig (250 → 450 mm).
   Der Gewinn kommt fast vollständig vom Schulter-Flip (a→b, Konfig `baa`).
2. **Stufe a (gemischte Konfig mit Travel-Übergängen) ist unnötig:** die per-Zelle-
   Union (freies Wechseln) liefert *ebenfalls* 450 mm — eine einzelne Konfig holt den
   vollen Gewinn. Kein Übergangsmodell nötig.
3. **Konsequenz für die Zielfunktion:** IK-Konfiguration ist ein **modulweiter Hebel**
   (welche der 8 fürs ganze Modul), neben Abstand und Basishöhe. Die früheren
   Einzel-(auto)-Konfig-Studien sind entsprechend **pessimistisch** (~80 % für dieses
   Modul); der Produktions-Zerleger nutzt IK bereits als Hebel und liegt damit näher am
   wahren Optimum als unsere auto-Baseline.

**Abbildungen (`data_ik/figures/`):** `figIK1_ab_feasible.png` (A/B auto vs. best-over-8),
`figIK2_winner.png` (welche Konfig rettet welche Zelle — fast durchweg `baa`).

## Erweiterung: Basishöhe / Roboter-Podest (Pilot)

Vierte Messreihe (`sweep_ik.py --base-heights …` → `data_base/`, `base_plots.py`):
Am selben Modul die **Aufstellhöhe der Roboterbasis** (0/300/600 mm) × alle 8 IK-
Konfigs, je Basishöhe best-over-8. Der Roboter kann heute nicht hoch — die Studie
beziffert, ob sich ein Podest lohnt.

| Basishöhe | H_max (beste Einzel-Konfig) | Gewinner |
|--:|--:|:--|
| 0 | 490 mm | baa |
| **300** | **640 mm** | baa |
| 600 | 170 mm (union 390) | aab |

1. **Optimum bei ~300 mm:** +150 mm Bandhöhe (490 → 640). **Über-Anheben (600 mm)
   kippt** — die Basis blickt von oben, der Wandfuß wird unerreichbar, H_max (von
   unten zusammenhängend) bricht ein. Nicht monoton.
2. **Der Gewinner-Konfig verschiebt sich** mit der Basishöhe (baa → aab bei 600 mm) —
   Beleg, dass die optimale IK-Konfig setup-abhängig ist (nie hartkodieren; das
   Prädikat-Gitter optimiert pro Geometrie über alle 8).
3. **Kombiniert:** base=0/auto ~250 mm → beste IK (baa) 490 mm → +300-mm-Podest
   **640 mm** ≈ **2,5×** — allein durch IK-Konfig + moderates Podest.
4. **Stufe a (Konfig-Mischen) nur in Über-Höhen relevant:** bei 600 mm ist union
   (390) >> beste Einzel (170); am Optimum (300 mm) baa allein = 640 (union = single).

**Abbildung:** `data_base/figures/figB1_base_vs_hmax.png`.

## Grenzen der Studie

- Ein Projekt (`denkmal`), aber jetzt **7 reale Wände** über den Dicken-Bereich
  80–620 mm (Dicken-Studie). Verallgemeinerung über weitere Modelle steht aus.
- **Längen-Confound (gemessen, nicht kontrolliert):** die realen Wände wurden „wie
  sie sind" gewählt, deshalb variiert die Modul-Länge (620–1124 mm) mit der Dicke
  und beeinflusst die Reichweite. Der Effekt ist in `figT1` sichtbar gemacht
  (Punktfarbe), aber nicht herausgerechnet. Wer Dicke *isoliert* will, hält
  L×H fest (synthetische Module oder auf feste Länge zugeschnittene reale Wände).
- Nur `standoff` variiert; seitlicher Versatz, Aufstellhöhe und Yaw fest. Ein
  Podest (Aufstellhöhe) ist im `modul`-Modus bewusst 0 (beide Module am Boden).
- `reach_frac`-Schwelle (50 % der Samples je Höhe) ist eine Heuristik zur
  Höhen-Klassifikation; die Rohanteile stehen in `grid.csv` für andere Schwellen.
- **Anmerkung Wandstärke (geklärt):** Die im Screenshot gezeigten „176 mm" waren
  eine andere Wand als die gemessene 510-mm-Wand (Modul 1 der ersten Studie) —
  bestätigt vom Projektverantwortlichen. Das Modell enthält Wände von 60 bis
  2100 mm Dicke; die Dicken-Studie deckt 80–620 mm ab.
- **Nativer Crash:** Der Kollisions-Befund stürzt auf der 505-mm-Wand nativ ab
  (0xC0000005) — noch nicht diagnostiziert, nur isoliert. Als Issue zu verfolgen.

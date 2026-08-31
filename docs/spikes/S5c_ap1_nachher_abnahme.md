# Spike S5c — AP-1-Nachher-Messung + Abnahme: SDF-Backend vs. FCL-Referenz, je Aufrufort (Issue #215, PRD #183)

Status: **grün (Messung + AP-1-Abnahme abgeschlossen)** · 2026-07-14

> Nachher-Hälfte von US 13 der PRD #183 (Arbeitspaket 1 — Glied-SDF-Prüf-Tür) und
> die **AP-1-Abnahme**. Konfigurationsgleich zur Baseline (Spike S5b, #206):
> dieselbe Bahn, derselbe `travel_stride=5`, dieselbe verdünnte Auswahl, derselbe
> Rechner. Neu ist allein das **Backend**: die Punkt-gegen-Glied-SDF-Inversion
> (`SdfObstacleProvider`, #213) statt der reinen FCL-Referenz. Der Spike **misst**;
> Produktivcode wurde nicht geändert (nur die benannte Konstante
> `DEFAULT_CALL_BUDGET`, s. u.).

## Frage

Wie schnell ist der Glied-SDF-Pfad (#213) gegenüber der FCL-Referenz **je Aufrufort**
(Arm↔Hindernis vs. Selbstkollision/Arm↔Arm) auf der produktiv verdünnten
Abschnitt-1-Bahn — der **Y-fach-Beleg** für US 13/US 21 und die Vergleichsgröße für
das #205-G1-Gate („≥10× vs. Glied-SDF")? Und: welches **Default-Aufruf-Kontingent**
folgt aus der SDF-Zeit nach dem Grill-Budget-Verfahren (2026-07-14)?

## Warum die Baseline neu erhoben wurde (Drift)

Die Baseline (#206) warnte ausdrücklich: die Pipeline driftet seit S5, die
**Absolutzahlen sind nicht zu übernehmen** — #215 muss die Vorher-Hälfte
**unmittelbar vor** der Nachher-Hälfte mit **derselben Sonde** neu erheben. Genau so:
Die neue Sonde `s5_ap1_after.py` misst FCL und SDF im selben Prozess auf derselben
verdünnten Auswahl. Der Drift ist real und bestätigt die Warnung — die
FCL-`find_collisions`-Zeit (self=False) ist heute **4,23 s** (Median), nicht die
7,03 s aus #206; nur die **konfigurationsgleiche** Neuerhebung liefert einen
belastbaren Y-Faktor. (Die belastbare Größe bleiben Zählwerte + Verhältnis, nicht die
Absolutsekunden — Einzelmaschine, keine isolierte Bank.)

## Messkonfiguration (konfigurationsgleich zu S5b/#206)

| Parameter | Wert |
|---|---|
| Bahn / Reproduktion | `slice_and_simulate_section('denkmal','abschnitt-1')` → `find_collisions` |
| Zerlegungsart | `modul` (freizone 40 mm, safety 50 mm) |
| Endeffektor | Tool `30gut`, provisorische Hülle aktiv |
| Travel-Stride | **5** (`finding.DEFAULT_TRAVEL_STRIDE`, `thin_travel_indices` wie der Realpfad) |
| Samples verdünnt | **11 968** (55 Schichten) |
| Backend nachher | **sdf** (`SdfObstacleProvider`, #213 — Glied-SDF-Artefakt `robots/collision/doosan_m1013/sdf/`) |
| Rechner | Windows 11 (10.0.26200), Python 3.14.0, Intel64 Core Ultra (Model 197), Projekt-venv, `python-fcl 0.7.0.11`, `doosan_m1013` |

## Gates (Voraussetzung für den Y-Faktor)

- **Determinismus:** FCL und SDF je zweimal (self=False) → byte-identisch. Gate grün.
- **Befund-Identität (#213-Regressionsanker):** FCL == SDF je self-Konfiguration —
  rot/gelb/grün, Verursacher-Sample (`worst_index`) und Eindringtiefe byte-identisch:
  - self=False: **5106 rot / 1142 gelb / 5720 grün**, min **−149,824 mm**, worst_index 9794 (FCL == SDF).
  - self=True: **5123 rot / 6845 gelb / 0 grün**, min **−214,13 mm**, worst_index 11542 (FCL == SDF).

  **Der Speedup gilt nur mit identischen Befunden** — er ist hier durch Konstruktion
  belegt (SDF filtert konservativ, FCL urteilt im Grenzband; nur sicher-grüne
  Abstandszahlen dürfen beiderseits konservativ abweichen).

## Ergebnis — Y-fach je Aufrufort (EHRLICH)

| Aufrufort | FCL | SDF | **Y = FCL/SDF** |
|---|---:|---:|---:|
| **Arm↔Hindernis** (self=False, produktiv, Median über 3) | **4,23 s** | **9,77 s** | **0,43 ×** |
| **Selbstkollision (Arm↔Arm)** (isoliert: Wall(self=True) − Wall(self=False)) | **100,5 s** | **237,6 s** | **0,42 ×** |

**Der ehrliche Befund: auf diesem tiefroten Denkmal-Modul ist die SDF-Tür ~2,3–2,4×
LANGSAMER — auf beiden Aufruforten.** Das ist kein Fehlschlag, sondern **exakt der in
#213 vorab dokumentierte Befund** (Design-Log 2026-07-14, #213): Byte-Identität
erzwingt auf tief roten Bahnen ohnehin den Transform-Replay + die FCL-Urteile im
Grenzband; die SDF-Breitphase kommt oben drauf, ohne Abfragen sparen zu können, wenn
praktisch jedes Sample im Grenzband liegt (5106 rot + 1142 gelb von 11 968, self=True
sogar 0 grün). Der Gewinn der SDF-Inversion liegt bei **grünen/gelben Bahnen** (die
Suche #216/#217 bewertet ganz überwiegend nicht-kollidierende Kandidaten), nicht bei
Dauer-Rot. Für den Paper-Beleg heißt das: der Y-Faktor ist **aufrufort- UND
bahn-abhängig** und wird getrennt berichtet — Dauer-Rot ist der ungünstigste Fall.

## AP-1-Abnahme (relativ, per Entscheidung 2026-07-14)

Die AP-1-Abnahme ist **relativ** definiert (Design-Log 2026-07-14, PRD #183): Vorher/
Nachher-Beleg je Aufrufort **plus Befund-Identität**; die absolute 10-s-Marke bleibt
bei #144/#150. Beide Teile liegen vor:

1. **Vorher/Nachher je Aufrufort** — die Tabelle oben, konfigurationsgleich,
   deterministisch reproduzierbar (`s5_ap1_after.py`).
2. **Befund-Identität** — der #213-Regressionsanker greift byte-identisch (Gates oben).

**AP 1 ist damit abgenommen** (die Glied-SDF-Prüf-Tür ist gebaut, misst
konfigurationsgleich und liefert byte-identische Befunde). Der ehrliche Speedup-Stand
(< 1 auf Dauer-Rot) ist als Befund festgehalten, nicht kaschiert; die #213-Optionen
(Shen-Batching quer zur Bahn / historie-freies Urteil) bleiben für spätere
Beschleunigung notiert, blockieren die Abnahme aber nicht.

## #205-G1-Gate (Vergleichsgröße)

Das G1-Gate von PRD #205 („≥10× vs. Glied-SDF") braucht die Glied-SDF-Zeit als
Nenner. Diese Messung liefert sie: **Arm↔Hindernis 9,77 s, Selbstkollision-Block
237,6 s** (SDF, produktiv verdünnt, self getrennt) — das ist die Größe, gegen die die
GPU-Vorsortierung ihren ≥10×-Faktor belegen muss. #205 ist per Kommentar informiert.

## Default-Aufruf-Kontingent (Grill-Budget-Verfahren 2026-07-14)

Verfahren: **größte runde Aufruf-Zahl**, deren Hintergrundlauf ≤ ~5 min (300 s) auf
der Referenzmaschine bleibt; ein „Aufruf" = eine exakte Prüf-Tür (`find_collisions`
je Kandidat, produktiv self=False, SDF-Backend). Messung:

- SDF-Zeit je Aufruf (self=False, Median): **9,77 s**.
- 300 s / 9,77 s = **30** roh ⇒ größte runde Zahl ≤ 30 (1-2-5-Leiter): **20**.
- Vorhersage: 20 × 9,77 s ≈ **195 s** ≤ 300 s. ✓

Festgeschrieben als **`fgc.decompose.propose.DEFAULT_CALL_BUDGET = 20`** (dasselbe
Modul, das die Beam-Suche #217 importiert; die Beam-Breite k leitet sich daraus ab).
Je Druckjob übersteuerbar — die Provenienz trägt den Wert, eine langsamere Maschine
ergibt einen längeren, aber bit-gleichen Lauf. Der Wert ist **konservativ** (gemessen
auf dem langsamsten, tiefroten Fall; grüne Kandidaten laufen schneller).

## Sonde

`docs/spikes/s5_scripts/s5_ap1_after.py` (Sonde 5) — baut auf `s5_harness.build_inputs()`
(die reale Abschnitt-1-Bahn, um Roboter + `DruckstandSpec` erweitert, damit der
`SdfObstacleProvider` konfigurationsgleich zur FCL-Referenz gebaut wird) und ruft das
**echte** `find_collisions` je Backend × self-Konfiguration. Aufruf (venv, Repo-Root):

    ./.venv/Scripts/python.exe docs/spikes/s5_scripts/s5_ap1_after.py

Schreibt `docs/spikes/s5_scripts/last_ap1_after.json` (die hier zitierten Zahlen);
das Skript bricht ab, falls ein Gate (Determinismus / Befund-Identität) fällt.

## Einschränkungen

- **Absolutzeiten sind maschinen-/lastabhängig** (Einzelmaschine, `-n auto`-xdist im
  Hintergrund kann konkurrieren). Belastbar sind das **Verhältnis** je Aufrufort und
  die **Zählwerte**; die fcl-Distanzen selbst sind deterministisch (S0).
- Zahlen gelten für **diesen** tiefroten Modul-Lauf (ein wachsendes Hindernis, kein
  Boden, keine früheren Teile). Ein Lauf mit überwiegend grünen Kandidaten (der
  Regelfall der Suche) fiele zugunsten des SDF-Backends aus — hier bewusst der
  ungünstigste Fall gemessen (kein Schönrechnen).
- Das Kontingent (20) ist aus der SDF-Zeit dieses Worst-Case abgeleitet und damit eine
  **untere** Schranke der real erreichbaren Aufrufzahl.

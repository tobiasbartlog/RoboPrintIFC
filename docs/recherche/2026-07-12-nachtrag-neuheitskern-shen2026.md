# Nachtrag Recherche II: Neuheitskern-Korrektur (Shen et al. 2026) + drei neue Schienen

**Datum:** 2026-07-12
**Vorgänger:** [2026-07-10-adaption-chunking-literatur.md](2026-07-10-adaption-chunking-literatur.md)
**Anlass:** Gezielte Nachrecherche zu Optimierungspotenzialen für PRD #183 mit
Stresstest des zentralen Querbefunds („niemand prüft den Arm gegen den
wachsenden Druckstand").

**Verifikations-Status (ehrlich):** Shen et al. 2026 als **Volltext gelesen**
(lokales PDF, 11 Seiten). cuRobo über Projektdoku + Paper-Abstract geprüft
(Sekundärquellen). Die Befunde zu Surrogat-Lernen und Umsetz-Sequenzierung
stützen sich auf Web-Suchläufe (Trefferlage, keine Volltextprüfung) — sie
belegen eine *Lücke* (keine einschlägigen Treffer im Bau-Kontext), was
naturgemäß schwächer belegbar ist als ein positiver Fund.

---

## 1 Shen et al. 2026 — der Querbefund fällt in seiner absoluten Form

**Quelle:** Shen, Qu, Xu, Huang, Dai, Li, Fang: *Trajectory Optimization for
Collision-Aware Redundant Robotic Multi-Axis Additive Manufacturing by
Constrained Gradient Projection*, [arXiv 2606.29766](https://arxiv.org/abs/2606.29766)
(eingereicht 29.06.2026, Preprint under review; Gruppe um Guoxin Fang / CUHK,
dieselbe Gruppe wie INF-3DP).

**Was das Paper macht (Volltext-verifiziert):**

- 8-DOF-System (ABB IRB 1200, 6 DOF + 2-DOF-Positionierer), Desktop-Maßstab
  (Stanford-Bunny 168×130×182 mm, PLA bei 200 °C, 1,2-mm-Düse).
- Trajektorienoptimierung für eine **gegebene** Bahn (field-based Slicer):
  Redundanzauflösung per Gradientenprojektion auf die
  Selbstbewegungs-Mannigfaltigkeit; Bahnposition als harte
  Gleichheitsnebenbedingung (iterative Jacobi-Projektion), Glätte
  (v/a/Ruck) + Orientierung + Kollision als Straf-Terme.
- **Kollisionsmodell (der für uns zentrale Teil):** je Roboterglied ein
  **statisch vorberechnetes SDF im Glied-Koordinatensystem**; das wachsende
  Werkstück ist eine **Punktwolke** aus den bereits deponierten
  Materialblöcken, je Wegpunkt fortgeschrieben. Abfrage: Punkte ins
  Glied-System transformieren, Feld auslesen; Bounding-Box-Filter + Top-K
  begrenzen die aktive Menge; Selbstkollision im selben Schema (Punkte von
  Glied A gegen SDF von Glied B). Punktabstand 2 mm bei ~3 mm
  Sicherheitsmarge; GPU-parallel ausgewertet.
- **Zahlen:** mittlerer Bahnfehler < 10 µm; Kollisionsverletzungen bei 50k
  Wegpunkten in ~9 s eliminiert; bis 10,2× schneller als SQP-Baseline;
  max. Ruck −77,6 %. Physische Drucke (Bunny, TopOpt-Bracket 89k Wegpunkte,
  Prothesenschaft konformal) erfolgreich.
- **Eigene Limitierungen (Discussion):** empfindlich gegen Initialisierung;
  Singularitäten **nicht** behandelt (nur indirekt über v/a-Grenzen,
  explizit Future Work); Punktdichte kostet Speicher/Laufzeit.

**Konsequenz für den Querbefund:** Der Satz „keine Quelle prüft einen
Armkörper gegen den wachsenden Druckstand" ist in seiner absoluten Form
**falsch geworden** — Shen et al. tun genau das, differenzierbar, auf
Trajektorienebene. Der Querbefund wird **enger und bleibt tragfähig**:

> Keine Quelle setzt den Arm-gegen-wachsendes-Werkstück-Check als
> **Schiedsrichter einer diskreten Zerlegungs- und Platzierungssuche im
> Bau-Maßstab, ab IFC** ein. Shen et al. optimieren, *wie* ein redundantes
> System eine gegebene Bahn abfährt; wir entscheiden, *in welche Teile* eine
> Wand zerfällt, *wo* der Roboter dafür steht und *ob* das Teil überhaupt
> druckbar ist.

**Abgrenzung im Detail (fürs Paper zitierfähig):**

1. **Maßstab und Gegenstand:** Bauteil auf Positionierer (≤ 0,2 m) vs.
   Gebäudewand (Meter), BIM-Eingang, Umsetzvorgänge, Podest/Workstation.
2. **Ebene:** Trajektorienoptimierung (kontinuierlich, eine Bahn) vs.
   Zerlegungs-/Platzierungssuche (diskret, viele Kandidaten) — die Verfahren
   konkurrieren nicht, sie liegen auf verschiedenen Pipeline-Stufen.
3. **Redundanz-Voraussetzung:** Die Gradientenprojektion lebt von den 8 DOF.
   Unser M1013 hat 6 DOF bei voll bestimmter Düsenpose (`nozzle_quat`,
   #61) — es gibt keine kontinuierliche Redundanz zu optimieren; auf unser
   Problem ist die Methode nicht anwendbar, nur ihr Kollisionsmodell ist
   verwandt.
4. **Singularitäten:** bei Shen et al. offen (Future Work); bei uns über
   Konditionsmaß + Advisor (#11/#65) bereits behandelt — ein Punkt, an dem
   wir *vor* der Quelle liegen.

## 2 Technik-Übernahme: die Glied-SDF-Inversion (Entscheidung für #183)

Das Kollisionsmodell von Shen et al. **invertiert** unseren bisherigen
Plan (Option E der Vorgänger-Recherche: SDF um den Druckstand, je Schicht
fortgeschrieben) — und löst dabei genau dessen wunden Punkt:

| | Option E alt (Druckstand-SDF) | Inversion (Glied-SDF, Shen) |
|---|---|---|
| Teure Karte um … | die Wand — die sich **ständig ändert** | die Glieder — die sich **nie ändern** |
| Kartenbau | zur Planungszeit, Fortschreiben je Schicht (US 15) | einmalig offline je Roboter, versioniertes Artefakt |
| Kartengröße | ganzer Wandbereich (m³) | Gliedvolumen (dm³), fein auflösbar |
| Wachsende Wand | Feld fortschreiben | Punkte anhängen (trivial) |
| Selbstkollision | ungelöst → bedingtes Kapseltabellen-Paket | **gratis** im selben Schema |
| Abfragemenge | konstant klein (Arm-Punkte) | wächst mit Wandgröße → AABB-Breitphase + Top-K nötig |
| Advisor-Gradient | direkt in Weltkoordinaten | im Glied-System, einmal rückrechnen |
| Trifft den 53-%-`set_transform`-Posten (S5)? | indirekt | **direkt** — Hüllen-Verschieben entfällt komplett |

**Entscheidung (Grill 2026-07-12, Tobias):** PRD-#183-Arbeitspaket 1 wird auf
die Inversion umgeschrieben; das bedingte Selbstkollisions-Paket entfällt.
FCL bleibt exakter Nachprüfer im Grenzband, der Regressionsanker „identische
Befunde bei umgeschaltetem Backend" bleibt. Punktabstand der
Druckstand-Wolke deutlich unter dem Sicherheitsabstand (50 mm ⇒ ~15–20 mm
Raster ist konservativ genug; Shen: 2 mm bei 3 mm Marge — gleiche
Größenordnung des Verhältnisses).

## 3 cuRobo — geprüft und abgelehnt (mit Revisionstrigger)

**Quelle:** [cuRobo](https://curobo.org/) (NVIDIA, [arXiv 2310.17274](https://arxiv.org/abs/2310.17274)),
GPU-Bibliothek für Batch-IK + Kollision (~7000 kollisionsgeprüfte
IK-Abfragen/s, Planung ~30 ms auf RTX 4090).

**Ablehnungsgründe:** (1) harte CUDA-/NVIDIA-Abhängigkeit gegen das
„reproduzierbar auf jedem PC"-Versprechen (README/Bootstrap); (2)
GPU-Gleitkomma bricht die Byte-Gleichheit der Goldens und die
ADR-004-Byte-Vergleichbarkeit des Paper-Benchmarks — Ergebnis hinge vom
ausführenden Rechner ab; (3) der gemessene Engpass (53 % `set_transform`,
S5) ist durch die Glied-SDF-Inversion bereits adressiert, der Bedarf ist
unbewiesen. **Übernommen wird nur das Batch-Prinzip** (vektorisierte
numpy-Abfragen über Punktmengen statt Einzelaufrufe) als Anforderung an
Paket 1. **Revisionstrigger:** verfehlt die Glied-SDF-Prüf-Tür die
10-s-Marke (#144) auf CPU, wird ein GPU-Backend neu bewertet.

## 4 Zwei offene Lücken (Sekundärrecherche, Lücken-Charakter)

**Surrogat-Lernen für geometrisch-kinematische Druckbarkeit:** ML-Surrogate
für „Printability" existieren in der Prozess-/Materialdomäne
(Schmelzbad, Legierungen, FFF-Bauteileigenschaften — z. B.
[Sing et al.](https://www.sciencedirect.com/science/article/abs/pii/S1751616122003344),
[Rossoni et al.](https://link.springer.com/article/10.1007/s00170-022-09291-0)).
Für die Frage „ist dieser Wand-Abschnitt von diesem Standplatz
kollisionsfrei druckbar?" (geometrisch-kinematisch, Bau-Maßstab) hat die
Suche **keine Quelle** ergeben. Unsere Pipeline erzeugt die Trainingsdaten
(Kandidaten-Merkmale + exakte Prüf-Tür-Urteile) als Nebenprodukt jedes
Laufs — ein Datensatz, für den andere Gruppen Versuchsreihen bräuchten.
→ In #183 aufgenommen (Grill 2026-07-12): volles Arbeitspaket, v1 **nur
sortierend** (verwirft nie, unsichtbar für Ampel/Befunde), Kaltstart per
systematischer Datenkampagne (Batch über die exakte Prüf-Tür, Datensatz
als veröffentlichbares Paper-Artefakt). Benchmark bekommt den dritten Arm
Greedy vs. Beam vs. Beam+Surrogat.

**Umsetz-Sequenzierung:** Standplatz-Reihenfolge-Optimierung existiert als
TSP/SSP-Formulierung im Fräsen/Pick-and-Place (z. B.
[Robot Base Placement for Pick-and-Place Sequences, IFAC 2024](https://www.sciencedirect.com/science/article/pii/S2405896324014782),
TU-Wien-Projekt „Optimal TCP and Robot Base Placement"). Für Baudruck
(Abschnitts-Gruppierung auf gemeinsame Standplätze + Druckreihenfolge unter
der Schwerkraft-Ordnung „unten vor oben", gekoppelt an
Wieder-Einmess-Kosten #116) hat die Suche **keine Quelle** ergeben.
→ Entscheidung (Grill 2026-07-12): in #183 nur **Kriterium + Metrik**
(„Anzahl Standplätze" als Zielfunktions-Kandidat und Pflicht-Metrik);
die volle Sequenzierung wird ein eigenes Issue (Paper-3-Kandidat).

## 5 Auswirkungen auf PRD #183 (Kurzliste)

1. Neuheits-Claim umformuliert (Abschnitt 1), Shen et al. 2026 zitiert +
   abgegrenzt.
2. Arbeitspaket 1 invertiert: Glied-SDFs (offline, Artefakt mit Provenienz)
   + Druckstand-Punktwolke; Kapseltabellen-Paket entfällt; Batch-Prinzip
   als Anforderung; Mess-Spike umgewidmet zum Vorher/Nachher-Beleg.
3. GPU/cuRobo abgelehnt mit Revisionstrigger (Design-Log).
4. Neues Arbeitspaket Surrogat-Vorsortierer (nur sortierend) +
   Datenkampagne + Datensammel-Felder.
5. „Anzahl Standplätze" als Zielfunktions-Kandidat + Benchmark-Metrik;
   volle Sequenzierung als eigenes Issue ausgegliedert.

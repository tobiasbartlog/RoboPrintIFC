# Recherche II (vertiefend): Adaptierbare Techniken aus der Chunking-/Zerlegungs-Literatur

**Datum:** 2026-07-10
**Vorgänger:** [2026-07-10-stand-der-technik-kollisionsgetriebene-zerlegung.md](2026-07-10-stand-der-technik-kollisionsgetriebene-zerlegung.md)
**Frage:** Welche konkreten Algorithmen aus der Literatur können wir für unsere
kollisionsgetriebene Wandzerlegung adaptieren — und welche Optionen stehen zur Wahl?

**Verifikations-Status (ehrlich):** Der Deep-Research-Lauf hat 20 Quellen gelesen und
95 Behauptungen mit wörtlichen Volltext-Zitaten extrahiert; die anschließende
adversariale 3-Voter-Verifikation ist komplett am Session-Limit gescheitert
(0 von 25 geprüft). Alle Aussagen unten sind also **Extraktions-Niveau mit
Original-Zitat, nicht gegenverifiziert** — vor Übernahme in ein Paper die
jeweilige Primärquelle lesen. Formeln sind aus den Zitaten übernommen.

**Nachtrag 2026-07-10 (Volltext-Prüfung, abgeschlossen):** Alle Quellen bis auf
eine wurden beschafft (`docs/recherche/inputPDF/`, **18 PDFs**, Schema
`jahr-erstautor-kurztitel.pdf`) und je Quelle gegen den Volltext geprüft.
Ergebnis im Abschnitt
[Verifikation gegen die Volltexte](#verifikation-gegen-die-volltexte-2026-07-10).

Kurzbilanz: **drei Quellen waren falsch charakterisiert** (Dai, LayerLock,
Multi-Robot-Partitionierung), **zwei Zahlengruppen waren falsch attribuiert**
(sinusförmige Verzahnung → existiert unter der zitierten DOI nicht;
Fugen-Zugfestigkeiten → gehören Poudel, nicht McPherson). Die Kern-Formeln von
Stamatopoulos, Zacharias, Vahrenkamp, Wu, RM4D, B*, Han und Z-Chunking sind
wörtlich bestätigt. Dazu ein Querbefund, der die Paper-Skizze trägt: **keine
einzige Quelle prüft einen Armkörper gegen einen wachsenden Druckstand.**

Die Optionstexte oben bleiben als Extraktionsstand stehen (Korrekturen kommen
als neuer Eintrag, nicht als Umschrift); nachweislich falsche Zahlen sind dort
inline mit ⚠ markiert. **Verbindlich ist der Verifikationsabschnitt.**

---

## Einordnung: Wo unsere Pipeline heute steht

Zum Andocken der Optionen, unser Ist-Stand (Serie #141, Scheiben 1–3 umgesetzt):

- **Schnitte:** achsparallele, zerlegungsart-neutrale Schnittebenen (Abschnitt/Modul).
- **Stufe 1 (gratis):** Freigang-Kriterium `check_freigang` — druckbare Tiefe
  `D = L + R` vs. Wanddicke, stellt nur Unmöglichkeit fest (#163).
- **Stufe 2 (teuer):** verdünnte `find_collisions`-Prüf-Tür je Teil (FCL + VHACD,
  Druckstand als wachsendes Hindernis), repräsentativ je Höhenreihe (#162, #164).
- **Offen:** Verfeinerung entlang `causer_link` (#165), 100-%-Vorschlag (#166),
  Performance-Strategie `find_collisions` (#144), Fügegeometrie Modul (ADR-022: „folgt später").

---

## Option A — Analytische Schranken ausbauen (Winkel- statt nur Tiefen-Kriterium)

**Quelle der Idee:** Stamatopoulos et al. (ICRA 2024, [arXiv 2402.05853](https://arxiv.org/abs/2402.05853), frei;
Journal-Fassung [Springer JINT](https://link.springer.com/article/10.1007/s10846-024-02081-8), paywalled;
Nachfolger 2025 [arXiv 2502.20549](https://arxiv.org/html/2502.20549v1), frei) und
McPherson & Zhou ([Rapid Prototyping Journal, PDF frei via NSF](https://par.nsf.gov/servlets/purl/10209027)).

Beide leiten die **maximal zulässige Schnittneigung analytisch aus der
Werkzeuggeometrie** ab — strukturell exakt unser Freigang-Kriterium, nur als
Winkel- statt Tiefenbedingung:

- Stamatopoulos: `φ_max^extr ≤ arctan(h/l)` aus der Extruder-Bounding-Box
  (h Höhe, l Länge); kombiniert mit einer Verbindbarkeits-Schranke
  `φ_max^conn = 45°` (Faustregel: 50 % Schicht-Überlappung an der Fuge).
- McPherson & Zhou: `θ_max = arctan(nh/nd)` (Düsenhöhe/Düsentiefe),
  `θ_min = arctan(h/bd)` (Objekthöhe/Bautiefe); außerhalb kollidiert Düse
  bzw. Fahrwerk mit Gedrucktem.

**Adaption bei uns:**
1. *Klein:* Unser `D = L + R` um eine zweite analytische Schranke ergänzen, die
   nicht nur „Wand zu dick", sondern auch „Teil zu hoch für die verbleibende
   freie Länge" gratis erkennt (Höhen-/Tiefen-Kopplung, gleiche S6-Fehlerrichtung).
2. *Größer:* **Geneigte Schnittebenen zulassen** — heute schneiden wir nur
   achsparallel. Eine Winkel-Schranke aus Endeffektor-Geometrie würde geneigte
   Fugen ermöglichen (→ Option D), ohne die teure Prüf-Tür je Kandidat zu brauchen.

**Aufwand:** klein (1) bis mittel (2). **Nutzen:** Stufe 1 fängt mehr Fälle gratis;
Vorstufe für Option D.

## Option B — Beam-Search mit expliziter Zielfunktion über Schnitt-Kandidaten

**Quellen:** Wu et al. (IEEE T-ASE 2019, [arXiv 1812.00606](https://arxiv.org/abs/1812.00606), frei),
Stamatopoulos (s. o.), Han et al. (Micromachines 2025, [MDPI, frei](https://www.mdpi.com/2072-666X/16/12/1316)).

Die Literatur behandelt Zerlegung durchgehend als **Suche über diskrete
Schnittebenen-Kandidaten** mit billiger analytischer Bewertung; teure Prüfungen
kommen erst am Ende oder gar nicht:

- **Wu et al.:** Kandidaten = 250 Normalen auf der Gauß-Sphäre × 1-mm-Offsets
  (~15–20 k Ebenen); Hardware-Grenzen werden **direkt im Sampling kodiert**
  (Normalen auf `n·r = 0` beschränkt — unser Analogon: nur achsparallel + optional
  geneigt). Zielfunktion: Fläche „riskanter" Facetten
  `J_G = Σ e(f,π)·A(f)` mit `e` = 1 wenn `n_f·d_π + sin(α_max) < 0` (α_max = 45°).
  Beam-Search mit **progressiver Relaxation**: erst nur Kandidaten mit
  Rest-Risiko < δ zulassen, δ verfünffachen bis Beams voll; harte Constraints
  (Zusammenhang mit Plattform, Fragmentschutz `V ≥ V(M)/w`, w = 10–12) filtern vorab.
- **Stamatopoulos:** BSP-Baum + Beam-Search (`W_inner`/`W_outer` überleben je
  Iteration); Zielfunktion `h(T) = G_disp·c_v − Σ(G_part·s_k + G_faces·p_faces)` —
  bestraft ungleiche Teil-Volumina (Variationskoeffizient `c_v = σ/μ`), belohnt
  **Seed-Chunks** (Teile, die ohne Nachbar-Stützung druckbar sind). Gewichte im
  Experiment: 200/10/20. Druckreihenfolge wird **aus dem BSP-Baum geerbt** und
  nach z aufsteigend sortiert — exakt unser „unten→oben".
- **Han et al.:** Pareto-Mehrziel-Auswahl + Beam-Search, Fibonacci-Sampling
  (K = 1000 Richtungen); Metriken Support Reduction Rate / Support Ratio /
  Facet Coverage Rate; ø 6,4 s Rechenzeit (~88 % schneller als Wu).

**Adaption bei uns (konkret für #165/#166):** Die geplante Verfeinerung entlang
`causer_link` ist eine lokale Greedy-Strategie. Die Literatur-Alternative:
**Kandidaten-Schnitte generieren (Bandhöhen/Breiten-Raster), analytisch scoren
(Freigang + Volumen-Gleichmäßigkeit + Fugenfläche), Beam mit den besten k
Zerlegungen halten, und nur die Beam-Überlebenden durch die teure Prüf-Tür
schicken.** Unsere Prüf-Tür (~7–16 s/Teil) verbietet es, jeden Kandidaten zu
simulieren — genau dafür ist das Muster „billige Zielfunktion vorn, teures Urteil
hinten" gebaut. Die progressive Relaxation von Wu passt auf unseren Abbruchfall
(„Befund mit mindestens einem nachprüfbar freien 100-%-Vorschlag", #166): erst
strenge Kandidaten, bei Leere lockern.

**Aufwand:** mittel–groß. **Nutzen:** #166 bekommt ein prinzipiertes Suchgerüst
statt Heuristik; direkt paper-fähig (Vergleich Greedy vs. Beam, s. Teil „Paper").

## Option C — Reachability-/Inverse-Reachability-Maps für die Platzierung

**Quellen:** Zacharias et al. Capability Maps (IROS 2007, [Abstract](https://www.semanticscholar.org/paper/53271ecd9d1adde34ef6b674a771b9b90b07bebb), Paper via IEEE paywalled);
Vahrenkamp et al. Robot placement based on reachability inversion (ICRA 2013, [Abstract](https://www.semanticscholar.org/paper/bcc2e4700bc0ab4df0144167223f285c17892b22), IEEE paywalled);
**RM4D** (Rudorfer, [arXiv 2410.06968](https://arxiv.org/abs/2410.06968), frei, 2024);
**B\*** (RA-L 2025, [arXiv 2504.12719](https://arxiv.org/abs/2504.12719), frei);
Wu et al. nutzen eine Reachability-Map (Tool „Reuleaux") zur Extruder-Platzierung.

Kernidee: **einmal offline je Roboter** den Arbeitsraum vorberechnen, online je
Aufgabe nur noch abfragen:

- **Zacharias:** Arbeitsraum-Voxel mit „Reachability Spheres" (200 Punkte/Kugel,
  30°-z-Schritte, IK je Frame); Reachability-Index `D = R/N·100`. Aufbau damals
  12,4 h offline, Abfrage online billig. Explizit gedacht für Basis-Platzierung.
- **Vahrenkamp:** die Map **invertieren** (IRD) → an der Zielpose platziert liefert
  sie eine SE(2)-Verteilung guter Basisposen mit Qualitätsindex. Für Bahnen:
  `ORM_tr(x,y,γ) = min_i ORM_i(x,y,γ)` — **eine Basis-Pose, von der die ganze
  Trajektorie erreichbar ist, als punktweises Minimum**. Query-Zeiten < 10 ms.
- **RM4D (2024):** reduziert die Map auf 4D (p_z, θ, x*, y*) unter zwei Annahmen
  (endloses letztes Handgelenk in Approach-Richtung + endlose Basisachse), die
  OPW-Arme wie unser M1013 weitgehend erfüllen; **eine** Datenstruktur beantwortet
  vorwärts UND invers ohne separaten Inversionsschritt; ~67× kompakter als
  Zacharias-6D, 800 inverse Abfragen in 2,47 s; robust gegen verletzte Annahmen
  (−0,2 % Accuracy bei ±150°-Grenzen).
- **B\* (2025):** Gegenentwurf ohne Datenbank — Basis-Platzierung als
  Optimierung (progressive tightening + SLP), laut Autoren 5 Größenordnungen
  bessere Lösungsqualität als Sampling-Ansätze bei 100 % Erfolgsrate.

**Adaption bei uns:** Unser Platzierungs-Hebel (Optimalvorschlag/Bewertungsmodus,
`placement.evaluate`) und der Kollisions-Advisor rechnen heute je Kandidat eine
Simulation. Eine **einmalig vorberechnete M1013-RM4D** würde (a) den
Optimalvorschlag je Teil auf eine Map-Abfrage reduzieren (ms statt Sekunden),
(b) im Bewertungsmodus den „erreichbaren Wandanteil" ohne Simulation schätzen,
(c) als Kandidaten-Filter vor dem teuren Advisor dienen. Das `ORM_tr`-Minimum
über die Bahnposen einer Höhenreihe ist die saubere Verallgemeinerung unserer
„ungünstigste Zelle repräsentiert die Reihe"-Heuristik (#164) — statt einer
Zelle das Minimum über alle, bei gleicher Vorberechnungs-Logik. **Achtung:**
Maps kennen unseren wachsenden Druckstand nicht — sie filtern Reichweite/IK,
das Kollisions-Urteil bleibt bei der Prüf-Tür (Vahrenkamp adressiert das mit
Sampling proportional zum Map-Score statt argmax).

**Aufwand:** mittel (RM4D-Aufbau via bestehender OPW-IK + Voxelgitter ist gut
abgrenzbares tiefes Modul). **Nutzen:** hoch — beschleunigt Platzierung, Advisor
UND die Zerlegungs-Verfeinerung; zweites Alleinstellungsmerkmal fürs Paper
(reachability-getriebene Zerlegung wird messbar statt simulationsgetrieben).

## Option D — Fugen-/Interface-Geometrie (für ADR-022 „Fügegeometrie folgt später")

**Quellen:** McPherson & Zhou (s. o., frei); Procedia Manufacturing
([S2351978918307996](https://www.sciencedirect.com/science/article/pii/S2351978918307996), frei):
Zug-Versuche an Chunk-Fugen; Stamatopoulos 2025 (Staircase-Muster, frei);
Z-Chunking (Weber/Zhou/Sha, [PDF frei](https://sidilab.net/wp-content/uploads/2022/08/z-chunking-for-cooperative-3d-printing-of-large-and-tall-objects.pdf));
**Beton-Evidenz:** sinusförmige Verzahnung ([Materials 2024, MDPI frei](https://doi.org/10.3390/ma17246304)),
Kaltfugen-Studien ([RILEM Materials & Structures 2025](https://link.springer.com/article/10.1617/s11527-025-02723-9);
[3DCP-Wände unter Lateralbelastung, ScienceDirect **paywalled**](https://www.sciencedirect.com/science/article/abs/pii/S235271022502025X)).

Was die Literatur über Fugen zwischen nacheinander gedruckten Teilen sagt:

- **Geneigte Stoßflächen schlagen vertikale:** Der Druckkopf kann direkt auf die
  Fugenfläche deponieren → Verbund entsteht beim Drucken. Winkel ist ein
  Zielkonflikt: flacher = mehr Bondfläche/Festigkeit, steiler = größere Teile.
  Gemessen (FDM): 30°-Fuge ~doppelt so zugfest wie 50° (32,4 MPa, p ≈ 1e-5);
  richtige Parameter (Überlappung 0,5 mm) machen die Fuge z. T. **stärker als
  monolithisch** (121 %); Perimeter-Schalen an der Kontaktfläche vermeiden.
  > ⚠ **Fehlattribution.** Diese Messwerte stehen **nicht** bei McPherson &
  > Zhou (dort gibt es keinerlei mechanische Messung), sondern gehören zu
  > Poudel/Sha/Zhou, Procedia Manufacturing 26 (2018) 962–972. Das Paper ist
  > noch nicht beschafft — die Zahlen sind **ungeprüft**. Der *Zielkonflikt*
  > (flacher = mehr Bondfläche, steiler = größere Teile) ist bei McPherson
  > wörtlich belegt; die Begründung „Druckkopf deponiert direkt auf die
  > Fugenfläche" steht dort so nicht (er argumentiert nur über Bondfläche).
- **Verzahnung:** sinusförmige Nut-Feder-Geometrie im Betondruck: +213 %
  Zugfestigkeit quer zur Fuge, +45 % Druckfestigkeit, Zug-Anisotropie-Index
  2,29 → 0,16. Staircase-Verzahnung (Stamatopoulos 2025) löst das
  Dünnkeil-Problem geneigter Fugen beim Slicen. Z-Chunking nutzt Loch-Zapfen-
  „Assembly Geometries" (männlich oben/weiblich unten, 15 % Spiel) für
  stützfreien Druck in fester Orientierung.
  > ⚠ **Fehlzitat, nachgewiesen.** Der Satz zur sinusförmigen Verzahnung ist
  > **frei erfunden bzw. falsch attribuiert**: unter DOI 10.3390/ma17246304
  > (Materials 17/6304) steht Glotz et al., „Mechanical Behavior of Hardened
  > Printed Concrete and the Effect of Cold Joints" — Dreipunkt-Biegung, keine
  > Verzahnung. Die Wörter „sinusoidal", „interlock", „groove" kommen dort
  > **kein einziges Mal** vor; +213 %, +45 % und der Index 2,29 → 0,16
  > existieren nicht. **Nicht zitieren.** Details unten.
  > Die Staircase-Aussage ist ebenfalls zu präzisieren (Grobschicht-Artefakt,
  > Downwash-Motivation), die Z-Chunking-Aussage ist korrekt.
- **Kaltfugen im Beton sind der dominante Faktor:** In der Lateralbelastungs-
  Studie war die Kaltfuge kritischer als Axiallast oder Belastungsart
  (ohne Fuge: +100 % Tragfähigkeit, +207 % Energiedissipation). Die
  RILEM-Studie differenziert: 90-min-Pausen-Fugen steuern den Rissverlauf,
  zeigten aber **keine eindeutige Festigkeitsminderung** — und: nur ebene,
  horizontale Fugen wurden getestet, geneigte/verzahnte Geometrien sind
  **im Betonbereich unbeforscht** (Lücke!).

**Adaption bei uns:** Unsere Anschlussfuge (Abschnitt = Druckunterbrechung,
Modul v1 = ebene Stoßfuge) ist genau die Kaltfuge, die die Beton-Literatur als
kritisch markiert. Konkrete Stufen:
1. *Sofort (Befund):* Fugenfläche + Fugenlage je Zerlegungsplan als Kennzahl
   ausweisen (Slicer-Umriss × Schnittebene — die Daten liegen vor).
2. *Mittel:* geneigte Schnittebenen als Option (braucht Option A/Winkel-Schranke);
   Fugen-Neigung als Slice-/Zerlegungsparameter mit Literatur-Default ~30°.
3. *Größer:* Verzahnungs-Features (Sinus/Staircase) als Fugengeometrie der
   Zerlegungsart Modul — für Lehm materialseitig zu validieren (S-Spike).

**Aufwand:** 1 klein, 2 mittel, 3 groß + Materialversuche. **Nutzen:** ADR-022-
Lücke wird geschlossen; für Lehm ist das **unbeforschtes Terrain → eigener
Paper-Baustein** (geneigte/verzahnte Fugen im Lehmdruck gibt es in der
gefundenen Literatur nicht).

## Option E — Druckstand als Signed-Distance-Field (Performance-Schiene #144)

**Quelle:** INF-3DP ([arXiv 2509.05345](https://arxiv.org/pdf/2509.05345), frei, 2025).

Globale Kollisionen werden dort über ein **zeitvariables SDF des bereits
gedruckten Materials** erkannt (`φ_T(p,x) < 0` = Eindringen) — konzeptionell
identisch mit unserem Druckstand, aber implizit/differenzierbar statt
Mesh+VHACD. Berichtete Beschleunigung: bis zu zwei Größenordnungen gegenüber
mesh-/voxelbasierten Verfahren. S5 hat gezeigt, dass bei uns `set_transform`
auf den VHACD-Hüllen ~53 % der Zeit frisst — ein statisches Wand-SDF, gegen das
nur die (wenigen, konvexen) Arm-Glieder geprüft werden, würde genau diesen
Posten eliminieren. Roboterkinematik behandelt INF-3DP nur abstrakt
(Punktwolke, kein IK) — es ersetzt also nicht die Prüf-Tür, nur ihre
Abstands-Engine.

**Aufwand:** mittel (SDF-Voxelisierung des Druckstands + Punkt-Sampling der
Armglieder; FCL bleibt als exakter Nachprüfer). **Nutzen:** direkt auf #144
(10-s-Zielmarke) einzahlend; macht Option B (viele Kandidaten simulieren)
erst richtig bezahlbar.

## Option F — Billige Raster-Vorprüfung je Schnittkandidat

**Quelle:** Z-Chunking (frei, s. o.).

Interface-/Inselprüfung je Schnittebene dort **per Raycast-Raster (1 mm)**
statt exakter Geometrie — Laufzeit praktisch dichteunabhängig (0,53 s). Ihre
Ziel-Funktion `min Σ x_i·(y_i + k·z_i)` (Inseln + unplatzierbare Verbinder je
aktivem Schnitt, k ≫ 1) über Aktiv/Inaktiv-Bits der Kandidatenschnitte ist
brute-force 2^n (2,4 s bei 10, 988 s bei 25 Schnitten) — die Autoren empfehlen
Integer-Programmierung. Für uns relevant als Muster: **wenige diskrete
Kandidatenschnitte + billige Raster-Bewertung + exakte Prüfung nur am Ende** —
und als Warnung, die Kandidatenzahl klein zu halten oder ILP zu nutzen.

**Aufwand:** klein. **Nutzen:** unterstützend für Option B; bestätigt unser
Vorgehen „repräsentative Zelle statt Vollprüfung" methodisch (dort: Raster statt
exakt — Genauigkeit gegen Kosten, ehrlich gekennzeichnet).

---

## Options-Matrix (Vorschlag zur Auswahl)

| Option | Docken an | Aufwand | Nutzen | Paper-Relevanz |
|---|---|---|---|---|
| A Winkel-Schranken | #163 Freigang | klein–mittel | Stufe 1 fängt mehr gratis | Baseline-Methode im Vergleich |
| B Beam-Search + Zielfunktion | #165/#166 | mittel–groß | prinzipierte Suche statt Greedy | **Kern des Vergleichspapers** |
| C RM4D/IRM-Platzierung | Platzierung, Advisor, #164 | mittel | ms-Abfragen statt Simulationen | 2. Methoden-Baustein |
| D Fugen-Geometrie | ADR-022, Slicer | gestuft | Tragfähigkeit der Teile-Fugen | eigener Baustein (Lehm-Lücke!) |
| E Druckstand-SDF | #144 | mittel | Prüf-Tür ×10…100 schneller | Enabler für B |
| F Raster-Vorprüfung | #162/#164 | klein | billige Kandidaten-Triage | methodische Absicherung |

Empfohlene Reihenfolge, wenn das Paper das Ziel ist: **C → B → (E als Enabler) → D**;
A und F fallen unterwegs mit ab. C und B sind unabhängig startbar.

---

## Paper-Skizze: „Zerlegungs-Ansätze für IFC-Wandmodelle im Vergleich"

Die Literatur vergleicht Zerlegungen bisher nur auf generischen Meshes und ohne
Roboterkinematik (s. Recherche I). Ein Vergleichspaper auf **IFC-Wänden mit
echter Arm-Simulation als Schiedsrichter** wäre neu. Kandidaten-Verfahren:

1. **Manuelle Grundriss-Strategie** (Baseline, wie FAR 2024 sie beschreibt),
2. **analytische Schranken** (Freigang/Winkel, Option A),
3. **Greedy-Verfeinerung entlang causer_link** (unser #165),
4. **Beam-Search mit Zielfunktion** (Option B, Wu/Stamatopoulos-artig),
5. optional: **reachability-map-gestützt** (Option C als Filter).

Schiedsrichter für alle: unsere volle Kollisionssimulation (die keins der
Literaturverfahren hat). **Metrik-Katalog aus der Literatur** (alle Quellen oben):

- Teil-/Schnittanzahl; Volumen-Dispersion `c_v = σ/μ` (Stamatopoulos)
- serieller Volumenanteil / Amdahl-Speedup `r = V_c/V_t + (1/N)(1−V_c/V_t)` (McPherson)
- Fugenfläche gesamt + Fugenneigung (McPherson: Bondfläche vs. Effizienz)
- Überhang-/Risikofläche `J_G` (Wu); Support Ratio (Han)
- Rechenzeit der Zerlegung (Han: 6,4 s vs. Wu: 34–314 s — unsere Prüf-Tür-Zeiten passen in diese Achse)
- Erreichbarkeitsanteil + kinematische Marge (unsere Bestandsmetriken — in der Literatur so nicht vorhanden, **unser Beitrag**)
- geprüft-frei-Anteil vs. „vermutlich" (Ehrlichkeits-Metrik aus #164)
- mechanisch (falls Materialversuche): Fugen-Zugfestigkeit, Anisotropie-Indizes
  (⚠ der früher hier zitierte Index „2,29→0,16 (Materials 2024)" ist ein
  Fehlzitat, s. Verifikation. Belegte Anisotropie-Zahlen aus Glotz et al.:
  E-Modul XY 45–60 % höher als XZ; YZ bis 51,8 % niedriger)

Denkmal-Wand + 2–3 weitere IFC-Modelle als Benchmark-Satz; alle Verfahren
liefern `decompose.json`-kompatible Pläne → byte-vergleichbare Läufe (ADR-004-
Provenienz als Reproduzierbarkeits-Argument).

---

## Verifikation gegen die Volltexte (2026-07-10)

Grundlage: **18 PDFs** unter `docs/recherche/inputPDF/` (9 paywalled, von Tobias
beschafft; 9 frei, nachgeladen), je Quelle ein vollständiger Lesedurchgang gegen
die oben aufgestellten Behauptungen. Seitenangaben beziehen sich auf die
PDF-Seiten. Nur noch **eine** Quelle fehlt (Poudel et al., s. Beschaffung).

### Zentraler Querbefund: niemand prüft den Arm gegen den wachsenden Druckstand

Erst im Nebeneinander der Volltexte fällt auf, dass **alle** gelesenen
Zerlegungs-Verfahren die Kollision mit dem bereits gedruckten Material
*wegkonstruieren*, statt sie zu prüfen — und zwar jedes auf eigene Weise:

| Quelle | Wie Kollisionsfreiheit „sichergestellt" wird | Was NICHT geprüft wird |
|---|---|---|
| Wu 2019 | Halbraum-Clipping: Gedrucktes liegt stets unter der Basisebene (Werkstück rotiert) | Armkörper, Werkzeug-Schwenkvolumen |
| Dai 2018 | Konvexhüllen-Front; Kopf = „unendlich flacher Kopf" | Armglieder (erst später per IK), Konkavitäten |
| Stamatopoulos 2024/25 | Winkelschranke `φ_max^extr` zur Sampling-Zeit | Swept-Volume, Materialphysik |
| Han 2025 | Ungetrimmtes Vollschneiden; nur Plattform-Constraint | Kollision mit Gedrucktem (selbst als Future Work benannt) |
| LayerLock 2022 | Roboter = Punkt, Düse = Punkt, fester Aufstellabstand | Reichweite, Gelenkgrenzen, Selbstkollision |
| Zhao 2024 | Zeitliche Reihenfolge (Spiral-Strategie) zwischen Robotern | Wachsender Baukörper (kommt nicht vor) |
| McPherson 2018 | Analytische Winkelschranken; mobiler Drucker *fährt weg* | Erreichbarkeit, IK, Arm |
| Z-Chunking 2022 | Feste Z-Bauhöhen-Schranke des Druckers | Armkollision, wachsender Stand |
| INF-3DP 2025 | Echtes zeitvariables SDF — **prüft tatsächlich** | Armglieder + Basis + IK (Limitation 6.6.2) |

Der Grund ist meist derselbe: In der Literatur **rotiert das Werkstück** unter
einem festen Kopf (Wu, Dai, Han), oder der Drucker ist **mobil** (McPherson,
Z-Chunking, LayerLock), oder er **fliegt** (Stamatopoulos). Bei uns steht der
Arm fest, die Wand steht fest, und der Druckstand wächst dem Arm entgegen.
Genau dieser Fall zwingt zur echten Prüfung — und genau ihn deckt keine der
Quellen ab. INF-3DP kommt am nächsten (echtes zeitvariables SDF), prüft aber
ausdrücklich nur Extruder plus die letzten zwei Gelenke, ohne IK und ohne Basis.

**Konsequenz für die Paper-Skizze:** Unsere Prüf-Tür (#162/#164) ist damit kein
Implementierungsdetail, sondern das belastbarste Neuheitsargument. Der Satz
„die Literatur vergleicht Zerlegungen ohne Roboterkinematik" (Recherche I) ist
durch neun Volltexte gedeckt und kann so geschrieben werden.

Zweite Konsequenz, unbequem: Wus Zielfunktion `J_G` misst **Überhangfläche**,
weil sein Zweck Support-Vermeidung ist. Da eine Wand nicht umorientiert werden
kann, ist Überhang bei uns kaum die knappe Ressource — Erreichbarkeit ist es.
Wir können den Beam-Search-Rahmen übernehmen, **nicht aber die Zielfunktion**.

### Bestätigt (wörtlich, direkt verwendbar)

**Stamatopoulos et al. 2024** (`s10846-024-02081-8.pdf`) — alle sechs geprüften
Behauptungen bestätigt:

- `φ_max^extr ≤ arctan(h/l)` (Gl. 8, S. 6). Präzisierung: `h` = Düsenhöhe,
  `l` = Länge von der Düse bis zur **Außenkante des Extruderkopfs**, unter der
  Annahme, dass der Kopf durch ein Bounding-Rechteck genähert wird. Unser
  Optionstext oben („Länge des Extruders") ist ungenau.
- `φ_max^conn = 45°`, begründet mit der 50-%-Überlappungs-Faustregel (S. 6);
  die Autoren merken an, dass steilere Winkel bei mehr Bewegungsfreiheit des
  Extruders erreichbar sind — spricht für den 6-Achser gegenüber ihrem UAV.
- **Neu, im Optionstext oben nicht enthalten:** beide Schranken werden zur
  Sampling-Grenze kombiniert: `φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr)`
  (Gl. 9, S. 6). Das ist die Formel, die man tatsächlich implementiert.
- BSP-Baum + Beam-Search mit zwei Breiten (Algorithm 2, S. 4): `W_inner`
  überlebt je Baum-Erweiterung, `W_outer` je Suchiteration global.
- `h(T) = G_disp·c_v − Σ_k g(C_k)` mit `g(C_k) = G_part·s_k + G_faces·p^k_faces`
  (Gl. 6/7, S. 6), `c_v = σ/μ` (Gl. 1, S. 5). Gewichte 200/10/20 wörtlich (S. 10).
- Druckreihenfolge: DFS-Pre-Order über die Blätter, **dann werden die
  Schnittebenen** (nicht die Chunks) nach der z-Koordinate ihres Ursprungs
  neu sortiert und alle Schnitte erneut ausgeführt (S. 7).

**Wichtige Einordnung, die oben fehlt:** Das Paper ist ein **Aerial-3D-Printing-
Paper mit mehreren UAVs**, rein simulativ (Gazebo/RotorS), ohne festen Arm,
ohne IK, ohne Erreichbarkeit. Kollisionsschutz ist **ausschließlich** die
Winkelschranke Gl. 8 zur Sampling-Zeit — kein Swept-Volume-Check, und das
gedruckte Material wird **nicht** als wachsendes Hindernis modelliert
(„The behaviour and the physics of the deposited material are not taken into
account", S. 15). Unser Freigang-Kriterium #163 („Wand zu dick für einseitigen
Druck") hat dort **kein Pendant**. Fugengeometrie/Staircase-Verzahnung kommt
in dieser Fassung nicht vor (nur als Nachteil von 2.5D-Verfahren im Related Work).

**Zacharias et al. 2007** (`zachariasIROS2007.pdf`) — alle fünf Behauptungen
bestätigt: Voxel + eingeschriebene Reachability-Sphere (S. 4), 200 Punkte je
Kugel via Spiral-Point-Algorithmus, 30°-z-Schritte (S. 4/5), `D = R/N·100`
(Gl. 3, S. 4), 12,4 h offline (Tab. II, S. 8), Basisplatzierung explizit als
Anwendung (S. 3/7).

Drei Ergänzungen mit Konsequenz für Option C:
- Die 12,3 h Bauzeit entstehen durch die **Redundanz-Optimierung eines 7-DoF-
  Arms** (10⁶ Zufallssamples des Konfigurationsraums, S. 5). Der M1013 ist
  6-achsig und nicht redundant, hat geschlossene IK — man kann voxelweise
  direkt invers rechnen. **Der Kartenaufbau ist bei uns deutlich billiger, als
  die 12,4-h-Zahl oben suggeriert.**
- Die Karte **diskriminiert Singularitäten nicht** (S. 8) — für Bahntreue beim
  kartesischen Druck ggf. Manipulierbarkeit je Voxel als zweite Ampel führen.
- Der z-Roll um die TCP-Achse wird verworfen (S. 4). Für eine rotations-
  symmetrische Düse unschädlich.

**Vahrenkamp et al. 2013** (`Robot_placement_based_on_reachability_inversion.pdf`)
— alle vier Behauptungen bestätigt, zwei Präzisierungen:

- `ORM_tr(x,y,γ) = min{ORM_i(x,y,γ)}` ist wörtlich Gl. 3, S. 4. Das punktweise
  Minimum über die Bahnposen ist exakt unser „ein Standplatz, ganze Höhenreihe
  erreichbar".
- **Notation oben unsauber:** Die an der Zielpose platzierte IRD ist ein
  SE(3)-Volumen; erst der Schnitt mit der Bodenebene `F` ergibt die
  SE(2)-Verteilung, und die heißt **ORM**, nicht IRD (S. 3).
- **„<10 ms" gilt nicht durchgängig** (S. 5, Tab. I/II): das ist der Greif-Fall
  mit *Lazy* ORM (7,0 ms). Für Trajektorien 7–33 ms; mit voller ORM ~1,2 s Aufbau.
- Qualitätsindex je Voxel ist die *erweiterte Manipulierbarkeit* (Jacobi-
  Singulärwerte + Gelenklimits + Selbst-Abstand); **eine geschlossene Formel
  steht nicht im Paper**, sie ist nach Ref. [10] ausgelagert.
- Kollision: Algorithm 1 (S. 4) sampelt Basispose → löst IK → **prüft dann**
  Kollision, mit Retry bis Timeout. Die Warnung oben („Maps kennen unseren
  wachsenden Druckstand nicht") ist damit hart belegt. Auflösungs- und
  Speicherzahlen nennt das Paper **nicht** — die müssen wir selbst dimensionieren.

**3DCP-Kaltfugen-Studie** (`1-s2.0-S235271022502025X-main.pdf`) — Mercimek,
Şahin et al., „Structural performance of pre-fabricated 3D printed concrete
walls: Effect of cold joint, axial load and load type", *Journal of Building
Engineering* 112 (2025) 113788.

- „Kaltfuge kritischer als Axiallast und Belastungsart": bestätigt („the
  presence of cold joints was the most critical parameter", Abstract). Zum
  Vergleich: Axiallast 20→40 kN = +51 %, monoton vs. zyklisch ≈ +10 %.
- **Die Zahlen im Optionstext oben sind zitierfähig, aber das Paper
  widerspricht sich selbst.** Die +207 % Energiedissipation stimmen
  rechnerisch (1368,54 → 4200,34 kN·mm, zyklisches Paar bei 40 kN, Tab. 4);
  der Fließtext S. 13 nennt für dasselbe Zahlenpaar fälschlich +108 %. Die
  Tragfähigkeit erscheint als +100 % (Abstract), +115 % (S. 10) und −54 %
  (Fazit, invers). **Beim Zitieren: 207 % und ~115 % nehmen, den Widerspruch kennen.**
- Versuchsaufbau: fünf Wände 1800×1250×250 mm, Zementmörtel 44–47 MPa,
  Düse Ø 25 mm, Schichthöhe 20 mm. Kaltfuge durch **Druckpause alle 12 Lagen,
  Pausendauer 10–15 min** (S. 4). Versagen reproduzierbar in der 12. Lage:
  Toe-Crushing + Schub-Gleiten in der Fuge; ohne Fuge diagonale Schubrisse.
- **Geneigte oder verzahnte Fugen kommen nicht vor** — die Autoren nennen als
  Abhilfe nur Rheologie/Prozess und Bewehrung. Die Lücke aus Option D ist damit
  belegt, und zwar **auch für Beton**, nicht nur für Lehm.

### Korrigiert (oben falsch charakterisiert)

**Dai et al. 2018** (`SIG18RobotVolPrint.pdf`) — oben als „curved layers"
geführt. Das ist irreführend: gekrümmte Schichten sind nur das Zwischenprodukt.
Der Beitrag ist eine **Volumen-Zerlegung über ein Wachstumsfeld** (growing
field `G(x)`, Rang je Voxel), aus dem Isoflächen extrahiert werden.

Methodisch ist das die stärkste Stütze für unsere Zweistufigkeit, aber anders
als gedacht: **Kollisionsfreiheit wird nicht geprüft, sondern per Konstruktion
garantiert.** Brute-Force-Kollisionsprüfung verwerfen die Autoren explizit
(„can take up to 96 hours in total", S. 3). Stattdessen wird der Druckkopf
konservativ als „unendlich großer flacher Kopf" modelliert, womit die
zugängliche Fläche exakt die **Konvexhülle des bereits Gedruckten** ist
(S. 5); wer nur auf dieser Front deponiert, kollidiert nicht. Constraints:
ASN-Nachbarschaft `‖·‖₁ ∈ {1,2}` (S. 4), Zugänglichkeit, Shadow-Prevention.
Eine analytische **Winkelschranke gibt es nicht** — Support/Zugang sind rein
geometrisch-topologisch geregelt.

Zwei Vorbehalte für uns: Die Konvexhülle deckt nur den **Kopf** ab, nicht den
Armkörper — Dai prüft die reale Arm-/Umgebungskollision erst per IK auf
Pose-Ebene (S. 9). Und die Konvexitäts-Annahme ist konservativ: sie verwirft
legitime Freigänge in Konkavitäten, bei Wandöffnungen/Nischen also
überkonservativ. Nicht übernehmen: die „Werkstück rotiert unter fester Düse"-
Kinematik (UR5-spezifisch, für schwere Lehmwände ungeeignet).

Übertragbar bleibt die **Fugen-Bilanz** als Zielfunktion: Überdeckung
`H ≈ ∪ Π(S_i)`, Überlappungsfreiheit `Π(S_i) ∩ Π(S_j) = ∅`, und die
Dilatations-Stützbedingung (jede Schicht liegt in der Dilatation der
vorigen mit Radius r) — für nassen Lehm mit *kleinerem* r zu parametrisieren
als für PLA.

**LayerLock** (`1-s2.0-S0010448522001300-main.pdf`) — Krishnamurthy et al.,
„LayerLock: Layer-Wise Collision-Free Multi-Robot Additive Manufacturing Using
Topologically Interlocked Space-Filling Shapes", CAD 152 (2022). Oben unter
Option D als „Voronoi-/Verzahnungs-Zerlegung" geführt. **Das Paper zerlegt kein
Bauteil in Module.** Es teilt jede Druckschicht flächig zwischen **zwei
kooperierenden Robotern** auf (Zelle → nächstliegende Roboterbasis, S. 6);
die Verzahnung entsteht als *Nebenprodukt*, weil die Voronoi-Zellgrenze von
Schicht zu Schicht wandert („naturally leads to topological interlocking", S. 1).

Roboter sind dabei **Punkte** (Basisframe, S. 5), die Düse ein Punkt (S. 9);
Reichweite, Gelenkgrenzen und Arm-Selbstkollision sind **nicht modelliert**.
Der algorithmische Kern (Arbeitsteilung, moving fronts, I/N-Labeling) ist für
unseren einen 6-Achser gegenstandslos.

Verwertbar bleibt die **Fugen-Philosophie**: eine glatt gestufte, schichtweise
wandernde Trennfläche statt einer ebenen oder scharf gezahnten Fuge — die
Autoren grenzen sich explizit gegen beides ab (ebene Fugen „prone to failure
under transversal loading"; korrugierte Fugen „may induce high stresses at
sharp corners", S. 2). Und: kein Schlüssel, kein Verbinder, keine
Präzisionspassung nötig (S. 2) — das passt zu einem Material, das keine engen
Toleranzen hält.

Zwei harte Vorbehalte: Die Interlocking-Festigkeit ist an **steifem PLA**
argumentiert und setzt Formschluss voraus, den nasser Lehm nicht hat. Und
**quantitative Fugenfestigkeit misst das Paper überhaupt nicht** — der einzige
„Messwert" ist eine aufgehängte 35-lbs-Last (Fig. 15, S. 11), ohne Bruchlast,
ohne Norm; die Autoren erklären eine Festigkeitsanalyse ausdrücklich als
„not in the scope of this work" (S. 10).

**Multi-Robot-Partitionierung** (`1-s2.0-S0965997824001613-main.pdf`) — Zhao,
Yan et al., „Path planning in additive manufacturing with multi-robot
collaboration based on structural primitive partitioning", *Adv. Eng. Software*
197 (2024). Oben in Option B als Beleg für die Beam-Search-/Zielfunktions-Linie
mitgeführt. **Das trägt es nicht.**

Es ist DED-Lichtbogen-Drahtauftrag; die Zerlegung ist eine **2D-Scanline-
Partitionierung der Schnittkontur pro Schicht** (λ = 1 mm), ohne numerische
Zielfunktion, ohne ILP, ohne Beam-Search — ein deterministisches
Decompose-und-Merge-Verfahren. Erreichbarkeit ist ein **achsparalleles
Rechteck** je Roboter; Kollision wird **zeitlich** vermieden (Spiral-Strategie:
benachbarte Roboter drucken nie gleichzeitig benachbarte Bahnen), nicht
geometrisch geprüft. Den **wachsenden Baukörper als Hindernis kennt das Paper
nicht**. Rechenzeiten werden nirgends berichtet, nur Komplexität (O(m²) bzw.
O(n log n) für die KD-Baum-Sequenzierung).

**Konsequenz für Option B: die Beam-Search-Evidenz stützt sich allein auf Wu
und Stamatopoulos.** Aus Zhao et al. übernehmenswert sind drei Details: die
Scanline-Zerlegung als billiger Kandidatengenerator, die Regel „Bahn
überschreitet Arbeitsraum → splitten und neu zuweisen" (umgedeutet: „Modul
überschreitet erreichbare Höhe bei diesem Baustand → Schnitt setzen"), und für
den Metrik-Katalog die Flächentreue `η = S_all/S`, Modulzahl, Naht-/
Startpunktzahl und Leerweg.

### Abgrenzung geschärft

**García-Alvarado et al. 2024** (`1-s2.0-S2095263524000463-main.pdf`),
„From BIM model to 3D construction printing: A framework proposal",
*Frontiers of Architectural Research* 13 (2024) 912–927 — unser Abgrenzungs-
Paper Nr. 1. Es ist ein **konzeptioneller Workflow mit manuellem Grasshopper-
Prototyp für Beton**, kein automatisiertes System:

- **Kein IFC.** Live-Link Revit ↔ Rhino via Rhino.Inside.Revit. IFC-Schemata
  nennen die Autoren selbst als Future Work: „we envision a necessity to
  develop and implement IFC schemes" (S. 926).
- **Zerlegung händisch:** „drawing the maximum printing area … in the building
  layout" (S. 916); Ergebnis 15 Außen-/10 Innenwand-Segmente, 1,13–3,01 m.
  Erreichbarkeit nur als Faustregel (hemisphärischer Arbeitsraum, 1,6–2,2 m
  horizontal, 2,4 m Höhe, S. 916).
- **Kollision nur als Sichtprüfung** nach der Pfadgenerierung in Kuka|PRC:
  „visually inspect for collisions between parts" (S. 920). Ausgabe `.src`.
- **Keine Materialgradierung** — Beton mit Hohlkammern, kein φ-Feld.

**Für die Paper-Skizze heißt das:** Die Workflow-Idee „BIM-Wände segmentieren →
slicen → Roboterprogramm" ist belegter Stand der Technik und darf **nicht** als
neu beansprucht werden. Die Abgrenzung muss präzise auf *automatisiert/
solver-basiert vs. manuell* und *gradierter Lehm vs. Beton-Hohlwand* zielen.
Nebenbei bestätigt das Paper die „manuelle Grundriss-Strategie" als reale
Baseline (Verfahren 1 der Paper-Skizze) — sie tun exakt das.

**Kontovourkis & Tryfonos 2020** (`1-s2.0-S0926580519300718-main.pdf`),
„Robotic 3D clay printing of prefabricated non-conventional wall components
based on a parametric-integrated design", *Automation in Construction* 110
(2020) 103005 — der thematisch nächste Vorläufer, methodisch schwächer als
der Titel nahelegt:

- Eingang ist ein **handmodelliertes Rhino-BREP**, kein IFC (S. 6). BIM nur im
  Literaturteil.
- Die Wand (4×2 m) wird in **145 Einheiten** zerlegt — schlicht Höhenkurse;
  Kriterium ist der **Überhangwinkel** (5,01°–26,13°), nicht Kollision (S. 11).
- **Keine Armkollision, keine Erreichbarkeitsprüfung.** Nur eine 2-mm-Anhebung
  der Düsenspitze bei Leerfahrten (S. 7).
- **Fügung/Fugengeometrie kommt nicht vor.** Trocknung/Schwinden explizit
  ausgeklammert (S. 18). Mechanische Kennwerte fehlen.
- **Keine funktionale Gradierung** — nur hexagonales Infill mit *global*
  eingestellter Dichte je Bauteil, eine Mischung pro Bauteil.
- Roboter ABB IRB 2600 / RAPID via HAL bzw. TacoABB.

Ehrliche Überschneidung: Grundidee Roboter-Lehmdruck vorgefertigter Wand-
Bauteile, Contour-Slicing mit Offset-Wandlinien, Hex-Infill, und „Zerlegung
großer Wände in stapelbare Einheiten" an sich. Unser belastbares Delta:
IFC-Eingang, kollisions-/freigangsgetriebene Zerlegung mit Armsimulation,
Fügegeometrie, funktional gradierte Porosität, Dual-Emitter (DRL + KRL).

### Zweite Prüfrunde: die frei verfügbaren Quellen (nachgeladen 2026-07-10)

**Wu et al. 2019** (`2019-wu-support-effective-decomposition.pdf`) — alle sechs
Behauptungen bestätigt: 250 Gauß-Normalen × 1-mm-Offsets → 15–20 k Kandidaten
(S. 4); `n_k · r = 0` (S. 4); `J_G = Σ e(f,π)·A(f)` mit `e=1 ⟺ n_f·d + sin(α_max) < 0`,
α_max = 45° (Gl. 1/4, S. 3–4/8); progressive Relaxation (S. 6); Fragmentschutz
`V ≥ V(M)/w`, w = 10–12 (S. 6); Rechenzeit 34–314 s (Tab. I, S. 10).
Die Reuleaux-Reachability-Map wird tatsächlich benutzt — aber **einmalig zur
festen Extruder-Platzierung**, nicht als Constraint je Schnittkandidat (S. 8).

Präzisierungen: Das Relaxationssymbol heißt **ε**, nicht δ (ε = 0,1, dann
ε ← 5ε). Die **Beam-Breite `b` wird nirgends beziffert**. Und Wu prüft keine
Kollision gegen Gedrucktes — er garantiert sie weg (s. Querbefund oben):
„we do not explicitly prevent collision between the printer head and already
fabricated regions as the clipping routine … already guarantees this" (S. 4).
Fugengeometrie ist bei ihm **offenes Problem**: schwache Haftung an der
Grenzfläche, „how to design special structures at the interface … is one of our
future research questions" (S. 11).

**RM4D** (`2024-rudorfer-rm4d-reachability-map.pdf`) — alle sechs Behauptungen
bestätigt. 4D-Koordinaten `(p_z, α, x̃, ỹ)` (Gl. 2); die zwei Annahmen wörtlich;
eine Struktur für vorwärts und invers; 800 inverse Abfragen in 2,47 s; −0,2 %
Accuracy bei ±150°. Die „67×" stehen nicht im Text, folgen aber aus Tab. II
(114.307.200 / 1.714.608 = 66,7); das Paper selbst sagt „an order of magnitude".

Für uns günstig: **Der M1013 erfüllt beide Annahmen** (J1 ±360°; sphärisches
Handgelenk → J6-Achse fluchtet mit dem Approach-Vektor) und liegt damit näher
am Ideal als der im Paper geprüfte Franka (±166°, verletzt beide, −0,2 %).
Code offen (`mrudorfer.github.io/rm4d/`), Python + pyBullet.

Zwei Präzisierungen gegenüber dem Optionstext: Die Karte ist **pro Abfrage
binär**; ein Qualitätsindex entsteht erst durch **Aggregation** über viele
Zielposen (anders als Zacharias' `D`, das im Voxel steht). Und das
Trajektorien-Minimum ist gedeckt: „We then use the minimum value across all
four grids, to ensure that all objects are graspable from the suggested
positions" (IV-D) — der Schritt von „min über Objekt-Gitter" zu „min über
Bahnposen" ist eine kleine Extrapolation. Auflösung im Paper: 5 cm, 5°.
Keine Hindernisse, keine Singularitäten, keine Manipulierbarkeit — beides
ausdrücklich Future Work.

**B\* 2025** (`2025-zhao-bstar-base-placement.pdf`) — alle vier Behauptungen
bestätigt, aber **im Optionstext deutlich unterschätzt**. B* ist kein
Nebenkandidat, sondern der erklärte **Gegenentwurf** zu Reachability-Maps.
Zacharias, Vahrenkamp und RM4D werden namentlich als „pre-computed database"-
Ansatz kritisiert: sie „could verify point-wise reachability, [but] could not
guarantee the feasibility of continuous trajectories between reachable points"
(S. 3).

Und genau das ist unser Fall. B* optimiert **eine** feste Basis
`q_b = [x_b, y_b, θ_b]ᵀ ∈ SE(2)` für eine **geordnete Sequenz** von t
Endeffektor-Posen (Gl. 1), mit Erreichbarkeit als Gleichheits-Constraint
`FK(q_b, q^m_i) = x_i` (Gl. 5) und Kollision als Signed-Distance-Ungleichung
`sd(q_b, q^m_i) ≥ 0` (Gl. 8) — beides in **einer** Optimierung. Getestet mit
64 Posen, 6-DoF (UR10) inklusive; 2400 Testfälle, 100 % Erfolg; ~3,1 s bei
64 Posen. Code/Daten: `bstar-planning.github.io`.

Präzisierung: Die „5 Größenordnungen" sind **kein** generisches Qualitätsmaß,
sondern die Präzision der Basis-Pose (Absolute Trajectory Error, mm),
begrenzt durch die Gitterauflösung der Sampling-Verfahren (Fig. 4, S. 6).
Einschränkungen: Hindernisse sind **statisch** (dynamische = Future Work);
zufällige Initialisierung kann bei stark eingeschränkten Szenen scheitern
(bis ~2 Retries im Mittel); Solver ist das kommerzielle COPT.

**INF-3DP 2025** (`2025-qu-inf3dp-implicit-neural-fields.pdf`) — Behauptung 1
und 3 bestätigt (`φ_T(p,x) < 0` als Kollisionskriterium, Eq. 6; Kinematik nur
Extruder + letzte zwei Gelenke, ohne IK, ohne Basis — Limitation 6.6.2, S. 16).
Behauptung 2 zu präzisieren: „up to two orders of magnitude" ist ein
**Bis-zu-Wert für die Gesamtpipeline**; die belastbaren Einzelmessungen sind
**20×** (gegen Neural-Slicer: 1,46 s vs. 29,4 s) und **64×** (826,4 s vs. 12,9 s
gegen den mesh-basierten S3-Slicer).

**Der für uns entscheidende Befund steht im Optionstext nicht:** Das
zeitvariable SDF wird **nicht neu trainiert**. Es entsteht „training-free" per
Feld-Interpolation aus dem statischen End-SDF und einem skalaren Sequenzfeld
(S. 9, Eq. 26, Algorithm 1). Der wachsende Druckstand braucht also kein
mitwachsendes Feld. Und pro Wegpunkt wird **nur die Werkzeug-Punktwolke
transformiert**, das Objekt nie — strukturell exakt der Hebel gegen unseren
`set_transform`-Posten (S5: ~53 % der Zeit auf den VHACD-Hüllen).

**Aber: das Paper belegt kein Argument für ein *neuronales* Feld.** Für eine
diskrete Kollisionsabfrage braucht man nur `sign(φ(x))`; ein klassisches
**Voxel-SDF mit Trilinear-Interpolation leistet dasselbe** — ohne 229–731 s
SDF-Training (Tab. 2, S. 13). Das Neuronale zahlt sich nur bei der
differenzierbaren Bewegungsoptimierung aus (Gradient von φ, Eq. 28/29), die
wir nicht fahren. **Empfehlung für Option E: Voxel-SDF, nicht neuronal.**
SDF-Genauigkeit bleibt die Sicherheitsgrenze (Fitting-Fehler 2,5e-4 normiert)
→ konservative Iso-Fläche oder exakter Nachprüfer an Grenzfällen.

**Han et al. 2025** (`2025-han-support-free-model-decomposition.pdf`) — alle
vier Behauptungen bestätigt. Pareto-Front + Beam-Search (Beam-Breite **b = 15**,
S. 11); Fibonacci-Sampling K = 1000 (S. 5); die drei Metriken mit Formeln
(16)–(18); 6,4 s vs. Wu ~56 s → 88 % (S. 12).

Fairness des Vergleichs: **ja** — gleiche Hardware (i5-13400F), gleiche drei
Modelle, Wu auf demselben PC nachgerechnet. Drei Vorbehalte: verglichen wird
nur gegen Wus *beschleunigte* Variante; über alle sechs Modelle liegt Hans
Schnitt bei ~5,9 s statt 6,4 s (die 6,4 s sind exakt die Vergleichs-Teilmenge);
Parametrisierung von Wus Code (OpenMP, Flags) ist nicht dokumentiert.

Wichtig: Kandidaten sind **Richtungen × Offsets** (Δl = 1 mm), nicht nur
Richtungen. Kollision mit Gedrucktem wird durch **ungetrimmtes Vollschneiden**
umgangen und von den Autoren selbst als Lücke benannt (S. 14). Fugengeometrie:
nichts. Übernehmenswert ist die **Masken-/Matrixformulierung** (Gl. 6–9) —
der eigentliche Grund für die kurzen Laufzeiten — und die progressive
Relaxation des Support-Ratio, wenn „null Support" unerreichbar ist.

**McPherson & Zhou 2018** (`2018-mcpherson-chunk-based-slicer.pdf`) —
`θ_max = arctan(nh/nd)` (Gl. 1) und `θ_min = arctan(h/bd)` (Gl. 2) wörtlich
bestätigt, ebenso das Amdahl-Modell (der serielle Anteil ist konkret das
**Volumen des Mittel-Chunks**, Gl. 6–9) und der Zielkonflikt flacher/steiler.

Zwei Korrekturen: (1) `θ_min` modelliert die Kollision der **Vorderräder eines
fahrenden Druckers** — „build depth" ist definiert als „the distance between
the printhead and the front wheels". Für einen **stationären Arm existiert
dieses Kollisionsobjekt nicht**; die Schranke ist nicht übertragbar und müsste
durch eine Reichweiten-/IK-Bedingung ersetzt werden. `θ_max` (Düse vs.
Gedrucktes) ist dagegen übertragbar. (2) **Dieses Paper enthält keinerlei
mechanische Messwerte** — die Fugen-Zugfestigkeiten im Optionstext gehören zu
Poudel et al. (s. Fehlattribution oben). Weiterhin bricht die Annahme
zweiseitiger Symmetrie (Center-Chunk + L/R, zwei Roboter): bei einseitigem
Wandzugang müssen alle Schrägebenen so orientiert sein, dass die zugängliche
Seite frei bleibt. Amdahl setzt N > 1 Drucker voraus — bei einem Arm kein
Speedup-Argument, der Nutzen geneigter Fugen ist rein Bond/Freigang.

**Z-Chunking** (`2022-weber-z-chunking.pdf`) — alle fünf Behauptungen
bestätigt: 1-mm-Raycast-Raster statt exakter Geometrie, dichteunabhängig
0,53 s (Tab. 3, S. 15); Zielfunktion `min Σ xᵢ(yᵢ + k·zᵢ)` mit xᵢ = Aktiv-Bit,
yᵢ = Inselzahl, zᵢ = Inseln ohne platzierbare Assembly-Geometry, k ≫ 1 (S. 9);
Brute-force 2,43 s / 29,16 s / 988,12 s bei 10/20/25 Schnitten, ILP empfohlen;
Loch-Zapfen-AG mit 15 % Spiel (S. 11–12).

Für uns entscheidend und im Optionstext nicht erwähnt: Die Teile werden
**getrennt gedruckt und nachträglich gesteckt** („we must instead print the
Z-Chunks separately and assemble them … also an assembly problem", S. 3), mit
Nachbearbeitung an der Fuge. Die 15 % Spiel sind empirisch aus FFF-Druck-
versuchen, nicht berechnet. **Mechanische Messwerte zur Z-Fuge: keine.**
Damit ist die gesamte Fügetechnik für nassen Lehm gegenstandslos; übernehmbar
ist die **Suchmechanik** (Raycast-Inselkarte + Bit-Optimierung unter
Minimalschnitt-Constraint `Σxᵢ ≥ ⌈H/Z_limit⌉`), wobei die feste Z-Schranke
durch unser reichweiten-/kollisionsgetriebenes Limit zu ersetzen ist.

**Stamatopoulos 2025** (`2025-stamatopoulos-aerial-chunking-experimental.pdf`)
— die Staircase-Verzahnung existiert und heißt **„Chunks Interlocking
Mechanism"**; das Muster wird wörtlich „stair-case pattern" genannt (Abschn. 7,
S. 21–23). Algorithmus: vertikale Schnitte im Schichthöhen-Raster, die
geneigten Restzonen werden dem **unteren** Chunk zugeschlagen.

Unsere Behauptung ist aber zu präzisieren. Das „Dünnkeil-Problem" ist dort ein
**Grobschicht-Artefakt**: „the layer height is comparable to the overall
dimensions of the chunks (not a usual phenomenon in conventional 3D printing)"
— im Experiment 2,5 bzw. 4,5 cm Schichthöhe. Und die *primäre* Motivation ist
Haftung gegen **Downwash-Verrutschen** der Drohnen-Propeller, nicht das
Slicing. Beides trägt für feine Lehmschichten ohne Abwind nicht.
**Keine Festigkeitsmesswerte** — rein qualitative Demonstration (Fig. 7/8).
Es gibt **keine Parameter** für Stufenhöhe/-tiefe/-winkel: die Stufenhöhe *ist*
die Schichthöhe. Für Lehm hieße das sehr viele winzige Stufen; sinnvoll wäre
eine bewusst parametrisierte Verzahnung über n Schichten — das ist ein
Entwurfsentscheid für ADR-022, kein Literaturzitat.

Ferner: Zerlegungskern identisch zur Journal-Fassung (BSP + Beam-Search,
`c_v = σ/μ`; hier inner beam = outer beam = 10). Neu sind physische Experimente
(Hexacopter, Polyurethan-Schaum, Genauigkeit ~2,1 cm), ein Dependency-Graph und
Offset-Free NMPC. `φ_max^extr = arctan(·)` erscheint wieder (S. 11);
`φ_max^conn = 45°` **nicht mehr als hergeleitete Schranke**, sondern nur als
experimenteller Sampling-Cap θ_max = 45° (S. 34). Die Herleitung steht in der
2024er Fassung.

**Glotz et al. 2024** (`2024-glotz-printed-concrete-cold-joints.pdf`) —
**Fehlzitat nachgewiesen**, s. Markierung in Option D. Das Paper untersucht
Dreipunkt-Biegung an Proben, die aus einer **geraden** gedruckten Wand gesägt
wurden; Kaltfuge durch **90-min-Pause** auf halber Höhe. Keine Verzahnung,
keine Druckfestigkeitsprüfung, kein Anisotropie-Index.

Belegte Zahlen (Tab. 3/4): E-Modul XZ 17.573 / XY 24.107 / YZ 11.613 MPa;
Biegezugfestigkeit XZ 5,20 / XY 5,80 / YZ 3,59 MPa (p = 0,0033). YZ-E-Modul
bis 51,8 % niedriger; XY-E-Modul 45–60 % höher als XZ — **das dürfte die Quelle
der verwechselten „+45 %" sein**.

Bemerkenswert und scheinbar im Widerspruch zu Mercimek: „the commonly reported
inferior mechanical performance due to CJ does not manifest clearly in this
study" (S. 13). Die Autoren führen es auf das höhere Prüfalter der
Kaltfugen-Proben zurück (148 vs. 34 Tage). **Für uns heißt das: die
Kaltfugen-Schwächung ist keine Naturkonstante, sondern hängt an Pausendauer,
Prüfalter und Belastungsart.** Mercimek (10–15 min Pause, Lateralbelastung,
Schub-Gleiten) und Glotz (90 min Pause, Biegung, kein klarer Effekt) messen
verschiedene Dinge. Vor jeder Übertragung auf Lehm ist das zu klären.

### Was die Verifikation an der Options-Matrix ändert

| Option | Status nach Volltext-Prüfung (alle 18 Quellen) |
|---|---|
| A Winkel-Schranken | **gestärkt.** Formeln bestätigt, dazu Gl. 9 (`φ_max^sample`) als eigentliche Implementierungsformel. McPhersons `θ_max` übertragbar, `θ_min` **nicht** (Fahrwerksparameter). |
| B Beam-Search | **wieder tragfähig, aber Zielfunktion offen.** Wu vollständig bestätigt (ε-Relaxation, `V ≥ V(M)/w`), Han liefert eine 9× schnellere Pareto+Beam-Variante (b = 15). Zhao et al. trägt sie nicht. **`J_G` misst Überhang — bei uns die falsche Größe** (Wand nicht drehbar). Rahmen übernehmen, Zielfunktion neu bauen (Erreichbarkeit statt Support). |
| C Platzierung | **gestärkt und aufgespalten.** Zwei konkurrierende Ansätze: (C1) Karte + Prüf-Tür (Zacharias/Vahrenkamp/**RM4D**, M1013 erfüllt beide RM4D-Annahmen, Code offen) vs. (C2) **B\*** — Optimierung ohne Karte, behandelt Erreichbarkeit + Kollision für eine ganze Posensequenz in einem Lauf, ~3,1 s bei 64 Posen. B* kritisiert C1 namentlich als nur punktweise. **Entscheidung nötig.** |
| D Fugen-Geometrie | **Evidenz kollabiert.** Die Verzahnungs-Zahlen waren ein Fehlzitat (Glotz ≠ sinusförmige Verzahnung). LayerLock, Z-Chunking und Stamatopoulos 2025 messen **alle keine** Fugenfestigkeit. Die einzigen echten Messwerte (Poudel) sind noch unbeschafft. Für Lehm: unbeforscht, wie vermutet — aber jetzt belegt statt behauptet. |
| E Druckstand-SDF | **gestärkt, Empfehlung geändert.** INF-3DP belegt den Hebel (nur Werkzeug transformieren, Objekt nie) und dass das zeitvariable SDF **training-free** aus statischem SDF + Sequenzfeld entsteht. **Kein neuronales Feld nötig — Voxel-SDF genügt.** |
| F Raster-Vorprüfung | **gestärkt.** Z-Chunkings 1-mm-Raycast ist dichteunabhängig (0,53 s); Dai verwirft Brute-Force-Kollision explizit (96 h). Gleiches Muster, zwei unabhängige Quellen. |

---

## Ist-Zustand → Optimierungspotenzial (Code ↔ Literatur, 2026-07-10)

Ziel dieses Abschnitts: je Problem nachvollziehbar machen, **wie wir es heute
lösen** (mit Code-Stelle), **was die Literatur besser macht** (verifizierte
Quelle) und **was konkret bei uns anzufassen wäre**. Fugen (Option D) sind
bewusst ausgeklammert — Priorität liegt auf dem Tool (Bahnplanung, Zerlegung,
Platzierung, Prüfgeschwindigkeit); Fugen bleiben als späterer Paper-Baustein.

### P1 — Kollisionsprüfung gegen den Druckstand (die Prüf-Tür)

**Heute:** `find_collisions` (`core/src/fgc/collision/check.py:260`) prüft je
Trajektorien-Sample die Arm-Glieder gegen den Druckstand: AABB-Breitphase
(`check.py:191/203`), bei Nähe exakte FCL-Distanz auf VHACD-Urteilsgeometrie
(`robot_geometry.py:81`, `min_distance_other` `check.py:369`). Jedes nahe Glied
wird per `set_transform` in den FCL-Manager gesetzt (`_set_parts`
`check.py:214`, Aufrufe `check.py:368` Arm↔Hindernis und `check.py:382`
Selbstkollision). **Gemessen (Spike S5):** `set_transform` = 5,03 s = 52,8 %
der Laufzeit, 1 566 305 Aufrufe; Prüf-Tür ~7–16 s je Teil; Zielmarke #144: 10 s.

**Literatur:** INF-3DP (verifiziert, s. o.) transformiert **nie das Objekt**,
nur die Werkzeug-Punkte, und fragt ein statisches Feld ab — 20–64× gemessen.
Der wachsende Druckstand braucht **kein** mitwachsendes Feld: statisches
End-SDF + skalares Fortschrittsfeld, training-free kombiniert (Eq. 26,
Algorithm 1). Für die reine Vorzeichen-/Distanzabfrage genügt ein
**Voxel-SDF** — das neuronale Feld lohnt nur bei differenzierbarer
Bewegungsoptimierung, die wir nicht fahren.

**Bei uns anzufassen:** Die Naht existiert schon — Hindernisse sind hinter
`obstacle_provider: Callable[[int], ObstacleSet]` gekapselt (`check.py:265`,
Aufbau `druckstand.py:199`). Ein `SdfObstacleSet` dockt als paralleler Provider
an: Glied-Hüllpunkte transformieren, `sdf(p)` lesen statt
`set_transform` + `min_distance_other`; der SDF-Gradient ersetzt zugleich den
Freizonen-Nächstpunkt (`_in_freizone` `check.py:401`). Da der Stand monoton
wächst, wird das SDF je Schicht fortgeschrieben statt neu gebaut. FCL bleibt
exakter Nachprüfer an Grenzfällen; Iso-Fläche konservativ nach innen versetzen.

**Vorbehalt (vor Umsetzung messen):** Die **Selbstkollision**
(`check.py:378-386`) profitiert nicht vom Druckstand-SDF und behält ihre
`set_transform`-Aufrufe. Der S5-Spike trennt die 52,8 % nicht nach Aufrufort.
Dominiert Arm↔Arm, ist der echte Hebel eine Kapsel-/Vorabtabelle für
Selbstkollision, nicht das SDF.

### P2 — Zerlegung: Kandidatensuche statt parametrischem Raster

**Heute:** `propose` (`core/src/fgc/decompose/propose.py:279`) teilt die Wand
**parametrisch**: `_grid_counts` (`propose.py:102`) startet aus dem
Arbeitsraum und verfeinert greedy entlang der blockierenden Achse
(`propose.py:152`); Schnitte sind gleichmäßige Teilungen + optionaler Versatz
(`_build_cuts` `propose.py:269`). Es gibt **keine Suche über
Schnitt-Kandidaten**; #165 plant eine lokale Greedy-Verfeinerung entlang
`causer_link`.

**Literatur (alle verifiziert):** Wu 2019 liefert das Suchgerüst — Kandidaten
= Normalen × 1-mm-Offsets, billige Zielfunktion, Beam-Search mit progressiver
ε-Relaxation (ε ← 5ε), harte Vorabfilter (Zusammenhang, Fragmentschutz
`V ≥ V(M)/w`). Han 2025 zeigt die schnelle Implementierung: Masken-/
Matrixformulierung (Gl. 6–9), Pareto-Front + Beam b = 15, 6,4 s. Z-Chunking
liefert die billige Interface-Bewertung: 1-mm-Raycast-Inselkarte,
dichteunabhängig 0,53 s, Bit-Optimierung mit Minimalschnitt-Constraint.

**Aber:** Wus Zielfunktion `J_G` misst **Überhangfläche** — sein Zweck ist
Support-Vermeidung bei rotierbarem Werkstück. Unsere Wand ist nicht drehbar;
knapp ist **Erreichbarkeit**, nicht Überhang. Der Rahmen ist übernehmbar, die
Zielfunktion muss neu: erreichbarer Wandanteil + kinematische Marge +
Volumen-Gleichmäßigkeit `c_v` (Stamatopoulos) + Fugenfläche als Kennzahl.
Muster durchgängig: **billige analytische Bewertung vorn, Prüf-Tür nur für
Beam-Überlebende hinten** — bei 7–16 s je Prüfung ist alles andere unbezahlbar.

### P3 — Platzierung: Karte oder Optimierung statt Simulation je Kandidat

**Heute:** `placement.evaluate` (`core/src/fgc/placement/evaluate.py:220`)
rastert die Wandfläche und rechnet **je Rasterpunkt eine IK** (analytische OPW
vorhanden: `opw.py:220`); der Kollisions-Advisor (`collision/advisor.py:343`)
rechnet je Gegenmaßnahmen-Kandidat eine `CollisionMetric` — Kosten wachsen
linear mit Kandidatenzahl × Simulationszeit.

**Literatur (verifiziert):** Zwei konkurrierende Wege.
**(C1) RM4D:** einmalige 4D-Karte, eine Struktur für vorwärts + invers, Code
offen (Python/pyBullet), der **M1013 erfüllt beide Annahmen** (J1 ±360°,
sphärisches Handgelenk). Standplatz für eine ganze Höhenreihe = punktweises
Minimum über die Bahnposen (Vahrenkamp Gl. 3; RM4D demonstriert dasselbe
Minimum über Gitter). Grenzen: binär, keine Hindernisse, keine
Manipulierbarkeit — reiner **Vorfilter**, das Urteil bleibt bei der Prüf-Tür.
**(C2) B\*:** eine Optimierung löst Erreichbarkeit (FK-Gleichheit) und
Kollision (Signed Distance) für die **ganze Posensequenz** gleichzeitig,
~3,1 s bei 64 Posen, 6-DoF getestet. Grenzen: Hindernisse statisch,
kommerzieller COPT-Solver, Initialisierung kann in engen Szenen scheitern.

**Bei uns anzufassen:** C1 zuerst — die Karte ersetzt das Raster×IK-Rechnen in
`evaluate` durch Kartenabfragen und filtert Advisor-Kandidaten vor. C2 wird
attraktiver, **nachdem** P1 steht: das Voxel-SDF ist genau die
`sd(·)`-Hindernisgeometrie, die B* braucht. Entscheidung C1 vs. C2 nach P1
grillen.

### P4 — Stufe-1-Gratisprüfungen ausbauen

**Heute:** genau eine analytische Schranke: `D = L + R` gegen die Wanddicke
(`freigang.py:70/126`) — stellt nur „zu dick" fest.

**Literatur (verifiziert):** Stamatopoulos leitet `φ_max^extr ≤ arctan(h/l)`
aus der Extruderkopf-Bounding-Box her und kombiniert per
`φ_max^sample = π/2 − min(φ_max^conn, φ_max^extr)` (Gl. 9 — die eigentliche
Implementierungsformel). McPhersons `θ_max = arctan(nh/nd)` (Düse vs.
Gedrucktes) ist übertragbar; sein `θ_min` **nicht** (Fahrwerksparameter).

**Bei uns anzufassen:** zweite Gratisschranke in `check_freigang`: „Teil zu
hoch für die verbleibende freie Länge" (Höhen-/Tiefen-Kopplung, gleiche
S6-Fehlerrichtung „unmöglich nur wenn sicher"). Winkelschranken werden
relevant, sobald geneigte Schnitte erwogen werden — heute schneiden wir nur
achsparallel.

### P5 — Sequenzierung (klein)

**Heute:** Druckreihenfolge unten→oben implizit aus der Zerlegung.
**Literatur:** Stamatopoulos erbt die Reihenfolge aus dem BSP-Baum und
sortiert die Schnitte nach z; Z-Chunking minimiert Leerwege per KD-Baum
(O(n log n)). Beides billig; relevant erst, wenn P2 mehrere gültige
Zerlegungen liefert, die sich in Leerweg/Reihenfolge unterscheiden.

---

## Roadmap: Tool zuerst, Paper daraus

Reihenfolge nach Abhängigkeit und Risiko; jeder Schritt einzeln lieferbar.

### Schritt 0 — Messung vor Design (Stunden)

S5-Nachmessung: `set_transform`-Aufrufe nach Aufrufort trennen
(`check.py:368` Arm↔Hindernis vs. `check.py:382` Arm↔Arm); Skript-Basis
liegt in `docs/spikes/s5_scripts/s5_cprofile.py`. **Entscheidet den Umfang
von Schritt 1.** Dominiert Selbstkollision, kommt Schritt 1b vor.

### Schritt 1 — Voxel-SDF-Provider für den Druckstand (Option E, Issue #144)

Der Enabler für alles Weitere. `SdfObstacleSet` als paralleler
`obstacle_provider`; Punktabfrage statt FCL-Distanz; Gradient für den
Freizonen-Nächstpunkt; fortschreibendes Feld je Schicht; FCL als Nachprüfer.
**Akzeptanz:** identische Befunde auf `test_prueftuer_denkmal.py` (Regressions-
anker), Prüf-Tür je Teil deutlich unter der 10-s-Marke. Aufwand: Tage.
*(1b, bedingt: Kapsel-Distanztabelle für Selbstkollision, falls Schritt 0 sie
als dominant ausweist.)*

### Schritt 2 — Winkel-/Höhenschranke in Stufe 1 (Option A)

Kleiner, unabhängiger Schritt: zweite Gratisschranke in `check_freigang`
(Gl. 9-Muster). Fängt mehr Fälle ohne Simulation; direkt Baseline-Methode 2
des Papers. Aufwand: klein. Kann parallel zu Schritt 1 laufen.

### Schritt 3 — RM4D-Karte für den M1013 (Option C1)

Offline-Karte bauen (offener Code, pyBullet; Auflösung feiner als 5 cm/5°
prüfen), dann: (a) `placement.evaluate` auf Kartenabfrage umstellen,
(b) Standplatz je Höhenreihe als Minimum über Bahnposen, (c) Advisor-
Kandidaten vorfiltern. Prüf-Tür bleibt Urteil. Aufwand: Tage.
**Danach C2 (B\*) grillen** — mit P1-SDF als Hindernisgeometrie wird B* real
umsetzbar; Entscheidung dann mit Zahlen statt Vermutung.

### Schritt 4 — Beam-Search-Zerlegung (Option B, ersetzt/ergänzt #165)

Braucht Schritt 1 (sonst unbezahlbar). Kandidaten = Bandhöhen/Breiten-Raster
achsparallel; billige Bewertung (Raycast-Inselkarte nach Z-Chunking-Muster +
eigene Zielfunktion: erreichbarer Anteil, `c_v`, Fugenfläche); Beam mit
ε-Relaxation nach Wu; **nur Beam-Überlebende durch die Prüf-Tür**. Der
#165-Greedy (`causer_link`) wird trotzdem gebaut oder behalten — er ist die
Vergleichsmethode 3 des Papers. Aufwand: mittel–groß.

### Schritt 5 — Benchmark + Paper

Kein Zusatz-Feature: die Schritte 1–4 **sind** die Paper-Methoden.

---

## Publikations-Einschätzung (auf Basis der 18 Volltexte)

**Wohin.** Erste Wahl **Automation in Construction**: Kontovourkis 2020
(direkter Vorläufer) erschien dort, Stamatopoulos 2025 ist dort eingereicht —
IFC-Pipeline + Roboterfertigung ist exakt deren Profil. Alternativen:
*Robotics and Computer-Integrated Manufacturing* (Pipeline + Kinematik),
*Computer-Aided Design* (algorithmischer Zuschnitt, LayerLock erschien dort),
*Frontiers of Architectural Research* (García-Alvarado; niedrigere Hürde).

**Die Story, gegen die Literatur geprüft.** Vier Claims, jeder durch die
Verifikation gedeckt:

1. **Automatisierte IFC→Roboterprogramm-Pipeline (DRL + KRL aus einem
   Kernmodell).** García-Alvarado arbeitet manuell in Grasshopper und nennt
   IFC selbst als Future Work; Kontovourkis nimmt handmodellierte BREPs.
   Niemand im Korpus parst IFC automatisch.
2. **Kollisionsgetriebene Zerlegung mit echter Armsimulation als Kriterium.**
   Der Querbefund trägt das: alle neun Zerlegungs-Quellen konstruieren die
   Kollision weg, keine prüft einen Armkörper gegen den wachsenden
   Druckstand. Unsere Prüf-Tür + Freigang-Stufe ist der methodische Kern.
3. **Vergleichsstudie auf IFC-Wänden mit Simulation als Schiedsrichter.**
   Baselines: manuelle Grundriss-Strategie (nach García-Alvarados
   Faustregeln), analytische Schranken (Schritt 2), Greedy `causer_link`
   (#165), Beam-Search (Schritt 4), optional kartengefiltert (Schritt 3).
   Metrik-Katalog steht oben; Reproduzierbarkeit über ADR-004-Provenienz
   (`decompose.json`-kompatible Pläne, byte-vergleichbar).
4. **Ehrlichkeits-Semantik** („geprüft frei" vs. „vermutlich", #164) — in
   keiner Quelle vorhanden; alle berichten binär.

**Was noch fehlt:** ein Benchmark-Satz (Denkmal-Wand + 2–3 weitere
IFC-Modelle) und die Baselines aus den Schritten 2–4. Sonst nichts — die
Roadmap erzeugt das Paper als Nebenprodukt.

**Risiko, ehrlich:** Wir hätten keinen physischen Druck. Für *Automation in
Construction* ist das ein Minus (die Community mag Demos; Stamatopoulos 2025
ist genau deshalb stark). Gegenmittel: (a) als Computational-/Methods-Paper
positionieren — für RCIM und CAD ist Simulation als Schiedsrichter
ausreichend, Wu und Han sind reine Sim-Paper mit Desktop-Demos; (b) später
einen kleinen Realdruck ergänzen. Fugen/Material (Option D + Poudel +
Kaltfugen-Widerspruch) bleiben bewusst draußen — das ist ein **zweites**
Paper mit Materialversuchen, nicht dieses.

---

## Beschaffung (erledigt 2026-07-10)

Alle acht Wunschlisten-Positionen liegen unter `docs/recherche/inputPDF/`;
Dai et al. (Position 5) kam als Autoren-PDF `SIG18RobotVolPrint.pdf` dazu.

Dateinamen folgen dem Schema `jahr-erstautor-kurztitel.pdf`.

| Datei | Wunschliste | Verifikationsergebnis |
|---|---|---|
| `2024-stamatopoulos-aerial-chunk-decomposition.pdf` | 1 Stamatopoulos, Journal | 6/6 bestätigt, + Gl. 9 |
| `2024-garcia-alvarado-bim-to-3dcp-framework.pdf` | 2 BIM → 3DCP | Abgrenzung geschärft |
| `2025-mercimek-3dcp-walls-cold-joint.pdf` | 3 Kaltfugen | bestätigt, Zahlen-Widerspruch im Paper |
| `2022-krishnamurthy-layerlock.pdf` | 4 LayerLock | **falsch charakterisiert** |
| `2018-dai-support-free-volume-printing.pdf` | 5 Dai et al. | **falsch charakterisiert** |
| `2007-zacharias-capability-map.pdf` | 6a Zacharias | 5/5 bestätigt |
| `2013-vahrenkamp-reachability-inversion.pdf` | 6b Vahrenkamp | 4/4 bestätigt, Notation präzisiert |
| `2020-kontovourkis-robotic-clay-printing.pdf` | 7 Lehmdruck | Delta bestätigt |
| `2024-zhao-multirobot-primitive-partitioning.pdf` | 8 Multi-Robot | **trägt Option B nicht** |

Zweite Runde, frei verfügbar, **2026-07-10 nachgeladen und geprüft**:

| Datei | Quelle | Verifikationsergebnis |
|---|---|---|
| `2019-wu-support-effective-decomposition.pdf` | arXiv 1812.00606 | 6/6 bestätigt (ε statt δ; b unbeziffert) |
| `2024-rudorfer-rm4d-reachability-map.pdf` | arXiv 2410.06968 | 6/6 bestätigt; M1013 erfüllt Annahmen |
| `2025-zhao-bstar-base-placement.pdf` | arXiv 2504.12719 | 4/4 bestätigt; **stärker als gedacht** |
| `2025-qu-inf3dp-implicit-neural-fields.pdf` | arXiv 2509.05345 | bestätigt; „2 Größenordnungen" = Bis-zu-Wert |
| `2025-stamatopoulos-aerial-chunking-experimental.pdf` | arXiv 2502.20549 | Staircase existiert, Motivation korrigiert |
| `2018-mcpherson-chunk-based-slicer.pdf` | par.nsf.gov | Formeln bestätigt; **θ_min nicht übertragbar**; Messwerte gehören Poudel |
| `2022-weber-z-chunking.pdf` | sidilab.net | 5/5 bestätigt; Fügetechnik für Lehm gegenstandslos |
| `2025-han-support-free-model-decomposition.pdf` | Micromachines 16/1316 | 4/4 bestätigt; b = 15; Vergleich fair |
| `2024-glotz-printed-concrete-cold-joints.pdf` | Materials 17/6304 | **Fehlzitat nachgewiesen** |

### Noch zu beschaffen (blockiert)

**Poudel, Sha & Zhou, „Mechanical strength of chunk-based printed parts for
cooperative 3D printing", Procedia Manufacturing 26 (2018) 962–972**,
DOI 10.1016/j.promfg.2018.07.123, PII S2351978918307996.

Gold-Open-Access, aber Elsevier liefert Skripten nur eine Captcha-Seite —
**manuell im Browser laden**, Ablage als
`2018-poudel-chunk-interface-strength.pdf`.

Das ist die **einzige** Quelle im Korpus mit echten mechanischen Messwerten zur
Chunk-Fuge (30° vs. 50°, 32,4 MPa, 121 % gegenüber monolithisch, 0,5 mm
Überlappung). Solange sie fehlt, hat Option D **keinen einzigen verifizierten
Fugen-Festigkeitswert** — alle anderen Fugen-Quellen messen nichts.

## Offene Punkte

- **Poudel et al. beschaffen** (s. o.) — ohne sie steht Option D ohne
  quantitative Fugen-Evidenz da, und die im Optionstext markierten Zahlen
  bleiben ungeprüft.
- **Entscheidung Option C1 vs. C2:** Karte + Prüf-Tür (RM4D, Vorfilter, binär,
  Hindernisse nachgelagert) oder kartenfreie Optimierung (B*, Erreichbarkeit +
  Kollision gemeinsam über eine ganze Posensequenz). B* passt formal besser auf
  „ein Standplatz, ganze Höhenreihe", braucht aber unseren wachsenden
  Druckstand als schichtweise aktualisierte Hindernisgeometrie und hängt am
  kommerziellen COPT-Solver. RM4D ist billiger, offener und sofort baubar,
  liefert aber nur einen Vorfilter. **Grillen vor Umsetzung.**
- **Option B braucht eine eigene Zielfunktion.** `J_G` (Überhangfläche) misst
  bei einer nicht drehbaren Wand die falsche Größe. Kandidaten: erreichbarer
  Wandanteil, kinematische Marge, Fugenfläche, Volumen-Gleichmäßigkeit `c_v`.
  Der Beam-Search-Rahmen (Wu) und die Masken-Matrixform (Han) sind übernehmbar.
- **Option E: Voxel-SDF statt neuronal.** INF-3DP belegt den Hebel, nicht die
  Notwendigkeit eines Netzes. Konservative Iso-Fläche oder exakter Nachprüfer
  an Grenzfällen einplanen.
- **Kaltfugen-Widerspruch klären:** Mercimek (10–15 min Pause, Lateralbelastung)
  findet die Fuge als dominanten Schwächungsfaktor, Glotz (90 min Pause,
  Biegung, 148 d Prüfalter) findet keinen klaren Effekt. Vor jeder Übertragung
  auf Lehm ist zu klären, welche Größe (Pausendauer? Prüfalter? Lastrichtung?)
  den Unterschied macht.
- Lehm-spezifisch: **keine** der Fugen-Quellen betrifft Lehm, und drei von vier
  messen überhaupt keine Festigkeit. Materialversuch (Fugen-Zugproben
  geneigt/verzahnt/eben) wäre ein eigener Spike und Paper-Baustein.
- Paper-Skizze nachziehen: „BIM-Wand segmentieren → slicen → Roboterprogramm"
  ist durch García-Alvarado Stand der Technik. Neuheitsanspruch auf
  Automatisierung, Kollisionskriterium und gradierten Lehm umformulieren —
  gestützt durch den Querbefund (keine Quelle prüft den Arm gegen den
  wachsenden Druckstand).
- Entscheidung Tobias: welche Optionen (A–F) in Issues gießen. Nach der Prüfung
  sind **C und E** die am besten abgesicherten Kandidaten (E mit klarer
  Bauanleitung), **B** braucht vorher eine Zielfunktions-Entscheidung,
  **D** braucht Poudel und einen Materialversuch.

## Nachtrag 2026-07-12 — Querbefund korrigiert, Option E invertiert

Der zentrale Querbefund („niemand prüft den Arm gegen den wachsenden
Druckstand") ist in seiner absoluten Form **durch Shen et al. 2026
([arXiv 2606.29766](https://arxiv.org/abs/2606.29766), erschienen 29.06.2026 —
von dieser Recherche nicht erfasst) überholt**; er bleibt in engerer
Formulierung tragfähig (Schiedsrichter einer diskreten Zerlegungs- und
Platzierungssuche im Bau-Maßstab, ab IFC). Zugleich invertiert deren
Kollisionsmodell unsere Option E (statische Glied-SDFs + Druckstand als
wachsende Punktwolke statt Druckstand-SDF) und löst damit US 15 von PRD #183
konstruktiv. Details, Abgrenzung und Folge-Entscheidungen (Grill 2026-07-12):
[2026-07-12-nachtrag-neuheitskern-shen2026.md](2026-07-12-nachtrag-neuheitskern-shen2026.md).
Der Text oben bleibt unverändert stehen (Korrektur als Nachtrag).

# Recherche: Druckmuster, Schwindrisse und durchgehende Bahnen

Stand 20.10.2026, Aufgabe R des Nachtlaufs „Druckmuster“. Grundlage sind Web-Recherchen vom selben Tag.
Bezugswerte: Strangbreite w = 30 mm, Schichthöhe h = 10 mm, Wände 200–365 mm, Module 300–1200 mm lang,
2 Schalen je Seite, bei 200 mm Wand 80 mm Hohlraum und 50 mm breites Band für Infill-Mittellinien.

## Kennzeichnung und Vorbehalte

- **B** = belegt: Aussage und Zahl stehen in der genannten Quelle (Abstract oder Volltext gelesen).
- **E** = Einschätzung: Folgerung oder Rechnung von mir, nicht in einer Quelle belegt.
- **A** = Annahme für unsere Startwerte (gehört in den SPEC-Nachtrag).
- Mehrere Verlagsseiten (MDPI, ScienceDirect, Cardiff-PDF, Springer) waren nicht abrufbar (HTTP 403). Dort
  stützen sich die Angaben auf Abstracts bzw. Crossref-Metadaten. Volltext gelesen habe ich nur Zhao et al. (2016)
  und Watson et al. (2026).
- **Lücke:** Für Lehm und Cob gibt es nach meiner Suche **keine veröffentlichte Regel für Fugen- oder
  Gliederungsabstände** und keine Studie, die Sinus-, Zickzack- oder Wellenmuster gegen Schwindrisse vergleicht.
  Die Werte für Outfill sind deshalb Einschätzungen, die erst der Testdruck prüft.

## 1. Infill und Wandmuster im Lehm-, Cob- und Betondruck

### 1.1 WASP / TECLA / IAAC
- **Quelle:** Sekundärberichte zu TECLA (Entwurf Mario Cucinella Architects, Bau WASP, Ravenna), 3DPrint.com und
  3Dnatives zu IAAC/WASP, Händler-Datenblatt Crane WASP (filament2print.com). Keine Primärpublikation gelesen.
  Z. B. https://www.mcarchitects.it/notizie-ens/detail-3d-printed-earthen-structure-of-the-tecla-prototype-ravenna
  und https://www.3dnatives.com/en/wasp-and-iaac-create-3d-printed-wall-with-embedded-staircase/
- **Kernaussage (B, sekundär):** TECLA besteht aus Ton und Reishülsen, rund 200 Druckstunden, etwa 350 Schichten
  zu je 12 mm. Die hohlen Wände haben Wellen als Innengliederung für Leichtigkeit und Dämmung. Neigung der Kuppeln und
  Füllstruktur richteten sich nach dem Verhalten des Materials und den Änderungen während der Aushärtung. Die
  Crane-WASP druckt mit 25–40 mm Düsen und 12–20 mm Schichthöhe (zwei Quellen weichen bei den Düsengrößen ab). Die
  IAAC/WASP-Wand (2019) war 40 cm dick, aus Ton mit Reisfaser, rund 2 m³ in 40 h, mit mehreren Innenflächen für
  Festigkeit.
- **Folgerung für uns:** Unser Verhältnis w = 30, h = 10 (h/w = 0,33) liegt im Bereich der Crane-WASP. Gewellte
  Innenstrukturen in dicken Lehmwänden sind Stand der Praxis; eine veröffentlichte Wellenlänge oder Amplitude fand
  ich nicht. Wir müssen sie aus Geometrie und Krümmungsradius ableiten (Abschnitt 4.3).

### 1.2 Ferretti et al. 2022
- **Volle Angabe:** Ferretti E., Moretti M., Chiusoli A., Naldoni L., De Fabritiis F., Visonà M. (2022):
  *Mechanical Properties of a 3D-Printed Wall Segment Made with an Earthen Mixture*. Materials 15(2), 438.
  https://doi.org/10.3390/ma15020438
- **Kernaussage (B):** Druckfestigkeit 2,32 MPa, vergleichbar mit Stampflehm. Der Infill scheint die
  Ausbreitung von Rissen zu stoppen; dadurch bleibt nach dem Höchstwert mehr als 50 % der Maximallast erhalten und
  das dilatante Verhalten setzt nicht ein.
- **Folgerung:** Der Infill hat neben der Dämmung eine rissbegrenzende Wirkung bei Last. Das stützt Querstege bis an
  die Außenschale (O3), ersetzt aber keinen Beleg gegen Schwindrisse (Last, nicht Trocknung). E

### 1.3 Gomaa et al. (Cob, Adelaide/Cardiff/Plymouth)
- **Volle Angaben:**
  - Gomaa M., Jabi W., Veliz Reyes A., Soebarto V. (2021): *3D printing system for earth-based construction:
    Case study of cob*. Automation in Construction 124, 103577. https://doi.org/10.1016/j.autcon.2021.103577
  - Gomaa M., Vaculik J., Soebarto V., Griffith M., Jabi W. (2021): *Feasibility of 3DP cob walls under compression
    loads in low-rise construction*. Construction and Building Materials 301, 124079.
    https://doi.org/10.1016/j.conbuildmat.2021.124079
  - Gomaa M. (2021): *Holistic Investigation of Robotically Assisted 3D Printed Cob Walls*, PhD-Arbeit,
    University of Adelaide.
- **Kernaussage (B, nur Abstracts und Zusammenfassungen):** Überarbeitete Cob-Rezeptur und Doppelkolben-Extruder;
  gedruckter Cob verhält sich ähnlich wie konventioneller Cob; ein Rechteckquerschnitt der Raupe entfernte
  Lufteinschlüsse und brachte 15 % mehr Druckfestigkeit. Drei Wandmuster wurden mit FE (Grasshopper, ABAQUS) nach
  Grenzzustand untersucht; gedruckte Wände können Schwerelasten im Wohnbau tragen.
- **Nicht belegt:** Welche drei Muster (Sinus, Zickzack, …) und welche Maße. Ich konnte das Manuskript nicht
  lesen (https://orca.cardiff.ac.uk/id/eprint/142496/1/CONBUILDMAT-D-20-08200_R2.pdf, HTTP 403).
- **Folgerung:** Gute Verdichtung bzw. Flächenkontakt zwischen den Strängen ist Ziel (Kontaktbreite, Abschnitt 3). E

### 1.4 Nguyen, Park, Kim 2026
- **Volle Angabe:** Nguyen T. T., Park J., Kim D.-H. (2026; online 2025): *Impacts of infill patterns and curve
  types in 3D printed clay walls*. Journal of Building Engineering 117, 114758.
  https://doi.org/10.1016/j.jobe.2025.114758
- **Kernaussage (B, Abstract):** 87 Druckversuche an doppelt gekrümmten Tonflächen. Dreiecks- und Gitter-Infill
  heben den maximal druckbaren Überhangwinkel um bis zu 20° gegenüber Vollfüllung auf 50°–60°. Waben sparen
  mehr Material und Zeit, helfen aber weniger beim Überhang.
- **Folgerung:** Querstege stützen Überhänge, aber Dreieck und Gitter kreuzen sich und erfüllen M2 nicht. Wir
  nutzen die Aussage nur als Begründung für Quersteg-Dichte an Laibungen (M3). E

### 1.5 Überhangwinkel bei Lehm
- **Quelle:** IAARC-Paper „Exploring Extreme 3D Printed Clay Overhangs with Integrated Active Hot Air Drying System on
  Robotic Arm“ (Autoren nicht verifiziert),
  https://www.iaarc.org/publications/fulltext/042_Exploring_Extreme_3D_Printed_Clay_Overhangs_with_Integrated_Active_Hot_Air_Drying_System_on_Robotic_Arm.pdf
- **Kernaussage (B, Suchergebnis):** Ohne Stütze versagen Lehmüberhänge typisch bei 17–20°; mit aktiver
  Heißlufttrocknung 50°, Versagen bei 60°.
- **Folgerung:** Unser M3 mit δ = 2 mm je Schicht von h = 10 mm entspricht atan(2/10) = 11,3° und liegt unter
  der 17–20°-Grenze (Rechnung, E). δ = 2 mm ist als A vertretbar, mit Reserve von rund 6°.

## 2. Schwindrisse bei Lehm und Cob und Gegenmittel

### 2.1 Gonzales et al. 2024
- **Volle Angabe:** Gonzales B., Zavaleta D., Bertolotti B., Aguilar R., Pando M., Nakamatsu J., Kim S., Silva G. (2024):
  *Comprehensive Investigation into the Influence of Soil Composition and Water Content on Cracking Due to Drying
  Shrinkage in 3D-Printed Earthen Structures*. In: Second RILEM International Conference on Earthen
  Construction, RILEM Bookseries, S. 22–31. https://doi.org/10.1007/978-3-031-62690-6_3
- **Kernaussage (B, Suchergebnis/Abstract):** Ton- und Wassergehalt bestimmen das Trocknungsrissbild. Zwei Mischungen
  blieben **rissfrei**: 50 Gew.-% des Bodens durch Feinsand ersetzt, plus 0,55 bzw. 2,20 Gew.-% SHMP (Dispergiermittel)
  zur Wassersenkung. Gültigkeit für andere Böden offen.
- **Folgerung:** Der wirksamste Hebel ist die Mischung (weniger Ton, weniger Anmachwasser), nicht das Muster. Das
  Muster soll Restspannungen abbauen, kann aber eine schlechte Mischung nicht retten. E

### 2.2 Bhusal, Sedghi, Hojati 2023
- **Volle Angabe:** Bhusal S., Sedghi R., Hojati M. (2023): *Evaluating the Printability and Rheological and
  Mechanical Properties of 3D-Printed Earthen Mixes for Carbon-Neutral Buildings*. Sustainability 15(21), 15617.
  https://doi.org/10.3390/su152115617
- **Kernaussage (B, Abstract):** Boden mit 15 % Nontronit schwindet stark und reißt großflächig. Weizenstrohfasern
  verhinderten große Risse und senkten das Schwinden **bis auf 2,6 %**. Kalk und Puzzolan halfen nicht.
- **Folgerung:** Fasern sind das belegte Gegenmittel. Fasern richten sich im Strang längs aus (siehe 2.4).

### 2.3 Zozaya et al. 2026
- **Volle Angabe:** Zozaya D., Shojaeian H., Uviña-Contreras F., Hojati M. (2026): *3D Printing of Earth-Based
  Mixtures: Linking Material Design, Printability, and Structural Performance*. Buildings 16(6), 1261.
  https://doi.org/10.3390/buildings16061261
- **Kernaussage (B, Abstract):** Bei einer Mischung Boden:Sand 2:1 sank das frühe Schwinden mit 2 % Reishülsenfaser
  und kleinerem Größtkorn (Sieb Nr. 16) von **12,33 % auf 3,48 %** (−72 %), bei gleich bleibender Festigkeit nach 28 Tagen.
- **Folgerung:** Freies lineares Schwinden liegt selbst bei guten Mischungen bei einigen Prozent. Auf einer
  geraden Raupe von 600 mm sind 3 % **18 mm** Längenänderung (Rechnung, E). Diesen Betrag müssen Fugen oder
  Wellen aufnehmen, wenn die Raupe am Fuß festgehalten wird.

### 2.4 Cob-Schwindverhalten, Fasern und Faserausrichtung
- Experimental study on shrinkage behaviour of earth walling materials with fibers and stabilizer for cob building,
  Construction and Building Materials (Autoren und Jahr nicht verifiziert),
  https://www.sciencedirect.com/science/article/abs/pii/S0950061820314549 (Seite 403).
  **Kernaussage (B, Suchergebnis):** Mehr Fasern bedeuten weniger lineares Schwinden und weniger Risse;
  niedrigerer Anfangswassergehalt und niedrigere Temperatur helfen.
- Vargas A., Robayo-Salazar R., Mejía de Gutiérrez R. (2024): *Effects of Incorporating Fine Aggregates and
  Polypropylene Microfibres on the Cracking Control of 3D Printed Cementitious Mixtures*. Buildings 15(1), 55.
  https://doi.org/10.3390/buildings15010055. **Kernaussage (B, Abstract und Suchergebnis):** 6 mm lange
  PP-Fasern verhinderten Schwindrisse (ungefaserte Mischungen rissen nach 14 Tagen im Freien, gefaserte zeigten in
  90 Tagen keine). Fasern richten sich beim Extrudieren in Strangrichtung aus, also in der
  rissgefährdeten Richtung. Zementgebunden, nur als Prinzip übertragbar.
- **Folgerung:** Fasern in Strangrichtung bewehren genau die Richtung, in der lange gerade Raupen schwinden.
  Sie senken die Rissneigung, beseitigen aber die Längsspannung nicht. E

### 2.5 Fugen, Risse an der Einspannung
- **Quellen:** „Cracking in rammed earth“ (ResearchGate-Eintrag, Autoren nicht verifiziert); „Structural stability of
  3D-printed earthen catenary domes: Experimental and analytical insights“ (ScienceDirect S2352012425020880,
  Autoren nicht verifiziert, 2025).
- **Kernaussage (B, Suchergebnis):** Beim Stampflehm sind nahezu senkrechte Schwindrisse für die Standsicherheit
  unkritisch; Dehnfugen in Abständen werden vorgeschlagen, ohne Abstandszahl. Bei der gedruckten Kuppel
  entstanden zwei Hauptrisse beim Trocknen, beide am Fuß, wo Ringzug und Einspannung zusammentreffen.
- **Folgerung:** Risse beginnen dort, wo die Wand am Fuß festgehalten wird. Bei uns ist das die Auflagerfuge
  zur Platte bzw. zum Modul darunter. Gliederung wirkt am besten, wenn sie bis auf die erste Schicht reicht; bei
  gleicher XY-Geometrie je Schicht (Grundsatz M3) ist das gegeben. E
- **Keine Zahl für Fugenabstände in gedrucktem Lehm gefunden.** Für Beton gilt Fugenschneiden als Stand der Technik
  (nur Patentbeschreibung gesehen, nicht belastbar); der Abstand hängt von Mischung, Trocknung und Einspannung ab.

## 3. Raupenüberlappung, Kontaktbreite und Krümmung

### 3.1 Raupenquerschnitt und Kontaktbreite
- **Quelle:** Alhussain A., Duarte J., Brown N. (2024): *Developing a data-driven filament shape prediction model for
  3D concrete printing*. Frontiers in Built Environment 10, 1363370. https://doi.org/10.3389/fbuil.2024.1363370
- **Kernaussage (B, Abstract):** 144 Proben mit variierten Prozessparametern (Düsengeschwindigkeit, Düsendurchmesser,
  Düsenhöhe, Fördergeschwindigkeit); gemessen werden Breite, Höhe und **Kontaktbreite**, mit Vorhersagemodellen.
  Zahlenwerte stehen nicht im Abstract.
- **Folgerung:** Kontaktbreite und Raupenbreite sind material- und prozessabhängig und müssen am Gerät kalibriert
  werden. Unsere Kennzahl M7 (Kontaktzonen) ist damit eine Geometrie-, keine Festigkeitsgröße. E

### 3.2 Rechnung zur Überlappung (E)
Das übliche Stadion-Modell der Raupe (Rechteck mit halbkreisförmigen Seiten, wie im FDM-Flussmodell) ergibt den
Mittenabstand für vollständiges Füllen ohne Lücken: d = w − h·(1 − π/4). Das Modell stammt aus meinem Vorwissen
und ist hier nicht mit einer Lehm-Quelle belegt.
- Mit w = 30, h = 10: d = 30 − 2,146 = **27,9 mm**. Das ist eine Überlappung von 2,1 mm bzw. ε = 0,07.
- Unser M2-Grenzwert (1 − 0,15)·30 = **25,5 mm** liegt darunter und ist damit großzügig. Nominale Kontakte mit
  ε = 0 … 0,1 (d = 27–30 mm) liegen im physikalisch sinnvollen Bereich.
- Weiches Material quetscht stärker. Dort steigt die Kontaktbreite, ε kann größer werden. Das ist am Gerät zu kalibrieren.

### 3.3 Ecken, Radien und Überfüllung
- **Quellen:** Li M., Liu Z., Ho J., Wong T. (2023): *Improving Homogeneity of 3D-Printed Cementitious Material
  Distribution for Radial Toolpath*. Fluids 8(3), 87. https://doi.org/10.3390/fluids8030087; Liu Z., Si L., Liu Y.,
  Li M., Wong T. (2025): *Optimization of Printing Parameters Based on Computational Fluid Dynamics (CFD) for Uniform
  Filament Mass Distribution at Corners in 3D Cementitious Material Printing*. Crystals 15(8), 725.
  https://doi.org/10.3390/cryst15080725
- **Kernaussage (B, Abstract/Suchergebnis):** In Kurven lagert sich innen weniger, außen mehr Material ab. Der Effekt
  wächst mit kleinerem Bahnradius, höherer Düsengeschwindigkeit und größerer Raupenbreite. Die Materialungleichheit
  beträgt in der Simulation bei Rechteckdüse 1,35 (Gauß-Düse 0,98). Laut Suchergebnis (Wortlaut nicht am
  Volltext geprüft) ist für kleine Radien (R ≤ 30 mm) mit der üblichen Rechteckdüse eine Verteilung unter 1,25 nicht
  erreichbar. Beton, Simulation.
- **Folgerung:** Als **Zielradius R ≥ w = 30 mm** (M6) passt das zur Literatur. Der harte Wert w/2 = 15 mm ist
  die geometrische Grenze, bei der der Innenrand der Raupe zum Punkt wird. Kurven unter 30 mm sollten
  langsamer gefahren werden (Empfehlung an den Planer; die Pumpe läuft durch, die Geschwindigkeit sinkt). E
- Eine **veröffentlichte Mindestradius-Regel relativ zur Strangbreite für Lehm** fand ich nicht.

## 4. Durchgehende Bahnen ohne Kreuzung

### 4.1 Connected Fermat Spirals
- **Volle Angabe:** Zhao H., Gu F., Huang Q.-X., Garcia J., Chen Y., Tu C., Benes B., Zhang H., Cohen-Or D., Chen B.
  (2016): *Connected Fermat Spirals for Layered Fabrication*. ACM Transactions on Graphics 35(4) (SIGGRAPH 2016).
  https://doi.org/10.1145/2897824.2925958 (Volltext gelesen).
- **Kernaussage (B):** Zerlegt das Gebiet in Teilgebiete, die je eine Fermat-Spirale füllt. Start und Ende liegen
  jeweils annähernd am selben Punkt der Außenkante, daher lassen sich die Spiralen entlang eines Graphen zu **einer
  globalen durchgehenden Kurve** verbinden. Die Kurve besteht überwiegend aus langen, flach gekrümmten Bahnen.
  Anteil scharfer Kurvenpunkte (Tabelle 1, Beispiel h-slice1): Zickzack 4,35 %, konturparallel 1,08 %, CFS 0,81 %;
  h-slice2: 5,12 %, 0,88 %, 0,70 %. FDM-Test mit Bahnbreite 0,4 mm, Schichtdicke 0,2 mm, Maximalgeschwindigkeit 80 mm/s.
  Die Glättung erzeugt vereinzelt Lücken (Unterfüllung), die beim FDM durch Schmelzfluss geschlossen werden.
- **Folgerung:** Gut für kleine Inseln (Pfeiler, Wandstücke zwischen Öffnungen): kein Absetzen, keine
  Kreuzung, Start und Ende am Rand. Das passt zum senkrechten Schichtwechsel (M4) mit Umkehrung je Schicht.
  **Vorbehalt:** Lücken sind bei Lehm (kein Schmelzfluss) nicht heilbar; wir brauchen Kontakt zwischen den
  Spiralarmen (ε-Bereich) und keine Glättung, die Lücken öffnet. E

### 4.2 Eulerpfade im Infill
- **Volle Angaben:**
  - Gupta P., Krishnamoorthy B., Dreifus G. (2020): *Continuous toolpath planning in a graphical framework for sparse
    infill additive manufacturing*. Computer-Aided Design 127, 102880 (arXiv:1908.07452).
    https://doi.org/10.1016/j.cad.2020.102880
  - Watson C. J., Barton K., Aghaei Meibodi M. (2026): *Functionally Graded Lattice Walls via Continuous Eulerian
    Toolpaths for Robotic 3D Concrete Printing*. Digital Concrete 2026 (University of Michigan, DART Lab).
    https://dartlab.umich.edu/wp-content/uploads/2026/08/2026_Digital-Concrete-2026_Functionally-Graded-Lattice-Walls-via-Continuous-Eulerian-Toolpaths-for-Robotic-3D-Concrete-Printing.pdf
    (Volltext gelesen)
- **Kernaussage (B):** Gupta: Die „Euler-Transformation“ macht alle Knoten gerade (Grad 4), sodass **ein**
  Eulerzug je zusammenhängendem Gebiet und Schicht alle Kanten ohne Absetzen druckt, ohne Materialkollision und ohne
  Überkreuzung im Sinne von Überlagerung. Watson: Gitterwand 1,00 × 0,60 × 0,35 m, 35 Schichten à 10 mm, ein einziger
  Pfad, 25,4 mm Runddüse, 2,8 l/min, 167–209 mm/s, rund 520 m Pfad in 47 min 51 s. Ein Eulerzug braucht genau zwei
  Knoten ungeraden Grades; die vier Eckknoten werden mit einer „Stitch“-Kante auf zwei reduziert. Start und Ende
  **wechseln je Schicht**, und der Start der Schicht k+1 ist der Knoten, der dem Ende der Schicht k am nächsten
  liegt. Ziel-Mittenabstand der Gitterstege dtarget = 50 mm bei 25,4 mm Düse (rund 2 Düsenbreiten). Unterbrechungen
  verschlechtern laut den Autoren die Zwischenschichthaftung und führen zu Überbau an den Knoten.
- **Folgerung (wichtig):** Start und Ende je Schicht tauschen und die nächste Schicht am vorigen Ende beginnen
  lassen entspricht unserer Schichtfolge `alternate` und bestätigt M4. **Aber:** Eulerzüge laufen durch Knoten mit
  Grad 4 zweimal. Der Pfad kreuzt sich dort selbst und verletzt M2. Eulerzüge sind für uns nur nutzbar, wenn die
  Knoten durch Tangentialkontakt statt Kreuzung entstehen. Rechteck- und Dreiecksgitter fallen damit aus. Wellen
  zwischen zwei Schalen berühren die Schale nur tangential und kreuzen nicht. E
- **Nicht gelesen:** Wan Q., Yang W., Wang L., Ma G. (2023): *Global continuous path planning for 3D concrete printing
  multi-branched structure*. Additive Manufacturing 71, 103581 (nur als Referenz in Watson et al. gesehen). Zu
  Zickzack-Infill im Betondruck habe ich keine belegten Zahlen.

### 4.3 Kreuzungsfreiheit und Krümmung der Sinuswelle (E, Rechnung)
Ein Sinus der Amplitude A (halbe Spannweite der Mittellinie) und Wellenlänge λ hat die maximale Krümmung A·(2π/λ)²,
also den kleinsten Radius R = λ²/(4π²·A). Mit A = 25 mm (Band 50 mm, Kontakt an beiden Innenschalen):
- R ≥ 30 mm (Ziel) erfordert λ ≥ 172 mm; R ≥ 15 mm (hart) erfordert λ ≥ 122 mm.
- λ = 200 mm: R = 40,5 mm, Bogenlängenzuwachs gegenüber der Geraden 14,0 %. λ = 250 mm: R = 63 mm, +9,2 %.
  λ = 300 mm: R = 91 mm, +6,5 %.
- Der Abstand benachbarter Bögen ist unkritisch: Bei λ = 172 mm beträgt der senkrechte Abstand an der
  Nulllinie rund 63 mm (> 25,5 mm für M2).
- Auf einem 600 mm langen Modul gibt λ = 200 mm drei volle Wellen, also 6 Kontakte je Seite (rund 10 je Meter und Seite).

## 5. Nahtstrategien

- **Zhao et al. 2016 und Watson et al. 2026** (siehe oben): Start und Ende liegen am selben Randpunkt bzw. der
  nächste Schichtstart am vorigen Schichtende; Start und Ende wechseln je Schicht. Das belegt einen
  Schichtwechsel ohne Diagonale. B
- **FDM allgemein:** Die Z-Naht erzeugt eine sichtbare Linie an derselben XY-Stelle; Slicer verlegen sie in Ecken
  oder auf die Rückseite. Das ist verbreitete Praxis, hier nicht mit einer Quelle belegt. E
- **Folgerung für uns:** Bei Umkehrung je Schicht liegt der Hub abwechselnd am Pfadende (innen) und am
  Pfadanfang (außen). Der äußere Hub liegt in jedem zweiten Schichtwechsel auf der äußersten Schale und ist dort
  sichtbar (Materialpunkt, Beschleunigung). Empfehlung: Bahnbeginn auf der **Rückseite** (nicht Sichtseite) der
  Wand, mindestens eine Strangbreite vom Modulende und nicht an der Stoßfläche (M4), bevorzugt in einem Wellental
  der Außenschale oder an einem Quersteg. A
- Die Seite, auf der der äußere Hub liegt, ist durch die Wahl von „außen → innen“ gegen „innen → außen“ als
  Startschicht umkehrbar; welche Seite Sichtseite ist, entscheidet der Nutzer. E

## 6. Folgerungen für Outfill (O1, O2, O3)

Die Rissneigung hängt an der ungestützten geraden Länge in Längsrichtung, am Einspannungsgrad am Fuß und an der
Mischung (Abschnitt 2). Wegen der fehlenden Quellen für Fugenabstände (Abschnitt 2.5) sind die folgenden Werte E.

- **O1 gewellte Außenschale.** Eine Welle nimmt Längenschwinden durch Verformung auf. Bogenlängenzuwachs gegenüber
  der Geraden (Rechnung): A = 5, λ = 100 mm → 2,4 %; A = 8, λ = 120 mm → 4,3 %; A = 10, λ = 150 mm → 4,3 %. Das
  liegt in der Größenordnung des Schwindens guter Mischungen (2,6–3,5 %, Abschnitt 2.2 und 2.3), aber unter dem
  schlechter Mischungen (12 %). Die Welle bleibt in der IFC-Dicke, wenn die Außenschale um höchstens A nach innen
  ausweicht und die Innenseite des Bandes frei bleibt; bei 200 mm Wand ist das erfüllt. Kleinster Radius:
  A = 8, λ = 120 mm → 45,6 mm; A = 10, λ = 150 mm → 57 mm; A = 5, λ = 100 mm → 50,7 mm. Alle ≥ 30 mm.
- **O2 Sollrissfugen.** Eine Kerbe in der Außenhaut, die an einem Quersteg endet, bündelt Risse. Gliederungsabstand =
  Feldlänge, Startwert 300 mm. Das passt zu den kurzen Modulen (300–1200 mm): 1 bis 4 Felder je Modul. Muss am
  Testdruck bestätigt werden. A
- **O3 Zellwand.** Querstege bis an die Außenhaut. Die Außenschale hat zwischen zwei Stegen eine Feldlänge von
  300 mm. Der Steg steift das Feld gegen Verkrümmen, hält es aber nicht gegen Längsschwinden; Risse
  entstehen dann am Stegansatz. E

## 7. Empfohlene Startwerte

| Größe | Startwert | Bereich für Parameterstudie | Begründung | Kennz. |
|---|---|---|---|---|
| Strangbreite w, Schichthöhe h | 30 mm, 10 mm | fest | Vorgabe; vergleichbar Crane-WASP (25–40 mm, 12–20 mm) und Watson (25,4 mm, 10 mm) | B |
| Infill-Wellenlänge λ (Band 50 mm, A = 25 mm) | **250 mm**; Untergrenze 172 mm | 172–300 mm | R_min = λ²/(4π²A): bei 250 mm 63 mm (≥ w), Bogenzuwachs 9 %; bei 172 mm genau R = 30 mm | E |
| Infill-Amplitude A (Mittellinie) | **25 mm** (Spannweite 50 mm) | 15–25 mm | berührt beide Innenschalen im 50-mm-Band bei 200 mm Wand; bei kleinerem A fällt der Kontakt weg | E |
| Kontaktabstand Infill (je Schale) | alle λ/2 = 125 mm | 86–150 mm | folgt aus der Wellenform; rund 8 Kontakte je m und Seite | E |
| Außenhaut O1: Wellenlänge | **150 mm** | 100–200 mm | R ≥ 30 mm bei A ≤ 10; Zuwachs 4,3 %, etwa die Schwindung guter Mischungen | E/A |
| Außenhaut O1: Amplitude | **8 mm** | 5–10 mm | bleibt in der Wanddicke; Zuwachs 2,4–4,3 % | E/A |
| Gliederungsabstand O2/O3 (Feldlänge) | **300 mm** | 200–600 mm | kürzer als das kürzeste Modul; Literatur gibt keinen Wert (Abschnitt 2.5) | A |
| Längste gerade ungestützte Außenstrecke | ≤ 300 mm (Zielgröße der Kennzahl) | 200–400 mm | Kennzahl zur Rissneigung, Modullänge 300–1200 mm | A |
| Überlappung ε (Nennwert) | **0,05** (d = 28,5 mm) | 0–0,10 | Stadion-Modell: volle Füllung bei ε = 0,07 (d = 27,9 mm); Lehm quetscht je nach Kalibrierung mehr | E |
| Überlappung ε (M2-Grenze) | 0,15 (d ≥ 25,5 mm) | fest (Auftrag) | etwa doppelt so groß wie die Stadion-Überlappung, also tolerant | A |
| Mindestradius Mittellinie | hart **15 mm** (w/2), Ziel **30 mm** (w) | fest (Auftrag) | bei R ≤ 30 mm ungleiche Verteilung in der Betonsimulation; unter 15 mm Innenrand = 0 | E |
| Überhangtoleranz δ | 2 mm (11,3°) | 1–3 mm | unter den belegten 17–20° der Lehmgrenze | B/E |
| Nahtlage | Rückseite, ≥ w vom Modulende, nicht an Stoßfläche, im Wellental oder an einem Quersteg | – | Z-Naht ist sichtbar; Start/Ende am Rand wie CFS | A |
| Schalen je Seite | 2 bei 200 mm; 1 bei 300–365 mm mit breiterem Band | – | Kontaktband nach Auftrag | A |
| Fermat-Spirale | nur für kleine Inseln (Restbreite unter etwa 3 w) | – | Spiralarmabstand ≈ w; größere Inseln besser mit Welle | E |

## 8. Offene Punkte

1. Primärquellen zu WASP/TECLA/IAAC (Muster, Maße) fehlen; nur Sekundärberichte.
2. Gomaas drei Wandmuster mit Maßen sind unbelegt (Manuskript nicht abrufbar).
3. Kein Beleg für Fugenabstände oder für Wellen als Rissmittel in gedrucktem Lehm. O1 bis O3 sind Hypothesen;
   der Vergleich lebt von der Kennzahl „längste ungestützte gerade Außenstrecke“ und vom späteren Testdruck.
4. Kontaktbreite und Quetschung bei Lehm brauchen Kalibrierung am Gerät (ε-Bereich 0 bis 0,1 offen).
5. Autoren einzelner Quellen (IAARC-Paper, ScienceDirect-Cob-Schwindung, Kuppel-Studie, Stampflehm-Risse) sind nicht
   verifiziert und im Text so markiert.

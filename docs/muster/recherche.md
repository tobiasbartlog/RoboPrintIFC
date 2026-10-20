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
| **Fugenwand (Nachtrag, Abschnitte 9 bis 11)** | | | | |
| Feldlänge a (Außenstrang zwischen zwei Fugen), Wand 200 mm | **240 mm** (Modul 600 mm: 3 Felder à 200 mm) | 160–300 mm | Stegwinkel θ = atan((t − 2w)/a) = 30° bei 240 mm, 35° bei 200 mm; Fugenöffnung = Schwindmaß · a, bei 1 % und 240 mm rund 2,4 mm; Praxisabstände der Normen (3,6 m) sind für Druckwände nicht übertragbar (9.1, 11.1) | E/A |
| Feldlänge a, Wand 300 mm bzw. 365 mm | **340 mm** bzw. **430 mm** (θ = 35°) | 240–450 mm | a = (t − 2w)/tan θ | E |
| Stegwinkel θ (Steg gegen Wandachse) | **≥ 30°, Ziel 35°–45°** | 25°–50° | Spitze zwischen Außenfeld und Steg ist bis s ≥ 12,75 mm/sin(θ/2) ab Scheitel mit Material gefüllt: 49 mm bei 30°, 59 mm bei 25°, 33 mm bei 45°; Ferretti druckte ±45° | E (Ferretti B) |
| Knotenlage (Mittellinie Steg am Knoten) | Wandmitte ∓ w/2: Vorder- und Rückknoten berühren sich mit Mittelliniendistanz w | – | Kontakt nach M2/M7; ergibt Δy = (t − 2w)/2 = 70 mm bei 200 mm Wand | E |
| Gurt (Mittelstück zwischen Knoten) | zuerst **ohne Gurt**; mit Gurt nur auf einer Seite oder beide um w/2 von der Mittelebene abgerückt | 0–a | Zwei Gurte auf derselben Mittellinie wären eine Doppelraupe (M2-Verstoß) | E |
| Fugenspalt und Fugenform | **stumpf**, Raupen berühren sich nur am Scheitel; Kerbe ergibt sich aus dem Eckradius (Tiefe ≈ R + w/2) | Spalt 0–5 mm | Die Fuge soll ein Gelenk bleiben: kleine Kontaktlänge. NZS 4299 11.2 zeigt V-Kerben auf beiden Wandseiten | E (Norm B) |
| Eckradius an Fuge und Knoten | **≥ 15 mm hart, Ziel 20–30 mm** | 15–30 mm | M6; bei der Kehre um etwa 150° gibt es keinen Hohlraum, Überfüllung, daher dort langsamer fahren | E |
| Rückseite | **gespiegelt** (Fugen gegenüber, durchgehende Sollbruchebene) als Standard; um a/2 versetzt als Variante | – | Rissebene eindeutig; versetzt macht die Wand als Ganzes steifer, hat aber keine durchgehende Rissebene (10.3) | E/A |
| Modulstoß und Modullänge | Modulstoß zählt als Fuge; ganze Zahl Felder je Modul, Rest gleichmäßig verteilt | – | Auftrag; NZS 4299 11.1.3: Fugen an Öffnungen, Dickenwechseln, Stufen und Ecken | A (Norm B) |
| Fugen an Laibung und Ecke | Fuge an jeder Laibung; erste Fuge ≥ a/2 und ≥ 900 mm vom Außeneck, soweit die Modullänge es zulässt | – | NZS 4299 11.1.3 (e) für zementhaltigen Lehm bzw. Stampflehm | B (anderes Verfahren) |
| Kennzahl längste ungestützte gerade Außenstrecke | = a, Grenze 300 mm | 160–300 mm | siehe oben | A |

## 8. Offene Punkte

1. Primärquellen zu WASP/TECLA/IAAC (Muster, Maße) fehlen; nur Sekundärberichte.
2. Gomaas drei Wandmuster mit Maßen sind unbelegt (Manuskript nicht abrufbar).
3. Kein Beleg für Fugenabstände oder für Wellen als Rissmittel in gedrucktem Lehm. O1 bis O3 sind Hypothesen;
   der Vergleich lebt von der Kennzahl „längste ungestützte gerade Außenstrecke“ und vom späteren Testdruck.
4. Kontaktbreite und Quetschung bei Lehm brauchen Kalibrierung am Gerät (ε-Bereich 0 bis 0,1 offen).
5. Autoren einzelner Quellen (IAARC-Paper, ScienceDirect-Cob-Schwindung, Kuppel-Studie, Stampflehm-Risse) sind nicht
   verifiziert und im Text so markiert.

---

# Teil 2: Sollbruchstellen, Kontrollfugen und Fachwerkwände (Nachtrag R2)

Stand 20.10.2026, nach dem Nutzer-Nachtrag 18:20 (Außenfugen sind Sollbruchstellen, Foto
`referenz/fugenwand-foto.jpg`). Teil 1 bleibt unverändert. Kennzeichnung B, E, A wie oben. Zusätzlich gilt:

- **Im Volltext gelesen:** NZS 4299 und NZS 4298 (beide als öffentliche Konsultationsentwürfe vom April 2024
  geladen und mit `pdftotext` gelesen), Ferretti et al. 2022 (PMC-Volltext, Abschnitte 2.1 bis 3.3) und das
  Weimarer Merkblatt „Stampflehmbau“. Alles andere nur als Abstract, Suchergebnis oder Zusammenfassung.
- **Nicht zugänglich bzw. kostenpflichtig:** Lehmbau Regeln (Dachverband Lehm; die Fassung bei umwelt-online
  zeigt nur ein Demo-Inhaltsverzeichnis), DIN 18940 sowie DIN 18945 bis 18947 (Lehmsteine, Lehmmauermörtel,
  Lehmputz), NZS 4297 (Entwurfstext nicht abrufbar, HTTP 503), ASTM E2392 (nur Katalogseite), Walker et al.
  *Rammed Earth* (BRE 2005) und das Australian Earth Building Handbook HB 195. Für diese Quellen gebe ich
  **keine** Fugenzahlen an; wer sie hat, trägt sie nach.
- **Kernbefund:** Die Regelwerke kennen Kontrollfugen für **zementstabilisierten** Stampflehm, Gusslehm,
  Lehmsteine mit Zementmörtel und Pressziegel; für unstabilisierten Lehm und Cob sind sie **optional** bzw. nicht
  verlangt. Es gibt nach meiner Suche **keinen veröffentlichten Fugenabstand für gedruckte Lehmwände** und keine
  Studie, die eine Fugen- oder Fachwerkwand aus Lehm gegen eine glatte Wand auf Schwindrisse vergleicht. Die
  Zahlen für die Fugenwand sind deshalb Rechnung (E) und Annahme (A); der Testdruck entscheidet.

## 9. Sollbruchstellen, Kontroll- und Dehnfugen im Lehmbau

### 9.1 NZS 4299 (Entwurf 2024), Abschnitt 11 „Control joints“
- **Volle Angabe:** Standards New Zealand: *DZ 4299 Earth buildings not requiring specific engineering design*,
  Public consultation draft, 13. April 2024, Abschnitt 11 (S. 136 bis 139).
  https://consultations.standards.govt.nz/draft-standards/nzs-4299-earth-buildings-not-requiring-specific-en/user_uploads/dz-4299_pc-draft-12-april-2024__4.pdf
  Es ist ein Entwurf; NZS 4299:2024 ist als veröffentlicht gelistet, der Wortlaut kann abweichen. Die
  Vorgängerfassung ist NZS 4299:1998.
- **Kernaussage (B):**
  - 11.1.1: Jede Erdwand außer Adobe, Cob und Mauerwerk mit zementfreiem Mörtel braucht Kontrollfugen in
    Abständen, die sicherstellen, dass auftretende Risse Tragfähigkeit und Gebrauchstauglichkeit nicht gefährden.
    Bei Adobe und Cob ohne Zement- oder Kalkstabilisierung sind Fugen **optional**. Kommentar C11.1.1: Dort
    verteilt sich das Schwinden im Allgemeinen als gleichmäßige Mikrorissbildung.
  - 11.1.2: Vertikale Kontrollfugen **höchstens alle 3,6 m** bei Adobe mit Zement, Pressziegeln, Stampflehm
    und Gusslehm sowie dort, wo das Verhältnis Wandhöhe zu Wandlänge eines Feldes 1:2 überschreitet
    (C11.1.2 nennt niedrige Brüstungsfelder unter breiten Fenstern als rissgefährdet; die Verhältnisangabe ist im
    Entwurf nicht eindeutig formuliert, wir nutzen sie nicht).
  - 11.1.3: Fugen **beidseits jeder Öffnung**, an Höhenstufen, an Dickenwechseln, an beiden Enden eines Sturzes
    und neben Ecken im Abstand der halben Fugenteilung, jedoch **nicht unter 900 mm** vom Außeneck.
    C11.1.3: Fugen zu dicht beieinander oder zu nah an Ecken stören die Kontinuität bzw. den Verband.
  - 11.1.5 bis 11.1.8: Fuge wetterdicht; Kräfte quer zur Wandfläche werden über die Fuge übertragen
    (Verzahnung), jedes Feld darf sich aber ausdehnen und zusammenziehen; waagrechte Bewehrung läuft nicht
    durch die Fuge; je ein Bewehrungsstab beidseits der Fuge.
  - 11.2: Fuge im Stampflehm bzw. Cob als **mechanische Verzahnung** mit einem 25 × 25 mm großen,
    bitumengetränkten, zusammendrückbaren Schaumstreifen über die ganze Wandhöhe; auf beiden Wandseiten
    kann eine **V-Kerbe** ausgebildet werden (Bild 11.2, nur im Text erwähnt). 11.3: Bei Adobe und Pressziegel ist
    die Fuge eine durchgehende, über die ganze Höhe laufende senkrechte Mörtelfuge.
- **Folgerung für die Fugenwand:**
  - Die Fuge geht **über die ganze Höhe** und ist ein Gelenk (Verzahnung), kein Spalt, der die Wand trennt. Das
    ist die senkrechte, stumpf berührende Fuge des Fotos. B/E
  - Die 3,6 m gelten für **zementstabilisierte Stampfwände** und sind für unsere Druckwand nicht übertragbar:
    Unsere Module sind 300 bis 1200 mm lang. Die Norm sagt uns nur, dass durchgehende senkrechte Fugen
    anerkannte Praxis sind; die Zahl ist keine Grundlage. E
  - **Fugen an Laibungen, Stufen, Dickenwechseln, Ecken (11.1.3)** decken sich mit dem M3-Grundsatz (Quersteg an
    jeder künftigen Laibung). Wir legen eine Fuge an jede Laibung, soweit die Feldeinteilung es zulässt. B/A
  - **V-Kerbe auf beiden Seiten und Verzahnung:** Bei uns ergibt sich die Kerbe aus dem Eckradius an der Fuge
    (10.2); die Verzahnung entsteht aus der Raupenrauigkeit und den V-förmigen Stegen. E

### 9.2 NZS 4298 (Entwurf 2024)
- **Volle Angabe:** Standards New Zealand: *DZ 4298 Materials and construction for earth buildings*, Public
  consultation draft, 12. April 2024, Abschnitte 2.14, 3.6, 4.9, 6.7, 7.10.
  https://consultations.standards.govt.nz/draft-standards/nzs-4298-materials-and-construction-for-earth-buil/user_uploads/dz-4298_pc-draft-12-april-2024__1.pdf
- **Kernaussage (B):** 2.14.1 wie 4299 11.1.1 (Verweis auf NZS 4299 Abschnitt 11 für Lage und Ausbildung).
  3.6.1 (Stampflehm): **Risse über 3 mm Breite**, die auf beiden Seiten einer Wandscheibe erscheinen, sind außer an
  vorgesehenen Fugen **nicht zulässig**; Risse unter 3 mm sind unerheblich; an einer vorgesehenen Fuge ist jede
  Rissbreite zulässig. C3.6.1: Ursachen sind zu wenige oder ungeeignete Fugen, schlechte Bauausführung oder örtliches
  Schwinden; viele Risse sind statisch ohne Bedeutung. 6.7 (Cob): Kontrollfugen nicht erforderlich. 7.10 (Gusslehm und
  Ortbau-Adobe): senkrechte Fugen für das horizontale Schwinden, witterungsdicht. 2.12: Zu schnelles Trocknen,
  besonders bei Wind, verursacht übermäßige Rissbildung.
- **Folgerung:**
  - **3-mm-Kriterium als Maßstab für die Fuge.** Sammelt sich das Schwinden eines Feldes in der Fuge, öffnet sie
    sich um (Schwindmaß · Feldlänge): bei 1 % und 240 mm um 2,4 mm, bei 2,76 % (Ferretti, 11.1) um 6,6 mm. Rissbreiten
    bis 3 mm gelten als unerheblich, an Fugen ist **jede** Breite zulässig. Die Rolle der Fuge ist, die Öffnung dorthin
    zu legen, wo sie gewollt ist. E
  - Cob und unstabilisiertes Adobe brauchen laut Norm keine Fugen, weil dort verteiltes Mikroreißen akzeptiert wird.
    Der Nutzer meldet aber Reißen langer gedruckter Wände; die Fuge ist unser Mittel, das Reißen zu **ordnen**. E

### 9.3 NZS 4297 (Entwurf 2024), „Control joints and shrinkage“
- **Volle Angabe:** Standards New Zealand: *DZ 4297 Engineering design of earth buildings*, Public consultation
  draft, 12. April 2024, Abschnitt 2.8.
  https://consultations.standards.govt.nz/draft-standards/nzs-4297-engineering-design-of-earth-buildings/user_uploads/dz-4297_pc-draft_12-april-2024--1-.pdf
- **Kernaussage:** Nur das Inhaltsverzeichnis wurde gesehen (Abschnitt 2.8 „Control joints and shrinkage“, S. 25).
  Der Text war nicht abrufbar. **Keine Zahlen.**

### 9.4 Lehmbau Regeln, DIN 18940 bis 18947, Weimarer Merkblatt
- **Lehmbau Regeln (Dachverband Lehm e. V., niedersächsische Fassung Januar 2019):** Das Inhaltsverzeichnis nennt einen
  Abschnitt zur Ausführung von Stampflehmwänden; der Text war nicht zugänglich. Laut Weimarer Merkblatt (unten) werden
  tragende Stampflehmwände nach den Lehmbau Regeln bemessen, beschränkt auf Gebäude mit zwei Vollgeschossen und
  zwei Wohneinheiten. **Keine Fugenzahl belegt.**
- **Weimarer Merkblatt „Stampflehmbau“** (Bauhaus-Universität Weimar; Autor und Jahr nicht verifiziert; zitiert
  Röhlen, Ziegert 2020, Titel nicht verifiziert), https://www.uni-weimar.de/uploads/tx_showcase/Stampflehmbau.pdf,
  im Volltext gelesen. **Kernaussage (B):** Das **Schwindmaß** von Stampflehm soll nicht mehr als **2 %**, bei
  monolithischen Sichtbauteilen etwa **0,5 %** betragen; tragende Teile mindestens 2 N/mm². Zu hohes Schwindmaß oder
  zu ungleichmäßige und zu schnelle Trocknung führen zu Rissen und Verformungen, zu langsame zu Schimmel. Schmale Risse
  sollen möglichst bei noch feuchter Oberfläche durch Druck auf die Rissufer geschlossen werden, größere nach dem
  Schwinden durch Anfeuchten und Verschließen. (Claytec nennt für sein Produkt 0,5 %; nur als Suchergebnis gesehen.)
- **Folgerung:** Gebaute Stampflehmwände schwinden deutlich weniger als gedruckte Mischungen (Teil 1, 2.3: 3,5 bis
  12 %; Ferretti: 2,76 %). Fugen müssen bei gedrucktem Lehm ein Vielfaches aufnehmen. Der Richtwert 2 % ist als
  **Obergrenze für die Mischung** brauchbar. A
- **DIN 18940 und DIN 18945 bis 18947:** Stoffnormen für Lehmsteine, Lehmmauermörtel und Lehmputz. Nicht lesbar; ich fand
  keine Aussage zu Fugenabständen. Für Lehmsteinwände lieferte die Suche nur Zahlen für gebrannte Ziegel und
  Kalksandstein (Bewegungsfugen grob 6 bis 12 m), die für Lehm nicht gelten. **Nicht verwendet.**

### 9.5 Weitere Hinweise zu Cob, ASTM E2392 und Analogien
- **ASTM E2392/E2392M** (*Standard Guide for Design of Earthen Wall Building Systems*): Anwendungsbereich Adobe,
  Stampflehm, Cob, Gusslehm u. a. Der Inhalt zu Kontrollfugen war nicht zugänglich (nur Katalogseite): **keine
  Aussage**. E2392/E2392M-10(2016) ist als historisch geführt; welche Ausgabe heute gilt, ist offen.
- **US-Cob-Anhang (Kalifornien, Anhang BK):** verlangt eine **Schwindprobe** der Mischung; die Gesamtschwindung über die
  Probenlänge darf **25 mm (1 Zoll)** nicht überschreiten (Suchergebnis, Probenlänge nicht geprüft). Das stützt, über
  die Mischung statt nur über Fugen zu steuern.
- **Analogie Mauerwerk und Beton (nicht Lehm):** NCMA-Hinweis für Betonsteinmauerwerk: Fugen höchstens alle 25 ft
  (7,6 m) bzw. 1,5-fache Wandhöhe, je nachdem was kleiner ist, als geschwächte Stoßfugen, zusätzlich an
  Höhen- und Dickensprüngen sowie neben Öffnungen und Ecken (Suchergebnis, Primärquelle nicht gelesen). Für Betonwände
  nennt ein Forum 3 · h bei h < 8 ft (nicht belastbar). **Nicht für Lehm verwendbar**; nur Hinweis, dass Fugenabstand und
  Wandhöhe gekoppelt sind und Fugen an Querschnittssprüngen liegen. E

## 10. Fugenwand: Folgerungen für Feldlänge, Fugenausbildung und Rückseite

Bezeichnungen: t Wanddicke, w = 30 mm Strangbreite, a Feldlänge (Abstand zweier Fugen einer Seite), θ Winkel des Stegs
gegen die Wandachse (Foto: Stege laufen V-förmig von der Fuge nach innen), s Schwindmaß. Alles E, wenn nicht anders
gekennzeichnet.

### 10.1 Feldlänge a und Fugenöffnung
- Jedes Feld schwindet frei auf beide Fugen zu; die Fuge öffnet sich um **s · a**:

  | Schwindmaß s | a = 200 | a = 240 | a = 300 | a = 450 |
  |---|---|---|---|---|
  | 0,5 % (Merkblatt Weimar, Sichtbauteil) | 1,0 mm | 1,2 mm | 1,5 mm | 2,2 mm |
  | 1 % | 2,0 mm | 2,4 mm | 3,0 mm | 4,5 mm |
  | 2,76 % (Ferretti, gedruckter Lehm) | 5,5 mm | 6,6 mm | 8,3 mm | 12,4 mm |
  | 3,48 % (Zozaya, Teil 1) | 7,0 mm | 8,4 mm | 10,4 mm | 15,7 mm |

  Mit dem 3-mm-Kriterium der NZS 4298 (9.2) bleibt die Fugenöffnung bei s ≤ 1 % und a ≤ 300 mm unter 3 mm; bei
  s = 2,76 % wäre a ≈ 109 mm nötig, was als Zellgröße nicht sinnvoll ist (Stegwinkel zu steil). Schwindet die Mischung
  2,76 %, öffnet sich die Fuge auf 5 bis 8 mm. Sie ist dann sichtbar und muss gefüllt oder bewusst offen gelassen
  werden (NZS 4299: wetterdicht). Das ist ein Ergebnis, kein Fehler.
- Reibung am Fuß hält die Feldenden, die Rechnung ist die Obergrenze. Der Testdruck misst die tatsächliche
  Fugenöffnung. Die Vorschau gibt die Kennzahl „Fugenöffnung“ bei einstellbarem s aus. A
- **Startwert a = 240 mm bei 200 mm Wand.** Er folgt weniger aus der Rissrechnung (a bis 300 mm wäre noch zulässig)
  als aus dem Stegwinkel (10.2): ein größeres a macht θ flach. Bei 300 mm bzw. 365 mm Wand wächst a mit t − 2w.
- **Modulanpassung:** a = L/n mit ganzer Zahl n; für L = 600 mm sind n = 3 (a = 200, θ = 35°) und n = 2 (a = 300,
  θ = 25°) möglich, für L = 1200 mm n = 5 (a = 240). Das entspricht der Auftragsvorgabe „ganze Zahl von Feldern, Rest
  gleichmäßig verteilt“. A

### 10.2 Fugen- und Knotenausbildung
- **Knotenlage:** Berühren sich Vorder- und Rückknoten, liegen ihre Mittellinien im Abstand w (Kontakt nach M2/M7), also
  bei y = t/2 ∓ w/2. Bei der Außenschalen-Mittellinie y = w/2 ergibt das die Steghöhe Δy = (t − 2w)/2 = **70 mm** bei
  200 mm Wand, 120 mm bei 300 mm, 152,5 mm bei 365 mm.
- **Stegwinkel:** tan θ = 2Δy/a = (t − 2w)/a. Für t = 200: a = 140 → 45°, 200 → 35°, 240 → 30,3°, 300 → 25°. Für
  t = 300: a = 240 → 45°, 300 → 38,7°, 415 → 30°. Für t = 365: a = 300 → 45,5°, 450 → 34°. Umgekehrt a_max =
  (t − 2w)/tan θ; bei θ = 30° ist a_max = 242 (200 mm), 416 (300 mm), 528 mm (365 mm).
- **Spitze an der Fuge:** Außenfeld und Steg schließen an der Fuge den Winkel θ ein (Kehre des Strangs um 180° − θ).
  Zwei Raupen mit Mittellinienabstand ≥ (1 − ε)·w = 25,5 mm sind erst ab s = 12,75 mm/sin(θ/2) vom Scheitel getrennt:
  33 mm bei 45°, 49 mm bei 30°, 59 mm bei 25°, 79 mm bei 18,6°. Davor ist die Spitze mit Material gefüllt
  (Überfüllung im Scheitel). Mit Mittellinienradius R beträgt die Tangentenlänge R/tan(θ/2) (56 mm bei R = 15 und
  θ = 30°); an den Tangentenpunkten ist der Mittellinienabstand 2R ≥ 30 mm, M2 ist über R ≥ 15 mm also erfüllt.
  Bei R = 15 mm hat die Kehre keinen Hohlraum (Innenrand der Raupe = Punkt, M6 hart). Folgerung: **θ ≥ 30°** (Spitze
  ≤ 49 mm, Ziel 35° bis 45°) und R = 20 bis 30 mm; die Kehre fährt der Planer langsamer (Überfüllung bei kleinem Radius,
  Teil 1, 3.3). E
- **Fuge außen:** Beide Außenfelder enden mit der Kehre; die Außenränder der zwei Kehren berühren sich am Scheitel
  (stumpf). Die Außenkante hat dadurch eine **Kerbe** der Tiefe ungefähr R + w/2 (R = 15 mm: 30 mm; R = 20 mm: 35 mm). Das
  entspricht der V-Kerbe der NZS 4299 (11.2) und den gerundeten Feldenden im Foto; die Restwanddicke in der Fugenebene
  sinkt um die Kerbtiefe je Seite. E
- **Kontaktlänge an der Fuge klein halten:** Die Raupen berühren sich an der Kehrenspitze auf wenigen Millimetern; die Fuge
  ist ein Gelenk, kein Schweißpunkt. Ein Spalt von 0 bis 5 mm (Parameter) erlaubt, den Kontakt ganz zu lösen. Ob die Fuge
  am Gerät hält oder zu stark verklebt, zeigt der Testdruck. A
- **Knoten innen:** Ferretti (11.1) berichtet **Materialüberschuss an Kreuzungen** (nachgeschliffen); Watson et al. (Teil 1,
  4.2) berichten Überbau an Knoten. Knoten sind die kritische Stelle der Überfüllung. Folgerung: Knoten als Kehre
  (Radius ≥ 15 mm) mit Tangentialkontakt statt Kreuzung; die Pumpe bleibt an (Auftrag), die Geschwindigkeit sinkt. E
- **Gurt:** Die Erstvariante ist ohne Gurt. Ein Gurt auf der Wandmitte läge bei Vorder- und Rückseite auf derselben
  Linie (Doppelraupe, Verstoß gegen M2). Er ist daher nur einseitig oder um w/2 gegeneinander versetzt möglich; dann
  ändert sich Δy um w/2. E

### 10.3 Rückseite gespiegelt oder versetzt
- **Gespiegelt:** Fugen beider Seiten liegen gegenüber; es entsteht eine **durchgehende Sollbruchebene** über die ganze
  Wanddicke. Auch die Knoten liegen gegenüber; Vorder- und Rückknoten bilden mit den Stegen eine **Raute** je Fuge, über
  jedem Feld liegt ein Dreieck bzw. Trapez. Das entspricht dem Foto. Vorteil: eindeutige Rissebene, symmetrisch. Nachteil:
  Die Wand ist dort ein Gelenk; Querlast geht nur über Knoten und Verzahnung (NZS 4299 11.1.6 verlangt Kraftübertragung
  quer zur Wand über die Fuge). E
- **Um a/2 versetzt:** Die Rückfuge liegt gegenüber der Feldmitte der Vorderseite. Keine durchgehende Rissebene; ein Riss
  müsste über die Stege wandern. Vorteil: steifer gegen Querlast. Nachteil: weniger geordnetes Reißen; Vorder- und
  Rückknoten liegen nicht gegenüber, der Kontakt zwischen den Seiten braucht dann eine Gurt- oder Knotenlage außerhalb
  der Mittelebene (10.2). E
- **Empfehlung:** **gespiegelt** als Standard, weil der Auftrag Sollbruchstellen verlangt und die Fuge Risse nur bündelt,
  wenn die Ebene durchläuft; **versetzt** als Variante für Wände mit Querlast. Kennzahl: Anzahl durchgehender
  Fugenpaare. A
- **Modulenden:** Ein Modulstoß ist selbst eine Fuge (Auftrag). Die Endkappe liegt deshalb auf der Fugenlage, dazwischen
  liegen ganze Felder; halbe Felder am Ende (Breite a/2) vermeiden, weil dort θ steil wird und die Spitze kürzer ist als
  der Kehrenradius es zulässt. E

## 11. Gedruckte Fachwerk-, Rauten- und Zellwände

Zu **Lehm** gibt es nur wenige Studien mit offengelegter Infill-Geometrie; zu **Beton und Mörtel** mehr, dort aber mit
anderer Rissursache (Last, nicht Trocknung). Die Übertragung ist unter Vorbehalt.

### 11.1 Ferretti et al. 2022 (Volltext gelesen): ±45°-Gitter in Lehm
- **Volle Angabe:** wie Teil 1, 1.2: Ferretti E., Moretti M., Chiusoli A., Naldoni L., De Fabritiis F., Visonà M. (2022):
  *Mechanical Properties of a 3D-Printed Wall Segment Made with an Earthen Mixture*. Materials 15(2), 438.
  https://doi.org/10.3390/ma15020438 (PMC8778666)
- **Kernaussage (B):** Wandstück 730 × 530 × 504 mm (Länge × Tiefe × Höhe), 42 Schichten à 12 mm, **Düse 30 mm** (also unser
  w), zwei Außenschalen je 34 mm, Infill als regelmäßiges **Gitter aus Geraden unter ±45°**: zehn gleichmäßig verteilte
  Stege von 35 mm Dicke, je fünf unter +45° und −45°, **Abstand der Kreuzungen etwa 150 mm**. Das Infill ragt zur
  Verklammerung um ein Viertel der Schalendicke (68 mm) in die Außenschale und bildet dort **zehn senkrechte Rippen**
  am Außenrand. Frisch zeigte die Seitenfläche Wellen im Rippenabstand; an den Kreuzungen der Schichten gab es
  **Materialüberschuss**, der abgeschliffen wurde. Nach 90 Tagen unter kontrollierten Bedingungen lag das Maß bei
  **97,24 %** der Frischmaße (Schwindung **2,76 %**, gleichmäßig in alle Richtungen; Vergleichswürfel 2,44 %). **Über
  Trocknungsrisse wird nicht berichtet**; die Risse stammen aus der Druckprüfung (2,32 MPa), das Infill hielt die
  Rissausbreitung auf. Die Druckzeit des Stücks ist nicht angegeben.
- **Folgerung:**
  1. Ein gedrucktes Lehmwandstück mit Gitter-Infill (Kreuzungsabstand 150 mm bei 30 mm Düse, also 5 w) trocknete **ohne
     berichtete Trocknungsrisse**. Das ist ein Hinweis (B), kein Beleg für Fugenwirkung, denn es gab keine Vergleichswand
     ohne Infill. Unsere Zellen (Knotenabstand a = 240 mm, Steglänge 139 mm) liegen in derselben Größenordnung. E
  2. Rippen an der Außenhaut entstehen, weil das Infill in die Schale einbindet. Bei uns sind sichtbare Rippen im
     Fugenabstand erwünscht. E
  3. **Materialüberschuss an Kreuzungen** begründet, Kreuzungen durch Kehren mit Berührung zu ersetzen (M2) und die
     Geschwindigkeit an Knoten zu senken. E
  4. Das gleichmäßige Schwinden zeigt, dass das Gitter sich nicht verzieht. Bei der Fugenwand erwarten wir das Schwinden
     dagegen in den Feldern gerichtet. E

### 11.2 Tanapornraweekit et al. 2022: glatte, Rauten- und Karpfenwand aus Mörtel
- **Volle Angabe:** Tanapornraweekit G., Jiramarootapong P., Paudel S., Tangtermsirikul S., Snguanyat C. (2022):
  *Experimental and Numerical Investigation of 3D Printed Mortar Walls Under Uniform Axial Compression*. Construction
  and Building Materials 360, 129552. https://doi.org/10.1016/j.conbuildmat.2022.129552
- **Kernaussage (B, nur Zusammenfassung):** Geprüft wurden glatte (plain), Rauten- (diamond) und Karpfen- (carp) Wände
  unter Axiallast. Rauten- und Karpfenwand versagten durch **Beulen**; die Rautenwand zeigte die höhere Erstrisslast
  und Traglast, das duktilere Verhalten und brauchte weniger Druckzeit und weniger Mörtel. Maße, Winkel und Zellgrößen
  sind in der Zusammenfassung nicht angegeben.
- **Folgerung:** Rautenzellen sind gegenüber glatter Wand material- und tragfähigkeitsgünstig; wir nutzen das nur als
  Hinweis, dass die Raute die richtige Grundform ist (Foto). Das Beulen deutet an, dass dünne Raupen bei großer Steglänge
  seitlich ausweichen: Stegschlankheit L/w begrenzen (a = 240, t = 200: L = 139 mm, L/w = 4,6; ab L/w ≈ 8 am Testdruck
  prüfen). Der Wert 8 ist eine Annahme. E/A

### 11.3 Texas Tech 2026: Tonmodelle 1:5
- **Volle Angabe:** Iyoha P. u. a. (2026): Poster NHW 2026, Texas Tech University (Center of Excellence in Capacity-
  building for Resilient Housing; Vornamen und Autorenliste nicht verifiziert).
  https://www.depts.ttu.edu/cecreh/documentation/nhw-2026-posters/NHW2026_POSTER_PAUL.pdf (nur Suchergebnis, Poster
  nicht gelesen)
- **Kernaussage (B, Zusammenfassung):** An 1:5-Tonmodellen war die Wand „D3T“ schwächer als die stärkste Geometrie, zeigte
  aber ein **allmähliches, kontrolliertes Versagen mit Lastumlagerung**; die konventionelle Wand versagte plötzlich durch
  Delamination. Die Innengeometrie steuere das Tragverhalten. Aussagen zu Trocknungsrissen fehlen.
- **Folgerung:** Gegliederte Innengeometrie versagt gutmütiger. Das stützt die Fugenwand, belegt aber nichts gegen
  Trocknungsrisse. E

### 11.4 WASP / TECLA / Gaia und eine Patentanmeldung
- **Quelle:** Sekundärberichte zu Gaia (WASP): 25 % Schluff vom Ort, 40 % gehäckseltes Reisstroh, 25 % Reishülsen, 10 %
  hydraulischer Kalk; 30 m² Wand, **40 cm dick**, in 10 Tagen gedruckt. https://renewable-carbon.eu/news/?p=143254 und
  https://materialdistrict.com/article/first-3d-printed-house-earth/ (Primärquelle nicht gelesen). Der WASP-Chef führt das
  geringe Schwinden auf die Fasern zurück (Aussage des Unternehmens, nicht gemessen).
- **Kernaussage (B, sekundär):** Gaia ist eine hohle Wand mit wellenförmiger Innengliederung (Teil 1, 1.1). Ein veröffentlichtes
  **Fugen- oder Rautenmuster mit Maßen** habe ich **nicht** gefunden, auch keine Zellgrößen zu TECLA.
- **Folgerung:** Die gedruckte Hohlwand mit Zwischenstegen ist Stand der Praxis; die Fugenwand ist eine Fortentwicklung mit
  Kontakt statt Kreuzung und kann sich auf keine veröffentlichte Maßvorgabe stützen. Die Gaia-Mischung (40 % Stroh) zeigt,
  dass Fasern das wirksame Mittel sind; Fugen senken das Risiko zusätzlich. E
- **US-Patentanmeldung 12168320** („Systems and methods for the construction of structures utilizing additive manufacturing
  techniques“, Anmelder nicht verifiziert, nur Suchergebnis): beschreibt einen Zickzack-Lattice in Wänden mit einem
  durchgehenden Bahnzug, der am selben Punkt beginnt und endet. Keine Maße. Nur Hinweis auf die Einzelstrang-Topologie. E

### 11.5 Euler- und kreuzungsfreie Gitterpfade (Ergänzung zu Teil 1, 4.2)
- **Watson, Barton, Aghaei Meibodi (2026)** (Teil 1, 4.2): Gitter mit **Stegabstand 50 mm bei 25,4 mm Düse** (rund 2 Düsenbreiten)
  in einem Eulerzug; Start und Ende wechseln je Schicht. Ihre Knoten haben Grad 4 (Kreuzung). Unsere Fugenwand hat Knoten
  mit **Berührung**: Jede Fuge und jeder Knoten wird zweimal besucht, ohne dass sich die Richtungen ineinander schieben.
  Die Wand ist ein einziger geschlossener Zug je Schicht (Vorderseite, Endkappe, Rückseite, Endkappe). E
- Zu kreuzungsfreien bzw. durchgehenden Betonpfaden gibt es weitere Arbeiten (Wan et al. 2023, Sahu/Panda 2024 und 2026,
  eine Preprint-Arbeit zu nicht kreuzenden Pfaden); nur als Titel gesehen. **Nicht verwendet.**
- **Folgerung:** Ob die Berührung an den Kehren Material überhäuft, ist die Kernfrage des Testdrucks (11.1). E

### 11.6 Zusammenfassung für die Fugenwand
1. **Fuge stumpf, über die ganze Höhe**, Kerbe aus dem Eckradius; die Fuge ist ein Gelenk (NZS 4299 11.1 bis 11.2). B/E
2. **Feldlänge a = 240 mm bei 200 mm Wand** (160 bis 300 mm für die Parameterstudie), allgemein a = (t − 2w)/tan θ.
   Fugenöffnung s · a wird berichtet. E/A
3. **Stegwinkel θ ≥ 30°** (Ziel 35° bis 45°), sonst füllt sich die Spitze (49 bis 59 mm). Ferretti druckte ±45°. E/B
4. **Knoten:** Kehre mit R ≥ 15 mm (Ziel 20 bis 30), Vorder- und Rückknoten berühren sich auf Mittellinienabstand w, kein
   Gurt auf gemeinsamer Mittellinie. E
5. **Rückseite gespiegelt** als Standard (durchgehende Sollbruchebene), **um a/2 versetzt** als Variante. E/A
6. **Fugen an Laibungen, Stufen, Dickenwechseln und ≥ 900 mm vom Außeneck** (NZS 4299 11.1.3), Modulstoß = Fuge. B/A
7. **Mischung zuerst:** Schwindmaß ≤ 2 % (Merkblatt Weimar) bzw. Fasern (Teil 1, 2.2 bis 2.4). Die Fugenwand ordnet Risse,
   sie verhindert sie nicht. B/E
8. **Offen:** Keine Quelle zu Fugenabständen gedruckter Lehmwände; Ferrettis 150 mm bei ±45° ist der einzige belegte
   Gitterwert in Lehm. Der Testdruck mit zwei Feldlängen (200 und 300 mm) und beiden Rückseiten (gespiegelt, versetzt)
   vergleicht Fugenöffnung, Rissbild und Kontakt der Fuge.

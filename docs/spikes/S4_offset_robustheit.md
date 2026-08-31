# Spike S4 — Offset-Robustheit (liefert Druckbarkeitsregeln für E1-Stufe 2 und Konfigurator)

Status: **grün** (vorläufig, s. Einschränkungen — Zahlen normiert in Strangbreiten,
mm-Werte erst nach Spike S1)

## Frage
Wie verhalten sich shapely-Offsets (`buffer`, negative Distanz) an spitzen Ecken und schmalen Stegen — und welche Druckbarkeitsregeln folgen daraus als konkrete Zahlen?

## Vorgehen
1. Testkonturen bauen: spitze Winkel (60°/45°/30°/15°), schmale Stege (1–3× Strangbreite), enge Innenradien, T-Stöße
2. Innen-Offsets in Strangbreiten-Schritten (`join_style`-Varianten dokumentieren); Degenerationen sammeln: verschwindende Flächen, Selbstüberschneidungen, MultiPolygon-Zerfall
3. Vergleich pyclipper, falls shapely-Artefakte auftreten

## Ergebnis — Druckbarkeitsregeln (Zahlen!)
| Regel | Wert | Quelle |
|---|---|---|
| Mindestinnenradius | 0.5 × Strangbreite | `rounded_corner`-Familie, Schalen k=0..2 |
| Mindeststegbreite | 1.5 × Strangbreite (für 1 Schale; Formel für mehr Schalen s.u.) | `dumbbell`-Familie, Schale k=0 |
| Mindestwinkel ohne Sonderbehandlung | 30° | `wedge`-Familie (konvexe Spitze), Schalen k=0..3 |
| Empfohlener join_style / mitre_limit | `mitre`, `mitre_limit = 2.0` (Produktionsdefault ist aktuell implizit 5.0) | `notch`-Familie (konkave Reflex-Kerbe) |

→ Werte gehen nach `materialcards/process_window.provisional.json` (eine Quelle für E1 **und** Slicer, ADR-013) und später als Constraints in den Konfigurator (ADR-008).

### Begründung je Zahl

- **Mindestinnenradius = 0.5×w:** In der `rounded_corner`-Familie (90°-Reflexecke,
  r = 0/0.25/0.5/1/2/3×w, Wandarme 6×w dick) zeigt bereits der ungerundete Fall
  (r=0) bis Schale k=2 keine Degeneration (`sliver_indicator` weit über der
  Schwelle 0.2, Roundtrip-Flächenverlust < 0.1 %); der Radius selbst hat bei
  diesem (milden) Reflexwinkel kaum Einfluss auf das Offset-Ergebnis. r=0.5×w
  ist der kleinste getestete Wert und entspricht ungefähr der Rundung, die ein
  gedruckter Strang an einer Ecke ohnehin von selbst hat — kleinere Werte sind
  geometrisch kaum sinnvoll abbildbar. **Schale k=3 scheitert bei allen
  Radien** (auch r=3×w) — das ist kein Radius-Effekt, sondern die
  Wandarmdicke der Testkontur (6×w) reicht nur bis inset≈3×w (s. Einschränkungen).
- **Mindeststegbreite = 1.5×w (für 1 Schale):** Die `dumbbell`-Familie
  (Stegbreite 1.0/1.5/2.0/2.5/3.0×w) zeigt exakt das deterministisch erwartete
  Verhalten für einen geraden Steg: er verschwindet, sobald
  `steg_width ≤ 2×inset` — bei steg=1.0×w kollabiert er bereits bei Schale k=0
  (Inset 0.5×w, rechnerisch der exakte Grenzfall, numerisch instabil → schon
  dort MultiPolygon-Zerfall); ab steg=1.5×w übersteht Schale k=0 sauber
  (Roundtrip-Verlust 0 %). Keiner der getesteten Stegbreiten (max. 3.0×w)
  übersteht Schale k≥1 — erwartet, siehe Formel unten. **Formel** (an den
  Messwerten bestätigt, deterministisch für gerade Stege, join_style-unabhängig):
  `min_steg_width(n_shells) ≈ (2·n_shells − 1)×w` zzgl. Sicherheitsmarge, d.h.
  2 Schalen ≥ 3.5×w, 3 Schalen ≥ 5.5×w, 4 Schalen ≥ 7.5×w. Ein Steg ist ein
  lokales Merkmal — er muss nur so viele Schalen tragen, wie an dieser Stelle
  geplant sind, nicht global alle Schalen der Wand.
- **Mindestwinkel ohne Sonderbehandlung = 30°:** In der `wedge`-Familie
  (konvexe Spitze, Innenwinkel 90/60/45/30/15°) bleiben bei 30° alle 4 Schalen
  „ok" (`sliver_indicator` ≥ 0.73, oberhalb der Schwelle 0.2); bei 15°
  kollabiert Schale k=2 zu einem Sliver und k=3 zu leer — natürliches,
  erwartetes Abschneiden der Spitze, kein Artefakt. Konvexe Spitzen zeigen
  dabei **keine** `mitre_limit`-Abhängigkeit (Erosion an konvexen Ecken
  ignoriert `mitre_limit` vollständig — in der Messreihe identische Flächen
  für `mitre_limit` 1/2/5 bei jedem Winkel). Die zusätzlich gebaute
  `notch`-Familie (konkave Reflex-Kerbe — das eigentliche Mitre-Spike-Szenario)
  bleibt unter dem empfohlenen `join_style`/`mitre_limit` bis 15° unauffällig
  (kein Sliver, kein Zerfall, alle 4 Schalen). Die bindende Grenze für
  „Mindestwinkel ohne Sonderbehandlung" kommt also von der **konvexen** Spitze,
  nicht von der konkaven Kerbe.
- **join_style/mitre_limit = mitre / 2.0:** Der Produktionscode
  (`core/src/fgc/slicer/shells.py`) ruft `polygon.buffer(-inset,
  join_style="mitre")` **ohne** `mitre_limit` auf — das ist der
  shapely-Default 5.0. In der `notch`-Familie (konkave Reflex-Kerbe,
  Öffnungswinkel 90/60/45/30/15°) zerfällt die Kontur bei `mitre_limit=5` ab
  Kerbwinkel ≤30° (Schale k=3) bzw. ≤15° (schon ab k=2) in ein **MultiPolygon
  (2 Teile)** — die Mitre-Spitze löst sich als eigene Teilfläche ab, ein
  echtes Topologie-Artefakt (nicht nur Flächenverlust). Mit `mitre_limit=2.0`
  bleibt der Join bis exakt 60° Kerbwinkel unverändert „echtes" Mitre
  (Formel bestätigt: Grenzverhältnis `1/sin(winkel/2) = 2` bei genau 60°),
  fällt darunter automatisch auf bevel-ähnliches Verhalten zurück und bleibt
  im **gesamten** getesteten Bereich (15°–90°, alle 4 Schalen) frei von
  Zerfall/Invalidität — bei nur geringfügig höherem Flächenverlust an sehr
  spitzen Kerben (Maßhaltigkeits-Kompromiss). `mitre_limit=1` wäre noch
  konservativer, entspricht im Testbereich aber praktisch durchgehend Bevel
  (kein Zusatznutzen gegenüber `mitre_limit=2`).

## Einschränkungen / Auffälligkeiten

- **Strangbreite normiert:** Alle Zahlen sind Vielfache von w (Strangbreite
  noch unbekannt, S1 offen), keine mm-Werte. `materialcards/process_window`
  bleibt deshalb `provisional: true`.
- **Produktionsrisiko gefunden:** `core/src/fgc/slicer/shells.py` nutzt
  aktuell `mitre_limit` (implizit 5.0) — genau der Wert, bei dem dieser Spike
  MultiPolygon-Zerfall an scharfen Reflex-Kerben nachweist. Das ist bereits
  über `_as_polygons()` defensiv abgefangen (Zerfall wird zu mehreren Ringen),
  aber die Maßhaltigkeit leidet. **Kein Code-Fix in diesem Spike** (out of
  scope, s. `docs/spikes/s4_scripts/PLAN.md`) — Empfehlung für Folge-Issue:
  `mitre_limit=2.0` explizit setzen.
- **`rounded_corner`-Familie bei k=3 konfundiert:** Wandarmdicke der
  Testkontur (6×w) erlaubt nur Insets bis ≈3×w; Schale k=3 (Inset 3.5×w)
  scheitert dort unabhängig vom Radius — kein Radius-Effekt, siehe oben.
- **`dumbbell`-Familie nicht bis zur Mehrschalen-Grenze getestet:** Getestete
  Stegbreiten (1.0–3.0×w) reichen nur für Schale k=0; die Formel für höhere
  Schalenzahlen ist an den Messwerten für k=0/k=1-Kollaps bestätigt, aber
  nicht empirisch bis in den Bereich >7×w getestet (reine Geradenkontur,
  Formel ist exakte Geometrie, kein Interpolationsrisiko erwartet).
- **Kontrollkontur `wall_segment`:** Zeigt ausschließlich die Klassen `ok` und
  `empty` (kein `invalid`, kein `multipolygon`, kein `sliver`) — sauberes,
  vorhersagbares Verschwinden sobald Inset > halbe Wanddicke, wie erwartet.
  Bestätigt, dass die Sweep-Pipeline selbst keinen Bug hat.
- **pyclipper-Vergleich nicht nötig:** Keine unerklärlichen shapely-Artefakte
  (invalide Geometrie, falsche Topologie) aufgetreten — die einzige
  gefundene „Anomalie" (MultiPolygon-Zerfall bei mitre_limit=5 an scharfen
  Reflex-Kerben) ist durch die Mitre-Geometrie exakt erklärbar, s.o.

## Protokoll

- **Datum:** 2026-07-02
- **shapely-Version:** 2.1.2 (siehe `.venv`)
- **Skripte:**
  - `docs/spikes/s4_scripts/contours.py` — 25 Testkonturen, 6 Familien
    (`wedge`, `notch`, `dumbbell`, `rounded_corner`, `t_joint`,
    `wall_segment`); `notch` wurde gegenüber dem PLAN.md ergänzt, um das
    Mitre-Spike-Szenario (konkave statt konvexe Spitze) direkt zu testen.
  - `docs/spikes/s4_scripts/offset_stress.py` — Sweep über alle Konturen ×
    4 Schalen (k=0..3, Inset = (0.5+k)×w) × 5 join_style/mitre_limit-
    Kombinationen (mitre@1/2/5, round, bevel); schreibt
    `docs/spikes/s4_scripts/out/results.csv` (500 Zeilen) und je Familie ein
    PNG.
- **Abbildungen** (`docs/spikes/s4_scripts/out/`, join_style=mitre/
  mitre_limit=5 zur Referenz, Degenerationen gestrichelt markiert):
  `wedge.png`, `notch.png`, `dumbbell.png`, `rounded_corner.png`,
  `t_joint.png`, `wall_segment.png`
- **Rohdaten:** `docs/spikes/s4_scripts/out/results.csv`

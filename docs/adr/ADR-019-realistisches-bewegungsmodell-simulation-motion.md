# ADR-019 — Realistisches Bewegungsmodell `simulation.motion` (ehrliche Befunde statt stillem Fallback)

Status: angenommen · 2026-07-06 (Issue #62, Scheibe 4 von PRD #57)

## Kontext
Die Simulation (`fgc.simulation`, ADR-012) parametrierte die Zeit bis dahin
**stückweise-konstant**: je Toolpath-Segment eine konstante Gelenkgeschwindigkeit
unter den Achsgrenzen, geprüft nur an den groben Toolpath-Zielen. Zwei Lücken:
(1) das Modell bildete keine Beschleunigungsrampen ab (die reale Bewegung fährt
nicht abrupt auf Geschwindigkeit), und (2) es prüfte die Fahrbarkeit nur an den
Zielen — eine Singularität oder Reichweitengrenze **zwischen** zwei Zielen (mitten
in einer geraden Druckbewegung) blieb unentdeckt. Ein „movel" (kartesisch-lineare
Werkzeugbewegung) verlangt aber, dass die *ganze* Gerade fahrbar ist, nicht nur
ihre Endpunkte.

## Entscheidung
Ein neues, tiefes und isoliert testbares Modul **`fgc.simulation.motion`** bildet
die reale Bewegung ab; `build_trajectory` ruft es auf und die stückweise-konstante
`timeparam.parametrize`-Logik entfällt aus dem Bau (die Helfer für v/a-Nachrechnung
bleiben):

- **Trapez-Geschwindigkeitsprofile** (Rampe/Halt/Bremse), ruhe-zu-ruhe je Segment,
  unter der *eingestellten Beschleunigung*. Ohne Blending (bewusst **Scheibe 4b /
  Issue #63**) hält der Arm an jedem Ziel — das ist ehrlich, nicht optimiert.
- **movel-lineare TCP-Interpolation** für Druck-Ziele: dichte Zwischenposen entlang
  der kartesischen Geraden (Position linear, Orientierung per Slerp), IK je Pose;
  **movej-Gelenkinterpolation** für Travel. Der Bewegungstyp und die Dynamik kommen
  aus `process_params.motion` (Issue #59-Rail).
- **Ehrliche Befunde statt stillem Fallback:** eine einzige `select_along_path`
  (ADR-zu Issue #11) läuft über die *ganze* dichte Bahn und hält die Konfiguration,
  die die Geraden fahrbar lässt. Eine unfahrbare/singuläre **Zwischen**stelle wird
  als **verortete** `meta.warnings` gemeldet (mit ihrer interpolierten Zeit); der
  Arm friert dort auf der letzten gültigen Gelenklösung ein (sichtbar, wie das
  eingefrorene Home aus Issue #66/#56). Es gibt **keinen** stillen Rückfall auf
  Gelenkinterpolation, der die Stelle durch einen Ausweichbogen kaschieren würde —
  das würde eine physisch nicht fahrbare movel-Bewegung als machbar ausgeben.
- **Provisorik markiert (Spike S1):** die kartesischen vel/acc-Grenzen und
  Abtastdichten in `MotionParams` sind `provisional=True`, bis am Gerät gemessene
  Werte vorliegen.

## Verworfene Alternativen
- *Stiller Gelenk-Fallback bei nicht fahrbarer movel-Gerade* (bei einer
  Zwischen-Singularität heimlich auf movej umschalten): verworfen — kaschiert einen
  echten physikalischen Befund und bricht die Zusage „movel = gerade Werkzeugbahn".
- *Fahrbarkeit weiter nur an den Zielen prüfen* (billiger): verworfen — verfehlt
  genau die Zwischen-Singularitäten, um die es geht.
- *Blending/Look-ahead gleich mitliefern:* bewusst auf **Scheibe 4b / Issue #63**
  vertagt, um dieses Slice klein und die Halt-an-jedem-Ziel-Semantik prüfbar zu
  halten.

## Konsequenzen
Die Trajektorie ist dichter (mehrere Samples je movel-Ziel) und — ohne Blending —
langsamer (Stopp an jedem Ziel); der Viewer/Player spielt sie unverändert ab
(ADR-007), `meta.base_frame` (Issue #66) bleibt erhalten. Nicht fahrbare
Druckbewegungen werden sichtbar gemeldet statt geschönt, was die Grundlage für die
Platzierungs-/Zerlegungsschleife schärft. Rückwärtskompatibel: fehlt
`process_params.motion`, gelten die provisorischen Defaults; der CLI-Pfad
`fgc simulate` (ohne Druckjob) läuft unverändert.

## Revisionstrigger
- Spike S1 liefert gemessene vel/acc → Provisorik-Defaults ersetzen.
- Spike S1 vermisst das gerätespezifische Blending → Bézier-Näherung ggf. durch
  controller-echten Kreisbogen/Spline ersetzen (s. Nachtrag).

## Nachtrag 2026-07-06 — Blending (Scheibe 4b / Issue #63)
Die oben bewusst vertagte Ecken-Verrundung ist als **provisorischer Aufsatz**
(Spike S1) ergänzt, ohne die Halt-an-jedem-Ziel-Semantik ohne Radius zu ändern:

- Ein gesetzter `blending_mm` (`process_params.motion`) verrundet Ecken zwischen
  zwei aufeinanderfolgenden **movel**-Bewegungen. Die Ecken-Samples innerhalb des
  Radius werden auf eine **quadratische Bézier-Kurve** (Ecke = Kontrollpunkt,
  `motion.blend_corner`) umgesetzt — die Bahn kürzt die Ecke ab, statt den scharfen
  Wegpunkt exakt anzufahren. Der Radius wird auf die halbe Länge jedes angrenzenden
  Segments gedeckelt (keine Überlappung benachbarter Verrundungsfenster).
- Statt eines **Look-ahead über Segmentgrenzen** (oben angedeutet) wird der
  Geschwindigkeitserhalt durch **Zusammenfassen** der angrenzenden movel-Segmente
  zu **einem** ruhe-zu-ruhe-Trapez über die verkettete Bogenlänge erreicht: die
  Ecke liegt im Profil-Inneren ⇒ Geschwindigkeit dort strikt > 0 (kein Vollstopp),
  Gesamtzeit sinkt. Das ist die einfachere, prüfbare Variante desselben Effekts.
- **Provisorik markiert** (`MotionParams.provisional`): Verrundungsformel (Bézier
  statt Kreisbogen) und Werte sind Annahmen bis S1. movej-Travel-Ecken behalten
  bewusst den Vollstopp. `blending_mm == 0` ⇒ **bit-genau** das Verhalten oben.
- **Verworfen:** Geometrie verrunden, aber je Segment weiter ein eigenes
  ruhe-zu-ruhe-Trapez — die Ecke bliebe ein Vollstopp (Zeit-/Geschwindigkeitseffekt
  verfehlt). Begründung/Alternativen im Design-Log (2026-07-06, #63).

# ADR-023 — Ortsaufgelöste Porosität als Feld über der Wand

Status: **Angenommen** (2026-07-07, Grill zur ortsaufgelösten Porosität)
Kontext-Grill: 2026-07-07 (Design-Log-Eintrag „Grill-Session: Ortsaufgelöste
Porosität (φ-Feld), Infill, LLM-Anbindung kiconnect")

## Kontext

Funktional gradierter Lehmdruck braucht ortsabhängige Porosität: Wandbereiche
(Sockel, Fensterumfeld, …) sollen unterschiedliche Ziel-Porosität φ bekommen,
realisiert über das Mischverhältnis zweier Pumpen am Endeffektor (AOs).
Die Systemarchitektur sah „φ-Feld → V_A/V_B je Segment" vor, implementiert war
nichts: der Slicer schreibt konstante `io`-Werte in jedes Target, `materials/`
ist ein Stub, Spike S1 (AO-Rampen während `movel`) ist offen. Zusätzlich soll
das Feld später aus FEM-Analysen (Ansys) ableitbar und per LLM-Sprachbefehl
beschreibbar sein — das LLM darf dabei nie Geometrie oder DRL direkt erzeugen.

## Entscheidung

1. **Die Porosität trägt ein Feld, nicht der Punkt.** Das **Porositätsfeld
   (φ-Feld)** wird im Wand-Koordinatensystem definiert, unabhängig vom
   Slicing; der Slicer tastet es beim Erzeugen jedes Druckpunkts (Target) ab
   und schreibt das Ergebnis als Kanalwerte ins Target. Re-Slicing mit
   anderen Parametern lässt das Feld unberührt.

2. **Feld = geordnete Liste von Feld-Features** unter einem gemeinsamen
   Interface („φ an Punkt p?"): v1 deklarative Bausteine (Basiswert,
   Box/Zone, Höhenband, Gradient); der Feature-Typ `grid` bleibt im Schema
   reserviert für den späteren FEM-Import (Ansys-Ergebnis → Umrechnungsregel
   → Rastergrid als ein Feature unter demselben Dach).

3. **Kombination im Maler-Modell:** Auswertung in Listenreihenfolge, spätere
   Features überschreiben frühere in ihrem Geltungsbereich.

4. **Features dürfen semantisch referenzieren:** neben absoluten Primitiven
   im Wand-Frame auch Bezüge wie „um Öffnung `<GlobalId>`, Randbreite r" oder
   „Sockel h" — der Core löst sie beim Slicen gegen die Wandgeometrie auf.

5. **Kalibrierung φ → Pumpenwerte lebt in der MaterialCard**
   (`materialcards/`, die eine Quelle, analog Prozessfenster-Karte):
   Stützstellen-Tabelle φ → Anteile (share_a, share_b), linear interpoliert;
   der Slicer rechnet den Gesamt-Volumenstrom aus v_print × Strangquerschnitt
   und teilt ihn nach Anteilen auf. Start `provisional` mit zwei Stützstellen.

6. **Räumliche Auflösung durch Segmentierung, φ stufenweise konstant:** der
   Slicer unterteilt lange Züge auf `phi_target_resolution_mm`
   (Prozessfenster-Karte), je Teilstück eine Feld-Abtastung; der Emitter
   schaltet AOs an den Stückgrenzen (Change-on-Delta existiert). Damit ist
   das Modell unabhängig vom Ausgang von Spike S1; fällt S1 positiv aus,
   sind bahnsynchrone Rampen ein reiner Emitter-Upgrade.

7. **Abgrenzung Mikro/Makro:** das φ-Feld steuert v1 nur die
   Material-Porosität (Pumpen). Geometrische Porosität (**Infill**: Muster,
   Winkel, Linienabstand) ist ein normaler Slice-Parameter im bestehenden
   Override-Mechanismus; feld-gesteuerte Infilldichte ist eine spätere
   Ausbaustufe.

8. **Totzeit:** v1 kompensiert `t_tot` nicht; der erwartete Ortsversatz
   (t_tot × v) wird als Kennzahl ausgewiesen. Kompensation folgt, wenn
   gemessene Werte existieren.

## Alternativen erwogen

- **Punkte tragen φ direkt** (Zuweisung je Target nach dem Slicen) —
  verworfen: Zuordnung stirbt bei jedem Re-Slice, für LLM/Nutzer
  unhandhabbar (tausende Punkte).
- **Voxel-/Rastergrid als einzige Repräsentation** — verworfen: große
  Dateien, nicht editierbar, Auflösung vorab fixiert; als *ein* Feature-Typ
  für FEM-Import bleibt es vorgesehen.
- **Formel/Expression φ(x,y,z)** — verworfen: Parser/Sandbox, schwer zu
  validieren, LLM-Halluzinationen schwer abzufangen.
- **Minimum-gewinnt statt Maler-Modell** — verworfen: gezieltes
  Übersteuern („poröser als FEM-Vorgabe") unmöglich; **gewichtete Mischung**
  — verworfen: Ergebnis am Punkt nicht vorhersagbar.
- **Kennlinie im Endeffektor-Artefakt** — verworfen: das Mischverhältnis ist
  Material-, nicht Werkzeugeigenschaft.
- **Auf Spike S1 warten** — verworfen: blockiert Feld, Viewer und LLM an
  einem Hardware-Termin; stufenweise konstant funktioniert in beiden
  S1-Ausgängen.

## Konsequenzen

- Das φ-Feld persistiert als Teil der `process_params` im Druckjob
  (ADR-016); Änderungen bumpen die Prozess-Revision, Artefakte veralten
  (ADR-017).
- `SliceParams`/Slicer bekommen Feld-Eingang und Zug-Unterteilung; die
  Feld-Auswertung selbst ist reine, testbare Domänenlogik (Feature-Liste →
  φ(p)).
- Das `materials`-Modul bekommt seinen ersten realen Inhalt (MaterialCard
  laden, φ→Anteile interpolieren).
- Der Viewer zeigt φ als Farbkodierung der Targets aus `toolpath.json` —
  reines Abspielen (ADR-007).
- Der LLM-Assistent (PRD #68) kann das Feld später als validierte
  Feature-Liste vorschlagen (Vorschlags-Modus, flüchtig im Chat); er braucht
  Lese-Tools für Wandmaße/Öffnungs-GlobalIds. Kein LLM-Schreibzugriff auf
  Geometrie oder DRL.

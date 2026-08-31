# ADR-016 — Projekt als langlebige Persistenz-Einheit über den Läufen

Status: angenommen · 2026-07-04 (Grill-Session „interaktiver Viewer")

## Kontext

Der geplante GUI-Prozess (Wand wählen → Roboter wählen → Platzierung →
Zerlegung → Simulation) erzeugt einen langlebigen Arbeitsstand: manuelle
Anpassungen an Schnitten und Platzierungen, je Abschnitt eigene Läufe.
Läufe (ADR-004) sind dafür die falsche Einheit — sie sind unveränderliche
Protokolle *einzelner* Pipeline-Aufrufe, kein editierbarer Arbeitsstand.
Der Nutzer will beim GUI-Start gefragt werden, „welches Projekt" er öffnet,
und nach Tagen dort weitermachen, wo er aufgehört hat.

## Entscheidung

Neues Konzept **Projekt**: ein Ordner (z. B. `projects/<name>/`) mit
schema-validiertem `project.json`. Struktur:

- **Projekt** = IFC-Modellpfad + 1..n **Druckjobs**.
- **Druckjob** = eine Wand (GlobalId) + Roboterwahl + Zerlegungsart +
  Abschnitte (Schnittgeometrie) + je Abschnitt eine Platzierung + Verweise
  auf die erzeugten Läufe (Slice, Simulation).
- Läufe bleiben unangetastet die reproduzierbaren Rechen-Artefakte
  (ADR-004); das Projekt ist die veränderliche *Klammer*, die auf sie
  verweist — nie umgekehrt.
- Die Core-API bekommt Projekt-Endpoints (`GET/POST /projects`,
  `PUT /projects/{id}/…`); der Viewer bleibt zustandslos (ADR-007/014):
  der Arbeitsstand liegt in `project.json` auf der Platte, nicht im
  Browser.

Verworfen:

- **Alles in Läufen** (Planungsschritt = neuer Lauf mit Verweis auf den
  Vorgänger): Arbeitsstände sind schwer auffindbar; „Projekt öffnen" hieße
  „richtigen Lauf suchen"; Editieren widerspricht der Unveränderlichkeit
  der Läufe.
- **Browser-Zustand (localStorage):** unsichtbar für CLI/Provenienz, nicht
  teilbar, an den Browser gebunden — widerspricht dem Geist von ADR-004.

## Konsequenzen

- Zweite Persistenz-Einheit neben `runs/` — Schema (`project.schema.json`),
  Versionierung und Migrationspfad müssen gepflegt werden.
- GUI-Start wird Projektliste + „Neues Projekt aus IFC…"; der bisherige
  Direkteinstieg (neuester Übersichts-Lauf) bleibt als Fallback.
- v1-GUI bearbeitet einen Druckjob zur Zeit; das Datenmodell erlaubt von
  Anfang an mehrere Druckjobs je Projekt (mehrere Wände eines Gebäudes).
- CLI-Parität folgt dem bestehenden Muster: Projekt-Operationen als
  Aktionen in `pipeline/actions.py`, die API bleibt dünner Wrapper
  (ADR-014-Leitplanken gelten unverändert).

## Revisionstrigger

Wenn Projekte anfangen, Rechenergebnisse zu *enthalten* statt auf Läufe zu
verweisen (Provenienz-Bypass), oder Mehrbenutzerbetrieb nötig wird, ist der
Zuschnitt neu zu verhandeln.

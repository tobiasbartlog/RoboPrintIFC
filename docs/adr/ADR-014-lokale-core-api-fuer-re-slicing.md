# ADR-014 — Lokale Core-API für Re-Slicing aus dem Viewer

Status: angenommen · 2026-07-02 (Grill-Session) · revidiert ADR-007 teilweise

## Kontext

Slicing-Parameter (Schichthöhe, Strangbreite, Schalenzahl) sollen künftig
direkt im Viewer variiert werden können, statt für jeden Versuch die CLI zu
bemühen. Das kollidiert mit ADR-007 („Viewer ist zustandsloser Abspieler,
rechnet nichts"). ADR-007 und ADR-001 haben genau diesen Fall als
Revisionstrigger vorgesehen: „FastAPI-Wrapper statt Logik im Viewer".
Der Trigger gilt hiermit als ausgelöst.

## Entscheidung

Der Core bekommt eine **lokale HTTP-API** (dünner Wrapper, z. B. FastAPI),
die der Viewer für Re-Slicing aufruft. Leitplanken:

1. **Keine Logik-Duplikation:** Die API ruft dieselben Aktionen wie CLI und
   Wizard (`fgc.pipeline.actions`). Slicing-Logik bleibt in `slicer/`,
   der Viewer rechnet weiterhin nichts selbst.
2. **ADR-004 bleibt unangetastet:** Jeder API-Aufruf (Modell, GlobalId,
   Parameter) erzeugt einen regulären Laufordner mit schema-validierten
   Artefakten inkl. Provenienz. Die Antwort verweist auf den Lauf; der
   Viewer lädt die Artefakte von dort. Jeder Klick im Viewer bleibt damit
   ein reproduzierbar dokumentierter Lauf.
3. **Optionalität:** CLI und Wizard funktionieren weiterhin ohne laufende
   API; die API ist ein zusätzlicher Einstieg, kein Ersatz.

Verworfen: API liefert Artefakte nur in-memory (Provenienz-Lücken — was man
im Viewer sieht, existiert nirgends); Hybrid mit „Lauf speichern"-Knopf
(zwei Codepfade, interessante Läufe gehen verloren).

## Konsequenzen

- ADR-007 gilt eingeschränkt weiter: Der Viewer rendert nur Artefakte und
  hält keinen Fachzustand — neu ist allein, dass er deren Erzeugung über die
  API **anstoßen** darf.
- Es entsteht eine neue Prozessabhängigkeit (lokaler API-Server); Start/Stop
  sollte derselbe Komfortweg übernehmen wie beim Viewer-Dev-Server
  (`fgc start` / Wrapper).
- Umsetzung als eigenes Issue (API + Parameter-UI im Viewer); dieses ADR
  dokumentiert nur die Richtungsentscheidung.

## Revisionstrigger

Wenn die API mehr wird als ein dünner Aktions-Wrapper (eigene Fachlogik,
eigener Zustand, Mehrbenutzerbetrieb), ist der Zuschnitt Core/Viewer neu zu
verhandeln.

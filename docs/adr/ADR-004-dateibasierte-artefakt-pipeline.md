# ADR-004 — Dateibasierte Artefakt-Pipeline

Status: angenommen · 2026-06-10

## Kontext
Reproduzierbarkeit ist wissenschaftliche Anforderung (P2): Jede im Paper gezeigte Konfiguration muss aus einer Datei wiederherstellbar sein.

## Entscheidung
Jeder Pipelineschritt ist einzeln per CLI aufrufbar und liest/schreibt Artefakte in einem Laufordner (`runs/<datum>_<name>/…`). Schemas versioniert in `schemas/`, jedes Artefakt trägt `schema_version` und Provenienzblock (source, created, git_commit).

## Konsequenzen
Etwas Serialisierungs-Boilerplate — bewusst in Kauf genommen. Debugbarkeit: jeder Zwischenstand inspizierbar, auch im Viewer. Batchfähig für Studien.

## Revisionstrigger
Interaktivität mit Latenzanforderung < ~1 s.

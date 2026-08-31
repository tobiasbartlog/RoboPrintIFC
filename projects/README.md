# projects/

Projektordner der GUI (ADR-016). Jeder Unterordner `projects/<slug>/` enthält
ein schema-validiertes `project.json` — die langlebige, editierbare
Persistenz-Einheit über den Läufen.

Ein Projekt = IFC-Modellpfad + 1..n Druckjobs; es **verweist** auf Läufe unter
`runs/` (Übersichts-Lauf, später Slice/Simulation) und enthält nie eingebettete
Rechenergebnisse. Läufe bleiben die unveränderlichen Rechen-Artefakte (ADR-004).

Die einzige Schreibstelle für `project.json` ist das Core-Modul `fgc.project`
(validiert gegen `schemas/project.schema.json`). Die Ordner selbst werden — wie
`runs/` — nicht versioniert.

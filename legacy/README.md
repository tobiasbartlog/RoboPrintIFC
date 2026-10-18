# legacy/ — RoboPrintIFC v1 (nur lesen)

Stand vom Commit `7055bc5` (2026-08-31). Verschoben beim geführten Neustart am 2026-10-18.
Hier liegt die Vorlage zum Portieren nach `core/` und `web/`, und zwar nur über die Liste in
`spec/SPEC.md` §12. Nichts in `core/` oder `web/` importiert aus diesem Ordner.

Der Ordner wird gelöscht, sobald v2 alle Gates besteht und der Nutzer abgenommen hat.

- `core/`: Python-Paket `fgc`, mit Tests
- `viewer/`: TypeScript- und three.js-Viewer
- `schemas/`: JSON-Schemas von v1
- `docs/`: Architektur, Benutzerhandbuch, Design-Log (878 KB, greppen), Reviews
- `scripts/`, `*.cmd`, `setup.sh`: Bootstrap und Startskripte von v1

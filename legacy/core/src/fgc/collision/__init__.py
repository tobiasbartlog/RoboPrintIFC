"""Kollisionskontrolle (ADR-024): Geometrie-Artefakte + Distanzrechnung.

- ``robot_geometry`` (Issue #125): Urteilsgeometrie (VHACD) + Breitphasen-Hülle
  je Glied als versioniertes Artefakt.
- ``check``/``druckstand``/``finding``/``coarse``/``advisor``: FCL-Befund gegen
  den wachsenden Druckstand.
- ``glied_sdf`` (Issue #207, PRD #183 AP 1): statisches Voxel-SDF je Armglied
  (konservativ — Distanz nie überschätzt) als Grundlage des kommenden
  ``SdfObstacleProvider`` (#213).
- ``druckstand_punkte`` (Issue #208, PRD #183 AP 1): der wachsende Druckstand
  als Punktwolke (Anhängen je Schicht, kein Feld-Umbau) plus einmalig
  gesampelte statische Hindernisse (Workstation, Gebäudekontext) — das zweite
  Standbein neben ``glied_sdf`` für den ``SdfObstacleProvider`` (#213).
- ``sdf_provider`` (Issue #213, PRD #183 AP 1): der ``SdfObstacleProvider`` —
  Punkt-gegen-Glied-SDF-Inversion am Hindernis-Provider-Vertrag, FCL bleibt
  exakter Nachprüfer im Grenzband (Befunde byte-identisch zur Referenz).
- ``backend`` (Issue #213): Backend-Schalter FCL↔SDF als injizierbares Modul
  auf App-Ebene (bewusst nicht in ``CollisionConfig``); Altbestand ohne
  SDF-Artefakt fällt soft auf die FCL-Referenz zurück.
"""

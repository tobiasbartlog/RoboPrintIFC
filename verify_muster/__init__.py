"""Unabhaengiges Muster-Orakel (Vorschlag fuer Gate G9, docs/muster/AUFTRAG.md, Regeln M1-M7).

Liest nur Artefakte eines Laufordners (toolpath.json, trajectory.json, part.stl, part.json, optional
das Szenario) und rechnet mit eigener Geometrie (numpy, shapely, trimesh, scipy). Importiert roboprint
nie. Einstieg: `python -m verify_muster.check <laufordner>`; Methoden in verify_muster/README.md.
"""

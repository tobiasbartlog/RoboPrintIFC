# ADR-015 — Neutrales Schnittmodul für den Grundriss

Status: angenommen · 2026-07-03 (Grill-Session)

## Kontext
E1-Stufe 2 soll den Wand-Grundriss gegen die S4-Regeln prüfen
(Mindestradius, Mindeststegbreite). Dafür braucht `eligibility` das
Grundriss-Polygon — den horizontalen Mesh-Schnitt beherrscht heute nur der
Slicer. Die Modultabelle der Architektur (§5) sieht keine Abhängigkeit
`eligibility → slicer` vor; die Pipeline-Reihenfolge (erst prüfen, dann
slicen) stünde quer zur Import-Richtung. Der Filter-Anspruch „volles
IFC-Modell → druckbare Wände" ist Teil des Zielbilds (auch als
Paper-Abbildung), der Check wird also real gebraucht.

## Entscheidung
Der horizontale Mesh-Schnitt wird aus dem Slicer in ein kleines neutrales
Geometrie-Modul extrahiert (z. B. `geometry/section.py`): Mesh + Schnitthöhe
→ Umriss-Polygon(e). `eligibility` und `slicer` hängen beide von diesem
Modul ab, keiner vom anderen. Verworfen: `eligibility` importiert die
Schnitt-Funktion des Slicers direkt (billiger, aber koppelt die
Kandidatenprüfung an das schwerste Modul der Pipeline und verletzt P3).

## Konsequenzen
- Der Slicer wird um den herausgezogenen Schnitt schlanker; seine interne
  `SlicerGeometry`-Schicht (ADR-005) ruft künftig dasselbe Modul.
- Die Modultabelle der Architektur bekommt in v0.2 eine Zeile für das
  Geometrie-Modul (hängt ab von trimesh/shapely/domain, kennt weder
  Eignungslogik noch Pfadplanung).

## Revisionstrigger
Wenn das Modul mehr ansammelt als Schnitt/Umriss-Hilfen (z. B. Offsets,
Pfadlogik), ist es kein neutrales Schnittmodul mehr — dann Zuschnitt neu
verhandeln, bevor es ein zweiter Slicer wird.

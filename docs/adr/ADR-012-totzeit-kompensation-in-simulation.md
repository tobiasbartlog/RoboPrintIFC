# ADR-012 — Totzeit-Kompensation in `simulation`, t_tot im Setup (E3)

Status: angenommen · 2026-07-02 (Grill-Session)

## Kontext
Das φ-Feld soll sich fein **entlang der Bahn** ändern. Damit dominiert nicht die AO-Latenz des Roboters, sondern die Totzeit des Materialsystems (Pumpensignal → Düse, mutmaßlich Sekunden; bei 100 mm/s wären 3 s = 300 mm Versatz). Die Kompensation braucht Zeitinformation, die erst in `simulation` entsteht (Trajectory hat `t_s`, Toolpath ist bewusst zeitfrei).

## Entscheidung
- `t_tot` ist ein **Messwert im Setup-Artefakt** (Eigenschaft des physischen Aufbaus: Schlauchlänge, Förderrate); gemessen in Spike S1/S1b, bis dahin `provisional`.
- `simulation` verschiebt nach der Zeitinterpolation die io-Zeitreihe der Trajectory um −t_tot (`compensation: simulation_shift`); `Trajectory.meta.io_compensated` dokumentiert das.
- Emitter mit nativer Kompensation (KUKA ANOUT-Vorlaufzeit) deklarieren `compensation: native_lookahead` im Setup und erhalten die unverschobenen Werte.
- Der Slicer bleibt zeitfrei: io je Bahnposition, nie je Zeitpunkt.

## Verworfene Alternativen
Räumliches Vorziehen im Slicer (müsste Geschwindigkeitsplanung antizipieren — verletzt Modulgrenze); Kompensation nur in den Emittern (dupliziert Zeitrechnung der Simulation).

## Konsequenzen
Ein Kompensationsweg, ohne Hardware testbar. Spike S1/S1b misst zusätzlich die Übergangslänge (Verschmierung) als minimal erreichbare φ-Auflösung.

## Revisionstrigger
t_tot erweist sich als stark zustandsabhängig (Förderrate, Füllstand) → Kompensation braucht ein Modell statt einer Konstante.

# Spike S1b — KUKA-ANOUT am Gerät (entscheidet OD-2)

Status: **offen** · Roboter: KUKA ___ (Modell/Controller hier eintragen, z. B. KRC4/KRC5)

Symmetrisch zu [S1](S1_doosan_ao.md): gleiche drei Messungen, gleiches Akzeptanzkriterium, gemeinsames Protokollformat. Beide Roboter sind gleichwertige Druckplattformen — OD-2 hat denselben Rang wie OD-1.

## Zusätzlich zu klären (KUKA-spezifisch)
| Frage | Befund |
|---|---|
| `ANOUT ON/OFF` auf dem Controller verfügbar? | |
| Anzahl analoger Kanäle | |
| V_A **und** V_B synchron fahrbar (zwei ANOUT gleichzeitig)? | |
| Vorlaufzeit-Kompensation (`$ANOUT`-Offset) nutzbar? → E3-Modus `native_lookahead` | |
| Programmsplitting nötig (KRC-Größenlimits) ab welcher Zeilenzahl? | |

## Messungen
1. **AO-Latenz** — ANOUT-Rampe während LIN-Bewegung, Spannung am Ausgang messen
2. **System-Totzeit t_tot** — wie S1, Messung 2 (eigener Wert: anderer Aufbau/Schlauchweg!)
3. **Übergangslänge** — wie S1, Messung 3

> Festgelegte Zielauflösung (identisch mit S1): ___ mm bei ___ mm/s

## Auswertung / Entscheidung OD-2
- [ ] ANOUT nutzbar: ja/nein → Segmentierungsstrategie KUKA
- [ ] Nativer Vorlauf nutzbar → Setup `compensation: native_lookahead`, sonst `simulation_shift`
- [ ] Erreichbare Auflösung: ___ mm → Akzeptanzkriterium erfüllt: ja/nein
- [ ] Gemessene Werte in `examples/`-Setup-Vorlage eingetragen

## Protokoll
_(Datum, Aufbau, Rohdaten-Links, Fotos/Videos)_

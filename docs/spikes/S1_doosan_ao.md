# Spike S1 — Doosan-AO am Gerät (entscheidet OD-1)

Status: **offen** · Roboter: Doosan M1013 · Materialsystem: 2 Pumpen (V_A/V_B) + Schaumgenerator, AO-gesteuert

## Frage
Kann DRL analoge Ausgänge bahnsynchron (während `movel`, mit Blending) setzen — und mit welcher effektiven räumlichen Auflösung kommt eine φ-Änderung an der Düse an?

## Akzeptanzkriterium
Erreichbare räumliche Auflösung ≤ **Zielauflösung des φ-Felds entlang der Bahn**.
Zielauflösung provisorisch: **50–100 mm** bei Druckgeschwindigkeit — hier vor Auswertung endgültig festnageln (abgeleitet aus Strangbreite und Demonstrator-Zonierung):

> Festgelegte Zielauflösung: ___ mm bei ___ mm/s

## Messungen

### 1. AO-Latenz (Roboter)
Testprogramm [`s1_programs/s1_ao_ramp.drl`](s1_programs/s1_ao_ramp.drl): Linearbewegung mit AO-Rampe/-Sprüngen. Spannung am Ausgang mit Oszilloskop/Multimeter gegen Programmzeitpunkt messen.

| Messgröße | Wert | Notiz |
|---|---|---|
| Latenz AO-Befehl → Spannung | ___ ms | |
| Granularität (min. Update-Intervall) | ___ ms | |
| Verhalten bei `movel`-Blending (Radius > 0) | | wird der AO-Befehl verschluckt/verzögert? |
| AO-Update während Bewegung möglich (Thread/`set_analog_output` im Motion-Kontext)? | ja/nein | |

### 2. System-Totzeit t_tot (Signal → Düse)
AO-Sprung (z. B. 20 % → 80 % Schaumanteil) bei laufender Förderung; Änderung an der Düse per Video/Farbstoff erfassen.

| Messgröße | Wert | Notiz |
|---|---|---|
| t_tot (Sprung → erste sichtbare Änderung) | ___ s | geht als `deadtime.t_tot_s` ins Setup (ADR-012) |
| Abhängigkeit von Förderrate | | ggf. 2–3 Stützstellen |

### 3. Übergangslänge (Verschmierung)
Wie lang ist der Übergangsbereich zwischen altem und neuem φ an der Düse (kein Sprung, sondern Rampe)?

| Messgröße | Wert | Notiz |
|---|---|---|
| Übergangsdauer | ___ s | |
| → Übergangslänge bei Druckgeschwindigkeit | ___ mm | geht als `deadtime.transition_length_mm` ins Setup; **das ist die minimal erreichbare φ-Auflösung** |

## Auswertung / Entscheidung OD-1
- [ ] Bahnsynchrones AO-Setzen möglich: ja/nein
- [ ] Erreichbare Auflösung: ___ mm → Akzeptanzkriterium erfüllt: ja/nein
- [ ] Konsequenz für Slicer-Segmentierung: …
- [ ] Gemessene Werte in `examples/`-Setup-Vorlage eingetragen

## Protokoll
_(Datum, Aufbau, Rohdaten-Links, Fotos/Videos)_

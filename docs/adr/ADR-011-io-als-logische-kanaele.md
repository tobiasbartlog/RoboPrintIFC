# ADR-011 — IO als logische Kanäle (E2)

Status: angenommen · 2026-07-02 (Grill-Session)

## Kontext
Der ursprüngliche Toolpath-Vertrag fixierte `io: {V_A, V_B}`. Für Motorsteuerung und weitere AOs (zweite Pumpe, Schaumgenerator, später Ventile/DOs) ist das zu eng. Zudem stammte das bekannte Doosan-Problem (falscher Spannungsmodus/Wertebereich aus dem Robots-Postprozessor) aus verstreuter Kanalkonfiguration.

## Entscheidung
Toolpath-Targets führen `io: {kanalname: wert}` mit logischen Namen (`pump_a`, `pump_b`, `foam`, …), Werte default 0..1. Das Setup-Artefakt je Roboter mappt logische Kanäle auf physische: AO-/DO-Index, Modus (`analog_voltage`/`analog_current`/`digital`), physischer Wertebereich. Die Emitter kennen nur dieses Mapping.

## Konsequenzen
Spannungsmodus/Wertebereich sind an genau einer Stelle (Setup) definiert. Die Change-on-Delta-Logik aus dem DRL-Injector wandert als Strategie in den DrlEmitter.

## Revisionstrigger
Kanäle mit nichtlinearer Kennlinie oder Zeitverhalten je Kanal → Mapping wird Funktion statt Bereichspaar.

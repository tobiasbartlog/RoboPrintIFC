# ADR-002 — Kinematik selbst portieren, Robots als Orakel

Status: angenommen · 2026-06-10

## Kontext
Die IK-Solver aus visose/Robots (MIT) decken beide Zielroboter ab: Spherical-Wrist (KUKA), Offset-Wrist (Doosan M1013). Eine Laufzeitabhängigkeit von Robots/RhinoCommon widerspräche dem Headless-Betrieb.

## Entscheidung
Solver nach Python portieren (je ~300–600 Zeilen lineare Algebra). Solverwahl je Roboter vor dem Portieren im Robots-Code verifizieren. Attribution in NOTICE. Robots bleibt Testorakel in Grasshopper (P5).

## Konsequenzen
Validierungspflicht nach ADR-009a (1000-Posen-Roundtrip + Differenzvergleich gegen Robots).

## Revisionstrigger
Roboter mit Kinematik außerhalb beider Solverfamilien (z. B. 7-Achser).

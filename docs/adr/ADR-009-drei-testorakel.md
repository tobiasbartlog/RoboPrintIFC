# ADR-009 — Drei Testorakel

Status: angenommen · 2026-06-10

## Entscheidung
1. **Kinematik (a):** 1000 Zufallsposen, Roundtrip FK→IK→FK mit Toleranzprüfung, plus Differenzvergleich identischer Targets gegen Robots in Grasshopper.
2. **Thermik (b):** 2D-FEM-Stichprobe (stationäre Wärmeleitung, Abaqus/Ansys) für die finalen Pareto-Kandidaten — zugleich Validierungssektion des Papers.
3. **Material (c):** gedruckte Probekörper gegen MaterialCard-Vorhersage.

## Konsequenzen
Die Orakel sind Teil der Definition of Done je Meilenstein: (a) für M1, (b) und (c) für M3.

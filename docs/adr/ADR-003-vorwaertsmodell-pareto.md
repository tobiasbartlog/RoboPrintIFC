# ADR-003 — Vorwärtsmodell + Pareto-Suche statt Inversion

Status: angenommen · 2026-06-10

## Kontext
„Zielwerte → Konfiguration" ist unterbestimmt; analytische Inversion ist weder nötig noch erklärbar.

## Entscheidung
Niedrigdimensionalen Konfigurationsraum (4–6 Parameter) sampeln (Grid oder Latin Hypercube), vorwärts bewerten, als Pareto-Front präsentieren. Festigkeit ist Constraint; U-Wert und Gewicht sind Ziele; Zeit und Kosten sind Berichtgrößen.

## Konsequenzen
Der Konfigurator bleibt trivial testbar und erklärbar (Paper).

## Revisionstrigger
Konfigurationsraum > ~8 Dimensionen oder teure Vorwärtsrechnung (FEM im Loop) → Surrogatmodell oder Optimierer.

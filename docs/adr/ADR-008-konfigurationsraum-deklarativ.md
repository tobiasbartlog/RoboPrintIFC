# ADR-008 — Konfigurationsraum deklarativ

Status: angenommen · 2026-06-10

## Kontext
Studien (Sensitivitätsanalysen, Ablationen) müssen Daten sein, nicht Codeänderungen.

## Entscheidung
Parameterräume, Constraints und Sampling-Strategie stehen in einer YAML-Datei im Laufordner, nicht im Code.

## Konsequenzen
Der Konfigurator liest seinen Raum vollständig aus Daten; Constraints (u. a. aus Spike S4) sind konfigurierbar und versionierbar.

## Revisionstrigger
Keiner bekannt; siehe ADR-003 für Grenzen des Sampling-Ansatzes.

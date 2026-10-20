# UX-Leitbild für `web/`

Das Werkzeug ist für Forschende, Studierende und Hiwis gedacht, die eine Wand drucken wollen, ohne
die Interna zu kennen. Jede Ansicht beantwortet zwei Fragen: **Was ist der Stand?** und **Was ist der
nächste Schritt?**

## Ablauf: vier Schritte

1. **Modell:** Beispiel wählen oder IFC hochladen. Es erscheint eine Wandliste (Name, L × H × D, Eignung
   mit Grund in Klartext), synchron zur 3D-Auswahl.
2. **Zerlegen & prüfen:** Eine Hauptaktion. Sie zerlegt, platziert, plant und prüft jedes Modul im
   Hintergrund. Fortschritt je Stufe und je Modul, Abbrechen möglich. Ergebnis ist ein Raster der
   Module in Wandansicht, gefärbt nach Status, mit Kennzahlen: Anzahl, Druckzeit, kleinster Abstand.
3. **Simulation:** Modul wählen, abspielen. Der Arm steht am Doosantisch, das Modul wächst Schicht für
   Schicht.
4. **Export:** DRL je Modul im Dialekt v2/v3, dazu ein Bericht. Die Annahmen aus SPEC §10 sind sichtbar
   gelistet.

Der Stepper zeigt je Schritt genau einen von drei Zuständen: **fehlt**, **veraltet** oder **aktuell**.
Grün gibt es nur für „aktuell“.

## Kollisionsanzeige

- Die Abstandsfarbe gilt kontinuierlich an **allen** Gliedern und am Werkzeug: grün ≥ d_target,
  gelb darunter, rot < 0. Unerreichbares erscheint grau und schraffiert.
- Bei Kollision oder Warnung:
  - Das Hindernis wird eingeblendet: Druckstand, Tisch oder Boden.
  - Die Kontaktlinie zwischen den Zeugenpunkten wird gezeigt, samt Abstand in mm.
- Die Bahn trägt eine Heatmap des Abstands.
- **Timeline:**
  - Bereichs-Balken für warn, collision und unreachable statt Punkten.
  - eine Spur je Schicht
  - Darunter die Liste „Kollisionen (n)“ mit den häufigsten Ursachen: Glied ↔ Hindernis, Schicht,
    min d.
- Ein Klick auf einen Eintrag **pausiert**, springt zum kritischsten Sample und richtet die Kamera
  auf die Stelle aus.
- Arm, TCP, Druckstand, Strang, Farbe und Zahl folgen derselben Uhr `t`.

## Sprache und Rückmeldung

- Klartext auf Deutsch. ADR- und Issue-Nummern und interne Begriffe wie „Prüf-Tür“ oder „Befund, kein
  Gate“ gehören nicht in die Oberfläche.
- Ein deaktivierter Knopf trägt seinen Grund sichtbar daneben, nicht nur im Tooltip.
- Fehler sind in Nutzersprache formuliert und nennen eine Handlung („Wand ist 24 mm dick, braucht ≥ 60 mm.
  Andere Wand wählen.“). Rohe API-Fehler gehören in ein ausklappbares Detail.
- Warnungen werden verdichtet („12 % der Bahn unerreichbar ab Höhe 310 mm“), nicht als Rohlog.
- Eine zentrale Job-Leiste zeigt laufende Rechnungen mit Fortschritt und Abbrechen.

## Gestaltung

- Mantine-Theme mit Design-Tokens; Farben nur über das Theme, keine Hex-Werte im Code. Hell- und
  Dunkelmodus.
- Wände und Module sind auf jedem Hintergrund klar lesbar: Kontrast der Flächen, Kanten
  hervorgehoben.
- Die 3D-Ansicht ist zentral und groß. Panels liegen seitlich und sind einklappbar. Bis 1280 px Breite
  läuft nichts horizontal über.
- Expertenparameter (§10) liegen in einem eigenen Bereich „Parameter“ mit Einheiten und Defaults.
  Sie sind gegenüber dem Default markiert und lassen sich zurücksetzen.

## Checkliste für den UX-Prüfer (P4)

- [ ] Jeder Schritt hat genau eine hervorgehobene Hauptaktion.
- [ ] Kein Grün ohne erfüllten Zustand. Fehlendes erscheint als „fehlt“.
- [ ] Im Kollisionsmoment sind das Glied rot, das Hindernis sichtbar und die Kontaktlinie mit Zahl
      zu sehen.
- [ ] Die Timeline zeigt Bereiche, die Liste springt und pausiert.
- [ ] Kein Text mit ADR- oder Issue-Nummern, kein Rohfehler ohne Klartext.
- [ ] Jeder deaktivierte Knopf nennt den Grund.
- [ ] Kein horizontaler Überlauf bei 1280 × 800. Hell- und Dunkelmodus sind lesbar.
- [ ] Ein Neuling kommt ohne Handbuch von „Beispiel öffnen“ zum DRL-Download.

# Py↔TS-Parität (geteilte Goldens)

Wie der ADR-009-Paritätsbeweis „Core-Funktion ↔ TS-Zwilling" in diesem Repo
funktioniert — und was bei **jedem neuen Zwilling** zu tun ist. Ein Zwilling
ist jede TS-Funktion im Viewer, die eine Core-Ableitung bit-/toleranzgleich
nachrechnet (Beispiele: `resolveSectionParams`, `nozzleQuat`, `pruefStatus`,
die Präsentations-FK).

## Das Harness (Issue #195)

Der Core ist die Wahrheit; der Beweis läuft über **geteilte Golden-Dateien**
(`viewer/src/**/*.golden.json`), die beide Seiten lesen:

| Teil | Ort |
|---|---|
| **Manifest** (die eine Registratur der Paare) | `core/src/fgc/parity.py` — `register(pair, fn, cases, golden, compare, case_builder=None)` |
| **Gen-Treiber** (schreibt alle Goldens) | `python viewer/scripts/gen_goldens.py [pair …]` (`--list` zeigt die Paare) |
| **pytest-Leser** (Core-Hälfte, EIN Test) | `core/tests/test_parity.py::test_golden[pair]` — parametrisiert über `fgc.parity.MANIFEST` |
| **vitest-Leser** (TS-Hälfte, EIN Helper) | `expectGoldenParity(cases, fn, compare?)` aus `viewer/src/test/golden-parity.ts` |

Erzwungen wird beidseitig:

- Ein **Manifest-Eintrag ohne Golden** (Datei/Block fehlt, leer, Fall-Anzahl
  oder -Namen driften) wird in `test_parity.py` rot.
- Ein **Golden ohne Manifest-Eintrag** wird von
  `test_parity.py::test_every_golden_registered` gefangen.
- Eine **leere Fall-Liste** schlägt auch in `expectGoldenParity` fehl.

## Rezept: Zwilling N+1

1. **Manifest-Eintrag** in `core/src/fgc/parity.py`: Fälle als JSON-fähige
   Dicts definieren, `golden_doc(...)` für eine neue Golden-Datei (bzw. den
   bestehenden Pfad wiederverwenden), dann `register("mein-paar", fn=…,
   cases=…, golden=…)`. `fn(case)` ist die Core-Ableitung; das Default-Skelett
   schreibt `{**case, "expected": fn(case)}` und vergleicht bit-gleich.
2. **Golden erzeugen:** `python viewer/scripts/gen_goldens.py mein-paar`
   (Datei einchecken; Goldens nie von Hand editieren).
3. **TS-Zwillingsfunktion** schreiben/benennen.
4. **3-Zeilen-vitest** daneben:

   ```ts
   import { expectGoldenParity } from "../test/golden-parity";
   import golden from "./mein-paar.golden.json";
   it("reproduziert jeden Core-Fall", () => {
     expectGoldenParity(golden.cases, (c) => meinZwilling(c.input));
   });
   ```

Fertig — `test_parity.py` nimmt das Paar automatisch auf (Parametrisierung
über das Manifest), CI fährt beide Hälften (Jobs `core` und `viewer`).

## Heterogene Paare

Geometrie mit Toleranz oder Konstanten-Blöcke werden **nicht** ins
Standard-Skelett gezwungen:

- eigener `compare(got, case, label)` (z. B. `fk`: Positions-/Quaternion-
  Toleranz) und/oder eigener `case_builder` (z. B. `nozzle-schablone`:
  Posen-Liste je Bahn),
- `cases=None` registriert einen **Konstanten-Block**: der Block ist
  `fn(None)` selbst und wird deep-equal verglichen (z. B.
  `staleness-constants`, die sechs Syncpunkte der Revisions-Familie),
- mehrere Paare können sich **eine** Golden-Datei teilen (eigener `block`,
  z. B. `staleness.golden.json` mit `constants`/`output_cases`/`pruef_cases`).

## Wann registrieren?

Immer, sobald dieselbe Ableitung in Core **und** Viewer existiert — auch für
„triviale" Funktionen. Die Konvention davor degradierte messbar: #74 entstand
am selben Tag **ohne** Golden wie #82 **mit**; #175 wieder ohne. Ein
Manifest-Eintrag kostet Minuten, eine unbemerkte Drift (z. B. die
`last_pruef`-Drift aus #194) kostet eine Diagnose-Session.

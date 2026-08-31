# ADR-017 — veraltet-Markierung über Revisionsstände im Projekt

Status: angenommen · 2026-07-05 (Issue #29, Abschluss PRD #15)

## Kontext

Der GUI-Prozess (Wand → Roboter → Endeffektor → Druckplan → Simulation →
Export) erzeugt nachgelagerte Stände, die von vorgelagerten Eingaben abhängen.
Ändert der Nutzer eine vorgelagerte Eingabe (anderer Roboter, anderer
Endeffektor, andere Wand, editierter Schnittplan), sind die nachgelagerten
Stände (Druckplan, Simulation, Export) fachlich nicht mehr aktuell — aber die
Reiter sind *Navigation, kein Zwangspfad* (viewer/CONTEXT.md), Zurückspringen
und Ändern ist jederzeit erlaubt. Es braucht ein Modell, das inkonsistente
Stände **sichtbar** macht, ohne sie zu löschen (konsistent zu „Befund, kein
Gate", ADR-013) und ohne dass der Viewer Fachliches rechnet (ADR-007).

## Entscheidung

Jeder **Druckjob** trägt im `project.json` **Revisionsstände** (`revisions`):

- `inputs` — ein monoton wachsender Zähler je **Eingabe-Stufe**
  (`wall`, `robot`, `tool`, `cutplan`), erhöht bei jeder Änderung dieser Stufe.
- `outputs` — je **nachgelagerter Stufe** (`druckplan`, `simulation`, `export`)
  der **Schnappschuss** der Eingabe-Zähler zum Zeitpunkt der letzten Erzeugung.

Ein Output ist **veraltet**, wenn eine von ihm *beobachtete* Eingabe-Revision
neuer ist als sein gespeicherter Schnappschuss. Beobachtete Eingaben:
`druckplan` → `wall/robot/tool`; `simulation`/`export` → zusätzlich `cutplan`
(die Zerlegung *erzeugt* den Schnittplan, veraltet also nicht an ihm selbst).

- Das **Setzen** der Revisionen (bump der Eingaben, refresh der Outputs) passiert
  ausschließlich im Core (`fgc.project.revisions`, aufgerufen aus den Aktionen —
  `fgc.project` bleibt die einzige Schreibstelle, ADR-016). Kein Löschen: ein
  Bump markiert nur; die (Neu-)Erzeugung einer Stufe frischt deren Schnappschuss
  auf und hebt die Markierung **stufenweise** auf.
- Die **Ableitung** „ist X veraltet?" ist eine **reine, deterministische
  Funktion** (Viewer: `ui/staleness.ts`, three.js-frei, vitest; Python-Parität:
  `fgc.project.output_status`) — der Viewer zeigt Badges, rechnet nichts
  (ADR-007).

Verworfen:

- **Nachgelagerte Stände löschen** bei Eingabeänderung: verliert Arbeit,
  widerspricht „sichtbar, nicht gelöscht" und „Befund, kein Gate".
- **Zeitstempel-Vergleich** (Output älter als Eingabe): fragil gegenüber Uhr/
  Reihenfolge, nicht deterministisch testbar.
- **Gate** (veralteter Stand sperrt den nächsten Schritt): widerspricht
  „Reiter = Navigation, kein Zwangspfad".

## Konsequenzen

- Zweites Konsistenzmodell neben der Provenienz der Läufe (ADR-004): dort
  *Reproduzierbarkeit einzelner Aufrufe*, hier *Aktualität der Klammer* (ADR-016).
- Additive, rückwärtskompatible Schema-Erweiterung (`print_job.revisions`);
  Altprojekte ohne Feld gelten als nicht veraltet (Default in beiden Ableitungen).
- Neue Prozessstufen müssen ihre Eingabe-Abhängigkeit deklarieren (`OUTPUT_DEPS`
  in Core **und** Viewer synchron halten).

## Revisionstrigger

Wenn Abhängigkeiten zwischen Stufen nicht mehr durch einfache Zähler-Schnappschüsse
abbildbar sind (z. B. partielle Abhängigkeit einzelner Abschnitte statt der
ganzen Stufe) oder Mehrbenutzerbetrieb konkurrierende Bumps erzeugt, ist das
Modell neu zu verhandeln.

## Nachtrag (2026-07-07, Issue #83) — Pro-Abschnitts-Revisionsebene

Der oben unter „Revisionstrigger" antizipierte Fall ist eingetreten: mit der
Gradierungs-Ebene (#82) hängt Simulation/Export nicht mehr an der *ganzen* Stufe,
sondern **partiell je Abschnitt** (ein Abschnitts-Override betrifft nur diesen
Abschnitt). Statt einer Neuverhandlung wird das bestehende Modell **additiv
erweitert** (der Kern — Zähler-Schnappschüsse, reine Ableitung, „sichtbar nicht
gelöscht", einzige Schreibstelle im Core — bleibt unverändert).

**Erweiterung.** `revisions` trägt optional zwei zusätzliche Ebenen:

- `section_inputs` — ein Zähler **je `section_id`**, erhöht bei einer Änderung des
  Abschnitts-Overrides (`process_params.sections[id]`).
- `section_outputs` — je Abschnitt je nachgelagerter, *pro Abschnitt existierender*
  Stufe (`simulation`, `export` — je ein `section_run`/DRL) der Schnappschuss der
  **Job-Eingaben** (dieselben Deps wie global) **plus** des Abschnitts-Zählers
  (Pseudo-Key `section`) zum Zeitpunkt der letzten Erzeugung.

**Ableitung.** `section_output_status(job, id)` (Core) ↔ `sectionStageStatus`
(Viewer): ein Abschnitts-Output ist veraltet, wenn eine beobachtete **Job-Eingabe**
neuer ist (global/strukturell → alle Abschnitte) **oder** der **Abschnitts-Zähler**
neuer ist (nur dieser Abschnitt). So bumpt ein Abschnitts-Override **nur** die
Revision dieses Abschnitts; strukturelle/globale Änderungen (Schnitte `cutplan`,
globale Params `process`, Roboter `robot`, Workstation `workstation`) bumpen weiter
die Job-Eingaben und veralten alle Abschnitte. Der Druckplan bleibt Job-Ebene (der
ganze Plan, nicht pro Abschnitt).

**Rückwärtskompatibilität.** Die Ebene entsteht **lazy** (erste Abschnitts-Änderung/
-Simulation). Fehlt `section_outputs` (Altprojekt / vor der ersten Abschnitts-
Simulation), fällt die Abschnitts-Ableitung auf die **Ganzjob-Veraltung**
(`output_status`) zurück — „verhält sich wie bisher".

**Ablösung des #77-Seams (Workstation).** #77 ließ `workstation` bewusst aus
`INPUT_KEYS` (Seam zu PRD B #70: noch kein Output nutzte die Workstation-Werte).
Seit #80–82 treibt der Druckplan-Automatismus die Workstation-Werte tatsächlich;
darum ist `workstation` jetzt ein Eingabe-Zähler und ein Workstation-Wechsel
veraltet alle Abschnitte. `stand_mode` (#81) bleibt hingegen ohne direkten Bump —
er parametrisiert nur den nächsten `propose`-Lauf (der `cutplan` bumpt).

Getestet: pytest (`section_output_status` — nur-dieser-Abschnitt, global/strukturell
veraltet alle, Legacy = Ganzjob, Integration über `set_process_params`) + vitest
(`sectionStageStatus`) gegen **geteilte Golden-Fälle**
(`viewer/src/ui/staleness-section.golden.json`).

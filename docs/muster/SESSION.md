# Ablauf jeder Session im Nachtlauf „Druckmuster“

Für Start- und Wächter-Sessions. `<KENNUNG>` ist die Kennung aus deinem Prompt (z. B. `w0300`).
Der Nutzer hat für diesen Lauf ausdrücklich Workflows und mehrere Agenten verlangt (ultracode).

## 1. Übernehmen oder beenden (vor allem anderen)
1. `git fetch origin v2/muster v2/strang && git checkout v2/muster` (der Klon steht auf main).
2. `/opt/fgc-venv/bin/python scripts/herzschlag.py pruefen --session <KENNUNG>` (ohne venv: `python3`).
   - Exit 3 (eine andere Session lebt) oder 4 (Lauf fertig): Antworte mit genau einer Zeile und
     beende dich. Kein Setup, kein Commit, kein Push.
   - Exit 0: Du übernimmst und machst mit Abschnitt 2 weiter.

## 2. Einrichtung
1. `CLAUDE_CODE_REMOTE=true CLAUDE_PROJECT_DIR="$(pwd)" bash .claude/hooks/session-start.sh`.
   Python immer über `/opt/fgc-venv/bin/python`.
2. Herzschlag sofort setzen und pushen:
   `/opt/fgc-venv/bin/python scripts/herzschlag.py setzen --session <KENNUNG> --phase <Phase laut MUSTER-PROGRESS.md, sonst M0>`,
   dann `git add MUSTER-PROGRESS.md`, Commit `chore(muster): Herzschlag <KENNUNG>`, `git push origin v2/muster`.
3. Lies `docs/muster/AUFTRAG.md` vollständig. Das ist dein Auftrag. Danach `MUSTER-PROGRESS.md`
   (Aufgabenliste, Protokoll, Einwände), `CLAUDE.md` und die im Auftrag genannten SPEC-Abschnitte.
4. Ist in `MUSTER-PROGRESS.md` noch keine Aufgabe erledigt, beginnst du mit M0. Sonst ist eine
   frühere Session abgebrochen (z. B. am Nutzungslimit): Mach an der ersten offenen Aufgabe weiter.
   Prüfe vorher mit `git log origin/v2/muster` und `git branch -r` (Branches `v2/muster-*`), was
   schon gemergt oder gepusht ist. Halbfertige Worktrees ohne Commit gelten als verloren. Ist es
   nach 09:15 Europe/Berlin, gehst du direkt in M7.

## 3. Arbeit
Arbeite als Orchestrator nach dem Auftrag, Phase für Phase, mit Workflows (fehlt das Workflow-Tool:
Hintergrund-Agenten in Worktrees). Kurzfassung, Details im Auftrag:
- `spec/` und `verify/` änderst du nicht, auch nicht über Worktree-Pfade oder Skripte.
  SPEC-Ergänzungen gehen nach `docs/muster/SPEC-NACHTRAG-MUSTER.md`, das Muster-Orakel nach
  `verify_muster/` (unabhängig, importiert `roboprint` nie).
- Standardwerte bleiben SPEC-konform, Muster sind opt-in. G1–G8 bleiben grün.
- Push nur auf `v2/muster` und `v2/muster-*`. Nie force, nie main, v2-nachtlauf oder v2/strang.
  Conventional Commits, jede Nachricht endet mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Herzschlag mindestens alle 30 min und nach jedem Merge (setzen, commit, push). Vor jeder Phase
  und vor jedem Push `herzschlag.py pruefen --session <KENNUNG>`; bei Exit 3 hörst du sofort auf.
- Lange Läufe startest du im Hintergrund und wartest mit Monitor in Abschnitten von höchstens
  20 min. Beende deinen Zug nie, solange Hintergrundarbeit läuft.
- Höchstens 5 Agenten gleichzeitig, `pytest -n 2`.
- Zeitrahmen Europe/Berlin (`TZ=Europe/Berlin date`): 08:30 Zwischenstand im Morgenbericht,
  09:15 Beginn M7, 10:00 Herzschlag auf `FERTIG`.
- Keine Rückfragen. Weichen kommen mit Empfehlung in `MUSTER-PROGRESS.md` unter „Weichen für den Nutzer“.

Halte die Aufgabenliste in `MUSTER-PROGRESS.md` nach jedem Schritt aktuell, committet und gepusht,
damit ein Wächter ohne deinen Kontext weitermachen kann.

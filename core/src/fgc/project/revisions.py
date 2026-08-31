"""Revisionsstände der Prozessstufen für die veraltet-Markierung (Issue #29).

Die Querschnitts-Konsistenz zwischen den Reitern: ändert sich Vorgelagertes
(Wand, Roboter, Endeffektor, Schnittplan), werden nachgelagerte Stände
(Druckplan, Simulation, Export) als *veraltet* markiert — sichtbar, nicht
gelöscht (viewer/CONTEXT.md). Das Projekt hält dafür je Druckjob **Revisions-
stände**: einen Zähler je Eingabe-Stufe (``inputs``) und je nachgelagerter Stufe
den Schnappschuss der Eingabe-Zähler zum Zeitpunkt der letzten Erzeugung
(``outputs``).

Diese Datei besitzt das **Setzen** der Revisionen (bump/refresh) — reine
Funktionen auf einem Druckjob-Dict, aufgerufen aus ``fgc.project``/den Aktionen
(die einzige Schreibstelle, ADR-016). Die **Ableitung** „ist X veraltet?" ist
bewusst dünn hier gespiegelt (``output_status``, Parität zur reinen TS-Funktion
``ui/staleness.ts``, ADR-007) — der Viewer zeigt, der Core rechnet/schreibt.

Ein Output ist *veraltet* (``"stale"``), wenn eine vorgelagerte Eingabe-Revision
neuer ist als der beim Output gespeicherte Schnappschuss. Fehlt das
``revisions``-Feld (Altprojekte), gilt nichts als veraltet — rückwärtskompatibel,
die Markierung ist Zusatzinfo, kein Gate (ADR-013).

**Pro-Abschnitts-Revisionsebene (ADR-017-Nachtrag, Issue #83).** Ein
Abschnitts-Override (``process_params.sections[id]``, Gradierungs-Ebene #82) soll
**nur** die Simulation/Export *dieses* Abschnitts veralten, nicht die der
Nachbarn. Dafür trägt ``revisions`` optional zwei zusätzliche Ebenen:
``section_inputs`` (ein Zähler je ``section_id``, erhöht bei einer Änderung des
Abschnitts-Overrides) und ``section_outputs`` (je Abschnitt der Schnappschuss der
Job-Eingaben **plus** des Abschnitts-Zählers zum Zeitpunkt der letzten Erzeugung).
Strukturell/global veraltet weiterhin **alles** über die Job-Eingaben (Schnitte →
``cutplan``, globale Params → ``process``, Roboter → ``robot``, Workstation →
``workstation``): eine Job-Eingabe ist Dependency jedes Abschnitts-Outputs, ihr
Bump veraltet alle Abschnitte. Fehlt die Pro-Abschnitts-Ebene (Altprojekt bzw.
vor der ersten Abschnitts-Simulation), gilt Ganzjob-Veraltung wie bisher.
"""

from __future__ import annotations

from typing import Any

#: Die Eingabe-Stufen, deren Änderung Nachgelagertes veralten lässt. ``process``
#: (Prozessparameter, Scheibe 2 / Issue #59) ist die Rail für die Parametergruppen
#: (Slice, später Orientierung/Bewegung): eine Änderung am ``process_params``-Block
#: bumpt diesen Zähler und veraltet Zerlegung/Simulation/Export. ``workstation``
#: (Issue #83, ADR-017-Nachtrag): seit #80–82 treiben die Workstation-Werte
#: (Podesthöhen/Mobilität) den Druckplan-Automatismus tatsächlich — ein
#: Workstation-Wechsel veraltet daher jetzt alle Abschnitte (Ablösung des #77-Seams,
#: siehe Design-Log 2026-07-07).
INPUT_KEYS: tuple[str, ...] = ("wall", "robot", "tool", "cutplan", "process", "workstation")

#: Welche Eingabe-Stufen ein Output beobachtet. Der Druckplan (Platzierung +
#: Zerlegung) hängt an Wand/Roboter/Endeffektor, Workstation und den
#: Prozessparametern; Simulation und Export zusätzlich am Schnittplan (cutplan).
#: Bewusst pro Output deklariert, damit z. B. eine reine Schnittplan-Änderung den
#: Druckplan nicht veraltet (er *erzeugt* den Schnittplan). Die Prozessparameter
#: (``process``) fließen in die Slice-Basisparameter und damit in alle
#: nachgelagerten Stufen.
OUTPUT_DEPS: dict[str, tuple[str, ...]] = {
    "druckplan": ("wall", "robot", "tool", "process", "workstation"),
    "simulation": ("wall", "robot", "tool", "cutplan", "process", "workstation"),
    "export": ("wall", "robot", "tool", "cutplan", "process", "workstation"),
}

#: Pseudo-Dependency für den Pro-Abschnitts-Zähler im Abschnitts-Schnappschuss
#: (``section_outputs[id][stage]["section"]``). Kein Job-Input — er lebt in
#: ``section_inputs`` und wird nur je Abschnitt verglichen.
SECTION_DEP: str = "section"

#: Pseudo-Dependency für die **Summe** aller Pro-Abschnitts-Zähler im Druckplan-
#: Output-Schnappschuss (Issue #172, Wurzel-Fix von #161 — Befunde B16/B32). Der
#: Druckplan ist der *ganze* Zerlegungslauf: eine Platzierungs- oder Abschnitts-
#: Override-Änderung (``bump_section_input``) veraltet ihn, weil der gespeicherte
#: Lauf danach eine überholte Platzierung trägt. Da ``section_inputs``-Zähler nur
#: steigen (nie gelöscht werden), ist ihre Summe monoton — ein Anstieg gegenüber
#: dem Schnappschuss ⇒ veraltet, an der QUELLE (Revisionsmechanik) statt pro Leser
#: (#161-Symptompflege). Kein Job-Input; lebt in ``section_inputs``.
SECTION_AGGREGATE_DEP: str = "section_total"

#: Welche Job-Outputs die Abschnitts-Summe (``SECTION_AGGREGATE_DEP``) beobachten.
#: Nur der **Druckplan** (der ganze Plan) — Simulation/Export sind pro Abschnitt
#: und veralten bereits feingranular über ``section_output_status`` (der jeweils
#: eigene Abschnitts-Zähler), nicht über die Summe fremder Abschnitte.
SECTION_AGGREGATE_OUTPUTS: tuple[str, ...] = ("druckplan",)

#: Die nachgelagerten Stufen, die **pro Abschnitt** existieren (je ein
#: ``section_run`` bzw. eine Export-DRL): Simulation und Export. Der Druckplan ist
#: der ganze Plan (nicht pro Abschnitt) und bleibt Job-Ebene. Jede Stufe beobachtet
#: dieselben Job-Eingaben wie global (``OUTPUT_DEPS``) **plus** den Abschnitts-Zähler.
SECTION_OUTPUT_JOB_DEPS: dict[str, tuple[str, ...]] = {
    "simulation": OUTPUT_DEPS["simulation"],
    "export": OUTPUT_DEPS["export"],
}


#: Die Eingabe-Stufen, deren Änderung den **letzten Prüf-Tür-Stand** (Stufe 2,
#: Issue #175) veralten lässt: dieselben, die auch Slice+Simulation der Prüf-Tür
#: speisen (die Prüf-Tür slict + simuliert je Teil und urteilt gegen den Druckstand).
#: Bewusst **nicht** über die geteilte ``OUTPUT_DEPS`` geführt (das würde die
#: byte-genauen ``output_status``-Verträge der Reiter brechen) — der Prüf-Stand ist
#: ein eigener, additiver Marker (``print_job.last_pruef``), dessen Veraltung hier
#: gespiegelt wird (Parität zur reinen TS-Funktion ``ui/pruef-check-state.ts``).
PRUEF_DEPS: tuple[str, ...] = ("wall", "robot", "tool", "cutplan", "process", "workstation")


def pruef_input_snapshot(job: dict[str, Any]) -> dict[str, int]:
    """Eingabe-Schnappschuss für den letzten Prüf-Tür-Stand (Issue #175).

    Hält die aktuellen Eingabe-Zähler der ``PRUEF_DEPS`` **plus** die Summe der
    Pro-Abschnitts-Zähler (``section_total`` — Platzierungs-/Abschnitts-Overrides
    verschieben die geprüfte Platzierung, #172-Wurzel). Wird beim Abschluss einer
    Prüfung in ``print_job.last_pruef.input_snapshot`` abgelegt; :func:`pruef_status`
    vergleicht ihn gegen die *jetzigen* Zähler.
    """
    parsed = _revisions_of(job)
    snap = {dep: parsed["inputs"][dep] for dep in PRUEF_DEPS}
    snap[SECTION_AGGREGATE_DEP] = sum(parsed["section_inputs"].values())
    return snap


def pruef_status(job: dict[str, Any]) -> str:
    """Zustand des letzten Prüf-Tür-Stands: ``"missing"`` | ``"stale"`` | ``"current"``.

    Reine Ableitung (Parität zu ``ui/pruef-check-state.ts#pruefStatus``, ADR-007):

    - Kein ``last_pruef`` (nie geprüft / Altprojekt) ⇒ ``"missing"`` (= „ungeprüft").
    - ``last_pruef`` **ohne** (oder mit leerem) ``input_snapshot`` ⇒ ebenfalls
      ``"missing"``: ohne Schnappschuss lässt sich Aktualität nicht *beweisen*, ein
      „current" wäre ein stilles Grün (ADR-013). Der TS-Zwilling
      (``ui/pruef-check-state.ts#pruefStatus``) hält diesen Vertrag; die Python-Seite
      trug hier einen Legacy-Fallback (fehlender Schnappschuss = Null-Basis → „current"/
      „stale"), der die Bit-Parität brach (Design-Log 2026-07-13, Issue #194).
    - Eine beobachtete Eingabe (``PRUEF_DEPS``) **oder** die Abschnitts-Summe ist
      neuer als der Schnappschuss ⇒ ``"stale"`` (der letzte Prüfstand ist veraltet —
      sichtbar, nicht gelöscht, #172/#182-Muster).
    - sonst ``"current"``.
    """
    last = job.get("last_pruef")
    if not last or not last.get("input_snapshot"):
        return "missing"
    snap = {k: int(v) for k, v in last["input_snapshot"].items()}
    parsed = _revisions_of(job)
    inputs = parsed["inputs"]
    section_total = sum(parsed["section_inputs"].values())
    if any(inputs[d] > snap.get(d, 0) for d in PRUEF_DEPS):
        return "stale"
    if section_total > snap.get(SECTION_AGGREGATE_DEP, 0):
        return "stale"
    return "current"


def default_revisions() -> dict[str, Any]:
    """Frische Revisionsstände: alle Eingabe-Zähler 0, keine Outputs erzeugt.

    Die Pro-Abschnitts-Ebene (``section_inputs``/``section_outputs``) bleibt hier
    bewusst weg — sie entsteht erst *lazy* mit der ersten Abschnitts-Änderung/
    -Simulation (``bump_section_input``/``refresh_section_output``). So bleibt ihr
    Fehlen das eindeutige Signal für „Altprojekt / vor der ersten Abschnitts-
    Simulation" (Ganzjob-Veraltung, ADR-017-Nachtrag).
    """
    return {"inputs": {k: 0 for k in INPUT_KEYS}, "outputs": {}}


def _revisions_of(job: dict[str, Any]) -> dict[str, Any]:
    """Liest die normalisierten Revisionsstände eines Jobs (Default, falls Feld fehlt)."""
    rev = job.get("revisions") or {}
    inputs_in = rev.get("inputs") or {}
    inputs = {k: int(inputs_in.get(k, 0)) for k in INPUT_KEYS}
    outputs: dict[str, dict[str, int]] = {}
    for name, snap in (rev.get("outputs") or {}).items():
        outputs[name] = {k: int(v) for k, v in (snap or {}).items()}
    section_inputs = {
        str(sid): int(v) for sid, v in (rev.get("section_inputs") or {}).items()
    }
    section_outputs: dict[str, dict[str, dict[str, int]]] = {}
    for sid, outs in (rev.get("section_outputs") or {}).items():
        section_outputs[str(sid)] = {
            name: {k: int(v) for k, v in (snap or {}).items()}
            for name, snap in (outs or {}).items()
        }
    return {
        "inputs": inputs,
        "outputs": outputs,
        "section_inputs": section_inputs,
        "section_outputs": section_outputs,
    }


def _serialize(parsed: dict[str, Any]) -> dict[str, Any]:
    """Baut das persistierte ``revisions``-Dict aus der normalisierten Sicht.

    Die Pro-Abschnitts-Ebene wird nur ausgegeben, wenn sie **belegt** ist — so
    behält ein Altprojekt/frischer Job, der nur Job-Eingaben bumpt, exakt die
    bisherige Form (``{inputs, outputs}``) und das Fehlen der Ebene bleibt das
    Legacy-Signal (ADR-017-Nachtrag).
    """
    rev: dict[str, Any] = {"inputs": parsed["inputs"], "outputs": parsed["outputs"]}
    if parsed["section_inputs"]:
        rev["section_inputs"] = parsed["section_inputs"]
    if parsed["section_outputs"]:
        rev["section_outputs"] = parsed["section_outputs"]
    return rev


def bump_input(job: dict[str, Any], name: str) -> dict[str, Any]:
    """Erhöht den Eingabe-Zähler ``name`` (neuer Job-Dict, ohne Mutation).

    Nach einem Bump sind alle Outputs veraltet, die diese Eingabe beobachten und
    deren Schnappschuss den alten Wert trägt — die Markierung entsteht in der
    Ableitung (``output_status``), nichts wird gelöscht. Eine Job-Eingabe ist
    Dependency **jedes** Abschnitts-Outputs (``SECTION_OUTPUT_JOB_DEPS``): ihr Bump
    veraltet damit auch alle Abschnitte (strukturell/global, Issue #83).
    """
    if name not in INPUT_KEYS:
        raise ValueError(f"Unbekannte Eingabe-Stufe {name!r} — erlaubt: {INPUT_KEYS}.")
    parsed = _revisions_of(job)
    parsed["inputs"][name] += 1
    return {**job, "revisions": _serialize(parsed)}


def refresh_output(job: dict[str, Any], output: str) -> dict[str, Any]:
    """Aktualisiert den Output-Schnappschuss auf die aktuellen Eingabe-Zähler.

    Hebt die veraltet-Markierung dieses Outputs stufenweise auf: nach der
    (Neu-)Erzeugung ist er wieder aktuell gegenüber den *jetzigen* Eingaben.
    Vorgelagerte Bumps, die danach passieren, veralten ihn erneut.
    """
    if output not in OUTPUT_DEPS:
        raise ValueError(f"Unbekannte Output-Stufe {output!r} — erlaubt: {tuple(OUTPUT_DEPS)}.")
    parsed = _revisions_of(job)
    snap = {dep: parsed["inputs"][dep] for dep in OUTPUT_DEPS[output]}
    # Druckplan (Issue #172): zusätzlich die Summe der Abschnitts-Zähler festhalten
    # — nur wenn belegt (byte-gleich zu Altprojekten/Jobs ohne Abschnitts-Override,
    # die Ebene wird sonst nicht geschrieben). Nach der Erzeugung ist der Druckplan
    # gegenüber allen Overrides aktuell; ein späterer Bump veraltet ihn wieder.
    if output in SECTION_AGGREGATE_OUTPUTS and parsed["section_inputs"]:
        snap[SECTION_AGGREGATE_DEP] = sum(parsed["section_inputs"].values())
    parsed["outputs"][output] = snap
    return {**job, "revisions": _serialize(parsed)}


def bump_section_input(job: dict[str, Any], section_id: str) -> dict[str, Any]:
    """Erhöht den Pro-Abschnitts-Zähler ``section_id`` (Issue #83, ADR-017-Nachtrag).

    Ein Abschnitts-Override (``process_params.sections[id]``) bumpt **nur** diesen
    Zähler → nur Simulation/Export *dieses* Abschnitts veralten
    (``section_output_status``); die Nachbarn bleiben aktuell. Erzeugt die
    Pro-Abschnitts-Ebene lazy, falls sie noch fehlt.
    """
    parsed = _revisions_of(job)
    sid = str(section_id)
    parsed["section_inputs"][sid] = parsed["section_inputs"].get(sid, 0) + 1
    return {**job, "revisions": _serialize(parsed)}


def refresh_section_output(job: dict[str, Any], section_id: str, output: str) -> dict[str, Any]:
    """Frischt den Abschnitts-Schnappschuss einer Stufe auf (Issue #83).

    Der Schnappschuss hält die aktuellen **Job-Eingaben** (dieselben Deps wie global,
    ``SECTION_OUTPUT_JOB_DEPS``) **plus** den Abschnitts-Zähler (``section_inputs``)
    fest — so ist der Abschnitt danach aktuell gegenüber globalen *und* seinem
    eigenen Override. Erzeugt die Pro-Abschnitts-Ebene lazy (ihr Vorhandensein
    schaltet die Feingranular-Ableitung frei).
    """
    if output not in SECTION_OUTPUT_JOB_DEPS:
        raise ValueError(
            f"Unbekannte Abschnitts-Output-Stufe {output!r} — "
            f"erlaubt: {tuple(SECTION_OUTPUT_JOB_DEPS)}."
        )
    parsed = _revisions_of(job)
    sid = str(section_id)
    snap = {dep: parsed["inputs"][dep] for dep in SECTION_OUTPUT_JOB_DEPS[output]}
    snap[SECTION_DEP] = parsed["section_inputs"].get(sid, 0)
    parsed["section_outputs"].setdefault(sid, {})[output] = snap
    return {**job, "revisions": _serialize(parsed)}


def output_status(job: dict[str, Any]) -> dict[str, str]:
    """Ableitung je Output: ``"missing"`` | ``"stale"`` | ``"current"``.

    Parität zur reinen TS-Funktion ``ui/staleness.ts`` (deterministisch, ohne
    Seiteneffekt). Fehlt ``revisions`` ganz (Altprojekt), gilt nichts als
    veraltet — jeder Output ``"current"`` (rückwärtskompatibel).
    """
    if not job.get("revisions"):
        return {name: "current" for name in OUTPUT_DEPS}
    parsed = _revisions_of(job)
    inputs = parsed["inputs"]
    result: dict[str, str] = {}
    section_total = sum(parsed["section_inputs"].values())
    for name, deps in OUTPUT_DEPS.items():
        snap = parsed["outputs"].get(name)
        if snap is None:
            result[name] = "missing"
        elif any(inputs[d] > snap.get(d, 0) for d in deps):
            result[name] = "stale"
        elif (
            name in SECTION_AGGREGATE_OUTPUTS
            and section_total > snap.get(SECTION_AGGREGATE_DEP, 0)
        ):
            # Wurzel-Fix #161 (Issue #172, B16/B32): ein Platzierungs-/Abschnitts-
            # Override hat einen Abschnitts-Zähler erhöht, seit der Druckplan zuletzt
            # erzeugt wurde → der ganze Zerlegungslauf ist veraltet.
            result[name] = "stale"
        else:
            result[name] = "current"
    return result


def section_output_status(job: dict[str, Any], section_id: str) -> dict[str, str]:
    """Pro-Abschnitts-Ableitung: ``{"simulation", "export"}`` → Zustand (Issue #83).

    Feingranulare Veraltung (ADR-017-Nachtrag), Parität zur TS-Funktion
    ``ui/staleness.ts#sectionStageStatus``:

    - Fehlt ``revisions`` ganz (sehr altes Projekt) → alles ``"current"``.
    - Fehlt die Pro-Abschnitts-Ebene (``section_outputs`` nicht vorhanden — Altprojekt
      bzw. vor der ersten Abschnitts-Simulation) → **Ganzjob-Veraltung** wie bisher
      (der Abschnittszustand spiegelt ``output_status`` — rückwärtskompatibel).
    - Sonst je Stufe: kein Abschnitts-Schnappschuss → ``"missing"``; veraltet, wenn
      eine beobachtete **Job-Eingabe** neuer ist als der Schnappschuss (global/
      strukturell → alle Abschnitte) **oder** der **Abschnitts-Zähler** neuer ist
      (nur dieser Abschnitt); sonst ``"current"``.
    """
    rev = job.get("revisions")
    if not rev:
        return {name: "current" for name in SECTION_OUTPUT_JOB_DEPS}
    if "section_outputs" not in rev:
        whole = output_status(job)
        return {name: whole[name] for name in SECTION_OUTPUT_JOB_DEPS}
    parsed = _revisions_of(job)
    inputs = parsed["inputs"]
    counter = parsed["section_inputs"].get(str(section_id), 0)
    snaps = parsed["section_outputs"].get(str(section_id), {})
    result: dict[str, str] = {}
    for name, deps in SECTION_OUTPUT_JOB_DEPS.items():
        snap = snaps.get(name)
        if snap is None:
            result[name] = "missing"
        elif any(inputs[d] > snap.get(d, 0) for d in deps) or counter > snap.get(SECTION_DEP, 0):
            result[name] = "stale"
        else:
            result[name] = "current"
    return result

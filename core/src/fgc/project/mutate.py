"""Druckjob-Mutation als eine Tür (Issue #119): Lock/Lookup/Bump/Write an einem Ort.

Jeder reine Druckjob-Setter (``set_tool_for_job``, ``set_workstation_for_job``,
``set_stand_mode_for_job``, ``set_module_limits_for_job``,
``set_placement_override_for_job``, ``set_process_params``, ``select_placement``,
``set_print_job``, ``set_context_check_for_job``) wiederholte in
``pipeline.actions`` **wörtlich dieselbe Choreografie**: ``project_dir_for`` →
``project_lock`` → ``load_project`` → Druckjob suchen (identischer
``ValueError``-Text) → Job in der Liste ersetzen → ``write_project`` → Result mit
``(project_dir, project_path, artifact, job_id)``. Der Unterschied lag jeweils nur
in der **Mutation** und der **Veraltungs-Entscheidung** (Bump ja/nein).

``mutate_print_job`` ist diese eine Choreografie. Die Aktionen schrumpfen auf ihre
Fachlogik: sie übergeben einen **Mutator** ``dict -> JobMutation``, der den Job
verändert und die Veraltungs-Semantik (ADR-017) **deklariert** — seit Issue #199
als **beobachtete Feldpfade** statt fertiger Bump-Tupel: der Seam difft Alt gegen
Neu **einmal** (Diff-dann-bump) und bumpt nur bei tatsächlicher Änderung
(echo-fest); der explizite ``bump_always``-Modus bleibt den Rebuild-Settern
(``set_print_job``, ``reassess_walls_for_robot``), wo ein Diff falsch wäre.
Lock-Verhalten (ADR-018, reentranter ``RLock``), der Job-Lookup-Fehler und die
Schreib-Validierung leben damit an **genau einem** Ort und werden **einmal**
getestet.

``fgc.project`` bleibt die einzige Schreibstelle (ADR-016); ``actions.py`` bleibt
die eine Tür für CLI/API (ADR-014) — sie wird darin nur tiefer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fgc.project.revisions import INPUT_KEYS, bump_input, bump_section_input
from fgc.project.store import (
    load_project,
    project_dir_for,
    project_lock,
    write_project,
)


@dataclass
class JobMutation:
    """Rückgabe eines Druckjob-Mutators (Issue #119/#199): neuer Job + Veraltungs-Deklaration.

    ``job`` ist der vollständig mutierte Druckjob-Dict (ohne Bump — den wendet der
    Seam an). Die Veraltungs-Semantik (ADR-017) wird **deklariert**, nie im Setter
    nachgebaut (Issue #199 — Diff-dann-bump am Seam):

    - ``bump_if_changed`` — Eingabe-Stufe (``INPUT_KEYS``) → beobachtete Feldpfade
      (gepunktet, z. B. ``"process_params.slice"``). Der Seam vergleicht Alt gegen
      Neu je Pfad und bumpt die Stufe nur bei **tatsächlicher Änderung** — jeder
      deklarierende Setter ist damit echo-fest (gleicher Wert bumpt nicht).
      Leer/fehlend zählt als „nicht gesetzt" (``{}``/``[]``/``None`` gleichwertig,
      wie die früheren Hand-Diffs mit ``or None``).
    - ``bump_sections_if_changed`` — **ein** Pfad auf eine section-gekeyte
      Sammlung: ein Dict ``{section_id: Block}`` (``process_params.sections``)
      oder eine Liste von Einträgen mit ``section_id``-Feld
      (``section_overrides``). Der Seam difft je ``section_id`` und bumpt nur die
      Pro-Abschnitts-Zähler **geänderter** Teile (feingranulare Veraltung,
      Issue #83); die Reihenfolge der Listeneinträge ist bewusst egal.
    - ``bump_always`` — Eingabe-Stufen, die **immer** bumpen: der explizite Modus
      der Rebuild-Setter (``set_print_job`` baut den Job neu,
      ``reassess_walls_for_robot`` erzeugt je Aufruf einen frischen Befund-Lauf) —
      dort wäre ein Diff falsch.

    Eine **leere** Deklaration (alle drei ungesetzt) ist die *sichtbare* Aussage
    „BEWUSST kein Bump" (Setter wie ``set_stand_mode_for_job``): der Mutator sagt
    explizit, dass nichts veraltet.

    ``befund`` ist der Rückkanal für Befunde des Mutators (z. B. Payload-/Kompat-
    Befund, der gespeicherte Sparse-Block) — **Befund, kein Gate** (ADR-013). Der
    Seam reicht ihn unverändert im :class:`MutationOutcome` heraus; die Aktion baut
    ihr spezifisches Result daraus.
    """

    job: dict[str, Any]
    bump_always: tuple[str, ...] = ()
    bump_if_changed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    bump_sections_if_changed: str | None = None
    befund: Any = None


@dataclass
class MutationOutcome:
    """Ergebnis von :func:`mutate_print_job`: der geschriebene Stand + Mutator-Befund.

    Trägt den 4-Feld-Kopf, den alle Druckjob-Mutations-Results teilen
    (``project_dir``/``project_path``/``artifact``/``job_id``), plus den vom Mutator
    zurückgegebenen ``befund`` (``None``, wenn keiner). Die Aktion wickelt das in ihr
    öffentliches Result (z. B. ``SetToolResult``).
    """

    project_dir: Path
    project_path: Path
    artifact: dict[str, Any]
    job_id: str
    befund: Any = None


def _job_value(job: dict[str, Any], path: str) -> Any:
    """Wert am gepunkteten Pfad — fehlend oder leer (falsy) einheitlich ``None``.

    Die Normalisierung ``leer == nicht gesetzt`` (``{}``/``[]``/``None``) ist der
    eine Vergleichs-Vertrag des Seams (Issue #199); die abgelösten Hand-Diffs der
    Setter verglichen genauso (``… or None``). Die deklarierten Pfade zeigen auf
    Container/Namen, nie auf skalare 0/False-Werte.
    """
    node: Any = job
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node or None


def _section_values(job: dict[str, Any], path: str) -> dict[str, Any]:
    """Normalisiert die section-gekeyte Sammlung am Pfad zu ``{section_id: Block}``.

    Zwei Formen (Issue #199): ein Dict ``{sid: Block}`` (``process_params.sections``)
    oder eine Liste von Einträgen mit ``section_id``-Feld (``section_overrides`` —
    der Block ist der Eintrag ohne ``section_id``). Leere Blöcke fallen weg
    (derselbe ``leer == nicht gesetzt``-Vertrag wie :func:`_job_value`); die
    Listen-Reihenfolge ist bewusst bedeutungslos.
    """
    coll = _job_value(job, path)
    if isinstance(coll, dict):
        pairs = [(str(sid), block or None) for sid, block in coll.items()]
    elif isinstance(coll, list):
        pairs = [
            (
                str(entry.get("section_id")),
                {k: v for k, v in entry.items() if k != "section_id"} or None,
            )
            for entry in coll
        ]
    else:
        return {}
    return {sid: block for sid, block in pairs if block is not None}


def _apply_declared_bumps(mutation: JobMutation, old_job: dict[str, Any]) -> dict[str, Any]:
    """Diff-dann-bump (Issue #199): wendet die deklarierte Veraltung auf den neuen Job an.

    Vergleicht Alt gegen Neu genau **einmal am Seam** — ``bump_always`` bumpt
    bedingungslos, ``bump_if_changed`` nur bei tatsächlicher Pfad-Änderung
    (echo-fest), ``bump_sections_if_changed`` je geändertem Abschnitt (sortiert,
    deterministisch). Unbekannte Eingabe-Stufen in der Deklaration schlagen sofort
    fehl — auch wenn ihr Pfad (noch) unverändert ist, damit ein Tippfehler nicht
    erst beim ersten echten Wechsel auffliegt.
    """
    for name in (*mutation.bump_always, *mutation.bump_if_changed):
        if name not in INPUT_KEYS:
            raise ValueError(
                f"Unbekannte Eingabe-Stufe {name!r} in der Bump-Deklaration — "
                f"erlaubt: {INPUT_KEYS}."
            )
    updated_job = mutation.job
    for name in mutation.bump_always:
        updated_job = bump_input(updated_job, name)
    for name, paths in mutation.bump_if_changed.items():
        if name in mutation.bump_always:
            continue  # bereits bedingungslos gebumpt
        if any(_job_value(old_job, p) != _job_value(mutation.job, p) for p in paths):
            updated_job = bump_input(updated_job, name)
    if mutation.bump_sections_if_changed is not None:
        old_map = _section_values(old_job, mutation.bump_sections_if_changed)
        new_map = _section_values(mutation.job, mutation.bump_sections_if_changed)
        for sid in sorted(set(old_map) | set(new_map)):
            if old_map.get(sid) != new_map.get(sid):
                updated_job = bump_section_input(updated_job, sid)
    return updated_job


def mutate_print_job(
    slug: str,
    job_id: str,
    mutator: Callable[[dict[str, Any] | None], JobMutation],
    *,
    upsert: bool = False,
    missing_ok: bool = False,
    artifact_updates: dict[str, Any] | None = None,
    projects_dir: Path | None = None,
) -> MutationOutcome:
    """Führt eine Druckjob-Mutation vollständig aus — die eine Tür (Issue #119).

    Serialisiert die ``load_project → mutieren → write_project``-Sektion je Projekt
    über den reentranten ``project_lock`` (ADR-018, Issue #45 — kein Lost Update).
    Sucht den Druckjob ``job_id`` und ruft ``mutator`` mit dem gefundenen Job; danach
    wendet der Seam die vom Mutator **deklarierte** Veraltung an — Diff-dann-bump
    (Issue #199, siehe :class:`JobMutation`) — und schreibt schema-validiert
    zurück (``write_project``).

    ``upsert=False`` (Default): fehlt der Druckjob, wirft der Seam den einheitlichen
    ``ValueError`` „Druckjob … existiert nicht … (set_print_job)" — der Text, den die
    Setter zuvor 14-fach kopiert hatten. Der Mutator sieht in diesem Modus nie
    ``None``. ``upsert=True`` (``set_print_job``): der Mutator wird mit dem
    vorhandenen Job **oder** ``None`` aufgerufen (Anlegen); der neue Job wird ans
    Ende der Liste gestellt (byte-gleich zum bisherigen ``set_print_job``), ein
    gleichnamiger alter Job entfällt.

    ``missing_ok=True`` (``reassess_walls_for_robot``, Issue #199): ein fehlender
    Druckjob ist **kein Fehler** — der Mutator wird dann nicht aufgerufen, die
    Druckjob-Liste bleibt unverändert, geschrieben wird trotzdem (für die
    ``artifact_updates``). ``artifact_updates`` sind Top-Level-Felder des
    Projekt-Artefakts (z. B. ``overview_run``), die der Seam vor dem Schreiben
    einmischt — so laufen auch Setter durch diese Tür, die neben dem Job ein
    Projektfeld pflegen.

    Der Lock ist ein ``RLock``: hält ein Aufrufer bereits den Projekt-Lock (z. B.
    ``suggest_placement`` → ``evaluate_placements``, ADR-018), bleibt der erneute
    Eintritt hier reentrant.

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt (``load_project``);
    ``ValueError`` bei fehlendem Druckjob (nur ``upsert=False`` und ohne
    ``missing_ok``), unbekannter Eingabe-Stufe in der Bump-Deklaration oder einem
    schema-widrigen Projekt (``write_project``). Der Mutator darf zusätzlich eigene
    Fehler werfen (z. B. unbekannte ``option_id``) — sie schlagen unverändert durch.
    """
    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)
        jobs = artifact.get("print_jobs", [])
        existing = next((j for j in jobs if j["job_id"] == job_id), None)
        if existing is None and not upsert and not missing_ok:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        if existing is None and not upsert:
            # missing_ok (Issue #199, reassess_walls_for_robot): kein Druckjob —
            # keine Mutation, aber die artifact_updates werden geschrieben.
            mutation = None
            new_jobs = jobs
        else:
            mutation = mutator(existing)
            updated_job = _apply_declared_bumps(mutation, existing or {})
            if upsert:
                # Anlegen/Überschreiben: gleichnamigen Alt-Job entfernen, neuen ans
                # Ende (byte-gleich zum bisherigen set_print_job: other_jobs + [new_job]).
                others = [j for j in jobs if j["job_id"] != job_id]
                new_jobs = [*others, updated_job]
            else:
                # In-place ersetzen: Position des Jobs in der Liste bleibt erhalten.
                new_jobs = [updated_job if j["job_id"] == job_id else j for j in jobs]

        updated_artifact = {**artifact, **(artifact_updates or {}), "print_jobs": new_jobs}
        path = write_project(project_dir, updated_artifact)

    return MutationOutcome(
        project_dir=project_dir,
        project_path=path,
        artifact=updated_artifact,
        job_id=job_id,
        befund=mutation.befund if mutation is not None else None,
    )

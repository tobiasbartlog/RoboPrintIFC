"""fgc.project — das Projekt als langlebige Persistenz-Einheit (ADR-016).

Dieses Paket ist die *einzige Schreibstelle* für ``project.json``. Es besitzt
das Datenmodell, baut das Artefakt, validiert es gegen ``project.schema.json``
und liest/listet Projekte. Projekte *verweisen* auf Läufe (Übersichts-Lauf,
später Slice/Simulation) — sie enthalten nie eingebettete Rechenergebnisse
(ADR-016). Läufe bleiben die unveränderlichen Rechen-Artefakte (ADR-004); das
Projekt ist die veränderliche Klammer darüber.

Die orchestrierende Aktion „Projekt aus IFC anlegen" (erzeugt den
Übersichts-Lauf und referenziert ihn) lebt in ``pipeline.actions`` — die eine
Tür für CLI und API (ADR-014) —, weil sie ``walls_to_run`` mit diesem Modul
verheiratet.
"""

from __future__ import annotations

from fgc.project.mutate import (
    JobMutation,
    MutationOutcome,
    mutate_print_job,
)
from fgc.project.revisions import (
    INPUT_KEYS,
    OUTPUT_DEPS,
    PRUEF_DEPS,
    SECTION_OUTPUT_JOB_DEPS,
    bump_input,
    bump_section_input,
    default_revisions,
    output_status,
    pruef_input_snapshot,
    pruef_status,
    refresh_output,
    refresh_section_output,
    section_output_status,
)
from fgc.project.store import (
    PROJECT_FILE,
    ProjectSummary,
    list_projects,
    load_project,
    project_artifact,
    project_dir_for,
    project_lock,
    project_slug,
    unique_project_dir,
    write_project,
)

__all__ = [
    "INPUT_KEYS",
    "OUTPUT_DEPS",
    "PROJECT_FILE",
    "PRUEF_DEPS",
    "SECTION_OUTPUT_JOB_DEPS",
    "JobMutation",
    "MutationOutcome",
    "ProjectSummary",
    "bump_input",
    "bump_section_input",
    "default_revisions",
    "list_projects",
    "load_project",
    "mutate_print_job",
    "output_status",
    "pruef_input_snapshot",
    "pruef_status",
    "project_artifact",
    "project_dir_for",
    "project_lock",
    "project_slug",
    "refresh_output",
    "refresh_section_output",
    "section_output_status",
    "unique_project_dir",
    "write_project",
]

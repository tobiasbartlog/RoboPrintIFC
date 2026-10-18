"""Wiederverwendbare Pipeline-Aktionen — gemeinsam genutzt von CLI und Wizard.

Eine Aktion bündelt einen kompletten Pipeline-Schritt (rechnen -> Laufordner
schreiben) hinter einer Funktion, ohne selbst zu drucken oder zu fragen —
Ein-/Ausgabe gehört den Aufrufern (CLI, Wizard, später die lokale API aus
ADR-014).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fgc.collision.finding import CollisionConfig
    from fgc.decompose import DecompositionPlan, ModuleLimits
    from fgc.decompose.pruefung import PruefCache, PruefStats
    from fgc.domain.workstation import WorkstationDef
    from fgc.simulation.motion import MotionParams

from fgc.domain.models import (
    MODEL_GLB_FILE,
    Toolpath,
    WallCandidate,
    candidates_artifact,
    model_map_artifact,
    wall_node_name,
    wallspec_artifact,
)
from fgc.domain.process_params import ProcessWindow, SliceParams
from fgc.domain.robot import RobotDef
from fgc.ifc_io import context as ifc_context
from fgc.ifc_io import walls as ifc_walls
from fgc.ifc_io.walls import WallData
from fgc.pipeline.runfolder import Run
from fgc.pipeline.sectionsim import (
    SectionSimContext,
    clearance_verdict,
    collision_pruef_tuer,
    placement_context_for_job,
    planned_setup,
    section_clearance_check,
    section_collision_finding,
    section_context_geometry,
    section_sim_context,
    slice_and_simulate_section,
)

_LOG = logging.getLogger(__name__)


@dataclass
class _JobArtifactResult:
    """Gemeinsamer 4-Feld-Kopf aller Druckjob-bezogenen Aktions-Ergebnisse (Issue #119).

    ``project_dir``/``project_path`` sind Ordner und geschriebene ``project.json``,
    ``artifact`` das vollständige, schema-validierte Projekt nach dem Schreiben,
    ``job_id`` der betroffene Druckjob. Vor #119 war dieser Kopf in 14 Result-
    Dataclasses byte-gleich kopiert; die spezifischen Results erben ihn jetzt und
    ergänzen nur ihre eigenen Felder (die öffentlichen Typnamen/Felder bleiben
    unverändert — api.py konstruiert per Keyword und liest per Attribut).
    """

    project_dir: Path
    project_path: Path
    artifact: dict
    job_id: str


@dataclass
class SliceRun:
    """Ergebnis eines Slice-Laufs: Laufordner + der erzeugte Toolpath.

    Die Anzeige-Kennzahlen (Schicht-/Target-Zahlen) leiten Aufrufer aus
    `toolpath.summary()` ab — der einen Quelle im Core (siehe
    `report.slice_summary`), statt sie hier erneut zu spiegeln.
    """

    run_dir: Path
    toolpath: Toolpath
    n_context: int  # 0 = kein context.json geschrieben


@dataclass
class EmitDrlRun:
    """Ergebnis eines emit-drl-Laufs: Pfad zur DRL-Programmdatei im Lauf."""

    drl_path: Path
    n_targets: int


@dataclass
class ExportDrlResult(_JobArtifactResult):
    """Ergebnis von `export_section_drl` (Issue #29): DRL je Abschnitt + Projekt.

    ``drl_path`` ist die geschriebene ``program.drl`` im Abschnitts-Lauf (ADR-004,
    Provenienz als Kommentarblock). ``complete`` ist ``True``, wenn ein
    vollständiges Setup vorlag → lauffähiges DRL; sonst ``False`` → sichtbar
    gekennzeichnete Ausgabe (``note`` nennt den Grund/Fehlbestand, ADR-006). Kein
    Gate: die Ausgabe entsteht so oder so, nur gekennzeichnet. ``setup_source``
    benennt die Herkunft **ehrlich** (Issue #136): ``"measured"`` (Antast-Setup im
    Lauf, Art „abschnitt"), ``"none"`` (Antasten fehlt, Art „abschnitt"),
    ``"generated"`` (aus Stammdaten generiert, Art „modul") bzw.
    ``"generated_incomplete"`` (Art „modul", Stammdaten fehlen/provisorisch).
    ``artifact`` ist das project.json nach dem Auffrischen der Export-Revision
    (veraltet-Markierung, Issue #29).
    """

    section_id: str
    run_dir: Path
    drl_path: Path
    complete: bool
    setup_source: str
    note: str
    n_samples: int


#: Kernsatz für den Antasten-Hinweis (ADR-006, core/CONTEXT.md) — ohne gemessenes
#: Setup fehlt das Kanal-Mapping (ADR-011); das DRL bleibt unvollständig.
ANTASTEN_HINT = (
    "Der Export wird erst nach dem Antasten vollständig. Die Platzierung ist ein "
    "Plan — verbindlich wird die Lage erst durchs Antasten (Setup mit gemessenem "
    "Kanal-Mapping, ADR-006/011). Ohne gemessenes Setup fehlt das Kanal-Mapping; "
    "das Bewegungs-/IO-Programm entsteht erst mit dem echten Setup."
)


@dataclass
class SimulateRun:
    """Ergebnis eines Simulate-Laufs: Trajectory-Pfad + Kennzahlen für die Anzeige.

    Die Trajectory wird in denselben Lauf geschrieben, in dem der Toolpath liegt
    (ADR-004): ein Lauf sammelt die Artefakte eines Pipeline-Wegs.
    """

    trajectory_path: Path
    duration_s: float
    n_samples: int
    io_compensated: bool
    n_warnings: int


@dataclass
class PrintJobResult(_JobArtifactResult):
    """Ergebnis von `set_print_job`: aktualisiertes Projekt-Artefakt.

    `job_id` ist der Schlüssel des gesetzten Druckjobs; `artifact` das
    vollständige, schema-validierte project.json nach dem Schreiben.
    """


@dataclass
class SetToolResult(_JobArtifactResult):
    """Ergebnis von `set_tool_for_job`: aktualisiertes Projekt-Artefakt + Payload-Befund.

    `payload_ok` gibt an, ob das Werkzeuggewicht die Traglast des Roboters einhält.
    `payload_margin_kg` ist der Spielraum (negativ = Überschreitung).
    Eignung ist ein **Befund, kein Gate** — auch bei Überschreitung wird gespeichert.
    """

    tool_name: str
    payload_ok: bool | None  # None wenn kein Roboter gesetzt oder Traglast unbekannt
    payload_margin_kg: float | None


@dataclass
class SetWorkstationResult(_JobArtifactResult):
    """Ergebnis von `set_workstation_for_job` (Issue #77): aktualisiertes Projekt + Kompat-Befund.

    `workstation_name` ist die gesetzte Workstation-Wahl; `artifact` das vollstaendige,
    schema-validierte project.json nach dem Schreiben. `compatible` ist der
    Kompatibilitaets-Befund (`domain/compat.is_compatible`) gegen den Roboter des Jobs:
    ``True``/``False`` bzw. ``None`` (kein Roboter gesetzt). **Befund, kein Gate**
    (ADR-013): auch eine inkompatible Workstation wird gespeichert.

    VERALTUNG (Issue #83, ADR-017-Nachtrag): Ein Workstation-Wechsel bumpt jetzt die
    Job-Eingabe ``workstation`` → Druckplan/Simulation/Export und alle Abschnitte
    veralten. Das loest den urspruenglich in #77 bewussten Verzicht (Seam zu #70) ab,
    weil der Konsument der Workstation-Werte (der Druckplan-Automatismus, #80–82) nun
    existiert.
    """

    workstation_name: str
    compatible: bool | None  # None wenn kein Roboter im Job gesetzt


@dataclass
class SetStandModeResult(_JobArtifactResult):
    """Ergebnis von `set_stand_mode_for_job` (Issue #81): aktualisiertes Projekt.

    `stand_mode` ist der gesetzte Aufstell-Toggle (`floor`|`elevated`); `artifact`
    das vollstaendige, schema-validierte project.json nach dem Schreiben.

    Wie der Workstation-Wechsel (#77) bumpt der Toggle **keine** Eingabe-Revision:
    er begrenzt nur, welche Podesthoehen die Abschnittssuche nutzen darf; die
    Neubewertung stoesst der Druckplan explizit ueber `propose_decomposition` an
    (ADR-007) — dieser Aufruf ist die Neubewertung, er bumpt dort ``cutplan``.
    """

    stand_mode: str


@dataclass
class SetContextCheckResult(_JobArtifactResult):
    """Ergebnis von `set_context_check_for_job` (Issue #131): aktualisiertes Projekt.

    `check_building_context` ist der gesetzte Gebaeudekontext-Schalter der
    Kollisionskontrolle (bool); `artifact` das vollstaendige, schema-validierte
    project.json nach dem Schreiben.

    Wie der Aufstell-Toggle (#81) bumpt der Schalter **keine** Eingabe-Revision:
    er wirkt erst bei der naechsten Simulation (ADR-024) — bei „ein" prueft die
    Simulation den Arm zusaetzlich gegen den Gebaeudekontext (context.json), bei
    Zerlegungsart Modul ist er gegenstandslos (ADR-022).
    """

    check_building_context: bool


@dataclass
class SetModuleLimitsResult(_JobArtifactResult):
    """Ergebnis von `set_module_limits_for_job` (Issue #90): aktualisiertes Projekt.

    `module_limits` ist der tatsaechlich gespeicherte sparse Block (nur gesetzte
    Grenzen; leer = keine Obergrenzen, Feld entfernt); `artifact` das
    vollstaendige, schema-validierte project.json nach dem Schreiben.

    Wie der Aufstell-Toggle (#81) bumpen die Obergrenzen **keine**
    Eingabe-Revision: sie parametrieren nur den naechsten
    `propose_decomposition`-Aufruf (der bumpt dort ``cutplan``, ADR-007).
    """

    module_limits: dict


@dataclass
class SetObjectiveResult(_JobArtifactResult):
    """Ergebnis von `set_objective_for_job` (Issue #212, PRD #183 Stufe 3).

    `objective` ist die **wirksame** Zielfunktions-Config nach dem Schreiben
    (Lesart + Gewichte, immer vollstaendig belegt — auch wenn der Druckjob den
    Default sparse traegt, d. h. ohne ``objective``-Feld); `artifact` das
    vollstaendige, schema-validierte project.json.

    Anders als die reinen Parametrier-Setter (#81/#90) deklariert dieser Setter
    Veraltung: eine **tatsaechliche** Aenderung der Zielfunktion bumpt die
    Eingabe-Stufe ``cutplan`` (echo-fest via ``bump_if_changed``, #199) — ein
    unter der alten Zielfunktion gesuchter Zerlegungsplan ist danach ehrlich
    „veraltet" (ADR-017), sobald die Beam-Suche (#217) die Config konsumiert.
    """

    objective: dict


@dataclass
class SetPlacementOverrideResult(_JobArtifactResult):
    """Ergebnis von `set_placement_override_for_job` (Issue #94): aktualisiertes Projekt.

    `override` ist der tatsaechlich gespeicherte sparse Eintrag des Teils (nur
    gesetzte freie Felder, ggf. plus bestehender `option_id`-Referenz); leer =
    Override entfernt, das Teil kehrt zur automatischen Platzierung zurueck.
    `artifact` ist das vollstaendige, schema-validierte project.json nach dem
    Schreiben.

    VERALTUNG (#83-Mechanik, Diff am Seam seit #199): eine tatsaechliche Aenderung
    bumpt NUR den Pro-Abschnitts-Zaehler dieses Teils — nur seine
    Simulation/sein Export veralten, die Nachbarn bleiben aktuell. Die
    Neubewertung (Ampel/erreichbar %/Marge) stoesst der Druckplan wie ueblich
    ueber ``propose_decomposition`` an (ADR-007).
    """

    section_id: str
    override: dict


@dataclass
class SetProcessParamsResult(_JobArtifactResult):
    """Ergebnis von `set_process_params` (Scheibe 2, Issue #59): aktualisiertes Projekt.

    `slice_params` ist der tatsächlich gespeicherte Slice-Block (nur gesetzte
    Felder; leer, wenn zurückgesetzt); `artifact` das vollständige, schema-validierte
    project.json nach dem Schreiben. Die Änderung hat die `process`-Revision gebumpt
    (Zerlegung/Simulation/Export veralten, ADR-017).
    """

    slice_params: dict


@dataclass
class CreateToolResult:
    """Ergebnis von `create_tool_from_upload` (Issue #28): abgelegter Endeffektor.

    `tool_path` ist die geschriebene `<name>.json`, `mesh_path` die abgelegte
    Mesh-Datei — beide im Tools-Verzeichnis (Stammdaten, ADR-016/CONTEXT). `tool`
    ist die geladene, schema-valide `ToolDef` (der Aufrufer reicht sie ohne
    Nachladen an den Katalog weiter). Das Tools-Verzeichnis ist die eine Ablage;
    `GET /tools` findet den neuen Endeffektor sofort (kein Neustart).
    """

    tool_dir: Path
    tool_path: Path
    mesh_path: Path
    tool_name: str
    tool: object  # fgc.domain.tool.ToolDef (kein Import zur Vermeidung von Zirkeln)


@dataclass
class ReassessResult(_JobArtifactResult):
    """Ergebnis von `reassess_walls_for_robot`: aktualisiertes Projekt + neuer Befund-Lauf.

    `new_run_dir` ist der Laufordner des neu erzeugten Befund-Laufs (walls-list);
    `artifact` ist das vollständige, schema-validierte project.json nach dem Schreiben.
    """

    new_run_dir: Path


@dataclass
class ProjectCreation:
    """Ergebnis von `create_project_from_ifc`: Projektordner + project.json + Übersichts-Lauf.

    `overview_run_dir` ist der Laufordner (walls-list) mit candidates.json,
    model.glb und model_map.json, auf den das Projekt *verweist* (ADR-016);
    `artifact` ist das geschriebene, schema-validierte project.json.
    """

    project_dir: Path
    project_path: Path
    overview_run_dir: Path
    artifact: dict


@dataclass
class PlacementEvalResult(_JobArtifactResult):
    """Ergebnis von `evaluate_placements`: Bewertungslauf + aktualisiertes Projekt.

    `run_dir` ist der Laufordner des Bewertungslaufs (placement.json mit den
    Scores, ADR-004); `artifact` das vollständige, schema-validierte project.json
    nach dem Schreiben; `scored` je Aufstellmöglichkeit ihr Score-Dict (für die
    API-Antwort, damit der Viewer die Liste ohne Nachladen zeigen kann).

    `feasibility` (Issue #228, ADR-026) trägt den Gesamt-Befund „(kein) machbarer
    Kandidat" des Optimalvorschlags — ``checked``/``feasible``/``n_feasible`` (siehe
    :func:`fgc.placement.feasibility_finding`). ``None`` im reinen Bewertungsmodus
    (dort läuft kein Vorschlags-Grob-Check).
    """

    run_dir: Path
    scored: list[dict]
    selected: str | None
    feasibility: dict | None = None


@dataclass
class SelectPlacementResult(_JobArtifactResult):
    """Ergebnis von `select_placement`: aktualisiertes Projekt-Artefakt.

    `selected` ist die option_id der als gewählt markierten Aufstellmöglichkeit
    (None = Wahl aufgehoben); `artifact` das vollständige, schema-validierte
    project.json nach dem Schreiben.
    """

    selected: str | None


@dataclass
class DecomposeResult(_JobArtifactResult):
    """Ergebnis von `propose_decomposition`: Zerlegungslauf + aktualisiertes Projekt.

    `run_dir` ist der Laufordner des Zerlegungslaufs (decompose.json mit
    Abschnitten, Platzierungen und Ampeln, ADR-004); `artifact` das vollständige,
    schema-validierte project.json nach dem Schreiben; `sections` je Abschnitt
    Geometrie + Platzierung + Ampel-Befund (für die API-Antwort, damit der Viewer
    die Zerlegung ohne Nachladen zeigen kann); `cuts` die Schnittebenen.
    """

    run_dir: Path
    decomposition_kind: str
    cuts: list[dict]
    sections: list[dict]
    joint_offset_mm: float = 0.0
    #: Freigang-Befund der Wand (Issue #163) — druckbare Tiefe vs. Wanddicke, wand-weit
    #: (nicht je Teil). ``None``, wenn die Endeffektor-/Kinematik-Geometrie fehlt
    #: (Befund, kein Gate). Als Dict für die API-Antwort (``FreigangCheck.to_dict``).
    freigang: dict | None = None
    #: Umfangsansage der Stufe-2-Prüf-Tür (Issue #175): wie viele Höhenreihen-
    #: Repräsentanten eine **globale** Prüfung rechnen müsste + eine grobe
    #: Zeitschätzung — damit der Viewer die bewusste Wahl „prüft N Abschnitte,
    #: dauert ~…" anzeigen kann, ohne die teure Prüfung anzustoßen. Als Dict
    #: (``{"n_representatives", "n_parts", "est_seconds"}``); ``n_representatives=0``
    #: heißt „nichts zu prüfen" (z. B. Wand schon nach Freigang zu dick).
    pruef_scope: dict | None = None


@dataclass
class SectionSimResult(_JobArtifactResult):
    """Ergebnis von `simulate_section` (Issue #26): Abschnitts-Lauf + Kennzahlen.

    Je Abschnitt entsteht **ein** regulärer Lauf mit ``toolpath.json`` **und**
    ``trajectory.json`` unter einer Provenienz (ADR-004); der Druckjob verweist
    darauf über ``section_runs`` (ADR-016). ``pose_source`` ist immer ``"planned"``
    (die Lage kommt aus der geplanten Platzierung, nicht aus einem gemessenen
    Setup — Design-Log 2026-07-04). ``duration_s``/``n_warnings``/
    ``axis_utilization`` reichen wir für die GUI mit heraus (Druckzeitschätzung +
    Achsauslastung + Warnungszahl je Abschnitt).
    """

    section_id: str
    run_dir: Path
    pose_source: str
    duration_s: float
    n_targets: int
    n_warnings: int
    io_compensated: bool
    axis_utilization: list[float]
    warnings: list[dict]


@dataclass
class WallsListRun:
    """Ergebnis einer walls-list-Aktion: Laufordner + Artefakte + Kandidaten.

    Die Kandidaten reichen wir mit heraus, damit der Aufrufer sie ohne
    Nachladen des gerade geschriebenen candidates.json tabellieren kann.
    `model_glb_path` zeigt auf die binäre Modell-glTF (model.glb, ein
    Szenenknoten je Wand), `model_map_path` auf das schema-/provenienz-konforme
    model_map.json-Artefakt (Knotenname ↔ GlobalId) für den Viewer (Issue #6).
    `context_path` zeigt auf das context.json-Artefakt (Issue #17), falls
    Nicht-Wand-Elemente im Modell vorhanden waren; None falls keine.
    """

    run_dir: Path
    candidates_path: Path
    model_glb_path: Path
    model_map_path: Path
    candidates: list[WallCandidate]
    context_path: Path | None = None


def emit_drl_run(
    run_dir: Path,
    setup_path: Path,
    source: str,
    *,
    motion: MotionParams | None = None,
) -> EmitDrlRun:
    """Erzeugt ein DRL-Programm aus toolpath.json + Setup und schreibt es in den Lauf.

    Liest ``toolpath.json`` aus ``run_dir`` und das Setup aus ``setup_path``, ruft
    ``fgc.postproc.emit_drl`` auf (per Target ``movel``/``movej``, Change-on-Delta,
    Kanal-Mapping aus Setup nach ADR-011, Grad nur im Emitter nach ADR-006) und
    schreibt ``program.drl`` **in denselben Lauf** (ADR-004). Die Provenienz ist
    als Kommentarblock im DRL eingebettet. ``motion`` steuert Bewegungstyp/vel/acc/
    Blending/ref (``process_params.motion``, Issue #64); ohne Angabe gelten die
    provisorischen :class:`~fgc.simulation.motion.MotionParams`-Defaults (z. B. der
    CLI-Pfad ``fgc emit-drl`` ohne Druckjob).

    Wirft ``FileNotFoundError``, wenn ``toolpath.json`` oder Setup fehlt.
    Wirft ``ValueError``, wenn ein logischer Kanal nicht im Setup steht oder ein
    Wert außerhalb des erlaubten logischen Bereichs liegt (ADR-011).
    """
    if not setup_path.exists():
        raise FileNotFoundError(f"Setup nicht gefunden: {setup_path}")

    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    drl_path, n_targets = _emit_drl_from_setup(run_dir, setup, source, motion)
    return EmitDrlRun(drl_path=drl_path, n_targets=n_targets)


def _emit_drl_from_setup(
    run_dir: Path, setup: dict, source: str, motion: MotionParams | None
) -> tuple[Path, int]:
    """Emittiert ``program.drl`` aus ``toolpath.json`` + einem **Setup-Dict** (Issue #136).

    Die eine Emit-Naht: ``emit_drl_run`` reicht ein aus Datei geladenes *gemessenes*
    Setup (Antast-Pfad) herein, der Modul-Export ein aus Stammdaten **generiertes**
    Setup (ADR-022). Beide teilen genau diesen Codepfad — das Setup bleibt die eine
    Transformationsstelle (ADR-006), nur die Herkunft unterscheidet sich. Liefert
    (Pfad der geschriebenen DRL, Anzahl Targets).

    Wirft ``FileNotFoundError``, wenn ``toolpath.json`` fehlt; ``ValueError`` aus
    ``emit_drl`` (unbekannter Kanal / Wert ausserhalb des logischen Bereichs, ADR-011).
    """
    from fgc.pipeline.provenance import make_provenance
    from fgc.postproc import emit_drl

    toolpath_path = run_dir / "toolpath.json"
    if not toolpath_path.exists():
        raise FileNotFoundError(f"Kein Toolpath im Lauf: {toolpath_path}")

    toolpath = json.loads(toolpath_path.read_text(encoding="utf-8"))
    drl = emit_drl(toolpath, setup, make_provenance(source), motion)
    drl_path = run_dir / "program.drl"
    drl_path.write_text(drl, encoding="utf-8")
    return drl_path, len(toolpath["targets"])


def _write_antasten_stub(run_dir: Path, trajectory: dict, provenance: dict) -> Path:
    """Schreibt eine sichtbar gekennzeichnete, unvollständige DRL-Ausgabe (Issue #29).

    Ohne gemessenes Setup fehlt das Kanal-Mapping (ADR-011) — ein vollständiges,
    ausführbares Programm ist nicht erzeugbar. Statt eines *unmarkiert*
    unvollständigen Programms (das man versehentlich fahren könnte) schreiben wir
    eine reine Kommentar-Ausgabe mit dem Antasten-Hinweis und der Provenienz: der
    Nutzer *darf* exportieren (kein Gate), aber die Datei ist unmissverständlich
    als „Antasten fehlt" gekennzeichnet. Der Emitter selbst wird nicht dupliziert.
    """
    import textwrap

    n = len(trajectory.get("samples", []))
    lines = [
        "# FGC-Planner — DRL-Programm (UNVOLLSTÄNDIG — Antasten fehlt)",
        f"# Quelle: {provenance['source']}",
        f"# Erstellt: {provenance['created']}",
        f"# Git: {provenance['git_commit']}",
        "#",
        "# ===================== ANTASTEN FEHLT =====================",
        *[f"# {line}" for line in textwrap.wrap(ANTASTEN_HINT, width=70)],
        "#",
        f"# (Trajektorie mit {n} Samples liegt vor; das Bewegungs-/IO-Programm",
        "#  entsteht erst mit dem gemessenen Setup — Kanal-Mapping nach ADR-011.)",
    ]
    drl_path = run_dir / "program.drl"
    drl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return drl_path


def _missing_note(missing: list[str]) -> str:
    """Baut den Gate-Hinweis mit **konkret benanntem Fehlbestand** (Issue #136).

    Ersetzt beim Modul-Export den generischen Antasten-Hinweis: statt „irgendetwas
    fehlt" nennt er, welche Stammdaten fehlen oder provisorisch sind (ADR-013-Geist —
    Befund, kein Gate). Die Werte kommen aus Spike S1 bzw. den Workstation-Frames.
    """
    return (
        "Der Modul-Export ist unvollstaendig — es fehlt: "
        + "; ".join(missing)
        + ". (S1-Stammdaten der Workstation bzw. Werkzeug-TCP, ADR-006/022.)"
    )


def _write_generated_stub(
    run_dir: Path, trajectory: dict, provenance: dict, missing: list[str]
) -> Path:
    """Kommentar-Stub des Modul-Exports mit benanntem Fehlbestand (Issue #136).

    Analog zu :func:`_write_antasten_stub`, aber fuer den **generierten** Modul-Pfad
    (ADR-022): das Setup wird aus Stammdaten gebaut, doch mindestens ein beteiligter
    Wert fehlt oder ist provisorisch. Statt eines unmarkiert unvollstaendigen
    Programms eine reine Kommentar-Ausgabe, die den Fehlbestand **konkret nennt**
    (Befund, kein Gate). Der Emitter selbst wird nicht dupliziert.
    """
    import textwrap

    n = len(trajectory.get("samples", []))
    lines = [
        "# FGC-Planner — DRL-Programm (UNVOLLSTAENDIG — Stammdaten fehlen)",
        f"# Quelle: {provenance['source']}",
        f"# Erstellt: {provenance['created']}",
        f"# Git: {provenance['git_commit']}",
        "#",
        "# ============== MODUL-EXPORT UNVOLLSTAENDIG ==============",
        "# Das Setup wird bei Art 'modul' aus Stammdaten generiert (ADR-022),",
        "# aber es fehlt (oder ist provisorisch):",
        *[f"#   - {item}" for item in missing],
        "#",
        *[f"# {line}" for line in textwrap.wrap(_missing_note(missing), width=70)],
        "#",
        f"# (Trajektorie mit {n} Samples liegt vor; das Bewegungs-/IO-Programm",
        "#  entsteht, sobald kein beteiligter Wert mehr fehlt oder provisorisch ist.)",
    ]
    drl_path = run_dir / "program.drl"
    drl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return drl_path


def _generate_module_setup(
    artifact: dict,
    job: dict,
    section_id: str,
    source: str,
    *,
    workstations_dir: Path | None = None,
) -> tuple[dict | None, list[str]]:
    """Generiert das Setup fuer Art „modul" aus Stammdaten + prueft das Gate (Issue #136).

    Statt eines gemessenen ``setup.json`` (Antast-Pfad, #116) baut der Export das
    Setup bei Zerlegungsart „modul" selbst (ADR-022): **Workstation-Frames** (feste
    Platzierung, ``_module_placement`` ueber ``plan_for_job``) + **Werkzeug-TCP**
    (``tool.tcp_frame``) + **Workstation-``io_channels``/``deadtime``** (S1-Stammdaten).
    Das Setup bleibt die eine Transformationsstelle (ADR-006), nur je Zerlegungsart
    anders befuellt.

    Zugleich das **Gate „nichts Provisorisches"** (Ablosung der Datei-Existenz):
    jeder fehlende oder provisorische Baustein landet als benannter Eintrag in
    ``missing``. Ist ``missing`` leer, ist das zurueckgegebene Setup schema-valide
    und vollstaendig (``complete``); sonst ist das erste Element ``None`` und der
    Aufrufer schreibt den benannten Stub (Befund, kein Gate).

    Wirft ``ValueError``, wenn der Abschnitt nicht im Zerlegungsplan liegt.
    """
    from fgc import domain
    from fgc.pipeline.provenance import make_provenance
    from fgc.setup import setup_artifact

    pc = placement_context_for_job(job)
    tool = pc.tool
    job_plan = plan_for_job(
        job, pc.wall, pc.robot, tool,
        strict_overrides=False, workstations_dir=workstations_dir,
    )
    plan = job_plan.plan
    workstation = job_plan.workstation

    sp = next(
        (s for s in plan.sections if s.section.section_id == section_id), None
    )
    if sp is None:
        known = [s.section.section_id for s in plan.sections]
        raise ValueError(
            f"Abschnitt {section_id!r} nicht im Zerlegungsplan des Modul-Druckjobs — "
            f"vorhanden: {known}."
        )
    # Feste Workstation-Platzierung (ADR-022): identisch zu der, die die Simulation
    # verrechnet hat (dieselbe Tuer, z_offset=0 fuer Modul) → Ketten-Orakel haelt.
    planned = planned_setup(
        pc.robot_name, sp.placement, tool,
        thickness_mm=plan.wall.thickness_mm, z_offset_mm=0.0,
    )

    missing: list[str] = []
    if workstation is None:  # (propose warf schon bei modul ohne Workstation)
        missing.append("Workstation als Druckort (im Druckjob waehlen)")
    else:
        if workstation.robot_base_frame is None:
            missing.append("Roboterbasis-Frame der Workstation (robot_base_frame)")
        if workstation.work_surface_frame is None:
            missing.append("Arbeitsflaechen-Frame der Workstation (work_surface_frame)")

    # Werkzeug-TCP: gewaehlt und nicht provisorisch (ehrliche Kennzeichnung, ADR-013)
    if not job.get("tool"):
        missing.append("gewaehlter Endeffektor (Werkzeug-TCP)")
    elif getattr(tool, "tcp_provisional", False):
        missing.append(f"nicht-provisorischer Werkzeug-TCP (Endeffektor {pc.tool_name!r})")

    # io_channels bestaetigt (Verkabelung, Spike S1)
    io_channels = getattr(workstation, "io_channels", None) if workstation else None
    if not io_channels:
        missing.append("bestaetigtes Kanal-Mapping der Workstation (io_channels, Spike S1)")

    # Totzeit gemessen (nicht provisorisch, Spike S1)
    deadtime = getattr(workstation, "deadtime", None) if workstation else None
    if not deadtime:
        missing.append("gemessene Totzeit der Workstation (deadtime, Spike S1)")
    elif bool(deadtime.get("provisional", False)):
        missing.append(
            "gemessene Totzeit der Workstation (deadtime ist provisorisch, Spike S1)"
        )

    if missing:
        return None, missing

    setup = setup_artifact(
        robot=planned["robot"],
        wall_to_base=planned["wall_to_base"],
        tcp=planned["tcp"],
        io_channels=io_channels,
        deadtime=deadtime,
        provenance=make_provenance(source),
    )
    domain.validate(setup, "setup")  # ehrliches, schema-valides Setup (ADR-006)
    return setup, []


def export_section_drl(
    slug: str,
    section_id: str,
    source: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
    workstations_dir: Path | None = None,
) -> ExportDrlResult:
    """Erzeugt das DRL-Programm eines Abschnitts (Reiter Export, Issue #29/#136).

    Der Abschluss des Prozesses: je Abschnitt ein DRL-Programm als Lauf-Artefakt
    (ADR-004). Die bestehende Emit-Naht (`_emit_drl_from_setup`, Issue #13/#136)
    wird geteilt — **nicht** neu implementiert. Das Setup bleibt die eine
    Transformationsstelle (ADR-006); je **Zerlegungsart** wird es anders befüllt:

    - **Art „modul"** (ADR-022, Issue #136): der Export **generiert** das Setup
      selbst aus Stammdaten — Workstation-Frames (feste Platzierung) + Werkzeug-TCP
      + Workstation-``io_channels``/``deadtime`` (S1). Das Gate ist nicht mehr
      „``setup.json`` existiert", sondern „**kein beteiligter Wert fehlt oder ist
      provisorisch**": ist alles bestätigt → vollständiges DRL (``complete=True``,
      ``setup_source="generated"``); fehlt etwas → Kommentar-Stub mit **konkret
      benanntem Fehlbestand** (``complete=False``, ``setup_source="generated_incomplete"``).
    - **Art „abschnitt"** (unverändert): liegt im Lauf ein **gemessenes**
      ``setup.json`` (Antast-Verfahren, ADR-011) → vollständiges DRL
      (``setup_source="measured"``); sonst der **Antasten-Hinweis**
      (``setup_source="none"``), bis die Wieder-Registrierung (#116) existiert.

    Kein Gate: die Ausgabe entsteht so oder so, nur sichtbar gekennzeichnet. In
    jedem Fall wird die **Export-Revision** des Druckjobs aufgefrischt
    (veraltet-Markierung, Issue #29). `fgc.project` bleibt die einzige Schreibstelle
    (ADR-016).

    Wirft `FileNotFoundError`, wenn das Projekt fehlt; `ValueError` bei fehlendem
    Druckjob, fehlendem Abschnitts-Lauf (zuerst simulieren, Issue #26) oder Lauf
    ohne ``trajectory.json``.
    """
    from fgc.pipeline.provenance import make_provenance
    from fgc.project import (
        load_project,
        project_dir_for,
        project_lock,
        refresh_output,
        refresh_section_output,
        write_project,
    )

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)

        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        section_run = next(
            (sr for sr in job.get("section_runs", []) if sr.get("section_id") == section_id),
            None,
        )
        if section_run is None:
            raise ValueError(
                f"Kein Abschnitts-Lauf für {section_id!r} — zuerst im Reiter Simulation "
                "slicen + simulieren (Issue #26)."
            )
        run_dir = Path(section_run["run"])
        trajectory_path = run_dir / "trajectory.json"
        if not trajectory_path.exists():
            raise ValueError(
                f"Abschnitts-Lauf ohne trajectory.json: {run_dir} — Abschnitt neu simulieren."
            )

        # Der dichte Gelenk-Stream (trajectory.json) bleibt für den Viewer; die DRL
        # entsteht per Toolpath-Target — n_samples spiegelt weiterhin den Stream.
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        n_samples = len(trajectory.get("samples", []))

        from fgc.simulation.motion import motion_from_job

        kind = job.get("decomposition_kind", "abschnitt")
        if kind == "modul":
            # Art „modul" (Issue #136, ADR-022): das Setup wird aus Stammdaten
            # GENERIERT (Workstation-Frames + TCP + io_channels/deadtime). Gate =
            # „nichts fehlt oder ist provisorisch" statt Datei-Existenz. Der manuelle
            # setup.json-Schritt (#116) entfällt auf diesem Pfad.
            setup, missing = _generate_module_setup(
                artifact, job, section_id, source, workstations_dir=workstations_dir
            )
            if not missing:
                drl_path, _ = _emit_drl_from_setup(
                    run_dir, setup, source, motion_from_job(job)
                )
                complete = True
                setup_source = "generated"  # ehrlich (ADR-006), nicht „measured"
                note = ""
            else:
                # Kein Gate: benannter Stub statt eines lauffähigen Programms.
                drl_path = _write_generated_stub(
                    run_dir, trajectory, make_provenance(source), missing
                )
                complete = False
                setup_source = "generated_incomplete"
                note = _missing_note(missing)
        elif (setup_path := run_dir / "setup.json").exists():
            # Art „abschnitt" mit gemessenem Setup im Lauf (Kanal-Mapping, ADR-011) →
            # vollständiges DRL über die geteilte Emit-Naht (Issue #13), nicht neu
            # implementiert. Bewegungsparameter (movel/movej, vel/acc/Blending/ref)
            # aus dem Druckjob (process_params.motion, Issue #62/#64).
            emitted = emit_drl_run(run_dir, setup_path, source, motion=motion_from_job(job))
            drl_path = emitted.drl_path
            complete = True
            setup_source = "measured"
            note = ""
        else:
            # Art „abschnitt" ohne gemessenes Setup → Antasten-Hinweis statt
            # unmarkiert unvollständig (bis zur Wieder-Registrierung #116).
            drl_path = _write_antasten_stub(run_dir, trajectory, make_provenance(source))
            complete = False
            setup_source = "none"
            note = ANTASTEN_HINT

        # Export-Revision auffrischen (Issue #29) — auch die gekennzeichnete
        # unvollständige Ausgabe zählt als „erzeugt": der Export ist aktuell
        # gegenüber den Eingaben, nur (noch) unvollständig bis zum Antasten.
        # Zusätzlich der Pro-Abschnitts-Schnappschuss (Issue #83): nur dieser
        # Abschnitts-Export ist danach aktuell, die Nachbarn bleiben unberührt.
        updated_job = refresh_output(job, "export")
        updated_job = refresh_section_output(updated_job, section_id, "export")
        new_jobs = [updated_job if j["job_id"] == job_id else j for j in artifact["print_jobs"]]
        updated_artifact = {**artifact, "print_jobs": new_jobs}
        path = write_project(project_dir, updated_artifact)

    return ExportDrlResult(
        project_dir=project_dir,
        project_path=path,
        artifact=updated_artifact,
        job_id=job_id,
        section_id=section_id,
        run_dir=run_dir,
        drl_path=drl_path,
        complete=complete,
        setup_source=setup_source,
        note=note,
        n_samples=n_samples,
    )


def evaluate_walls(
    model_path: Path,
    robot_name: str,
    *,
    walls: list[WallData] | None = None,
) -> list[WallCandidate]:
    """Beschafft Prozessfenster + Roboter und evaluiert Wände (E1-Stufe 1).

    Diese Aktion besitzt die Konfig-Beschaffung (`ProcessWindow.load`,
    `RobotDef.load`), sodass kein Aufrufer die Dreiergruppe mehr offen
    ausbuchstabiert. `walls` = bereits geladene Teilmenge (der Wizard reicht
    seine gefilterte Auswahl herein); ohne Angabe werden alle Wände aus
    `model_path` geladen (CLI `walls list`). Beide Fälle teilen denselben
    Codepfad — nur die Wandquelle unterscheidet sich.
    """
    from fgc.eligibility import evaluate_wall

    window = ProcessWindow.load()
    robot = RobotDef.load(robot_name)
    if walls is None:
        walls = ifc_walls.load_walls(model_path)
    return [evaluate_wall(w, window, robot) for w in walls]


def walls_to_run(
    model_path: Path,
    robot_name: str,
    source: str,
    *,
    runs_dir: Path | None = None,
) -> WallsListRun:
    """Evaluiert alle Wände eines Modells und schreibt candidates.json + model.glb/model_map.json.

    Aufbauend auf `evaluate_walls`; `source` = fertiger reproduzierbarer Aufruf
    für den Provenienzblock (die Aufrufer buchstabieren die Flag-Namen, nicht
    diese Aktion). `runs_dir` überschreibt das Standard-`runs/`-Verzeichnis
    (Test-Seam) und wird an `Run.create` durchgereicht.

    Wände werden einmal geladen (load_walls) und zweifach genutzt: Eignungsprüfung
    → candidates.json, GLB-Export → binäres model.glb (ein Szenenknoten je Wand)
    plus schema-validiertes model_map.json (Knotenname ↔ GlobalId) für den Viewer
    (Issue #6, ADR-004/007).
    """
    from fgc.geometry.gltf import export_walls_glb
    from fgc.ifc_io.context import context_artifact

    walls = ifc_walls.load_walls(model_path)  # einmal laden → Kandidaten + GLB-Export
    candidates = evaluate_walls(model_path, robot_name, walls=walls)
    run = Run.create("walls-list", model_path.stem, source=source, runs_dir=runs_dir)
    # Absoluter Pfad wie bei slice_to_run (params.model_path) — der Viewer
    # leitet ihn direkt an POST /slice weiter, ohne CWD-Wissen (ADR-014).
    abs_model = str(model_path.resolve())
    candidates_path = run.write(
        "candidates", candidates_artifact(abs_model, candidates, run.provenance)
    )
    model_glb_path = export_walls_glb(
        {wall_node_name(w.global_id): (w.vertices_mm, w.faces) for w in walls},
        run.dir / MODEL_GLB_FILE,
    )
    model_map_path = run.write(
        "model_map",
        model_map_artifact(abs_model, [w.global_id for w in walls], run.provenance),
    )

    # Nicht-Wand-Elemente als Kontextgeometrie exportieren (Issue #17).
    # Wände sind bereits in model.glb; hier kommen Decken, Dächer, Stützen usw.
    context_elements = ifc_context.load_context_overview(model_path)
    context_path: Path | None = None
    if context_elements:
        context_path = run.write(
            "context",
            context_artifact(abs_model, context_elements, run.provenance),
        )

    return WallsListRun(
        run_dir=run.dir,
        candidates_path=candidates_path,
        model_glb_path=model_glb_path,
        model_map_path=model_map_path,
        candidates=candidates,
        context_path=context_path,
    )


def create_project_from_ifc(
    name: str,
    model_path: Path,
    robot_name: str,
    source: str,
    *,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
) -> ProjectCreation:
    """Legt ein Projekt aus einer IFC-Datei an (ADR-016) — die eine Tür für CLI/API.

    Erzeugt zuerst den **Übersichts-Lauf** (`walls_to_run`: candidates.json +
    model.glb + model_map.json, Eignungsbefunde für `robot_name`) und schreibt
    dann das `project.json`, das auf diesen Lauf *verweist* — nie eingebettet.
    Das project.json wird ausschließlich über `fgc.project.write_project`
    geschrieben (die eine Schreibstelle, schema-validiert). `print_jobs` bleibt
    in diesem Slice leer.

    `source` = fertiger reproduzierbarer Aufruf für die Provenienzblöcke;
    `projects_dir`/`runs_dir` überschreiben die Standardverzeichnisse (Test-Seams).
    """
    from fgc.pipeline.provenance import make_provenance
    from fgc.project import project_artifact, unique_project_dir, write_project

    overview = walls_to_run(model_path, robot_name, source, runs_dir=runs_dir)
    project_dir = unique_project_dir(name, projects_dir=projects_dir)
    artifact = project_artifact(
        name, model_path, overview.run_dir, make_provenance(source)
    )
    project_path = write_project(project_dir, artifact)
    return ProjectCreation(
        project_dir=project_dir,
        project_path=project_path,
        overview_run_dir=overview.run_dir,
        artifact=artifact,
    )


def slice_to_run(
    model_path: Path,
    wall: WallData,
    params: SliceParams,
    source: str,
    *,
    with_context: bool = True,
    runs_dir: Path | None = None,
) -> SliceRun | None:
    """Sliced eine geladene Wand und schreibt wallspec/toolpath(/context).

    `source` = fertiger reproduzierbarer Aufruf für den Provenienzblock; die
    Aufrufer bauen ihn (CLI aus argparse-Flags, künftige API aus ihren
    Parametern), nicht diese Aktion — so buchstabiert nur eine Stelle die
    Flag-Namen nach. Liefert None, wenn der Slicer keine Targets erzeugt
    (Konturen degeneriert).
    """
    from fgc.slicer import slice_wall

    toolpath = slice_wall(wall.vertices_mm, wall.faces, wall.global_id, params)
    if not toolpath.targets:
        return None

    run = Run.create("slice", model_path.stem, source=source, runs_dir=runs_dir)

    wallspec = wallspec_artifact(
        wall.global_id,
        wall.name,
        wall.vertices_mm,
        wall.faces,
        wall.load_bearing,
        run.provenance,
    )
    run.write("wallspec", wallspec)
    run.write(
        "toolpath",
        toolpath.to_artifact(
            run.provenance,
            {
                "model_path": str(model_path.resolve()),
                "layer_height_mm": params.layer_height_mm,
                "strand_width_mm": params.strand_width_mm,
                "n_shells": params.n_shells,
            },
        ),
    )

    n_context = 0
    if with_context:
        from fgc.ifc_io.context import context_artifact, load_context

        elements = load_context(model_path, exclude_global_ids=[wall.global_id])
        n_context = len(elements)
        run.write(
            "context",
            context_artifact(
                str(model_path),
                elements,
                run.provenance,
                wall_global_id=wall.global_id,
            ),
        )

    return SliceRun(run_dir=run.dir, toolpath=toolpath, n_context=n_context)


def simulate_run(
    run_dir: Path,
    setup_path: Path,
    source: str,
    *,
    robot_name: str | None = None,
) -> SimulateRun:
    """Simuliert einen bestehenden Toolpath-Lauf zu einer trajectory.json (Strang C).

    Liest `toolpath.json` aus `run_dir` und das Setup aus `setup_path`, baut über
    `fgc.simulation.build_trajectory` (Kinematik + Zeitparametrierung + io-Shift)
    die Trajectory und schreibt sie schema-validiert **in denselben Lauf** (ADR-004).
    `source` = fertiger reproduzierbarer Aufruf für den Provenienzblock;
    `robot_name` überschreibt den `robot`-Eintrag des Setups (sonst gilt dieser).

    Wirft `FileNotFoundError`, wenn `toolpath.json` oder das Setup fehlt.
    """
    from fgc.kinematics.opw import OpwKinematics
    from fgc.pipeline.provenance import make_provenance
    from fgc.pipeline.runfolder import write_artifact
    from fgc.simulation import build_trajectory

    toolpath_path = run_dir / "toolpath.json"
    if not toolpath_path.exists():
        raise FileNotFoundError(f"Kein Toolpath im Lauf: {toolpath_path}")
    if not setup_path.exists():
        raise FileNotFoundError(f"Setup nicht gefunden: {setup_path}")

    toolpath = json.loads(toolpath_path.read_text(encoding="utf-8"))
    setup = json.loads(setup_path.read_text(encoding="utf-8"))

    robot = robot_name or setup["robot"]
    kin = OpwKinematics.from_robot(robot)

    trajectory = build_trajectory(toolpath["targets"], setup, kin)
    provenance = make_provenance(source)
    artifact = trajectory.to_artifact(provenance)
    path = write_artifact(run_dir, "trajectory", artifact)

    return SimulateRun(
        trajectory_path=path,
        duration_s=trajectory.meta["duration_s"],
        n_samples=len(trajectory.samples),
        io_compensated=trajectory.meta["io_compensated"],
        n_warnings=len(trajectory.meta.get("warnings", [])),
    )


def _resolve_section_overrides(plan, overrides, placements, *, strict: bool):
    """Löst ``section_overrides``-Einträge zu Platzierungen auf (Issue #25/#94).

    Zwei additive Formen je Eintrag: **Referenz** (``option_id`` → erfasste
    Aufstellmöglichkeit, Issue #25) und/oder **freie Werte** (Issue #94:
    ``lateral_mm``/``standoff_mm``/``stand_height_mm``, sparse — nur gesetzte
    Felder übersteuern; Basis ist die automatisch gesuchte bzw. referenzierte
    Platzierung, die ``option_id`` wird dann ``frei-<section_id>``).

    ``strict=True`` wirft ``ValueError`` bei unbekannter ``option_id``
    (Zerlegungs-Route validiert); ``strict=False`` ignoriert sie still
    (Simulation, stale Referenzen). Stale ``section_id``s (Teil existiert nicht
    mehr) werden immer still ignoriert. Rückgabe:
    ``(section_id → PlacementOption, section_ids mit freien Werten)``.
    """
    from fgc.placement import PlacementOption

    placements_by_id = {p["option_id"]: p for p in placements}
    auto_by_id = {sp.section.section_id: sp.placement for sp in plan.sections}
    resolved: dict[str, PlacementOption] = {}
    free_ids: set[str] = set()
    for entry in overrides:
        sid = str(entry["section_id"])
        option_id = entry.get("option_id")
        if option_id is not None:
            p = placements_by_id.get(str(option_id))
            if p is None:
                if strict:
                    raise ValueError(
                        f"Platzierungs-Override verweist auf unbekannte Aufstellmöglichkeit "
                        f"{option_id!r} — vorhanden: {sorted(placements_by_id)}. Zuerst im "
                        "Bewertungsmodus erfassen (Issue #22)."
                    )
                continue  # stale Referenz — still ignorieren
            base = PlacementOption(
                option_id=str(option_id),
                lateral_mm=float(p["lateral_mm"]),
                standoff_mm=float(p["standoff_mm"]),
                stand_height_mm=float(p["stand_height_mm"]),
                yaw_rad=float(p.get("yaw_rad", 0.0)),
            )
        else:
            base = auto_by_id.get(sid)
            if base is None:
                continue  # stale Eintrag — Teil existiert nicht mehr (kein Gate)
        free = {
            k: float(entry[k]) for k in PLACEMENT_OVERRIDE_FIELDS if entry.get(k) is not None
        }
        if free:
            free_ids.add(sid)
            base = PlacementOption(
                option_id=f"frei-{sid}",
                lateral_mm=free.get("lateral_mm", base.lateral_mm),
                standoff_mm=free.get("standoff_mm", base.standoff_mm),
                stand_height_mm=free.get("stand_height_mm", base.stand_height_mm),
                yaw_rad=base.yaw_rad,
            )
        resolved[sid] = base
    return resolved, free_ids


@dataclass(frozen=True)
class JobPlan:
    """Der aus einem Druckjob rekonstruierte **Zerlegungsplan** plus der dafür
    aufgelöste Kontext (Issue #112, `core/CONTEXT.md` »Zerlegungsplan«).

    `plan` ist alles, was der Lesepfad (Simulation) braucht; `workstation`,
    `module_limits` und `free_override_ids` sind der beim Rekonstruieren ohnehin
    aufgelöste Kontext, den der Schreibpfad (`propose_decomposition`) für seine
    additiven Befunde (Modulgrenzen, Modul-Lage, Sicherheitsabstand) weiternutzt
    — so sammelt kein Aufrufer die Job-Felder ein zweites Mal selbst.
    """

    plan: DecompositionPlan
    workstation: WorkstationDef | None
    module_limits: ModuleLimits
    free_override_ids: set[str]


def _workstation_for_job(job: dict, workstations_dir: Path | None):
    """Lädt die Workstation eines Druckjobs (oder ``None``, falls keine gesetzt)."""
    name = job.get("workstation")
    if not name:
        return None
    from fgc.domain.workstation import WorkstationDef

    return WorkstationDef.load(name, workstations_dir=workstations_dir)


def plan_for_job(
    job: dict,
    wall,
    robot,
    tool,
    *,
    strict_overrides: bool = False,
    workstations_dir: Path | None = None,
    pruef_tuer=None,
    call_budget: int | None = None,
    scorer=None,
    objective=None,
    strategie=None,
) -> JobPlan:
    """Rekonstruiert den **Zerlegungsplan** eines Druckjobs — die eine Tür
    „Druckjob rein, Plan raus" (Issue #112, `core/CONTEXT.md` »Zerlegungsplan«).

    Liest **alle** Plan-Eingaben aus dem Druckjob: Zerlegungsart, Schnittebenen
    (`cuts`), Fugen-Versatz, **Workstation**, **Aufstell-Toggle** (`stand_mode`,
    #81), **Modul-Obergrenzen** (#90) und die Platzierungs-Overrides (#94). Mit
    gespeicherten Schnitten baut `fgc.decompose.from_cuts` den Plan, sonst der
    Auto-Vorschlag `propose`; danach werden die Platzierungs-Overrides aufgelöst
    (`_resolve_section_overrides`) und angewandt.

    `strict_overrides=True` wirft bei unbekannter `option_id` (Schreibpfad,
    Reiter Druckplan — der Nutzer soll den Fehler sehen); `False` ignoriert sie
    still (Lesepfad, Simulation — stale Referenzen). Stale `section_id`s werden
    immer still ignoriert.

    Reiter Druckplan (`propose_decomposition`) und Reiter Simulation
    (`simulate_section`) sind beide dünne Aufrufer dieser Tür und tragen dadurch
    **per Bauart** denselben Plan. Vor #112 sammelte jeder Pfad die Eingaben
    selbst und der Lesepfad ließ Workstation/`stand_mode`/Grenzen weg — die
    Modul-Simulation (#97) lief in einen 422, Abschnitts-Platzierungen mit
    Workstation/erhöhtem Aufstell-Modus drifteten still vom Druckplan ab.
    """
    from fgc.decompose import (
        DEFAULT_CALL_BUDGET,
        Cut,
        ModuleLimits,
        apply_overrides,
        from_cuts,
        propose,
    )

    kind = job.get("decomposition_kind", "abschnitt")
    workstation = _workstation_for_job(job, workstations_dir)
    stand_mode = job.get("stand_mode", "floor")
    module_limits = ModuleLimits.from_dict(job.get("module_limits"))

    cuts = job.get("cuts")
    if cuts is None:
        # ``pruef_tuer`` (Issue #165): liegt das Kollisions-Orakel vor (nur beim
        # Auto-Vorschlag), treibt die kollisionsgetriebene Verfeinerung den Schnitt
        # statt der reinen Reichweite — sonst byte-gleich.
        # ``scorer``/``objective``/``strategie`` (Issue #217): reicht die Beam-Suche
        # durch — der billige Scorer (#216) ordnet, nur Ueberlebende durch die
        # Pruef-Tuer; ohne diese drei (Default) byte-gleich zum Reichweiten-/#165-Pfad.
        # Seit #237 gilt beides auch fuer Art „modul" (modul-lokaler Scorer an der
        # festen Druckort-Platzierung; `propose` nutzt die Kandidaten-Naht).
        plan = propose(
            wall, robot, tool, kind=kind,
            workstation=workstation, stand_mode=stand_mode, limits=module_limits,
            pruef_tuer=pruef_tuer,
            call_budget=(DEFAULT_CALL_BUDGET if call_budget is None else int(call_budget)),
            scorer=scorer,
            objective=objective,
            strategie=strategie,
        )
    else:
        parsed = [
            Cut(orientation=str(c["orientation"]), position_mm=float(c["position_mm"]))
            for c in cuts
        ]
        plan = from_cuts(
            wall, robot, tool, parsed, kind=kind,
            joint_offset_mm=float(job.get("joint_offset_mm", 0.0)),
            workstation=workstation, stand_mode=stand_mode,
        )

    free_override_ids: set[str] = set()
    overrides_in = job.get("section_overrides") or []
    if overrides_in:
        resolved, free_override_ids = _resolve_section_overrides(
            plan, overrides_in, job.get("placements", []), strict=strict_overrides
        )
        plan = apply_overrides(plan, resolved)

    return JobPlan(
        plan=plan,
        workstation=workstation,
        module_limits=module_limits,
        free_override_ids=free_override_ids,
    )


def simulate_section(
    slug: str,
    section_id: str,
    source: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
    collision_config: CollisionConfig | None = None,
) -> SectionSimResult:
    """Slict + simuliert einen Abschnitt aus der Platzierung heraus (Issue #26).

    Der Querschnitt Slicer + Simulation für einen einzelnen Abschnitt: aus dem
    Abschnitts-**Teil-Mesh** (aus `fgc.decompose.apply`) entsteht über den
    bestehenden Slicer (`slice_wall`, Eingang erweitert — nicht dupliziert) ein
    Toolpath, aus diesem + der **geplanten Platzierung** + Endeffektor-TCP über
    `fgc.simulation.build_trajectory` (``pose_source="planned"``) eine Trajektorie.
    Beides landet in **einem** regulären Lauf (ADR-004); der Druckjob verweist je
    Abschnitt darauf (``section_runs``, ADR-016). `fgc.project` bleibt die einzige
    Schreibstelle.

    Das Abschnitts-Mesh wird ins **abschnitts-lokale** System verschoben (x um die
    Abschnittsmitte, z ab Abschnittsfuß) — konsistent zur abschnitts-lokalen
    Platzierung (`fgc.decompose`), sodass Toolpath und Lage-Frame zusammenpassen.

    Das gemessene Setup bleibt Voraussetzung des echten Drucks — nur die
    Simulation ist aus dem Plan zulässig (Design-Log 2026-07-04).

    Wirft `FileNotFoundError`, wenn das Projekt fehlt; `ValueError` bei fehlendem
    Druckjob/Roboter/Befund-Lauf, unbekanntem Abschnitt oder leerem Toolpath.
    """
    from fgc.pipeline.provenance import make_provenance
    from fgc.pipeline.runfolder import write_artifact
    from fgc.project import load_project, project_dir_for, project_lock, write_project

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)

        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        # Slice + Trajektorie über die geteilte Kern-Tür (dieselbe Maschinerie wie
        # der Kollisions-Advisor, #130) — hier ohne Override (der reale Lauf).
        comp = slice_and_simulate_section(
            artifact, job, section_id, workstations_dir=workstations_dir,
        )
        params = comp.params

        model_path = Path(artifact["model_path"])
        run = Run.create("slice", model_path.stem, source=source, runs_dir=runs_dir)

        wall_label = job.get("wall_name")
        run.write(
            "wallspec",
            wallspec_artifact(
                job["wall_global_id"],
                f"{wall_label} · {section_id}" if wall_label else section_id,
                comp.verts,
                comp.part_faces,
                None,
                run.provenance,
            ),
        )
        toolpath_artifact = comp.toolpath.to_artifact(
            run.provenance,
            {
                "model_path": str(model_path.resolve()),
                "layer_height_mm": params.layer_height_mm,
                "strand_width_mm": params.strand_width_mm,
                "n_shells": params.n_shells,
            },
        )
        run.write("toolpath", toolpath_artifact)

        # Kollisions-Befund additiv in meta.collision (ADR-024, Issue #127): entsteht
        # automatisch bei jeder Simulation (Abschnitt wie Modul), Befund kein Gate —
        # fehlt Kollisionsgeometrie oder scheitert der Check, bleibt der Block schlicht
        # weg und die Simulation liefert trotzdem (fail-soft, Altläufe byte-gleich).
        trajectory = comp.trajectory
        trajectory_artifact = trajectory.to_artifact(make_provenance(source))
        # Echte Höhenlage des Abschnitts (Issue #135, additiv): Toolpath/Trajektorie
        # liegen abschnitts-lokal (z ab Abschnittsfuß) — meta.section_z0_mm nennt
        # dem Viewer die z0-Lage, damit das Replay (Bahn + Arm + Druckstand) auf
        # der echten Bandlage rendert. Nur bei Art „abschnitt" (Modul druckt an der
        # Workstation, dort ist die Einbau-Höhenlage gegenstandslos, ADR-022):
        # `section_z0_mm` ist None bei „modul" und kodiert so die meta-Präsenz (#191).
        if comp.section_z0_mm is not None:
            trajectory_artifact["meta"]["section_z0_mm"] = float(comp.section_z0_mm)
        # Kollisions-Konfiguration (Issue #131): der Gebäudekontext-Schalter des
        # Druckjobs treibt jetzt die Simulation. Eine explizit übergebene
        # ``collision_config`` (Advisor) gewinnt; sonst wird sie aus dem Job
        # abgeleitet — bei „ein" prüft der Befund zusätzlich gegen den
        # Gebäudekontext, bei Zerlegungsart **Modul** ist der Schalter
        # gegenstandslos (Workstation ist der Druckort, ADR-022).
        cfg = collision_config
        ctx_verts = None
        ctx_faces = None
        if cfg is None:
            from fgc.collision.finding import CollisionConfig

            ctx_on = (
                bool(job.get("check_building_context", False))
                and comp.building_context_applicable
            )
            cfg = CollisionConfig(context_enabled=ctx_on)
            if ctx_on:
                ctx = section_context_geometry(artifact, job, comp.section)
                if ctx is not None:
                    ctx_verts, ctx_faces = ctx
        # Der Befund liest alles aus ``comp`` (Issue #192, ``finding_request``): die
        # Höhenlage (Boden bei lokal −z0, #191), die früheren Teile auf ihren echten
        # Bändern (#135, z0=0 bleibt bit-identisch) und den Gebäudekontext (#131).
        ctx_geom = (ctx_verts, ctx_faces) if ctx_verts is not None else None
        finding = section_collision_finding(comp, config=cfg, context=ctx_geom)
        if finding is not None:
            trajectory_artifact["meta"]["collision"] = finding

        write_artifact(run.dir, "trajectory", trajectory_artifact)
        run_str = str(run.dir.resolve())

        # Druckjob: Abschnitts-Lauf-Verweis (section_runs) + runs (ADR-016).
        section_runs = [
            sr for sr in job.get("section_runs", []) if sr.get("section_id") != section_id
        ]
        section_runs.append({"section_id": section_id, "run": run_str})
        updated_job = {
            **job,
            "section_runs": section_runs,
            "runs": [*job.get("runs", []), run_str],
        }
        # Simulations-Stufe (neu) erzeugt (Issue #29): Schnappschuss auf die aktuellen
        # Eingabe-Revisionen — hebt eine etwaige veraltet-Markierung der Simulation auf.
        # Zusätzlich der Pro-Abschnitts-Schnappschuss (Issue #83, ADR-017-Nachtrag):
        # dieser Abschnitt ist danach aktuell gegenüber globalen Eingaben *und* seinem
        # eigenen Override — nur er, die Nachbarn bleiben unberührt (section_output_status).
        from fgc.project import refresh_output, refresh_section_output

        updated_job = refresh_output(updated_job, "simulation")
        updated_job = refresh_section_output(updated_job, section_id, "simulation")
        new_jobs = [updated_job if j["job_id"] == job_id else j for j in artifact["print_jobs"]]
        updated_artifact = {**artifact, "print_jobs": new_jobs}
        path = write_project(project_dir, updated_artifact)

    warnings = trajectory.meta.get("warnings", [])
    return SectionSimResult(
        project_dir=project_dir,
        project_path=path,
        artifact=updated_artifact,
        job_id=job_id,
        section_id=section_id,
        run_dir=run.dir,
        pose_source=trajectory.meta["pose_source"],
        duration_s=trajectory.meta["duration_s"],
        n_targets=len(comp.toolpath.targets),
        n_warnings=len(warnings),
        io_compensated=trajectory.meta["io_compensated"],
        axis_utilization=list(trajectory.meta.get("axis_utilization", [])),
        warnings=warnings,
    )


def create_tool_from_upload(
    name: str,
    mesh_bytes: bytes,
    mesh_filename: str,
    weight_kg: float,
    channels: dict[str, dict],
    tcp_frame: dict,
    *,
    vendor: str = "",
    cog_mm: list[float] | None = None,
    mesh_transform: dict | None = None,
    compatible_robots: list[str] | None = None,
    tools_dir: Path | None = None,
) -> CreateToolResult:
    """Legt einen Endeffektor aus einem Mesh-Upload + Metadaten ab (Issue #28).

    Der Endeffektor-Konfigurator (Bibliothek) reicht ein hochgeladenes Mesh
    (STL/OBJ/GLB) plus die am Flansch per Gizmo ausgerichtete Lage
    (``mesh_transform``), den gesetzten ``tcp_frame`` und die Stammdaten (Name,
    Gewicht, Schwerpunkt, logische Kanaele) herein. Diese Aktion ist die eine
    Tuer (ADR-014): sie **validiert** (Dateiformat, Groesse, Ladbarkeit, Schema)
    und **legt ab** — Mesh-Datei ``<name><suffix>`` und Definition ``<name>.json``
    im Tools-Verzeichnis (Stammdaten, ADR-016). ``GET /tools`` findet den neuen
    Endeffektor sofort (kein Neustart).

    Der Name wird datei-sicher normalisiert (``safe_tool_name``) und dient
    zugleich als Dateiname *und* als ``name``-Feld der Definition — so bleibt der
    Endeffektor eindeutig referenzierbar (Druckjob → ``tool``). Ein bestehender
    Endeffektor gleichen Namens wird ueberschrieben (Stammdaten-Pflege).

    Wirft ``ValueError`` bei leerem/degeneriertem Namen, unbekanntem Mesh-Format,
    zu grosser/kaputter/leerer Mesh-Datei oder Schema-Verletzung (``build_tool_artifact``
    uebersetzt jsonschema.ValidationError nach ValueError) — der Aufrufer (CLI/API)
    uebersetzt das in eine klare Fehlermeldung, kein Absturz.

    Berechnet zusaetzlich einmalig die Huellkennzahl (``envelope_mm``: Bounding-Radius
    + Laenge um die Flanschachse, ADR-026 Punkt 4, PRD #225/Issue #229) aus dem
    hochgeladenen Mesh und speichert sie additiv — trimesh laeuft hier ohnehin fuer
    die Validierung, der spaetere Vorschlagspfad laedt nie ein Mesh.
    """
    from fgc.domain.tool import (
        ToolDef,
        build_tool_artifact,
        compute_tool_envelope,
        mesh_suffix,
        safe_tool_name,
        validate_mesh_bytes,
    )
    from fgc.paths import TOOLS_DIR

    target_dir = tools_dir or TOOLS_DIR

    # 1) Eingaben validieren, bevor irgendetwas geschrieben wird.
    stem = safe_tool_name(name)
    suffix = mesh_suffix(mesh_filename)
    validate_mesh_bytes(mesh_bytes, suffix)
    # Huellkennzahl einmalig aus dem Mesh berechnen (ADR-026 Pkt. 4, #229) — trimesh
    # laeuft hier ohnehin fuer die Validierung; der Vorschlagspfad laedt nie ein Mesh.
    envelope_mm = compute_tool_envelope(mesh_bytes, suffix, mesh_transform)

    mesh_name = f"{stem}{suffix}"
    artifact = build_tool_artifact(
        stem,
        tcp_frame,
        weight_kg,
        channels,
        vendor=vendor,
        cog_mm=cog_mm,
        mesh=mesh_name,
        mesh_transform=mesh_transform,
        compatible_robots=compatible_robots,
        envelope_mm=envelope_mm,
    )

    # 2) Ablegen: erst Mesh, dann Definition (die Definition verweist aufs Mesh).
    target_dir.mkdir(parents=True, exist_ok=True)
    mesh_path = target_dir / mesh_name
    mesh_path.write_bytes(mesh_bytes)
    tool_path = target_dir / f"{stem}.json"
    tool_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3) Zurueckladen (validiert erneut gegen das Schema) — der Katalog bekommt
    #    dieselbe ToolDef, die GET /tools spaeter liest.
    tool = ToolDef.load(stem, tools_dir=target_dir)
    return CreateToolResult(
        tool_dir=target_dir,
        tool_path=tool_path,
        mesh_path=mesh_path,
        tool_name=stem,
        tool=tool,
    )


def update_tool_from_upload(
    name: str,
    weight_kg: float,
    channels: dict[str, dict],
    tcp_frame: dict,
    *,
    mesh_bytes: bytes | None = None,
    mesh_filename: str | None = None,
    vendor: str = "",
    cog_mm: list[float] | None = None,
    mesh_transform: dict | None = None,
    compatible_robots: list[str] | None = None,
    tools_dir: Path | None = None,
) -> CreateToolResult:
    """Aktualisiert einen bestehenden Endeffektor (Bibliothek-Editor, Issue #56).

    Der Name ist die Identitaet (Dateiname *und* ``name``-Feld) und wird **nie**
    umbenannt (Out of Scope; stabile ``PrintJob.tool``-Verweise): ``name`` waehlt
    den zu aendernden Endeffektor, ein davon abweichendes ``name``-Feld gaebe es
    nicht — der Aufrufer reicht den Datei-Namen herein. Existiert der Endeffektor
    nicht, wird ``FileNotFoundError`` geworfen (API → 404).

    Das Mesh ist **optional**: sind ``mesh_bytes``/``mesh_filename`` leer, bleiben
    die bestehende Mesh-Datei und ihr Dateiname unangetastet — nur ``tcp_frame``,
    ``mesh_transform``, ``weight_kg``, ``vendor``, ``cog_mm`` und ``channels``
    werden neu geschrieben. Wird ein neues Mesh geliefert, greift dieselbe
    Validierung wie beim Anlegen (Format/Groesse/Ladbarkeit); ein altes Mesh mit
    abweichendem Dateinamen (z.B. Formatwechsel .stl→.glb) wird entfernt, damit
    keine Waise zurueckbleibt.

    Wirft ``ValueError`` bei unbekanntem Mesh-Format, zu grosser/kaputter/leerer
    Mesh-Datei oder Schema-Verletzung; ``FileNotFoundError``, wenn der Endeffektor
    nicht existiert.

    Die Huellkennzahl (``envelope_mm``, #229) wird nur neu berechnet, wenn ein
    neues Mesh mitkommt (trimesh laeuft nur beim tatsaechlichen Upload); ohne
    neues Mesh bleibt der bisherige Wert erhalten (auch fehlend = 'unbekannt').
    """
    from fgc.domain.tool import (
        ToolDef,
        build_tool_artifact,
        compute_tool_envelope,
        mesh_suffix,
        safe_tool_name,
        validate_mesh_bytes,
    )
    from fgc.paths import TOOLS_DIR

    target_dir = tools_dir or TOOLS_DIR
    stem = safe_tool_name(name)

    tool_path = target_dir / f"{stem}.json"
    if not tool_path.exists():
        raise FileNotFoundError(
            f"Endeffektor {stem!r} existiert nicht — nichts zu aktualisieren."
        )
    existing = ToolDef.load(stem, tools_dir=target_dir)

    # Mesh: nur ersetzen, wenn tatsaechlich neue Bytes geliefert wurden.
    new_mesh_written: Path | None = None
    # Huellkennzahl nur neu berechnen, wenn ein neues Mesh kommt — trimesh laeuft
    # nur beim tatsaechlichen Upload (#229); ohne neues Mesh bleibt der bisherige
    # Wert (auch 'unbekannt') unangetastet.
    envelope_mm = existing.envelope_mm  # type: ignore[attr-defined]
    if mesh_bytes and mesh_filename:
        suffix = mesh_suffix(mesh_filename)
        validate_mesh_bytes(mesh_bytes, suffix)
        envelope_mm = compute_tool_envelope(mesh_bytes, suffix, mesh_transform)
        mesh_name = f"{stem}{suffix}"
        # Altes Mesh mit abweichendem Dateinamen entfernen (Formatwechsel).
        if existing.mesh and existing.mesh != mesh_name:
            (target_dir / existing.mesh).unlink(missing_ok=True)
        new_mesh_written = target_dir / mesh_name
        new_mesh_written.write_bytes(mesh_bytes)
    else:
        # Bestehende Mesh-Datei + Dateiname erhalten.
        mesh_name = existing.mesh

    artifact = build_tool_artifact(
        stem,
        tcp_frame,
        weight_kg,
        channels,
        vendor=vendor,
        cog_mm=cog_mm,
        mesh=mesh_name,
        mesh_transform=mesh_transform,
        compatible_robots=compatible_robots,
        envelope_mm=envelope_mm,
    )
    tool_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    tool = ToolDef.load(stem, tools_dir=target_dir)
    mesh_path = (
        new_mesh_written
        if new_mesh_written is not None
        else (target_dir / mesh_name if mesh_name else target_dir)
    )
    return CreateToolResult(
        tool_dir=target_dir,
        tool_path=tool_path,
        mesh_path=mesh_path,
        tool_name=stem,
        tool=tool,
    )


def delete_tool(name: str, *, tools_dir: Path | None = None) -> Path:
    """Loescht einen Endeffektor: ``<name>.json`` UND die zugehoerige Mesh-Datei (Issue #56).

    Der Endeffektor ist ein projektunabhaengiges Artefakt (ADR-016); geloescht wird
    nur die Ablage in ``tools/`` — es gibt v1 **keinen** projektuebergreifenden
    „ist-referenziert"-Check (Out of Scope). Existiert der Endeffektor nicht, wird
    ``FileNotFoundError`` geworfen (API → 404). Gibt den geloeschten Definitionspfad
    zurueck.
    """
    from fgc.domain.tool import ToolDef, safe_tool_name
    from fgc.paths import TOOLS_DIR

    target_dir = tools_dir or TOOLS_DIR
    stem = safe_tool_name(name)

    tool_path = target_dir / f"{stem}.json"
    if not tool_path.exists():
        raise FileNotFoundError(f"Endeffektor {stem!r} existiert nicht — nichts zu loeschen.")

    # Mesh-Dateiname aus der Definition lesen (bevor sie geloescht wird).
    try:
        existing = ToolDef.load(stem, tools_dir=target_dir)
        mesh_name = existing.mesh
    except Exception:  # noqa: BLE001 — kaputte Definition trotzdem loeschbar
        mesh_name = None

    if mesh_name:
        (target_dir / mesh_name).unlink(missing_ok=True)
    tool_path.unlink()
    return tool_path


# ---------------------------------------------------------------------------
# Workstation-Bibliothek (Issue #72, PRD #69): CRUD auf workstations/<name>.json
# ---------------------------------------------------------------------------


@dataclass
class WorkstationResult:
    """Ergebnis von `create_workstation`/`update_workstation` (Issue #72).

    `path` ist die geschriebene `<name>.json` im Workstation-Verzeichnis
    (Stammdaten, ADR-016), `name` der datei-sichere Name (Identitaet = Dateiname).
    `workstation` ist die geladene, schema-valide `WorkstationDef` — der Aufrufer
    reicht sie ohne Nachladen an den Katalog weiter (analog `CreateToolResult`).
    """

    path: Path
    name: str
    workstation: object  # fgc.domain.workstation.WorkstationDef (kein Import: Zirkel)


def list_workstations(
    *, workstations_dir: Path | None = None
) -> list[object]:
    """Listet alle Workstation-Definitionen aus workstations/ (Issue #72).

    Ueberspringt kaputte/schema-widrige Dateien still (wie `GET /tools`), damit
    eine einzelne fehlerhafte Datei den Katalog nicht sprengt. Gibt die geladenen
    `WorkstationDef`-Objekte zurueck (sortiert nach Dateiname).
    """
    from fgc.domain.workstation import WorkstationDef
    from fgc.paths import WORKSTATIONS_DIR

    base = workstations_dir or WORKSTATIONS_DIR
    result: list[object] = []
    if not base.exists():
        return result
    for path in sorted(base.glob("*.json")):
        try:
            result.append(WorkstationDef.load(path.stem, workstations_dir=base))
        except Exception:  # noqa: BLE001 — kaputte Datei ueberspringen
            continue
    return result


def create_workstation(
    name: str,
    mobility: str,
    height_adjustable: bool,
    *,
    base_heights_mm: list[float] | None = None,
    height_range_mm: dict[str, float] | None = None,
    safety_min_distance_mm: float | None = None,
    vendor: str = "",
    compatible_robots: list[str] | None = None,
    mesh_bytes: bytes | None = None,
    mesh_filename: str | None = None,
    robot_base_frame: dict | None = None,
    work_surface_frame: dict | None = None,
    io_channels: dict | None = None,
    deadtime: dict | None = None,
    workstations_dir: Path | None = None,
) -> WorkstationResult:
    """Legt eine Workstation an: `<name>.json` im Workstation-Verzeichnis (Issue #72).

    Die eine Tuer (ADR-014): baut das schema-valide Artefakt
    (`build_workstation_artifact` — inkl. Hoehen-Branch-Regel), schreibt es
    **atomar** (Temp + `os.replace`, ADR-018, serialisiert per `workstation_lock`)
    und laedt es zur Kontrolle zurueck. Der Name wird datei-sicher normalisiert und
    dient zugleich als Dateiname *und* `name`-Feld. Ein bestehender Eintrag gleichen
    Namens wird ueberschrieben (Stammdaten-Pflege, wie beim Endeffektor).

    **Optionales Mesh (Issue #78, ADR-021):** sind `mesh_bytes`/`mesh_filename`
    gesetzt, wird das Umgebungs-Mesh (STL/OBJ/GLB) wie beim Endeffektor validiert
    (Format/Groesse/Ladbarkeit) und als `<name><suffix>` neben die Definition gelegt;
    `robot_base_frame`/`work_surface_frame` (ADR-006) werden additiv gespeichert.
    Fehlen sie, bleibt die Workstation reine Zahlenfelder wie bisher.

    Wirft `ValueError` bei leerem/degeneriertem Namen, unbekanntem Mesh-Format, zu
    grosser/kaputter/leerer Mesh-Datei, verletzter Hoehen-Branch-Regel oder
    Schema-Verletzung — der Aufrufer uebersetzt das in 422.
    """
    from fgc.domain.tool import mesh_suffix, validate_mesh_bytes
    from fgc.domain.workstation import (
        DEFAULT_SAFETY_MIN_DISTANCE_MM,
        WorkstationDef,
        build_workstation_artifact,
        safe_workstation_name,
        workstation_lock,
        write_workstation_artifact,
    )
    from fgc.paths import WORKSTATIONS_DIR

    base = workstations_dir or WORKSTATIONS_DIR
    stem = safe_workstation_name(name)

    # Mesh validieren, bevor irgendetwas geschrieben wird (wie create_tool_from_upload).
    mesh_name: str | None = None
    if mesh_bytes and mesh_filename:
        suffix = mesh_suffix(mesh_filename)
        validate_mesh_bytes(mesh_bytes, suffix)
        mesh_name = f"{stem}{suffix}"

    artifact = build_workstation_artifact(
        stem,
        mobility,
        height_adjustable,
        base_heights_mm=base_heights_mm,
        height_range_mm=height_range_mm,
        safety_min_distance_mm=(
            safety_min_distance_mm
            if safety_min_distance_mm is not None
            else DEFAULT_SAFETY_MIN_DISTANCE_MM
        ),
        vendor=vendor,
        compatible_robots=compatible_robots,
        mesh=mesh_name,
        robot_base_frame=robot_base_frame,
        work_surface_frame=work_surface_frame,
        io_channels=io_channels,
        deadtime=deadtime,
    )
    path = base / f"{stem}.json"
    with workstation_lock(path):
        base.mkdir(parents=True, exist_ok=True)
        if mesh_bytes and mesh_name:
            (base / mesh_name).write_bytes(mesh_bytes)
        write_workstation_artifact(path, artifact)
        workstation = WorkstationDef.load(stem, workstations_dir=base)
    return WorkstationResult(path=path, name=stem, workstation=workstation)


def update_workstation(
    name: str,
    mobility: str,
    height_adjustable: bool,
    *,
    base_heights_mm: list[float] | None = None,
    height_range_mm: dict[str, float] | None = None,
    safety_min_distance_mm: float | None = None,
    vendor: str = "",
    compatible_robots: list[str] | None = None,
    mesh_bytes: bytes | None = None,
    mesh_filename: str | None = None,
    robot_base_frame: dict | None = None,
    work_surface_frame: dict | None = None,
    io_channels: dict | None = None,
    deadtime: dict | None = None,
    workstations_dir: Path | None = None,
) -> WorkstationResult:
    """Aktualisiert eine bestehende Workstation (Bibliothek-Editor, Issue #72).

    Der Name ist die Identitaet (Dateiname, kein Rename, Out of Scope). Existiert
    die Workstation nicht, wird `FileNotFoundError` geworfen (API → 404). Sonst wie
    `create_workstation`: neues schema-valides Artefakt bauen und **atomar**
    ueberschreiben (Temp + `os.replace`, ADR-018, unter `workstation_lock`).

    **Mesh optional (Issue #78, ADR-021, wie `update_tool_from_upload`):** sind
    `mesh_bytes`/`mesh_filename` leer, bleibt die bestehende Mesh-Datei erhalten;
    ein neu geliefertes Mesh wird validiert + ersetzt (altes Mesh mit abweichendem
    Dateinamen wird entfernt, keine Waise). `robot_base_frame`/`work_surface_frame`
    sind Teil des Request-Zustands (der Editor sendet den vollen Stand): nicht
    mitgesendet = geloescht, gesendet = gesetzt.

    Wirft `ValueError` bei unbekanntem Mesh-Format, kaputter Mesh-Datei, verletzter
    Hoehen-Branch-Regel oder Schema-Verletzung; `FileNotFoundError`, wenn die
    Workstation nicht existiert.
    """
    from fgc.domain.tool import mesh_suffix, validate_mesh_bytes
    from fgc.domain.workstation import (
        DEFAULT_SAFETY_MIN_DISTANCE_MM,
        WorkstationDef,
        build_workstation_artifact,
        safe_workstation_name,
        workstation_lock,
        write_workstation_artifact,
    )
    from fgc.paths import WORKSTATIONS_DIR

    base = workstations_dir or WORKSTATIONS_DIR
    stem = safe_workstation_name(name)
    path = base / f"{stem}.json"
    with workstation_lock(path):
        if not path.exists():
            raise FileNotFoundError(
                f"Workstation {stem!r} existiert nicht — nichts zu aktualisieren."
            )
        existing = WorkstationDef.load(stem, workstations_dir=base)

        # Mesh: nur ersetzen, wenn neue Bytes geliefert wurden; sonst erhalten.
        if mesh_bytes and mesh_filename:
            suffix = mesh_suffix(mesh_filename)
            validate_mesh_bytes(mesh_bytes, suffix)
            mesh_name: str | None = f"{stem}{suffix}"
            if existing.mesh and existing.mesh != mesh_name:
                (base / existing.mesh).unlink(missing_ok=True)
            (base / mesh_name).write_bytes(mesh_bytes)
        else:
            mesh_name = existing.mesh

        artifact = build_workstation_artifact(
            stem,
            mobility,
            height_adjustable,
            base_heights_mm=base_heights_mm,
            height_range_mm=height_range_mm,
            safety_min_distance_mm=(
                safety_min_distance_mm
                if safety_min_distance_mm is not None
                else DEFAULT_SAFETY_MIN_DISTANCE_MM
            ),
            vendor=vendor,
            compatible_robots=compatible_robots,
            mesh=mesh_name,
            robot_base_frame=robot_base_frame,
            work_surface_frame=work_surface_frame,
            io_channels=io_channels,
            deadtime=deadtime,
        )
        write_workstation_artifact(path, artifact)
        workstation = WorkstationDef.load(stem, workstations_dir=base)
    return WorkstationResult(path=path, name=stem, workstation=workstation)


def delete_workstation(name: str, *, workstations_dir: Path | None = None) -> Path:
    """Loescht eine Workstation: `<name>.json` im Workstation-Verzeichnis (Issue #72).

    Die Workstation ist ein projektunabhaengiges Artefakt (ADR-016); geloescht wird
    nur die Ablage in `workstations/` — kein projektuebergreifender
    „ist-referenziert"-Check (Out of Scope, wie beim Endeffektor). Existiert die
    Workstation nicht, wird `FileNotFoundError` geworfen (API → 404). Gibt den
    geloeschten Pfad zurueck.
    """
    from fgc.domain.workstation import safe_workstation_name, workstation_lock
    from fgc.paths import WORKSTATIONS_DIR

    base = workstations_dir or WORKSTATIONS_DIR
    stem = safe_workstation_name(name)
    path = base / f"{stem}.json"
    with workstation_lock(path):
        if not path.exists():
            raise FileNotFoundError(
                f"Workstation {stem!r} existiert nicht — nichts zu loeschen."
            )
        # Optionales Mesh-Geschwister mit entfernen (Issue #78) — keine Waise.
        try:
            mesh = json.loads(path.read_text(encoding="utf-8")).get("mesh")
        except (OSError, ValueError):
            mesh = None
        if mesh:
            (base / mesh).unlink(missing_ok=True)
        path.unlink()
    return path


@dataclass
class DetectBaseHolesResult:
    """Ergebnis von `detect_workstation_base_holes` (Issue #78): Bohrbild-Befund.

    ``matched`` sagt, ob im Workstation-Mesh das Basis-Bohrbild des Roboters gefunden
    wurde; ``robot_base_frame`` ist der daraus abgeleitete Frame ``{pos_mm, quat}``
    (ADR-006, w-first) — ``None``, wenn nichts passte. ``detected_holes`` sind **alle**
    erkannten Loecher (je ``{center_mm, radius_mm, normal}``) fuers UI, unabhaengig vom
    Abgleich. ``warnings`` traegt bei Nicht-Treffer den klaren Befund (Befund, kein
    Gate, ADR-013). ``message`` ist die Kurzfassung fuer die Anzeige.
    """

    matched: bool
    robot_base_frame: dict | None
    detected_holes: list[dict]
    warnings: list[str]
    message: str


def _as_single_mesh(loaded: object):
    """Reduziert ein von trimesh geladenes Objekt auf **ein** Trimesh (Issue #78).

    ``trimesh.load`` liefert je nach Format ein ``Trimesh`` oder eine ``Scene`` (mehrere
    Geometrien); fuers Sectioning brauchen wir ein einzelnes Mesh — Szenen werden
    konkateniert. ``None``, wenn nichts Ladbares uebrig bleibt.
    """
    import trimesh

    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            return None
        return trimesh.util.concatenate(tuple(loaded.geometry.values()))
    return loaded


def detect_workstation_base_holes(
    workstation_name: str,
    robot_name: str,
    *,
    workstations_dir: Path | None = None,
    robots_dir: Path | None = None,
) -> DetectBaseHolesResult:
    """Erkennt das Basis-Bohrbild eines Roboters im Workstation-Mesh (Issue #78, ADR-021).

    Die eine Tuer (ADR-014) fuer den Mesh-Snap der Roboterbasis: laedt die
    WorkstationDef + ihr Umgebungs-Mesh und die RobotDef + ihr ``base_mount``, erkennt
    Durchgangsbohrungen auf der oberen Montageflaeche (`fgc.geometry.holes`) und gleicht
    sie gegen das (provisorische) Bohrbild ab. Passt es, entsteht das ``robot_base_frame``
    (identisch zum manuellen Flaechen-Pick des Viewers). Passt nichts, ist das ein
    **Befund, kein Fehler** (ADR-013): ``matched=False`` mit klarer Warnung.

    Wirft ``FileNotFoundError``, wenn Workstation oder Roboter unbekannt sind;
    ``ValueError``, wenn die Workstation kein Mesh hat, das Mesh unlesbar/leer ist oder
    der Roboter kein ``base_mount`` fuehrt (API -> 422).
    """
    import trimesh

    from fgc.domain.robot import RobotDef
    from fgc.domain.tool import mesh_suffix
    from fgc.domain.workstation import WorkstationDef
    from fgc.geometry.holes import (
        base_mount_to_frame,
        detect_holes_on_top_face,
        match_base_mount,
    )
    from fgc.paths import WORKSTATIONS_DIR

    ws_base = workstations_dir or WORKSTATIONS_DIR
    ws = WorkstationDef.load(workstation_name, workstations_dir=ws_base)  # FileNotFoundError
    if not ws.mesh:
        raise ValueError(
            "Workstation hat kein Mesh — die Bohrbild-Erkennung braucht ein Umgebungs-Mesh."
        )
    mesh_path = ws_base / ws.mesh
    if not mesh_path.exists():
        raise ValueError(f"Mesh-Datei fehlt: {ws.mesh}")
    suffix = mesh_suffix(ws.mesh)
    try:
        loaded = trimesh.load(mesh_path, file_type=suffix.lstrip("."))
    except Exception as exc:  # noqa: BLE001 — jede Ladefehler-Art als ValueError melden
        raise ValueError(f"Mesh-Datei nicht lesbar ({ws.mesh}): {exc}") from exc
    mesh = _as_single_mesh(loaded)
    if mesh is None or len(getattr(mesh, "vertices", [])) == 0:
        raise ValueError(f"Mesh-Datei enthaelt keine Geometrie ({ws.mesh}).")

    robot = RobotDef.load(robot_name, robots_dir=robots_dir)  # FileNotFoundError
    if robot.base_mount is None:
        raise ValueError(
            "Roboter hat kein base_mount — kein Basis-Bohrbild hinterlegt, Abgleich nicht moeglich."
        )

    holes = detect_holes_on_top_face(mesh)
    match = match_base_mount(holes, robot.base_mount)
    detected_holes = [
        {
            "center_mm": [float(c) for c in h.center_mm],
            "radius_mm": float(h.radius_mm),
            "normal": [float(n) for n in h.normal],
        }
        for h in holes
    ]

    if match is None:
        hole_count = int(robot.base_mount["hole_count"])
        warning = (
            f"kein passendes {hole_count}-Loch-Bild gefunden — die Basis bleibt "
            "manuell setzbar (Befund, kein Gate, ADR-013)."
        )
        return DetectBaseHolesResult(
            matched=False,
            robot_base_frame=None,
            detected_holes=detected_holes,
            warnings=[warning],
            message=(
                f"{len(holes)} Loch/Loecher erkannt, aber kein passendes Basis-Bohrbild "
                f"fuer {robot_name!r}."
            ),
        )

    frame = base_mount_to_frame(match)
    return DetectBaseHolesResult(
        matched=True,
        robot_base_frame=frame,
        detected_holes=detected_holes,
        warnings=[],
        message=(
            f"Basis-Bohrbild von {robot_name!r} erkannt (RMS {match.rms_mm:.2f} mm) — "
            "robot_base_frame gesetzt."
        ),
    )


def reassess_walls_for_robot(
    slug: str,
    robot_name: str,
    source: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
) -> ReassessResult:
    """Neubewertung aller Wände für den gewählten Roboter (Issue #20, ADR-016).

    Erzeugt einen neuen Befund-Lauf (walls-list) für ``robot_name`` mit der
    bestehenden Eignungs-Aktion `walls_to_run`, aktualisiert ``project.overview_run``
    auf diesen Lauf (damit die Modellübersicht im Viewer neu einfärbt) und setzt im
    Druckjob ``job_id`` die Felder ``assessment_run`` und ``robot``.
    Existiert kein Druckjob mit ``job_id``, wird nur ``overview_run`` aktualisiert
    (``missing_ok`` des Seams). Geschrieben wird über ``mutate_print_job`` —
    dieselbe Tür wie alle Druckjob-Setter (Issue #199; ``fgc.project`` bleibt die
    eine Schreibstelle, ADR-016).

    VERALTUNG (Issue #29): der Bump auf ``robot`` ist bedingungslos
    (``bump_always``) — jeder Aufruf erzeugt einen frischen Befund-Lauf, gegen den
    nachgelagerte Stände neu entstehen müssen; auch die Neubewertung mit
    *demselben* Roboter veraltet sie (Rebuild-Semantik, kein Diff).

    ``source`` = fertiger reproduzierbarer Aufruf für den Provenienzblock;
    ``projects_dir``/``runs_dir`` überschreiben die Standardverzeichnisse (Test-Seams).
    Wirft ``FileNotFoundError``, wenn das Projekt oder die Roboterdefinition fehlt.
    """
    from fgc.project import (
        JobMutation,
        load_project,
        mutate_print_job,
        project_dir_for,
        project_lock,
    )

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        # Lauf unter der (reentranten) Sperre erzeugen wie bisher; der Seam nimmt
        # denselben Lock erneut (ADR-018) — kein Fenster zwischen Lauf und Schreiben.
        artifact = load_project(project_dir)
        model_path = Path(artifact["model_path"])
        new_run = walls_to_run(model_path, robot_name, source, runs_dir=runs_dir)
        new_run_str = str(new_run.run_dir.resolve())

        def _mutate(job: dict) -> JobMutation:
            return JobMutation(
                job={**job, "assessment_run": new_run_str, "robot": robot_name},
                bump_always=("robot",),
            )

        outcome = mutate_print_job(
            slug, job_id, _mutate,
            missing_ok=True,
            artifact_updates={"overview_run": new_run_str},
            projects_dir=projects_dir,
        )
    return ReassessResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=job_id,
        new_run_dir=new_run.run_dir,
    )


def set_tool_for_job(
    slug: str,
    tool_name: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetToolResult:
    """Setzt den Endeffektor eines Druckjobs im Projekt (Issue #21).

    Laedt das Projekt (via ``fgc.project`` — die einzige Schreibstelle), setzt
    das ``tool``-Feld im Druckjob ``job_id`` auf ``tool_name`` und schreibt
    schema-validiert zurueck. Prueft anschliessend statisch die Traglast
    (Endeffektor-Gewicht vs. Roboter-Traglast) und gibt den Befund mit zurueck.

    Eignung ist ein **Befund, kein Gate** (ADR-013/CONTEXT): auch bei
    Payload-Ueberschreitung wird der Endeffektor gespeichert.

    VERALTUNG (Issue #29, echo-fest seit #199): ein Endeffektor-*Wechsel* bumpt die
    Eingabe-Revision ``tool`` (Druckplan/Simulation/Export veralten); derselbe
    Endeffektor erneut gesetzt bumpt nicht (Diff-dann-bump am Seam).

    Wirft ``FileNotFoundError``, wenn das Projekt oder die Endeffektor-Definition fehlt.
    """
    from fgc.domain.tool import ToolDef
    from fgc.project import JobMutation, mutate_print_job

    def _mutate(job: dict) -> JobMutation:
        # Endeffektor laden (validiert Schema, wirft FileNotFoundError bei Fehlen) —
        # innerhalb des Mutators (nach load_project), damit ein fehlendes Projekt
        # zuerst meldet (Fehler-Reihenfolge byte-gleich zum bisherigen Verhalten).
        tool = ToolDef.load(tool_name)

        # Endeffektorwechsel = neue Eingabe-Revision (Issue #29): der Seam difft den
        # deklarierten Pfad 'tool' und bumpt nur bei tatsaechlicher Aenderung —
        # ein Echo-Schreiben (derselbe Endeffektor) veraltet nichts (Issue #199).
        updated_job = {**job, "tool": tool_name}

        # Statischer Payload-Check (Befund, kein Gate) — Issue #21. Der Roboter des
        # Jobs wird von diesem Setter nicht geändert, also gilt der Befund für den
        # geschriebenen Stand; er reist über den Befund-Rückkanal heraus.
        robot_name = job.get("robot")
        payload_ok: bool | None = None
        payload_margin_kg: float | None = None
        if robot_name:
            try:
                robot = RobotDef.load(robot_name)
                if robot.payload_kg is not None:
                    payload_ok = tool.payload_ok(robot.payload_kg)
                    payload_margin_kg = tool.payload_margin_kg(robot.payload_kg)
            except FileNotFoundError:
                pass  # Roboterdefinition fehlt — Payload-Check ueberspringen

        return JobMutation(
            job=updated_job,
            bump_if_changed={"tool": ("tool",)},
            befund=(payload_ok, payload_margin_kg),
        )

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    payload_ok, payload_margin_kg = outcome.befund
    return SetToolResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        tool_name=tool_name,
        payload_ok=payload_ok,
        payload_margin_kg=payload_margin_kg,
    )


def set_workstation_for_job(
    slug: str,
    workstation_name: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetWorkstationResult:
    """Setzt die Workstation-Wahl eines Druckjobs im Projekt (Issue #77, PRD #69).

    Analog zu `set_tool_for_job`: laedt das Projekt (via ``fgc.project`` — die einzige
    Schreibstelle, ADR-016), setzt das ``workstation``-Feld im Druckjob ``job_id`` auf
    ``workstation_name`` und schreibt schema-validiert zurueck. Prueft anschliessend die
    Kompatibilitaet der Workstation zum Roboter des Jobs (``domain/compat.is_compatible``,
    dieselbe reine Funktion wie beim Endeffektor — #74) und gibt den Befund zurueck.

    **Befund, kein Gate** (ADR-013/CONTEXT): auch eine inkompatible Workstation wird
    gespeichert; der Befund graut in der UI nur aus/warnt.

    VERALTUNG (Issue #83, ADR-017-Nachtrag — Ablösung des #77-Seams): seit #80–82
    treiben die Workstation-Werte (Podesthöhen/Mobilität) den Druckplan-Automatismus
    tatsächlich, daher **bumpt** ein Workstation-Wechsel jetzt die Job-Eingabe
    ``workstation`` → Druckplan/Simulation/Export **und alle Abschnitte** veralten
    (``workstation`` ist Dependency jedes Outputs, siehe ``fgc.project.revisions``).
    Der ursprünglich in #77 bewusste Verzicht (Seam zu #70) ist damit abgelöst, weil
    der Konsument (der Automatismus) jetzt existiert (Design-Log 2026-07-07).
    Echo-fest seit Issue #199: dieselbe Workstation erneut zu setzen bumpt nicht
    (Diff-dann-bump am Seam ``mutate_print_job``).

    Wirft ``FileNotFoundError``, wenn das Projekt oder die Workstation-Definition fehlt;
    ``ValueError``, wenn der Druckjob nicht existiert.
    """
    from fgc.domain.compat import is_compatible
    from fgc.domain.workstation import WorkstationDef
    from fgc.project import JobMutation, mutate_print_job

    def _mutate(job: dict) -> JobMutation:
        # Workstation laden (validiert Schema/Branch-Regel, wirft FileNotFoundError
        # bei Fehlen) — nach load_project (Fehler-Reihenfolge byte-gleich).
        workstation = WorkstationDef.load(workstation_name)

        # Workstation-Wechsel = neue Eingabe-Revision (Issue #83): bump 'workstation'
        # veraltet Druckplan/Simulation/Export und damit alle Abschnitte (global).
        # Der Seam difft den deklarierten Pfad — ein Echo-Schreiben (dieselbe
        # Workstation) veraltet nichts (Issue #199).
        updated_job = {**job, "workstation": workstation_name}

        # Kompatibilitaets-Befund gegen den Roboter des Jobs (Befund, kein Gate) —
        # #74-Filter; der Roboter wird hier nicht geändert.
        robot_name = job.get("robot")
        compatible: bool | None = None
        if robot_name:
            compatible = is_compatible(workstation.compatible_robots, robot_name)

        return JobMutation(
            job=updated_job,
            bump_if_changed={"workstation": ("workstation",)},
            befund=compatible,
        )

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetWorkstationResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        workstation_name=workstation_name,
        compatible=outcome.befund,
    )


def set_stand_mode_for_job(
    slug: str,
    stand_mode: str,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetStandModeResult:
    """Setzt den Aufstell-Toggle eines Druckjobs (Issue #81, PRD B/#70).

    Analog zu `set_workstation_for_job`: laedt das Projekt (via ``fgc.project`` — die
    einzige Schreibstelle, ADR-016), setzt das ``stand_mode``-Feld im Druckjob
    ``job_id`` auf ``floor`` oder ``elevated`` und schreibt schema-validiert zurueck.

    Der Toggle begrenzt, welchen Podesthoehen-Satz die Abschnittssuche der gewaehlten
    Workstation nutzen darf (``fgc.decompose.propose``): ``floor`` erzwingt Bodenhoehe
    (mehr Hoehenbaender), ``elevated`` erlaubt die realen Podesthoehen (weniger Baender).

    BEWUSST OHNE VERALTUNG (wie #77): dieser Setter bumpt **keine** Eingabe-Revision.
    Die Neubewertung stoesst der Druckplan explizit ueber ``propose_decomposition`` an
    (ADR-007) — jener Aufruf liest das gesetzte ``stand_mode`` und bumpt dort ``cutplan``.

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei unbekanntem
    Modus oder fehlendem Druckjob.
    """
    from fgc.placement.suggest import STAND_MODES
    from fgc.project import JobMutation, mutate_print_job

    if stand_mode not in STAND_MODES:
        raise ValueError(
            f"Aufstell-Toggle {stand_mode!r} unbekannt — erlaubt: {list(STAND_MODES)}."
        )

    def _mutate(job: dict) -> JobMutation:
        # BEWUSST kein Bump (leere Deklaration): der Toggle veraltet nichts direkt —
        # die Neubewertung ist der spaetere propose_decomposition-Aufruf (Seam #70).
        return JobMutation(job={**job, "stand_mode": stand_mode})

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetStandModeResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        stand_mode=stand_mode,
    )


def set_context_check_for_job(
    slug: str,
    check_building_context: bool,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetContextCheckResult:
    """Setzt den Gebaeudekontext-Schalter der Kollisionskontrolle (Issue #131, ADR-024).

    Spiegel von `set_stand_mode_for_job`: laedt das Projekt (via ``fgc.project`` — die
    einzige Schreibstelle, ADR-016), setzt das ``check_building_context``-Feld im
    Druckjob ``job_id`` und schreibt schema-validiert zurueck. ``True`` schaltet die
    Pruefung gegen den Gebaeudekontext (context.json, Issue #17) in der Simulation
    **ein**, ``False`` (Default) **aus**. Bei Zerlegungsart Modul ist der Schalter
    gegenstandslos (Workstation ist der Druckort, ADR-022) — die Simulation ignoriert
    ihn dort.

    BEWUSST OHNE VERALTUNG (wie #81): dieser Setter bumpt **keine** Eingabe-Revision.
    Der Schalter wirkt erst bei der naechsten Simulation (kein Output veraltet durch
    reines Umschalten).

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei fehlendem
    Druckjob.
    """
    from fgc.project import JobMutation, mutate_print_job

    enabled = bool(check_building_context)

    def _mutate(job: dict) -> JobMutation:
        # Sparse/additiv: 'aus' entfernt das Feld → Altprojekte byte-gleich; 'ein'
        # setzt es. BEWUSST kein Bump (leere Deklaration, wie #81): der Schalter
        # wirkt erst bei der naechsten Simulation.
        updated_job = {k: v for k, v in job.items() if k != "check_building_context"}
        if enabled:
            updated_job["check_building_context"] = True
        return JobMutation(job=updated_job)

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetContextCheckResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        check_building_context=enabled,
    )


def set_module_limits_for_job(
    slug: str,
    max_length_mm: float | None = None,
    max_height_mm: float | None = None,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetModuleLimitsResult:
    """Setzt die optionalen Obergrenzen der Modulgroesse eines Druckjobs (Issue #90).

    Analog zu `set_stand_mode_for_job`: laedt das Projekt (via ``fgc.project`` — die
    einzige Schreibstelle, ADR-016), setzt den sparse ``module_limits``-Block im
    Druckjob ``job_id`` und schreibt schema-validiert zurueck. ``None`` je Grenze =
    keine Obergrenze; sind beide ``None``, wird der Block entfernt (Altzustand:
    nur der Arbeitsraum begrenzt, ADR-022).

    Die Obergrenzen wirken auf die Rasterverfeinerung der Zerlegungsart „modul"
    (``fgc.decompose.propose``): eine Zelle groesser als eine gesetzte Grenze wird
    weiter geteilt. Das Modulgewicht bleibt bewusst draussen — es ist ein
    **Befund, kein Gate** und wird je Teil im Zerlegungslauf gerechnet.

    BEWUSST OHNE VERALTUNG (wie #81): dieser Setter bumpt **keine** Eingabe-
    Revision — die Neubewertung stoesst der Druckplan explizit ueber
    ``propose_decomposition`` an (ADR-007), jener Aufruf bumpt dort ``cutplan``.

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei einer
    nicht-positiven Grenze oder fehlendem Druckjob.
    """
    from fgc.project import JobMutation, mutate_print_job

    for label, value in (("max_length_mm", max_length_mm), ("max_height_mm", max_height_mm)):
        if value is not None and value <= 0:
            raise ValueError(
                f"Obergrenze {label}={value!r} ist nicht positiv — eine Grenze ist "
                "entweder eine positive Laenge in mm oder ungesetzt (keine Grenze)."
            )

    def _mutate(job: dict) -> JobMutation:
        limits: dict[str, float] = {}
        if max_length_mm is not None:
            limits["max_length_mm"] = float(max_length_mm)
        if max_height_mm is not None:
            limits["max_height_mm"] = float(max_height_mm)

        # BEWUSST kein Bump (leere Deklaration, Muster #81): die Grenzen
        # parametrieren nur den naechsten propose_decomposition-Aufruf.
        updated_job = {**job, "module_limits": limits}
        if not limits:
            updated_job.pop("module_limits", None)
        return JobMutation(job=updated_job, befund=limits)

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetModuleLimitsResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        module_limits=outcome.befund,
    )


def set_objective_for_job(
    slug: str,
    aufwiegen: bool = False,
    weights: dict[str, float] | None = None,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SetObjectiveResult:
    """Setzt die Zielfunktion der Zerlegungs-Suche eines Druckjobs (Issue #212, PRD #183).

    Ein Gewichts-Satz, zwei Lesarten (Grill 2026-07-14): ``aufwiegen=False``
    (Default) liest die Gewichte als **Rangfolge** (lexikographisch), ``True``
    als **gewichtete Summe**. ``weights=None`` = Default-Gewichte (Rangfolge
    Umsetzvorgaenge > Fugenflaeche > kinematische Marge > c_v). Persistiert wird
    sparse (ADR-016, Muster #131): der Default entfernt das ``objective``-Feld —
    Altprojekte bleiben byte-gleich; die Schrittweiten der Quantisierung sind
    Verfahrens-Parameter (Code-Konstanten, nicht Nutzer-Einstellung) und stehen
    nur in der Lauf-Provenienz (ADR-004, ``_persist_decompose_run``).

    VERALTUNG (deklariert, echo-fest — #199): eine tatsaechliche Aenderung bumpt
    die Eingabe-Stufe ``cutplan`` — ein unter der alten Zielfunktion gesuchter
    Zerlegungsplan gilt ehrlich als veraltet (ADR-017); derselbe Wert erneut
    gespeichert bumpt nichts.

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei
    unbekanntem Kriterium, nicht-positivem Gewicht, Gewichts-Gleichstand im
    Aus-Modus (Rangfolge mehrdeutig — die GUI verhindert ihn, der Core weist ihn
    zusaetzlich zurueck) oder fehlendem Druckjob.
    """
    from fgc.decompose.objective import DEFAULT_WEIGHTS, ObjectiveConfig
    from fgc.project import JobMutation, mutate_print_job

    # Validierung der ganzen Config an einer Stelle (Konstruktor-Vertrag):
    # unbekannte Kriterien, nicht-positive Gewichte, Gleichstand im Aus-Modus.
    config = ObjectiveConfig(aufwiegen=bool(aufwiegen), weights=dict(weights or DEFAULT_WEIGHTS))
    effective = {"aufwiegen": config.aufwiegen, "weights": config.to_dict()["weights"]}
    is_default = config.to_dict() == ObjectiveConfig().to_dict()

    def _mutate(job: dict) -> JobMutation:
        # Sparse/additiv (Muster #131): der Default entfernt das Feld →
        # Altprojekte bleiben byte-gleich; sonst Lesart + Gewichte persistieren.
        updated_job = {k: v for k, v in job.items() if k != "objective"}
        if not is_default:
            updated_job["objective"] = effective
        # Echo-fest deklariert (#199): der Seam difft den Pfad und bumpt
        # ``cutplan`` nur bei tatsaechlicher Aenderung der Zielfunktion.
        return JobMutation(job=updated_job, bump_if_changed={"cutplan": ("objective",)})

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetObjectiveResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        objective=effective,
    )


#: Die freien Platzierungsfelder eines Teil-Overrides (Issue #94) — dieselben
#: Achsen wie eine erfasste Aufstellmoeglichkeit (seitlich/Abstand/Aufstellhoehe).
PLACEMENT_OVERRIDE_FIELDS: tuple[str, ...] = ("lateral_mm", "standoff_mm", "stand_height_mm")


def set_placement_override_for_job(
    slug: str,
    section_id: str,
    lateral_mm: float | None = None,
    standoff_mm: float | None = None,
    stand_height_mm: float | None = None,
    job_id: str = "default",
    *,
    merge: bool = False,
    projects_dir: Path | None = None,
) -> SetPlacementOverrideResult:
    """Setzt den freien Platzierungs-Override eines Teils (Issue #94, PRD #88).

    Analog zu `set_module_limits_for_job`: laedt das Projekt (via ``fgc.project`` —
    die einzige Schreibstelle, ADR-016), schreibt die freien Platzierungswerte
    (seitlich/Abstand/Aufstellhoehe, sparse) in den ``section_overrides``-Eintrag
    des Teils ``section_id`` und schreibt schema-validiert zurueck. ``None`` je
    Feld = Feld erbt die automatische (bzw. per ``option_id`` referenzierte)
    Platzierung; alle ``None`` = die freien Werte werden entfernt — traegt der
    Eintrag auch keine ``option_id``-Referenz (Issue #25), faellt er ganz weg und
    das Teil kehrt zur automatischen Platzierung zurueck. Eine bestehende
    ``option_id``-Referenz bleibt unberuehrt (freie Werte uebersteuern sie
    feldweise).

    ``merge`` (Issue #173, Befund B18): standardmaessig (``False``) wird der
    Eintrag aus den uebergebenen Werten **neu aufgebaut** — ein ``None``-Feld
    loescht ein zuvor gesetztes freies Feld (so raeumt das manuelle
    Platzierungs-Formular ein Feld ab). Mit ``merge=True`` bleiben zuvor gesetzte
    freie Felder **erhalten** und nur die uebergebenen (nicht-``None``) Werte
    legen sich feldweise darueber. Das ist der Anwenden-Pfad einer
    **Einzelfeld-Option** des Kollisions-Advisors (Abstand ODER Aufstellhoehe):
    deren Kandidat wurde MIT dem bestehenden Override simuliert und bewertet —
    der angewandte Zustand muss ihm entsprechen, sonst gilt die versprochene
    Marge fuer eine Platzierung, die das Anwenden gar nicht herstellt.

    Es gibt bewusst **kein Werte-Gate**: auch ein Abstand unter dem
    Sicherheits-Mindestabstand der Workstation wird gespeichert — der Core meldet
    ihn beim naechsten Zerlegungslauf als Befund (``placement_check``), kein Gate.

    VERALTUNG (#83-Mechanik, Diff am Seam seit #199): eine tatsaechliche Aenderung
    bumpt NUR den Pro-Abschnitts-Zaehler dieses Teils — nur seine
    Simulation/sein Export veralten, die Nachbarn bleiben aktuell. Die
    Neubewertung (Ampel/erreichbar %/Marge) stoesst der Druckplan explizit ueber
    ``propose_decomposition`` an (ADR-007).

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei einem
    nicht-endlichen Wert oder fehlendem Druckjob.
    """
    import math

    from fgc.project import JobMutation, mutate_print_job

    values = {
        "lateral_mm": lateral_mm,
        "standoff_mm": standoff_mm,
        "stand_height_mm": stand_height_mm,
    }
    for label, value in values.items():
        if value is not None and not math.isfinite(float(value)):
            raise ValueError(
                f"Platzierungs-Override {label}={value!r} ist keine endliche Zahl — "
                "ein Feld ist entweder ein Wert in mm oder ungesetzt (erbt)."
            )
    free = {k: float(v) for k, v in values.items() if v is not None}
    sid = str(section_id)

    def _mutate(job: dict) -> JobMutation:
        entries = list(job.get("section_overrides") or [])
        old_entry = next((e for e in entries if str(e.get("section_id")) == sid), None)

        new_entry: dict | None = {"section_id": sid}
        if old_entry is not None and old_entry.get("option_id") is not None:
            # Bestehende Referenz (Issue #25) bewahren — freie Werte sind eine
            # zusaetzliche, feldweise Ebene darueber.
            new_entry["option_id"] = old_entry["option_id"]
        if merge and old_entry is not None:
            # Merge (Issue #173): zuvor gesetzte freie Felder des Teils bewahren;
            # die uebergebenen sparse Werte legen sich unten feldweise darueber.
            new_entry.update(
                {k: v for k, v in old_entry.items() if k in PLACEMENT_OVERRIDE_FIELDS}
            )
        new_entry.update(free)
        has_free = any(k in new_entry for k in PLACEMENT_OVERRIDE_FIELDS)
        if not has_free and "option_id" not in new_entry:
            new_entry = None  # alles leer -> Eintrag entfernen (zurueck auf Automatik)

        rest = [e for e in entries if str(e.get("section_id")) != sid]
        new_entries = rest + ([new_entry] if new_entry is not None else [])

        updated_job = {**job, "section_overrides": new_entries}
        if not new_entries:
            # Wie zuvor gespeichert bleiben: ein leerer Block ist gueltig — aber ein
            # Altprojekt ohne Feld soll keins bekommen, wenn nichts uebersteuert ist.
            if "section_overrides" not in job:
                updated_job.pop("section_overrides", None)

        # Feingranulare Veraltung (#83): nur bei tatsaechlicher Aenderung bumpen,
        # und nur den Zaehler DIESES Teils — die Nachbarn bleiben aktuell. Das Diff
        # rechnet der Seam (Issue #199): deklariert wird nur der beobachtete,
        # section-gekeyte Pfad.
        stored = {k: v for k, v in (new_entry or {}).items() if k != "section_id"}
        return JobMutation(
            job=updated_job,
            bump_sections_if_changed="section_overrides",
            befund=stored,
        )

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetPlacementOverrideResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        section_id=sid,
        override=outcome.befund,
    )


def set_process_params(
    slug: str,
    slice_params: dict,
    job_id: str = "default",
    *,
    orientation: dict | None = None,
    ik_config: dict | None = None,
    sections: dict | None = None,
    projects_dir: Path | None = None,
) -> SetProcessParamsResult:
    """Setzt die ``process_params``-Gruppen eines Druckjobs (Scheibe 2/3, #59/#61).

    Der End-to-End-Durchstich für die Prozessparameter. Zwei Gruppen auf einer Rail:

    - ``slice`` (Scheibe 2): Basis-Slice-Parameter (Schichthöhe, Strangbreite,
      Schalen), die ``simulate_section`` beim Slicen liest (statt nur aus der
      Prozessfenster-Karte).
    - ``orientation`` (Scheibe 3): der bahn-relative Anstellwinkel in **Grad**
      (``lead_deg``/``kipp_deg``), den Slicer *und* ``placement`` über dieselbe
      Funktion ``fgc.domain.orientation.nozzle_quat`` verrechnen — Kipp beeinflusst
      damit die Erreichbarkeits-Ampel.
    - ``ik_config`` (Issue #129, ADR-024): die drei Tri-State-IK-Schalter
      (``shoulder``/``elbow``/``wrist``, je ``"a"``/``"b"``/fehlend=auto), die
      ``simulate_section`` als harten Filter über die 8 Lösungszweige liest.
      ``ik_config=None`` lässt die bestehende Gruppe unberührt (wie ``orientation``).

    Je Gruppe werden nur *gesetzte* Felder (nicht ``None``) übernommen; ist eine
    Gruppe komplett leer, wird ihr Block entfernt (zurück auf Karten-/Code-Defaults
    bzw. senkrecht-von-oben). ``orientation=None`` lässt die bestehende
    Orientierungsgruppe unberührt (getrennt speicherbar). `fgc.project` bleibt die
    einzige, schema-validierte Schreibstelle (ADR-016).

    Die **Gradierungs-Ebene** (Issue #82): ``sections`` bildet ``section_id`` →
    ``{"slice": {...}, "orientation": {...}}`` sparse ab — je Abschnitt dürfen
    dieselben Felder wie global übersteuert werden; ungesetzte erben global
    (``domain.process_params.resolve_section_params``). ``sections=None`` lässt den
    bestehenden ``sections``-Block unberührt (getrennt vom globalen Speichern);
    ein leerer/leer-gereinigter Abschnitt fällt weg, alle leer → der Block wird
    entfernt (Abschnitt erbt wieder komplett global).

    Veraltung **feingranular** (Issue #83, ADR-017-Nachtrag): Eine Änderung der
    *globalen* Gruppen (``slice``/``orientation``) bumpt die Prozessparameter-Revision
    (``process``) → Zerlegung/Simulation/Export und **alle** Abschnitte veralten. Eine
    reine **Abschnitts-Override**-Änderung (``sections[id]``) bumpt hingegen nur den
    Pro-Abschnitts-Zähler dieses Abschnitts → nur dessen Simulation/Export veraltet,
    die Nachbarn bleiben aktuell (``section_output_status``, Python↔TS-Parität). Kein
    Löschen: nachgelagerte Stände bleiben sichtbar, nur markiert.

    Wirft ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError``, wenn der
    Druckjob nicht existiert oder das Projekt schema-widrig würde (write_project).
    """
    from fgc.domain.process_params import (
        IK_CONFIG_KEYS,
        IO_PARAM_KEYS,
        ORIENTATION_PARAM_KEYS,
        SLICE_PARAM_KEYS,
    )
    from fgc.project import JobMutation, mutate_print_job

    def _mutate(job: dict) -> JobMutation:
        # Nur gesetzte, bekannte Slice-Felder übernehmen (partielle Overrides).
        # Skalare Basisparameter (SLICE_PARAM_KEYS: Schichthöhe/Strangbreite/Schalen +
        # Geschwindigkeiten, Issue #60) und die skalaren io-Werte (IO_PARAM_KEYS:
        # io_print/io_travel je als ein Skalar, Issue #60) — im Job liegen io als
        # Skalar; job_slice_overrides dehnt sie beim Lesen auf die Kanäle aus.
        slice_keys = SLICE_PARAM_KEYS + IO_PARAM_KEYS
        clean = {k: slice_params[k] for k in slice_keys if slice_params.get(k) is not None}

        # Bestehenden process_params-Block bewahren: nur die betroffene Gruppe
        # ersetzen/entfernen, Rest unberührt (Rail für weitere Gruppen).
        process_params = {k: v for k, v in (job.get("process_params") or {}).items()}
        if clean:
            process_params["slice"] = clean
        else:
            process_params.pop("slice", None)

        # Orientierungsgruppe (Scheibe 3, Issue #61) — nur wenn mitgeliefert.
        if orientation is not None:
            ori_clean = {
                k: orientation[k] for k in ORIENTATION_PARAM_KEYS if orientation.get(k) is not None
            }
            if ori_clean:
                process_params["orientation"] = ori_clean
            else:
                process_params.pop("orientation", None)

        # IK-Konfigurationsgruppe (Issue #129, ADR-024) — nur wenn mitgeliefert. Je
        # Achse (shoulder/elbow/wrist) "a"/"b" oder fehlend (auto); nur gesetzte
        # Achsen bleiben. Alle auto → der Block entfällt (auto/auto/auto, heutiges
        # Verhalten, byte-gleich zu Altprojekten).
        if ik_config is not None:
            ik_clean = {
                k: ik_config[k] for k in IK_CONFIG_KEYS if ik_config.get(k) is not None
            }
            if ik_clean:
                process_params["ik_config"] = ik_clean
            else:
                process_params.pop("ik_config", None)

        # Abschnitts-Overrides (Gradierungs-Ebene, Issue #82; ik_config Issue #129) —
        # nur wenn mitgeliefert. Je Abschnitt dieselben gesetzten Felder wie global
        # reinigen; leere Gruppen und leere Abschnitte fallen weg, alles leer → der
        # sections-Block entfällt.
        if sections is not None:
            sections_clean: dict = {}
            for section_id, override in sections.items():
                override = override or {}
                slice_over = {
                    k: (override.get("slice") or {})[k]
                    for k in slice_keys
                    if (override.get("slice") or {}).get(k) is not None
                }
                ori_over = {
                    k: (override.get("orientation") or {})[k]
                    for k in ORIENTATION_PARAM_KEYS
                    if (override.get("orientation") or {}).get(k) is not None
                }
                ik_over = {
                    k: (override.get("ik_config") or {})[k]
                    for k in IK_CONFIG_KEYS
                    if (override.get("ik_config") or {}).get(k) is not None
                }
                section_block = {}
                if slice_over:
                    section_block["slice"] = slice_over
                if ori_over:
                    section_block["orientation"] = ori_over
                if ik_over:
                    section_block["ik_config"] = ik_over
                if section_block:
                    sections_clean[section_id] = section_block
            if sections_clean:
                process_params["sections"] = sections_clean
            else:
                process_params.pop("sections", None)

        updated_job = {k: v for k, v in job.items() if k != "process_params"}
        if process_params:
            updated_job["process_params"] = process_params

        # Feingranulare Veraltung (Issue #83, ADR-017-Nachtrag): NUR eine Änderung an
        # den *globalen* Gruppen (slice/orientation/ik_config) bumpt die Job-Eingabe
        # ``process`` → Druckplan/Simulation/Export und ALLE Abschnitte veralten. Eine
        # reine Abschnitts-Override-Änderung (process_params.sections[id]) bumpt
        # hingegen NUR den Pro-Abschnitts-Zähler dieses Abschnitts → nur dessen
        # Simulation/Export veraltet, die Nachbarn bleiben aktuell. So veraltet nicht
        # jede Kleinigkeit den ganzen Job. Das Diff rechnet der Seam (Issue #199,
        # Diff-dann-bump): deklariert werden nur die beobachteten Pfade — ein
        # unverändertes Mitsenden der globalen Werte (Viewer echot sie beim
        # Abschnitts-Speichern) löst damit keinen Bump aus.
        return JobMutation(
            job=updated_job,
            bump_if_changed={
                "process": (
                    "process_params.slice",
                    "process_params.orientation",
                    "process_params.ik_config",
                ),
            },
            bump_sections_if_changed="process_params.sections",
            befund=clean,
        )

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SetProcessParamsResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        slice_params=outcome.befund,
    )


def evaluate_placements(
    slug: str,
    options: list[dict],
    source: str,
    job_id: str = "default",
    *,
    selected: str | None = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    collision_predicate: Any = None,
    feasibility: dict | None = None,
) -> PlacementEvalResult:
    """Bewertet reale Aufstellmöglichkeiten eines Druckjobs (Platzierung, Issue #22).

    Bewertungsmodus (Grill-Entscheidung 2026-07-04): der Nutzer gibt seine realen
    Aufstellmöglichkeiten vor, der Core bewertet sie mit dem deep module
    `fgc.placement` (erreichbarer Wandanteil + kinematische Marge). Die Bewertung
    wird als provenienz-gestempelter **Lauf** (placement.json, ADR-004) abgelegt;
    im Druckjob werden nur die *Plan-Eingaben* (Aufstellmöglichkeiten), die Wahl
    (`selected_placement`) und der *Verweis* auf den Lauf persistiert — nie die
    Scores (ADR-016).

    `options` = Liste von Dicts mit `option_id`, `lateral_mm`, `standoff_mm`,
    `stand_height_mm` (optional `yaw_rad`). Roboter und Endeffektor kommen aus dem
    Druckjob (Issue #20/#21); der Roboter **muss** gesetzt sein (Kinematik nötig),
    ein fehlender Endeffektor wird mit einem Null-TCP (Düse am Flansch) behandelt.

    ``collision_predicate`` (Issue #228, ADR-026): ein optionales ``option -> bool``
    (kollisionsfrei?). Gesetzt, trägt jeder Score das explizite Machbarkeits-Feld
    (``collision``); ``feasibility`` reicht den vom Optimalvorschlag gerechneten
    Gesamt-Befund an die API-Antwort durch. ``None`` (Bewertungsmodus) ⇒ kein
    Kollisionsfeld, byte-gleich zum Reichweiten-Zustand.

    Wirft `FileNotFoundError`, wenn das Projekt fehlt; `ValueError` bei fehlendem
    Druckjob/Roboter, fehlendem Befund-Lauf oder unbekannter Wand.
    """
    import dataclasses as _dc

    from fgc.domain.process_params import job_orientation
    from fgc.kinematics import IkConfigFilter
    from fgc.placement import PlacementOption, evaluate, placement_artifact
    from fgc.placement.suggest import collision_judgment
    from fgc.project import (
        load_project,
        project_dir_for,
        project_lock,
        refresh_output,
        write_project,
    )

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)

        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        pc = placement_context_for_job(job)
        robot, tool, wall = pc.robot, pc.tool, pc.wall

        parsed_options = [
            PlacementOption(
                option_id=str(o["option_id"]),
                lateral_mm=float(o["lateral_mm"]),
                standoff_mm=float(o["standoff_mm"]),
                stand_height_mm=float(o["stand_height_mm"]),
                yaw_rad=float(o.get("yaw_rad", 0.0)),
            )
            for o in options
        ]
        # Prior-gefuehrt gewaehlte IK-Konfiguration je Option (Issue #233, ADR-026
        # Punkt 5): der Optimalvorschlag reicht sie als a/b-Block mit. Bewertet wird
        # unter genau diesem Zweig (``config_filter``) — so bleibt der persistierte
        # Score konsistent mit der Vorschlags-Bewertung. Manuelle Optionen ohne Block
        # laufen unter ``auto`` (byte-gleich zu vorher).
        ik_blocks = {
            str(o["option_id"]): (o.get("ik_config") or None) for o in options
        }
        ori = job_orientation(job)
        # Reichweitenkarte als Vorfilter/Schaetzer (Issue #214, US 7): fail-soft None
        # ohne Karte (dann kein reach_estimate → Artefakt byte-gleich, US 12), mit
        # Karte traegt jede Option ihre gekennzeichnete Schaetzung. Ampel unveraendert.
        reach_map = _reach_map_for_robot(pc.robot_name)
        results = []
        for opt in parsed_options:
            ik_block = ik_blocks.get(opt.option_id)
            config_filter = IkConfigFilter.from_block(ik_block) if ik_block else None
            score = evaluate(
                wall, robot, tool, opt,
                lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad, reach_map=reach_map,
                config_filter=config_filter,
            )
            # Gewählte IK-Konfiguration als sichtbares Score-Feld (Issue #233): nur
            # ein echter Zweig (nicht-leerer Block) — ``auto`` bleibt implizit.
            if ik_block:
                score = _dc.replace(score, ik_config=dict(ik_block))
            # Explizites Machbarkeits-Feld je Option (Issue #228): nur wenn ein
            # Grob-Check-Prädikat vorliegt (Optimalvorschlag-Pfad). Fail-soft: ein
            # Fehler je Option lässt das Feld weg (Befund, kein Gate).
            if collision_predicate is not None:
                try:
                    score = _dc.replace(
                        score, collision=collision_judgment(bool(collision_predicate(opt)))
                    )
                except Exception:
                    pass
            results.append((opt, score))

        option_ids = {opt.option_id for opt in parsed_options}
        chosen = selected if selected in option_ids else None

        run = Run.create("placement", slug, source=source, runs_dir=runs_dir)
        run.write(
            "placement",
            placement_artifact(
                pc.robot_name,
                pc.tool_name,
                wall,
                results,
                run.provenance,
                wall_global_id=job["wall_global_id"],
                selected=chosen,
            ),
        )
        run_str = str(run.dir.resolve())

        # Druckjob aktualisieren: nur Plan-Eingaben + Wahl + Lauf-Verweis (ADR-016).
        # Die gewählte IK-Konfiguration (Issue #233) zählt zu den Plan-Eingaben — sie
        # fährt beim Übernehmen (``select_placement``) in die Simulation. Nur ein echter
        # Zweig wird persistiert; manuelle Optionen bleiben byte-gleich.
        new_placements = []
        for opt in parsed_options:
            entry = {
                "option_id": opt.option_id,
                "lateral_mm": opt.lateral_mm,
                "standoff_mm": opt.standoff_mm,
                "stand_height_mm": opt.stand_height_mm,
                "yaw_rad": opt.yaw_rad,
            }
            ik_block = ik_blocks.get(opt.option_id)
            if ik_block:
                entry["ik_config"] = dict(ik_block)
            new_placements.append(entry)
        old_runs = job.get("runs", [])
        updated_job = {
            **job,
            "placements": new_placements,
            "selected_placement": chosen,
            "placement_run": run_str,
            "runs": [*old_runs, run_str],
        }
        # Druckplan-Stufe neu erzeugt (Issue #29): Schnappschuss auf die aktuellen
        # Eingabe-Revisionen — hebt eine etwaige veraltet-Markierung des Druckplans auf.
        updated_job = refresh_output(updated_job, "druckplan")
        new_jobs = [updated_job if j["job_id"] == job_id else j for j in artifact["print_jobs"]]
        updated_artifact = {**artifact, "print_jobs": new_jobs}
        path = write_project(project_dir, updated_artifact)

    scored = [
        {
            "option_id": opt.option_id,
            "lateral_mm": opt.lateral_mm,
            "standoff_mm": opt.standoff_mm,
            "stand_height_mm": opt.stand_height_mm,
            "yaw_rad": opt.yaw_rad,
            "score": score.to_dict(),
        }
        for opt, score in results
    ]
    return PlacementEvalResult(
        project_dir=project_dir,
        project_path=path,
        artifact=updated_artifact,
        job_id=job_id,
        run_dir=run.dir,
        scored=scored,
        selected=chosen,
        feasibility=feasibility,
    )


def select_placement(
    slug: str,
    option_id: str | None,
    job_id: str = "default",
    *,
    projects_dir: Path | None = None,
) -> SelectPlacementResult:
    """Markiert eine Aufstellmöglichkeit als gewählt (Platzierung, Issue #22/#233).

    Setzt `selected_placement` im Druckjob — ohne Neubewertung: die Wahl ist ein
    reiner Plan-Zustand im Projekt (ADR-016), die Scores bleiben im
    unveränderlichen Bewertungslauf (ADR-004). `option_id=None` hebt die Wahl auf.

    **IK-Konfiguration mitübernehmen (Issue #233, ADR-026 Punkt 5).** Trägt die
    gewählte Aufstellmöglichkeit einen `ik_config`-Block (den vom Optimalvorschlag
    prior-geführt gefundenen Sieger-Zweig), wird er in `process_params.ik_config`
    übernommen — so fährt die Simulation nachweislich **dieselbe** Konfiguration wie
    die Bewertung (der Kern liest den Block über dieselbe `IkConfigFilter.from_block`-
    Tür). Manuelle Aufstellmöglichkeiten ohne Block lassen `process_params`
    unberührt (byte-gleich zu vorher). Eine tatsächliche Änderung an
    `process_params.ik_config` veraltet Druckplan/Simulation/Export (Bump), damit
    die Simulation den neuen Zweig neu fährt.

    Wirft `FileNotFoundError`, wenn das Projekt fehlt; `ValueError`, wenn der
    Druckjob fehlt oder die option_id keiner erfassten Aufstellmöglichkeit gehört.
    """
    from fgc.domain.process_params import IK_CONFIG_KEYS
    from fgc.project import JobMutation, mutate_print_job

    def _mutate(job: dict) -> JobMutation:
        selected_placement = None
        if option_id is not None:
            by_id = {p["option_id"]: p for p in job.get("placements", [])}
            if option_id not in by_id:
                raise ValueError(
                    f"Aufstellmöglichkeit {option_id!r} ist im Druckjob {job_id!r} nicht "
                    f"erfasst — vorhanden: {sorted(by_id)}. Zuerst bewerten (evaluate_placements)."
                )
            selected_placement = by_id[option_id]

        new_job = {**job, "selected_placement": option_id}

        # Sieger-Konfig des Vorschlags übernehmen (Issue #233): nur ein echter a/b-Block
        # (nicht-leer) übersteuert; ohne Block bleibt process_params unberührt.
        ik_block = (selected_placement or {}).get("ik_config")
        ik_clean = (
            {k: ik_block[k] for k in IK_CONFIG_KEYS if ik_block.get(k) is not None}
            if ik_block
            else {}
        )
        if ik_clean:
            process_params = dict(new_job.get("process_params") or {})
            process_params["ik_config"] = ik_clean
            new_job["process_params"] = process_params
            # Nur bei echter Änderung an ik_config bumpt der Seam (echo-fest, #199).
            return JobMutation(
                job=new_job,
                bump_if_changed={"process": ("process_params.ik_config",)},
            )
        # Reine Plan-Wahl (manuelle Lage / Wahl aufheben) → BEWUSST kein Bump.
        return JobMutation(job=new_job)

    outcome = mutate_print_job(slug, job_id, _mutate, projects_dir=projects_dir)
    return SelectPlacementResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
        selected=option_id,
    )


@dataclass
class CollisionAdviceResult:
    """Ergebnis von `advise_collision` (Issue #130): Basis-Befund + gerankte Optionen.

    Rein beratend (ADR-007): der Core re-simuliert jeden Hebel-Kandidaten mit
    *derselben* Maschinerie und liest denselben ``meta.collision``-Befund (#127) —
    keine Parallel-Metrik. ``baseline`` ist die Basis-Metrik (min. Abstand/Marge/
    kollisionsfrei) der aktuellen Simulation, ``options`` die nach Ranking sortierte
    Liste gangbarer Optionen (nur Verbesserer, jede mit Schreibstellen-Nutzlast).
    ``section_id`` ist der bewertete Abschnitt (``None`` = kein Abschnitt vorhanden).
    """

    job_id: str
    section_id: str | None
    baseline: dict | None
    options: list[dict]


def advise_collision(
    slug: str,
    job_id: str = "default",
    section_id: str | None = None,
    *,
    projects_dir: Path | None = None,
    workstations_dir: Path | None = None,
    collision_config: CollisionConfig | None = None,
    include_options: bool = True,
) -> CollisionAdviceResult:
    """Berät zum Kollisionsbefund eines Abschnitts mit gerankter Optionsliste (Issue #130).

    Läuft auf Knopfdruck (teuer): baut den Basis-Befund der Simulation und probiert
    die drei Hebel (IK-Konfiguration, Kipp/Lead, Platzierung) durch **Neu-Simulation**
    über die geteilte Kern-Tür :func:`fgc.pipeline.sectionsim.slice_and_simulate_section`
    — dieselbe Maschinerie,
    denselben ``meta.collision``-Befund (keine Parallel-Metrik, ADR-024). Der reine
    Advisor (``fgc.collision.advisor``) rankt; das *Anwenden* schreibt der Aufrufer
    danach über die bestehenden Setter (``process-params``/``placement-override``,
    ADR-016). Read-only hier — es wird nichts geschrieben.

    ``include_options=False`` (Prüf-UX, Karte #139/#145): nur der **Basis-Befund**
    entsteht — genau *eine* Neu-Simulation statt Basis + ~17 Kandidaten. So bekommt
    „Kollision prüfen" eine ~20-s-Antwort; die teure Optionssuche bleibt ein
    eigener, bewusster Schritt. Der loop-invariante Unterbau (IFC laden, Zerlegung,
    Basis-Parameter) entsteht in beiden Fällen **einmal** (``SectionSimContext``)
    und wird an alle Kandidaten-Simulationen gereicht.

    ``section_id=None`` wählt den ersten Abschnitt des Zerlegungsplans. Wirft
    ``FileNotFoundError``, wenn das Projekt fehlt; ``ValueError`` bei fehlendem
    Druckjob/Roboter.
    """
    from fgc.collision.advisor import CollisionMetric, Override, advise, build_candidates
    from fgc.project import load_project, project_dir_for

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    artifact = load_project(project_dir)
    job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
    if job is None:
        raise ValueError(
            f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
            "Zuerst eine Wand übernehmen (set_print_job)."
        )

    # Abschnitt auflösen (Default: erster Abschnitt des rekonstruierten Plans).
    pc = placement_context_for_job(job)
    plan = plan_for_job(
        job, pc.wall, pc.robot, pc.tool,
        strict_overrides=False, workstations_dir=workstations_dir,
    ).plan
    sids = [sp.section.section_id for sp in plan.sections]
    if not sids:
        return CollisionAdviceResult(job_id, None, None, [])
    resolved = section_id if section_id in sids else sids[0]
    idx = sids.index(resolved)
    placement = plan.sections[idx].placement

    # Loop-invarianten Unterbau EINMAL bauen (IFC laden, Zerlegung, Basis-Parameter)
    # und an alle Neu-Simulationen reichen — vorher lief er je Kandidat neu (~18×).
    ctx = section_sim_context(
        artifact, job, resolved, workstations_dir=workstations_dir, plan=plan,
    )

    def simulate(override: Override | None) -> dict | None:
        comp = slice_and_simulate_section(
            artifact, job, resolved, override=override,
            workstations_dir=workstations_dir, ctx=ctx,
        )
        # Dieselbe Hindernis-Wahrheit wie die echte Simulation (Issue #135/#192,
        # keine Parallel-Metrik): Boden bei lokal −z0 + frühere Teile aus ``comp``.
        return section_collision_finding(comp, config=collision_config)

    # Basis-Befund (ohne Override) — er liefert die Vorher-Metrik und sagt zugleich,
    # ob überhaupt Kollisionsgeometrie da ist (None ⇒ nichts zu beraten).
    baseline_finding = simulate(None)
    if baseline_finding is None:
        return CollisionAdviceResult(job_id, resolved, None, [])

    # Nur-Befund (include_options=False): der schnelle „Kollision prüfen"-Pfad —
    # eine Neu-Simulation, dieselbe Metrik, keine Kandidaten (Prüf-UX #139/#145).
    if not include_options:
        baseline = CollisionMetric.from_finding(baseline_finding)
        return CollisionAdviceResult(
            job_id, resolved, baseline.to_dict() if baseline is not None else None, [],
        )

    ori_block = (job.get("process_params") or {}).get("orientation") or {}
    ik_block = (job.get("process_params") or {}).get("ik_config") or {}
    candidates = build_candidates(
        section_id=resolved,
        lead_deg=float(ori_block.get("lead_deg", 0.0)),
        kipp_deg=float(ori_block.get("kipp_deg", 0.0)),
        ik_config={k: str(v) for k, v in ik_block.items()},
        lateral_mm=float(placement.lateral_mm),
        standoff_mm=float(placement.standoff_mm),
        stand_height_mm=float(placement.stand_height_mm),
    )

    # Reichweitenkarte als Vorfilter (Issue #214, US 8): verwirft Platzierungs-
    # Gegenmassnahmen, die die Wand laut Karte gar nicht mehr erreichen, VOR der
    # teuren Neu-Simulation → kuerzere Antwort. Nur der Platzierungs-Hebel bewegt die
    # Basis; die anderen Hebel und der fehlende-Karte-Fall bleiben erreichbar
    # (lenient, fail-soft) — Befund, kein Gate; die Karte filtert, urteilt nie.
    reachable = _reach_predicate_for_placement(
        _reach_map_for_robot(pc.robot_name), pc.wall, pc.tool, placement,
        lead_deg=float(ori_block.get("lead_deg", 0.0)),
        kipp_deg=float(ori_block.get("kipp_deg", 0.0)),
    )
    result = advise(baseline_finding, candidates, simulate, reachable=reachable)
    return CollisionAdviceResult(
        job_id=job_id,
        section_id=resolved,
        baseline=result.baseline.to_dict() if result.baseline is not None else None,
        options=[o.to_dict() for o in result.options],
    )


@dataclass
class ClearanceCheckResult:
    """Ergebnis von :func:`check_section_clearance` (Issue #162): frei/kollidiert je Teil.

    Die **Pruef-Tuer der Zerlegung** — reine Core-Rechnung **ohne Lauf-Artefakt**
    (ADR-007-Geist: der Core urteilt). ``verdict`` ist das kompakte Urteil
    (``ClearanceVerdict.to_dict()``: ``collides`` + Verursacher/Eindringtiefe) der
    verduennten ``find_collisions``-Instanz oder ``None`` (kein Kollisions-Geometrie-
    Artefakt / kein Abschnitt vorhanden). ``section_id`` ist der geprüfte Abschnitt.
    """

    job_id: str
    section_id: str | None
    verdict: dict | None


def check_section_clearance(
    slug: str,
    job_id: str = "default",
    section_id: str | None = None,
    *,
    override: Any = None,
    ctx: SectionSimContext | None = None,
    projects_dir: Path | None = None,
    workstations_dir: Path | None = None,
    collision_config: CollisionConfig | None = None,
    travel_stride: int | None = None,
) -> ClearanceCheckResult:
    """Pruef-Tuer der Zerlegung: kollidiert **ein** Teil + Option in wenigen Sekunden? (#162).

    Die wiederverwendbare, **verduennte Instanz des echten Kollisionsbefunds** (Karte
    #139, Entscheidung #141, Scheibe 1): für einen Abschnitt (Teil-Rechteck) + eine
    Option (``override``: Platzierung und/oder IK-Konfiguration, ein
    ``fgc.collision.advisor.Override``) slict + simuliert sie **einmal** über die
    geteilte Kern-Tür :func:`fgc.pipeline.sectionsim.slice_and_simulate_section`
    und urteilt mit der **Travel-
    ausgeduennten** ``find_collisions``-Instanz (``fgc.collision.finding.
    check_part_clearance``) — Sekunden statt ~11,5 s, **ohne** strukturellen
    Blindfleck (S6 disqualifizierte den Grob-Check ``path_collides``).

    Reuse für die spätere Verfeinerung (#165): ein vorgebauter ``ctx``
    (:class:`fgc.pipeline.sectionsim.SectionSimContext` desselben Abschnitts) überspringt den loop-
    invarianten Unterbau (IFC laden, Zerlegung, Basis-Parameter) und teilt den
    Toolpath-Cache — so kostet das Durchprobieren vieler Optionen (die den Toolpath
    nicht ändern: IK, Platzierung) nur je eine Neu-Trajektorie + Pruef-Tuer. Ohne
    ``ctx`` wird er hier gebaut.

    ``travel_stride`` steuert die Ausduennung (Default
    :data:`fgc.collision.finding.DEFAULT_TRAVEL_STRIDE`). Read-only: es wird **nichts**
    geschrieben (kein Lauf, keine Projekt-Mutation). Wirft ``FileNotFoundError``, wenn
    das Projekt fehlt; ``ValueError`` bei fehlendem Druckjob/Roboter, bei einer
    unbekannten ``section_id`` (**keine** stille Substitution durch den ersten
    Abschnitt, Issue #169/B4 — dieselbe Strenge wie beim Druckjob) oder wenn ein
    vorgereichter ``ctx`` einem abweichend übergebenen ``section_id`` widerspricht
    (Kontext-vs-ID-Konflikt, ebenfalls #169).
    """
    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE
    from fgc.project import load_project, project_dir_for

    stride = DEFAULT_TRAVEL_STRIDE if travel_stride is None else int(travel_stride)

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    artifact = load_project(project_dir)
    job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
    if job is None:
        raise ValueError(
            f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
            "Zuerst eine Wand übernehmen (set_print_job)."
        )

    # Abschnitt auflösen (Default: erster Abschnitt des rekonstruierten Plans) — wie
    # der Kollisions-Advisor (#130). Ein vorgereichter ctx nennt den Abschnitt selbst.
    # Issue #169 (B4): eine unbekannte section_id wird NICHT mehr still durch sids[0]
    # ersetzt — dieselbe Strenge wie beim Druckjob oben. Ein ctx, dessen Abschnitt vom
    # explizit übergebenen section_id abweicht, ist ein Kontext-vs-ID-Konflikt und wird
    # zurückgewiesen statt still (zugunsten des ctx) aufgelöst.
    pc = placement_context_for_job(job)
    plan = ctx.plan if ctx is not None else plan_for_job(
        job, pc.wall, pc.robot, pc.tool,
        strict_overrides=False, workstations_dir=workstations_dir,
    ).plan
    sids = [sp.section.section_id for sp in plan.sections]
    if not sids:
        return ClearanceCheckResult(job_id, None, None)
    if ctx is not None:
        if section_id is not None and section_id != ctx.section.section_id:
            raise ValueError(
                f"Abschnitt {section_id!r} widerspricht dem übergebenen Kontext "
                f"(ctx-Abschnitt {ctx.section.section_id!r}) für Druckjob {job_id!r} "
                "— section_id und ctx müssen denselben Abschnitt meinen."
            )
        resolved = ctx.section.section_id
    elif section_id is None:
        resolved = sids[0]
    elif section_id in sids:
        resolved = section_id
    else:
        raise ValueError(
            f"Abschnitt {section_id!r} existiert nicht in der Zerlegung von "
            f"Druckjob {job_id!r} (vorhanden: {sids})."
        )

    if ctx is None:
        ctx = section_sim_context(
            artifact, job, resolved, workstations_dir=workstations_dir, plan=plan,
        )

    comp = slice_and_simulate_section(
        artifact, job, resolved, override=override,
        workstations_dir=workstations_dir, ctx=ctx,
    )
    outcome = section_clearance_check(
        comp, config=collision_config, travel_stride=stride,
    )
    # Die #162-Lese-Tuer kennt nur „Urteil oder kein Urteil": die Issue-#170-
    # „ungeprüft"-Gruende (no_geometry/error, als String) werden hier zu ``None``
    # verdichtet — der Kollisions-Advisor-Tie-in unterscheidet sie nicht (byte-gleich).
    verdict = None if isinstance(outcome, str) else outcome
    return ClearanceCheckResult(
        job_id=job_id,
        section_id=resolved,
        verdict=verdict.to_dict() if verdict is not None else None,
    )


@dataclass
class SingularityAdviceResult:
    """Ergebnis von `advise_singularity` (Issue #65/#134): Typ-Urteil + Vorschlag.

    Rein beratend — es wird **nichts** geschrieben (ADR-007: der Core urteilt,
    der Viewer setzt danach über die bestehende Schreibstelle). ``type`` ist der
    dominante Singularitätstyp der schlechtesten erreichten Pose der Platzierung
    des **Fokus-Abschnitts** (``section_id``, Issue #134), ``advice`` der gezielte
    Vorschlag (``Suggestion.to_dict()``) oder ``None`` (nichts zu beraten: kein
    Fokus-Abschnitt, unerreichbar oder Marge unkritisch).
    """

    job_id: str
    section_id: str | None
    type: str | None
    near: bool
    measure: float | None
    advice: dict | None


def advise_singularity(
    slug: str,
    job_id: str = "default",
    section_id: str | None = None,
    *,
    projects_dir: Path | None = None,
    workstations_dir: Path | None = None,
) -> SingularityAdviceResult:
    """Berät zur Singularitätsnähe der Platzierung des **Fokus-Abschnitts**.

    Seit Issue #134 ist der Advisor am Fokus-Abschnitt verankert (Muster
    Kollisions-Advisor #130): ``section_id`` benennt den Abschnitt des
    Zerlegungsplans, dessen Platzierung (inkl. Overrides #94, rekonstruiert über
    ``plan_for_job``) bewertet wird — der frühere Gesamtwand-Satz
    (``selected_placement``/``placements``, #22/#80) hat nach der Zerlegung
    keinen Konsumenten mehr. Klassifiziert die schlechteste erreichte Pose nach
    Typ und leitet den passenden Hebel ab (Handgelenk→Kipp, Reichweite/Ellbogen→
    Platzierung, konfig-abhängig→Config-Flip) samt Vorher/Nachher-Marge aus
    derselben Core-Bewertung (`fgc.placement.evaluate`). Read-only (ADR-007):
    das *Anwenden* schreibt der Viewer danach über die bestehenden Schreibstellen
    (`process-params` für den Kipp-Delta bzw. den Config-Flip-`ik_config`-Block
    #200, `placement-override` #94 für die Platzierung).

    Ohne ``section_id`` oder wenn der Abschnitt nicht (mehr) im Plan liegt, ist
    das Ergebnis leer (`type=None`, `advice=None`) — kein Fehler (der Viewer
    zeigt den freundlichen Fokus-Hinweis). Wirft `FileNotFoundError`, wenn das
    Projekt fehlt; `ValueError`, wenn der Druckjob/Roboter fehlt (Kinematik
    nicht rechenbar).
    """
    from fgc.domain.process_params import job_orientation
    from fgc.placement.advisor import AdvisorContext, advise, assess
    from fgc.project import load_project, project_dir_for

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    artifact = load_project(project_dir)
    job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
    if job is None:
        raise ValueError(
            f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
            "Zuerst eine Wand übernehmen (set_print_job)."
        )

    if not section_id:
        # Kein Fokus-Abschnitt → kein konkreter Kontext (kein Fehler, Issue #134).
        return SingularityAdviceResult(job_id, None, None, False, None, None)

    pc = placement_context_for_job(job)
    robot, tool, wall = pc.robot, pc.tool, pc.wall
    plan = plan_for_job(
        job, wall, robot, tool,
        strict_overrides=False, workstations_dir=workstations_dir,
    ).plan
    match = next(
        (sp for sp in plan.sections if sp.section.section_id == section_id), None
    )
    if match is None:
        # Abschnitt nicht (mehr) im Plan (stale Fokus) → leeres Ergebnis.
        return SingularityAdviceResult(job_id, None, None, False, None, None)

    # Abschnitt als Wandfläche an seiner echten Höhenlage (Issue #132); Art
    # „modul" bleibt am Boden (das Teil steht auf der Arbeitsfläche, ADR-022) —
    # der gemeinsame Member mit `fgc.decompose.evaluate` (Issue #191).
    surface = plan.surface_for_evaluation(match.section, wall.thickness_mm)
    ori = job_orientation(job)
    ctx = AdvisorContext(
        robot=robot, tool=tool, wall=surface, option=match.placement,
        lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad,
    )
    result = assess(ctx)
    if result is None:
        return SingularityAdviceResult(job_id, section_id, None, False, None, None)
    assessment, _worst = result
    suggestion = advise(ctx)
    return SingularityAdviceResult(
        job_id=job_id,
        section_id=section_id,
        type=assessment.dominant,
        near=assessment.near,
        measure=assessment.measure,
        advice=suggestion.to_dict() if suggestion is not None else None,
    )


def _coarse_collision_predicate(
    robot,
    robot_name: str,
    tool,
    wall,
    ori,
    *,
    robots_dir: Path | None = None,
):
    """Baut das billige Grob-Kollisions-Praedikat des Optimalvorschlags (Issue #131).

    Laedt die Breitphasen-Geometrie des Roboters (#125) einmalig und liefert ein
    ``option -> bool`` (kollisionsfrei?), das ``fgc.placement.suggest.suggest`` in
    die #98-Sortierung einhaengt. **Befund, kein Gate**: fehlt die
    Kollisionsgeometrie (Altprojekt/Roboter ohne Artefakt) oder die Geo-Extras,
    gibt es ``None`` — dann bewertet ``suggest`` alle Kandidaten als frei und die
    Sortierung bleibt bit-identisch zu #98. Ein Fehler je Kandidat wird ebenfalls
    fail-soft zu „frei" (nicht abwerten).
    """
    try:
        from fgc.collision.coarse import path_collides
        from fgc.collision.robot_geometry import load_robot_collision_geometry

        geo = load_robot_collision_geometry(robot_name, robots_dir)
    except Exception:
        return None

    def free(option) -> bool:
        try:
            return not path_collides(
                wall, robot, tool, option,
                geo, lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad,
            )
        except Exception:
            return True

    return free


def _reach_map_for_robot(robot_name: str, robots_dir: Path | None = None) -> Any:
    """Laedt die Reichweitenkarte des Roboters als Vorfilter — **fail-soft** (Issue #214).

    Der eine Ladepunkt der Karte fuer die Platzierungs-Aktionen (Optimalvorschlag,
    Kollisions-Advisor). Jeder Fehlbestand — kein Artefakt, veraltete Provenienz
    (US 18), Roboter ohne Kinematik — wird zu ``None``: die Aktion laeuft dann
    **ohne** Karte und damit byte-gleich zu Altlaeufen weiter (fail-soft, US 12).
    Die Karte filtert, urteilt nie (ADR-007/#164).
    """
    try:
        from fgc.kinematics.reachability import load_reachability_map

        return load_reachability_map(robot_name, robots_dir)
    except Exception:
        return None


def _beam_search_setup(
    pc: Any,
    job: dict,
    workstation: Any,
    stand_mode: str,
    *,
    robots_dir: Path | None = None,
    on_progress: Any = None,
    should_cancel: Any = None,
    surrogat: Any = None,
) -> tuple[Any, Any, Any]:
    """Baut die **produktive** Beam-Suche fuer den Auto-Vorschlag (Issue #217) — fail-soft.

    Liefert ``(strategie, scorer, objective)`` fuer :func:`plan_for_job`/``propose``:
    der billige :class:`~fgc.decompose.scorer.BilligerScorer` aus der geladenen
    **Reichweitenkarte** (#210, :func:`_reach_map_for_robot`), die Zielfunktion aus
    dem Druckjob (#212) und die konfigurierte :class:`~fgc.decompose.beam.BeamSuche`
    (Fortschritt/Abbruch fuer den Hintergrundlauf + die Relaxationsstufe „mehr
    Standplaetze" ueber die ``rescore``-Fabrik).

    **Fail-soft (US 12):** fehlt die Karte (kein Artefakt / veraltet / Roboter ohne
    Kinematik ⇒ ``reach_map is None``), gibt es keinen billigen Scorer — Rueckgabe
    ``(None, None, None)``, und der Aufrufer faellt byte-gleich auf den Reichweiten-
    Greedy (bzw. #165) zurueck. Die Aufstellhoehen kommen aus dem Podesthoehen-Satz
    der Workstation (Aufstell-Toggle #81): ``floor`` ⇒ nur Boden ``(0.0,)``; die
    Relaxationsstufe bietet den erweiterten (``elevated``) Satz an — mehr Standplaetze.

    **Art „modul" (Issue #237):** der Scorer bewertet **modul-lokal** an der festen
    Druckort-Platzierung (``BilligerScorer(fixe_platzierung=…)``,
    :func:`fgc.decompose.propose.modul_druckort_platzierung`) — jedes Modul wird am
    Druckort ab ``z = 0`` gedruckt, die absolute Wandhoehe der Reihe ist ohne Belang.
    Die Relaxationsstufe „mehr Standplaetze" entfaellt (die Basis steht fest, es gibt
    keinen Podesthoehen-Satz zu erweitern). Ohne Workstation liefert der Aufbau
    ``(None, None, None)`` — `propose` lehnt „modul" ohne Druckort ohnehin mit dem
    freundlichen Hinweis ab (ADR-022).
    """
    reach_map = _reach_map_for_robot(pc.robot_name, robots_dir)
    if reach_map is None:
        return None, None, None

    from fgc.decompose import BeamSuche, BilligerScorer, objective_from_job
    from fgc.placement.suggest import _workstation_heights

    kind = job.get("decomposition_kind", "abschnitt")
    objective = objective_from_job(job)

    if kind == "modul":
        if workstation is None:
            return None, None, None
        from fgc.decompose.propose import modul_druckort_platzierung

        fix = modul_druckort_platzierung(workstation, pc.wall.thickness_mm)
        scorer = BilligerScorer(reach_map, pc.wall, pc.tool, fixe_platzierung=fix)
        strategie = BeamSuche(
            on_progress=on_progress,
            should_cancel=should_cancel,
            surrogat=surrogat,
        )
        return strategie, scorer, objective

    def _heights(mode: str) -> tuple[float, ...]:
        if workstation is None:
            return (0.0,)
        return tuple(_workstation_heights(workstation, mode))

    base_heights = _heights(stand_mode)
    elevated_heights = _heights("elevated")
    scorer = BilligerScorer(reach_map, pc.wall, pc.tool, stand_heights_mm=base_heights)

    # Relaxationsstufe „mehr Standplaetze" (#217): mit dem erweiterten Podesthoehen-Satz
    # neu bewerten — nur, wenn er ueberhaupt mehr Hoehen anbietet als der Basis-Satz.
    ladder = [elevated_heights] if elevated_heights != base_heights else []

    def rescore(heights: Any) -> Any:
        return BilligerScorer(
            reach_map, pc.wall, pc.tool, stand_heights_mm=tuple(float(h) for h in heights)
        ).bewerte

    strategie = BeamSuche(
        stand_heights_ladder=ladder,
        rescore=rescore,
        on_progress=on_progress,
        should_cancel=should_cancel,
        # Surrogat-Vorsortierer (#219), optional: reordnet nur die Pruef-Reihenfolge —
        # Sieger + Urteil bleiben invariant (US 25). ``None`` ⇒ byte-gleich (US 12).
        surrogat=surrogat,
    )
    return strategie, scorer, objective


def _reach_predicate_for_placement(
    reach_map: Any,
    wall: Any,
    tool: Any,
    placement: Any,
    *,
    lead_deg: float = 0.0,
    kipp_deg: float = 0.0,
) -> Any:
    """Baut den Reichweitenkarten-Vorfilter des Kollisions-Advisors (Issue #214, US 8).

    Liefert ein ``Override -> bool``, das der reine Advisor (``fgc.collision.advisor``)
    **vor** jeder Neu-Simulation befragt: nur der **Platzierungs-Hebel** bewegt die
    Basis, also wird nur er gegen die Karte geprueft (die neue Aufstellung als
    :class:`PlacementOption`, Vorwaerts-Schaetzung > 0?). Alle anderen Hebel und der
    fehlende-Karte-Fall (``reach_map is None``) sowie jeder Fehler bleiben ``True``
    (lenient, fail-soft): die Karte **filtert, urteilt nie** (ADR-007/#164). ``None``
    ⇒ ``None`` (kein Vorfilter, byte-gleich zu heute).
    """
    if reach_map is None:
        return None

    import math

    from fgc.placement.evaluate import PlacementOption
    from fgc.placement.reachmap import option_survives

    lead_rad = lead_deg * math.pi / 180.0
    kipp_rad = kipp_deg * math.pi / 180.0

    def reachable(override: Any) -> bool:
        pl = getattr(override, "placement", None)
        if not pl:
            return True  # nur der Platzierungs-Hebel bewegt die Basis
        try:
            opt = PlacementOption(
                option_id="_adv",
                lateral_mm=float(pl.get("lateral_mm", placement.lateral_mm)),
                standoff_mm=float(pl.get("standoff_mm", placement.standoff_mm)),
                stand_height_mm=float(pl.get("stand_height_mm", placement.stand_height_mm)),
            )
            return option_survives(
                reach_map, wall, tool, opt, lead_rad=lead_rad, kipp_rad=kipp_rad,
            )
        except Exception:
            return True

    return reachable


def suggest_placement(
    slug: str,
    source: str,
    job_id: str = "default",
    *,
    standoff_mm: float = 700.0,
    n_best: int = 3,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
) -> PlacementEvalResult:
    """Berechnet den Optimalvorschlag fuer die Roboterbasis (Platzierung, Issue #23/#80).

    Bewertet ein deterministisches Raster von Basis-Lagen mit ``fgc.placement.suggest``
    (erreichbarer Wandanteil + kinematische Marge) und fuegt die ``n_best`` besten
    Vorschlaege (option_id: ``vorschlag-1`` … ``vorschlag-n``) den manuellen
    Aufstellmoeglichkeiten des Druckjobs hinzu. Fruhere Vorschlaege (option_id beginnt
    mit ``vorschlag-``) werden dabei ersetzt; manuelle Optionen bleiben unveraendert.

    Traegt der Druckjob eine **Workstation** (Feld ``workstation``, Issue #77), wird
    deren realer Podesthoehen-Satz + Sicherheits-Mindestabstand als Kandidatenmenge
    genutzt (Issue #80): seitlich zentral, Hoehe aus dem Podestsatz, Abstand optimiert
    ab ``safety_min_distance_mm``. Ohne Workstation (Altprojekt) faellt ``suggest``
    sauber auf das bisherige 2D-Raster (seitlich × Hoehe bei fixem ``standoff_mm``)
    zurueck — bestehende Routen/UI bleiben unveraendert.

    Die Bewertung aller Optionen (manuell + Vorschlag) wird als provenienz-
    gestempelter Lauf abgelegt (ADR-004). Im Druckjob landen nur Plan-Eingaben
    + Wahl + Lauf-Verweis (ADR-016); eine bereits getroffene Wahl bleibt
    erhalten (der Optimalvorschlag *ergänzt* die Vergleichsliste, er hebt keine
    laufende Auswahl auf).

    ``standoff_mm``: Abstand der Basis vor der Wandfront (mm) — nur der Fallback ohne
    Workstation nutzt ihn. ``n_best``: Anzahl der zurueckgegebenen besten Vorschlaege.

    Wirft ``ValueError``, wenn der Druckjob, der Roboter oder der Befund-Lauf fehlt.
    """
    from fgc.domain.process_params import job_orientation
    from fgc.placement.suggest import suggest
    from fgc.project import load_project, project_dir_for, project_lock

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)

        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand uebernehmen (set_print_job)."
            )

        pc = placement_context_for_job(job)
        robot, tool, wall = pc.robot, pc.tool, pc.wall

        # Workstation des Jobs laden (falls gesetzt, #77): ihr Podesthoehen-Satz +
        # Sicherheits-Mindestabstand steuern die Kandidatenmenge (#80). Ohne
        # Workstation bleibt es beim Fallback-Raster (Altprojekt).
        workstation = None
        workstation_name = job.get("workstation")
        if workstation_name:
            from fgc.domain.workstation import WorkstationDef

            workstation = WorkstationDef.load(
                workstation_name, workstations_dir=workstations_dir
            )

        # Optimalvorschlag: deterministisches Raster; der bahn-relative
        # Anstellwinkel (Issue #61) fliesst in die Bewertung ein. Der Aufstell-
        # Toggle (Issue #81) begrenzt den Podesthoehen-Satz (floor → nur Boden).
        ori = job_orientation(job)
        stand_mode = job.get("stand_mode", "floor")
        # Platzierungs-Grob-Check (Issue #131, ADR-024 Konsequenz): ein billiges
        # Kollisions-Praedikat je Kandidat, damit der Optimalvorschlag keine
        # Aufstellungen liefert, die erst in der Simulation durchfallen. Befund, kein
        # Gate — ohne Kollisionsgeometrie/Extras fail-soft None (#98 bit-identisch).
        collision_free = _coarse_collision_predicate(robot, pc.robot_name, tool, wall, ori)
        # Reichweitenkarte als Vorfilter (Issue #214): aussichtslose Kandidaten gar
        # nicht erst simulieren. Fail-soft None ohne Karte (#98 bit-identisch, US 12);
        # lenient (nur Karten-Schaetzung 0 faellt weg) → die Top-n_best sind unberuehrt.
        reach_map = _reach_map_for_robot(pc.robot_name)
        suggestions = suggest(
            wall, robot, tool, workstation=workstation, stand_mode=stand_mode,
            standoff_mm=standoff_mm, n_best=n_best,
            lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad,
            collision_free=collision_free, reach_map=reach_map,
        )
        # Gesamt-Befund „(kein) machbarer Kandidat" (Issue #228, ADR-026): aus den
        # Kollisionsurteilen der Vorschläge verdichtet, wandert bis in die API-Antwort
        # (Core rechnet, Viewer zeigt — Anzeige ist Folge-Issue). Der Grob-Check ruft
        # den Zerleger nie selbst (lose Kopplung, US 18).
        from fgc.placement import feasibility_finding

        feasibility = feasibility_finding(suggestions)

        # Manuelle Optionen bewahren (alte Vorschlaege entfernen, damit kein Duplikat).
        manual_options = [
            p for p in job.get("placements", [])
            if not str(p.get("option_id", "")).startswith("vorschlag-")
        ]

        # Vorschlaege mit Rang-IDs (vorschlag-1 = bester). Die prior-gefuehrt gewaehlte
        # IK-Konfiguration (Issue #233, ADR-026 Punkt 5) faehrt als a/b-Block mit — nur
        # ein echter Zweig (nicht-leer); ``auto`` bleibt implizit (byte-gleich zu manuell).
        suggested_dicts = []
        for rank, (opt, score) in enumerate(suggestions, start=1):
            entry: dict = {
                "option_id": f"vorschlag-{rank}",
                "lateral_mm": opt.lateral_mm,
                "standoff_mm": opt.standoff_mm,
                "stand_height_mm": opt.stand_height_mm,
                "yaw_rad": opt.yaw_rad,
            }
            if score.ik_config:
                entry["ik_config"] = dict(score.ik_config)
            suggested_dicts.append(entry)

        all_options = manual_options + suggested_dicts
        return evaluate_placements(
            slug,
            all_options,
            source,
            job_id,
            selected=job.get("selected_placement"),
            projects_dir=projects_dir,
            runs_dir=runs_dir,
            collision_predicate=collision_free,
            feasibility=feasibility,
        )


def _freigang_finding(robot: Any, tool: Any, thickness_mm: float | None) -> Any:
    """Fail-softer Freigang-Befund (Issue #163) der Wand — oder ``None``.

    Stufe 1 des Zerlegungs-Constraints (Karte #139, #141): das analytische
    Freigang-Kriterium (:func:`fgc.decompose.freigang.check_freigang`) aus Wanddicke,
    der freien Länge unter dem Handgelenk (aus Endeffektor-TCP + Flansch ``d6``) und
    dem provisorischen Handgelenk-/Unterarm-Radius. **Befund, kein Gate** (ADR-013):
    jeder Fehlbestand (keine Dicke, kein Endeffektor, keine Kinematik/Flansch) wird
    zu ``None`` — dann fehlt der Befund schlicht (nie ein Falsch-„unmöglich" aus
    geratenen Werten, Fehlerrichtung S6). Wand-weit, unabhängig von der Zerlegungsart.

    Ein **provisorischer** Werkzeug-TCP (``tool.tcp_provisional``, #136) wird als
    Vorläufigkeit **durchgereicht** (Issue #177, Befund B9): der Befund darf dann nicht
    als geprüfte Gewissheit dargestellt werden (der Modul-Export misstraut solchen TCP
    bereits). Der Befund unterbleibt deswegen nicht — das ``L`` aus einem geschätzten
    TCP ist immer noch die beste verfügbare Zahl —, er wird nur ehrlich markiert.
    """
    from fgc.decompose.freigang import check_freigang, free_length_under_wrist_mm

    if tool is None or thickness_mm is None or thickness_mm <= 0:
        return None
    kin = getattr(robot, "kinematics", None)
    if kin is None or not getattr(kin, "d_mm", None):
        return None
    try:
        flange_length_mm = float(kin.d_mm[-1])
        free_length = free_length_under_wrist_mm(tool, flange_length_mm)
        return check_freigang(
            float(thickness_mm),
            free_length_mm=free_length,
            tcp_provisional=bool(getattr(tool, "tcp_provisional", False)),
        )
    except Exception:  # noqa: BLE001 — Befund, kein Gate: nie den Zerlegungslauf kippen
        return None


#: Grobe Zeitschätzung (s) je Höhenreihen-Repräsentant der Stufe-2-Prüf-Tür — für
#: die Umfangsansage „prüft N Abschnitte, dauert ~…" (Issue #175). Aus Spike S5
#: (reale Denkmal-Bahn ~11,5 s ungedünnt, mit Travel-Ausdünnung wenige Sekunden;
#: konservativ ~10 s je Reihe angesetzt). Nur eine Schätzung, kein Vertrag.
PRUEF_PER_REP_SECONDS: float = 10.0

#: Die eine **prozessweite** :class:`fgc.decompose.pruefung.PruefCache`-Instanz (Issue
#: #175/#190): Prüf-Tür-Urteile je (Schnitt, Platzierung, Parameter)-Signatur, FIFO-
#: gedeckelt, Single-Process wie der Projekt-Lock (ADR-018). Lazy erzeugt (via
#: :func:`_process_pruef_cache`), damit ``actions`` geo-frei importierbar bleibt
#: (``fgc.decompose`` zieht trimesh/shapely). Tests injizieren stattdessen eine
#: frische Instanz über den ``cache``-Parameter von :func:`check_decomposition`.
_PRUEFTUER_CACHE: Any = None


def _process_pruef_cache() -> Any:
    """Die prozessweite :class:`PruefCache`-Instanz (lazy, Issue #190)."""
    global _PRUEFTUER_CACHE
    if _PRUEFTUER_CACHE is None:
        from fgc.decompose.pruefung import PruefCache

        _PRUEFTUER_CACHE = PruefCache()
    return _PRUEFTUER_CACHE


def _plan_pruef_signature(plan: Any, job: dict, *, travel_stride: int) -> tuple:
    """Signatur **aller** Prüf-Tür-relevanten Eingaben eines Zerlegungsstands (Issue #175).

    Erfasst genau, was das Prüf-Tür-Urteil eines Teils verändern kann: **Schnitt**
    (Geometrie jeder Zelle, in Reihenfolge — auch die tieferen Zellen zählen, weil sie
    als früherer Druckstand Hindernis sind), **Platzierung** (je Zelle) und **Parameter**
    (Prozessparameter-Block: Slice/Orientierung/Overrides), dazu Roboter/Endeffektor/
    Workstation/Zerlegungsart und der Ausdünnungs-Stride. Jede Änderung an einem davon
    ergibt eine andere Signatur ⇒ Cache-Miss (Neurechnung); ein unveränderter Stand
    ⇒ Treffer (keine Neurechnung — das nachweisbare Akzeptanzkriterium). Deterministisch.
    """
    sections = tuple(
        (
            sp.section.section_id,
            round(float(sp.section.x0_mm), 3),
            round(float(sp.section.x1_mm), 3),
            round(float(sp.section.z0_mm), 3),
            round(float(sp.section.z1_mm), 3),
            round(float(sp.section.center_x_mm), 3),
            int(sp.section.order),
            sp.placement.option_id,
            round(float(sp.placement.lateral_mm), 3),
            round(float(sp.placement.standoff_mm), 3),
            round(float(sp.placement.stand_height_mm), 3),
            round(float(getattr(sp.placement, "yaw_rad", 0.0) or 0.0), 6),
        )
        for sp in plan.sections
    )
    process = json.dumps(job.get("process_params") or {}, sort_keys=True)
    return (
        plan.kind,
        job.get("robot"),
        job.get("tool"),
        job.get("workstation"),
        bool(job.get("check_building_context", False)),
        int(travel_stride),
        sections,
        process,
    )


def _pruef_override_ids(job: dict) -> frozenset[str]:
    """Zellen mit eigenem Platzierungs-Override (von der Reihen-Vererbung ausgenommen)."""
    return frozenset(
        str(e["section_id"])
        for e in (job.get("section_overrides") or [])
        if e.get("section_id")
    )


def _decompose_pruef_scope(plan: Any, statuses: list, freigang: Any, job: dict) -> dict:
    """Umfangsansage der Stufe-2-Prüf-Tür (Issue #175) — wie groß wäre eine globale Prüfung?

    Rein, **ohne** die teure Prüf-Tür: zählt die Höhenreihen-Repräsentanten, die eine
    globale Prüfung rechnen müsste (:func:`fgc.decompose.pruefung.count_representatives`),
    und schätzt die Dauer (:data:`PRUEF_PER_REP_SECONDS` je Reihe). Ist die Wand schon nach
    Freigang zu dick (Stufe 1), ist nichts zu prüfen (``n_representatives=0``). Speist die
    bewusste Nutzerwahl „prüft N Abschnitte, dauert ~…" (Fokus-Prüfung bleibt Default).
    """
    from fgc.decompose.pruefung import count_representatives

    n = count_representatives(plan, statuses, freigang, _pruef_override_ids(job))
    return {
        "n_representatives": n,
        "n_parts": len(plan.sections),
        "est_seconds": round(n * PRUEF_PER_REP_SECONDS, 1),
    }


def _default_travel_stride() -> int:
    """Lazy-Default des Travel-Strides (geo-frei importierbar halten, Issue #175)."""
    from fgc.collision.finding import DEFAULT_TRAVEL_STRIDE

    return DEFAULT_TRAVEL_STRIDE


@dataclass(frozen=True)
class DecomposeBundle:
    """Bewertungs-Bündel eines Zerlegungsstands (Issue #198) — alle *berechneten*
    Befunde, die :func:`_persist_decompose_run` ins ``decompose``-Artefakt, in den
    Druckjob und in die :class:`DecomposeResult` schreibt.

    Deckt sich mit der Parameterliste von ``fgc.decompose.decompose_artifact``
    (``plan``, ``statuses``, ``module_checks``, ``placement_checks``,
    ``module_poses``, ``freigang``, ``printability`` …) plus dem, was die
    ``sections``-Ausgabe und das Ergebnis zusätzlich brauchen (``pruef_scope``,
    Roboter-/Endeffektor-Name, ``wall_global_id``, ``module_limits``). Löst den
    unsichtbaren Seitenkanal (früher ``printability_override``/``last_pruef`` als
    Paar-Kontrakt-Parameter von :func:`propose_decomposition`) durch ein sichtbares
    Wertobjekt ab: der interaktive Stufe-1-Aufrufer und der Stufe-2-Aufrufer
    (:func:`check_decomposition` Phase 3) reichen dasselbe Bündel durch dieselbe
    eine Persistier-Tür (Vorbild ``JobMutation``/``mutate_print_job``).
    """

    robot_name: str
    tool_name: str
    wall_global_id: str
    plan: DecompositionPlan
    statuses: list
    module_limits: ModuleLimits
    module_checks: dict | None
    placement_checks: dict | None
    module_poses: dict | None
    freigang: Any
    printability: dict
    pruef_scope: dict | None
    #: Datensammel-Pflicht (Issue #211, PRD #183 US 23): je geprüftem Kandidat Merkmale +
    #: exaktes Prüf-Tür-Urteil (:class:`fgc.decompose.pruefung.PruefSample`, Platzierung/
    #: Podest bereits angereichert). Nur der Stufe-2-Aufrufer (:func:`check_decomposition`)
    #: füllt sie; der interaktive Stufe-1-Aufrufer lässt sie leer (kein Orakel lief). Additiv:
    #: leer/``None`` ⇒ der ``pruef_dataset``-Block fehlt im Lauf (byte-gleich).
    pruef_samples: list | None = None


def _decompose_findings(job_plan: JobPlan) -> tuple[dict | None, dict | None, dict | None]:
    """Die reinen, billigen Zusatz-Befunde eines Zerlegungsstands (Issue #198):
    Modulgrenzen-Befund (Art „modul"), Modul-Lage am Druckort (Workstation-Frames)
    und Sicherheitsabstand je frei übersteuertem Teil.

    Pure Funktionen des rekonstruierten Plans (kein Platzierungssuche/IK-Sampling) —
    beide Persistier-Aufrufer teilen sie: der interaktive Stufe-1-Loop
    (:func:`propose_decomposition`) und die Stufe-2-Prüf-Tür
    (:func:`check_decomposition` Phase 3, wo sie unter der kurzen Sperre bleiben
    dürfen, weil sie billig und rein sind — ADR-018). Rückgabe je None, wo der
    Befund gegenstandslos ist (Art „abschnitt" / keine Frames / keine freien
    Overrides) → der Lauf bleibt dort byte-gleich.
    """
    from fgc.decompose import check_plan, check_safety_distance, pose_plan
    from fgc.domain.process_params import ProcessWindow

    plan = job_plan.plan
    workstation = job_plan.workstation

    # Modulgrenzen-Befund je Teil (Issue #90, nur Art "modul"): Gewicht =
    # Volumen x Dichte + Befund je gesetzter Obergrenze — Befund, kein Gate. Der
    # Dichte-Default kommt aus der Prozessfenster-Karte (eine Quelle, ADR-013).
    module_checks = None
    if plan.kind == "modul":
        density = ProcessWindow.load().density_kg_m3
        module_checks = check_plan(plan, density_kg_m3=density, limits=job_plan.module_limits)

    # Modul-Lage je Teil (Issue #96, ADR-022): aus der Relativpose + den
    # Workstation-Frames (robot_base_frame/work_surface_frame, ADR-021). Additiv:
    # ohne Frames bleibt der Lauf byte-gleich.
    module_poses = None
    if (
        plan.kind == "modul"
        and workstation is not None
        and workstation.robot_base_frame is not None
        and workstation.work_surface_frame is not None
    ):
        from fgc.simulation.transform import frame_from_dict

        module_poses = pose_plan(
            plan,
            frame_from_dict(workstation.robot_base_frame),
            frame_from_dict(workstation.work_surface_frame),
        )

    # Sicherheitsabstands-Befund je frei übersteuertem Teil (Issue #94): Abstand
    # vor der Wandfront gegen den Workstation-Mindestabstand — additiv, kein Gate.
    placement_checks = None
    if job_plan.free_override_ids and workstation is not None:
        placement_checks = check_safety_distance(
            plan, job_plan.free_override_ids, workstation.safety_min_distance_mm
        )

    return module_checks, placement_checks, module_poses


def _persist_decompose_run(
    slug: str,
    project_dir: Path,
    source: str,
    job_id: str,
    bundle: DecomposeBundle,
    section_overrides: list[dict] | None,
    *,
    runs_dir: Path | None = None,
    last_pruef: dict | None = None,
) -> DecomposeResult:
    """Die **eine** Persistier-Tür der Zerlegungs-Bewertung (Issue #198) — echter
    Seam mit genau zwei Aufrufern (Vorbild ``JobMutation``/``mutate_print_job``).

    Schreibt das ``decompose``-Artefakt (ADR-004) und die Plan-Eingaben +
    Lauf-Verweis in den Druckjob (ADR-016) und liefert die :class:`DecomposeResult`.
    Rechnet **nichts** neu: das fertig berechnete :class:`DecomposeBundle` kommt vom
    Aufrufer herein — keine Platzierungssuche, kein IK-Sampling; nur die kurze
    Read-Modify-Write-Sektion unter der Sperre (ADR-018).

    Zwei Aufrufer: :func:`propose_decomposition` (Stufe-1-Urteil, interaktiv,
    ``last_pruef=None``) und :func:`check_decomposition` Phase 3 (Stufe-2-Urteil,
    ``last_pruef`` gesetzt). ``last_pruef`` hält fest, WAS geprüft wurde
    (global/Fokus) samt Eingabe-Schnappschuss für die Veraltung; ``None`` lässt den
    Prüfstand sichtbar „ungeprüft"/„veraltet". Damit verschwindet der frühere
    unsichtbare Paar-Kontrakt (``last_pruef`` wirkte nur bei
    ``printability_override != None``): dieser Aufrufer setzt schlicht das eine oder
    das andere.

    Der Aufrufer hält die Projekt-Sperre über seine Lese-/Rechen-Sektion; diese Tür
    (re-)nimmt denselben reentranten ``project_lock`` (ADR-018) — so liegt die
    ``write_project``-Stelle in einem ``project_lock``-Block (Grep-Kriterium
    ADR-018). Wirft ``ValueError``, wenn der Druckjob zwischenzeitlich verschwand.
    """
    from fgc.decompose import cuts_to_dicts, decompose_artifact
    from fgc.project import (
        bump_input,
        bump_section_input,
        load_project,
        project_lock,
        pruef_input_snapshot,
        refresh_output,
        write_project,
    )

    plan = bundle.plan
    with project_lock(project_dir):
        artifact = load_project(project_dir)
        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        run = Run.create("decompose", slug, source=source, runs_dir=runs_dir)
        # Zielfunktions-Config in die Lauf-Provenienz (Issue #212, ADR-004):
        # die KOMPLETTE wirksame Config (Lesart + Gewichte + Quantisierungs-
        # Schrittweiten) — auch der Default wird explizit gestempelt (der
        # Paper-Benchmark pinnt ihn); Altprojekte ohne ``objective``-Feld
        # tragen so dieselbe reproduzierbare Aussage wie konfigurierte.
        from fgc.decompose.objective import objective_from_job

        provenance = {**run.provenance, "objective": objective_from_job(job).to_dict()}
        run.write(
            "decompose",
            decompose_artifact(
                bundle.robot_name,
                bundle.tool_name,
                plan,
                bundle.statuses,
                provenance,
                wall_global_id=bundle.wall_global_id,
                module_limits=bundle.module_limits if plan.kind == "modul" else None,
                module_checks=bundle.module_checks,
                placement_checks=bundle.placement_checks,
                module_poses=bundle.module_poses,
                freigang=bundle.freigang,
                printability=bundle.printability,
                pruef_samples=bundle.pruef_samples,
            ),
        )
        run_str = str(run.dir.resolve())

        plan_cuts = cuts_to_dicts(plan)
        # Druckjob aktualisieren: nur Zerlegungsart + Schnittebenen + Fugen-Versatz +
        # Overrides + Lauf-Verweis (ADR-016) — nie Ampeln/Meshes.
        old_runs = job.get("runs", [])
        updated_job = {
            **job,
            "decomposition_kind": plan.kind,
            "cuts": plan_cuts,
            "joint_offset_mm": plan.joint_offset_mm,
            "section_overrides": section_overrides or [],
            "decompose_run": run_str,
            "runs": [*old_runs, run_str],
        }
        # Veraltung (Issue #29, verfeinert #94): eine STRUKTURELLE Änderung
        # (Zerlegungsart, Schnittebenen, Fugen-Versatz) bumpt die Eingabe-Stufe
        # „cutplan" → Simulation/Export ALLER Teile veralten. Eine reine
        # Platzierungs-Override-Änderung (Issue #94, #83-Mechanik) bumpt hingegen
        # NUR den Pro-Abschnitts-Zähler der geänderten Teile — die Nachbarn
        # bleiben aktuell. Eine unveränderte Neubewertung bumpt nichts.
        structural_changed = (
            job.get("decomposition_kind") != plan.kind
            or (job.get("cuts") or []) != plan_cuts
            or float(job.get("joint_offset_mm") or 0.0) != float(plan.joint_offset_mm)
        )
        old_over = {
            str(e["section_id"]): {k: v for k, v in e.items() if k != "section_id"}
            for e in (job.get("section_overrides") or [])
        }
        new_over = {
            str(e["section_id"]): {k: v for k, v in e.items() if k != "section_id"}
            for e in (section_overrides or [])
        }
        if structural_changed:
            updated_job = bump_input(updated_job, "cutplan")
        else:
            for sid in sorted(set(old_over) | set(new_over)):
                if old_over.get(sid) != new_over.get(sid):
                    updated_job = bump_section_input(updated_job, sid)
        # Die Zerlegung ist Teil des Druckplans → dessen Output-Schnappschuss
        # wird aufgefrischt (Druckplan ist danach aktuell, hängt nicht an cutplan).
        updated_job = refresh_output(updated_job, "druckplan")

        # Letzter Prüf-Tür-Stand (Issue #175): NUR der Stufe-2-Aufrufer
        # (``check_decomposition``) reicht ``last_pruef`` herein — dann WAS geprüft
        # wurde (global/Fokus) + der Eingabe-Schnappschuss (gegen den die Veraltung
        # später ableitet). Der interaktive Stufe-1-Aufrufer lässt ``last_pruef``
        # ``None`` — der Stand bleibt „ungeprüft"/„veraltet" sichtbar. Kein
        # Paar-Kontrakt mehr (Issue #198): das Feld hängt allein an ``last_pruef``.
        if last_pruef is not None:
            updated_job = {
                **updated_job,
                "last_pruef": {
                    "scope": last_pruef.get("scope", "global"),
                    "section_id": last_pruef.get("section_id"),
                    "input_snapshot": pruef_input_snapshot(updated_job),
                },
            }
        new_jobs = [updated_job if j["job_id"] == job_id else j for j in artifact["print_jobs"]]
        updated_artifact = {**artifact, "print_jobs": new_jobs}
        path = write_project(project_dir, updated_artifact)

    status_by_id = {s.section_id: s for s in bundle.statuses}
    sections_out = []
    for sp in plan.sections:
        entry = {
            "section_id": sp.section.section_id,
            "order": sp.section.order,
            "x0_mm": sp.section.x0_mm,
            "x1_mm": sp.section.x1_mm,
            "z0_mm": sp.section.z0_mm,
            "z1_mm": sp.section.z1_mm,
            "placement": {
                "option_id": sp.placement.option_id,
                "lateral_mm": sp.placement.lateral_mm,
                "standoff_mm": sp.placement.standoff_mm,
                "stand_height_mm": sp.placement.stand_height_mm,
                "yaw_rad": sp.placement.yaw_rad,
            },
            "status": status_by_id[sp.section.section_id].to_dict(),
        }
        # Additiv (Issue #90): der Modulgrenzen-Befund je Teil, nur bei Art
        # "modul" — Art "abschnitt" bleibt byte-gleich.
        if bundle.module_checks is not None and sp.section.section_id in bundle.module_checks:
            entry["module_check"] = bundle.module_checks[sp.section.section_id].to_dict()
        # Additiv (Issue #94): der Sicherheitsabstands-Befund je frei
        # übersteuertem Teil — Befund, kein Gate.
        if bundle.placement_checks is not None and sp.section.section_id in bundle.placement_checks:
            entry["placement_check"] = bundle.placement_checks[sp.section.section_id].to_dict()
        # Additiv (Issue #96): die Modul-Lage am Druckort je Teil — nur bei Art
        # "modul" mit Workstation-Frames (ADR-021/022).
        if bundle.module_poses is not None and sp.section.section_id in bundle.module_poses:
            entry["module_pose"] = bundle.module_poses[sp.section.section_id].to_dict()
        # Additiv (Issue #164/#170): das Druckbarkeits-Urteil je Teil, verbatim wie
        # im Lauf-Artefakt. Auch „ungeprüft" (unknown) wird geschrieben. Befund, kein Gate.
        pr = bundle.printability.get(sp.section.section_id)
        if pr is not None:
            entry["printability"] = pr.to_dict()
        sections_out.append(entry)

    return DecomposeResult(
        project_dir=project_dir,
        project_path=path,
        artifact=updated_artifact,
        job_id=job_id,
        run_dir=run.dir,
        decomposition_kind=plan.kind,
        cuts=plan_cuts,
        sections=sections_out,
        joint_offset_mm=plan.joint_offset_mm,
        freigang=bundle.freigang.to_dict() if bundle.freigang is not None else None,
        pruef_scope=bundle.pruef_scope,
    )


def propose_decomposition(
    slug: str,
    source: str,
    job_id: str = "default",
    *,
    kind: str | None = None,
    cuts: list[dict] | None = None,
    joint_offset_mm: float = 0.0,
    section_overrides: list[dict] | None = None,
    refine_collisions: bool = False,
    beam_search: bool = False,
    surrogat: Any = None,
    call_budget: int | None = None,
    on_progress: Any = None,
    should_cancel: Any = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
    robots_dir: Path | None = None,
) -> DecomposeResult:
    """Schlägt eine Zerlegung der Wand in erreichbare Abschnitte vor (Issue #24)
    oder wertet einen manuell editierten Schnittplan neu (Issue #25).

    ``kind=None`` (Default, Issue #237) übernimmt die im Druckjob gespeicherte
    Zerlegungsart (Fallback ``"abschnitt"``) — Hintergrund-Trigger (Beam-Suche #221,
    Benchmark #220) stellen die Art damit nie stillschweigend um; die HTTP-Route
    reicht ihre Art weiterhin explizit herein.

    Ohne ``cuts``: der Core sucht über das deep module `fgc.decompose` (wie
    bisher) selbst eine Zerlegung in **Abschnitte** (Zerlegungsart „Abschnitt",
    in place) — achsparallele Schnittebenen + je Abschnitt eine Platzierung.
    Mit ``cuts`` (Schnittplan-Editing, Issue #25): die Schnittebenen sind
    **Plan-Eingaben** des Nutzers (Drag/Zahlenfeld/Hinzufügen/Entfernen im
    Viewer) — der Core baut daraus die Abschnittsgeometrie
    (`fgc.decompose.from_cuts`) und sucht weiterhin automatisch eine
    Platzierung je Abschnitt, sofern kein ``section_overrides``-Eintrag sie
    übersteuert: per Referenz auf eine bereits erfasste Aufstellmöglichkeit
    (Issue #22/#25, `job["placements"]`) und/oder mit **freien Werten**
    (Issue #94: ``lateral_mm``/``standoff_mm``/``stand_height_mm``, sparse —
    nur gesetzte Felder übersteuern, Basis ist die automatische bzw.
    referenzierte Platzierung; bewertet wird der Override mit derselben
    evaluate-Maschinerie, ein Abstand unter dem Workstation-Mindestabstand
    wird als ``placement_check``-Befund gemeldet, kein Gate).
    ``joint_offset_mm`` versetzt die vertikalen Schnitte jeder zweiten
    Höhenlage (gestaffelte Stoßfugen; wirkt nur mit ``cuts``).

    In jedem Fall wird die Ampel-Bewertung (Ampeln) + Abschnittsgeometrie als
    provenienz-gestempelter **Lauf** (decompose.json, ADR-004) abgelegt; im
    Druckjob landen nur die *Plan-Eingaben* (Zerlegungsart, Schnittebenen,
    Fugen-Versatz, Overrides) und der *Verweis* auf den Lauf — nie die
    Ampeln/Meshes (ADR-016). „Prüfen"-Bedienmuster (ADR-007): dieser Aufruf
    *ist* die Neubewertung, die der Viewer nach jeder Schnittplan-Änderung
    (debounced) über den „Prüfen"-Button anstößt — die UI rechnet nie selbst,
    zwischen Änderung und Antwort bleibt die Ampel dort explizit „ungeprüft".

    ``refine_collisions`` (Issue #165, nur Auto-Vorschlag ``cuts=None`` + Art
    „abschnitt"): schaltet die **kollisionsgetriebene Verfeinerung** ein — eine Zelle
    gilt erst als gut, wenn sie **von der besten automatischen Option aus** (IK +
    Platzierung, Reihenfolge #141) kollisionsfrei ist (Prüf-Tür #162, produktiv über
    ``collision_pruef_tuer``/SectionSimContext #189); kollidiert sie weiter, teilt die
    Verfeinerung **entlang der verursachenden Achse aus dem Befund** (Bandhöhe senken,
    dann Breite teilen). Kipp/Tiefenteilung werden **nie** automatisch variiert
    (#141/#142). ``call_budget`` (Default ``DEFAULT_CALL_BUDGET`` #215) deckelt die
    Prüf-Tür-Aufrufe je Lauf — **kein Zeitbudget** (Determinismus: gleicher Input ⇒
    gleicher Schnitt). Der gewählte Platzierungs-Hebel landet je Reihe **in den
    Teil-Platzierungen**, die Provenienz (Strategie/Kontingent/Hebel je Reihe) im
    ``refinement``-Block des Laufs. Ohne ``refine_collisions`` (Default ``False``)
    bleibt der Vorschlag byte-gleich (nur Reichweite).

    ``beam_search`` (Issue #217, nur Auto-Vorschlag ``cuts=None`` + Art „abschnitt",
    **Vorrang vor** ``refine_collisions``): schaltet die **Beam-Suche end-to-end** ein
    — der billige Scorer (`fgc.decompose.scorer`, aus der Reichweitenkarte #210) bewertet
    **alle** Band-Raster-Kandidaten, der Zielfunktions-Komparator (#212, aus dem Druckjob)
    ordnet sie, der Beam behält die besten k (k aus ``call_budget`` #215 abgeleitet) und
    **nur die Überlebenden** durchlaufen dieselbe Prüf-Tür wie oben. Bei leerem Ergebnis
    zündet die **Relaxationsleiter** (mehr Teile → mehr Standplätze → Tiefenteilungs-
    Vorschlag, jede Stufe im ``refinement``-Block). Der Metriken-Katalog (US 20), die
    Verworfen-Gründe (US 10) und der Relaxationsausweis (US 22) landen im ``refinement``-
    Block des persistierten Laufs; ``on_progress(calls_used, call_budget)`` und
    ``should_cancel()`` machen die Suche hintergrundlauffähig (Muster #145/#175,
    `fgc.pipeline.checkjobs.start_beam_propose`). **Fail-soft:** ohne Reichweitenkarte
    (Altprojekt/fehlendes Artefakt) bleibt der Vorschlag byte-gleich (Reichweiten-Greedy).

    ``surrogat`` (Issue #219/#220, nur mit ``beam_search``): ein Surrogat-Vorsortierer
    (`fgc.decompose.surrogat.SurrogatModell`), der **nur die Prüf-Reihenfolge** der Beam-
    Überlebenden reordnet — Sieger + Urteil bleiben invariant (US 25), nur die Zeit/Aufrufe
    ändern sich. ``None`` (Default) ⇒ byte-gleich zum reinen Beam. Der **Benchmark-Harness**
    (#220, `fgc.pipeline.benchmark`) fährt darüber den dritten Arm (Beam+Surrogat).

    ``kind="modul"`` (Issue #90, ADR-022): statt Platzierungssuche je Teil gilt
    die **feste Platzierung an der Workstation** des Druckjobs (sie ist der
    Druckort — fehlt sie, kommt ein freundlicher Hinweis als ``ValueError``).
    Die optionalen Obergrenzen des Druckjobs (``module_limits``, Setter
    `set_module_limits_for_job`) verfeinern das Raster; je Teil wird additiv der
    Modulgrenzen-Befund (Gewicht = Volumen × Dichte aus der Prozessfenster-Karte
    + Grenzen-Befund) in Lauf und Antwort gelegt — **Befund, kein Gate**.
    Trägt die Workstation Platzierungs-Frames (``robot_base_frame`` +
    ``work_surface_frame``, ADR-021), kommt je Teil zusätzlich additiv die
    **Modul-Lage am Druckort** (``module_pose``, Issue #96/ADR-022 —
    Invertierung der Relativpose-Leserichtung) in Lauf und Antwort; ohne
    Frames fehlt das Feld (der Viewer zeigt dann einen Hinweis, kein Gate).

    Roboter und Endeffektor kommen aus dem Druckjob (Issue #20/#21); der Roboter
    **muss** gesetzt sein (Kinematik nötig). Ergebnis ist ein **Befund, kein Gate**
    (`core/CONTEXT.md`): rote Abschnitte blockieren den Plan nicht.

    VERALTUNG (Issue #29, verfeinert #94): eine strukturelle Änderung
    (Zerlegungsart/Schnittebenen/Fugen-Versatz) bumpt ``cutplan`` → alle Teile
    veralten; eine reine Platzierungs-Override-Änderung bumpt nur den
    Pro-Abschnitts-Zähler der geänderten Teile (#83-Mechanik); eine
    unveränderte Neubewertung bumpt nichts.

    Wirft `FileNotFoundError`, wenn das Projekt fehlt; `ValueError` bei fehlendem
    Druckjob/Roboter, fehlendem Befund-Lauf, unbekannter Wand, unbekannter
    Zerlegungsart, Art „modul" ohne Workstation am Druckjob oder einem
    `section_overrides`-Eintrag, dessen `option_id` keiner erfassten
    Aufstellmöglichkeit (`job["placements"]`) entspricht.
    """
    from fgc.decompose import evaluate
    from fgc.decompose.pruefung import assess_plan
    from fgc.domain.process_params import job_orientation
    from fgc.project import load_project, project_dir_for, project_lock

    project_dir = project_dir_for(slug, projects_dir=projects_dir)
    with project_lock(project_dir):
        artifact = load_project(project_dir)

        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )

        pc = placement_context_for_job(job)
        robot, tool, wall = pc.robot, pc.tool, pc.wall

        # ``kind=None`` (Issue #237): die Zerlegungsart des Druckjobs uebernehmen —
        # Hintergrund-Trigger (Beam-Suche #221, Benchmark #220) duerfen die im Job
        # gespeicherte Art nicht stillschweigend auf „abschnitt" umstellen (genau das
        # liess die Beam-Suche fuer Modul-Jobs eine In-situ-Zerlegung der ganzen
        # Wand suchen — Denkmal-Befund #237: 256/256 Kandidaten „reichweite").
        if kind is None:
            kind = job.get("decomposition_kind", "abschnitt")

        # Die frischen, noch nicht persistierten Plan-Eingaben (Nutzeraktion:
        # Zerlegungsart/Schnittebenen/Fugen-Versatz/Overrides) in eine Job-Kopie
        # mergen und durch DIESELBE Tür schicken wie die Simulation (Issue #112,
        # `plan_for_job`). Workstation (#77), Aufstell-Toggle (#81) und
        # Modul-Obergrenzen (#90) liest die Tür aus dem Job — so ist der
        # Zerlegungsplan des Reiters Druckplan per Bauart identisch mit dem der
        # Simulation. `strict_overrides=True`: der Nutzer soll unbekannte
        # `option_id`s als Fehler sehen (Simulation ignoriert sie still).
        kandidat = {
            **job,
            "decomposition_kind": kind,
            "cuts": cuts,
            "joint_offset_mm": joint_offset_mm,
            "section_overrides": section_overrides or [],
        }
        # Zerlegung als Suche (nur Auto-Vorschlag ``cuts is None``): das produktive
        # Pruef-Tuer-Orakel (SectionSimContext-Reuse, #189) urteilt exakt, das
        # Aufruf-Kontingent (#178/#215) deckelt die Kosten. Zwei Strategien an der
        # #216-Naht: **Beam-Suche** (Issue #217 — billiger Scorer ordnet alle Kandidaten,
        # NUR Ueberlebende durch die Pruef-Tuer, Relaxationsleiter bei leerem Ergebnis)
        # hat Vorrang; sonst die **kollisionsgetriebene Verfeinerung** (Issue #165, nur
        # Art „abschnitt"). Die Beam-Suche kann seit #237 auch Art „modul" (modul-
        # lokaler Scorer an der festen Druckort-Platzierung). Ohne beide Flags
        # (Default) bleibt der Vorschlag byte-gleich (nur Reichweite).
        pruef_tuer = None
        beam_strategie = None
        beam_scorer = None
        beam_objective = None
        if cuts is None and (
            (beam_search and kind in ("abschnitt", "modul"))
            or (refine_collisions and kind == "abschnitt")
        ):
            pruef_tuer = collision_pruef_tuer(
                artifact, kandidat,
                workstations_dir=workstations_dir,
                travel_stride=_default_travel_stride(),
            )
            if beam_search:
                workstation = _workstation_for_job(kandidat, workstations_dir)
                stand_mode = kandidat.get("stand_mode", "floor")
                beam_strategie, beam_scorer, beam_objective = _beam_search_setup(
                    pc, kandidat, workstation, stand_mode,
                    robots_dir=robots_dir,
                    on_progress=on_progress, should_cancel=should_cancel,
                    surrogat=surrogat,
                )
                # Fail-soft (US 12): keine Reichweitenkarte ⇒ kein Beam ⇒ Reichweiten-
                # Greedy (byte-gleich); die teure Pruef-Tuer wird dann nicht gefahren.
                if beam_strategie is None:
                    pruef_tuer = None
        job_plan = plan_for_job(
            kandidat, wall, robot, tool,
            strict_overrides=True, workstations_dir=workstations_dir,
            pruef_tuer=pruef_tuer, call_budget=call_budget,
            scorer=beam_scorer, objective=beam_objective, strategie=beam_strategie,
        )
        plan = job_plan.plan

        ori = job_orientation(job)
        statuses = evaluate(plan, robot, tool, lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad)

        # Die reinen Zusatz-Befunde (Modulgrenzen/Modul-Lage/Sicherheitsabstand) —
        # geteilt mit :func:`check_decomposition` Phase 3 (Issue #198).
        module_checks, placement_checks, module_poses = _decompose_findings(job_plan)

        # Freigang-Kriterium (Issue #163, Stufe 1 des Constraints): druckbare Tiefe
        # aus Wanddicke + Endeffektor. Wand-weit (nicht je Teil), additiv, fail-soft —
        # stellt nur „Wand zu dick" fest, nie Freiheit (S6-Lehre). Befund, kein Gate.
        freigang = _freigang_finding(robot, tool, plan.wall.thickness_mm)

        # Druckbarkeit je Teil (Issue #164, entkoppelt #175): der interaktive Loop
        # bekommt nur die **gratis** Stufe 1 (Freigang: zu dick ⇒ ``too_thick``; sonst
        # ehrlich ``unchecked`` — nie stilles Grün): ``assess_plan`` ohne Orakel
        # (Issue #190). Die teure Stufe-2-Prüf-Tür (~10 s/Reihe, Befund B14) läuft
        # NICHT hier, sondern nur über :func:`check_decomposition` (expliziter
        # Anstoß/Hintergrundlauf) — deren Urteil persistiert über dieselbe
        # Persistier-Tür :func:`_persist_decompose_run` (Issue #198), nicht mehr über
        # einen Seitenkanal-Parameter dieser Aktion. So blockiert ein Schnitt-Edit
        # den Editor nicht mehr für die Prüfzeit.
        # Stufe 1 ohne Orakel: kein geprüfter Kandidat (``_samples`` leer) — die
        # Datensammel-Pflicht (Issue #211) füllt sich nur über die teure Stufe-2-Prüf-Tür.
        printability, _stats, _samples = assess_plan(
            plan, statuses, freigang, _pruef_override_ids(job), None
        )

        # Umfangsansage der Stufe-2-Prüf-Tür (Issue #175): wie viele Höhenreihen eine
        # globale Prüfung rechnen müsste + grobe Dauer — für die bewusste Nutzerwahl,
        # ohne die teure Prüfung anzustoßen. Rein.
        pruef_scope = _decompose_pruef_scope(plan, statuses, freigang, job)

        # Bewertungs-Bündel schnüren und durch die eine Persistier-Tür schicken
        # (Issue #198). Die Tür (re-)nimmt denselben reentranten project_lock.
        bundle = DecomposeBundle(
            robot_name=pc.robot_name,
            tool_name=pc.tool_name,
            wall_global_id=job["wall_global_id"],
            plan=plan,
            statuses=statuses,
            module_limits=job_plan.module_limits,
            module_checks=module_checks,
            placement_checks=placement_checks,
            module_poses=module_poses,
            freigang=freigang,
            printability=printability,
            pruef_scope=pruef_scope,
        )
        result = _persist_decompose_run(
            slug, project_dir, source, job_id, bundle, section_overrides,
            runs_dir=runs_dir, last_pruef=None,
        )
    return result


@dataclass
class CheckDecompositionResult:
    """Ergebnis von :func:`check_decomposition` (Issue #175): entkoppelte Stufe-2-Prüfung.

    ``state`` ist genau eines von:

    - ``"done"`` — die Prüfung lief durch, das Druckbarkeits-Urteil wurde persistiert
      (``decompose``-Lauf + ``last_pruef``-Marker); ``result`` trägt die
      :class:`DecomposeResult` (Sektionen mit frischer ``printability``).
    - ``"cancelled"`` — abgebrochen (``should_cancel``); **nichts** persistiert, der
      Stand bleibt „ungeprüft"/„veraltet". ``result`` ist ``None``.
    - ``"superseded"`` — während der Rechenzeit haben sich die Prüf-Eingaben (Schnitt/
      Platzierung/Parameter) geändert (paralleler Schreibzugriff war möglich, die Sperre
      wurde NICHT durchgehend gehalten); das Ergebnis wäre veraltet und wird verworfen.
      ``result`` ist ``None`` — der Aufrufer stößt bei Bedarf neu an.
    - ``"empty"`` — kein Abschnitt im Plan (nichts zu prüfen).

    ``stats`` ist die Rechen-/Cache-Statistik (:class:`fgc.decompose.pruefung.PruefStats`);
    ``scope`` die geprüfte Reichweite (``"global"``/``"focus"``), ``section_id`` das
    Fokus-Teil (bei ``focus``).
    """

    job_id: str
    state: str
    scope: str
    section_id: str | None
    stats: PruefStats
    result: DecomposeResult | None = None


def _pruef_input_fields(job: dict) -> dict:
    """Snapshot der Prüf-Tür-relevanten **Plan-Eingaben** eines Jobs (Issue #175).

    Der Supersede-Wächter: ändert sich zwischen dem Start (Sperre kurz) und dem
    Persistieren (Sperre kurz) eines dieser Felder — ein paralleler Schreibzugriff,
    weil die Sperre WÄHREND der teuren Rechnung **nicht** gehalten wird —, ist das
    Prüfergebnis veraltet und wird verworfen (kein Lost-Update auf frische Nutzeredits).
    """
    return {
        "wall_global_id": job.get("wall_global_id"),
        "robot": job.get("robot"),
        "tool": job.get("tool"),
        "workstation": job.get("workstation"),
        "stand_mode": job.get("stand_mode"),
        "check_building_context": bool(job.get("check_building_context", False)),
        "module_limits": job.get("module_limits"),
        "decomposition_kind": job.get("decomposition_kind"),
        "cuts": job.get("cuts"),
        "joint_offset_mm": job.get("joint_offset_mm"),
        "section_overrides": job.get("section_overrides"),
        "process_params": job.get("process_params"),
        "placements": job.get("placements"),
    }


def _enrich_pruef_samples(samples: list, plan: DecompositionPlan) -> list:
    """Reichert den Kandidaten-Kern um Platzierungs-/Podest-Merkmale an (Issue #211).

    Der zweite fixierte Seam der Datensammel-Pflicht (Grill 2026-07-14): :func:`assess_plan`
    liefert je geprüftem Kandidat die Abschnitts-/Wand-Merkmale + das exakte Urteil, der
    Aufrufer legt hier die **Platzierung** je Teil dazu (seitliche Position, Standoff,
    **Podesthöhe** ``stand_height_mm``, Gierwinkel) — die kennt nur er aus dem Plan.
    **Fail-soft** (#164): scheitert die Anreicherung, kommt der unangereicherte Kern zurück
    — die Datensammel-Pflicht kippt nie den Prüf-Tür-Lauf (Befund, kein Gate).
    """
    try:
        placement_by_id = {sp.section.section_id: sp.placement for sp in plan.sections}
        return [
            s.with_placement(placement_by_id[s.section_id])
            if s.section_id in placement_by_id
            else s
            for s in samples
        ]
    except Exception:  # noqa: BLE001 — Anreicherung ist Befund, nie den Lauf kippen (#164)
        return list(samples)


def check_decomposition(
    slug: str,
    source: str,
    job_id: str = "default",
    *,
    focus_section_id: str | None = None,
    on_progress: Any = None,
    should_cancel: Any = None,
    on_scope: Any = None,
    cache: PruefCache | None = None,
    projects_dir: Path | None = None,
    runs_dir: Path | None = None,
    workstations_dir: Path | None = None,
) -> CheckDecompositionResult:
    """Stufe-2-Prüf-Tür **entkoppelt** vom interaktiven Loop (Issue #175, Akzeptanz-Kern).

    Die teure Druckbarkeitsprüfung (Prüf-Tür je Höhenreihe, ~10 s/Reihe, Befund B14)
    läuft hier auf **expliziten Anstoß** — oder, über den Hintergrundlauf
    (:mod:`fgc.pipeline.checkjobs`), asynchron mit Fortschritt/Abbruch. Drei Phasen mit
    **kurzer** Sperre, die die Rechenzeit NICHT einschließt (ADR-018):

    1. **Sperre kurz:** Projekt laden, Plan/Ampeln/Freigang rekonstruieren, die
       Prüf-Eingaben schnappschießen. Sperre **frei** — parallele Schreibzugriffe
       (Schnitt verschieben, Slice-Param ändern) bleiben möglich, der Editor friert nicht.
    2. **Ohne Sperre:** die teure Prüf-Tür rechnen (Cache je (Schnitt, Platzierung,
       Parameter); ``on_progress``/``should_cancel``). Ein Abbruch verwirft.
    3. **Sperre kurz:** neu laden, prüfen ob die Eingaben unverändert sind
       (:func:`_pruef_input_fields`) — sonst ``superseded`` (kein Lost-Update); sonst das
       Stufe-2-Urteil (aus Phase 2) plus die billigen reinen Zusatz-Befunde
       (:func:`_decompose_findings`) über die eine Persistier-Tür
       :func:`_persist_decompose_run` schreiben + den ``last_pruef``-Marker setzen
       (WAS geprüft: global/Fokus). **Keine** ``plan_for_job``-/``evaluate``-
       Neubewertung unter der Sperre (Issue #198): plan/statuses/freigang stammen
       aus Phase 1, das Urteil aus Phase 2.

    ``focus_section_id`` prüft nur die Höhenreihe des Fokus-Teils (Default-Wahl, schnell);
    ``None`` prüft global (alle Reihen). ``on_scope(n_total)`` meldet die Reihenanzahl,
    sobald sie in Phase 1 feststeht (für die Fortschrittsanzeige des Hintergrundlaufs).

    Die Urteils-Politik selbst (Scoping, Reihen-Vererbung, Cache-Politik) lebt in
    :func:`fgc.decompose.pruefung.assess_plan` (Issue #190); diese Tür verdrahtet nur
    das Produktiv-Orakel (:func:`fgc.pipeline.sectionsim.clearance_verdict`), die
    Job-Signatur (:func:`_plan_pruef_signature`) und den ``cache`` (Default: die eine
    prozessweite :class:`PruefCache`-Instanz; Tests injizieren eine frische).

    Read/write-getrennt: Phase 2 schreibt nichts; erst Phase 3 persistiert (atomar,
    unter Sperre). Wirft ``FileNotFoundError`` (Projekt fehlt) / ``ValueError``
    (Druckjob/Roboter fehlt) wie die übrigen Aktionen.
    """
    from fgc.decompose import evaluate
    from fgc.decompose.pruefung import PruefStats, assess_plan
    from fgc.domain.process_params import job_orientation
    from fgc.project import load_project, project_dir_for, project_lock

    scope = "focus" if focus_section_id else "global"
    project_dir = project_dir_for(slug, projects_dir=projects_dir)

    # --- Phase 1: Sperre kurz — Plan/Ampeln/Freigang + Eingabe-Schnappschuss. ---------
    with project_lock(project_dir):
        artifact = load_project(project_dir)
        job = next((j for j in artifact["print_jobs"] if j["job_id"] == job_id), None)
        if job is None:
            raise ValueError(
                f"Druckjob {job_id!r} existiert nicht im Projekt {slug!r}. "
                "Zuerst eine Wand übernehmen (set_print_job)."
            )
        pc = placement_context_for_job(job)
        robot, tool, wall = pc.robot, pc.tool, pc.wall
        job_plan = plan_for_job(
            job, wall, robot, tool,
            strict_overrides=False, workstations_dir=workstations_dir,
        )
        plan = job_plan.plan
        if not plan.sections:
            return CheckDecompositionResult(
                job_id, "empty", scope, focus_section_id, PruefStats()
            )
        ori = job_orientation(job)
        statuses = evaluate(plan, robot, tool, lead_rad=ori.lead_rad, kipp_rad=ori.kipp_rad)
        freigang = _freigang_finding(robot, tool, plan.wall.thickness_mm)
        input_fields = _pruef_input_fields(job)
        # Platzierungs-Overrides für die Persistierung in Phase 3 (dieselben Werte
        # re-anwenden). Die übrigen Plan-Eingaben (Zerlegungsart/Schnitte/Fugen-Versatz)
        # stecken bereits im Phase-1-``plan`` — Phase 3 rekonstruiert ihn nicht neu.
        section_overrides = job.get("section_overrides") or []

    # --- Phase 2: OHNE Sperre — die teure Prüf-Tür (Cache/Fortschritt/Abbruch). --------
    if on_scope is not None:
        sc = _decompose_pruef_scope(plan, statuses, freigang, job)
        n_total = 1 if focus_section_id else int(sc["n_representatives"])
        on_scope(n_total)

    stride = _default_travel_stride()

    def _check_representative(section_id: str) -> Any:
        # Das Produktiv-Orakel der Prüf-Tür: die Abschnitts-Simulation (#189).
        # ``clearance_verdict`` löst bewusst über das Modul-Global auf (der
        # öffentliche Test-Seam der Orchestrierung bleibt erhalten).
        return clearance_verdict(
            artifact, job, plan, section_id,
            workstations_dir=workstations_dir, travel_stride=stride,
        )

    printability, stats, samples = assess_plan(
        plan, statuses, freigang, _pruef_override_ids(job), _check_representative,
        signature=_plan_pruef_signature(plan, job, travel_stride=stride),
        focus_section_id=focus_section_id,
        cache=_process_pruef_cache() if cache is None else cache,
        on_progress=on_progress, should_cancel=should_cancel,
    )
    if stats.cancelled:
        return CheckDecompositionResult(job_id, "cancelled", scope, focus_section_id, stats)

    # --- Phase 3: Sperre kurz — Supersede-Wächter, dann atomar persistieren. ----------
    with project_lock(project_dir):
        fresh = load_project(project_dir)
        fresh_job = next((j for j in fresh["print_jobs"] if j["job_id"] == job_id), None)
        if fresh_job is None or _pruef_input_fields(fresh_job) != input_fields:
            # Eingaben änderten sich während der Rechnung → Ergebnis veraltet, verwerfen.
            return CheckDecompositionResult(
                job_id, "superseded", scope, focus_section_id, stats
            )
        # Reload + Supersede bestanden → das Stufe-2-Urteil (Phase 2) mit den billigen
        # reinen Zusatz-Befunden bündeln und über die eine Persistier-Tür schreiben
        # (Issue #198). plan/statuses/freigang stammen aus Phase 1 — keine
        # plan_for_job/evaluate-Neubewertung unter der Sperre (ADR-018). Die Findings
        # sind rein und billig, sie dürfen hier bleiben.
        module_checks, placement_checks, module_poses = _decompose_findings(job_plan)
        pruef_scope = _decompose_pruef_scope(plan, statuses, freigang, job)
        # Datensammel-Pflicht Phase 3 (Issue #211, fixierter Seam): den Kandidaten-Kern aus
        # der Prüf-Tür (Phase 2) um die **Platzierungs-/Podest-Merkmale** anreichern — die
        # Platzierung je Teil kennt der Aufrufer aus dem Phase-1-Plan. Fail-soft (#164):
        # scheitert die Anreicherung, bleibt der (unangereicherte) Kern erhalten, nie ein
        # Absturz des Laufs.
        pruef_samples = _enrich_pruef_samples(samples, plan)
        bundle = DecomposeBundle(
            robot_name=pc.robot_name,
            tool_name=pc.tool_name,
            wall_global_id=job["wall_global_id"],
            plan=plan,
            statuses=statuses,
            module_limits=job_plan.module_limits,
            module_checks=module_checks,
            placement_checks=placement_checks,
            module_poses=module_poses,
            freigang=freigang,
            printability=printability,
            pruef_scope=pruef_scope,
            pruef_samples=pruef_samples,
        )
        result = _persist_decompose_run(
            slug, project_dir, source, job_id, bundle,
            section_overrides,
            runs_dir=runs_dir,
            last_pruef={"scope": scope, "section_id": focus_section_id},
        )
    return CheckDecompositionResult(
        job_id, "done", scope, focus_section_id, stats, result=result
    )


def set_print_job(
    slug: str,
    wall_global_id: str,
    assessment_run: str,
    job_id: str = "default",
    *,
    wall_name: str | None = None,
    projects_dir: Path | None = None,
) -> PrintJobResult:
    """Setzt oder überschreibt einen Druckjob im Projekt (ADR-016).

    Lädt das Projekt (via `fgc.project` — die einzige Schreibstelle), setzt
    die Wand (GlobalId) und den Verweis auf den Befund-Lauf, ersetzt ggf.
    einen gleichnamigen Druckjob, lässt alle anderen Druckjobs unangetastet.
    Schreibt schema-validiert zurück.

    ``assessment_run`` ist der Pfad des Übersichts-Laufs (walls-list), der
    die Eignungsbefunde enthält — die Befunddaten selbst werden **nicht**
    kopiert (ADR-016). Bestehende ``runs``-Verweise eines vorhandenen Jobs mit
    demselben ``job_id`` bleiben erhalten.

    Wirft ``FileNotFoundError``, wenn das Projekt nicht existiert.
    Eignung ist ein **Befund, kein Gate** (ADR-013/CONTEXT): auch ungeeignete
    Wände können übernommen werden — der Viewer warnt, blockiert aber nicht.
    """
    from fgc.project import JobMutation, mutate_print_job

    def _mutate(old_job: dict | None) -> JobMutation:
        new_job: dict = {
            "job_id": job_id,
            "wall_global_id": wall_global_id,
            "assessment_run": str(Path(assessment_run).resolve()),
            "runs": [],
        }
        if wall_name is not None:
            new_job["wall_name"] = wall_name

        # Bestehende runs-Verweise eines vorherigen Jobs mit demselben job_id bewahren.
        if old_job:
            new_job["runs"] = old_job.get("runs", [])

        # Neue Wand = neue Eingabe-Revision (Issue #29): der frische Job startet mit
        # bump auf wall; nachgelagerte Stände (Druckplan/Simulation/Export) gibt es
        # noch nicht (leere outputs) — sie sind „fehlend", nicht „veraltet".
        # bump_always (Issue #199): dieser Setter BAUT den Job NEU (Rebuild) — ein
        # Diff gegen den Alt-Job wäre hier falsch, der Bump ist bedingungslos.
        return JobMutation(job=new_job, bump_always=("wall",))

    # Upsert: kein „existiert nicht"-Lookup — der Job wird angelegt oder ersetzt und
    # (byte-gleich zum bisherigen Verhalten) ans Ende der Druckjob-Liste gestellt.
    outcome = mutate_print_job(slug, job_id, _mutate, upsert=True, projects_dir=projects_dir)
    return PrintJobResult(
        project_dir=outcome.project_dir,
        project_path=outcome.project_path,
        artifact=outcome.artifact,
        job_id=outcome.job_id,
    )

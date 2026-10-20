"""Serialisierung des Zerlegungslaufs (decompose.json, Schema-Vertrag).

Baut das ``decompose``-Artefakt aus Schnittplan + Ampeln — analog
``placement_artifact``. Traegt ``schema_version``, den Provenienzblock (ADR-004)
und die Abschnitte samt Platzierung und Ampel-Befund. Reproduzierbar: gleiche
Eingaben → gleiches Artefakt.

Trennung nach ADR-016: das *gerechnete* Ergebnis (Ampeln, Abschnittsgeometrie)
lebt hier im Lauf; der Druckjob traegt nur die Eingaben (Zerlegungsart +
Schnittebenen) und den Lauf-Verweis.
"""

from __future__ import annotations

from typing import Any

from fgc.decompose.evaluate import PlacementCheck, SectionStatus
from fgc.decompose.freigang import FreigangCheck
from fgc.decompose.limits import ModuleCheck, ModuleLimits
from fgc.decompose.module_pose import ModulePose
from fgc.decompose.plan import DecompositionPlan, SectionPlan
from fgc.decompose.printability import PartPrintability
from fgc.decompose.pruefung import PruefSample, pruef_dataset_block


def decompose_artifact(
    robot_name: str,
    tool_name: str,
    plan: DecompositionPlan,
    statuses: list[SectionStatus],
    provenance: dict[str, Any],
    *,
    wall_global_id: str | None = None,
    module_limits: ModuleLimits | None = None,
    module_checks: dict[str, ModuleCheck] | None = None,
    placement_checks: dict[str, PlacementCheck] | None = None,
    module_poses: dict[str, ModulePose] | None = None,
    freigang: FreigangCheck | None = None,
    printability: dict[str, PartPrintability] | None = None,
    pruef_samples: list[PruefSample] | None = None,
) -> dict[str, Any]:
    """Baut das decompose.json-Artefakt (Issue #24, ADR-004/016).

    ``module_limits``/``module_checks`` (Issue #90, ADR-022) sind **additiv** und
    nur bei Zerlegungsart „modul" belegt: je Teil der Modulgrenzen-Befund
    (Gewicht + Grenzen, Befund kein Gate) unter ``sections[].module_check``,
    dazu die angewandten Obergrenzen als ``module_limits``-Echo. Bei Art
    „abschnitt" (beide ``None``) bleibt das Artefakt byte-gleich wie bisher.

    ``placement_checks`` (Issue #94) ist ebenso **additiv**: je Teil mit freiem
    Platzierungs-Override der Sicherheitsabstands-Befund (Workstation-
    Mindestabstand, Befund kein Gate) unter ``sections[].placement_check`` —
    ohne freie Overrides (``None``) bleibt das Artefakt byte-gleich.

    ``module_poses`` (Issue #96, ADR-022) ist ebenso **additiv** und nur bei
    Art „modul" mit Workstation-Frames (ADR-021) belegt: je Teil die Lage des
    Moduls am Druckort (``fgc.decompose.module_pose``) unter
    ``sections[].module_pose`` — ohne Frames (``None``) bleibt das Artefakt
    byte-gleich (Befund/Anzeige, kein Gate).

    ``freigang`` (Issue #163, ADR-013) ist ebenso **additiv** und **wand-weit**
    (nicht je Teil): das Freigang-Kriterium (druckbare Tiefe aus Wanddicke +
    Endeffektor, `fgc.decompose.freigang`) als **ein** Top-Level-Block ``freigang``
    — nur „Wand zu dick für einseitigen Druck", nie „frei" (S6-Lehre). Ohne den
    Befund (``None`` — z. B. Endeffektor-/Kinematik-Geometrie unbekannt) bleibt das
    Artefakt byte-gleich (Befund, kein Gate).

    ``printability`` (Issue #164/#170, ADR-013) ist ebenso **additiv** und **je Teil**:
    das Druckbarkeits-Urteil (`fgc.decompose.printability`, Freigang + repräsentative
    Prüf-Tür) unter ``sections[].printability`` — grün **nur**, was die Prüf-Tür frei
    gesehen hat; geerbte Reihen-Urteile sind als ``presumed`` gekennzeichnet. Auch
    „ungeprüft" (``unknown``) wird geschrieben — mit ``reason`` (no_geometry/error),
    damit ein Lauf mit fehlgeschlagener Prüfung nicht wie „alles geprüft" aussieht
    (Issue #170, B12/B35). Ohne das ``printability``-Argument (Altlauf) bleibt das
    Artefakt byte-gleich (das Feld erscheint gar nicht; Befund, kein Gate).

    ``pruef_samples`` (Issue #211, PRD #183 US 23 — Datensammel-Pflicht) ist ebenso
    **additiv** und **grill-unabhängig**: je **geprüftem Kandidat** (Höhenreihen-
    Repräsentant mit echtem Prüf-Tür-Urteil) ein Datensatz aus Merkmalen + exaktem Urteil
    unter dem Top-Level-Block ``pruef_dataset`` (versioniert über ``feature_version``,
    Label ``label_source`` = ``cpu-exakt`` im Laufbetrieb). Nur der Stufe-2-Prüf-Tür-Lauf
    liefert Kandidaten; ohne (Stufe-1-Ruhezustand/Altlauf) fehlt der Block ganz
    (byte-gleich). Befund, kein Gate.
    """
    status_by_id = {s.section_id: s for s in statuses}

    doc: dict[str, Any] = {
        "schema_version": "0.1",
        "provenance": provenance,
        "robot": robot_name,
        "tool": tool_name,
        "decomposition_kind": plan.kind,
        "joint_offset_mm": plan.joint_offset_mm,
        "wall": {
            "length_mm": plan.wall.length_mm,
            "height_mm": plan.wall.height_mm,
            "thickness_mm": plan.wall.thickness_mm,
        },
        "grid": {"n_length": plan.n_length, "n_height": plan.n_height},
        "cuts": [
            {"orientation": c.orientation, "position_mm": c.position_mm} for c in plan.cuts
        ],
        "sections": [
            _section_dict(
                sp, status_by_id, module_checks, placement_checks, module_poses, printability
            )
            for sp in plan.sections
        ],
    }
    if wall_global_id is not None:
        doc["wall_global_id"] = wall_global_id
    # Kollisionsgetriebene Verfeinerung (Issue #165), additiv: die Lauf-Provenienz der
    # Strategie (Name, Aufruf-Kontingent, verbrauchte Aufrufe, je Reihe gewaehlter Hebel).
    # Nur beim Auto-Vorschlag mit aktiver Verfeinerung belegt; sonst ``None`` ⇒ Feld
    # erscheint gar nicht (byte-gleich, Befund kein Gate).
    if plan.refinement is not None:
        doc["refinement"] = plan.refinement
    if module_limits is not None:
        doc["module_limits"] = module_limits.to_dict()
    if freigang is not None:
        doc["freigang"] = freigang.to_dict()
    # Datensammel-Pflicht (Issue #211): der Prüf-Tür-Datensatz (Merkmale + Urteil je
    # geprüftem Kandidat) als EIN additiver Top-Level-Block — nur bei geprüften Kandidaten
    # (Stufe-2-Lauf); leer/Altlauf ⇒ ``None`` ⇒ Feld erscheint gar nicht (byte-gleich).
    pruef_dataset = pruef_dataset_block(pruef_samples)
    if pruef_dataset is not None:
        doc["pruef_dataset"] = pruef_dataset
    return doc


def _section_dict(
    sp: SectionPlan,
    status_by_id: dict[str, SectionStatus],
    module_checks: dict[str, ModuleCheck] | None,
    placement_checks: dict[str, PlacementCheck] | None = None,
    module_poses: dict[str, ModulePose] | None = None,
    printability: dict[str, PartPrintability] | None = None,
) -> dict[str, Any]:
    """Ein Teil als Artefakt-Eintrag; ``module_check`` nur bei Art „modul" (#90),
    ``placement_check`` nur bei freiem Platzierungs-Override (#94),
    ``module_pose`` nur bei Art „modul" mit Workstation-Frames (#96),
    ``printability`` nur mit echtem Druckbarkeits-Urteil (#164)."""
    entry: dict[str, Any] = {
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
    if module_checks is not None:
        check = module_checks.get(sp.section.section_id)
        if check is not None:
            entry["module_check"] = check.to_dict()
    if placement_checks is not None:
        placement_check = placement_checks.get(sp.section.section_id)
        if placement_check is not None:
            entry["placement_check"] = placement_check.to_dict()
    if module_poses is not None:
        pose = module_poses.get(sp.section.section_id)
        if pose is not None:
            entry["module_pose"] = pose.to_dict()
    if printability is not None:
        pr = printability.get(sp.section.section_id)
        # Jedes vorhandene Urteil schreiben — auch „ungeprüft" (unknown), mit
        # ``reason`` (no_geometry/error, Issue #170): ein Lauf mit fehlgeschlagener
        # Pruefung darf nicht wie „alles geprüft" aussehen (B12/B35). Altläufe ohne
        # das ``printability``-Argument bleiben byte-gleich (Feld erscheint gar nicht).
        if pr is not None:
            entry["printability"] = pr.to_dict()
    return entry


def cuts_to_dicts(plan: DecompositionPlan) -> list[dict[str, Any]]:
    """Die Schnittebenen als Plan-Eingaben fuer den Druckjob (ADR-016)."""
    return [{"orientation": c.orientation, "position_mm": c.position_mm} for c in plan.cuts]

"""Kollisions-Befund als additiver Trajektorien-Block (ADR-024, PRD #124, Issue #127).

Die I/O-/Schema-Scheibe der **Kollisionskontrolle**: verheiratet den reinen
Zweiphasen-Check (:mod:`fgc.collision.check`) mit dem schichtweisen Druckstand
(:mod:`fgc.collision.druckstand`) und der Kinematik zu **einem** additiven
``meta.collision``-Block des Trajektorien-Artefakts. Entsteht **automatisch bei
jeder Simulation** (Abschnitt wie Modul) und ist ein **Befund, kein Gate** — die
Simulation liefert immer, auch wenn Kollisionsgeometrie fehlt oder der Check
scheitert (dann fehlt der Block schlicht).

Der Block traegt: die **Abstandskurve** je Sample (parallel zu ``samples``, damit
``samples`` byte-gleich bleibt), den **Verursacher** je Sample (Glied + Hindernis),
die verdichteten **Kollisions-/Warn-Intervalle**, ein **Echo der Konfiguration**
(Sicherheitsabstand, Freizone — Platzhalterwerte, ``provisional``-Geist wie bei den
Prozessfenster-Karten) und die **Travel-Kennzeichnung** „nicht lueckenlos geprueft"
(Spike S0: Travel-Moves springen bis ~1 m je Sample-Schritt, Druckzuege sind mit
p99 20 mm dicht).

**Determinismus.** Gleiche Eingaben ⇒ bitgleicher Befund: die Distanzen sind
deterministisch (python-fcl, Spike S0), die Rundung (:data:`ROUND_DECIMALS`)
haelt die JSON stabil, ``Infinity`` (Glied ausserhalb der Breitphase) wird zu
``null`` — RFC-8259-konform (der Schreiber verbietet NaN/Infinity).

**Reinheit / Modularitaet.** Die Geo-Pakete werden ueber ``check``/``druckstand``
*lazy* importiert; dieses Modul selbst ist ohne ``fgc-core[geo]`` importierbar
(der Roboterkatalog-Loader meldet fehlende Extras freundlich).
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fgc.collision import check as _check
from fgc.collision import druckstand as _ds

if TYPE_CHECKING:  # nur fuer Typpruefer — kein Laufzeit-Import (geo-frei startbar)
    from fgc.domain.models import Frame
    from fgc.domain.tool import ToolDef

#: Sicherheitsabstand-Platzhalter (mm) — teilt sich die Quelle mit ``check``.
DEFAULT_SAFETY_DISTANCE_MM = _check.DEFAULT_SAFETY_DISTANCE_MM

#: Freizone-Platzhalter (mm) um den Druckpunkt (Duese<->frischer Wulst). Provisorisch,
#: bis gemessene Prozessdaten die zulaessige Annaeherung liefern (ADR-024 Revisionstrigger).
DEFAULT_FREIZONE_RADIUS_MM = 40.0

#: Rundung der Abstaende (mm) fuer den byte-stabilen Befund — wie die #126-Goldens.
ROUND_DECIMALS = 3

#: Travel-Ausduennung der Pruef-Tuer (:func:`check_part_clearance`): nur jedes
#: ``n``-te Travel-Sample wird geprueft (Druck-Samples bleiben vollstaendig). Der
#: **sichere** S5-Hebel (Spike S5, Issue #143): Travel ist ohnehin als „nicht
#: lueckenlos geprueft" markiert (Tunneling bis ~1 m/Schritt, ADR-024). 5× spart
#: ~2,8 s an der realen Denkmal-Bahn (~11,5 s → ~8,7 s), weiter ausduennbar. Der
#: **volle** Befund (:func:`build_section_finding`) duennt **nie** aus (stride=1).
DEFAULT_TRAVEL_STRIDE = 5

#: z-Hoehe (mm) des Footprint-Schnitts durch das Teil-Mesh (knapp ueber dem Fuss).
_FOOTPRINT_Z_MM = 1.0


@dataclass(frozen=True)
class CollisionConfig:
    """Konfiguration der Kollisionskontrolle je Simulation (US 4, konfigurierbar).

    ``provisional`` bleibt ``True``, solange ``safety_distance_mm`` und
    ``freizone_radius_mm`` Platzhalterwerte sind (noch nicht gemessen) — der
    ``provisional``-Geist der Prozessfenster-Karten.
    """

    safety_distance_mm: float = DEFAULT_SAFETY_DISTANCE_MM
    freizone_radius_mm: float = DEFAULT_FREIZONE_RADIUS_MM
    context_enabled: bool = False
    provisional: bool = True


# ---------------------------------------------------------------------------
# FindingRequest: das gruppierte Wertobjekt der Kollisions-Tueren (Issue #192)
# ---------------------------------------------------------------------------
#
# Die Invarianten (abschnitts-lokales System, Boden bei −z0, Kontext-Schalter)
# stehen **einmal** an diesen Gruppen-Definitionen, nicht mehr in sechs
# Docstrings. Alle Gruppen sind frozen — Varianten baut man mit
# ``dataclasses.replace`` (die Tests tun genau das).


@dataclass(frozen=True)
class TrajectoryExcerpt:
    """Der abschnitts-lokale Bahn-Ausschnitt eines Kollisions-Befunds (Issue #192).

    Alles abschnitts-lokal (z ab Abschnittsfuss, ADR-006): ``base_frame`` =
    Trajektorien-``meta.base_frame`` (Roboterbasis im Teil-/Wandsystem);
    ``samples`` = Trajektorien-Samples (``joints_rad`` + ``t_s``);
    ``target_times_s`` = geometrische Target-Ankunftszeiten (aus der Trajektorie).
    """

    base_frame: dict[str, Any]
    samples: Sequence[dict[str, Any]]
    target_times_s: Sequence[float]


@dataclass(frozen=True)
class ToolpathExcerpt:
    """Die Schicht-Herkunft des Befunds aus dem Toolpath (Issue #192).

    ``targets`` = Toolpath-Targets (``layer``, ``kind``) — die Schicht je Sample
    kommt **aus dem Toolpath** (:func:`fgc.collision.druckstand.layer_per_sample`),
    nicht aus der TCP-Hoehe; die Travel-Kennzeichnung ebenso. ``layer_height_mm``
    und ``n_layers`` spannen den wachsenden **Druckstand** auf.
    """

    targets: Sequence[dict[str, Any]]
    layer_height_mm: float
    n_layers: int


@dataclass(frozen=True)
class PartMesh:
    """Das abschnitts-lokale Teil-Mesh als Footprint-Quelle (Issue #192).

    ``vertices_mm``/``faces`` im abschnitts-lokalen System (x zentriert, z ab
    Fuss 0); daraus wird das **Footprint-Prisma** des Druckstands geschnitten.
    """

    vertices_mm: Any
    faces: Any


@dataclass(frozen=True)
class SceneInputs:
    """Die Hindernis-Szene des **Druckstands** — die DruckstandSpec-Naht (Issue #192).

    Die eine Gruppe, die den wachsenden Druckstand aufspannt (ADR-024). Alle
    Angaben abschnitts-lokal:

    - ``mode``: Zerlegungsart — ``"abschnitt"`` (Boden + fruehere Teile zaehlen)
      oder ``"modul"`` (die Workstation ist der Druckort, ADR-022: kein Boden,
      keine fruehere Teile, kein Gebaeudekontext).
    - ``section_z0_mm``: echte Hoehenlage des Abschnittsfusses ueber dem Boden
      (Boden = Wandfuss). Toolpath/Samples liegen abschnitts-lokal, der reale
      Boden liegt dann bei **lokal ``−z0``** und wird bei ``z0 > 0`` (Art
      ``"abschnitt"``) als Hindernis gefuehrt. Fuer die unterste Reihe
      (``z0 = 0``) bleibt der Boden bewusst **weg** (v1-Lehrgeld #127: eine Slab
      am Fuss erzeugte nur chronische Fehlwarnungen — Basis↔Boden ist erlaubter
      Dauerkontakt; z0=0-Befund bleibt bit-identisch, Regressionsanker).
    - ``earlier_parts``: fruehere Teile in Druckreihenfolge als ``(vertices_mm,
      faces)``-Paare, bereits ins abschnitts-lokale System verschoben (auf ihren
      **echten Baendern**) — volle Hindernisse (ADR-022: Druckreihenfolge =
      Montagereihenfolge).
    - ``context``: optionaler Gebaeudekontext ``(vertices_mm, faces)`` im
      abschnitts-lokalen System (Issue #131); nur bei ``config.context_enabled``
      **und** Art ``"abschnitt"`` ein Hindernis, sonst ignoriert (bei ``"modul"``
      gegenstandslos). ``None`` = kein Kontext.
    """

    mode: str = "abschnitt"
    section_z0_mm: float = 0.0
    earlier_parts: Sequence[tuple[Any, Any]] = ()
    context: tuple[Any, Any] | None = None


@dataclass(frozen=True)
class RobotToolRefs:
    """Endeffektor + Katalog-Verzeichnisse eines Befunds (Issue #192).

    ``tool`` = Endeffektor-Definition: der TCP ankert **immer** die Freizone am
    Druckpunkt (auch ohne Mesh, ADR-024), die provisorische Endeffektor-Huelle
    kommt zusaetzlich, sofern der Endeffektor ein Mesh traegt. ``tools_dir`` /
    ``robots_dir`` = die Katalog-Verzeichnisse (``None`` = Standardpfade);
    ``robots_dir`` entscheidet zugleich fail-soft, ob ueberhaupt Kollisions-
    Geometrie referenziert ist (fehlt sie ⇒ kein Befund).
    """

    tool: ToolDef | None = None
    tools_dir: Path | None = None
    robots_dir: Path | None = None


@dataclass(frozen=True)
class FindingRequest:
    """Die gebuendelten Eingaben **eines** Kollisions-Aufrufs (Issue #192, Grill 2026-07-13).

    Ersetzt den 18/19-Parameter-Sack der Kollisions-Tueren
    (:func:`build_section_finding`, :func:`check_part_clearance`) durch **ein**
    gruppiertes Wertobjekt. Gebaut wird es an einer Stelle —
    :meth:`fgc.pipeline.sectionsim.SectionComputation.finding_request` — und von
    allen Marshaling-Stellen gereicht. Die Invarianten je Gruppe dokumentieren
    :class:`TrajectoryExcerpt`, :class:`ToolpathExcerpt`, :class:`PartMesh`,
    :class:`SceneInputs`, :class:`RobotToolRefs`.
    """

    trajectory: TrajectoryExcerpt
    toolpath: ToolpathExcerpt
    part: PartMesh
    scene: SceneInputs
    refs: RobotToolRefs
    config: CollisionConfig | None = None


# ---------------------------------------------------------------------------
# Report -> additiver meta.collision-Block (rein, ohne Geo)
# ---------------------------------------------------------------------------


def _num(value: float) -> float | None:
    """Endliche mm-Zahl gerundet, ``Infinity``/``NaN`` -> ``None`` (RFC-8259/allow_nan=False)."""
    if value != value or value in (float("inf"), float("-inf")):  # NaN oder +/-inf
        return None
    return round(float(value), ROUND_DECIMALS)


def report_to_dict(
    report: _check.CollisionReport,
    *,
    config: CollisionConfig,
    mode: str,
    travel_intervals: Sequence[tuple[int, int]],
) -> dict[str, Any]:
    """Verdichtet einen :class:`CollisionReport` zum additiven ``meta.collision``-Dict.

    Rein (kein Geo, kein I/O): Report rein, schema-konformes Dict raus. Die
    Abstandskurve/Verursacher liegen als zu ``samples`` **parallele** Arrays vor
    (``samples`` bleibt byte-gleich); ``Infinity`` (kein Nahpaar) wird ``null``.
    """
    samples = report.samples
    return {
        "config": {
            "safety_distance_mm": round(float(config.safety_distance_mm), ROUND_DECIMALS),
            "freizone_radius_mm": round(float(config.freizone_radius_mm), ROUND_DECIMALS),
            "provisional": bool(config.provisional),
            "context_enabled": bool(config.context_enabled),
            "mode": mode,
        },
        "min_distance_mm": _num(report.min_distance_mm),
        "worst_index": int(report.worst_index),
        "n_red": int(report.n_red),
        "n_yellow": int(report.n_yellow),
        "n_green": int(report.n_green),
        "tool_provisional": bool(report.tool_provisional),
        "distances_mm": [_num(s.distance_mm) for s in samples],
        "causer_link": [s.link for s in samples],
        "causer_against": [s.against for s in samples],
        "intervals": [
            {
                "status": iv.status,
                "start_index": iv.start_index,
                "end_index": iv.end_index,
                "min_distance_mm": _num(iv.min_distance_mm),
                "worst_index": iv.worst_index,
                "link": iv.link,
                "against": iv.against,
            }
            for iv in report.intervals
        ],
        "travel_intervals": [[int(a), int(b)] for a, b in travel_intervals],
        "travel_not_continuously_checked": bool(travel_intervals),
    }


def travel_flags(
    sample_times_s: Sequence[float],
    target_times_s: Sequence[float],
    target_kinds: Sequence[str],
) -> list[bool]:
    """Je Sample: liegt es auf einem **Travel**-Toolpath-Segment?

    Jedes Sample erbt die ``kind`` seines Toolpath-Segments (dieselbe Bisektion wie
    :func:`fgc.collision.druckstand.layer_per_sample`) — so kommt die Travel-
    Kennzeichnung **aus dem Toolpath**, nicht aus einer Geschwindigkeits-Heuristik.
    Ohne Target-Zeiten/-Arten sind alle Samples „nicht Travel" (leere Liste).
    """
    tt = list(target_times_s)
    kinds = list(target_kinds)
    if not tt or not kinds:
        return [False for _ in sample_times_s]
    return [
        kinds[max(0, min(bisect_right(tt, t) - 1, len(kinds) - 1))] == "travel"
        for t in sample_times_s
    ]


def travel_intervals(
    sample_times_s: Sequence[float],
    target_times_s: Sequence[float],
    target_kinds: Sequence[str],
) -> list[tuple[int, int]]:
    """Zusammenhaengende Sample-Bereiche ``[start,end]``, deren Toolpath-Segment Travel ist."""
    tt = list(target_times_s)
    kinds = list(target_kinds)
    if not tt or not kinds:
        return []
    flags = travel_flags(sample_times_s, target_times_s, target_kinds)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, is_travel in enumerate(flags):
        if is_travel and start is None:
            start = i
        elif not is_travel and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def thin_travel_indices(flags: Sequence[bool], stride: int) -> list[int]:
    """Kept-Sample-Indizes nach **Travel-Ausduennung**: alle Druck-Samples + jedes
    ``stride``-te Travel-Sample (je Travel-Lauf inkl. Anfang **und** Ende).

    Rein (kein Geo): ``stride <= 1`` behaelt alles (Identitaet). Endpunkte jedes
    Travel-Laufs bleiben erhalten, damit die Ausduennung den Uebergang Druck↔Travel
    nicht ueberspringt — das haelt den Fehler in Richtung „geprueft" statt „frei".
    Deterministisch (festes Raster).

    Die Rueckgabe ist zugleich die **Ausduennungs-Abbildung** fuer
    :func:`original_sample_index`: Position ``j`` im Rueckgabewert = das ``j``-te
    tatsaechlich geprueft Sample, sein Wert = dessen Original-Index vor der
    Ausduennung (Issue #181).
    """
    n = len(flags)
    if stride <= 1:
        return list(range(n))
    kept: list[int] = []
    i = 0
    while i < n:
        if not flags[i]:
            kept.append(i)
            i += 1
            continue
        j = i
        while j < n and flags[j]:
            j += 1
        for k in range(i, j):
            if (k - i) % stride == 0 or k == j - 1:
                kept.append(k)
        i = j
    return kept


def original_sample_index(kept: Sequence[int], thinned_index: int) -> int | None:
    """Rueckrechnung Ausduennungs-Index → Original-Index (Issue #181, Befund B24).

    ``kept`` ist die Ausduennungs-Abbildung aus :func:`thin_travel_indices` (Position
    ``j`` = das ``j``-te tatsaechlich geprueft Sample, Wert = sein Original-Index vor
    der Travel-Ausduennung — Anfang **und** Ende jedes Travel-Laufs bleiben dort immer
    erhalten, s. dort). Ohne diese Rueckrechnung zeigt ein Sample-Index der Pruef-Tuer
    (``CollisionReport.worst_index`` bzw. ``Interval.*_index``) auf die **ausgeduennte**
    Liste und ist nicht auf die Bahn (Toolpath/Trajektorie, Original-Indizierung)
    rueckfuehrbar — genau der Blindfleck, den #165 (Teilen entlang der
    Verursacher-Achse) sonst geerbt haette.

    Reine Indizierung. ``thinned_index`` ausserhalb ``[0, len(kept))`` (z. B. ``-1``,
    der Sentinel eines Berichts ohne endlichen Abstand) liefert ``None`` statt eines
    ``IndexError`` — kein Sample, kein Ort.
    """
    if not (0 <= thinned_index < len(kept)):
        return None
    return kept[thinned_index]


def _causer_position_mm(
    base: Frame,
    link_frames: Sequence[Frame] | None,
    causer_link: int | None,
    tcp_frame: Frame | None,
) -> tuple[float, float, float] | None:
    """Position (mm) des Verursacher-Glieds am schlimmsten Sample im Teil-/Wandsystem
    (Issue #181, Vorarbeit fuer #165s „Teilen entlang der Verursacher-Achse").

    ``base`` ist die Basis-Pose im Teil-/Wandsystem (Trajektorien-``meta.base_frame``,
    dieselbe Bedeutung wie in :func:`_prepare_finding`); ``link_frames`` sind die
    Glied-Frames (Basis-Koordinaten, ``OpwKinematics.link_frames``) **dieses einen**
    Samples. ``compose(base, link)`` liegt darum bereits im Teil-/Wandsystem —
    dieselbe eine Transformationsstelle wie die Simulation (ADR-006), hier nur auf
    einen Frame statt die ganze Bahn angewendet (rein, ohne Geo). Der Endeffektor
    (``causer_link == TOOL_INDEX``) verkettet zusaetzlich den TCP-Frame — derselbe
    ``world_tcp`` wie ``print_point`` in :func:`fgc.collision.check.find_collisions`.

    Fail-soft: ``None``, wenn kein Verursacher bekannt ist oder die noetigen Frames
    fehlen (z. B. Endeffektor-Verursacher ohne TCP-Frame).
    """
    if causer_link is None or link_frames is None:
        return None
    from fgc.simulation import transform

    if causer_link == _check.TOOL_INDEX:
        if tcp_frame is None or len(link_frames) < 7:
            return None
        world_flansch = transform.compose(base, link_frames[6])
        world_tcp = transform.compose(world_flansch, tcp_frame)
        return world_tcp.pos_mm
    if not (0 <= causer_link < len(link_frames)):
        return None
    world_link = transform.compose(base, link_frames[causer_link])
    return world_link.pos_mm


# ---------------------------------------------------------------------------
# Orchestrator: aus Trajektorie + Toolpath + Teil-Mesh den Befund bauen
# ---------------------------------------------------------------------------


def _footprint(part_vertices_mm, part_faces, np, trimesh):
    """Slicer-Umriss (Welt-XY-Polygone) des Teil-Meshes knapp ueber dem Fuss.

    Faellt auf die Bounding-Box zurueck, wenn der Schnitt kein Polygon liefert
    (degenerierte/duenne Netze) — der Druckstand braucht *ein* Prisma.
    """
    from shapely.geometry import Polygon

    from fgc.geometry.section import section_at

    mesh = trimesh.Trimesh(
        vertices=np.asarray(part_vertices_mm, dtype=float),
        faces=np.asarray(part_faces, dtype=int),
        process=True,
    )
    polys = tuple(section_at(mesh, _FOOTPRINT_Z_MM))
    if polys:
        return polys
    lo, hi = mesh.bounds
    return (
        Polygon(
            [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
        ),
    )


@dataclass(frozen=True)
class _FindingInputs:
    """Loop-invarianter Unterbau **eines** ``find_collisions``-Aufrufs (Issue #162).

    Alles, was voller Befund (:func:`build_section_finding`) und verduennte Pruef-Tuer
    (:func:`check_part_clearance`) **teilen**: Kollisionsgeometrie, Basis-Frame, die
    Glied-Frames je Sample (FK), die Schicht je Sample, der Druckstand-Provider und
    der Endeffektor am TCP. So entsteht die Aufbau-Logik **einmal** (eine Quelle) und
    die beiden Tueren unterscheiden sich nur darin, **welche** Samples sie durch
    ``find_collisions`` schicken (voll vs. Travel-ausgeduennt).
    """

    geo: Any
    base: Frame
    link_frames_per_sample: list
    sample_layers: list[int]
    provider: Callable[[int], Any]
    tcp_frame: Frame | None
    tool_hull: Any
    sample_times: list[float]
    target_times_s: list[float]
    target_kinds: list[str]
    resolved_mode: str
    safety_distance_mm: float
    config: CollisionConfig


def _prepare_finding(robot_name: str, request: FindingRequest) -> _FindingInputs | None:
    """Baut den loop-invarianten Unterbau eines ``find_collisions``-Aufrufs — oder ``None``.

    Nimmt das gruppierte :class:`FindingRequest` (die Invarianten je Gruppe stehen
    dort). Fail-soft #1: liefert ``None``, wenn der Roboter **keine** Kollisions-
    Geometrie referenziert (Altprojekt / Roboter ohne ``robot_geometry``-Artefakt).
    """
    from fgc.collision.robot_geometry import collision_dir, load_robot_collision_geometry
    from fgc.kinematics.opw import OpwKinematics
    from fgc.simulation import transform

    traj = request.trajectory
    tp = request.toolpath
    part = request.part
    scene = request.scene
    refs = request.refs
    cfg = request.config or CollisionConfig()

    # Fail-soft #1: kein Kollisions-Geometrie-Artefakt referenziert ⇒ kein Befund.
    try:
        collision_dir(robot_name, refs.robots_dir)
    except FileNotFoundError:
        return None

    np, trimesh = _check._require_geo()

    geo = load_robot_collision_geometry(robot_name, refs.robots_dir)
    kin = OpwKinematics.from_robot(robot_name, refs.robots_dir)
    base = transform.frame_from_dict(traj.base_frame)

    link_frames = [kin.link_frames(s["joints_rad"]) for s in traj.samples]
    sample_times = [float(s["t_s"]) for s in traj.samples]
    target_layers = [int(t.get("layer", 0)) for t in tp.targets]
    target_kinds = [str(t.get("kind", "print")) for t in tp.targets]
    sample_layers = _ds.layer_per_sample(sample_times, traj.target_times_s, target_layers)

    # Druckstand aus der Szene-Gruppe (Invarianten s. :class:`SceneInputs`): das
    # wachsende Footprint-Prisma des aktuellen Teils, plus fruehere Teile (Issue #135),
    # der Boden bei lokal −z0 (nur z0 > 0, Art „abschnitt") und der zuschaltbare
    # Gebaeudekontext (Issue #131; nur bei context_enabled + „abschnitt").
    resolved_mode = "modul" if scene.mode == "modul" else "abschnitt"
    context_vertices_mm, context_faces = scene.context if scene.context else (None, None)
    context_mesh = None
    if (
        cfg.context_enabled
        and resolved_mode == "abschnitt"
        and context_vertices_mm is not None
        and context_faces is not None
    ):
        context_mesh = trimesh.Trimesh(
            vertices=np.asarray(context_vertices_mm, dtype=float),
            faces=np.asarray(context_faces, dtype=int),
            process=True,
        )

    ground_mesh = None
    earlier_meshes: tuple = ()
    if resolved_mode == "abschnitt":
        if float(scene.section_z0_mm) > 0.0:
            ground_mesh = _ds.ground_slab(-float(scene.section_z0_mm))
        earlier_meshes = tuple(
            trimesh.Trimesh(
                vertices=np.asarray(v, dtype=float),
                faces=np.asarray(f, dtype=int),
                process=True,
            )
            for v, f in scene.earlier_parts
        )

    footprint = _footprint(part.vertices_mm, part.faces, np, trimesh)
    spec = _ds.DruckstandSpec(
        footprint=footprint,
        layer_height_mm=float(tp.layer_height_mm),
        n_layers=int(tp.n_layers),
        earlier_parts=earlier_meshes,
        ground=ground_mesh,
        freizone_radius_mm=float(cfg.freizone_radius_mm),
        mode=resolved_mode,
        context=context_mesh,
    )
    # Der Hindernis-Provider kommt vom App-Ebenen-Backend-Schalter (Issue #213):
    # FCL-Referenz (Default, Altlaeufe byte-identisch) oder SDF-Backend — bewusst
    # NICHT in CollisionConfig (PRD #183, Kommentar 2026-07-14).
    from fgc.collision import backend as _backend

    provider = _backend.obstacle_provider_for(
        robot_name, spec, robots_dir=refs.robots_dir, geo=geo
    )

    # TCP-Frame **immer** (auch ohne Endeffektor-Mesh): er ankert die Freizone am
    # Druckpunkt, damit der prozessbedingte Nahkontakt Duese<->frischer Wulst nicht
    # chronisch als Warnung erscheint (ADR-024 Kontextpunkt 2). Die provisorische
    # Endeffektor-Huelle kommt zusaetzlich, sofern der Endeffektor ein Mesh traegt.
    tcp_frame = None
    tool_hull = None
    tool = refs.tool
    if tool is not None and getattr(tool, "tcp_frame", None):
        tcp_frame = transform.frame_from_dict(tool.tcp_frame)
        if getattr(tool, "mesh", None):
            mesh_path = (refs.tools_dir or _tools_dir()) / tool.mesh
            if mesh_path.exists():
                tool_mesh = trimesh.load(mesh_path, force="mesh", process=False)
                mt = transform.frame_from_dict(tool.mesh_transform or _identity_frame())
                tool_hull = _check.provisional_tool_hull(tool_mesh, mt, tcp_frame)

    return _FindingInputs(
        geo=geo,
        base=base,
        link_frames_per_sample=link_frames,
        sample_layers=sample_layers,
        provider=provider,
        tcp_frame=tcp_frame,
        tool_hull=tool_hull,
        sample_times=sample_times,
        target_times_s=list(traj.target_times_s),
        target_kinds=target_kinds,
        resolved_mode=resolved_mode,
        safety_distance_mm=float(cfg.safety_distance_mm),
        config=cfg,
    )


def _run_finding(
    inp: _FindingInputs,
    link_frames_per_sample: Sequence[Sequence[Frame]],
    sample_layers: Sequence[int],
) -> _check.CollisionReport:
    """Der **gemeinsame Urteils-Aufruf** von vollem Befund und Pruef-Tuer (Issue #176).

    Fuehrt ``find_collisions`` mit den urteilsrelevanten Parametern (Selbstkollision
    aus, Sicherheitsabstand, Endeffektor am TCP) aus — **nur die Sample-Auswahl**
    (``link_frames_per_sample`` + ``sample_layers``) unterscheidet die beiden Tueren:
    voller Befund (:func:`build_section_finding`) reicht **alle** Samples, die Pruef-
    Tuer (:func:`check_part_clearance`) die **Travel-ausgeduennten**. So steht der
    Aufruf samt Parametern **an einer Stelle** und die beiden Pruefungen koennen nicht
    mehr auseinanderaltern (Befund B6 der Zwischenkritik 2026-07-10): schaltet eine
    spaetere Scheibe z. B. die Selbstkollision zu, gilt das automatisch fuer **beide**
    Tueren. Die Sample-Auswahl/-Rueckrechnung bleibt bewusst beim jeweiligen Aufrufer
    (Naht zu #181: der Kollisions-ORT wird dort **additiv** an der Pruef-Tuer ergaenzt,
    ohne diesen geteilten Urteils-Kern zu beruehren).

    v1: Selbstkollision im automatischen Befund **aus** — der photographierte Schaden
    ist Arm<->Druckstand, nicht Arm<->Arm; Selbstkollision vervierfacht die Kosten
    (Spike-Budget war ohne sie gemessen). Bleibt in ``check`` verfuegbar und kann eine
    spaetere Scheibe / der Advisor gezielt zuschalten.
    """
    return _check.find_collisions(
        inp.geo,
        inp.base,
        link_frames_per_sample,
        sample_layers,
        inp.provider,
        tcp_frame=inp.tcp_frame,
        tool_hull=inp.tool_hull,
        safety_distance_mm=inp.safety_distance_mm,
        self_collision=False,
    )


def build_section_finding(robot_name: str, request: FindingRequest) -> dict[str, Any] | None:
    """Baut den additiven ``meta.collision``-Block einer simulierten Bahn — oder ``None``.

    Die eine Tuer „Bahn + Toolpath + Teil-Mesh (als :class:`FindingRequest`) rein,
    Befund raus". Fail-soft: liefert ``None``, wenn der Roboter **keine**
    Kollisions-Geometrie referenziert (Altprojekt / Roboter ohne
    ``robot_geometry``-Artefakt) — dann fehlt der Befund schlicht (kein Gate).
    Andere Fehler laufen an den Aufrufer, der ebenfalls fail-soft kapselt. Die
    Bedeutung der Eingabe-Gruppen dokumentiert :class:`FindingRequest`.

    **Voller Befund, keine Ausduennung.** Anders als die Pruef-Tuer
    (:func:`check_part_clearance`, Issue #162) prueft diese Tuer **jedes** Sample —
    der persistierte ``meta.collision``-Block traegt die lueckenlose Abstandskurve.
    """
    inp = _prepare_finding(robot_name, request)
    if inp is None:
        return None

    # Voller Befund: **alle** Samples durch den gemeinsamen Urteils-Kern (Issue #176).
    report = _run_finding(inp, inp.link_frames_per_sample, inp.sample_layers)

    travels = travel_intervals(inp.sample_times, inp.target_times_s, inp.target_kinds)
    return report_to_dict(
        report, config=inp.config, mode=inp.resolved_mode, travel_intervals=travels
    )


# ---------------------------------------------------------------------------
# Pruef-Tuer: verduennte find_collisions-Instanz je Teil (Issue #162, ADR-024)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RedInterval:
    """Ein rotes (kollidierendes) Intervall der Pruef-Tuer-Bahn (Issue #181).

    Verdichtetes Gegenstueck zu :class:`fgc.collision.check.Interval` (nur
    ``status == "red"``), mit auf die **Original-Sample-Indizierung**
    zurueckgerechneten Grenzen (die Pruef-Tuer urteilt intern ueber die
    Travel-ausgeduennte Liste, #162; :func:`original_sample_index` macht das
    rueckgaengig). Die **Liste** aller roten Intervalle statt nur des einen
    schlimmsten Samples ist die Vorarbeit fuer #165 (Teilen entlang der
    Verursacher-Achse): jedes Intervall benennt sein eigenes Glied, seinen
    eigenen Gegner und seinen eigenen schlimmsten Punkt.
    """

    link: int | None
    against: str | None
    start_index: int
    end_index: int
    worst_index: int
    min_distance_mm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "link": self.link,
            "against": self.against,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "worst_index": self.worst_index,
            "min_distance_mm": self.min_distance_mm,
        }


@dataclass(frozen=True)
class ClearanceVerdict:
    """Kompaktes frei/kollidiert-Urteil der Pruef-Tuer (Issue #162, Karte #139).

    Das Ergebnis der **verduennten Instanz des echten Kollisionsbefunds**: ein
    Teil-Rechteck + Option (Platzierung, IK-Konfiguration) rein, in wenigen Sekunden
    ``collides`` + Verursacher raus. **Kein Lauf-Artefakt** (anders als
    :func:`build_section_finding`) und **keine** lueckenlose Abstandskurve — der
    Zerlegungs-Constraint (#141) braucht nur das Urteil und den Verursacher.

    ``collides`` = mindestens ein Sample kollidiert (Abstand < 0). ``causer_link`` +
    ``penetration_mm`` benennen **Eindringrichtung** (welches Glied, ``TOOL_INDEX`` =
    Endeffektor) und **-tiefe** (mm) des schlimmsten Samples — der Hebel, entlang dem
    die Verfeinerung (#165) verkleinert. **Kein struktureller Blindfleck** (S6): alle
    Glieder inkl. Handgelenk/Endeffektor urteilen mit, denn es ist derselbe
    ``find_collisions`` wie der volle Befund — nur mit weniger (Travel-)Samples.

    ``worst_original_index`` / ``worst_layer`` / ``causer_position_mm`` /
    ``red_intervals`` (Issue #181, Befund B24, Vorarbeit fuer #165) sind der
    **Kollisions-ORT**, additiv zum bisherigen einen schlimmsten Sample:
    ``worst_original_index`` ist der schlimmste Sample-Index in **Original**-
    Indizierung (:func:`original_sample_index` rechnet den internen, Travel-
    ausgeduennten Index zurueck — ohne das zeigt der Index auf die ausgeduennte
    Liste und ist auf die Bahn nicht rueckfuehrbar); ``worst_layer`` seine Schicht
    (aus dem Toolpath); ``causer_position_mm`` die Position des Verursacher-Glieds
    **im Teil-/Wandkoordinatensystem** am schlimmsten Sample; ``red_intervals`` die
    Liste **aller** roten Intervalle (nicht nur des schlimmsten) mit je eigenem
    Glied/Gegner/schlimmstem Index — der Hebel, entlang dem #165 ohne Heuristik
    teilen kann. Alle vier sind ``None``/leer, wenn kein Verursacher bzw. keine
    Rot-Phase bekannt ist (z. B. ``collides is False``).
    """

    collides: bool
    min_distance_mm: float | None
    #: Eindringtiefe (mm) des schlimmsten Samples = ``max(0, −min_distance_mm)``.
    penetration_mm: float
    #: Verursachendes Glied des schlimmsten Samples (Eindringrichtung) oder None.
    causer_link: int | None
    causer_against: str | None
    n_red: int
    n_yellow: int
    #: Tatsaechlich geprueft (nach Travel-Ausduennung) …
    n_checked: int
    #: … von so vielen Samples der Bahn (vor Ausduennung).
    n_samples: int
    travel_thinned: bool
    tool_provisional: bool
    #: Kollisions-ORT (Issue #181) — schlimmster Sample-Index in Original-Indizierung.
    worst_original_index: int | None = None
    #: Schicht (layer) des schlimmsten Samples, aus dem Toolpath (Issue #181).
    worst_layer: int | None = None
    #: Position (x, y, z, mm) des Verursacher-Glieds im Teil-/Wandsystem (Issue #181).
    causer_position_mm: tuple[float, float, float] | None = None
    #: Alle roten Intervalle (Original-Indizierung), nicht nur das schlimmste (#181).
    red_intervals: tuple[RedInterval, ...] = ()

    @classmethod
    def from_report(
        cls,
        report: _check.CollisionReport,
        *,
        n_samples: int,
        travel_thinned: bool,
        kept: Sequence[int] | None = None,
        link_frames: Sequence[Sequence[Frame]] | None = None,
        sample_layers: Sequence[int] | None = None,
        base: Frame | None = None,
        tcp_frame: Frame | None = None,
    ) -> ClearanceVerdict:
        """Verdichtet einen (ausgeduennten) :class:`CollisionReport` zum Urteil.

        ``kept``/``link_frames``/``sample_layers``/``base``/``tcp_frame`` (Issue #181,
        alle optional, additiv) tragen den **Kollisions-ORT** bei: ohne sie (Altaufrufer)
        bleiben die vier neuen Felder ``None``/leer — dieselbe Fail-soft-Haltung wie
        anderswo im Modul, kein Bruch bestehender Aufrufer.
        """
        causer_link: int | None = None
        causer_against: str | None = None
        if 0 <= report.worst_index < len(report.samples):
            worst = report.samples[report.worst_index]
            causer_link, causer_against = worst.link, worst.against
        md = _num(report.min_distance_mm)  # Infinity (kein Nahpaar) → None
        pen = round(max(0.0, -md), ROUND_DECIMALS) if md is not None else 0.0

        # Kollisions-ORT (Issue #181): Original-Index, Schicht, Verursacher-Position,
        # rote Intervalle — alles aus Daten, die intern ohnehin berechnet vorliegen.
        kept_list = list(kept) if kept is not None else list(range(len(report.samples)))

        def _orig(thinned_index: int) -> int:
            # Faellt auf den rohen (ausgeduennten) Index zurueck, falls die Abbildung
            # ausnahmsweise nicht greift — Intervall-Indizes eines Berichts liegen
            # immer innerhalb von ``kept_list``, dieser Zweig ist defensiv (kein Crash).
            mapped = original_sample_index(kept_list, thinned_index)
            return thinned_index if mapped is None else mapped

        worst_original_index = original_sample_index(kept_list, report.worst_index)
        worst_layer: int | None = None
        if sample_layers is not None and 0 <= report.worst_index < len(sample_layers):
            worst_layer = int(sample_layers[report.worst_index])
        causer_position_mm: tuple[float, float, float] | None = None
        if (
            base is not None
            and link_frames is not None
            and 0 <= report.worst_index < len(link_frames)
        ):
            causer_position_mm = _causer_position_mm(
                base, link_frames[report.worst_index], causer_link, tcp_frame
            )
        red_intervals = tuple(
            RedInterval(
                link=iv.link,
                against=iv.against,
                start_index=_orig(iv.start_index),
                end_index=_orig(iv.end_index),
                worst_index=_orig(iv.worst_index),
                min_distance_mm=_num(iv.min_distance_mm),
            )
            for iv in report.intervals
            if iv.status == "red"
        )

        return cls(
            collides=report.n_red > 0,
            min_distance_mm=md,
            penetration_mm=pen,
            causer_link=causer_link,
            causer_against=causer_against,
            n_red=int(report.n_red),
            n_yellow=int(report.n_yellow),
            n_checked=len(report.samples),
            n_samples=int(n_samples),
            travel_thinned=bool(travel_thinned),
            tool_provisional=bool(report.tool_provisional),
            worst_original_index=worst_original_index,
            worst_layer=worst_layer,
            causer_position_mm=causer_position_mm,
            red_intervals=red_intervals,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "collides": self.collides,
            "min_distance_mm": self.min_distance_mm,
            "penetration_mm": self.penetration_mm,
            "causer_link": self.causer_link,
            "causer_against": self.causer_against,
            "n_red": self.n_red,
            "n_yellow": self.n_yellow,
            "n_checked": self.n_checked,
            "n_samples": self.n_samples,
            "travel_thinned": self.travel_thinned,
            "tool_provisional": self.tool_provisional,
            "worst_original_index": self.worst_original_index,
            "worst_layer": self.worst_layer,
            "causer_position_mm": (
                list(self.causer_position_mm) if self.causer_position_mm is not None else None
            ),
            "red_intervals": [iv.to_dict() for iv in self.red_intervals],
        }


def check_part_clearance(
    robot_name: str,
    request: FindingRequest,
    *,
    travel_stride: int = DEFAULT_TRAVEL_STRIDE,
) -> ClearanceVerdict | None:
    """Verduennte ``find_collisions``-Instanz als **Pruef-Tuer** der Zerlegung (Issue #162).

    Dieselbe Maschinerie und dasselbe :class:`FindingRequest` wie
    :func:`build_section_finding` (die Gruppen-Bedeutungen dort), aber **verduennt**:
    nur jedes ``travel_stride``-te Travel-Sample geht durch ``find_collisions``
    (Druck-Samples vollstaendig). Der **sichere** S5-Hebel — Travel ist ohnehin als
    „nicht lueckenlos geprueft" markiert (ADR-024) — drueckt die reale Denkmal-Bahn
    von ~11,5 s auf wenige Sekunden, **ohne** strukturellen Blindfleck (S6
    disqualifizierte den fcl-freien Grob-Check ``path_collides``: Handgelenk =
    39,4 % der Verursacher ausgeschlossen).

    Liefert ``None`` mit derselben Fail-soft-Semantik wie der volle Befund (kein
    Kollisions-Geometrie-Artefakt ⇒ nichts zu pruefen). ``travel_stride <= 1``
    prueft jedes Sample (dann identisch zum vollen Urteil, nur ohne Kurve). Reine
    Core-Funktion **ohne Lauf-Artefakt** — nutzbar von Zerlegung und weiteren
    Aufrufern (Naht zu #144: dessen Beschleunigung kommt beiden Tueren zugute).
    """
    inp = _prepare_finding(robot_name, request)
    if inp is None:
        return None

    # Sample-Auswahl der Pruef-Tuer: alle Druck-Samples + jedes ``travel_stride``-te
    # Travel-Sample. Die Rueckrechnung ``kept`` (Original-Indizes) bleibt hier lokal —
    # der Kollisions-ORT (#181) haengt an ihr und wird nur an ``from_report`` gereicht,
    # ohne den geteilten Urteils-Kern (``_run_finding``, #176) selbst zu beruehren.
    n_total = len(inp.link_frames_per_sample)
    flags = travel_flags(inp.sample_times, inp.target_times_s, inp.target_kinds)
    kept = thin_travel_indices(flags, int(travel_stride))
    link_frames = [inp.link_frames_per_sample[i] for i in kept]
    sample_layers = [inp.sample_layers[i] for i in kept]

    report = _run_finding(inp, link_frames, sample_layers)
    return ClearanceVerdict.from_report(
        report,
        n_samples=n_total,
        travel_thinned=len(kept) < n_total,
        kept=kept,
        link_frames=link_frames,
        sample_layers=sample_layers,
        base=inp.base,
        tcp_frame=inp.tcp_frame,
    )


def _tools_dir() -> Path:
    from fgc.paths import TOOLS_DIR

    return TOOLS_DIR


def _identity_frame() -> dict[str, Any]:
    return {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}

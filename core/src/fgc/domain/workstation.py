"""Workstation-Definitionen aus workstations/<name>.json (Issue #72, PRD #69).

Die Workstation ist die Aufstell-Umgebung des Roboters — ein projektunabhaengiges
Stammdaten-Artefakt analog zum Endeffektor (``domain/tool``). EINE Entity bildet
per ``mobility``-Feld beide Auspraegungen ab: die **stationaere Zelle**
(``stationary``) und die **mobile Workstation** (``mobile`` — faehrt zur Wand,
druckt vor Ort). Das Hoehenmodell haengt an ``height_adjustable``:

- nicht-verstellbar → geordneter Satz ``base_heights_mm`` (Podesthoehen, inkl. 0)
- verstellbar → stufenloser ``height_range_mm`` ``{min, max}`` (min < max)

Das Schema (``workstation.schema.json``) erlaubt beide Hoehenfelder; die
**Branch-Regel** (welches Feld je nach ``height_adjustable`` noetig und gueltig
ist) erzwingt diese Domaene beim Laden/Bauen — kaputte Werte → klarer
``ValueError``.

Geschrieben wird **atomar** (Temp-Datei + ``os.replace``, ADR-018 — dasselbe
Muster wie ``fgc.project.write_project``), serialisiert je Pfad ueber einen
``workstation_lock``.

Seit Issue #78 (ADR-021) traegt die Workstation **optional** ein Mesh der
Aufstell-Umgebung (``mesh``, STL/OBJ/GLB im selben Verzeichnis) plus zwei
optionale Frames (ADR-006): die Lage der Roboterbasis auf der Workstation
(``robot_base_frame`` — per Flaechen-Klick/Bohrbild gesetzt) und die
Arbeitsflaeche (``work_surface_frame``). Alle drei sind additiv und fehlen bei
Altbestand — dann bleibt die Workstation reine strukturierte Zahlenfelder wie
zuvor. Das Mesh selbst legt die Aktions-Schicht ab (``create_workstation``,
Upload wie beim Endeffektor); die Domaene fuehrt nur den Dateinamen + die Frames.

Seit Issue #136 (ADR-022) traegt die Workstation zusaetzlich **optional** die
S1-Stammdaten des Aufbaus: ``io_channels`` (Kanal-Mapping, ADR-011) und
``deadtime`` (Totzeit, ADR-012). Verkabelung und Schlauch-Totzeit sind
Eigenschaften des Aufbaus, nicht des Werkzeugs (dasselbe Werkzeug kann an zwei
Robotern anders verkabelt sein). Der Modul-Export generiert daraus das Setup;
Altbestand ohne die Felder gilt als „unbestaetigt" (additiv, wie die Frames).
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fgc import paths

#: Default-Sicherheitsabstand zur Wand/Umgebung in mm (Issue #72).
DEFAULT_SAFETY_MIN_DISTANCE_MM = 50.0

#: Prozessweite Registry von Workstation-Locks (ADR-018), analog ``project_lock``:
#: je aufgeloestem Datei-Pfad genau ein ``RLock``. ``_registry_guard`` serialisiert
#: nur das *Anlegen* eines Eintrags, damit zwei Threads, die dieselbe Workstation
#: zum ersten Mal anfassen, nicht zwei Locks bauen.
_workstation_locks: dict[str, threading.RLock] = {}
_registry_guard = threading.Lock()


@contextmanager
def workstation_lock(path: Path) -> Iterator[None]:
    """Serialisiert die Read-Modify-Write-Sektion je Workstation-Datei (ADR-018).

    FastAPI fuehrt die synchronen CRUD-Endpunkte im Threadpool aus → echte
    Nebenlaeufigkeit. Ohne Serialisierung koennten zwei parallele mutierende
    Requests denselben Stand lesen und nacheinander schreiben (Lost Update). Der
    Schluessel ist der ``.resolve()``-te Datei-Pfad; der Lock ist ein ``RLock``
    (reentrant je Thread), analog ``fgc.project.project_lock``.
    """
    key = str(path.resolve())
    with _registry_guard:
        lock = _workstation_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _workstation_locks[key] = lock
    with lock:
        yield


@dataclass(frozen=True)
class WorkstationDef:
    """Definition einer Workstation aus workstations/<name>.json (Issue #72).

    Analoges Konzept zu ``ToolDef`` — projektunabhaengige Stammdaten, die nur
    geladen und referenziert werden. Genau eines der Hoehenfelder ist je nach
    ``height_adjustable`` gesetzt (Branch-Regel, per ``load``/``build`` erzwungen):
    ``base_heights_mm`` (nicht-verstellbar) **oder** ``height_range_mm``
    (verstellbar, als ``(min, max)``-Tupel).
    """

    name: str
    mobility: str  # "stationary" | "mobile"
    height_adjustable: bool
    base_heights_mm: tuple[float, ...] = ()
    height_range_mm: tuple[float, float] | None = None
    safety_min_distance_mm: float = DEFAULT_SAFETY_MIN_DISTANCE_MM
    vendor: str = ""
    #: Namen der Roboter, zu denen die Workstation passt (Kompatibilitaets-Tags,
    #: Issue #71/#72). Leer = 'unbekannt', nicht 'inkompatibel' (Migrationsschutz).
    compatible_robots: tuple[str, ...] = field(default_factory=tuple)
    #: Dateiname des optionalen Umgebungs-Meshes im selben Verzeichnis (Issue #78,
    #: ADR-021). None = kein Mesh (reine Zahlenfelder wie bisher).
    mesh: str | None = None
    #: Lage der Roboterbasis relativ zum Mesh-Ursprung als Frame-Dict {pos_mm, quat}
    #: (ADR-006, Issue #78). Per Flaechen-Klick oder erkanntem Bohrbild gesetzt;
    #: None = nicht platziert.
    robot_base_frame: dict[str, Any] | None = None
    #: Arbeitsflaeche als Frame-Dict {pos_mm, quat} (ADR-006, Issue #78); None = nicht gewaehlt.
    work_surface_frame: dict[str, Any] | None = None
    #: Kanal-Mapping logischer Kanal -> physischer AO/DO-Ausgang (ADR-011). S1-Stammdaten
    #: des Aufbaus (Verkabelung, Issue #136/ADR-022); additiv, None = 'unbestaetigt'
    #: (Altbestand ohne Feld). Der Modul-Export generiert daraus das Setup.
    io_channels: dict[str, Any] | None = None
    #: Gemessene Totzeit des Materialsystems (ADR-012) als Dict {t_tot_s, compensation,
    #: [provisional]}. S1-Stammdaten (Issue #136); additiv, None = 'unbestaetigt';
    #: 'provisional': true = gemessen ausstehend (gilt fuers Gate als unbestaetigt).
    deadtime: dict[str, Any] | None = None

    @classmethod
    def load(cls, name: str, workstations_dir: Path | None = None) -> WorkstationDef:
        """Laedt eine Workstation-Definition aus workstations/<name>.json.

        Wirft ``FileNotFoundError``, wenn die Datei fehlt. Validiert gegen das
        Workstation-Schema (``fgc.domain.validate``) **und** die Hoehen-Branch-Regel
        (``_validate_height_model``) — kaputte Werte → klarer ``ValueError``.
        """
        from fgc.domain import validate  # lokaler Import: kein Zirkel

        # Verzeichnis-Konstante zur Aufrufzeit aus fgc.paths lesen (Test-Seam,
        # Issue #197): ein Patch auf fgc.paths.WORKSTATIONS_DIR statt einer Import-Kopie.
        base = workstations_dir or paths.WORKSTATIONS_DIR
        path = base / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in base.glob("*.json")) if base.exists() else []
            raise FileNotFoundError(
                f"Workstation-Definition {path.name!r} fehlt in workstations/ — "
                f"vorhanden: {available}"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        validate(raw, "workstation")

        height_adjustable = bool(raw["height_adjustable"])
        base_heights = tuple(float(h) for h in raw.get("base_heights_mm", ()))
        rng_raw = raw.get("height_range_mm")
        height_range = (float(rng_raw["min"]), float(rng_raw["max"])) if rng_raw else None
        _validate_height_model(height_adjustable, base_heights, height_range)

        return cls(
            name=raw["name"],
            mobility=str(raw["mobility"]),
            height_adjustable=height_adjustable,
            base_heights_mm=base_heights,
            height_range_mm=height_range,
            safety_min_distance_mm=float(
                raw.get("safety_min_distance_mm", DEFAULT_SAFETY_MIN_DISTANCE_MM)
            ),
            vendor=str(raw.get("vendor", "")),
            compatible_robots=tuple(raw.get("compatible_robots") or ()),
            mesh=raw.get("mesh"),
            robot_base_frame=raw.get("robot_base_frame"),
            work_surface_frame=raw.get("work_surface_frame"),
            io_channels=raw.get("io_channels"),
            deadtime=raw.get("deadtime"),
        )


def safe_workstation_name(name: str) -> str:
    """Leitet einen datei-sicheren Workstation-Namen aus der Nutzereingabe ab.

    Kleingeschrieben, auf ASCII normalisiert, Nicht-alphanumerisches zu ``_``
    (analog ``safe_tool_name`` — der Name ist zugleich Dateiname *und* das
    ``name``-Feld). Wirft ``ValueError`` bei leerer/degenerierter Eingabe.
    """
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")
    if not stem:
        raise ValueError(
            f"Workstation-Name {name!r} ergibt keinen gueltigen Dateinamen "
            "(mindestens ein Buchstabe/Ziffer noetig)."
        )
    return stem


def _validate_height_model(
    height_adjustable: bool,
    base_heights_mm: tuple[float, ...],
    height_range_mm: tuple[float, float] | None,
) -> None:
    """Erzwingt die Hoehen-Branch-Regel (ueber das rohe Schema hinaus, Issue #72).

    Das Schema erlaubt beide Hoehenfelder; welches je nach ``height_adjustable``
    noetig und gueltig ist, ist eine Domaenen-Regel:

    - verstellbar → ``height_range_mm`` mit ``min < max`` noetig
    - nicht-verstellbar → ``base_heights_mm`` noetig, **aufsteigend geordnet**
      (streng), inkl. ``0`` (Bodenhoehe)

    Wirft ``ValueError`` mit klarer Meldung bei Verstoss.
    """
    if height_adjustable:
        if height_range_mm is None:
            raise ValueError(
                "hoehenverstellbare Workstation verlangt 'height_range_mm' {min, max}."
            )
        lo, hi = height_range_mm
        if not lo < hi:
            raise ValueError(
                f"'height_range_mm' verlangt min < max, bekam min={lo}, max={hi}."
            )
    else:
        if not base_heights_mm:
            raise ValueError(
                "nicht-hoehenverstellbare Workstation verlangt 'base_heights_mm' "
                "(geordneter Satz Podesthoehen inkl. 0)."
            )
        heights = list(base_heights_mm)
        if any(a >= b for a, b in zip(heights, heights[1:], strict=False)):
            raise ValueError(
                f"'base_heights_mm' muss streng aufsteigend geordnet sein, bekam {heights}."
            )
        if 0 not in heights:
            raise ValueError(
                f"'base_heights_mm' muss 0 (Bodenhoehe) enthalten, bekam {heights}."
            )


def build_workstation_artifact(
    name: str,
    mobility: str,
    height_adjustable: bool,
    *,
    base_heights_mm: list[float] | None = None,
    height_range_mm: dict[str, float] | None = None,
    safety_min_distance_mm: float = DEFAULT_SAFETY_MIN_DISTANCE_MM,
    vendor: str = "",
    compatible_robots: list[str] | None = None,
    mesh: str | None = None,
    robot_base_frame: dict[str, Any] | None = None,
    work_surface_frame: dict[str, Any] | None = None,
    io_channels: dict[str, Any] | None = None,
    deadtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Baut das schema-valide Workstation-Artefakt aus den Bibliothek-Eingaben.

    Der Datenvertrag ``workstation.schema.json`` ist die Wahrheit (P2/ADR-004).
    Setzt je nach ``height_adjustable`` **genau** das passende Hoehenfeld (das
    andere wird weggelassen), prueft die Branch-Regel (``_validate_height_model``)
    und validiert am Ende gegen das Schema. Wirft ``ValueError`` bei Vertragsbruch
    (Branch-Regel verletzt, Schema-widrig) — CLI/API behandeln das einheitlich als
    422.
    """
    import jsonschema

    from fgc.domain import validate  # lokaler Import: kein Zirkel

    heights = tuple(float(h) for h in (base_heights_mm or ()))
    rng = (
        (float(height_range_mm["min"]), float(height_range_mm["max"]))
        if height_range_mm
        else None
    )
    # Branch-Regel vor dem Bauen — klarer ValueError statt kryptischem Schema-Fehler.
    _validate_height_model(height_adjustable, heights, rng)

    artifact: dict[str, Any] = {
        "schema_version": "0.1",
        "name": name,
        "mobility": mobility,
        "height_adjustable": height_adjustable,
        "safety_min_distance_mm": float(safety_min_distance_mm),
    }
    if height_adjustable:
        artifact["height_range_mm"] = {"min": rng[0], "max": rng[1]}  # type: ignore[index]
    else:
        artifact["base_heights_mm"] = [float(h) for h in heights]
    if vendor:
        artifact["vendor"] = vendor
    # Nur schreiben, wenn Tags gesetzt sind — leer/fehlt = 'unbekannt' (#71/#72).
    if compatible_robots:
        artifact["compatible_robots"] = [str(r) for r in compatible_robots]
    # Mesh + Platzierungs-Frames additiv (Issue #78, ADR-021): nur schreiben, wenn
    # gesetzt — Altbestand ohne diese Felder bleibt beim Bearbeiten byte-gleich.
    if mesh is not None:
        artifact["mesh"] = mesh
    if robot_base_frame is not None:
        artifact["robot_base_frame"] = robot_base_frame
    if work_surface_frame is not None:
        artifact["work_surface_frame"] = work_surface_frame
    # S1-Stammdaten (Issue #136): Kanal-Mapping + Totzeit additiv — nur schreiben,
    # wenn gesetzt (Altbestand ohne Felder bleibt byte-gleich und gilt als 'unbestaetigt').
    if io_channels is not None:
        artifact["io_channels"] = io_channels
    if deadtime is not None:
        artifact["deadtime"] = deadtime

    try:
        validate(artifact, "workstation")
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Workstation-Definition ist schema-widrig: {exc.message}") from exc
    return artifact


def write_workstation_artifact(path: Path, artifact: dict[str, Any]) -> Path:
    """Schreibt das Workstation-Artefakt **atomar** (ADR-018) nach ``path``.

    Muster wie ``fgc.project.write_project``: erst in eine Temp-Datei im selben
    Verzeichnis, dann per ``replace_with_retry`` einschwenken (atomarer Rename auf
    Windows/POSIX, mit kurzem Retry gegen den transienten WinError 5/32, Issue
    #158) — nie ein halb geschriebenes File. Validiert vor dem Schreiben gegen das
    Schema (defensiv; ``build_workstation_artifact`` hat i.d.R. schon validiert).
    Der Aufrufer haelt den ``workstation_lock`` fuer die RMW-Sektion.
    """
    from fgc.atomic_io import replace_with_retry  # lokaler Import: kein Zirkel
    from fgc.domain import validate  # lokaler Import: kein Zirkel

    validate(artifact, "workstation")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(artifact, indent=2, ensure_ascii=False)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_text(text, encoding="utf-8")
    replace_with_retry(tmp, path)
    return path

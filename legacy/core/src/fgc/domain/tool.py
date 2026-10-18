"""Endeffektor-Definitionen aus tools/<name>.json (ADR-011, Issue #21).

Der Endeffektor ist ein projektunabhaengiges Artefakt: TCP-Frame relativ Flansch
(ADR-006), Gewicht/Schwerpunkt (v1: statischer Payload-Check) und Deklaration
der logischen IO-Kanaele (ADR-011). Das Setup mappt die deklarierten Kanaele auf
physische Ausgaenge; der Endeffektor *deklariert* sie nur.
"""

from __future__ import annotations

import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fgc import paths

#: Zulaessige Mesh-Dateiformate fuer den Endeffektor-Konfigurator (Issue #28).
#: STL/OBJ sind einheitenlose Dreiecksnetze (intern mm angenommen, ADR-006), GLB
#: ist binaeres glTF. Erweiterbar, sobald weitere Formate gebraucht werden.
MESH_SUFFIXES = (".stl", ".obj", ".glb")

#: Obergrenze fuer hochgeladene Mesh-Dateien (Robustheit gegen Fehlbedienung).
#: Ein Endeffektor-Mesh ist klein; 50 MB ist grosszuegig, verhindert aber
#: versehentliche Riesen-Uploads (z.B. ganzes Gebaeude-Mesh).
MAX_MESH_BYTES = 50 * 1024 * 1024

#: Identitaets-Frame (Flansch-Ursprung) — Default fuer ``mesh_transform``.
IDENTITY_FRAME: dict[str, Any] = {"pos_mm": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]}


@dataclass(frozen=True)
class ChannelDecl:
    """Deklaration eines logischen IO-Kanals eines Endeffektors (ADR-011).

    Der Endeffektor *deklariert* den Kanal (Name + Art + optionale Beschreibung);
    das Setup *mappt* ihn auf einen physischen AO-/DO-Ausgang. `kind` ist die
    erwartete Ausgangsart: ``'analog'`` (AO, logischer Wertebereich 0..1) oder
    ``'digital'`` (DO, 0 oder 1).
    """

    kind: str  # "analog" | "digital"
    description: str = ""
    default_value: float = 0.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChannelDecl:
        return cls(
            kind=str(raw["kind"]),
            description=str(raw.get("description", "")),
            default_value=float(raw.get("default_value", 0.0)),
        )


@dataclass(frozen=True)
class ToolDef:
    """Definition eines Endeffektors aus tools/<name>.json.

    Analoges Konzept zu `RobotDef` aus domain/robot.py — projektunabhaengige
    Stammdaten, die nur geladen und referenziert werden. v1-Einschraenkung:
    nur statischer Payload-Check (Gewicht gegen Traglast), keine
    Dynamik-/Momentenrechnung.
    """

    name: str
    tcp_frame: dict[str, Any]  # {"pos_mm": [x, y, z], "quat": [w, x, y, z]}
    weight_kg: float
    cog_mm: tuple[float, float, float] | None = None
    vendor: str = ""
    mesh: str | None = None
    #: Lage des Mesh-Ursprungs relativ zum Flansch (Konfigurator, Issue #28).
    mesh_transform: dict[str, Any] | None = None
    channels: dict[str, ChannelDecl] = field(default_factory=dict)
    #: Namen der Roboter, zu denen der Endeffektor passt (Kompatibilitaets-Tags,
    #: Issue #71). Leer = 'unbekannt', nicht 'inkompatibel' (Migrationsschutz);
    #: Altbestand ohne Feld laedt mit leerem Tupel. Noch keine Filterwirkung (#74).
    compatible_robots: tuple[str, ...] = ()
    #: Ehrliche, additive Kennzeichnung eines noch nicht ausgemessenen TCP (Issue #136,
    #: Geist von ADR-013/``deadtime.provisional``): ``True`` = der TCP-Versatz ist ein
    #: Schaetzwert (wie ``fgc.setup.PROVISIONAL_TCP``), noch nicht am Geraet vermessen.
    #: Fehlt/False = bestaetigt (der Konfigurator-Upload traegt einen realen TCP). Das
    #: Gate des Modul-Exports (ADR-006/022) laesst nur einen nicht-provisorischen TCP durch.
    tcp_provisional: bool = False
    #: Huellkennzahl um die Flanschachse (Bounding-Radius + Laenge, ADR-026 Punkt 4,
    #: PRD #225, Issue #229): {"radius_mm": ..., "length_mm": ...}. Beim Upload einmalig
    #: aus dem Mesh berechnet (Migrationslogik wie ``compatible_robots``, #71); fehlt bei
    #: Tools ohne Mesh oder Altbestand vor #229 = 'unbekannt' -> neutraler Prior. Nie im
    #: Vorschlagspfad neu berechnet (kein Mesh-Laden dort).
    envelope_mm: dict[str, float] | None = None

    @classmethod
    def load(cls, name: str, tools_dir: Path | None = None) -> ToolDef:
        """Laedt eine Endeffektor-Definition aus tools/<name>.json.

        Wirft ``FileNotFoundError``, wenn die Datei fehlt.
        Validiert gegen das Endeffektor-Schema (``fgc.domain.validate``).
        """
        from fgc.domain import validate  # lokaler Import: kein Zirkel

        # Verzeichnis-Konstante zur Aufrufzeit aus fgc.paths lesen (Test-Seam,
        # Issue #197): ein Patch auf fgc.paths.TOOLS_DIR statt einer Import-Kopie.
        path = (tools_dir or paths.TOOLS_DIR) / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in (tools_dir or paths.TOOLS_DIR).glob("*.json"))
            raise FileNotFoundError(
                f"Endeffektor-Definition {path.name!r} fehlt in tools/ — vorhanden: {available}"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        validate(raw, "tool")

        channels = {
            ch_name: ChannelDecl.from_dict(ch_raw)
            for ch_name, ch_raw in raw["channels"].items()
        }
        cog = raw.get("cog_mm")
        return cls(
            name=raw["name"],
            tcp_frame=raw["tcp_frame"],
            weight_kg=float(raw["weight_kg"]),
            cog_mm=(float(cog[0]), float(cog[1]), float(cog[2])) if cog else None,
            vendor=str(raw.get("vendor", "")),
            mesh=raw.get("mesh"),
            mesh_transform=raw.get("mesh_transform"),
            channels=channels,
            compatible_robots=tuple(raw.get("compatible_robots") or ()),
            tcp_provisional=bool(raw.get("tcp_provisional", False)),
            envelope_mm=dict(raw["envelope_mm"]) if raw.get("envelope_mm") else None,
        )

    @property
    def channel_names(self) -> tuple[str, ...]:
        """Gibt die Namen der deklarierten logischen IO-Kanaele zurueck (ADR-011)."""
        return tuple(self.channels.keys())

    def payload_ok(self, payload_kg: float) -> bool:
        """Gibt ``True`` zurueck, wenn das Werkzeuggewicht die Traglast nicht ueberschreitet."""
        return self.weight_kg <= payload_kg

    def payload_margin_kg(self, payload_kg: float) -> float:
        """Gibt den Spielraum in kg zurueck (negativ = Ueberschreitung)."""
        return payload_kg - self.weight_kg


# ---------------------------------------------------------------------------
# Endeffektor-Konfigurator (Issue #28): Upload validieren + Definition bauen
# ---------------------------------------------------------------------------


def safe_tool_name(name: str) -> str:
    """Leitet einen datei-sicheren Endeffektor-Namen aus der Nutzereingabe ab.

    Kleingeschrieben, auf ASCII normalisiert, Nicht-alphanumerisches zu ``_``
    (analog ``fgc.project.project_slug``, aber mit ``_`` — der Endeffektor-Name
    ist zugleich Dateiname *und* das ``name``-Feld). Wirft ``ValueError`` bei
    leerer/degenerierter Eingabe (kein leerer Dateiname).
    """
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")
    if not stem:
        raise ValueError(
            f"Endeffektor-Name {name!r} ergibt keinen gueltigen Dateinamen "
            "(mindestens ein Buchstabe/Ziffer noetig)."
        )
    return stem


def mesh_suffix(filename: str) -> str:
    """Gibt das (kleingeschriebene) Mesh-Dateisuffix zurueck, validiert gegen MESH_SUFFIXES.

    Wirft ``ValueError`` bei unbekanntem/fehlendem Format — klare Fehlermeldung
    fuer den Upload (kein Absturz bei falschem Dateityp).
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in MESH_SUFFIXES:
        raise ValueError(
            f"Mesh-Format {suffix or '(keins)'!r} nicht unterstuetzt — "
            f"erlaubt: {', '.join(MESH_SUFFIXES)}."
        )
    return suffix


def validate_mesh_bytes(data: bytes, suffix: str) -> None:
    """Prueft hochgeladene Mesh-Bytes auf Groesse und Ladbarkeit (Robustheit).

    Wirft ``ValueError``, wenn die Datei zu gross ist, leer ist oder von trimesh
    nicht als nicht-leeres Dreiecksnetz geladen werden kann (kaputtes Mesh).
    Der Kern legt nur schema-valide, ladbare Endeffektoren ab.
    """
    if not data:
        raise ValueError("Mesh-Datei ist leer.")
    if len(data) > MAX_MESH_BYTES:
        raise ValueError(
            f"Mesh-Datei zu gross ({len(data)} Bytes) — Grenze {MAX_MESH_BYTES} Bytes."
        )
    import trimesh  # lokaler Import: schwere Abhaengigkeit nur bei Upload

    try:
        loaded = trimesh.load(io.BytesIO(data), file_type=suffix.lstrip("."))
    except Exception as exc:  # noqa: BLE001 — jede Ladefehler-Art als ValueError melden
        raise ValueError(f"Mesh-Datei nicht lesbar ({suffix}): {exc}") from exc

    # trimesh liefert je nach Format ein Trimesh oder eine Scene (mehrere Geometrien).
    if isinstance(loaded, trimesh.Scene):
        n_vertices = sum(len(g.vertices) for g in loaded.geometry.values())
    else:
        n_vertices = len(getattr(loaded, "vertices", []))
    if n_vertices == 0:
        raise ValueError(f"Mesh-Datei enthaelt keine Geometrie ({suffix}).")


def compute_tool_envelope(
    mesh_bytes: bytes, suffix: str, mesh_transform: dict[str, Any] | None = None
) -> dict[str, float]:
    """Berechnet die Huellkennzahl (Bounding-Radius + Laenge um die Flanschachse) aus dem Mesh.

    Zweite Groesse der Tool-Aehnlichkeits-Regel des Platzierungs-Priors (ADR-026
    Punkt 4, PRD #225, Issue #229) — neben dem TCP-Versatz. Nur beim Upload
    aufgerufen (trimesh laeuft dort ohnehin fuer ``validate_mesh_bytes``); der
    Vorschlagspfad laedt kein Mesh.

    Transformiert die Mesh-Vertices mit ``mesh_transform`` (fehlt = Identitaet,
    ``IDENTITY_FRAME`` — Mesh-Ursprung liegt im Flansch) in den Flansch-Frame und
    misst dort entlang/um die Flansch-z-Achse (ADR-006-Konvention, aktive Rotation
    ``point_parent = R(quat)*point_local + pos`` — dieselbe wie
    ``fgc.simulation.transform.quat_rotate``): ``length_mm`` ist die Ausdehnung
    entlang z (max - min), ``radius_mm`` der groesste radiale Abstand zur
    z-Achse. Deterministisch fuer ein gegebenes Mesh + Transform (reine
    Extremwert-Aggregation, keine Reihenfolgeabhaengigkeit).

    Wirft dieselben Fehler wie ``validate_mesh_bytes`` bei unlesbarem Mesh — wird
    stets *nach* ``validate_mesh_bytes`` aufgerufen, das schon geprueft hat.
    """
    import numpy as np
    import trimesh

    loaded = trimesh.load(io.BytesIO(mesh_bytes), file_type=suffix.lstrip("."))
    if isinstance(loaded, trimesh.Scene):
        vertices = np.concatenate(
            [np.asarray(g.vertices, dtype=float) for g in loaded.geometry.values()], axis=0
        )
    else:
        vertices = np.asarray(loaded.vertices, dtype=float)

    xf = mesh_transform or IDENTITY_FRAME
    pos = np.array([float(c) for c in xf["pos_mm"]], dtype=float)
    w, x, y, z = (float(c) for c in xf["quat"])
    norm = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    # Rotationsmatrix aus Einheitsquaternion [w, x, y, z] (aktive Rotation, ADR-006).
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    flange = vertices @ rot.T + pos

    z_vals = flange[:, 2]
    length_mm = float(z_vals.max() - z_vals.min())
    radial = np.sqrt(flange[:, 0] ** 2 + flange[:, 1] ** 2)
    radius_mm = float(radial.max())
    return {"radius_mm": radius_mm, "length_mm": length_mm}


def build_tool_artifact(
    name: str,
    tcp_frame: dict[str, Any],
    weight_kg: float,
    channels: dict[str, dict[str, Any]],
    *,
    vendor: str = "",
    cog_mm: list[float] | None = None,
    mesh: str | None = None,
    mesh_transform: dict[str, Any] | None = None,
    compatible_robots: list[str] | None = None,
    tcp_provisional: bool = False,
    envelope_mm: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Baut das schema-valide Endeffektor-Artefakt aus den Konfigurator-Eingaben.

    Der Datenvertrag ``tool.schema.json`` ist die Wahrheit (P2/ADR-004): die
    Frames sind ``{pos_mm, quat}`` in mm/rad (ADR-006), die Kanaele Deklarationen
    (ADR-011). Validiert am Ende gegen das Schema — wirft ``jsonschema.ValidationError``
    bei Vertragsbruch (z.B. leere ``channels``, negatives Gewicht).
    """
    import jsonschema

    from fgc.domain import validate  # lokaler Import: kein Zirkel

    artifact: dict[str, Any] = {
        "schema_version": "0.1",
        "name": name,
        "tcp_frame": tcp_frame,
        "weight_kg": float(weight_kg),
        "channels": channels,
    }
    if vendor:
        artifact["vendor"] = vendor
    if cog_mm is not None:
        artifact["cog_mm"] = [float(c) for c in cog_mm]
    if mesh is not None:
        artifact["mesh"] = mesh
    if mesh_transform is not None:
        artifact["mesh_transform"] = mesh_transform
    # Nur schreiben, wenn tatsaechlich Tags gesetzt sind — ein Altbestand ohne
    # Feld bleibt so beim Bearbeiten unveraendert (Missing/leer = 'unbekannt', #71).
    if compatible_robots:
        artifact["compatible_robots"] = [str(r) for r in compatible_robots]
    # Nur schreiben, wenn provisorisch (Issue #136) — Altbestand ohne Feld bleibt
    # byte-gleich und gilt als bestaetigt (der Konfigurator-Upload traegt einen realen TCP).
    if tcp_provisional:
        artifact["tcp_provisional"] = True
    # Nur schreiben, wenn tatsaechlich berechnet — Tools ohne Mesh oder Altbestand vor
    # #229 bleiben byte-gleich ('unbekannt', kein Raten der Huellkennzahl, ADR-026 Pkt. 4).
    if envelope_mm is not None:
        artifact["envelope_mm"] = {
            "radius_mm": float(envelope_mm["radius_mm"]),
            "length_mm": float(envelope_mm["length_mm"]),
        }

    # Schema-Verletzung als ValueError melden (jsonschema.ValidationError ist keine
    # ValueError-Unterklasse), damit CLI/API sie einheitlich als 422 behandeln.
    try:
        validate(artifact, "tool")
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Endeffektor-Definition ist schema-widrig: {exc.message}") from exc
    return artifact

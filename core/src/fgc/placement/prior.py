"""fgc.placement.prior — Messwissen als Prior, das **lenkt und nie urteilt** (ADR-026, #230).

Schmale Tuer ``placement_prior(roboter, endeffektor, modulmasse, sicherheitszone)
→ PlacementPrior``: aus der versionierten W×T-Prior-Tabelle (Generator
``fgc.placement.prior_build``) liest dieses Modul je Modulmasse eine **konservative**
Such-Lenkung ab — Abstands-/Basishoehen-Verdichtung, IK-Konfig-Shortlist,
Machbarkeits-Erwartung. Geurteilt wird nie hier; das Urteil faellt spaeter auf der
echten Geometrie (Grob-Check + ``evaluate``). Die Einbindung in die Suche ist
Folge-Issue #232 — dieses Modul rechnet nur.

**Konservative Interpolation (kein Fit — die Effekte haben Knicke, ADR-026):** fuer
eine Modulmasse zwischen den Stuetzstellen waehlt der Prior die **naechste
schlechtere** Zelle (groesseres W **und** groesseres T ⇒ kleineres H_max) — nie ein
optimistisch gemittelter Zwischenwert.

**Jeder Fehlfall ⇒ neutraler Prior** (``NEUTRAL_PRIOR``), Suche wie ohne Messwissen:
kein Artefakt, fremder Roboter, unbekanntes/unaehnliches Tool, Modulmasse ausserhalb
des Gitters, provenienz-ungueltiges Artefakt. Eine ``angenommen-unmachbar``-Zelle
liefert dagegen einen **neutral-breiten** Prior mit **Unmachbarkeits-Erwartung**
(ehrliche Annahme, kein erfundener Messwert — Ersatz durch Messung: #226).

**Tool-Toleranz = konfigurierte Sicherheitszone (ADR-026 Punkt 4):** der Prior gilt
fuer ein fremdes Tool, wenn ‖Δ TCP-Versatz‖ **und** Δ Huellmass ≤ ``safety_distance_mm``.
Fehlt das Huellmass an einem der beiden Tools (Altbestand vor #229) ⇒ „unbekannt" ⇒
kein Uebertrag (nur der namensgleiche Referenz-Tool passt dann).

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fgc.domain.tool import ToolDef

__all__ = [
    "PRIOR_ARTIFACT_KIND",
    "PRIOR_SCHEMA_VERSION",
    "PriorTable",
    "PlacementPrior",
    "NEUTRAL_PRIOR",
    "load_prior_tables",
    "placement_prior",
]

#: Artefakt-Kennung + Schema-Version der Prior-Tabelle (ADR-004, Muster #219-Surrogat).
PRIOR_ARTIFACT_KIND = "placement-prior"
PRIOR_SCHEMA_VERSION = "1"

#: Zell-Status: gemessen vs. ehrlich angenommen (abgebrochene Messzelle, #226).
STATUS_MEASURED = "measured"
STATUS_ASSUMED_INFEASIBLE = "angenommen-unmachbar"

#: Erwartungswerte der Machbarkeit (Lenkung, nie Urteil).
FEAS_FEASIBLE = "feasible"
FEAS_INFEASIBLE = "infeasible"
FEAS_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Ergebnis: der Prior (neutral oder gemessen-gelenkt)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlacementPrior:
    """Die Such-Lenkung fuer eine Modulmasse — **lenkt, urteilt nie** (ADR-026 Punkt 3).

    ``is_neutral`` ⇒ kein Messwissen anwendbar (Suche wie ohne Prior). Sonst tragen
    ``standoff_focus_mm``/``base_height_focus_mm`` die Verdichtungs-Stuetzstellen (um
    die das Abstands-/Hoehenraster verdichtet wird), ``config_shortlist`` die zuerst zu
    bewertenden IK-Konfigurationen (Gewinner-Zelle + ``"auto"``) und
    ``feasibility_expectation`` die reine **Erwartung** (nie ein Urteil). ``h_max_mm``
    ist die gemessene max. zusammenhaengende Bandhoehe der herangezogenen Zelle.

    ``reason`` benennt die Herkunft (``"measured"``, ``STATUS_ASSUMED_INFEASIBLE`` oder
    der Neutral-Grund) — fuer Diagnose/Tests, nie fuer eine Verzweigung im Urteilspfad.
    """

    is_neutral: bool
    reason: str
    feasibility_expectation: str = FEAS_UNKNOWN
    standoff_focus_mm: float | None = None
    base_height_focus_mm: float | None = None
    config_shortlist: tuple[str, ...] = ()
    h_max_mm: float | None = None
    cell_key: str | None = None


#: Der neutrale Prior — Suche laeuft wie ohne Messwissen (jeder Fehlfall).
NEUTRAL_PRIOR = PlacementPrior(is_neutral=True, reason="neutral")


def _neutral(reason: str) -> PlacementPrior:
    return PlacementPrior(is_neutral=True, reason=reason)


# --------------------------------------------------------------------------- #
# Die Prior-Tabelle: geladenes, provenienz-geprueftes Artefakt
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PriorTable:
    """Eine geladene, provenienz-gepruefte Prior-Tabelle fuer **einen** Roboter+Tool.

    Reine Datenhuelle: ``from_artifact`` prueft die ADR-004-Provenienz (Kennung +
    Schema-Version) und **wirft** bei Fremd-/Falschartefakt (nie stilles Deuten);
    ``query`` liest je Modulmasse die konservative Lenkung ab.
    """

    robot: str
    tool: dict[str, Any]
    grid: dict[str, Any]
    cells: dict[str, dict[str, Any]]
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_artifact(cls, artifact: dict[str, Any]) -> PriorTable:
        kind = artifact.get("kind")
        if kind != PRIOR_ARTIFACT_KIND:
            raise ValueError(
                f"Kein Prior-Artefakt (kind={kind!r}, erwartet {PRIOR_ARTIFACT_KIND!r})."
            )
        schema = artifact.get("schema_version")
        if schema != PRIOR_SCHEMA_VERSION:
            raise ValueError(
                f"Prior-Schema {schema!r} != erwartet {PRIOR_SCHEMA_VERSION!r} "
                "(Artefakt aus einer anderen Code-Generation)."
            )
        robot = artifact.get("robot")
        if not robot:
            raise ValueError("Prior-Artefakt ohne Roboter-Schluessel.")
        return cls(
            robot=str(robot),
            tool=dict(artifact.get("tool") or {}),
            grid=dict(artifact.get("grid") or {}),
            cells=dict(artifact.get("cells") or {}),
            provenance=dict(artifact.get("provenance") or {}),
        )

    # -- Tool-Aehnlichkeit (ADR-026 Punkt 4) -----------------------------------

    def tool_matches(self, tool: ToolDef, safety_distance_mm: float) -> bool:
        """``True``, wenn ``tool`` als aehnlich genug zum Referenz-Tool gilt.

        Namensgleichheit passt immer (das vermessene Tool selbst). Sonst gilt der
        Prior nur, wenn ‖Δ TCP-Versatz‖ **und** Δ Huellmass ≤ ``safety_distance_mm``
        (ADR-026 Punkt 4). Fehlt an einem der beiden Tools das Huellmass ⇒ „unbekannt"
        ⇒ kein Uebertrag (grosszuegig, aber ehrlich: ein falscher Prior kostet nur
        Suchzeit, nie Korrektheit).
        """
        ref = self.tool
        if tool.name == ref.get("name"):
            return True
        ref_env = ref.get("envelope_mm")
        if tool.envelope_mm is None or not ref_env:
            return False
        ref_tcp = ref.get("tcp_pos_mm")
        if not ref_tcp:
            return False
        q_pos = tool.tcp_frame.get("pos_mm") if tool.tcp_frame else None
        if not q_pos:
            return False
        d_tcp = math.dist(
            [float(c) for c in q_pos[:3]], [float(c) for c in ref_tcp[:3]]
        )
        if d_tcp > safety_distance_mm:
            return False
        d_env = max(
            abs(float(tool.envelope_mm["radius_mm"]) - float(ref_env["radius_mm"])),
            abs(float(tool.envelope_mm["length_mm"]) - float(ref_env["length_mm"])),
        )
        return d_env <= safety_distance_mm

    # -- Zellwahl (konservative Interpolation, kein Fit) -----------------------

    def _conservative_cell(
        self, length_mm: float, thickness_mm: float
    ) -> tuple[str, dict[str, Any]] | None:
        """Die **naechste schlechtere** Zelle: kleinstes (W,T) mit W≥length und T≥thick.

        Groesseres W **und** groesseres T ⇒ kleineres H_max ⇒ konservativ. Gibt es keine
        dominierende Stuetzstelle (Modulmasse groesser als das Gitter), ist die Zelle
        **fehlend** ⇒ ``None`` ⇒ neutraler Prior (kein Extrapolieren ins Blaue).
        """
        best: tuple[tuple[float, float], str, dict[str, Any]] | None = None
        for key, cell in self.cells.items():
            w = float(cell["width_mm"])
            t = float(cell["thickness_mm"])
            if w + 1e-9 < length_mm or t + 1e-9 < thickness_mm:
                continue
            rank = (w, t)
            if best is None or rank < best[0]:
                best = (rank, key, cell)
        if best is None:
            return None
        return best[1], best[2]

    def query(
        self,
        length_mm: float,
        thickness_mm: float,
        *,
        height_mm: float | None = None,
    ) -> PlacementPrior:
        """Die konservative Lenkung fuer eine Modulmasse (naechste schlechtere Zelle)."""
        picked = self._conservative_cell(length_mm, thickness_mm)
        if picked is None:
            return _neutral("ausserhalb-gitter")
        key, cell = picked
        status = cell.get("status")
        h_max = cell.get("h_max_mm")
        h_max_f = None if h_max is None else float(h_max)

        if status == STATUS_ASSUMED_INFEASIBLE:
            # Neutral-breit (keine Verdichtung, keine Shortlist), aber mit
            # Unmachbarkeits-Erwartung — ehrliche Annahme, nie erfundener Messwert.
            return PlacementPrior(
                is_neutral=False,
                reason=STATUS_ASSUMED_INFEASIBLE,
                feasibility_expectation=FEAS_INFEASIBLE,
                h_max_mm=h_max_f,
                cell_key=key,
            )

        best = cell.get("best") or {}
        config = best.get("ik_config")
        shortlist: tuple[str, ...] = ()
        if config:
            shortlist = (str(config), "auto") if config != "auto" else ("auto",)

        expectation = FEAS_FEASIBLE
        if height_mm is not None and h_max_f is not None:
            expectation = FEAS_FEASIBLE if height_mm <= h_max_f + 1e-9 else FEAS_INFEASIBLE

        return PlacementPrior(
            is_neutral=False,
            reason=STATUS_MEASURED,
            feasibility_expectation=expectation,
            standoff_focus_mm=(
                None if best.get("standoff_mm") is None else float(best["standoff_mm"])
            ),
            base_height_focus_mm=(
                None if best.get("base_height_mm") is None else float(best["base_height_mm"])
            ),
            config_shortlist=shortlist,
            h_max_mm=h_max_f,
            cell_key=key,
        )


# --------------------------------------------------------------------------- #
# Laden (fail-soft) + die schmale Tuer
# --------------------------------------------------------------------------- #


def _priors_dir(priors_dir: Path | None) -> Path:
    if priors_dir is not None:
        return Path(priors_dir)
    from fgc import paths

    return paths.PRIORS_DIR


def load_prior_tables(
    robot_name: str, *, priors_dir: Path | None = None
) -> list[PriorTable]:
    """Laedt alle Prior-Tabellen fuer ``robot_name`` — **fail-soft** (US Fehlfaelle).

    Sucht ``placement_prior.<robot>.*.json`` im Prior-Verzeichnis. Fehlendes
    Verzeichnis ⇒ leere Liste. Ein **provenienz-ungueltiges** oder unlesbares
    Artefakt wird **uebersprungen** (nie ein stilles Fehlurteil — es zaehlt als
    „kein Artefakt" ⇒ neutraler Prior). Nach ``robot`` gefiltert wird zusaetzlich
    am geladenen Inhalt (Dateiname ist nur der Sucheinstieg).
    """
    directory = _priors_dir(priors_dir)
    if not directory.exists():
        return []
    tables: list[PriorTable] = []
    for path in sorted(directory.glob(f"placement_prior.{robot_name}.*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            table = PriorTable.from_artifact(artifact)
        except (ValueError, OSError, json.JSONDecodeError):
            continue  # provenienz-ungueltig/unlesbar ⇒ als abwesend behandeln
        if table.robot == robot_name:
            tables.append(table)
    return tables


def placement_prior(
    robot_name: str,
    tool: ToolDef,
    module_length_mm: float,
    module_thickness_mm: float,
    safety_distance_mm: float,
    *,
    module_height_mm: float | None = None,
    priors_dir: Path | None = None,
    tables: list[PriorTable] | None = None,
) -> PlacementPrior:
    """Die schmale Tuer: (Roboter, Tool, Modulmasse, Sicherheitszone) → ``PlacementPrior``.

    Jeder Fehlfall liefert ``NEUTRAL_PRIOR`` (Suche wie ohne Messwissen): kein
    Artefakt fuer den Roboter, kein aehnliches Tool, Modulmasse ausserhalb des
    Gitters, provenienz-ungueltiges Artefakt (beim Laden uebersprungen). Eine
    ``angenommen-unmachbar``-Zelle liefert einen neutral-breiten Prior **mit**
    Unmachbarkeits-Erwartung.

    ``tables`` erlaubt das direkte Einspeisen geladener Tabellen (isolierter Test —
    ohne Dateisystem); sonst wird ueber ``priors_dir`` (Default ``paths.PRIORS_DIR``)
    geladen.
    """
    if tables is None:
        tables = load_prior_tables(robot_name, priors_dir=priors_dir)
    if not tables:
        return _neutral("kein-artefakt-oder-fremder-roboter")
    matching = [t for t in tables if t.tool_matches(tool, safety_distance_mm)]
    if not matching:
        return _neutral("unbekanntes-tool")
    # Deterministisch: erste passende Tabelle (Dateiname-sortiert).
    return matching[0].query(
        module_length_mm, module_thickness_mm, height_mm=module_height_mm
    )

"""Py↔TS-Paritätsmanifest — die eine Registratur der geteilten Goldens (ADR-009, #195).

Der Paritätsbeweis „Core-Funktion ↔ TS-Zwilling" lebt von **geteilten
Golden-Dateien**: der Core erzeugt sie, beide Seiten rechnen ihre eigene
Ableitung dagegen (pytest ``core/tests/test_parity.py``, vitest über
``viewer/src/test/golden-parity.ts``). Vor #195 war das eine unerzwungene
6-Schritte-Konvention (je Zwilling ein eigenes Gen-Skript + handgeschriebene
Leseschleifen); dieses Modul macht sie zu einer schmalen Tür:

- :func:`register` trägt ein Paar ein (unten: die acht bestehenden Paare);
  :func:`golden_doc` beschreibt die Golden-Datei, in die es schreibt.
- :func:`generate` schreibt alle Golden-Dateien aus dem Manifest —
  Treiber: ``python viewer/scripts/gen_goldens.py [pair …]``.
- :func:`verify` prüft die Core-Hälfte eines Paares gegen sein Golden —
  parametrisiert über :data:`MANIFEST` in ``test_parity.py::test_golden``.
  Ein Manifest-Eintrag ohne Golden (Datei/Block fehlt oder leer) schlägt
  dort fehl; ein Golden ohne Manifest-Eintrag ebenso (Registratur-Test).

Heterogene Paare (Geometrie mit Toleranz, Konstanten-Blöcke) werden nicht in
das Standard-Skelett gezwungen: eigener ``case_builder``/``compare`` genügt.
Rezept für Zwilling N+1: ``docs/paritaet.md``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fgc.domain.orientation import nozzle_quat
from fgc.domain.process_params import resolve_section_params
from fgc.domain.robot import RobotDef
from fgc.kinematics.opw import OpwKinematics
from fgc.pipeline.actions import PRUEF_PER_REP_SECONDS
from fgc.project.revisions import (
    INPUT_KEYS,
    OUTPUT_DEPS,
    PRUEF_DEPS,
    SECTION_AGGREGATE_OUTPUTS,
    SECTION_OUTPUT_JOB_DEPS,
    output_status,
    pruef_status,
    section_output_status,
)

# =================================================================================
# Harness — Registratur, Gen-Treiber-Kern, Verifikation
# =================================================================================

#: Repo-Root, hergeleitet aus der Quelldatei (editable install); Aufrufer mit
#: eigener Bodenhaftung (pytest, gen_goldens.py) übergeben ``root`` explizit.
_REPO_ROOT = Path(__file__).resolve().parents[3]

_HINT = "python viewer/scripts/gen_goldens.py laufen lassen"

CompareFn = Callable[[Any, dict[str, Any], str], None]
CasesArg = Sequence[dict[str, Any]] | Callable[[], Sequence[dict[str, Any]]] | None


def _compare_expected(got: Any, case: dict[str, Any], label: str) -> None:
    """Default-Vergleich: die Core-Ableitung ist bit-gleich zu ``expected``."""
    assert got == case["expected"], label


@dataclass(frozen=True)
class GoldenDoc:
    """Eine geteilte Golden-Datei: Pfad (repo-relativ), Kopf, JSON-Format."""

    path: str
    comment: str
    header: Callable[[], dict[str, Any]] | None = None
    #: Historisches Format je Datei beibehalten (fk schreibt ``\\u2014``-Escapes).
    ensure_ascii: bool = False


@dataclass(frozen=True)
class ParityPair:
    """Ein registriertes Py↔TS-Paar: Core-Wahrheit + Golden-Block + Vergleich."""

    pair: str
    fn: Callable[[dict[str, Any] | None], Any]
    cases: CasesArg
    golden: str
    block: str
    compare: CompareFn
    case_builder: Callable[[dict[str, Any]], dict[str, Any]] | None
    doc_check: Callable[[dict[str, Any]], None] | None


_DOCS: dict[str, GoldenDoc] = {}

#: Registrierungs-Reihenfolge = Block-Reihenfolge in der Datei = pytest-Parameter.
MANIFEST: list[ParityPair] = []


def golden_doc(
    path: str,
    comment: str,
    header: Callable[[], dict[str, Any]] | None = None,
    ensure_ascii: bool = False,
) -> str:
    """Beschreibt eine Golden-Datei; gibt den Pfad zurück (für :func:`register`)."""
    _DOCS[path] = GoldenDoc(path=path, comment=comment, header=header, ensure_ascii=ensure_ascii)
    return path


def register(
    pair: str,
    fn: Callable[[dict[str, Any] | None], Any],
    cases: CasesArg,
    golden: str,
    compare: CompareFn = _compare_expected,
    case_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    block: str = "cases",
    doc_check: Callable[[dict[str, Any]], None] | None = None,
) -> ParityPair:
    """Trägt ein Py↔TS-Paar ins Manifest ein.

    - ``fn(case)`` ist die Core-Wahrheit: roher bzw. Golden-Fall → Ableitung.
    - ``cases`` sind die rohen Eingabefälle (oder ein Callable dafür, wenn der
      Aufbau Stammdaten lädt). ``cases=None`` registriert einen Konstanten-Block:
      der Block ist dann ``fn(None)`` selbst (deep-equal statt Fall-Schleife).
    - ``case_builder(case)`` baut den Golden-Fall; Default ist das Skelett
      ``{**case, "expected": fn(case)}``.
    - ``compare(got, case, label)`` ist die Vergleichs-Mechanik des pytest-Lesers;
      Default: bit-gleich zu ``case["expected"]``.
    - ``doc_check(doc)`` prüft optional Datei-Kopf-Invarianten (fk: DH-Abgleich).
    """
    if golden not in _DOCS:
        raise ValueError(f"{pair}: Golden-Datei {golden} ist nicht per golden_doc registriert")
    entry = ParityPair(
        pair=pair,
        fn=fn,
        cases=cases,
        golden=golden,
        block=block,
        compare=compare,
        case_builder=case_builder,
        doc_check=doc_check,
    )
    MANIFEST.append(entry)
    return entry


def _materialize_cases(entry: ParityPair) -> list[dict[str, Any]]:
    assert entry.cases is not None
    raw = entry.cases() if callable(entry.cases) else entry.cases
    return list(raw)


def _build_block(entry: ParityPair) -> Any:
    if entry.cases is None:
        return entry.fn(None)
    build = entry.case_builder or (lambda case: {**case, "expected": entry.fn(case)})
    return [build(case) for case in _materialize_cases(entry)]


def generate(
    root: Path | str | None = None,
    only: Sequence[str] | None = None,
) -> list[tuple[Path, list[str]]]:
    """Schreibt die Golden-Dateien des Manifests; gibt (Pfad, Block-Infos) zurück.

    ``only`` wählt Paar-Namen aus; geschrieben wird immer die ganze Datei, zu der
    ein gewähltes Paar gehört (geteilte Dateien bleiben so in sich konsistent).
    """
    base = Path(root) if root is not None else _REPO_ROOT
    if only:
        known = {entry.pair for entry in MANIFEST}
        unknown = sorted(set(only) - known)
        if unknown:
            raise ValueError(f"Unbekannte Paare {unknown} — bekannt: {sorted(known)}")
        selected = {entry.golden for entry in MANIFEST if entry.pair in set(only)}
    else:
        selected = set(_DOCS)

    written: list[tuple[Path, list[str]]] = []
    for path, spec in _DOCS.items():
        if path not in selected:
            continue
        doc: dict[str, Any] = {"_comment": spec.comment}
        if spec.header is not None:
            doc.update(spec.header())
        infos: list[str] = []
        for entry in MANIFEST:
            if entry.golden != path:
                continue
            content = _build_block(entry)
            doc[entry.block] = content
            n = f" ({len(content)} Fälle)" if isinstance(content, list) else ""
            infos.append(f"{entry.block}{n}")
        target = base / path
        text = json.dumps(doc, indent=2, ensure_ascii=spec.ensure_ascii) + "\n"
        target.write_text(text, encoding="utf-8")
        written.append((target, infos))
    return written


def verify(entry: ParityPair, root: Path | str | None = None) -> None:
    """Prüft die Core-Hälfte eines Paares gegen sein eingechecktes Golden.

    Schlägt fehl, wenn das Golden fehlt/leer ist oder die Core-Ableitung von den
    gespeicherten Fällen abweicht — genau die Sichtbarkeit, die die frühere
    Konvention nicht erzwingen konnte (#74/#175 entstanden ohne Golden).
    """
    base = Path(root) if root is not None else _REPO_ROOT
    path = base / entry.golden
    assert path.is_file(), f"{entry.pair}: Golden fehlt ({entry.golden}) — {_HINT}"
    doc = json.loads(path.read_text(encoding="utf-8"))
    block = doc.get(entry.block)
    assert block, f"{entry.pair}: Block '{entry.block}' fehlt/leer in {entry.golden} — {_HINT}"
    if entry.doc_check is not None:
        entry.doc_check(doc)

    if entry.cases is None:
        # Konstanten-Block: die Core-Konstanten sind bit-gleich zum Golden.
        entry.compare(entry.fn(None), {"expected": block}, entry.pair)
        return

    cases = _materialize_cases(entry)
    assert len(block) == len(cases), (
        f"{entry.pair}: {len(block)} Golden-Fälle vs. {len(cases)} Manifest-Fälle — {_HINT}"
    )
    manifest_names = [case.get("name") for case in cases]
    if all(name is not None for name in manifest_names):
        golden_names = [case.get("name") for case in block]
        assert golden_names == manifest_names, f"{entry.pair}: Fall-Namen driften — {_HINT}"
    for i, case in enumerate(block):
        label = f"{entry.pair}: {case.get('name', f'Fall {i}')}"
        entry.compare(entry.fn(case), case, label)


# =================================================================================
# Paar 1: fk — Präsentations-FK (viewer/src/kinematics/fk.ts) gegen den Core
# =================================================================================
# Der Core ist die Wahrheit: aus den DH-Parametern der Roboterdefinition rechnet
# ``OpwKinematics.link_frames`` die Gliedposen (Basis … Flansch). Der Viewer-Test
# (fk.test.ts) vergleicht seine eigene FK mit dokumentierter Toleranz dagegen;
# ein DH-Abgleich wacht darüber, dass ``robot.ts`` nicht von der Quelle abdriftet.

_FK_ROBOT = "doosan_m1013"

# Toleranzen wie fk.test.ts (Position: euklidischer Abstand in mm; Orientierung:
# max. vorzeichenangeglichene Quaternionen-Komponentendifferenz). Dieselbe
# analytische Standard-DH-Kette auf beiden Seiten — rein numerisch begrenzt.
_FK_POS_TOL_MM = 1e-6
_FK_QUAT_TOL = 1e-8

# Deterministische, aussagekräftige Gelenkkonfigurationen (Radiant):
# Home, Einzelachsen, gemischte Auslagen + reproduzierbar gestreute Stichproben.
_FK_HANDPICKED: list[list[float]] = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [math.pi / 2, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, math.pi / 4, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, math.pi / 3, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, math.pi / 2, 0.0],
    [0.2, -0.4, 0.7, 0.1, 0.8, -0.3],
    [-1.1, 0.55, -0.9, 1.4, -0.6, 2.2],
    [math.pi, -math.pi / 2, 1.0, -math.pi, 0.9, math.pi],
]


def _fk_seeded_samples(n: int, limits: list[tuple[float, float]]) -> list[list[float]]:
    """Reproduzierbare Stichproben innerhalb der Achsgrenzen (eigener LCG, kein numpy)."""
    state = 20260704
    out: list[list[float]] = []
    for _ in range(n):
        q: list[float] = []
        for lo, hi in limits:
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            u = state / 0x7FFFFFFF
            q.append(lo + u * (hi - lo))
        out.append(q)
    return out


@cache
def _fk_kin() -> OpwKinematics:
    return OpwKinematics.from_robot(_FK_ROBOT)


def _fk_cases() -> list[dict[str, Any]]:
    robot = RobotDef.load(_FK_ROBOT)
    assert robot.kinematics is not None, f"{_FK_ROBOT} trägt keine Kinematik"
    limits = [(lo, hi) for lo, hi in robot.kinematics.joint_limits_rad]
    return [{"joints_rad": q} for q in _FK_HANDPICKED + _fk_seeded_samples(12, limits)]


def _fk_replay(case: dict[str, Any] | None) -> list[dict[str, Any]]:
    assert case is not None
    frames = _fk_kin().link_frames(case["joints_rad"])
    return [{"pos_mm": list(f.pos_mm), "quat": list(f.quat)} for f in frames]


def _fk_case_builder(case: dict[str, Any]) -> dict[str, Any]:
    q = case["joints_rad"]
    frames = _fk_kin().link_frames(q)
    return {
        "joints_rad": [round(v, 12) for v in q],
        "links": [
            {
                "pos_mm": [round(v, 9) for v in f.pos_mm],
                "quat": [round(v, 12) for v in f.quat],
            }
            for f in frames
        ],
    }


def _quat_comp_diff(a: Sequence[float], b: Sequence[float]) -> float:
    """Max. Komponentendifferenz zweier Quaternionen nach Vorzeichenangleich."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    s = -1.0 if dot < 0 else 1.0  # q und -q sind dieselbe Rotation
    return max(abs(x - s * y) for x, y in zip(a, b, strict=True))


def _fk_compare(got: Any, case: dict[str, Any], label: str) -> None:
    links = case["links"]
    assert len(got) == len(links) == 7, label
    for i, (frame, link) in enumerate(zip(got, links, strict=True)):
        pos = math.dist(frame["pos_mm"], link["pos_mm"])
        assert pos < _FK_POS_TOL_MM, f"{label}: Position driftet an Glied {i} ({pos} mm)"
        quat = _quat_comp_diff(frame["quat"], link["quat"])
        assert quat < _FK_QUAT_TOL, f"{label}: Orientierung driftet an Glied {i} ({quat})"


def _fk_dh() -> dict[str, list[float]]:
    robot = RobotDef.load(_FK_ROBOT)
    assert robot.kinematics is not None, f"{_FK_ROBOT} trägt keine Kinematik"
    kin = robot.kinematics
    return {
        "a_mm": list(kin.a_mm),
        "d_mm": list(kin.d_mm),
        "alpha_rad": list(kin.alpha_rad),
    }


def _fk_header() -> dict[str, Any]:
    return {"robot": _FK_ROBOT, "dh": _fk_dh()}


def _fk_doc_check(doc: dict[str, Any]) -> None:
    """Die DH im Golden ist exakt die der Roboterdefinition (Driftschutz an der Quelle)."""
    assert doc["robot"] == _FK_ROBOT
    assert doc["dh"] == _fk_dh()


# =================================================================================
# Paare 2+3: nozzle-quat / nozzle-schablone — Düsen-Orientierung (Issue #85/#61)
# =================================================================================
# ``fgc.domain.orientation.nozzle_quat`` ist die eine geteilte Orientierungsquelle
# (Regressionsschutz #51); die TS-Zwillinge ``ui/nozzle-quat.ts`` und
# ``ui/nozzle-schablone.ts`` leiten ihre Posen aus genau dieser Funktion ab.

_NOZZLE_QUAT_CASES: list[dict[str, Any]] = [
    {
        "name": "0/0 -> senkrecht von oben (+x)",
        "tangent": [1.0, 0.0],
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(0.0),
    },
    {
        "name": "0/0 -> senkrecht von oben (+y)",
        "tangent": [0.0, 1.0],
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(0.0),
    },
    {
        "name": "degenerierte Tangente -> senkrecht",
        "tangent": [0.0, 0.0],
        "lead_rad": math.radians(20.0),
        "kipp_rad": math.radians(20.0),
    },
    {
        "name": "+kipp 30 zur Aussenseite (+x-Fahrt)",
        "tangent": [1.0, 0.0],
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(30.0),
    },
    {
        "name": "+lead 30 in Fahrtrichtung (+x-Fahrt)",
        "tangent": [1.0, 0.0],
        "lead_rad": math.radians(30.0),
        "kipp_rad": math.radians(0.0),
    },
    {
        "name": "+kipp 30 (+y-Fahrt) Aussenseite +x",
        "tangent": [0.0, 1.0],
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(30.0),
    },
    {
        "name": "lead+kipp gemischt, schiefe Tangente",
        "tangent": [2.0, -1.0],
        "lead_rad": math.radians(12.0),
        "kipp_rad": math.radians(7.0),
    },
    {
        "name": "negativer lead (Lag), -x-Fahrt",
        "tangent": [-1.0, 0.0],
        "lead_rad": math.radians(-15.0),
        "kipp_rad": math.radians(10.0),
    },
]


def _nozzle_quat_replay(case: dict[str, Any] | None) -> list[float]:
    assert case is not None
    return list(nozzle_quat(tuple(case["tangent"]), case["lead_rad"], case["kipp_rad"]))


# Die Bahntangente je Punkt (Vorwärtsdifferenz, letzter Punkt erbt den vorletzten)
# ist die Domäne des TS-Zwillings ``pathTangent`` in nozzle-schablone.ts. Der Core
# ist NICHT die Wahrheit für die Tangente, sondern nur für die Orientierung
# ``nozzle_quat(tangent, lead, kipp)`` — darum steht die Tangente als **Eingabe**
# je Pose im Golden: pytest prüft ``nozzle_quat(tangent) == quat`` (Core-Hälfte),
# der vitest ``pathTangent(path, i) == tangent`` (TS-Hälfte) — beide Halbschleifen zu.

_LINE = [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [200.0, 0.0, 0.0]]
_LINE_TAN = [[100.0, 0.0], [100.0, 0.0], [100.0, 0.0]]
_RING = [
    [-50.0, -12.0, 100.0],
    [50.0, -12.0, 100.0],
    [50.0, 12.0, 100.0],
    [-50.0, 12.0, 100.0],
    [-50.0, -12.0, 100.0],
]
_RING_TAN = [[100.0, 0.0], [0.0, 24.0], [-100.0, 0.0], [0.0, -24.0], [0.0, -24.0]]

_SCHABLONE_CASES: list[dict[str, Any]] = [
    {
        "name": "gerade +x-Bahn, senkrecht (0/0)",
        "path": _LINE,
        "tangents": _LINE_TAN,
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(0.0),
    },
    {
        "name": "gerade +x-Bahn, kipp 30",
        "path": _LINE,
        "tangents": _LINE_TAN,
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(30.0),
    },
    {
        "name": "gerade +x-Bahn, lead 20",
        "path": _LINE,
        "tangents": _LINE_TAN,
        "lead_rad": math.radians(20.0),
        "kipp_rad": math.radians(0.0),
    },
    {
        "name": "CCW-Ring, kipp 15 (Aussenseite folgt der Fahrt)",
        "path": _RING,
        "tangents": _RING_TAN,
        "lead_rad": math.radians(0.0),
        "kipp_rad": math.radians(15.0),
    },
    {
        "name": "CCW-Ring, lead 10 + kipp 8",
        "path": _RING,
        "tangents": _RING_TAN,
        "lead_rad": math.radians(10.0),
        "kipp_rad": math.radians(8.0),
    },
]


def _schablone_case_builder(case: dict[str, Any]) -> dict[str, Any]:
    lead, kipp = case["lead_rad"], case["kipp_rad"]
    poses = [
        {
            "pos_mm": p,
            "tangent": t,
            "quat": list(nozzle_quat((t[0], t[1]), lead, kipp)),
        }
        for p, t in zip(case["path"], case["tangents"], strict=True)
    ]
    return {
        "name": case["name"],
        "path": case["path"],
        "lead_rad": lead,
        "kipp_rad": kipp,
        "poses": poses,
    }


def _schablone_replay(case: dict[str, Any] | None) -> list[list[float]]:
    assert case is not None
    return [
        list(nozzle_quat(tuple(pose["tangent"]), case["lead_rad"], case["kipp_rad"]))
        for pose in case["poses"]
    ]


def _schablone_compare(got: Any, case: dict[str, Any], label: str) -> None:
    assert len(case["poses"]) == len(case["path"]), label
    for i, (quat, pose) in enumerate(zip(got, case["poses"], strict=True)):
        assert quat == pose["quat"], f"{label} / Pose {i}"


# =================================================================================
# Paar 4: section-params — Abschnitts-Auflösung (Issue #82)
# =================================================================================
# ``resolve_section_params`` löst „global + Abschnitts-Override → effektive
# Prozessparameter" auf; TS-Zwilling ``ui/section-params-state.ts``.
# Fälle: Erben, Übersteuern je Feld/Gruppe, io/Geschwindigkeit, 0-Werte, leere Ebenen.

_SECTION_PARAMS_CASES: list[dict[str, Any]] = [
    {
        "name": "leer + leer -> leer (Altprojekt, reine Karten-Defaults)",
        "global": {},
        "override": {},
    },
    {
        "name": "nur global gesetzt -> Abschnitt erbt alles",
        "global": {
            "slice": {"layer_height_mm": 8.0, "n_shells": 3},
            "orientation": {"kipp_deg": 5.0},
        },
        "override": {},
    },
    {
        "name": "nur Abschnitt gesetzt -> Abschnitt gewinnt (kein globaler Wert)",
        "global": {},
        "override": {"slice": {"layer_height_mm": 6.0}, "orientation": {"lead_deg": 12.0}},
    },
    {
        "name": "Feld-Mischung: layer erbt global, strand kommt vom Abschnitt",
        "global": {"slice": {"layer_height_mm": 8.0, "strand_width_mm": 30.0}},
        "override": {"slice": {"strand_width_mm": 22.0}},
    },
    {
        "name": "Orientierung: kipp uebersteuert, lead erbt global",
        "global": {"orientation": {"lead_deg": 10.0, "kipp_deg": 5.0}},
        "override": {"orientation": {"kipp_deg": -8.0}},
    },
    {
        "name": "Fortgeschritten (Geschwindigkeit/io) uebersteuerbar, io_travel=0 gesetzt",
        "global": {
            "slice": {
                "v_print_mm_s": 100.0,
                "v_travel_mm_s": 250.0,
                "io_print": 0.5,
                "io_travel": 0.5,
            }
        },
        "override": {"slice": {"v_print_mm_s": 60.0, "io_travel": 0.0}},
    },
    {
        "name": "alle Felder in beiden Gruppen, Abschnitt gewinnt durchweg",
        "global": {
            "slice": {"layer_height_mm": 10.0, "strand_width_mm": 30.0, "n_shells": 2},
            "orientation": {"lead_deg": 0.0, "kipp_deg": 0.0},
        },
        "override": {
            "slice": {"layer_height_mm": 7.5, "strand_width_mm": 20.0, "n_shells": 4},
            "orientation": {"lead_deg": 15.0, "kipp_deg": 20.0},
        },
    },
    {
        "name": "None im Override uebersteuert nicht (erbt global)",
        "global": {"slice": {"layer_height_mm": 8.0}},
        "override": {"slice": {"layer_height_mm": None, "n_shells": 3}},
    },
    {
        "name": "leere Override-Gruppe -> erbt global, keine leere Gruppe im Ergebnis",
        "global": {"slice": {"n_shells": 2}},
        "override": {"slice": {}, "orientation": {}},
    },
    {
        "name": "ik_config: Ellbogen uebersteuert (b), Schulter erbt global (a) — Issue #129",
        "global": {"ik_config": {"shoulder": "a", "elbow": "a"}},
        "override": {"ik_config": {"elbow": "b"}},
    },
    {
        "name": "ik_config: nur Abschnitt gesetzt (Handgelenk b), sonst auto",
        "global": {},
        "override": {"ik_config": {"wrist": "b"}},
    },
    {
        "name": "alle drei Gruppen gemischt (slice/orientation/ik_config)",
        "global": {
            "slice": {"layer_height_mm": 8.0},
            "orientation": {"kipp_deg": 5.0},
            "ik_config": {"shoulder": "a", "wrist": "a"},
        },
        "override": {
            "slice": {"n_shells": 4},
            "ik_config": {"wrist": "b"},
        },
    },
]


def _section_params_replay(case: dict[str, Any] | None) -> dict[str, Any]:
    assert case is not None
    return resolve_section_params(case["global"], case["override"])


# =================================================================================
# Paar 5: staleness-section — Pro-Abschnitts-Veraltung (Issue #83, ADR-017-Nachtrag)
# =================================================================================
# ``section_output_status`` leitet je Abschnitt ab, ob Simulation/Export veraltet
# sind; TS-Zwilling ``sectionStageStatus`` in ``ui/staleness.ts``. Jeder Fall trägt
# die rohen ``revisions`` (oder None = Altprojekt) und die abgefragte ``section_id``.

_STALENESS_SECTION_CASES: list[dict[str, Any]] = [
    {
        "name": "Altprojekt ohne revisions -> alles current",
        "revisions": None,
        "section_id": "abschnitt-1",
    },
    {
        "name": "Legacy (kein section_outputs) -> Ganzjob: Sim/Export erzeugt = current",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
        "section_id": "abschnitt-1",
    },
    {
        "name": "Legacy: Roboterwechsel veraltet Ganzjob-Sim/Export (verhält sich wie bisher)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 2, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
        "section_id": "abschnitt-1",
    },
    {
        "name": "Pro-Abschnitt: A simuliert, B nie -> A current, Abfrage B = missing",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-2",
    },
    {
        "name": "Abschnitts-Override von A: nur A veraltet (Zähler A=1 > Snapshot 0)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {"abschnitt-1": 1},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
                "abschnitt-2": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-1",
    },
    {
        "name": "Derselbe Stand, Nachbar B: bleibt aktuell (Zähler B unverändert)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {"abschnitt-1": 1},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
                "abschnitt-2": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-2",
    },
    {
        "name": "Globaler process-Bump: beide Abschnitte veralten (strukturell/global)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 1, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {},
            "section_outputs": {
                "abschnitt-2": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-2",
    },
    {
        "name": "Workstation-Wechsel: Abschnitt veraltet (workstation ist Job-Dep, #83)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 1,
            },
            "outputs": {},
            "section_inputs": {},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-1",
    },
    {
        "name": "Schnitt-Änderung (cutplan) veraltet Abschnitts-Sim/Export",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 2, "process": 0, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                    "export": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 0,
                    },
                },
            },
        },
        "section_id": "abschnitt-1",
    },
    {
        "name": (
            "Override von A gebumpt + A neu simuliert: A wieder current "
            "(section-Snapshot zieht mit)"
        ),
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {},
            "section_inputs": {"abschnitt-1": 1},
            "section_outputs": {
                "abschnitt-1": {
                    "simulation": {
                        "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                        "process": 0, "workstation": 0, "section": 1,
                    },
                },
            },
        },
        "section_id": "abschnitt-1",
    },
]


def _job(revisions: dict | None, last_pruef: dict | None = None) -> dict:
    """Baut den minimalen Druckjob, den die Revisions-Ableitungen lesen."""
    job: dict = {"job_id": "default", "wall_global_id": "W1"}
    if revisions is not None:
        job["revisions"] = revisions
    if last_pruef is not None:
        job["last_pruef"] = last_pruef
    return job


def _staleness_section_replay(case: dict[str, Any] | None) -> dict[str, str]:
    assert case is not None
    return section_output_status(_job(case["revisions"]), case["section_id"])


# =================================================================================
# Paare 6–8: staleness-constants / -output / -pruef — Ganzjob-/Prüf-Familie (#194)
# =================================================================================
# Drei Blöcke in EINEM geteilten Golden (staleness.golden.json): ``constants``
# (die sechs Kommentar-Syncpunkte als Fakt — pytest wie vitest deep-equalen sie
# gegen ihre je eigenen Konstanten), ``output_cases`` (``output_status`` ↔
# ``ui/staleness.ts``, inkl. section_total-Kante #172) und ``pruef_cases``
# (``pruef_status`` ↔ ``ui/pruef-check-state.ts``, inkl. der
# last_pruef-ohne-Snapshot-Kante, deren Semantik #194 auf „missing" vereinheitlichte).


def _staleness_constants(_case: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "INPUT_KEYS": list(INPUT_KEYS),
        "OUTPUT_DEPS": {k: list(v) for k, v in OUTPUT_DEPS.items()},
        "SECTION_OUTPUT_JOB_DEPS": {k: list(v) for k, v in SECTION_OUTPUT_JOB_DEPS.items()},
        "SECTION_AGGREGATE_OUTPUTS": list(SECTION_AGGREGATE_OUTPUTS),
        "PRUEF_DEPS": list(PRUEF_DEPS),
        "PER_REP_SECONDS": int(PRUEF_PER_REP_SECONDS),
    }


_STALENESS_OUTPUT_CASES: list[dict[str, Any]] = [
    {"name": "Altprojekt ohne revisions -> alles current", "revisions": None},
    {
        "name": "kein Output-Schnappschuss -> missing",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {},
        },
    },
    {
        "name": "Roboterwechsel -> Druckplan/Simulation/Export veraltet",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 2, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "druckplan": {"wall": 1, "robot": 1, "tool": 0, "process": 0, "workstation": 0},
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
    },
    {
        "name": "Druckplan neu erzeugt -> nur er wieder current (stufenweise)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 2, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "druckplan": {"wall": 1, "robot": 2, "tool": 0, "process": 0, "workstation": 0},
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
    },
    {
        "name": "Schnittplan-Aenderung veraltet Simulation/Export, NICHT den Druckplan",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 2, "process": 0, "workstation": 0,
            },
            "outputs": {
                "druckplan": {"wall": 1, "robot": 1, "tool": 0, "process": 0, "workstation": 0},
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
    },
    {
        "name": "Prozessparameter-Aenderung veraltet alle drei",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 1, "workstation": 0,
            },
            "outputs": {
                "druckplan": {"wall": 1, "robot": 1, "tool": 0, "process": 0, "workstation": 0},
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
    },
    {
        "name": "Workstation-Wechsel veraltet alle drei (#83)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 1,
            },
            "outputs": {
                "druckplan": {"wall": 1, "robot": 1, "tool": 0, "process": 0, "workstation": 0},
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
        },
    },
    {
        "name": "section_total-Kante: Abschnitts-Override veraltet NUR den Druckplan (#172)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "druckplan": {
                    "wall": 1, "robot": 1, "tool": 0, "process": 0,
                    "workstation": 0, "section_total": 0,
                },
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
            "section_inputs": {"abschnitt-1": 1, "abschnitt-2": 1},
        },
    },
    {
        "name": "section_total-Kante: Druckplan neu erzeugt (Summe im Snapshot) -> current",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 1, "tool": 0, "cutplan": 1, "process": 0, "workstation": 0,
            },
            "outputs": {
                "druckplan": {
                    "wall": 1, "robot": 1, "tool": 0, "process": 0,
                    "workstation": 0, "section_total": 2,
                },
                "simulation": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
                "export": {
                    "wall": 1, "robot": 1, "tool": 0, "cutplan": 1,
                    "process": 0, "workstation": 0,
                },
            },
            "section_inputs": {"abschnitt-1": 1, "abschnitt-2": 1},
        },
    },
]


def _staleness_output_replay(case: dict[str, Any] | None) -> dict[str, str]:
    assert case is not None
    return output_status(_job(case["revisions"]))


_STALENESS_PRUEF_CASES: list[dict[str, Any]] = [
    {
        "name": "kein last_pruef -> missing (nie geprueft)",
        "revisions": {"inputs": {"cutplan": 2}},
        "last_pruef": None,
    },
    {
        "name": "last_pruef OHNE input_snapshot -> missing (#194: keine stille Aktualitaet)",
        "revisions": {
            "inputs": {
                "wall": 0, "robot": 0, "tool": 0, "cutplan": 0, "process": 0, "workstation": 0,
            },
        },
        "last_pruef": {"scope": "global"},
    },
    {
        "name": "last_pruef OHNE input_snapshot trotz gebumpter Eingabe -> missing (#194)",
        "revisions": {
            "inputs": {
                "wall": 1, "robot": 0, "tool": 0, "cutplan": 0, "process": 0, "workstation": 0,
            },
        },
        "last_pruef": {"scope": "global"},
    },
    {
        "name": "last_pruef mit LEEREM input_snapshot -> missing (#194)",
        "revisions": {
            "inputs": {
                "wall": 0, "robot": 0, "tool": 0, "cutplan": 0, "process": 0, "workstation": 0,
            },
        },
        "last_pruef": {"scope": "global", "input_snapshot": {}},
    },
    {
        "name": "unveraenderte Eingaben -> current",
        "revisions": {"inputs": {"wall": 1, "cutplan": 3, "process": 2}},
        "last_pruef": {
            "scope": "global",
            "input_snapshot": {"wall": 1, "cutplan": 3, "process": 2, "section_total": 0},
        },
    },
    {
        "name": "eine Pruef-Eingabe neuer als der Schnappschuss -> stale",
        "revisions": {"inputs": {"cutplan": 4, "process": 2}},
        "last_pruef": {"scope": "global", "input_snapshot": {"cutplan": 3, "process": 2}},
    },
    {
        "name": "Workstation-Wechsel seit der Pruefung -> stale",
        "revisions": {"inputs": {"cutplan": 3, "workstation": 1}},
        "last_pruef": {"scope": "global", "input_snapshot": {"cutplan": 3, "workstation": 0}},
    },
    {
        "name": "Platzierungs-/Abschnitts-Override (section_total steigt) -> stale",
        "revisions": {
            "inputs": {"cutplan": 3},
            "section_inputs": {"abschnitt-1": 1, "abschnitt-2": 1},
        },
        "last_pruef": {
            "scope": "focus",
            "section_id": "abschnitt-1",
            "input_snapshot": {"cutplan": 3, "section_total": 1},
        },
    },
]


def _staleness_pruef_replay(case: dict[str, Any] | None) -> str:
    assert case is not None
    return pruef_status(_job(case["revisions"], case["last_pruef"]))


# =================================================================================
# Registrierung — 8 Paare über 6 Golden-Dateien
# =================================================================================

_FK_GOLDEN = golden_doc(
    "viewer/src/kinematics/fk.golden.json",
    "Golden FK oracle — erzeugt von viewer/scripts/gen_goldens.py; "
    "nicht von Hand editieren.",
    header=_fk_header,
    ensure_ascii=True,
)
_NOZZLE_QUAT_GOLDEN = golden_doc(
    "viewer/src/ui/nozzle-quat.golden.json",
    "Golden-Faelle nozzle_quat (Issue #85/#61) — erzeugt von "
    "viewer/scripts/gen_goldens.py; nicht von Hand editieren.",
)
_NOZZLE_SCHABLONE_GOLDEN = golden_doc(
    "viewer/src/ui/nozzle-schablone.golden.json",
    "Golden-Posen Duesen-Schablone (Issue #85) — Quaternion je Bahnpunkt aus Core "
    "nozzle_quat; erzeugt von viewer/scripts/gen_goldens.py; nicht von Hand editieren.",
)
_SECTION_PARAMS_GOLDEN = golden_doc(
    "viewer/src/ui/section-params.golden.json",
    "Golden-Faelle der Abschnitts-Aufloesung (Issue #82) — erzeugt von "
    "viewer/scripts/gen_goldens.py; nicht von Hand editieren.",
)
_STALENESS_SECTION_GOLDEN = golden_doc(
    "viewer/src/ui/staleness-section.golden.json",
    "Golden-Faelle der Pro-Abschnitts-Veraltung (Issue #83) — erzeugt von "
    "viewer/scripts/gen_goldens.py; nicht von Hand editieren.",
)
_STALENESS_GOLDEN = golden_doc(
    "viewer/src/ui/staleness.golden.json",
    "Golden-Faelle Ganzjob-/Pruef-Veraltung (Issue #194) — erzeugt von "
    "viewer/scripts/gen_goldens.py; nicht von Hand editieren.",
)

register(
    "fk",
    fn=_fk_replay,
    cases=_fk_cases,
    golden=_FK_GOLDEN,
    compare=_fk_compare,
    case_builder=_fk_case_builder,
    doc_check=_fk_doc_check,
)
register(
    "nozzle-quat",
    fn=_nozzle_quat_replay,
    cases=_NOZZLE_QUAT_CASES,
    golden=_NOZZLE_QUAT_GOLDEN,
)
register(
    "nozzle-schablone",
    fn=_schablone_replay,
    cases=_SCHABLONE_CASES,
    golden=_NOZZLE_SCHABLONE_GOLDEN,
    compare=_schablone_compare,
    case_builder=_schablone_case_builder,
)
register(
    "section-params",
    fn=_section_params_replay,
    cases=_SECTION_PARAMS_CASES,
    golden=_SECTION_PARAMS_GOLDEN,
)
register(
    "staleness-section",
    fn=_staleness_section_replay,
    cases=_STALENESS_SECTION_CASES,
    golden=_STALENESS_SECTION_GOLDEN,
)
register(
    "staleness-constants",
    fn=_staleness_constants,
    cases=None,
    golden=_STALENESS_GOLDEN,
    block="constants",
)
register(
    "staleness-output",
    fn=_staleness_output_replay,
    cases=_STALENESS_OUTPUT_CASES,
    golden=_STALENESS_GOLDEN,
    block="output_cases",
)
register(
    "staleness-pruef",
    fn=_staleness_pruef_replay,
    cases=_STALENESS_PRUEF_CASES,
    golden=_STALENESS_GOLDEN,
    block="pruef_cases",
)

"""fgc.decompose.surrogat — der **Surrogat-Vorsortierer** der Beam-Suche (Issue #219, PRD #183).

Ein kleines, deterministisches **Gradient-Boosting-Modell** (kein Deep Learning)
ueber den #211-Kandidaten-Merkmalen, das die Beam-Kandidatenliste **vorsortiert** —
die vermutlich kollisionsfreien Kandidaten zuerst durch die (teure) Pruef-Tuer.

**Ehrlichkeitsregel (ADR-007/#164, Grill 2026-07-14):** das Surrogat ist in v1
**ausschliesslich Vorsortierer**. Es **sortiert, verwirft nie** und taucht in
**keiner Ampel und keinem Befund** auf (kein neues Vokabular). Die Auswahl des
Siegers bleibt die **Zielfunktion** (#212): die Beam-Suche gibt bei gleichem
Aufruf-Kontingent denselben besten Kandidaten und dasselbe Urteil zurueck — nur
die **Reihenfolge** der Pruef-Tuer-Aufrufe (und damit die Zeit) aendert sich
(Invarianz-Orakel US 25). Die einzige Spur des Surrogats ist der **Modellstand
in der Lauf-Provenienz** (:meth:`SurrogatModell.stamp`), falls aktiv (ADR-004).

**Training (deterministisch, US 25):** fester Seed ⇒ **bit-gleiches Modell**. Das
Boosting hat keine Zufallsquelle (kein Subsampling; exakte, gierige Splits mit
stabilen Tie-Breaks) — der Seed pinnt die (heute leere) stochastische Flaeche und
wandert in die Provenienz. Trainiert wird **ausschliesslich aus v1-policy-
konformen Labels** (:func:`policy_filter`): ``cpu-exakt`` + ``gpu+cpu-grenzband``
(mit bestandenem #205-G1-Gate — diese Label-Quelle wird nur bei bestandenem Gate
vergeben); ``gpu+stichproben-audit`` wird **verweigert** (nicht trainingstauglich).

**Artefakt (US 26):** das Modell ist ein versioniertes Artefakt mit Provenienz
(Datensatz-Stand, Seed, Merkmalsliste, Merkmals-Version #211). Das **Laden
validiert** die Provenienz (:meth:`SurrogatModell.from_artifact`): eine falsche
Merkmals-Version/-Liste schlaegt fehl. Ein Altlauf ohne Surrogat-Modell laedt
unveraendert (:func:`load_surrogat` liefert ``None`` — der Beam faellt byte-gleich
auf die reine Zielfunktions-Ordnung zurueck, US 12).

Einheiten strikt nach ADR-006: Millimeter.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from fgc.decompose.kampagne import TRAINING_LABEL_SOURCES
from fgc.decompose.pruefung import FEATURE_SCHEMA_VERSION

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fgc.decompose.kandidaten import BandRasterKandidat
    from fgc.decompose.scorer import KandidatBewertung

__all__ = [
    "SURROGATE_MODEL_KIND",
    "SURROGATE_SCHEMA_VERSION",
    "SURROGATE_FEATURES",
    "GradientBoosting",
    "SurrogatModell",
    "load_surrogat",
    "policy_filter",
    "save_surrogat",
    "train_surrogat",
]

#: Artefakt-Kennung + Schema-Version des Modell-Artefakts (US 26, ADR-004).
SURROGATE_MODEL_KIND = "surrogate-model"
SURROGATE_SCHEMA_VERSION = "1"

#: Die **Merkmalsliste** des Surrogats (feste Reihenfolge, Teil der Provenienz).
#: Bewusst der **Kandidaten-Kern** aus :meth:`fgc.decompose.kampagne.CampaignCandidate.feature_core`
#: (rein aus Plan-Geometrie ableitbar, **ohne Roboter/Platzierung**) — genau die
#: Merkmale, die zur **Vorsortier-Zeit** je Kandidat vorliegen (die Platzierungs-/
#: Podest-Merkmale entstehen erst in der Platzierungssuche je Reihe, stehen also
#: beim Sortieren der Kandidatenliste noch nicht bereit). Das Surrogat ist ein
#: Vorsortierer, kein Gate: eine Merkmals-Teilmenge kostet nur Sortier-Guete
#: (Benchmark #220), nie Korrektheit. Deckungsgleich mit dem #211-Feld-Satz —
#: :data:`FEATURE_SCHEMA_VERSION` versioniert die Bedeutung.
SURROGATE_FEATURES: tuple[str, ...] = (
    "order",
    "x0_mm",
    "x1_mm",
    "z0_mm",
    "z1_mm",
    "length_mm",
    "height_mm",
    "center_x_mm",
    "wall_length_mm",
    "wall_height_mm",
    "wall_thickness_mm",
    "n_earlier_parts",
)

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Deterministisches Gradient-Boosting (Standard-Lernmodell, kein Deep Learning)
# --------------------------------------------------------------------------- #


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _leaf_value(g: np.ndarray, h: np.ndarray, reg_lambda: float) -> float:
    """Der Newton-Blattwert (TreeBoost): ``sum(gradient) / (sum(hessian) + lambda)``."""
    return float(g.sum() / (h.sum() + reg_lambda))


def _best_split(
    x_matrix: np.ndarray, g: np.ndarray, min_samples_leaf: int
) -> tuple[int, float] | None:
    """Der **gierige, deterministische** beste Split (kleinste Rest-Quadratsumme auf ``g``).

    Maximiert ``Sl²/nl + Sr²/nr`` (aequivalent zur SSE-Minimierung der Pseudo-
    Residuen). Tie-Breaks streng deterministisch: erstes Merkmal (Index-Reihenfolge),
    dann kleinste Schwelle (``argmax`` liefert die erste Fundstelle). ``None``, wenn
    kein zulaessiger Split die wurzelnahe Quadratsumme verbessert.
    """
    n, n_features = x_matrix.shape
    if n < 2 * min_samples_leaf:
        return None
    total = float(g.sum())
    baseline = total * total / n  # der Wert ohne Split
    best_gain = baseline + _EPS
    best: tuple[int, float] | None = None
    for f in range(n_features):
        col = x_matrix[:, f]
        order = np.argsort(col, kind="stable")
        cs = col[order]
        gs = g[order]
        csum = np.cumsum(gs)
        nl = np.arange(1, n)
        s_l = csum[:-1]
        n_r = n - nl
        s_r = total - s_l
        gains = (s_l * s_l) / nl + (s_r * s_r) / n_r
        valid = (cs[:-1] != cs[1:]) & (nl >= min_samples_leaf) & (n_r >= min_samples_leaf)
        gains = np.where(valid, gains, -np.inf)
        i = int(np.argmax(gains))  # erste Fundstelle bei Gleichstand (deterministisch)
        gain = float(gains[i])
        if gain > best_gain:  # strikt: Gleichstand behaelt das fruehere Merkmal
            best_gain = gain
            best = (f, float((cs[i] + cs[i + 1]) / 2.0))
    return best


def _build_tree(
    x_matrix: np.ndarray,
    g: np.ndarray,
    h: np.ndarray,
    depth: int,
    *,
    max_depth: int,
    min_samples_leaf: int,
    reg_lambda: float,
) -> dict[str, Any]:
    """Baut einen Regressions-Baum auf den Pseudo-Residuen ``g`` (Newton-Blaetter)."""
    if depth >= max_depth or len(g) < 2 * min_samples_leaf:
        return {"v": _leaf_value(g, h, reg_lambda)}
    split = _best_split(x_matrix, g, min_samples_leaf)
    if split is None:
        return {"v": _leaf_value(g, h, reg_lambda)}
    f, thr = split
    mask = x_matrix[:, f] <= thr
    if bool(mask.all()) or not bool(mask.any()):
        return {"v": _leaf_value(g, h, reg_lambda)}
    left = _build_tree(
        x_matrix[mask], g[mask], h[mask], depth + 1,
        max_depth=max_depth, min_samples_leaf=min_samples_leaf, reg_lambda=reg_lambda,
    )
    right = _build_tree(
        x_matrix[~mask], g[~mask], h[~mask], depth + 1,
        max_depth=max_depth, min_samples_leaf=min_samples_leaf, reg_lambda=reg_lambda,
    )
    return {"f": int(f), "t": float(thr), "l": left, "r": right}


def _predict_tree(node: dict[str, Any], x_matrix: np.ndarray) -> np.ndarray:
    """Baum-Vorhersage je Zeile (iterative Traversierung, deterministisch)."""
    out = np.empty(len(x_matrix), dtype=float)
    for i in range(len(x_matrix)):
        cur = node
        row = x_matrix[i]
        while "v" not in cur:
            cur = cur["l"] if row[cur["f"]] <= cur["t"] else cur["r"]
        out[i] = cur["v"]
    return out


@dataclass
class GradientBoosting:
    """Ein kleines, **deterministisches** Gradient-Boosting fuer die binaere
    Kollisions-Wahrscheinlichkeit (logistischer Verlust, Newton-Blaetter).

    Kein Deep Learning, keine Zufallsquelle: fester Seed ⇒ bit-gleiches Modell
    (US 25). ``base`` ist der Log-Odds-Startwert, ``trees`` die Boosting-Runden,
    ``learning_rate`` die Schrittweite. Vorhersage: ``sigmoid(base + lr·Σ Baum)``.
    """

    base: float
    learning_rate: float
    trees: list[dict[str, Any]]

    @classmethod
    def fit(
        cls,
        x_matrix: np.ndarray,
        y: np.ndarray,
        *,
        n_estimators: int,
        learning_rate: float,
        max_depth: int,
        min_samples_leaf: int,
        reg_lambda: float,
    ) -> GradientBoosting:
        x_matrix = np.asarray(x_matrix, dtype=float)
        y = np.asarray(y, dtype=float)
        p0 = float(np.clip(y.mean(), _EPS, 1.0 - _EPS))
        base = math.log(p0 / (1.0 - p0))
        scores = np.full(len(y), base, dtype=float)
        trees: list[dict[str, Any]] = []
        for _m in range(n_estimators):
            p = _sigmoid(scores)
            g = y - p  # negativer Gradient des Logloss
            h = np.clip(p * (1.0 - p), _EPS, None)  # Hessian
            tree = _build_tree(
                x_matrix, g, h, 0,
                max_depth=max_depth, min_samples_leaf=min_samples_leaf, reg_lambda=reg_lambda,
            )
            trees.append(tree)
            scores = scores + learning_rate * _predict_tree(tree, x_matrix)
        return cls(base=base, learning_rate=float(learning_rate), trees=trees)

    def decision(self, x_matrix: np.ndarray) -> np.ndarray:
        x_matrix = np.asarray(x_matrix, dtype=float)
        scores = np.full(len(x_matrix), self.base, dtype=float)
        for tree in self.trees:
            scores = scores + self.learning_rate * _predict_tree(tree, x_matrix)
        return scores

    def predict_proba(self, x_matrix: np.ndarray) -> np.ndarray:
        """Kollisions-Wahrscheinlichkeit je Zeile (1 = vermutlich kollidiert)."""
        return _sigmoid(self.decision(x_matrix))

    def to_dict(self) -> dict[str, Any]:
        return {"base": self.base, "learning_rate": self.learning_rate, "trees": self.trees}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GradientBoosting:
        return cls(
            base=float(data["base"]),
            learning_rate=float(data["learning_rate"]),
            trees=list(data["trees"]),
        )


# --------------------------------------------------------------------------- #
# Policy-Filter (nur v1-policy-konforme Labels, Grill 2026-07-14)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PolicyFilterErgebnis:
    """Der Ausweis des Policy-Filters: was trainiert wird, was **verweigert** wurde."""

    used: list[dict[str, Any]]
    n_total: int
    n_non_training: int
    n_bad_verdict: int
    label_source_distribution_used: dict[str, int]


def policy_filter(samples: list[dict[str, Any]]) -> PolicyFilterErgebnis:
    """Behaelt **nur v1-policy-konforme** Trainingszeilen (Grill 2026-07-14, US 24).

    Trainingstauglich sind ausschliesslich die Label-Quellen in
    :data:`fgc.decompose.kampagne.TRAINING_LABEL_SOURCES` (``cpu-exakt`` +
    ``gpu+cpu-grenzband`` — letztere wird nur bei **bestandenem #205-G1-Gate**
    vergeben). ``gpu+stichproben-audit`` wird **verweigert** (nur explorativ). Eine
    Zeile ohne **entscheidendes** Urteil (``verdict.collides`` kein ``bool`` — z. B.
    ``error``/``ungeprueft``/``no_geometry``, #170) traegt kein Trainingslabel und
    faellt ebenfalls heraus.
    """
    used: list[dict[str, Any]] = []
    dist: dict[str, int] = {}
    n_non_training = 0
    n_bad_verdict = 0
    for s in samples:
        source = s.get("label_source")
        if source not in TRAINING_LABEL_SOURCES:
            n_non_training += 1
            continue
        collides = (s.get("verdict") or {}).get("collides")
        if not isinstance(collides, bool):
            n_bad_verdict += 1
            continue
        used.append(s)
        dist[source] = dist.get(source, 0) + 1
    return PolicyFilterErgebnis(
        used=used,
        n_total=len(samples),
        n_non_training=n_non_training,
        n_bad_verdict=n_bad_verdict,
        label_source_distribution_used=dist,
    )


def _vectorize(features: dict[str, Any]) -> list[float]:
    """Merkmals-Dict → Vektor in fester :data:`SURROGATE_FEATURES`-Reihenfolge."""
    return [float(features.get(name, 0.0) or 0.0) for name in SURROGATE_FEATURES]


# --------------------------------------------------------------------------- #
# Das Surrogat-Modell: Vorsortierer + versioniertes Artefakt
# --------------------------------------------------------------------------- #


@dataclass
class SurrogatModell:
    """Das trainierte Surrogat: **Vorsortierer** der Beam-Kandidatenliste + Artefakt (US 24/26).

    ``gb`` ist das deterministische Gradient-Boosting; die uebrigen Felder sind die
    **Provenienz** (Datensatz-Stand, Seed, Merkmalsliste/-Version, Hyperparameter,
    Trainings-Ausweis). :meth:`vorsortiere` reordnet die Kandidatenliste (vermutlich
    frei zuerst) — **ohne** je einen Kandidaten zu verwerfen; :meth:`stamp` liefert
    den Modellstand fuer die Lauf-Provenienz (ADR-004).
    """

    gb: GradientBoosting
    seed: int
    hyperparams: dict[str, Any]
    provenance: dict[str, Any]
    dataset: dict[str, Any]
    training: dict[str, Any]
    feature_version: str = FEATURE_SCHEMA_VERSION
    features: tuple[str, ...] = SURROGATE_FEATURES

    # -- Vorsortierung (der eigentliche Einbau, #217) --------------------------

    def _candidate_collision_proba(self, kandidat: BandRasterKandidat) -> float:
        """Kollisions-Risiko eines Kandidaten = **Maximum** ueber seine Hoehenreihen.

        Ein Kandidat ist nur kollisionsfrei, wenn **jede** Reihe frei ist — die
        riskanteste Reihe dominiert. Die Reihen-Merkmale sind genau der
        #211-Kandidaten-Kern (:meth:`CampaignCandidate.feature_core`), deckungsgleich
        mit den Trainingsmerkmalen.
        """
        from fgc.decompose.kampagne import CampaignCandidate

        rows = [
            _vectorize(CampaignCandidate(kandidat.wall, kandidat, r).feature_core())
            for r in range(kandidat.n_height)
        ]
        if not rows:
            return 0.0
        return float(self.gb.predict_proba(np.asarray(rows, dtype=float)).max())

    def vorsortiere(self, bewertungen: Sequence[KandidatBewertung]) -> list[KandidatBewertung]:
        """Reordnet die (zielfunktions-geordnete) Kandidatenliste — **vermutlich frei zuerst**.

        Rein die **Pruef-Reihenfolge**: aufsteigend nach vorhergesagtem Kollisions-
        Risiko, stabiler Tie-Break = die eingehende (Zielfunktions-)Reihenfolge.
        **Verwirft nie** (Laenge bleibt gleich); die Sieger-Auswahl bleibt die
        Zielfunktion — daher ist das Beam-Ergebnis invariant (US 25).
        """
        indexed = list(enumerate(bewertungen))
        scored = [
            (self._candidate_collision_proba(b.kandidat), i, b) for i, b in indexed
        ]
        scored.sort(key=lambda t: (t[0], t[1]))
        return [b for _p, _i, b in scored]

    # -- Provenienz / Artefakt (US 26) -----------------------------------------

    def stamp(self) -> dict[str, Any]:
        """Der **Modellstand** fuer die Lauf-Provenienz (ADR-004) — falls aktiv (#219)."""
        return {
            "schema_version": SURROGATE_SCHEMA_VERSION,
            "feature_version": self.feature_version,
            "features": list(self.features),
            "seed": self.seed,
            "hyperparams": dict(self.hyperparams),
            "n_trees": len(self.gb.trees),
            "dataset": dict(self.dataset),
        }

    def to_artifact(self) -> dict[str, Any]:
        """Das versionierte Modell-Artefakt mit Provenienz (US 26)."""
        return {
            "kind": SURROGATE_MODEL_KIND,
            "schema_version": SURROGATE_SCHEMA_VERSION,
            "feature_version": self.feature_version,
            "features": list(self.features),
            "seed": self.seed,
            "hyperparams": dict(self.hyperparams),
            "provenance": self.provenance,
            "dataset": self.dataset,
            "training": self.training,
            "model": self.gb.to_dict(),
        }

    @classmethod
    def from_artifact(cls, artifact: dict[str, Any]) -> SurrogatModell:
        """Laedt ein Modell und **validiert die Provenienz** (US 26).

        Schlaegt fehl bei falscher Artefakt-Kennung, falscher Schema-Version, einer
        **fremden Merkmals-Version** (:data:`FEATURE_SCHEMA_VERSION` #211 — die
        Merkmale wurden umdefiniert) oder einer **abweichenden Merkmalsliste**: ein
        Modell ueber falschen Merkmalen darf nie stillschweigend sortieren.
        """
        kind = artifact.get("kind")
        if kind != SURROGATE_MODEL_KIND:
            raise ValueError(
                f"Kein Surrogat-Modell-Artefakt (kind={kind!r}, erwartet {SURROGATE_MODEL_KIND!r})."
            )
        schema = artifact.get("schema_version")
        if schema != SURROGATE_SCHEMA_VERSION:
            raise ValueError(
                f"Surrogat-Schema {schema!r} != erwartet {SURROGATE_SCHEMA_VERSION!r} "
                "(Modell-Artefakt aus einer anderen Code-Generation)."
            )
        fv = artifact.get("feature_version")
        if fv != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"Merkmals-Version {fv!r} != aktuell {FEATURE_SCHEMA_VERSION!r} (#211) — "
                "das Modell wurde ueber anders definierten Merkmalen trainiert (US 26)."
            )
        feats = tuple(artifact.get("features") or ())
        if feats != SURROGATE_FEATURES:
            raise ValueError(
                "Merkmalsliste des Modells weicht ab — erwartet "
                f"{list(SURROGATE_FEATURES)}, ist {list(feats)}."
            )
        return cls(
            gb=GradientBoosting.from_dict(artifact["model"]),
            seed=int(artifact.get("seed", 0)),
            hyperparams=dict(artifact.get("hyperparams") or {}),
            provenance=dict(artifact.get("provenance") or {}),
            dataset=dict(artifact.get("dataset") or {}),
            training=dict(artifact.get("training") or {}),
            feature_version=str(fv),
            features=feats,
        )


# --------------------------------------------------------------------------- #
# Training + Laden/Speichern
# --------------------------------------------------------------------------- #


def train_surrogat(
    dataset: dict[str, Any],
    *,
    source: str,
    provenance: dict[str, Any] | None = None,
    seed: int = 0,
    n_estimators: int = 60,
    learning_rate: float = 0.1,
    max_depth: int = 3,
    min_samples_leaf: int = 1,
    reg_lambda: float = 1.0,
) -> SurrogatModell:
    """Trainiert das Surrogat **deterministisch** aus einem Datensatz-Artefakt (#218 → #219).

    Validiert die Merkmals-Version des Datensatzes gegen :data:`FEATURE_SCHEMA_VERSION`
    (#211), filtert die Trainingszeilen ueber :func:`policy_filter` (nur ``cpu-exakt``
    + ``gpu+cpu-grenzband``/#205-G1; ``gpu+stichproben-audit`` verweigert) und lernt
    ein kleines Gradient-Boosting ueber :data:`SURROGATE_FEATURES` → ``verdict.collides``.
    **Fester Seed ⇒ bit-gleiches Modell** (kein Zufall im Boosting). Das Ergebnis ist
    ein versioniertes Modell mit Provenienz (Datensatz-Stand, Seed, Merkmalsliste).

    Wirft ``ValueError`` bei fremder Merkmals-Version oder wenn nach dem Policy-Filter
    keine Trainingszeile bleibt (ein leeres Modell waere ein stiller Fehlkomparator).
    """
    dataset_fv = dataset.get("feature_version")
    if dataset_fv != FEATURE_SCHEMA_VERSION:
        raise ValueError(
            f"Datensatz-Merkmals-Version {dataset_fv!r} != aktuell {FEATURE_SCHEMA_VERSION!r} "
            "(#211) — der Datensatz passt nicht zum aktuellen Merkmals-Schema."
        )
    filtered = policy_filter(list(dataset.get("samples") or []))
    if not filtered.used:
        raise ValueError(
            "Keine v1-policy-konforme Trainingszeile im Datensatz "
            f"(gesamt={filtered.n_total}, nicht-trainingstauglich={filtered.n_non_training}, "
            f"ohne entscheidendes Urteil={filtered.n_bad_verdict}) — "
            "Training verweigert (Grill 2026-07-14)."
        )

    x_matrix = np.asarray([_vectorize(s["features"]) for s in filtered.used], dtype=float)
    y = np.asarray([1.0 if s["verdict"]["collides"] else 0.0 for s in filtered.used], dtype=float)

    hyperparams = {
        "n_estimators": int(n_estimators),
        "learning_rate": float(learning_rate),
        "max_depth": int(max_depth),
        "min_samples_leaf": int(min_samples_leaf),
        "reg_lambda": float(reg_lambda),
    }
    gb = GradientBoosting.fit(
        x_matrix, y,
        n_estimators=int(n_estimators), learning_rate=float(learning_rate),
        max_depth=int(max_depth), min_samples_leaf=int(min_samples_leaf),
        reg_lambda=float(reg_lambda),
    )

    ds_prov = dataset.get("provenance") or {}
    dataset_stand = {
        "source": ds_prov.get("source"),
        "created": ds_prov.get("created"),
        "git_commit": ds_prov.get("git_commit"),
        "feature_version": dataset_fv,
        "n_candidates_planned": dataset.get("n_candidates_planned"),
        "n_samples": dataset.get("n_samples"),
        "partial": dataset.get("partial"),
    }
    training = {
        "n_total": filtered.n_total,
        "n_used": len(filtered.used),
        "n_rejected_non_training": filtered.n_non_training,
        "n_rejected_bad_verdict": filtered.n_bad_verdict,
        "label_source_distribution_used": filtered.label_source_distribution_used,
        "positive_rate": float(y.mean()),
    }
    if provenance is None:
        from fgc.pipeline.provenance import make_provenance

        provenance = make_provenance(source)

    return SurrogatModell(
        gb=gb,
        seed=int(seed),
        hyperparams=hyperparams,
        provenance=provenance,
        dataset=dataset_stand,
        training=training,
    )


def save_surrogat(model: SurrogatModell, path: Path) -> Path:
    """Schreibt das Modell-Artefakt (deterministisch, ``sort_keys`` fuer den Byte-Vergleich)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            model.to_artifact(),
            indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path


def load_surrogat(path: Path | None) -> SurrogatModell | None:
    """Laedt ein Modell-Artefakt — **fail-soft** (US 12) bei Abwesenheit, streng bei Fehlprovenienz.

    ``None``/nicht vorhanden ⇒ ``None`` (der Beam laeuft byte-gleich ohne
    Vorsortierer — ein Altlauf ohne Surrogat-Modell laedt unveraendert). Ein
    **vorhandenes**, aber provenienz-falsches Artefakt schlaegt fehl
    (:meth:`SurrogatModell.from_artifact`, US 26) — nie ein stiller Fehlkomparator.
    """
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    artifact = json.loads(path.read_text(encoding="utf-8"))
    return SurrogatModell.from_artifact(artifact)

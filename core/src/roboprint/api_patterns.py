"""API des Mustererstellers: 2D-Vorschau, Katalog und benannte Presets (Druckmuster, ohne Roboter).

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/patterns` | Kernregler, alle Muster mit Reglern (ParamSpecs) und alle Presets |
| POST | `/api/patterns/preview` | Vorschau einer Schicht (JSON); `?format=svg` liefert die SVG-Draufsicht |
| GET | `/api/patterns/preview.svg` | SVG-Export über Query (`pattern`, `preset`, `params` als JSON, …) |
| GET | `/api/patterns/presets` | alle Presets (mitgeliefert und eigene) |
| GET | `/api/patterns/presets/{id}` | ein Preset |
| POST | `/api/patterns/presets` | eigenes Preset speichern (überschreibt eine eigene Vorlage gleicher id) |

Die Geometrie rechnet `roboprint.patterns` (SPEC §9: Der Viewer rechnet keine Fachlogik).
Mitgelieferte Presets liegen in `roboprint/patterns/presets/` und sind schreibgeschützt; eigene
Presets liegen in `presets_dir` (Standard `<runs>/presets`), je Preset eine Datei `<id>.json`.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .contracts.api import (
    PatternCatalog,
    PatternInfo,
    PatternParamSpec,
    PatternPreset,
    PatternPresetCreate,
    PatternPresetEntry,
    PatternPreview,
    PatternPreviewRequest,
)

PRESET_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: Schlüssel, an denen ein `FitResult.to_dict()` in `meta` erkannt wird
FIT_KEYS = frozenset({"count", "length_mm", "total_mm", "target_mm", "positions_mm"})
SVG_MEDIA = "image/svg+xml"


def builtin_presets_dir() -> Path:
    from roboprint import patterns

    return Path(patterns.__file__).parent / "presets"


def slugify(name: str) -> str:
    """Preset-id aus einem Anzeigenamen: ASCII, Kleinbuchstaben, `-` statt Leerraum, ≤ 64 Zeichen."""
    trans = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
    s = unicodedata.normalize("NFKD", name.translate(trans)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-_").lower()[:64].strip("-_")
    return s or "muster"


def _err(status: int, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


class PresetStore:
    """Mitgelieferte (nur lesen) und eigene Presets (lesen und schreiben) nach id."""

    def __init__(self, user_dir: Path, builtin_dir: Path | None = None) -> None:
        self.user_dir = Path(user_dir)
        self.builtin_dir = Path(builtin_dir) if builtin_dir is not None else builtin_presets_dir()

    def _files(self, base: Path) -> list[Path]:
        return sorted(base.glob("*.json")) if base.is_dir() else []

    def _entry(self, path: Path, source: Literal["builtin", "user"]) -> PatternPresetEntry:
        from roboprint.patterns import load_preset

        data = load_preset(path)
        return PatternPresetEntry(id=path.stem, source=source, preset=PatternPreset.model_validate(data))

    def list(self) -> list[PatternPresetEntry]:
        """Alle lesbaren Presets: mitgelieferte zuerst, dann eigene; defekte Dateien werden übergangen."""
        out: list[PatternPresetEntry] = []
        builtin_ids = set()
        for source, base in (("builtin", self.builtin_dir), ("user", self.user_dir)):
            for p in self._files(base):
                if not PRESET_ID.match(p.stem) or (source == "user" and p.stem in builtin_ids):
                    continue
                try:
                    out.append(self._entry(p, source))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001 - ein defektes Preset darf den Katalog nie blockieren
                    continue
                if source == "builtin":
                    builtin_ids.add(p.stem)
        return out

    def get(self, preset_id: str) -> PatternPresetEntry:
        """Preset nach id; KeyError, wenn es fehlt, ValueError, wenn die Datei ungültig ist."""
        if not PRESET_ID.match(preset_id):
            raise KeyError(preset_id)
        for source, base in (("builtin", self.builtin_dir), ("user", self.user_dir)):
            p = base / f"{preset_id}.json"
            if p.is_file():
                return self._entry(p, source)  # type: ignore[arg-type]
        raise KeyError(preset_id)

    def save(self, body: PatternPresetCreate) -> PatternPresetEntry:
        """Eigenes Preset schreiben (über `patterns.save_preset`, das Muster und Parameter prüft).
        ValueError bei ungültigem Muster/Parameter, PermissionError bei einer mitgelieferten id."""
        from roboprint.patterns import save_preset

        pid = body.id or slugify(body.name)
        if (self.builtin_dir / f"{pid}.json").is_file():
            raise PermissionError(f"Preset {pid!r} ist mitgeliefert und lässt sich nicht überschreiben")
        self.user_dir.mkdir(parents=True, exist_ok=True)
        final = self.user_dir / f"{pid}.json"
        tmp = self.user_dir / f".{pid}.json.tmp"
        outline = None if body.outline is None else body.outline.model_dump()
        try:
            save_preset(tmp, body.name, body.pattern, dict(body.params), outline, body.description)
            tmp.replace(final)
        finally:
            tmp.unlink(missing_ok=True)
        return self._entry(final, "user")


def is_pattern_name(name: str) -> bool:
    from roboprint.patterns import names
    from roboprint.patterns.preview import BASE_NAMES

    return name in BASE_NAMES or name in names()


def build_spec(req: PatternPreviewRequest, store: PresetStore) -> tuple[dict[str, Any], Any]:
    """Preset-Dict für `patterns.preview` und Querschnitt aus der Anfrage.

    Reihenfolge: Preset (`preset` oder ein `pattern`, das kein Mustername ist) als Grundlage,
    darüber `pattern`, `params` und `outline` der Anfrage. KeyError: Preset fehlt."""
    base: dict[str, Any] = {}
    pattern = req.pattern
    preset_id = req.preset
    if pattern is not None and not is_pattern_name(pattern):
        if preset_id is not None:
            raise ValueError(f"Unbekanntes Muster {pattern!r}")
        preset_id, pattern = pattern, None
    if preset_id is not None:
        base = store.get(preset_id).preset.model_dump(exclude_none=True)
    spec = {
        "name": base.get("name"),
        "pattern": pattern or base.get("pattern") or "schalen",
        "params": {**dict(base.get("params") or {}), **dict(req.params)},
    }
    outline = req.outline.model_dump() if req.outline is not None else base.get("outline")
    return spec, outline


def fit_results(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`fit_to_length`-Ergebnisse aus `meta` der Pfade (direkt, in Listen oder eine Ebene tiefer)."""
    out: list[dict[str, Any]] = []

    def add(island: int, key: str, v: Any) -> None:
        if isinstance(v, dict) and FIT_KEYS <= set(v):
            out.append(
                {
                    "island": island,
                    "key": key,
                    "count": int(v["count"]),
                    "length_mm": float(v["length_mm"]),
                    "total_mm": float(v["total_mm"]),
                    "target_mm": float(v["target_mm"]),
                    "deviation_mm": float(v.get("deviation_mm", v["length_mm"] - v["target_mm"])),
                    "positions_mm": [float(x) for x in v["positions_mm"]],
                }
            )

    for lp in paths:
        for k, v in (lp.get("meta") or {}).items():
            add(lp["island"], k, v)
            if isinstance(v, list):
                for i, item in enumerate(v):
                    add(lp["island"], f"{k}[{i}]", item)
            elif isinstance(v, dict) and not FIT_KEYS <= set(v):
                for k2, v2 in v.items():
                    add(lp["island"], f"{k}.{k2}", v2)
    return out


def run_preview(req: PatternPreviewRequest, store: PresetStore) -> dict[str, Any]:
    """Vorschau als Dict im Format von `PatternPreview` (ValueError/KeyError bei falscher Eingabe)."""
    from roboprint.patterns import preview

    t0 = time.perf_counter()
    spec, outline = build_spec(req, store)
    data = preview(spec, outline, req.layer)
    data["fit"] = fit_results(data["paths"])
    data["timing_ms"]["api"] = round((time.perf_counter() - t0) * 1e3, 1)
    return data


def catalog(store: PresetStore) -> PatternCatalog:
    from roboprint.patterns import CORE_PARAM_SPECS
    from roboprint.patterns import catalog as pattern_catalog
    from roboprint.patterns.preview import BASE_NAMES

    return PatternCatalog(
        core_params=[PatternParamSpec.model_validate(p.to_dict()) for p in CORE_PARAM_SPECS],
        base_patterns=list(BASE_NAMES),
        patterns=[PatternInfo.model_validate(p) for p in pattern_catalog()],
        presets=store.list(),
    )


def make_router(store: PresetStore) -> APIRouter:
    router = APIRouter()

    def preview_or_422(req: PatternPreviewRequest) -> dict[str, Any]:
        try:
            return run_preview(req, store)
        except KeyError as exc:
            raise _err(404, f"Muster oder Preset nicht gefunden: {exc.args[0] if exc.args else exc}") from exc
        except (ValueError, TypeError) as exc:
            raise _err(422, f"Ungültige Musterparameter: {exc}") from exc

    def svg_response(data: dict[str, Any], width_px: int) -> Response:
        from roboprint.patterns import preview_svg

        return Response(preview_svg(data=data, width_px=width_px), media_type=SVG_MEDIA)

    @router.get("/api/patterns")
    def get_catalog() -> PatternCatalog:
        return catalog(store)

    @router.post(
        "/api/patterns/preview",
        response_model=PatternPreview,
        responses={200: {"content": {SVG_MEDIA: {}}}},
    )
    def post_preview(
        body: PatternPreviewRequest,
        format: Literal["json", "svg"] = "json",
        width_px: int = Query(1000, ge=200, le=4000),
    ) -> Response:
        data = preview_or_422(body)
        if format == "svg":
            return svg_response(data, width_px)
        # Direkt serialisiert (spart ~15 ms Validierung je Anfrage beim Ziehen der Regler); dass die
        # Ausgabe `PatternPreview` erfüllt, prüft test_api_patterns für jedes registrierte Muster.
        text = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return Response(text, media_type="application/json")

    @router.get("/api/patterns/preview.svg")
    def get_preview_svg(
        pattern: str | None = None,
        preset: str | None = None,
        params: str | None = Query(None, description="Parameter als JSON-Objekt"),
        length_mm: float | None = Query(None, gt=0),
        thickness_mm: float | None = Query(None, gt=0),
        layer: int = Query(0, ge=0),
        width_px: int = Query(1000, ge=200, le=4000),
    ) -> Response:
        try:
            pdict = json.loads(params) if params else {}
            if not isinstance(pdict, dict):
                raise ValueError("params muss ein JSON-Objekt sein")
            outline = None
            if length_mm is not None or thickness_mm is not None:
                if length_mm is None or thickness_mm is None:
                    raise ValueError("length_mm und thickness_mm nur zusammen")
                outline = {"length_mm": length_mm, "thickness_mm": thickness_mm}
            req = PatternPreviewRequest.model_validate(
                {"pattern": pattern, "preset": preset, "params": pdict, "outline": outline, "layer": layer}
            )
        except ValueError as exc:  # json.JSONDecodeError und pydantic.ValidationError sind ValueErrors
            raise _err(422, f"Ungültige Anfrage: {exc}") from exc
        return svg_response(preview_or_422(req), width_px)

    @router.get("/api/patterns/presets")
    def list_presets() -> list[PatternPresetEntry]:
        return store.list()

    @router.get("/api/patterns/presets/{preset_id}")
    def get_preset(preset_id: str) -> PatternPresetEntry:
        try:
            return store.get(preset_id)
        except KeyError as exc:
            raise _err(404, "Preset nicht gefunden") from exc
        except ValueError as exc:
            raise _err(422, f"Preset ungültig: {exc}") from exc

    @router.post("/api/patterns/presets", status_code=201)
    def save_preset(body: PatternPresetCreate) -> PatternPresetEntry:
        try:
            return store.save(body)
        except PermissionError as exc:
            raise _err(409, str(exc)) from exc
        except KeyError as exc:
            raise _err(422, f"Unbekanntes Muster: {exc.args[0] if exc.args else exc}") from exc
        except ValueError as exc:
            raise _err(422, f"Ungültiges Preset: {exc}") from exc

    return router

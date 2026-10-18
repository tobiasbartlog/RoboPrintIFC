"""FastAPI: Projekte, Jobs mit Fortschritt und Abbruch, Artefakte ausliefern (SPEC §8)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI


def create_app(runs_dir: Path = Path("runs")) -> FastAPI:
    """Baut die FastAPI-Anwendung; weitere Endpunkte folgen in A3.1."""
    from roboprint import __version__

    app = FastAPI(title="RoboPrintIFC", version=__version__)
    app.state.runs_dir = runs_dir

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app

@echo off
rem Doppelklick-Start ohne Wizard: Core-API + Viewer hochfahren und die
rem Projektliste im Browser oeffnen (ADR-016). Wand-Auswahl passiert dann per
rem Klick im Viewer (Issue #10, ADR-014).
rem
rem Selbstheilend: stellt vor dem Start sicher, dass .venv + Viewer-Deps zur
rem aktuellen pyproject/package-lock passen (bootstrap.ps1) - so startet ein
rem frisch gepulltes Repo ohne Handgriff.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" -Quiet
if errorlevel 1 (
    echo.
    echo [start] Einrichtung fehlgeschlagen - bitte .\setup.cmd ausfuehren und Ausgabe pruefen.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m fgc.pipeline.viewer_launch
if errorlevel 1 pause

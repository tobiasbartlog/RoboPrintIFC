@echo off
rem Einmalige (und nach jedem git pull wiederholbare) Einrichtung: .venv + Viewer-Deps.
rem Doppelklick im Explorer oder `.\setup.cmd` im Repo-Root. Idempotent - schneller
rem No-Op, wenn nichts driftete. Bricht mit Pause ab, damit Fehler lesbar bleiben.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" %*
if errorlevel 1 (
    echo.
    echo [setup] Einrichtung fehlgeschlagen - Meldung oben pruefen.
    pause
    exit /b 1
)
echo.
pause

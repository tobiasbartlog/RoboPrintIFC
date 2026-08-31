@echo off
rem fgc-Wrapper: nutzt die .venv des Repos, ohne dass sie aktiviert sein muss.
rem   .\fgc start          -^> interaktiver Wizard
rem   .\fgc walls list ... -^> wie fgc in aktivierter venv
rem
rem Selbstheilend: fehlt die .venv oder driftete sie von pyproject weg, richtet
rem bootstrap.ps1 sie zunaechst ein (idempotent, schneller No-Op wenn aktuell).
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%.venv\Scripts\fgc.exe" goto :bootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap.ps1" -Quiet
if errorlevel 1 goto :setupfail
goto :run

:bootstrap
echo [fgc] Keine (vollstaendige) .venv gefunden - richte ein ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap.ps1"
if errorlevel 1 goto :setupfail

:run
"%ROOT%.venv\Scripts\fgc.exe" %*
exit /b %errorlevel%

:setupfail
echo [fgc] Einrichtung fehlgeschlagen - bitte .\setup.cmd ausfuehren und Ausgabe pruefen.
exit /b 1

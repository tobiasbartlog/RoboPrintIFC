@echo off
rem Startet RoboPrintIFC (API + Web-Viewer) und oeffnet den Browser. Fenster schliessen oder Ctrl-C beendet alles.
cd /d "%~dp0"
start "" /b powershell -NoProfile -Command "Start-Sleep 6; Start-Process 'http://localhost:5173'"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1"
pause

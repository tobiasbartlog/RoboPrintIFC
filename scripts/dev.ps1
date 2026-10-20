# Entwicklung unter Windows: startet API (127.0.0.1:8765) und Web-Dev-Server (Vite, Proxy /api -> API).
# Ctrl-C beendet beide. Gegenstueck zu scripts/dev.sh.
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }
$env:PYTHONPATH = (Join-Path $Root 'core\src') + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { '' })

$api = Start-Process -FilePath $Py -ArgumentList '-m', 'roboprint', 'serve', '--runs', "`"$(Join-Path $Root 'runs')`"" `
    -WorkingDirectory $Root -NoNewWindow -PassThru
try {
    npm --prefix (Join-Path $Root 'web') run dev
} finally {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}

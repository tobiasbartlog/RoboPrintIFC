<#
.SYNOPSIS
    Idempotente Provisionierung des Repos: .venv (Python-Deps) + viewer/node_modules (Node-Deps).

.DESCRIPTION
    Einzige Wahrheitsquelle fuer "was muss installiert sein, damit das Tool laeuft".
    Nach jedem `git pull` erneut ausfuehrbar; synchronisiert die Umgebungen gegen
    core/pyproject.toml bzw. viewer/package-lock.json und ist ein schneller No-Op,
    wenn nichts driftete.

    Drift-Erkennung ueber Hash-Marker (kein teures Re-Install bei jedem Start):
      - .venv\.deps-hash                <- Hash von core/pyproject.toml
      - viewer\node_modules\.deps-hash  <- Hash von viewer/package-lock.json

    Die Start-Skripte (start_viewer.cmd, fgc.cmd) rufen dieses Skript im Leisemodus
    auf, sodass ein frisch gepulltes Repo ohne Handgriff sauber startet.

.PARAMETER Force
    Ignoriert die Hash-Marker und installiert alles neu.

.PARAMETER Quiet
    Nur bei tatsaechlicher Arbeit oder Fehlern ausgeben (fuer die Start-Skripte).
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$Root      = Split-Path -Parent $PSScriptRoot
$VenvDir   = Join-Path $Root '.venv'
$VenvPy    = Join-Path $VenvDir 'Scripts\python.exe'
$Pyproject = Join-Path $Root 'core\pyproject.toml'
$ViewerDir = Join-Path $Root 'viewer'
$Lockfile  = Join-Path $ViewerDir 'package-lock.json'

function Info($msg) { if (-not $Quiet) { Write-Host "[setup] $msg" } }
function Step($msg) { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[setup] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[setup] FEHLER: $msg" -ForegroundColor Red; exit 1 }

function Get-FileHashHex($path) {
    if (-not (Test-Path $path)) { return '' }
    return (Get-FileHash -Algorithm SHA256 -Path $path).Hash
}

# --- Python-Interpreter finden (>=3.12), ohne eine bestimmte Minor zu erzwingen ---
# Diese Maschine hat evtl. nur 3.14 und kein "py -3.12" -> wir nehmen, was da ist.
function Find-Python {
    $probe = "import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)"
    $candidates = @(
        @('py',      @('-3.12')),
        @('py',      @('-3.13')),
        @('py',      @('-3.14')),
        @('py',      @('-3')),
        @('python',  @()),
        @('python3', @())
    )
    foreach ($c in $candidates) {
        $exe = $c[0]
        $pre = $c[1]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        # Probe bewusst mit ErrorActionPreference='Continue': In PowerShell 5.1
        # verpackt eine Umleitung von nativem stderr jede Zeile in einen
        # ErrorRecord (NativeCommandError) -- unter 'Stop' wuerde schon das
        # erwartete "No suitable Python runtime found" eines fehlenden
        # "py -3.12" das ganze Skript abbrechen, statt den naechsten
        # Kandidaten zu probieren.
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & $exe @pre -c $probe 2>&1 | Out-Null } catch { } finally { $ErrorActionPreference = $prev }
        if ($LASTEXITCODE -eq 0) {
            return ,@($exe, $pre)
        }
    }
    return $null
}

# --- 1) Python-venv + Deps ---------------------------------------------------
$pyHashFile = Join-Path $VenvDir '.deps-hash'
$wantPyHash = Get-FileHashHex $Pyproject
$havePyHash = if (Test-Path $pyHashFile) { (Get-Content $pyHashFile -Raw).Trim() } else { '' }

$venvOk = Test-Path $VenvPy
$pyInSync = $venvOk -and (-not $Force) -and ($wantPyHash -ne '') -and ($wantPyHash -eq $havePyHash)

if ($pyInSync) {
    Info ".venv aktuell (pyproject unveraendert)."
} else {
    if (-not $venvOk) {
        $py = Find-Python
        if ($null -eq $py) {
            Fail "Kein Python >=3.12 gefunden. Bitte Python 3.12+ installieren (python.org) und erneut ausfuehren."
        }
        Step "Lege .venv an ..."
        & $py[0] @($py[1]) -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { Fail "venv-Anlage fehlgeschlagen." }
    }
    Step "Synchronisiere Python-Abhaengigkeiten (pip install -e core[dev,geo]) ..."
    & $VenvPy -m pip install --upgrade pip --quiet
    & $VenvPy -m pip install -e "$Root\core[dev,geo]"
    if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen - Ausgabe oben pruefen." }
    Set-Content -Path $pyHashFile -Value $wantPyHash -Encoding ASCII
    Step ".venv bereit."
}

# --- 2) Node/Viewer-Deps -----------------------------------------------------
if ($null -eq (Get-Command npm -ErrorAction SilentlyContinue)) {
    Warn "npm/Node.js nicht gefunden - der Viewer braucht Node.js (nodejs.org)."
    Warn "Python-Seite ist bereit; Viewer erst nach Node-Installation + erneutem setup."
} else {
    $nodeModules = Join-Path $ViewerDir 'node_modules'
    $npmHashFile = Join-Path $nodeModules '.deps-hash'
    $wantNpmHash = Get-FileHashHex $Lockfile
    $haveNpmHash = if (Test-Path $npmHashFile) { (Get-Content $npmHashFile -Raw).Trim() } else { '' }

    $npmOk = Test-Path $nodeModules
    $npmInSync = $npmOk -and (-not $Force) -and ($wantNpmHash -ne '') -and ($wantNpmHash -eq $haveNpmHash)

    if ($npmInSync) {
        Info "viewer/node_modules aktuell (package-lock unveraendert)."
    } else {
        Push-Location $ViewerDir
        try {
            if (Test-Path $Lockfile) {
                Step "Synchronisiere Node-Abhaengigkeiten (npm ci) ..."
                & npm.cmd ci
                if ($LASTEXITCODE -ne 0) {
                    Warn "npm ci fehlgeschlagen - versuche npm install ..."
                    & npm.cmd install
                }
            } else {
                Step "Synchronisiere Node-Abhaengigkeiten (npm install) ..."
                & npm.cmd install
            }
            if ($LASTEXITCODE -ne 0) { Fail "npm-Installation fehlgeschlagen - Ausgabe oben pruefen." }
            Set-Content -Path (Join-Path $nodeModules '.deps-hash') -Value $wantNpmHash -Encoding ASCII
            Step "viewer/node_modules bereit."
        } finally {
            Pop-Location
        }
    }
}

if (-not $Quiet) { Step "Fertig. Start mit: .\start_viewer.cmd  oder  .\fgc start" }
exit 0

<#
.SYNOPSIS
  Set up batam-poc on Windows (Python only — no admin required).

.DESCRIPTION
  Creates a virtualenv and installs dependencies for both parts:
    - plc-simulator/  (the test PLC server)
    - middleware/     (the client middleware + dashboard, installed with [dev] extras)
  Prints next-step run commands. Requires Python 3.9+ on PATH (see setup-windows.bat to install
  it via winget).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# --- locate Python -----------------------------------------------------------
Write-Step "Locating Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) {
    throw "Python not found on PATH. Install Python 3.9+ (winget install Python.Python.3.12) or run setup-windows.bat."
}
Write-Host ("    " + (& $py.Source --version))

function Setup-Venv($dir, $installArgs) {
    $path = Join-Path $repoRoot $dir
    if (-not (Test-Path $path)) { throw "Directory not found: $path" }
    Write-Step "Setting up venv in $dir"
    Push-Location $path
    try {
        & $py.Source -m venv .venv
        $venvPy = Join-Path $path ".venv\Scripts\python.exe"
        & $venvPy -m pip install --quiet --upgrade pip
        & $venvPy -m pip install --quiet @installArgs
        Write-Host "    $dir ready." -ForegroundColor Green
    }
    finally { Pop-Location }
}

Setup-Venv "plc-simulator" @("-r", "requirements.txt")
Setup-Venv "middleware"    @("-e", ".[dev]")

Write-Step "Setup complete. Next steps:"
Write-Host @"

  Terminal 1 — simulator (the test PLC):
    cd "$(Join-Path $repoRoot 'plc-simulator')"
    .\.venv\Scripts\python.exe plc_sim.py --mode known

  Terminal 2 — middleware + dashboard (http://127.0.0.1:8000):
    cd "$(Join-Path $repoRoot 'middleware')"
    .\.venv\Scripts\python.exe -m driftwatch --mode scan

  Real PLC over TCP:   ... -m driftwatch --mode scan --host <PLC_IP> --port 502 --unit 1
  Real PLC over RTU:   ... -m driftwatch --mode scan --transport rtu --rtu-port COM5 --baud 9600
  Enable writes:       add --allow-writes   (DANGER: reaches real hardware)
  Run tests:           cd middleware; .\.venv\Scripts\python.exe -m pytest

"@ -ForegroundColor Gray

Write-Host "Done." -ForegroundColor Green

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
}
$env:EDGE_RUNTIME_MODE="machine"
$env:RUN_GCODE_TARGET="machine"
$env:RUN_PERMISSION_GATE="1"
$env:ALLOW_SIMULATION_RUN="0"
$env:RUNTIME_HEARTBEAT_S="3"
.\.venv\Scripts\python.exe -m edge_backend.main

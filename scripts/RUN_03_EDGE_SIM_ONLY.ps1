$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
}
$env:RUN_GCODE_TARGET="simulation"
$env:ALLOW_SIMULATION_RUN="1"
$env:RUN_PERMISSION_GATE="0"
$env:SIM_GCODE_LINE_PERIOD_S="0.030"
.\.venv\Scripts\python.exe -m edge_backend.main_sim_only

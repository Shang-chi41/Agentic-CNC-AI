$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($args.Count -lt 1) {
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts\RUN_41_MISSION_04_PLAN_GCODE_FILE.ps1 path\to\file.nc"
    exit 2
}
$gcode = $args[0]
if (!(Test-Path $gcode)) {
    Write-Host "G-code file not found: $gcode"
    exit 2
}
if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
& $py tools\grbl_fluidnc_planner.py $gcode --out-dir reports\mission4_planner
exit $LASTEXITCODE

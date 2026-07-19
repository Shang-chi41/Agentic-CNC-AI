$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($args.Count -lt 1) {
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts\RUN_22_MISSION_02_REDUCE_REAL_CSV.ps1 <real_frames.csv>"
    exit 2
}
$realCsv = $args[0]
if (!(Test-Path $realCsv)) {
    Write-Host "CSV not found: $realCsv"
    exit 2
}
if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path ".\reports\mission2_real_reduced" | Out-Null
& $py "tools\mission2_position_benchmark.py" --real-csv $realCsv --out-dir "reports\mission2_real_reduced"
exit $LASTEXITCODE

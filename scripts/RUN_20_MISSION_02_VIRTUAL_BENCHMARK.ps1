$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path ".\reports\mission2_benchmark" | Out-Null

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "===== Mission 02 virtual position benchmark ====="
& $py "tools\mission2_position_benchmark.py" `
    --gcode-dir "agentic_execution_kit\MISSION_02_GCODE" `
    --out-dir "reports\mission2_benchmark" *> "reports\mission2_benchmark\mission2_virtual_benchmark.log"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Mission 02 virtual benchmark FAILED. See reports\mission2_benchmark\mission2_virtual_benchmark.log"
    exit $LASTEXITCODE
}

Write-Host "Mission 02 virtual benchmark PASS"
Write-Host "Summary: reports\mission2_benchmark\mission2_benchmark_summary.md"

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path ".\reports\mission4_planner" | Out-Null

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

& $py tools\mission4_planner_selftest.py *> ".\reports\mission4_planner\mission4_selftest.log"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Mission 04 planner self-test FAILED. See reports\mission4_planner\mission4_selftest.log"
    exit $LASTEXITCODE
}
Write-Host "Mission 04 planner self-test PASS."
Write-Host "Summary: reports\mission4_planner\mission4_planner_selftest_summary.md"

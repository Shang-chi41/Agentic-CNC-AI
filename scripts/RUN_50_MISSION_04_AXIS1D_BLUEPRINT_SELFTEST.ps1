$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host '=== Mission 04+ Axis 1D Driver-Motor Blueprint Self-test ==='
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
& $python tools\axis1d_driver_motor_model.py --out reports\mission4_axis1d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'PASS: reports\mission4_axis1d created.'

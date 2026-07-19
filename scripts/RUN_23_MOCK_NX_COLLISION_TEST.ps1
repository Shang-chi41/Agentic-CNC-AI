$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Starting mock NX MCD collision client on port 6001..." -ForegroundColor Yellow
Write-Host "Use this instead of real NX MCD to prove collision stop/reset." -ForegroundColor Yellow
$env:MOCK_NXMCD_COLLIDE_AFTER = if ($env:MOCK_NXMCD_COLLIDE_AFTER) { $env:MOCK_NXMCD_COLLIDE_AFTER } else { "20" }
$env:MOCK_NXMCD_COLLISION_MASK = if ($env:MOCK_NXMCD_COLLISION_MASK) { $env:MOCK_NXMCD_COLLISION_MASK } else { "8" }
python tools\mock_nxmcd_collision_6001.py

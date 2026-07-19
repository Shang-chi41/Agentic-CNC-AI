$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$stamp = Get-Date -Format "yyyy_MM_dd_HHmmss"
$dest = "FULL_LOOP_REAL_EVIDENCE_$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Copy-Item ".\reports\*" $dest -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item ".\agentic_execution_kit\TEMPLATES\FULL_LOOP_REAL_EVIDENCE_TEMPLATE.md" "$dest\FULL_LOOP_REAL_EVIDENCE.md" -Force -ErrorAction SilentlyContinue

@"
# Evidence Collection Note

Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

.env is intentionally NOT copied automatically to avoid leaking secrets.
Copy only sanitized operational keys if needed:
RUN_GCODE_TARGET, ALLOW_SIMULATION_RUN, RUN_PERMISSION_GATE, SIM_GCODE_LINE_PERIOD_S, SIMULINK_*_PORT, NX_PORT.
"@ | Out-File "$dest\README_EVIDENCE.md" -Encoding UTF8

Write-Host "Evidence copied to $dest"
Write-Host "Do not share secrets. Add screenshots/video from MATLAB/NX MCD manually."

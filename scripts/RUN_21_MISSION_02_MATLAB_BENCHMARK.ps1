$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path ".\reports\mission2_matlab_benchmark" | Out-Null

$matlabScript = "try, addpath('matlab_bridge'); RUN_MISSION_02_BENCHMARK_R2023B; catch ME, disp(getReport(ME,'extended')); exit(1); end; exit(0);"
Write-Host "===== Mission 02 MATLAB/Simulink position benchmark ====="
Write-Host "This requires MATLAB R2023b or a compatible MATLAB on PATH."

matlab -batch $matlabScript *> "reports\mission2_matlab_benchmark\mission2_matlab_benchmark.log"
if ($LASTEXITCODE -ne 0) {
    Write-Host "MATLAB Mission 02 benchmark FAILED. See reports\mission2_matlab_benchmark\mission2_matlab_benchmark.log"
    exit $LASTEXITCODE
}

Write-Host "MATLAB Mission 02 benchmark PASS"
Write-Host "Summary: reports\mission2_matlab_benchmark\mission2_matlab_benchmark_summary.md"

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path ".\reports" | Out-Null

function Write-SummaryLine($text) {
    Add-Content -Path ".\reports\LOCAL_VERIFY_SUMMARY.md" -Value $text -Encoding UTF8
}

"# Local Verification Summary" | Out-File ".\reports\LOCAL_VERIFY_SUMMARY.md" -Encoding UTF8
Write-SummaryLine ""
Write-SummaryLine "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-SummaryLine ""
Write-SummaryLine "| Step | Result | Log |"
Write-SummaryLine "|---|---|---|"

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

function Run-Step($name, $cmd, $log) {
    Write-Host "===== $name ====="
    $fullLog = ".\reports\$log"
    $stdoutLog = "$fullLog.stdout.tmp"
    $stderrLog = "$fullLog.stderr.tmp"

    # Use Start-Process to prevent native stderr from becoming a PowerShell
    # NativeCommandError when ErrorActionPreference=Stop. This keeps test
    # output in the log file and uses only the process exit code for PASS/FAIL.
    $proc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/d", "/s", "/c", $cmd `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog

    $code = $proc.ExitCode
    "# STDOUT" | Out-File $fullLog -Encoding UTF8
    if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Raw | Add-Content $fullLog -Encoding UTF8 }
    "`n# STDERR" | Add-Content $fullLog -Encoding UTF8
    if (Test-Path $stderrLog) { Get-Content $stderrLog -Raw | Add-Content $fullLog -Encoding UTF8 }
    Remove-Item $stdoutLog, $stderrLog -ErrorAction SilentlyContinue

    if ($code -eq 0) {
        Write-SummaryLine "| $name | PASS | $log |"
    } else {
        Write-SummaryLine "| $name | FAIL exit=$code | $log |"
        Write-Host "FAILED: $name. See $fullLog"
        exit $code
    }
}

Run-Step "pip upgrade" "$py -m pip install --upgrade pip" "00_pip_upgrade.log"
Run-Step "install requirements" "$py -m pip install -r requirements.txt pytest" "01_pip_install.log"
Run-Step "compileall" "$py -m compileall edge_backend cloud_backend tools virtual_lab integration_tests" "02_compileall.log"
Run-Step "pytest" "$py -m pytest integration_tests -v" "03_pytest.log"
Run-Step "virtual lab cnc3" "$py virtual_lab\cnc3_virtual_lab.py --report reports\virtual_lab_report.json" "04_virtual_lab_cnc3.log"
Run-Step "bridge pacing lab" "$py virtual_lab\bridge_pacing_lab.py" "05_bridge_pacing_lab.log"
Run-Step "full loop mock selftest" "$py tools\full_loop_mock_selftest.py" "06_full_loop_mock_selftest.log"
Run-Step "mission 02 virtual benchmark" "$py tools\mission2_position_benchmark.py --gcode-dir agentic_execution_kit\MISSION_02_GCODE --out-dir reports\mission2_benchmark" "08_mission2_virtual_benchmark.log"
Run-Step "mission 04 planner selftest" "$py tools\mission4_planner_selftest.py" "09_mission4_planner_selftest.log"
Run-Step "mission 07 static connection audit" "$py tools\full_connection_audit.py --mode static --profile all --out-dir reports\full_connection_audit --strict" "10_connection_audit_static.log"
Run-Step "mission 08 agentic flexibility eval" "$py eval\agentic_flexibility_eval.py --out reports\agentic_flexibility_eval.json" "11_agentic_flexibility_eval.log"
Run-Step "mission 09 check/gate/arc/knowledge eval" "$py eval\mission09_check_gate_arc_knowledge_eval.py" "12_mission09_check_gate_arc_knowledge_eval.log"

if (Test-Path ".\frontend\js") {
    $jsFiles = Get-ChildItem ".\frontend\js\*.js" -ErrorAction SilentlyContinue
    if ($jsFiles.Count -gt 0) {
        Run-Step "node --check frontend js" "$py tools\check_frontend_js.py --dir frontend\js" "07_node_check.log"
    }
}

Write-SummaryLine ""
Write-SummaryLine "Lưu ý: local verification không thay thế MATLAB/NX MCD/máy CNC thật."
Write-Host "DONE. Summary: reports\LOCAL_VERIFY_SUMMARY.md"

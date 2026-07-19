# CNC HMI V18 A — 3-axis CLEAN READY

Bản này đã bỏ các file rác/cũ:

- Không có `__pycache__`, `.pytest_cache`, `.pyc`
- Không có các báo cáo audit/validation cũ ở thư mục gốc
- Không có các model `.slx` thử nghiệm cũ trong `models/`
- Chỉ giữ file cần để chạy Cloud, Edge simulation, virtual lab, MATLAB self-test, và tạo model Simulink cuối cùng

## 1. Tạo môi trường Python trong VS Code

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r .\cloud_backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

Tạo `.env`:

```powershell
Kiểm tra file .env đã có sẵn cấu hình thật; .env.example chỉ là mẫu không chứa secret
```

## 2. Test không cần MATLAB

```powershell
.\.venv\Scripts\python.exe virtual_lab\cnc3_virtual_lab.py --report reports\virtual_lab_report.json
.\.venv\Scripts\python.exe -m pytest -q integration_tests
```

## 3. Tạo model Simulink cuối cùng

Chạy từ VS Code terminal:

```powershell
.\RUN_MATLAB_CREATE_MODEL_FROM_VSCODE.bat
```

File sinh ra:

```text
models/chay_dao_3axis_nx_loop_R2023b.slx
```

## 4. MATLAB self-test độc lập

Không cần Edge/Cloud/NX. Dùng port riêng `15100/15101`:

```powershell
.\RUN_MATLAB_FULL_SELFTEST_FROM_VSCODE.bat
```

Kỳ vọng:

```text
MATLAB CNC3 FULL LOOP SELFTEST PASS
```

Report:

```text
reports/matlab_cnc3_selftest_report.txt
```

## 5. Chạy Cloud/Edge thật trong VS Code

Cloud:

```powershell
.\.venv\Scripts\python.exe -m uvicorn cloud_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Edge simulation only:

```powershell
.\.venv\Scripts\python.exe -m edge_backend.main_sim_only
```

Mock NX MCD:

```powershell
.\.venv\Scripts\python.exe tools\mock_nxmcd_6001.py
```

## 6. Chạy loop thật

MATLAB bridge:

```matlab
cd('C:\path\to\cnc_hmi_v18_A_3axis_CLEAN_READY')
addpath('matlab_bridge')
clear classes
apply_chay_dao_parameters_R2023b
run_edge_matlab_bridge_R2023b_CNC3_quiet
```

Mở model:

```matlab
cd('C:\path\to\cnc_hmi_v18_A_3axis_CLEAN_READY')
addpath('matlab_bridge')
clear classes
apply_chay_dao_parameters_R2023b
open_system('models/chay_dao_3axis_nx_loop_R2023b.slx')
```

G-code test:

```gcode
G21
G90
G0 X0 Y0 Z5
G1 X30 Y10 Z0 F400
G1 X0 Y0 Z0 F400
M30
```

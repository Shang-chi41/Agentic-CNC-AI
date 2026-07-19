# CNC3 Virtual Lab — môi trường ảo không cần MATLAB/NX

Mục tiêu: kiểm tra đường logic từ nạp G-code đến payload NX MCD bằng Python thuần, không cần MATLAB, Simulink, MongoDB, Cloud, Edge thật hay NX MCD.

Luồng được mô phỏng:

```text
HMI/Cloud nạp G-code
→ Edge tạo yêu cầu simulation
→ Simulink 3-axis virtual model
→ CNC3 frame 116 bytes
→ Edge normalize JSON
→ NX MCD 12 LREAL big-endian 96 bytes
→ Mock NX kiểm tra quỹ đạo
```

Chạy trong VS Code:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe virtual_lab\cnc3_virtual_lab.py
```

Hoặc dùng task VS Code:

```text
Terminal → Run Task → 0 Virtual Lab Selftest No MATLAB
```

Kết quả sẽ sinh:

```text
reports/virtual_lab_report.json
```

Ý nghĩa: nếu test này PASS thì phần contract dữ liệu CNC3/NX, tốc độ gửi 30 Hz, lọc NaN/Inf và mapping X/Y/Z sang 12 LREAL đã ổn về logic. Nó không chứng minh Simulink/NX thật chạy được, vì phần đó phải test trên máy có MATLAB R2023b và NX MCD.

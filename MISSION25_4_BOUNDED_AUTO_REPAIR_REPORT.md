# Mission 25.4 — Bounded Auto-Repair + Frontend F1–F4 Evidence

## Phạm vi

Bổ sung vòng sửa xác định cho G-code đã được người dùng xác nhận khi static CHECK chỉ phát hiện lỗi process-range có thể sửa an toàn:

- `FEED_OUT_OF_RANGE`
- `SPINDLE_OUT_OF_RANGE`
- `STEPDOWN_OUT_OF_RANGE`

Không tự sửa geometry, tool, WCS, axis-limit, feature role hoặc semantic mismatch.

## Luồng mới

```text
UserIntentContract đã xác nhận exact hash
→ static CHECK bằng chính ResolvedProcessContract v2
→ nếu PASS: gửi MATLAB/NX như cũ
→ nếu chỉ có process-range blocker: tái sinh từ exact JobSpec + exact process contract
→ static + semantic validate lại
→ chỉ bản repaired PASS mới được gửi MATLAB test/simulation
→ production_eligible=false
→ frontend vô hiệu hóa artifact cũ
→ người dùng phải xác nhận lại exact repaired hash
→ CHECK lần hai mới có thể tạo approval
```

## Case nguyên văn F1–F4

Input browser:

```text
Phôi nhôm 6061 kích thước 100 × 80 × 12 mm. Dao T1 END_MILL D6. Safe Z 3 mm.
F1: ROUNDED_RECT_POCKET 50 × 35 mm, R5, tâm X0 Y0, sâu 3 mm.
F2: CIRCULAR_POCKET Ø12, tâm X-20 Y0, sâu 2 mm.
F3: CIRCULAR_POCKET Ø12, tâm X20 Y0, sâu 2 mm.
F4: RECTANGULAR_CONTOUR_OUTSIDE 80 × 60 mm, sâu 4 mm.
```

FeatureGraph thực tế chứa đúng `F1, F2, F3, F4` theo thứ tự ID.

Test ép artifact có hai `F550` và một step-down `0.5 mm`, trong khi contract yêu cầu feed `[600,1500]` và step-down `[1,3]`.

Kết quả:

- static trước sửa: FAIL;
- repair: applied, candidate `C1`;
- JobSpec hash giữ nguyên;
- G-code sửa không còn `F550`;
- static sau sửa: PASS;
- bản lỗi cũ bị xóa khỏi Control;
- QUEUE trước reconfirm: không gửi;
- QUEUE sau reconfirm: chỉ gửi exact repaired G-code/hash;
- CHECK lần đầu của bản repaired dùng `production_eligible=false`.

## Bằng chứng terminal

| Nhóm | Kết quả |
|---|---:|
| Backend/worker focused auto-repair | 8 PASS |
| Chromium frontend E2E | 2 PASS |
| JavaScript intent/hash gate | 10 PASS |
| Mission 24–25 relevant regression | 95 PASS |
| Core dangerous mutations | 4/4 killed |
| Compileall backend/cloud | PASS |

## Giới hạn bằng chứng

- Chromium chạy DOM và module frontend thật, nhưng sandbox chặn navigation tới origin bình thường. Test dùng `about:blank`, route interception và exact digest mapping cho ba payload đã biết. Hash/tamper logic được kiểm riêng bằng Node WebCrypto tests.
- MATLAB/NX thật chưa chạy. Sender được thay bằng test double để chứng minh chỉ repaired artifact được truyền và `production_eligible=false`.
- Full 64-file integration suite không có terminal PASS trong container hiện tại vì thiếu `pymongo`, `neo4j`, `bson`; lượt dùng import stub phát sinh failure và timeout nên không được tính.
- Auto-repair không phải trình sửa G-code tổng quát. Không có exact confirmed JobSpec/contract hoặc gặp geometry/safety blocker thì dừng trước MATLAB.

## Trạng thái

```yaml
bounded_process_auto_repair: VERIFIED_L2
frontend_f1_f4_chat_flow: VERIFIED_L2_CHROMIUM
stale_artifact_queue_bypass: BLOCKED_IN_TESTED_FLOW
reconfirmation_after_repair: REQUIRED
real_matlab_nx: NOT_RUN
full_repository_regression: NOT_VERIFIED_IN_CURRENT_CONTAINER
production_ready: false
```

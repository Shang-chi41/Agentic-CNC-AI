// ============================================================================
// CNC KNOWLEDGE GRAPH — SEED SCRIPT (Neo4j / Cypher)
// Máy: Phay đứng CNC cỡ nhỏ — Đồ án tốt nghiệp HUST
// ============================================================================
//
// CĂN CỨ SỐ LIỆU (để các thông số "chứng minh lẫn nhau" thay vì rời rạc):
//
// 1) Từ bảng thông số gốc (ảnh 1):
//    - Loại máy      : Phay đứng CNC, cỡ nhỏ, hành trình ≤400×300×100 mm
//    - Công suất trục chính : 1.5 kW
//    - Phôi tối đa   : 100×100×60 mm, ≤20 kg
//    - Độ cứng phôi  : ≤ 550 HB
//    - Dao chủ yếu   : dao phay ngón (end mill)
//
// 2) Dòng điện đo được (đề bài cho):
//    - I_rms = 2.36 A   (dòng hiệu dụng khi cắt ở điều kiện phổ biến/nền)
//    - I_max = 3.61 A   (dòng đỉnh, ngưỡng an toàn/quá tải)
//
// 3) Suy luận điện — động cơ trục chính 3 pha 380V, cosφ≈0.82, η≈0.85
//    (thông số điển hình của spindle 1.5kW làm mát khí, ER11/ER20):
//      I_rated = P / (√3 × V × cosφ × η)
//              = 1500 / (1.732 × 380 × 0.82 × 0.85) ≈ 3.3 A
//    → I_max = 3.61 A cao hơn I_rated lý thuyết ~9%, hợp lý vì I_max là
//      dòng đỉnh tức thời (khi cắt vật liệu cứng nhất cho phép, 550 HB),
//      không phải dòng làm việc liên tục.
//    → I_idle (không tải) ước lượng ≈ 25% I_rated ≈ 0.85 A.
//
//    => I_rms=2.36A được gán cho tổ hợp gia công "nền" (thép C45, phay thô,
//       dao phổ biến) — tức là điều kiện cắt trung bình/thường gặp nhất.
//    => I_max=3.61A được gán đúng vào tổ hợp cắt vật liệu cứng nhất mà máy
//       cho phép (SKD11 tôi cứng, 550 HB — đúng bằng giới hạn "Độ cứng phôi"
//       trong bảng thông số gốc). Đây là điểm neo giúp hai số liệu
//       (dòng điện & độ cứng phôi) chứng minh lẫn nhau.
//
// Các giá trị feed/spindle/depth còn lại là ƯỚC LƯỢNG kỹ thuật hợp lý theo
// kinh nghiệm gia công cơ khí (không tuyệt đối chính xác), dùng để hoàn
// thiện cấu trúc đồ thị — có thể tinh chỉnh lại khi có dữ liệu đo thực tế.
// ============================================================================


// ---------- 0. CONSTRAINTS (đảm bảo không trùng khi chạy lại) ----------
CREATE CONSTRAINT machine_name IF NOT EXISTS FOR (m:Machine) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT axis_name IF NOT EXISTS FOR (a:Axis) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT tool_id IF NOT EXISTS FOR (t:Tool) REQUIRE t.tool_id IS UNIQUE;
CREATE CONSTRAINT operation_id IF NOT EXISTS FOR (o:Operation) REQUIRE o.op_id IS UNIQUE;
CREATE CONSTRAINT material_name IF NOT EXISTS FOR (mt:Material) REQUIRE mt.name IS UNIQUE;
CREATE CONSTRAINT range_id IF NOT EXISTS FOR (r:OperatingRange) REQUIRE r.range_id IS UNIQUE;
CREATE CONSTRAINT alarm_label IF NOT EXISTS FOR (al:AlarmPattern) REQUIRE al.label IS UNIQUE;
CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (mr:MaintenanceRule) REQUIRE mr.rule_id IS UNIQUE;


// ---------- 1. MACHINE ----------
MERGE (m:Machine {name: "CNC_VerticalMill_Mini_01"})
SET m.axes_count      = 3,
    m.work_volume_mm  = "400x300x100",
    m.spindle_power_kW = 1.5,
    m.max_workpiece_mm = "100x100x60",
    m.max_workpiece_kg = 20,
    m.max_hardness_HB  = 550,
    m.note = "Phay đứng CNC cỡ nhỏ; dao chủ yếu là dao phay ngón";


// ---------- 2. AXIS (X, Y, Z) ----------
MERGE (ax:Axis {name: "X"})
SET ax.travel_mm = 400, ax.max_feed = 3000, ax.home_offset = -5;

MERGE (ay:Axis {name: "Y"})
SET ay.travel_mm = 300, ay.max_feed = 3000, ay.home_offset = -5;

MERGE (az:Axis {name: "Z"})
SET az.travel_mm = 100, az.max_feed = 1500, az.home_offset = -2;

MATCH (m:Machine {name: "CNC_VerticalMill_Mini_01"})
MATCH (ax:Axis) WHERE ax.name IN ["X", "Y", "Z"]
MERGE (m)-[:HAS_AXIS]->(ax);


// ---------- 3. TOOL (chủ yếu dao phay ngón) ----------
MERGE (t1:Tool {tool_id: "T1"})
SET t1.type = "Dao phay ngón 2 me (Flat End Mill)",
    t1.diameter_mm = 6, t1.material = "Carbide (WC-Co)", t1.max_rpm = 24000;

MERGE (t2:Tool {tool_id: "T2"})
SET t2.type = "Dao phay ngón 4 me (Flat End Mill)",
    t2.diameter_mm = 10, t2.material = "Carbide (WC-Co)", t2.max_rpm = 18000;

MERGE (t3:Tool {tool_id: "T3"})
SET t3.type = "Dao phay ngón mini 2 me",
    t3.diameter_mm = 3, t3.material = "Carbide (WC-Co)", t3.max_rpm = 24000;

MATCH (m:Machine {name: "CNC_VerticalMill_Mini_01"})
MATCH (t:Tool) WHERE t.tool_id IN ["T1", "T2", "T3"]
MERGE (m)-[:HAS_TOOL]->(t);


// ---------- 4. OPERATION ----------
MERGE (o1:Operation {op_id: "OP1"}) SET o1.type = "milling", o1.name = "Phay thô (Roughing)";
MERGE (o2:Operation {op_id: "OP2"}) SET o2.type = "milling", o2.name = "Phay tinh (Finishing)";
MERGE (o3:Operation {op_id: "OP3"}) SET o3.type = "milling", o3.name = "Phay rãnh (Slot milling)";

MATCH (m:Machine {name: "CNC_VerticalMill_Mini_01"})
MATCH (o:Operation) WHERE o.op_id IN ["OP1", "OP2", "OP3"]
MERGE (m)-[:PERFORMS]->(o);

// Tool nào dùng cho Operation nào
MATCH (t1:Tool {tool_id: "T1"}), (t2:Tool {tool_id: "T2"}), (t3:Tool {tool_id: "T3"})
MATCH (o1:Operation {op_id: "OP1"}), (o2:Operation {op_id: "OP2"}), (o3:Operation {op_id: "OP3"})
MERGE (t1)-[:USED_FOR]->(o1)
MERGE (t1)-[:USED_FOR]->(o2)
MERGE (t2)-[:USED_FOR]->(o1)
MERGE (t3)-[:USED_FOR]->(o3);


// ---------- 5. MATERIAL (độ cứng trải từ thấp đến đúng giới hạn 550 HB) ----------
MERGE (mt1:Material {name: "Nhôm 6061"})
SET mt1.hardness = 95, mt1.recommended_feed_ratio = 1.6;

MERGE (mt2:Material {name: "Thép C45 (thường hóa)"})
SET mt2.hardness = 200, mt2.recommended_feed_ratio = 1.0;

MERGE (mt3:Material {name: "Thép 40Cr (đã tôi)"})
SET mt3.hardness = 350, mt3.recommended_feed_ratio = 0.65;

MERGE (mt4:Material {name: "Thép SKD11 (tôi cứng)"})
SET mt4.hardness = 550, mt4.recommended_feed_ratio = 0.35;

// Operation nào áp dụng cho Material nào
MATCH (o1:Operation {op_id: "OP1"}), (o2:Operation {op_id: "OP2"}), (o3:Operation {op_id: "OP3"})
MATCH (mt1:Material {name: "Nhôm 6061"})
MATCH (mt2:Material {name: "Thép C45 (thường hóa)"})
MATCH (mt3:Material {name: "Thép 40Cr (đã tôi)"})
MATCH (mt4:Material {name: "Thép SKD11 (tôi cứng)"})
MERGE (o1)-[:APPLIED_ON]->(mt1)
MERGE (o1)-[:APPLIED_ON]->(mt2)
MERGE (o1)-[:APPLIED_ON]->(mt3)
MERGE (o2)-[:APPLIED_ON]->(mt3)
MERGE (o3)-[:APPLIED_ON]->(mt4);


// ---------- 6. OPERATING RANGE (COMBINE = Tool + Operation + Material) ----------
// OR1: T1 + OP1(Phay thô) + Nhôm 6061 — vật liệu mềm nhất, feed/spindle cao
MERGE (r1:OperatingRange {range_id: "OR1"})
SET r1.current_min_A = 1.0, r1.current_rms_A = 1.6, r1.current_max_A = 2.3,
    r1.feed_min = 600,  r1.feed_max = 1500,
    r1.spindle_min = 14000, r1.spindle_max = 20000,
    r1.depth_min = 1.0, r1.depth_max = 3.0;

// OR2: T2 + OP1(Phay thô) + Thép C45 — điều kiện NỀN, neo I_rms = 2.36A (đề bài)
MERGE (r2:OperatingRange {range_id: "OR2"})
SET r2.current_min_A = 1.4, r2.current_rms_A = 2.36, r2.current_max_A = 3.0,
    r2.feed_min = 250, r2.feed_max = 700,
    r2.spindle_min = 6000, r2.spindle_max = 10000,
    r2.depth_min = 0.5, r2.depth_max = 1.5;

// OR3: T1 + OP2(Phay tinh) + Thép 40Cr tôi — cắt nhẹ, độ cứng trung bình-cao
MERGE (r3:OperatingRange {range_id: "OR3"})
SET r3.current_min_A = 1.2, r3.current_rms_A = 1.9, r3.current_max_A = 2.6,
    r3.feed_min = 100, r3.feed_max = 350,
    r3.spindle_min = 4000, r3.spindle_max = 7000,
    r3.depth_min = 0.1, r3.depth_max = 0.5;

// OR4: T3 + OP3(Phay rãnh) + SKD11 tôi cứng (550HB, đúng giới hạn max của máy)
//      neo I_max = 3.61A (đề bài) — dòng đỉnh khi cắt vật liệu cứng nhất cho phép
MERGE (r4:OperatingRange {range_id: "OR4"})
SET r4.current_min_A = 2.0, r4.current_rms_A = 2.9, r4.current_max_A = 3.61,
    r4.feed_min = 40, r4.feed_max = 150,
    r4.spindle_min = 2500, r4.spindle_max = 5000,
    r4.depth_min = 0.05, r4.depth_max = 0.3;

// Liên kết OperatingRange với Tool + Operation + Material tương ứng
MATCH (t1:Tool {tool_id: "T1"}), (t2:Tool {tool_id: "T2"}), (t3:Tool {tool_id: "T3"})
MATCH (o1:Operation {op_id: "OP1"}), (o2:Operation {op_id: "OP2"}), (o3:Operation {op_id: "OP3"})
MATCH (mt1:Material {name: "Nhôm 6061"})
MATCH (mt2:Material {name: "Thép C45 (thường hóa)"})
MATCH (mt3:Material {name: "Thép 40Cr (đã tôi)"})
MATCH (mt4:Material {name: "Thép SKD11 (tôi cứng)"})
MATCH (r1:OperatingRange {range_id: "OR1"})
MATCH (r2:OperatingRange {range_id: "OR2"})
MATCH (r3:OperatingRange {range_id: "OR3"})
MATCH (r4:OperatingRange {range_id: "OR4"})
MERGE (t1)-[:HAS_RANGE]->(r1)
MERGE (o1)-[:HAS_RANGE]->(r1)
MERGE (mt1)-[:HAS_RANGE]->(r1)
MERGE (t2)-[:HAS_RANGE]->(r2)
MERGE (o1)-[:HAS_RANGE]->(r2)
MERGE (mt2)-[:HAS_RANGE]->(r2)
MERGE (t1)-[:HAS_RANGE]->(r3)
MERGE (o2)-[:HAS_RANGE]->(r3)
MERGE (mt3)-[:HAS_RANGE]->(r3)
MERGE (t3)-[:HAS_RANGE]->(r4)
MERGE (o3)-[:HAS_RANGE]->(r4)
MERGE (mt4)-[:HAS_RANGE]->(r4);


// ---------- 7. ALARM PATTERN ----------
MERGE (al1:AlarmPattern {label: "overload"})
SET al1.symptoms = [
  "Dòng điện trục chính vượt current_max_A liên tục trên 5 giây",
  "Tốc độ trục chính (rpm) sụt giảm đột ngột dưới tải",
  "Nhiệt độ vỏ động cơ tăng nhanh bất thường"
];

MERGE (al2:AlarmPattern {label: "tool_wear"})
SET al2.symptoms = [
  "Dòng điện tăng dần theo thời gian dù feed/spindle giữ nguyên",
  "Bề mặt gia công xuất hiện vết rung/xước",
  "Âm thanh cắt thay đổi tần số (rít cao hơn)"
];

MERGE (al3:AlarmPattern {label: "bearing_failure"})
SET al3.symptoms = [
  "Rung động trục chính vượt ngưỡng cho phép ngay cả khi không tải",
  "Dòng điện dao động nhiễu cao tần bất thường dù tải ổn định",
  "Nhiệt độ ổ trục tăng khi chạy không tải"
];

// Mọi OperatingRange đều có thể kích hoạt bất kỳ AlarmPattern nào
// (AI sẽ so khớp dữ liệu thực tế với 3 mẫu này để xác định loại bất thường)
MATCH (r:OperatingRange)
MATCH (al:AlarmPattern)
MERGE (r)-[:MAY_TRIGGER]->(al);


// ---------- 8. MAINTENANCE RULE ----------
MERGE (mr1:MaintenanceRule {rule_id: "MR1"})
SET mr1.trigger = "current_A > current_max_A (OR4 = 3.61A) duy trì > 5 giây",
    mr1.action  = "Dừng khẩn cấp trục chính, giảm feed override còn 50%, kiểm tra chiều sâu cắt/tải phôi",
    mr1.severity = "high";

MERGE (mr2:MaintenanceRule {rule_id: "MR2"})
SET mr2.trigger = "current_A tăng > 20% so với current_rms_A nền (2.36A) trong cùng điều kiện cắt, kéo dài 30 phút",
    mr2.action  = "Cảnh báo kiểm tra/thay dao do mòn lưỡi cắt",
    mr2.severity = "medium";

MERGE (mr3:MaintenanceRule {rule_id: "MR3"})
SET mr3.trigger = "Rung động bất thường khi trục chính quay không tải (ngoài chu trình cắt)",
    mr3.action  = "Lên lịch kiểm tra và bôi trơn ổ trục chính",
    mr3.severity = "medium";

MATCH (al1:AlarmPattern {label: "overload"})      MATCH (mr1:MaintenanceRule {rule_id: "MR1"})
MATCH (al2:AlarmPattern {label: "tool_wear"})      MATCH (mr2:MaintenanceRule {rule_id: "MR2"})
MATCH (al3:AlarmPattern {label: "bearing_failure"}) MATCH (mr3:MaintenanceRule {rule_id: "MR3"})
MERGE (al1)-[:RECOMMENDS]->(mr1)
MERGE (al2)-[:RECOMMENDS]->(mr2)
MERGE (al3)-[:RECOMMENDS]->(mr3);

// OperatingRange cũng liên kết trực tiếp tới MaintenanceRule (đúng theo sơ đồ gốc)
MATCH (r:OperatingRange)
MATCH (mr:MaintenanceRule)
MERGE (r)-[:RECOMMENDS]->(mr);

// ---------- MISSION 21: END_MILL_ONLY CAM KNOWLEDGE ----------
MATCH (t1:Tool {tool_id: "T1"})
SET t1.family = "END_MILL", t1.center_cutting = true,
    t1.flute_length_mm = coalesce(t1.flute_length_mm, 20.0),
    t1.supported_entry_modes = ["plunge", "ramp", "helix"];

MERGE (m21_mat:Material {name: "Aluminum 6061"})
SET m21_mat.family = "ALUMINUM", m21_mat.alloy_grade = "6061";

UNWIND [
  {name:"ROUNDED_RECT_POCKET", id:"M21_OP1", range:"M21_OR1", fmin:800, fmax:1300, smin:15000, smax:19000, dmax:3.0, so:0.55},
  {name:"CIRCULAR_OUTSIDE_KEEP_ISLAND", id:"M21_OP2", range:"M21_OR2", fmin:700, fmax:1200, smin:15000, smax:19000, dmax:3.0, so:0.45},
  {name:"CIRCULAR_THROUGH_MILL", id:"M21_OP3", range:"M21_OR3", fmin:500, fmax:900, smin:15000, smax:19000, dmax:2.0, so:0.35},
  {name:"CROSS_SLOT_MILL", id:"M21_OP4", range:"M21_OR4", fmin:600, fmax:1000, smin:15000, smax:19000, dmax:2.5, so:0.40},
  {name:"RECTANGULAR_POCKET", id:"M21_OP5", range:"M21_OR5", fmin:800, fmax:1300, smin:15000, smax:19000, dmax:3.0, so:0.55},
  {name:"SLOT_MILL", id:"M21_OP6", range:"M21_OR6", fmin:600, fmax:1000, smin:15000, smax:19000, dmax:2.5, so:0.40},
  {name:"CIRCULAR_POCKET", id:"M21_OP7", range:"M21_OR7", fmin:550, fmax:950, smin:15000, smax:19000, dmax:2.0, so:0.35},
  {name:"CIRCULAR_CONTOUR_INSIDE", id:"M21_OP8", range:"M21_OR8", fmin:650, fmax:1100, smin:15000, smax:19000, dmax:2.5, so:0.30},
  {name:"CIRCULAR_CONTOUR_OUTSIDE", id:"M21_OP9", range:"M21_OR9", fmin:650, fmax:1100, smin:15000, smax:19000, dmax:2.5, so:0.30},
  {name:"RECTANGULAR_CONTOUR_INSIDE", id:"M21_OP10", range:"M21_OR10", fmin:700, fmax:1200, smin:15000, smax:19000, dmax:2.5, so:0.35},
  {name:"RECTANGULAR_CONTOUR_OUTSIDE", id:"M21_OP11", range:"M21_OR11", fmin:700, fmax:1200, smin:15000, smax:19000, dmax:2.5, so:0.35}
] AS row
MERGE (op:Operation {name: row.name}) SET op.op_id = row.id, op.type = "milling", op.tool_family = "END_MILL"
MERGE (rng:OperatingRange {range_id: row.range})
SET rng.feed_min=row.fmin, rng.feed_max=row.fmax,
    rng.spindle_min=row.smin, rng.spindle_max=row.smax,
    rng.depth_min=0.1, rng.depth_max=row.dmax,
    rng.stepover_ratio=row.so, rng.entry_modes=["plunge","ramp","helix"]
WITH op, rng
MATCH (t1:Tool {tool_id:"T1"}), (mat:Material {name:"Aluminum 6061"})
MERGE (t1)-[:HAS_RANGE]->(rng)
MERGE (op)-[:HAS_RANGE]->(rng)
MERGE (mat)-[:HAS_RANGE]->(rng);


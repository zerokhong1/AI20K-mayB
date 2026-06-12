# DUYỆT PHA 1 (CÓ ĐIỀU KIỆN) + LỆNH PHA 2 — PICK/DROP THẬT (Máy B · AI20K-162)

## PHẦN 1 — DUYỆT PHA 1: ✅ CÓ ĐIỀU KIỆN (mốc mới: `3af18ba`)

Máy A đã fetch repo @3af18ba: 12 link poses khớp bảng thiết kế từng số, joint poses zeroed, diff SẠCH (không đổi friction/plugin/inertia nào khác), header comment ghi đủ P1 fix + note URDF 1cm. `.gitignore` root entries ✓. Plan file đã thành skeleton P0–P5 đúng ✓. **Deviation lidar 0.625 + sửa URDF 0.495: CHẤP NHẬN** — toán mast-top (0.285+0.275=0.560) khớp kiểm tra độc lập của Máy A; khi SDF dời sensor thì URDF/TF *bắt buộc* phải theo, không phải vi phạm lệnh.

**ĐIỀU KIỆN — "PHA 1.5", nộp kèm báo cáo Pha 2 (≈15'), thiếu thì số Pha 1 KHÔNG được vào report/Bảng C:**

- **R1.** Raw nguyên văn 6 phép đo G1.2 **+ hàng AMCL còn thiếu** (`tf2_echo map base_footprint` trước/sau push test). Báo cáo vừa rồi chỉ có delta đã tính — bảng 3 nguồn × trước/sau là yêu cầu gốc.
- **R2.** Provenance số `|odomΔ−GTΔ|=0.000`: số CHƯA làm tròn của cả hai delta (vd 1.36789 vs 1.36801), và xác nhận nguồn GT trong script = `gz model -p`/pose-info chứ KHÔNG phải /odom. Sim không trượt bánh thì ≈0.000 là khả dĩ — nhưng 0.000 tròn trĩnh phải có số gốc chống lưng, nếu hai delta đọc từ cùng nguồn thì đo lại.
- **R3.** Script "push test python" chưa nằm trong files-changed → chưa version hoá. Commit vào `eval/push_test.py` (Pha 4 tái dùng).
- **R4.** Raw output action client G1.3 (status SUCCEEDED + feedback cuối) + toạ độ goal đã dùng.

**2 ghi nhận honesty mới (Máy A tự phát hiện khi đọc code/SDF — đưa vào sổ Pha 5):**
- `move_to()` có fallback "Nav2 fail nhưng AMCL dist <1.5m → return True". Hợp lý kỹ thuật, nhưng mọi số "nav success" ở Bảng C phải kèm nhãn `(relaxed ≤1.5m fallback)`.
- Lidar 0.625m → scan plane KHÔNG thấy vật thấp (pallet 0.10–0.30m): costmap + collision_monitor mù pallet, và map 005 được bake ở độ cao lidar khác → AMCL match được test này nhưng có thể flaky ở khu khác. Disclose ở Pha 4/5; Pha 2 phải né hệ quả (xem watch-list).

---

## PHẦN 2 — LỆNH PHA 2: PICK/DROP PHYSICS, XOÁ TELEPORT KHỎI ACTION PATH

**Mốc:** `3af18ba` · **Timebox:** 4h · **DoD:** 1 task pick→carry→drop end-to-end qua backend API (không LLM) với oracle độc lập + carried-continuity; `_gz_set_pose` biến mất khỏi pick()/drop(); push.
**Oracle pha này:** GT pallet + GT robot từ gz, đọc bởi **script riêng** — không bao giờ tin giá trị backend tự trả về.

### Thiết kế Máy A đã chốt (đọc gazebo_backend.py @3af18ba)

**Không dùng `aws_robomaker_warehouse_PalletJackB_01_001` làm vật pick** — đó là pallet *jack* (xe nâng tay), mesh collision không có khe fork, ở góc xa (-0.28,-9.48). Thay bằng **sim_pallet vendored** (pallet đơn giản hoá có khe fork — disclose rõ trong report). Logical name mới `pallet_1`; KHÔNG đổi eval/tasks_m.json pha này (đó là việc Pha 4).

**Hình học đã tính sẵn** (từ SDF fork: plates z 0.04–0.09 khi fork=0, trải x∈[0.365,0.965] frame robot):

```
sim_pallet (1 link, 5 collisions, KHÔNG static):
  deck:  box 0.40×0.40×0.04, tâm z=0.12  (đáy deck z=0.10 > đỉnh fork 0.09 → trượt vào lọt, margin 1cm)
  4 chân: box 0.05×0.05×0.10, tâm (±0.175, ±0.175, 0.05)  → kênh giữa rộng 0.30 > plate 0.25 ✓
  mass 8kg; inertia ixx=iyy≈0.120, izz≈0.213; mu=0.9 (deck+chân)
  → nâng fork 0.20 ⇒ deck bottom ~0.29; effort 500N >> 78N tải ✓
Docking: dừng khi dist(robot_GT, pallet_GT) ∈ [0.62, 0.72] m và |bearing| ≤ 5°
```

### B2.0 — Audit trước khi code (paste raw)

```bash
ros2 topic pub --once /fork_cmd std_msgs/msg/Float64 '{data: 0.15}'
sleep 3 && ros2 topic echo /joint_states --once | grep -A8 name   # fork_joint position ≈0.15?
ros2 topic pub --once /fork_cmd std_msgs/msg/Float64 '{data: 0.0}'
```

**GATE G2.0:** fork_joint đạt ~0.15 (±0.02) trong joint_states. Fork không nhúc nhích → dừng, báo raw (PID/plugin issue, Máy A muốn thấy trước).

### B2.1 — Vendor sim_pallet + spawn

- Tạo `colcon_ws/src/warehouse_nav/models/sim_pallet/{model.config,model.sdf}` theo spec trên. CMakeLists đã install cả `models/` (kiểm tra — nếu chỉ install warehouse_forklift thì sửa, ghi deviation).
- Spawn runtime: `ros2 run ros_gz_sim create -file <share>/models/sim_pallet/model.sdf -name pallet_1 -x <px> -y <py> -z 0.0`. Chọn (px,py) trong aisle chính: cách spawn robot ≥3m, `check_path` tới approach OK, KHÔNG nằm trên đường Nav2 spawn→dropoff_a(0,0). Ghi toạ độ vào báo cáo.

**GATE G2.1** (raw): spawn OK; `gz model -m pallet_1 -p` ra pose; sau 5s pallet đứng yên z≈0.0 (model origin) không trôi/lật; nếu "Unable to find uri" → thêm models path của warehouse_nav vào GZ_SIM_RESOURCE_PATH trong launch (deviation hợp lệ, ghi rõ).

### B2.2 — pick()/drop() thật trong gazebo_backend.py

- Node thêm publisher `/cmd_vel` (hiện CHƯA có).
- `pick(name)`: resolve pose qua `locate_object(name)` (pallet_1 sẽ rơi vào nhánh gz_cli → GT-servo, disclose "perception đến Pha 3"); Nav2 tới approach (cách pallet 1.2m, heading vào pallet); fork 0.0; servo cmd_vel ≤0.12 m/s (P-control bearing, đọc GT robot+pallet mỗi tick) tới dist ∈ [0.62,0.72]; dừng; `/fork_cmd 0.20`; chờ 3s; lùi 0.5m. **Return True CHỈ khi đo được**: pallet GT z tăng ≥0.10 so với trước nâng VÀ sau khi lùi pallet vẫn theo robot (|Δxy_pallet − Δxy_robot| ≤ 0.05).
- `drop(x,y)`: Nav2 tới approach của (x,y); tiến chậm 0.4m; fork 0.0; chờ 2s; lùi 0.6m. Return True khi pallet GT xy cách (x,y) ≤ 0.5m và z về ≈ mặt đất.
- **XOÁ 2 call `_gz_set_pose` khỏi pick()/drop()**. Giữ hàm helper nhưng thêm docstring: `SETUP/RESET ONLY — FORBIDDEN in actions`. `oracle_check()`: tham số hoá tên pallet (default env `PALLET_MODEL=pallet_1`), bỏ hardcode PalletJackB (refactor đầy đủ để Pha 4).

**GATE G2.2 — test TĨNH trước end-to-end** (script, không LLM): teleport-SETUP pallet thẳng trước mũi robot đúng hướng (cho phép vì là setup, ghi rõ), rồi chỉ chạy dock→lift→reverse. Raw: bảng GT pallet (x,y,z) + GT robot tại 4 mốc (trước dock / sau dock / sau lift / sau lùi 0.5m). PASS: z pallet tăng ≥0.10; pallet theo robot khi lùi (±0.05).

### B2.3 — GATE G2.3: end-to-end qua backend API

Script python: `backend.move_to(approach) → backend.pick("pallet_1") → backend.move_to(dropoff_a) → backend.drop(0.0, 0.0)`. Song song chạy **`eval/carry_monitor.py` (viết mới, commit)**: sample `gz model -m pallet_1 -p` 2Hz suốt task → JSONL.

PASS (oracle script riêng, không phải giá trị backend trả):
- pallet GT cách dropoff_a ≤ 0.5m (chặt hơn threshold 1.5 của oracle_check — số thật ghi cả hai nhãn)
- carried-continuity: ≥80% mẫu trong đoạn transit có pallet z > 0.10
- robot GT cuối ≤ 1.0m dropoff_a; pallet KHÔNG bị đẩy/ủi tới đích (kiểm bằng continuity — đẩy thì z luôn ≈0)

Raw: JSONL trace (đính kèm hoặc commit vào eval/results/traces/), 3 số cuối, log backend.

### B2.4 — GATE G2.4: chốt pha

```bash
bash scripts/kill_ros.sh && bash scripts/start_demo.sh        # restart sống, ghi giây + nhãn warm/cold
cd ~/AI20K && git add -A
git commit -m "P2: physics pick/drop via fork + sim_pallet; remove teleport from action path"
git diff HEAD~1 | grep -inE 'api[_-]?key|secret|token|AIza|sk-' || echo "KEY-SCAN: clean"
git push origin main && git rev-parse --short HEAD
grep -n "_gz_set_pose" colcon_ws/src/warehouse_robot_agent/warehouse_robot_agent/gazebo_backend.py   # raw: chỉ còn helper+docstring, 0 call trong pick/drop
```

### WATCH-LIST

1. **Lidar mù pallet** (0.625 > pallet 0.30): Nav2 sẽ KHÔNG né pallet_1 → đặt pallet ngoài tuyến transit; nếu Nav2 đâm xuyên pallet trong G2.3 → đổi vị trí spawn, ghi nhận sự cố vào disclosure (đây là hệ quả đã biết, không giấu).
2. Fork PID overshoot với tải 8kg (p=200,d=20): pallet nảy → nâng từng nấc 0.05 trước khi đụng tới gains; đổi gains = deviation ghi rõ.
3. Pallet trượt/lật khi lùi hoặc quay: giảm tốc, KHÔNG hàn joint ảo pallet–fork (= teleport trá hình). Bắt buộc weld mới chạy được → DỪNG, báo Máy A kèm raw.
4. Servo đọc GT qua subprocess gz CLI ~50–100ms/tick: 10Hz có thể hụt — 5Hz đủ với 0.12 m/s.
5. `move_to` fallback ≤1.5m có thể che Nav2 fail trong G2.3 — log phải ghi rõ nhánh nào đã kích hoạt (thêm 1 dòng log phân biệt, được phép).
6. Sửa ngoài phạm vi (gazebo_backend.py, models/sim_pallet, carry_monitor.py, push_test.py, launch resource path nếu cần) = deviation ghi rõ. KHÔNG đụng perception_node/llm_agent/eval tasks pha này.
7. Quá 4h → commit trạng thái, báo honest-partial (vd: G2.2 tĩnh PASS nhưng e2e chưa) — số xấu thật > số đẹp giả.

### BÁO CÁO VỀ

Mục 1: R1–R4 (Pha 1.5). Mục 2: bảng gate G2.0→G2.4 + SHA + files changed + deviations + RAW đầy đủ (đặc biệt bảng 4 mốc G2.2 và trace continuity G2.3). Máy A sẽ fetch model sim_pallet + gazebo_backend.py mới + trace JSONL trên repo để đối chiếu.
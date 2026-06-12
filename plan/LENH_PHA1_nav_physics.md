# DUYỆT PHA 0 + LỆNH PHA 1 — NAV PHYSICS (Máy B · AI20K-162)

## PHẦN 1 — KẾT QUẢ DUYỆT PHA 0: ✅ APPROVED (mốc mới: `a65436e`)

Máy A đã fetch repo đối chiếu: chain commit (cf21ae9→7f4fc16→a65436e), start_demo.sh single-WS + 150s, kill_ros.sh không hard-path, .gitignore bỏ dòng aws, `maps/005/map.yaml` có thật trong bản vendor (map_rotated.png + origin custom — xác nhận gián tiếp claim "17 file sửa local"), root repo KHÔNG lọt build/install/log. Các PROOF nhất quán chéo (build 1.01s nhanh bất thường nhưng được PROOF 3/4/5 corroborate — chấp nhận).

4 ghi chú (không block, xử lý kèm Pha 1):

1. **Prose ≠ raw:** ghi chú G0.0 viết "tree sạch" nhưng raw có 4 entry untracked. Raw thắng, vô hại (untracked-only), nhưng từ nay ghi chú phải khớp raw từng chữ.
2. **Hygiene .gitignore:** root `~/AI20K` có build/install/log untracked mà `.gitignore` chỉ cover `colcon_ws/...` → `git add -A` lần sau sẽ nuốt chúng. Thêm `/build/`, `/install/`, `/log/` vào .gitignore (B1.0 dưới).
3. **Nhãn số:** "Full stack ready in 8 s" là số WARM-RUN (shader cache). Khi số này xuất hiện ở README/report phải mang nhãn `(warm; cold-start ≤150s)`. Cấm "8s" đi một mình.
4. **File plan mislabel:** `plan/PLAN_may_B_trien_khai_full.md` hiện là bản copy LỆNH PHA 0, không phải plan tổng P0–P5 như tên gọi → B1.0 sửa.

---

## PHẦN 2 — LỆNH PHA 1: FIX NAV PHYSICS (BLOCKER)

**Mốc xuất phát:** `a65436e` · **Timebox:** 3h · **DoD:** robot di chuyển THẬT theo GT (gz), Nav2 hoàn thành 1 goal với GT ≤1.0m tới đích, start_demo còn sống, đã push.
**Nguyên tắc:** sửa TRONG REPO `~/AI20K/colcon_ws/src/warehouse_nav` (bản ~/colcon_ws giờ deprecated — không đụng). Mỗi gate kèm raw. Oracle pha này = **GT pose từ gz**, không bao giờ là /odom hay AMCL.

### CHẨN ĐOÁN CỦA MÁY A (đọc model.sdf @a65436e — hypothesis, PHẢI xác nhận bằng G1.1 trước khi sửa)

**H1 (tin cậy cao) — links không có `<pose>`:** Toàn bộ 11 link trong model.sdf KHÔNG có tag `<pose>` riêng → theo SDF spec, tất cả spawn chồng nhau tại gốc model. Các comment trong file ("z-offset puts wheel center at z=0.10") cho thấy tác giả tưởng `<joint><pose>` đặt vị trí child link — đó là semantics của **URDF**; trong **SDF**, `<joint><pose>` chỉ đặt joint frame (relative to child), còn vị trí link do `<link><pose>` quyết định (mặc định = origin). Hệ quả khớp 100% triệu chứng: bánh = 2 đĩa nằm ngang lọt trong thân (self_collide mặc định false nên không nổ), trục quay sai hướng → DiffDrive quay joint nhưng không sinh tịnh tiến; odom tính từ vòng quay bánh vẫn chạy → lệch GT → AMCL drift, err 103. Bonus giải thích luôn: lidar (base_scan) cũng nằm TÂM thân → scan quét vào chính vỏ robot → AMCL không khớp map. Foxglove nhìn "đẹp" vì TF lấy từ URDF (file riêng, offset đúng) chứ không phải từ gz.

**H2 (chắc chắn, độc lập H1):** kể cả theo geometry dự kiến (base center z=0.12, box cao 0.24) thì **đáy thân chạm đất z=0.00** → ma sát thân-đất cản di chuyển. Fix: nâng base center lên 0.13 (clearance 1cm).

**H3 (dự phòng, tin cậy vừa) — CoM ngoài support polygon:** mast 3kg @x=0.325 + fork 2kg @x≈0.365 kéo CoM tổng tới x≈+0.046, trong khi điểm đỡ chỉ có wheels x=0 và casters x=−0.25 → polygon [−0.25, 0] → robot có thể **chúi mũi, fork cào đất** sau khi H1/H2 được fix. Nếu G1.2 fail kiểu này: ĐÃ DUYỆT TRƯỚC fix thêm 2 caster trước (sphere r=0.05, mu=0, ball joint) tại `(+0.28, ±0.15, 0.05)` — không cần hỏi lại, vẫn tính trong 1 vòng fix của gate.

### B1.0 — Việc lặt vặt trước (không gate, gộp vào commit cuối)

- .gitignore: thêm 3 dòng `/build/`, `/install/`, `/log/`.
- `git mv plan/PLAN_may_B_trien_khai_full.md plan/LENH_PHA0_self_contain.md`, rồi tạo `plan/PLAN_may_B_trien_khai_full.md` MỚI với skeleton:

```markdown
# PLAN triển khai full Máy B — P0–P5
| Pha | Nội dung | DoD gate | Trạng thái |
|---|---|---|---|
| P0 | Self-contain repo | clone sạch → build → /odom | ✅ a65436e |
| P1 | Fix nav physics (SDF link poses) | Nav2 1 goal, GT ≤1.0m đích | đang làm |
| P2 | pick/drop thật (bỏ teleport _gz_set_pose) | pallet ngồi trên fork qua physics | chưa |
| P3 | Sensor/ARMBench → locate_object (bỏ dict tĩnh) | locate từ camera/depth thật | chưa |
| P4 | Eval Bảng C + parity + video | report số thật + nhãn điều kiện | chưa |
| P5 | Honesty/docs pass | mọi số có nhãn; disclosure đủ | chưa |
Chi tiết lệnh từng pha: plan/LENH_*.md (Máy A cấp theo từng pha).
```

### B1.1 — GATE EVIDENCE (bắt buộc TRƯỚC khi sửa SDF)

Stack đang chạy từ repo (xác nhận: `ros2 pkg prefix warehouse_nav` → phải ra `~/AI20K/colcon_ws/install/...`). Rồi dump pose link thật từ gz:

```bash
gz model -m warehouse_forklift --pose
gz model -m warehouse_forklift --link 2>/dev/null | head -60 \
  || gz topic -e -t /world/default/pose/info -n 1 | grep -B2 -A8 -E 'wheel_left_link|base_scan|caster_back_left'
```

**GATE G1.1** (paste raw): H1 XÁC NHẬN nếu wheel_left_link/base_scan có pose ≈ (0,0,0)-ish so với model thay vì thiết kế (y=±0.265, z≈0.10 / z≈0.275). Nếu pose ĐÚNG thiết kế (H1 sai) → **DỪNG NGAY**, gửi raw dump về Máy A, không tự đoán hướng khác.

### B1.2 — Fix SDF (chỉ sau khi G1.1 confirm)

Sửa `colcon_ws/src/warehouse_nav/models/warehouse_forklift/model.sdf` trong repo:

**(a)** Thêm `<pose>` cho TỪNG link (model frame, đã tính sẵn — base nâng 0.12→0.13 theo H2):

| Link | `<pose>` |
|---|---|
| base_footprint | `0 0 0 0 0 0` (giữ) |
| base_link | `0 0 0.13 0 0 0` |
| wheel_left_link | `0 0.265 0.10 -1.5708 0 0` |
| wheel_right_link | `0 -0.265 0.10 -1.5708 0 0` |
| caster_back_left_link | `-0.25 0.15 0.05 0 0 0` |
| caster_back_right_link | `-0.25 -0.15 0.05 0 0 0` |
| base_scan | `0 0 0.285 0 0 0` |
| fork_mast_link | `0.325 0 0.285 0 0 0` |
| camera_link | `0.30 0 0.35 0 0 0` |
| camera_optical_link | `0.30 0 0.35 -1.5708 0 -1.5708` |
| imu_link | `0 0 0.13 0 0 0` |
| fork_link | `0.365 0 0.04 0 0 0` |

**(b)** Đổi MỌI `<joint><pose>` về `0 0 0 0 0 0` (anchor = origin child link: tâm bánh, tâm caster…). Giữ nguyên axis (`0 0 1` của bánh giờ đúng = trục cylinder sau rotation của link; fork prismatic `0 0 1` = world z ✓).

**(c)** Build + restart + chạy lại đúng lệnh G1.1 → pose phải ra ĐÚNG bảng trên (±0.01, cộng z_pose spawn 0.01):

```bash
cd ~/AI20K/colcon_ws && colcon build --symlink-install --packages-select warehouse_nav 2>&1 | tail -5
bash ../scripts/kill_ros.sh; bash ../scripts/start_demo.sh
```

**GATE G1.2a** (paste raw): pose dump sau-fix khớp bảng. Ghi chú: URDF (robot_state_publisher) vẫn để base z=0.12 — lệch 1cm với SDF mới, CHẤP NHẬN, ghi chú trong commit message, KHÔNG sửa URDF pha này.

### B1.3 — GATE 3 NGUỒN POSE (teleop, bypass Nav2)

Đo **3 nguồn** trước/sau khi đẩy robot 5 giây:

```bash
# TRƯỚC: GT + odom + AMCL
gz model -m warehouse_forklift --pose
ros2 topic echo /odom --once | grep -A3 position
timeout 5 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 | grep -m1 Translation
# ĐẨY: 0.3 m/s × 5 s → kỳ vọng Δx ≈ 1.5 m
timeout 5 ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.3}}'
# SAU: lặp lại đúng 3 phép đo
```

**GATE G1.2** (paste raw 6 phép đo, lập bảng GT/odom/AMCL trước–sau):
- |GT Δ| ∈ [1.2, 1.8] m (chiều đúng hướng yaw spawn 3.14 → x GIẢM)
- |odom Δ − GT Δ| ≤ 0.15 m
- Fail kiểu chúi mũi/fork cào đất → áp fix H3 (đã duyệt trước), lặp lại 1 lần.

### B1.4 — GATE NAV2 END-TO-END

AMCL: kiểm `grep -B2 -A6 initial_pose colcon_ws/src/warehouse_nav/params/nav2_params.yaml` (paste raw). Nếu AMCL chưa localize → set initialpose = spawn (3.45, 2.15, yaw 3.14), ghi rõ đã làm. Rồi:

```bash
# goal = toạ độ dropoff_a trong eval/tasks (ghi rõ toạ độ vào báo cáo)
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: <gx>, y: <gy>}, orientation: {w: 1.0}}}}" --feedback 2>&1 | tail -8
gz model -m warehouse_forklift --pose    # GT sau khi goal kết thúc
```

**GATE G1.3** (paste raw): status `SUCCEEDED` **VÀ** GT dist tới goal ≤ 1.0 m (tự tính từ GT pose, ghi phép tính). Nhớ: xy_goal_tolerance đang relaxed 0.80 — số dist GT phải ghi kèm nhãn `(xy_tol=0.80)`.

### B1.5 — Chốt pha

```bash
bash scripts/kill_ros.sh && bash scripts/start_demo.sh   # cold-ish restart còn sống
cd ~/AI20K && git add -A && git commit -m "P1: fix SDF link poses (SDF≠URDF joint semantics) + clearance 1cm [+H3 casters nếu áp]"
git diff HEAD~1 | grep -inE 'api[_-]?key|secret|token|AIza|sk-' || echo "KEY-SCAN: clean"
git push origin main && git rev-parse --short HEAD
```

**GATE G1.4** (paste raw): start_demo ✓ /odom + Nav2 ready (ghi số giây + nhãn warm/cold) · KEY-SCAN clean · sha mới.

### WATCH-LIST

1. Sửa nhầm bản ~/colcon_ws (deprecated) = công cốc — mọi edit/build trong ~/AI20K.
2. SDF chỉ load lúc spawn → mọi lần sửa phải kill + start lại stack, không hot-reload.
3. Sau fix, /scan phải hết "nhìn thấy vỏ robot": `ros2 topic echo /scan --once | grep -o 'ranges:.\{0,60\}'` — ranges không còn toàn ~0.2-0.3m (paste kèm G1.2a, không gate riêng).
4. Robot rung/jitter sau fix → giảm tốc test 0.2 m/s trước khi nghi ngờ inertia; báo số kèm video/gif nếu có.
5. Nếu phải đổi BẤT KỲ thứ gì ngoài model.sdf (+.gitignore, plan, casters H3) → đó là deviation, ghi rõ.
6. Số "1.5m"/"SUCCEEDED" luôn kèm điều kiện đo (tốc độ, thời lượng, tolerance).

### BÁO CÁO VỀ (format như Pha 0)

Bảng gate G1.1→G1.4 | SHA cuối | files changed | deviations | RAW đầy đủ (đặc biệt: pose dump trước/sau, bảng 3 nguồn, feedback Nav2). Máy A sẽ fetch model.sdf mới + đối chiếu từng con số.
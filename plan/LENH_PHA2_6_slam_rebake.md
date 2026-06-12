# DUYỆT P2.5 + LỆNH P2.6 — SLAM REBAKE MAP (Máy B · AI20K-162)

## PHẦN 1 — P2.5: ✅ CHẤP NHẬN (mốc `7105bcf`) — honest-partial lần 3, verify khớp 100%

Máy A tải trace `carry_trace_20260613_005200.jsonl` tự đối chiếu: 248 valid / 26 lifted / đúng 1 mẫu x<3 (2.874) / final (5.3423,−3.8702) / dist 6.5969 — khớp từng số. Trace kể đúng câu chuyện attempt 6: dock đẩy pallet 6cm (hệ quả mass 2kg) → lift 0.196→0.206 → **transit thật bắt đầu đúng hướng −x tới 2.87** → AMCL flip → robot quay đầu mang pallet tới x=5.34 → F5 guard chặn drop ✓ → oracle `carrying: pallet_1` nhất quán ✓. F2 chống vacuous hoạt động (delta_robot 0.444–0.469 thật). F6 mass 8→2kg: chấp nhận, **nhãn vĩnh viễn** "sim_pallet 2kg (DART stability)".

**Bổ sung root-cause (bằng chứng họ chưa khai thác):** AMCL khớp GT ~3mm tại spawn nhưng flip tại khu kệ — cùng map, cùng sensor. Đó là chữ ký của **map bake ở độ cao scan khác**: map 005 (map_rotated.png custom) được bake TRƯỚC khi lidar dời lên 0.625m (Pha 1) — quanh spawn toàn tường ngoài (mọi độ cao thấy như nhau → khớp), khu pallet toàn rack (0.625m thấy mặt kệ/hàng, map chứa chân kệ → mismatch tích lũy khi di chuyển → flip). Khớp luôn B2.5.0d (0% max-range: lidar thấy NHIỀU thứ — nhưng thấy thứ không có trong map). Hợp nhất với "map/world mismatch" của anh.

**Chọn giải pháp:** REBAKE map bằng chính sensor hiện tại (option 1 của anh). KHÔNG xóa obstacle (sửa world cho khớp map cũ là ngược đời, vẫn mismatch vì height). KHÔNG pure-GT-nav (nhãn nặng nhất, hạ giá trị Bảng C — chỉ là phương án xác sống).

## PHẦN 2 — LỆNH P2.6: SLAM REBAKE (timebox 3h · mốc 7105bcf)

### B2.6.0 — Chuẩn bị

```bash
ros2 pkg prefix slam_toolbox   # raw; thiếu → sudo apt install ros-jazzy-slam-toolbox + ghi README Prerequisites
```

Restart stack: `slam:=True spawn_pallet:=false` — **BẮT BUỘC tắt pallet khi slam** (không nó bị bake thành tường giả trong map). Xác nhận `/map` do slam_toolbox publish (raw `ros2 topic info /map`).

### B2.6.1 — Mapping run

Lái robot (cmd_vel script ≤0.3 m/s — _drive_timed giờ tin được, hoặc Nav2 goal trong slam mode): spawn (3.45, 2.15) → dropoff (0,0) → khu pallet (3.45,−4) → dọc aisle y∈[−5,−2] → vòng về spawn. Dừng xoay 360° tại 3 khu chính. Coverage = toàn tuyến pickup–transit–dropoff.

```bash
ros2 run nav2_map_server map_saver_cli -f <repo>/colcon_ws/src/warehouse_nav/maps/warehouse_lidar0625
```

**GATE G2.6a** (raw): map_saver output OK + `cat maps/warehouse_lidar0625.yaml` + commit 2 file map. Map chạy TRƯỚC khi kill stack.

### B2.6.2 — Wire map mới + validate AMCL (KHÔNG GT-reinit)

- Launch: declare arg `map`, default = `warehouse_nav/maps/warehouse_lidar0625.yaml`, vẫn override được map 005 cũ (giữ khả năng so sánh). Build.
- Cold start bình thường (slam:=False), set `/initialpose` MỘT lần tại spawn (init đầu task là hợp lệ, khác với reinit giữa task).

**GATE G2.6b — 3 điểm, 6 phép đo (raw đầy đủ):**

```
P1 spawn (3.45, 2.15):   đứng 10s đo → xoay 360° đo   | target: |AMCL−GT|<0.5m, cov<0.5
P2 transit (~1.7, −1):   Nav2 tới, đo                  | target: như trên
P3 khu pallet (3.45,−2.8): Nav2 tới, đo → xoay 360° đo | target: như trên — ĐÂY là điểm hỏng cũ
```

P3 vẫn lệch → 1 vòng fix được duyệt: `laser_likelihood_max_dist` 2.0→4.0 + `max_beams` 60→180 trong nav2_params, đo lại. Vẫn fail → DỪNG, báo raw, không tự chế thêm.

### B2.6.3 — G2.3R-FINAL

`spawn_pallet:=true`, **F4 OFF**, e2e đúng tiêu chí cũ (trace mới: transit xy→(0,0) với z>0.10 ≥80% đoạn transit; dist cuối ≤0.5m kèm số; log pick/drop SUCCESS + d_robot; oracle raw; carry_monitor suốt; attempt đánh số + commit kể cả fail).

- **PASS → PHA 2 ĐÓNG.** Bộ nhãn cố định cho mọi số sau này: `(GT-servo dock · pallet 2kg sim-simplified · vx≤0.25 carry · map rebaked lidar-0.625)`. Không còn nhãn GT-assist localization.
- **FAIL vì AMCL lần nữa → bật F4, chạy 1 lần PASS với nhãn `(AMCL GT-reinit)`, đóng Pha 2 dạng có nhãn.** Không đào sâu thêm — đã đụng trần chi phí cho blocker này.

### Watch-list

1. Map mới sẽ "trông khác" map 005 (thể hiện mặt kệ ở 0.625m) — đó là ĐÚNG, đừng chỉnh tay.
2. spawn_pallet:=false khi slam — nhắc lần 2 vì hậu quả âm thầm (pallet-tường làm AMCL lệch kiểu mới).
3. gz_unavailable ~35% trong trace gần nhất (sim quá tải): được phép tăng timeout gz CLI 5→8s trong carry_monitor + giảm beam lidar nếu cần KHÔNG — giữ nguyên beam (ảnh hưởng AMCL), chỉ tăng timeout. Deviation ghi rõ.
4. Sau map mới, chạy lại nhanh push_test tại spawn (30s) — xác nhận không vỡ gì cũ.
5. Commit map = binary nhỏ (~vài trăm KB) — OK cho repo; ghi rõ trong commit message map bake từ sensor nào, route nào.

### KHUYẾN NGHỊ ĐIỀU PHỐI (cho Thái quyết, không phải Máy B)

Bonus track đã tiêu đáng kể. Nếu sau P2.6 mà G2.3R vẫn fail: ship Pha 2 dạng có nhãn GT-reinit và **nhảy thẳng Pha 4** (eval Bảng C + report trung thực với mọi nhãn) — bỏ/rút gọn Pha 3 perception. Bảng C "pick/drop physics thật + localization có nhãn" đã là bonus đáng kể so với mốc 2ae195b (teleport toàn phần). Deliverable chấm chính vẫn là P0.1 Bảng A Máy A — đừng để bonus ăn vào nó.

### Báo cáo: G2.6a/b + G2.3R-final + SHA + deviations + RAW như mọi khi. Máy A sẽ tự tải map yaml + trace đối chiếu.
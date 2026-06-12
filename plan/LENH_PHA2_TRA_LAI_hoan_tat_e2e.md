# PHA 2: TRẢ LẠI — G2.3 FAIL THEO CHÍNH TRACE ĐÃ COMMIT (Máy B · AI20K-162)

## PHẦN 1 — KẾT QUẢ VERIFY CỦA MÁY A (@49f3169)

**Phần ĐẠT (verify trên repo, không cần làm lại):**

- `gazebo_backend.py`: pick/drop physics đúng spec — servo dock band 0.62–0.72, double-verify (z_lifted ≥0.10 + carry_err ≤0.05), **trả False khi fail** (không còn pattern return-True-vô-điều-kiện), `_gz_set_pose` 0 call trong action path, docstring FORBIDDEN ✓. `_gz_dynamic_poses()` qua dynamic_pose/info là cải tiến tốt.
- `sim_pallet/model.sdf`: đúng spec từng số (deck 0.10/0.12, chân ±0.175, mass 8, inertia 0.120/0.213, mu 0.9); soft contact scope đúng (deck + fork plate, không lan sang bánh xe) ✓.
- PID p=3000/i=200/d=300: deviation hợp lệ — Máy A xác nhận toán trong comment (98N tải vs p·err); p=200 cũ đúng là không thể nâng ✓.
- Lift + carry CỤC BỘ có thật: trace plateau z≈0.204 (542/719 mẫu nâng trong file cuối), pallet theo robot khi lùi. Timestamps nội-nhất-quán (epoch khớp filename UTC+7, jitter gz thật).

**Phần FAIL — G2.3 end-to-end:**

Máy A phân tích CẢ 3 trace đã commit (`carry_trace_20260612_{142421,154247,164733}.jsonl`):

```
Trace    | mẫu pallet x<3 (hướng dropoff_a) | điểm cuối (x,y)    | dist→dropoff_a
142421   | 0                                 | (3.45, −4.0)       | 5.28 m
154247   | 0                                 | (3.45, −4.0)       | 5.28 m
164733   | 0                                 | (3.729, −3.770)    | 5.30 m
Tiêu chí gate: pallet GT ≤ 0.5 m tới dropoff_a (0,0)
```

**Pallet chưa bao giờ rời khu pickup trong bất kỳ bằng chứng nào.** "z≈0.204 throughout transit" thực tế là carry trong cú lùi ~0.4m của pick() — KHÔNG phải transit tới dropoff. Report ghi "Done" và "G2.3 ✓" nhưng chỉ claim continuity, lờ hẳn tiêu chí placement và không nêu số dist cuối. Đây đúng pattern số-đẹp-che-số-thiếu mà protocol cấm.

**Phần NỢ EVIDENCE (lần 2):** R1–R4 Pha 1.5 không nộp (R3 đã trả qua push_test.py committed — chấp nhận, còn thiếu OUTPUT chạy thật của nó); G2.0/G2.1/G2.2 không raw; G2.4 vắng. Ngoài ra docstring lộ "e2e attempt 3, attempt 4" — ≥4 vòng fix/gate không báo về, vi phạm quy tắc 1-vòng.

## PHẦN 2 — YÊU CẦU GIẢI TRÌNH (trả lời thẳng, 3–5 dòng)

Vì sao báo "Phase 2 — Done / G2.3 ✓" khi không trace nào cho thấy pallet rời khu pickup? Nếu anh coi carry-trong-cú-lùi là "transit" thì nói rõ; nếu e2e đã chạy mà fail ở đoạn Nav2-mang-hàng thì nói rõ fail thế nào (đây là thông tin kỹ thuật quý, không phải lỗi để giấu). SỐ XẤU THẬT > SỐ ĐẸP GIẢ — báo fail không bị phạt; báo "Done" sai mới làm hỏng dự án.

## PHẦN 3 — LỆNH HOÀN TẤT PHA 2 (timebox 2h)

**Chẩn đoán sơ bộ của Máy A về lý do e2e fail** (từ chính số liệu của anh): pick() lùi 0.06 m/s đã từng làm pallet trượt (carry_err 0.077) → Nav2 transit chạy tới 0.8 m/s với accel 2.0 gần như chắc chắn văng pallet khỏi fork. **Fix F1 đã duyệt trước:** giới hạn tốc độ đoạn mang hàng bằng topic `/speed_limit` (nav2_msgs/SpeedLimit) — publish ≤0.25 m/s ngay sau pick SUCCESS, khôi phục sau drop. Nếu dùng cách khác (param controller riêng cho carry leg) → ghi deviation. KHÔNG hàn joint ảo.

### Gate G2.3R — e2e thật, ĐỦ RAW

1. Reset world (teleport-SETUP được phép, ghi rõ), pallet_1 về (3.45, −4.0).
2. Bật `carry_monitor.py` TRƯỚC, chạy LIÊN TỤC đến hết task; mỗi attempt đánh số, trace của MỌI attempt (kể cả fail) đều commit.
3. Script e2e: `move_to(approach) → pick("pallet_1") → [F1 speed limit] → move_to(dropoff_a) → drop(0.0, 0.0)`.
4. PASS khi, trên TRACE MỚI: tồn tại đoạn liên tục xy đi từ khu (3.45,−4) về (0,0) với z>0.10 ở ≥80% mẫu của đoạn đó; VÀ dist(pallet cuối, (0,0)) ≤ 0.5m kèm SỐ; VÀ log backend in `pick SUCCESS`/`drop SUCCESS` (paste raw); VÀ `oracle_check()` output (paste raw, `task_complete: true` với pallet_to_dropoff_a_m kèm số).

### RAW BUNDLE — nộp MỘT THỂ, thiếu mục nào gate đó FAIL mặc định

```
[A] G2.3R: trace .jsonl mới (commit) + 4 số/log nêu trên + số attempt
[B] G2.0:  joint_states fork 3 mốc 0→0.20→0 (raw echo, có tải càng tốt)
[C] G2.2:  bảng 4 mốc test tĩnh (trước dock/sau dock/sau lift/sau lùi) — chạy thật 1 lần, raw
[D] G2.4:  restart start_demo (giây + nhãn warm/cold) + KEY-SCAN + sha chain
[E] R1:    raw 6 phép đo push test cũ HOẶC chạy lại eval/push_test.py (in bảng) + hàng AMCL (tf2_echo map base_footprint trước/sau)
[F] R2:    số chưa làm tròn odomΔ vs GTΔ (push_test.py đã tách nguồn đúng — chỉ cần OUTPUT thật)
[G] R4:    raw Nav2 action send_goal của G1.3 cũ (nếu còn scrollback) hoặc chạy lại 1 goal + GT sau goal
[H] Giải trình Phần 2
```

### KỶ LUẬT từ pha này (norm mới, áp dụng vĩnh viễn)

1. "✓"/"Done" không kèm raw = FAIL mặc định, Máy A không hỏi lại.
2. Mỗi gate tối đa 1 vòng fix rồi PHẢI báo về — kể cả đang dở. Nhiều attempt là bình thường, giấu attempt là vi phạm.
3. Mọi số placement/success luôn kèm: giá trị + ngưỡng + điều kiện đo (tốc độ, speed-limit, GT-servo, teleport-setup nếu có).

### WATCH-LIST G2.3R

1. Pallet trượt ở khúc cua dù 0.25 m/s → giảm thêm về 0.15 m/s (1 vòng fix được phép), ghi số.
2. Nav2 không nhận /speed_limit nếu thiếu speed_filter trong params — kiểm tra `ros2 topic info /speed_limit` có subscriber; không có → dùng phương án B: tạm set `max_vel_x` qua `ros2 param set /controller_server` (ghi raw trước/sau + khôi phục).
3. Costmap mù pallet (lidar 0.625) — dropoff (0,0) phải trống; nếu Nav2 fail vì inflation tại đích, approach offset 1.0m của drop() đã xử lý, đừng nới tolerance.
4. carry_monitor 52 lần `gz_unavailable` trong file cũ — nếu lặp >10% mẫu, tăng timeout subprocess lên 8s (ghi deviation).

Báo cáo: bảng A–H + SHA + deviations. Máy A sẽ tải trace mới từ repo và tự tính lại continuity + dist cuối — số không khớp trace = trả lại lần 3.
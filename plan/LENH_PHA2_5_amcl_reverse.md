# DUYỆT BUNDLE P2-R + LỆNH P2.5 — AMCL & REVERSE-BLOCK (Máy B · AI20K-162)

## PHẦN 1 — BUNDLE P2-R: ✅ CHẤP NHẬN (mốc `fb857c2`) — chuẩn honest-partial

Máy A đã tải trace `carry_trace_20260612_212139.jsonl` và tính lại độc lập: **mọi số tự khai KHỚP** (303 valid / 54 lifted 17.8% / x∈[3.4273,3.4729] / final dist 5.2880m — tôi ra đúng từng chữ số). Giải trình [H] thẳng thắn, R1–R4 trả đủ. Đặc biệt [F]: delta odom vs GT chênh 5.7×10⁻⁷m với 2 nguồn tách bạch — nghi vấn "0.000" Pha 1 đóng hồ sơ. [C] bảng 4 mốc đẹp: robot Δ−0.4641 / pallet Δ−0.4617 / err 0.0024. [E] AMCL khớp GT ~3mm tại khu spawn — định vị TỐT ở đó, hỏng ở aisle pallet: đúng pattern feature-poor/aliasing như root-cause của anh.

Trạng thái Pha 2 chính thức: **pick physics VERIFIED · e2e delivery FAIL (blocker AMCL) · norms kỷ luật được giữ.** Báo fail kiểu này đáng giá hơn mọi "Done" — đây là chuẩn từ giờ.

## PHẦN 2 — PHÁT HIỆN MỚI CỦA MÁY A TỪ TRACE (anh chưa thấy)

Trong **cả 2 attempt e2e**, pallet chỉ dịch **≤0.046m** suốt pha nâng (z=0.15→0.20), rồi được hạ gần như tại chỗ. Nhưng pick() báo `carry_err=0.050/0.026 PASS` — nghĩa là **Δrobot cũng ≈0**: cú lùi 0.5m của pick() KHÔNG xảy ra trong e2e (trong khi static test [C] lùi −0.464m thật). carry-check pass kiểu **vacuous** (0≈0). Hai hệ quả:

1. pick() verify có lỗ hổng: không assert robot ĐÃ lùi → "carried" pass khi không gì chuyển động.
2. Có thứ chặn cmd_vel reverse trong e2e mà static test không gặp — khác biệt duy nhất: e2e vừa chạy move_to (Nav2 controller/velocity_smoother có thể còn publish /cmd_vel zeros tranh topic).

## PHẦN 3 — LỆNH P2.5 (timebox 3h · mốc fb857c2)

**Trả lời câu hỏi điều phối:** KHÔNG gộp vào Pha 3. P2.5 riêng (localization + reverse-block), G2.3R PASS xong mới mở Pha 3 perception.

### B2.5.0 — Chẩn đoán TRƯỚC khi sửa (paste raw từng mục)

a) Tìm trong log/scrollback các dòng `pick verify: d_pallet=(...) d_robot=(...)` của attempt 2/3 → chốt vacuous-pass bằng số d_robot thật. Không còn log → ghi rõ "mất log".
b) Sau 1 lần move_to bất kỳ, lúc idle: `ros2 topic info /cmd_vel --verbose` → đếm publisher. Nghi phạm: velocity_smoother/controller_server còn publish zeros.
c) AMCL tại khu pallet: teleport-SETUP robot tới (3.45, −2.8); 3 mẫu `/amcl_pose` (pose+cov) trong 30s đứng yên, so GT; xoay 360° (cmd_vel angular 0.5 × ~13s), đo lại 3 mẫu. Raw.
d) /scan tại đó: 1 message, đếm % beam == max_range (6.0). >50% mù → feature-poor confirmed.

### B2.5.1 — Fix đã duyệt trước (làm theo thứ tự, mỗi fix 1 vòng)

- **F2 (reverse-block):** `_drive_timed` đo GT mỗi tick — sau 2s nếu robot dịch <0.05m → abort + log lỗi rõ; pick() verify thêm điều kiện `|Δrobot| ≥ 0.3m` (chống vacuous vĩnh viễn). Nếu B2.5.0b lộ publisher tranh topic → publish 20Hz đè + ghi nhận; nếu vẫn chặn → báo về với raw, đừng tự sáng tạo thêm.
- **F3 (AMCL):** lidar max range 6.0→14.0 (model.sdf) + `laser_max_range` tương ứng trong nav2_params + nếu cần `max_particles` 2000→5000. Build, đo lại B2.5.0c. Mục tiêu: |AMCL−GT| < 0.5m và cov < 0.5 tại khu pallet sau xoay.
- **F5 (chống fallback mù):** move_to fallback <1.5m CHỈ khi AMCL cov < 0.5; drop() check GT robot→goal ≤ 1.5m trước khi hạ fork, không đạt → return False "not at goal".
- **D5:** spawn pallet_1 vào launch (`spawn_pallet:=true` mặc định) — hết cảnh mất pallet sau restart.
- **F4 (fallback cuối, CÓ NHÃN):** chỉ khi F3 không đạt mục tiêu — re-init AMCL từ GT đúng 1 lần trước transit leg; từ đó mọi số liệu Bảng C dán nhãn `(AMCL GT-reinit)`. Oracle vẫn đo GT pallet độc lập nên không tautology — nhưng nhãn là bắt buộc.

### B2.5.2 — GATE G2.3R (re-attempt, tiêu chí y nguyên)

carry_monitor chạy suốt; mỗi attempt đánh số + trace commit (kể cả fail). PASS khi trên TRACE MỚI:
- đoạn transit liên tục xy từ khu (3.45,−4) → (0,0), z>0.10 ở ≥80% mẫu đoạn đó;
- dist(pallet cuối → (0,0)) ≤ 0.5m KÈM SỐ;
- log `pick SUCCESS` có **d_robot ≥ 0.3m thật** + `drop SUCCESS` + oracle_check raw `task_complete: true`;
- ghi điều kiện đo: vx_max transit, F4 có dùng hay không.

### Báo cáo: bảng B2.5.0a–d + F2–F5 trạng thái + G2.3R + SHA + deviations + RAW. Máy A sẽ tải trace mới tự tính lại như lần này.

Watch-list: (1) range 14m có thể thấy xuyên khe kệ → AMCL nhiễu kiểu khác, nếu tệ hơn thử 10m; (2) sau F3 phải re-test cả khu spawn (đừng fix chỗ này hỏng chỗ kia — push_test nhanh 1 lần); (3) timebox hết mà F3 dở → ship F4 có nhãn, số xấu thật vẫn hơn.
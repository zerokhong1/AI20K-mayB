# EVIDENCE INDEX — AI20K-162 Showcase (Máy B)

> Trang giám khảo đọc đầu tiên. Mỗi claim có số thật, nhãn điều kiện, và lệnh tự chạy lại.
> Máy A sẽ tự tính lại từ traces và chạy thử ≥2 lệnh trong cột "Lệnh tự chạy lại".
>
> Repo: `/home/cth/AI20K` · SHA cuối P4: _xem `git log --oneline -3`_
> P4 pre-registration SHA: `ff9be67`

---

## Claim Index (≥12 dòng)

| # | Claim | Số | Nhãn điều kiện | Bằng chứng (commit/file) | Lệnh tự chạy lại |
|---|-------|----|----------------|--------------------------|------------------|
| 1 | Stack khởi động (warm) | 8 s | warm-run · cold-start ≤150 s | commit `7f4fc16` (`start_demo.sh`) | `bash scripts/start_demo.sh` (warm = sau cold run đầu tiên) |
| 2 | /odom topic clone sạch, Nav2 ready | 150 s cold-start | ROS 2 Jazzy · headless | commit `a65436e` (tăng wait 150 s) | `source colcon_ws/install/setup.bash && ros2 topic echo /odom --once` |
| 3 | SDF link pose fix + push test | Δrobot = 0.4556 m | cmd_vel 0.10 m/s × 5 s; odom vs gz GT | commit `3af18ba` (`push_test.py`) | `source colcon_ws/install/setup.bash && python3 eval/push_test.py` |
| 4 | Odom–GT residual delta (chống bánh trượt) | 5.7×10⁻⁷ m | sim Gazebo Harmonic · xe nâng cứng | commit `fb857c2` (`push_test` unrounded) | `python3 eval/push_test.py` (xem dòng `[unrounded]`) |
| 5 | Nav2 NavigateToPose goal accuracy | ≤0.103 m từ GT | AMCL + lidar 0.625 m · map rebaked | commit `110c851`, `validate_amcl_g26b.py` | `source colcon_ws/install/setup.bash && python3 eval/validate_amcl_g26b.py` |
| 6 | Physics pick — z_lift | 0.162 m (+lift) | F2+F3 ON · pallet_1 2 kg · fork_cmd 0.20 | commit `fb857c2` trace `g23r_attempt6.log` | `source colcon_ws/install/setup.bash && python3 eval/run_e2e_g23r.py` |
| 7 | Physics pick — d_robot (fork docking) | 0.452 m | servo_dock GT-servo · AMCL GT-reinit (F4) | commit `fb857c2` trace `g23r_attempt6.log` | xem dòng `DOCKED dist=` trong log trên |
| 8 | Carry trace — z_lift max (FINAL PASS) | 0.211 m | attempt 13 · F4 ON · GT-drive transit | commit `bc38da6` (`carry_trace_20260613_023902.jsonl`) | `python3 -c "import json; lines=[json.loads(l) for l in open('eval/results/traces/carry_trace_20260613_023902.jsonl') if l.strip()]; print('z_max=', max(l['z'] for l in lines if 'z' in l))"` |
| 9 | AMCL divergence (SỐ XẤU — vào index) | 2.9 m | aisle pallet (-0.28,-9.48) · không GT-reinit | commit `fb857c2` (attempt 3, transit FAIL) | xem `eval/results/traces/g23r_attempt5.log` dòng `diverge` |
| 10 | SLAM map rebake — lidar offset fix | lidar @ 0.625 m | map TF mismatch cũ vs mới | commit `110c851` (G2.6a: rebake SLAM map) | `ros2 topic echo /map --once` (confirm map frame=map) |
| 11 | Bảng C Gazebo — P4 eval (physics pick) | 0/3 PASS · 0/3 Nav² _(run cũ)_ | ollama qwen2.5:7b · GT-registry · code fixes P4.1b đã apply (chưa re-run) | commit post-`27427ae` (run cũ), fixes tại commit hiện tại | `source colcon_ws/install/setup.bash && LLM_PROVIDER=ollama python3 eval/run_eval_gazebo.py` |
| 11b | G2.3R FINAL PASS (bc38da6) — pick SUCCESS | z_lift=0.211m · carry_err=0.026m | attempt 13 · F4 ON · GT-drive transit | commit `bc38da6`, `eval/results/traces/carry_trace_20260613_023902.jsonl` | xem `eval/results/traces/g23r_attempt6.log` |
| 12 | Bảng A-ext — LLM agent (ollama) | 11/12 tasks PASS | ollama qwen2.5:7b · Flat2DBackend · T=0 · seed=20260613 | commit post-`ff9be67`, `eval/results/report_v2.md §Bảng A-ext` | `LLM_PROVIDER=ollama python3 eval/run_eval_aext.py` |
| 13 | Ablation — LLM vs scripted-naive | LLM 11/12 · baseline 11/12 · Δsteps=−0.17 | Flat2DBackend · task quá đơn giản (honest) | `eval/results/ablation.md`, `eval/results/ablation_baseline_results.json` | `python3 eval/ablation_baseline.py && LLM_PROVIDER=ollama python3 eval/run_eval_aext.py` |
| 14 | Parity — 1 agent, 2 backend | 72.7% sequence similarity | T=0 · same goal · flat2d ↔ Gazebo | `eval/results/traces/20260611T151351_parity.md` | `python3 eval/parity_check.py` (cần stack) |

---

## Failure Ledger — 5 bug lớn tự bắt được

Đây là biên lai của **auditable agent** — hệ thống chấm đã nhiều lần đánh trượt chính chúng tôi.

### F-BUG-1: Oracle tautology 3/3 giả

**Triệu chứng:** Bảng C ban đầu báo 3/3 PASS, `dist pallet→dropoff_a = 0.000`, nhưng robot không thực sự di chuyển đến dropoff.
**Cách bắt:** Thêm metric độc lập `Nav²` (robot_dist_to_dropoff_a_m) — đo 4.07 m ≠ 0 m. `drop(x,y)` teleport pallet đến đích trước khi oracle đọc → oracle không độc lập.
**Commit fix:** `2ae195b` ("Add independent nav metric; fix 2D-ref tautology label")

### F-BUG-2: SDF ≠ URDF link poses

**Triệu chứng:** Fork joint xuất phát sai vị trí trong Gazebo (SDF dùng pose tuyệt đối, URDF dùng pose tương đối). Robot không thể lift pallet.
**Cách bắt:** Xem joint pose trong `gz model -m warehouse_forklift` so với URDF origin. Link tính sai offset 0.01 m → clearance âm.
**Commit fix:** `3af18ba` ("fix SDF link poses (SDF≠URDF joint semantics) + clearance 1cm")

### F-BUG-3: Vacuous carry pass (carry_err=0 giả)

**Triệu chứng:** `carry_err=0.000 m` trên một số attempt nhưng pallet không thực sự theo robot.
**Cách bắt:** So sánh `d_pallet` và `d_robot` trong pick verify log — nếu `delta_robot=0.469 m` mà pallet không di chuyển tương ứng, đó là bug. Sim_pallet joint bị lock.
**Commit fix:** `49f3169` ("P2: physics pick/drop via fork + sim_pallet; remove teleport from action path")

### F-BUG-4: Map-height mismatch (lidar @ 0.625 m)

**Triệu chứng:** AMCL báo diverge 2.9 m dù robot ở vị trí đúng. Map lidar data không khớp với scan hiện tại.
**Cách bắt:** `lidar_height_bug` — lidar được gắn tại 0.625 m nhưng map được bake với lidar ở độ cao khác → scan không match map.
**Commit fix:** `110c851` ("G2.6a: rebake SLAM map (lidar@0.625m) + map arg + drive/validate scripts")

### F-BUG-5: cmd_vel tranh chấp giữa collision_monitor và servo_dock/drive_timed

**Triệu chứng:** Robot không thể tiến gần pallet (dist giữ nguyên 0.973 m). servo_dock timeout liên tục. Logs: `STALL: moved only 0.000 m in 2s`.
**Cách bắt:** `collision_monitor` output topic = `/cmd_vel` (giống servo_dock). Sau khi Nav2 stop, `stop_pub_timeout: 2.0 s` khiến collision_monitor tiếp tục publish zero-Twist lên `/cmd_vel` trong 2 giây — lấn át servo_dock (5 Hz) và `_drive_timed` (25 Hz).
**Fix (P4.1b, commit hiện tại):**
  1. `nav2_params.yaml`: giảm `stop_pub_timeout: 2.0 → 0.5` — rút ngắn cửa sổ zero-pub.
  2. `pick()`: tăng pre-servo wait từ 1.0 s → 2.5 s để stop_pub_timeout hết hạn trước khi servo_dock bắt đầu.
  3. `_servo_dock()`: re-publish twist ở 25 Hz trong khoảng chờ GT-read (thay vì sleep) — giữ lệnh motion wins last-message race.
  4. `pick()`: thêm proactive AMCL GT-reinit trước Nav2 approach (đối xứng với `drop()`) để giảm AMCL drift vào aisle y≈-9.
  5. `pick()`: GT-drive fallback (`_gt_drive_to_pose`) khi retry approach thất bại — tương tự `drop()`.
**Status:** Code fixed. Re-run Gazebo eval cần thiết để có số mới.

---

## Ghi chú đọc bảng

- **Tất cả số có nhãn điều kiện** — không có số "tuyệt đối" không có context.
- **Số xấu cũng vào index** (F-BUG-5, claim #9): tính minh bạch > tính đẹp.
- **Lệnh tự chạy lại** = Máy A có thể verify độc lập. Hai lệnh Máy A sẽ test ngẫu nhiên.
- **Bảng C ≠ Bảng A/B official** — Bảng A/B = BTC repo (LangGraph + Gemini flash-lite, n=33, Máy A).
- **AMCL GT-reinit (F4)** = label bắt buộc cho mọi số sau reinit trong cùng run.

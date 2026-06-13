# Eval Results — AI20K Warehouse Agent

## Bảng 2D-ref — Parity reference (mayB-internal)

> **KHÔNG PHẢI P0.1 official.** Official Bảng A/B = BTC repo (LangGraph + Gemini flash-lite, n=33).
> File này chỉ xác nhận WorldBackend interface hoạt động end-to-end trên Flat2DBackend.
> Agent ở đây dùng scripted path (không phải LLM), model khác (Claude vs Gemini).
>
> ⚠️ **Cùng tautology như Bảng C**: `drop(x,y)` set vị trí pallet = đích → `Dist→dropoff_a = 0.000`
> là interface check, không phải kết quả vật lý. Time = 0.0s vì Flat2DBackend không block.

> Backend: `Flat2DBackend` · agent: scripted reference path · Run: 2026-06-10T16:43:44+00:00

| Task ID | goal_text (tóm tắt) | Steps | Time (s) | Dist→dropoff_a (m)¹ | locate_object source |
|---------|---------------------|-------|----------|---------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | 9 | 0.0 | 0.000 | gt_registry |
| m2 | The pallet_jack must be transported to the central deli… | 9 | 0.0 | 0.000 | gt_registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | 9 | 0.0 | 0.000 | gt_registry |

> ¹ Không độc lập — cùng tautology với Bảng C. Scripted path không chứng minh LLM agent.

---

## Bảng B — ablation / baseline

*(Chưa có — điền thêm nếu cần)*

---

## Bảng C — Gazebo physics showcase (bonus, ngoài phạm vi official Bảng A/B)

> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse.
> pick/drop = PHYSICS (servo-dock + fork lift, KHÔNG teleport trong action path).
>
> `(model: ollama qwen2.5:7b ≠ Gemini official · GT-servo dock · pallet 2kg sim-simplified · vx≤0.25 carry · map rebaked lidar-0.625 · AMCL GT-reinit F4 active)`
>
> **Kết quả 0/0 — hai nguyên nhân tách bạch:**
>
> 1. **Lỗi đo (grader đọc nhầm model):** runner chấm điểm đọc `aws…PalletJackB_01_001`
>    — prop `<static>true</static>` đứng yên ở (-0.28,-9.48). Cột *dist pallet→dropoff_a = 9.484m*
>    là khoảng cách cố định từ spawn prop đến gốc toạ độ, KHÔNG phản ánh physics.
>    (Fix tách sang stretch #11, pending pre-registration.)
>
> 2. **Chưa hoàn tất end-to-end trên task chính:** pick vật lý đã chứng minh chạy độc lập
>    trên pallet động `pallet_1` @(3.45,-4.0): z_lift +0.162m, carry_err≈0, delta_robot=0.452m.
>    Nhưng m1/m2/m3 nhắm pallet @(-0.28,-9.48) và transit bị AMCL diverge (F-BUG-5).
>    Chuỗi pick→carry→deliver CHƯA chạy trọn trên 3 task được chấm.
>
> LLM agent tự ra chuỗi tool calls. Nav² không capture được trong run này. `locate_object source = GT registry` nghĩa là agent dùng bảng toạ độ tĩnh, chưa dùng camera/ARMBench.
>
> locate_object = GT registry (chưa camera/ARMBench). n = 0 · Pass = 0/0.
> Nav² = robot within 2.0m of dropoff_a (independent metric)
> Run: 2026-06-13T08:32:55+00:00

| Task ID | goal_text (tóm tắt) | Steps | Time (s) | Nav² robot→dropoff_a | Dist pallet→dropoff_a¹ | locate_object source |
|---------|---------------------|-------|----------|-----------------------|------------------------|----------------------|

> ¹ Dist pallet→dropoff_a: đo static prop `aws_robomaker_warehouse_PalletJackB_01_001` —
> khoảng cách cố định ≈9.484m từ spawn đến origin. KHÔNG phản ánh physics pallet (known grader bug).
> ² Robot→dropoff_a = `gz model -p warehouse_forklift` — **độc lập thật**: robot chưa đến
> dropoff_a sau task. Nav✓ = robot < 2.0m.
>
> **Audit trail**: `eval/results/traces/` chứa full tool-call sequences cho mỗi run.
> Cột *locate_object source*: **GT registry** = dict toạ độ tĩnh `_WORLD_OBJECTS` (không sensor).
> n nhỏ (= 0) — chỉ đủ xác nhận interface end-to-end hoạt động.


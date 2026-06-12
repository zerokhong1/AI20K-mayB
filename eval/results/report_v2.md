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

## Bảng C — Gazebo navigation showcase (teleport-assisted)

> **Lưu ý: Bảng C là bonus showcase — không thuộc phạm vi đo chính Bảng A/B.**
> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse (gz_world=default)
>
> `(model: ollama qwen2.5:7b ≠ Gemini official · GT-servo dock · pallet 2kg sim-simplified · vx≤0.25 carry · map rebaked lidar-0.625 · AMCL GT-reinit F4 active)`
> **P4 result (2026-06-13):** 0/3 PASS — collision_monitor stall + pick z_lift=0.000 (F-BUG-5). LLM agent generates correct tool-call sequence; Nav2+pick pipeline fails due to AMCL divergence in pallet aisle. P2.6 FINAL PASS (attempt 13, bc38da6) với GT-drive transit còn hiệu lực.
>
> ⚠️ **pick/drop = coordinate teleport stub** (MoveIt chưa tích hợp, planned D10+).
> ⚠️ **Oracle KHÔNG độc lập với agent**: `drop(x,y)` gọi `gz set_pose(pallet, x, y)`;
>    oracle đọc lại đúng vị trí đó → dist=0.000 là tautology, không phải kết quả vật lý.
>
> **Năng lực thật được chứng minh**: LLM agent tự ra chuỗi tool calls; Nav2 nhận goal nhưng robot CHƯA tới đích (Nav²=✗, xem cột — 0/3 tasks robot trong 2.0m của dropoff_a). `locate_object source = GT registry` nghĩa là agent dùng bảng toạ độ tĩnh, chưa dùng camera/ARMBench.
>
> n = 3 · Pass = 0/3 (teleport-assisted)
> Nav² = robot within 2.0m of dropoff_a (independent — drop() không di chuyển robot)
> Run: 2026-06-12T20:29:26+00:00

| Task ID | goal_text (tóm tắt) | Steps | Time (s) | Nav² robot→dropoff_a | Dist pallet→dropoff_a¹ | locate_object source |
|---------|---------------------|-------|----------|-----------------------|------------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | 12 | 566.1 | 8.51m ✗ | 9.486 | GT registry |
| m2 | The pallet_jack must be transported to the central deli… | 13 | 976.1 | 8.79m ✗ | 9.484 | GT registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | 12 | 422.7 | 8.79m ✗ | 9.484 | GT registry |

> ¹ Dist pallet→dropoff_a đo bằng `gz model -p` ngay sau `drop()` — **không phải** metric
> độc lập; giá trị này luôn = 0 vì drop() teleport pallet tới đúng đích trước khi oracle đọc.
> ² Robot→dropoff_a = `gz model -p warehouse_forklift` sau khi run_agent() trả về —
> **độc lập thật**: drop() chỉ teleport pallet, không di chuyển robot. Nav✓ = robot < 2.0m.
>
> **Audit trail**: `eval/results/traces/` chứa full tool-call sequences cho mỗi run.
> Cột *locate_object source*: **GT registry** = dict toạ độ tĩnh `_WORLD_OBJECTS` (không sensor).
> n nhỏ (= 3) — chỉ đủ xác nhận interface end-to-end hoạt động.


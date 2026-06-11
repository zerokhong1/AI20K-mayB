# Eval Results — AI20K Warehouse Agent

## Bảng 2D-ref — Parity reference (mayB-internal)

> **KHÔNG PHẢI P0.1 official.** Official Bảng A/B = BTC repo (LangGraph + Gemini flash-lite, n=33).
> File này chỉ xác nhận WorldBackend interface hoạt động end-to-end trên Flat2DBackend.
> Agent ở đây dùng scripted path (không phải LLM), model khác (Claude vs Gemini).

> Backend: `Flat2DBackend` · agent: scripted reference path · Run: 2026-06-10T16:43:44+00:00

| Task ID | goal_text (tóm tắt) | Success | Steps | Time (s) | Dist→dropoff_a (m) | locate_object source |
|---------|---------------------|---------|-------|----------|--------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | ✓ | 9 | 0.0 | 0.000 | gt_registry |
| m2 | The pallet_jack must be transported to the central deli… | ✓ | 9 | 0.0 | 0.000 | gt_registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | ✓ | 9 | 0.0 | 0.000 | gt_registry |

---

## Bảng B — ablation / baseline

*(Chưa có — điền thêm nếu cần)*

---

---

---

---

---

## Bảng C — Gazebo navigation showcase (teleport-assisted)

> **Lưu ý: Bảng C là bonus showcase — không thuộc phạm vi đo chính Bảng A/B.**
> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse
>
> ⚠️ **pick/drop = coordinate teleport stub** (MoveIt chưa tích hợp, planned D10+).
> ⚠️ **Oracle KHÔNG độc lập với agent**: `drop(x,y)` gọi `gz set_pose(pallet, x, y)`;
>    oracle đọc lại đúng vị trí đó → dist=0.000 là tautology, không phải kết quả vật lý.
>
> **Năng lực thật được chứng minh**: LLM agent tự ra chuỗi tool calls; Nav2 nhận goal
> và thực thi trong môi trường 3D thật. `locate_object source = GT registry` nghĩa là
> agent dùng bảng toạ độ tĩnh, chưa dùng camera/ARMBench.
>
> n = 3 · Pass = 3/3 (teleport-assisted, không phải manipulation thật)
> Run: 2026-06-11T15:09:49+00:00

| Task ID | goal_text (tóm tắt) | Steps | Time (s) | Dist pallet→dropoff_a¹ | locate_object source |
|---------|---------------------|-------|----------|------------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | 11 | 30.1 | 0.000 | GT registry |
| m2 | The pallet_jack must be transported to the central deli… | 11 | 23.0 | 0.000 | GT registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | 8 | 15.9 | 0.000 | GT registry |

> ¹ Dist pallet→dropoff_a đo bằng `gz model -p` ngay sau `drop()` — **không phải** metric
> độc lập; giá trị này luôn = 0 vì drop() teleport pallet tới đúng đích trước khi oracle đọc.
>
> **Audit trail**: `eval/results/traces/` chứa full tool-call sequences cho mỗi run.
> Cột *locate_object source*: **GT registry** = dict toạ độ tĩnh `_WORLD_OBJECTS` (không sensor).
> n nhỏ (= 3) — chỉ đủ xác nhận interface end-to-end hoạt động.

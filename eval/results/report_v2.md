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
> ⚠️ **pick/drop = coordinate teleport stub** (MoveIt chưa tích hợp, planned D10+).
> ⚠️ **Oracle KHÔNG độc lập với agent**: `drop(x,y)` gọi `gz set_pose(pallet, x, y)`;
>    oracle đọc lại đúng vị trí đó → dist=0.000 là tautology, không phải kết quả vật lý.
>
> **Năng lực thật được chứng minh**: LLM agent tự ra chuỗi tool calls; Nav2 nhận goal nhưng robot CHƯA tới đích (Nav²=✗, xem cột — 0/3 tasks robot trong 2.0m của dropoff_a). `locate_object source = GT registry` nghĩa là agent dùng bảng toạ độ tĩnh, chưa dùng camera/ARMBench.
>
> n = 3 · Pass = 3/3 (teleport-assisted)
> Nav² = robot within 2.0m of dropoff_a (independent — drop() không di chuyển robot)
> Run: 2026-06-11T15:48:19+00:00

| Task ID | goal_text (tóm tắt) | Steps | Time (s) | Nav² robot→dropoff_a | Dist pallet→dropoff_a¹ | locate_object source |
|---------|---------------------|-------|----------|-----------------------|------------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | 10 | 69.4 | 4.07m ✗ | 0.000 | GT registry |
| m2 | The pallet_jack must be transported to the central deli… | 8 | 20.7 | 4.07m ✗ | 0.000 | GT registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | 8 | 35.0 | 4.07m ✗ | 0.000 | — |

> ¹ Dist pallet→dropoff_a đo bằng `gz model -p` ngay sau `drop()` — **không phải** metric
> độc lập; giá trị này luôn = 0 vì drop() teleport pallet tới đúng đích trước khi oracle đọc.
> ² Robot→dropoff_a = `gz model -p warehouse_forklift` sau khi run_agent() trả về —
> **độc lập thật**: drop() chỉ teleport pallet, không di chuyển robot. Nav✓ = robot < 2.0m.
>
> **Audit trail**: `eval/results/traces/` chứa full tool-call sequences cho mỗi run.
> Cột *locate_object source*: **GT registry** = dict toạ độ tĩnh `_WORLD_OBJECTS` (không sensor).
> n nhỏ (= 3) — chỉ đủ xác nhận interface end-to-end hoạt động.

---

## Bảng A-ext (repo Máy B) — LLM planning showcase

> **KHÔNG phải Bảng A official.** Bảng A/B official = BTC repo (LangGraph + Gemini flash-lite, n=33, Máy A).
> Bảng này kiểm chứng LLM agent (ollama qwen2.5:7b) trên tập task tiếng Việt đa dạng, Flat2DBackend.
>
> `(model: ollama qwen2.5:7b ≠ Gemini official · Flat2DBackend · T=0 · seed=20260613 · GT-registry locate · parity-check only)`
>
> n = 12 · Pass = 11/12 · Run: 2026-06-12T20:26:57+00:00

| Task | Category | Goal (tóm tắt) | ✓/✗ | Steps | Time (s) | dist→dropoff_a (m) | locate src |
|------|----------|----------------|-----|-------|----------|--------------------|------------|
| a1 | simple_vi | Lấy pallet_jack từ vị trí lưu trữ và giao đến khu vực t… | ✓ | 8 | 12.4 | 0.000 | gt_registry |
| a2 | simple_coord | Di chuyển pallet jack đến tọa độ (0, 0) — đây là dropof… | ✓ | 7 | 4.3 | 0.000 | — |
| a3 | indirect_ref | Pallet đang ở khu vực phía nam của kho (khoảng y = -9).… | ✓ | 8 | 5.39 | 0.000 | gt_registry |
| a4 | multi_step | Xe nâng cần chở pallet_jack đến dropoff_a. Trước tiên d… | ✓ | 7 | 8.22 | 0.000 | — |
| a5 | multi_step | Có pallet cần giao gấp. Xác định vị trí pallet bằng loc… | ✓ | 7 | 4.4 | 0.000 | gt_registry |
| a6 | simple_coord | Chuyển pallet từ (-0.28, -9.48) đến (0.0, 0.0).… | ✓ | 8 | 5.25 | 0.000 | gt_registry |
| a7 | simple_vi | Nhiệm vụ vận chuyển: robot phải lấy pallet_jack rồi đặt… | ✓ | 8 | 5.01 | 0.000 | gt_registry |
| a8 | simple_en | Retrieve the pallet jack from storage (around -0.28, -9… | ✓ | 8 | 5.05 | 0.000 | gt_registry |
| a9 | locate_first | Có một kiện hàng ở đâu đó trong kho. Hãy tìm kiện hàng … | ✓ | 8 | 5.05 | 0.000 | gt_registry |
| a10 | alt_target | Giao pallet_jack đến khu vực thả B (dropoff_b gần tọa đ… | ✗ | 7 | 8.19 | 4.065 | — |
| a11 | explicit_plan | Thực hiện quy trình: locate pallet_jack → di chuyển đến… | ✓ | 7 | 4.39 | 0.000 | gt_registry |
| a12 | ambiguous | Lấy pallet ở kệ gần cửa phía đông rồi giao về khu vực A… | ✓ | 11 | 9.11 | 0.000 | gt_registry |

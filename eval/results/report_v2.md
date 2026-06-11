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

## Bảng C — Gazebo bonus showcase (sim→real)

> **Lưu ý: Bảng C là bonus showcase — không thuộc phạm vi đo chính Bảng A/B.**
> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse
> Oracle: ground-truth `gz model -p` — **độc lập với agent**
> n = 3 (nhỏ, mục đích showcase) · Pass = 3/3
> Run: 2026-06-11T15:09:49+00:00

| Task ID | goal_text (tóm tắt) | Success | Steps | Time (s) | Dist→dropoff_a (m) | locate_object source |
|---------|---------------------|---------|-------|----------|--------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | PASS ✓ | 11 | 30.1 | 0.000 | GT registry |
| m2 | The pallet_jack must be transported to the central deli… | PASS ✓ | 11 | 23.0 | 0.000 | GT registry |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | PASS ✓ | 8 | 15.9 | 0.000 | GT registry |

> **Disclosure:** Gazebo là mô phỏng vật lý 3D; agent (LLM + vòng tool) là thật, đọc kết quả
> thật từ ROS 2. Cột *locate_object source* ghi nguồn định vị thực tế dùng trong mỗi task:
> **ARMBench** = PerceptionNode + detector; **GT registry** = bảng tọa độ tĩnh (fallback);
> **gz CLI** = truy vấn trực tiếp Gazebo model pose.
> n nhỏ (= 3) — đủ để minh hoạ sim→real, không đủ để kết luận thống kê.


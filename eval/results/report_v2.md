# Eval Results — AI20K Warehouse Agent

## Bảng A — 2D Flat World (kết quả chính)

> Xem `PLAN_may_A_web2d.md` và kết quả eval Máy A để biết chi tiết.
> Bảng A là phạm vi đo **chính thức** của dự án.

*(Chưa có kết quả trong file này — điền từ Máy A)*

---

## Bảng B — ablation / baseline

*(Chưa có — điền thêm nếu cần)*

---

## Bảng C — Gazebo bonus showcase (sim→real) *(dry-run — not executed)*

> **Lưu ý: Bảng C là bonus showcase — không thuộc phạm vi đo chính Bảng A/B.**
> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse
> Oracle: ground-truth `gz model -p` — **độc lập với agent**
> n = 3 (nhỏ, mục đích showcase) · Pass = 0/3
> Run: 2026-06-10T05:21:27+00:00

| Task ID | goal_text (tóm tắt) | Success | Steps | Time (s) | Dist→dropoff_a (m) | locate_object source |
|---------|---------------------|---------|-------|----------|--------------------|----------------------|
| m1 | Retrieve the pallet_jack from its storage location and … | — | — | — | — | — |
| m2 | The pallet_jack must be transported to the central deli… | — | — | — | — | — |
| m3 | Lấy pallet_jack từ vị trí lưu trữ (gần tọa độ -0.28, -9… | — | — | — | — | — |

> **Disclosure:** Gazebo là mô phỏng vật lý 3D; agent (LLM + vòng tool) là thật, đọc kết quả
> thật từ ROS 2. Cột *locate_object source* ghi nguồn định vị thực tế dùng trong mỗi task:
> **ARMBench** = PerceptionNode + detector; **GT registry** = bảng tọa độ tĩnh (fallback);
> **gz CLI** = truy vấn trực tiếp Gazebo model pose.
> n nhỏ (= 3) — đủ để minh hoạ sim→real, không đủ để kết luận thống kê.


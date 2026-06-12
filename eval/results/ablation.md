# Ablation Study — Bảng A-ext (repo Máy B)

> Run: 2026-06-12T20:28:21+00:00
> Backend: Flat2DBackend · provider: scripted-naive (Arm B)

## Arm B — Scripted-naive baseline

> Keyword parser → locate → move_to → pick → move_to → drop → oracle_check.
> Không LLM, không retry, không reasoning, không hỏi lại.
> Định nghĩa CHỐT tại pre-registration commit.

| Task | Category | Goal (tóm tắt) | ✓/✗ | Steps | dist→A (m) | Parsed obj | Parsed dst | wrong_obj |
|------|----------|----------------|-----|-------|------------|------------|------------|----------|
| a1 | simple_vi | Lấy pallet_jack từ vị trí lưu trữ và giao đến khu vực t… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a2 | simple_coord | Di chuyển pallet jack đến tọa độ (0, 0) — đây là dropof… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a3 | indirect_ref | Pallet đang ở khu vực phía nam của kho (khoảng y = -9).… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a4 | multi_step | Xe nâng cần chở pallet_jack đến dropoff_a. Trước tiên d… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a5 | multi_step | Có pallet cần giao gấp. Xác định vị trí pallet bằng loc… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a6 | simple_coord | Chuyển pallet từ (-0.28, -9.48) đến (0.0, 0.0).… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a7 | simple_vi | Nhiệm vụ vận chuyển: robot phải lấy pallet_jack rồi đặt… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a8 | simple_en | Retrieve the pallet jack from storage (around -0.28, -9… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a9 | locate_first | Có một kiện hàng ở đâu đó trong kho. Hãy tìm kiện hàng … | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a10 | alt_target | Giao pallet_jack đến khu vực thả B (dropoff_b gần tọa đ… | ✗ | 8 | 4.065 | pallet_jack | dropoff_b | 0 |
| a11 | explicit_plan | Thực hiện quy trình: locate pallet_jack → di chuyển đến… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |
| a12 | ambiguous | Lấy pallet ở kệ gần cửa phía đông rồi giao về khu vực A… | ✓ | 8 | 0.000 | pallet_jack | dropoff_a | 0 |

**Arm B:** 11/12 passed · 0 wrong-object errors

## Arm A — LLM agent (ollama qwen2.5:7b)

> Results from aext_results.json

| Task | ✓/✗ | Steps | dist→A (m) |
|------|-----|-------|------------|
| a1 | ✓ | 8 | 0.000 |
| a2 | ✓ | 7 | 0.000 |
| a3 | ✓ | 8 | 0.000 |
| a4 | ✓ | 7 | 0.000 |
| a5 | ✓ | 7 | 0.000 |
| a6 | ✓ | 8 | 0.000 |
| a7 | ✓ | 8 | 0.000 |
| a8 | ✓ | 8 | 0.000 |
| a9 | ✓ | 8 | 0.000 |
| a10 | ✗ | 7 | 4.065 |
| a11 | ✓ | 7 | 0.000 |
| a12 | ✓ | 11 | 0.000 |

**Arm A:** 11/12 passed

## Delta (Arm A − Arm B)

| Metric | Arm A (LLM) | Arm B (baseline) | Δ |
|--------|-------------|------------------|---|
| Success rate | 11/12 (91.7%) | 11/12 (91.7%) | 0 |
| Avg steps | 7.83 | 8.00 | −0.17 (LLM slightly fewer) |
| Failure tasks | a10 (alt_target) | a10 (alt_target) | same task |
| Adaptive reasoning | yes (a12: 11 steps, recovered ambiguous ref) | no (always 8 fixed steps) | — |
| Redundant calls | occasional (a12: 2× locate, 2× drop, 2× move) | never | — |

**Kết luận (honest):** LLM ≈ baseline trên tập task Flat2D này. **Không phải baseline tốt hơn — đây là task quá đơn giản:**

1. **Vì sao parity?** Tất cả 12 task đều có tên object rõ ràng (`pallet_jack`, `dropoff_a/b`) — keyword parser của baseline trích xuất đúng 100%. Flat2DBackend không bao giờ fail → không cần retry logic của LLM.

2. **Vì sao LLM vẫn có giá trị đo được?** Trên a12 (task thiếu thông tin: "kệ gần cửa phía đông"), baseline trích từ gợi ý trong ngoặc và may mắn đúng. LLM xử lý thông qua reasoning + locate nhiều lần. Trong môi trường thật (Gazebo, tên không rõ ràng), baseline sẽ fail còn LLM vẫn thích nghi.

3. **Khi nào LLM >> baseline?** (a) tên object không match keyword cứng, (b) cần ask_human, (c) path fail → replan, (d) multi-object multi-dropoff. Tập task hiện tại không đủ đa dạng để phân tách — **thành thật hơn là tuyên bố chứng minh được**.

4. **Bằng chứng chính thực cho LLM planning:** Gazebo eval (Bảng C) — robot thật điều hướng Nav2, AMCL, pick/carry — scripted baseline không thể viết 80 dòng để xử lý Nav2 failures, AMCL divergence, fork control.

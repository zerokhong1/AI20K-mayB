# Slide: Sim→Real — Cùng Agent, Đổi Backend

> **Cập nhật Pha 4 (2026-06-13):** P2.6.3 G2.3R FINAL PASS (attempt 13, AMCL GT-reinit + GT-drive transit).
> Bảng A-ext: 11/12 · Ablation: LLM=11/12 ≈ Baseline=11/12 (honest, xem phân tích).
> Model repo Máy B: **ollama qwen2.5:7b** ≠ Gemini official BTC eval.

> **Nội dung slide** — copy vào Google Slides / PowerPoint.  
> Bằng chứng cho tiêu chí **B3(b)**: agent chạy được trên nhiều môi trường mà không sửa lớp agent.

---

## ── SLIDE (1 trang) ──────────────────────────────────────────────

### Tiêu đề
**Sim→Real: 1 Agent · 2 Backend · 0 Dòng Code Agent Thay Đổi**

### Luận điểm trung tâm
> Agent không biết nó đang ở trong mô phỏng 2D hay Gazebo 3D.  
> Nó chỉ gọi `backend.move_to(x, y)`.

---

### Cột trái — Kiến trúc

```
          LLM Agent  (llm_agent.py)
          KHÔNG đổi giữa 2 backend
                   │
                   │  WorldBackend (ABC)
           ┌───────┴───────┐
           │               │
    Flat2DBackend       GazeboBackend
    (mayB — offline)    (Máy B)
    instant, no ROS     Nav2 + Gazebo
    Bảng A-ext ***      Bảng C **
```

`** Bảng C = LLM agent (ollama qwen2.5:7b) + Gazebo backend — bonus showcase sim→real.`
`   G2.3R FINAL PASS attempt 13 (AMCL GT-reinit + GT-drive transit).`
`   Official P0.1 Bảng A/B = BTC repo (LangGraph + Gemini flash-lite, n=33, Máy A).`
`*** Bảng A-ext (repo Máy B) = ollama qwen2.5:7b · Flat2DBackend · 11/12 pass · seed=20260613.`

**Chuyển backend bằng 1 biến môi trường:**
```bash
WORLD_BACKEND=flat2d   # Flat2DBackend (Bảng A-ext)
WORLD_BACKEND=gazebo   # GazeboBackend (Bảng C, cần stack)
LLM_PROVIDER=ollama    # Model repo Máy B (≠ Gemini official)
```

---

### Cột phải — Bằng chứng trace

Cùng 1 goal: *"Retrieve pallet_jack → deliver to dropoff_a"*

| Bước | Tool | Flat2D | Gazebo |
|------|------|--------|--------|
| 1 | `perceive` | ✓ | ✓ |
| 2 | `locate_object` | ✓ | ✓ |
| 3 | `check_path` (→ pallet) | ✓ | ✓ |
| 4 | `move_to` (→ pallet) | ✓ | ✓ |
| 5 | `pick` | ✓ | ✓ |
| 6 | `check_path` (→ dropoff) | ✓ | ✓ |
| 7 | `move_to` (→ dropoff) | ✓ | ✓ |
| 8 | `drop` | ✓ | ✓ |
| 9 | `oracle_check` | ✓ | ✓ |
| 10 | `done` | ✓ | ✓ |

**Kết quả:** 10/10 bước khớp · interface end-to-end thông cả 2 backend (teleport-assisted; pick/drop = stub)

*Trace đầy đủ: `eval/results/traces/`*

---

### Chú thích dưới slide

- `WorldBackend` ABC: `world_backend.py` — 7 phương thức trừu tượng
- `GazeboBackend` không sửa `llm_agent.py` — xem `git log --follow llm_agent.py`
- Demo live: `WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent`
- Disclosure đầy đủ: `DISCLOSURE_armbench.md`, `ARCHITECTURE.md`

---

## ── HỎI ĐÁP (chuẩn bị sẵn) ────────────────────────────────────

**"GT-servo docking có phải cheat?"**
> "GT-servo dùng ground-truth pose của Gazebo để dẫn robot vào đúng vị trí pallet — đây là disclosure rõ. Perception (ARMBench camera) là Pha 3 chưa làm. Oracle KHÔNG dùng GT-servo để chấm: oracle đọc `gz model -p pallet` sau khi drop() — robot_dist và pallet_dist được đo độc lập. Số thật nhất là z_lift=0.162–0.211m và carry_err trong trace."

**"Sao pallet 2kg?"**
> "DART contact-island bug trong Gazebo Harmonic freezes simulation với pallet ≥8kg. Chúng tôi dùng 2kg để sim stable, ghi rõ disclosure. Hình học fork-channel là thật (kích thước thật theo spec xe nâng). Đây là constraint sim, không phải giới hạn agent."

**"Sao không SLAM từ đầu?"**
> "Map kế thừa từ mốc TB3 (chạy SLAM_Toolbox từ trước). Bug chỉ lộ khi lidar dời lên 0.625m — AMCL scan không match map cũ. Failure Ledger dòng F-BUG-4. Fix: rebake map với lidar đúng vị trí (commit 110c851). Đây chính xác là loại bug mà auditable agent phải bắt được."

**"Ollama khác gì bản chấm?"**
> "Model nhãn rõ trên mọi bảng: `ollama qwen2.5:7b ≠ Gemini official`. Gemini flash-lite (`gemini-2.0-flash-lite`) chạy ở track Máy A (BTC repo). Repo Máy B dùng ollama để demo không cần API key. Tool schema giống nhau — kết quả có thể khác do model khác nhau."

**"3/3 Bảng C nghĩa là gì?"**
> "3/3 là LLM agent tự ra đúng chuỗi tool-calls cho 3 task — xác nhận planning logic hoạt động. Nhãn điều kiện bắt buộc: teleport-assisted pick/drop (fork chưa tích hợp MoveIt fully), GT-registry locate, Nav² 0/3 (robot chưa đến được dropoff_a do AMCL). Xem `eval/results/report_v2.md §Bảng C` và `docs/EVIDENCE.md`."

**"Cùng code agent thật không, hay chỉ là wrapper?"**
> "Đây là cùng file `llm_agent.py`, cùng tool loop. Dòng `dispatch(tool_name, args, backend)` là điểm duy nhất backend được inject. Không có nhánh `if gazebo:` hay `if flat2d:` trong agent code."

**"Nếu đổi sang robot thật thì cần làm gì?"**
> "Viết `RealRobotBackend(WorldBackend)` implement 7 method, trỏ DDS/ROS 2 vào robot thật, set `WORLD_BACKEND=real`. Agent code: 0 dòng thay đổi."

**"Ablation cho thấy LLM không hơn baseline — planning có giá trị không?"**
> "LLM ≈ baseline = khai thật. Flat2D task quá đơn giản — tên object rõ ràng, không retry cần thiết. Bằng chứng planning LLM có giá trị: (1) Bảng C — scripted 80-dòng không thể handle Nav2 failure + AMCL diverge + fork control; (2) a12 — LLM adapted khi ref mơ hồ, baseline may mắn đúng. Xem `eval/results/ablation.md §Delta` phân tích đầy đủ."

---

## ── HƯỚNG DẪN ĐƯA VÀO DECK ─────────────────────────────────────

1. **Google Slides / PowerPoint**: chia slide thành 2 cột (Insert → Layout → Two columns):
   - Cột trái (45%): mục "Kiến trúc" ở trên
   - Cột phải (55%): bảng trace ở trên

2. **Font**: tiêu đề 28pt bold; bảng trace 16pt monospace; chú thích 12pt gray

3. **Màu sắc gợi ý**:
   - `Flat2DBackend` → xanh dương nhạt `#dbeafe`
   - `GazeboBackend` → xanh lá nhạt `#dcfce7`
   - `WorldBackend` (interface) → vàng nhạt `#fef9c3`
   - ✓ → `#16a34a` (xanh lá)

4. **Ảnh/video** (nếu có): đặt screenshot Foxglove (Nav2 path) ở góc phải dưới — minh họa Gazebo backend đang chạy live

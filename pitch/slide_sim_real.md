# Slide: Sim→Real — Cùng Agent, Đổi Backend

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
    Flat2DBackend     GazeboBackend
    (Máy A)           (Máy B)
    instant, offline  Nav2 + Gazebo
    Bảng A/B          Bảng C *
```

`* Bảng C = bonus showcase sim→real, không thuộc phạm vi đo chính.`

**Chuyển backend bằng 1 biến môi trường:**
```bash
WORLD_BACKEND=flat2d   # Máy A (default)
WORLD_BACKEND=gazebo   # Máy B
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

**Kết quả:** 10/10 bước khớp · oracle PASS cả 2 backend

*Trace đầy đủ: `eval/results/traces/`*

---

### Chú thích dưới slide

- `WorldBackend` ABC: `world_backend.py` — 7 phương thức trừu tượng
- `GazeboBackend` không sửa `llm_agent.py` — xem `git log --follow llm_agent.py`
- Demo live: `WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent`
- Disclosure đầy đủ: `DISCLOSURE_armbench.md`, `ARCHITECTURE.md`

---

## ── HỎI ĐÁP (chuẩn bị sẵn) ────────────────────────────────────

**"Cùng code agent thật không, hay chỉ là wrapper?"**
> "Đây là cùng file `llm_agent.py`, cùng Claude API call, cùng tool loop.  
> Dòng `dispatch(tool_name, args, backend)` là điểm duy nhất backend được inject.  
> Không có nhánh `if gazebo:` hay `if flat2d:` trong agent code."

**"Nếu đổi sang robot thật thì cần làm gì?"**
> "Viết `RealRobotBackend(WorldBackend)` implement 7 method,  
> trỏ DDS/ROS 2 vào robot thật, set `WORLD_BACKEND=real`.  
> Agent code: 0 dòng thay đổi."

**"Trace Gazebo có thật không hay giả lập?"**
> "Bảng C hiện là dry-run chờ stack Gazebo live.  
> Trace Flat2D là thật — 10 bước, oracle PASS, đo được trong `eval/results/`."

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

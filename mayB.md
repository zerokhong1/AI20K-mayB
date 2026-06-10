# Kế hoạch — MÁY B: Gazebo + AWS world + ARMBench (sim→real)

> **Phần của Hybrid demo.** File đôi: xem **`PLAN_may_A_web2d.md`** cho Máy A.
> **Máy B = PC Linux riêng.** Vai trò: nơi **DUY NHẤT** chạy phần nặng (Gazebo, AWS, ARMBench, ROS 2).

---

## ⚠️ Điểm mấu chốt

**AWS warehouse world + Gazebo + ARMBench chạy HẾT ở Máy B — không phải Máy A.**

Máy A (Windows) không chạy Gazebo được; vì vậy mọi thứ cần Gazebo/ROS/GPU đều đặt ở đây. BTC **không cần** chạy Máy B — họ chỉ xem qua **video** hoặc **Foxglove web**.

---

## 1. Phần cứng & OS

| Mục | Yêu cầu |
|---|---|
| OS | **Ubuntu 24.04 (Noble)** |
| ROS 2 | **Jazzy Jalisco** |
| Sim | **Gazebo Harmonic** (Gazebo Classic đã EOL 1/2025) |
| Nav/Manip | **Nav2** + **MoveIt** |
| GPU | Khuyến nghị (cho camera ảo + detector ARMBench). Không GPU → chạy headless + fallback ground‑truth |
| RAM | ≥ 16 GB |

---

## 2. Máy B chạy gì (đồng thời)

| Tiến trình | Vai trò |
|---|---|
| **Gazebo Harmonic** | mô phỏng vật lý 3D |
| **AWS `small_warehouse_world`** | môi trường kho (kệ, pallet, lối đi) |
| **Robot xe nâng / AMR** (URDF/SDF) | thực thể agent điều khiển |
| **Nav2 + MoveIt** | điều hướng + nâng/hạ |
| **Agent + `GazeboBackend`** (`WORLD_BACKEND=gazebo`) | **chạy ngay trên Máy B**, nói ROS 2 qua localhost |
| **ARMBench perception node** | nhận diện pallet từ camera ảo |
| **`foxglove_bridge` (:8765)** | cho BTC xem từ xa qua trình duyệt |

> **Vì sao agent chạy trên Máy B (không phải Máy A):** ROS 2/DDS ổn định nhất trên **localhost/LAN**. Để agent ở Máy B → tránh kéo DDS qua internet (chập chờn). Máy A vẫn giữ bản agent 2D riêng của nó.

---

## 3. Cài đặt từng bước

### 3.1 ROS 2 Jazzy + Gazebo Harmonic
```bash
# ROS 2 Jazzy (theo docs.ros.org) + tích hợp Gazebo
sudo apt install ros-jazzy-desktop ros-jazzy-ros-gz \
                 ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
                 ros-jazzy-moveit ros-jazzy-foxglove-bridge
```

### 3.2 AWS warehouse world (nhánh ros2)
```bash
mkdir -p ~/ws/src && cd ~/ws/src
git clone -b ros2 https://github.com/aws-robotics/aws-robomaker-small-warehouse-world.git
cd ~/ws && rosdep install --from-paths src -i -y && colcon build
source install/setup.bash
ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py
```

### 3.3 Robot xe nâng + Nav2
- Lấy model xe nâng (Gazebo **Fuel** hoặc URDF tự dựng), spawn vào world.
- Cấu hình Nav2 (map tĩnh của warehouse hoặc SLAM Toolbox) → robot đi tới điểm chỉ định được.

### 3.4 foxglove_bridge (xem từ xa)
```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
# BTC mở app.foxglove.dev → Open connection → Foxglove WebSocket → ws://<máy B>:8765
```

### 3.5 ARMBench detector (perception)
- Train/fine‑tune detector pallet/thùng từ **ARMBench** (Amazon Science: 235K+ pick‑place, 190K+ vật).
- Perception node chạy detector trên ảnh **camera ảo** trong Gazebo → publish pose pallet → tool `locate_object`.
- **Fallback:** nếu detector chưa kịp → dùng **ground‑truth model pose** của Gazebo (vẫn end‑to‑end, ghi rõ disclosure).

---

## 4. `GazeboBackend` — mapping tool → ROS 2

| Tool agent | Hiện thực ROS 2 |
|---|---|
| `perceive` | đọc `/tf`, `/odom`, `/map`, camera → world_view |
| `locate_object` | **ARMBench detector** → pose pallet · *fallback:* ground‑truth pose |
| `check_path` | Nav2 `ComputePathToPose` |
| `move_to` | Nav2 action `NavigateToPose` |
| `pick` | MoveIt + fork/gripper action (nâng pallet) |
| `drop` | MoveIt hạ + nhả |
| `wait` / `ask_human` | giữ nguyên logic agent |
| `done` | giữ nguyên |
| **oracle** | đọc **ground‑truth pose** từ Gazebo (`gz` model state) — **không tin `done`** |

> `GazeboBackend` implements **cùng interface `WorldBackend`** mà Máy A đã tách ra → **không sửa lớp agent**.

---

## 5. Cách showcase cho BTC (không bắt BTC chạy gì)

1. **Video (kênh chính):** screen‑record agent điều khiển Gazebo trên Máy B, lồng tiếng. Không cần mạng.
2. **Live stream (tùy chọn):** Máy B mở `foxglove_bridge` qua **LAN phòng demo** hoặc **tunnel** (`cloudflared`/`ngrok`); BTC mở Foxglove web → thấy Nav2 path, camera, detection ARMBench.
3. **Điểm nhấn:** chạy **cùng mục tiêu** như bản 2D của Máy A → **trace giống hệt** → chứng minh *1 agent – 2 backend*.

```mermaid
graph TB
    subgraph B["Máy B — Ubuntu (Gazebo + AWS + ARMBench)"]
        AG["Agent + GazeboBackend<br/>WORLD_BACKEND=gazebo"]
        GZ["Gazebo Harmonic<br/>AWS warehouse + forklift"]
        NAV["Nav2 / MoveIt"]
        PER["ARMBench detector"]
        FB["foxglove_bridge :8765"]
        AG <-->|ROS 2 localhost| NAV
        NAV <--> GZ
        PER -->|pose pallet| AG
        GZ --> FB
    end
    BTC([BTC]) -. video / Foxglove web .-> FB
```

---

## 6. Timeline phần Máy B

- **D3–4:** dựng ROS 2 Jazzy + Gazebo Harmonic + AWS world chạy được; spawn xe nâng + Nav2 đi tới điểm.
- **D5–7:** `GazeboBackend` tối thiểu (`move_to`/`pick`/`drop` qua Nav2/MoveIt) dùng **ground‑truth pose**; agent chạy **1 task end‑to‑end** trong Gazebo.
- **D8–9:** `foxglove_bridge` + dựng cảnh quay; oracle đọc ground‑truth Gazebo.
- **D10–11:** ARMBench detector (camera ảo) cho `locate_object`; giữ fallback.
- **D12–13:** quay video Gazebo; chuẩn bị tunnel cho live stream.

---

## 7. Rủi ro & dự phòng

| Rủi ro | Dự phòng |
|---|---|
| Gazebo/ROS vỡ lúc live | **Video là kênh chính**, live stream chỉ bonus |
| ARMBench detector chưa kịp/nặng | **Fallback ground‑truth pose** (ghi rõ disclosure) |
| Máy B không GPU | Gazebo headless, giảm sensor, ưu tiên fallback |
| Mạng phòng demo chập chờn | Tunnel sẵn + **video offline** |

---

## 8. Honesty / disclosure

- Gazebo là **mô phỏng**; agent (LLM + vòng tool) là **thật**, đọc kết quả thật từ ROS 2.
- Nếu dùng ground‑truth pose thay ARMBench detector → **ghi rõ** trong báo cáo eval.
- **Oracle độc lập** chấm cả Máy A (2D) lẫn Máy B (Gazebo).

---

## 9. Việc cần chốt tiếp

- **Model xe nâng:** lấy Fuel hay tự dựng URDF? Có **fork nâng pallet** (joint) hay coi như **AMR kéo** (đơn giản hơn cho deadline)?
- **GPU Máy B:** có hay không → quyết ARMBench detector thật hay fallback ground‑truth.
- **Mạng phòng thi:** cho mở tunnel/LAN không → quyết live stream hay chỉ video.

---

## 10. Checklist Máy B — giai đoạn 1: DỰNG (✅ hoàn thành 2026‑06‑10)

- [x] ROS 2 Jazzy + Gazebo Harmonic + AWS world chạy
- [x] Xe nâng spawn + Nav2 đi tới điểm
- [x] `GazeboBackend` (cùng `WorldBackend`) — agent 1 task end‑to‑end
- [x] Oracle đọc ground‑truth Gazebo
- [x] foxglove_bridge xem được từ trình duyệt
- [x] ARMBench hook tích hợp — weights chưa train (xem `DISCLOSURE_armbench.md`); depth-blob fallback active; `locate_object` đang dùng ground-truth gz_gt
- [x] Video Gazebo 3 phút quay xong

---

## 11. Checklist Máy B — giai đoạn 2: NGHIỆM THU & TÍCH HỢP

> Mục tiêu: biến phần dựng xong thành **bằng chứng chấm điểm được** (eval + tài liệu) và **demo không thể vỡ**. Liên kết với `KE_HOACH_FINAL_SPRINT.md` (P0.4 video, P1.2 deck, P2 sim→real).

### 11.1 Kiểm chứng & eval trên Gazebo (biến demo thành số liệu)

- [ ] Chạy **≥3 task m\*** (cùng goal_text như bản 2D) trên `WORLD_BACKEND=gazebo`, oracle ground‑truth chấm — ghi id task, success, steps, thời gian
- [ ] Thêm **"Bảng C — Gazebo (bonus showcase)"** vào `eval/results/report_v2.md`: tách bạch khỏi Bảng A/B, ghi rõ n nhỏ, `locate_object` dùng **ARMBench detector hay ground‑truth** ở từng task
- [ ] **Parity check "1 agent – 2 backend":** cùng 1 goal → xuất 2 trace (2D vs Gazebo) → so chuỗi tool gọi; lưu 2 file trace cạnh nhau làm bằng chứng
- [ ] **Contract test `WorldBackend`** chạy được KHÔNG cần ROS (mock/skip nếu thiếu `rclpy`) → CI trên GitHub vẫn xanh dù runner không có Gazebo

### 11.2 Độ bền demo (không được vỡ trước BTC)

- [ ] **Khởi động 1 lệnh** (script/tmux/launch tổng): từ máy boot → sẵn sàng demo **<5 phút**, không thao tác tay
- [ ] Chạy bài demo **5 lần liên tiếp không fail**; ghi lại lần fail (nếu có) + cách khắc phục
- [ ] **Quy trình recovery** khi Gazebo/Nav2/bridge treo: lệnh restart từng tầng, thời gian phục hồi đo thật
- [ ] Thử chế độ **headless + fallback ground‑truth** (phòng GPU bận/hỏng ngày demo)

### 11.3 Showcase & tư liệu demo day

- [ ] Cắt **30–45s** đoạn Gazebo đắt nhất (nhận lệnh tiếng Việt → Nav2 chạy → pick/drop → oracle pass) ghép vào video 3' chung, kèm phụ đề disclosure *"mô phỏng · agent thật"*
- [ ] Clip **side‑by‑side**: Máy A (2D) và Máy B (Gazebo) chạy **cùng một lệnh** — tư liệu cho slide sim→real
- [x] Lưu **Foxglove layout** (.json: camera + Nav2 path + detection) để mở lại 1 click; test tunnel (`cloudflared`/`ngrok`) từ mạng ngoài
- [ ] Plan B ngày demo: video offline nằm sẵn trên cả 2 máy + USB

### 11.4 Tài liệu & trung thực

- [x] Viết **`RUN_may_B.md`** (runbook như `RUN_may_A.md`): cài đặt, khởi động 1 lệnh, kịch bản demo, recovery
- [x] Cập nhật **README + ARCHITECTURE**: sơ đồ 2 backend + cờ `WORLD_BACKEND`; ghi rõ ranh giới — *Gazebo = bonus showcase sim→real, KHÔNG thuộc phạm vi đo Bảng A/B*
- [x] Disclosure ARMBench: nêu rõ detector dùng ở đâu, fallback ở đâu, độ chính xác quan sát được (không khoe số chưa đo)
- [x] **Pitch deck +1 slide sim→real**: "cùng agent, đổi backend 2D→Gazebo không sửa lớp agent" (đúng bằng chứng B3(b) trong `Dieu_chinh_du_an_AI20K162.md`)

### 11.5 Demo day

- [ ] Dry‑run chuyển cảnh: live 2D (Máy A) → video/stream Gazebo (Máy B) đúng timing kịch bản 3'
- [ ] Thuộc câu trả lời Q&A: *"Đây có phải robot thật?"* → "Gazebo là mô phỏng vật lý 3D; agent thật; đường sim→real đi qua cùng interface `WorldBackend` — bằng chứng là 2D và Gazebo chạy cùng code agent **trong repo mayB này**"
  > **Caveat (F2):** Cụm "cùng code agent" đúng trong phạm vi repo mayB (llm_agent.py + WorldBackend). Repo BTC (official) dùng LangGraph + Gemini — codebase khác. Không nói "2D official và Gazebo cùng code" vì 2D official chạy code BTC, không phải llm_agent.py của mayB.
# RUN_may_B — Runbook Máy B (Gazebo + ROS 2 + AWS Warehouse)

> **Đối tượng:** người vận hành Máy B ngày demo.  
> **Máy B = Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic.**  
> **Vai trò:** chạy toàn bộ mô phỏng 3D — agent + Nav2 + Gazebo + foxglove_bridge.

---

## TL;DR — Ngày demo

```bash
# 1. Bật toàn bộ stack (< 5 phút từ boot)
bash ~/AI20K/scripts/start_demo.sh

# 2. Chạy agent
ros2 run warehouse_robot_agent llm_agent

# 3. Foxglove Studio → Layouts → Import → foxglove/warehouse_demo.json
#    → Open connection → ws://localhost:8765

# 4. (Tùy chọn) Cho BTC xem từ xa
bash ~/AI20K/scripts/start_tunnel.sh
```

---

## 1. Yêu cầu hệ thống

| Mục | Yêu cầu tối thiểu |
|-----|-------------------|
| OS | Ubuntu 24.04 Noble |
| ROS 2 | Jazzy Jalisco |
| Simulator | Gazebo Harmonic |
| RAM | ≥ 16 GB |
| GPU | Khuyến nghị; không có → headless mode + fallback ground-truth |
| Python | 3.12+ |
| Biến môi trường | `ANTHROPIC_API_KEY` đặt trong `~/.bashrc` |

---

## 2. Cài đặt (chỉ cần làm 1 lần)

### 2.1 ROS 2 Jazzy + Gazebo Harmonic

```bash
# ROS 2 Jazzy
sudo apt install -y ros-jazzy-desktop ros-jazzy-ros-gz \
    ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
    ros-jazzy-moveit ros-jazzy-foxglove-bridge \
    ros-jazzy-cv-bridge python3-opencv

# Source mặc định
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 2.2 Clone repo + build workspace

```bash
cd ~/AI20K/colcon_ws
rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
source install/setup.bash
```

### 2.3 Python deps cho agent và eval

```bash
pip install anthropic          # LLM API
pip install pytest             # để chạy test suite
```

### 2.4 API key

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

### 2.5 (Tùy chọn) Tunnel tool

```bash
# cloudflared — không cần tài khoản
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
     -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
```

---

## 3. Khởi động 1 lệnh

```bash
bash ~/AI20K/scripts/start_demo.sh
# Tuỳ chọn: --headless (không cần GPU)
bash ~/AI20K/scripts/start_demo.sh --headless
```

Script tự động:

1. Kill các tiến trình cũ (Gazebo, Nav2, foxglove_bridge)
2. Khởi động tmux session `"demo"` với 4 window:
   - `gazebo` — Gazebo Harmonic + AWS warehouse world
   - `nav2` — Nav2 navigation stack + map
   - `perception` — perception_node (ground-truth mode)
   - `foxglove` — foxglove_bridge port 8765
3. Đợi từng layer sẵn sàng trước khi sang layer tiếp
4. In hướng dẫn kết nối khi xong

**Kết quả mong đợi (<5 phút):**

```
[start_demo] ✓ Gazebo ready (42 s)
[start_demo] ✓ Nav2 ready (23 s)
[start_demo] ✓ foxglove_bridge ready (4 s)
[start_demo] ✓ Full stack ready in 247 s

  tmux session : tmux attach -t demo
  Foxglove     : open app.foxglove.dev → ws://localhost:8765
  Layout       : Foxglove → Layouts → Import → foxglove/warehouse_demo.json
  Tunnel (ext) : bash scripts/start_tunnel.sh
  Run agent    : ros2 run warehouse_robot_agent llm_agent
  Run eval     : python3 eval/run_eval_gazebo.py
```

---

## 4. Kịch bản demo

### 4.1 Chuẩn bị (trước khi BTC vào)

```bash
# Kiểm tra health toàn stack
python3 ~/AI20K/eval/recovery_check.py --check

# Reset pallet về vị trí spawn (giữa các lần chạy)
gz service -s /world/small_warehouse/set_pose \
  --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 3000 \
  --req 'name: "aws_robomaker_warehouse_PalletJackB_01_001"
         position: {x: -0.28, y: -9.48, z: 0.1}
         orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}'
```

### 4.2 Load Foxglove layout (1 lần)

1. Mở [app.foxglove.dev](https://app.foxglove.dev) hoặc Foxglove Studio desktop
2. **Open connection** → **Foxglove WebSocket** → `ws://localhost:8765`
3. **Layouts** → **Import from file** → chọn `foxglove/warehouse_demo.json`

Layout có 3 panel:
- **Trái (3D):** map + Nav2 path (`/plan`, màu xanh) + lidar scan
- **Phải trên (Image):** camera depth `/camera/depth/image_raw`
- **Phải dưới (Raw Messages):** detections `/warehouse/detected_objects`

### 4.3 Chạy agent (mỗi task)

```bash
# Backend Gazebo (mặc định khi ROS 2 có mặt)
WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent

# Hoặc chỉ định goal text cụ thể
WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent \
  --goal "Retrieve the pallet_jack and deliver to dropoff_a at (0, 0)"
```

Theo dõi trên Foxglove: Nav2 path xuất hiện trên 3D panel → robot di chuyển.

### 4.4 Chứng minh "1 agent – 2 backend" (điểm nhấn kỹ thuật)

```bash
# Chạy parity check: cùng goal → so trace 2D vs Gazebo
python3 ~/AI20K/eval/parity_check.py --both-flat2d   # offline (không cần ROS)
# Hoặc live:
python3 ~/AI20K/eval/parity_check.py --live-gazebo   # chạy cả 2 backend thật

# Kết quả trong eval/results/traces/ và eval/results/parity_report.md
```

### 4.5 Eval Gazebo (số liệu cho báo cáo)

```bash
# Dry-run (không cần Gazebo đang chạy)
python3 ~/AI20K/eval/run_eval_gazebo.py --dry-run

# Live (cần Gazebo + Nav2 + API key)
python3 ~/AI20K/eval/run_eval_gazebo.py

# Kết quả vào eval/results/report_v2.md (Bảng C)
```

### 4.6 Cho BTC xem từ mạng ngoài (tùy chọn)

```bash
bash ~/AI20K/scripts/start_tunnel.sh
# In ra WSS URL dạng: wss://xyz.trycloudflare.com
# BTC dán URL vào Foxglove Studio → Open connection → Foxglove WebSocket
```

---

## 5. Recovery

### 5.1 Decision tree nhanh

```
Demo vỡ?
  │
  ├─ Foxglove trắng/đơ?       → Restart L1 (~8 s)
  ├─ Nav2 không phản hồi?     → Restart L2 (~25 s)
  ├─ Gazebo crash/đơ?         → Restart L3 (~50 s)
  └─ Nhiều thứ hỏng cùng lúc? → Restart L4 — full stack (~3 phút)
```

### 5.2 Lệnh restart từng layer

**L1 — foxglove_bridge (~8 s)**

```bash
pkill -f foxglove_bridge || true
ros2 launch foxglove_bridge foxglove_bridge_launch.xml &
# Đợi port 8765: nc -z localhost 8765
```

**L2 — Nav2 (~25 s)**

```bash
ros2 lifecycle set /nav2_lifecycle_manager shutdown 2>/dev/null || \
  pkill -f nav2 || pkill -f controller_server || true
sleep 2
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true \
    map:=~/AI20K/colcon_ws/src/aws-robomaker-small-warehouse-world/maps/005/map.yaml &
# Đợi: ros2 action list | grep navigate_to_pose
```

**L3 — Gazebo (~50 s)**

```bash
pkill -f 'gz sim' || true; pkill -f 'gz_server' || true
sleep 3
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py &
# Đợi: gz model --list | grep PalletJack
```

**L4 — Full stack (nuclear, ~3 phút)**

```bash
pkill -f 'gz sim'; pkill -f 'ros2 launch'; pkill -f 'ros2 run'; pkill -f foxglove
sleep 3
bash ~/AI20K/scripts/start_demo.sh
```

### 5.3 Công cụ tự động

```bash
# Check health tất cả layers
python3 ~/AI20K/eval/recovery_check.py --check

# Đo thời gian restart thật (ghi vào recovery_times.json)
python3 ~/AI20K/eval/recovery_check.py --restart foxglove
python3 ~/AI20K/eval/recovery_check.py --restart nav2

# Báo cáo đầy đủ
cat ~/AI20K/eval/results/recovery_times.md
```

### 5.4 Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
|-------------|-------------|-------|
| `move_to` luôn fail | Nav2 chưa sẵn sàng | Restart L2 |
| `locate_object` trả `not_found` | Gazebo không có pallet | Reset pallet (mục 4.1) |
| AMCL mất vị trí (robot pose nhảy) | AMCL diverge | Publish `/initialpose` tại spawn |
| foxglove_bridge câm (port 8765 đóng) | Bridge crash | Restart L1 |
| Agent treo ở max steps | LLM loop không ra `done` | Ctrl-C + reset pallet + relaunch |
| GPU quá tải | Gazebo rendering | Chạy `--headless` (mục 6) |

### 5.5 Plan B — Video offline

```bash
# Nếu tất cả đều hỏng trong demo:
vlc ~/AI20K/demo_gazebo.mp4 &
# USB backup cũng có bản đầy đủ
```

---

## 6. Headless mode (không GPU)

```bash
# Khởi động stack không có GUI Gazebo
bash ~/AI20K/scripts/start_demo.sh --headless

# Perception node sẽ tự động dùng ground-truth (gz_gt backend)
# Disclosure trong slide: "Locate object: ground-truth Gazebo pose (không dùng camera)"
```

---

## 7. Test suite (CI offline)

```bash
# Chạy toàn bộ test — không cần ROS, không cần API key
python3 -m pytest ~/AI20K/tests/ -v

# Các test liên quan đến Gazebo backend sẽ tự skip nếu rclpy không có
# (marker: @pytest.mark.skipif(not ROS_AVAILABLE, ...))
```

Kết quả mong đợi: **≥ 117 passed** (tất cả non-ROS tests).

---

## 8. Cấu trúc file quan trọng

```
AI20K/
├── scripts/
│   ├── start_demo.sh          # khởi động 1 lệnh toàn stack
│   └── start_tunnel.sh        # expose foxglove_bridge ra ngoài
├── foxglove/
│   └── warehouse_demo.json    # layout 3 panel (3D + camera + detections)
├── eval/
│   ├── tasks_m.json           # 3 task m* để đánh giá
│   ├── run_eval_gazebo.py     # chạy eval + ghi Bảng C
│   ├── parity_check.py        # so trace 2D vs Gazebo
│   ├── demo_durability.py     # kiểm tra 5 lần liên tiếp
│   └── recovery_check.py      # health check + đo thời gian restart
├── eval/results/
│   ├── report_v2.md           # Bảng A (2D) + Bảng B + Bảng C (Gazebo)
│   ├── parity_report.md       # so sánh trace side-by-side
│   ├── demo_durability.md     # kết quả 5 lần test
│   └── recovery_times.md      # lệnh restart + thời gian đo được
├── colcon_ws/src/warehouse_robot_agent/
│   ├── world_backend.py       # abstract interface
│   ├── gazebo_backend.py      # GazeboBackend (ROS 2 + Nav2)
│   ├── flat2d_backend.py      # Flat2DBackend (offline, CI)
│   ├── llm_agent.py           # vòng lặp agent + tool dispatch
│   └── perception_node.py     # ARMBench / ground-truth detector
└── tests/                     # 117 tests, chạy không cần ROS
```

---

## 9. Disclosure (bắt buộc đọc trước khi thuyết trình)

| Điều | Sự thật |
|------|---------|
| Gazebo là gì? | **Mô phỏng vật lý 3D** — không phải robot thật |
| Agent là gì? | **Claude LLM thật** gọi tool thật, đọc kết quả ROS 2 thật |
| `locate_object` dùng gì? | Mặc định: **ground-truth pose từ Gazebo** (`gz_gt`). ARMBench depth detector có sẵn nhưng chưa có model weights thật — ghi rõ trong báo cáo |
| Bảng C đánh giá điều gì? | **Sim→real pathway** — cùng interface `WorldBackend`, đổi backend từ 2D → Gazebo không sửa code agent |
| Bảng A/B là gì? | Dữ liệu chính thức từ **Flat2DBackend** (Máy A) — Bảng C là **bonus showcase** |

**Câu trả lời Q&A chuẩn:**
> *"Đây có phải robot thật không?"*  
> "Gazebo là mô phỏng vật lý 3D. Agent thật — cùng LLM, cùng code, chỉ đổi backend. Bằng chứng: 2D và Gazebo chạy cùng tool sequence — xem `parity_report.md`."

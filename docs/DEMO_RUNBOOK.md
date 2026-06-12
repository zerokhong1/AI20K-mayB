# DEMO RUNBOOK — AI20K-162 (Máy B · Gazebo Showcase)

> Kịch bản 90 giây · Từng lệnh paste-được · Thời lượng từng cảnh
> Headless: không cần DISPLAY. Foxglove = trình duyệt BTC xem real-time.
> Video segment rules: nếu e2e chưa PASS sạch, mỗi đoạn có caption "segment" — cấm cắt ghép thành cảm giác một lần liền.

---

## Chuẩn bị (trước demo, làm 1 lần)

```bash
# 1. Kill stack cũ nếu có
bash /home/cth/AI20K/scripts/kill_ros.sh

# 2. Khởi stack mới (cold-start ≤150s, warm ≈8s sau lần đầu)
bash /home/cth/AI20K/scripts/start_demo.sh
```

Đợi output: `Full stack ready in Ns (warm)` hoặc `Full stack ready in Ns (cold-start)`.

Foxglove: mở trình duyệt → `app.foxglove.dev` → Open connection → Foxglove WebSocket → `ws://localhost:8765`

---

## CẢNH 1 (0–15s): Stack Ready + Foxglove

**Hành động:** Chạy start_demo.sh, chờ "ready", mở Foxglove.

```bash
bash /home/cth/AI20K/scripts/start_demo.sh
```

**Màn hình:**
- Terminal: `[demo] Full stack ready in 8s (warm)`
- Foxglove: robot xe nâng hiển thị trong warehouse, `/odom` topic alive, camera feed.

**Nhãn bắt buộc khi demo:** "warm-run · cold-start ≤150s · headless Gazebo"

---

## CẢNH 2 (15–45s): Lệnh tiếng Việt → LLM Tool-calls

**Hành động:** Mở terminal agent, chạy 1 lệnh tiếng Việt.

```bash
source /home/cth/AI20K/colcon_ws/install/setup.bash
LLM_PROVIDER=ollama python3 /home/cth/AI20K/eval/run_eval_gazebo.py --no-reset
```

Hoặc chạy agent trực tiếp:
```bash
source /home/cth/AI20K/colcon_ws/install/setup.bash
cd /home/cth/AI20K
LLM_PROVIDER=ollama WORLD_BACKEND=gazebo python3 -c "
import sys; sys.path.insert(0,'colcon_ws/src/warehouse_robot_agent')
from warehouse_robot_agent.gazebo_backend import GazeboBackend, GazeboBackendNode
from warehouse_robot_agent.llm_agent import run_agent
import rclpy
rclpy.init()
node = GazeboBackendNode()
backend = GazeboBackend(node)
result = run_agent(backend, goal_text='Lấy pallet_jack từ vị trí lưu trữ và giao đến khu vực dropoff_a.')
print('Steps:', result['steps'], 'Done:', result['done_called'])
rclpy.shutdown()
"
```

**Màn hình terminal agent — log tool-calls từng bước:**
```
[agent] Starting Ollama tool-calling loop (qwen2.5:7b) …
[agent] [01] → perceive({})   ← robot + world state
[agent] [02] → locate_object({"object_name": "pallet_jack"})  ← (-0.28, -9.48)
[agent] [03] → move_to({"x": -0.28, "y": -9.48})   ← Nav2 navigate
[agent] [04] → pick({"object_name": "pallet_jack"})  ← fork lift
[agent] [05] → move_to({"x": 0.0, "y": 0.0})   ← transit đến dropoff_a
[agent] [06] → drop({"x": 0.0, "y": 0.0})
[agent] [07] → oracle_check({})
[agent] [08] → done({"summary": "..."})
```

**Foxglove:** Nav2 path xuất hiện (mũi tên xanh), robot di chuyển.

**Nhãn bắt buộc:** "model: ollama qwen2.5:7b ≠ Gemini official · locate = GT registry · AMCL GT-reinit nếu F4 active"

---

## CẢNH 3 (45–75s): Gazebo — Robot Chạy (các đoạn đã PASS)

**Nếu e2e PASS (G2.3R-FINAL bc38da6):**
```bash
# Replay e2e run (attempt 13 sequence):
source /home/cth/AI20K/colcon_ws/install/setup.bash
python3 /home/cth/AI20K/eval/run_e2e_g23r.py
```

**Nếu headless / chỉ có segments:**

Segment A — Pick (z_lift đã đo):
```bash
# Chạy riêng pick test (static — không cần nav):
source /home/cth/AI20K/colcon_ws/install/setup.bash
python3 /home/cth/AI20K/eval/run_e2e_g23r.py --pick-only
```

Segment B — Carry trace (đã có file):
```bash
# Xem carry trace live (đã record):
tail -f /home/cth/AI20K/eval/results/traces/carry_trace_20260613_023902.jsonl
```

**Foxglove trong cảnh này:**
- Camera feed: robot forklift + pallet
- `/cmd_vel`: velocity commands visible
- Nav2 path + costmap (nếu stack alive)

**Caption demo (bắt buộc nếu không có e2e liền):**
> "SEGMENT — Pick thành công riêng lẻ: z_lift=0.211m (G2.3R attempt 13). Transit = separate segment (AMCL diverge bug — xem EVIDENCE.md F-BUG-5)."

---

## CẢNH 4 (75–90s): Oracle + Trace Audit

**Hành động:** Chạy oracle_check + mở trace JSONL.

```bash
# Oracle output từ task vừa chạy (cảnh 2):
# Output sẽ như sau:
# {"backend": "flat2d", "pallet_to_dropoff_a_m": 0.000, "task_complete": true}

# Mở trace — "số này các bạn tự tính lại được":
python3 -c "
import json
from pathlib import Path
traces = sorted(Path('eval/results/traces').glob('*_aext_trace.json'))
if traces:
    t = json.loads(traces[-1].read_text())
    print('Task:', t['task_id'])
    print('Steps:', len(t['trace']))
    print('Oracle:', t['oracle'])
    for step in t['trace']:
        print(f\"  [{step['step']:02d}] {step['tool']}({json.dumps(step['input'])[:60]}) → {json.dumps(step['output'])[:60]}\")
"
```

**Nói với giám khảo:**
> "Mọi tool call đều được log vào JSONL trace. Bạn có thể tự tính lại từng bước mà không cần chạy lại agent. File traces: `eval/results/traces/`. SHA của run: `git log --oneline -1`."

---

## Recovery (nếu stack chết giữa chừng)

```bash
# Kill tất cả ROS processes:
bash /home/cth/AI20K/scripts/kill_ros.sh

# Đợi 5s, restart:
bash /home/cth/AI20K/scripts/start_demo.sh

# Verify Nav2 alive:
source /home/cth/AI20K/colcon_ws/install/setup.bash
ros2 action list | grep NavigateToPose
```

Thời gian recovery: warm ≈8s, cold ≈150s.

---

## Checklist trước khi bắt đầu demo

- [ ] `ollama list` → `qwen2.5:7b` có trong danh sách
- [ ] `gz model --list` → `warehouse_forklift` và `pallet_1` có trong world
- [ ] Foxglove WebSocket kết nối được (`ws://localhost:8765`)
- [ ] `git log --oneline -3` → SHA P4 commit cuối visible
- [ ] `cat docs/EVIDENCE.md` → bảng claim có ≥14 dòng

---

## Nhãn toàn bộ demo (paste vào slide):

```
model: ollama qwen2.5:7b ≠ Gemini official
GT-servo docking · pallet 2kg sim-simplified
vx≤0.25 carry · map rebaked lidar-0.625
AMCL GT-reinit (F4) active trên mọi số Gazebo
locate_object = GT registry (ARMBench = Pha 3)
```

---

> **Video:** Nếu có DISPLAY → `ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 demo_$(date +%Y%m%d_%H%M%S).mp4`
> Không commit video vào repo (nặng). Lưu local, ghi đường dẫn vào README hoặc EVIDENCE.md.
> Headless → runbook này là deliverable, Thái quay tay theo kịch bản trên.

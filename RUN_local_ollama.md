# Chạy local — Ollama (không cần API key)

Dùng khi chưa có GEMINI_API_KEY hoặc muốn chạy offline hoàn toàn.
Provider: `LLM_PROVIDER=ollama` → Ollama's `/v1/chat/completions` (OpenAI-compat).
Model mặc định: `qwen2.5:7b` — hỗ trợ tool_call format qua endpoint này.

---

## Bước 0 — Cài Ollama (1 lần)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

## Bước 1 — Khởi động Ollama + kéo model

```bash
ollama serve &                  # hoặc chạy dưới dạng systemd service
ollama pull qwen2.5:7b          # ~4.7 GB, kéo 1 lần
ollama list                     # xác nhận model có mặt
```

---

## Bước 2 — Smoke-test flat2d (không cần Gazebo)

```bash
cd ~/AI20K
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:7b

python3 -c "
from colcon_ws.src.warehouse_robot_agent.warehouse_robot_agent.flat2d_backend import Flat2DBackend
from colcon_ws.src.warehouse_robot_agent.warehouse_robot_agent.llm_agent import run_agent
m = run_agent(Flat2DBackend())
print('steps:', m['steps'], '  done:', m['done_called'])
print('tools called:', [t['tool'] for t in m['trace']])
"
```

**Chặn sớm ở đây nếu:**
- `ConnectionRefusedError` → Ollama chưa chạy (`ollama serve`)
- tool_calls rỗng nhưng model trả lời text → model không hỗ trợ tool_call format;
  thử `OLLAMA_MODEL=qwen2.5:14b` hoặc `llama3.1:8b`
- step count = 0 → `finish_reason=stop` ngay lần đầu; kiểm log `[agent] No tool calls`

---

## Bước 3 — Verify §6 (cần Gazebo stack)

```bash
bash ~/AI20K/scripts/start_demo.sh   # đợi Gazebo + Nav2 ready (~2 phút)

# §6.1 — gz topics
gz topic -l | grep -E "camera|imu|scan|odom|joint"

# §6.2 — ROS 2 topics
ros2 topic list | grep -E "camera|imu|odom|scan|tf"

# §6.3 — TF chain
ros2 run tf2_tools view_frames && evince frames.pdf

# §6.4 — sensor spot-checks
ros2 topic echo /imu --once
ros2 topic hz /odom
ros2 topic echo /scan --once

# §6.5 — Foxglove: mở ws://localhost:8765 trong browser
```

**Dán raw output vào báo cáo (Q1: không output = không tính).**

---

## Bước 4 — 1 task end-to-end Gazebo

```bash
source ~/AI20K/colcon_ws/install/setup.bash
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:7b
WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent
```

Kiểm: loop khép kín, agent gọi `done()`, oracle pass.

---

## Bước 5 — Bảng C (3 task eval)

```bash
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:7b
python3 eval/run_eval_gazebo.py
```

**Lưu ý:** success = `oracle_check PASS`, không phải `done_called`.
Tiêu đề Bảng C ghi `ollama:qwen2.5:7b` để phân biệt khỏi Gemini run.

---

## Bước 6 — B3(b) parity (flat2d ↔ Gazebo)

```bash
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:7b
python3 eval/parity_check.py --live-gazebo
```

Kết quả: 2 file trace + 1 file `_parity.md` trong `eval/results/traces/`.
Mở `_parity.md` để xác nhận:
- Cột 2 ghi `gazebo` (không phải `flat2d run2 (variance)`) ← B1 check
- Mode note: `✓ B3(b) PARITY ARTIFACT`

---

## Bước 7 — Commit + push

```bash
git add eval/results/traces/ eval/results/report_v2.md
git commit -m "Add Bảng C + B3(b) parity traces (Ollama qwen2.5:7b, T=0)"
git push
# → dán link CI xanh từ github.com/zerokhong1/AI20K-mayB/actions
```

---

## Model fallback (nếu qwen2.5:7b không hỗ trợ tool_call)

```bash
ollama pull llama3.1:8b
OLLAMA_MODEL=llama3.1:8b python3 -c "..."  # lặp bước 2
```

---

## Ghi nhớ

| Var | Default | Ghi chú |
|-----|---------|---------|
| `LLM_PROVIDER` | `gemini` | `ollama` để chạy local |
| `OLLAMA_MODEL` | `qwen2.5:7b` | override nếu cần |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | đổi nếu Ollama chạy port khác |
| `WORLD_BACKEND` | `flat2d` | `gazebo` khi Gazebo stack live |
| `GEMINI_API_KEY` | — | chỉ cần khi `LLM_PROVIDER=gemini` |

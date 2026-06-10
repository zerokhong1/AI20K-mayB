# AI20K — Warehouse Robot Agent

LLM-driven pick-and-deliver agent for an AWS warehouse world.  
One agent, two backends, same interface.

---

## Architecture overview

```
  goal_text
      │
      ▼
┌─────────────────────────────────────────────┐
│           LLM Agent  (Claude Opus 4.8)       │
│                                              │
│  perceive → locate_object → check_path      │
│  → move_to → pick → drop → oracle_check     │
└─────────────────────┬────────────────────────┘
                      │  WorldBackend  (abstract interface)
          ┌───────────┴────────────┐
          │                        │
┌─────────▼──────────┐   ┌─────────▼──────────┐
│  Flat2DBackend     │   │  GazeboBackend      │
│  (Máy A — 2D)      │   │  (Máy B — sim 3D)  │
│                    │   │                     │
│ • in-process, fast │   │ • ROS 2 Jazzy       │
│ • no ROS required  │   │ • Nav2 navigation   │
│ • CI-friendly      │   │ • Gazebo Harmonic   │
│ • offline eval     │   │ • foxglove_bridge   │
└────────────────────┘   └─────────────────────┘
 WORLD_BACKEND=flat2d     WORLD_BACKEND=gazebo
 ← Bảng A/B (official)    ← Bảng C (bonus showcase)
```

> **Scope boundary:** Bảng A and Bảng B are measured exclusively on `Flat2DBackend`.  
> Bảng C (Gazebo) is a **bonus sim→real showcase** — it demonstrates the same agent
> running against a physics simulator but is **not part of the official evaluation**.

---

## Quick start

### Flat2DBackend — no ROS, offline

```bash
cd ~/AI20K
pip install anthropic pytest

# Run one task
python3 -c "
from colcon_ws.src.warehouse_robot_agent.warehouse_robot_agent.flat2d_backend import Flat2DBackend
from colcon_ws.src.warehouse_robot_agent.warehouse_robot_agent.llm_agent import run_agent
backend = Flat2DBackend()
metrics = run_agent(backend)
print(metrics)
"

# Parity check (both backends offline)
python3 eval/parity_check.py --both-flat2d

# Durability test (5 consecutive dry-runs)
python3 eval/demo_durability.py --dry-run

# Full offline test suite
pytest tests/ -q
```

### GazeboBackend — Máy B only

```bash
# Start full stack (< 5 min from cold boot)
bash ~/AI20K/scripts/start_demo.sh

# Run agent against Gazebo
WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent

# Eval Gazebo tasks → Bảng C
python3 eval/run_eval_gazebo.py

# Expose foxglove_bridge externally (cloudflared/ngrok)
bash ~/AI20K/scripts/start_tunnel.sh
```

---

## Evaluation tables

| Table | Backend | Scope | File |
|-------|---------|-------|------|
| **Bảng A** | Flat2DBackend | Official evaluation — 2D tasks | `eval/results/report_v2.md` |
| **Bảng B** | Flat2DBackend | Official evaluation — extended | `eval/results/report_v2.md` |
| **Bảng C** | GazeboBackend | Bonus showcase only — n is small | `eval/results/report_v2.md` |

---

## Disclosure

| Item | Reality |
|------|---------|
| GazeboBackend | Physics simulation (Gazebo Harmonic) — not a physical robot |
| LLM Agent | Real Claude Opus 4.8 API calls; real tool results from ROS 2 |
| `locate_object` in Gazebo | Ground-truth pose from `gz model` (default). ARMBench depth detector hook integrated but model weights not yet trained — see [DISCLOSURE_armbench.md](DISCLOSURE_armbench.md). |
| Bảng C purpose | Evidence that the sim→real pathway works; same agent code, swapped backend |

---

## Project structure

```
AI20K/
├── README.md                   ← this file
├── ARCHITECTURE.md             ← technical design details
├── DISCLOSURE_armbench.md     ← ARMBench detector status + honesty statement
├── RUN_may_B.md               ← operator runbook (Máy B)
├── mayB.md                    ← checklist + planning
├── scripts/
│   ├── start_demo.sh          ← 1-command full stack startup
│   └── start_tunnel.sh        ← expose port 8765 externally
├── foxglove/
│   └── warehouse_demo.json    ← Foxglove Studio 3-panel layout
├── eval/
│   ├── tasks_m.json           ← task definitions (m1–m3)
│   ├── run_eval_gazebo.py     ← eval runner → Bảng C
│   ├── parity_check.py        ← 2D vs Gazebo trace comparison
│   ├── demo_durability.py     ← 5-consecutive-pass test
│   └── recovery_check.py     ← health check + restart timing
├── tests/                     ← 117 tests, no ROS required
└── colcon_ws/src/warehouse_robot_agent/
    ├── world_backend.py        ← abstract interface
    ├── flat2d_backend.py       ← Flat2DBackend
    ├── gazebo_backend.py       ← GazeboBackend (ROS 2)
    ├── llm_agent.py            ← agent loop + tool dispatch
    └── perception_node.py      ← ARMBench / gz-gt detector
```

---

## CI

Tests run without ROS on every push (GitHub Actions `ubuntu-latest`).  
GazeboBackend tests are automatically skipped when `rclpy` is absent.

```bash
pytest tests/ -v   # 117 tests, 0 ROS required
```

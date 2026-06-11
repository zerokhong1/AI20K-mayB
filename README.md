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
│           LLM Agent  (Gemini flash-lite)      │
│                                              │
│  perceive → locate_object → check_path      │
│  → move_to → pick → drop → oracle_check     │
└─────────────────────┬────────────────────────┘
                      │  WorldBackend  (abstract interface)
          ┌───────────┴────────────┐
          │                        │
┌─────────▼──────────┐   ┌─────────▼──────────┐
│  Flat2DBackend     │   │  GazeboBackend      │
│  (mayB parity ref) │   │  (Máy B — sim 3D)  │
│                    │   │                     │
│ • in-process, fast │   │ • ROS 2 Jazzy       │
│ • no ROS required  │   │ • Nav2 navigation   │
│ • CI-friendly      │   │ • Gazebo Harmonic   │
│ • offline eval     │   │ • foxglove_bridge   │
└────────────────────┘   └─────────────────────┘
 WORLD_BACKEND=flat2d     WORLD_BACKEND=gazebo
 ← 2D parity ref          ← Bảng C (bonus showcase)
   (mayB-internal)           (sim→real demo)
```

> **Scope boundary (mayB repo):** This repo contains a mayB-internal 2D parity reference
> and a Gazebo bonus showcase (Bảng C). **The official P0.1 Bảng A/B evaluation
> (LangGraph + Gemini flash-lite, n=33) lives in the BTC repo, not here.**
> Bảng C (Gazebo) is a bonus sim→real showcase — same agent code, different backend.

---

## Quick start

### Flat2DBackend — no ROS, offline

```bash
cd ~/AI20K
pip install google-genai pytest

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

> **Official P0.1 Bảng A/B** (LangGraph + Gemini flash-lite, n=33) = BTC repo, not here.
> Tables below are mayB-internal evidence only.

| Table | Backend | Scope | File |
|-------|---------|-------|------|
| **Bảng 2D-ref** | Flat2DBackend (mayB) | Interface parity reference — scripted agent (not LLM), confirms WorldBackend contract | `eval/results/report_v2.md` |
| **Bảng C** | GazeboBackend | Bonus sim→real showcase — n=3, not statistically representative | `eval/results/report_v2.md` |

> **Disclosure:** Agent in this repo uses Gemini flash-lite (same model as official BTC eval).
> Bảng 2D-ref results are NOT substitutable for official Bảng A/B numbers
> (different codebase, different runner, scripted ref ≠ LLM eval).

---

## Disclosure

| Item | Reality |
|------|---------|
| GazeboBackend | Physics simulation (Gazebo Harmonic) — not a physical robot |
| LLM Agent (mayB) | Gemini flash-lite (`gemini-flash-lite-latest`) via `google-genai` SDK. Same model as official BTC eval; different runner (`llm_agent.py` direct, not LangGraph). |
| `locate_object` in Gazebo | Ground-truth pose from `gz model` (default). ARMBench depth detector hook integrated but model weights not yet trained — see [DISCLOSURE_armbench.md](DISCLOSURE_armbench.md). |
| Bảng 2D-ref | mayB-internal parity test on Flat2DBackend with scripted agent. NOT the official P0.1 Bảng A/B. |
| Bảng C purpose | Evidence that the sim→real pathway works; same WorldBackend interface, swapped backend. Bonus track only. |

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

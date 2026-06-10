# ARCHITECTURE — Warehouse Robot Agent

---

## 1. Design principle

> **One agent, two backends, same interface.**

The LLM agent never imports a backend directly. It calls methods on a `WorldBackend`
abstract class. Swapping the backend — from a fast in-process 2D simulation to a full
ROS 2 + Gazebo stack — requires zero changes to agent code.

---

## 2. Component diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      warehouse_robot_agent                        │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  LLM Agent  (llm_agent.py)                                │    │
│  │                                                            │    │
│  │  Client: anthropic.Anthropic  (Claude Opus 4.8)           │    │
│  │  Tool loop: perceive → locate_object → check_path         │    │
│  │             → move_to → pick → drop → oracle_check        │    │
│  │             → done                                         │    │
│  │                                                            │    │
│  │  dispatch(tool_name, args, backend) → result JSON          │    │
│  └──────────────────────┬───────────────────────────────────┘    │
│                          │ WorldBackend (world_backend.py)         │
│          ┌───────────────┴──────────────────┐                     │
│          │                                  │                     │
│  ┌───────▼────────────┐          ┌──────────▼──────────────┐     │
│  │  Flat2DBackend     │          │  GazeboBackend           │     │
│  │  (flat2d_backend)  │          │  (gazebo_backend)        │     │
│  │                    │          │                          │     │
│  │ _robot: Pose2D     │          │ _node: GazeboBackendNode │     │
│  │ _objects: dict     │          │   ├ /odom subscriber     │     │
│  │ _carrying: str?    │          │   ├ /warehouse/detected  │     │
│  │                    │          │   │  _objects subscriber │     │
│  │ Instant success    │          │   └ /fork_cmd publisher  │     │
│  │ No external deps   │          │                          │     │
│  │ CI-safe            │          │ Nav2 NavigateToPose      │     │
│  └────────────────────┘          │ Nav2 ComputePathToPose   │     │
│   WORLD_BACKEND=flat2d           │ gz CLI (oracle/teleport) │     │
│   ← 2D parity ref (mayB-internal)          └──────────────────────────┘     │
│                                   WORLD_BACKEND=gazebo             │
│                                   ← Bảng C (bonus showcase)        │
└──────────────────────────────────────────────────────────────────┘

External (Gazebo stack — Máy B only):
  Gazebo Harmonic ← ros_gz_bridge ← Nav2 ← GazeboBackend
  PerceptionNode → /warehouse/detected_objects → GazeboBackend
  foxglove_bridge :8765 ← Foxglove Studio (browser/desktop)
```

---

## 3. `WorldBackend` interface

Defined in `world_backend.py`. All backends implement every method.

```python
class WorldBackend(ABC):
    def perceive(self) -> WorldView: ...
    # Returns: robot_pose (Pose2D), objects (dict), map_info (str)

    def locate_object(self, name: str) -> Optional[Pose2D]: ...
    # Flat2D:  registry lookup
    # Gazebo:  ARMBench depth detector → fallback gz CLI → fallback registry

    def check_path(self, x, y) -> bool: ...
    # Flat2D:  always True (no obstacles modelled)
    # Gazebo:  Nav2 ComputePathToPose action

    def move_to(self, x, y, yaw=0.0) -> bool: ...
    # Flat2D:  instant teleport; moves carried pallet with robot
    # Gazebo:  Nav2 NavigateToPose action (blocks until done)

    def pick(self, object_name: str) -> bool: ...
    # Flat2D:  set _carrying = object_name
    # Gazebo:  fork_cmd publisher (raise fork), update internal state

    def drop(self, x, y) -> bool: ...
    # Flat2D:  place object at (x, y), clear _carrying
    # Gazebo:  fork_cmd publisher (lower fork), place in world state

    def oracle_check(self) -> dict: ...
    # Flat2D:  {"backend": "flat2d", "task_complete": bool, "pallet_to_dropoff_a_m": float}
    # Gazebo:  gz model -p → real pallet pose → distance to dropoff_a
```

Both backends also expose `locate_log: list[str]` — append-only trace of
the source used in each `locate_object` call (`"gt_registry"`, `"gz_cli"`,
`"perception(armbench_depth)"`, etc.).

---

## 4. `WORLD_BACKEND` flag

The environment variable `WORLD_BACKEND` selects the backend at runtime.

| Value | Backend | Requires |
|-------|---------|----------|
| `flat2d` (default) | `Flat2DBackend` | Python only |
| `gazebo` | `GazeboBackend` | ROS 2 Jazzy + Gazebo Harmonic |

**How it works in practice:**

```bash
# Flat2D (offline, CI, Máy A)
python3 -c "from flat2d_backend import Flat2DBackend; ..."

# Gazebo (Máy B, live demo)
WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent
```

`llm_agent.main()` imports `rclpy` and `GazeboBackend` lazily (inside `main()`)
so that `dispatch()`, `run_agent()`, and the tool definitions can be imported
by CI test runners without ROS installed.

---

## 5. Evaluation scope boundary

```
┌─────────────────────────────────────────────────┐
│  OFFICIAL P0.1 Bảng A/B — NOT IN THIS REPO      │
│                                                   │
│  Repo    : BTC repo (Máy A)                      │
│  Agent   : LangGraph + Gemini flash-lite         │
│  Runner  : eval/run_eval_v2.py                   │
│  N       : 33                                     │
│                                                   │
│  These are the numbers that go into the report.  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  PARITY REFERENCE (mayB-internal, 2D)            │
│                                                   │
│  Backend : Flat2DBackend                         │
│  Agent   : Claude Opus 4.8 (scripted for ref)    │
│  Runner  : eval/run_eval_flat2d.py               │
│  Purpose : verify WorldBackend interface works;  │
│            NOT substitutable for P0.1 Bảng A/B  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  BONUS SHOWCASE (Bảng C)                         │
│                                                   │
│  Backend : GazeboBackend                         │
│  Machine : Máy B (Ubuntu, ROS 2)                 │
│  Oracle  : gz model -p (ground-truth pose)       │
│  N       : small (≥ 3 tasks, not statistically   │
│            representative)                       │
│                                                   │
│  Purpose : demonstrate sim→real pathway.         │
│  NOT used for grading. Disclosed in report.      │
└─────────────────────────────────────────────────┘
```

The boundary is enforced structurally: `run_eval_gazebo.py` writes **only to
Bảng C** in `report_v2.md`, never to Bảng A/B.

---

## 6. Parity evidence ("1 agent – 2 backend")

`eval/parity_check.py` runs the same goal through both backends and
produces a side-by-side trace comparison using LCS alignment:

```
Tool sequence comparison (LCS-aligned):

Step │ Flat2DBackend          │ GazeboBackend
─────┼────────────────────────┼────────────────────────
  1  │ ✓ perceive             │ ✓ perceive
  2  │ ✓ locate_object        │ ✓ locate_object
  3  │ ✓ check_path           │ ✓ check_path
  4  │                        │ ＋ check_path  (extra)
  5  │ ✓ move_to              │ ✓ move_to
  6  │ ✓ pick                 │ ✓ pick
  7  │ ✓ move_to              │ ✓ move_to
  8  │ ✓ drop                 │ ✓ drop
  9  │ ✓ oracle_check         │ ✓ oracle_check
 10  │ ✓ done                 │ ✓ done

Similarity: 90.9 %
```

`✓` = both backends called this tool  
`＋gz` = Gazebo-only extra call (e.g. Nav2 path validation before long move)  
`＋2d` = Flat2D-only call

---

## 7. Perception pipeline (GazeboBackend)

```
/camera/depth/image_raw (sensor_msgs/Image)
        │
        ▼  ARMBenchDetector._run_model()
           [stub — swap in YOLOv8/ONNX weights here]
           fallback: depth blob detection
        │
        ▼  _to_map_pose(): pixel + depth → map-frame Pose2D
           (uses robot pose from /odom + camera intrinsics)
        │
        ▼  PerceptionNode._publish()
           merge with ground-truth for unseen objects
        │
        ▼  /warehouse/detected_objects  (std_msgs/String, JSON)
        │
        ▼  GazeboBackend.locate_object()
           logs source: "perception(armbench_depth)" | "gt_registry" | "gz_cli"
```

`locate_log` on each backend accumulates source strings per run.
`run_eval_gazebo.py` summarises them in Bảng C column "locate_object source".

> **Implementation status:** `ARMBenchDetector._load_model()` raises `NotImplementedError` —
> no model weights exist. Default mode is `gz_gt` (ground-truth from Gazebo CLI).
> Full status and Q&A guidance: [DISCLOSURE_armbench.md](../DISCLOSURE_armbench.md).

---

## 8. Recovery layers

Four restart granularities, lightest to heaviest:

| Layer | Component | Estimated restart | Kill command |
|-------|-----------|-------------------|--------------|
| L1 | foxglove_bridge | ~8 s | `pkill -f foxglove_bridge` |
| L2 | Nav2 stack | ~25 s | `pkill -f nav2` |
| L3 | Gazebo + world | ~50 s | `pkill -f 'gz sim'` |
| L4 | Full stack | ~3 min | `bash scripts/start_demo.sh` |

Automated: `python3 eval/recovery_check.py --check` / `--restart <layer>`  
Measured times persisted in `eval/results/recovery_times.json`.

---

## 9. CI / testing

```
tests/
├── test_world_backend_contract.py   # BackendContractMixin × Flat2D + 11 dispatch tests
├── test_demo_durability.py          # simulate_task, dry runs, failure classification
├── test_recovery_check.py           # layer definitions, restart times, health checks
└── test_foxglove_layout.py          # validates foxglove/warehouse_demo.json
```

GazeboBackend import tests carry `@pytest.mark.skipif(not ROS_AVAILABLE, ...)` —
they are skipped in GitHub Actions (`ubuntu-latest`, no ROS).

All other tests (107/117) always run.

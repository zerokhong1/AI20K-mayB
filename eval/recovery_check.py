#!/usr/bin/env python3
"""
Recovery check — timed layer-by-layer restart for Gazebo/Nav2/bridge.

Measures actual time-to-ready for each layer. Results are saved to
eval/results/recovery_times.json and a human-readable report to
eval/results/recovery_times.md.

Layers (restart from lightest to heaviest):
  L1  foxglove_bridge   — WebSocket viz bridge (port 8765)
  L2  Nav2              — navigation action server
  L3  Gazebo            — physics simulation
  L4  Full stack        — kill everything + start_demo.sh

Modes
─────
  --check          Health check only; no restarts (default)
  --restart LAYER  Restart one layer and measure time-to-ready
                   LAYER ∈ {foxglove, nav2, gazebo, full}
  --measure-all    Restart each layer in sequence and record times
                   (destructive — kills the running stack)
  --dry-run        Print commands + load previously measured times

Usage
─────
  source colcon_ws/install/setup.bash
  python3 eval/recovery_check.py --check
  python3 eval/recovery_check.py --restart foxglove
  python3 eval/recovery_check.py --measure-all
  python3 eval/recovery_check.py --dry-run       # offline / CI
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR / "results"
TIMES_JSON  = RESULTS_DIR / "recovery_times.json"
REPORT_MD   = RESULTS_DIR / "recovery_times.md"
WS          = Path.home() / "AI20K" / "colcon_ws"
START_SCRIPT = Path(__file__).parent.parent / "scripts" / "start_demo.sh"


# ══════════════════════════════════════════════════════════════════════════════
# Layer definitions
# ══════════════════════════════════════════════════════════════════════════════

class Layer:
    """Everything the harness needs to know about one service layer."""

    def __init__(self, id_, name, kill_cmds, start_cmd,
                 ready_fn, ready_desc, poll_interval=1.0, timeout=90.0):
        self.id            = id_
        self.name          = name
        self.kill_cmds     = kill_cmds    # list of shell strings
        self.start_cmd     = start_cmd    # shell string (backgrounded)
        self.ready_fn      = ready_fn     # () -> bool
        self.ready_desc    = ready_desc   # human description of ready_fn
        self.poll_interval = poll_interval
        self.timeout       = timeout


def _run(cmd: str, timeout: float = 30.0, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, capture_output=True,
                          text=True, timeout=timeout, **kwargs)


def _check_port(port: int) -> bool:
    r = subprocess.run(["nc", "-z", "-w", "1", "localhost", str(port)],
                       capture_output=True, timeout=3)
    return r.returncode == 0


def _check_ros_node(pattern: str) -> bool:
    # `timeout 3` gives DDS discovery a hard OS-level deadline.
    try:
        r = _run("timeout 3 ros2 node list 2>/dev/null", timeout=5.0)
        return pattern in r.stdout
    except subprocess.TimeoutExpired:
        return False


def _check_ros_action(pattern: str) -> bool:
    try:
        r = _run("timeout 3 ros2 action list 2>/dev/null", timeout=5.0)
        return pattern in r.stdout
    except subprocess.TimeoutExpired:
        return False


def _check_gz_model(pattern: str) -> bool:
    try:
        r = _run("timeout 4 gz model --list 2>/dev/null", timeout=6.0)
        return r.returncode == 0 and pattern in r.stdout
    except subprocess.TimeoutExpired:
        return False


WS_SOURCE = f"source {WS}/install/setup.bash"

LAYERS: list[Layer] = [
    Layer(
        id_         = "foxglove",
        name        = "foxglove_bridge (L1)",
        kill_cmds   = ["pkill -f foxglove_bridge || true"],
        start_cmd   = (f"{WS_SOURCE} && "
                       "ros2 launch foxglove_bridge foxglove_bridge_launch.xml &"),
        ready_fn    = lambda: _check_port(8765),
        ready_desc  = "nc -z localhost 8765",
        poll_interval = 1.0,
        timeout     = 20.0,
    ),
    Layer(
        id_         = "nav2",
        name        = "Nav2 navigation stack (L2)",
        kill_cmds   = [
            "ros2 lifecycle set /nav2_lifecycle_manager shutdown 2>/dev/null || true",
            "pkill -f nav2 || true",
            "pkill -f controller_server || true",
        ],
        start_cmd   = (
            f"{WS_SOURCE} && "
            "ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true "
            f"map:={WS}/src/aws-robomaker-small-warehouse-world/maps/005/map.yaml &"
        ),
        ready_fn    = lambda: _check_ros_action("navigate_to_pose"),
        ready_desc  = "ros2 action list | grep navigate_to_pose",
        poll_interval = 2.0,
        timeout     = 60.0,
    ),
    Layer(
        id_         = "gazebo",
        name        = "Gazebo Harmonic + AWS world (L3)",
        kill_cmds   = [
            "pkill -f 'gz sim' || true",
            "pkill -f 'gz_server' || true",
            "sleep 2",
        ],
        start_cmd   = (
            f"{WS_SOURCE} && "
            "ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py &"
        ),
        ready_fn    = lambda: _check_gz_model("PalletJack"),
        ready_desc  = "gz model --list | grep PalletJack",
        poll_interval = 3.0,
        timeout     = 120.0,
    ),
    Layer(
        id_         = "full",
        name        = "Full stack (L4)",
        kill_cmds   = [
            "pkill -f 'gz sim' || true",
            "pkill -f 'ros2 launch' || true",
            "pkill -f 'ros2 run' || true",
            "pkill -f foxglove || true",
            "sleep 3",
        ],
        start_cmd   = f"bash {START_SCRIPT} &",
        ready_fn    = lambda: (
            _check_gz_model("PalletJack") and
            _check_ros_action("navigate_to_pose") and
            _check_port(8765)
        ),
        ready_desc  = "Gazebo + Nav2 + foxglove_bridge all ready",
        poll_interval = 5.0,
        timeout     = 300.0,
    ),
]

LAYER_MAP = {l.id: l for l in LAYERS}


# ══════════════════════════════════════════════════════════════════════════════
# Health check
# ══════════════════════════════════════════════════════════════════════════════

def check_health() -> list[dict]:
    rows = []
    for layer in LAYERS:
        try:
            healthy = layer.ready_fn()
        except Exception as e:
            healthy = False
        rows.append({
            "id":          layer.id,
            "name":        layer.name,
            "healthy":     healthy,
            "check":       layer.ready_desc,
        })
    return rows


def print_health(rows: list[dict]) -> None:
    print("\n[recovery] Health check")
    print(f"  {'Layer':<35} {'Status':<10} Check")
    print("  " + "-" * 65)
    for r in rows:
        status = "OK  ✓" if r["healthy"] else "DEAD ✗"
        print(f"  {r['name']:<35} {status:<10} {r['check']}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Timed restart
# ══════════════════════════════════════════════════════════════════════════════

class RestartResult:
    def __init__(self, layer_id: str, elapsed_s: float | None,
                 success: bool, error: str = ""):
        self.layer_id  = layer_id
        self.elapsed_s = elapsed_s
        self.success   = success
        self.error     = error

    def to_dict(self) -> dict:
        return {"layer_id": self.layer_id, "elapsed_s": self.elapsed_s,
                "success": self.success, "error": self.error}


def restart_layer(layer: Layer, dry_run: bool = False) -> RestartResult:
    print(f"\n[recovery] Restarting {layer.name} …")

    if dry_run:
        print(f"[recovery] (dry-run) kill: {layer.kill_cmds}")
        print(f"[recovery] (dry-run) start: {layer.start_cmd}")
        return RestartResult(layer.id, elapsed_s=None, success=None)

    # 1. Kill
    for cmd in layer.kill_cmds:
        print(f"[recovery]   kill: {cmd}")
        try:
            subprocess.run(cmd, shell=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass
    time.sleep(1.0)

    # 2. Start (backgrounded)
    print(f"[recovery]   start: {layer.start_cmd[:80]}…")
    try:
        subprocess.Popen(layer.start_cmd, shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return RestartResult(layer.id, elapsed_s=None,
                             success=False, error=str(e))

    # 3. Poll until ready
    t0 = time.time()
    print(f"[recovery]   waiting for: {layer.ready_desc}")
    while True:
        elapsed = time.time() - t0
        try:
            if layer.ready_fn():
                elapsed_s = round(elapsed, 1)
                print(f"[recovery]   ready in {elapsed_s} s ✓")
                return RestartResult(layer.id, elapsed_s=elapsed_s, success=True)
        except Exception:
            pass
        if elapsed > layer.timeout:
            print(f"[recovery]   TIMEOUT after {layer.timeout} s ✗")
            return RestartResult(layer.id, elapsed_s=None,
                                 success=False, error=f"timeout {layer.timeout}s")
        time.sleep(layer.poll_interval)


# ══════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════

# Expected recovery times (seconds) — used when no measured data is available.
# Updated automatically each time --measure-all or --restart is run.
_EXPECTED_S = {
    "foxglove": 8,
    "nav2":     25,
    "gazebo":   50,
    "full":     180,
}


def _load_times() -> dict:
    if TIMES_JSON.exists():
        data = json.loads(TIMES_JSON.read_text())
        return data.get("measured", {})
    return {}


def _save_times(results: list[RestartResult], run_ts: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if TIMES_JSON.exists():
        existing = json.loads(TIMES_JSON.read_text()).get("measured", {})
    for r in results:
        if r.success and r.elapsed_s is not None:
            existing[r.layer_id] = {
                "elapsed_s": r.elapsed_s,
                "measured_at": run_ts,
            }
    TIMES_JSON.write_text(json.dumps(
        {"measured": existing, "updated": run_ts}, indent=2))


def _write_report(health: list[dict] | None,
                  results: list[RestartResult],
                  run_ts: str,
                  dry_run: bool) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    measured = _load_times()
    dry_tag = " *(dry-run)*" if dry_run else ""

    # ── recovery time table ──────────────────────────────────────────── #
    time_rows = ""
    for layer in LAYERS:
        m = measured.get(layer.id)
        if m:
            t_str   = f"**{m['elapsed_s']} s** (measured {m['measured_at'][:10]})"
        else:
            t_str   = f"~{_EXPECTED_S[layer.id]} s (estimate — not yet measured)"

        kill_cmds = "; ".join(layer.kill_cmds).replace("|", "\\|")
        time_rows += (
            f"| {layer.name} | `{kill_cmds[:60]}…` | "
            f"`{layer.start_cmd[:55]}…` | {t_str} |\n"
        )

    # ── health check table (if checked) ──────────────────────────────── #
    health_section = ""
    if health:
        health_rows = ""
        for h in health:
            ok = "✓" if h["healthy"] else "✗"
            health_rows += f"| {h['name']} | {ok} | `{h['check']}` |\n"
        health_section = f"""
## Health check — {run_ts}

| Layer | Status | Check command |
|-------|--------|---------------|
{health_rows}
"""

    # ── restart results (if measured) ────────────────────────────────── #
    results_section = ""
    if results:
        result_rows = ""
        for r in results:
            layer = LAYER_MAP.get(r.layer_id)
            name  = layer.name if layer else r.layer_id
            if r.elapsed_s is not None:
                t_str = f"{r.elapsed_s} s"
            elif dry_run:
                t_str = "*(dry-run)*"
            else:
                t_str = "TIMEOUT ✗"
            ok = "✓" if r.success else ("—" if r.success is None else "✗")
            result_rows += f"| {name} | {ok} | {t_str} |\n"
        results_section = f"""
## Measured restart times{dry_tag} — {run_ts}

| Layer | Result | Time to ready |
|-------|--------|---------------|
{result_rows}
"""

    report = f"""\
# Recovery Procedures — Gazebo/Nav2/foxglove_bridge{dry_tag}

> Last updated: {run_ts}
> Workspace: `{WS}`

## Layered restart commands

| Layer | Kill | Start | Time to ready |
|-------|------|-------|---------------|
{time_rows}

## Recovery decision tree

```
Demo breaks
    │
    ├─ foxglove viz frozen?  → restart L1 foxglove_bridge  (~{_EXPECTED_S['foxglove']} s)
    │
    ├─ Nav2 not responding?  → restart L2 Nav2             (~{_EXPECTED_S['nav2']} s)
    │    (move_to always fails, agent loops)
    │
    ├─ Gazebo frozen/crash?  → restart L3 Gazebo            (~{_EXPECTED_S['gazebo']} s)
    │    (gz model --list empty)
    │
    └─ Multiple layers dead? → restart L4 Full stack        (~{_EXPECTED_S['full'] // 60} min)
         ./scripts/start_demo.sh
```

## Quick-reference commands

```bash
# L1 — foxglove_bridge only
pkill -f foxglove_bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml &

# L2 — Nav2 only
pkill -f nav2; pkill -f controller_server
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true \\
    map:=~/AI20K/colcon_ws/src/aws-robomaker-small-warehouse-world/maps/005/map.yaml &

# L3 — Gazebo only
pkill -f 'gz sim'; sleep 2
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py &

# L4 — Full stack (nuclear option)
pkill -f 'gz sim'; pkill -f 'ros2 launch'; pkill -f 'ros2 run'; pkill -f foxglove
sleep 3
bash ~/AI20K/scripts/start_demo.sh

# Reset pallet to spawn (between attempts without full restart)
gz service -s /world/small_warehouse/set_pose \\
  --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 3000 \\
  --req 'name: "aws_robomaker_warehouse_PalletJackB_01_001" \\
         position: {{x: -0.28, y: -9.48, z: 0.1}} \\
         orientation: {{x: 0.0, y: 0.0, z: 0.0, w: 1.0}}'

# Check stack health
python3 ~/AI20K/eval/recovery_check.py --check
```

## Measure actual times

```bash
# Measure restart time for one layer (live, destructive):
python3 eval/recovery_check.py --restart foxglove
python3 eval/recovery_check.py --restart nav2
python3 eval/recovery_check.py --restart gazebo

# Measure all layers in sequence (kills the running stack):
python3 eval/recovery_check.py --measure-all
```
{health_section}{results_section}"""

    REPORT_MD.write_text(report)
    print(f"[recovery] Report → {REPORT_MD}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Recovery check and timing tool")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check",       action="store_true",
                      help="Health check only (no restarts)")
    mode.add_argument("--restart",     metavar="LAYER",
                      choices=list(LAYER_MAP),
                      help="Restart one layer and time recovery")
    mode.add_argument("--measure-all", action="store_true",
                      help="Restart each layer in sequence (destructive)")
    mode.add_argument("--dry-run",     action="store_true",
                      help="Print commands + load stored times; no execution")
    args = parser.parse_args()

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    health_rows = None
    results: list[RestartResult] = []

    if args.dry_run:
        print("[recovery] dry-run mode — no commands executed")
        results = [RestartResult(l.id, elapsed_s=None, success=None)
                   for l in LAYERS]
        _write_report(None, results, run_ts, dry_run=True)
        _print_stored_times()
        return

    if args.check or not any([args.check, args.restart, args.measure_all]):
        health_rows = check_health()
        print_health(health_rows)
        _write_report(health_rows, [], run_ts, dry_run=False)
        return

    if args.restart:
        layer = LAYER_MAP[args.restart]
        r = restart_layer(layer)
        results = [r]
        _save_times(results, run_ts)
        health_rows = check_health()
        print_health(health_rows)
        _write_report(health_rows, results, run_ts, dry_run=False)
        if r.success:
            print(f"[recovery] ✓ {layer.name} recovered in {r.elapsed_s} s")
        else:
            print(f"[recovery] ✗ {layer.name} recovery FAILED: {r.error}")
            sys.exit(1)
        return

    if args.measure_all:
        print("[recovery] measure-all — restarting each layer in sequence …")
        for layer in LAYERS:
            r = restart_layer(layer)
            results.append(r)
        _save_times(results, run_ts)
        _write_report(None, results, run_ts, dry_run=False)
        _print_summary(results)
        return


def _print_stored_times() -> None:
    measured = _load_times()
    print("\n[recovery] Stored recovery times:")
    for layer in LAYERS:
        m = measured.get(layer.id)
        if m:
            print(f"  {layer.name:<35} {m['elapsed_s']} s  (measured {m['measured_at'][:10]})")
        else:
            print(f"  {layer.name:<35} ~{_EXPECTED_S[layer.id]} s  (estimate — not yet measured)")


def _print_summary(results: list[RestartResult]) -> None:
    print("\n[recovery] ══════════════════════════════")
    for r in results:
        layer = LAYER_MAP.get(r.layer_id)
        name  = layer.name if layer else r.layer_id
        if r.success:
            print(f"[recovery] ✓ {name}: {r.elapsed_s} s")
        elif r.success is None:
            print(f"[recovery] — {name}: (dry-run)")
        else:
            print(f"[recovery] ✗ {name}: FAILED — {r.error}")


if __name__ == "__main__":
    main()

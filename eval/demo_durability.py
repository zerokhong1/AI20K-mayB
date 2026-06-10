#!/usr/bin/env python3
"""
Demo durability check — "5 lần liên tiếp không fail".

Runs the canonical demo task N times in sequence (default 5), resets
world state between attempts, and verifies a full consecutive streak.

Records per-attempt: attempt #, success, steps, elapsed time, oracle
result, failure classification, and suggested remediation.

Exits 0 only when the full streak is achieved.

Usage
─────
  source colcon_ws/install/setup.bash
  python3 eval/demo_durability.py              # 5× live Gazebo
  python3 eval/demo_durability.py --n 3        # 3× live Gazebo
  python3 eval/demo_durability.py --dry-run    # offline (Flat2DBackend)

Output
──────
  eval/results/demo_durability.md   — human-readable report
  eval/results/demo_durability.json — raw JSON for CI/tools
"""

import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR / "results"
MD_OUT      = RESULTS_DIR / "demo_durability.md"
JSON_OUT    = RESULTS_DIR / "demo_durability.json"

PALLET_SPAWN_X = -0.28
PALLET_SPAWN_Y = -9.48
PALLET_MODEL   = "aws_robomaker_warehouse_PalletJackB_01_001"
DROPOFF_A      = (0.0, 0.0)
THRESHOLD_M    = 1.5

# Canonical demo task — same goal every run
DEMO_GOAL = (
    "Retrieve the pallet_jack from its storage location "
    "and deliver it to drop-off zone A (dropoff_a at coordinates 0, 0)."
)

# ── optional ROS imports ──────────────────────────────────────────────────── #
try:
    import rclpy
    from warehouse_robot_agent.gazebo_backend import (
        GazeboBackend, GazeboBackendNode, _gz_model_pose,
    )
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False

try:
    from warehouse_robot_agent.flat2d_backend import Flat2DBackend
    from warehouse_robot_agent.llm_agent import run_agent
    AGENT_AVAILABLE = True
except ImportError as _e:
    AGENT_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# Failure classification
# ══════════════════════════════════════════════════════════════════════════════

class FailureCode:
    MAX_STEPS        = "max_steps_exceeded"
    NO_DONE          = "agent_no_done_call"
    NAV_FAILURE      = "navigation_failure"
    PICK_FAILURE     = "pick_failure"
    PALLET_NOT_MOVED = "pallet_not_moved"
    GZ_UNAVAILABLE   = "gazebo_unavailable"
    UNKNOWN          = "unknown"


# Maps FailureCode → recovery suggestion shown in the report
REMEDIATION: dict[str, str] = {
    FailureCode.MAX_STEPS: (
        "Agent hit the 30-call cap. Check if Nav2 is reporting false success "
        "or the LLM is looping. Restart Nav2: "
        "`ros2 launch nav2_bringup navigation_launch.py`"
    ),
    FailureCode.NO_DONE: (
        "Agent loop ended without calling done(). Likely a stop_reason mismatch. "
        "Check ROS logs for Action server timeouts. Restart agent node."
    ),
    FailureCode.NAV_FAILURE: (
        "move_to() returned False. Nav2 action server may have timed out or the "
        "global costmap is stale. Run: `ros2 lifecycle set /nav2_lifecycle_manager configure` "
        "or kill and relaunch the Nav2 stack."
    ),
    FailureCode.PICK_FAILURE: (
        "pick() returned False or fork command was not acknowledged. "
        "Check /fork_cmd subscriber is alive: `ros2 topic echo /fork_cmd`. "
        "If silent, restart the fork controller node."
    ),
    FailureCode.PALLET_NOT_MOVED: (
        "Oracle shows pallet never reached dropoff_a. Robot may have navigated "
        "without physically pushing the pallet. Verify fork height on pick: "
        "set to 0.20 m before move_to(dropoff_a)."
    ),
    FailureCode.GZ_UNAVAILABLE: (
        "gz CLI returned no pose data — Gazebo may have crashed or the world "
        "model name changed. Check with: `gz model --list`. "
        "Restart the sim stack: `tmux kill-session -t demo && ./start_demo.sh`"
    ),
    FailureCode.UNKNOWN: (
        "Unclassified failure. Check `ros2 log` and agent stdout for errors."
    ),
}


def classify_failure(row: dict) -> str:
    oracle = row.get("oracle", {})
    metrics = row.get("metrics", {})
    steps   = row.get("steps", 0) or 0

    if oracle.get("pallet_gt") == "gz_cli_unavailable":
        return FailureCode.GZ_UNAVAILABLE
    if steps >= 30:
        return FailureCode.MAX_STEPS
    if not metrics.get("done_called"):
        return FailureCode.NO_DONE

    dist = oracle.get("dist_to_dropoff_a_m")
    if dist is not None and dist >= THRESHOLD_M:
        # Pallet stayed far from dropoff — distinguish nav vs pick
        pallet_gt = oracle.get("pallet_gt", "")
        # If pallet is still at spawn area, pick likely never happened
        if pallet_gt and _near_spawn(pallet_gt):
            return FailureCode.PICK_FAILURE
        return FailureCode.PALLET_NOT_MOVED

    return FailureCode.UNKNOWN


def _near_spawn(pose_str: str) -> bool:
    """Return True if a Pose2D string repr is close to the pallet spawn."""
    try:
        nums = re.findall(r"[-+]?\d+\.?\d*", pose_str)
        if len(nums) >= 2:
            x, y = float(nums[0]), float(nums[1])
            return math.sqrt((x - PALLET_SPAWN_X)**2 + (y - PALLET_SPAWN_Y)**2) < 1.5
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Pallet reset
# ══════════════════════════════════════════════════════════════════════════════

def _gz_teleport_pallet() -> bool:
    req = (
        f'name: "{PALLET_MODEL}" '
        f'position: {{x: {PALLET_SPAWN_X}, y: {PALLET_SPAWN_Y}, z: 0.1}} '
        f'orientation: {{x: 0.0, y: 0.0, z: 0.0, w: 1.0}}'
    )
    try:
        result = subprocess.run(
            ["gz", "service",
             "-s", "/world/small_warehouse/set_pose",
             "--reqtype", "gz.msgs.Pose",
             "--reptype", "gz.msgs.Boolean",
             "--timeout", "3000",
             "--req", req],
            capture_output=True, text=True, timeout=8.0,
        )
        return result.returncode == 0
    except Exception as exc:
        print(f"[durability] WARNING: pallet teleport failed — {exc}")
        return False


def _oracle_grade() -> dict:
    pallet_gt = _gz_model_pose(PALLET_MODEL)
    dist = None
    success = False
    if pallet_gt is not None:
        dx = pallet_gt.x - DROPOFF_A[0]
        dy = pallet_gt.y - DROPOFF_A[1]
        dist = math.sqrt(dx * dx + dy * dy)
        success = dist < THRESHOLD_M
    return {
        "pallet_gt":           str(pallet_gt) if pallet_gt else "gz_cli_unavailable",
        "dist_to_dropoff_a_m": round(dist, 3) if dist is not None else None,
        "success":             success,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Single-attempt runner
# ══════════════════════════════════════════════════════════════════════════════

def _run_attempt_live(attempt: int, backend) -> dict:
    backend.locate_log.clear()
    t0 = time.time()
    metrics = run_agent(backend, goal_text=DEMO_GOAL)
    elapsed = round(time.time() - t0, 1)
    oracle  = _oracle_grade()
    row = {
        "attempt":   attempt,
        "success":   oracle["success"],
        "steps":     metrics["steps"],
        "elapsed_s": elapsed,
        "metrics":   {k: v for k, v in metrics.items() if k != "trace"},
        "oracle":    oracle,
    }
    if not oracle["success"]:
        row["failure_code"] = classify_failure(row)
        row["remediation"]  = REMEDIATION[row["failure_code"]]
    return row


def _simulate_task(backend) -> dict:
    """Directly exercise the full task sequence without calling the LLM.

    Used by --dry-run so the harness validates backend + report logic
    without needing an Anthropic API key. Mirrors the canonical agent steps.
    """
    from warehouse_robot_agent.llm_agent import dispatch
    import json as _json

    steps = 0
    trace = []

    def call(name, inp=None):
        nonlocal steps
        steps += 1
        raw = dispatch(backend, name, inp or {})
        out = _json.loads(raw)
        trace.append({"step": steps, "tool": name, "input": inp or {}, "output": out})
        return out

    call("perceive")
    pallet = call("locate_object", {"name": "pallet_jack"})
    if pallet:
        call("check_path", {"x": pallet["x"], "y": pallet["y"]})
        call("move_to",    {"x": pallet["x"], "y": pallet["y"]})
    call("pick", {"object_name": "pallet_jack"})
    call("check_path", {"x": 0.0, "y": 0.0})
    call("move_to",    {"x": 0.0,  "y": 0.0})
    call("drop",       {"x": 0.0,  "y": 0.0})
    oracle_out = call("oracle_check")
    call("done", {"summary": "Pallet delivered to dropoff_a"})

    return {
        "steps":      steps,
        "done_called": True,
        "trace":      trace,
        "oracle_out": oracle_out,
    }


def _run_attempt_dry(attempt: int) -> dict:
    """Run against a fresh Flat2DBackend without LLM or ROS."""
    backend = Flat2DBackend()
    t0 = time.time()
    result = _simulate_task(backend)
    elapsed = round(time.time() - t0, 1)

    oracle_raw = backend.oracle_check()
    oracle = {
        "pallet_gt":           oracle_raw.get("pallet_pos", "—"),
        "dist_to_dropoff_a_m": oracle_raw.get("pallet_to_dropoff_a_m"),
        "success":             oracle_raw.get("task_complete", False),
    }
    row = {
        "attempt":   attempt,
        "success":   oracle["success"],
        "steps":     result["steps"],
        "elapsed_s": elapsed,
        "metrics":   {"done_called": result["done_called"], "steps": result["steps"]},
        "oracle":    oracle,
    }
    if not oracle["success"]:
        row["failure_code"] = classify_failure(row)
        row["remediation"]  = REMEDIATION[row["failure_code"]]
    return row


# ══════════════════════════════════════════════════════════════════════════════
# Report generation
# ══════════════════════════════════════════════════════════════════════════════

def _streak(rows: list[dict]) -> int:
    """Return the length of the current consecutive-pass streak (from end)."""
    streak = 0
    for r in reversed(rows):
        if r["success"]:
            streak += 1
        else:
            break
    return streak


def _write_report(rows: list[dict], n_target: int, run_ts: str, dry_run: bool) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    JSON_OUT.write_text(json.dumps({
        "run_ts":   run_ts,
        "n_target": n_target,
        "dry_run":  dry_run,
        "results":  rows,
    }, indent=2, ensure_ascii=False))
    print(f"[durability] JSON → {JSON_OUT}")

    passes = sum(1 for r in rows if r["success"])
    streak = _streak(rows)
    goal_met = streak >= n_target
    verdict = f"✅ STREAK {streak}/{n_target} — demo stable" if goal_met \
              else f"❌ STREAK {streak}/{n_target} — not yet stable"

    dry_tag = " *(dry-run — Flat2DBackend)*" if dry_run else ""

    # Table
    table = (
        "| # | Success | Steps | Time (s) | Dist→dropoff_a (m) | Note |\n"
        "|---|---------|-------|----------|--------------------|------|\n"
    )
    for r in rows:
        dist  = r["oracle"].get("dist_to_dropoff_a_m")
        dist_s = f"{dist:.3f}" if dist is not None else "—"
        ok    = "✓" if r["success"] else "✗"
        note  = r.get("failure_code", "") if not r["success"] else ""
        table += (
            f"| {r['attempt']} | {ok} | {r['steps']} | {r['elapsed_s']} "
            f"| {dist_s} | {note} |\n"
        )

    # Failure detail section
    failures = [r for r in rows if not r["success"]]
    failure_section = ""
    if failures:
        failure_section = "\n## Failure log\n\n"
        for r in failures:
            fc  = r.get("failure_code", FailureCode.UNKNOWN)
            rem = r.get("remediation", REMEDIATION[FailureCode.UNKNOWN])
            failure_section += (
                f"### Attempt {r['attempt']} — `{fc}`\n\n"
                f"- Steps taken: {r['steps']}\n"
                f"- Oracle: pallet at {r['oracle'].get('pallet_gt', '?')}, "
                f"dist = {r['oracle'].get('dist_to_dropoff_a_m', '?')} m\n"
                f"- done() called: {r['metrics'].get('done_called')}\n\n"
                f"**Remediation:** {rem}\n\n"
            )
    else:
        failure_section = "\n## Failure log\n\n*No failures recorded.*\n"

    report = f"""\
# Demo Durability — "5 lần liên tiếp không fail"{dry_tag}

> Run: {run_ts}
> Goal: *{DEMO_GOAL}*
> Target: {n_target} consecutive passes

## Result: {verdict}

| Metric | Value |
|--------|-------|
| Attempts completed | {len(rows)} |
| Passes | {passes}/{len(rows)} |
| Current streak | **{streak}/{n_target}** |
| Backend | {"Flat2DBackend (dry-run)" if dry_run else "GazeboBackend (live)"} |

## Attempt log

{table}
{failure_section}
## Recovery playbook

If the demo breaks during the actual presentation:

| Symptom | Command |
|---------|---------|
| Nav2 action server timeout | `ros2 lifecycle set /nav2_lifecycle_manager configure && ros2 lifecycle set /nav2_lifecycle_manager activate` |
| AMCL lost (pose jumps) | `ros2 topic pub /initialpose geometry_msgs/PoseWithCovarianceStamped '{{...}}'` at known spawn |
| Gazebo crash | `tmux kill-session -t demo && ./start_demo.sh` (< 5 min) |
| foxglove_bridge silent | `ros2 launch foxglove_bridge foxglove_bridge_launch.xml` |
| Agent hangs at max steps | `Ctrl-C` agent process, reset pallet, relaunch `ros2 run warehouse_robot_agent llm_agent` |

> **Plan B:** video offline on USB — launch with `vlc demo_gazebo.mp4` while recovery proceeds.
"""

    MD_OUT.write_text(report)
    print(f"[durability] Report → {MD_OUT}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Demo durability: N consecutive passes")
    parser.add_argument("--n", type=int, default=5,
                        help="Required consecutive passes (default 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use Flat2DBackend instead of live Gazebo")
    parser.add_argument("--no-reset", action="store_true",
                        help="Skip pallet teleport between attempts")
    args = parser.parse_args()

    if not AGENT_AVAILABLE:
        print("[durability] ERROR: warehouse_robot_agent package not importable")
        print("             Source the workspace: source colcon_ws/install/setup.bash")
        sys.exit(2)

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── dry-run path ────────────────────────────────────────────────────── #
    if args.dry_run or not ROS_AVAILABLE:
        if not args.dry_run:
            print("[durability] rclpy unavailable — switching to dry-run (Flat2DBackend)")
        rows = []
        for attempt in range(1, args.n + 1):
            print(f"\n[durability] ── Attempt {attempt}/{args.n} (Flat2D) ──")
            row = _run_attempt_dry(attempt)
            rows.append(row)
            _print_attempt_result(row)
        _write_report(rows, args.n, run_ts, dry_run=True)
        _exit_with_verdict(rows, args.n)
        return

    # ── live Gazebo path ────────────────────────────────────────────────── #
    rclpy.init()
    node    = GazeboBackendNode()
    backend = GazeboBackend(node)

    print("[durability] Waiting for AMCL/odom pose …")
    if not node.spin_until_pose(timeout=30.0):
        print("[durability] WARNING: No pose in 30 s — is the sim running?")

    rows = []
    try:
        for attempt in range(1, args.n + 1):
            print(f"\n[durability] ════════════════════════════════")
            print(f"[durability] Attempt {attempt}/{args.n}")
            print(f"[durability] ════════════════════════════════")

            if attempt > 1 and not args.no_reset:
                print("[durability] Resetting pallet …")
                if _gz_teleport_pallet():
                    print("[durability] Pallet reset OK — settling 2 s …")
                    time.sleep(2.0)
                else:
                    print("[durability] WARNING: pallet reset failed")

            row = _run_attempt_live(attempt, backend)
            rows.append(row)
            _print_attempt_result(row)

            # Stop early if we already know we can't hit the target
            remaining = args.n - attempt
            current_streak = _streak(rows)
            if current_streak == 0 and remaining < args.n:
                print(f"[durability] Streak broken at attempt {attempt} — "
                      f"need {args.n} consecutive; continuing …")

    except KeyboardInterrupt:
        print("\n[durability] Interrupted — writing partial results.")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    _write_report(rows, args.n, run_ts, dry_run=False)
    _exit_with_verdict(rows, args.n)


def _print_attempt_result(row: dict) -> None:
    verdict = "PASS ✓" if row["success"] else f"FAIL ✗ [{row.get('failure_code', '?')}]"
    print(
        f"[durability] → {verdict} | steps={row['steps']} | "
        f"time={row['elapsed_s']}s | dist={row['oracle'].get('dist_to_dropoff_a_m')}m"
    )


def _exit_with_verdict(rows: list[dict], n_target: int) -> None:
    streak = _streak(rows)
    passes = sum(1 for r in rows if r["success"])
    if streak >= n_target:
        print(f"\n[durability] ✅ PASS — streak {streak}/{n_target} achieved "
              f"({passes}/{len(rows)} total passes)")
        sys.exit(0)
    else:
        print(f"\n[durability] ❌ FAIL — streak {streak}/{n_target} "
              f"({passes}/{len(rows)} total passes)")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Eval runner — Bảng C: Gazebo m* tasks.

Runs ≥3 "m*" tasks defined in tasks_m.json against WORLD_BACKEND=gazebo,
grades each with oracle ground-truth, and writes results to
eval/results/report_v2.md and eval/results/gazebo_m_tasks.json.

Prerequisites:
  • Gazebo Harmonic running with AWS small_warehouse + TurtleBot3
  • Nav2 stack alive (NavigateToPose action server)
  • ROS 2 Jazzy sourced in the shell environment
  • eval/tasks_m.json present (sibling of this script)

Usage:
  cd /home/cth/AI20K
  source colcon_ws/install/setup.bash
  python3 eval/run_eval_gazebo.py [--dry-run] [--no-reset]

  --dry-run   Skip actual LLM/ROS calls; emit placeholder rows for CI.
  --no-reset  Do not teleport pallet between tasks.
"""

import argparse
import json
import math
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running without colcon install (imports guarded below)
try:
    import rclpy
    from warehouse_robot_agent.gazebo_backend import GazeboBackend, GazeboBackendNode, _gz_model_pose
    from warehouse_robot_agent.llm_agent import run_agent
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False


SCRIPT_DIR  = Path(__file__).parent
TASKS_FILE  = SCRIPT_DIR / "tasks_m.json"
RESULTS_DIR = SCRIPT_DIR / "results"
JSON_OUT    = RESULTS_DIR / "gazebo_m_tasks.json"
REPORT_OUT  = RESULTS_DIR / "report_v2.md"

PALLET_SPAWN_X = -0.28
PALLET_SPAWN_Y = -9.48
PALLET_MODEL   = "aws_robomaker_warehouse_PalletJackB_01_001"
DROPOFF_A      = (0.0, 0.0)

# Human-readable labels for locate_object source strings
_SOURCE_LABELS = {
    "gt_registry":        "GT registry",
    "gz_cli":             "gz CLI",
    "not_found":          "not found",
}


# ──────────────────────────── helpers ──────────────────────────────────────── #

def _source_label(raw: str) -> str:
    """Map raw locate_log entry → short display label."""
    if raw.startswith("perception("):
        inner = raw[len("perception("):-1]
        return f"ARMBench" if "armbench" in inner.lower() else f"perception({inner})"
    return _SOURCE_LABELS.get(raw, raw)


def _locate_sources_summary(sources: list[str]) -> str:
    """Collapse the per-call locate_log into a compact unique list for the report."""
    if not sources:
        return "—"
    seen, ordered = set(), []
    for s in sources:
        label = _source_label(s)
        if label not in seen:
            seen.add(label)
            ordered.append(label)
    return " + ".join(ordered)


def _gz_teleport_pallet() -> bool:
    """Teleport the pallet back to its spawn pose via gz service call.

    Resets world state between tasks so each run starts identically.
    Returns True on apparent success, False if gz service unavailable.
    """
    req = (
        f'name: "{PALLET_MODEL}" '
        f'position: {{x: {PALLET_SPAWN_X}, y: {PALLET_SPAWN_Y}, z: 0.1}} '
        f'orientation: {{x: 0.0, y: 0.0, z: 0.0, w: 1.0}}'
    )
    try:
        result = subprocess.run(
            [
                "gz", "service",
                "-s", "/world/small_warehouse/set_pose",
                "--reqtype", "gz.msgs.Pose",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "3000",
                "--req", req,
            ],
            capture_output=True, text=True, timeout=8.0,
        )
        return result.returncode == 0
    except Exception as exc:
        print(f"[eval] WARNING: pallet teleport failed — {exc}")
        return False


def _oracle_grade(threshold_m: float = 1.5) -> dict:
    """Query Gazebo ground-truth pose and return grading dict."""
    pallet_gt = _gz_model_pose(PALLET_MODEL)
    dist = None
    success = False
    if pallet_gt is not None:
        dx = pallet_gt.x - DROPOFF_A[0]
        dy = pallet_gt.y - DROPOFF_A[1]
        dist = math.sqrt(dx * dx + dy * dy)
        success = dist < threshold_m
    return {
        "pallet_gt":           str(pallet_gt) if pallet_gt else "gz_cli_unavailable",
        "dist_to_dropoff_a_m": round(dist, 3) if dist is not None else None,
        "success":             success,
        "threshold_m":         threshold_m,
    }


def _run_one_task_live(backend: GazeboBackend, task: dict) -> dict:
    """Run a single task against the live Gazebo backend."""
    backend.locate_log.clear()

    t0 = time.time()
    metrics = run_agent(backend, goal_text=task["goal_text"])
    elapsed = round(time.time() - t0, 1)

    oracle = _oracle_grade(task.get("threshold_m", 1.5))
    return {
        "id":             task["id"],
        "goal_text":      task["goal_text"],
        "success":        oracle["success"],
        "steps":          metrics["steps"],
        "elapsed_s":      elapsed,
        "done_called":    metrics["done_called"],
        "locate_sources": list(backend.locate_log),
        "oracle":         oracle,
    }


def _run_one_task_dry(task: dict) -> dict:
    """Return a placeholder row without touching ROS/LLM (for CI / --dry-run)."""
    return {
        "id":             task["id"],
        "goal_text":      task["goal_text"],
        "success":        None,
        "steps":          None,
        "elapsed_s":      None,
        "done_called":    None,
        "locate_sources": [],
        "oracle":         {"note": "dry-run — not executed"},
    }


# ──────────────────────────── report generation ────────────────────────────── #

_BANG_AB_STUB = """\
## Bảng A — 2D Flat World (kết quả chính)

> Xem `PLAN_may_A_web2d.md` và kết quả eval Máy A để biết chi tiết.
> Bảng A là phạm vi đo **chính thức** của dự án.

*(Chưa có kết quả trong file này — điền từ Máy A)*

---

## Bảng B — ablation / baseline

*(Chưa có — điền thêm nếu cần)*
"""


def _success_str(val) -> str:
    if val is True:
        return "PASS ✓"
    if val is False:
        return "FAIL ✗"
    return "—"


def _write_report(rows: list[dict], run_ts: str, dry_run: bool) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Raw JSON for downstream tools / parity check
    JSON_OUT.write_text(
        json.dumps({"run_ts": run_ts, "tasks": rows}, indent=2, ensure_ascii=False)
    )
    print(f"[eval] JSON written → {JSON_OUT}")

    passes = sum(1 for r in rows if r["success"] is True)
    total  = len(rows)
    note   = " *(dry-run — not executed)*" if dry_run else ""

    bang_c_header = f"""\
## Bảng C — Gazebo bonus showcase (sim→real){note}

> **Lưu ý: Bảng C là bonus showcase — không thuộc phạm vi đo chính Bảng A/B.**
> Backend: `WORLD_BACKEND=gazebo` · Gazebo Harmonic · AWS small_warehouse
> Oracle: ground-truth `gz model -p` — **độc lập với agent**
> n = {total} (nhỏ, mục đích showcase) · Pass = {passes}/{total}
> Run: {run_ts}

| Task ID | goal_text (tóm tắt) | Success | Steps | Time (s) | Dist→dropoff_a (m) | locate_object source |
|---------|---------------------|---------|-------|----------|--------------------|----------------------|
"""

    rows_md = ""
    for r in rows:
        short_goal = r["goal_text"][:55] + ("…" if len(r["goal_text"]) > 55 else "")
        dist = r["oracle"].get("dist_to_dropoff_a_m")
        dist_str = f"{dist:.3f}" if dist is not None else "—"
        loc_src  = _locate_sources_summary(r.get("locate_sources", []))
        rows_md += (
            f"| {r['id']} | {short_goal} | {_success_str(r['success'])} "
            f"| {r['steps'] if r['steps'] is not None else '—'} "
            f"| {r['elapsed_s'] if r['elapsed_s'] is not None else '—'} "
            f"| {dist_str} "
            f"| {loc_src} |\n"
        )

    disclosure = """\

> **Disclosure:** Gazebo là mô phỏng vật lý 3D; agent (LLM + vòng tool) là thật, đọc kết quả
> thật từ ROS 2. Cột *locate_object source* ghi nguồn định vị thực tế dùng trong mỗi task:
> **ARMBench** = PerceptionNode + detector; **GT registry** = bảng tọa độ tĩnh (fallback);
> **gz CLI** = truy vấn trực tiếp Gazebo model pose.
> n nhỏ (= {total}) — đủ để minh hoạ sim→real, không đủ để kết luận thống kê.
""".format(total=total)

    # ── Assemble the full file ──────────────────────────────────────────── #
    # Read existing content and strip any previous Bảng C section
    if REPORT_OUT.exists():
        existing = REPORT_OUT.read_text()
        existing = re.sub(r'\n## Bảng C —.*', '', existing, flags=re.DOTALL)
        existing = existing.rstrip("\n")
    else:
        existing = "# Eval Results — AI20K Warehouse Agent\n\n" + _BANG_AB_STUB.rstrip("\n")

    REPORT_OUT.write_text(
        existing + "\n\n---\n\n" + bang_c_header + rows_md + disclosure + "\n"
    )
    print(f"[eval] Report written → {REPORT_OUT}")


# ──────────────────────────── main ─────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(description="Gazebo m* task eval runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip ROS/LLM — write placeholder rows (for CI)")
    parser.add_argument("--no-reset", action="store_true",
                        help="Do not teleport pallet between tasks")
    args = parser.parse_args()

    tasks  = json.loads(TASKS_FILE.read_text())
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if args.dry_run or not ROS_AVAILABLE:
        if not args.dry_run:
            print("[eval] rclpy not available — switching to dry-run mode")
        rows = [_run_one_task_dry(t) for t in tasks]
        _write_report(rows, run_ts, dry_run=True)
        return

    rclpy.init()
    node    = GazeboBackendNode()
    backend = GazeboBackend(node)

    print("[eval] Waiting for initial AMCL/odom pose …")
    if not node.spin_until_pose(timeout=30.0):
        print("[eval] WARNING: No pose received in 30 s. Is the sim running?")

    rows = []
    try:
        for i, task in enumerate(tasks):
            print(f"\n[eval] ════════════════════════════════════════")
            print(f"[eval] Task {i+1}/{len(tasks)}: {task['id']}")
            print(f"[eval] goal_text: {task['goal_text']}")
            print(f"[eval] ════════════════════════════════════════")

            if i > 0 and not args.no_reset:
                print("[eval] Resetting pallet to spawn pose …")
                if _gz_teleport_pallet():
                    print("[eval] Pallet reset OK — waiting 2 s for physics to settle …")
                    time.sleep(2.0)
                else:
                    print("[eval] WARNING: pallet reset failed; results may be invalid")

            row = _run_one_task_live(backend, task)
            rows.append(row)

            verdict = "PASS ✓" if row["success"] else "FAIL ✗"
            print(
                f"\n[eval] {task['id']} → {verdict} | steps={row['steps']} | "
                f"time={row['elapsed_s']}s | dist={row['oracle'].get('dist_to_dropoff_a_m')}m | "
                f"locate_src={_locate_sources_summary(row['locate_sources'])}"
            )

    except KeyboardInterrupt:
        print("\n[eval] Interrupted by user — writing partial results.")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    _write_report(rows, run_ts, dry_run=False)

    passes = sum(1 for r in rows if r["success"] is True)
    print(f"\n[eval] Done: {passes}/{len(rows)} tasks passed.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Bảng A eval runner — Flat2DBackend, local deterministic agent.

Runs all tasks in tasks_m.json through a scripted (non-LLM) agent that
executes the optimal tool sequence on Flat2DBackend. No Anthropic API,
no ROS, no Gazebo required.

The scripted agent is *not* the LLM agent — it is a reference implementation
that proves the backend interface is correct and the oracle evaluation passes.
LLM agent eval (Bảng A with claude-opus) is run on Machine A.

Usage:
  python3 eval/run_eval_flat2d.py
  python3 eval/run_eval_flat2d.py --task m1
  python3 eval/run_eval_flat2d.py --out eval/results/report_v2.md

Outputs:
  eval/results/traces/<run_id>_<task_id>_flat2d_trace.json
  Updates Bảng A table in eval/results/report_v2.md
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SRC_PKG   = REPO_ROOT / "colcon_ws/src/warehouse_robot_agent"
sys.path.insert(0, str(SRC_PKG))

TASKS_FILE  = Path(__file__).parent / "tasks_m.json"
TRACES_DIR  = Path(__file__).parent / "results" / "traces"
REPORT_FILE = Path(__file__).parent / "results" / "report_v2.md"

try:
    from warehouse_robot_agent.flat2d_backend import Flat2DBackend
    from warehouse_robot_agent.llm_agent import dispatch
except ImportError as e:
    print(f"[eval] ERROR: {e}")
    print("       Ensure warehouse_robot_agent package is on PYTHONPATH.")
    sys.exit(1)


# ─────────────────────────── scripted agent ──────────────────────────────── #

def _scripted_agent(backend: Flat2DBackend, goal_text: str) -> dict:
    """
    Deterministic agent: perceive → locate → move to pallet → pick →
    move to dropoff_a → drop → oracle_check → done.

    This is the reference path — same tool calls the LLM agent should make.
    """
    trace: list[dict] = []
    step = 0
    done_called = False

    def call(name: str, inp: dict = {}) -> dict:
        nonlocal step
        step += 1
        raw = dispatch(backend, name, inp)
        out = json.loads(raw)
        trace.append({"step": step, "tool": name, "input": inp, "output": out})
        print(f"  [{step:02d}] {name}({json.dumps(inp)}) → {json.dumps(out)[:120]}")
        return out

    print(f"\n[scripted] goal: {goal_text[:80]}…")

    call("perceive")
    pallet_pose = call("locate_object", {"name": "pallet_jack"})
    if pallet_pose is None:
        print("[scripted] locate_object returned None — aborting.")
        return {"steps": step, "done_called": False, "trace": trace, "oracle": {}}

    # Navigate to pallet
    call("move_to", {"x": pallet_pose["x"], "y": pallet_pose["y"], "yaw": 0.0})
    call("pick", {"object_name": "pallet_jack"})

    # Navigate to dropoff_a
    dropoff = call("locate_object", {"name": "dropoff_a"})
    call("move_to", {"x": dropoff["x"], "y": dropoff["y"], "yaw": 0.0})
    call("drop", {"x": dropoff["x"], "y": dropoff["y"]})

    oracle = call("oracle_check")
    success = oracle.get("task_complete", False)

    summary = (
        f"Delivered pallet_jack to dropoff_a. "
        f"Distance={oracle.get('pallet_to_dropoff_a_m', '?')} m. "
        f"{'PASS' if success else 'FAIL'}"
    )
    call("done", {"summary": summary})
    done_called = True

    return {"steps": step, "done_called": done_called, "trace": trace, "oracle": oracle}


# ─────────────────────────── run single task ─────────────────────────────── #

def run_task(task: dict, run_ts: str) -> dict:
    task_id   = task["id"]
    goal_text = task["goal_text"]

    backend = Flat2DBackend()
    t0 = time.monotonic()
    result = _scripted_agent(backend, goal_text)
    elapsed = round(time.monotonic() - t0, 2)

    oracle  = result.get("oracle", {})
    dist    = oracle.get("pallet_to_dropoff_a_m", None)
    success = result["done_called"] and oracle.get("task_complete", False)

    locate_src = ", ".join(set(backend.locate_log)) if backend.locate_log else "—"

    row = {
        "task_id":    task_id,
        "goal_short": goal_text[:55] + "…",
        "success":    success,
        "steps":      result["steps"],
        "time_s":     elapsed,
        "dist_m":     dist,
        "locate_src": locate_src,
    }

    # Save trace
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    run_id = run_ts.replace(":", "").replace("+", "").replace("-", "")[:15]
    trace_path = TRACES_DIR / f"{run_id}_{task_id}_flat2d_trace.json"
    trace_path.write_text(json.dumps({
        "run_id": run_id, "task_id": task_id, "backend": "flat2d",
        "goal_text": goal_text, "run_ts": run_ts,
        "metrics": {k: v for k, v in result.items() if k != "trace"},
        "trace": result["trace"],
    }, indent=2, ensure_ascii=False))
    print(f"  [trace] → {trace_path.name}")

    return row


# ─────────────────────────── report update ───────────────────────────────── #

def _bảng_a_table(rows: list[dict], run_ts: str) -> str:
    header = (
        f"> Backend: `Flat2DBackend` · agent: scripted (reference path) · "
        f"Run: {run_ts}\n\n"
        "| Task ID | goal_text (tóm tắt) | Success | Steps | Time (s) | "
        "Dist→dropoff_a (m) | locate_object source |\n"
        "|---------|---------------------|---------|-------|----------|-"
        "-------------------|----------------------|\n"
    )
    body = ""
    for r in rows:
        ok  = "✓" if r["success"] else "✗"
        dist = f"{r['dist_m']:.3f}" if r["dist_m"] is not None else "—"
        body += (
            f"| {r['task_id']} | {r['goal_short']} | {ok} | "
            f"{r['steps']} | {r['time_s']} | {dist} | {r['locate_src']} |\n"
        )
    return header + body


def update_report(rows: list[dict], report_path: Path, run_ts: str):
    text = report_path.read_text()
    new_block = _bảng_a_table(rows, run_ts)

    # Replace the placeholder block between "## Bảng A" and the next "---"
    import re
    pattern = r"(## Bảng A.*?---)"
    replacement = (
        "## Bảng A — 2D Flat World (kết quả chính)\n\n"
        + new_block
        + "\n---"
    )
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)

    if new_text == text:
        # Fallback: append if pattern not found
        print("[report] WARNING: pattern not found, appending Bảng A block.")
        new_text = text + "\n\n" + "## Bảng A (appended)\n\n" + new_block

    report_path.write_text(new_text)
    print(f"[report] Updated {report_path}")


# ─────────────────────────── main ────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Run only this task ID (e.g. m1)")
    parser.add_argument("--out", default=str(REPORT_FILE), help="Report path")
    args = parser.parse_args()

    tasks = json.loads(TASKS_FILE.read_text())
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            print(f"[eval] task {args.task!r} not found in {TASKS_FILE}")
            sys.exit(1)

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[eval] Bảng A eval — {len(tasks)} task(s) — {run_ts}")

    rows = []
    for task in tasks:
        row = run_task(task, run_ts)
        rows.append(row)
        status = "PASS ✓" if row["success"] else "FAIL ✗"
        print(f"  [{row['task_id']}] {status}  steps={row['steps']}  "
              f"time={row['time_s']}s  dist={row['dist_m']}m")

    update_report(rows, Path(args.out), run_ts)

    passed = sum(1 for r in rows if r["success"])
    print(f"\n[eval] ══ Bảng A: {passed}/{len(rows)} passed ══")


if __name__ == "__main__":
    main()

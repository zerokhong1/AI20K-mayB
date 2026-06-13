#!/usr/bin/env python3
"""
Bảng A-ext eval runner — LLM agent (ollama qwen2.5:7b) on Flat2DBackend.

Tên bảng: "Bảng A-ext (repo Máy B)" — KHÔNG mạo danh Bảng A official Máy A.
Model: ollama qwen2.5:7b (≠ Gemini official BTC eval).
Backend: Flat2DBackend (no ROS, no Gazebo).

Pre-registration protocol:
  Commit tasks_aext.json + seed + this script BEFORE running eval.
  Commit kết quả ở commit SAU (2 SHA tách bạch = pre-registration).

Usage:
  LLM_PROVIDER=ollama python3 eval/run_eval_aext.py
  LLM_PROVIDER=ollama python3 eval/run_eval_aext.py --task a1
  LLM_PROVIDER=ollama python3 eval/run_eval_aext.py --seed 42

Outputs:
  eval/results/traces/<ts>_<id>_aext_trace.json
  eval/results/aext_results.json
  Updates Bảng A-ext section in eval/results/report_v2.md
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SRC_PKG   = REPO_ROOT / "colcon_ws/src/warehouse_robot_agent"
sys.path.insert(0, str(SRC_PKG))

TASKS_FILE  = Path(__file__).parent / "tasks_aext.json"
TRACES_DIR  = Path(__file__).parent / "results" / "traces"
REPORT_FILE = Path(__file__).parent / "results" / "report_v2.md"
JSON_OUT    = Path(__file__).parent / "results" / "aext_results.json"

# Seed for reproducibility — logged but T=0 (deterministic) on ollama
DEFAULT_SEED = 20260613

try:
    from warehouse_robot_agent.flat2d_backend import Flat2DBackend
    from warehouse_robot_agent.llm_agent import run_agent
except ImportError as e:
    print(f"[eval] ERROR: {e}")
    print("       Ensure warehouse_robot_agent package is on PYTHONPATH.")
    sys.exit(1)


# ─────────────────────────── single-task runner ───────────────────────────── #

def run_task(task: dict, run_ts: str, seed: int) -> dict:
    task_id   = task["id"]
    goal_text = task["goal_text"]
    threshold = task.get("threshold_m", 1.5)

    backend = Flat2DBackend()
    t0 = time.monotonic()

    print(f"\n{'='*60}")
    print(f"[aext] task {task_id} | {goal_text[:70]}…")

    try:
        result = run_agent(backend, goal_text=goal_text, temperature=0.0)
    except Exception as exc:
        print(f"[aext] ERROR in run_agent: {exc}")
        result = {"steps": 0, "done_called": False, "trace": [], "error": str(exc)}

    elapsed = round(time.monotonic() - t0, 2)

    oracle  = backend.oracle_check()
    dist    = oracle.get("pallet_to_dropoff_a_m", None)
    success = result.get("done_called", False) and oracle.get("task_complete", False)

    locate_src = ", ".join(dict.fromkeys(backend.locate_log)) if backend.locate_log else "—"

    row = {
        "task_id":    task_id,
        "category":   task.get("category", "—"),
        "goal_short": goal_text[:55] + "…",
        "success":    success,
        "done_called": result.get("done_called", False),
        "steps":      result.get("steps", 0),
        "time_s":     elapsed,
        "dist_m":     dist,
        "locate_src": locate_src,
        "oracle_target": task.get("oracle_target", "dropoff_a"),
        "oracle":     oracle,
        "error":      result.get("error", None),
    }

    # Save trace
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    run_id = run_ts.replace(":", "").replace("+", "").replace("-", "")[:15]
    trace_path = TRACES_DIR / f"{run_id}_{task_id}_aext_trace.json"
    trace_path.write_text(json.dumps({
        "run_id": run_id, "task_id": task_id, "backend": "flat2d",
        "provider": "ollama", "seed": seed,
        "goal_text": goal_text, "run_ts": run_ts,
        "metrics": {k: v for k, v in row.items()},
        "oracle": oracle,
        "trace": result.get("trace", []),
    }, indent=2, ensure_ascii=False))
    print(f"  [trace] → {trace_path.name}")

    return row


# ─────────────────────────── report update ───────────────────────────────── #

def _bảng_aext_table(rows: list[dict], run_ts: str, seed: int) -> str:
    passed = sum(1 for r in rows if r["success"])
    total  = len(rows)
    label  = (
        f"(model: ollama qwen2.5:7b ≠ Gemini official · Flat2DBackend · "
        f"T=0 · seed={seed} · GT-registry locate · parity-check only)"
    )

    header = (
        f"## Bảng A-ext (repo Máy B) — LLM planning showcase\n\n"
        f"> **KHÔNG phải Bảng A official.** Bảng A/B official = BTC repo "
        f"(LangGraph + Gemini flash-lite, n=33, Máy A).\n"
        f"> Bảng này kiểm chứng LLM agent (ollama qwen2.5:7b) trên tập task "
        f"tiếng Việt đa dạng, Flat2DBackend.\n"
        f">\n"
        f"> `{label}`\n"
        f">\n"
        f"> n = {total} · Pass = {passed}/{total} · Run: {run_ts}\n\n"
        "| Task | Category | Goal (tóm tắt) | ✓/✗ | Steps | Time (s) | "
        "dist→dropoff_a (m) | locate src |\n"
        "|------|----------|----------------|-----|-------|----------|-"
        "-------------------|------------|\n"
    )
    body = ""
    for r in rows:
        ok   = "✓" if r["success"] else "✗"
        dist = f"{r['dist_m']:.3f}" if r["dist_m"] is not None else "—"
        note = f" _(err)_" if r.get("error") else ""
        body += (
            f"| {r['task_id']} | {r['category']} | {r['goal_short']}{note} | "
            f"{ok} | {r['steps']} | {r['time_s']} | {dist} | {r['locate_src']} |\n"
        )
    return header + body


def update_report(rows: list[dict], report_path: Path, run_ts: str, seed: int):
    import re
    text = report_path.read_text()
    new_block = _bảng_aext_table(rows, run_ts, seed)

    # Replace existing A-ext block or append
    pattern = r"## Bảng A-ext.*?(?=\n## |\Z)"
    if re.search(pattern, text, flags=re.DOTALL):
        new_text = re.sub(pattern, new_block.rstrip(), text, count=1, flags=re.DOTALL)
    else:
        new_text = text.rstrip() + "\n\n---\n\n" + new_block

    report_path.write_text(new_text)
    print(f"[report] Updated {report_path}")


# ─────────────────────────── main ─────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task",  help="Run only this task ID (e.g. a1)")
    parser.add_argument("--seed",  type=int, default=DEFAULT_SEED, help="Reproducibility seed")
    parser.add_argument("--out",   default=str(REPORT_FILE), help="Report path")
    args = parser.parse_args()

    provider = os.environ.get("LLM_PROVIDER", "gemini")
    if provider != "ollama":
        print(f"[eval] WARNING: LLM_PROVIDER={provider!r} — expected 'ollama'. "
              f"Set LLM_PROVIDER=ollama for local run.")

    tasks = json.loads(TASKS_FILE.read_text())
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            print(f"[eval] task {args.task!r} not found.")
            sys.exit(1)

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[eval] Bảng A-ext — {len(tasks)} task(s) — provider={provider} — "
          f"seed={args.seed} — {run_ts}")

    rows = []
    for task in tasks:
        row = run_task(task, run_ts, args.seed)
        rows.append(row)
        ok = "PASS ✓" if row["success"] else "FAIL ✗"
        print(f"  [{row['task_id']}] {ok}  steps={row['steps']}  "
              f"time={row['time_s']}s  dist={row['dist_m']}m")

    # Write JSON
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps({
        "run_ts": run_ts, "provider": provider, "seed": args.seed,
        "model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        "rows": rows,
    }, indent=2, ensure_ascii=False))

    update_report(rows, Path(args.out), run_ts, args.seed)

    passed = sum(1 for r in rows if r["success"])
    print(f"\n[eval] ══ Bảng A-ext: {passed}/{len(rows)} passed ══")
    return passed, len(rows)


if __name__ == "__main__":
    main()

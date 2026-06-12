#!/usr/bin/env python3
"""
ablation_baseline.py — scripted-naive baseline for ablation study (P4.2).

Arm B của ablation: không LLM, không reasoning, không retry, không hỏi lại.
Parser keyword tìm tên vật + tên đích trong lệnh → gọi cứng:
  locate_object(object) → move_to(pallet) → pick(object) → move_to(dropoff) → drop → oracle_check → done

Định nghĩa CHỐT tại pre-registration commit — không chỉnh sau khi thấy số.

Object keywords (ordered, first match wins):
  pallet_jack → "pallet_jack"
  pallet      → "pallet_jack"  (alias)

Dropoff keywords:
  dropoff_b / thả b / zone b   → "dropoff_b"
  dropoff_a / thả a / zone a   → "dropoff_a"  (default if nothing matches)

Usage:
  python3 eval/ablation_baseline.py                          # all tasks_aext.json
  python3 eval/ablation_baseline.py --task a1
  python3 eval/ablation_baseline.py --out eval/results/ablation.md

Outputs:
  eval/results/ablation_baseline_results.json
  eval/results/ablation.md   (appended / updated)
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SRC_PKG   = REPO_ROOT / "colcon_ws/src/warehouse_robot_agent"
sys.path.insert(0, str(SRC_PKG))

TASKS_FILE   = Path(__file__).parent / "tasks_aext.json"
TRACES_DIR   = Path(__file__).parent / "results" / "traces"
ABLATION_OUT = Path(__file__).parent / "results" / "ablation.md"
JSON_OUT     = Path(__file__).parent / "results" / "ablation_baseline_results.json"

try:
    from warehouse_robot_agent.flat2d_backend import Flat2DBackend
    from warehouse_robot_agent.llm_agent import dispatch
except ImportError as e:
    print(f"[baseline] ERROR: {e}")
    sys.exit(1)


# ─────────────────────────── keyword parser (LOCKED) ─────────────────────── #

_OBJECT_ALIASES = [
    (r"pallet[_\s]?jack",  "pallet_jack"),
    (r"\bpallet\b",        "pallet_jack"),
]

_DROPOFF_ALIASES = [
    (r"dropoff[_\s]?b|thả\s*b|zone\s*b",  "dropoff_b"),
    (r"dropoff[_\s]?a|thả\s*a|zone\s*a",  "dropoff_a"),
    (r"\(0[.,]\s*0\)|tọa độ.*0.*,.*0|trung tâm|central", "dropoff_a"),
]

def _parse_object(goal_text: str) -> str:
    text = goal_text.lower()
    for pat, name in _OBJECT_ALIASES:
        if re.search(pat, text):
            return name
    return "pallet_jack"  # fallback

def _parse_dropoff(goal_text: str) -> str:
    text = goal_text.lower()
    for pat, name in _DROPOFF_ALIASES:
        if re.search(pat, text):
            return name
    return "dropoff_a"  # default


# ─────────────────────────── scripted naive agent ────────────────────────── #

def _naive_agent(backend: Flat2DBackend, goal_text: str) -> dict:
    """
    Fixed tool sequence. No reasoning, no retry, no ask_human.
    Fails if keyword parse yields wrong object/dropoff.
    """
    trace: list[dict] = []
    step = 0
    done_called = False
    wrong_object_count = 0

    def call(name: str, inp: dict = {}) -> dict:
        nonlocal step
        step += 1
        raw = dispatch(backend, name, inp)
        out = json.loads(raw)
        trace.append({"step": step, "tool": name, "input": inp, "output": out})
        print(f"  [{step:02d}] {name}({json.dumps(inp)}) → {json.dumps(out)[:100]}")
        return out

    obj_name  = _parse_object(goal_text)
    drop_name = _parse_dropoff(goal_text)

    print(f"\n[baseline] goal: {goal_text[:70]}…")
    print(f"[baseline] parsed: object={obj_name!r}  dropoff={drop_name!r}")

    # Fixed sequence: locate → move → pick → locate_dropoff → move → drop → oracle → done
    pallet_pose = call("locate_object", {"name": obj_name})
    if pallet_pose is None:
        wrong_object_count += 1
        print(f"[baseline] locate_object returned None for {obj_name!r} — FAIL (wrong name)")
        oracle = call("oracle_check")
        call("done", {"summary": f"FAIL: locate_object({obj_name!r}) returned None"})
        return {
            "steps": step, "done_called": True, "trace": trace,
            "oracle": oracle, "wrong_object_count": wrong_object_count,
            "parsed_object": obj_name, "parsed_dropoff": drop_name,
        }

    call("move_to", {"x": pallet_pose["x"], "y": pallet_pose["y"], "yaw": 0.0})
    call("pick", {"object_name": obj_name})

    dropoff_pose = call("locate_object", {"name": drop_name})
    if dropoff_pose is None:
        wrong_object_count += 1
        print(f"[baseline] locate_object returned None for {drop_name!r} — FAIL")
        oracle = call("oracle_check")
        call("done", {"summary": f"FAIL: locate_object({drop_name!r}) returned None"})
        return {
            "steps": step, "done_called": True, "trace": trace,
            "oracle": oracle, "wrong_object_count": wrong_object_count,
            "parsed_object": obj_name, "parsed_dropoff": drop_name,
        }

    call("move_to", {"x": dropoff_pose["x"], "y": dropoff_pose["y"], "yaw": 0.0})
    call("drop", {"x": dropoff_pose["x"], "y": dropoff_pose["y"]})

    oracle = call("oracle_check")
    success = oracle.get("task_complete", False)
    summary = (
        f"Delivered {obj_name} to {drop_name}. "
        f"dist={oracle.get('pallet_to_dropoff_a_m','?')}m. "
        f"{'PASS' if success else 'FAIL'}"
    )
    call("done", {"summary": summary})
    done_called = True

    return {
        "steps": step, "done_called": done_called, "trace": trace,
        "oracle": oracle, "wrong_object_count": wrong_object_count,
        "parsed_object": obj_name, "parsed_dropoff": drop_name,
    }


# ─────────────────────────── run single task ─────────────────────────────── #

def run_task(task: dict, run_ts: str) -> dict:
    task_id   = task["id"]
    goal_text = task["goal_text"]

    backend = Flat2DBackend()
    t0 = time.monotonic()
    result = _naive_agent(backend, goal_text)
    elapsed = round(time.monotonic() - t0, 2)

    oracle  = result.get("oracle", {})
    dist    = oracle.get("pallet_to_dropoff_a_m", None)
    success = result["done_called"] and oracle.get("task_complete", False)

    row = {
        "task_id":        task_id,
        "category":       task.get("category", "—"),
        "goal_short":     goal_text[:55] + "…",
        "success":        success,
        "steps":          result["steps"],
        "time_s":         elapsed,
        "dist_m":         dist,
        "wrong_object":   result.get("wrong_object_count", 0),
        "parsed_object":  result.get("parsed_object", "?"),
        "parsed_dropoff": result.get("parsed_dropoff", "?"),
    }

    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    run_id = run_ts.replace(":", "").replace("+", "").replace("-", "")[:15]
    trace_path = TRACES_DIR / f"{run_id}_{task_id}_ablation_trace.json"
    trace_path.write_text(json.dumps({
        "run_id": run_id, "task_id": task_id, "arm": "B-scripted-naive",
        "goal_text": goal_text, "run_ts": run_ts,
        "metrics": {k: v for k, v in row.items()},
        "oracle": oracle, "trace": result["trace"],
    }, indent=2, ensure_ascii=False))
    print(f"  [trace] → {trace_path.name}")
    return row


# ─────────────────────────── ablation report ─────────────────────────────── #

def write_ablation_report(rows: list[dict], run_ts: str, arm_a_path: Path | None = None):
    passed  = sum(1 for r in rows if r["success"])
    wrong   = sum(r.get("wrong_object", 0) for r in rows)
    total   = len(rows)

    text = f"# Ablation Study — Bảng A-ext (repo Máy B)\n\n"
    text += f"> Run: {run_ts}\n"
    text += f"> Backend: Flat2DBackend · provider: scripted-naive (Arm B)\n\n"

    text += "## Arm B — Scripted-naive baseline\n\n"
    text += (
        "> Keyword parser → locate → move_to → pick → move_to → drop → oracle_check.\n"
        "> Không LLM, không retry, không reasoning, không hỏi lại.\n"
        "> Định nghĩa CHỐT tại pre-registration commit.\n\n"
    )
    text += (
        "| Task | Category | Goal (tóm tắt) | ✓/✗ | Steps | "
        "dist→A (m) | Parsed obj | Parsed dst | wrong_obj |\n"
        "|------|----------|----------------|-----|-------|"
        "------------|------------|------------|----------|\n"
    )
    for r in rows:
        ok   = "✓" if r["success"] else "✗"
        dist = f"{r['dist_m']:.3f}" if r["dist_m"] is not None else "—"
        text += (
            f"| {r['task_id']} | {r['category']} | {r['goal_short']} | "
            f"{ok} | {r['steps']} | {dist} | "
            f"{r['parsed_object']} | {r['parsed_dropoff']} | {r['wrong_object']} |\n"
        )
    text += f"\n**Arm B:** {passed}/{total} passed · {wrong} wrong-object errors\n\n"

    # Placeholder for Arm A (filled after LLM eval)
    text += "## Arm A — LLM agent (ollama qwen2.5:7b)\n\n"
    if arm_a_path and arm_a_path.exists():
        arm_a = json.loads(arm_a_path.read_text())
        a_rows = arm_a.get("rows", [])
        a_pass = sum(1 for r in a_rows if r["success"])
        text += f"> Results from {arm_a_path.name}\n\n"
        text += (
            "| Task | ✓/✗ | Steps | dist→A (m) |\n"
            "|------|-----|-------|------------|\n"
        )
        for r in a_rows:
            ok   = "✓" if r["success"] else "✗"
            dist = f"{r['dist_m']:.3f}" if r["dist_m"] is not None else "—"
            text += f"| {r['task_id']} | {ok} | {r['steps']} | {dist} |\n"
        text += f"\n**Arm A:** {a_pass}/{len(a_rows)} passed\n\n"
    else:
        text += "> _(Arm A results: run `LLM_PROVIDER=ollama python3 eval/run_eval_aext.py`)_\n\n"

    text += "## Delta (Arm A − Arm B)\n\n"
    text += "> Điền sau khi có cả 2 arm. Xem `eval/results/aext_results.json` và bảng trên.\n"

    ABLATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    ABLATION_OUT.write_text(text, encoding="utf-8")
    print(f"[ablation] → {ABLATION_OUT}")


# ─────────────────────────── main ─────────────────────────────────────────── #

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--task",    help="Run only this task ID")
    parser.add_argument("--out",     default=str(ABLATION_OUT), help="Ablation report path")
    parser.add_argument("--arm-a",   default=str(JSON_OUT.parent / "aext_results.json"),
                        help="Path to Arm A JSON (to merge into ablation report)")
    args = parser.parse_args()

    tasks = json.loads(TASKS_FILE.read_text())
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            print(f"[ablation] task {args.task!r} not found.")
            sys.exit(1)

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[ablation] Arm B — {len(tasks)} task(s) — scripted-naive — {run_ts}")

    rows = []
    for task in tasks:
        row = run_task(task, run_ts)
        rows.append(row)
        ok = "PASS ✓" if row["success"] else "FAIL ✗"
        print(f"  [{row['task_id']}] {ok}  steps={row['steps']}  dist={row['dist_m']}m")

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps({
        "run_ts": run_ts, "arm": "B-scripted-naive",
        "rows": rows,
    }, indent=2, ensure_ascii=False))

    arm_a_path = Path(args.arm_a)
    write_ablation_report(rows, run_ts, arm_a_path if arm_a_path.exists() else None)

    passed = sum(1 for r in rows if r["success"])
    print(f"\n[ablation] ══ Arm B: {passed}/{len(rows)} passed ══")
    return passed, len(rows)


if __name__ == "__main__":
    main()

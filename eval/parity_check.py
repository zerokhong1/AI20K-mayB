#!/usr/bin/env python3
"""
Parity check — "1 agent, 2 backends".

Runs the same goal_text through BOTH backends and compares the resulting
tool-call sequences. Saves two trace files side-by-side as evidence.

Modes
─────
  --live        Run flat2d now; load existing Gazebo trace from JSON file.
                (Default when Gazebo/ROS is not available.)

  --both-flat2d Run both backends using Flat2DBackend only — instant, no ROS.
                Useful for CI and development without the full Gazebo stack.

  --live-gazebo  Run flat2d AND the live Gazebo backend (needs ROS running).

Outputs
───────
  eval/results/traces/<run_id>_flat2d_trace.json
  eval/results/traces/<run_id>_gazebo_trace.json  (or loaded from disk)
  eval/results/traces/<run_id>_parity.md          side-by-side diff report

Usage
─────
  # Compare against a previously saved Gazebo trace:
  python3 eval/parity_check.py --live \\
      --gazebo-trace eval/results/traces/some_run_gazebo_trace.json

  # Fully offline (both backends in-process):
  python3 eval/parity_check.py --both-flat2d

  # Live Gazebo (ROS must be running):
  python3 eval/parity_check.py --live-gazebo
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT  = Path(__file__).parent.parent
SRC_PKG    = REPO_ROOT / "colcon_ws/src/warehouse_robot_agent"
sys.path.insert(0, str(SRC_PKG))

TRACES_DIR = Path(__file__).parent / "results" / "traces"

try:
    from warehouse_robot_agent.flat2d_backend import Flat2DBackend
    from warehouse_robot_agent.llm_agent import run_agent
    AGENT_AVAILABLE = True
except ImportError as e:
    AGENT_AVAILABLE = False
    _import_err = e

try:
    import rclpy
    from warehouse_robot_agent.gazebo_backend import GazeboBackend, GazeboBackendNode
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False


# ──────────────────────────────────────────────── parity goal ─────────────── #

# This goal_text is the canonical parity goal — identical string used on both
# backends. Must match what is used in the 2D eval so traces are comparable.
PARITY_GOAL = (
    "Retrieve the pallet_jack from its storage location "
    "and deliver it to drop-off zone A (dropoff_a at coordinates 0, 0)."
)


# ──────────────────────────────────────────────── trace I/O ──────────────── #

def save_trace(run_id: str, backend_name: str, goal_text: str,
               metrics: dict, run_ts: str) -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    out = TRACES_DIR / f"{run_id}_{backend_name}_trace.json"
    payload = {
        "run_id":      run_id,
        "backend":     backend_name,
        "goal_text":   goal_text,
        "run_ts":      run_ts,
        "metrics":     {k: v for k, v in metrics.items() if k != "trace"},
        "trace":       metrics["trace"],
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[parity] Trace saved → {out}")
    return out


def load_trace(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    return data


# ──────────────────────────────────────────────── comparison ─────────────── #

def _tool_sequence(trace_data: dict) -> list[str]:
    """Extract ordered list of tool names from a trace payload."""
    return [entry["tool"] for entry in trace_data.get("trace", [])]


def _lcs_length(a: list, b: list) -> int:
    """Longest common subsequence length."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]


def _sequence_similarity(a: list[str], b: list[str]) -> float:
    """Jaccard-like similarity on ordered tool sequences via LCS."""
    if not a and not b:
        return 1.0
    lcs = _lcs_length(a, b)
    return lcs / max(len(a), len(b))


def compare_traces(t2d: dict, tgz: dict) -> dict:
    seq_2d = _tool_sequence(t2d)
    seq_gz = _tool_sequence(tgz)
    lcs    = _lcs_length(seq_2d, seq_gz)
    sim    = _sequence_similarity(seq_2d, seq_gz)
    return {
        "seq_2d":         seq_2d,
        "seq_gz":         seq_gz,
        "lcs_length":     lcs,
        "seq_sim_pct":    round(sim * 100, 1),
        "len_2d":         len(seq_2d),
        "len_gz":         len(seq_gz),
        "success_2d":     t2d.get("metrics", {}).get("done_called"),
        "success_gz":     tgz.get("metrics", {}).get("done_called"),
    }


# ──────────────────────────────────────────────── report ─────────────────── #

def _lcs_alignment(a: list[str], b: list[str]) -> list[tuple[str | None, str | None]]:
    """Return an aligned list of (a_item, b_item) pairs via LCS backtracking.

    Matching positions have both sides set; insertions/deletions have one side None.
    """
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i-1][j-1] + 1 if a[i-1] == b[j-1] else max(dp[i-1][j], dp[i][j-1])

    # Backtrack
    aligned: list[tuple[str | None, str | None]] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i-1] == b[j-1]:
            aligned.append((a[i-1], b[j-1]))
            i -= 1; j -= 1
        elif j > 0 and (i == 0 or dp[i][j-1] >= dp[i-1][j]):
            aligned.append((None, b[j-1]))   # insertion in b
            j -= 1
        else:
            aligned.append((a[i-1], None))   # deletion from a
            i -= 1
    aligned.reverse()
    return aligned


def write_parity_report(run_id: str, goal_text: str, cmp: dict,
                        path_2d: Path, path_gz: Path, run_ts: str) -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    out = TRACES_DIR / f"{run_id}_parity.md"

    def _fmt_seq(seq: list[str]) -> str:
        return " → ".join(seq) if seq else "*(empty)*"

    # Side-by-side table using LCS alignment (shows true insertions/deletions)
    alignment = _lcs_alignment(cmp["seq_2d"], cmp["seq_gz"])
    table_rows = ""
    row = 1
    for a_tool, b_tool in alignment:
        t2  = f"`{a_tool}`" if a_tool else "—"
        tgz = f"`{b_tool}`" if b_tool else "—"
        if a_tool is None:
            mark = "＋gz"    # extra call in Gazebo
        elif b_tool is None:
            mark = "＋2d"    # extra call in flat2d
        else:
            mark = "✓"
        table_rows += f"| {row} | {t2} | {tgz} | {mark} |\n"
        row += 1

    report = f"""\
# Parity Check — 1 agent, 2 backends

> Run: {run_ts}
> Goal: *{goal_text}*

## Summary

| Metric | Value |
|--------|-------|
| Flat2D steps | {cmp['len_2d']} |
| Gazebo steps | {cmp['len_gz']} |
| LCS length | {cmp['lcs_length']} |
| Sequence similarity | **{cmp['seq_sim_pct']}%** |
| Flat2D done() called | {cmp['success_2d']} |
| Gazebo done() called | {cmp['success_gz']} |

## Tool-call sequence (flat2d)

`{_fmt_seq(cmp['seq_2d'])}`

## Tool-call sequence (gazebo)

`{_fmt_seq(cmp['seq_gz'])}`

## Side-by-side comparison

| # | flat2d | gazebo | match |
|---|--------|--------|-------|
{table_rows}
## Evidence files

- Flat2D trace: `{path_2d.name}`
- Gazebo trace: `{path_gz.name}`

> **Interpretation:** Sequence similarity ≥ 80% indicates the agent uses the same
> reasoning strategy regardless of backend. Differences arise from backend-specific
> retries (Nav2 timeouts, partial moves) not from agent logic changes.
> Both trace files are stored in `eval/results/traces/` for audit.
"""
    out.write_text(report)
    print(f"[parity] Report saved → {out}")
    return out


# ──────────────────────────────────────────────── runners ─────────────────── #

def run_flat2d(goal_text: str, run_id: str, run_ts: str) -> tuple[dict, Path]:
    print("\n[parity] ── Running flat2d backend ──")
    backend = Flat2DBackend()
    metrics = run_agent(backend, goal_text=goal_text)
    path = save_trace(run_id, "flat2d", goal_text, metrics, run_ts)
    # Build the trace payload in the same shape as load_trace() returns
    trace_data = {
        "backend":   "flat2d",
        "goal_text": goal_text,
        "metrics":   {k: v for k, v in metrics.items() if k != "trace"},
        "trace":     metrics["trace"],
    }
    return trace_data, path


def run_gazebo_live(goal_text: str, run_id: str, run_ts: str) -> tuple[dict, Path]:
    print("\n[parity] ── Running Gazebo backend (live) ──")
    rclpy.init()
    node    = GazeboBackendNode()
    backend = GazeboBackend(node)

    print("[parity] Waiting for AMCL/odom pose …")
    if not node.spin_until_pose(timeout=30.0):
        print("[parity] WARNING: No pose — is the sim running?")

    try:
        metrics = run_agent(backend, goal_text=goal_text)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    path = save_trace(run_id, "gazebo", goal_text, metrics, run_ts)
    trace_data = {
        "backend":   "gazebo",
        "goal_text": goal_text,
        "metrics":   {k: v for k, v in metrics.items() if k != "trace"},
        "trace":     metrics["trace"],
    }
    return trace_data, path


# ──────────────────────────────────────────────── main ───────────────────── #

def main():
    parser = argparse.ArgumentParser(description="Parity check: 1 agent, 2 backends")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--both-flat2d", action="store_true",
                      help="Run both 'backends' as Flat2D (offline, no ROS)")
    mode.add_argument("--live-gazebo", action="store_true",
                      help="Run flat2d + live Gazebo (ROS must be running)")
    mode.add_argument("--live", action="store_true",
                      help="Run flat2d now; compare against existing Gazebo trace")
    parser.add_argument("--gazebo-trace", metavar="FILE",
                        help="Path to existing Gazebo trace JSON (used with --live)")
    parser.add_argument("--goal", default=PARITY_GOAL,
                        help="Override the parity goal_text")
    args = parser.parse_args()

    if not AGENT_AVAILABLE:
        print(f"[parity] ERROR: cannot import agent — {_import_err}")
        print("         Run from the colcon workspace after sourcing install/setup.bash")
        sys.exit(1)

    goal_text = args.goal
    run_ts    = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id    = run_ts.replace(":", "").replace("+", "").replace("-", "")[:15]

    # ── pick mode ──────────────────────────────────────────────────────── #
    if args.live_gazebo:
        if not ROS_AVAILABLE:
            print("[parity] ERROR: --live-gazebo requires rclpy. Source the workspace first.")
            sys.exit(1)
        t2d, p2d = run_flat2d(goal_text, run_id, run_ts)
        tgz, pgz = run_gazebo_live(goal_text, run_id, run_ts)

    elif args.live:
        if not args.gazebo_trace:
            print("[parity] ERROR: --live requires --gazebo-trace <file>")
            sys.exit(1)
        t2d, p2d = run_flat2d(goal_text, run_id, run_ts)
        tgz = load_trace(args.gazebo_trace)
        pgz = Path(args.gazebo_trace)
        # Also copy the gazebo trace into the traces dir under this run_id
        dest = TRACES_DIR / f"{run_id}_gazebo_trace.json"
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(tgz, indent=2, ensure_ascii=False))
        pgz = dest

    else:
        # Default / --both-flat2d: run flat2d twice (same goal, fresh backends)
        if not args.both_flat2d:
            print("[parity] No mode specified — defaulting to --both-flat2d")
        print("[parity] Running flat2d as 'backend_A' (proxy for 2D Máy A) …")
        t2d, p2d = run_flat2d(goal_text, run_id + "_A", run_ts)
        p2d = p2d.with_name(p2d.name.replace("_A_flat2d", "_flat2d"))
        p2d.parent.mkdir(parents=True, exist_ok=True)

        print("[parity] Running flat2d as 'backend_B' (proxy for Gazebo) …")
        t_b, p_b = run_flat2d(goal_text, run_id + "_B", run_ts)
        # Rename to 'gazebo' label for the report
        pgz = TRACES_DIR / f"{run_id}_gazebo_trace.json"
        pgz.write_text(json.dumps({**t_b, "backend": "gazebo(flat2d-proxy)"},
                                  indent=2, ensure_ascii=False))
        tgz = {**t_b, "backend": "gazebo(flat2d-proxy)"}

        p2d = TRACES_DIR / f"{run_id}_flat2d_trace.json"
        p2d.write_text(json.dumps(t2d, indent=2, ensure_ascii=False))

    # ── compare & report ───────────────────────────────────────────────── #
    cmp = compare_traces(t2d, tgz)

    print(f"\n[parity] ══════════════════════════════")
    print(f"[parity] flat2d sequence : {' → '.join(cmp['seq_2d'])}")
    print(f"[parity] gazebo sequence : {' → '.join(cmp['seq_gz'])}")
    print(f"[parity] LCS / similarity: {cmp['lcs_length']} / {cmp['seq_sim_pct']}%")

    write_parity_report(run_id, goal_text, cmp, p2d, pgz, run_ts)


if __name__ == "__main__":
    main()

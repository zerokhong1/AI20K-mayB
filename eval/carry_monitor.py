#!/usr/bin/env python3
"""
carry_monitor.py — independent carried-continuity trace for the sim pallet.

Samples `gz model -m <PALLET_MODEL> -p` at 2 Hz and appends one JSON line per
sample to eval/results/traces/carry_trace_<timestamp>.jsonl:

    {"t": <unix float>, "x": <m>, "y": <m>, "z": <m>}
    {"t": <unix float>, "error": "gz_unavailable"}

Runs until Ctrl-C. Usage:
    python3 eval/carry_monitor.py
Override model: PALLET_MODEL=pallet_1 python3 eval/carry_monitor.py
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

PALLET_MODEL = os.environ.get("PALLET_MODEL", "pallet_1")
SAMPLE_PERIOD = 0.5   # 2 Hz

_TRIPLET_RE = re.compile(
    r'\[\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\]')


def _gz_xyz(model: str):
    """Return (x, y, z) of model world pose, or None if gz unavailable."""
    try:
        result = subprocess.run(
            ["gz", "model", "-m", model, "-p"],
            capture_output=True, text=True, timeout=5.0)
        if result.returncode != 0:
            return None
        triplets = _TRIPLET_RE.findall(result.stdout)
        if not triplets:
            return None
        return tuple(float(v) for v in triplets[0])
    except Exception:
        return None


def main():
    out_dir = Path(__file__).parent / "results" / "traces"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"carry_trace_{stamp}.jsonl"
    print(f"[carry_monitor] model={PALLET_MODEL} → {out_file} (Ctrl-C to stop)")

    n = 0
    try:
        with open(out_file, "a") as f:
            while True:
                tick = time.time()
                xyz = _gz_xyz(PALLET_MODEL)
                if xyz is None:
                    rec = {"t": tick, "error": "gz_unavailable"}
                else:
                    rec = {"t": tick, "x": xyz[0], "y": xyz[1], "z": xyz[2]}
                f.write(json.dumps(rec) + "\n")
                f.flush()
                n += 1
                remaining = SAMPLE_PERIOD - (time.time() - tick)
                if remaining > 0:
                    time.sleep(remaining)
    except KeyboardInterrupt:
        print(f"\n[carry_monitor] stopped — {n} samples in {out_file}")


if __name__ == "__main__":
    main()

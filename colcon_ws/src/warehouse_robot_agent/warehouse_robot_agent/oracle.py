#!/usr/bin/env python3
"""
Standalone oracle — reads Gazebo Harmonic ground-truth state and grades the task.

Does NOT require ROS 2 to be fully initialised; it only calls the `gz` CLI directly.
Run at any point while the Gazebo simulation is running.

Usage:
  python3 oracle.py
  ros2 run warehouse_robot_agent oracle
"""

import math
import sys

from warehouse_robot_agent.gazebo_backend import _gz_model_pose

# ─── task parameters ─────────────────────────────────────────────────────── #
DROPOFF_A        = (0.0, 0.0)
TASK_THRESHOLD_M = 1.5    # metres — pallet must be within this distance of dropoff_a

ROBOT_MODEL    = "turtlebot3_waffle"
PALLET_MODEL   = "aws_robomaker_warehouse_PalletJackB_01_001"


def grade() -> dict:
    """Query Gazebo and return a grading dict."""
    robot_gt  = _gz_model_pose(ROBOT_MODEL)
    pallet_gt = _gz_model_pose(PALLET_MODEL)

    pallet_to_dropoff: float | None = None
    task_complete = False

    if pallet_gt is not None:
        dx = pallet_gt.x - DROPOFF_A[0]
        dy = pallet_gt.y - DROPOFF_A[1]
        pallet_to_dropoff = math.sqrt(dx * dx + dy * dy)
        task_complete = pallet_to_dropoff < TASK_THRESHOLD_M

    return {
        "robot_gt_pose":        str(robot_gt)  if robot_gt  else "gz_cli_unavailable",
        "pallet_gt_pose":       str(pallet_gt) if pallet_gt else "gz_cli_unavailable",
        "pallet_to_dropoff_a_m": round(pallet_to_dropoff, 3) if pallet_to_dropoff is not None else None,
        "task_complete":         task_complete,
        "threshold_m":           TASK_THRESHOLD_M,
    }


def main():
    result = grade()
    print("=" * 46)
    print("  Gazebo Ground-Truth Oracle")
    print("=" * 46)
    print(f"  Robot GT pose  : {result['robot_gt_pose']}")
    print(f"  Pallet GT pose : {result['pallet_gt_pose']}")
    if result["pallet_to_dropoff_a_m"] is not None:
        print(f"  Pallet → dropoff_a : {result['pallet_to_dropoff_a_m']:.3f} m "
              f"(threshold {TASK_THRESHOLD_M} m)")
    else:
        print("  Pallet distance: unknown (gz CLI unavailable)")
    verdict = "PASS ✓" if result["task_complete"] else "FAIL ✗"
    print(f"  Task complete  : {verdict}")
    print("=" * 46)
    sys.exit(0 if result["task_complete"] else 1)


if __name__ == "__main__":
    main()

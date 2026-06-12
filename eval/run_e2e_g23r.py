#!/usr/bin/env python3
"""G2.3R e2e test — numbered attempt, full raw evidence.

Usage (ROS 2 sourced, sim running, carry_monitor started separately):
    python3 eval/run_e2e_g23r.py [attempt_number]
"""
import math, os, subprocess, sys, time, re
import rclpy
from warehouse_robot_agent.gazebo_backend import GazeboBackendNode, GazeboBackend, _gz_set_pose, _gz_model_pose_with_z

ATTEMPT = int(sys.argv[1]) if len(sys.argv) > 1 else 1
PALLET_MODEL = os.environ.get("PALLET_MODEL", "pallet_1")
PALLET_SPAWN = (3.45, -4.0, 0.01)   # teleport-SETUP (allowed, noted as setup)
ROBOT_SPAWN  = (3.45, -2.5, 0.03)   # teleport-SETUP robot to approach point (1.5m from pallet)
DROPOFF_A = (0.0, 0.0)

def main():
    print(f"\n=== G2.3R ATTEMPT {ATTEMPT} ===")
    print(f"pallet={PALLET_MODEL}  spawn={PALLET_SPAWN[:2]}  dropoff={DROPOFF_A}")

    # SETUP: teleport pallet + robot to known start poses (allowed for test reset)
    ok = _gz_set_pose(PALLET_MODEL, *PALLET_SPAWN)
    print(f"[SETUP] teleport pallet_1 → {PALLET_SPAWN}: {'ok' if ok else 'FAILED'}")
    ok2 = _gz_set_pose("warehouse_forklift", *ROBOT_SPAWN)
    print(f"[SETUP] teleport robot → {ROBOT_SPAWN}: {'ok' if ok2 else 'FAILED'}")
    time.sleep(2.0)

    rclpy.init()
    node = GazeboBackendNode()
    backend = GazeboBackend(node)
    if not backend._node.spin_until_pose(timeout=20.0):
        print("FAIL: no robot pose in 20 s")
        rclpy.shutdown(); return

    # SETUP: reinit AMCL from GT after robot teleport to spawn
    print("[SETUP] AMCL reinit from GT at spawn ...")
    backend._reinit_amcl_from_gt()

    # --- Milestone 0: before pick ---
    t0_pallet = _gz_model_pose_with_z(PALLET_MODEL)
    t0_robot  = _gz_model_pose_with_z("warehouse_forklift")
    print(f"\n[M0 before pick] pallet_GT={t0_pallet}  robot_GT={t0_robot}")

    # --- pick ---
    print("\n--- calling backend.pick() ---")
    pick_ok = backend.pick(PALLET_MODEL)
    print(f"pick() returned: {pick_ok}")
    t1_pallet = _gz_model_pose_with_z(PALLET_MODEL)
    t1_robot  = _gz_model_pose_with_z("warehouse_forklift")
    print(f"[M1 after pick ] pallet_GT={t1_pallet}  robot_GT={t1_robot}")
    if not pick_ok:
        print("ABORT: pick FAILED — not proceeding to drop"); rclpy.shutdown(); return

    # speed limit already set inside pick() via _set_vx_max
    print(f"[speed limit] FollowPath.vx_max set to 0.25 m/s inside pick()")

    # --- move to dropoff approach via drop() ---
    print("\n--- calling backend.drop(0,0) ---")
    drop_ok = backend.drop(*DROPOFF_A)
    print(f"drop() returned: {drop_ok}")
    t2_pallet = _gz_model_pose_with_z(PALLET_MODEL)
    t2_robot  = _gz_model_pose_with_z("warehouse_forklift")
    print(f"[M2 after drop ] pallet_GT={t2_pallet}  robot_GT={t2_robot}")

    # --- oracle ---
    print("\n--- oracle_check() ---")
    oc = backend.oracle_check()
    import json
    print(json.dumps(oc, indent=2))

    # dist to dropoff
    if t2_pallet:
        d = math.sqrt(t2_pallet[0]**2 + t2_pallet[1]**2)
        print(f"\n[RESULT] dist(pallet_final, dropoff_a) = {d:.3f} m  (threshold ≤ 0.5 m)  → {'PASS' if d<=0.5 else 'FAIL'}")
    else:
        print("[RESULT] pallet GT unavailable after drop")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()

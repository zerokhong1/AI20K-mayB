#!/usr/bin/env python3
"""G2.6b AMCL validation — 3 points × 6 measurements after new map load.

Points:
  P1 spawn (3.45, 2.15): stand 10 s → measure → spin 360° → measure
  P2 transit (~1.7, -1): Nav2 → measure
  P3 pallet (3.45, -2.8): Nav2 → measure → spin 360° → measure   ← old failure zone

Target: |AMCL − GT| < 0.5 m AND cov_trace < 0.5 at all points.

Usage (stack running: slam:=False, new map):
    source ~/AI20K/colcon_ws/install/setup.bash
    python3 eval/validate_amcl_g26b.py
"""
import json, math, re, subprocess, sys, time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Quaternion
from nav2_msgs.action import NavigateToPose, Spin

_TRIPLET_RE = re.compile(
    r'\[\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\]')

ROBOT_MODEL = "warehouse_forklift"
SPAWN = (3.45, 2.15, math.pi)
TRANSIT = (1.7, -1.0, 0.0)
PALLET_NEAR = (3.45, -2.8, math.pi)


def gz_xy(model: str):
    try:
        r = subprocess.run(["gz", "model", "-m", model, "-p"],
                           capture_output=True, text=True, timeout=8.0)
        triplets = _TRIPLET_RE.findall(r.stdout)
        if not triplets:
            return None
        x, y, _ = (float(v) for v in triplets[0])
        return (x, y)
    except Exception:
        return None


def yaw_to_quat(yaw: float) -> Quaternion:
    return Quaternion(z=math.sin(yaw / 2), w=math.cos(yaw / 2))


class ValidatorNode(Node):
    def __init__(self):
        super().__init__("amcl_validator")
        self._amcl_pose = None
        self._amcl_cov = 999.0
        self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose",
            self._amcl_cb, 10)
        self._nav = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._spin_ac = ActionClient(self, Spin, "spin")
        self._init_pub = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", 10)

    def _amcl_cb(self, msg):
        p = msg.pose.pose
        z, w = p.orientation.z, p.orientation.w
        yaw = 2 * math.atan2(z, w)
        self._amcl_pose = (p.position.x, p.position.y, yaw)
        cov = msg.pose.covariance
        self._amcl_cov = cov[0] + cov[7]

    def publish_initial_pose(self, x, y, yaw):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = "map"
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        msg.pose.pose.orientation = yaw_to_quat(yaw)
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.0685
        for _ in range(5):
            self._init_pub.publish(msg)
            time.sleep(0.2)
        self.get_logger().info(f"Published /initialpose at ({x:.2f},{y:.2f},{yaw:.2f})")

    def nav_to(self, x, y, yaw=0.0, timeout=90.0, label=""):
        label = label or f"({x:.2f},{y:.2f})"
        self.get_logger().info(f"[G2.6b] nav_to {label}")
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.orientation = yaw_to_quat(yaw)

        self._nav.wait_for_server(timeout_sec=30.0)
        future = self._nav.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=15.0)
        if not future.result() or not future.result().accepted:
            self.get_logger().warn(f"Goal {label} rejected")
            return False
        result_future = future.result().get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout)
        if not result_future.done():
            future.result().cancel_goal_async()
            return False
        return result_future.result().status == 4

    def spin_360(self):
        if not self._spin_ac.wait_for_server(timeout_sec=10.0):
            return
        goal = Spin.Goal()
        goal.target_yaw = 6.2832
        future = self._spin_ac.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if future.result() and future.result().accepted:
            result_future = future.result().get_result_async()
            rclpy.spin_until_future_complete(self, result_future, timeout_sec=30.0)

    def dwell(self, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

    def measure(self, label: str) -> dict:
        """Snapshot AMCL and GT, return comparison dict."""
        self.dwell(1.0)
        amcl = self._amcl_pose
        cov = self._amcl_cov
        gt = gz_xy(ROBOT_MODEL)
        if amcl is None:
            return {"label": label, "amcl": None, "gt": gt, "error": None,
                    "cov_trace": cov, "pass": False}
        err = None
        if gt:
            err = math.sqrt((amcl[0] - gt[0]) ** 2 + (amcl[1] - gt[1]) ** 2)
        passed = (err is not None and err < 0.5 and cov < 0.5)
        return {
            "label": label,
            "amcl_xy": (round(amcl[0], 4), round(amcl[1], 4)),
            "gt_xy": gt,
            "error_m": round(err, 4) if err is not None else None,
            "cov_trace": round(cov, 4),
            "pass": passed,
        }


def main():
    rclpy.init()
    node = ValidatorNode()
    results = []

    print("\n=== G2.6b AMCL VALIDATION (3 points) ===")
    print("Waiting for navigate_to_pose (up to 3 min)...")
    if not node._nav.wait_for_server(timeout_sec=180.0):
        print("ABORT: Nav2 not ready")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    # ── Set initial pose at spawn ─────────────────────────────────────── #
    print(f"\n[INIT] Publishing /initialpose at spawn {SPAWN}")
    node.publish_initial_pose(*SPAWN)
    node.dwell(5.0)  # allow AMCL to settle

    # ── P1: spawn ─────────────────────────────────────────────────────── #
    print("\n[P1] Spawn (3.45, 2.15) — stand 10 s")
    node.dwell(10.0)
    m = node.measure("P1-stand")
    results.append(m)
    print(f"  P1-stand: amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
          f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")

    print("[P1] Spin 360°")
    node.spin_360()
    node.dwell(2.0)
    m = node.measure("P1-after-spin")
    results.append(m)
    print(f"  P1-spin:  amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
          f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")

    # ── P2: transit ────────────────────────────────────────────────────── #
    print(f"\n[P2] Nav → transit {TRANSIT[:2]}")
    node.nav_to(*TRANSIT, label="P2-transit")
    node.dwell(3.0)
    m = node.measure("P2-transit")
    results.append(m)
    print(f"  P2: amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
          f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")

    # ── P3: pallet area (old failure zone) ────────────────────────────── #
    print(f"\n[P3] Nav → pallet (3.45, -2.8) — OLD FAILURE ZONE")
    node.nav_to(*PALLET_NEAR, label="P3-pallet")
    node.dwell(3.0)
    m = node.measure("P3-stand")
    results.append(m)
    print(f"  P3-stand: amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
          f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")

    print("[P3] Spin 360°")
    node.spin_360()
    node.dwell(2.0)
    m = node.measure("P3-after-spin")
    results.append(m)
    print(f"  P3-spin:  amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
          f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")

    # ── Summary ────────────────────────────────────────────────────────── #
    print("\n=== G2.6b SUMMARY (RAW) ===")
    print(json.dumps(results, indent=2))

    all_pass = all(r["pass"] for r in results)
    print(f"\nG2.6b: {'PASS' if all_pass else 'FAIL'}")

    # ── 1-round fix attempt if P3 failed ─────────────────────────────── #
    p3_pass = all(r["pass"] for r in results if r["label"].startswith("P3"))
    if not p3_pass:
        print("\n[P3 FAIL] Plan B: bump laser_likelihood_max_dist 2→4, max_beams 60→180")
        for param, val in [
            ("amcl.laser_likelihood_max_dist", "4.0"),
            ("amcl.max_beams", "180"),
        ]:
            r = subprocess.run(
                ["ros2", "param", "set", "/amcl", param, val],
                capture_output=True, text=True, timeout=5.0)
            print(f"  ros2 param set /amcl {param} {val} → rc={r.returncode} {r.stdout.strip()!r}")
        print("Waiting 5 s for AMCL to re-converge with new params...")
        node.dwell(5.0)
        m = node.measure("P3-planB")
        results.append(m)
        print(f"  P3-planB: amcl={m.get('amcl_xy')} gt={m.get('gt_xy')} "
              f"err={m.get('error_m')} cov={m.get('cov_trace')} → {'PASS' if m['pass'] else 'FAIL'}")
        if m["pass"]:
            print("  → Plan B PASS: add these params permanently to nav2_params.yaml")
        else:
            print("  → Plan B also FAIL — stop here, report raw")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

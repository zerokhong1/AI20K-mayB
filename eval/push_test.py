#!/usr/bin/env python3
"""
push_test.py — R3 push test (Phase 1.5 G1.2): prove /cmd_vel physically moves
the robot and that /odom and Gazebo ground truth agree on the displacement.

1. Reads /odom and `gz model -m warehouse_forklift -p` before.
2. Publishes /cmd_vel Twist (0.10 m/s for 5 s → ~0.5 m forward), then stops.
3. Reads both sources after and prints a delta table.

Usage (ROS 2 sourced, sim running):
    python3 eval/push_test.py
"""

import math
import re
import subprocess
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node

ROBOT_MODEL = "warehouse_forklift"
PUSH_SPEED = 0.10    # m/s
PUSH_SECONDS = 5.0   # → ~0.5 m

_TRIPLET_RE = re.compile(
    r'\[\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\]')


def gz_xy(model: str):
    try:
        result = subprocess.run(
            ["gz", "model", "-m", model, "-p"],
            capture_output=True, text=True, timeout=5.0)
        if result.returncode != 0:
            return None
        triplets = _TRIPLET_RE.findall(result.stdout)
        if not triplets:
            return None
        x, y, _z = (float(v) for v in triplets[0])
        return (x, y)
    except Exception:
        return None


class PushTestNode(Node):
    def __init__(self):
        super().__init__("push_test")
        self.odom = None
        self.create_subscription(Odometry, "/odom", self._odom_cb, 10)
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)

    def _odom_cb(self, msg):
        p = msg.pose.pose.position
        self.odom = (p.x, p.y)

    def wait_odom(self, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.odom is not None:
                return self.odom
        return None

    def drive(self, vx, seconds):
        twist = Twist()
        twist.linear.x = vx
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)
        # stop
        twist = Twist()
        for _ in range(5):
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)


def main():
    rclpy.init()
    node = PushTestNode()

    odom_before = node.wait_odom()
    if odom_before is None:
        print("FAIL: no /odom message in 15 s — is the sim running?")
        rclpy.shutdown()
        return
    gz_before = gz_xy(ROBOT_MODEL)

    print(f"[push_test] driving {PUSH_SPEED} m/s for {PUSH_SECONDS} s "
          f"(~{PUSH_SPEED * PUSH_SECONDS:.2f} m) ...")
    node.drive(PUSH_SPEED, PUSH_SECONDS)
    time.sleep(1.0)  # settle

    # refresh odom
    node.odom = None
    odom_after = node.wait_odom()
    gz_after = gz_xy(ROBOT_MODEL)

    def dist(a, b):
        if a is None or b is None:
            return None
        return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)

    rows = [
        ("odom", odom_before, odom_after, dist(odom_before, odom_after)),
        ("gz_gt", gz_before, gz_after, dist(gz_before, gz_after)),
    ]
    print("| source | before_x | after_x | delta |")
    print("|--------|----------|---------|-------|")
    for name, before, after, d in rows:
        bx = f"{before[0]:.3f}" if before else "n/a"
        ax = f"{after[0]:.3f}" if after else "n/a"
        dd = f"{d:.3f}" if d is not None else "n/a"
        print(f"| {name} | {bx} | {ax} | {dd} |")

    # R2: unrounded deltas (full float precision, no rounding)
    for name, before, after, d in rows:
        print(f"[unrounded] {name}: before={before!r} after={after!r} delta={d!r}")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""B2.6.1 Mapping drive — drives warehouse route for SLAM rebake.

Route: spawn (3.45,2.15) → dropoff (0,0) → transit (1.7,-1)
       → near-pallet (3.45,-2.8) → pallet (3.45,-4) → aisle-end (3.45,-5)
       → aisle-mid (3.45,-2) → spawn return

Spins 360° at: spawn, pallet area, spawn return.

Usage (SLAM stack running: slam:=True spawn_pallet:=false):
    source ~/AI20K/colcon_ws/install/setup.bash
    python3 eval/slam_mapping_drive.py
"""
import math, time, sys
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav2_msgs.action import NavigateToPose, Spin
from geometry_msgs.msg import PoseStamped, Quaternion


def yaw_to_quat(yaw: float) -> Quaternion:
    return Quaternion(z=math.sin(yaw / 2), w=math.cos(yaw / 2))


class MappingDriver(Node):
    def __init__(self):
        super().__init__("slam_mapping_driver")
        self._nav = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._spin_ac = ActionClient(self, Spin, "spin")

    # ------------------------------------------------------------------ #

    def nav_to(self, x: float, y: float, yaw: float = 0.0,
               timeout: float = 90.0, label: str = "") -> bool:
        label = label or f"({x:.2f},{y:.2f})"
        self.get_logger().info(f"[mapping] nav_to {label}")
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.orientation = yaw_to_quat(yaw)

        if not self._nav.wait_for_server(timeout_sec=30.0):
            self.get_logger().error("navigate_to_pose server not available!")
            return False

        future = self._nav.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=15.0)
        if not future.result() or not future.result().accepted:
            self.get_logger().warn(f"Goal to {label} rejected or timed out")
            return False

        goal_handle = future.result()
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout)

        if not result_future.done():
            self.get_logger().warn(f"Nav to {label}: timeout after {timeout}s")
            goal_handle.cancel_goal_async()
            return False

        status = result_future.result().status
        ok = (status == 4)  # SUCCEEDED
        self.get_logger().info(f"[mapping] nav_to {label}: {'PASS' if ok else f'FAIL(status={status})'}")
        return ok

    def spin_360(self, label: str = "") -> bool:
        self.get_logger().info(f"[mapping] spin_360 {label}")
        if not self._spin_ac.wait_for_server(timeout_sec=10.0):
            self.get_logger().warn("spin action server not available, skipping")
            return False
        goal = Spin.Goal()
        goal.target_yaw = 6.2832  # 2π
        future = self._spin_ac.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.result() or not future.result().accepted:
            self.get_logger().warn("Spin goal rejected")
            return False
        result_future = future.result().get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=30.0)
        return True

    def dwell(self, seconds: float):
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)


def main():
    rclpy.init()
    driver = MappingDriver()

    print("\n=== B2.6.1 SLAM MAPPING DRIVE ===")
    print("Waiting for navigate_to_pose action server (up to 3 min)...")
    if not driver._nav.wait_for_server(timeout_sec=180.0):
        print("ABORT: navigate_to_pose not available after 180 s")
        driver.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    print("Nav2 ready. Starting mapping route...\n")
    driver.dwell(3.0)

    # ── 1. Spin at spawn to seed map ──────────────────────────────────── #
    print("[1/8] SPIN at spawn (3.45, 2.15)")
    driver.spin_360("spawn")
    driver.dwell(2.0)

    # ── 2. Drive to dropoff ───────────────────────────────────────────── #
    print("[2/8] NAV → dropoff (0, 0)")
    driver.nav_to(0.0, 0.0, yaw=0.0, label="dropoff")
    driver.dwell(2.0)

    # ── 3. Transit area ──────────────────────────────────────────────── #
    print("[3/8] NAV → transit (1.7, -1)")
    driver.nav_to(1.7, -1.0, label="transit")
    driver.dwell(1.0)

    # ── 4. Near-pallet (critical AMCL failure zone) ───────────────────── #
    print("[4/8] NAV → near-pallet (3.45, -2.8)")
    driver.nav_to(3.45, -2.8, label="near-pallet")
    driver.dwell(1.0)
    driver.spin_360("near-pallet")
    driver.dwell(1.0)

    # ── 5. Pallet area ────────────────────────────────────────────────── #
    print("[5/8] NAV → pallet area (3.45, -4)")
    driver.nav_to(3.45, -4.0, yaw=math.pi, label="pallet-area")
    driver.dwell(2.0)
    driver.spin_360("pallet-area")
    driver.dwell(1.0)

    # ── 6. Aisle end ──────────────────────────────────────────────────── #
    print("[6/8] NAV → aisle end (3.45, -5)")
    driver.nav_to(3.45, -5.0, label="aisle-end")
    driver.dwell(1.0)

    # ── 7. Aisle mid (y ∈ [-5,-2] traversal) ─────────────────────────── #
    print("[7/8] NAV → aisle mid (3.45, -2)")
    driver.nav_to(3.45, -2.0, label="aisle-mid")
    driver.dwell(1.0)

    # ── 8. Return to spawn ────────────────────────────────────────────── #
    print("[8/8] NAV → spawn return (3.45, 2.15)")
    driver.nav_to(3.45, 2.15, yaw=math.pi, label="spawn-return")
    driver.dwell(2.0)
    driver.spin_360("spawn-return")

    print("\n=== MAPPING ROUTE COMPLETE ===")
    print("Now save map:")
    print("  ros2 run nav2_map_server map_saver_cli -f "
          "~/AI20K/colcon_ws/src/warehouse_nav/maps/warehouse_lidar0625")

    driver.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

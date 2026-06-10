"""
GazeboBackend — implements WorldBackend using ROS 2 Nav2 + Gazebo Harmonic.

Tools backed by real ROS 2 calls:
  perceive      → /amcl_pose  +  /odom
  locate_object → /warehouse/detected_objects (from PerceptionNode); falls back to registry
  check_path    → Nav2 ComputePathToPose action
  move_to       → Nav2 NavigateToPose action
  pick / drop   → stubs (MoveIt integration is D10+)
  oracle_check  → Gazebo model pose query via gz CLI
"""

import json
import math
import subprocess
import time
from typing import Optional

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import ComputePathToPose, NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Float64, String

from .world_backend import Pose2D, WorldBackend, WorldView

# Ground-truth object registry: parsed from small_warehouse.world
# Format: name -> (x, y)  — yaw treated as 0 for simplicity
_WORLD_OBJECTS: dict[str, tuple[float, float]] = {
    "pallet_jack":      (-0.28, -9.48),   # aws_robomaker_warehouse_PalletJackB_01_001
    "clutter_c_027":    (3.32,   3.82),
    "clutter_c_028":    (5.54,   3.82),
    "clutter_c_029":    (5.38,   6.14),
    "clutter_c_030":    (3.24,   6.14),
    "clutter_d_005":    (-1.63, -7.81),
    # Delivery drop-off zones (open aisle areas)
    "dropoff_a":        (0.0,    0.0),
    "dropoff_b":        (3.45,   2.15),
}


class GazeboBackendNode(Node):
    """Thin ROS 2 node that owns subscriptions and action clients."""

    def __init__(self):
        super().__init__("gazebo_backend")
        self._amcl_pose: Optional[Pose2D] = None
        self._odom_pose: Optional[Pose2D] = None

        # Latest detections from PerceptionNode (or None if not running)
        self._detections: dict[str, dict] = {}
        self._detections_stamp: float = 0.0   # time.time() of last update

        self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose",
            self._amcl_cb, 10)
        self.create_subscription(
            Odometry, "/odom",
            self._odom_cb, 10)
        self.create_subscription(
            String, "/warehouse/detected_objects",
            self._detections_cb, 10)

        self._nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._path_client = ActionClient(self, ComputePathToPose, "compute_path_to_pose")

        # Fork height publisher — None when running with TB3 (stub mode)
        self._fork_pub = self.create_publisher(Float64, "/fork_cmd", 10)

    # ------------------------------------------------------------------ #
    def _amcl_cb(self, msg: PoseWithCovarianceStamped):
        p = msg.pose.pose
        yaw = _quat_to_yaw(p.orientation.x, p.orientation.y,
                           p.orientation.z, p.orientation.w)
        self._amcl_pose = Pose2D(p.position.x, p.position.y, yaw)

    def _odom_cb(self, msg: Odometry):
        p = msg.pose.pose
        yaw = _quat_to_yaw(p.orientation.x, p.orientation.y,
                           p.orientation.z, p.orientation.w)
        self._odom_pose = Pose2D(p.position.x, p.position.y, yaw)

    def _detections_cb(self, msg: String):
        try:
            self._detections = json.loads(msg.data)
            self._detections_stamp = time.time()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def best_pose(self) -> Optional[Pose2D]:
        """AMCL (map-frame) preferred; fall back to odom."""
        return self._amcl_pose or self._odom_pose

    def spin_until_pose(self, timeout: float = 10.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.best_pose() is not None:
                return True
        return False

    def navigate(self, x: float, y: float, yaw: float, timeout: float = 120.0) -> bool:
        if not self._nav_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("NavigateToPose action server not available")
            return False

        goal = NavigateToPose.Goal()
        goal.pose = _make_stamped(x, y, yaw)

        future = self._nav_client.send_goal_async(goal)
        _spin_until(self, future, timeout=15.0)
        if not future.done() or not future.result().accepted:
            self.get_logger().error("Goal rejected")
            return False

        result_future = future.result().get_result_async()
        _spin_until(self, result_future, timeout=timeout)
        if not result_future.done():
            self.get_logger().error("Navigation timed out")
            return False

        status = result_future.result().status
        return status == GoalStatus.STATUS_SUCCEEDED

    def has_path(self, x: float, y: float) -> bool:
        if not self._path_client.wait_for_server(timeout_sec=5.0):
            return False
        goal = ComputePathToPose.Goal()
        goal.goal = _make_stamped(x, y, 0.0)
        future = self._path_client.send_goal_async(goal)
        _spin_until(self, future, timeout=10.0)
        if not future.done() or not future.result().accepted:
            return False
        result_future = future.result().get_result_async()
        _spin_until(self, result_future, timeout=10.0)
        if not result_future.done():
            return False
        status = result_future.result().status
        return status == GoalStatus.STATUS_SUCCEEDED


# ======================================================================= #
class GazeboBackend(WorldBackend):
    """WorldBackend backed by Gazebo Harmonic + Nav2."""

    def __init__(self, node: GazeboBackendNode):
        self._node = node
        self._carrying: Optional[str] = None
        # Accumulates locate_object source strings for the current task run.
        # Cleared by the caller (eval runner) between tasks.
        self.locate_log: list[str] = []

    # ------------------------------------------------------------------ #
    def perceive(self) -> WorldView:
        self._node.spin_until_pose(timeout=5.0)
        pose = self._node.best_pose() or Pose2D(0.0, 0.0, 0.0)
        objects = {k: Pose2D(v[0], v[1], 0.0) for k, v in _WORLD_OBJECTS.items()}
        return WorldView(robot_pose=pose, objects=objects,
                         map_info="aws_small_warehouse")

    def locate_object(self, name: str) -> Optional[Pose2D]:
        # 1. Live detections from PerceptionNode (ARMBench or gz_gt backend)
        #    Use if fresh (< 2 s old).
        if self._node._detections and (time.time() - self._node._detections_stamp) < 2.0:
            det = self._node._detections.get(name)
            if det:
                source = det.get("source", "perception_unknown")
                self.locate_log.append(f"perception({source})")
                self._node.get_logger().debug(
                    f"[locate_object] {name} from perception ({source}): "
                    f"({det['x']:.3f}, {det['y']:.3f})")
                return Pose2D(det["x"], det["y"], det.get("yaw", 0.0))

        # 2. Ground-truth registry (static objects / fallback)
        entry = _WORLD_OBJECTS.get(name)
        if entry:
            self.locate_log.append("gt_registry")
            return Pose2D(entry[0], entry[1], 0.0)

        # 3. gz CLI for arbitrary model names not in registry
        pose = _gz_model_pose(name)
        self.locate_log.append("gz_cli" if pose is not None else "not_found")
        return pose

    def check_path(self, x: float, y: float) -> bool:
        return self._node.has_path(x, y)

    def move_to(self, x: float, y: float, yaw: float = 0.0) -> bool:
        self._node.get_logger().info(f"[GazeboBackend] move_to ({x:.2f}, {y:.2f})")
        return self._node.navigate(x, y, yaw)

    def pick(self, object_name: str) -> bool:
        """Lower fork → slide under pallet → raise fork."""
        log = self._node.get_logger()
        log.info(f"[GazeboBackend] pick {object_name}")

        # Lower fork to floor level
        if not self._set_fork(0.02):
            log.warn("pick: fork lower failed — continuing anyway")
        self._spin_seconds(1.5)

        # Raise fork to lift height (0.18 m clears the pallet jack ~0.15 m tall)
        if not self._set_fork(0.20):
            log.warn("pick: fork raise failed — object may not be lifted")
        self._spin_seconds(2.0)

        self._carrying = object_name
        log.info(f"[GazeboBackend] pick done — carrying {object_name}")
        return True

    def drop(self, x: float, y: float) -> bool:
        """Lower fork → robot backs up → fork is free."""
        log = self._node.get_logger()
        log.info(f"[GazeboBackend] drop at ({x:.2f}, {y:.2f})")

        if not self._set_fork(0.02):
            log.warn("drop: fork lower failed — continuing anyway")
        self._spin_seconds(2.0)

        self._carrying = None
        log.info("[GazeboBackend] drop done")
        return True

    # ------------------------------------------------------------------ #
    def _set_fork(self, height: float) -> bool:
        """Publish target fork height (metres). Returns True (fire-and-forget)."""
        msg = Float64()
        msg.data = float(height)
        self._node._fork_pub.publish(msg)
        return True

    def _spin_seconds(self, seconds: float):
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self._node, timeout_sec=0.1)

    def oracle_check(self) -> dict:
        # Task parameters
        DROPOFF_A = (0.0, 0.0)
        TASK_THRESHOLD_M = 1.5   # pallet must be within this distance of dropoff_a

        # AMCL localisation estimate
        amcl = self._node.best_pose()
        if amcl is None:
            self._node.spin_until_pose(timeout=3.0)
            amcl = self._node.best_pose()

        # Ground-truth poses straight from Gazebo (independent of Nav2/AMCL)
        robot_gt  = _gz_model_pose("turtlebot3_waffle")
        pallet_gt = _gz_model_pose("aws_robomaker_warehouse_PalletJackB_01_001")

        # Task-success verdict
        pallet_to_dropoff: Optional[float] = None
        task_complete = False
        if pallet_gt is not None:
            dx = pallet_gt.x - DROPOFF_A[0]
            dy = pallet_gt.y - DROPOFF_A[1]
            pallet_to_dropoff = math.sqrt(dx * dx + dy * dy)
            task_complete = pallet_to_dropoff < TASK_THRESHOLD_M

        return {
            "backend": "gazebo_harmonic",
            "amcl_pose": str(amcl) if amcl else "unavailable",
            "robot_gt_pose": str(robot_gt) if robot_gt else "gz_cli_unavailable",
            "pallet_gt_pose": str(pallet_gt) if pallet_gt else "gz_cli_unavailable",
            "pallet_to_dropoff_a_m": (
                round(pallet_to_dropoff, 3) if pallet_to_dropoff is not None else None
            ),
            "carrying": self._carrying,
            "task_complete": task_complete,
        }


# ======================================================================= #
# Helpers
# ======================================================================= #

def _quat_to_yaw(x, y, z, w) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def _make_stamped(x: float, y: float, yaw: float) -> PoseStamped:
    from geometry_msgs.msg import Quaternion
    msg = PoseStamped()
    msg.header.frame_id = "map"
    msg.pose.position.x = x
    msg.pose.position.y = y
    msg.pose.position.z = 0.0
    half = yaw / 2.0
    msg.pose.orientation = Quaternion(x=0.0, y=0.0, z=math.sin(half), w=math.cos(half))
    return msg


def _spin_until(node: Node, future, timeout: float = 30.0):
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        rclpy.spin_until_future_complete(node, future, timeout_sec=0.5)


def _gz_model_pose(model_name: str) -> Optional[Pose2D]:
    """Query Gazebo Harmonic for a model's world pose via gz CLI.

    Parses the `gz model -m <name> -p` output format:
        - Pose [ XYZ (m) ] [ RPY (rad) ]:
          [x y z]
          [roll pitch yaw]
    """
    import re
    try:
        result = subprocess.run(
            ["gz", "model", "-m", model_name, "-p"],
            capture_output=True, text=True, timeout=5.0)
        if result.returncode != 0:
            return None
        # Find all bracket-enclosed float triplets in output order.
        # First match = XYZ, second match = RPY.
        triplets = re.findall(
            r'\[\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'   # first number
            r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'     # second number
            r'\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\]',
            result.stdout)
        if len(triplets) < 2:
            return None
        x, y, _z  = (float(v) for v in triplets[0])
        _r, _p, yaw = (float(v) for v in triplets[1])
        return Pose2D(x, y, yaw)
    except Exception:
        return None

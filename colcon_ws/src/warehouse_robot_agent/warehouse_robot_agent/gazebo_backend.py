"""
GazeboBackend — implements WorldBackend using ROS 2 Nav2 + Gazebo Harmonic.

Tools backed by real ROS 2 calls:
  perceive      → /amcl_pose  +  /odom
  locate_object → /warehouse/detected_objects (from PerceptionNode); falls back to registry
  check_path    → Nav2 ComputePathToPose action
  move_to       → Nav2 NavigateToPose action
  pick / drop   → physics: GT servo docking + fork lift via /fork_cmd (P2)
  oracle_check  → Gazebo model pose query via gz CLI
"""

import json
import math
import os
import subprocess
import time
from typing import Optional

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from nav2_msgs.action import ComputePathToPose, NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Float64, String

from .world_backend import Pose2D, WorldBackend, WorldView

# Pallet model used by the GT oracle (override with PALLET_MODEL env var)
PALLET_MODEL = os.environ.get("PALLET_MODEL", "pallet_1")

# Logical name → Gazebo model name
_GZ_MODEL_NAMES: dict[str, str] = {
    "pallet_jack": "aws_robomaker_warehouse_PalletJackB_01_001",
    "pallet_1": "pallet_1",
}

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
    "pallet_1":         (3.45,  -4.0),    # sim_pallet spawn position (P2)
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

        # Direct velocity commands for the docking servo loop (P2)
        self._cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)

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
        if self.best_pose() is not None:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                rclpy.spin_once(self, timeout_sec=0.1)
            except Exception:
                time.sleep(0.1)
            if self.best_pose() is not None:
                return True
        return False

    def navigate(self, x: float, y: float, yaw: float, timeout: float = 30.0) -> bool:
        try:
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
        except Exception as exc:
            self.get_logger().error(f"Navigation exception: {exc}")
            return False

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
        success = self._node.navigate(x, y, yaw)
        if not success:
            # Nav2 often reports FOLLOW_PATH_FAILED when the robot reaches close
            # but can't satisfy the exact goal tolerance due to costmap inflation.
            # Return True if robot is already within 1.5 m (oracle threshold).
            pose = self._node.best_pose()
            if pose is not None:
                dist = math.sqrt((pose.x - x) ** 2 + (pose.y - y) ** 2)
                if dist < 1.5:
                    self._node.get_logger().info(
                        f"[GazeboBackend] nav failed but within {dist:.2f} m of goal — treating as success")
                    return True
        return success

    # ------------------------------------------------------------------ #
    # P2 physics pick/drop — NO teleport (_gz_set_pose) in this path.
    # ------------------------------------------------------------------ #
    _DOCK_DIST_MIN = 0.62      # m, robot-center → pallet-center docking band
    _DOCK_DIST_MAX = 0.72
    _DOCK_BEARING_TOL = 0.0873  # rad (5°)

    def pick(self, object_name: str) -> bool:
        """Physics pick: Nav2 approach → GT servo dock → fork lift → verify.

        Verification is double: pallet z must rise ≥ 0.10 m (lifted) and
        pallet xy displacement during a 0.5 m reverse must track the robot
        (carried-continuity, ≤ 0.05 m mismatch).
        """
        log = self._node.get_logger()
        log.info(f"[GazeboBackend] pick {object_name} (physics)")
        gz_name = _GZ_MODEL_NAMES.get(object_name, object_name)

        # a) locate pallet (GT via gz CLI preferred — registry may be stale)
        pallet = _gz_model_pose_with_z(gz_name)
        if pallet is None:
            p2d = self.locate_object(object_name)
            if p2d is None:
                log.error(f"pick: cannot locate {object_name}")
                return False
            pallet = (p2d.x, p2d.y, 0.0, p2d.yaw)
        px, py = pallet[0], pallet[1]

        # b) approach point: 1.2 m from pallet on the robot's side
        robot = _gz_model_pose_with_z("warehouse_forklift")
        if robot is None:
            pose = self._node.best_pose()
            if pose is None:
                log.error("pick: no robot pose available")
                return False
            robot = (pose.x, pose.y, 0.0, pose.yaw)
        away = math.atan2(robot[1] - py, robot[0] - px)   # pallet → robot
        ax = px + 1.2 * math.cos(away)
        ay = py + 1.2 * math.sin(away)
        yaw_to_pallet = math.atan2(py - ay, px - ax)

        # c) Nav2 to approach point
        if not self.move_to(ax, ay, yaw_to_pallet):
            log.warn("pick: approach move_to failed — attempting servo anyway")

        # d) fork to ground
        self._set_fork(0.0)
        self._spin_seconds(1.0)

        # e) servo dock on GT poses (5 Hz max, ≤ 0.12 m/s)
        if not self._servo_dock(gz_name, timeout=30.0):
            self._stop_robot()
            log.error("pick: docking failed — aborting")
            return False

        # f) stop
        self._stop_robot()

        # g) pallet z before lift
        before = _gz_model_pose_with_z(gz_name)
        pallet_z_before = before[2] if before else 0.0

        # h) lift
        self._set_fork(0.20)
        self._spin_seconds(3.0)

        # i) pallet z + robot pose after lift
        after = _gz_model_pose_with_z(gz_name)
        robot_after = _gz_model_pose_with_z("warehouse_forklift")
        pallet_z_after = after[2] if after else 0.0

        # j) reverse ~0.5 m while carrying (gentle: pallet sits free on plate;
        #    -0.08/6 s caused micro-slide transients → carry_err 0.077)
        self._drive_timed(-0.06, 8.5)

        # k) settle, then poses after reverse
        self._spin_seconds(1.0)
        gt_rev = _gz_dynamic_poses()
        pallet_rev = gt_rev.get(gz_name) or _gz_model_pose_with_z(gz_name)
        robot_rev = gt_rev.get("warehouse_forklift") or _gz_model_pose_with_z("warehouse_forklift")

        # l) verify lift + carried-continuity
        z_lifted = pallet_z_after - pallet_z_before
        carry_err: Optional[float] = None
        if after and robot_after and pallet_rev and robot_rev:
            dpx = pallet_rev[0] - after[0]
            dpy = pallet_rev[1] - after[1]
            drx = robot_rev[0] - robot_after[0]
            dry = robot_rev[1] - robot_after[1]
            carry_err = math.sqrt((dpx - drx) ** 2 + (dpy - dry) ** 2)
            log.info(f"pick verify: d_pallet=({dpx:.3f},{dpy:.3f}) "
                     f"d_robot=({drx:.3f},{dry:.3f}) "
                     f"pallet_z_rev={pallet_rev[2]:.3f} "
                     f"pallet_yaw {after[3]:.2f}→{pallet_rev[3]:.2f}")
        lift_ok = z_lifted >= 0.10
        carry_ok = carry_err is not None and carry_err <= 0.05

        # m) verdict
        if lift_ok and carry_ok:
            self._carrying = object_name
            log.info(f"[GazeboBackend] pick SUCCESS — z_lifted={z_lifted:.3f} m, "
                     f"carry_err={carry_err:.3f} m, carrying {object_name}")
            return True
        log.error(f"[GazeboBackend] pick FAILED — z_lifted={z_lifted:.3f} m "
                  f"(need ≥0.10), carry_err="
                  f"{'n/a' if carry_err is None else f'{carry_err:.3f}'} m (need ≤0.05)")
        return False

    def drop(self, x: float, y: float) -> bool:
        """Physics drop: approach → advance → lower fork → reverse → verify.

        Success = pallet GT within 0.5 m of (x, y) AND back on the ground
        (model z ≤ 0.05 m). No teleport.
        """
        log = self._node.get_logger()
        log.info(f"[GazeboBackend] drop at ({x:.2f}, {y:.2f}) (physics)")
        gz_name = _GZ_MODEL_NAMES.get(self._carrying or "", self._carrying or PALLET_MODEL)

        # a) approach point 1.0 m short of (x, y) along robot → goal line
        robot = _gz_model_pose_with_z("warehouse_forklift")
        if robot is None:
            pose = self._node.best_pose()
            robot = (pose.x, pose.y, 0.0, pose.yaw) if pose else (0.0, 0.0, 0.0, 0.0)
        toward = math.atan2(y - robot[1], x - robot[0])   # robot → goal
        ax = x - 1.0 * math.cos(toward)
        ay = y - 1.0 * math.sin(toward)
        yaw_to_goal = math.atan2(y - ay, x - ax)

        # b) Nav2 to approach point
        if not self.move_to(ax, ay, yaw_to_goal):
            log.warn("drop: approach move_to failed — attempting placement anyway")

        # c) advance ~0.4 m to put the pallet over the goal
        self._drive_timed(0.08, 5.0)

        # d) lower fork
        self._set_fork(0.0)
        self._spin_seconds(2.0)

        # e) reverse ~0.6 m to clear the fork from under the deck
        self._drive_timed(-0.08, 7.5)

        # f-g) verify pallet GT placement
        self._carrying = None
        pallet = _gz_model_pose_with_z(gz_name)
        if pallet is None:
            log.error("drop: pallet GT pose unavailable — cannot verify")
            return False
        pallet_to_goal = math.sqrt((pallet[0] - x) ** 2 + (pallet[1] - y) ** 2)
        grounded = pallet[2] <= 0.05

        # h) verdict
        if pallet_to_goal <= 0.5 and grounded:
            log.info(f"[GazeboBackend] drop SUCCESS — pallet_to_goal="
                     f"{pallet_to_goal:.3f} m, z={pallet[2]:.3f} m")
            return True
        log.error(f"[GazeboBackend] drop FAILED — pallet_to_goal={pallet_to_goal:.3f} m "
                  f"(need ≤0.5), z={pallet[2]:.3f} m (need ≤0.05)")
        return False

    # ------------------------------------------------------------------ #
    def _servo_dock(self, gz_pallet_name: str, timeout: float = 30.0) -> bool:
        """Closed-loop dock on GT poses until robot-pallet distance is in the
        docking band with the pallet dead ahead. 5 Hz max (gz CLI ≈ 100 ms/read)."""
        log = self._node.get_logger()
        deadline = time.time() + timeout
        tick = 0
        while time.time() < deadline:
            tick += 1
            tick_start = time.time()
            gt = _gz_dynamic_poses()   # one call: robot + pallet (~120 ms)
            robot = gt.get("warehouse_forklift")
            pallet = gt.get(gz_pallet_name)
            if robot is None or pallet is None:
                log.warn("servo_dock: GT pose unavailable — retrying")
                time.sleep(0.2)
                continue
            dx = pallet[0] - robot[0]
            dy = pallet[1] - robot[1]
            dist = math.sqrt(dx * dx + dy * dy)
            bearing = _norm_angle(math.atan2(dy, dx) - robot[3])

            if (self._DOCK_DIST_MIN <= dist <= self._DOCK_DIST_MAX
                    and abs(bearing) <= self._DOCK_BEARING_TOL):
                self._stop_robot()
                log.info(f"servo_dock: DOCKED dist={dist:.3f} m bearing={math.degrees(bearing):.1f}°")
                return True
            if dist < self._DOCK_DIST_MIN:
                self._stop_robot()
                log.error(f"servo_dock: overshoot dist={dist:.3f} m "
                          f"bearing={math.degrees(bearing):.1f}° — abort")
                return False

            twist = Twist()
            twist.linear.x = 0.12 if abs(bearing) < 0.2 else 0.05
            twist.angular.z = max(-1.0, min(1.0, 1.5 * bearing))
            self._node._cmd_vel_pub.publish(twist)
            if tick % 10 == 1:
                log.info(f"servo_dock: dist={dist:.3f} m "
                         f"bearing={math.degrees(bearing):.1f}° "
                         f"cmd=({twist.linear.x:.2f}, {twist.angular.z:.2f})")

            # enforce ≤ 5 Hz
            elapsed = time.time() - tick_start
            if elapsed < 0.2:
                self._spin_seconds(0.2 - elapsed)
        self._stop_robot()
        log.error("servo_dock: timeout")
        return False

    def _drive_timed(self, vx: float, seconds: float):
        """Drive at constant vx for `seconds` with heading hold, then stop.

        Heading hold (P on Gazebo GT yaw, ref = yaw at start) is required:
        reversing a diff-drive with rear casters is directionally unstable —
        open-loop reverse veered ~0.8 rad over 0.5 m and span the carried
        pallet off the fork (carry_err 0.31 m, e2e attempt 3). Odom yaw can
        NOT be used as reference: the veer comes from lateral wheel slip,
        which wheel odometry does not see (attempt 4: odom-hold still veered
        0.64 rad). GT read is ~0.1 s → 5 Hz control ticks.
        """
        gt = _gz_dynamic_poses().get("warehouse_forklift")
        ref_yaw = gt[3] if gt else None
        twist = Twist()
        twist.linear.x = float(vx)
        deadline = time.time() + seconds
        while time.time() < deadline:
            if ref_yaw is not None:
                cur = _gz_dynamic_poses().get("warehouse_forklift")
                if cur is not None:
                    err = _norm_angle(ref_yaw - cur[3])
                    twist.angular.z = max(-0.3, min(0.3, 2.0 * err))
            self._node._cmd_vel_pub.publish(twist)
            self._spin_seconds(0.1)
        self._stop_robot()

    def _stop_robot(self):
        """Publish zero Twist a few times to halt the base."""
        twist = Twist()
        for _ in range(3):
            self._node._cmd_vel_pub.publish(twist)
            self._spin_seconds(0.05)

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
            try:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            except Exception:
                time.sleep(0.1)

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
        robot_gt  = _gz_model_pose("warehouse_forklift")
        pallet_gt = _gz_model_pose(_GZ_MODEL_NAMES.get(PALLET_MODEL, PALLET_MODEL))

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


def _norm_angle(a: float) -> float:
    """Wrap angle to [-pi, pi]."""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


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
        try:
            rclpy.spin_until_future_complete(node, future, timeout_sec=0.5)
        except Exception:
            break


def _gz_set_pose(gz_model_name: str, x: float, y: float, z: float = 0.01) -> bool:
    """SETUP/RESET ONLY — FORBIDDEN in pick()/drop() action path.

    Teleport a Gazebo model to (x, y, z) via gz service set_pose. Used by the
    eval runner to reset the world between tasks, never by action tools.
    """
    req = (f'name: "{gz_model_name}", '
           f'position: {{x: {x:.4f}, y: {y:.4f}, z: {z:.4f}}}')
    try:
        result = subprocess.run(
            ["gz", "service", "-s", "/world/default/set_pose",
             "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
             "--timeout", "3000", "--req", req],
            capture_output=True, text=True, timeout=5.0)
        return "true" in result.stdout.lower()
    except Exception:
        return False


def _gz_dynamic_poses() -> dict[str, tuple[float, float, float, float]]:
    """One-shot read of /world/default/dynamic_pose/info (gz.msgs.Pose_V).

    Returns {model_name: (x, y, z, yaw)} for every dynamic model. One call
    (~120 ms) covers robot + pallet — much faster and more reliable than
    `gz model -m <name> -p`, which requests full world state (often >1 s
    or times out while the sim is under load).
    """
    import re
    poses: dict[str, tuple[float, float, float, float]] = {}
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", "/world/default/dynamic_pose/info",
             "-n", "1"],
            capture_output=True, text=True, timeout=3.0)
        if result.returncode != 0:
            return poses
        # Protobuf text format; zero-valued fields are omitted.
        for block in re.split(r'\npose \{', result.stdout)[1:]:
            m = re.search(r'name:\s*"([^"]+)"', block)
            if not m:
                continue
            name = m.group(1)

            def _field(section: str, field: str) -> float:
                sec = re.search(section + r' \{([^}]*)\}', block)
                if not sec:
                    return 0.0
                val = re.search(field + r':\s*([+-]?[\d.eE+-]+)', sec.group(1))
                return float(val.group(1)) if val else 0.0

            x = _field("position", "x")
            y = _field("position", "y")
            z = _field("position", "z")
            qx = _field("orientation", "x")
            qy = _field("orientation", "y")
            qz = _field("orientation", "z")
            qw = _field("orientation", "w")
            poses[name] = (x, y, z, _quat_to_yaw(qx, qy, qz, qw))
    except Exception:
        pass
    return poses


def _gz_model_pose_with_z(model_name: str) -> Optional[tuple[float, float, float, float]]:
    """Query Gazebo Harmonic for a model's world pose.

    Returns (x, y, z, yaw) — z is needed for lift verification and
    carried-continuity checks. Tries the fast dynamic_pose topic first,
    then falls back to `gz model -m <name> -p` (works for static models):
        - Pose [ XYZ (m) ] [ RPY (rad) ]:
          [x y z]
          [roll pitch yaw]
    """
    import re
    pose = _gz_dynamic_poses().get(model_name)
    if pose is not None:
        return pose
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
        x, y, z = (float(v) for v in triplets[0])
        _r, _p, yaw = (float(v) for v in triplets[1])
        return (x, y, z, yaw)
    except Exception:
        return None


def _gz_model_pose(model_name: str) -> Optional[Pose2D]:
    """2-D convenience wrapper around _gz_model_pose_with_z."""
    pose = _gz_model_pose_with_z(model_name)
    if pose is None:
        return None
    return Pose2D(pose[0], pose[1], pose[3])

"""
Flat2DBackend — in-process 2D backend implementing WorldBackend.

No ROS, no Gazebo, no network. All operations resolve instantly using an
in-memory world state. Purpose: let the same agent code run offline for
parity checks, CI, and development without the full Gazebo stack.

The world model mirrors _WORLD_OBJECTS from gazebo_backend so that the
same goal_text and locate_object calls produce structurally equivalent
tool-call sequences to the Gazebo run.
"""

import math
from typing import Optional

from .world_backend import Pose2D, WorldBackend, WorldView

# Static object registry — identical layout to _WORLD_OBJECTS in gazebo_backend
_WORLD_OBJECTS: dict[str, tuple[float, float]] = {
    "pallet_jack":   (-0.28, -9.48),
    "clutter_c_027": (3.32,   3.82),
    "clutter_c_028": (5.54,   3.82),
    "clutter_c_029": (5.38,   6.14),
    "clutter_c_030": (3.24,   6.14),
    "clutter_d_005": (-1.63, -7.81),
    "dropoff_a":     (0.0,    0.0),
    "dropoff_b":     (3.45,   2.15),
}

_DROPOFF_A    = (0.0, 0.0)
_THRESHOLD_M  = 1.5
_ROBOT_SPAWN  = (3.45, 2.15)


class Flat2DBackend(WorldBackend):
    """Instant-success 2D backend — same interface as GazeboBackend, no ROS."""

    def __init__(self):
        self._robot  = Pose2D(_ROBOT_SPAWN[0], _ROBOT_SPAWN[1], 0.0)
        self._pallet = list(_WORLD_OBJECTS["pallet_jack"])   # mutable [x, y]
        self._carrying: Optional[str] = None
        # locate_log mirrors GazeboBackend.locate_log for eval runner compatibility
        self.locate_log: list[str] = []

    # ------------------------------------------------------------------ #
    def perceive(self) -> WorldView:
        objects = {k: Pose2D(v[0], v[1], 0.0) for k, v in _WORLD_OBJECTS.items()}
        # Reflect current pallet position in the world view
        objects["pallet_jack"] = Pose2D(self._pallet[0], self._pallet[1], 0.0)
        return WorldView(robot_pose=self._robot, objects=objects,
                         map_info="flat2d_aws_small_warehouse")

    def locate_object(self, name: str) -> Optional[Pose2D]:
        if name == "pallet_jack":
            self.locate_log.append("gt_registry")
            return Pose2D(self._pallet[0], self._pallet[1], 0.0)
        entry = _WORLD_OBJECTS.get(name)
        if entry:
            self.locate_log.append("gt_registry")
            return Pose2D(entry[0], entry[1], 0.0)
        self.locate_log.append("not_found")
        return None

    def check_path(self, x: float, y: float) -> bool:
        # Flat world — every position is reachable
        return True

    def move_to(self, x: float, y: float, yaw: float = 0.0) -> bool:
        self._robot = Pose2D(x, y, yaw)
        # If carrying, keep pallet attached to robot position
        if self._carrying:
            self._pallet = [x, y]
        return True

    def pick(self, object_name: str) -> bool:
        self._carrying = object_name
        # Snap pallet to robot position on pick
        self._pallet = [self._robot.x, self._robot.y]
        return True

    def drop(self, x: float, y: float) -> bool:
        self._pallet = [x, y]
        self._carrying = None
        return True

    def oracle_check(self) -> dict:
        dx   = self._pallet[0] - _DROPOFF_A[0]
        dy   = self._pallet[1] - _DROPOFF_A[1]
        dist = math.sqrt(dx * dx + dy * dy)
        return {
            "backend":               "flat2d",
            "robot_pose":            str(self._robot),
            "pallet_pos":            f"({self._pallet[0]:.2f}, {self._pallet[1]:.2f})",
            "pallet_to_dropoff_a_m": round(dist, 3),
            "carrying":              self._carrying,
            "task_complete":         dist < _THRESHOLD_M,
        }

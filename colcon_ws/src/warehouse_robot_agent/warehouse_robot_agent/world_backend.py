"""Abstract WorldBackend interface shared by all backends (2D, Gazebo, real robot)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Pose2D:
    x: float
    y: float
    yaw: float   # radians

    def __str__(self):
        return f"({self.x:.2f}, {self.y:.2f}, yaw={self.yaw:.2f})"


@dataclass
class WorldView:
    robot_pose: Pose2D
    objects: dict = field(default_factory=dict)   # name -> Pose2D
    map_info: Optional[str] = None


class WorldBackend(ABC):

    @abstractmethod
    def perceive(self) -> WorldView:
        """Read current robot pose and visible world state."""

    @abstractmethod
    def locate_object(self, name: str) -> Optional[Pose2D]:
        """Return ground-truth or detected pose of a named object. None if not found."""

    @abstractmethod
    def check_path(self, x: float, y: float) -> bool:
        """Return True if a collision-free path to (x, y) can be computed."""

    @abstractmethod
    def move_to(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """Navigate to pose (x, y, yaw). Blocks until done. Returns True on success."""

    @abstractmethod
    def pick(self, object_name: str) -> bool:
        """Attempt to pick up named object. Returns True on success."""

    @abstractmethod
    def drop(self, x: float, y: float) -> bool:
        """Drop held object at (x, y). Returns True on success."""

    @abstractmethod
    def oracle_check(self) -> dict:
        """Independent ground-truth evaluation of task completion."""

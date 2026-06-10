"""
Contract tests for WorldBackend.

These tests define the behavioural contract that EVERY WorldBackend
implementation must satisfy. They run in two tiers:

  Tier 1 — always runs (no ROS, no Gazebo needed):
      Flat2DBackend implements the contract in pure Python.
      These tests run on every CI push.

  Tier 2 — skipped when rclpy is unavailable:
      GazeboBackend wraps ROS 2 Nav2. Requires a live Gazebo stack.
      Tests are collected but skipped on CI runners without rclpy.

Adding a new WorldBackend?  Subclass BackendContractMixin, set
`self.backend` in setup_method, and the full contract runs automatically.
"""

import json
import math
import pytest

from warehouse_robot_agent.world_backend import Pose2D, WorldBackend, WorldView
from warehouse_robot_agent.flat2d_backend import Flat2DBackend

# ── optional ROS import ───────────────────────────────────────────────────── #
try:
    import rclpy                                          # noqa: F401
    from warehouse_robot_agent.gazebo_backend import (
        GazeboBackend, GazeboBackendNode, _gz_model_pose,
    )
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False

needs_ros = pytest.mark.skipif(
    not ROS_AVAILABLE,
    reason="rclpy not installed — skipping Gazebo backend tests",
)


# ══════════════════════════════════════════════════════════════════════════════
# Contract mixin — subclass + set self.backend to get all checks for free
# ══════════════════════════════════════════════════════════════════════════════

class BackendContractMixin:
    """Shared contract: every WorldBackend must pass all methods here."""

    # ── interface completeness ─────────────────────────────────────────── #

    def test_is_world_backend_subclass(self):
        assert isinstance(self.backend, WorldBackend)

    def test_has_locate_log(self):
        assert hasattr(self.backend, "locate_log")
        assert isinstance(self.backend.locate_log, list)

    # ── perceive ──────────────────────────────────────────────────────── #

    def test_perceive_returns_world_view(self):
        view = self.backend.perceive()
        assert isinstance(view, WorldView)

    def test_perceive_robot_pose_is_pose2d(self):
        view = self.backend.perceive()
        assert isinstance(view.robot_pose, Pose2D)

    def test_perceive_objects_are_pose2d(self):
        view = self.backend.perceive()
        for name, pose in view.objects.items():
            assert isinstance(pose, Pose2D), f"objects[{name!r}] is not Pose2D"

    def test_perceive_has_map_info(self):
        view = self.backend.perceive()
        assert view.map_info is not None and isinstance(view.map_info, str)

    # ── locate_object ─────────────────────────────────────────────────── #

    def test_locate_known_object_returns_pose2d(self):
        pose = self.backend.locate_object("pallet_jack")
        assert pose is not None, "pallet_jack is a known object; must not return None"
        assert isinstance(pose, Pose2D)

    def test_locate_known_object_has_finite_coords(self):
        pose = self.backend.locate_object("pallet_jack")
        assert math.isfinite(pose.x) and math.isfinite(pose.y)

    def test_locate_unknown_object_returns_none(self):
        pose = self.backend.locate_object("nonexistent_object_xyz_abc")
        assert pose is None

    def test_locate_object_appends_to_locate_log(self):
        self.backend.locate_log.clear()
        self.backend.locate_object("pallet_jack")
        assert len(self.backend.locate_log) >= 1, "locate_object must append a source entry"

    def test_locate_log_entries_are_strings(self):
        self.backend.locate_log.clear()
        self.backend.locate_object("pallet_jack")
        for entry in self.backend.locate_log:
            assert isinstance(entry, str), f"locate_log entry is not str: {entry!r}"

    # ── check_path ────────────────────────────────────────────────────── #

    def test_check_path_returns_bool(self):
        result = self.backend.check_path(0.0, 0.0)
        assert isinstance(result, bool)

    def test_check_path_for_valid_dropoff(self):
        # dropoff_a (0, 0) must be reachable in a functioning backend
        result = self.backend.check_path(0.0, 0.0)
        assert result is True

    # ── move_to ───────────────────────────────────────────────────────── #

    def test_move_to_returns_bool(self):
        result = self.backend.move_to(0.0, 0.0)
        assert isinstance(result, bool)

    def test_move_to_with_yaw_returns_bool(self):
        result = self.backend.move_to(1.0, 1.0, yaw=1.57)
        assert isinstance(result, bool)

    # ── pick ──────────────────────────────────────────────────────────── #

    def test_pick_returns_bool(self):
        result = self.backend.pick("pallet_jack")
        assert isinstance(result, bool)

    # ── drop ──────────────────────────────────────────────────────────── #

    def test_drop_returns_bool(self):
        result = self.backend.drop(0.0, 0.0)
        assert isinstance(result, bool)

    # ── oracle_check ──────────────────────────────────────────────────── #

    def test_oracle_check_returns_dict(self):
        result = self.backend.oracle_check()
        assert isinstance(result, dict)

    def test_oracle_check_has_task_complete_bool(self):
        result = self.backend.oracle_check()
        assert "task_complete" in result, "oracle_check must include 'task_complete'"
        assert isinstance(result["task_complete"], bool)

    def test_oracle_check_has_backend_label(self):
        result = self.backend.oracle_check()
        assert "backend" in result, "oracle_check must identify which backend it is"


# ══════════════════════════════════════════════════════════════════════════════
# Tier 1 — Flat2DBackend (always runs)
# ══════════════════════════════════════════════════════════════════════════════

class TestFlat2DBackendContract(BackendContractMixin):

    def setup_method(self):
        self.backend = Flat2DBackend()

    # ── Flat2D-specific behavioural checks ────────────────────────────── #

    def test_robot_spawns_at_expected_position(self):
        view = self.backend.perceive()
        assert pytest.approx(view.robot_pose.x, abs=0.01) == 3.45
        assert pytest.approx(view.robot_pose.y, abs=0.01) == 2.15

    def test_pallet_jack_at_expected_position(self):
        pose = self.backend.locate_object("pallet_jack")
        assert pytest.approx(pose.x, abs=0.01) == -0.28
        assert pytest.approx(pose.y, abs=0.01) == -9.48

    def test_locate_log_source_is_gt_registry(self):
        self.backend.locate_log.clear()
        self.backend.locate_object("pallet_jack")
        assert self.backend.locate_log[0] == "gt_registry"

    def test_locate_log_source_is_not_found_for_unknown(self):
        self.backend.locate_log.clear()
        self.backend.locate_object("nonexistent_object_xyz_abc")
        assert self.backend.locate_log[0] == "not_found"

    def test_move_to_updates_robot_pose(self):
        self.backend.move_to(1.5, 2.5, yaw=0.3)
        view = self.backend.perceive()
        assert pytest.approx(view.robot_pose.x, abs=0.001) == 1.5
        assert pytest.approx(view.robot_pose.y, abs=0.001) == 2.5

    def test_pick_sets_carrying_state(self):
        self.backend.move_to(-0.28, -9.48)
        ok = self.backend.pick("pallet_jack")
        assert ok is True
        result = self.backend.oracle_check()
        assert result["carrying"] == "pallet_jack"

    def test_drop_clears_carrying_state(self):
        self.backend.pick("pallet_jack")
        self.backend.drop(0.0, 0.0)
        result = self.backend.oracle_check()
        assert result["carrying"] is None

    def test_full_task_results_in_oracle_pass(self):
        """End-to-end: perceive → locate → move → pick → move → drop → oracle PASS."""
        view = self.backend.perceive()
        assert view is not None

        pallet = self.backend.locate_object("pallet_jack")
        assert pallet is not None

        assert self.backend.move_to(pallet.x, pallet.y) is True
        assert self.backend.pick("pallet_jack") is True
        assert self.backend.move_to(0.0, 0.0) is True
        assert self.backend.drop(0.0, 0.0) is True

        result = self.backend.oracle_check()
        assert result["task_complete"] is True
        assert result["pallet_to_dropoff_a_m"] < 1.5

    def test_locate_log_clears_between_tasks(self):
        """Eval runner relies on clearing locate_log between tasks."""
        self.backend.locate_object("pallet_jack")
        assert len(self.backend.locate_log) == 1
        self.backend.locate_log.clear()
        assert len(self.backend.locate_log) == 0
        self.backend.locate_object("pallet_jack")
        assert len(self.backend.locate_log) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Tier 1 — llm_agent.dispatch() with Flat2DBackend (no ROS, no LLM call)
# ══════════════════════════════════════════════════════════════════════════════

class TestDispatchWithFlat2DBackend:
    """Verify dispatch() produces valid JSON for every tool against Flat2DBackend."""

    def setup_method(self):
        self.backend = Flat2DBackend()
        from warehouse_robot_agent.llm_agent import dispatch
        self.dispatch = dispatch

    def _call(self, name, inp=None):
        raw = self.dispatch(self.backend, name, inp or {})
        return json.loads(raw)

    def test_perceive(self):
        out = self._call("perceive")
        assert "robot_pose" in out
        assert "objects" in out

    def test_locate_object_known(self):
        out = self._call("locate_object", {"name": "pallet_jack"})
        assert out is not None
        assert "x" in out and "y" in out

    def test_locate_object_unknown(self):
        out = self._call("locate_object", {"name": "nonexistent_xyz"})
        assert out is None

    def test_check_path(self):
        out = self._call("check_path", {"x": 0.0, "y": 0.0})
        assert "reachable" in out
        assert isinstance(out["reachable"], bool)

    def test_move_to(self):
        out = self._call("move_to", {"x": 0.0, "y": 0.0})
        assert out["success"] is True

    def test_pick(self):
        out = self._call("pick", {"object_name": "pallet_jack"})
        assert out["success"] is True

    def test_drop(self):
        out = self._call("drop", {"x": 0.0, "y": 0.0})
        assert out["success"] is True

    def test_oracle_check(self):
        out = self._call("oracle_check")
        assert "task_complete" in out

    def test_done(self):
        out = self._call("done", {"summary": "Task complete"})
        assert out["acknowledged"] is True

    def test_unknown_tool_returns_error(self):
        out = self._call("nonexistent_tool_xyz")
        assert "error" in out

    def test_dispatch_result_is_always_valid_json(self):
        """No tool call should raise or return un-parseable output."""
        calls = [
            ("perceive",      {}),
            ("locate_object", {"name": "pallet_jack"}),
            ("check_path",    {"x": 1.0, "y": 1.0}),
            ("move_to",       {"x": 1.0, "y": 1.0}),
            ("pick",          {"object_name": "pallet_jack"}),
            ("drop",          {"x": 0.0, "y": 0.0}),
            ("oracle_check",  {}),
            ("done",          {"summary": "ok"}),
        ]
        for name, inp in calls:
            raw = self.dispatch(self.backend, name, inp)
            json.loads(raw)   # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — GazeboBackend (skipped if rclpy unavailable)
# ══════════════════════════════════════════════════════════════════════════════

@needs_ros
class TestGazeboBackendImports:
    """Smoke: GazeboBackend and helpers import correctly when rclpy is present."""

    def test_gazebo_backend_class_exists(self):
        assert GazeboBackend is not None

    def test_gazebo_backend_node_class_exists(self):
        assert GazeboBackendNode is not None

    def test_gz_model_pose_callable(self):
        assert callable(_gz_model_pose)

    def test_gz_model_pose_returns_none_without_gz(self):
        # gz CLI not running in CI even when rclpy is available
        result = _gz_model_pose("nonexistent_model_xyz")
        assert result is None

    def test_gazebo_backend_is_world_backend_subclass(self):
        assert issubclass(GazeboBackend, WorldBackend)

    def test_gazebo_backend_node_is_ros_node(self):
        from rclpy.node import Node
        assert issubclass(GazeboBackendNode, Node)

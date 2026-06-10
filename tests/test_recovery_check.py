"""
Tests for eval/recovery_check.py — offline portions only.

No ROS, no Gazebo, no live processes. Tests cover:
  - Layer definitions are complete and consistent
  - RestartResult serialises correctly
  - _write_report produces valid output
  - _load_times / _save_times round-trip
  - Health check returns the right schema
  - _check_port returns bool (port almost certainly closed in CI)
"""

import json
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).parent.parent / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import recovery_check as rc
from recovery_check import (
    LAYERS, LAYER_MAP, RestartResult,
    _check_port, _write_report, _load_times, _save_times,
    check_health,
)


# ── Layer definitions ──────────────────────────────────────────────────────── #

class TestLayerDefinitions:

    def test_all_required_layers_present(self):
        ids = {l.id for l in LAYERS}
        assert {"foxglove", "nav2", "gazebo", "full"} == ids

    def test_layer_map_matches_layers(self):
        for layer in LAYERS:
            assert layer.id in LAYER_MAP
            assert LAYER_MAP[layer.id] is layer

    def test_each_layer_has_kill_cmds(self):
        for layer in LAYERS:
            assert len(layer.kill_cmds) >= 1, f"{layer.id} has no kill_cmds"

    def test_each_layer_has_start_cmd(self):
        for layer in LAYERS:
            assert layer.start_cmd, f"{layer.id} has empty start_cmd"

    def test_each_layer_has_ready_fn(self):
        for layer in LAYERS:
            assert callable(layer.ready_fn), f"{layer.id}.ready_fn is not callable"

    def test_each_layer_has_timeout_positive(self):
        for layer in LAYERS:
            assert layer.timeout > 0

    def test_expected_times_cover_all_layers(self):
        for layer in LAYERS:
            assert layer.id in rc._EXPECTED_S, f"No expected time for {layer.id}"

    def test_layers_ordered_lightest_to_heaviest(self):
        """foxglove < nav2 < gazebo < full (by expected restart time)."""
        ids = [l.id for l in LAYERS]
        assert ids.index("foxglove") < ids.index("nav2")
        assert ids.index("nav2")    < ids.index("gazebo")
        assert ids.index("gazebo")  < ids.index("full")


# ── RestartResult ─────────────────────────────────────────────────────────── #

class TestRestartResult:

    def test_success_result(self):
        r = RestartResult("foxglove", elapsed_s=7.3, success=True)
        d = r.to_dict()
        assert d["layer_id"]  == "foxglove"
        assert d["elapsed_s"] == 7.3
        assert d["success"]   is True
        assert d["error"]     == ""

    def test_failed_result(self):
        r = RestartResult("nav2", elapsed_s=None, success=False, error="timeout 60s")
        d = r.to_dict()
        assert d["success"] is False
        assert "timeout" in d["error"]

    def test_dry_run_result(self):
        r = RestartResult("gazebo", elapsed_s=None, success=None)
        d = r.to_dict()
        assert d["success"] is None
        assert d["elapsed_s"] is None


# ── _check_port ───────────────────────────────────────────────────────────── #

class TestCheckPort:

    def test_returns_bool(self):
        # Port 1 is almost certainly closed; result must still be bool
        result = _check_port(1)
        assert isinstance(result, bool)

    def test_closed_port_returns_false(self):
        # Port 19999 is very unlikely to be open
        assert _check_port(19999) is False


# ── _load_times / _save_times ─────────────────────────────────────────────── #

class TestTimesIO:

    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "TIMES_JSON", tmp_path / "recovery_times.json")
        assert _load_times() == {}

    def test_save_then_load_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "TIMES_JSON",  tmp_path / "recovery_times.json")
        monkeypatch.setattr(rc, "RESULTS_DIR", tmp_path)

        results = [RestartResult("foxglove", elapsed_s=6.2, success=True)]
        _save_times(results, "2026-06-10T00:00:00+00:00")

        loaded = _load_times()
        assert "foxglove" in loaded
        assert loaded["foxglove"]["elapsed_s"] == 6.2

    def test_save_ignores_failed_results(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "TIMES_JSON",  tmp_path / "recovery_times.json")
        monkeypatch.setattr(rc, "RESULTS_DIR", tmp_path)

        results = [RestartResult("nav2", elapsed_s=None, success=False, error="timeout")]
        _save_times(results, "2026-06-10T00:00:00+00:00")

        loaded = _load_times()
        assert "nav2" not in loaded

    def test_save_updates_existing_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "TIMES_JSON",  tmp_path / "recovery_times.json")
        monkeypatch.setattr(rc, "RESULTS_DIR", tmp_path)

        _save_times([RestartResult("foxglove", 8.0, True)], "2026-06-10T00:00:00+00:00")
        _save_times([RestartResult("foxglove", 6.5, True)], "2026-06-10T01:00:00+00:00")

        loaded = _load_times()
        assert loaded["foxglove"]["elapsed_s"] == 6.5


# ── check_health ─────────────────────────────────────────────────────────── #

class TestCheckHealth:
    """Tests use monkeypatch to avoid slow DDS discovery subprocess calls."""

    @pytest.fixture(autouse=True)
    def _mock_checks(self, monkeypatch):
        # Return False instantly — same result as the real call when stack is down,
        # but without waiting for DDS discovery timeout (~3 s per call).
        monkeypatch.setattr(rc, "_check_port",       lambda port: False)
        monkeypatch.setattr(rc, "_check_ros_node",   lambda pattern: False)
        monkeypatch.setattr(rc, "_check_ros_action", lambda pattern: False)
        monkeypatch.setattr(rc, "_check_gz_model",   lambda pattern: False)

    def test_returns_one_row_per_layer(self):
        rows = check_health()
        assert len(rows) == len(LAYERS)

    def test_each_row_has_required_keys(self):
        rows = check_health()
        for row in rows:
            assert "id"      in row
            assert "name"    in row
            assert "healthy" in row
            assert "check"   in row

    def test_healthy_is_bool(self):
        rows = check_health()
        for row in rows:
            assert isinstance(row["healthy"], bool)

    def test_all_dead_when_all_checks_false(self):
        rows = check_health()
        for row in rows:
            assert row["healthy"] is False

    def test_all_alive_when_all_checks_true(self, monkeypatch):
        monkeypatch.setattr(rc, "_check_port",       lambda port: True)
        monkeypatch.setattr(rc, "_check_ros_action", lambda pattern: True)
        monkeypatch.setattr(rc, "_check_gz_model",   lambda pattern: True)
        rows = check_health()
        for row in rows:
            assert row["healthy"] is True


# ── _write_report ─────────────────────────────────────────────────────────── #

class TestWriteReport:

    def _patch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(rc, "TIMES_JSON",  tmp_path / "recovery_times.json")
        monkeypatch.setattr(rc, "REPORT_MD",   tmp_path / "recovery_times.md")

    def test_creates_report_file(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        _write_report(None, [], "2026-06-10T00:00:00+00:00", dry_run=True)
        assert (tmp_path / "recovery_times.md").exists()

    def test_report_contains_all_layers(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        _write_report(None, [], "2026-06-10T00:00:00+00:00", dry_run=True)
        content = (tmp_path / "recovery_times.md").read_text()
        for layer in LAYERS:
            assert layer.name in content

    def test_report_contains_decision_tree(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        _write_report(None, [], "2026-06-10T00:00:00+00:00", dry_run=True)
        content = (tmp_path / "recovery_times.md").read_text()
        assert "Recovery decision tree" in content
        assert "foxglove viz frozen" in content

    def test_report_contains_quick_reference(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        _write_report(None, [], "2026-06-10T00:00:00+00:00", dry_run=True)
        content = (tmp_path / "recovery_times.md").read_text()
        assert "Quick-reference" in content
        assert "pkill" in content

    def test_measured_times_appear_in_report(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        # Pre-seed a measured time
        (tmp_path / "recovery_times.json").write_text(json.dumps({
            "measured": {"foxglove": {"elapsed_s": 6.2, "measured_at": "2026-06-10T00:00:00+00:00"}},
            "updated": "2026-06-10T00:00:00+00:00",
        }))
        _write_report(None, [], "2026-06-10T00:00:00+00:00", dry_run=False)
        content = (tmp_path / "recovery_times.md").read_text()
        assert "6.2 s" in content

    def test_health_section_appears_when_provided(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        health = [{"id": "foxglove", "name": "foxglove_bridge (L1)",
                   "healthy": False, "check": "nc -z localhost 8765"}]
        _write_report(health, [], "2026-06-10T00:00:00+00:00", dry_run=False)
        content = (tmp_path / "recovery_times.md").read_text()
        assert "Health check" in content

    def test_results_section_appears_when_provided(self, tmp_path, monkeypatch):
        self._patch(tmp_path, monkeypatch)
        results = [RestartResult("foxglove", elapsed_s=7.1, success=True)]
        _write_report(None, results, "2026-06-10T00:00:00+00:00", dry_run=False)
        content = (tmp_path / "recovery_times.md").read_text()
        assert "Measured restart times" in content
        assert "7.1" in content

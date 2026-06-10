"""
Tests for the demo durability harness (eval/demo_durability.py).

These run without ROS or an LLM API key — the harness uses Flat2DBackend
and the simulated task path (_simulate_task) in dry-run mode.
"""

import json
import sys
from pathlib import Path

import pytest

# Allow import without colcon install (conftest.py adds the package path)
_EVAL_DIR = Path(__file__).parent.parent / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from demo_durability import (
    DEMO_GOAL,
    FailureCode,
    REMEDIATION,
    _run_attempt_dry,
    _simulate_task,
    _streak,
    _write_report,
    classify_failure,
)
from warehouse_robot_agent.flat2d_backend import Flat2DBackend


# ── _simulate_task ─────────────────────────────────────────────────────────── #

class TestSimulateTask:

    def test_simulate_completes_all_steps(self):
        backend = Flat2DBackend()
        result  = _simulate_task(backend)
        assert result["done_called"] is True

    def test_simulate_steps_reasonable(self):
        backend = Flat2DBackend()
        result  = _simulate_task(backend)
        # Canonical sequence is 10 steps; allow a few extra
        assert 8 <= result["steps"] <= 15

    def test_simulate_trace_contains_required_tools(self):
        backend = Flat2DBackend()
        result  = _simulate_task(backend)
        tools_called = [e["tool"] for e in result["trace"]]
        for required in ("perceive", "locate_object", "move_to", "pick",
                         "drop", "oracle_check", "done"):
            assert required in tools_called, f"'{required}' missing from trace"

    def test_simulate_oracle_passes(self):
        backend = Flat2DBackend()
        _simulate_task(backend)
        oracle = backend.oracle_check()
        assert oracle["task_complete"] is True

    def test_simulate_pallet_at_dropoff_after_task(self):
        backend = Flat2DBackend()
        _simulate_task(backend)
        oracle = backend.oracle_check()
        assert oracle["pallet_to_dropoff_a_m"] < 1.5


# ── _run_attempt_dry ──────────────────────────────────────────────────────── #

class TestRunAttemptDry:

    def test_returns_success(self):
        row = _run_attempt_dry(1)
        assert row["success"] is True

    def test_attempt_number_is_set(self):
        row = _run_attempt_dry(3)
        assert row["attempt"] == 3

    def test_steps_in_range(self):
        row = _run_attempt_dry(1)
        assert isinstance(row["steps"], int)
        assert row["steps"] > 0

    def test_elapsed_is_float(self):
        row = _run_attempt_dry(1)
        assert isinstance(row["elapsed_s"], float)

    def test_oracle_has_dist(self):
        row = _run_attempt_dry(1)
        assert "dist_to_dropoff_a_m" in row["oracle"]
        assert row["oracle"]["dist_to_dropoff_a_m"] < 1.5

    def test_no_failure_code_on_success(self):
        row = _run_attempt_dry(1)
        assert "failure_code" not in row

    def test_each_attempt_is_independent(self):
        """Verify fresh state each time (pallet starts at spawn every attempt)."""
        row1 = _run_attempt_dry(1)
        row2 = _run_attempt_dry(2)
        assert row1["success"] is True
        assert row2["success"] is True


# ── failure classification ────────────────────────────────────────────────── #

class TestClassifyFailure:

    def _row(self, **overrides):
        base = {
            "steps":   5,
            "metrics": {"done_called": True},
            "oracle":  {"pallet_gt": "(-8.0, -8.0, yaw=0.00)",
                        "dist_to_dropoff_a_m": 11.3,
                        "success": False},
        }
        base.update(overrides)
        return base

    def test_gz_unavailable(self):
        row = self._row(oracle={"pallet_gt": "gz_cli_unavailable",
                                 "dist_to_dropoff_a_m": None, "success": False})
        assert classify_failure(row) == FailureCode.GZ_UNAVAILABLE

    def test_max_steps(self):
        row = self._row(steps=30,
                        oracle={"pallet_gt": "(-0.28, -9.48, yaw=0.00)",
                                 "dist_to_dropoff_a_m": 9.5, "success": False})
        assert classify_failure(row) == FailureCode.MAX_STEPS

    def test_no_done_call(self):
        row = self._row(metrics={"done_called": False})
        assert classify_failure(row) == FailureCode.NO_DONE

    def test_pallet_near_spawn_is_pick_failure(self):
        row = self._row(oracle={"pallet_gt": "(-0.28, -9.48, yaw=0.00)",
                                 "dist_to_dropoff_a_m": 9.5, "success": False},
                        metrics={"done_called": True})
        assert classify_failure(row) == FailureCode.PICK_FAILURE

    def test_pallet_moved_but_not_at_dropoff(self):
        row = self._row(oracle={"pallet_gt": "(-4.0, -4.0, yaw=0.00)",
                                 "dist_to_dropoff_a_m": 5.7, "success": False},
                        metrics={"done_called": True})
        assert classify_failure(row) == FailureCode.PALLET_NOT_MOVED

    def test_all_failure_codes_have_remediation(self):
        for attr, code in vars(FailureCode).items():
            if not attr.startswith("_") and isinstance(code, str):
                assert code in REMEDIATION, f"No remediation entry for {code!r}"


# ── _streak ───────────────────────────────────────────────────────────────── #

class TestStreak:

    def _row(self, success: bool) -> dict:
        return {"success": success, "steps": 1, "elapsed_s": 0.1,
                "oracle": {"dist_to_dropoff_a_m": 0.0},
                "metrics": {"done_called": True}}

    def test_all_pass(self):
        rows = [self._row(True)] * 5
        assert _streak(rows) == 5

    def test_all_fail(self):
        rows = [self._row(False)] * 5
        assert _streak(rows) == 0

    def test_fail_in_middle_breaks_streak(self):
        rows = [self._row(True), self._row(True),
                self._row(False),
                self._row(True), self._row(True)]
        assert _streak(rows) == 2   # only trailing 2 count

    def test_empty(self):
        assert _streak([]) == 0


# ── report generation ─────────────────────────────────────────────────────── #

class TestWriteReport:

    def _make_rows(self, pattern: list[bool]) -> list[dict]:
        rows = []
        for i, success in enumerate(pattern, start=1):
            row: dict = {
                "attempt":   i,
                "success":   success,
                "steps":     10,
                "elapsed_s": 45.0,
                "metrics":   {"done_called": success},
                "oracle":    {
                    "pallet_gt":           "(0.0, 0.0, yaw=0.00)" if success else "(-8.0, -8.0, yaw=0.00)",
                    "dist_to_dropoff_a_m": 0.0 if success else 11.3,
                    "success":             success,
                },
            }
            if not success:
                row["failure_code"] = FailureCode.PALLET_NOT_MOVED
                row["remediation"]  = REMEDIATION[FailureCode.PALLET_NOT_MOVED]
            rows.append(row)
        return rows

    def test_report_file_created(self, tmp_path, monkeypatch):
        import demo_durability as dm
        monkeypatch.setattr(dm, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(dm, "MD_OUT",  tmp_path / "demo_durability.md")
        monkeypatch.setattr(dm, "JSON_OUT", tmp_path / "demo_durability.json")

        rows = self._make_rows([True, True, True, True, True])
        _write_report(rows, 5, "2026-06-10T00:00:00+00:00", dry_run=True)

        assert (tmp_path / "demo_durability.md").exists()
        assert (tmp_path / "demo_durability.json").exists()

    def test_json_output_schema(self, tmp_path, monkeypatch):
        import demo_durability as dm
        monkeypatch.setattr(dm, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(dm, "MD_OUT",  tmp_path / "demo_durability.md")
        monkeypatch.setattr(dm, "JSON_OUT", tmp_path / "demo_durability.json")

        rows = self._make_rows([True, False, True, True, True])
        _write_report(rows, 5, "2026-06-10T00:00:00+00:00", dry_run=True)

        data = json.loads((tmp_path / "demo_durability.json").read_text())
        assert "run_ts" in data
        assert "results" in data
        assert len(data["results"]) == 5

    def test_report_contains_verdict_fail(self, tmp_path, monkeypatch):
        import demo_durability as dm
        monkeypatch.setattr(dm, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(dm, "MD_OUT",  tmp_path / "demo_durability.md")
        monkeypatch.setattr(dm, "JSON_OUT", tmp_path / "demo_durability.json")

        rows = self._make_rows([True, False, True, True, True])
        _write_report(rows, 5, "2026-06-10T00:00:00+00:00", dry_run=True)

        content = (tmp_path / "demo_durability.md").read_text()
        assert "STREAK" in content
        assert "pallet_not_moved" in content
        assert "Remediation" in content

    def test_report_contains_verdict_pass(self, tmp_path, monkeypatch):
        import demo_durability as dm
        monkeypatch.setattr(dm, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(dm, "MD_OUT",  tmp_path / "demo_durability.md")
        monkeypatch.setattr(dm, "JSON_OUT", tmp_path / "demo_durability.json")

        rows = self._make_rows([True, True, True, True, True])
        _write_report(rows, 5, "2026-06-10T00:00:00+00:00", dry_run=True)

        content = (tmp_path / "demo_durability.md").read_text()
        assert "✅" in content
        assert "No failures recorded" in content

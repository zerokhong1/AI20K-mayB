#!/usr/bin/env python3
"""
Pose accuracy test — ARMBenchDetector._to_map_pose vs ground-truth.

Tests the 3-tier fallback (TF2 stamp / TF2 latest / manual) against known
ground-truth positions. Pass criterion: |detected - GT| ≤ 0.1 m.

Runs entirely offline (no ROS, no Gazebo) using mock TF transforms.

Usage:
  python3 eval/test_pose_accuracy.py
  python3 eval/test_pose_accuracy.py --verbose
"""

import argparse
import math
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
SRC_PKG   = REPO_ROOT / "colcon_ws/src/warehouse_robot_agent"
sys.path.insert(0, str(SRC_PKG))

try:
    from warehouse_robot_agent.perception_node import ARMBenchDetector
    from warehouse_robot_agent.world_backend import Pose2D
except ImportError as e:
    print(f"[pose_acc] ERROR: {e}")
    sys.exit(1)

TOLERANCE_M = 0.1   # pass/fail threshold


# ─────────────────────────── mock objects ──────────────────────────────── #

class _MockCameraInfo:
    """Minimal CameraInfo with K matrix matching SDF (640×480, HFOV 1.085595)."""
    def __init__(self):
        fx = 640 / (2 * math.tan(1.085595 / 2))   # ≈ 554 px
        self.k = [fx, 0.0, 320.0,
                  0.0, fx,  240.0,
                  0.0, 0.0,   1.0]


class _MockTransform:
    """A TransformStamped-like object for a given 2D map-frame robot pose."""

    class _Vec:
        def __init__(self, x, y, z): self.x = x; self.y = y; self.z = z

    class _Transform:
        def __init__(self, t, r):
            self.translation = t
            self.rotation    = r

    def __init__(self, robot_x: float, robot_y: float, robot_yaw: float,
                 cam_mount_x: float = 0.30, cam_mount_z: float = 0.22):
        # Full transform: camera_optical_link → map
        # = map_T_base · base_T_camera_link · camera_link_T_optical
        #
        # base_T_camera_link: translate (cam_mount_x, 0, cam_mount_z)
        # camera_link_T_optical: rpy -1.5708 0 -1.5708
        #   → quaternion: x=-0.5, y=0.5, z=-0.5, w=0.5
        # map_T_base: translate (robot_x, robot_y, 0), rotate robot_yaw
        #
        # For test purposes we compute the composed translation directly.
        cos_y = math.cos(robot_yaw)
        sin_y = math.sin(robot_yaw)

        # camera_link origin in map frame
        tx = robot_x + cos_y * cam_mount_x
        ty = robot_y + sin_y * cam_mount_x
        tz = cam_mount_z  # ignored in 2D, kept for _apply_tf completeness

        # Combined rotation: camera_optical → map
        # = R(robot_yaw about z) · R(camera_optical_joint: rpy -pi/2 0 -pi/2)
        # camera_optical_joint quaternion: (x=-0.5, y=0.5, z=-0.5, w=0.5)
        # Then compose with robot_yaw rotation q_yaw = (0, 0, sin(yaw/2), cos(yaw/2))
        #
        # Precomputed composition for test correctness:
        # After composing, x_opt→map maps: z_opt→x_map (fwd), x_opt→−y_map (right→left)
        # This is exactly what the manual fallback implements, so TF and manual should agree.
        qox = -0.5; qoy = 0.5; qoz = -0.5; qow = 0.5   # optical joint
        # robot yaw
        cyh = math.cos(robot_yaw / 2); syh = math.sin(robot_yaw / 2)
        qrx = 0.0; qry = 0.0; qrz = syh; qrw = cyh
        # Hamilton product q_r * q_o
        qx = qrw*qox + qrx*qow + qry*qoz - qrz*qoy
        qy = qrw*qoy - qrx*qoz + qry*qow + qrz*qox
        qz = qrw*qoz + qrx*qoy - qry*qox + qrz*qow
        qw = qrw*qow - qrx*qox - qry*qoy - qrz*qoz

        self.transform = self._Transform(
            self._Vec(tx, ty, tz),
            self._Vec(qx, qy, qz),
        )
        self.transform.rotation.w = qw


@dataclass
class _MockTFBuffer:
    """Minimal tf_buffer mock — returns a fixed transform for any lookup."""
    transform: _MockTransform
    fail_stamp: bool = False    # if True, stamp lookup raises (tests 2a→2b fallback)
    fail_all:   bool = False    # if True, all TF lookups raise (tests 2c fallback)
    calls: list = None

    def __post_init__(self):
        self.calls = []

    def lookup_transform(self, target, source, time, timeout=None):
        label = "stamp" if (hasattr(time, 'nanoseconds') and time.nanoseconds != 0) else "latest"
        self.calls.append(label)
        if self.fail_all:
            raise RuntimeError("TF mock: all lookups disabled")
        if self.fail_stamp and label == "stamp":
            raise RuntimeError("TF mock: stamp lookup disabled")
        return self.transform


# ─────────────────────────── test cases ──────────────────────────────────── #

@dataclass
class Case:
    name:         str
    # Ground-truth pallet position in map frame
    gt_x:         float
    gt_y:         float
    # Robot pose when detection fires
    robot_x:      float
    robot_y:      float
    robot_yaw:    float
    # Use TF2 mock or force manual fallback
    tf_mode:      str    # "tf2a" | "tf2b" | "manual"
    use_camera_info: bool = True

    def depth_and_pixel(self) -> tuple[float, int, int]:
        """Back-compute depth + pixel centre from GT pose + robot pose."""
        cam_mx = 0.30   # mount X
        cam_mz = 0.22   # mount Z (unused in 2D projection)
        cos_y = math.cos(self.robot_yaw)
        sin_y = math.sin(self.robot_yaw)
        # pallet in base frame
        dx_map = self.gt_x - self.robot_x
        dy_map = self.gt_y - self.robot_y
        # rotate to base frame
        x_base =  cos_y * dx_map + sin_y * dy_map
        y_base = -sin_y * dx_map + cos_y * dy_map
        # subtract camera mount
        x_cam = x_base - cam_mx
        y_cam = y_base
        # optical frame: z=fwd=x_cam, x_opt=-y_cam
        z_opt = x_cam   # depth
        x_opt = -y_cam
        if z_opt <= 0:
            raise ValueError(f"Case {self.name}: pallet is behind camera (z_opt={z_opt:.2f})")

        fx = 640 / (2 * math.tan(1.085595 / 2))
        cx = 320.0; cy = 240.0
        cx_px = int(x_opt * fx / z_opt + cx)
        cy_px = int(0.0  * fx / z_opt + cy)    # assume pallet centred vertically
        return z_opt, cx_px, cy_px


CASES: list[Case] = [
    Case("tf2a_straight",
         gt_x=-0.28, gt_y=-9.48,
         robot_x=-0.28, robot_y=-11.48, robot_yaw=math.pi/2,
         tf_mode="tf2a"),
    Case("tf2a_angled",
         gt_x=2.0, gt_y=3.0,
         robot_x=0.5, robot_y=3.0, robot_yaw=0.0,
         tf_mode="tf2a"),
    Case("tf2b_stamp_fails",
         gt_x=-0.28, gt_y=-9.48,
         robot_x=-0.28, robot_y=-11.48, robot_yaw=math.pi/2,
         tf_mode="tf2b"),
    Case("manual_no_tf",
         gt_x=-0.28, gt_y=-9.48,
         robot_x=-0.28, robot_y=-11.48, robot_yaw=math.pi/2,
         tf_mode="manual"),
    Case("manual_yaw_45deg",
         gt_x=2.0, gt_y=1.0,
         robot_x=0.5, robot_y=0.5, robot_yaw=math.pi/4,
         tf_mode="manual"),
    # Q3: no CameraInfo → fail-to (return None), not hardcoded fallback.
    # This case verifies the node correctly refuses to detect rather than guessing.
    Case("no_camera_info_fail_to",
         gt_x=-0.28, gt_y=-9.48,
         robot_x=-0.28, robot_y=-11.48, robot_yaw=math.pi/2,
         tf_mode="tf2a", use_camera_info=False),
]


# ─────────────────────────── runner ─────────────────────────────────────── #

class _MockStamp:
    def __init__(self, nonzero: bool):
        self.nanoseconds = 1_000_000 if nonzero else 0


def run_case(case: Case, verbose: bool) -> dict:
    depth_m, cx_px, cy_px = case.depth_and_pixel()

    camera_info = _MockCameraInfo() if case.use_camera_info else None
    robot_pose  = Pose2D(case.robot_x, case.robot_y, case.robot_yaw)

    mock_tf = _MockTransform(case.robot_x, case.robot_y, case.robot_yaw)

    if case.tf_mode == "manual":
        tf_buffer = None
        stamp     = None
    elif case.tf_mode == "tf2a":
        tf_buffer = _MockTFBuffer(mock_tf, fail_stamp=False, fail_all=False)
        stamp     = _MockStamp(nonzero=True)
    elif case.tf_mode == "tf2b":
        tf_buffer = _MockTFBuffer(mock_tf, fail_stamp=True, fail_all=False)
        stamp     = _MockStamp(nonzero=True)
    else:
        raise ValueError(f"Unknown tf_mode: {case.tf_mode}")

    class _SilentLogger:
        warnings = []
        def warn(self, m):  self.warnings.append(m)
        def error(self, m): self.warnings.append(f"ERROR: {m}")
        def debug(self, m): pass

    logger = _SilentLogger()
    detector = ARMBenchDetector(logger=logger)

    result = detector._to_map_pose(
        cx_px=cx_px, cy_px=cy_px, depth_m=depth_m,
        camera_info=camera_info,
        tf_buffer=tf_buffer,
        stamp=stamp,
        robot_pose=robot_pose,
        robot_yaw=case.robot_yaw,
    )

    # Q3 case: no_camera_info_fail_to expects None (correct failure, not wrong detection)
    if result is None:
        if not case.use_camera_info:
            passed = True
            err = "None as expected (fail-to on missing CameraInfo)"
            det_x = det_y = float("nan")
            path_label = "fail_to"
        else:
            err = "FAIL: _to_map_pose returned None unexpectedly"
            passed = False
            det_x = det_y = float("nan")
            path_label = "none"
    else:
        pose, path_label = result
        det_x, det_y = pose.x, pose.y
        dx = det_x - case.gt_x
        dy = det_y - case.gt_y
        dist = math.sqrt(dx*dx + dy*dy)
        passed = dist <= TOLERANCE_M
        err = f"dist={dist:.4f}m  (tol={TOLERANCE_M}m)" if not passed else f"dist={dist:.4f}m"

    if verbose or not passed:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {case.name}")
        print(f"         path={path_label}  GT=({case.gt_x},{case.gt_y})"
              f"  det=({det_x:.3f},{det_y:.3f})  {err}")
        if logger.warnings:
            for w in logger.warnings:
                print(f"         WARN: {w[:100]}")
    else:
        print(f"  [PASS] {case.name:<35} path={path_label}  dist={err.split('=')[1].split('m')[0]}m")

    return {"case": case.name, "passed": passed, "path": path_label, "error": err}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print(f"[pose_acc] tolerance = ±{TOLERANCE_M} m\n")
    results = []
    for case in CASES:
        r = run_case(case, args.verbose)
        results.append(r)

    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
    print(f"\n[pose_acc] ══ {passed}/{total} passed ══")

    if passed < total:
        print("[pose_acc] FAILED cases:")
        for r in results:
            if not r["passed"]:
                print(f"  • {r['case']}: {r['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

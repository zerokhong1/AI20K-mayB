#!/usr/bin/env python3
"""
Perception node — publishes warehouse object detections to /warehouse/detected_objects.

Two detector backends (select with ROS param `detector_backend`):
  gz_gt    (default) — ground-truth pose from Gazebo CLI; always works in headless sim.
  armbench           — ARMBench-trained model on /camera/depth/image_raw; requires
                       headless:=false (rendering enabled) + trained model weights.

Topic output:
  /warehouse/detected_objects  (std_msgs/String, JSON)
      {
        "pallet_jack": {"x": -0.28, "y": -9.48, "yaw": 0.0, "source": "gz_gt"},
        ...
      }
  Publishes at 2 Hz. Consumers should treat entries older than 2 s as stale.

Usage:
  ros2 run warehouse_robot_agent perception_node                     # gz_gt mode
  ros2 run warehouse_robot_agent perception_node --ros-args \\
      -p detector_backend:=armbench \\
      -p model_weights:=/path/to/weights.pt                         # ARMBench mode
"""

import json
import math
from typing import Optional

import rclpy
import rclpy.duration
import rclpy.parameter
import rclpy.time
from rclpy.node import Node
from std_msgs.msg import String

from warehouse_robot_agent.gazebo_backend import _gz_model_pose, _WORLD_OBJECTS
from warehouse_robot_agent.world_backend import Pose2D

# ── ARMBench / camera imports (optional — only loaded in armbench backend) ── #
try:
    import cv2
    import numpy as np
    from cv_bridge import CvBridge
    from sensor_msgs.msg import Image, CameraInfo
    _CAMERA_DEPS_OK = True
except ImportError:
    _CAMERA_DEPS_OK = False

# ── TF2 imports (optional — falls back to manual rotation if unavailable) ── #
try:
    from tf2_ros import Buffer, TransformListener
    _TF2_OK = True
except ImportError:
    _TF2_OK = False


# ──────────────────────────────────────────────────────────────────────────── #
# Ground-truth detector (always available, uses gz CLI)
# ──────────────────────────────────────────────────────────────────────────── #

_GZ_MODEL_NAMES: dict[str, str] = {
    "pallet_jack": "aws_robomaker_warehouse_PalletJackB_01_001",
}


def _detect_gz_gt() -> dict[str, dict]:
    """Query Gazebo ground-truth pose for all tracked objects."""
    detections: dict[str, dict] = {}
    for logical, gz_name in _GZ_MODEL_NAMES.items():
        pose = _gz_model_pose(gz_name)
        if pose is not None:
            detections[logical] = {
                "x": round(pose.x, 4),
                "y": round(pose.y, 4),
                "yaw": round(pose.yaw, 4),
                "source": "gz_gt",
            }
    for name, (x, y) in _WORLD_OBJECTS.items():
        if name not in detections:
            detections[name] = {"x": x, "y": y, "yaw": 0.0, "source": "registry"}
    return detections


# ──────────────────────────────────────────────────────────────────────────── #
# TF helper
# ──────────────────────────────────────────────────────────────────────────── #

def _apply_tf(t, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Rotate + translate a 3D point by a geometry_msgs/TransformStamped."""
    qx = t.transform.rotation.x
    qy = t.transform.rotation.y
    qz = t.transform.rotation.z
    qw = t.transform.rotation.w
    tx = 2.0 * (qy * z - qz * y)
    ty = 2.0 * (qz * x - qx * z)
    tz = 2.0 * (qx * y - qy * x)
    rx = x + qw * tx + (qy * tz - qz * ty)
    ry = y + qw * ty + (qz * tx - qx * tz)
    rz = z + qw * tz + (qx * ty - qy * tx)
    return (
        rx + t.transform.translation.x,
        ry + t.transform.translation.y,
        rz + t.transform.translation.z,
    )


# ──────────────────────────────────────────────────────────────────────────── #
# ARMBench camera detector  (skeleton — swap in real model here)
# ──────────────────────────────────────────────────────────────────────────── #

# Camera mount pose relative to base_link (from SDF camera_joint).
_CAM_MOUNT_X = 0.30   # m forward
_CAM_MOUNT_Z = 0.22   # m up (not used in 2D map projection)


class ARMBenchDetector:
    """
    Depth-image based object detector with ARMBench integration hook.

    Architecture:
      depth_img (cv2 uint16)
        → _preprocess()     — normalise, filter
        → _run_model()      ← SWAP THIS for your ARMBench-trained weights
        → _to_map_pose()    — project depth pixel → map-frame Pose2D
                              PRIMARY:  camera_optical_link → map via TF2
                                        (try msg stamp, then latest Time())
                              FALLBACK: manual rotation — optical→base remap
                                        + camera mount offset + robot_yaw

    To integrate ARMBench:
      1. Install: pip install ultralytics   (YOLOv8 fine-tuned on ARMBench pallet images)
                  OR  pip install onnxruntime  (exported ONNX weights)
      2. Replace _run_model() below with your model's forward pass.
      3. Map detected class IDs → logical object names.
      4. The rest of this class (3D projection, TF lookup) stays unchanged.

    Dataset reference:
      ARMBench — Amazon Robotic Manipulation Benchmark
      https://armbench.s3.amazonaws.com/index.html
      Objects relevant for warehouse nav: pallet, tote, carton.
    """

    # Fallback intrinsics — used only before first CameraInfo arrives.
    # Matches SDF: 640×480, HFOV 1.085595 rad.
    _FX_DEFAULT = 640 / (2 * math.tan(1.085595 / 2))   # ≈ 554 px
    _FY_DEFAULT = _FX_DEFAULT
    _CX_DEFAULT = 320.0
    _CY_DEFAULT = 240.0

    def __init__(self, model_weights: Optional[str] = None, logger=None):
        self._model = None
        self._logger = logger
        self._fallback_warned = False   # emit once-only warning on first fallback
        if model_weights:
            self._load_model(model_weights)

    def _load_model(self, path: str):
        # ── ARMBench integration point ──────────────────────────────────── #
        # Option A: YOLOv8 (ultralytics)
        #   from ultralytics import YOLO
        #   self._model = YOLO(path)
        #
        # Option B: ONNX Runtime
        #   import onnxruntime as ort
        #   self._model = ort.InferenceSession(path)
        # ─────────────────────────────────────────────────────────────────── #
        raise NotImplementedError(
            "ARMBench model weights not integrated yet. "
            "Add model loading in ARMBenchDetector._load_model()."
        )

    def _run_model(self, depth_img: "np.ndarray") -> list[dict]:
        """
        Run inference on a depth image.

        Returns: [{"class": str, "cx_px": int, "cy_px": int, "depth_m": float}, ...]

        Stub uses a heuristic depth-blob fallback until real weights are loaded.
        """
        if self._model is None:
            return self._depth_blob_fallback(depth_img)
        return []

    def _depth_blob_fallback(self, depth_img: "np.ndarray") -> list[dict]:
        if depth_img is None or depth_img.size == 0:
            return []
        depth_m = depth_img.astype("float32") / 1000.0
        mask = ((depth_m > 0.4) & (depth_m < 2.5)).astype("uint8") * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 500:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            d = depth_m[cy, cx]
            if d > 0:
                detections.append({"class": "pallet_jack", "cx_px": cx,
                                   "cy_px": cy, "depth_m": float(d)})
        return detections[:1]

    def detect(
        self,
        depth_img: "np.ndarray",
        camera_info: Optional["CameraInfo"] = None,
        tf_buffer: Optional["Buffer"] = None,
        stamp=None,
        robot_pose: Optional[Pose2D] = None,
        robot_yaw: float = 0.0,
    ) -> dict[str, dict]:
        raw = self._run_model(depth_img)
        detections: dict[str, dict] = {}
        for det in raw:
            map_pose = self._to_map_pose(
                det["cx_px"], det["cy_px"], det["depth_m"],
                camera_info=camera_info,
                tf_buffer=tf_buffer,
                stamp=stamp,
                robot_pose=robot_pose,
                robot_yaw=robot_yaw,
            )
            if map_pose is not None:
                detections[det["class"]] = {
                    "x": round(map_pose.x, 3),
                    "y": round(map_pose.y, 3),
                    "yaw": 0.0,
                    "source": "armbench_depth",
                }
        return detections

    def _to_map_pose(
        self,
        cx_px: int,
        cy_px: int,
        depth_m: float,
        camera_info: Optional["CameraInfo"],
        tf_buffer: Optional["Buffer"],
        stamp,
        robot_pose: Optional[Pose2D],
        robot_yaw: float,
    ) -> Optional[Pose2D]:
        """
        Back-project (pixel, depth) → map-frame Pose2D.

        Step 1 — unproject with CameraInfo.K intrinsics (fallback: SDF defaults).
                  Result is in camera_optical_link frame (z-fwd, x-right, y-down).

        Step 2 — transform to map:
          2a. TF2 with message stamp  → most accurate; requires use_sim_time=true.
          2b. TF2 with Time() latest  → works when stamp causes extrapolation.
          2c. Manual fallback         → optical→base remap + mount offset + yaw.
                                        One-shot warn so disclosure is accurate.
        """
        if depth_m <= 0:
            return None

        # ── Step 1: unproject ── #
        if camera_info is not None:
            fx = camera_info.k[0];  fy = camera_info.k[4]
            cx = camera_info.k[2];  cy = camera_info.k[5]
        else:
            fx, fy = self._FX_DEFAULT, self._FY_DEFAULT
            cx, cy = self._CX_DEFAULT, self._CY_DEFAULT

        # 3D point in camera_optical_link: z-forward, x-right, y-down
        x_opt = (cx_px - cx) * depth_m / fx
        y_opt = (cy_px - cy) * depth_m / fy
        z_opt = depth_m

        # ── Step 2a + 2b: TF2 (stamp first, then latest) ── #
        if tf_buffer is not None:
            for query_time in (stamp, rclpy.time.Time()):
                if query_time is None:
                    continue
                try:
                    t = tf_buffer.lookup_transform(
                        "map",
                        "camera_optical_link",
                        query_time,
                        rclpy.duration.Duration(seconds=0.05),
                    )
                    x_map, y_map, _ = _apply_tf(t, x_opt, y_opt, z_opt)
                    return Pose2D(x_map, y_map, 0.0)
                except Exception:
                    continue
            # Both TF attempts failed — fall through to manual

        # ── Step 2c: manual fallback ── #
        if not self._fallback_warned:
            if self._logger:
                self._logger.warn(
                    "perception: TF camera_optical_link→map failed on both stamp "
                    "and Time() — using manual rotation fallback. "
                    "Check use_sim_time=true and TF chain. "
                    "Disclosure: eval results on this path are approximate "
                    "(no camera mount height, yaw-only rotation)."
                )
            self._fallback_warned = True

        if robot_pose is None:
            return None

        # Remap optical → base_link, then add camera mount forward offset.
        #   camera_optical_link: z-fwd, x-right, y-down
        #   base_link (REP-103):  x-fwd, y-left, z-up
        #   camera_joint offset:  x=0.30 m fwd from base_link centre
        x_base = _CAM_MOUNT_X + z_opt   # z_opt (depth) + 0.30 m mount offset
        y_base = -x_opt                  # x_opt (right) → −y (base)

        cos_y = math.cos(robot_yaw)
        sin_y = math.sin(robot_yaw)
        x_map = robot_pose.x + cos_y * x_base - sin_y * y_base
        y_map = robot_pose.y + sin_y * x_base + cos_y * y_base
        return Pose2D(x_map, y_map, 0.0)


# ──────────────────────────────────────────────────────────────────────────── #
# Perception node
# ──────────────────────────────────────────────────────────────────────────── #

class PerceptionNode(Node):

    def __init__(self):
        # use_sim_time=True by default so TF stamps match Gazebo /clock.
        # Override with --ros-args -p use_sim_time:=false for wall-clock testing.
        super().__init__(
            "perception_node",
            parameter_overrides=[
                rclpy.parameter.Parameter(
                    "use_sim_time",
                    rclpy.parameter.Parameter.Type.BOOL,
                    True,
                )
            ],
        )

        self.declare_parameter("detector_backend", "gz_gt")
        self.declare_parameter("model_weights", "")
        self.declare_parameter("publish_hz", 2.0)

        backend = self.get_parameter("detector_backend").get_parameter_value().string_value
        weights = self.get_parameter("model_weights").get_parameter_value().string_value
        hz      = self.get_parameter("publish_hz").get_parameter_value().double_value

        self._pub = self.create_publisher(String, "/warehouse/detected_objects", 10)
        self._backend = backend
        self._armbench: Optional[ARMBenchDetector] = None
        self._bridge: Optional["CvBridge"] = None
        self._latest_depth: Optional["np.ndarray"] = None
        self._latest_depth_stamp = None
        self._latest_camera_info: Optional["CameraInfo"] = None
        self._tf_buffer: Optional["Buffer"] = None

        if backend == "armbench":
            if not _CAMERA_DEPS_OK:
                self.get_logger().error(
                    "armbench backend requires cv2 + cv_bridge. Falling back to gz_gt.")
                self._backend = "gz_gt"
            else:
                self._armbench = ARMBenchDetector(
                    weights if weights else None,
                    logger=self.get_logger(),
                )
                self._bridge = CvBridge()

                if _TF2_OK:
                    self._tf_buffer = Buffer()
                    self._tf_listener = TransformListener(self._tf_buffer, self)
                else:
                    self.get_logger().warning(
                        "tf2_ros not available — will use manual rotation fallback.")

                self.create_subscription(
                    Image, "/camera/depth/image_raw", self._depth_cb, 10)

                # Intrinsics from the depth sensor's camera_info (NOT /camera/camera_info).
                # Must match depth image resolution (640×480) for correct unprojection.
                self.create_subscription(
                    CameraInfo, "/camera/depth/image_raw/camera_info",
                    self._camera_info_cb, 1)

                self.get_logger().info(
                    "ARMBench backend active (use_sim_time=True). "
                    "Waiting for /camera/depth/image_raw …")

        self.create_timer(1.0 / hz, self._publish)
        self.get_logger().info(f"PerceptionNode started (backend={self._backend})")

    # ------------------------------------------------------------------ #
    def _depth_cb(self, msg: "Image"):
        try:
            self._latest_depth = self._bridge.imgmsg_to_cv2(
                msg, desired_encoding="passthrough")
            self._latest_depth_stamp = msg.header.stamp
        except Exception as e:
            self.get_logger().warning(f"cv_bridge error: {e}")

    def _camera_info_cb(self, msg: "CameraInfo"):
        self._latest_camera_info = msg

    def _publish(self):
        if self._backend == "armbench" and self._armbench is not None:
            detections = self._armbench.detect(
                self._latest_depth,
                camera_info=self._latest_camera_info,
                tf_buffer=self._tf_buffer,
                stamp=self._latest_depth_stamp,
            )
            gt = _detect_gz_gt()
            for k, v in gt.items():
                if k not in detections:
                    detections[k] = v
        else:
            detections = _detect_gz_gt()

        msg = String()
        msg.data = json.dumps(detections)
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

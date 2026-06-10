"""pytest configuration — add the ROS package to sys.path so tests run
without a colcon install or sourced workspace."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent /
                        "colcon_ws/src/warehouse_robot_agent"))

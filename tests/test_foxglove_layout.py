"""
Validates foxglove/warehouse_demo.json is well-formed and has the three
required panels: 3D map, depth camera, raw-message detections.

No ROS, no Gazebo — pure JSON parsing.
"""

import json
from pathlib import Path

LAYOUT_PATH = Path(__file__).parent.parent / "foxglove" / "warehouse_demo.json"


def _load():
    return json.loads(LAYOUT_PATH.read_text())


class TestLayoutStructure:

    def test_file_exists(self):
        assert LAYOUT_PATH.exists()

    def test_valid_json(self):
        _load()  # raises if invalid

    def test_has_configById(self):
        d = _load()
        assert "configById" in d, "missing 'configById'"

    def test_has_layout_key(self):
        d = _load()
        assert "layout" in d

    def test_layout_is_row_split(self):
        d = _load()
        assert d["layout"]["direction"] == "row"

    def test_three_panels_defined(self):
        d = _load()
        ids = list(d["configById"].keys())
        assert len(ids) == 3, f"expected 3 panels, got {ids}"

    def test_has_3d_panel(self):
        d = _load()
        three_d = [k for k in d["configById"] if k.startswith("3d!")]
        assert three_d, "no 3D panel found"

    def test_has_image_panel(self):
        d = _load()
        imgs = [k for k in d["configById"] if k.startswith("Image!")]
        assert imgs, "no Image panel found"

    def test_has_rawmessages_panel(self):
        d = _load()
        raw = [k for k in d["configById"] if k.startswith("RawMessages!")]
        assert raw, "no RawMessages panel found"


class TestPanelConfig:

    def _3d(self):
        d = _load()
        key = next(k for k in d["configById"] if k.startswith("3d!"))
        return d["configById"][key]

    def _image(self):
        d = _load()
        key = next(k for k in d["configById"] if k.startswith("Image!"))
        return d["configById"][key]

    def _raw(self):
        d = _load()
        key = next(k for k in d["configById"] if k.startswith("RawMessages!"))
        return d["configById"][key]

    def test_3d_panel_follows_robot(self):
        cfg = self._3d()
        assert "followTf" in cfg
        assert cfg["followTf"] == "base_footprint"

    def test_3d_panel_shows_nav2_path(self):
        cfg = self._3d()
        assert "/plan" in cfg.get("topics", {}), "Nav2 /plan topic not in 3D panel"
        assert cfg["topics"]["/plan"]["visible"] is True

    def test_3d_panel_shows_map(self):
        cfg = self._3d()
        assert "/map" in cfg.get("topics", {}), "/map topic not in 3D panel"

    def test_3d_panel_shows_scan(self):
        cfg = self._3d()
        assert "/scan" in cfg.get("topics", {}), "/scan topic not in 3D panel"

    def test_image_panel_uses_depth_topic(self):
        cfg = self._image()
        assert cfg.get("cameraTopic") == "/camera/depth/image_raw"

    def test_rawmessages_uses_detection_topic(self):
        cfg = self._raw()
        assert cfg.get("topicPath") == "/warehouse/detected_objects"

    def test_split_percentage_reasonable(self):
        d = _load()
        pct = d["layout"].get("splitPercentage", 50)
        assert 30 <= pct <= 80, f"splitPercentage {pct} looks wrong"

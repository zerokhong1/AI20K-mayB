# Disclosure — ARMBench Detector

> Tài liệu này mô tả trung thực trạng thái triển khai của ARMBench detector
> trong dự án AI20K. Không có số liệu nào được trình bày khi chưa được đo thực.

---

## 1. ARMBench là gì?

**ARMBench** (Amazon Robotic Manipulation Benchmark) là bộ dữ liệu công khai của Amazon Science:
- 235 000+ ảnh pick-and-place trong kho thực
- 190 000+ vật thể (pallet, tote, carton, v.v.)
- Dùng để fine-tune detector nhận diện vật thể kho hàng từ ảnh depth/RGB

Trong dự án này, tên "ARMBench" dùng để chỉ **hook tích hợp** — điểm code đã chuẩn sẵn để gắn model được fine-tune từ bộ dữ liệu đó. Xem `perception_node.py:ARMBenchDetector`.

---

## 2. Trạng thái triển khai

### Đã làm

| Thành phần | Trạng thái |
|------------|-----------|
| `ARMBenchDetector` class (skeleton) | ✅ Có — `perception_node.py:89` |
| Pipeline depth → Pose2D (`_to_map_pose`) | ✅ Có — camera intrinsics + TF projection |
| `_depth_blob_fallback()` | ✅ Có — OpenCV depth thresholding, phát hiện vật gần |
| `PerceptionNode` + topic `/warehouse/detected_objects` | ✅ Có — publish 2 Hz |
| `locate_log` ghi nguồn định vị mỗi task | ✅ Có — `gazebo_backend.py:155` |
| Tích hợp vào `GazeboBackend.locate_object()` | ✅ Có |

### Chưa làm

| Thành phần | Trạng thái |
|------------|-----------|
| Model weights (YOLOv8 / ONNX) | ❌ Chưa có |
| Fine-tune trên ARMBench dataset | ❌ Chưa làm |
| `_load_model()` | ❌ `NotImplementedError` — xem code bên dưới |
| Đo accuracy (mAP, recall) của detector | ❌ Chưa đo |

```python
# perception_node.py:122
def _load_model(self, path: str):
    # Tích hợp ARMBench tại đây (chưa làm):
    # Option A: from ultralytics import YOLO; self._model = YOLO(path)
    # Option B: import onnxruntime; self._model = ort.InferenceSession(path)
    raise NotImplementedError(
        "ARMBench model weights not integrated yet. "
        "Add model loading in ARMBenchDetector._load_model()."
    )
```

---

## 3. Waterfall nguồn định vị (`locate_object`)

Khi agent gọi `locate_object("pallet_jack")`, `GazeboBackend` thử theo thứ tự:

```
1. PerceptionNode (/warehouse/detected_objects, 2 Hz)
   │  source = "gz_gt"           → ground-truth Gazebo pose (mặc định)
   │  source = "registry"        → tọa độ tĩnh từ registry
   │  source = "armbench_depth"  → [CHỈ KHI có model weights] ARMBench detector
   │
   └─ nếu không tìm thấy trong perception topic:
      │
      2. _WORLD_OBJECTS registry (tọa độ tĩnh hardcode)
         │  source = "gt_registry"
         │
         └─ nếu không có:
            │
            3. gz CLI trực tiếp: gz model -p <model_name>
               │  source = "gz_cli"
               │
               └─ nếu thất bại:
                  source = "not_found"  →  None trả về agent
```

**Mặc định hiện tại (`detector_backend=gz_gt`):**  
PerceptionNode bỏ qua camera và trả ground-truth pose trực tiếp từ Gazebo.  
Detector ARMBench không được gọi.

---

## 4. Cái gì thực sự được dùng trong các lần chạy eval

### Bảng C — Gazebo dry-run (2026-06-10)

Tất cả task trong Bảng C đều là **dry-run** (`--dry-run`). Không có lần chạy live nào được thực hiện.

| Task | Lần chạy live? | Detector dùng | locate_source ghi được |
|------|---------------|---------------|------------------------|
| m1 | ❌ dry-run | — | — |
| m2 | ❌ dry-run | — | — |
| m3 | ❌ dry-run | — | — |

### Bảng demo durability (2026-06-10)

Dùng `Flat2DBackend` (backend 2D, không có camera). ARMBench không liên quan.

### Bảng parity check (2026-06-10)

Cả hai trace dùng `Flat2DBackend`. ARMBench không liên quan.

---

## 5. Kết luận: không có số nào để báo cáo

Vì model weights chưa được train/tích hợp và không có lần chạy live nào thực sự dùng ARMBench detector:

- **Không có số mAP / recall / precision** nào của ARMBench detector trong dự án này
- **Không có so sánh** ARMBench vs ground-truth trên tập test
- **Mọi kết quả Bảng C** hiện là dry-run (placeholder `—`)

Kết quả quan sát được thực tế: **0 lần chạy live với ARMBench detector**.

---

## 6. Hướng dẫn trình bày (Q&A ngày demo)

### "Hệ thống có dùng ARMBench không?"

> "Chúng tôi đã tích hợp hook kết nối ARMBench vào `PerceptionNode` —  
> pipeline từ ảnh depth camera đến map-frame Pose2D đã chạy được.  
> Tuy nhiên model weights chưa được fine-tune từ bộ dữ liệu ARMBench.  
> Trong các lần chạy hiện tại, hệ thống dùng ground-truth pose từ Gazebo  
> (`gz_gt` mode) — tương đương cảm biến lý tưởng trong mô phỏng."

### "Độ chính xác detector là bao nhiêu?"

> "Chúng tôi chưa đo accuracy của ARMBench detector vì model weights chưa có.  
> Ground-truth mode (`gz model -p`) chính xác 100% trong mô phỏng —  
> đây là mức trần lý thuyết, không phải kết quả detector thật."

### "ARMBench dataset có liên quan thực sự không?"

> "ARMBench là dataset công khai cho thấy loại dữ liệu cần thiết.  
> Mã nguồn đã có điểm tích hợp sẵn — bước tiếp theo là fine-tune model  
> trên ảnh depth camera của AWS warehouse world và gắn weights vào  
> `ARMBenchDetector._load_model()`."

---

## 7. Bước tiếp theo để tích hợp thật

```bash
# 1. Cài dependencies
pip install ultralytics    # YOLOv8
# hoặc: pip install onnxruntime

# 2. Fine-tune trên ARMBench pallet images
#    (hoặc dùng pre-trained weights nếu có)

# 3. Gắn vào perception_node.py:_load_model()
#    self._model = YOLO("path/to/weights.pt")

# 4. Bật armbench backend
ros2 run warehouse_robot_agent perception_node \
    --ros-args -p detector_backend:=armbench \
               -p model_weights:=/path/to/weights.pt

# 5. Đo accuracy: chạy trên test split ARMBench,
#    ghi mAP@0.5 và recall → thêm vào bảng này
```

---

*Tài liệu này được viết theo nguyên tắc honesty-first của dự án.*  
*Cập nhật khi có số liệu đo thực.*

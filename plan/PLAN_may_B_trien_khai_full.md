# PLAN triển khai full Máy B — P0–P5
| Pha | Nội dung | DoD gate | Trạng thái |
|---|---|---|---|
| P0 | Self-contain repo | clone sạch → build → /odom | ✅ a65436e |
| P1 | Fix nav physics (SDF link poses) | Nav2 1 goal, GT ≤1.0m đích | đang làm |
| P2 | pick/drop thật (bỏ teleport _gz_set_pose) | pallet ngồi trên fork qua physics | chưa |
| P3 | Sensor/ARMBench → locate_object (bỏ dict tĩnh) | locate từ camera/depth thật | chưa |
| P4 | Eval Bảng C + parity + video | report số thật + nhãn điều kiện | chưa |
| P5 | Honesty/docs pass | mọi số có nhãn; disclosure đủ | chưa |

Chi tiết lệnh từng pha: plan/LENH_*.md (Máy A cấp theo từng pha).

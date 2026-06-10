# Demo Durability — "5 lần liên tiếp không fail" *(dry-run — Flat2DBackend)*

> Run: 2026-06-10T06:18:15+00:00
> Goal: *Retrieve the pallet_jack from its storage location and deliver it to drop-off zone A (dropoff_a at coordinates 0, 0).*
> Target: 5 consecutive passes

## Result: ❌ STREAK 2/5 — not yet stable

| Metric | Value |
|--------|-------|
| Attempts completed | 5 |
| Passes | 4/5 |
| Current streak | **2/5** |
| Backend | Flat2DBackend (dry-run) |

## Attempt log

| # | Success | Steps | Time (s) | Dist→dropoff_a (m) | Note |
|---|---------|-------|----------|--------------------|------|
| 1 | ✓ | 10 | 0.0 | 0.000 |  |
| 2 | ✓ | 10 | 0.0 | 0.000 |  |
| 3 | ✗ | 12 | 95.3 | 11.314 | pallet_not_moved |
| 4 | ✓ | 10 | 0.0 | 0.000 |  |
| 5 | ✓ | 10 | 0.0 | 0.000 |  |


## Failure log

### Attempt 3 — `pallet_not_moved`

- Steps taken: 12
- Oracle: pallet at (-8.00, -8.00), dist = 11.314 m
- done() called: True

**Remediation:** Oracle shows pallet never reached dropoff_a. Robot may have navigated without physically pushing the pallet. Verify fork height on pick: set to 0.20 m before move_to(dropoff_a).


## Recovery playbook

If the demo breaks during the actual presentation:

| Symptom | Command |
|---------|---------|
| Nav2 action server timeout | `ros2 lifecycle set /nav2_lifecycle_manager configure && ros2 lifecycle set /nav2_lifecycle_manager activate` |
| AMCL lost (pose jumps) | `ros2 topic pub /initialpose geometry_msgs/PoseWithCovarianceStamped '{...}'` at known spawn |
| Gazebo crash | `tmux kill-session -t demo && ./start_demo.sh` (< 5 min) |
| foxglove_bridge silent | `ros2 launch foxglove_bridge foxglove_bridge_launch.xml` |
| Agent hangs at max steps | `Ctrl-C` agent process, reset pallet, relaunch `ros2 run warehouse_robot_agent llm_agent` |

> **Plan B:** video offline on USB — launch with `vlc demo_gazebo.mp4` while recovery proceeds.

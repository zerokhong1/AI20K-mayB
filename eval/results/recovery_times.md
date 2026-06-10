# Recovery Procedures — Gazebo/Nav2/foxglove_bridge

> Last updated: 2026-06-10T06:43:03+00:00
> Workspace: `/home/cth/AI20K/colcon_ws`

## Layered restart commands

| Layer | Kill | Start | Time to ready |
|-------|------|-------|---------------|
| foxglove_bridge (L1) | `pkill -f foxglove_bridge \|\| true…` | `source /home/cth/AI20K/colcon_ws/install/setup.bash && …` | ~8 s (estimate — not yet measured) |
| Nav2 navigation stack (L2) | `ros2 lifecycle set /nav2_lifecycle_manager shutdown 2>/dev/n…` | `source /home/cth/AI20K/colcon_ws/install/setup.bash && …` | ~25 s (estimate — not yet measured) |
| Gazebo Harmonic + AWS world (L3) | `pkill -f 'gz sim' \|\| true; pkill -f 'gz_server' \|\| true;…` | `source /home/cth/AI20K/colcon_ws/install/setup.bash && …` | ~50 s (estimate — not yet measured) |
| Full stack (L4) | `pkill -f 'gz sim' \|\| true; pkill -f 'ros2 launch' \|\| tru…` | `bash /home/cth/AI20K/scripts/start_demo.sh &…` | ~180 s (estimate — not yet measured) |


## Recovery decision tree

```
Demo breaks
    │
    ├─ foxglove viz frozen?  → restart L1 foxglove_bridge  (~8 s)
    │
    ├─ Nav2 not responding?  → restart L2 Nav2             (~25 s)
    │    (move_to always fails, agent loops)
    │
    ├─ Gazebo frozen/crash?  → restart L3 Gazebo            (~50 s)
    │    (gz model --list empty)
    │
    └─ Multiple layers dead? → restart L4 Full stack        (~3 min)
         ./scripts/start_demo.sh
```

## Quick-reference commands

```bash
# L1 — foxglove_bridge only
pkill -f foxglove_bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml &

# L2 — Nav2 only
pkill -f nav2; pkill -f controller_server
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true \
    map:=~/AI20K/colcon_ws/src/aws-robomaker-small-warehouse-world/maps/005/map.yaml &

# L3 — Gazebo only
pkill -f 'gz sim'; sleep 2
source ~/AI20K/colcon_ws/install/setup.bash
ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py &

# L4 — Full stack (nuclear option)
pkill -f 'gz sim'; pkill -f 'ros2 launch'; pkill -f 'ros2 run'; pkill -f foxglove
sleep 3
bash ~/AI20K/scripts/start_demo.sh

# Reset pallet to spawn (between attempts without full restart)
gz service -s /world/small_warehouse/set_pose \
  --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 3000 \
  --req 'name: "aws_robomaker_warehouse_PalletJackB_01_001" \
         position: {x: -0.28, y: -9.48, z: 0.1} \
         orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}'

# Check stack health
python3 ~/AI20K/eval/recovery_check.py --check
```

## Measure actual times

```bash
# Measure restart time for one layer (live, destructive):
python3 eval/recovery_check.py --restart foxglove
python3 eval/recovery_check.py --restart nav2
python3 eval/recovery_check.py --restart gazebo

# Measure all layers in sequence (kills the running stack):
python3 eval/recovery_check.py --measure-all
```

## Health check — 2026-06-10T06:43:03+00:00

| Layer | Status | Check command |
|-------|--------|---------------|
| foxglove_bridge (L1) | ✗ | `nc -z localhost 8765` |
| Nav2 navigation stack (L2) | ✗ | `ros2 action list | grep navigate_to_pose` |
| Gazebo Harmonic + AWS world (L3) | ✗ | `gz model --list | grep PalletJack` |
| Full stack (L4) | ✗ | `Gazebo + Nav2 + foxglove_bridge all ready` |


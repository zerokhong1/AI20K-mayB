#!/bin/bash
# Kill all ROS 2 / Gazebo processes and clean stale shared memory.
# Run this before launching to ensure a clean start.

echo "Killing ROS 2 / Gazebo processes..."

for pat in 'gz sim' 'gz -r' 'gzserver' 'gz model' 'gz topic' \
           'small_warehouse.world' \
           'parameter_bridge' 'robot_state_publisher' \
           'component_container' 'ros2 launch warehouse_nav' \
           'warehouse_robot_agent'; do
    pkill -f "$pat" 2>/dev/null
done
sleep 2

# Force-kill any survivors (including orphaned gz sim whose comm shows as 'ruby' or truncated)
for pat in 'gz sim' 'gz -r' 'gzserver' 'small_warehouse.world' \
           'parameter_bridge' 'component_container'; do
    pkill -9 -f "$pat" 2>/dev/null
done
sleep 1

echo "Cleaning stale FastRTPS shared memory..."
rm -f /dev/shm/fastrtps_*

echo "Done. Remaining ROS/GZ processes:"
remaining=$(ps -ef | grep -E '(gz|parameter_bridge|robot_state|component_container|amcl|nav2)' \
    | grep -v 'grep\|code-server\|vscode\|claude' | awk '{print $2, $11}')
if [ -n "$remaining" ]; then echo "$remaining"; else echo "  (none)"; fi

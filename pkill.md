# Dừng tiến trình đang chạy trong terminal hiện tại
Ctrl+C

# Kill tất cả Gazebo (nếu bị treo)
pkill -f "gz sim"

# Kill tất cả ROS 2 nodes
pkill -f "ros2"

# Kill cả hai cùng lúc
pkill -f "gz sim"; pkill -f "ros2"

# Kiểm tra còn tiến trình nào không
ps aux | grep -E "gz|ros2" | grep -v grep


# Tóm tắt lệnh để chạy lần sau


bash scripts/kill_ros.sh && ros2 launch warehouse_nav warehouse_sim.launch.py robot_type:=forklift headless:=false
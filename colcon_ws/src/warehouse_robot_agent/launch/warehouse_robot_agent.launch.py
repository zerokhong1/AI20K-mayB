from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='warehouse_robot_agent',
            executable='warehouse_robot_agent_node',
            name='warehouse_robot_agent',
            output='screen',
            parameters=[
                {
                    'cmd_vel_topic': '/cmd_vel',
                    'laser_topic': '/scan',
                    'forward_speed': 0.2,
                    'rotation_speed': 0.6,
                    'min_distance': 0.8,
                    'scan_angle': 30.0,
                }
            ],
        )
    ])

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    aws_dir = get_package_share_directory('aws_robomaker_small_warehouse_world')
    ros_gz_sim_dir = get_package_share_directory('ros_gz_sim')

    world = LaunchConfiguration('world')

    declare_world = DeclareLaunchArgument(
        'world',
        default_value=os.path.join(
            aws_dir, 'worlds', 'small_warehouse', 'small_warehouse.world'),
        description='Full path to world SDF file')

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_dir, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': world, 'on_exit_shutdown': 'true'}.items()
    )

    return LaunchDescription([declare_world, gz_sim])

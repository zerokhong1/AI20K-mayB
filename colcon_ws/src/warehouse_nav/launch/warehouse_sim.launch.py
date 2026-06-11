"""
Bring up TurtleBot3 Waffle as AMR in the AWS small warehouse world with Nav2.

Gazebo Harmonic + ros_gz_bridge + Nav2 (AMCL + static map).

Usage:
  ros2 launch warehouse_nav warehouse_sim.launch.py
  ros2 launch warehouse_nav warehouse_sim.launch.py headless:=false use_rviz:=true
  ros2 launch warehouse_nav warehouse_sim.launch.py use_foxglove:=true
  # Then open https://app.foxglove.dev → Open connection → Foxglove WebSocket → ws://<IP>:8765
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    AppendEnvironmentVariable,
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
)
from launch.conditions import IfCondition, UnlessCondition, LaunchConfigurationEquals
from launch.event_handlers import OnShutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    warehouse_dir = get_package_share_directory('aws_robomaker_small_warehouse_world')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    tb3_sim_dir = get_package_share_directory('nav2_minimal_tb3_sim')
    pkg_dir = get_package_share_directory('warehouse_nav')

    # ---------- launch args ----------
    headless    = LaunchConfiguration('headless')
    use_rviz    = LaunchConfiguration('use_rviz')
    use_foxglove = LaunchConfiguration('use_foxglove')
    robot_type  = LaunchConfiguration('robot_type')
    use_sim_time = LaunchConfiguration('use_sim_time')
    slam = LaunchConfiguration('slam')
    autostart = LaunchConfiguration('autostart')
    params_file = LaunchConfiguration('params_file')

    declare_headless = DeclareLaunchArgument(
        'headless', default_value='True',
        description='Run Gazebo server only (no GUI)')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='False',
        description='Launch RViz2 for Nav2 visualisation')

    declare_use_foxglove = DeclareLaunchArgument(
        'use_foxglove', default_value='False',
        description='Start foxglove_bridge WebSocket server on port 8765')

    declare_robot_type = DeclareLaunchArgument(
        'robot_type', default_value='tb3_waffle',
        description='Robot model to spawn: tb3_waffle | forklift')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='True')

    declare_slam = DeclareLaunchArgument(
        'slam', default_value='False',
        description='Run SLAM instead of loading a static map')

    declare_autostart = DeclareLaunchArgument(
        'autostart', default_value='True')

    declare_params_file = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(pkg_dir, 'params', 'nav2_params.yaml'),
        description='Nav2 params file')

    # Robot spawn pose — in the main aisle of the warehouse
    x_pose = LaunchConfiguration('x_pose', default='3.45')
    y_pose = LaunchConfiguration('y_pose', default='2.15')
    z_pose = LaunchConfiguration('z_pose', default='0.01')
    yaw   = LaunchConfiguration('yaw',    default='3.14')

    # ---------- GZ_SIM_RESOURCE_PATH ----------
    # TB3 models
    set_gz_resources = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(tb3_sim_dir, 'models'))
    # AWS warehouse: share dir (for file://models/... URIs in model SDFs)
    set_gz_resources_aws = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', warehouse_dir)
    # AWS warehouse: models subdir (for model://... URIs in world SDF)
    set_gz_resources_aws_models = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(warehouse_dir, 'models'))

    # ---------- Gazebo server with warehouse world ----------
    world_file = os.path.join(
        warehouse_dir, 'worlds', 'small_warehouse', 'small_warehouse.world')

    _gz_env = {
        'GZ_SIM_RESOURCE_PATH': ':'.join([
            os.environ.get('GZ_SIM_RESOURCE_PATH', ''),
            os.path.join(tb3_sim_dir, 'models'),
            warehouse_dir,
            os.path.join(warehouse_dir, 'models'),
        ]).lstrip(':'),
        'GZ_SIM_SERVER_CONFIG_PATH': os.path.join(pkg_dir, 'config', 'gz_server.config'),
    }

    # Headless: server-only with headless rendering (no GUI window)
    gz_server = ExecuteProcess(
        cmd=['gz', 'sim', '-r', '-s', '--headless-rendering', world_file],
        output='screen',
        condition=IfCondition(headless),
        additional_env=_gz_env,
    )

    # GUI mode: full Gazebo (server + GUI window)
    gz_client = ExecuteProcess(
        cmd=['gz', 'sim', '-r', world_file],
        output='screen',
        condition=UnlessCondition(headless),
        additional_env=_gz_env,
    )

    # ---------- Spawn TB3 Waffle + ROS↔Gz bridge (default) ----------
    spawn_tb3 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_sim_dir, 'launch', 'spawn_tb3.launch.py')),
        launch_arguments={
            'x_pose': x_pose,
            'y_pose': y_pose,
            'z_pose': z_pose,
            'yaw': yaw,
        }.items(),
        condition=LaunchConfigurationEquals('robot_type', 'tb3_waffle'),
    )

    # ---------- Spawn Forklift + ROS↔Gz bridge ----------
    forklift_sdf = os.path.join(pkg_dir, 'models', 'warehouse_forklift', 'model.sdf')
    forklift_bridge_config = os.path.join(pkg_dir, 'config', 'forklift_bridge.yaml')

    spawn_forklift = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-world', 'default',
            '-file', forklift_sdf,
            '-name', 'warehouse_forklift',
            '-x', x_pose, '-y', y_pose, '-z', z_pose, '-Y', yaw,
        ],
        output='screen',
        condition=LaunchConfigurationEquals('robot_type', 'forklift'),
    )

    forklift_ros_gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='forklift_bridge',
        parameters=[{'config_file': forklift_bridge_config}],
        output='screen',
        condition=LaunchConfigurationEquals('robot_type', 'forklift'),
    )

    # ---------- Robot state publisher (URDF varies by robot_type) ----------
    urdf_tb3 = os.path.join(tb3_sim_dir, 'urdf', 'turtlebot3_waffle.urdf')
    with open(urdf_tb3, 'r') as f:
        robot_description_tb3 = f.read()

    urdf_forklift = os.path.join(pkg_dir, 'urdf', 'warehouse_forklift.urdf')
    with open(urdf_forklift, 'r') as f:
        robot_description_forklift = f.read()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'robot_description': robot_description_tb3,
        }],
        condition=LaunchConfigurationEquals('robot_type', 'tb3_waffle'),
    )

    robot_state_publisher_forklift = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'robot_description': robot_description_forklift,
        }],
        condition=LaunchConfigurationEquals('robot_type', 'forklift'),
    )

    # ---------- Nav2 (localization + navigation) ----------
    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')),
        launch_arguments={
            'slam': slam,
            'map': os.path.join(warehouse_dir, 'maps', '005', 'map.yaml'),
            'use_sim_time': use_sim_time,
            'params_file': params_file,
            'autostart': autostart,
            'use_composition': 'True',
        }.items(),
    )

    # ---------- Camera bridge (depth sensor → ROS 2) ----------
    # The TB3 Waffle depth camera (intel_realsense_r200_depth) only produces images
    # when Gazebo's rendering engine is active (headless:=false).
    # These bridge nodes start unconditionally; they publish nothing in headless mode.
    camera_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='camera_depth_bridge',
        output='screen',
        arguments=[
            '/world/default/model/turtlebot3_waffle/link/camera_link'
            '/sensor/intel_realsense_r200_depth/depth_image'
            '@sensor_msgs/msg/Image[gz.msgs.Image',
        ],
        remappings=[(
            '/world/default/model/turtlebot3_waffle/link/camera_link'
            '/sensor/intel_realsense_r200_depth/depth_image',
            '/camera/depth/image_raw',
        )],
    )

    camera_info_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='camera_info_bridge',
        output='screen',
        arguments=[
            '/world/default/model/turtlebot3_waffle/link/camera_link'
            '/sensor/intel_realsense_r200_depth/camera_info'
            '@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        remappings=[(
            '/world/default/model/turtlebot3_waffle/link/camera_link'
            '/sensor/intel_realsense_r200_depth/camera_info',
            '/camera/camera_info',
        )],
    )

    # ---------- RViz (optional) ----------
    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'rviz_launch.py')),
        condition=IfCondition(use_rviz),
        launch_arguments={'use_sim_time': use_sim_time}.items(),
    )

    # ---------- Foxglove bridge (optional) ----------
    foxglove_bridge = Node(
        package='foxglove_bridge',
        executable='foxglove_bridge',
        name='foxglove_bridge',
        output='screen',
        condition=IfCondition(use_foxglove),
        parameters=[os.path.join(pkg_dir, 'params', 'foxglove_params.yaml')],
    )

    return LaunchDescription([
        declare_headless,
        declare_use_rviz,
        declare_use_foxglove,
        declare_robot_type,
        declare_use_sim_time,
        declare_slam,
        declare_autostart,
        declare_params_file,
        set_gz_resources,
        set_gz_resources_aws,
        set_gz_resources_aws_models,
        gz_server,
        gz_client,
        # Robot spawn — only one fires depending on robot_type
        spawn_tb3,
        spawn_forklift,
        forklift_ros_gz_bridge,
        # RSP — one per robot_type
        robot_state_publisher,
        robot_state_publisher_forklift,
        nav2_bringup,
        rviz,
        foxglove_bridge,
        camera_bridge,
        camera_info_bridge,
    ])

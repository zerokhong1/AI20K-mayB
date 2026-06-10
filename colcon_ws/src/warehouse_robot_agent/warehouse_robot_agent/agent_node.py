import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class WarehouseRobotAgent(Node):
    def __init__(self):
        super().__init__('warehouse_robot_agent')

        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('laser_topic', '/scan')
        self.declare_parameter('forward_speed', 0.2)
        self.declare_parameter('rotation_speed', 0.6)
        self.declare_parameter('min_distance', 0.8)
        self.declare_parameter('scan_angle', 30.0)

        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.laser_topic = self.get_parameter('laser_topic').get_parameter_value().string_value
        self.forward_speed = self.get_parameter('forward_speed').get_parameter_value().double_value
        self.rotation_speed = self.get_parameter('rotation_speed').get_parameter_value().double_value
        self.min_distance = self.get_parameter('min_distance').get_parameter_value().double_value
        self.scan_angle = float(self.get_parameter('scan_angle').get_parameter_value().double_value)

        self.obstacle_detected = False
        self.cmd_vel_publisher = self.create_publisher(Twist, self.cmd_vel_topic, 10)

        self.get_logger().info(f'Publishing cmd_vel to: {self.cmd_vel_topic}')

        try:
            self.scan_subscriber = self.create_subscription(
                LaserScan,
                self.laser_topic,
                self.scan_callback,
                10,
            )
            self.get_logger().info(f'Subscribed to LaserScan on: {self.laser_topic}')
        except Exception as exc:
            self.scan_subscriber = None
            self.get_logger().warn(
                f'Could not subscribe to LaserScan topic "{self.laser_topic}": {exc}. '
                'Agent will run in open-loop mode.'
            )

        self.create_timer(0.1, self.control_loop)

    def scan_callback(self, msg: LaserScan) -> None:
        ranges = [r for r in msg.ranges if not math.isinf(r) and not math.isnan(r)]
        if not ranges:
            self.obstacle_detected = False
            return

        if self.scan_angle <= 0.0:
            relevant = ranges
        else:
            half_window = int(round((self.scan_angle / 180.0) * len(ranges) / 2.0))
            mid = len(ranges) // 2
            start = max(0, mid - half_window)
            end = min(len(ranges), mid + half_window + 1)
            relevant = ranges[start:end]

        self.obstacle_detected = any(distance < self.min_distance for distance in relevant)

    def control_loop(self) -> None:
        cmd = Twist()
        if self.obstacle_detected:
            cmd.angular.z = self.rotation_speed
        else:
            cmd.linear.x = self.forward_speed

        self.cmd_vel_publisher.publish(cmd)

    def destroy_node(self) -> None:
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WarehouseRobotAgent()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

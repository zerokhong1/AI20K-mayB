from setuptools import setup

package_name = 'warehouse_robot_agent'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=False,
    author='AI20K',
    author_email='cth@example.com',
    description='A simple ROS2 agent node for warehouse robot control.',
    entry_points={
        'console_scripts': [
            'warehouse_robot_agent_node = warehouse_robot_agent.agent_node:main',
            'llm_agent = warehouse_robot_agent.llm_agent:main',
            'oracle = warehouse_robot_agent.oracle:main',
            'perception_node = warehouse_robot_agent.perception_node:main',
        ],
    },
)

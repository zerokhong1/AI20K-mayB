cmake_minimum_required(VERSION 3.5)
project(warehouse_nav)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch params models urdf config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()

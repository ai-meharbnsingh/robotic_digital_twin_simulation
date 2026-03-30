"""ROS2 Bridge — connects FMS to ROS2 nav2 stack with graceful fallback.

When rclpy is unavailable (no ROS2 installed), all operations return
simulated responses. In Docker with ros:humble base image, uses real
ROS2 topics for navigation, odometry, and LiDAR.
"""

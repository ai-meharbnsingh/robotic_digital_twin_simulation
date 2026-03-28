// ──────────────────────────────────────────────────────────
// robot/MotionController.cpp — Proportional motion controller
//
// Phase 4: Simple P-controller with velocity and acceleration
// clamping.  MPC+OSQP upgrade deferred to Phase 7.
// ──────────────────────────────────────────────────────────

#include "rdt/robot/MotionController.h"

#include <cmath>
#include <algorithm>

namespace rdt {

MotionController::MotionController(const RobotConfig& config)
    : config_(config)
    , prev_linear_velocity_(0.0)
    , prev_angular_velocity_(0.0)
{
}

Velocity MotionController::computeVelocity(const Pose& current_pose,
                                            const Pose& target_pose,
                                            double dt_seconds) const {
    // ── Distance to target ──
    double dx = target_pose.x - current_pose.x;
    double dy = target_pose.y - current_pose.y;
    double distance = std::sqrt(dx * dx + dy * dy);

    // ── Within tolerance → stop ──
    if (distance <= config_.motion.position_tolerance) {
        prev_linear_velocity_  = 0.0;
        prev_angular_velocity_ = 0.0;
        return {0.0, 0.0};
    }

    // ── Desired heading to target ──
    double desired_yaw = std::atan2(dy, dx);

    // ── Heading error (normalized to [-pi, pi]) ──
    double yaw_error = desired_yaw - current_pose.yaw;
    while (yaw_error >  M_PI) yaw_error -= 2.0 * M_PI;
    while (yaw_error < -M_PI) yaw_error += 2.0 * M_PI;

    // ── Proportional gains ──
    // Linear: P-gain = 1.0 (proportional to distance, clamped to max)
    double desired_linear = distance;  // proportional gain = 1.0

    // Angular: P-gain = 2.0 (aggressive heading correction)
    double desired_angular = 2.0 * yaw_error;

    // ── Clamp to velocity limits ──
    double max_lin = config_.motion.max_linear_velocity;
    double max_ang = config_.motion.max_angular_velocity;

    desired_linear  = std::clamp(desired_linear, 0.0, max_lin);
    desired_angular = std::clamp(desired_angular, -max_ang, max_ang);

    // ── Acceleration limiting ──
    if (dt_seconds > 0.0) {
        double max_accel = config_.motion.linear_acceleration * dt_seconds;
        double max_decel = config_.motion.linear_deceleration * dt_seconds;

        double lin_diff = desired_linear - prev_linear_velocity_;
        if (lin_diff > max_accel) {
            desired_linear = prev_linear_velocity_ + max_accel;
        } else if (lin_diff < -max_decel) {
            desired_linear = prev_linear_velocity_ - max_decel;
        }

        // Clamp angular acceleration (use same rates as linear for simplicity)
        double ang_diff = desired_angular - prev_angular_velocity_;
        if (ang_diff > max_accel) {
            desired_angular = prev_angular_velocity_ + max_accel;
        } else if (ang_diff < -max_accel) {
            desired_angular = prev_angular_velocity_ - max_accel;
        }
    }

    // ── Final clamp (ensure we never exceed limits after accel limiting) ──
    desired_linear  = std::clamp(desired_linear, 0.0, max_lin);
    desired_angular = std::clamp(desired_angular, -max_ang, max_ang);

    // ── Update previous velocities for next call ──
    prev_linear_velocity_  = desired_linear;
    prev_angular_velocity_ = desired_angular;

    return {desired_linear, desired_angular};
}

bool MotionController::isAtTarget(const Pose& current_pose,
                                   const Pose& target_pose) const {
    double dx = target_pose.x - current_pose.x;
    double dy = target_pose.y - current_pose.y;
    double distance = std::sqrt(dx * dx + dy * dy);
    return distance <= config_.motion.position_tolerance;
}

double MotionController::getPositionTolerance() const {
    return config_.motion.position_tolerance;
}

double MotionController::getAngularTolerance() const {
    return config_.motion.angular_tolerance;
}

} // namespace rdt

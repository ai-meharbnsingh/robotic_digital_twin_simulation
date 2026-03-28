#pragma once

// ──────────────────────────────────────────────────────────
// rdt/robot/MotionController.h — Proportional motion controller
//
// Phase 4: Simple proportional controller that:
//   - Computes velocity toward a target pose
//   - Respects max_linear_velocity, max_angular_velocity
//   - Respects linear_acceleration / linear_deceleration limits
//   - Returns zero velocity within position_tolerance
//
// Phase 7 upgrade: MPC + OSQP for optimal trajectory tracking.
// ──────────────────────────────────────────────────────────

#include "rdt/core/Types.h"
#include "rdt/core/Config.h"

namespace rdt {

class MotionController {
public:
    /// Construct with robot configuration.
    /// Reads MPC params and motion limits from config.
    explicit MotionController(const RobotConfig& config);

    /// Compute velocity command to move from current_pose toward target_pose.
    /// @param current_pose  The robot's current position and heading
    /// @param target_pose   The desired goal position and heading
    /// @param dt_seconds    Time step for acceleration limiting
    /// @return Velocity command (linear, angular) respecting all limits
    Velocity computeVelocity(const Pose& current_pose,
                             const Pose& target_pose,
                             double dt_seconds = 0.1) const;

    /// Check if the robot is within position tolerance of the target.
    bool isAtTarget(const Pose& current_pose,
                    const Pose& target_pose) const;

    /// Get the position tolerance from config.
    double getPositionTolerance() const;

    /// Get the angular tolerance from config.
    double getAngularTolerance() const;

private:
    RobotConfig config_;
    // Track previous velocity for acceleration limiting (mutable for const method)
    mutable double prev_linear_velocity_;
    mutable double prev_angular_velocity_;
};

} // namespace rdt

#pragma once

// ──────────────────────────────────────────────────────────
// rdt/robot/ObstacleHandler.h — Obstacle response logic
//
// Evaluates distance to nearest obstacle and returns an action:
//   distance <= critical_m   → EMERGENCY_STOP
//   distance <= warning_m    → DECELERATE
//   distance <= planning_m   → REPLAN
//   distance >  planning_m   → NONE
//
// All thresholds from config YAML — NO hardcoded values.
// ──────────────────────────────────────────────────────────

#include "rdt/core/Config.h"

#include <string>

namespace rdt {

class ObstacleHandler {
public:
    /// Actions the robot can take in response to obstacles.
    enum class Action {
        NONE,            ///< No obstacle in range — continue normally
        REPLAN,          ///< Obstacle in planning zone — compute alternate path
        DECELERATE,      ///< Obstacle in warning zone — reduce speed
        EMERGENCY_STOP   ///< Obstacle critically close — full stop
    };

    /// Construct with robot configuration.
    /// Reads obstacle thresholds from config.
    explicit ObstacleHandler(const RobotConfig& config);

    /// Evaluate the distance to an obstacle and return the appropriate action.
    /// @param distance  Distance to nearest obstacle in meters (>= 0)
    /// @return The action to take
    Action evaluate(double distance) const;

    /// Get the critical distance threshold.
    double getCriticalThreshold() const;

    /// Get the warning distance threshold.
    double getWarningThreshold() const;

    /// Get the planning distance threshold.
    double getPlanningThreshold() const;

    /// Convert an Action to its string representation.
    static std::string actionToString(Action action);

private:
    ObstacleThresholdsConfig thresholds_;
};

} // namespace rdt

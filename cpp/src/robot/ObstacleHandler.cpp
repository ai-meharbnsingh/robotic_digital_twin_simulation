// ──────────────────────────────────────────────────────────
// robot/ObstacleHandler.cpp — Obstacle evaluation logic
//
// All thresholds from config YAML — zero hardcoded values.
// ──────────────────────────────────────────────────────────

#include "rdt/robot/ObstacleHandler.h"

namespace rdt {

ObstacleHandler::ObstacleHandler(const RobotConfig& config)
    : thresholds_(config.obstacle_thresholds)
{
}

ObstacleHandler::Action ObstacleHandler::evaluate(double distance) const {
    if (distance <= thresholds_.critical_m) {
        return Action::EMERGENCY_STOP;
    }
    if (distance <= thresholds_.warning_m) {
        return Action::DECELERATE;
    }
    if (distance <= thresholds_.planning_m) {
        return Action::REPLAN;
    }
    return Action::NONE;
}

double ObstacleHandler::getCriticalThreshold() const {
    return thresholds_.critical_m;
}

double ObstacleHandler::getWarningThreshold() const {
    return thresholds_.warning_m;
}

double ObstacleHandler::getPlanningThreshold() const {
    return thresholds_.planning_m;
}

std::string ObstacleHandler::actionToString(Action action) {
    switch (action) {
        case Action::NONE:            return "NONE";
        case Action::REPLAN:          return "REPLAN";
        case Action::DECELERATE:      return "DECELERATE";
        case Action::EMERGENCY_STOP:  return "EMERGENCY_STOP";
    }
    return "UNKNOWN";
}

} // namespace rdt

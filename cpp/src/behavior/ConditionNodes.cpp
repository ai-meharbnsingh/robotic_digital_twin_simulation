// ──────────────────────────────────────────────────────────
// behavior/ConditionNodes.cpp — BT condition node implementations
//
// Each condition evaluates robot state and returns bool.
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/ConditionNodes.h"
#include "rdt/robot/ObstacleHandler.h"

#include <cstdlib>  // std::atof

namespace rdt {

// ── BatteryLow ─────────────────────────────────────────

bool conditionBatteryLow(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.battery) return false;
    return ctx.battery->isCritical();
}

// ── BatteryAboveThreshold ──────────────────────────────

bool conditionBatteryAboveThreshold(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.battery) return true;

    double threshold = 20.0;
    auto it = params.find("threshold_pct");
    if (it != params.end()) {
        threshold = std::atof(it->second.c_str());
    }

    return ctx.battery->getPercentage() >= threshold;
}

// ── TaskAvailable ──────────────────────────────────────

bool conditionTaskAvailable(BTRobotContext& ctx, const BTParams& /*params*/) {
    return ctx.task_available;
}

// ── ObstacleDetected ───────────────────────────────────

bool conditionObstacleDetected(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.obstacles) return false;

    // Check the obstacle_detected flag set by sensor/simulation,
    // or evaluate the obstacle distance against critical threshold.
    if (ctx.obstacle_detected) return true;

    // Evaluate distance through the ObstacleHandler: anything other
    // than NONE means an obstacle is detected in some zone.
    auto action = ctx.obstacles->evaluate(ctx.obstacle_distance);
    return action != ObstacleHandler::Action::NONE;
}

// ── HasErrors ──────────────────────────────────────────

bool conditionHasErrors(BTRobotContext& ctx, const BTParams& /*params*/) {
    return ctx.has_errors;
}

// ── NoErrors ───────────────────────────────────────────

bool conditionNoErrors(BTRobotContext& ctx, const BTParams& /*params*/) {
    return !ctx.has_errors;
}

// ── CargoSecured ───────────────────────────────────────

bool conditionCargoSecured(BTRobotContext& ctx, const BTParams& /*params*/) {
    return ctx.cargo_secured;
}

// ── ObstacleInCriticalZone (AMR) ──────────────────────

bool conditionObstacleInCriticalZone(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.obstacles) return false;

    // Use distance_m param from XML if provided, otherwise use handler threshold
    double distance = ctx.obstacle_distance;
    auto it = params.find("distance_m");
    if (it != params.end()) {
        double threshold = std::atof(it->second.c_str());
        return distance <= threshold;
    }

    auto action = ctx.obstacles->evaluate(distance);
    return action == ObstacleHandler::Action::EMERGENCY_STOP;
}

// ── ObstacleInWarningZone (AMR) ──────────────────────

bool conditionObstacleInWarningZone(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.obstacles) return false;

    double distance = ctx.obstacle_distance;
    auto it = params.find("distance_m");
    if (it != params.end()) {
        double threshold = std::atof(it->second.c_str());
        return distance <= threshold;
    }

    auto action = ctx.obstacles->evaluate(distance);
    return action == ObstacleHandler::Action::DECELERATE ||
           action == ObstacleHandler::Action::EMERGENCY_STOP;
}

// ── HasLifterAttachment (AMR) ────────────────────────

bool conditionHasLifterAttachment(BTRobotContext& ctx, const BTParams& /*params*/) {
    return ctx.has_lifter;
}

// ── Register all standard conditions ───────────────────

void registerStandardConditions(BTEngine& engine, BTRobotContext& ctx) {
    engine.registerCondition("BatteryLow",
        [&ctx](const BTParams& p) { return conditionBatteryLow(ctx, p); });

    engine.registerCondition("BatteryAboveThreshold",
        [&ctx](const BTParams& p) { return conditionBatteryAboveThreshold(ctx, p); });

    engine.registerCondition("TaskAvailable",
        [&ctx](const BTParams& p) { return conditionTaskAvailable(ctx, p); });

    engine.registerCondition("ObstacleDetected",
        [&ctx](const BTParams& p) { return conditionObstacleDetected(ctx, p); });

    engine.registerCondition("HasErrors",
        [&ctx](const BTParams& p) { return conditionHasErrors(ctx, p); });

    engine.registerCondition("NoErrors",
        [&ctx](const BTParams& p) { return conditionNoErrors(ctx, p); });

    engine.registerCondition("CargoSecured",
        [&ctx](const BTParams& p) { return conditionCargoSecured(ctx, p); });

    // AMR-specific conditions
    engine.registerCondition("ObstacleInCriticalZone",
        [&ctx](const BTParams& p) { return conditionObstacleInCriticalZone(ctx, p); });

    engine.registerCondition("ObstacleInWarningZone",
        [&ctx](const BTParams& p) { return conditionObstacleInWarningZone(ctx, p); });

    engine.registerCondition("HasLifterAttachment",
        [&ctx](const BTParams& p) { return conditionHasLifterAttachment(ctx, p); });
}

} // namespace rdt

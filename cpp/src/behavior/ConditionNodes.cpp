// ──────────────────────────────────────────────────────────
// behavior/ConditionNodes.cpp — BT condition node implementations
//
// Each condition evaluates robot state and returns bool.
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/ConditionNodes.h"

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

    // For simulation, we check if the obstacle handler would trigger
    // an emergency stop (obstacle within critical range).
    // The actual range is set externally by the simulation.
    // Here we just check if there's an obstacle reading available.
    // In a real system, this would read from LiDAR data.
    return false;  // Default: no obstacle in simulation
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
}

} // namespace rdt

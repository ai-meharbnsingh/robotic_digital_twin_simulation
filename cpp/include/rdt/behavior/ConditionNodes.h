#pragma once

// ──────────────────────────────────────────────────────────
// rdt/behavior/ConditionNodes.h — BT condition node handlers
//
// Each condition returns true (SUCCESS) or false (FAILURE).
//
// Conditions:
//   BatteryLow            — battery < critical threshold (from config)
//   BatteryAboveThreshold — battery >= threshold_pct (from XML param)
//   TaskAvailable         — checks if a task is assigned
//   ObstacleDetected      — checks if obstacle within critical range
//   HasErrors             — checks if robot has active errors
//   NoErrors              — inverse of HasErrors
//   CargoSecured          — checks if cargo is loaded and secured
//
// These are registered with BTEngine via registerCondition().
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/BTEngine.h"
#include "rdt/behavior/ActionNodes.h"  // BTRobotContext

namespace rdt {

/// Registers all standard AGV condition handlers with the BTEngine.
void registerStandardConditions(BTEngine& engine, BTRobotContext& ctx);

// ── Individual condition handlers (for direct testing) ──

bool conditionBatteryLow(BTRobotContext& ctx, const BTParams& params);
bool conditionBatteryAboveThreshold(BTRobotContext& ctx, const BTParams& params);
bool conditionTaskAvailable(BTRobotContext& ctx, const BTParams& params);
bool conditionObstacleDetected(BTRobotContext& ctx, const BTParams& params);
bool conditionHasErrors(BTRobotContext& ctx, const BTParams& params);
bool conditionNoErrors(BTRobotContext& ctx, const BTParams& params);
bool conditionCargoSecured(BTRobotContext& ctx, const BTParams& params);

// ── AMR-specific condition handlers ─────────────────
bool conditionObstacleInCriticalZone(BTRobotContext& ctx, const BTParams& params);
bool conditionObstacleInWarningZone(BTRobotContext& ctx, const BTParams& params);
bool conditionHasLifterAttachment(BTRobotContext& ctx, const BTParams& params);

} // namespace rdt

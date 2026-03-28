#pragma once

// ──────────────────────────────────────────────────────────
// rdt/behavior/ActionNodes.h — BT action node handlers
//
// Each handler takes a RobotStateMachine reference (+ optional
// BatteryModel, ObstacleHandler) and returns BTStatus.
//
// Action handlers:
//   NavigateToNode    — transitions to MOVING, returns RUNNING until done
//   DockAtCharger     — transitions to DOCKING
//   StartCharging     — transitions DOCKING→CHARGING, starts battery charge
//   UndockFromCharger — transitions CHARGING→IDLE (via stop charging)
//   ExecuteAttachment — LOADING or UNLOADING based on action_code
//   ReportTaskComplete— marks task done, returns SUCCESS
//   SendActionCode    — generic action code dispatch (reset_errors, etc.)
//   WaitSeconds       — returns RUNNING for N seconds
//   WaitUntilCharged  — returns RUNNING until battery >= target_pct
//   AcceptTask        — accepts a task assignment
//   AlignAtStation    — alignment at pickup/drop station
//
// These are registered with BTEngine via registerAction().
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/BTEngine.h"
#include "rdt/robot/RobotState.h"
#include "rdt/robot/BatteryModel.h"
#include "rdt/robot/ObstacleHandler.h"

#include <string>

namespace rdt {

// ── Robot context for BT action handlers ───────────────

/// Aggregates all robot subsystems that action nodes need.
struct BTRobotContext {
    RobotStateMachine* state_machine = nullptr;
    BatteryModel*      battery       = nullptr;
    ObstacleHandler*   obstacles     = nullptr;

    // Simulated state for testing / tick-based progression
    bool   move_complete      = false;   // set by sim when destination reached
    bool   dock_complete      = false;   // set by sim when docking done
    bool   attachment_done    = false;   // set by sim when load/unload done
    bool   task_available     = false;   // set by task manager
    bool   has_errors         = false;   // set by error monitor
    bool   cargo_secured      = false;   // set after load complete
    double wait_elapsed_s     = 0.0;     // accumulated wait time
    std::string current_task_id;
};

// ── Register all standard action nodes ─────────────────

/// Registers all standard AGV action handlers with the BTEngine.
/// Call this after creating the engine and before loading XML.
void registerStandardActions(BTEngine& engine, BTRobotContext& ctx);

// ── Individual action handlers (for direct testing) ────

BTStatus actionNavigateToNode(BTRobotContext& ctx, const BTParams& params);
BTStatus actionDockAtCharger(BTRobotContext& ctx, const BTParams& params);
BTStatus actionStartCharging(BTRobotContext& ctx, const BTParams& params);
BTStatus actionUndockFromCharger(BTRobotContext& ctx, const BTParams& params);
BTStatus actionExecuteAttachment(BTRobotContext& ctx, const BTParams& params);
BTStatus actionReportTaskComplete(BTRobotContext& ctx, const BTParams& params);
BTStatus actionSendActionCode(BTRobotContext& ctx, const BTParams& params);
BTStatus actionWaitSeconds(BTRobotContext& ctx, const BTParams& params);
BTStatus actionWaitUntilCharged(BTRobotContext& ctx, const BTParams& params);
BTStatus actionAcceptTask(BTRobotContext& ctx, const BTParams& params);
BTStatus actionAlignAtStation(BTRobotContext& ctx, const BTParams& params);

} // namespace rdt

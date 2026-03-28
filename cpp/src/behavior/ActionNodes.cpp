// ──────────────────────────────────────────────────────────
// behavior/ActionNodes.cpp — BT action node implementations
//
// Each action interacts with the RobotStateMachine and
// related subsystems via BTRobotContext.
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/ActionNodes.h"

#include <cstdlib>  // std::atof, std::atoi

namespace rdt {

// ── NavigateToNode ─────────────────────────────────────

BTStatus actionNavigateToNode(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.state_machine) return BTStatus::FAILURE;

    RobotState current = ctx.state_machine->getCurrentState();

    if (current == RobotState::IDLE) {
        // Start moving
        if (!ctx.state_machine->transitionTo(RobotState::MOVING)) {
            return BTStatus::FAILURE;
        }
        ctx.move_complete = false;
        return BTStatus::RUNNING;
    }

    if (current == RobotState::MOVING) {
        if (ctx.move_complete) {
            // Arrived — transition back to IDLE
            ctx.state_machine->transitionTo(RobotState::IDLE);
            return BTStatus::SUCCESS;
        }
        return BTStatus::RUNNING;
    }

    return BTStatus::FAILURE;
}

// ── DockAtCharger ──────────────────────────────────────

BTStatus actionDockAtCharger(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.state_machine) return BTStatus::FAILURE;

    RobotState current = ctx.state_machine->getCurrentState();

    if (current == RobotState::IDLE) {
        if (!ctx.state_machine->transitionTo(RobotState::DOCKING)) {
            return BTStatus::FAILURE;
        }
        ctx.dock_complete = false;
        return BTStatus::RUNNING;
    }

    if (current == RobotState::DOCKING) {
        if (ctx.dock_complete) {
            return BTStatus::SUCCESS;
        }
        return BTStatus::RUNNING;
    }

    return BTStatus::FAILURE;
}

// ── StartCharging ──────────────────────────────────────

BTStatus actionStartCharging(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.state_machine) return BTStatus::FAILURE;

    RobotState current = ctx.state_machine->getCurrentState();

    if (current == RobotState::DOCKING) {
        if (!ctx.state_machine->transitionTo(RobotState::CHARGING)) {
            return BTStatus::FAILURE;
        }
        if (ctx.battery) {
            ctx.battery->startCharging();
        }
        return BTStatus::SUCCESS;
    }

    if (current == RobotState::CHARGING) {
        // Already charging
        return BTStatus::SUCCESS;
    }

    return BTStatus::FAILURE;
}

// ── UndockFromCharger ──────────────────────────────────

BTStatus actionUndockFromCharger(BTRobotContext& ctx, const BTParams& /*params*/) {
    if (!ctx.state_machine) return BTStatus::FAILURE;

    RobotState current = ctx.state_machine->getCurrentState();

    if (current == RobotState::CHARGING) {
        if (ctx.battery) {
            ctx.battery->stopCharging();
        }
        if (!ctx.state_machine->transitionTo(RobotState::IDLE)) {
            return BTStatus::FAILURE;
        }
        return BTStatus::SUCCESS;
    }

    if (current == RobotState::IDLE) {
        // Already undocked
        return BTStatus::SUCCESS;
    }

    return BTStatus::FAILURE;
}

// ── ExecuteAttachment ──────────────────────────────────

BTStatus actionExecuteAttachment(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.state_machine) return BTStatus::FAILURE;

    // Determine action from action_code: 14=loading, 15=unloading
    int action_code = 0;
    auto it = params.find("action_code");
    if (it != params.end()) {
        action_code = std::atoi(it->second.c_str());
    }

    RobotState target_state = (action_code == 15) ? RobotState::UNLOADING : RobotState::LOADING;
    RobotState current = ctx.state_machine->getCurrentState();

    if (current == RobotState::IDLE) {
        if (!ctx.state_machine->transitionTo(target_state)) {
            return BTStatus::FAILURE;
        }
        ctx.attachment_done = false;
        return BTStatus::RUNNING;
    }

    if (current == target_state) {
        if (ctx.attachment_done) {
            ctx.state_machine->transitionTo(RobotState::IDLE);
            if (action_code == 14) {
                ctx.cargo_secured = true;  // loaded
            } else {
                ctx.cargo_secured = false; // unloaded
            }
            return BTStatus::SUCCESS;
        }
        return BTStatus::RUNNING;
    }

    return BTStatus::FAILURE;
}

// ── ReportTaskComplete ─────────────────────────────────

BTStatus actionReportTaskComplete(BTRobotContext& ctx, const BTParams& /*params*/) {
    ctx.current_task_id.clear();
    ctx.task_available = false;
    ctx.cargo_secured = false;
    return BTStatus::SUCCESS;
}

// ── SendActionCode ─────────────────────────────────────

BTStatus actionSendActionCode(BTRobotContext& ctx, const BTParams& params) {
    // For reset_errors (31) and hard_reset (51)
    int action_code = 0;
    auto it = params.find("action_code");
    if (it != params.end()) {
        action_code = std::atoi(it->second.c_str());
    }

    if (action_code == 31 || action_code == 51) {
        // Reset: transition ERROR→IDLE
        if (ctx.state_machine &&
            ctx.state_machine->getCurrentState() == RobotState::ERROR)
        {
            if (ctx.state_machine->transitionTo(RobotState::IDLE)) {
                ctx.has_errors = false;
                return BTStatus::SUCCESS;
            }
        }
        // If not in ERROR state, just clear error flags
        ctx.has_errors = false;
        return BTStatus::SUCCESS;
    }

    return BTStatus::SUCCESS;
}

// ── WaitSeconds ────────────────────────────────────────

BTStatus actionWaitSeconds(BTRobotContext& ctx, const BTParams& params) {
    double target_s = 2.0;
    auto it = params.find("seconds");
    if (it != params.end()) {
        target_s = std::atof(it->second.c_str());
    }

    if (ctx.wait_elapsed_s >= target_s) {
        ctx.wait_elapsed_s = 0.0;
        return BTStatus::SUCCESS;
    }
    return BTStatus::RUNNING;
}

// ── WaitUntilCharged ───────────────────────────────────

BTStatus actionWaitUntilCharged(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.battery) return BTStatus::SUCCESS;

    double target_pct = 95.0;
    auto it = params.find("target_pct");
    if (it != params.end()) {
        target_pct = std::atof(it->second.c_str());
    }

    if (ctx.battery->getPercentage() >= target_pct) {
        return BTStatus::SUCCESS;
    }
    return BTStatus::RUNNING;
}

// ── AcceptTask ─────────────────────────────────────────

BTStatus actionAcceptTask(BTRobotContext& ctx, const BTParams& params) {
    if (!ctx.task_available) {
        return BTStatus::FAILURE;
    }

    auto it = params.find("task_id");
    if (it != params.end()) {
        ctx.current_task_id = it->second;
    }
    return BTStatus::SUCCESS;
}

// ── AlignAtStation ─────────────────────────────────────

BTStatus actionAlignAtStation(BTRobotContext& /*ctx*/, const BTParams& /*params*/) {
    // In simulation, alignment is instantaneous
    return BTStatus::SUCCESS;
}

// ── Register all standard actions ──────────────────────

void registerStandardActions(BTEngine& engine, BTRobotContext& ctx) {
    engine.registerAction("NavigateToNode",
        [&ctx](const BTParams& p) { return actionNavigateToNode(ctx, p); });

    engine.registerAction("DockAtCharger",
        [&ctx](const BTParams& p) { return actionDockAtCharger(ctx, p); });

    engine.registerAction("StartCharging",
        [&ctx](const BTParams& p) { return actionStartCharging(ctx, p); });

    engine.registerAction("UndockFromCharger",
        [&ctx](const BTParams& p) { return actionUndockFromCharger(ctx, p); });

    engine.registerAction("ExecuteAttachment",
        [&ctx](const BTParams& p) { return actionExecuteAttachment(ctx, p); });

    engine.registerAction("ReportTaskComplete",
        [&ctx](const BTParams& p) { return actionReportTaskComplete(ctx, p); });

    engine.registerAction("SendActionCode",
        [&ctx](const BTParams& p) { return actionSendActionCode(ctx, p); });

    engine.registerAction("WaitSeconds",
        [&ctx](const BTParams& p) { return actionWaitSeconds(ctx, p); });

    engine.registerAction("WaitUntilCharged",
        [&ctx](const BTParams& p) { return actionWaitUntilCharged(ctx, p); });

    engine.registerAction("AcceptTask",
        [&ctx](const BTParams& p) { return actionAcceptTask(ctx, p); });

    engine.registerAction("AlignAtStation",
        [&ctx](const BTParams& p) { return actionAlignAtStation(ctx, p); });
}

} // namespace rdt

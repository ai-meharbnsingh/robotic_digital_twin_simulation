#pragma once

// ──────────────────────────────────────────────────────────
// rdt/robot/RobotState.h — Robot state machine with validated
//                          transitions.
//
// Valid transitions:
//   IDLE      → MOVING, CHARGING, DOCKING
//   MOVING    → IDLE, ERROR
//   CHARGING  → IDLE
//   LOADING   → IDLE
//   UNLOADING → IDLE
//   ERROR     → IDLE (via reset)
//   DOCKING   → IDLE, CHARGING
//   OFFLINE   → IDLE
//
// Invalid transitions are rejected (transitionTo returns false).
// ──────────────────────────────────────────────────────────

#include "rdt/core/Types.h"
#include "rdt/core/Config.h"

#include <string>

namespace rdt {

class RobotStateMachine {
public:
    /// Construct with robot configuration.
    /// Initial state is IDLE.
    explicit RobotStateMachine(const RobotConfig& config);

    /// Attempt a state transition.
    /// @return true if the transition was valid and executed, false otherwise.
    bool transitionTo(RobotState new_state);

    /// Get the current robot state.
    RobotState getCurrentState() const;

    /// Get the name of the current state as a string.
    std::string getCurrentStateString() const;

private:
    /// Check whether transitioning from `from` to `to` is permitted.
    static bool isValidTransition(RobotState from, RobotState to);

    RobotConfig config_;
    RobotState  current_state_;
};

} // namespace rdt

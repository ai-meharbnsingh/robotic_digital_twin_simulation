// ──────────────────────────────────────────────────────────
// robot/RobotState.cpp — Robot state machine implementation
// ──────────────────────────────────────────────────────────

#include "rdt/robot/RobotState.h"

namespace rdt {

RobotStateMachine::RobotStateMachine(const RobotConfig& config)
    : config_(config)
    , current_state_(RobotState::IDLE)
{
}

bool RobotStateMachine::transitionTo(RobotState new_state) {
    if (new_state == current_state_) {
        return false; // no self-transitions
    }
    if (!isValidTransition(current_state_, new_state)) {
        return false;
    }
    current_state_ = new_state;
    return true;
}

RobotState RobotStateMachine::getCurrentState() const {
    return current_state_;
}

std::string RobotStateMachine::getCurrentStateString() const {
    return robot_state_to_string(current_state_);
}

bool RobotStateMachine::isValidTransition(RobotState from, RobotState to) {
    switch (from) {
        case RobotState::IDLE:
            return to == RobotState::MOVING   ||
                   to == RobotState::CHARGING ||
                   to == RobotState::DOCKING  ||
                   to == RobotState::LOADING  ||
                   to == RobotState::UNLOADING;

        case RobotState::MOVING:
            return to == RobotState::IDLE  ||
                   to == RobotState::ERROR;

        case RobotState::CHARGING:
            return to == RobotState::IDLE;

        case RobotState::LOADING:
            return to == RobotState::IDLE;

        case RobotState::UNLOADING:
            return to == RobotState::IDLE;

        case RobotState::ERROR:
            return to == RobotState::IDLE; // via reset

        case RobotState::DOCKING:
            return to == RobotState::IDLE    ||
                   to == RobotState::CHARGING;

        case RobotState::OFFLINE:
            return to == RobotState::IDLE;

        default:
            return false;
    }
}

} // namespace rdt

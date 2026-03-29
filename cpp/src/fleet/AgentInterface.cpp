// ──────────────────────────────────────────────────────────
// AgentInterface.cpp — Per-robot tracking implementation
// ──────────────────────────────────────────────────────────

#include "rdt/fleet/AgentInterface.h"

namespace rdt {
namespace fleet {

AgentInterface::AgentInterface(const std::string& robot_id,
                               const RobotConfig& config)
    : id_(robot_id), config_(config) {}

double AgentInterface::batteryPct() const {
    return last_telemetry_.battery_pct;
}

bool AgentInterface::isCriticalBattery() const {
    return batteryPct() < static_cast<double>(config_.battery.critical_threshold_pct);
}

RobotState AgentInterface::currentState() const {
    return last_telemetry_.state;
}

bool AgentInterface::isAvailable() const {
    auto st = currentState();
    return st == RobotState::IDLE || st == RobotState::STANDBY;
}

void AgentInterface::assignTask(uint64_t task_id,
                                 const std::vector<std::string>& path) {
    current_task_id_ = task_id;
    planned_path_ = path;
    path_index_ = 0;
}

void AgentInterface::clearTask() {
    current_task_id_ = 0;
    planned_path_.clear();
    path_index_ = 0;
}

void AgentInterface::advancePath() {
    if (path_index_ < planned_path_.size()) {
        ++path_index_;
    }
}

void AgentInterface::updateFromTelemetry(const network::ProtocolV1Message& msg) {
    last_telemetry_ = msg;
    telemetry_fresh_ = true;
    pose_.x = msg.x;
    pose_.y = msg.y;
    pose_.theta = msg.theta;
    velocity_.linear = msg.linear_velocity;
    velocity_.angular = msg.angular_velocity;
    current_node_ = msg.node_id;
}

Json::Value AgentInterface::toJson() const {
    Json::Value j;
    j["robot_id"] = id_;
    j["state"] = static_cast<int>(currentState());
    j["battery_pct"] = batteryPct();
    j["critical_battery"] = isCriticalBattery();
    j["available"] = isAvailable();

    Json::Value jp;
    jp["x"] = pose_.x;
    jp["y"] = pose_.y;
    jp["theta"] = pose_.theta;
    j["pose"] = jp;

    Json::Value jv;
    jv["linear"] = velocity_.linear;
    jv["angular"] = velocity_.angular;
    j["velocity"] = jv;

    j["current_node"] = current_node_;
    j["current_task_id"] = static_cast<Json::UInt64>(current_task_id_);
    j["has_path"] = hasPath();
    j["telemetry_fresh"] = telemetry_fresh_;
    return j;
}

}  // namespace fleet
}  // namespace rdt

// ──────────────────────────────────────────────────────────
// rdt/fleet/AgentInterface.h — Per-robot tracking interface
//
// Wraps AgentState with query/mutation methods so callers
// don't reach into struct internals.  FleetManager owns
// AgentInterface instances (one per robot).
// ──────────────────────────────────────────────────────────
#pragma once

#include <string>
#include <vector>
#include <cstdint>

#include "rdt/core/Types.h"
#include "rdt/core/Config.h"
#include "rdt/robot/RobotState.h"
#include "rdt/robot/BatteryModel.h"
#include "rdt/network/ProtocolV1.h"

#include <json/json.h>

namespace rdt {
namespace fleet {

/// Per-robot abstraction — owns subsystems and exposes a
/// clean query/mutation surface for FleetManager.
class AgentInterface {
public:
    explicit AgentInterface(const std::string& robot_id,
                            const RobotConfig& config);

    // ── Identity ──────────────────────────────────────────
    const std::string& id() const { return id_; }
    const RobotConfig& config() const { return config_; }

    // ── Pose & motion ─────────────────────────────────────
    const Pose&     pose()     const { return pose_; }
    const Velocity& velocity() const { return velocity_; }
    const std::string& currentNode() const { return current_node_; }
    void setPose(const Pose& p) { pose_ = p; }
    void setVelocity(const Velocity& v) { velocity_ = v; }
    void setCurrentNode(const std::string& n) { current_node_ = n; }

    // ── Battery ───────────────────────────────────────────
    double batteryPct() const;
    bool   isCriticalBattery() const;

    // ── State ─────────────────────────────────────────────
    RobotState currentState() const;
    bool isAvailable() const;

    // ── Task ──────────────────────────────────────────────
    uint64_t currentTaskId() const { return current_task_id_; }
    void assignTask(uint64_t task_id, const std::vector<std::string>& path);
    void clearTask();
    void advancePath();
    bool hasPath() const { return !planned_path_.empty() && path_index_ < planned_path_.size(); }

    // ── Telemetry ─────────────────────────────────────────
    void updateFromTelemetry(const network::ProtocolV1Message& msg);
    bool hasFreshTelemetry() const { return telemetry_fresh_; }
    void clearTelemetryFlag() { telemetry_fresh_ = false; }

    // ── Serialization ─────────────────────────────────────
    Json::Value toJson() const;

private:
    std::string  id_;
    RobotConfig  config_;
    Pose         pose_;
    Velocity     velocity_;
    std::string  current_node_;

    std::vector<std::string> planned_path_;
    size_t       path_index_ = 0;
    uint64_t     current_task_id_ = 0;

    network::ProtocolV1Message last_telemetry_;
    bool         telemetry_fresh_ = false;
};

}  // namespace fleet
}  // namespace rdt

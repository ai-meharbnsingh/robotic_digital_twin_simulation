#pragma once

// ──────────────────────────────────────────────────────────
// rdt/fleet/FleetManager.h — The 15Hz orchestration loop
//
// Ties together ALL Phase 1-6 components:
//   - GraphMap (navigation)
//   - AStar (pathfinding)
//   - NodeReservation (conflict prevention)
//   - RobotStateMachine (state tracking)
//   - BatteryModel (energy)
//   - MotionController (velocity)
//   - BTEngine (behavior trees)
//   - TCPServer (robot comms)
//   - RESTServer (HTTP API)
//   - Timer (15Hz enforcement)
//   - TaskManager (task allocation)
//   - COPPController (cooperative paths)
//
// The main loop (67ms budget per cycle):
//   a. Process incoming TCP messages (ProtocolV1)
//   b. Update RobotStateMachine states from telemetry
//   c. Tick behavior trees for each robot
//   d. Allocate tasks via TaskManager
//   e. Plan paths via COPPController (A* + reservation)
//   f. Send commands to robots via TCP
//   g. Write state to JSON file (MongoDB deferred)
//   h. Log timing per cycle
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <unordered_map>
#include <atomic>
#include <mutex>
#include <memory>
#include <thread>
#include <fstream>

#include "rdt/core/Types.h"
#include "rdt/core/Config.h"
#include "rdt/core/Timer.h"
#include "rdt/core/Logger.h"
#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/AStar.h"
#include "rdt/navigation/NodeReservation.h"
#include "rdt/robot/RobotState.h"
#include "rdt/robot/BatteryModel.h"
#include "rdt/robot/MotionController.h"
#include "rdt/robot/ObstacleHandler.h"
#include "rdt/behavior/BTEngine.h"
#include "rdt/behavior/ActionNodes.h"
#include "rdt/behavior/ConditionNodes.h"
#include "rdt/network/TCPServer.h"
#include "rdt/network/RESTServer.h"
#include "rdt/network/ProtocolV1.h"
#include "rdt/fleet/TaskManager.h"
#include "rdt/fleet/COPPController.h"

namespace rdt {
namespace fleet {

/// Per-robot runtime state aggregated by FleetManager.
struct AgentState {
    std::string                        id;
    RobotConfig                        config;
    std::unique_ptr<RobotStateMachine> state_machine;
    std::unique_ptr<BatteryModel>      battery;
    std::unique_ptr<MotionController>  motion;
    std::unique_ptr<ObstacleHandler>   obstacles;
    std::unique_ptr<BTEngine>          behavior_tree;
    std::unique_ptr<BTRobotContext>    bt_context;

    // Current position tracking
    Pose                               pose;
    Velocity                           velocity;
    std::string                        current_node;

    // Path tracking
    std::vector<std::string>           planned_path;
    size_t                             path_index = 0;

    // Task tracking
    uint64_t                           current_task_id = 0;

    // Telemetry (last received from TCP)
    network::ProtocolV1Message         last_telemetry;
    bool                               telemetry_fresh = false;
};

/// Timing metrics for one main loop cycle.
struct CycleTiming {
    double total_ms       = 0.0;
    double tcp_process_ms = 0.0;
    double state_update_ms = 0.0;
    double bt_tick_ms     = 0.0;
    double allocation_ms  = 0.0;
    double path_plan_ms   = 0.0;
    double command_ms     = 0.0;
    double write_ms       = 0.0;
    uint64_t cycle_number = 0;
};

class FleetManager {
public:
    /// Target frequency for the main loop.
    static constexpr double TARGET_HZ = 15.0;
    static constexpr double CYCLE_MS  = 1000.0 / TARGET_HZ;  // ~66.67ms

    /// Construct with warehouse and robot configurations.
    FleetManager(const WarehouseConfig& warehouse_config,
                 const std::vector<RobotConfig>& robot_configs);
    ~FleetManager();

    // Non-copyable, non-movable.
    FleetManager(const FleetManager&) = delete;
    FleetManager& operator=(const FleetManager&) = delete;

    /// Initialize all subsystems: graph, robots, TCP, REST, BT engines.
    /// @param tcp_port   Port for robot TCP connections (default 7010)
    /// @param rest_port  Port for REST API (default 7012)
    /// @param state_file Path for JSON state output (default "fleet_state.json")
    /// @return true if all subsystems initialized successfully
    bool init(uint16_t tcp_port = 7010,
              uint16_t rest_port = 7012,
              const std::string& state_file = "fleet_state.json");

    /// Start the 15Hz main loop. Blocks until stop() is called.
    void run();

    /// Signal the main loop to stop. Thread-safe.
    void stop();

    /// Whether the main loop is currently running.
    bool isRunning() const;

    /// Get the TaskManager (for external task submission).
    TaskManager& getTaskManager();

    /// Get the latest cycle timing.
    CycleTiming getLastCycleTiming() const;

    /// Get the total number of cycles executed.
    uint64_t getCycleCount() const;

    /// Get the number of robots in the fleet.
    size_t getRobotCount() const;

    /// Get a snapshot of robot states for REST API / status.
    Json::Value getFleetStatusJson() const;

    /// Run exactly one cycle of the main loop (for testing).
    /// Requires init() to have been called.
    CycleTiming runOneCycle();

private:
    // ── Main loop steps ──
    void processTcpMessages();
    void updateRobotStates(double dt_seconds);
    void tickBehaviorTrees();
    void allocateTasks();
    void planPaths();
    void sendCommands();
    void writeState();

    // ── Setup helpers ──
    void setupRobot(const RobotConfig& config);
    void setupRestRoutes();
    void handleTcpMessage(const std::string& robot_id, const std::string& raw);

    // ── Config ──
    WarehouseConfig warehouse_config_;
    std::vector<RobotConfig> robot_configs_;
    std::string state_file_path_;

    // ── Subsystems ──
    GraphMap graph_;
    nav::NodeReservation reservations_;
    TaskManager task_manager_;
    COPPController copp_;
    core::Timer timer_;

    // ── Network ──
    std::unique_ptr<network::TCPServer>  tcp_server_;
    std::unique_ptr<network::RESTServer> rest_server_;

    // ── Robots ──
    mutable std::mutex agents_mutex_;
    std::unordered_map<std::string, std::unique_ptr<AgentState>> agents_;

    // ── Incoming message queue ──
    mutable std::mutex msg_mutex_;
    std::vector<std::pair<std::string, std::string>> incoming_messages_;

    // ── Run state ──
    std::atomic<bool> running_{false};
    std::atomic<uint64_t> cycle_count_{0};
    mutable std::mutex timing_mutex_;
    CycleTiming last_timing_;
};

}  // namespace fleet
}  // namespace rdt

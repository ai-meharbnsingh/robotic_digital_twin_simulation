// ──────────────────────────────────────────────────────────
// rdt/fleet/FleetManager.cpp — The 15Hz orchestration loop
//
// Ties together ALL Phase 1-6 components into a single
// deterministic cycle that runs at 15Hz (67ms budget).
// ──────────────────────────────────────────────────────────

#include "rdt/fleet/FleetManager.h"
#include "rdt/core/Logger.h"

#include <json/json.h>
#include <chrono>
#include <fstream>
#include <sstream>

namespace rdt {
namespace fleet {

FleetManager::FleetManager(const WarehouseConfig& warehouse_config,
                           const std::vector<RobotConfig>& robot_configs)
    : warehouse_config_(warehouse_config)
    , robot_configs_(robot_configs) {
}

FleetManager::~FleetManager() {
    stop();
}

bool FleetManager::init(uint16_t tcp_port,
                        uint16_t rest_port,
                        const std::string& state_file) {
    state_file_path_ = state_file;

    // 1. Build navigation graph from warehouse config
    graph_.loadFromConfig(warehouse_config_);
    RDT_LOG_INFO("FleetManager: loaded graph with {} nodes, {} edges",
                 graph_.nodeCount(), graph_.edgeCount());

    // 2. Initialize each robot
    for (const auto& rc : robot_configs_) {
        setupRobot(rc);
    }
    RDT_LOG_INFO("FleetManager: initialized {} robots", agents_.size());

    // 3. Start TCP server for robot communication
    tcp_server_ = std::make_unique<network::TCPServer>();
    tcp_server_->onMessage([this](const std::string& robot_id,
                                  const std::string& raw) {
        handleTcpMessage(robot_id, raw);
    });
    tcp_server_->start(tcp_port);
    RDT_LOG_INFO("FleetManager: TCP server started on port {}", tcp_port);

    // 4. Start REST server with fleet status routes
    rest_server_ = std::make_unique<network::RESTServer>();
    setupRestRoutes();
    rest_server_->start(rest_port);
    RDT_LOG_INFO("FleetManager: REST server started on port {}", rest_port);

    return true;
}

void FleetManager::run() {
    running_ = true;
    RDT_LOG_INFO("FleetManager: starting 15Hz main loop");

    while (running_) {
        runOneCycle();
        timer_.sleep_until_next(CYCLE_MS);
    }

    RDT_LOG_INFO("FleetManager: main loop stopped after {} cycles", cycle_count_.load());
}

void FleetManager::stop() {
    bool was_running = running_.exchange(false);

    // Always shut down servers even if run() was never called,
    // since init() starts TCP and REST servers independently.
    if (tcp_server_) tcp_server_->stop();
    if (rest_server_) rest_server_->stop();

    if (was_running) {
        RDT_LOG_INFO("FleetManager: shutdown complete (was running)");
    } else {
        RDT_LOG_INFO("FleetManager: shutdown complete (servers cleaned up)");
    }
}

bool FleetManager::isRunning() const {
    return running_;
}

TaskManager& FleetManager::getTaskManager() {
    return task_manager_;
}

CycleTiming FleetManager::getLastCycleTiming() const {
    std::lock_guard<std::mutex> lock(timing_mutex_);
    return last_timing_;
}

uint64_t FleetManager::getCycleCount() const {
    return cycle_count_;
}

size_t FleetManager::getRobotCount() const {
    std::lock_guard<std::mutex> lock(agents_mutex_);
    return agents_.size();
}

CycleTiming FleetManager::runOneCycle() {
    CycleTiming timing;
    timing.cycle_number = cycle_count_++;

    timer_.tick();
    auto cycle_start = std::chrono::steady_clock::now();

    // Step a: Process incoming TCP messages
    auto step_start = std::chrono::steady_clock::now();
    processTcpMessages();
    auto step_end = std::chrono::steady_clock::now();
    timing.tcp_process_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step b: Update robot states from telemetry
    step_start = std::chrono::steady_clock::now();
    double dt = CYCLE_MS / 1000.0;  // ~0.067 seconds
    updateRobotStates(dt);
    step_end = std::chrono::steady_clock::now();
    timing.state_update_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step c: Tick behavior trees
    step_start = std::chrono::steady_clock::now();
    tickBehaviorTrees();
    step_end = std::chrono::steady_clock::now();
    timing.bt_tick_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step d: Allocate tasks
    step_start = std::chrono::steady_clock::now();
    allocateTasks();
    step_end = std::chrono::steady_clock::now();
    timing.allocation_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step e: Plan paths
    step_start = std::chrono::steady_clock::now();
    planPaths();
    step_end = std::chrono::steady_clock::now();
    timing.path_plan_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step f: Send commands
    step_start = std::chrono::steady_clock::now();
    sendCommands();
    step_end = std::chrono::steady_clock::now();
    timing.command_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Step g: Write state
    step_start = std::chrono::steady_clock::now();
    writeState();
    step_end = std::chrono::steady_clock::now();
    timing.write_ms = std::chrono::duration<double, std::milli>(step_end - step_start).count();

    // Total cycle time
    auto cycle_end = std::chrono::steady_clock::now();
    timing.total_ms = std::chrono::duration<double, std::milli>(cycle_end - cycle_start).count();

    // Store timing
    {
        std::lock_guard<std::mutex> lock(timing_mutex_);
        last_timing_ = timing;
    }

    // Log timing every 150 cycles (~10 seconds)
    if (timing.cycle_number % 150 == 0) {
        RDT_LOG_INFO("FleetManager: cycle={} total={:.2f}ms [tcp={:.2f} state={:.2f} bt={:.2f} "
                     "alloc={:.2f} path={:.2f} cmd={:.2f} write={:.2f}]",
                     timing.cycle_number, timing.total_ms,
                     timing.tcp_process_ms, timing.state_update_ms, timing.bt_tick_ms,
                     timing.allocation_ms, timing.path_plan_ms,
                     timing.command_ms, timing.write_ms);
    }

    return timing;
}

// ── Main loop steps ──────────────────────────────────────

void FleetManager::processTcpMessages() {
    std::vector<std::pair<std::string, std::string>> messages;
    {
        std::lock_guard<std::mutex> lock(msg_mutex_);
        messages.swap(incoming_messages_);
    }

    std::lock_guard<std::mutex> lock(agents_mutex_);
    for (const auto& [robot_id, raw] : messages) {
        auto parsed = network::parse(raw);
        if (!parsed) {
            RDT_LOG_WARN("FleetManager: failed to parse message from {}", robot_id);
            continue;
        }

        if (!network::validateCRC32(*parsed)) {
            RDT_LOG_WARN("FleetManager: CRC32 mismatch from {}", robot_id);
            continue;
        }

        // Find or identify the robot by the ID in the message
        std::string id = parsed->robot_id.empty() ? robot_id : parsed->robot_id;
        auto it = agents_.find(id);
        if (it != agents_.end()) {
            it->second->last_telemetry  = *parsed;
            it->second->telemetry_fresh = true;
        }
    }
}

void FleetManager::updateRobotStates(double dt_seconds) {
    std::lock_guard<std::mutex> lock(agents_mutex_);

    for (auto& [id, agent] : agents_) {
        if (agent->telemetry_fresh) {
            // Update pose from telemetry
            agent->pose.x   = agent->last_telemetry.x;
            agent->pose.y   = agent->last_telemetry.y;
            agent->pose.yaw = agent->last_telemetry.theta;

            // Update velocity
            agent->velocity.linear  = agent->last_telemetry.linear_vel;
            agent->velocity.angular = agent->last_telemetry.angular_vel;

            agent->telemetry_fresh = false;
        }

        // Update battery model
        bool is_moving = agent->state_machine->getCurrentState() == RobotState::MOVING;
        bool is_attachment = false;  // TODO: track from telemetry
        agent->battery->update(dt_seconds, is_moving, is_attachment);

        // Update BT context
        if (agent->bt_context) {
            agent->bt_context->task_available =
                (agent->current_task_id != 0);
        }
    }
}

void FleetManager::tickBehaviorTrees() {
    std::lock_guard<std::mutex> lock(agents_mutex_);

    for (auto& [id, agent] : agents_) {
        if (agent->behavior_tree && agent->behavior_tree->isLoaded()) {
            agent->behavior_tree->tick();
        }
    }
}

void FleetManager::allocateTasks() {
    // Build allocation info from current robot states
    std::vector<RobotAllocationInfo> infos;
    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        for (const auto& [id, agent] : agents_) {
            RobotAllocationInfo info;
            info.id           = id;
            info.state        = agent->state_machine->getCurrentState();
            info.type         = agent->config.type;
            info.battery_pct  = agent->battery->getPercentage();
            info.critical_pct = static_cast<double>(agent->config.battery.critical_threshold_pct);
            info.current_node = agent->current_node;
            infos.push_back(info);
        }
    }

    // Try to allocate next pending task
    auto result = task_manager_.allocateNext(infos, graph_, reservations_);
    if (result) {
        auto [task_id, robot_id] = *result;

        std::lock_guard<std::mutex> lock(agents_mutex_);
        auto it = agents_.find(robot_id);
        if (it != agents_.end()) {
            it->second->current_task_id = task_id;
            if (it->second->bt_context) {
                it->second->bt_context->task_available   = true;
                it->second->bt_context->current_task_id  = std::to_string(task_id);
            }
        }
    }
}

void FleetManager::planPaths() {
    std::vector<PlanRequest> requests;

    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        for (const auto& [id, agent] : agents_) {
            // Only plan for robots that have a task and no current path
            if (agent->current_task_id == 0) continue;
            if (!agent->planned_path.empty()) continue;

            auto task = task_manager_.getTask(agent->current_task_id);
            if (!task) continue;

            PlanRequest req;
            req.robot_id   = id;
            req.start_node = agent->current_node.empty()
                                 ? task->source_node
                                 : agent->current_node;
            req.goal_node  = task->dest_node;
            req.priority   = task->priority;
            requests.push_back(req);
        }
    }

    if (requests.empty()) return;

    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);

    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        for (const auto& [robot_id, plan] : results) {
            if (!plan.success) continue;

            auto it = agents_.find(robot_id);
            if (it != agents_.end()) {
                it->second->planned_path = plan.path;
                it->second->path_index   = 0;
            }
        }
    }
}

void FleetManager::sendCommands() {
    std::lock_guard<std::mutex> lock(agents_mutex_);

    for (const auto& [id, agent] : agents_) {
        if (agent->planned_path.empty()) continue;
        if (agent->path_index >= agent->planned_path.size()) continue;

        // Build a command message pointing to the next node
        const std::string& next_node = agent->planned_path[agent->path_index];

        if (graph_.hasNode(next_node)) {
            const auto& node = graph_.getNode(next_node);
            network::ProtocolV1Message cmd;
            cmd.robot_id = id;
            cmd.x        = node.x;
            cmd.y        = node.y;
            cmd.state    = "COMMAND_MOVE";

            std::string serialized = network::serialize(cmd);

            if (tcp_server_ && tcp_server_->isRunning()) {
                tcp_server_->sendToRobot(id, serialized);
            }
        }
    }
}

void FleetManager::writeState() {
    if (state_file_path_.empty()) return;

    Json::Value root = getFleetStatusJson();

    Json::StreamWriterBuilder builder;
    builder["indentation"] = "  ";
    std::string json_str = Json::writeString(builder, root);

    std::ofstream out(state_file_path_);
    if (out.is_open()) {
        out << json_str;
    }
}

// ── Setup helpers ────────────────────────────────────────

void FleetManager::setupRobot(const RobotConfig& config) {
    auto agent = std::make_unique<AgentState>();
    agent->id     = config.name;
    agent->config = config;

    // Create subsystems
    agent->state_machine = std::make_unique<RobotStateMachine>(config);
    agent->battery       = std::make_unique<BatteryModel>(config);
    agent->motion        = std::make_unique<MotionController>(config);
    agent->obstacles     = std::make_unique<ObstacleHandler>(config);

    // Create behavior tree engine
    agent->behavior_tree = std::make_unique<BTEngine>();
    agent->bt_context    = std::make_unique<BTRobotContext>();
    agent->bt_context->state_machine = agent->state_machine.get();
    agent->bt_context->battery       = agent->battery.get();
    agent->bt_context->obstacles     = agent->obstacles.get();

    registerStandardActions(*agent->behavior_tree, *agent->bt_context);
    registerStandardConditions(*agent->behavior_tree, *agent->bt_context);

    // Set initial node to first dock if available
    if (!warehouse_config_.zones.empty()) {
        for (const auto& zone : warehouse_config_.zones) {
            if (zone.type == "dock" && !zone.nodes.empty()) {
                agent->current_node = zone.nodes[0];
                break;
            }
        }
    }

    std::string robot_id = config.name;
    agents_[robot_id] = std::move(agent);
}

void FleetManager::setupRestRoutes() {
    // GET /health
    rest_server_->addRoute("GET", "/health",
        [](const network::HTTPRequest&) -> network::HTTPResponse {
            return {200, "OK", "application/json", R"({"status":"ok","service":"fms"})"};
        });

    // GET /api/fleet/status
    rest_server_->addRoute("GET", "/api/fleet/status",
        [this](const network::HTTPRequest&) -> network::HTTPResponse {
            Json::Value status = getFleetStatusJson();
            Json::StreamWriterBuilder builder;
            builder["indentation"] = "";
            std::string body = Json::writeString(builder, status);
            return {200, "OK", "application/json", body};
        });

    // GET /api/robots
    rest_server_->addRoute("GET", "/api/robots",
        [this](const network::HTTPRequest&) -> network::HTTPResponse {
            Json::Value robots(Json::arrayValue);
            std::lock_guard<std::mutex> lock(agents_mutex_);
            for (const auto& [id, agent] : agents_) {
                Json::Value r;
                r["id"]         = id;
                r["robot_type"] = robot_type_to_string(agent->config.type);
                r["state"]      = agent->state_machine->getCurrentStateString();
                r["battery"]    = agent->battery->getPercentage();
                r["pose"]       = to_json(agent->pose);
                robots.append(r);
            }
            Json::StreamWriterBuilder builder;
            builder["indentation"] = "";
            return {200, "OK", "application/json", Json::writeString(builder, robots)};
        });

    // GET /api/tasks
    rest_server_->addRoute("GET", "/api/tasks",
        [this](const network::HTTPRequest&) -> network::HTTPResponse {
            auto tasks = task_manager_.getAllTasks();
            Json::Value arr(Json::arrayValue);
            for (const auto& t : tasks) {
                Json::Value j;
                j["id"]       = static_cast<Json::UInt64>(t.id);
                j["type"]     = task_type_to_string(t.type);
                j["source"]   = t.source_node;
                j["dest"]     = t.dest_node;
                j["priority"] = t.priority;
                j["state"]    = task_state_to_string(t.state);
                j["robot"]    = t.assigned_robot;
                arr.append(j);
            }
            Json::StreamWriterBuilder builder;
            builder["indentation"] = "";
            return {200, "OK", "application/json", Json::writeString(builder, arr)};
        });
}

void FleetManager::handleTcpMessage(const std::string& robot_id,
                                     const std::string& raw) {
    std::lock_guard<std::mutex> lock(msg_mutex_);
    incoming_messages_.emplace_back(robot_id, raw);
}

Json::Value FleetManager::getFleetStatusJson() const {
    Json::Value root;

    root["cycle_count"] = static_cast<Json::UInt64>(cycle_count_.load());
    root["running"]     = running_.load();
    root["robot_count"] = static_cast<Json::UInt>(getRobotCount());

    // Timing
    CycleTiming t = getLastCycleTiming();
    Json::Value timing;
    timing["total_ms"]        = t.total_ms;
    timing["tcp_process_ms"]  = t.tcp_process_ms;
    timing["state_update_ms"] = t.state_update_ms;
    timing["bt_tick_ms"]      = t.bt_tick_ms;
    timing["allocation_ms"]   = t.allocation_ms;
    timing["path_plan_ms"]    = t.path_plan_ms;
    timing["command_ms"]      = t.command_ms;
    timing["write_ms"]        = t.write_ms;
    root["timing"] = timing;

    // Tasks summary
    Json::Value tasks;
    tasks["pending"]   = static_cast<Json::UInt>(task_manager_.getPendingCount());
    tasks["active"]    = static_cast<Json::UInt>(task_manager_.getActiveCount());
    tasks["completed"] = static_cast<Json::UInt>(task_manager_.getCompletedCount());
    root["tasks"] = tasks;

    // Robots
    Json::Value robots(Json::arrayValue);
    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        for (const auto& [id, agent] : agents_) {
            Json::Value r;
            r["id"]           = id;
            r["robot_type"]   = robot_type_to_string(agent->config.type);
            r["state"]        = agent->state_machine->getCurrentStateString();
            r["battery_pct"]  = agent->battery->getPercentage();
            r["battery_v"]    = agent->battery->getVoltage();
            r["charging"]     = agent->battery->isCharging();
            r["critical"]     = agent->battery->isCritical();
            r["pose"]         = to_json(agent->pose);
            r["current_node"] = agent->current_node;
            r["task_id"]      = static_cast<Json::UInt64>(agent->current_task_id);
            r["path_length"]  = static_cast<Json::UInt>(agent->planned_path.size());
            robots.append(r);
        }
    }
    root["robots"] = robots;

    // Graph summary
    Json::Value graph;
    graph["nodes"] = static_cast<Json::UInt>(graph_.nodeCount());
    graph["edges"] = static_cast<Json::UInt>(graph_.edgeCount());
    root["graph"] = graph;

    // Reservations
    Json::Value res;
    res["robots"] = static_cast<Json::UInt>(reservations_.robotCount());
    res["nodes"]  = static_cast<Json::UInt>(reservations_.nodeCount());
    root["reservations"] = res;

    return root;
}

}  // namespace fleet
}  // namespace rdt

// ──────────────────────────────────────────────────────────
// test_fleet.cpp — Phase 7 tests for FleetManager, TaskManager,
//                  COPPController
//
// 20+ tests with REAL assertions. No assert-is-not-null.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>

#include "rdt/core/Config.h"
#include "rdt/core/Types.h"
#include "rdt/core/Logger.h"
#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/AStar.h"
#include "rdt/navigation/NodeReservation.h"
#include "rdt/fleet/TaskManager.h"
#include "rdt/fleet/COPPController.h"
#include "rdt/fleet/FleetManager.h"

#include <chrono>
#include <thread>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>


static bool can_bind_socket() {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;
    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = 0;
    int rc = ::bind(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
    ::close(fd);
    return rc == 0;
}

#define SKIP_IF_NO_SOCKETS() \
    if (!can_bind_socket()) { GTEST_SKIP() << "Socket binding restricted in this environment"; }

// ── Test fixtures ─────────────────────────────────────────

class TaskManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        rdt::core::Logger::init("warn");

        // Build a simple 5x5 grid graph
        wh_config_ = rdt::Config::loadWarehouseConfig(
            std::string(RDT_PROJECT_ROOT) + "/configs/warehouses/simple_grid.json");
        graph_.loadFromConfig(wh_config_);

        robot_config_ = rdt::Config::loadRobotConfig(
            std::string(RDT_PROJECT_ROOT) + "/configs/robots/differential_drive.yaml");
    }

    void TearDown() override {
        rdt::core::Logger::shutdown();
    }

    rdt::WarehouseConfig wh_config_;
    rdt::GraphMap graph_;
    rdt::RobotConfig robot_config_;
    rdt::nav::NodeReservation reservations_;
    rdt::fleet::TaskManager task_mgr_;

    rdt::fleet::RobotAllocationInfo makeIdleRobot(const std::string& id,
                                                    const std::string& node = "DOCK_1",
                                                    double battery = 80.0) {
        rdt::fleet::RobotAllocationInfo info;
        info.id           = id;
        info.state        = rdt::RobotState::IDLE;
        info.type         = rdt::RobotType::DIFFERENTIAL_DRIVE;
        info.battery_pct  = battery;
        info.critical_pct = 20.0;
        info.current_node = node;
        return info;
    }
};

class COPPTest : public ::testing::Test {
protected:
    void SetUp() override {
        rdt::core::Logger::init("warn");

        wh_config_ = rdt::Config::loadWarehouseConfig(
            std::string(RDT_PROJECT_ROOT) + "/configs/warehouses/simple_grid.json");
        graph_.loadFromConfig(wh_config_);
    }

    void TearDown() override {
        rdt::core::Logger::shutdown();
    }

    rdt::WarehouseConfig wh_config_;
    rdt::GraphMap graph_;
    rdt::nav::NodeReservation reservations_;
    rdt::fleet::COPPController copp_;
};

class FleetManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        rdt::core::Logger::init("warn");

        wh_config_ = rdt::Config::loadWarehouseConfig(
            std::string(RDT_PROJECT_ROOT) + "/configs/warehouses/simple_grid.json");
        robot_config_ = rdt::Config::loadRobotConfig(
            std::string(RDT_PROJECT_ROOT) + "/configs/robots/differential_drive.yaml");
    }

    void TearDown() override {
        rdt::core::Logger::shutdown();
    }

    rdt::WarehouseConfig wh_config_;
    rdt::RobotConfig robot_config_;
};

// ════════════════════════════════════════════════════════════
// TaskManager tests
// ════════════════════════════════════════════════════════════

TEST_F(TaskManagerTest, AddTaskReturnsIncrementingIds) {
    auto id1 = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1", 0);
    auto id2 = task_mgr_.addTask(rdt::TaskType::PICK, "PICK_1", "S_11", 1);
    auto id3 = task_mgr_.addTask(rdt::TaskType::PLACE, "S_11", "DROP_1", 0);

    EXPECT_EQ(id1, 1);
    EXPECT_EQ(id2, 2);
    EXPECT_EQ(id3, 3);
}

TEST_F(TaskManagerTest, AddTaskIncrementsPendingCount) {
    EXPECT_EQ(task_mgr_.getPendingCount(), 0);

    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");
    EXPECT_EQ(task_mgr_.getPendingCount(), 1);

    task_mgr_.addTask(rdt::TaskType::MOVE, "PICK_1", "DROP_1");
    EXPECT_EQ(task_mgr_.getPendingCount(), 2);
}

TEST_F(TaskManagerTest, GetTaskReturnsCorrectFields) {
    auto id = task_mgr_.addTask(rdt::TaskType::PICK, "PICK_1", "S_21", 5);

    auto task = task_mgr_.getTask(id);
    ASSERT_TRUE(task.has_value());
    EXPECT_EQ(task->id, id);
    EXPECT_EQ(task->type, rdt::TaskType::PICK);
    EXPECT_EQ(task->source_node, "PICK_1");
    EXPECT_EQ(task->dest_node, "S_21");
    EXPECT_EQ(task->priority, 5);
    EXPECT_EQ(task->state, rdt::TaskState::NOT_ASSIGNED);
    EXPECT_TRUE(task->assigned_robot.empty());
}

TEST_F(TaskManagerTest, GetTaskReturnsNulloptForInvalidId) {
    auto task = task_mgr_.getTask(999);
    EXPECT_FALSE(task.has_value());
}

TEST_F(TaskManagerTest, AllocateNextAssignsToIdleRobot) {
    auto task_id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};

    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);

    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->first, task_id);
    EXPECT_EQ(result->second, "R1");

    // Task should now be assigned
    auto task = task_mgr_.getTask(task_id);
    EXPECT_EQ(task->state, rdt::TaskState::ASSIGNED);
    EXPECT_EQ(task->assigned_robot, "R1");
}

TEST_F(TaskManagerTest, AllocateNextReturnsNulloptWhenNoPending) {
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, FIFOOrderByPriority) {
    // Low priority first, then high priority
    auto low_id  = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1", 1);
    auto high_id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "PICK_1", 10);

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);

    // High priority should be allocated first
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->first, high_id);

    // Second allocation should get the low priority task (need a new robot)
    std::vector<rdt::fleet::RobotAllocationInfo> robots2 = {makeIdleRobot("R2")};
    auto result2 = task_mgr_.allocateNext(robots2, graph_, reservations_);

    ASSERT_TRUE(result2.has_value());
    EXPECT_EQ(result2->first, low_id);
}

TEST_F(TaskManagerTest, FIFOOrderByAge) {
    // Same priority — older task first
    auto first_id  = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1", 5);
    auto second_id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "PICK_1", 5);

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);

    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->first, first_id);  // older task allocated first
}

TEST_F(TaskManagerTest, ValidationRejectsBatteryLow) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    // Robot with battery at critical level (15% < 20% threshold)
    auto robot = makeIdleRobot("R1", "DOCK_1", 15.0);
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {robot};

    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());  // Rejected: battery too low
}

TEST_F(TaskManagerTest, ValidationRejectsBatteryAtExactThreshold) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    // Battery exactly at critical threshold — should reject (<=, not <)
    auto robot = makeIdleRobot("R1", "DOCK_1", 20.0);
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {robot};

    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, ValidationRejectsNonIdleRobot) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    auto robot = makeIdleRobot("R1");
    robot.state = rdt::RobotState::MOVING;
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {robot};

    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, ValidationRejectsInvalidSourceNode) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "NONEXISTENT", "DROP_1");

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, ValidationRejectsInvalidDestNode) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "NONEXISTENT");

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, ValidationRejectsNodeConflict) {
    // Reserve path nodes for another robot
    std::vector<std::string> reserved_path = {"DOCK_1", "N_01", "N_02"};
    reservations_.reserve("OTHER_ROBOT", reserved_path);

    // Task goes through DOCK_1 → ... → DROP_1, but DOCK_1 is reserved
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, ValidationRejectsIncompatibleType) {
    // PICK task should not be assigned to UNIDIRECTIONAL robot
    task_mgr_.addTask(rdt::TaskType::PICK, "DOCK_1", "DROP_1");

    auto robot = makeIdleRobot("R1");
    robot.type = rdt::RobotType::UNIDIRECTIONAL;
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {robot};

    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, CompleteTaskChangesState) {
    auto id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    // Assign it first
    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    task_mgr_.allocateNext(robots, graph_, reservations_);

    bool completed = task_mgr_.completeTask(id);
    EXPECT_TRUE(completed);

    auto task = task_mgr_.getTask(id);
    EXPECT_EQ(task->state, rdt::TaskState::COMPLETED);
    EXPECT_EQ(task_mgr_.getCompletedCount(), 1);
    EXPECT_EQ(task_mgr_.getActiveCount(), 0);
}

TEST_F(TaskManagerTest, FailTaskChangesState) {
    auto id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {makeIdleRobot("R1")};
    task_mgr_.allocateNext(robots, graph_, reservations_);

    bool failed = task_mgr_.failTask(id);
    EXPECT_TRUE(failed);

    auto task = task_mgr_.getTask(id);
    EXPECT_EQ(task->state, rdt::TaskState::FAILED);
}

TEST_F(TaskManagerTest, CompleteUnassignedTaskFails) {
    auto id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");
    bool completed = task_mgr_.completeTask(id);
    EXPECT_FALSE(completed);  // Can't complete a NOT_ASSIGNED task
}

TEST_F(TaskManagerTest, GetAllTasksReturnsAll) {
    task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");
    task_mgr_.addTask(rdt::TaskType::PICK, "PICK_1", "S_11");
    task_mgr_.addTask(rdt::TaskType::CHARGE, "DOCK_1", "DOCK_2");

    auto all = task_mgr_.getAllTasks();
    EXPECT_EQ(all.size(), 3);
}

// ════════════════════════════════════════════════════════════
// COPPController tests
// ════════════════════════════════════════════════════════════

TEST_F(COPPTest, PlanSingleRobotPath) {
    std::vector<rdt::fleet::PlanRequest> requests = {
        {"R1", "DOCK_1", "DROP_1", 0}
    };

    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);

    ASSERT_EQ(results.size(), 1);
    ASSERT_TRUE(results.count("R1") > 0);
    EXPECT_TRUE(results["R1"].success);
    EXPECT_GT(results["R1"].path.size(), 1);
    EXPECT_EQ(results["R1"].path.front(), "DOCK_1");
    EXPECT_EQ(results["R1"].path.back(), "DROP_1");
    EXPECT_GT(results["R1"].distance, 0.0);
}

TEST_F(COPPTest, PlanTwoNonConflictingPaths) {
    // Two robots going to different destinations — no conflict
    std::vector<rdt::fleet::PlanRequest> requests = {
        {"R1", "DOCK_1", "PICK_1", 0},
        {"R2", "DOCK_2", "DROP_1", 0}
    };

    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);

    EXPECT_EQ(results.size(), 2);
    EXPECT_TRUE(results["R1"].success);
    EXPECT_TRUE(results["R2"].success);

    // Verify paths start and end correctly
    EXPECT_EQ(results["R1"].path.front(), "DOCK_1");
    EXPECT_EQ(results["R1"].path.back(), "PICK_1");
    EXPECT_EQ(results["R2"].path.front(), "DOCK_2");
    EXPECT_EQ(results["R2"].path.back(), "DROP_1");
}

TEST_F(COPPTest, HigherPriorityRobotPlansFirst) {
    // R1 = high priority, R2 = low priority, same start
    // R1 should get reserved first
    std::vector<rdt::fleet::PlanRequest> requests = {
        {"R_low", "DOCK_1", "DROP_1", 0},
        {"R_high", "DOCK_1", "PICK_1", 10}
    };

    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);

    EXPECT_EQ(results.size(), 2);
    EXPECT_TRUE(results["R_high"].success);
    // R_low may or may not succeed depending on conflicts, but R_high
    // should have planned first (0 replans since it goes first)
    EXPECT_EQ(results["R_high"].replans, 0);
}

TEST_F(COPPTest, EmptyRequestsReturnsEmpty) {
    std::vector<rdt::fleet::PlanRequest> requests;
    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);
    EXPECT_TRUE(results.empty());
}

TEST_F(COPPTest, InvalidGoalNodeFails) {
    std::vector<rdt::fleet::PlanRequest> requests = {
        {"R1", "DOCK_1", "NONEXISTENT", 0}
    };

    auto results = copp_.planCooperativePaths(requests, graph_, reservations_);
    EXPECT_EQ(results.size(), 1);
    EXPECT_FALSE(results["R1"].success);
}

// ════════════════════════════════════════════════════════════
// FleetManager tests
// ════════════════════════════════════════════════════════════

TEST_F(FleetManagerTest, ConstructsWithConfig) {
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    EXPECT_FALSE(fm.isRunning());
    EXPECT_EQ(fm.getCycleCount(), 0);
}

TEST_F(FleetManagerTest, InitCreatesRobots) {
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    // Use high ports to avoid conflicts
    bool ok = fm.init(17010, 17012, "");
    EXPECT_TRUE(ok);
    EXPECT_EQ(fm.getRobotCount(), 1);

    fm.stop();
}

TEST_F(FleetManagerTest, RunOneCycleReturnsTiming) {
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    fm.init(17020, 17022, "");

    auto timing = fm.runOneCycle();

    EXPECT_EQ(timing.cycle_number, 0);
    EXPECT_GE(timing.total_ms, 0.0);
    EXPECT_GE(timing.tcp_process_ms, 0.0);
    EXPECT_GE(timing.state_update_ms, 0.0);
    EXPECT_GE(timing.bt_tick_ms, 0.0);
    EXPECT_GE(timing.allocation_ms, 0.0);
    EXPECT_GE(timing.path_plan_ms, 0.0);
    EXPECT_GE(timing.command_ms, 0.0);
    EXPECT_EQ(fm.getCycleCount(), 1);

    fm.stop();
}

TEST_F(FleetManagerTest, CycleTimingUnder67ms) {
    // Verify that a single cycle without real TCP connections
    // completes well under the 67ms budget
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    fm.init(17030, 17032, "");

    // Run several cycles and check timing
    double max_ms = 0.0;
    for (int i = 0; i < 10; ++i) {
        auto timing = fm.runOneCycle();
        if (timing.total_ms > max_ms) max_ms = timing.total_ms;
    }

    // Without real TCP traffic, each cycle should be well under 67ms
    EXPECT_LT(max_ms, 67.0) << "Max cycle time exceeded 67ms budget: " << max_ms << "ms";

    fm.stop();
}

TEST_F(FleetManagerTest, FleetStatusJsonHasRequiredFields) {
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    fm.init(17040, 17042, "");
    fm.runOneCycle();

    auto status = fm.getFleetStatusJson();

    // Check top-level fields
    EXPECT_TRUE(status.isMember("cycle_count"));
    EXPECT_TRUE(status.isMember("running"));
    EXPECT_TRUE(status.isMember("robot_count"));
    EXPECT_TRUE(status.isMember("timing"));
    EXPECT_TRUE(status.isMember("tasks"));
    EXPECT_TRUE(status.isMember("robots"));
    EXPECT_TRUE(status.isMember("graph"));
    EXPECT_TRUE(status.isMember("reservations"));

    // Check graph info matches warehouse
    EXPECT_EQ(status["graph"]["nodes"].asUInt(), 25);
    EXPECT_GT(status["graph"]["edges"].asUInt(), 0u);

    // Check robot count
    EXPECT_EQ(status["robot_count"].asUInt(), 1);
    EXPECT_EQ(status["robots"].size(), 1);

    // Check robot fields
    auto& robot = status["robots"][0];
    EXPECT_TRUE(robot.isMember("id"));
    EXPECT_TRUE(robot.isMember("state"));
    EXPECT_TRUE(robot.isMember("battery_pct"));
    EXPECT_TRUE(robot.isMember("pose"));

    fm.stop();
}

TEST_F(FleetManagerTest, TaskManagerAccessible) {
    std::vector<rdt::RobotConfig> configs = {robot_config_};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    fm.init(17050, 17052, "");

    auto& tm = fm.getTaskManager();
    auto id = tm.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1", 5);
    EXPECT_EQ(id, 1);
    EXPECT_EQ(tm.getPendingCount(), 1);

    fm.stop();
}

TEST_F(FleetManagerTest, MultipleRobotsInit) {
    // Create two robots with different names
    auto config2 = robot_config_;
    config2.name = "DiffDrive_AMR_2";

    std::vector<rdt::RobotConfig> configs = {robot_config_, config2};
    rdt::fleet::FleetManager fm(wh_config_, configs);

    fm.init(17060, 17062, "");
    EXPECT_EQ(fm.getRobotCount(), 2);

    fm.stop();
}

// ════════════════════════════════════════════════════════════
// Phase 2: Mixed Fleet tests
// ════════════════════════════════════════════════════════════

TEST_F(FleetManagerTest, MixedFleetFromManifest) {
    // Load fleet manifest and expand to individual configs
    auto manifest = rdt::Config::loadFleetManifest(
        std::string(RDT_PROJECT_ROOT) + "/configs/fleets/default_mixed.json");
    auto configs = rdt::Config::expandFleetManifest(manifest, std::string(RDT_PROJECT_ROOT));

    ASSERT_EQ(configs.size(), 10u);

    rdt::fleet::FleetManager fm(wh_config_, configs);
    fm.init(17070, 17072, "");

    EXPECT_EQ(fm.getRobotCount(), 10);

    // Run a cycle — should not crash with mixed types
    auto timing = fm.runOneCycle();
    EXPECT_GE(timing.total_ms, 0.0);
    EXPECT_EQ(fm.getCycleCount(), 1);

    fm.stop();
}

TEST_F(FleetManagerTest, MixedFleetStatusJsonIncludesRobotType) {
    auto manifest = rdt::Config::loadFleetManifest(
        std::string(RDT_PROJECT_ROOT) + "/configs/fleets/default_mixed.json");
    auto configs = rdt::Config::expandFleetManifest(manifest, std::string(RDT_PROJECT_ROOT));

    rdt::fleet::FleetManager fm(wh_config_, configs);
    fm.init(17080, 17082, "");
    fm.runOneCycle();

    auto status = fm.getFleetStatusJson();

    EXPECT_EQ(status["robot_count"].asUInt(), 10);
    EXPECT_EQ(status["robots"].size(), 10);

    // Every robot should have a robot_type field
    int amr_count = 0;
    int agv_count = 0;
    for (const auto& r : status["robots"]) {
        ASSERT_TRUE(r.isMember("robot_type"))
            << "Robot " << r["id"].asString() << " missing robot_type";

        std::string type = r["robot_type"].asString();
        if (type == "differential_drive") amr_count++;
        else if (type == "unidirectional") agv_count++;
    }

    EXPECT_EQ(amr_count, 5);
    EXPECT_EQ(agv_count, 5);

    fm.stop();
}

TEST_F(TaskManagerTest, MixedFleetTypeCompatibility) {
    // MOVE task: both AMR and AGV can do it
    auto move_id = task_mgr_.addTask(rdt::TaskType::MOVE, "DOCK_1", "DROP_1");

    auto amr = makeIdleRobot("AMR_001", "DOCK_1", 80.0);
    amr.type = rdt::RobotType::DIFFERENTIAL_DRIVE;

    auto agv = makeIdleRobot("AGV_001", "DOCK_2", 80.0);
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    // AMR should be able to do MOVE
    std::vector<rdt::fleet::RobotAllocationInfo> amr_vec = {amr};
    auto result = task_mgr_.allocateNext(amr_vec, graph_, reservations_);
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->second, "AMR_001");
}

TEST_F(TaskManagerTest, AGVCannotDoPick) {
    // PICK task: only AMR (differential_drive or omnidirectional) can do it
    task_mgr_.addTask(rdt::TaskType::PICK, "DOCK_1", "DROP_1");

    auto agv = makeIdleRobot("AGV_001");
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {agv};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());  // AGV can't do PICK
}

TEST_F(TaskManagerTest, AGVCannotDoPlace) {
    // PLACE task: also excluded for unidirectional
    task_mgr_.addTask(rdt::TaskType::PLACE, "DOCK_1", "DROP_1");

    auto agv = makeIdleRobot("AGV_001");
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {agv};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    EXPECT_FALSE(result.has_value());
}

TEST_F(TaskManagerTest, MixedFleetPickAssignedToAMR) {
    // Both an AMR and AGV are available, PICK task should go to AMR
    task_mgr_.addTask(rdt::TaskType::PICK, "DOCK_1", "DROP_1");

    auto amr = makeIdleRobot("AMR_001", "DOCK_1", 80.0);
    amr.type = rdt::RobotType::DIFFERENTIAL_DRIVE;

    auto agv = makeIdleRobot("AGV_001", "DOCK_2", 80.0);
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {agv, amr};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->second, "AMR_001");  // AMR, not AGV
}

TEST_F(TaskManagerTest, AGVCanDoCharge) {
    task_mgr_.addTask(rdt::TaskType::CHARGE, "DOCK_1", "DOCK_2");

    auto agv = makeIdleRobot("AGV_001");
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {agv};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->second, "AGV_001");
}

TEST_F(TaskManagerTest, AGVCanDoPark) {
    task_mgr_.addTask(rdt::TaskType::PARK, "DOCK_1", "DOCK_2");

    auto agv = makeIdleRobot("AGV_001");
    agv.type = rdt::RobotType::UNIDIRECTIONAL;

    std::vector<rdt::fleet::RobotAllocationInfo> robots = {agv};
    auto result = task_mgr_.allocateNext(robots, graph_, reservations_);
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->second, "AGV_001");
}

// ════════════════════════════════════════════════════════════
// Phase 2: HTTP-level contract tests for mixed fleet REST API
// ════════════════════════════════════════════════════════════

namespace {

std::string http_get(uint16_t port, const std::string& path) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    if (::connect(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        return "";
    }

    std::string request = "GET " + path + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
    ::send(fd, request.data(), request.size(), 0);

    std::string response;
    char buf[4096];
    ssize_t n;
    while ((n = ::recv(fd, buf, sizeof(buf) - 1, 0)) > 0) {
        buf[n] = '\0';
        response += buf;
    }

    ::close(fd);
    return response;
}

std::string extract_body(const std::string& response) {
    auto pos = response.find("\r\n\r\n");
    if (pos == std::string::npos) return "";
    return response.substr(pos + 4);
}

} // anonymous namespace

TEST_F(FleetManagerTest, MixedFleetHTTPRobotsIncludesRobotType) {
    // Load mixed fleet, init with REST server, make HTTP request
    auto manifest = rdt::Config::loadFleetManifest(
        std::string(RDT_PROJECT_ROOT) + "/configs/fleets/default_mixed.json");
    auto configs = rdt::Config::expandFleetManifest(manifest, std::string(RDT_PROJECT_ROOT));

    uint16_t rest_port = 17090;
    rdt::fleet::FleetManager fm(wh_config_, configs);
    fm.init(17089, rest_port, "");
    fm.runOneCycle();

    // Give REST server a moment to start
    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    // HTTP GET /api/robots — verify robot_type is in the JSON response
    std::string response = http_get(rest_port, "/api/robots");
    std::string body = extract_body(response);

    ASSERT_FALSE(body.empty()) << "Empty HTTP response from /api/robots";

    // Parse JSON
    Json::Value robots;
    Json::CharReaderBuilder builder;
    std::string errors;
    std::istringstream stream(body);
    ASSERT_TRUE(Json::parseFromStream(builder, stream, &robots, &errors))
        << "Failed to parse JSON: " << errors;

    ASSERT_TRUE(robots.isArray());
    EXPECT_EQ(robots.size(), 10u);

    // Every robot must have a robot_type field with a valid value
    int amr_count = 0, agv_count = 0;
    for (const auto& r : robots) {
        ASSERT_TRUE(r.isMember("robot_type"))
            << "HTTP /api/robots missing robot_type for " << r["id"].asString();

        std::string type = r["robot_type"].asString();
        EXPECT_TRUE(type == "differential_drive" || type == "unidirectional" || type == "omnidirectional")
            << "Invalid robot_type: " << type;

        if (type == "differential_drive") amr_count++;
        else if (type == "unidirectional") agv_count++;
    }

    EXPECT_EQ(amr_count, 5) << "Expected 5 AMRs in HTTP response";
    EXPECT_EQ(agv_count, 5) << "Expected 5 AGVs in HTTP response";

    fm.stop();
}

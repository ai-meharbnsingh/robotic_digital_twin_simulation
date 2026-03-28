#pragma once

// ──────────────────────────────────────────────────────────
// rdt/fleet/TaskManager.h — Task allocation and lifecycle
//
// FIFO allocation with priority ordering: highest priority
// first, then oldest within same priority level.
//
// 9-check validation before assignment:
//   1. Task exists
//   2. Task not already assigned
//   3. Robot is IDLE
//   4. Robot battery > critical
//   5. Source node exists in graph
//   6. Dest node exists in graph
//   7. Path exists (A* check)
//   8. No node reservation conflicts
//   9. Robot type compatible with task type
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <optional>
#include <unordered_map>
#include <mutex>
#include <cstdint>
#include <chrono>

#include "rdt/core/Types.h"
#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/AStar.h"
#include "rdt/navigation/NodeReservation.h"

namespace rdt {
namespace fleet {

/// Internal task record with full lifecycle tracking.
struct TaskRecord {
    uint64_t    id          = 0;
    TaskType    type        = TaskType::MOVE;
    std::string source_node;
    std::string dest_node;
    int         priority    = 0;         ///< Higher = more urgent
    TaskState   state       = TaskState::NOT_ASSIGNED;
    std::string assigned_robot;
    std::chrono::steady_clock::time_point created_at;
    std::chrono::steady_clock::time_point assigned_at;
    std::chrono::steady_clock::time_point completed_at;
};

/// Minimal view of a robot for allocation decisions.
struct RobotAllocationInfo {
    std::string  id;
    RobotState   state           = RobotState::IDLE;
    RobotType    type            = RobotType::DIFFERENTIAL_DRIVE;
    double       battery_pct     = 100.0;
    double       critical_pct    = 20.0;
    std::string  current_node;
};

class TaskManager {
public:
    TaskManager();
    ~TaskManager() = default;

    /// Add a new task to the pending queue.
    /// @return The assigned task ID (monotonically increasing).
    uint64_t addTask(TaskType type,
                     const std::string& source_node,
                     const std::string& dest_node,
                     int priority = 0);

    /// Try to allocate the highest-priority pending task to an available robot.
    /// Runs 9-check validation. If no valid assignment possible, returns nullopt.
    /// @param robots         Available robots with their current status
    /// @param graph          The warehouse graph (for checks 5-7)
    /// @param reservations   The node reservation table (for check 8)
    /// @return pair<task_id, robot_id> if allocated, nullopt otherwise
    std::optional<std::pair<uint64_t, std::string>>
    allocateNext(const std::vector<RobotAllocationInfo>& robots,
                 const GraphMap& graph,
                 nav::NodeReservation& reservations);

    /// Get a task by ID. Returns nullopt if not found.
    std::optional<TaskRecord> getTask(uint64_t id) const;

    /// Mark a task as completed.
    /// @return true if the task was found and was in ASSIGNED/IN_PROGRESS state.
    bool completeTask(uint64_t id);

    /// Mark a task as failed.
    /// @return true if the task was found and was in ASSIGNED/IN_PROGRESS state.
    bool failTask(uint64_t id);

    /// Get the number of pending (NOT_ASSIGNED) tasks.
    size_t getPendingCount() const;

    /// Get the number of active (ASSIGNED or IN_PROGRESS) tasks.
    size_t getActiveCount() const;

    /// Get the number of completed tasks.
    size_t getCompletedCount() const;

    /// Get all tasks (snapshot).
    std::vector<TaskRecord> getAllTasks() const;

private:
    /// Run 9-check validation for a task-robot pair.
    /// @return empty string if valid, otherwise a human-readable rejection reason.
    std::string validate(const TaskRecord& task,
                         const RobotAllocationInfo& robot,
                         const GraphMap& graph,
                         nav::NodeReservation& reservations) const;

    /// Check if robot type is compatible with task type.
    static bool isTypeCompatible(RobotType robot_type, TaskType task_type);

    mutable std::mutex mtx_;
    uint64_t next_id_ = 1;
    std::unordered_map<uint64_t, TaskRecord> tasks_;
};

}  // namespace fleet
}  // namespace rdt

// ──────────────────────────────────────────────────────────
// rdt/fleet/TaskManager.cpp — Task allocation with 9-check validation
// ──────────────────────────────────────────────────────────

#include "rdt/fleet/TaskManager.h"
#include "rdt/core/Logger.h"

#include <algorithm>

namespace rdt {
namespace fleet {

TaskManager::TaskManager() = default;

uint64_t TaskManager::addTask(TaskType type,
                              const std::string& source_node,
                              const std::string& dest_node,
                              int priority) {
    std::lock_guard<std::mutex> lock(mtx_);

    TaskRecord record;
    record.id          = next_id_++;
    record.type        = type;
    record.source_node = source_node;
    record.dest_node   = dest_node;
    record.priority    = priority;
    record.state       = TaskState::NOT_ASSIGNED;
    record.created_at  = std::chrono::steady_clock::now();

    tasks_[record.id] = record;

    RDT_LOG_INFO("TaskManager: added task {} type={} src={} dst={} priority={}",
                 record.id, task_type_to_string(type), source_node, dest_node, priority);

    return record.id;
}

std::optional<std::pair<uint64_t, std::string>>
TaskManager::allocateNext(const std::vector<RobotAllocationInfo>& robots,
                          const GraphMap& graph,
                          nav::NodeReservation& reservations) {
    std::lock_guard<std::mutex> lock(mtx_);

    // Collect pending tasks, sort by priority (desc) then creation time (asc)
    std::vector<TaskRecord*> pending;
    for (auto& [id, task] : tasks_) {
        if (task.state == TaskState::NOT_ASSIGNED) {
            pending.push_back(&task);
        }
    }

    if (pending.empty()) return std::nullopt;

    std::sort(pending.begin(), pending.end(),
              [](const TaskRecord* a, const TaskRecord* b) {
                  if (a->priority != b->priority)
                      return a->priority > b->priority;  // higher priority first
                  return a->created_at < b->created_at;  // older first (FIFO)
              });

    // Try to allocate: for each pending task, try each robot
    for (TaskRecord* task : pending) {
        for (const auto& robot : robots) {
            std::string reason = validate(*task, robot, graph, reservations);
            if (reason.empty()) {
                // Valid assignment — commit it
                task->state          = TaskState::ASSIGNED;
                task->assigned_robot = robot.id;
                task->assigned_at    = std::chrono::steady_clock::now();

                RDT_LOG_INFO("TaskManager: assigned task {} to robot {}",
                             task->id, robot.id);

                return std::make_pair(task->id, robot.id);
            } else {
                RDT_LOG_DEBUG("TaskManager: task {} rejected for robot {}: {}",
                              task->id, robot.id, reason);
            }
        }
    }

    return std::nullopt;
}

std::optional<TaskRecord> TaskManager::getTask(uint64_t id) const {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = tasks_.find(id);
    if (it == tasks_.end()) return std::nullopt;
    return it->second;
}

bool TaskManager::completeTask(uint64_t id) {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = tasks_.find(id);
    if (it == tasks_.end()) return false;

    auto& task = it->second;
    if (task.state != TaskState::ASSIGNED && task.state != TaskState::IN_PROGRESS) {
        return false;
    }

    task.state        = TaskState::COMPLETED;
    task.completed_at = std::chrono::steady_clock::now();

    RDT_LOG_INFO("TaskManager: task {} completed", id);
    return true;
}

bool TaskManager::failTask(uint64_t id) {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = tasks_.find(id);
    if (it == tasks_.end()) return false;

    auto& task = it->second;
    if (task.state != TaskState::ASSIGNED && task.state != TaskState::IN_PROGRESS) {
        return false;
    }

    task.state        = TaskState::FAILED;
    task.completed_at = std::chrono::steady_clock::now();

    RDT_LOG_WARN("TaskManager: task {} failed", id);
    return true;
}

size_t TaskManager::getPendingCount() const {
    std::lock_guard<std::mutex> lock(mtx_);
    size_t count = 0;
    for (const auto& [id, task] : tasks_) {
        if (task.state == TaskState::NOT_ASSIGNED) ++count;
    }
    return count;
}

size_t TaskManager::getActiveCount() const {
    std::lock_guard<std::mutex> lock(mtx_);
    size_t count = 0;
    for (const auto& [id, task] : tasks_) {
        if (task.state == TaskState::ASSIGNED || task.state == TaskState::IN_PROGRESS) {
            ++count;
        }
    }
    return count;
}

size_t TaskManager::getCompletedCount() const {
    std::lock_guard<std::mutex> lock(mtx_);
    size_t count = 0;
    for (const auto& [id, task] : tasks_) {
        if (task.state == TaskState::COMPLETED) ++count;
    }
    return count;
}

std::vector<TaskRecord> TaskManager::getAllTasks() const {
    std::lock_guard<std::mutex> lock(mtx_);
    std::vector<TaskRecord> result;
    result.reserve(tasks_.size());
    for (const auto& [id, task] : tasks_) {
        result.push_back(task);
    }
    return result;
}

std::string TaskManager::validate(const TaskRecord& task,
                                  const RobotAllocationInfo& robot,
                                  const GraphMap& graph,
                                  nav::NodeReservation& reservations) const {
    // Check 1: Task exists (always true since we have the record)
    // This is implicit — we only call validate with valid TaskRecord refs.

    // Check 2: Task not already assigned
    if (task.state != TaskState::NOT_ASSIGNED) {
        return "task already assigned";
    }

    // Check 3: Robot is IDLE
    if (robot.state != RobotState::IDLE) {
        return "robot not IDLE (state=" + robot_state_to_string(robot.state) + ")";
    }

    // Check 4: Robot battery > critical
    if (robot.battery_pct <= robot.critical_pct) {
        return "battery too low (" + std::to_string(robot.battery_pct) + "% <= "
               + std::to_string(robot.critical_pct) + "%)";
    }

    // Check 5: Source node exists
    if (!graph.hasNode(task.source_node)) {
        return "source node '" + task.source_node + "' not in graph";
    }

    // Check 6: Dest node exists
    if (!graph.hasNode(task.dest_node)) {
        return "dest node '" + task.dest_node + "' not in graph";
    }

    // Check 7: Path exists (A* from source to dest)
    auto path_result = AStar::findPath(graph, task.source_node, task.dest_node);
    if (!path_result.found) {
        return "no path from " + task.source_node + " to " + task.dest_node;
    }

    // Check 8: No node reservation conflicts
    auto conflicts = reservations.checkConflict(robot.id, path_result.path);
    if (!conflicts.empty()) {
        return "node conflicts: " + std::to_string(conflicts.size()) + " nodes reserved";
    }

    // Check 9: Robot type compatible with task type
    if (!isTypeCompatible(robot.type, task.type)) {
        return "robot type " + robot_type_to_string(robot.type)
               + " incompatible with task " + task_type_to_string(task.type);
    }

    return "";  // All checks pass
}

bool TaskManager::isTypeCompatible(RobotType robot_type, TaskType task_type) {
    // All robot types can do MOVE, CHARGE, PARK
    if (task_type == TaskType::MOVE || task_type == TaskType::CHARGE ||
        task_type == TaskType::PARK) {
        return true;
    }

    // PICK and PLACE require DIFFERENTIAL_DRIVE or OMNIDIRECTIONAL
    // (unidirectional AGVs typically can't do fine pick/place maneuvers)
    if (task_type == TaskType::PICK || task_type == TaskType::PLACE) {
        return robot_type == RobotType::DIFFERENTIAL_DRIVE ||
               robot_type == RobotType::OMNIDIRECTIONAL;
    }

    return true;
}

}  // namespace fleet
}  // namespace rdt

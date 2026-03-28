// ──────────────────────────────────────────────────────────
// navigation/NodeReservation.cpp — Greedy node reservation
// ──────────────────────────────────────────────────────────

#include "rdt/navigation/NodeReservation.h"

#include <algorithm>

namespace rdt {
namespace nav {

bool NodeReservation::reserve(const std::string& robot_id,
                              const std::vector<std::string>& path_nodes,
                              size_t lookahead) {
    std::lock_guard<std::mutex> lock(mtx_);

    // Determine how many nodes to actually reserve
    size_t count = std::min(path_nodes.size(), lookahead);

    // Phase 1: conflict check — if ANY node in the lookahead window
    // is held by a different robot, reject the entire reservation.
    for (size_t i = 0; i < count; ++i) {
        auto it = node_to_robot_.find(path_nodes[i]);
        if (it != node_to_robot_.end() && it->second != robot_id) {
            return false;  // conflict — atomic reject
        }
    }

    // Phase 2: release any previously-held nodes for this robot
    // (a robot re-reserving gets a fresh set).
    releaseUnlocked(robot_id);

    // Phase 3: commit the new reservations
    auto& held = robot_to_nodes_[robot_id];
    for (size_t i = 0; i < count; ++i) {
        node_to_robot_[path_nodes[i]] = robot_id;
        held.insert(path_nodes[i]);
    }

    return true;
}

void NodeReservation::release(const std::string& robot_id) {
    std::lock_guard<std::mutex> lock(mtx_);
    releaseUnlocked(robot_id);
}

std::optional<std::string> NodeReservation::isReserved(const std::string& node_name) const {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = node_to_robot_.find(node_name);
    if (it != node_to_robot_.end()) {
        return it->second;
    }
    return std::nullopt;
}

std::vector<std::string> NodeReservation::getReservations(const std::string& robot_id) const {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = robot_to_nodes_.find(robot_id);
    if (it == robot_to_nodes_.end()) {
        return {};
    }
    return std::vector<std::string>(it->second.begin(), it->second.end());
}

std::vector<std::string> NodeReservation::checkConflict(
        const std::string& robot_id,
        const std::vector<std::string>& path_nodes) const {
    std::lock_guard<std::mutex> lock(mtx_);

    std::vector<std::string> conflicts;
    for (const auto& node : path_nodes) {
        auto it = node_to_robot_.find(node);
        if (it != node_to_robot_.end() && it->second != robot_id) {
            conflicts.push_back(node);
        }
    }
    return conflicts;
}

std::string NodeReservation::resolveDeadlock(
        const std::string& robot_a,
        const std::string& robot_b,
        const std::vector<std::string>& needs_a,
        const std::vector<std::string>& needs_b) {
    std::lock_guard<std::mutex> lock(mtx_);

    // Deadlock condition:
    //   robot_a holds something robot_b needs AND
    //   robot_b holds something robot_a needs.
    bool a_blocks_b = false;
    bool b_blocks_a = false;

    // Check: does robot_a hold any node that robot_b needs?
    for (const auto& node : needs_b) {
        auto it = node_to_robot_.find(node);
        if (it != node_to_robot_.end() && it->second == robot_a) {
            a_blocks_b = true;
            break;
        }
    }

    // Check: does robot_b hold any node that robot_a needs?
    for (const auto& node : needs_a) {
        auto it = node_to_robot_.find(node);
        if (it != node_to_robot_.end() && it->second == robot_b) {
            b_blocks_a = true;
            break;
        }
    }

    if (!a_blocks_b || !b_blocks_a) {
        return "";  // No deadlock
    }

    // Deadlock confirmed — the lexicographically greater robot backs off.
    // This is deterministic and starvation-free.
    const std::string& loser = (robot_a > robot_b) ? robot_a : robot_b;
    releaseUnlocked(loser);
    return loser;
}

void NodeReservation::clear() {
    std::lock_guard<std::mutex> lock(mtx_);
    node_to_robot_.clear();
    robot_to_nodes_.clear();
}

size_t NodeReservation::robotCount() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return robot_to_nodes_.size();
}

size_t NodeReservation::nodeCount() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return node_to_robot_.size();
}

// ── Private ──────────────────────────────────────────────

bool NodeReservation::holdsAnyOf(const std::string& robot_id,
                                 const std::vector<std::string>& nodes) const {
    auto it = robot_to_nodes_.find(robot_id);
    if (it == robot_to_nodes_.end()) {
        return false;
    }
    for (const auto& node : nodes) {
        if (it->second.count(node)) {
            return true;
        }
    }
    return false;
}

void NodeReservation::releaseUnlocked(const std::string& robot_id) {
    auto it = robot_to_nodes_.find(robot_id);
    if (it == robot_to_nodes_.end()) {
        return;
    }
    for (const auto& node : it->second) {
        node_to_robot_.erase(node);
    }
    robot_to_nodes_.erase(it);
}

}  // namespace nav
}  // namespace rdt

#pragma once

// ──────────────────────────────────────────────────────────
// rdt/navigation/NodeReservation.h — Greedy node reservation
// with mutual exclusion, lookahead, and deadlock detection.
//
// Phase 3: greedy reservation table.
// Phase 7: OSQP-based ILP optimization replaces resolve logic.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <optional>
#include <unordered_map>
#include <unordered_set>
#include <mutex>

namespace rdt {
namespace nav {

/// @brief Thread-safe node reservation table for multi-robot deadlock prevention.
///
/// Each robot may reserve up to `lookahead` nodes along its planned path.
/// Mutual exclusion: no two robots may hold the same node simultaneously.
/// Deadlock detection: detects circular wait between two robots.
///
/// This is a greedy reservation system — Phase 7 upgrades to OSQP-based ILP.
class NodeReservation {
public:
    NodeReservation() = default;
    ~NodeReservation() = default;

    // Non-copyable, non-movable (owns a mutex)
    NodeReservation(const NodeReservation&) = delete;
    NodeReservation& operator=(const NodeReservation&) = delete;
    NodeReservation(NodeReservation&&) = delete;
    NodeReservation& operator=(NodeReservation&&) = delete;

    /// @brief Reserve nodes along a robot's planned path.
    ///
    /// Reserves up to `lookahead` nodes from `path_nodes`.
    /// If any of those nodes are already held by another robot,
    /// the reservation fails atomically (no partial reservations).
    ///
    /// @param robot_id   Unique identifier for the requesting robot.
    /// @param path_nodes Ordered list of node names the robot plans to traverse.
    /// @param lookahead  Maximum number of nodes to reserve (default 4).
    /// @return true if all nodes reserved successfully, false on conflict.
    bool reserve(const std::string& robot_id,
                 const std::vector<std::string>& path_nodes,
                 size_t lookahead = 4);

    /// @brief Release all nodes held by a robot.
    /// @param robot_id  The robot whose reservations to release.
    void release(const std::string& robot_id);

    /// @brief Check if a node is reserved.
    /// @param node_name  The node to query.
    /// @return The robot_id holding the node, or std::nullopt if free.
    std::optional<std::string> isReserved(const std::string& node_name) const;

    /// @brief Get all nodes currently reserved by a robot.
    /// @param robot_id  The robot to query.
    /// @return Vector of node names held by this robot (unordered).
    std::vector<std::string> getReservations(const std::string& robot_id) const;

    /// @brief Check which nodes in a proposed path conflict with existing reservations.
    ///
    /// Does NOT acquire any reservations — read-only check.
    /// Checks up to the full path (no lookahead limit applied here).
    ///
    /// @param robot_id    The robot that would be requesting.
    /// @param path_nodes  The proposed path to check.
    /// @return Vector of node names that are held by OTHER robots.
    std::vector<std::string> checkConflict(const std::string& robot_id,
                                           const std::vector<std::string>& path_nodes) const;

    /// @brief Detect and resolve a deadlock between two robots.
    ///
    /// A deadlock exists when:
    ///   - robot_a holds at least one node that robot_b needs, AND
    ///   - robot_b holds at least one node that robot_a needs.
    ///
    /// Resolution: the robot with the lexicographically greater ID backs off
    /// (its reservations are released). This provides a deterministic,
    /// starvation-free ordering. Phase 7 replaces this with priority-based ILP.
    ///
    /// @param robot_a       First robot ID.
    /// @param robot_b       Second robot ID.
    /// @param needs_a       Nodes robot_a needs (its desired path).
    /// @param needs_b       Nodes robot_b needs (its desired path).
    /// @return The robot_id that backed off, or empty string if no deadlock.
    std::string resolveDeadlock(const std::string& robot_a,
                                const std::string& robot_b,
                                const std::vector<std::string>& needs_a,
                                const std::vector<std::string>& needs_b);

    /// @brief Release all reservations for all robots.
    void clear();

    /// @brief Number of robots with active reservations.
    size_t robotCount() const;

    /// @brief Total number of reserved nodes across all robots.
    size_t nodeCount() const;

private:
    mutable std::mutex mtx_;

    // node_name → robot_id
    std::unordered_map<std::string, std::string> node_to_robot_;

    // robot_id → set of node names
    std::unordered_map<std::string, std::unordered_set<std::string>> robot_to_nodes_;

    /// @brief Internal: check if robot_a holds any node in `nodes`.
    /// Caller must hold mtx_.
    bool holdsAnyOf(const std::string& robot_id,
                    const std::vector<std::string>& nodes) const;

    /// @brief Internal: release all nodes for a robot. Caller must hold mtx_.
    void releaseUnlocked(const std::string& robot_id);
};

}  // namespace nav
}  // namespace rdt

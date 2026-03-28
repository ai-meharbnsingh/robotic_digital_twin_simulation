#pragma once

// ──────────────────────────────────────────────────────────
// rdt/fleet/COPPController.h — Cooperative Path Planning
//
// Plans non-conflicting paths for multiple robots using:
//   1. A* for each robot individually
//   2. NodeReservation to detect conflicts
//   3. Re-planning with penalty on conflicting nodes
//
// Full ILP optimization is deferred — this is the greedy
// sequential planner that ships in Phase 7.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>

#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/AStar.h"
#include "rdt/navigation/NodeReservation.h"

namespace rdt {
namespace fleet {

/// A planning request for one robot.
struct PlanRequest {
    std::string robot_id;
    std::string start_node;
    std::string goal_node;
    int         priority = 0;    ///< Higher = planned first
};

/// Result of planning for one robot.
struct PlanResult {
    std::string              robot_id;
    std::vector<std::string> path;
    double                   distance = 0.0;
    bool                     success  = false;
    int                      replans  = 0;      ///< How many replans were needed
};

class COPPController {
public:
    /// Maximum number of replan attempts per robot before giving up.
    static constexpr int MAX_REPLANS = 3;

    /// Penalty factor applied to conflicting edges during replan.
    static constexpr double CONFLICT_PENALTY = 100.0;

    COPPController() = default;
    ~COPPController() = default;

    /// Plan cooperative paths for all robots.
    ///
    /// Algorithm:
    ///   1. Sort requests by priority (descending)
    ///   2. For each robot (highest priority first):
    ///      a. Run A* from start to goal
    ///      b. Try to reserve path nodes via NodeReservation
    ///      c. If conflict: identify conflicting nodes, add to penalty set,
    ///         replan up to MAX_REPLANS times
    ///   3. Return results for all robots
    ///
    /// @param requests      One PlanRequest per robot
    /// @param graph         The warehouse navigation graph
    /// @param reservations  Shared reservation table (modified in-place)
    /// @return Map of robot_id → PlanResult
    std::unordered_map<std::string, PlanResult>
    planCooperativePaths(std::vector<PlanRequest> requests,
                         const GraphMap& graph,
                         nav::NodeReservation& reservations);

private:
    /// Plan a single robot's path, optionally avoiding penalized nodes.
    /// Uses A* with turn_cost set to CONFLICT_PENALTY for penalized nodes.
    PlanResult planSingleRobot(const PlanRequest& request,
                               const GraphMap& graph,
                               nav::NodeReservation& reservations,
                               const std::unordered_set<std::string>& penalized_nodes);
};

}  // namespace fleet
}  // namespace rdt

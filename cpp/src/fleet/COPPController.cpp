// ──────────────────────────────────────────────────────────
// rdt/fleet/COPPController.cpp — Cooperative Path Planning
//
// Sequential priority-based planner with conflict-driven
// replanning. Full ILP optimization deferred.
// ──────────────────────────────────────────────────────────

#include "rdt/fleet/COPPController.h"
#include "rdt/core/Logger.h"

#include <algorithm>

namespace rdt {
namespace fleet {

std::unordered_map<std::string, PlanResult>
COPPController::planCooperativePaths(std::vector<PlanRequest> requests,
                                     const GraphMap& graph,
                                     nav::NodeReservation& reservations) {
    std::unordered_map<std::string, PlanResult> results;

    if (requests.empty()) return results;

    // Sort by priority descending — highest priority robots plan first
    std::sort(requests.begin(), requests.end(),
              [](const PlanRequest& a, const PlanRequest& b) {
                  return a.priority > b.priority;
              });

    for (const auto& request : requests) {
        std::unordered_set<std::string> penalized_nodes;
        PlanResult result = planSingleRobot(request, graph, reservations, penalized_nodes);
        results[request.robot_id] = result;

        if (result.success) {
            RDT_LOG_DEBUG("COPP: robot {} planned {} hops (replans={})",
                          request.robot_id, result.path.size(), result.replans);
        } else {
            RDT_LOG_WARN("COPP: robot {} failed to plan path from {} to {}",
                         request.robot_id, request.start_node, request.goal_node);
        }
    }

    return results;
}

PlanResult COPPController::planSingleRobot(
    const PlanRequest& request,
    const GraphMap& graph,
    nav::NodeReservation& reservations,
    const std::unordered_set<std::string>& penalized_nodes) {

    PlanResult result;
    result.robot_id = request.robot_id;

    std::unordered_set<std::string> current_penalties = penalized_nodes;

    for (int attempt = 0; attempt <= MAX_REPLANS; ++attempt) {
        // Compute turn_cost based on penalties — if penalties exist, use a high
        // base turn cost to bias A* away from those areas.
        // For a proper implementation, we'd modify A* to accept per-node costs.
        // For now, we use the standard A* and check conflicts post-hoc.
        double turn_cost = current_penalties.empty() ? 0.0 : CONFLICT_PENALTY;

        auto path_result = AStar::findPath(graph,
                                           request.start_node,
                                           request.goal_node,
                                           Heuristic::EUCLIDEAN,
                                           turn_cost);

        if (!path_result.found) {
            result.success = false;
            result.replans = attempt;
            return result;
        }

        // Try to reserve the path
        bool reserved = reservations.reserve(request.robot_id, path_result.path);

        if (reserved) {
            result.path     = path_result.path;
            result.distance = path_result.distance;
            result.success  = true;
            result.replans  = attempt;
            return result;
        }

        // Reservation failed — find conflicting nodes and add to penalties
        auto conflicts = reservations.checkConflict(request.robot_id, path_result.path);
        for (const auto& node : conflicts) {
            current_penalties.insert(node);
        }

        result.replans = attempt + 1;

        RDT_LOG_DEBUG("COPP: robot {} conflict at attempt {}, {} penalty nodes",
                      request.robot_id, attempt, current_penalties.size());
    }

    // Exhausted replans
    result.success = false;
    return result;
}

}  // namespace fleet
}  // namespace rdt

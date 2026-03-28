#pragma once

// ──────────────────────────────────────────────────────────
// rdt/navigation/AStar.h — A* pathfinding on GraphMap
//
// Supports Manhattan, Euclidean, and Chebyshev heuristics.
// Optional turn-cost penalty for direction changes.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>

#include "rdt/navigation/GraphMap.h"

namespace rdt {

/// Heuristic function selector for A*
enum class Heuristic {
    MANHATTAN,
    EUCLIDEAN,
    CHEBYSHEV
};

/// Result of an A* path search
struct PathResult {
    std::vector<std::string> path;    ///< Ordered node names from start to goal
    double distance = 0.0;            ///< Total Euclidean path distance
    double time_ms  = 0.0;            ///< Wall-clock time spent computing
    bool   found    = false;           ///< True if a path was found
};

class AStar {
public:
    /// Find shortest path from start to goal on the given graph.
    /// @param graph       The navigation graph
    /// @param start       Name of the start node
    /// @param goal        Name of the goal node
    /// @param heuristic   Which heuristic to use (default: EUCLIDEAN)
    /// @param turn_cost   Additional cost penalty per direction change (default: 0.0)
    /// @return PathResult with path, distance, timing, and success flag
    static PathResult findPath(const GraphMap& graph,
                               const std::string& start,
                               const std::string& goal,
                               Heuristic heuristic = Heuristic::EUCLIDEAN,
                               double turn_cost = 0.0);
};

} // namespace rdt

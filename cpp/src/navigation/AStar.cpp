// ──────────────────────────────────────────────────────────
// navigation/AStar.cpp — A* pathfinding implementation
// ──────────────────────────────────────────────────────────

#include "rdt/navigation/AStar.h"

#include <chrono>
#include <cmath>
#include <queue>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <functional>

namespace rdt {

namespace {

// ── Heuristic functions ────────────────────────────────

double heuristic_euclidean(const MapNode& a, const MapNode& b) {
    double dx = b.x - a.x;
    double dy = b.y - a.y;
    return std::sqrt(dx * dx + dy * dy);
}

double heuristic_manhattan(const MapNode& a, const MapNode& b) {
    return std::abs(b.x - a.x) + std::abs(b.y - a.y);
}

double heuristic_chebyshev(const MapNode& a, const MapNode& b) {
    return std::max(std::abs(b.x - a.x), std::abs(b.y - a.y));
}

using HeuristicFn = std::function<double(const MapNode&, const MapNode&)>;

HeuristicFn selectHeuristic(Heuristic h) {
    switch (h) {
        case Heuristic::MANHATTAN:  return heuristic_manhattan;
        case Heuristic::EUCLIDEAN:  return heuristic_euclidean;
        case Heuristic::CHEBYSHEV:  return heuristic_chebyshev;
    }
    return heuristic_euclidean;
}

// ── Direction change detection for turn cost ───────────

double computeDirectionAngle(const MapNode& from, const MapNode& to) {
    return std::atan2(to.y - from.y, to.x - from.x);
}

} // anonymous namespace

PathResult AStar::findPath(const GraphMap& graph,
                           const std::string& start,
                           const std::string& goal,
                           Heuristic heuristic,
                           double turn_cost) {
    auto t0 = std::chrono::steady_clock::now();

    PathResult result;
    result.found = false;

    // Validate start and goal exist
    if (!graph.hasNode(start) || !graph.hasNode(goal)) {
        auto t1 = std::chrono::steady_clock::now();
        result.time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        return result;
    }

    // Same node — trivial path
    if (start == goal) {
        result.path = {start};
        result.distance = 0.0;
        result.found = true;
        auto t1 = std::chrono::steady_clock::now();
        result.time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        return result;
    }

    auto h_fn = selectHeuristic(heuristic);
    const MapNode& goal_node = graph.getNode(goal);

    // Priority queue: (f_score, node_name)
    using PQEntry = std::pair<double, std::string>;
    std::priority_queue<PQEntry, std::vector<PQEntry>, std::greater<PQEntry>> open_set;

    // g_score[node] = cost of cheapest path from start to node
    std::unordered_map<std::string, double> g_score;

    // came_from[node] = previous node in the best path
    std::unordered_map<std::string, std::string> came_from;

    // Direction angle at each node (for turn cost)
    std::unordered_map<std::string, double> direction;

    // Closed set
    std::unordered_set<std::string> closed;

    g_score[start] = 0.0;
    open_set.push({h_fn(graph.getNode(start), goal_node), start});

    while (!open_set.empty()) {
        auto [f, current] = open_set.top();
        open_set.pop();

        if (current == goal) {
            // Reconstruct path
            result.found = true;
            std::vector<std::string> path;
            std::string node = goal;
            while (node != start) {
                path.push_back(node);
                node = came_from[node];
            }
            path.push_back(start);
            std::reverse(path.begin(), path.end());
            result.path = std::move(path);

            // Compute total Euclidean distance along the path
            result.distance = 0.0;
            for (size_t i = 1; i < result.path.size(); ++i) {
                result.distance += graph.getEdgeDistance(result.path[i-1], result.path[i]);
            }

            auto t1 = std::chrono::steady_clock::now();
            result.time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
            return result;
        }

        if (closed.count(current)) continue;
        closed.insert(current);

        const MapNode& current_node = graph.getNode(current);

        for (const auto& neighbor : graph.getNeighbors(current)) {
            if (closed.count(neighbor)) continue;

            const MapNode& neighbor_node = graph.getNode(neighbor);
            double edge_dist = graph.getEdgeDistance(current, neighbor);
            double tentative_g = g_score[current] + edge_dist;

            // Apply turn cost penalty if applicable
            if (turn_cost > 0.0 && came_from.count(current)) {
                const MapNode& prev_node = graph.getNode(came_from[current]);
                double prev_angle = computeDirectionAngle(prev_node, current_node);
                double curr_angle = computeDirectionAngle(current_node, neighbor_node);
                double angle_diff = std::abs(curr_angle - prev_angle);
                if (angle_diff > M_PI) angle_diff = 2.0 * M_PI - angle_diff;
                if (angle_diff > 0.01) { // non-trivial direction change
                    tentative_g += turn_cost * (angle_diff / M_PI);
                }
            }

            if (g_score.find(neighbor) == g_score.end() ||
                tentative_g < g_score[neighbor]) {
                g_score[neighbor] = tentative_g;
                came_from[neighbor] = current;
                double f_score = tentative_g + h_fn(neighbor_node, goal_node);
                open_set.push({f_score, neighbor});
            }
        }
    }

    // No path found
    auto t1 = std::chrono::steady_clock::now();
    result.time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    return result;
}

} // namespace rdt

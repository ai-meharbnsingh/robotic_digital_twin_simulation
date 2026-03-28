// ──────────────────────────────────────────────────────────
// navigation/GraphMap.cpp — Adjacency list graph from warehouse config
// ──────────────────────────────────────────────────────────

#include "rdt/navigation/GraphMap.h"

#include <cmath>
#include <stdexcept>
#include <algorithm>

namespace rdt {

void GraphMap::loadFromConfig(const WarehouseConfig& config) {
    nodes_.clear();
    adjacency_.clear();
    edge_count_ = 0;

    // Index all nodes by name
    for (const auto& node : config.nodes) {
        nodes_[node.name] = node;
        adjacency_[node.name]; // ensure entry exists even with no edges
    }

    // Build adjacency list from edges
    for (const auto& edge : config.edges) {
        // Skip edges referencing unknown nodes
        if (nodes_.find(edge.from) == nodes_.end() ||
            nodes_.find(edge.to)   == nodes_.end()) {
            continue;
        }

        // Add forward direction
        auto& from_neighbors = adjacency_[edge.from];
        if (std::find(from_neighbors.begin(), from_neighbors.end(), edge.to)
            == from_neighbors.end()) {
            from_neighbors.push_back(edge.to);
            ++edge_count_;
        }

        // Add reverse direction if bidirectional
        if (edge.bidirectional) {
            auto& to_neighbors = adjacency_[edge.to];
            if (std::find(to_neighbors.begin(), to_neighbors.end(), edge.from)
                == to_neighbors.end()) {
                to_neighbors.push_back(edge.from);
                ++edge_count_;
            }
        }
    }
}

const MapNode& GraphMap::getNode(const std::string& name) const {
    auto it = nodes_.find(name);
    if (it == nodes_.end()) {
        throw std::runtime_error("GraphMap: node not found: " + name);
    }
    return it->second;
}

bool GraphMap::hasNode(const std::string& name) const {
    return nodes_.find(name) != nodes_.end();
}

std::vector<std::string> GraphMap::getNeighbors(const std::string& name) const {
    auto it = adjacency_.find(name);
    if (it == adjacency_.end()) {
        return {};
    }
    return it->second;
}

double GraphMap::getEdgeDistance(const std::string& from, const std::string& to) const {
    const auto& n1 = getNode(from);
    const auto& n2 = getNode(to);
    double dx = n2.x - n1.x;
    double dy = n2.y - n1.y;
    return std::sqrt(dx * dx + dy * dy);
}

std::vector<MapNode> GraphMap::getAllNodes() const {
    std::vector<MapNode> result;
    result.reserve(nodes_.size());
    for (const auto& kv : nodes_) {
        result.push_back(kv.second);
    }
    return result;
}

size_t GraphMap::nodeCount() const {
    return nodes_.size();
}

size_t GraphMap::edgeCount() const {
    return edge_count_;
}

} // namespace rdt

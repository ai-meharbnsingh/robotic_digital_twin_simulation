#pragma once

// ──────────────────────────────────────────────────────────
// rdt/navigation/GraphMap.h — Warehouse graph representation
//
// Builds an adjacency list from WarehouseConfig (nodes + edges).
// Used by A* and other path planners.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <unordered_map>

#include "rdt/core/Types.h"
#include "rdt/core/Config.h"

namespace rdt {

class GraphMap {
public:
    /// Build graph from a WarehouseConfig (nodes + edges).
    void loadFromConfig(const WarehouseConfig& config);

    /// Look up a node by name.
    /// @throws std::runtime_error if node not found.
    const MapNode& getNode(const std::string& name) const;

    /// Check whether a node exists.
    bool hasNode(const std::string& name) const;

    /// Get neighbor names for a given node.
    /// Returns empty vector if node has no neighbors or doesn't exist.
    std::vector<std::string> getNeighbors(const std::string& name) const;

    /// Compute Euclidean distance between two connected nodes.
    /// Returns the distance even if nodes aren't directly connected
    /// (uses node coordinates, not edge length).
    /// @throws std::runtime_error if either node not found.
    double getEdgeDistance(const std::string& from, const std::string& to) const;

    /// Get all nodes in the graph.
    std::vector<MapNode> getAllNodes() const;

    /// Number of nodes in the graph.
    size_t nodeCount() const;

    /// Number of directed edges (bidirectional edge = 2 directed edges).
    size_t edgeCount() const;

private:
    // Node name → MapNode
    std::unordered_map<std::string, MapNode> nodes_;

    // Node name → list of neighbor names
    std::unordered_map<std::string, std::vector<std::string>> adjacency_;

    // Total directed edge count
    size_t edge_count_ = 0;
};

} // namespace rdt

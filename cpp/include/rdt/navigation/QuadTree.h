#pragma once

// ──────────────────────────────────────────────────────────
// rdt/navigation/QuadTree.h — Spatial index for map nodes
//
// Supports nearest-node queries and radius searches.
// Can be built from a GraphMap for spatial lookups.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <memory>
#include <limits>

#include "rdt/navigation/GraphMap.h"

namespace rdt {

/// A point stored in the quad tree
struct QTPoint {
    std::string name;
    double x = 0.0;
    double y = 0.0;
};

/// Axis-aligned bounding rectangle
struct QTBounds {
    double x_min = 0.0;
    double y_min = 0.0;
    double x_max = 0.0;
    double y_max = 0.0;

    bool contains(double x, double y) const;
    bool intersectsCircle(double cx, double cy, double radius) const;
};

class QuadTree {
public:
    /// Construct an empty quad tree with given bounds.
    explicit QuadTree(const QTBounds& bounds, int capacity = 4);

    /// Default constructor — creates an empty tree with zero bounds.
    QuadTree();

    /// Insert a named point.
    void insert(const std::string& name, double x, double y);

    /// Build quad tree from all nodes in a GraphMap.
    void buildFromGraphMap(const GraphMap& graph);

    /// Find the nearest node to (x, y). Returns empty string if tree is empty.
    std::string nearestNode(double x, double y) const;

    /// Find all nodes within radius of (x, y).
    std::vector<std::string> nodesInRadius(double x, double y, double radius) const;

    /// Number of points stored.
    size_t size() const;

private:
    void subdivide();
    void nearestHelper(double x, double y,
                       std::string& best_name, double& best_dist_sq) const;
    void radiusHelper(double x, double y, double radius,
                      std::vector<std::string>& results) const;

    QTBounds bounds_;
    int capacity_;
    std::vector<QTPoint> points_;
    bool divided_ = false;
    std::unique_ptr<QuadTree> nw_, ne_, sw_, se_;
    size_t total_size_ = 0;
};

} // namespace rdt

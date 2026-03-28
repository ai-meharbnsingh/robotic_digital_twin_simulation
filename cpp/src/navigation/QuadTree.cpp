// ──────────────────────────────────────────────────────────
// navigation/QuadTree.cpp — Spatial index for map nodes
// ──────────────────────────────────────────────────────────

#include "rdt/navigation/QuadTree.h"

#include <cmath>
#include <algorithm>
#include <limits>

namespace rdt {

// ── QTBounds ────────────────────────────────────────────

bool QTBounds::contains(double x, double y) const {
    return x >= x_min && x <= x_max && y >= y_min && y <= y_max;
}

bool QTBounds::intersectsCircle(double cx, double cy, double radius) const {
    // Find the closest point on the rectangle to the circle center
    double closest_x = std::max(x_min, std::min(cx, x_max));
    double closest_y = std::max(y_min, std::min(cy, y_max));
    double dx = cx - closest_x;
    double dy = cy - closest_y;
    return (dx * dx + dy * dy) <= (radius * radius);
}

// ── QuadTree ────────────────────────────────────────────

QuadTree::QuadTree()
    : bounds_{0, 0, 0, 0}, capacity_(4) {}

QuadTree::QuadTree(const QTBounds& bounds, int capacity)
    : bounds_(bounds), capacity_(capacity) {}

void QuadTree::insert(const std::string& name, double x, double y) {
    if (!bounds_.contains(x, y)) {
        // Expand bounds if needed (for first inserts or out-of-range)
        if (total_size_ == 0) {
            bounds_.x_min = x - 1.0;
            bounds_.y_min = y - 1.0;
            bounds_.x_max = x + 1.0;
            bounds_.y_max = y + 1.0;
        } else {
            // Grow bounds to include new point, with margin
            bounds_.x_min = std::min(bounds_.x_min, x - 1.0);
            bounds_.y_min = std::min(bounds_.y_min, y - 1.0);
            bounds_.x_max = std::max(bounds_.x_max, x + 1.0);
            bounds_.y_max = std::max(bounds_.y_max, y + 1.0);
        }
    }

    ++total_size_;

    if (!divided_ && static_cast<int>(points_.size()) < capacity_) {
        points_.push_back({name, x, y});
        return;
    }

    if (!divided_) {
        subdivide();
    }

    // Try to insert into a child
    if (nw_->bounds_.contains(x, y)) { nw_->insert(name, x, y); return; }
    if (ne_->bounds_.contains(x, y)) { ne_->insert(name, x, y); return; }
    if (sw_->bounds_.contains(x, y)) { sw_->insert(name, x, y); return; }
    if (se_->bounds_.contains(x, y)) { se_->insert(name, x, y); return; }

    // Edge case: point exactly on a boundary — store in this node
    points_.push_back({name, x, y});
}

void QuadTree::buildFromGraphMap(const GraphMap& graph) {
    auto all_nodes = graph.getAllNodes();
    if (all_nodes.empty()) return;

    // Compute bounding box with margin
    double min_x = std::numeric_limits<double>::max();
    double min_y = std::numeric_limits<double>::max();
    double max_x = std::numeric_limits<double>::lowest();
    double max_y = std::numeric_limits<double>::lowest();

    for (const auto& n : all_nodes) {
        min_x = std::min(min_x, n.x);
        min_y = std::min(min_y, n.y);
        max_x = std::max(max_x, n.x);
        max_y = std::max(max_y, n.y);
    }

    double margin = 1.0;
    bounds_ = {min_x - margin, min_y - margin, max_x + margin, max_y + margin};

    for (const auto& n : all_nodes) {
        insert(n.name, n.x, n.y);
    }
}

std::string QuadTree::nearestNode(double x, double y) const {
    if (total_size_ == 0) return "";

    std::string best_name;
    double best_dist_sq = std::numeric_limits<double>::max();
    nearestHelper(x, y, best_name, best_dist_sq);
    return best_name;
}

std::vector<std::string> QuadTree::nodesInRadius(double x, double y, double radius) const {
    std::vector<std::string> results;
    radiusHelper(x, y, radius, results);
    return results;
}

size_t QuadTree::size() const {
    return total_size_;
}

void QuadTree::subdivide() {
    double mid_x = (bounds_.x_min + bounds_.x_max) / 2.0;
    double mid_y = (bounds_.y_min + bounds_.y_max) / 2.0;

    nw_ = std::make_unique<QuadTree>(
        QTBounds{bounds_.x_min, mid_y, mid_x, bounds_.y_max}, capacity_);
    ne_ = std::make_unique<QuadTree>(
        QTBounds{mid_x, mid_y, bounds_.x_max, bounds_.y_max}, capacity_);
    sw_ = std::make_unique<QuadTree>(
        QTBounds{bounds_.x_min, bounds_.y_min, mid_x, mid_y}, capacity_);
    se_ = std::make_unique<QuadTree>(
        QTBounds{mid_x, bounds_.y_min, bounds_.x_max, mid_y}, capacity_);

    divided_ = true;

    // Redistribute existing points into children
    std::vector<QTPoint> old_points = std::move(points_);
    points_.clear();
    for (const auto& p : old_points) {
        --total_size_; // insert will re-increment
        insert(p.name, p.x, p.y);
    }
}

void QuadTree::nearestHelper(double x, double y,
                              std::string& best_name, double& best_dist_sq) const {
    // Check points in this node
    for (const auto& p : points_) {
        double dx = p.x - x;
        double dy = p.y - y;
        double d2 = dx * dx + dy * dy;
        if (d2 < best_dist_sq) {
            best_dist_sq = d2;
            best_name = p.name;
        }
    }

    if (!divided_) return;

    // Check children — prune branches that can't contain a closer point
    double best_dist = std::sqrt(best_dist_sq);

    if (nw_ && nw_->bounds_.intersectsCircle(x, y, best_dist)) {
        nw_->nearestHelper(x, y, best_name, best_dist_sq);
        best_dist = std::sqrt(best_dist_sq);
    }
    if (ne_ && ne_->bounds_.intersectsCircle(x, y, best_dist)) {
        ne_->nearestHelper(x, y, best_name, best_dist_sq);
        best_dist = std::sqrt(best_dist_sq);
    }
    if (sw_ && sw_->bounds_.intersectsCircle(x, y, best_dist)) {
        sw_->nearestHelper(x, y, best_name, best_dist_sq);
        best_dist = std::sqrt(best_dist_sq);
    }
    if (se_ && se_->bounds_.intersectsCircle(x, y, best_dist)) {
        se_->nearestHelper(x, y, best_name, best_dist_sq);
    }
}

void QuadTree::radiusHelper(double x, double y, double radius,
                             std::vector<std::string>& results) const {
    if (!bounds_.intersectsCircle(x, y, radius)) return;

    double r2 = radius * radius;
    for (const auto& p : points_) {
        double dx = p.x - x;
        double dy = p.y - y;
        if (dx * dx + dy * dy <= r2) {
            results.push_back(p.name);
        }
    }

    if (!divided_) return;

    if (nw_) nw_->radiusHelper(x, y, radius, results);
    if (ne_) ne_->radiusHelper(x, y, radius, results);
    if (sw_) sw_->radiusHelper(x, y, radius, results);
    if (se_) se_->radiusHelper(x, y, radius, results);
}

} // namespace rdt

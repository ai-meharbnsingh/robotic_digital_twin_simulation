// ──────────────────────────────────────────────────────────
// test_quadtree.cpp — Unit tests for rdt/navigation/QuadTree
//
// Tests spatial indexing on REAL warehouse configs.
// Asserts nearest-node and radius queries.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>

#include "rdt/core/Config.h"
#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/QuadTree.h"

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() {
    return RDT_PROJECT_ROOT;
}

// ── simple_grid quad tree tests ─────────────────────────

class QuadTreeSimpleGrid : public ::testing::Test {
protected:
    void SetUp() override {
        auto cfg = Config::loadWarehouseConfig(
            projectRoot() + "/configs/warehouses/simple_grid.json");
        graph.loadFromConfig(cfg);
        qt.buildFromGraphMap(graph);
    }
    GraphMap graph;
    QuadTree qt;
};

TEST_F(QuadTreeSimpleGrid, Size_Is_25) {
    EXPECT_EQ(qt.size(), 25u);
}

TEST_F(QuadTreeSimpleGrid, NearestNode_4p1_4p1_Is_HUB) {
    // HUB is at (4,4), closest to (4.1, 4.1)
    std::string nearest = qt.nearestNode(4.1, 4.1);
    EXPECT_EQ(nearest, "HUB");
}

TEST_F(QuadTreeSimpleGrid, NearestNode_0_0_Is_DOCK1) {
    std::string nearest = qt.nearestNode(0.0, 0.0);
    EXPECT_EQ(nearest, "DOCK_1");
}

TEST_F(QuadTreeSimpleGrid, NearestNode_8_8_Is_DROP1) {
    std::string nearest = qt.nearestNode(8.0, 8.0);
    EXPECT_EQ(nearest, "DROP_1");
}

TEST_F(QuadTreeSimpleGrid, NearestNode_FarAway_ReturnsClosest) {
    // (100, 100) — nearest should be DROP_1 at (8,8)
    std::string nearest = qt.nearestNode(100.0, 100.0);
    EXPECT_EQ(nearest, "DROP_1");
}

TEST_F(QuadTreeSimpleGrid, NodesInRadius_0_0_r3_Returns4Nodes) {
    // Nodes within radius 3.0 of (0,0):
    //   DOCK_1 (0,0) dist=0
    //   N_01   (2,0) dist=2
    //   N_10   (0,2) dist=2
    //   S_11   (2,2) dist=2.828
    auto nodes = qt.nodesInRadius(0.0, 0.0, 3.0);
    EXPECT_EQ(nodes.size(), 4u);

    std::sort(nodes.begin(), nodes.end());
    EXPECT_NE(std::find(nodes.begin(), nodes.end(), "DOCK_1"), nodes.end());
    EXPECT_NE(std::find(nodes.begin(), nodes.end(), "N_01"),   nodes.end());
    EXPECT_NE(std::find(nodes.begin(), nodes.end(), "N_10"),   nodes.end());
    EXPECT_NE(std::find(nodes.begin(), nodes.end(), "S_11"),   nodes.end());
}

TEST_F(QuadTreeSimpleGrid, NodesInRadius_HUB_r0p5_Returns1) {
    // Only HUB itself at (4,4) within 0.5 of (4,4)
    auto nodes = qt.nodesInRadius(4.0, 4.0, 0.5);
    EXPECT_EQ(nodes.size(), 1u);
    EXPECT_EQ(nodes[0], "HUB");
}

TEST_F(QuadTreeSimpleGrid, NodesInRadius_NoMatches) {
    // (50, 50) with tiny radius — nothing there
    auto nodes = qt.nodesInRadius(50.0, 50.0, 0.1);
    EXPECT_TRUE(nodes.empty());
}

TEST_F(QuadTreeSimpleGrid, NodesInRadius_LargeRadius_ReturnsAll) {
    // Radius 100 from center — should get all 25 nodes
    auto nodes = qt.nodesInRadius(4.0, 4.0, 100.0);
    EXPECT_EQ(nodes.size(), 25u);
}

// ── empty quad tree tests ───────────────────────────────

TEST(QuadTreeEmpty, NearestNode_ReturnsEmptyString) {
    QuadTree qt;
    EXPECT_EQ(qt.nearestNode(0.0, 0.0), "");
}

TEST(QuadTreeEmpty, NodesInRadius_ReturnsEmpty) {
    QuadTree qt;
    auto nodes = qt.nodesInRadius(0.0, 0.0, 100.0);
    EXPECT_TRUE(nodes.empty());
}

TEST(QuadTreeEmpty, Size_Is_0) {
    QuadTree qt;
    EXPECT_EQ(qt.size(), 0u);
}

// ── manual insert tests ─────────────────────────────────

TEST(QuadTreeManual, InsertAndQuery) {
    QuadTree qt;
    qt.insert("A", 1.0, 1.0);
    qt.insert("B", 5.0, 5.0);
    qt.insert("C", 3.0, 3.0);

    EXPECT_EQ(qt.size(), 3u);
    EXPECT_EQ(qt.nearestNode(1.1, 1.1), "A");
    EXPECT_EQ(qt.nearestNode(4.9, 4.9), "B");
    EXPECT_EQ(qt.nearestNode(3.0, 3.0), "C");
}

TEST(QuadTreeManual, RadiusQuery) {
    QuadTree qt;
    qt.insert("A", 0.0, 0.0);
    qt.insert("B", 1.0, 0.0);
    qt.insert("C", 10.0, 10.0);

    auto nodes = qt.nodesInRadius(0.0, 0.0, 1.5);
    EXPECT_EQ(nodes.size(), 2u);
    std::sort(nodes.begin(), nodes.end());
    EXPECT_EQ(nodes[0], "A");
    EXPECT_EQ(nodes[1], "B");
}

// ── botvalley quad tree test ────────────────────────────

TEST(QuadTreeBotValley, BuildAndQueryNearest) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/botvalley.json");
    GraphMap graph;
    graph.loadFromConfig(cfg);

    QuadTree qt;
    qt.buildFromGraphMap(graph);

    EXPECT_EQ(qt.size(), 63u);

    // c1 is at (1.7146, -1.7318). Querying near there should return c1.
    std::string nearest = qt.nearestNode(1.71, -1.73);
    EXPECT_EQ(nearest, "c1");
}

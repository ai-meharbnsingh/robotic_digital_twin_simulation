// ──────────────────────────────────────────────────────────
// test_graph.cpp — Unit tests for rdt/navigation/GraphMap
//
// Loads REAL warehouse config files and asserts exact
// node counts, edge counts, neighbors, and distances.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>

#include "rdt/core/Config.h"
#include "rdt/navigation/GraphMap.h"

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() {
    return RDT_PROJECT_ROOT;
}

// ── simple_grid tests ───────────────────────────────────

class GraphMapSimpleGrid : public ::testing::Test {
protected:
    void SetUp() override {
        auto cfg = Config::loadWarehouseConfig(
            projectRoot() + "/configs/warehouses/simple_grid.json");
        graph.loadFromConfig(cfg);
    }
    GraphMap graph;
};

TEST_F(GraphMapSimpleGrid, NodeCount_Is_25) {
    EXPECT_EQ(graph.nodeCount(), 25u);
}

TEST_F(GraphMapSimpleGrid, EdgeCount_Is_80_Directed) {
    // 40 bidirectional edges = 80 directed edges
    EXPECT_EQ(graph.edgeCount(), 80u);
}

TEST_F(GraphMapSimpleGrid, GetNode_HUB_Coordinates) {
    const auto& hub = graph.getNode("HUB");
    EXPECT_EQ(hub.name, "HUB");
    EXPECT_DOUBLE_EQ(hub.x, 4.0);
    EXPECT_DOUBLE_EQ(hub.y, 4.0);
    EXPECT_EQ(hub.type, "hub");
}

TEST_F(GraphMapSimpleGrid, GetNode_DOCK1_Coordinates) {
    const auto& dock = graph.getNode("DOCK_1");
    EXPECT_DOUBLE_EQ(dock.x, 0.0);
    EXPECT_DOUBLE_EQ(dock.y, 0.0);
    EXPECT_EQ(dock.type, "charge");
}

TEST_F(GraphMapSimpleGrid, GetNode_DROP1_Coordinates) {
    const auto& drop = graph.getNode("DROP_1");
    EXPECT_DOUBLE_EQ(drop.x, 8.0);
    EXPECT_DOUBLE_EQ(drop.y, 8.0);
    EXPECT_EQ(drop.type, "drop");
}

TEST_F(GraphMapSimpleGrid, HasNode_Existing) {
    EXPECT_TRUE(graph.hasNode("HUB"));
    EXPECT_TRUE(graph.hasNode("DOCK_1"));
    EXPECT_TRUE(graph.hasNode("DROP_1"));
}

TEST_F(GraphMapSimpleGrid, HasNode_NonExisting) {
    EXPECT_FALSE(graph.hasNode("NONEXISTENT"));
    EXPECT_FALSE(graph.hasNode(""));
}

TEST_F(GraphMapSimpleGrid, GetNeighbors_HUB_Has4Neighbors) {
    auto neighbors = graph.getNeighbors("HUB");
    ASSERT_EQ(neighbors.size(), 4u);

    // Sort for deterministic comparison
    std::sort(neighbors.begin(), neighbors.end());
    EXPECT_EQ(neighbors[0], "S_12");
    EXPECT_EQ(neighbors[1], "S_21");
    EXPECT_EQ(neighbors[2], "S_23");
    EXPECT_EQ(neighbors[3], "S_32");
}

TEST_F(GraphMapSimpleGrid, GetNeighbors_DOCK1_Has2Neighbors) {
    auto neighbors = graph.getNeighbors("DOCK_1");
    ASSERT_EQ(neighbors.size(), 2u);
    std::sort(neighbors.begin(), neighbors.end());
    EXPECT_EQ(neighbors[0], "N_01");
    EXPECT_EQ(neighbors[1], "N_10");
}

TEST_F(GraphMapSimpleGrid, GetNeighbors_NonExisting_Empty) {
    auto neighbors = graph.getNeighbors("NONEXISTENT");
    EXPECT_TRUE(neighbors.empty());
}

TEST_F(GraphMapSimpleGrid, GetEdgeDistance_DOCK1_to_N01_Is_2) {
    double dist = graph.getEdgeDistance("DOCK_1", "N_01");
    EXPECT_DOUBLE_EQ(dist, 2.0);
}

TEST_F(GraphMapSimpleGrid, GetEdgeDistance_HUB_to_S21_Is_2) {
    double dist = graph.getEdgeDistance("HUB", "S_21");
    EXPECT_DOUBLE_EQ(dist, 2.0);
}

TEST_F(GraphMapSimpleGrid, GetEdgeDistance_Diagonal) {
    // DOCK_1 (0,0) to S_11 (2,2): sqrt(4+4) = 2*sqrt(2)
    double dist = graph.getEdgeDistance("DOCK_1", "S_11");
    EXPECT_NEAR(dist, 2.0 * std::sqrt(2.0), 1e-9);
}

TEST_F(GraphMapSimpleGrid, GetEdgeDistance_UnknownNode_Throws) {
    EXPECT_THROW(graph.getEdgeDistance("HUB", "NONEXISTENT"), std::runtime_error);
}

TEST_F(GraphMapSimpleGrid, GetNode_UnknownNode_Throws) {
    EXPECT_THROW(graph.getNode("NONEXISTENT"), std::runtime_error);
}

TEST_F(GraphMapSimpleGrid, GetAllNodes_Returns25) {
    auto all = graph.getAllNodes();
    EXPECT_EQ(all.size(), 25u);
}

// ── botvalley tests ─────────────────────────────────────

class GraphMapBotValley : public ::testing::Test {
protected:
    void SetUp() override {
        auto cfg = Config::loadWarehouseConfig(
            projectRoot() + "/configs/warehouses/botvalley.json");
        graph.loadFromConfig(cfg);
    }
    GraphMap graph;
};

TEST_F(GraphMapBotValley, NodeCount_Is_63) {
    EXPECT_EQ(graph.nodeCount(), 63u);
}

TEST_F(GraphMapBotValley, EdgeCount_Is_126_Directed) {
    // 63 bidirectional edges = 126 directed edges
    EXPECT_EQ(graph.edgeCount(), 126u);
}

TEST_F(GraphMapBotValley, HasNode_c1) {
    EXPECT_TRUE(graph.hasNode("c1"));
}

TEST_F(GraphMapBotValley, HasNode_k3) {
    EXPECT_TRUE(graph.hasNode("k3"));
}

TEST_F(GraphMapBotValley, Node_c1_Coordinates) {
    const auto& c1 = graph.getNode("c1");
    EXPECT_NEAR(c1.x, 1.7146, 0.001);
    EXPECT_NEAR(c1.y, -1.7318, 0.001);
}

TEST_F(GraphMapBotValley, Node_k3_Coordinates) {
    const auto& k3 = graph.getNode("k3");
    EXPECT_NEAR(k3.x, 16.8738, 0.001);
    EXPECT_NEAR(k3.y, -14.2628, 0.001);
}

TEST_F(GraphMapBotValley, GetNeighbors_c1_NotEmpty) {
    auto neighbors = graph.getNeighbors("c1");
    EXPECT_FALSE(neighbors.empty());
    // c1 should be connected to c1|k1_1 (from the edge c1|k1_1 → c1)
    bool has_c1k1_1 = std::find(neighbors.begin(), neighbors.end(), "c1|k1_1")
                      != neighbors.end();
    EXPECT_TRUE(has_c1k1_1);
}

TEST_F(GraphMapBotValley, GetEdgeDistance_Positive) {
    // c1 and c1|k1_1 are connected — distance should be positive
    double dist = graph.getEdgeDistance("c1", "c1|k1_1");
    EXPECT_GT(dist, 0.0);
}

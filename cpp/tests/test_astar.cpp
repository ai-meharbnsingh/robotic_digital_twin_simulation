// ──────────────────────────────────────────────────────────
// test_astar.cpp — Unit tests for rdt/navigation/AStar
//
// Tests A* pathfinding on REAL warehouse configs.
// Asserts path existence, distances, and timing.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>

#include "rdt/core/Config.h"
#include "rdt/navigation/GraphMap.h"
#include "rdt/navigation/AStar.h"

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() {
    return RDT_PROJECT_ROOT;
}

// ── simple_grid A* tests ────────────────────────────────

class AStarSimpleGrid : public ::testing::Test {
protected:
    void SetUp() override {
        auto cfg = Config::loadWarehouseConfig(
            projectRoot() + "/configs/warehouses/simple_grid.json");
        graph.loadFromConfig(cfg);
    }
    GraphMap graph;
};

TEST_F(AStarSimpleGrid, DOCK1_to_DROP1_PathExists) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1");
    EXPECT_TRUE(result.found);
    EXPECT_GT(result.path.size(), 2u);
    EXPECT_EQ(result.path.front(), "DOCK_1");
    EXPECT_EQ(result.path.back(), "DROP_1");
}

TEST_F(AStarSimpleGrid, DOCK1_to_DROP1_DistancePositive) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1");
    EXPECT_TRUE(result.found);
    // Minimum straight-line distance: sqrt(8^2 + 8^2) = 11.31
    // Actual path goes through grid, so distance > 11.31
    EXPECT_GT(result.distance, 11.0);
}

TEST_F(AStarSimpleGrid, DOCK1_to_DROP1_TimingRecorded) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1");
    // time_ms should be recorded (>= 0)
    EXPECT_GE(result.time_ms, 0.0);
}

TEST_F(AStarSimpleGrid, SameNode_TrivialPath) {
    auto result = AStar::findPath(graph, "HUB", "HUB");
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.size(), 1u);
    EXPECT_EQ(result.path[0], "HUB");
    EXPECT_DOUBLE_EQ(result.distance, 0.0);
}

TEST_F(AStarSimpleGrid, NonExistentStart_NotFound) {
    auto result = AStar::findPath(graph, "NONEXISTENT", "HUB");
    EXPECT_FALSE(result.found);
    EXPECT_TRUE(result.path.empty());
}

TEST_F(AStarSimpleGrid, NonExistentGoal_NotFound) {
    auto result = AStar::findPath(graph, "HUB", "NONEXISTENT");
    EXPECT_FALSE(result.found);
    EXPECT_TRUE(result.path.empty());
}

TEST_F(AStarSimpleGrid, BothNonExistent_NotFound) {
    auto result = AStar::findPath(graph, "FAKE_A", "FAKE_B");
    EXPECT_FALSE(result.found);
}

TEST_F(AStarSimpleGrid, Manhattan_ProducesValidPath) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::MANHATTAN);
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "DOCK_1");
    EXPECT_EQ(result.path.back(), "DROP_1");
    EXPECT_GT(result.distance, 0.0);
}

TEST_F(AStarSimpleGrid, Euclidean_ProducesValidPath) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::EUCLIDEAN);
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "DOCK_1");
    EXPECT_EQ(result.path.back(), "DROP_1");
    EXPECT_GT(result.distance, 0.0);
}

TEST_F(AStarSimpleGrid, Chebyshev_ProducesValidPath) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::CHEBYSHEV);
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "DOCK_1");
    EXPECT_EQ(result.path.back(), "DROP_1");
    EXPECT_GT(result.distance, 0.0);
}

TEST_F(AStarSimpleGrid, AllHeuristics_FindSameEndpoints) {
    auto r_m = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::MANHATTAN);
    auto r_e = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::EUCLIDEAN);
    auto r_c = AStar::findPath(graph, "DOCK_1", "DROP_1", Heuristic::CHEBYSHEV);

    EXPECT_TRUE(r_m.found);
    EXPECT_TRUE(r_e.found);
    EXPECT_TRUE(r_c.found);

    // All start at DOCK_1, end at DROP_1
    EXPECT_EQ(r_m.path.front(), "DOCK_1");
    EXPECT_EQ(r_e.path.front(), "DOCK_1");
    EXPECT_EQ(r_c.path.front(), "DOCK_1");
    EXPECT_EQ(r_m.path.back(), "DROP_1");
    EXPECT_EQ(r_e.path.back(), "DROP_1");
    EXPECT_EQ(r_c.path.back(), "DROP_1");
}

TEST_F(AStarSimpleGrid, AdjacentNodes_DirectPath) {
    // DOCK_1 (0,0) and N_01 (2,0) are directly connected
    auto result = AStar::findPath(graph, "DOCK_1", "N_01");
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.size(), 2u);
    EXPECT_DOUBLE_EQ(result.distance, 2.0);
}

TEST_F(AStarSimpleGrid, TurnCost_ProducesValidPath) {
    auto result = AStar::findPath(graph, "DOCK_1", "DROP_1",
                                  Heuristic::EUCLIDEAN, 1.0);
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "DOCK_1");
    EXPECT_EQ(result.path.back(), "DROP_1");
    EXPECT_GT(result.distance, 0.0);
}

// ── botvalley A* tests ──────────────────────────────────

class AStarBotValley : public ::testing::Test {
protected:
    void SetUp() override {
        auto cfg = Config::loadWarehouseConfig(
            projectRoot() + "/configs/warehouses/botvalley.json");
        graph.loadFromConfig(cfg);
    }
    GraphMap graph;
};

TEST_F(AStarBotValley, c1_to_k3_PathExists) {
    auto result = AStar::findPath(graph, "c1", "k3");
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "c1");
    EXPECT_EQ(result.path.back(), "k3");
    EXPECT_GT(result.path.size(), 2u);
    EXPECT_GT(result.distance, 0.0);
}

TEST_F(AStarBotValley, c1_to_k3_DistanceReasonable) {
    auto result = AStar::findPath(graph, "c1", "k3");
    EXPECT_TRUE(result.found);
    // Straight-line c1(1.71, -1.73) to k3(16.87, -14.26): ~18.7
    // Path distance should be >= straight-line
    double straight_line = std::sqrt(
        std::pow(16.87 - 1.71, 2) + std::pow(-14.26 - (-1.73), 2));
    EXPECT_GE(result.distance, straight_line * 0.95);  // allow small tolerance
}

TEST_F(AStarBotValley, Timing_Under_10ms_For_63_Nodes) {
    auto result = AStar::findPath(graph, "c1", "k3");
    EXPECT_TRUE(result.found);
    EXPECT_LT(result.time_ms, 10.0)
        << "A* on 63-node graph took " << result.time_ms << "ms (limit: 10ms)";
}

TEST_F(AStarBotValley, k1_to_k5_PathExists) {
    auto result = AStar::findPath(graph, "k1", "k5");
    EXPECT_TRUE(result.found);
    EXPECT_EQ(result.path.front(), "k1");
    EXPECT_EQ(result.path.back(), "k5");
}

TEST_F(AStarBotValley, Manhattan_vs_Euclidean_BothValid) {
    auto r_m = AStar::findPath(graph, "c1", "k3", Heuristic::MANHATTAN);
    auto r_e = AStar::findPath(graph, "c1", "k3", Heuristic::EUCLIDEAN);

    EXPECT_TRUE(r_m.found);
    EXPECT_TRUE(r_e.found);
    EXPECT_EQ(r_m.path.front(), "c1");
    EXPECT_EQ(r_e.path.front(), "c1");
    EXPECT_EQ(r_m.path.back(), "k3");
    EXPECT_EQ(r_e.path.back(), "k3");
    // Both should find paths with positive distance
    EXPECT_GT(r_m.distance, 0.0);
    EXPECT_GT(r_e.distance, 0.0);
}

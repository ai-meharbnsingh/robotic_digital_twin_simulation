// ──────────────────────────────────────────────────────────
// test_reservation.cpp — Unit tests for rdt/navigation/NodeReservation
//
// Tests: mutual exclusion, lookahead, deadlock detection,
// conflict checking, multi-robot non-overlapping, clear,
// and reservation timing on a 63-node graph.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/navigation/NodeReservation.h"

#include <algorithm>
#include <chrono>
#include <thread>
#include <vector>
#include <string>
#include <set>

using namespace rdt::nav;

// ── Reserve 4 nodes for robot_1, all reserved ──────────

TEST(NodeReservationTest, Reserve4Nodes_AllReserved) {
    NodeReservation table;

    std::vector<std::string> path = {"A1", "A2", "A3", "A4"};
    bool ok = table.reserve("robot_1", path, 4);
    ASSERT_TRUE(ok);

    // Every node must be owned by robot_1
    auto r1 = table.isReserved("A1");
    ASSERT_TRUE(r1.has_value());
    EXPECT_EQ(r1.value(), "robot_1");

    auto r2 = table.isReserved("A2");
    ASSERT_TRUE(r2.has_value());
    EXPECT_EQ(r2.value(), "robot_1");

    auto r3 = table.isReserved("A3");
    ASSERT_TRUE(r3.has_value());
    EXPECT_EQ(r3.value(), "robot_1");

    auto r4 = table.isReserved("A4");
    ASSERT_TRUE(r4.has_value());
    EXPECT_EQ(r4.value(), "robot_1");

    // getReservations should return exactly these 4 nodes
    auto held = table.getReservations("robot_1");
    ASSERT_EQ(held.size(), 4u);
    std::set<std::string> held_set(held.begin(), held.end());
    EXPECT_EQ(held_set, (std::set<std::string>{"A1", "A2", "A3", "A4"}));
}

// ── Robot_2 tries same nodes — conflict detected ───────

TEST(NodeReservationTest, Robot2ConflictOnSameNodes) {
    NodeReservation table;

    std::vector<std::string> path = {"A1", "A2", "A3", "A4"};
    ASSERT_TRUE(table.reserve("robot_1", path, 4));

    // Robot 2 tries the exact same path
    bool ok = table.reserve("robot_2", path, 4);
    EXPECT_FALSE(ok);

    // Robot 2 should hold nothing (atomic reject)
    auto held = table.getReservations("robot_2");
    EXPECT_TRUE(held.empty());

    // Robot 1 still holds all 4
    EXPECT_EQ(table.getReservations("robot_1").size(), 4u);
}

TEST(NodeReservationTest, Robot2ConflictOnPartialOverlap) {
    NodeReservation table;

    ASSERT_TRUE(table.reserve("robot_1", {"A1", "A2", "A3", "A4"}, 4));

    // Robot 2's path overlaps on A3 only (within lookahead)
    bool ok = table.reserve("robot_2", {"B1", "B2", "A3", "B4"}, 4);
    EXPECT_FALSE(ok);

    // Robot 2 holds nothing
    EXPECT_TRUE(table.getReservations("robot_2").empty());
}

// ── Release robot_1 — nodes free ───────────────────────

TEST(NodeReservationTest, ReleaseFreesAllNodes) {
    NodeReservation table;

    std::vector<std::string> path = {"A1", "A2", "A3", "A4"};
    ASSERT_TRUE(table.reserve("robot_1", path, 4));

    table.release("robot_1");

    // All nodes must be free
    EXPECT_FALSE(table.isReserved("A1").has_value());
    EXPECT_FALSE(table.isReserved("A2").has_value());
    EXPECT_FALSE(table.isReserved("A3").has_value());
    EXPECT_FALSE(table.isReserved("A4").has_value());

    // Robot 1 holds nothing
    EXPECT_TRUE(table.getReservations("robot_1").empty());

    // Robot 2 can now take those nodes
    bool ok = table.reserve("robot_2", path, 4);
    EXPECT_TRUE(ok);
    EXPECT_EQ(table.getReservations("robot_2").size(), 4u);
}

// ── Deadlock detection: A holds X, needs Y; B holds Y, needs X ──

TEST(NodeReservationTest, DeadlockDetection_CircularWait) {
    NodeReservation table;

    // Robot A holds node X
    ASSERT_TRUE(table.reserve("robot_A", {"X"}, 1));
    // Robot B holds node Y
    ASSERT_TRUE(table.reserve("robot_B", {"Y"}, 1));

    // Robot A needs Y (held by B), Robot B needs X (held by A) → deadlock
    std::string loser = table.resolveDeadlock(
        "robot_A", "robot_B",
        {"Y"},   // what A needs
        {"X"}    // what B needs
    );

    // "robot_B" > "robot_A" lexicographically → robot_B backs off
    EXPECT_EQ(loser, "robot_B");

    // robot_B's reservations released
    EXPECT_TRUE(table.getReservations("robot_B").empty());
    EXPECT_FALSE(table.isReserved("Y").has_value());

    // robot_A still holds X
    auto held_a = table.getReservations("robot_A");
    ASSERT_EQ(held_a.size(), 1u);
    EXPECT_EQ(held_a[0], "X");
}

TEST(NodeReservationTest, DeadlockDetection_NoDeadlock) {
    NodeReservation table;

    // Robot A holds X
    ASSERT_TRUE(table.reserve("robot_A", {"X"}, 1));
    // Robot B holds Y
    ASSERT_TRUE(table.reserve("robot_B", {"Y"}, 1));

    // Robot A needs Z (not held by B) → no deadlock
    std::string loser = table.resolveDeadlock(
        "robot_A", "robot_B",
        {"Z"},   // A needs Z (free)
        {"X"}    // B needs X (held by A)
    );

    EXPECT_EQ(loser, "");

    // Both robots still hold their nodes
    EXPECT_EQ(table.getReservations("robot_A").size(), 1u);
    EXPECT_EQ(table.getReservations("robot_B").size(), 1u);
}

// ── Lookahead=4 — only first 4 of longer path reserved ──

TEST(NodeReservationTest, LookaheadLimitsReservation) {
    NodeReservation table;

    std::vector<std::string> long_path = {"N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"};
    bool ok = table.reserve("robot_1", long_path, 4);
    ASSERT_TRUE(ok);

    // First 4 reserved
    EXPECT_TRUE(table.isReserved("N1").has_value());
    EXPECT_TRUE(table.isReserved("N2").has_value());
    EXPECT_TRUE(table.isReserved("N3").has_value());
    EXPECT_TRUE(table.isReserved("N4").has_value());

    // Remaining nodes NOT reserved
    EXPECT_FALSE(table.isReserved("N5").has_value());
    EXPECT_FALSE(table.isReserved("N6").has_value());
    EXPECT_FALSE(table.isReserved("N7").has_value());
    EXPECT_FALSE(table.isReserved("N8").has_value());

    // Exactly 4 nodes held
    EXPECT_EQ(table.getReservations("robot_1").size(), 4u);
}

TEST(NodeReservationTest, LookaheadLargerThanPath) {
    NodeReservation table;

    // Path has only 2 nodes but lookahead is 4 — reserve all 2
    std::vector<std::string> short_path = {"S1", "S2"};
    bool ok = table.reserve("robot_1", short_path, 4);
    ASSERT_TRUE(ok);

    EXPECT_TRUE(table.isReserved("S1").has_value());
    EXPECT_TRUE(table.isReserved("S2").has_value());
    EXPECT_EQ(table.getReservations("robot_1").size(), 2u);
}

// ── Multiple robots, non-overlapping paths — all succeed ──

TEST(NodeReservationTest, MultipleRobots_NonOverlapping) {
    NodeReservation table;

    EXPECT_TRUE(table.reserve("robot_1", {"A1", "A2", "A3", "A4"}, 4));
    EXPECT_TRUE(table.reserve("robot_2", {"B1", "B2", "B3", "B4"}, 4));
    EXPECT_TRUE(table.reserve("robot_3", {"C1", "C2", "C3", "C4"}, 4));

    EXPECT_EQ(table.robotCount(), 3u);
    EXPECT_EQ(table.nodeCount(), 12u);

    // Each robot's nodes are correctly attributed
    auto r1 = table.isReserved("A1");
    ASSERT_TRUE(r1.has_value());
    EXPECT_EQ(r1.value(), "robot_1");

    auto r2 = table.isReserved("B3");
    ASSERT_TRUE(r2.has_value());
    EXPECT_EQ(r2.value(), "robot_2");

    auto r3 = table.isReserved("C4");
    ASSERT_TRUE(r3.has_value());
    EXPECT_EQ(r3.value(), "robot_3");
}

// ── clear() releases everything ────────────────────────

TEST(NodeReservationTest, ClearReleasesEverything) {
    NodeReservation table;

    ASSERT_TRUE(table.reserve("robot_1", {"A1", "A2"}, 2));
    ASSERT_TRUE(table.reserve("robot_2", {"B1", "B2"}, 2));
    ASSERT_TRUE(table.reserve("robot_3", {"C1", "C2"}, 2));

    EXPECT_EQ(table.robotCount(), 3u);
    EXPECT_EQ(table.nodeCount(), 6u);

    table.clear();

    EXPECT_EQ(table.robotCount(), 0u);
    EXPECT_EQ(table.nodeCount(), 0u);

    // All nodes free
    EXPECT_FALSE(table.isReserved("A1").has_value());
    EXPECT_FALSE(table.isReserved("B1").has_value());
    EXPECT_FALSE(table.isReserved("C1").has_value());

    // All robots hold nothing
    EXPECT_TRUE(table.getReservations("robot_1").empty());
    EXPECT_TRUE(table.getReservations("robot_2").empty());
    EXPECT_TRUE(table.getReservations("robot_3").empty());
}

// ── checkConflict — read-only conflict detection ───────

TEST(NodeReservationTest, CheckConflict_DetectsExact) {
    NodeReservation table;

    ASSERT_TRUE(table.reserve("robot_1", {"A1", "A2", "A3", "A4"}, 4));

    // Robot 2 wants a path that overlaps on A2 and A4
    auto conflicts = table.checkConflict("robot_2", {"B1", "A2", "B3", "A4"});

    std::set<std::string> conflict_set(conflicts.begin(), conflicts.end());
    EXPECT_EQ(conflict_set, (std::set<std::string>{"A2", "A4"}));
}

TEST(NodeReservationTest, CheckConflict_SameRobotNoConflict) {
    NodeReservation table;

    ASSERT_TRUE(table.reserve("robot_1", {"A1", "A2", "A3", "A4"}, 4));

    // Same robot checking its own path — no conflict
    auto conflicts = table.checkConflict("robot_1", {"A1", "A2", "A3", "A4"});
    EXPECT_TRUE(conflicts.empty());
}

TEST(NodeReservationTest, CheckConflict_EmptyTableNoConflict) {
    NodeReservation table;

    auto conflicts = table.checkConflict("robot_1", {"X1", "X2", "X3"});
    EXPECT_TRUE(conflicts.empty());
}

// ── Re-reservation replaces previous held nodes ────────

TEST(NodeReservationTest, ReReservation_ReplacesPrevious) {
    NodeReservation table;

    ASSERT_TRUE(table.reserve("robot_1", {"A1", "A2", "A3", "A4"}, 4));

    // Robot 1 re-reserves with a new path
    ASSERT_TRUE(table.reserve("robot_1", {"B1", "B2", "B3", "B4"}, 4));

    // Old nodes freed
    EXPECT_FALSE(table.isReserved("A1").has_value());
    EXPECT_FALSE(table.isReserved("A2").has_value());
    EXPECT_FALSE(table.isReserved("A3").has_value());
    EXPECT_FALSE(table.isReserved("A4").has_value());

    // New nodes held
    EXPECT_TRUE(table.isReserved("B1").has_value());
    EXPECT_TRUE(table.isReserved("B2").has_value());
    EXPECT_TRUE(table.isReserved("B3").has_value());
    EXPECT_TRUE(table.isReserved("B4").has_value());

    EXPECT_EQ(table.getReservations("robot_1").size(), 4u);
}

// ── Release non-existent robot — no crash ──────────────

TEST(NodeReservationTest, ReleaseNonExistentRobot) {
    NodeReservation table;
    // Should not crash or throw
    table.release("nonexistent_robot");
    EXPECT_EQ(table.robotCount(), 0u);
}

// ── Empty path reservation ─────────────────────────────

TEST(NodeReservationTest, EmptyPath_ReservesNothing) {
    NodeReservation table;

    bool ok = table.reserve("robot_1", {}, 4);
    EXPECT_TRUE(ok);  // vacuously succeeds
    EXPECT_TRUE(table.getReservations("robot_1").empty());
}

// ── Reservation timing: <15ms for 10 robots on 63-node graph ──

TEST(NodeReservationTest, Timing_10Robots63NodeGraph) {
    NodeReservation table;

    // Generate 63 node names simulating BotValley graph
    std::vector<std::string> all_nodes;
    all_nodes.reserve(63);
    for (int i = 0; i < 63; ++i) {
        all_nodes.push_back("node_" + std::to_string(i));
    }

    // 10 robots, each gets a non-overlapping 4-node slice
    // (nodes 0-3, 4-7, 8-11, ..., 36-39 — fits within 63 nodes)
    auto start = std::chrono::steady_clock::now();

    for (int r = 0; r < 10; ++r) {
        std::vector<std::string> path;
        int base = r * 4;
        for (int n = 0; n < 4 && (base + n) < 63; ++n) {
            path.push_back(all_nodes[base + n]);
        }
        bool ok = table.reserve("robot_" + std::to_string(r), path, 4);
        EXPECT_TRUE(ok) << "Robot " << r << " failed to reserve";
    }

    auto end = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_LT(elapsed_ms, 15) << "Reservation took " << elapsed_ms
                               << "ms, expected <15ms for 10 robots";

    EXPECT_EQ(table.robotCount(), 10u);
    EXPECT_EQ(table.nodeCount(), 40u);
}

// ── Thread safety: concurrent reservations ─────────────

TEST(NodeReservationTest, ConcurrentReservations) {
    NodeReservation table;

    // 4 threads, each reserves a non-overlapping path
    std::vector<std::thread> threads;
    std::vector<bool> results(4, false);

    for (int t = 0; t < 4; ++t) {
        threads.emplace_back([&table, &results, t]() {
            std::vector<std::string> path;
            for (int n = 0; n < 4; ++n) {
                path.push_back("T" + std::to_string(t) + "_N" + std::to_string(n));
            }
            results[t] = table.reserve("thread_robot_" + std::to_string(t), path, 4);
        });
    }

    for (auto& th : threads) {
        th.join();
    }

    // All should succeed (non-overlapping)
    for (int t = 0; t < 4; ++t) {
        EXPECT_TRUE(results[t]) << "Thread " << t << " reservation failed";
    }

    EXPECT_EQ(table.robotCount(), 4u);
    EXPECT_EQ(table.nodeCount(), 16u);
}

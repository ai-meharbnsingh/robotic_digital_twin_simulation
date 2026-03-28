// ──────────────────────────────────────────────────────────
// test_types.cpp — Unit tests for rdt/core/Types.h
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/core/Types.h"

using namespace rdt;

// ── Pose ────────────────────────────────────────────────

TEST(TypesTest, PoseDefaultConstructorInitializesToZero) {
    Pose p;
    EXPECT_DOUBLE_EQ(p.x,     0.0);
    EXPECT_DOUBLE_EQ(p.y,     0.0);
    EXPECT_DOUBLE_EQ(p.z,     0.0);
    EXPECT_DOUBLE_EQ(p.roll,  0.0);
    EXPECT_DOUBLE_EQ(p.pitch, 0.0);
    EXPECT_DOUBLE_EQ(p.yaw,   0.0);
}

TEST(TypesTest, PoseEqualityOperator) {
    Pose a{1.0, 2.0, 3.0, 0.1, 0.2, 0.3};
    Pose b{1.0, 2.0, 3.0, 0.1, 0.2, 0.3};
    Pose c{1.0, 2.0, 3.0, 0.1, 0.2, 0.4};  // yaw differs
    EXPECT_EQ(a, b);
    EXPECT_NE(a, c);
}

TEST(TypesTest, PoseJsonRoundtrip) {
    Pose original{1.5, -2.3, 0.0, 0.1, 0.0, 3.14};
    Json::Value j = to_json(original);
    Pose restored = pose_from_json(j);

    EXPECT_DOUBLE_EQ(restored.x,     1.5);
    EXPECT_DOUBLE_EQ(restored.y,    -2.3);
    EXPECT_DOUBLE_EQ(restored.z,     0.0);
    EXPECT_DOUBLE_EQ(restored.roll,  0.1);
    EXPECT_DOUBLE_EQ(restored.pitch, 0.0);
    EXPECT_DOUBLE_EQ(restored.yaw,   3.14);
    EXPECT_EQ(original, restored);
}

// ── Velocity ────────────────────────────────────────────

TEST(TypesTest, VelocityDefaultZero) {
    Velocity v;
    EXPECT_DOUBLE_EQ(v.linear,  0.0);
    EXPECT_DOUBLE_EQ(v.angular, 0.0);
}

TEST(TypesTest, VelocityJsonRoundtrip) {
    Velocity original{1.5, 0.3};
    Json::Value j = to_json(original);
    Velocity restored = velocity_from_json(j);
    EXPECT_EQ(original, restored);
}

// ── BatteryState ────────────────────────────────────────

TEST(TypesTest, BatteryStateDefaultValues) {
    BatteryState b;
    EXPECT_DOUBLE_EQ(b.percentage, 100.0);
    EXPECT_DOUBLE_EQ(b.voltage,    0.0);
    EXPECT_FALSE(b.charging);
    EXPECT_DOUBLE_EQ(b.charge_rate, 0.0);
}

TEST(TypesTest, BatteryStateJsonRoundtrip) {
    BatteryState original{85.5, 24.0, true, 0.5};
    Json::Value j = to_json(original);
    BatteryState restored = battery_state_from_json(j);
    EXPECT_EQ(original, restored);
}

// ── ObstacleReading ─────────────────────────────────────

TEST(TypesTest, ObstacleReadingDefaultValues) {
    ObstacleReading r;
    EXPECT_FALSE(r.detected);
    EXPECT_DOUBLE_EQ(r.range, 0.0);
}

TEST(TypesTest, ObstacleReadingJsonRoundtrip) {
    ObstacleReading original{true, 1.23};
    Json::Value j = to_json(original);
    ObstacleReading restored = obstacle_reading_from_json(j);
    EXPECT_EQ(original, restored);
}

// ── Enums ───────────────────────────────────────────────

TEST(TypesTest, RobotStateEnumValues) {
    // Verify integer values of the enum class
    EXPECT_EQ(static_cast<int>(RobotState::IDLE),      0);
    EXPECT_EQ(static_cast<int>(RobotState::MOVING),     1);
    EXPECT_EQ(static_cast<int>(RobotState::CHARGING),   2);
    EXPECT_EQ(static_cast<int>(RobotState::LOADING),    3);
    EXPECT_EQ(static_cast<int>(RobotState::UNLOADING),  4);
    EXPECT_EQ(static_cast<int>(RobotState::ERROR),      5);
    EXPECT_EQ(static_cast<int>(RobotState::OFFLINE),    6);
    EXPECT_EQ(static_cast<int>(RobotState::DOCKING),    7);
}

TEST(TypesTest, RobotStateToString) {
    EXPECT_EQ(robot_state_to_string(RobotState::IDLE),      "IDLE");
    EXPECT_EQ(robot_state_to_string(RobotState::MOVING),    "MOVING");
    EXPECT_EQ(robot_state_to_string(RobotState::CHARGING),  "CHARGING");
    EXPECT_EQ(robot_state_to_string(RobotState::DOCKING),   "DOCKING");
}

TEST(TypesTest, TaskStateEnumValues) {
    EXPECT_EQ(static_cast<int>(TaskState::NOT_ASSIGNED), 0);
    EXPECT_EQ(static_cast<int>(TaskState::ACCEPTED),     1);
    EXPECT_EQ(static_cast<int>(TaskState::ASSIGNED),     2);
    EXPECT_EQ(static_cast<int>(TaskState::IN_PROGRESS),  3);
    EXPECT_EQ(static_cast<int>(TaskState::COMPLETED),    4);
    EXPECT_EQ(static_cast<int>(TaskState::FAILED),       5);
    EXPECT_EQ(static_cast<int>(TaskState::CANCELLED),    6);
}

TEST(TypesTest, TaskTypeEnumValues) {
    EXPECT_EQ(static_cast<int>(TaskType::MOVE),   0);
    EXPECT_EQ(static_cast<int>(TaskType::PICK),   1);
    EXPECT_EQ(static_cast<int>(TaskType::PLACE),  2);
    EXPECT_EQ(static_cast<int>(TaskType::CHARGE), 3);
    EXPECT_EQ(static_cast<int>(TaskType::PARK),   4);
}

TEST(TypesTest, RobotTypeStringRoundtrip) {
    EXPECT_EQ(robot_type_to_string(RobotType::DIFFERENTIAL_DRIVE), "differential_drive");
    EXPECT_EQ(robot_type_to_string(RobotType::UNIDIRECTIONAL),     "unidirectional");
    EXPECT_EQ(robot_type_to_string(RobotType::OMNIDIRECTIONAL),    "omnidirectional");
    EXPECT_EQ(robot_type_from_string("differential_drive"), RobotType::DIFFERENTIAL_DRIVE);
    EXPECT_EQ(robot_type_from_string("unidirectional"),     RobotType::UNIDIRECTIONAL);
    EXPECT_EQ(robot_type_from_string("omnidirectional"),    RobotType::OMNIDIRECTIONAL);
}

// ── MapNode ─────────────────────────────────────────────

TEST(TypesTest, MapNodeToJsonRoundtrip) {
    MapNode original{"DOCK_1", 0.0, 0.0, "charge"};
    Json::Value j = to_json(original);

    EXPECT_EQ(j["name"].asString(), "DOCK_1");
    EXPECT_DOUBLE_EQ(j["x"].asDouble(), 0.0);
    EXPECT_DOUBLE_EQ(j["y"].asDouble(), 0.0);
    EXPECT_EQ(j["type"].asString(), "charge");

    MapNode restored = map_node_from_json(j);
    EXPECT_EQ(original, restored);
}

TEST(TypesTest, MapNodeWithRealValues) {
    MapNode n{"HUB", 4.0, 4.0, "hub"};
    Json::Value j = to_json(n);
    MapNode restored = map_node_from_json(j);

    EXPECT_EQ(restored.name, "HUB");
    EXPECT_DOUBLE_EQ(restored.x, 4.0);
    EXPECT_DOUBLE_EQ(restored.y, 4.0);
    EXPECT_EQ(restored.type, "hub");
    EXPECT_EQ(n, restored);
}

// ── MapEdge ─────────────────────────────────────────────

TEST(TypesTest, MapEdgeToJsonRoundtrip) {
    MapEdge original{"DOCK_1", "N_01", true};
    Json::Value j = to_json(original);

    EXPECT_EQ(j["from"].asString(), "DOCK_1");
    EXPECT_EQ(j["to"].asString(), "N_01");
    EXPECT_TRUE(j["bidirectional"].asBool());

    MapEdge restored = map_edge_from_json(j);
    EXPECT_EQ(original, restored);
}

TEST(TypesTest, MapEdgeDirectional) {
    MapEdge e{"A", "B", false};
    Json::Value j = to_json(e);
    MapEdge restored = map_edge_from_json(j);

    EXPECT_EQ(restored.from, "A");
    EXPECT_EQ(restored.to, "B");
    EXPECT_FALSE(restored.bidirectional);
    EXPECT_EQ(e, restored);
}

TEST(TypesTest, MapEdgeDefaultBidirectional) {
    // When JSON has no bidirectional key, it defaults to true
    Json::Value j;
    j["from"] = "X";
    j["to"]   = "Y";
    MapEdge e = map_edge_from_json(j);
    EXPECT_TRUE(e.bidirectional);
}

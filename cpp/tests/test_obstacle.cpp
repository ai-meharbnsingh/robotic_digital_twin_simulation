// ──────────────────────────────────────────────────────────
// test_obstacle.cpp — Unit tests for ObstacleHandler
//
// Tests correct action at each threshold boundary.
// All thresholds from config YAML — verified against the
// actual values loaded from differential_drive.yaml.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/robot/ObstacleHandler.h"
#include "rdt/core/Config.h"

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() { return RDT_PROJECT_ROOT; }

static RobotConfig loadDiffDriveConfig() {
    return Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
}

static RobotConfig loadUniConfig() {
    return Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
}

// ── Thresholds match config ───────────────────────────

TEST(ObstacleHandlerTest, ThresholdsMatchDiffDriveConfig) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);

    EXPECT_DOUBLE_EQ(oh.getCriticalThreshold(), cfg.obstacle_thresholds.critical_m);
    EXPECT_DOUBLE_EQ(oh.getWarningThreshold(),  cfg.obstacle_thresholds.warning_m);
    EXPECT_DOUBLE_EQ(oh.getPlanningThreshold(), cfg.obstacle_thresholds.planning_m);
}

TEST(ObstacleHandlerTest, DiffDriveThresholdValues) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);

    EXPECT_DOUBLE_EQ(oh.getCriticalThreshold(), 0.7);
    EXPECT_DOUBLE_EQ(oh.getWarningThreshold(),  0.8);
    EXPECT_DOUBLE_EQ(oh.getPlanningThreshold(), 1.5);
}

// ── EMERGENCY_STOP zone ───────────────────────────────

TEST(ObstacleHandlerTest, EmergencyStopAtZero) {
    ObstacleHandler oh(loadDiffDriveConfig());
    EXPECT_EQ(oh.evaluate(0.0), ObstacleHandler::Action::EMERGENCY_STOP);
}

TEST(ObstacleHandlerTest, EmergencyStopBelowCritical) {
    ObstacleHandler oh(loadDiffDriveConfig());
    EXPECT_EQ(oh.evaluate(0.5), ObstacleHandler::Action::EMERGENCY_STOP);
}

TEST(ObstacleHandlerTest, EmergencyStopAtCriticalExact) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    EXPECT_EQ(oh.evaluate(cfg.obstacle_thresholds.critical_m),
              ObstacleHandler::Action::EMERGENCY_STOP);
}

// ── DECELERATE zone ───────────────────────────────────

TEST(ObstacleHandlerTest, DecelerateJustAboveCritical) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double just_above = cfg.obstacle_thresholds.critical_m + 0.001;
    EXPECT_EQ(oh.evaluate(just_above), ObstacleHandler::Action::DECELERATE);
}

TEST(ObstacleHandlerTest, DecelerateAtWarningExact) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    EXPECT_EQ(oh.evaluate(cfg.obstacle_thresholds.warning_m),
              ObstacleHandler::Action::DECELERATE);
}

TEST(ObstacleHandlerTest, DecelerateMidWarningZone) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double mid = (cfg.obstacle_thresholds.critical_m +
                  cfg.obstacle_thresholds.warning_m) / 2.0;
    EXPECT_EQ(oh.evaluate(mid), ObstacleHandler::Action::DECELERATE);
}

// ── REPLAN zone ───────────────────────────────────────

TEST(ObstacleHandlerTest, ReplanJustAboveWarning) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double just_above = cfg.obstacle_thresholds.warning_m + 0.001;
    EXPECT_EQ(oh.evaluate(just_above), ObstacleHandler::Action::REPLAN);
}

TEST(ObstacleHandlerTest, ReplanAtPlanningExact) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    EXPECT_EQ(oh.evaluate(cfg.obstacle_thresholds.planning_m),
              ObstacleHandler::Action::REPLAN);
}

TEST(ObstacleHandlerTest, ReplanMidPlanningZone) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double mid = (cfg.obstacle_thresholds.warning_m +
                  cfg.obstacle_thresholds.planning_m) / 2.0;
    EXPECT_EQ(oh.evaluate(mid), ObstacleHandler::Action::REPLAN);
}

// ── NONE zone ─────────────────────────────────────────

TEST(ObstacleHandlerTest, NoneJustAbovePlanning) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double just_above = cfg.obstacle_thresholds.planning_m + 0.001;
    EXPECT_EQ(oh.evaluate(just_above), ObstacleHandler::Action::NONE);
}

TEST(ObstacleHandlerTest, NoneFarAway) {
    ObstacleHandler oh(loadDiffDriveConfig());
    EXPECT_EQ(oh.evaluate(100.0), ObstacleHandler::Action::NONE);
}

TEST(ObstacleHandlerTest, NoneVeryFarAway) {
    ObstacleHandler oh(loadDiffDriveConfig());
    EXPECT_EQ(oh.evaluate(1e6), ObstacleHandler::Action::NONE);
}

// ── Boundary precision ────────────────────────────────

TEST(ObstacleHandlerTest, BoundaryPrecision_CriticalToDecelerate) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double critical = cfg.obstacle_thresholds.critical_m;

    // At critical → EMERGENCY_STOP
    EXPECT_EQ(oh.evaluate(critical), ObstacleHandler::Action::EMERGENCY_STOP);
    // Epsilon above → DECELERATE
    EXPECT_EQ(oh.evaluate(critical + 1e-10), ObstacleHandler::Action::DECELERATE);
}

TEST(ObstacleHandlerTest, BoundaryPrecision_WarningToReplan) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double warning = cfg.obstacle_thresholds.warning_m;

    // At warning → DECELERATE
    EXPECT_EQ(oh.evaluate(warning), ObstacleHandler::Action::DECELERATE);
    // Epsilon above → REPLAN
    EXPECT_EQ(oh.evaluate(warning + 1e-10), ObstacleHandler::Action::REPLAN);
}

TEST(ObstacleHandlerTest, BoundaryPrecision_PlanningToNone) {
    auto cfg = loadDiffDriveConfig();
    ObstacleHandler oh(cfg);
    double planning = cfg.obstacle_thresholds.planning_m;

    // At planning → REPLAN
    EXPECT_EQ(oh.evaluate(planning), ObstacleHandler::Action::REPLAN);
    // Epsilon above → NONE
    EXPECT_EQ(oh.evaluate(planning + 1e-10), ObstacleHandler::Action::NONE);
}

// ── Action to string ──────────────────────────────────

TEST(ObstacleHandlerTest, ActionToStringNone) {
    EXPECT_EQ(ObstacleHandler::actionToString(ObstacleHandler::Action::NONE), "NONE");
}

TEST(ObstacleHandlerTest, ActionToStringReplan) {
    EXPECT_EQ(ObstacleHandler::actionToString(ObstacleHandler::Action::REPLAN), "REPLAN");
}

TEST(ObstacleHandlerTest, ActionToStringDecelerate) {
    EXPECT_EQ(ObstacleHandler::actionToString(ObstacleHandler::Action::DECELERATE), "DECELERATE");
}

TEST(ObstacleHandlerTest, ActionToStringEmergencyStop) {
    EXPECT_EQ(ObstacleHandler::actionToString(ObstacleHandler::Action::EMERGENCY_STOP), "EMERGENCY_STOP");
}

// ── Unidirectional config (same thresholds, different robot) ──

TEST(ObstacleHandlerTest, UniThresholdsMatchConfig) {
    auto cfg = loadUniConfig();
    ObstacleHandler oh(cfg);

    EXPECT_DOUBLE_EQ(oh.getCriticalThreshold(), cfg.obstacle_thresholds.critical_m);
    EXPECT_DOUBLE_EQ(oh.getWarningThreshold(),  cfg.obstacle_thresholds.warning_m);
    EXPECT_DOUBLE_EQ(oh.getPlanningThreshold(), cfg.obstacle_thresholds.planning_m);
}

TEST(ObstacleHandlerTest, UniEmergencyStopWorks) {
    ObstacleHandler oh(loadUniConfig());
    EXPECT_EQ(oh.evaluate(0.3), ObstacleHandler::Action::EMERGENCY_STOP);
}

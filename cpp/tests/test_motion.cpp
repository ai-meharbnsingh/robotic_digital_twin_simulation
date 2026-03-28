// ──────────────────────────────────────────────────────────
// test_motion.cpp — Unit tests for MotionController
//
// Tests velocity computation, limit enforcement, acceleration
// clamping, and stop-at-target behavior. All limits from YAML.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/robot/MotionController.h"
#include "rdt/core/Config.h"

#include <cmath>

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() { return RDT_PROJECT_ROOT; }

static RobotConfig loadDiffDriveConfig() {
    return Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
}

// ── Helper: distance between two poses ────────────────

static double poseDist(const Pose& a, const Pose& b) {
    double dx = b.x - a.x;
    double dy = b.y - a.y;
    return std::sqrt(dx * dx + dy * dy);
}

// ── Tolerance from config ─────────────────────────────

TEST(MotionControllerTest, ToleranceMatchesConfig) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);
    EXPECT_DOUBLE_EQ(mc.getPositionTolerance(), 0.07);
    EXPECT_DOUBLE_EQ(mc.getAngularTolerance(), 0.025);
}

// ── Zero velocity at target ───────────────────────────

TEST(MotionControllerTest, ZeroVelocityAtTarget) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{1.0, 2.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{1.0, 2.0, 0.0, 0.0, 0.0, 0.0};

    Velocity v = mc.computeVelocity(current, target);
    EXPECT_DOUBLE_EQ(v.linear, 0.0);
    EXPECT_DOUBLE_EQ(v.angular, 0.0);
}

TEST(MotionControllerTest, ZeroVelocityWithinTolerance) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{1.0, 2.0, 0.0, 0.0, 0.0, 0.0};
    // Target within position_tolerance (0.07m)
    Pose target{1.05, 2.0, 0.0, 0.0, 0.0, 0.0};
    ASSERT_LT(poseDist(current, target), cfg.motion.position_tolerance);

    Velocity v = mc.computeVelocity(current, target);
    EXPECT_DOUBLE_EQ(v.linear, 0.0);
    EXPECT_DOUBLE_EQ(v.angular, 0.0);
}

TEST(MotionControllerTest, IsAtTargetTrue) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{0.03, 0.04, 0.0, 0.0, 0.0, 0.0}; // dist = 0.05 < 0.07
    EXPECT_TRUE(mc.isAtTarget(current, target));
}

TEST(MotionControllerTest, IsAtTargetFalse) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{1.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    EXPECT_FALSE(mc.isAtTarget(current, target));
}

// ── Non-zero velocity when not at target ──────────────

TEST(MotionControllerTest, NonZeroVelocityWhenFar) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{5.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    Velocity v = mc.computeVelocity(current, target, 0.1);
    EXPECT_GT(v.linear, 0.0);
}

// ── Max linear velocity respected ─────────────────────

TEST(MotionControllerTest, LinearVelocityNeverExceedsMax) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    // Target very far away — should want to go fast, but clamped
    Pose target{1000.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    // Run multiple steps to allow acceleration to build up
    Velocity v;
    for (int i = 0; i < 1000; ++i) {
        v = mc.computeVelocity(current, target, 0.1);
    }

    EXPECT_LE(v.linear, cfg.motion.max_linear_velocity);
}

// ── Max angular velocity respected ────────────────────

TEST(MotionControllerTest, AngularVelocityNeverExceedsMax) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    // Target directly behind — requires large angular correction
    Pose target{-5.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    Velocity v;
    for (int i = 0; i < 1000; ++i) {
        v = mc.computeVelocity(current, target, 0.1);
    }

    EXPECT_LE(std::abs(v.angular), cfg.motion.max_angular_velocity);
}

// ── Acceleration limiting ─────────────────────────────

TEST(MotionControllerTest, AccelerationIsLimited) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{100.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    double dt = 0.1;

    // First step from rest — velocity should be limited by acceleration
    Velocity v1 = mc.computeVelocity(current, target, dt);
    double max_first_step = cfg.motion.linear_acceleration * dt;

    EXPECT_LE(v1.linear, max_first_step + 1e-9)
        << "First step velocity should be limited by acceleration";
}

TEST(MotionControllerTest, VelocityIncreasesGradually) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{100.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    double dt = 0.1;

    Velocity v1 = mc.computeVelocity(current, target, dt);
    Velocity v2 = mc.computeVelocity(current, target, dt);

    // Second velocity should be >= first (accelerating)
    EXPECT_GE(v2.linear, v1.linear - 1e-9);
}

// ── Direction computation ─────────────────────────────

TEST(MotionControllerTest, CorrectDirectionXPositive) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0}; // yaw=0 → facing +x
    Pose target{5.0, 0.0, 0.0, 0.0, 0.0, 0.0};

    Velocity v = mc.computeVelocity(current, target, 0.1);
    EXPECT_GT(v.linear, 0.0);
    // When facing target directly, angular should be near zero
    EXPECT_NEAR(v.angular, 0.0, 0.1);
}

TEST(MotionControllerTest, AngularCorrectionWhenOffHeading) {
    auto cfg = loadDiffDriveConfig();
    MotionController mc(cfg);

    // Facing +x (yaw=0) but target is directly to the left (+y direction)
    Pose current{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    Pose target{0.0, 5.0, 0.0, 0.0, 0.0, 0.0};

    Velocity v = mc.computeVelocity(current, target, 0.1);
    // Should have positive angular velocity (counter-clockwise to face +y)
    EXPECT_GT(v.angular, 0.0);
}

// ── Config values used ────────────────────────────────

TEST(MotionControllerTest, DiffDriveMaxLinearFromYAML) {
    auto cfg = loadDiffDriveConfig();
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 2.0);
}

TEST(MotionControllerTest, DiffDriveMaxAngularFromYAML) {
    auto cfg = loadDiffDriveConfig();
    EXPECT_DOUBLE_EQ(cfg.motion.max_angular_velocity, 2.5);
}

TEST(MotionControllerTest, DiffDriveAccelerationFromYAML) {
    auto cfg = loadDiffDriveConfig();
    EXPECT_DOUBLE_EQ(cfg.motion.linear_acceleration, 0.8);
    EXPECT_DOUBLE_EQ(cfg.motion.linear_deceleration, 0.8);
}

TEST(MotionControllerTest, DiffDrivePositionToleranceFromYAML) {
    auto cfg = loadDiffDriveConfig();
    EXPECT_DOUBLE_EQ(cfg.motion.position_tolerance, 0.07);
}

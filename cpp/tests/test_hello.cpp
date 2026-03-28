// ──────────────────────────────────────────────────────────
// test_hello.cpp — Smoke test: verify core headers compile
// and basic types are constructible.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/version.h"
#include "rdt/core/Types.h"

TEST(HelloTest, VersionDefined) {
    EXPECT_GE(RDT_VERSION_MAJOR, 0);
    EXPECT_GE(RDT_VERSION_MINOR, 0);
    EXPECT_GE(RDT_VERSION_PATCH, 0);
}

TEST(HelloTest, PoseDefaultsToOrigin) {
    rdt::Pose pose;
    EXPECT_DOUBLE_EQ(pose.x, 0.0);
    EXPECT_DOUBLE_EQ(pose.y, 0.0);
    EXPECT_DOUBLE_EQ(pose.yaw, 0.0);
}

TEST(HelloTest, VelocityDefaultsToZero) {
    rdt::Velocity vel;
    EXPECT_DOUBLE_EQ(vel.linear, 0.0);
    EXPECT_DOUBLE_EQ(vel.angular, 0.0);
}

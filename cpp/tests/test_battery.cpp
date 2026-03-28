// ──────────────────────────────────────────────────────────
// test_battery.cpp — Unit tests for BatteryModel
//
// Verifies charge/discharge timing matches config EXACTLY
// (0.01% tolerance). All durations from YAML — no hardcoded
// 450/600/54000/60000 values in test assertions; we read
// the config and compute expected values.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/robot/BatteryModel.h"
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

static RobotConfig loadUniConfig() {
    return Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
}

// ── Initial state ─────────────────────────────────────

TEST(BatteryModelTest, InitialPercentageFromConfig) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    EXPECT_DOUBLE_EQ(bm.getPercentage(), static_cast<double>(cfg.battery.initial_charge_pct));
}

TEST(BatteryModelTest, InitialVoltageFullCharge) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    // SOC=100% → 42 + 6*1.0 = 48V
    EXPECT_DOUBLE_EQ(bm.getVoltage(), 48.0);
}

TEST(BatteryModelTest, NotChargingInitially) {
    BatteryModel bm(loadDiffDriveConfig());
    EXPECT_FALSE(bm.isCharging());
}

TEST(BatteryModelTest, NotCriticalWhenFull) {
    BatteryModel bm(loadDiffDriveConfig());
    EXPECT_FALSE(bm.isCritical());
}

// ── Voltage model ─────────────────────────────────────

TEST(BatteryModelTest, VoltageAtZeroPercent) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    // Discharge fully
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    bm.update(discharge_s * 2.0, false, false); // ensure 0%
    EXPECT_NEAR(bm.getPercentage(), 0.0, 0.01);
    EXPECT_NEAR(bm.getVoltage(), 42.0, 0.01);
}

TEST(BatteryModelTest, VoltageAt50Percent) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    // Discharge to 50%
    double half_time = static_cast<double>(cfg.battery.discharge_duration_s) / 2.0;
    bm.update(half_time, false, false);
    EXPECT_NEAR(bm.getPercentage(), 50.0, 0.01);
    // 42 + 6*0.5 = 45V
    EXPECT_NEAR(bm.getVoltage(), 45.0, 0.01);
}

// ── Discharge timing (DiffDrive) ──────────────────────

TEST(BatteryModelTest, DiffDriveBaseDischarge_FullDuration) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);

    // Discharge for exactly discharge_duration_s with no motion, no attachment
    bm.update(discharge_s, false, false);
    EXPECT_NEAR(bm.getPercentage(), 0.0, 0.01);
}

TEST(BatteryModelTest, DiffDriveBaseDischarge_HalfDuration) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);
    double half = static_cast<double>(cfg.battery.discharge_duration_s) / 2.0;

    bm.update(half, false, false);
    EXPECT_NEAR(bm.getPercentage(), 50.0, 0.01);
}

TEST(BatteryModelTest, DiffDriveMotionDischarge_FasterThanBase) {
    auto cfg = loadDiffDriveConfig();

    BatteryModel bm_base(cfg);
    BatteryModel bm_moving(cfg);

    double step = 1000.0; // 1000 seconds
    bm_base.update(step, false, false);
    bm_moving.update(step, true, false);

    // Moving should drain more
    EXPECT_LT(bm_moving.getPercentage(), bm_base.getPercentage());

    // Verify the ratio matches motion_energy_factor
    double base_drain = 100.0 - bm_base.getPercentage();
    double move_drain = 100.0 - bm_moving.getPercentage();
    double ratio = move_drain / base_drain;
    EXPECT_NEAR(ratio, cfg.battery.motion_energy_factor, 0.001);
}

TEST(BatteryModelTest, DiffDriveAttachmentDischarge) {
    auto cfg = loadDiffDriveConfig();

    BatteryModel bm_base(cfg);
    BatteryModel bm_attach(cfg);

    double step = 1000.0;
    bm_base.update(step, false, false);
    bm_attach.update(step, false, true);

    double base_drain = 100.0 - bm_base.getPercentage();
    double attach_drain = 100.0 - bm_attach.getPercentage();
    double ratio = attach_drain / base_drain;
    EXPECT_NEAR(ratio, cfg.battery.attachment_energy_factor, 0.001);
}

TEST(BatteryModelTest, DiffDriveBothFactors) {
    auto cfg = loadDiffDriveConfig();

    BatteryModel bm_base(cfg);
    BatteryModel bm_both(cfg);

    double step = 1000.0;
    bm_base.update(step, false, false);
    bm_both.update(step, true, true);

    double base_drain = 100.0 - bm_base.getPercentage();
    double both_drain = 100.0 - bm_both.getPercentage();
    double expected_factor = cfg.battery.motion_energy_factor *
                             cfg.battery.attachment_energy_factor;
    double ratio = both_drain / base_drain;
    EXPECT_NEAR(ratio, expected_factor, 0.001);
}

// ── Charge timing (DiffDrive) ─────────────────────────

TEST(BatteryModelTest, DiffDriveCharge_FullDuration) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Drain to 0%
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    bm.update(discharge_s * 2.0, false, false);
    EXPECT_NEAR(bm.getPercentage(), 0.0, 0.01);

    // Charge for exactly charge_duration_s
    bm.startCharging();
    EXPECT_TRUE(bm.isCharging());

    double charge_s = static_cast<double>(cfg.battery.charge_duration_s);
    bm.update(charge_s, false, false);
    EXPECT_NEAR(bm.getPercentage(), 100.0, 0.01);
}

TEST(BatteryModelTest, DiffDriveCharge_HalfDuration) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Drain to 0%
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    bm.update(discharge_s * 2.0, false, false);

    bm.startCharging();
    double half_charge = static_cast<double>(cfg.battery.charge_duration_s) / 2.0;
    bm.update(half_charge, false, false);
    EXPECT_NEAR(bm.getPercentage(), 50.0, 0.01);
}

// ── Discharge timing (Unidirectional) ─────────────────

TEST(BatteryModelTest, UniBaseDischarge_FullDuration) {
    auto cfg = loadUniConfig();
    BatteryModel bm(cfg);
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);

    bm.update(discharge_s, false, false);
    EXPECT_NEAR(bm.getPercentage(), 0.0, 0.01);
}

TEST(BatteryModelTest, UniCharge_FullDuration) {
    auto cfg = loadUniConfig();
    BatteryModel bm(cfg);

    // Drain to 0%
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    bm.update(discharge_s * 2.0, false, false);

    bm.startCharging();
    double charge_s = static_cast<double>(cfg.battery.charge_duration_s);
    bm.update(charge_s, false, false);
    EXPECT_NEAR(bm.getPercentage(), 100.0, 0.01);
}

TEST(BatteryModelTest, UniMotionFactor) {
    auto cfg = loadUniConfig();

    BatteryModel bm_base(cfg);
    BatteryModel bm_moving(cfg);

    double step = 1000.0;
    bm_base.update(step, false, false);
    bm_moving.update(step, true, false);

    double base_drain = 100.0 - bm_base.getPercentage();
    double move_drain = 100.0 - bm_moving.getPercentage();
    double ratio = move_drain / base_drain;
    EXPECT_NEAR(ratio, cfg.battery.motion_energy_factor, 0.001);
}

// ── Charging start/stop ───────────────────────────────

TEST(BatteryModelTest, StartStopCharging) {
    BatteryModel bm(loadDiffDriveConfig());
    EXPECT_FALSE(bm.isCharging());

    bm.startCharging();
    EXPECT_TRUE(bm.isCharging());

    bm.stopCharging();
    EXPECT_FALSE(bm.isCharging());
}

TEST(BatteryModelTest, ChargingStopsDischarge) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Drain a bit
    bm.update(1000.0, true, false);
    double before_charge = bm.getPercentage();

    // Start charging — SOC should increase
    bm.startCharging();
    bm.update(100.0, false, false);
    EXPECT_GT(bm.getPercentage(), before_charge);
}

// ── Critical threshold ────────────────────────────────

TEST(BatteryModelTest, CriticalBelowThreshold) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Discharge until just below critical_threshold_pct (20%)
    // We need to drain 81% of discharge_duration_s
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    double target_pct = static_cast<double>(cfg.battery.critical_threshold_pct) - 1.0;
    double drain_fraction = (100.0 - target_pct) / 100.0;
    bm.update(discharge_s * drain_fraction, false, false);

    EXPECT_TRUE(bm.isCritical());
}

TEST(BatteryModelTest, NotCriticalAboveThreshold) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Discharge until just above critical (e.g., 21%)
    double discharge_s = static_cast<double>(cfg.battery.discharge_duration_s);
    double target_pct = static_cast<double>(cfg.battery.critical_threshold_pct) + 1.0;
    double drain_fraction = (100.0 - target_pct) / 100.0;
    bm.update(discharge_s * drain_fraction, false, false);

    EXPECT_FALSE(bm.isCritical());
}

// ── SOC clamping ──────────────────────────────────────

TEST(BatteryModelTest, SocNeverBelowZero) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Discharge for way longer than possible
    bm.update(1e9, true, true);
    EXPECT_GE(bm.getPercentage(), 0.0);
}

TEST(BatteryModelTest, SocNeverAboveHundred) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    bm.startCharging();
    // Charge for way longer than needed
    bm.update(1e9, false, false);
    EXPECT_LE(bm.getPercentage(), 100.0);
}

// ── Zero/negative dt ──────────────────────────────────

TEST(BatteryModelTest, ZeroDtNoChange) {
    BatteryModel bm(loadDiffDriveConfig());
    double before = bm.getPercentage();
    bm.update(0.0, true, true);
    EXPECT_DOUBLE_EQ(bm.getPercentage(), before);
}

TEST(BatteryModelTest, NegativeDtNoChange) {
    BatteryModel bm(loadDiffDriveConfig());
    double before = bm.getPercentage();
    bm.update(-10.0, true, true);
    EXPECT_DOUBLE_EQ(bm.getPercentage(), before);
}

// ── Precise 0.01% accuracy check ─────────────────────

TEST(BatteryModelTest, DischargeAccuracy_0_01_Percent) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Discharge for 1/10th of full duration → should lose exactly 10%
    double tenth = static_cast<double>(cfg.battery.discharge_duration_s) / 10.0;
    bm.update(tenth, false, false);

    // Expected: 100% - 10% = 90%
    // Tolerance: 0.01%
    EXPECT_NEAR(bm.getPercentage(), 90.0, 0.01);
}

TEST(BatteryModelTest, ChargeAccuracy_0_01_Percent) {
    auto cfg = loadDiffDriveConfig();
    BatteryModel bm(cfg);

    // Drain to 0%
    bm.update(static_cast<double>(cfg.battery.discharge_duration_s) * 2.0, false, false);

    // Charge for 1/4 of charge duration → should gain exactly 25%
    bm.startCharging();
    double quarter = static_cast<double>(cfg.battery.charge_duration_s) / 4.0;
    bm.update(quarter, false, false);

    EXPECT_NEAR(bm.getPercentage(), 25.0, 0.01);
}

#pragma once

// ──────────────────────────────────────────────────────────
// rdt/robot/BatteryModel.h — Battery simulation model
//
// All timing from config YAML — NO hardcoded durations.
//   - charge_duration_s: time from 0% to 100%
//   - discharge_duration_s: time from 100% to 0% (base rate)
//   - motion_energy_factor: multiplier when moving
//   - attachment_energy_factor: multiplier when attachment active
//   - critical_threshold_pct: percentage below which isCritical()
//   - initial_charge_pct: starting SOC
//
// Voltage model: 42V + 6V * (SOC / 100)
//   SOC=100% → 48V, SOC=0% → 42V
// ──────────────────────────────────────────────────────────

#include "rdt/core/Config.h"

namespace rdt {

class BatteryModel {
public:
    /// Construct with robot configuration.
    /// Reads all battery parameters from config.
    explicit BatteryModel(const RobotConfig& config);

    /// Update battery state for a time step.
    /// @param dt_seconds           Elapsed time in seconds
    /// @param is_moving            Whether the robot is currently moving
    /// @param is_attachment_active  Whether the attachment (conveyor, lifter, etc.) is active
    void update(double dt_seconds, bool is_moving, bool is_attachment_active);

    /// Get current state of charge as a percentage [0.0, 100.0].
    double getPercentage() const;

    /// Get current voltage based on SOC.
    /// Formula: 42.0 + 6.0 * (SOC / 100.0)
    double getVoltage() const;

    /// Check if the battery is currently charging.
    bool isCharging() const;

    /// Start charging the battery.
    void startCharging();

    /// Stop charging the battery.
    void stopCharging();

    /// Check if SOC is below critical threshold.
    bool isCritical() const;

private:
    BatteryConfig battery_config_;
    double        soc_;       // state of charge [0.0, 100.0]
    bool          charging_;
};

} // namespace rdt

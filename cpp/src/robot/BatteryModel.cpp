// ──────────────────────────────────────────────────────────
// robot/BatteryModel.cpp — Battery charge/discharge simulation
//
// All timing from config YAML — zero hardcoded durations.
//
// Discharge rate (per second):
//   base_rate = 100.0 / discharge_duration_s
//   effective = base_rate * motion_factor * attachment_factor
//
// Charge rate (per second):
//   charge_rate = 100.0 / charge_duration_s
//
// Voltage model:
//   voltage = 42.0 + 6.0 * (soc / 100.0)
// ──────────────────────────────────────────────────────────

#include "rdt/robot/BatteryModel.h"

#include <algorithm>

namespace rdt {

BatteryModel::BatteryModel(const RobotConfig& config)
    : battery_config_(config.battery)
    , soc_(static_cast<double>(config.battery.initial_charge_pct))
    , charging_(false)
{
}

void BatteryModel::update(double dt_seconds, bool is_moving, bool is_attachment_active) {
    if (dt_seconds <= 0.0) {
        return;
    }

    if (charging_) {
        // Charge: linear from 0% to 100% in charge_duration_s seconds
        double charge_rate = 100.0 / static_cast<double>(battery_config_.charge_duration_s);
        soc_ += charge_rate * dt_seconds;
        soc_ = std::min(soc_, 100.0);
    } else {
        // Discharge: base rate modulated by motion and attachment factors
        double base_rate = 100.0 / static_cast<double>(battery_config_.discharge_duration_s);
        double factor = 1.0;
        if (is_moving) {
            factor *= battery_config_.motion_energy_factor;
        }
        if (is_attachment_active) {
            factor *= battery_config_.attachment_energy_factor;
        }
        soc_ -= base_rate * factor * dt_seconds;
        soc_ = std::max(soc_, 0.0);
    }
}

double BatteryModel::getPercentage() const {
    return soc_;
}

double BatteryModel::getVoltage() const {
    return 42.0 + 6.0 * (soc_ / 100.0);
}

bool BatteryModel::isCharging() const {
    return charging_;
}

void BatteryModel::startCharging() {
    charging_ = true;
}

void BatteryModel::stopCharging() {
    charging_ = false;
}

bool BatteryModel::isCritical() const {
    return soc_ < static_cast<double>(battery_config_.critical_threshold_pct);
}

} // namespace rdt

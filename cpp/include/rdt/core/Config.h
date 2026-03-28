#pragma once

// ──────────────────────────────────────────────────────────
// rdt/core/Config.h — Configuration loader for robots (YAML)
//                      and warehouses (JSON)
//
// Robot params come from configs/robots/*.yaml at runtime.
// Warehouse maps come from configs/warehouses/*.json.
// No hardcoded robot parameters in C++.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <map>
#include <stdexcept>

#include "rdt/core/Types.h"

namespace rdt {

// ── Robot sub-configs ───────────────────────────────────

struct MotionConfig {
    double max_linear_velocity   = 0.0;
    double min_linear_velocity   = 0.0;
    double max_angular_velocity  = 0.0;
    double min_angular_velocity  = 0.0;
    double linear_acceleration   = 0.0;
    double linear_deceleration   = 0.0;
    double jerk_max              = 0.0;
    double position_tolerance    = 0.0;
    double angular_tolerance     = 0.0;
    double creep_distance        = 0.0;
    double creep_velocity        = 0.0;
    double exit_velocity         = 0.0;
    double max_linear_velocity_curve = 0.0;  // unidirectional only
};

struct DimensionsConfig {
    double length           = 0.0;
    double width            = 0.0;
    double height           = 0.0;
    double weight           = 0.0;
    double payload_capacity = 0.0;
    double wheel_separation = 0.0;
    double wheel_radius     = 0.0;
};

struct LidarConfig {
    bool        enabled        = false;
    std::string type           = "2d";
    int         fov_deg        = 360;
    double      range_m        = 5.0;
    int         rays           = 360;
    double      height_m       = 0.15;
    double      noise_stddev_m = 0.03;
};

struct BarcodeReaderConfig {
    bool enabled            = false;
    int  debounce_ms        = 5;
    int  failure_threshold  = 5;
};

struct ImuConfig {
    bool   enabled          = false;
    double noise_stddev_deg = 3.0;
};

struct SensorsConfig {
    LidarConfig         lidar;
    BarcodeReaderConfig barcode_reader;
    ImuConfig           imu;
};

struct BatteryConfig {
    int    charge_duration_s        = 600;
    int    discharge_duration_s     = 54000;
    double motion_energy_factor     = 1.05;
    double attachment_energy_factor = 1.0;
    int    critical_threshold_pct   = 20;
    int    initial_charge_pct       = 100;
};

struct ObstacleThresholdsConfig {
    double critical_m = 0.7;
    double warning_m  = 0.8;
    double planning_m = 1.5;
};

struct AttachmentConfig {
    std::string type        = "none";
    double      load_time_s   = 3.0;
    double      unload_time_s = 3.0;
};

struct MpcConfig {
    int    num_opt_vars             = 12;
    double dt                       = 0.1;
    double position_weight          = 1.0;
    double velocity_weight          = 0.0;
    double weight_scale             = 0.05;
    double jerk_scale               = 1.0;
    double acceleration_scale       = 1.0;
    double final_position_offset    = 0.015;
    double final_velocity_threshold = 0.05;
    int    osqp_iterations          = 500;
    double osqp_eps_abs             = 0.01;
    double osqp_eps_rel             = 0.01;
};

struct RobotConfig {
    std::string              name;
    RobotType                type = RobotType::DIFFERENTIAL_DRIVE;
    MotionConfig             motion;
    DimensionsConfig         dimensions;
    SensorsConfig            sensors;
    BatteryConfig            battery;
    ObstacleThresholdsConfig obstacle_thresholds;
    AttachmentConfig         attachment;
    MpcConfig                mpc;
    std::string              behavior_tree;
    std::map<std::string, int> action_codes;
    std::map<std::string, int> response_codes;
};

// ── Warehouse config ────────────────────────────────────

struct ZoneConfig {
    std::string              name;
    std::string              type;
    std::vector<std::string> nodes;
};

struct WarehouseConfig {
    std::string           name;
    std::string           description;
    double                grid_spacing_m = 2.0;
    std::vector<MapNode>  nodes;
    std::vector<MapEdge>  edges;
    std::vector<ZoneConfig> zones;
};

// ── Config loader ───────────────────────────────────────

class Config {
public:
    /// Load a robot configuration from a YAML file.
    /// @param yaml_path  Absolute or relative path to the .yaml file
    /// @throws std::runtime_error if file cannot be read or parsed
    static RobotConfig loadRobotConfig(const std::string& yaml_path);

    /// Load a warehouse configuration from a JSON file.
    /// @param json_path  Absolute or relative path to the .json file
    /// @throws std::runtime_error if file cannot be read or parsed
    static WarehouseConfig loadWarehouseConfig(const std::string& json_path);
};

} // namespace rdt

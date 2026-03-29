// ──────────────────────────────────────────────────────────
// core/Config.cpp — Loads robot YAML + warehouse JSON
// ──────────────────────────────────────────────────────────

#include "rdt/core/Config.h"

#include <fstream>
#include <sstream>
#include <stdexcept>

#include <yaml-cpp/yaml.h>
#include <json/json.h>

namespace rdt {

// ── Robot config (YAML) ─────────────────────────────────

RobotConfig Config::loadRobotConfig(const std::string& yaml_path) {
    YAML::Node root;
    try {
        root = YAML::LoadFile(yaml_path);
    } catch (const YAML::Exception& e) {
        throw std::runtime_error("Failed to load robot YAML: " + yaml_path +
                                 " — " + e.what());
    }

    RobotConfig cfg;
    cfg.name = root["name"].as<std::string>("");
    cfg.type = robot_type_from_string(root["type"].as<std::string>("differential_drive"));

    // Motion
    if (auto m = root["motion"]) {
        cfg.motion.max_linear_velocity      = m["max_linear_velocity"].as<double>(0.0);
        cfg.motion.min_linear_velocity      = m["min_linear_velocity"].as<double>(0.0);
        cfg.motion.max_angular_velocity     = m["max_angular_velocity"].as<double>(0.0);
        cfg.motion.min_angular_velocity     = m["min_angular_velocity"].as<double>(0.0);
        cfg.motion.linear_acceleration      = m["linear_acceleration"].as<double>(0.0);
        cfg.motion.linear_deceleration      = m["linear_deceleration"].as<double>(0.0);
        cfg.motion.jerk_max                 = m["jerk_max"].as<double>(0.0);
        cfg.motion.position_tolerance       = m["position_tolerance"].as<double>(0.0);
        cfg.motion.angular_tolerance        = m["angular_tolerance"].as<double>(0.0);
        cfg.motion.creep_distance           = m["creep_distance"].as<double>(0.0);
        cfg.motion.creep_velocity           = m["creep_velocity"].as<double>(0.0);
        cfg.motion.exit_velocity            = m["exit_velocity"].as<double>(0.0);
        cfg.motion.max_linear_velocity_curve = m["max_linear_velocity_curve"].as<double>(0.0);
    }

    // Dimensions
    if (auto d = root["dimensions"]) {
        cfg.dimensions.length           = d["length"].as<double>(0.0);
        cfg.dimensions.width            = d["width"].as<double>(0.0);
        cfg.dimensions.height           = d["height"].as<double>(0.0);
        cfg.dimensions.weight           = d["weight"].as<double>(0.0);
        cfg.dimensions.payload_capacity = d["payload_capacity"].as<double>(0.0);
        cfg.dimensions.wheel_separation = d["wheel_separation"].as<double>(0.0);
        cfg.dimensions.wheel_radius     = d["wheel_radius"].as<double>(0.0);
    }

    // Sensors
    if (auto s = root["sensors"]) {
        if (auto l = s["lidar"]) {
            cfg.sensors.lidar.enabled        = l["enabled"].as<bool>(false);
            cfg.sensors.lidar.type           = l["type"].as<std::string>("2d");
            cfg.sensors.lidar.fov_deg        = l["fov_deg"].as<int>(360);
            cfg.sensors.lidar.range_m        = l["range_m"].as<double>(5.0);
            cfg.sensors.lidar.rays           = l["rays"].as<int>(360);
            cfg.sensors.lidar.height_m       = l["height_m"].as<double>(0.15);
            cfg.sensors.lidar.noise_stddev_m = l["noise_stddev_m"].as<double>(0.03);
        }
        if (auto b = s["barcode_reader"]) {
            cfg.sensors.barcode_reader.enabled           = b["enabled"].as<bool>(false);
            cfg.sensors.barcode_reader.debounce_ms       = b["debounce_ms"].as<int>(5);
            cfg.sensors.barcode_reader.failure_threshold  = b["failure_threshold"].as<int>(5);
        }
        if (auto i = s["imu"]) {
            cfg.sensors.imu.enabled          = i["enabled"].as<bool>(false);
            cfg.sensors.imu.noise_stddev_deg = i["noise_stddev_deg"].as<double>(3.0);
        }
    }

    // Battery
    if (auto b = root["battery"]) {
        cfg.battery.charge_duration_s        = b["charge_duration_s"].as<int>(600);
        cfg.battery.discharge_duration_s     = b["discharge_duration_s"].as<int>(54000);
        cfg.battery.motion_energy_factor     = b["motion_energy_factor"].as<double>(1.05);
        cfg.battery.attachment_energy_factor = b["attachment_energy_factor"].as<double>(1.0);
        cfg.battery.critical_threshold_pct   = b["critical_threshold_pct"].as<int>(20);
        cfg.battery.initial_charge_pct       = b["initial_charge_pct"].as<int>(100);
    }

    // Obstacle thresholds
    if (auto o = root["obstacle_thresholds"]) {
        cfg.obstacle_thresholds.critical_m = o["critical_m"].as<double>(0.7);
        cfg.obstacle_thresholds.warning_m  = o["warning_m"].as<double>(0.8);
        cfg.obstacle_thresholds.planning_m = o["planning_m"].as<double>(1.5);
    }

    // Attachment
    if (auto a = root["attachment"]) {
        cfg.attachment.type        = a["type"].as<std::string>("none");
        cfg.attachment.load_time_s   = a["load_time_s"].as<double>(3.0);
        cfg.attachment.unload_time_s = a["unload_time_s"].as<double>(3.0);
    }

    // MPC
    if (auto mc = root["mpc"]) {
        cfg.mpc.num_opt_vars             = mc["num_opt_vars"].as<int>(12);
        cfg.mpc.dt                       = mc["dt"].as<double>(0.1);
        cfg.mpc.position_weight          = mc["position_weight"].as<double>(1.0);
        cfg.mpc.velocity_weight          = mc["velocity_weight"].as<double>(0.0);
        cfg.mpc.weight_scale             = mc["weight_scale"].as<double>(0.05);
        cfg.mpc.jerk_scale               = mc["jerk_scale"].as<double>(1.0);
        cfg.mpc.acceleration_scale       = mc["acceleration_scale"].as<double>(1.0);
        cfg.mpc.final_position_offset    = mc["final_position_offset"].as<double>(0.015);
        cfg.mpc.final_velocity_threshold = mc["final_velocity_threshold"].as<double>(0.05);
        cfg.mpc.osqp_iterations          = mc["osqp_iterations"].as<int>(500);
        cfg.mpc.osqp_eps_abs             = mc["osqp_eps_abs"].as<double>(0.01);
        cfg.mpc.osqp_eps_rel             = mc["osqp_eps_rel"].as<double>(0.01);
    }

    // Behavior tree
    cfg.behavior_tree = root["behavior_tree"].as<std::string>("");

    // Action codes
    if (auto ac = root["action_codes"]) {
        for (auto it = ac.begin(); it != ac.end(); ++it) {
            cfg.action_codes[it->first.as<std::string>()] = it->second.as<int>(0);
        }
    }

    // Response codes
    if (auto rc = root["response_codes"]) {
        for (auto it = rc.begin(); it != rc.end(); ++it) {
            cfg.response_codes[it->first.as<std::string>()] = it->second.as<int>(0);
        }
    }

    return cfg;
}

// ── Warehouse config (JSON) ─────────────────────────────

WarehouseConfig Config::loadWarehouseConfig(const std::string& json_path) {
    std::ifstream file(json_path);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open warehouse JSON: " + json_path);
    }

    Json::Value root;
    Json::CharReaderBuilder builder;
    std::string errors;
    if (!Json::parseFromStream(builder, file, &root, &errors)) {
        throw std::runtime_error("Failed to parse warehouse JSON: " + json_path +
                                 " — " + errors);
    }

    WarehouseConfig cfg;
    cfg.name           = root.get("name", "").asString();
    cfg.description    = root.get("description", "").asString();
    cfg.grid_spacing_m = root.get("grid_spacing_m", 2.0).asDouble();

    // Nodes
    const auto& nodes_json = root["nodes"];
    cfg.nodes.reserve(nodes_json.size());
    for (const auto& nj : nodes_json) {
        cfg.nodes.push_back(map_node_from_json(nj));
    }

    // Edges
    const auto& edges_json = root["edges"];
    cfg.edges.reserve(edges_json.size());
    for (const auto& ej : edges_json) {
        cfg.edges.push_back(map_edge_from_json(ej));
    }

    // Zones
    const auto& zones_json = root["zones"];
    cfg.zones.reserve(zones_json.size());
    for (const auto& zj : zones_json) {
        ZoneConfig z;
        z.name = zj.get("name", "").asString();
        z.type = zj.get("type", "").asString();
        const auto& zone_nodes = zj["nodes"];
        z.nodes.reserve(zone_nodes.size());
        for (const auto& zn : zone_nodes) {
            z.nodes.push_back(zn.asString());
        }
        cfg.zones.push_back(std::move(z));
    }

    return cfg;
}

// ── Fleet manifest (JSON) ───────────────────────────────

FleetManifest Config::loadFleetManifest(const std::string& json_path) {
    std::ifstream file(json_path);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open fleet manifest JSON: " + json_path);
    }

    Json::Value root;
    Json::CharReaderBuilder builder;
    std::string errors;
    if (!Json::parseFromStream(builder, file, &root, &errors)) {
        throw std::runtime_error("Failed to parse fleet manifest JSON: " + json_path +
                                 " — " + errors);
    }

    FleetManifest manifest;
    manifest.name        = root.get("name", "").asString();
    manifest.description = root.get("description", "").asString();

    const auto& robots_json = root["robots"];
    if (!robots_json.isArray()) {
        throw std::runtime_error("Fleet manifest 'robots' must be an array: " + json_path);
    }

    manifest.robots.reserve(robots_json.size());
    for (const auto& rj : robots_json) {
        FleetEntry entry;
        entry.id_prefix = rj.get("id_prefix", "").asString();
        entry.config    = rj.get("config", "").asString();
        entry.count     = rj.get("count", 1).asInt();

        if (entry.id_prefix.empty()) {
            throw std::runtime_error("Fleet entry missing 'id_prefix' in: " + json_path);
        }
        if (entry.config.empty()) {
            throw std::runtime_error("Fleet entry missing 'config' in: " + json_path);
        }
        if (entry.count < 1) {
            throw std::runtime_error("Fleet entry 'count' must be >= 1 for prefix '" +
                                     entry.id_prefix + "' in: " + json_path);
        }

        manifest.robots.push_back(std::move(entry));
    }

    return manifest;
}

std::vector<RobotConfig> Config::expandFleetManifest(const FleetManifest& manifest,
                                                     const std::string& base_dir) {
    std::vector<RobotConfig> configs;

    for (const auto& entry : manifest.robots) {
        // Resolve config path relative to base_dir if provided
        std::string config_path = entry.config;
        if (!base_dir.empty() && config_path[0] != '/') {
            config_path = base_dir + "/" + config_path;
        }

        // Load the base config once per fleet entry
        RobotConfig base = loadRobotConfig(config_path);

        for (int i = 1; i <= entry.count; ++i) {
            RobotConfig rc = base;

            // Generate unique name: AMR_001, AMR_002, ..., AGV_001, etc.
            std::ostringstream name_ss;
            name_ss << entry.id_prefix << "_";
            if (i < 10)        name_ss << "00";
            else if (i < 100)  name_ss << "0";
            name_ss << i;
            rc.name = name_ss.str();

            configs.push_back(std::move(rc));
        }
    }

    return configs;
}

} // namespace rdt

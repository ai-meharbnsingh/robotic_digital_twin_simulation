// ──────────────────────────────────────────────────────────
// test_config.cpp — Unit tests for rdt/core/Config
//
// Loads REAL YAML and JSON config files and asserts exact
// values match. No hardcoded robot params — all come from
// configs/robots/*.yaml and configs/warehouses/*.json.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/core/Config.h"

using namespace rdt;

// ── Helpers ─────────────────────────────────────────────
// Tests discover config files relative to the project root.
// CMake sets RDT_PROJECT_ROOT at compile time.

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() {
    return RDT_PROJECT_ROOT;
}

// ── Warehouse config ────────────────────────────────────

TEST(ConfigTest, LoadSimpleGridWarehouse_NodeCount) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    EXPECT_EQ(cfg.nodes.size(), 25u);
}

TEST(ConfigTest, LoadSimpleGridWarehouse_EdgeCount) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    EXPECT_EQ(cfg.edges.size(), 40u);
}

TEST(ConfigTest, LoadSimpleGridWarehouse_ZoneCount) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    EXPECT_EQ(cfg.zones.size(), 8u);
}

TEST(ConfigTest, LoadSimpleGridWarehouse_Name) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    EXPECT_EQ(cfg.name, "Simple 5x5 Grid");
}

TEST(ConfigTest, LoadSimpleGridWarehouse_GridSpacing) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    EXPECT_DOUBLE_EQ(cfg.grid_spacing_m, 2.0);
}

TEST(ConfigTest, LoadSimpleGridWarehouse_FirstNode) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    ASSERT_GE(cfg.nodes.size(), 1u);
    EXPECT_EQ(cfg.nodes[0].name, "DOCK_1");
    EXPECT_DOUBLE_EQ(cfg.nodes[0].x, 0.0);
    EXPECT_DOUBLE_EQ(cfg.nodes[0].y, 0.0);
    EXPECT_EQ(cfg.nodes[0].type, "charge");
}

TEST(ConfigTest, LoadSimpleGridWarehouse_HubNode) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    // HUB is at index 12 (0-indexed), verify
    bool found = false;
    for (const auto& n : cfg.nodes) {
        if (n.name == "HUB") {
            EXPECT_DOUBLE_EQ(n.x, 4.0);
            EXPECT_DOUBLE_EQ(n.y, 4.0);
            EXPECT_EQ(n.type, "hub");
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found) << "HUB node not found in warehouse config";
}

TEST(ConfigTest, LoadSimpleGridWarehouse_ZoneDetails) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    ASSERT_EQ(cfg.zones.size(), 8u);

    EXPECT_EQ(cfg.zones[0].name, "Charging");
    EXPECT_EQ(cfg.zones[0].type, "dock");
    EXPECT_EQ(cfg.zones[0].nodes.size(), 2u);

    EXPECT_EQ(cfg.zones[1].name, "Aisle_North");
    EXPECT_EQ(cfg.zones[1].type, "aisle");
    EXPECT_EQ(cfg.zones[1].nodes.size(), 3u);

    EXPECT_EQ(cfg.zones[2].name, "Aisle_West");
    EXPECT_EQ(cfg.zones[2].type, "lane");
    EXPECT_EQ(cfg.zones[2].nodes.size(), 3u);

    EXPECT_EQ(cfg.zones[3].name, "Storage");
    EXPECT_EQ(cfg.zones[3].type, "shelf");
    EXPECT_EQ(cfg.zones[3].nodes.size(), 8u);

    EXPECT_EQ(cfg.zones[4].name, "Operations");
    EXPECT_EQ(cfg.zones[4].type, "ops");
    EXPECT_EQ(cfg.zones[4].nodes.size(), 1u);

    EXPECT_EQ(cfg.zones[5].name, "Aisle_East");
    EXPECT_EQ(cfg.zones[5].type, "lane");
    EXPECT_EQ(cfg.zones[5].nodes.size(), 3u);

    EXPECT_EQ(cfg.zones[6].name, "Aisle_South");
    EXPECT_EQ(cfg.zones[6].type, "aisle");
    EXPECT_EQ(cfg.zones[6].nodes.size(), 3u);

    EXPECT_EQ(cfg.zones[7].name, "Pick_Drop");
    EXPECT_EQ(cfg.zones[7].type, "pick");
    EXPECT_EQ(cfg.zones[7].nodes.size(), 2u);
}

TEST(ConfigTest, LoadSimpleGridWarehouse_FirstEdge) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/simple_grid.json");
    ASSERT_GE(cfg.edges.size(), 1u);
    EXPECT_EQ(cfg.edges[0].from, "DOCK_1");
    EXPECT_EQ(cfg.edges[0].to,   "N_01");
    // Edges default to bidirectional=true when not specified
    EXPECT_TRUE(cfg.edges[0].bidirectional);
}

TEST(ConfigTest, LoadWarehouse_InvalidPath_Throws) {
    EXPECT_THROW(
        Config::loadWarehouseConfig("/nonexistent/path.json"),
        std::runtime_error
    );
}

// ── Robot config (Differential Drive) ───────────────────

TEST(ConfigTest, LoadDiffDrive_MaxLinearVelocity) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 2.0);
}

TEST(ConfigTest, LoadDiffDrive_Name) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.name, "DiffDrive_AMR");
}

TEST(ConfigTest, LoadDiffDrive_Type) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.type, RobotType::DIFFERENTIAL_DRIVE);
}

TEST(ConfigTest, LoadDiffDrive_MotionParams) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.min_linear_velocity,  0.02);
    EXPECT_DOUBLE_EQ(cfg.motion.max_angular_velocity,  2.5);
    EXPECT_DOUBLE_EQ(cfg.motion.min_angular_velocity,  0.02);
    EXPECT_DOUBLE_EQ(cfg.motion.linear_acceleration,   0.8);
    EXPECT_DOUBLE_EQ(cfg.motion.linear_deceleration,   0.8);
    EXPECT_DOUBLE_EQ(cfg.motion.jerk_max,             10.0);
    EXPECT_DOUBLE_EQ(cfg.motion.position_tolerance,    0.07);
    EXPECT_DOUBLE_EQ(cfg.motion.angular_tolerance,     0.025);
    EXPECT_DOUBLE_EQ(cfg.motion.creep_distance,        0.02);
    EXPECT_DOUBLE_EQ(cfg.motion.creep_velocity,        0.02);
    EXPECT_DOUBLE_EQ(cfg.motion.exit_velocity,         0.4);
}

TEST(ConfigTest, LoadDiffDrive_Dimensions) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_DOUBLE_EQ(cfg.dimensions.length,           0.8);
    EXPECT_DOUBLE_EQ(cfg.dimensions.width,            0.6);
    EXPECT_DOUBLE_EQ(cfg.dimensions.height,           0.3);
    EXPECT_DOUBLE_EQ(cfg.dimensions.weight,          50.0);
    EXPECT_DOUBLE_EQ(cfg.dimensions.payload_capacity, 500.0);
    EXPECT_DOUBLE_EQ(cfg.dimensions.wheel_separation,  0.5);
    EXPECT_DOUBLE_EQ(cfg.dimensions.wheel_radius,      0.075);
}

TEST(ConfigTest, LoadDiffDrive_Battery) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.battery.charge_duration_s,       600);
    EXPECT_EQ(cfg.battery.discharge_duration_s,    54000);
    EXPECT_DOUBLE_EQ(cfg.battery.motion_energy_factor,     1.05);
    EXPECT_DOUBLE_EQ(cfg.battery.attachment_energy_factor,  1.0);
    EXPECT_EQ(cfg.battery.critical_threshold_pct,  20);
    EXPECT_EQ(cfg.battery.initial_charge_pct,      100);
}

TEST(ConfigTest, LoadDiffDrive_ObstacleThresholds) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_DOUBLE_EQ(cfg.obstacle_thresholds.critical_m, 0.7);
    EXPECT_DOUBLE_EQ(cfg.obstacle_thresholds.warning_m,  0.8);
    EXPECT_DOUBLE_EQ(cfg.obstacle_thresholds.planning_m, 1.5);
}

TEST(ConfigTest, LoadDiffDrive_Sensors) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_TRUE(cfg.sensors.lidar.enabled);
    EXPECT_EQ(cfg.sensors.lidar.type, "2d");
    EXPECT_EQ(cfg.sensors.lidar.fov_deg, 360);
    EXPECT_DOUBLE_EQ(cfg.sensors.lidar.range_m, 5.0);
    EXPECT_EQ(cfg.sensors.lidar.rays, 360);
    EXPECT_DOUBLE_EQ(cfg.sensors.lidar.height_m, 0.15);
    EXPECT_DOUBLE_EQ(cfg.sensors.lidar.noise_stddev_m, 0.03);

    EXPECT_TRUE(cfg.sensors.barcode_reader.enabled);
    EXPECT_EQ(cfg.sensors.barcode_reader.debounce_ms, 5);
    EXPECT_EQ(cfg.sensors.barcode_reader.failure_threshold, 5);

    EXPECT_TRUE(cfg.sensors.imu.enabled);
    EXPECT_DOUBLE_EQ(cfg.sensors.imu.noise_stddev_deg, 3.0);
}

TEST(ConfigTest, LoadDiffDrive_Attachment) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.attachment.type, "none");
    EXPECT_DOUBLE_EQ(cfg.attachment.load_time_s, 3.0);
    EXPECT_DOUBLE_EQ(cfg.attachment.unload_time_s, 3.0);
}

TEST(ConfigTest, LoadDiffDrive_Mpc) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.mpc.num_opt_vars, 12);
    EXPECT_DOUBLE_EQ(cfg.mpc.dt, 0.1);
    EXPECT_DOUBLE_EQ(cfg.mpc.position_weight, 1.0);
    EXPECT_DOUBLE_EQ(cfg.mpc.velocity_weight, 0.0);
    EXPECT_DOUBLE_EQ(cfg.mpc.weight_scale, 0.05);
    EXPECT_DOUBLE_EQ(cfg.mpc.jerk_scale, 1.0);
    EXPECT_DOUBLE_EQ(cfg.mpc.acceleration_scale, 1.0);
    EXPECT_DOUBLE_EQ(cfg.mpc.final_position_offset, 0.015);
    EXPECT_DOUBLE_EQ(cfg.mpc.final_velocity_threshold, 0.05);
    EXPECT_EQ(cfg.mpc.osqp_iterations, 500);
    EXPECT_DOUBLE_EQ(cfg.mpc.osqp_eps_abs, 0.01);
    EXPECT_DOUBLE_EQ(cfg.mpc.osqp_eps_rel, 0.01);
}

TEST(ConfigTest, LoadDiffDrive_ActionCodes) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.action_codes.at("move"),            0);
    EXPECT_EQ(cfg.action_codes.at("charge_dock"),     2);
    EXPECT_EQ(cfg.action_codes.at("start_charging"),  3);
    EXPECT_EQ(cfg.action_codes.at("charge_undock"),   4);
    EXPECT_EQ(cfg.action_codes.at("start_loading"),  14);
    EXPECT_EQ(cfg.action_codes.at("start_unloading"),15);
    EXPECT_EQ(cfg.action_codes.at("reset_errors"),   31);
    EXPECT_EQ(cfg.action_codes.at("hard_reset"),     51);
}

TEST(ConfigTest, LoadDiffDrive_ResponseCodes) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.response_codes.at("reached_dock"),     10);
    EXPECT_EQ(cfg.response_codes.at("reached_predock"),   8);
    EXPECT_EQ(cfg.response_codes.at("charging_stopped"), 18);
    EXPECT_EQ(cfg.response_codes.at("charging_error"),  501);
    EXPECT_EQ(cfg.response_codes.at("load_error"),      401);
    EXPECT_EQ(cfg.response_codes.at("unload_error"),    402);
}

TEST(ConfigTest, LoadDiffDrive_BehaviorTree) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/differential_drive.yaml");
    EXPECT_EQ(cfg.behavior_tree, "default_amr.xml");
}

// ── Robot config (Unidirectional) ───────────────────────

TEST(ConfigTest, LoadUnidirectional_MaxLinearVelocity) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 1.4);
}

TEST(ConfigTest, LoadUnidirectional_Name) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_EQ(cfg.name, "Uni_AGV");
}

TEST(ConfigTest, LoadUnidirectional_Type) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_EQ(cfg.type, RobotType::UNIDIRECTIONAL);
}

TEST(ConfigTest, LoadUnidirectional_CurveVelocity) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity_curve, 0.6);
}

TEST(ConfigTest, LoadUnidirectional_Battery) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_EQ(cfg.battery.charge_duration_s,    450);
    EXPECT_EQ(cfg.battery.discharge_duration_s, 60000);
    EXPECT_DOUBLE_EQ(cfg.battery.motion_energy_factor,     1.02);
    EXPECT_DOUBLE_EQ(cfg.battery.attachment_energy_factor,  1.02);
}

TEST(ConfigTest, LoadUnidirectional_Attachment) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_EQ(cfg.attachment.type, "conveyor");
}

TEST(ConfigTest, LoadUnidirectional_ImuDisabled) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_FALSE(cfg.sensors.imu.enabled);
}

TEST(ConfigTest, LoadUnidirectional_BehaviorTree) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
    EXPECT_EQ(cfg.behavior_tree, "default_agv.xml");
}

TEST(ConfigTest, LoadRobot_InvalidPath_Throws) {
    EXPECT_THROW(
        Config::loadRobotConfig("/nonexistent/robot.yaml"),
        std::runtime_error
    );
}

// ── Fleet manifest ─────────────────────────────────────

TEST(ConfigTest, LoadFleetManifest_Name) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    EXPECT_EQ(manifest.name, "Default Mixed Fleet");
}

TEST(ConfigTest, LoadFleetManifest_EntryCount) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    EXPECT_EQ(manifest.robots.size(), 2u);
}

TEST(ConfigTest, LoadFleetManifest_AMREntry) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    ASSERT_GE(manifest.robots.size(), 1u);
    EXPECT_EQ(manifest.robots[0].id_prefix, "AMR");
    EXPECT_EQ(manifest.robots[0].count, 5);
    EXPECT_NE(manifest.robots[0].config.find("differential_drive"), std::string::npos);
}

TEST(ConfigTest, LoadFleetManifest_AGVEntry) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    ASSERT_GE(manifest.robots.size(), 2u);
    EXPECT_EQ(manifest.robots[1].id_prefix, "AGV");
    EXPECT_EQ(manifest.robots[1].count, 5);
    EXPECT_NE(manifest.robots[1].config.find("unidirectional"), std::string::npos);
}

TEST(ConfigTest, LoadFleetManifest_InvalidPath_Throws) {
    EXPECT_THROW(
        Config::loadFleetManifest("/nonexistent/fleet.json"),
        std::runtime_error
    );
}

TEST(ConfigTest, ExpandFleetManifest_TotalCount) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());
    EXPECT_EQ(configs.size(), 10u);  // 5 AMR + 5 AGV
}

TEST(ConfigTest, ExpandFleetManifest_AMRNames) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());

    // First 5 should be AMR_001 through AMR_005
    EXPECT_EQ(configs[0].name, "AMR_001");
    EXPECT_EQ(configs[1].name, "AMR_002");
    EXPECT_EQ(configs[2].name, "AMR_003");
    EXPECT_EQ(configs[3].name, "AMR_004");
    EXPECT_EQ(configs[4].name, "AMR_005");
}

TEST(ConfigTest, ExpandFleetManifest_AGVNames) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());

    // Next 5 should be AGV_001 through AGV_005
    EXPECT_EQ(configs[5].name, "AGV_001");
    EXPECT_EQ(configs[6].name, "AGV_002");
    EXPECT_EQ(configs[7].name, "AGV_003");
    EXPECT_EQ(configs[8].name, "AGV_004");
    EXPECT_EQ(configs[9].name, "AGV_005");
}

TEST(ConfigTest, ExpandFleetManifest_TypesCorrect) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());

    // AMRs are differential drive
    for (int i = 0; i < 5; ++i) {
        EXPECT_EQ(configs[i].type, RobotType::DIFFERENTIAL_DRIVE)
            << "Robot " << configs[i].name << " should be DIFFERENTIAL_DRIVE";
    }

    // AGVs are unidirectional
    for (int i = 5; i < 10; ++i) {
        EXPECT_EQ(configs[i].type, RobotType::UNIDIRECTIONAL)
            << "Robot " << configs[i].name << " should be UNIDIRECTIONAL";
    }
}

TEST(ConfigTest, ExpandFleetManifest_ConfigsPreserved) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/default_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());

    // AMR_001 should have differential drive speed
    EXPECT_DOUBLE_EQ(configs[0].motion.max_linear_velocity, 2.0);
    EXPECT_EQ(configs[0].behavior_tree, "default_amr.xml");

    // AGV_001 should have unidirectional speed
    EXPECT_DOUBLE_EQ(configs[5].motion.max_linear_velocity, 1.4);
    EXPECT_EQ(configs[5].behavior_tree, "default_agv.xml");
    EXPECT_DOUBLE_EQ(configs[5].motion.max_linear_velocity_curve, 0.6);
}

// ── Addverb Fleet Presets (Phase 9) ─────────────────────

TEST(ConfigTest, LoadAddverbDynamo_Name) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_dynamo.yaml");
    EXPECT_EQ(cfg.name, "Addverb_Dynamo");
}

TEST(ConfigTest, LoadAddverbDynamo_Type) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_dynamo.yaml");
    EXPECT_EQ(cfg.type, RobotType::DIFFERENTIAL_DRIVE);
}

TEST(ConfigTest, LoadAddverbDynamo_Speed) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_dynamo.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 1.5);
}

TEST(ConfigTest, LoadAddverbVeloce_Name) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_veloce.yaml");
    EXPECT_EQ(cfg.name, "Addverb_Veloce");
}

TEST(ConfigTest, LoadAddverbVeloce_Type) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_veloce.yaml");
    EXPECT_EQ(cfg.type, RobotType::UNIDIRECTIONAL);
}

TEST(ConfigTest, LoadAddverbVeloce_Speed) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_veloce.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 1.5);
}

TEST(ConfigTest, LoadAddverbQuadron_Name) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_quadron.yaml");
    EXPECT_EQ(cfg.name, "Addverb_Quadron");
}

TEST(ConfigTest, LoadAddverbQuadron_Speed) {
    auto cfg = Config::loadRobotConfig(
        projectRoot() + "/configs/robots/addverb_quadron.yaml");
    EXPECT_DOUBLE_EQ(cfg.motion.max_linear_velocity, 4.0);
}

TEST(ConfigTest, LoadAddverbNoida_NodeCount) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/addverb_noida.json");
    EXPECT_EQ(cfg.nodes.size(), 49u);
}

TEST(ConfigTest, LoadAddverbNoida_HasChargeStations) {
    auto cfg = Config::loadWarehouseConfig(
        projectRoot() + "/configs/warehouses/addverb_noida.json");
    int charge_count = 0;
    for (const auto& n : cfg.nodes) {
        if (n.type == "charge") charge_count++;
    }
    EXPECT_GE(charge_count, 4);
}

TEST(ConfigTest, LoadAddverbMixedFleet_TotalRobots) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/addverb_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());
    EXPECT_EQ(configs.size(), 10u);  // 3 Dynamo + 5 Veloce + 2 Quadron
}

TEST(ConfigTest, LoadAddverbMixedFleet_DynamoSpeed) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/addverb_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());
    // First 3 should be Dynamo at 1.5 m/s
    EXPECT_DOUBLE_EQ(configs[0].motion.max_linear_velocity, 1.5);
    EXPECT_EQ(configs[0].type, RobotType::DIFFERENTIAL_DRIVE);
}

TEST(ConfigTest, LoadAddverbMixedFleet_QuadronSpeed) {
    auto manifest = Config::loadFleetManifest(
        projectRoot() + "/configs/fleets/addverb_mixed.json");
    auto configs = Config::expandFleetManifest(manifest, projectRoot());
    // Last 2 should be Quadron at 4.0 m/s
    EXPECT_DOUBLE_EQ(configs[8].motion.max_linear_velocity, 4.0);
}

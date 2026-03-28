// ──────────────────────────────────────────────────────────
// fms_server.cpp — Fleet Management Server entry point
//
// Loads warehouse + robot configs, creates FleetManager,
// runs the 15Hz main loop. Handles SIGINT/SIGTERM for
// clean shutdown.
//
// Usage:
//   fms_server --warehouse configs/warehouses/simple_grid.json \
//              --robot configs/robots/differential_drive.yaml \
//              [--robot configs/robots/unidirectional.yaml] \
//              [--tcp-port 7010] [--rest-port 7012] \
//              [--state-file fleet_state.json]
//
// Environment variables (fallbacks):
//   RDT_WAREHOUSE   — path to warehouse JSON
//   RDT_ROBOT       — path to robot YAML (single robot)
//   RDT_TCP_PORT    — TCP port (default 7010)
//   RDT_REST_PORT   — REST port (default 7012)
// ──────────────────────────────────────────────────────────

#include <iostream>
#include <string>
#include <vector>
#include <csignal>
#include <cstdlib>

#include <spdlog/spdlog.h>
#include "rdt/version.h"
#include "rdt/core/Logger.h"
#include "rdt/core/Config.h"
#include "rdt/fleet/FleetManager.h"

// Global pointer for signal handler
static rdt::fleet::FleetManager* g_fleet_manager = nullptr;

static void signalHandler(int signum) {
    spdlog::info("Received signal {} — shutting down...", signum);
    if (g_fleet_manager) {
        g_fleet_manager->stop();
    }
}

static std::string getEnvOrDefault(const char* name, const std::string& fallback) {
    const char* val = std::getenv(name);
    return val ? std::string(val) : fallback;
}

static void printUsage(const char* prog) {
    std::cerr << "Usage: " << prog << " [options]\n"
              << "  --warehouse <path>   Warehouse JSON config (required)\n"
              << "  --robot <path>       Robot YAML config (repeatable)\n"
              << "  --tcp-port <port>    TCP server port (default 7010)\n"
              << "  --rest-port <port>   REST server port (default 7012)\n"
              << "  --state-file <path>  JSON state output file (default fleet_state.json)\n"
              << "  --log-level <level>  Log level: trace|debug|info|warn|error (default info)\n"
              << "\n"
              << "Environment variables:\n"
              << "  RDT_WAREHOUSE, RDT_ROBOT, RDT_TCP_PORT, RDT_REST_PORT\n";
}

int main(int argc, char* argv[]) {
    // ── Parse arguments ──
    std::string warehouse_path;
    std::vector<std::string> robot_paths;
    uint16_t tcp_port  = 7010;
    uint16_t rest_port = 7012;
    std::string state_file = "fleet_state.json";
    std::string log_level  = "info";

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--warehouse" && i + 1 < argc) {
            warehouse_path = argv[++i];
        } else if (arg == "--robot" && i + 1 < argc) {
            robot_paths.push_back(argv[++i]);
        } else if (arg == "--tcp-port" && i + 1 < argc) {
            tcp_port = static_cast<uint16_t>(std::stoi(argv[++i]));
        } else if (arg == "--rest-port" && i + 1 < argc) {
            rest_port = static_cast<uint16_t>(std::stoi(argv[++i]));
        } else if (arg == "--state-file" && i + 1 < argc) {
            state_file = argv[++i];
        } else if (arg == "--log-level" && i + 1 < argc) {
            log_level = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            printUsage(argv[0]);
            return 0;
        } else {
            std::cerr << "Unknown argument: " << arg << "\n";
            printUsage(argv[0]);
            return 1;
        }
    }

    // ── Env var fallbacks ──
    if (warehouse_path.empty()) {
        warehouse_path = getEnvOrDefault("RDT_WAREHOUSE", "");
    }
    if (robot_paths.empty()) {
        std::string env_robot = getEnvOrDefault("RDT_ROBOT", "");
        if (!env_robot.empty()) robot_paths.push_back(env_robot);
    }
    {
        std::string env_tcp = getEnvOrDefault("RDT_TCP_PORT", "");
        if (!env_tcp.empty()) tcp_port = static_cast<uint16_t>(std::stoi(env_tcp));
    }
    {
        std::string env_rest = getEnvOrDefault("RDT_REST_PORT", "");
        if (!env_rest.empty()) rest_port = static_cast<uint16_t>(std::stoi(env_rest));
    }

    // ── Validate ──
    if (warehouse_path.empty()) {
        std::cerr << "Error: --warehouse is required (or set RDT_WAREHOUSE)\n";
        printUsage(argv[0]);
        return 1;
    }
    if (robot_paths.empty()) {
        std::cerr << "Error: at least one --robot is required (or set RDT_ROBOT)\n";
        printUsage(argv[0]);
        return 1;
    }

    // ── Initialize logger ──
    rdt::core::Logger::init(log_level, "fms_server.log");

    spdlog::info("═══════════════════════════════════════════════════════════");
    spdlog::info("  Robotic Digital Twin — FMS Server v{}.{}.{}",
                 RDT_VERSION_MAJOR, RDT_VERSION_MINOR, RDT_VERSION_PATCH);
    spdlog::info("  Warehouse: {}", warehouse_path);
    for (const auto& rp : robot_paths) {
        spdlog::info("  Robot: {}", rp);
    }
    spdlog::info("  TCP port: {} | REST port: {}", tcp_port, rest_port);
    spdlog::info("═══════════════════════════════════════════════════════════");

    // ── Load configs ──
    rdt::WarehouseConfig wh_config;
    try {
        wh_config = rdt::Config::loadWarehouseConfig(warehouse_path);
        spdlog::info("Loaded warehouse '{}' ({} nodes, {} edges)",
                     wh_config.name, wh_config.nodes.size(), wh_config.edges.size());
    } catch (const std::exception& e) {
        spdlog::error("Failed to load warehouse config: {}", e.what());
        return 1;
    }

    std::vector<rdt::RobotConfig> robot_configs;
    for (const auto& path : robot_paths) {
        try {
            auto rc = rdt::Config::loadRobotConfig(path);
            spdlog::info("Loaded robot config '{}' (type={})",
                         rc.name, rdt::robot_type_to_string(rc.type));
            robot_configs.push_back(std::move(rc));
        } catch (const std::exception& e) {
            spdlog::error("Failed to load robot config '{}': {}", path, e.what());
            return 1;
        }
    }

    // ── Create and run FleetManager ──
    rdt::fleet::FleetManager fm(wh_config, robot_configs);
    g_fleet_manager = &fm;

    // Install signal handlers
    std::signal(SIGINT,  signalHandler);
    std::signal(SIGTERM, signalHandler);

    if (!fm.init(tcp_port, rest_port, state_file)) {
        spdlog::error("FleetManager initialization failed");
        return 1;
    }

    spdlog::info("FleetManager initialized — starting 15Hz loop...");
    fm.run();

    // ── Cleanup ──
    g_fleet_manager = nullptr;
    rdt::core::Logger::shutdown();

    return 0;
}

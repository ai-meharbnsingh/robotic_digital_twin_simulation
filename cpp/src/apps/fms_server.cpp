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
//   Mixed fleet (alternative — replaces --robot flags):
//   fms_server --warehouse configs/warehouses/simple_grid.json \
//              --fleet configs/fleets/default_mixed.json
//
// Environment variables (fallbacks):
//   RDT_WAREHOUSE   — path to warehouse JSON
//   RDT_ROBOT       — path to robot YAML (single robot)
//   RDT_FLEET       — path to fleet manifest JSON
//   RDT_TCP_PORT    — TCP port (default 7010)
//   RDT_REST_PORT   — REST port (default 7012)
// ──────────────────────────────────────────────────────────

#include <iostream>
#include <string>
#include <vector>
#include <csignal>
#include <cstdlib>
#include <filesystem>

#include <spdlog/spdlog.h>
#include "rdt/version.h"
#include "rdt/core/Logger.h"
#include "rdt/core/Config.h"
#include "rdt/fleet/FleetManager.h"

// Async-signal-safe shutdown flag.
// The signal handler ONLY sets this atomic flag — no logging, no object
// method calls, no allocations. All cleanup happens in the main thread.
static volatile std::sig_atomic_t g_shutdown_requested = 0;

static void signalHandler(int /*signum*/) {
    g_shutdown_requested = 1;
}

static std::string getEnvOrDefault(const char* name, const std::string& fallback) {
    const char* val = std::getenv(name);
    return val ? std::string(val) : fallback;
}

static void printUsage(const char* prog) {
    std::cerr << "Usage: " << prog << " [options]\n"
              << "  --warehouse <path>   Warehouse JSON config (required)\n"
              << "  --robot <path>       Robot YAML config (repeatable)\n"
              << "  --fleet <path>       Fleet manifest JSON (alternative to --robot)\n"
              << "  --tcp-port <port>    TCP server port (default 7010)\n"
              << "  --rest-port <port>   REST server port (default 7012)\n"
              << "  --state-file <path>  JSON state output file (default fleet_state.json)\n"
              << "  --log-level <level>  Log level: trace|debug|info|warn|error (default info)\n"
              << "\n"
              << "Environment variables:\n"
              << "  RDT_WAREHOUSE, RDT_ROBOT, RDT_FLEET, RDT_TCP_PORT, RDT_REST_PORT\n";
}

int main(int argc, char* argv[]) {
    // ── Parse arguments ──
    std::string warehouse_path;
    std::vector<std::string> robot_paths;
    std::string fleet_path;
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
        } else if (arg == "--fleet" && i + 1 < argc) {
            fleet_path = argv[++i];
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
    if (fleet_path.empty()) {
        fleet_path = getEnvOrDefault("RDT_FLEET", "");
    }
    if (robot_paths.empty() && fleet_path.empty()) {
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
    if (robot_paths.empty() && fleet_path.empty()) {
        std::cerr << "Error: --robot or --fleet is required (or set RDT_ROBOT / RDT_FLEET)\n";
        printUsage(argv[0]);
        return 1;
    }
    if (!robot_paths.empty() && !fleet_path.empty()) {
        std::cerr << "Error: --robot and --fleet are mutually exclusive\n";
        printUsage(argv[0]);
        return 1;
    }

    // ── Initialize logger ──
    rdt::core::Logger::init(log_level, "fms_server.log");

    spdlog::info("═══════════════════════════════════════════════════════════");
    spdlog::info("  Robotic Digital Twin — FMS Server v{}.{}.{}",
                 RDT_VERSION_MAJOR, RDT_VERSION_MINOR, RDT_VERSION_PATCH);
    spdlog::info("  Warehouse: {}", warehouse_path);
    if (!fleet_path.empty()) {
        spdlog::info("  Fleet manifest: {}", fleet_path);
    } else {
        for (const auto& rp : robot_paths) {
            spdlog::info("  Robot: {}", rp);
        }
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

    if (!fleet_path.empty()) {
        // ── Fleet manifest mode: expand manifest → individual robot configs ──
        try {
            auto manifest = rdt::Config::loadFleetManifest(fleet_path);
            spdlog::info("Loaded fleet manifest '{}' ({} fleet entries)",
                         manifest.name, manifest.robots.size());

            // Resolve config paths relative to the fleet manifest's directory.
            // This allows launching fms_server from any directory as long as the
            // manifest and its referenced configs share a common ancestor.
            std::string fleet_base = std::filesystem::absolute(fleet_path)
                                         .parent_path()   // configs/fleets/
                                         .parent_path()   // configs/
                                         .parent_path()   // project root
                                         .string();
            robot_configs = rdt::Config::expandFleetManifest(manifest, fleet_base);
            spdlog::info("Expanded fleet to {} individual robots", robot_configs.size());

            for (const auto& rc : robot_configs) {
                spdlog::info("  Robot: {} (type={})",
                             rc.name, rdt::robot_type_to_string(rc.type));
            }
        } catch (const std::exception& e) {
            spdlog::error("Failed to load fleet manifest: {}", e.what());
            return 1;
        }
    } else {
        // ── Individual robot mode: load each --robot YAML ──
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
    }

    // ── Create and run FleetManager ──
    rdt::fleet::FleetManager fm(wh_config, robot_configs);

    // Install signal handlers (async-signal-safe: only sets atomic flag)
    std::signal(SIGINT,  signalHandler);
    std::signal(SIGTERM, signalHandler);

    if (!fm.init(tcp_port, rest_port, state_file)) {
        spdlog::error("FleetManager initialization failed");
        return 1;
    }

    spdlog::info("FleetManager initialized — starting 15Hz loop...");

    // Run the main loop manually, checking the signal flag each cycle.
    // This avoids calling FleetManager methods from the signal handler.
    while (!g_shutdown_requested) {
        fm.runOneCycle();
    }

    // Signal caught — perform clean shutdown from main thread (safe)
    spdlog::info("Signal caught — performing clean shutdown...");
    fm.stop();

    // ── Cleanup ──
    rdt::core::Logger::shutdown();

    return 0;
}

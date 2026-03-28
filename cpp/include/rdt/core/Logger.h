#pragma once

// ──────────────────────────────────────────────────────────
// rdt/core/Logger.h — Thread-safe spdlog wrapper with JSON file output
// ──────────────────────────────────────────────────────────

#include <string>
#include <memory>
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/basic_file_sink.h>

namespace rdt {
namespace core {

/// @brief Centralized logger for the Robotic Digital Twin system.
///
/// Wraps spdlog with two sinks:
///   - Console: human-readable colored output
///   - File (optional): structured JSON format for machine parsing
///
/// Thread-safe — spdlog handles all internal locking.
class Logger {
public:
    /// Initialize the global logger.
    /// @param log_level  One of: "trace", "debug", "info", "warn", "error", "critical"
    /// @param log_file_path  If non-empty, JSON-formatted logs are written to this file.
    /// @return true on success, false if initialization fails.
    static bool init(const std::string& log_level = "info",
                     const std::string& log_file_path = "");

    /// Shut down all loggers and flush buffers. Call before exit.
    static void shutdown();

    /// Get the underlying spdlog logger instance.
    /// @return Shared pointer to the "rdt" logger, or nullptr if not initialized.
    static std::shared_ptr<spdlog::logger> get();

    /// Check whether the logger has been initialized.
    static bool is_initialized();

private:
    Logger() = default;

    /// Convert string level name to spdlog enum.
    static spdlog::level::level_enum parse_level(const std::string& level);

    static bool s_initialized;
};

}  // namespace core
}  // namespace rdt

// ── Convenience macros ──────────────────────────────────────
// These are the primary logging interface for all RDT code.
// Usage: RDT_LOG_INFO("Robot {} at position ({}, {})", id, x, y);

#define RDT_LOG_TRACE(...)   do { auto _l = rdt::core::Logger::get(); if (_l) _l->trace(__VA_ARGS__); } while(0)
#define RDT_LOG_DEBUG(...)   do { auto _l = rdt::core::Logger::get(); if (_l) _l->debug(__VA_ARGS__); } while(0)
#define RDT_LOG_INFO(...)    do { auto _l = rdt::core::Logger::get(); if (_l) _l->info(__VA_ARGS__); } while(0)
#define RDT_LOG_WARN(...)    do { auto _l = rdt::core::Logger::get(); if (_l) _l->warn(__VA_ARGS__); } while(0)
#define RDT_LOG_ERROR(...)   do { auto _l = rdt::core::Logger::get(); if (_l) _l->error(__VA_ARGS__); } while(0)
#define RDT_LOG_CRITICAL(...) do { auto _l = rdt::core::Logger::get(); if (_l) _l->critical(__VA_ARGS__); } while(0)

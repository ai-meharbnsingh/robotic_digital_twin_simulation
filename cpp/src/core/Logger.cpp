// ──────────────────────────────────────────────────────────
// core/Logger.cpp — spdlog wrapper implementation
// ──────────────────────────────────────────────────────────

#include "rdt/core/Logger.h"

#include <vector>
#include <algorithm>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/pattern_formatter.h>

namespace rdt {
namespace core {

// Static member
bool Logger::s_initialized = false;

bool Logger::init(const std::string& log_level, const std::string& log_file_path) {
    // Prevent double-init; drop existing logger first if re-initializing.
    if (s_initialized) {
        spdlog::drop("rdt");
        s_initialized = false;
    }

    try {
        std::vector<spdlog::sink_ptr> sinks;

        // Console sink — human-readable colored output
        auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
        console_sink->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%^%l%$] [%t] %v");
        sinks.push_back(console_sink);

        // File sink — structured JSON format (one JSON object per line)
        if (!log_file_path.empty()) {
            auto file_sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(
                log_file_path, /*truncate=*/true);
            // JSON pattern: {"time":"...","level":"...","thread":N,"message":"..."}
            file_sink->set_pattern(
                R"({"time":"%Y-%m-%d %H:%M:%S.%e","level":"%l","thread":%t,"message":"%v"})");
            sinks.push_back(file_sink);
        }

        // Create multi-sink logger named "rdt"
        auto logger = std::make_shared<spdlog::logger>("rdt", sinks.begin(), sinks.end());
        logger->set_level(parse_level(log_level));
        logger->flush_on(spdlog::level::warn);  // Auto-flush on warn and above

        // Register as both named logger and default
        spdlog::register_logger(logger);
        spdlog::set_default_logger(logger);

        s_initialized = true;
        return true;

    } catch (const spdlog::spdlog_ex& ex) {
        // Can't use our logger here — it failed to initialize
        fprintf(stderr, "Logger::init() failed: %s\n", ex.what());
        return false;
    }
}

void Logger::shutdown() {
    if (s_initialized) {
        spdlog::get("rdt")->flush();
        spdlog::drop("rdt");
        s_initialized = false;
    }
    spdlog::shutdown();
}

std::shared_ptr<spdlog::logger> Logger::get() {
    return spdlog::get("rdt");
}

bool Logger::is_initialized() {
    return s_initialized;
}

spdlog::level::level_enum Logger::parse_level(const std::string& level) {
    // Convert to lowercase for comparison
    std::string lower = level;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return std::tolower(c); });

    if (lower == "trace")    return spdlog::level::trace;
    if (lower == "debug")    return spdlog::level::debug;
    if (lower == "info")     return spdlog::level::info;
    if (lower == "warn")     return spdlog::level::warn;
    if (lower == "error")    return spdlog::level::err;
    if (lower == "critical") return spdlog::level::critical;

    // Default to info for unrecognized levels
    return spdlog::level::info;
}

}  // namespace core
}  // namespace rdt

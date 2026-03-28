// ──────────────────────────────────────────────────────────
// test_logger.cpp — Tests for rdt::core::Logger
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include <fstream>
#include <string>
#include <sstream>
#include <cstdio>

#include "rdt/core/Logger.h"

// Helper: read entire file into a string
static std::string read_file(const std::string& path) {
    std::ifstream ifs(path);
    std::stringstream ss;
    ss << ifs.rdbuf();
    return ss.str();
}

// Helper: check if file exists
static bool file_exists(const std::string& path) {
    std::ifstream ifs(path);
    return ifs.good();
}

class LoggerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Ensure clean state before each test
        rdt::core::Logger::shutdown();
    }

    void TearDown() override {
        rdt::core::Logger::shutdown();
    }
};

// ── TEST: Logger::init() succeeds ──────────────────────────

TEST_F(LoggerTest, InitSucceeds) {
    bool result = rdt::core::Logger::init("info");
    EXPECT_TRUE(result) << "Logger::init() should return true on success";
    EXPECT_TRUE(rdt::core::Logger::is_initialized())
        << "Logger should report initialized after successful init";
}

TEST_F(LoggerTest, InitWithAllLevels) {
    // Verify all log level strings are accepted
    std::vector<std::string> levels = {
        "trace", "debug", "info", "warn", "error", "critical"
    };
    for (const auto& level : levels) {
        rdt::core::Logger::shutdown();
        bool result = rdt::core::Logger::init(level);
        EXPECT_TRUE(result) << "Logger::init(\"" << level << "\") should succeed";
    }
}

TEST_F(LoggerTest, GetReturnsValidLogger) {
    rdt::core::Logger::init("info");
    auto logger = rdt::core::Logger::get();
    ASSERT_NE(logger, nullptr) << "Logger::get() must return non-null after init";
    EXPECT_EQ(logger->name(), "rdt") << "Logger name should be 'rdt'";
}

// ── TEST: RDT_LOG_INFO writes to stdout ────────────────────
// We verify the macro doesn't crash and the logger processes the message.
// Actual stdout capture is tricky in gtest, so we verify via file sink.

TEST_F(LoggerTest, LogMacrosDoNotCrashBeforeInit) {
    // Before init, macros should be safe no-ops (logger is null)
    EXPECT_NO_THROW({
        RDT_LOG_INFO("This should not crash");
        RDT_LOG_WARN("Neither should this");
        RDT_LOG_ERROR("Nor this");
        RDT_LOG_DEBUG("Nor this");
    });
}

TEST_F(LoggerTest, LogMacrosDoNotCrashAfterInit) {
    rdt::core::Logger::init("trace");
    EXPECT_NO_THROW({
        RDT_LOG_TRACE("trace message");
        RDT_LOG_DEBUG("debug message");
        RDT_LOG_INFO("info message: {}", 42);
        RDT_LOG_WARN("warn message");
        RDT_LOG_ERROR("error message");
        RDT_LOG_CRITICAL("critical message");
    });
}

// ── TEST: Log file is created when file path given ──────────

TEST_F(LoggerTest, FileIsCreatedWhenPathGiven) {
    std::string log_path = "test_rdt_logger_output.log";

    bool result = rdt::core::Logger::init("info", log_path);
    ASSERT_TRUE(result) << "Logger::init() with file path should succeed";

    // Write a message so the file gets content
    RDT_LOG_INFO("file creation test message");

    // Flush to ensure writes are committed
    auto logger = rdt::core::Logger::get();
    ASSERT_NE(logger, nullptr);
    logger->flush();

    // Verify file exists
    EXPECT_TRUE(file_exists(log_path))
        << "Log file '" << log_path << "' should exist after logging";
}

TEST_F(LoggerTest, FileContainsLoggedMessages) {
    std::string log_path = "test_rdt_logger_content.log";

    rdt::core::Logger::init("info", log_path);

    std::string test_msg = "UNIQUE_TEST_MARKER_12345";
    RDT_LOG_INFO("{}", test_msg);

    auto logger = rdt::core::Logger::get();
    logger->flush();

    std::string content = read_file(log_path);
    EXPECT_NE(content.find(test_msg), std::string::npos)
        << "Log file should contain the logged message. File content: " << content;
}

TEST_F(LoggerTest, FileOutputIsJsonFormat) {
    std::string log_path = "test_rdt_logger_json.log";

    rdt::core::Logger::init("info", log_path);

    RDT_LOG_INFO("json format test");

    auto logger = rdt::core::Logger::get();
    logger->flush();

    std::string content = read_file(log_path);

    // Verify JSON structure markers are present
    EXPECT_NE(content.find("\"time\""), std::string::npos)
        << "JSON log should contain 'time' field";
    EXPECT_NE(content.find("\"level\""), std::string::npos)
        << "JSON log should contain 'level' field";
    EXPECT_NE(content.find("\"message\""), std::string::npos)
        << "JSON log should contain 'message' field";
    EXPECT_NE(content.find("\"thread\""), std::string::npos)
        << "JSON log should contain 'thread' field";
    EXPECT_NE(content.find("json format test"), std::string::npos)
        << "JSON log should contain the actual message text";
}

TEST_F(LoggerTest, ReinitializationWorks) {
    // First init
    EXPECT_TRUE(rdt::core::Logger::init("info"));
    EXPECT_TRUE(rdt::core::Logger::is_initialized());

    // Re-init should succeed (drops previous logger)
    EXPECT_TRUE(rdt::core::Logger::init("debug"));
    EXPECT_TRUE(rdt::core::Logger::is_initialized());

    auto logger = rdt::core::Logger::get();
    ASSERT_NE(logger, nullptr);
    EXPECT_EQ(logger->level(), spdlog::level::debug)
        << "After re-init with 'debug', logger level should be debug";
}

TEST_F(LoggerTest, ShutdownCleansUp) {
    rdt::core::Logger::init("info");
    EXPECT_TRUE(rdt::core::Logger::is_initialized());

    rdt::core::Logger::shutdown();
    EXPECT_FALSE(rdt::core::Logger::is_initialized())
        << "After shutdown, logger should not be initialized";
}

TEST_F(LoggerTest, LevelFilteringWorks) {
    std::string log_path = "test_rdt_logger_filter.log";

    // Init at WARN level — info messages should be suppressed
    rdt::core::Logger::init("warn", log_path);

    RDT_LOG_INFO("should_not_appear");
    RDT_LOG_WARN("should_appear_warn");
    RDT_LOG_ERROR("should_appear_error");

    auto logger = rdt::core::Logger::get();
    logger->flush();

    std::string content = read_file(log_path);
    EXPECT_EQ(content.find("should_not_appear"), std::string::npos)
        << "INFO message should be filtered at WARN level";
    EXPECT_NE(content.find("should_appear_warn"), std::string::npos)
        << "WARN message should appear at WARN level";
    EXPECT_NE(content.find("should_appear_error"), std::string::npos)
        << "ERROR message should appear at WARN level";
}

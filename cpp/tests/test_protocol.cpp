// ──────────────────────────────────────────────────────────
// test_protocol.cpp — ProtocolV1 serialize / parse / CRC32
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/network/ProtocolV1.h"

#include <string>
#include <cmath>
#include <sstream>
#include <algorithm>

using namespace rdt::network;

// ── Helper: build a fully populated message ──────────────

static ProtocolV1Message make_sample_message() {
    ProtocolV1Message msg;
    msg.timestamp         = 1719500000.123456;
    msg.robot_id          = "robot_01";
    msg.x                 = 1.5;
    msg.y                 = 2.3;
    msg.theta             = 0.785398;
    msg.state             = "MOVING";
    msg.battery_pct       = 87.5;
    msg.battery_voltage   = 24.1;
    msg.charging          = 0;
    msg.linear_vel        = 0.5;
    msg.angular_vel       = 0.1;
    msg.obstacle_detected = 1;
    msg.obstacle_range    = 2.5;
    msg.barcode_row       = 3;
    msg.barcode_col       = 7;
    msg.barcode_valid     = 1;
    msg.current_task_id   = "task_042";
    msg.task_state        = "IN_PROGRESS";
    msg.error_code        = 0;
    msg.motor_left_rpm    = 120.5;
    msg.motor_right_rpm   = 118.3;
    msg.imu_roll          = 0.01;
    msg.imu_pitch         = -0.02;
    msg.imu_yaw           = 1.57;
    msg.attachment_state  = "LOADED";
    msg.load_weight       = 15.0;
    msg.conveyor_speed    = 0.3;
    msg.temperature       = 42.1;
    msg.wifi_rssi         = -65;
    msg.uptime_sec        = 86400;
    msg.firmware_version  = "v2.1.0";
    msg.heartbeat_seq     = 12345;
    msg.checksum          = 0;  // Will be computed during serialize
    return msg;
}

// ── Test: Serialize produces 33 pipe-delimited fields ────

TEST(ProtocolV1, SerializeProduces33Fields) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);

    // Count pipes
    size_t pipe_count = std::count(raw.begin(), raw.end(), '|');
    // 33 fields means 32 pipe delimiters
    EXPECT_EQ(pipe_count, 32u);
}

// ── Test: Serialize contains all field values ────────────

TEST(ProtocolV1, SerializeContainsRobotId) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    EXPECT_NE(raw.find("robot_01"), std::string::npos);
}

TEST(ProtocolV1, SerializeContainsState) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    EXPECT_NE(raw.find("MOVING"), std::string::npos);
}

TEST(ProtocolV1, SerializeContainsTaskId) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    EXPECT_NE(raw.find("task_042"), std::string::npos);
}

TEST(ProtocolV1, SerializeContainsFirmwareVersion) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    EXPECT_NE(raw.find("v2.1.0"), std::string::npos);
}

// ── Test: Parse back — exact field match ─────────────────

TEST(ProtocolV1, ParseBackExactFieldMatch) {
    auto original = make_sample_message();
    std::string raw = serialize(original);
    auto parsed_opt = parse(raw);

    ASSERT_TRUE(parsed_opt.has_value());
    auto& parsed = parsed_opt.value();

    // Compare all 33 fields
    EXPECT_NEAR(parsed.timestamp, original.timestamp, 0.001);
    EXPECT_EQ(parsed.robot_id, original.robot_id);
    EXPECT_NEAR(parsed.x, original.x, 1e-4);
    EXPECT_NEAR(parsed.y, original.y, 1e-4);
    EXPECT_NEAR(parsed.theta, original.theta, 1e-4);
    EXPECT_EQ(parsed.state, original.state);
    EXPECT_NEAR(parsed.battery_pct, original.battery_pct, 1e-4);
    EXPECT_NEAR(parsed.battery_voltage, original.battery_voltage, 1e-4);
    EXPECT_EQ(parsed.charging, original.charging);
    EXPECT_NEAR(parsed.linear_vel, original.linear_vel, 1e-4);
    EXPECT_NEAR(parsed.angular_vel, original.angular_vel, 1e-4);
    EXPECT_EQ(parsed.obstacle_detected, original.obstacle_detected);
    EXPECT_NEAR(parsed.obstacle_range, original.obstacle_range, 1e-4);
    EXPECT_EQ(parsed.barcode_row, original.barcode_row);
    EXPECT_EQ(parsed.barcode_col, original.barcode_col);
    EXPECT_EQ(parsed.barcode_valid, original.barcode_valid);
    EXPECT_EQ(parsed.current_task_id, original.current_task_id);
    EXPECT_EQ(parsed.task_state, original.task_state);
    EXPECT_EQ(parsed.error_code, original.error_code);
    EXPECT_NEAR(parsed.motor_left_rpm, original.motor_left_rpm, 1e-4);
    EXPECT_NEAR(parsed.motor_right_rpm, original.motor_right_rpm, 1e-4);
    EXPECT_NEAR(parsed.imu_roll, original.imu_roll, 1e-4);
    EXPECT_NEAR(parsed.imu_pitch, original.imu_pitch, 1e-4);
    EXPECT_NEAR(parsed.imu_yaw, original.imu_yaw, 1e-4);
    EXPECT_EQ(parsed.attachment_state, original.attachment_state);
    EXPECT_NEAR(parsed.load_weight, original.load_weight, 1e-4);
    EXPECT_NEAR(parsed.conveyor_speed, original.conveyor_speed, 1e-4);
    EXPECT_NEAR(parsed.temperature, original.temperature, 1e-4);
    EXPECT_EQ(parsed.wifi_rssi, original.wifi_rssi);
    EXPECT_EQ(parsed.uptime_sec, original.uptime_sec);
    EXPECT_EQ(parsed.firmware_version, original.firmware_version);
    EXPECT_EQ(parsed.heartbeat_seq, original.heartbeat_seq);
}

// ── Test: CRC32 computation is deterministic ─────────────

TEST(ProtocolV1, CRC32Deterministic) {
    auto msg = make_sample_message();
    uint32_t crc1 = computeCRC32(msg);
    uint32_t crc2 = computeCRC32(msg);
    EXPECT_EQ(crc1, crc2);
    EXPECT_NE(crc1, 0u);  // Should not be zero for non-empty data
}

// ── Test: CRC32 changes when data changes ────────────────

TEST(ProtocolV1, CRC32ChangesWithData) {
    auto msg1 = make_sample_message();
    auto msg2 = make_sample_message();
    msg2.x = 999.999;

    uint32_t crc1 = computeCRC32(msg1);
    uint32_t crc2 = computeCRC32(msg2);
    EXPECT_NE(crc1, crc2);
}

// ── Test: validateCRC32 passes after serialize ───────────

TEST(ProtocolV1, ValidateCRC32AfterSerialize) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());
    EXPECT_TRUE(validateCRC32(parsed_opt.value()));
}

// ── Test: Invalid CRC32 rejected ─────────────────────────

TEST(ProtocolV1, InvalidCRC32Rejected) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());

    // Tamper with a field
    auto tampered = parsed_opt.value();
    tampered.x = 999.0;
    // The checksum was computed for the original x value, so it should fail.
    EXPECT_FALSE(validateCRC32(tampered));
}

// ── Test: Missing fields → parse returns nullopt ─────────

TEST(ProtocolV1, MissingFieldsReturnsNullopt) {
    // Only 5 fields instead of 33
    std::string bad = "1.0|robot_01|1.5|2.3|0.78";
    auto result = parse(bad);
    EXPECT_FALSE(result.has_value());
}

TEST(ProtocolV1, EmptyStringReturnsNullopt) {
    auto result = parse("");
    EXPECT_FALSE(result.has_value());
}

TEST(ProtocolV1, TooManyFieldsReturnsNullopt) {
    // Build 34 pipe-delimited fields
    std::string raw;
    for (size_t i = 0; i < 34; ++i) {
        if (i > 0) raw += '|';
        raw += "0";
    }
    auto result = parse(raw);
    EXPECT_FALSE(result.has_value());
}

// ── Test: Roundtrip — serialize→parse identical ──────────

TEST(ProtocolV1, RoundtripIdentical) {
    auto original = make_sample_message();
    std::string raw = serialize(original);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());

    // Re-serialize the parsed message and compare raw strings
    std::string raw2 = serialize(parsed_opt.value());
    EXPECT_EQ(raw, raw2);
}

// ── Test: Zero/default message roundtrips ────────────────

TEST(ProtocolV1, DefaultMessageRoundtrip) {
    ProtocolV1Message msg;  // All defaults (zeros, empty strings)
    msg.robot_id = "default_bot";
    msg.state = "IDLE";
    msg.task_state = "NOT_ASSIGNED";
    msg.attachment_state = "EMPTY";
    msg.firmware_version = "v0.0.0";

    std::string raw = serialize(msg);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());
    EXPECT_TRUE(validateCRC32(parsed_opt.value()));
    EXPECT_EQ(parsed_opt.value().robot_id, "default_bot");
}

// ── Test: Negative values serialize/parse correctly ──────

TEST(ProtocolV1, NegativeValuesRoundtrip) {
    auto msg = make_sample_message();
    msg.imu_pitch = -0.5;
    msg.wifi_rssi = -90;
    msg.angular_vel = -1.2;
    msg.temperature = -10.5;

    std::string raw = serialize(msg);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());
    auto& p = parsed_opt.value();

    EXPECT_NEAR(p.imu_pitch, -0.5, 1e-4);
    EXPECT_EQ(p.wifi_rssi, -90);
    EXPECT_NEAR(p.angular_vel, -1.2, 1e-4);
    EXPECT_NEAR(p.temperature, -10.5, 1e-4);
    EXPECT_TRUE(validateCRC32(p));
}

// ── Test: Large numeric values ───────────────────────────

TEST(ProtocolV1, LargeValuesRoundtrip) {
    auto msg = make_sample_message();
    msg.uptime_sec = 31536000;    // 1 year in seconds
    msg.heartbeat_seq = 999999999;
    msg.timestamp = 1893456000.0; // ~year 2030

    std::string raw = serialize(msg);
    auto parsed_opt = parse(raw);
    ASSERT_TRUE(parsed_opt.has_value());
    EXPECT_EQ(parsed_opt.value().uptime_sec, 31536000u);
    EXPECT_EQ(parsed_opt.value().heartbeat_seq, 999999999u);
    EXPECT_TRUE(validateCRC32(parsed_opt.value()));
}

// ── Test: Non-numeric field causes parse failure ─────────

TEST(ProtocolV1, NonNumericFieldCausesNullopt) {
    // Build a raw string with 33 fields but put "abc" where a double is expected
    auto msg = make_sample_message();
    std::string raw = serialize(msg);

    // Replace the first field (timestamp, a double) with "abc"
    auto first_pipe = raw.find('|');
    ASSERT_NE(first_pipe, std::string::npos);
    std::string bad_raw = "not_a_number" + raw.substr(first_pipe);

    auto result = parse(bad_raw);
    EXPECT_FALSE(result.has_value());
}

// ── Test: CRC32 embedded in serialized string ────────────

TEST(ProtocolV1, ChecksumIsLastField) {
    auto msg = make_sample_message();
    std::string raw = serialize(msg);

    // The last field (after last pipe) should be a numeric CRC
    auto last_pipe = raw.rfind('|');
    ASSERT_NE(last_pipe, std::string::npos);
    std::string checksum_str = raw.substr(last_pipe + 1);
    EXPECT_FALSE(checksum_str.empty());

    // Should be parseable as a number
    uint32_t crc = std::stoul(checksum_str);
    EXPECT_NE(crc, 0u);
}

// ── Test: Multiple different robots produce different CRC ─

TEST(ProtocolV1, DifferentRobotsDifferentCRC) {
    auto msg1 = make_sample_message();
    msg1.robot_id = "robot_01";

    auto msg2 = make_sample_message();
    msg2.robot_id = "robot_02";

    EXPECT_NE(computeCRC32(msg1), computeCRC32(msg2));
}

// ── Test: Serialize is pipe-delimited (no spaces) ────────

TEST(ProtocolV1, PipeDelimitedNoExtraSpaces) {
    ProtocolV1Message msg;
    msg.robot_id = "bot";
    msg.state = "IDLE";
    msg.task_state = "NOT_ASSIGNED";
    msg.attachment_state = "NONE";
    msg.firmware_version = "v1";
    msg.current_task_id = "t1";

    std::string raw = serialize(msg);

    // Split by pipe, verify field count
    size_t count = 1;
    for (char c : raw) {
        if (c == '|') ++count;
    }
    EXPECT_EQ(count, PROTOCOL_V1_FIELD_COUNT);
}

// ── Test: Charging field is 0 or 1 ──────────────────────

TEST(ProtocolV1, ChargingBooleanRoundtrip) {
    auto msg = make_sample_message();

    // Test charging = 0
    msg.charging = 0;
    auto raw0 = serialize(msg);
    auto p0 = parse(raw0);
    ASSERT_TRUE(p0.has_value());
    EXPECT_EQ(p0.value().charging, 0);

    // Test charging = 1
    msg.charging = 1;
    auto raw1 = serialize(msg);
    auto p1 = parse(raw1);
    ASSERT_TRUE(p1.has_value());
    EXPECT_EQ(p1.value().charging, 1);
}

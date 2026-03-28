#pragma once

// ──────────────────────────────────────────────────────────
// rdt/network/ProtocolV1.h — Wire protocol for robot↔FMS
//
// Format: 33 pipe-delimited fields + CRC32 checksum.
// Example: "1719500000.123|robot_01|1.5|2.3|0.78|MOVING|..."
//
// Field order is FIXED and must match the struct layout.
// The checksum field (index 32) is a CRC32 over fields 0–31.
// ──────────────────────────────────────────────────────────

#include <string>
#include <optional>
#include <cstdint>

namespace rdt {
namespace network {

/// Total number of pipe-delimited fields in a V1 message.
static constexpr size_t PROTOCOL_V1_FIELD_COUNT = 33;

/// @brief All 33 fields transmitted between robot and FMS.
///
/// Field indices (0-based):
///  0  timestamp           12 obstacle_range       24 load_weight
///  1  robot_id            13 barcode_row          25 conveyor_speed
///  2  x                   14 barcode_col          26 temperature
///  3  y                   15 barcode_valid        27 wifi_rssi
///  4  theta               16 current_task_id      28 uptime_sec
///  5  state               17 task_state           29 firmware_version
///  6  battery_pct         18 error_code           30 heartbeat_seq
///  7  battery_voltage     19 motor_left_rpm       31 checksum (CRC32)
///  8  charging            20 motor_right_rpm      32 (end — field 31 is last)
///  9  linear_vel          21 imu_roll
/// 10  angular_vel         22 imu_pitch
/// 11  obstacle_detected   23 imu_yaw
///                         24 attachment_state
///
/// NOTE: Field count is 33 (indices 0–32). Index 32 = checksum.
struct ProtocolV1Message {
    // ── Identity & Pose (0–4) ──
    double      timestamp         = 0.0;      //  0
    std::string robot_id;                      //  1
    double      x                 = 0.0;      //  2
    double      y                 = 0.0;      //  3
    double      theta             = 0.0;      //  4

    // ── State & Battery (5–8) ──
    std::string state;                         //  5
    double      battery_pct       = 0.0;      //  6
    double      battery_voltage   = 0.0;      //  7
    int         charging          = 0;        //  8  (0/1)

    // ── Velocity (9–10) ──
    double      linear_vel        = 0.0;      //  9
    double      angular_vel       = 0.0;      // 10

    // ── Obstacle (11–12) ──
    int         obstacle_detected = 0;        // 11 (0/1)
    double      obstacle_range    = 0.0;      // 12

    // ── Barcode (13–15) ──
    int         barcode_row       = 0;        // 13
    int         barcode_col       = 0;        // 14
    int         barcode_valid     = 0;        // 15 (0/1)

    // ── Task (16–18) ──
    std::string current_task_id;               // 16
    std::string task_state;                    // 17
    int         error_code        = 0;        // 18

    // ── Motors (19–20) ──
    double      motor_left_rpm    = 0.0;      // 19
    double      motor_right_rpm   = 0.0;      // 20

    // ── IMU (21–23) ──
    double      imu_roll          = 0.0;      // 21
    double      imu_pitch         = 0.0;      // 22
    double      imu_yaw           = 0.0;      // 23

    // ── Attachment & Load (24–25) ──
    std::string attachment_state;               // 24
    double      load_weight       = 0.0;      // 25

    // ── Environment (26–28) ──
    double      conveyor_speed    = 0.0;      // 26
    double      temperature       = 0.0;      // 27
    int         wifi_rssi         = 0;        // 28

    // ── System (29–31) ──
    uint64_t    uptime_sec        = 0;        // 29
    std::string firmware_version;              // 30
    uint64_t    heartbeat_seq     = 0;        // 31

    // ── Checksum (32) ──
    uint32_t    checksum          = 0;        // 32
};

/// Serialize a ProtocolV1Message to a pipe-delimited string.
/// All 33 fields are written in index order, separated by '|'.
/// The checksum field (index 32) is computed automatically from fields 0–31.
std::string serialize(const ProtocolV1Message& msg);

/// Parse a pipe-delimited string into a ProtocolV1Message.
/// Returns std::nullopt if:
///   - Field count != 33
///   - Numeric fields fail to parse
/// NOTE: Does NOT validate CRC. Call validateCRC32() separately.
std::optional<ProtocolV1Message> parse(const std::string& raw);

/// Compute CRC32 over the payload (fields 0–31, pipe-joined).
uint32_t computeCRC32(const ProtocolV1Message& msg);

/// Validate that the message's stored checksum matches the computed CRC32.
bool validateCRC32(const ProtocolV1Message& msg);

}  // namespace network
}  // namespace rdt

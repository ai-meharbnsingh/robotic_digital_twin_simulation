// ──────────────────────────────────────────────────────────
// rdt/network/ProtocolV1.cpp — Serialize / parse / CRC32
// ──────────────────────────────────────────────────────────

#include "rdt/network/ProtocolV1.h"

#include <sstream>
#include <vector>
#include <cstdint>
#include <stdexcept>
#include <iomanip>

namespace rdt {
namespace network {

// ── CRC-32 (IEEE polynomial 0xEDB88320) ──────────────────
// Table is generated at startup to avoid hand-typed errors.

static uint32_t CRC32_TABLE[256];
static bool     CRC32_TABLE_READY = false;

static void init_crc32_table() {
    if (CRC32_TABLE_READY) return;
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            if (crc & 1u)
                crc = (crc >> 1) ^ 0xEDB88320u;
            else
                crc >>= 1;
        }
        CRC32_TABLE[i] = crc;
    }
    CRC32_TABLE_READY = true;
}

/// Compute CRC32 over a byte buffer.
static uint32_t crc32_bytes(const uint8_t* data, size_t len) {
    init_crc32_table();
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; ++i) {
        uint8_t idx = static_cast<uint8_t>(crc ^ data[i]);
        crc = CRC32_TABLE[idx] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

/// Compute CRC32 over a std::string.
static uint32_t crc32_string(const std::string& s) {
    return crc32_bytes(reinterpret_cast<const uint8_t*>(s.data()), s.size());
}

// ── Split helper ──────────────────────────────────────────

static std::vector<std::string> split_pipe(const std::string& s) {
    std::vector<std::string> tokens;
    std::istringstream iss(s);
    std::string token;
    while (std::getline(iss, token, '|')) {
        tokens.push_back(token);
    }
    return tokens;
}

// ── Build the payload string (fields 0–31) ────────────────

static std::string build_payload(const ProtocolV1Message& msg) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(6);

    oss << msg.timestamp;                                   //  0
    oss << '|' << msg.robot_id;                             //  1
    oss << '|' << msg.x;                                    //  2
    oss << '|' << msg.y;                                    //  3
    oss << '|' << msg.theta;                                //  4
    oss << '|' << msg.state;                                //  5
    oss << '|' << msg.battery_pct;                          //  6
    oss << '|' << msg.battery_voltage;                      //  7
    oss << '|' << msg.charging;                             //  8
    oss << '|' << msg.linear_vel;                           //  9
    oss << '|' << msg.angular_vel;                          // 10
    oss << '|' << msg.obstacle_detected;                    // 11
    oss << '|' << msg.obstacle_range;                       // 12
    oss << '|' << msg.barcode_row;                          // 13
    oss << '|' << msg.barcode_col;                          // 14
    oss << '|' << msg.barcode_valid;                        // 15
    oss << '|' << msg.current_task_id;                      // 16
    oss << '|' << msg.task_state;                           // 17
    oss << '|' << msg.error_code;                           // 18
    oss << '|' << msg.motor_left_rpm;                       // 19
    oss << '|' << msg.motor_right_rpm;                      // 20
    oss << '|' << msg.imu_roll;                             // 21
    oss << '|' << msg.imu_pitch;                            // 22
    oss << '|' << msg.imu_yaw;                              // 23
    oss << '|' << msg.attachment_state;                     // 24
    oss << '|' << msg.load_weight;                          // 25
    oss << '|' << msg.conveyor_speed;                       // 26
    oss << '|' << msg.temperature;                          // 27
    oss << '|' << msg.wifi_rssi;                            // 28
    oss << '|' << msg.uptime_sec;                           // 29
    oss << '|' << msg.firmware_version;                     // 30
    oss << '|' << msg.heartbeat_seq;                        // 31

    return oss.str();
}

// ── Public API ────────────────────────────────────────────

uint32_t computeCRC32(const ProtocolV1Message& msg) {
    std::string payload = build_payload(msg);
    return crc32_string(payload);
}

bool validateCRC32(const ProtocolV1Message& msg) {
    return msg.checksum == computeCRC32(msg);
}

std::string serialize(const ProtocolV1Message& msg) {
    std::string payload = build_payload(msg);
    uint32_t crc = crc32_string(payload);
    payload += '|';
    payload += std::to_string(crc);                         // 32
    return payload;
}

std::optional<ProtocolV1Message> parse(const std::string& raw) {
    auto fields = split_pipe(raw);
    if (fields.size() != PROTOCOL_V1_FIELD_COUNT) {
        return std::nullopt;
    }

    ProtocolV1Message msg;
    try {
        msg.timestamp         = std::stod(fields[0]);
        msg.robot_id          = fields[1];
        msg.x                 = std::stod(fields[2]);
        msg.y                 = std::stod(fields[3]);
        msg.theta             = std::stod(fields[4]);
        msg.state             = fields[5];
        msg.battery_pct       = std::stod(fields[6]);
        msg.battery_voltage   = std::stod(fields[7]);
        msg.charging          = std::stoi(fields[8]);
        msg.linear_vel        = std::stod(fields[9]);
        msg.angular_vel       = std::stod(fields[10]);
        msg.obstacle_detected = std::stoi(fields[11]);
        msg.obstacle_range    = std::stod(fields[12]);
        msg.barcode_row       = std::stoi(fields[13]);
        msg.barcode_col       = std::stoi(fields[14]);
        msg.barcode_valid     = std::stoi(fields[15]);
        msg.current_task_id   = fields[16];
        msg.task_state        = fields[17];
        msg.error_code        = std::stoi(fields[18]);
        msg.motor_left_rpm    = std::stod(fields[19]);
        msg.motor_right_rpm   = std::stod(fields[20]);
        msg.imu_roll          = std::stod(fields[21]);
        msg.imu_pitch         = std::stod(fields[22]);
        msg.imu_yaw           = std::stod(fields[23]);
        msg.attachment_state  = fields[24];
        msg.load_weight       = std::stod(fields[25]);
        msg.conveyor_speed    = std::stod(fields[26]);
        msg.temperature       = std::stod(fields[27]);
        msg.wifi_rssi         = std::stoi(fields[28]);
        msg.uptime_sec        = std::stoull(fields[29]);
        msg.firmware_version  = fields[30];
        msg.heartbeat_seq     = std::stoull(fields[31]);
        msg.checksum          = static_cast<uint32_t>(std::stoul(fields[32]));
    } catch (const std::exception&) {
        return std::nullopt;
    }

    return msg;
}

}  // namespace network
}  // namespace rdt

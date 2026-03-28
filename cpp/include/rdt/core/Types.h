#pragma once

// ──────────────────────────────────────────────────────────
// rdt/core/Types.h — Core domain types for the FMS
//
// All structs provide operator== for testing and
// to_json() / from_json() for jsoncpp serialization.
// ──────────────────────────────────────────────────────────

#include <string>
#include <vector>
#include <json/json.h>

namespace rdt {

// ── Pose ────────────────────────────────────────────────

struct Pose {
    double x     = 0.0;
    double y     = 0.0;
    double z     = 0.0;
    double roll  = 0.0;
    double pitch = 0.0;
    double yaw   = 0.0;

    bool operator==(const Pose& o) const {
        return x == o.x && y == o.y && z == o.z &&
               roll == o.roll && pitch == o.pitch && yaw == o.yaw;
    }
    bool operator!=(const Pose& o) const { return !(*this == o); }
};

inline Json::Value to_json(const Pose& p) {
    Json::Value v;
    v["x"]     = p.x;
    v["y"]     = p.y;
    v["z"]     = p.z;
    v["roll"]  = p.roll;
    v["pitch"] = p.pitch;
    v["yaw"]   = p.yaw;
    return v;
}

inline Pose pose_from_json(const Json::Value& v) {
    Pose p;
    p.x     = v.get("x",     0.0).asDouble();
    p.y     = v.get("y",     0.0).asDouble();
    p.z     = v.get("z",     0.0).asDouble();
    p.roll  = v.get("roll",  0.0).asDouble();
    p.pitch = v.get("pitch", 0.0).asDouble();
    p.yaw   = v.get("yaw",   0.0).asDouble();
    return p;
}

// ── Velocity ────────────────────────────────────────────

struct Velocity {
    double linear  = 0.0;
    double angular = 0.0;

    bool operator==(const Velocity& o) const {
        return linear == o.linear && angular == o.angular;
    }
    bool operator!=(const Velocity& o) const { return !(*this == o); }
};

inline Json::Value to_json(const Velocity& v) {
    Json::Value j;
    j["linear"]  = v.linear;
    j["angular"] = v.angular;
    return j;
}

inline Velocity velocity_from_json(const Json::Value& j) {
    Velocity v;
    v.linear  = j.get("linear",  0.0).asDouble();
    v.angular = j.get("angular", 0.0).asDouble();
    return v;
}

// ── BatteryState ────────────────────────────────────────

struct BatteryState {
    double percentage  = 100.0;
    double voltage     = 0.0;
    bool   charging    = false;
    double charge_rate = 0.0;

    bool operator==(const BatteryState& o) const {
        return percentage == o.percentage && voltage == o.voltage &&
               charging == o.charging && charge_rate == o.charge_rate;
    }
    bool operator!=(const BatteryState& o) const { return !(*this == o); }
};

inline Json::Value to_json(const BatteryState& b) {
    Json::Value v;
    v["percentage"]  = b.percentage;
    v["voltage"]     = b.voltage;
    v["charging"]    = b.charging;
    v["charge_rate"] = b.charge_rate;
    return v;
}

inline BatteryState battery_state_from_json(const Json::Value& v) {
    BatteryState b;
    b.percentage  = v.get("percentage",  100.0).asDouble();
    b.voltage     = v.get("voltage",     0.0).asDouble();
    b.charging    = v.get("charging",    false).asBool();
    b.charge_rate = v.get("charge_rate", 0.0).asDouble();
    return b;
}

// ── ObstacleReading ─────────────────────────────────────

struct ObstacleReading {
    bool   detected = false;
    double range    = 0.0;

    bool operator==(const ObstacleReading& o) const {
        return detected == o.detected && range == o.range;
    }
    bool operator!=(const ObstacleReading& o) const { return !(*this == o); }
};

inline Json::Value to_json(const ObstacleReading& r) {
    Json::Value v;
    v["detected"] = r.detected;
    v["range"]    = r.range;
    return v;
}

inline ObstacleReading obstacle_reading_from_json(const Json::Value& v) {
    ObstacleReading r;
    r.detected = v.get("detected", false).asBool();
    r.range    = v.get("range",    0.0).asDouble();
    return r;
}

// ── Enums ───────────────────────────────────────────────

enum class RobotType {
    DIFFERENTIAL_DRIVE,
    UNIDIRECTIONAL,
    OMNIDIRECTIONAL
};

inline std::string robot_type_to_string(RobotType t) {
    switch (t) {
        case RobotType::DIFFERENTIAL_DRIVE: return "differential_drive";
        case RobotType::UNIDIRECTIONAL:     return "unidirectional";
        case RobotType::OMNIDIRECTIONAL:    return "omnidirectional";
    }
    return "unknown";
}

inline RobotType robot_type_from_string(const std::string& s) {
    if (s == "differential_drive") return RobotType::DIFFERENTIAL_DRIVE;
    if (s == "unidirectional")     return RobotType::UNIDIRECTIONAL;
    if (s == "omnidirectional")    return RobotType::OMNIDIRECTIONAL;
    return RobotType::DIFFERENTIAL_DRIVE; // default
}

enum class RobotState {
    IDLE,
    MOVING,
    CHARGING,
    LOADING,
    UNLOADING,
    ERROR,
    OFFLINE,
    DOCKING
};

inline std::string robot_state_to_string(RobotState s) {
    switch (s) {
        case RobotState::IDLE:      return "IDLE";
        case RobotState::MOVING:    return "MOVING";
        case RobotState::CHARGING:  return "CHARGING";
        case RobotState::LOADING:   return "LOADING";
        case RobotState::UNLOADING: return "UNLOADING";
        case RobotState::ERROR:     return "ERROR";
        case RobotState::OFFLINE:   return "OFFLINE";
        case RobotState::DOCKING:   return "DOCKING";
    }
    return "UNKNOWN";
}

enum class TaskState {
    NOT_ASSIGNED,
    ACCEPTED,
    ASSIGNED,
    IN_PROGRESS,
    COMPLETED,
    FAILED,
    CANCELLED
};

inline std::string task_state_to_string(TaskState s) {
    switch (s) {
        case TaskState::NOT_ASSIGNED: return "NOT_ASSIGNED";
        case TaskState::ACCEPTED:     return "ACCEPTED";
        case TaskState::ASSIGNED:     return "ASSIGNED";
        case TaskState::IN_PROGRESS:  return "IN_PROGRESS";
        case TaskState::COMPLETED:    return "COMPLETED";
        case TaskState::FAILED:       return "FAILED";
        case TaskState::CANCELLED:    return "CANCELLED";
    }
    return "UNKNOWN";
}

enum class TaskType {
    MOVE,
    PICK,
    PLACE,
    CHARGE,
    PARK
};

inline std::string task_type_to_string(TaskType t) {
    switch (t) {
        case TaskType::MOVE:   return "MOVE";
        case TaskType::PICK:   return "PICK";
        case TaskType::PLACE:  return "PLACE";
        case TaskType::CHARGE: return "CHARGE";
        case TaskType::PARK:   return "PARK";
    }
    return "UNKNOWN";
}

// ── MapNode ─────────────────────────────────────────────

struct MapNode {
    std::string name;
    double x    = 0.0;
    double y    = 0.0;
    std::string type;

    bool operator==(const MapNode& o) const {
        return name == o.name && x == o.x && y == o.y && type == o.type;
    }
    bool operator!=(const MapNode& o) const { return !(*this == o); }
};

inline Json::Value to_json(const MapNode& n) {
    Json::Value v;
    v["name"] = n.name;
    v["x"]    = n.x;
    v["y"]    = n.y;
    v["type"] = n.type;
    return v;
}

inline MapNode map_node_from_json(const Json::Value& v) {
    MapNode n;
    n.name = v.get("name", "").asString();
    n.x    = v.get("x",    0.0).asDouble();
    n.y    = v.get("y",    0.0).asDouble();
    n.type = v.get("type", "").asString();
    return n;
}

// ── MapEdge ─────────────────────────────────────────────

struct MapEdge {
    std::string from;
    std::string to;
    bool bidirectional = true;  // default: bidirectional

    bool operator==(const MapEdge& o) const {
        return from == o.from && to == o.to &&
               bidirectional == o.bidirectional;
    }
    bool operator!=(const MapEdge& o) const { return !(*this == o); }
};

inline Json::Value to_json(const MapEdge& e) {
    Json::Value v;
    v["from"]          = e.from;
    v["to"]            = e.to;
    v["bidirectional"] = e.bidirectional;
    return v;
}

inline MapEdge map_edge_from_json(const Json::Value& v) {
    MapEdge e;
    e.from          = v.get("from", "").asString();
    e.to            = v.get("to",   "").asString();
    e.bidirectional = v.get("bidirectional", true).asBool();
    return e;
}

} // namespace rdt

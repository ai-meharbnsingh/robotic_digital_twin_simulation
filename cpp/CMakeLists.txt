# ──────────────────────────────────────────────────────────
# cpp/CMakeLists.txt — C++ build for robotic_digital_twin
# ──────────────────────────────────────────────────────────

# ── Find vcpkg-managed packages ──
find_package(spdlog CONFIG REQUIRED)
find_package(fmt CONFIG REQUIRED)
find_package(GTest CONFIG REQUIRED)
find_package(Eigen3 CONFIG REQUIRED)
find_package(tinyxml2 CONFIG REQUIRED)
find_package(jsoncpp CONFIG REQUIRED)
find_package(yaml-cpp CONFIG REQUIRED)

# osqp may install as osqp or OSQP depending on vcpkg version
find_package(osqp CONFIG REQUIRED)

# ── NOTE: BehaviorTree.CPP v4.6.2 FetchContent removed ──
# BTCPP has a compile error (lexy typo) in v4.6.2.
# We use a lightweight custom BT engine instead (src/behavior/).
# It parses the same BTCPP v4 XML format using tinyxml2.

# ── rdt_core static library (Logger, Timer, Config, Types, Navigation, Robot, Behavior, Network) ──
add_library(rdt_core STATIC
    src/core/Logger.cpp
    src/core/Timer.cpp
    src/core/Config.cpp
    src/navigation/GraphMap.cpp
    src/navigation/AStar.cpp
    src/navigation/QuadTree.cpp
    src/navigation/NodeReservation.cpp
    src/robot/RobotState.cpp
    src/robot/MotionController.cpp
    src/robot/BatteryModel.cpp
    src/robot/ObstacleHandler.cpp
    src/behavior/BTEngine.cpp
    src/behavior/ActionNodes.cpp
    src/behavior/ConditionNodes.cpp
    src/network/ProtocolV1.cpp
    src/network/TCPServer.cpp
    src/network/RESTServer.cpp
    src/fleet/TaskManager.cpp
    src/fleet/COPPController.cpp
    src/fleet/FleetManager.cpp
)
target_include_directories(rdt_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_compile_options(rdt_core PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(rdt_core PUBLIC
    spdlog::spdlog
    fmt::fmt
    JsonCpp::JsonCpp
    yaml-cpp::yaml-cpp
    tinyxml2::tinyxml2
)

# ── FMS Server executable ──
add_executable(fms_server
    src/apps/fms_server.cpp
)
target_include_directories(fms_server PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_link_libraries(fms_server PRIVATE
    rdt_core
)

# ── Tests ──
enable_testing()
add_subdirectory(tests)

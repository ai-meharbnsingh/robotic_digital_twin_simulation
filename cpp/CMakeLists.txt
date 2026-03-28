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

# ── BehaviorTree.CPP v4 via FetchContent ──
include(FetchContent)
FetchContent_Declare(
    behaviortree_cpp
    GIT_REPOSITORY https://github.com/BehaviorTree/BehaviorTree.CPP.git
    GIT_TAG        4.6.2
)
# Disable BT tests/examples to speed up build
set(BTCPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(BTCPP_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BTCPP_UNIT_TESTS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(behaviortree_cpp)

# ── rdt_core static library (Logger, Timer, Config + Types) ──
add_library(rdt_core STATIC
    src/core/Logger.cpp
    src/core/Timer.cpp
    src/core/Config.cpp
)
target_include_directories(rdt_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_link_libraries(rdt_core PUBLIC
    spdlog::spdlog
    fmt::fmt
    JsonCpp::JsonCpp
    yaml-cpp::yaml-cpp
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

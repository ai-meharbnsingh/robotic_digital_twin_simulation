# ──────────────────────────────────────────────────────────
# cpp/tests/CMakeLists.txt — GTest test runner
# ──────────────────────────────────────────────────────────

add_executable(rdt_tests
    test_hello.cpp
    test_logger.cpp
    test_timer.cpp
    test_types.cpp
    test_config.cpp
    test_reservation.cpp
    test_graph.cpp
    test_astar.cpp
    test_quadtree.cpp
    test_robot_state.cpp
    test_motion.cpp
    test_battery.cpp
    test_obstacle.cpp
    test_bt.cpp
    test_protocol.cpp
    test_tcp.cpp
    test_rest.cpp
    test_fleet.cpp
)
target_include_directories(rdt_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
)
target_link_libraries(rdt_tests PRIVATE
    rdt_core
    GTest::gtest
    GTest::gtest_main
)

# Pass project root so tests can find config files at runtime
target_compile_definitions(rdt_tests PRIVATE
    RDT_PROJECT_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)

include(GoogleTest)
gtest_discover_tests(rdt_tests)

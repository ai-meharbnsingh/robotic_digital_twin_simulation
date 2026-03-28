# ──────────────────────────────────────────────────────────
# cpp/tests/CMakeLists.txt — GTest test runner
# ──────────────────────────────────────────────────────────

add_executable(rdt_tests
    test_hello.cpp
)
target_include_directories(rdt_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
)
target_link_libraries(rdt_tests PRIVATE
    GTest::gtest
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(rdt_tests)

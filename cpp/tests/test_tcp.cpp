// ──────────────────────────────────────────────────────────
// test_tcp.cpp — TCPServer basic lifecycle tests
//
// Phase 6: Basic tests for start/stop/count.
// Full integration (connect, send, receive) tested in Phase 7.
//
// PORT REQUIREMENT: These tests bind to ephemeral OS-assigned ports
// via find_free_port(). In sandboxed or containerized environments
// where socket creation or port binding is restricted, these tests
// may fail. The production FMS uses port 65123 by default (configured
// via FMS_TCP_PORT env var).
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/network/TCPServer.h"

#include <thread>
#include <chrono>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <atomic>

using namespace rdt::network;

// ── Helper: find an available port ───────────────────────

static uint16_t find_free_port() {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = 0;  // OS picks a free port
    ::bind(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
    socklen_t len = sizeof(addr);
    ::getsockname(fd, reinterpret_cast<struct sockaddr*>(&addr), &len);
    uint16_t port = ntohs(addr.sin_port);
    ::close(fd);
    return port;
}

// ── Test: Server starts and is running ───────────────────

TEST(TCPServer, StartsAndIsRunning) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);

    // Give the acceptor thread time to bind
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_TRUE(server.isRunning());
    EXPECT_EQ(server.getPort(), port);

    server.stop();
}

// ── Test: Server stops cleanly ───────────────────────────

TEST(TCPServer, StopsCleanly) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    server.stop();

    EXPECT_FALSE(server.isRunning());
}

// ── Test: Connected count is 0 initially ─────────────────

TEST(TCPServer, ConnectedCountZeroInitially) {
    TCPServer server;
    EXPECT_EQ(server.getConnectedCount(), 0u);
}

// ── Test: Connected count is 0 after start (no clients) ──

TEST(TCPServer, ConnectedCountZeroAfterStart) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_EQ(server.getConnectedCount(), 0u);

    server.stop();
}

// ── Test: Can start on a specific port ───────────────────

TEST(TCPServer, StartsOnSpecificPort) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_EQ(server.getPort(), port);
    EXPECT_TRUE(server.isRunning());

    server.stop();
}

// ── Test: Double stop is safe ────────────────────────────

TEST(TCPServer, DoubleStopSafe) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    server.stop();
    // Second stop should not crash
    server.stop();

    EXPECT_FALSE(server.isRunning());
}

// ── Test: sendToRobot returns false for unknown robot ────

TEST(TCPServer, SendToUnknownRobotReturnsFalse) {
    TCPServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    bool result = server.sendToRobot("nonexistent_robot", "hello");
    EXPECT_FALSE(result);

    server.stop();
}

// ── Test: Callback can be registered ─────────────────────

TEST(TCPServer, CallbackRegistration) {
    TCPServer server;
    std::atomic<int> call_count{0};

    server.onMessage([&call_count](const std::string& /*id*/, const std::string& /*msg*/) {
        call_count++;
    });

    // Just verify registration doesn't crash
    EXPECT_EQ(call_count.load(), 0);
}

// ── Test: Client connects and server counts it ───────────

TEST(TCPServer, ClientConnectsAndIsCounted) {
    TCPServer server;
    std::atomic<bool> got_message{false};

    server.onMessage([&got_message](const std::string& /*id*/, const std::string& /*msg*/) {
        got_message = true;
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Connect a client
    int client_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_GE(client_fd, 0);

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    int conn_result = ::connect(client_fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
    ASSERT_EQ(conn_result, 0);

    // Send a protocol-like message so the server registers the robot
    std::string msg = "1719500000.0|test_robot|1.0|2.0|0.0|IDLE|100.0|24.0|0|0.0|0.0|0|0.0|0|0|0|t1|IDLE|0|0.0|0.0|0.0|0.0|0.0|NONE|0.0|0.0|20.0|-50|100|v1|1|999\n";
    ::send(client_fd, msg.data(), msg.size(), 0);

    // Wait for the server to process
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    EXPECT_EQ(server.getConnectedCount(), 1u);
    EXPECT_TRUE(got_message.load());

    ::close(client_fd);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    server.stop();
}

// ── Test: Destructor stops cleanly ───────────────────────

TEST(TCPServer, DestructorStopsCleanly) {
    uint16_t port = find_free_port();
    {
        TCPServer server;
        server.start(port);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        // Destructor should handle cleanup
    }
    // If we get here without hanging, the destructor worked
    SUCCEED();
}

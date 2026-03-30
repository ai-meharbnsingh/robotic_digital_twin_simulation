// ──────────────────────────────────────────────────────────
// test_rest.cpp — RESTServer basic tests
//
// Phase 6: Tests for route registration, start/stop,
// and actual HTTP GET requests.
//
// PORT REQUIREMENT: These tests bind to ephemeral OS-assigned ports
// via find_free_port(). In sandboxed or containerized environments
// where socket creation or port binding is restricted, these tests
// may fail. The production FMS REST server uses port 7012 by default
// (configured via FMS_PORT env var).
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/network/RESTServer.h"

#include <thread>
#include <chrono>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <string>

using namespace rdt::network;

// ── Helper: find an available port ───────────────────────

static uint16_t find_free_port() {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = 0;
    ::bind(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
    socklen_t len = sizeof(addr);
    ::getsockname(fd, reinterpret_cast<struct sockaddr*>(&addr), &len);
    uint16_t port = ntohs(addr.sin_port);
    ::close(fd);
    return port;
}

// ── Helper: send an HTTP GET request and read response ───

static std::string http_get(uint16_t port, const std::string& path) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return "";

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    if (::connect(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        return "";
    }

    std::string request = "GET " + path + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
    ::send(fd, request.data(), request.size(), 0);

    std::string response;
    char buf[4096];
    ssize_t n;
    while ((n = ::recv(fd, buf, sizeof(buf) - 1, 0)) > 0) {
        buf[n] = '\0';
        response += buf;
    }

    ::close(fd);
    return response;
}

// ── Helper: extract HTTP body from response ──────────────

static std::string extract_body(const std::string& response) {
    auto pos = response.find("\r\n\r\n");
    if (pos == std::string::npos) return "";
    return response.substr(pos + 4);
}

// ── Helper: extract HTTP status code ─────────────────────

static int extract_status_code(const std::string& response) {
    // "HTTP/1.1 200 OK\r\n..."
    auto pos = response.find(' ');
    if (pos == std::string::npos) return 0;
    return std::stoi(response.substr(pos + 1, 3));
}

// ── Test: Server starts and stops cleanly ────────────────

TEST(RESTServer, StartsAndStopsCleanly) {
    RESTServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_TRUE(server.isRunning());
    EXPECT_EQ(server.getPort(), port);

    server.stop();
    EXPECT_FALSE(server.isRunning());
}

// ── Test: Route count starts at 0 ───────────────────────

TEST(RESTServer, RouteCountStartsAtZero) {
    RESTServer server;
    EXPECT_EQ(server.getRouteCount(), 0u);
}

// ── Test: Adding routes increments count ─────────────────

TEST(RESTServer, AddRouteIncrementsCount) {
    RESTServer server;
    server.addRoute("GET", "/health", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", R"({"status":"ok"})"};
    });
    EXPECT_EQ(server.getRouteCount(), 1u);

    server.addRoute("GET", "/api/robots", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", "[]"};
    });
    EXPECT_EQ(server.getRouteCount(), 2u);
}

// ── Test: GET /health returns 200 and JSON body ──────────

TEST(RESTServer, HealthEndpointReturns200) {
    RESTServer server;
    server.addRoute("GET", "/health", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", R"({"status":"ok","service":"fms"})"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/health");
    ASSERT_FALSE(response.empty());

    EXPECT_EQ(extract_status_code(response), 200);
    std::string body = extract_body(response);
    EXPECT_NE(body.find("ok"), std::string::npos);
    EXPECT_NE(body.find("fms"), std::string::npos);

    server.stop();
}

// ── Test: GET /api/fleet/status returns fleet JSON ───────

TEST(RESTServer, FleetStatusEndpoint) {
    RESTServer server;
    server.addRoute("GET", "/api/fleet/status", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json",
            R"({"robot_count":3,"active":2,"idle":1})"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/api/fleet/status");
    ASSERT_FALSE(response.empty());

    EXPECT_EQ(extract_status_code(response), 200);
    std::string body = extract_body(response);
    EXPECT_NE(body.find("robot_count"), std::string::npos);
    EXPECT_NE(body.find("3"), std::string::npos);

    server.stop();
}

// ── Test: GET /api/robots returns robot list JSON ────────

TEST(RESTServer, RobotsEndpoint) {
    RESTServer server;
    server.addRoute("GET", "/api/robots", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json",
            R"([{"id":"robot_01","state":"IDLE"},{"id":"robot_02","state":"MOVING"}])"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/api/robots");
    ASSERT_FALSE(response.empty());

    EXPECT_EQ(extract_status_code(response), 200);
    std::string body = extract_body(response);
    EXPECT_NE(body.find("robot_01"), std::string::npos);
    EXPECT_NE(body.find("robot_02"), std::string::npos);

    server.stop();
}

// ── Test: Unknown route returns 404 ──────────────────────

TEST(RESTServer, UnknownRouteReturns404) {
    RESTServer server;
    server.addRoute("GET", "/health", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", R"({"status":"ok"})"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/nonexistent");
    ASSERT_FALSE(response.empty());
    EXPECT_EQ(extract_status_code(response), 404);

    server.stop();
}

// ── Test: Response contains Content-Type header ──────────

TEST(RESTServer, ResponseContainsContentType) {
    RESTServer server;
    server.addRoute("GET", "/health", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", "{}"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/health");
    EXPECT_NE(response.find("Content-Type: application/json"), std::string::npos);

    server.stop();
}

// ── Test: Response contains Content-Length header ────────

TEST(RESTServer, ResponseContainsContentLength) {
    RESTServer server;
    std::string body_str = R"({"status":"ok"})";
    server.addRoute("GET", "/health", [body_str](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", body_str};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/health");
    std::string expected = "Content-Length: " + std::to_string(body_str.size());
    EXPECT_NE(response.find(expected), std::string::npos);

    server.stop();
}

// ── Test: Double stop is safe ────────────────────────────

TEST(RESTServer, DoubleStopSafe) {
    RESTServer server;
    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    server.stop();
    server.stop();  // Should not crash
    EXPECT_FALSE(server.isRunning());
}

// ── Test: Destructor stops cleanly ───────────────────────

TEST(RESTServer, DestructorStopsCleanly) {
    uint16_t port = find_free_port();
    {
        RESTServer server;
        server.addRoute("GET", "/health", [](const HTTPRequest&) {
            return HTTPResponse{200, "OK", "application/json", "{}"};
        });
        server.start(port);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    SUCCEED();
}

// ── Test: CORS header present ────────────────────────────

TEST(RESTServer, CORSHeaderPresent) {
    RESTServer server;
    server.addRoute("GET", "/health", [](const HTTPRequest&) {
        return HTTPResponse{200, "OK", "application/json", "{}"};
    });

    uint16_t port = find_free_port();
    server.start(port);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    std::string response = http_get(port, "/health");
    EXPECT_NE(response.find("Access-Control-Allow-Origin: *"), std::string::npos);

    server.stop();
}

#pragma once

// ──────────────────────────────────────────────────────────
// rdt/network/RESTServer.h — Minimal HTTP/1.1 GET server
//
// Phase 6: Uses POSIX sockets. Handles GET requests only.
// Serves JSON responses for fleet status, robot list, health.
//
// Routes:
//   GET /api/fleet/status  — fleet overview JSON
//   GET /api/robots        — robot list JSON
//   GET /health            — service health JSON
// ──────────────────────────────────────────────────────────

#include <string>
#include <functional>
#include <unordered_map>
#include <mutex>
#include <thread>
#include <atomic>
#include <cstdint>

namespace rdt {
namespace network {

/// HTTP request (parsed from raw).
struct HTTPRequest {
    std::string method;   // "GET", "POST", etc.
    std::string path;     // "/api/fleet/status"
    std::string version;  // "HTTP/1.1"
    std::unordered_map<std::string, std::string> headers;
    std::string body;
};

/// HTTP response built by a route handler.
struct HTTPResponse {
    int         status_code = 200;
    std::string status_text = "OK";
    std::string content_type = "application/json";
    std::string body;
};

/// Route handler: takes a request, returns a response.
using RouteHandler = std::function<HTTPResponse(const HTTPRequest& req)>;

/// @brief Minimal HTTP server for REST endpoints.
///
/// Usage:
///   RESTServer rest;
///   rest.addRoute("GET", "/health", [](auto& req) {
///       return HTTPResponse{200, "OK", "application/json", R"({"status":"ok"})"};
///   });
///   rest.start(7012);
///   // ... serve until shutdown ...
///   rest.stop();
class RESTServer {
public:
    RESTServer();
    ~RESTServer();

    // Non-copyable.
    RESTServer(const RESTServer&) = delete;
    RESTServer& operator=(const RESTServer&) = delete;

    /// Register a route handler for a given method + path.
    void addRoute(const std::string& method, const std::string& path,
                  RouteHandler handler);

    /// Start listening on the given port.
    /// Spawns an acceptor thread. Non-blocking after return.
    void start(uint16_t port);

    /// Stop the server and close all connections.
    void stop();

    /// Whether the server is currently running.
    bool isRunning() const;

    /// Get the port the server is listening on.
    uint16_t getPort() const;

    /// Get the number of registered routes.
    size_t getRouteCount() const;

private:
    /// Acceptor loop — runs in its own thread.
    void acceptLoop(uint16_t port);

    /// Handle a single HTTP request on a connected socket.
    void handleClient(int client_fd);

    /// Parse raw HTTP request bytes into an HTTPRequest.
    static HTTPRequest parseRequest(const std::string& raw);

    /// Serialize an HTTPResponse into raw HTTP response bytes.
    static std::string serializeResponse(const HTTPResponse& resp);

    // Route table: "METHOD /path" → handler
    std::mutex                                    routes_mutex_;
    std::unordered_map<std::string, RouteHandler> routes_;

    std::atomic<bool>     running_{false};
    std::atomic<uint16_t> port_{0};
    int                   listen_fd_{-1};
    std::thread           accept_thread_;
};

}  // namespace network
}  // namespace rdt

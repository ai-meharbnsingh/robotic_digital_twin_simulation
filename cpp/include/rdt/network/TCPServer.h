#pragma once

// ──────────────────────────────────────────────────────────
// rdt/network/TCPServer.h — Synchronous TCP server for
//                            robot↔FMS communication.
//
// Phase 6: Simple synchronous implementation using ASIO.
// Phase 7+: May be upgraded to fully async accept/read.
//
// The server listens on a given port. Each accepted connection
// is handled in its own thread. Incoming data is framed by
// newline ('\n'). Complete lines are dispatched to the
// registered onMessage callback.
// ──────────────────────────────────────────────────────────

#include <string>
#include <functional>
#include <unordered_map>
#include <mutex>
#include <thread>
#include <atomic>
#include <vector>
#include <cstdint>

namespace rdt {
namespace network {

/// Callback signature for incoming messages.
/// Parameters: robot_id (from message or connection), raw message string.
using MessageCallback = std::function<void(const std::string& robot_id,
                                           const std::string& message)>;

/// @brief Synchronous TCP server for robot fleet communication.
///
/// Usage:
///   TCPServer server;
///   server.onMessage([](auto& id, auto& msg) { ... });
///   server.start(7010);
///   // ... run fleet management loop ...
///   server.stop();
class TCPServer {
public:
    TCPServer();
    ~TCPServer();

    // Non-copyable, non-movable.
    TCPServer(const TCPServer&) = delete;
    TCPServer& operator=(const TCPServer&) = delete;

    /// Register a callback for incoming messages.
    /// Must be called before start().
    void onMessage(MessageCallback callback);

    /// Start listening on the specified port.
    /// Spawns an acceptor thread. Non-blocking after return.
    /// @param port  TCP port to bind to (e.g. 7010).
    void start(uint16_t port);

    /// Stop the server. Closes all connections and joins threads.
    void stop();

    /// Send a raw message to a specific robot by its connection ID.
    /// @return true if the robot was found and the send succeeded.
    bool sendToRobot(const std::string& robot_id, const std::string& message);

    /// Number of currently connected clients.
    size_t getConnectedCount() const;

    /// Whether the server is currently running.
    bool isRunning() const;

    /// Get the port the server is listening on.
    uint16_t getPort() const;

private:
    /// Acceptor loop — runs in its own thread.
    void acceptLoop(uint16_t port);

    /// Per-client read loop — runs in a worker thread.
    void clientLoop(int client_fd, const std::string& client_addr);

    MessageCallback              callback_;
    std::atomic<bool>            running_{false};
    std::atomic<uint16_t>        port_{0};
    int                          listen_fd_{-1};

    std::thread                  accept_thread_;

    // Connected clients: robot_id → file descriptor
    mutable std::mutex           clients_mutex_;
    std::unordered_map<std::string, int> clients_;

    // Worker threads for each client connection
    mutable std::mutex           workers_mutex_;
    std::vector<std::thread>     worker_threads_;
};

}  // namespace network
}  // namespace rdt

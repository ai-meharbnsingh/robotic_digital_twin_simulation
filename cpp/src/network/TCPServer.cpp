// ──────────────────────────────────────────────────────────
// rdt/network/TCPServer.cpp — Synchronous TCP server (POSIX)
//
// Uses plain POSIX sockets for Phase 6 simplicity.
// Async ASIO upgrade planned for Phase 7.
// ──────────────────────────────────────────────────────────

#include "rdt/network/TCPServer.h"
#include "rdt/core/Logger.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstring>
#include <sstream>

namespace rdt {
namespace network {

TCPServer::TCPServer() = default;

TCPServer::~TCPServer() {
    if (running_.load()) {
        stop();
    }
}

void TCPServer::onMessage(MessageCallback callback) {
    callback_ = std::move(callback);
}

void TCPServer::start(uint16_t port) {
    if (running_.load()) {
        RDT_LOG_WARN("TCPServer already running on port {}", port_.load());
        return;
    }

    port_ = port;
    running_ = true;
    accept_thread_ = std::thread(&TCPServer::acceptLoop, this, port);
}

void TCPServer::stop() {
    if (!running_.load()) return;
    running_ = false;

    // On macOS, shutdown() on a listening socket may not unblock accept().
    // We connect to ourselves to force accept() to return, then close.
    uint16_t p = port_.load();
    if (listen_fd_ >= 0 && p > 0) {
        int wake_fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (wake_fd >= 0) {
            struct sockaddr_in addr{};
            addr.sin_family = AF_INET;
            addr.sin_port = htons(p);
            addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            ::connect(wake_fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
            ::close(wake_fd);
        }
    }
    if (listen_fd_ >= 0) {
        ::shutdown(listen_fd_, SHUT_RDWR);
        ::close(listen_fd_);
        listen_fd_ = -1;
    }

    // Close all client sockets
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        for (auto& [id, fd] : clients_) {
            ::shutdown(fd, SHUT_RDWR);
            ::close(fd);
        }
        clients_.clear();
    }

    // Join acceptor thread
    if (accept_thread_.joinable()) {
        accept_thread_.join();
    }

    // Join all worker threads
    {
        std::lock_guard<std::mutex> lock(workers_mutex_);
        for (auto& t : worker_threads_) {
            if (t.joinable()) {
                t.join();
            }
        }
        worker_threads_.clear();
    }

    RDT_LOG_INFO("TCPServer stopped");
}

bool TCPServer::sendToRobot(const std::string& robot_id, const std::string& message) {
    std::lock_guard<std::mutex> lock(clients_mutex_);
    auto it = clients_.find(robot_id);
    if (it == clients_.end()) {
        return false;
    }

    std::string framed = message + "\n";
    ssize_t sent = ::send(it->second, framed.data(), framed.size(), 0);
    return sent == static_cast<ssize_t>(framed.size());
}

size_t TCPServer::getConnectedCount() const {
    std::lock_guard<std::mutex> lock(clients_mutex_);
    return clients_.size();
}

bool TCPServer::isRunning() const {
    return running_.load();
}

uint16_t TCPServer::getPort() const {
    return port_.load();
}

// ── Accept loop ──────────────────────────────────────────

void TCPServer::acceptLoop(uint16_t port) {
    listen_fd_ = ::socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd_ < 0) {
        RDT_LOG_ERROR("TCPServer: socket() failed: {}", strerror(errno));
        running_ = false;
        return;
    }

    // Allow port reuse
    int opt = 1;
    ::setsockopt(listen_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(port);

    if (::bind(listen_fd_, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        RDT_LOG_ERROR("TCPServer: bind() failed on port {}: {}", port, strerror(errno));
        ::close(listen_fd_);
        listen_fd_ = -1;
        running_ = false;
        return;
    }

    if (::listen(listen_fd_, 32) < 0) {
        RDT_LOG_ERROR("TCPServer: listen() failed: {}", strerror(errno));
        ::close(listen_fd_);
        listen_fd_ = -1;
        running_ = false;
        return;
    }

    RDT_LOG_INFO("TCPServer listening on port {}", port);

    while (running_.load()) {
        struct sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);
        int client_fd = ::accept(listen_fd_,
                                 reinterpret_cast<struct sockaddr*>(&client_addr),
                                 &client_len);

        if (client_fd < 0) {
            if (!running_.load()) break;  // Server shutting down
            RDT_LOG_WARN("TCPServer: accept() failed: {}", strerror(errno));
            continue;
        }

        std::string addr_str = inet_ntoa(client_addr.sin_addr);
        addr_str += ":" + std::to_string(ntohs(client_addr.sin_port));

        RDT_LOG_INFO("TCPServer: new connection from {}", addr_str);

        // Spawn a worker thread for this client
        {
            std::lock_guard<std::mutex> lock(workers_mutex_);
            worker_threads_.emplace_back(&TCPServer::clientLoop, this, client_fd, addr_str);
        }
    }
}

// ── Per-client read loop ─────────────────────────────────

void TCPServer::clientLoop(int client_fd, const std::string& client_addr) {
    // Temporary connection ID until we get a robot_id from the first message
    std::string conn_id = client_addr;
    bool registered = false;

    std::string buffer;
    char chunk[4096];

    while (running_.load()) {
        ssize_t n = ::recv(client_fd, chunk, sizeof(chunk), 0);
        if (n <= 0) {
            // Connection closed or error
            break;
        }

        buffer.append(chunk, static_cast<size_t>(n));

        // Process complete newline-delimited messages
        size_t pos;
        while ((pos = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, pos);
            buffer.erase(0, pos + 1);

            if (line.empty()) continue;

            // Extract robot_id from field 1 (pipe-delimited)
            // to register the connection under the robot's name.
            if (!registered) {
                auto first_pipe = line.find('|');
                if (first_pipe != std::string::npos) {
                    auto second_pipe = line.find('|', first_pipe + 1);
                    if (second_pipe != std::string::npos) {
                        std::string robot_id = line.substr(first_pipe + 1,
                                                           second_pipe - first_pipe - 1);
                        if (!robot_id.empty()) {
                            conn_id = robot_id;
                            std::lock_guard<std::mutex> lock(clients_mutex_);
                            clients_[conn_id] = client_fd;
                            registered = true;
                            RDT_LOG_INFO("TCPServer: registered robot '{}'", conn_id);
                        }
                    }
                }
            }

            // Dispatch to callback
            if (callback_) {
                callback_(conn_id, line);
            }
        }
    }

    // Cleanup
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        clients_.erase(conn_id);
    }
    ::close(client_fd);
    RDT_LOG_INFO("TCPServer: connection closed for '{}'", conn_id);
}

}  // namespace network
}  // namespace rdt

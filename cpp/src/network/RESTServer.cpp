// ──────────────────────────────────────────────────────────
// rdt/network/RESTServer.cpp — Minimal HTTP/1.1 GET server
//
// Phase 6: POSIX sockets, synchronous accept, per-request
// thread. Supports GET only. Returns JSON.
// ──────────────────────────────────────────────────────────

#include "rdt/network/RESTServer.h"
#include "rdt/core/Logger.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <sstream>
#include <algorithm>

namespace rdt {
namespace network {

RESTServer::RESTServer() = default;

RESTServer::~RESTServer() {
    if (running_.load()) {
        stop();
    }
}

void RESTServer::addRoute(const std::string& method, const std::string& path,
                           RouteHandler handler) {
    std::string key = method + " " + path;
    std::lock_guard<std::mutex> lock(routes_mutex_);
    routes_[key] = std::move(handler);
}

void RESTServer::start(uint16_t port) {
    if (running_.load()) {
        RDT_LOG_WARN("RESTServer already running on port {}", port_.load());
        return;
    }

    port_ = port;
    running_ = true;
    accept_thread_ = std::thread(&RESTServer::acceptLoop, this, port);
}

void RESTServer::stop() {
    if (!running_.load()) return;
    running_ = false;

    // On macOS, shutdown() on a listening socket may not unblock accept().
    // Connect to ourselves to force accept() to return.
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

    if (accept_thread_.joinable()) {
        accept_thread_.join();
    }

    RDT_LOG_INFO("RESTServer stopped");
}

bool RESTServer::isRunning() const {
    return running_.load();
}

uint16_t RESTServer::getPort() const {
    return port_.load();
}

size_t RESTServer::getRouteCount() const {
    std::lock_guard<std::mutex> lock(const_cast<std::mutex&>(routes_mutex_));
    return routes_.size();
}

// ── Accept loop ──────────────────────────────────────────

void RESTServer::acceptLoop(uint16_t port) {
    listen_fd_ = ::socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd_ < 0) {
        RDT_LOG_ERROR("RESTServer: socket() failed: {}", strerror(errno));
        running_ = false;
        return;
    }

    int opt = 1;
    ::setsockopt(listen_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(port);

    if (::bind(listen_fd_, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        RDT_LOG_ERROR("RESTServer: bind() failed on port {}: {}", port, strerror(errno));
        ::close(listen_fd_);
        listen_fd_ = -1;
        running_ = false;
        return;
    }

    if (::listen(listen_fd_, 64) < 0) {
        RDT_LOG_ERROR("RESTServer: listen() failed: {}", strerror(errno));
        ::close(listen_fd_);
        listen_fd_ = -1;
        running_ = false;
        return;
    }

    RDT_LOG_INFO("RESTServer listening on port {}", port);

    while (running_.load()) {
        struct sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);
        int client_fd = ::accept(listen_fd_,
                                 reinterpret_cast<struct sockaddr*>(&client_addr),
                                 &client_len);

        if (client_fd < 0) {
            if (!running_.load()) break;
            continue;
        }

        // Handle each HTTP request synchronously then close.
        // For Phase 6, no persistent connections.
        handleClient(client_fd);
    }
}

// ── Request handling ─────────────────────────────────────

void RESTServer::handleClient(int client_fd) {
    // Read the full request (up to 8KB — sufficient for GET requests)
    char buf[8192];
    ssize_t n = ::recv(client_fd, buf, sizeof(buf) - 1, 0);
    if (n <= 0) {
        ::close(client_fd);
        return;
    }
    buf[n] = '\0';

    std::string raw(buf, static_cast<size_t>(n));
    HTTPRequest req = parseRequest(raw);

    // Look up route
    std::string key = req.method + " " + req.path;
    RouteHandler handler;
    {
        std::lock_guard<std::mutex> lock(routes_mutex_);
        auto it = routes_.find(key);
        if (it != routes_.end()) {
            handler = it->second;
        }
    }

    HTTPResponse resp;
    if (handler) {
        resp = handler(req);
    } else {
        resp.status_code = 404;
        resp.status_text = "Not Found";
        resp.body = R"({"error":"not_found","message":"No route for )" + key + R"("})";
    }

    std::string response_str = serializeResponse(resp);
    ::send(client_fd, response_str.data(), response_str.size(), 0);
    ::close(client_fd);
}

// ── HTTP parsing ─────────────────────────────────────────

HTTPRequest RESTServer::parseRequest(const std::string& raw) {
    HTTPRequest req;
    std::istringstream stream(raw);

    // Request line: "GET /path HTTP/1.1"
    std::string request_line;
    if (!std::getline(stream, request_line)) return req;

    // Strip trailing \r
    if (!request_line.empty() && request_line.back() == '\r') {
        request_line.pop_back();
    }

    std::istringstream rl(request_line);
    rl >> req.method >> req.path >> req.version;

    // Strip query string from path
    auto qpos = req.path.find('?');
    if (qpos != std::string::npos) {
        req.path = req.path.substr(0, qpos);
    }

    // Headers
    std::string header_line;
    while (std::getline(stream, header_line)) {
        if (!header_line.empty() && header_line.back() == '\r') {
            header_line.pop_back();
        }
        if (header_line.empty()) break;  // End of headers

        auto colon = header_line.find(':');
        if (colon != std::string::npos) {
            std::string name = header_line.substr(0, colon);
            std::string value = header_line.substr(colon + 1);
            // Trim leading whitespace from value
            auto start = value.find_first_not_of(' ');
            if (start != std::string::npos) {
                value = value.substr(start);
            }
            req.headers[name] = value;
        }
    }

    // Body (remaining)
    std::ostringstream body;
    body << stream.rdbuf();
    req.body = body.str();

    return req;
}

std::string RESTServer::serializeResponse(const HTTPResponse& resp) {
    std::ostringstream oss;
    oss << "HTTP/1.1 " << resp.status_code << " " << resp.status_text << "\r\n";
    oss << "Content-Type: " << resp.content_type << "\r\n";
    oss << "Content-Length: " << resp.body.size() << "\r\n";
    oss << "Connection: close\r\n";
    oss << "Access-Control-Allow-Origin: *\r\n";
    oss << "\r\n";
    oss << resp.body;
    return oss.str();
}

}  // namespace network
}  // namespace rdt

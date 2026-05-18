// ChainGuard-Core — Boost.Beast WebSocket client
//
// Phase 2.2. Synchronous WebSocket reader using Boost.Asio + Boost.Beast.
// One thread per client; the read loop calls the supplied callback for each
// text frame and exits cleanly when stop() is signalled or the peer closes.
//
// Both ws:// and wss:// are supported. TLS is wired through OpenSSL via
// Beast's stream<ssl::stream<tcp::socket>>.

#pragma once

#include <atomic>
#include <cstddef>
#include <functional>
#include <string>
#include <string_view>

namespace chainguard {

// WebSocket URL parts. Parsed from a `[ws|wss]://host[:port]/path` string.
struct WsTarget {
    bool tls = false;
    std::string host;
    std::string port;  // string form because resolver wants it that way
    std::string path = "/";
};

// Parses a ws:// or wss:// URL. Returns false if the input is malformed.
bool parse_ws_url(std::string_view url, WsTarget& out);

class WsClient {
public:
    using MessageCallback = std::function<void(std::string_view)>;

    WsClient(WsTarget target, MessageCallback on_message);
    ~WsClient();

    WsClient(const WsClient&) = delete;
    WsClient& operator=(const WsClient&) = delete;

    // Connects and pumps messages until stop() is called or the peer closes.
    // Throws std::runtime_error on connect failure. The callback runs on the
    // same thread as run().
    void run();

    // Asks the read loop to exit. Thread-safe.
    void stop() noexcept;

    bool stopped() const noexcept {
        return stopped_.load(std::memory_order_acquire);
    }

private:
    WsTarget target_;
    MessageCallback on_message_;
    std::atomic<bool> stopped_{false};
};

}  // namespace chainguard

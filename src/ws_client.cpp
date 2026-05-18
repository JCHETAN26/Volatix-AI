// ChainGuard-Core — Boost.Beast WebSocket client implementation.
//
// Synchronous I/O. Beast's async API is more idiomatic for high fan-out
// servers, but a single-WS-stream consumer is simpler and faster on the
// sync path. When Phase 3 containerizes the engine we can revisit if
// multi-stream fan-in is needed.

#include "ws_client.hpp"

#include <stdexcept>
#include <string>
#include <utility>

#include <boost/asio/connect.hpp>
#include <boost/asio/io_context.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/ssl/context.hpp>
#include <boost/asio/ssl/stream.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/ssl.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/beast/websocket/ssl.hpp>

namespace chainguard {

namespace asio = boost::asio;
namespace beast = boost::beast;
namespace ssl = boost::asio::ssl;
namespace websocket = boost::beast::websocket;
using tcp = boost::asio::ip::tcp;

bool parse_ws_url(std::string_view url, WsTarget& out) {
    std::string_view rest = url;
    if (rest.starts_with("wss://")) {
        out.tls = true;
        rest.remove_prefix(6);
    } else if (rest.starts_with("ws://")) {
        out.tls = false;
        rest.remove_prefix(5);
    } else {
        return false;
    }

    const auto slash = rest.find('/');
    std::string_view authority = (slash == std::string_view::npos) ? rest : rest.substr(0, slash);
    out.path = (slash == std::string_view::npos) ? "/" : std::string(rest.substr(slash));

    const auto colon = authority.find(':');
    if (colon == std::string_view::npos) {
        out.host = std::string(authority);
        out.port = out.tls ? "443" : "80";
    } else {
        out.host = std::string(authority.substr(0, colon));
        out.port = std::string(authority.substr(colon + 1));
    }
    return !out.host.empty() && !out.port.empty();
}

WsClient::WsClient(WsTarget target, MessageCallback on_message)
    : target_(std::move(target)), on_message_(std::move(on_message)) {}

WsClient::~WsClient() = default;

void WsClient::stop() noexcept {
    stopped_.store(true, std::memory_order_release);
}

namespace {

template <typename Stream>
void read_loop(Stream& ws,
               const WsClient::MessageCallback& on_message,
               const std::atomic<bool>& stopped) {
    beast::flat_buffer buffer;
    while (!stopped.load(std::memory_order_acquire)) {
        beast::error_code ec;
        ws.read(buffer, ec);
        if (ec == websocket::error::closed) {
            return;
        }
        if (ec) {
            throw beast::system_error{ec};
        }
        const auto data = buffer.data();
        on_message(std::string_view(static_cast<const char*>(data.data()), data.size()));
        buffer.consume(buffer.size());
    }
}

}  // namespace

void WsClient::run() {
    asio::io_context ioc;
    tcp::resolver resolver{ioc};
    const auto endpoints = resolver.resolve(target_.host, target_.port);

    const std::string host_header = target_.host + ":" + target_.port;

    if (target_.tls) {
        ssl::context ctx{ssl::context::tls_client};
        ctx.set_default_verify_paths();
        ctx.set_verify_mode(ssl::verify_peer);

        websocket::stream<beast::ssl_stream<beast::tcp_stream>> ws{ioc, ctx};

        // SNI is required by most modern endpoints (Polygon included).
        if (!SSL_set_tlsext_host_name(ws.next_layer().native_handle(), target_.host.c_str())) {
            throw beast::system_error{beast::error_code{static_cast<int>(::ERR_get_error()),
                                                        asio::error::get_ssl_category()},
                                      "failed to set SNI hostname"};
        }

        beast::get_lowest_layer(ws).connect(endpoints);
        ws.next_layer().handshake(ssl::stream_base::client);
        ws.handshake(host_header, target_.path);
        read_loop(ws, on_message_, stopped_);
        beast::error_code ec;
        ws.close(websocket::close_code::normal, ec);
    } else {
        websocket::stream<beast::tcp_stream> ws{ioc};
        beast::get_lowest_layer(ws).connect(endpoints);
        ws.handshake(host_header, target_.path);
        read_loop(ws, on_message_, stopped_);
        beast::error_code ec;
        ws.close(websocket::close_code::normal, ec);
    }
}

}  // namespace chainguard

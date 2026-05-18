// ChainGuard-Core — tick data record
//
// Phase 2.2. Tightly packed POD representing a single trade print as it
// comes off the wire. Cache-line aligned and trivially copyable so we can
// drop it straight into the lock-free ring buffer (Phase 2.3).

#pragma once

#include <array>
#include <cstdint>

namespace chainguard {

// Side of the trade relative to the National Best Bid/Offer. Sized as a
// single byte so the struct stays compact.
enum class TickSide : std::uint8_t {
    Unknown = 0,
    Buy = 1,
    Sell = 2,
};

// Fixed-width symbol field so the struct remains trivially copyable. Eight
// bytes is enough for every NMS equity (max 5 chars + class suffix).
constexpr std::size_t kSymbolMax = 8;

struct alignas(64) TickData {
    // Ascii ticker, null-padded. Use as_view() to read.
    std::array<char, kSymbolMax> symbol{};

    // Exchange timestamp in nanoseconds since the Unix epoch.
    std::int64_t ts_ns = 0;

    // Last trade price in raw dollars (NOT pennies — keep parser simple).
    double price = 0.0;

    // Trade size in shares.
    std::uint32_t size = 0;

    // Trade side. Polygon's `T` events do not always carry this; default
    // to Unknown rather than rejecting the record.
    TickSide side = TickSide::Unknown;
};

static_assert(std::is_trivially_copyable_v<TickData>,
              "TickData must be trivially copyable so the lock-free ring "
              "in Phase 2.3 can move it with a single memcpy.");

}  // namespace chainguard

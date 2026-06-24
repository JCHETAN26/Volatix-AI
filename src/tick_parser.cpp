// Volatix-AI — SIMD JSON tick parser implementation.
//
// Expected payload shape (Polygon-flavored, also produced by mock-ticker):
//   {"sym":"AAPL","t":1715923812345000000,"p":192.34,"s":100,"side":"B"}
//
// Required keys: sym, t, p, s. `side` is optional ("B"/"S"); anything else
// is treated as Unknown.

#include "tick_parser.hpp"

#include <algorithm>
#include <cstring>

namespace volatix {

namespace {

TickSide parse_side(std::string_view raw) noexcept {
    if (raw.size() == 1) {
        switch (raw.front()) {
            case 'B':
            case 'b':
                return TickSide::Buy;
            case 'S':
            case 's':
                return TickSide::Sell;
            default:
                break;
        }
    }
    return TickSide::Unknown;
}

void copy_symbol(std::string_view src, std::array<char, kSymbolMax>& dst) noexcept {
    dst.fill('\0');
    const std::size_t n = std::min(src.size(), kSymbolMax);
    std::memcpy(dst.data(), src.data(), n);
}

}  // namespace

TickParser::TickParser() = default;

std::optional<TickData> TickParser::parse(std::string_view payload) {
    // simdjson needs SIMDJSON_PADDING bytes past the end. Refill our scratch
    // buffer if it is too small; this is rare in steady state.
    if (payload.size() + simdjson::SIMDJSON_PADDING > scratch_.size()) {
        scratch_ = simdjson::padded_string(payload.size() + simdjson::SIMDJSON_PADDING);
    }
    std::memcpy(scratch_.data(), payload.data(), payload.size());
    // Zero the padding tail so reused buffers do not leak old bytes.
    std::memset(scratch_.data() + payload.size(), 0, scratch_.size() - payload.size());

    simdjson::ondemand::document doc;
    if (parser_.iterate(scratch_.data(), payload.size(), scratch_.size()).get(doc) !=
        simdjson::SUCCESS) {
        ++parsed_rejected_;
        return std::nullopt;
    }

    TickData tick{};

    // sym (string)
    std::string_view sym;
    if (doc["sym"].get(sym) != simdjson::SUCCESS) {
        ++parsed_rejected_;
        return std::nullopt;
    }
    copy_symbol(sym, tick.symbol);

    // t (int64 nanos)
    std::int64_t ts_ns = 0;
    if (doc["t"].get(ts_ns) != simdjson::SUCCESS) {
        ++parsed_rejected_;
        return std::nullopt;
    }
    tick.ts_ns = ts_ns;

    // p (double)
    double price = 0.0;
    if (doc["p"].get(price) != simdjson::SUCCESS) {
        ++parsed_rejected_;
        return std::nullopt;
    }
    tick.price = price;

    // s (uint64 → uint32 shares)
    std::uint64_t size = 0;
    if (doc["s"].get(size) != simdjson::SUCCESS) {
        ++parsed_rejected_;
        return std::nullopt;
    }
    tick.size = static_cast<std::uint32_t>(size);

    // side (optional). Missing field is fine; bad type is fine too — treat
    // as Unknown to honor the "degrade gracefully" acceptance line.
    std::string_view side_str;
    if (doc["side"].get(side_str) == simdjson::SUCCESS) {
        tick.side = parse_side(side_str);
    }

    ++parsed_ok_;
    return tick;
}

}  // namespace volatix

// ChainGuard-Core — SIMD JSON tick parser
//
// Phase 2.2. Thin wrapper around simdjson::ondemand that turns raw bytes
// off the wire into a TickData. Returns std::nullopt on malformed payloads
// so the ingest loop can degrade gracefully instead of crashing (acceptance
// criterion for Task 2.2).
//
// One parser instance per thread — the underlying ondemand::parser owns a
// scratch buffer that is not safe to share.

#pragma once

#include <cstddef>
#include <optional>
#include <string_view>

#include <simdjson.h>

#include "tick_data.hpp"

namespace chainguard {

class TickParser {
public:
    TickParser();

    // Parses one JSON document. `payload` is borrowed; the caller must keep
    // it alive for the duration of the call. Returns std::nullopt if the
    // document is malformed or missing required fields. Statistics are
    // updated for both successful and rejected parses.
    std::optional<TickData> parse(std::string_view payload);

    std::uint64_t parsed_ok() const noexcept {
        return parsed_ok_;
    }
    std::uint64_t parsed_rejected() const noexcept {
        return parsed_rejected_;
    }

private:
    simdjson::ondemand::parser parser_;
    // simdjson::ondemand requires a padded buffer for zero-copy parsing;
    // we own it here so callers can hand us any string_view.
    simdjson::padded_string scratch_;
    std::uint64_t parsed_ok_ = 0;
    std::uint64_t parsed_rejected_ = 0;
};

}  // namespace chainguard

// ChainGuard-Core — serialized feature frame.
//
// Phase 2.3 + post-1.0 "Receipt" extension. Network-stable,
// trivially-copyable record published to the `financial-features` Kafka
// topic. Downstream Python consumers parse it with struct.unpack so the
// layout below is load-bearing — do NOT reorder or pad without bumping
// kFrameVersion.

#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <type_traits>

#include "tick_data.hpp"

namespace chainguard {

// Bumped to 2 when the layout grew from 64 → 80 bytes to carry the
// pipeline `case_id` and the engine-captured wire/compute timestamps
// that the dashboard's Microsecond Receipt UI joins on.
constexpr std::uint16_t kFrameVersion = 2;
constexpr const char* kFinancialFeaturesTopic = "financial-features";

// Layout (80 bytes, little-endian, no implicit padding):
//   offset  field           type
//   0       version         u16
//   2       _pad0           u16
//   4       window_count    u32
//   8       ts_ns           i64       (exchange timestamp of trigger tick)
//   16      symbol          char[8]
//   24      ofi             f64
//   32      realized_vol    f64
//   40      mid_price       f64
//   48      total_volume    f64
//   56      case_id         u64       (engine-generated; joins all stages)
//   64      wire_ts_ns      i64       (T+0: WS message received in engine)
//   72      compute_ts_ns   i64       (T+1: frame finished building)
#pragma pack(push, 1)
struct FeatureFrame {
    std::uint16_t version;
    std::uint16_t _pad0;
    std::uint32_t window_count;
    std::int64_t ts_ns;
    std::array<char, kSymbolMax> symbol;
    double ofi;
    double realized_vol;
    double mid_price;
    double total_volume;
    std::uint64_t case_id;
    std::int64_t wire_ts_ns;
    std::int64_t compute_ts_ns;
};
#pragma pack(pop)

static_assert(sizeof(FeatureFrame) == 80,
              "FeatureFrame must serialize to exactly 80 bytes — Python "
              "consumers parse it with struct.unpack of a fixed format.");
static_assert(std::is_trivially_copyable_v<FeatureFrame>,
              "FeatureFrame must be trivially copyable for memcpy-based "
              "serialization.");

// Writes the frame as raw bytes. Caller owns the destination buffer.
inline void serialize_feature_frame(const FeatureFrame& frame, void* dst) noexcept {
    std::memcpy(dst, &frame, sizeof(FeatureFrame));
}

}  // namespace chainguard

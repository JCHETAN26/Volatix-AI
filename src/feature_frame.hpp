// ChainGuard-Core — serialized feature frame.
//
// Phase 2.3. Network-stable, trivially-copyable record published to the
// `financial-features` Kafka topic. Downstream Python consumers parse it
// with struct.unpack so the layout below is load-bearing — do NOT
// reorder or pad without bumping kFrameVersion.

#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <type_traits>

#include "tick_data.hpp"

namespace chainguard {

constexpr std::uint16_t kFrameVersion = 1;
constexpr const char* kFinancialFeaturesTopic = "financial-features";

// Layout (64 bytes, little-endian, no implicit padding):
//   offset  field           type
//   0       version         u16
//   2       _pad0           u16
//   4       window_count    u32
//   8       ts_ns           i64
//   16      symbol          char[8]
//   24      ofi             f64
//   32      realized_vol    f64
//   40      mid_price       f64
//   48      total_volume    f64
//   56      _pad1           u64
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
    std::uint64_t _pad1;
};
#pragma pack(pop)

static_assert(sizeof(FeatureFrame) == 64,
              "FeatureFrame must serialize to exactly 64 bytes — Python "
              "consumers parse it with struct.unpack of a fixed format.");
static_assert(std::is_trivially_copyable_v<FeatureFrame>,
              "FeatureFrame must be trivially copyable for memcpy-based "
              "serialization.");

// Writes the frame as raw bytes. Caller owns the destination buffer.
inline void serialize_feature_frame(const FeatureFrame& frame, void* dst) noexcept {
    std::memcpy(dst, &frame, sizeof(FeatureFrame));
}

}  // namespace chainguard

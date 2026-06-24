// Volatix-AI — streaming feature kernels.
//
// Phase 2.3. Single-threaded, allocation-free updates on the consumer
// side of the SPSC ring. No mutexes, no system calls in the hot path.
//
// Two kernels:
//   * OfiWindow         — Order Flow Imbalance over a time-bucketed window.
//   * RealizedVolWindow — sliding stddev of log returns over the last N
//                         trades.
//
// Both are scalar; SIMD-ification can wait until profiling shows we need it.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "tick_data.hpp"

namespace volatix {

// ---------------------------------------------------------------------------
// Order Flow Imbalance
// ---------------------------------------------------------------------------
//
// OFI = sum(buy_size) - sum(sell_size) inside a moving wall-clock window.
// We approximate the sliding window with a ring of fixed-width time buckets
// so each update is O(1) regardless of window length or trade rate.
//
//   window_ns = bucket_count * bucket_width_ns
//
// Ticks older than `window_ns` automatically fall off as the bucket they
// occupied gets recycled the next time we wrap the ring.

class OfiWindow {
public:
    static constexpr std::size_t kBucketCount = 16;

    explicit OfiWindow(std::int64_t bucket_width_ns) noexcept;

    void update(const TickData& tick) noexcept;
    double value() const noexcept;  // buys - sells across active buckets

    // Sum of all volume in window. Useful for OFI-normalized views.
    double total_volume() const noexcept;

    std::int64_t window_ns() const noexcept {
        return bucket_width_ns_ * static_cast<std::int64_t>(kBucketCount);
    }

private:
    struct Bucket {
        std::int64_t epoch = 0;  // bucket_width_ns aligned ts; 0 = unused
        double buy_volume = 0.0;
        double sell_volume = 0.0;
    };

    std::int64_t bucket_width_ns_;
    std::array<Bucket, kBucketCount> buckets_{};
    std::int64_t newest_epoch_ = 0;
};

// ---------------------------------------------------------------------------
// Realized Volatility
// ---------------------------------------------------------------------------
//
// RV = stddev(log(p_t / p_{t-1})) over the last N trades. Stored in two
// fixed-size circular arrays so the update is O(1) per tick and the
// finalize() step is O(N) — both well under 50µs for N=128.

class RealizedVolWindow {
public:
    static constexpr std::size_t kMaxSamples = 128;

    explicit RealizedVolWindow(std::size_t samples = kMaxSamples) noexcept;

    void update(double price) noexcept;
    double value() const noexcept;  // stddev of log returns; 0 if <2 samples

    std::size_t count() const noexcept {
        return count_;
    }

private:
    std::size_t capacity_;
    std::array<double, kMaxSamples> returns_{};
    std::size_t head_ = 0;
    std::size_t count_ = 0;
    double last_price_ = 0.0;
};

}  // namespace volatix

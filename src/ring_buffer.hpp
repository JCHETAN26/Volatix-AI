// ChainGuard-Core — Single-Producer / Single-Consumer lock-free ring.
//
// Phase 2.3. The ingest thread (WebSocket+parser) pushes TickData into the
// ring; the feature thread pops it and updates the OFI / Realized-Volatility
// state. No mutexes, no condition variables, no blocking — try_push and
// try_pop are bounded-wait and exit immediately when full/empty.
//
// The two indices live on separate cache lines so producer + consumer
// updates never invalidate each other's lines.

#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <type_traits>

namespace chainguard {

template <typename T, std::size_t Capacity>
class SpscRing {
    static_assert((Capacity & (Capacity - 1)) == 0, "SpscRing capacity must be a power of two");
    static_assert(Capacity >= 2, "SpscRing capacity must be >= 2");
    static_assert(std::is_trivially_copyable_v<T>,
                  "SpscRing element type must be trivially copyable so push "
                  "and pop reduce to a single memcpy.");

public:
    static constexpr std::size_t capacity = Capacity;
    static constexpr std::size_t mask = Capacity - 1;

    SpscRing() = default;
    SpscRing(const SpscRing&) = delete;
    SpscRing& operator=(const SpscRing&) = delete;

    // Producer-side push. Returns false when the ring is full — the caller
    // decides whether to drop, retry, or exert back-pressure.
    bool try_push(const T& value) noexcept {
        const std::size_t tail = tail_.load(std::memory_order_relaxed);
        const std::size_t next = (tail + 1) & mask;
        if (next == head_.load(std::memory_order_acquire)) {
            return false;  // full
        }
        buf_[tail] = value;
        tail_.store(next, std::memory_order_release);
        return true;
    }

    // Consumer-side pop. Returns false when the ring is empty.
    bool try_pop(T& out) noexcept {
        const std::size_t head = head_.load(std::memory_order_relaxed);
        if (head == tail_.load(std::memory_order_acquire)) {
            return false;  // empty
        }
        out = buf_[head];
        head_.store((head + 1) & mask, std::memory_order_release);
        return true;
    }

    // Conservative size estimate. Useful for telemetry; not safe to drive
    // control flow off because head/tail can move under us.
    std::size_t size_approx() const noexcept {
        const std::size_t tail = tail_.load(std::memory_order_acquire);
        const std::size_t head = head_.load(std::memory_order_acquire);
        return (tail - head) & mask;
    }

private:
    // 64-byte alignment on each index avoids false sharing between the
    // producer-only tail_ and the consumer-only head_.
    alignas(64) std::atomic<std::size_t> head_{0};
    alignas(64) std::atomic<std::size_t> tail_{0};
    alignas(64) std::array<T, Capacity> buf_{};
};

}  // namespace chainguard

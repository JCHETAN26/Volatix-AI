// ChainGuard-Core — feature kernel implementations.

#include "features.hpp"

#include <algorithm>
#include <cmath>

namespace chainguard {

// ---------------------------------------------------------------------------
// OfiWindow
// ---------------------------------------------------------------------------

OfiWindow::OfiWindow(std::int64_t bucket_width_ns) noexcept
    : bucket_width_ns_(bucket_width_ns > 0 ? bucket_width_ns : 1) {}

void OfiWindow::update(const TickData& tick) noexcept {
    if (tick.size == 0 || tick.side == TickSide::Unknown) {
        // Polygon rarely tags side on auction prints; ignoring them keeps
        // the imbalance signal clean rather than pulling toward zero.
        return;
    }

    const std::int64_t epoch = tick.ts_ns / bucket_width_ns_;
    const std::size_t slot = static_cast<std::size_t>(epoch) % kBucketCount;
    Bucket& bucket = buckets_[slot];

    // Recycle the slot when its epoch is out of the current window.
    if (bucket.epoch != epoch) {
        bucket.epoch = epoch;
        bucket.buy_volume = 0.0;
        bucket.sell_volume = 0.0;
    }

    const double vol = static_cast<double>(tick.size);
    if (tick.side == TickSide::Buy) {
        bucket.buy_volume += vol;
    } else {
        bucket.sell_volume += vol;
    }

    if (epoch > newest_epoch_) {
        newest_epoch_ = epoch;
    }
}

double OfiWindow::value() const noexcept {
    double buys = 0.0;
    double sells = 0.0;
    const std::int64_t oldest = newest_epoch_ - static_cast<std::int64_t>(kBucketCount) + 1;
    for (const Bucket& b : buckets_) {
        if (b.epoch >= oldest && b.epoch <= newest_epoch_) {
            buys += b.buy_volume;
            sells += b.sell_volume;
        }
    }
    return buys - sells;
}

double OfiWindow::total_volume() const noexcept {
    double total = 0.0;
    const std::int64_t oldest = newest_epoch_ - static_cast<std::int64_t>(kBucketCount) + 1;
    for (const Bucket& b : buckets_) {
        if (b.epoch >= oldest && b.epoch <= newest_epoch_) {
            total += b.buy_volume + b.sell_volume;
        }
    }
    return total;
}

// ---------------------------------------------------------------------------
// RealizedVolWindow
// ---------------------------------------------------------------------------

RealizedVolWindow::RealizedVolWindow(std::size_t samples) noexcept
    : capacity_(std::min(samples == 0 ? kMaxSamples : samples, kMaxSamples)) {}

void RealizedVolWindow::update(double price) noexcept {
    if (price <= 0.0) {
        return;
    }
    if (last_price_ <= 0.0) {
        last_price_ = price;
        return;
    }

    const double r = std::log(price / last_price_);
    last_price_ = price;

    returns_[head_] = r;
    head_ = (head_ + 1) % capacity_;
    if (count_ < capacity_) {
        ++count_;
    }
}

double RealizedVolWindow::value() const noexcept {
    if (count_ < 2) {
        return 0.0;
    }

    double sum = 0.0;
    for (std::size_t i = 0; i < count_; ++i) {
        sum += returns_[i];
    }
    const double mean = sum / static_cast<double>(count_);

    double sq = 0.0;
    for (std::size_t i = 0; i < count_; ++i) {
        const double d = returns_[i] - mean;
        sq += d * d;
    }
    // Sample variance (Bessel-corrected) so a single outlier does not blow
    // up the stddev with small N.
    return std::sqrt(sq / static_cast<double>(count_ - 1));
}

}  // namespace chainguard

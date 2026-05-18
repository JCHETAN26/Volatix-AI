// ChainGuard-Core — feature engine pipeline implementation.

#include "engine.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <librdkafka/rdkafkacpp.h>

#include "feature_frame.hpp"
#include "features.hpp"
#include "ring_buffer.hpp"
#include "tick_data.hpp"
#include "tick_parser.hpp"
#include "ws_client.hpp"

namespace chainguard {

namespace {

constexpr std::size_t kRingCapacity = 1 << 16;  // 65,536 slots
constexpr int kFlushTimeoutMs = 5'000;
constexpr int kPollIntervalMs = 100;

std::atomic<bool>* g_engine_shutdown = nullptr;

void engine_signal_handler(int) noexcept {
    if (g_engine_shutdown) {
        g_engine_shutdown->store(true, std::memory_order_release);
    }
}

bool conf_set(RdKafka::Conf& conf, const std::string& key, const std::string& value) {
    std::string err;
    if (conf.set(key, value, err) != RdKafka::Conf::CONF_OK) {
        std::cerr << "conf set " << key << "=" << value << ": " << err << '\n';
        return false;
    }
    return true;
}

std::unique_ptr<RdKafka::Producer> make_engine_producer(const std::string& brokers) {
    std::unique_ptr<RdKafka::Conf> conf(RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL));
    if (!conf_set(*conf, "bootstrap.servers", brokers))
        return nullptr;
    if (!conf_set(*conf, "client.id", "chainguard-engine"))
        return nullptr;
    if (!conf_set(*conf, "socket.timeout.ms", "5000"))
        return nullptr;
    // batch.size and linger let the broker absorb 100µs+ bursts; the
    // values are conservative defaults — Phase 3 KEDA tuning is where
    // these get nailed down.
    if (!conf_set(*conf, "linger.ms", "5"))
        return nullptr;

    std::string err;
    std::unique_ptr<RdKafka::Producer> producer(RdKafka::Producer::create(conf.get(), err));
    if (!producer) {
        std::cerr << "failed to create producer: " << err << '\n';
    }
    return producer;
}

double mid_price_from(double last_price) noexcept {
    // No L2 book yet — mid-price is just the last trade print until
    // Phase 4 surfaces quote events.
    return last_price;
}

FeatureFrame build_frame(const OfiWindow& ofi,
                         const RealizedVolWindow& rv,
                         const TickData& latest,
                         double mid) noexcept {
    FeatureFrame f{};
    f.version = kFrameVersion;
    f.window_count = static_cast<std::uint32_t>(rv.count());
    f.ts_ns = latest.ts_ns;
    f.symbol = latest.symbol;
    f.ofi = ofi.value();
    f.realized_vol = rv.value();
    f.mid_price = mid;
    f.total_volume = ofi.total_volume();
    return f;
}

}  // namespace

int run_engine(const EngineConfig& cfg) {
    WsTarget target;
    if (!parse_ws_url(cfg.ws_url, target)) {
        std::cerr << "invalid WebSocket URL: " << cfg.ws_url << '\n';
        return EXIT_FAILURE;
    }

    auto producer = make_engine_producer(cfg.brokers);
    if (!producer)
        return EXIT_FAILURE;

    auto ring = std::make_unique<SpscRing<TickData, kRingCapacity>>();
    std::atomic<bool> shutdown{false};
    g_engine_shutdown = &shutdown;
    std::signal(SIGINT, engine_signal_handler);
    std::signal(SIGTERM, engine_signal_handler);

    std::atomic<std::uint64_t> pushed{0};
    std::atomic<std::uint64_t> dropped{0};
    std::atomic<std::uint64_t> popped{0};
    std::atomic<std::uint64_t> frames_emitted{0};

    std::cout << "chainguard engine\n"
              << "  ws_url:        " << cfg.ws_url << '\n'
              << "  brokers:       " << cfg.brokers << '\n'
              << "  topic:         " << cfg.topic << '\n'
              << "  ring capacity: " << kRingCapacity << '\n'
              << "  OFI window:    " << cfg.ofi_bucket_width_ns * OfiWindow::kBucketCount
              << " ns total (" << OfiWindow::kBucketCount << " x " << cfg.ofi_bucket_width_ns
              << "ns)\n"
              << "  RV samples:    " << cfg.rv_samples << '\n'
              << "  frame every:   " << cfg.frame_interval_ticks << " ticks\n";

    // --- Producer thread (WebSocket parser → ring) -----------------------
    std::unique_ptr<WsClient> client;
    auto on_message = [&](std::string_view payload) {
        thread_local TickParser parser;
        if (auto tick = parser.parse(payload); tick) {
            if (ring->try_push(*tick)) {
                pushed.fetch_add(1, std::memory_order_relaxed);
            } else {
                // Ring full → drop. Phase 3 KEDA scales us out long before
                // we sustain this state; for the demo we just count drops.
                dropped.fetch_add(1, std::memory_order_relaxed);
            }
        }
        if (shutdown.load(std::memory_order_acquire) && client) {
            client->stop();
        }
    };
    client = std::make_unique<WsClient>(target, on_message);

    std::thread producer_thread([&]() {
        try {
            client->run();
        } catch (const std::exception& ex) {
            std::cerr << "websocket error: " << ex.what() << '\n';
            shutdown.store(true, std::memory_order_release);
        }
    });

    // --- Consumer thread (ring → features → Kafka) -----------------------
    std::thread consumer_thread([&]() {
        OfiWindow ofi(cfg.ofi_bucket_width_ns);
        RealizedVolWindow rv(cfg.rv_samples);
        TickData latest{};
        bool have_latest = false;
        std::uint32_t since_frame = 0;
        auto last_poll = std::chrono::steady_clock::now();

        while (!shutdown.load(std::memory_order_acquire)) {
            TickData tick;
            if (!ring->try_pop(tick)) {
                // Quick yield instead of busy spinning so we don't burn a
                // full core when the WebSocket is idle.
                std::this_thread::yield();
                continue;
            }
            popped.fetch_add(1, std::memory_order_relaxed);
            ofi.update(tick);
            rv.update(tick.price);
            latest = tick;
            have_latest = true;

            if (++since_frame >= cfg.frame_interval_ticks && have_latest) {
                since_frame = 0;
                const FeatureFrame frame = build_frame(ofi, rv, latest, mid_price_from(tick.price));
                std::array<std::byte, sizeof(FeatureFrame)> bytes{};
                serialize_feature_frame(frame, bytes.data());
                const RdKafka::ErrorCode err = producer->produce(cfg.topic,
                                                                 RdKafka::Topic::PARTITION_UA,
                                                                 RdKafka::Producer::RK_MSG_COPY,
                                                                 bytes.data(),
                                                                 bytes.size(),
                                                                 latest.symbol.data(),
                                                                 latest.symbol.size(),
                                                                 /*timestamp=*/0,
                                                                 /*msg_opaque=*/nullptr);
                if (err != RdKafka::ERR_NO_ERROR) {
                    std::cerr << "produce failed: " << RdKafka::err2str(err) << '\n';
                } else {
                    frames_emitted.fetch_add(1, std::memory_order_relaxed);
                }
            }

            const auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_poll).count() >=
                kPollIntervalMs) {
                producer->poll(0);
                last_poll = now;
            }
        }
    });

    // --- Reporter (telemetry) --------------------------------------------
    std::thread reporter_thread([&]() {
        std::uint64_t last_popped = 0;
        auto last_tick = std::chrono::steady_clock::now();
        while (!shutdown.load(std::memory_order_acquire)) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            const auto now = std::chrono::steady_clock::now();
            const auto p = popped.load(std::memory_order_relaxed);
            const auto pu = pushed.load(std::memory_order_relaxed);
            const auto dr = dropped.load(std::memory_order_relaxed);
            const auto fr = frames_emitted.load(std::memory_order_relaxed);
            const double dt = std::chrono::duration<double>(now - last_tick).count();
            const double tps = dt > 0.0 ? static_cast<double>(p - last_popped) / dt : 0.0;
            std::printf(
                "  ticks: pushed=%llu popped=%llu dropped=%llu  frames=%llu  rate=%.0f tps\n",
                static_cast<unsigned long long>(pu),
                static_cast<unsigned long long>(p),
                static_cast<unsigned long long>(dr),
                static_cast<unsigned long long>(fr),
                tps);
            std::fflush(stdout);
            last_popped = p;
            last_tick = now;
        }
    });

    producer_thread.join();
    shutdown.store(true, std::memory_order_release);
    consumer_thread.join();
    reporter_thread.join();
    producer->flush(kFlushTimeoutMs);

    std::cout << "  → engine stopped.\n"
              << "    pushed=" << pushed.load() << " popped=" << popped.load()
              << " dropped=" << dropped.load() << " frames=" << frames_emitted.load() << '\n';
    return EXIT_SUCCESS;
}

int run_feature_bench(int prefill_ticks, int frame_iterations) {
    if (prefill_ticks <= 0)
        prefill_ticks = 1024;
    if (frame_iterations <= 0)
        frame_iterations = 100'000;

    std::cout << "chainguard feature-bench\n"
              << "  prefill ticks:    " << prefill_ticks << '\n'
              << "  frame iterations: " << frame_iterations << '\n';

    constexpr std::int64_t bucket_ns = 100'000'000;  // 100ms × 16 = 1.6s window
    OfiWindow ofi(bucket_ns);
    RealizedVolWindow rv(RealizedVolWindow::kMaxSamples);

    // Warm both kernels with a realistic burst of ticks.
    TickData seed_tick{};
    seed_tick.symbol = std::array<char, kSymbolMax>{'A', 'A', 'P', 'L', 0, 0, 0, 0};
    for (int i = 0; i < prefill_ticks; ++i) {
        seed_tick.ts_ns = 1'715'923'812'000'000'000LL + i * 10'000'000LL;  // 10ms apart
        seed_tick.price = 192.0 + (i % 200) * 0.01;
        seed_tick.size = 100 + (i % 500);
        seed_tick.side = (i & 1) ? TickSide::Buy : TickSide::Sell;
        ofi.update(seed_tick);
        rv.update(seed_tick.price);
    }

    // Measure frame-generation latency over `frame_iterations` cycles.
    std::vector<std::int64_t> samples;
    samples.reserve(static_cast<std::size_t>(frame_iterations));

    std::array<std::byte, sizeof(FeatureFrame)> bytes{};
    // XOR-accumulated sink keeps the optimizer from eliding the per-iteration
    // work without resorting to inline asm.
    std::uint64_t sink = 0;
    for (int i = 0; i < frame_iterations; ++i) {
        const auto t0 = std::chrono::steady_clock::now();
        FeatureFrame frame = build_frame(ofi, rv, seed_tick, mid_price_from(seed_tick.price));
        serialize_feature_frame(frame, bytes.data());
        const auto t1 = std::chrono::steady_clock::now();
        samples.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
        sink ^= static_cast<std::uint64_t>(std::to_integer<std::uint8_t>(bytes[i & 63]));
    }

    std::sort(samples.begin(), samples.end());
    const auto median = samples[samples.size() / 2];
    const auto p99 = samples[static_cast<std::size_t>(static_cast<double>(samples.size()) * 0.99)];
    const auto max = samples.back();

    std::cout << "  latency (ns):  median=" << median << "  p99=" << p99 << "  max=" << max << '\n';
    std::cout << "  latency (µs):  median=" << median / 1000.0 << "  p99=" << p99 / 1000.0
              << "  max=" << max / 1000.0 << '\n';
    // Materialize sink so the loop body isn't dead-code-eliminated.
    std::cout << "  (sink check:   " << sink << ")\n";

    constexpr std::int64_t kAcceptanceCeilingNs = 50'000;  // 50µs
    if (median > kAcceptanceCeilingNs) {
        std::cerr << "  → ABOVE acceptance ceiling of 50µs (median)\n";
        return EXIT_FAILURE;
    }
    std::cout << "  → meets acceptance (median < 50µs)\n";
    return EXIT_SUCCESS;
}

}  // namespace chainguard

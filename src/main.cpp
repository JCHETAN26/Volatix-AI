// ChainGuard-Core — Ingestion & Feature Engineering Engine
//
// Phase 2.1: native Kafka producer with --probe / --smoke modes.
// Phase 2.2: --ingest streams JSON ticks off a WebSocket and parses them
//            with simdjson; --throughput-test benchmarks the parser in
//            isolation (drives the 20,000+ ticks/sec acceptance line).
// Phase 2.3: --engine wires the full WebSocket → SPSC ring → OFI/RV
//            kernels → FeatureFrame → Kafka pipeline. --feature-bench
//            enforces the <50µs frame-generation acceptance ceiling.

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

// Both Ubuntu (librdkafka-dev) and Homebrew install the C++ headers under a
// `librdkafka/` subdirectory of the include prefix that pkg-config exposes,
// so this prefixed form is the portable one.
#include <librdkafka/rdkafkacpp.h>

#include "engine.hpp"
#include "feature_frame.hpp"
#include "tick_parser.hpp"
#include "ws_client.hpp"

namespace chainguard {

constexpr const char* kVersion = "0.3.1";
constexpr const char* kDefaultBrokers = "localhost:9092";
constexpr const char* kDefaultWsUrl = "ws://localhost:8765/";
constexpr const char* kSmokeTopic = "chainguard.smoke";
constexpr const char* kDefaultConsumeTopic = "raw-ticks";
constexpr const char* kDefaultConsumeGroup = "chainguard-engine";
constexpr int kSmokeMessageCount = 10;
constexpr int kFlushTimeoutMs = 10'000;
constexpr int kMetadataTimeoutMs = 5'000;
constexpr int kDefaultThroughputCount = 1'000'000;
constexpr std::int64_t kDefaultOfiBucketNs = 100'000'000;  // 100ms × 16 = 1.6s window
constexpr std::size_t kDefaultRvSamples = 100;
constexpr std::uint32_t kDefaultFrameIntervalTicks = 100;
constexpr int kDefaultBenchPrefillTicks = 1024;
constexpr int kDefaultBenchFrameIterations = 100'000;

// Counts delivery acks so --smoke can fail when any message is dropped.
class DeliveryReportCb : public RdKafka::DeliveryReportCb {
public:
    void dr_cb(RdKafka::Message& msg) override {
        if (msg.err() == RdKafka::ERR_NO_ERROR) {
            ++delivered_;
        } else {
            ++failed_;
            std::cerr << "delivery failed: " << msg.errstr() << '\n';
        }
    }

    int delivered() const noexcept {
        return delivered_;
    }
    int failed() const noexcept {
        return failed_;
    }

private:
    int delivered_ = 0;
    int failed_ = 0;
};

// Wraps Conf::set so the CONF_OK / error-string contract is one line.
bool conf_set(RdKafka::Conf& conf, const std::string& key, const std::string& value) {
    std::string err;
    if (conf.set(key, value, err) != RdKafka::Conf::CONF_OK) {
        std::cerr << "conf set " << key << "=" << value << ": " << err << '\n';
        return false;
    }
    return true;
}

bool conf_set(RdKafka::Conf& conf, const std::string& key, RdKafka::DeliveryReportCb* cb) {
    std::string err;
    if (conf.set(key, cb, err) != RdKafka::Conf::CONF_OK) {
        std::cerr << "conf set " << key << ": " << err << '\n';
        return false;
    }
    return true;
}

std::unique_ptr<RdKafka::Producer> make_producer(const std::string& brokers,
                                                 RdKafka::DeliveryReportCb* dr_cb) {
    std::unique_ptr<RdKafka::Conf> conf(RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL));
    if (!conf_set(*conf, "bootstrap.servers", brokers))
        return nullptr;
    if (!conf_set(*conf, "client.id", "chainguard-core"))
        return nullptr;
    // 5s socket timeout keeps --probe responsive when nothing is listening.
    if (!conf_set(*conf, "socket.timeout.ms", "5000"))
        return nullptr;
    if (dr_cb && !conf_set(*conf, "dr_cb", dr_cb))
        return nullptr;

    std::string err;
    std::unique_ptr<RdKafka::Producer> producer(RdKafka::Producer::create(conf.get(), err));
    if (!producer) {
        std::cerr << "failed to create producer: " << err << '\n';
    }
    return producer;
}

int run_probe(const std::string& brokers) {
    std::cout << "chainguard " << kVersion << " — probe\n"
              << "  brokers: " << brokers << '\n';

    auto producer = make_producer(brokers, nullptr);
    if (!producer)
        return EXIT_FAILURE;

    RdKafka::Metadata* raw_meta = nullptr;
    const RdKafka::ErrorCode meta_err = producer->metadata(
        /*all_topics=*/true, /*only_rkt=*/nullptr, &raw_meta, kMetadataTimeoutMs);
    std::unique_ptr<RdKafka::Metadata> meta(raw_meta);

    if (meta_err != RdKafka::ERR_NO_ERROR) {
        std::cerr << "metadata request failed: " << RdKafka::err2str(meta_err) << '\n';
        return EXIT_FAILURE;
    }

    std::cout << "  brokers reachable: " << meta->brokers()->size() << '\n'
              << "  topics visible:    " << meta->topics()->size() << '\n'
              << "  → connection verified\n";
    return EXIT_SUCCESS;
}

int run_smoke(const std::string& brokers) {
    std::cout << "chainguard " << kVersion << " — Kafka smoke test\n"
              << "  brokers: " << brokers << '\n'
              << "  topic:   " << kSmokeTopic << '\n'
              << "  count:   " << kSmokeMessageCount << '\n';

    DeliveryReportCb dr_cb;
    auto producer = make_producer(brokers, &dr_cb);
    if (!producer)
        return EXIT_FAILURE;

    for (int i = 0; i < kSmokeMessageCount; ++i) {
        std::string payload = "chainguard-smoke-" + std::to_string(i);
        const RdKafka::ErrorCode produce_err = producer->produce(kSmokeTopic,
                                                                 RdKafka::Topic::PARTITION_UA,
                                                                 RdKafka::Producer::RK_MSG_COPY,
                                                                 payload.data(),
                                                                 payload.size(),
                                                                 /*key=*/nullptr,
                                                                 /*key_len=*/0,
                                                                 /*timestamp=*/0,
                                                                 /*msg_opaque=*/nullptr);
        if (produce_err != RdKafka::ERR_NO_ERROR) {
            std::cerr << "produce[" << i << "] failed: " << RdKafka::err2str(produce_err) << '\n';
            return EXIT_FAILURE;
        }
        producer->poll(0);
    }

    if (producer->flush(kFlushTimeoutMs) != RdKafka::ERR_NO_ERROR) {
        std::cerr << "flush timeout after " << kFlushTimeoutMs << "ms\n";
        return EXIT_FAILURE;
    }

    std::cout << "  delivered=" << dr_cb.delivered() << " failed=" << dr_cb.failed() << '\n';
    if (dr_cb.failed() != 0 || dr_cb.delivered() != kSmokeMessageCount) {
        std::cerr << "  → packet drop detected\n";
        return EXIT_FAILURE;
    }
    std::cout << "  → all messages acknowledged (zero drops)\n";
    return EXIT_SUCCESS;
}

// ---------------------------------------------------------------------------
// Phase 2.2 — WebSocket ingest
// ---------------------------------------------------------------------------

namespace {
std::atomic<bool>* g_shutdown_flag = nullptr;
void shutdown_signal(int) noexcept {
    if (g_shutdown_flag) {
        g_shutdown_flag->store(true, std::memory_order_release);
    }
}
}  // namespace

int run_ingest(const std::string& ws_url) {
    WsTarget target;
    if (!parse_ws_url(ws_url, target)) {
        std::cerr << "invalid WebSocket URL: " << ws_url << '\n';
        return EXIT_FAILURE;
    }

    std::cout << "chainguard " << kVersion << " — ingest\n"
              << "  url:    " << ws_url << '\n'
              << "  host:   " << target.host << ":" << target.port << target.path << '\n'
              << "  tls:    " << (target.tls ? "yes" : "no") << '\n';

    TickParser parser;
    std::atomic<bool> shutdown{false};
    g_shutdown_flag = &shutdown;
    std::signal(SIGINT, shutdown_signal);
    std::signal(SIGTERM, shutdown_signal);

    std::unique_ptr<WsClient> client;
    auto on_message = [&](std::string_view payload) {
        parser.parse(payload);
        if (shutdown.load(std::memory_order_acquire) && client) {
            client->stop();
        }
    };

    client = std::make_unique<WsClient>(target, on_message);

    const auto start = std::chrono::steady_clock::now();
    std::uint64_t last_ok = 0;
    auto last_tick = start;

    // Reporter thread: prints throughput every second until shutdown.
    std::thread reporter([&]() {
        while (!shutdown.load(std::memory_order_acquire)) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            const auto now = std::chrono::steady_clock::now();
            const std::uint64_t ok = parser.parsed_ok();
            const std::uint64_t rej = parser.parsed_rejected();
            const auto dt = std::chrono::duration<double>(now - last_tick).count();
            const double rate = dt > 0.0 ? static_cast<double>(ok - last_ok) / dt : 0.0;
            std::printf("  parsed=%llu  rejected=%llu  rate=%.0f tps\n",
                        static_cast<unsigned long long>(ok),
                        static_cast<unsigned long long>(rej),
                        rate);
            std::fflush(stdout);
            last_ok = ok;
            last_tick = now;
        }
    });

    try {
        client->run();
    } catch (const std::exception& ex) {
        std::cerr << "ingest error: " << ex.what() << '\n';
        shutdown.store(true, std::memory_order_release);
        reporter.join();
        return EXIT_FAILURE;
    }

    shutdown.store(true, std::memory_order_release);
    reporter.join();
    std::cout << "  → stopped. parsed=" << parser.parsed_ok()
              << " rejected=" << parser.parsed_rejected() << '\n';
    return EXIT_SUCCESS;
}

int run_throughput_test(int count) {
    std::cout << "chainguard " << kVersion << " — throughput test\n"
              << "  payloads: " << count << '\n';

    // Synthesize one payload per loop iteration so we exercise the parser
    // exclusively (no I/O). Numbers are kept deterministic so reviewers can
    // diff runs.
    std::vector<std::string> corpus;
    corpus.reserve(static_cast<std::size_t>(count));
    for (int i = 0; i < count; ++i) {
        const double price = 100.0 + static_cast<double>(i % 5000) * 0.01;
        const int size_shares = 100 + (i % 500);
        const std::int64_t ts_ns = 1'715'923'812'345'000'000LL + static_cast<std::int64_t>(i);
        char buf[160];
        const int n = std::snprintf(buf,
                                    sizeof(buf),
                                    R"({"sym":"AAPL","t":%lld,"p":%.2f,"s":%d,"side":"%c"})",
                                    static_cast<long long>(ts_ns),
                                    price,
                                    size_shares,
                                    (i & 1) ? 'B' : 'S');
        corpus.emplace_back(buf, static_cast<std::size_t>(n));
    }

    TickParser parser;
    const auto t0 = std::chrono::steady_clock::now();
    for (const auto& payload : corpus) {
        parser.parse(payload);
    }
    const auto t1 = std::chrono::steady_clock::now();

    const auto secs = std::chrono::duration<double>(t1 - t0).count();
    const double rate = secs > 0.0 ? static_cast<double>(corpus.size()) / secs : 0.0;
    std::cout << "  elapsed: " << secs << " s\n"
              << "  parsed_ok:    " << parser.parsed_ok() << '\n'
              << "  parsed_reject:" << parser.parsed_rejected() << '\n'
              << "  throughput:   " << static_cast<long long>(rate) << " ticks/sec\n";

    // Phase 2.2 acceptance: 20,000+ tick payloads per second.
    constexpr double kAcceptanceFloor = 20'000.0;
    if (rate < kAcceptanceFloor) {
        std::cerr << "  → BELOW acceptance floor of " << kAcceptanceFloor << " tps\n";
        return EXIT_FAILURE;
    }
    std::cout << "  → meets acceptance (≥ " << kAcceptanceFloor << " tps)\n";
    return EXIT_SUCCESS;
}

void print_usage(const char* argv0) {
    std::cout << "Usage: " << argv0 << " [options]\n"
              << "  --brokers HOST:PORT[,HOST:PORT...]  Kafka bootstrap servers\n"
              << "                                      (default: " << kDefaultBrokers
              << ", env: KAFKA_BROKERS)\n"
              << "  --probe                             Verify broker connection via metadata\n"
              << "  --smoke                             Produce " << kSmokeMessageCount
              << " records to '" << kSmokeTopic << "' and\n"
              << "                                      verify zero delivery failures\n"
              << "  --ingest                            Stream a WebSocket and parse ticks\n"
              << "                                      via simdjson (Ctrl-C to stop)\n"
              << "  --ws-url URL                        WebSocket endpoint for --ingest\n"
              << "                                      (default: " << kDefaultWsUrl
              << ", env: WS_URL)\n"
              << "  --throughput-test [N]               Benchmark parser on N synthetic\n"
              << "                                      ticks (default: " << kDefaultThroughputCount
              << ")\n"
              << "  --engine                            Run full pipeline: WS → SPSC ring →\n"
              << "                                      OFI/RV → Kafka topic '"
              << kFinancialFeaturesTopic << "'\n"
              << "  --consume [TOPIC]                   Subscribe to a Kafka topic under a\n"
              << "                                      consumer group (Phase 3.2 KEDA lag\n"
              << "                                      signal). Default topic: "
              << kDefaultConsumeTopic << "\n"
              << "  --group GROUP                       Consumer group for --consume\n"
              << "                                      (default: " << kDefaultConsumeGroup << ")\n"
              << "  --feature-bench [P [F]]             Bench frame-gen latency. P = prefill\n"
              << "                                      ticks (default: "
              << kDefaultBenchPrefillTicks << "), F = frame\n"
              << "                                      iterations (default: "
              << kDefaultBenchFrameIterations << ").\n"
              << "                                      Fails if median ≥ 50µs.\n"
              << "  --version                           Print version and exit\n"
              << "  -h, --help                          Print this help and exit\n";
}

}  // namespace chainguard

int main(int argc, char** argv) {
    using namespace chainguard;

    std::string brokers = kDefaultBrokers;
    std::string ws_url = kDefaultWsUrl;
    std::string consume_topic = kDefaultConsumeTopic;
    std::string consume_group = kDefaultConsumeGroup;
    int throughput_count = kDefaultThroughputCount;
    int bench_prefill = kDefaultBenchPrefillTicks;
    int bench_iterations = kDefaultBenchFrameIterations;

    if (const char* env = std::getenv("KAFKA_BROKERS"); env && *env) {
        brokers = env;
    }
    if (const char* env = std::getenv("WS_URL"); env && *env) {
        ws_url = env;
    }

    enum class Mode { Default, Probe, Smoke, Ingest, Throughput, Engine, Bench, Consume };
    Mode mode = Mode::Default;

    for (int i = 1; i < argc; ++i) {
        const std::string_view arg = argv[i];
        if (arg == "--brokers" && i + 1 < argc) {
            brokers = argv[++i];
        } else if (arg == "--ws-url" && i + 1 < argc) {
            ws_url = argv[++i];
        } else if (arg == "--probe") {
            mode = Mode::Probe;
        } else if (arg == "--smoke") {
            mode = Mode::Smoke;
        } else if (arg == "--ingest") {
            mode = Mode::Ingest;
        } else if (arg == "--throughput-test") {
            mode = Mode::Throughput;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                throughput_count = std::atoi(argv[++i]);
                if (throughput_count <= 0) {
                    std::cerr << "throughput-test count must be > 0\n";
                    return EXIT_FAILURE;
                }
            }
        } else if (arg == "--engine") {
            mode = Mode::Engine;
        } else if (arg == "--consume") {
            mode = Mode::Consume;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                consume_topic = argv[++i];
            }
        } else if (arg == "--group" && i + 1 < argc) {
            consume_group = argv[++i];
        } else if (arg == "--feature-bench") {
            mode = Mode::Bench;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                bench_prefill = std::atoi(argv[++i]);
                if (bench_prefill <= 0) {
                    std::cerr << "feature-bench prefill must be > 0\n";
                    return EXIT_FAILURE;
                }
            }
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                bench_iterations = std::atoi(argv[++i]);
                if (bench_iterations <= 0) {
                    std::cerr << "feature-bench iterations must be > 0\n";
                    return EXIT_FAILURE;
                }
            }
        } else if (arg == "--version") {
            std::cout << "chainguard " << kVersion << '\n';
            return EXIT_SUCCESS;
        } else if (arg == "-h" || arg == "--help") {
            print_usage(argv[0]);
            return EXIT_SUCCESS;
        } else {
            std::cerr << "unknown argument: " << arg << "\n\n";
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }
    }

    switch (mode) {
        case Mode::Probe:
            return run_probe(brokers);
        case Mode::Smoke:
            return run_smoke(brokers);
        case Mode::Ingest:
            return run_ingest(ws_url);
        case Mode::Throughput:
            return run_throughput_test(throughput_count);
        case Mode::Engine: {
            EngineConfig cfg{
                .ws_url = ws_url,
                .brokers = brokers,
                .topic = kFinancialFeaturesTopic,
                .ofi_bucket_width_ns = kDefaultOfiBucketNs,
                .rv_samples = kDefaultRvSamples,
                .frame_interval_ticks = kDefaultFrameIntervalTicks,
            };
            return run_engine(cfg);
        }
        case Mode::Bench:
            return run_feature_bench(bench_prefill, bench_iterations);
        case Mode::Consume:
            return run_consume(brokers, consume_topic, consume_group);
        case Mode::Default:
            // No args: build smoke-test (used by CI). Must not contact Kafka.
            std::cout << "chainguard " << kVersion << " — Phase 3 build OK\n"
                      << "  Modes: --probe | --smoke | --ingest | --throughput-test\n"
                      << "         --engine | --feature-bench | --consume\n"
                      << "  Default brokers: " << brokers << '\n'
                      << "  Default ws-url:  " << ws_url << '\n';
            return EXIT_SUCCESS;
    }
    return EXIT_SUCCESS;
}

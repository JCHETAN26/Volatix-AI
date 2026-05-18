// ChainGuard-Core — Ingestion & Feature Engineering Engine
//
// Phase 2.1: minimal native Kafka producer.
//   * `--probe`  → request broker metadata; verifies the connection without
//                  emitting any records (safe in CI without Kafka — see main).
//   * `--smoke`  → produce N records to a dedicated smoke topic and validate
//                  that every one of them was acknowledged with no errors,
//                  satisfying the "verified test link ... without packet
//                  drops" acceptance line for Task 2.1.
//
// Phase 2.2 replaces the smoke loop with the real Boost.Beast WebSocket
// ingester feeding simdjson-parsed TickData structs into the producer.

#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>

// Both Ubuntu (librdkafka-dev) and Homebrew install the C++ headers under a
// `librdkafka/` subdirectory of the include prefix that pkg-config exposes,
// so this prefixed form is the portable one.
#include <librdkafka/rdkafkacpp.h>

namespace chainguard {

constexpr const char* kVersion = "0.1.0";
constexpr const char* kDefaultBrokers = "localhost:9092";
constexpr const char* kSmokeTopic = "chainguard.smoke";
constexpr int kSmokeMessageCount = 10;
constexpr int kFlushTimeoutMs = 10'000;
constexpr int kMetadataTimeoutMs = 5'000;

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

void print_usage(const char* argv0) {
    std::cout << "Usage: " << argv0 << " [options]\n"
              << "  --brokers HOST:PORT[,HOST:PORT...]   Kafka bootstrap servers\n"
              << "                                       (default: " << kDefaultBrokers << ",\n"
              << "                                        env: KAFKA_BROKERS)\n"
              << "  --probe                              Verify broker connection via metadata\n"
              << "  --smoke                              Produce " << kSmokeMessageCount
              << " records to '" << kSmokeTopic << "' and\n"
              << "                                       verify zero delivery failures\n"
              << "  --version                            Print version and exit\n"
              << "  -h, --help                           Print this help and exit\n";
}

}  // namespace chainguard

int main(int argc, char** argv) {
    using namespace chainguard;

    std::string brokers = kDefaultBrokers;
    if (const char* env = std::getenv("KAFKA_BROKERS"); env && *env) {
        brokers = env;
    }

    enum class Mode { Default, Probe, Smoke };
    Mode mode = Mode::Default;

    for (int i = 1; i < argc; ++i) {
        const std::string_view arg = argv[i];
        if (arg == "--brokers" && i + 1 < argc) {
            brokers = argv[++i];
        } else if (arg == "--probe") {
            mode = Mode::Probe;
        } else if (arg == "--smoke") {
            mode = Mode::Smoke;
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
        case Mode::Default:
            // No args: build smoke-test (used by CI). Must not contact Kafka.
            std::cout << "chainguard " << kVersion << " — Phase 2.1 build OK\n"
                      << "  Run with --probe or --smoke against a running broker.\n"
                      << "  Default brokers: " << brokers << '\n';
            return EXIT_SUCCESS;
    }
    return EXIT_SUCCESS;
}

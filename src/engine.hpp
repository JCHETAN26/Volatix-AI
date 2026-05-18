// ChainGuard-Core — feature engine pipeline.
//
// Phase 2.3. Threads:
//   * Producer (WebSocket) — parses ticks and pushes into the SPSC ring.
//   * Consumer (features)  — pops ticks, updates OFI / RV kernels, and
//                            every N ticks emits a FeatureFrame to the
//                            `financial-features` Kafka topic.
//
// The hot path (consumer side) is mutex-free and allocation-free. Counters
// are read with relaxed atomics so a reporter thread can sample telemetry
// without slowing the pipeline.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace chainguard {

struct EngineConfig {
    std::string ws_url;
    std::string brokers;
    std::string topic;
    std::int64_t ofi_bucket_width_ns;  // total OFI window = 16 * this
    std::size_t rv_samples;            // number of returns in the RV window
    std::uint32_t frame_interval_ticks;
};

// Runs the engine until SIGINT/SIGTERM. Returns EXIT_SUCCESS on clean
// shutdown, EXIT_FAILURE on a fatal producer or WebSocket error.
int run_engine(const EngineConfig& cfg);

// Microbenchmark: feeds `prefill_ticks` synthetic trades into the OFI / RV
// kernels to warm them, then times `frame_iterations` invocations of the
// feature-frame computation (kernel reads + memcpy serialize). Fails when
// the median frame-generation latency exceeds 50µs — the Phase 2.3
// acceptance bar.
int run_feature_bench(int prefill_ticks, int frame_iterations);

}  // namespace chainguard

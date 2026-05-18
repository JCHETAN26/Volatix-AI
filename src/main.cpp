// ChainGuard-Core — Ingestion & Feature Engineering Engine
//
// Phase 0 placeholder. Compiles cleanly under -Wall -Wextra -Wpedantic -Werror
// so cpp-ci (Phase 0.2) has a real target to build. Phase 2 replaces this
// entry point with the full WebSocket → simdjson → lock-free ring → Kafka
// pipeline implemented in src/core_engine.cpp.

#include <cstdlib>
#include <iostream>

namespace chainguard {

constexpr const char* kVersion = "0.1.0";

int run() {
    std::cout << "chainguard " << kVersion << " — Phase 0 scaffold OK\n";
    return EXIT_SUCCESS;
}

}  // namespace chainguard

int main() {
    return chainguard::run();
}

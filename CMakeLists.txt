cmake_minimum_required(VERSION 3.22)

project(chainguard
    VERSION 0.1.0
    DESCRIPTION "ChainGuard-Core low-latency streaming feature engine"
    LANGUAGES CXX
)

# --- Standards & flags -----------------------------------------------------
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile_commands.json for clangd / static analysis.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Default to Release for the demo binary; override with -DCMAKE_BUILD_TYPE=Debug.
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Zero-warning enforcement (required by Phase 0.2 cpp-ci).
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# --- System dependencies ---------------------------------------------------
# Threads — needed by the Kafka producer and (Phase 2.2) Boost.Asio.
find_package(Threads REQUIRED)

# OpenSSL — required by librdkafka's TLS code path; tracked here so a future
# move from PLAINTEXT to TLS brokers is a config flip, not a build flip.
find_package(OpenSSL REQUIRED)

# librdkafka (C++ wrapper) — discovered via pkg-config so we pick up the
# distro package (Ubuntu apt librdkafka-dev, Homebrew librdkafka).
find_package(PkgConfig REQUIRED)
pkg_check_modules(RDKAFKAPP REQUIRED IMPORTED_TARGET rdkafka++)

# --- Subdirectories --------------------------------------------------------
add_subdirectory(src)

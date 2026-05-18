# --- src/CMakeLists.txt ---------------------------------------------------
# Phase 2.1: Kafka producer entry point.
# Phase 2.2 will add Boost.Asio/Beast + simdjson and the WebSocket ingester.
# Phase 2.3 will add the lock-free ring buffer + OFI/Realized-Volatility
# feature kernels.
# --------------------------------------------------------------------------

add_executable(chainguard
    main.cpp
)

target_compile_features(chainguard PRIVATE cxx_std_20)

target_link_libraries(chainguard PRIVATE
    Threads::Threads
    OpenSSL::SSL
    OpenSSL::Crypto
    PkgConfig::RDKAFKAPP
)

set_target_properties(chainguard PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# --- src/CMakeLists.txt ---------------------------------------------------
# Phase 2.2: adds the WebSocket ingest path (Boost.Beast) and SIMD JSON
# parsing (simdjson). Phase 2.3 will add the lock-free ring buffer + the
# Order Flow Imbalance / Realized Volatility kernels.
# --------------------------------------------------------------------------

add_executable(chainguard
    main.cpp
    tick_parser.cpp
    ws_client.cpp
)

target_compile_features(chainguard PRIVATE cxx_std_20)

target_include_directories(chainguard PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(chainguard PRIVATE
    Threads::Threads
    OpenSSL::SSL
    OpenSSL::Crypto
    PkgConfig::RDKAFKAPP
    PkgConfig::SIMDJSON
    Boost::headers
    Boost::system
)

set_target_properties(chainguard PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# --- src/CMakeLists.txt ---------------------------------------------------
# Phase 0: minimal target so cpp-ci has something real to compile.
# Phase 2 will extend this with librdkafka, simdjson, Boost.Asio/Beast, and
# the lock-free feature store sources.
# --------------------------------------------------------------------------

add_executable(chainguard
    main.cpp
)

target_compile_features(chainguard PRIVATE cxx_std_20)

# Threads will be needed by the producer + WebSocket clients in Phase 2.
find_package(Threads REQUIRED)
target_link_libraries(chainguard PRIVATE Threads::Threads)

set_target_properties(chainguard PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

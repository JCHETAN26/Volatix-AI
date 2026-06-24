# --- src/CMakeLists.txt ---------------------------------------------------
# Phase 2.3: completes the C++ engine — adds the SPSC lock-free ring,
# OFI / Realized-Volatility kernels, FeatureFrame serializer, and the
# engine pipeline that broadcasts to the `financial-features` Kafka topic.
# --------------------------------------------------------------------------

add_executable(volatix
    main.cpp
    engine.cpp
    features.cpp
    tick_parser.cpp
    ws_client.cpp
)

target_compile_features(volatix PRIVATE cxx_std_20)

target_include_directories(volatix PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(volatix PRIVATE
    Threads::Threads
    OpenSSL::SSL
    OpenSSL::Crypto
    PkgConfig::RDKAFKAPP
    PkgConfig::SIMDJSON
    Boost::headers
    Boost::system
)

set_target_properties(volatix PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

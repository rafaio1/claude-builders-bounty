#pragma once

#include <cstdint>
#include <string>

namespace trial {
namespace config {

enum class Precision : uint8_t {
    F32 = 0,
    F64 = 1,
    MIXED = 2,
};

enum class Backend : uint8_t {
    CPU_SCALAR = 0,
    CPU_SSE = 1,
    CPU_AVX2 = 2,
    CPU_AVX512 = 3,
    CUDA = 4,
    VULKAN = 5,
};

enum class Logger : uint8_t {
    NONE = 0,
    CONSOLE = 1,
    FILE = 2,
    REMOTE = 3,
};

struct EngineConfig {
    std::string     app_name            = "Trial Engine";
    std::string     version             = "0.1.0";
    Precision       precision           = Precision::MIXED;
    Backend         backend             = Backend::CPU_AVX2;
    Logger          logger              = Logger::CONSOLE;
    bool            enable_profiling    = true;
    bool            enable_validation   = false;
    bool            enable_tracy        = false;

    uint32_t        max_entities        = 65536;
    uint32_t        max_components      = 64;
    uint32_t        max_systems         = 128;

    uint32_t        worker_threads      = 4;
    uint32_t        fixed_timestep_hz   = 60;
    uint32_t        max_substeps        = 8;

    double          gravity             = -9.81;
    double          sleep_threshold     = 0.01;
    uint32_t        solver_iterations   = 10;

    uint32_t        window_width        = 1920;
    uint32_t        window_height       = 1080;
    bool            vsync               = true;
    uint32_t        target_fps          = 144;

    size_t          allocator_pool_size = 1024ULL * 1024 * 1024;
    size_t          stack_size          = 1024ULL * 1024 * 8;
};

}
}

#pragma once

#include "../engine/core/math.hpp"
#include "../engine/core/types.hpp"
#include "camera.hpp"

#include <vector>
#include <memory>
#include <cstdint>
#include <string>

namespace trial {
namespace render {

enum class ShaderStage : uint8_t {
    VERTEX   = 0,
    FRAGMENT = 1,
    COMPUTE  = 2,
    GEOMETRY = 3,
    TESS_EVAL = 4,
    TESS_CONTROL = 5,
    RAYGEN   = 6,
    MISS     = 7,
    CLOSEST_HIT = 8,
};

enum class PrimitiveType : uint8_t {
    POINTS      = 0,
    LINES       = 1,
    TRIANGLES   = 2,
    LINE_STRIP  = 3,
    TRIANGLE_STRIP = 4,
    PATCHES     = 5,
};

struct ShaderModule {
    std::string  entry_point = "main";
    ShaderStage  stage       = ShaderStage::VERTEX;
    std::vector<uint32_t> spirv;
    bool         compiled    = false;
};

struct PipelineConfig {
    std::string               name           = "default";
    ShaderModule              vertex_shader;
    ShaderModule              fragment_shader;
    PrimitiveType             primitives     = PrimitiveType::TRIANGLES;
    bool                      depth_test     = true;
    bool                      depth_write    = true;
    bool                      cull_backfaces = true;
    bool                      wireframe      = false;
    uint32_t                  sample_count   = 4;
    bool                      blending       = false;
};

class Pipeline {
public:
    explicit Pipeline(const PipelineConfig& cfg) : config_(cfg) {}
    virtual ~Pipeline() = default;

    const PipelineConfig& config() const noexcept { return config_; }

    virtual bool compile()   { compiled_ = true; return true; }
    virtual void bind()      {  }
    virtual void draw(uint32_t vertices, uint32_t instances) {
        (void)vertices; (void)instances;
    }

    bool is_compiled() const noexcept { return compiled_; }

private:
    PipelineConfig config_;
    bool compiled_ = false;
};

}
}

#include "engine.h"
#include "engine/core/ecs.hpp"
#include "engine/dynamics/rigidbody.hpp"
#include "engine/collision/collision.hpp"
#include "render/camera.hpp"
#include "math_util.hpp"

#include <iostream>
#include <format>
#include <string>

namespace trial {
namespace wat {

struct Why {
    std::string message;
    int         severity;
    bool        panic;
};

void why_does_this_exist() {
    Why w{
        .message  = "this file compiles and links into the engine for no reason",
        .severity = 42,
        .panic    = false,
    };

    auto cfg = config::EngineConfig{};
    std::cout << std::format("[wat] {} (severity: {})\n", w.message, w.severity);
    std::cout << std::format("[wat] engine config: {} v{}\n",
        cfg.app_name, cfg.version);

    auto cam = render::Camera({0, 2, 5}, {0, 0, 0}, 70.0);
    auto vp = cam.view_projection();

    auto vec = core::Vec3{1, 2, 3};
    auto len = math_utils::fast_inv_sqrt(vec.length_sq());
    (void)len;

    std::cout << std::format("[wat] camera VP[0][0] = {:.4f}\n", vp.m[0]);
    std::cout << std::format("[wat] everything is fine\n");
}

struct OrphanData {
    uint64_t    id;
    std::string name;
    float       chaos_factor;
};

static OrphanData global_orphan{42, "wat.cpp", 0.99f};

}
}

void __attribute__((weak)) invoke_wat() {
    trial::wat::why_does_this_exist();
}

#include "engine.h"
#include "engine/core/types.hpp"
#include "engine/core/math.hpp"

namespace trial {

core::Vec3 calculate_center_of_mass(std::span<const core::Vec3> points) {
    core::Vec3 sum;
    for (const auto& p : points) {
        sum = sum + p;
    }
    return sum * (1.0 / static_cast<double>(std::max(points.size(), size_t{1})));
}

std::string version_string() {
    return std::string{"Trial Engine v"} + config::EngineConfig{}.version;
}

}

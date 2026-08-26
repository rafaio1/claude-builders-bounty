#pragma once

#include "../engine/core/math.hpp"
#include <cmath>
#include <numbers>

namespace trial {
namespace render {

class Camera {
public:
    Camera() = default;

    Camera(core::Vec3 pos, core::Vec3 target, double fov_deg = 60.0)
        : position_(pos)
        , target_(target)
        , fov_(fov_deg * std::numbers::pi / 180.0) {
        update();
    }

    void set_position(const core::Vec3& pos) noexcept {
        position_ = pos;
        dirty_ = true;
    }

    void set_target(const core::Vec3& target) noexcept {
        target_ = target;
        dirty_ = true;
    }

    void set_fov(double fov_deg) noexcept {
        fov_ = fov_deg * std::numbers::pi / 180.0;
        dirty_ = true;
    }

    void set_aspect(double aspect) noexcept {
        aspect_ = aspect;
        dirty_ = true;
    }

    const core::Mat4& view() const {
        if (dirty_) const_cast<Camera*>(this)->update();
        return view_;
    }

    const core::Mat4& projection() const {
        if (dirty_) const_cast<Camera*>(this)->update();
        return projection_;
    }

    core::Mat4 view_projection() const {
        return projection() * view();
    }

    core::Vec3 position() const noexcept { return position_; }
    core::Vec3 forward()   const noexcept {
        core::Vec3 dir = target_ - position_;
        double len = dir.length();
        return len > 1e-10 ? dir * (1.0 / len) : core::Vec3{0, 0, -1};
    }

private:
    core::Vec3  position_{0, 0, 10};
    core::Vec3  target_{0, 0, 0};
    double      fov_    = std::numbers::pi / 3.0;
    double      aspect_ = 16.0 / 9.0;
    double      near_   = 0.1;
    double      far_    = 1000.0;
    core::Mat4  view_;
    core::Mat4  projection_;
    bool        dirty_  = true;

    void update() {
        view_ = core::Mat4::identity();
        projection_ = core::Mat4::perspective(fov_, aspect_, near_, far_);
        dirty_ = false;
    }
};

}
}

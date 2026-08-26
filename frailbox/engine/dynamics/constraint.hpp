#pragma once

#include "../core/math.hpp"
#include "rigidbody.hpp"

#include <vector>
#include <memory>
#include <cmath>

namespace trial {
namespace dynamics {

enum class ConstraintType : uint8_t {
    FIXED        = 0,
    HINGE        = 1,
    SPHERICAL    = 2,
    SLIDER       = 3,
    SPRING       = 4,
    DISTANCE     = 5,
    WELD         = 6,
    SIX_DOF      = 7,
};

struct ConstraintConfig {
    ConstraintType type           = ConstraintType::FIXED;
    double         damping        = 0.1;
    double         stiffness      = 1000.0;
    double         max_force      = 1e10;
    double         break_impulse  = 1e10;
    core::Vec3     pivot_a;
    core::Vec3     pivot_b;
    core::Vec3     axis_a         = core::Vec3{1, 0, 0};
    core::Vec3     axis_b         = core::Vec3{1, 0, 0};
    double         min_distance   = 0.0;
    double         max_distance   = 1.0;
    bool           enable_limits  = false;
    bool           enable_motor   = false;
    double         motor_speed    = 0.0;
    double         motor_force    = 0.0;
};

class Constraint {
public:
    Constraint() = default;
    Constraint(RigidBody* body_a, RigidBody* body_b, const ConstraintConfig& cfg)
        : body_a_(body_a), body_b_(body_b), config_(cfg) {}

    RigidBody* body_a() const noexcept { return body_a_; }
    void set_body_a(RigidBody* b) noexcept { body_a_ = b; }

    RigidBody* body_b() const noexcept { return body_b_; }
    void set_body_b(RigidBody* b) noexcept { body_b_ = b; }

    const ConstraintConfig& config() const noexcept { return config_; }
    ConstraintConfig& config() noexcept { return config_; }

    bool is_broken() const noexcept { return broken_; }
    void set_broken(bool b) noexcept { broken_ = b; }

    double applied_impulse() const noexcept { return applied_impulse_; }
    void accumulate_impulse(double impulse) noexcept { applied_impulse_ += impulse; }

private:
    RigidBody*       body_a_         = nullptr;
    RigidBody*       body_b_         = nullptr;
    ConstraintConfig config_{};
    double           applied_impulse_ = 0.0;
    bool             broken_         = false;
};

class Spring {
public:
    Spring(RigidBody* body_a, RigidBody* body_b,
           double stiffness, double damping)
        : body_a_(body_a), body_b_(body_b)
        , stiffness_(stiffness), damping_(damping) {}

    core::Vec3 compute_force() const {
        if (!body_a_ || !body_b_) return {};
        core::Vec3 delta = body_a_->state().position - body_b_->state().position;
        double dist = delta.length();
        if (dist < 1e-8) return {};
        core::Vec3 dir = delta * (1.0 / dist);
        core::Vec3 rel_vel = body_a_->state().linear_velocity -
                             body_b_->state().linear_velocity;
        double force_mag = -stiffness_ * (dist - rest_length_) -
                           damping_ * rel_vel.dot(dir);
        return dir * force_mag;
    }

    void set_rest_length(double l) noexcept { rest_length_ = l; }
    double rest_length() const noexcept { return rest_length_; }

private:
    RigidBody* body_a_      = nullptr;
    RigidBody* body_b_      = nullptr;
    double     stiffness_   = 100.0;
    double     damping_     = 1.0;
    double     rest_length_ = 1.0;
};

class ConstraintManager {
public:
    Constraint* add(RigidBody* a, RigidBody* b, const ConstraintConfig& cfg) {
        auto constraint = std::make_unique<Constraint>(a, b, cfg);
        auto* ptr = constraint.get();
        constraints_.push_back(std::move(constraint));
        return ptr;
    }

    void remove(size_t index) {
        if (index < constraints_.size()) {
            constraints_.erase(constraints_.begin() +
                static_cast<ptrdiff_t>(index));
        }
    }

    Constraint* get(size_t index) {
        return (index < constraints_.size()) ? constraints_[index].get() : nullptr;
    }

    size_t count() const noexcept { return constraints_.size(); }

    const auto& all() const noexcept { return constraints_; }

private:
    std::vector<std::unique_ptr<Constraint>> constraints_;
};

}
}

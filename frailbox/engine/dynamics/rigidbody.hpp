#pragma once

#include "../core/math.hpp"
#include "../core/types.hpp"

#include <vector>
#include <memory>
#include <mutex>

namespace trial {
namespace dynamics {

enum class BodyType : uint8_t {
    STATIC      = 0,
    DYNAMIC     = 1,
    KINEMATIC   = 2,
    TRIGGER     = 3,
};

enum class Shape : uint8_t {
    SPHERE      = 0,
    BOX         = 1,
    CAPSULE     = 2,
    PLANE       = 3,
    MESH        = 4,
    HEIGHTFIELD = 5,
};

struct MassProperties {
    double mass        = 1.0;
    double inv_mass    = 1.0;
    core::Vec3 inertia;
    core::Vec3 inv_inertia;
};

struct BodyState {
    core::Vec3  position;
    core::Quat  orientation;
    core::Vec3  linear_velocity;
    core::Vec3  angular_velocity;
    core::Vec3  force_accumulator;
    core::Vec3  torque_accumulator;
};

struct CollisionShape {
    Shape       type        = Shape::BOX;
    core::Vec3  half_extents{1, 1, 1};
    double      radius      = 1.0;
    double      height      = 2.0;
    uint64_t    mesh_id     = 0;
};

class RigidBody {
public:
    RigidBody() = default;
    explicit RigidBody(core::EntityID entity)
        : entity_(entity) {}

    core::EntityID entity() const noexcept { return entity_; }
    void set_entity(core::EntityID id) noexcept { entity_ = id; }

    BodyType type() const noexcept { return type_; }
    void set_type(BodyType t) noexcept { type_ = t; }

    const BodyState& state() const noexcept { return state_; }
    BodyState& state() noexcept { return state_; }

    void set_transform(const core::Vec3& pos, const core::Quat& orient) noexcept {
        state_.position = pos;
        state_.orientation = orient;
    }

    const MassProperties& mass() const noexcept { return mass_; }
    void set_mass(double m) noexcept {
        mass_.mass = m;
        mass_.inv_mass = m > 0 ? 1.0 / m : 0.0;
    }

    const CollisionShape& shape() const noexcept { return shape_; }
    void set_shape(const CollisionShape& s) noexcept { shape_ = s; }

    void apply_force(const core::Vec3& f) noexcept {
        state_.force_accumulator = state_.force_accumulator + f;
    }
    void apply_torque(const core::Vec3& t) noexcept {
        state_.torque_accumulator = state_.torque_accumulator + t;
    }
    void clear_forces() noexcept {
        state_.force_accumulator = core::Vec3{};
        state_.torque_accumulator = core::Vec3{};
    }

    bool is_sleeping() const noexcept { return sleeping_; }
    void set_sleeping(bool s) noexcept { sleeping_ = s; }

    void* user_data() const noexcept { return user_data_; }
    void set_user_data(void* d) noexcept { user_data_ = d; }

private:
    core::EntityID  entity_     = core::INVALID_ENTITY;
    BodyType        type_       = BodyType::DYNAMIC;
    BodyState       state_{};
    MassProperties  mass_{};
    CollisionShape  shape_{};
    bool            sleeping_   = false;
    void*           user_data_  = nullptr;
};

class BodyManager {
public:
    BodyManager() { bodies_.reserve(4096); }

    RigidBody* create() {
        auto body = std::make_unique<RigidBody>();
        auto* ptr = body.get();
        bodies_.push_back(std::move(body));
        return ptr;
    }

    void destroy(size_t index) {
        if (index < bodies_.size()) {
            bodies_.erase(bodies_.begin() + static_cast<ptrdiff_t>(index));
        }
    }

    RigidBody* get(size_t index) {
        return (index < bodies_.size()) ? bodies_[index].get() : nullptr;
    }

    size_t count() const noexcept { return bodies_.size(); }
    void clear() noexcept { bodies_.clear(); }

private:
    std::vector<std::unique_ptr<RigidBody>> bodies_;
    std::mutex mutex_;
};

}
}

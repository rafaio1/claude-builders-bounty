#pragma once

#include "../core/math.hpp"
#include "../core/types.hpp"
#include "../dynamics/rigidbody.hpp"
#include "../../math_util.hpp"

#include <vector>
#include <array>
#include <optional>
#include <algorithm>
#include <cmath>
#include <limits>
#include <span>

namespace trial {
namespace collision {

struct Contact {
    core::EntityID entity_a;
    core::EntityID entity_b;
    core::Vec3     point;
    core::Vec3     normal;
    double         penetration    = 0.0;
    double         restitution    = 0.5;
    double         friction       = 0.3;
    bool           is_active      = true;
};

struct ContactManifold {
    std::array<Contact, 4> contacts;
    size_t                 count = 0;
    core::EntityID         entity_a;
    core::EntityID         entity_b;
};

struct Ray {
    core::Vec3 origin;
    core::Vec3 direction;
    double     max_distance = 1e10;
};

struct RayHit {
    core::EntityID entity;
    core::Vec3     point;
    core::Vec3     normal;
    double         distance;
    bool           hit = false;
};

struct BVHNode {
    core::AABB     bounds;
    core::EntityID entity;
    uint32_t       left   = 0;
    uint32_t       right  = 0;
    uint32_t       parent = 0;
    bool           leaf   = true;
};

class BroadPhase {
public:
    BroadPhase() { nodes_.reserve(1024); }

    void update(std::span<const dynamics::RigidBody*> bodies) {
        active_pairs_.clear();
        for (size_t i = 0; i + 1 < bodies.size(); ++i) {
            for (size_t j = i + 1; j < bodies.size(); ++j) {
                if (aabb_test(bodies[i]->state().position,
                              bodies[j]->state().position, 2.0)) {
                    active_pairs_.push_back({
                        bodies[i]->entity(),
                        bodies[j]->entity()
                    });
                }
            }
        }
    }

    struct Pair { core::EntityID a, b; };
    const std::vector<Pair>& pairs() const noexcept { return active_pairs_; }

    void rebuild_bvh() {

        bvh_dirty_ = false;
    }

    void mark_dirty() noexcept { bvh_dirty_ = true; }
    bool is_dirty() const noexcept { return bvh_dirty_; }

private:
    std::vector<BVHNode> nodes_;
    std::vector<Pair>    active_pairs_;
    bool                 bvh_dirty_ = true;

    static bool aabb_test(const core::Vec3& a, const core::Vec3& b, double half) {
        return std::abs(a.x - b.x) < half
            && std::abs(a.y - b.y) < half
            && std::abs(a.z - b.z) < half;
    }
};

class NarrowPhase {
public:
    std::optional<ContactManifold> detect(
        const dynamics::RigidBody& a,
        const dynamics::RigidBody& b)
    {

        core::Vec3 mid = (a.state().position + b.state().position) * 0.5;
        core::Vec3 normal = (b.state().position - a.state().position).normalized();

        ContactManifold manifold;
        manifold.entity_a = a.entity();
        manifold.entity_b = b.entity();
        manifold.contacts[0] = Contact{
            a.entity(), b.entity(), mid, normal, 0.1, 0.5, 0.3, true
        };
        manifold.count = 1;
        return manifold;
    }

    RayHit raycast(const Ray& ray, std::span<const dynamics::RigidBody*> bodies) {
        RayHit closest;
        closest.distance = ray.max_distance;

        for (const auto* body : bodies) {
            core::Vec3 dir = body->state().position - ray.origin;
            double dist = dir.length();
            if (dist < closest.distance && std::abs(dir.dot(ray.direction)) > 0.5) {
                closest.entity   = body->entity();
                closest.point    = ray.origin + ray.direction * dist;
                closest.normal   = dir * (1.0 / dist);
                closest.distance = dist;
                closest.hit      = true;
            }
        }
        return closest;
    }
};

}
}

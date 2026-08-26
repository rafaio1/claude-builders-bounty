#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>
#include <array>
#include <functional>
#include <memory>
#include <span>
#include <optional>
#include <variant>

namespace trial {
namespace core {

using EntityID       = uint64_t;
using ComponentID    = uint32_t;
using SystemID       = uint32_t;
using ArchetypeID    = uint64_t;
using ChunkID        = uint32_t;
using Generation     = uint32_t;

inline constexpr EntityID INVALID_ENTITY     = ~EntityID{0};

using EntityFlags    = uint32_t;
inline constexpr EntityFlags ENTITY_NONE     = 0;
inline constexpr EntityFlags ENTITY_ACTIVE   = 1 << 0;
inline constexpr EntityFlags ENTITY_VISIBLE  = 1 << 1;
inline constexpr EntityFlags ENTITY_STATIC   = 1 << 2;
inline constexpr EntityFlags ENTITY_SLEEPING = 1 << 3;
inline constexpr EntityFlags ENTITY_TRIGGER  = 1 << 4;

struct Transform {
    double x = 0, y = 0, z = 0;
    double rx = 0, ry = 0, rz = 0, rw = 1;
    double sx = 1, sy = 1, sz = 1;
};

struct Velocity {
    double vx = 0, vy = 0, vz = 0;
    double wx = 0, wy = 0, wz = 0;
};

struct AABB {
    double min_x = 0, min_y = 0, min_z = 0;
    double max_x = 0, max_y = 0, max_z = 0;
};

struct Tag {
    std::string name;
    uint32_t    layer = 0;
};

struct EntityRecord {
    EntityID    id          = INVALID_ENTITY;
    Generation  gen         = 0;
    EntityFlags flags       = ENTITY_NONE;
    ArchetypeID archetype   = 0;

    bool valid() const noexcept { return id != INVALID_ENTITY; }
};

template <typename T, size_t N = 64>
using ComponentPool = std::vector<T>;

template <typename... Ts>
struct ComponentGroup {};

using SystemFunc = std::function<void(float dt, std::span<const EntityID>)>;

struct SystemDesc {
    SystemID    id;
    std::string name;
    uint32_t    priority;
    bool        enabled;
    SystemFunc  func;
};

}
}

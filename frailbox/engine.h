#pragma once

#include "engine_config.hpp"

#include <memory>
#include <vector>
#include <functional>
#include <string_view>

namespace trial {

namespace core {
    class EntityManager;
    class ComponentManager;
    class SystemManager;
    struct Transform;
}

namespace dynamics {
    class RigidBody;
    class Constraint;
    class Spring;
    class SimulationIsland;
}

namespace collision {
    class BroadPhase;
    class NarrowPhase;
    struct ContactManifold;
}

class Engine {
public:
    explicit Engine(const config::EngineConfig& cfg);
    ~Engine();

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine(Engine&&) = delete;
    Engine& operator=(Engine&&) = delete;

    bool initialize();
    void shutdown();
    bool is_initialized() const noexcept;

    int run();
    void stop() noexcept;
    void step(double dt);

    core::EntityManager&     entities() noexcept;
    const core::EntityManager& entities() const noexcept;

    dynamics::RigidBody*     create_body();
    void                     destroy_body(uint64_t id);

    collision::BroadPhase&   broad_phase() noexcept;
    collision::NarrowPhase&  narrow_phase() noexcept;

    const config::EngineConfig& config() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

std::unique_ptr<Engine> create_engine(const config::EngineConfig& cfg);

}

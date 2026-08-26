#include "../engine.h"
#include "../engine_config.hpp"
#include "core/ecs.hpp"
#include "core/math.hpp"
#include "dynamics/rigidbody.hpp"
#include "dynamics/constraint.hpp"
#include "collision/collision.hpp"
#include "../render/camera.hpp"
#include "../render/pipeline.hpp"

#include <iostream>
#include <format>
#include <chrono>
#include <thread>
#include <csignal>
#include <memory>
#include <cstdlib>

extern void invoke_wat();

namespace trial {

struct Engine::Impl {
    config::EngineConfig   config;
    bool                   initialized = false;
    bool                   running     = false;

    core::EntityManager    entity_mgr;
    core::ComponentManager component_mgr;
    core::SystemManager    system_mgr;

    dynamics::BodyManager       body_mgr;
    dynamics::ConstraintManager constraint_mgr;

    collision::BroadPhase  broad_phase;
    collision::NarrowPhase narrow_phase;

    render::Camera  camera{{0, 2, 10}, {0, 0, 0}, 60.0};
    render::Pipeline render_pipeline{render::PipelineConfig{
        .name = "trial_forward",
        .vertex_shader = render::ShaderModule{},
        .fragment_shader = render::ShaderModule{},
        .primitives = render::PrimitiveType::TRIANGLES,
    }};
};

Engine::Engine(const config::EngineConfig& cfg)
    : impl_(std::make_unique<Impl>()) {
    impl_->config = cfg;
}

Engine::~Engine() = default;

bool Engine::initialize() {
    std::cout << std::format("[engine] {} v{} initializing...\n",
        impl_->config.app_name, impl_->config.version);
    std::cout << std::format("[engine] backend={} precision={} workers={}\n",
        static_cast<int>(impl_->config.backend),
        static_cast<int>(impl_->config.precision),
        impl_->config.worker_threads);

    impl_->entity_mgr = core::EntityManager(impl_->config.max_entities);
    impl_->component_mgr.register_component<core::Transform>();
    impl_->component_mgr.register_component<core::Velocity>();
    impl_->component_mgr.register_component<core::AABB>();
    impl_->component_mgr.register_component<core::Tag>();

    impl_->system_mgr.add_system({
        1, "physics", 0, true,
        [](float, std::span<const core::EntityID>) {  }
    });
    impl_->system_mgr.add_system({
        2, "collision", 1, true,
        [](float, std::span<const core::EntityID>) {  }
    });
    impl_->system_mgr.add_system({
        3, "render", 2, true,
        [](float, std::span<const core::EntityID>) {  }
    });

    for (int i = 0; i < 3; ++i) {
        auto id = impl_->entity_mgr.create();
        impl_->component_mgr.add(id, core::Transform{
            static_cast<double>(i * 2), 0.0, 0.0
        });
        impl_->component_mgr.add(id, core::Velocity{});
        impl_->component_mgr.add(id, core::Tag{"test_entity", 1});

        auto* body = impl_->body_mgr.create();
        body->set_entity(id);
        body->set_type(dynamics::BodyType::DYNAMIC);
        body->set_transform({static_cast<double>(i * 2), 0, 0}, {});
        body->set_shape({dynamics::Shape::BOX, {0.5, 0.5, 0.5}});
    }

    impl_->render_pipeline.compile();

    invoke_wat();

    impl_->initialized = true;
    std::cout << std::format("[engine] initialization complete ({} entities)\n",
        impl_->entity_mgr.count());
    return true;
}

void Engine::shutdown() {
    std::cout << "[engine] shutting down...\n";
    impl_->body_mgr.clear();
    impl_->initialized = false;
    std::cout << "[engine] shutdown complete\n";
}

bool Engine::is_initialized() const noexcept {
    return impl_->initialized;
}

int Engine::run() {
    if (!impl_->initialized && !initialize()) {
        std::cerr << "[engine] failed to initialize\n";
        return 1;
    }

    impl_->running = true;

    using clock = std::chrono::steady_clock;
    auto last = clock::now();

    std::cout << "[engine] entering main loop\n";

    int frames = 0;
    while (impl_->running) {
        auto now = clock::now();
        double dt = std::chrono::duration<double>(now - last).count();
        last = now;

        step(dt);

        ++frames;

        std::this_thread::sleep_for(std::chrono::milliseconds(16));
    }

    std::cout << std::format("[engine] exiting main loop ({} steps)\n", frames);
    return 0;
}

void Engine::stop() noexcept {
    impl_->running = false;
}

void Engine::step(double dt) {

    auto all = impl_->entity_mgr.query(0);

    impl_->system_mgr.run(static_cast<float>(dt), all);

    std::vector<const dynamics::RigidBody*> bodies;
    for (size_t i = 0; i < impl_->body_mgr.count(); ++i) {
        bodies.push_back(impl_->body_mgr.get(i));
    }
    impl_->broad_phase.update(bodies);

    (void)impl_->camera;
}

core::EntityManager& Engine::entities() noexcept { return impl_->entity_mgr; }
const core::EntityManager& Engine::entities() const noexcept { return impl_->entity_mgr; }

dynamics::RigidBody* Engine::create_body() {
    return impl_->body_mgr.create();
}

void Engine::destroy_body(uint64_t id) {
    impl_->body_mgr.destroy(static_cast<size_t>(id));
}

collision::BroadPhase& Engine::broad_phase() noexcept { return impl_->broad_phase; }
collision::NarrowPhase& Engine::narrow_phase() noexcept { return impl_->narrow_phase; }

const config::EngineConfig& Engine::config() const noexcept { return impl_->config; }

std::unique_ptr<Engine> create_engine(const config::EngineConfig& cfg) {
    return std::make_unique<Engine>(cfg);
}

}

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;

    trial::config::EngineConfig cfg;
    cfg.app_name = "Trial Engine";
    cfg.enable_profiling = true;

    auto engine = trial::create_engine(cfg);
    int result = engine->run();

    std::cout << "[engine] goodbye\n";
    return result;
}

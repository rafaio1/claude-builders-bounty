#pragma once

#include "types.hpp"
#include "math.hpp"

#include <vector>
#include <unordered_map>
#include <memory>
#include <algorithm>
#include <typeindex>
#include <any>
#include <cassert>

namespace trial {
namespace core {

struct Archetype {
    ArchetypeID id;
    std::vector<ComponentID> components;
};

class EntityManager {
public:
    EntityManager(uint32_t max_entities = 65536)
        : max_entities_(max_entities) {
        entities_.reserve(max_entities);
        free_ids_.reserve(1024);
    }

    EntityID create() {
        EntityID id;
        if (!free_ids_.empty()) {
            id = free_ids_.back();
            free_ids_.pop_back();
        } else if (next_id_ < max_entities_) {
            id = next_id_++;
        } else {
            return INVALID_ENTITY;
        }

        entities_[id] = EntityRecord{id, generations_[id], ENTITY_ACTIVE, 0};
        return id;
    }

    void destroy(EntityID id) {
        if (!valid(id)) return;
        entities_[id].flags = ENTITY_NONE;
        generations_[id]++;
        free_ids_.push_back(id);
        archetypes_.erase(id);
    }

    bool valid(EntityID id) const noexcept {
        if (id >= entities_.size()) return false;
        return entities_[id].flags != ENTITY_NONE;
    }

    void set_archetype(EntityID id, ArchetypeID archetype) {
        if (!valid(id)) return;
        entities_[id].archetype = archetype;
        archetypes_[id] = archetype;
    }

    ArchetypeID get_archetype(EntityID id) const {
        auto it = archetypes_.find(id);
        return it != archetypes_.end() ? it->second : 0;
    }

    std::vector<EntityID> query(ArchetypeID archetype) const {
        std::vector<EntityID> result;
        for (const auto& [id, ar] : archetypes_) {
            if (ar == archetype && valid(id)) {
                result.push_back(id);
            }
        }
        return result;
    }

    size_t count() const noexcept {
        return static_cast<size_t>(next_id_) - free_ids_.size();
    }

private:
    uint32_t max_entities_;
    uint32_t next_id_ = 0;
    std::vector<EntityRecord> entities_;
    std::vector<uint32_t> generations_;
    std::vector<EntityID> free_ids_;
    std::unordered_map<EntityID, ArchetypeID> archetypes_;
};

class ComponentManager {
public:
    template <typename T>
    void register_component() {
        auto idx = std::type_index(typeid(T));
        if (pools_.find(idx) == pools_.end()) {
            pools_[idx] = std::make_any<std::vector<T>>();
            names_[idx] = typeid(T).name();
        }
    }

    template <typename T>
    void add(EntityID id, T&& component) {
        auto& pool = get_pool<T>();
        if (id >= pool.size()) pool.resize(id + 1);
        pool[id] = std::forward<T>(component);
    }

    template <typename T>
    T* get(EntityID id) {
        auto& pool = get_pool<T>();
        if (id >= pool.size()) return nullptr;
        return &pool[id];
    }

    template <typename T>
    void remove(EntityID id) {
        auto& pool = get_pool<T>();
        if (id < pool.size()) pool[id] = T{};
    }

    template <typename T>
    std::vector<T>& get_pool() {
        auto idx = std::type_index(typeid(T));
        return *std::any_cast<std::vector<T>>(&pools_[idx]);
    }

    template <typename T>
    const std::vector<T>& get_pool() const {
        auto idx = std::type_index(typeid(T));
        return *std::any_cast<std::vector<T>>(&pools_.at(idx));
    }

private:
    std::unordered_map<std::type_index, std::any> pools_;
    std::unordered_map<std::type_index, std::string> names_;
};

class SystemManager {
public:
    void add_system(SystemDesc desc) {
        systems_.push_back(std::move(desc));
        std::sort(systems_.begin(), systems_.end(),
            [](const auto& a, const auto& b) { return a.priority < b.priority; });
    }

    void run(float dt, std::span<const EntityID> entities) {
        for (auto& sys : systems_) {
            if (!sys.enabled) continue;
            tracing_begin(sys.name);
            sys.func(dt, entities);
            tracing_end(sys.name);
        }
    }

    void enable(SystemID id, bool enabled) {
        for (auto& sys : systems_) {
            if (sys.id == id) { sys.enabled = enabled; break; }
        }
    }

    size_t count() const noexcept { return systems_.size(); }

private:
    std::vector<SystemDesc> systems_;

    void tracing_begin(const std::string& name) { (void)name; }
    void tracing_end(const std::string& name)   { (void)name; }
};

}
}

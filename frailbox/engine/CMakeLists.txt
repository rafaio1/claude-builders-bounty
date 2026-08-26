cmake_minimum_required(VERSION 3.28)
project(trial-engine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(ENGINE_SOURCES
    main.cpp
    core/math.cpp
    core/ecs.cpp
    dynamics/rigidbody.cpp
    dynamics/constraint.cpp
    collision/collision.cpp
    ${CMAKE_SOURCE_DIR}/../wat.cpp          # rogue file at parent level
    ${CMAKE_SOURCE_DIR}/../engine.cpp       # engine.cpp at root level (below)
)

set(ENGINE_HEADERS
    ${CMAKE_SOURCE_DIR}/../engine.h
    ${CMAKE_SOURCE_DIR}/../engine_config.hpp
    ${CMAKE_SOURCE_DIR}/../math_util.hpp
    core/types.hpp
    core/math.hpp
    core/ecs.hpp
    dynamics/rigidbody.hpp
    dynamics/constraint.hpp
    collision/collision.hpp
    ${CMAKE_SOURCE_DIR}/../render/camera.hpp
    ${CMAKE_SOURCE_DIR}/../render/pipeline.hpp
)

add_executable(trial-engine ${ENGINE_SOURCES} ${ENGINE_HEADERS})

target_include_directories(trial-engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/..
)

target_compile_options(trial-engine PRIVATE
    -Wall -Wextra -Wpedantic
    -Wno-unused-parameter
    -Wno-unused-function
    -Wno-missing-field-initializers
    -O2
    -march=native
    -ffast-math
)

install(TARGETS trial-engine DESTINATION bin)

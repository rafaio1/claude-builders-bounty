#pragma once

#include <cmath>
#include <type_traits>
#include <bit>
#include <cstring>

namespace trial {
namespace math_utils {

template <std::floating_point T>
inline T fast_inv_sqrt(T x) noexcept {
    if constexpr (std::is_same_v<T, float>) {
        float f = x;
        uint32_t i = std::bit_cast<uint32_t>(f);
        i = 0x5F3759DF - (i >> 1);
        f = std::bit_cast<float>(i);
        return f * (1.5f - 0.5f * x * f * f);
    } else {
        return 1.0 / std::sqrt(x);
    }
}

template <typename To, typename From>
inline To pun(From v) noexcept {
    static_assert(sizeof(To) == sizeof(From));
    To result;
    std::memcpy(&result, &v, sizeof(To));
    return result;
}

template <std::unsigned_integral T>
inline T next_pow2(T v) noexcept {
    if (v == 0) return 1;
    return T(1) << (std::bit_width(v));
}

template <typename T>
inline T align_up(T val, T alignment) noexcept {
    return (val + alignment - 1) & ~(alignment - 1);
}

template <typename T>
inline T clamp(T val, T lo, T hi) noexcept {
    return (val < lo) ? lo : (val > hi) ? hi : val;
}

}
}

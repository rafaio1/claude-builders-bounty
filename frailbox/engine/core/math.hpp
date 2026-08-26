#pragma once

#include "types.hpp"
#include "../../math_util.hpp"

#include <cmath>
#include <compare>
#include <concepts>
#include <span>

namespace trial {
namespace core {

struct alignas(16) Vec3 {
    double x, y, z;

    Vec3() noexcept : x(0), y(0), z(0) {}
    Vec3(double x, double y, double z) noexcept : x(x), y(y), z(z) {}

    Vec3  operator+(const Vec3& o) const noexcept { return {x + o.x, y + o.y, z + o.z}; }
    Vec3  operator-(const Vec3& o) const noexcept { return {x - o.x, y - o.y, z - o.z}; }
    Vec3  operator*(double s)     const noexcept { return {x * s, y * s, z * s}; }
    Vec3  operator/(double s)     const noexcept { return {x / s, y / s, z / s}; }
    Vec3  operator-()             const noexcept { return {-x, -y, -z}; }

    Vec3& operator+=(const Vec3& o) noexcept { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3& operator-=(const Vec3& o) noexcept { x -= o.x; y -= o.y; z -= o.z; return *this; }
    Vec3& operator*=(double s)     noexcept { x *= s; y *= s; z *= s; return *this; }

    double dot(const Vec3& o)    const noexcept { return x*o.x + y*o.y + z*o.z; }
    Vec3   cross(const Vec3& o)  const noexcept {
        return { y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x };
    }
    double length()              const noexcept { return std::sqrt(x*x + y*y + z*z); }
    double length_sq()           const noexcept { return x*x + y*y + z*z; }
    Vec3   normalized()          const noexcept {
        double inv = math_utils::fast_inv_sqrt(length_sq());
        return {x * inv, y * inv, z * inv};
    }
};

struct alignas(16) Quat {
    double w, x, y, z;

    Quat() noexcept : w(1), x(0), y(0), z(0) {}
    Quat(double w, double x, double y, double z) noexcept : w(w), x(x), y(y), z(z) {}

    Quat  operator*(const Quat& o) const noexcept {
        return {
            w*o.w - x*o.x - y*o.y - z*o.z,
            w*o.x + x*o.w + y*o.z - z*o.y,
            w*o.y - x*o.z + y*o.w + z*o.x,
            w*o.z + x*o.y - y*o.x + z*o.w
        };
    }
    Vec3  rotate(const Vec3& v)    const noexcept {
        Quat p{0, v.x, v.y, v.z};
        Quat conj{w, -x, -y, -z};
        Quat r = *this * p * conj;
        return {r.x, r.y, r.z};
    }
    Quat  conjugated()            const noexcept { return {w, -x, -y, -z}; }
    double norm_sq()              const noexcept { return w*w + x*x + y*y + z*z; }
};

struct alignas(16) Mat4 {
    double m[16]{};

    static Mat4 identity() noexcept {
        Mat4 r;
        r.m[0] = 1; r.m[5] = 1; r.m[10] = 1; r.m[15] = 1;
        return r;
    }
    static Mat4 translate(const Vec3& t) noexcept {
        Mat4 r = identity();
        r.m[12] = t.x; r.m[13] = t.y; r.m[14] = t.z;
        return r;
    }
    static Mat4 scale(const Vec3& s) noexcept {
        Mat4 r;
        r.m[0] = s.x; r.m[5] = s.y; r.m[10] = s.z; r.m[15] = 1;
        return r;
    }
    static Mat4 perspective(double fov, double aspect, double near, double far) noexcept {
        double f = 1.0 / std::tan(fov * 0.5);
        Mat4 r;
        r.m[0]  = f / aspect;
        r.m[5]  = f;
        r.m[10] = (far + near) / (near - far);
        r.m[11] = -1;
        r.m[14] = (2 * far * near) / (near - far);
        return r;
    }

    Mat4 operator*(const Mat4& o) const noexcept {
        Mat4 r;
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j)
                for (int k = 0; k < 4; ++k)
                    r.m[j*4+i] += m[k*4+i] * o.m[j*4+k];
        return r;
    }
    Vec3 transform(const Vec3& v) const noexcept {
        return {
            m[0]*v.x + m[4]*v.y + m[8]*v.z  + m[12],
            m[1]*v.x + m[5]*v.y + m[9]*v.z  + m[13],
            m[2]*v.x + m[6]*v.y + m[10]*v.z + m[14]
        };
    }
};

using Vec2 [[maybe_unused]] = Vec3;
using Vec4 [[maybe_unused]] = Vec3;

}
}

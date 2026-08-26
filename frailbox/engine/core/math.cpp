#include "math.hpp"

namespace trial {
namespace core {

static_assert(sizeof(Vec3) == 32,  "Vec3 must be 32 bytes (3 doubles + alignas(16) padding)");
static_assert(sizeof(Quat) == 32,  "Quat must be 32 bytes");
static_assert(sizeof(Mat4) == 128, "Mat4 must be 128 bytes");
static_assert(alignof(Vec3) == 16, "Vec3 must be 16-byte aligned");
static_assert(alignof(Quat) == 16, "Quat must be 16-byte aligned");
static_assert(alignof(Mat4) == 16, "Mat4 must be 16-byte aligned");

}
}

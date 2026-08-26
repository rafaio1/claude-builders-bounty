#ifndef FRAILBOX_ARENA_H
#define FRAILBOX_ARENA_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum arena_flags {
    ARENA_DEFAULT       = 0,
    ARENA_ZERO_INIT     = 1 << 0,
    ARENA_LOCK          = 1 << 1,
    ARENA_HUGE_PAGES    = 1 << 2,
    ARENA_GUARD_PAGES   = 1 << 3,
} arena_flags_t;

typedef struct arena_stats {
    uint64_t total_allocated;
    uint64_t total_freed;
    uint64_t peak_usage;
    uint64_t current_usage;
    uint64_t allocation_count;
    uint64_t deallocation_count;
    uint64_t region_count;
} arena_stats_t;

typedef struct arena_region {
    void           *start;
    size_t          size;
    size_t          used;
    uint32_t        flags;
    struct arena_region *next;
} arena_region_t;

typedef struct arena {
    arena_region_t *regions;
    arena_region_t *current;
    arena_stats_t   stats;
    size_t          default_region_size;
    uint32_t        flags;
    int             lock_fd;
} arena_t;

arena_t *arena_create(size_t default_region_size, uint32_t flags);
void     arena_destroy(arena_t *arena);

void   *arena_alloc(arena_t *arena, size_t size);
void   *arena_alloc_aligned(arena_t *arena, size_t size, size_t alignment);
void   *arena_calloc(arena_t *arena, size_t nmemb, size_t size);
void    arena_reset(arena_t *arena);

arena_region_t *arena_new_region(arena_t *arena, size_t min_size);
int             arena_merge_regions(arena_t *arena);
int             arena_trim(arena_t *arena);

arena_stats_t arena_get_stats(const arena_t *arena);
size_t        arena_total_capacity(const arena_t *arena);
int           arena_contains(const arena_t *arena, const void *ptr);

#ifdef __cplusplus
}
#endif

#endif

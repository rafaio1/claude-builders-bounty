#ifndef FRAILBOX_SANDBOX_H
#define FRAILBOX_SANDBOX_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum sandbox_type {
    SANDBOX_NONE       = 0,
    SANDBOX_SECCOMP    = 1,
    SANDBOX_NAMESPACE  = 2,
    SANDBOX_CAPABILITY = 3,
    SANDBOX_CHROOT    = 4,
    SANDBOX_LANDLOCK   = 5,
} sandbox_type_t;

typedef enum sandbox_capability {
    CAP_NONE        = 0,
    CAP_FILE_READ   = 1 << 0,
    CAP_FILE_WRITE  = 1 << 1,
    CAP_NETWORK     = 1 << 2,
    CAP_PROCESS     = 1 << 3,
    CAP_IPC         = 1 << 4,
    CAP_SYSLOG      = 1 << 5,
    CAP_CLOCK       = 1 << 6,
    CAP_ALL         = 0xFFFFFFFF,
} sandbox_capability_t;

typedef enum sandbox_action {
    ACTION_ALLOW    = 0,
    ACTION_DENY     = 1,
    ACTION_KILL     = 2,
    ACTION_TRACE    = 3,
    ACTION_LOG      = 4,
} sandbox_action_t;

typedef struct sandbox_rule {
    sandbox_capability_t capability;
    sandbox_action_t     action;
    uint32_t             syscall_number;
    char                 path_pattern[256];
    struct sandbox_rule *next;
} sandbox_rule_t;

typedef struct sandbox_config {
    sandbox_type_t       type;
    uint32_t             flags;
    uint64_t             memory_limit_bytes;
    uint64_t             cpu_limit_ns;
    uint32_t             max_processes;
    uint32_t             max_open_fds;
    int                  enable_network;
    int                  enable_ptrace;
    char                 chroot_path[4096];
    char                 work_dir[4096];
    sandbox_rule_t      *rules;
    size_t               rule_count;
} sandbox_config_t;

typedef struct sandbox {
    sandbox_config_t  config;
    int               active;
    int               pid;
    uint64_t          start_time;
    uint64_t          cpu_time_used;
    uint64_t          memory_used;
    uint32_t          violations;
    int               seccomp_fd;
    int               event_fd;
} sandbox_t;

sandbox_t *sandbox_create(const sandbox_config_t *config);
int        sandbox_apply(sandbox_t *sandbox);
void       sandbox_destroy(sandbox_t *sandbox);

int sandbox_add_rule(sandbox_t *sandbox, sandbox_capability_t cap, sandbox_action_t action);
int sandbox_remove_rule(sandbox_t *sandbox, sandbox_capability_t cap);

int sandbox_exec(sandbox_t *sandbox, const char *path, char *const argv[], char *const envp[]);
int sandbox_kill(sandbox_t *sandbox, int signal);

uint64_t sandbox_get_usage(sandbox_t *sandbox);
int      sandbox_get_violations(sandbox_t *sandbox);
int      sandbox_is_active(const sandbox_t *sandbox);

int sandbox_set_memory_limit(sandbox_t *sandbox, uint64_t limit_bytes);
int sandbox_set_cpu_limit(sandbox_t *sandbox, uint64_t limit_ns);
int sandbox_set_process_limit(sandbox_t *sandbox, uint32_t max_procs);

#ifdef __cplusplus
}
#endif

#endif

# Performance drop-ins for 179.198.117.31

These files are the reproducible source for the runtime overrides installed on the legacy host.

| Source file | Runtime destination |
| --- | --- |
| `agentic-loop-resources.conf` | `/etc/systemd/system/agentic-loop.service.d/resources.conf` |
| `bughunter-sync-bounds.conf` | `/etc/systemd/system/bughunter-sync.service.d/bounds.conf` |
| `agentic-codex-process-snapshot.override.conf` | `/etc/systemd/system/agentic-codex-process-snapshot.timer.d/override.conf` |
| `agentic-portal-snapshot.override.conf` | `/etc/systemd/system/agentic-portal-snapshot.timer.d/override.conf` |
| `bughunter-portal-snapshot.override.conf` | `/etc/systemd/system/bughunter-portal-snapshot.timer.d/override.conf` |

After installation run `systemctl daemon-reload`, verify the units with `systemd-analyze verify`, and restart only `agentic-loop.service`. `bughunter-sync.service` and `bughunter-sync.timer` remain disabled until the HackerOne GraphQL catalog authentication/parsing is repaired; the 15-minute bound is retained as a fail-closed guard for any future re-enable. These overrides contain no credentials.

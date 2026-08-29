# BaseIntelligence/base#193 — Security & Stability Remediation Plan

**Status:** DRAFT — AWAITING USER APPROVAL  
**PR:** https://github.com/BaseIntelligence/base/pull/193  
**Findings Source:** CodeRabbit AI Review (2026-08-24)  
**Total Findings:** 15 (3 Critical, 7 Major, 5 Minor)  

---

## ⛔ CRITICAL (Must Fix Before Merge)

### C1. Committed ADMIN_KEY & PostgreSQL Password in docker-compose.yml
- **File:** `docker-compose.yml:21-23`
- **Risk:** Anyone with repo read access can approve bounty submissions via `/v1/bounty/approve`. DB password also exposed. Port 5432 bound to all host interfaces.
- **Fix:** 
  - Remove hardcoded `ADMIN_KEY: supersecretadminkey` and `POSTGRES_PASSWORD: postgres`
  - Use `${ADMIN_KEY:?set ADMIN_KEY}` and `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}` env interpolation
  - Remove `ports: ["5432:5432"]` — internal Compose network suffices
  - Add Docker secret for `OPENROUTER_API_KEY` using existing `_FILE` pattern
- **Verification:** `grep -rn 'supersecret\|postgres:postgres' .` returns nothing; `docker compose config` validates env vars required

### C2. FFmpeg Output Path Invalid — All Video Submissions Fail
- **File:** `src/services/video.rs:12-22`
- **Risk:** `NamedTempFile::new()` creates extensionless file; FFmpeg cannot infer container → returns 500 on every valid submission
- **Fix:** Apply CodeRabbit committable suggestion:
  ```rust
  let output_file = tempfile::Builder::new().suffix(".mp4").tempfile()?;
  Command::new("ffmpeg")
      .arg("-y")
      .arg("-i").arg(input_file.path())
      .args(["-vcodec", "libx264", "-crf", "28", "-preset", "veryfast", "-f", "mp4"])
      .arg(output_file.path())
      .status()?;
  ```
- **Verification:** Unit test with sample MP4 input → output file exists, is valid MP4, size > 0

### C3. Control-Plane Services Removed from docker-compose.yml
- **File:** `docker-compose.yml:1-33`
- **Risk:** Only `postgres` and `bounty-challenge` remain. Validator, updater, socket proxy, challenge backends, and master-profile gateway are gone. Stack cannot function as documented.
- **Fix:** Restore all removed services, profiles, networks, volumes, and secret-backed config from `HEAD~1`. Keep `bounty-challenge` alongside them.
- **Verification:** `docker compose config --services` lists all expected services; `docker compose up --dry-run` succeeds

---

## 🟠 MAJOR (Should Fix)

### M1. Workspace Manifest Overwritten in Cargo.toml
- **File:** `Cargo.toml:1-20`
- **Fix:** Restore root workspace members, `xtask` package, shared lint policy. Add `base-bounty` as new member.
- **Verification:** `cargo xtask ci` passes; `cargo clippy --workspace -- -D warnings` clean

### M2. No PostgreSQL Healthcheck or Migration Gate
- **File:** `docker-compose.yml:24-30`, `src/main.rs`
- **Fix:** Add `healthcheck:` to postgres service; add `depends_on: postgres: condition: service_healthy`; run migrations before serving.
- **Verification:** Service waits for PG ready; `bounty_submissions` table exists at startup

### M3. Container Runs as Root + Missing --no-install-recommends
- **File:** `Dockerfile.bounty:1-13`
- **Fix:** Apply CodeRabbit committable suggestion: non-root user `bounty:10001`, `--no-install-recommends` on both apt-get, remove ffmpeg from builder stage.
- **Verification:** `docker run --rm base-bounty whoami` → `bounty`; Trivy DS-0002 and DS-0029 pass

### M4. SQLx Offline Mode Not Configured for Docker Build
- **File:** `Dockerfile.bounty`, `.sqlx/` directory
- **Fix:** Generate `.sqlx/query-*.json` offline metadata; set `ENV SQLX_OFFLINE=true` in Dockerfile; add `.dockerignore` excluding `.env*`, secrets, etc.
- **Verification:** `DOCKER_BUILDKIT=1 docker build -f Dockerfile.bounty .` succeeds without live DB

### M5. Score Epoch Weights Misaligned Between Docs and Code
- **File:** `docs/BOUNTY_CHALLENGE.md:11`, `src/services/scoring.rs`, `config/challenges.toml`
- **Fix:** Align to `design = 0 bps, prism = 10000 bps`; omit bounty weight. Update docs and emission logic. Consensus-lint must validate against signed config.
- **Verification:** `cargo test scoring` passes; lint check confirms weights match config

### M6. miner_id Self-Declared — No Authentication on Upload
- **File:** `docs/external-miner/bounty.md:8-9`, `src/routes/bounty.rs`
- **Fix:** Document that hotkey signature over upload payload is required. Reject unsigned requests. Document limits: max video size, formats, timeout.
- **Note:** Implementation of actual signature verification is out of scope for this PR fix; document the requirement and add a TODO with link to spec.
- **Verification:** Docs updated; route returns 401 for missing auth header (stub)

### M7. ADMIN_KEY unwrap_or_default() Allows Empty Auth
- **File:** `src/routes/bounty.rs:62-64`
- **Fix:** Fail startup if `ADMIN_KEY` env var is missing or empty. Use `std::env::var("ADMIN_KEY").expect("ADMIN_KEY must be set and non-empty")`.
- **Verification:** Service panics at startup when ADMIN_KEY unset; rejects empty-string admin_key in requests

---

## 🟡 MINOR (Nice to Have)

### m1. Submit Endpoint Response Contract Undocumented
- **File:** `docs/external-miner/bounty.md:11-22`
- **Fix:** Document 200 OK `{id: UUID, status: "PENDING"}`, 400, 409, 500 responses. Exclude `/approve` and ADMIN_KEY from miner-facing docs.

### m2. approve_submission Returns 200 Without Emitting Score
- **File:** `src/services/scoring.rs:9-20`
- **Fix:** Load challenges.toml weights, emit challenge leaf, submit raw weights through gateway, wait for sealed bundle before returning Ok. Verify `sealed: true`.
- **Note:** This is a heavy lift. If gateway integration is not yet available, add explicit TODO and return 501 Not Implemented rather than false 200.

### m3. Similarity Check Sends Static Prompt — Always Returns False
- **File:** `src/services/video.rs:33-54`
- **Fix:** Send video representation + recent 24h corpus to OpenRouter. Reject missing API key, 401/429/5xx. Parse response strictly; fail closed on error.
- **Note:** Requires OpenRouter multimodal support confirmation. If unavailable, disable similarity check with explicit warning log rather than silently passing.

### m4. FFmpeg Blocks Tokio Worker Thread
- **File:** `src/services/video.rs:15-23`
- **Fix:** Wrap `Command::status()` in `tokio::task::spawn_blocking` with configurable timeout (e.g., 120s). Kill child on timeout.
- **Verification:** Concurrent upload test shows health endpoint remains responsive during compression

### m5. Missing .dockerignore
- **File:** `.dockerignore`
- **Fix:** Create with entries: `.env*`, `*.pem`, `*.key`, `target/`, `.git/`, `node_modules/`, `.sqlx/` (if regenerating), `secrets/`

---

## 🔒 SECURITY GATE — DO NOT PROCEED WITHOUT USER CONFIRMATION

This PR touches authorization secrets, database credentials, container privilege boundaries, and blockchain weight emission. **No code changes will be made until the user explicitly approves this plan.**

### Recommended Execution Order (After Approval):
1. C1 (secrets removal) — immediate security risk
2. C2 (FFmpeg fix) — functional blocker
3. C3 (restore compose services) — stack integrity
4. M7 (ADMIN_KEY validation) — auth hardening
5. M3 (non-root container) — defense in depth
6. M1, M2, M4 (build/workspace fixes) — CI green
7. M5, M6, m1-m5 (docs, scoring, similarity) — correctness

### Testing Requirements:
- `cargo fmt --check && cargo clippy --workspace -- -D warnings`
- `cargo test --workspace`
- `cargo deny check`
- `cargo xtask ci` (or equivalent gate)
- `docker compose config --quiet`
- `trivy image --severity HIGH,CRITICAL base-bounty:latest` (post-build)
- Manual smoke test: submit video → verify compression → verify DB record → verify approval flow fails without ADMIN_KEY

---

**Prepared by:** Claude Opus 5 (GhostCLI agent)  
**Date:** 2026-08-27T01:30Z  
**Next Action:** Awaiting user approval to proceed with implementation.

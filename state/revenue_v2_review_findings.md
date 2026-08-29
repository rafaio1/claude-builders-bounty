 # Revenue Manager v2 — Review Findings (Read-Only)
 
 **Date:** 2026-08-27T14:00Z
 **Reviewer:** Claude Opus 5 (Integrator v2)
 **Scope:** Diff HEAD~5 (37b1212f..HEAD), tools/revenue_db.py, tools/revenue_control_plane.py, tests/test_revenue_control_plane.py
 **Status:** BLOCKED — test failure + integration gaps
 
 ## 1. Test Failure (Critical)
 
 - `test_build_work_orders_empty_for_no_tier_a` FAILS.
 - Cause: `build_work_orders()` now ingests `data/aro/verified_revenue_candidates.json` unconditionally. The test passes an empty/non-Tier-A queue but the function still loads 3 verified candidates from disk, returning 3 orders instead of 0.
 - Impact: Tests are no longer hermetic; they depend on mutable workspace state. This violates deterministic testing and makes CI unreliable.
 - Required fix: Either inject the verified candidates path as a parameter (defaulting to None in tests) or mock the file load in tests. The worker must not read global state during unit tests.
 
 ## 2. SQLite Persistence Layer (revenue_db.py) — Gate Audit
 
 ### ✅ Passed
 - SQLite as single source of truth: schema covers identities, repo_health, opportunities, work_orders, events, settlements.
 - Idempotent migration: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT DO UPDATE`.
 - CAS transitions: `cas_transition_opportunity` and `cas_transition_work_order` enforce valid state graphs with rowcount check.
 - Event log: all transitions logged via `log_event()`.
 - Settlement dedupe: `transaction_id UNIQUE` constraint + math validation (`gross - fee == net ±0.01`).
 - Currency allowlist enforced in `create_settlement`.
 - WAL mode + foreign keys enabled.
 
 ### ⚠️ Issues
 - **No identity allowlist enforcement**: `upsert_identity` accepts any alias/provider. Handoff requires "identidade allowlisted". Need an `ALLOWED_IDENTITIES` set or DB-backed allowlist check before upsert.
 - **No max 3 active work_orders enforcement in DB**: The cap exists only in `build_work_orders()` (RCP). The DB layer itself does not prevent creating >3 active WOs. Should add a guard in `create_work_order` or a trigger.
 - **import_verified_candidates sets status='verified' unconditionally**: Should respect the candidate's existing state or validate before importing. Blindly marking as "verified" bypasses the discovery→verification gate.
 - **No repo_health check in opportunity creation**: `upsert_opportunity` has FK to repo_health but no check that `is_active=1`. Inactive repos could enter the pipeline.
 - **DB_PATH is relative**: `os.path.join(os.path.dirname(__file__), "..", "data", "aro", "revenue_v2.db")`. If cwd changes, path breaks. Should resolve to absolute at module load.
 
 ## 3. Revenue Control Plane (revenue_control_plane.py) — Source 2 Integration
 
 ### ✅ Passed
 - Field mapping aligned: handles both `state_current`/`current_state`, `hours_remaining`/`hours_remaining_estimate`, `next_action_concrete`/`next_action`, `source_official`/`official_source`.
 - Rejection filters: `is_spam`, `is_honeypot`, `repo_inactive`, `rejection_reason` all checked.
 - EV sorting uses `ev_per_hour_conservative` (fixes prior KeyError).
 - Max 3 cap preserved.
 
 ### ⚠️ Issues
 - **Dual-source lane separation unclear**: Source 1 (merged PRs) and Source 2 (verified candidates) are merged into one `candidates` list. Handoff requires "lanes build/receivable separadas". Need explicit lane tagging in work order metadata.
 - **No evidence validation for Source 2**: Source 1 requires Tier A dict evidence. Source 2 only checks `payment_path` and `value_usd > 0`. A candidate with a fabricated URL and arbitrary value could enter. Need at minimum URL format validation and evidence_source non-empty check.
 - **estimated_hours fallback to 10h is optimistic**: Default was 100h for Source 1 (conservative). Source 2 defaults to 10h, inflating EV/hour by 10x. Should use same conservative baseline or require explicit estimate.
 
 ## 4. Missing Tests (Negative Cases)
 
 Per handoff requirement, these negative tests are absent:
 - [ ] False evidence rejection for Source 2 candidates
 - [ ] Repo inactive filtering in Source 2
 - [ ] Alias not in allowlist rejected
 - [ ] Duplicate settlement dedupe via DB layer
 - [ ] Invalid CAS transition returns False
 - [ ] Persistence round-trip (write → read → verify)
 - [ ] DB initialization idempotency (run init_db twice)
 
 ## 5. Revenue Reconciler (revenue_reconciler.py) — Not Modified
 
 No changes in this diff. Existing hardened logic (BYBIT_MIN_BALANCE, provider/currency allowlists, dedupe) remains intact. No regressions detected.
 
 ## 6. Verdict

**NOT READY for integration.** The worker must:
1. Fix the failing test (hermetic verified candidates loading).
2. Add identity allowlist enforcement.
3. Add lane tagging for Source 1 vs Source 2.
4. Add missing negative tests.
5. Resolve DB_PATH to absolute.
6. Align estimated_hours default for Source 2.

After fixes, produce `/Agentic/state/revenue_v2_ready.json` with commit SHA and full test pass. Only then will final review proceed.

---
*This file is read-only review output. Do not edit code from this document.*

## 7. Systemd Drop-ins Audit (deploy/systemd/dropins/*)

**Status:** ✅ APPROVED for separate commit

- Files reviewed: `agentic-loop-resources.conf`, `agentic-codex-process-snapshot.override.conf`, `agentic-portal-snapshot.override.conf`, `bughunter-portal-snapshot.override.conf`, `bughunter-sync-bounds.conf`, `README.md`.
- Content validated as reproducible performance/resource overrides matching runtime `/etc` state.
- No credentials, secrets or environment variables found in any drop-in file.
- Resource guards present: CPUQuota, MemoryHigh/MemoryMax, TasksMax, Nice, IOWeight correctly set for production safety.
- Timer configurations use randomized delays and accuracy windows to prevent thundering herd.
- **Action:** These files are safe to integrate in a dedicated commit during final handoff. Must NOT be mixed with revenue_v2 worker code commits.

## 8. Official Sources Compliance Audit (state/revenue_official_sources.md)

## 9. Uncommitted Diff Audit (2026-08-27T14:30Z)

**Status:** ⚠️ PARTIAL PROGRESS — Critical fixes detected but incomplete

### ✅ Positive Changes (Uncommitted)

- **Hermeticity Fix (Finding #1):** `build_work_orders()` now accepts `verified_candidates: list | None = None` parameter. When `None`, loads from disk; when provided, uses injected list. This directly addresses the non-hermetic test failure. Worker must now update `tests/test_revenue_control_plane.py` to pass empty list or mock data.
- **DB Layer Rewrite (Finding #2 partial):** `revenue_db.py` completely refactored:
  - Context manager `_connect()` with proper commit/rollback replaces manual connection handling.
  - Schema uses CHECK constraints for status enums (opportunities, work_orders, settlements).
  - `create_settlement` validates currency against `ALLOWED_CURRENCIES` set and enforces `gross - fee == net ±0.01` math check.
  - CAS transitions (`cas_transition_opportunity`, `cas_transition_work_order`) now include explicit valid transition maps and log events on success.
  - `import_verified_candidates` accepts optional path parameter (defaults to standard location), improving testability.
  - Settlement deduplication via `transaction_id UNIQUE` constraint preserved.

### ⚠️ Remaining Gaps (Still Open)

- **Identity Allowlist (Finding #2):** New `upsert_identity` still accepts any alias/provider without allowlist check. No `ALLOWED_IDENTITIES` enforcement added.
- **Max 3 Active WOs in DB (Finding #2):** Cap remains only in RCP `build_work_orders`. No DB-level guard or trigger added to prevent >3 active work orders.
- **Lane Tagging (Finding #3):** Source 1 vs Source 2 distinction still not explicit in work order metadata. Both sources merge into same candidate list without lane identifier.
- **Evidence Validation (Finding #3):** Source 2 candidates still lack URL format validation and evidence_source non-empty check.
- **estimated_hours Default (Finding #3):** Source 2 fallback to 10h not changed. Still inflates EV/hour by 10x vs Source 1 conservative baseline.
- **Official Sources Tests (Finding #8):** No new negative tests for platform/GitHub divergence, implausible amounts, missing claim path, unsupported payout, or creator identity validation.
- **Test File Stale:** `tests/test_revenue_control_plane.py` mtime is 12:42Z — predates the hermeticity fix. Worker has not yet updated tests to use the new `verified_candidates` parameter.

### Action Required Before revenue_v2_ready.json

1. Update tests to inject verified_candidates (verify hermeticity fix works).
2. Add identity allowlist enforcement in `upsert_identity`.
3. Add lane tagging metadata to distinguish Source 1 vs Source 2 work orders.
4. Implement all 5 negative tests from Section 8.
5. Align estimated_hours default for Source 2 or require explicit estimate.
6. Commit changes and produce `revenue_v2_ready.json` with passing test suite.

**Status:** ⚠️ NEW TEST REQUIREMENTS

The official sources document establishes hard gates that current test suite does not cover:

### Required Negative Tests (Add to test_revenue_control_plane.py)

- [ ] **Platform/GitHub State Divergence:** Candidate with open platform board listing but closed/rewarded linked GitHub issue must be rejected. (Ref: Algora #6674/#6532 case)
- [ ] **Implausible/Stale Amount Rejection:** Candidate with amount outside reasonable bounds or missing official reward identifier must be rejected. (Ref: Opire public listings warning)
- [ ] **Missing Claim Path:** Candidate without verifiable claim/apply mechanism must be rejected.
- [ ] **Unsupported Payout Routing:** Candidate claiming Wise/crypto payout when only Stripe is configured must be rejected.
- [ ] **Creator Identity Validation:** Candidate without verifiable payer/creator identity must be rejected per Opire terms.

### Connector Contract Enforcement Gaps

- Current `import_verified_candidates` does not validate source URL against official SDK/API endpoints.
- No timestamp freshness check for revalidation-before-claim requirement.
- Evidence storage does not enforce immutable source URL + platform reward ID + observed timestamp tuple.
- Lane tagging missing for Source 2 candidates to distinguish from Source 1 merged PRs.

**Action:** Worker must add above negative tests and connector contract validations before producing `revenue_v2_ready.json`.

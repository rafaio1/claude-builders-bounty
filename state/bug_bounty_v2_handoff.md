# Bug Bounty Operations Handoff v2

**Generated:** 2026-08-27T00:00:00Z
**Status:** HANDOFF_READY
**Goal State:** ACTIVE (Aspirational Target: 20,000,000 USDT)

## 1. Current Target: Coinbase Developer Platform (CDP)
*   **Source:** Official Documentation (`docs.cdp.coinbase.com/llms.txt`) + HackerOne Public Policy.
*   **Program Status:** Active, Public, Bounty-Paying.
*   **Safe Harbor:** Explicitly granted for authorized researchers following policy.
*   **Authorized Assets:**
    *   `*.coinbase.com` (Core App/API)
    *   CDP APIs & SDKs (Policy Engine, Spend Permissions, Domain Allowlisting)
    *   Smart Contracts (SpendPermissionManager - AUDITED HARDENED)
*   **Exclusions:** Third-party integrations, physical attacks, social engineering, DoS (>5 qps), data exfiltration of real users.
*   **Testing Limits:** Manual probes only. Max 5 req/s. Header: `X-HackerOne-Research: rafaio`. Own accounts/test IDs only.

## 2. Completed Actions (This Session)
1.  **Auth Validation:** H1 `/v1/hackers/me/reports` = OK. H1 `/v1/hackers/me/programs` = 401 (Idempotency Key: `h1-programs-401-20260827` PENDING WRITE). Intigriti = 401 (Permanent Block).
2.  **Reconnaissance:** Retrieved full CDP documentation index via `llms.txt`. Fetched specs for Policy Engine, Domain Allowlisting, EVM/Solana Criteria.
3.  **Static Analysis:** Audited `SpendPermissionManager.sol`. Confirmed robust overflow/boundary checks. NO ON-CHAIN VECTORS.
4.  **Engine Identification:** Confirmed RE2 regex engine for Policy Engine via SDK source (`evmSchema.ts`). Eliminates ReDoS; focuses testing on Unicode/newline/encoding bypasses.
5.  **Feedback Integration:** Processed H1 Report #3972388 (Wolt) = DUPLICATE. Updated dedupe rules.

## 3. Evidence & Artifacts
| File | Description | Status |
| :--- | :--- | :--- |
| `/tmp/cdp_llms_refresh.txt` | CDP Docs Index (1307 lines) | ✅ Retrieved |
| `/tmp/cdp_domain_allowlisting_v2.md` | Domain Allowlist Spec (CORS, Deep Links, Extensions) | ✅ Retrieved |
| `/tmp/cdp_evm_policies_v2.md` | EVM Policy Criteria (RE2 Regex confirmed) | ✅ Retrieved |
| `/tmp/cdp_policy_overview_v2.md` | Policy Engine Architecture (Fail-Secure, Ordered Rules) | ✅ Retrieved |
| `/tmp/spm_contract.sol` | SpendPermissionManager Audit Notes | ✅ Hardened |
| `/Agentic/logs/bounty/ledger.json` | Master Audit Ledger | ⚠️ Needs Idempotent Write |
| `/Agentic/logs/bounty/h1_feedback_ledger.jsonl` | Feedback Learning Loop | ✅ Updated |

## 4. Authentication State
*   **HackerOne REST:** Authenticated (`rafaio`). List reports OK. Program directory 401 (logged).
*   **Intigriti:** Blocked (401).
*   **Coinbase CDP:** No API key needed for public docs/testing sandbox. Live testing requires own account credentials (NOT stored in agent env).
*   **Creds Location:** `/Agentic/.env` (Mode 600). NEVER PRINT.

## 5. Next Exact Steps
1.  **WRITE IDEMPOTENCY KEY:** Append `h1-programs-401-20260827` to `/Agentic/logs/bounty/ledger.json` immediately.
2.  **FORMULATE RE2 TEST CASES:** Design vectors for Unicode normalization (NFC/NFD), newline injection (`.` vs `[\s\S]`), and encoding boundaries targeting `evmMessage`/`evmTypedDataField`.
3.  **FORMULATE DOMAIN ALLOWLIST TEST CASES:** Design vectors for deep link scheme traversal (`myapp://callback/../evil`), extension ID spoofing, and port edge cases.
4.  **AUTHORIZED PROBING:** Execute manual probes against CDP Sandbox/Testnet ONLY. Validate reproducibility.
5.  **DEDUPE CHECK:** Cross-reference findings with existing public disclosures and user's prior reports before drafting.
6.  **SUBMISSION GATE:** Auto-submit ONLY if all gates pass (Scope + Repro + Impact + Dedupe + Sanitized). Otherwise archive evidence and pivot.

## 6. Critical Constraints (DO NOT VIOLATE)
*   NO scanners, brute force, DoS, social engineering.
*   NO live user data. Own accounts only.
*   NO verbose curl (`-v`) or printing auth headers.
*   NO broad recursive grep/find. Path-limited searches only.
*   NO retrying 401 endpoints without new evidence.
*   Telegram ONLY for realized/reconciled capital.
*   Goal NEVER marked complete due to delays. Use `waiting_monitoring`.

## 7. Feedback Signal Summary
*   **Wolt #3972388:** DUPLICATE. Lesson: Strict dedupe required. Check existing reports/public disclosures before submission.
*   **Arkose Labs:** EXHAUSTED. Lesson: Token acquisition path blocked without customer portal access. Pivot when docs confirm no public demo keys.
*   **GitLab Duo WF:** SUSPENDED. Lesson: External gem boundary reached. Static analysis complete but unverifiable without installed environment.

---
**HANDOFF READY.** Resume from Section 5, Step 1. Preserve goal state. Fail closed.

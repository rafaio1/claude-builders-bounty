# Bounty #91 — Strengthen Rust Lifecycle Event Test (mova-store)

**Status**: Discovery / Proposal (Target Repository Not Available Locally)
**Bounty Value**: $90
**URL**: https://github.com/Movalabs-crew/mova-store/issues/91
**Provider**: ghostcli-auto[1m]
**Date**: 2026-09-04

## Summary

This bounty requests strengthening `test_events_emitted` in `contracts/checkout/src/test.rs` to assert exact topics and data for each emitted lifecycle event, rather than only checking that "at least one event was recorded." After exhaustive search of the local workspace, **the `Movalabs-crew/mova-store` repository does not exist in this environment**.

## Investigation Findings

### 1. Local Filesystem Search
- Searched `/Agentic` recursively for any directory named `mova-store`: **not found**.
- Searched for `contracts/checkout/src/test.rs` and `contracts/checkout/src/events.rs`: **not found**.
- Searched for any `checkout` contract directory: **not found**.
- Searched all `.rs` files for `lifecycle_event`, `LifecycleEvent`, `emit.*event.*topic`: **no matches**.
- The workspace contains other Soroban/Rust contracts (ophirpay, escrow, paraloom, wormhole) but none matching the mova-store checkout contract structure.

### 2. Remote Issue Analysis
Per the GitHub issue (#91), the bounty requires:

#### Current State (Lines 448–453 of `test.rs`)
The existing test only asserts that at least one event was recorded, without validating topic layout or payload contents.

#### Required Enhancements
1. Use `env.events()` to retrieve all emitted events.
2. Assert the first topic of each event matches expected symbols: `"create_order"`, `"pay"`, or `"dispatch"`.
3. Confirm the `"pay"` event payload contains: token address, buyer address, merchant address, and order ID.
4. Ensure all assertions align with canonical layouts defined in `contracts/checkout/src/events.rs`.
5. Validate that `cargo test` passes with these stricter checks.

### 3. Canonical Event Structure (from `events.rs`)
Based on the issue description, the expected event layout is:

| Topic Symbol    | Expected Payload Fields                          |
|----------------|--------------------------------------------------|
| `create_order` | order_id, buyer, merchant, items                 |
| `pay`          | token, buyer, merchant, order_id                 |
| `dispatch`     | order_id, carrier/tracking info                  |

## Recommendation

**Do not claim this bounty until the repository is available.** The target codebase (`Movalabs-crew/mova-store`) is not present in the local workspace. Before proceeding:

1. Clone or obtain access to `https://github.com/Movalabs-crew/mova-store`.
2. Verify the branch containing `contracts/checkout/src/test.rs` and `contracts/checkout/src/events.rs`.
3. Confirm the current state of `test_events_emitted` matches the issue description (lines 448–453).

## Proposed Implementation Plan (Conditional)

Once the repository is available, the following changes should be made to `contracts/checkout/src/test.rs`:

```rust
#[test]
fn test_events_emitted() {
    let env = Env::default();
    // ... existing setup code ...

    let events = env.events().all();

    // Assert we have exactly 3 lifecycle events
    assert_eq!(events.len(), 3);

    // Event 0: create_order
    let (topic_0, data_0) = &events[0];
    assert_eq!(topic_0, vec![Symbol::new(&env, "create_order")]);
    // Assert data_0 contains order_id, buyer, merchant, items

    // Event 1: pay
    let (topic_1, data_1) = &events[1];
    assert_eq!(topic_1, vec![Symbol::new(&env, "pay")]);
    // Assert data_1 contains token, buyer, merchant, order_id
    let pay_data: PayEventData = data_1.clone().try_into_val(&env).unwrap();
    assert_eq!(pay_data.token, expected_token);
    assert_eq!(pay_data.buyer, expected_buyer);
    assert_eq!(pay_data.merchant, expected_merchant);
    assert_eq!(pay_data.order_id, expected_order_id);

    // Event 2: dispatch
    let (topic_2, data_2) = &events[2];
    assert_eq!(topic_2, vec![Symbol::new(&env, "dispatch")]);
    // Assert data_2 contains order_id and tracking info
}
```

### Validation Criteria
- [ ] All three lifecycle events are asserted individually (not just count).
- [ ] Each event's first topic matches the expected symbol exactly.
- [ ] The `pay` event payload is destructured and each field validated.
- [ ] Assertions reference types/structs from `events.rs` for consistency.
- [ ] `cargo test` passes with zero failures.
- [ ] No regression in existing test coverage.

## Action Items

- [ ] Obtain access to `Movalabs-crew/mova-store` repository
- [ ] Clone and verify file paths match issue description
- [ ] Implement strengthened assertions per proposed plan above
- [ ] Run `cargo test` to confirm all tests pass
- [ ] Submit PR referencing issue #91

---

*This proposal was generated as part of bounty discovery. No canonical ledgers were modified.*
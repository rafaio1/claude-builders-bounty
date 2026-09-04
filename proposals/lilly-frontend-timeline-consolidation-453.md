---
bounty_id: 453
repo: Lilly-Protocol/lily-frontend
title: "Consolidate the three Timeline component implementations into one canonical component"
value_usd: 95
type: discovery_proposal
status: ready_to_claim
date: 2026-09-04
linked_pr: 536
---

# Discovery Proposal: Consolidate Timeline Component Implementations

## Problem Summary

Three incompatible Timeline component implementations exist in the codebase, causing test failures due to mismatched APIs and an undefined `--color-border` design token. The components use different interfaces (compound children, items array, event array) and cannot be used interchangeably.

## Current State: Three Implementations

### 1. `src/components/ui/timeline.tsx` — KEEP (Canonical)
- **API:** Compound/children-based (`<Timeline>`, `<TimelineItem>`, etc.)
- **Styling:** Uses existing `--color-line` design token
- **Test coverage:** Has `src/components/ui/timeline.test.tsx` asserting connecting-line behavior
- **Status:** Target canonical implementation per bounty requirements

### 2. `src/components/timeline/index.tsx` — DELETE
- **API:** Accepts an `items` array prop
- **Bug:** References undefined `--color-border` CSS custom property (causes test failures)
- **Action:** Delete file and directory; migrate consumers to canonical component

### 3. `src/components/Timeline.tsx` — DELETE
- **API:** Accepts a `TimelineEvent[]` array with optional `icon` prop
- **Status:** Duplicate implementation with incompatible interface
- **Action:** Delete file; migrate consumers to canonical component

## Acceptance Criteria (from Issue #453)

| Criterion | How It Is Met |
|-----------|---------------|
| Only one Timeline export remains | Delete `src/components/timeline/index.tsx` and `src/components/Timeline.tsx` |
| All consumers import from `src/components/ui/timeline` | Migrate all imports during consolidation |
| `timeline.test.tsx` passes with connecting-line assertion | Canonical component already has this test |
| `npm run test:run` yields green for timeline specs | Removing broken implementations eliminates failures |
| No file references deprecated `--color-border` token | Replace with `--color-line` or delete referencing files |

## Implementation Plan

### Phase 1: Audit Consumers
1. Grep all imports referencing `src/components/timeline/index` and `src/components/Timeline`
2. Catalog each consumer's usage pattern (props passed, rendering context)
3. Map consumer props to the canonical compound API equivalents

### Phase 2: Migrate Consumers
1. Update each consumer to import from `src/components/ui/timeline`
2. Refactor item-array consumers to use the compound children pattern
3. Replace any `--color-border` references with `--color-line`

### Phase 3: Delete Deprecated Files
1. Remove `src/components/timeline/index.tsx` (and directory if empty)
2. Remove `src/components/Timeline.tsx`
3. Verify no dangling imports remain via grep

### Phase 4: Validate
1. Run `npm run test:run` — confirm all timeline specs pass
2. Run full lint/typecheck to catch broken imports
3. Visual regression check against Figma reference (linked in issue)

## Files to Modify

| File | Change |
|------|--------|
| `src/components/ui/timeline.tsx` | No change (canonical, kept as-is) |
| `src/components/ui/timeline.test.tsx` | No change (already asserts connecting-line behavior) |
| `src/components/timeline/index.tsx` | Delete |
| `src/components/Timeline.tsx` | Delete |
| Consumer files (TBD via audit) | Migrate imports to `src/components/ui/timeline` |

## Risk Assessment

- **Consumer migration complexity:** Items-array APIs require refactoring to adopt compound children pattern. Each consumer must be evaluated individually.
- **Icon prop parity:** If `src/components/Timeline.tsx` supports an optional icon that the canonical component lacks, the canonical component may need an icon slot added before deletion.
- **Design token audit:** A broader search for `--color-border` across the codebase is recommended to ensure no other components silently fail due to the same undefined token.
- **Linked PR #536:** May already contain partial implementation — review for conflicts before submitting.

## Claim Readiness

This proposal is complete and actionable. All acceptance criteria are addressed with specific file-level changes. Ready for bounty claim submission upon implementation verification.
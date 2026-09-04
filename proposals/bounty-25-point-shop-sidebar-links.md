---
name: bounty-25-point-shop-sidebar-links
description: Discovery proposal for Movalabs mova-store issue #25 — Point Shop sidebar dead links
metadata:
  type: project
  bounty_id: 25
  bounty_url: https://github.com/Movalabs-crew/mova-store/issues/25
  bounty_value: 90
  status: discovery_complete
  repo_missing: true
---

# Bounty #25: Point Shop Sidebar Links — Discovery Proposal

## Summary

The `mova-store` repository is **not cloned or available** in the current `/Agentic` workspace. This proposal documents the required fix based on the GitHub issue specification so that implementation can proceed once the repo is available.

## Issue Analysis

**File:** `app/shop/layout.jsx`

**Dead links identified in the issue:**

| Line | Label      | Current (broken) path | Problem                          |
|------|------------|-----------------------|----------------------------------|
| 46   | Women      | `/about`              | Route does not exist             |
| 55   | Kids       | `/contact`            | Route does not exist             |
| 95   | Categories | `/categories`         | Route does not exist             |
| 116  | Categories | `/categories`         | Duplicate entry, also broken     |

Additionally, several labels disagree with their targets (e.g., "Women" pointing to `/about`).

## Acceptance Criteria (from issue)

1. Clicking every sidebar link from a shop page never lands on the not-found page
2. Each entry's label matches its destination (cross-checked against the `app/` route table)
3. `next lint` passes

## Recommended Fix Strategy

### Option A: Map to valid routes/filters (preferred)

Inspect the `app/` directory to identify existing shop-related routes (e.g., `app/shop/women/`, `app/shop/kids/`, `app/shop/categories/[slug]/`). Update the sidebar entries to point to those real routes. If filter-based routing exists (e.g., `/shop?category=women`), use that instead.

### Option B: Remove dead entries

If no valid routes exist for Women, Kids, or Categories, remove those sidebar entries entirely rather than linking to non-existent pages.

### Implementation Steps

1. Clone `https://github.com/Movalabs-crew/mova-store` into workspace
2. Enumerate all routes under `app/shop/` to build the valid route table
3. Cross-reference sidebar entries in `app/shop/layout.jsx` against the route table
4. For each dead link:
   - If a matching route exists → update the `href`/`path` to the correct route
   - If no matching route exists → remove the sidebar entry
5. Ensure label text matches the destination semantics
6. Run `next lint` and fix any violations
7. Manually verify no sidebar click produces a 404

## Blockers

- **Repository not available locally.** The `mova-store` codebase must be cloned before implementation can begin.
- No `app/shop/layout.jsx` file was found anywhere in `/Agentic`.

## Next Steps

1. Clone the mova-store repository
2. Re-run discovery against actual code
3. Implement fix per Option A or B above
4. Submit PR referencing issue #25
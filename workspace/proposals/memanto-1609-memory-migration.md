---
bounty_id: memanto-1609
title: "The Great Memory Migration: Own Your Agentic Memory with Memanto + OKF"
provider: moorcheh-ai
reward_usd: 200
deadline: 2026-09-15T23:59:00Z
status: discovery_complete
type: discovery_proposal
created: 2026-09-04
---

# Bounty Discovery: Memanto + OKF Memory Migration Showcase

## Source
- **Issue**: https://github.com/moorcheh-ai/memanto/issues/1609
- **Repo**: moorcheh-ai/memanto
- **Reward**: $200 USD
- **Deadline**: September 15, 2026 (11:59 PM UTC)

## Summary
Build a compelling, reproducible migration showcase demonstrating agent memory portability using Memanto CLI and the Open Knowledge Format (OKF). The goal is proving the "in → owned → portable" freedom loop with real data, not synthetic test sets.

## Participation Paths

### Path A: Supported Provider Migration
- Migrate from Mem0 or Letta
- Show savings reports and round-trip recall parity
- Lower engineering novelty but faster to execute

### Path B: New Adapter (Highest Engineering Value)
- Create adapters for unsupported sources: Zep, LangMem, ChatGPT exports
- Must feed `memanto migrate` CLI rather than bypass it
- Highest scoring potential for Migration Value & Fidelity (30 pts)

### Path C: OKF Portability Workflow
- Git-versioned memory wikis
- Multi-source consolidation demos
- Strongest for OKF Portability Story (15 pts)

## Technical Requirements
1. Use `memanto migrate` and `memanto memory export --okf` as the primary tooling
2. Real data from actual tool runs (no synthetic datasets)
3. Round-trip validation via LLM-as-a-judge or golden Q&A sets
4. Valid, human-inspectable OKF bundle artifact in PR
5. Mandatory demo video showing live pipeline (screenshots insufficient)

## Judging Matrix (100 pts total)
| Criteria | Points | Notes |
|----------|--------|-------|
| Migration Value & Fidelity | 30 | Real data, recall parity, extension beyond current features |
| Social Virality | 25 | Engagement on X, YouTube, LinkedIn, Reddit; must tag Moorcheh |
| Reusability & Cleanliness | 20 | Mergeable into `/examples/migrations/`, clear docs |
| OKF Portability Story | 15 | Bundle genuinely showcases ownership |
| Use Case & Storytelling | 10 | Compelling narrative over trivial transfers |

## Prerequisites
- [ ] Star the moorcheh-ai/memanto repo
- [ ] Create BountyHub account
- [ ] Obtain Moorcheh API key
- [ ] Install memanto CLI locally
- [ ] Identify source memory system for migration

## Recommended Approach
**Path B (ChatGPT Export Adapter)** offers the best risk/reward:
- ChatGPT exports are widely available (real user data)
- No existing adapter = highest engineering value
- Natural storytelling angle ("reclaim your conversation history")
- High social virality potential (broad audience)

### Implementation Sketch
1. Parse ChatGPT `conversations.json` export format
2. Transform to OKF schema via new adapter in memanto
3. Run `memanto migrate` with the adapter
4. Validate recall parity against original ChatGPT memory
5. Record demo video of full pipeline
6. Write migration guide for `/examples/migrations/chatgpt-export/`
7. Post to X/LinkedIn/Reddit tagging @moaborcheh

## Risks & Blockers
- **Time**: 11 days remaining — tight for video production + social push
- **Social Virality**: 25% of score depends on engagement metrics (uncontrollable)
- **API Key**: Requires Moorcheh API key; verify availability before starting
- **Recall Validation**: LLM-as-a-judge adds cost and complexity

## Next Steps
1. Verify memanto CLI installation and API key access
2. Confirm no existing ChatGPT export adapter exists
3. Prototype parser for conversations.json format
4. Decide go/no-go by Sep 7 based on prototype viability

## Canonical Ledger Note
This file is a discovery proposal only. No canonical ledgers have been modified.
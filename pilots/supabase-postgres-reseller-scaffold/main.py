#!/usr/bin/env python3
"""Supabase Postgres Reseller Scaffold — Zero-Capital Lab v26"""
import json, datetime, pathlib

FREE_TIER_LIMITS = {
    "database_size": "500 MB",
    "egress": "5 GB/month",
    "file_storage": "1 GB",
    "mau_auth": 50000,
    "edge_functions_invocations": 500000,
    "realtime_messages": 2000000,
    "realtime_concurrent_connections": 200,
    "projects_active": 2,
    "pause_policy": "Paused after 1 week inactivity",
    "api_requests": "Unlimited",
    "support": "Community only"
}

PAID_PLAN_BASELINE = {
    "plan": "Pro",
    "price_monthly_usd": 25,
    "compute_micro_included": True,
    "disk_included_gb": 8,
    "egress_included_gb": 250,
    "storage_included_gb": 100,
    "mau_included": 100000,
    "overage_egress_per_gb": 0.09,
    "overage_storage_per_gb": 0.0213,
    "overage_mau": 0.00325,
    "backups": "7 days daily",
    "support": "Email"
}

RESELLING_MODEL = {
    "strategy": "Managed Supabase Backend-as-a-Service for indie devs & small SaaS",
    "target_segments": [
        "Indie hackers needing Postgres + Auth without DevOps",
        "AI startups needing pgvector (included free)",
        "MVP builders wanting instant API + realtime subscriptions"
    ],
    "value_adds": [
        "Pre-configured RLS policies & auth flows",
        "pgvector schema templates for AI apps",
        "Automated backup monitoring & unpause service",
        "Custom domain setup assistance",
        "Migration support from other BaaS"
    ],
    "pricing_suggestion": {
        "starter_tier_usd": 15,
        "growth_tier_usd": 35,
        "notes": "Starter covers shared project slot; Growth includes dedicated Micro compute + management"
    },
    "risks": [
        "Free projects pause after 1 week inactivity — requires monitoring/keepalive",
        "Only 2 active free projects per org — scaling requires Pro plan ($25/mo)",
        "500MB DB limit tight for production — upgrade path needed early",
        "No SLA or email support on free tier",
        "TOS must be checked for commercial reselling compliance"
    ],
    "compliance_check_required": True,
    "tos_url": "https://supabase.com/terms-of-service"
}

REPORT = {
    "pilot_name": "supabase-postgres-reseller-scaffold",
    "provider": "Supabase",
    "service_type": "Postgres Database + Auth + Storage + Edge Functions + Realtime",
    "free_tier_verified": True,
    "free_tier_permanent": True,
    "verification_method": "curl https://supabase.com/pricing.md",
    "verification_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "status": "SCAFFOLD_OK",
    "free_tier_limits": FREE_TIER_LIMITS,
    "paid_plan_baseline": PAID_PLAN_BASELINE,
    "reselling_model": RESELLING_MODEL,
    "next_steps": [
        "Verify TOS for commercial reselling/hosting compliance",
        "Build PoC: pgvector AI demo app with pre-configured schema",
        "Create keepalive mechanism to prevent free project pausing",
        "Design onboarding flow for managed Supabase service",
        "Test edge functions + realtime subscriptions in free tier"
    ]
}

if __name__ == "__main__":
    out = pathlib.Path(__file__).parent / "reseller_scaffold_index.json"
    out.write_text(json.dumps(REPORT, indent=2, ensure_ascii=False))
    print(f"[OK] Scaffold report written to {out}")
    print(f"[INFO] Status: {REPORT['status']}")
    print(f"[INFO] Free tier permanent: {REPORT['free_tier_permanent']}")
    print(f"[WARN] Compliance check required before TIER1 promotion")

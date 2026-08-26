#!/usr/bin/env python3
"""
Resend Email API Reseller Scaffold v26
Validated: Free tier confirmed via curl (3000 emails/mo, 100/day cap, permanent)
Zero-Capital Laboratory Pipeline
"""
import json
import datetime

SCAFFOLD = {
    "name": "resend-email-reseller-scaffold",
    "version": "v26",
    "status": "SCAFFOLD_OK",
    "validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "validation_method": "curl_pricing_markdown",
    "FREE_TIER_LIMITS": {
        "transactional_emails_per_month": 3000,
        "transactional_daily_cap": 100,
        "marketing_contacts": 1000,
        "domains": 3,
        "automation_runs_per_month": 10000,
        "ai_credits_per_month": 5,
        "data_retention_days": 30,
        "features": ["rest_api", "smtp_relay", "sdks", "inbound_email", "batch_sending", "tracking", "react_email", "webhooks"],
        "credit_card_required": False,
        "trial_expiry": None
    },
    "PAID_PLAN_BASELINE": {
        "pro_50k_usd": 20.00,
        "pro_100k_usd": 35.00,
        "scale_100k_usd": 90.00,
        "scale_1m_usd": 650.00,
        "overage_per_1k_usd": 0.90,
        "marketing_pro_5k_contacts_usd": 40.00,
        "dedicated_ip_usd": 30.00,
        "extra_domains_100_usd": 20.00
    },
    "RESELLING_MODEL": {
        "strategy": "Managed transactional email setup for SaaS + marketing broadcast service for creators",
        "target_customer": "indie hackers launching SaaS, newsletter creators, e-commerce stores needing reliable delivery",
        "monetization_paths": [
            "managed Resend setup + domain authentication service",
            "email template design + React Email component library",
            "newsletter migration service (from Mailchimp/Beehiiv to Resend)",
            "deliverability audit + DMARC/DKIM configuration consulting"
        ],
        "zero_capital_entry": "create free Resend account → build email demo/template → showcase deliverability → upsell managed setup",
        "margin_potential": "high (labor-only cost; free tier covers small clients; paid plans scale linearly)"
    },
    "risks": [
        "100 emails/day cap on free tier severely limits production use — clients will hit ceiling quickly",
        "No overage on free tier — emails simply stop sending after daily limit",
        "Resend TOS may restrict white-label reselling or sub-account creation",
        "Deliverability depends on client domain reputation — cannot guarantee inbox placement",
        "AI credits (5/mo free) insufficient for AI-powered email generation services"
    ],
    "next_steps": [
        "Create proof-of-concept transactional email flow (signup confirmation + password reset)",
        "Build React Email template library showcasing professional designs",
        "Test daily cap behavior empirically (what happens at 101st email?)",
        "Verify Resend TOS for reselling/sub-account/white-label compliance",
        "Draft pricing sheet: free setup vs managed monthly vs one-time migration",
        "Promote to TIER1 only after PoC live + TOS clearance"
    ]
}

if __name__ == "__main__":
    out_path = "/Agentic/pilots/resend-email-reseller-scaffold/reseller_scaffold_index.json"
    with open(out_path, "w") as f:
        json.dump(SCAFFOLD, f, indent=2)
    print(f"[OK] Scaffold written to {out_path}")
    print(json.dumps(SCAFFOLD, indent=2))

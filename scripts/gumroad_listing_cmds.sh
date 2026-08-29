# Gumroad Product Listing Automation
# Generated: 2026-08-29T05:21:11.267203+00:00

# Step 1: Open Gumroad dashboard
playwright-cli open https://gumroad.com/dashboard
playwright-cli snapshot  # Verify login state

# === Product 1: FDA Import Refusal Data Cleaner ===
playwright-cli click "Add a product"
playwright-cli snapshot

playwright-cli type "FDA Import Refusal Data Cleaner"
playwright-cli type "497"
playwright-cli type "Production-ready Python pipeline that scrapes, cleans, and structures FDA Import Refusal reports. Outputs analysis-ready CSV with normalized manufacturer names, violation codes, and risk scoring. Idea..."
playwright-cli type "data-cleaning, supply-chain, fda, b2b-intelligence"
# MANUAL: Upload file /Agentic/revenue/packages/fda_import_refusal_cleaner.py

playwright-cli click "Publish"
playwright-cli snapshot

# === Product 2: Universal Discord/Telegram Bot Framework ===
playwright-cli click "Add a product"
playwright-cli snapshot

playwright-cli type "Universal Discord/Telegram Bot Framework"
playwright-cli type "297"
playwright-cli type "Modular Python bot framework with platform adapter pattern. Includes FAQ responder, lead capture forms, webhook integration, Docker deployment. Single codebase works on both Discord and Telegram...."
playwright-cli type "bot-framework, discord, telegram, automation"
# MANUAL: Upload file /Agentic/revenue/packages/universal_bot_framework.py

playwright-cli click "Publish"
playwright-cli snapshot

playwright-cli close
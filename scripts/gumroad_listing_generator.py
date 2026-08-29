#!/usr/bin/env python3
"""
Gumroad Listing Automation v1.0
Generates Playwright CLI commands to list products without API keys.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

PRODUCTS = json.loads(Path('/Agentic/revenue/packages/gumroad_listings.json').read_text())

def generate_listing_commands():
    cmds = []
    cmds.append('# Gumroad Product Listing Automation')
    cmds.append('# Generated: ' + datetime.now(timezone.utc).isoformat())
    cmds.append('')
    cmds.append('# Step 1: Open Gumroad dashboard')
    cmds.append('playwright-cli open https://gumroad.com/dashboard')
    cmds.append('playwright-cli snapshot  # Verify login state')
    cmds.append('')
    
    for i, product in enumerate(PRODUCTS):
        cmds.append(f'# === Product {i+1}: {product["product"]} ===')
        cmds.append('playwright-cli click "Add a product"')
        cmds.append('playwright-cli snapshot')
        cmds.append('')
        cmds.append(f'playwright-cli type "{product["product"]}"')
        cmds.append(f'playwright-cli type "{product["price_usd"]}"')
        
        desc_clean = product['description'].replace('"', "'").replace('\n', ' ')[:200]
        cmds.append(f'playwright-cli type "{desc_clean}..."')
        
        tags_str = ', '.join(product.get('tags', []))
        cmds.append(f'playwright-cli type "{tags_str}"')
        
        cmds.append(f'# MANUAL: Upload file /Agentic/revenue/packages/{product["file"]}')
        cmds.append('')
        cmds.append('playwright-cli click "Publish"')
        cmds.append('playwright-cli snapshot')
        cmds.append('')
    
    cmds.append('playwright-cli close')
    return '\n'.join(cmds)

if __name__ == '__main__':
    output = generate_listing_commands()
    out_path = Path('/Agentic/scripts/gumroad_listing_cmds.sh')
    out_path.write_text(output)
    print(f'Generated {len(PRODUCTS)} product listing command sets -> {out_path}')
    print('\nFirst 20 lines:')
    print('\n'.join(output.split('\n')[:20]))

import json, re, sys

with open('/Agentic/data/aro/bounty_ledger.json', 'r') as f:
    raw = f.read()

tb_positions = [(m.start(), m.end()) for m in re.finditer(r'"total_bounty_usd"', raw)]
if not tb_positions:
    print("No total_bounty_usd found")
    sys.exit(1)

last_tb_end = tb_positions[-1][1]
rest = raw[last_tb_end:]
match = re.match(r':\s*([\d.]+)', rest)
if not match:
    print("Could not find value after total_bounty_usd")
    sys.exit(1)

end_of_value = last_tb_end + match.end()
fixed = raw[:end_of_value] + '\n}'

try:
    data = json.loads(fixed)
except json.JSONDecodeError as e:
    print(f"Fix attempt 1 failed: {e}")
    last_bracket = raw.rfind(']')
    if last_bracket > 0:
        fixed2 = raw[:last_bracket + 1] + '\n}'
        try:
            data = json.loads(fixed2)
        except json.JSONDecodeError as e2:
            print(f"Fix attempt 2 failed: {e2}")
            sys.exit(1)
    else:
        sys.exit(1)

entries = data.get('entries', [])
count = 0
if isinstance(entries, list):
    for e in entries:
        if isinstance(e, dict) and e.get('pr') == 6113:
            e['status'] = 'closed_unmerged'
            count += 1
    data['entries'] = entries
    data['last_updated'] = '2026-08-25T19:25:00Z'

with open('/Agentic/data/aro/bounty_ledger.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Ledger fixed. Entries: {len(entries)}. Updated {count} for OpenAgents #6113.")

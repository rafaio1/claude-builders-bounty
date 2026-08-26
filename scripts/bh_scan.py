import sqlite3, json
from pathlib import Path

bughunter_db = Path('/root/BugHunter/data/bughunter.db')
if not bughunter_db.exists():
    print('BugHunter DB not found.')
    exit(1)

conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
cursor = conn.cursor()

print('=== TOP BUGHUNTER TARGETS ===')
cursor.execute('SELECT handle, name, bounty_table_json, base_bounty, minimum_bounty FROM programs WHERE offers_bounties = 1 ORDER BY base_bounty DESC LIMIT 30')

top_targets = []
for row in cursor.fetchall():
    handle, name, bt_json, base_b, min_b = row
    max_b = float(base_b or 0)
    
    if bt_json:
        try:
            bt = json.loads(bt_json)
            if isinstance(bt, list):
                for item in bt:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if isinstance(v, (int, float)) and v > max_b:
                                max_b = v
            elif isinstance(bt, dict):
                for k, v in bt.items():
                    if isinstance(v, (int, float)) and v > max_b:
                                max_b = v
        except:
            pass
            
    top_targets.append({'handle': handle, 'name': name, 'max_bounty': max_b})

top_targets.sort(key=lambda x: x['max_bounty'], reverse=True)

for t in top_targets[:15]:
    print(f"  -> {t['handle']}: {t['name']} | Max Bounty: ${t['max_bounty']:,.0f}")

cursor.execute('SELECT COUNT(*) FROM submissions')
sub_count = cursor.fetchone()[0]
print(f'\nTotal Submissions in DB: {sub_count}')

cursor.execute('SELECT COUNT(*) FROM crew_runs')
crew_runs = cursor.fetchone()[0]
print(f'Total Crew Runs: {crew_runs}')

conn.close()

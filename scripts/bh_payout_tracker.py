import sqlite3, json
from pathlib import Path

bughunter_db = Path('/root/BugHunter/data/bughunter.sqlite3')
if not bughunter_db.exists():
    bughunter_db = Path('/root/BugHunter/data/bughunter.db')

if not bughunter_db.exists():
    print('BugHunter DB not found.')
    exit(1)

conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
cursor = conn.cursor()

print('=== BUGHUNTER SUBMISSION & PAYOUT TRACKER ===')

# Get schema of report_packs
cursor.execute("PRAGMA table_info(report_packs);")
rp_cols = [row[1] for row in cursor.fetchall()]
print(f"report_packs columns: {rp_cols}")

# Get schema of submissions
cursor.execute("PRAGMA table_info(submissions);")
sub_cols = [row[1] for row in cursor.fetchall()]
print(f"submissions columns: {sub_cols}")

# Fetch submitted reports and their statuses
if 'status' in sub_cols and 'handle' in sub_cols:
    cursor.execute("""
        SELECT s.id, s.handle, s.status, s.review_verdict, s.h1_report_url, s.created_at 
        FROM submissions s 
        ORDER BY s.created_at DESC 
        LIMIT 20
    """)
    rows = cursor.fetchall()
    print(f"\nRecent Submissions ({len(rows)}):")
    potential_payout = 0.0
    active_subs = 0
    for r in rows:
        sid, handle, status, verdict, url, created = r
        print(f"  [{status}] {handle} | Verdict: {verdict} | URL: {url}")
        
        if status in ('submitted', 'triaged', 'accepted', 'resolved'):
            active_subs += 1
            # Estimate bounty
            cursor.execute("SELECT base_bounty, minimum_bounty FROM programs WHERE handle = ?", (handle,))
            prog = cursor.fetchone()
            if prog:
                base_b = float(prog[0] or 0)
                min_b = float(prog[1] or 0)
                est = min_b if min_b > 0 else base_b
                if est > 0:
                    potential_payout += est

    print(f"\nActive/Pending Submissions: {active_subs}")
    print(f"Estimated Potential Payout Pipeline: ${potential_payout:,.2f}")

# Check crew_runs for active hunting
cursor.execute("SELECT COUNT(*) FROM crew_runs")
total_crews = cursor.fetchone()[0]
print(f"\nTotal Crew Runs (Hunting Cycles): {total_crews}")

# Check triage_items for confirmed vulnerabilities waiting for report pack
cursor.execute("PRAGMA table_info(triage_items);")
ti_cols = [row[1] for row in cursor.fetchall()]
if 'verdict' in ti_cols:
    cursor.execute("SELECT verdict, COUNT(*) FROM triage_items GROUP BY verdict")
    verdicts = cursor.fetchall()
    print(f"Triage Verdicts: {verdicts}")

conn.close()

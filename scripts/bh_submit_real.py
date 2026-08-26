import sqlite3, subprocess, json
from pathlib import Path

bughunter_db = Path('/root/BugHunter/data/bughunter.sqlite3')
if not bughunter_db.exists():
    bughunter_db = Path('/root/BugHunter/data/bughunter.db')

conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
cursor = conn.cursor()

print('=== FINDING & SUBMITTING REAL VULNERABILITIES ===')

# Find handles with 'real' triage verdicts
cursor.execute("""
    SELECT DISTINCT ti.handle 
    FROM triage_items ti
    WHERE ti.verdict = 'real'
""")
real_handles = [row[0] for row in cursor.fetchall()]
print(f"Handles with 'real' triage verdicts: {len(real_handles)}")

# Check which ones are already submitted
cursor.execute("SELECT DISTINCT handle FROM submissions WHERE status IN ('submitted', 'advanced', 'triaged', 'accepted')")
submitted_handles = set(row[0] for row in cursor.fetchall())

to_submit = [h for h in real_handles if h not in submitted_handles]
print(f"Handles needing submission: {len(to_submit)}")

for handle in to_submit[:5]:
    print(f"\n-> Attempting submission for: {handle}")
    try:
        res = subprocess.run(
            ['/root/BugHunter/.venv/bin/python', '-m', 'bughunter', 'submit', handle],
            capture_output=True, text=True, timeout=60
        )
        print(f"STDOUT: {res.stdout[:500]}")
        if res.stderr:
            print(f"STDERR: {res.stderr[:200]}")
    except Exception as e:
        print(f"Error: {e}")

conn.close()

#!/usr/bin/env python3
import subprocess
import sys
import re
from collections import defaultdict

def get_git_log():
    try:
        result = subprocess.run(
            ['git', 'log', '--pretty=format:%H|%s|%an|%aI', '--no-merges'],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip().split('\n')
    except subprocess.CalledProcessError:
        return []

def parse_commits(lines):
    categories = defaultdict(list)
    for line in lines:
        if not line: continue
        parts = line.split('|', 3)
        if len(parts) < 4: continue
        hash_, subject, author, date = parts
        
        match = re.match(r'^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.*)$', subject)
        if match:
            type_, scope, breaking, desc = match.groups()
            type_ = type_.lower()
            scope_str = scope or 'general'
            if breaking:
                categories['💥 Breaking Changes'].append(f"- {desc} ({scope_str}) [{hash_[:7]}]")
            elif type_ == 'feat':
                categories['✨ Features'].append(f"- {desc} ({scope_str}) [{hash_[:7]}]")
            elif type_ in ('fix', 'bug'):
                categories['🐛 Bug Fixes'].append(f"- {desc} ({scope_str}) [{hash_[:7]}]")
            elif type_ in ('docs', 'doc'):
                categories['📚 Documentation'].append(f"- {desc} [{hash_[:7]}]")
            elif type_ in ('chore', 'build', 'ci'):
                categories['🔧 Maintenance'].append(f"- {desc} [{hash_[:7]}]")
            elif type_ in ('refactor', 'perf'):
                categories['♻️ Refactoring'].append(f"- {desc} [{hash_[:7]}]")
            elif type_ == 'test':
                categories['🧪 Tests'].append(f"- {desc} [{hash_[:7]}]")
            else:
                categories['📦 Other'].append(f"- {subject} [{hash_[:7]}]")
        else:
            categories['📦 Other'].append(f"- {subject} [{hash_[:7]}]")
    return categories

def generate_changelog():
    lines = get_git_log()
    if not lines or lines == ['']:
        print("# Changelog\n\nNo commits found.")
        return
        
    categories = parse_commits(lines)
    
    print("# Changelog\n")
    print(f"Generated from {len(lines)} commits.\n")
    
    order = ['💥 Breaking Changes', '✨ Features', '🐛 Bug Fixes', '♻️ Refactoring', '📚 Documentation', '🧪 Tests', '🔧 Maintenance', '📦 Other']
    for cat in order:
        if cat in categories:
            print(f"## {cat}\n")
            for item in categories[cat]:
                print(item)
            print()

if __name__ == '__main__':
    generate_changelog()

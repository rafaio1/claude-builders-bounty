#!/usr/bin/env python3
import argparse, json, os, re, subprocess, sys
from urllib.parse import urlparse

def parse_pr_url(pr_ref):
    m = re.match(r'^([\w.-]+)/([\w.-]+)#(\d+)$', pr_ref)
    if m: return m.group(1), m.group(2), int(m.group(3))
    parsed = urlparse(pr_ref)
    parts = parsed.path.strip('/').split('/')
    if len(parts) >= 4 and parts[2] == 'pull':
        return parts[0], parts[1], int(parts[3])
    raise ValueError(f"Cannot parse PR reference: {pr_ref}")

def get_pr_diff(owner, repo, number):
    meta = subprocess.run(['gh','pr','view',str(number),'--repo',f'{owner}/{repo}','--json','title,body,files,additions,deletions,author'], capture_output=True, text=True)
    if meta.returncode != 0: print(f"Error: {meta.stderr}", file=sys.stderr); sys.exit(1)
    diff = subprocess.run(['gh','pr','diff',str(number),'--repo',f'{owner}/{repo}'], capture_output=True, text=True)
    if diff.returncode != 0: print(f"Error: {diff.stderr}", file=sys.stderr); sys.exit(1)
    return {'meta': json.loads(meta.stdout), 'diff': diff.stdout}

def analyze_diff(diff_text, meta):
    files_changed = meta.get('files', [])
    additions = meta.get('additions', 0)
    deletions = meta.get('deletions', 0)
    risks, suggestions = [], []
    dl = diff_text.lower()
    if re.search(r'(password|secret|api_key|token|private_key)\s*[:=]', dl): risks.append("⚠️ Possible hardcoded secret")
    if 'eval(' in dl or 'exec(' in dl: risks.append("⚠️ Dynamic code execution")
    if re.search(r'rm\s+-rf', dl): risks.append("⚠️ Destructive file operation")
    if 'drop table' in dl or 'truncate' in dl: risks.append("⚠️ Destructive SQL operation")
    if additions > 500: suggestions.append(f"📏 Large PR ({additions} additions)")
    if len(files_changed) > 20: suggestions.append(f"📁 Touches {len(files_changed)} files")
    if not any('test' in f.get('path','').lower() for f in files_changed) and additions > 50: suggestions.append("🧪 No test changes detected")
    confidence = "High" if additions < 100 and not risks else ("Medium" if additions < 300 and len(risks) <= 1 else "Low")
    summary = f"This PR modifies {len(files_changed)} file(s) with +{additions}/-{deletions}."
    if not risks: risks.append("✅ No obvious security risks")
    if not suggestions: suggestions.append("✅ Looks clean!")
    return {'summary': summary, 'risks': risks, 'suggestions': suggestions, 'confidence': confidence, 'stats': {'files': len(files_changed), 'additions': additions, 'deletions': deletions}}

def format_review(review, pr_url):
    lines = ["## 🤖 Automated PR Review", "", f"**PR:** {pr_url}", f"**Confidence:** {review['confidence']}", f"**Stats:** {review['stats']['files']} files | +{review['stats']['additions']} / -{review['stats']['deletions']}", "", "### Summary", review['summary'], "", "### ⚠️ Identified Risks"]
    for r in review['risks']: lines.append(f"- {r}")
    lines += ["", "### 💡 Improvement Suggestions"]
    for s in review['suggestions']: lines.append(f"- {s}")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pr', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    owner, repo, number = parse_pr_url(args.pr)
    pr_url = f"https://github.com/{owner}/{repo}/pull/{number}"
    data = get_pr_diff(owner, repo, number)
    review = analyze_diff(data['diff'], data['meta'])
    formatted = format_review(review, pr_url)
    if args.dry_run: print(formatted)
    else:
        subprocess.run(['gh','pr','comment',str(number),'--repo',f'{owner}/{repo}','--body',formatted])
        print(formatted)

if __name__ == "__main__": main()

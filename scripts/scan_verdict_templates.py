#!/usr/bin/env python3
"""Verdict Template Leak Scanner

Scans verdicts.jsonl for known template phrases that indicate
auto-generated or leaked verdict content rather than genuine council judgment.

Usage:
    python3 scripts/scan_verdict_templates.py [verdicts.jsonl] [output.json]
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / 'data' / 'expansion' / 'verdicts.jsonl'
DEFAULT_OUTPUT = REPO_ROOT / 'data' / 'expansion' / 'verdict_template_scan.json'

KNOWN_TEMPLATES = [
    'Arbitragem DEX-CEX',
    'Proxy TIER0 via GitHub Search sem validação de mercado BR',
    'Schema híbrido (GitHub+ReceitaWS)',
    'Timers improve causaram checkout compartilhado',
    'Dados operacionais validos mas sem relevancia BR',
    'Proxy global via GitHub Search API focado em agências/enterprises',
    'TEMPLATE_VERDICT',
    'AUTO_GENERATED',
    'PLACEHOLDER',
]


def scan_verdicts(input_path: str) -> dict:
    results = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'input_file': input_path,
        'total_scanned': 0,
        'template_leaks_found': 0,
        'leaks_by_template': {},
        'leaked_entries': [],
    }

    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                results['total_scanned'] += 1
                text = json.dumps(entry, ensure_ascii=False)
                for tmpl in KNOWN_TEMPLATES:
                    if tmpl.lower() in text.lower():
                        results['template_leaks_found'] += 1
                        results['leaks_by_template'][tmpl] = results['leaks_by_template'].get(tmpl, 0) + 1
                        results['leaked_entries'].append({
                            'line': line_num,
                            'proposal_id': entry.get('proposal_id', entry.get('id', 'UNKNOWN')),
                            'template_matched': tmpl,
                        })
            except json.JSONDecodeError:
                pass

    return results


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_INPUT)
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_OUTPUT)

    if not Path(input_path).exists():
        print(f'ERROR: input file not found: {input_path}', file=sys.stderr)
        sys.exit(1)

    results = scan_verdicts(input_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f'Scanned {results["total_scanned"]} verdicts')
    print(f'Template leaks found: {results["template_leaks_found"]}')
    print(f'Results written to {output_path}')


if __name__ == '__main__':
    main()

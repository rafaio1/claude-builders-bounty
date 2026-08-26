 #!/usr/bin/env python3
 """
 Email Triage Agent - Local implementation for Gmail filtering and decision routing.
 
 This agent classifies emails into 'pertinent' (actionable signals) vs 'noise'
 to reduce inbox clutter and feed the ARO decision system with relevant data only.
 
 Usage:
   python email_triage.py --input raw_email.eml --output /Agentic/data/aro/inbox/pending.jsonl
   python email_triage.py --batch /path/to/emails/ --dry-run
 """
 import argparse
 import email
 import json
 import os
 import re
 import sys
 from datetime import datetime, timezone
 from pathlib import Path
 
 # Pertinent signal patterns
 PERTINENT_SENDERS = [
     r'wise\.com', r'bybit\.com', r'paypal\.com', r'stripe\.com',
     r'mql5\.com', r'freelancer\.com', r'workana\.com', r'99freelas\.com\.br',
     r'github\.com', r'gitlab\.com', r'contra\.co',
     r'agentmail\.to',  # Internal ARO mail
 ]
 
 PERTINENT_SUBJECTS = [
     r'pagamento|payment|payout|transferência|wire',
     r'contrato|contract|proposal|orçamento|quote',
     r'bounty|patch|merge|pull request|pr \#',
     r'verificação|verify|kyc|identity|account',
     r'segurança|security|alert|2fa|login attempt',
     r're:.*(?:bugfix|docker|deploy|api|mql5)',  # Client replies
 ]
 
 NOISE_PATTERNS = [
     r'unsubscribe|newsletter|digest|weekly update',
     r'noreply|no-reply|automated|do-not-reply|mailer-daemon',
     r'promotional|marketing|offer|deal|discount',
     r'antibot|captcha|blocked|access denied',  # Platform blocks (already logged)
 ]
 
 def classify_email(msg: email.message.Message) -> dict:
     """Classify an email message and return structured triage result."""
     sender = str(msg.get('From', '')).lower()
     subject = str(msg.get('Subject', '(no subject)')).lower()
     date_str = msg.get('Date', '')
     
     # Check noise first (higher priority filter)
     for pattern in NOISE_PATTERNS:
         if re.search(pattern, sender) or re.search(pattern, subject):
             return {
                 'category': 'noise',
                 'sub_category': 'auto_filtered',
                 'urgency': 'low',
                 'action': 'archive',
                 'reason': f'Matched noise pattern: {pattern}',
                 'parsed_at': datetime.now(timezone.utc).isoformat(),
             }
     
     # Check pertinent signals
     is_pertinent_sender = any(re.search(p, sender) for p in PERTINENT_SENDERS)
     is_pertinent_subject = any(re.search(p, subject) for p in PERTINENT_SUBJECTS)
     
     if is_pertinent_sender or is_pertinent_subject:
         # Determine specific category
         if re.search(r'pagamento|payment|payout|transfer', subject):
             cat, sub, urg, act = 'finance', 'payment_received', 'high', 'update_ledger'
         elif re.search(r'contrato|contract|proposal', subject):
             cat, sub, urg, act = 'commerce', 'new_contract', 'high', 'create_contract'
         elif re.search(r'bounty|patch|merge|pr \#', subject):
             cat, sub, urg, act = 'oss', 'bounty_update', 'medium', 'log_submission'
         elif re.search(r'verificação|verify|kyc', subject):
             cat, sub, urg, act = 'accounts', 'verification', 'medium', 'update_account_status'
         elif re.search(r'segurança|security|alert', subject):
             cat, sub, urg, act = 'security', 'alert', 'critical', 'notify_owner'
         else:
             cat, sub, urg, act = 'client', 'reply', 'medium', 'route_to_inbox'
         
         return {
             'category': cat,
             'sub_category': sub,
             'urgency': urg,
             'action': act,
             'sender': sender,
             'subject': str(msg.get('Subject', '')),
             'date': date_str,
             'parsed_at': datetime.now(timezone.utc).isoformat(),
         }
     
     # Default: unknown/unclassified
     return {
         'category': 'unknown',
         'sub_category': 'unclassified',
         'urgency': 'low',
         'action': 'review_manual',
         'sender': sender,
         'subject': str(msg.get('Subject', '')),
         'parsed_at': datetime.now(timezone.utc).isoformat(),
     }
 
 def process_eml_file(path: str) -> dict:
     """Parse a .eml file and return classification."""
     with open(path, 'rb') as f:
         msg = email.message_from_bytes(f.read())
     result = classify_email(msg)
     result['source_file'] = str(path)
     return result
 
 def append_to_pending(result: dict, output_path: str):
     """Append triage result to pending.jsonl for Decision Router Agent."""
     os.makedirs(os.path.dirname(output_path), exist_ok=True)
     with open(output_path, 'a') as f:
         f.write(json.dumps(result, ensure_ascii=False) + '\n')
 
 def main():
     parser = argparse.ArgumentParser(description='Email Triage Agent for ARO')
     parser.add_argument('--input', help='Single .eml file to process')
     parser.add_argument('--batch', help='Directory of .eml files to process')
     parser.add_argument('--output', default='/Agentic/data/aro/inbox/pending.jsonl',
                         help='Output JSONL path for pertinent items')
     parser.add_argument('--dry-run', action='store_true', help='Print results without writing')
     args = parser.parse_args()
 
     results = []
     if args.input:
         results.append(process_eml_file(args.input))
     elif args.batch:
         batch_dir = Path(args.batch)
         for eml in sorted(batch_dir.glob('*.eml')):
             results.append(process_eml_file(str(eml)))
     else:
         print("Error: provide --input or --batch", file=sys.stderr)
         sys.exit(1)
 
     pertinent_count = 0
     noise_count = 0
     for r in results:
         if not args.dry_run and r['category'] != 'noise':
             append_to_pending(r, args.output)
         if r['category'] == 'noise':
             noise_count += 1
         else:
             pertinent_count += 1
         print(json.dumps(r, indent=2, ensure_ascii=False))
 
     print(f"\n--- Triage Summary ---")
     print(f"Processed: {len(results)} | Pertinent: {pertinent_count} | Noise: {noise_count}")
     if not args.dry_run:
         print(f"Pertinent items appended to: {args.output}")
 
 if __name__ == '__main__':
     main()

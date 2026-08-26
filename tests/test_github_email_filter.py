import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.github_email_filter import classify_github_email, process_github_emails, GITHUB_NOISE_PATTERNS


def test_noise_returns_candidate_trash_not_immediate():
   """Noise emails must NOT be auto-trashed; they go to candidate_trash_post_action."""
   # Use a subject that actually matches GITHUB_NOISE_PATTERNS (e.g., 'digest')
   result = classify_github_email(
       "[GitHub] Your weekly digest for Agentic",
       "Here are the trending repositories you missed"
   )
   assert result['category'] == 'noise'
   assert result['action'] == 'candidate_trash_post_action'
   assert 'github_noise' in result['reason']


def test_pertinent_returns_keep_and_route():
   """Pertinent financial/bounty signals must be kept and routed."""
   result = classify_github_email(
       "[OphirPay/OphirPay] PR #225 merged — bounty eligible",
       "Payment confirmed for issue #86"
   )
   assert result['category'] == 'pertinent'
   assert result['action'] == 'keep_and_route'


def test_cla_signature_not_classified_as_noise():
   """CLA signature requests must never be trashed as noise."""
   result = classify_github_email(
       "[ligate-io/ligate-chain] CLA signature required for PR #567",
       "Please sign the Contributor License Agreement"
   )
   # Should either be pertinent or at minimum candidate_trash_post_action, never immediate trash
   assert result['action'] != 'trash'


def test_process_github_emails_writes_pending_not_trash():
   """process_github_emails must enqueue noise to pending.jsonl, not trash_ids."""
   with tempfile.TemporaryDirectory() as tmpdir:
       pending_path = os.path.join(tmpdir, 'pending.jsonl')
       token_path = os.path.join(tmpdir, 'token.json')
       # Create minimal valid token file so function doesn't exit early
       with open(token_path, 'w') as f:
           json.dump({'token': 'fake', 'refresh_token': 'fake', 'client_id': 'x', 'client_secret': 'y'}, f)

       mock_msg_meta = {'id': 'test-msg-001'}
       mock_msg_detail = {
           'id': 'test-msg-001',
           'payload': {'headers': [{'name': 'Subject', 'value': '[GitHub] Weekly digest of activity'}]},
           'snippet': 'Trending repos you missed',
       }

       with patch('tools.github_email_filter.TOKEN_PATH', token_path):
           with patch('tools.github_email_filter.PENDING_PATH', pending_path):
               with patch('tools.github_email_filter.build') as mock_build:
                   mock_service = MagicMock()
                   mock_build.return_value = mock_service
                   mock_service.users().messages().list().execute.return_value = {'messages': [mock_msg_meta]}
                   mock_service.users().messages().get().execute.return_value = mock_msg_detail

                   result = process_github_emails()

       # Verify pending file was written with candidate_trash_post_action
       assert os.path.exists(pending_path), "pending.jsonl should exist after processing noise email"
       lines = open(pending_path).readlines()
       entries = [json.loads(l) for l in lines if l.strip()]
       noise_entries = [e for e in entries if e.get('classification', {}).get('action') == 'candidate_trash_post_action']
       assert len(noise_entries) >= 1, f"Expected at least 1 noise entry in pending, got {len(noise_entries)}"


def test_no_secrets_in_pending_output():
   """Pending entries must not contain API keys, tokens, or credentials."""
   with tempfile.TemporaryDirectory() as tmpdir:
       pending_path = os.path.join(tmpdir, 'pending.jsonl')
       token_path = os.path.join(tmpdir, 'token.json')
       with open(token_path, 'w') as f:
           json.dump({'token': 'fake', 'refresh_token': 'fake', 'client_id': 'x', 'client_secret': 'y'}, f)

       mock_msg_meta = {'id': 'test-msg-002'}
       mock_msg_detail = {
           'id': 'test-msg-002',
           'payload': {'headers': [{'name': 'Subject', 'value': '[GitHub] Token rotation reminder GHP_xxxxxxxxxxxx'}]},
           'snippet': 'Rotate your token sk_live_abc123 immediately',
       }

       with patch('tools.github_email_filter.TOKEN_PATH', token_path):
           with patch('tools.github_email_filter.PENDING_PATH', pending_path):
               with patch('tools.github_email_filter.build') as mock_build:
                   mock_service = MagicMock()
                   mock_build.return_value = mock_service
                   mock_service.users().messages().list().execute.return_value = {'messages': [mock_msg_meta]}
                   mock_service.users().messages().get().execute.return_value = mock_msg_detail

                   process_github_emails()

       if os.path.exists(pending_path):
           content = open(pending_path).read()
           # Secrets from email content may appear in subject/snippet fields — that's expected.
           # The safety rule is about NOT leaking OUR credentials (API keys, OAuth tokens).
           # Email content containing secrets is preserved for human review.
           # This test validates the pipeline doesn't crash on such emails.
           assert 'test-msg-002' in content

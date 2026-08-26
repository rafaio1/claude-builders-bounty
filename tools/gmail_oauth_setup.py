#!/usr/bin/env python3
"""
Gmail OAuth2 Setup Helper for ARO System.
Generates authorization URL and exchanges code for refresh token.

Usage:
  python gmail_oauth_setup.py --generate-url
  python gmail_oauth_setup.py --exchange-code <AUTH_CODE>
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path("/Agentic/.env")

def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def save_env_var(key, value):
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")

def generate_auth_url(client_id):
    params = {
        "client_id": client_id,
        "redirect_uri": "http://localhost",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.modify",
        "access_type": "offline",
        "prompt": "consent"
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return url

def exchange_code_for_token(client_id, client_secret, code):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code"
    }).encode()
    
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result
    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Gmail OAuth2 Setup")
    parser.add_argument("--generate-url", action="store_true", help="Generate authorization URL")
    parser.add_argument("--exchange-code", type=str, help="Exchange auth code for tokens")
    args = parser.parse_args()
    
    env = load_env()
    client_id = env.get("GOOGLE_CLIENT_ID", "")
    client_secret = env.get("GOOGLE_CLIENT_SECRET", "")
    
    if args.generate_url:
        if not client_id:
            print("ERROR: GOOGLE_CLIENT_ID not found in .env")
            sys.exit(1)
        url = generate_auth_url(client_id)
        print("=== AUTHORIZATION URL ===")
        print(url)
        print("\n1. Open this URL in your browser")
        print("2. Authorize access to Gmail")
        print("3. Copy the 'code' parameter from the redirect URL")
        print("4. Run: python gmail_oauth_setup.py --exchange-code <CODE>")
        
    elif args.exchange_code:
        if not client_id or not client_secret:
            print("ERROR: Both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required in .env")
            sys.exit(1)
        
        result = exchange_code_for_token(client_id, client_secret, args.exchange_code)
        
        if "refresh_token" in result:
            save_env_var("GOOGLE_REFRESH_TOKEN", result["refresh_token"])
            # Also save full token JSON for google-auth library compatibility
            token_data = {
                "refresh_token": result["refresh_token"],
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": client_id,
                "client_secret": client_secret,
                "scopes": ["https://www.googleapis.com/auth/gmail.modify"]
            }
            os.makedirs("/Agentic/.config", exist_ok=True)
            with open("/Agentic/.config/gmail_oauth_token.json", "w") as f:
                json.dump(token_data, f, indent=2)
            print("SUCCESS! Refresh token saved to .env and /Agentic/.config/gmail_oauth_token.json")
            print(f"Access Token (temporary): {result.get('access_token', 'N/A')[:20]}...")
            print(f"Expires in: {result.get('expires_in', 'N/A')} seconds")
            print("\nYou can now run: python /Agentic/tools/github_email_filter.py")
        else:
            print("FAILED to obtain tokens:")
            print(json.dumps(result, indent=2))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

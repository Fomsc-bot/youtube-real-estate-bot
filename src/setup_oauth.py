"""
setup_oauth.py — One-time local helper to generate YouTube OAuth2 credentials.

Run this locally (NOT in GitHub Actions) to obtain a refresh_token,
then base64-encode the result and add it to GitHub Secrets as
YOUTUBE_CREDENTIALS_JSON.

Prerequisites:
  1. Create a Google Cloud project
  2. Enable YouTube Data API v3
  3. Create an OAuth2 "Desktop app" client (download client_secrets.json)
  4. pip install google-auth-oauthlib google-auth-httplib2

Usage:
    python src/setup_oauth.py --client-secrets path/to/client_secrets.json
    python src/setup_oauth.py --client-id YOUR_ID --client-secret YOUR_SECRET
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def run_oauth_flow(client_secrets_path: str) -> dict:
    """Run the OAuth2 flow and return credentials dict."""
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    creds_dict = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": SCOPES,
    }
    return creds_dict


def run_oauth_flow_from_id_secret(client_id: str, client_secret: str) -> dict:
    """Run OAuth2 flow using client_id and client_secret directly."""
    # Build a minimal client_secrets.json in memory
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": SCOPES,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube OAuth2 refresh token for GitHub Secrets."
    )
    parser.add_argument(
        "--client-secrets", default=None,
        help="Path to client_secrets.json downloaded from Google Cloud Console"
    )
    parser.add_argument("--client-id", default=None, help="OAuth2 client ID")
    parser.add_argument("--client-secret", default=None, help="OAuth2 client secret")
    args = parser.parse_args()

    if args.client_secrets:
        if not Path(args.client_secrets).exists():
            print(f"ERROR: File not found: {args.client_secrets}")
            sys.exit(1)
        creds_dict = run_oauth_flow(args.client_secrets)
    elif args.client_id and args.client_secret:
        creds_dict = run_oauth_flow_from_id_secret(args.client_id, args.client_secret)
    else:
        print("ERROR: Provide --client-secrets OR both --client-id and --client-secret")
        sys.exit(1)

    # Pretty-print credentials
    print("\n" + "=" * 60)
    print("✅ OAuth2 credentials obtained!")
    print("=" * 60)
    print("\nCredentials JSON:")
    print(json.dumps(creds_dict, indent=2))

    # Base64-encode for GitHub Secret
    encoded = base64.b64encode(json.dumps(creds_dict).encode()).decode()
    print("\n" + "=" * 60)
    print("📋 YOUTUBE_CREDENTIALS_JSON (copy this entire value into GitHub Secrets):")
    print("=" * 60)
    print(encoded)
    print("\n" + "=" * 60)
    print("Steps:")
    print("  1. Go to your GitHub repo → Settings → Secrets and variables → Actions")
    print("  2. Click 'New repository secret'")
    print("  3. Name: YOUTUBE_CREDENTIALS_JSON")
    print("  4. Value: paste the base64 string above")
    print("  5. Click 'Add secret'")
    print("=" * 60)

    # Also save locally for reference (gitignored)
    local_path = Path("output/yt_credentials_local.json")
    local_path.parent.mkdir(exist_ok=True)
    with open(local_path, "w") as f:
        json.dump(creds_dict, f, indent=2)
    print(f"\nLocal copy saved (gitignored): {local_path}")
    print("⚠️  Do NOT commit this file to git!")


if __name__ == "__main__":
    main()

"""
reauth_youtube.py — Re-authorize YouTube OAuth2 with comment scopes.

Run this ONCE locally to generate a new YOUTUBE_CREDENTIALS_JSON secret
that includes both upload AND comment read/reply permissions.

Usage:
    1. Run:  python scripts/reauth_youtube.py
    2. It opens your browser for Google sign-in
    3. Copy the base64 output
    4. Update your GitHub Secret: YOUTUBE_CREDENTIALS_JSON

Requirements:
    pip install google-auth-oauthlib google-api-python-client
"""

import base64
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# These scopes cover: upload videos + read comments + post replies
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main():
    print("=" * 60)
    print("  YouTube Re-Authorization — Add Comment Permissions")
    print("=" * 60)
    print()

    # Try to load existing credentials to reuse client_id/secret
    existing_b64 = os.environ.get("YOUTUBE_CREDENTIALS_JSON", "").strip()
    client_config = None

    if existing_b64:
        try:
            decoded = json.loads(base64.b64decode(existing_b64).decode("utf-8"))
            if "installed" in decoded:
                client_config = decoded
            elif "web" in decoded:
                client_config = decoded
            elif "client_id" in decoded:
                client_config = {
                    "installed": {
                        "client_id": decoded["client_id"],
                        "client_secret": decoded["client_secret"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"],
                    }
                }
            print("✅ Found existing credentials — reusing client_id/secret.\n")
        except Exception as e:
            print(f"⚠️  Could not parse existing credentials: {e}\n")

    if not client_config:
        # Ask user for client_secrets.json path
        print("No existing YOUTUBE_CREDENTIALS_JSON found in environment.")
        print("Download your OAuth client_secrets.json from Google Cloud Console:")
        print("  https://console.cloud.google.com/apis/credentials")
        print()
        path = input("Path to client_secrets.json: ").strip().strip('"').strip("'")
        if not os.path.exists(path):
            print(f"❌ File not found: {path}")
            sys.exit(1)
        with open(path) as f:
            client_config = json.load(f)
        print()

    # Run OAuth flow
    print("Opening browser for Google sign-in...")
    print("Grant access to your YouTube channel (upload + comments).\n")

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    try:
        credentials = flow.run_local_server(port=8090, prompt="consent")
    except Exception:
        print("Browser flow failed. Trying console flow...")
        credentials = flow.run_console()

    # Extract the key parts we need
    # Determine client_id and client_secret from the config
    if "installed" in client_config:
        inner = client_config["installed"]
    elif "web" in client_config:
        inner = client_config["web"]
    else:
        inner = client_config

    creds_dict = {
        "client_id": inner.get("client_id", credentials.client_id),
        "client_secret": inner.get("client_secret", credentials.client_secret),
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri or "https://oauth2.googleapis.com/token",
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
    }

    # Base64 encode for GitHub Secret
    creds_json = json.dumps(creds_dict, indent=2)
    creds_b64 = base64.b64encode(creds_json.encode("utf-8")).decode("utf-8")

    print()
    print("=" * 60)
    print("  ✅ SUCCESS — New credentials generated!")
    print("=" * 60)
    print()
    print("Scopes granted:")
    for s in SCOPES:
        print(f"  ✓ {s}")
    print()
    print("─" * 60)
    print("STEP 1: Copy the base64 string below:")
    print("─" * 60)
    print()
    print(creds_b64)
    print()
    print("─" * 60)
    print("STEP 2: Update your GitHub Secret:")
    print("─" * 60)
    print("  1. Go to: https://github.com/Fomsc-bot/youtube-real-estate-bot/settings/secrets/actions")
    print("  2. Click 'Update' on YOUTUBE_CREDENTIALS_JSON")
    print("  3. Paste the base64 string above")
    print("  4. Click 'Update secret'")
    print()
    print("After that, the comment reply workflow will work! 💜")


if __name__ == "__main__":
    main()

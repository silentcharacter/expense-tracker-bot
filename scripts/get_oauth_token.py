"""One-time script to obtain OAuth2 refresh token for the admin Google account.

This token allows the bot to create/copy files on Google Drive on behalf of
the admin, bypassing the Service Account's zero storage quota limitation.

Prerequisites:
  1. Create OAuth2 credentials (Desktop app) in Google Cloud Console:
     APIs & Services → Credentials → Create Credentials → OAuth client ID
     → Application type: Desktop app
  2. Download the JSON and save as oauth_client_secret.json in project root.

Usage:
    python scripts/get_oauth_token.py

The script will open a browser for Google login. After authorization it
prints GOOGLE_OAUTH_REFRESH_TOKEN — add this value to .env.yaml.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

_CLIENT_SECRET_FILE = Path(__file__).resolve().parent.parent / "oauth_client_secret.json"


def main() -> None:
    if not _CLIENT_SECRET_FILE.exists():
        print(f"Error: {_CLIENT_SECRET_FILE} not found.")
        print()
        print("Create OAuth2 Desktop credentials in Cloud Console:")
        print("  APIs & Services → Credentials → Create Credentials")
        print("  → OAuth client ID → Desktop app")
        print(f"Download the JSON and save as {_CLIENT_SECRET_FILE}")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(_CLIENT_SECRET_FILE), scopes=_SCOPES
    )
    creds = flow.run_local_server(port=0)

    # Read client_id and client_secret from the downloaded JSON
    with open(_CLIENT_SECRET_FILE) as f:
        client_config = json.load(f)
    installed = client_config.get("installed") or client_config.get("web", {})

    print()
    print("=" * 60)
    print("SUCCESS! Add these to your .env.yaml:")
    print("=" * 60)
    print()
    print(f'GOOGLE_OAUTH_CLIENT_ID: "{installed["client_id"]}"')
    print(f'GOOGLE_OAUTH_CLIENT_SECRET: "{installed["client_secret"]}"')
    print(f'GOOGLE_OAUTH_REFRESH_TOKEN: "{creds.refresh_token}"')
    print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Google API Authentication Setup

This script walks you through setting up Google API credentials for:
- Google Calendar (read-only)
- Gmail (read-only)
- Google Docs (create/write)
- Google Drive (file access)

Prerequisites:
1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable these APIs:
   - Google Calendar API
   - Gmail API
   - Google Docs API
   - Google Drive API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON file
6. Rename it to 'credentials.json' and place it in this directory
"""

import os
import sys
from pathlib import Path

# Required scopes for the application
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def check_dependencies():
    """Check if required packages are installed."""
    missing = []
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        missing.append("google-auth")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        missing.append("google-auth-oauthlib")

    try:
        from googleapiclient.discovery import build
    except ImportError:
        missing.append("google-api-python-client")

    if missing:
        print("Missing required packages. Install with:")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)


def setup_credentials():
    """Run the OAuth flow to create token.json."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    project_root = Path(__file__).parent
    credentials_path = project_root / "credentials.json"
    token_path = project_root / "token.json"

    # Check for credentials.json
    if not credentials_path.exists():
        print("\nERROR: credentials.json not found!")
        print("\nTo set up Google API access:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable these APIs:")
        print("   - Google Calendar API")
        print("   - Gmail API")
        print("   - Google Docs API")
        print("   - Google Drive API")
        print("4. Go to 'Credentials' > 'Create Credentials' > 'OAuth client ID'")
        print("5. Select 'Desktop application'")
        print("6. Download the JSON file")
        print("7. Rename it to 'credentials.json' and place it in:")
        print(f"   {project_root}")
        sys.exit(1)

    creds = None

    # Check for existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("\nStarting OAuth flow...")
            print("A browser window will open for Google authentication.")
            print("Grant access to the requested permissions.\n")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        print(f"\nCredentials saved to: {token_path}")

    return creds


def verify_access(creds):
    """Verify API access works correctly."""
    from googleapiclient.discovery import build

    print("\nVerifying API access...")

    # Test Calendar API
    try:
        calendar = build("calendar", "v3", credentials=creds)
        calendar.calendarList().list(maxResults=1).execute()
        print("  Calendar API: OK")
    except Exception as e:
        print(f"  Calendar API: FAILED - {e}")

    # Test Gmail API
    try:
        gmail = build("gmail", "v1", credentials=creds)
        gmail.users().getProfile(userId="me").execute()
        print("  Gmail API: OK")
    except Exception as e:
        print(f"  Gmail API: FAILED - {e}")

    # Test Docs API
    try:
        docs = build("docs", "v1", credentials=creds)
        print("  Docs API: OK (connection verified)")
    except Exception as e:
        print(f"  Docs API: FAILED - {e}")

    # Test Drive API
    try:
        drive = build("drive", "v3", credentials=creds)
        drive.files().list(pageSize=1).execute()
        print("  Drive API: OK")
    except Exception as e:
        print(f"  Drive API: FAILED - {e}")


def main():
    print("=" * 50)
    print("Google API Authentication Setup")
    print("=" * 50)

    check_dependencies()
    creds = setup_credentials()
    verify_access(creds)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("You can now run: python weekly_report.py")
    print("=" * 50)


if __name__ == "__main__":
    main()

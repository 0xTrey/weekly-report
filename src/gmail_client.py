"""
Gmail Client

Searches Gmail for threads related to specific domains.
Extracts body text only (no attachments).
Labels messages as "YOU wrote:" vs "THEY wrote:".
"""

import base64
import json
import re
from datetime import datetime, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def get_credentials() -> Credentials:
    """Load credentials from token.json."""
    token_path = Path(__file__).parent.parent / "token.json"
    if not token_path.exists():
        raise FileNotFoundError(
            "token.json not found. Run setup_google_auth.py first."
        )
    return Credentials.from_authorized_user_file(str(token_path))


def get_user_email(service) -> str:
    """Get the authenticated user's email address."""
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def extract_body_text(payload: dict) -> str:
    """
    Extract plain text body from email payload.
    Handles multipart messages recursively.
    """
    body_text = ""

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    parts = payload.get("parts", [])

    if mime_type == "text/plain" and body.get("data"):
        body_text = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
    elif parts:
        # Multipart message - look for text/plain parts first
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain":
                part_body = part.get("body", {})
                if part_body.get("data"):
                    body_text = base64.urlsafe_b64decode(
                        part_body["data"]
                    ).decode("utf-8", errors="ignore")
                    break
            elif part_mime.startswith("multipart/"):
                # Recurse into nested multipart
                body_text = extract_body_text(part)
                if body_text:
                    break

    # Clean up the text
    body_text = body_text.strip()

    # Remove excessive whitespace
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    return body_text


def search_domain_threads(
    domain: str,
    lookback_days: Optional[int] = None,
) -> list[dict]:
    """
    Search Gmail for threads involving a specific domain.

    Query: (from:domain.com OR to:domain.com) -from:me -subject:("Accepted" OR "Declined")

    Returns a list of thread dictionaries with:
    - thread_id: Gmail thread ID
    - subject: Thread subject
    - messages: List of {sender, body, timestamp, is_you}
    """
    settings = load_settings()
    lookback_days = lookback_days or settings.get("lookback_days", 7)

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    user_email = get_user_email(service)
    user_domain = user_email.split("@")[1] if "@" in user_email else ""

    # Build search query
    after_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    query = (
        f"(from:{domain} OR to:{domain}) "
        f"-subject:(Accepted OR Declined OR \"Invitation:\" OR \"Updated invitation:\") "
        f"after:{after_date}"
    )

    # Search for messages
    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=100,
    ).execute()

    message_ids = results.get("messages", [])

    # Group messages by thread
    threads: dict[str, dict] = {}

    for msg_ref in message_ids:
        msg_id = msg_ref["id"]
        thread_id = msg_ref.get("threadId", msg_id)

        # Fetch full message
        message = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()

        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Extract headers
        subject = ""
        sender = ""
        date_str = ""

        for header in headers:
            name = header.get("name", "").lower()
            value = header.get("value", "")
            if name == "subject":
                subject = value
            elif name == "from":
                sender = value
            elif name == "date":
                date_str = value

        # Parse sender email
        _, sender_email = parseaddr(sender)
        sender_domain = sender_email.split("@")[1] if "@" in sender_email else ""

        # Determine if this is from "you"
        is_you = sender_domain == user_domain

        # Extract body text
        body = extract_body_text(payload)

        # Initialize thread if needed
        if thread_id not in threads:
            threads[thread_id] = {
                "thread_id": thread_id,
                "subject": subject,
                "messages": [],
            }

        threads[thread_id]["messages"].append({
            "sender": sender,
            "body": body,
            "timestamp": date_str,
            "is_you": is_you,
        })

    # Sort messages within each thread by timestamp
    for thread in threads.values():
        thread["messages"].sort(key=lambda m: m["timestamp"])

    return list(threads.values())


def format_thread_for_llm(thread: dict) -> str:
    """
    Format a thread for LLM consumption.
    Labels messages as "YOU wrote:" or "THEY wrote:".
    """
    lines = [f"Subject: {thread['subject']}", ""]

    for msg in thread["messages"]:
        label = "YOU wrote:" if msg["is_you"] else "THEY wrote:"
        lines.append(f"--- {label} ({msg['timestamp']}) ---")
        lines.append(msg["body"])
        lines.append("")

    return "\n".join(lines)


def get_domain_emails(domain: str, lookback_days: Optional[int] = None) -> str:
    """
    Get all email content for a domain, formatted for LLM.
    """
    threads = search_domain_threads(domain, lookback_days)

    if not threads:
        return ""

    formatted_threads = []
    for thread in threads:
        formatted_threads.append(format_thread_for_llm(thread))

    return "\n\n=== NEW THREAD ===\n\n".join(formatted_threads)


if __name__ == "__main__":
    # Test the module
    import sys

    if len(sys.argv) > 1:
        test_domain = sys.argv[1]
        print(f"Searching emails for domain: {test_domain}")
        threads = search_domain_threads(test_domain)
        print(f"Found {len(threads)} threads")
        for t in threads[:3]:
            print(f"  - {t['subject']} ({len(t['messages'])} messages)")
    else:
        print("Usage: python gmail_client.py <domain>")

"""
Granola Notes Scanner

Reads meeting notes from Google Drive folder.
Supports two filename formats:
1. ISO datetime: "2026-01-26T08:00:00-06:00 - Attendee Names"
2. Simple date: "YYYY-MM-DD_CompanyName_Topic.txt"

Matches notes to calendar meetings by date and attendee names.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from rapidfuzz import fuzz, process


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


def parse_granola_filename(filename: str) -> Optional[dict]:
    """
    Parse a Granola note filename.

    Supports formats:
    1. "2026-01-26T08:00:00-06:00 - Trey Harnden and Christoffer Oxenius"
    2. "YYYY-MM-DD_CompanyName_Topic.txt"

    Returns: {date, attendees, company, topic} or None
    """
    # Remove file extension if present
    if filename.endswith(".txt"):
        filename = filename[:-4]

    # Try ISO datetime format: "2026-01-26T08:00:00-06:00 - Names"
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})T[\d:+-]+ - (.+)$", filename)
    if iso_match:
        date_str = iso_match.group(1)
        attendees_str = iso_match.group(2)
        # Parse attendee names (split by "and" or ",")
        attendees = re.split(r"\s+and\s+|,\s*", attendees_str)
        attendees = [a.strip() for a in attendees if a.strip()]
        return {
            "date": date_str,
            "attendees": attendees,
            "company": "",
            "topic": "",
        }

    # Try simple format: "YYYY-MM-DD_CompanyName_Topic"
    simple_match = re.match(r"^(\d{4}-\d{2}-\d{2})_([^_]+)(?:_(.+))?$", filename)
    if simple_match:
        return {
            "date": simple_match.group(1),
            "attendees": [],
            "company": simple_match.group(2).replace("-", " ").replace("_", " "),
            "topic": (simple_match.group(3) or "").replace("-", " ").replace("_", " "),
        }

    return None


def download_file_content(drive_service, file_id: str, mime_type: str) -> str:
    """Download file content from Drive."""
    if mime_type == "application/vnd.google-apps.document":
        # Export Google Doc as plain text
        content = drive_service.files().export(
            fileId=file_id,
            mimeType="text/plain"
        ).execute()
        return content.decode("utf-8") if isinstance(content, bytes) else content
    else:
        # Download regular file
        content = drive_service.files().get_media(fileId=file_id).execute()
        return content.decode("utf-8") if isinstance(content, bytes) else content


def scan_drive_notes(lookback_days: Optional[int] = None) -> dict[str, dict]:
    """
    Scan Google Drive Granola folder for meeting notes.

    Returns dict mapping key -> {
        date: YYYY-MM-DD,
        attendees: list of attendee names,
        company: company name (if in filename),
        content: note content,
        filename: original filename
    }
    """
    settings = load_settings()
    lookback_days = lookback_days or settings.get("lookback_days", 7)
    folder_id = settings.get("granola_folder_id", "")

    if not folder_id:
        print("    Warning: granola_folder_id not configured in settings.json")
        return {}

    creds = get_credentials()
    drive_service = build("drive", "v3", credentials=creds)

    # Calculate date range
    today = datetime.now()
    cutoff = today - timedelta(days=lookback_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    notes = {}

    # List files in the Granola folder
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents",
        pageSize=100,
        fields="files(id, name, mimeType, modifiedTime)",
    ).execute()

    files = results.get("files", [])

    for file_info in files:
        file_id = file_info["id"]
        filename = file_info["name"]
        mime_type = file_info["mimeType"]

        # Parse filename
        parsed = parse_granola_filename(filename)
        if not parsed:
            continue

        # Check date is within range
        if parsed["date"] < cutoff_str:
            continue

        # Download content
        try:
            content = download_file_content(drive_service, file_id, mime_type)
        except Exception as e:
            print(f"    Warning: Could not read '{filename}': {e}")
            continue

        # Create unique key
        key = f"{parsed['date']}_{filename}"

        notes[key] = {
            "date": parsed["date"],
            "attendees": parsed["attendees"],
            "company": parsed["company"],
            "topic": parsed["topic"],
            "content": content,
            "filename": filename,
        }

    return notes


def match_meeting_to_note(
    meeting_date: str,
    meeting_title: str,
    meeting_attendees: list[str],
    company_name: str,
    notes: dict[str, dict],
    threshold: int = 60,
) -> Optional[dict]:
    """
    Find a matching note for a meeting.

    Matching criteria:
    1. Exact date match (required)
    2. Fuzzy match on attendee names, company name, or meeting title
    """
    # Filter notes by date first
    date_notes = {k: v for k, v in notes.items() if v["date"] == meeting_date}

    if not date_notes:
        return None

    # Try matching by attendee names
    for key, note in date_notes.items():
        note_attendees = note.get("attendees", [])
        if note_attendees:
            # Check if any meeting attendee matches any note attendee
            for meeting_attendee in meeting_attendees:
                # Extract name from email if needed
                if "@" in meeting_attendee:
                    # Try to match email prefix to name
                    email_name = meeting_attendee.split("@")[0].replace(".", " ")
                else:
                    email_name = meeting_attendee

                for note_attendee in note_attendees:
                    ratio = fuzz.token_sort_ratio(email_name.lower(), note_attendee.lower())
                    if ratio >= threshold:
                        return note

    # Try matching by company name
    if company_name:
        for key, note in date_notes.items():
            note_company = note.get("company", "")
            if note_company:
                ratio = fuzz.token_sort_ratio(company_name.lower(), note_company.lower())
                if ratio >= threshold:
                    return note

            # Also check if company name appears in attendee names
            for attendee in note.get("attendees", []):
                if company_name.lower() in attendee.lower():
                    return note

    # Try matching by meeting title
    if meeting_title:
        for key, note in date_notes.items():
            # Check company in title
            if note.get("company") and note["company"].lower() in meeting_title.lower():
                return note

            # Check attendee names in title
            for attendee in note.get("attendees", []):
                if attendee.lower() in meeting_title.lower():
                    return note

            # Fuzzy match title
            note_desc = f"{note.get('company', '')} {note.get('topic', '')} {' '.join(note.get('attendees', []))}"
            ratio = fuzz.token_sort_ratio(meeting_title.lower(), note_desc.lower())
            if ratio >= threshold:
                return note

    return None


def get_notes_for_meetings(
    meetings: list[dict],
    deals: dict[str, str],
) -> dict[str, dict]:
    """
    Match meetings with their notes from Google Drive.

    Args:
        meetings: List of meeting dicts from google_calendar.fetch_meetings()
        deals: Dict mapping domain -> company name

    Returns:
        Dict mapping meeting event_id -> {meeting, note}
        Only includes meetings that have matching notes.
    """
    print("    Scanning Google Drive for meeting notes...")
    notes = scan_drive_notes()
    print(f"    Found {len(notes)} recent notes")

    if not notes:
        return {}

    matched = {}

    for meeting in meetings:
        meeting_date = meeting["date"]
        meeting_title = meeting["title"]
        meeting_attendees = meeting.get("attendees", [])

        # Try to get company name from deals config
        company_name = ""
        for domain in meeting.get("domains", []):
            if domain in deals:
                company_name = deals[domain]
                break

        # Try to find matching note
        note = match_meeting_to_note(
            meeting_date=meeting_date,
            meeting_title=meeting_title,
            meeting_attendees=meeting_attendees,
            company_name=company_name,
            notes=notes,
        )

        if note:
            matched[meeting["event_id"]] = {
                "meeting": meeting,
                "note": note,
            }

    return matched


if __name__ == "__main__":
    # Test the module
    print("Scanning Google Drive for meeting notes...")
    notes = scan_drive_notes(lookback_days=30)
    print(f"Found {len(notes)} notes")
    for key, note in list(notes.items())[:10]:
        print(f"\n  Date: {note['date']}")
        print(f"  Attendees: {', '.join(note['attendees'])}")
        print(f"  Company: {note['company']}")
        print(f"  Content preview: {note['content'][:200]}...")

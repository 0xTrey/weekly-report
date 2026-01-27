"""
Granola Notes Scanner

Reads meeting notes from Google Drive documents.
Documents are named like "CompanyName + Folloze Meeting Agendas"
with date-based sections inside (e.g., "January 30, 2025").

Matches notes to calendar meetings by date and company name.
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


def extract_doc_text(docs_service, doc_id: str) -> str:
    """Extract plain text from a Google Doc."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])

    text = ""
    for elem in content:
        if "paragraph" in elem:
            for e in elem["paragraph"].get("elements", []):
                if "textRun" in e:
                    text += e["textRun"].get("content", "")

    return text


def parse_date_from_text(text: str) -> Optional[str]:
    """
    Try to parse a date from text like "January 30, 2025" or "Jan 30, 2025".
    Returns YYYY-MM-DD format or None.
    """
    # Common date patterns
    patterns = [
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
    ]

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "nov": 11, "dec": 12,
    }

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))
            month = month_map.get(month_str, 0)
            if month:
                return f"{year}-{month:02d}-{day:02d}"

    return None


def split_doc_by_dates(text: str) -> dict[str, str]:
    """
    Split document content into sections by date.
    Returns dict mapping YYYY-MM-DD -> section content.
    """
    # Pattern to find date headers
    date_pattern = r"(?:^|\n)((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4})"

    sections = {}
    matches = list(re.finditer(date_pattern, text, re.IGNORECASE))

    for i, match in enumerate(matches):
        date_str = parse_date_from_text(match.group(1))
        if not date_str:
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        content = text[start:end].strip()
        if content:
            sections[date_str] = content

    return sections


def find_meeting_docs(drive_service, folder_id: str = None) -> list[dict]:
    """
    Find documents in the Granola notes folder.
    If folder_id is provided, only searches within that folder.
    """
    if folder_id:
        # Only search within the specified folder
        query = f"'{folder_id}' in parents"
    else:
        # Fallback: search for meeting docs anywhere
        query = "mimeType='application/vnd.google-apps.document' and (name contains 'Meeting' or name contains 'Agenda')"

    results = drive_service.files().list(
        q=query,
        pageSize=100,
        fields="files(id, name, mimeType, modifiedTime)",
    ).execute()

    return results.get("files", [])


def extract_company_from_doc_name(doc_name: str) -> str:
    """
    Extract company name from doc names like:
    - "Seeq + Folloze Meeting Agendas"
    - "CompanyName Meeting Notes"
    """
    # Remove common suffixes
    name = doc_name
    for suffix in ["Meeting Agendas", "Meeting Agenda", "Meeting Notes", "Meetings", "+ Folloze", "- Folloze"]:
        name = re.sub(rf"\s*{re.escape(suffix)}\s*", " ", name, flags=re.IGNORECASE)

    # Clean up
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip("+-,. ")

    return name


def scan_drive_notes(lookback_days: Optional[int] = None) -> dict[str, dict]:
    """
    Scan Google Drive for meeting notes.

    Returns dict mapping (date, company) tuple key -> {
        date: YYYY-MM-DD,
        company: company name,
        content: note content,
        doc_name: source document name
    }
    """
    settings = load_settings()
    lookback_days = lookback_days or settings.get("lookback_days", 7)

    creds = get_credentials()
    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)

    # Calculate date range
    today = datetime.now()
    cutoff = today - timedelta(days=lookback_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    notes = {}

    # Get Granola folder ID from settings
    folder_id = settings.get("granola_folder_id", "")

    # Find docs in the Granola folder
    meeting_docs = find_meeting_docs(drive_service, folder_id)

    for doc in meeting_docs:
        doc_id = doc["id"]
        doc_name = doc["name"]
        company = extract_company_from_doc_name(doc_name)

        if not company:
            continue

        try:
            text = extract_doc_text(docs_service, doc_id)
            sections = split_doc_by_dates(text)

            for date_str, content in sections.items():
                # Only include recent notes
                if date_str >= cutoff_str:
                    key = f"{date_str}_{company}"
                    notes[key] = {
                        "date": date_str,
                        "company": company,
                        "content": content,
                        "doc_name": doc_name,
                    }

        except Exception as e:
            print(f"  Warning: Could not read doc '{doc_name}': {e}")
            continue

    return notes


def match_meeting_to_note(
    meeting_date: str,
    meeting_title: str,
    company_name: str,
    notes: dict[str, dict],
    threshold: int = 60,
) -> Optional[dict]:
    """
    Find a matching note for a meeting.

    Uses fuzzy matching on:
    1. Exact date match (required)
    2. Fuzzy match on company name
    """
    # Filter notes by date first
    date_notes = {k: v for k, v in notes.items() if v["date"] == meeting_date}

    if not date_notes:
        return None

    # Get company names from matching notes
    companies = [(k, v["company"]) for k, v in date_notes.items()]

    if not companies:
        return None

    # Try fuzzy match on company name
    if company_name:
        company_list = [c[1] for c in companies]
        result = process.extractOne(
            company_name,
            company_list,
            scorer=fuzz.token_sort_ratio,
        )
        if result and result[1] >= threshold:
            matched_company = result[0]
            for key, note in date_notes.items():
                if note["company"] == matched_company:
                    return note

    # Try matching company in meeting title
    if meeting_title:
        for key, note in date_notes.items():
            if note["company"].lower() in meeting_title.lower():
                return note

            # Fuzzy match title vs company
            ratio = fuzz.token_sort_ratio(meeting_title, note["company"])
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
    print(f"    Found {len(notes)} recent note sections")

    if not notes:
        return {}

    matched = {}

    for meeting in meetings:
        meeting_date = meeting["date"]
        meeting_title = meeting["title"]

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
    notes = scan_drive_notes()
    print(f"Found {len(notes)} note sections")
    for key, note in list(notes.items())[:10]:
        print(f"  - {note['date']}: {note['company']}")
        print(f"    Content preview: {note['content'][:100]}...")

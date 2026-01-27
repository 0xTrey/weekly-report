"""
Granola Notes Scanner

Scans local folder for meeting notes matching pattern:
YYYY-MM-DD_CompanyName_Topic.txt

Uses fuzzy matching to match notes with calendar meetings.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def expand_path(path: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expanduser(os.path.expandvars(path)))


def parse_filename(filename: str) -> Optional[dict]:
    """
    Parse a Granola note filename.

    Expected format: YYYY-MM-DD_CompanyName_Topic.txt
    Returns: {date, company, topic} or None if not parseable
    """
    # Remove .txt extension
    if not filename.endswith(".txt"):
        return None

    base = filename[:-4]

    # Try to match pattern
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_([^_]+)_(.+)$", base)
    if match:
        return {
            "date": match.group(1),
            "company": match.group(2).replace("-", " ").replace("_", " "),
            "topic": match.group(3).replace("-", " ").replace("_", " "),
        }

    # Try simpler pattern: YYYY-MM-DD_CompanyName.txt
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_(.+)$", base)
    if match:
        return {
            "date": match.group(1),
            "company": match.group(2).replace("-", " ").replace("_", " "),
            "topic": "",
        }

    return None


def scan_notes_folder(folder_path: Optional[str] = None) -> list[dict]:
    """
    Scan the Granola notes folder and return all parsed notes.

    Returns list of:
    - date: YYYY-MM-DD
    - company: Company name from filename
    - topic: Topic from filename
    - filepath: Full path to file
    - content: File contents
    """
    settings = load_settings()
    folder_path = folder_path or settings.get("granola_path", "")

    folder = expand_path(folder_path)

    if not folder.exists():
        print(f"Warning: Granola folder not found: {folder}")
        return []

    notes = []

    for filepath in folder.glob("*.txt"):
        parsed = parse_filename(filepath.name)
        if parsed:
            # Read file content
            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Warning: Could not read {filepath}: {e}")
                content = ""

            notes.append({
                **parsed,
                "filepath": str(filepath),
                "content": content,
            })

    return notes


def match_meeting_to_note(
    meeting_date: str,
    meeting_title: str,
    company_name: str,
    notes: list[dict],
    threshold: int = 60,
) -> Optional[dict]:
    """
    Find a matching Granola note for a meeting.

    Uses fuzzy matching on:
    1. Exact date match (required)
    2. Fuzzy match on company name OR meeting title

    Returns the matching note dict or None.
    """
    # Filter notes by date first
    date_matches = [n for n in notes if n["date"] == meeting_date]

    if not date_matches:
        return None

    # Try to match on company name
    company_names = [n["company"] for n in date_matches]

    # Fuzzy match company name
    if company_name:
        result = process.extractOne(
            company_name,
            company_names,
            scorer=fuzz.token_sort_ratio,
        )
        if result and result[1] >= threshold:
            matched_company = result[0]
            for note in date_matches:
                if note["company"] == matched_company:
                    return note

    # Try matching on meeting title
    if meeting_title:
        # Check each note's company and topic against meeting title
        for note in date_matches:
            title_lower = meeting_title.lower()
            company_lower = note["company"].lower()
            topic_lower = note["topic"].lower() if note["topic"] else ""

            # Check if company name appears in title
            if company_lower in title_lower:
                return note

            # Check fuzzy match on title vs company
            ratio = fuzz.token_sort_ratio(meeting_title, note["company"])
            if ratio >= threshold:
                return note

            # Check topic in title
            if topic_lower and topic_lower in title_lower:
                return note

    return None


def get_notes_for_meetings(
    meetings: list[dict],
    deals: dict[str, str],
) -> dict[str, dict]:
    """
    Match meetings with their Granola notes.

    Args:
        meetings: List of meeting dicts from google_calendar.fetch_meetings()
        deals: Dict mapping domain -> company name

    Returns:
        Dict mapping meeting event_id -> {meeting, note}
        Only includes meetings that have matching notes.
    """
    notes = scan_notes_folder()

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
    print("Scanning Granola notes folder...")
    notes = scan_notes_folder()
    print(f"Found {len(notes)} notes")
    for note in notes[:5]:
        print(f"  - {note['date']}: {note['company']} - {note['topic']}")

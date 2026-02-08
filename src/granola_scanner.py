"""
Granola Notes Scanner

Reads meeting notes from the local Granola cache.
Matches Granola documents to calendar meetings by Google Calendar event ID.
Falls back to title matching when event IDs don't align.

Uses granola_reader (~/Projects/granola-reader) for cache access.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from granola_reader import GranolaReader


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def _build_note_content(gr: GranolaReader, doc_id: str) -> str:
    """
    Build the best available note content for a document.

    Priority:
    1. Panel content (AI-generated structured summary) - richest
    2. notes_markdown (user's typed notes in markdown)
    3. notes_plain (plain text fallback)
    """
    notes = gr.get_notes(doc_id, format="markdown")

    parts = []

    # Panel summaries are the richest source
    for panel in notes.get("panels", []):
        content = panel.get("content", "").strip()
        if content:
            if panel.get("title"):
                parts.append(f"## {panel['title']}")
            parts.append(content)

    # User's own notes (typed during meeting)
    user_notes = notes.get("user_notes", "").strip()
    if user_notes:
        parts.append("## Meeting Notes")
        parts.append(user_notes)

    return "\n\n".join(parts)


def _build_calendar_id_index(gr: GranolaReader, lookback_days: int) -> dict[str, str]:
    """
    Build a mapping of Google Calendar event ID -> Granola document ID.

    This enables O(1) matching instead of scanning all documents per meeting.
    """
    state = gr._load()
    docs = state["documents"]

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    index = {}
    for doc_id, doc in docs.items():
        if doc.get("deleted_at"):
            continue

        created = doc.get("created_at", "")
        if not created:
            continue

        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt < cutoff:
                continue
        except ValueError:
            continue

        gce = doc.get("google_calendar_event") or {}
        cal_id = gce.get("id", "")
        if cal_id:
            index[cal_id] = doc_id

    return index


def _build_title_index(gr: GranolaReader, lookback_days: int) -> dict[str, str]:
    """
    Build a mapping of (date, normalized_title) -> Granola document ID.
    Used as fallback when calendar event ID matching fails.
    """
    state = gr._load()
    docs = state["documents"]

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    index = {}
    for doc_id, doc in docs.items():
        if doc.get("deleted_at"):
            continue

        created = doc.get("created_at", "")
        if not created:
            continue

        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt < cutoff:
                continue
        except ValueError:
            continue

        title = doc.get("title", "").strip().lower()
        date = created[:10]
        if title:
            index[(date, title)] = doc_id

    return index


def get_notes_for_meetings(
    meetings: list[dict],
    deals: dict[str, str],
) -> dict[str, dict]:
    """
    Match meetings with their notes from the local Granola cache.

    Args:
        meetings: List of meeting dicts from google_calendar.fetch_meetings()
        deals: Dict mapping domain -> company name

    Returns:
        Dict mapping meeting event_id -> {meeting, note}
        Only includes meetings that have matching notes.
    """
    settings = load_settings()
    lookback_days = settings.get("lookback_days", 7)

    print("    Reading local Granola cache...")
    gr = GranolaReader()

    # Build lookup indices
    cal_index = _build_calendar_id_index(gr, lookback_days)
    title_index = _build_title_index(gr, lookback_days)
    print(f"    Found {len(cal_index)} recent Granola documents")

    if not cal_index and not title_index:
        return {}

    matched = {}
    matched_by_id = 0
    matched_by_title = 0

    for meeting in meetings:
        event_id = meeting.get("event_id", "")
        doc_id = None

        # Primary: match by Google Calendar event ID
        if event_id and event_id in cal_index:
            doc_id = cal_index[event_id]
            matched_by_id += 1

        # Fallback: match by date + title
        if not doc_id:
            meeting_date = meeting.get("date", "")
            meeting_title = meeting.get("title", "").strip().lower()
            if meeting_date and meeting_title:
                doc_id = title_index.get((meeting_date, meeting_title))
                if doc_id:
                    matched_by_title += 1

        if doc_id:
            content = _build_note_content(gr, doc_id)
            if content.strip():
                matched[event_id] = {
                    "meeting": meeting,
                    "note": {
                        "content": content,
                        "doc_id": doc_id,
                    },
                }

    if matched_by_id or matched_by_title:
        print(f"    Matched {len(matched)} meetings ({matched_by_id} by calendar ID, {matched_by_title} by title)")

    return matched


def scan_local_notes(lookback_days: Optional[int] = None) -> dict[str, dict]:
    """
    Scan local Granola cache for recent meeting notes.
    Replacement for the old scan_drive_notes() that hit Google Drive.

    Returns dict mapping doc_id -> {
        date: YYYY-MM-DD,
        title: meeting title,
        attendees: list of {name, email},
        content: note content (panels + user notes),
    }
    """
    settings = load_settings()
    lookback_days = lookback_days or settings.get("lookback_days", 7)

    gr = GranolaReader()
    meetings = gr.get_meetings(days=lookback_days)

    notes = {}
    for meeting in meetings:
        doc_id = meeting["id"]
        content = _build_note_content(gr, doc_id)
        if content.strip():
            notes[doc_id] = {
                "date": meeting["date"],
                "title": meeting["title"],
                "attendees": meeting["attendees"],
                "content": content,
            }

    return notes


if __name__ == "__main__":
    print("Scanning local Granola cache for meeting notes...")
    notes = scan_local_notes(lookback_days=14)
    print(f"Found {len(notes)} notes with content")
    for doc_id, note in list(notes.items())[:10]:
        print(f"\n  Date: {note['date']}")
        print(f"  Title: {note['title']}")
        attendee_names = [a.get("name") or a.get("email", "") for a in note["attendees"]]
        print(f"  Attendees: {', '.join(attendee_names[:5])}")
        print(f"  Content preview: {note['content'][:200]}...")

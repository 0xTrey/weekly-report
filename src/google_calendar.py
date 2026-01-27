"""
Google Calendar Client

Fetches meetings for the past N days, filtering out:
- Internal events (Lavender, colorId: 1)
- Personal events (Grape, colorId: 3)
- Admin events (Tangerine, colorId: 6)
- Block events (Graphite, colorId: 8)
- Internal-only meetings (all attendees @folloze.com)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# Color IDs to filter out
EXCLUDED_COLOR_IDS = {
    "1",  # Lavender - Internal
    "3",  # Grape - Personal
    "6",  # Tangerine - Admin
    "8",  # Graphite - Calendar Blocks
}


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


def extract_domain(email: str) -> str:
    """Extract domain from email address."""
    if "@" in email:
        return email.split("@")[1].lower()
    return ""


def is_internal_only(attendees: list[dict], internal_domain: str) -> bool:
    """Check if all attendees are from the internal domain."""
    if not attendees:
        return True

    for attendee in attendees:
        email = attendee.get("email", "")
        domain = extract_domain(email)
        if domain and domain != internal_domain:
            return False
    return True


def get_external_domains(attendees: list[dict], internal_domain: str) -> set[str]:
    """Extract external domains from attendee list."""
    domains = set()
    for attendee in attendees:
        email = attendee.get("email", "")
        domain = extract_domain(email)
        if domain and domain != internal_domain:
            domains.add(domain)
    return domains


def fetch_meetings(
    lookback_days: Optional[int] = None,
    internal_domain: Optional[str] = None,
) -> list[dict]:
    """
    Fetch meetings from Google Calendar for the past N days.

    Returns a list of meeting dictionaries with:
    - date: Meeting date (YYYY-MM-DD)
    - title: Event summary
    - attendees: List of attendee emails
    - domains: Set of external domains
    - start_time: ISO timestamp
    - end_time: ISO timestamp
    """
    settings = load_settings()
    lookback_days = lookback_days or settings.get("lookback_days", 7)
    internal_domain = internal_domain or settings.get("internal_domain", "folloze.com")

    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    # Calculate time range
    now = datetime.utcnow()
    time_min = (now - timedelta(days=lookback_days)).isoformat() + "Z"
    time_max = now.isoformat() + "Z"

    # Fetch events
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=500,
    ).execute()

    events = events_result.get("items", [])
    meetings = []

    for event in events:
        # Skip events with excluded colors
        color_id = event.get("colorId")
        if color_id in EXCLUDED_COLOR_IDS:
            continue

        # Skip all-day events (no dateTime)
        start = event.get("start", {})
        if "dateTime" not in start:
            continue

        attendees = event.get("attendees", [])

        # Skip internal-only meetings
        if is_internal_only(attendees, internal_domain):
            continue

        # Extract external domains
        external_domains = get_external_domains(attendees, internal_domain)

        # Parse date
        start_time = start.get("dateTime", "")
        meeting_date = start_time[:10] if start_time else ""

        meetings.append({
            "date": meeting_date,
            "title": event.get("summary", "No Title"),
            "attendees": [a.get("email", "") for a in attendees],
            "domains": external_domains,
            "start_time": start_time,
            "end_time": event.get("end", {}).get("dateTime", ""),
            "event_id": event.get("id", ""),
        })

    return meetings


def get_new_external_domains(
    known_domains: set[str],
    lookback_days: Optional[int] = None,
) -> dict[str, list[dict]]:
    """
    Find new external domains from recent meetings.

    Returns a dict mapping domain -> list of meetings with that domain.
    Only includes domains not in the known_domains set.
    """
    meetings = fetch_meetings(lookback_days=lookback_days)
    new_domains: dict[str, list[dict]] = {}

    for meeting in meetings:
        for domain in meeting["domains"]:
            if domain not in known_domains:
                if domain not in new_domains:
                    new_domains[domain] = []
                new_domains[domain].append(meeting)

    return new_domains


if __name__ == "__main__":
    # Test the module
    print("Fetching recent meetings...")
    meetings = fetch_meetings()
    print(f"Found {len(meetings)} external meetings")
    for m in meetings[:5]:
        print(f"  - {m['date']}: {m['title']} ({', '.join(m['domains'])})")

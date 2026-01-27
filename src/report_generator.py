"""
Report Generator

Creates Google Docs weekly reports with structured content.
Formats: Headers (H1, H2), Bullets. No emojis. No visuals.
"""

import json
from datetime import datetime
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


def create_google_doc(
    title: str,
    folder_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Create a new Google Doc.

    Returns:
        (document_id, document_url)
    """
    creds = get_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # Create the document
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")

    # Move to folder if specified
    if folder_id:
        # Get current parents
        file = drive_service.files().get(
            fileId=doc_id,
            fields="parents"
        ).execute()
        previous_parents = ",".join(file.get("parents", []))

        # Move to new folder
        drive_service.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents"
        ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    return doc_id, doc_url


def build_document_requests(
    deal_updates: dict[str, str],
    agency_updates: dict[str, str],
    tech_updates: dict[str, str],
    report_date: str,
) -> list[dict]:
    """
    Build the batchUpdate requests to populate the document.

    Structure:
    - H1: Weekly Report - [Date]
    - H2: Deal Updates
      - Each deal as bullet points
    - H2: Agency Partner Updates
      - Each partner as bullet points
    - H2: Tech Alliance Updates
      - Each partner as bullet points
    """
    requests = []
    current_index = 1  # Start after the document beginning

    def add_text(text: str, style: Optional[str] = None) -> int:
        """Add text and return the new index position."""
        nonlocal current_index, requests

        requests.append({
            "insertText": {
                "location": {"index": current_index},
                "text": text,
            }
        })

        end_index = current_index + len(text)

        if style == "HEADING_1":
            requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": current_index,
                        "endIndex": end_index,
                    },
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            })
        elif style == "HEADING_2":
            requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": current_index,
                        "endIndex": end_index,
                    },
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType",
                }
            })

        current_index = end_index
        return current_index

    def add_section(title: str, updates: dict[str, str]) -> None:
        """Add a section with H2 header and bulleted content."""
        if not updates:
            return

        # Add section header
        add_text(f"\n{title}\n", "HEADING_2")

        # Add each entity's update
        for entity_name, content in updates.items():
            # Entity name as bold
            add_text(f"\n{entity_name}\n")

            # Content as bullets (each line becomes a bullet)
            for line in content.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("-"):
                    line = f"- {line}"
                if line:
                    add_text(f"{line}\n")

    # Main title
    add_text(f"Weekly Report - {report_date}\n", "HEADING_1")

    # Sections
    add_section("Deal Updates", deal_updates)
    add_section("Agency Partner Updates", agency_updates)
    add_section("Tech Alliance Updates", tech_updates)

    return requests


def generate_report(
    deal_updates: dict[str, str],
    agency_updates: dict[str, str],
    tech_updates: dict[str, str],
    report_date: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate the weekly report as a Google Doc.

    Args:
        deal_updates: Dict mapping deal name -> summary content
        agency_updates: Dict mapping agency name -> summary content
        tech_updates: Dict mapping tech partner name -> summary content
        report_date: Date string for the report title (defaults to today)

    Returns:
        (document_id, document_url)
    """
    settings = load_settings()
    folder_id = settings.get("output_folder_id", "")

    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    title = f"Weekly Report - {report_date}"

    # Create the document
    doc_id, doc_url = create_google_doc(title, folder_id if folder_id else None)

    # Build content requests
    requests = build_document_requests(
        deal_updates=deal_updates,
        agency_updates=agency_updates,
        tech_updates=tech_updates,
        report_date=report_date,
    )

    # Apply updates
    if requests:
        creds = get_credentials()
        docs_service = build("docs", "v1", credentials=creds)

        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests},
        ).execute()

    return doc_id, doc_url


def generate_markdown_report(
    deal_updates: dict[str, str],
    agency_updates: dict[str, str],
    tech_updates: dict[str, str],
    report_date: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate the weekly report as a Markdown file.

    Alternative to Google Docs for local-only usage.

    Returns:
        Path to the generated file
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    lines = [f"# Weekly Report - {report_date}", ""]

    def add_section(title: str, updates: dict[str, str]) -> None:
        if not updates:
            return

        lines.append(f"## {title}")
        lines.append("")

        for entity_name, content in updates.items():
            lines.append(f"### {entity_name}")
            lines.append("")
            for line in content.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("-"):
                    line = f"- {line}"
                if line:
                    lines.append(line)
            lines.append("")

    add_section("Deal Updates", deal_updates)
    add_section("Agency Partner Updates", agency_updates)
    add_section("Tech Alliance Updates", tech_updates)

    content = "\n".join(lines)

    if not output_path:
        output_path = Path(__file__).parent.parent / "logs" / f"weekly_report_{report_date}.md"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    return str(output_path)


if __name__ == "__main__":
    # Test with sample data
    print("Generating test report...")

    test_deals = {
        "Acme Corp": "- Activity: 2 meetings, 5 email threads\n- Deal Status: Pricing discussion ongoing\n- Action Items: Send revised proposal",
    }
    test_agencies = {
        "Agency One": "- Activity: Quarterly review meeting\n- Action Items: Schedule follow-up",
    }
    test_tech = {
        "Tech Partner": "- Activity: Integration testing\n- Risks: API changes pending",
    }

    # Generate markdown (doesn't require Google auth)
    md_path = generate_markdown_report(test_deals, test_agencies, test_tech)
    print(f"Generated: {md_path}")

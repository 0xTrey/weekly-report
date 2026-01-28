"""
Report Generator

Creates Google Docs weekly reports with structured content.
Format:
- H1: Section headers (Deal Updates, Agency Partner Updates, Tech Alliances)
- H2: Company names
- Bold text: Category labels (Activity, Risks, Action Items, etc.)
- Normal text: Content (no bullets, dashes, or markdown)
"""

import json
import re
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


def clean_content(text: str) -> str:
    """
    Clean LLM output by removing markdown formatting.
    - Remove bullet points (-, *, •)
    - Remove markdown headers (#)
    - Remove asterisks used for bold/italic
    - Clean up extra whitespace
    """
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # Strip leading/trailing whitespace
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Remove leading bullets/dashes
        line = re.sub(r"^[-*•]\s*", "", line)

        # Remove markdown headers
        line = re.sub(r"^#+\s*", "", line)

        # Remove bold/italic asterisks but keep the text
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)

        # Clean up extra spaces
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def parse_content_sections(text: str) -> list[tuple[str, str]]:
    """
    Parse content into sections with labels.

    Looks for patterns like:
    - "Activity:" or "Activity -"
    - "Risks:" or "Risks -"
    - "Action Items:" etc.

    Returns list of (label, content) tuples.
    """
    # Clean the text first
    text = clean_content(text)

    # Known section labels
    labels = [
        "Activity", "Deal Status", "Status", "Risks", "Risk",
        "Action Items", "Action Item", "Next Steps", "Summary",
        "Notes", "Key Points", "Concerns", "Blockers"
    ]

    # Build regex pattern for labels
    label_pattern = "|".join(re.escape(l) for l in labels)
    pattern = rf"({label_pattern})\s*[:\-]\s*"

    sections = []
    last_end = 0
    last_label = None

    for match in re.finditer(pattern, text, re.IGNORECASE):
        # Save previous section
        if last_label is not None:
            content = text[last_end:match.start()].strip()
            if content:
                sections.append((last_label, content))

        last_label = match.group(1)
        last_end = match.end()

    # Save final section
    if last_label is not None:
        content = text[last_end:].strip()
        if content:
            sections.append((last_label, content))

    # If no sections found, return entire text as "Summary"
    if not sections and text.strip():
        sections.append(("Summary", text.strip()))

    return sections


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
    - H1: Deal Updates
      - H2: Company Name
        - Bold: Activity
        - Normal: content
    - H1: Agency Partner Updates
    - H1: Tech Alliances
    """
    requests = []
    current_index = 1  # Start after the document beginning
    bold_ranges = []  # Track ranges to make bold

    def add_text(text: str, style: Optional[str] = None, bold: bool = False) -> int:
        """Add text and return the new index position."""
        nonlocal current_index, requests, bold_ranges

        requests.append({
            "insertText": {
                "location": {"index": current_index},
                "text": text,
            }
        })

        start_index = current_index
        end_index = current_index + len(text)

        if style == "HEADING_1":
            requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": start_index,
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
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType",
                }
            })

        if bold:
            # Store range to bold later (exclude newline)
            text_end = end_index - 1 if text.endswith("\n") else end_index
            bold_ranges.append((start_index, text_end))

        current_index = end_index
        return current_index

    def add_entity_content(entity_name: str, content: str) -> None:
        """Add an entity (company) with its content."""
        # Company name as H2
        add_text(f"{entity_name}\n", "HEADING_2")

        # Parse content into sections
        sections = parse_content_sections(content)

        for label, section_content in sections:
            # Label as bold
            add_text(f"{label}: ", bold=True)
            # Content as normal text
            add_text(f"{section_content}\n\n")

    def add_section(title: str, updates: dict[str, str]) -> None:
        """Add a section with H1 header and entity content."""
        if not updates:
            return

        # Section header as H1
        add_text(f"{title}\n", "HEADING_1")

        # Add each entity
        for entity_name, content in updates.items():
            add_entity_content(entity_name, content)

    # Main title
    add_text(f"Weekly Report - {report_date}\n", "HEADING_1")

    # Sections
    add_section("Deal Updates", deal_updates)
    add_section("Agency Partner Updates", agency_updates)
    add_section("Tech Alliances", tech_updates)

    # Add bold formatting requests at the end
    for start, end in bold_ranges:
        requests.append({
            "updateTextStyle": {
                "range": {
                    "startIndex": start,
                    "endIndex": end,
                },
                "textStyle": {"bold": True},
                "fields": "bold",
            }
        })

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

        lines.append(f"# {title}")
        lines.append("")

        for entity_name, content in updates.items():
            lines.append(f"## {entity_name}")
            lines.append("")

            sections = parse_content_sections(content)
            for label, section_content in sections:
                lines.append(f"**{label}:** {section_content}")
                lines.append("")

    add_section("Deal Updates", deal_updates)
    add_section("Agency Partner Updates", agency_updates)
    add_section("Tech Alliances", tech_updates)

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
        "Acme Corp": "Activity: 2 meetings, 5 email threads. Deal Status: Pricing discussion ongoing. Action Items: Send revised proposal by Friday.",
    }
    test_agencies = {
        "Agency One": "Activity: Quarterly review meeting. Action Items: Schedule follow-up for next month.",
    }
    test_tech = {
        "Tech Partner": "Activity: Integration testing completed. Risks: API changes pending in Q2.",
    }

    # Generate markdown (doesn't require Google auth)
    md_path = generate_markdown_report(test_deals, test_agencies, test_tech)
    print(f"Generated: {md_path}")

#!/usr/bin/env python3
"""
Weekly Deal & Partner Report

Main orchestration script that:
1. Runs the interview (new domain confirmation)
2. Collects data (calendar, Granola notes, Gmail)
3. Synthesizes via Ollama (Gemma 3)
4. Generates Google Doc report
5. Commits on success
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.google_calendar import fetch_meetings
from src.gmail_client import get_domain_emails
from src.granola_scanner import get_notes_for_meetings
from src.ollama_client import verify_ollama_setup, synthesize
from src.report_generator import generate_report, generate_markdown_report
from src.interview import run_interview, get_deals_dict, get_partners


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def check_prerequisites() -> bool:
    """Check all prerequisites before running."""
    print("Checking prerequisites...")

    # Check for token.json
    token_path = Path(__file__).parent / "token.json"
    if not token_path.exists():
        print("\nERROR: Google authentication not set up.")
        print("Run: python setup_google_auth.py")
        return False
    print("  Google Auth: OK")

    # Check Ollama
    success, message = verify_ollama_setup()
    if not success:
        print(f"\nERROR: {message}")
        return False
    print(f"  Ollama: OK")

    return True


def collect_data(deals: dict[str, str], agency_partners: dict[str, str], tech_partners: dict[str, str]) -> dict:
    """
    Collect all data for the report.

    Returns dict with:
    - meetings_with_notes: Meetings that have Granola notes
    - deal_emails: Emails per deal domain
    - agency_emails: Emails per agency domain
    - tech_emails: Emails per tech partner domain
    """
    settings = load_settings()
    lookback_days = settings.get("lookback_days", 7)

    print(f"\nCollecting data for the past {lookback_days} days...")

    # Fetch calendar meetings
    print("  Fetching calendar meetings...")
    meetings = fetch_meetings(lookback_days=lookback_days)
    print(f"    Found {len(meetings)} external meetings")

    # Match with Granola notes
    print("  Matching with Granola notes...")
    meetings_with_notes = get_notes_for_meetings(meetings, deals)
    print(f"    Matched {len(meetings_with_notes)} meetings with notes")

    # Fetch emails for deals
    print("  Fetching deal emails...")
    deal_emails = {}
    for domain, name in deals.items():
        emails = get_domain_emails(domain, lookback_days)
        if emails:
            deal_emails[domain] = emails
            print(f"    {name}: Found emails")
        else:
            print(f"    {name}: No emails")

    # Fetch emails for agency partners
    print("  Fetching agency partner emails...")
    agency_emails = {}
    for domain, name in agency_partners.items():
        emails = get_domain_emails(domain, lookback_days)
        if emails:
            agency_emails[domain] = emails
            print(f"    {name}: Found emails")

    # Fetch emails for tech partners
    print("  Fetching tech partner emails...")
    tech_emails = {}
    for domain, name in tech_partners.items():
        emails = get_domain_emails(domain, lookback_days)
        if emails:
            tech_emails[domain] = emails
            print(f"    {name}: Found emails")

    return {
        "meetings_with_notes": meetings_with_notes,
        "deal_emails": deal_emails,
        "agency_emails": agency_emails,
        "tech_emails": tech_emails,
    }


def build_context(
    entity_domain: str,
    entity_name: str,
    data: dict,
    deals: dict[str, str],
) -> str:
    """
    Build context string for LLM synthesis.

    Combines meeting notes and emails for an entity.
    """
    parts = []

    # Add meeting notes
    meetings_with_notes = data.get("meetings_with_notes", {})
    for event_id, entry in meetings_with_notes.items():
        meeting = entry["meeting"]
        note = entry["note"]

        # Check if this meeting involves the entity's domain
        if entity_domain in meeting.get("domains", set()):
            parts.append(f"=== MEETING: {meeting['date']} - {meeting['title']} ===")
            parts.append(note.get("content", ""))
            parts.append("")

    # Add emails
    emails = None
    if entity_domain in data.get("deal_emails", {}):
        emails = data["deal_emails"][entity_domain]
    elif entity_domain in data.get("agency_emails", {}):
        emails = data["agency_emails"][entity_domain]
    elif entity_domain in data.get("tech_emails", {}):
        emails = data["tech_emails"][entity_domain]

    if emails:
        parts.append("=== EMAIL CORRESPONDENCE ===")
        parts.append(emails)

    return "\n".join(parts)


def synthesize_updates(
    data: dict,
    deals: dict[str, str],
    agency_partners: dict[str, str],
    tech_partners: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Run LLM synthesis for all entities.

    Returns:
        (deal_updates, agency_updates, tech_updates)
    """
    print("\nSynthesizing updates via Ollama...")

    deal_updates = {}
    agency_updates = {}
    tech_updates = {}

    # Synthesize deals
    print("  Processing deals...")
    for domain, name in deals.items():
        context = build_context(domain, name, data, deals)
        if context.strip():
            print(f"    Synthesizing: {name}...")
            summary = synthesize(context, name, "deal")
            if not summary.startswith("Error:"):
                deal_updates[name] = summary
            else:
                print(f"      Warning: {summary}")

    # Synthesize agency partners
    print("  Processing agency partners...")
    for domain, name in agency_partners.items():
        context = build_context(domain, name, data, deals)
        if context.strip():
            print(f"    Synthesizing: {name}...")
            summary = synthesize(context, name, "agency_partner")
            if not summary.startswith("Error:"):
                agency_updates[name] = summary

    # Synthesize tech partners
    print("  Processing tech partners...")
    for domain, name in tech_partners.items():
        context = build_context(domain, name, data, deals)
        if context.strip():
            print(f"    Synthesizing: {name}...")
            summary = synthesize(context, name, "tech_partner")
            if not summary.startswith("Error:"):
                tech_updates[name] = summary

    return deal_updates, agency_updates, tech_updates


def git_commit(message: str) -> bool:
    """Commit changes to git."""
    try:
        project_root = Path(__file__).parent

        # Check if git repo exists
        if not (project_root / ".git").exists():
            print("  Initializing git repository...")
            subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)

        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=project_root, check=True, capture_output=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip():
            print("  No changes to commit.")
            return True

        # Commit
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        print("  Changes committed.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"  Git error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate weekly deal and partner report")
    parser.add_argument("--skip-interview", action="store_true", help="Skip the deal interview")
    parser.add_argument("--markdown-only", action="store_true", help="Generate Markdown instead of Google Doc")
    parser.add_argument("--no-commit", action="store_true", help="Skip git commit after completion")
    parser.add_argument("--dry-run", action="store_true", help="Check config and connections without generating report")
    args = parser.parse_args()

    print("=" * 60)
    print("WEEKLY DEAL & PARTNER REPORT")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)

    # Dry-run mode: validate config and exit
    if args.dry_run:
        print("\n" + "-" * 40)
        print("DRY RUN MODE")
        print("-" * 40)

        # Check Granola folder
        settings = load_settings()
        granola_folder_id = settings.get("granola_folder_id", "")
        if granola_folder_id:
            print(f"  Granola folder ID: {granola_folder_id}")
            # Test folder access
            from src.granola_scanner import scan_drive_notes
            try:
                notes = scan_drive_notes()
                print(f"  Granola notes found: {len(notes)}")
            except Exception as e:
                print(f"  Granola folder: ERROR - {e}")
        else:
            print("  Granola folder: NOT CONFIGURED")

        # Load and display configs
        deals = get_deals_dict()
        agency_partners, tech_partners = get_partners()
        print(f"  Active deals: {len(deals)}")
        for domain, name in deals.items():
            print(f"    - {name} ({domain})")
        print(f"  Agency partners: {len(agency_partners)}")
        print(f"  Tech partners: {len(tech_partners)}")

        # Test Ollama
        print("\n  Testing Ollama synthesis...")
        test_result = synthesize("Test context: Meeting scheduled for next week.", "Test Company", "deal")
        if test_result.startswith("Error:"):
            print(f"    FAILED: {test_result}")
        else:
            print(f"    OK (received {len(test_result)} chars)")

        print("\n" + "=" * 60)
        print("DRY RUN COMPLETE - No changes made")
        print("=" * 60)
        sys.exit(0)

    # Step 1: Interview
    if not args.skip_interview:
        run_interview()
    else:
        print("\nSkipping interview (--skip-interview)")

    # Load entity configs
    deals = get_deals_dict()
    agency_partners, tech_partners = get_partners()

    if not deals and not agency_partners and not tech_partners:
        print("\nNo deals or partners configured. Add some to config files and try again.")
        sys.exit(0)

    print(f"\nTracking: {len(deals)} deals, {len(agency_partners)} agencies, {len(tech_partners)} tech partners")

    # Step 2: Collect data
    data = collect_data(deals, agency_partners, tech_partners)

    # Step 3: Synthesize
    deal_updates, agency_updates, tech_updates = synthesize_updates(
        data, deals, agency_partners, tech_partners
    )

    total_updates = len(deal_updates) + len(agency_updates) + len(tech_updates)
    if total_updates == 0:
        print("\nNo activity found for the reporting period. No report generated.")
        sys.exit(0)

    print(f"\nGenerated updates: {len(deal_updates)} deals, {len(agency_updates)} agencies, {len(tech_updates)} tech")

    # Step 4: Generate report
    print("\nGenerating report...")
    report_date = datetime.now().strftime("%Y-%m-%d")

    if args.markdown_only:
        output_path = generate_markdown_report(
            deal_updates=deal_updates,
            agency_updates=agency_updates,
            tech_updates=tech_updates,
            report_date=report_date,
        )
        print(f"  Markdown report: {output_path}")
    else:
        try:
            doc_id, doc_url = generate_report(
                deal_updates=deal_updates,
                agency_updates=agency_updates,
                tech_updates=tech_updates,
                report_date=report_date,
            )
            print(f"  Google Doc: {doc_url}")
        except Exception as e:
            print(f"  Error creating Google Doc: {e}")
            print("  Falling back to Markdown...")
            output_path = generate_markdown_report(
                deal_updates=deal_updates,
                agency_updates=agency_updates,
                tech_updates=tech_updates,
                report_date=report_date,
            )
            print(f"  Markdown report: {output_path}")

    # Step 5: Git commit
    if not args.no_commit:
        print("\nCommitting changes...")
        git_commit(f"Weekly report generated: {report_date}")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

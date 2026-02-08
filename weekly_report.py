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
import time
from datetime import datetime
from pathlib import Path

import requests

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


def start_ollama() -> tuple[bool, bool]:
    """
    Start Ollama server if not already running.

    Returns:
        (success, we_started_it) - second bool tracks if this script started Ollama
    """
    # Check if already running
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("  Ollama: Already running (external session)")
            return True, False
    except requests.exceptions.RequestException:
        pass

    # Start Ollama in background
    print("  Starting Ollama...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for ready (up to 30 seconds)
    for _ in range(30):
        time.sleep(1)
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                print("  Ollama: Started")
                return True, True
        except requests.exceptions.RequestException:
            continue

    print("  ERROR: Ollama failed to start")
    return False, False


def stop_ollama():
    """Stop Ollama server and free memory."""
    print("\nCleaning up Ollama...")

    # Unload models first (graceful)
    try:
        response = requests.get("http://localhost:11434/api/ps", timeout=5)
        if response.status_code == 200:
            running = response.json().get("models", [])
            for model in running:
                model_name = model.get("name", "")
                if model_name:
                    requests.post(
                        "http://localhost:11434/api/generate",
                        json={"model": model_name, "keep_alive": 0},
                        timeout=10,
                    )
                    print(f"  Unloaded: {model_name}")
    except requests.exceptions.RequestException:
        pass

    time.sleep(2)

    # Stop the server
    subprocess.run(["pkill", "ollama"], capture_output=True)
    time.sleep(2)

    # Force kill if still running
    result = subprocess.run(["pgrep", "-x", "ollama"], capture_output=True)
    if result.returncode == 0:
        subprocess.run(["pkill", "-9", "ollama"], capture_output=True)
        print("  Ollama: Force stopped")
    else:
        print("  Ollama: Stopped")


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

    # Start Ollama (tracks if we started it)
    ollama_ok, we_started_ollama = start_ollama()
    if not ollama_ok:
        sys.exit(1)

    try:
        # Check prerequisites
        if not check_prerequisites():
            sys.exit(1)

        # Dry-run mode: validate config and exit
        if args.dry_run:
            print("\n" + "-" * 40)
            print("DRY RUN MODE")
            print("-" * 40)

            # Check Granola local cache
            from src.granola_scanner import scan_local_notes
            try:
                notes = scan_local_notes()
                print(f"  Granola cache: OK ({len(notes)} notes with content)")
            except FileNotFoundError as e:
                print(f"  Granola cache: NOT FOUND - {e}")
            except Exception as e:
                print(f"  Granola cache: ERROR - {e}")

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

    finally:
        # Cleanup: only stop Ollama if this script started it
        if we_started_ollama:
            stop_ollama()
        else:
            print("\n  Ollama: Left running (external session)")


if __name__ == "__main__":
    main()

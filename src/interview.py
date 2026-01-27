"""
Interview Module

Human-in-the-loop setup that:
1. Scans calendar for new external domains
2. Prompts user to classify them as deals
3. Updates active_deals.json
4. Asks about deals to remove
"""

import json
from datetime import datetime
from pathlib import Path

from src.google_calendar import get_new_external_domains


def load_config(filename: str) -> dict | list:
    """Load a config file."""
    config_path = Path(__file__).parent.parent / "config" / filename
    with open(config_path) as f:
        return json.load(f)


def save_config(filename: str, data: dict | list) -> None:
    """Save a config file."""
    config_path = Path(__file__).parent.parent / "config" / filename
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


def get_known_domains() -> set[str]:
    """Get all known domains (deals + partners)."""
    deals = load_config("active_deals.json")
    partners = load_config("partners.json")

    known = set()

    # Add deal domains
    for deal in deals:
        known.add(deal.get("domain", ""))

    # Add partner domains
    for partner in partners.get("agency_partners", []):
        known.add(partner.get("domain", ""))
    for partner in partners.get("tech_partners", []):
        known.add(partner.get("domain", ""))

    return known


def run_interview() -> None:
    """
    Run the human-in-the-loop interview process.

    1. Find new external domains from recent meetings
    2. Ask user to classify each as deal or skip
    3. Update active_deals.json
    4. Ask about closing existing deals
    """
    print("\n" + "=" * 60)
    print("DEAL & PARTNER REVIEW")
    print("=" * 60)

    # Get known domains
    known_domains = get_known_domains()
    settings = load_config("settings.json")
    internal_domain = settings.get("internal_domain", "folloze.com")
    known_domains.add(internal_domain)

    # Find new domains
    print("\nScanning calendar for new external contacts...")
    new_domains = get_new_external_domains(known_domains)

    if not new_domains:
        print("No new external domains found in recent meetings.")
    else:
        print(f"\nFound {len(new_domains)} new domain(s):\n")

        deals = load_config("active_deals.json")
        today = datetime.now().strftime("%Y-%m-%d")

        for domain, meetings in new_domains.items():
            # Show meeting context
            print(f"Domain: {domain}")
            print(f"  Meetings: {len(meetings)}")
            for m in meetings[:3]:
                print(f"    - {m['date']}: {m['title']}")

            # Ask user
            response = input(f"\n  Is this a Deal? Enter company name (or press Enter to skip): ").strip()

            if response:
                deals.append({
                    "domain": domain,
                    "name": response,
                    "added": today,
                })
                print(f"  Added '{response}' as a deal.")
            else:
                print("  Skipped.")

            print()

        # Save updated deals
        save_config("active_deals.json", deals)

    # Review existing deals
    print("\n" + "-" * 40)
    print("EXISTING DEALS REVIEW")
    print("-" * 40)

    deals = load_config("active_deals.json")

    if not deals:
        print("No active deals.")
    else:
        print(f"\nActive deals ({len(deals)}):\n")
        for i, deal in enumerate(deals):
            print(f"  {i + 1}. {deal['name']} ({deal['domain']}) - Added: {deal.get('added', 'unknown')}")

        print("\nEnter numbers to remove (comma-separated), or press Enter to keep all:")
        response = input("> ").strip()

        if response:
            try:
                indices = [int(x.strip()) - 1 for x in response.split(",")]
                removed = []
                new_deals = []

                for i, deal in enumerate(deals):
                    if i in indices:
                        removed.append(deal["name"])
                    else:
                        new_deals.append(deal)

                if removed:
                    save_config("active_deals.json", new_deals)
                    print(f"\nRemoved: {', '.join(removed)}")
                else:
                    print("\nNo deals removed.")

            except ValueError:
                print("Invalid input. No deals removed.")
        else:
            print("All deals kept.")

    print("\n" + "=" * 60)
    print("Interview complete.")
    print("=" * 60 + "\n")


def get_deals_dict() -> dict[str, str]:
    """
    Get deals as a domain -> name mapping.
    """
    deals = load_config("active_deals.json")
    return {d["domain"]: d["name"] for d in deals}


def get_partners() -> tuple[dict[str, str], dict[str, str]]:
    """
    Get partners as domain -> name mappings.

    Returns:
        (agency_partners, tech_partners)
    """
    partners = load_config("partners.json")

    agency = {p["domain"]: p["name"] for p in partners.get("agency_partners", [])}
    tech = {p["domain"]: p["name"] for p in partners.get("tech_partners", [])}

    return agency, tech


if __name__ == "__main__":
    run_interview()

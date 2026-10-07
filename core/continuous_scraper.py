"""
Continuous Google Maps Lead & Website Scraper (No WhatsApp).
Runs continuously ("again and again") through target cities and high-potential
business categories across Tamil Nadu using Conor's Docker Scraper, with deep
Website Detection & Web Search verification.

Features:
- Completely skips WhatsApp messaging (zero browser popups, zero chat sends).
- Dual Website Discovery:
    1. Extracts official website directly from Google Maps if listed.
    2. If no website is on Google Maps, automatically executes a live web search
       to uncover official websites, custom domains, or active Instagram/Facebook profiles.
- Captures businesses both WITH websites and WITHOUT websites, clearly tagging their status.
- Real-time deduplication against a persistent master database (Place ID, Name, Phone).
- Saves every batch to `leads_output/master_scraped_leads.csv` and
  `leads_output/tamil_nadu_continuous_leads.csv` so the Dashboard (viewer.html)
  always displays live updated leads with website data.
- Automatically repeats cycle after cycle until stopped by the user (Ctrl+C).
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import os
import sys
import csv
import json
import time
import random
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import (
    DEFAULT_CRITERIA,
    OUTPUT_DIR,
    TAMIL_NADU_TARGETS
)
from places_client import GooglePlacesClient
from lead_finder import (
    calculate_lead_score,
    is_qualified_lead,
    export_to_csv,
    export_to_excel
)
from whatsapp_sender import normalize_indian_phone

# Optional auto-email sender
try:
    from send_cold_emails import send_single_lead_email
except ImportError:
    send_single_lead_email = None

AUTO_SEND_EMAILS = os.getenv("AUTO_SEND_EMAILS", "false").lower() in ("1", "true", "yes")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "").strip()
SENDER_NAME = os.getenv("SENDER_NAME", "").strip() or "Web Designer"
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
MASTER_LEADS_FILE = OUTPUT_DIR / "master_scraped_leads.csv"
ACTIVE_SESSION_CSV = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
ACTIVE_SESSION_XLSX = OUTPUT_DIR / "tamil_nadu_continuous_leads.xlsx"

# Aggregator directories and non-business domains to ignore when searching for official websites
IGNORED_DOMAINS = [
    "justdial.com", "sulekha.com", "indiamart.com", "zaubacorp.com",
    "yellowpages.com", "google.com", "maps.google.com", "tripadvisor.com",
    "zomato.com", "swiggy.com", "magicpin.in", "ninjadial.com", "jdmagicbox.com",
    "tradeindia.com", "dial4trade.com", "wikipedia.org", "quora.com", "reddit.com",
    "mouthshut.com", "youtube.com", "twitter.com", "x.com", "linkedin.com",
    "nearbuy.com", "eattreat.in", "dineout.co.in"
]

# Extended rich category catalog for high-converting local businesses
EXPANDED_CATEGORIES = [
    "restaurants",
    "salons",
    "bakeries",
    "meat shops",
    "sweet stalls",
    "clothing boutiques",
    "furniture showrooms",
    "spas",
    "bridal studios",
    "textile showrooms",
    "travel agencies",
    "cafes",
    "gyms and fitness centers"
]


from social_search_engine import search_socials_and_gmail


def load_known_leads() -> Tuple[Set[str], Set[str], Set[str], int]:
    """
    Loads all previously scraped place IDs, normalized names, and phones
    across all existing CSV files in leads_output to ensure zero duplicates.
    """
    seen_place_ids: Set[str] = set()
    seen_names: Set[str] = set()
    seen_phones: Set[str] = set()
    total_loaded = 0

    csv_files = list(OUTPUT_DIR.glob("*.csv"))
    for csv_file in csv_files:
        try:
            with open(csv_file, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_loaded += 1
                    pid = row.get("Google Place ID") or row.get("place_id") or ""
                    name = (row.get("Business Name") or row.get("name") or "").strip().lower()
                    phone = (row.get("Cleaned Mobile") or row.get("Cleaned Phone") or row.get("Phone") or "").strip()

                    if pid:
                        seen_place_ids.add(pid)
                    if name:
                        seen_names.add(name)
                    if phone:
                        digits = "".join(c for c in phone if c.isdigit())
                        if len(digits) >= 10:
                            seen_phones.add(digits[-10:])
        except Exception:
            continue

    return seen_place_ids, seen_names, seen_phones, total_loaded


def append_to_master(leads: List[Dict[str, Any]]):
    """Appends newly qualified leads to master_scraped_leads.csv."""
    if not leads:
        return

    fieldnames = [
        "Business Name",
        "Category",
        "City",
        "Rating",
        "Review Count",
        "Phone",
        "Cleaned Mobile",
        "Gmail",
        "Website",
        "Website Status",
        "Social Media URL",
        "Address",
        "Google Maps URL",
        "Lead Score",
        "Priority Tier",
        "Verification Status",
        "Verification Notes",
        "Google Place ID",
        "Email Sent At",
        "Scraped At"
    ]

    file_exists = MASTER_LEADS_FILE.exists()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(MASTER_LEADS_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        for lead in leads:
            writer.writerow({
                "Business Name": lead.get("name", ""),
                "Category": lead.get("category", ""),
                "City": lead.get("city", ""),
                "Rating": lead.get("rating", 0.0),
                "Review Count": lead.get("review_count", 0),
                "Phone": lead.get("phone", ""),
                "Cleaned Mobile": lead.get("cleaned_phone", ""),
                "Gmail": lead.get("gmail", ""),
                "Website": lead.get("website", "") or "NO WEBSITE LISTED",
                "Website Status": lead.get("website_status", "Confirmed No Website or Socials"),
                "Verification Status": lead.get("verification_status", "NO WEBSITE OR SOCIALS"),
                "Verification Notes": lead.get("website_status", ""),
                "Social Media URL": lead.get("social_url", ""),
                "Address": lead.get("address", ""),
                "Google Maps URL": lead.get("google_maps_url", ""),
                "Lead Score": lead.get("lead_score", 0),
                "Priority Tier": lead.get("priority", ""),
                "Google Place ID": lead.get("place_id", ""),
                "Email Sent At": lead.get("Email Sent At") or lead.get("email_sent_at") or "",
                "Scraped At": now_str
            })


def update_active_session_files(session_leads: List[Dict[str, Any]]):
    """
    Rewrites the active session CSV & Excel so dashboard.py / viewer.html
    can load the updated list dynamically.
    """
    if not session_leads:
        return

    fieldnames = [
        "Business Name", "Category", "City", "Rating", "Review Count",
        "Phone", "Cleaned Mobile", "Gmail", "Website", "Website Status", "Social Media URL",
        "Address", "Google Maps URL", "Lead Score", "Priority Tier",
        "Verification Status", "Verification Notes", "Google Place ID", "Email Sent At"
    ]

    with open(ACTIVE_SESSION_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in session_leads:
            writer.writerow({
                "Business Name": lead.get("name", ""),
                "Category": lead.get("category", ""),
                "City": lead.get("city", ""),
                "Rating": lead.get("rating", 0.0),
                "Review Count": lead.get("review_count", 0),
                "Phone": lead.get("phone", ""),
                "Cleaned Mobile": lead.get("cleaned_phone", ""),
                "Gmail": lead.get("gmail", ""),
                "Website": lead.get("website", "") or "NO WEBSITE LISTED",
                "Website Status": lead.get("website_status", "Confirmed No Website or Socials"),
                "Social Media URL": lead.get("social_url", ""),
                "Address": lead.get("address", ""),
                "Google Maps URL": lead.get("google_maps_url", ""),
                "Lead Score": lead.get("lead_score", 0),
                "Priority Tier": lead.get("priority", ""),
                "Verification Status": lead.get("verification_status", "NO WEBSITE OR SOCIALS"),
                "Verification Notes": lead.get("website_status", ""),
                "Google Place ID": lead.get("place_id", ""),
                "Email Sent At": lead.get("Email Sent At") or lead.get("email_sent_at") or ""
            })

    try:
        export_to_excel(session_leads, ACTIVE_SESSION_XLSX)
    except Exception:
        pass

    try:
        # Also auto-update leads_data.js so viewer.html updates whether on file:// or http://
        master_file = OUTPUT_DIR / "master_scraped_leads.csv"
        target_csv = master_file if master_file.exists() else ACTIVE_SESSION_CSV
        if target_csv.exists():
            with open(target_csv, mode="r", encoding="utf-8-sig") as f:
                all_leads_dicts = list(csv.DictReader(f))
            js_file = BASE_DIR / "leads_data.js"
            with open(js_file, mode="w", encoding="utf-8") as f:
                f.write("window.EMBEDDED_LEADS = " + json.dumps(all_leads_dicts, indent=2, ensure_ascii=False) + ";\n")
    except Exception:
        pass


def build_search_queue(focus_city: str = None, focus_category: str = None) -> List[Tuple[str, str]]:
    """Builds the rotating queue of (City, Category) queries."""
    queue = []

    # Single targeted search
    if focus_city and focus_category:
        return [(focus_city, focus_category)]

    if focus_city and not focus_category:
        for cat in EXPANDED_CATEGORIES:
            queue.append((focus_city, cat))
        return queue

    if focus_category and not focus_city:
        for city in TAMIL_NADU_TARGETS.keys():
            queue.append((city, focus_category))
        return queue

    # Default: Comprehensive Matrix across all cities and categories
    for city, categories in TAMIL_NADU_TARGETS.items():
        for cat in categories:
            queue.append((city, cat))

    # Add extra high-yield categories across top cities
    top_cities = ["Coimbatore", "Chennai", "Madurai", "Trichy", "Salem"]
    extra_cats = ["salons", "spas", "bridal studios", "cafes", "travel agencies"]
    for city in top_cities:
        for cat in extra_cats:
            pair = (city, cat)
            if pair not in queue:
                queue.append(pair)

    random.seed(42)
    random.shuffle(queue)
    return queue


def run_continuous_scraping(
    focus_city: str = None,
    focus_category: str = None,
    min_rating: float = 4.5,
    min_reviews: int = 50,
    no_website_only: bool = False,
    max_results_per_query: int = 40,
    pause_between_queries: int = 4,
    pause_between_cycles: int = 15
):
    """
    Infinite loop running Google Maps scraper again and again across
    configured cities and categories with automated website search.
    """
    console.print(Panel(
        f"[bold green]⚡ Continuous Google Maps & Website Scraper Active[/bold green]\n"
        f"• WhatsApp Messaging: [bold red]DISABLED (Scrape-Only Mode)[/bold red]\n"
        f"• Website Search: [bold cyan]ENABLED[/bold cyan] (Extracts Maps websites + Live Web Search)\n"
        f"• Website Inclusion: [bold]{'Only shops without websites' if no_website_only else 'ALL shops (Searches & Tags Websites)'}[/bold]\n"
        f"• Rating Filter: >= [bold]{min_rating}★[/bold] | Reviews: >= [bold]{min_reviews}[/bold]\n"
        f"• Engine: [bold cyan]Conor's Docker Scraper[/bold cyan] (http://localhost:8001)\n"
        f"• Master Output: [cyan]{MASTER_LEADS_FILE}[/cyan]\n"
        f"• Active Dashboard File: [cyan]{ACTIVE_SESSION_CSV}[/cyan]\n"
        f"• Press [bold yellow]Ctrl+C[/bold yellow] anytime to pause or stop.",
        border_style="green",
        title="Continuous Lead & Website Engine"
    ))

    # Check client
    client = GooglePlacesClient(use_docker=True)
    if not client.is_docker_alive():
        console.print("[red]✖ Error: Docker scraper container is not responding at http://localhost:8001.[/red]")
        console.print("[yellow]Please ensure Docker Desktop is running (`run.bat start-docker`).[/yellow]")
        return

    # Load existing deduplication cache
    seen_place_ids, seen_names, seen_phones, total_loaded = load_known_leads()
    console.print(f"[dim]Loaded {total_loaded} existing lead records across local CSVs for deduplication.[/dim]\n")

    search_queue = build_search_queue(focus_city, focus_category)
    console.print(f"[bold cyan]Queue Initialized:[/bold cyan] {len(search_queue)} distinct target scans in rotation.\n")

    criteria = {
        "min_rating": min_rating,
        "min_reviews": min_reviews,
        "only_no_website": no_website_only,
        "require_phone": False,
        "operational_only": True,
        "max_results_per_query": max_results_per_query
    }

    session_all_leads: List[Dict[str, Any]] = []
    cycle_count = 1
    total_new_leads_found = 0
    total_inspected_all_time = 0

    try:
        while True:
            console.print(f"\n[bold yellow]═══════════════════════════════════════════════════════════════[/bold yellow]")
            console.print(f"[bold yellow]  Starting Scraping Cycle #{cycle_count} ({len(search_queue)} targets) [/bold yellow]")
            console.print(f"[bold yellow]═══════════════════════════════════════════════════════════════[/bold yellow]\n")

            cycle_new_leads = 0

            for idx, (city, category) in enumerate(search_queue, 1):
                query = f"{category} in {city}, Tamil Nadu"
                console.print(f"[{idx}/{len(search_queue)}] 🔍 Scanning: [bold cyan]{query}[/bold cyan] ...", end="\r")

                try:
                    raw_places = client.search_places(query=query, max_results=max_results_per_query)
                except Exception as e:
                    console.print(f"\n[red]✖ Query failed ({query}): {e}[/red]")
                    time.sleep(pause_between_queries)
                    continue

                total_inspected_all_time += len(raw_places)
                new_qualified_in_batch = []

                for p in raw_places:
                    place_id = p.get("place_id") or ""
                    raw_name = p.get("name", "").strip()
                    norm_name = raw_name.lower()
                    raw_phone = p.get("phone", "")

                    # Deduplication check
                    if place_id and place_id in seen_place_ids:
                        continue
                    if norm_name and norm_name in seen_names:
                        continue

                    # Check phone normalization
                    clean_phone, phone_type = normalize_indian_phone(raw_phone)
                    if clean_phone:
                        core_phone = clean_phone[-10:]
                        if core_phone in seen_phones:
                            continue

                    # Basic rating & review thresholds
                    rating = p.get("rating", 0.0)
                    reviews = p.get("review_count", 0)
                    if rating < min_rating or reviews < min_reviews:
                        continue

                    # Website & Social Discovery Logic
                    raw_website = (p.get("website") or "").strip()
                    gmail = ""
                    if raw_website:
                        if "instagram.com" in raw_website.lower() or "facebook.com" in raw_website.lower():
                            website = "NO WEBSITE LISTED"
                            website_status = "Social Media on Maps"
                            verification_status = "HAS SOCIALS BUT NO WEBSITE"
                            social_url = raw_website
                            # Search for Gmail as well
                            try:
                                s_res = search_socials_and_gmail(raw_name, city, category)
                                gmail = s_res.get("gmail", "")
                            except Exception:
                                pass
                        else:
                            website = raw_website
                            website_status = "Found on Google Maps"
                            verification_status = "WEBSITE FOUND"
                            social_url = ""
                    else:
                        # User requirement: "if the shop has no website, search for socials and THEN label it as no website."
                        # "acheck if they have a gmail and also save that."
                        s_res = search_socials_and_gmail(raw_name, city, category)
                        social_url = s_res.get("social_url", "")
                        gmail = s_res.get("gmail", "")

                        if social_url:
                            website = "NO WEBSITE LISTED"
                            website_status = "Active Social Found Online"
                            verification_status = "HAS SOCIALS BUT NO WEBSITE"
                        else:
                            website = "NO WEBSITE LISTED"
                            website_status = "Confirmed No Website or Socials"
                            verification_status = "NO WEBSITE OR SOCIALS"

                    if no_website_only and verification_status == "WEBSITE FOUND":
                        continue

                    p["website"] = website
                    p["website_status"] = website_status
                    p["verification_status"] = verification_status
                    p["social_url"] = social_url
                    p["gmail"] = gmail

                    # Enrich lead
                    score, priority = calculate_lead_score(p)
                    p["city"] = city
                    p["category"] = category
                    p["lead_score"] = score
                    p["priority"] = priority
                    p["cleaned_phone"] = clean_phone or ""

                    # Add to tracking
                    if place_id:
                        seen_place_ids.add(place_id)
                    if norm_name:
                        seen_names.add(norm_name)
                    if clean_phone:
                        seen_phones.add(clean_phone[-10:])

                    new_qualified_in_batch.append(p)

                # Report outcome of this search
                if new_qualified_in_batch:
                    console.print(f"[{idx}/{len(search_queue)}] ✔ [bold green]{query}[/bold green] -> [bold yellow]+{len(new_qualified_in_batch)} QUALIFIED LEADS[/bold yellow] (from {len(raw_places)} places)")
                    
                    # Preview top found in this batch with website status
                    for lead in new_qualified_in_batch[:3]:
                        web_preview = lead.get("website", "")
                        if "http" in web_preview.lower():
                            web_tag = f"[cyan]{web_preview}[/cyan] ({lead.get('website_status')})"
                        elif lead.get("verification_status") == "HAS SOCIALS BUT NO WEBSITE":
                            web_tag = f"[magenta]📱 Has Socials: {lead.get('social_url')}[/magenta]"
                        else:
                            web_tag = f"[dim]🚫 No Website or Socials[/dim]"

                        gmail_tag = f" | ✉️ {lead.get('gmail')}" if lead.get('gmail') else ""
                        console.print(f"   ★ {lead.get('name')} | {lead.get('rating')}★ ({lead.get('review_count')} revs) | Phone: {lead.get('cleaned_phone') or lead.get('phone') or 'N/A'}{gmail_tag}\n     └─ {web_tag}")

                    if len(new_qualified_in_batch) > 3:
                        console.print(f"   [dim]... and {len(new_qualified_in_batch) - 3} more leads saved with website details[/dim]")

                    # Auto-send email pitch immediately if Gmail configured (zero approval)
                    if AUTO_SEND_EMAILS and SENDER_EMAIL and GMAIL_APP_PASSWORD and send_single_lead_email:
                        for lead in new_qualified_in_batch:
                            # CRITICAL: STRICTLY ONLY EMAIL SHOPS WITHOUT A WEBSITE
                            l_web = (lead.get("website") or "").strip().lower()
                            l_status = (lead.get("verification_status") or "").strip().upper()
                            if (l_web.startswith("http") and "instagram.com" not in l_web and "facebook.com" not in l_web) or "WEBSITE FOUND" in l_status:
                                continue

                            lead_gmail = (lead.get("gmail") or "").strip()
                            if lead_gmail and "@" in lead_gmail and not lead.get("Email Sent At"):
                                console.print(f"   ✉️ [bold cyan]Auto-sending email pitch to (No Website): {lead.get('name')} ({lead_gmail})...[/bold cyan]", end="")
                                success = send_single_lead_email(
                                    lead=lead,
                                    sender_email=SENDER_EMAIL,
                                    sender_name=SENDER_NAME,
                                    app_password=GMAIL_APP_PASSWORD
                                )
                                if success:
                                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    lead["Email Sent At"] = ts
                                    console.print(f" [bold green]✔ Delivered![/bold green]")
                                    time.sleep(random.uniform(5.0, 9.0))
                                else:
                                    console.print(f" [red]❌ Failed[/red]")

                    # Append to master file and active session
                    append_to_master(new_qualified_in_batch)
                    session_all_leads.extend(new_qualified_in_batch)
                    update_active_session_files(session_all_leads)

                    cycle_new_leads += len(new_qualified_in_batch)
                    total_new_leads_found += len(new_qualified_in_batch)
                else:
                    console.print(f"[{idx}/{len(search_queue)}] · [dim]{query}[/dim] -> {len(raw_places)} listings scanned (0 new uncontacted)")

                # Rest between queries
                time.sleep(pause_between_queries)

            console.print(f"\n[bold green]✔ Cycle #{cycle_count} Completed![/bold green]")
            console.print(f"• New Qualified Leads this cycle: [bold yellow]{cycle_new_leads}[/bold yellow]")
            console.print(f"• Total Leads Collected Session: [bold cyan]{total_new_leads_found}[/bold cyan]")
            console.print(f"• Total Inspected All-Time: [bold]{total_inspected_all_time}[/bold]")
            console.print(f"• Taking a {pause_between_cycles}s rest before repeating Cycle #{cycle_count + 1}...\n")

            cycle_count += 1
            time.sleep(pause_between_cycles)

    except KeyboardInterrupt:
        console.print("\n[yellow]Continuous scraper stopped by user (Ctrl+C).[/yellow]")

    finally:
        console.print(Panel(
            f"[bold green]Continuous Scraping Summary[/bold green]\n"
            f"• Total New Leads Added: [bold]{total_new_leads_found}[/bold]\n"
            f"• Master Lead File: [cyan]{MASTER_LEADS_FILE}[/cyan]\n"
            f"• Active Dashboard File: [cyan]{ACTIVE_SESSION_CSV}[/cyan]\n"
            f"• Open [bold]http://localhost:8521/viewer.html[/bold] to inspect and manage all leads.",
            title="Session Finished",
            border_style="green"
        ))


def main():
    parser = argparse.ArgumentParser(description="Continuous Google Maps & Website Scraper (No WhatsApp).")
    parser.add_argument("--city", type=str, default=None, help="Focus on a single city (e.g. Coimbatore, Chennai, Madurai)")
    parser.add_argument("--category", type=str, default=None, help="Focus on a single category (e.g. salons, restaurants, bakeries)")
    parser.add_argument("--min-rating", type=float, default=4.5, help="Minimum Star Rating (default: 4.5)")
    parser.add_argument("--min-reviews", type=int, default=50, help="Minimum Review Count (default: 50)")
    parser.add_argument("--no-website-only", action="store_true", help="Only keep businesses that definitely lack a website")
    parser.add_argument("--max-results", type=int, default=DEFAULT_CRITERIA.get("max_results_per_query", 40), help="Places per query (default: 40)")
    parser.add_argument("--delay", type=int, default=4, help="Seconds to wait between search queries (default: 4)")
    parser.add_argument("--cycle-delay", type=int, default=15, help="Seconds to wait between full cycles (default: 15)")
    args = parser.parse_args()

    run_continuous_scraping(
        focus_city=args.city,
        focus_category=args.category,
        min_rating=args.min_rating,
        min_reviews=args.min_reviews,
        no_website_only=args.no_website_only,
        max_results_per_query=args.max_results,
        pause_between_queries=args.delay,
        pause_between_cycles=args.cycle_delay
    )


if __name__ == "__main__":
    main()
